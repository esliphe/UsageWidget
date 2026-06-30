from __future__ import annotations

from PySide6.QtGui import QColor


APP_COLORS = {
    "focus": "#1677d2",
    "web": "#4a90c4",
    "video": "#f0a33a",
    "music": "#d95f76",
    "learn": "#55b88d",
    "success": "#55b88d",
    "warning": "#f0a33a",
    "danger": "#d95f76",
    "muted": "#6b7c93",
}

CATEGORY_COLORS = {
    "学习": APP_COLORS["learn"],
    "编程": APP_COLORS["focus"],
    "AI 工具": "#8b72d9",
    "系统软件": "#6b7c93",
    "聊天": "#1abc9c",
    "游戏": "#e74c3c",
    "视频": APP_COLORS["video"],
    "音乐": APP_COLORS["music"],
    "娱乐": "#fd79a8",
    "社交": "#2f9aa0",
    "办公": "#64748b",
    "工具": "#8b72d9",
    "打字": "#2f9aa0",
    "网站": APP_COLORS["web"],
    "购物": "#e17055",
    "新闻": "#636e72",
    "其他": APP_COLORS["muted"],
}

FALLBACK_CATEGORY_COLORS = (
    APP_COLORS["focus"],
    APP_COLORS["learn"],
    APP_COLORS["video"],
    APP_COLORS["music"],
    "#8b72d9",
    "#2f9aa0",
    APP_COLORS["muted"],
)


def app_color(name: str) -> str:
    return APP_COLORS.get(name, APP_COLORS["muted"])


def category_color(name: str, index: int = 0) -> str:
    normalized = (name or "").strip()
    if normalized in CATEGORY_COLORS:
        return CATEGORY_COLORS[normalized]
    return FALLBACK_CATEGORY_COLORS[index % len(FALLBACK_CATEGORY_COLORS)]


def qcolor(value: str) -> QColor:
    return QColor(value)
