from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


def diagnostics_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / "AppData" / "Local"
    path = root / "UsageWidget"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return diagnostics_dir() / "diagnostics.log"


MAX_LOG_SIZE = 512 * 1024  # 512 KB max log size

def log_event(message: str) -> None:
    try:
        stamp = datetime.now().isoformat(timespec="seconds")
        path = log_path()
        # Rotate if log exceeds max size (keep last ~25%)
        if path.exists() and path.stat().st_size > MAX_LOG_SIZE:
            try:
                existing = path.read_text(encoding="utf-8", errors="replace")
                path.write_text(existing[-(MAX_LOG_SIZE // 4):], encoding="utf-8")
            except Exception:
                pass
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")
    except Exception:
        pass


def read_recent_log(max_chars: int = 12000) -> str:
    path = log_path()
    if not path.exists():
        return "暂无诊断日志。"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-max_chars:] if len(text) > max_chars else text
    except Exception as exc:
        return f"读取诊断日志失败：{exc}"


def clear_log() -> None:
    try:
        log_path().write_text("", encoding="utf-8")
    except Exception:
        pass
