# scripts/check_messages.py
# Hand-run, real check of "Message Maria" and the daily postcard (feature
# 22, app/postcards.py and the offer_family_message tool). Costs about 2
# cents. Nothing is written to her real database: a throwaway one is used.
#   .venv\Scripts\python scripts\check_messages.py
# One part only: add `postcard`, `companion`, or `voice` after the script's name.
#
# 1. The postcard: three made-up lines of hers (one about her knee, which
#    plain code drops before the picker ever sees it). Muse Spark picks a
#    line and describes a scene; plain code checks both; Muse Image paints
#    it to test-output/postcard-check.webp.
# 2. The companion: "Tell Maria the tulips came up, come and see them Sunday".
#    Buddy should offer a "Send this to Maria" button with her words, never
#    its own, and never send anything itself.
# 3. A voice message: Buddy's natural voice says a made-up message from
#    Maria, and Muse Voice Transcribe writes it down (the words shown under
#    the recording on her Family screen).

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# A throwaway database, chosen before the app's settings are read.
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp(prefix="buddy-check-")) / "check.db")

HER_LINES = [
    "My knee is sore again this morning",
    "The tulips came up this morning, the red ones by the gate",
    "Leo is coming on Sunday to show me his bike",
]
HER_ASK = "Tell Maria the tulips came up, come and see them Sunday"


def check_postcard() -> int:
    from app import meta_client, postcards, tools

    print("=== The postcard")
    rows = [{"content": line, "created_at": f"2026-10-31T10:{20 + index}:00"} for index, line in enumerate(HER_LINES)]
    lines = postcards.postcard_lines(rows)
    print("lines the picker sees:", [line["text"] for line in lines])
    if any("knee" in line["text"] for line in lines):
        print("UNEXPECTED: the line about her knee reached the picker.")
        return 1
    try:
        pick, why = postcards.picked(lines, "Rose")
    except meta_client.MetaError as problem:
        print(f"FAILED: {problem}")
        return 1
    if pick is None:
        print(f"no postcard: {why} (the AI's pick was dropped by the checks; that is allowed, but look at why)")
        return 1
    print("her line, word for word:", pick["sentence"])
    print("the scene to paint:", pick["scene"])
    if pick["sentence"] not in HER_LINES:
        print("UNEXPECTED: the sentence is not one of her lines.")
        return 1
    try:
        picture, kind = postcards.painted(pick["scene"])
    except meta_client.MetaError as problem:
        print(f"FAILED to paint: {problem}")
        return 1
    out = ROOT / "test-output" / f"postcard-check.{kind}"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(picture)
    print(f"painted: {out} ({len(picture)} bytes)")
    return 0


def check_companion() -> int:
    from app import companion, db, meta_client, tools

    print("\n=== The companion: " + HER_ASK)
    db.init_db()
    connection = db.get_connection()
    try:
        db.get_profile(connection)
        connection.execute("UPDATE profile SET name = 'Rose', preferred_name = 'Rose', family_name = 'Maria', "
                           "family_phone = '555-0100' WHERE id = 1")
        connection.commit()
        profile = db.get_profile(connection)
        talk = f"check-{int(datetime.now().timestamp())}"
        db.save_message(connection, talk, "user", HER_ASK)
        connection.commit()
        try:
            answer = companion.answer(connection, profile, talk, HER_ASK, "chat")
        except meta_client.MetaError as problem:
            print(f"FAILED: {problem}")
            return 1
    finally:
        connection.close()
    print("Buddy says:", answer["reply"])
    buttons = [action for action in answer["actions"] if action.get("type") == "message"]
    print("buttons:", answer["actions"])
    if not buttons:
        print("UNEXPECTED: Buddy didn't offer to send her message (the tool was not called).")
        return 1
    if not tools.her_own_words(buttons[0]["text"], [HER_ASK]):
        print("UNEXPECTED: the button's words are not all hers.")
        return 1
    print("the button's words are hers:", buttons[0]["text"])
    return 0


def check_voice() -> int:
    """A voice message's words: Buddy's own natural voice (Kokoro, on this
    computer) says Maria's made-up message, and Muse Voice Transcribe writes
    it down the way app/voice_messages.py does, with her name as a hint."""
    from app import db, voice, voice_messages

    print("\n=== A voice message, written down")
    db.init_db()  # the throwaway database: the name hints come from its tables
    if not voice.available():
        print("Buddy's natural voice isn't set up here (scripts/get_voice.py), so there is no recording to try. Skipped.")
        return 0
    said = "Hi Mom, it's Maria. I'll bring Leo on Sunday to see the tulips."
    recording = voice.speech(said, voice.DEFAULT_VOICE, 1.0)
    words = voice_messages.words_of(recording, "Rose")
    print("said:  ", said)
    print("heard: ", words or "(nothing: Meta couldn't write it down)")
    if not words or "leo" not in words.lower() or "tulips" not in words.lower():
        print("UNEXPECTED: the words came back different from what was said.")
        return 1
    return 0


def main(args: list[str]) -> int:
    """All parts, or only one: `postcard` (about 1 cent), `companion`, or `voice` (well under 1 cent each)."""
    only = args[0] if args else ""
    failures = 0
    if only in ("", "postcard"):
        failures += check_postcard()
    if only in ("", "companion"):
        failures += check_companion()
    if only in ("", "voice"):
        failures += check_voice()
    print(f"\nAbout {'2 cents' if not only else 'a cent or less'}. {'All good.' if not failures else f'{failures} problem(s).'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
