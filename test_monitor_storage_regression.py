from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from usage_widget.monitor import ProcessMonitor
from usage_widget.storage import Storage


class BrokenBridge:
    def audible_tabs(self):
        raise RuntimeError("audible bridge failed")

    def latest(self):
        raise RuntimeError("latest bridge failed")


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        raise AssertionError(detail or name)


def main() -> None:
    db_path = Path("monitor-storage-regression.db")
    for suffix in ("", "-shm", "-wal"):
        Path(str(db_path) + suffix).unlink(missing_ok=True)

    storage = Storage(db_path)
    monitor = ProcessMonitor(storage)
    try:
        journal_mode = storage.conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = storage.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        check("sqlite uses WAL", str(journal_mode).lower() == "wal", str(journal_mode))
        check("sqlite busy timeout enabled", int(busy_timeout) >= 3000, str(busy_timeout))

        now = datetime(2026, 1, 1, 12, 0, 0)
        check("warmup sample has zero delta", monitor._sample_delta(now, write=False) == 0.0)
        monitor._last_sample = None
        check("first write sample has zero delta", monitor._sample_delta(now, write=True) == 0.0)
        check(
            "normal delta is preserved",
            abs(monitor._sample_delta(now + timedelta(seconds=42), write=True) - 42.0) < 0.001,
        )
        check(
            "long resume delta is not truncated to five seconds",
            monitor._sample_delta(now + timedelta(seconds=42 + 3600), write=True) == monitor.MAX_SAMPLE_DELTA_SECONDS,
        )

        monitor._sampling = True
        monitor.sample(write=False)
        check("sampling reentry guard keeps active sample state", monitor._sampling is True)
        monitor._sampling = False

        monitor.browser_bridge = BrokenBridge()  # type: ignore[assignment]
        settings = storage.load_settings()
        check("broken latest browser bridge is contained", monitor._latest_browser_tab(settings) is None)

        storage.record_activity(
            [
                {
                    "exe_name": "chrome.exe",
                    "exe_path": "C:/Chrome/chrome.exe",
                    "running_seconds": 10.0,
                    "foreground_seconds": 10.0,
                }
            ],
            [],
            [],
            now,
        )
        row = storage.conn.execute(
            "SELECT running_seconds, foreground_seconds FROM usage_daily WHERE exe_path = ?",
            ("C:/Chrome/chrome.exe",),
        ).fetchone()
        check("running seconds are stored once per grouped process", float(row["running_seconds"]) == 10.0, repr(dict(row)))
    finally:
        storage.close()
        for suffix in ("", "-shm", "-wal"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)

    print("all monitor/storage regression tests passed")


if __name__ == "__main__":
    main()
