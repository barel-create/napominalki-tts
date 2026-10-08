"""
Tiny shared state the poll thread writes and the Settings panel reads
(via gui_api.get_status), so the window itself shows whether the app is
polling, what it last spoke, and the last error -- no log file needed.
"""

import threading
import time

_lock = threading.Lock()
_state = {
    "polls": 0,
    "last_poll_at": None,
    "last_poll_ok": None,   # True / False / None (not polled yet)
    "last_items": 0,
    "last_spoken": None,
    "last_spoken_at": None,
    "last_error": None,
    "last_error_at": None,
    "note": None,
}


def update(**kw):
    with _lock:
        _state.update(kw)


def bump_polls():
    with _lock:
        _state["polls"] += 1


def snapshot():
    with _lock:
        return dict(_state)


def _hms(ts):
    return time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "--:--:--"


def summary_lines():
    """Short Russian status lines for the Settings panel."""
    s = snapshot()
    lines = []
    if s["note"]:
        lines.append(s["note"])
    if s["last_poll_at"]:
        mark = "OK" if s["last_poll_ok"] else "ОШИБКА"
        lines.append(f"Опрос: {_hms(s['last_poll_at'])} {mark} (получено: {s['last_items']})")
    else:
        lines.append("Опрос: ещё не было")
    if s["last_spoken_at"]:
        lines.append(f"Озвучено: {_hms(s['last_spoken_at'])}")
    if s["last_error"]:
        lines.append(f"Ошибка {_hms(s['last_error_at'])}: {s['last_error'][:90]}")
    return lines
