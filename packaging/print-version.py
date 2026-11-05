#!/usr/bin/env python3
"""打印 main.py 里的 VERSION（打包脚本与 CI 共用，避免版本号漂移）。"""
import pathlib
import re

root = pathlib.Path(__file__).resolve().parent.parent
text = (root / "main.py").read_text(encoding="utf-8")
match = re.search(r'^VERSION\s*=\s*"([^"]+)"', text, re.M)
if not match:
    raise SystemExit("读不到 main.py 里的 VERSION")
print(match.group(1))
