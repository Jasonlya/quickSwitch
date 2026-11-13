"""macOS 原生全局热键。

``keyboard`` 库只适用于 Windows；macOS 端改用 Carbon 的
``RegisterEventHotKey``。它不需要辅助功能/输入监控权限，也不会吞掉普通按键。
热键事件由主线程的 NSApplication 事件循环派发；无托盘模式由 ``pump_events``
主动驱动 Carbon 事件循环。
"""
from __future__ import annotations

import ctypes
import ctypes.util
import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from config import normalize_hotkey

log = logging.getLogger("mac_hotkeys")

_HOTKEY_SIGNATURE = 0x51535748  # "QSWH"
_EVENT_CLASS_KEYBOARD = 0x6B657962  # "keyb"
_EVENT_HOTKEY_PRESSED = 5
_PARAM_DIRECT_OBJECT = 0x2D2D2D2D  # "----"
_TYPE_EVENT_HOTKEY_ID = 0x686B6964  # "hkid"
_EVENT_NOT_HANDLED = -9874

# Carbon 修饰键常量
_MOD_CMD = 256
_MOD_SHIFT = 512
_MOD_OPTION = 2048
_MOD_CONTROL = 4096
_MODIFIERS = {
    "windows": _MOD_CMD,
    "shift": _MOD_SHIFT,
    "alt": _MOD_OPTION,
    "ctrl": _MOD_CONTROL,
}

# macOS 虚拟键码（Carbon/Quartz）
_KEY_CODES: Dict[str, int] = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22,
    "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29,
    "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "enter": 36,
    "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43,
    "/": 44, "n": 45, "m": 46, ".": 47, "tab": 48, "space": 49,
    "`": 50, "backspace": 51, "esc": 53,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97,
    "f7": 98, "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "home": 115, "pageup": 116, "delete": 117, "end": 119,
    "pagedown": 121, "left": 123, "right": 124, "down": 125, "up": 126,
    "insert": 114,
}


class HotkeyError(RuntimeError):
    """热键格式无效或 Carbon 注册失败。"""


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


def parse_hotkey(value: str) -> Tuple[int, int]:
    """把配置里的组合键转换成 Carbon 的 ``(keycode, modifiers)``。"""
    normalized = normalize_hotkey(value)
    if normalized is None:
        raise HotkeyError(f"热键格式无效：{value}")
    parts = normalized.split("+")
    key = parts[-1]
    keycode = _KEY_CODES.get(key)
    if keycode is None:
        raise HotkeyError(f"macOS 不支持这个按键：{key}")
    modifiers = 0
    for modifier in parts[:-1]:
        try:
            modifiers |= _MODIFIERS[modifier]
        except KeyError as exc:
            raise HotkeyError(f"macOS 不支持这个修饰键：{modifier}") from exc
    return keycode, modifiers


class _CarbonAPI:
    """对 Carbon/CoreFoundation 的最小 ctypes 封装，便于单测替换。"""

    def __init__(self) -> None:
        path = ctypes.util.find_library("Carbon")
        if not path:
            raise HotkeyError("找不到 macOS Carbon 框架")
        self.lib = ctypes.cdll.LoadLibrary(path)
        self._handler_callback = None
        self.lib.GetApplicationEventTarget.restype = ctypes.c_void_p
        self.lib.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            _EventHotKeyID,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.lib.RegisterEventHotKey.restype = ctypes.c_int32
        self.lib.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        self.lib.UnregisterEventHotKey.restype = ctypes.c_int32
        self.lib.InstallEventHandler.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(_EventTypeSpec),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.lib.InstallEventHandler.restype = ctypes.c_int32
        self.lib.RemoveEventHandler.argtypes = [ctypes.c_void_p]
        self.lib.RemoveEventHandler.restype = ctypes.c_int32
        self.lib.GetEventParameter.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self.lib.GetEventParameter.restype = ctypes.c_int32

    def install_handler(self, on_hotkey: Callable[[int], None]) -> int:
        handler_type = ctypes.CFUNCTYPE(
            ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )

        @handler_type
        def handler(_call_ref, event, _user_data):
            hotkey_id = _EventHotKeyID()
            status = self.lib.GetEventParameter(
                event,
                _PARAM_DIRECT_OBJECT,
                _TYPE_EVENT_HOTKEY_ID,
                None,
                ctypes.sizeof(hotkey_id),
                None,
                ctypes.byref(hotkey_id),
            )
            if status != 0:
                return _EVENT_NOT_HANDLED
            on_hotkey(int(hotkey_id.id))
            return 0

        self._handler_callback = handler
        spec = _EventTypeSpec(_EVENT_CLASS_KEYBOARD, _EVENT_HOTKEY_PRESSED)
        handler_ref = ctypes.c_void_p()
        status = self.lib.InstallEventHandler(
            self.lib.GetApplicationEventTarget(),
            handler,
            1,
            ctypes.byref(spec),
            None,
            ctypes.byref(handler_ref),
        )
        if status != 0 or not handler_ref.value:
            self._handler_callback = None
            raise HotkeyError(f"安装 macOS 热键处理器失败（{status}）")
        return int(handler_ref.value)

    def register_hotkey(self, keycode: int, modifiers: int, hotkey_id: int) -> int:
        ref = ctypes.c_void_p()
        status = self.lib.RegisterEventHotKey(
            keycode,
            modifiers,
            _EventHotKeyID(_HOTKEY_SIGNATURE, hotkey_id),
            self.lib.GetApplicationEventTarget(),
            0,
            ctypes.byref(ref),
        )
        if status != 0 or not ref.value:
            raise HotkeyError(f"注册 macOS 热键失败（Carbon 错误 {status}）")
        return int(ref.value)

    def unregister_hotkey(self, ref: int) -> None:
        self.lib.UnregisterEventHotKey(ctypes.c_void_p(ref))

    def remove_handler(self, ref: int) -> None:
        self.lib.RemoveEventHandler(ctypes.c_void_p(ref))


class MacHotkeyManager:
    """注册/注销一组 macOS 全局热键；重复注册前先调用 ``close``。"""

    def __init__(self, api: Optional[_CarbonAPI] = None) -> None:
        self._api = api
        self._observer = _HotkeyObserver(self._dispatch) if api is None else None
        self._last_dispatch = {}
        self._handler_ref: Optional[int] = None
        self._refs: List[Tuple[int, int, str]] = []
        self._callbacks: Dict[int, Callable[[], None]] = {}
        self._next_id = 1
        self._lock = threading.RLock()
        self._closed = False

    def _ensure_api(self) -> _CarbonAPI:
        if self._api is None:
            self._api = _CarbonAPI()
        return self._api

    def register(self, combo: str, callback: Callable[[], None]) -> None:
        keycode, modifiers = parse_hotkey(combo)
        with self._lock:
            if self._closed:
                raise HotkeyError("热键管理器已经关闭")
            api = self._ensure_api()
            if self._handler_ref is None:
                self._handler_ref = api.install_handler(self._dispatch)
            hotkey_id = self._next_id
            self._next_id += 1
            ref = api.register_hotkey(keycode, modifiers, hotkey_id)
            self._callbacks[hotkey_id] = callback
            self._refs.append((ref, hotkey_id, combo))
            if self._observer is not None:
                self._observer.add(keycode, modifiers, hotkey_id)

    def _dispatch(self, hotkey_id: int) -> None:
        with self._lock:
            callback = self._callbacks.get(hotkey_id)
            now = time.monotonic()
            if callback is None or now - self._last_dispatch.get(hotkey_id, -1) < 0.25:
                return
            self._last_dispatch[hotkey_id] = now
        combo = next(
            (item[2] for item in self._refs if item[1] == hotkey_id),
            f"id={hotkey_id}",
        )
        log.info("macOS 热键触发：%s", combo)
        try:
            callback()
        except Exception:
            log.exception("执行 macOS 热键回调失败")

    def close(self) -> None:
        if self._observer is not None:
            self._observer.close()
        with self._lock:
            if self._closed:
                return
            self._closed = True
            api = self._api
            if api is not None:
                for ref, _hotkey_id, _combo in self._refs:
                    try:
                        api.unregister_hotkey(ref)
                    except Exception as exc:
                        log.debug("注销 macOS 热键失败：%s", exc)
                if self._handler_ref is not None:
                    try:
                        api.remove_handler(self._handler_ref)
                    except Exception as exc:
                        log.debug("移除 macOS 热键处理器失败：%s", exc)
            self._refs.clear()
            self._callbacks.clear()
            self._handler_ref = None

    def __enter__(self) -> "MacHotkeyManager":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def pump_events(seconds: float = 0.05) -> None:
    """无托盘模式下驱动一次当前线程的 Carbon/CF 事件循环。"""
    path = ctypes.util.find_library("CoreFoundation")
    if not path:
        return
    cf = ctypes.cdll.LoadLibrary(path)
    cf.CFRunLoopRunInMode.argtypes = [
        ctypes.c_void_p,
        ctypes.c_double,
        ctypes.c_bool,
    ]
    cf.CFRunLoopRunInMode.restype = ctypes.c_int32
    mode = ctypes.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode")
    cf.CFRunLoopRunInMode(mode, max(0.0, float(seconds)), True)


class _HotkeyObserver:
    """Listen at the HID tap before Deskflow can consume forwarded keystrokes.

    Carbon remains the permission-free fallback. This tap never swallows keys;
    it has its own run loop so tray menus cannot delay hotkey dispatch.
    """
    def __init__(self, dispatch):
        self.dispatch = dispatch
        self.bindings = {}
        self.stop_event = threading.Event()
        self.thread = None

    def add(self, keycode, modifiers, hotkey_id):
        # Carbon and Quartz use different modifier masks.
        flags = 0
        for carbon, quartz in ((_MOD_CMD, 1 << 20), (_MOD_SHIFT, 1 << 17),
                                (_MOD_OPTION, 1 << 19), (_MOD_CONTROL, 1 << 18)):
            if modifiers & carbon:
                flags |= quartz
        self.bindings[(keycode, flags)] = hotkey_id
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, daemon=True, name="quickswitch-hotkeys")
            self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)

    def _run(self):
        tap = source = None
        try:
            cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
            cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
            callback_type = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32,
                                             ctypes.c_void_p, ctypes.c_void_p)
            cg.CGEventTapCreate.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
                                          ctypes.c_uint64, callback_type, ctypes.c_void_p]
            cg.CGEventTapCreate.restype = ctypes.c_void_p
            cg.CGEventGetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            cg.CGEventGetIntegerValueField.restype = ctypes.c_int64
            cg.CGEventGetFlags.argtypes = [ctypes.c_void_p]
            cg.CGEventGetFlags.restype = ctypes.c_uint64
            cg.CGEventTapEnable.argtypes = [ctypes.c_void_p, ctypes.c_bool]
            cf.CFMachPortCreateRunLoopSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]
            cf.CFMachPortCreateRunLoopSource.restype = ctypes.c_void_p
            cf.CFRunLoopGetCurrent.restype = ctypes.c_void_p
            cf.CFRunLoopAddSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            cf.CFRunLoopRemoveSource.argtypes = cf.CFRunLoopAddSource.argtypes
            cf.CFRunLoopRunInMode.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_bool]
            cf.CFMachPortInvalidate.argtypes = [ctypes.c_void_p]
            cf.CFRelease.argtypes = [ctypes.c_void_p]
            mask = (1 << 17) | (1 << 18) | (1 << 19) | (1 << 20)

            @callback_type
            def callback(_proxy, event_type, event, _context):
                try:
                    if event_type in (0xFFFFFFFE, 0xFFFFFFFF):
                        cg.CGEventTapEnable(tap, True)
                    elif event_type == 10 and not cg.CGEventGetIntegerValueField(event, 8):
                        key = int(cg.CGEventGetIntegerValueField(event, 9))
                        flags = int(cg.CGEventGetFlags(event)) & mask
                        hotkey_id = self.bindings.get((key, flags))
                        if hotkey_id:
                            self.dispatch(hotkey_id)
                except Exception:
                    log.exception("处理 macOS 键盘监听事件失败")
                return event

            # kCGHIDEventTap, kCGHeadInsertEventTap, kCGEventTapOptionListenOnly
            tap = cg.CGEventTapCreate(0, 0, 1, 1 << 10, callback, None)
            if not tap:
                log.warning("macOS 热键监听不可用（请检查输入监控权限），继续使用 Carbon 热键")
                return
            source = cf.CFMachPortCreateRunLoopSource(None, tap, 0)
            if not source:
                raise HotkeyError("无法创建热键监听事件源")
            mode = ctypes.c_void_p.in_dll(cf, "kCFRunLoopDefaultMode")
            loop = cf.CFRunLoopGetCurrent()
            cf.CFRunLoopAddSource(loop, source, mode)
            try:
                while not self.stop_event.is_set():
                    cf.CFRunLoopRunInMode(mode, 0.1, False)
            finally:
                cf.CFRunLoopRemoveSource(loop, source, mode)
        except Exception:
            log.warning("macOS 热键监听启动失败，继续使用 Carbon 热键", exc_info=True)
        finally:
            if source:
                cf.CFRelease(source)
            if tap:
                cf.CFMachPortInvalidate(tap)
                cf.CFRelease(tap)
