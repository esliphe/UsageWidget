from __future__ import annotations

import ctypes
import html
import sys
import threading
import time
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QEvent, QFileInfo, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFontMetrics, QIcon, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .diagnostics import clear_log, log_path, read_recent_log
from .monitor import ProcessMonitor, RunningProcess
from .startup import is_startup_enabled, set_startup_enabled
from .storage import AppSettings, DEFAULT_CATEGORY_RULES, DEFAULT_IGNORED, Storage
from .timefmt import format_duration, format_duration_long, format_duration_smart


FULL_SIZE = (400, 520)
COLLAPSED_SIZE = (500, 118)


def build_app_icon() -> QIcon:
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
    return QIcon(pix)


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
        "- 联网分类增强只在本地规则识别为“其他”时使用，隐私模式下自动关闭，不会覆盖你手动添加的分类规则。"
    )


def online_feature_state(enabled: bool, private_mode: bool) -> str:
    if private_mode and enabled:
        return "关闭（隐私模式生效）"
    if private_mode:
        return "关闭（隐私模式）"
    if enabled:
        return "开启"
    return "关闭（设置关闭）"


class ProgressBarWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.value = 0.0
        self.accent = QColor("#1677d2")
        self.track = QColor(120, 140, 165, 55)
        self.setFixedHeight(5)

    def set_value(self, value: float, accent: str) -> None:
        self.value = max(0.0, min(1.0, value))
        self.accent = QColor(accent)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 1, self.width(), 3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.track)
        painter.drawRoundedRect(rect, 2, 2)
        if self.value > 0:
            painter.setBrush(self.accent)
            painter.drawRoundedRect(QRectF(rect.left(), rect.top(), rect.width() * self.value, rect.height()), 2, 2)
        painter.end()


class SortableTableItem(QTableWidgetItem):
    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if left is not None and right is not None:
            try:
                return float(left) < float(right)
            except (TypeError, ValueError):
                pass
        left_text = self.text().casefold()
        right_text = other.text().casefold() if other is not None else ""
        return left_text < right_text


class ProcessRow(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("processRow")
        self.setFixedHeight(62)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(9)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(28, 28)
        self.icon_label.setScaledContents(True)
        layout.addWidget(self.icon_label)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(1)
        self.name_label = QLabel()
        self.name_label.setObjectName("processName")
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.path_label = QLabel()
        self.path_label.setObjectName("processPath")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.progress_bar = ProgressBarWidget()
        text_box.addWidget(self.name_label)
        text_box.addWidget(self.path_label)
        text_box.addWidget(self.progress_bar)
        layout.addLayout(text_box, 1)

        self.time_label = QLabel()
        self.time_label.setObjectName("processTime")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.time_label.setMinimumWidth(66)
        layout.addWidget(self.time_label)

    def set_data(
        self,
        icon: QIcon,
        proc: RunningProcess,
        today_foreground: float,
        today_running: float,
        cumulative_foreground: float,
        cumulative_running: float,
        is_foreground: bool,
        detail_text: str = "",
        content_lines: list[str] | None = None,
        display_metric: str = "foreground",
    ) -> None:
        pixmap = icon.pixmap(28, 28)
        self.icon_label.setPixmap(pixmap)
        self.name_label.setText(proc.exe_name)
        if display_metric == "running":
            primary_label = "运行"
            primary_seconds = today_running
            subtitle = f"运行 {format_duration(today_running)} · 前台 {format_duration(today_foreground)}"
        else:
            primary_label = "前台"
            primary_seconds = today_foreground
            subtitle = f"前台 {format_duration(today_foreground)}"
        if detail_text:
            subtitle = f"{subtitle} · {detail_text}"
        elif proc.instance_count > 1:
            subtitle = f"{subtitle} · {proc.instance_count} 个实例"
        self.path_label.setText(subtitle)
        self.time_label.setText(format_duration(primary_seconds))
        self.time_label.setToolTip(f"{primary_label}时长：{format_duration_long(primary_seconds)}")
        self.setProperty("active", "true" if is_foreground else "false")
        ratio = today_foreground / today_running if today_running > 0 else 0.0
        self.progress_bar.set_value(ratio, "#55d6be" if is_foreground else "#1677d2")
        self.style().unpolish(self)
        self.style().polish(self)

        today_background = max(0.0, today_running - today_foreground)
        content_html = ""
        if content_lines:
            escaped_lines = "<br>".join(html.escape(line) for line in content_lines)
            content_html = f"<br><br><b>今日内容 Top</b><br>{escaped_lines}"
        tooltip = (
            f"<b>{html.escape(proc.exe_name)}</b><br>"
            f"今日前台：{html.escape(format_duration_long(today_foreground))}<br>"
            f"今日总运行：{html.escape(format_duration_long(today_running))}<br>"
            f"今日后台：{html.escape(format_duration_long(today_background))}<br>"
            f"累计前台：{html.escape(format_duration_long(cumulative_foreground))}<br>"
            f"累计总运行：{html.escape(format_duration_long(cumulative_running))}<br>"
            f"路径：{html.escape(proc.exe_path)}"
            f"{content_html}"
        )
        self.setToolTip(tooltip)


class StatCard(QFrame):
    def __init__(self, title: str, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        self.accent = accent
        self.setMinimumHeight(86)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("statCardTitle")
        self.value_label = QLabel("0s")
        self.value_label.setObjectName("statCardValue")
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("statCardSub")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.subtitle_label)

    def set_data(self, value: float | str, subtitle: str = "") -> None:
        self.value_label.setText(format_duration(value) if isinstance(value, (int, float)) else value)
        self.subtitle_label.setText(subtitle)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.accent))
        painter.drawRoundedRect(QRectF(0, 12, 4, self.height() - 24), 2, 2)
        painter.end()


class BarChartWidget(QWidget):
    def __init__(self, title: str, accent: str = "#1677d2", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.accent = QColor(accent)
        self.data: list[tuple[str, float, str]] = []
        self.setMinimumHeight(230)
        self.setMouseTracking(True)

    def set_data(self, data: list[tuple[str, float, str]]) -> None:
        self.data = [(label, max(0.0, float(value)), extra) for label, value, extra in data[:8]]
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        painter.setPen(QColor("#17202a"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(QRectF(12, 8, rect.width() - 24, 22), Qt.AlignmentFlag.AlignLeft, self.title)

        if not self.data:
            painter.setPen(QColor("#8a98aa"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "暂无数据")
            painter.end()
            return

        max_value = max([value for _, value, _ in self.data] or [1.0])
        chart_top = 40
        row_gap = 8
        row_height = max(22, int((rect.height() - chart_top - 12) / max(len(self.data), 1)) - row_gap)
        label_width = min(150, max(92, int(rect.width() * 0.34)))
        value_width = 68
        bar_left = 12 + label_width
        bar_right = rect.width() - value_width - 12
        bar_width = max(30, bar_right - bar_left)

        normal_font = painter.font()
        normal_font.setBold(False)
        normal_font.setPointSize(9)
        painter.setFont(normal_font)
        metrics = painter.fontMetrics()
        track_color = QColor("#e8eef5")
        text_color = QColor("#273449")
        muted_color = QColor("#738196")

        for index, (label, value, extra) in enumerate(self.data):
            y = chart_top + index * (row_height + row_gap)
            label_text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, label_width - 10)
            painter.setPen(text_color)
            painter.drawText(QRectF(12, y, label_width - 8, row_height), Qt.AlignmentFlag.AlignVCenter, label_text)

            track_rect = QRectF(bar_left, y + 5, bar_width, max(8, row_height - 10))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(track_color)
            painter.drawRoundedRect(track_rect, 5, 5)

            ratio = value / max_value if max_value else 0
            fill_width = max(3.0 if value > 0 else 0.0, track_rect.width() * ratio)
            fill_rect = QRectF(track_rect.left(), track_rect.top(), fill_width, track_rect.height())
            color = QColor(self.accent)
            color = color.lighter(100 + min(index * 8, 45))
            painter.setBrush(color)
            painter.drawRoundedRect(fill_rect, 5, 5)

            painter.setPen(muted_color)
            painter.drawText(
                QRectF(bar_right + 8, y, value_width - 8, row_height),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                format_duration(value),
            )
            if extra:
                self.setToolTip(extra)
        painter.end()


class HourlyActivityChart(QWidget):
    COLORS = {
        "focus": QColor("#1677d2"),
        "video": QColor("#f0a33a"),
        "music": QColor("#d95f76"),
        "learn": QColor("#55b88d"),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = "24 小时时间分布"
        self.data: list[tuple[int, float, float, float, float]] = []
        self.setMinimumHeight(220)

    def set_data(self, rows: list[tuple[int, float, float, float, float]]) -> None:
        self.data = rows
        self._update_tooltip()
        self.update()

    def _update_tooltip(self) -> None:
        if not self.data:
            self.setToolTip("暂无时间线数据")
            return
        peak = max(self.data, key=lambda row: row[1] + row[2] + row[3])
        learn_peak = max(self.data, key=lambda row: row[4])
        self.setToolTip(
            "24 小时时间分布\n"
            f"活动高峰：{peak[0]:02d}:00，{format_duration(peak[1] + peak[2] + peak[3])}\n"
            f"学习高峰：{learn_peak[0]:02d}:00，{format_duration(learn_peak[4])}"
        )

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        painter.setPen(QColor("#17202a"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(QRectF(12, 8, rect.width() - 24, 22), Qt.AlignmentFlag.AlignLeft, self.title)

        if not self.data:
            painter.setPen(QColor("#8a98aa"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "暂无时间线数据")
            painter.end()
            return

        activity_totals = [focus + video + music for _, focus, video, music, _learn in self.data]
        learning_totals = [learn for *_rest, learn in self.data]
        totals = activity_totals + learning_totals
        max_value = max(totals or [1.0])
        chart = QRectF(18, 46, rect.width() - 36, rect.height() - 94)
        bar_gap = 3
        bar_width = max(4.0, (chart.width() - bar_gap * 23) / 24)

        painter.setPen(QColor("#e5ebf2"))
        grid_font = painter.font()
        grid_font.setBold(False)
        grid_font.setPointSize(7)
        painter.setFont(grid_font)
        for ratio, label in ((0.5, "50%"), (1.0, "max")):
            y = chart.bottom() - chart.height() * ratio
            painter.drawLine(int(chart.left()), int(y), int(chart.right()), int(y))
            painter.drawText(QRectF(chart.right() - 34, y - 14, 32, 14), Qt.AlignmentFlag.AlignRight, label)
        painter.setPen(QColor("#d9e1ea"))
        painter.drawLine(int(chart.left()), int(chart.bottom()), int(chart.right()), int(chart.bottom()))
        painter.setPen(Qt.PenStyle.NoPen)

        peak_hour = -1
        if self.data:
            peak_hour = max(self.data, key=lambda row: row[1] + row[2] + row[3])[0]
        for hour, focus, video, music, learn in self.data:
            x = chart.left() + hour * (bar_width + bar_gap)
            total = focus + video + music
            if total <= 0 or max_value <= 0:
                painter.setBrush(QColor("#e8eef5"))
                painter.drawRoundedRect(QRectF(x, chart.bottom() - 3, bar_width, 3), 2, 2)
            else:
                current_bottom = chart.bottom()
                for value, key in ((music, "music"), (video, "video"), (focus, "focus")):
                    if value <= 0:
                        continue
                    height = max(2.0, chart.height() * (value / max_value))
                    painter.setBrush(self.COLORS[key])
                    painter.drawRoundedRect(QRectF(x, current_bottom - height, bar_width, height), 2, 2)
                    current_bottom -= height
            if learn > 0 and max_value > 0:
                learn_height = max(2.0, chart.height() * (learn / max_value))
                marker_width = max(2.0, min(5.0, bar_width * 0.28))
                painter.setBrush(self.COLORS["learn"])
                painter.drawRoundedRect(
                    QRectF(x + bar_width - marker_width, chart.bottom() - learn_height, marker_width, learn_height),
                    2,
                    2,
                )
            if hour == peak_hour and max_value > 0:
                peak_height = max(4.0, chart.height() * (max(total, learn) / max_value))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QColor("#17202a"))
                painter.drawRoundedRect(QRectF(x - 1, chart.bottom() - peak_height - 1, bar_width + 2, peak_height + 2), 3, 3)
                painter.setPen(Qt.PenStyle.NoPen)

        painter.setPen(QColor("#738196"))
        small = painter.font()
        small.setBold(False)
        small.setPointSize(8)
        painter.setFont(small)
        for hour in (0, 6, 12, 18, 23):
            x = chart.left() + hour * (bar_width + bar_gap)
            painter.drawText(QRectF(x - 8, chart.bottom() + 8, 34, 18), Qt.AlignmentFlag.AlignCenter, f"{hour:02d}")

        legend_y = rect.height() - 24
        x = 16
        for label, key in (("前台", "focus"), ("视频", "video"), ("音乐", "music"), ("学习标记", "learn")):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.COLORS[key])
            painter.drawRoundedRect(QRectF(x, legend_y + 5, 10, 10), 3, 3)
            painter.setPen(QColor("#273449"))
            painter.drawText(QRectF(x + 16, legend_y, 70, 20), Qt.AlignmentFlag.AlignVCenter, label)
            x += 86 if key == "learn" else 60
        painter.end()


class HeatmapWidget(QWidget):
    COLORS = [
        QColor("#ebedf0"), QColor("#c6e48b"), QColor("#7bc96f"),
        QColor("#239a3b"), QColor("#196127"),
    ]

    def __init__(self, title: str = "学习热力图", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.data: list[tuple[str, float]] = []
        self.metric_label = "学习"
        self._cell_rects: list[tuple[QRectF, str, float]] = []
        self.setMinimumHeight(155)
        self.setMouseTracking(True)

    def set_data(self, rows: list[tuple[str, float]], metric_label: str = "学习") -> None:
        if rows:
            self.data = rows
        else:
            self.data = []
        self.metric_label = metric_label
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        painter.setPen(QColor("#17202a"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        title_text = f"{self.title}（{self.metric_label}）"
        painter.drawText(QRectF(12, 6, rect.width() - 24, 22), Qt.AlignmentFlag.AlignLeft, title_text)
        self._cell_rects = []
        if not self.data:
            painter.setPen(QColor("#8a98aa"))
            painter.drawText(QRectF(16, 30, rect.width() - 32, rect.height() - 30),
                             Qt.AlignmentFlag.AlignCenter, "暂无足够数据（需使用 1 天以上）")
            painter.end()
            return
        max_val = max(v for _, v in self.data) or 1.0
        total_cols = (len(self.data) + 6) // 7
        cell = min(15.0, max(8.0, (rect.width() - 50) / max(total_cols, 1)))
        cell_gap = 2
        chart_left = 32
        chart_top = 36
        for idx, (date_str, value) in enumerate(self.data):
            col = idx // 7
            row = idx % 7
            ratio = value / max_val if max_val > 0 else 0
            ci = min(len(self.COLORS) - 1, int(ratio * (len(self.COLORS) - 1) + 0.5)) if value > 0 else 0
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.COLORS[ci])
            x = chart_left + col * (cell + cell_gap)
            y = chart_top + row * (cell + cell_gap)
            r = QRectF(x, y, cell, cell)
            self._cell_rects.append((r, date_str, value))
            painter.drawRoundedRect(r, 2, 2)
        painter.setPen(QColor("#738196"))
        small = painter.font()
        small.setPointSize(6)
        painter.setFont(small)
        days = ("一", "", "三", "", "五", "", "日")
        for i, label in enumerate(days):
            y = chart_top + i * (cell + cell_gap) + cell / 2 - 4
            painter.drawText(QRectF(4, int(y), 24, 12),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
        painter.end()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        from .timefmt import format_duration
        for r, date_str, value in self._cell_rects:
            if r.contains(event.position()):
                tip = f"{date_str} · {self.metric_label} {format_duration(value)}"
                self.setToolTip(tip)
                return
        self.setToolTip("")


class LineChartWidget(QWidget):
    COLORS = {"this": QColor("#1677d2"), "last": QColor("#c4cdd6")}

    def __init__(self, title: str = "本周 vs 上周", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.this_week: list[tuple[str, float]] = []
        self.last_week: list[tuple[str, float]] = []
        self.metric_label = "前台"
        self._bar_rects: list[tuple[QRectF, QRectF, str, float, float]] = []
        self.setMinimumHeight(180)
        self.setMouseTracking(True)

    def set_data(self, this: list[tuple[str, float]], last: list[tuple[str, float]],
                 metric_label: str = "前台") -> None:
        self.this_week = this or []
        self.last_week = last or []
        self.metric_label = metric_label
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        painter.setPen(QColor("#17202a"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        title_text = f"{self.title}（{self.metric_label}）"
        painter.drawText(QRectF(12, 6, rect.width() - 24, 22),
                         Qt.AlignmentFlag.AlignLeft, title_text)
        self._bar_rects = []
        if not self.this_week:
            painter.setPen(QColor("#8a98aa"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "暂无数据")
            painter.end()
            return
        has_any = any(v > 0 for _, v in self.this_week) or any(v > 0 for _, v in self.last_week)
        if not has_any:
            painter.setPen(QColor("#8a98aa"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "暂无数据（本周尚未产生记录）")
            painter.end()
            return
        all_vals = [v for _, v in self.this_week] + [v for _, v in self.last_week]
        max_val = max(all_vals or [1.0])
        chart = QRectF(52, 40, rect.width() - 68, rect.height() - 74)
        bar_w = max(6.0, (chart.width() - 100) / 14)
        gap = 3
        group_w = bar_w * 2 + gap
        painter.setPen(QColor("#d9e1ea"))
        painter.drawLine(int(chart.left()), int(chart.bottom()), int(chart.right()), int(chart.bottom()))
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(7):
            if i >= len(self.this_week):
                break
            day_label = self.this_week[i][0] if i < len(self.this_week) else ""
            tv = self.this_week[i][1] if i < len(self.this_week) else 0
            lv = self.last_week[i][1] if i < len(self.last_week) else 0
            gx = chart.left() + i * (group_w + 8)
            r1 = QRectF(0, 0, 0, 0)
            r2 = QRectF(0, 0, 0, 0)
            for val, key in ((lv, "last"), (tv, "this")):
                h = max(2.0, chart.height() * (val / max_val)) if max_val > 0 else 2
                offset = 0 if key == "last" else bar_w + gap
                r = QRectF(gx + offset, chart.bottom() - h, bar_w, h)
                if key == "last":
                    r1 = r
                else:
                    r2 = r
                painter.setBrush(self.COLORS[key])
                painter.drawRoundedRect(r, 2, 2)
            self._bar_rects.append((r1, r2, day_label, lv, tv))
            painter.setPen(QColor("#738196"))
            ff = painter.font()
            ff.setPointSize(7)
            painter.setFont(ff)
            painter.drawText(QRectF(gx - 2, chart.bottom() + 6, group_w + 8, 14),
                             Qt.AlignmentFlag.AlignCenter, day_label[:2])
        legend_y = rect.height() - 22
        painter.setPen(Qt.PenStyle.NoPen)
        for label, key, lx in (("本周", "this", chart.left()), ("上周", "last", chart.left() + 56)):
            painter.setBrush(self.COLORS[key])
            painter.drawRoundedRect(QRectF(lx, legend_y + 4, 10, 10), 3, 3)
            painter.setPen(QColor("#273449"))
            painter.drawText(QRectF(lx + 16, legend_y, 40, 18), Qt.AlignmentFlag.AlignVCenter, label)
        painter.end()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        from .timefmt import format_duration
        for r1, r2, day, lv, tv in self._bar_rects:
            if r1.contains(event.position()) or r2.contains(event.position()):
                tip = f"{day} · 本周 {format_duration(tv)} · 上周 {format_duration(lv)}"
                self.setToolTip(tip)
                return
        self.setToolTip("")


class DonutChartWidget(QWidget):
    COLORS = ["#1677d2", "#55b88d", "#f0a33a", "#d95f76", "#8b72d9", "#2f9aa0", "#6b7c93"]

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.data: list[tuple[str, float, float]] = []
        self._legend_rects: list[tuple[QRectF, str, float, float, float]] = []
        self.setMinimumHeight(230)
        self.setMouseTracking(True)

    def set_data(self, data: list[tuple[str, float, float]]) -> None:
        self.data = [(name, max(0.0, attention), max(0.0, background)) for name, attention, background in data[:7]]
        self._update_tooltip()
        self.update()

    def _update_tooltip(self) -> None:
        totals = [(name, attention, background, attention + background) for name, attention, background in self.data if attention + background > 0]
        if not totals:
            self.setToolTip("暂无分类数据")
            return
        name, attention, background, total = max(totals, key=lambda item: item[3])
        all_total = sum(item[3] for item in totals)
        percent = total / all_total * 100.0 if all_total > 0 else 0.0
        self.setToolTip(
            f"最大分类：{name} · {format_duration(total)} · {percent:.1f}%\n"
            f"注视 {format_duration(attention)} · 播放/后台 {format_duration(background)}"
        )

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        self._legend_rects = []

        painter.setPen(QColor("#17202a"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(QRectF(12, 8, rect.width() - 24, 22), Qt.AlignmentFlag.AlignLeft, self.title)

        totals = [(name, attention + background) for name, attention, background in self.data if attention + background > 0]
        total = sum(value for _, value in totals)
        if total <= 0:
            painter.setPen(QColor("#8a98aa"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "暂无分类数据")
            painter.end()
            return

        side = min(150, rect.height() - 64, max(92, int(rect.width() * 0.38)))
        pie_rect = QRectF(16, 52, side, side)
        start_angle = 90 * 16
        painter.setPen(Qt.PenStyle.NoPen)
        for index, (_, value) in enumerate(totals):
            span = int(-(value / total) * 360 * 16)
            painter.setBrush(QColor(self.COLORS[index % len(self.COLORS)]))
            painter.drawPie(pie_rect, start_angle, span)
            start_angle += span

        painter.setBrush(QColor("#f6f8fb"))
        inner = pie_rect.adjusted(side * 0.24, side * 0.24, -side * 0.24, -side * 0.24)
        painter.drawEllipse(inner)
        painter.setPen(QColor("#17202a"))
        center_font = painter.font()
        center_font.setBold(True)
        center_font.setPointSize(12)
        painter.setFont(center_font)
        painter.drawText(inner.adjusted(0, -8, 0, -2), Qt.AlignmentFlag.AlignCenter, format_duration(total))
        sub_font = painter.font()
        sub_font.setBold(False)
        sub_font.setPointSize(8)
        painter.setFont(sub_font)
        painter.setPen(QColor("#738196"))
        painter.drawText(inner.adjusted(0, 18, 0, 0), Qt.AlignmentFlag.AlignCenter, "总时长")

        legend_left = int(pie_rect.right() + 18)
        legend_width = rect.width() - legend_left - 12
        legend_font = painter.font()
        legend_font.setBold(False)
        legend_font.setPointSize(9)
        painter.setFont(legend_font)
        metrics = painter.fontMetrics()
        y = 50
        for index, (name, value) in enumerate(totals[:7]):
            color = QColor(self.COLORS[index % len(self.COLORS)])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(legend_left, y + 5, 10, 10), 3, 3)
            percent = f"{value / total * 100:.0f}%"
            text = metrics.elidedText(f"{name} · {format_duration(value)} · {percent}", Qt.TextElideMode.ElideRight, legend_width - 18)
            painter.setPen(QColor("#273449"))
            row_rect = QRectF(legend_left + 18, y, legend_width - 18, 20)
            painter.drawText(row_rect, Qt.AlignmentFlag.AlignVCenter, text)
            attention = next((a for n, a, _b in self.data if n == name), 0.0)
            background = next((b for n, _a, b in self.data if n == name), 0.0)
            self._legend_rects.append((QRectF(legend_left, y, legend_width, 20), name, value, attention, background))
            y += 24
        painter.end()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        totals = [(name, attention + background) for name, attention, background in self.data if attention + background > 0]
        total = sum(value for _, value in totals)
        for rect, name, value, attention, background in self._legend_rects:
            if rect.contains(event.position()):
                pct = value / total * 100.0 if total > 0 else 0.0
                self.setToolTip(
                    f"{name} · {format_duration(value)} · {pct:.1f}%\n"
                    f"注视 {format_duration(attention)} · 播放/后台 {format_duration(background)}"
                )
                return
        self._update_tooltip()


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

        self.online_category_lookup_box = QCheckBox("联网增强程序/网页分类（可选，仅本地规则为“其他”时使用）")
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

        idle_row = QHBoxLayout()
        idle_label = QLabel("空闲阈值（秒）")
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(30, 3600)
        self.idle_spin.setSingleStep(30)
        self.idle_spin.setValue(settings.idle_threshold_seconds)
        idle_row.addWidget(idle_label)
        idle_row.addWidget(self.idle_spin, 1)
        general_layout.addLayout(idle_row)

        retention_row = QHBoxLayout()
        retention_label = QLabel("时间线保留（天，0 为永久）")
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(0, 3650)
        self.retention_spin.setSingleStep(30)
        self.retention_spin.setValue(settings.timeline_retention_days)
        retention_row.addWidget(retention_label)
        retention_row.addWidget(self.retention_spin, 1)
        general_layout.addLayout(retention_row)

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
        category_layout.addWidget(QLabel("网页/内容分类规则（target: app / domain / title / any）"))
        self.category_table = QTableWidget(0, 3)
        self.category_table.setHorizontalHeaderLabels(["关键词", "分类", "匹配位置"])
        self.category_table.verticalHeader().setVisible(False)
        self.category_table.horizontalHeader().setStretchLastSection(True)
        self.category_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row in self.storage.category_rules():
            self._append_category_rule(str(row["pattern"]), str(row["category"]), str(row["target"]))
        category_layout.addWidget(self.category_table, 1)

        category_row = QHBoxLayout()
        self.category_pattern_input = QLineEdit()
        self.category_pattern_input.setPlaceholderText("例如: 原神 / coursera.org / steam.exe")
        self.category_name_input = QLineEdit()
        self.category_name_input.setPlaceholderText("例如: 游戏 / 学习")
        self.category_target_combo = QComboBox()
        self.category_target_combo.addItems(["title", "domain", "app", "any"])
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
        self.settings_tabs.addTab(category_panel, "分类规则")

        goal_panel = QFrame()
        goal_panel.setObjectName("settingsPanel")
        goal_layout = QVBoxLayout(goal_panel)
        goal_layout.setContentsMargins(12, 12, 12, 12)
        goal_layout.setSpacing(8)
        goal_desc = QLabel("设置学习与使用时长目标，查看连续达标天数。指标：category=分类, domain=域名, app=程序, learning_topic=学习主题")
        goal_desc.setWordWrap(True)
        goal_layout.addWidget(goal_desc)
        self.goal_table = QTableWidget(0, 6)
        self.goal_table.setHorizontalHeaderLabels(["目标名称", "指标类型", "匹配模式", "目标小时", "方向", "启用"])
        self.goal_table.verticalHeader().setVisible(False)
        self.goal_table.horizontalHeader().setStretchLastSection(True)
        self.goal_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.goal_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.goal_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.goal_table.setMaximumHeight(160)
        self._populate_goal_table()
        goal_layout.addWidget(self.goal_table)
        goal_form = QHBoxLayout()
        self.goal_name_input = QLineEdit()
        self.goal_name_input.setPlaceholderText("目标名称")
        self.goal_metric_combo = QComboBox()
        self.goal_metric_combo.addItems(["category", "domain", "app", "learning_topic"])
        self.goal_metric_combo.setMaximumWidth(120)
        self.goal_pattern_input = QLineEdit()
        self.goal_pattern_input.setPlaceholderText("匹配模式（如 学习 或留空=全部）")
        self.goal_target_spin = QDoubleSpinBox()
        self.goal_target_spin.setRange(0.1, 168.0)
        self.goal_target_spin.setValue(1.0)
        self.goal_target_spin.setSuffix("h")
        self.goal_target_spin.setMaximumWidth(80)
        self.goal_direction_combo = QComboBox()
        self.goal_direction_combo.addItems(["至少", "不超过"])
        self.goal_direction_combo.setMaximumWidth(80)
        self.goal_enabled_box = QCheckBox("启用")
        self.goal_enabled_box.setChecked(True)
        add_goal_btn = QPushButton("添加/更新")
        add_goal_btn.clicked.connect(self.add_or_update_goal)
        del_goal_btn = QPushButton("删除选中")
        del_goal_btn.clicked.connect(self.delete_selected_goal)
        for w in (self.goal_name_input, self.goal_metric_combo, self.goal_pattern_input,
                  self.goal_target_spin, self.goal_direction_combo, self.goal_enabled_box,
                  add_goal_btn, del_goal_btn):
            goal_form.addWidget(w)
        goal_layout.addLayout(goal_form)
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
        data_layout.addWidget(danger_label)
        data_layout.addWidget(clear_button, 0, Qt.AlignmentFlag.AlignLeft)
        data_layout.addStretch(1)
        self.settings_tabs.addTab(data_panel, "数据")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.setStyleSheet(
            """
            QDialog { background: #f6f8fb; color: #17202a; font-family: "Microsoft YaHei UI", "Segoe UI"; }
            QFrame#settingsPanel { background: white; border: 1px solid #d9e1ea; border-radius: 8px; }
            QLabel#sectionLabel { color: #607089; font-weight: 700; }
            QLineEdit, QListWidget, QComboBox, QTableWidget {
                border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px; background: white;
            }
            QPushButton { padding: 6px 10px; border: 1px solid #b9c6d4; border-radius: 6px; background: #ffffff; }
            QPushButton:disabled, QCheckBox:disabled { color: #94a3b8; }
            QPushButton:hover { background: #eef6ff; }
            """
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
        category_tip = "联网增强程序/网页分类；仅在关闭隐私模式且本地规则不确定时生效。"
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

    def _append_category_rule(self, pattern: str, category: str, target: str) -> None:
        row = self.category_table.rowCount()
        self.category_table.insertRow(row)
        for col, value in enumerate((pattern, category, target)):
            self.category_table.setItem(row, col, QTableWidgetItem(value))

    def add_category_rule(self) -> None:
        pattern = self.category_pattern_input.text().strip().lower()
        category = self.category_name_input.text().strip() or "其他"
        target = str(self.category_target_combo.currentText()).strip() or "any"
        if not pattern:
            return
        self._append_category_rule(pattern, category, target)
        self.category_pattern_input.clear()
        self.category_name_input.clear()

    def remove_selected_category_rules(self) -> None:
        rows = sorted({index.row() for index in self.category_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.category_table.removeRow(row)

    def restore_default_category_rules(self) -> None:
        self.category_table.setRowCount(0)
        for pattern, category, target in DEFAULT_CATEGORY_RULES:
            self._append_category_rule(pattern, category, target)

    def category_rule_rows(self) -> list[tuple[str, str, str]]:
        rules = []
        for row in range(self.category_table.rowCount()):
            values = []
            for col in range(3):
                item = self.category_table.item(row, col)
                values.append(item.text().strip() if item else "")
            pattern, category, target = values
            if pattern:
                rules.append((pattern, category or "其他", target or "any"))
        return rules

    def ignored_names(self) -> list[str]:
        names = []
        for index in range(self.ignore_list.count()):
            item = self.ignore_list.item(index)
            if isinstance(item, QListWidgetItem):
                names.append(item.text())
        return names

    def export_csv(self) -> None:
        default_name = f"usage-widget-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self.storage.export_csv(Path(path))
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")

    def export_content_csv(self) -> None:
        default_name = f"usage-widget-content-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出内容 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self.storage.export_content_csv(Path(path))
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")

    def export_music_csv(self) -> None:
        default_name = f"usage-widget-music-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出音乐分析 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self.storage.export_music_csv(Path(path))
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")

    def export_learning_csv(self) -> None:
        default_name = f"usage-widget-learning-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出学习分析 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self.storage.export_learning_csv(Path(path))
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")

    def clear_usage_data(self) -> None:
        answer = QMessageBox.warning(
            self,
            "清除数据",
            "这会删除所有已记录的使用时长，忽略列表和设置会保留。",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.storage.delete_usage()
            self.data_changed.emit()

    def backup_database(self) -> None:
        default_name = f"usage-widget-db-{date.today().isoformat()}.sqlite"
        path, _ = QFileDialog.getSaveFileName(self, "备份数据库", default_name, "SQLite Database (*.sqlite *.db)")
        if not path:
            return
        self.storage.backup_database(Path(path))
        QMessageBox.information(self, "备份完成", f"已备份到：\n{path}")

    def optimize_database(self) -> None:
        self.storage.optimize_database()
        QMessageBox.information(self, "优化完成", "数据库索引统计和 WAL 检查点已更新。")

    def cleanup_timeline(self) -> None:
        retention_days = self.retention_spin.value()
        if retention_days <= 0:
            QMessageBox.information(self, "未清理", "当前设置为永久保留时间线。")
            return
        removed = self.storage.cleanup_old_timeline_events(retention_days)
        self.data_changed.emit()
        QMessageBox.information(self, "清理完成", f"已清理 {removed} 条旧时间线事件，保留最近 {retention_days} 天。")

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

    def _populate_goal_table(self) -> None:
        self.goal_table.setRowCount(0)
        for row_data in self.storage.goal_rows_all():
            self._add_goal_row(row_data)

    def _add_goal_row(self, row_data) -> None:
        r = self.goal_table.rowCount()
        self.goal_table.insertRow(r)
        self.goal_table.setItem(r, 0, QTableWidgetItem(str(row_data["name"])))
        self.goal_table.setItem(r, 1, QTableWidgetItem(str(row_data["metric"])))
        self.goal_table.setItem(r, 2, QTableWidgetItem(str(row_data["pattern"])))
        hours = float(row_data["target_seconds"]) / 3600.0
        self.goal_table.setItem(r, 3, QTableWidgetItem(f"{hours:.1f}"))
        direction_text = "至少" if str(row_data["direction"]) == "min" else "不超过"
        self.goal_table.setItem(r, 4, QTableWidgetItem(direction_text))
        self.goal_table.setItem(r, 5, QTableWidgetItem("是" if int(row_data["enabled"]) else "否"))

    def add_or_update_goal(self) -> None:
        name = self.goal_name_input.text().strip()
        if not name:
            return
        metric = str(self.goal_metric_combo.currentText())
        pattern = self.goal_pattern_input.text().strip()
        target_hours = self.goal_target_spin.value()
        direction = "min" if str(self.goal_direction_combo.currentText()) == "至少" else "max"
        enabled = 1 if self.goal_enabled_box.isChecked() else 0
        self.storage.upsert_goal(name, metric, pattern, target_hours * 3600, direction, enabled)
        self._populate_goal_table()
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
            QDialog { background: #f6f8fb; color: #17202a; font-family: "Microsoft YaHei UI", "Segoe UI"; }
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
            """
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
        rows = [
            ("数据库路径", str(self.storage.db_path)),
            ("数据库大小", self._format_size(self.storage.database_size_bytes())),
            ("进程日汇总行数", str(db_stats.get("usage_daily_rows", 0))),
            ("内容日汇总行数", str(db_stats.get("content_usage_daily_rows", 0))),
            ("时间线事件行数", str(db_stats.get("timeline_events_rows", 0))),
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
            ("学习主题分类", online_feature_state(settings.online_category_lookup, settings.private_title_mode)),
            ("学习主题来源", self.monitor.learning_classifier.last_source or "无"),
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
            parts.append("video")
        if getattr(latest_tab, "has_audio", False):
            parts.append("audio")
        if getattr(latest_tab, "muted", False):
            parts.append("muted")
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
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(title)
        header.addStretch(1)
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
            QDialog { background: #f6f8fb; color: #17202a; font-family: "Microsoft YaHei UI", "Segoe UI"; }
            QLabel#statsTitle { font-size: 18px; font-weight: 700; }
            QLabel#statsNote { color: #607089; }
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
            """
        )
        self.refresh()

    def _browser_media_detail(self, latest_tab) -> str:
        if not latest_tab:
            return "无"
        parts = []
        if getattr(latest_tab, "has_video", False):
            parts.append("video")
        if getattr(latest_tab, "has_audio", False):
            parts.append("audio")
        if getattr(latest_tab, "muted", False):
            parts.append("muted")
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
        settings = self.storage.load_settings()
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
            ("空闲状态", f"{'空闲' if self.monitor.is_idle else '活动'} · {format_duration(self.monitor.idle_seconds)}"),
            ("前台程序", self.monitor.foreground_path or "未识别"),
            ("前台标题", self.monitor.foreground_title[:160] or "无"),
            ("当前网页", latest_web),
            ("网页媒体元素", self._browser_media_detail(latest_tab)),
            ("当前视频", current_video),
            ("当前音乐", current_music),
            ("发声标签页", f"{len(audible_tabs)} 个"),
            ("系统媒体会话", "可用" if self.monitor.media_provider.available else "不可用/使用兜底"),
            ("当前媒体项", f"{len(media_items)} 个"),
            ("浏览器扩展", "最近有活动标签页上报" if latest_tab else "最近无活动标签页上报"),
            ("页面内容信号", f"{self.monitor.browser_bridge.page_signal_count()} 条/小时"),
            ("联网音乐校验", online_feature_state(settings.online_music_lookup, settings.private_title_mode)),
            ("联网分类增强", online_feature_state(settings.online_category_lookup, settings.private_title_mode)),
            ("学习主题识别", online_feature_state(settings.online_category_lookup, settings.private_title_mode)),
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
        self.setWindowTitle(f"使用数据分析 · v{__version__}")
        self.setWindowIcon(build_app_icon())
        self.setMinimumSize(1020, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("使用数据分析")
        title.setObjectName("statsTitle")
        self.range_combo = QComboBox()
        self.range_combo.addItem("今天", "today")
        self.range_combo.addItem("昨天", "yesterday")
        self.range_combo.addItem("最近 7 天", "7d")
        self.range_combo.addItem("最近 30 天", "30d")
        self.range_combo.addItem("本周", "week")
        self.range_combo.currentIndexChanged.connect(self.refresh)
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
        report_button = QPushButton("导出报告")
        report_button.clicked.connect(self.export_report)
        music_export_button = QPushButton("导出音乐")
        music_export_button.clicked.connect(self.export_music_csv)
        learning_export_button = QPushButton("导出学习")
        learning_export_button.clicked.connect(self.export_learning_csv)
        definition_button = QPushButton("数据口径")
        definition_button.clicked.connect(self.show_data_definitions)
        header.addWidget(title)
        header.addWidget(self.range_combo)
        header.addStretch(1)
        header.addWidget(self.learning_total)
        header.addWidget(self.foreground_total)
        header.addWidget(self.video_total)
        header.addWidget(self.media_total)
        header.addWidget(self.detail_status)
        header.addWidget(definition_button)
        header.addWidget(music_export_button)
        header.addWidget(learning_export_button)
        header.addWidget(report_button)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.overview_tab = self._make_overview_tab()
        self.trend_tab = self._make_trend_tab()
        self.process_table = self._make_table(["程序", "前台时长", "总运行", "后台", "路径"], sort_column=1)
        self.web_table = self._make_table(["网页/网站标题", "域名", "分类", "主题", "浏览器", "注视时长", "URL"], sort_column=5)
        self.video_table = self._make_table(["视频/发声标签页", "域名", "分类", "主题", "播放时长", "URL"], sort_column=4)
        self.media_table = self._make_table(["播放内容", "分类", "来源", "播放时长", "最后记录"], sort_column=3)
        self.music_analysis_table = self._make_table(["歌曲", "歌手", "来源", "播放时长", "占音乐时长", "最后记录"], sort_column=3)
        self.music_analysis_tab = self._make_music_analysis_tab()
        self.artist_analysis_table = self._make_table(["歌手", "播放时长", "歌曲数", "代表歌曲", "来源", "占音乐时长"], sort_column=1)
        self.artist_analysis_tab = self._make_artist_analysis_tab()
        self.learning_analysis_table = self._make_table(["学习主题", "网页注视时长", "视频/播放时长", "总时长", "条目数", "最后记录"], sort_column=3)
        self.learning_analysis_tab = self._make_learning_analysis_tab()
        self.window_table = self._make_table(["窗口标题", "分类", "主题", "程序", "注视时长", "最后记录"], sort_column=4)
        self.category_table = self._make_table(["分类", "总时长", "占比", "注视时长", "播放/后台", "条目数", "来源类型", "最后记录"], sort_column=1)
        self.goal_table = self._make_table(["目标", "方向", "当前", "目标值", "状态"], sort_column=2)
        self.timeline_table = self._make_table(["开始", "类型", "标题", "应用", "分类", "主题", "时长"], sort_column=0)
        self.timeline_tab = self._make_timeline_tab()
        for table, kind in (
            (self.web_table, "web"),
            (self.video_table, "video"),
            (self.media_table, "media"),
            (self.window_table, "window"),
        ):
            self._install_category_menu(table, kind)
        # Domain and video-domain tables (created here, populated later)
        self.domain_table = self._make_table(["网站域名", "浏览时长", "网页数", "主要页面", "最后访问"], 1)
        self.video_domain_table = self._make_table(["视频来源", "播放时长", "视频数", "主要视频", "分类", "最后播放"], 1)

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
            "视频播放", self.video_table,
            "视频来源", self.video_domain_table,
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
        self.tabs.addTab(self.video_tab, "视频")
        self.tabs.addTab(self.music_tab, "音乐")
        self.tabs.addTab(self.learning_analysis_tab, "学习")
        self.tabs.addTab(self.category_table, "分类")
        self.tabs.addTab(self.goal_table, "目标")
        self.tabs.addTab(self.timeline_tab, "时间线")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

        note = QLabel("网页注视和窗口标题统计的是前台焦点；音乐播放统计的是后台播放内容，两者不会混在一起计算。")
        note.setObjectName("statsNote")
        note.setWordWrap(True)
        root.addWidget(note)

        self.setStyleSheet(
            """
            QDialog { background: #f6f8fb; color: #17202a; font-family: "Microsoft YaHei UI", "Segoe UI"; }
            QLabel#statsTitle { font-size: 18px; font-weight: 700; }
            QLabel#statsNote { color: #607089; }
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
            QLabel#timelineHint {
                color: #607089;
                padding: 3px 4px;
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
            """
        )
        QTimer.singleShot(0, self.refresh)

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
        self.learning_today_card = StatCard("学习总时长", "#55b88d")
        self.learning_today_card.setMinimumHeight(100)
        learn_row.addWidget(self.learning_today_card, 2)
        self.focus_card = StatCard("前台注视", "#1677d2")
        self.web_card = StatCard("网页注视", "#4a90c4")
        learn_row.addWidget(self.focus_card, 1)
        learn_row.addWidget(self.web_card, 1)
        layout.addLayout(learn_row)

        # Row 2: Secondary metrics
        sec_row = QHBoxLayout()
        sec_row.setSpacing(10)
        self.video_card = StatCard("视频播放", "#f0a33a")
        self.music_card = StatCard("音乐播放", "#d95f76")
        sec_row.addWidget(self.video_card, 1)
        sec_row.addWidget(self.music_card, 1)
        layout.addLayout(sec_row)

        self.streak_label = QLabel("")
        self.streak_label.setObjectName("streakLabel")
        self.streak_label.setStyleSheet("color: #f0a33a; font-size: 13px; font-weight: 700; padding: 4px 10px; background: #fff8e6; border-radius: 6px;")
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
        self.line_chart = LineChartWidget("本周 vs 上周")
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
        self.music_analysis_total = StatCard("音乐总时长", "#d95f76")
        self.music_analysis_count = StatCard("去重歌曲", "#55b88d")
        self.music_analysis_top = StatCard("最常听", "#1677d2")
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
        self.artist_analysis_total = StatCard("歌手总时长", "#d95f76")
        self.artist_analysis_count = StatCard("去重歌手", "#8b72d9")
        self.artist_analysis_top = StatCard("最爱歌手", "#1677d2")
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
        self.learning_analysis_total = StatCard("学习总时长", "#1677d2")
        self.learning_analysis_count = StatCard("去重主题数", "#55b88d")
        self.learning_analysis_top = StatCard("最常学主题", "#f0a33a")
        for card in (self.learning_analysis_total, self.learning_analysis_count, self.learning_analysis_top):
            summary_layout.addWidget(card, 1)
        layout.addWidget(summary)
        layout.addWidget(self.learning_analysis_table, 1)
        return tab

    def _make_timeline_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.timeline_hint = QLabel("时间线按需加载，默认只显示最近 120 条，避免大量历史事件导致界面卡顿。")
        self.timeline_hint.setObjectName("timelineHint")
        self.timeline_more_button = QPushButton("加载更多")
        self.timeline_more_button.setToolTip("每次增加 200 条时间线记录")
        self.timeline_more_button.clicked.connect(self._load_more_timeline)
        header.addWidget(self.timeline_hint, 1)
        header.addWidget(self.timeline_more_button)
        layout.addLayout(header)
        layout.addWidget(self.timeline_table, 1)
        return tab

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
        return table

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

    def _show_category_menu(self, table: QTableWidget, kind: str, pos: QPoint) -> None:
        row = table.rowAt(pos.y())
        if row < 0:
            return
        table.selectRow(row)
        pattern, target = self._category_rule_source(table, kind, row)
        if not pattern:
            return
        menu = QMenu(self)
        for category in ("学习", "编程", "AI 工具", "系统软件", "聊天", "游戏", "视频", "音乐", "娱乐", "社交", "办公", "工具", "网站", "购物", "新闻", "其他"):
            action = QAction(f"以后归为：{category}", self)
            action.triggered.connect(lambda _checked=False, cat=category: self._apply_category_correction(table, pattern, target, cat))
            menu.addAction(action)
        menu.addSeparator()
        custom_action = QAction("输入自定义分类...", self)
        custom_action.triggered.connect(lambda: self._prompt_category_correction(table, pattern, target))
        menu.addAction(custom_action)
        menu.exec(table.viewport().mapToGlobal(pos))

    def _cell_text(self, table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        return item.text().strip() if item else ""

    def _category_rule_source(self, table: QTableWidget, kind: str, row: int) -> tuple[str, str]:
        if kind in {"web", "video"}:
            domain = self._cell_text(table, row, 1).lower()
            title = self._cell_text(table, row, 0).lower()
            return (domain, "domain") if domain else (title[:80], "title")
        if kind == "media":
            source = self._cell_text(table, row, 2).lower()
            title = self._cell_text(table, row, 0).lower()
            if source and source not in {"browser", "browser-extension"}:
                return source, "app"
            return title[:80], "title"
        if kind == "window":
            app = self._cell_text(table, row, 3).lower()
            title = self._cell_text(table, row, 0).lower()
            return (app, "app") if app else (title[:80], "title")
        return "", "any"

    def _apply_category_correction(self, table: QTableWidget, pattern: str, target: str, category: str) -> None:
        self.storage.add_category_rule(pattern, category, target, update_existing=True)
        self.refresh()
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_open_dialogs"):
            QTimer.singleShot(0, parent.refresh_open_dialogs)  # type: ignore[attr-defined]
        QMessageBox.information(
            self,
            "分类规则已保存",
            f"已添加规则：{target} 包含“{pattern}”时归为“{category}”。",
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
            "video_playback": "视频",
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

    def _date_range_key(self) -> str:
        start_date, end_date = self.storage.date_range_for_preset(self._range_key())
        return f"{start_date.isoformat()}:{end_date.isoformat()}:{self._timeline_limit}"

    def _is_timeline_tab_active(self) -> bool:
        return self.tabs.currentWidget() is self.timeline_tab

    def _on_tab_changed(self, _index: int) -> None:
        if self._is_timeline_tab_active() and self._timeline_loaded_key != self._date_range_key():
            QTimer.singleShot(0, self.refresh)

    def _load_more_timeline(self) -> None:
        self._timeline_limit = min(self._timeline_limit + 200, 2000)
        self._timeline_loaded_key = ""
        self.refresh()

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
                return f"↑ {pct_str}", "#55b88d"
            elif pct < 0:
                return f"↓ {pct_str}", "#d95f76"
        return "—", "#738196"

    def _on_line_metric_changed(self) -> None:
        if not self._refreshing:
            self.refresh()

    def _on_heatmap_metric_changed(self) -> None:
        if not self._refreshing:
            self.refresh()

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        if hasattr(self, "refresh_button"):
            self.refresh_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._do_refresh()
        finally:
            QApplication.restoreOverrideCursor()
            if hasattr(self, "refresh_button"):
                self.refresh_button.setEnabled(True)
            self._refreshing = False

    def _do_refresh(self) -> None:
        start_date, end_date = self.storage.date_range_for_preset(self._range_key())
        active_timeline = self._is_timeline_tab_active()
        # ---- All queries (synchronous, fast with indexes) ----
        foreground = self.storage.foreground_total_range(start_date, end_date)
        media = self.storage.media_total_range(start_date, end_date)
        video = self.storage.video_total_range(start_date, end_date)
        learning_total = self.storage.learning_total_range(start_date, end_date)
        learning_topics_count = len(self.storage.learning_topic_summary_range(start_date, end_date, limit=100))
        process_rows = list(self.storage.process_rows_range(start_date, end_date, limit=120))
        web_rows = list(self.storage.content_rows_range(start_date, end_date, kind="web_page", limit=200))
        vp_rows = list(self.storage.content_rows_range(start_date, end_date, kind="video_playback", limit=200))
        mp_rows = list(self.storage.music_playback_rows_range(start_date, end_date, limit=200))
        win_rows = list(self.storage.content_rows_range(start_date, end_date, kind="window_title", limit=200))
        cat_rows = list(self.storage.category_summary_range(start_date, end_date))
        hourly_rows = self.storage.hourly_activity_range(start_date, end_date)
        tl_rows = list(self.storage.timeline_rows_range(start_date, end_date, limit=self._timeline_limit)) if active_timeline else []
        domain_rows = list(self.storage.domain_summary_range(start_date, end_date, limit=100))
        vd_rows = list(self.storage.video_domain_summary_range(start_date, end_date, limit=100))
        music_analysis = self.storage.music_analysis_range(start_date, end_date, limit=200)
        artist_data = self.storage.artist_summary_range(start_date, end_date, limit=80)
        learning_data = self.storage.learning_topic_summary_range(start_date, end_date, limit=200)
        goal_progress = self.storage.goal_progress_range(start_date, end_date)
        goal_streaks = {str(g["goal"]["name"]): self.storage.goal_streak(str(g["goal"]["name"])) for g in goal_progress}

        # ---- Top totals ----
        self.foreground_total.setText(f"前台注视 {format_duration(foreground)}")
        self.video_total.setText(f"视频播放 {format_duration(video)}")
        self.media_total.setText(f"音乐播放 {format_duration(media)}")
        self.learning_total.setText(f"学习 {format_duration(learning_total)}")
        self.detail_status.setText(
            f"{start_date.isoformat()} ~ {end_date.isoformat()} · "
            f"程序 {len(process_rows)} · 网页 {len(web_rows)} · 视频 {len(vp_rows)} · 分类 {len(cat_rows)}"
        )

        # ---- Overview cards ----
        web_total = sum(float(r["attention_seconds"] or 0) for r in web_rows)
        web_domains = len({str(r["content_domain"]) for r in web_rows if str(r["content_domain"]).strip()})
        self.focus_card.set_data(foreground, f"{len(process_rows)} programs")
        self.web_card.set_data(web_total, f"{web_domains} domains")
        self.video_card.set_data(video, f"{len(vp_rows)} videos")
        self.music_card.set_data(media, f"{len(mp_rows)} tracks")
        self.learning_today_card.set_data(learning_total, f"{learning_topics_count} topics")

        # ---- Charts ----
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
        self._set_rows(self.process_table, [[
            str(r["exe_name"]),
            self._duration_cell(float(r["foreground_seconds"] or 0)),
            self._duration_cell(float(r["running_seconds"] or 0)),
            self._duration_cell(max(0.0, float(r["running_seconds"] or 0) - float(r["foreground_seconds"] or 0))),
            str(r["exe_path"]),
        ] for r in process_rows])

        self._set_rows(self.web_table, [[
            str(r["content_title"]), str(r["content_domain"]), str(r["category"]),
            str(r["learning_topic"] or "-"),
            str(r["exe_name"]), self._duration_cell(float(r["attention_seconds"] or 0)),
            str(r["content_url"]),
        ] for r in web_rows])

        self._set_rows(self.video_table, [[
            str(r["content_title"]), str(r["content_domain"]), str(r["category"]),
            str(r["learning_topic"] or "-"),
            self._duration_cell(float(r["background_seconds"] or 0)), str(r["content_url"]),
        ] for r in vp_rows])

        self._set_rows(self.media_table, [[
            str(r["content_title"]), str(r["category"]), str(r["exe_name"]),
            self._duration_cell(float(r["background_seconds"] or 0)), str(r["last_seen"]),
        ] for r in mp_rows])

        self._set_rows(self.window_table, [[
            str(r["content_title"]), str(r["category"]), str(r["learning_topic"] or "-"), str(r["exe_name"]),
            self._duration_cell(float(r["attention_seconds"] or 0)), str(r["last_seen"]),
        ] for r in win_rows])

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
        self._set_rows(self.domain_table, [[
            str(r["content_domain"]).replace("（无域名 - 需安装浏览器扩展）|", ""),
            self._duration_cell(float(r["attention_seconds"] or 0)),
            str(r["page_count"]),
            " / ".join((str(r["top_titles"] or "").split(","))[:3]) or "-",
            str(r["last_seen"]),
        ] for r in domain_rows])

        self._set_rows(self.video_domain_table, [[
            str(r["content_domain"]).replace("（无域名 - 需安装浏览器扩展）|", ""),
            self._duration_cell(float(r["total_seconds"] or 0)),
            str(r["video_count"]),
            " / ".join((str(r["top_titles"] or "").split(","))[:3]) or "-",
            str(r["category"]), str(r["last_seen"]),
        ] for r in vd_rows])

        # ---- Music analysis ----
        ma_rows = [[
            str(r["song"]), str(r["artist"]),
            " / ".join(str(s) for s in r["sources"])[:80],
            self._duration_cell(float(r["seconds"])),
            (f"{float(r['percent']):.1f}%", float(r["percent"])),
            str(r["last_seen"]),
        ] for r in music_analysis]
        self._set_rows(self.music_analysis_table, ma_rows)
        self.music_analysis_total.set_data(media, f"{len(mp_rows)} tracks")
        self.music_analysis_count.set_data(str(len(ma_rows)), "by song+artist")
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
        lr_rows = [[
            str(r["learning_topic"]),
            self._duration_cell(float(r["attention_seconds"] or 0)),
            self._duration_cell(float(r["background_seconds"] or 0)),
            self._duration_cell(float(r["total_seconds"] or 0)),
            str(r["item_count"]), str(r["last_seen"]),
        ] for r in learning_data]
        self._set_rows(self.learning_analysis_table, lr_rows)
        self.learning_analysis_total.set_data(learning_total, f"{len(learning_data)} topics")

        # ---- Goals ----
        goal_rows = []
        goal_colors = []
        streak_parts = []
        for item in goal_progress:
            g = item["goal"]
            val, target = float(item["value"]), float(item["target"])
            ok = bool(item["ok"])
            ratio = val / target if target > 0 else 0
            if ok:
                st, color = "达标", "#55b88d"
            elif ratio >= 0.7:
                st, color = "接近", "#f0a33a"
            else:
                st, color = "未达标", "#d95f76"
            goal_rows.append([
                str(g["name"]), "at least" if g["direction"] == "min" else "max",
                self._duration_cell(val), self._duration_cell(target), st,
            ])
            goal_colors.append(color)
            streak = goal_streaks.get(str(g["name"]), 0)
            if streak > 0:
                streak_parts.append(f"{g['name']} {streak}d")
        self._set_rows(self.goal_table, goal_rows)
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
                str(r["start_time"]), str(r["kind"]), str(r["title"]),
                str(r["app_name"]), str(r["category"]),
                str(r["learning_topic"] or "-"),
                self._duration_cell(float(r["seconds"] or 0)),
            ] for r in tl_rows]
            self._set_rows(self.timeline_table, tl_table_rows)
            self._timeline_loaded_key = self._date_range_key()
            more_text = "可继续加载更多" if len(tl_rows) >= self._timeline_limit else "已显示当前范围内全部可用记录"
            self.timeline_hint.setText(
                f"时间线已加载最近 {len(tl_rows)} 条 · 上限 {self._timeline_limit} · {more_text}"
            )
            self.timeline_more_button.setEnabled(len(tl_rows) >= self._timeline_limit and self._timeline_limit < 2000)
        elif self.timeline_table.rowCount() == 0:
            self.timeline_hint.setText("时间线按需加载：切换到本页后才查询最近事件，避免详情刷新时卡住。")

        # ---- Deferred charts: only render while the visual tabs are relevant.
        if self.tabs.currentWidget() in {self.overview_tab, self.trend_tab}:
            QTimer.singleShot(100, lambda: self._render_heatmap(start_date, end_date))

    def _render_heatmap(self, start_date, end_date) -> None:
        """Deferred: heavy heatmap + week comparison charts."""
        try:
            if hasattr(self, "line_chart"):
                metric_map = {"前台注视": "foreground", "视频播放": "video", "音乐播放": "music", "学习": "learning"}
                lm = metric_map.get(str(self.line_metric_combo.currentText()), "foreground")
                lbl = str(self.line_metric_combo.currentText())
                breakdown = self.storage.week_daily_breakdown(lm)
                self.line_chart.set_data(breakdown["this_week"], breakdown["last_week"], lbl)
        except Exception:
            pass
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
        except Exception:
            pass

    def export_report(self) -> None:
        start_date, end_date = self.storage.date_range_for_preset(str(self.range_combo.currentData()))
        default_name = f"usage-widget-report-{start_date.isoformat()}-{end_date.isoformat()}.html"
        path, _ = QFileDialog.getSaveFileName(self, "导出 HTML 报告", default_name, "HTML Files (*.html)")
        if not path:
            return
        self.storage.export_html_report(Path(path), start_date, end_date)
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")

    def export_music_csv(self) -> None:
        start_date, end_date = self.storage.date_range_for_preset(str(self.range_combo.currentData()))
        default_name = f"usage-widget-music-{start_date.isoformat()}-{end_date.isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出音乐分析 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self.storage.export_music_csv(Path(path), start_date, end_date)
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")

    def export_learning_csv(self) -> None:
        start_date, end_date = self.storage.date_range_for_preset(str(self.range_combo.currentData()))
        default_name = f"usage-widget-learning-{start_date.isoformat()}-{end_date.isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出学习分析 CSV", default_name, "CSV Files (*.csv)")
        if not path:
            return
        self.storage.export_learning_csv(Path(path), start_date, end_date)
        QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")


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
        self.apply_settings()
        self.restore_position()

        self.monitor.updated.connect(self.refresh)

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
        self.status_dot = QFrame()
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setProperty("state", "active")
        self.status_dot.setFixedSize(12, 12)
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

        self.collapse_button = self._make_header_button("固", "取消固定，改为悬停展开")
        self.collapse_button.clicked.connect(self.toggle_pin_mode)
        self.status_button = self._make_header_button("态", "当前状态")
        self.status_button.clicked.connect(self.open_status_center)
        self.stats_button = self._make_header_button("图", "数据详情")
        self.stats_button.clicked.connect(self.open_stats)
        self.settings_button = self._make_header_button("设", "设置")
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
        button.setFixedSize(34, 30)
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

    def _sync_tray_actions(self) -> None:
        if hasattr(self, "show_action"):
            self.show_action.setText("隐藏小组件" if self.isVisible() else "显示小组件")
        if hasattr(self, "pause_action"):
            self.pause_action.setText("恢复记录" if self.storage.load_settings().pause_tracking else "暂停记录")

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
            panel = "rgba(255, 255, 255, 22)"
            panel_hover = "rgba(255, 255, 255, 34)"
            border = "rgba(255, 255, 255, 48)"
            text = "#f5f7fb"
            muted = "#aeb8c7"
            accent = "#55d6be"
            idle = "#f0a33a"
            paused = "#d95f76"
        else:
            bg = f"rgba(248, 250, 252, {alpha})"
            panel = "rgba(255, 255, 255, 150)"
            panel_hover = "rgba(232, 241, 252, 180)"
            border = "rgba(110, 128, 150, 72)"
            text = "#162033"
            muted = "#607089"
            accent = "#1677d2"
            idle = "#d98b10"
            paused = "#d95f76"

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
                font-family: "Microsoft YaHei UI", "Segoe UI";
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
                background: #27ae60;
            }}
            QLabel#collapsedActivityBadge[category="编程"] {{
                background: #2c7be5;
            }}
            QLabel#collapsedActivityBadge[category="视频"] {{
                background: #e67e22;
            }}
            QLabel#collapsedActivityBadge[category="音乐"] {{
                background: #9b59b6;
            }}
            QLabel#collapsedActivityBadge[category="游戏"] {{
                background: #e74c3c;
            }}
            QLabel#collapsedActivityBadge[category="聊天"] {{
                background: #1abc9c;
            }}
            QLabel#collapsedActivityBadge[category="AI 工具"] {{
                background: #6c5ce7;
            }}
            QLabel#collapsedActivityBadge[category="娱乐"] {{
                background: #fd79a8;
            }}
            QLabel#collapsedActivityBadge[category="购物"] {{
                background: #e17055;
            }}
            QLabel#collapsedActivityBadge[category="新闻"] {{
                background: #636e72;
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
                background: {accent};
                border-radius: 6px;
            }}
            QFrame#statusDot[state="idle"] {{
                background: {idle};
            }}
            QFrame#statusDot[state="paused"] {{
                background: {paused};
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
                border: 1px solid transparent;
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
        apply_windows_backdrop(self, is_dark_theme(self.settings))
        self._last_widget_refresh = 0.0
        self._footer_cache_at = 0.0
        self._footer_cache_text = "当前运行 · " + self._top_list_sort_label()
        self.refresh()
        if not hasattr(self, "_summary_checked_today"):
            self._summary_checked_today = True
            QTimer.singleShot(800, self.check_daily_summary)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._position_save_timer.stop()
        self._hover_expand_timer.stop()
        self._hover_collapse_timer.stop()
        self.drag_pos = None
        self.drag_start_pos = None
        self.drag_moved = False
        if not self.settings.always_expanded:
            self.set_expanded(False)
        self.save_position()
        event.ignore()
        self.hide()
        self.show_action.setText("显示小组件")

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
        self.setFixedSize(width, height)
        self.keep_on_screen()

    def _expand_from_hover(self) -> None:
        if self._pointer_inside and not self.settings.always_expanded and self.is_collapsed:
            self.set_expanded(True)

    def _collapse_from_hover(self) -> None:
        if not self._pointer_inside and not self.settings.always_expanded and not self.drag_pos:
            self.set_expanded(False)

    def _sync_pin_button(self) -> None:
        if self.settings.always_expanded:
            self.collapse_button.setText("固")
            self.collapse_button.setToolTip("取消固定，改为悬停展开")
        else:
            self.collapse_button.setText("浮")
            self.collapse_button.setToolTip("固定展开")

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
            return cached
        path = Path(exe_path)
        if path.exists():
            icon = self.icon_provider.icon(QFileInfo(str(path)))
        else:
            icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
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
        if category and topic:
            return f"{category} · {topic}"
        if category and category not in ("其他", "工具", "网站", "浏览器", "系统软件", "办公"):
            if display_exe and display_exe.lower() != category:
                return f"{category} · {display_exe}"
            return category
        if topic:
            return f"学习 · {topic}"
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
        if self.isVisible():
            self._hover_expand_timer.stop()
            self._hover_collapse_timer.stop()
            self.drag_pos = None
            self.drag_start_pos = None
            self.drag_moved = False
            if not self.settings.always_expanded:
                self.set_expanded(False)
            self.hide()
            self._sync_tray_actions()
        else:
            self._pointer_inside = False
            if not self.settings.always_expanded:
                self.set_expanded(False)
            self.show()
            self.keep_on_screen()
            self.raise_()
            self.activateWindow()
            self._sync_tray_actions()

    def toggle_background_mode(self) -> None:
        if self.background_action.isChecked():
            self._hover_expand_timer.stop()
            self._hover_collapse_timer.stop()
            self.hide()
            self.show_action.setText("显示小组件")
        else:
            self.show()
            self.keep_on_screen()
            self.show_action.setText("隐藏小组件")
        self._sync_tray_actions()

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
            self.storage.export_csv(Path(path))
            self.tray.showMessage("UsageWidget", "CSV 导出完成", build_app_icon(), 2500)

    def export_content_csv(self) -> None:
        default_name = f"usage-widget-content-{date.today().isoformat()}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出内容 CSV", default_name, "CSV Files (*.csv)")
        if path:
            self.storage.export_content_csv(Path(path))
            self.tray.showMessage("UsageWidget", "内容 CSV 导出完成", build_app_icon(), 2500)
