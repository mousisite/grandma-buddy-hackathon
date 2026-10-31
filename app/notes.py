# app/notes.py
# Doctor notes (docs/SPEC.md feature 8): one page for her next visit.
#
# Every fact on the page comes straight from the logs, with plain code:
# her words (quoted exactly), where, pain, since, pills taken and missed,
# her mood each day, and her questions. Nothing is summed up or explained.
#
# Muse Spark's only job is grouping her diary entries into a few topics
# ("Left knee", "Headache"). It answers with a short label and entry ids,
# and the grouping is used only if every id is real, every entry is there
# exactly once, and every word of each label is a word she said. Otherwise
# (or when the AI is down) entries are grouped by where she said it hurts.
# So the AI never writes a sentence on the page (docs/SAFETY.md section 6).

import json
import re
from datetime import datetime, timedelta

from app import db, meta_client, prompts, reminders

DAY_CHOICES = (7, 14, 30)
MOOD_WORDS = {"great": "Great", "good": "Good", "okay": "Okay", "low": "Low", "very_low": "Very low"}
EMERGENCY_NOTE = "Buddy showed the emergency screen."
OTHER_THINGS = "Other things"
MAX_LABEL_WORDS = 3
# Small words a topic label may use even if she didn't say them.
JOINERS = {"and", "or", "the", "of", "in", "my", "a"}

TOPICS_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "entry_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["label", "entry_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["topics"],
    "additionalProperties": False,
}


# ---------- Dates in plain words ----------

def day_words(when: datetime) -> str:
    """ "Mon, Oct 26" """
    return f"{when:%a, %b} {when.day}"


def time_words(when: datetime) -> str:
    """ "9:15 AM" """
    return when.strftime("%I:%M %p").lstrip("0")


def period_words(start: datetime, end: datetime) -> str:
    """ "October 22 to 28", or "September 29 to October 28" across two months. """
    if start.month == end.month:
        return f"{start:%B} {start.day} to {end.day}"
    return f"{start:%B} {start.day} to {end:%B} {end.day}"


# ---------- The facts (plain code only) ----------

def gather(connection, days: int) -> dict:
    """Everything for the page from the last `days` days (today included),
    straight from the logs."""
    now = reminders.current_time()
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    since = start.isoformat(timespec="seconds")
    return {
        "period": period_words(start, now),
        "symptoms": symptoms(connection, since),
        "pills": pills(connection, since, now),
        "moods": moods(connection, since),
        # Her questions, in the order she added them: each still to ask, or
        # asked in these days (shown with a check, so she sees it's done).
        "questions": [
            {"id": row["id"], "question": row["question"], "asked": bool(row["resolved"])}
            for row in connection.execute(
                "SELECT id, question, resolved FROM doctor_questions WHERE resolved = 0 OR asked_at >= ? ORDER BY id",
                (since,),
            )
        ],
    }


def symptoms(connection, since: str, until: str = "9999") -> list[dict]:
    """Her diary entries from `since` up to `until` (not included), oldest
    first, exactly as written down. (Crisis events are never here: only
    emergencies are in her diary.)"""
    found = []
    for row in connection.execute(
        "SELECT id, created_at, description, body_area, pain_level, since, source FROM symptoms "
        "WHERE created_at >= ? AND created_at < ? ORDER BY created_at, id",
        (since, until),
    ):
        when = datetime.fromisoformat(row["created_at"])
        found.append({
            "id": row["id"],
            "at": row["created_at"],
            "date": day_words(when),
            "time": time_words(when),
            "words": row["description"],
            # "Emergency warning signs (…)" is written by Buddy, not her words.
            "quoted": not row["description"].startswith("Emergency warning signs ("),
            "where": row["body_area"],
            "pain": row["pain_level"],
            "since": row["since"],
            "note": EMERGENCY_NOTE if row["source"] == "safety_net" else "",
        })
    return found


def pills(connection, since: str, now: datetime) -> list[dict]:
    """Each pill exactly as labeled, with how many reminders were taken and
    which were missed (the same rules as the reminders: missed after 2
    hours with no answer), from `since` up to now. A reminder still
    waiting for her isn't counted."""
    found = []
    end = now.isoformat(timespec="seconds")
    for pill in reminders.active_pills(connection):
        taken, missed = 0, []
        for row in connection.execute(
            "SELECT due_at, status, snooze_until FROM med_events WHERE medication_id = ? AND due_at >= ? AND due_at <= ? "
            "ORDER BY due_at",
            (pill["id"], since, end),
        ):
            state = reminders.status(dict(row), now)
            if state == "taken":
                taken += 1
            elif state == "missed":
                due = datetime.fromisoformat(row["due_at"])
                missed.append(f"{day_words(due)}, {time_words(due)}")
        found.append({"name": pill["name"], "label": pill["label_dose"], "taken": taken,
                      "total": taken + len(missed), "missed": missed})
    return found


def moods(connection, since: str) -> list[dict]:
    """One mood per day: the last thing she said about how she feels."""
    by_day: dict[str, str] = {}
    for row in connection.execute("SELECT created_at, mood FROM moods WHERE created_at >= ? ORDER BY created_at, id", (since,)):
        by_day[day_words(datetime.fromisoformat(row["created_at"]))] = MOOD_WORDS.get(row["mood"], row["mood"])
    return [{"day": day, "mood": mood} for day, mood in by_day.items()]


# ---------- Grouping (the AI's only job), always checked ----------

def her_words(entries: list[dict]) -> set[str]:
    """Every word she said in these entries, and the places she gave."""
    text = " ".join(entry["words"] + " " + entry["where"] for entry in entries).lower()
    return set(re.findall(r"[a-z]+", text))


def label_is_hers(label: str, vocabulary: set[str]) -> bool:
    """True when every word of a topic label is one she said (a plural or
    singular of it counts), so the AI can't name a condition like "Arthritis"."""
    words = re.findall(r"[a-z]+", label.lower())
    # A topic is a few words ("Left knee"), never a sentence made of her words.
    return 0 < len(words) <= MAX_LABEL_WORDS and all(
        word in JOINERS or word in vocabulary or word.rstrip("s") in vocabulary or word + "s" in vocabulary
        for word in words
    )


def by_place(entries: list[dict]) -> list[dict]:
    """Group by where she said it hurts ("Left knee"); the rest under "Other things", last."""
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        place = entry["where"].strip()
        label = place[:1].upper() + place[1:] if place else OTHER_THINGS
        groups.setdefault(label, []).append(entry)
    ordered = sorted(groups.items(), key=lambda group: (group[0] == OTHER_THINGS, group[1][0]["at"]))
    return [{"label": label, "entries": grouped} for label, grouped in ordered]


def checked_topics(answer: dict, entries: list[dict]) -> list[dict] | None:
    """The AI's grouping, if it passes every check; otherwise None."""
    by_id = {entry["id"]: entry for entry in entries}
    vocabulary = her_words(entries)
    used: list[int] = []
    topics = []
    for topic in answer.get("topics") or []:
        label = str(topic.get("label", "")).strip()
        ids = topic.get("entry_ids")
        if not label or not isinstance(ids, list) or not ids or not label_is_hers(label, vocabulary):
            return None
        if any(entry_id not in by_id or entry_id in used for entry_id in ids):
            return None
        used += ids
        grouped = sorted((by_id[entry_id] for entry_id in ids), key=lambda entry: entry["at"])
        topics.append({"label": label[:1].upper() + label[1:], "entries": grouped})
    if sorted(used) != sorted(by_id):
        return None  # an entry was left out
    return sorted(topics, key=lambda topic: topic["entries"][0]["at"])


def group_symptoms(entries: list[dict]) -> list[dict]:
    """Her entries in a few topics: the AI's grouping if it checks out,
    otherwise by where she said it hurts."""
    if not entries:
        return []
    shown = [{"id": entry["id"], "her_words": entry["words"], "where": entry["where"]} for entry in entries]
    messages = [
        {"role": "developer", "content": prompts.NOTE_TOPICS},
        {"role": "user", "content": json.dumps(shown)},
    ]
    try:
        answer = meta_client.structured(messages, "symptom_topics", TOPICS_SCHEMA, reasoning="low")
    except meta_client.MetaError as problem:
        print(f"Grouping the doctor notes failed: {problem}")  # never her words
        return by_place(entries)
    return checked_topics(answer, entries) or by_place(entries)


# ---------- The whole page ----------

def notes(connection, days: int) -> dict:
    """The doctor notes page for the last `days` days."""
    facts = gather(connection, days)
    profile = db.get_profile(connection)
    return {
        "period": facts["period"],
        "her_name": profile["preferred_name"] or profile["name"],
        "doctor_name": profile["doctor_name"],
        "topics": group_symptoms(facts["symptoms"]),
        "pills": facts["pills"],
        "moods": facts["moods"],
        "questions": facts["questions"],
        "made_on": f"{reminders.current_time():%A, %B} {reminders.current_time().day}",
    }
