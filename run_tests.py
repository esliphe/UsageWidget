"""Run the whole regression suite with one command.

The suite predates pytest: every ``test_*.py`` is a standalone script that
prints ``[OK]`` / ``[FAIL]`` lines and exits non-zero on the first failure.
That works fine by hand, but it means there is no single command a CI job (or a
release checklist) can call. This runner is that command.

    python run_tests.py             # offline suites only
    python run_tests.py --online    # also run suites that hit live endpoints

Exit code is 0 only when every selected suite passes.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


# Hits Baidu / DuckDuckGo / Wikipedia for real. Kept out of the default run so
# a release build does not fail because of someone else's rate limit.
NETWORK_SUITES = {"test_online_apis.py"}

ROOT = Path(__file__).resolve().parent


def discover(include_network: bool) -> list[Path]:
    suites = sorted(ROOT.glob("test_*.py"))
    if not include_network:
        suites = [path for path in suites if path.name not in NETWORK_SUITES]
    return suites


def run_suite(path: Path) -> tuple[bool, str]:
    completed = subprocess.run(
        [sys.executable, str(path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the UsageWidget regression suite.")
    parser.add_argument(
        "--online",
        action="store_true",
        help="include suites that require live network access",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print the full output of every suite",
    )
    args = parser.parse_args()

    suites = discover(args.online)
    if not suites:
        print("no test suites found")
        return 1

    failures: list[tuple[str, str]] = []
    for path in suites:
        ok, output = run_suite(path)
        tail = [line for line in output.strip().splitlines() if line.strip()]
        print(f"[{'PASS' if ok else 'FAIL'}] {path.name}")
        if args.verbose or not ok:
            for line in tail:
                print(f"    {line}")
        if not ok:
            failures.append((path.name, output))

    total = len(suites)
    passed = total - len(failures)
    print(f"\n{passed}/{total} suites passed")
    if failures:
        print("failed suites: " + ", ".join(name for name, _ in failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
