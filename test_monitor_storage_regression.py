from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import usage_widget.monitor as monitor_module
from usage_widget.media import MediaItem
from usage_widget.monitor import ProcessMonitor
from usage_widget.storage import Storage


class BrokenBridge:
    def audible_tabs(self):
        raise RuntimeError("audible bridge failed")

    def latest(self):
        raise RuntimeError("latest bridge failed")


class FakeProc:
    def __init__(self, pid: int, name: str, exe_path: str) -> None:
        self.info = {"pid": pid, "name": name}
        self._exe_path = exe_path

    def exe(self) -> str:
        return self._exe_path


class FakeBridge:
    def __init__(self, latest_tab) -> None:
        self.latest_tab = latest_tab

    def audible_tabs(self) -> list:
        return []

    def latest(self, max_age_seconds: float = 10.0):
        return self.latest_tab


class FakeMediaProvider:
    consecutive_errors = 0

    def refresh_sync(self, timeout_seconds: float = 0.8) -> list[MediaItem]:
        return [MediaItem(source="chrome.exe", title="Song A", artist="Artist A", is_playing=True)]

    def current_items(self) -> list[MediaItem]:
        return []


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

        typing_title = "在线打字练习"
        typing_tab = SimpleNamespace(
            title=typing_title,
            url="https://dazidazi.com",
            domain="dazidazi.com",
            h1="",
            description="",
            muted=False,
            has_video=True,
            has_audio=True,
            media_state="playing",
        )
        original_process_iter = monitor_module.psutil.process_iter
        original_foreground_window_info = monitor_module.foreground_window_info
        original_idle_seconds = monitor_module.idle_seconds
        try:
            monitor_module.psutil.process_iter = lambda _attrs: [
                FakeProc(10, "Code.exe", "C:/Apps/Code.exe"),
                FakeProc(20, "chrome.exe", "C:/Apps/chrome.exe"),
            ]
            monitor_module.foreground_window_info = lambda: SimpleNamespace(pid=10, title="notes")
            monitor_module.idle_seconds = lambda: 0.0
            monitor.browser_bridge = FakeBridge(typing_tab)  # type: ignore[assignment]
            monitor.media_provider = FakeMediaProvider()  # type: ignore[assignment]
            monitor._last_sample = datetime.now() - timedelta(seconds=5)
            monitor.sample(write=True)
            content_row = storage.conn.execute(
                """
                SELECT kind, content_title, content_domain, category
                FROM content_usage_daily
                WHERE attention_seconds > 0
                ORDER BY rowid DESC
                LIMIT 1
                """
            ).fetchone()
            check("non-browser foreground does not borrow stale browser tab", content_row["kind"] == "window_title", repr(dict(content_row)))
            check("non-browser foreground keeps own title", content_row["content_title"] == "notes", repr(dict(content_row)))
            check("non-browser foreground is not typing category", content_row["category"] != "打字", repr(dict(content_row)))

            storage.conn.execute("DELETE FROM content_usage_daily")
            storage.conn.execute("DELETE FROM timeline_events")
            storage.conn.commit()
            monitor_module.foreground_window_info = lambda: SimpleNamespace(pid=20, title=f"{typing_title} - Google Chrome")
            monitor._last_sample = datetime.now() - timedelta(seconds=5)
            monitor.sample(write=True)
            fg_row = storage.conn.execute(
                """
                SELECT kind, content_title, content_domain, category
                FROM content_usage_daily
                WHERE attention_seconds > 0
                ORDER BY rowid DESC
                LIMIT 1
                """
            ).fetchone()
            check("browser foreground uses active typing tab", fg_row["kind"] == "web_page", repr(dict(fg_row)))
            check("browser foreground typing domain is preserved", fg_row["content_domain"] == "dazidazi.com", repr(dict(fg_row)))
            check("browser foreground typing category is typing", fg_row["category"] == "打字", repr(dict(fg_row)))
        finally:
            monitor_module.psutil.process_iter = original_process_iter
            monitor_module.foreground_window_info = original_foreground_window_info
            monitor_module.idle_seconds = original_idle_seconds
    finally:
        storage.close()
        for suffix in ("", "-shm", "-wal"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)

    print("all monitor/storage regression tests passed")


if __name__ == "__main__":
    main()
