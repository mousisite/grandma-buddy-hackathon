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
# 4. A phone number or web address in the words is looked up on the web
#    (Meta's web search, app/briefing.py's daily budget) at the same time:
#    plain code reads one word of the answer (REPORTED, CLEAR, UNKNOWN) and
#    shows fixed words and the sites. A report makes the verdict stronger,
#    never weaker; the number or address is never repeated to her.
#
# The emergency safety net does NOT run on these words: they are someone
# else's ("Grandma, I'm bleeding, send money" is a scam, not her emergency).
# Her own words always go through the safety net when she talks to Buddy.

import json
import re
from concurrent.futures import ThreadPoolExecutor

from app import briefing, db, guard, meta_client, prompts, reminders, tools

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


# A scam story told in a talk ("a man rang saying my grandson is in jail"):
# someone asking her to send, pay, or share, or one of the classic hooks.
# Found by the Buddy eval (Nov 2): without a nudge, Buddy asked gentle
# questions instead of warning her. Plain code hears the story; the prompt
# then tells Buddy to warn her in that same reply (prompts.SCAM_STORY_TOLD).
STORY = re.compile(
    r"\b(?:"
    r"(?:ask\w*|want\w*|told|tell\w*|said|saying) me to (?:send|pay|buy|wire|give|share|confirm|read out|transfer)"
    r"|gift cards?|processing fee|pay (?:a|the) fee|in jail|arrested|bail money|for bail"
    r"|computer (?:has|had|got) a virus|won (?:a|the) (?:prize|lottery)|prize money"
    r"|parcel .{0,30}?(?:fee|held|customs)"
    r"|(?:confirm|verify|give|send|share|read out|update) (?:my|your|the) "
    r"(?:password|pin|account|card number|bank details|social security)"
    r")\b",
    re.IGNORECASE,
)


def sounds_like_a_story(text: str) -> bool:
    """True when her own words tell a scam story (see STORY)."""
    return STORY.search(text) is not None


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


# ---------- Looking up a number or a web address (Meta's web search) ----------

# A phone number as people write them: (555) 010-0199, 555-010-0199,
# 1-800-555-0133, +1 555 010 0199. Never a bare code like 482913.
PHONE = re.compile(r"(?<![\w.])(?:\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\w.])")
# The endings a web address can have here (the same list wherever one is
# found or hidden). A web address, with or without https:// and www., never
# the domain of an email address, and never a sentence with a missing space
# ("back.Help"): the ending must be lowercase.
TLDS = r"com|net|org|info|xyz|top|co|biz|us|io|me|online|site|shop|club|live|link|help"
SITE = re.compile(rf"(?<![\w@.-])(?:https?://)?(?:www\.)?((?:[A-Za-z0-9-]+\.)+(?:{TLDS}))\b")
MAX_CONTACTS = 2  # looked up together, in one search
# The one word plain code reads from the web answer. CLEAR counts as nothing
# found: a real company's name proves nothing about a message that uses it.
LOOKUP_WORDS = {"REPORTED", "CLEAR", "UNKNOWN"}


def contacts(text: str) -> dict:
    """The phone numbers and web addresses in a message, as written, so they
    can be looked up: {"numbers": [...], "sites": [...]}, at most 2 each."""
    numbers = list(dict.fromkeys(" ".join(found.split()) for found in PHONE.findall(text)))[:MAX_CONTACTS]
    sites = list(dict.fromkeys(found.lower() for found in SITE.findall(text)))[:MAX_CONTACTS]
    return {"numbers": numbers, "sites": sites}


def lookup_words(reported: bool, found: dict) -> str:
    """Fixed words for what the web said, never the number or the address.
    With both a number and a website, a report may concern either one."""
    both = bool(found["numbers"] and found["sites"])
    if reported:
        if both:
            return "Something in it (the phone number or the website) has been reported as a scam online."
        return f"The {'phone number' if found['numbers'] else 'website'} in it has been reported as a scam online."
    what = "phone number and the website" if both else "phone number" if found["numbers"] else "website"
    return f"Nothing was found online about the {what} in it. That doesn’t make it safe."


def named_sites(sources: list[dict], found: dict) -> list[str]:
    """The sites the web answer came from, for the screen: never the
    looked-up address itself (or a site under it), and never a host that
    carries the looked-up number's digits, so the screen can't repeat them."""
    digits = [re.sub(r"\D", "", number) for number in found["numbers"]]
    sites = []
    for source in sources:
        host = briefing.site(source["url"])
        if not host or host in sites:
            continue
        if any(host == site or host.endswith("." + site) for site in found["sites"]):
            continue
        if any(number and number in re.sub(r"\D", "", host) for number in digits):
            continue
        sites.append(host)
    return sites[:briefing.MAX_SITES]


def searched(found: dict) -> dict | None:
    """Ask Meta's web search about the message's number or address (no town:
    a number is the same everywhere). Only the number or address is sent,
    never her name or the rest of the message. Returns
    {"reported", "words", "sites"} with fixed words, or None when the search
    failed, didn't really search, or its answer can't be read."""
    what = " or ".join(found["numbers"] + found["sites"])
    question = f"Is {what} reported as a scam, spam, fraud, or phishing? Search the web for it."
    try:
        answer = meta_client.search(question, prompts.SCAM_LOOKUP, "")
    except meta_client.MetaError as problem:
        print(f"Scam lookup failed: {problem}")  # never the message
        return None
    word = (answer["text"].split() or [""])[0].strip(".,:;!").upper()
    if not answer["searched"] or word not in LOOKUP_WORDS:
        return None
    return {"reported": word == "REPORTED", "words": lookup_words(word == "REPORTED", found),
            "sites": named_sites(answer["sources"], found)}


# ---------- Cleaning up words ----------

def excerpt(text: str) -> str:
    """What is kept of a checked message: the start, with long numbers hidden
    (docs/SAFETY.md section 8: never account or Social Security numbers)."""
    return re.sub(r"\d{5,}", "•••", " ".join(text.split()))[:120]


def without_links_or_numbers(text: str) -> str:
    """The AI's words, without any link or phone number it copied from the
    message, so the screen never shows her something to tap or call."""
    text = re.sub(rf"https?://\S+|www\.\S+|\b[\w-]+\.({TLDS})\b\S*", "the link", text, flags=re.IGNORECASE)
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
    # A number or web address in the words (never in a photo) is looked up on
    # the web meanwhile, in one of the day's 30 searches, while the AI reads.
    found = contacts(text) if text and not image else {"numbers": [], "sites": []}
    web = None
    with ThreadPoolExecutor(max_workers=1) as searcher:
        looking = None
        if (found["numbers"] or found["sites"]) and briefing.take_search(connection, reminders.current_time()):
            connection.commit()
            looking = searcher.submit(searched, found)
        ai = ai_answer(text, image)
        if looking is not None:
            web = looking.result()
    # A report online makes it a likely scam (never weaker), with a fixed red flag first.
    web_verdict = "likely_scam" if web and web["reported"] else None
    web_flags = [web["words"]] if web_verdict else []

    if ai is None:
        verdict = stronger(rules, web_verdict) or "suspicious"
        flags = web_flags + rule_flags
        explanation = RULES_EXPLANATION[verdict] if (rules or web_verdict) else NOT_SURE.format(family=family)
    else:
        verdict = stronger(stronger(ai["verdict"], rules), web_verdict)
        ai_flags = [without_links_or_numbers(flag) for flag in ai["red_flags"] if flag.strip()]
        flags = ai_flags or rule_flags
        explanation = without_links_or_numbers(ai["explanation"])
        # The rules or the web found more than the AI said, or the AI's words
        # slipped into advice: then its words don't fit, so fixed words are used.
        if verdict != ai["verdict"] or guard.check_reply(explanation) is not None:
            explanation = RULES_EXPLANATION.get(verdict, NOT_SURE.format(family=family))
            flags = flags if verdict == ai["verdict"] else rule_flags
        flags = web_flags + flags
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
        # What the web said about the number or address in it (fixed words
        # and the sites), or null when there was nothing to look up.
        "lookup": web,
    }

