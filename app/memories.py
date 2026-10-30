# app/memories.py
# The Memory book (docs/SPEC.md feature 10). She tells Buddy a memory from
# her life; Muse Spark writes it up as a keepsake page in her own words, and
# Muse Image paints one picture for it, always in the same watercolor style.
#
# During the talk, the save_memory tool only stores what was said (tools
# never use the internet, app/tools.py). The page is written and painted
# afterward in the background (make_page), so Buddy answers her right away.
# Plain code checks the AI's page before it is kept: every name and number
# must come from the talk, and there is no advice. Otherwise the page is
# simply her own words (docs/SAFETY.md section 8a).

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from app import db, family, guard, meta_client, prompts
from app.config import get_settings

# The one style every picture in the book shares, so the pages belong
# together. People stay small and faceless: never a real person's likeness.
STYLE = (
    "A soft watercolor storybook illustration, hand-painted on textured paper, with gentle washes and loose, "
    "light ink lines. A warm, calm palette of peach, amber, rose, and soft violet with creamy white space. "
    "Cozy and nostalgic, like a page from a beloved picture book. No text, letters, or numbers anywhere. "
    "Any people are small figures seen from behind or far away, with no detailed faces."
)

FALLBACK_TITLE = "A memory"
# Painted when the AI couldn't write the page, so every page still has a picture.
FALLBACK_SCENE = "A sunny window with lace curtains, a vase of garden flowers, and an open photo album on the sill."
# Writing or painting longer than this: offer "Paint it again". Longer than
# the slowest real job (4 tries of up to 3 minutes each to paint).
STUCK_MINUTES = 15
MAX_TITLE = 70
MAX_PARAGRAPH = 700
MAX_SCENE = 400

# The answer the writer fills in (structured output, a strict JSON schema).
PAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "paragraphs": {"type": "array", "items": {"type": "string"}},
        "scene": {"type": "string"},
    },
    "required": ["title", "paragraphs", "scene"],
    "additionalProperties": False,
}

# A picture file starts with its type's own bytes. Anything else is not saved.
PICTURE_KINDS = {b"RIFF": "webp", b"\x89PNG": "png", b"\xff\xd8\xff": "jpg"}
MEDIA_TYPES = {"webp": "image/webp", "png": "image/png", "jpg": "image/jpeg"}
PICTURE_NAME = re.compile(r"^\d+\.(webp|png|jpg)$")


def pictures_dir() -> Path:
    """data/memories/, next to the database (git-ignored with it)."""
    return Path(get_settings().database_path).parent / "memories"


def picture_path(name: str) -> Path | None:
    """Where a saved picture is. Only names we made ("3.webp") are used."""
    return pictures_dir() / name if PICTURE_NAME.match(name or "") else None


# ---------- No invented facts ----------

WORD = re.compile(r"[A-Za-z][A-Za-z'’]*|\d+")


def plain(word: str) -> str:
    """ "Maria's" -> "maria", "Summers" -> "summer": so a name or word she
    said still counts with a possessive or a plural."""
    word = re.sub(r"['’]s$", "", word.lower())
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def invented(text: str, said: str) -> list[str]:
    """The names and numbers in the page that never came up in the talk.

    A name is a word with a capital letter that doesn't start a sentence
    ("I" doesn't count). So "We went to Paris in 1962" finds "Paris" and
    "1962" if nobody said them."""
    known = {plain(word) for word in WORD.findall(said)}
    found = []
    for sentence in re.split(r"(?<=[.!?…])\s+|\n+", text.strip()):
        for index, word in enumerate(WORD.findall(sentence)):
            is_name = index > 0 and word[0].isupper() and word != "I" and not re.match(r"I['’]", word)
            if (word.isdigit() or is_name) and plain(word) not in known and word not in found:
                found.append(word)
    return found


def checked(answer: dict, said: str) -> tuple[dict | None, str]:
    """The writer's page if it keeps to the rules, else (None, what to fix)."""
    title = str(answer.get("title", "")).strip()
    paragraphs = [str(part).strip() for part in answer.get("paragraphs") or [] if str(part).strip()]
    scene = str(answer.get("scene", "")).strip()
    if not (title and len(title) <= MAX_TITLE and 2 <= len(paragraphs) <= 3 and scene
            and len(scene) <= MAX_SCENE and all(len(part) <= MAX_PARAGRAPH for part in paragraphs)):
        return None, "Write the page again: a short title, 2 or 3 short paragraphs, and a scene."
    words = title + ".\n" + "\n".join(paragraphs)
    if guard.check_reply(words + "\n" + scene) is not None:
        return None, "Write the page again with only her memory: no advice, lessons, or comments on health or feelings."
    made_up = invented(words, said)
    if made_up:
        return None, ("Write the page again using only her own details. These were not in what she said: "
                      + ", ".join(made_up) + ". Write the title in sentence case.")
    return {"title": title, "paragraphs": paragraphs, "scene": scene}, ""


# ---------- Writing and painting (the background job) ----------

def written_page(talk: list[dict], her_name: str) -> dict | None:
    """Ask Muse Spark for the page, and once more if it broke a rule.
    None when it still did (then the page is her own words)."""
    lines = "\n".join(("Buddy" if part["role"] == "assistant" else her_name) + ": " + part["content"] for part in talk)
    said = " ".join(part["content"] for part in talk)
    messages = [
        {"role": "developer", "content": prompts.MEMORY_PAGE.format(her_name=her_name)},
        {"role": "user", "content": "The talk:\n" + lines},
    ]
    for _ in range(2):
        # Room to spare: at 3000 the real AI once used it all thinking.
        answer = meta_client.structured(messages, "memory_page", PAGE_SCHEMA, reasoning="medium", max_tokens=6000)
        page, fix = checked(answer, said)
        if page:
            return page
        messages = messages + [{"role": "assistant", "content": json.dumps(answer)}, {"role": "developer", "content": fix}]
    return None


def set_status(connection, memory_id: int, status: str, **fields) -> None:
    """Change a page's status (and any other fields; names from our own code)."""
    fields.update(status=status, updated_at=db.now())
    connection.execute(
        "UPDATE memories SET " + ", ".join(f"{name} = ?" for name in fields) + " WHERE id = ?",
        [*fields.values(), memory_id],
    )


def write_page(connection, memory_id: int) -> None:
    row = connection.execute("SELECT her_words, talk FROM memories WHERE id = ?", (memory_id,)).fetchone()
    profile = db.get_profile(connection)
    # get_profile may write (it makes her profile row the first time), which
    # holds the database's write lock until a commit. Let go of it before
    # the AI thinks, so chat, pill reminders, and this screen never wait.
    connection.commit()
    try:
        page = written_page(json.loads(row["talk"]), profile["preferred_name"] or profile["name"] or "She")
    except meta_client.MetaError as problem:
        print(f"Writing memory page {memory_id} failed: {problem}")  # never her words
        page = None
    if page is None:
        page = {"title": FALLBACK_TITLE, "paragraphs": [row["her_words"]], "scene": FALLBACK_SCENE}
    set_status(connection, memory_id, "painting", title=page["title"],
               story=json.dumps(page["paragraphs"]), scene=page["scene"])


def paint_page(connection, memory_id: int) -> None:
    scene = connection.execute("SELECT scene FROM memories WHERE id = ?", (memory_id,)).fetchone()["scene"]
    try:
        picture = meta_client.paint(STYLE + "\n\nThe scene: " + (scene or FALLBACK_SCENE))
        kind = next((kind for start, kind in PICTURE_KINDS.items() if picture.startswith(start)), None)
        if kind == "webp" and picture[8:12] != b"WEBP":  # "RIFF" also starts sound and video files
            kind = None
        if kind is None:
            raise meta_client.MetaError("what came back was not a picture")
    except meta_client.MetaError as problem:
        print(f"Painting memory page {memory_id} failed: {problem}")
        set_status(connection, memory_id, "no_picture")
        return
    name = f"{memory_id}.{kind}"
    pictures_dir().mkdir(parents=True, exist_ok=True)
    (pictures_dir() / name).write_bytes(picture)
    set_status(connection, memory_id, "ready", picture=name)


def make_page(memory_id: int) -> None:
    """The background job after she saved a memory: write the page (unless
    it is written already), then paint it. Saves after each step, so the
    screen shows the title while the picture is painted, and nothing waits
    on the database while Meta works."""
    connection = db.get_connection()
    try:
        row = connection.execute("SELECT title, status FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None or row["status"] == "ready":
            return  # painted already: each page costs one painting
        if not row["title"]:
            set_status(connection, memory_id, "writing")
            connection.commit()
            write_page(connection, memory_id)
        set_status(connection, memory_id, "painting")
        connection.commit()
        paint_page(connection, memory_id)
        connection.commit()
    except Exception as problem:  # anything at all: never leave a page "writing" forever
        print(f"Memory page {memory_id} failed: {type(problem).__name__}")
        connection.rollback()
        set_status(connection, memory_id, "no_picture")
        connection.commit()
    finally:
        connection.close()


def paint_again(connection, memory_id: int) -> None:
    """ "Paint it again": back to writing (if it has no title) or painting.
    The caller runs make_page afterward."""
    row = connection.execute("SELECT title FROM memories WHERE id = ?", (memory_id,)).fetchone()
    set_status(connection, memory_id, "painting" if row["title"] else "writing")


# ---------- For the screen ----------

def curly(text: str) -> str:
    """A book's apostrophes: "Lucy's" -> "Lucy’s" (only inside words, so quotes stay as they are)."""
    return re.sub(r"(?<=\w)'(?=\w)", "’", text)


def for_screen(row, profile: dict) -> dict:
    """One page as the Memory book screen shows it, with a "Send to
    {family}" email link (the family update's mailto pattern)."""
    status = row["status"]
    stuck_since = (datetime.now() - timedelta(minutes=STUCK_MINUTES)).isoformat(timespec="seconds")
    if status in ("writing", "painting") and row["updated_at"] < stuck_since:
        status = "no_picture"  # the server probably restarted mid-way: offer "Paint it again"
    written = status != "writing"
    title = curly(row["title"] or (FALLBACK_TITLE if written else ""))
    paragraphs = [curly(part) for part in json.loads(row["story"]) or ([row["her_words"]] if written else [])]
    her = profile["preferred_name"] or profile["name"]
    mailto = ""
    if title and paragraphs:
        subject = f"A memory from {her}: {title}" if her else f"A memory: {title}"
        text = "\n\n".join([title, *paragraphs,
                            f"From {her + chr(39) + 's' if her else 'her'} memory book. Written by Grandma Buddy, "
                            "an AI helper, from her own words."])
        mailto = family.mailto(profile["family_email"], subject, text)
    return {
        "id": row["id"],
        "date": family.day_words(datetime.fromisoformat(row["created_at"]).date()),
        "title": title,
        "paragraphs": paragraphs,
        "scene": row["scene"],
        "status": status,
        "picture": f"/api/memories/{row['id']}/picture?v={row['picture']}" if status == "ready" else "",
        "mailto": mailto,
    }


def pages(connection) -> list[dict]:
    """Every page, newest first."""
    profile = db.get_profile(connection)
    return [for_screen(row, profile) for row in connection.execute("SELECT * FROM memories ORDER BY id DESC")]


def page(connection, memory_id: int) -> dict | None:
    row = connection.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    return for_screen(row, db.get_profile(connection)) if row else None
