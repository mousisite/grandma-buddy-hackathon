# Tests for the advice guard (app/guard.py): plain rules that check every AI
# reply AFTER it is written, as a second safety layer. If a reply gives any
# medical, mental-health, or food advice, it is swapped for fixed, reviewed
# text from docs/SAFETY.md. It must also stay quiet on normal friendly chat.

import pytest

from app import guard

# Replies that give advice and must be caught.
ADVICE = [
    "You could take 200 mg of ibuprofen for that.",
    "Try putting some ice on your knee.",
    "You should rest and drink plenty of water.",
    "It's probably nothing to worry about.",
    "That's probably nothing serious.",
    "It might be a sprain.",
    "That sounds like arthritis.",
    "Headaches like that can be caused by stress.",
    "That could be a sign of high blood pressure.",
    "Maybe a little Tylenol would help.",
    "I'd suggest you stop taking that pill.",
    "Eating more salt is bad for blood pressure, so try to avoid it.",
    "You might have a cold.",
    "Make sure to take two tablets with food.",
]

THERAPY = [
    "Let's take a few deep breaths together.",
    "Try to cheer up, things will look better tomorrow.",
    "You don't mean that.",
    "Have you tried meditation for your sadness?",
    "Look on the bright side!",
]

# Normal replies that must NOT be touched.
NORMAL = [
    "That sounds like a lovely day.",
    "It could be a nice afternoon for a walk with Maria.",
    "Did you take your Vitamin D this morning?",
    "Would you like to call Maria today?",
    "I've written that down for your doctor.",
    "Tell me more about your garden.",
    "That must have been hard. I'm here with you.",
    "What did you have for breakfast?",
    "Your tomatoes sound wonderful!",
    "I'm an AI helper, not a person, but I'm happy to keep you company.",
    "Where does it hurt?",
    "How bad is it, from 0 to 10?",
    "Since when has it felt like this?",
    "I'm sorry, I can't give medical advice. Your doctor is the right person for that.",
    "Would you like me to add that question to your doctor notes?",
    "Try calling Maria, she would love to hear from you.",
    "It's good to hear your voice this morning.",
]


@pytest.mark.parametrize("reply", ADVICE)
def test_advice_is_caught(reply):
    assert guard.check_reply(reply) == "advice", reply


@pytest.mark.parametrize("reply", THERAPY)
def test_therapy_and_minimizing_are_caught(reply):
    assert guard.check_reply(reply) == "therapy", reply


@pytest.mark.parametrize("reply", NORMAL)
def test_normal_friendly_replies_pass(reply):
    assert guard.check_reply(reply, own_pills=["Vitamin D"]) is None, reply


def test_her_own_pill_names_are_allowed():
    # Asking about her own pill is fine; recommending a new one is not.
    assert guard.check_reply("Did you take your vitamins today?", own_pills=["Daily vitamins"]) is None
    assert guard.check_reply("Did you take your vitamins today?") == "advice"


@pytest.mark.parametrize("words", [
    "I've had a headache since yesterday, should I go to the doctor?",
    "what should I eat for my blood pressure?",
    "should I stop my blood pressure pills? they make me dizzy",
    "can I take more ibuprofen for my back?",
    "I feel sad all the time, what should I do?",
    "is it okay to skip my pills today",
    "is this serious?",
])
def test_advice_seeking_questions_are_recognized(words):
    assert guard.seeks_advice(words)


@pytest.mark.parametrize("words", ["I'm so lonely today", "my knee hurts when I walk, about a 5", "Maria visited today"])
def test_everyday_words_are_not_advice_seeking(words):
    assert not guard.seeks_advice(words)


def test_side_effects_and_missed_doses_get_the_fixed_safety_lines():
    notes = guard.fixed_notes("should I stop my blood pressure pills? they make me dizzy")
    assert guard.SIDE_EFFECT_TEXT in notes
    assert guard.fixed_notes("I forgot my morning pills") == [guard.MISSED_DOSE_TEXT]
    assert guard.fixed_notes("I had a nice walk") == []


def test_fixed_texts_match_docs_safety():
    assert guard.NO_ADVICE_REPLY == (
        "I'm sorry, I can't give medical advice. Your doctor is the right person for that. "
        "Would you like me to call them, or add this question to your doctor notes? "
        "If it feels like an emergency, call 911."
    )
    assert guard.MISSED_DOSE_TEXT == "Please check the label or call your pharmacist about what to do."
    assert guard.SIDE_EFFECT_TEXT == "Please call your doctor or pharmacist today and tell them."
