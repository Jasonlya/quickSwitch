"""Fixed shortcuts, checked against OS key state rather than hook history."""
import ctypes
import ctypes.util
from functools import lru_cache
import platform

FIXED_HOTKEYS = {"switch_to_mac": "ctrl+alt+1", "switch_to_win": "ctrl+alt+2"}


def chord_matches(target, down):
    """Require Ctrl + Alt + the target digit; reject Shift/Win and the other digit."""
    if target not in ("mac", "win"):
        return False
    digit, other = ("1", "2") if target == "mac" else ("2", "1")
    return (down("ctrl") and down("alt") and down(digit)
            and not any(down(key) for key in ("shift", "win", other)))


@lru_cache(maxsize=2)
def _key_reader(system):
    if system == "Windows":
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user.GetAsyncKeyState.restype = ctypes.c_short
        codes = {"ctrl": (0xA2, 0xA3), "alt": (0xA4, 0xA5), "shift": (0xA0, 0xA1),
                 "win": (0x5B, 0x5C), "1": (0x31,), "2": (0x32,)}
        return lambda key: any(user.GetAsyncKeyState(code) & 0x8000 for code in codes[key])
    if system == "Darwin":
        cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
        cg.CGEventSourceKeyState.argtypes = [ctypes.c_int, ctypes.c_uint16]
        cg.CGEventSourceKeyState.restype = ctypes.c_bool
        codes = {"ctrl": (59, 62), "alt": (58, 61), "shift": (56, 60),
                 "win": (54, 55), "1": (18,), "2": (19,)}
        # HID system state avoids trusting stale modifier flags in injected events.
        return lambda key: any(cg.CGEventSourceKeyState(0, code) for code in codes[key])
    raise RuntimeError("不支持此平台的热键状态检查")


def switch_chord_pressed(target):
    try:
        return chord_matches(target, _key_reader(platform.system()))
    except Exception:
        return False  # Fail closed if the OS cannot confirm the complete chord.
