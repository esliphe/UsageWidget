"""Regression tests for content and online category classification."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import sys
import time
import tempfile

sys.path.insert(0, ".")

from usage_widget.monitor import ProcessMonitor
from usage_widget.classification import clean_lookup_title
from usage_widget.online_category import OnlineCategoryClassifier
from usage_widget.online_category import CategoryLookupResult
from usage_widget.storage import Storage


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {name}")
    if not condition:
        if detail:
            print(f"       {detail}")
        raise AssertionError(name)


def fresh_monitor() -> tuple[Storage, ProcessMonitor, object, tempfile.TemporaryDirectory[str]]:
    temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(temp_dir.name) / f"usage-widget-classification-{time.time_ns()}.db"
    storage = Storage(db_path)
    monitor = ProcessMonitor(storage)
    settings = replace(storage.load_settings(), online_category_lookup=True)
    return storage, monitor, settings, temp_dir


def main() -> int:
    print("=== online category rule persistence ===")
    storage, monitor, settings, temp_dir = fresh_monitor()
    try:
        key = monitor.category_classifier._key("browser", "unknown.example", "Some AI assistant product")
        monitor.category_classifier._cache[key] = (
            time.monotonic(),
            CategoryLookupResult("AI 工具", 0.90, "test"),
        )
        category = monitor._category_for("browser", "unknown.example", "Some AI assistant product", settings)
        check("uses cached online result", category == "AI 工具", f"got {category}")
        check(
            "does not persist browser as AI app",
            storage.category_for("browser", "", "Plain page") == "其他",
            storage.category_for("browser", "", "Plain page"),
        )
        check(
            "does not persist generic web domain rule",
            storage.category_for("", "unknown.example", "Other page") == "其他",
            storage.category_for("", "unknown.example", "Other page"),
        )
    finally:
        storage.close()
        temp_dir.cleanup()

    storage, monitor, settings, temp_dir = fresh_monitor()
    try:
        key = monitor.category_classifier._key("rareapp.exe", "", "Acme project dashboard")
        monitor.category_classifier._cache[key] = (
            time.monotonic(),
            CategoryLookupResult("办公", 0.88, "test"),
        )
        category = monitor._category_for("rareapp.exe", "", "Acme project dashboard", settings)
        check("uses app online result", category == "办公", f"got {category}")
        check(
            "persists specific app rule",
            storage.category_for("rareapp.exe", "", "Anything") == "办公",
            storage.category_for("rareapp.exe", "", "Anything"),
        )
        explanation = storage.category_explanation("办公", "rareapp.exe", "", "Anything")
        check(
            "online learned rule is explained as online",
            "来源：联网分类" in explanation,
            explanation,
        )
    finally:
        storage.close()
        temp_dir.cleanup()

    storage, monitor, settings, temp_dir = fresh_monitor()
    try:
        key = monitor.category_classifier._key("browser", "developer.vendor-example.com", "SDK reference")
        monitor.category_classifier._cache[key] = (
            time.monotonic(),
            CategoryLookupResult("编程", 0.86, "test"),
        )
        category = monitor._category_for("browser", "developer.vendor-example.com", "SDK reference", settings)
        check("uses domain online result", category == "编程", f"got {category}")
        check(
            "persists specific domain rule",
            storage.category_for("", "developer.vendor-example.com", "Other reference") == "编程",
            storage.category_for("", "developer.vendor-example.com", "Other reference"),
        )
    finally:
        storage.close()
        temp_dir.cleanup()

    print("\n=== broad video platform content refinement ===")
    storage, monitor, settings, temp_dir = fresh_monitor()
    try:
        check(
            "bilibili suffix is stripped before classification",
            clean_lookup_title("bilibili.com", "搞笑合集 笑到肚子疼_哔哩哔哩_bilibili") == "搞笑合集 笑到肚子疼",
            clean_lookup_title("bilibili.com", "搞笑合集 笑到肚子疼_哔哩哔哩_bilibili"),
        )
        check(
            "bilibili funny video refines to entertainment",
            monitor._category_for("browser", "bilibili.com", "搞笑合集 笑到肚子疼_哔哩哔哩_bilibili", settings) == "娱乐",
            monitor._category_for("browser", "bilibili.com", "搞笑合集 笑到肚子疼_哔哩哔哩_bilibili", settings),
        )
        check(
            "bilibili game video refines to game",
            monitor._category_for("browser", "bilibili.com", "【原神】4.0 新角色实况 - 哔哩哔哩", settings) == "游戏",
            monitor._category_for("browser", "bilibili.com", "【原神】4.0 新角色实况 - 哔哩哔哩", settings),
        )
        check(
            "bilibili law lecture refines to learning",
            monitor._category_for("browser", "bilibili.com", "罗翔 刑法 总则 第1讲", settings) == "学习",
            monitor._category_for("browser", "bilibili.com", "罗翔 刑法 总则 第1讲", settings),
        )
        check(
            "b23 short domain uses title content",
            monitor._category_for("browser", "b23.tv", "Python教程 零基础入门", settings) == "学习",
            monitor._category_for("browser", "b23.tv", "Python教程 零基础入门", settings),
        )
        check(
            "product review video refines to shopping",
            monitor._category_for("browser", "bilibili.com", "手机开箱测评 好物推荐", settings) == "购物",
            monitor._category_for("browser", "bilibili.com", "手机开箱测评 好物推荐", settings),
        )
        check(
            "news video refines to news",
            monitor._category_for("browser", "bilibili.com", "今日热点 新闻资讯", settings) == "新闻",
            monitor._category_for("browser", "bilibili.com", "今日热点 新闻资讯", settings),
        )
        online = OnlineCategoryClassifier()
        result = online._lookup("browser", "bilibili.com", "搞笑合集 笑到肚子疼_哔哩哔哩_bilibili")
        check(
            "online classifier local-title avoids broad video bucket",
            result.category == "娱乐" and result.source == "local-title",
            f"category={result.category} source={result.source} conf={result.confidence:.2f}",
        )
        key = monitor.category_classifier._key("browser", "bilibili.com", "冷门专题 Alpha-42")
        monitor.category_classifier._cache[key] = (
            time.monotonic(),
            CategoryLookupResult("学习", 0.84, "test"),
        )
        check(
            "online bilibili video result can override video bucket",
            monitor._category_for("browser", "bilibili.com", "冷门专题 Alpha-42", settings) == "学习",
            monitor._category_for("browser", "bilibili.com", "冷门专题 Alpha-42", settings),
        )
        check(
            "does not persist whole bilibili domain as learning",
            storage.category_for("", "bilibili.com", "普通视频") == "视频",
            storage.category_for("", "bilibili.com", "普通视频"),
        )
        storage.add_category_rule("alpha-42", "游戏", "title", update_existing=True, source="user")
        monitor._remember_online_category_rule("browser", "bilibili.com", "alpha-42", "学习")
        check(
            "online learned rule does not overwrite user correction",
            storage.category_for("", "bilibili.com", "alpha-42") == "游戏",
            storage.category_for("", "bilibili.com", "alpha-42"),
        )
    finally:
        storage.close()
        temp_dir.cleanup()

    print("\n=== default rule conflict guards ===")
    storage, _monitor, _settings, temp_dir = fresh_monitor()
    try:
        check(
            "douyin.com defaults to entertainment",
            storage.category_for("", "douyin.com", "短视频") == "娱乐",
            storage.category_for("", "douyin.com", "短视频"),
        )
        check(
            "weibo.com defaults to entertainment",
            storage.category_for("", "weibo.com", "热搜") == "娱乐",
            storage.category_for("", "weibo.com", "热搜"),
        )
    finally:
        storage.close()
        temp_dir.cleanup()

    print("\n=== storage overview and nocase path lookups ===")
    storage, _monitor, _settings, temp_dir = fresh_monitor()
    try:
        when = datetime(2026, 1, 2, 12, 0, 0)
        stored_path = r"C:\Apps\FooApp\Foo.EXE"
        lookup_path = r"c:\apps\fooapp\foo.exe"
        storage.increment_usage(
            [
                {
                    "exe_name": "Foo.EXE",
                    "exe_path": stored_path,
                    "foreground_seconds": 30.0,
                    "running_seconds": 45.0,
                }
            ],
            when,
        )
        storage.increment_content_usage(
            [
                {
                    "kind": "web_page",
                    "exe_name": "Foo.EXE",
                    "exe_path": stored_path,
                    "content_key": "web:https://example.com/page",
                    "content_title": "Example page",
                    "content_url": "https://example.com/page",
                    "content_domain": "example.com",
                    "category": "学习",
                    "learning_topic": "综合学习",
                    "attention_seconds": 30.0,
                    "background_seconds": 0.0,
                }
            ],
            when,
        )
        counts = storage.overview_counts_range(when.date(), when.date())
        check("overview program count", counts["program_count"] == 1, str(counts))
        check("overview web count", counts["web_count"] == 1, str(counts))
        check("overview learning topic count", counts["learning_topic_count"] == 1, str(counts))
        stats = storage.stats_for_paths([lookup_path], target_date=when.date())
        check("stats_for_paths matches path case-insensitively", lookup_path in stats, str(stats.keys()))
        top = storage.top_content_for_paths([lookup_path], target_date=when.date())
        check("top_content_for_paths matches path case-insensitively", bool(top.get(lookup_path)), str(top))
    finally:
        storage.close()
        temp_dir.cleanup()

    print("\n=== local fallback misclassification guards ===")
    storage, monitor, settings, temp_dir = fresh_monitor()
    try:
        cases = [
            ("browser", "bilibili.com", "大学物理 光学 期末不挂科 蜂考", "学习"),
            ("browser", "bilibili.com", "原神 4.0 新角色实况", "游戏"),
            ("browser", "bilibili.com", "搞笑合集 笑到肚子疼", "娱乐"),
            ("browser", "bilibili.com", "手机开箱测评 好物推荐", "购物"),
            ("browser", "bilibili.com", "今日热点 新闻资讯", "新闻"),
            ("Codex.exe", "", "Codex", "AI 工具"),
            ("browser", "dazidazi.com", "在线打字练习", "工具"),
            ("browser", "music.163.com", "周杰伦 歌单", "音乐"),
            ("yuanbao.exe", "", "腾讯元宝", "AI 工具"),
            ("stm32cubemx.exe", "", "Pinout Configuration", "编程"),
        ]
        for exe, domain, title, expected in cases:
            actual = monitor._fallback_category_for(exe, domain, title)
            check(f"{title[:24]} -> {expected}", actual == expected, f"got {actual}")
    finally:
        storage.close()
        temp_dir.cleanup()

    print("\n=== unidentified content repair ===")
    storage, _monitor, _settings, temp_dir = fresh_monitor()
    try:
        when = datetime(2026, 1, 3, 9, 0, 0)
        storage.increment_content_usage(
            [
                {
                    "kind": "video_playback",
                    "exe_name": "browser",
                    "exe_path": "browser",
                    "content_key": "video:bilibili-genshin",
                    "content_title": "原神 4.0 新角色实况 - 哔哩哔哩",
                    "content_url": "https://www.bilibili.com/video/BV-genshin",
                    "content_domain": "bilibili.com",
                    "category": "视频",
                    "learning_topic": "",
                    "attention_seconds": 0,
                    "background_seconds": 1800,
                },
                {
                    "kind": "web_page",
                    "exe_name": "browser",
                    "exe_path": "browser",
                    "content_key": "web:dazidazi",
                    "content_title": "在线打字练习",
                    "content_url": "https://dazidazi.com/",
                    "content_domain": "dazidazi.com",
                    "category": "其他",
                    "learning_topic": "",
                    "attention_seconds": 300,
                    "background_seconds": 0,
                },
                {
                    "kind": "web_page",
                    "exe_name": "browser",
                    "exe_path": "browser",
                    "content_key": "web:alpha-study",
                    "content_title": "Alpha Research Dashboard",
                    "content_url": "https://alpha-study.example/",
                    "content_domain": "alpha-study.example",
                    "category": "其他",
                    "learning_topic": "",
                    "attention_seconds": 600,
                    "background_seconds": 0,
                },
            ],
            when,
        )
        stats = storage.repair_unidentified_content(online=False)
        game_row = storage.conn.execute(
            "SELECT category FROM content_usage_daily WHERE content_key = 'video:bilibili-genshin'"
        ).fetchone()
        check("local repair refines bilibili video", game_row["category"] == "游戏", str(stats))
        typing_row = storage.conn.execute(
            "SELECT category FROM content_usage_daily WHERE content_key = 'web:dazidazi'"
        ).fetchone()
        check("local repair marks known typing site as tool", typing_row["category"] == "工具", str(stats))

        old_lookup_sync = OnlineCategoryClassifier.lookup_sync

        def fake_lookup_sync(self, exe_name: str, domain: str = "", title: str = "") -> CategoryLookupResult:
            return CategoryLookupResult("学习", 0.82, "fake", "research learning dashboard")

        OnlineCategoryClassifier.lookup_sync = fake_lookup_sync
        try:
            stats = storage.repair_unidentified_content(online=True, online_limit=5)
        finally:
            OnlineCategoryClassifier.lookup_sync = old_lookup_sync
        online_row = storage.conn.execute(
            "SELECT category FROM content_usage_daily WHERE content_key = 'web:alpha-study'"
        ).fetchone()
        check("online repair updates unknown site", online_row["category"] == "学习", str(stats))
        explanation = storage.category_explanation("学习", "", "alpha-study.example", "Other page")
        check("online repair persists explanation source", "来源：联网分类" in explanation, explanation)
    finally:
        storage.close()
        temp_dir.cleanup()

    print("\n=== timeline history query helpers ===")
    storage, _monitor, _settings, temp_dir = fresh_monitor()
    try:
        day = datetime(2026, 1, 4, 10, 0, 0)
        storage.add_timeline_event(day, day + timedelta(minutes=30), "web_page", "Python 教程 检索测试", 1800, app_name="chrome.exe", category="学习", learning_topic="Python")
        storage.add_timeline_event(day + timedelta(hours=1), day + timedelta(hours=1, minutes=10), "video_playback", "原神 实况", 600, app_name="chrome.exe", category="游戏")
        storage.add_timeline_event(day + timedelta(hours=2), day + timedelta(hours=2, minutes=4), "media_playback", "周杰伦 - 七里香", 240, app_name="music.exe", category="音乐")
        rows = storage.timeline_rows_range(day.date(), day.date(), query="python", kind="web_page", min_seconds=600, sort="duration")
        check("timeline query filters keyword/kind/min duration", len(rows) == 1 and rows[0]["category"] == "学习", [dict(row) for row in rows])
        summary = storage.timeline_query_summary_range(day.date(), day.date(), query="python", kind="web_page", min_seconds=600)
        check("timeline query summary", summary["count"] == 1 and int(summary["seconds"]) == 1800, str(summary))
        duration_rows = storage.timeline_rows_range(day.date(), day.date(), sort="duration")
        check("timeline duration sort", duration_rows[0]["seconds"] >= duration_rows[1]["seconds"], [row["seconds"] for row in duration_rows])
    finally:
        storage.close()
        temp_dir.cleanup()

    print("\nall classification regression tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
