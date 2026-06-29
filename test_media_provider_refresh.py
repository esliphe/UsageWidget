from __future__ import annotations

import time

from usage_widget import media
from usage_widget.media import MediaItem, MediaSessionProvider


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        raise AssertionError(detail or name)


def main() -> None:
    original_reader = media._read_media_sessions

    async def fast_reader() -> list[MediaItem]:
        return [MediaItem(source="unit", title="Song", artist="Artist", is_playing=True)]

    async def slow_reader() -> list[MediaItem]:
        time.sleep(0.4)
        return [MediaItem(source="unit", title="Late", artist="Artist", is_playing=True)]

    try:
        provider = MediaSessionProvider(min_interval=0.0)
        media._read_media_sessions = fast_reader  # type: ignore[assignment]
        items = provider.refresh_sync(timeout_seconds=0.3)
        check("sync refresh returns fresh items", len(items) == 1 and items[0].title == "Song", repr(items))
        check("sync refresh clears consecutive errors", provider.consecutive_errors == 0)

        provider._last_refresh = 0.0
        media._read_media_sessions = slow_reader  # type: ignore[assignment]
        started = time.monotonic()
        items = provider.refresh_sync(timeout_seconds=0.1)
        elapsed = time.monotonic() - started
        check("sync refresh timeout returns quickly", elapsed < 0.3, f"elapsed={elapsed}")
        check("sync refresh timeout preserves cached items", len(items) == 1 and items[0].title == "Song", repr(items))
    finally:
        media._read_media_sessions = original_reader  # type: ignore[assignment]

    print("all media provider refresh tests passed")


if __name__ == "__main__":
    main()
