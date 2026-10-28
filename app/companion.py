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

import json

from app import db, guard, meta_client, prompts, safety, tools

MAX_TOOL_ROUNDS = 3
DIARY_MAX_ANSWERS = 4  # her first answer plus up to three follow-ups
EMPTY_REPLY = "I'm listening. Tell me more whenever you're ready."
TROUBLE_REPLY = "I'm sorry, I'm having trouble thinking right now. Please try again in a moment."
# Meta has no tool_choice "none", so words are asked for with this instead.
WORDS_NOW = "Now answer her in a few warm words. Don't call any tools."


def words_only(messages: list[dict]) -> str:
    """One more call that should answer in words. A tool it still asks for is not run."""
    return meta_client.chat(messages + [{"role": "developer", "content": WORDS_NOW}], tools=tools.TOOLS)["content"] or ""


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
        for call in answer["tool_calls"]:
            result, new_buttons = tools.run_tool(call["name"], call["arguments"], context)
            buttons.extend(new_buttons)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
    # Still no words after 3 rounds: one last call that asks for words.
    return words_only(messages)


def add_buttons(buttons: list[dict], more: list[dict]) -> None:
    """Add buttons, skipping any that are already there."""
    for button in more:
        if button not in buttons:
            buttons.append(button)


def answer(connection, profile: dict, conversation_id: str, text: str, mode: str) -> dict:
    """Buddy's reply to her words, ready for the screen. Saves it too."""
    crisis = db.crisis_recently(connection)
    prompt = prompts.companion_prompt(profile, mode, crisis)
    # A "Something hurts" talk ends at her 4th answer, so Buddy is told
    # it is the last one: save now if something hurts.
    answers = len(db.her_recent_words(connection, conversation_id, limit=DIARY_MAX_ANSWERS)) if mode == "diary" else 0
    last_answer = answers >= DIARY_MAX_ANSWERS
    if last_answer:
        prompt += prompts.LAST_DIARY_ANSWER
    messages = [{"role": "developer", "content": prompt}]
    messages += db.recent_history(connection, limit=20)
    context = {"connection": connection, "profile": profile, "conversation_id": conversation_id, "mode": mode}
    buttons: list[dict] = []

    try:
        reply = ask_the_ai(messages, context, buttons).strip() or EMPTY_REPLY
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

    db.save_message(connection, conversation_id, "assistant", reply)
    connection.commit()
    return {
        "reply": reply,
        "show": None,
        "actions": buttons,
        "diary_saved": context.get("diary_saved", False),  # a diary entry was saved in this reply
        "diary_done": diary_done,
    }
