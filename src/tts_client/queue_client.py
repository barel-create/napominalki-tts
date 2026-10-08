"""
Talks to the Apps Script doGet endpoint (see Code.gs: handleTtsPeek /
handleTtsAck / handleTtsGet).

TWO MODES (chosen automatically):
  * peek/ack (Code.gs deployed with ttspeek/ttsack): ?action=ttspeek returns the
    queue WITHOUT deleting it; after the app has spoken an item it confirms it
    with ?action=ttsack&ids=... . A timed-out or lost reply therefore loses
    nothing -- the item is simply still queued and comes back on the next poll.
  * legacy (older Code.gs): ?action=tts returns the queue AND deletes it. Items
    are lost if the reply never arrives. Used only when the server answers
    "unknown action" to ttspeek; re-probed every few minutes so a later Code.gs
    deploy is picked up without restarting the app.

Apps Script web apps answer in TWO hops: script.google.com runs the script and
replies 302 -> script.googleusercontent.com/macros/echo?... which serves the
stored result. The 1.1.3 log showed the second hop timing out on this PC. Here
the redirect is followed by hand so that hop can be retried (the echo URL can be
fetched again), with each hop's duration logged when it is slow.
"""

import time
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import requests

from tts_client.logsetup import log

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30          # Apps Script is sometimes slow; 15 s (1.1.3) timed out repeatedly
ECHO_ATTEMPTS = 3
SLOW_HOP_SEC = 5
LEGACY_REPROBE_SEC = 300

# Filled in by every request, read by the poll loop's heartbeat log.
last_info = {}

_legacy_until = 0.0        # while time.time() < this, skip ttspeek and use the legacy drain


class QueueError(Exception):
    pass


def _get_json(url, params):
    """GET with manual redirect handling + echo-hop retry. Returns parsed JSON (dict)."""
    t0 = time.time()
    resp = requests.get(url, params=params, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=False)
    first = time.time() - t0
    echo = None

    hops = 0
    while resp.is_redirect and hops < 5:
        hops += 1
        target = urljoin(resp.url, resp.headers["Location"])
        last_exc = None
        for attempt in range(1, ECHO_ATTEMPTS + 1):
            t1 = time.time()
            try:
                resp = requests.get(target, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=False)
                echo = (echo or 0) + (time.time() - t1)
                last_exc = None
                break
            except requests.exceptions.RequestException as e:
                last_exc = e
                log(f"[queue] redirect hop failed (attempt {attempt}/{ECHO_ATTEMPTS}, "
                    f"{time.time() - t1:.1f}s): {type(e).__name__}")
                if attempt < ECHO_ATTEMPTS:
                    time.sleep(1.5 * attempt)
        if last_exc is not None:
            raise last_exc

    last_info["elapsed"] = round(time.time() - t0, 2)
    try:
        last_info["skew"] = round(time.time() - parsedate_to_datetime(resp.headers["Date"]).timestamp())
    except Exception:
        last_info["skew"] = None
    if first > SLOW_HOP_SEC or (echo or 0) > SLOW_HOP_SEC:
        log(f"[queue] slow reply: first hop {first:.1f}s" + (f", redirect hop {echo:.1f}s" if echo else ""))

    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        raise QueueError(f"reply is not JSON (HTTP {resp.status_code}): {resp.text[:150]!r}")
    if not isinstance(data, dict):
        raise QueueError(f"unexpected reply: {str(data)[:150]!r}")
    return data


def fetch(web_app_url, token):
    """
    Returns (items, mode) where mode is "peek" or "legacy". Items are dicts
    {"id": ..., "ts": ..., "text": ...} (legacy items may lack "id").
    """
    global _legacy_until

    if time.time() >= _legacy_until:
        data = _get_json(web_app_url, {"action": "ttspeek", "token": token})
        err = data.get("error")
        if err == "unknown action":
            _legacy_until = time.time() + LEGACY_REPROBE_SEC
            log("[queue] server has no ttspeek yet (old Code.gs) -> using the legacy destructive drain; re-checking in 5 min")
        elif err:
            raise QueueError(err)
        else:
            if data.get("busy"):
                log("[queue] server was busy (lock); will retry next poll")
            return data.get("items", []), "peek"

    data = _get_json(web_app_url, {"action": "tts", "token": token})
    if data.get("error"):
        raise QueueError(data["error"])
    return data.get("items", []), "legacy"


def ack(web_app_url, token, ids):
    """Confirms items to the server so it deletes them. True on success, False to retry later."""
    ids = [i for i in ids if i]
    if not ids:
        return True
    try:
        data = _get_json(web_app_url, {"action": "ttsack", "token": token, "ids": ",".join(ids)})
    except Exception as e:
        log(f"[queue] ack failed ({type(e).__name__}: {e}); will retry next poll")
        return False
    if data.get("error") or data.get("busy"):
        log(f"[queue] ack not accepted: {data}; will retry next poll")
        return False
    return True


def age_sec(item_ts):
    now = time.time()
    ts = float(item_ts)
    if ts > 10_000_000_000:  # looks like milliseconds
        ts /= 1000.0
    return now - ts


def is_stale(item_ts, stale_sec):
    """
    item_ts may be epoch seconds or epoch milliseconds depending on how
    Apps Script's Date.getTime() serialized it; both are handled so a unit
    mismatch never accidentally makes everything (or nothing) look stale.
    """
    return age_sec(item_ts) > stale_sec
