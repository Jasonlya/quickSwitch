"""DDC 写入自检命令的单元测试。"""
from __future__ import annotations

import contextlib
import io
import unittest

from main import cmd_ddc_selftest


class FakeDDC:
    system = "Windows"
    ddc_cfg = {"display_index": 1}
    win_input = 15
    mac_input = 18

    def __init__(self, *, current=15, write_ok=True, error="") -> None:
        self.current = current
        self.write_ok = write_ok
        self.error = error
        self.writes = []

    def tool_available(self):
        return True, "Windows 原生 DDC（DXVA2）已检测到 1 个显示器：Shared"

    def get_input(self):
        return self.current

    def set_input(self, value):
        self.writes.append(value)
        return self.write_ok

    def native_error(self):
        return self.error


class DdcSelfTestTests(unittest.TestCase):
    def run_test(self, ddc):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cmd_ddc_selftest({}, ddc=ddc)
        return code, out.getvalue()

    def test_writes_current_value_without_changing_input(self) -> None:
        ddc = FakeDDC(current=15)
        code, output = self.run_test(ddc)

        self.assertEqual(code, 0)
        self.assertEqual(ddc.writes, [15])
        self.assertIn("不会改变画面", output)
        self.assertIn("写入结果   : 成功", output)

    def test_uses_platform_input_when_read_fails_and_reports_native_error(self) -> None:
        ddc = FakeDDC(current=None, write_ok=False, error="写入 VCP 0x60 失败（WinError 31）")
        code, output = self.run_test(ddc)

        self.assertEqual(code, 1)
        self.assertEqual(ddc.writes, [15])
        self.assertIn("原生错误", output)
        self.assertIn("WinError 31", output)
        self.assertIn("OSD", output)
        self.assertIn("DDC/CI", output)


if __name__ == "__main__":
    unittest.main()
