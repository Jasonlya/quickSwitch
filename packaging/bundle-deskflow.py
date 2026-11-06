#!/usr/bin/env python3
"""把已校验的官方 Deskflow.app 原样嵌入 macOS QuickSwitch.app。

必须在 PyInstaller 完成之后运行。不能把 Deskflow.app 放进 PyInstaller 的 datas，
否则 PyInstaller 会把嵌套 App 当成自己的二进制继续分析，破坏 Qt framework 软链。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def run(command: list, *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=check, capture_output=True, text=True)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="嵌入 Deskflow.app 到 QuickSwitch.app")
    parser.add_argument("--app", required=True, help="dist/QuickSwitch.app")
    parser.add_argument(
        "--source",
        default=str(Path(__file__).resolve().parent / "vendor" / "deskflow" / "macos-arm64" / "Deskflow.app"),
        help="官方 Deskflow.app 路径",
    )
    args = parser.parse_args(argv)

    app = Path(args.app).resolve()
    source = Path(args.source).resolve()
    if not (app / "Contents" / "MacOS" / "QuickSwitch").is_file():
        raise SystemExit(f"不是有效的 QuickSwitch.app：{app}")
    if not (source / "Contents" / "MacOS" / "Deskflow").is_file():
        raise SystemExit(f"缺少 Deskflow.app：{source}")

    destination = app / "Contents" / "Resources" / "deskflow"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    run(["ditto", str(source), str(destination / "Deskflow.app")])

    nested = destination / "Deskflow.app"
    verify_nested = run(["codesign", "--verify", "--deep", "--strict", str(nested)], check=False)
    if verify_nested.returncode != 0:
        raise SystemExit(f"内置 Deskflow 签名无效：{verify_nested.stderr or verify_nested.stdout}")

    # 复制资源后 QuickSwitch 的外层签名会失效；先做 ad-hoc 签名。
    # 正式构建脚本随后会再用 Developer ID 签一次并公证。
    run(["codesign", "--force", "--sign", "-", str(app)])
    verify_app = run(["codesign", "--verify", "--deep", "--strict", str(app)], check=False)
    if verify_app.returncode != 0:
        raise SystemExit(f"QuickSwitch.app 重签失败：{verify_app.stderr or verify_app.stdout}")

    print(f"已嵌入 Deskflow：{nested}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
