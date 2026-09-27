"""
Config loading / first-run setup wizard.

Design goal: "download this on any PC, it just works" — no Syncthing, no
separate .bat runner, no hand-edited constants in a .py file. Everything
that's per-install (the Apps Script URL, the shared TTS token) lives in a
small config.json saved next to the running executable. Everything that's
a fixed product decision (voice, poll interval, etc.) ships with a sane
default matching the values LOCKED in the original Napominalki project
(config.txt -> TTS -- HARDWARE, PATHS, AND VALUES) but stays overridable
in config.json for anyone who wants to retune it without a rebuild.
"""

import json
import os
import sys

APP_DIR_NAME = "NapominalkiTTS"

DEFAULTS = {
    "web_app_url": "",       # Apps Script /exec URL (doGet ?action=tts endpoint)
    "tts_token": "",         # shared-secret token, same as TTS_TOKEN in Code.gs
    "voice": "ru-RU-DmitryNeural",
    "poll_sec": 5,
    "stale_sec": 300,
    "volume_boost": 2.0,
    "autostart": False,
}

REQUIRED_KEYS = ("web_app_url", "tts_token")


def app_base_dir():
    """
    Directory the exe/script lives in. When frozen by PyInstaller (--onefile),
    sys.executable is the .exe itself; when running from source, it's the
    directory containing main.py. Keeping config.json here (not %APPDATA%)
    is deliberate: the whole point is "the folder you downloaded IS the app",
    nothing hidden elsewhere on the machine.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # source layout: <repo>/src/tts_client/config.py -> <repo>
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def config_path():
    return os.path.join(app_base_dir(), "config.json")


def load_config():
    path = config_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[config] could not read {path}: {e}")
        return None
    merged = dict(DEFAULTS)
    merged.update(data)
    missing = [k for k in REQUIRED_KEYS if not merged.get(k)]
    if missing:
        print(f"[config] {path} is missing: {', '.join(missing)}")
        return None
    return merged


def save_config(cfg):
    path = config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"[config] saved {path}")


def run_setup_wizard():
    """
    Interactive first-run prompt. Values come from the family's Apps Script
    project (config.txt in the Napominalki project: WEB_APP_URL and
    TTS_TOKEN under "APPS SCRIPT" / "TTS -- VALUES -- LOCKED").
    """
    print("=" * 60)
    print(" Napominalki TTS client -- first-run setup")
    print("=" * 60)
    print()
    print("Paste the values from the Napominalki project's config.txt.")
    print()

    cfg = dict(DEFAULTS)

    web_app_url = input("Apps Script Web App URL (WEB_APP_URL): ").strip()
    tts_token = input("TTS token (TTS_TOKEN): ").strip()
    cfg["web_app_url"] = web_app_url
    cfg["tts_token"] = tts_token

    voice = input(f"Voice [{cfg['voice']}]: ").strip()
    if voice:
        cfg["voice"] = voice

    autostart_answer = input("Start automatically when Windows logs in? [Y/n]: ").strip().lower()
    cfg["autostart"] = autostart_answer in ("", "y", "yes")

    save_config(cfg)
    return cfg


def get_or_setup_config():
    cfg = load_config()
    if cfg is not None:
        return cfg
    return run_setup_wizard()
