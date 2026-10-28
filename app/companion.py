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
#    - side effects or a missed dose -> the fixed lines from SAFETY.md
#    - a crisis in the last day -> Call 988 and Call family stay visible

import json

from app import db, guard, meta_client, prompts, safety, tools

MAX_TOOL_ROUNDS = 3
EMPTY_REPLY = "I'm listening. Tell me more whenever you're ready."
TROUBLE_REPLY = "I'm sorry, I'm having trouble thinking right now. Please try again in a moment."


def ask_the_ai(messages: list[dict], context: dict, buttons: list[dict]) -> str:
    """Ask Muse Spark, running any tools it asks for. Returns its words."""
    for _ in range(MAX_TOOL_ROUNDS):
        answer = meta_client.chat(messages, tools=tools.TOOLS)
        if not answer["tool_calls"]:
            if answer["content"]:
                return answer["content"]
            # No words and no tools: ask once more, for words only.
            return meta_client.chat(messages, tools=tools.TOOLS, tool_choice="none")["content"] or ""
        # Meta needs the whole assistant message back, then one tool answer
        # per call, before the next turn.
        messages.append(answer["message"])
        for call in answer["tool_calls"]:
            result, new_buttons = tools.run_tool(call["name"], call["arguments"], context)
            buttons.extend(new_buttons)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
    # Still asking for tools after 3 rounds: one last call that must answer in words.
    final = meta_client.chat(messages, tools=tools.TOOLS, tool_choice="none")
    return final["content"] or ""


def add_buttons(buttons: list[dict], more: list[dict]) -> None:
    """Add buttons, skipping any that are already there."""
    for button in more:
        if button not in buttons:
            buttons.append(button)


def answer(connection, profile: dict, conversation_id: str, text: str, mode: str) -> dict:
    """Buddy's reply to her words, ready for the screen. Saves it too."""
    crisis = db.crisis_recently(connection)
    messages = [{"role": "developer", "content": prompts.companion_prompt(profile, mode, crisis)}]
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

    for note in guard.fixed_notes(text):
        if note == guard.SIDE_EFFECT_TEXT:
            db.add_symptom(connection, text, source={"diary": "diary", "check_in": "check_in"}.get(mode, "chat"))
        if note not in reply:
            reply += " " + note

    if crisis:
        crisis_buttons = safety.call_buttons("crisis", profile["family_name"], profile["family_phone"])
        add_buttons(buttons, [b for b in crisis_buttons if b["href"] in ("tel:988", f"tel:{profile['family_phone']}")])

    db.save_message(connection, conversation_id, "assistant", reply)
    connection.commit()
    return {"reply": reply, "show": None, "actions": buttons}
