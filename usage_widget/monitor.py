from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
import time

import psutil
from PySide6.QtCore import QObject, QTimer, Signal

from .browser_bridge import BrowserBridge
from .classification import (
    BROAD_PLATFORM_CATEGORIES,
    clean_lookup_title,
    is_generic_content_domain,
    looks_like_video_content,
    normalize_lookup_text,
)
from .content import classify_window_content, extract_onenote_info
from .diagnostics import log_event
from .idle import idle_seconds
from .learning import (
    OnlineLearningTopicClassifier,
    domain_matches,
    has_learning_intent,
    local_learning_topic,
    normalize_text,
    should_mark_learning,
    VIDEO_LEARNING_DOMAINS,
)
from .media import MediaSessionProvider, friendly_source_name, parse_music_identity
from .music_lookup import OnlineMusicVerifier
from .native_window import foreground_window_info
from .online_category import OnlineCategoryClassifier
from .storage import Storage


MEDIA_BROWSER_HINTS = {
    "chrome",
    "msedge",
    "edge",
    "firefox",
    "brave",
    "opera",
    "vivaldi",
    "arc",
    "browser",
}

KNOWN_MUSIC_APP_HINTS = {
    "kugou",
    "kuwo",
    "cloudmusic",
    "netease",
    "spotify",
    "qqmusic",
    "qqmusic.exe",
}

WEB_MUSIC_DOMAIN_HINTS = {
    "music.163.com",
    "open.spotify.com",
    "music.youtube.com",
    "y.qq.com",
    "kugou.com",
    "kuwo.cn",
    "soundcloud.com",
    "podcasts.apple.com",
    "podcasts.google.com",
    "music.apple.com",
}

WEB_VIDEO_DOMAIN_HINTS = {
    "bilibili.com",
    "youtube.com",
    "youtu.be",
    "youku.com",
    "iqiyi.com",
    "v.qq.com",
    "mgtv.com",
    "douyin.com",
    "kuaishou.com",
}

MUSIC_TITLE_HINTS = {
    "music",
    "spotify",
    "网易云音乐",
    "qq音乐",
    "酷狗",
    "酷我",
    "音乐",
    "歌曲",
    "新歌",
    "单曲",
    "歌单",
    "专辑",
    "演唱会",
    "翻唱",
    "cover",
    "mv",
    "live",
    "ost",
    "原声",
    "podcast",
    "播客",
    "白噪音",
}

NON_MUSIC_TITLE_HINTS = {
    "tutorial",
    "course",
    "lesson",
    "lecture",
    "python",
    "java",
    "数学",
    "课程",
    "教程",
    "讲解",
    "公开课",
    "游戏",
    "攻略",
    "解说",
    "直播",
    "vlog",
}


@dataclass
class RunningProcess:
    exe_name: str
    exe_path: str
    pids: set[int] = field(default_factory=set)

    @property
    def instance_count(self) -> int:
        return len(self.pids)


class ProcessMonitor(QObject):
    updated = Signal()
    MAX_SAMPLE_DELTA_SECONDS = 300.0
    MEDIA_FALLBACK_ERROR_THRESHOLD = 3

    def __init__(self, storage: Storage, interval_ms: int = 1500, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.interval_ms = interval_ms
        self.current_processes: dict[str, RunningProcess] = {}
        self.foreground_path: str | None = None
        self.foreground_title: str = ""
        self.current_media_titles: list[str] = []
        self.current_video_titles: list[str] = []
        self.media_provider = MediaSessionProvider(min_interval=2.0)
        self.music_verifier = OnlineMusicVerifier()
        self.category_classifier = OnlineCategoryClassifier()
        self.learning_classifier = OnlineLearningTopicClassifier()
        self.browser_bridge = BrowserBridge()
        self.idle_seconds = 0.0
        self.is_idle = False
        self.is_paused = False
        self._started = False
        self.last_sample_ms = 0.0
        self.max_sample_ms = 0.0
        self.last_process_scan_ms = 0.0
        self.last_db_write_ms = 0.0
        self.slow_sample_count = 0
        self.last_cleanup_date: date | None = None
        self.current_learning_topic: str = ""
        self.current_onenote_notebook: str = ""
        self.current_category: str = ""
        self.current_foreground_exe: str = ""
        self._last_sample: datetime | None = None
        self._sampling = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.sample)

    def _is_generic_browser_process(self, exe_name: str) -> bool:
        exe = (exe_name or "").casefold()
        if not exe:
            return False
        return exe in MEDIA_BROWSER_HINTS or any(hint in exe for hint in MEDIA_BROWSER_HINTS)

    def _is_browser_process(self, exe_name: str) -> bool:
        return self._is_generic_browser_process(exe_name)

    def _is_typing_context(self, domain: str = "", title: str = "", url: str = "") -> bool:
        text = " ".join((domain or "", title or "", url or "")).casefold()
        typing_hints = (
            "dazidazi",
            "monkeytype",
            "10fastfingers",
            "keybr.com",
            "typing.com",
            "typingclub.com",
            "typing practice",
            "type practice",
            "keyboard practice",
            "words per minute",
            "wpm",
            "打字",
            "打字练习",
            "键盘练习",
        )
        return any(item in text for item in typing_hints)

    def _is_generic_content_domain(self, domain: str) -> bool:
        return is_generic_content_domain(domain)

    def _should_remember_domain_rule(self, domain: str, category: str) -> bool:
        domain_l = (domain or "").casefold()
        if not domain_l or self._is_generic_content_domain(domain_l):
            return False
        category_hints = {
            "编程": ("docs.", "developer", "dev.", "api.", "sdk", "github", "gitlab", "code", "stackoverflow"),
            "学习": ("learn", "course", "edu", "academy", "university", "school", "wiki", "scholar", "research", "arxiv", "paper", "docs."),
            "音乐": ("music", "spotify", "soundcloud", "podcast"),
            "购物": ("shop", "store", "mall", "market"),
            "新闻": ("news", "daily", "paper"),
            "聊天": ("chat", "message", "messenger", "telegram", "discord", "slack"),
            "AI 工具": ("ai", "gpt", "llm", "openai", "claude", "gemini", "deepseek", "kimi", "doubao", "yuanbao"),
        }
        hints = category_hints.get(category, ())
        return any(hint in domain_l for hint in hints)

    def _refine_generic_content_category(self, category: str, exe_name: str, domain: str, title: str, url: str = "") -> str:
        if not self._is_generic_content_domain(domain):
            return category
        if category not in BROAD_PLATFORM_CATEGORIES:
            return category
        local = self._fallback_category_for(exe_name, "", clean_lookup_title(domain, title))
        if local in {"其他", "工具", "浏览器", "网站"}:
            if category == "视频" and not looks_like_video_content(domain, title, url):
                return "网站"
            return category
        if local == "视频":
            return "视频" if looks_like_video_content(domain, title, url) else "网站"
        return local

    def _should_refine_generic_content_online(self, category: str, domain: str, title: str, settings) -> bool:
        if not settings.online_category_lookup or settings.private_title_mode:
            return False
        if category not in BROAD_PLATFORM_CATEGORIES:
            return False
        if not self._is_generic_content_domain(domain):
            return False
        clean_title = clean_lookup_title(domain, title)
        if len(clean_title) < 4:
            return False
        return len(normalize_lookup_text(clean_title)) >= 8

    def _remember_online_category_rule(
        self,
        exe_name: str,
        domain: str,
        title: str,
        category: str,
    ) -> None:
        if not category or category == "其他":
            return
        domain_l = (domain or "").casefold().strip()
        exe_l = (exe_name or "").casefold().strip()
        title_l = clean_lookup_title(domain_l, title).casefold().strip()
        if self._should_remember_domain_rule(domain_l, category):
            self.storage.add_category_rule(domain_l, category, "domain", update_existing=False, source="online")
            return
        if self._is_generic_content_domain(domain_l):
            if title_l and len(title_l) >= 8 and category not in BROAD_PLATFORM_CATEGORIES:
                self.storage.add_category_rule(title_l[:120], category, "title", update_existing=False, source="online")
            return
        if self._is_generic_browser_process(exe_l):
            return
        if exe_l and len(exe_l) >= 3:
            self.storage.add_category_rule(exe_l, category, "app", update_existing=False, source="online")
            return
        if title_l and len(title_l) >= 8:
            self.storage.add_category_rule(title_l[:80], category, "title", update_existing=False, source="online")

    def _is_handwriting_context(self, settings, proc: RunningProcess | None, title: str) -> bool:
        if not settings.handwriting_mode or not proc:
            return False
        exe = proc.exe_name.lower()
        path = proc.exe_path.lower()
        title_l = (title or "").lower()
        configured = [
            item.strip().lower()
            for item in settings.handwriting_apps.split(",")
            if item.strip()
        ]
        for pattern in configured:
            if pattern in exe or pattern in path or pattern in title_l:
                return True
        handwriting_words = ["onenote", "one note", "whiteboard", "journal", "notebook", "手写", "笔记"]
        return any(word in exe or word in title_l for word in handwriting_words)

    def _is_browser_media_source(self, source: str) -> bool:
        source_l = (source or "").lower()
        return any(hint in source_l for hint in MEDIA_BROWSER_HINTS)

    def _is_web_music_domain(self, domain: str) -> bool:
        domain_l = (domain or "").lower()
        return any(domain_l == item or domain_l.endswith("." + item) for item in WEB_MUSIC_DOMAIN_HINTS)

    def _looks_like_music_content(self, domain: str, title: str) -> bool:
        return self._looks_like_music_content_with_lookup(domain, title, False)

    def _looks_like_music_content_with_lookup(self, domain: str, title: str, online_lookup: bool) -> bool:
        text = (title or "").lower()
        if self._is_web_music_domain(domain):
            return True
        if any(hint in text for hint in MUSIC_TITLE_HINTS):
            # Check for false positives: e.g., "音乐教程" contains "音乐" but is a tutorial
            if not any(hint in text for hint in NON_MUSIC_TITLE_HINTS):
                return True
        if self._looks_like_song_title(domain, title):
            return True
        if online_lookup and self._should_lookup_music_title(domain, title):
            result = self.music_verifier.cached(title, domain)
            if result and result.is_music and result.confidence >= 0.75:
                return True
            if result is None:
                self.music_verifier.queue(title, domain)
        return False

    def _category_for(self, exe_name: str, domain: str, title: str, settings, url: str = "") -> str:
        clean_title = clean_lookup_title(domain, title)
        if self._is_codex_context(exe_name, domain, clean_title):
            return "AI 工具"
        if self._is_typing_context(domain, clean_title, url):
            return "打字"
        category = self.storage.category_for(exe_name, domain, clean_title)
        if category != "其他":
            refined_category = self._refine_generic_content_category(category, exe_name, domain, clean_title, url)
            if self._should_refine_generic_content_online(category, domain, clean_title, settings):
                result = self.category_classifier.cached(exe_name, domain, clean_title)
                if result:
                    if result.category != "其他" and result.confidence >= 0.55:
                        self._remember_online_category_rule(exe_name, domain, clean_title, result.category)
                        if result.category not in {"视频", "网站", "浏览器"}:
                            return result.category
                elif len(normalize_text(exe_name, domain, clean_title)) >= 3:
                    self.category_classifier.queue(exe_name, domain, clean_title)
            return refined_category
        if not settings.online_category_lookup or settings.private_title_mode:
            return self._fallback_category_for(exe_name, domain, clean_title, url=url)
        result = self.category_classifier.cached(exe_name, domain, clean_title)
        if result:
            if result.category != "其他" and result.confidence >= 0.55:
                self._remember_online_category_rule(exe_name, domain, clean_title, result.category)
                return result.category
        else:
            if len(normalize_text(exe_name, domain, clean_title)) >= 3:
                self.category_classifier.queue(exe_name, domain, clean_title)
        return self._fallback_category_for(exe_name, domain, clean_title, url=url)

    def _is_codex_context(self, exe_name: str = "", domain: str = "", title: str = "") -> bool:
        text = " ".join((exe_name or "", domain or "", title or "")).casefold()
        return "codex" in text or "openai codex" in text

    def _learning_topic_for(
        self,
        category: str,
        domain: str,
        title: str,
        description: str,
        kind: str,
        settings,
    ) -> str:
        try:
            return self._learning_topic_for_impl(category, domain, title, description, kind, settings)
        except Exception:
            from .diagnostics import log_event
            import traceback
            log_event(f"学习主题识别异常: category={category} domain={domain} title={str(title)[:80]} kind={kind}: {traceback.format_exc()}")
            return ""

    def _learning_topic_for_impl(
        self,
        category: str,
        domain: str,
        title: str,
        description: str,
        kind: str,
        settings,
    ) -> str:
        if settings.private_title_mode:
            return ""
        clean_title = clean_lookup_title(domain, title)
        text = normalize_text(clean_title, description)
        local = local_learning_topic(text)
        if local.topic and should_mark_learning(category, local.topic, domain, text, kind):
            return local.topic
        is_video_edu = kind == "video_playback" and domain_matches(
            domain, VIDEO_LEARNING_DOMAINS
        )
        should_online = (
            settings.online_category_lookup
            and (
                category in {"学习", "编程", "网站", "视频", "工具"}
                or has_learning_intent(domain, text, kind)
                or is_video_edu
                or (local.topic and local.confidence < 0.70)
            )
        )
        if should_online:
            result = self.learning_classifier.cached(domain, title, description)
            if result and result.topic and result.confidence >= 0.55:
                if should_mark_learning(category, result.topic, domain, text, kind):
                    return result.topic
            if result is None and len(text) >= 4:
                self.learning_classifier.queue(domain, title, description)
        if category in {"学习", "视频"} and has_learning_intent(domain, text, kind):
            return local.topic or "综合学习"
        return ""

    def _learning_category_for(self, category: str, learning_topic: str, domain: str, title: str, kind: str) -> str:
        try:
            if learning_topic and should_mark_learning(category, learning_topic, domain, title, kind):
                return "学习"
        except Exception as exc:
            log_event(
                f"学习分类判定失败: {type(exc).__name__}: category={category} topic={learning_topic} "
                f"domain={domain} title={str(title)[:80]} kind={kind}: {exc}"
            )
        return category

    def _fallback_category_for(self, exe_name: str, domain: str = "", title: str = "", url: str = "") -> str:
        exe = (exe_name or "").casefold()
        domain_l = (domain or "").casefold()
        title_l = clean_lookup_title(domain_l, title).casefold()
        text = f"{exe} {domain_l} {title_l}"

        if self._is_codex_context(exe, domain_l, title_l):
            return "AI 工具"

        if "applicationframehost.exe" in exe and "onenote" in title_l:
            return "学习"

        system_apps = (
            "explorer.exe",
            "taskmgr.exe",
            "control.exe",
            "systemsettings.exe",
            "cmd.exe",
            "powershell.exe",
            "windowsterminal.exe",
            "terminal",
            "applicationframehost.exe",
        )
        if any(item in exe for item in system_apps):
            return "系统软件"

        ai_priority_hints = (
            "codex", "openai codex", "chatgpt", "openai", "claude", "gemini",
            "deepseek", "kimi", "doubao", "copilot", "llm", "ai assistant",
            "元宝", "豆包", "通义", "文心", "星火", "智谱",
        )
        if any(item in text for item in ai_priority_hints):
            return "AI 工具"

        chat_hints = ("qq", "wechat", "weixin", "telegram", "discord", "slack", "whatsapp", "聊天", "消息", "群聊")
        if any(item in text for item in chat_hints):
            return "聊天"

        coding_hints = (
            "code",
            "cursor",
            "windsurf",
            "trae",
            "github",
            "gitlab",
            "stackoverflow",
            "developer",
            "docs.",
            "api",
            "python",
            "javascript",
            "typescript",
            "vibe coding",
            "vibecoding",
            "编程",
            "代码",
            "开发",
            # Embedded / MCU
            "keil",
            "stm32",
            "cubemx",
            "cubeide",
            "arm",
            "cortex-m",
            "risc-v",
            "esp32",
            "arduino",
            "mplab",
            "iar",
            "segger",
            "openocd",
            "rtos",
            "freertos",
            "ucos",
            "rt-thread",
            "嵌入式",
            "单片机",
            "mcu",
            "固件",
            # FPGA / HDL
            "vivado",
            "quartus",
            "modelsim",
            "verilog",
            "vhdl",
            "fpga",
            "soc",
            "hls",
            "xilinx",
            # EDA / PCB
            "altium",
            "kicad",
            "pcb",
            "schematic",
            "电路",
            "原理图",
            "layout",
            "布线",
            # MATLAB / Scientific
            "matlab",
            "simulink",
            "octave",
            "labview",
            "ansys",
            "comsol",
            "仿真",
            "数值计算",
            "有限元",
            # CAD
            "autocad",
            "solidworks",
            "fusion",
            "catia",
            "cad",
            "建模",
            "工程图",
            # Game engines
            "unity",
            "unreal",
            "godot",
            "gamemaker",
            "游戏引擎",
        )
        if any(item in text for item in coding_hints):
            return "编程"

        ai_hints = (
            "chatgpt", "openai", "claude", "gemini", "deepseek", "kimi", "doubao",
            "copilot", "llm", "ai 工具",
            "元宝", "yuanbao", "豆包", "通义", "tongyi", "文心", "wenxin",
            "星火", "xinghuo", "智脑", "qianwen", "百川", "baichuan",
            "chatglm", "智谱", "zhipu", "minimax", "海螺", "moonshot",
            "阶跃星辰", "stepfun", "零一万物", "abab", "codex", "openai codex",
        )
        if any(item in text for item in ai_hints):
            return "AI 工具"

        music_hints = ("music", "spotify", "kugou", "kuwo", "cloudmusic", "song", "album", "音乐", "歌曲", "歌单", "专辑")
        if any(item in text for item in music_hints) and not has_learning_intent(domain_l, title_l):
            return "音乐"

        game_hints = (
            "game", "steam", "epicgames", "riot", "minecraft", "roblox", "genshin",
            "游戏", "攻略", "原神", "英雄联盟", "王者荣耀", "崩坏", "星穹铁道",
            "实况", "试玩", "通关", "抽卡", "boss战", "游戏解说", "gameplay",
        )
        if any(item in text for item in game_hints):
            if not has_learning_intent(domain_l, title_l) or any(item in text for item in ("实况", "娱乐", "直播", "攻略", "gameplay")):
                return "游戏"

        entertainment_hints = (
            "douyin", "tiktok", "kuaishou", "xiaohongshu", "weibo", "reddit",
            "funny", "娱乐", "搞笑", "搞笑合集", "笑到", "整活", "鬼畜", "沙雕",
            "短视频", "热搜", "吐槽", "reaction", "vlog", "日常", "生活",
            "综艺", "番剧", "动漫", "动画", "二创", "影视解说", "名场面",
        )
        if any(item in text for item in entertainment_hints) and not has_learning_intent(domain_l, title_l):
            return "娱乐"

        learning_hints = (
            "course", "lecture", "lesson", "learn", "edu", "university", "wikipedia", "zhihu",
            "教程", "课程", "学习", "讲解", "论文", "考试", "期末", "期中", "不挂科",
            "突击", "速成", "冲刺", "备考", "考点", "蜂考", "大学物理", "光学",
            "知识", "科普", "详解", "入门", "公开课",
            "法律", "法学", "刑法", "民法", "法考", "司法考试", "罗翔",
        )
        if any(item in text for item in learning_hints):
            return "学习"
        if has_learning_intent(domain_l, title_l):
            return "学习"

        if any(item in text for item in music_hints):
            return "音乐"

        if any(item in text for item in game_hints):
            return "游戏"

        shopping_hints = (
            "shop", "store", "taobao", "tmall", "jd.com", "amazon", "购物",
            "商城", "电商", "开箱", "测评", "评测", "好物", "优惠", "省钱",
            "618", "双十一", "值得买",
        )
        if any(item in text for item in shopping_hints):
            return "购物"

        news_hints = ("news", "headline", "breaking", "新闻", "资讯", "热点", "时事", "国际", "财经新闻", "日报")
        if any(item in text for item in news_hints):
            return "新闻"

        if any(item in text for item in entertainment_hints):
            return "娱乐"

        office_hints = ("office", "word", "excel", "powerpoint", "onenote", "notion", "lark", "feishu", "dingtalk", "teams", "办公", "文档", "笔记", "会议")
        if any(item in text for item in office_hints):
            return "办公"

        if self._is_typing_context(domain_l, title_l, url):
            return "打字"

        if looks_like_video_content(domain_l, title_l, url):
            return "视频"

        if exe in MEDIA_BROWSER_HINTS or any(browser in exe for browser in MEDIA_BROWSER_HINTS):
            return "网站" if domain_l else "浏览器"
        if domain_l:
            return "网站"
        if exe:
            return "工具"
        return "其他"

    def _should_lookup_music_title(self, domain: str, title: str) -> bool:
        domain_l = (domain or "").lower()
        if not any(item in domain_l for item in ("bilibili.com", "youtube.com", "youtu.be", "music.youtube.com")):
            return False
        text = (title or "").strip()
        if len(text) < 6 or len(text) > 160:
            return False
        if any(hint in text.lower() for hint in NON_MUSIC_TITLE_HINTS):
            return False
        return any(sep in text for sep in (" - ", " — ", " – ", "|", "《", "<", ":", "："))

    def _looks_like_song_title(self, domain: str, title: str) -> bool:
        domain_l = (domain or "").lower()
        # Allow detection on known video domains, or when domain is empty (SMTC path without browser extension)
        if domain_l and not any(item in domain_l for item in ("bilibili.com", "youtube.com", "youtu.be", "music.youtube.com")):
            return False
        text = (title or "").strip()
        if not text:
            return False
        text_l = text.lower()
        if any(hint in text_l for hint in NON_MUSIC_TITLE_HINTS):
            return False
        if not any(sep in text for sep in (" - ", " — ", " – ", "|", "《", "<", ":", "：")):
            return False
        song, artist, _label = parse_music_identity(text, source="browser", domain=domain)
        if not song or not artist:
            return False
        if len(song) > 90 or len(artist) > 60:
            return False
        return True

    def _known_music_processes(self, groups: dict[str, RunningProcess]) -> list[RunningProcess]:
        result = []
        seen = set()
        for proc in groups.values():
            combined = f"{proc.exe_name} {proc.exe_path}".lower()
            if any(hint in combined for hint in KNOWN_MUSIC_APP_HINTS):
                key = proc.exe_path.lower()
                if key not in seen:
                    seen.add(key)
                    result.append(proc)
        return result[:3]

    def _browser_playback_kind(self, tab) -> str:
        domain = (getattr(tab, "domain", "") or "").lower()
        url = (getattr(tab, "url", "") or "").lower()
        title = " ".join(
            [
                getattr(tab, "title", "") or "",
                getattr(tab, "h1", "") or "",
                getattr(tab, "description", "") or "",
            ]
        ).lower()
        if getattr(tab, "muted", False):
            return "muted"
        if self._is_typing_context(domain, title, url):
            return "web_page"
        if self._is_web_music_domain(domain):
            return "media_playback"
        if any(hint in url for hint in ("/playlist", "/album", "/artist", "/song", "/podcast")):
            if any(domain == item or domain.endswith("." + item) for item in WEB_MUSIC_DOMAIN_HINTS):
                return "media_playback"
        if self._looks_like_music_content(domain, title):
            return "media_playback"
        has_video = bool(getattr(tab, "has_video", False))
        media_state = (getattr(tab, "media_state", "") or "").casefold()
        if has_video and media_state in {"playing", "paused", "present"}:
            return "video_playback"
        if looks_like_video_content(domain, title, url):
            return "video_playback"
        if getattr(tab, "has_audio", False) and not getattr(tab, "has_video", False):
            return "media_playback"
        return "web_page"

    def _browser_tab_has_media_signal(self, tab) -> bool:
        if not tab or getattr(tab, "muted", False):
            return False
        kind = self._browser_playback_kind(tab)
        return kind in {"video_playback", "media_playback"}

    def _music_label(self, title: str, source: str = "", domain: str = "") -> str:
        _song, _artist, label = parse_music_identity(title, source=source, domain=domain)
        return label or title

    def _latest_browser_tab(self, settings):
        if not settings.track_browser_urls:
            return None
        try:
            return self.browser_bridge.latest()
        except Exception as exc:
            log_event(f"读取浏览器当前标签失败: {type(exc).__name__}: {exc}")
            return None

    def start(self) -> None:
        self._started = True
        self.browser_bridge.start()
        self._timer.start(self.interval_ms)
        QTimer.singleShot(250, self._sample_after_start)

    def stop(self) -> None:
        self._started = False
        self._timer.stop()
        self.browser_bridge.stop()

    def _sample_after_start(self) -> None:
        if self._started and self._timer.isActive():
            self.sample(write=False)

    def _sample_delta(self, now: datetime, write: bool) -> float:
        if self._last_sample is None:
            self._last_sample = now
            return 0.0
        observed = max(0.0, (now - self._last_sample).total_seconds())
        self._last_sample = now
        if not write:
            return 0.0
        if observed > self.MAX_SAMPLE_DELTA_SECONDS:
            log_event(
                f"采样间隔过长，按 {self.MAX_SAMPLE_DELTA_SECONDS:.0f}s 计入：observed={observed:.1f}s"
            )
            return self.MAX_SAMPLE_DELTA_SECONDS
        return observed

    def sample(self, write: bool = True) -> None:
        if self._sampling:
            log_event("采样仍在执行，跳过本次定时器触发")
            return
        self._sampling = True
        sample_started = time.perf_counter()
        try:
            self._sample_impl(write=write, sample_started=sample_started)
        finally:
            self._sampling = False

    def _sample_impl(self, write: bool, sample_started: float) -> None:
        now = datetime.now()
        delta = self._sample_delta(now, write)

        ignored = set(self.storage.ignored_processes())
        groups: dict[str, RunningProcess] = {}
        pid_to_path: dict[int, str] = {}

        scan_started = time.perf_counter()
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                info = proc.info
                pid = int(info.get("pid") or 0)
                name = str(info.get("name") or "").strip()
                if not name:
                    continue
                lower_name = name.lower()
                if lower_name in ignored or not lower_name.endswith(".exe"):
                    continue
                try:
                    exe = proc.exe()
                except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                    exe = ""
                exe_path = str(exe) if exe else lower_name
                key = str(Path(exe_path)).lower() if exe else lower_name
                item = groups.get(key)
                if item is None:
                    item = RunningProcess(exe_name=name, exe_path=exe_path)
                    groups[key] = item
                item.pids.add(pid)
                pid_to_path[pid] = key
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        self.last_process_scan_ms = (time.perf_counter() - scan_started) * 1000.0

        fg_window = foreground_window_info()
        fg_pid = fg_window.pid if fg_window else None
        fg_title = fg_window.title if fg_window else ""
        fg_path = pid_to_path.get(fg_pid) if fg_pid else None
        self.foreground_path = groups[fg_path].exe_path if fg_path and fg_path in groups else None
        self.foreground_title = fg_title if self.foreground_path else ""
        self.current_learning_topic = ""
        self.current_onenote_notebook = ""
        self.current_category = ""
        self.current_foreground_exe = ""

        settings = self.storage.load_settings()
        audible_tabs = []
        if settings.track_browser_urls:
            try:
                audible_tabs = self.browser_bridge.audible_tabs()
            except Exception as exc:
                log_event(f"读取浏览器音频标签失败: {type(exc).__name__}: {exc}")
        if settings.track_media_sessions:
            media_items = self.media_provider.refresh_sync(timeout_seconds=0.8)
        else:
            media_items = self.media_provider.current_items()
        media_activity = bool(audible_tabs or media_items)
        foreground_proc = groups.get(fg_path) if fg_path else None
        handwriting_context = self._is_handwriting_context(settings, foreground_proc, fg_title)
        self.idle_seconds = idle_seconds()
        raw_idle = self.idle_seconds >= settings.idle_threshold_seconds
        idle_overridden = (
            raw_idle
            and (
                (settings.media_activity_keeps_attention and media_activity)
                or handwriting_context
            )
        )
        self.is_idle = raw_idle and not idle_overridden
        self.is_paused = settings.pause_tracking
        should_count_attention = not self.is_idle and not self.is_paused

        if write:
            samples = []
            content_samples = []
            timeline_events = []
            event_start = now - timedelta(seconds=delta)
            for key, proc in groups.items():
                samples.append(
                    {
                        "exe_name": proc.exe_name,
                        "exe_path": proc.exe_path,
                        "running_seconds": delta,
                        "foreground_seconds": delta if should_count_attention and key == fg_path else 0.0,
                    }
                )
            if settings.track_window_titles and should_count_attention and fg_path and fg_path in groups and fg_title:
                proc = groups[fg_path]
                tab = self._latest_browser_tab(settings) if self._is_browser_process(proc.exe_name) else None
                title = tab.title if tab and tab.title else fg_title
                url = tab.url if tab else ""
                content = classify_window_content(
                    proc.exe_name,
                    title,
                    url=url,
                    private_title_mode=settings.private_title_mode,
                )
                if content:
                    onenote_is, onenote_nb, onenote_learning = extract_onenote_info(fg_title, proc.exe_name)
                    if onenote_is:
                        self.current_onenote_notebook = onenote_nb
                    page_context = normalize_text(
                        content.title,
                        getattr(tab, "h1", "") if tab else "",
                        getattr(tab, "description", "") if tab else "",
                    )
                    category = self._category_for(proc.exe_name, content.domain, page_context, settings, url=content.url)
                    if onenote_learning:
                        category = "学习"
                    learning_topic = self._learning_topic_for(
                        category,
                        content.domain,
                        content.title,
                        normalize_text(getattr(tab, "h1", "") if tab else "", getattr(tab, "description", "") if tab else ""),
                        content.kind,
                        settings,
                    )
                    category = self._learning_category_for(category, learning_topic, content.domain, page_context, content.kind)
                    if onenote_learning and onenote_nb:
                        learning_topic = onenote_nb
                    self.current_learning_topic = learning_topic
                    self.current_category = category
                    self.current_foreground_exe = proc.exe_name
                    content_samples.append(
                        {
                            "kind": content.kind,
                            "exe_name": proc.exe_name,
                            "exe_path": proc.exe_path,
                            "content_key": content.key,
                            "content_title": content.title,
                            "content_url": content.url,
                            "content_domain": content.domain,
                            "category": category,
                            "learning_topic": learning_topic,
                            "attention_seconds": delta,
                            "background_seconds": 0.0,
                        }
                    )
                    timeline_events.append(
                        {
                            "start_time": event_start,
                            "end_time": now,
                            "kind": content.kind,
                            "title": content.title,
                            "seconds": delta,
                            "app_name": proc.exe_name,
                            "app_path": proc.exe_path,
                            "category": category,
                            "learning_topic": learning_topic,
                            "extra": content.url,
                        }
                    )
            elif self.is_idle and fg_title:
                timeline_events.append(
                    {
                        "start_time": event_start,
                        "end_time": now,
                        "kind": "idle",
                        "title": "空闲",
                        "seconds": delta,
                        "category": "空闲",
                    }
                )

            web_media_titles = []
            if audible_tabs and not self.is_paused:
                video_titles = []
                seen_video_keys = set()
                for tab in audible_tabs:
                    kind = self._browser_playback_kind(tab)
                    if kind == "muted":
                        continue
                    title = tab.title or tab.domain or tab.url
                    if not title:
                        continue
                    key = tab.url or f"{tab.domain}:{title.lower()}"
                    if key in seen_video_keys:
                        continue
                    seen_video_keys.add(key)
                    category_text = " ".join(part for part in (title, getattr(tab, "h1", ""), getattr(tab, "description", "")) if part)
                    is_music_content = self._looks_like_music_content_with_lookup(
                        tab.domain,
                        category_text,
                        settings.online_music_lookup and not settings.private_title_mode,
                    )
                    category = "音乐" if is_music_content else self._category_for("browser", tab.domain, category_text, settings, url=tab.url)
                    learning_topic = ""
                    if not is_music_content:
                        learning_topic = self._learning_topic_for(
                            category,
                            tab.domain,
                            title,
                            normalize_text(getattr(tab, "h1", ""), getattr(tab, "description", "")),
                            kind,
                            settings,
                        )
                        category = self._learning_category_for(category, learning_topic, tab.domain, category_text, kind)
                    if is_music_content:
                        title = getattr(tab, "h1", "") or title
                        title = self._music_label(title, source=tab.browser, domain=tab.domain)
                        web_media_titles.append(title)
                    if kind == "video_playback":
                        video_titles.append(title)
                    content_samples.append(
                        {
                            "kind": kind,
                            "exe_name": tab.browser,
                            "exe_path": tab.browser,
                            "content_key": f"{kind}:{key}",
                            "content_title": title,
                            "content_url": tab.url,
                            "content_domain": tab.domain,
                            "category": category,
                            "learning_topic": learning_topic,
                            "attention_seconds": 0.0,
                            "background_seconds": delta,
                        }
                    )
                    timeline_events.append(
                        {
                            "start_time": event_start,
                            "end_time": now,
                            "kind": kind,
                            "title": title,
                            "seconds": delta,
                            "app_name": tab.browser,
                            "app_path": tab.browser,
                            "category": category,
                            "learning_topic": learning_topic,
                            "extra": tab.url,
                        }
                    )
                self.current_video_titles = video_titles[:3]
            else:
                self.current_video_titles = []

            if settings.track_media_sessions and not self.is_paused:
                media_titles = list(web_media_titles)
                fallback_video_titles = []
                for item in media_items:
                    display_title = item.display_title
                    if not display_title:
                        continue
                    is_browser_media = self._is_browser_media_source(item.source)
                    if is_browser_media and audible_tabs:
                        continue
                    content_url = ""
                    content_domain = ""
                    if is_browser_media:
                        latest_tab = self._latest_browser_tab(settings)
                        if latest_tab and self._browser_tab_has_media_signal(latest_tab):
                            browser_kind = self._browser_playback_kind(latest_tab)
                            kind = browser_kind
                            content_url = latest_tab.url
                            content_domain = latest_tab.domain
                        else:
                            kind = "video_playback" if looks_like_video_content("", display_title) else "media_playback"
                    else:
                        kind = "media_playback"
                    is_music_browser_media = is_browser_media and self._looks_like_music_content_with_lookup(
                        content_domain,
                        display_title,
                        settings.online_music_lookup and not settings.private_title_mode,
                    )
                    if kind == "media_playback" or is_music_browser_media:
                        display_title = self._music_label(display_title, source=item.source, domain=content_domain)
                    if is_music_browser_media:
                        category = "音乐"
                        learning_topic = ""
                    else:
                        category = self._category_for("browser" if is_browser_media else item.source, content_domain, display_title, settings, url=content_url)
                        learning_topic = self._learning_topic_for(
                            category,
                            content_domain,
                            display_title,
                            "",
                            kind,
                            settings,
                        )
                        category = self._learning_category_for(category, learning_topic, content_domain, display_title, kind)
                    if is_browser_media and kind == "video_playback" and not is_music_browser_media:
                        fallback_video_titles.append(display_title)
                    else:
                        media_titles.append(display_title)
                    content_samples.append(
                        {
                            "kind": kind,
                            "exe_name": item.source,
                            "exe_path": item.source,
                            "content_key": f"{kind}:{item.source}:{display_title.lower()}",
                            "content_title": display_title,
                            "content_url": content_url,
                            "content_domain": content_domain,
                            "category": category,
                            "learning_topic": learning_topic,
                            "attention_seconds": 0.0,
                            "background_seconds": delta,
                        }
                    )
                    timeline_events.append(
                        {
                            "start_time": event_start,
                            "end_time": now,
                            "kind": kind,
                            "title": display_title,
                            "seconds": delta,
                            "app_name": item.source,
                            "app_path": item.source,
                            "category": category,
                            "learning_topic": learning_topic,
                        }
                    )
                self.current_media_titles = media_titles[:3]
                if fallback_video_titles and not self.current_video_titles:
                    self.current_video_titles = fallback_video_titles[:3]
                if (
                    not media_items
                    and not audible_tabs
                    and self.media_provider.consecutive_errors >= self.MEDIA_FALLBACK_ERROR_THRESHOLD
                ):
                    for proc in self._known_music_processes(groups):
                        display_title = f"{friendly_source_name(proc.exe_name)}（后台播放兜底）"
                        category = self._category_for(proc.exe_name, "", display_title, settings)
                        media_titles.append(display_title)
                        content_samples.append(
                            {
                                "kind": "media_playback",
                                "exe_name": proc.exe_name,
                                "exe_path": proc.exe_path,
                                "content_key": f"media_fallback:{proc.exe_path.lower()}",
                                "content_title": display_title,
                                "content_url": "",
                                "content_domain": "",
                                "category": category,
                                "learning_topic": "",
                                "attention_seconds": 0.0,
                                "background_seconds": delta,
                            }
                        )
                        timeline_events.append(
                            {
                                "start_time": event_start,
                                "end_time": now,
                                "kind": "media_playback",
                                "title": display_title,
                                "seconds": delta,
                                "app_name": proc.exe_name,
                                "app_path": proc.exe_path,
                                "category": category,
                                "learning_topic": "",
                            }
                        )
                    self.current_media_titles = media_titles[:3]
            else:
                self.current_media_titles = web_media_titles[:3]
            db_started = time.perf_counter()
            self.storage.record_activity(samples, content_samples, timeline_events, now)
            self.last_db_write_ms = (time.perf_counter() - db_started) * 1000.0
            if self.last_cleanup_date != now.date() and settings.timeline_retention_days > 0:
                removed = self.storage.cleanup_old_timeline_events(settings.timeline_retention_days)
                self.last_cleanup_date = now.date()
                if removed:
                    log_event(f"清理旧时间线 {removed} 条，保留 {settings.timeline_retention_days} 天")

        self.current_processes = groups
        self.last_sample_ms = (time.perf_counter() - sample_started) * 1000.0
        self.max_sample_ms = max(self.max_sample_ms, self.last_sample_ms)
        if self.last_sample_ms >= 900 or self.last_db_write_ms >= 350 or self.last_process_scan_ms >= 650:
            self.slow_sample_count += 1
            log_event(
                "慢采样 "
                f"total={self.last_sample_ms:.0f}ms "
                f"scan={self.last_process_scan_ms:.0f}ms "
                f"db={self.last_db_write_ms:.0f}ms "
                f"processes={len(groups)} "
                f"foreground={self.foreground_title[:80]}"
            )
        self.updated.emit()
