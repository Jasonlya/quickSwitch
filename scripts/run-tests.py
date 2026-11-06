#!/usr/bin/env python3
"""逐个运行 unittest 用例，避免单个用例卡死拖住整个 CI 任务。"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def iter_test_ids(suite: unittest.TestSuite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from iter_test_ids(test)
        else:
            yield test.id()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=60.0, help="单条用例超时秒数")
    parser.add_argument("--max-timeouts", type=int, default=3, help="出现多少次超时后停止")
    args = parser.parse_args()

    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    ids = list(iter_test_ids(suite))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    failures = 0
    timeouts = 0

    for index, test_id in enumerate(ids, 1):
        started = time.monotonic()
        command = [sys.executable, "-m", "unittest", "-v", test_id]
        try:
            completed = subprocess.run(
                command,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=args.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            timeouts += 1
            failures += 1
            output = (exc.stdout or "") + (exc.stderr or "")
            print("\n" + "=" * 70, flush=True)
            print(f"ERROR: TIMEOUT {test_id}", flush=True)
            print("-" * 70, flush=True)
            print(f"超过 {args.timeout:g}s 未结束", flush=True)
            if output:
                print(output[-4000:], flush=True)
            if timeouts >= args.max_timeouts:
                print(f"达到 {args.max_timeouts} 次超时，停止继续运行。", flush=True)
                break
            continue

        elapsed = time.monotonic() - started
        if completed.returncode != 0:
            failures += 1
            print("\n" + "=" * 70, flush=True)
            print(f"FAIL: {test_id} ({elapsed:.2f}s)", flush=True)
            print("-" * 70, flush=True)
            print((completed.stdout or "") + (completed.stderr or ""), flush=True)
        elif index % 25 == 0 or index == len(ids):
            print(f"进度：{index}/{len(ids)}（{elapsed:.2f}s）", flush=True)

    print(f"\nRan {len(ids)} tests: {failures} failed, {timeouts} timed out", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
