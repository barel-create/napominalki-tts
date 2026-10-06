"""
The JS <-> Python bridge. Every public method here is callable from
web/app.js as `window.pywebview.api.<method>(...)`, returning a Promise
(pywebview marshals args/return values as JSON automatically).

Kept as a thin wrapper around config.py / synth.py / player.py / updater.py
-- the real logic lives in those already-tested modules, not duplicated here.
"""

import threading

from tts_client import config, synth, player, updater
from tts_client.version import APP_VERSION

VOICE_TEST_PHRASE = "Проверка голоса"


class Api:
    """
    `window_holder` is a single-item list ([window]) rather than a plain
    attribute so gui.py can swap in a freshly-recreated window (see
    set_borderless below) and every already-bound Api method picks up the
    new one immediately, without re-wiring the JS bridge.
    """

    def __init__(self, window_holder, on_recreate_window):
        self._window_holder = window_holder
        self._on_recreate_window = on_recreate_window

    def _window(self):
        return self._window_holder[0]

    # ------------------------------------------------------------
    # Settings load / save
    # ------------------------------------------------------------

    def get_settings(self):
        cfg = config.get_config_for_gui()
        return {
            "web_app_url": cfg.get("web_app_url", ""),
            "tts_token": cfg.get("tts_token", ""),
            "voice": cfg.get("voice", config.DEFAULTS["voice"]),
            "voices": config.VOICE_OPTIONS,
            "theme": cfg.get("theme", "light"),
            "borderless": bool(cfg.get("borderless", False)),
            "autoupdate": bool(cfg.get("autoupdate", False)),
            "dashboard_url": cfg.get("dashboard_url", config.DEFAULTS["dashboard_url"]),
            "version": APP_VERSION,
        }

    def save_setting(self, key, value):
        """
        `key` is one of: url, token, voice, theme, autoupdate -- app.js's
        save buttons/toggles pass short names for url/token; map those to
        the real config keys. (borderless goes through set_borderless
        instead, since it also has to act on the live window.)
        """
        key_map = {"url": "web_app_url", "token": "tts_token"}
        real_key = key_map.get(key, key)
        config.update_setting(real_key, value)
        return True

    # ------------------------------------------------------------
    # Voice test
    # ------------------------------------------------------------

    def test_voice(self, voice):
        try:
            raw_path = synth.synthesize(VOICE_TEST_PHRASE, voice)
            boosted_path = synth.boost_volume(raw_path, config.DEFAULTS["volume_boost"])
            ok = player.play_file(boosted_path)
            synth.cleanup(raw_path, boosted_path)
            return bool(ok)
        except Exception as e:
            print(f"[gui_api] voice test failed: {e}")
            return False

    # ------------------------------------------------------------
    # Borderless toggle -- applied live. A real OS window's frame style
    # can't be flipped in place on Windows without a native win32 call
    # pywebview doesn't expose, so this destroys and recreates the window
    # with the new frameless= setting instead (confirmed acceptable: a
    # brief visible blink, not instant/seamless).
    # ------------------------------------------------------------

    def set_borderless(self, borderless):
        config.update_setting("borderless", bool(borderless))
        threading.Thread(
            target=self._on_recreate_window, args=(bool(borderless),), daemon=True
        ).start()
        return True

    # ------------------------------------------------------------
    # Update
    # ------------------------------------------------------------

    def check_for_update(self):
        return updater.check_latest()

    def apply_update(self, download_url, expected_size=None):
        ok = updater.apply_update(download_url, expected_size=expected_size)
        if ok:
            # Helper .bat is already waiting on this PID; exiting now is
            # what lets it proceed (see updater.apply_update's docstring).
            threading.Thread(target=self._window().destroy, daemon=True).start()
        return ok
