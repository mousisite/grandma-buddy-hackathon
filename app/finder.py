# app/finder.py
# "Find my things" (docs/SPEC.md feature 12): she can't find her glasses,
# keys, or TV remote. She takes a photo of the room and says what she's
# looking for.
#
# 1. clean_thing turns what she said into one short noun phrase ("glasses").
# 2. SAM 3.1 (meta_client.segment) finds it and answers with one line: a box
#    around every match, with how sure it is.
# 3. parse_matches reads that line, and best_match picks the surest match.
# 4. Muse Spark looks at the photo and says where it is in plain words
#    ("Your glasses are on the side table, next to the lamp."). If Spark is
#    down, or its sentence isn't right for her, where_words says it in plain
#    code instead ("Your glasses are near the bottom left of your photo.").
#
# Her photo is never saved: not in the database, not on disk, not in logs.
# The safety net runs on what she said before any of this (app/routes/find.py).

import re

from app import guard, meta_client, prompts

MAX_WORDS = 4  # SAM wants a short noun phrase
MIN_SCORE = 0.5  # how sure SAM must be (0 to 1) before Buddy says "it's here"
MAX_SENTENCE_WORDS = 30  # Spark's sentence is read aloud: keep it short

LOOK_FAILED = "I couldn't look just now. Please try again in a moment."

# Words around the thing in what she said: "Buddy, where are my glasses?"
FILLER = {
    "hey", "ok", "okay", "oh", "buddy", "please", "where", "where's", "wheres", "are", "is", "did", "do",
    "i", "i've", "ive", "i'm", "im", "put", "leave", "can't", "cant", "cannot", "can", "could", "would",
    "you", "find", "lost", "misplaced", "help", "me", "have", "seen", "see", "look", "looking", "for",
    "my", "the", "a", "an", "again", "now", "today", "still", "just", "know",
}

# The words she might use for her things, and what SAM should look for.
# Make this list hers: add the words she actually says.
FIND_WORDS = {
    "specs": "glasses",
    "spectacles": "glasses",
    "eyeglasses": "glasses",
    "remote": "remote control",
    "tv remote": "remote control",
    "clicker": "remote control",
    "zapper": "remote control",
    "pills": "pill bottle",
    "pill": "pill bottle",
    "medicine": "pill bottle",
    "medicines": "pill bottle",
    "key": "keys",
    "house keys": "keys",
    "cell phone": "phone",
    "cellphone": "phone",
    "mobile": "phone",
}


# A few things SAM knows by another name. Buddy still says hers ("Your pill
# bottle is…"); only SAM is asked differently. Found with the real SAM 3.1
# (scripts/check_find.py): "pill bottle" matched nothing in the kitchen
# photo, while "medicine bottle" found it.
SAM_WORDS = {
    "pill bottle": "medicine bottle",
}


def sam_words(thing: str) -> str:
    """What to ask SAM to look for."""
    return SAM_WORDS.get(thing, thing)


def clean_thing(said: str) -> str:
    """What she's looking for, as a short noun phrase: "Buddy, where are my
    reading glasses?" -> "reading glasses". "" if she didn't name anything."""
    words = re.sub(r"[^a-z' -]", " ", said.lower().replace("’", "'")).split()
    kept = [word for word in words if word.strip("'-") and word not in FILLER]
    thing = " ".join(kept[-MAX_WORDS:])  # in English the thing's name comes last
    return FIND_WORDS.get(thing, thing)


# ---------- SAM 3.1's answer ----------

# One box: <|box;x1=100;y1=200;x2=199;y2=259;w=1000;h=800;c=0.91|>
# x1,y1 is the top-left corner, x2,y2 the bottom-right (inclusive), in the
# photo's own pixels. w,h is the photo's size; c is how sure SAM is.
# (Each box is followed by a mask, the exact outline. Its encoding isn't
# documented, so Buddy draws a soft halo around the box instead.)
BOX = re.compile(r"<\|box;([^|>]*)\|>")


def parse_matches(line: str) -> list[dict]:
    """Every match in SAM's answer line. [] when nothing matched (SAM sends
    an empty line) or the line isn't what we expect."""
    matches = []
    for found in BOX.finditer(line or ""):
        values = dict(part.split("=", 1) for part in found.group(1).split(";") if "=" in part)
        try:
            match = {key: int(values[key]) for key in ("x1", "y1", "x2", "y2")}
            match["w"] = int(values.get("w", 0))
            match["h"] = int(values.get("h", 0))
            match["score"] = float(values.get("c", 1.0))  # no c: SAM didn't say, so it counts as sure
        except (KeyError, ValueError):
            continue
        if match["x2"] >= match["x1"] and match["y2"] >= match["y1"]:
            matches.append(match)
    return matches


def best_match(matches: list[dict]) -> dict | None:
    """The match SAM is surest about, if it is sure enough."""
    surest = max(matches, key=lambda match: match["score"], default=None)
    if surest is None or surest["score"] < MIN_SCORE:
        return None
    return surest


# ---------- What Buddy says ----------

def is_or_are(thing: str) -> str:
    """"Your glasses are", "Your remote control is"."""
    return "are" if thing.endswith("s") and not thing.endswith("ss") else "is"


def where_words(thing: str, box: dict, width: int, height: int) -> str:
    """Where it is in the photo, in plain code (no AI): the fallback sentence."""
    across = (box["x1"] + box["x2"] + 1) / 2 / width
    down = (box["y1"] + box["y2"] + 1) / 2 / height
    side = "left" if across < 0.34 else "right" if across > 0.66 else ""
    level = "top" if down < 0.34 else "bottom" if down > 0.66 else ""
    if side and level:
        place = f"near the {level} {side} of your photo"
    elif side:
        place = f"on the {side} side of your photo"
    elif level:
        place = f"near the {level} of your photo"
    else:
        place = "in the middle of your photo"
    return f"Your {thing} {is_or_are(thing)} {place}."


def not_found(thing: str) -> str:
    """Said kindly when SAM found nothing."""
    return (f"I couldn't spot your {thing} in this photo. Could you take another one, "
            "maybe from a different spot with the lights on?")


SENTENCE_SCHEMA = {
    "type": "object",
    "properties": {"sentence": {"type": "string"}},
    "required": ["sentence"],
    "additionalProperties": False,
}


def percent(value: float, size: int) -> int:
    return round(100 * value / size)


def describe(image: str, thing: str, box: dict, width: int, height: int) -> str:
    """Muse Spark looks at the photo and says where the thing is, next to
    what. The sentence goes through the advice guard and a length check;
    if anything is off, she hears where_words instead."""
    area = (f"She is looking for: {thing}. It is in this part of the photo: from "
            f"{percent(box['x1'], width)}% to {percent(box['x2'] + 1, width)}% across (from the left), and from "
            f"{percent(box['y1'], height)}% to {percent(box['y2'] + 1, height)}% down (from the top).")
    messages = [
        {"role": "developer", "content": prompts.FIND},
        {"role": "user", "content": [
            {"type": "text", "text": area},
            {"type": "image_url", "image_url": {"url": image}},
        ]},
    ]
    fallback = where_words(thing, box, width, height)
    try:
        answer = meta_client.structured(messages, "where_it_is", SENTENCE_SCHEMA, reasoning="low", max_tokens=1500)
    except meta_client.MetaError as problem:
        print(f"Find: Spark couldn't describe it ({problem})")  # never her photo
        return fallback
    sentence = " ".join(str(answer.get("sentence") or "").split()).strip('"')
    if not sentence or len(sentence.split()) > MAX_SENTENCE_WORDS or guard.check_reply(sentence):
        return fallback
    return sentence


# ---------- The whole look ----------

def find(image: str, thing: str, width: int, height: int) -> dict:
    """Look for her thing in the photo. width and height are the photo's
    size, from the page (SAM's own w and h win when it sends them).
    Raises meta_client.MetaError when SAM can't look (the route says so kindly)."""
    match = best_match(parse_matches(meta_client.segment(image, sam_words(thing))))
    if match is None:
        return {"found": False, "sentence": not_found(thing)}
    width = match["w"] or width or match["x2"] + 1
    height = match["h"] or height or match["y2"] + 1
    box = {key: match[key] for key in ("x1", "y1", "x2", "y2")}
    return {
        "found": True,
        "sentence": describe(image, thing, box, width, height),
        "box": box,
        "width": width,
        "height": height,
    }
