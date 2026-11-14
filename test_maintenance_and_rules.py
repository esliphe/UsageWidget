"""Regression tests for database maintenance and rule ownership.

Two things are covered here:

1. ``optimize_database`` must actually shrink the file after rows are deleted.
   It used to run only ``PRAGMA optimize`` plus a WAL checkpoint, so the UI
   reported "优化完成" while the file stayed exactly the same size.
2. Typing-site knowledge must have a single owner. It used to be copy-pasted
   into storage.py (twice, plus a migration list) and monitor.py.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, ".")

from usage_widget import classification, monitor, storage
from usage_widget.storage import Storage


TEST_DB = Path("maintenance-regression.db")


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK' if condition else 'FAIL'}] {name}")
    if not condition:
        raise AssertionError(detail or name)


def fresh_db() -> Storage:
    for suffix in ("", "-wal", "-shm"):
        Path(str(TEST_DB) + suffix).unlink(missing_ok=True)
    return Storage(TEST_DB)


def fill_timeline(store: Storage, rows: int, days_ago: int, payload: str) -> None:
    stamp = datetime.now() - timedelta(days=days_ago)
    events = [
        {
            "start_time": stamp + timedelta(seconds=index),
            "end_time": stamp + timedelta(seconds=index + 1),
            "kind": "window_title",
            "title": f"{payload}-{index}",
            "seconds": 1.0,
            "app_name": "regression.exe",
            "app_path": r"C:\regression.exe",
            "category": "工具",
            "learning_topic": "",
            "extra": payload,
        }
        for index in range(rows)
    ]
    store.insert_timeline_events(events)


def test_optimize_reclaims_space() -> None:
    store = fresh_db()
    try:
        payload = "占位内容" * 400          # ~1.2 KB per row, on purpose
        fill_timeline(store, 4000, days_ago=120, payload=payload)
        size_after_insert = store.database_size_bytes()
        removed = store.cleanup_old_timeline_events(30)
        size_after_delete = store.database_size_bytes()

        check("old timeline rows are deleted", removed == 4000, f"removed={removed}")
        check(
            "deleting rows alone does not shrink the file",
            size_after_delete >= size_after_insert * 0.95,
            f"{size_after_insert} -> {size_after_delete}",
        )

        before, after = store.optimize_database()
        check("optimize reports the size before compaction", before == size_after_delete, f"{before} vs {size_after_delete}")
        check(
            "optimize actually reclaims space",
            after < size_after_delete * 0.6,
            f"{size_after_delete} -> {after}",
        )
        check(
            "database stays queryable after vacuum",
            store.conn.execute("SELECT COUNT(*) FROM timeline_events").fetchone()[0] == 0,
        )
    finally:
        store.close()
        for suffix in ("", "-wal", "-shm"):
            Path(str(TEST_DB) + suffix).unlink(missing_ok=True)


def test_schema_version_is_stamped() -> None:
    store = fresh_db()
    try:
        version = store.conn.execute("PRAGMA user_version").fetchone()[0]
        check("schema version is stamped on startup", version == Storage.SCHEMA_VERSION, f"user_version={version}")

        store.close()
        reopened = Storage(TEST_DB)
        try:
            again = reopened.conn.execute("PRAGMA user_version").fetchone()[0]
            check("reopening keeps the stamped version", again == Storage.SCHEMA_VERSION, f"user_version={again}")
        finally:
            reopened.close()
    finally:
        for suffix in ("", "-wal", "-shm"):
            Path(str(TEST_DB) + suffix).unlink(missing_ok=True)


def test_typing_rules_have_one_owner() -> None:
    check(
        "default rules are generated from the shared constants",
        all(
            (domain, "打字", "domain") in storage.DEFAULT_CATEGORY_RULES
            for domain in classification.TYPING_DOMAINS
        ),
    )
    check(
        "no typing site is hardcoded in storage.py",
        "dazidazi" not in Path("usage_widget/storage.py").read_text(encoding="utf-8").lower(),
    )
    check(
        "no typing site is hardcoded in monitor.py",
        "dazidazi" not in Path("usage_widget/monitor.py").read_text(encoding="utf-8").lower(),
    )
    check(
        "monitor reads the shared hint tuple",
        monitor.TYPING_CONTEXT_HINTS is classification.TYPING_CONTEXT_HINTS,
    )


def test_network_helpers_are_shared() -> None:
    netlookup = Path("usage_widget/netlookup.py")
    check("netlookup module exists", netlookup.exists())
    for module in ("usage_widget/learning.py", "usage_widget/online_category.py"):
        source = Path(module).read_text(encoding="utf-8")
        check(f"{module} delegates fetching", "urllib.request" not in source)
        check(f"{module} reuses the shared challenge detector", "staticmethod(is_access_challenge)" in source)


def main() -> None:
    test_optimize_reclaims_space()
    test_schema_version_is_stamped()
    test_typing_rules_have_one_owner()
    test_network_helpers_are_shared()
    print("all maintenance and rule ownership tests passed")


if __name__ == "__main__":
    main()
