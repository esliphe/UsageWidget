from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

_ONENOTE_FULL = re.compile(r"^(.+?)\s*[-—–]\s*(.+?)\s*[-—–]\s*OneNote$", re.IGNORECASE)
_ONENOTE_SHORT = re.compile(r"^(.+?)\s*[-—–]\s*OneNote$", re.IGNORECASE)


BROWSER_EXE_NAMES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "opera_gx.exe",
    "vivaldi.exe",
    "arc.exe",
}


BROWSER_SUFFIXES = {
    "chrome.exe": [" - Google Chrome"],
    "msedge.exe": [" - Microsoft Edge"],
    "firefox.exe": [" - Mozilla Firefox", " — Mozilla Firefox"],
    "brave.exe": [" - Brave"],
    "opera.exe": [" - Opera"],
    "opera_gx.exe": [" - Opera GX"],
    "vivaldi.exe": [" - Vivaldi"],
    "arc.exe": [" - Arc"],
}


@dataclass(frozen=True)
class ContentInfo:
    kind: str
    key: str
    title: str
    url: str = ""
    domain: str = ""


def clean_window_title(title: str) -> str:
    return " ".join((title or "").strip().split())


def domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host.lower()
    except Exception:
        return ""


def classify_window_content(exe_name: str, title: str, url: str = "", private_title_mode: bool = False) -> ContentInfo | None:
    clean_title = clean_window_title(title)
    clean_url = (url or "").strip()
    domain = domain_from_url(clean_url)
    if not clean_title and not clean_url:
        return None

    lower_exe = (exe_name or "").lower()
    if lower_exe in BROWSER_EXE_NAMES:
        page_title = clean_title
        for suffix in BROWSER_SUFFIXES.get(lower_exe, []):
            if page_title.lower().endswith(suffix.lower()):
                page_title = page_title[: -len(suffix)].strip()
                break
        if not page_title and domain:
            page_title = domain
        if not page_title or page_title.lower() in {"new tab", "about:blank", "新建标签页"}:
            return None
        if private_title_mode:
            page_title = domain or "网页浏览"
        key_body = clean_url or (f"{domain}:{page_title.lower()}" if domain else page_title.lower())
        return ContentInfo(kind="web_page", key=f"{lower_exe}:{key_body}", title=page_title, url=clean_url, domain=domain)

    ignored_titles = {
        "usagewidget",
        "usagewidget 设置",
        "设置",
        "program manager",
    }
    if clean_title.lower() in ignored_titles:
        return None
    title_out = lower_exe if private_title_mode else clean_title
    return ContentInfo(kind="window_title", key=f"{lower_exe}:{clean_title.lower()}", title=title_out)


def extract_onenote_info(title: str, exe_name: str) -> tuple[bool, str, bool]:
    clean = clean_window_title(title)
    lower_exe = (exe_name or "").lower()
    is_onenote = False
    if lower_exe == "onenote.exe" or lower_exe.endswith("\\onenote.exe"):
        is_onenote = True
    elif lower_exe == "applicationframehost.exe" or lower_exe.endswith("\\applicationframehost.exe"):
        if clean.lower().endswith(" - onenote"):
            is_onenote = True
    if not is_onenote:
        return False, "", False
    m = _ONENOTE_FULL.match(clean)
    if m:
        return True, m.group(1).strip(), True
    m = _ONENOTE_SHORT.match(clean)
    if m:
        return True, m.group(1).strip(), True
    return True, "", True
