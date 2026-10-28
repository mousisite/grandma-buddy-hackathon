# app/tools.py
# The companion's tools: things the AI can ask our code to do (function
# calling). Each tool only touches our own database or tells the screen to
# show something. No tool sends messages, calls anyone, or uses the internet.
#
# Every tool checks what the AI sent before using it, and always answers,
# even when the AI sent something odd, because Meta requires one answer per
# tool call.

import json

from app import db

MOODS = ["great", "good", "okay", "low", "very_low"]
SCREENS = ["today", "diary", "pills", "notes", "family", "scam"]
SCREEN_NAMES = {
    "today": "Today", "diary": "My diary", "pills": "My pills",
    "notes": "Doctor notes", "family": "Family", "scam": "Scam check",
}


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
        # Her own words, never the AI's: docs/SAFETY.md section 6.
        her_words = ". ".join(db.her_recent_words(connection, context["conversation_id"]))
        pain = args.get("pain_level")
        if not (isinstance(pain, int) and 0 <= pain <= 10):
            pain = None
        source = {"diary": "diary", "check_in": "check_in"}.get(context["mode"], "chat")
        db.add_symptom(
            connection,
            her_words,
            source=source,
            body_area=str(args.get("body_area", ""))[:60],
            pain_level=pain,
            since=str(args.get("since", ""))[:60],
        )
        return {"ok": True, "saved": her_words}, []

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
