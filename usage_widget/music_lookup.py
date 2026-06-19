from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .media import parse_music_identity


@dataclass(frozen=True)
class MusicLookupResult:
    is_music: bool
    confidence: float
    source: str
    title: str = ""
    artist: str = ""


class OnlineMusicVerifier:
    MAX_CACHE_SIZE = 800

    def __init__(self, min_interval: float = 8.0, ttl_seconds: float = 86400.0) -> None:
        self.min_interval = min_interval
        self.ttl_seconds = ttl_seconds
        self.error_ttl_seconds = 600.0
        self.max_workers = 5
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, MusicLookupResult]] = {}
        self._pending: set[str] = set()
        self._last_request_at = 0.0
        self._active_workers = 0
        self.last_error = ""
        self.last_source = ""

    def cached(self, title: str, domain: str = "") -> MusicLookupResult | None:
        key = self._key(title, domain)
        now = time.monotonic()
        with self._lock:
            item = self._cache.get(key)
            if not item:
                return None
            saved_at, result = item
            ttl = self.error_ttl_seconds if result.source == "error" else self.ttl_seconds
            if now - saved_at > ttl:
                self._cache.pop(key, None)
                return None
            return result

    def queue(self, title: str, domain: str = "") -> None:
        key = self._key(title, domain)
        if not key:
            return
        with self._lock:
            if key in self._pending or key in self._cache:
                return
            if self._active_workers >= self.max_workers:
                return
            self._pending.add(key)
            self._active_workers += 1
        try:
            thread = threading.Thread(target=self._worker, args=(key, title, domain), name="UsageWidgetMusicLookup", daemon=True)
            thread.start()
        except Exception as exc:
            with self._lock:
                self._pending.discard(key)
                self._active_workers -= 1
                self.last_error = f"Thread start failed: {exc}"

    def _worker(self, key: str, title: str, domain: str) -> None:
        try:
            now = time.monotonic()
            with self._lock:
                wait = max(0.0, self.min_interval - (now - self._last_request_at))
            if wait:
                time.sleep(wait)
            with self._lock:
                self._last_request_at = time.monotonic()
            result = self._lookup(title, domain)
            with self._lock:
                self._cache[key] = (time.monotonic(), result)
                self._evict_locked()
                self.last_error = ""
                self.last_source = result.source
        except Exception as exc:
            with self._lock:
                self._cache[key] = (
                    time.monotonic(),
                    MusicLookupResult(False, 0.0, "error"),
                )
                self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                self._pending.discard(key)
                self._active_workers -= 1

    def _lookup(self, title: str, domain: str) -> MusicLookupResult:
        song, artist, label = parse_music_identity(title, source="browser", domain=domain)
        query = label or title
        if not query:
            return MusicLookupResult(False, 0.0, "empty")
        # Try iTunes first
        result = self._lookup_itunes(query, song, artist)
        if result.is_music:
            return result
        # Try MusicBrainz
        result = self._lookup_musicbrainz(query, song, artist)
        if result.is_music:
            return result
        # Try Last.fm as final fallback
        result = self._lookup_lastfm(query, song, artist)
        if result.is_music:
            return result
        return MusicLookupResult(False, 0.0, "multi")

    def _lookup_itunes(self, query: str, song: str, artist: str) -> MusicLookupResult:
        params = urllib.parse.urlencode({"term": query, "media": "music", "entity": "song", "limit": 5})
        data = self._fetch_json(f"https://itunes.apple.com/search?{params}", headers={"User-Agent": "UsageWidget/5.6"})
        for item in data.get("results", []):
            track = str(item.get("trackName", "")).strip()
            artist_name = str(item.get("artistName", "")).strip()
            if self._matches(song, artist, track, artist_name):
                return MusicLookupResult(True, 0.92, "itunes", track, artist_name)
        return MusicLookupResult(False, 0.0, "itunes")

    def _lookup_musicbrainz(self, query: str, song: str, artist: str) -> MusicLookupResult:
        params = urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 5})
        data = self._fetch_json(
            f"https://musicbrainz.org/ws/2/recording/?{params}",
            headers={"User-Agent": "UsageWidget/5.6 (local personal usage analytics)"},
        )
        for item in data.get("recordings", []):
            track = str(item.get("title", "")).strip()
            artists = item.get("artist-credit", [])
            artist_name = ""
            if artists and isinstance(artists, list) and isinstance(artists[0], dict):
                artist_name = str(artists[0].get("name", "")).strip()
            score = float(item.get("score", 0) or 0)
            if score >= 80 and self._matches(song, artist, track, artist_name):
                return MusicLookupResult(True, min(0.98, score / 100.0), "musicbrainz", track, artist_name)
        return MusicLookupResult(False, 0.0, "musicbrainz")

    def _lookup_lastfm(self, query: str, song: str, artist: str) -> MusicLookupResult:
        """Query Last.fm search API as a fallback music verification source."""
        params = urllib.parse.urlencode({
            "method": "track.search",
            "track": query,
            "api_key": "2c5389f92935c2ef25f6e1f8b944a3d3",
            "format": "json",
            "limit": "5",
        })
        try:
            data = self._fetch_json(
                f"https://ws.audioscrobbler.com/2.0/?{params}",
                headers={"User-Agent": "UsageWidget/5.30"},
            )
            tracks = data.get("results", {}).get("trackmatches", {}).get("track", [])
            if not isinstance(tracks, list):
                tracks = [tracks] if tracks else []
            for item in tracks[:5]:
                track = str(item.get("name", "")).strip()
                artist_name = str(item.get("artist", "")).strip()
                if self._matches(song, artist, track, artist_name):
                    return MusicLookupResult(True, 0.85, "lastfm", track, artist_name)
        except Exception:
            pass
        return MusicLookupResult(False, 0.0, "lastfm")

    def _fetch_json(self, url: str, headers: dict[str, str]) -> dict:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=3.0) as response:
            raw = response.read(256 * 1024)
        return json.loads(raw.decode("utf-8", errors="replace"))

    def _matches(self, song: str, artist: str, track: str, artist_name: str) -> bool:
        song_l = self._norm(song)
        artist_l = self._norm(artist)
        track_l = self._norm(track)
        artist_name_l = self._norm(artist_name)
        if not track_l:
            return False
        # Require at least 3 chars for substring matching to avoid false positives
        def _fuzzy(a: str, b: str) -> bool:
            if not a or not b:
                return True
            if len(a) < 3 or len(b) < 3:
                return a == b
            return a in b or b in a
        return _fuzzy(song_l, track_l) and _fuzzy(artist_l, artist_name_l)

    def _key(self, title: str, domain: str) -> str:
        return f"{domain.lower().strip()}|{title.lower().strip()}"[:260]

    def _evict_locked(self) -> None:
        """Evict oldest entries when cache exceeds MAX_CACHE_SIZE. Must hold _lock."""
        excess = len(self._cache) - self.MAX_CACHE_SIZE
        if excess <= 0:
            return
        sorted_items = sorted(self._cache.items(), key=lambda item: item[1][0])
        for i in range(min(excess, len(sorted_items))):
            self._cache.pop(sorted_items[i][0], None)

    def _norm(self, value: str) -> str:
        return " ".join((value or "").casefold().replace("_", " ").replace("-", " ").split())
