# app/guard.py
# The advice guard: plain Python rules that check every reply the AI writes,
# AFTER it is written and BEFORE she sees or hears it. A second safety layer
# on top of the companion prompt (app/prompts.py).
#
# - Medical, medicine, or food advice -> swapped for the fixed no-advice
#   reply from docs/SAFETY.md section 2.
# - Psychological advice or minimizing ("cheer up", "deep breaths") ->
#   swapped for a fixed gentle reply that points to real people
#   (docs/SAFETY.md section 7).
#
# The rules are kept narrow on purpose, so normal friendly chat like
# "That sounds like a lovely day" is never changed. tests/test_guard.py
# checks both sides.

import re

from app.safety import normalize

# ---------- Fixed texts (docs/SAFETY.md sections 2, 5, and 7) ----------

NO_ADVICE_REPLY = (
    "I'm sorry, I can't give medical advice. Your doctor is the right person for that. "
    "Would you like me to call them, or add this question to your doctor notes? "
    "If it feels like an emergency, call 911."
)

GENTLE_REPLY = (
    "I'm here with you, and I'm glad you told me. "
    "The people who care about you can help with this more than I can. "
    "Would you like to call {family_name} or talk to your doctor?"
)

MISSED_DOSE_TEXT = "Please check the label or call your pharmacist about what to do."
SIDE_EFFECT_TEXT = "Please call your doctor or pharmacist today and tell them."


def gentle_reply(family_name: str = "") -> str:
    return GENTLE_REPLY.format(family_name=family_name.strip() or "your family")


# ---------- What counts as advice in a reply ----------

# A number with a dose unit: "200 mg", "2 tablets".
DOSE = re.compile(r"\b\d+(\.\d+)? ?(mg|mcg|milligrams?|micrograms?|ml|milliliters?|tablets?|pills?|capsules?|drops?|units?)\b")

# An instruction ("you should", "try", "have you tried") followed closely by a health action.
INSTRUCTION = (
    r"you should|you could|you can|you might want to|try|trying|tried|i'd suggest|i suggest|i recommend"
    r"|i'd recommend|make sure to|be sure to|it's best to|it might help to|it may help to|consider"
    r"|don't forget to|remember to"
)
HEALTH_ACTION = (
    r"take|taking|stop|stopping|skip|skipping|double|rest|resting|ice|heat|eat|eating|drink|drinking"
    r"|avoid|avoiding|stretch\w*|exercise|elevate|apply|lie down|sleep|cut back|reduce"
)
INSTRUCTED_ACTION = re.compile(rf"\b({INSTRUCTION})\b(?:\s+\S+){{0,6}}?\s+\b({HEALTH_ACTION})\b")

# Saying how serious it is, what causes it, or naming a condition.
MINIMIZING_OR_CAUSE = re.compile(
    r"\b(probably nothing|nothing to worry about|nothing serious|not serious|isn't serious|not a big deal"
    r"|you'll be fine|caused by|a sign of|signs of|symptoms? of|you (might|may|probably|could) have)\b"
)
CONDITIONS = (
    r"sprain|strain|arthritis|infection|virus|flu|cold|fracture|inflammation|condition|disease|migraine"
    r"|heartburn|reflux|dehydration|deficiency|side effect|allergy|anxiety|depression|tendonitis"
    r"|pinched nerve|blood pressure|diabetes|old age"
)
GUESSING_A_CONDITION = re.compile(
    rf"\b(could|might|may|probably|likely|sounds like|seems like|looks like)\b(?: be)?(?: just)?"
    rf"(?: a| an| your| some)?(?: \w+){{0,2}}? ({CONDITIONS})\b"
)

# Medicines and home remedies she wasn't prescribed.
REMEDIES = re.compile(
    r"\b(ibuprofen|advil|motrin|aspirin|tylenol|acetaminophen|paracetamol|aleve|naproxen|antacids?|tums"
    r"|pepto|benadryl|antihistamines?|melatonin|supplements?|vitamins?|ice packs?|heating pads?|epsom"
    r"|herbal|chamomile|painkillers?|pain relievers?|cough syrup)\b"
)

# ---------- What counts as therapy or minimizing feelings ----------

THERAPY = re.compile(
    r"\b(deep breaths?|breathing exercises?|meditat\w*|mindful\w*|cheer up|bright side|think positive\w*"
    r"|positive thinking|you don't mean that|don't be sad|count your blessings|journal\w*|gratitude list"
    r"|therap\w*|counsel\w*|self care)\b"
)


def mentions_a_new_remedy(text: str, own_pills: list[str]) -> bool:
    """True if a medicine or remedy is mentioned that isn't one of her own pills."""
    own = " ".join(own_pills).lower()
    return any(match.group(0) not in own for match in REMEDIES.finditer(text))


def check_reply(reply: str, own_pills: list[str] | None = None) -> str | None:
    """Return "advice", "therapy", or None (the reply is fine as it is)."""
    text = normalize(reply)
    if (
        DOSE.search(text)
        or INSTRUCTED_ACTION.search(text)
        or MINIMIZING_OR_CAUSE.search(text)
        or GUESSING_A_CONDITION.search(text)
        or mentions_a_new_remedy(text, own_pills or [])
    ):
        return "advice"
    if THERAPY.search(text):
        return "therapy"
    return None


# ---------- What she says ----------

SEEKS_ADVICE = re.compile(
    r"\b(should i|can i take|what can i take|is it (ok|okay|safe|alright|all right) to"
    r"|is (this|it|that) (serious|bad|dangerous)|do i need (to see|to go|a doctor)|what do i do about)\b"
)
SIDE_EFFECT = re.compile(r"\b((make|makes|made|making) me (feel )?(dizzy|sick|sleepy|tired|nause\w*|drowsy|itchy|woozy)|side effects?)\b")
MISSED_DOSE = re.compile(
    r"\b((forgot|forget|missed|skipped) (to take )?(my )?(\w+ )?(pills?|medicines?|medications?|meds|doses?)"
    r"|didn't take my (\w+ )?(pills?|medicines?|medications?|meds))\b"
)


def seeks_advice(her_words: str) -> bool:
    """True when she asks something only a doctor or pharmacist should answer."""
    return SEEKS_ADVICE.search(normalize(her_words)) is not None


def fixed_notes(her_words: str) -> list[str]:
    """Fixed safety lines to add after Buddy's reply (docs/SAFETY.md section 5)."""
    text = normalize(her_words)
    notes = []
    if SIDE_EFFECT.search(text):
        notes.append(SIDE_EFFECT_TEXT)
    if MISSED_DOSE.search(text):
        notes.append(MISSED_DOSE_TEXT)
    return notes
