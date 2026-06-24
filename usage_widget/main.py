from __future__ import annotations

import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from . import __app_name__, __version__
from .diagnostics import log_event, log_path
from .monitor import ProcessMonitor
from .storage import Storage
from .ui import UsageWidgetWindow, apply_app_font


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    apply_app_font(app)
    app.setQuitOnLastWindowClosed(False)

    try:
        storage = Storage()
        monitor = ProcessMonitor(storage)
        window = UsageWidgetWindow(storage, monitor)
        window.show()
        monitor.start()
    except Exception as exc:
        log_event("启动失败：\n" + traceback.format_exc())
        QMessageBox.critical(
            None,
            "UsageWidget 启动失败",
            f"程序启动时遇到错误：\n{exc}\n\n诊断日志：\n{log_path()}",
        )
        return 1

    code = app.exec()
    monitor.stop()
    storage.close()
    return code
