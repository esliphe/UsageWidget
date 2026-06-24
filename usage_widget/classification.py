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
