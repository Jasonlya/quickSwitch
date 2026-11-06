"""Windows 原生 DDC 后端的纯 Python 单元测试（不加载真实 dxva2.dll）。"""
from __future__ import annotations

import contextlib
import unittest
from typing import Iterator, List, Tuple

from windows_ddc import VCP_INPUT, WindowsNativeDDC


class FakeDxva2:
    def __init__(self, value: int = 18, failing_handles=()) -> None:
        self.value = value
        self.failing_handles = set(failing_handles)
        self.read_handles: List[int] = []
        self.writes: List[Tuple[int, int, int]] = []

    def GetVCPFeatureAndVCPFeatureReply(
        self,
        handle: int,
        code: int,
        _code_type,
        current,
        _maximum,
    ) -> int:
        self.read_handles.append(handle)
        assert code == VCP_INPUT
        if handle in self.failing_handles:
            return 0
        current._obj.value = self.value
        return 1

    def SetVCPFeature(self, handle: int, code: int, value: int) -> int:
        self.writes.append((handle, code, value))
        if handle in self.failing_handles:
            return 0
        self.value = value
        return 1


class Harness(WindowsNativeDDC):
    def __init__(
        self,
        display_index: int,
        entries: List[Tuple[int, int, str]],
        *,
        failing_handles=(),
    ) -> None:
        super().__init__(display_index)
        self.entries = entries
        self.dxva2 = FakeDxva2(failing_handles=failing_handles)

    def _api(self):
        return object(), self.dxva2

    @contextlib.contextmanager
    def _physical_monitors(self) -> Iterator[List[Tuple[int, int, str]]]:
        yield self.entries


class WindowsNativeDDCTests(unittest.TestCase):
    def test_reads_and_writes_selected_physical_monitor(self) -> None:
        backend = Harness(2, [(1, 101, "Left"), (2, 202, "Center")])

        self.assertEqual(backend.get_input(), 18)
        self.assertTrue(backend.set_input(15))
        self.assertEqual(backend.dxva2.read_handles, [202, 202])
        self.assertEqual(backend.dxva2.writes, [(202, VCP_INPUT, 15)])

    def test_falls_back_to_first_monitor_when_index_is_out_of_range(self) -> None:
        backend = Harness(9, [(1, 101, "Only")])

        self.assertEqual(backend.get_input(), 18)
        self.assertEqual(backend.dxva2.read_handles, [101])

    def test_skips_write_when_monitor_is_already_on_target_input(self) -> None:
        backend = Harness(1, [(1, 101, "Only")])

        self.assertTrue(backend.set_input(18))
        self.assertEqual(backend.dxva2.writes, [])
        self.assertIn("已在输入源 18", backend.last_success)

    def test_no_monitors_returns_no_value(self) -> None:
        backend = Harness(1, [])

        self.assertIsNone(backend.get_input())
        self.assertFalse(backend.set_input(15))
        self.assertIn("未枚举到物理显示器", backend.last_error)

    def test_tries_other_physical_monitors_when_selected_one_fails(self) -> None:
        backend = Harness(1, [(1, 101, "Internal"), (2, 202, "Shared")], failing_handles={101})

        self.assertEqual(backend.get_input(), 18)
        self.assertTrue(backend.set_input(15))
        self.assertEqual(backend.dxva2.read_handles, [101, 202, 101, 202])
        self.assertEqual(backend.dxva2.writes, [(101, VCP_INPUT, 15), (202, VCP_INPUT, 15)])
        self.assertIn("Shared", backend.last_success)

    def test_records_error_when_all_monitors_reject_write(self) -> None:
        backend = Harness(1, [(1, 101, "Only")], failing_handles={101})

        self.assertFalse(backend.set_input(15))
        self.assertIn("Only", backend.last_error)


if __name__ == "__main__":
    unittest.main()
