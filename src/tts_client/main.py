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

import sys
import time
import traceback

from tts_client import autostart, config, player, queue_client, synth


def speak_item(text, cfg, base_dir):
    print(f"[speak] {text}")
    raw_path = None
    boosted_path = None
    try:
        raw_path = synth.synthesize(text, cfg["voice"])
        boosted_path = synth.boost_volume(raw_path, cfg.get("volume_boost", 1.0))

        chime_path = player.find_chime_path(base_dir)
        if chime_path:
            player.play_file(chime_path, timeout=10)

        player.play_file(boosted_path)
    except Exception:
        print("[speak] failed:")
        traceback.print_exc()
    finally:
        synth.cleanup(raw_path, boosted_path)


def poll_once(cfg, base_dir):
    items = queue_client.fetch_items(cfg["web_app_url"], cfg["tts_token"])
    for item in items:
        text = (item or {}).get("text", "").strip()
        ts = (item or {}).get("ts")
        if not text:
            continue
        if ts is not None and queue_client.is_stale(ts, cfg["stale_sec"]):
            print(f"[poll] skipping stale item (older than {cfg['stale_sec']}s): {text!r}")
            continue
        speak_item(text, cfg, base_dir)


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
