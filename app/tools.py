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
from datetime import date, datetime, timedelta

from app import briefing, db, finder, guard, meta_client, reminders, safety

MOODS = ["great", "good", "okay", "low", "very_low"]
SCREENS = ["today", "diary", "pills", "notes", "family", "scam", "memories", "help", "read"]
SCREEN_NAMES = {
    "today": "Today", "diary": "My diary", "pills": "My pills",
    "notes": "Doctor notes", "family": "Family", "scam": "Scam check", "memories": "Memory book",
    "help": "Help", "read": "Read it to me",
}
# ---------- What Buddy remembers about her life ----------

FACT_KINDS = ["person", "pet", "hobby", "show", "event", "other"]
MAX_FACT = 200
MAX_FOLLOW_UP = 160
FOLLOW_UP_DAYS = 60  # a follow-up is planned for the next two months at most
EVENT_DAYS = 7  # an event stays in Buddy's mind for a week after it

# Words that never belong in a remembered fact or a learned note: health,
# medicines, hard feelings, and anything like a judgment of her mind. Her
# health goes in the diary (her own words), and crisis words are never kept.
PRIVATE = re.compile(
    r"\b(pain\w*|hurt\w*|ach(e|es|ing)|sick\w*|ill|illness\w*|diseas\w*|diagnos\w*|symptom\w*|medic\w*|pills?|"
    r"tablets?|doses?|hospital\w*|surger\w*|operation|cancer|dementia|alzheimer\w*|depress\w*|anxi\w*|lonel\w*|"
    r"sad\w*|grie\w*|mood\w*|confus\w*|forgetful\w*|memory loss|mental\w*|cognit\w*|declin\w*|"
    r"suicid\w*|kill\w*|self.harm|die|dying|dead)\b",
    re.IGNORECASE,
)


def private(words: str) -> bool:
    """True if these words are about health, hard feelings, or her mind,
    or the safety net or the advice guard would react to them."""
    return bool(PRIVATE.search(words)) or safety.check(words) is not None or guard.check_reply(words) is not None


def fact_problem(kind: str, fact: str, follow_up: str, follow_up_on: str) -> str:
    """Why a fact can't be remembered ("" when it can)."""
    if kind not in FACT_KINDS:
        return "kind must be one of " + ", ".join(FACT_KINDS)
    if not fact or len(fact) > MAX_FACT or len(follow_up) > MAX_FOLLOW_UP:
        return "Keep the fact and the follow-up short."
    if follow_up_on:
        try:
            when = date.fromisoformat(follow_up_on)
        except ValueError:
            return "follow_up_on must be a date like 2026-11-02, or empty."
        today = reminders.current_time().date()
        if not today <= when <= today + timedelta(days=FOLLOW_UP_DAYS):
            return "follow_up_on must be today or within the next two months."
    if private(fact) or private(follow_up):
        return "Only remember her life: people, pets, hobbies, shows, and plans. Never health or hard feelings."
    return ""


def facts_for_prompt(connection) -> list[str]:
    """What Buddy keeps in mind about her, newest first (at most 30)."""
    since = (reminders.current_time().date() - timedelta(days=EVENT_DAYS)).isoformat()
    lines = []
    for row in db.known_facts(connection, since):
        when = f" (around {date.fromisoformat(row['follow_up_on']):%A, %B} {date.fromisoformat(row['follow_up_on']).day})" \
            if row["kind"] == "event" and row["follow_up_on"] else ""
        lines.append(row["fact"] + when)
    return lines


MEMORY_MINUTES = 30  # a memory is what was said in the last half hour of the talk
# ponytail: a word count tells a new memory from "Yes please, save it";
# ask the AI to mark where a memory starts if this ever guesses wrong.
NEW_MEMORY_WORDS = 10
MEMORY_MODES = ("chat", "memory")  # never from a "Something hurts" talk or a check-in
SAVE_MEMORY_BUTTON = {"type": "memory", "label": "Save it in my memory book"}
OPEN_MEMORY_BOOK = {"type": "open", "screen": "memories", "label": "Open my memory book"}

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


# Buddy asking about her pills, in a check-in.
PILL_TOPIC = re.compile(r"\b(pills?|medicines?|medications?)\b", re.IGNORECASE)


def asks_about_pills(buddy_words: str, pill_names: list[str]) -> bool:
    """True when Buddy talks about her pills, in general ("your pills") or by
    name ("Did you take your Lisinopril?")."""
    said = set(re.findall(r"[a-z]+", buddy_words.lower()))
    return PILL_TOPIC.search(buddy_words) is not None or any(
        reminders.name_words(name) & said for name in pill_names
    )


def check_in_words(connection, conversation_id: str) -> str:
    """Her words about what hurts, in a daily check-in: what she said after
    Buddy asked whether anything hurts, until Buddy asked about her pills.
    So "I'm feeling pretty good" and "Yes, I took them" stay out of her diary.
    (If Buddy never asked about pain, her last few words, as in a chat.)"""
    pill_names = db.active_pill_names(connection)
    words, listening = [], False
    for row in db.talk_messages(connection, conversation_id):
        if row["role"] == "assistant":
            if not listening:
                listening = safety.pain_is_the_topic("chat", row["content"])
            elif asks_about_pills(row["content"], pill_names):
                break
        elif row["role"] == "user" and listening:
            words.append(row["content"])
    return joined(words[-6:] or db.her_recent_words(connection, conversation_id, limit=4))


def save_memory(connection, conversation_id: str, mode: str) -> tuple[int | None, bool]:
    """Save the memory she told in this talk for the Memory book: what was
    said in its last half hour, or since its last page (Buddy's questions
    too, so the writer understands her answers). The page is written and
    painted afterward (app/memories.py), never inside a tool.

    Returns (the page's id, True if it is a new page that still needs
    writing and painting), or (None, False) if she hasn't told one yet.
    Saving again is the same page, never a second painting:
    - a memory talk ("Tell Buddy a memory") makes one page;
    - in ordinary talk, a new page needs a new memory since the last one,
      not just "Yes please, save it"."""
    last = db.last_memory(connection, conversation_id)
    if last is not None and mode == "memory":
        return last["id"], False
    since = (datetime.now() - timedelta(minutes=MEMORY_MINUTES)).isoformat(timespec="seconds")
    after_last = last is not None and last["created_at"] >= since
    talk = db.memory_talk(connection, conversation_id, last["created_at"] if after_last else since)
    her_words = joined([part["content"] for part in talk if part["role"] == "user"])
    if after_last and len(words_in(her_words)) < NEW_MEMORY_WORDS:
        return last["id"], False
    if not her_words:
        return None, False
    return db.add_memory(connection, conversation_id, her_words, talk), True


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
    tool("remember_fact",
         "Remember something lasting about her life, to bring up warmly later: a person (their name and who they "
         "are to her), a pet, a hobby, a favorite show, or an upcoming event. Never health, medicines, or "
         "feelings. For an event, give a short, warm follow-up question to ask afterward and the date to ask it "
         "(YYYY-MM-DD, the day after the event); otherwise leave both empty.",
         {"kind": {"type": "string", "enum": FACT_KINDS},
          "fact": {"type": "string", "description": "In plain words, like \"Her grandson Tom visits on Sunday\"."},
          "follow_up": {"type": "string"},
          "follow_up_on": {"type": "string"}},
         ["kind", "fact", "follow_up", "follow_up_on"]),
    tool("offer_memory_page",
         "Show a button to save the memory she is telling you in her memory book, when she starts telling a "
         "memory from her life or says she wants to tell you one.",
         {}, []),
    tool("save_memory",
         "Save the memory she just told you in her memory book, when she says yes. Her words are saved "
         "automatically; Buddy then writes the page and paints a picture for it.",
         {}, []),
    tool("find_my_things",
         "Show a button to look for something she can't find (her glasses, keys, TV remote) in a photo of the "
         "room she takes.",
         {"thing": {"type": "string", "description": "What she is looking for, in a few words, like \"glasses\"."}},
         ["thing"]),
    tool("look_up_today",
         "Look up today's weather, one cheerful thing happening in her town, or how the local sports teams did, "
         "on the web. Only these three; never anything about health, medicine, or food.",
         {"topic": {"type": "string", "enum": sorted(briefing.QUESTIONS)}}, ["topic"]),
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
        db.save_mood(connection, context["conversation_id"], args["mood"], str(args.get("note", ""))[:200])
        return {"ok": True}, []

    if name == "log_symptom":
        # Her own words, never the AI's: docs/SAFETY.md section 6. Her first
        # message plus up to three follow-ups (4). A "Something hurts" talk
        # has its own conversation, so all of it is kept (6, with room to spare).
        diary = context["mode"] == "diary"
        if context["mode"] == "check_in":
            her_words = check_in_words(connection, context["conversation_id"])
        else:
            her_words = joined(db.her_recent_words(connection, context["conversation_id"], limit=6 if diary else 4))
        facts = {
            "body_area": from_her_words(args.get("body_area"), her_words),
            "pain_level": pain_she_said(args.get("pain_level"), her_words),
            "since": from_her_words(args.get("since"), her_words),
        }
        if diary or context["mode"] == "check_in":
            # One entry per "Something hurts" talk or check-in, even if the
            # AI saves again on a later turn.
            db.save_talk_entry(connection, context["conversation_id"], her_words, source=context["mode"], **facts)
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

    if name == "remember_fact":
        kind = str(args.get("kind", ""))
        fact = " ".join(str(args.get("fact", "")).split())
        follow_up = " ".join(str(args.get("follow_up", "")).split())
        follow_up_on = str(args.get("follow_up_on", "")).strip()
        problem = fact_problem(kind, fact, follow_up, follow_up_on)
        if problem:
            return {"ok": False, "error": problem}, []
        if not db.save_fact(connection, kind, fact, follow_up if follow_up_on else "", follow_up_on):
            return {"ok": False, "error": "She asked Buddy to forget this."}, []
        return {"ok": True}, []

    if name in ("offer_memory_page", "save_memory") and context["mode"] not in MEMORY_MODES:
        return {"ok": False, "error": "Memories are saved in ordinary talk or a memory talk, not here."}, []

    if name == "offer_memory_page":
        return {"ok": True}, [SAVE_MEMORY_BUTTON]

    if name == "save_memory":
        memory_id, new = save_memory(connection, context["conversation_id"], context["mode"])
        if memory_id is None:
            return {"ok": False, "error": "She hasn't told a memory in this talk yet."}, []
        if new:
            context["memory_saved"] = memory_id  # the route writes and paints it next
        return {"ok": True}, [OPEN_MEMORY_BOOK]

    if name == "find_my_things":
        thing = finder.clean_thing(str(args.get("thing", "")))
        if not thing:
            return {"ok": False, "error": "Ask her what she's looking for."}, []
        return {"ok": True}, [{"type": "find", "thing": thing, "label": f"Find my {thing}"}]

    if name == "look_up_today":
        # Our code writes the question for one of three topics (app/briefing.py),
        # so the AI can't search for anything else.
        topic = args.get("topic")
        if topic not in briefing.QUESTIONS:
            return {"ok": False, "error": "Only the weather, local news, or sports can be looked up."}, []
        town = (context["profile"].get("city") or "").strip()
        if not town:
            return {"ok": False, "error": "Her town isn't set up yet. A family member can add it in Settings, "
                                          "under Names and phone numbers."}, []
        try:
            found = briefing.look_up(connection, topic, town)
        except meta_client.MetaError as problem:
            print(f"Looking up today's {topic} failed: {problem}")  # never her words
            found = None
        if not found:
            return {"ok": False, "error": "Nothing good to share was found just now."}, []
        return {"ok": True, "found": found["text"], "from": found["sites"]}, [{"type": "sources", "sites": found["sites"]}]

    if name == "open_screen":
        screen = args.get("screen")
        if screen not in SCREENS:
            return {"ok": False, "error": "Unknown screen."}, []
        return {"ok": True}, [{"type": "open", "screen": screen, "label": "Open " + SCREEN_NAMES[screen]}]

    return {"ok": False, "error": f"There is no tool called {name}."}, []
