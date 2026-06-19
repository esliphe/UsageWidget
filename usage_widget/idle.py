from __future__ import annotations

import ctypes
from ctypes import wintypes


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


def idle_seconds() -> float:
    try:
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        # Use GetTickCount64 to avoid overflow after 49.7 days of uptime
        tick_count = ctypes.windll.kernel32.GetTickCount64()
        return max(0.0, (int(tick_count) - int(info.dwTime)) / 1000.0)
    except Exception:
        return 0.0
