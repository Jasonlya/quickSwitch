import itertools
import unittest
from unittest import mock
from fixed_hotkeys import chord_matches
from main import QuickSwitchApp


class StrictChordTests(unittest.TestCase):
    def test_every_partial_combination_is_rejected(self):
        for target, digit in (("mac", "1"), ("win", "2")):
            keys = ("ctrl", "alt", digit)
            for count in range(4):
                for subset in itertools.combinations(keys, count):
                    with self.subTest(target=target, subset=subset):
                        self.assertEqual(chord_matches(target, set(subset).__contains__), count == 3)

    def test_extra_modifiers_and_other_digit_are_rejected(self):
        for key in ("shift", "win", "1"):
            self.assertFalse(chord_matches("win", {"ctrl", "alt", "2", key}.__contains__))
        self.assertFalse(chord_matches("invalid", lambda _: True))

    def test_stale_hook_callback_cannot_switch_without_full_chord(self):
        app = object.__new__(QuickSwitchApp)
        app.trigger = mock.Mock()
        with mock.patch("main.switch_chord_pressed", return_value=False):
            app._trigger_hotkey("win")
        app.trigger.assert_not_called()
        with mock.patch("main.switch_chord_pressed", return_value=True):
            app._trigger_hotkey("win")
        app.trigger.assert_called_once_with("win", "hotkey")

    def test_tray_default_action_opens_settings(self):
        import pystray
        app = object.__new__(QuickSwitchApp)
        app.platform = "Windows"
        app.quick = mock.Mock()
        app.peer = mock.Mock()
        app._open_console = mock.Mock()
        icon = mock.Mock()
        with mock.patch.object(pystray, "Icon", return_value=icon) as factory:
            app._run_tray()
        menu = factory.call_args.args[3]
        default = next(item for item in menu.items if item.default)
        self.assertEqual(default.text, "打开设置窗口")
        default(icon)
        app._open_console.assert_called_once()

    def test_reopening_settings_foregrounds_existing_process(self):
        from settings_window import SettingsWindow
        window = SettingsWindow("http://127.0.0.1:12345/?t=test")
        window._process = mock.Mock(pid=123)
        window._process.poll.return_value = None
        with mock.patch("settings_window.webview_available", return_value=True), mock.patch("settings_window.focus_settings_process") as focus:
            self.assertTrue(window.open())
        focus.assert_called_once_with(123)

    @unittest.skipUnless(__import__('sys').platform == 'darwin', 'macOS native tray')
    def test_macos_click_dispatch_preserves_right_click_menu(self):
        import mac_tray
        delegate = mac_tray.QuickSwitchTrayDelegate.alloc().init()
        icon = mock.Mock()
        icon._menu_handle = ("menu", [])
        delegate.icon = icon
        event = mock.Mock()
        application = mock.Mock()
        application.currentEvent.return_value = event
        with mock.patch.object(mac_tray.AppKit, "NSApplication") as application_class:
            application_class.sharedApplication.return_value = application
            event.type.return_value = mac_tray.AppKit.NSLeftMouseUp
            delegate.click_(None)
            icon.assert_called_once_with()
            event.type.return_value = mac_tray.AppKit.NSRightMouseUp
            delegate.click_(None)
            icon._status_item.popUpStatusItemMenu_.assert_called_once_with("menu")
            self.assertEqual(icon.call_count, 1)
