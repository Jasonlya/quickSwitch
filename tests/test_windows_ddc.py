"""Windows 原生 DDC 后端的纯 Python 单元测试（不加载真实 dxva2.dll）。"""
from __future__ import annotations

import contextlib
import unittest
from typing import Iterator, List, Tuple

from windows_ddc import VCP_INPUT, WindowsNativeDDC


class FakeDxva2:
    def __init__(self, value: int = 18) -> None:
        self.value = value
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
        current._obj.value = self.value
        return 1

    def SetVCPFeature(self, handle: int, code: int, value: int) -> int:
        self.writes.append((handle, code, value))
        self.value = value
        return 1


class Harness(WindowsNativeDDC):
    def __init__(self, display_index: int, entries: List[Tuple[int, int, str]]) -> None:
        super().__init__(display_index)
        self.entries = entries
        self.dxva2 = FakeDxva2()

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
        self.assertEqual(backend.dxva2.read_handles, [202])
        self.assertEqual(backend.dxva2.writes, [(202, VCP_INPUT, 15)])

    def test_falls_back_to_first_monitor_when_index_is_out_of_range(self) -> None:
        backend = Harness(9, [(1, 101, "Only")])

        self.assertEqual(backend.get_input(), 18)
        self.assertEqual(backend.dxva2.read_handles, [101])

    def test_no_monitors_returns_no_value(self) -> None:
        backend = Harness(1, [])

        self.assertIsNone(backend.get_input())
        self.assertFalse(backend.set_input(15))


if __name__ == "__main__":
    unittest.main()
