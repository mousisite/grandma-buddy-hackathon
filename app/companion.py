# app/companion.py
# Buddy's reply, after the safety net has checked her words
# (app/routes/companion.py runs the safety net first).
#
# 1. Build the instructions (app/prompts.py) and the recent conversation.
# 2. Ask Muse Spark, letting it use tools (app/tools.py), at most 3 rounds.
# 3. Check the reply with the advice guard (app/guard.py) and swap in fixed
#    text if it gave advice.
# 4. Add fixed safety lines and buttons that must always appear:
#    - she asked for advice -> Call doctor, Call family, Add to doctor notes
#    - a diary entry was saved -> Call doctor, Call family
#    - side effects or a missed dose -> the fixed lines from SAFETY.md
#    - a crisis in the last day -> Call 988 and Call family stay visible
#    - a memory talk's last answer -> the memory is saved for the Memory book

import json
import re
import threading
from datetime import date

from app import briefing, db, guard, meta_client, prompts, reminders, safety, scam, tools

MAX_TOOL_ROUNDS = 3
# (Tried Nov 1 and dropped: a second, words-only request in parallel with
# the tool round, to skip the round after a tool. Asked for words alone, the
# model sometimes wrote about her instead of to her, "I'll sit with her in
# it", which no rule can catch. So a reply after a tool always comes from
# the round after it, with the tool's answer in view.)
# While a slow tool runs, Buddy says this right away (plain words, never the
# AI's), so she isn't left in silence. The page gets it as an event
# (app/routes/companion.py); it is never kept as part of the reply.
BRIDGES = {
    "look_up_today": "Let me look that up.",
    "get_pills_due": "Let me check your pills.",
    "mark_pill_taken": "Let me mark that down.",
    "save_memory": "Let me write that down.",
}
DIARY_MAX_ANSWERS = 4  # her first answer plus up to three follow-ups
MEMORY_MAX_ANSWERS = 3  # her memory plus one or two follow-ups
LAST_ANSWER = {"diary": (DIARY_MAX_ANSWERS, prompts.LAST_DIARY_ANSWER),
               "memory": (MEMORY_MAX_ANSWERS, prompts.LAST_MEMORY_ANSWER)}
EMPTY_REPLY = "I'm listening. Tell me more whenever you're ready."
TROUBLE_REPLY = "I'm sorry, I'm having trouble thinking right now. Please try again in a moment."
# Meta has no tool_choice "none", so words are asked for with this instead.
WORDS_NOW = "Now answer her in a few warm words. Don't call any tools."


# ---------- Spoken words only ----------

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def spoken(text: str) -> str:
    """Buddy's reply as plain spoken words: no emoji, list bullets, headings,
    or markdown stars, which look odd and sound odd read aloud."""
    text = EMOJI.sub("", text)
    text = re.sub(r"^\s*(?:[-*•]|\d+[.)]|#+)\s+", "", text, flags=re.MULTILINE)  # a bullet or heading at a line's start
    text = re.sub(r"[*_`#]+", "", text)
    return " ".join(text.split())


# ---------- What Buddy knows about her, for its instructions ----------

def day_words(day: str) -> str:
    """ "2026-10-27" -> "Tuesday, October 27" """
    when = date.fromisoformat(day)
    return f"{when:%A, %B} {when.day}"


def opener(reply: str) -> str:
    """How a reply began: its first four words ("Oh, that sounds lovely")."""
    return " ".join(reply.split()[:4]).rstrip(".,!?;:")


def memory_for_prompt(connection) -> dict:
    """Her facts, the last few days' talks, how she likes to talk (once
    learned), and how Buddy's last reply began (so the next starts differently)."""
    return {
        "facts": tools.facts_for_prompt(connection),
        "summaries": [(day_words(row["day"]), row["summary"]) for row in db.recent_summaries(connection)],
        "notes": [row["note"] for row in db.style_notes(connection)],
        "days_learned": db.days_learned(connection),
        "last_opener": opener(db.buddy_last_reply(connection)),
    }


def words_only(messages: list[dict]) -> str:
    """One more call that should answer in words. A tool it still asks for is not run."""
    return meta_client.chat(messages + [{"role": "developer", "content": WORDS_NOW}], tools=tools.TOOLS)["content"] or ""


def say_bridge(context: dict, tool_names: list[str]) -> None:
    """A slow tool is about to run: say its bridge line, once per reply."""
    words = next((BRIDGES[name] for name in tool_names if name in BRIDGES), "")
    if words and context.get("on_bridge") and not context.get("bridged"):
        context["bridged"] = True
        context["on_bridge"](words)


def ask_the_ai(messages: list[dict], context: dict, buttons: list[dict]) -> str:
    """Ask Muse Spark, running any tools it asks for. Returns its words."""
    for _ in range(MAX_TOOL_ROUNDS):
        answer = meta_client.chat(messages, tools=tools.TOOLS)
        if not answer["tool_calls"]:
            if answer["content"]:
                return answer["content"]
            # No words and no tools (it used up its room thinking): ask again
            # the same way, so it can still use a tool, like saving the entry.
            continue
        # Meta needs the whole assistant message back, then one tool answer
        # per call, before the next turn.
        messages.append(answer["message"])
        names = [call["name"] for call in answer["tool_calls"]]
        say_bridge(context, names)
        for call in answer["tool_calls"]:
            result, new_buttons = tools.run_tool(call["name"], call["arguments"], context)
            add_buttons(buttons, new_buttons)  # the AI may ask for the same buttons twice
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
        # Save what the tools wrote before asking the AI again, so "I took it"
        # and the 30-second pill check never wait on a slow AI reply.
        context["connection"].commit()
    # Still no words after 3 rounds: one last call that asks for words.
    return words_only(messages)


def todays_weather(connection, profile: dict) -> dict | None:
    """Today's forecast for her town (app/briefing.py, Open-Meteo), or None
    without a town or when it can't be fetched just now."""
    town = (profile.get("city") or "").strip()
    if not town:
        return None
    try:
        return briefing.look_up(connection, "weather", town)
    except (meta_client.MetaError, briefing.WeatherError) as problem:
        print(f"Today's weather couldn't be fetched: {problem}")  # never her words
        return None


def add_buttons(buttons: list[dict], more: list[dict]) -> None:
    """Add buttons, skipping any that are already there."""
    for button in more:
        if button not in buttons:
            buttons.append(button)


def answer(connection, profile: dict, conversation_id: str, text: str, mode: str, on_bridge=None) -> dict:
    """Buddy's reply to her words, ready for the screen. Saves it too.
    on_bridge (optional) is called with a fixed line to say while a slow
    tool runs (BRIDGES), so the page can speak it at once."""
    crisis = db.crisis_recently(connection)
    prompt = prompts.companion_prompt(profile, mode, crisis, memory_for_prompt(connection))
    # A "Something hurts" talk ends at her 4th answer and a memory talk at
    # her 3rd, so Buddy is told it is the last one: save now.
    limit, last_words = LAST_ANSWER.get(mode, (0, ""))
    last_answer = bool(limit) and len(db.her_recent_words(connection, conversation_id, limit=limit)) >= limit
    if last_answer:
        prompt += last_words
    buttons: list[dict] = []
    if scam.sounds_like_a_story(text):
        prompt += prompts.SCAM_STORY_TOLD.format(family=profile["family_name"].strip() or "your family")
    elif guard.seeks_advice(text):
        prompt += prompts.ADVICE_ASKED  # answer her question first, the no-advice way
    elif briefing.asks_about_today(text):
        weather = todays_weather(connection, profile) if briefing.asks_about_weather(text) else None
        if weather:
            # The forecast is in hand (plain code, Open-Meteo): the model gets
            # it to say, and the screen its source line, with no tool round.
            prompt += prompts.WEATHER_IN_HAND.format(town=profile["city"].strip(), weather=weather["text"])
            buttons.append({"type": "sources", "sites": weather["sites"], "from": weather["from"]})
        else:
            prompt += prompts.LOOK_UP_ASKED  # look today's weather, news, or game up before answering
    messages = [{"role": "developer", "content": prompt}]
    messages += db.recent_history(connection, limit=20)
    context = {"connection": connection, "profile": profile, "conversation_id": conversation_id, "mode": mode,
               "on_bridge": on_bridge}

    try:
        reply = spoken(ask_the_ai(messages, context, buttons)) or EMPTY_REPLY
    except meta_client.MetaError as problem:
        print(f"Chat failed: {problem}")  # never her words, only what went wrong
        reply = TROUBLE_REPLY

    # The advice guard: a second safety layer on every AI reply.
    verdict = guard.check_reply(reply, own_pills=db.active_pill_names(connection))
    if verdict == "advice":
        reply = guard.NO_ADVICE_REPLY
    elif verdict == "therapy":
        reply = guard.gentle_reply(profile["family_name"])

    if verdict == "advice" or guard.seeks_advice(text):
        add_buttons(buttons, tools.call_doctor(profile) + tools.call_family(profile))
        add_buttons(buttons, [tools.add_question_action(text)])

    # Is Buddy still asking her something? Judged on its own words, before
    # the fixed lines below are added after them.
    still_asking = reply.rstrip().rstrip("\"'”’").endswith("?")

    for note in guard.fixed_notes(text):
        if note == guard.SIDE_EFFECT_TEXT:
            # Side effects always go in the diary (docs/SAFETY.md section 5),
            # once: in a "Something hurts" talk, as part of its one entry.
            if mode == "diary":
                her_words = tools.joined(db.her_recent_words(connection, conversation_id, limit=6))
                db.save_talk_entry(connection, conversation_id, her_words)
            elif not context.get("diary_saved"):
                db.add_symptom(connection, text, source="check_in" if mode == "check_in" else "chat",
                               conversation_id=conversation_id)
            context["diary_saved"] = True
        if note not in reply:
            reply += " " + note

    # A saved diary entry is always followed by Call doctor and Call family
    # (docs/SPEC.md feature 3), even if the AI forgot to show them.
    if context.get("diary_saved"):
        add_buttons(buttons, tools.call_doctor(profile) + tools.call_family(profile))

    if crisis:
        crisis_buttons = safety.call_buttons("crisis", profile["family_name"], profile["family_phone"])
        add_buttons(buttons, [b for b in crisis_buttons if b["href"] in ("tel:988", f"tel:{profile['family_phone']}")])

    # A "Something hurts" talk is done once its entry is saved and Buddy
    # isn't asking anything more, or at her last answer. The page then goes
    # back to ordinary talk.
    diary_done = mode == "diary" and (
        (db.talk_has_entry(connection, conversation_id) and not still_asking) or last_answer
    )

    # A memory talk is saved by her last answer, even if the AI forgot, so
    # her story is never lost. It is done once saved and Buddy isn't asking.
    if mode == "memory" and last_answer and not context.get("memory_saved"):
        memory_id, new = tools.save_memory(connection, conversation_id, mode)
        if new:
            context["memory_saved"] = memory_id
        if memory_id:
            add_buttons(buttons, [tools.OPEN_MEMORY_BOOK])
    memory_done = mode == "memory" and ((bool(context.get("memory_saved")) and not still_asking) or last_answer)

    # "Tell Maria the tulips came up": the "Send this to Maria" button
    # appears even if the AI forgot its tool, with her words (never the AI's).
    if mode == "chat" and not any(button.get("type") == "message" for button in buttons):
        asked = tools.message_she_asked_for(text, profile["family_name"])
        if asked:
            add_buttons(buttons, [tools.family_message_button(asked, [text], profile)])

    db.save_message(connection, conversation_id, "assistant", reply)
    connection.commit()
    return {
        "reply": reply,
        "show": None,
        "actions": buttons,
        "diary_saved": context.get("diary_saved", False),  # a diary entry was saved in this reply
        "diary_done": diary_done,
        # A Memory book page was saved: its id. The route writes and paints it next.
        "memory_saved": context.get("memory_saved"),
        "memory_done": memory_done,
    }


# ---------- Learning about her, a day at a time ----------

# After her first talk each day, Buddy learns from the days before: a short
# summary of each (so it remembers what they talked about), and its notes on
# how she likes to talk, which sharpen day by day. From her third day, Buddy
# follows those notes (app/prompts.py). Plain code checks every word kept.
LEARN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "notes"],
    "additionalProperties": False,
}
MAX_SUMMARY = 400
MAX_NOTES = 8
MAX_NOTE = 80
_learning = threading.Lock()  # one learning job at a time


def checked_summary(summary) -> str:
    """The day's summary, or "" if it is long or has anything the advice
    guard or the safety net would react to."""
    summary = " ".join(str(summary or "").split())
    if len(summary) > MAX_SUMMARY or guard.check_reply(summary) is not None or safety.check(summary) is not None:
        return ""
    return summary


def checked_notes(notes, forgotten: set[str]) -> list[str]:
    """Her style notes as kept: short, never about health, hard feelings,
    or her mind (tools.private), never one she asked to forget, at most 8."""
    kept = []
    for note in notes if isinstance(notes, list) else []:
        note = " ".join(str(note).split()).rstrip(".")
        if note and len(note) <= MAX_NOTE and not tools.private(note) and note.lower() not in forgotten \
                and note.lower() not in (one.lower() for one in kept):
            kept.append(note)
    return kept[:MAX_NOTES]


def learn_from_past_days() -> None:
    """The background job after a chat: learn from each earlier day not yet
    learned from (the last two weeks, at most 5 at a time), oldest first.
    Commits after each day and never holds the database while the AI thinks."""
    if not _learning.acquire(blocking=False):
        return  # already learning
    connection = db.get_connection()
    try:
        profile = db.get_profile(connection)
        connection.commit()  # get_profile may write: let go before the AI thinks
        her = profile["preferred_name"] or profile["name"] or "Her"
        for day in db.days_to_learn(connection, reminders.current_time().date().isoformat()):
            notes = [row["note"] for row in db.style_notes(connection)]
            forgotten = [row["note"] for row in db.style_notes(connection, forgotten=True)]
            talk = "\n".join(("Buddy" if part["role"] == "assistant" else her) + ": " + part["content"]
                             for part in db.day_talk(connection, day))
            messages = [
                {"role": "developer", "content": prompts.LEARN_DAY.format(her_name=her)},
                {"role": "user", "content": f"Buddy's notes so far:\n{prompts.bullets(notes) or '(none yet)'}\n\n"
                                            f"Notes she asked Buddy to forget:\n{prompts.bullets(forgotten) or '(none)'}\n\n"
                                            f"Their talk on {day_words(day)}:\n{talk}"},
            ]
            try:
                answer = meta_client.structured(messages, "day_learned", LEARN_SCHEMA, reasoning="low")
            except meta_client.MetaError as problem:
                print(f"Learning from {day} failed: {problem}")  # never her words; tried again after the next chat
                break
            db.save_learned_day(connection, day, checked_summary(answer.get("summary")),
                                checked_notes(answer.get("notes"), {note.lower() for note in forgotten}))
            connection.commit()
    except Exception as problem:  # never break her chat over this
        print(f"Learning failed: {type(problem).__name__}")
        connection.rollback()
    finally:
        connection.close()
        _learning.release()
