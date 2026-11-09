"""macOS Carbon 全局热键的解析与注册生命周期测试。"""
from __future__ import annotations

import unittest

import mac_hotkeys


class FakeCarbonAPI:
    def __init__(self) -> None:
        self.handler = None
        self.install_count = 0
        self.registered = []
        self.unregistered = []
        self.removed = []

    def install_handler(self, callback):
        self.handler = callback
        self.install_count += 1
        return 100

    def register_hotkey(self, keycode, modifiers, hotkey_id):
        self.registered.append((keycode, modifiers, hotkey_id))
        return 200 + hotkey_id

    def unregister_hotkey(self, ref):
        self.unregistered.append(ref)

    def remove_handler(self, ref):
        self.removed.append(ref)


class MacHotkeyTests(unittest.TestCase):
    def test_parse_common_combinations(self) -> None:
        self.assertEqual(mac_hotkeys.parse_hotkey("ctrl+alt+1"), (18, 4096 | 2048))
        self.assertEqual(mac_hotkeys.parse_hotkey("cmd+shift+space"), (49, 256 | 512))
        self.assertEqual(mac_hotkeys.parse_hotkey("ctrl+f12"), (111, 4096))

    def test_parse_rejects_invalid_or_unsupported_keys(self) -> None:
        with self.assertRaises(mac_hotkeys.HotkeyError):
            mac_hotkeys.parse_hotkey("a")
        with self.assertRaises(mac_hotkeys.HotkeyError):
            mac_hotkeys.parse_hotkey("hyper+1")
        with self.assertRaises(mac_hotkeys.HotkeyError):
            mac_hotkeys.parse_hotkey("ctrl+volumeup")

    def test_manager_registers_dispatches_and_closes(self) -> None:
        api = FakeCarbonAPI()
        manager = mac_hotkeys.MacHotkeyManager(api=api)
        fired = []
        manager.register("ctrl+alt+1", lambda: fired.append("mac"))
        manager.register("ctrl+alt+2", lambda: fired.append("win"))

        self.assertEqual(api.install_count, 1)
        self.assertEqual([item[2] for item in api.registered], [1, 2])
        api.handler(1)
        self.assertEqual(fired, ["mac"])

        manager.close()
        self.assertEqual(api.unregistered, [201, 202])
        self.assertEqual(api.removed, [100])

    def test_callback_exception_does_not_break_dispatch(self) -> None:
        api = FakeCarbonAPI()
        manager = mac_hotkeys.MacHotkeyManager(api=api)
        fired = []
        manager.register("ctrl+alt+1", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        manager.register("ctrl+alt+2", lambda: fired.append("ok"))
        api.handler(1)
        api.handler(2)
        self.assertEqual(fired, ["ok"])
        manager.close()


if __name__ == "__main__":
    unittest.main()
