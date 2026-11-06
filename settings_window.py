"""QuickSwitch 原生设置窗口。

主进程需要把 macOS 主线程留给 pystray，因此设置窗口在独立子进程中运行。
窗口只加载本机 QuickSwitch 控制台，不打开地址栏，也不会把令牌发到外部地址。
"""
from __future__ import annotations

import importlib.util
import contextlib
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from process_utils import windowed_subprocess_kwargs

TITLE = "QuickSwitch 设置"
WIDTH = 1120
HEIGHT = 820
MIN_SIZE = (780, 560)
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def enable_windows_high_dpi() -> bool:
    """在创建任何窗口前启用 Windows Per-Monitor DPI 感知。

    pywebview 自己只调用 ``SetProcessDPIAware``（系统级 DPI 感知）。当窗口位于
    缩放比例不同的显示器上时，Windows 会把整张窗口位图放大，WebView2 里的文字
    就会变糊。Per-Monitor V2 让窗口和 WebView2 按当前显示器的真实 DPI 渲染。
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
    except ImportError:
        return False

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_context = getattr(user32, "SetProcessDpiAwarenessContext", None)
        if set_context is not None:
            set_context.argtypes = [ctypes.c_void_p]
            set_context.restype = ctypes.c_int
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            if set_context(ctypes.c_void_p(-4)):
                return True
    except (AttributeError, OSError):
        pass

    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        set_awareness = shcore.SetProcessDpiAwareness
        set_awareness.argtypes = [ctypes.c_int]
        set_awareness.restype = ctypes.c_long
        # PROCESS_PER_MONITOR_DPI_AWARE（Windows 8.1+）
        if set_awareness(2) == 0:
            return True
    except (AttributeError, OSError):
        pass

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        return bool(user32.SetProcessDPIAware())
    except (AttributeError, OSError):
        return False


def is_local_console_url(url: str) -> bool:
    """只允许打开本机 HTTP 控制台，避免把带令牌的地址交给任意外部页面。"""
    try:
        parsed = urlparse(str(url))
    except ValueError:
        return False
    return parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS and parsed.port is not None


def webview_available() -> bool:
    try:
        return importlib.util.find_spec("webview") is not None
    except (ImportError, ValueError):
        return False


def settings_window_command(
    url: str,
    *,
    frozen: Optional[bool] = None,
    executable: Optional[str] = None,
    script: Optional[Path] = None,
) -> List[str]:
    """构造复用当前可执行文件的窗口子进程命令，兼容源码运行和 PyInstaller 包。"""
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    exe = executable or sys.executable
    if is_frozen:
        return [exe, "--settings-window", url]
    entry = script or Path(__file__).resolve().with_name("main.py")
    return [exe, str(entry), "--settings-window", url]


def run_settings_window(url: str) -> int:
    """在子进程主线程中运行 WebView；失败时回退到系统浏览器。"""
    if not is_local_console_url(url):
        print("拒绝打开非本机控制台地址", file=sys.stderr)
        return 2
    # 必须在导入 webview / 创建 WinForms 窗口之前设置，否则 Windows 已经按
    # DPI-unaware 模式创建了窗口，后续再改只会得到被系统放大的模糊画面。
    enable_windows_high_dpi()
    try:
        import webview

        webview.create_window(
            TITLE,
            url=url,
            width=WIDTH,
            height=HEIGHT,
            min_size=MIN_SIZE,
            background_color="#eef0f5",
            text_select=True,
        )
        webview.start(private_mode=True)
        return 0
    except Exception as exc:
        print(f"设置窗口启动失败，改用浏览器：{exc}", file=sys.stderr)
        with contextlib.suppress(Exception):
            webbrowser.open(url)
        return 1


class SettingsWindow:
    """管理唯一的设置窗口子进程；重复点击托盘不会叠加窗口。"""

    def __init__(self, url: str) -> None:
        self.url = url
        self._process: Optional[subprocess.Popen] = None

    def open(self) -> bool:
        if not is_local_console_url(self.url) or not webview_available():
            return False
        if self._process is not None and self._process.poll() is None:
            return True
        try:
            self._process = subprocess.Popen(
                settings_window_command(self.url),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                **windowed_subprocess_kwargs(),
            )
        except OSError:
            self._process = None
            return False
        return True

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
