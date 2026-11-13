import sys
import unittest
from pathlib import Path
from unittest import mock

import settings_window


class _DpiFunction:
    def __init__(self, result=1):
        self.result = result
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, value):
        self.calls.append(value)
        return self.result


class _DpiDll:
    def __init__(self, *, context=None, awareness=None, legacy=None):
        if context is not None:
            self.SetProcessDpiAwarenessContext = context
        if awareness is not None:
            self.SetProcessDpiAwareness = awareness
        if legacy is not None:
            self.SetProcessDPIAware = legacy


class _FakeCtypes:
    c_void_p = staticmethod(lambda value: ("pointer", value))
    c_int = int
    c_long = int
    c_bool = bool

    def __init__(self, dlls):
        self._dlls = dlls
        self.loaded = []

    def WinDLL(self, name, use_last_error=True):
        self.loaded.append(name)
        return self._dlls[name]


class ConsoleUrlTests(unittest.TestCase):
    def test_accepts_loopback_console_urls(self) -> None:
        for url in (
            "http://127.0.0.1:8767/?t=secret",
            "http://localhost:8767/",
            "http://[::1]:8767/?t=secret",
        ):
            with self.subTest(url=url):
                self.assertTrue(settings_window.is_local_console_url(url))

    def test_rejects_external_or_incomplete_urls(self) -> None:
        for url in (
            "https://127.0.0.1:8767/",
            "http://example.com:8767/",
            "http://127.0.0.1/",
            "file:///tmp/settings.html",
            "not a url",
        ):
            with self.subTest(url=url):
                self.assertFalse(settings_window.is_local_console_url(url))


class WindowsDpiTests(unittest.TestCase):
    def test_noop_outside_windows(self) -> None:
        with mock.patch.object(settings_window.sys, "platform", "darwin"):
            self.assertFalse(settings_window.enable_windows_high_dpi())

    def test_prefers_per_monitor_v2_before_importing_webview(self) -> None:
        set_context = _DpiFunction(True)
        fake = _FakeCtypes({"user32": _DpiDll(context=set_context)})
        with mock.patch.object(settings_window.sys, "platform", "win32"), \
                mock.patch.dict(sys.modules, {"ctypes": fake}):
            self.assertTrue(settings_window.enable_windows_high_dpi())
        self.assertEqual(set_context.calls, [("pointer", -4)])
        self.assertEqual(fake.loaded, ["user32"])

    def test_falls_back_to_per_monitor_awareness(self) -> None:
        set_awareness = _DpiFunction(0)
        fake = _FakeCtypes({
            "user32": _DpiDll(),
            "shcore": _DpiDll(awareness=set_awareness),
        })
        with mock.patch.object(settings_window.sys, "platform", "win32"), \
                mock.patch.dict(sys.modules, {"ctypes": fake}):
            self.assertTrue(settings_window.enable_windows_high_dpi())
        self.assertEqual(set_awareness.calls, [2])


class CommandTests(unittest.TestCase):
    def test_source_command_reuses_python_and_main_script(self) -> None:
        command = settings_window.settings_window_command(
            "http://127.0.0.1:8767/?t=secret",
            frozen=False,
            executable="/usr/bin/python3",
            script=Path("/repo/main.py"),
        )
        self.assertEqual(
            command,
            [
                "/usr/bin/python3",
                str(Path("/repo/main.py")),
                "--settings-window",
                "http://127.0.0.1:8767/?t=secret",
            ],
        )

    def test_frozen_command_reuses_bundle_executable(self) -> None:
        command = settings_window.settings_window_command(
            "http://127.0.0.1:8767/",
            frozen=True,
            executable="/Applications/QuickSwitch.app/Contents/MacOS/QuickSwitch",
        )
        self.assertEqual(
            command,
            [
                "/Applications/QuickSwitch.app/Contents/MacOS/QuickSwitch",
                "--settings-window",
                "http://127.0.0.1:8767/",
            ],
        )


class _Process:
    def __init__(self, *, exits: bool = False) -> None:
        self.pid = 123
        self.terminated = False
        self.killed = False
        self.exits = exits

    def poll(self):
        return 1 if self.terminated or self.exits else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout=None) -> int:
        return 0

    def kill(self) -> None:
        self.killed = True


class SettingsWindowTests(unittest.TestCase):
    def test_falls_back_when_webview_is_unavailable(self) -> None:
        window = settings_window.SettingsWindow("http://127.0.0.1:8767/")
        with mock.patch.object(settings_window, "webview_available", return_value=False):
            self.assertFalse(window.open())

    def test_reuses_one_window_process(self) -> None:
        process = _Process()
        window = settings_window.SettingsWindow(
            "http://127.0.0.1:8767/", startup_grace=0
        )
        with mock.patch.object(settings_window, "webview_available", return_value=True), \
                mock.patch.object(settings_window.subprocess, "Popen", return_value=process) as popen, \
                mock.patch.object(settings_window, "focus_settings_process") as focus:
            self.assertTrue(window.open())
            self.assertTrue(window.open())
            popen.assert_called_once()
            focus.assert_called_once_with(123)
        window.close()
        self.assertTrue(process.terminated)

    def test_rejects_non_local_url_before_spawning(self) -> None:
        window = settings_window.SettingsWindow("https://example.com/")
        with mock.patch.object(settings_window, "webview_available", return_value=True), \
                mock.patch.object(settings_window.subprocess, "Popen") as popen:
            self.assertFalse(window.open())
            popen.assert_not_called()

    def test_window_process_is_spawned_without_console_or_hidden_gui(self) -> None:
        process = _Process()
        window = settings_window.SettingsWindow(
            "http://127.0.0.1:8767/", startup_grace=0
        )
        with mock.patch.object(settings_window, "webview_available", return_value=True), \
                mock.patch("process_utils.platform.system", return_value="Windows"), \
                mock.patch.object(settings_window.subprocess, "Popen", return_value=process) as popen, \
                mock.patch.object(settings_window, "focus_settings_process") as focus:
            self.assertTrue(window.open())
        self.assertTrue(popen.call_args.kwargs["creationflags"] & 0x08000000)
        self.assertNotIn("startupinfo", popen.call_args.kwargs)

    def test_alive_window_process_counts_as_opened(self) -> None:
        process = mock.Mock()
        process.wait.side_effect = settings_window.subprocess.TimeoutExpired("QuickSwitch", 1.2)
        window = settings_window.SettingsWindow("http://127.0.0.1:8767/")
        with mock.patch.object(settings_window, "webview_available", return_value=True), \
                mock.patch.object(settings_window.subprocess, "Popen", return_value=process):
            self.assertTrue(window.open())
        process.wait.assert_called_once_with(timeout=settings_window.STARTUP_GRACE_SECONDS)

    def test_immediately_exiting_window_process_falls_back(self) -> None:
        process = mock.Mock()
        process.wait.return_value = 1
        window = settings_window.SettingsWindow("http://127.0.0.1:8767/")
        with mock.patch.object(settings_window, "webview_available", return_value=True), \
                mock.patch.object(settings_window.subprocess, "Popen", return_value=process):
            self.assertFalse(window.open())
        self.assertIsNone(window._process)


if __name__ == "__main__":
    unittest.main()
