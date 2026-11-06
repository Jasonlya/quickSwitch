"""可选的局域网 UDP 设备发现（``peer_host`` 配成 ``"auto"`` 时使用）。

两端各自周期性向广播地址发送一条 JSON 公告，同时在本机端口监听公告；
收到公告后即可得到对端当前 IP，从而在 DHCP 变动、没有 Tailscale 的场景下自动寻址。

注意：广播只在同一广播域（同一网段/VLAN）内有效；跨网段请改用 Tailscale 或静态绑定。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import socket
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

log = logging.getLogger("discovery")

MAGIC = "quickswitch/1"
DEFAULT_PORT = 8766

PeerHook = Callable[[Dict[str, Any]], None]


def local_ipv4_addresses() -> List[str]:
    """返回本机默认出口网卡的 IPv4，不依赖可能阻塞的主机名 DNS 查询。

    GitHub 的 macOS Runner 上，解析 ``socket.gethostname()`` 可能卡住数十秒；
    这里对固定 IP 做 UDP ``connect``（不发送数据），只让系统选择出口网卡。
    使用几个不同目标可覆盖默认路由切换的情况，重复地址会自动去重。
    """
    result: List[str] = []
    for target in ("1.1.1.1", "8.8.8.8", "223.5.5.5"):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect((target, 80))
            address = str(probe.getsockname()[0])
        except OSError:
            continue
        finally:
            probe.close()
        if address and not address.startswith(("127.", "169.254.")) and address not in result:
            result.append(address)
    return result


class PeerDiscovery:
    """广播 + 监听同一端口，维护一份「在线设备表」。"""

    def __init__(
        self,
        name: str,
        listen_port: int,
        *,
        port: int = DEFAULT_PORT,
        interval: float = 5.0,
        ttl: float = 15.0,
        role: str = "server",
        on_peer: Optional[PeerHook] = None,
        broadcast: Union[str, List[str]] = "255.255.255.255",
        infer_subnet_broadcast: bool = True,
    ) -> None:
        self.name = name
        self.listen_port = int(listen_port)
        self.port = int(port)
        self.interval = float(interval)
        self.ttl = float(ttl)
        self.role = role
        self.on_peer = on_peer
        if isinstance(broadcast, (list, tuple)):
            self.broadcast = [str(item) for item in broadcast if item]
        else:
            self.broadcast = [broadcast] if broadcast else []
        self.infer_subnet_broadcast = infer_subnet_broadcast
        self._sock: Optional[socket.socket] = None
        self._tasks: List[asyncio.Task] = []
        self._peers: Dict[str, Dict[str, Any]] = {}
        self._sequence = 0
        self._running = False

    # ---------------------------------------------------------------- 目标地址
    def broadcast_targets(self) -> List[Tuple[str, int]]:
        """返回全部公告目标：配置里的广播地址 + 按本机网段推导的 x.y.z.255。"""
        targets: List[Tuple[str, int]] = []
        for address in self.broadcast:
            if address and (address, self.port) not in targets:
                targets.append((address, self.port))
        if self.infer_subnet_broadcast:
            for address in local_ipv4_addresses():
                parts = address.split(".")
                if len(parts) != 4:
                    continue
                subnet = ".".join(parts[:3] + ["255"])
                if (subnet, self.port) not in targets:
                    targets.append((subnet, self.port))
        return targets

    # ---------------------------------------------------------------- 报文
    def build_packet(self) -> bytes:
        payload = {
            "magic": MAGIC,
            "name": self.name,
            "port": self.listen_port,
            "role": self.role,
            "ts": time.time(),
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def parse_packet(data: bytes) -> Optional[Dict[str, Any]]:
        try:
            payload = json.loads(data.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("magic") != MAGIC:
            return None
        name = payload.get("name")
        port = payload.get("port")
        if not isinstance(name, str) or not name or not isinstance(port, int):
            return None
        return payload

    # ---------------------------------------------------------------- 生命周期
    async def start(self) -> "PeerDiscovery":
        if self._running:
            return self
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        sock.bind(("", self.port))
        self._sock = sock
        self._running = True
        loop = asyncio.get_running_loop()
        self._tasks = [
            loop.create_task(self._listen_loop(), name=f"{self.name}-discovery-listen"),
            loop.create_task(self._announce_loop(), name=f"{self.name}-discovery-announce"),
        ]
        log.info("设备发现已启用：监听 udp/%s，公告名称 %s", self.port, self.name)
        return self

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._sock is not None:
            with contextlib.suppress(Exception):
                self._sock.close()
            self._sock = None

    # ---------------------------------------------------------------- 设备表
    def peers(self) -> Dict[str, Dict[str, Any]]:
        self._prune()
        # Web 控制台会在别的线程读这张表，先做快照再遍历
        return {name: dict(info) for name, info in list(self._peers.items())}

    def best_peer(self, exclude: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        self._prune()
        excluded = set(exclude or ())
        candidates = [info for name, info in self._peers.items() if name not in excluded]
        if not candidates:
            return None
        # Windows 的 monotonic 时钟精度可能让两条公告落在同一时刻，用单调序号兜底。
        return dict(max(candidates, key=lambda info: (info["ts"], info.get("seq", 0))))

    def observe(self, data: bytes, addr: Tuple[str, int]) -> Optional[Dict[str, Any]]:
        """处理一个数据报；返回「新发现或地址变化」的设备信息，否则 None。"""
        payload = self.parse_packet(data)
        if payload is None:
            return None
        if payload["name"] == self.name:
            return None  # 忽略自己（多网卡时可能收到本机广播）
        host = addr[0]
        previous = self._peers.get(payload["name"])
        self._sequence += 1
        info = {
            "name": payload["name"],
            "host": host,
            "port": payload["port"],
            "role": payload.get("role"),
            "ts": time.monotonic(),
            "seq": self._sequence,
        }
        self._peers[payload["name"]] = info
        if previous is None or previous["host"] != host or previous["port"] != info["port"]:
            log.info("发现设备 %s（%s:%s，role=%s）", info["name"], host, info["port"], info["role"])
            if self.on_peer:
                try:
                    self.on_peer(dict(info))
                except Exception as exc:
                    log.debug("on_peer 回调异常：%s", exc)
            return dict(info)
        return None

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [name for name, info in self._peers.items() if now - info["ts"] > self.ttl]
        for name in expired:
            log.info("设备 %s 已离线（超过 %.0fs 无公告）", name, self.ttl)
            self._peers.pop(name, None)

    # ---------------------------------------------------------------- 循环
    async def _listen_loop(self) -> None:
        sock = self._sock
        assert sock is not None
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                # sock_recvfrom 同时支持 macOS 的 selector 和 Windows 的
                # ProactorEventLoop；add_reader 在 Windows 上不可用。
                data, addr = await loop.sock_recvfrom(sock, 4096)
            except asyncio.CancelledError:
                raise
            except OSError as exc:
                if self._running:
                    log.debug("设备发现接收失败：%s", exc)
                return
            self.observe(data, addr)

    async def _announce_loop(self) -> None:
        sock = self._sock
        assert sock is not None
        failures = 0
        while self._running:
            packet = self.build_packet()
            delivered = False
            for target in self.broadcast_targets():
                try:
                    sock.sendto(packet, target)
                    delivered = True
                except OSError as exc:
                    log.debug("公告发送到 %s 失败：%s", target[0], exc)
            if delivered:
                failures = 0
            else:
                failures += 1
                if failures == 3:
                    log.warning(
                        "连续 %s 次无法发出设备发现公告（可能没有广播路由）。\n"
                        "  可配置 discovery.broadcast 指定网段广播地址，"
                        "或改用固定 IP / Tailscale。",
                        failures,
                    )
            await asyncio.sleep(self.interval)
