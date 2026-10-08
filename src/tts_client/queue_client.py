"""
Polls the Apps Script doGet ?action=tts&token=... endpoint (see config.txt
"APPS SCRIPT" / Code.gs handleTtsGet). This is a *destructive* drain — every
poll that returns items has already deleted them server-side — matching the
single-consumer design documented in current_state.txt (multi-zone/non-
destructive draining is a separate, not-yet-built project, out of scope here).
"""

import time
from email.utils import parsedate_to_datetime

import requests

# Filled in by every fetch_items() call, read by the poll loop's heartbeat log:
# {"elapsed": seconds the request took, "skew": PC clock minus server clock, seconds}
last_info = {}


class QueueError(Exception):
    pass


def fetch_items(web_app_url, token, timeout=15):
    """
    GET ?action=tts&token=... -> {"items": [{"ts": <epoch>, "text": "..."}]}
    requests follows the Apps Script 302 redirect natively (same reason the
    original design never needed the Cloudflare Worker on this path).
    """
    t0 = time.time()
    resp = requests.get(
        web_app_url,
        params={"action": "tts", "token": token},
        timeout=timeout,
    )
    last_info["elapsed"] = round(time.time() - t0, 2)
    try:
        last_info["skew"] = round(time.time() - parsedate_to_datetime(resp.headers["Date"]).timestamp())
    except Exception:
        last_info["skew"] = None
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        raise QueueError(f"reply is not JSON (HTTP {resp.status_code}): {resp.text[:150]!r}")
    if isinstance(data, dict) and data.get("error"):
        raise QueueError(data["error"])
    return data.get("items", []) if isinstance(data, dict) else []


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
