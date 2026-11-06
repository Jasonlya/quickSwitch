"""Windows 安装器必须按 UTF-8 编译，否则中文页面会乱码。"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallerEncodingTests(unittest.TestCase):
    def test_installer_script_has_utf8_bom(self) -> None:
        data = (ROOT / "packaging" / "installer.nsi").read_bytes()
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))

    def test_release_build_passes_utf8_input_charset(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("-INPUTCHARSET UTF8", workflow)


if __name__ == "__main__":
    unittest.main()
