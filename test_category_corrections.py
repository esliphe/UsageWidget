from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import time

from usage_widget.storage import Storage


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        raise AssertionError(detail or name)


def fresh_storage() -> tuple[Storage, tempfile.TemporaryDirectory[str]]:
    temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(temp_dir.name) / f"category-corrections-{time.time_ns()}.db"
    return Storage(db_path), temp_dir


def main() -> None:
    storage, temp_dir = fresh_storage()
    try:
        title = "大学物理 光学 课程"
        check("default learning rule applies", storage.category_for("chrome.exe", "bilibili.com", title) == "学习")
        storage.add_category_rule("bilibili.com", "娱乐", "domain", update_existing=False, source="user")
        check(
            "user domain correction beats default title rule",
            storage.category_for("chrome.exe", "bilibili.com", title) == "娱乐",
            storage.category_explanation("娱乐", "chrome.exe", "bilibili.com", title),
        )
        storage.add_category_rule("chrome.exe", "办公", "app", update_existing=False, source="user")
        check(
            "more specific user domain beats user app rule",
            storage.category_for("chrome.exe", "bilibili.com", title) == "娱乐",
            storage.category_explanation("娱乐", "chrome.exe", "bilibili.com", title),
        )
    finally:
        storage.close()
        temp_dir.cleanup()

    storage, temp_dir = fresh_storage()
    try:
        storage.add_category_rule("example", "办公", "domain", update_existing=False, source="user")
        storage.add_category_rule("example", "学习", "title", update_existing=False, source="user")
        rows = [(str(row["pattern"]), str(row["target"]), str(row["category"])) for row in storage.category_rules()]
        check("same keyword can exist for different targets", ("example", "domain", "办公") in rows and ("example", "title", "学习") in rows, repr(rows))
    finally:
        storage.close()
        temp_dir.cleanup()

    storage, temp_dir = fresh_storage()
    try:
        when = datetime(2026, 1, 2, 12, 0, 0)
        storage.increment_content_usage(
            [
                {
                    "kind": "video_playback",
                    "exe_name": "browser-extension",
                    "exe_path": "browser-extension",
                    "content_key": "video:https://bilibili.com/video/abc",
                    "content_title": "大学物理 光学 课程",
                    "content_url": "https://bilibili.com/video/abc",
                    "content_domain": "bilibili.com",
                    "category": "学习",
                    "learning_topic": "物理",
                    "attention_seconds": 0.0,
                    "background_seconds": 600.0,
                }
            ],
            when,
        )
        storage.insert_timeline_events(
            [
                {
                    "start_time": when,
                    "end_time": when,
                    "kind": "video_playback",
                    "title": "大学物理 光学 课程",
                    "app_name": "browser-extension",
                    "app_path": "browser-extension",
                    "category": "学习",
                    "learning_topic": "物理",
                    "seconds": 600.0,
                    "extra": "https://bilibili.com/video/abc",
                }
            ]
        )
        before = storage.overview_metrics_range(when.date(), when.date())
        check("learning total exists before correction", float(before["learning"]) == 600.0, repr(before))
        storage.add_category_rule("大学物理 光学", "娱乐", "title", update_existing=True, source="user")
        row = storage.conn.execute("SELECT category, learning_topic FROM content_usage_daily").fetchone()
        event = storage.conn.execute("SELECT category, learning_topic FROM timeline_events").fetchone()
        after = storage.overview_metrics_range(when.date(), when.date())
        check("content category corrected", row["category"] == "娱乐" and row["learning_topic"] == "", repr(dict(row)))
        check("timeline category corrected", event["category"] == "娱乐" and event["learning_topic"] == "", repr(dict(event)))
        check("learning total cleared after non-learning correction", float(after["learning"]) == 0.0, repr(after))
    finally:
        storage.close()
        temp_dir.cleanup()

    print("all category correction tests passed")


if __name__ == "__main__":
    main()
