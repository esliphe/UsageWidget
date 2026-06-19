from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


@dataclass(frozen=True)
class BrowserTab:
    title: str
    url: str
    domain: str
    browser: str
    received_at: float
    audible: bool = False
    tab_id: int | None = None
    window_id: int | None = None
    muted: bool = False
    active: bool = False
    fav_icon_url: str = ""
    description: str = ""
    h1: str = ""
    has_video: bool = False
    has_audio: bool = False
    media_state: str = ""


@dataclass(frozen=True)
class PageSignal:
    url: str
    domain: str
    received_at: float
    title: str = ""
    description: str = ""
    h1: str = ""
    has_video: bool = False
    has_audio: bool = False
    media_state: str = ""


def domain_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host.lower()
    except Exception:
        return ""


class BrowserBridge:
    def __init__(self, host: str = "127.0.0.1", port: int = 47621) -> None:
        self.host = host
        self.port = port
        self._lock = threading.RLock()
        self._latest: BrowserTab | None = None
        self._audible_tabs: list[BrowserTab] = []
        self._page_signals: dict[str, PageSignal] = {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server:
            return

        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self) -> None:  # noqa: N802
                self._send_cors(204)

            def do_POST(self) -> None:  # noqa: N802
                if self.path not in {"/active-tab", "/audible-tabs", "/page-signal"}:
                    self._send_cors(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(min(length, 16384))
                    payload = json.loads(raw.decode("utf-8"))
                    if self.path == "/page-signal":
                        bridge.update_page_signal(payload)
                        self._send_cors(200, b'{"ok":true}')
                        return
                    if self.path == "/audible-tabs":
                        bridge.update_audible_tabs(payload.get("tabs", []))
                        self._send_cors(200, b'{"ok":true}')
                        return
                    title = (payload.get("title") or "").strip()
                    url = (payload.get("url") or "").strip()
                    browser = (payload.get("browser") or "browser").strip()
                    if title or url:
                        bridge.update(payload, title=title, url=url, browser=browser)
                    self._send_cors(200, b'{"ok":true}')
                except Exception:
                    self._send_cors(400, b'{"ok":false}')

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _send_cors(self, status: int, body: bytes = b"") -> None:
                self.send_response(status)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if body:
                    self.wfile.write(body)

        try:
            self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as exc:
            self._server = None
            self.last_error = f"Port {self.port} unavailable: {exc}"
            return
        self._thread = threading.Thread(target=self._server.serve_forever, name="UsageWidgetBrowserBridge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        server = self._server
        self._server = None
        if server:
            server.shutdown()
            server.server_close()

    def _signal_for_url(self, url: str, max_age_seconds: float = 30.0) -> PageSignal | None:
        with self._lock:
            signal = self._page_signals.get(url)
        if not signal or time.monotonic() - signal.received_at > max_age_seconds:
            return None
        return signal

    def _tab_from_payload(self, payload: dict, title: str, url: str, browser: str, audible: bool) -> BrowserTab:
        signal = self._signal_for_url(url)
        return BrowserTab(
            title=title or (signal.title if signal else ""),
            url=url,
            domain=domain_from_url(url),
            browser=browser,
            received_at=time.monotonic(),
            audible=audible,
            tab_id=int(payload["tabId"]) if str(payload.get("tabId", "")).lstrip("-").isdigit() else None,
            window_id=int(payload["windowId"]) if str(payload.get("windowId", "")).lstrip("-").isdigit() else None,
            muted=bool(payload.get("muted", False)),
            active=bool(payload.get("active", False)),
            fav_icon_url=str(payload.get("favIconUrl", "")).strip(),
            description=(signal.description if signal else str(payload.get("description", "")).strip()),
            h1=(signal.h1 if signal else str(payload.get("h1", "")).strip()),
            has_video=bool(signal.has_video if signal else payload.get("hasVideo", False)),
            has_audio=bool(signal.has_audio if signal else payload.get("hasAudio", False)),
            media_state=(signal.media_state if signal else str(payload.get("mediaState", "")).strip()),
        )

    def update(self, payload: dict, title: str, url: str, browser: str) -> None:
        with self._lock:
            self._latest = self._tab_from_payload(payload, title, url, browser, bool(payload.get("audible", False)))

    def update_page_signal(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        url = (payload.get("url") or "").strip()
        if not url:
            return
        signal = PageSignal(
            url=url,
            domain=domain_from_url(url),
            received_at=time.monotonic(),
            title=(payload.get("title") or "").strip(),
            description=((payload.get("description") or "").strip())[:500],
            h1=((payload.get("h1") or "").strip())[:240],
            has_video=bool(payload.get("hasVideo", False)),
            has_audio=bool(payload.get("hasAudio", False)),
            media_state=((payload.get("mediaState") or "").strip())[:40],
        )
        with self._lock:
            self._page_signals[url] = signal
            if len(self._page_signals) > 200:
                old_keys = sorted(self._page_signals, key=lambda key: self._page_signals[key].received_at)[:50]
                for key in old_keys:
                    self._page_signals.pop(key, None)

    def update_audible_tabs(self, tabs: object) -> None:
        clean: list[BrowserTab] = []
        if isinstance(tabs, list):
            for item in tabs:
                if not isinstance(item, dict):
                    continue
                title = (item.get("title") or "").strip()
                url = (item.get("url") or "").strip()
                if not title and not url:
                    continue
                clean.append(self._tab_from_payload(item, title, url, (item.get("browser") or "browser").strip(), True))
        with self._lock:
            self._audible_tabs = clean[:12]

    def latest(self, max_age_seconds: float = 10.0) -> BrowserTab | None:
        with self._lock:
            item = self._latest
        if not item:
            return None
        if time.monotonic() - item.received_at > max_age_seconds:
            return None
        return item

    def audible_tabs(self, max_age_seconds: float = 10.0) -> list[BrowserTab]:
        now = time.monotonic()
        with self._lock:
            return [tab for tab in self._audible_tabs if now - tab.received_at <= max_age_seconds]

    def page_signal_count(self, max_age_seconds: float = 3600.0) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(1 for item in self._page_signals.values() if now - item.received_at <= max_age_seconds)
