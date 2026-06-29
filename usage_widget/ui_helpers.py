from __future__ import annotations

import html
from typing import Protocol


class FeatureSettings(Protocol):
    private_title_mode: bool
    online_category_lookup: bool


GENERIC_CONTENT_DOMAIN_HINTS = (
    "bilibili.com",
    "youtube.com",
    "douyin.com",
    "kuaishou.com",
    "xiaohongshu.com",
    "weibo.com",
    "zhihu.com",
)

TARGET_LABELS = {"title": "标题", "domain": "域名", "app": "程序", "any": "全部"}
SOURCE_LABELS = {"default": "本地规则", "user": "用户纠正", "online": "联网分类"}
GOAL_METRIC_LABELS = {
    "category": "分类",
    "domain": "域名",
    "app": "程序",
    "learning_topic": "学习主题",
}
GOAL_METRIC_HELP = {
    "category": "按内容分类统计，例如：学习、编程、视频、娱乐。",
    "domain": "按网页域名包含匹配，例如：bilibili.com、github.com。",
    "app": "按程序名包含匹配，例如：code.exe、chrome.exe。",
    "learning_topic": "按学习主题统计；匹配模式留空表示全部学习主题。",
}


def learning_feature_state(settings: FeatureSettings) -> str:
    if settings.private_title_mode:
        return "本地开启；联网增强关闭（隐私模式）"
    if settings.online_category_lookup:
        return "本地开启；联网增强开启"
    return "本地开启；联网增强关闭"


def is_generic_content_domain(domain: str) -> bool:
    lowered = domain.casefold()
    return any(hint in lowered for hint in GENERIC_CONTENT_DOMAIN_HINTS)


def cleanup_rule_title(title: str) -> str:
    value = title.strip()
    for suffix in (" - 哔哩哔哩", "_哔哩哔哩_bilibili", " - bilibili", " - YouTube"):
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
    return value[:80]


def quality_summary_text(quality: dict[str, int | float | str]) -> str:
    return (
        f"{quality.get('score', 100)}/100 · {quality.get('level', '良好')} · "
        f"仅域名 {quality.get('web_domain_only_rows', 0)} · "
        f"泛视频 {quality.get('broad_video_rows', 0)} · "
        f"低置信 {quality.get('low_confidence_rows', 0)}"
    )


def target_label(value: str) -> str:
    return TARGET_LABELS.get(value, value or "全部")


def source_label(value: str) -> str:
    return SOURCE_LABELS.get(value, value or "用户纠正")


def short_activity_hint(exe_name: str = "", domain: str = "", title: str = "", category: str = "") -> str:
    text = " ".join((exe_name, domain, title, category)).casefold()
    hints = [
        (("dazidazi.com", "dazidazi", "monkeytype", "10fastfingers", "typing", "type practice", "打字", "键盘练习"), "打字"),
        (("codex", "chatgpt", "openai", "claude", "deepseek", "kimi", "doubao"), "AI助手"),
        (("figma", "canva", "photoshop", "illustrator", "sketch"), "设计"),
        (("excalidraw", "draw.io", "diagram", "流程图"), "绘图"),
        (("notion", "obsidian", "onenote", "笔记"), "笔记"),
        (("gmail", "outlook", "mail", "邮箱", "邮件"), "邮件"),
        (("calendar", "日历", "日程"), "日程"),
        (("translate", "翻译"), "翻译"),
        (("github", "vscode", "visual studio", "pycharm", "编程", "代码"), "编程"),
        (("docs", "word", "文档"), "文档"),
        (("excel", "sheet", "表格"), "表格"),
    ]
    for keys, label in hints:
        if any(key in text for key in keys):
            return label
    if category in {"学习", "编程", "游戏", "音乐", "娱乐", "购物", "新闻", "聊天", "办公"}:
        return category
    return ""


def low_info_web_hint(domain: str = "", title: str = "", category: str = "") -> str:
    if category not in {"", "其他", "工具", "网站", "浏览器"}:
        return ""
    domain = (domain or "").strip()
    title = html.unescape((title or "").strip())
    if domain:
        return f"网页 · {domain}"
    if title:
        return f"未识别网页 · {title[:24]}"
    return ""


def data_definition_text() -> str:
    return (
        "核心口径\n"
        "1. 前台注视时长：窗口获得焦点，且未被判定为空闲时累计。它代表你正在操作或关注的主要窗口。\n"
        "2. 总运行时长：进程存在的时间，后台运行也累计。它用于判断软件开着多久，不等于你看了多久。\n"
        "3. 后台时长：总运行时长减去前台注视时长，主要用于分析常驻软件、播放器、同步工具等。\n"
        "4. 网页注视时长：浏览器在前台时，结合浏览器扩展上报的活动标签页、URL、域名和标题累计。\n"
        "5. 视频播放时长：网页视频、发声视频标签页或浏览器媒体会话播放时累计。它可能和前台注视同时发生。\n"
        "6. 音乐播放时长：酷狗、网易云、Spotify、网页音乐域名、B 站音乐视频等音乐内容播放时累计。\n"
        "7. 音乐分析：按“歌曲 + 歌手”尽量去重后统计，适合看重复播放和听歌习惯。\n\n"
        "容易混淆的地方\n"
        "- 前台注视、视频播放、音乐播放不是互斥时间。比如你前台写 OneNote，左侧网页视频播放，二者会分别记录。\n"
        "- B 站音乐视频可以同时属于“视频播放”和“音乐播放/音乐分析”，因为它既有视频画面，也是在播放音乐内容。\n"
        "- 后台音乐不会并入前台注视，但会进入音乐播放和音乐分析。\n"
        "- 当前运行列表可以切换排序：当前优先、前台排行、运行排行、按名称；行内标题只是补充说明，不参与排序。\n"
        "- 空闲时默认不累计前台注视；如果开启媒体/手写豁免，播放视频音乐或 OneNote 手写场景可继续计入。\n"
        "- 联网分类增强会在本地不确定，或 B 站等泛内容平台只得到宽泛分类时尝试细分；隐私模式下自动关闭，不会覆盖你手动添加的分类规则。"
    )


def online_feature_state(enabled: bool, private_mode: bool) -> str:
    if private_mode and enabled:
        return "关闭（隐私模式生效）"
    if private_mode:
        return "关闭（隐私模式）"
    if enabled:
        return "开启"
    return "关闭（设置关闭）"
