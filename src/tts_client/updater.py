"""
Self-update: check GitHub Releases for a newer tag, download the new .exe,
and relaunch on it.

A running .exe can't overwrite its own file on Windows (the OS keeps it
locked), so the swap happens via a tiny detached helper .bat that:
  1. waits a moment for this process to fully exit,
  2. deletes the old exe and renames the freshly-downloaded one into its place,
  3. relaunches it,
  4. deletes itself.
This means an update is NOT invisible -- the window closes and reopens a
few seconds later (confirmed acceptable; see README). There's no safer way
to replace a running Windows executable without a separate always-on
background service, which this app deliberately doesn't have.
"""

import os
import subprocess
import sys
import tempfile
import urllib.request
import json

from tts_client.version import APP_VERSION, GITHUB_OWNER, GITHUB_REPO

RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "NapominalkiTTS.exe"


def _parse_version(tag):
    """'v1.2.0' or '1.2.0' -> (1, 2, 0). Non-numeric parts sort as 0."""
    tag = tag.lstrip("vV")
    parts = []
    for p in tag.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def check_latest():
    """
    Returns {"available": bool, "version": "1.2.0", "download_url": "..."}
    or {"available": False, "error": "..."} if the check itself failed
    (network down, rate-limited, etc. -- never raises).
    """
    try:
        req = urllib.request.Request(
            RELEASES_API,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "NapominalkiTTS"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        tag = data.get("tag_name", "")
        latest = _parse_version(tag)
        current = _parse_version(APP_VERSION)

        asset_url = None
        for asset in data.get("assets", []):
            if asset.get("name") == ASSET_NAME:
                asset_url = asset.get("browser_download_url")
                break

        return {
            "available": latest > current and asset_url is not None,
            "version": tag.lstrip("vV"),
            "download_url": asset_url,
        }
    except Exception as e:
        print(f"[updater] check failed: {e}")
        return {"available": False, "error": str(e)}


def _download(url, dest_path):
    req = urllib.request.Request(url, headers={"User-Agent": "NapominalkiTTS"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as f:
        f.write(resp.read())


def apply_update(download_url):
    """
    Downloads the new exe, writes + launches the swap-and-relaunch helper,
    then this process should exit immediately after calling this (see
    gui.py's update flow). Returns False (with no relaunch attempted) if
    anything before the handoff fails, so the caller can show an error
    instead of silently vanishing.
    """
    if not getattr(sys, "frozen", False):
        print("[updater] running from source, not a packaged .exe -- refusing to self-update")
        return False

    current_exe = sys.executable
    exe_dir = os.path.dirname(current_exe)
    new_exe = os.path.join(exe_dir, "NapominalkiTTS.new.exe")

    try:
        _download(download_url, new_exe)
    except Exception as e:
        print(f"[updater] download failed: {e}")
        if os.path.exists(new_exe):
            os.remove(new_exe)
        return False

    bat_path = os.path.join(tempfile.gettempdir(), "napominalki_update.bat")
    bat_contents = f"""@echo off
:wait
tasklist /FI "PID eq {os.getpid()}" 2>NUL | find "{os.getpid()}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto wait
)
del "{current_exe}"
move /Y "{new_exe}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_contents)

    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0),
    )
    return True
