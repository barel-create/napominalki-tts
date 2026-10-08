"""
Napominalki TTS client -- entry point.

Replaces the old C:\\tts folder (tts_client.py + tts_runner.bat + chime.mp3,
Syncthing-synced from the Mint PC) with a single self-contained program:
download, run once to configure, done. See README.md for the full story.

Behavior is intentionally a straight port of the proven design in
context.txt / config.txt -- TTS (poll every POLL_SEC, skip items older than
STALE_SEC, edge-tts -> ffmpeg volume boost -> chime -> voice) -- not a
redesign. The only real changes are *how the app is distributed and
configured*, not what it does once running.
"""

import os
import sys
import time
import traceback

from tts_client import autostart, config, player, queue_client, status, synth
from tts_client.logsetup import log


def speak_item(text, cfg, base_dir):
    # Everything here is logged step by step (1.1.3). Before, the first line was
    # a bare print() OUTSIDE the try -- any failure there lost the item silently.
    log(f"[speak] start: {text!r}")
    raw_path = None
    boosted_path = None
    t0 = time.time()
    try:
        raw_path = synth.synthesize(text, cfg["voice"])
        log(f"[speak] synthesized {os.path.getsize(raw_path)} bytes in {time.time() - t0:.1f}s")

        boosted_path = synth.boost_volume(raw_path, cfg.get("volume_boost", 1.0))
        log(f"[speak] volume boost: {'applied' if boosted_path != raw_path else 'skipped/failed (raw audio)'}")

        chime_path = player.find_chime_path(base_dir)
        if chime_path:
            player.play_file(chime_path, timeout=10)
        else:
            log("[speak] no chime found")

        ok = player.play_file(boosted_path)
        if ok:
            status.update(last_spoken=text, last_spoken_at=time.time())
            log(f"[speak] done in {time.time() - t0:.1f}s")
        else:
            raise RuntimeError("voice playback failed (see [player] line above)")
    except Exception as e:
        log("[speak] FAILED:\n" + traceback.format_exc())
        status.update(last_error=f"{type(e).__name__}: {e}", last_error_at=time.time())
    finally:
        synth.cleanup(raw_path, boosted_path)


def poll_once(cfg, base_dir):
    """Returns how many items the server handed back (0 is normal)."""
    items = queue_client.fetch_items(cfg["web_app_url"], cfg["tts_token"])
    if items:
        log(f"[poll] server returned {len(items)} item(s); skew vs server={queue_client.last_info.get('skew')}s")
    for item in items:
        text = (item or {}).get("text", "").strip()
        ts = (item or {}).get("ts")
        if not text:
            log(f"[poll] skipping item with empty text: {item!r}")
            continue
        if ts is not None and queue_client.is_stale(ts, cfg["stale_sec"]):
            age = int(queue_client.age_sec(ts))
            log(f"[poll] SKIPPED as stale ({age}s old > {cfg['stale_sec']}s): {text!r}")
            continue
        speak_item(text, cfg, base_dir)
    return len(items)


def main():
    print("Napominalki TTS client starting...")
    cfg = config.get_or_setup_config()
    base_dir = config.app_base_dir()

    if cfg.get("autostart"):
        autostart.install()

    print(f"Polling {cfg['web_app_url']} every {cfg['poll_sec']}s "
          f"(voice={cfg['voice']}, stale_sec={cfg['stale_sec']})")
    print("Leave this window open (or minimized). Ctrl+C to stop.")

    consecutive_errors = 0
    while True:
        try:
            poll_once(cfg, base_dir)
            consecutive_errors = 0
        except KeyboardInterrupt:
            print("Stopping.")
            return 0
        except Exception:
            consecutive_errors += 1
            print(f"[poll] error (#{consecutive_errors}):")
            traceback.print_exc()
            # Back off a bit on repeated failures (e.g. network/PC just woke
            # up) instead of hammering the endpoint, but never give up --
            # there is no external relauncher anymore, this loop IS it.
            time.sleep(min(30, cfg["poll_sec"] * consecutive_errors))

        time.sleep(cfg["poll_sec"])


if __name__ == "__main__":
    sys.exit(main())
