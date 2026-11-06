"""Deskflow 1.27 无界面核心的检测、配置和进程管理。

QuickSwitch 不再要求用户打开 Deskflow 客户端：这里根据 QuickSwitch 的 role、
peer_host 和热键生成 Deskflow 配置，启动 ``deskflow-core``，并随 QuickSwitch
退出停止它。macOS/Windows 都使用同一个无窗口核心。
"""
from __future__ import annotations

import contextlib
import logging
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from process_utils import silent_subprocess_kwargs

log = logging.getLogger("deskflow")

SERVER_NAME = "quickswitch-server"
CLIENT_NAME = "quickswitch-client"
DEFAULT_PORT = 24800

MAC_APP_CANDIDATES = (
    Path("/Applications/Deskflow.app"),
    Path.home() / "Applications" / "Deskflow.app",
)
REPO_ROOT = Path(__file__).resolve().parent
VENDOR_ROOT = REPO_ROOT / "packaging" / "vendor" / "deskflow"

# Popen 必须保留到本进程退出，否则子进程结束后可能留下僵尸进程。
_PROCESS: Optional[subprocess.Popen] = None
_PROCESS_LOCK = threading.Lock()

PRIVACY_URLS = {
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "input_monitoring": "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
    "local_network": "x-apple.systempreferences:com.apple.preference.security?Privacy_LocalNetwork",
}


class DeskflowError(RuntimeError):
    """配置或启动 Deskflow 核心失败。"""


@dataclass(frozen=True)
class PreparedDeskflow:
    mode: str
    core_path: str
    settings_path: Path
    server_config_path: Optional[Path]
    log_path: Path
    pid_path: Path
    port: int
    remote_host: str


def _section(cfg: Dict[str, Any]) -> Dict[str, Any]:
    section = cfg.get("deskflow") or {}
    return section if isinstance(section, dict) else {}


def _role(cfg: Dict[str, Any], system: str) -> str:
    role = str(cfg.get("role") or "").lower()
    if role in ("client", "server"):
        return role
    return "client" if system == "Darwin" else "server"


def _candidate_roots() -> Tuple[Path, ...]:
    roots = []
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        value = os.environ.get(key)
        if value:
            roots.append(Path(value))
    return tuple(roots)


def _bundle_roots(system: str) -> Tuple[Path, ...]:
    """QuickSwitch 安装包内放置 Deskflow 的候选目录。"""
    roots = []
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        if system == "Darwin":
            contents = executable.parent.parent
            roots.extend((contents / "Resources" / "deskflow", contents / "Frameworks" / "deskflow"))
        else:
            roots.append(executable.parent / "deskflow")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.extend((Path(meipass) / "deskflow", Path(meipass).parent / "Resources" / "deskflow"))

    roots.append(VENDOR_ROOT)
    seen = set()
    result = []
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            result.append(root)
    return tuple(result)


def _core_candidates(root: Path, system: str) -> Tuple[Path, ...]:
    if system == "Darwin":
        apps = (root / "Deskflow.app", root / "macos-arm64" / "Deskflow.app")
        return tuple(app / "Contents" / "MacOS" / "deskflow-core" for app in apps)
    if system == "Windows":
        return (
            root / "deskflow-core.exe",
            root / "Deskflow-core.exe",
            root / "windows-x64" / "deskflow-core.exe",
            root / "win-x64" / "deskflow-core.exe",
        )
    return (root / "deskflow-core", root / "bin" / "deskflow-core")


def bundled_deskflow_core_path(*, system: Optional[str] = None) -> Optional[str]:
    """返回 QuickSwitch 安装包内自带的 deskflow-core。"""
    system = system or platform.system()
    for root in _bundle_roots(system):
        for candidate in _core_candidates(root, system):
            if candidate.is_file():
                return str(candidate)
    return None


def bundled_deskflow_path(*, system: Optional[str] = None) -> Optional[str]:
    """兼容旧调用名；现在返回无界面核心路径。"""
    return bundled_deskflow_core_path(system=system)


def is_bundled_path(path: str, *, system: Optional[str] = None) -> bool:
    bundled = bundled_deskflow_core_path(system=system)
    if not bundled:
        return False
    try:
        return Path(path).resolve() == Path(bundled).resolve()
    except OSError:
        return str(path) == bundled


def _core_from_configured(path: Path, system: str) -> Optional[Path]:
    if path.is_file():
        if path.name.lower() in ("deskflow-core", "deskflow-core.exe"):
            return path
        sibling = path.parent / ("deskflow-core.exe" if system == "Windows" else "deskflow-core")
        if sibling.is_file():
            return sibling
        return None
    if path.is_dir():
        if path.suffix == ".app":
            candidate = path / "Contents" / "MacOS" / "deskflow-core"
            if candidate.is_file():
                return candidate
        for candidate in _core_candidates(path, system):
            if candidate.is_file():
                return candidate
        for nested in (path / "Deskflow.app", path / "macos-arm64" / "Deskflow.app"):
            candidate = nested / "Contents" / "MacOS" / "deskflow-core"
            if candidate.is_file():
                return candidate
    return None


def _resolve_configured(configured: str, system: str) -> Optional[str]:
    expanded = Path(os.path.expandvars(configured)).expanduser()
    found = _core_from_configured(expanded, system)
    if found:
        return str(found)
    if not expanded.exists():
        command = shutil.which(configured)
        if command:
            found = _core_from_configured(Path(command), system)
            if found:
                return str(found)
        if system == "Darwin" and not configured.endswith(".app"):
            for candidate in (
                Path("/Applications") / f"{configured}.app",
                Path.home() / "Applications" / f"{configured}.app",
            ):
                found = _core_from_configured(candidate, system)
                if found:
                    return str(found)
    return None


def locate_deskflow_core(cfg: Dict[str, Any], *, system: Optional[str] = None) -> Optional[str]:
    """按“显式配置 > 安装包内置 > 用户安装 > PATH”查找 deskflow-core。"""
    system = system or platform.system()
    configured = str(_section(cfg).get("path") or "").strip()
    if configured:
        return _resolve_configured(configured, system)

    bundled = bundled_deskflow_core_path(system=system)
    if bundled:
        return bundled

    if system == "Darwin":
        for app in MAC_APP_CANDIDATES:
            found = _core_from_configured(app, system)
            if found:
                return str(found)
        return shutil.which("deskflow-core")

    if system == "Windows":
        for root in _candidate_roots():
            for subdir in (root / "Deskflow", root / "Programs" / "Deskflow"):
                for candidate in _core_candidates(subdir, system):
                    if candidate.is_file():
                        return str(candidate)
        return shutil.which("deskflow-core.exe")

    return shutil.which("deskflow-core")


def locate_deskflow(cfg: Dict[str, Any], *, system: Optional[str] = None) -> Optional[str]:
    """兼容旧接口：返回 QuickSwitch 管理的 Deskflow 核心。"""
    return locate_deskflow_core(cfg, system=system)


def _run_text(
    command: list[str], *, timeout: float = 3.0, system: Optional[str] = None
) -> Tuple[int, str]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        **silent_subprocess_kwargs(system=system),
    )
    return int(completed.returncode), (completed.stdout or "") + (completed.stderr or "")


def is_running(*, system: Optional[str] = None) -> bool:
    """只检测无界面核心，不把 Deskflow 图形客户端误判为已运行。"""
    system = system or platform.system()
    global _PROCESS
    try:
        with _PROCESS_LOCK:
            if _PROCESS is not None:
                if _PROCESS.poll() is None:
                    return True
                _PROCESS = None
        if system == "Windows":
            code, output = _run_text(
                ["tasklist", "/FI", "IMAGENAME eq deskflow-core.exe", "/NH"],
                system=system,
            )
            return code == 0 and "deskflow-core.exe" in output.lower()
        code, _ = _run_text(["pgrep", "-x", "deskflow-core"], system=system)
        return code == 0
    except (OSError, subprocess.SubprocessError):
        return False


def read_pid(*, state_dir: Optional[Path] = None) -> Optional[int]:
    """读取 QuickSwitch 上次启动的核心 PID。"""
    directory = Path(state_dir).expanduser() if state_dir is not None else _state_dir({}, None)
    try:
        return int((directory / "deskflow.pid").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_is_core(pid: int, *, system: str) -> bool:
    """避免 PID 被系统复用后误把别的进程当成 Deskflow。"""
    if not _pid_alive(pid, system=system):
        return False
    try:
        if system == "Windows":
            code, output = _run_text(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"], system=system
            )
            return code == 0 and "deskflow-core" in output.lower()
        code, output = _run_text(
            ["ps", "-p", str(pid), "-o", "comm="], system=system
        )
        return code == 0 and "deskflow-core" in output.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def managed_pid(*, system: Optional[str] = None, state_dir: Optional[Path] = None) -> Optional[int]:
    """返回由 QuickSwitch 启动且仍存活的核心 PID；不把外部进程误认成自己的。"""
    system = system or platform.system()
    pid = read_pid(state_dir=state_dir)
    if pid is None:
        return None
    with _PROCESS_LOCK:
        if _PROCESS is not None and _PROCESS.pid == pid:
            return pid if _PROCESS.poll() is None else None
    return pid if _pid_is_core(pid, system=system) else None


def macos_accessibility_trusted() -> Optional[bool]:
    """查询当前进程的 macOS 辅助功能授权；非 macOS 或查询失败时返回 None。"""
    if platform.system() != "Darwin":
        return None
    try:
        import ctypes
        import ctypes.util

        services = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("ApplicationServices") or "ApplicationServices"
        )
        services.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(services.AXIsProcessTrusted())
    except Exception as exc:
        log.debug("读取 macOS 辅助功能权限失败：%s", exc)
        return None


def prompt_macos_accessibility() -> Optional[bool]:
    """打开系统「辅助功能」授权页；用户授权后仍需重启核心。"""
    if platform.system() != "Darwin":
        return None
    trusted = macos_accessibility_trusted()
    if trusted is False:
        open_macos_privacy_settings("accessibility")
    return trusted


def open_macos_privacy_settings(kind: str = "accessibility") -> bool:
    """打开对应的 macOS 隐私设置页；只接受白名单，避免任意 URL 注入。"""
    if platform.system() != "Darwin":
        return False
    url = PRIVACY_URLS.get(str(kind).strip())
    if not url:
        return False
    try:
        subprocess.Popen(
            ["open", url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            **silent_subprocess_kwargs(),
        )
        return True
    except OSError as exc:
        log.warning("打开 macOS 隐私设置失败：%s", exc)
        return False


def _state_dir(cfg: Dict[str, Any], base_dir: Optional[Path]) -> Path:
    if base_dir is not None:
        return Path(base_dir).expanduser()
    env_path = os.environ.get("QUICKSWITCH_CONFIG", "").strip()
    if env_path:
        return Path(env_path).expanduser().parent / "deskflow"
    return Path.home() / ".quickswitch" / "deskflow"


def _hotkey_to_deskflow(combo: Any) -> Optional[str]:
    """把 QuickSwitch/keyboard 风格热键转成 Deskflow 的 keystroke() 语法。"""
    text = str(combo or "").strip().lower()
    if not text:
        return None
    parts = [part.strip() for part in text.split("+") if part.strip()]
    if not parts:
        return None

    modifiers = []
    aliases = {
        "ctrl": "control",
        "control": "control",
        "alt": "alt",
        "option": "alt",
        "shift": "shift",
        "cmd": "super",
        "command": "super",
        "win": "super",
        "windows": "super",
        "meta": "super",
        "super": "super",
    }
    for part in parts[:-1]:
        modifier = aliases.get(part)
        if not modifier:
            return None
        if modifier not in modifiers:
            modifiers.append(modifier)

    key = parts[-1]
    key_aliases = {
        "esc": "escape",
        "enter": "return",
        "del": "delete",
        "ins": "insert",
        "pgup": "pageup",
        "pgdn": "pagedown",
        "arrowleft": "left",
        "arrowright": "right",
        "arrowup": "up",
        "arrowdown": "down",
    }
    key = key_aliases.get(key, key)
    if not (len(key) == 1 and key.isalnum()) and not re.fullmatch(r"f(?:[1-9]|1[0-2])", key):
        if key not in {
            "space", "tab", "return", "escape", "backspace", "delete", "insert",
            "home", "end", "pageup", "pagedown", "left", "right", "up", "down",
        }:
            return None
    return "+".join([*modifiers, key])


def render_server_config(cfg: Dict[str, Any]) -> str:
    """生成只有两台机器的 Deskflow server 配置，并复用 QuickSwitch 热键。"""
    side = str(_section(cfg).get("mac_side") or "left")
    # mac_side 描述 Mac 相对 Windows 的位置：Mac 在左侧时，Windows 的左边就是客户端。
    server_side, client_side = ("left", "right") if side == "left" else ("right", "left")
    hotkeys = cfg.get("hotkeys") or {}
    to_mac = _hotkey_to_deskflow(hotkeys.get("switch_to_mac"))
    to_win = _hotkey_to_deskflow(hotkeys.get("switch_to_win"))

    lines = [
        "section: links",
        f"    {SERVER_NAME}:",
        f"        {server_side} = {CLIENT_NAME}",
        f"    {CLIENT_NAME}:",
        f"        {client_side} = {SERVER_NAME}",
        "end",
        "",
        "section: options",
    ]
    if to_mac:
        lines.append(f"    keystroke({to_mac}) = switchToScreen({CLIENT_NAME})")
    if to_win:
        lines.append(f"    keystroke({to_win}) = switchToScreen({SERVER_NAME})")
    lines.extend(("end", ""))
    return "\n".join(lines)


def render_settings(cfg: Dict[str, Any], prepared: PreparedDeskflow) -> str:
    computer_name = SERVER_NAME if prepared.mode == "server" else CLIENT_NAME
    lines = [
        "[core]",
        f"computerName={computer_name}",
        f"port={prepared.port}",
        f"coreMode={'2' if prepared.mode == 'server' else '1'}",
        "useHooks=true",
        "",
        "[security]",
        "tlsEnabled=false",
        "",
        "[log]",
        "level=INFO",
        "toFile=false",
        "",
        f"[computer_{SERVER_NAME}]",
        f"name={SERVER_NAME}",
        "",
        f"[computer_{CLIENT_NAME}]",
        f"name={CLIENT_NAME}",
        "",
    ]
    if prepared.mode == "server":
        # Deskflow 的 INI 解析器会把反斜杠当作转义符；Windows 路径必须用正斜杠。
        external_config = str(prepared.server_config_path).replace("\\", "/")
        lines.extend((
            "[server]",
            "externalConfig=true",
            f"externalConfigFile={external_config}",
            "enableClipboard=true",
            "",
        ))
    else:
        language_sync = bool(_section(cfg).get("language_sync", False))
        lines.extend((
            "[client]",
            f"remoteHost={prepared.remote_host}",
            f"languageSync={'true' if language_sync else 'false'}",
            "",
        ))
    return "\n".join(lines)


def prepare(
    cfg: Dict[str, Any],
    *,
    system: Optional[str] = None,
    state_dir: Optional[Path] = None,
    peer_host: Optional[str] = None,
) -> PreparedDeskflow:
    """写出 QuickSwitch 管理的 Deskflow 配置，返回可直接启动的路径。"""
    system = system or platform.system()
    mode = _role(cfg, system)
    core = locate_deskflow_core(cfg, system=system)
    if not core:
        raise DeskflowError("找不到内置 Deskflow 核心；请重新安装 QuickSwitch，或在 deskflow.path 指定 Deskflow.app")

    section = _section(cfg)
    port = int(section.get("port", DEFAULT_PORT))
    directory = _state_dir(cfg, state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    settings_path = directory / "Deskflow.conf"
    server_config_path = directory / "Deskflow-server.conf" if mode == "server" else None
    prepared = PreparedDeskflow(
        mode=mode,
        core_path=core,
        settings_path=settings_path,
        server_config_path=server_config_path,
        log_path=directory / "deskflow.log",
        pid_path=directory / "deskflow.pid",
        port=port,
        remote_host=str(peer_host or cfg.get("peer_host") or "").strip(),
    )
    if mode == "client" and (not prepared.remote_host or prepared.remote_host.lower() == "auto"):
        raise DeskflowError("client 模式需要已知的 Windows 地址；请把 peer_host 设为具体 IP，或等待自动发现")

    if server_config_path is not None:
        server_config_path.write_text(render_server_config(cfg), encoding="utf-8")
    settings_path.write_text(render_settings(cfg, prepared), encoding="utf-8")
    return prepared


def _append_launch_banner(path: Path, prepared: PreparedDeskflow) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with path.open("ab") as handle:
        handle.write(
            f"\n===== QuickSwitch {stamp} 启动 deskflow-core ({prepared.mode}) =====\n".encode("utf-8")
        )


def _launch(prepared: PreparedDeskflow, *, system: str) -> subprocess.Popen:
    core = Path(prepared.core_path)
    _append_launch_banner(prepared.log_path, prepared)
    env = os.environ.copy()
    if system == "Darwin":
        env.setdefault("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM", "1")
    with prepared.log_path.open("ab") as output:
        kwargs: Dict[str, Any] = {
            "cwd": str(core.parent),
            "stdin": subprocess.DEVNULL,
            "stdout": output,
            "stderr": subprocess.STDOUT,
            "env": env,
            "close_fds": True,
        }
        if system == "Windows":
            kwargs.update(silent_subprocess_kwargs(system=system, detached=True))
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(
            [prepared.core_path, prepared.mode, "--settings", str(prepared.settings_path), "--new-instance"],
            **kwargs,  # type: ignore[arg-type]
        )
    global _PROCESS
    with _PROCESS_LOCK:
        _PROCESS = process
    prepared.pid_path.write_text(f"{process.pid}\n", encoding="utf-8")
    return process


def log_tail(path: Path, *, lines: int = 12, limit: int = 900) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    return "\n".join(rows[-lines:])[-limit:]


_LAUNCH_BANNER_RE = re.compile(
    r"^===== QuickSwitch .*? 启动 deskflow-core .*=====\s*$", re.MULTILINE
)
_LOG_PREFIX_RE = re.compile(
    r"^\[[^\]]+\]\s*(?:TRACE|DEBUG|INFO|WARNING|ERROR|FATAL):\s*", re.IGNORECASE
)
_PERMISSION_MARKERS = (
    "assistive devices does not trust this process",
    "process is not trusted anymore",
    "failed to create quartz event tap",
    "not authorized to capture",
    "input monitoring permission",
)


def _log_since_launch(path: Path, *, max_bytes: int = 128 * 1024) -> str:
    """读取本次核心启动后的日志，避免旧连接状态覆盖当前结果。"""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            data = handle.read()
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace")
    matches = list(_LAUNCH_BANNER_RE.finditer(text))
    if matches:
        text = text[matches[-1].end():]
    return text.strip()


def _log_message(line: str) -> str:
    return _LOG_PREFIX_RE.sub("", line.strip())


def inspect_connection_log(text: str, *, mode: str) -> Dict[str, Any]:
    """从本次 Deskflow 日志提取连接状态和最近一次连接错误。"""
    state = "waiting_peer"
    last_error = ""
    for raw_line in (text or "").splitlines():
        message = _log_message(raw_line)
        if not message:
            continue
        lower = message.lower()

        if mode == "client":
            if "connected to server" in lower:
                state = "connected"
            elif "failed to connect to server" in lower:
                state = "error"
                last_error = message.rsplit(": ", 1)[-1].strip() or message
            elif "disconnected from server" in lower:
                state = "waiting_peer"
            elif "started client" in lower or "starting client" in lower:
                state = "connecting"
        else:
            if re.search(r'client "[^"]+" has connected', message, re.IGNORECASE):
                state = "connected"
            elif re.search(r'client "[^"]+" has disconnected', message, re.IGNORECASE):
                state = "waiting_peer"
            elif "accepted client connection" in lower or "starting server" in lower:
                state = "connecting"
            elif "started server, waiting for clients" in lower:
                state = "waiting_peer"
            elif "cannot listen for clients" in lower or "failed to start server" in lower:
                state = "error"
                last_error = message.rsplit(": ", 1)[-1].strip() or message

    return {"state": state, "last_error": last_error}


def _endpoint_port(endpoint: str) -> Optional[int]:
    match = re.search(r":(\d+)$", endpoint.strip())
    return int(match.group(1)) if match else None


def parse_established_connections(
    output: str,
    *,
    system: str,
    pid: Optional[int] = None,
    port: int = DEFAULT_PORT,
) -> int:
    """解析 ``netstat`` / ``lsof`` 输出中的已建立连接数。"""
    connections = set()
    for line in (output or "").splitlines():
        stripped = line.strip()
        if not stripped or "ESTABLISHED" not in stripped.upper():
            continue

        if system == "Windows":
            parts = stripped.split()
            if len(parts) < 5 or parts[0].upper() != "TCP":
                continue
            local, remote, state, owner = parts[1], parts[2], parts[3], parts[4]
            if state.upper() != "ESTABLISHED":
                continue
            try:
                owner_pid: Optional[int] = int(owner)
            except ValueError:
                owner_pid = None
            if pid is not None and owner_pid != pid:
                continue
            if _endpoint_port(local) != port and _endpoint_port(remote) != port:
                continue
            connections.add((local, remote, owner_pid))
            continue

        parts = stripped.split()
        try:
            owner_pid = int(parts[1])
        except (IndexError, ValueError):
            continue
        if pid is not None and owner_pid != pid:
            continue
        if pid is None and "deskflow" not in parts[0].lower():
            continue
        try:
            tcp_index = [part.upper() for part in parts].index("TCP")
            endpoints = parts[tcp_index + 1]
            local, remote = endpoints.split("->", 1)
        except (ValueError, IndexError):
            continue
        if _endpoint_port(local) != port and _endpoint_port(remote) != port:
            continue
        connections.add((local, remote, owner_pid))
    return len(connections)


def _active_connection_count(
    *, system: str, pid: Optional[int], port: int
) -> Optional[int]:
    try:
        if system == "Windows":
            code, output = _run_text(
                ["netstat", "-ano", "-p", "tcp"], timeout=2.5, system=system
            )
            if code != 0:
                return None
            return parse_established_connections(
                output, system=system, pid=pid, port=port
            )

        command = ["lsof", "-nP"]
        if pid is not None:
            command.extend(["-a", "-p", str(pid)])
        command.extend([f"-iTCP:{port}", "-sTCP:ESTABLISHED"])
        code, output = _run_text(command, timeout=2.5, system=system)
        if code not in (0, 1) and not output:
            return None
        return parse_established_connections(
            output, system=system, pid=pid, port=port
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _permission_error(text: str) -> bool:
    lower = (text or "").lower()
    return any(marker in lower for marker in _PERMISSION_MARKERS)


def _friendly_connection_error(reason: str, *, port: int) -> str:
    message = (reason or "").strip().strip('"')
    lower = message.lower()
    if "timed out" in lower or "timeout" in lower:
        return f"连接超时；请确认对端 QuickSwitch 正在运行，并允许 TCP {port}"
    if "connection refused" in lower:
        return f"对端拒绝连接；请确认服务端已启动并监听 TCP {port}"
    if "not trusted" in lower or "quartz event tap" in lower or "assistive" in lower:
        return "macOS 未授予辅助功能或输入监控权限"
    if "unrecognised client" in lower:
        return "对端不认识本机名称；请重启两端 QuickSwitch 后重试"
    if "already has a connected client" in lower:
        return "对端已有同名客户端连接；请关闭另一台正在使用的 QuickSwitch"
    return message or "未知连接错误"


def _connection_summary(
    mode: str, state: str, *, peer_host: str, port: int, error: str
) -> str:
    if state == "missing":
        return "键鼠共享不可用：安装包缺少内置 Deskflow 核心"
    if state == "permission_required":
        return "键鼠共享未工作：macOS 未授予辅助功能或输入监控权限"
    if state == "stopped":
        return "键鼠共享已停止"
    if state == "unmanaged":
        return "键鼠共享异常：检测到非 QuickSwitch 管理的核心"
    if state == "connected":
        if mode == "server":
            return "已连接：Windows 键鼠可以移到 Mac 上使用"
        return "已连接：Windows 键鼠已经可以控制这台 Mac"
    if state == "connecting":
        return "核心已启动，正在建立连接"
    if state == "error":
        action = "连接 Windows" if mode == "client" else "等待 Mac 连接"
        return f"{action}失败：{error}"
    if mode == "server":
        return "服务已就绪，等待 Mac 连接"
    target = peer_host or "Windows"
    return f"客户端运行中，正在尝试连接 {target}:{port}"


def start(
    cfg: Dict[str, Any],
    *,
    system: Optional[str] = None,
    state_dir: Optional[Path] = None,
    peer_host: Optional[str] = None,
    startup_wait: float = 0.8,
) -> Tuple[bool, str]:
    """生成配置并启动无界面核心；已由 QuickSwitch 启动时直接返回成功。"""
    global _PROCESS
    system = system or platform.system()
    directory = _state_dir(cfg, state_dir)
    ours = managed_pid(system=system, state_dir=directory)
    if ours is not None:
        return True, "键鼠共享核心已在运行"
    if is_running(system=system):
        return False, "检测到另一个 deskflow-core 正在运行；请退出旧的 QuickSwitch 或 Deskflow 后重试"
    try:
        prepared = prepare(cfg, system=system, state_dir=directory, peer_host=peer_host)
    except (DeskflowError, OSError, ValueError) as exc:
        return False, str(exc)

    try:
        process = _launch(prepared, system=system)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("启动 deskflow-core 失败：%s", exc)
        return False, f"启动键鼠共享失败：{exc}"

    exit_code = process.poll()
    if exit_code is not None:
        prepared.pid_path.unlink(missing_ok=True)
        with _PROCESS_LOCK:
            if _PROCESS is process:
                _PROCESS = None
        detail = log_tail(prepared.log_path)
        message = f"键鼠共享核心启动后退出（退出码 {exit_code}）"
        if detail:
            message += f"：{detail}"
        return False, message

    deadline = time.monotonic() + startup_wait
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            prepared.pid_path.unlink(missing_ok=True)
            with _PROCESS_LOCK:
                if _PROCESS is process:
                    _PROCESS = None
            detail = log_tail(prepared.log_path)
            message = f"键鼠共享核心启动后退出（退出码 {exit_code}）"
            if detail:
                message += f"：{detail}"
            return False, message
        time.sleep(0.1)

    return True, f"已启动键鼠共享核心（{prepared.mode}，端口 {prepared.port}）"


def _pid_alive(pid: int, *, system: str) -> bool:
    try:
        if system == "Windows":
            code, output = _run_text(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"], system=system
            )
            return code == 0 and str(pid) in output
        os.kill(pid, 0)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def stop(
    cfg: Dict[str, Any],
    *,
    system: Optional[str] = None,
    state_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """停止由 QuickSwitch 写入 PID 文件的核心进程。"""
    system = system or platform.system()
    directory = _state_dir(cfg, state_dir)
    pid_path = directory / "deskflow.pid"
    pid = managed_pid(system=system, state_dir=directory)
    if pid is None:
        pid_path.unlink(missing_ok=True)
        if is_running(system=system):
            return False, "检测到非 QuickSwitch 管理的 deskflow-core，未自动结束它"
        return True, "没有正在运行的键鼠共享核心"

    try:
        if system == "Windows":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=8,
                **silent_subprocess_kwargs(system=system),
            )
        else:
            os.kill(pid, signal.SIGTERM)
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if not _pid_alive(pid, system=system):
                    break
                time.sleep(0.1)
            if _pid_alive(pid, system=system):
                os.kill(pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"停止键鼠共享失败：{exc}"
    finally:
        pid_path.unlink(missing_ok=True)
    global _PROCESS
    with _PROCESS_LOCK:
        if _PROCESS is not None and _PROCESS.pid == pid:
            with contextlib.suppress(Exception):
                _PROCESS.wait(timeout=1.0)
            _PROCESS = None
    return True, "已停止键鼠共享核心"


def restart(
    cfg: Dict[str, Any],
    *,
    system: Optional[str] = None,
    state_dir: Optional[Path] = None,
    peer_host: Optional[str] = None,
    startup_wait: float = 0.8,
) -> Tuple[bool, str]:
    """按当前配置重启无界面核心；配置或热键改动后调用。"""
    stopped, stop_detail = stop(cfg, system=system, state_dir=state_dir)
    if not stopped:
        return False, stop_detail
    return start(
        cfg,
        system=system,
        state_dir=state_dir,
        peer_host=peer_host,
        startup_wait=startup_wait,
    )


def snapshot(
    cfg: Dict[str, Any],
    *,
    system: Optional[str] = None,
    state_dir: Optional[Path] = None,
    peer_host: Optional[str] = None,
) -> Dict[str, Any]:
    """生成供日志和设置页展示的 Deskflow 核心快照。"""
    system = system or platform.system()
    section = _section(cfg)
    mode = _role(cfg, system)
    path = locate_deskflow_core(cfg, system=system)
    directory = _state_dir(cfg, state_dir)
    log_path = directory / "deskflow.log"
    pid = managed_pid(system=system, state_dir=directory)
    managed = pid is not None
    running = managed or is_running(system=system)
    port = int(section.get("port", DEFAULT_PORT))
    peer_host = str(peer_host or cfg.get("peer_host") or "")
    session_log = _log_since_launch(log_path)
    last_log = log_tail(log_path, lines=20, limit=3000)
    log_state = inspect_connection_log(session_log, mode=mode)
    accessibility = macos_accessibility_trusted() if system == "Darwin" else None
    permission_required = system == "Darwin" and _permission_error(session_log)
    active_connections = (
        _active_connection_count(system=system, pid=pid, port=port) if running else 0
    )
    connected = bool(
        running
        and not permission_required
        and (
            (active_connections is not None and active_connections > 0)
            or log_state["state"] == "connected"
        )
    )
    last_error = ""
    if permission_required:
        connection_state = "permission_required"
        last_error = "macOS 未授予辅助功能或输入监控权限"
    elif not path:
        connection_state = "missing"
    elif not running:
        connection_state = "stopped"
    elif not managed:
        connection_state = "unmanaged"
    elif connected:
        connection_state = "connected"
    elif log_state["state"] == "error":
        connection_state = "error"
        last_error = _friendly_connection_error(
            str(log_state.get("last_error") or ""), port=port
        )
    elif log_state["state"] == "connecting":
        connection_state = "connecting"
    else:
        connection_state = "waiting_peer"

    summary = _connection_summary(
        mode,
        connection_state,
        peer_host=peer_host,
        port=port,
        error=last_error,
    )
    if connection_state == "unmanaged":
        last_error = "检测到非 QuickSwitch 管理的 deskflow-core"
    if connection_state == "stopped" and not bool(section.get("auto_start", True)):
        summary = "键鼠共享已停止（自动启动已关闭）"
    if connection_state == "permission_required" and active_connections:
        summary = "已连上 Windows，但 macOS 尚未授权键盘和鼠标控制"

    return {
        "auto_start": bool(section.get("auto_start", True)),
        "mode": mode,
        "language_sync": bool(section.get("language_sync", False)),
        "path": path or "",
        "installed": bool(path),
        "running": running,
        "system": system,
        "bundled": bool(path and is_bundled_path(path, system=system)),
        "managed": managed,
        "tls": False,
        "port": port,
        "peer_host": peer_host,
        "connected": connected,
        "connection_state": connection_state,
        "active_connections": active_connections,
        "summary": summary,
        "last_error": last_error,
        "config_path": str(directory / "Deskflow.conf"),
        "server_config_path": (
            str(directory / "Deskflow-server.conf") if mode == "server" else ""
        ),
        "log_path": str(log_path),
        "last_log": last_log,
        "accessibility": accessibility,
        "permission_required": permission_required,
        "detail": summary,
    }
