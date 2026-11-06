"""Windows 原生 DDC/CI 后端（DXVA2）。

ControlMyMonitor 需要用户额外下载，安装包不携带时 Windows 端就无法读取输入源。
这里直接调用系统 ``dxva2.dll`` 的 VCP 0x60 接口：目标机不需要安装额外程序。

模块本身可以在 macOS/Linux 上导入；只有真正调用 ``available()`` / ``get_input()``
/ ``set_input()`` 时才会加载 Windows DLL，便于在非 Windows 环境运行单元测试。
"""
from __future__ import annotations

import contextlib
import ctypes
import logging
import sys
from ctypes import wintypes
from typing import Iterator, List, Optional, Tuple

log = logging.getLogger("ddc.windows")

VCP_INPUT = 0x60
PHYSICAL_MONITOR_DESCRIPTION_SIZE = 128


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [
        ("hPhysicalMonitor", wintypes.HANDLE),
        ("szPhysicalMonitorDescription", wintypes.WCHAR * PHYSICAL_MONITOR_DESCRIPTION_SIZE),
    ]


_FUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
MONITORENUMPROC = _FUNCTYPE(
    wintypes.BOOL,
    wintypes.HMONITOR,
    wintypes.HDC,
    ctypes.POINTER(RECT),
    ctypes.c_ssize_t,
)


def _load_api():
    """加载并声明 user32 / dxva2 的函数签名。只应在 Windows 上调用。"""
    if sys.platform != "win32":
        raise OSError("Windows 原生 DDC 只能在 Windows 上使用")

    win_dll = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        raise OSError("当前 Python 不支持 WinDLL")
    user32 = win_dll("user32", use_last_error=True)
    dxva2 = win_dll("dxva2", use_last_error=True)

    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(RECT),
        MONITORENUMPROC,
        ctypes.c_ssize_t,
    ]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL

    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [
        wintypes.HMONITOR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
        wintypes.HMONITOR,
        wintypes.DWORD,
        ctypes.POINTER(PHYSICAL_MONITOR),
    ]
    dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
    dxva2.DestroyPhysicalMonitors.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(PHYSICAL_MONITOR),
    ]
    dxva2.DestroyPhysicalMonitors.restype = wintypes.BOOL
    dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
        wintypes.HANDLE,
        ctypes.c_ubyte,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    dxva2.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL
    dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, ctypes.c_ubyte, wintypes.DWORD]
    dxva2.SetVCPFeature.restype = wintypes.BOOL
    return user32, dxva2


class WindowsNativeDDC:
    """用 DXVA2 枚举物理显示器并读写 VCP 0x60。"""

    def __init__(self, display_index: int = 1, *, api=None) -> None:
        self.display_index = max(1, int(display_index))
        self._api_override = api

    def _api(self):
        return self._api_override or _load_api()

    @contextlib.contextmanager
    def _physical_monitors(self) -> Iterator[List[Tuple[int, int, str]]]:
        user32, dxva2 = self._api()
        groups: List[Tuple[object, int]] = []

        def callback(hmonitor, _hdc, _rect, _data):
            count = wintypes.DWORD()
            if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmonitor, ctypes.byref(count)):
                return True
            if count.value == 0:
                return True
            monitors = (PHYSICAL_MONITOR * count.value)()
            if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmonitor, count.value, monitors):
                return True
            groups.append((monitors, count.value))
            return True

        monitor_callback = MONITORENUMPROC(callback)
        if not user32.EnumDisplayMonitors(None, None, monitor_callback, 0):
            raise OSError("枚举显示器失败")

        entries: List[Tuple[int, int, str]] = []
        index = 1
        for monitors, count in groups:
            for offset in range(count):
                item = monitors[offset]  # type: ignore[index]
                description = str(item.szPhysicalMonitorDescription).split("\x00", 1)[0]
                entries.append((index, int(item.hPhysicalMonitor or 0), description))
                index += 1
        try:
            yield entries
        finally:
            for monitors, count in groups:
                with contextlib.suppress(Exception):
                    dxva2.DestroyPhysicalMonitors(count, monitors)

    def monitors(self) -> List[Tuple[int, int, str]]:
        """返回 ``(序号, 物理显示器句柄, 描述)``；句柄只在返回前有效，供状态展示用。"""
        try:
            with self._physical_monitors() as entries:
                return list(entries)
        except OSError as exc:
            log.debug("Windows 原生 DDC 不可用：%s", exc)
            return []

    def available(self) -> bool:
        return bool(self.monitors())

    def status(self) -> Tuple[bool, str]:
        entries = self.monitors()
        if entries:
            names = "、".join(item[2] for item in entries)
            return True, f"Windows 原生 DDC（DXVA2）已检测到 {len(entries)} 个显示器：{names}"
        return False, "Windows 原生 DDC（DXVA2）未检测到可用显示器"

    def _target(self, entries: List[Tuple[int, int, str]]) -> Optional[int]:
        if not entries:
            return None
        for index, handle, _description in entries:
            if index == self.display_index:
                return handle
        return entries[0][1]

    def get_input(self) -> Optional[int]:
        try:
            _user32, dxva2 = self._api()
            with self._physical_monitors() as entries:
                handle = self._target(entries)
                if not handle:
                    return None
                code = wintypes.DWORD()
                current = wintypes.DWORD()
                maximum = wintypes.DWORD()
                ok = dxva2.GetVCPFeatureAndVCPFeatureReply(
                    handle,
                    VCP_INPUT,
                    ctypes.byref(code),
                    ctypes.byref(current),
                    ctypes.byref(maximum),
                )
                return int(current.value) if ok else None
        except OSError as exc:
            log.debug("Windows 原生 DDC 读取失败：%s", exc)
            return None

    def set_input(self, value: int) -> bool:
        try:
            _user32, dxva2 = self._api()
            with self._physical_monitors() as entries:
                handle = self._target(entries)
                if not handle:
                    return False
                return bool(dxva2.SetVCPFeature(handle, VCP_INPUT, int(value)))
        except OSError as exc:
            log.debug("Windows 原生 DDC 写入失败：%s", exc)
            return False
