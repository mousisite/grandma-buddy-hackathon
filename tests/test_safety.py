# Tests for the safety net (app/safety.py): plain rules, no AI.
# Covers every phrase in the table in section 10 of docs/SAFETY.md, at least
# two more ways of saying each emergency, and "near misses" that must NOT
# fire, so the screens only appear when they should. All phrases are made up.

import pytest

from app import safety

EMERGENCY = [
    # From docs/SAFETY.md section 10
    "my chest feels really tight",
    "I can't catch my breath",
    "the left side of my face feels droopy",
    "my words are coming out wrong",
    "I fell and hit my head on the counter",
    "worst headache of my life, it came on all of a sudden",
    # Heart
    "there's a lot of pressure in my chest",
    "I have chest pain",
    "my arm hurts and I'm sweating a lot",
    # Breathing
    "I cannot breathe",
    "it's really hard to breathe",
    "I'm choking",
    # Stroke (BE FAST)
    "my right arm suddenly went numb",
    "my speech is slurred",
    "I suddenly can't see out of one eye",
    "all of a sudden I lost my balance",
    "I feel suddenly confused",
    # Fainting
    "I fainted in the kitchen",
    "I passed out this morning",
    # Bleeding
    "my hand is bleeding and it won't stop",
    "I'm coughing up blood",
    # Falls
    "I fell and I can't get up",
    "I've fallen and can't get up",
    # Allergic reaction
    "my throat is closing up",
    "my lips are swelling",
    # Other
    "I think I'm having a seizure",
    "I don't know where I am",
    "I have sudden terrible pain in my belly",
    # More ways of saying it (found by a safety review, Oct 26)
    "I have shortness of breath",
    "I can hardly breathe",
    "it's hard to catch my breath",
    "I couldn't breathe last night and still can't",
    "I'm bleeding bad",
    "my stool was black",
    "I have black stools",
    "I fell and hit the back of my head",
    "I woke up on the floor",
    "I can't feel my face",
    "my arm went numb",
    "my words aren't coming out right",
    "I can't get my words out",
    "I'm feeling faint",
    "I don't know where I'm at",
    "I do not know where I am",
    "I think I'm dying",
    "I have chest discomfort",
    "my chest has been feeling kind of tight",
    "I'm having trouble swallowing",
    "I lost my balance and the room is spinning",
    "I'm having a heart attack",
    "I collapsed in the hall",
]

POISON_CONTROL = [
    "I took my pills twice by accident",          # from section 10
    "I think I took too many pills",
    "I took a double dose of my medicine",
    "I took the wrong pills this morning",
    "I took too much of my medicine",
    "I took my husband's pills by mistake",
]

CRISIS = [
    "I wish I wasn't here anymore",                # from section 10
    "I want to die",
    "I wish I were dead",
    "sometimes I want to end it all",
    "there's no reason to live",
    "everyone would be better off without me",
    "I don't want to wake up tomorrow",
    "I want to hurt myself",
    "I just want it all to be over",
    "I'm tired of living",
    "what's the point of living",
    "I wanna die",
    "I've been thinking about ending it all",
    "I'm thinking about killing myself",
    "I hope I don't wake up",
    "I do not want to wake up",
    "no one would miss me",
    "I'd rather be dead",
    "life isn't worth living anymore",
    "I still want to die",
]

NOT_AN_EMERGENCY = [
    "my chest of drawers is too heavy to move",    # from section 10
    "I'm so lonely today",                         # from section 10
    "my knee hurts when I walk, about a 5",        # from section 10
    "I've had a headache since yesterday, should I go to the doctor?",
    "what should I eat for my blood pressure?",
    "should I stop my blood pressure pills? they make me dizzy",
    "can I take more ibuprofen for my back?",
    "I feel sad all the time, what should I do?",
    "this knee is killing me",
    "I'm dying to see Maria on Sunday",
    "I took my pills this morning",
    "I watched a show about heart attacks",
    "Good morning, I slept well",
    # Everyday talk that used to set off a screen (safety review, Oct 26)
    "I take my pills twice a day",
    "I took all of my pills",
    "where am I going to put this",
    "I can't see anything without my glasses",
    "I can't talk right now, my show is on",
    "the cedar chest is heavy",
    "I hurt myself on the stairs yesterday",
    "my tomatoes are going to die",
    "my stomach hurts and the weather is awful",
    "I passed out the cookies at church",
    "my husband had a heart attack in 1998",
    "I gasped when I saw the price",
    "that man on TV was talking funny",
    "I get out of breath on the stairs",
    "I can't get up this early anymore",
]


@pytest.mark.parametrize("words", EMERGENCY)
def test_emergency_phrases_show_the_emergency_screen(words):
    result = safety.check(words)
    assert result is not None, words
    assert result.kind == "emergency"


@pytest.mark.parametrize("words", POISON_CONTROL)
def test_medication_mix_ups_show_poison_control(words):
    result = safety.check(words)
    assert result is not None, words
    assert result.kind == "poison_control"


@pytest.mark.parametrize("words", CRISIS)
def test_crisis_phrases_show_the_crisis_screen(words):
    result = safety.check(words)
    assert result is not None, words
    assert result.kind == "crisis"


@pytest.mark.parametrize("words", NOT_AN_EMERGENCY)
def test_everyday_words_do_not_fire(words):
    assert safety.check(words) is None, words


def test_curly_quotes_and_missing_apostrophes_still_match():
    assert safety.check("I can’t breathe").kind == "emergency"   # curly apostrophe
    assert safety.check("i cant breathe").kind == "emergency"    # no apostrophe
    assert safety.check("I CANNOT BREATHE").kind == "emergency"  # capitals


def test_a_symptom_split_across_answers_still_fires():
    # Buddy asks "Where?" then "How does it feel?" one question at a time.
    assert safety.check("my chest") is None
    assert safety.check("tight") is None
    result = safety.check_recent(["my chest", "tight"])
    assert result is not None and result.kind == "emergency"


def test_fixed_messages_match_docs_safety_word_for_word():
    assert safety.EMERGENCY_MESSAGE == "This could be an emergency. If it is, please call 911 right now."
    assert safety.POISON_CONTROL_MESSAGE == (
        "Please call Poison Control now at 1-800-222-1222. It's free. "
        "If you feel very sleepy, confused, or have trouble breathing, call 911."
    )
    crisis = safety.check("I want to die", family_name="Maria").message
    assert crisis == (
        "I'm really glad you told me. You matter, and you don't have to go through this alone. "
        "You can call or text 988 any time, day or night, to talk with someone kind. It's free. "
        "If you might hurt yourself or you're in danger right now, please call 911. "
        "Would you like to call Maria too?"
    )


def test_crisis_message_without_a_family_name_still_reads_well():
    message = safety.check("I want to die").message
    assert message.endswith("Would you like to call your family too?")


def test_emergency_outranks_crisis_but_both_are_reported():
    result = safety.check("I want to die and my chest feels tight")
    assert result.kind == "emergency"
    assert "crisis" in result.kinds


def test_merging_two_checks_keeps_every_kind():
    merged = safety.merge(safety.check("I took too many pills"), safety.check("my chest feels tight"))
    assert merged.kind == "emergency"
    assert merged.kinds == ["emergency", "poison_control"]
    assert safety.merge(None, None) is None


def test_crisis_together_with_an_emergency_adds_988():
    hrefs = [b["href"] for b in safety.buttons_for(safety.check("I took too many pills, I want to die"))]
    assert hrefs[0] == "tel:18002221222"
    assert "tel:988" in hrefs and "sms:988" in hrefs


def test_call_buttons_for_each_screen():
    emergency = safety.call_buttons("emergency", family_name="Maria", family_phone="555-0100")
    assert [b["href"] for b in emergency] == ["tel:911", "tel:555-0100"]
    poison = safety.call_buttons("poison_control", family_name="Maria", family_phone="555-0100")
    assert [b["href"] for b in poison] == ["tel:18002221222", "tel:911", "tel:555-0100"]
    crisis = safety.call_buttons("crisis", family_name="Maria", family_phone="555-0100")
    assert [b["href"] for b in crisis] == ["tel:988", "sms:988", "tel:555-0100", "tel:911"]
    # No family phone set up yet: that button is left out, never a broken link.
    assert [b["href"] for b in safety.call_buttons("emergency")] == ["tel:911"]
