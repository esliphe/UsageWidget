from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request
import html as html_lib
from dataclasses import dataclass

from .classification import (
    BROAD_PLATFORM_CATEGORIES,
    clean_lookup_title,
    is_generic_content_domain,
    normalize_lookup_text,
)


USER_AGENT = "UsageWidget"
DESKTOP_USER_AGENT = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) {USER_AGENT}"

@dataclass(frozen=True)
class CategoryLookupResult:
    category: str
    confidence: float
    source: str
    summary: str = ""


class OnlineCategoryClassifier:
    MAX_CACHE_SIZE = 1200

    CATEGORY_HINTS = {
        "系统软件": {
            "windows",
            "microsoft windows",
            "system settings",
            "file explorer",
            "task manager",
            "terminal",
            "powershell",
            "command prompt",
            "control panel",
            "系统",
            "设置",
            "文件资源管理器",
            "任务管理器",
            "终端",
            "控制面板",
        },
        "学习": {
            "course",
            "lecture",
            "lesson",
            "learn",
            "education",
            "university",
            "school",
            "tutorial",
            "mooc",
            "课程",
            "公开课",
            "学习",
            "教学",
            "教程",
            "知识",
            "科普",
            "详解",
            "讲义",
            "考试",
            "期末",
            "期中",
            "不挂科",
            "挂科",
            "突击",
            "速成",
            "冲刺",
            "备考",
            "刷题",
            "考点",
            "大学物理",
            "光学",
            "蜂考",
            "高等数学",
            "线性代数",
            "英语",
            "exam",
            "homework",
            "textbook",
            "paper",
            "research",
            "law",
            "legal",
            "jurisprudence",
            "法律",
            "法学",
            "刑法",
            "民法",
            "法考",
            "司法考试",
            "罗翔",
        },
        "编程": {
            "programming",
            "developer",
            "software development",
            "python",
            "java",
            "javascript",
            "typescript",
            "github",
            "git",
            "api",
            "docs",
            "documentation",
            "代码",
            "编程",
            "开发",
            "程序",
            "文档",
            "算法",
            "vibe coding",
            "vibecoding",
            "cursor",
            "windsurf",
            "replit",
            "vercel",
            "netlify",
            "docker",
            "npm",
            "pypi",
            "代码生成",
            # Embedded / MCU
            "embedded",
            "microcontroller",
            "keil",
            "stm32",
            "cubemx",
            "cubeide",
            "arm cortex",
            "risc-v",
            "esp32",
            "arduino",
            "mplab",
            "iar",
            "segger",
            "openocd",
            "rtos",
            "freertos",
            "firmware",
            "hal",
            "寄存器",
            "嵌入式",
            "单片机",
            "mcu",
            "固件",
            "中断",
            "定时器",
            "gpio",
            "uart",
            "spi",
            "i2c",
            "can总线",
            "pwm",
            "adc",
            "dac",
            "dma",
            "bootloader",
            # FPGA / HDL
            "fpga",
            "vivado",
            "quartus",
            "modelsim",
            "verilog",
            "vhdl",
            "xilinx",
            "altera",
            "hls",
            "soc",
            "zynq",
            # EDA / PCB
            "altium",
            "kicad",
            "pcb",
            "schematic",
            "电路",
            "原理图",
            "layout",
            "布线",
            "eagle",
            "easyeda",
            # MATLAB / Scientific
            "matlab",
            "simulink",
            "labview",
            "octave",
            "ansys",
            "comsol",
            "mathematica",
            "仿真",
            "数值计算",
            "有限元",
            "信号处理",
            # CAD / 3D modeling
            "autocad",
            "solidworks",
            "catia",
            "fusion360",
            "sketchup",
            "freecad",
            "inventor",
            "revit",
            "rhino",
            "creo",
            "cad",
            "建模",
            "工程图",
            "bim",
            # Game Engines
            "unity",
            "unreal engine",
            "godot",
            "gamemaker",
            "游戏引擎",
        },
        "AI 工具": {
            "artificial intelligence",
            "machine learning",
            "large language model",
            "chatgpt",
            "openai",
            "claude",
            "gemini",
            "copilot",
            "llm",
            "ai assistant",
            "ai chatbot",
            "ai model",
            "人工智能",
            "大语言模型",
            "大模型",
            "模型",
            "deepseek",
            "kimi",
            "doubao",
            "豆包",
            "perplexity",
            "bolt.new",
            "lovable",
            "codex",
            "openai codex",
            # Chinese AI assistants (ambiguous names)
            "yuanbao",
            "元宝",
            "tongyi",
            "通义",
            "通义千问",
            "qianwen",
            "wenxin",
            "文心一言",
            "文心",
            "xinghuo",
            "讯飞星火",
            "星火",
            "chatglm",
            "zhipu",
            "智谱",
            "minimax",
            "baichuan",
            "百川",
            "moonshot",
            "kimi",
            "stepfun",
            "阶跃星辰",
            "零一万物",
        },
        "游戏": {
            "game",
            "gaming",
            "steam",
            "esports",
            "walkthrough",
            "minecraft",
            "roblox",
            "genshin",
            "游戏",
            "攻略",
            "实况",
            "试玩",
            "通关",
            "抽卡",
            "游戏解说",
            "电竞",
            "原神",
            "崩坏",
            "王者荣耀",
            "英雄联盟",
        },
        "音乐": {
            "music",
            "song",
            "album",
            "artist",
            "spotify",
            "soundcloud",
            "lyrics",
            "mv",
            "concert",
            "音乐",
            "歌曲",
            "歌手",
            "专辑",
            "演唱会",
        },
        "视频": {
            "video",
            "streaming",
            "youtube",
            "bilibili",
            "movie",
            "tv",
            "episode",
            "视频",
            "影视",
            "电影",
            "电视剧",
            "直播",
        },
        "社交": {
            "social network",
            "community",
            "chat",
            "messaging",
            "forum",
            "twitter",
            "x.com",
            "reddit",
            "telegram",
            "discord",
            "社交",
            "聊天",
            "社区",
            "论坛",
        },
        "聊天": {
            "instant messaging",
            "messenger",
            "chat app",
            "qq",
            "wechat",
            "weixin",
            "telegram",
            "discord",
            "slack",
            "whatsapp",
            "teams chat",
            "聊天",
            "消息",
            "微信",
            "qq",
            "群聊",
        },
        "娱乐": {
            "entertainment",
            "funny",
            "variety show",
            "short video",
            "meme",
            "douyin",
            "tiktok",
            "kuaishou",
            "xiaohongshu",
            "reddit",
            "娱乐",
            "搞笑",
            "搞笑合集",
            "笑到",
            "整活",
            "鬼畜",
            "沙雕",
            "短视频",
            "综艺",
            "热搜",
            "小红书",
            "吐槽",
            "reaction",
            "vlog",
            "日常",
            "生活",
            "影视解说",
            "番剧",
            "动漫",
            "动画",
            "二创",
        },
        "新闻": {
            "news",
            "newspaper",
            "journalism",
            "breaking news",
            "新闻",
            "资讯",
            "日报",
            "热点",
            "时事",
            "国际新闻",
            "财经新闻",
        },
        "购物": {
            "shopping",
            "e-commerce",
            "marketplace",
            "store",
            "amazon",
            "taobao",
            "jd.com",
            "购物",
            "商城",
            "电商",
            "开箱",
            "测评",
            "评测",
            "好物",
            "优惠",
        },
        "办公": {
            "productivity",
            "office",
            "spreadsheet",
            "document",
            "presentation",
            "onenote",
            "notion",
            "office",
            "办公",
            "文档",
            "笔记",
            "表格",
            "幻灯片",
        },
        "工具": {
            "utility",
            "tool",
            "file manager",
            "system",
            "download",
            "compress",
            "typing",
            "typing practice",
            "type practice",
            "keyboard practice",
            "words per minute",
            "wpm",
            "打字",
            "打字练习",
            "键盘练习",
            "工具",
            "下载",
            "压缩",
            "系统",
            "utility software",
            "productivity tool",
            "screenshot",
            "launcher",
            "search tool",
        },
    }

    def __init__(self, min_interval: float = 12.0, ttl_seconds: float = 7 * 86400.0) -> None:
        self.min_interval = min_interval
        self.ttl_seconds = ttl_seconds
        self.error_ttl_seconds = 900.0  # Only cache errors for 15 minutes
        self.max_workers = 6
        self.max_pending = 80
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, CategoryLookupResult]] = {}
        self._pending: set[str] = set()
        self._last_request_at = 0.0
        self._active_workers = 0
        self.last_error = ""
        self.last_source = ""
        self.last_query = ""
        self.last_provider_errors = ""

    def cached(self, exe_name: str, domain: str = "", title: str = "") -> CategoryLookupResult | None:
        key = self._key(exe_name, domain, title)
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

    def queue(self, exe_name: str, domain: str = "", title: str = "") -> None:
        key = self._key(exe_name, domain, title)
        if not key:
            return
        with self._lock:
            if key in self._pending or key in self._cache:
                return
            if len(self._pending) >= self.max_pending:
                self.last_error = "Online category queue full"
                return
            if self._active_workers >= self.max_workers:
                return  # Drop request if too many workers are already running
            self._pending.add(key)
            self._active_workers += 1
        try:
            thread = threading.Thread(
                target=self._worker,
                args=(key, exe_name, domain, title),
                name="UsageWidgetCategoryLookup",
                daemon=True,
            )
            thread.start()
        except Exception as exc:
            with self._lock:
                self._pending.discard(key)
                self._active_workers -= 1
                self.last_error = f"Thread start failed: {exc}"

    def lookup_sync(self, exe_name: str, domain: str = "", title: str = "") -> CategoryLookupResult:
        key = self._key(exe_name, domain, title)
        if not key:
            return CategoryLookupResult("其他", 0.0, "empty")
        cached = self.cached(exe_name, domain, title)
        if cached is not None:
            return cached
        result = self._lookup(exe_name, domain, title)
        with self._lock:
            self._cache[key] = (time.monotonic(), result)
            self._evict_locked()
            if result.category != "其他" or result.source not in {"multi", "error"}:
                self.last_error = ""
            self.last_source = result.source
        return result

    def _worker(self, key: str, exe_name: str, domain: str, title: str) -> None:
        try:
            with self._lock:
                now = time.monotonic()
                wait = max(0.0, self.min_interval - (now - self._last_request_at))
                self._last_request_at = now + wait
            if wait:
                time.sleep(wait)
            result = self._lookup(exe_name, domain, title)
            with self._lock:
                self._cache[key] = (time.monotonic(), result)
                self._evict_locked()
                if result.category != "其他" or result.source not in {"multi", "error"}:
                    self.last_error = ""
                self.last_source = result.source
        except Exception as exc:
            with self._lock:
                self._cache[key] = (time.monotonic(), CategoryLookupResult("其他", 0.0, "error"))
                self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                self._pending.discard(key)
                self._active_workers -= 1

    def _lookup(self, exe_name: str, domain: str, title: str) -> CategoryLookupResult:
        title_for_lookup = clean_lookup_title(domain, title)
        query = self._query(exe_name, domain, title_for_lookup)
        self.last_query = query
        if not query:
            return CategoryLookupResult("其他", 0.0, "empty")

        category, confidence = self._classify_text(query)
        title_category, title_confidence = self._classify_text(title_for_lookup)
        if (
            title_category != "其他"
            and title_confidence >= 0.62
            and (
                not self._is_generic_content_domain(domain)
                or title_category not in {"视频", "网站"}
            )
        ):
            return CategoryLookupResult(title_category, title_confidence, "local-title", title_for_lookup[:260])
        if category != "其他" and confidence >= 0.62 and not self._is_broad_platform_bucket(domain, category):
            return CategoryLookupResult(category, confidence, "local-query", query[:260])

        providers = []
        if domain and not self._is_generic_content_domain(domain):
            providers.append(lambda: self._lookup_site_metadata(query, domain))
        providers.append(lambda: self._lookup_baidu(query, domain))
        providers.extend(
            [
                lambda: self._lookup_duckduckgo(query, domain),
                lambda: self._lookup_duckduckgo_html(query, domain),
                lambda: self._lookup_wikipedia(query, domain, "zh"),
                lambda: self._lookup_wikipedia(query, domain, "en"),
            ]
        )

        best = CategoryLookupResult("其他", 0.0, "multi")
        provider_errors = []
        for provider in providers:
            try:
                result = provider()
            except Exception as exc:
                provider_errors.append(f"{type(exc).__name__}: {exc}")
                self.last_error = provider_errors[-1]
                continue
            candidate = result if result.category != "其他" else None
            if result.source in {"duckduckgo", "duckduckgo-html", "baidu"} and result.summary:
                fallback_category, fallback_conf = self._classify_text(" ".join((query, result.summary)))
                if fallback_category != "其他" and fallback_conf >= 0.55:
                    candidate = CategoryLookupResult(fallback_category, fallback_conf, result.source, result.summary)
            if candidate and candidate.confidence > best.confidence:
                best = candidate
            if candidate and candidate.confidence >= 0.70:
                self.last_provider_errors = " | ".join(provider_errors[-3:])
                return candidate

        if best.category != "其他" and best.confidence >= 0.55:
            self.last_provider_errors = " | ".join(provider_errors[-3:])
            return best
        self.last_provider_errors = " | ".join(provider_errors[-3:])
        if provider_errors:
            self.last_error = self.last_provider_errors
        return CategoryLookupResult("其他", 0.0, "multi")

    def _is_generic_content_domain(self, domain: str) -> bool:
        return is_generic_content_domain(domain)

    def _is_broad_platform_bucket(self, domain: str, category: str) -> bool:
        return self._is_generic_content_domain(domain) and category in BROAD_PLATFORM_CATEGORIES

    def _lookup_site_metadata(self, query: str, domain: str) -> CategoryLookupResult:
        """Fetch a site's own title/meta first; this is faster and stabler than a search page for unknown domains."""
        domain = domain.strip().strip("/")
        if not domain or len(domain) > 180:
            return CategoryLookupResult("其他", 0.0, "site-meta")
        if not re.match(r"^[a-z0-9.-]+(?::\d+)?$", domain, re.I):
            return CategoryLookupResult("其他", 0.0, "site-meta")
        pieces = []
        for scheme in ("https", "http"):
            try:
                text = self._fetch_text(f"{scheme}://{domain}/")
            except Exception:
                continue
            pieces = self._site_metadata_pieces(text)
            if pieces:
                break
        summary = html_lib.unescape(re.sub(r"<[^>]+>", " ", " ".join(pieces)))
        summary = re.sub(r"\s+", " ", summary).strip()
        if not summary:
            return CategoryLookupResult("其他", 0.0, "site-meta")
        category, confidence = self._classify_text(" ".join((query, domain, summary)))
        if category == "其他":
            category, confidence = self._classify_text(" ".join((domain, summary)))
        return CategoryLookupResult(category, confidence, "site-meta", summary[:260])

    def _site_metadata_pieces(self, text: str) -> list[str]:
        pieces = []
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        if title_match:
            pieces.append(title_match.group(1))
        for meta_match in re.finditer(r"<meta\b[^>]*>", text, re.I | re.S):
            tag = meta_match.group(0)
            name_match = re.search(r'(?:name|property)=["\']([^"\']+)["\']', tag, re.I)
            content_match = re.search(r'content=["\']([^"\']+)["\']', tag, re.I | re.S)
            if not name_match or not content_match:
                continue
            name = name_match.group(1).casefold()
            if name in {"description", "keywords", "og:title", "og:description", "twitter:title", "twitter:description"}:
                pieces.append(content_match.group(1))
            if len(pieces) >= 8:
                break
        return pieces

    def _lookup_baidu(self, query: str, domain: str) -> CategoryLookupResult:
        params = urllib.parse.urlencode({"wd": query})
        text = self._fetch_text(f"https://www.baidu.com/s?{params}")
        pieces = []
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        if title_match:
            pieces.append(title_match.group(1))
        for match in re.finditer(r'<div[^>]+class="[^"]*(?:c-abstract|result|content-right)[^"]*"[^>]*>(.*?)</div>', text, re.I | re.S):
            pieces.append(match.group(1))
            if len(pieces) >= 6:
                break
        summary = html_lib.unescape(re.sub(r"<[^>]+>", " ", " ".join(pieces)))
        summary = re.sub(r"\s+", " ", summary).strip()
        category, confidence = self._classify_text(" ".join((query, summary)))
        if category == "其他" and domain:
            category, confidence = self._classify_text(domain)
        return CategoryLookupResult(category, confidence, "baidu", summary[:260])

    def _lookup_duckduckgo(self, query: str, domain: str) -> CategoryLookupResult:
        params = urllib.parse.urlencode(
            {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        )
        data = self._fetch_json(f"https://api.duckduckgo.com/?{params}")
        text_parts = [
            str(data.get("Heading", "")),
            str(data.get("AbstractText", "")),
            str(data.get("Definition", "")),
        ]
        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict):
                text_parts.append(str(topic.get("Text", "")))
        summary = " ".join(part for part in text_parts if part).strip()
        category, confidence = self._classify_text(" ".join((query, summary)))
        if category == "其他" and domain:
            category, confidence = self._classify_text(domain)
        return CategoryLookupResult(category, confidence, "duckduckgo", summary[:260])

    def _lookup_duckduckgo_html(self, query: str, domain: str) -> CategoryLookupResult:
        params = urllib.parse.urlencode({"q": query})
        text = self._fetch_text(f"https://duckduckgo.com/html/?{params}")
        pieces = []
        for pattern in (
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>',
            r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
            r'<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
        ):
            for match in re.finditer(pattern, text, re.I | re.S):
                piece = html_lib.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))
                piece = re.sub(r"\s+", " ", piece).strip()
                if piece:
                    pieces.append(piece)
                if len(pieces) >= 8:
                    break
            if len(pieces) >= 8:
                break
        summary = " ".join(pieces).strip()
        category, confidence = self._classify_text(" ".join((query, summary)))
        if category == "其他" and domain:
            category, confidence = self._classify_text(domain)
        return CategoryLookupResult(category, confidence, "duckduckgo-html", summary[:260])

    def _lookup_wikipedia(self, query: str, domain: str, lang: str = "en") -> CategoryLookupResult:
        """Query Wikipedia search API as a fallback classification source."""
        base = f"https://{lang}.wikipedia.org/w/api.php"
        params = urllib.parse.urlencode({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "origin": "*",
            "srlimit": "5",
        })
        try:
            data = self._fetch_json(f"{base}?{params}")
            snippets = []
            for item in data.get("query", {}).get("search", [])[:5]:
                title_wiki = str(item.get("title", ""))
                snippet = str(item.get("snippet", ""))
                # Strip HTML tags from snippet
                snippet = re.sub(r"<[^>]+>", "", snippet)
                snippets.append(f"{title_wiki}: {snippet}")
            summary = " ".join(snippets).strip()
            if not summary:
                return CategoryLookupResult("其他", 0.0, f"wiki-{lang}")
            category, confidence = self._classify_text(" ".join((query, summary)))
            if category == "其他" and domain:
                category, confidence = self._classify_text(domain)
            return CategoryLookupResult(category, confidence, f"wiki-{lang}", summary[:260])
        except Exception:
            return CategoryLookupResult("其他", 0.0, f"wiki-{lang}")

    def _query(self, exe_name: str, domain: str, title: str) -> str:
        domain = (domain or "").strip()
        title = clean_lookup_title(domain, title)
        exe_name = (exe_name or "").strip()
        if domain and self._is_generic_content_domain(domain):
            return title[:120] if title else domain
        if domain:
            return f"{domain} {title[:80]}".strip()
        if exe_name and title:
            return f"{exe_name} {title[:80]}".strip()
        # For exe-only or title-only queries, add context to help disambiguate
        if exe_name:
            return f"{exe_name} software application what is".strip()
        return normalize_lookup_text(title[:100], "software") if title else ""

    def _classify_text(self, text: str) -> tuple[str, float]:
        text_l = (text or "").casefold()
        if not text_l:
            return "其他", 0.0
        if "codex" in text_l or "openai codex" in text_l:
            return "AI 工具", 0.92
        scores: dict[str, int] = {}
        for category, hints in self.CATEGORY_HINTS.items():
            score = 0
            for hint in hints:
                hint_l = hint.casefold()
                if self._hint_matches(text_l, hint_l):
                    score += 2 + min(4, len(hint_l) // 5)
            if score:
                scores[category] = score
        if not scores:
            return "其他", 0.0
        category, score = max(scores.items(), key=lambda item: item[1])
        second = max([value for key, value in scores.items() if key != category] or [0])
        confidence = min(0.92, 0.48 + score * 0.06 + max(0, score - second) * 0.03)
        return category, confidence

    @staticmethod
    def _hint_matches(text_l: str, hint_l: str) -> bool:
        if not hint_l:
            return False
        # Short latin hints like "ai", "exam", "wpm" should not match inside
        # unrelated words/domains such as "train", "example.com", or "dazidazi".
        if re.fullmatch(r"[a-z0-9]+", hint_l) and len(hint_l) <= 4:
            return re.search(rf"(?<![a-z0-9]){re.escape(hint_l)}(?![a-z0-9])", text_l) is not None
        return hint_l in text_l

    def _fetch_json(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=2.5) as response:
            raw = response.read(256 * 1024)
        data = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object, got {type(data).__name__}")
        return data

    def _fetch_text(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": DESKTOP_USER_AGENT,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            },
        )
        with urllib.request.urlopen(request, timeout=2.5) as response:
            raw = response.read(256 * 1024)
            charset = response.headers.get_content_charset() or ""
        for encoding in (charset, "utf-8", "gb18030"):
            if not encoding:
                continue
            try:
                return raw.decode(encoding, errors="replace")
            except LookupError:
                continue
        return raw.decode("utf-8", errors="replace")

    def _key(self, exe_name: str, domain: str, title: str) -> str:
        clean_title = clean_lookup_title(domain, title)
        base = f"{exe_name.casefold().strip()}|{domain.casefold().strip()}|{clean_title.casefold().strip()}"
        return base[:300]

    def _evict_locked(self) -> None:
        """Evict oldest entries when cache exceeds MAX_CACHE_SIZE. Must hold _lock."""
        excess = len(self._cache) - self.MAX_CACHE_SIZE
        if excess <= 0:
            return
        sorted_items = sorted(self._cache.items(), key=lambda item: item[1][0])
        for i in range(min(excess, len(sorted_items))):
            self._cache.pop(sorted_items[i][0], None)
