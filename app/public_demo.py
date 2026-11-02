# app/public_demo.py
# The public demo (PUBLIC_DEMO=1 in the host's settings; docs/DEPLOY.md says
# how to put it up): anyone on the web can try Buddy with Rose's made-up
# week. On top of the ordinary app it adds:
# - the week is loaded when the database is empty, and put back once a day
#   from DEMO_RESET_HOUR on (3 in the morning, the server's clock);
# - each visitor gets a share of Meta's calls an hour, and the day has a cap
#   for everyone (AI_CALLS_PER_VISITOR_HOUR, AI_CALLS_PER_DAY), so the key's
#   credits can't be drained. Kind words when a share is used up. The safety
#   net never counts and is never stopped: it needs no AI;
# - no invites or sign-ups (only the made-up family account, "Try the demo
#   as Maria"), and her data can't be exported or deleted.
# At home (no PUBLIC_DEMO) none of this runs.

import threading
import time
from datetime import datetime

from app import db, demo
from app.config import get_settings

VISITOR_LIMIT = "You've used this demo's share of Buddy's thinking for now. Please try again in a little while."
DAILY_LIMIT = ("Buddy's thinking is used up for today in this demo. Please come back tomorrow, or run Buddy on your "
               "own computer: the README says how.")
NO_SIGN_UP = "This public demo has no sign-ups. Tap \"Try the demo as Maria\" to see the family page."
NO_DATA_CHANGES = "This is a public demo, so her data can't be taken or wiped here. It starts over every night."

# The requests that call Meta: (method, the path or the start of it). The
# safety net runs first in /api/chat, so that one is checked inside its
# route, after the net (app/routes/companion.py), and /api/listen at its start.
AI_PATHS = (
    ("POST", "/api/transcribe"), ("POST", "/api/scam-check"), ("POST", "/api/read"), ("POST", "/api/find"),
    ("POST", "/api/meds/label"), ("POST", "/api/memories"), ("POST", "/api/messages/voice"),
    ("POST", "/api/family/voice"), ("GET", "/api/postcard/today"), ("GET", "/api/briefing/news"),
    ("GET", "/api/briefing/sports"), ("GET", "/api/doctor-notes"),
)
# What a public demo never does: (method, path, the kind words).
REFUSED = (
    ("POST", "/api/family/invite", NO_SIGN_UP),
    ("POST", "/api/family/account", NO_SIGN_UP),
    ("GET", "/api/data/export", NO_DATA_CHANGES),
    ("POST", "/api/data/delete", NO_DATA_CHANGES),
)
HOUR = 3600
_visitors: dict[str, list[float]] = {}  # each visitor's recent AI calls (when, in seconds)
_lock = threading.Lock()


def on() -> bool:
    return get_settings().public_demo


def visitor_of(headers, client_host: str) -> str:
    """Who is asking: the first address the host's proxy reports (the
    visitor's own), or the connection's. Never kept beyond the hour's count."""
    forwarded = (headers.get("x-forwarded-for") or "") if headers is not None else ""
    first = forwarded.split(",")[0].strip()
    return first or client_host or "unknown"


def refused(method: str, path: str) -> str | None:
    """The kind words when this request is never done in a public demo, else None."""
    if not on():
        return None
    for refused_method, refused_path, words in REFUSED:
        if method == refused_method and path == refused_path:
            return words
    return None


def is_ai_call(method: str, path: str) -> bool:
    return any(method == ai_method and (path == ai_path or path.startswith(ai_path + "/"))
               for ai_method, ai_path in AI_PATHS)


def ai_call_allowed(headers, client_host: str, now: float | None = None) -> str | None:
    """None when this visitor may make a Meta call now (and it is counted);
    otherwise the kind words to show instead. Always None at home."""
    if not on():
        return None
    settings = get_settings()
    moment = time.time() if now is None else now
    visitor = visitor_of(headers, client_host)
    with _lock:
        recent = [when for when in _visitors.get(visitor, []) if moment - when < HOUR]
        _visitors[visitor] = recent
        if len(recent) >= settings.ai_calls_per_visitor_hour:
            return VISITOR_LIMIT
        day = datetime.fromtimestamp(moment).date().isoformat()
        connection = db.get_connection()
        try:
            row = connection.execute("SELECT count FROM ai_calls WHERE day = ?", (day,)).fetchone()
            if (row["count"] if row else 0) >= settings.ai_calls_per_day:
                return DAILY_LIMIT
            connection.execute(
                "INSERT INTO ai_calls (day, count) VALUES (?, 1) ON CONFLICT (day) DO UPDATE SET count = count + 1", (day,)
            )
            connection.commit()
        finally:
            connection.close()
        recent.append(moment)
    return None


def reset_if_due(now: datetime) -> bool:
    """The demo week: loaded when the database is empty, and put back once a
    day from DEMO_RESET_HOUR on. Returns True when it was. Nothing at home."""
    if not on():
        return False
    settings = get_settings()
    today = now.date().isoformat()
    connection = db.get_connection()
    try:
        empty = not demo.has_data(connection)
        last = connection.execute("SELECT day FROM demo_resets ORDER BY day DESC LIMIT 1").fetchone()
        last_day = last["day"] if last else ""
    finally:
        connection.close()
    if not empty and (now.hour < settings.demo_reset_hour or last_day == today):
        return False
    demo.reset(now)
    connection = db.get_connection()
    try:
        connection.execute("INSERT OR REPLACE INTO demo_resets (day) VALUES (?)", (today,))
        connection.commit()
    finally:
        connection.close()
    return True


def keep_the_week_fresh() -> None:
    """The background thread of a public demo: the week at start, and the
    nightly reset, checked every minute."""
    while True:
        try:
            reset_if_due(datetime.now())
        except Exception as problem:  # never stop the app over this
            print(f"The demo week couldn't be reset: {type(problem).__name__}")
        time.sleep(60)
