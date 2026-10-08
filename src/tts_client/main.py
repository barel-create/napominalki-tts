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
    """Returns True if the announcement was actually played."""
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
            return True
        raise RuntimeError("voice playback failed (see [player] line above)")
    except Exception as e:
        log("[speak] FAILED:\n" + traceback.format_exc())
        status.update(last_error=f"{type(e).__name__}: {e}", last_error_at=time.time())
        return False
    finally:
        synth.cleanup(raw_path, boosted_path)


# --- state that lives for the whole run (poll_once is called every few seconds) ---
MAX_SPEAK_ATTEMPTS = 3
_spoken = {}        # item id -> time it was spoken; stops a re-delivered item (lost ack) being spoken twice
_attempts = {}      # item id -> failed speak attempts so far
_pending_ack = set()  # ids handled locally but not yet confirmed to the server


def _remember_spoken(item_id):
    _spoken[item_id] = time.time()
    if len(_spoken) > 300:
        for k, _ in sorted(_spoken.items(), key=lambda kv: kv[1])[:100]:
            _spoken.pop(k, None)


def poll_once(cfg, base_dir):
    """Returns how many items the server handed back (0 is normal)."""
    url, token = cfg["web_app_url"], cfg["tts_token"]
    items, mode = queue_client.fetch(url, token)
    if items:
        log(f"[poll] server returned {len(items)} item(s) ({mode}); skew vs server={queue_client.last_info.get('skew')}s")

    for item in items:
        item = item or {}
        text = (item.get("text") or "").strip()
        ts = item.get("ts")
        item_id = item.get("id")

        if item_id and item_id in _spoken:
            log(f"[poll] item {item_id[:8]} was already spoken (earlier ack not confirmed) -> only re-acking")
            _pending_ack.add(item_id)
            continue
        if not text:
            log(f"[poll] skipping item with empty text: {item!r}")
            if item_id:
                _pending_ack.add(item_id)
            continue
        if ts is not None and queue_client.is_stale(ts, cfg["stale_sec"]):
            age = int(queue_client.age_sec(ts))
            log(f"[poll] SKIPPED as stale ({age}s old > {cfg['stale_sec']}s): {text!r}")
            if item_id:
                _pending_ack.add(item_id)
            continue

        if speak_item(text, cfg, base_dir):
            if item_id:
                _remember_spoken(item_id)
                _pending_ack.add(item_id)
        elif item_id:
            _attempts[item_id] = _attempts.get(item_id, 0) + 1
            if _attempts[item_id] >= MAX_SPEAK_ATTEMPTS:
                log(f"[poll] giving up on item {item_id[:8]} after {_attempts[item_id]} failed attempts: {text!r}")
                _pending_ack.add(item_id)
            else:
                log(f"[poll] item {item_id[:8]} not spoken (attempt {_attempts[item_id]}/{MAX_SPEAK_ATTEMPTS}); it stays queued and will be retried")

    if _pending_ack and mode == "peek":
        if queue_client.ack(url, token, sorted(_pending_ack)):
            _pending_ack.clear()
    elif mode == "legacy":
        _pending_ack.clear()   # legacy server already deleted everything it returned
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
