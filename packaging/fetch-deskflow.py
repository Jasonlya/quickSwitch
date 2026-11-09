#!/usr/bin/env python3
"""下载并准备随 QuickSwitch 分发的官方 Deskflow 二进制。

用户只需要安装 QuickSwitch，不再单独下载 Deskflow。构建机在打包前运行本脚本：

    python packaging/fetch-deskflow.py --target macos-arm64
    python packaging/fetch-deskflow.py --target windows-x64

下载地址固定到 Deskflow v1.27.0，并校验上游 SHA256；不会把大型二进制提交进
Git 仓库。Deskflow 使用 GPL-2.0，详见仓库根目录 THIRD_PARTY_NOTICES.md。
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, Optional, Tuple

VERSION = "1.27.0"
RELEASE_URL = f"https://github.com/deskflow/deskflow/releases/download/v{VERSION}"
SOURCE_URL = f"https://github.com/deskflow/deskflow/tree/v{VERSION}"

ASSETS: Dict[str, Tuple[str, str]] = {
    "macos-arm64": (
        f"deskflow-{VERSION}-macos-arm64.dmg",
        "dd21e79e566314394214906d3338c505d337af536fc580c022ee3fadffad0c97",
    ),
    "windows-x64": (
        f"deskflow-{VERSION}-win-x64-portable.zip",
        "8d19004cc3625623489d96580c1b58fd13ee78185689907fd4478595f93fab9a",
    ),
}

# GitHub Release 的直链在共享 CI IP 上偶尔会被限流/超时。带 GITHUB_TOKEN
# 调用资产 API 可以走已认证额度，失败时再回退到普通下载地址。
ASSET_IDS: Dict[str, int] = {
    "macos-arm64": 603209747,
    "windows-x64": 603209735,
}


def current_target() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin" and machine in ("arm64", "aarch64"):
        return "macos-arm64"
    if system == "Windows" and machine in ("amd64", "x86_64"):
        return "windows-x64"
    raise SystemExit(f"不支持的构建平台：{system} {machine}（只支持 macOS arm64 / Windows x64）")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_once(url: str, destination: Path, headers: Dict[str, str]) -> None:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)


def download(url: str, destination: Path, asset_id: Optional[int] = None) -> None:
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    candidates = []
    if token and asset_id is not None:
        candidates.append(
            (
                f"https://api.github.com/repos/deskflow/deskflow/releases/assets/{asset_id}",
                {
                    "Accept": "application/octet-stream",
                    "Authorization": f"Bearer {token}",
                },
            )
        )
    candidates.append((url, {}))

    errors = []
    for candidate, extra_headers in candidates:
        headers = {"User-Agent": "QuickSwitch-build", **extra_headers}
        for attempt in range(1, 3):
            try:
                print(f"  下载 {candidate}（第 {attempt}/2 次）")
                _download_once(candidate, destination, headers)
                return
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
                print(f"  下载失败：{exc}")
                if attempt < 2:
                    time.sleep(attempt * 2)

    raise RuntimeError("Deskflow 下载失败：" + "；".join(errors[-4:]))


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if root not in target.parents and target != root:
            raise RuntimeError(f"不安全的压缩包路径：{member.filename}")
    archive.extractall(destination)


def copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True)


def prepare_windows(archive: Path, target: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="quickswitch-deskflow-") as tmp:
        extracted = Path(tmp)
        with zipfile.ZipFile(archive) as bundle:
            safe_extract(bundle, extracted)
        roots = [path for path in extracted.iterdir() if path.is_dir()]
        source = roots[0] if roots else extracted
        executable = source / "deskflow.exe"
        if not executable.is_file():
            executable = source / "Deskflow.exe"
        if not executable.is_file():
            raise RuntimeError("Windows 便携包中找不到 deskflow.exe")
        copy_tree(source, target)


def prepare_macos(archive: Path, target: Path) -> None:
    if sys.platform != "darwin":
        raise RuntimeError("macOS Deskflow 只能在 macOS 构建机上准备")
    with tempfile.TemporaryDirectory(prefix="quickswitch-deskflow-") as tmp:
        mount = Path(tmp) / "mnt"
        mount.mkdir()
        attach = subprocess.run(
            [
                "hdiutil", "attach", "-nobrowse", "-readonly",
                "-mountpoint", str(mount), str(archive),
            ],
            input="Y\n",
            text=True,
            capture_output=True,
            timeout=120,
        )
        if attach.returncode != 0:
            detail = (attach.stderr or attach.stdout or "").strip()
            raise RuntimeError(f"挂载 Deskflow DMG 失败：{detail[-800:]}")
        try:
            source = mount / "Deskflow.app"
            if not source.is_dir():
                raise RuntimeError("Deskflow DMG 中找不到 Deskflow.app")
            subprocess.run(["ditto", str(source), str(target / "Deskflow.app")], check=True)
        finally:
            subprocess.run(
                ["hdiutil", "detach", str(mount), "-quiet"],
                capture_output=True,
                timeout=60,
            )

    verify = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(target / "Deskflow.app")],
        capture_output=True,
        text=True,
    )
    if verify.returncode != 0:
        detail = (verify.stderr or verify.stdout or "").strip()
        raise RuntimeError(f"内置 Deskflow.app 签名校验失败：{detail}")


def write_metadata(target: Path) -> None:
    (target / "VERSION").write_text(VERSION + "\n", encoding="utf-8")
    (target / "DESKFLOW-NOTICE.txt").write_text(
        "\n".join(
            [
                f"Deskflow {VERSION}",
                "License: GNU General Public License v2.0 (GPL-2.0)",
                f"Source: {SOURCE_URL}",
                f"Release: {RELEASE_URL}",
                "This is an unmodified official upstream build bundled with QuickSwitch.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def prepare(target_name: str, output: Path, *, if_missing: bool) -> Path:
    filename, expected = ASSETS[target_name]
    target = output / target_name
    marker = target / "VERSION"
    if if_missing and marker.is_file() and marker.read_text(encoding="utf-8").strip() == VERSION:
        print(f"  已准备 Deskflow {VERSION}：{target}")
        return target

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="quickswitch-download-") as tmp:
        archive = Path(tmp) / filename
        download(f"{RELEASE_URL}/{filename}", archive, ASSET_IDS.get(target_name))
        actual = sha256(archive)
        if actual != expected:
            raise RuntimeError(f"{filename} SHA256 不匹配：期望 {expected}，实际 {actual}")
        print(f"  SHA256 校验通过：{actual}")
        if target_name == "windows-x64":
            prepare_windows(archive, target)
        else:
            prepare_macos(archive, target)

    write_metadata(target)
    print(f"  已准备 Deskflow {VERSION}：{target}")
    return target


def main(argv: Optional[list] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="下载 QuickSwitch 内置 Deskflow")
    parser.add_argument("--target", choices=sorted(ASSETS), default=None,
                        help="目标平台；默认按当前构建机判断")
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent / "vendor" / "deskflow"),
                        help="输出目录（默认 packaging/vendor/deskflow）")
    parser.add_argument("--if-missing", action="store_true", help="同版本已存在时跳过下载")
    parser.add_argument("--print-version", action="store_true", help="只输出固定版本号")
    parser.add_argument("--print-source-url", action="store_true", help="只输出对应源码地址")
    args = parser.parse_args(argv)

    if args.print_version:
        print(VERSION)
        return 0
    if args.print_source_url:
        print(SOURCE_URL)
        return 0

    target = args.target or current_target()
    prepare(target, Path(args.output).expanduser().resolve(), if_missing=args.if_missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
