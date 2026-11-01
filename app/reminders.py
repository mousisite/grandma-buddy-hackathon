# app/reminders.py
# Pill reminders, worked out with plain Python (no AI).
#
# A family member enters each pill: its name, the label text exactly as on
# the bottle, and the times of day. Each time gets one reminder row per day
# (med_events). A reminder is:
#   upcoming  its time hasn't come yet
#   due       its time has come (or its snooze ended): the banner shows it
#   snoozed   she tapped "Remind me in 10 minutes"
#   taken     she tapped "I took it", or told Buddy (also after it was missed)
#   missed    2 hours went by without an answer
# Only her answers (taken, snoozed) are written down. Everything else follows
# from the clock, so nothing has to run in the background.
#
# The words she hears repeat the label exactly as the family typed it
# (docs/SAFETY.md section 5). The app never invents or changes dose
# information, and the AI is never given the label (see get_pills_due).

import json
import re
from datetime import datetime, time, timedelta

SNOOZE = timedelta(minutes=10)
MISSED_AFTER = timedelta(hours=2)
SOON = timedelta(hours=1)  # "I took it" a little early still counts

# Words that mean her pills in general, not one pill by name.
ALL_WORDS = {"all", "both", "them", "everything", "pill", "pills", "med", "meds", "medicine", "medicines",
             "medication", "medications", "tablet", "tablets"}


def current_time() -> datetime:
    """The local time. Tests replace this with a clock they set."""
    return datetime.now()


# ---------- The rules (pure: no database, easy to test) ----------

def todays_times(times: list[str], now: datetime, since: str = "") -> list[datetime]:
    """The reminder times for one pill today.

    A daily pill set up before today (`since`, when it was added) gets every
    time today: a dose she never marked shows as not taken, so her family
    can see it, and the ones still to come are upcoming. Just after
    midnight, last night's late pill (within the last 2 hours) is offered too.
    A pill added today only gets the times from then on: 8 AM for a pill
    added at noon gets no reminder, so it can never count as not taken."""
    earliest = now - MISSED_AFTER
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    set_up_before_today = bool(since) and datetime.fromisoformat(since) < start_of_today
    due_times = []
    for day in sorted({earliest.date(), now.date()}):
        for text in times:
            hour, minute = (int(part) for part in text.split(":"))
            due = datetime.combine(day, time(hour, minute))
            if due > earliest or (set_up_before_today and day == now.date()):
                due_times.append(due)
    return sorted(due_times)


def status(reminder: dict, now: datetime) -> str:
    """What a reminder is right now: upcoming, due, snoozed, taken, or missed."""
    if reminder["status"] == "taken":
        return "taken"
    due = datetime.fromisoformat(reminder["due_at"])
    if now < due:
        return "upcoming"
    snoozed_until = datetime.fromisoformat(reminder["snooze_until"]) if reminder["snooze_until"] else None
    # Missed after 2 hours with no answer since it was last shown to her.
    last_shown = max(due, snoozed_until) if snoozed_until else due
    if now >= last_shown + MISSED_AFTER:
        return "missed"
    if snoozed_until and now < snoozed_until:
        return "snoozed"
    return "due"


def snooze_until(now: datetime) -> datetime:
    return now + SNOOZE


def part_of_day(due: datetime) -> str:
    """Morning 5 AM to noon, afternoon to 5 PM, evening to 9 PM, then night."""
    if 5 <= due.hour < 12:
        return "morning"
    if 12 <= due.hour < 17:
        return "afternoon"
    return "evening" if 17 <= due.hour < 21 else "night"


def name_words(name: str) -> set[str]:
    """The words of a pill's name that she might say ("Vitamin D" -> {"vitamin"})."""
    return {word for word in re.findall(r"[a-z]+", name.lower()) if len(word) >= 3}


def pick_taken(found: list[dict], her_words: str, now: datetime) -> list[dict]:
    """Which of today's reminders to mark taken when she says she took her pills.

    - A pill she names ("my lisinopril", "my vitamins"), or every pill when
      she speaks in general ("all", "my pills", "both").
    - At most one reminder per pill: a due or snoozed one first. Only if
      nothing is due at all, one coming up within the hour (taken a bit early).
    - A missed reminder only when she names that pill and nothing else of it
      is open, so "I took my pills" at night can't hide a missed morning pill
      from her family.
    """
    said = set(re.findall(r"[a-z]+", her_words.lower()))
    by_pill: dict[str, list[dict]] = {}
    for reminder in found:
        by_pill.setdefault(reminder["name"], []).append(reminder)
    named = [name for name in by_pill if any(w in said or w + "s" in said for w in name_words(name))]
    in_general = not named and (not said or bool(said & ALL_WORDS))
    wanted = named or (list(by_pill) if in_general else [])
    soon = (now + SOON).isoformat(timespec="seconds")

    def open_now(reminder):
        return reminder["status"] in ("due", "snoozed")

    def coming_soon(reminder):
        return reminder["status"] == "upcoming" and reminder["due_at"] <= soon

    anything_due = any(open_now(r) for name in wanted for r in by_pill[name])
    chosen = []
    for name in wanted:
        reminders_of_pill = by_pill[name]
        pick = next((r for r in reminders_of_pill if open_now(r)), None)
        if pick is None and not anything_due:
            pick = next((r for r in reminders_of_pill if coming_soon(r)), None)
        if pick is None and named:
            missed = [r for r in reminders_of_pill if r["status"] == "missed"]
            if missed and not any(coming_soon(r) for r in reminders_of_pill):
                pick = missed[-1]
        if pick:
            chosen.append(pick)
    return chosen


def joined(names: list[str]) -> str:
    """ "Lisinopril and Metformin", or "Lisinopril, Metformin, and Vitamin D". """
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + ", and " + names[-1]


def reminder_title(due_pills: list[dict], her_name: str = "") -> str:
    """The first thing the reminder card says, with her name: "Rose, it's
    time for your evening Metformin." or, for several pills, "Rose, it's
    time for your morning pills: Lisinopril and Metformin." """
    when = part_of_day(datetime.fromisoformat(due_pills[0]["due_at"]))
    names = [pill["name"] for pill in due_pills]
    what = f"{when} {names[0]}" if len(names) == 1 else f"{when} pills: {joined(names)}"
    return f"{her_name + ', it’s' if her_name else 'It’s'} time for your {what}."


def reminder_words(due_pills: list[dict], her_name: str = "") -> str:
    """What Buddy reads aloud: the title, then each label exactly as the
    family typed it ("The label says: 500 mg tablet, take 1 by mouth…", or
    "Metformin: 500 mg tablet…" for several pills). Only a period is added
    at the very end of a label if needed. A pill with no label is named in
    the title, and nothing is made up for it."""
    words = reminder_title(due_pills, her_name)
    for pill in due_pills:
        label = pill["label_dose"]
        if label:
            start = "The label says: " if len(due_pills) == 1 else f"{pill['name']}: "
            words += " " + start + label + ("" if label[-1] in ".!?" else ".")
    return words


# ---------- The database ----------

def active_pills(connection) -> list[dict]:
    """Her pills (not removed), with their times as a list."""
    rows = connection.execute(
        "SELECT id, name, label_dose, times, created_at FROM medications WHERE active = 1 ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return [dict(row, times=json.loads(row["times"])) for row in rows]


def make_todays_reminders(connection, now: datetime) -> None:
    """Create today's reminder rows that don't exist yet. Safe to run every
    time: each pill gets one row per time per day (the med_events_once index).

    A pill never gets more reminders on one day than it has times, so moving
    a time later (8 AM to 9 AM after she took the 8 AM one) can't remind her
    again for a dose she already took. Later times are created first.
    """
    for pill in active_pills(connection):
        for due in reversed(todays_times(pill["times"], now, pill["created_at"])):
            on_that_day = connection.execute(
                "SELECT COUNT(*) FROM med_events WHERE medication_id = ? AND due_at LIKE ?",
                (pill["id"], due.date().isoformat() + "%"),
            ).fetchone()[0]
            if on_that_day < len(pill["times"]):
                connection.execute(
                    "INSERT OR IGNORE INTO med_events (medication_id, due_at) VALUES (?, ?)",
                    (pill["id"], due.isoformat(timespec="seconds")),
                )


def reminders_now(connection, now: datetime) -> list[dict]:
    """Today's reminders with what each is now, in time order. Yesterday's
    late ones that are still due (just after midnight) are included too."""
    make_todays_reminders(connection, now)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = connection.execute(
        "SELECT e.id, e.medication_id, e.due_at, e.status, e.snooze_until, e.acted_at, m.name, m.label_dose "
        "FROM med_events e JOIN medications m ON m.id = e.medication_id "
        "WHERE m.active = 1 AND e.due_at >= ? ORDER BY e.due_at, m.name COLLATE NOCASE",
        ((today - timedelta(days=1)).isoformat(timespec="seconds"),),
    ).fetchall()
    found = []
    for row in rows:
        reminder = dict(row)
        reminder["status"] = status(reminder, now)
        if reminder["due_at"] >= today.isoformat(timespec="seconds") or reminder["status"] in ("due", "snoozed"):
            found.append(reminder)
    return found


def mark_taken(connection, ids: list[int], now: datetime) -> None:
    connection.executemany(
        "UPDATE med_events SET status = 'taken', acted_at = ? WHERE id = ? AND status != 'taken'",
        [(now.isoformat(timespec="seconds"), i) for i in ids],
    )


def snooze(connection, ids: list[int], now: datetime) -> None:
    connection.executemany(
        "UPDATE med_events SET status = 'snoozed', snooze_until = ?, acted_at = ? WHERE id = ? AND status != 'taken'",
        [(snooze_until(now).isoformat(timespec="seconds"), now.isoformat(timespec="seconds"), i) for i in ids],
    )


def forget_waiting_reminders(connection, medication_id: int, now: datetime, keep_times: list[str] = ()) -> None:
    """When a pill is changed or removed: drop its reminders that are still
    waiting (upcoming, due, or snoozed), except those at a time of day it
    still has (so a label-only change keeps her snooze). Taken and missed
    ones always stay as a record."""
    rows = connection.execute(
        "SELECT id, due_at, status, snooze_until FROM med_events WHERE medication_id = ? AND status != 'taken'",
        (medication_id,),
    ).fetchall()
    waiting = [
        row["id"] for row in rows
        if status(dict(row), now) in ("upcoming", "due", "snoozed") and row["due_at"][11:16] not in keep_times
    ]
    connection.executemany("DELETE FROM med_events WHERE id = ?", [(i,) for i in waiting])
