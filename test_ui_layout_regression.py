from __future__ import annotations

import shutil
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QAbstractItemView, QApplication

from usage_widget.monitor import ProcessMonitor
from usage_widget.storage import Storage
from usage_widget.ui import (
    CurrentStatusDialog,
    SettingsDialog,
    StatsDialog,
    UsageWidgetWindow,
    dialog_stylesheet,
)


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "OK" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        raise AssertionError(detail or name)


def main() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(tempfile.mkdtemp(prefix="usagewidget-ui-"))
    storage = Storage(root / "ui-layout.db")
    try:
        settings = SettingsDialog(storage)
        settings.resize(760, 600)
        app.processEvents()
        check("settings minimum height stays within requested viewport", settings.height() == 600, str(settings.size()))

        settings.settings_tabs.setCurrentIndex(3)
        settings.category_filter_input.setText("codex")
        app.processEvents()
        visible = [
            settings.category_table.item(row, 0).text()
            for row in range(settings.category_table.rowCount())
            if not settings.category_table.isRowHidden(row)
        ]
        check("category rule keyword filter", bool(visible) and all("codex" in item.casefold() for item in visible), repr(visible))
        settings.category_source_filter.setCurrentIndex(settings.category_source_filter.findData("user"))
        app.processEvents()
        user_visible = sum(
            not settings.category_table.isRowHidden(row)
            for row in range(settings.category_table.rowCount())
        )
        check("category rule source filter", user_visible == 0, str(user_visible))
        settings.settings_tabs.setCurrentIndex(4)
        metric_labels = [settings.goal_metric_combo.itemText(index) for index in range(settings.goal_metric_combo.count())]
        check("goal metrics hide internal identifiers", all("_" not in label for label in metric_labels), repr(metric_labels))
        settings.close()

        storage.save_settings(replace(storage.load_settings(), theme="dark"))
        stylesheet = dialog_stylesheet("QDialog { background: #f6f8fb; color: #17202a; }", storage.load_settings())
        check("dark dialog stylesheet replaces light palette", "#151a22" in stylesheet and "#f5f7fb" in stylesheet)

        stats = StatsDialog(storage)
        stats.resize(1020, 720)
        stats.tabs.setCurrentWidget(stats.timeline_tab)
        stats.show()
        app.processEvents()
        chart_window = stats.hourly_chart.palette().color(QPalette.ColorRole.Window).name().lower()
        check("dark chart receives dialog palette", chart_window == "#151a22", chart_window)
        check(
            "timeline fits minimum width without horizontal scrolling",
            stats.timeline_table.horizontalScrollBar().maximum() == 0,
            str(stats.timeline_table.horizontalScrollBar().maximum()),
        )
        check(
            "timeline uses compact same-day time",
            stats._timeline_start_label("2026-07-13T09:05:00", date(2026, 7, 13), date(2026, 7, 13)) == "09:05",
        )
        check(
            "timeline includes date for multi-day range",
            stats._timeline_start_label("2026-07-13T09:05:00", date(2026, 7, 12), date(2026, 7, 13)) == "07-13 09:05",
        )
        stats.close()

        monitor = ProcessMonitor(storage)
        status = CurrentStatusDialog(storage, monitor)
        check(
            "status table is read-only without selection highlight",
            status.status_table.selectionMode() == QAbstractItemView.SelectionMode.NoSelection
            and status.status_table.currentRow() == -1,
        )
        status.close()

        storage.save_settings(replace(storage.load_settings(), always_expanded=True))
        widget = UsageWidgetWindow(storage, monitor)
        check("process placeholders start hidden", all(row.isHidden() for row in widget.rows))
        widget.tray.hide()
        widget.hide()
    finally:
        storage.close()
        shutil.rmtree(root, ignore_errors=True)

    print("all UI layout regression tests passed")


if __name__ == "__main__":
    main()
