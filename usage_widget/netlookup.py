"""Shared outbound HTTP helpers for the online lookup providers.

Both ``learning`` and ``online_category`` talk to Baidu, DuckDuckGo and
Wikipedia. They used to carry their own copy of the user agent, the 256 KB
body cap, the access-challenge detection and the two fetch helpers -- which is
exactly the kind of duplication where one copy gets a bug fix and the other
does not. The module keeps a single implementation; the callers keep their own
timeout because their latency budgets differ.
"""
from __future__ import annotations

import json
import urllib.request


USER_AGENT = "UsageWidget"
DESKTOP_USER_AGENT = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) {USER_AGENT}"
MAX_BODY_BYTES = 256 * 1024

# Markers seen when a search engine answers with a captcha / bot wall instead
# of results. Parsing such a page would silently yield junk, so callers treat
# it as a provider failure.
_ACCESS_CHALLENGE_MARKERS = (
    "百度安全验证",
    "安全验证",
    "请输入验证码",
    "verify you are human",
    "captcha",
    "unusual traffic",
    "cf-chl-",
)


def is_access_challenge(text: str) -> bool:
    """Return True when the response is a captcha / bot wall, not content."""
    normalized = (text or "").casefold()
    return any(marker in normalized for marker in _ACCESS_CHALLENGE_MARKERS)


def fetch_json(url: str, timeout: float = 3.0) -> dict:
    """Fetch a JSON object. Raises when the payload is not a JSON object."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_BODY_BYTES)
    data = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")
    return data


def fetch_text(url: str, timeout: float = 4.0) -> str:
    """Fetch an HTML page, honouring the charset the server declares.

    Baidu sometimes answers in GB18030; decoding it as UTF-8 would turn every
    Chinese snippet into replacement characters.
    """
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DESKTOP_USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_BODY_BYTES)
        charset = response.headers.get_content_charset() or ""
    for encoding in (charset, "utf-8", "gb18030"):
        if not encoding:
            continue
        try:
            return raw.decode(encoding, errors="replace")
        except LookupError:
            continue
    return raw.decode("utf-8", errors="replace")
