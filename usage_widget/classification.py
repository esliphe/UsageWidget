from __future__ import annotations

import re


GENERIC_CONTENT_DOMAINS = {
    "bilibili.com",
    "b23.tv",
    "youtube.com",
    "youtu.be",
    "youku.com",
    "iqiyi.com",
    "v.qq.com",
    "mgtv.com",
    "douyin.com",
    "kuaishou.com",
    "xiaohongshu.com",
    "weibo.com",
    "reddit.com",
    "zhihu.com",
    "x.com",
    "twitter.com",
}


BROAD_PLATFORM_CATEGORIES = {"视频", "娱乐", "社交", "网站", "浏览器"}


KNOWN_VIDEO_DOMAINS = {
    "bilibili.com",
    "b23.tv",
    "youtube.com",
    "youtu.be",
    "youku.com",
    "iqiyi.com",
    "v.qq.com",
    "mgtv.com",
    "douyin.com",
    "kuaishou.com",
}


_VIDEO_TITLE_HINTS = (
    "video",
    "movie",
    "episode",
    "streaming",
    "livestream",
    "live stream",
    "watch",
    "视频",
    "播放",
    "直播",
    "电影",
    "电视剧",
    "剧集",
    "番剧",
    "纪录片",
    "影视",
    "在线观看",
)


_VIDEO_URL_HINTS = (
    "/watch?",
    "/watch/",
    "/shorts/",
    "/embed/",
    "/video/",
    "/live/",
    "/bangumi/play/",
    "/medialist/play/",
    "/x/cover/",
    "/cover/",
    "/v_",
)


_BROWSER_TITLE_SUFFIXES = (
    " - Google Chrome",
    " - Microsoft Edge",
    " - Mozilla Firefox",
    " - Brave",
    " - Opera",
    " - Opera GX",
    " - Vivaldi",
    " - Arc",
)


_PLATFORM_TITLE_SUFFIXES = (
    r"\s*[_\-|｜—–]\s*哔哩哔哩\s*[_\-|｜—–]?\s*bilibili\s*$",
    r"\s*[_\-|｜—–]\s*bilibili\s*$",
    r"\s*[_\-|｜—–]\s*哔哩哔哩\s*$",
    r"\s*[_\-|｜—–]\s*YouTube\s*$",
    r"\s*[_\-|｜—–]\s*YouTube Music\s*$",
    r"\s*[_\-|｜—–]\s*知乎\s*$",
    r"\s*[_\-|｜—–]\s*微博\s*$",
)


_GENERIC_PAGE_TITLES = {
    "bilibili",
    "哔哩哔哩",
    "哔哩哔哩 (゜-゜)つロ 干杯~-bilibili",
    "youtube",
    "youtube music",
    "新建标签页",
    "new tab",
    "about:blank",
}


def normalize_lookup_text(*parts: str) -> str:
    text = " ".join(str(part) for part in parts if part)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_generic_content_domain(domain: str) -> bool:
    domain_l = (domain or "").casefold().strip()
    if not domain_l:
        return False
    return any(domain_l == item or domain_l.endswith("." + item) for item in GENERIC_CONTENT_DOMAINS)


def is_known_video_domain(domain: str) -> bool:
    domain_l = (domain or "").casefold().strip()
    if not domain_l:
        return False
    return any(domain_l == item or domain_l.endswith("." + item) for item in KNOWN_VIDEO_DOMAINS)


def _hint_matches(text_l: str, hint_l: str) -> bool:
    if not hint_l:
        return False
    if re.fullmatch(r"[a-z0-9]+", hint_l) and len(hint_l) <= 5:
        return re.search(rf"(?<![a-z0-9]){re.escape(hint_l)}(?![a-z0-9])", text_l) is not None
    return hint_l in text_l


def looks_like_video_content(domain: str, title: str = "", url: str = "") -> bool:
    title_l = clean_lookup_title(domain, title).casefold()
    if title_l and any(_hint_matches(title_l, hint.casefold()) for hint in _VIDEO_TITLE_HINTS):
        return True
    url_l = (url or "").casefold().strip()
    if not url_l:
        return False
    if any(hint in url_l for hint in _VIDEO_URL_HINTS):
        return True
    if is_known_video_domain(domain):
        if re.search(r"/(?:bv|av)[a-z0-9]+(?:[/?#]|$)", url_l, flags=re.I):
            return True
        if re.search(r"\.html(?:[?#]|$)", url_l) and not any(
            marker in url_l
            for marker in ("/search", "/space/", "/channel/", "/account/", "/settings", "/feed/")
        ):
            return True
    return False


def clean_lookup_title(domain: str, title: str) -> str:
    text = normalize_lookup_text(title)
    if not text:
        return ""
    for suffix in _BROWSER_TITLE_SUFFIXES:
        if text.casefold().endswith(suffix.casefold()):
            text = text[: -len(suffix)].strip()
            break
    for pattern in _PLATFORM_TITLE_SUFFIXES:
        text = re.sub(pattern, "", text, flags=re.I).strip()
    text = re.sub(r"\s*-\s*播放页\s*$", "", text, flags=re.I).strip()
    text = re.sub(r"\s*-\s*(高清在线观看|视频在线观看|正版高清)\s*$", "", text, flags=re.I).strip()
    text = re.sub(r"\s+", " ", text).strip(" -_|｜")
    if text.casefold() in _GENERIC_PAGE_TITLES:
        return ""
    domain_l = (domain or "").casefold()
    if "bilibili" in domain_l or domain_l.endswith("b23.tv"):
        text = re.sub(r"^\s*【?已关注】?\s*", "", text).strip()
        text = re.sub(r"\s*(?:UP主|弹幕|评论|收藏|转发)\s*$", "", text).strip()
    return text
