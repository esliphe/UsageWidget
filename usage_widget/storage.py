from __future__ import annotations

import csv
import html
import os
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from .diagnostics import log_event
from .media import parse_music_identity


DEFAULT_IGNORED = {
    "system",
    "idle",
    "registry",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "fontdrvhost.exe",
    "dwm.exe",
    "conhost.exe",
    "sihost.exe",
    "ctfmon.exe",
    "runtimebroker.exe",
    "searchindexer.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "textinputhost.exe",
    "widgets.exe",
    "widgetservice.exe",
    "securityhealthservice.exe",
    "wudfhost.exe",
    "audiodg.exe",
}


BROWSER_MEDIA_HINTS = (
    "chrome",
    "msedge",
    "edge",
    "firefox",
    "brave",
    "opera",
    "vivaldi",
    "arc",
    "browser",
)


DEFAULT_CATEGORY_RULES = [
    ("code.exe", "编程", "app"),
    ("pycharm", "编程", "app"),
    ("cursor", "编程", "app"),
    ("github.com", "编程", "domain"),
    ("stackoverflow.com", "编程", "domain"),
    ("leetcode", "编程", "domain"),
    ("learn.microsoft.com", "学习", "domain"),
    ("docs.python.org", "学习", "domain"),
    ("wikipedia.org", "学习", "domain"),
    ("zhihuishu.com", "学习", "domain"),
    ("icourse163.org", "学习", "domain"),
    ("xuetangx.com", "学习", "domain"),
    ("coursera.org", "学习", "domain"),
    ("edx.org", "学习", "domain"),
    ("khanacademy.org", "学习", "domain"),
    ("duolingo.com", "学习", "domain"),
    ("学堂", "学习", "title"),
    ("课程", "学习", "title"),
    ("公开课", "学习", "title"),
    ("网课", "学习", "title"),
    ("教程", "学习", "title"),
    ("讲义", "学习", "title"),
    ("论文", "学习", "title"),
    ("考试", "学习", "title"),
    ("期末", "学习", "title"),
    ("不挂科", "学习", "title"),
    ("突击", "学习", "title"),
    ("速成", "学习", "title"),
    ("备考", "学习", "title"),
    ("考点", "学习", "title"),
    ("蜂考", "学习", "title"),
    ("大学物理", "学习", "title"),
    ("光学", "学习", "title"),
    ("高等数学", "学习", "title"),
    ("线性代数", "学习", "title"),
    ("英语", "学习", "title"),
    ("python 教程", "学习", "title"),
    ("chatgpt.com", "AI 工具", "domain"),
    ("claude.ai", "AI 工具", "domain"),
    ("bilibili.com", "视频", "domain"),
    ("youtube.com", "视频", "domain"),
    ("youku.com", "视频", "domain"),
    ("iqiyi.com", "视频", "domain"),
    ("v.qq.com", "视频", "domain"),
    ("mgtv.com", "视频", "domain"),
    ("douyin.com", "娱乐", "domain"),
    ("weixin.exe", "聊天", "app"),
    ("qq.exe", "聊天", "app"),
    ("weibo.com", "娱乐", "domain"),
    ("x.com", "社交", "domain"),
    ("twitter.com", "社交", "domain"),
    ("kugou", "音乐", "app"),
    ("cloudmusic", "音乐", "app"),
    ("spotify", "音乐", "app"),
    ("music.163.com", "音乐", "domain"),
    ("open.spotify.com", "音乐", "domain"),
    ("music.youtube.com", "音乐", "domain"),
    ("y.qq.com", "音乐", "domain"),
    ("kugou.com", "音乐", "domain"),
    ("kuwo.cn", "音乐", "domain"),
    ("music.apple.com", "音乐", "domain"),
    ("soundcloud.com", "音乐", "domain"),
    ("播客", "音乐", "title"),
    ("podcast", "音乐", "title"),
    ("歌单", "音乐", "title"),
    ("专辑", "音乐", "title"),
    ("音乐", "音乐", "title"),
    ("歌曲", "音乐", "title"),
    ("演唱会", "音乐", "title"),
    ("翻唱", "音乐", "title"),
    ("cover", "音乐", "title"),
    ("steam.exe", "游戏", "app"),
    ("epicgameslauncher.exe", "游戏", "app"),
    ("riotclientservices.exe", "游戏", "app"),
    ("leagueclient.exe", "游戏", "app"),
    ("genshinimpact", "游戏", "app"),
    ("yuanshen.exe", "游戏", "app"),
    ("starrail.exe", "游戏", "app"),
    ("minecraft", "游戏", "app"),
    ("roblox", "游戏", "app"),
    ("store.steampowered.com", "游戏", "domain"),
    ("steamcommunity.com", "游戏", "domain"),
    ("epicgames.com", "游戏", "domain"),
    ("riotgames.com", "游戏", "domain"),
    ("taptap.cn", "游戏", "domain"),
    ("4399.com", "游戏", "domain"),
    ("3dmgame.com", "游戏", "domain"),
    ("gamersky.com", "游戏", "domain"),
    ("nga.cn", "游戏", "domain"),
    ("游戏", "游戏", "title"),
    ("game", "游戏", "title"),
    ("steam", "游戏", "title"),
    ("原神", "游戏", "title"),
    ("崩坏", "游戏", "title"),
    ("星穹铁道", "游戏", "title"),
    ("王者荣耀", "游戏", "title"),
    ("英雄联盟", "游戏", "title"),
    ("minecraft", "游戏", "title"),
    ("roblox", "游戏", "title"),
    ("openttd", "游戏", "app"),
    ("openttd.exe", "游戏", "app"),
    ("openrct2", "游戏", "app"),
    ("simutrans", "游戏", "app"),
    ("transport fever", "游戏", "app"),
    ("cities skylines", "游戏", "app"),
    ("factori", "游戏", "app"),
    ("rimworld", "游戏", "app"),
    ("terraria", "游戏", "app"),
    ("stardew valley", "游戏", "app"),
    ("civilization", "游戏", "app"),
    ("age of empires", "游戏", "app"),
    ("total war", "游戏", "app"),
    ("euro truck", "游戏", "app"),
    ("american truck", "游戏", "app"),
    ("farming simulator", "游戏", "app"),
    ("kerbal space", "游戏", "app"),
    ("subnautica", "游戏", "app"),
    ("satisfactory", "游戏", "app"),
    ("dyson sphere", "游戏", "app"),
    ("anno", "游戏", "app"),
    ("tropico", "游戏", "app"),
    ("prison architect", "游戏", "app"),
    ("planet coaster", "游戏", "app"),
    ("planet zoo", "游戏", "app"),
    ("two point", "游戏", "app"),
    ("oxygen not included", "游戏", "app"),
    ("don't starve", "游戏", "app"),
    ("slay the spire", "游戏", "app"),
    ("hollow knight", "游戏", "app"),
    ("dead cells", "游戏", "app"),
    ("hades", "游戏", "app"),
    ("baldur", "游戏", "app"),
    ("divinity", "游戏", "app"),
    ("elder scrolls", "游戏", "app"),
    ("fallout", "游戏", "app"),
    ("witcher", "游戏", "app"),
    ("cyberpunk", "游戏", "app"),
    ("gta", "游戏", "app"),
    ("grand theft auto", "游戏", "app"),
    ("call of duty", "游戏", "app"),
    ("battlefield", "游戏", "app"),
    ("counter-strike", "游戏", "app"),
    ("valorant", "游戏", "app"),
    ("overwatch", "游戏", "app"),
    ("apex legends", "游戏", "app"),
    ("pubg", "游戏", "app"),
    ("fortnite", "游戏", "app"),
    ("elden ring", "游戏", "app"),
    ("dark souls", "游戏", "app"),
    ("sekiro", "游戏", "app"),
    ("monster hunter", "游戏", "app"),
    ("final fantasy", "游戏", "app"),
    ("zelda", "游戏", "app"),
    ("pokemon", "游戏", "app"),
    ("mario", "游戏", "app"),
    ("assassin", "游戏", "app"),
    ("far cry", "游戏", "app"),
    ("tomb raider", "游戏", "app"),
    ("resident evil", "游戏", "app"),
    ("devil may cry", "游戏", "app"),
    ("doom", "游戏", "app"),
    ("half-life", "游戏", "app"),
    ("portal", "游戏", "app"),
    ("left 4 dead", "游戏", "app"),
    ("borderlands", "游戏", "app"),
    ("bioshock", "游戏", "app"),
    ("mass effect", "游戏", "app"),
    ("dragon age", "游戏", "app"),
    ("path of exile", "游戏", "app"),
    ("diablo", "游戏", "app"),
    ("world of warcraft", "游戏", "app"),
    ("dota", "游戏", "app"),
]

DEFAULT_CATEGORY_RULES += [
    ("explorer.exe", "系统软件", "app"),
    ("taskmgr.exe", "系统软件", "app"),
    ("control.exe", "系统软件", "app"),
    ("systemsettings.exe", "系统软件", "app"),
    ("applicationframehost.exe", "系统软件", "app"),
    ("cmd.exe", "系统软件", "app"),
    ("powershell.exe", "系统软件", "app"),
    ("windowsterminal.exe", "系统软件", "app"),
    ("terminal", "系统软件", "app"),
    ("everything.exe", "工具", "app"),
    ("snippingtool.exe", "工具", "app"),
    ("sharex.exe", "工具", "app"),
    ("7zfm.exe", "工具", "app"),
    ("winrar.exe", "工具", "app"),
    ("bandizip.exe", "工具", "app"),
    ("idm.exe", "工具", "app"),
    ("downloader", "工具", "app"),
    ("obsidian.exe", "学习", "app"),
    ("notion.exe", "办公", "app"),
    ("onenote.exe", "学习", "app"),
    ("winword.exe", "办公", "app"),
    ("excel.exe", "办公", "app"),
    ("powerpnt.exe", "办公", "app"),
    ("wps.exe", "办公", "app"),
    ("et.exe", "办公", "app"),
    ("wpp.exe", "办公", "app"),
    ("feishu.exe", "办公", "app"),
    ("lark.exe", "办公", "app"),
    ("dingtalk.exe", "办公", "app"),
    ("teams.exe", "办公", "app"),
    ("zoom.exe", "办公", "app"),
    ("vscode", "编程", "app"),
    ("windsurf", "编程", "app"),
    ("trae", "编程", "app"),
    ("webstorm", "编程", "app"),
    ("idea", "编程", "app"),
    ("clion", "编程", "app"),
    ("rider", "编程", "app"),
    ("visualstudio", "编程", "app"),
    ("devenv.exe", "编程", "app"),
    ("sublime_text.exe", "编程", "app"),
    ("notepad++.exe", "编程", "app"),
    ("gitkraken", "编程", "app"),
    ("sourcetree", "编程", "app"),
    ("postman.exe", "编程", "app"),
    ("docker desktop.exe", "编程", "app"),
    ("cursor.com", "编程", "domain"),
    ("windsurf.com", "编程", "domain"),
    ("replit.com", "编程", "domain"),
    ("codepen.io", "编程", "domain"),
    ("codesandbox.io", "编程", "domain"),
    ("vercel.com", "编程", "domain"),
    ("netlify.com", "编程", "domain"),
    ("npmjs.com", "编程", "domain"),
    ("pypi.org", "编程", "domain"),
    ("docker.com", "编程", "domain"),
    ("vibe coding", "编程", "title"),
    ("vibecoding", "编程", "title"),
    ("copilot", "编程", "title"),
    ("代码生成", "编程", "title"),
    # --- Embedded / MCU development ---
    ("keil", "编程", "app"),
    ("uv4.exe", "编程", "app"),
    ("uv5.exe", "编程", "app"),
    ("stm32cube", "编程", "app"),
    ("stm32cubemx", "编程", "app"),
    ("stm32cubeide", "编程", "app"),
    ("iar", "编程", "app"),
    ("segger", "编程", "app"),
    ("j-link", "编程", "app"),
    ("platformio", "编程", "app"),
    ("arduino", "编程", "app"),
    ("arduino ide", "编程", "app"),
    ("mplab", "编程", "app"),
    ("mplabx", "编程", "app"),
    ("eclipse", "编程", "app"),
    ("espidf", "编程", "app"),
    ("esp-idf", "编程", "app"),
    ("openocd", "编程", "app"),
    ("gdb", "编程", "app"),
    ("arm-none-eabi", "编程", "app"),
    ("riscv", "编程", "app"),
    ("proteus", "编程", "app"),
    ("multisim", "编程", "app"),
    ("ltspice", "编程", "app"),
    ("pspice", "编程", "app"),
    # --- FPGA / HDL ---
    ("vivado", "编程", "app"),
    ("quartus", "编程", "app"),
    ("modelsim", "编程", "app"),
    ("ise", "编程", "app"),
    ("vitis", "编程", "app"),
    ("petalinux", "编程", "app"),
    # --- EDA / PCB ---
    ("altium", "编程", "app"),
    ("kicad", "编程", "app"),
    ("eagle", "编程", "app"),
    ("orcad", "编程", "app"),
    ("allegro", "编程", "app"),
    ("easyeda", "编程", "app"),
    ("lceda", "编程", "app"),
    ("pads", "编程", "app"),
    ("cadence", "编程", "app"),
    # --- MATLAB / Scientific ---
    ("matlab", "编程", "app"),
    ("simulink", "编程", "app"),
    ("octave", "编程", "app"),
    ("labview", "编程", "app"),
    ("ansys", "编程", "app"),
    ("comsol", "编程", "app"),
    ("mathcad", "编程", "app"),
    ("mathematica", "编程", "app"),
    ("maple", "编程", "app"),
    # --- CAD / 3D ---
    ("autocad", "编程", "app"),
    ("solidworks", "编程", "app"),
    ("fusion360", "编程", "app"),
    ("fusion 360", "编程", "app"),
    ("catia", "编程", "app"),
    ("sketchup", "编程", "app"),
    ("freecad", "编程", "app"),
    ("inventor", "编程", "app"),
    ("revit", "编程", "app"),
    ("rhino", "编程", "app"),
    ("creo", "编程", "app"),
    ("nx", "编程", "app"),
    # --- Game engines ---
    ("unity", "编程", "app"),
    ("unity.exe", "编程", "app"),
    ("unreal", "编程", "app"),
    ("unrealeditor", "编程", "app"),
    ("godot", "编程", "app"),
    ("gamemaker", "编程", "app"),
    ("rpg maker", "编程", "app"),
    # --- Domain hints for embedded ---
    ("st.com", "编程", "domain"),
    ("nxp.com", "编程", "domain"),
    ("ti.com", "编程", "domain"),
    ("allaboutcircuits.com", "编程", "domain"),
    ("eeworld.com.cn", "编程", "domain"),
    ("eet-china.com", "编程", "domain"),
    ("21ic.com", "编程", "domain"),
    ("oshwhub.com", "编程", "domain"),
    ("digikey.com", "编程", "domain"),
    ("mouser.com", "编程", "domain"),
    ("lcsc.com", "编程", "domain"),
    ("grabcad.com", "编程", "domain"),
    # --- Domain hints for FPGA/EDA ---
    ("xilinx.com", "编程", "domain"),
    ("amd.com", "编程", "domain"),
    ("intel.com/content/www/us/en/products/details/fpga", "编程", "domain"),
    ("digilent.com", "编程", "domain"),
    ("fpga4fun.com", "编程", "domain"),
    ("fpga4student.com", "编程", "domain"),
    ("hackaday.io", "编程", "domain"),
    ("instructables.com", "编程", "domain"),
    ("bolt.new", "AI 工具", "domain"),
    ("lovable.dev", "AI 工具", "domain"),
    ("poe.com", "AI 工具", "domain"),
    ("perplexity.ai", "AI 工具", "domain"),
    ("deepseek.com", "AI 工具", "domain"),
    ("kimi.moonshot.cn", "AI 工具", "domain"),
    ("doubao.com", "AI 工具", "domain"),
    ("yuanbao.tencent.com", "AI 工具", "domain"),
    ("通义", "AI 工具", "title"),
    ("豆包", "AI 工具", "title"),
    ("kimi", "AI 工具", "title"),
    ("deepseek", "AI 工具", "title"),
    ("codex.exe", "AI 工具", "app"),
    ("codex", "AI 工具", "title"),
    ("openai codex", "AI 工具", "title"),
    # Known AI tools with ambiguous names (need local rules)
    ("yuanbao", "AI 工具", "app"),
    ("元宝", "AI 工具", "title"),
    ("腾讯元宝", "AI 工具", "title"),
    ("doubao", "AI 工具", "app"),
    ("豆包", "AI 工具", "title"),
    ("tongyi", "AI 工具", "app"),
    ("通义千问", "AI 工具", "title"),
    ("通义", "AI 工具", "title"),
    ("wenxin", "AI 工具", "app"),
    ("文心一言", "AI 工具", "title"),
    ("文心", "AI 工具", "title"),
    ("xinghuo", "AI 工具", "app"),
    ("讯飞星火", "AI 工具", "title"),
    ("星火", "AI 工具", "title"),
    ("360gpt", "AI 工具", "app"),
    ("智脑", "AI 工具", "title"),
    ("qianwen", "AI 工具", "app"),
    ("baichuan", "AI 工具", "app"),
    ("百川", "AI 工具", "title"),
    ("chatglm", "AI 工具", "app"),
    ("智谱", "AI 工具", "title"),
    ("minimax", "AI 工具", "app"),
    ("海螺", "AI 工具", "title"),
    ("moonshot", "AI 工具", "app"),
    ("月之暗面", "AI 工具", "title"),
    ("stepfun", "AI 工具", "app"),
    ("阶跃星辰", "AI 工具", "title"),
    ("zhipu", "AI 工具", "app"),
    ("abab", "AI 工具", "app"),
    ("yi-api", "AI 工具", "app"),
    ("零一万物", "AI 工具", "title"),
    ("qq.exe", "聊天", "app"),
    ("ntqq.exe", "聊天", "app"),
    ("wechat.exe", "聊天", "app"),
    ("weixin.exe", "聊天", "app"),
    ("tim.exe", "聊天", "app"),
    ("telegram.exe", "聊天", "app"),
    ("discord.exe", "聊天", "app"),
    ("slack.exe", "聊天", "app"),
    ("wx.qq.com", "聊天", "domain"),
    ("web.telegram.org", "聊天", "domain"),
    ("discord.com", "聊天", "domain"),
    ("slack.com", "聊天", "domain"),
    ("messages.google.com", "聊天", "domain"),
    ("whatsapp.com", "聊天", "domain"),
    ("dazidazi.com", "工具", "domain"),
    ("dazidazi", "工具", "title"),
    ("打字", "工具", "title"),
    ("typing", "工具", "title"),
    ("zhihu.com", "学习", "domain"),
    ("csdn.net", "编程", "domain"),
    ("cnblogs.com", "编程", "domain"),
    ("juejin.cn", "编程", "domain"),
    ("segmentfault.com", "编程", "domain"),
    ("developer.mozilla.org", "编程", "domain"),
    ("mdn", "编程", "title"),
    ("arxiv.org", "学习", "domain"),
    ("scholar.google.com", "学习", "domain"),
    ("researchgate.net", "学习", "domain"),
    ("pubmed.ncbi.nlm.nih.gov", "学习", "domain"),
    ("z-library", "学习", "domain"),
    ("readpaper.com", "学习", "domain"),
    ("哔哩哔哩课堂", "学习", "title"),
    ("课程", "学习", "title"),
    ("讲解", "学习", "title"),
    ("学习路线", "学习", "title"),
    ("douyin.exe", "娱乐", "app"),
    ("tiktok", "娱乐", "app"),
    ("kuaishou", "娱乐", "app"),
    ("netflix", "娱乐", "domain"),
    ("hulu.com", "娱乐", "domain"),
    ("disneyplus.com", "娱乐", "domain"),
    ("douyin.com", "娱乐", "domain"),
    ("kuaishou.com", "娱乐", "domain"),
    ("xiaohongshu.com", "娱乐", "domain"),
    ("weibo.com", "娱乐", "domain"),
    ("reddit.com", "娱乐", "domain"),
    ("贴吧", "娱乐", "title"),
    ("热搜", "娱乐", "title"),
    ("搞笑", "娱乐", "title"),
    ("综艺", "娱乐", "title"),
    ("淘宝", "购物", "title"),
    ("京东", "购物", "title"),
    ("拼多多", "购物", "title"),
    ("taobao.com", "购物", "domain"),
    ("tmall.com", "购物", "domain"),
    ("jd.com", "购物", "domain"),
    ("pinduoduo.com", "购物", "domain"),
    ("amazon.com", "购物", "domain"),
    ("news.qq.com", "新闻", "domain"),
    ("news.sina.com.cn", "新闻", "domain"),
    ("thepaper.cn", "新闻", "domain"),
    ("36kr.com", "新闻", "domain"),
    ("新闻", "新闻", "title"),
    ("资讯", "新闻", "title"),
]


@dataclass(frozen=True)
class AppSettings:
    theme: str = "system"
    always_expanded: bool = True
    window_opacity: float = 0.92
    background_alpha: int = 190
    pos_x: int | None = None
    pos_y: int | None = None
    auto_start: bool = False
    track_window_titles: bool = True
    track_media_sessions: bool = True
    track_browser_urls: bool = True
    idle_threshold_seconds: int = 180
    pause_tracking: bool = False
    private_title_mode: bool = False
    online_music_lookup: bool = False
    online_category_lookup: bool = False
    media_activity_keeps_attention: bool = True
    handwriting_mode: bool = True
    handwriting_apps: str = "onenote.exe,applicationframehost.exe,whiteboard.exe,journal.exe,powerpnt.exe"
    timeline_retention_days: int = 90
    top_list_sort: str = "current_first"
    daily_summary: bool = True
    last_summary_date: str = ""


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / "AppData" / "Local"
    path = root / "UsageWidget"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Storage:
    def __init__(self, db_path: Path | None = None) -> None:
        requested_path = Path(db_path) if db_path else app_data_dir() / "usage.db"
        self.db_path = requested_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_cache: AppSettings | None = None
        self._ignored_cache: list[str] | None = None
        self._category_rules_cache: list[sqlite3.Row] | None = None
        try:
            self._connect()
            self._initialize_database()
        except sqlite3.OperationalError as exc:
            if db_path is not None or "readonly" not in str(exc).lower():
                raise
            self._recover_readonly_database(requested_path, exc)

    def _connect(self) -> None:
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.conn.execute("PRAGMA cache_size=-16000")
        self.conn.execute("PRAGMA busy_timeout=3000")

    def _initialize_database(self) -> None:
        self._init_schema()
        self._migrate_schema()
        self._ensure_defaults()

    def _recover_readonly_database(self, original_path: Path, error: Exception) -> None:
        try:
            self.conn.close()
        except Exception:
            pass
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidates = [
            original_path.with_name("usage-writable.db"),
            original_path.with_name(f"usage-writable-{stamp}.db"),
            Path.cwd() / "usage-writable.db",
            Path.cwd() / f"usage-writable-{stamp}.db",
        ]
        documents_dir = Path.home() / "Documents" / "UsageWidget"
        candidates.extend(
            [
                documents_dir / "usage-writable.db",
                documents_dir / f"usage-writable-{stamp}.db",
            ]
        )
        last_error: Exception = error
        fallback: Path | None = None
        for candidate in candidates:
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                if original_path.exists():
                    if candidate.exists():
                        pass
                    else:
                        try:
                            shutil.copyfile(original_path, candidate)
                        except Exception:
                            pass
                test = sqlite3.connect(candidate)
                test.execute("CREATE TABLE IF NOT EXISTS __write_test (id INTEGER)")
                test.execute("DROP TABLE IF EXISTS __write_test")
                test.commit()
                test.close()
                fallback = candidate
                break
            except Exception as exc:
                last_error = exc
                try:
                    test.close()  # type: ignore[name-defined]
                except Exception:
                    pass
                continue
        if fallback is None:
            raise sqlite3.OperationalError(
                f"默认数据库只读，且无法创建可写恢复库；原错误：{error}；最后错误：{last_error}"
            ) from last_error
        self.db_path = fallback
        self._settings_cache = None
        self._ignored_cache = None
        self._category_rules_cache = None
        self._connect()
        self._initialize_database()
        log_event(f"默认数据库只读，已切换到可写恢复库：{fallback}；原错误：{error}")

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ignored_processes (
                name TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS usage_daily (
                usage_date TEXT NOT NULL,
                exe_name TEXT NOT NULL,
                exe_path TEXT NOT NULL,
                foreground_seconds REAL NOT NULL DEFAULT 0,
                running_seconds REAL NOT NULL DEFAULT 0,
                last_seen TEXT NOT NULL,
                PRIMARY KEY (usage_date, exe_path)
            );

            CREATE INDEX IF NOT EXISTS idx_usage_daily_date
                ON usage_daily (usage_date);
            CREATE INDEX IF NOT EXISTS idx_usage_daily_exe
                ON usage_daily (exe_name);
            CREATE INDEX IF NOT EXISTS idx_usage_daily_path
                ON usage_daily (exe_path);

            CREATE TABLE IF NOT EXISTS content_usage_daily (
                usage_date TEXT NOT NULL,
                kind TEXT NOT NULL,
                exe_name TEXT NOT NULL,
                exe_path TEXT NOT NULL,
                content_key TEXT NOT NULL,
                content_title TEXT NOT NULL,
                content_url TEXT NOT NULL DEFAULT '',
                content_domain TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '其他',
                learning_topic TEXT NOT NULL DEFAULT '',
                attention_seconds REAL NOT NULL DEFAULT 0,
                background_seconds REAL NOT NULL DEFAULT 0,
                last_seen TEXT NOT NULL,
                PRIMARY KEY (usage_date, kind, exe_path, content_key)
            );

            CREATE INDEX IF NOT EXISTS idx_content_usage_daily_date
                ON content_usage_daily (usage_date);
            CREATE INDEX IF NOT EXISTS idx_content_usage_daily_kind
                ON content_usage_daily (kind);
            CREATE INDEX IF NOT EXISTS idx_content_usage_daily_path
                ON content_usage_daily (exe_path);

            CREATE TABLE IF NOT EXISTS category_rules (
                pattern TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                target TEXT NOT NULL DEFAULT 'any',
                source TEXT NOT NULL DEFAULT 'user'
            );

            CREATE TABLE IF NOT EXISTS goals (
                name TEXT PRIMARY KEY,
                metric TEXT NOT NULL,
                pattern TEXT NOT NULL DEFAULT '',
                target_seconds REAL NOT NULL,
                direction TEXT NOT NULL DEFAULT 'max',
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS timeline_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                event_date TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                app_name TEXT NOT NULL DEFAULT '',
                app_path TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '其他',
                learning_topic TEXT NOT NULL DEFAULT '',
                seconds REAL NOT NULL DEFAULT 0,
                extra TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_timeline_events_date
                ON timeline_events (event_date);
            CREATE INDEX IF NOT EXISTS idx_timeline_events_date_start
                ON timeline_events (event_date, start_time DESC);
            """
        )
        self.conn.commit()

    def _migrate_schema(self) -> None:
        self._ensure_columns(
            "content_usage_daily",
            {
                "content_url": "TEXT NOT NULL DEFAULT ''",
                "content_domain": "TEXT NOT NULL DEFAULT ''",
                "category": "TEXT NOT NULL DEFAULT '其他'",
                "learning_topic": "TEXT NOT NULL DEFAULT ''",
            },
        )
        self._ensure_columns(
            "timeline_events",
            {
                "learning_topic": "TEXT NOT NULL DEFAULT ''",
            },
        )
        self._ensure_columns(
            "category_rules",
            {
                "source": "TEXT NOT NULL DEFAULT 'user'",
            },
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_usage_daily_domain ON content_usage_daily (content_domain)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_usage_daily_category ON content_usage_daily (category)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_usage_daily_learning_topic ON content_usage_daily (learning_topic)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_timeline_events_date ON timeline_events (event_date)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_daily_path ON usage_daily (exe_path)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_timeline_events_date_start ON timeline_events (event_date, start_time DESC)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_timeline_events_date_kind ON timeline_events (event_date, kind)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_kind_domain ON content_usage_daily (kind, content_domain)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_date_kind ON content_usage_daily (usage_date, kind)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_kind_date ON content_usage_daily (kind, usage_date)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_date_category ON content_usage_daily (usage_date, category)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_date_learning_topic ON content_usage_daily (usage_date, learning_topic)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_kind_date_domain ON content_usage_daily (kind, usage_date, content_domain)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_date_path_nocase ON content_usage_daily (usage_date, exe_path COLLATE NOCASE)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_date_lower_path ON content_usage_daily (usage_date, lower(exe_path))"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_date_path ON usage_daily (usage_date, exe_path)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_date_path_nocase ON usage_daily (usage_date, exe_path COLLATE NOCASE)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_usage_date_lower_path ON usage_daily (usage_date, lower(exe_path))"
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goal_streaks (
                goal_name TEXT NOT NULL,
                streak_date TEXT NOT NULL,
                achieved INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (goal_name, streak_date)
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_goal_streaks_name ON goal_streaks (goal_name)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_goal_streaks_date ON goal_streaks (streak_date)"
        )
        try:
            self._migrate_browser_media_to_video()
        except sqlite3.OperationalError as exc:
            log_event(f"浏览器媒体旧数据迁移跳过：{exc}")
        self.conn.commit()

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        existing = {
            str(row["name"])
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, definition in columns.items():
            if name not in existing:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def _migrate_browser_media_to_video(self) -> None:
        filters = " OR ".join(
            "lower(exe_name) LIKE ? OR lower(exe_path) LIKE ?"
            for _ in BROWSER_MEDIA_HINTS
        )
        params: list[object] = []
        for hint in BROWSER_MEDIA_HINTS:
            like = f"%{hint}%"
            params.extend([like, like])
        self.conn.execute(
            f"""
            INSERT INTO content_usage_daily (
                usage_date, kind, exe_name, exe_path, content_key, content_title,
                content_url, content_domain, category, learning_topic, attention_seconds,
                background_seconds, last_seen
            )
            SELECT usage_date, 'video_playback', exe_name, exe_path,
                   'video_playback:' || content_key, content_title, content_url,
                   content_domain, category, learning_topic, attention_seconds, background_seconds,
                   last_seen
            FROM content_usage_daily
            WHERE kind = 'media_playback' AND ({filters})
            ON CONFLICT(usage_date, kind, exe_path, content_key) DO UPDATE SET
                exe_name = excluded.exe_name,
                content_title = excluded.content_title,
                content_url = excluded.content_url,
                content_domain = excluded.content_domain,
                category = excluded.category,
                learning_topic = excluded.learning_topic,
                attention_seconds = content_usage_daily.attention_seconds + excluded.attention_seconds,
                background_seconds = content_usage_daily.background_seconds + excluded.background_seconds,
                last_seen = excluded.last_seen
            """,
            params,
        )
        self.conn.execute(
            f"""
            DELETE FROM content_usage_daily
            WHERE kind = 'media_playback' AND ({filters})
            """,
            params,
        )

    def _ensure_defaults(self) -> None:
        initialized = self.get_setting("defaults_initialized", "0")
        self.conn.executemany(
            "INSERT OR IGNORE INTO ignored_processes (name) VALUES (?)",
            [(name.lower(),) for name in sorted(DEFAULT_IGNORED)],
        )
        self._ensure_default_category_rules()
        self._ensure_default_goals()
        defaults = AppSettings()
        for key, value in {
            "theme": defaults.theme,
            "always_expanded": str(int(defaults.always_expanded)),
            "window_opacity": str(defaults.window_opacity),
            "background_alpha": str(defaults.background_alpha),
            "auto_start": str(int(defaults.auto_start)),
            "track_window_titles": str(int(defaults.track_window_titles)),
            "track_media_sessions": str(int(defaults.track_media_sessions)),
            "track_browser_urls": str(int(defaults.track_browser_urls)),
            "idle_threshold_seconds": str(defaults.idle_threshold_seconds),
            "pause_tracking": str(int(defaults.pause_tracking)),
            "private_title_mode": str(int(defaults.private_title_mode)),
            "online_music_lookup": str(int(defaults.online_music_lookup)),
            "online_category_lookup": str(int(defaults.online_category_lookup)),
            "media_activity_keeps_attention": str(int(defaults.media_activity_keeps_attention)),
            "handwriting_mode": str(int(defaults.handwriting_mode)),
            "handwriting_apps": defaults.handwriting_apps,
            "timeline_retention_days": str(defaults.timeline_retention_days),
            "top_list_sort": defaults.top_list_sort,
            "daily_summary": str(int(defaults.daily_summary)),
            "last_summary_date": defaults.last_summary_date,
            "defaults_initialized": "1",
        }.items():
            if initialized != "1" or not self.get_setting(key, ""):
                self.set_setting(key, value, commit=False)
        self.conn.commit()

    def _ensure_default_category_rules(self) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO category_rules (pattern, category, target, source) VALUES (?, ?, ?, 'default')",
            DEFAULT_CATEGORY_RULES,
        )
        self.conn.executemany(
            """
            UPDATE category_rules
            SET source = 'default'
            WHERE pattern = ? AND category = ? AND target = ? AND source IN ('', 'user')
            """,
            [(pattern, category, target) for pattern, category, target in DEFAULT_CATEGORY_RULES],
        )
        self.conn.executemany(
            "UPDATE category_rules SET category = ?, source = 'default' WHERE pattern = ? AND target = ? AND category = ?",
            [
                ("聊天", "qq.exe", "app", "社交"),
                ("聊天", "weixin.exe", "app", "社交"),
                ("娱乐", "douyin.com", "domain", "视频"),
                ("娱乐", "weibo.com", "domain", "社交"),
            ],
        )
        self._apply_default_category_rules_to_existing()

    def _apply_default_category_rules_to_existing(self) -> None:
        for pattern, category, target in DEFAULT_CATEGORY_RULES:
            like = f"%{pattern.lower()}%"
            if target == "domain":
                self.conn.execute(
                    """
                    UPDATE content_usage_daily
                    SET category = ?
                    WHERE category = '其他' AND lower(content_domain) LIKE ?
                    """,
                    (category, like),
                )
            elif target == "title":
                self.conn.execute(
                    """
                    UPDATE content_usage_daily
                    SET category = ?
                    WHERE category = '其他' AND lower(content_title) LIKE ?
                    """,
                    (category, like),
                )
            elif target == "app":
                self.conn.execute(
                    """
                    UPDATE content_usage_daily
                    SET category = ?
                    WHERE category = '其他'
                      AND (lower(exe_name) LIKE ? OR lower(exe_path) LIKE ?)
                    """,
                    (category, like, like),
                )
        self.conn.execute(
            """
            UPDATE content_usage_daily
            SET category = '聊天'
            WHERE category = '社交'
              AND (lower(exe_name) LIKE '%qq.exe%' OR lower(exe_name) LIKE '%weixin.exe%' OR lower(exe_name) LIKE '%wechat.exe%')
            """
        )

    def _ensure_default_goals(self) -> None:
        goals = [
            ("学习至少 1 小时", "learning_topic", "", 3600, "min", 1),
            ("编程至少 2 小时", "learning_topic", "Python", 7200, "min", 0),
            ("视频不超过 1 小时", "category", "视频", 3600, "max", 1),
        ]
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO goals (name, metric, pattern, target_seconds, direction, enabled)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            goals,
        )

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str, commit: bool = True) -> None:
        self.conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self._settings_cache = None
        if commit:
            self.conn.commit()

    def load_settings(self) -> AppSettings:
        if self._settings_cache is not None:
            return self._settings_cache

        def as_bool(key: str, default: bool) -> bool:
            return self.get_setting(key, str(int(default))) == "1"

        def as_float(key: str, default: float) -> float:
            try:
                return float(self.get_setting(key, str(default)))
            except ValueError:
                return default

        def as_int_optional(key: str) -> int | None:
            value = self.get_setting(key, "")
            if not value:
                return None
            try:
                return int(value)
            except ValueError:
                return None

        self._settings_cache = AppSettings(
            theme=self.get_setting("theme", "system"),
            always_expanded=as_bool("always_expanded", True),
            window_opacity=max(0.4, min(1.0, as_float("window_opacity", 0.92))),
            background_alpha=max(40, min(245, int(as_float("background_alpha", 190)))),
            pos_x=as_int_optional("pos_x"),
            pos_y=as_int_optional("pos_y"),
            auto_start=as_bool("auto_start", False),
            track_window_titles=as_bool("track_window_titles", True),
            track_media_sessions=as_bool("track_media_sessions", True),
            track_browser_urls=as_bool("track_browser_urls", True),
            idle_threshold_seconds=max(30, min(3600, int(as_float("idle_threshold_seconds", 180)))),
            pause_tracking=as_bool("pause_tracking", False),
            private_title_mode=as_bool("private_title_mode", False),
            online_music_lookup=as_bool("online_music_lookup", False),
            online_category_lookup=as_bool("online_category_lookup", False),
            media_activity_keeps_attention=as_bool("media_activity_keeps_attention", True),
            handwriting_mode=as_bool("handwriting_mode", True),
            handwriting_apps=self.get_setting(
                "handwriting_apps",
                "onenote.exe,applicationframehost.exe,whiteboard.exe,journal.exe,powerpnt.exe",
            ),
            timeline_retention_days=max(0, min(3650, int(as_float("timeline_retention_days", 90)))),
            top_list_sort=self.get_setting("top_list_sort", "current_first")
            if self.get_setting("top_list_sort", "current_first") in {"current_first", "foreground", "running", "name"}
            else "current_first",
            daily_summary=as_bool("daily_summary", True),
            last_summary_date=self.get_setting("last_summary_date", ""),
        )
        return self._settings_cache

    def save_settings(self, settings: AppSettings) -> None:
        values = {
            "theme": settings.theme,
            "always_expanded": str(int(settings.always_expanded)),
            "window_opacity": str(settings.window_opacity),
            "background_alpha": str(settings.background_alpha),
            "auto_start": str(int(settings.auto_start)),
            "track_window_titles": str(int(settings.track_window_titles)),
            "track_media_sessions": str(int(settings.track_media_sessions)),
            "track_browser_urls": str(int(settings.track_browser_urls)),
            "idle_threshold_seconds": str(settings.idle_threshold_seconds),
            "pause_tracking": str(int(settings.pause_tracking)),
            "private_title_mode": str(int(settings.private_title_mode)),
            "online_music_lookup": str(int(settings.online_music_lookup)),
            "online_category_lookup": str(int(settings.online_category_lookup)),
            "media_activity_keeps_attention": str(int(settings.media_activity_keeps_attention)),
            "handwriting_mode": str(int(settings.handwriting_mode)),
            "handwriting_apps": settings.handwriting_apps,
            "timeline_retention_days": str(settings.timeline_retention_days),
            "top_list_sort": settings.top_list_sort
            if settings.top_list_sort in {"current_first", "foreground", "running", "name"}
            else "current_first",
            "daily_summary": str(int(settings.daily_summary)),
            "last_summary_date": settings.last_summary_date,
        }
        if settings.pos_x is not None:
            values["pos_x"] = str(settings.pos_x)
        if settings.pos_y is not None:
            values["pos_y"] = str(settings.pos_y)
        for key, value in values.items():
            self.set_setting(key, value, commit=False)
        self._settings_cache = None
        self.conn.commit()

    def increment_content_usage(self, samples: Iterable[dict[str, object]], when: datetime, commit: bool = True) -> None:
        usage_date = when.date().isoformat()
        last_seen = when.isoformat(timespec="seconds")
        rows = []
        for sample in samples:
            kind = str(sample["kind"])
            exe_name = str(sample["exe_name"])
            exe_path = str(sample["exe_path"])
            content_key = str(sample["content_key"])
            content_title = str(sample["content_title"])
            content_url = str(sample.get("content_url", ""))
            content_domain = str(sample.get("content_domain", ""))
            category = str(sample.get("category", self.category_for(exe_name, content_domain, content_title)))
            learning_topic = str(sample.get("learning_topic", "")).strip()
            attention = float(sample.get("attention_seconds", 0.0))
            background = float(sample.get("background_seconds", 0.0))
            if not kind or not exe_name or not exe_path or not content_key or not content_title:
                continue
            if attention <= 0 and background <= 0:
                continue
            rows.append(
                (
                    usage_date,
                    kind,
                    exe_name,
                    exe_path,
                    content_key,
                    content_title,
                    content_url,
                    content_domain,
                    category,
                    learning_topic,
                    attention,
                    background,
                    last_seen,
                )
            )
        if not rows:
            return
        self.conn.executemany(
            """
            INSERT INTO content_usage_daily (
                usage_date, kind, exe_name, exe_path, content_key, content_title,
                content_url, content_domain, category,
                learning_topic, attention_seconds, background_seconds, last_seen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(usage_date, kind, exe_path, content_key) DO UPDATE SET
                exe_name = excluded.exe_name,
                content_title = excluded.content_title,
                content_url = excluded.content_url,
                content_domain = excluded.content_domain,
                category = excluded.category,
                learning_topic = CASE
                    WHEN excluded.learning_topic != '' THEN excluded.learning_topic
                    ELSE content_usage_daily.learning_topic
                END,
                attention_seconds = content_usage_daily.attention_seconds + excluded.attention_seconds,
                background_seconds = content_usage_daily.background_seconds + excluded.background_seconds,
                last_seen = excluded.last_seen
            """,
            rows,
        )
        if commit:
            self.conn.commit()

    def category_rules(self) -> list[sqlite3.Row]:
        if self._category_rules_cache is None:
            self._category_rules_cache = self.conn.execute(
                "SELECT pattern, category, target, source FROM category_rules ORDER BY category, pattern"
            ).fetchall()
        return self._category_rules_cache

    def replace_category_rules(self, rules: Iterable[tuple[str, ...]]) -> None:
        clean = []
        default_set = {(pattern.lower(), category, target) for pattern, category, target in DEFAULT_CATEGORY_RULES}
        target_aliases = {"标题": "title", "域名": "domain", "程序": "app", "全部": "any"}
        source_aliases = {"本地规则": "default", "用户纠正": "user", "联网分类": "online"}
        for rule in rules:
            if len(rule) < 3:
                continue
            pattern, category, target = rule[:3]
            source = rule[3] if len(rule) >= 4 else ""
            pattern = pattern.strip().lower()
            category = category.strip() or "其他"
            target = target_aliases.get(target.strip(), target.strip()) or "any"
            source = source_aliases.get(source.strip(), source.strip().lower()) if source else "default" if (pattern, category, target) in default_set else "user"
            if target not in {"app", "domain", "title", "any"}:
                target = "any"
            if source not in {"default", "user", "online"}:
                source = "user"
            if pattern:
                clean.append((pattern, category, target, source))
        self.conn.execute("DELETE FROM category_rules")
        self.conn.executemany(
            "INSERT INTO category_rules (pattern, category, target, source) VALUES (?, ?, ?, ?)",
            clean,
        )
        self._category_rules_cache = None
        self.conn.commit()

    def add_category_rule(
        self,
        pattern: str,
        category: str,
        target: str = "any",
        update_existing: bool = True,
        source: str = "user",
    ) -> None:
        pattern = pattern.strip().lower()
        category = category.strip() or "其他"
        target = {"标题": "title", "域名": "domain", "程序": "app", "全部": "any"}.get(target.strip(), target.strip().lower()) or "any"
        source = {"本地规则": "default", "用户纠正": "user", "联网分类": "online"}.get(source.strip(), source.strip().lower()) or "user"
        if not pattern:
            return
        if target not in {"app", "domain", "title", "any"}:
            target = "any"
        if source not in {"default", "user", "online"}:
            source = "user"
        if source == "online" and not update_existing:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO category_rules (pattern, category, target, source)
                VALUES (?, ?, ?, ?)
                """,
                (pattern, category, target, source),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO category_rules (pattern, category, target, source)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(pattern) DO UPDATE SET
                    category = excluded.category,
                    target = excluded.target,
                    source = excluded.source
                """,
                (pattern, category, target, source),
            )
        if update_existing:
            like = f"%{pattern}%"
            if target == "domain":
                self.conn.execute(
                    "UPDATE content_usage_daily SET category = ? WHERE lower(content_domain) LIKE ?",
                    (category, like),
                )
            elif target == "title":
                self.conn.execute(
                    "UPDATE content_usage_daily SET category = ? WHERE lower(content_title) LIKE ?",
                    (category, like),
                )
            elif target == "app":
                self.conn.execute(
                    """
                    UPDATE content_usage_daily
                    SET category = ?
                    WHERE lower(exe_name) LIKE ? OR lower(exe_path) LIKE ?
                    """,
                    (category, like, like),
                )
            else:
                self.conn.execute(
                    """
                    UPDATE content_usage_daily
                    SET category = ?
                    WHERE lower(content_domain) LIKE ?
                       OR lower(content_title) LIKE ?
                       OR lower(exe_name) LIKE ?
                       OR lower(exe_path) LIKE ?
                    """,
                    (category, like, like, like, like),
                )
        self._category_rules_cache = None
        self.conn.commit()

    def _category_rule_match(
        self,
        exe_name: str = "",
        domain: str = "",
        title: str = "",
    ) -> tuple[int, int, str, str, str, str] | None:
        exe = (exe_name or "").lower()
        domain_l = (domain or "").lower()
        title_l = (title or "").lower()
        combined = f"{exe} {domain_l} {title_l}"
        best: tuple[int, int, str, str, str, str] | None = None
        for row in self.category_rules():
            pattern = str(row["pattern"]).lower()
            target = str(row["target"])
            category = str(row["category"])
            source = str(row["source"] or "user")
            score = 0
            if target in {"any", "title"} and title_l and pattern in title_l:
                score = max(score, 400 + len(pattern))
            if target in {"any", "domain"} and domain_l and pattern in domain_l:
                score = max(score, 300 + len(pattern))
            if target in {"any", "app"} and exe and pattern in exe:
                score = max(score, 250 + len(pattern))
            if target == "any" and score == 0 and pattern in combined:
                score = 100 + len(pattern)
            if score > 0 and (best is None or score > best[0]):
                best = (score, len(pattern), category, target, pattern, source)
        return best

    def category_for(self, exe_name: str, domain: str = "", title: str = "") -> str:
        best = self._category_rule_match(exe_name, domain, title)
        return best[2] if best else "其他"

    def category_explanation(
        self,
        category: str,
        exe_name: str = "",
        domain: str = "",
        title: str = "",
        learning_topic: str = "",
    ) -> str:
        category = category or "其他"
        if learning_topic:
            return f"命中学习主题：{learning_topic} · 来源：学习主题识别 · 置信度：高"
        best = self._category_rule_match(exe_name, domain, title)
        if best and best[2] == category:
            _score, _length, _rule_category, target, pattern, source_key = best
            target_labels = {"title": "标题关键词", "domain": "域名", "app": "程序", "any": "综合关键词"}
            source_labels = {"default": "本地规则", "user": "用户纠正", "online": "联网分类"}
            source = source_labels.get(source_key, "用户纠正")
            confidence = "高" if source_key in {"default", "user"} else "中"
            return f"命中规则：{target_labels.get(target, target)}“{pattern}” · 来源：{source} · 置信度：{confidence}"
        if category in {"其他", ""}:
            return "未命中明确规则 · 来源：兜底分类 · 置信度：低"
        if category in {"视频", "网站", "浏览器", "工具"}:
            return f"未命中细分类 · 来源：本地兜底 · 置信度：低"
        return f"未保存具体命中 · 来源：本地/联网分类 · 置信度：中"

    def recognition_health_range(self, start_date: date, end_date: date) -> dict[str, int | float | str]:
        start, end = start_date.isoformat(), end_date.isoformat()
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS total_rows,
                SUM(CASE WHEN kind='web_page' THEN 1 ELSE 0 END) AS web_rows,
                SUM(CASE WHEN kind='web_page' AND content_domain != ''
                    AND (
                        TRIM(content_title) = ''
                        OR lower(TRIM(content_title)) = lower(TRIM(content_domain))
                        OR lower(TRIM(content_title)) LIKE 'http%'
                    )
                    THEN 1 ELSE 0 END) AS web_domain_only_rows,
                SUM(CASE WHEN kind='video_playback' AND category = '视频' THEN 1 ELSE 0 END) AS broad_video_rows,
                SUM(CASE WHEN category IN ('其他', '视频', '网站', '浏览器', '工具') AND learning_topic = ''
                    THEN 1 ELSE 0 END) AS low_confidence_rows
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ?
            """,
            (start, end),
        ).fetchone()
        total = int(row["total_rows"] or 0)
        domain_only = int(row["web_domain_only_rows"] or 0)
        broad_video = int(row["broad_video_rows"] or 0)
        low_conf = int(row["low_confidence_rows"] or 0)
        if total <= 0:
            score = 100
        else:
            penalty = domain_only * 8 + broad_video * 6 + low_conf * 3
            score = max(0, min(100, int(round(100 - penalty / max(total, 1)))))
        if score >= 85:
            level = "良好"
        elif score >= 65:
            level = "一般"
        else:
            level = "需处理"
        return {
            "score": score,
            "level": level,
            "total_rows": total,
            "web_rows": int(row["web_rows"] or 0),
            "web_domain_only_rows": domain_only,
            "broad_video_rows": broad_video,
            "low_confidence_rows": low_conf,
        }

    def add_timeline_event(
        self,
        start_time: datetime,
        end_time: datetime,
        kind: str,
        title: str,
        seconds: float,
        app_name: str = "",
            app_path: str = "",
            category: str = "其他",
            learning_topic: str = "",
            extra: str = "",
        commit: bool = True,
    ) -> None:
        if seconds <= 0:
            return
        self.insert_timeline_events(
            [
                {
                    "start_time": start_time,
                    "end_time": end_time,
                    "kind": kind,
                    "title": title,
                    "seconds": seconds,
                    "app_name": app_name,
                    "app_path": app_path,
                    "category": category,
                    "learning_topic": learning_topic,
                    "extra": extra,
                }
            ],
            commit=commit,
        )

    def insert_timeline_events(self, events: Iterable[dict[str, object]], commit: bool = True) -> None:
        rows = []
        for event in events:
            seconds = float(event.get("seconds", 0.0))
            if seconds <= 0:
                continue
            start_time = event.get("start_time")
            end_time = event.get("end_time")
            if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
                continue
            rows.append(
                (
                    start_time.isoformat(timespec="seconds"),
                    end_time.isoformat(timespec="seconds"),
                    start_time.date().isoformat(),
                    str(event.get("kind", "")),
                    str(event.get("title", "")),
                    str(event.get("app_name", "")),
                    str(event.get("app_path", "")),
                    str(event.get("category", "其他")),
                    str(event.get("learning_topic", "")),
                    seconds,
                    str(event.get("extra", "")),
                )
            )
        if not rows:
            return
        self.conn.executemany(
            """
            INSERT INTO timeline_events (
                start_time, end_time, event_date, kind, title, app_name, app_path,
                category, learning_topic, seconds, extra
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        if commit:
            self.conn.commit()

    def record_activity(
        self,
        usage_samples: Iterable[dict[str, object]],
        content_samples: Iterable[dict[str, object]],
        timeline_events: Iterable[dict[str, object]],
        when: datetime,
    ) -> None:
        self.conn.execute("BEGIN")
        try:
            self.increment_usage(usage_samples, when, commit=False)
            self.increment_content_usage(content_samples, when, commit=False)
            self.insert_timeline_events(timeline_events, commit=False)
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()

    def save_position(self, x: int, y: int) -> None:
        self.set_setting("pos_x", str(x), commit=False)
        self.set_setting("pos_y", str(y), commit=True)

    def ignored_processes(self) -> list[str]:
        if self._ignored_cache is not None:
            return self._ignored_cache
        rows = self.conn.execute("SELECT name FROM ignored_processes ORDER BY name").fetchall()
        self._ignored_cache = [str(row["name"]) for row in rows]
        return self._ignored_cache

    def replace_ignored_processes(self, names: Iterable[str]) -> None:
        clean = sorted({name.strip().lower() for name in names if name.strip()})
        self.conn.execute("DELETE FROM ignored_processes")
        self.conn.executemany(
            "INSERT INTO ignored_processes (name) VALUES (?)",
            [(name,) for name in clean],
        )
        self._ignored_cache = None
        self.conn.commit()

    def increment_usage(self, samples: Iterable[dict[str, object]], when: datetime, commit: bool = True) -> None:
        usage_date = when.date().isoformat()
        last_seen = when.isoformat(timespec="seconds")
        rows = []
        for sample in samples:
            exe_name = str(sample["exe_name"])
            exe_path = str(sample["exe_path"])
            fg = float(sample.get("foreground_seconds", 0.0))
            running = float(sample.get("running_seconds", 0.0))
            if not exe_name or not exe_path or (fg <= 0 and running <= 0):
                continue
            rows.append((usage_date, exe_name, exe_path, fg, running, last_seen))
        if not rows:
            return
        self.conn.executemany(
            """
            INSERT INTO usage_daily (
                usage_date, exe_name, exe_path,
                foreground_seconds, running_seconds, last_seen
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(usage_date, exe_path) DO UPDATE SET
                exe_name = excluded.exe_name,
                foreground_seconds = usage_daily.foreground_seconds + excluded.foreground_seconds,
                running_seconds = usage_daily.running_seconds + excluded.running_seconds,
                last_seen = excluded.last_seen
            """,
            rows,
        )
        if commit:
            self.conn.commit()

    def stats_for_paths(self, paths: Iterable[str], target_date: date | None = None) -> dict[str, sqlite3.Row]:
        clean = sorted({path for path in paths if path})
        if not clean:
            return {}
        usage_date = (target_date or date.today()).isoformat()
        requested_by_lower = {path.lower(): path for path in clean}
        lookup_paths = sorted(requested_by_lower)
        placeholders = ",".join("?" for _ in lookup_paths)
        rows = self.conn.execute(
            f"""
            SELECT lower(exe_path) AS lookup_path,
                   MAX(exe_name) AS exe_name,
                   MAX(exe_path) AS exe_path,
                   COALESCE(SUM(foreground_seconds), 0) AS foreground_seconds,
                   COALESCE(SUM(running_seconds), 0) AS running_seconds,
                   MAX(last_seen) AS last_seen
            FROM usage_daily
            WHERE usage_date = ? AND exe_path COLLATE NOCASE IN ({placeholders})
            GROUP BY exe_path COLLATE NOCASE
            """,
            [usage_date, *lookup_paths],
        ).fetchall()
        result: dict[str, sqlite3.Row] = {}
        for row in rows:
            requested = requested_by_lower.get(str(row["lookup_path"]))
            if requested:
                result[requested] = row
            result[str(row["exe_path"])] = row
        return result

    def total_for_path(self, path: str) -> dict[str, float]:
        row = self.totals_for_paths([path]).get(path)
        if not row:
            return {"foreground_seconds": 0.0, "running_seconds": 0.0}
        return {
            "foreground_seconds": float(row["foreground_seconds"]),
            "running_seconds": float(row["running_seconds"]),
        }

    def totals_for_paths(self, paths: Iterable[str]) -> dict[str, dict[str, float]]:
        clean = sorted({path for path in paths if path})
        if not clean:
            return {}
        requested_by_lower = {path.lower(): path for path in clean}
        lookup_paths = sorted(requested_by_lower)
        placeholders = ",".join("?" for _ in lookup_paths)
        rows = self.conn.execute(
            f"""
            SELECT lower(exe_path) AS lookup_path,
                   MAX(exe_path) AS exe_path,
                   COALESCE(SUM(foreground_seconds), 0) AS foreground_seconds,
                   COALESCE(SUM(running_seconds), 0) AS running_seconds
            FROM usage_daily
            WHERE exe_path COLLATE NOCASE IN ({placeholders})
            GROUP BY exe_path COLLATE NOCASE
            """,
            lookup_paths,
        ).fetchall()
        result: dict[str, dict[str, float]] = {}
        for row in rows:
            value = {
                "foreground_seconds": float(row["foreground_seconds"] or 0),
                "running_seconds": float(row["running_seconds"] or 0),
            }
            requested = requested_by_lower.get(str(row["lookup_path"]))
            if requested:
                result[requested] = value
            result[str(row["exe_path"])] = value
        return result

    def day_total_foreground(self, target_date: date | None = None) -> float:
        usage_date = (target_date or date.today()).isoformat()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(foreground_seconds), 0) AS total FROM usage_daily WHERE usage_date = ?",
            (usage_date,),
        ).fetchone()
        return float(row["total"] or 0)

    def date_range_for_preset(self, preset: str) -> tuple[date, date]:
        today = date.today()
        if preset == "yesterday":
            day = today - timedelta(days=1)
            return day, day
        if preset == "7d":
            return today - timedelta(days=6), today
        if preset == "30d":
            return today - timedelta(days=29), today
        if preset == "week":
            today_idx = today.weekday()
            return today - timedelta(days=today_idx), today
        if preset == "last_week":
            today_idx = today.weekday()
            last_monday = today - timedelta(days=today_idx + 7)
            return last_monday, last_monday + timedelta(days=6)
        if preset == "84d":
            return today - timedelta(days=83), today
        return today, today

    def foreground_total_range(self, start_date: date, end_date: date) -> float:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(foreground_seconds), 0) AS total
            FROM usage_daily
            WHERE usage_date BETWEEN ? AND ?
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchone()
        return float(row["total"] or 0)

    def media_total_range(self, start_date: date, end_date: date) -> float:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(background_seconds), 0) AS total
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ?
              AND (kind = 'media_playback' OR (kind = 'video_playback' AND category = '音乐'))
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchone()
        return float(row["total"] or 0)

    def video_total_range(self, start_date: date, end_date: date) -> float:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(background_seconds), 0) AS total
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ? AND kind = 'video_playback'
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchone()
        return float(row["total"] or 0)

    def overview_counts_range(self, start_date: date, end_date: date) -> dict[str, float | int]:
        """Small aggregate used by the overview tab without loading detail tables."""
        s = start_date.isoformat()
        e = end_date.isoformat()
        process_row = self.conn.execute(
            """
            SELECT COUNT(DISTINCT exe_path) AS program_count
            FROM usage_daily
            WHERE usage_date BETWEEN ? AND ?
            """,
            (s, e),
        ).fetchone()
        content_row = self.conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN kind = 'web_page' THEN attention_seconds ELSE 0 END), 0) AS web_attention,
                COUNT(DISTINCT CASE WHEN kind = 'web_page'
                    THEN kind || ':' || exe_path || ':' || content_key END) AS web_count,
                COUNT(DISTINCT CASE WHEN kind = 'video_playback'
                    THEN kind || ':' || exe_path || ':' || content_key END) AS video_count,
                COUNT(DISTINCT CASE
                    WHEN kind = 'media_playback' OR (kind = 'video_playback' AND category = '音乐')
                    THEN kind || ':' || exe_path || ':' || content_key END) AS music_count,
                COUNT(DISTINCT CASE WHEN kind = 'web_page' AND content_domain != ''
                    THEN content_domain END) AS web_domain_count,
                COUNT(DISTINCT CASE WHEN category != '' THEN category END) AS category_count,
                COUNT(DISTINCT CASE
                    WHEN category = '学习' OR learning_topic != ''
                    THEN CASE WHEN learning_topic != '' THEN learning_topic ELSE '综合学习' END
                END) AS learning_topic_count
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ?
            """,
            (s, e),
        ).fetchone()
        return {
            "program_count": int(process_row["program_count"] or 0),
            "web_attention": float(content_row["web_attention"] or 0),
            "web_count": int(content_row["web_count"] or 0),
            "video_count": int(content_row["video_count"] or 0),
            "music_count": int(content_row["music_count"] or 0),
            "web_domain_count": int(content_row["web_domain_count"] or 0),
            "category_count": int(content_row["category_count"] or 0),
            "learning_topic_count": int(content_row["learning_topic_count"] or 0),
        }

    def day_total_media_playback(self, target_date: date | None = None) -> float:
        usage_date = (target_date or date.today()).isoformat()
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(background_seconds), 0) AS total
            FROM content_usage_daily
            WHERE usage_date = ?
              AND (kind = 'media_playback' OR (kind = 'video_playback' AND category = '音乐'))
            """,
            (usage_date,),
        ).fetchone()
        return float(row["total"] or 0)

    def day_overview_totals(self, target_date: date | None = None) -> dict[str, float]:
        usage_date = (target_date or date.today()).isoformat()
        foreground_row = self.conn.execute(
            "SELECT COALESCE(SUM(foreground_seconds), 0) AS total FROM usage_daily WHERE usage_date = ?",
            (usage_date,),
        ).fetchone()
        content_row = self.conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN kind = 'video_playback' THEN background_seconds ELSE 0 END), 0) AS video,
                COALESCE(SUM(CASE
                    WHEN kind = 'media_playback' OR (kind = 'video_playback' AND category = '音乐')
                    THEN background_seconds ELSE 0
                END), 0) AS media
            FROM content_usage_daily
            WHERE usage_date = ? AND kind IN ('video_playback', 'media_playback')
            """,
            (usage_date,),
        ).fetchone()
        learning_row = self.conn.execute(
            """
            SELECT COALESCE(SUM(attention_seconds + background_seconds), 0) AS total
            FROM content_usage_daily
            WHERE usage_date = ? AND (category = '学习' OR learning_topic != '')
            """,
            (usage_date,),
        ).fetchone()
        totals = {
            "foreground": float(foreground_row["total"] or 0),
            "video": float(content_row["video"] or 0),
            "media": float(content_row["media"] or 0),
            "learning": float(learning_row["total"] or 0),
        }
        return totals

    def week_comparison(self) -> dict[str, dict[str, float]]:
        this_start, this_end = self.date_range_for_preset("week")
        last_start, last_end = self.date_range_for_preset("last_week")

        def _totals(s: date, e: date) -> dict[str, float]:
            row = self.conn.execute(
                """
                SELECT
                    (SELECT COALESCE(SUM(foreground_seconds), 0) FROM usage_daily
                     WHERE usage_date BETWEEN ? AND ?) AS fg,
                    (SELECT COALESCE(SUM(background_seconds), 0) FROM content_usage_daily
                     WHERE usage_date BETWEEN ? AND ? AND kind='video_playback') AS vid,
                    (SELECT COALESCE(SUM(background_seconds), 0) FROM content_usage_daily
                     WHERE usage_date BETWEEN ? AND ?
                       AND (kind='media_playback' OR (kind='video_playback' AND category='音乐'))) AS mus,
                    (SELECT COALESCE(SUM(attention_seconds + background_seconds), 0) FROM content_usage_daily
                     WHERE usage_date BETWEEN ? AND ?
                       AND (category='学习' OR learning_topic!='')) AS lrn
                """,
                (s.isoformat(), e.isoformat(),
                 s.isoformat(), e.isoformat(),
                 s.isoformat(), e.isoformat(),
                 s.isoformat(), e.isoformat()),
            ).fetchone()
            return {
                "foreground": float(row["fg"] or 0),
                "video": float(row["vid"] or 0),
                "music": float(row["mus"] or 0),
                "learning": float(row["lrn"] or 0),
            }

        return {
            "current_week": _totals(this_start, this_end),
            "last_week": _totals(last_start, last_end),
        }

    def daily_heatmap_range(self, start_date: date, end_date: date) -> list[tuple[str, float, float, float, float]]:
        s = start_date.isoformat()
        e = end_date.isoformat()
        cursor = self.conn.execute(
            """
            WITH RECURSIVE dates(d) AS (
                SELECT ? AS d
                UNION ALL
                SELECT date(d, '+1 day') FROM dates WHERE d < ?
            )
            SELECT dates.d AS usage_date,
                   COALESCE(f.fg, 0) AS fg,
                   COALESCE(c.vid, 0) AS vid,
                   COALESCE(c.mus, 0) AS mus,
                   COALESCE(c.lrn, 0) AS lrn
            FROM dates
            LEFT JOIN (
                SELECT usage_date, COALESCE(SUM(foreground_seconds), 0) AS fg
                FROM usage_daily WHERE usage_date BETWEEN ? AND ? GROUP BY usage_date
            ) f ON dates.d = f.usage_date
            LEFT JOIN (
                SELECT usage_date,
                    COALESCE(SUM(CASE WHEN kind='video_playback' THEN background_seconds ELSE 0 END), 0) AS vid,
                    COALESCE(SUM(CASE WHEN kind='media_playback' OR (kind='video_playback' AND category='音乐')
                                THEN background_seconds ELSE 0 END), 0) AS mus,
                    COALESCE(SUM(CASE WHEN category='学习' OR learning_topic!=''
                                THEN attention_seconds+background_seconds ELSE 0 END), 0) AS lrn
                FROM content_usage_daily WHERE usage_date BETWEEN ? AND ? GROUP BY usage_date
            ) c ON dates.d = c.usage_date
            ORDER BY dates.d
            """,
            (s, e, s, e, s, e),
        ).fetchall()
        return [
            (str(r["usage_date"]), float(r["fg"]), float(r["vid"]), float(r["mus"]), float(r["lrn"]))
            for r in cursor
        ]

    def week_daily_breakdown(self, metric: str = "foreground") -> dict[str, list[tuple[str, float]]]:
        this_s, this_e = self.date_range_for_preset("week")
        last_s, last_e = self.date_range_for_preset("last_week")
        day_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

        def _daily(s: date, e: date) -> list[tuple[str, float]]:
            if metric == "learning":
                rows = self.conn.execute(
                    """SELECT usage_date, COALESCE(SUM(attention_seconds + background_seconds), 0) AS val
                       FROM content_usage_daily
                       WHERE usage_date BETWEEN ? AND ? AND (category='学习' OR learning_topic!='')
                       GROUP BY usage_date ORDER BY usage_date""",
                    (s.isoformat(), e.isoformat())).fetchall()
            elif metric == "foreground":
                rows = self.conn.execute(
                    """SELECT usage_date, COALESCE(SUM(foreground_seconds), 0) AS val
                       FROM usage_daily WHERE usage_date BETWEEN ? AND ?
                       GROUP BY usage_date ORDER BY usage_date""",
                    (s.isoformat(), e.isoformat())).fetchall()
            elif metric == "video":
                rows = self.conn.execute(
                    """SELECT usage_date, COALESCE(SUM(background_seconds), 0) AS val
                       FROM content_usage_daily WHERE usage_date BETWEEN ? AND ? AND kind='video_playback'
                       GROUP BY usage_date ORDER BY usage_date""",
                    (s.isoformat(), e.isoformat())).fetchall()
            else:
                rows = self.conn.execute(
                    """SELECT usage_date, COALESCE(SUM(background_seconds), 0) AS val
                       FROM content_usage_daily WHERE usage_date BETWEEN ? AND ?
                         AND (kind='media_playback' OR (kind='video_playback' AND category='音乐'))
                       GROUP BY usage_date ORDER BY usage_date""",
                    (s.isoformat(), e.isoformat())).fetchall()
            date_map = {str(r["usage_date"]): float(r["val"] or 0) for r in rows}
            result = []
            current = s
            while current <= e:
                result.append((day_names[current.weekday()], date_map.get(current.isoformat(), 0.0)))
                current += timedelta(days=1)
            return result

        return {
            "this_week": _daily(this_s, this_e),
            "last_week": _daily(last_s, last_e),
        }

    def daily_process_rows(self, target_date: date | None = None, limit: int = 100) -> list[sqlite3.Row]:
        usage_date = (target_date or date.today()).isoformat()
        return self.conn.execute(
            """
            SELECT usage_date, exe_name, exe_path, foreground_seconds, running_seconds,
                   MAX(running_seconds - foreground_seconds, 0) AS background_seconds,
                   last_seen
            FROM usage_daily
            WHERE usage_date = ?
            ORDER BY foreground_seconds DESC, running_seconds DESC
            LIMIT ?
            """,
            (usage_date, limit),
        ).fetchall()

    def process_rows_range(self, start_date: date, end_date: date, limit: int = 100) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT exe_name, exe_path,
                   COALESCE(SUM(foreground_seconds), 0) AS foreground_seconds,
                   COALESCE(SUM(running_seconds), 0) AS running_seconds,
                   MAX(last_seen) AS last_seen
            FROM usage_daily
            WHERE usage_date BETWEEN ? AND ?
            GROUP BY exe_path
            ORDER BY foreground_seconds DESC, running_seconds DESC
            LIMIT ?
            """,
            (start_date.isoformat(), end_date.isoformat(), limit),
        ).fetchall()

    def top_content_for_path(self, path: str, target_date: date | None = None, limit: int = 3) -> list[sqlite3.Row]:
        return self.top_content_for_paths([path], target_date=target_date, limit_per_path=limit).get(path, [])

    def top_content_for_paths(
        self,
        paths: Iterable[str],
        target_date: date | None = None,
        limit_per_path: int = 3,
    ) -> dict[str, list[sqlite3.Row]]:
        clean = sorted({path for path in paths if path})
        if not clean:
            return {}
        usage_date = (target_date or date.today()).isoformat()
        requested_by_lower = {path.lower(): path for path in clean}
        lookup_paths = sorted(requested_by_lower)
        placeholders = ",".join("?" for _ in lookup_paths)
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM content_usage_daily
            WHERE usage_date = ? AND exe_path COLLATE NOCASE IN ({placeholders})
            ORDER BY exe_path COLLATE NOCASE, attention_seconds DESC, background_seconds DESC
            """,
            [usage_date, *lookup_paths],
        ).fetchall()
        grouped: dict[str, list[sqlite3.Row]] = {path: [] for path in clean}
        for row in rows:
            path = requested_by_lower.get(str(row["exe_path"]).lower(), str(row["exe_path"]))
            bucket = grouped.setdefault(path, [])
            if len(bucket) < limit_per_path:
                bucket.append(row)
        return grouped

    def top_content(
        self,
        target_date: date | None = None,
        kind: str | None = None,
        limit: int = 10,
    ) -> list[sqlite3.Row]:
        usage_date = (target_date or date.today()).isoformat()
        if kind:
            return self.conn.execute(
                """
                SELECT *
                FROM content_usage_daily
                WHERE usage_date = ? AND kind = ?
                ORDER BY attention_seconds DESC, background_seconds DESC
                LIMIT ?
                """,
                (usage_date, kind, limit),
            ).fetchall()
        return self.conn.execute(
            """
            SELECT *
            FROM content_usage_daily
            WHERE usage_date = ?
            ORDER BY attention_seconds DESC, background_seconds DESC
            LIMIT ?
            """,
            (usage_date, limit),
        ).fetchall()

    def content_rows(
        self,
        target_date: date | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[sqlite3.Row]:
        usage_date = (target_date or date.today()).isoformat()
        order = """
            CASE WHEN kind = 'media_playback'
                THEN background_seconds
                ELSE attention_seconds
            END DESC,
            attention_seconds DESC,
            background_seconds DESC
        """
        if kind:
            return self.conn.execute(
                f"""
                SELECT *
                FROM content_usage_daily
                WHERE usage_date = ? AND kind = ?
                ORDER BY {order}
                LIMIT ?
                """,
                (usage_date, kind, limit),
            ).fetchall()
        return self.conn.execute(
            f"""
            SELECT *
            FROM content_usage_daily
            WHERE usage_date = ?
            ORDER BY {order}
            LIMIT ?
            """,
            (usage_date, limit),
        ).fetchall()

    def content_rows_range(
        self,
        start_date: date,
        end_date: date,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[sqlite3.Row]:
        order = """
            CASE WHEN kind = 'media_playback'
                THEN COALESCE(SUM(background_seconds), 0)
                ELSE COALESCE(SUM(attention_seconds), 0)
            END DESC,
            COALESCE(SUM(attention_seconds), 0) DESC,
            COALESCE(SUM(background_seconds), 0) DESC
        """
        params: list[object] = [start_date.isoformat(), end_date.isoformat()]
        filter_kind = ""
        if kind:
            filter_kind = "AND kind = ?"
            params.append(kind)
        params.append(limit)
        return self.conn.execute(
            f"""
            SELECT kind, exe_name, exe_path, content_title, content_url, content_domain, category, learning_topic,
                   COALESCE(SUM(attention_seconds), 0) AS attention_seconds,
                   COALESCE(SUM(background_seconds), 0) AS background_seconds,
                   MAX(last_seen) AS last_seen
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ? {filter_kind}
            GROUP BY kind, exe_path, content_key
            ORDER BY {order}
            LIMIT ?
            """,
            params,
        ).fetchall()

    def music_playback_rows_range(self, start_date: date, end_date: date, limit: int = 200) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT kind, exe_name, exe_path, content_title, content_url, content_domain, category, learning_topic,
                   COALESCE(SUM(attention_seconds), 0) AS attention_seconds,
                   COALESCE(SUM(background_seconds), 0) AS background_seconds,
                   MAX(last_seen) AS last_seen
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ?
              AND (kind = 'media_playback' OR (kind = 'video_playback' AND category = '音乐'))
            GROUP BY kind, exe_path, content_key
            ORDER BY COALESCE(SUM(background_seconds), 0) DESC, MAX(last_seen) DESC
            LIMIT ?
            """,
            (start_date.isoformat(), end_date.isoformat(), limit),
        ).fetchall()

    def music_analysis_range(self, start_date: date, end_date: date, limit: int = 300) -> list[dict[str, object]]:
        rows = self.music_playback_rows_range(start_date, end_date, limit=max(limit * 4, 500))
        total_seconds = self.media_total_range(start_date, end_date)
        grouped: dict[tuple[str, str], dict[str, object]] = {}
        for row in rows:
            seconds = float(row["background_seconds"] or 0)
            if seconds <= 0:
                continue
            source = str(row["exe_name"] or "")
            domain = str(row["content_domain"] or "")
            raw_title = str(row["content_title"] or "")
            title, artist, label = parse_music_identity(raw_title, source=source, domain=domain)
            song = title or label or raw_title or "未知歌曲"
            singer = artist or "未知歌手"
            key = (song.casefold(), singer.casefold())
            item = grouped.setdefault(
                key,
                {
                    "song": song,
                    "artist": singer,
                    "seconds": 0.0,
                    "sources": set(),
                    "domains": set(),
                    "raw_titles": set(),
                    "kinds": set(),
                    "last_seen": "",
                },
            )
            item["seconds"] = float(item["seconds"]) + seconds
            if source:
                item["sources"].add(source)  # type: ignore[union-attr]
            if domain:
                item["domains"].add(domain)  # type: ignore[union-attr]
            if raw_title:
                item["raw_titles"].add(raw_title)  # type: ignore[union-attr]
            item["kinds"].add(str(row["kind"] or ""))  # type: ignore[union-attr]
            item["last_seen"] = max(str(item["last_seen"]), str(row["last_seen"] or ""))

        result: list[dict[str, object]] = []
        for item in grouped.values():
            seconds = float(item["seconds"])
            percent = seconds / total_seconds * 100.0 if total_seconds > 0 else 0.0
            result.append(
                {
                    "song": str(item["song"]),
                    "artist": str(item["artist"]),
                    "seconds": seconds,
                    "percent": percent,
                    "sources": sorted(str(value) for value in item["sources"]),  # type: ignore[union-attr]
                    "domains": sorted(str(value) for value in item["domains"]),  # type: ignore[union-attr]
                    "raw_titles": sorted(str(value) for value in item["raw_titles"]),  # type: ignore[union-attr]
                    "kinds": sorted(str(value) for value in item["kinds"]),  # type: ignore[union-attr]
                    "last_seen": str(item["last_seen"]),
                }
            )
        return sorted(result, key=lambda value: float(value["seconds"]), reverse=True)[:limit]

    def artist_summary_range(self, start_date: date, end_date: date, limit: int = 100) -> list[dict[str, object]]:
        rows = self.music_playback_rows_range(start_date, end_date, limit=max(limit * 4, 500))
        grouped: dict[str, dict[str, object]] = {}
        for row in rows:
            seconds = float(row["background_seconds"] or 0)
            if seconds <= 0:
                continue
            source = str(row["exe_name"] or "")
            domain = str(row["content_domain"] or "")
            raw_title = str(row["content_title"] or "")
            title, artist, label = parse_music_identity(raw_title, source=source, domain=domain)
            singer = artist or "未知歌手"
            song = title or label or raw_title or "未知歌曲"
            item = grouped.setdefault(singer, {
                "artist": singer,
                "seconds": 0.0,
                "song_count": 0,
                "songs": set(),
                "sources": set(),
                "domains": set(),
                "last_seen": "",
            })
            item["seconds"] = float(item["seconds"]) + seconds
            item["songs"].add(song)  # type: ignore[union-attr]
            item["song_count"] = len(item["songs"])  # type: ignore[union-attr]
            if source:
                item["sources"].add(source)  # type: ignore[union-attr]
            if domain:
                item["domains"].add(domain)  # type: ignore[union-attr]
            item["last_seen"] = max(str(item.get("last_seen", "")), str(row["last_seen"] or ""))
        result = []
        total = self.media_total_range(start_date, end_date)
        for singer_data in grouped.values():
            secs = float(singer_data["seconds"])
            result.append({
                "artist": str(singer_data["artist"]),
                "seconds": secs,
                "song_count": int(singer_data["song_count"]),
                "top_songs": ", ".join(sorted(singer_data["songs"], key=str)[:5]),  # type: ignore[union-attr]
                "sources": ", ".join(sorted(singer_data["sources"], key=str)),  # type: ignore[union-attr]
                "percent": round(secs / total * 100, 1) if total > 0 else 0.0,
                "last_seen": str(singer_data["last_seen"]),
            })
        return sorted(result, key=lambda x: float(x["seconds"]), reverse=True)[:limit]

    def learning_total_range(self, start_date: date, end_date: date) -> float:
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(attention_seconds + background_seconds), 0) AS total
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ?
              AND (category = '学习' OR learning_topic != '')
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchone()
        return float(row["total"] or 0)

    def learning_topic_summary_range(self, start_date: date, end_date: date, limit: int = 200) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT
                CASE WHEN learning_topic != '' THEN learning_topic ELSE '综合学习' END AS learning_topic,
                COALESCE(SUM(attention_seconds), 0) AS attention_seconds,
                COALESCE(SUM(background_seconds), 0) AS background_seconds,
                COALESCE(SUM(attention_seconds + background_seconds), 0) AS total_seconds,
                COUNT(*) AS item_count,
                MAX(last_seen) AS last_seen
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ?
              AND (category = '学习' OR learning_topic != '')
            GROUP BY CASE WHEN learning_topic != '' THEN learning_topic ELSE '综合学习' END
            ORDER BY total_seconds DESC, last_seen DESC
            LIMIT ?
            """,
            (start_date.isoformat(), end_date.isoformat(), limit),
        ).fetchall()

    def learning_detail_rows_range(self, start_date: date, end_date: date, limit: int = 300) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT kind, exe_name, exe_path, content_title, content_url, content_domain, category, learning_topic,
                   COALESCE(SUM(attention_seconds), 0) AS attention_seconds,
                   COALESCE(SUM(background_seconds), 0) AS background_seconds,
                   COALESCE(SUM(attention_seconds + background_seconds), 0) AS total_seconds,
                   MAX(last_seen) AS last_seen
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ?
              AND (category = '学习' OR learning_topic != '')
            GROUP BY kind, exe_path, content_key
            ORDER BY total_seconds DESC, last_seen DESC
            LIMIT ?
            """,
            (start_date.isoformat(), end_date.isoformat(), limit),
        ).fetchall()

    def domain_summary_range(self, start_date: date, end_date: date, limit: int = 100) -> list[sqlite3.Row]:
        """Aggregate web browsing time by domain (or fallback to exe_name if no domain)."""
        return self.conn.execute(
            """
            SELECT CASE WHEN content_domain != '' THEN content_domain ELSE '（无域名 - 需安装浏览器扩展）' || '|' || exe_name END AS content_domain,
                   COALESCE(SUM(attention_seconds), 0) AS attention_seconds,
                   COUNT(DISTINCT content_key) AS page_count,
                   GROUP_CONCAT(DISTINCT content_title) AS top_titles,
                   MAX(last_seen) AS last_seen
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ?
              AND kind = 'web_page'
            GROUP BY CASE WHEN content_domain != '' THEN content_domain ELSE '（无域名 - 需安装浏览器扩展）' || '|' || exe_name END
            ORDER BY attention_seconds DESC
            LIMIT ?
            """,
            (start_date.isoformat(), end_date.isoformat(), limit),
        ).fetchall()

    def video_domain_summary_range(self, start_date: date, end_date: date, limit: int = 100) -> list[sqlite3.Row]:
        """Aggregate video playback by domain (or fallback to exe_name if no domain)."""
        return self.conn.execute(
            """
            SELECT CASE WHEN content_domain != '' THEN content_domain ELSE '（无域名 - 需安装浏览器扩展）' || '|' || exe_name END AS content_domain,
                   COALESCE(SUM(background_seconds), 0) AS total_seconds,
                   COUNT(DISTINCT content_key) AS video_count,
                   GROUP_CONCAT(DISTINCT content_title) AS top_titles,
                   category,
                   MAX(last_seen) AS last_seen
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ?
              AND kind = 'video_playback'
            GROUP BY CASE WHEN content_domain != '' THEN content_domain ELSE '（无域名 - 需安装浏览器扩展）' || '|' || exe_name END
            ORDER BY total_seconds DESC
            LIMIT ?
            """,
            (start_date.isoformat(), end_date.isoformat(), limit),
        ).fetchall()

    def hourly_activity_range(self, start_date: date, end_date: date) -> list[tuple[int, float, float, float, float]]:
        rows = self.conn.execute(
            """
            SELECT start_time, end_time, kind, category, learning_topic, seconds
            FROM timeline_events
            WHERE event_date BETWEEN ? AND ?
              AND kind != 'idle'
              AND seconds > 0
            ORDER BY start_time
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
        buckets = [[0.0, 0.0, 0.0, 0.0] for _ in range(24)]
        for row in rows:
            try:
                start = datetime.fromisoformat(str(row["start_time"]))
                end = datetime.fromisoformat(str(row["end_time"]))
                seconds = float(row["seconds"] or 0)
            except Exception:
                continue
            if seconds <= 0:
                continue
            if end <= start:
                end = start + timedelta(seconds=seconds)
            actual_seconds = max(0.001, (end - start).total_seconds())
            scale = seconds / actual_seconds
            cursor = start
            kind = str(row["kind"] or "")
            category = str(row["category"] or "")
            learning_topic = str(row["learning_topic"] or "")
            is_learning = category == "学习" or bool(learning_topic)
            while cursor < end:
                next_hour = (cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
                segment_end = min(end, next_hour)
                segment_seconds = max(0.0, (segment_end - cursor).total_seconds()) * scale
                hour = max(0, min(23, cursor.hour))
                if kind == "video_playback":
                    buckets[hour][1] += segment_seconds
                elif kind == "media_playback":
                    buckets[hour][2] += segment_seconds
                else:
                    buckets[hour][0] += segment_seconds
                if is_learning:
                    buckets[hour][3] += segment_seconds
                cursor = segment_end
        return [(hour, values[0], values[1], values[2], values[3]) for hour, values in enumerate(buckets)]

    def category_summary_range(self, start_date: date, end_date: date) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT category,
                   COALESCE(SUM(attention_seconds), 0) AS attention_seconds,
                   COALESCE(SUM(background_seconds), 0) AS background_seconds,
                   COALESCE(SUM(attention_seconds + background_seconds), 0) AS total_seconds,
                   COUNT(DISTINCT kind || ':' || exe_path || ':' || content_key) AS item_count,
                   GROUP_CONCAT(DISTINCT kind) AS kinds,
                   MAX(last_seen) AS last_seen
            FROM content_usage_daily
            WHERE usage_date BETWEEN ? AND ?
            GROUP BY category
            ORDER BY total_seconds DESC, attention_seconds DESC, background_seconds DESC
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()

    def timeline_rows_range(self, start_date: date, end_date: date, limit: int = 300) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT *
            FROM timeline_events
            WHERE event_date BETWEEN ? AND ?
            ORDER BY start_time DESC
            LIMIT ?
            """,
            (start_date.isoformat(), end_date.isoformat(), limit),
        ).fetchall()

    def goal_rows(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM goals WHERE enabled = 1 ORDER BY name"
        ).fetchall()

    def goal_progress_range(self, start_date: date, end_date: date) -> list[dict[str, object]]:
        result = []
        for goal in self.goal_rows():
            metric = str(goal["metric"])
            pattern = str(goal["pattern"])
            value = 0.0
            if metric == "category":
                row = self.conn.execute(
                    """
                    SELECT COALESCE(SUM(attention_seconds + background_seconds), 0) AS total
                    FROM content_usage_daily
                    WHERE usage_date BETWEEN ? AND ? AND category = ?
                    """,
                    (start_date.isoformat(), end_date.isoformat(), pattern),
                ).fetchone()
                value = float(row["total"] or 0)
            elif metric == "domain":
                row = self.conn.execute(
                    """
                    SELECT COALESCE(SUM(attention_seconds), 0) AS total
                    FROM content_usage_daily
                    WHERE usage_date BETWEEN ? AND ? AND content_domain LIKE ?
                    """,
                    (start_date.isoformat(), end_date.isoformat(), f"%{pattern}%"),
                ).fetchone()
                value = float(row["total"] or 0)
            elif metric == "app":
                row = self.conn.execute(
                    """
                    SELECT COALESCE(SUM(foreground_seconds), 0) AS total
                    FROM usage_daily
                    WHERE usage_date BETWEEN ? AND ? AND lower(exe_name) LIKE ?
                    """,
                    (start_date.isoformat(), end_date.isoformat(), f"%{pattern.lower()}%"),
                ).fetchone()
                value = float(row["total"] or 0)
            elif metric == "learning_topic":
                if pattern:
                    row = self.conn.execute(
                        """
                        SELECT COALESCE(SUM(attention_seconds + background_seconds), 0) AS total
                        FROM content_usage_daily
                        WHERE usage_date BETWEEN ? AND ? AND learning_topic = ?
                        """,
                        (start_date.isoformat(), end_date.isoformat(), pattern),
                    ).fetchone()
                else:
                    row = self.conn.execute(
                        """
                        SELECT COALESCE(SUM(attention_seconds + background_seconds), 0) AS total
                        FROM content_usage_daily
                        WHERE usage_date BETWEEN ? AND ?
                          AND (category = '学习' OR learning_topic != '')
                        """,
                        (start_date.isoformat(), end_date.isoformat()),
                    ).fetchone()
                value = float(row["total"] or 0)
            target = float(goal["target_seconds"] or 0)
            direction = str(goal["direction"])
            ok = value >= target if direction == "min" else value <= target
            result.append({"goal": goal, "value": value, "target": target, "ok": ok})
        return result

    def goal_rows_all(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM goals ORDER BY name").fetchall()

    def upsert_goal(self, name: str, metric: str, pattern: str, target_seconds: float,
                    direction: str, enabled: int) -> None:
        self.conn.execute(
            """INSERT INTO goals (name, metric, pattern, target_seconds, direction, enabled)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   metric=excluded.metric, pattern=excluded.pattern,
                   target_seconds=excluded.target_seconds, direction=excluded.direction,
                   enabled=excluded.enabled""",
            (name, metric, pattern, target_seconds, direction, enabled),
        )
        self.conn.commit()

    def delete_goal(self, name: str) -> None:
        self.conn.execute("DELETE FROM goals WHERE name = ?", (name,))
        self.conn.execute("DELETE FROM goal_streaks WHERE goal_name = ?", (name,))
        self.conn.commit()

    def goal_streak(self, goal_name: str) -> int:
        today = date.today()
        streak = 0
        check_date = today - timedelta(days=1)
        while True:
            row = self.conn.execute(
                "SELECT achieved FROM goal_streaks WHERE goal_name=? AND streak_date=?",
                (goal_name, check_date.isoformat()),
            ).fetchone()
            if not row or not int(row["achieved"]):
                break
            streak += 1
            check_date -= timedelta(days=1)
        return streak

    def save_goal_streak(self, goal_name: str, target_date: date, achieved: bool) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO goal_streaks (goal_name, streak_date, achieved)"
            " VALUES (?, ?, ?)",
            (goal_name, target_date.isoformat(), 1 if achieved else 0),
        )
        self.conn.commit()

    def compose_daily_summary(self, target_date: date | None = None) -> str | None:
        from .timefmt import format_duration

        d = target_date or (date.today() - timedelta(days=1))
        totals = self.day_overview_totals(d)
        foreground = totals["foreground"]
        learning = self.learning_total_range(d, d)
        top_proc = self.daily_process_rows(d, limit=1)
        top_app = str(top_proc[0]["exe_name"]) if top_proc else "未知"
        top_time = float(top_proc[0]["foreground_seconds"]) if top_proc else 0.0
        topics = self.learning_topic_summary_range(d, d, limit=3)
        topic_parts = []
        for t in topics:
            name = str(t["learning_topic"])
            secs = float(t["total_seconds"] or 0)
            if name and secs > 0:
                topic_parts.append(f"{name} {format_duration(secs)}")
        video_rows = self.content_rows_range(d, d, kind="video_playback", limit=100)
        video_count = len(video_rows)
        max_streak = 0
        for goal in self.goal_rows():
            s = self.goal_streak(str(goal["name"]))
            if s > max_streak:
                max_streak = s
        if foreground <= 0 and learning <= 0 and video_count == 0:
            return None
        parts = [f"昨天你学习了 {format_duration(learning)}"]
        if topic_parts:
            parts.append("（" + "、".join(topic_parts) + "）")
        parts.append(f"，前台最久的是 {top_app}（{format_duration(top_time)}）")
        if video_count:
            parts.append(f"，看了 {video_count} 个视频")
        if max_streak > 0:
            parts.append(f"，连续学习第 {max_streak} 天")
        return "".join(parts)

    def backup_database(self, output_path: Path) -> None:
        self.conn.commit()
        shutil.copy2(self.db_path, output_path)

    def optimize_database(self) -> None:
        self.conn.commit()
        self.conn.execute("PRAGMA optimize")
        self.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def database_size_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.db_path) + suffix)
            if path.exists():
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
        return total

    def database_stats(self) -> dict[str, int | str]:
        stats: dict[str, int | str] = {
            "path": str(self.db_path),
            "size_bytes": self.database_size_bytes(),
        }
        for table in ("usage_daily", "content_usage_daily", "timeline_events", "category_rules", "ignored_processes"):
            try:
                stats[f"{table}_rows"] = int(
                    self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
            except sqlite3.Error:
                stats[f"{table}_rows"] = 0
        try:
            row = self.conn.execute("SELECT MIN(event_date), MAX(event_date) FROM timeline_events").fetchone()
            stats["timeline_start"] = str(row[0] or "")
            stats["timeline_end"] = str(row[1] or "")
        except sqlite3.Error:
            stats["timeline_start"] = ""
            stats["timeline_end"] = ""
        return stats

    def cleanup_old_timeline_events(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = (date.today() - timedelta(days=retention_days)).isoformat()
        cursor = self.conn.execute(
            "DELETE FROM timeline_events WHERE event_date < ?",
            (cutoff,),
        )
        self.conn.commit()
        return int(cursor.rowcount or 0)

    def export_html_report(self, output_path: Path, start_date: date, end_date: date) -> None:
        foreground = self.foreground_total_range(start_date, end_date)
        media = self.media_total_range(start_date, end_date)
        categories = self.category_summary_range(start_date, end_date)
        learning_topics = self.learning_topic_summary_range(start_date, end_date, limit=30)
        learning_details = self.learning_detail_rows_range(start_date, end_date, limit=30)
        web = self.content_rows_range(start_date, end_date, kind="web_page", limit=20)
        video = self.content_rows_range(start_date, end_date, kind="video_playback", limit=20)
        music = self.music_playback_rows_range(start_date, end_date, limit=20)
        music_analysis = self.music_analysis_range(start_date, end_date, limit=30)
        goals = self.goal_progress_range(start_date, end_date)

        def rows(items: Iterable[Iterable[str]], raw_columns: set[int] | None = None) -> str:
            raw_columns = raw_columns or set()
            rendered = []
            for item in items:
                cells = []
                for index, cell in enumerate(item):
                    value = str(cell) if index in raw_columns else html.escape(str(cell))
                    cells.append(f"<td>{value}</td>")
                rendered.append("<tr>" + "".join(cells) + "</tr>")
            return "\n".join(rendered)

        max_category = max(
            [float(row["attention_seconds"] or 0) + float(row["background_seconds"] or 0) for row in categories] or [1.0]
        )
        category_rows = []
        for row in categories:
            total = float(row["attention_seconds"] or 0) + float(row["background_seconds"] or 0)
            width = int((total / max_category) * 100) if max_category else 0
            category_rows.append(
                [
                    row["category"],
                    f"{int(total // 3600)}h {int((total % 3600) // 60)}m",
                    f"<div class='bar'><span style='width:{width}%'></span></div>",
                ]
            )

        html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>UsageWidget 报告</title>
<style>
body {{ font-family: "Microsoft YaHei", Segoe UI, sans-serif; margin: 32px; color: #17202a; background: #f6f8fb; }}
h1, h2 {{ margin: 0 0 12px; }}
section {{ background: white; border: 1px solid #d9e1ea; border-radius: 10px; padding: 16px; margin: 16px 0; }}
.summary {{ display: flex; gap: 12px; }}
.metric {{ flex: 1; background: #eef6ff; border-radius: 8px; padding: 14px; }}
.metric b {{ display: block; font-size: 22px; margin-top: 6px; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; border-bottom: 1px solid #e5ebf2; padding: 8px; vertical-align: top; }}
th {{ background: #eef3f8; }}
.bar {{ width: 160px; height: 10px; background: #e5ebf2; border-radius: 999px; overflow: hidden; }}
.bar span {{ display: block; height: 100%; background: #1677d2; }}
</style>
</head>
<body>
<h1>UsageWidget 报告</h1>
<p>{start_date.isoformat()} 至 {end_date.isoformat()}</p>
<div class="summary">
  <div class="metric">前台注视<b>{int(foreground // 3600)}h {int((foreground % 3600) // 60)}m</b></div>
  <div class="metric">音乐播放<b>{int(media // 3600)}h {int((media % 3600) // 60)}m</b></div>
</div>
<section><h2>分类汇总</h2><table><tr><th>分类</th><th>时长</th><th>占比</th></tr>{rows(category_rows, {2})}</table></section>
<section><h2>学习主题汇总</h2><table><tr><th>学习主题</th><th>总分钟</th><th>网页注视分钟</th><th>视频/播放分钟</th><th>条目数</th></tr>{rows((r["learning_topic"], round(float(r["total_seconds"] or 0) / 60, 1), round(float(r["attention_seconds"] or 0) / 60, 1), round(float(r["background_seconds"] or 0) / 60, 1), r["item_count"]) for r in learning_topics)}</table></section>
<section><h2>学习内容明细</h2><table><tr><th>标题</th><th>主题</th><th>域名</th><th>类型</th><th>总分钟</th></tr>{rows((r["content_title"], r["learning_topic"] or "综合学习", r["content_domain"], r["kind"], round(float(r["total_seconds"] or 0) / 60, 1)) for r in learning_details)}</table></section>
<section><h2>Top 网站</h2><table><tr><th>标题</th><th>域名</th><th>分类</th><th>注视时长</th></tr>{rows((r["content_title"], r["content_domain"], r["category"], round(float(r["attention_seconds"] or 0) / 60, 1)) for r in web)}</table></section>
<section><h2>Top 视频</h2><table><tr><th>标题</th><th>域名</th><th>分类</th><th>播放分钟</th></tr>{rows((r["content_title"], r["content_domain"], r["category"], round(float(r["background_seconds"] or 0) / 60, 1)) for r in video)}</table></section>
<section><h2>Top 音乐原始记录</h2><table><tr><th>内容</th><th>来源</th><th>分类</th><th>播放分钟</th></tr>{rows((r["content_title"], r["exe_name"], r["category"], round(float(r["background_seconds"] or 0) / 60, 1)) for r in music)}</table></section>
<section><h2>音乐分析（按歌曲去重）</h2><table><tr><th>歌曲</th><th>歌手</th><th>播放分钟</th><th>占音乐时长</th><th>来源</th></tr>{rows((r["song"], r["artist"], round(float(r["seconds"]) / 60, 1), f'{float(r["percent"]):.1f}%', " / ".join(r["sources"])) for r in music_analysis)}</table></section>
<section><h2>目标</h2><table><tr><th>目标</th><th>当前分钟</th><th>目标分钟</th><th>状态</th></tr>{rows((g["goal"]["name"], round(float(g["value"]) / 60, 1), round(float(g["target"]) / 60, 1), "达标" if g["ok"] else "未达标") for g in goals)}</table></section>
</body>
</html>"""
        Path(output_path).write_text(html_text, encoding="utf-8")

    def delete_usage(self) -> None:
        self.conn.execute("DELETE FROM usage_daily")
        self.conn.execute("DELETE FROM content_usage_daily")
        self.conn.execute("DELETE FROM timeline_events")
        self.conn.commit()

    def export_csv(
        self,
        output_path: Path,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> None:
        query = """
            SELECT usage_date, exe_name, exe_path, foreground_seconds, running_seconds,
                   MAX(running_seconds - foreground_seconds, 0) AS background_seconds,
                   last_seen
            FROM usage_daily
        """
        params: list[object] = []
        filters = []
        if start_date:
            filters.append("usage_date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            filters.append("usage_date <= ?")
            params.append(end_date.isoformat())
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY usage_date DESC, foreground_seconds DESC"

        rows = self.conn.execute(query, params).fetchall()
        with Path(output_path).open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "date",
                    "exe_name",
                    "exe_path",
                    "foreground_seconds",
                    "running_seconds",
                    "background_seconds",
                    "last_seen",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["usage_date"],
                        row["exe_name"],
                        row["exe_path"],
                        round(float(row["foreground_seconds"] or 0), 2),
                        round(float(row["running_seconds"] or 0), 2),
                        round(float(row["background_seconds"] or 0), 2),
                        row["last_seen"],
                    ]
                )

    def export_content_csv(
        self,
        output_path: Path,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> None:
        query = """
            SELECT usage_date, kind, exe_name, exe_path, content_title, content_url, content_domain, category, learning_topic,
                   attention_seconds, background_seconds, last_seen
            FROM content_usage_daily
        """
        params: list[object] = []
        filters = []
        if start_date:
            filters.append("usage_date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            filters.append("usage_date <= ?")
            params.append(end_date.isoformat())
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY usage_date DESC, attention_seconds DESC, background_seconds DESC"

        rows = self.conn.execute(query, params).fetchall()
        with Path(output_path).open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "date",
                    "kind",
                    "exe_name",
                    "exe_path_or_source",
                    "content_title",
                    "content_url",
                    "content_domain",
                    "category",
                    "learning_topic",
                    "attention_seconds",
                    "background_seconds",
                    "last_seen",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row["usage_date"],
                        row["kind"],
                        row["exe_name"],
                        row["exe_path"],
                        row["content_title"],
                        row["content_url"],
                        row["content_domain"],
                        row["category"],
                        row["learning_topic"],
                        round(float(row["attention_seconds"] or 0), 2),
                        round(float(row["background_seconds"] or 0), 2),
                        row["last_seen"],
                    ]
                )

    def export_music_csv(
        self,
        output_path: Path,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> None:
        start = start_date or date.today()
        end = end_date or date.today()
        rows = self.music_analysis_range(start, end, limit=10000)
        with Path(output_path).open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "start_date",
                    "end_date",
                    "song",
                    "artist",
                    "play_seconds",
                    "play_minutes",
                    "percent_of_music",
                    "sources",
                    "domains",
                    "kinds",
                    "raw_titles",
                    "last_seen",
                ]
            )
            for row in rows:
                seconds = float(row["seconds"])
                writer.writerow(
                    [
                        start.isoformat(),
                        end.isoformat(),
                        row["song"],
                        row["artist"],
                        round(seconds, 2),
                        round(seconds / 60.0, 2),
                        round(float(row["percent"]), 2),
                        " / ".join(row["sources"]),  # type: ignore[arg-type]
                        " / ".join(row["domains"]),  # type: ignore[arg-type]
                        " / ".join(row["kinds"]),  # type: ignore[arg-type]
                        " | ".join(row["raw_titles"]),  # type: ignore[arg-type]
                        row["last_seen"],
                    ]
                )

    def export_learning_csv(
        self,
        output_path: Path,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> None:
        start = start_date or date.today()
        end = end_date or date.today()
        summary_rows = self.learning_topic_summary_range(start, end, limit=10000)
        detail_rows = self.learning_detail_rows_range(start, end, limit=10000)
        with Path(output_path).open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["section", "start_date", "end_date", "learning_topic", "total_seconds", "attention_seconds", "background_seconds", "item_count", "title", "domain", "kind", "url", "last_seen"])
            for row in summary_rows:
                writer.writerow(
                    [
                        "summary",
                        start.isoformat(),
                        end.isoformat(),
                        row["learning_topic"],
                        round(float(row["total_seconds"] or 0), 2),
                        round(float(row["attention_seconds"] or 0), 2),
                        round(float(row["background_seconds"] or 0), 2),
                        row["item_count"],
                        "",
                        "",
                        "",
                        "",
                        row["last_seen"],
                    ]
                )
            for row in detail_rows:
                topic = str(row["learning_topic"] or "综合学习")
                writer.writerow(
                    [
                        "detail",
                        start.isoformat(),
                        end.isoformat(),
                        topic,
                        round(float(row["total_seconds"] or 0), 2),
                        round(float(row["attention_seconds"] or 0), 2),
                        round(float(row["background_seconds"] or 0), 2),
                        "",
                        row["content_title"],
                        row["content_domain"],
                        row["kind"],
                        row["content_url"],
                        row["last_seen"],
                    ]
                )
