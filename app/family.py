# app/family.py
# The family update (docs/SPEC.md feature 9): one day of her life in plain
# words for the family member she chose: her mood, her pills, what she put
# in her diary, new Memory book pages, and any safety screens.
#
# Written by plain code from the logs, not the AI, so it says only what
# happened and never judges it ("Mom seems worse"). It reuses the same
# facts as the Doctor notes (app/notes.py). She sends it herself: the
# screen's "Send" opens her own email app with it written (a mailto: link),
# so no email password is ever stored (docs/SAFETY.md section 9).

from datetime import date, datetime
from urllib.parse import quote

from app import db, notes, reminders

# Fixed words for each safety screen. A crisis is named, but never with her
# words or what matched (docs/SAFETY.md 7b: only the kind and the time).
SAFETY_WORDS = {
    "emergency": "Buddy showed the emergency screen (call 911). Please call her.",
    "poison_control": "Buddy showed the Poison Control screen.",
    "crisis": "Buddy showed her the 988 Suicide & Crisis Lifeline. Please call her today.",
}
FOOTER = "Grandma Buddy is an AI helper. It doesn't give medical advice."


def day_words(day: date) -> str:
    """ "Wednesday, October 28" """
    return f"{day:%A, %B} {day.day}"


def mood_line(connection, start: str, end: str) -> str:
    row = connection.execute(
        "SELECT mood, created_at FROM moods WHERE created_at >= ? AND created_at < ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (start, end),
    ).fetchone()
    if row is None:
        return "Mood: No check-in that day."  # "that day": the update can be yesterday's
    said_at = notes.time_words(datetime.fromisoformat(row["created_at"]))
    return f"Mood: {notes.MOOD_WORDS.get(row['mood'], row['mood'])} (at {said_at})"


# What the update calls a reminder she hasn't taken, by what it is now.
# Snoozed counts as due now: it is waiting for her answer.
NOT_TAKEN_WORDS = {"missed": "Missed", "due": "Due now", "snoozed": "Due now", "upcoming": "Still to come"}


def pills_line(connection, start: str, day_end: str) -> str:
    """How many of that day's reminders she took, out of all of them, so it
    says the same as the Pills screen ("2 of 3"). Then each one not taken,
    by name and time: missed, due now, or still to come."""
    if not reminders.active_pills(connection):
        return "Pills: No pills set up."
    now = reminders.current_time()
    # Today's later reminders are made when the app asks for them: make sure
    # they are there, so a pill still to come counts. (Not saved from here.)
    reminders.make_todays_reminders(connection, now)
    rows = connection.execute(
        "SELECT e.due_at, e.status, e.snooze_until, m.name FROM med_events e JOIN medications m ON m.id = e.medication_id "
        "WHERE m.active = 1 AND e.due_at >= ? AND e.due_at <= ? ORDER BY e.due_at, m.name COLLATE NOCASE",
        (start, day_end),
    ).fetchall()
    if not rows:
        return "Pills: No reminders that day."
    taken = 0
    not_taken: dict[str, list[str]] = {}
    for row in rows:
        state = reminders.status(dict(row), now)
        if state == "taken":
            taken += 1
        else:
            # The day is already in the update, so only the time: "Metformin at 6:00 PM".
            when = notes.time_words(datetime.fromisoformat(row["due_at"]))
            not_taken.setdefault(NOT_TAKEN_WORDS[state], []).append(f"{row['name']} at {when}")
    line = f"Pills: {taken} of {len(rows)} taken."
    for words in ("Missed", "Due now", "Still to come"):
        if words in not_taken:
            line += f" {words}: {', '.join(not_taken[words])}."
    return line


def diary_lines(connection, start: str, end: str) -> list[str]:
    entries = notes.symptoms(connection, start, end)
    if not entries:
        return ["Diary: Nothing new in her diary."]
    lines = [f"Diary: {len(entries)} new {'entry' if len(entries) == 1 else 'entries'}"]
    for entry in entries:
        words = f'"{entry["words"]}"' if entry["quoted"] else entry["words"]
        note = f" ({entry['note']})" if entry["note"] else ""
        lines.append(f"  - {entry['time']}: {words}{note}")
    return lines


def safety_lines(connection, start: str, end: str) -> list[str]:
    rows = connection.execute(
        "SELECT created_at, kind FROM safety_events WHERE created_at >= ? AND created_at < ? ORDER BY created_at, id",
        (start, end),
    ).fetchall()
    if not rows:
        return ["Safety screens: none that day."]
    return ["Safety screens:"] + [
        f"  - {notes.time_words(datetime.fromisoformat(row['created_at']))}: {SAFETY_WORDS.get(row['kind'], 'Buddy showed a safety screen.')}"
        for row in rows
    ]


def memory_lines(connection, start: str, end: str) -> list[str]:
    """New Memory book pages that day, by title (only on days with new pages)."""
    rows = connection.execute(
        "SELECT title FROM memories WHERE created_at >= ? AND created_at < ? ORDER BY id", (start, end)
    ).fetchall()
    if not rows:
        return []
    return [f"Memory book: {len(rows)} new {'page' if len(rows) == 1 else 'pages'}"] + [
        f'  - "{row["title"] or "A memory"}"' for row in rows
    ]


def mailto(to: str, subject: str, text: str) -> str:
    """An email link with the words written in: she sends it from her own
    email app. Every part URL-encoded; email apps expect line breaks as %0D%0A."""
    return (f"mailto:{quote(to.strip(), safe='@')}?subject={quote(subject, safe='')}"
            f"&body={quote(text.replace(chr(10), chr(13) + chr(10)), safe='')}")


def summary(connection, day: date) -> dict:
    """The update for one day: its words, and a mailto: link with them."""
    profile = db.get_profile(connection)
    her = profile["preferred_name"] or profile["name"]
    family_name = profile["family_name"].strip()
    start = day.isoformat() + "T00:00:00"
    end = day.isoformat() + "T23:59:59"
    lines = [
        f"Hi {family_name}," if family_name else "Hi,",
        "",
        f"Here is {her + chr(39) + 's' if her else 'her'} day, {day_words(day)}, from Grandma Buddy.",
        "",
        mood_line(connection, start, end),
        pills_line(connection, start, end),
        *diary_lines(connection, start, end),
        *memory_lines(connection, start, end),
        *safety_lines(connection, start, end),
        "",
        FOOTER,
    ]
    text = "\n".join(lines)
    subject = f"{her + chr(39) + 's' if her else 'Her'} day: {day_words(day)}"
    to = profile["family_email"].strip()
    return {"date": day.isoformat(), "subject": subject, "text": text, "mailto": mailto(to, subject, text), "to": to}
