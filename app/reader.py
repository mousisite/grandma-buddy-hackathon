# app/reader.py
# "Read it to me": she takes a photo of a letter, a bill, or a form, and
# Buddy says what it is and what it says, in plain words.
#
# Muse Spark reads the photo into a strict form (what kind it is, who sent
# it, every word as printed, a short plain summary, an amount and a date).
# Plain code then decides what she hears (docs/SAFETY.md section 8d):
# - anything about her health (a doctor's letter, test results, a pill
#   label) is never explained: Buddy offers to read it word for word, and
#   says who is the right person to ask;
# - every sentence of the summary passes the advice guard, gives no advice
#   of its own ("you should pay it"), and has only numbers that are printed
#   on the paper;
# - phone numbers and links are never repeated in Buddy's own words (a
#   scammer's number could be one), long account numbers are hidden, and
#   the scam checker's plain rules run on the words: a likely scam is said
#   out loud, and its number and link are never read out, even word for word.
# Her photo is never saved.

import re

from app import briefing, guard, meta_client, prompts, scam

KINDS = ["bill", "letter", "medical", "pill_label", "advertisement", "form", "other", "unreadable"]
TITLES = {"bill": "A bill", "letter": "A letter", "medical": "A letter about your health", "pill_label": "A pill label",
          "advertisement": "An ad", "form": "A form", "other": "A paper", "unreadable": ""}
MAX_WORDS = 4000  # characters read word for word
MAX_SENTENCES = 3

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": KINDS},
        "from": {"type": "string"},
        "words": {"type": "string"},
        "summary": {"type": "string"},
        "amount": {"type": "string"},
        "due": {"type": "string"},
    },
    "required": ["kind", "from", "words", "summary", "amount", "due"],
    "additionalProperties": False,
}

# Buddy's own advice about what to do (never Buddy's job), not the paper's.
ADVICE = re.compile(
    r"\b(you should|you shouldn'?t|i (would )?(suggest|recommend|advise)|make sure|be sure to|don'?t forget"
    r"|it'?s (best|a good idea)|you'?d better)\b",
    re.IGNORECASE,
)
# A real bill prints its account number and its website. The scam checker
# counts both as red flags, so they are left out before its rules run here
# (a paper that asks for a password, a PIN, or a Social Security number
# still counts).
PRINTED_ON_BILLS = re.compile(
    r"\b(account|customer|member) (number|no\.?|#)|https?://\S+|\bwww\.\S+|\b[a-z0-9-]+\.(com|net|org)\b",
    re.IGNORECASE,
)
LONG_NUMBER = re.compile(r"\d{5,}")
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

COULDNT_READ = "I couldn’t read this one. Could you take another photo, a little closer, with good light?"


def hidden(text: str) -> str:
    """Long account numbers out of what she sees and hears, with the paper's
    lines kept (one printed line per line, spaces tidied)."""
    lines = (" ".join(line.split()) for line in text.splitlines())
    return LONG_NUMBER.sub("a long number", "\n".join(line for line in lines if line))


def printed(text: str, words: str) -> bool:
    """True when every number in the text is printed on the paper."""
    on_paper = words.replace(" ", "")
    return all(number in on_paper for number in NUMBER.findall(text))


def checked(summary: str, words: str) -> str:
    """The summary without advice, without numbers that aren't printed, at
    most 3 sentences, and with no phone number or link to call or tap."""
    kept = []
    for sentence in SENTENCE_END.split(" ".join(summary.split())):
        if sentence and not guard.check_reply(sentence) and not ADVICE.search(sentence) and printed(sentence, words):
            safe = scam.without_links_or_numbers(sentence)
            # A link at the end takes its period with it: give it back.
            kept.append(safe + "." if safe and safe[-1] not in ".!?" and sentence[-1] in ".!?" else safe)
    return " ".join(kept[:MAX_SENTENCES])


def calm(sender: str) -> str:
    """ "NATIONAL PRIZE CENTER" -> "National Prize Center": no shouting."""
    return sender.title() if sender.isupper() else sender


def health_words(profile: dict, sender: str) -> str:
    """What Buddy says about a paper about her health (or a pill label):
    never what it means, only that she can hear it word for word, and who
    to ask."""
    doctor = (profile.get("doctor_name") or "").strip() or "Your doctor"
    return (f"This looks like a letter about your health{' from ' + sender if sender else ''}. "
            f"I can read it to you word for word. If you have questions about it, {doctor} is the right person to ask.")


PILL_LABEL_WORDS = ("This looks like a pill label. I can read it to you word for word. "
                    "If you have a question about it, your pharmacist is the right person to ask.")


def read(image: str, profile: dict) -> dict:
    """Read the photo: {kind, title, summary, note, facts, words, spoken, scam}.
    summary is Spark's checked summary; note is Buddy's own fixed words
    instead (a health paper, a pill label, a photo it can't read); spoken is
    what Buddy says aloud. Raises meta_client.MetaError when Spark can't read it."""
    messages = [
        {"role": "developer", "content": prompts.READ},
        {"role": "user", "content": [
            {"type": "text", "text": "Here is a photo of the paper she wants read to her."},
            {"type": "image_url", "image_url": {"url": image}},
        ]},
    ]
    form = meta_client.structured(messages, "paper", SCHEMA, reasoning="low", max_tokens=4000)
    if form.get("kind") not in KINDS or not all(isinstance(form.get(field), str) for field in SCHEMA["required"]):
        raise meta_client.MetaError("the paper's form came back wrong")

    kind = form["kind"]
    words = hidden(form["words"])[:MAX_WORDS]
    sender = calm(hidden(" ".join(form["from"].split()))[:60])
    summary = checked(form["summary"], form["words"])
    # Anything about her health is handled as a medical letter.
    if kind in ("bill", "letter", "advertisement", "form", "other") and (
        briefing.HEALTH.search(summary) or briefing.HEALTH.search(sender)
    ):
        kind = "medical"

    if kind == "unreadable" or not words:
        return {"kind": "unreadable", "title": "", "summary": "", "note": COULDNT_READ, "facts": [], "words": "",
                "spoken": COULDNT_READ, "scam": None}
    title = TITLES[kind] + (f" from {sender}" if sender and kind != "pill_label" else "")
    # The scam checker's plain rules run on every paper but a pill label
    # (scammers pose as Medicare too). Only a likely scam is said out loud;
    # "Check it for a scam" is offered on the screen either way.
    paper = PRINTED_ON_BILLS.sub(" ", form["words"])
    verdict, flags = scam.rules_verdict(paper) if kind != "pill_label" else (None, [])
    signs = {"verdict": verdict, "flags": flags} if verdict == "likely_scam" else None
    warning = " It has signs of a scam." if signs else ""
    if signs:
        # Buddy's voice never reads out a scammer's phone number or link
        # (line by line, so the paper's lines are kept).
        words = "\n".join(scam.without_links_or_numbers(line) for line in words.splitlines())
    if kind in ("medical", "pill_label"):
        note = health_words(profile, sender) if kind == "medical" else PILL_LABEL_WORDS
        return {"kind": kind, "title": title, "summary": "", "note": note, "facts": [], "words": words,
                "spoken": note + warning, "scam": signs}

    # The amount and the date, only when printed; never a likely scam's
    # "fee", which would look like a real bill's amount due.
    facts = [{"label": label, "value": form[field].strip()}
             for label, field in (("Amount due", "amount"), ("Pay by", "due"))
             if form[field].strip() and printed(form[field], form["words"]) and not signs]
    return {
        "kind": kind,
        "title": title,
        "summary": summary,
        "note": "",
        "facts": facts,
        "words": words,
        "spoken": (summary or f"{title}.") + warning,
        "scam": signs,
    }
