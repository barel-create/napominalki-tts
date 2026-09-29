"""
GUI entry point (Sep 2026 rewrite) -- replaces the console window with a
pywebview window hosting web/index.html. The TTS poll loop keeps running
exactly as before (see main.py's poll_once/speak_item, reused unchanged
here), just on a background thread instead of blocking the main one, since
webview.start() owns the main thread now.
"""

import os
import sys
import threading
import time
import traceback

import webview

from tts_client import config, gui_api

WINDOW_TITLE = "Napominalki TTS"


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
    )
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
