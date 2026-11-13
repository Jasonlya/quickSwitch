"""Transport tests use paired in-memory peers, including the real JSON wire encoding."""
import asyncio
import base64
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from clipboard_sync import CHUNK, ClipboardSync, pack_files, unpack_files, safe_name
from network import _Auth


class Backend:
    def __init__(self):
        self.sequence = 0
        self.value = None
        self.writes = []

    def token(self):
        return self.sequence

    def read(self):
        return self.value

    def write(self, kind, value):
        self.sequence += 1
        self.value = (kind, value)
        self.writes.append(self.value)


class Peer:
    connected = True
    auth_enabled = False
    authenticated = False
    peer_info = {"clipboard_protocol": 1}

    def __init__(self):
        self.messages = []
        self.other = None

    async def send(self, msg):
        wire = json.dumps(msg).encode()
        assert len(wire) < 65536
        self.messages.append(msg)
        await self.other.handle(json.loads(wire))
        return True


class FileTests(unittest.TestCase):
    def test_folder_and_unicode_files_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "图片与文档"
            (folder / "空目录").mkdir(parents=True)
            (folder / "hello.txt").write_text("你好")
            packed = pack_files([folder], 1024 * 1024)
            received = unpack_files(packed, root / "received", 1024 * 1024)
            self.assertEqual((received[0] / "hello.txt").read_text(), "你好")
            self.assertTrue((received[0] / "空目录").is_dir())

    def test_size_limit_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "file"
            file.write_bytes(b"x" * 200)
            with self.assertRaises(ValueError):
                pack_files([file], 100)
            link = Path(tmp) / "link"
            link.symlink_to(file)
            with self.assertRaises(ValueError):
                pack_files([link], 1000)

    def test_rejects_traversal_reserved_names_and_zip_bomb(self):
        with self.assertRaises(ValueError):
            safe_name("a\\file")
        for name in ("../escape", "/absolute", "a/../../escape", "C:/file", "CON.txt"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w") as z:
                    z.writestr(name, b"x")
                with self.assertRaises(ValueError):
                    unpack_files(output.getvalue(), Path(tmp) / "received", 10000)
        with tempfile.TemporaryDirectory() as tmp:
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("large", b"x" * 20000)
            with self.assertRaises(ValueError):
                unpack_files(output.getvalue(), Path(tmp) / "received", 1000)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a, self.b = Backend(), Backend()
        self.pa, self.pb = Peer(), Peer()
        self.sa = ClipboardSync({"role": "server"}, self.pa, backend=self.a)
        self.sb = ClipboardSync({"role": "client"}, self.pb, backend=self.b, cache_dir=self.tmp.name)
        self.pa.other, self.pb.other = self.sb, self.sa

    async def asyncTearDown(self):
        await self.sa.stop()
        await self.sb.stop()
        self.tmp.cleanup()

    async def test_text_image_and_files_with_chunking_and_ack(self):
        import PIL.Image
        image = io.BytesIO()
        PIL.Image.new("RGB", (30, 30), (255, 0, 0)).save(image, "PNG")
        for kind, data in (("text", json.dumps({"text": "你好" * 30000, "html": "<b>你好</b>"}).encode()),
                           ("image", image.getvalue())):
            self.assertTrue(await self.sa.send(kind, data))
            self.assertEqual(self.b.value, (kind, data))
            self.assertEqual(self.sb.last_token, self.b.token())
        file = Path(self.tmp.name) / "photo.png"
        file.write_bytes(image.getvalue())
        self.assertTrue(await self.sa.send("files", pack_files([file], 1024 * 1024)))
        kind, paths = self.b.value
        self.assertEqual(kind, "files")
        self.assertEqual(paths[0].read_bytes(), image.getvalue())
        self.assertTrue(any(m.get("offset", 0) > 0 for m in self.pa.messages))

    async def begin(self, data=b"hello", **fields):
        msg = {"type": "clipboard_begin", "id": "test", "kind": "text", "size": len(data),
               "sha256": hashlib.sha256(data).hexdigest(), **fields}
        await self.sb.handle(msg)

    async def test_rejects_over_limit_and_bad_chunks(self):
        await self.begin(size=129 * 1024 * 1024)
        self.assertIsNone(self.sb.incoming)
        await self.begin()
        await self.sb.handle({"type": "clipboard_chunk", "id": "test", "offset": 10, "data": "aGVsbG8="})
        self.assertIsNone(self.sb.incoming)
        self.assertEqual(self.b.writes, [])

    async def test_rejects_bad_hash_and_preserves_new_local_copy(self):
        for local_copy in (False, True):
            await self.begin()
            data = b"hello" if local_copy else b"other"
            await self.sb.handle({"type": "clipboard_chunk", "id": "test", "offset": 0,
                                  "data": base64.b64encode(data).decode()})
            if local_copy:
                self.b.write("text", b"new local data")
            before = list(self.b.writes)
            await self.sb.handle({"type": "clipboard_end", "id": "test"})
            self.assertEqual(self.b.writes, before)

    async def test_disabled_and_server_policy(self):
        self.sb.cfg["deskflow"] = {"clipboard_enabled": False}
        await self.begin()
        self.assertIsNone(self.sb.incoming)
        self.sb.cfg["deskflow"] = {"clipboard_size": 128}
        await self.sb.handle({"type": "clipboard_policy", "enabled": True, "size": 32})
        self.assertEqual(self.sb.settings(), (True, 32 * 1024 * 1024))

    async def test_each_clipboard_message_requires_authentication(self):
        auth = _Auth("test-secret")
        async def send(_):
            return True
        for name in ("policy", "begin", "chunk", "end", "ack"):
            self.assertFalse(await auth.absorb({"type": "clipboard_" + name}, send))

    async def test_poller_does_not_echo_received_clipboard(self):
        self.sa.peer_policy = self.sb.peer_policy = {"enabled": True, "size": 16}
        self.a.write("text", b'{"text":"test","html":""}')
        self.sa.start()
        # Let A's single transfer complete before polling B's native clipboard.
        for _ in range(50):
            if self.b.writes:
                break
            await asyncio.sleep(0.02)
        self.sb.start()
        await asyncio.sleep(0.5)
        self.assertEqual(len(self.b.writes), 1)
        self.assertEqual(self.a.writes, [("text", b'{"text":"test","html":""}')])


class PolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_policy_limits_can_expand_again_and_disabled_session_can_recover(self):
        a, b = Backend(), Backend()
        pa, pb = Peer(), Peer()
        sa = ClipboardSync({"role": "server", "deskflow": {"clipboard_size": 128}}, pa, backend=a)
        sb = ClipboardSync({"role": "client", "deskflow": {"clipboard_size": 16}}, pb, backend=b)
        pa.other, pb.other = sb, sa
        try:
            sa.start()
            sb.start()
            await asyncio.sleep(0.5)
            self.assertEqual(sa.settings()[1], 16 * 1024 * 1024)
            sb.cfg["deskflow"]["clipboard_size"] = 64
            sa.cfg["deskflow"]["clipboard_enabled"] = False
            await asyncio.sleep(0.5)
            self.assertFalse(sb.settings()[0])
            sa.cfg["deskflow"]["clipboard_enabled"] = True
            await asyncio.sleep(0.5)
            self.assertTrue(sb.settings()[0])
            self.assertEqual(sa.settings()[1], 64 * 1024 * 1024)
            self.assertEqual(sb.settings()[1], 64 * 1024 * 1024)
        finally:
            await sa.stop()
            await sb.stop()
