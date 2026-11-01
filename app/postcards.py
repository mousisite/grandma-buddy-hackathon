# app/postcards.py
# The daily postcard (docs/SPEC.md feature 22, docs/SAFETY.md 9c): once a
# day, one cheerful sentence she said to Buddy, kept word for word, with a
# picture painted for it in the Memory book's watercolor style, to send to
# her family's page.
#
# How it is made, and what plain code checks:
# 1. Her words today, in any talk, filtered first by plain code: a line
#    about health, medicines, hard feelings, or anything the safety net or
#    advice guard would react to never reaches the picker.
# 2. Muse Spark picks the number of the nicest line and describes a simple
#    scene to paint (structured output). It never rewrites her words.
# 3. Plain code checks the pick: a real number, the line checked again, a
#    scene with no name, number, health word, or advice. Anything else: no
#    postcard today (until she says something new).
# 4. Muse Image paints the scene (one painting a day). If painting fails,
#    nothing is kept, so it can be tried again.
# The family sees it only once she taps "Send postcard to Maria" (shared_at).

import re
import sqlite3
from datetime import date, datetime, timedelta

from app import briefing, db, guard, memories, meta_client, notes, prompts, reader, safety, tools

# Added to the Memory book's style (memories.STYLE) so the picture reads
# like a postcard: one simple scene, nothing busy.
STYLE_WORDS = "Composed like a picture postcard: one simple, cheerful scene with room to breathe, nothing busy."

MIN_WORDS = 3  # "Yes please" is not a postcard
MAX_LINE = 200  # a postcard line, not a story
MAX_LINES = 30  # the newest lines of hers today
MAX_SCENE = 300
STUCK_MINUTES = 15  # a postcard "painting" this long: the server restarted mid-way, try again

PICK_SCHEMA = {
    "type": "object",
    "properties": {"number": {"type": "integer"}, "scene": {"type": "string"}},
    "required": ["number", "scene"],
    "additionalProperties": False,
}

NOTHING_YET = "Nothing nice to paint yet today. After you talk with Buddy a little, look again."
PAINT_FAILED = "Buddy couldn’t paint it just now. Please try again in a moment."
PAINTING = "Buddy is painting today’s postcard…"


# ---------- Plain-code checks ----------

# The everyday ways she says how she is, on top of what the safety net, the
# advice guard, and the other health patterns catch. Over-careful on
# purpose: a missed postcard costs nothing, and the screen promises "never
# anything about your health".
BODY = (r"knees?|hips?|stomach|tummy|belly|chest|throat|tooth|teeth|gums?|bowels?|bladder|kidneys?|liver|lungs?"
        r"|spine|ankles?|wrists?|elbows?|toes?|fingers?|skin|heart")
# Common words that are body parts only with a complaint near them ("my back is bad", not "there and back").
BODY_IF_SORE = r"back|head|hands?|arms?|legs?|foot|feet|eyes?|ears?|neck|shoulders?|side"
SORE = (r"hurt\w*|ach\w*|sore|pain\w*|stiff|swollen|swelling|bad|bother\w*|trouble|weak|numb|tingl\w*|crack\w*"
        r"|twist\w*|sprain\w*|broke\w*|cut|burn\w*|bleed\w*|funny|strange|odd|better|worse")
SYMPTOMS = (r"headaches?|migraines?|dizz\w*|faint\w*|nause\w*|threw up|throw(ing)? up|vomit\w*|sleep\w*|slept|insomnia"
            r"|tired|exhausted|fell|falls?|fallen|falling|bruis\w*|bleed\w*|blood|pressure|cough\w*|fever|chills|flu"
            r"|shak\w*|trembl\w*|cramps?|rash|itch\w*|infection|surgery|operation|stitches|wound|breath\w*|diarrh\w*"
            r"|constipat\w*|pills?|tablets?|doses?|medicines?|medications?|prescriptions?|pharmac\w*|doctors?|dr\.?"
            r"|nurses?|clinic|hospital|appointments?|checkup|test results|x-ray|scans?|therap\w*|oxygen|inhaler|insulin"
            r"|diabet\w*|cancer|strokes?|dementia|hospice")
FEELINGS = (r"cried|cry|crying|tears|sad|lonely|alone|upset|worried|worry\w*|scared|afraid|frightened|anxious"
            r"|depress\w*|grie\w*|mourn\w*|funeral|passed away|died|death|dead|miss(ed|ing)?")
COLD = r"\b(a|my|the|bad|nasty|head) cold\b|caught (a )?cold|cold and flu"
DOWN = r"\b(feel|feels|feeling|felt|been|so|very|bit|little) down\b"
PAIN_SCALE = r"\b(a|about|maybe|around|probably) \d{1,2}\b|\bout of (ten|10)\b|\b\d{1,2} out of\b"
POSTCARD_SKIP = re.compile(
    rf"\b({BODY}|{SYMPTOMS}|{FEELINGS})\b|{COLD}|{DOWN}|{PAIN_SCALE}"
    rf"|\b({BODY_IF_SORE})\b.{{0,40}}\b({SORE})\b|\b({SORE})\b.{{0,40}}\b({BODY_IF_SORE})\b",
    re.IGNORECASE,
)


def about_health(words: str) -> bool:
    """True when these words are about health, pain, medicines, hard
    feelings, or anything the safety net or the advice guard would react
    to. A postcard never carries any of it (docs/SAFETY.md 9c)."""
    return bool(
        POSTCARD_SKIP.search(words) or tools.PRIVATE.search(words) or briefing.HEALTH.search(words)
        or safety.PAIN_TOPIC.search(words) or reader.ADVICE.search(words)
        or safety.check(words) is not None or guard.check_reply(words) is not None
    )


def postcard_lines(rows) -> list[dict]:
    """Her lines today that could be a postcard: her own words, 3 words or
    more, not too long, and nothing about health. Each with the time she
    said it, so a later line means a new try."""
    lines = []
    for row in rows:
        text = " ".join(row["content"].split())
        if MIN_WORDS <= len(tools.words_in(text)) and len(text) <= MAX_LINE and not about_health(text):
            lines.append({"text": text, "at": row["created_at"]})
    return lines[-MAX_LINES:]


def checked_pick(answer: dict, lines: list[dict]) -> tuple[dict | None, str]:
    """The picked line and scene when the AI kept to the rules, else
    (None, why). The line is hers word for word: the AI only chose its number."""
    number = answer.get("number")
    if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= len(lines):
        return None, "nothing cheerful enough today, the AI said" if number == 0 else "a number that isn't there"
    sentence = lines[number - 1]["text"]
    scene = " ".join(str(answer.get("scene", "")).split())
    if about_health(sentence):
        return None, "the picked line is about her health"  # can't happen: the lines were filtered; belt and braces
    if not scene or len(scene) > MAX_SCENE:
        return None, "the scene is missing or too long"
    if about_health(scene) or memories.invented(scene, "") or guard.check_reply(scene) is not None:
        return None, "the scene has a name, a number, a health word, or advice"
    return {"sentence": sentence, "scene": scene, "at": lines[number - 1]["at"]}, ""


# ---------- Picking and painting ----------

def picked(lines: list[dict], her_name: str) -> tuple[dict | None, str]:
    """Ask Muse Spark which line is the nicest, and for a scene to paint.
    MetaError when it can't answer."""
    numbered = "\n".join(f"{index}. {line['text']}" for index, line in enumerate(lines, start=1))
    messages = [
        {"role": "developer", "content": prompts.POSTCARD.format(her_name=her_name)},
        {"role": "user", "content": "What she said today:\n" + numbered},
    ]
    answer = meta_client.structured(messages, "postcard_pick", PICK_SCHEMA, reasoning="low", max_tokens=1500)
    return checked_pick(answer, lines)


def painted(scene: str) -> tuple[bytes, str]:
    """One picture for the scene, in the book's style. MetaError when it
    fails or what came back isn't a picture."""
    picture = meta_client.paint(memories.STYLE + "\n\n" + STYLE_WORDS + "\n\nThe scene: " + scene)
    kind = next((kind for start, kind in memories.PICTURE_KINDS.items() if picture.startswith(start)), None)
    if kind == "webp" and picture[8:12] != b"WEBP":
        kind = None
    if kind is None:
        raise meta_client.MetaError("what came back was not a picture")
    return picture, kind


def stuck_since() -> str:
    return (datetime.now() - timedelta(minutes=STUCK_MINUTES)).isoformat(timespec="seconds")


def today_row(connection, day: str):
    return connection.execute("SELECT * FROM postcards WHERE day = ?", (day,)).fetchone()


def make_today(connection, day: str) -> tuple[dict | None, str, str]:
    """Today's postcard: (the postcard for the screen or None, its status,
    why there is none). Makes it when there isn't one yet, or when there was
    nothing nice and she has said something new since. Holds the database
    only while writing, never while Meta works."""
    row = today_row(connection, day)
    if row is not None and row["status"] == "ready":
        return for_screen(row), "ready", ""
    if row is not None and row["status"] == "painting" and row["updated_at"] >= stuck_since():
        return None, "painting", PAINTING  # another request is painting it right now
    lines = postcard_lines(db.her_words_on(connection, day))
    if not lines:
        return None, "none", NOTHING_YET
    if row is not None and row["status"] == "none" and row["said_until"] >= lines[-1]["at"]:
        return None, "none", NOTHING_YET  # nothing new since the last try
    profile = db.get_profile(connection)
    her_name = profile["preferred_name"] or profile["name"] or "She"
    # Claim today: anyone else asking meanwhile sees "painting". The day is
    # UNIQUE, so two requests that both saw no row can't both claim it.
    try:
        if row is None:
            connection.execute("INSERT INTO postcards (day, created_at, updated_at, status, said_until) VALUES (?, ?, ?, 'painting', ?)",
                               (day, db.now(), db.now(), lines[-1]["at"]))
        else:
            connection.execute("UPDATE postcards SET status = 'painting', updated_at = ?, said_until = ? WHERE day = ?",
                               (db.now(), lines[-1]["at"], day))
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        return None, "painting", PAINTING  # another request claimed it just now
    try:
        pick, why = picked(lines, her_name)
        if pick is None:
            print(f"No postcard today: {why}")  # never her words
            connection.execute("UPDATE postcards SET status = 'none', updated_at = ? WHERE day = ?", (db.now(), day))
            connection.commit()
            return None, "none", NOTHING_YET
        picture, kind = painted(pick["scene"])
        claimed = connection.execute("SELECT id FROM postcards WHERE day = ?", (day,)).fetchone()
        name = f"postcard-{claimed['id']}.{kind}"
        memories.pictures_dir().mkdir(parents=True, exist_ok=True)
        (memories.pictures_dir() / name).write_bytes(picture)
        connection.execute(
            "UPDATE postcards SET status = 'ready', sentence = ?, scene = ?, picture = ?, updated_at = ? WHERE day = ?",
            (pick["sentence"], pick["scene"], name, db.now(), day),
        )
        connection.commit()
    except Exception as problem:  # Meta, the disk, anything: the day is never left stuck at "painting"
        said = problem if isinstance(problem, meta_client.MetaError) else type(problem).__name__
        print(f"Today's postcard failed: {said}")  # never her words
        connection.rollback()
        # Nothing half-made is kept: she can try again in a moment.
        connection.execute("DELETE FROM postcards WHERE day = ? AND status = 'painting'", (day,))
        connection.commit()
        return None, "failed", PAINT_FAILED
    return for_screen(today_row(connection, day)), "ready", ""


def send(connection, day: str, now: datetime):
    """ "Send postcard to Maria": the family page shows it from now on. Returns the
    postcard, or None when today has no finished postcard."""
    row = today_row(connection, day)
    if row is None or row["status"] != "ready":
        return None
    if not row["shared_at"]:
        connection.execute("UPDATE postcards SET shared_at = ?, updated_at = ? WHERE day = ?",
                           (now.isoformat(timespec="seconds"), db.now(), day))
    return for_screen(today_row(connection, day))


# ---------- For the screens ----------

def for_screen(row) -> dict:
    """One postcard as her Family screen shows it."""
    return {
        "id": row["id"],
        "day": row["day"],
        "date": f"{date.fromisoformat(row['day']):%A, %B} {date.fromisoformat(row['day']).day}",  # like family.day_words
        "sentence": memories.curly(row["sentence"]),
        "scene": row["scene"],
        "status": row["status"],
        "picture": f"/api/postcard/{row['id']}/picture?v={row['picture']}" if row["status"] == "ready" else "",
        "shared": bool(row["shared_at"]),
        "shared_time": notes.time_words(datetime.fromisoformat(row["shared_at"])) if row["shared_at"] else "",
    }


def shared_on(connection, day: str) -> dict | None:
    """The postcard she sent that day, for the family page: her sentence,
    the picture, and when she sent it. None until she sends it."""
    row = today_row(connection, day)
    if row is None or row["status"] != "ready" or not row["shared_at"]:
        return None
    card = for_screen(row)
    return {"sentence": card["sentence"], "scene": card["scene"], "picture": card["picture"], "time": card["shared_time"]}
