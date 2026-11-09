"""Wake-on-LAN helpers used by the switching safety guard.

The implementation intentionally uses only the standard library.  A machine
advertises all of its physical interface MAC addresses to the peer; the user
can override the target address with ``wake.mac`` when the automatic value is
not the NIC that supports Wake-on-LAN.
"""
from __future__ import annotations

import csv
import io
import logging
import platform
import re
import socket
import subprocess
import uuid
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union

from discovery import local_ipv4_addresses

log = logging.getLogger("wol")

MAC_HEX_RE = re.compile(r"^[0-9a-fA-F]{12}$")


def normalize_mac(value: object) -> Optional[str]:
    """Return a lower-case colon separated MAC address, or ``None``."""
    text = re.sub(r"[^0-9a-fA-F]", "", str(value or ""))
    if not MAC_HEX_RE.match(text):
        return None
    if not int(text, 16):
        return None
    return ":".join(text[i : i + 2] for i in range(0, 12, 2)).lower()


def parse_macs(value: object) -> List[str]:
    """Parse a MAC string/list, accepting comma, semicolon and whitespace separators."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items: Iterable[object] = value
    else:
        items = re.split(r"[,;\s]+", str(value))
    result: List[str] = []
    for item in items:
        mac = normalize_mac(item)
        if mac and mac not in result:
            result.append(mac)
    return result


def _run_text(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout or ""


def _macs_from_ifconfig(output: str) -> List[str]:
    result: List[str] = []
    for line in output.splitlines():
        match = re.search(r"\bether\s+([0-9a-fA-F:]{17})\b", line)
        if match:
            mac = normalize_mac(match.group(1))
            if mac and mac not in result:
                result.append(mac)
    return result


def _macs_from_getmac(output: str) -> List[str]:
    result: List[str] = []
    for row in csv.reader(io.StringIO(output)):
        for field in row:
            mac = normalize_mac(field)
            if mac and mac not in result:
                result.append(mac)
    return result


def local_mac_addresses() -> List[str]:
    """Return physical MAC addresses visible on this machine without admin rights."""
    system = platform.system()
    result: List[str] = []
    if system == "Darwin":
        result = _macs_from_ifconfig(_run_text(["ifconfig", "-a"]))
    elif system == "Windows":
        result = _macs_from_getmac(_run_text(["getmac", "/fo", "csv", "/nh"]))
    elif system == "Linux":
        for path in Path("/sys/class/net").glob("*/address"):
            try:
                mac = normalize_mac(path.read_text(encoding="ascii").strip())
            except OSError:
                continue
            if mac and mac not in result:
                result.append(mac)
    if not result:
        node = uuid.getnode()
        if node:
            mac = normalize_mac(f"{node:012x}")
            if mac:
                result.append(mac)
    return result


def magic_packet(mac: str) -> bytes:
    normalized = normalize_mac(mac)
    if normalized is None:
        raise ValueError(f"无效的 MAC 地址：{mac!r}")
    payload = bytes.fromhex(normalized.replace(":", ""))
    return b"\xff" * 6 + payload * 16


def broadcast_targets(extra: Optional[Union[str, Sequence[str]]] = None) -> List[str]:
    targets = ["255.255.255.255"]
    if isinstance(extra, (list, tuple, set)):
        configured = [str(item).strip() for item in extra]
    else:
        configured = [part.strip() for part in re.split(r"[,;\s]+", str(extra or ""))]
    for address in configured:
        if address and address not in targets:
            targets.append(address)
    for address in local_ipv4_addresses():
        parts = address.split(".")
        if len(parts) == 4:
            subnet = ".".join(parts[:3] + ["255"])
            if subnet not in targets:
                targets.append(subnet)
    return targets


def send_magic_packet(
    macs: object,
    *,
    port: int = 9,
    broadcast: Optional[Union[str, Sequence[str]]] = None,
    host: Optional[str] = None,
) -> int:
    """Send magic packets; returns the number of UDP datagrams sent."""
    addresses = parse_macs(macs)
    if not addresses:
        return 0
    destinations = broadcast_targets(broadcast)
    host = str(host or "").strip()
    if host and host.lower() != "auto" and host not in destinations:
        destinations.append(host)

    sent = 0
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for mac in addresses:
                packet = magic_packet(mac)
                for destination in destinations:
                    try:
                        sock.sendto(packet, (destination, int(port)))
                        sent += 1
                    except OSError as exc:
                        log.debug("WoL 发送到 %s:%s 失败：%s", destination, port, exc)
    except OSError as exc:
        log.warning("无法创建 WoL UDP socket：%s", exc)
        return sent
    if sent:
        log.info("已发送 Wake-on-LAN 魔包：%s → %s", "、".join(addresses), "、".join(destinations))
    return sent
