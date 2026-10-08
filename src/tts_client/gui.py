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

from tts_client import logsetup

logsetup.init()  # no-op when run.py already did; keeps `python -m tts_client.gui` safe too

import webview  # noqa: E402  (must come AFTER logsetup.init(): pywebview swaps a missing stdout for devnull on import)

from tts_client import autostart, config, gui_api, queue_client, status  # noqa: E402
from tts_client.logsetup import log  # noqa: E402

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
    base_dir = config.app_base_dir()
    consecutive_errors = 0
    polls = 0
    last_heartbeat = time.time()
    poll_sec = 5

    try:
        from tts_client.main import poll_once  # local import: avoids main.py's module-level side effects running twice
    except Exception:
        log("[poll] FATAL: could not import poll_once:\n" + traceback.format_exc())
        status.update(last_error="не удалось запустить опрос (см. log.txt)", last_error_at=time.time())
        return

    log("[poll] loop started")
    while True:
        # The WHOLE iteration is guarded (config load included) so nothing can
        # silently kill this thread.
        try:
            cfg = config._read_raw() or {}  # raw read: load_config() would print a 'missing' line every 2 s while unconfigured
            poll_sec = cfg.get("poll_sec", 5)
            if not config.is_configured(cfg):
                status.update(note="Не заданы URL / токен (Настройки)")
                time.sleep(2)
                continue
            status.update(note=None)

            n = poll_once(cfg, base_dir)
            polls += 1
            if consecutive_errors:
                log(f"[poll] recovered after {consecutive_errors} error(s)")
            consecutive_errors = 0
            status.update(polls=polls, last_poll_at=time.time(), last_poll_ok=True, last_items=n)

            if time.time() - last_heartbeat >= 600:
                last_heartbeat = time.time()
                log(f"[poll] alive: {polls} polls so far; last request took "
                    f"{queue_client.last_info.get('elapsed')}s, clock skew vs server {queue_client.last_info.get('skew')}s")
        except Exception as e:
            consecutive_errors += 1
            status.update(last_poll_at=time.time(), last_poll_ok=False,
                          last_error=f"{type(e).__name__}: {e}", last_error_at=time.time())
            # Log the first few in full, then only every 20th, so a long outage can't fill the disk.
            if consecutive_errors <= 3 or consecutive_errors % 20 == 0:
                log(f"[poll] error #{consecutive_errors}:\n{traceback.format_exc()}")
            time.sleep(min(30, poll_sec * consecutive_errors))
        time.sleep(poll_sec)


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
                log(f"[gui] could not maximize window: {e}")
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
        log(f"[gui] window recreation failed: {e}")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main():
    logsetup.init()

    # Always on, no setting/toggle (by request): every launch (re)registers
    # this exe to start at Windows login. Deliberately does NOT consult
    # config.json's legacy "autostart" key -- existing installs have it saved
    # as False from the console era. A user who wants it off uses Task
    # Manager -> Startup apps; Windows keeps that choice separately.
    try:
        autostart.install()
    except Exception:
        log("[autostart] unexpected error:\n" + traceback.format_exc())

    cfg = config.get_config_for_gui()

    window_holder = [None]
    api = gui_api.Api(window_holder, on_recreate_window=lambda frameless: _recreate_window(window_holder, api, frameless))
    _create_window(bool(cfg.get("borderless", False)), window_holder, api)

    poll_thread = threading.Thread(target=_poll_loop, name="poll-loop", daemon=True)
    poll_thread.start()

    log("[gui] window created; entering webview.start()")
    webview.start()
    log("[gui] webview.start() returned -- window closed, app exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
