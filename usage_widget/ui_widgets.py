from __future__ import annotations

import html
from datetime import date
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .timefmt import format_duration, format_duration_long
from .ui_palette import app_color, category_color

if TYPE_CHECKING:
    from .monitor import RunningProcess


def ui_scale(widget: QWidget) -> float:
    try:
        return max(1.0, min(2.25, widget.logicalDpiX() / 96.0))
    except Exception:
        return 1.0


def px(widget: QWidget, value: float, minimum: float | None = None) -> float:
    scaled = value * ui_scale(widget)
    return max(float(minimum), scaled) if minimum is not None else scaled


def format_axis_duration(seconds: float) -> str:
    if seconds <= 0:
        return "0"
    return format_duration(seconds)


def draw_empty_state(painter: QPainter, rect: QRectF, message: str) -> None:
    painter.save()
    box = rect.adjusted(18, 34, -18, -18)
    if box.width() < 80 or box.height() < 44:
        box = rect.adjusted(12, 28, -12, -12)
    pen = QPen(QColor("#cbd5e1"))
    pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(QColor("#f8fafc"))
    painter.drawRoundedRect(box, 8, 8)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#dbe5f0"))
    base_y = box.center().y() + 12
    bar_w = max(6.0, min(12.0, box.width() / 16))
    gap = bar_w * 0.8
    start_x = box.center().x() - (bar_w * 4 + gap * 3) / 2
    for i, height in enumerate((14, 24, 18, 30)):
        painter.drawRoundedRect(QRectF(start_x + i * (bar_w + gap), base_y - height, bar_w, height), 3, 3)
    painter.setPen(QColor("#738196"))
    painter.drawText(box.adjusted(10, 0, -10, -10), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, message)
    painter.restore()


class ProgressBarWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.value = 0.0
        self.accent = QColor(app_color("focus"))
        self.track = QColor(120, 140, 165, 55)
        self.setFixedHeight(int(px(self, 7, 6)))

    def set_value(self, value: float, accent: str) -> None:
        self.value = max(0.0, min(1.0, value))
        self.accent = QColor(accent)
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track_h = px(self, 4, 4)
        radius = track_h / 2
        rect = QRectF(0, max(0.0, (self.height() - track_h) / 2), self.width(), track_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.track)
        painter.drawRoundedRect(rect, radius, radius)
        if self.value > 0:
            painter.setBrush(self.accent)
            painter.drawRoundedRect(QRectF(rect.left(), rect.top(), rect.width() * self.value, rect.height()), radius, radius)
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
        self.ratio_label = QLabel("")
        self.ratio_label.setObjectName("processRatio")
        self.ratio_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.progress_bar = ProgressBarWidget()
        text_box.addWidget(self.name_label)
        text_box.addWidget(self.path_label)
        progress_row = QHBoxLayout()
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(6)
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.ratio_label)
        text_box.addLayout(progress_row)
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
        ratio_text = f"前台占比 {ratio * 100:.0f}%"
        self.ratio_label.setText(ratio_text)
        self.ratio_label.setToolTip("进度条表示今日前台时长 / 今日总运行时长")
        self.progress_bar.setToolTip(f"{ratio_text}（前台 / 总运行）")
        self.progress_bar.set_value(ratio, app_color("focus"))
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
            f"前台占比：{ratio * 100:.0f}%<br>"
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
        stripe_w = px(self, 4, 4)
        margin = px(self, 12, 12)
        painter.drawRoundedRect(QRectF(0, margin, stripe_w, self.height() - margin * 2), stripe_w / 2, stripe_w / 2)
        painter.end()


class BarChartWidget(QWidget):
    def __init__(self, title: str, accent: str = app_color("focus"), parent: QWidget | None = None) -> None:
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
            draw_empty_state(painter, QRectF(rect), "暂无数据")
            painter.end()
            return

        max_value = max([value for _, value, _ in self.data] or [1.0])
        chart_top = px(self, 40, 40)
        row_gap = px(self, 8, 8)
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

            track_rect = QRectF(bar_left, y + px(self, 5, 5), bar_width, max(px(self, 8, 8), row_height - px(self, 10, 10)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(track_color)
            painter.drawRoundedRect(track_rect, 5, 5)

            ratio = value / max_value if max_value else 0
            fill_width = max(px(self, 3, 3) if value > 0 else 0.0, track_rect.width() * ratio)
            fill_rect = QRectF(track_rect.left(), track_rect.top(), fill_width, track_rect.height())
            painter.setBrush(self.accent)
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
        "focus": QColor(app_color("focus")),
        "video": QColor(app_color("video")),
        "music": QColor(app_color("music")),
        "learn": QColor(app_color("learn")),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = "24 小时时间分布"
        self.data: list[tuple[int, float, float, float, float]] = []
        self._bar_rects: list[tuple[QRectF, int, float, float, float, float]] = []
        self._hover_hour: int | None = None
        self.setMouseTracking(True)
        self.setMinimumHeight(260)

    def set_data(self, rows: list[tuple[int, float, float, float, float]]) -> None:
        self.data = rows
        self._hover_hour = None
        self._update_tooltip()
        self.update()

    def _summary(self) -> dict[str, float | int]:
        focus_total = sum(row[1] for row in self.data)
        video_total = sum(row[2] for row in self.data)
        music_total = sum(row[3] for row in self.data)
        learn_total = sum(row[4] for row in self.data)
        active_hours = sum(1 for row in self.data if max(row[1], row[2], row[3], row[4]) > 0)
        peak = max(self.data, key=lambda row: max(row[1], row[2], row[3])) if self.data else (0, 0, 0, 0, 0)
        learn_peak = max(self.data, key=lambda row: row[4]) if self.data else (0, 0, 0, 0, 0)
        return {
            "focus": focus_total,
            "video": video_total,
            "music": music_total,
            "learn": learn_total,
            "active_hours": active_hours,
            "peak_hour": int(peak[0]),
            "peak_total": float(max(peak[1], peak[2], peak[3])),
            "learn_peak_hour": int(learn_peak[0]),
            "learn_peak_total": float(learn_peak[4]),
        }

    def _update_tooltip(self) -> None:
        if not self.data:
            self.setToolTip("暂无时间线数据")
            return
        summary = self._summary()
        self.setToolTip(
            "24 小时时间分布\n"
            f"前台总计：{format_duration(float(summary['focus']))}\n"
            f"视频总计：{format_duration(float(summary['video']))}\n"
            f"音乐总计：{format_duration(float(summary['music']))}\n"
            f"活跃小时：{int(summary['active_hours'])} 个\n"
            f"单项高峰：{int(summary['peak_hour']):02d}:00，{format_duration(float(summary['peak_total']))}\n"
            f"学习高峰：{int(summary['learn_peak_hour']):02d}:00，{format_duration(float(summary['learn_peak_total']))}"
        )

    def _draw_badges(self, painter: QPainter, rect: QRectF, summary: dict[str, float | int]) -> None:
        painter.save()
        font = painter.font()
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        badges = (
            ("前台", format_duration(float(summary["focus"]))),
            ("峰值", f"{int(summary['peak_hour']):02d}:00"),
            ("活跃", f"{int(summary['active_hours'])}h"),
        )
        x = rect.right()
        for label, value in reversed(badges):
            text = f"{label} {value}"
            width = min(118, max(64, painter.fontMetrics().horizontalAdvance(text) + 18))
            x -= width
            if x < rect.left() + 155:
                break
            badge = QRectF(x, rect.top(), width, 24)
            painter.setPen(QColor("#d9e1ea"))
            painter.setBrush(QColor("#f8fafc"))
            painter.drawRoundedRect(badge, 7, 7)
            painter.setPen(QColor("#475569"))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
            x -= 7
        painter.restore()

    def _draw_wrapped_legend(
        self,
        painter: QPainter,
        chart: QRectF,
        y: float,
        summary: dict[str, float | int],
    ) -> None:
        painter.save()
        font = painter.font()
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        x = chart.left()
        line_y = y
        legend_items = (
            ("前台", "focus", float(summary["focus"])),
            ("视频", "video", float(summary["video"])),
            ("音乐", "music", float(summary["music"])),
            ("学习标记", "learn", float(summary["learn"])),
        )
        for label, key, seconds in legend_items:
            text = f"{label} {format_duration(seconds)}"
            width = min(158, max(84, painter.fontMetrics().horizontalAdvance(text) + 30))
            if x + width > chart.right() and x > chart.left():
                x = chart.left()
                line_y += 22
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.COLORS[key])
            painter.drawRoundedRect(QRectF(x, line_y + 5, 10, 10), 3, 3)
            painter.setPen(QColor("#273449"))
            painter.drawText(QRectF(x + 16, line_y, width - 16, 20), Qt.AlignmentFlag.AlignVCenter, text)
            x += width + 12
        painter.restore()

    def _hover_row(self) -> tuple[int, float, float, float, float] | None:
        if self._hover_hour is None:
            return None
        for row in self.data:
            if int(row[0]) == self._hover_hour:
                return row
        return None

    def _draw_hover_card(self, painter: QPainter, chart: QRectF, bar_width: float, bar_gap: float) -> None:
        row = self._hover_row()
        if row is None:
            return
        hour, focus, video, music, learn = row
        peak = max(focus, video, music, learn)
        lines = [
            f"{hour:02d}:00 - {hour:02d}:59",
            f"单项最高 {format_duration(peak)}",
            f"前台 {format_duration(focus)}",
            f"视频 {format_duration(video)}",
            f"音乐 {format_duration(music)}",
            f"学习标记 {format_duration(learn)}",
        ]
        painter.save()
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        width = max(142, max(metrics.horizontalAdvance(text) for text in lines) + 22)
        height = 22 + (len(lines) - 1) * 17 + 12
        hour_slot = chart.width() / 24
        bar_center = chart.left() + hour * hour_slot + hour_slot / 2
        x = bar_center + 10
        if x + width > chart.right():
            x = bar_center - width - 10
        x = min(max(chart.left() + 4, x), chart.right() - width - 4)
        y = max(chart.top() + 4, chart.bottom() - height - 8)
        card = QRectF(x, y, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 34))
        painter.drawRoundedRect(card.translated(0, 2), 8, 8)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QColor("#cbd5e1"))
        painter.drawRoundedRect(card, 8, 8)
        painter.setPen(QColor("#0f172a"))
        title_font = QFont(font)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(x + 10, y + 7, width - 20, 16), Qt.AlignmentFlag.AlignLeft, lines[0])
        painter.setFont(font)
        painter.setPen(QColor("#334155"))
        text_y = y + 29
        for text in lines[1:]:
            painter.drawText(QRectF(x + 10, text_y, width - 20, 16), Qt.AlignmentFlag.AlignLeft, text)
            text_y += 17
        painter.restore()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        self._bar_rects = []

        painter.setPen(QColor("#17202a"))
        title_font = painter.font()
        title_font.setBold(True)
        title_font.setPointSize(10)
        painter.setFont(title_font)
        painter.drawText(QRectF(14, 9, rect.width() - 28, 24), Qt.AlignmentFlag.AlignLeft, self.title)

        if not self.data:
            draw_empty_state(painter, rect, "暂无时间线数据")
            painter.end()
            return

        summary = self._summary()
        if rect.width() >= 520:
            self._draw_badges(painter, QRectF(14, 8, rect.width() - 28, 24), summary)
            chart_top = 58
        else:
            painter.setPen(QColor("#64748b"))
            compact = (
                f"前台 {format_duration(float(summary['focus']))} · "
                f"峰值 {int(summary['peak_hour']):02d}:00"
            )
            painter.drawText(QRectF(14, 35, rect.width() - 28, 18), Qt.AlignmentFlag.AlignLeft, compact)
            chart_top = 64

        activity_totals = [max(focus, video, music) for _, focus, video, music, _learn in self.data]
        learning_totals = [learn for *_rest, learn in self.data]
        max_value = max(activity_totals + learning_totals + [1.0])
        footer_height = 76 if rect.width() >= 560 else 96
        chart_height = max(74.0, rect.height() - chart_top - footer_height)
        chart = QRectF(56, chart_top, rect.width() - 74, chart_height)
        bar_gap = px(self, 4, 4)
        hour_slot = chart.width() / 24
        bar_width = max(px(self, 2.8, 3), min(px(self, 8, 6), (hour_slot - px(self, 3, 3)) / 3))
        cluster_width = bar_width * 3
        learn_marker_r = px(self, 4, 4)

        grid_font = painter.font()
        grid_font.setBold(False)
        grid_font.setPointSize(7)
        painter.setFont(grid_font)
        axis_ticks = ((0.5, format_axis_duration(max_value * 0.5)), (1.0, format_axis_duration(max_value)))
        for ratio, label in axis_ticks:
            y = chart.bottom() - chart.height() * ratio
            painter.setPen(QColor("#edf2f7"))
            painter.drawLine(int(chart.left()), int(y), int(chart.right()), int(y))
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(QRectF(6, y - 8, chart.left() - 12, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
        painter.setPen(QColor("#d9e1ea"))
        painter.drawLine(int(chart.left()), int(chart.bottom()), int(chart.right()), int(chart.bottom()))
        painter.setPen(Qt.PenStyle.NoPen)

        peak_hour = int(summary["peak_hour"])
        peak_rect: QRectF | None = None
        for hour, focus, video, music, learn in self.data:
            slot_left = chart.left() + hour * hour_slot
            x = slot_left + max(0.0, (hour_slot - cluster_width) / 2)
            slot_rect = QRectF(slot_left, chart.top(), hour_slot, chart.height())
            if 8 <= hour <= 11:
                painter.setBrush(QColor("#f8fafc"))
                painter.drawRoundedRect(slot_rect, 3, 3)
            if self._hover_hour == hour:
                painter.setBrush(QColor(22, 119, 210, 32))
                painter.drawRoundedRect(slot_rect.adjusted(1, 0, -1, 0), 5, 5)
            if max(focus, video, music) <= 0:
                painter.setBrush(QColor("#e8eef5"))
                painter.drawRoundedRect(QRectF(x, chart.bottom() - px(self, 4, 4), cluster_width, px(self, 4, 4)), 2, 2)
            else:
                for series_index, (value, key) in enumerate(((focus, "focus"), (video, "video"), (music, "music"))):
                    bar_x = x + series_index * bar_width
                    if value <= 0:
                        continue
                    height = max(px(self, 2, 2), chart.height() * (value / max_value))
                    painter.setBrush(self.COLORS[key])
                    painter.drawRoundedRect(QRectF(bar_x, chart.bottom() - height, bar_width - 0.5, height), 2, 2)
            if learn > 0:
                learn_height = max(px(self, 3, 3), chart.height() * (learn / max_value))
                marker_center = x + cluster_width / 2
                painter.setBrush(self.COLORS["learn"])
                painter.setPen(QColor("#ffffff"))
                painter.drawEllipse(QRectF(marker_center - learn_marker_r, chart.bottom() - learn_height - learn_marker_r * 2 - 2, learn_marker_r * 2, learn_marker_r * 2))
                painter.setPen(Qt.PenStyle.NoPen)
            if hour == peak_hour:
                peak_height = max(px(self, 4, 4), chart.height() * (max(focus, video, music, learn) / max_value))
                peak_rect = QRectF(slot_left + 1, chart.bottom() - peak_height - 3, hour_slot - 2, peak_height + 5)
                painter.setBrush(QColor(22, 119, 210, 28))
                painter.setPen(QColor("#17202a"))
                painter.drawRoundedRect(peak_rect, 5, 5)
                painter.setPen(Qt.PenStyle.NoPen)
            self._bar_rects.append((slot_rect, hour, focus, video, music, learn))

        if peak_rect is not None and float(summary["peak_total"]) > 0:
            label_width = 84
            label_x = min(max(chart.left(), peak_rect.center().x() - label_width / 2), chart.right() - label_width)
            label_rect = QRectF(label_x, max(34, peak_rect.top() - 22), label_width, 18)
            painter.setBrush(QColor("#17202a"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(label_rect, 6, 6)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, f"峰值 {peak_hour:02d}:00")

        self._draw_hover_card(painter, chart, bar_width, bar_gap)

        axis_font = painter.font()
        axis_font.setBold(False)
        axis_font.setPointSize(8)
        painter.setFont(axis_font)
        painter.setPen(QColor("#738196"))
        label_hours = (0, 3, 6, 9, 12, 15, 18, 21, 23) if rect.width() >= 560 else (0, 6, 12, 18, 23)
        for hour in label_hours:
            x = chart.left() + hour * hour_slot + hour_slot / 2
            painter.drawText(QRectF(x - 8, chart.bottom() + 8, 34, 18), Qt.AlignmentFlag.AlignCenter, f"{hour:02d}")

        hint_y = chart.bottom() + 29
        if rect.width() >= 500:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(QRectF(chart.left(), hint_y, chart.width(), 18), Qt.AlignmentFlag.AlignLeft, "每小时三柱分别为前台、视频、音乐；绿色圆点表示学习标记")
            legend_y = hint_y + 23
        else:
            legend_y = hint_y
        self._draw_wrapped_legend(painter, chart, legend_y, summary)
        painter.end()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        pos = event.position() if hasattr(event, "position") else event.pos()
        for rect, hour, focus, video, music, learn in self._bar_rects:
            if rect.contains(pos):
                tip = (
                    f"{hour:02d}:00 - {hour:02d}:59\n"
                    f"单项最高 {format_duration(max(focus, video, music, learn))}\n"
                    f"前台 {format_duration(focus)}\n"
                    f"视频 {format_duration(video)}\n"
                    f"音乐 {format_duration(music)}\n"
                    f"学习标记 {format_duration(learn)}"
                )
                self.setToolTip(tip)
                if self._hover_hour != hour:
                    self._hover_hour = hour
                    self.update()
                global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
                QToolTip.showText(global_pos, tip, self)
                return
        if self._hover_hour is not None:
            self._hover_hour = None
            self.update()
        QToolTip.hideText()
        self._update_tooltip()

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hover_hour = None
        QToolTip.hideText()
        self.update()
        self._update_tooltip()
        super().leaveEvent(event)


class HeatmapWidget(QWidget):
    COLORS = [
        QColor("#edf2f7"), QColor("#cfe4ff"), QColor("#8fc0f4"),
        QColor(app_color("focus")), QColor("#0f5fa8"),
    ]

    def __init__(self, title: str = "学习热力图", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.data: list[tuple[str, float]] = []
        self.metric_label = "学习"
        self._cell_rects: list[tuple[QRectF, str, float]] = []
        self.setMinimumHeight(185)
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
            draw_empty_state(painter, QRectF(rect), "暂无足够数据（需使用 1 天以上）")
            painter.end()
            return
        max_val = max(v for _, v in self.data) or 1.0
        peak_date, peak_value = max(self.data, key=lambda item: item[1])
        peak_label = peak_date
        try:
            peak_label = date.fromisoformat(peak_date).strftime("%m-%d")
        except ValueError:
            pass
        if rect.width() >= 360:
            peak_font = painter.font()
            peak_font.setBold(False)
            peak_font.setPointSize(8)
            painter.setFont(peak_font)
            painter.setPen(QColor("#64748b"))
            painter.drawText(
                QRectF(12, 7, rect.width() - 24, 20),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"峰值 {peak_label} {format_duration(peak_value)}",
            )
        cell_gap = px(self, 2, 2)
        chart_left = 32
        chart_top = 36
        total_cols = (len(self.data) + 6) // 7
        legend_reserved = px(self, 32, 32)
        available_w = max(px(self, 72, 72), rect.width() - chart_left - px(self, 18, 18))
        available_h = max(px(self, 64, 64), rect.height() - chart_top - legend_reserved)
        cell_by_w = available_w / max(total_cols, 1) - cell_gap
        cell_by_h = available_h / 7 - cell_gap
        cell = min(px(self, 15, 15), max(px(self, 8, 8), min(cell_by_w, cell_by_h)))
        month_font = painter.font()
        month_font.setPointSize(6)
        month_font.setBold(False)
        painter.setFont(month_font)
        painter.setPen(QColor("#738196"))
        seen_months: set[str] = set()
        for idx, (date_str, _value) in enumerate(self.data):
            try:
                day = date.fromisoformat(date_str)
            except ValueError:
                continue
            month_key = day.strftime("%Y-%m")
            if day.day <= 7 and month_key not in seen_months:
                col = idx // 7
                x = chart_left + col * (cell + cell_gap)
                painter.drawText(QRectF(x - 2, 22, 44, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{day.month}月")
                seen_months.add(month_key)
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
            radius = min(px(self, 2, 2), cell / 4)
            painter.drawRoundedRect(r, radius, radius)
            if date_str == peak_date and value > 0:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QColor("#17202a"))
                painter.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        painter.setPen(QColor("#738196"))
        small = painter.font()
        small.setPointSize(6)
        painter.setFont(small)
        days = ("一", "", "三", "", "五", "", "日")
        for i, label in enumerate(days):
            y = chart_top + i * (cell + cell_gap) + cell / 2 - 4
            painter.drawText(QRectF(4, int(y), 24, 12),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
        legend_y = min(rect.height() - px(self, 20, 20), chart_top + 7 * (cell + cell_gap) + px(self, 10, 10))
        legend_x = chart_left
        legend_font = painter.font()
        legend_font.setPointSize(7)
        painter.setFont(legend_font)
        painter.setPen(QColor("#738196"))
        painter.drawText(QRectF(legend_x, legend_y, 20, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "少")
        swatch = px(self, 9, 9)
        x = legend_x + 18
        for color in self.COLORS:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, legend_y + 2, swatch, swatch), 2, 2)
            x += swatch + px(self, 2, 2)
        painter.setPen(QColor("#738196"))
        max_label = format_duration(max_val)
        remaining_w = max(0, rect.width() - x - px(self, 8, 8))
        if remaining_w >= 26:
            painter.drawText(
                QRectF(x + px(self, 2, 2), legend_y, remaining_w, 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"多 {max_label}",
            )
        painter.end()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        from .timefmt import format_duration
        for r, date_str, value in self._cell_rects:
            if r.contains(event.position()):
                tip = f"{date_str} · {self.metric_label} {format_duration(value)}"
                self.setToolTip(tip)
                return
        self.setToolTip("")


class GroupedBarChartWidget(QWidget):
    COLORS = {"this": QColor(app_color("focus")), "last": QColor("#c4cdd6")}

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
            draw_empty_state(painter, QRectF(rect), "暂无数据")
            painter.end()
            return
        has_any = any(v > 0 for _, v in self.this_week) or any(v > 0 for _, v in self.last_week)
        if not has_any:
            draw_empty_state(painter, QRectF(rect), "暂无数据（本周尚未产生记录）")
            painter.end()
            return
        all_vals = [v for _, v in self.this_week] + [v for _, v in self.last_week]
        max_val = max(all_vals or [1.0])
        chart = QRectF(58, 40, rect.width() - 78, rect.height() - 82)
        bar_w = max(px(self, 6, 6), (chart.width() - 100) / 14)
        gap = px(self, 3, 3)
        group_w = bar_w * 2 + gap
        axis_font = painter.font()
        axis_font.setBold(False)
        axis_font.setPointSize(7)
        painter.setFont(axis_font)
        for ratio, label in ((0.5, format_axis_duration(max_val * 0.5)), (1.0, format_axis_duration(max_val))):
            y = chart.bottom() - chart.height() * ratio
            painter.setPen(QColor("#edf2f7"))
            painter.drawLine(int(chart.left()), int(y), int(chart.right()), int(y))
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(QRectF(6, y - 8, chart.left() - 12, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
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
                h = max(px(self, 2, 2), chart.height() * (val / max_val)) if max_val > 0 else px(self, 2, 2)
                offset = 0 if key == "last" else bar_w + gap
                r = QRectF(gx + offset, chart.bottom() - h, bar_w, h)
                if key == "last":
                    r1 = r
                else:
                    r2 = r
                painter.setBrush(self.COLORS[key])
                painter.drawRoundedRect(r, 2, 2)
                if val > 0 and rect.width() >= 420:
                    painter.setPen(QColor("#64748b"))
                    label_rect = QRectF(r.left() - 12, r.top() - 16, r.width() + 24, 14)
                    painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, format_duration(val))
                    painter.setPen(Qt.PenStyle.NoPen)
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


LineChartWidget = GroupedBarChartWidget


class DonutChartWidget(QWidget):
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

        totals = [(name, attention, background, attention + background) for name, attention, background in self.data if attention + background > 0]
        total = sum(value for *_rest, value in totals)
        if total <= 0:
            draw_empty_state(painter, QRectF(rect), "暂无分类数据")
            painter.end()
            return

        if len(totals) > 5 or rect.width() < 420:
            chart_left = 16
            chart_top = 46
            value_width = 116
            label_width = min(96, max(64, int(rect.width() * 0.22)))
            bar_left = chart_left + label_width + 10
            bar_right = rect.width() - value_width - 14
            bar_width = max(40, bar_right - bar_left)
            row_gap = px(self, 6, 6)
            row_height = max(px(self, 22, 22), (rect.height() - chart_top - 16 - row_gap * max(0, len(totals) - 1)) / len(totals))
            max_value = max(value for *_rest, value in totals) or 1.0
            metrics = painter.fontMetrics()
            text_color = QColor("#273449")
            muted_color = QColor("#738196")
            track_color = QColor("#e8eef5")

            for index, (name, attention, background, value) in enumerate(totals[:7]):
                y = chart_top + index * (row_height + row_gap)
                color = QColor(category_color(name, index))
                label = metrics.elidedText(name, Qt.TextElideMode.ElideRight, label_width - 8)
                painter.setPen(text_color)
                painter.drawText(QRectF(chart_left, y, label_width, row_height), Qt.AlignmentFlag.AlignVCenter, label)

                track_rect = QRectF(bar_left, y + px(self, 5, 5), bar_width, max(px(self, 10, 10), row_height - px(self, 10, 10)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(track_color)
                painter.drawRoundedRect(track_rect, 5, 5)
                fill = QRectF(track_rect.left(), track_rect.top(), max(px(self, 4, 4), track_rect.width() * (value / max_value)), track_rect.height())
                painter.setBrush(color)
                painter.drawRoundedRect(fill, 5, 5)

                percent = value / total * 100.0
                painter.setPen(muted_color)
                painter.drawText(
                    QRectF(bar_right + 8, y, value_width - 8, row_height),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    f"{format_duration(value)} · {percent:.0f}%",
                )
                self._legend_rects.append((QRectF(chart_left, y, rect.width() - chart_left - 12, row_height), name, value, attention, background))
            painter.end()
            return

        side = min(150, rect.height() - 64, max(92, int(rect.width() * 0.38)))
        pie_rect = QRectF(16, 52, side, side)
        start_angle = 90 * 16
        painter.setPen(Qt.PenStyle.NoPen)
        for index, (name, _attention, _background, value) in enumerate(totals):
            span = int(-(value / total) * 360 * 16)
            painter.setBrush(QColor(category_color(name, index)))
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
        painter.drawText(inner.adjusted(0, 18, 0, 0), Qt.AlignmentFlag.AlignCenter, "注视+播放")

        legend_left = int(pie_rect.right() + 18)
        legend_width = rect.width() - legend_left - 12
        legend_font = painter.font()
        legend_font.setBold(False)
        legend_font.setPointSize(9)
        painter.setFont(legend_font)
        metrics = painter.fontMetrics()
        y = 50
        for index, (name, attention, background, value) in enumerate(totals[:7]):
            color = QColor(category_color(name, index))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(legend_left, y + 5, 10, 10), 3, 3)
            percent = f"{value / total * 100:.0f}%"
            text = metrics.elidedText(f"{name} · {format_duration(value)} · {percent}", Qt.TextElideMode.ElideRight, legend_width - 18)
            painter.setPen(QColor("#273449"))
            row_rect = QRectF(legend_left + 18, y, legend_width - 18, 20)
            painter.drawText(row_rect, Qt.AlignmentFlag.AlignVCenter, text)
            self._legend_rects.append((QRectF(legend_left, y, legend_width, 20), name, value, attention, background))
            y += 24
        painter.end()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        total = sum(attention + background for _name, attention, background in self.data)
        for rect, name, value, attention, background in self._legend_rects:
            if rect.contains(event.position()):
                pct = value / total * 100.0 if total > 0 else 0.0
                self.setToolTip(
                    f"{name} · {format_duration(value)} · {pct:.1f}%\n"
                    f"注视 {format_duration(attention)} · 播放/后台 {format_duration(background)}"
                )
                return
        self._update_tooltip()
