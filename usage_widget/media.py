from __future__ import annotations

import asyncio
import re
import threading
import time
from dataclasses import dataclass


KNOWN_SOURCE_NAMES = {
    "kugou": "酷狗音乐",
    "kuwo": "酷我音乐",
    "cloudmusic": "网易云音乐",
    "netease": "网易云音乐",
    "spotify": "Spotify",
    "qqmusic": "QQ 音乐",
    "music": "音乐",
}


def friendly_source_name(source: str) -> str:
    source_l = (source or "").lower()
    for hint, name in KNOWN_SOURCE_NAMES.items():
        if hint in source_l:
            return name
    cleaned = (source or "媒体播放").replace("!", " ").replace("_", " ").strip()
    return cleaned[:48] or "媒体播放"


MUSIC_SERVICE_SUFFIXES = (
    "bilibili",
    "哔哩哔哩",
    "youtube",
    "youtube music",
    "spotify",
    "网易云音乐",
    "酷狗音乐",
    "qq音乐",
    "酷我音乐",
    "apple music",
    "soundcloud",
    "music",
)

MUSIC_NOISE_WORDS = (
    "官方",
    "official",
    "mv",
    "music video",
    "lyrics",
    "歌词",
    "完整版",
    "高音质",
    "无损",
)


def _clean_music_piece(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip(" -_—–|·\t\r\n")
    # Strip any 【】 or 【】 bracketed content (quality tags, platform tags)
    text = re.sub(r"\s*[【].*?[】]\s*", " ", text)
    text = re.sub(r"\s*[「].*?[」]\s*", " ", text)
    # Strip bracketed keywords (official, mv, lyrics, etc.)
    text = re.sub(r"\s*[\(\[【（][^\)\]】）]*(官方|official|music video|mv|lyrics?|歌词|live|inst|instrumental|remix|cover|翻唱)[^\)\]】）]*[\)\]】）]\s*", " ", text, flags=re.I)
    text = re.sub(r"\s*[\(\[【（]\s*(19|20)\d{2}\s*[\)\]】）]\s*$", "", text)
    text = re.sub(r"\s*\??\s*(19|20)\d{2}\s*\??\s*$", "", text)
    for suffix in MUSIC_SERVICE_SUFFIXES:
        text = re.sub(rf"\s*[-_—–|·]\s*{re.escape(suffix)}\s*$", "", text, flags=re.I)
    for word in MUSIC_NOISE_WORDS:
        text = re.sub(rf"\b{re.escape(word)}\b", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" -_—–|·")


def parse_music_identity(text: str, source: str = "", domain: str = "") -> tuple[str, str, str]:
    raw = _clean_music_piece(text)
    if not raw:
        return "", "", ""
    lower_domain = (domain or "").lower()
    book_title = re.search(r"(.{1,40})[《<](.{1,80})[》>]", raw)
    if book_title:
        artist = _clean_music_piece(book_title.group(1))
        title = _clean_music_piece(book_title.group(2))
        label = f"{artist} - {title}" if artist and title else title or artist
        return title, artist, label
    parts = [_clean_music_piece(part) for part in re.split(r"\s*(?:-|—|–|\||:|：)\s*", raw)]
    parts = [part for part in parts if part]
    filtered = []
    for part in parts:
        part_l = part.lower()
        if any(suffix in part_l for suffix in MUSIC_SERVICE_SUFFIXES) and len(parts) > 1:
            continue
        filtered.append(part)
    parts = filtered or parts
    artist = ""
    title = raw
    if len(parts) >= 2:
        if "music.youtube.com" in lower_domain or "open.spotify.com" in lower_domain:
            title, artist = parts[0], parts[1]
        else:
            artist, title = parts[0], parts[1]
    elif parts:
        title = parts[0]
    if not artist and source and not any(hint in source.lower() for hint in ("browser", "extension", "chrome", "edge", "firefox")):
        friendly = friendly_source_name(source)
        if friendly not in {"音乐", "媒体播放"} and friendly not in title:
            artist = friendly
    label = f"{artist} - {title}" if artist and title else title or artist or raw
    return _clean_music_piece(title), _clean_music_piece(artist), _clean_music_piece(label)


@dataclass(frozen=True)
class MediaItem:
    source: str
    title: str
    artist: str
    is_playing: bool

    @property
    def display_title(self) -> str:
        if self.artist and self.title:
            return f"{self.artist} - {self.title}"
        return self.title or self.artist or f"{friendly_source_name(self.source)}（播放中）"


class MediaSessionProvider:
    def __init__(self, min_interval: float = 3.0) -> None:
        self.min_interval = min_interval
        self.available = True
        self._items: list[MediaItem] = []
        self._last_refresh = 0.0
        self._lock = threading.Lock()
        self._refreshing = False
        self.consecutive_errors = 0
        self.last_error = ""
        self.last_success_at = 0.0

    def current_items(self) -> list[MediaItem]:
        with self._lock:
            return list(self._items)

    def refresh_async(self) -> None:
        now = time.monotonic()
        with self._lock:
            if not self.available and now - self._last_refresh < 60.0:
                return
            if self._refreshing or now - self._last_refresh < self.min_interval:
                return
            self._refreshing = True
            self._last_refresh = now

        try:
            thread = threading.Thread(target=self._refresh_worker, name="UsageWidgetMediaRefresh", daemon=True)
            thread.start()
        except Exception as exc:
            with self._lock:
                self._refreshing = False
                self.consecutive_errors += 1
                self.last_error = f"Thread start failed: {exc}"

    def _refresh_worker(self) -> None:
        try:
            items = asyncio.run(_read_media_sessions())
            with self._lock:
                self._items = items
                self.available = True
                self.consecutive_errors = 0
                self.last_error = ""
                self.last_success_at = time.monotonic()
        except Exception as exc:
            with self._lock:
                self.consecutive_errors += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.available = self.consecutive_errors < 5
                self._items = []
        finally:
            with self._lock:
                self._refreshing = False


async def _read_media_sessions() -> list[MediaItem]:
    from winsdk.windows.media.control import (  # type: ignore[import-not-found]
        GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    )

    manager = await SessionManager.request_async()
    sessions = manager.get_sessions()
    result: list[MediaItem] = []
    for session in sessions:
        try:
            playback_info = session.get_playback_info()
            status = playback_info.playback_status
            status_name = str(getattr(status, "name", status)).split(".")[-1].lower()
            try:
                status_value = int(status)
            except Exception:
                status_value = -1
            is_playing = status_name == "playing" or status_value == 4
            if not is_playing:
                continue
            props = await session.try_get_media_properties_async()
            title = str(getattr(props, "title", "") or "").strip()
            artist = str(getattr(props, "artist", "") or "").strip()
            source = str(getattr(session, "source_app_user_model_id", "") or "media").strip()
            if not title and not artist and not source:
                continue
            result.append(MediaItem(source=source, title=title, artist=artist, is_playing=True))
        except Exception:
            continue
    return result
