"""Windows 静默子进程参数测试。"""
from __future__ import annotations

import unittest

import process_utils


class SilentProcessTests(unittest.TestCase):
    def test_windows_hides_console(self) -> None:
        kwargs = process_utils.silent_subprocess_kwargs(system="Windows")
        self.assertTrue(kwargs["creationflags"] & process_utils.CREATE_NO_WINDOW)

    def test_windows_detached_keeps_no_window_flag(self) -> None:
        kwargs = process_utils.silent_subprocess_kwargs(system="Windows", detached=True)
        self.assertTrue(kwargs["creationflags"] & process_utils.CREATE_NO_WINDOW)
        self.assertTrue(kwargs["creationflags"] & process_utils.DETACHED_PROCESS)
        self.assertTrue(kwargs["creationflags"] & process_utils.CREATE_NEW_PROCESS_GROUP)

    def test_non_windows_adds_no_flags(self) -> None:
        self.assertEqual(process_utils.silent_subprocess_kwargs(system="Darwin"), {})
        self.assertEqual(process_utils.silent_subprocess_kwargs(system="Linux"), {})


if __name__ == "__main__":
    unittest.main()
