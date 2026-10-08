"""
Audio playback via PowerShell's System.Windows.Media.MediaPlayer.

Same approach as the original tts_client.py (config.txt notes pygame was
tried and abandoned on the old PC — build failure — so this project deliberately
does NOT reintroduce a Python audio library). PowerShell + MediaPlayer ships
with every Windows 10/11 install, so this needs nothing extra on the target PC.

(Linux support was explored and built in an earlier pass of this project,
then dropped by request -- Windows only, going forward.)
"""

import os
import subprocess
import sys
import time

from tts_client.logsetup import log

_PS_SCRIPT = """
Add-Type -AssemblyName PresentationCore
$player = New-Object System.Windows.Media.MediaPlayer
$player.Open([Uri]::new("{path}"))
Start-Sleep -Milliseconds 400
$player.Play()
$duration = 0
while (-not $player.NaturalDuration.HasTimeSpan -and $duration -lt 50) {{
    Start-Sleep -Milliseconds 100
    $duration++
}}
if ($player.NaturalDuration.HasTimeSpan) {{
    Start-Sleep -Milliseconds ($player.NaturalDuration.TimeSpan.TotalMilliseconds + 300)
}} else {{
    Start-Sleep -Seconds 6
}}
$player.Close()
"""


def play_file(path, timeout=30):
    """Blocks until playback finishes (or times out). True only if PowerShell exited 0."""
    if not path or not os.path.exists(path):
        log(f"[player] file missing, nothing to play: {path}")
        return False
    script = _PS_SCRIPT.format(path=path.replace("\\", "\\\\"))
    t0 = time.time()
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        log(f"[player] TIMEOUT after {timeout}s playing {os.path.basename(path)}")
        return False
    except (OSError, subprocess.SubprocessError) as e:
        log(f"[player] could not start PowerShell for {os.path.basename(path)}: {e!r}")
        return False

    elapsed = time.time() - t0
    out = (result.stdout or b"").decode("utf-8", "replace").strip()[:300]
    err = (result.stderr or b"").decode("utf-8", "replace").strip()[:300]
    log(f"[player] {os.path.basename(path)} rc={result.returncode} took {elapsed:.1f}s"
        + (f" stdout={out!r}" if out else "") + (f" stderr={err!r}" if err else ""))
    return result.returncode == 0


def default_chime_path():
    """
    Bundled default chime (assets/chime.wav), used unless the user drops
    their own chime.mp3/.wav next to the exe (see find_chime_path).
    """
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "chime.wav")
        if os.path.exists(bundled):
            return bundled
        return None
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate = os.path.join(here, "assets", "chime.wav")
    return candidate if os.path.exists(candidate) else None


def find_chime_path(base_dir):
    """
    A user-supplied chime next to the exe always wins (same "drop a
    chime.mp3 in the folder" convenience the original C:\\tts setup had),
    otherwise fall back to the bundled default chime.
    """
    for name in ("chime.mp3", "chime.wav"):
        candidate = os.path.join(base_dir, name)
        if os.path.exists(candidate):
            return candidate
    return default_chime_path()
