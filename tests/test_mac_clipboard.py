"""macOS 图片剪贴板规范化的格式转换与粘贴板写入测试。"""
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from mac_clipboard import (
    MacClipboardNormalizer,
    bmp_is_windows_compatible,
    image_to_windows_bmp,
)


def image_bytes(fmt: str = "PNG") -> bytes:
    image = Image.new("RGB", (8, 8), (12, 34, 56))
    output = io.BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


class FakeItem:
    def __init__(self, values=None, file_url=None) -> None:
        self.values = dict(values or {})
        self.file_url = file_url
        self.writes = []

    def dataForType_(self, flavor):
        return self.values.get(flavor)

    def stringForType_(self, flavor):
        return self.file_url if flavor == "public.file-url" else None

    def setData_forType_(self, data, flavor):
        self.writes.append((flavor, bytes(data)))
        self.values[flavor] = data
        return True


class FakePasteboard:
    def __init__(self, items) -> None:
        self.items = list(items)

    def pasteboardItems(self):
        return self.items


class MacClipboardTests(unittest.TestCase):
    def test_pillow_output_is_native_windows_bmp(self) -> None:
        bmp = image_to_windows_bmp(image_bytes())
        self.assertIsNotNone(bmp)
        self.assertTrue(bmp_is_windows_compatible(bmp))
        self.assertEqual(bmp[:2], b"BM")

    def test_v5_top_down_dib_is_rejected(self) -> None:
        data = bytearray(14 + 124 + 64)
        data[:2] = b"BM"
        data[10:14] = (138).to_bytes(4, "little")
        data[14:18] = (124).to_bytes(4, "little")
        data[18:22] = (2).to_bytes(4, "little", signed=True)
        data[22:26] = (-2).to_bytes(4, "little", signed=True)
        data[26:28] = (1).to_bytes(2, "little")
        data[28:30] = (32).to_bytes(2, "little")
        data[30:34] = (3).to_bytes(4, "little")
        self.assertFalse(bmp_is_windows_compatible(bytes(data)))

    def test_normalize_rewrites_existing_v5_bmp(self) -> None:
        bad = b"BM" + bytes(60)
        item = FakeItem({"public.tiff": image_bytes("TIFF"), "com.microsoft.bmp": bad})
        normalizer = MacClipboardNormalizer()
        self.assertTrue(normalizer.normalize_once(FakePasteboard([item])))
        self.assertEqual(item.writes[0][0], "com.microsoft.bmp")
        self.assertTrue(bmp_is_windows_compatible(item.writes[0][1]))

    def test_normalize_skips_already_compatible_bmp(self) -> None:
        good = image_to_windows_bmp(image_bytes())
        item = FakeItem({"com.microsoft.bmp": good, "public.tiff": image_bytes("TIFF")})
        normalizer = MacClipboardNormalizer()
        self.assertFalse(normalizer.normalize_once(FakePasteboard([item])))
        self.assertEqual(item.writes, [])

    def test_normalize_reads_image_file_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "图片.png"
            path.write_bytes(image_bytes())
            item = FakeItem(file_url=path.as_uri())
            normalizer = MacClipboardNormalizer()
            self.assertTrue(normalizer.normalize_once(FakePasteboard([item])))
            self.assertTrue(bmp_is_windows_compatible(item.writes[0][1]))

    def test_normalize_ignores_non_image_clipboard(self) -> None:
        item = FakeItem({"public.utf8-plain-text": b"hello"})
        normalizer = MacClipboardNormalizer()
        self.assertFalse(normalizer.normalize_once(FakePasteboard([item])))
        self.assertEqual(item.writes, [])


if __name__ == "__main__":
    unittest.main()
