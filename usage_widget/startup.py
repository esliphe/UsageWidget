from __future__ import annotations

import os
import sys
from pathlib import Path


APP_SHORTCUT_NAME = "UsageWidget.cmd"


def startup_folder() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_file() -> Path:
    return startup_folder() / APP_SHORTCUT_NAME


def is_startup_enabled() -> bool:
    return startup_file().exists()


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'start "" "{sys.executable}"'

    project_root = Path(__file__).resolve().parents[1]
    run_py = project_root / "run.py"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else Path(sys.executable)
    return f'start "" "{launcher}" "{run_py}"'


def set_startup_enabled(enabled: bool) -> None:
    path = startup_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("@echo off\n" + _launch_command() + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()
