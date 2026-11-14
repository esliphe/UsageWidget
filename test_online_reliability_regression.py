from __future__ import annotations

import tempfile
import time
from dataclasses import replace
from pathlib import Path

from usage_widget.learning import OnlineLearningTopicClassifier
from usage_widget.monitor import ProcessMonitor
from usage_widget.music_lookup import OnlineMusicVerifier
from usage_widget.online_category import (
    CategoryLookupResult,
    OnlineCategoryClassifier,
    ProviderResponseError,
)
from usage_widget.storage import Storage


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK' if condition else 'FAIL'}] {name}")
    if not condition:
        raise AssertionError(detail or name)


class BlockedCategoryClassifier(OnlineCategoryClassifier):
    def _fetch_text(self, url: str) -> str:
        return "<html><title>百度安全验证</title></html>"


class BlockedLearningClassifier(OnlineLearningTopicClassifier):
    def _fetch_text(self, url: str) -> str:
        return "<html><title>百度安全验证</title></html>"


class OfflineCategoryClassifier(OnlineCategoryClassifier):
    def __init__(self) -> None:
        super().__init__(min_interval=0.0)
        self.calls: list[str] = []

    def _fail(self, name: str) -> CategoryLookupResult:
        self.calls.append(name)
        raise OSError(f"{name} unavailable")

    def _lookup_baidu(self, query: str, domain: str) -> CategoryLookupResult:
        return self._fail("baidu")

    def _lookup_duckduckgo(self, query: str, domain: str) -> CategoryLookupResult:
        return self._fail("duckduckgo")

    def _lookup_duckduckgo_html(self, query: str, domain: str) -> CategoryLookupResult:
        return self._fail("duckduckgo-html")

    def _lookup_wikipedia(self, query: str, domain: str, lang: str = "en") -> CategoryLookupResult:
        return self._fail(f"wiki-{lang}")


def queue_without_starting_workers(client, args: tuple[str, ...]) -> tuple[str, int]:
    with client._lock:
        client._active_workers = client.max_workers
    client.queue(*args)
    key = client._key(*args)
    with client._lock:
        pending = key in client._pending
        queued = len(client._queued)
        client._pending.clear()
        client._queued.clear()
        client._active_workers = 0
    check(f"{type(client).__name__} retains saturated task", pending and queued == 1, f"queued={queued}")
    return key, queued


def main() -> None:
    for classifier, args in (
        (BlockedCategoryClassifier(min_interval=0.0), ("query", "")),
        (BlockedLearningClassifier(min_interval=0.0), ("query", "text", "", "")),
    ):
        try:
            classifier._lookup_baidu(*args)
        except ProviderResponseError:
            continue
        raise AssertionError(f"{type(classifier).__name__} accepted a challenge page")
    print("[OK] challenge pages are rejected")

    offline = OfflineCategoryClassifier()
    offline._lookup("", "", "qzxv neutral phrase")
    first_call_count = len(offline.calls)
    offline._lookup("", "", "qzxv neutral phrase")
    check("failed providers enter cooldown", len(offline.calls) == first_call_count, repr(offline.calls))
    check("cooldown is visible in diagnostics", "cooldown" in offline.last_provider_errors, offline.last_provider_errors)

    queue_without_starting_workers(OnlineCategoryClassifier(), ("queued.exe", "", "queued content"))
    queue_without_starting_workers(OnlineLearningTopicClassifier(), ("example.com", "queued topic", ""))
    queue_without_starting_workers(OnlineMusicVerifier(), ("queued song", "example.com"))

    temp_dir = tempfile.TemporaryDirectory(prefix="usagewidget-online-")
    storage = Storage(Path(temp_dir.name) / "usage.db")
    try:
        monitor = ProcessMonitor(storage)
        settings = replace(storage.load_settings(), online_category_lookup=True)
        key = monitor.category_classifier._key("rareapp.exe", "", "Project planning board")
        monitor.category_classifier._cache[key] = (
            time.monotonic(),
            CategoryLookupResult("办公", 0.88, "local-query"),
        )
        category = monitor._category_for("rareapp.exe", "", "Project planning board", settings)
        check("local classifier result remains usable", category == "办公", category)
        check(
            "local classifier result is not persisted as online rule",
            storage.category_for("rareapp.exe", "", "Another page") == "其他",
            storage.category_for("rareapp.exe", "", "Another page"),
        )
    finally:
        storage.close()
        temp_dir.cleanup()

    print("all online reliability regression tests passed")


if __name__ == "__main__":
    main()
