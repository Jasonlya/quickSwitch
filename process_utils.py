"""子进程启动参数：在 Windows 上隐藏控制台窗口。"""
from __future__ import annotations

import platform
import subprocess
from typing import Any, Dict, Optional

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0


def silent_subprocess_kwargs(
    *, system: Optional[str] = None, detached: bool = False
) -> Dict[str, Any]:
    """返回隐藏子进程控制台的 ``subprocess`` 参数。

    QuickSwitch 是 ``console=False`` 的托盘程序，但状态轮询仍会调用
    ``tasklist``、``netstat``、DDC 工具等控制台程序。Windows 如果不显式加
    ``CREATE_NO_WINDOW``，每次调用都会闪出一个终端窗口。
    """
    system = system or platform.system()
    if system != "Windows":
        return {}

    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW))
    if detached:
        flags |= int(getattr(subprocess, "DETACHED_PROCESS", DETACHED_PROCESS))
        flags |= int(
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", CREATE_NEW_PROCESS_GROUP)
        )
    kwargs: Dict[str, Any] = {"creationflags": flags}

    startupinfo_type = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_type is not None:
        startupinfo = startupinfo_type()
        startupinfo.dwFlags |= int(
            getattr(subprocess, "STARTF_USESHOWWINDOW", STARTF_USESHOWWINDOW)
        )
        startupinfo.wShowWindow = int(getattr(subprocess, "SW_HIDE", SW_HIDE))
        kwargs["startupinfo"] = startupinfo
    return kwargs


def windowed_subprocess_kwargs(*, system: Optional[str] = None) -> Dict[str, Any]:
    """返回启动 GUI 子进程时使用的参数。

    不能复用 :func:`silent_subprocess_kwargs`：其中的 ``wShowWindow=SW_HIDE``
    会让 Windows 把子进程创建的 WebView 主窗口也隐藏，表现为设置窗口打不开。
    ``CREATE_NO_WINDOW`` 只抑制控制台，不影响 GUI 窗口。
    """
    system = system or platform.system()
    if system != "Windows":
        return {}
    return {
        "creationflags": int(
            getattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW)
        )
    }
