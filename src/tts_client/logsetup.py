"""
Always-on logging (added in 1.1.3).

WHY THIS EXISTS: pywebview, the moment it is imported, replaces a missing
stdout/stderr with open(os.devnull, "w") (see webview/http.py). From then on
every print() and traceback in this app was silently thrown away -- which is
why the 1.1.2 "log.txt" never appeared (its "only if stdout is None" check ran
AFTER that import) and why failures were invisible. This module is imported
and init()-ed by run.py BEFORE anything else, so:

  * stdout/stderr always point at a UTF-8 log file (never devnull, never an
    ANSI-encoded stream that chokes on Cyrillic) when running as the packaged
    .exe;
  * the log is written next to the exe if possible, else in
    %LOCALAPPDATA%\\NapominalkiTTS\\, else in the temp folder -- the first
    one that works, and the startup banner says which;
  * uncaught exceptions (main thread and background threads) are logged.

Only the standard library is used here, on purpose: this must work even when
every other import fails.
"""

import os
import sys
import tempfile
import threading
import time

_lock = threading.Lock()
_file = None
_path = None
_inited = False

MAX_BYTES = 1_000_000


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _candidates():
    yield os.path.join(_base_dir(), "log.txt")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        yield os.path.join(local, "NapominalkiTTS", "log.txt")
    yield os.path.join(tempfile.gettempdir(), "NapominalkiTTS_log.txt")


def _open_first():
    for p in _candidates():
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            try:
                if os.path.exists(p) and os.path.getsize(p) > MAX_BYTES:
                    os.replace(p, p + ".old")
            except OSError:
                pass
            return open(p, "a", encoding="utf-8", errors="replace", buffering=1), p
        except OSError:
            continue
    return None, None


def log_path():
    return _path


def log(msg):
    """Timestamped line to the log file. Never raises."""
    try:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        with _lock:
            if _file is not None:
                _file.write(line + "\n")
            elif sys.stdout is not None:
                print(line)
    except Exception:
        pass


def _version_of(dist, module=None):
    # Frozen exes usually don't carry the packages' dist-info, so fall back to
    # the module's own __version__ (a plain import: edge_tts/requests/aiohttp
    # are already loaded or loadable by the time the banner is written).
    try:
        from importlib import metadata
        return metadata.version(dist)
    except Exception:
        pass
    try:
        import importlib
        mod = importlib.import_module(module or dist.replace("-", "_"))
        v = getattr(mod, "__version__", None) or getattr(getattr(mod, "version", None), "__version__", None)
        return str(v) if v else "?"
    except Exception:
        return "?"


def _banner():
    import locale
    import platform
    from datetime import datetime, timezone

    try:
        from tts_client.version import APP_VERSION
    except Exception:
        APP_VERSION = "?"

    try:
        ansi = locale.getpreferredencoding(False)
    except Exception:
        ansi = "?"
    log("=" * 60)
    log(f"Napominalki TTS v{APP_VERSION} starting")
    log(f"frozen={getattr(sys, 'frozen', False)} exe={sys.executable}")
    log(f"python={platform.python_version()} os={platform.platform()}")
    log(f"log file: {_path}")
    log(f"ANSI codepage={ansi} stdout.encoding={getattr(sys.stdout, 'encoding', None)}")
    log(f"edge-tts={_version_of('edge-tts', 'edge_tts')} requests={_version_of('requests')} "
        f"aiohttp={_version_of('aiohttp')} pywebview={_version_of('pywebview', 'webview')}")
    log(f"local time={datetime.now().isoformat(timespec='seconds')} "
        f"utc={datetime.now(timezone.utc).isoformat(timespec='seconds')}")


def init():
    """Idempotent. Call as early as possible (run.py does, before any import)."""
    global _file, _path, _inited
    if _inited:
        return
    _inited = True

    _file, _path = _open_first()

    frozen = getattr(sys, "frozen", False)
    if _file is not None and (frozen or sys.stdout is None or sys.stderr is None):
        sys.stdout = _file
        sys.stderr = _file

    def _excepthook(exc_type, exc, tb):
        import traceback
        log("UNCAUGHT EXCEPTION:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))

    def _thread_hook(args):
        import traceback
        log(f"UNCAUGHT EXCEPTION in thread {getattr(args.thread, 'name', '?')}:\n"
            + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))

    sys.excepthook = _excepthook
    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass

    try:
        _banner()
    except Exception:
        pass
