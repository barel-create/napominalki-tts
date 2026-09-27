"""
Windows "run at login" install/uninstall, replacing the old shell:startup
shortcut -> tts_runner.bat -> tts_client.py chain with one self-managed step.
"""

import os
import sys

STARTUP_BAT_NAME = "NapominalkiTTS.bat"


def _startup_dir():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def _target_exe():
    if getattr(sys, "frozen", False):
        return sys.executable
    # Running from source: point the shortcut at "python main.py" instead.
    return None


def install():
    startup_dir = _startup_dir()
    if not startup_dir or not os.path.isdir(startup_dir):
        print("[autostart] could not find the Windows Startup folder; skipping")
        return False

    exe = _target_exe()
    if not exe:
        print("[autostart] running from source (not a packaged .exe); skipping autostart install")
        return False

    bat_path = os.path.join(startup_dir, STARTUP_BAT_NAME)
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(f'@echo off\r\nstart "" "{exe}"\r\n')
    print(f"[autostart] installed: {bat_path}")
    return True


def uninstall():
    startup_dir = _startup_dir()
    if not startup_dir:
        return False
    bat_path = os.path.join(startup_dir, STARTUP_BAT_NAME)
    if os.path.exists(bat_path):
        os.remove(bat_path)
        print(f"[autostart] removed: {bat_path}")
        return True
    return False
