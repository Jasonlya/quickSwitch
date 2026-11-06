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
import time
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
        self.last_error = ""
        self.last_success = ""

    def _api(self):
        return self._api_override or _load_api()

    @contextlib.contextmanager
    def _physical_monitors(self) -> Iterator[List[Tuple[int, int, str]]]:
        user32, dxva2 = self._api()
        groups: List[Tuple[object, int]] = []
        errors: List[str] = []
        self.last_error = ""

        def fail(action: str) -> None:
            errors.append(self._win_error(action))

        def callback(hmonitor, _hdc, _rect, _data):
            count = wintypes.DWORD()
            if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmonitor, ctypes.byref(count)):
                fail("读取物理显示器数量")
                return True
            if count.value == 0:
                return True
            monitors = (PHYSICAL_MONITOR * count.value)()
            if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmonitor, count.value, monitors):
                fail("获取物理显示器句柄")
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
        if errors:
            self.last_error = "；".join(errors)

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
        detail = "Windows 原生 DDC（DXVA2）未检测到可用显示器"
        if self.last_error:
            detail += f"（{self.last_error}）"
        return False, detail

    def _ordered_targets(
        self, entries: List[Tuple[int, int, str]]
    ) -> List[Tuple[int, int, str]]:
        """优先使用配置的 display_index，失败后继续尝试其它物理显示器。"""
        selected = [item for item in entries if item[0] == self.display_index]
        others = [item for item in entries if item[0] != self.display_index]
        return selected + others

    def _win_error(self, action: str) -> str:
        getter = getattr(ctypes, "get_last_error", None)
        code = int(getter() or 0) if callable(getter) else 0
        if not code:
            return f"{action} 失败（Windows 未返回错误码）"
        formatter = getattr(ctypes, "FormatError", None)
        message = ""
        if callable(formatter):
            with contextlib.suppress(Exception):
                message = str(formatter(code)).strip()
        suffix = f"：{message}" if message else ""
        return f"{action} 失败（WinError {code}{suffix}）"

    def get_input(self) -> Optional[int]:
        errors: List[str] = []
        try:
            _user32, dxva2 = self._api()
            with self._physical_monitors() as entries:
                if not entries:
                    self.last_error = self.last_error or "未枚举到物理显示器"
                    return None
                for index, handle, description in self._ordered_targets(entries):
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
                    if ok:
                        self.last_error = ""
                        return int(current.value)
                    errors.append(f"显示器 {index}（{description}）{self._win_error('读取 VCP 0x60')}")
                self.last_error = "；".join(errors)
                return None
        except OSError as exc:
            log.debug("Windows 原生 DDC 读取失败：%s", exc)
            self.last_error = str(exc)
            return None

    def set_input(self, value: int) -> bool:
        errors: List[str] = []
        try:
            _user32, dxva2 = self._api()
            with self._physical_monitors() as entries:
                if not entries:
                    self.last_error = self.last_error or "未枚举到物理显示器"
                    return False
                for index, handle, description in self._ordered_targets(entries):
                    # 先做一次 VCP 读取：部分显示器的 DDC 通道在首次访问时才唤醒，
                    # 而且如果画面已经在目标输入源，可以避免不必要的写入。
                    code = wintypes.DWORD()
                    current = wintypes.DWORD()
                    maximum = wintypes.DWORD()
                    if dxva2.GetVCPFeatureAndVCPFeatureReply(
                        handle,
                        VCP_INPUT,
                        ctypes.byref(code),
                        ctypes.byref(current),
                        ctypes.byref(maximum),
                    ) and int(current.value) == int(value):
                        self.last_success = f"显示器 {index}（{description}）已在输入源 {value}"
                        self.last_error = ""
                        return True
                    if dxva2.SetVCPFeature(handle, VCP_INPUT, int(value)):
                        self.last_success = f"显示器 {index}（{description}）"
                        self.last_error = ""
                        log.info("Windows 原生 DDC 写入 %s 成功：%s", value, self.last_success)
                        return True
                    errors.append(f"显示器 {index}（{description}）{self._win_error('写入 VCP 0x60')}")
                    time.sleep(0.12)
                self.last_error = "；".join(errors)
                log.warning("Windows 原生 DDC 写入 %s 失败：%s", value, self.last_error)
                return False
        except OSError as exc:
            log.debug("Windows 原生 DDC 写入失败：%s", exc)
            self.last_error = str(exc)
            return False
