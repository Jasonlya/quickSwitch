"""Native clipboard adapters. File lists always take precedence over image previews."""
from __future__ import annotations

import contextlib
import ctypes
import io
import platform
import struct
from pathlib import Path

from PIL import Image, ImageGrab


class MacClipboard:
    def __init__(self):
        from AppKit import NSPasteboard
        self.board = NSPasteboard.generalPasteboard()
        if self.board is None:
            raise OSError("无法连接 macOS 剪贴板服务")

    def token(self):
        return int(self.board.changeCount())

    def read(self):
        from Foundation import NSURL
        paths = self.board.readObjectsForClasses_options_([NSURL], {"NSPasteboardURLReadingFileURLsOnlyKey": True}) or []
        if paths:
            return "files", [Path(str(url.path())) for url in paths]
        for flavor in ("public.png", "public.tiff", "com.microsoft.bmp"):
            data = self.board.dataForType_(flavor)
            if data:
                with Image.open(io.BytesIO(bytes(data))) as image:
                    out = io.BytesIO()
                    image.save(out, "PNG")
                    return "image", out.getvalue()
        text = self.board.stringForType_("public.utf8-plain-text")
        html = self.board.dataForType_("public.html")
        if text is not None or html:
            import json
            return "text", json.dumps({"text": str(text or ""), "html": bytes(html).decode("utf-8") if html else ""}).encode()
        return None

    def write(self, kind, data):
        from AppKit import NSPasteboardItem
        from Foundation import NSData, NSURL
        import json
        if kind == "files":
            objects = [NSURL.fileURLWithPath_(str(path)) for path in data]
        else:
            item = NSPasteboardItem.alloc().init()
            if kind == "image":
                item.setData_forType_(NSData.dataWithBytes_length_(data, len(data)), "public.png")
            else:
                value = json.loads(data)
                item.setString_forType_(value["text"], "public.utf8-plain-text")
                if value.get("html"):
                    item.setString_forType_(value["html"], "public.html")
            objects = [item]
        self.board.clearContents()
        if not self.board.writeObjects_(objects):
            raise OSError("无法写入 macOS 剪贴板")


class WindowsClipboard:
    def __init__(self):
        from ctypes import wintypes as w
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.shell = ctypes.WinDLL("shell32", use_last_error=True)
        self.user.GetClipboardData.argtypes = [w.UINT]
        self.user.GetClipboardData.restype = w.HANDLE
        self.user.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
        self.user.SetClipboardData.restype = w.HANDLE
        self.user.OpenClipboard.argtypes = [w.HWND]
        self.kernel.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
        self.kernel.GlobalAlloc.restype = w.HANDLE
        self.kernel.GlobalLock.argtypes = [w.HANDLE]
        self.kernel.GlobalLock.restype = ctypes.c_void_p
        self.kernel.GlobalUnlock.argtypes = [w.HANDLE]
        self.kernel.GlobalSize.argtypes = [w.HANDLE]
        self.kernel.GlobalSize.restype = ctypes.c_size_t
        self.kernel.GlobalFree.argtypes = [w.HANDLE]
        self.shell.DragQueryFileW.argtypes = [w.HANDLE, w.UINT, w.LPWSTR, w.UINT]
        self.user.RegisterClipboardFormatW.argtypes = [w.LPCWSTR]
        self.html_format = self.user.RegisterClipboardFormatW("HTML Format")
        # EmptyClipboard requires a real owner HWND for subsequent SetClipboardData.
        self.user.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                            w.HWND, w.HMENU, w.HINSTANCE, ctypes.c_void_p]
        self.user.CreateWindowExW.restype = w.HWND
        self.hwnd = self.user.CreateWindowExW(0, "STATIC", "QuickSwitch Clipboard", 0,
                                              0, 0, 0, 0, -3, None, None, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.user.DestroyWindow.argtypes = [w.HWND]
        self.user.GetClipboardSequenceNumber.restype = w.DWORD
        self.user.PeekMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT, w.UINT]
        self.user.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
        self.user.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
        self.user.DispatchMessageW.restype = ctypes.c_ssize_t

    def close(self):
        self.user.DestroyWindow(self.hwnd)

    def token(self):
        # Service messages for the clipboard owner window on its owning thread.
        from ctypes import wintypes
        message = wintypes.MSG()
        while self.user.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
            self.user.TranslateMessage(ctypes.byref(message))
            self.user.DispatchMessageW(ctypes.byref(message))
        return int(self.user.GetClipboardSequenceNumber())

    @contextlib.contextmanager
    def opened(self):
        if not self.user.OpenClipboard(self.hwnd):
            raise OSError("剪贴板正忙")
        try:
            yield
        finally:
            self.user.CloseClipboard()

    def _data(self, fmt):
        handle = self.user.GetClipboardData(fmt)
        if not handle:
            return None
        pointer = self.kernel.GlobalLock(handle)
        if not pointer:
            raise OSError("无法读取剪贴板")
        try:
            return ctypes.string_at(pointer, self.kernel.GlobalSize(handle))
        finally:
            self.kernel.GlobalUnlock(handle)

    def read(self):
        import json
        with self.opened():
            handle = self.user.GetClipboardData(15)  # CF_HDROP
            if handle:
                paths = []
                for index in range(self.shell.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)):
                    length = self.shell.DragQueryFileW(handle, index, None, 0)
                    buf = ctypes.create_unicode_buffer(length + 1)
                    self.shell.DragQueryFileW(handle, index, buf, length + 1)
                    paths.append(Path(buf.value))
                return "files", paths
            has_image = self.user.IsClipboardFormatAvailable(8) or self.user.IsClipboardFormatAvailable(17)
            text = self._data(13)
            html = self._data(self.html_format)
        if has_image:
            image = ImageGrab.grabclipboard()
            if isinstance(image, Image.Image):
                output = io.BytesIO()
                image.save(output, "PNG")
                return "image", output.getvalue()
        if text is not None or html:
            # CF_HTML offsets are byte offsets, not character offsets.
            fragment = ""
            if html:
                import re
                start = re.search(rb"StartFragment:(\d+)", html)
                end = re.search(rb"EndFragment:(\d+)", html)
                if start and end:
                    fragment = html[int(start[1]):int(end[1])].decode("utf-8", errors="replace")
            return "text", json.dumps({"text": text.decode("utf-16-le").split("\0", 1)[0] if text else "", "html": fragment}).encode()
        return None

    def _put(self, fmt, data):
        handle = self.kernel.GlobalAlloc(0x42, len(data))
        if not handle:
            raise MemoryError("剪贴板内存分配失败")
        try:
            pointer = self.kernel.GlobalLock(handle)
            if not pointer:
                raise OSError("无法锁定剪贴板内存")
            ctypes.memmove(pointer, data, len(data))
            self.kernel.GlobalUnlock(handle)
            if not self.user.SetClipboardData(fmt, handle):
                raise OSError("无法写入 Windows 剪贴板")
        except BaseException:
            self.kernel.GlobalFree(handle)
            raise

    def write(self, kind, data):
        import json
        formats = []
        if kind == "files":
            names = ("\0".join(str(p) for p in data) + "\0\0").encode("utf-16-le")
            formats.append((15, struct.pack("<IiiII", 20, 0, 0, 0, 1) + names))
        elif kind == "image":
            with Image.open(io.BytesIO(data)) as image:
                output = io.BytesIO()
                image.convert("RGB").save(output, "BMP")
                formats.append((8, output.getvalue()[14:]))
        else:
            value = json.loads(data)
            formats.append((13, (value["text"] + "\0").encode("utf-16-le")))
            if value.get("html"):
                prefix = b"<html><body><!--StartFragment-->"
                fragment = value["html"].encode("utf-8")
                suffix = b"<!--EndFragment--></body></html>"
                template = "Version:0.9\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\nStartFragment:{:010d}\r\nEndFragment:{:010d}\r\n"
                start = len(template.format(0, 0, 0, 0).encode())
                header = template.format(start, start + len(prefix + fragment + suffix), start + len(prefix), start + len(prefix + fragment)).encode()
                formats.append((self.html_format, header + prefix + fragment + suffix + b"\0"))
        with self.opened():
            if not self.user.EmptyClipboard():
                raise OSError("无法清空 Windows 剪贴板")
            for fmt, payload in formats:
                self._put(fmt, payload)


def native_clipboard():
    if platform.system() == "Darwin":
        return MacClipboard()
    if platform.system() == "Windows":
        return WindowsClipboard()
    raise RuntimeError("剪贴板共享仅支持 macOS 和 Windows")
