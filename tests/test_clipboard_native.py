"""Validate actual Windows clipboard byte formats without modifying the user's clipboard."""
import contextlib
import io
import json
from pathlib import Path
import re
import struct
import unittest
from unittest import mock

from PIL import Image
from clipboard_native import WindowsClipboard


class WindowsFormatTests(unittest.TestCase):
    def setUp(self):
        self.backend = WindowsClipboard.__new__(WindowsClipboard)
        self.backend.html_format = 0xC000
        self.backend.user = mock.Mock()
        self.backend.opened = contextlib.nullcontext
        self.formats = {}
        self.backend._put = lambda fmt, data: self.formats.update({fmt: data})

    def test_unicode_text_and_html_byte_offsets(self):
        self.backend.write("text", json.dumps({"text": "你好", "html": "<b>你好</b>"}).encode())
        self.assertEqual(self.formats[13].decode("utf-16-le"), "你好\0")
        html = self.formats[0xC000]
        start = int(re.search(rb"StartFragment:(\d+)", html)[1])
        end = int(re.search(rb"EndFragment:(\d+)", html)[1])
        self.assertEqual(html[start:end].decode(), "<b>你好</b>")

    def test_file_list_uses_wide_dropfiles_header(self):
        paths = [Path("C:/图片.png"), Path("C:/目录")]
        self.backend.write("files", paths)
        data = self.formats[15]
        self.assertEqual(struct.unpack("<IiiII", data[:20]), (20, 0, 0, 0, 1))
        self.assertEqual(data[20:].decode("utf-16-le"), "\0".join(str(path) for path in paths) + "\0\0")

    def test_image_has_dib_header_and_pixels(self):
        output = io.BytesIO()
        Image.new("RGB", (2, 3), "red").save(output, "PNG")
        self.backend.write("image", output.getvalue())
        dib = self.formats[8]
        self.assertEqual(struct.unpack_from("<IiiHHI", dib), (40, 2, 3, 1, 24, 0))
        self.assertEqual(len(dib), 40 + 8 * 3)
