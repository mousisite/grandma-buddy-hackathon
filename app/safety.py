# app/safety.py
# The safety net: plain Python rules (no AI) that check everything she says
# BEFORE any AI is called. Rules come from docs/SAFETY.md sections 3 and 4.
#
# - Emergency warning signs  -> the red emergency screen (Call 911)
# - Medication mix-ups       -> the red Poison Control screen
# - Thoughts of dying        -> the calm crisis screen (Call or text 988)
#
# It works with no internet and no AI, and its messages are fixed text,
# copied word for word from docs/SAFETY.md. The AI never writes or changes them.
#
# The rules try to catch the many ways people really say these things
# ("I can hardly breathe", "I'm bleeding bad", "I wanna die"), while staying
# quiet on everyday talk ("I take my pills twice a day", "my chest of drawers
# is heavy"). tests/test_safety.py checks both sides. When unsure, a rule
# leans toward showing the screen: a false alarm is better than a missed one.

import re
from dataclasses import dataclass

# ---------- Fixed messages (word for word from docs/SAFETY.md) ----------

EMERGENCY_MESSAGE = "This could be an emergency. If it is, please call 911 right now."

POISON_CONTROL_MESSAGE = (
    "Please call Poison Control now at 1-800-222-1222. It's free. "
    "If you feel very sleepy, confused, or have trouble breathing, call 911."
)

CRISIS_MESSAGE = (
    "I'm really glad you told me. You matter, and you don't have to go through this alone. "
    "You can call or text 988 any time, day or night, to talk with someone kind. It's free. "
    "If you might hurt yourself or you're in danger right now, please call 911. "
    "Would you like to call {family_name} too?"
)

# If two kinds match, the most urgent one is shown first.
PRIORITY = ["emergency", "poison_control", "crisis"]


@dataclass
class SafetyResult:
    kind: str           # the screen to show: the most urgent kind that matched
    kinds: list[str]    # every kind that matched (each is saved as an event)
    matched: list[str]  # names of the rules that matched, for the records
    message: str        # the fixed message for that screen


# ---------- Cleaning up her words before checking ----------

# Long forms and missing apostrophes, turned into one standard spelling.
SPELLINGS = [
    (r"\bcan ?not\b", "can't"), (r"\bcant\b", "can't"),
    (r"\bdo not\b", "don't"), (r"\bdont\b", "don't"),
    (r"\bdoes not\b", "doesn't"), (r"\bdoesnt\b", "doesn't"),
    (r"\bdid not\b", "didn't"), (r"\bdidnt\b", "didn't"),
    (r"\bcould not\b", "couldn't"), (r"\bcouldnt\b", "couldn't"),
    (r"\bwould not\b", "wouldn't"), (r"\bwouldnt\b", "wouldn't"),
    (r"\bwill not\b", "won't"), (r"\bwont\b", "won't"),
    (r"\bis not\b", "isn't"), (r"\bisnt\b", "isn't"),
    (r"\bare not\b", "aren't"), (r"\barent\b", "aren't"),
    (r"\bwas not\b", "wasn't"), (r"\bwasnt\b", "wasn't"),
    (r"\bwere not\b", "weren't"), (r"\bwerent\b", "weren't"),
    (r"\bi am\b", "i'm"), (r"\bim\b", "i'm"), (r"\bive\b", "i've"),
    (r"\bwhats\b", "what's"), (r"\bwhat is\b", "what's"),
    (r"\bwanna\b", "want to"), (r"\bgonna\b", "going to"),
    (r"\bbreath\b(?= (well|right|properly|good))", "breathe"),  # a common typo
]

# Things that sound alarming but are not, replaced before checking.
HARMLESS = [
    r"\b(chest of drawers|treasure chest|tool chest|toy chest|hope chest|cedar chest|blanket chest|ice chest"
    r"|chest freezer|war chest)\b",
    r"\bpass(ed|ing)? out (the |some |a few )?(cookies|papers|flyers|programs|candy|food|bulletins|plates"
    r"|cards|presents|gifts|hymnals|treats|sandwiches)\b",
]


def normalize(text: str) -> str:
    """Lowercase, standard spellings, drop punctuation, remove harmless phrases."""
    t = text.lower()
    t = t.replace("’", "'").replace("‘", "'").replace("`", "'")
    t = re.sub(r"[^a-z0-9' ]+", " ", t)  # punctuation becomes spaces
    t = re.sub(r"\s+", " ", t).strip()
    for pattern, standard in SPELLINGS:
        t = re.sub(pattern, standard, t)
    for pattern in HARMLESS:
        t = re.sub(pattern, "something", t)
    return t


# ---------- Small helpers for writing rules ----------

def near(first: str, second: str, gap: int = 4) -> re.Pattern:
    """A pattern for two things within `gap` words of each other, either order.

    Example: near("chest", "tight") matches "my chest feels really tight"
    and "tightness in my chest".
    """
    between = rf"(?:\s+\S+){{0,{gap}}}?\s+"
    a = rf"\b(?:{first})\b"
    b = rf"\b(?:{second})\b"
    return re.compile(rf"{a}{between}{b}|{b}{between}{a}")


def words(pattern: str) -> re.Pattern:
    """A pattern for whole words or phrases."""
    return re.compile(rf"\b(?:{pattern})\b")


def fires(rule, cleaned: str) -> bool:
    """A rule is either a single pattern or an any_of/all_of combination."""
    if isinstance(rule, re.Pattern):
        return rule.search(cleaned) is not None
    return rule(cleaned)


def any_of(*parts):
    """A rule that fires if any part fires (a part is a pattern or another rule)."""
    return lambda t: any(fires(part, t) for part in parts)


def all_of(*parts):
    """A rule that fires only if every part fires."""
    return lambda t: all(fires(part, t) for part in parts)


SUDDEN = r"sudden\w*|all of a sudden|out of nowhere"
PAIN = r"pain\w*|hurt\w*|ach\w*|sore|cramp\w*"
LIMB = r"arms?|legs?|hands?|foot|feet"
PILLS = words(r"pills?|medicines?|medications?|meds|tablets?|doses?|capsules?")

# ---------- The rules (docs/SAFETY.md sections 3 and 4) ----------

RULES = [
    # Heart
    ("chest", "emergency", near(
        "chest",
        r"tight\w*|pressure|pain\w*|hurt\w*|ach\w*|squeez\w*|heavy|heaviness|crush\w*|burn\w*"
        r"|discomfort|killing|weight|flutter\w*|funny|sitting on",
        6,
    )),
    ("heart attack", "emergency", words(r"(i'm|i think i'm|i might be|i may be|am i) having a heart attack|heart attack right now")),
    ("pain spreading with sweating or nausea", "emergency", all_of(
        near(r"arm|jaw|neck|back|shoulder", PAIN, 3),
        words(r"sweat\w*|nause\w*|clammy|sick to my stomach|throw\w* up"),
    )),
    ("feels like dying", "emergency", words(r"i'm dying(?! to)|i think i'm dying|i feel like i'm dying|i think i'm going to die|i feel like i'm going to die")),
    # Breathing
    ("breathing", "emergency", any_of(
        words(r"(can't|couldn't|unable to|can hardly|can barely|hardly|barely) (breathe|get (my |a |any |enough )?(breath|air)|catch my breath)"),
        words(r"short(ness)? of breath|gasping|choking|can't get enough air"),
        near(r"hard|trouble|difficult\w*|struggl\w*|hard time", r"breath\w*|catch\w* my breath", 4),
    )),
    # Stroke: Balance, Eyes, Face, Arms, Speech, Time
    ("face drooping or numb", "emergency", any_of(
        near(r"face|mouth|smile", r"droop\w*|numb\w*|crooked|lopsided|sag\w*|uneven|tingl\w*", 5),
        words(r"can't feel my face"),
    )),
    ("arm or leg numb or weak", "emergency", any_of(
        near(LIMB, r"numb\w*|tingl\w*|dead|went numb", 4),
        words(r"can't (move|lift|feel) my (left |right )?(arm|leg|hand|foot|arms|legs|side)"),
        all_of(near(LIMB, r"weak\w*", 4), words(rf"{SUDDEN}|one side|left|right|half")),
    )),
    ("speech", "emergency", any_of(
        near(
            r"my (words?|speech|voice|tongue|mouth)|i'm (talking|speaking)",
            r"wrong|slurr\w*|funny|strange|jumbled|garbled|scrambled|mixed up|weird|thick|won't work"
            r"|not (coming out )?right|aren't (coming out )?right",
            4,
        ),
        words(r"slurr\w*|can't (get|find) (my|the) words( out)?|can't (speak|talk) (properly|clearly|straight)|can't talk right(?! now)"),
    )),
    ("eyes", "emergency", any_of(
        words(r"can't see (out of|at all|anything at all)|i suddenly can't see|double vision|seeing double"
              r"|lost (my )?(sight|vision)|went blind|going blind|everything (went|is|looks) (blurry|black|dark)"),
        near(SUDDEN, r"blurr\w*|blind|vision|can't see", 6),
    )),
    ("balance", "emergency", any_of(
        near(SUDDEN, r"balance|dizzy|spinning|can't walk|can't stand|fall\w* over", 6),
        words(r"lost my balance|room is spinning|room's spinning|everything is spinning|can't walk straight"),
    )),
    ("confusion or lost", "emergency", any_of(
        near(SUDDEN, r"confus\w*", 4),
        words(r"don't know where i('m| am)( at)?|where am i(?! (going|supposed|gonna|meant))"),
    )),
    ("worst headache", "emergency", any_of(words(r"worst headache"), near(SUDDEN, r"headache", 8))),
    # Fainting
    ("fainting", "emergency", words(
        r"fainted|fainting|feel(ing)? faint|felt faint|i'm faint|going to faint|pass(ed|ing)? out"
        r"|black(ed|ing)? out|can't stay awake|collapsed"
    )),
    # Bleeding
    ("bleeding", "emergency", any_of(
        near(
            r"bleed\w*|blood",
            r"won't stop|will not stop|can't stop|isn't stopping|not stopping|doesn't stop|so much|a lot|lots"
            r"|bad|badly|heav(y|ily)|everywhere|still",
            6,
        ),
        words(
            r"(cough\w*|vomit\w*|throw\w* up|spit\w*) (up )?blood|blood in my (stools?|poop|bowel movements?)"
            r"|(black|bloody) (stools?|poop|bowel movements?)|(stools?|poop|bowel movements?) (is|was|are|were|look\w*) (black|bloody)"
        ),
    )),
    # Falls and head injuries
    ("fall or head injury", "emergency", any_of(
        words(r"(hit|bumped|banged|knocked|cracked|smacked) (the (back|side|front|top) of )?my head|my head hit"),
        near(r"fell|fallen|fall|on the floor", r"can't get (back )?up|can't stand up", 6),
        words(r"woke up on the floor|can't get (back )?up off the floor|can't get off the floor"),
    )),
    # Allergic reaction
    ("allergic reaction", "emergency", any_of(
        near(r"throat", r"clos\w*|swell\w*|swollen|tight\w*", 4),
        near(r"lips?|tongue|face", r"swell\w*|swollen|puff\w*", 4),
        words(r"can't swallow|trouble swallowing|hard to swallow|difficulty swallowing"),
    )),
    # Other
    ("seizure", "emergency", words(r"seizure\w*|convuls\w*")),
    ("sudden severe belly pain", "emergency", all_of(
        near(r"sudden\w*|severe|terrible|awful|unbearable|worst|really bad", r"belly|stomach|tummy|abdomen|abdominal", 4),
        near(r"belly|stomach|tummy|abdomen|abdominal", PAIN, 4),
    )),
    # Medication mix-ups (Poison Control)
    ("medication mix-up", "poison_control", any_of(
        all_of(
            near(
                r"took|taken|swallowed",
                r"too many|too much|wrong|someone else's|an extra|extra|double"
                r"|my (husband|wife|sister|brother|neighbor|daughter|son|friend)'s",
                5,
            ),
            PILLS,
        ),
        # "twice" only counts with a sign it was a mistake ("twice a day" is fine)
        all_of(
            near(r"took|taken|swallowed", r"twice|again|two times", 5),
            words(r"by accident|by mistake|accidentally|i think|forgot i|may have|might have|oh no"),
        ),
        words(r"overdos\w*|double dose|doubled (up )?(on )?my (dose|pills|medicine)"),
    )),
    # Crisis: thoughts of dying or self-harm (docs/SAFETY.md section 4)
    ("thoughts of dying or self-harm", "crisis", words(
        r"want(ed|ing)? to die|ready to die|wish i (was|were|had been) dead|wish i'd die"
        r"|wish i (wasn't|weren't) (here|alive|around)|wish i'd never been born|wish i (was|were) never born"
        r"|rather be dead|better off dead|better off without me|better off if i (was|were) (gone|dead)"
        r"|no one would miss me|nobody would miss me|nobody would care if i"
        r"|kill(ing)? myself|end(ing)? (my (own )?life|it all)|tak(e|ing) my (own )?life"
        r"|(thinking (about|of)|want to|going to|might|could|feel like) (hurt|harm)(ing)? myself"
        r"|hurt(ing)? myself on purpose|self harm|cutting myself"
        r"|no reason to (live|go on)|nothing (left )?to live for|(tired|sick) of (living|life|being alive)"
        r"|what's the point (of|in) (living|going on|life|anything)|(isn't|not) worth living"
        r"|don't want to (be here|live|wake up|be alive|go on|be around)"
        r"|(hope|wish) i (don't|never|won't) wake up|never wake up again"
        r"|want (it|this|everything) (all )?to (be over|end|stop)|want it (all )?over"
        r"|suicid\w*|can't go on"
    )),
]


def check(text: str, family_name: str = "") -> SafetyResult | None:
    """Check her words. Returns what to show, or None if nothing matched."""
    cleaned = normalize(text)
    matched = [(name, kind) for name, kind, rule in RULES if fires(rule, cleaned)]
    if not matched:
        return None
    kinds = [kind for kind in PRIORITY if any(k == kind for _, k in matched)]
    return SafetyResult(
        kind=kinds[0],
        kinds=kinds,
        matched=[name for name, _ in matched],
        message=fixed_message(kinds[0], family_name),
    )


def as_hurting(text: str) -> str:
    """Her words with "it hurts" made plain.

    After she taps "Something hurts", or Buddy asks where it hurts, "my
    chest" means "my chest hurts". The rules for chest pain, pain spreading
    to the arm or jaw, and belly pain need a body part AND a pain word, so
    "hurts" is added on both sides, wherever she named the place.
    """
    return f"it hurts {text} hurts"


# Buddy's last words were about pain ("Where does it hurt?").
PAIN_TOPIC = words(r"pain\w*|hurt\w*|ache|aches|aching|sore\w*")


def pain_is_the_topic(mode: str, buddy_last_words: str) -> bool:
    """True in a "Something hurts" talk, or right after Buddy asked about pain."""
    return mode == "diary" or PAIN_TOPIC.search(normalize(buddy_last_words)) is not None


def check_recent(recent_messages: list[str], family_name: str = "") -> SafetyResult | None:
    """Check her last few messages together.

    Buddy asks one question at a time, so "my chest" and "tight" may come in
    two answers. Joined, they still show the emergency screen.
    """
    return check(" ".join(recent_messages[-3:]), family_name)


def merge(first: SafetyResult | None, second: SafetyResult | None, family_name: str = "") -> SafetyResult | None:
    """Combine two checks (this message, and her last few together)."""
    if first is None or second is None:
        return first or second
    kinds = [kind for kind in PRIORITY if kind in first.kinds or kind in second.kinds]
    matched = first.matched + [name for name in second.matched if name not in first.matched]
    return SafetyResult(kind=kinds[0], kinds=kinds, matched=matched, message=fixed_message(kinds[0], family_name))


def fixed_message(kind: str, family_name: str = "") -> str:
    if kind == "emergency":
        return EMERGENCY_MESSAGE
    if kind == "poison_control":
        return POISON_CONTROL_MESSAGE
    return CRISIS_MESSAGE.format(family_name=family_name.strip() or "your family")


def call_buttons(kind: str, family_name: str = "", family_phone: str = "") -> list[dict]:
    """The big call buttons for each screen (docs/SAFETY.md sections 3 and 4).

    The family button is left out until a family phone number is set up,
    so there is never a button that dials nothing.
    """
    family = []
    if family_phone.strip():
        label = f"Call {family_name.strip()}" if family_name.strip() else "Call family"
        family = [{"type": "call", "label": label, "href": f"tel:{family_phone.strip()}"}]
    call_911 = [{"type": "call", "label": "Call 911", "href": "tel:911"}]
    if kind == "emergency":
        return call_911 + family
    if kind == "poison_control":
        return [{"type": "call", "label": "Call Poison Control", "href": "tel:18002221222"}] + call_911 + family
    return (
        [{"type": "call", "label": "Call 988", "href": "tel:988"}, {"type": "call", "label": "Text 988", "href": "sms:988"}]
        + family
        + call_911
    )


def buttons_for(result: SafetyResult, family_name: str = "", family_phone: str = "") -> list[dict]:
    """The buttons for a result. If crisis words came together with an
    emergency or a pill mix-up, Call and Text 988 are added too."""
    buttons = call_buttons(result.kind, family_name, family_phone)
    if result.kind != "crisis" and "crisis" in result.kinds:
        buttons += [b for b in call_buttons("crisis") if b["href"] in ("tel:988", "sms:988")]
    return buttons
