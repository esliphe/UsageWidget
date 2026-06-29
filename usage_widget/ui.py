from __future__ import annotations

import ctypes
import html
import sys
import threading
import time
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QEasingCurve, QEvent, QFileInfo, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QKeySequence, QMouseEvent, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QAbstractItemView,
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFileIconProvider,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .diagnostics import clear_log, log_event, log_path, read_recent_log
from .monitor import ProcessMonitor, RunningProcess
from .startup import is_startup_enabled, set_startup_enabled
from .storage import AppSettings, DEFAULT_CATEGORY_RULES, DEFAULT_IGNORED, Storage
from .timefmt import format_duration, format_duration_long, format_duration_smart
from .ui_palette import app_color, category_color
from .ui_helpers import (
    GOAL_METRIC_HELP,
    GOAL_METRIC_LABELS,
    cleanup_rule_title,
    data_definition_text,
    is_generic_content_domain,
    learning_feature_state,
    low_info_web_hint,
    online_feature_state,
    quality_summary_text,
    short_activity_hint,
    source_label,
    target_label,
)
from .ui_widgets import (
    DonutChartWidget,
    GroupedBarChartWidget,
    HeatmapWidget,
    HourlyActivityChart,
    ProcessRow,
    SortableTableItem,
    StatCard,
)


FULL_SIZE = (400, 520)
COLLAPSED_SIZE = (500, 118)
MAX_ICON_CACHE_SIZE = 200
_APP_ICON_CACHE: QIcon | None = None
UI_FONT_CANDIDATES = (
    "Noto Sans SC",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "SimSun",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Segoe UI",
    "Arial",
)
COMMON_CATEGORY_CHOICES = (
    "学习",
    "编程",
    "AI 工具",
    "系统软件",
    "聊天",
    "游戏",
    "视频",
    "音乐",
    "娱乐",
    "社交",
    "办公",
    "工具",
    "网站",
    "购物",
    "新闻",
    "其他",
)
TARGET_EXPLANATIONS = {
    "title": "标题",
    "domain": "域名",
    "app": "程序",
    "any": "全部",
}


def ui_font_family() -> str:
    try:
        available = {family.casefold(): family for family in QFontDatabase.families()}
        for family in UI_FONT_CANDIDATES:
            matched = available.get(family.casefold())
            if matched:
                return matched
    except Exception:
        pass
    try:
        fallback = QApplication.font().family()
        if fallback:
            return fallback
    except Exception:
        pass
    return "Microsoft YaHei UI"


def load_bundled_fonts() -> list[str]:
    loaded: list[str] = []
    roots = [Path(__file__).resolve().parent.parent / "fonts"]
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent if getattr(sys, "frozen", False) else ""))
    if bundle_root:
        roots.extend([bundle_root / "fonts", bundle_root / "assets" / "fonts"])
    for root in roots:
        if not root.exists():
            continue
        for pattern in ("*.ttf", "*.otf", "*.ttc"):
            for font_path in root.glob(pattern):
                try:
                    font_id = QFontDatabase.addApplicationFont(str(font_path))
                    if font_id >= 0:
                        loaded.extend(QFontDatabase.applicationFontFamilies(font_id))
                except Exception:
                    pass
    return loaded


def ui_font_status_text() -> str:
    try:
        families = QFontDatabase.families()
    except Exception as exc:
        return f"字体库不可读：{exc}"
    available = {family.casefold(): family for family in families}
    for family in UI_FONT_CANDIDATES:
        matched = available.get(family.casefold())
        if matched:
            return f"{matched}（可用字体 {len(families)} 个）"
    fallback = QApplication.font().family()
    return f"未找到常见中文字体，当前回退为 {fallback or 'Qt 默认字体'}（可用字体 {len(families)} 个）"


def ui_font_stack() -> str:
    return ", ".join(f'"{family}"' for family in UI_FONT_CANDIDATES)


def apply_app_font(app: QApplication) -> None:
    loaded = load_bundled_fonts()
    family = ui_font_family()
    app.setFont(QFont(family, 9))
    try:
        bundled = f"；已加载随包字体：{', '.join(loaded)}" if loaded else ""
        log_event(f"UI 字体：{ui_font_status_text()}{bundled}")
    except Exception:
        pass


def show_operation_error(parent: QWidget | None, title: str, exc: Exception) -> None:
    QMessageBox.critical(parent, title, f"操作失败：\n{exc}\n\n可在运行诊断中查看日志路径。")


def build_app_icon() -> QIcon:
    global _APP_ICON_CACHE
    if _APP_ICON_CACHE is not None:
        return _APP_ICON_CACHE
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(34, 132, 220))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(6, 6, 52, 52, 14, 14)
    painter.setBrush(QColor(255, 255, 255))
    painter.drawRoundedRect(18, 35, 7, 13, 3, 3)
    painter.drawRoundedRect(29, 24, 7, 24, 3, 3)
    painter.drawRoundedRect(40, 14, 7, 34, 3, 3)
    painter.end()
    _APP_ICON_CACHE = QIcon(pix)
    return _APP_ICON_CACHE


def is_dark_theme(settings: AppSettings) -> bool:
    if settings.theme == "dark":
        return True
    if settings.theme == "light":
        return False
    color = QApplication.palette().window().color()
    return color.lightness() < 128


def apply_windows_backdrop(widget: QWidget, dark: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        dark_value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(dark_value), ctypes.sizeof(dark_value))
        backdrop = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW: acrylic-like on Windows 11.
        dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
    except Exception:
        pass


class SettingsDialog(QDialog):
    settings_changed = Signal()
    data_changed = Signal()

    def __init__(self, storage: Storage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.storage = storage
        settings = self.storage.load_settings()
        self.setWindowTitle(f"UsageWidget 设置 · v{__version__}")
        self.setMinimumSize(760, 620)
        self.setWindowIcon(build_app_icon())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        self.settings_tabs = QTabWidget()
        root.addWidget(self.settings_tabs, 1)

        general = QFrame()
        general.setObjectName("settingsPanel")
        general_layout = QVBoxLayout(general)
        general_layout.setContentsMargins(12, 12, 12, 12)
        general_layout.setSpacing(10)

        general_layout.addWidget(self._section_label("启动与显示"))
        self.auto_start_box = QCheckBox("开机自启动")
        self.auto_start_box.setChecked(is_startup_enabled())
        general_layout.addWidget(self.auto_start_box)

        self.always_expanded_box = QCheckBox("始终展开（关闭后为悬停展开）")
        self.always_expanded_box.setChecked(settings.always_expanded)
        general_layout.addWidget(self.always_expanded_box)

        general_layout.addWidget(self._section_label("数据采集"))
        self.track_titles_box = QCheckBox("记录前台窗口/网页标题注视时长")
        self.track_titles_box.setChecked(settings.track_window_titles)
        general_layout.addWidget(self.track_titles_box)

        self.track_media_box = QCheckBox("记录后台媒体播放内容（如酷狗音乐）")
        self.track_media_box.setChecked(settings.track_media_sessions)
        general_layout.addWidget(self.track_media_box)

        self.track_urls_box = QCheckBox("接收浏览器扩展 URL / 域名")
        self.track_urls_box.setChecked(settings.track_browser_urls)
        general_layout.addWidget(self.track_urls_box)

        self.private_title_box = QCheckBox("隐私模式：网页仅显示域名，窗口标题脱敏")
        self.private_title_box.setChecked(settings.private_title_mode)
        general_layout.addWidget(self.private_title_box)

        general_layout.addWidget(self._section_label("联网功能"))
        self.online_music_lookup_box = QCheckBox("联网校验网页音乐标题（可选，隐私模式下自动禁用）")
        self.online_music_lookup_box.setChecked(settings.online_music_lookup)
        general_layout.addWidget(self.online_music_lookup_box)

        self.online_category_lookup_box = QCheckBox("联网增强分类：本地规则不确定，或 B 站等泛内容平台只得到宽泛分类时尝试细分")
        self.online_category_lookup_box.setChecked(settings.online_category_lookup)
        general_layout.addWidget(self.online_category_lookup_box)
        self.private_title_box.toggled.connect(self._sync_privacy_dependent_controls)

        self.daily_summary_box = QCheckBox("每日自动摘要（每天首次启动时显示昨日总结）")
        self.daily_summary_box.setChecked(settings.daily_summary)
        general_layout.addWidget(self.daily_summary_box)

        general_layout.addWidget(self._section_label("空闲豁免"))
        self.media_keeps_attention_box = QCheckBox("播放视频/音乐时不因键鼠空闲停止注视统计")
        self.media_keeps_attention_box.setChecked(settings.media_activity_keeps_attention)
        general_layout.addWidget(self.media_keeps_attention_box)

        self.handwriting_mode_box = QCheckBox("手写/笔记应用前台时不因键鼠空闲停止注视统计")
        self.handwriting_mode_box.setChecked(settings.handwriting_mode)
        general_layout.addWidget(self.handwriting_mode_box)

        handwriting_row = QHBoxLayout()
        handwriting_label = QLabel("手写应用")
        self.handwriting_input = QLineEdit()
        self.handwriting_input.setText(settings.handwriting_apps)
        self.handwriting_input.setPlaceholderText("例如: onenote.exe,whiteboard.exe")
        handwriting_row.addWidget(handwriting_label)
        handwriting_row.addWidget(self.handwriting_input, 1)
        general_layout.addLayout(handwriting_row)

        general_layout.addWidget(self._section_label("系统"))
        self.pause_box = QCheckBox("暂停记录")
        self.pause_box.setChecked(settings.pause_tracking)
        general_layout.addWidget(self.pause_box)

        time_settings_tip = QLabel("空闲判定、时间线保留和清理策略已移到“时间管理”页。")
        time_settings_tip.setObjectName("settingsHint")
        time_settings_tip.setWordWrap(True)
        general_layout.addWidget(time_settings_tip)

        theme_row = QHBoxLayout()
        theme_label = QLabel("主题")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        current_theme = settings.theme
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(current_theme)))
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_combo, 1)
        general_layout.addLayout(theme_row)

        self.window_opacity = self._slider_row(general_layout, "整体透明度", 40, 100, int(settings.window_opacity * 100))
        self.background_alpha = self._slider_row(general_layout, "背景透明度", 40, 245, settings.background_alpha)
        self.settings_tabs.addTab(general, "常规")

        time_panel = QFrame()
        time_panel.setObjectName("settingsPanel")
        time_layout = QVBoxLayout(time_panel)
        time_layout.setContentsMargins(12, 12, 12, 12)
        time_layout.setSpacing(10)
        time_layout.addWidget(self._section_label("记录节奏"))
        idle_note = QLabel("空闲阈值决定键鼠无输入多久后暂停前台注视累计。看视频、听音乐或使用手写应用时，可由常规页的豁免开关继续累计。")
        idle_note.setObjectName("settingsHint")
        idle_note.setWordWrap(True)
        time_layout.addWidget(idle_note)
        idle_row = QHBoxLayout()
        idle_label = QLabel("空闲判定")
        self.idle_preset_combo = QComboBox()
        self.idle_preset_combo.addItem("灵敏：1 分钟", 60)
        self.idle_preset_combo.addItem("均衡：3 分钟（推荐）", 180)
        self.idle_preset_combo.addItem("宽松：5 分钟", 300)
        self.idle_preset_combo.addItem("长时间阅读：10 分钟", 600)
        self.idle_preset_combo.addItem("自定义", -1)
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(30, 3600)
        self.idle_spin.setSingleStep(30)
        self.idle_spin.setSuffix(" 秒")
        self.idle_spin.setValue(settings.idle_threshold_seconds)
        idle_row.addWidget(idle_label)
        idle_row.addWidget(self.idle_preset_combo, 1)
        idle_row.addWidget(self.idle_spin)
        time_layout.addLayout(idle_row)

        time_layout.addWidget(self._section_label("历史管理"))
        retention_note = QLabel("时间线是最细的事件明细，保留越久越便于回看，但数据库会更大；汇总统计不依赖完整时间线。")
        retention_note.setObjectName("settingsHint")
        retention_note.setWordWrap(True)
        time_layout.addWidget(retention_note)
        retention_row = QHBoxLayout()
        retention_label = QLabel("时间线保留")
        self.retention_preset_combo = QComboBox()
        self.retention_preset_combo.addItem("30 天", 30)
        self.retention_preset_combo.addItem("90 天（推荐）", 90)
        self.retention_preset_combo.addItem("180 天", 180)
        self.retention_preset_combo.addItem("365 天", 365)
        self.retention_preset_combo.addItem("永久保留", 0)
        self.retention_preset_combo.addItem("自定义", -1)
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(0, 3650)
        self.retention_spin.setSingleStep(30)
        self.retention_spin.setSuffix(" 天")
        self.retention_spin.setSpecialValueText("永久")
        self.retention_spin.setValue(settings.timeline_retention_days)
        retention_row.addWidget(retention_label)
        retention_row.addWidget(self.retention_preset_combo, 1)
        retention_row.addWidget(self.retention_spin)
        time_layout.addLayout(retention_row)

        self.time_settings_summary = QLabel()
        self.time_settings_summary.setObjectName("timeSummary")
        self.time_settings_summary.setWordWrap(True)
        time_layout.addWidget(self.time_settings_summary)
        time_layout.addStretch(1)
        self._sync_time_preset_combos()
        self.idle_preset_combo.currentIndexChanged.connect(self._apply_idle_preset)
        self.retention_preset_combo.currentIndexChanged.connect(self._apply_retention_preset)
        self.idle_spin.valueChanged.connect(self._sync_idle_preset_from_spin)
        self.retention_spin.valueChanged.connect(self._sync_retention_preset_from_spin)
        self.idle_spin.valueChanged.connect(self._update_time_management_summary)
        self.retention_spin.valueChanged.connect(self._update_time_management_summary)
        self._update_time_management_summary()
        self.settings_tabs.addTab(time_panel, "时间管理")

        ignore_panel = QFrame()
        ignore_panel.setObjectName("settingsPanel")
        ignore_layout = QVBoxLayout(ignore_panel)
        ignore_layout.setContentsMargins(12, 12, 12, 12)
        ignore_layout.setSpacing(8)
        ignore_layout.addWidget(QLabel("忽略监控的进程"))
        self.ignore_list = QListWidget()
        for name in self.storage.ignored_processes():
            self.ignore_list.addItem(name)
        ignore_layout.addWidget(self.ignore_list, 1)

        add_row = QHBoxLayout()
        self.ignore_input = QLineEdit()
        self.ignore_input.setPlaceholderText("例如: antivirus.exe")
        add_button = QPushButton("添加")
        remove_button = QPushButton("删除选中")
        restore_button = QPushButton("恢复默认")
        add_button.clicked.connect(self.add_ignored_name)
        remove_button.clicked.connect(self.remove_selected_names)
        restore_button.clicked.connect(self.restore_default_ignored)
        add_row.addWidget(self.ignore_input, 1)
        add_row.addWidget(add_button)
        add_row.addWidget(remove_button)
        add_row.addWidget(restore_button)
        ignore_layout.addLayout(add_row)
        self.settings_tabs.addTab(ignore_panel, "忽略进程")

        category_panel = QFrame()
        category_panel.setObjectName("settingsPanel")
        category_layout = QVBoxLayout(category_panel)
        category_layout.setContentsMargins(12, 12, 12, 12)
        category_layout.setSpacing(8)
        category_intro = QLabel("网页/内容分类规则：优先用域名规则识别网站，用标题规则细分 B 站/YouTube 等内容，用程序规则识别本地应用。来源会区分本地、联网和用户纠正。")
        category_intro.setObjectName("settingsHint")
        category_intro.setWordWrap(True)
        category_layout.addWidget(category_intro)
        self.category_table = QTableWidget(0, 4)
        self.category_table.setHorizontalHeaderLabels(["关键词", "分类", "匹配位置", "来源"])
        self.category_table.verticalHeader().setVisible(False)
        self.category_table.horizontalHeader().setStretchLastSection(True)
        self.category_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row in self.storage.category_rules():
            self._append_category_rule(str(row["pattern"]), str(row["category"]), str(row["target"]), str(row["source"] or "user"))
        category_layout.addWidget(self.category_table, 1)

        category_row = QHBoxLayout()
        self.category_pattern_input = QLineEdit()
        self.category_pattern_input.setPlaceholderText("关键词，例如: 原神 / coursera.org / steam.exe")
        self.category_name_input = QLineEdit()
        self.category_name_input.setPlaceholderText("例如: 游戏 / 学习")
        self.category_target_combo = QComboBox()
        for label, value in (("标题", "title"), ("域名", "domain"), ("程序", "app"), ("全部", "any")):
            self.category_target_combo.addItem(label, value)
        add_category_button = QPushButton("添加规则")
        remove_category_button = QPushButton("删除选中")
        restore_category_button = QPushButton("恢复默认规则")
        add_category_button.clicked.connect(self.add_category_rule)
        remove_category_button.clicked.connect(self.remove_selected_category_rules)
        restore_category_button.clicked.connect(self.restore_default_category_rules)
        category_row.addWidget(self.category_pattern_input, 2)
        category_row.addWidget(self.category_name_input, 1)
        category_row.addWidget(self.category_target_combo)
        category_row.addWidget(add_category_button)
        category_row.addWidget(remove_category_button)
        category_row.addWidget(restore_category_button)
        category_layout.addLayout(category_row)
        self.category_rule_preview = QLabel("")
        self.category_rule_preview.setObjectName("settingsHint")
        self.category_rule_preview.setWordWrap(True)
        category_layout.addWidget(self.category_rule_preview)
        self.category_pattern_input.textChanged.connect(self._update_category_rule_preview)
        self.category_name_input.textChanged.connect(self._update_category_rule_preview)
        self.category_target_combo.currentIndexChanged.connect(self._update_category_rule_preview)
        category_help = QLabel("选择建议：网页域名固定时选“域名”；同一平台下按内容细分时选“标题”；本地软件选“程序”；不确定时选“全部”。")
        category_help.setObjectName("settingsHint")
        category_help.setWordWrap(True)
        category_layout.addWidget(category_help)
        self._update_category_rule_preview()
        self.settings_tabs.addTab(category_panel, "分类规则")

        goal_panel = QFrame()
        goal_panel.setObjectName("settingsPanel")
        goal_layout = QVBoxLayout(goal_panel)
        goal_layout.setContentsMargins(14, 14, 14, 14)
        goal_layout.setSpacing(12)

        goal_header = QHBoxLayout()
        goal_title_box = QVBoxLayout()
        goal_title_box.setSpacing(4)
        goal_title = QLabel("目标管理")
        goal_title.setObjectName("goalTitle")
        goal_desc = QLabel("设置学习、娱乐、视频、应用或网站的每日时长目标。选中一行可直接回填到下方编辑器。")
        goal_desc.setObjectName("settingsHint")
        goal_desc.setWordWrap(True)
        goal_desc.setMaximumHeight(42)
        goal_title_box.addWidget(goal_title)
        goal_title_box.addWidget(goal_desc)
        goal_header.addLayout(goal_title_box, 1)
        self.goal_total_card = self._make_goal_summary_card("目标数", "0", "全部")
        self.goal_enabled_card = self._make_goal_summary_card("启用", "0", "正在跟踪")
        self.goal_progress_card = self._make_goal_summary_card("今日达成", "0/0", "目标进度")
        self.goal_limit_card = self._make_goal_summary_card("限制", "0", "不超过")
        goal_header.addWidget(self.goal_total_card)
        goal_header.addWidget(self.goal_enabled_card)
        goal_header.addWidget(self.goal_progress_card)
        goal_header.addWidget(self.goal_limit_card)
        goal_layout.addLayout(goal_header)

        template_row = QHBoxLayout()
        template_row.setSpacing(8)
        template_label = QLabel("常用模板")
        template_label.setObjectName("settingsHint")
        template_row.addWidget(template_label)
        for label, name, metric, pattern, hours, direction in (
            ("学习至少 1 小时", "学习至少 1 小时", "learning_topic", "", 1.0, "min"),
            ("编程至少 2 小时", "编程至少 2 小时", "category", "编程", 2.0, "min"),
            ("娱乐不超过 1 小时", "娱乐不超过 1 小时", "category", "娱乐", 1.0, "max"),
            ("视频不超过 1 小时", "视频不超过 1 小时", "category", "视频", 1.0, "max"),
        ):
            template_btn = QPushButton(label)
            template_btn.setObjectName("subtleButton")
            template_btn.clicked.connect(
                lambda _checked=False, n=name, m=metric, p=pattern, h=hours, d=direction: self._apply_goal_template(n, m, p, h, d)
            )
            template_row.addWidget(template_btn)
        template_row.addStretch(1)
        goal_layout.addLayout(template_row)

        goal_tip_grid = QGridLayout()
        goal_tip_grid.setHorizontalSpacing(8)
        goal_tip_grid.setVerticalSpacing(8)
        for index, metric in enumerate(("category", "learning_topic", "domain", "app")):
            tip = QFrame()
            tip.setObjectName("goalTip")
            tip_layout = QVBoxLayout(tip)
            tip_layout.setContentsMargins(9, 7, 9, 7)
            tip_layout.setSpacing(3)
            tip_title = QLabel(f"{metric} · {GOAL_METRIC_LABELS[metric]}")
            tip_title.setObjectName("goalTipTitle")
            tip_text = QLabel(GOAL_METRIC_HELP[metric])
            tip_text.setObjectName("goalTipText")
            tip_text.setWordWrap(True)
            tip_layout.addWidget(tip_title)
            tip_layout.addWidget(tip_text)
            goal_tip_grid.addWidget(tip, index // 2, index % 2)
        goal_layout.addLayout(goal_tip_grid)

        self.goal_table = QTableWidget(0, 6)
        self.goal_table.setHorizontalHeaderLabels(["目标名称", "指标类型", "匹配模式", "目标小时", "方向", "启用"])
        self.goal_table.verticalHeader().setVisible(False)
        self.goal_table.horizontalHeader().setStretchLastSection(False)
        self.goal_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.goal_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.goal_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.goal_table.setAlternatingRowColors(True)
        self.goal_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.goal_table.verticalHeader().setDefaultSectionSize(32)
        self.goal_table.setShowGrid(False)
        self.goal_table.setMinimumHeight(210)
        self.goal_table.itemSelectionChanged.connect(self._load_selected_goal)
        goal_layout.addWidget(self.goal_table, 1)
        self.goal_empty_label = QLabel("暂无目标。可以先点上方模板，或在下方手动创建一个目标。")
        self.goal_empty_label.setObjectName("goalEmptyHint")
        self.goal_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        goal_layout.addWidget(self.goal_empty_label)

        goal_editor = QFrame()
        goal_editor.setObjectName("goalEditor")
        goal_form = QGridLayout(goal_editor)
        goal_form.setContentsMargins(12, 10, 12, 10)
        goal_form.setHorizontalSpacing(10)
        goal_form.setVerticalSpacing(8)
        self.goal_name_input = QLineEdit()
        self.goal_name_input.setPlaceholderText("目标名称")
        self.goal_metric_combo = QComboBox()
        for value in ("category", "learning_topic", "domain", "app"):
            self.goal_metric_combo.addItem(f"{GOAL_METRIC_LABELS[value]} · {value}", value)
        self.goal_pattern_input = QLineEdit()
        self.goal_pattern_input.setPlaceholderText("匹配模式，例如 学习 / Python / bilibili.com；学习主题留空=全部学习")
        self.goal_target_spin = QDoubleSpinBox()
        self.goal_target_spin.setRange(0.1, 168.0)
        self.goal_target_spin.setValue(1.0)
        self.goal_target_spin.setSuffix("h")
        self.goal_direction_combo = QComboBox()
        self.goal_direction_combo.addItems(["至少", "不超过"])
        self.goal_enabled_box = QCheckBox("启用")
        self.goal_enabled_box.setChecked(True)
        add_goal_btn = QPushButton("添加/更新")
        add_goal_btn.setObjectName("primaryButton")
        add_goal_btn.clicked.connect(self.add_or_update_goal)
        del_goal_btn = QPushButton("删除选中")
        del_goal_btn.clicked.connect(self.delete_selected_goal)
        clear_goal_btn = QPushButton("新建空白")
        clear_goal_btn.clicked.connect(self.clear_goal_form)
        self.goal_form_hint = QLabel("当前条件：分类包含“学习”时，每天至少 1.0 小时。")
        self.goal_form_hint.setObjectName("goalFormHint")
        self.goal_form_hint.setWordWrap(True)

        goal_form.addWidget(QLabel("名称"), 0, 0)
        goal_form.addWidget(self.goal_name_input, 0, 1, 1, 3)
        goal_form.addWidget(QLabel("指标"), 0, 4)
        goal_form.addWidget(self.goal_metric_combo, 0, 5)
        goal_form.addWidget(QLabel("匹配"), 1, 0)
        goal_form.addWidget(self.goal_pattern_input, 1, 1, 1, 3)
        goal_form.addWidget(QLabel("目标"), 1, 4)
        goal_form.addWidget(self.goal_target_spin, 1, 5)
        goal_form.addWidget(QLabel("方向"), 2, 0)
        goal_form.addWidget(self.goal_direction_combo, 2, 1)
        goal_form.addWidget(self.goal_enabled_box, 2, 2)
        goal_form.addWidget(self.goal_form_hint, 2, 3, 1, 3)
        goal_form.addWidget(clear_goal_btn, 3, 3)
        goal_form.addWidget(del_goal_btn, 3, 4)
        goal_form.addWidget(add_goal_btn, 3, 5)
        goal_form.setColumnStretch(1, 1)
        goal_form.setColumnStretch(3, 1)
        goal_layout.addWidget(goal_editor)
        self.goal_metric_combo.currentIndexChanged.connect(self._update_goal_form_hint)
        self.goal_pattern_input.textChanged.connect(self._update_goal_form_hint)
        self.goal_target_spin.valueChanged.connect(self._update_goal_form_hint)
        self.goal_direction_combo.currentIndexChanged.connect(self._update_goal_form_hint)
        self._populate_goal_table()
        self._update_goal_form_hint()
        self.settings_tabs.addTab(goal_panel, "学习目标")

        data_panel = QFrame()
        data_panel.setObjectName("settingsPanel")
        data_layout = QVBoxLayout(data_panel)
        data_layout.setContentsMargins(12, 12, 12, 12)
        data_layout.setSpacing(12)
        export_label = QLabel("导出")
        export_label.setObjectName("sectionLabel")
        export_grid = QGridLayout()
        export_grid.setHorizontalSpacing(8)
        export_grid.setVerticalSpacing(8)
        export_button = QPushButton("导出进程 CSV")
        export_content_button = QPushButton("导出内容 CSV")
        export_music_button = QPushButton("导出音乐分析 CSV")
        export_learning_button = QPushButton("导出学习分析 CSV")
        maintenance_label = QLabel("维护")
        maintenance_label.setObjectName("sectionLabel")
        maintenance_grid = QGridLayout()
        maintenance_grid.setHorizontalSpacing(8)
        maintenance_grid.setVerticalSpacing(8)
        backup_button = QPushButton("备份数据库")
        optimize_button = QPushButton("优化数据库")
        cleanup_timeline_button = QPushButton("清理旧时间线")
        self.repair_unknown_button = QPushButton("修复未识别内容")
        self.repair_unknown_button.setObjectName("primaryButton")
        self.repair_unknown_button.setToolTip("后台修复低置信内容：先用本地分类规则回填；若允许联网分类，会在时间预算内继续查询网页信息。")
        health = self.storage.recognition_health_range(date.today() - timedelta(days=6), date.today())
        repair_card = QFrame()
        repair_card.setObjectName("repairCard")
        repair_layout = QHBoxLayout(repair_card)
        repair_layout.setContentsMargins(12, 10, 12, 10)
        repair_layout.setSpacing(10)
        repair_text_box = QVBoxLayout()
        repair_text_box.setSpacing(3)
        repair_title = QLabel("识别数据修复")
        repair_title.setObjectName("repairTitle")
        repair_desc = QLabel(
            "低置信内容、仍归为“视频/其他”的网页会优先用本地规则重算；允许联网分类时会限量查询网页信息再回填。"
        )
        repair_desc.setObjectName("settingsHint")
        repair_desc.setWordWrap(True)
        self.repair_status_label = QLabel(
            f"近 7 天低置信 {health.get('low_confidence_rows', 0)} 条 · 泛视频 {health.get('broad_video_rows', 0)} 条 · 仅域名 {health.get('web_domain_only_rows', 0)} 条"
        )
        self.repair_status_label.setObjectName("repairStatus")
        repair_text_box.addWidget(repair_title)
        repair_text_box.addWidget(repair_desc)
        repair_text_box.addWidget(self.repair_status_label)
        repair_layout.addLayout(repair_text_box, 1)
        repair_layout.addWidget(self.repair_unknown_button, 0, Qt.AlignmentFlag.AlignVCenter)
        danger_label = QLabel("危险操作")
        danger_label.setObjectName("sectionLabel")
        clear_button = QPushButton("清除数据")
        export_button.clicked.connect(self.export_csv)
        export_content_button.clicked.connect(self.export_content_csv)
        export_music_button.clicked.connect(self.export_music_csv)
        export_learning_button.clicked.connect(self.export_learning_csv)
        backup_button.clicked.connect(self.backup_database)
        optimize_button.clicked.connect(self.optimize_database)
        cleanup_timeline_button.clicked.connect(self.cleanup_timeline)
        self.repair_unknown_button.clicked.connect(self.repair_unidentified_content)
        clear_button.clicked.connect(self.clear_usage_data)
        export_grid.addWidget(export_button, 0, 0)
        export_grid.addWidget(export_content_button, 0, 1)
        export_grid.addWidget(export_music_button, 0, 2)
        export_grid.addWidget(export_learning_button, 0, 3)
        maintenance_grid.addWidget(backup_button, 0, 0)
        maintenance_grid.addWidget(optimize_button, 0, 1)
        maintenance_grid.addWidget(cleanup_timeline_button, 0, 2)
        data_layout.addWidget(export_label)
        data_layout.addLayout(export_grid)
        data_layout.addWidget(maintenance_label)
        data_layout.addLayout(maintenance_grid)
        data_layout.addWidget(repair_card)
        data_layout.addWidget(danger_label)
        data_layout.addWidget(clear_button, 0, Qt.AlignmentFlag.AlignLeft)
        data_layout.addStretch(1)
        self.settings_tabs.addTab(data_panel, "数据")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        if buttons.button(QDialogButtonBox.StandardButton.Save):
            buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        if buttons.button(QDialogButtonBox.StandardButton.Cancel):
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.setStyleSheet(
            """
            QDialog { background: #f6f8fb; color: #17202a; font-family: {ui_font_stack()}; }
            QFrame#settingsPanel { background: white; border: 1px solid #d9e1ea; border-radius: 8px; }
            QLabel#sectionLabel { color: #607089; font-weight: 700; }
            QLabel#settingsHint { color: #64748b; font-size: 12px; }
            QLabel#timeSummary {
                background: #f8fafc;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
                color: #334155;
                padding: 9px 10px;
            }
            QLabel#goalTitle {
                color: #0f172a;
                font-size: 18px;
                font-weight: 800;
            }
            QFrame#goalSummaryCard {
                background: #f8fafc;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
                min-width: 98px;
            }
            QLabel#goalSummaryTitle { color: #64748b; font-size: 11px; }
            QLabel#goalSummaryValue { color: #0f172a; font-size: 20px; font-weight: 800; }
            QLabel#goalSummarySub { color: #64748b; font-size: 11px; }
            QFrame#goalTip {
                background: #fbfdff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            QLabel#goalTipTitle { color: #334155; font-weight: 750; font-size: 12px; }
            QLabel#goalTipText { color: #64748b; font-size: 11px; }
            QFrame#goalEditor {
                background: #f8fafc;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
            }
            QLabel#goalEmptyHint {
                color: #64748b;
                background: #f8fafc;
                border: 1px dashed #cbd5e1;
                border-radius: 8px;
                padding: 8px 10px;
            }
            QLabel#goalFormHint {
                color: #475569;
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QFrame#repairCard {
                background: #f8fbff;
                border: 1px solid #bfdbfe;
                border-radius: 8px;
            }
            QLabel#repairTitle {
                color: #0f172a;
                font-weight: 800;
            }
            QLabel#repairStatus {
                color: #1d4ed8;
                font-weight: 650;
            }
            QLineEdit, QListWidget, QComboBox, QTableWidget {
                border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px; background: white;
            }
            QPushButton { padding: 6px 10px; border: 1px solid #b9c6d4; border-radius: 6px; background: #ffffff; }
            QPushButton#primaryButton { background: #1677d2; color: white; border-color: #1677d2; font-weight: 700; }
            QPushButton#subtleButton { background: #f8fafc; color: #334155; border-color: #d9e1ea; }
            QPushButton:disabled, QCheckBox:disabled { color: #94a3b8; }
            QPushButton:hover { background: #eef6ff; }
            QPushButton#primaryButton:hover { background: #1268bb; }
            QPushButton#subtleButton:hover { background: #eef6ff; color: #0f172a; }
            """.replace("{ui_font_stack()}", ui_font_stack())
        )
        self._sync_privacy_dependent_controls()

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _sync_privacy_dependent_controls(self) -> None:
        privacy_enabled = self.private_title_box.isChecked()
        privacy_tip = "隐私模式下不会进行联网音乐校验或联网分类。关闭隐私模式后会恢复这里保存的开关状态。"
        music_tip = "联网校验网页标题是否为音乐；仅在关闭隐私模式时生效。"
        category_tip = "本地规则不确定，或 B 站等泛内容平台只得到宽泛分类时，联网尝试细分；隐私模式下自动禁用。"
        for widget, normal_tip in (
            (self.online_music_lookup_box, music_tip),
            (self.online_category_lookup_box, category_tip),
        ):
            widget.setEnabled(not privacy_enabled)
            widget.setToolTip(privacy_tip if privacy_enabled else normal_tip)

    def _slider_row(self, parent_layout: QVBoxLayout, label_text: str, minimum: int, maximum: int, value: int) -> QSlider:
        row = QHBoxLayout()
        label = QLabel(label_text)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        value_label = QLabel(str(value))
        value_label.setMinimumWidth(32)
        slider.valueChanged.connect(lambda number: value_label.setText(str(number)))
        row.addWidget(label)
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        parent_layout.addLayout(row)
        return slider

    def _set_combo_to_data(self, combo: QComboBox, data: int) -> None:
        index = combo.findData(data)
        if index < 0:
            index = combo.findData(-1)
        combo.blockSignals(True)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)

    def _sync_time_preset_combos(self) -> None:
        self._set_combo_to_data(self.idle_preset_combo, self.idle_spin.value())
        self._set_combo_to_data(self.retention_preset_combo, self.retention_spin.value())

    def _apply_idle_preset(self) -> None:
        value = int(self.idle_preset_combo.currentData())
        if value >= 0 and self.idle_spin.value() != value:
            self.idle_spin.setValue(value)
        self._update_time_management_summary()

    def _apply_retention_preset(self) -> None:
        value = int(self.retention_preset_combo.currentData())
        if value >= 0 and self.retention_spin.value() != value:
            self.retention_spin.setValue(value)
        self._update_time_management_summary()

    def _sync_idle_preset_from_spin(self, value: int) -> None:
        self._set_combo_to_data(self.idle_preset_combo, value)

    def _sync_retention_preset_from_spin(self, value: int) -> None:
        self._set_combo_to_data(self.retention_preset_combo, value)

    def _update_time_management_summary(self) -> None:
        idle_text = format_duration_long(float(self.idle_spin.value()))
        retention_days = self.retention_spin.value()
        retention_text = "永久保留" if retention_days <= 0 else f"保留最近 {retention_days} 天"
        cleanup_text = "清理旧时间线时不会删除任何事件" if retention_days <= 0 else f"清理旧时间线会删除早于 {retention_days} 天的细节事件"
        self.time_settings_summary.setText(
            f"当前策略：键鼠空闲超过 {idle_text} 后暂停前台注视累计；时间线{retention_text}。"
            f"{cleanup_text}，程序/网页/视频/音乐的日汇总仍会保留。"
        )

    def add_ignored_name(self) -> None:
        name = self.ignore_input.text().strip().lower()
        if not name:
            return
        existing = {self.ignore_list.item(i).text().lower() for i in range(self.ignore_list.count())}
        if name not in existing:
            self.ignore_list.addItem(name)
        self.ignore_input.clear()

    def remove_selected_names(self) -> None:
        for item in self.ignore_list.selectedItems():
            self.ignore_list.takeItem(self.ignore_list.row(item))

    def restore_default_ignored(self) -> None:
        self.ignore_list.clear()
        for name in sorted(DEFAULT_IGNORED):
            self.ignore_list.addItem(name)

    def _append_category_rule(self, pattern: str, category: str, target: str, source: str = "user") -> None:
        row = self.category_table.rowCount()
        self.category_table.insertRow(row)
        values = (pattern, category, target_label(target), source_label(source))
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col == 2:
                item.setData(Qt.ItemDataRole.UserRole, target)
            elif col == 3:
                item.setData(Qt.ItemDataRole.UserRole, source)
            self.category_table.setItem(row, col, item)

    def add_category_rule(self) -> None:
        pattern = self.category_pattern_input.text().strip().lower()
        category = self.category_name_input.text().strip() or "其他"
        target = str(self.category_target_combo.currentData() or "any")
        if not pattern:
            return
        existing_row = self._find_category_rule_row(pattern, target)
        if existing_row >= 0:
            answer = QMessageBox.question(
                self,
                "更新已有规则",
                f"已存在关键词“{pattern}”的规则。是否更新为：{target_label(target)} → {category}？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.category_table.item(existing_row, 1).setText(category)
            self.category_table.item(existing_row, 2).setText(target_label(target))
            self.category_table.item(existing_row, 2).setData(Qt.ItemDataRole.UserRole, target)
            self.category_table.item(existing_row, 3).setText(source_label("user"))
            self.category_table.item(existing_row, 3).setData(Qt.ItemDataRole.UserRole, "user")
            self.category_table.selectRow(existing_row)
        else:
            self._append_category_rule(pattern, category, target, "user")
        self.category_pattern_input.clear()
        self.category_name_input.clear()
        self._update_category_rule_preview()

    def _find_category_rule_row(self, pattern: str, target: str = "") -> int:
        pattern_l = pattern.strip().lower()
        target_l = target.strip().lower()
        for row in range(self.category_table.rowCount()):
            item = self.category_table.item(row, 0)
            target_item = self.category_table.item(row, 2)
            row_target = str(target_item.data(Qt.ItemDataRole.UserRole) or target_item.text()).strip().lower() if target_item else ""
            if item and item.text().strip().lower() == pattern_l and (not target_l or row_target == target_l):
                return row
        return -1

    def _update_category_rule_preview(self) -> None:
        pattern = self.category_pattern_input.text().strip().lower()
        category = self.category_name_input.text().strip() or "其他"
        target = str(self.category_target_combo.currentData() or "any")
        if not pattern:
            self.category_rule_preview.setText("先输入关键词。标题适合细分 B 站/YouTube 内容，域名适合普通网站，程序适合本地应用。")
            return
        duplicate = self._find_category_rule_row(pattern, target) >= 0
        prefix = "将更新已有规则：" if duplicate else "将添加规则："
        self.category_rule_preview.setText(
            f"{prefix}{target_label(target)}包含“{pattern}”时归为“{category}”。保存后会用于后续识别，也会回填可匹配的历史汇总。"
        )

    def remove_selected_category_rules(self) -> None:
        rows = sorted({index.row() for index in self.category_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.category_table.removeRow(row)

    def restore_default_category_rules(self) -> None:
        self.category_table.setRowCount(0)
        for pattern, category, target in DEFAULT_CATEGORY_RULES:
            self._append_category_rule(pattern, category, target, "default")

    def category_rule_rows(self) -> list[tuple[str, str, str, str]]:
        rules = []
        for row in range(self.category_table.rowCount()):
            values = []
            for col in range(4):
                item = self.category_table.item(row, col)
                if item and col in {2, 3}:
                    values.append(str(item.data(Qt.ItemDataRole.UserRole) or item.text()).strip())
                else:
                    values.append(item.text().strip() if item else "")
            pattern, category, target, source = values
            if pattern:
                rules.append((pattern, category or "其他", target or "any", source or "user"))
        return rules

    def ignored_names(self) -> list[str]:
        names = []
        for index in range(self.ignore_list.count()):
            item = self.ignore_list.item(index)
            if isinstance(item, QListWidgetItem):
                names.append(item.text())
        return names

    def _run_file_action(self, success_title: str, success_text: str, action) -> None:
        try:
            action()
        except Exception as exc:
            show_operation_error(self, success_title.replace("完成", "失败"), exc)
            return
        QMessageBox.information(self, success_title, success_text)

    def export_csv(self) -> None:
        default_name = f"usage-widget-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self._run_file_action("导出完成", f"已导出到：\n{path}", lambda: self.storage.export_csv(Path(path)))

    def export_content_csv(self) -> None:
        default_name = f"usage-widget-content-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出内容 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self._run_file_action("导出完成", f"已导出到：\n{path}", lambda: self.storage.export_content_csv(Path(path)))

    def export_music_csv(self) -> None:
        default_name = f"usage-widget-music-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出音乐分析 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self._run_file_action("导出完成", f"已导出到：\n{path}", lambda: self.storage.export_music_csv(Path(path)))

    def export_learning_csv(self) -> None:
        default_name = f"usage-widget-learning-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出学习分析 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self._run_file_action("导出完成", f"已导出到：\n{path}", lambda: self.storage.export_learning_csv(Path(path)))

    def clear_usage_data(self) -> None:
        answer = QMessageBox.warning(
            self,
            "清除数据",
            "这会删除所有已记录的使用时长，忽略列表和设置会保留。",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                self.storage.delete_usage()
            except Exception as exc:
                show_operation_error(self, "清除失败", exc)
                return
            self.data_changed.emit()

    def backup_database(self) -> None:
        default_name = f"usage-widget-db-{date.today().isoformat()}.sqlite"
        path, _ = QFileDialog.getSaveFileName(self, "备份数据库", default_name, "SQLite Database (*.sqlite *.db)")
        if not path:
            return
        self._run_file_action("备份完成", f"已备份到：\n{path}", lambda: self.storage.backup_database(Path(path)))

    def optimize_database(self) -> None:
        self._run_file_action("优化完成", "数据库索引统计和 WAL 检查点已更新。", self.storage.optimize_database)

    def cleanup_timeline(self) -> None:
        retention_days = self.retention_spin.value()
        if retention_days <= 0:
            QMessageBox.information(self, "未清理", "当前设置为永久保留时间线。")
            return
        try:
            removed = self.storage.cleanup_old_timeline_events(retention_days)
        except Exception as exc:
            show_operation_error(self, "清理失败", exc)
            return
        self.data_changed.emit()
        QMessageBox.information(self, "清理完成", f"已清理 {removed} 条旧时间线事件，保留最近 {retention_days} 天。")

    def repair_unidentified_content(self) -> None:
        running_thread = getattr(self, "_repair_thread", None)
        if running_thread is not None and running_thread.is_alive():
            QMessageBox.information(self, "正在修复", "未识别内容修复正在后台运行，请稍后查看结果。")
            return
        use_online = self.online_category_lookup_box.isChecked() and not self.private_title_box.isChecked()
        self._repair_result = None
        self._repair_error = None
        self.repair_unknown_button.setEnabled(False)
        self.repair_unknown_button.setText("修复中...")
        if hasattr(self, "repair_status_label"):
            mode_text = "本地规则 + 联网增强" if use_online else "本地规则"
            self.repair_status_label.setText(f"正在后台修复：{mode_text}。窗口可继续使用，不会阻塞。")

        db_path = self.storage.db_path

        def worker() -> None:
            worker_storage: Storage | None = None
            try:
                worker_storage = Storage(db_path)
                self._repair_result = worker_storage.repair_unidentified_content(
                    online=use_online,
                    limit=5000,
                    online_limit=420 if use_online else 0,
                    online_time_budget_seconds=110.0,
                )
            except Exception as exc:
                self._repair_error = exc
            finally:
                if worker_storage is not None:
                    worker_storage.close()

        self._repair_thread = threading.Thread(target=worker, name="UsageWidgetRepairUnknown", daemon=True)
        self._repair_thread.start()
        if not hasattr(self, "_repair_poll_timer"):
            self._repair_poll_timer = QTimer(self)
            self._repair_poll_timer.setInterval(350)
            self._repair_poll_timer.timeout.connect(self._poll_repair_unidentified_content)
        self._repair_poll_timer.start()

    def _poll_repair_unidentified_content(self) -> None:
        running_thread = getattr(self, "_repair_thread", None)
        if running_thread is not None and running_thread.is_alive():
            return
        if hasattr(self, "_repair_poll_timer"):
            self._repair_poll_timer.stop()
        self.repair_unknown_button.setEnabled(True)
        self.repair_unknown_button.setText("修复未识别内容")
        error = getattr(self, "_repair_error", None)
        if error is not None:
            if hasattr(self, "repair_status_label"):
                self.repair_status_label.setText("修复失败，可在运行诊断中查看最近日志。")
            show_operation_error(self, "修复失败", error)
            return
        stats = getattr(self, "_repair_result", None) or {}
        self.data_changed.emit()
        online_enabled = bool(int(stats.get("online_enabled", 0) or 0))
        if hasattr(self, "repair_status_label"):
            skip_hint = (
                f" · 候选 {stats.get('online_candidates', 0)} 条"
                f" · 跳过 {int(stats.get('online_skipped', 0) or 0) + int(stats.get('online_limit_skipped', 0) or 0)} 条"
            ) if online_enabled else " · 联网未启用"
            self.repair_status_label.setText(
                f"最近修复：检查 {stats.get('checked', 0)} 条 · 本地 {stats.get('local_updated', 0)} 条 · "
                f"联网 {stats.get('online_updated', 0)}/{stats.get('online_checked', 0)} 条 · 剩余 {stats.get('remaining', 0)} 条"
                f"{skip_hint}"
            )
        mode = "本地规则 + 联网增强" if online_enabled else "本地规则"
        skipped = int(stats.get("online_skipped", 0) or 0)
        limit_skipped = int(stats.get("online_limit_skipped", 0) or 0)
        duplicate_skipped = int(stats.get("online_duplicate_skipped", 0) or 0)
        no_query = int(stats.get("online_no_query", 0) or 0)
        disabled = int(stats.get("online_disabled", 0) or 0)
        skipped_text = ""
        if skipped or limit_skipped or duplicate_skipped or no_query or disabled:
            skipped_text = (
                "\n未联网原因："
                f"预算到期 {skipped} 条；本次上限 {limit_skipped} 条；"
                f"重复内容 {duplicate_skipped} 条；标题/域名不足 {no_query} 条；联网关闭 {disabled} 条。"
                "\n可再次点击继续修复剩余低置信内容。"
            )
        QMessageBox.information(
            self,
            "修复完成",
            f"模式：{mode}\n"
            f"检查内容：{stats.get('checked', 0)} 条\n"
            f"本地修复：{stats.get('local_updated', 0)} 条\n"
            f"联网候选：{stats.get('online_candidates', 0)} 条\n"
            f"联网检查：{stats.get('online_checked', 0)} 条\n"
            f"联网修复：{stats.get('online_updated', 0)} 条\n"
            f"剩余低置信：{stats.get('remaining', 0)} 条"
            f"{skipped_text}",
        )

    def save(self) -> None:
        self.storage.replace_ignored_processes(self.ignored_names())
        self.storage.replace_category_rules(self.category_rule_rows())
        set_startup_enabled(self.auto_start_box.isChecked())
        current = self.storage.load_settings()
        updated = replace(
            current,
            theme=str(self.theme_combo.currentData()),
            always_expanded=self.always_expanded_box.isChecked(),
            window_opacity=self.window_opacity.value() / 100.0,
            background_alpha=self.background_alpha.value(),
            auto_start=self.auto_start_box.isChecked(),
            track_window_titles=self.track_titles_box.isChecked(),
            track_media_sessions=self.track_media_box.isChecked(),
            track_browser_urls=self.track_urls_box.isChecked(),
            idle_threshold_seconds=self.idle_spin.value(),
            pause_tracking=self.pause_box.isChecked(),
            private_title_mode=self.private_title_box.isChecked(),
            online_music_lookup=self.online_music_lookup_box.isChecked(),
            online_category_lookup=self.online_category_lookup_box.isChecked(),
            media_activity_keeps_attention=self.media_keeps_attention_box.isChecked(),
            handwriting_mode=self.handwriting_mode_box.isChecked(),
            handwriting_apps=self.handwriting_input.text().strip(),
            timeline_retention_days=self.retention_spin.value(),
            daily_summary=self.daily_summary_box.isChecked(),
        )
        self.storage.save_settings(updated)
        self.settings_changed.emit()
        self.accept()

    def _make_goal_summary_card(self, title: str, value: str, sub: str) -> QFrame:
        card = QFrame()
        card.setObjectName("goalSummaryCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("goalSummaryTitle")
        value_label = QLabel(value)
        value_label.setObjectName("goalSummaryValue")
        sub_label = QLabel(sub)
        sub_label.setObjectName("goalSummarySub")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(sub_label)
        card.value_label = value_label  # type: ignore[attr-defined]
        card.sub_label = sub_label  # type: ignore[attr-defined]
        return card

    def _set_goal_summary_card(self, card: QFrame, value: object, sub: str) -> None:
        if hasattr(card, "value_label"):
            card.value_label.setText(str(value))  # type: ignore[attr-defined]
        if hasattr(card, "sub_label"):
            card.sub_label.setText(sub)  # type: ignore[attr-defined]

    def _goal_metric_label(self, metric: str) -> str:
        return GOAL_METRIC_LABELS.get(metric, metric or "分类")

    def _goal_metric_index(self, metric: str) -> int:
        index = self.goal_metric_combo.findData(metric)
        return index if index >= 0 else 0

    def _update_goal_summary(self) -> None:
        rows = self.storage.goal_rows_all()
        total = len(rows)
        enabled = sum(1 for row in rows if int(row["enabled"]))
        max_count = sum(1 for row in rows if str(row["direction"]) == "max")
        min_count = total - max_count
        progress = self.storage.goal_progress_range(date.today(), date.today())
        done = sum(1 for item in progress if bool(item.get("ok")))
        self._set_goal_summary_card(self.goal_total_card, total, f"{min_count} 个至少目标")
        self._set_goal_summary_card(self.goal_enabled_card, enabled, f"{total - enabled} 个暂停")
        self._set_goal_summary_card(self.goal_progress_card, f"{done}/{len(progress)}", "按今日数据计算")
        self._set_goal_summary_card(self.goal_limit_card, max_count, "控制娱乐/视频等上限")

    def _populate_goal_table(self) -> None:
        previous = self.goal_table.currentRow()
        self.goal_table.blockSignals(True)
        self.goal_table.setRowCount(0)
        for row_data in self.storage.goal_rows_all():
            self._add_goal_row(row_data)
        self.goal_table.blockSignals(False)
        if self.goal_table.rowCount() > 0:
            self.goal_table.selectRow(max(0, min(previous, self.goal_table.rowCount() - 1)))
        if hasattr(self, "goal_empty_label"):
            self.goal_empty_label.setVisible(self.goal_table.rowCount() == 0)
        self._update_goal_summary()

    def _add_goal_row(self, row_data) -> None:
        r = self.goal_table.rowCount()
        self.goal_table.insertRow(r)
        enabled = int(row_data["enabled"])
        name_item = QTableWidgetItem(str(row_data["name"]))
        metric = str(row_data["metric"])
        metric_item = QTableWidgetItem(f"{self._goal_metric_label(metric)} · {metric}")
        metric_item.setData(Qt.ItemDataRole.UserRole, metric)
        pattern = str(row_data["pattern"])
        pattern_item = QTableWidgetItem(pattern if pattern else "全部")
        hours = float(row_data["target_seconds"]) / 3600.0
        hour_item = QTableWidgetItem(f"{hours:.1f}")
        direction_text = "至少" if str(row_data["direction"]) == "min" else "不超过"
        direction_item = QTableWidgetItem(direction_text)
        enabled_item = QTableWidgetItem("是" if enabled else "否")
        for item in (name_item, metric_item, pattern_item, hour_item, direction_item, enabled_item):
            if not enabled:
                item.setForeground(QBrush(QColor("#94a3b8")))
        self.goal_table.setItem(r, 0, name_item)
        self.goal_table.setItem(r, 1, metric_item)
        self.goal_table.setItem(r, 2, pattern_item)
        self.goal_table.setItem(r, 3, hour_item)
        self.goal_table.setItem(r, 4, direction_item)
        self.goal_table.setItem(r, 5, enabled_item)

    def _load_selected_goal(self) -> None:
        row = self.goal_table.currentRow()
        if row < 0:
            return
        name_item = self.goal_table.item(row, 0)
        metric_item = self.goal_table.item(row, 1)
        pattern_item = self.goal_table.item(row, 2)
        hours_item = self.goal_table.item(row, 3)
        direction_item = self.goal_table.item(row, 4)
        enabled_item = self.goal_table.item(row, 5)
        self.goal_name_input.setText(name_item.text() if name_item else "")
        metric = str(metric_item.data(Qt.ItemDataRole.UserRole) if metric_item else "category")
        self.goal_metric_combo.setCurrentIndex(self._goal_metric_index(metric))
        pattern = pattern_item.text() if pattern_item else ""
        self.goal_pattern_input.setText("" if pattern == "全部" else pattern)
        try:
            self.goal_target_spin.setValue(float(hours_item.text()) if hours_item else 1.0)
        except ValueError:
            self.goal_target_spin.setValue(1.0)
        self.goal_direction_combo.setCurrentText(direction_item.text() if direction_item else "至少")
        self.goal_enabled_box.setChecked((enabled_item.text() if enabled_item else "是") == "是")
        self._update_goal_form_hint()

    def clear_goal_form(self) -> None:
        self.goal_table.clearSelection()
        self.goal_name_input.clear()
        self.goal_metric_combo.setCurrentIndex(self._goal_metric_index("category"))
        self.goal_pattern_input.clear()
        self.goal_target_spin.setValue(1.0)
        self.goal_direction_combo.setCurrentText("至少")
        self.goal_enabled_box.setChecked(True)
        self.goal_name_input.setFocus()
        self._update_goal_form_hint()

    def _apply_goal_template(self, name: str, metric: str, pattern: str, hours: float, direction: str) -> None:
        self.goal_name_input.setText(name)
        self.goal_metric_combo.setCurrentIndex(self._goal_metric_index(metric))
        self.goal_pattern_input.setText(pattern)
        self.goal_target_spin.setValue(hours)
        self.goal_direction_combo.setCurrentText("至少" if direction == "min" else "不超过")
        self.goal_enabled_box.setChecked(True)
        self._update_goal_form_hint()

    def _update_goal_form_hint(self) -> None:
        if not hasattr(self, "goal_form_hint"):
            return
        metric = str(self.goal_metric_combo.currentData() or "category")
        metric_label = self._goal_metric_label(metric)
        pattern = self.goal_pattern_input.text().strip()
        target = self.goal_target_spin.value()
        direction = str(self.goal_direction_combo.currentText())
        scope = f"{metric_label}包含“{pattern}”" if pattern else ("全部学习主题" if metric == "learning_topic" else f"全部{metric_label}")
        self.goal_form_hint.setText(f"当前条件：{scope}时，每天{direction} {target:.1f} 小时。")

    def _select_goal_by_name(self, name: str) -> None:
        for row in range(self.goal_table.rowCount()):
            item = self.goal_table.item(row, 0)
            if item and item.text() == name:
                self.goal_table.selectRow(row)
                return

    def add_or_update_goal(self) -> None:
        name = self.goal_name_input.text().strip()
        if not name:
            return
        metric = str(self.goal_metric_combo.currentData() or self.goal_metric_combo.currentText())
        pattern = self.goal_pattern_input.text().strip()
        target_hours = self.goal_target_spin.value()
        direction = "min" if str(self.goal_direction_combo.currentText()) == "至少" else "max"
        enabled = 1 if self.goal_enabled_box.isChecked() else 0
        self.storage.upsert_goal(name, metric, pattern, target_hours * 3600, direction, enabled)
        self._populate_goal_table()
        self._select_goal_by_name(name)
        self.data_changed.emit()

    def delete_selected_goal(self) -> None:
        rows = sorted({i.row() for i in self.goal_table.selectedIndexes()}, reverse=True)
        for r in rows:
            name = self.goal_table.item(r, 0).text()
            self.storage.delete_goal(name)
        self._populate_goal_table()
        self.data_changed.emit()


class DiagnosticsDialog(QDialog):
    def __init__(self, storage: Storage, monitor: ProcessMonitor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.monitor = monitor
        self.setWindowTitle(f"UsageWidget 诊断 · v{__version__}")
        self.setWindowIcon(build_app_icon())
        self.setMinimumSize(760, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("运行诊断")
        title.setObjectName("statsTitle")
        refresh_button = QPushButton("刷新")
        clear_button = QPushButton("清空日志")
        copy_button = QPushButton("复制日志路径")
        refresh_button.clicked.connect(self.refresh)
        clear_button.clicked.connect(self.clear_diagnostics_log)
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(str(log_path())))
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(copy_button)
        header.addWidget(clear_button)
        header.addWidget(refresh_button)
        root.addLayout(header)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["项目", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        root.addWidget(self.table, 1)

        root.addWidget(QLabel("最近诊断日志"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(600)
        root.addWidget(self.log_view, 1)

        self.setStyleSheet(
            """
            QDialog { background: #f6f8fb; color: #17202a; font-family: {ui_font_stack()}; }
            QLabel#statsTitle { font-size: 18px; font-weight: 700; }
            QTableWidget, QPlainTextEdit {
                background: white;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
                gridline-color: #e5ebf2;
            }
            QHeaderView::section {
                background: #eef3f8;
                border: none;
                border-right: 1px solid #d9e1ea;
                padding: 6px;
                font-weight: 650;
            }
            QPushButton { padding: 6px 10px; border: 1px solid #b9c6d4; border-radius: 6px; background: #ffffff; }
            QPushButton:hover { background: #eef6ff; }
            """.replace("{ui_font_stack()}", ui_font_stack())
        )
        self.refresh()

    def _format_size(self, value: int) -> str:
        size = float(value)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{value} B"

    def _set_metrics(self, rows: list[tuple[str, str]]) -> None:
        self.table.setRowCount(len(rows))
        for row_index, (name, value) in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(name))
            self.table.setItem(row_index, 1, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def refresh(self) -> None:
        latest_tab = self.monitor.browser_bridge.latest(max_age_seconds=3600)
        audible_tabs = self.monitor.browser_bridge.audible_tabs(max_age_seconds=3600)
        media_items = self.monitor.media_provider.current_items()
        settings = self.storage.load_settings()
        log_file = log_path()
        db_stats = self.storage.database_stats()
        latest_page_signal_count = self.monitor.browser_bridge.page_signal_count()
        health_7d = self.storage.recognition_health_range(date.today() - timedelta(days=6), date.today())
        rows = [
            ("数据库路径", str(self.storage.db_path)),
            ("数据库大小", self._format_size(self.storage.database_size_bytes())),
            ("UI 字体", ui_font_status_text()),
            ("进程日汇总行数", str(db_stats.get("usage_daily_rows", 0))),
            ("内容日汇总行数", str(db_stats.get("content_usage_daily_rows", 0))),
            ("时间线事件行数", str(db_stats.get("timeline_events_rows", 0))),
            ("识别健康度（近 7 天）", quality_summary_text(health_7d)),
            ("仅域名无标题网页（近 7 天）", str(health_7d.get("web_domain_only_rows", 0))),
            ("仍归为“视频”的播放（近 7 天）", str(health_7d.get("broad_video_rows", 0))),
            ("低置信内容（近 7 天）", str(health_7d.get("low_confidence_rows", 0))),
            ("时间线范围", f"{db_stats.get('timeline_start', '') or '无'} ~ {db_stats.get('timeline_end', '') or '无'}"),
            ("分类规则数", str(db_stats.get("category_rules_rows", 0))),
            ("诊断日志", str(log_file)),
            ("日志大小", self._format_size(log_file.stat().st_size) if log_file.exists() else "0 B"),
            ("当前进程数", str(len(self.monitor.current_processes))),
            ("前台程序", self.monitor.foreground_path or "未识别"),
            ("前台标题", self.monitor.foreground_title[:120] or "无"),
            ("空闲状态", f"{'空闲' if self.monitor.is_idle else '活动'}，{format_duration(self.monitor.idle_seconds)}"),
            ("记录状态", "已暂停" if self.monitor.is_paused else "记录中"),
            ("最近采样耗时", f"{self.monitor.last_sample_ms:.0f} ms"),
            ("最高采样耗时", f"{self.monitor.max_sample_ms:.0f} ms"),
            ("最近进程扫描", f"{self.monitor.last_process_scan_ms:.0f} ms"),
            ("最近数据库写入", f"{self.monitor.last_db_write_ms:.0f} ms"),
            ("慢采样次数", str(self.monitor.slow_sample_count)),
            ("浏览器扩展", "有活动标签页上报" if latest_tab else "最近无活动标签页上报"),
            ("最近网页", f"{latest_tab.domain} · {latest_tab.title[:80]}" if latest_tab else "无"),
            ("页面内容信号", f"{latest_page_signal_count} 条/小时"),
            ("最近网页媒体元素", self._browser_media_detail(latest_tab) if latest_tab else "无"),
            ("联网音乐校验", online_feature_state(settings.online_music_lookup, settings.private_title_mode)),
            ("联网音乐来源", self.monitor.music_verifier.last_source or "无"),
            ("联网音乐错误", self.monitor.music_verifier.last_error or "无"),
            ("联网分类增强", online_feature_state(settings.online_category_lookup, settings.private_title_mode)),
            ("联网分类来源", self.monitor.category_classifier.last_source or "无"),
            ("联网分类查询", self.monitor.category_classifier.last_query or "无"),
            ("联网分类错误", self.monitor.category_classifier.last_error or "无"),
            ("联网分类 Provider 错误", self.monitor.category_classifier.last_provider_errors or "无"),
            ("学习主题识别", learning_feature_state(settings)),
            ("学习主题来源", self.monitor.learning_classifier.last_source or "本地规则"),
            ("学习主题查询", self.monitor.learning_classifier.last_query or "无"),
            ("学习主题错误", self.monitor.learning_classifier.last_error or "无"),
            ("发声标签页", str(len(audible_tabs))),
            ("媒体会话", "可用" if self.monitor.media_provider.available else "不可用/兜底中"),
            ("媒体会话错误", self.monitor.media_provider.last_error or "无"),
            ("媒体会话连续失败", str(self.monitor.media_provider.consecutive_errors)),
            ("当前媒体项", str(len(media_items))),
            ("时间线保留", "永久" if settings.timeline_retention_days <= 0 else f"{settings.timeline_retention_days} 天"),
        ]
        self._set_metrics(rows)
        self.log_view.setPlainText(read_recent_log())

    def _browser_media_detail(self, latest_tab) -> str:
        parts = []
        if getattr(latest_tab, "has_video", False):
            parts.append("视频元素")
        if getattr(latest_tab, "has_audio", False):
            parts.append("音频元素")
        if getattr(latest_tab, "muted", False):
            parts.append("已静音")
        state = getattr(latest_tab, "media_state", "") or ""
        if state:
            parts.append(state)
        return " / ".join(parts) if parts else "未发现媒体元素"

    def clear_diagnostics_log(self) -> None:
        clear_log()
        self.refresh()


class CurrentStatusDialog(QDialog):
    def __init__(self, storage: Storage, monitor: ProcessMonitor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.monitor = monitor
        self.setWindowTitle("当前状态")
        self.setWindowIcon(build_app_icon())
        self.setMinimumSize(740, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("当前状态")
        title.setObjectName("statsTitle")
        self.last_refresh_label = QLabel("上次刷新：--")
        self.last_refresh_label.setObjectName("refreshStamp")
        self.category_correction_button = QPushButton("纠正当前分类")
        self.category_correction_button.setToolTip("把当前网页、视频或前台程序保存为新的分类规则")
        self.category_correction_button.clicked.connect(self.correct_current_category)
        copy_button = QPushButton("复制诊断信息")
        copy_button.setToolTip("复制当前状态表格，便于反馈识别问题")
        copy_button.clicked.connect(self.copy_status_diagnostics)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(title)
        header.addWidget(self.last_refresh_label)
        header.addStretch(1)
        header.addWidget(self.category_correction_button)
        header.addWidget(copy_button)
        header.addWidget(refresh_button)
        root.addLayout(header)

        self.tabs = QTabWidget()
        status_tab = QWidget()
        status_layout = QVBoxLayout(status_tab)
        status_layout.setContentsMargins(8, 8, 8, 8)
        status_layout.setSpacing(8)
        self.status_table = QTableWidget(0, 2)
        self.status_table.setHorizontalHeaderLabels(["项目", "当前值"])
        self.status_table.setAlternatingRowColors(True)
        self.status_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.status_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.horizontalHeader().setStretchLastSection(True)
        self.status_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        status_layout.addWidget(self.status_table, 1)

        note = QLabel("这个面板用于解释“现在软件正在记录什么”。更底层的错误日志和耗时指标请看托盘菜单里的运行诊断。")
        note.setObjectName("statsNote")
        note.setWordWrap(True)
        status_layout.addWidget(note)

        definitions_tab = QWidget()
        definitions_layout = QVBoxLayout(definitions_tab)
        definitions_layout.setContentsMargins(8, 8, 8, 8)
        self.definition_view = QPlainTextEdit()
        self.definition_view.setReadOnly(True)
        self.definition_view.setPlainText(data_definition_text())
        definitions_layout.addWidget(self.definition_view, 1)

        self.tabs.addTab(status_tab, "当前识别")
        self.tabs.addTab(definitions_tab, "数据口径")
        root.addWidget(self.tabs, 1)

        self.setStyleSheet(
            """
            QDialog { background: #f6f8fb; color: #17202a; font-family: {ui_font_stack()}; }
            QLabel#statsTitle { font-size: 18px; font-weight: 700; }
            QLabel#statsNote { color: #607089; }
            QLabel#refreshStamp {
                color: #607089;
                background: #ffffff;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: 650;
            }
            QTableWidget, QPlainTextEdit {
                background: white;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
                gridline-color: #e5ebf2;
            }
            QHeaderView::section {
                background: #eef3f8;
                border: none;
                border-right: 1px solid #d9e1ea;
                padding: 6px;
                font-weight: 650;
            }
            QTabWidget::pane { border: 1px solid #d9e1ea; border-radius: 8px; background: white; }
            QTabBar::tab { padding: 7px 12px; }
            QTabBar::tab:selected { background: #ffffff; border-bottom: 2px solid #1677d2; font-weight: 700; }
            QPushButton { padding: 6px 10px; border: 1px solid #b9c6d4; border-radius: 6px; background: #ffffff; }
            QPushButton:hover { background: #eef6ff; }
            """.replace("{ui_font_stack()}", ui_font_stack())
        )
        self.refresh()

    def _current_rule_source(self) -> tuple[str, str, str]:
        candidates = self._current_rule_candidates()
        if not candidates:
            return "", "any", ""
        pattern, target, preview, _description = candidates[0]
        return pattern, target, preview

    def _current_rule_candidates(self) -> list[tuple[str, str, str, str]]:
        candidates: list[tuple[str, str, str, str]] = []

        def add(pattern: str, target: str, preview: str, description: str) -> None:
            clean = pattern.strip().lower()
            if not clean:
                return
            if any(existing_pattern == clean and existing_target == target for existing_pattern, existing_target, _preview, _desc in candidates):
                return
            candidates.append((clean, target, preview, description))

        latest_tab = self.monitor.browser_bridge.latest(max_age_seconds=3600)
        if latest_tab:
            domain = str(getattr(latest_tab, "domain", "") or "").strip().lower()
            title = cleanup_rule_title(str(getattr(latest_tab, "title", "") or ""))
            title_hint = "只纠正类似标题/视频，更适合 B 站、YouTube 等同一站点下内容差异很大的平台。"
            domain_hint = "纠正整个域名，适合普通网站；不适合把 B 站整个域名都归到同一类。"
            if title and (not domain or is_generic_content_domain(domain)):
                add(title, "title", f"标题：{title}", title_hint)
                if domain:
                    add(domain, "domain", f"域名：{domain}", domain_hint)
            else:
                if domain:
                    add(domain, "domain", f"域名：{domain}", domain_hint)
                if title:
                    add(title, "title", f"标题：{title}", title_hint)
        if self.monitor.current_video_titles:
            for title in self.monitor.current_video_titles[:2]:
                cleaned = cleanup_rule_title(title)
                add(cleaned, "title", f"播放内容：{cleaned}", "纠正当前播放内容标题，适合单条视频或音乐视频。")
        if self.monitor.current_media_titles:
            for title in self.monitor.current_media_titles[:2]:
                cleaned = cleanup_rule_title(title)
                add(cleaned, "title", f"媒体标题：{cleaned}", "纠正当前媒体标题，适合单首歌或一次播放内容。")
        if self.monitor.foreground_title:
            title = cleanup_rule_title(self.monitor.foreground_title)
            add(title, "title", f"窗口标题：{title}", "纠正相似窗口标题，适合文档、课程页或本地窗口内容。")
        if self.monitor.current_foreground_exe:
            exe = self.monitor.current_foreground_exe.strip().lower()
            add(exe, "app", f"程序：{exe}", "纠正整个本地程序，适合把某个应用长期归为同一分类。")
        return candidates

    def _classification_source_text(self) -> str:
        category = self.monitor.current_category or "无"
        if category == "无":
            return "无"
        latest_tab = self.monitor.browser_bridge.latest(max_age_seconds=60)
        domain = str(getattr(latest_tab, "domain", "") or "") if latest_tab else ""
        title = str(getattr(latest_tab, "title", "") or self.monitor.foreground_title or "")
        exe = self.monitor.current_foreground_exe or ("browser" if latest_tab else "")
        detail = self.storage.category_explanation(
            category,
            exe,
            domain,
            title,
            self.monitor.current_learning_topic or "",
        )
        return f"{category} · {detail}"

    def _current_content_type_text(self, latest_tab) -> str:
        if self.monitor.current_video_titles:
            return "播放内容（视频/发声标签页）"
        if self.monitor.current_media_titles:
            return "音乐/媒体播放"
        if latest_tab:
            return "网页注视"
        if self.monitor.foreground_title:
            return "窗口标题"
        return "前台程序"

    def copy_status_diagnostics(self) -> None:
        lines = []
        for row in range(self.status_table.rowCount()):
            name_item = self.status_table.item(row, 0)
            value_item = self.status_table.item(row, 1)
            if name_item and value_item:
                lines.append(f"{name_item.text()}: {value_item.text()}")
        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "已复制", "当前状态诊断信息已复制到剪贴板。")

    def correct_current_category(self) -> None:
        candidates = self._current_rule_candidates()
        if not candidates:
            QMessageBox.information(self, "暂无可纠正内容", "当前没有可用于保存规则的网页、标题或程序。")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("纠正当前分类")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        intro = QLabel("选择新的内容分类，并确认这条规则以后按什么范围生效。")
        intro.setObjectName("statsNote")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(8)
        category_combo = QComboBox()
        category_combo.addItems([*COMMON_CATEGORY_CHOICES, "自定义..."])
        current = self.monitor.current_category or "其他"
        category_index = category_combo.findText(current)
        category_combo.setCurrentIndex(category_index if category_index >= 0 else category_combo.findText("其他"))
        target_combo = QComboBox()
        for pattern, target, preview, description in candidates:
            target_combo.addItem(preview, (pattern, target, preview, description))
        rule_preview = QLabel("")
        rule_preview.setObjectName("statsNote")
        rule_preview.setWordWrap(True)

        def update_preview() -> None:
            data = target_combo.currentData()
            if not data:
                return
            pattern, target, _preview, description = data
            category = category_combo.currentText()
            exists = any(str(row["pattern"]).lower() == pattern for row in self.storage.category_rules())
            prefix = "将更新已有规则：" if exists else "将添加规则："
            rule_preview.setText(f"{prefix}{target_label(target)}包含“{pattern}”时归为“{category}”。{description}")

        category_combo.currentIndexChanged.connect(update_preview)
        target_combo.currentIndexChanged.connect(update_preview)
        form.addWidget(QLabel("归为"), 0, 0)
        form.addWidget(category_combo, 0, 1)
        form.addWidget(QLabel("保存范围"), 1, 0)
        form.addWidget(target_combo, 1, 1)
        form.setColumnStretch(1, 1)
        layout.addLayout(form)
        layout.addWidget(rule_preview)
        update_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        if buttons.button(QDialogButtonBox.StandardButton.Save):
            buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        if buttons.button(QDialogButtonBox.StandardButton.Cancel):
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = target_combo.currentData()
        if not data:
            return
        pattern, target, preview, _description = data
        category = category_combo.currentText()
        if category == "自定义...":
            category, ok = QInputDialog.getText(self, "自定义分类", "分类名称：")
            if not ok or not category.strip():
                return
            category = category.strip()
        try:
            self.storage.add_category_rule(pattern, category, target, update_existing=True)
        except Exception as exc:
            show_operation_error(self, "保存分类规则失败", exc)
            return
        self.refresh()
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_open_dialogs"):
            QTimer.singleShot(0, parent.refresh_open_dialogs)  # type: ignore[attr-defined]
        QMessageBox.information(self, "分类规则已保存", f"已保存规则：{target_label(target)}包含“{pattern}”时归为“{category}”。\n\n来源：{preview}")

    def _browser_media_detail(self, latest_tab) -> str:
        if not latest_tab:
            return "无"
        parts = []
        if getattr(latest_tab, "has_video", False):
            parts.append("视频元素")
        if getattr(latest_tab, "has_audio", False):
            parts.append("音频元素")
        if getattr(latest_tab, "muted", False):
            parts.append("已静音")
        state = getattr(latest_tab, "media_state", "") or ""
        if state:
            parts.append(state)
        return " / ".join(parts) if parts else "未发现媒体元素"

    def _set_rows(self, rows: list[tuple[str, str]]) -> None:
        self.status_table.setRowCount(len(rows))
        for row_index, (name, value) in enumerate(rows):
            name_item = QTableWidgetItem(name)
            value_item = QTableWidgetItem(value)
            value_item.setToolTip(value)
            self.status_table.setItem(row_index, 0, name_item)
            self.status_table.setItem(row_index, 1, value_item)
        self.status_table.resizeColumnsToContents()

    def refresh(self) -> None:
        self.last_refresh_label.setText(f"上次刷新：{datetime.now().strftime('%H:%M:%S')}")
        settings = self.storage.load_settings()
        quality = self.storage.recognition_health_range(date.today(), date.today())
        latest_tab = self.monitor.browser_bridge.latest(max_age_seconds=3600)
        audible_tabs = self.monitor.browser_bridge.audible_tabs(max_age_seconds=3600)
        media_items = self.monitor.media_provider.current_items()
        current_music = " / ".join(self.monitor.current_media_titles[:3]) if self.monitor.current_media_titles else "无"
        current_video = " / ".join(self.monitor.current_video_titles[:3]) if self.monitor.current_video_titles else "无"
        latest_web = "无"
        if latest_tab:
            latest_web = f"{latest_tab.domain or '未知域名'} · {latest_tab.title[:140] or '无标题'}"
        sort_labels = {
            "current_first": "当前应用置顶，其余按今日前台时长降序",
            "foreground": "按今日前台时长从大到小",
            "running": "按今日总运行时长从大到小",
            "name": "按程序名称 A-Z",
        }
        rows = [
            ("记录状态", "已暂停" if self.monitor.is_paused else "记录中"),
            ("小组件模式", "固定展开" if settings.always_expanded else "悬浮折叠/悬停展开"),
            ("隐私模式", "开启" if settings.private_title_mode else "关闭"),
            ("UI 字体", ui_font_status_text()),
            ("空闲状态", f"{'空闲' if self.monitor.is_idle else '活动'} · {format_duration(self.monitor.idle_seconds)}"),
            ("前台程序", self.monitor.foreground_path or "未识别"),
            ("前台标题", self.monitor.foreground_title[:160] or "无"),
            ("当前网页", latest_web),
            ("内容类型", self._current_content_type_text(latest_tab)),
            ("内容分类", self.monitor.current_category or "无"),
            ("分类依据", self._classification_source_text()),
            ("纠正规则候选", self._current_rule_source()[2] or "无"),
            ("最近联网分类", f"{self.monitor.category_classifier.last_source or '无'} · {self.monitor.category_classifier.last_query[:100] if self.monitor.category_classifier.last_query else '无查询'}"),
            ("联网分类错误", self.monitor.category_classifier.last_error or self.monitor.category_classifier.last_provider_errors or "无"),
            ("网页媒体元素", self._browser_media_detail(latest_tab)),
            ("当前视频", current_video),
            ("当前音乐", current_music),
            ("发声标签页", f"{len(audible_tabs)} 个"),
            ("系统媒体会话", "可用" if self.monitor.media_provider.available else "不可用/使用兜底"),
            ("当前媒体项", f"{len(media_items)} 个"),
            ("浏览器扩展", "最近有活动标签页上报" if latest_tab else "最近无活动标签页上报"),
            ("识别健康度（今天）", quality_summary_text(quality)),
            ("健康度说明", f"仅域名网页 {quality.get('web_domain_only_rows', 0)} 条；播放内容仍停留在宽泛分类 {quality.get('broad_video_rows', 0)} 条；低置信内容 {quality.get('low_confidence_rows', 0)} 条"),
            ("页面内容信号", f"{self.monitor.browser_bridge.page_signal_count()} 条/小时"),
            ("联网音乐校验", online_feature_state(settings.online_music_lookup, settings.private_title_mode)),
            ("联网分类增强", online_feature_state(settings.online_category_lookup, settings.private_title_mode)),
            ("学习主题识别", learning_feature_state(settings)),
            ("当前学习主题", self.monitor.current_learning_topic or "无"),
            ("当前 OneNote 笔记本", self.monitor.current_onenote_notebook or "未检测到"),
            ("当前列表排序", sort_labels.get(settings.top_list_sort, sort_labels["current_first"])),
            ("采样频率", f"约 {self.monitor.interval_ms / 1000:.1f} 秒/次"),
            ("最近采样耗时", f"{self.monitor.last_sample_ms:.0f} ms"),
            ("最近数据库写入", f"{self.monitor.last_db_write_ms:.0f} ms"),
            ("数据库", str(self.storage.db_path)),
        ]
        self._set_rows(rows)


class StatsDialog(QDialog):
    def __init__(self, storage: Storage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.storage = storage
        self._refreshing = False
        self._heatmap_cache: tuple[str, list] | None = None
        self._line_chart_cache: tuple[str, dict] | None = None
        self._artist_cache: tuple[str, list] | None = None
        self._chart_cache_time = 0.0
        self._timeline_limit = 120
        self._timeline_loaded_key = ""
        self._slow_refresh_timer = QTimer(self)
        self._slow_refresh_timer.setSingleShot(True)
        self._slow_refresh_timer.setInterval(300)
        self._slow_refresh_timer.timeout.connect(self._show_slow_refresh_hint)
        self.setWindowTitle(f"使用数据分析 · v{__version__}")
        self.setWindowIcon(build_app_icon())
        self.setMinimumSize(1020, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header_panel = QFrame()
        header_panel.setObjectName("statsHeaderPanel")
        header_box = QVBoxLayout(header_panel)
        header_box.setContentsMargins(12, 10, 12, 10)
        header_box.setSpacing(8)
        range_row = QHBoxLayout()
        range_row.setSpacing(8)
        summary_row = QHBoxLayout()
        summary_row.setSpacing(8)
        title = QLabel("使用数据分析")
        title.setObjectName("statsTitle")
        self.range_combo = QComboBox()
        self.range_combo.addItem("今天", "today")
        self.range_combo.addItem("昨天", "yesterday")
        self.range_combo.addItem("最近 7 天", "7d")
        self.range_combo.addItem("最近 30 天", "30d")
        self.range_combo.addItem("本周", "week")
        self.range_combo.addItem("自定义", "custom")
        self.range_combo.currentIndexChanged.connect(self._on_range_changed)
        today_qdate = QDate.currentDate()
        self.start_date_edit = QDateEdit(today_qdate)
        self.start_date_edit.setCalendarPopup(False)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setMinimumWidth(132)
        self.start_date_edit.dateChanged.connect(self._on_custom_date_changed)
        self.end_date_edit = QDateEdit(today_qdate)
        self.end_date_edit.setCalendarPopup(False)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setMinimumWidth(132)
        self.end_date_edit.dateChanged.connect(self._on_custom_date_changed)
        self._style_date_edit(self.start_date_edit)
        self._style_date_edit(self.end_date_edit)
        self.range_picker_button = QPushButton("选择范围")
        self.range_picker_button.setToolTip("打开更清晰的日期范围选择面板")
        self.range_picker_button.clicked.connect(self._open_range_picker)
        self._custom_refresh_timer = QTimer(self)
        self._custom_refresh_timer.setSingleShot(True)
        self._custom_refresh_timer.setInterval(180)
        self._custom_refresh_timer.timeout.connect(self.refresh)
        self.foreground_total = QLabel()
        self.foreground_total.setObjectName("statsPill")
        self.media_total = QLabel()
        self.media_total.setObjectName("statsPill")
        self.video_total = QLabel()
        self.video_total.setObjectName("statsPill")
        self.learning_total = QLabel()
        self.learning_total.setObjectName("statsPill")
        self.detail_status = QLabel("准备加载数据")
        self.detail_status.setObjectName("detailStatus")
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.refresh)
        self.prev_range_button = QPushButton("上一段")
        self.prev_range_button.setToolTip("按当前范围长度向前移动，例如 7 天范围会向前切换 7 天")
        self.prev_range_button.clicked.connect(lambda: self._shift_date_range(-1))
        self.next_range_button = QPushButton("下一段")
        self.next_range_button.setToolTip("按当前范围长度向后移动，不会超过今天")
        self.next_range_button.clicked.connect(lambda: self._shift_date_range(1))
        self.today_range_button = QPushButton("今天")
        self.today_range_button.setToolTip("回到今天")
        self.today_range_button.clicked.connect(self._jump_to_today_range)
        export_menu = QMenu(self)
        report_action = QAction("导出 HTML 报告", self)
        report_action.triggered.connect(self.export_report)
        music_export_action = QAction("导出音乐分析 CSV", self)
        music_export_action.triggered.connect(self.export_music_csv)
        learning_export_action = QAction("导出学习分析 CSV", self)
        learning_export_action.triggered.connect(self.export_learning_csv)
        export_menu.addAction(report_action)
        export_menu.addAction(music_export_action)
        export_menu.addAction(learning_export_action)
        self.export_button = QPushButton("导出")
        self.export_button.setToolTip("导出当前统计范围的报告或分析 CSV")
        self.export_button.setMenu(export_menu)
        definition_button = QPushButton("数据口径")
        definition_button.clicked.connect(self.show_data_definitions)
        range_row.addWidget(title)
        range_row.addWidget(self.range_combo)
        range_row.addWidget(self.start_date_edit)
        self.date_separator_label = QLabel("至")
        range_row.addWidget(self.date_separator_label)
        range_row.addWidget(self.end_date_edit)
        range_row.addWidget(self.range_picker_button)
        range_row.addWidget(self.prev_range_button)
        range_row.addWidget(self.next_range_button)
        range_row.addWidget(self.today_range_button)
        range_row.addStretch(1)
        range_row.addWidget(definition_button)
        range_row.addWidget(self.refresh_button)
        summary_row.addWidget(self.learning_total)
        summary_row.addWidget(self.foreground_total)
        summary_row.addWidget(self.video_total)
        summary_row.addWidget(self.media_total)
        summary_row.addWidget(self.detail_status, 1)
        summary_row.addWidget(self.export_button)
        header_box.addLayout(range_row)
        separator = QFrame()
        separator.setObjectName("statsHeaderSeparator")
        separator.setFrameShape(QFrame.Shape.HLine)
        header_box.addWidget(separator)
        header_box.addLayout(summary_row)
        root.addWidget(header_panel)
        self.range_summary_label = QLabel("当前范围：准备加载")
        self.range_summary_label.setObjectName("rangeSummary")
        self.range_summary_label.setWordWrap(True)
        root.addWidget(self.range_summary_label)
        self.compare_label = QLabel("对比上一周期：准备加载")
        self.compare_label.setObjectName("compareLabel")
        self.compare_label.setWordWrap(True)
        root.addWidget(self.compare_label)
        self.data_tools = self._make_data_tools()
        root.addWidget(self.data_tools)

        self.tabs = QTabWidget()
        self.overview_tab = self._make_overview_tab()
        self.trend_tab = self._make_trend_tab()
        self.process_table = self._make_table(["程序", "前台时长", "总运行", "后台", "路径"], sort_column=1)
        self.web_table = self._make_table(["页面标题", "域名", "内容分类", "分类依据", "学习主题", "浏览器", "注视时长", "URL"], sort_column=6)
        self.video_table = self._make_table(["播放内容", "内容类型", "域名", "内容分类", "分类依据", "学习主题", "播放时长", "URL"], sort_column=6)
        self.media_table = self._make_table(["播放内容", "内容分类", "分类依据", "来源", "播放时长", "最后记录"], sort_column=4)
        self.music_analysis_table = self._make_table(["歌曲", "歌手", "来源", "播放时长", "占音乐时长", "最后记录"], sort_column=3)
        self.music_analysis_tab = self._make_music_analysis_tab()
        self.artist_analysis_table = self._make_table(["歌手", "播放时长", "歌曲数", "代表歌曲", "来源", "占音乐时长"], sort_column=1)
        self.artist_analysis_tab = self._make_artist_analysis_tab()
        self.learning_analysis_table = self._make_table(["学习主题", "网页注视时长", "视频/播放时长", "总时长", "条目数", "最后记录"], sort_column=3)
        self.learning_analysis_tab = self._make_learning_analysis_tab()
        self.window_table = self._make_table(["窗口标题", "内容分类", "分类依据", "学习主题", "程序", "注视时长", "最后记录"], sort_column=5)
        self.category_table = self._make_table(["内容分类", "总时长", "占比", "注视时长", "播放/后台", "条目数", "来源类型", "最后记录"], sort_column=1)
        self.goal_table = self._make_table(["目标", "方向", "当前", "目标值", "状态"], sort_column=2)
        self.goal_tab = self._make_goal_tab()
        self.timeline_table = self._make_table(["开始", "类型", "标题", "应用", "内容分类", "学习主题", "时长"], sort_column=0)
        self.timeline_tab = self._make_timeline_tab()
        self.timeline_table.itemSelectionChanged.connect(self._update_timeline_detail)
        for table, kind in (
            (self.web_table, "web"),
            (self.video_table, "video"),
            (self.media_table, "media"),
            (self.window_table, "window"),
        ):
            self._install_category_menu(table, kind)
        # Domain and video-domain tables (created here, populated later)
        self.domain_table = self._make_table(["网站域名", "浏览时长", "网页数", "主要页面", "最后访问"], 1)
        self.video_domain_table = self._make_table(["播放来源", "播放时长", "条目数", "主要内容", "分类分布", "最后播放"], 1)

        # --- Merged tabs: 程序, 网页, 视频, 音乐 ---
        self.programs_tab = self._make_merged_tab(
            "程序前台", self.process_table,
            "窗口标题", self.window_table,
        )
        self.web_tab = self._make_merged_tab(
            "网页注视", self.web_table,
            "网站排行", self.domain_table,
        )
        self.video_tab = self._make_merged_tab(
            "播放内容（类型=视频播放，分类=学习/游戏/音乐等细分）", self.video_table,
            "播放来源与分类分布", self.video_domain_table,
        )
        self.music_tab = QWidget()
        music_layout = QVBoxLayout(self.music_tab)
        music_layout.setContentsMargins(0, 0, 0, 0)
        music_layout.addWidget(QLabel("音乐播放记录"))
        music_layout.addWidget(self.media_table)
        music_layout.addSpacing(8)
        music_layout.addWidget(QLabel("歌曲分析（按歌曲+歌手去重）"))
        music_layout.addWidget(self.music_analysis_table)
        music_layout.addSpacing(8)
        music_layout.addWidget(QLabel("歌手分析（按歌手汇总）"))
        music_layout.addWidget(self.artist_analysis_table)

        self.tabs.addTab(self.overview_tab, "概览")
        self.tabs.addTab(self.trend_tab, "趋势")
        self.tabs.addTab(self.programs_tab, "程序")
        self.tabs.addTab(self.web_tab, "网页")
        self.tabs.addTab(self.video_tab, "播放")
        self.tabs.addTab(self.music_tab, "音乐")
        self.tabs.addTab(self.learning_analysis_tab, "学习")
        self.tabs.addTab(self.category_table, "分类")
        self.tabs.addTab(self.goal_tab, "目标")
        self.tabs.addTab(self.timeline_tab, "时间线")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        note = QLabel("网页注视和窗口标题统计的是前台焦点；播放页里的“内容类型”表示视频/发声标签页，“内容分类”表示学习、游戏、音乐等细分。可用“纠正选中”或右键保存分类规则。")
        note.setObjectName("statsNote")
        note.setWordWrap(True)
        root.addWidget(note)

        self.setStyleSheet(
            """
            QDialog { background: #f6f8fb; color: #17202a; font-family: {ui_font_stack()}; }
            QLabel#statsTitle { font-size: 18px; font-weight: 700; }
            QLabel#statsNote { color: #607089; }
            QFrame#statsHeaderPanel {
                background: #ffffff;
                border: 1px solid #d9e1ea;
                border-radius: 10px;
            }
            QFrame#statsHeaderSeparator {
                color: #e8eef5;
                background: #e8eef5;
                max-height: 1px;
            }
            QLabel#mergedSectionHeader {
                color: #334155;
                font-size: 13px;
                font-weight: 700;
                padding: 6px 0 2px 4px;
            }
            QTableWidget {
                gridline-color: #e8ecf1;
                alternate-background-color: #f8fafc;
            }
            QHeaderView::section {
                background: #eef3f8;
                color: #334155;
                font-weight: 700;
                padding: 5px 4px;
                border: none;
                border-bottom: 2px solid #d9e1ea;
            }
            QLabel#statsPill {
                background: #ffffff;
                border: 1px solid #d9e1ea;
                border-radius: 12px;
                padding: 5px 9px;
                color: #334155;
                font-weight: 650;
            }
            QLabel#detailStatus {
                color: #607089;
                padding: 5px 8px;
                font-size: 12px;
            }
            QLabel#rangeSummary {
                color: #475569;
                padding: 2px 4px;
                font-size: 12px;
            }
            QLabel#compareLabel {
                background: #ffffff;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
                color: #334155;
                padding: 7px 10px;
                font-weight: 650;
            }
            QDateEdit#dateRangeEdit {
                padding: 6px 10px;
                border: 1px solid #b9c6d4;
                border-radius: 8px;
                background: #ffffff;
                color: #0f172a;
                font-weight: 650;
            }
            QDateEdit#dateRangeEdit:focus {
                border-color: #1677d2;
                background: #f8fbff;
            }
            QFrame#dataTools {
                background: #ffffff;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
            }
            QLabel#dataToolsTitle {
                color: #334155;
                font-weight: 750;
                padding-right: 4px;
            }
            QLabel#dataScopeLabel {
                background: #eef6ff;
                border: 1px solid #cfe4ff;
                border-radius: 6px;
                color: #1d4ed8;
                font-size: 12px;
                font-weight: 700;
                padding: 5px 8px;
            }
            QLabel#dataFilterStatus {
                color: #607089;
                font-size: 12px;
                min-width: 128px;
            }
            QLineEdit {
                padding: 6px 9px;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background: #ffffff;
            }
            QLineEdit:focus {
                border-color: #1677d2;
            }
            QComboBox:disabled, QCheckBox:disabled {
                color: #94a3b8;
            }
            QLabel#timelineHint {
                color: #607089;
                padding: 3px 4px;
            }
            QFrame#timelineQueryPanel {
                background: #ffffff;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
            }
            QFrame#goalDashboard {
                background: #ffffff;
                border: 1px solid #d9e1ea;
                border-radius: 10px;
            }
            QLabel#goalHint {
                color: #475569;
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 8px 10px;
                font-weight: 650;
            }
            QLabel#timelineQueryTitle {
                color: #334155;
                font-weight: 750;
            }
            QPlainTextEdit#timelineDetail {
                background: #f8fafc;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
                color: #334155;
                padding: 8px;
            }
            QLabel { color: #17202a; }
            QComboBox { padding: 6px 10px; border: 1px solid #b9c6d4; border-radius: 6px; background: #ffffff; }
            QPushButton { padding: 6px 10px; border: 1px solid #b9c6d4; border-radius: 6px; background: #ffffff; }
            QPushButton:hover { background: #eef6ff; }
            QFrame#statCard, QFrame#chartPanel {
                background: #ffffff;
                border: 1px solid #d9e1ea;
                border-radius: 10px;
            }
            QLabel#statCardTitle { color: #607089; font-size: 12px; }
            QLabel#statCardValue { color: #17202a; font-size: 23px; font-weight: 800; }
            QLabel#statCardSub { color: #738196; font-size: 11px; }
            QTabWidget::pane { border: 1px solid #d9e1ea; border-radius: 8px; background: white; }
            QTabBar::tab { padding: 7px 12px; }
            QTabBar::tab:selected { background: #ffffff; border-bottom: 2px solid #1677d2; font-weight: 700; }
            QTableWidget {
                background: white;
                border: none;
                gridline-color: #e5ebf2;
                selection-background-color: #ddecff;
            }
            QHeaderView::section {
                background: #eef3f8;
                border: none;
                border-right: 1px solid #d9e1ea;
                padding: 6px;
                font-weight: 650;
            }
            """.replace("{ui_font_stack()}", ui_font_stack())
        )
        self._install_shortcuts()
        self._sync_custom_date_controls()
        QTimer.singleShot(0, self.refresh)

    def _install_shortcuts(self) -> None:
        self._shortcuts = [
            QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_timeline_search),
            QShortcut(QKeySequence("Ctrl+D"), self, activated=self._jump_to_today_range),
            QShortcut(QKeySequence("Ctrl+Left"), self, activated=lambda: self._shift_date_range(-1)),
            QShortcut(QKeySequence("Ctrl+Right"), self, activated=lambda: self._shift_date_range(1)),
            QShortcut(QKeySequence("Escape"), self, activated=self.close),
        ]

    def _focus_timeline_search(self) -> None:
        self.tabs.setCurrentWidget(self.timeline_tab)
        self.timeline_search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.timeline_search_input.selectAll()

    def _style_date_edit(self, edit: QDateEdit) -> None:
        edit.setObjectName("dateRangeEdit")
        edit.setCalendarPopup(False)
        edit.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        edit.setMinimumDate(QDate(2000, 1, 1))
        edit.setMaximumDate(QDate.currentDate())
        edit.setToolTip("直接输入 yyyy-MM-dd，或点击右侧“选择范围”打开日期面板")
        calendar = edit.calendarWidget()
        if calendar is not None:
            calendar.setGridVisible(True)
            calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
            calendar.setStyleSheet(
                """
                QCalendarWidget {
                    background: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 8px;
                }
                QCalendarWidget QWidget#qt_calendar_navigationbar {
                    background: #eef6ff;
                    border-bottom: 1px solid #cfe4ff;
                }
                QCalendarWidget QToolButton {
                    color: #0f172a;
                    background: transparent;
                    border: none;
                    border-radius: 6px;
                    padding: 5px 8px;
                    font-weight: 700;
                }
                QCalendarWidget QToolButton:hover { background: #dbeafe; }
                QCalendarWidget QMenu { background: #ffffff; border: 1px solid #cbd5e1; }
                QCalendarWidget QSpinBox {
                    background: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    padding: 3px 6px;
                }
                QCalendarWidget QAbstractItemView {
                    outline: 0;
                    selection-background-color: #1677d2;
                    selection-color: #ffffff;
                    color: #0f172a;
                    background: #ffffff;
                    alternate-background-color: #f8fafc;
                }
                """
            )

    def _open_range_picker(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("选择日期范围")
        dialog.setMinimumSize(760, 470)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        quick_label = QLabel("快捷范围")
        quick_label.setObjectName("rangePickerLabel")
        quick_row.addWidget(quick_label)
        for label, days in (("今天", 1), ("最近 7 天", 7), ("最近 30 天", 30)):
            btn = QPushButton(label)
            btn.setObjectName("subtleButton")
            btn.clicked.connect(lambda _checked=False, d=days: self._set_picker_days(start_cal, end_cal, d))
            quick_row.addWidget(btn)
        quick_row.addStretch(1)
        layout.addLayout(quick_row)

        calendars = QHBoxLayout()
        calendars.setSpacing(12)
        start_box = QVBoxLayout()
        end_box = QVBoxLayout()
        start_label = QLabel("开始日期")
        end_label = QLabel("结束日期")
        start_label.setObjectName("rangePickerLabel")
        end_label.setObjectName("rangePickerLabel")
        start_cal = QCalendarWidget()
        end_cal = QCalendarWidget()
        for cal in (start_cal, end_cal):
            cal.setGridVisible(True)
            cal.setMaximumDate(QDate.currentDate())
            cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
            cal.setStyleSheet(self._calendar_style_sheet())
        start_cal.setSelectedDate(self.start_date_edit.date())
        end_cal.setSelectedDate(self.end_date_edit.date())
        start_box.addWidget(start_label)
        start_box.addWidget(start_cal)
        end_box.addWidget(end_label)
        end_box.addWidget(end_cal)
        calendars.addLayout(start_box, 1)
        calendars.addLayout(end_box, 1)
        layout.addLayout(calendars, 1)

        preview = QLabel()
        preview.setObjectName("rangePickerPreview")
        preview.setWordWrap(True)
        layout.addWidget(preview)

        def update_preview() -> None:
            start = self._qdate_to_date(start_cal.selectedDate())
            end = self._qdate_to_date(end_cal.selectedDate())
            if end < start:
                start, end = end, start
            days = (end - start).days + 1
            preview.setText(f"已选：{start.isoformat()} 至 {end.isoformat()} · 共 {days} 天")

        start_cal.selectionChanged.connect(update_preview)
        end_cal.selectionChanged.connect(update_preview)
        update_preview()

        hint = QLabel("选择后会切换到“自定义”范围。若结束日期早于开始日期，软件会自动交换。为避免误触，日期输入框不再弹出遮挡界面的下拉日历。")
        hint.setObjectName("rangePickerHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.setStyleSheet(
            """
            QDialog { background: #f6f8fb; color: #17202a; font-family: {ui_font_stack()}; }
            QLabel#rangePickerLabel { color: #0f172a; font-weight: 800; padding: 2px 0; }
            QLabel#rangePickerPreview { color: #1d4ed8; background: #eef6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 8px 10px; font-weight: 750; }
            QLabel#rangePickerHint { color: #64748b; background: #ffffff; border: 1px solid #d9e1ea; border-radius: 8px; padding: 8px 10px; }
            QPushButton { padding: 6px 10px; border: 1px solid #b9c6d4; border-radius: 7px; background: #ffffff; }
            QPushButton:hover { background: #eef6ff; }
            QPushButton#subtleButton { background: #f8fafc; color: #334155; border-color: #d9e1ea; }
            """.replace("{ui_font_stack()}", ui_font_stack())
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_custom_date_range(self._qdate_to_date(start_cal.selectedDate()), self._qdate_to_date(end_cal.selectedDate()))

    def _set_picker_days(self, start_cal: QCalendarWidget, end_cal: QCalendarWidget, days: int) -> None:
        end = QDate.currentDate()
        start = end.addDays(-(max(1, days) - 1))
        start_cal.setSelectedDate(start)
        end_cal.setSelectedDate(end)

    @staticmethod
    def _calendar_style_sheet() -> str:
        return """
            QCalendarWidget {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
            }
            QCalendarWidget QWidget#qt_calendar_navigationbar {
                background: #eef6ff;
                border-bottom: 1px solid #cfe4ff;
            }
            QCalendarWidget QToolButton {
                color: #0f172a;
                background: transparent;
                border: none;
                border-radius: 6px;
                padding: 5px 8px;
                font-weight: 700;
            }
            QCalendarWidget QToolButton:hover { background: #dbeafe; }
            QCalendarWidget QMenu { background: #ffffff; border: 1px solid #cbd5e1; }
            QCalendarWidget QSpinBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 3px 6px;
            }
            QCalendarWidget QAbstractItemView {
                outline: 0;
                selection-background-color: #1677d2;
                selection-color: #ffffff;
                color: #0f172a;
                background: #ffffff;
                alternate-background-color: #f8fafc;
            }
        """

    def _make_chart_panel(self, chart: QWidget) -> QFrame:
        panel = QFrame()
        panel.setObjectName("chartPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(chart)
        return panel

    def _make_overview_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # Row 1: Learning spotlight (prominent)
        learn_row = QHBoxLayout()
        learn_row.setSpacing(10)
        self.learning_today_card = StatCard("学习总时长", app_color("learn"))
        self.learning_today_card.setMinimumHeight(100)
        learn_row.addWidget(self.learning_today_card, 2)
        self.focus_card = StatCard("前台注视", app_color("focus"))
        self.web_card = StatCard("网页注视", app_color("web"))
        learn_row.addWidget(self.focus_card, 1)
        learn_row.addWidget(self.web_card, 1)
        layout.addLayout(learn_row)

        # Row 2: Secondary metrics
        sec_row = QHBoxLayout()
        sec_row.setSpacing(10)
        self.video_card = StatCard("视频播放", app_color("video"))
        self.music_card = StatCard("音乐播放", app_color("music"))
        sec_row.addWidget(self.video_card, 1)
        sec_row.addWidget(self.music_card, 1)
        layout.addLayout(sec_row)

        self.streak_label = QLabel("")
        self.streak_label.setObjectName("streakLabel")
        self.streak_label.setStyleSheet(f"color: {app_color('video')}; font-size: 13px; font-weight: 700; padding: 4px 10px; background: #fff8e6; border-radius: 6px;")
        self.streak_label.setVisible(False)
        layout.addWidget(self.streak_label)

        chart_grid = QGridLayout()
        chart_grid.setHorizontalSpacing(10)
        chart_grid.setVerticalSpacing(10)
        self.category_chart = DonutChartWidget("分类时间占比")
        self.hourly_chart = HourlyActivityChart()
        chart_grid.addWidget(self._make_chart_panel(self.category_chart), 0, 0)
        chart_grid.addWidget(self._make_chart_panel(self.hourly_chart), 0, 1)
        chart_grid.setColumnStretch(0, 1)
        chart_grid.setColumnStretch(1, 1)
        layout.addLayout(chart_grid, 1)
        return tab

    def _make_trend_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        layout.addWidget(self._section_label("本周对比"))
        self.line_chart = GroupedBarChartWidget("本周 vs 上周")
        self.line_metric_combo = QComboBox()
        self.line_metric_combo.addItems(["前台注视", "视频播放", "音乐播放", "学习"])
        self.line_metric_combo.setMaximumWidth(120)
        self.line_metric_combo.currentIndexChanged.connect(self._on_line_metric_changed)
        line_hdr = QHBoxLayout()
        line_hdr.setContentsMargins(0, 0, 0, 2)
        line_hdr.addWidget(QLabel("指标"))
        line_hdr.addWidget(self.line_metric_combo)
        line_hdr.addStretch(1)
        line_panel = QFrame()
        line_panel.setObjectName("chartPanel")
        line_playout = QVBoxLayout(line_panel)
        line_playout.setContentsMargins(8, 6, 8, 8)
        line_playout.addLayout(line_hdr)
        line_playout.addWidget(self.line_chart)
        layout.addWidget(line_panel)

        layout.addWidget(self._section_label("长期趋势"))
        self.heatmap = HeatmapWidget("学习热力图（近 84 天）")
        self.heatmap_metric_combo = QComboBox()
        self.heatmap_metric_combo.addItems(["学习", "前台注视", "视频播放", "音乐播放"])
        self.heatmap_metric_combo.setMaximumWidth(120)
        self.heatmap_metric_combo.currentIndexChanged.connect(self._on_heatmap_metric_changed)
        heat_hdr = QHBoxLayout()
        heat_hdr.setContentsMargins(0, 0, 0, 2)
        heat_hdr.addWidget(QLabel("指标"))
        heat_hdr.addWidget(self.heatmap_metric_combo)
        heat_hdr.addStretch(1)
        heat_panel = QFrame()
        heat_panel.setObjectName("chartPanel")
        heat_playout = QVBoxLayout(heat_panel)
        heat_playout.setContentsMargins(8, 6, 8, 8)
        heat_playout.addLayout(heat_hdr)
        heat_playout.addWidget(self.heatmap)
        layout.addWidget(heat_panel)
        return tab

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        label.setStyleSheet("color: #607089; font-weight: 700; font-size: 13px; margin-top: 6px;")
        return label

    def _make_music_analysis_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        summary = QFrame()
        summary.setObjectName("chartPanel")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setSpacing(10)
        self.music_analysis_total = StatCard("音乐总时长", app_color("music"))
        self.music_analysis_count = StatCard("去重歌曲", app_color("learn"))
        self.music_analysis_top = StatCard("最常听", app_color("focus"))
        for card in (self.music_analysis_total, self.music_analysis_count, self.music_analysis_top):
            summary_layout.addWidget(card, 1)
        layout.addWidget(summary)
        layout.addWidget(self.music_analysis_table, 1)
        return tab

    def _make_artist_analysis_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        summary = QFrame()
        summary.setObjectName("chartPanel")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setSpacing(10)
        self.artist_analysis_total = StatCard("歌手总时长", app_color("music"))
        self.artist_analysis_count = StatCard("去重歌手", "#8b72d9")
        self.artist_analysis_top = StatCard("最爱歌手", app_color("focus"))
        for card in (self.artist_analysis_total, self.artist_analysis_count, self.artist_analysis_top):
            summary_layout.addWidget(card, 1)
        layout.addWidget(summary)
        layout.addWidget(self.artist_analysis_table, 1)
        return tab

    def _make_learning_analysis_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        summary = QFrame()
        summary.setObjectName("chartPanel")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setSpacing(10)
        self.learning_analysis_total = StatCard("学习总时长", app_color("focus"))
        self.learning_analysis_count = StatCard("去重主题数", app_color("learn"))
        self.learning_analysis_top = StatCard("最常学主题", app_color("video"))
        for card in (self.learning_analysis_total, self.learning_analysis_count, self.learning_analysis_top):
            summary_layout.addWidget(card, 1)
        layout.addWidget(summary)
        layout.addWidget(self.learning_analysis_table, 1)
        return tab

    def _make_goal_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        summary = QFrame()
        summary.setObjectName("goalDashboard")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(10, 8, 10, 8)
        summary_layout.setSpacing(10)
        self.goal_done_card = StatCard("达标", app_color("success"))
        self.goal_close_card = StatCard("接近", app_color("warning"))
        self.goal_missed_card = StatCard("未达标", app_color("danger"))
        for card in (self.goal_done_card, self.goal_close_card, self.goal_missed_card):
            card.setMinimumHeight(96)
            summary_layout.addWidget(card, 1)
        layout.addWidget(summary)
        self.goal_hint_label = QLabel("目标按当前日期范围计算；“接近”表示进度达到 70% 以上。可到设置 > 学习目标中调整目标。")
        self.goal_hint_label.setObjectName("goalHint")
        self.goal_hint_label.setWordWrap(True)
        layout.addWidget(self.goal_hint_label)
        layout.addWidget(self.goal_table, 1)
        return tab

    def _make_timeline_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        query_panel = QFrame()
        query_panel.setObjectName("timelineQueryPanel")
        query_layout = QGridLayout(query_panel)
        query_layout.setContentsMargins(10, 8, 10, 8)
        query_layout.setHorizontalSpacing(8)
        query_layout.setVerticalSpacing(6)

        title = QLabel("历史查询")
        title.setObjectName("timelineQueryTitle")
        self.timeline_search_input = QLineEdit()
        self.timeline_search_input.setPlaceholderText("搜索标题 / 应用 / 分类 / 学习主题")
        self.timeline_search_input.setClearButtonEnabled(True)
        self.timeline_kind_filter = QComboBox()
        for label, value in (
            ("全部类型", ""),
            ("网页", "web_page"),
            ("窗口", "window_title"),
            ("视频", "video_playback"),
            ("音乐", "media_playback"),
            ("空闲", "idle"),
        ):
            self.timeline_kind_filter.addItem(label, value)
        self.timeline_sort_combo = QComboBox()
        self.timeline_sort_combo.addItem("最近优先", "recent")
        self.timeline_sort_combo.addItem("时长最长", "duration")
        self.timeline_sort_combo.addItem("最早优先", "oldest")
        self.timeline_min_minutes_spin = QSpinBox()
        self.timeline_min_minutes_spin.setRange(0, 1440)
        self.timeline_min_minutes_spin.setSuffix(" 分钟+")
        self.timeline_min_minutes_spin.setToolTip("只显示单条持续时长不低于该值的记录；0 表示不限。")
        query_button = QPushButton("查询")
        query_button.clicked.connect(self._refresh_timeline_query)
        self.timeline_more_button = QPushButton("加载更多")
        self.timeline_more_button.setToolTip("每次增加 200 条时间线记录")
        self.timeline_more_button.clicked.connect(self._load_more_timeline)

        self.timeline_query_timer = QTimer(self)
        self.timeline_query_timer.setSingleShot(True)
        self.timeline_query_timer.setInterval(220)
        self.timeline_query_timer.timeout.connect(self._refresh_timeline_query)
        self.timeline_search_input.textChanged.connect(self._schedule_timeline_query_refresh)
        self.timeline_search_input.returnPressed.connect(self._refresh_timeline_query)
        self.timeline_kind_filter.currentIndexChanged.connect(self._refresh_timeline_query)
        self.timeline_sort_combo.currentIndexChanged.connect(self._refresh_timeline_query)
        self.timeline_min_minutes_spin.valueChanged.connect(self._refresh_timeline_query)

        self.timeline_hint = QLabel("按当前日期范围查询历史事件；关键词会匹配标题、应用、分类和学习主题。")
        self.timeline_hint.setObjectName("timelineHint")
        self.timeline_detail = QPlainTextEdit()
        self.timeline_detail.setObjectName("timelineDetail")
        self.timeline_detail.setReadOnly(True)
        self.timeline_detail.setMaximumHeight(104)
        self.timeline_detail.setPlainText("选择一条历史记录查看详情。")

        query_layout.addWidget(title, 0, 0)
        query_layout.addWidget(self.timeline_search_input, 0, 1, 1, 3)
        query_layout.addWidget(self.timeline_kind_filter, 0, 4)
        query_layout.addWidget(self.timeline_sort_combo, 0, 5)
        query_layout.addWidget(self.timeline_min_minutes_spin, 0, 6)
        query_layout.addWidget(query_button, 0, 7)
        query_layout.addWidget(self.timeline_more_button, 0, 8)
        query_layout.addWidget(self.timeline_hint, 1, 0, 1, 9)
        query_layout.setColumnStretch(1, 1)

        layout.addWidget(query_panel)
        layout.addWidget(self.timeline_table, 1)
        layout.addWidget(self.timeline_detail)
        return tab

    def _timeline_search_text(self) -> str:
        return self.timeline_search_input.text().strip() if hasattr(self, "timeline_search_input") else ""

    def _timeline_kind_value(self) -> str:
        return str(self.timeline_kind_filter.currentData() or "") if hasattr(self, "timeline_kind_filter") else ""

    def _timeline_sort_value(self) -> str:
        return str(self.timeline_sort_combo.currentData() or "recent") if hasattr(self, "timeline_sort_combo") else "recent"

    def _timeline_min_seconds(self) -> float:
        return float(self.timeline_min_minutes_spin.value() * 60) if hasattr(self, "timeline_min_minutes_spin") else 0.0

    def _schedule_timeline_query_refresh(self) -> None:
        if hasattr(self, "timeline_query_timer"):
            self.timeline_query_timer.start()

    def _refresh_timeline_query(self) -> None:
        if hasattr(self, "timeline_query_timer"):
            self.timeline_query_timer.stop()
        self._timeline_limit = 120
        self._timeline_loaded_key = ""
        if hasattr(self, "tabs") and self._is_timeline_tab_active():
            self.refresh()

    def _update_timeline_detail(self) -> None:
        if not hasattr(self, "timeline_detail") or not hasattr(self, "timeline_table"):
            return
        row = self.timeline_table.currentRow()
        if row < 0:
            self.timeline_detail.setPlainText("选择一条历史记录查看详情。")
            return
        values = {}
        for col in range(self.timeline_table.columnCount()):
            header_item = self.timeline_table.horizontalHeaderItem(col)
            item = self.timeline_table.item(row, col)
            if header_item and item:
                values[header_item.text()] = item.text()
        self.timeline_detail.setPlainText(
            "开始：{start}\n类型：{kind}\n标题：{title}\n应用：{app}\n分类：{category} · 学习主题：{topic}\n时长：{duration}".format(
                start=values.get("开始", ""),
                kind=values.get("类型", ""),
                title=values.get("标题", ""),
                app=values.get("应用", ""),
                category=values.get("内容分类", ""),
                topic=values.get("学习主题", ""),
                duration=values.get("时长", ""),
            )
        )

    def _make_data_tools(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("dataTools")
        panel.setVisible(False)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        title = QLabel("数据视图")
        title.setObjectName("dataToolsTitle")
        self.data_search_input = QLineEdit()
        self.data_search_input.setPlaceholderText("搜索当前表格：标题 / 域名 / 程序 / 分类")
        self.data_search_input.setClearButtonEnabled(True)
        self.data_search_input.textChanged.connect(self._apply_data_filters)

        self.data_scope_label = QLabel("当前页")
        self.data_scope_label.setObjectName("dataScopeLabel")

        self.data_category_filter = QComboBox()
        for item in ("全部分类", "学习", "编程", "AI 工具", "系统软件", "聊天", "游戏", "视频", "音乐", "娱乐", "社交", "办公", "工具", "网站", "购物", "新闻", "其他"):
            self.data_category_filter.addItem(item, "" if item == "全部分类" else item)
        self.data_category_filter.currentIndexChanged.connect(self._apply_data_filters)

        self.low_confidence_only_box = QCheckBox("低置信")
        self.low_confidence_only_box.setToolTip("只显示分类依据为低置信、兜底分类，或仍停留在宽泛分类的行")
        self.low_confidence_only_box.toggled.connect(self._apply_data_filters)

        self.correct_selected_button = QPushButton("纠正选中")
        self.correct_selected_button.setToolTip("为当前选中行添加可记住的分类规则")
        self.correct_selected_button.clicked.connect(self.correct_selected_category)

        clear_button = QPushButton("清空")
        clear_button.setToolTip("清空搜索、分类和低置信筛选")
        clear_button.clicked.connect(self._clear_data_filters)

        self.data_filter_status = QLabel("显示 0/0")
        self.data_filter_status.setObjectName("dataFilterStatus")

        layout.addWidget(title)
        layout.addWidget(self.data_scope_label)
        layout.addWidget(self.data_search_input, 1)
        layout.addWidget(self.data_category_filter)
        layout.addWidget(self.low_confidence_only_box)
        layout.addWidget(self.correct_selected_button)
        layout.addWidget(clear_button)
        layout.addWidget(self.data_filter_status)
        return panel

    def _make_table(self, headers: list[str], sort_column: int | None = None) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setProperty("defaultSortColumn", -1 if sort_column is None else sort_column)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(28)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setDefaultSectionSize(150)
        table.setShowGrid(False)
        table.setStyleSheet(
            """
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d9e1ea;
                border-radius: 8px;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }
            QTableWidget::item {
                border-bottom: 1px solid #edf2f7;
                padding-left: 4px;
                padding-right: 4px;
            }
            """
        )
        return table

    def _clear_data_filters(self) -> None:
        self.data_search_input.clear()
        self.data_category_filter.setCurrentIndex(0)
        self.low_confidence_only_box.setChecked(False)
        self._apply_data_filters()

    def _current_data_tables(self) -> list[QTableWidget]:
        if not hasattr(self, "tabs"):
            return []
        active = self.tabs.currentWidget()
        if active is self.programs_tab:
            return [self.process_table, self.window_table]
        if active is self.web_tab:
            return [self.web_table, self.domain_table]
        if active is self.video_tab:
            return [self.video_table, self.video_domain_table]
        if active is self.music_tab:
            return [self.media_table, self.music_analysis_table, self.artist_analysis_table]
        if active is self.learning_analysis_tab:
            return [self.learning_analysis_table]
        if active is self.category_table:
            return [self.category_table]
        if active is self.goal_tab:
            return [self.goal_table]
        if self._is_timeline_tab_active():
            return []
        return []

    def _header_texts(self, table: QTableWidget) -> list[str]:
        values = []
        for col in range(table.columnCount()):
            item = table.horizontalHeaderItem(col)
            values.append(item.text().strip() if item else "")
        return values

    def _category_column(self, table: QTableWidget) -> int:
        for index, header in enumerate(self._header_texts(table)):
            if header in {"内容分类", "分类", "主要分类", "分类分布"}:
                return index
        return -1

    def _classification_column(self, table: QTableWidget) -> int:
        for index, header in enumerate(self._header_texts(table)):
            if header == "分类依据":
                return index
        return -1

    def _row_text(self, table: QTableWidget, row: int) -> str:
        parts = []
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item:
                parts.append(item.text())
        return " ".join(parts)

    def _row_is_low_confidence(self, table: QTableWidget, row: int, category_col: int, reason_col: int) -> bool:
        reason = table.item(row, reason_col).text() if reason_col >= 0 and table.item(row, reason_col) else ""
        if "置信度：低" in reason or "未命中细分类" in reason or "兜底分类" in reason:
            return True
        if category_col >= 0:
            item = table.item(row, category_col)
            category = item.text().strip() if item else ""
            return category in {"其他", "视频", "网站", "浏览器", "工具"}
        return False

    def _decorate_data_table(self, table: QTableWidget) -> None:
        category_col = self._category_column(table)
        reason_col = self._classification_column(table)
        if category_col < 0 and reason_col < 0:
            return
        for row in range(table.rowCount()):
            reason = table.item(row, reason_col).text() if reason_col >= 0 and table.item(row, reason_col) else ""
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item:
                    item.setBackground(QBrush())
                    item.setForeground(QBrush())
            background = None
            if self._row_is_low_confidence(table, row, category_col, reason_col):
                background = QColor("#fff7ed")
            if "来源：用户纠正" in reason:
                background = QColor("#ecfdf5")
            elif "来源：联网分类" in reason:
                background = QColor("#eff6ff")
            elif "来源：学习主题识别" in reason:
                background = QColor("#f0fdf4")
            if background is not None:
                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if item:
                        item.setBackground(QBrush(background))
            if category_col >= 0:
                item = table.item(row, category_col)
                if item:
                    item.setForeground(QBrush(QColor(category_color(item.text().strip()))))
            if reason_col >= 0:
                item = table.item(row, reason_col)
                if item:
                    if "置信度：低" in reason or "兜底分类" in reason:
                        item.setForeground(QBrush(QColor("#b45309")))
                    elif "来源：用户纠正" in reason:
                        item.setForeground(QBrush(QColor("#047857")))
                    elif "来源：联网分类" in reason:
                        item.setForeground(QBrush(QColor("#1d4ed8")))

    def _data_filter_capabilities(self, tables: list[QTableWidget]) -> tuple[bool, bool]:
        has_category = any(self._category_column(table) >= 0 for table in tables)
        has_reason = any(self._classification_column(table) >= 0 for table in tables)
        return has_category, has_reason

    def _update_data_tools_for_tab(self) -> None:
        tables = self._current_data_tables()
        self.data_tools.setVisible(bool(tables))
        if hasattr(self, "data_scope_label") and hasattr(self, "tabs"):
            self.data_scope_label.setText(self.tabs.tabText(self.tabs.currentIndex()))
        has_category, has_reason = self._data_filter_capabilities(tables)
        self.data_category_filter.setEnabled(has_category)
        self.low_confidence_only_box.setEnabled(has_category or has_reason)
        self.correct_selected_button.setEnabled(bool(tables))
        if not has_category and self.data_category_filter.currentIndex() != 0:
            self.data_category_filter.blockSignals(True)
            self.data_category_filter.setCurrentIndex(0)
            self.data_category_filter.blockSignals(False)
        if not (has_category or has_reason) and self.low_confidence_only_box.isChecked():
            self.low_confidence_only_box.blockSignals(True)
            self.low_confidence_only_box.setChecked(False)
            self.low_confidence_only_box.blockSignals(False)
        self._apply_data_filters()

    def _apply_data_filters(self) -> None:
        if not hasattr(self, "data_search_input"):
            return
        tables = self._current_data_tables()
        has_category, has_reason = self._data_filter_capabilities(tables)
        query = self.data_search_input.text().strip().casefold()
        category_filter = str(self.data_category_filter.currentData() or "") if has_category else ""
        low_only = self.low_confidence_only_box.isChecked() if (has_category or has_reason) else False
        visible_total = 0
        row_total = 0
        for table in tables:
            self._decorate_data_table(table)
            category_col = self._category_column(table)
            reason_col = self._classification_column(table)
            table.setUpdatesEnabled(False)
            try:
                for row in range(table.rowCount()):
                    row_total += 1
                    row_text = self._row_text(table, row).casefold()
                    category_text = ""
                    if category_col >= 0 and table.item(row, category_col):
                        category_text = table.item(row, category_col).text().strip()
                    matches_query = not query or query in row_text
                    matches_category = not category_filter or (category_col >= 0 and category_text == category_filter)
                    matches_confidence = not low_only or self._row_is_low_confidence(table, row, category_col, reason_col)
                    visible = matches_query and matches_category and matches_confidence
                    table.setRowHidden(row, not visible)
                    if visible:
                        visible_total += 1
            finally:
                table.setUpdatesEnabled(True)
        if tables:
            active_filters = []
            if query:
                active_filters.append("搜索")
            if category_filter:
                active_filters.append("分类")
            if low_only:
                active_filters.append("低置信")
            suffix = f" · {'/'.join(active_filters)}" if active_filters else ""
            self.data_filter_status.setText(f"{len(tables)} 表 · 显示 {visible_total}/{row_total}{suffix}")
        else:
            self.data_filter_status.setText("显示 0/0")

    @staticmethod
    def _make_merged_tab(title1: str, table1: QTableWidget, title2: str, table2: QTableWidget) -> QWidget:
        """Create a tab containing two tables with section headers."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        h1 = QLabel(title1)
        h1.setObjectName("mergedSectionHeader")
        layout.addWidget(h1)
        layout.addWidget(table1, 1)
        h2 = QLabel(title2)
        h2.setObjectName("mergedSectionHeader")
        layout.addWidget(h2)
        layout.addWidget(table2, 1)
        return tab

    def _install_category_menu(self, table: QTableWidget, kind: str) -> None:
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos, current=table, table_kind=kind: self._show_category_menu(current, table_kind, pos))

    def correct_selected_category(self) -> None:
        active = self.tabs.currentWidget()
        targets = [
            (self.web_table, "web"),
            (self.video_table, "video"),
            (self.media_table, "media"),
            (self.window_table, "window"),
        ]
        if active is self.web_tab:
            targets = [(self.web_table, "web")]
        elif active is self.video_tab:
            targets = [(self.video_table, "video")]
        elif active is self.music_tab:
            targets = [(self.media_table, "media")]
        elif active is self.programs_tab:
            targets = [(self.window_table, "window")]
        for table, kind in targets:
            row = table.currentRow()
            if row >= 0 and not table.isRowHidden(row):
                row_rect = table.visualItemRect(table.item(row, 0)) if table.item(row, 0) else table.visualRect(table.model().index(row, 0))
                pos = row_rect.center() if row_rect.isValid() else QPoint(12, 12)
                self._prompt_category_for_row(table, kind, row, pos)
                return
        QMessageBox.information(self, "请选择一行", "请先在网页、播放内容、音乐或窗口表格中选中一条记录。")

    def _show_category_menu(self, table: QTableWidget, kind: str, pos: QPoint) -> None:
        row = table.rowAt(pos.y())
        if row < 0:
            return
        table.selectRow(row)
        self._prompt_category_for_row(table, kind, row, pos)

    def _prompt_category_for_row(self, table: QTableWidget, kind: str, row: int, pos: QPoint | None = None) -> None:
        pattern, target = self._category_rule_source(table, kind, row)
        if not pattern:
            return
        menu = QMenu(self)
        summary = QAction(f"保存范围：{target_label(target)}包含“{pattern}”", self)
        summary.setEnabled(False)
        menu.addAction(summary)
        menu.addSeparator()
        for category in COMMON_CATEGORY_CHOICES:
            action = QAction(f"以后归为：{category}", self)
            action.triggered.connect(lambda _checked=False, cat=category: self._apply_category_correction(table, pattern, target, cat))
            menu.addAction(action)
        menu.addSeparator()
        custom_action = QAction("输入自定义分类...", self)
        custom_action.triggered.connect(lambda: self._prompt_category_correction(table, pattern, target))
        menu.addAction(custom_action)
        menu.exec(table.viewport().mapToGlobal(pos or QPoint(12, 12)))

    def _cell_text(self, table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item else ""

    def _category_rule_source(self, table: QTableWidget, kind: str, row: int) -> tuple[str, str]:
        if kind == "web":
            domain = self._cell_text(table, row, 1).lower()
            title = self._cell_text(table, row, 0).lower()
            if domain and is_generic_content_domain(domain) and title:
                return title[:120], "title"
            return (domain, "domain") if domain else (title[:80], "title")
        if kind == "video":
            domain = self._cell_text(table, row, 2).lower()
            title = self._cell_text(table, row, 0).lower()
            if title and (not domain or is_generic_content_domain(domain)):
                return title[:120], "title"
            return (domain, "domain") if domain else (title[:80], "title")
        if kind == "media":
            source = self._cell_text(table, row, 3).lower()
            title = self._cell_text(table, row, 0).lower()
            if source and source not in {"browser", "browser-extension"}:
                return source, "app"
            return title[:80], "title"
        if kind == "window":
            app = self._cell_text(table, row, 4).lower()
            title = self._cell_text(table, row, 0).lower()
            return (app, "app") if app else (title[:80], "title")
        return "", "any"

    def _apply_category_correction(self, table: QTableWidget, pattern: str, target: str, category: str) -> None:
        try:
            self.storage.add_category_rule(pattern, category, target, update_existing=True)
        except Exception as exc:
            show_operation_error(self, "保存分类规则失败", exc)
            return
        self.refresh()
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_open_dialogs"):
            QTimer.singleShot(0, parent.refresh_open_dialogs)  # type: ignore[attr-defined]
        QMessageBox.information(
            self,
            "分类规则已保存",
            f"已保存规则：{target_label(target)}包含“{pattern}”时归为“{category}”。",
        )

    def _prompt_category_correction(self, table: QTableWidget, pattern: str, target: str) -> None:
        category, ok = QInputDialog.getText(self, "自定义分类", "分类名称：")
        if ok and category.strip():
            self._apply_category_correction(table, pattern, target, category.strip())

    def _duration_cell(self, seconds: float) -> tuple[str, float]:
        return (format_duration(seconds), seconds)

    @staticmethod
    def _kind_label(kinds: str) -> str:
        labels = {
            "web_page": "网页",
            "window_title": "窗口",
            "video_playback": "播放内容",
            "media_playback": "音乐",
            "idle": "空闲",
        }
        values = [labels.get(item.strip(), item.strip()) for item in kinds.split(",") if item.strip()]
        return " / ".join(values) if values else "-"

    def show_data_definitions(self) -> None:
        QMessageBox.information(
            self,
            "数据口径",
            data_definition_text(),
        )

    def _set_rows(self, table: QTableWidget, rows: list[list[object]]) -> None:
        table.setUpdatesEnabled(False)
        table.setSortingEnabled(False)
        try:
            table.clearContents()
            table.setRowCount(len(rows))
            for row_index, row_values in enumerate(rows):
                if row_index and row_index % 250 == 0:
                    QApplication.processEvents()
                for col_index, value in enumerate(row_values):
                    sort_value = None
                    text = value
                    if isinstance(value, tuple) and len(value) == 2:
                        text, sort_value = value
                    item = SortableTableItem(str(text))
                    if sort_value is not None:
                        item.setData(Qt.ItemDataRole.UserRole, sort_value)
                    item.setToolTip(str(text))
                    table.setItem(row_index, col_index, item)
            table.setSortingEnabled(True)
            sort_property = table.property("defaultSortColumn")
            sort_column = -1 if sort_property is None else int(sort_property)
            if sort_column >= 0 and rows:
                table.sortItems(sort_column, Qt.SortOrder.DescendingOrder)
        finally:
            table.setUpdatesEnabled(True)

    def _range_key(self) -> str:
        return str(self.range_combo.currentData())

    @staticmethod
    def _qdate_to_date(value: QDate) -> date:
        return date(value.year(), value.month(), value.day())

    @staticmethod
    def _date_to_qdate(value: date) -> QDate:
        return QDate(value.year, value.month, value.day)

    def _current_date_range(self) -> tuple[date, date]:
        if self._range_key() == "custom":
            start_date = self._qdate_to_date(self.start_date_edit.date())
            end_date = self._qdate_to_date(self.end_date_edit.date())
            if end_date < start_date:
                start_date, end_date = end_date, start_date
            return start_date, end_date
        return self.storage.date_range_for_preset(self._range_key())

    def _sync_custom_date_controls(self) -> None:
        is_custom = self._range_key() == "custom"
        if not is_custom:
            start_date, end_date = self.storage.date_range_for_preset(self._range_key())
            self.start_date_edit.blockSignals(True)
            self.end_date_edit.blockSignals(True)
            self.start_date_edit.setDate(self._date_to_qdate(start_date))
            self.end_date_edit.setDate(self._date_to_qdate(end_date))
            self.start_date_edit.blockSignals(False)
            self.end_date_edit.blockSignals(False)
        self.start_date_edit.setVisible(is_custom)
        self.date_separator_label.setVisible(is_custom)
        self.end_date_edit.setVisible(is_custom)

    def _set_custom_date_range(self, start_date: date, end_date: date) -> None:
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        custom_index = self.range_combo.findData("custom")
        self.range_combo.blockSignals(True)
        if custom_index >= 0:
            self.range_combo.setCurrentIndex(custom_index)
        self.range_combo.blockSignals(False)
        self.start_date_edit.blockSignals(True)
        self.end_date_edit.blockSignals(True)
        self.start_date_edit.setDate(self._date_to_qdate(start_date))
        self.end_date_edit.setDate(self._date_to_qdate(end_date))
        self.start_date_edit.blockSignals(False)
        self.end_date_edit.blockSignals(False)
        self._timeline_loaded_key = ""
        self._sync_custom_date_controls()
        self.refresh()

    def _shift_date_range(self, direction: int) -> None:
        start_date, end_date = self._current_date_range()
        span_days = max(1, (end_date - start_date).days + 1)
        new_start = start_date + timedelta(days=span_days * direction)
        new_end = end_date + timedelta(days=span_days * direction)
        today = date.today()
        if direction > 0 and end_date >= today:
            return
        if new_end > today:
            new_end = today
            new_start = today - timedelta(days=span_days - 1)
        self._set_custom_date_range(new_start, new_end)

    def _jump_to_today_range(self) -> None:
        today_index = self.range_combo.findData("today")
        if today_index >= 0:
            self.range_combo.setCurrentIndex(today_index)

    def _on_range_changed(self) -> None:
        self._timeline_loaded_key = ""
        self._custom_refresh_timer.stop()
        self._sync_custom_date_controls()
        self.refresh()

    def _on_custom_date_changed(self) -> None:
        if self._range_key() != "custom":
            return
        self._timeline_loaded_key = ""
        self._custom_refresh_timer.start()

    def _previous_date_range(self, start_date: date, end_date: date) -> tuple[date, date]:
        span_days = max(1, (end_date - start_date).days + 1)
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=span_days - 1)
        return previous_start, previous_end

    def _date_range_key(self) -> str:
        start_date, end_date = self._current_date_range()
        return (
            f"{start_date.isoformat()}:{end_date.isoformat()}:{self._timeline_limit}:"
            f"{self._timeline_search_text()}:{self._timeline_kind_value()}:"
            f"{self._timeline_sort_value()}:{self._timeline_min_seconds()}"
        )

    def _is_timeline_tab_active(self) -> bool:
        return self.tabs.currentWidget() is self.timeline_tab

    def _on_tab_changed(self, _index: int) -> None:
        self._update_data_tools_for_tab()
        QTimer.singleShot(0, self.refresh)

    def _load_more_timeline(self) -> None:
        self._timeline_limit = min(self._timeline_limit + 200, 5000)
        self._timeline_loaded_key = ""
        self.refresh()

    def _compare_text(self, current: float, previous: float) -> str:
        if previous <= 0:
            return f"{format_duration(current)} / 上期无数据"
        delta = current - previous
        pct = delta / previous * 100.0
        direction = "↑" if delta > 0 else "↓" if delta < 0 else "→"
        return f"{format_duration(current)} {direction} {abs(pct):.0f}%"

    def _hourly_rows(self, timeline_rows: list) -> list[tuple[int, float, float, float, float]]:
        buckets = [[0.0, 0.0, 0.0, 0.0] for _ in range(24)]
        for row in timeline_rows:
            try:
                start = datetime.fromisoformat(str(row["start_time"]))
                hour = max(0, min(23, start.hour))
                seconds = float(row["seconds"] or 0)
            except Exception:
                continue
            kind = str(row["kind"])
            category = str(row["category"])
            try:
                learning_topic = str(row["learning_topic"] or "")
            except (KeyError, IndexError):
                learning_topic = ""
            is_learning = category == "学习" or bool(learning_topic)
            if kind == "video_playback":
                buckets[hour][1] += seconds
            elif kind == "media_playback":
                buckets[hour][2] += seconds
            elif kind != "idle":
                buckets[hour][0] += seconds
            if is_learning:
                buckets[hour][3] += seconds
        return [(hour, values[0], values[1], values[2], values[3]) for hour, values in enumerate(buckets)]

    @staticmethod
    def _delta_text(current: float, previous: float) -> tuple[str, str]:
        if previous > 0:
            pct = (current - previous) / previous * 100
            pct_str = f"{abs(pct):.0f}%"
            if pct > 0:
                return f"↑ {pct_str}", app_color("success")
            elif pct < 0:
                return f"↓ {pct_str}", app_color("danger")
        return "—", "#738196"

    def _on_line_metric_changed(self) -> None:
        if not self._refreshing:
            self.refresh()

    def _on_heatmap_metric_changed(self) -> None:
        if not self._refreshing:
            self.refresh()

    def _keep_refresh_responsive(self) -> None:
        QApplication.processEvents()

    def _show_slow_refresh_hint(self) -> None:
        if self._refreshing:
            self.detail_status.setText("正在加载统计数据...")

    def _set_refresh_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            getattr(self, "refresh_button", None),
            getattr(self, "prev_range_button", None),
            getattr(self, "next_range_button", None),
            getattr(self, "today_range_button", None),
            getattr(self, "range_combo", None),
            getattr(self, "start_date_edit", None),
            getattr(self, "end_date_edit", None),
            getattr(self, "range_picker_button", None),
            getattr(self, "export_button", None),
        ):
            if widget is not None:
                widget.setEnabled(enabled)

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self._slow_refresh_timer.start()
        self._set_refresh_controls_enabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._do_refresh()
            self._update_data_tools_for_tab()
        finally:
            self._slow_refresh_timer.stop()
            QApplication.restoreOverrideCursor()
            self._refreshing = False
            self._set_refresh_controls_enabled(True)
            try:
                self.next_range_button.setEnabled(self._current_date_range()[1] < date.today())
            except Exception:
                pass

    def _do_refresh(self) -> None:
        start_date, end_date = self._current_date_range()
        active_widget = self.tabs.currentWidget()
        active_overview = active_widget is self.overview_tab
        active_programs = active_widget is self.programs_tab
        active_timeline = self._is_timeline_tab_active()
        active_web = active_widget is self.web_tab
        active_video = active_widget is self.video_tab
        active_music = active_widget is self.music_tab
        active_learning = active_widget is self.learning_analysis_tab
        active_category = active_widget is self.category_table
        active_goal = active_widget is self.goal_tab
        previous_start, previous_end = self._previous_date_range(start_date, end_date)
        # ---- All queries (synchronous, compact with indexes) ----
        overview_counts = self.storage.overview_metrics_range(start_date, end_date)
        previous_counts = self.storage.overview_metrics_range(previous_start, previous_end)
        foreground = float(overview_counts["foreground"])
        media = float(overview_counts["media"])
        video = float(overview_counts["video"])
        learning_total = float(overview_counts["learning"])
        prev_foreground = float(previous_counts["foreground"])
        prev_media = float(previous_counts["media"])
        prev_video = float(previous_counts["video"])
        prev_learning = float(previous_counts["learning"])
        learning_topics_count = int(overview_counts["learning_topic_count"])
        self._keep_refresh_responsive()
        process_rows = list(self.storage.process_rows_range(start_date, end_date, limit=120)) if active_programs else []
        web_rows = list(self.storage.content_rows_range(start_date, end_date, kind="web_page", limit=200)) if active_web else []
        vp_rows = list(self.storage.content_rows_range(start_date, end_date, kind="video_playback", limit=200)) if active_video else []
        mp_rows = list(self.storage.music_playback_rows_range(start_date, end_date, limit=200)) if active_music else []
        win_rows = list(self.storage.content_rows_range(start_date, end_date, kind="window_title", limit=200)) if active_programs else []
        cat_rows = list(self.storage.category_summary_range(start_date, end_date)) if active_overview or active_category else []
        hourly_rows = self.storage.hourly_activity_range(start_date, end_date) if active_overview else []
        self._keep_refresh_responsive()
        tl_rows = list(
            self.storage.timeline_rows_range(
                start_date,
                end_date,
                limit=self._timeline_limit,
                query=self._timeline_search_text(),
                kind=self._timeline_kind_value(),
                min_seconds=self._timeline_min_seconds(),
                sort=self._timeline_sort_value(),
            )
        ) if active_timeline else []
        timeline_summary = self.storage.timeline_query_summary_range(
            start_date,
            end_date,
            query=self._timeline_search_text(),
            kind=self._timeline_kind_value(),
            min_seconds=self._timeline_min_seconds(),
        ) if active_timeline else {"count": 0, "seconds": 0.0}
        domain_rows = list(self.storage.domain_summary_range(start_date, end_date, limit=100)) if active_web else []
        vd_rows = list(self.storage.video_domain_summary_range(start_date, end_date, limit=100)) if active_video else []
        music_analysis = self.storage.music_analysis_range(start_date, end_date, limit=200) if active_music else []
        artist_data = self.storage.artist_summary_range(start_date, end_date, limit=80) if active_music else []
        learning_data = self.storage.learning_topic_summary_range(start_date, end_date, limit=200) if active_learning else []
        goal_progress = self.storage.goal_progress_range(start_date, end_date) if active_goal else []
        goal_streaks = {str(g["goal"]["name"]): self.storage.goal_streak(str(g["goal"]["name"])) for g in goal_progress}
        self._keep_refresh_responsive()

        # ---- Top totals ----
        self.foreground_total.setText(f"前台注视 {format_duration(foreground)}")
        self.video_total.setText(f"播放内容 {format_duration(video)}")
        self.media_total.setText(f"音乐播放 {format_duration(media)}")
        self.learning_total.setText(f"学习 {format_duration(learning_total)}")
        self.detail_status.setText(
            f"{start_date.isoformat()} ~ {end_date.isoformat()} · "
            f"程序 {int(overview_counts['program_count'])} · "
            f"网页 {int(overview_counts['web_count'])} · "
            f"播放 {int(overview_counts['video_count'])} · "
            f"分类 {int(overview_counts['category_count'])}"
        )
        span_days = max(1, (end_date - start_date).days + 1)
        self.range_summary_label.setText(
            f"当前范围：{start_date.isoformat()} ~ {end_date.isoformat()}（{span_days} 天） · "
            f"上一周期：{previous_start.isoformat()} ~ {previous_end.isoformat()} · "
            "时间、导出和图表均按当前范围计算"
        )
        self.next_range_button.setEnabled(end_date < date.today())
        self.compare_label.setText(
            "对比上一周期 "
            f"{previous_start.isoformat()} ~ {previous_end.isoformat()}："
            f"前台 {self._compare_text(foreground, prev_foreground)} · "
            f"学习 {self._compare_text(learning_total, prev_learning)} · "
            f"播放 {self._compare_text(video, prev_video)} · "
            f"音乐 {self._compare_text(media, prev_media)}"
        )

        # ---- Overview cards ----
        web_total = float(overview_counts["web_attention"])
        web_domains = int(overview_counts["web_domain_count"])
        self.focus_card.set_data(foreground, f"{int(overview_counts['program_count'])} 个程序")
        self.web_card.set_data(web_total, f"{web_domains} 个域名")
        self.video_card.set_data(video, f"{int(overview_counts['video_count'])} 条播放内容")
        self.music_card.set_data(media, f"{int(overview_counts['music_count'])} 首歌曲/媒体")
        self.learning_today_card.set_data(learning_total, f"{learning_topics_count} 个主题")

        # ---- Charts ----
        if active_overview:
            try:
                self.category_chart.set_data([
                    (str(r["category"]), float(r["attention_seconds"] or 0), float(r["background_seconds"] or 0))
                    for r in cat_rows
                ])
            except Exception:
                pass
            try:
                self.hourly_chart.set_data(hourly_rows)
            except Exception:
                pass

        # ---- Tables ----
        if active_programs:
            self._set_rows(self.process_table, [[
                str(r["exe_name"]),
                self._duration_cell(float(r["foreground_seconds"] or 0)),
                self._duration_cell(float(r["running_seconds"] or 0)),
                self._duration_cell(max(0.0, float(r["running_seconds"] or 0) - float(r["foreground_seconds"] or 0))),
                str(r["exe_path"]),
            ] for r in process_rows])

            self._set_rows(self.window_table, [[
                str(r["content_title"]), str(r["category"]),
                self.storage.category_explanation(str(r["category"]), str(r["exe_name"]), str(r["content_domain"]), str(r["content_title"]), str(r["learning_topic"] or "")),
                str(r["learning_topic"] or "-"), str(r["exe_name"]),
                self._duration_cell(float(r["attention_seconds"] or 0)), str(r["last_seen"]),
            ] for r in win_rows])

        if active_web:
            self._set_rows(self.web_table, [[
                str(r["content_title"]), str(r["content_domain"]), str(r["category"]),
                self.storage.category_explanation(str(r["category"]), str(r["exe_name"]), str(r["content_domain"]), str(r["content_title"]), str(r["learning_topic"] or "")),
                str(r["learning_topic"] or "-"),
                str(r["exe_name"]), self._duration_cell(float(r["attention_seconds"] or 0)),
                str(r["content_url"]),
            ] for r in web_rows])

        if active_video:
            self._set_rows(self.video_table, [[
                str(r["content_title"]), "视频播放", str(r["content_domain"]), str(r["category"]),
                self.storage.category_explanation(str(r["category"]), str(r["exe_name"]), str(r["content_domain"]), str(r["content_title"]), str(r["learning_topic"] or "")),
                str(r["learning_topic"] or "-"),
                self._duration_cell(float(r["background_seconds"] or 0)), str(r["content_url"]),
            ] for r in vp_rows])

        if active_music:
            self._set_rows(self.media_table, [[
                str(r["content_title"]), str(r["category"]),
                self.storage.category_explanation(str(r["category"]), str(r["exe_name"]), str(r["content_domain"]), str(r["content_title"]), str(r["learning_topic"] or "")),
                str(r["exe_name"]),
                self._duration_cell(float(r["background_seconds"] or 0)), str(r["last_seen"]),
            ] for r in mp_rows])

        if active_category:
            category_total = sum(float(r["total_seconds"] or 0) for r in cat_rows)
            self._set_rows(self.category_table, [[
                str(r["category"]),
                self._duration_cell(float(r["total_seconds"] or 0)),
                (f"{(float(r['total_seconds'] or 0) / category_total * 100):.1f}%" if category_total > 0 else "0.0%", float(r["total_seconds"] or 0)),
                self._duration_cell(float(r["attention_seconds"] or 0)),
                self._duration_cell(float(r["background_seconds"] or 0)),
                str(r["item_count"]),
                self._kind_label(str(r["kinds"] or "")),
                str(r["last_seen"] or ""),
            ] for r in cat_rows])

        # ---- Domain tables ----
        if active_web:
            self._set_rows(self.domain_table, [[
                str(r["content_domain"]).replace("（无域名 - 需安装浏览器扩展）|", ""),
                self._duration_cell(float(r["attention_seconds"] or 0)),
                str(r["page_count"]),
                " / ".join((str(r["top_titles"] or "").split(","))[:3]) or "-",
                str(r["last_seen"]),
            ] for r in domain_rows])

        if active_video:
            self._set_rows(self.video_domain_table, [[
                str(r["content_domain"]).replace("（无域名 - 需安装浏览器扩展）|", ""),
                self._duration_cell(float(r["total_seconds"] or 0)),
                str(r["video_count"]),
                " / ".join((str(r["top_titles"] or "").split(","))[:3]) or "-",
                str(r["category"]), str(r["last_seen"]),
            ] for r in vd_rows])

        # ---- Music analysis ----
        if active_music:
            ma_rows = [[
                str(r["song"]), str(r["artist"]),
                " / ".join(str(s) for s in r["sources"])[:80],
                self._duration_cell(float(r["seconds"])),
                (f"{float(r['percent']):.1f}%", float(r["percent"])),
                str(r["last_seen"]),
            ] for r in music_analysis]
            self._set_rows(self.music_analysis_table, ma_rows)
            self.music_analysis_total.set_data(media, f"{int(overview_counts['music_count'])} 首歌曲/媒体")
            self.music_analysis_count.set_data(str(len(ma_rows)), "按歌曲+歌手去重")
            if ma_rows:
                self.music_analysis_top.set_data(str(ma_rows[0][0])[:18], str(ma_rows[0][1])[:24])

            # ---- Artist analysis ----
            ar_rows = [[
                str(r["artist"]), self._duration_cell(float(r["seconds"])),
                str(r["song_count"]), str(r["top_songs"])[:60],
                str(r["sources"])[:60], (f"{float(r['percent']):.1f}%", float(r["percent"])),
            ] for r in artist_data]
            self._set_rows(self.artist_analysis_table, ar_rows)

        # ---- Learning analysis ----
        if active_learning:
            lr_rows = [[
                str(r["learning_topic"]),
                self._duration_cell(float(r["attention_seconds"] or 0)),
                self._duration_cell(float(r["background_seconds"] or 0)),
                self._duration_cell(float(r["total_seconds"] or 0)),
                str(r["item_count"]), str(r["last_seen"]),
            ] for r in learning_data]
            self._set_rows(self.learning_analysis_table, lr_rows)
            self.learning_analysis_total.set_data(learning_total, f"{len(learning_data)} 个主题")

        # ---- Goals ----
        if active_goal:
            goal_rows = []
            goal_colors = []
            streak_parts = []
            done_count = 0
            close_count = 0
            missed_count = 0
            for item in goal_progress:
                g = item["goal"]
                val, target = float(item["value"]), float(item["target"])
                ok = bool(item["ok"])
                ratio = val / target if target > 0 else 0
                if ok:
                    st, color = "达标", app_color("success")
                    done_count += 1
                elif ratio >= 0.7:
                    st, color = "接近", app_color("warning")
                    close_count += 1
                else:
                    st, color = "未达标", app_color("danger")
                    missed_count += 1
                goal_rows.append([
                    str(g["name"]), "至少" if g["direction"] == "min" else "不超过",
                    self._duration_cell(val), self._duration_cell(target), st,
                ])
                goal_colors.append(color)
                streak = goal_streaks.get(str(g["name"]), 0)
                if streak > 0:
                    streak_parts.append(f"{g['name']} {streak} 天")
            self._set_rows(self.goal_table, goal_rows)
            self.goal_done_card.set_data(str(done_count), f"{len(goal_progress)} 个启用目标")
            self.goal_close_card.set_data(str(close_count), "70% 以上")
            self.goal_missed_card.set_data(str(missed_count), "需要关注")
            if hasattr(self, "goal_hint_label"):
                self.goal_hint_label.setText(
                    f"当前范围共有 {len(goal_progress)} 个启用目标：达标 {done_count} 个，接近 {close_count} 个，未达标 {missed_count} 个。"
                )
            for i, c in enumerate(goal_colors):
                item = self.goal_table.item(i, 4)
                if item:
                    item.setForeground(QColor(c))
            if streak_parts:
                self.streak_label.setText(" + ".join(streak_parts))
                self.streak_label.setVisible(True)
            else:
                self.streak_label.setVisible(False)

        # ---- Timeline: lazy-loaded because large event tables can freeze QTableWidget.
        if active_timeline:
            tl_table_rows = [[
                str(r["start_time"]), self._kind_label(str(r["kind"])), str(r["title"]),
                str(r["app_name"]), str(r["category"]),
                str(r["learning_topic"] or "-"),
                self._duration_cell(float(r["seconds"] or 0)),
            ] for r in tl_rows]
            self._set_rows(self.timeline_table, tl_table_rows)
            self._timeline_loaded_key = self._date_range_key()
            total_matches = int(timeline_summary.get("count", 0))
            total_seconds = float(timeline_summary.get("seconds", 0.0))
            filter_parts = []
            if self._timeline_search_text():
                filter_parts.append(f"关键词“{self._timeline_search_text()}”")
            if self._timeline_kind_value():
                filter_parts.append(str(self.timeline_kind_filter.currentText()))
            if self._timeline_min_seconds() > 0:
                filter_parts.append(f"≥{int(self._timeline_min_seconds() / 60)}分钟")
            filter_text = f" · {' / '.join(filter_parts)}" if filter_parts else ""
            more_text = "可继续加载更多" if len(tl_rows) < total_matches else "已显示全部匹配记录"
            self.timeline_hint.setText(
                f"查询命中 {total_matches} 条 · 合计 {format_duration(total_seconds)} · "
                f"已显示 {len(tl_rows)} 条 · 上限 {self._timeline_limit}{filter_text} · {more_text}"
            )
            self.timeline_more_button.setEnabled(len(tl_rows) < total_matches and self._timeline_limit < 5000)
            self._update_timeline_detail()
        elif self.timeline_table.rowCount() == 0:
            self.timeline_hint.setText("时间线按需加载：切换到本页后才查询最近事件，避免详情刷新时卡住。")

        # ---- Deferred charts: only render while the visual tabs are relevant.
        if self.tabs.currentWidget() in {self.overview_tab, self.trend_tab}:
            QTimer.singleShot(100, self, lambda: self._render_heatmap_if_alive(start_date, end_date))

    def _render_heatmap_if_alive(self, start_date, end_date) -> None:
        if not self.isVisible():
            return
        if self.tabs.currentWidget() not in {self.overview_tab, self.trend_tab}:
            return
        self._render_heatmap(start_date, end_date)

    def _render_heatmap(self, start_date, end_date) -> None:
        """Deferred: heavy heatmap + week comparison charts."""
        try:
            if hasattr(self, "line_chart"):
                metric_map = {"前台注视": "foreground", "视频播放": "video", "音乐播放": "music", "学习": "learning"}
                lm = metric_map.get(str(self.line_metric_combo.currentText()), "foreground")
                lbl = str(self.line_metric_combo.currentText())
                breakdown = self.storage.week_daily_breakdown(lm)
                self.line_chart.set_data(breakdown["this_week"], breakdown["last_week"], lbl)
        except Exception as exc:
            log_event(f"折线图渲染失败: {type(exc).__name__}: {exc}")
        try:
            if hasattr(self, "heatmap"):
                metric_map = {"前台注视": "foreground", "视频播放": "video", "音乐播放": "music", "学习": "learning"}
                hm = metric_map.get(str(self.heatmap_metric_combo.currentText()), "learning")
                raw = self.storage.daily_heatmap_range(*self.storage.date_range_for_preset("84d"))
                hm_lbl = str(self.heatmap_metric_combo.currentText())
                if hm == "foreground":
                    hrows = [(d, fg) for d, fg, _, _, _ in raw]
                elif hm == "video":
                    hrows = [(d, vid) for d, _, vid, _, _ in raw]
                elif hm == "music":
                    hrows = [(d, mus) for d, _, _, mus, _ in raw]
                else:
                    hrows = [(d, lrn) for d, _, _, _, lrn in raw]
                self.heatmap.set_data(hrows, hm_lbl)
        except Exception as exc:
            log_event(f"热力图渲染失败: {type(exc).__name__}: {exc}")

    def _export_with_error_message(self, path: str, action) -> None:
        try:
            action()
        except Exception as exc:
            show_operation_error(self, "导出失败", exc)
            return
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")

    def export_report(self) -> None:
        start_date, end_date = self._current_date_range()
        default_name = f"usage-widget-report-{start_date.isoformat()}-{end_date.isoformat()}.html"
        path, _ = QFileDialog.getSaveFileName(self, "导出 HTML 报告", default_name, "HTML Files (*.html)")
        if not path:
            return
        self._export_with_error_message(path, lambda: self.storage.export_html_report(Path(path), start_date, end_date))

    def export_music_csv(self) -> None:
        start_date, end_date = self._current_date_range()
        default_name = f"usage-widget-music-{start_date.isoformat()}-{end_date.isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出音乐分析 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self._export_with_error_message(path, lambda: self.storage.export_music_csv(Path(path), start_date, end_date))

    def export_learning_csv(self) -> None:
        start_date, end_date = self._current_date_range()
        default_name = f"usage-widget-learning-{start_date.isoformat()}-{end_date.isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出学习分析 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self._export_with_error_message(path, lambda: self.storage.export_learning_csv(Path(path), start_date, end_date))


class UsageWidgetWindow(QWidget):
    def __init__(self, storage: Storage, monitor: ProcessMonitor) -> None:
        super().__init__()
        self.storage = storage
        self.monitor = monitor
        self.settings = self.storage.load_settings()
        self.icon_provider = QFileIconProvider()
        self.icon_cache: dict[str, QIcon] = {}
        self.rows: list[ProcessRow] = []
        self.drag_pos: QPoint | None = None
        self.drag_start_pos: QPoint | None = None
        self.drag_moved = False
        self.is_collapsed = not self.settings.always_expanded
        self._pointer_inside = False
        self.settings_dialog: SettingsDialog | None = None
        self.stats_dialog: StatsDialog | None = None
        self.diagnostics_dialog: DiagnosticsDialog | None = None
        self.status_dialog: CurrentStatusDialog | None = None
        self._last_stats_refresh = 0.0
        self._last_widget_refresh = 0.0
        self._last_saved_pos: tuple[int, int] | None = None
        self._footer_cache_at = 0.0
        self._footer_cache_text = "当前运行 · 当前优先，其余按今日前台时长降序"
        self._collapsed_media_cache_at = -float("inf")
        self._collapsed_media_cache: tuple[str, str] = ("音乐", "暂无正在播放的音乐")
        self._position_save_timer = QTimer(self)
        self._position_save_timer.setSingleShot(True)
        self._position_save_timer.timeout.connect(self.save_position)
        self._hover_expand_timer = QTimer(self)
        self._hover_expand_timer.setSingleShot(True)
        self._hover_expand_timer.timeout.connect(self._expand_from_hover)
        self._hover_collapse_timer = QTimer(self)
        self._hover_collapse_timer.setSingleShot(True)
        self._hover_collapse_timer.timeout.connect(self._collapse_from_hover)
        self._resize_animation = QPropertyAnimation(self, b"geometry", self)
        self._resize_animation.setDuration(140)
        self._resize_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._target_fixed_size: QSize | None = None
        self._resize_animation.finished.connect(self._finish_resize_animation)

        self.setWindowTitle(f"UsageWidget v{__version__}")
        self.setWindowIcon(build_app_icon())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._build_ui()
        self._build_tray()
        self._install_shortcuts()
        self.apply_settings()
        self.restore_position()

        self.monitor.updated.connect(self.refresh)

    def _install_shortcuts(self) -> None:
        self._shortcuts = [
            QShortcut(QKeySequence("Ctrl+,"), self, activated=self.open_settings),
            QShortcut(QKeySequence("Ctrl+F"), self, activated=self.open_stats_search),
            QShortcut(QKeySequence("Ctrl+D"), self, activated=self.open_stats_today),
        ]

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self.shell = QFrame()
        self.shell.setObjectName("shell")
        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(10, 10, 10, 10)
        shell_layout.setSpacing(8)
        outer_layout.addWidget(self.shell)

        self.collapsed_bar = QFrame()
        self.collapsed_bar.setObjectName("collapsedBar")
        collapsed_layout = QHBoxLayout(self.collapsed_bar)
        collapsed_layout.setContentsMargins(14, 12, 14, 12)
        collapsed_layout.setSpacing(11)
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setProperty("state", "active")
        self.status_dot.setFixedSize(18, 18)
        self.status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_box = QVBoxLayout()
        status_box.setContentsMargins(0, 5, 0, 0)
        status_box.setSpacing(0)
        status_box.addWidget(self.status_dot)
        status_box.addStretch(1)
        self.collapsed_state = QLabel("活动中")
        self.collapsed_state.setObjectName("collapsedState")
        self.collapsed_state.setProperty("state", "active")
        self.collapsed_activity_badge = QLabel("")
        self.collapsed_activity_badge.setObjectName("collapsedActivityBadge")
        self.collapsed_activity_badge.setVisible(False)
        self.collapsed_total = QLabel("今日前台 0s")
        self.collapsed_total.setObjectName("collapsedTotal")
        self.collapsed_music = QLabel("暂无正在播放的音乐")
        self.collapsed_music.setObjectName("collapsedMusic")
        self.collapsed_music.setWordWrap(False)
        self.collapsed_music.setMinimumWidth(0)
        self.collapsed_total.setMinimumWidth(0)
        self.collapsed_activity_badge.setMinimumWidth(0)
        collapsed_text = QVBoxLayout()
        collapsed_text.setContentsMargins(0, 0, 0, 0)
        collapsed_text.setSpacing(4)
        collapsed_header = QHBoxLayout()
        collapsed_header.setContentsMargins(0, 0, 0, 0)
        collapsed_header.setSpacing(7)
        collapsed_header.addWidget(self.collapsed_state)
        collapsed_header.addWidget(self.collapsed_activity_badge)
        collapsed_header.addWidget(self.collapsed_total, 1)
        collapsed_metrics = QHBoxLayout()
        collapsed_metrics.setContentsMargins(0, 0, 0, 0)
        collapsed_metrics.setSpacing(6)
        self.collapsed_focus_metric = self._make_collapsed_metric(collapsed_metrics, "前台 0s")
        self.collapsed_video_metric = self._make_collapsed_metric(collapsed_metrics, "视频 0s")
        self.collapsed_music_metric = self._make_collapsed_metric(collapsed_metrics, "音乐 0s")
        self.collapsed_learning_metric = self._make_collapsed_metric(collapsed_metrics, "学习 0s")
        collapsed_text.addLayout(collapsed_header)
        collapsed_text.addLayout(collapsed_metrics)
        collapsed_text.addWidget(self.collapsed_music)
        collapsed_layout.addLayout(status_box)
        collapsed_layout.addLayout(collapsed_text, 1)
        self.collapsed_drag_handle = QLabel("||")
        self.collapsed_drag_handle.setObjectName("collapsedDragHandle")
        self.collapsed_drag_handle.setToolTip("拖动缩小窗口")
        self.collapsed_drag_handle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.collapsed_drag_handle.setFixedWidth(24)
        self.collapsed_drag_handle.setCursor(Qt.CursorShape.SizeAllCursor)
        collapsed_layout.addWidget(self.collapsed_drag_handle)
        shell_layout.addWidget(self.collapsed_bar)

        self.full_panel = QFrame()
        self.full_panel.setObjectName("fullPanel")
        panel_layout = QVBoxLayout(self.full_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(8)
        shell_layout.addWidget(self.full_panel, 1)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 2, 0)
        header_layout.setSpacing(6)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        self.title_label = QLabel("使用焦点")
        self.title_label.setObjectName("titleLabel")
        self.total_label = QLabel("今日 0s")
        self.total_label.setObjectName("totalLabel")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.total_label)
        header_layout.addLayout(title_box, 1)

        self.top_sort_combo = QComboBox()
        self.top_sort_combo.setObjectName("topSortCombo")
        self.top_sort_combo.setToolTip("当前运行列表排序方式")
        self.top_sort_combo.addItem("当前优先", "current_first")
        self.top_sort_combo.addItem("前台排行", "foreground")
        self.top_sort_combo.addItem("运行排行", "running")
        self.top_sort_combo.addItem("按名称", "name")
        self.top_sort_combo.setFixedWidth(112)
        sort_index = self.top_sort_combo.findData(self.settings.top_list_sort)
        self.top_sort_combo.setCurrentIndex(sort_index if sort_index >= 0 else 0)
        self.top_sort_combo.currentIndexChanged.connect(self.change_top_list_sort)

        self.collapse_button = self._make_header_button("⌖", "固定展开")
        self.collapse_button.clicked.connect(self.toggle_pin_mode)
        self.status_button = self._make_header_button("ℹ", "当前状态")
        self.status_button.clicked.connect(self.open_status_center)
        self.stats_button = self._make_header_button("▥", "数据详情")
        self.stats_button.clicked.connect(self.open_stats)
        self.settings_button = self._make_header_button("⚙", "设置")
        self.settings_button.clicked.connect(self.open_settings)
        header_layout.addWidget(self.collapse_button)
        header_layout.addWidget(self.status_button)
        header_layout.addWidget(self.stats_button)
        header_layout.addWidget(self.settings_button)
        panel_layout.addWidget(header)

        summary = QFrame()
        summary.setObjectName("summaryStrip")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(4, 4, 4, 4)
        summary_layout.setSpacing(6)
        self.focus_value_label = self._make_summary_metric(summary_layout, "前台")
        self.video_value_label = self._make_summary_metric(summary_layout, "视频")
        self.music_value_label = self._make_summary_metric(summary_layout, "音乐")
        self.learning_value_label = self._make_summary_metric(summary_layout, "学习")
        panel_layout.addWidget(summary)

        self.learning_summary_label = QLabel("")
        self.learning_summary_label.setObjectName("learningSummary")
        self.learning_summary_label.setWordWrap(True)
        self.learning_summary_label.setVisible(False)
        panel_layout.addWidget(self.learning_summary_label)

        self.goal_strip = QLabel("")
        self.goal_strip.setObjectName("goalStrip")
        self.goal_strip.setWordWrap(True)
        self.goal_strip.setVisible(False)
        panel_layout.addWidget(self.goal_strip)

        sort_strip = QFrame()
        sort_strip.setObjectName("sortStrip")
        sort_layout = QHBoxLayout(sort_strip)
        sort_layout.setContentsMargins(8, 5, 8, 5)
        sort_layout.setSpacing(8)
        sort_label = QLabel("列表")
        sort_label.setObjectName("sortLabel")
        self.sort_hint_label = QLabel(self._top_list_sort_label())
        self.sort_hint_label.setObjectName("sortHint")
        self.sort_hint_label.setMinimumWidth(0)
        self.sort_hint_label.setWordWrap(False)
        sort_layout.addWidget(sort_label)
        sort_layout.addWidget(self.top_sort_combo)
        sort_layout.addWidget(self.sort_hint_label, 1)
        panel_layout.addWidget(sort_strip)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setObjectName("processScroll")
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        for _ in range(5):
            row = ProcessRow()
            self.rows.append(row)
            self.list_layout.addWidget(row)
        self.empty_label = QLabel("暂无可显示的运行程序")
        self.empty_label.setObjectName("emptyLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_layout.addWidget(self.empty_label, 1)
        self.scroll.setWidget(self.list_widget)
        panel_layout.addWidget(self.scroll, 1)

        self.footer_label = QLabel("当前运行 · 当前优先，其余按今日前台时长降序")
        self.footer_label.setObjectName("footerLabel")
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(self.footer_label)

        self._collapsed_click_widgets = {
            self.collapsed_bar,
            self.collapsed_total,
            self.collapsed_activity_badge,
            self.collapsed_focus_metric,
            self.collapsed_video_metric,
            self.collapsed_music_metric,
            self.collapsed_learning_metric,
            self.collapsed_music,
        }
        self._status_click_widgets = {self.status_dot, self.collapsed_state}
        self._collapsed_drag_widgets = {self.collapsed_drag_handle}
        for widget in (
            self.shell,
            self.collapsed_bar,
            self.status_dot,
            self.collapsed_state,
            self.collapsed_activity_badge,
            self.collapsed_total,
            self.collapsed_focus_metric,
            self.collapsed_video_metric,
            self.collapsed_music_metric,
            self.collapsed_learning_metric,
            self.collapsed_music,
            self.collapsed_drag_handle,
            header,
            summary,
            sort_strip,
            self.title_label,
            self.total_label,
            self.footer_label,
        ):
            widget.installEventFilter(self)

    def _make_header_button(self, text: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(38, 30)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _make_collapsed_metric(self, parent_layout: QHBoxLayout, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("collapsedMetric")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumWidth(0)
        parent_layout.addWidget(label, 1)
        return label

    def _make_summary_metric(self, parent_layout: QHBoxLayout, title: str) -> QLabel:
        box = QFrame()
        box.setObjectName("metricBox")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(0)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label = QLabel("0s")
        value_label.setObjectName("metricValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        parent_layout.addWidget(box, 1)
        return value_label

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(build_app_icon(), self)
        self.tray.setToolTip(f"UsageWidget v{__version__}")
        menu = QMenu()
        self.show_action = QAction("隐藏小组件", self)
        self.show_action.triggered.connect(self.toggle_visible)
        status_action = QAction("当前状态", self)
        status_action.triggered.connect(self.open_status_center)
        stats_action = QAction("数据详情", self)
        stats_action.triggered.connect(self.open_stats)
        diagnostics_action = QAction("运行诊断", self)
        diagnostics_action.triggered.connect(self.open_diagnostics)
        self.pause_action = QAction("暂停记录", self)
        self.pause_action.triggered.connect(self.toggle_pause_tracking)
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.open_settings)
        export_action = QAction("导出 CSV", self)
        export_action.triggered.connect(self.export_csv)
        export_content_action = QAction("导出内容 CSV", self)
        export_content_action.triggered.connect(self.export_content_csv)
        summary_action = QAction("查看今日摘要", self)
        summary_action.triggered.connect(self.show_daily_summary)
        self.background_action = QAction("后台运行（仅托盘）", self)
        self.background_action.setCheckable(True)
        self.background_action.triggered.connect(self.toggle_background_mode)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(self.show_action)
        menu.addAction(status_action)
        menu.addAction(stats_action)
        menu.addAction(diagnostics_action)
        menu.addAction(self.pause_action)
        menu.addAction(settings_action)
        menu.addAction(export_action)
        menu.addAction(export_content_action)
        menu.addAction(summary_action)
        menu.addAction(self.background_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()
        self._sync_tray_actions()

    def _sync_tray_actions(self, visible: bool | None = None) -> None:
        is_visible = self.isVisible() if visible is None else visible
        if hasattr(self, "show_action"):
            self.show_action.setText("隐藏小组件" if is_visible else "显示小组件")
        if hasattr(self, "pause_action"):
            self.pause_action.setText("恢复记录" if self.storage.load_settings().pause_tracking else "暂停记录")
        if hasattr(self, "background_action"):
            self.background_action.blockSignals(True)
            self.background_action.setChecked(not is_visible)
            self.background_action.blockSignals(False)

    def _prepare_hide_to_tray(self) -> None:
        self._hover_expand_timer.stop()
        self._hover_collapse_timer.stop()
        self.drag_pos = None
        self.drag_start_pos = None
        self.drag_moved = False
        if not self.settings.always_expanded:
            self.set_expanded(False)
        self.hide()
        self._sync_tray_actions(False)

    def _show_from_tray(self) -> None:
        self._pointer_inside = False
        if not self.settings.always_expanded:
            self.set_expanded(False)
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.keep_on_screen()
        self.raise_()
        self.activateWindow()
        self._last_widget_refresh = 0.0
        self.refresh()
        self._sync_tray_actions(True)

    def check_daily_summary(self) -> None:
        settings = self.storage.load_settings()
        today_str = date.today().isoformat()
        if settings.last_summary_date == today_str:
            return
        yesterday = date.today() - timedelta(days=1)
        for item in self.storage.goal_progress_range(yesterday, yesterday):
            goal_name = str(item["goal"]["name"])
            self.storage.save_goal_streak(goal_name, yesterday, bool(item["ok"]))
        if settings.daily_summary:
            summary = self.storage.compose_daily_summary()
            if summary:
                self.tray.showMessage("UsageWidget 每日摘要", summary, build_app_icon(), 8000)
        self.storage.save_settings(replace(settings, last_summary_date=today_str))

    def show_daily_summary(self) -> None:
        summary = self.storage.compose_daily_summary()
        if summary:
            self.tray.showMessage("UsageWidget 今日摘要", summary, build_app_icon(), 8000)
        else:
            self.tray.showMessage("UsageWidget", "暂无昨日数据，摘要不可用。", build_app_icon(), 3000)

    def restore_position(self) -> None:
        if self.settings.pos_x is not None and self.settings.pos_y is not None:
            self.move(self.settings.pos_x, self.settings.pos_y)
            self.keep_on_screen()
            self._last_saved_pos = (self.pos().x(), self.pos().y())
            return
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - FULL_SIZE[0] - 24, geo.top() + 80)
        self.keep_on_screen()
        self._last_saved_pos = (self.pos().x(), self.pos().y())

    def _clamped_position(self, pos: QPoint) -> QPoint:
        center = pos + QPoint(max(1, self.width() // 2), max(1, self.height() // 2))
        screen = QApplication.screenAt(center) or QApplication.screenAt(self.pos()) or QApplication.primaryScreen()
        if not screen:
            return pos
        geo = screen.availableGeometry()
        margin = 8
        max_x = max(geo.left() + margin, geo.right() - self.width() + 1 - margin)
        max_y = max(geo.top() + margin, geo.bottom() - self.height() + 1 - margin)
        x = min(max(pos.x(), geo.left() + margin), max_x)
        y = min(max(pos.y(), geo.top() + margin), max_y)
        return QPoint(x, y)

    def keep_on_screen(self) -> None:
        clamped = self._clamped_position(self.pos())
        if clamped != self.pos():
            self.move(clamped)

    def apply_settings(self) -> None:
        self.settings = self.storage.load_settings()
        dark = is_dark_theme(self.settings)
        self.setWindowOpacity(self.settings.window_opacity)
        self._apply_styles(dark)
        sort_index = self.top_sort_combo.findData(self._top_list_sort_mode())
        if sort_index >= 0 and self.top_sort_combo.currentIndex() != sort_index:
            self.top_sort_combo.blockSignals(True)
            self.top_sort_combo.setCurrentIndex(sort_index)
            self.top_sort_combo.blockSignals(False)
        self._sync_sort_hint()
        self.set_expanded(self.settings.always_expanded or (self._pointer_inside and not self.is_collapsed))
        apply_windows_backdrop(self, dark)
        self._sync_tray_actions()

    def _apply_styles(self, dark: bool) -> None:
        alpha = self.settings.background_alpha
        if dark:
            bg = f"rgba(22, 26, 32, {alpha})"
            panel = "rgba(255, 255, 255, 34)"
            panel_hover = "rgba(255, 255, 255, 54)"
            border = "rgba(255, 255, 255, 124)"
            row_border = "rgba(255, 255, 255, 92)"
            text = "#f5f7fb"
            muted = "#c4cedd"
            accent = app_color("success")
            idle = app_color("warning")
            paused = app_color("danger")
        else:
            bg = f"rgba(248, 250, 252, {alpha})"
            panel = "rgba(255, 255, 255, 150)"
            panel_hover = "rgba(232, 241, 252, 180)"
            border = "rgba(110, 128, 150, 72)"
            row_border = "transparent"
            text = "#162033"
            muted = "#607089"
            accent = app_color("focus")
            idle = "#d98b10"
            paused = app_color("danger")

        self.setStyleSheet(
            f"""
            QFrame#shell {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 18px;
            }}
            QFrame#collapsedBar {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QFrame#fullPanel {{
                background: transparent;
                border: none;
            }}
            QFrame#summaryStrip {{
                background: transparent;
                border: none;
            }}
            QFrame#sortStrip {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QFrame#metricBox {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QLabel {{
                color: {text};
                letter-spacing: 0px;
                font-family: {ui_font_stack()};
            }}
            QLabel#titleLabel {{
                font-size: 18px;
                font-weight: 700;
            }}
            QLabel#totalLabel, QLabel#footerLabel, QLabel#processPath {{
                color: {muted};
                font-size: 11px;
            }}
            QLabel#metricTitle {{
                color: {muted};
                font-size: 10px;
            }}
            QLabel#metricValue {{
                color: {text};
                font-size: 12px;
                font-weight: 750;
            }}
            QLabel#sortLabel {{
                color: {muted};
                font-size: 11px;
                font-weight: 700;
            }}
            QLabel#sortHint {{
                color: {muted};
                font-size: 11px;
            }}
            QLabel#collapsedTotal {{
                color: {muted};
                font-size: 12px;
                font-weight: 650;
            }}
            QLabel#collapsedState {{
                color: white;
                font-size: 12px;
                font-weight: 800;
                background: {accent};
                border: 1px solid transparent;
                border-radius: 9px;
                padding: 3px 8px;
            }}
            QLabel#collapsedState[state="idle"] {{
                background: {idle};
            }}
            QLabel#collapsedState[state="paused"] {{
                background: {paused};
            }}
            QLabel#collapsedActivityBadge {{
                color: white;
                font-size: 11px;
                font-weight: 800;
                background: {accent};
                border: 1px solid transparent;
                border-radius: 9px;
                padding: 3px 8px;
            }}
            QLabel#collapsedActivityBadge[category="学习"] {{
                background: {category_color("学习")};
            }}
            QLabel#collapsedActivityBadge[category="编程"] {{
                background: {category_color("编程")};
            }}
            QLabel#collapsedActivityBadge[category="视频"] {{
                background: {category_color("视频")};
            }}
            QLabel#collapsedActivityBadge[category="音乐"] {{
                background: {category_color("音乐")};
            }}
            QLabel#collapsedActivityBadge[category="游戏"] {{
                background: {category_color("游戏")};
            }}
            QLabel#collapsedActivityBadge[category="聊天"] {{
                background: {category_color("聊天")};
            }}
            QLabel#collapsedActivityBadge[category="AI 工具"] {{
                background: {category_color("AI 工具")};
            }}
            QLabel#collapsedActivityBadge[category="娱乐"] {{
                background: {category_color("娱乐")};
            }}
            QLabel#collapsedActivityBadge[category="购物"] {{
                background: {category_color("购物")};
            }}
            QLabel#collapsedActivityBadge[category="新闻"] {{
                background: {category_color("新闻")};
            }}
            QLabel#collapsedMetric {{
                color: {text};
                font-size: 11px;
                font-weight: 700;
                background: {panel_hover};
                border: 1px solid {border};
                border-radius: 7px;
                padding: 3px 6px;
            }}
            QLabel#collapsedMusic {{
                color: {text};
                font-size: 15px;
                font-weight: 800;
            }}
            QLabel#collapsedDragHandle {{
                color: {muted};
                font-size: 18px;
                font-weight: 800;
                background: {panel_hover};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 2px 0px;
            }}
            QLabel#collapsedDragHandle:hover {{
                color: {text};
                background: {panel};
            }}
            QFrame#statusDot {{
                color: {accent};
                background: transparent;
                font-size: 16px;
                font-weight: 900;
            }}
            QFrame#statusDot[state="idle"] {{
                color: {idle};
            }}
            QFrame#statusDot[state="paused"] {{
                color: {paused};
            }}
            QLabel#statusDot {{
                color: {accent};
                background: transparent;
                font-size: 16px;
                font-weight: 900;
            }}
            QLabel#statusDot[state="idle"] {{
                color: {idle};
            }}
            QLabel#statusDot[state="paused"] {{
                color: {paused};
            }}
            QToolButton {{
                color: {text};
                background: {panel};
                border: 1px solid {border};
                border-radius: 8px;
                font-size: 14px;
                font-weight: 700;
            }}
            QToolButton:hover {{
                background: {panel_hover};
            }}
            QComboBox#topSortCombo {{
                color: {text};
                background: {panel};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 3px 6px;
                min-height: 22px;
                font-size: 12px;
            }}
            QScrollArea#processScroll {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 7px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {border};
                border-radius: 3px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QFrame#processRow {{
                background: {panel};
                border: 1px solid {row_border};
                border-radius: 10px;
            }}
            QFrame#processRow:hover {{
                background: {panel_hover};
                border: 1px solid {border};
            }}
            QFrame#processRow[active="true"] {{
                border: 1px solid {accent};
            }}
            QLabel#processName {{
                font-size: 13px;
                font-weight: 650;
            }}
            QLabel#processTime {{
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#processRatio {{
                color: {muted};
                font-size: 10px;
                font-weight: 700;
            }}
            QLabel#goalStrip {{
                color: {text};
                font-size: 11px;
                padding: 3px 6px;
                background: {panel_hover};
                border-radius: 4px;
            }}
            QLabel#learningSummary {{
                color: {text};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#emptyLabel {{
                color: {muted};
                font-size: 12px;
            }}
            """
        )

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._sync_tray_actions(True)
        apply_windows_backdrop(self, is_dark_theme(self.settings))
        self._last_widget_refresh = 0.0
        self._footer_cache_at = 0.0
        self._footer_cache_text = "当前运行 · " + self._top_list_sort_label()
        self.refresh()
        if not hasattr(self, "_summary_checked_today"):
            self._summary_checked_today = True
            QTimer.singleShot(800, self.check_daily_summary)

    def hideEvent(self, event) -> None:  # type: ignore[override]
        super().hideEvent(event)
        self._sync_tray_actions(False)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.save_position()
        event.ignore()
        self._prepare_hide_to_tray()

    def moveEvent(self, event) -> None:  # type: ignore[override]
        super().moveEvent(event)
        if self.isVisible():
            self._position_save_timer.start(700)

    def enterEvent(self, event) -> None:  # type: ignore[override]
        super().enterEvent(event)
        self._pointer_inside = True
        self._hover_collapse_timer.stop()
        if not self.settings.always_expanded and self.is_collapsed:
            self._hover_expand_timer.start(220)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        super().leaveEvent(event)
        self._pointer_inside = False
        self._hover_expand_timer.stop()
        if not self.settings.always_expanded and not self.drag_pos:
            self._hover_collapse_timer.start(360)

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        is_collapsed_drag_handle = obj in getattr(self, "_collapsed_drag_widgets", set())
        if is_collapsed_drag_handle and self.is_collapsed and not self.settings.always_expanded:
            if event.type() == QEvent.Type.Enter:
                self._hover_expand_timer.stop()
                return False
            if event.type() == QEvent.Type.Leave:
                if self._pointer_inside and not self.drag_pos:
                    self._hover_expand_timer.start(260)
                return False
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            can_drag = (not self.is_collapsed) or is_collapsed_drag_handle
            if event.button() == Qt.MouseButton.LeftButton and can_drag:
                global_pos = event.globalPosition().toPoint()
                self.drag_pos = global_pos - self.frameGeometry().topLeft()
                self.drag_start_pos = global_pos
                self.drag_moved = False
                self._hover_expand_timer.stop()
                self._hover_collapse_timer.stop()
                return is_collapsed_drag_handle
        if event.type() == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
            if self.drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
                global_pos = event.globalPosition().toPoint()
                if self.drag_start_pos and (global_pos - self.drag_start_pos).manhattanLength() >= QApplication.startDragDistance():
                    self.drag_moved = True
                self.move(self._clamped_position(global_pos - self.drag_pos))
                return True
        if event.type() == QEvent.Type.MouseButtonRelease and isinstance(event, QMouseEvent):
            status_click = (
                event.button() == Qt.MouseButton.LeftButton
                and not self.drag_moved
                and obj in getattr(self, "_status_click_widgets", set())
            )
            was_click = (
                event.button() == Qt.MouseButton.LeftButton
                and not self.drag_moved
                and obj in getattr(self, "_collapsed_click_widgets", set())
                and not self.settings.always_expanded
            )
            self.drag_pos = None
            self.drag_start_pos = None
            self.drag_moved = False
            if is_collapsed_drag_handle:
                return True
            if status_click:
                self.open_status_center()
                return True
            if was_click:
                self.set_expanded(True)
                return True
            if not self._pointer_inside and not self.settings.always_expanded:
                self._hover_collapse_timer.start(220)
        return super().eventFilter(obj, event)

    def set_expanded(self, expanded: bool) -> None:
        self._sync_pin_button()
        if self.is_collapsed == (not expanded) and self.full_panel.isVisible() == expanded:
            return
        self.is_collapsed = not expanded
        self.full_panel.setVisible(expanded)
        self.collapsed_bar.setVisible(not expanded)
        width, height = FULL_SIZE if expanded else COLLAPSED_SIZE
        target_size = QSize(width, height)
        if self.isVisible():
            start = self.geometry()
            target = QRect(start.topLeft(), target_size)
            self._resize_animation.stop()
            self.setMinimumSize(QSize(0, 0))
            self.setMaximumSize(QSize(16777215, 16777215))
            self._target_fixed_size = target_size
            self._resize_animation.setStartValue(start)
            self._resize_animation.setEndValue(target)
            self._resize_animation.start()
        else:
            self.setFixedSize(target_size)
        self.keep_on_screen()

    def _finish_resize_animation(self) -> None:
        if self._target_fixed_size is not None:
            self.setFixedSize(self._target_fixed_size)
            self._target_fixed_size = None
            self.keep_on_screen()

    def _expand_from_hover(self) -> None:
        if self._pointer_inside and not self.settings.always_expanded and self.is_collapsed:
            self.set_expanded(True)

    def _collapse_from_hover(self) -> None:
        if not self._pointer_inside and not self.settings.always_expanded and not self.drag_pos:
            self.set_expanded(False)

    def _sync_pin_button(self) -> None:
        if self.settings.always_expanded:
            self.collapse_button.setText("⌕")
            self.collapse_button.setToolTip("取消固定，改为悬停展开")
            self.collapse_button.setAccessibleName("取消固定，改为悬停展开")
        else:
            self.collapse_button.setText("⌖")
            self.collapse_button.setToolTip("固定展开")
            self.collapse_button.setAccessibleName("固定展开")

    def _sync_sort_hint(self) -> None:
        if hasattr(self, "sort_hint_label"):
            text = self._top_list_sort_label()
            self.sort_hint_label.setText(text)
            self.sort_hint_label.setToolTip(text)

    def toggle_pin_mode(self) -> None:
        current = self.storage.load_settings()
        pinned = not current.always_expanded
        self.settings = replace(current, always_expanded=pinned)
        self.storage.save_settings(self.settings)
        self._hover_expand_timer.stop()
        self._hover_collapse_timer.stop()
        self.set_expanded(pinned or self._pointer_inside)

    def save_position(self) -> None:
        if self.isVisible():
            self.keep_on_screen()
            pos = self.pos()
            current = (pos.x(), pos.y())
            if current == self._last_saved_pos:
                return
            self._last_saved_pos = current
            self.storage.save_position(pos.x(), pos.y())

    def process_icon(self, exe_path: str) -> QIcon:
        cached = self.icon_cache.get(exe_path)
        if cached:
            self.icon_cache.pop(exe_path, None)
            self.icon_cache[exe_path] = cached
            return cached
        path = Path(exe_path)
        if path.exists():
            icon = self.icon_provider.icon(QFileInfo(str(path)))
        else:
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if len(self.icon_cache) >= MAX_ICON_CACHE_SIZE:
            oldest_key = next(iter(self.icon_cache), None)
            if oldest_key is not None:
                self.icon_cache.pop(oldest_key, None)
        self.icon_cache[exe_path] = icon
        return icon

    def _set_elided_text(self, label: QLabel, text: str, fallback_width: int) -> None:
        width = label.width()
        if width <= 20:
            width = fallback_width
        elided = QFontMetrics(label.font()).elidedText(text, Qt.TextElideMode.ElideRight, max(40, width))
        label.setText(elided)
        label.setToolTip(text if elided != text else "")

    def _set_widget_state(self, widget: QWidget, state: str) -> None:
        if widget.property("state") == state:
            return
        widget.setProperty("state", state)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _sync_status_indicator(self, state: str, state_label: str) -> None:
        symbols = {"active": "●", "idle": "◆", "paused": "Ⅱ"}
        self.status_dot.setText(symbols.get(state, "●"))
        self.status_dot.setAccessibleName(f"记录状态：{state_label}")

    def _joined_titles(self, titles: list[str], limit: int = 2) -> str:
        clean = [str(title).strip() for title in titles if str(title).strip()]
        return " / ".join(clean[:limit])

    def _activity_label(self) -> str:
        """Build a human-readable label for the current foreground activity."""
        if self.monitor.is_paused or self.monitor.is_idle:
            return ""
        category = self.monitor.current_category
        topic = self.monitor.current_learning_topic
        exe = self.monitor.current_foreground_exe
        if not category and not topic and not exe:
            return ""
        exe_name = exe.replace(".exe", "").replace(".EXE", "") if exe else ""
        # Map common exe names to friendly labels
        friendly_names = {
            "code": "VS Code",
            "msedge": "Edge",
            "chrome": "Chrome",
            "firefox": "Firefox",
            "devenv": "Visual Studio",
            "pycharm": "PyCharm",
            "idea64": "IntelliJ",
            "clion64": "CLion",
            "webstorm64": "WebStorm",
            "goland64": "GoLand",
            "rider64": "Rider",
            "notion": "Notion",
            "obsidian": "Obsidian",
            "typora": "Typora",
            "spotify": "Spotify",
            "steam": "Steam",
            "wechat": "微信",
            "qq": "QQ",
            "dingtalk": "钉钉",
        }
        display_exe = friendly_names.get(exe_name.lower(), exe_name) if exe_name else ""
        latest_tab = self.monitor.browser_bridge.latest(max_age_seconds=30)
        domain = str(getattr(latest_tab, "domain", "") or "") if latest_tab else ""
        title = str(getattr(latest_tab, "title", "") or self.monitor.foreground_title or "")
        short_hint = short_activity_hint(exe or "", domain, title, category or "")
        if category and topic:
            return f"{category} · {topic}"
        if category and category not in ("其他", "工具", "网站", "浏览器", "系统软件", "办公"):
            if display_exe and display_exe.lower() != category:
                return f"{category} · {display_exe}"
            return category
        if topic:
            return f"学习 · {topic}"
        if short_hint:
            if display_exe and display_exe.lower() != short_hint.lower():
                return f"{short_hint} · {display_exe}"
            return short_hint
        web_hint = low_info_web_hint(domain, title, category or "")
        if web_hint:
            return web_hint
        if display_exe:
            return display_exe
        return ""

    def _activity_short_label(self) -> str:
        """Short label for the activity badge pill."""
        if self.monitor.is_paused or self.monitor.is_idle:
            return ""
        category = self.monitor.current_category
        topic = self.monitor.current_learning_topic
        if category and category not in ("其他", "工具", "网站", "浏览器", "系统软件", "办公"):
            return category
        if topic:
            return "学习"
        latest_tab = self.monitor.browser_bridge.latest(max_age_seconds=30)
        domain = str(getattr(latest_tab, "domain", "") or "") if latest_tab else ""
        title = str(getattr(latest_tab, "title", "") or self.monitor.foreground_title or "")
        short_hint = short_activity_hint(self.monitor.current_foreground_exe or "", domain, title, category or "")
        if short_hint:
            return short_hint
        web_hint = low_info_web_hint(domain, title, category or "")
        if web_hint:
            return "网页" if domain else "未识别"
        if self.monitor.current_foreground_exe:
            return "使用中"
        return ""

    def _collapsed_media_text(self) -> tuple[str, str]:
        music_text = self._joined_titles(self.monitor.current_media_titles)
        if music_text:
            self._collapsed_media_cache = ("最近音乐", music_text)
            self._collapsed_media_cache_at = time.monotonic()
            return "正在听", music_text
        video_text = self._joined_titles(self.monitor.current_video_titles)
        if video_text:
            return "视频播放", video_text
        now_mono = time.monotonic()
        if now_mono - self._collapsed_media_cache_at < 15.0:
            return self._collapsed_media_cache
        start_date, end_date = self.storage.date_range_for_preset("today")
        top_music = self.storage.music_playback_rows_range(start_date, end_date, limit=1)
        if top_music:
            title = str(top_music[0]["content_title"] or "").strip()
            if title:
                self._collapsed_media_cache = ("最近音乐", title)
                self._collapsed_media_cache_at = now_mono
                return self._collapsed_media_cache
        self._collapsed_media_cache = ("音乐", "暂无正在播放的音乐")
        self._collapsed_media_cache_at = now_mono
        return self._collapsed_media_cache

    def _top_list_sort_mode(self) -> str:
        mode = str(self.settings.top_list_sort or "current_first")
        return mode if mode in {"current_first", "foreground", "running", "name"} else "current_first"

    def _top_list_sort_label(self, mode: str | None = None) -> str:
        labels = {
            "current_first": "当前优先，其余按今日前台时长降序",
            "foreground": "按今日前台时长从大到小",
            "running": "按今日总运行时长从大到小",
            "name": "按程序名称 A-Z",
        }
        return labels.get(mode or self._top_list_sort_mode(), labels["current_first"])

    def _is_foreground_process(self, proc: RunningProcess) -> bool:
        return bool(self.monitor.foreground_path) and proc.exe_path.casefold() == self.monitor.foreground_path.casefold()

    def change_top_list_sort(self) -> None:
        mode = str(self.top_sort_combo.currentData() or "current_first")
        if mode not in {"current_first", "foreground", "running", "name"}:
            mode = "current_first"
        current = self.storage.load_settings()
        if current.top_list_sort != mode:
            self.storage.save_settings(replace(current, top_list_sort=mode))
            self.settings = self.storage.load_settings()
        self._sync_sort_hint()
        self._last_widget_refresh = 0.0
        self._footer_cache_at = 0.0
        self._footer_cache_text = "当前运行 · " + self._top_list_sort_label(mode)
        self.refresh()

    def refresh(self) -> None:
        now_mono = time.monotonic()
        if self.stats_dialog and self.stats_dialog.isVisible() and now_mono - self._last_stats_refresh >= 8.0:
            self.stats_dialog.refresh()
            self._last_stats_refresh = now_mono
        if not self.isVisible():
            return
        if now_mono - self._last_widget_refresh < 2.0:
            return
        self._last_widget_refresh = now_mono

        totals = self.storage.day_overview_totals()
        total = totals["foreground"]
        video_total = totals["video"]
        media_total = totals["media"]
        learning_total = totals.get("learning", 0.0)
        metrics_text = f"前台 {format_duration(total)} · 视频 {format_duration(video_total)} · 音乐 {format_duration(media_total)} · 学习 {format_duration(learning_total)}"
        activity_label = self._activity_label()
        activity_short = self._activity_short_label()
        collapsed_caption = f"今日前台 {format_duration(total)}"
        state_label = "活动中"
        if self.monitor.is_paused:
            total_text = "已暂停 · " + metrics_text
            collapsed_caption = f"统计已暂停 · 今日前台 {format_duration(total)}"
            state_label = "已暂停"
            state = "paused"
        elif self.monitor.is_idle:
            total_text = f"空闲 {format_duration(self.monitor.idle_seconds)} · " + metrics_text
            collapsed_caption = f"空闲 {format_duration(self.monitor.idle_seconds)} · 今日前台 {format_duration(total)}"
            state_label = "空闲"
            state = "idle"
        else:
            total_text = metrics_text
            state = "active"
        self._sync_status_indicator(state, state_label)
        self._set_widget_state(self.status_dot, state)
        self._set_widget_state(self.collapsed_state, state)
        if activity_short and state == "active":
            self.collapsed_activity_badge.setText(activity_short)
            activity_cat = self.monitor.current_category
            if self.monitor.current_learning_topic and not activity_cat:
                activity_cat = "学习"
            self.collapsed_activity_badge.setProperty("category", activity_cat or "其他")
            self.collapsed_activity_badge.style().unpolish(self.collapsed_activity_badge)
            self.collapsed_activity_badge.style().polish(self.collapsed_activity_badge)
            self.collapsed_activity_badge.setVisible(True)
        else:
            self.collapsed_activity_badge.setVisible(False)
        self.total_label.setText(total_text)
        self.collapsed_state.setText(state_label)
        self._set_elided_text(self.collapsed_total, collapsed_caption, COLLAPSED_SIZE[0] - 110)
        self.collapsed_focus_metric.setText(f"前台 {format_duration(total)}")
        self.collapsed_video_metric.setText(f"视频 {format_duration(video_total)}")
        self.collapsed_music_metric.setText(f"音乐 {format_duration(media_total)}")
        self.collapsed_learning_metric.setText(f"学习 {format_duration(learning_total)}")
        media_label, media_text = self._collapsed_media_text()
        if media_text == "暂无正在播放的音乐" and activity_label:
            self._set_elided_text(self.collapsed_music, f"当前 · {activity_label}", COLLAPSED_SIZE[0] - 64)
        else:
            self._set_elided_text(self.collapsed_music, f"{media_label} · {media_text}", COLLAPSED_SIZE[0] - 64)
        status_tip = (
            f"{state_label}\n"
            f"{metrics_text}\n"
            f"{media_label}：{media_text}"
        )
        if activity_label:
            status_tip += f"\n当前活动：{activity_label}"
        for widget in (self.status_dot, self.collapsed_state, self.collapsed_bar):
            widget.setToolTip(status_tip)
        self.focus_value_label.setText(format_duration(total))
        self.video_value_label.setText(format_duration(video_total))
        self.music_value_label.setText(format_duration(media_total))
        self.learning_value_label.setText(format_duration(learning_total))
        self.tray.setToolTip(f"UsageWidget v{__version__}\n{total_text}")

        if learning_total > 0:
            topic_rows = self.storage.learning_topic_summary_range(date.today(), date.today(), limit=3)
            topic_parts = []
            for t in topic_rows:
                name = str(t["learning_topic"])
                secs = float(t["total_seconds"] or 0)
                if name and secs > 0:
                    topic_parts.append(f"{name} {format_duration(secs)}")
            if topic_parts:
                self.learning_summary_label.setText(
                    f"今天学习了 {format_duration_smart(learning_total)} · " + " · ".join(topic_parts)
                )
            else:
                self.learning_summary_label.setText(f"今天学习了 {format_duration_smart(learning_total)}")
            self.learning_summary_label.setVisible(True)
        else:
            self.learning_summary_label.setVisible(False)
        today = date.today()
        goal_parts = []
        for item in self.storage.goal_progress_range(today, today):
            g = item["goal"]
            val = float(item["value"])
            target = float(item["target"])
            ok = bool(item["ok"])
            pct = min(100, int(val / target * 100)) if target > 0 else 0
            icon = "✓" if ok else ("≈" if pct >= 70 else "✗")
            goal_parts.append(f"{icon} {g['name']} {format_duration(val)}/{format_duration(target)}")
        if goal_parts:
            self.goal_strip.setText("  ".join(goal_parts))
            self.goal_strip.setVisible(True)
        else:
            self.goal_strip.setVisible(False)
        if self.monitor.current_media_titles:
            self.footer_label.setText("正在播放 · " + " / ".join(self.monitor.current_media_titles[:2]))
        elif self.monitor.current_video_titles:
            self.footer_label.setText("视频播放 · " + " / ".join(self.monitor.current_video_titles[:2]))
        elif activity_label:
            self.footer_label.setText("当前 · " + activity_label)
            self._footer_cache_text = "当前 · " + activity_label
            self._footer_cache_at = now_mono
        else:
            if now_mono - self._footer_cache_at >= 15.0:
                top_web = self.storage.top_content(kind="web_page", limit=1)
                top_video = self.storage.top_content(kind="video_playback", limit=1)
                start_date, end_date = self.storage.date_range_for_preset("today")
                top_music = self.storage.music_playback_rows_range(start_date, end_date, limit=1)
                parts = []
                if top_web:
                    parts.append("网页 " + str(top_web[0]["content_title"])[:16])
                if top_video:
                    parts.append("视频 " + str(top_video[0]["content_title"])[:16])
                if top_music:
                    parts.append("音乐 " + str(top_music[0]["content_title"])[:16])
                self._footer_cache_text = " · ".join(parts) if parts else "当前运行 · " + self._top_list_sort_label()
                self._footer_cache_at = now_mono
            self.footer_label.setText(self._footer_cache_text)

        current = list(self.monitor.current_processes.values())
        stats = self.storage.stats_for_paths([proc.exe_path for proc in current])

        items = []
        for proc in current:
            row = stats.get(proc.exe_path)
            fg = float(row["foreground_seconds"] or 0) if row else 0.0
            running = float(row["running_seconds"] or 0) if row else 0.0
            is_foreground = self._is_foreground_process(proc)
            items.append((fg, running, proc.exe_name.lower(), is_foreground, proc))
        sort_mode = self._top_list_sort_mode()
        if sort_mode == "running":
            items.sort(key=lambda item: (-item[1], -item[0], -int(item[3]), item[2]))
        elif sort_mode == "name":
            items.sort(key=lambda item: (item[2], -int(item[3]), -item[0], -item[1]))
        elif sort_mode == "foreground":
            items.sort(key=lambda item: (-item[0], -int(item[3]), -item[1], item[2]))
        else:
            items.sort(key=lambda item: (-int(item[3]), -item[0], -item[1], item[2]))

        visible_items = items[:5]
        visible_paths = [proc.exe_path for _, _, _, _, proc in visible_items]
        cumulative_by_path = self.storage.totals_for_paths(visible_paths)
        content_by_path = self.storage.top_content_for_paths(visible_paths, limit_per_path=3)
        self.empty_label.setVisible(not visible_items)
        for index, row_widget in enumerate(self.rows):
            if index >= len(visible_items):
                row_widget.hide()
                continue
            _, _, _, is_foreground, proc = visible_items[index]
            row = stats.get(proc.exe_path)
            fg = float(row["foreground_seconds"] or 0) if row else 0.0
            running = float(row["running_seconds"] or 0) if row else 0.0
            cumulative = cumulative_by_path.get(proc.exe_path, {"foreground_seconds": 0.0, "running_seconds": 0.0})
            content_rows = content_by_path.get(proc.exe_path, [])
            content_lines = []
            content_titles = []
            for content_row in content_rows:
                seconds = float(content_row["attention_seconds"] or 0) + float(content_row["background_seconds"] or 0)
                content_title = str(content_row["content_title"] or "")
                content_lines.append(f"{format_duration(seconds)} · {content_title}")
                if content_title:
                    content_titles.append(content_title)
            detail_text = ""
            if proc.exe_path == self.monitor.foreground_path and self.monitor.foreground_title:
                detail_text = self.monitor.foreground_title
            elif content_titles:
                detail_text = content_titles[0]
            row_widget.set_data(
                self.process_icon(proc.exe_path),
                proc,
                fg,
                running,
                cumulative["foreground_seconds"],
                cumulative["running_seconds"],
                is_foreground,
                detail_text=detail_text,
                content_lines=content_lines,
                display_metric="running" if sort_mode == "running" else "foreground",
            )
            row_widget.show()

    def toggle_visible(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self._prepare_hide_to_tray()
        else:
            self._show_from_tray()

    def toggle_background_mode(self) -> None:
        if self.background_action.isChecked():
            self._prepare_hide_to_tray()
        else:
            self._show_from_tray()

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def open_settings(self) -> None:
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        dialog = SettingsDialog(self.storage, self)
        dialog.settings_changed.connect(self.apply_settings)
        dialog.settings_changed.connect(self.refresh_open_dialogs)
        dialog.data_changed.connect(self.refresh_open_dialogs)
        dialog.destroyed.connect(lambda: setattr(self, "settings_dialog", None))
        self.settings_dialog = dialog
        dialog.show()

    def open_stats(self) -> None:
        if self.stats_dialog and self.stats_dialog.isVisible():
            self.stats_dialog.refresh()
            self._last_stats_refresh = time.monotonic()
            self.stats_dialog.raise_()
            self.stats_dialog.activateWindow()
            return
        dialog = StatsDialog(self.storage, self)
        self.stats_dialog = dialog
        self._last_stats_refresh = time.monotonic()
        dialog.destroyed.connect(lambda: setattr(self, "stats_dialog", None))
        dialog.show()

    def open_stats_search(self) -> None:
        self.open_stats()
        if self.stats_dialog:
            self.stats_dialog._focus_timeline_search()

    def open_stats_today(self) -> None:
        self.open_stats()
        if self.stats_dialog:
            self.stats_dialog._jump_to_today_range()

    def open_status_center(self) -> None:
        if self.status_dialog and self.status_dialog.isVisible():
            self.status_dialog.refresh()
            self.status_dialog.raise_()
            self.status_dialog.activateWindow()
            return
        dialog = CurrentStatusDialog(self.storage, self.monitor, self)
        self.status_dialog = dialog
        dialog.destroyed.connect(lambda: setattr(self, "status_dialog", None))
        dialog.show()

    def open_diagnostics(self) -> None:
        if self.diagnostics_dialog and self.diagnostics_dialog.isVisible():
            self.diagnostics_dialog.refresh()
            self.diagnostics_dialog.raise_()
            self.diagnostics_dialog.activateWindow()
            return
        dialog = DiagnosticsDialog(self.storage, self.monitor, self)
        self.diagnostics_dialog = dialog
        dialog.destroyed.connect(lambda: setattr(self, "diagnostics_dialog", None))
        dialog.show()

    def refresh_open_dialogs(self) -> None:
        self._last_widget_refresh = 0.0
        self.refresh()
        now_mono = time.monotonic()
        if self.stats_dialog and self.stats_dialog.isVisible():
            self.stats_dialog.refresh()
            self._last_stats_refresh = now_mono
        if self.status_dialog and self.status_dialog.isVisible():
            self.status_dialog.refresh()
        if self.diagnostics_dialog and self.diagnostics_dialog.isVisible():
            self.diagnostics_dialog.refresh()
        self._sync_tray_actions()

    def toggle_pause_tracking(self) -> None:
        settings = self.storage.load_settings()
        self.storage.save_settings(replace(settings, pause_tracking=not settings.pause_tracking))
        self.apply_settings()
        self.refresh_open_dialogs()

    def export_csv(self) -> None:
        default_name = f"usage-widget-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", default_name, "CSV Files (*.csv)")
        if path:
            try:
                self.storage.export_csv(Path(path))
            except Exception as exc:
                show_operation_error(self, "导出失败", exc)
                return
            self.tray.showMessage("UsageWidget", "CSV 导出完成", build_app_icon(), 2500)

    def export_content_csv(self) -> None:
        default_name = f"usage-widget-content-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出内容 CSV", default_name, "CSV Files (*.csv)")
        if path:
            try:
                self.storage.export_content_csv(Path(path))
            except Exception as exc:
                show_operation_error(self, "导出失败", exc)
                return
            self.tray.showMessage("UsageWidget", "内容 CSV 导出完成", build_app_icon(), 2500)
