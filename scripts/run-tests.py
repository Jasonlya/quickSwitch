#!/usr/bin/env python3
"""逐个运行 unittest 用例，避免单个用例卡死拖住整个 CI 任务。"""
from __future__ import annotations

import argparse
import contextlib
import os
import signal
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


def child_process_options():
    """让测试子进程拥有独立进程组，超时后可连同其子进程一起终止。"""
    if os.name == "posix":
        return {"start_new_session": True}
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": flags} if flags else {}
    return {}


def terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
    elif os.name == "nt":
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
            )
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        process.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=5)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")

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
        print(f"[{index}/{len(ids)}] {test_id}", flush=True)
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            **child_process_options(),
        )
        try:
            stdout, stderr = process.communicate(timeout=args.timeout)
            returncode = process.returncode
        except subprocess.TimeoutExpired as exc:
            terminate_process_tree(process)
            stdout, stderr = process.communicate()
            timeouts += 1
            failures += 1
            output = str(exc.stdout or "") + str(exc.stderr or "") + (stdout or "") + (stderr or "")
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
        if returncode != 0:
            failures += 1
            print("\n" + "=" * 70, flush=True)
            print(f"FAIL: {test_id} ({elapsed:.2f}s)", flush=True)
            print("-" * 70, flush=True)
            print((stdout or "") + (stderr or ""), flush=True)
        elif index % 25 == 0 or index == len(ids):
            print(f"进度：{index}/{len(ids)}（{elapsed:.2f}s）", flush=True)

    print(f"\nRan {len(ids)} tests: {failures} failed, {timeouts} timed out", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
