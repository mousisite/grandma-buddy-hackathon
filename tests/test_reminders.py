# Tests for the pill reminder rules (app/reminders.py), with a clock the
# tests set. Made-up pills only.

from datetime import datetime

from app import reminders


def at(hour, minute=0, day=27):
    return datetime(2026, 10, day, hour, minute)


def event(due, status="due", snooze_until=""):
    return {"due_at": due.isoformat(timespec="seconds"), "status": status, "snooze_until": snooze_until}


# ---------- Which of today's times get a reminder ----------

def test_todays_times_include_later_times_and_ones_from_the_last_two_hours():
    assert reminders.todays_times(["20:00", "08:00"], at(9)) == [at(8), at(20)]


def test_a_pill_added_today_gets_no_reminder_for_a_time_that_already_passed():
    # A pill added at noon: no 8 AM reminder today, so it can never count as not taken.
    assert reminders.todays_times(["08:00", "20:00"], at(12)) == [at(20)]
    assert reminders.todays_times(["08:00", "20:00"], at(12), since=at(11, 30).isoformat()) == [at(20)]


def test_a_daily_pill_set_up_before_today_gets_every_time_today():
    # Her pills repeat every day: at noon, this morning's 8 AM dose is there
    # (not taken, unless she marks it), and tonight's is still to come.
    since = at(7, day=20).isoformat()
    assert reminders.todays_times(["08:00", "20:00"], at(12), since=since) == [at(8), at(20)]
    assert reminders.todays_times(["08:00", "20:00"], at(15), since=since) == [at(8), at(20)]
    # Just after midnight, last night's late pill is still offered too, with today's.
    assert reminders.todays_times(["23:30", "08:00"], at(0, 30, day=28), since=since) == [at(23, 30), at(8, day=28), at(23, 30, day=28)]


# ---------- What a reminder is right now ----------

def test_a_reminder_is_upcoming_then_due_then_missed_after_two_hours():
    reminder = event(at(8))
    assert reminders.status(reminder, at(7, 59)) == "upcoming"
    assert reminders.status(reminder, at(8)) == "due"
    assert reminders.status(reminder, at(9, 59)) == "due"
    assert reminders.status(reminder, at(10)) == "missed"


def test_a_snoozed_reminder_comes_back_after_ten_minutes():
    reminder = event(at(8), status="snoozed", snooze_until=at(8, 15).isoformat(timespec="seconds"))
    assert reminders.status(reminder, at(8, 10)) == "snoozed"
    assert reminders.status(reminder, at(8, 15)) == "due"
    # Missed 2 hours after it came back, not 2 hours after it was first due.
    assert reminders.status(reminder, at(10, 5)) == "due"
    assert reminders.status(reminder, at(10, 15)) == "missed"


def test_taken_stays_taken_even_after_its_time_has_passed():
    assert reminders.status(event(at(8), status="taken"), at(23)) == "taken"


def test_the_snooze_is_ten_minutes():
    assert reminders.snooze_until(at(8, 3)) == at(8, 13)


# ---------- What the banner says and Buddy reads aloud ----------

def pill(name, label, due):
    return {"name": name, "label_dose": label, "due_at": due.isoformat(timespec="seconds")}


def test_buddy_says_her_name_and_the_pill_then_repeats_the_label_exactly():
    due = [pill("Metformin", "500 mg tablet, take 1 by mouth twice daily with meals", at(18))]
    assert reminders.reminder_title(due, "Rose") == "Rose, it’s time for your evening Metformin."
    assert reminders.reminder_words(due, "Rose") == (
        "Rose, it’s time for your evening Metformin. "
        "The label says: 500 mg tablet, take 1 by mouth twice daily with meals.")


def test_several_pills_are_named_then_each_label_is_repeated_exactly():
    due = [
        pill("Lisinopril", "10 mg tablet. Take 1 daily.", at(8)),
        pill("Metformin", "500 mg tablet", at(8)),
        pill("Vitamin D", "", at(8)),
    ]
    assert reminders.reminder_title(due, "Rose") == (
        "Rose, it’s time for your morning pills: Lisinopril, Metformin, and Vitamin D.")
    # A label's own period is kept as it is; one is added only at its end if
    # needed. A pill with no label is named, with nothing made up for it.
    assert reminders.reminder_words(due, "Rose") == (
        "Rose, it’s time for your morning pills: Lisinopril, Metformin, and Vitamin D. "
        "Lisinopril: 10 mg tablet. Take 1 daily. Metformin: 500 mg tablet.")


def test_without_her_name_it_still_reads_well():
    due = [pill("Lisinopril", "", at(13)), pill("Vitamin D", "", at(13))]
    assert reminders.reminder_words(due, "") == "It’s time for your afternoon pills: Lisinopril and Vitamin D."


# ---------- Night, and last night's late pill ----------

def test_nine_pm_to_five_am_is_night():
    assert [reminders.part_of_day(at(h)) for h in (3, 5, 13, 17, 20, 21)] == [
        "night", "morning", "afternoon", "evening", "evening", "night"]


def test_last_nights_late_time_is_still_offered_just_after_midnight():
    assert reminders.todays_times(["23:30"], at(0, 15, day=28)) == [at(23, 30, day=27), at(23, 30, day=28)]


# ---------- Which reminders "I took my pills" marks ----------

def reminder(i, name, due, status):
    return {"id": i, "name": name, "due_at": due.isoformat(timespec="seconds"), "status": status}


def picked(found, words, now):
    return [r["id"] for r in reminders.pick_taken(found, words, now)]


def test_all_marks_only_what_is_due_not_a_pill_coming_later():
    found = [reminder(1, "Lisinopril", at(8), "due"), reminder(2, "Vitamin D", at(9), "upcoming")]
    assert picked(found, "all", at(8, 30)) == [1]


def test_with_nothing_due_a_pill_coming_within_the_hour_counts():
    found = [reminder(2, "Vitamin D", at(9), "upcoming"), reminder(3, "Fish oil", at(11), "upcoming")]
    assert picked(found, "my pills", at(8, 30)) == [2]


def test_one_reminder_per_pill_and_a_missed_one_stays_missed():
    # Twice a day: the 8 AM dose was missed, the 8 PM one is due.
    found = [reminder(1, "Lisinopril", at(8), "missed"), reminder(2, "Lisinopril", at(20), "due")]
    assert picked(found, "lisinopril", at(20, 30)) == [2]


def test_a_missed_pill_is_marked_only_when_she_names_it_and_nothing_else_is_open():
    found = [reminder(1, "Lisinopril", at(8), "missed"), reminder(2, "Lisinopril", at(20), "upcoming")]
    assert picked(found, "I took my lisinopril", at(11)) == [1]
    assert picked(found, "all", at(11)) == []


def test_pill_names_match_whole_words_and_general_words_mean_all():
    found = [reminder(1, "Vitamin D", at(8), "due"), reminder(2, "Lisinopril", at(8), "due")]
    assert picked(found, "my vitamin", at(8, 5)) == [1]
    assert picked(found, "my vitamins", at(8, 5)) == [1]  # a plural of the pill's name
    assert picked(found, "both", at(8, 5)) == [1, 2]
    assert picked(found, "aspirin", at(8, 5)) == []
