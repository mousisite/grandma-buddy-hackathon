# app/briefing.py
# "What's happening today": today's weather, one gentle local story, or the
# local teams' sports, looked up on the web for her town with Meta's own web
# search (meta_client.search). For Buddy's look_up_today tool and the
# weather row on Home.
#
# Only three things can be looked up, and our code writes each question, so
# nothing about health, medicine, or food is ever searched. What comes back
# is checked by plain code before she hears it:
# - it must really come from today's web (a search ran, and sources are cited);
# - links are taken out, and at most 2 sentences are kept;
# - a sentence about health, medicine, or food, or one that gives advice,
#   is left out (docs/SAFETY.md section 8c).
# An answer is kept for 3 hours, and at most 30 searches are made a day, so
# it stays cheap ($0.0025 a search).

import json
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from app import guard, meta_client, prompts, reminders

FRESH_FOR = timedelta(hours=3)
MAX_SEARCHES_A_DAY = 30
MAX_SENTENCES = 2
MAX_SITES = 3  # the sites named under Buddy's words: the cited ones, or the top results

# What can be looked up, and the question our code asks for it.
QUESTIONS = {
    "weather": "What is the weather in {town} today, {day}: the conditions, and the high and low?",
    "news": "What is one cheerful thing happening in {town} today or this week, {day}?",
    "sports": "What was the latest result, or when is the next game, for the major sports teams of {town}, as of {day}?",
}

# Links in the answer: "([weather.gov](https://…))", "[weather.gov](https://…)", or a bare address.
CITED_LINK = re.compile(r"\s*\(\[[^\]]*\]\([^)]*\)\)")
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
ADDRESS = re.compile(r"\s*\(?\bhttps?://\S+")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Health, medicine, and food words: a sentence with one is left out. (Not
# the guard's own list, which has "cold" and "condition": weather words.)
HEALTH = re.compile(
    r"\b(health\w*|ill|illness\w*|sick\w*|diseases?|infections?|virus\w*|flu|covid\w*|vaccin\w*|booster|cancer"
    r"|allerg\w*|arthritis|diabetes|blood pressure|heart attacks?|strokes?|dehydrat\w*|anxiety|depression"
    r"|hospitals?|clinics?|doctors?|nurses?|medic\w*|prescriptions?|pharmac\w*|drugs?|diet\w*|calories"
    r"|nutrition\w*|supplements?|vitamins?)\b"
    rf"|{guard.REMEDIES.pattern}",
    re.IGNORECASE,
)


def site(url: str) -> str:
    """ "https://www.weather.gov/pqr" -> "weather.gov" """
    host = urlsplit(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def clean(text: str) -> str:
    """The answer without links, without sentences about health or with
    advice, and at most 2 sentences long."""
    text = ADDRESS.sub("", LINK.sub(r"\1", CITED_LINK.sub("", text))).strip()
    kept = []
    for sentence in SENTENCE_END.split(text):
        sentence = sentence.strip()
        if sentence and not HEALTH.search(sentence) and not guard.check_reply(sentence):
            kept.append(sentence)
    return " ".join(kept[:MAX_SENTENCES])


def searches_today(connection, now: datetime) -> int:
    row = connection.execute("SELECT count FROM web_searches WHERE day = ?", (now.date().isoformat(),)).fetchone()
    return row["count"] if row else 0


def take_search(connection, now: datetime) -> bool:
    """One of today's web searches (at most 30 a day, for the briefing and
    the scam lookup together): counted and allowed, or False when today's
    are used up. The caller commits."""
    if searches_today(connection, now) >= MAX_SEARCHES_A_DAY:
        return False
    connection.execute(
        "INSERT INTO web_searches (day, count) VALUES (?, 1) ON CONFLICT (day) DO UPDATE SET count = count + 1",
        (now.date().isoformat(),),
    )
    return True


def look_up(connection, topic: str, town: str) -> dict | None:
    """Today's weather, news, or sports for her town: {"text", "sites"}, or
    None when there is nothing good to share (no town, nothing found on the
    web, or too many searches today). When a new look fails or can't be
    made, the last one from today is kept (never yesterday's). Raises
    meta_client.MetaError when the search fails and there is none."""
    town = town.strip()
    if topic not in QUESTIONS or not town:
        return None
    now = reminders.current_time()
    kept = connection.execute(
        "SELECT text, sources, made_at FROM briefings WHERE topic = ? AND city = ?", (topic, town)
    ).fetchone()
    made = datetime.fromisoformat(kept["made_at"]) if kept else None
    last = {"text": kept["text"], "sites": json.loads(kept["sources"])} if kept and made.date() == now.date() else None
    if last and now - made < FRESH_FOR:
        return last
    if not take_search(connection, now):
        return last
    connection.commit()
    day = f"{now:%A, %B} {now.day}"
    instructions = prompts.BRIEFING.format(rules=prompts.BRIEFING_RULES[topic])
    try:
        found = meta_client.search(QUESTIONS[topic].format(town=town, day=day), instructions, town)
    except meta_client.MetaError:
        if last:
            return last  # no internet just now: this morning's is still right
        raise
    text = clean(found["text"])
    sites = list(dict.fromkeys(site(source["url"]) for source in found["sources"] if site(source["url"])))[:MAX_SITES]
    if not found["searched"] or not sites or not text:
        return None
    connection.execute(
        "INSERT OR REPLACE INTO briefings (topic, city, text, sources, made_at) VALUES (?, ?, ?, ?, ?)",
        (topic, town, text, json.dumps(sites), now.isoformat(timespec="seconds")),
    )
    connection.commit()
    return {"text": text, "sites": sites}
