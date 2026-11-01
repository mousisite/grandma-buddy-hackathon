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
#
# A page can also start from an old photo of hers (docs/SAFETY.md 8e): SAM
# 3.1 checks for people (fail closed: unsure counts as people), Muse Spark
# says what it shows and asks one question (never who anyone is), and the
# page waits ("telling") for her story. With people in it, her own photo is
# the page's picture, kept on this computer and never painted; without, the
# book's watercolor is painted from the written scene as usual.

import base64
import json
import re
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from app import briefing, db, family, finder, guard, meta_client, prompts, reader
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
PICTURE_NAME = re.compile(r"^(photo-|postcard-)?\d+\.(webp|png|jpg)$")  # a painting, her own photo, or a postcard

# A page from an old photo: what Spark fills in, and the fixed words used
# instead when its description breaks a rule or it can't look.
PHOTO_SCHEMA = {
    "type": "object",
    "properties": {"scene": {"type": "string"}, "question": {"type": "string"}},
    "required": ["scene", "question"],
    "additionalProperties": False,
}
PHOTO_OPENING = "What a lovely photo. What do you remember about that day?"
MAX_PHOTO_SCENE = 300
MAX_QUESTION = 160
UNTOLD_FOR = timedelta(days=1)  # a photo she never told about is forgotten after this


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

def written_page(talk: list[dict], her_name: str, photo_scene: str = "") -> dict | None:
    """Ask Muse Spark for the page, and once more if it broke a rule.
    None when it still did (then the page is her own words). For a page
    from her old photo, the writer is told what the photo shows, and those
    words count as hers."""
    lines = "\n".join(("Buddy" if part["role"] == "assistant" else her_name) + ": " + part["content"] for part in talk)
    said = " ".join(part["content"] for part in talk) + " " + photo_scene
    about_photo = f"She started this memory from an old photo of hers. What the photo shows: {photo_scene}\n\n" if photo_scene else ""
    messages = [
        {"role": "developer", "content": prompts.MEMORY_PAGE.format(her_name=her_name)},
        {"role": "user", "content": about_photo + "The talk:\n" + lines},
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
    row = connection.execute("SELECT her_words, talk, photo_scene FROM memories WHERE id = ?", (memory_id,)).fetchone()
    profile = db.get_profile(connection)
    # get_profile may write (it makes her profile row the first time), which
    # holds the database's write lock until a commit. Let go of it before
    # the AI thinks, so chat, pill reminders, and this screen never wait.
    connection.commit()
    try:
        page = written_page(json.loads(row["talk"]), profile["preferred_name"] or profile["name"] or "She",
                            row["photo_scene"])
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
        row = connection.execute("SELECT title, status, photo, people FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None or row["status"] in ("ready", "telling"):
            return  # painted already (each page costs one painting), or her story isn't told yet
        if not row["title"]:
            set_status(connection, memory_id, "writing")
            connection.commit()
            write_page(connection, memory_id)
        if row["people"] and row["photo"]:
            # People in her photo: it is the page's picture itself, kept here
            # and never painted, so no likeness is ever made.
            use_photo_as_picture(connection, memory_id, row["photo"])
        else:
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


def use_photo_as_picture(connection, memory_id: int, photo: str) -> None:
    """Her own photo as the page's picture: a copy under the picture's name."""
    picture = f"{memory_id}.{photo.rsplit('.', 1)[-1]}"
    shutil.copyfile(pictures_dir() / photo, pictures_dir() / picture)
    set_status(connection, memory_id, "ready", picture=picture)


# ---------- A page from an old photo ----------

def photo_bytes(image: str) -> tuple[bytes, str]:
    """The photo's bytes and kind ("jpg") from a data URL. ValueError when it
    isn't a picture file."""
    raw = base64.b64decode(image.split(",", 1)[1], validate=True)
    kind = next((kind for start, kind in PICTURE_KINDS.items() if raw.startswith(start)), None)
    if kind == "webp" and raw[8:12] != b"WEBP":
        kind = None
    if kind is None:
        raise ValueError("not a picture")
    return raw, kind


def has_people(image: str) -> bool:
    """Does SAM 3.1 see a person? Unsure (SAM down) counts as yes: a photo
    that might show someone is never painted."""
    try:
        return finder.best_match(finder.parse_matches(meta_client.segment(image, "person"))) is not None
    except meta_client.MetaError as problem:
        print(f"The person check couldn't look: {problem}")  # never her photo
        return True


def checked_description(scene: str, question: str) -> bool:
    """Spark's words about the photo keep to the rules: short, a question,
    no name or number, no "who", nothing about health, no advice."""
    both = scene + " " + question
    return bool(
        scene and question and len(scene) <= MAX_PHOTO_SCENE and len(question) <= MAX_QUESTION
        and question.endswith("?") and not re.search(r"\bwho\b", question, re.IGNORECASE)
        and not invented(both, "") and not briefing.HEALTH.search(both) and not reader.ADVICE.search(both)
        and guard.check_reply(both) is None
    )


def described(image: str) -> tuple[str, str]:
    """What the photo shows and one question, from Muse Spark; ("", "")
    when it can't look or its words break a rule (then PHOTO_OPENING)."""
    messages = [
        {"role": "developer", "content": prompts.PHOTO_MEMORY},
        {"role": "user", "content": [
            {"type": "text", "text": "Here is her old photo."},
            {"type": "image_url", "image_url": {"url": image}},
        ]},
    ]
    try:
        answer = meta_client.structured(messages, "photo_scene", PHOTO_SCHEMA, reasoning="low", max_tokens=1500)
    except meta_client.MetaError as problem:
        print(f"Describing her photo failed: {problem}")
        return "", ""
    scene = " ".join(str(answer.get("scene", "")).split())
    question = " ".join(str(answer.get("question", "")).split())
    return (scene, question) if checked_description(scene, question) else ("", "")


def photo_page(connection, image: str) -> dict:
    """A new page from her old photo, waiting for her story ("telling"):
    the photo kept on this computer, whether people are in it, and what it
    shows. Returns what the talk needs: the page's id, its own talk's id,
    and Buddy's opening words. ValueError when the photo isn't a picture."""
    raw, kind = photo_bytes(image)
    people = has_people(image)
    scene, question = described(image)
    memory_id = db.add_memory(connection, "", "", [])
    conversation_id = f"photo-{memory_id}-{int(time.time())}"
    name = f"photo-{memory_id}.{kind}"
    pictures_dir().mkdir(parents=True, exist_ok=True)
    (pictures_dir() / name).write_bytes(raw)
    set_status(connection, memory_id, "telling", conversation_id=conversation_id, photo=name, people=int(people),
               photo_scene=scene)
    return {"id": memory_id, "conversation_id": conversation_id,
            "opening": f"{scene} {question}" if scene else PHOTO_OPENING}


def forget_untold(connection) -> None:
    """A photo she never told about is forgotten after a day, file and all."""
    before = (datetime.now() - UNTOLD_FOR).isoformat(timespec="seconds")
    rows = connection.execute(
        "SELECT id, photo FROM memories WHERE status = 'telling' AND created_at < ?", (before,)
    ).fetchall()
    for row in rows:
        path = picture_path(row["photo"])
        if path is not None:
            path.unlink(missing_ok=True)
        connection.execute("DELETE FROM memories WHERE id = ?", (row["id"],))


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
        # Her own photo, when the page started from one (the picture itself when people are in it).
        "photo": f"/api/memories/{row['id']}/photo?v={row['photo']}" if row["photo"] else "",
        "people": bool(row["people"]),
        "mailto": mailto,
    }


def pages(connection) -> list[dict]:
    """Every page, newest first."""
    profile = db.get_profile(connection)
    return [for_screen(row, profile) for row in connection.execute(
        "SELECT * FROM memories WHERE status != 'telling' ORDER BY id DESC"  # a photo not yet told about isn't a page
    )]


def page(connection, memory_id: int) -> dict | None:
    row = connection.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    return for_screen(row, db.get_profile(connection)) if row else None
