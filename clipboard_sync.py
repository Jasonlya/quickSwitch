"""Bounded, chunked clipboard transport over QuickSwitch's existing peer connection.

No dependence on Deskflow focus changes. Both peers must advertise protocol 1.
Received files live in clipboard-cache, so Finder/Explorer paste actual files.
"""
from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import logging
from pathlib import Path, PurePosixPath
import shutil
import time
import uuid
import zipfile

from clipboard_native import native_clipboard

log = logging.getLogger("clipboard")
CHUNK = 24 * 1024  # Base64 + JSON stays below asyncio's 64 KiB line limit.
MAX_ENTRIES = 4096


def safe_name(name):
    parts = PurePosixPath(name).parts
    if not parts or name.startswith("/") or "\\" in name:
        raise ValueError("无效文件路径")
    for part in parts:
        if part in (".", "..") or any(c in part for c in '\0:<>"|?*') or part.endswith((" ", ".")):
            raise ValueError("文件名不能跨平台使用")
        if part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
            raise ValueError("Windows 保留文件名")
    return parts


def pack_files(paths, limit):
    output = io.BytesIO()
    total = 0
    count = 0
    seen = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for root in paths:
            root = Path(root)
            if root.name.casefold() in seen:
                raise ValueError("复制的文件存在重名")
            seen.add(root.name.casefold())
            for path in [root, *(sorted(root.rglob("*")) if root.is_dir() else [])]:
                if path.is_symlink() or not (path.is_file() or path.is_dir()):
                    raise ValueError("不支持符号链接或特殊文件")
                name = root.name if path == root else root.name + "/" + path.relative_to(root).as_posix()
                safe_name(name)
                count += 1
                total += path.stat().st_size if path.is_file() else 0
                if count > MAX_ENTRIES or total > limit:
                    raise ValueError("文件数量或大小超过剪贴板上限")
                if path.is_dir():
                    archive.writestr(name + "/", b"")
                else:
                    # Bound actual reads as well as stat sizes (files can grow).
                    with path.open("rb") as source, archive.open(name, "w") as target:
                        while True:
                            block = source.read(min(CHUNK, max(1, limit - output.tell() + 1)))
                            if not block:
                                break
                            if output.tell() + len(block) > limit:
                                raise ValueError("文件传输大小超过剪贴板上限")
                            target.write(block)
                if output.tell() > limit:
                    raise ValueError("文件传输大小超过剪贴板上限")
    return output.getvalue()


def unpack_files(data, destination, limit):
    destination = Path(destination)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_ENTRIES or sum(e.file_size for e in entries) > limit:
            raise ValueError("文件数量或解压大小超过上限")
        seen = set()
        roots = []
        for entry in entries:
            parts = safe_name(entry.filename.rstrip("/"))
            key = "/".join(parts).casefold()
            if key in seen or ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("压缩包包含重名或符号链接")
            seen.add(key)
            if parts[0] not in roots:
                roots.append(parts[0])
        destination.mkdir(parents=True, exist_ok=False)
        try:
            for entry in entries:
                path = destination.joinpath(*safe_name(entry.filename.rstrip("/")))
                if entry.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as source, path.open("xb") as target:
                        shutil.copyfileobj(source, target)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return [destination / name for name in roots]


class ClipboardSync:
    def __init__(self, cfg, peer, *, cache_dir=None, backend=None):
        self.cfg, self.peer = cfg, peer
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".quickswitch" / "clipboard-cache"
        self.backend = backend
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="quickswitch-clipboard")
        self.task = None
        self.last_token = None
        self.incoming = None
        self.pending = {}
        self.policy = None
        self.peer_policy = None
        self.last_error = ""

    async def native(self, method, *args):
        loop = asyncio.get_running_loop()
        def call():
            # PyObjC objects created on a worker must have an autorelease pool.
            import contextlib
            try:
                from objc import autorelease_pool
                pool = autorelease_pool()
            except ImportError:
                pool = contextlib.nullcontext()
            with pool:
                if self.backend is None:
                    self.backend = native_clipboard()
                if method == "apply":
                    token, kind, data = args
                    if self.backend.token() != token:
                        raise ValueError("本机已经复制了新内容，跳过旧传输")
                    self.backend.write(kind, data)
                    return self.backend.token()
                return getattr(self.backend, method)(*args)
        return await loop.run_in_executor(self.executor, call)

    def local_settings(self):
        section = self.cfg.get("deskflow") or {}
        return (bool(section.get("clipboard_enabled", True)),
                max(1, min(128, int(section.get("clipboard_size", 16)))) * 1024 * 1024)

    def settings(self):
        enabled, limit = self.local_settings()
        if self.peer_policy:
            enabled = enabled and bool(self.peer_policy.get("enabled"))
            limit = min(limit, max(1, min(128, int(self.peer_policy.get("size", 16)))) * 1024 * 1024)
        return enabled, limit

    def start(self):
        self.task = asyncio.create_task(self.run(), name="clipboard-sync")

    async def stop(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.backend and hasattr(self.backend, "close"):
            await self.native("close")
        self.executor.shutdown(wait=True)
        self.incoming = None

    async def run(self):
        while True:
            try:
                if not self.peer.connected or self.peer.peer_info.get("clipboard_protocol") != 1:
                    self.policy = None
                    self.peer_policy = None
                    await asyncio.sleep(0.3)
                    continue
                if self.peer.auth_enabled and not self.peer.authenticated:
                    await asyncio.sleep(0.3)
                    continue
                enabled, limit = self.settings()
                policy = self.local_settings()
                if self.policy != policy:
                    if await self.peer.send({"type": "clipboard_policy", "enabled": policy[0], "size": policy[1] // (1024 * 1024)}):
                        self.policy = policy
                if enabled and self.peer_policy and self.peer_policy.get("enabled"):
                    token = await self.native("token")
                    if token != self.last_token:
                        value = await self.native("read")
                        # Reading delayed data may race another local copy.
                        if token == await self.native("token"):
                            if value:
                                kind, data = value
                                if kind == "files":
                                    data = await asyncio.to_thread(pack_files, data, limit)
                                if len(data) > limit:
                                    raise ValueError("复制内容超过剪贴板大小上限")
                                if await self.send(kind, data):
                                    if token == await self.native("token"):
                                        self.last_token = token
                                else:
                                    await asyncio.sleep(1)
                            else:
                                self.last_token = token
                if self.incoming and time.monotonic() - self.incoming["at"] > 30:
                    self.incoming = None
                self.last_error = ""
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if str(exc) != self.last_error:
                    log.warning("剪贴板同步失败：%s", exc)
                    self.last_error = str(exc)
                await asyncio.sleep(1)
            await asyncio.sleep(0.2)

    async def send(self, kind, data):
        transfer = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending[transfer] = future
        try:
            if not await self.peer.send({"type": "clipboard_begin", "id": transfer, "kind": kind,
                                         "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}):
                return False
            for offset in range(0, len(data), CHUNK):
                if not self.settings()[0]:
                    return False
                if not await self.peer.send({"type": "clipboard_chunk", "id": transfer, "offset": offset,
                                             "data": base64.b64encode(data[offset:offset + CHUNK]).decode("ascii")}):
                    return False
                await asyncio.sleep(0)  # Let switch commands and heartbeats through.
            if not await self.peer.send({"type": "clipboard_end", "id": transfer}):
                return False
            return bool(await asyncio.wait_for(future, 15))
        finally:
            self.pending.pop(transfer, None)

    async def handle(self, msg):
        kind = msg.get("type")
        if kind == "clipboard_policy":
            self.peer_policy = {"enabled": bool(msg.get("enabled")), "size": max(1, min(128, int(msg.get("size", 16))))}
            return
        if kind == "clipboard_ack":
            future = self.pending.get(msg.get("id"))
            if future and not future.done():
                future.set_result(bool(msg.get("ok")))
            return
        enabled, limit = self.settings()
        if not enabled:
            self.incoming = None
            return
        transfer = str(msg.get("id", ""))
        if kind == "clipboard_begin":
            size = msg.get("size")
            if not isinstance(size, int) or not 0 <= size <= limit or msg.get("kind") not in ("files", "image", "text"):
                return
            self.incoming = {"id": transfer, "kind": msg["kind"], "size": size, "hash": msg.get("sha256"),
                             "data": bytearray(), "at": time.monotonic(), "token": await self.native("token")}
            return
        incoming = self.incoming
        if not incoming or incoming["id"] != transfer:
            return
        try:
            if kind == "clipboard_chunk":
                data = base64.b64decode(msg.get("data", ""), validate=True)
                if len(data) > CHUNK or msg.get("offset") != len(incoming["data"]) or len(incoming["data"]) + len(data) > min(limit, incoming["size"]):
                    raise ValueError("剪贴板分块顺序或大小无效")
                incoming["data"].extend(data)
                incoming["at"] = time.monotonic()
            elif kind == "clipboard_end":
                self.incoming = None
                data = bytes(incoming["data"])
                if len(data) != incoming["size"] or hashlib.sha256(data).hexdigest() != incoming["hash"]:
                    raise ValueError("剪贴板校验失败")
                if await self.native("token") != incoming["token"]:
                    raise ValueError("本机已经复制了新内容，跳过旧传输")
                if incoming["kind"] == "files":
                    data = await asyncio.to_thread(unpack_files, data, self.cache_dir / uuid.uuid4().hex, limit)
                # Check again after disk I/O; never overwrite a newer local copy.
                if await self.native("token") != incoming["token"]:
                    return
                self.last_token = await self.native("apply", incoming["token"], incoming["kind"], data)
                await self.peer.send({"type": "clipboard_ack", "id": transfer, "ok": True})
                log.info("剪贴板已接收：%s（%d 字节）", incoming["kind"], incoming["size"])
        except Exception as exc:
            self.incoming = None
            log.warning("接收剪贴板失败：%s", exc)
            await self.peer.send({"type": "clipboard_ack", "id": transfer, "ok": False})
