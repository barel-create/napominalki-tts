"""
Speech synthesis (edge-tts) and volume boost (ffmpeg).

Mirrors the exact tool chain already proven live on the family's Windows PC
(config.txt -> TTS -- LOCKED ARCHITECTURE DECISIONS): edge-tts for the
Russian neural voice, ffmpeg for a volume boost pass, with a fallback to
the raw (un-boosted) file if ffmpeg fails for any reason.
"""

import asyncio
import os
import subprocess
import sys
import tempfile

import edge_tts


def _ffmpeg_path():
    """
    Packaged builds bundle ffmpeg.exe next to this script (PyInstaller
    --add-binary, see build.spec) so the app needs nothing pre-installed on
    the target PC. Running from source falls back to 'ffmpeg' on PATH.
    """
    if getattr(sys, "frozen", False):
        bundled = os.path.join(sys._MEIPASS, "ffmpeg.exe")
        if os.path.exists(bundled):
            return bundled
    return "ffmpeg"


async def _synthesize_async(text, voice, out_path):
    communicate = edge_tts.Communicate(text, voice)
    # Hard cap: without it one stalled connection would hang the caller forever.
    await asyncio.wait_for(communicate.save(out_path), timeout=45)


def synthesize(text, voice):
    """Returns the path to a freshly-generated raw mp3 for `text`."""
    fd, raw_path = tempfile.mkstemp(prefix="tts_raw_", suffix=".mp3")
    os.close(fd)
    asyncio.run(_synthesize_async(text, voice, raw_path))
    return raw_path


def boost_volume(raw_path, boost):
    """
    Re-encodes raw_path with ffmpeg's volume filter. Returns the boosted
    file's path, or raw_path unchanged if ffmpeg isn't available / fails
    (same graceful fallback as the original tts_client.py).
    """
    if not boost or boost == 1.0:
        return raw_path

    out_path = raw_path.replace("_raw_", "_out_")
    if out_path == raw_path:
        base, ext = os.path.splitext(raw_path)
        out_path = base + "_boosted" + ext

    cmd = [
        _ffmpeg_path(), "-y", "-i", raw_path,
        "-filter:a", f"volume={boost}",
        out_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0 and os.path.exists(out_path):
            return out_path
        print(f"[synth] ffmpeg volume boost failed (rc={result.returncode}); using raw audio")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[synth] ffmpeg volume boost failed ({e}); using raw audio")
    return raw_path


def cleanup(*paths):
    for p in set(paths):
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
