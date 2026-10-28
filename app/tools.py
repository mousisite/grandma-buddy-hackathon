# app/tools.py
# The companion's tools: things the AI can ask our code to do (function
# calling). Each tool only touches our own database or tells the screen to
# show something. No tool sends messages, calls anyone, or uses the internet.
#
# Every tool checks what the AI sent before using it, and always answers,
# even when the AI sent something odd, because Meta requires one answer per
# tool call.

import json
import re
from datetime import datetime

from app import db, reminders

MOODS = ["great", "good", "okay", "low", "very_low"]
SCREENS = ["today", "diary", "pills", "notes", "family", "scam"]
SCREEN_NAMES = {
    "today": "Today", "diary": "My diary", "pills": "My pills",
    "notes": "Doctor notes", "family": "Family", "scam": "Scam check",
}

# ---------- Her own words in the diary (docs/SAFETY.md section 6) ----------

# Small words the AI may add around her words ("her left knee", "since Tuesday").
FILLER = {"a", "an", "the", "my", "her", "since", "about", "around", "in", "on", "of", "and", "at"}
NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
# A number followed by one of these is a time or a count, not a pain level ("for 2 days").
NOT_PAIN_AFTER = r"(minutes?|hours?|days?|weeks?|months?|years?|times?|o'clock|am|pm|of)\b"


def words_in(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def joined(parts: list[str]) -> str:
    """Her messages as one text: a period after each, unless she ended it with one."""
    return " ".join(part if part[-1:] in ".!?" else part + "." for part in parts)


def from_her_words(fact, her_words: str) -> str:
    """Keep a fact the AI filled in (where, since when) only if she said it.

    So "knee" is kept when she said "my knee", but "patella" or "possible
    sprain" is dropped. Her full words are always saved anyway. Small words
    in front ("her left knee", "since Tuesday") are left out, because the
    screen already says "Where:" and "Since:".
    """
    words = str(fact or "").strip()[:60].split()
    while words and words[0].lower() in FILLER:
        words = words[1:]
    said = set(words_in(her_words))
    meaningful = [word for word in words_in(" ".join(words)) if word not in FILLER]
    return " ".join(words) if meaningful and all(word in said for word in meaningful) else ""


def pain_she_said(pain, her_words: str):
    """Keep a pain number (0 to 10) only if she said it, as "5" or "five",
    and not as a time or a count ("sore for 2 days", "one of my knees")."""
    if not (isinstance(pain, int) and not isinstance(pain, bool) and 0 <= pain <= 10):
        return None
    number = rf"\b({pain}|{NUMBER_WORDS[pain]})\b(?!\s+{NOT_PAIN_AFTER})"
    return pain if re.search(number, her_words.lower()) else None


def tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """One tool definition in the format Meta's API expects."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOLS = [
    tool("log_mood", "Save how she says she feels overall right now.",
         {"mood": {"type": "string", "enum": MOODS}, "note": {"type": "string", "description": "A few of her own words."}},
         ["mood", "note"]),
    tool("log_symptom",
         "Save a diary entry about something physical she described. Her own words are saved automatically; "
         "fill in only where it is, how bad from 0 to 10 if she said, and since when if she said.",
         {"body_area": {"type": "string"},
          "pain_level": {"type": ["integer", "null"], "minimum": 0, "maximum": 10},
          "since": {"type": "string"}},
         ["body_area", "pain_level", "since"]),
    tool("add_doctor_question", "Save a question she wants to ask her doctor at her next visit.",
         {"question": {"type": "string"}}, ["question"]),
    tool("show_call_buttons", "Show big buttons to call her doctor, her family member, or both.",
         {"who": {"type": "string", "enum": ["doctor", "family", "both"]}}, ["who"]),
    tool("suggest_calling_family", "Show a big button to call her family member, when she sounds lonely.",
         {}, []),
    tool("open_screen", "Open a part of the app she asked to see.",
         {"screen": {"type": "string", "enum": SCREENS}}, ["screen"]),
    tool("get_pills_due",
         "List today's pill reminders: each pill's name, its time, and whether it is upcoming, due, taken, or "
         "missed. Doses are not included: never tell her a dose.",
         {}, []),
    tool("mark_pill_taken",
         "Write down that she took a pill, when she says she did. Use the pill's name, or \"all\" for every "
         "pill that is due now.",
         {"medication_name": {"type": "string"}}, ["medication_name"]),
]


# ---------- Buttons the screen can show ----------

def call_action(name: str, phone: str, fallback: str) -> list[dict]:
    """A call button, or nothing if that phone number isn't set up yet."""
    if not phone.strip():
        return []
    return [{"type": "call", "label": f"Call {name.strip() or fallback}", "href": f"tel:{phone.strip()}"}]


def call_doctor(profile: dict) -> list[dict]:
    return call_action(profile["doctor_name"], profile["doctor_phone"], "your doctor")


def call_family(profile: dict) -> list[dict]:
    return call_action(profile["family_name"], profile["family_phone"], "family")


def add_question_action(question: str) -> dict:
    return {"type": "add_question", "label": "Add to doctor notes", "question": question[:300]}


# ---------- Pills ----------

def clock_time(due_at: str) -> str:
    """ "2026-10-27T08:00:00" -> "8:00 AM"."""
    return datetime.fromisoformat(due_at).strftime("%I:%M %p").lstrip("0")


def name_for_ai(name: str) -> str:
    """A pill's name without a strength the family may have typed with it
    ("Lisinopril 10 mg" -> "Lisinopril"): the AI never hears a dose."""
    words = []
    for word in name.split():
        if word[0].isdigit():
            break
        words.append(word)
    return " ".join(words) or name


def mark_pill_taken(connection, pill_name: str) -> dict:
    """She says she took a pill: mark the right reminders taken
    (reminders.pick_taken decides which, with plain tested rules)."""
    now = reminders.current_time()
    chosen = reminders.pick_taken(reminders.reminders_now(connection, now), pill_name, now)
    if not chosen:
        return {"ok": False, "error": "No pill like that is due right now."}
    reminders.mark_taken(connection, [r["id"] for r in chosen], now)
    return {"ok": True, "marked": [name_for_ai(r["name"]) for r in chosen]}


# ---------- Running a tool ----------

def run_tool(name: str, raw_arguments: str, context: dict) -> tuple[dict, list[dict]]:
    """Run one tool the AI asked for. Returns (answer for the AI, buttons for the screen).

    context holds: connection, profile, conversation_id, mode.
    """
    try:
        args = json.loads(raw_arguments or "{}")
        if not isinstance(args, dict):
            raise ValueError
    except ValueError:
        return {"ok": False, "error": "The arguments were not valid."}, []

    connection = context["connection"]
    profile = context["profile"]

    if name == "log_mood":
        if args.get("mood") not in MOODS:
            return {"ok": False, "error": "mood must be one of " + ", ".join(MOODS)}, []
        connection.execute(
            "INSERT INTO moods (created_at, mood, note) VALUES (?, ?, ?)",
            (db.now(), args["mood"], str(args.get("note", ""))[:200]),
        )
        return {"ok": True}, []

    if name == "log_symptom":
        # Her own words, never the AI's: docs/SAFETY.md section 6. Her first
        # message plus up to three follow-ups (4). A "Something hurts" talk
        # has its own conversation, so all of it is kept (6, with room to spare).
        diary = context["mode"] == "diary"
        her_words = joined(db.her_recent_words(connection, context["conversation_id"], limit=6 if diary else 4))
        facts = {
            "body_area": from_her_words(args.get("body_area"), her_words),
            "pain_level": pain_she_said(args.get("pain_level"), her_words),
            "since": from_her_words(args.get("since"), her_words),
        }
        if diary:
            # One entry per "Something hurts" talk, even if the AI saves again.
            db.save_talk_entry(connection, context["conversation_id"], her_words, **facts)
        elif not context.get("diary_saved"):  # one entry per reply, even if the AI asks twice
            source = "check_in" if context["mode"] == "check_in" else "chat"
            db.add_symptom(connection, her_words, source, conversation_id=context["conversation_id"], **facts)
        context["diary_saved"] = True
        return {"ok": True, "saved": her_words}, []

    if name == "get_pills_due":
        # Names, times, and status only: the AI never sees the label, so it
        # can't repeat or change dose information (docs/SAFETY.md section 5).
        pills = [
            {"name": name_for_ai(r["name"]), "time": clock_time(r["due_at"]), "status": r["status"]}
            for r in reminders.reminders_now(connection, reminders.current_time())
        ]
        return {"ok": True, "pills": pills}, []

    if name == "mark_pill_taken":
        return mark_pill_taken(connection, str(args.get("medication_name", ""))), []

    if name == "add_doctor_question":
        question = str(args.get("question", "")).strip()[:300]
        if not question:
            return {"ok": False, "error": "The question was empty."}, []
        db.add_doctor_question(connection, question)
        return {"ok": True}, []

    if name == "show_call_buttons":
        who = args.get("who", "both")
        buttons = []
        if who in ("doctor", "both"):
            buttons += call_doctor(profile)
        if who in ("family", "both"):
            buttons += call_family(profile)
        return {"ok": True, "shown": len(buttons)}, buttons

    if name == "suggest_calling_family":
        buttons = call_family(profile)
        return {"ok": True, "shown": len(buttons)}, buttons

    if name == "open_screen":
        screen = args.get("screen")
        if screen not in SCREENS:
            return {"ok": False, "error": "Unknown screen."}, []
        return {"ok": True}, [{"type": "open", "screen": screen, "label": "Open " + SCREEN_NAMES[screen]}]

    return {"ok": False, "error": f"There is no tool called {name}."}, []
