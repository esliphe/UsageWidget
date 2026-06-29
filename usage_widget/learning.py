from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
import urllib.request
import html as html_lib
from dataclasses import dataclass

from .classification import clean_lookup_title


USER_AGENT = "UsageWidget"
DESKTOP_USER_AGENT = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) {USER_AGENT}"

LEARNING_INTENT_HINTS = {
    "course",
    "lecture",
    "lesson",
    "learn",
    "learning",
    "tutorial",
    "mooc",
    "education",
    "homework",
    "textbook",
    "paper",
    "research",
    "documentation",
    "academic",
    "university",
    "college",
    "curriculum",
    "syllabus",
    "quiz",
    "assignment",
    "课程",
    "公开课",
    "网课",
    "课堂",
    "学习",
    "教学",
    "教程",
    "讲解",
    "入门",
    "基础",
    "进阶",
    "复习",
    "考研",
    "考试",
    "期末",
    "期中",
    "不挂科",
    "挂科",
    "突击",
    "速成",
    "冲刺",
    "必备",
    "刷题",
    "备考",
    "考点",
    "笔记",
    "论文",
    "习题",
    "例题",
    "真题",
    "讲义",
    "知识点",
    "重点",
    "难点",
    "预习",
    "蜂考",
    "猴博士",
    "高斯课堂",
    "宋浩",
    "大学物理",
    "光学",
    "高等数学",
    "高数",
    "线性代数",
    "概率论",
    "微积分",
    "大物",
    "C语言",
    "Python",
    "Java",
    "数据结构",
    "计算机网络",
    "操作系统",
    "机器学习",
    "深度学习",
    "英语四级",
    "英语六级",
    "考研",
    "电路",
    "模拟电子",
    "数字电路",
    "信号与系统",
    "单片机",
    "嵌入式",
    "法律",
    "法学",
    "刑法",
    "民法",
    "法考",
    "司法考试",
    "罗翔",
}


LEARNING_DOMAINS = {
    "coursera.org",
    "edx.org",
    "khanacademy.org",
    "icourse163.org",
    "zhihuishu.com",
    "xuetangx.com",
    "duolingo.com",
    "wikipedia.org",
    "zhihu.com",
    "csdn.net",
    "cnblogs.com",
    "juejin.cn",
    "learn.microsoft.com",
    "docs.python.org",
    "developer.mozilla.org",
    "arxiv.org",
    "scholar.google.com",
    "ocw.mit.edu",
    "open.ac.uk",
    "futurelearn.com",
    "udemy.com",
    "udacity.com",
    "skillshare.com",
    "pluralsight.com",
    "linkedin.com",
    "academic.oup.com",
    "nature.com",
    "sciencedirect.com",
    "researchgate.net",
    "smartedu.cn",
    "chaoxing.com",
    "mooc1.chaoxing.com",
    "xuexi.cn",
    "gaodun.com",
    "koolearn.com",
    "offcn.com",
    "fenbi.com",
    "hujiang.com",
}

VIDEO_LEARNING_DOMAINS = {
    "bilibili.com",
    "youtube.com",
    "youtu.be",
}


TOPIC_HINTS: dict[str, tuple[str, ...]] = {
    "嵌入式开发": ("嵌入式", "embedded", "stm32", "keil", "cubemx", "cubeide", "arm cortex",
                 "esp32", "arduino", "mplab", "iar", "segger", "openocd",
                 "rtos", "freertos", "ucos", "rt-thread", "hal库", "寄存器",
                 "单片机", "mcu", "固件", "gpio", "uart", "spi", "i2c",
                 "bootloader", "中断", "定时器", "pwm", "dma"),
    "C 语言": ("c语言", "c 语言", "c programming", "language c", "c语言程序设计", "谭浩强c", "c primer"),
    "C++": ("c++", "cpp", "c plus plus", "c++ primer"),
    "Python": ("python", "pyhton", "pandas", "numpy", "django", "flask", "爬虫", "matplotlib", "scipy"),
    "Java": ("java", "spring", "springboot", "jvm", "mybatis", "hibernate"),
    "JavaScript": ("javascript", "js基础", "node.js", "nodejs", "vue", "react", "typescript", "前端",
                    "next.js", "nuxt", "angular", "svelte"),
    "Vibe Coding": ("vibe coding", "vibecoding", "ai编程", "ai 编程",
                     "代码生成", "cline", "lovable.dev", "bolt.new", "v0.dev"),
    "FPGA/HDL": ("fpga", "vivado", "quartus", "modelsim", "verilog", "vhdl", "xilinx",
                 "altera", "hls", "zynq", "ise", "vitis", "petalinux", "数字电路",
                 "时序", "综合", "布局布线", "逻辑设计", "硬件描述", "hdl"),
    "EDA/PCB": ("altium", "kicad", "pcb", "schematic", "原理图", "布线", "layout",
                "eagle", "easyeda", "lceda", "orcad", "pads", "cadence",
                "电路设计", "封装", "焊盘", "走线", "敷铜", "gerber"),
    "MATLAB/仿真": ("matlab", "simulink", "labview", "octave", "ansys", "comsol",
                    "mathematica", "mathcad", "maple", "仿真", "simulation",
                    "数值计算", "有限元", "信号处理", "simulink模型"),
    "CAD/建模": ("autocad", "solidworks", "catia", "fusion360", "sketchup", "freecad",
                 "inventor", "revit", "rhino", "creo", "nx cad", "blender 建模",
                 "工程图", "参数化", "装配体", "bim", "三维建模", "cad"),
    "数据结构": ("数据结构", "data structure", "链表", "二叉树", "红黑树", "堆栈", "栈和队列", "b树", "b+树",
                 "avl树", "哈希表", "并查集", "字典树", "trie"),
    "算法": ("算法", "algorithm", "leetcode", "力扣", "动态规划", "dp算法", "贪心", "回溯", "分治",
             "bfs", "dfs", "dijkstra", "最短路径", "排序算法", "二分查找", "滑动窗口", "双指针"),
    "计算机网络": ("计算机网络", "computer network", "tcp/ip", "http协议", "网络协议", "osi", "dns",
                  "cdn", "websocket", "网络安全", "加密"),
    "操作系统": ("操作系统", "operating system", "os原理", "进程线程", "内存管理", "文件系统",
                "linux内核", "并发", "锁", "死锁", "调度"),
    "数据库": ("数据库", "database", "mysql", "postgresql", "sqlite", "sql教程", "redis",
               "mongodb", "索引", "事务", "acid", "nosql"),
    "机器学习": ("机器学习", "machine learning", "ml", "监督学习", "无监督学习", "深度学习",
                "神经网络", "cnn", "rnn", "lstm", "transformer", "bert", "gpt", "xgboost",
                "random forest", "svm", "kmeans", "pca"),
    "人工智能": ("人工智能", "大模型", "llm", "chatgpt", "transformer", "prompt engineering",
                "rag", "fine tuning", "agent", "扩散模型", "stable diffusion", "midjourney", "sora"),
    "物理": ("物理", "physics", "高中物理", "大学物理", "力学", "电磁学", "热学", "光学", "量子",
             "干涉", "衍射", "偏振", "双缝", "杨氏", "波动", "相对论", "核物理", "粒子物理",
             "蜂考", "期末物理", "不挂科物理", "大物",
             "天体物理", "凝聚态", "半导体", "超导", "等离子体", "光谱", "能级", "薛定谔",
             "麦克斯韦", "牛顿", "爱因斯坦", "费曼", "弦理论", "弦论", "熵", "光速", "引力", "黑洞",
             "狭义相对论", "广义相对论", "electromagnetic", "wave", "optics", "thermodynamics",
             "quantum", "relativity", "nuclear", "particle", "astrophysics"),
    "化学": ("化学", "chemistry", "有机化学", "无机化学", "物理化学", "高中化学", "分析化学",
             "生物化学", "元素", "分子", "反应", "催化", "电化学", "配位化学", "光谱分析",
             "色谱", "滴定", "氧化还原", "酸碱", "官能团"),
    "生物": ("生物", "biology", "细胞", "遗传", "分子生物", "高中生物", "基因", "dna", "rna",
             "蛋白质", "进化", "生态", "微生物", "免疫", "神经科学", "干细胞", "crispr",
             "基因编辑", "转录", "翻译", "有丝分裂", "减数分裂"),
    "高等数学": ("高等数学", "高数", "微积分", "calculus", "极限", "导数", "积分", "多元函数",
                "级数", "傅里叶", "拉普拉斯", "常微分方程", "偏微分方程", "泰勒展开", "微分"),
    "线性代数": ("线性代数", "linear algebra", "矩阵", "行列式", "特征值", "向量空间",
                "线性变换", "正交", "对角化", "svd", "奇异值"),
    "概率统计": ("概率论", "概率统计", "statistics", "probability", "数理统计", "随机变量",
                "贝叶斯", "假设检验", "回归分析", "方差", "期望", "大数定律", "中心极限"),
    "离散数学": ("离散数学", "discrete math", "图论", "集合论", "命题逻辑", "组合数学",
                "数论", "布尔代数", "自动机", "形式语言"),
    "数学": ("数学", "math", "mathematics", "函数", "方程", "几何", "代数", "三角",
             "解析几何", "复数", "数列", "不等式", "数学分析", "拓扑"),
    "英语": ("英语", "english", "单词", "语法", "听力", "阅读理解", "雅思", "托福", "cet4",
             "cet6", "四六级", "gre", "gmat", "口语", "写作", "翻译", "词汇"),
    "日语": ("日语", "japanese", "jlpt", "n1", "n2", "n3", "五十音", "nhk", "日语学习"),
    "历史": ("历史", "history", "中国史", "世界史", "近代史", "古代史", "中世纪", "二战",
             "冷战", "文明", "考古"),
    "政治": ("政治", "politics", "马原", "毛概", "思修", "近代史纲要", "法考", "公务员"),
    "经济学": ("经济学", "economics", "宏观经济", "微观经济", "金融学", "投资", "股票",
              "基金", "区块链", "比特币", "货币政策", "gdp", "通胀", "利率"),
    "医学": ("医学", "medicine", "解剖", "生理学", "病理学", "药理学", "临床", "诊断",
             "内科", "外科", "影像", "护理", "中医", "针灸"),
    "法律/法学": ("法律", "法学", "刑法", "民法", "行政法", "商法", "经济法", "诉讼法",
                 "法考", "司法考试", "罗翔", "jurisprudence", "legal", "law course"),
    "设计": ("设计", "design", "ui设计", "平面设计", "figma", "photoshop", "摄影",
             "illustrator", "premiere", "剪辑", "调色", "3d建模",
             "blender", "c4d", "cad"),
    "论文/科研": ("论文", "科研", "research paper", "paper reading", "arxiv", "文献", "学术",
                 "sci", "nature", "science", "研究方法", "文献综述", "meta分析"),
    "综合学习": ("学习", "课程", "教程", "公开课", "讲解", "知识", "科普", "入门", "基础",
                "lecture", "course", "tutorial", "education", "educational"),
}


PROGRAMMING_TOPICS = {
    "嵌入式开发",
    "C 语言",
    "C++",
    "Python",
    "Java",
    "JavaScript",
    "Vibe Coding",
    "数据结构",
    "算法",
    "计算机网络",
    "操作系统",
    "数据库",
    "机器学习",
    "人工智能",
    "FPGA/HDL",
    "EDA/PCB",
    "MATLAB/仿真",
    "CAD/建模",
}


@dataclass(frozen=True)
class LearningTopicResult:
    topic: str
    confidence: float
    source: str
    summary: str = ""


def normalize_text(*parts: str) -> str:
    text = " ".join(part for part in parts if part)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def domain_matches(domain: str, candidates: set[str]) -> bool:
    domain_l = (domain or "").casefold()
    return any(domain_l == item or domain_l.endswith("." + item) for item in candidates)


def has_learning_intent(domain: str, text: str, kind: str = "") -> bool:
    text_l = clean_lookup_title(domain, text).casefold()
    if any(hint.casefold() in text_l for hint in LEARNING_INTENT_HINTS):
        return True
    if domain_matches(domain, LEARNING_DOMAINS):
        return True
    if kind in {"web_page", "video_playback"}:
        edu_patterns = ("知识", "科普", "原理", "基础", "入门", "教程", "讲解", "详解",
                        "lecture", "tutorial", "course", "lesson", "explain", "introduction",
                        "习题", "例题", "考点", "考试", "真题", "复习", "考研",
                        "期末", "期中", "不挂科", "突击", "速成", "冲刺", "备考",
                        "必备", "大学物理", "高数", "线代", "概率论", "蜂考",
                        "法律", "法学", "刑法", "民法", "法考", "司法考试")
        if any(hint in text_l for hint in edu_patterns):
            return True
    if kind == "video_playback" and domain_matches(domain, VIDEO_LEARNING_DOMAINS):
        # Only flag video as learning if title text also suggests educational content
        edu_patterns = ("课程", "教程", "讲解", "学习", "课", "公开课", "讲义", "复习",
                        "lecture", "tutorial", "course", "lesson", "education", "learn",
                        "期末", "不挂科", "突击", "速成", "考点", "备考", "蜂考",
                        "法律", "法学", "刑法", "民法", "法考", "司法考试")
        if any(hint in text_l for hint in edu_patterns):
            return True
    return False


def local_learning_topic(text: str) -> LearningTopicResult:
    text_l = clean_lookup_title("", text).casefold()
    if not text_l:
        return LearningTopicResult("", 0.0, "empty")
    scores: dict[str, int] = {}
    for topic, hints in TOPIC_HINTS.items():
        score = 0
        for hint in hints:
            hint_l = hint.casefold()
            if hint_l and hint_l in text_l:
                score += 2 + min(5, len(hint_l) // 4)
        if score:
            scores[topic] = score
    if not scores:
        return LearningTopicResult("", 0.0, "local")
    # Penalize catch-all "综合学习" when specific topics also match
    if "综合学习" in scores and len(scores) > 1:
        scores["综合学习"] = max(0, scores["综合学习"] - 3)
    topic, score = max(scores.items(), key=lambda item: item[1])
    second = max([value for key, value in scores.items() if key != topic] or [0])
    confidence = min(0.96, 0.52 + score * 0.06 + max(0, score - second) * 0.03)
    return LearningTopicResult(topic, confidence, "local")


def should_mark_learning(category: str, topic: str, domain: str, text: str, kind: str = "") -> bool:
    if not topic:
        return False
    if category == "学习":
        return True
    if has_learning_intent(domain, text, kind):
        return True
    if kind == "video_playback" and topic not in {"音乐", "游戏"}:
        return True
    if category == "编程" and topic in PROGRAMMING_TOPICS and has_learning_intent(domain, text, kind):
        return True
    return False


class OnlineLearningTopicClassifier:
    MAX_CACHE_SIZE = 1200

    def __init__(self, min_interval: float = 12.0, ttl_seconds: float = 7 * 86400.0) -> None:
        self.min_interval = min_interval
        self.ttl_seconds = ttl_seconds
        self.error_ttl_seconds = 900.0
        self.max_workers = 6
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, LearningTopicResult]] = {}
        self._pending: set[str] = set()
        self._last_request_at = 0.0
        self._active_workers = 0
        self.last_error = ""
        self.last_source = ""
        self.last_query = ""

    def cached(self, domain: str, title: str, description: str = "") -> LearningTopicResult | None:
        key = self._key(domain, title, description)
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

    def queue(self, domain: str, title: str, description: str = "") -> None:
        key = self._key(domain, title, description)
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
            thread = threading.Thread(
                target=self._worker,
                args=(key, domain, title, description),
                name="UsageWidgetLearningTopicLookup",
                daemon=True,
            )
            thread.start()
        except Exception as exc:
            with self._lock:
                self._pending.discard(key)
                self._active_workers -= 1
                self.last_error = f"Thread start failed: {exc}"

    def _worker(self, key: str, domain: str, title: str, description: str) -> None:
        try:
            with self._lock:
                now = time.monotonic()
                wait = max(0.0, self.min_interval - (now - self._last_request_at))
                self._last_request_at = now + wait
            if wait:
                time.sleep(wait)
            result = self._lookup(domain, title, description)
            with self._lock:
                self._cache[key] = (time.monotonic(), result)
                self._evict_locked()
                self.last_error = ""
                self.last_source = result.source
        except Exception as exc:
            with self._lock:
                self._cache[key] = (time.monotonic(), LearningTopicResult("", 0.0, "error"))
                self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                self._pending.discard(key)
                self._active_workers -= 1

    def _lookup(self, domain: str, title: str, description: str) -> LearningTopicResult:
        clean_title = clean_lookup_title(domain, title)
        query_text = normalize_text(clean_title[:120], description[:100])
        domain_clean = domain.replace("www.", "").lower()
        if "bilibili.com" in domain_clean or domain_clean.endswith("b23.tv"):
            query_text = normalize_text(clean_title[:160])
        local = local_learning_topic(query_text)
        if local.topic and local.confidence >= 0.62 and has_learning_intent(domain, query_text):
            return LearningTopicResult(local.topic, max(local.confidence, 0.72), "local-query", query_text[:300])
        if has_learning_intent(domain, query_text):
            query = f"{domain_clean} {query_text} 课程 教程 学习 期末"
        else:
            query = f"{domain_clean} {query_text}"
        self.last_query = query
        if not query_text:
            return LearningTopicResult("", 0.0, "empty")

        providers = []
        if re.search(r"[\u4e00-\u9fff]", query):
            providers.append(lambda: self._lookup_baidu(query, query_text, domain_clean, title))
        providers.extend(
            [
                lambda: self._lookup_duckduckgo(query, query_text, domain_clean, title),
                lambda: self._lookup_wikipedia(query, query_text, domain_clean, title, "zh"),
                lambda: self._lookup_wikipedia(query, query_text, domain_clean, title, "en"),
            ]
        )
        if not re.search(r"[\u4e00-\u9fff]", query):
            providers.append(lambda: self._lookup_baidu(query, query_text, domain_clean, title))

        for provider in providers:
            try:
                result = provider()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                continue
            if result.topic:
                return result

        return LearningTopicResult("", 0.0, "multi")

    def _lookup_baidu(self, query: str, query_text: str, domain_clean: str, title: str) -> LearningTopicResult:
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
        combined = normalize_text(query_text, summary)
        local = local_learning_topic(combined)
        if local.topic:
            conf = max(local.confidence, 0.66)
            if has_learning_intent(domain_clean, combined):
                conf = min(0.94, conf + 0.08)
            return LearningTopicResult(local.topic, conf, "baidu", summary[:300])
        if "bilibili" in domain_clean or domain_clean.endswith("b23.tv") or "youtube" in domain_clean:
            alt = local_learning_topic(normalize_text(clean_lookup_title(domain_clean, title)[:200], summary[:200]))
            if alt.topic:
                return LearningTopicResult(alt.topic, max(alt.confidence, 0.60), "baidu", summary[:300])
        return LearningTopicResult("", 0.0, "baidu", summary[:300])

    def _lookup_duckduckgo(self, query: str, query_text: str, domain_clean: str, title: str) -> LearningTopicResult:
        params = urllib.parse.urlencode(
            {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        )
        data = self._fetch_json(f"https://api.duckduckgo.com/?{params}")
        text_parts = [
            str(data.get("Heading", "")),
            str(data.get("AbstractText", "")),
            str(data.get("Definition", "")),
        ]
        for topic in data.get("RelatedTopics", [])[:6]:
            if isinstance(topic, dict):
                text_parts.append(str(topic.get("Text", "")))
        summary = normalize_text(*text_parts)
        combined = normalize_text(query_text, summary)
        local = local_learning_topic(combined)
        if local.topic:
            conf = max(local.confidence, 0.66)
            if len(query_text) >= 20 and local.confidence >= 0.60:
                conf = min(0.92, conf + 0.08)
            return LearningTopicResult(local.topic, conf, "duckduckgo", summary[:300])
        if "bilibili" in domain_clean or domain_clean.endswith("b23.tv") or "youtube" in domain_clean:
            alt = local_learning_topic(normalize_text(clean_lookup_title(domain_clean, title)[:200], summary[:200]))
            if alt.topic:
                return LearningTopicResult(alt.topic, max(alt.confidence, 0.60), "duckduckgo", summary[:300])
        return LearningTopicResult("", 0.0, "duckduckgo", summary[:300])

    def _lookup_wikipedia(self, query: str, query_text: str, domain_clean: str, title: str, lang: str) -> LearningTopicResult:
        """Query Wikipedia search API as a fallback for learning topic classification."""
        base = f"https://{lang}.wikipedia.org/w/api.php"
        params = urllib.parse.urlencode({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "origin": "*",
            "srlimit": "6",
        })
        try:
            data = self._fetch_json(f"{base}?{params}")
            snippets = []
            for item in data.get("query", {}).get("search", [])[:6]:
                title_wiki = str(item.get("title", ""))
                snippet = str(item.get("snippet", ""))
                snippet = re.sub(r"<[^>]+>", "", snippet)
                snippets.append(f"{title_wiki}: {snippet}")
            summary = normalize_text(*snippets)
            if not summary:
                return LearningTopicResult("", 0.0, f"wiki-{lang}")
            combined = normalize_text(query_text, summary)
            local = local_learning_topic(combined)
            if local.topic:
                conf = max(local.confidence, 0.60)
                return LearningTopicResult(local.topic, conf, f"wiki-{lang}", summary[:300])
            if "bilibili" in domain_clean or domain_clean.endswith("b23.tv") or "youtube" in domain_clean:
                alt = local_learning_topic(normalize_text(clean_lookup_title(domain_clean, title)[:200], summary[:200]))
                if alt.topic:
                    return LearningTopicResult(alt.topic, max(alt.confidence, 0.55), f"wiki-{lang}", summary[:300])
            return LearningTopicResult("", 0.0, f"wiki-{lang}", summary[:300])
        except Exception:
            return LearningTopicResult("", 0.0, f"wiki-{lang}")

    def _fetch_json(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=3.0) as response:
            raw = response.read(256 * 1024)
        return json.loads(raw.decode("utf-8", errors="replace"))

    def _fetch_text(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": DESKTOP_USER_AGENT,
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            },
        )
        with urllib.request.urlopen(request, timeout=4.0) as response:
            raw = response.read(256 * 1024)
        return raw.decode("utf-8", errors="replace")

    def _key(self, domain: str, title: str, description: str) -> str:
        return normalize_text(domain.casefold(), title.casefold(), description.casefold())[:320]

    def _evict_locked(self) -> None:
        """Evict oldest entries when cache exceeds MAX_CACHE_SIZE. Must hold _lock."""
        excess = len(self._cache) - self.MAX_CACHE_SIZE
        if excess <= 0:
            return
        sorted_items = sorted(self._cache.items(), key=lambda item: item[1][0])
        for i in range(min(excess, len(sorted_items))):
            self._cache.pop(sorted_items[i][0], None)
