"""把 macOS 剪贴板图片规范成 Windows 能解码的 BMP。

Deskflow 1.27.0 会把 macOS 粘贴板里的 ``com.microsoft.bmp`` 原样转发给
Windows。macOS 截图常见的是 ``BITMAPV5HEADER`` + 顶行 + ``BI_BITFIELDS``，
大多数 Windows 程序无法把它合成 ``CF_BITMAP``。这里在图片变更后补一份
40 字节 ``BITMAPINFOHEADER``、底行、``BI_RGB`` 的规范 BMP，不调用
``clearContents``，也不改变剪贴板变更计数。
"""
from __future__ import annotations

import io
import logging
import platform
import struct
import threading
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from PIL import Image

log = logging.getLogger("mac_clipboard")

_IMAGE_TYPES = (
    "public.tiff",
    "public.png",
    "public.jpeg",
    "public.jpg",
    "com.microsoft.bmp",
    "public.bmp",
)


def bmp_is_windows_compatible(data: bytes) -> bool:
    """判断 BMP 是否是 Windows ``CF_DIB`` 能直接接受的规范形式。"""
    if len(data) < 54 or data[:2] != b"BM":
        return False
    try:
        pixel_offset = struct.unpack_from("<I", data, 10)[0]
        header_size = struct.unpack_from("<I", data, 14)[0]
        width = struct.unpack_from("<i", data, 18)[0]
        height = struct.unpack_from("<i", data, 22)[0]
        planes = struct.unpack_from("<H", data, 26)[0]
        bit_count = struct.unpack_from("<H", data, 28)[0]
        compression = struct.unpack_from("<I", data, 30)[0]
    except struct.error:
        return False
    if header_size != 40 or width <= 0 or height <= 0:
        return False
    if planes != 1 or bit_count not in (24, 32) or compression != 0:
        return False
    if pixel_offset < 54 or pixel_offset > len(data):
        return False
    row_bytes = ((width * bit_count + 31) // 32) * 4
    return len(data) >= pixel_offset + row_bytes * height


def image_to_windows_bmp(data: bytes) -> Optional[bytes]:
    """把任意 Pillow 能读的图片转成规范 BMP；失败返回 ``None``。"""
    if not data:
        return None
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.seek(0)
            if source.mode in ("RGBA", "LA", "PA") or "transparency" in source.info:
                rgba = source.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                image = flat
            else:
                image = source.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="BMP")
    except Exception as exc:
        log.debug("剪贴板图片解码失败：%s", exc)
        return None
    bmp = output.getvalue()
    return bmp if bmp_is_windows_compatible(bmp) else None


def _file_url_to_path(value: Any) -> Optional[Path]:
    if not value:
        return None
    parsed = urlparse(str(value))
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return None
    path = Path(unquote(parsed.path))
    return path if path.is_file() else None


def _as_nsdata(data: bytes) -> Any:
    """真实 macOS 上转成 NSData；测试与其它平台直接返回 bytes。"""
    try:
        from Foundation import NSData

        return NSData.dataWithBytes_length_(data, len(data))
    except Exception:
        return data


class MacClipboardNormalizer:
    """后台监听 NSPasteboard，为图片补一份 Windows 兼容 BMP。"""

    def __init__(self, interval: float = 0.2) -> None:
        self.interval = max(0.05, float(interval))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> bool:
        if platform.system() != "Darwin":
            return False
        if self.running:
            return True
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="quickswitch-clipboard", daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None

    def _run(self) -> None:
        try:
            from AppKit import NSPasteboard
            from objc import autorelease_pool
        except Exception as exc:
            log.warning("macOS 图片剪贴板规范化不可用：%s", exc)
            return

        pasteboard = NSPasteboard.generalPasteboard()
        with autorelease_pool():
            self.normalize_once(pasteboard)
            last_change = int(pasteboard.changeCount())
        while not self._stop.is_set():
            with autorelease_pool():
                try:
                    change = int(pasteboard.changeCount())
                    if change != last_change:
                        last_change = change
                        self.normalize_once(pasteboard)
                except Exception:
                    log.debug("检查 macOS 剪贴板失败", exc_info=True)
            self._stop.wait(self.interval)

    def normalize_once(self, pasteboard: Any = None) -> bool:
        """检查一次粘贴板；写入兼容 BMP 时返回 ``True``。"""
        if pasteboard is None:
            try:
                from AppKit import NSPasteboard

                pasteboard = NSPasteboard.generalPasteboard()
            except Exception:
                return False
        try:
            items = pasteboard.pasteboardItems() or []
            if not items:
                return False
            item = items[0]
            existing = item.dataForType_("com.microsoft.bmp")
            if existing is not None and bmp_is_windows_compatible(bytes(existing)):
                return False

            candidates = []
            for flavor in _IMAGE_TYPES:
                data = item.dataForType_(flavor)
                if data is not None:
                    candidates.append(bytes(data))

            if not candidates:
                path = _file_url_to_path(item.stringForType_("public.file-url"))
                if path is not None:
                    try:
                        candidates.append(path.read_bytes())
                    except OSError as exc:
                        log.debug("读取剪贴板图片文件失败：%s", exc)

            for data in candidates:
                bmp = image_to_windows_bmp(data)
                if bmp is None:
                    continue
                if item.setData_forType_(_as_nsdata(bmp), "com.microsoft.bmp"):
                    log.debug("剪贴板图片已转换为 Windows 兼容 BMP（%d 字节）", len(bmp))
                    return True
        except Exception:
            log.debug("规范化 macOS 剪贴板图片失败", exc_info=True)
        return False
