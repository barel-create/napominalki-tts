"""
GUI entry point (Sep 2026 rewrite) -- replaces the console window with a
pywebview window hosting web/index.html. The TTS poll loop keeps running
exactly as before (see main.py's poll_once/speak_item, reused unchanged
here), just on a background thread instead of blocking the main one, since
webview.start() owns the main thread now.
"""

import inspect
import os
import sys
import threading
import time
import traceback
from datetime import datetime

import webview

from tts_client import autostart, config, gui_api

WINDOW_TITLE = "Napominalki TTS"


# ------------------------------------------------------------------
# Safe stdout/stderr -- THE ACTUAL CAUSE of "app runs but never speaks".
#
# build.spec sets console=False (no black terminal window). On Windows,
# a PyInstaller --windowed build with no console attached has
# sys.stdout / sys.stderr set to None. Every print() call in this
# codebase (speak_item's very first line is print(f"[speak] {text}"))
# then raises AttributeError: 'NoneType' object has no attribute 'write'.
# That exception happens inside _poll_loop()'s try block, gets caught,
# and the except handler ITSELF calls print() to log the error -- which
# raises the same AttributeError again, uncaught this time, silently
# killing the whole background polling thread. The window stays open
# and looks completely normal; the app just never speaks again, from
# the very first lesson it ever tried to announce, until it's restarted.
#
# Fix: redirect stdout/stderr to a log file BEFORE anything else runs,
# so every existing print()/traceback.print_exc() call site keeps
# working unchanged, and -- as a bonus -- there's now an actual log.txt
# to look at if something goes wrong in the future instead of silence.
# ------------------------------------------------------------------

class _NullWriter:
    """Last-resort fallback if the log file itself can't be opened (e.g.
    installed to a read-only location) -- print() still must not crash."""
    def write(self, _s):
        pass

    def flush(self):
        pass


def _setup_safe_output(base_dir):
    if sys.stdout is not None and sys.stderr is not None:
        return  # real console attached (running from source) -- leave it alone

    try:
        log_path = os.path.join(base_dir, "log.txt")
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        log_file = _NullWriter()

    sys.stdout = log_file
    sys.stderr = log_file
    print(f"\n--- Napominalki TTS starting ({datetime.now().isoformat(timespec='seconds')}) ---")


def _web_dir():
    """
    web/ is bundled as PyInstaller data (see build.spec), same pattern as
    assets/chime.wav -- sys._MEIPASS when frozen, else the repo's own web/
    folder when running from source.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "web")
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, "web")


def _index_path():
    return os.path.join(_web_dir(), "index.html")


# ------------------------------------------------------------------
# Background TTS poll loop -- identical behavior to main.py's console
# loop, just reusing its functions instead of duplicating them. Sleeps
# instead of doing anything while web_app_url/tts_token aren't filled in
# yet (first run before Settings has been saved).
# ------------------------------------------------------------------

def _poll_loop():
    from tts_client.main import poll_once  # local import: avoids main.py's
                                            # module-level side effects (none
                                            # today, but keeps gui.py safe if
                                            # that ever changes) running twice.
    base_dir = config.app_base_dir()
    consecutive_errors = 0

    while True:
        cfg = config.load_config() or {}
        if not config.is_configured(cfg):
            time.sleep(2)
            continue
        try:
            poll_once(cfg, base_dir)
            consecutive_errors = 0
        except Exception:
            consecutive_errors += 1
            print(f"[poll] error (#{consecutive_errors}):")
            traceback.print_exc()
            time.sleep(min(30, cfg.get("poll_sec", 5) * consecutive_errors))
        time.sleep(cfg.get("poll_sec", 5))


# ------------------------------------------------------------------
# Window creation / borderless recreation
# ------------------------------------------------------------------

def _create_window(frameless, window_holder, api):
    # Opens MAXIMIZED (not true fullscreen): fills the screen but keeps the
    # normal title bar with minimize / maximize-restore / close buttons and
    # the window border (unless the "borderless" setting is on). width/height
    # below is the size the window restores to if the person un-maximizes it.
    # `maximized=` is passed only if this pywebview build accepts it (feature
    # check, not a version guess) so an older pywebview can never crash
    # startup over it -- it falls back to calling win.maximize() once shown.
    supports_maximized = "maximized" in inspect.signature(webview.create_window).parameters
    extra = {"maximized": True} if supports_maximized else {}

    win = webview.create_window(
        WINDOW_TITLE,
        url=_index_path(),
        js_api=api,
        width=1000,
        height=700,
        min_size=(480, 360),
        frameless=frameless,
        easy_drag=frameless,  # frameless windows need this to stay draggable
        resizable=True,
        **extra,
    )

    if not supports_maximized:
        def _maximize_when_shown():
            try:
                win.maximize()
            except Exception as e:
                print(f"[gui] could not maximize window: {e}")
        win.events.shown += _maximize_when_shown

    window_holder[0] = win
    return win


def _recreate_window(window_holder, api, frameless):
    """
    Runs on its own thread (see gui_api.Api.set_borderless) so the pywebview
    JS call that triggered this can return immediately instead of blocking
    on the destroy/create round-trip. NEEDS REAL-DEVICE VERIFICATION: this
    assumes pywebview's EdgeChromium (Windows) backend supports creating a
    new window while the event loop is already running and before the old
    one is destroyed -- documented as supported, but never exercised on
    actual Windows in this build. If it turns out not to work cleanly, the
    fallback is: keep the old window, just don't apply frameless live (tell
    the person to restart the app after toggling it).
    """
    old_win = window_holder[0]
    try:
        new_win = _create_window(frameless, window_holder, api)
        time.sleep(0.3)  # let the new window actually come up before closing the old one
        old_win.destroy()
    except Exception as e:
        print(f"[gui] window recreation failed: {e}")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main():
    _setup_safe_output(config.app_base_dir())

    # Always on, no setting/toggle (by request): every launch (re)registers
    # this exe to start at Windows login. Deliberately does NOT consult
    # config.json's legacy "autostart" key -- existing installs have it saved
    # as False from the console era. A user who wants it off uses Task
    # Manager -> Startup apps; Windows keeps that choice separately.
    try:
        autostart.install()
    except Exception:
        traceback.print_exc()

    cfg = config.get_config_for_gui()

    window_holder = [None]
    api = gui_api.Api(window_holder, on_recreate_window=lambda frameless: _recreate_window(window_holder, api, frameless))
    _create_window(bool(cfg.get("borderless", False)), window_holder, api)

    poll_thread = threading.Thread(target=_poll_loop, daemon=True)
    poll_thread.start()

    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
