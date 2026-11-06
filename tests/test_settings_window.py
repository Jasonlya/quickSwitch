import unittest
from pathlib import Path
from unittest import mock

import settings_window


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
                "/repo/main.py",
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
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def poll(self):
        return None

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
        window = settings_window.SettingsWindow("http://127.0.0.1:8767/")
        with mock.patch.object(settings_window, "webview_available", return_value=True), \
                mock.patch.object(settings_window.subprocess, "Popen", return_value=process) as popen:
            self.assertTrue(window.open())
            self.assertTrue(window.open())
            popen.assert_called_once()
        window.close()
        self.assertTrue(process.terminated)

    def test_rejects_non_local_url_before_spawning(self) -> None:
        window = settings_window.SettingsWindow("https://example.com/")
        with mock.patch.object(settings_window, "webview_available", return_value=True), \
                mock.patch.object(settings_window.subprocess, "Popen") as popen:
            self.assertFalse(window.open())
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
