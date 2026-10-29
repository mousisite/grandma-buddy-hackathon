# app/scam.py
# "Check a message": is this text, email, or letter a scam?
# (docs/SPEC.md feature 7, docs/SAFETY.md section 8)
#
# 1. Plain rules (no AI) look for the red flags in SAFETY.md section 8. They
#    set a floor: the AI can make the verdict stronger, never weaker, and if
#    the AI is down, the rules still answer.
# 2. Muse Spark reads the message (or a photo of it) and fills in a form
#    (structured output): verdict, red flags in plain words, explanation.
# 3. "What to do" is always fixed text from SAFETY.md, never the AI's words.
#
# The emergency safety net does NOT run on these words: they are someone
# else's ("Grandma, I'm bleeding, send money" is a scam, not her emergency).
# Her own words always go through the safety net when she talks to Buddy.

import json
import re

from app import db, guard, meta_client, prompts, tools

VERDICTS = ["looks_safe", "suspicious", "likely_scam"]  # weakest to strongest
TITLES = {"likely_scam": "Likely scam", "suspicious": "Suspicious", "looks_safe": "Looks safe"}
MAX_FLAGS = 4

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["likely_scam", "suspicious", "looks_safe"]},
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
    "required": ["verdict", "red_flags", "explanation"],
    "additionalProperties": False,
}

# ---------- Fixed words (docs/SAFETY.md section 8) ----------

ALWAYS = [
    "Don't click links, reply, or call numbers in the message.",
    "Hang up. Call the real number yourself (from the back of your card or a bill), or call {family} first.",
    "Never share passwords, codes, bank numbers, or your Social Security number.",
]
LOOKS_SAFE = [
    "If you're not sure, call them at a number you already know, not one in the message.",
    "Never share passwords, codes, bank numbers, or your Social Security number.",
]
IF_YOU_PAID = [
    "Call your bank or card company right away.",
    "Report it to the FTC at ReportFraud.ftc.gov.",
    "Call the National Elder Fraud Hotline at 1-833-372-8311 (833-FRAUD-11), open 6 AM to 11 PM Eastern, every day.",
]
ELDER_FRAUD_HOTLINE = {"type": "call", "label": "Call the Elder Fraud Hotline", "href": "tel:18333728311"}
# Used when the rules found more than the AI said, or the AI's words can't be used.
RULES_EXPLANATION = {
    "likely_scam": "This message has the warning signs of a scam.",
    "suspicious": "Some things in this message are warning signs. Please be careful with it.",
}
NOT_SURE = "I'm not sure about this one. Don't click anything, and call {family} before you reply or pay."

# ---------- The rules ----------

# (plain words she sees, what kind of flag, pattern). Payment flags together
# with pressure or secrecy make a likely scam even on their own.
RED_FLAGS = [
    ("Asks to be paid with gift cards", "payment", r"\bgift ?cards?\b|itunes card|google play card"),
    ("Asks you to wire money", "payment", r"\bwire (transfer|the money|money)\b|western union|moneygram"),
    ("Asks for crypto, like Bitcoin", "payment", r"\bbitcoin\b|\bcrypto(currency)?\b|\bbtc\b"),
    ("Asks you to pay with a payment app", "payment", r"\b(zelle|venmo|cash ?app)\b"),
    ("Says a package is held until you pay", "payment",
     r"\b(package|parcel|delivery|shipment)\b.{0,60}\b(on hold|held|undeliver\w*|fee|pay)\b|\bredeliver"),
    ("Asks you to keep it secret", "secrecy", r"\b(don'?t|do not) tell\b|keep (this|it) (a )?secret|between us"),
    ("Pushes you to act right now", "pressure",
     r"\b(urgent|urgently|immediately|act now|call now|right away|within 24 hours|final notice|expires today)\b"),
    ("Threatens arrest or trouble", "pressure", r"\barrest\w*\b|\bwarrant\b|legal action|\blawsuit\b|\bsuspended\b"),
    ("Says it's the IRS, Social Security, or Medicare", "other", r"\birs\b|social security|\bmedicare\b|tax refund"),
    ("Says you won a prize", "other", r"\byou('ve| have)? won\b|\bwinner\b|\bprize\b|\blottery\b|sweepstakes"),
    ("Says your computer has a problem", "other", r"\bvirus\b|\binfected\b|\bhacked\b|tech support"),
    ("Asks for private information", "other",
     r"\bpassword\b|\bpin\b|verification code|security code|one[- ]time code|"
     r"\b(bank|account|routing|card) number\b|social security number|\bssn\b"),
    ("Says it's family and needs money", "payment",
     r"\b(grandma|grandpa|grandson|granddaughter|it'?s me)\b.{0,200}(\bsend\b|\bmoney\b|\$\d|\bbail\b|\blawyer\b)"),
    ("Has a link to click", "other", r"https?://|www\.|\b[a-z0-9-]+\.(com|net|org|info|xyz|top|co)\b"),
]


def normalize(text: str) -> str:
    return text.lower().replace("’", "'").replace("‘", "'")


def rules_verdict(text: str) -> tuple[str | None, list[str]]:
    """The plain rules: (verdict or None, red flags in plain words)."""
    said = normalize(text)
    found = [(label, kind) for label, kind, pattern in RED_FLAGS if re.search(pattern, said, re.DOTALL)]
    kinds = {kind for _, kind in found}
    if len(found) >= 2 or ("payment" in kinds and kinds & {"pressure", "secrecy"}):
        verdict = "likely_scam"
    elif found:
        verdict = "suspicious"
    else:
        verdict = None
    return verdict, [label for label, _ in found]


def stronger(first: str | None, second: str | None) -> str | None:
    """The stronger of two verdicts (None means no verdict)."""
    ranked = [v for v in (first, second) if v]
    return max(ranked, key=VERDICTS.index) if ranked else None


# ---------- Cleaning up words ----------

def excerpt(text: str) -> str:
    """What is kept of a checked message: the start, with long numbers hidden
    (docs/SAFETY.md section 8: never account or Social Security numbers)."""
    return re.sub(r"\d{5,}", "•••", " ".join(text.split()))[:120]


def without_links_or_numbers(text: str) -> str:
    """The AI's words, without any link or phone number it copied from the
    message, so the screen never shows her something to tap or call."""
    text = re.sub(r"https?://\S+|www\.\S+|\b[\w-]+\.(com|net|org|info|xyz|top|co)\b\S*", "the link", text)
    text = re.sub(r"\+?\d[\d\-\s().]{6,}\d", "the number", text)
    return " ".join(text.split())


def ai_answer(text: str, image: str) -> dict | None:
    """Muse Spark's verdict, red flags, and explanation, or None if it is
    down or its answer doesn't fit the form."""
    if image:
        content = [
            {"type": "text", "text": "Here is a photo of the message she wants checked."},
            {"type": "image_url", "image_url": {"url": image}},
        ]
    else:
        content = "Here is the message she wants checked:\n\n" + text
    messages = [{"role": "developer", "content": prompts.SCAM}, {"role": "user", "content": content}]
    try:
        answer = meta_client.structured(messages, "scam_result", SCHEMA, reasoning="medium")
    except meta_client.MetaError as problem:
        print(f"Scam check failed: {problem}")  # never the message itself
        return None
    flags = answer.get("red_flags")
    if (answer.get("verdict") not in VERDICTS or not isinstance(answer.get("explanation"), str)
            or not isinstance(flags, list) or not all(isinstance(flag, str) for flag in flags)):
        return None
    return answer


# ---------- The whole check ----------

def check(connection, profile: dict, text: str, image: str, kind: str) -> dict:
    """Check one message (words, or a photo as a data URL). Saves a short
    record and returns what the screen shows."""
    family = profile.get("family_name") or "your family"
    rules, rule_flags = rules_verdict(text)
    ai = ai_answer(text, image)

    if ai is None:
        verdict = rules or "suspicious"
        flags = rule_flags
        explanation = RULES_EXPLANATION[rules] if rules else NOT_SURE.format(family=family)
    else:
        verdict = stronger(ai["verdict"], rules)
        ai_flags = [without_links_or_numbers(flag) for flag in ai["red_flags"] if flag.strip()]
        flags = ai_flags or rule_flags
        explanation = without_links_or_numbers(ai["explanation"])
        # The rules found more than the AI said, or the AI's words slipped
        # into advice: then its words don't fit, so fixed words are used.
        if verdict != ai["verdict"] or guard.check_reply(explanation) is not None:
            explanation = RULES_EXPLANATION.get(verdict, NOT_SURE.format(family=family))
            flags = flags if verdict == ai["verdict"] else rule_flags
    flags = flags[:MAX_FLAGS]

    connection.execute(
        "INSERT INTO scam_checks (created_at, input_kind, excerpt, verdict, red_flags) VALUES (?, ?, ?, ?, ?)",
        (db.now(), kind, "(photo)" if image else excerpt(text), verdict, json.dumps(flags)),
    )
    connection.commit()

    actions = []
    if verdict != "looks_safe":
        actions += tools.call_family(profile)
    if verdict == "likely_scam":
        actions.append(ELDER_FRAUD_HOTLINE)
    return {
        "verdict": verdict,
        "title": TITLES[verdict],
        "red_flags": flags,
        "explanation": explanation,
        "what_to_do": LOOKS_SAFE if verdict == "looks_safe" else [line.format(family=family) for line in ALWAYS],
        "if_you_paid": IF_YOU_PAID if verdict == "likely_scam" else [],
        "actions": actions,
    }

