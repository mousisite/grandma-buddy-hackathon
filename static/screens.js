// Grandma Buddy: the screens, the pill reminders, and toasts.
// Each time the router (app.js) shows a screen, it runs that screen's
// loader below, so the screen always shows fresh information.
// Checking a message and Doctor notes are designed, and arrive in the next
// steps.

"use strict";

var SCREEN_LOADERS = {
  today: function () {
    showCheckIn();
    showTodayDiary();
  },
  diary: showDiary,
  pills: showPillsScreen,
  notes: showNotes,
  family: showFamilyCalls,
  settings: fillSettingsForm,
};

// ---------- Pill reminders (on every screen) ----------

// Today's reminders from /api/reminders, checked every 30 seconds (app.js).
// One answer drives the banner, the "My pills" card on Today, and the
// Pills screen's list.
var pillState = { reminders: [], due_words: "", has_pills: false };
var shownReminders = ""; // which due reminders the banner was already brought into view for
var spokenReminders = ""; // which due reminders were already read aloud

var reminderRequests = 0; // so an older answer never replaces a newer one

function loadReminders() {
  var mine = ++reminderRequests;
  return api("/api/reminders")
    .then(function (state) {
      if (mine === reminderRequests) {
        showReminders(state);
      }
    })
    .catch(function () {
      // No connection to our own server: keep what is shown.
    });
}

// Change words on the page only when they are different, so screen readers
// aren't told the same thing again every 30 seconds.
function setText(element, text) {
  if (element.textContent !== text) {
    element.textContent = text;
  }
}

// Put keyboard focus on the heading of the screen she is on.
function focusScreenHeading() {
  document.querySelector('[data-screen="' + currentScreen() + '"] h1').focus({ preventScroll: true });
}

// A short note that slides in at the top and leaves by itself after 4
// seconds: a confirmation ("Saved to diary") with a check, or a problem
// without one. Screen readers announce it (#toasts is a polite live region).
var CHECK_ICON = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"></path></svg>';

function toast(text, problem) {
  var shelf = document.getElementById("toasts");
  var note = document.createElement("p");
  note.className = "toast";
  note.innerHTML = problem ? "" : CHECK_ICON;
  note.appendChild(document.createTextNode(text));
  shelf.appendChild(note);
  setTimeout(function () {
    note.classList.add("toast--leaving");
    setTimeout(function () { note.remove(); }, 300);
  }, 4000);
}

function showReminders(state) {
  pillState = state;
  showPillBanner();
  showPillsSummary();
  showTodaysPills();
}

function duePills() {
  return pillState.reminders.filter(function (r) { return r.status === "due"; });
}

// "8:00 AM" from "2026-10-27T08:00:00" (local time) or from "08:00".
function clockTime(text) {
  var time = new Date(text.length === 5 ? "2000-01-01T" + text : text);
  return time.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

// The banner: the label words exactly as the family typed them, "I took
// it", and "Remind me in 10 minutes". Read aloud once for each new set of
// due pills, but never while she is talking (the microphone would hear it),
// never over a safety message, and never cutting Buddy off mid-sentence
// (then it waits for the next check, 30 seconds later).
function showPillBanner() {
  var due = duePills();
  var banner = document.getElementById("pill-banner");
  var hadFocus = banner.contains(document.activeElement);
  banner.hidden = due.length === 0;
  if (!due.length) {
    shownReminders = "";
    spokenReminders = "";
    if (hadFocus) {
      focusScreenHeading(); // the button she tapped is gone
    }
    return;
  }
  var which = due.map(function (r) { return r.id; }).join(",");
  if (which !== shownReminders) {
    setText(document.getElementById("pill-banner-note"), ""); // an old note is about old pills
  }
  setText(document.getElementById("pill-banner-words"), pillState.due_words);
  setText(document.getElementById("pill-taken"), due.length > 1 ? "I took them" : "I took it");
  // After a Poison Control screen today: the fixed Poison Control message
  // with its call button, and the reminder is not read aloud.
  var poison = document.getElementById("pill-banner-poison");
  poison.hidden = !pillState.after_poison_control;
  setText(document.getElementById("pill-banner-poison-words"), pillState.poison_control_words || "");
  // A new reminder is brought into view once, unless she is talking or
  // someone is typing in a box. The banner is the first thing on the page,
  // so going to the top shows all of it (even while it is still easing in).
  var typing = document.activeElement && document.activeElement.matches("input, textarea, select");
  if (which !== shownReminders && talkState === "idle" && !typing) {
    shownReminders = which;
    window.scrollTo(0, 0);
  }
  // It counts as read only once the voice really starts (Chrome stays
  // silent until her first tap), so a blocked reminder is tried again.
  var quiet = talkState !== "idle" || safetySpeaking || isSpeaking() || pillState.after_poison_control;
  if (which !== spokenReminders && !quiet) {
    speak(pillState.due_words, { onStart: function () { spokenReminders = which; } });
  }
}

// "I took it" or "Remind me in 10 minutes", for every pill in the banner.
function answerReminder(answer) {
  var ids = duePills().map(function (r) { return r.id; });
  var buttons = document.querySelectorAll("#pill-banner button, #today-take");
  var note = document.getElementById("pill-banner-note");
  if (!ids.length) {
    return;
  }
  buttons.forEach(function (button) { button.disabled = true; });
  note.textContent = "";
  var mine = ++reminderRequests;
  api("/api/reminders/" + answer, "POST", { ids: ids })
    .then(function (state) {
      if (mine === reminderRequests) {
        showReminders(state);
      }
      var words = answer === "taken" ? "Thank you. I wrote that down." : "Okay. I’ll remind you again in 10 minutes.";
      if (answer === "taken") {
        toast("Marked as taken");
      }
      if (currentScreen() === "talk") {
        say(words);
      }
      if (talkState === "idle") {
        speak(words); // never into an open microphone
      }
    })
    .catch(function () {
      note.textContent = "I couldn’t save that just now. Please tap it again.";
    })
    .then(function () {
      buttons.forEach(function (button) { button.disabled = false; });
    });
}

// The pills row on Home: what's next, with "Take" when a pill is due.
function showPillsSummary() {
  var reminders = pillState.reminders;
  var snoozed = reminders.filter(function (r) { return r.status === "snoozed"; })[0];
  var next = reminders.filter(function (r) { return r.status === "upcoming"; })[0];
  var text = "No more pills today";
  if (!pillState.has_pills) {
    text = "No pills set up yet";
  } else if (duePills().length) {
    text = "Time for your pills now";
  } else if (snoozed) {
    text = "Pill reminder again at " + clockTime(snoozed.snooze_until);
  } else if (next) {
    // "Next: evening pills at 8:00 PM"
    text = "Next: " + partOfDay(new Date(next.due_at)) + " pills at " + clockTime(next.due_at);
  } else if (reminders.length && reminders.every(function (r) { return r.status === "taken"; })) {
    text = "All of today’s pills are taken";
  }
  setText(document.getElementById("pills-summary"), text);
  document.getElementById("today-take").hidden = duePills().length === 0;
}

// What each reminder is now, in plain words. Missed uses the fixed text
// from docs/SAFETY.md section 5.
var PILL_STATUS = {
  upcoming: function () { return "Later today"; },
  due: function () { return "Time to take it now"; },
  snoozed: function (r) { return "Reminding you again at " + clockTime(r.snooze_until); },
  taken: function (r) { return "Taken at " + clockTime(r.acted_at); }, // shown with a check icon
  missed: function () { return "Missed. Please check the label or call your pharmacist about what to do."; },
};

// Today's pills on the Pills screen: a "2 of 3 taken" ring, then one group
// for each part of the day, each pill a large row with a round check, its
// label word for word, and what it is now. Drawn again only when something
// changed, so the 30-second check never moves anything (or her focus).
var PILL_SLOTS = [["morning", "Morning"], ["afternoon", "Afternoon"], ["evening", "Evening"], ["night", "Night"]];
var shownPills = "";
var justTaken = null; // the pill she just checked: its check draws itself

function showTodaysPills() {
  var reminders = pillState.reminders;
  setText(document.getElementById("pills-day"),
    "Today, " + new Date().toLocaleDateString("en-US", { weekday: "long" }));
  showRing(reminders);
  var status = document.getElementById("pills-today-status");
  status.hidden = reminders.length > 0;
  setText(status, pillState.has_pills
    ? "No more pill reminders today."
    : "No pills set up yet. A family member can add them below.");
  var drawn = JSON.stringify(reminders);
  if (drawn === shownPills) {
    return;
  }
  shownPills = drawn;
  var schedule = document.getElementById("pills-today");
  schedule.textContent = "";
  var slots = {};
  reminders.forEach(function (reminder) {
    // Just after midnight, last night's late reminder can still be due: night.
    var part = lastNight(reminder) ? "night" : partOfDay(new Date(reminder.due_at));
    (slots[part] = slots[part] || []).push(reminder);
  });
  PILL_SLOTS.forEach(function (slot) {
    if (slots[slot[0]]) {
      schedule.appendChild(pillSlot(slot[1], slots[slot[0]]));
    }
  });
  justTaken = null;
}

function lastNight(reminder) {
  return new Date(reminder.due_at).toDateString() !== new Date().toDateString();
}

// The ring fills as pills are taken: "2 of 3".
function showRing(reminders) {
  var taken = reminders.filter(function (r) { return r.status === "taken"; }).length;
  var total = reminders.length;
  var ring = document.getElementById("pills-ring");
  ring.hidden = total === 0;
  ring.style.setProperty("--done", total ? Math.round((taken / total) * 100) : 0);
  setText(document.getElementById("pills-ring-count"), String(taken));
  setText(document.getElementById("pills-ring-total"), String(total));
  ring.setAttribute("aria-label", taken + " of " + total + " pills taken today");
}

function pillSlot(title, reminders) {
  var slot = document.createElement("section");
  slot.setAttribute("aria-label", title + " pills");
  addText(slot, "h2", "slot-title", title);
  var list = document.createElement("ol");
  list.className = "rows";
  list.setAttribute("role", "list");
  reminders.forEach(function (reminder) {
    list.appendChild(pillRow(reminder));
  });
  slot.appendChild(list);
  return slot;
}

// One pill. A pill to take now has a round check button ("I took this
// one"); a taken pill shows a filled check.
function pillRow(reminder) {
  var item = document.createElement("li");
  item.className = "check-row check-row--" + reminder.status + (reminder.id === justTaken ? " check-row--new" : "");
  var canTake = reminder.status === "due" || reminder.status === "snoozed";
  var check = document.createElement(canTake ? "button" : "span");
  check.className = "check";
  check.innerHTML = '<span class="check-circle">' + CHECK_ICON + "</span>";
  if (canTake) {
    check.type = "button";
    check.setAttribute("aria-label", "I took this one: " + reminder.name);
    check.addEventListener("click", function () {
      takeOnePill(reminder, check);
    });
  }
  item.appendChild(check);
  var text = document.createElement("div");
  text.className = "check-text";
  addText(text, "p", "check-time", (lastNight(reminder) ? "Last night, " : "") + clockTime(reminder.due_at));
  addText(text, "p", "pill-name", reminder.name);
  if (reminder.label_dose) {
    addText(text, "p", "pill-label", reminder.label_dose);
  }
  addText(text, "p", "pill-status", PILL_STATUS[reminder.status](reminder));
  item.appendChild(text);
  return item;
}

function takeOnePill(reminder, button) {
  button.disabled = true;
  var mine = ++reminderRequests;
  api("/api/reminders/taken", "POST", { ids: [reminder.id] })
    .then(function (state) {
      justTaken = reminder.id;
      if (mine === reminderRequests) {
        showReminders(state);
      }
      toast("Marked as taken");
      focusScreenHeading(); // the button she tapped is gone
    })
    .catch(function () {
      button.disabled = false;
      toast("I couldn’t save that. Please tap again.", true);
    });
}

// ---------- Setting up pills (for a family member) ----------

var MAX_TIMES = 6;
var editingPill = null; // the pill being changed, or null when adding one
var pillToRemove = null;

function showPillsScreen() {
  loadReminders();
  api("/api/meds")
    .then(showPillList)
    .catch(function () {
      document.getElementById("pills-undo").textContent = "I couldn’t open the pill list just now. Please try again in a moment.";
    });
}

// Each pill with its label and times, and buttons to change or remove it.
function showPillList(pills) {
  var list = document.getElementById("pills-list");
  list.textContent = "";
  pills.forEach(function (pill) {
    var item = document.createElement("li");
    item.className = "entry";
    addText(item, "p", "entry-words", pill.name);
    if (pill.label_dose) {
      addText(item, "p", "pill-label", pill.label_dose);
    }
    addText(item, "p", "entry-when", pill.times.map(clockTime).join(", "));
    var actions = document.createElement("div");
    actions.className = "form-actions";
    actions.append(
      smallButton("Change", "Change " + pill.name, function () { editPill(pill); }),
      smallButton("Remove", "Remove " + pill.name, function () { confirmRemove(pill); })
    );
    item.appendChild(actions);
    list.appendChild(item);
  });
}

function smallButton(text, label, onClick) {
  var button = document.createElement("button");
  button.type = "button";
  button.className = "pill-button pill-button--quiet pill-button--small";
  button.textContent = text;
  button.setAttribute("aria-label", label);
  button.addEventListener("click", onClick);
  return button;
}

// One more "time of day" box, up to 6.
function addTimeInput(value) {
  var times = document.getElementById("pill-times");
  var count = times.querySelectorAll(".time-input").length;
  if (count >= MAX_TIMES) {
    return null;
  }
  var input = document.createElement("input");
  input.type = "time";
  input.name = "time";
  input.className = "time-input";
  input.setAttribute("aria-label", "Time " + (count + 1));
  input.value = value || "";
  times.appendChild(input);
  document.getElementById("pill-add-time").hidden = count + 1 >= MAX_TIMES;
  return input;
}

// Back to "Add a pill" with empty boxes and one time.
function resetPillForm() {
  var form = document.getElementById("pill-form");
  editingPill = null;
  form.reset();
  clearProblem(form);
  form.querySelectorAll(".time-input").forEach(function (input, index) {
    if (index > 0) {
      input.remove();
    }
  });
  document.getElementById("pill-add-time").hidden = false;
  document.getElementById("pill-form-title").textContent = "Add a pill";
  document.getElementById("pill-cancel").hidden = true;
}

// "Change": the pill's details go into the form.
function editPill(pill) {
  var form = document.getElementById("pill-form");
  resetPillForm();
  editingPill = pill;
  form.elements.name.value = pill.name;
  form.elements.label_dose.value = pill.label_dose;
  pill.times.forEach(function (time, index) {
    if (index === 0) {
      form.querySelector(".time-input").value = time;
    } else {
      addTimeInput(time);
    }
  });
  document.getElementById("pill-form-title").textContent = "Change " + pill.name;
  document.getElementById("pill-cancel").hidden = false;
  document.getElementById("pill-status").textContent = "";
  form.scrollIntoView({ block: "start" });
  form.elements.name.focus({ preventScroll: true });
}

// Save the form. The server checks every entry and names the one to fix.
function savePill(event) {
  event.preventDefault();
  var form = event.target;
  var status = document.getElementById("pill-status");
  var times = [];
  var unfinished = null; // a time box with only the hour typed in
  form.querySelectorAll(".time-input").forEach(function (input) {
    if (input.value) {
      times.push(input.value);
    } else if (input.validity.badInput && !unfinished) {
      unfinished = input;
    }
  });
  clearProblem(form);
  if (unfinished) {
    // Never drop a half-typed time: that dose would get no reminder.
    showProblem(unfinished, "Please finish this time, or clear it.");
    status.textContent = "Please finish this time, or clear it.";
    return;
  }
  var pill = { name: form.elements.name.value, label_dose: form.elements.label_dose.value, times: times };
  var changing = editingPill;
  status.textContent = "Saving…";
  var saving = changing ? api("/api/meds/" + changing.id, "PUT", pill) : api("/api/meds", "POST", pill);
  saving
    .then(function (saved) {
      resetPillForm();
      status.textContent = (changing ? "Saved the changes to " : "Added ") + saved.name + ".";
      showPillsScreen();
    })
    .catch(function (problem) {
      var detail = problem.detail || {};
      var input = detail.field === "times" ? form.querySelector(".time-input") : form.elements[detail.field];
      if (input) {
        showProblem(input, detail.message);
        status.textContent = detail.message;
      } else if (typeof problem.detail === "string") {
        status.textContent = problem.detail; // like "That pill isn't there anymore."
      } else {
        status.textContent = "I couldn’t save that just now. Please try again.";
      }
    });
}

// "Are you sure?" first. Keep it is where the cursor starts.
function confirmRemove(pill) {
  pillToRemove = pill;
  document.getElementById("confirm-text").textContent =
    "Buddy will stop reminding her about " + pill.name + ". You can undo this.";
  document.getElementById("confirm-dialog").showModal();
}

function removePill() {
  var pill = pillToRemove;
  document.getElementById("confirm-dialog").close();
  api("/api/meds/" + pill.id, "DELETE")
    .then(function () {
      if (editingPill && editingPill.id === pill.id) {
        resetPillForm();
      }
      showUndo(pill);
      showPillsScreen();
    })
    .catch(function () {
      document.getElementById("pills-undo").textContent = "I couldn’t remove that just now. Please try again.";
    });
}

// "Removed Lisinopril. Undo" (it stays until something else happens).
function showUndo(pill) {
  var line = document.getElementById("pills-undo");
  line.textContent = "Removed " + pill.name + ". ";
  var undo = smallButton("Undo", "Undo: bring back " + pill.name, function () {
    api("/api/meds/" + pill.id + "/restore", "POST")
      .then(function () {
        line.textContent = pill.name + " is back.";
        focusScreenHeading(); // the Undo button she tapped is gone
        showPillsScreen();
      })
      .catch(function () {
        line.textContent = "I couldn’t bring it back just now. Please try again.";
      });
  });
  line.appendChild(undo);
  undo.focus();
}

// ---------- My diary ----------

// A short line under an entry that didn't come from a "Something hurts" talk.
var DIARY_SOURCES = {
  safety_net: "Buddy showed the emergency screen.",
  check_in: "From the daily check-in.",
};

// Her entries from the last 30 days, newest first, on a timeline with a
// heading per day. A soft shimmer shows while they load.
function showDiary() {
  var list = document.getElementById("diary-list");
  var status = document.getElementById("diary-status");
  if (!list.children.length) {
    list.setAttribute("aria-busy", "true");
  }
  api("/api/diary?days=30")
    .then(function (entries) {
      list.removeAttribute("aria-busy");
      list.textContent = "";
      status.hidden = entries.length > 0;
      status.textContent =
        "Nothing written down in the last 30 days. When something hurts, tap “Something hurts” and tell Buddy.";
      var shownDay = "";
      var dayList = null;
      entries.forEach(function (entry) {
        var when = new Date(entry.created_at); // local time, like "2026-10-27T14:15:00"
        var day = dayName(when);
        if (day !== shownDay) {
          shownDay = day;
          var section = document.createElement("section");
          section.className = "diary-day";
          var heading = document.createElement("h2");
          heading.className = "day-heading";
          heading.textContent = day;
          dayList = document.createElement("ol");
          dayList.className = "entries";
          dayList.setAttribute("role", "list"); // stays a list for screen readers without bullets
          section.append(heading, dayList);
          list.appendChild(section);
        }
        dayList.appendChild(diaryEntry(entry, when));
      });
    })
    .catch(function () {
      list.removeAttribute("aria-busy");
      status.hidden = false;
      status.textContent = "I couldn’t open your diary just now. Please try again in a moment.";
    });
}

// ---------- The daily check-in on Home ----------

var MOOD_WORDS = { great: "Feeling great", good: "Feeling good", okay: "Feeling okay", low: "Feeling low", very_low: "Feeling very low" };

// The card on her first visit each day, and the check-in row in the Today
// list: her mood once she told Buddy how she feels.
function showCheckIn() {
  api("/api/check-in")
    .then(function (today) {
      document.getElementById("check-in-card").hidden = !today.due;
      var words = "Not done yet";
      if (today.mood) {
        words = (MOOD_WORDS[today.mood.mood] || "Checked in") + ", at " +
          new Date(today.mood.at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
      } else if (!today.due) {
        words = "Done for today";
      }
      setText(document.getElementById("today-check-in"), words);
    })
    .catch(function () {
      // No connection to our own server: keep what is shown.
    });
}

// "Not today": the card goes away until tomorrow.
function skipCheckIn() {
  api("/api/check-in/skip", "POST")
    .then(function () {
      document.getElementById("check-in-card").hidden = true;
      setText(document.getElementById("today-check-in"), "Done for today");
      focusScreenHeading(); // the button she tapped is gone
      toast("Okay, maybe tomorrow");
    })
    .catch(function () {
      toast("I couldn’t save that just now. Please try again.", true);
    });
}

// Home's diary row: the latest thing she noted today, in her words.
function showTodayDiary() {
  api("/api/diary?days=1")
    .then(function (entries) {
      var today = entries.filter(function (entry) {
        return new Date(entry.created_at).toDateString() === new Date().toDateString();
      })[0];
      setText(document.getElementById("today-diary"), today ? "“" + today.description + "”" : "Nothing noted today");
      setText(document.getElementById("today-diary-when"), today
        ? "Noted at " + new Date(today.created_at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
        : "");
    })
    .catch(function () {
      // No connection to our own server: keep what is shown.
    });
}

// "Today", "Yesterday", or a date like "Monday, October 26".
function dayName(date) {
  var yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  if (date.toDateString() === new Date().toDateString()) {
    return "Today";
  }
  if (date.toDateString() === yesterday.toDateString()) {
    return "Yesterday";
  }
  return date.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

// One entry: the time, her own words, and where, how bad, and since when
// (only the ones she said). Always textContent: her words are never HTML.
function diaryEntry(entry, when) {
  var item = document.createElement("li");
  item.className = "entry";
  addText(item, "p", "entry-when", when.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }));
  // Her words in quotes. "Emergency warning signs (…)" is written by Buddy
  // instead of her words when crisis words were involved, so it isn't quoted.
  var herWords = !/^Emergency warning signs \(/.test(entry.description);
  addText(item, "p", "entry-words", herWords ? "“" + entry.description + "”" : entry.description);
  // Where it hurts, as a tag.
  if (entry.body_area) {
    var tags = document.createElement("p");
    tags.className = "tags";
    addText(tags, "span", "tag", entry.body_area);
    item.appendChild(tags);
  }
  var facts = [
    ["Pain:", entry.pain_level === null ? "" : entry.pain_level + " out of 10"],
    ["Since:", entry.since],
  ].filter(function (fact) { return fact[1]; });
  if (facts.length) {
    var list = document.createElement("dl");
    list.className = "entry-facts";
    facts.forEach(function (fact) {
      var pair = document.createElement("div");
      addText(pair, "dt", "", fact[0]);
      addText(pair, "dd", "", fact[1]);
      list.appendChild(pair);
    });
    item.appendChild(list);
  }
  if (DIARY_SOURCES[entry.source]) {
    addText(item, "p", "entry-note", DIARY_SOURCES[entry.source]);
  }
  return item;
}

function addText(parent, tag, className, text) {
  var element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  parent.appendChild(element);
}

// ---------- Doctor notes ----------

var notesRequests = 0; // so an older page never replaces a newer one

function notesDays() {
  return document.querySelector('input[name="notes-days"]:checked').value;
}

// Ask for the page (the server puts it together from her logs) and draw it.
function showNotes() {
  var doc = document.getElementById("notes-doc");
  var status = document.getElementById("notes-status");
  var mine = ++notesRequests;
  doc.setAttribute("aria-busy", "true");
  api("/api/doctor-notes?days=" + notesDays())
    .then(function (page) {
      if (mine === notesRequests) {
        status.hidden = true;
        drawNotes(page);
      }
    })
    .catch(function () {
      status.hidden = false;
      status.textContent = "I couldn’t put your notes together just now. Please try again in a moment.";
    })
    .then(function () {
      doc.removeAttribute("aria-busy");
    });
}

// A small helper: an element with a class and words (always as text,
// never as HTML, because her words are never code).
function element(tag, className, text) {
  var made = document.createElement(tag);
  made.className = className;
  if (text !== undefined) {
    made.textContent = text;
  }
  return made;
}

function docSection(title) {
  var section = element("section", "doc-section");
  section.appendChild(element("h3", "doc-heading", title));
  return section;
}

// The page, in the order a doctor reads it: her questions, how she has been
// feeling (her words, grouped by topic), her pills, her mood.
function drawNotes(page) {
  var doc = document.getElementById("notes-doc");
  var doctor = page.doctor_name || "your doctor";
  doc.textContent = "";
  document.getElementById("question-label").textContent = "Add a question for " + doctor;

  var head = element("header", "doc-head");
  var title = element("h2", "doc-title", "Notes for " + doctor);
  title.id = "notes-doc-title";
  head.appendChild(title);
  head.appendChild(element("p", "doc-meta", (page.her_name ? page.her_name + ", " : "") + page.period));
  doc.appendChild(head);

  var questions = docSection("Questions to ask");
  if (page.questions.length) {
    var list = element("ol", "doc-questions");
    page.questions.forEach(function (question) {
      var item = element("li", "");
      item.appendChild(element("span", "doc-question", question.question));
      item.appendChild(smallButton("Asked", "Asked: " + question.question, function () {
        markAsked(question);
      }));
      list.appendChild(item);
    });
    questions.appendChild(list);
  } else {
    questions.appendChild(element("p", "empty", "No questions yet. Add one below, or tell Buddy “I want to ask my doctor about…”."));
  }
  doc.appendChild(questions);

  var feeling = docSection("How I’ve been feeling");
  if (!page.topics.length) {
    feeling.appendChild(element("p", "empty", "Nothing written down in these days. When something hurts, tell Buddy."));
  }
  page.topics.forEach(function (topic) {
    feeling.appendChild(element("h4", "doc-topic", topic.label));
    var entries = element("ul", "doc-entries");
    entries.setAttribute("role", "list");
    topic.entries.forEach(function (entry) {
      var item = element("li", "");
      item.appendChild(element("span", "doc-date", entry.date + ", " + entry.time));
      item.appendChild(element("span", "doc-words", entry.quoted ? "“" + entry.words + "”" : entry.words));
      var facts = [];
      if (entry.pain !== null) {
        facts.push("Pain " + entry.pain + " of 10");
      }
      if (entry.since) {
        // Her words: "since lunch" stays as she said it; "yesterday" gets "Since".
        facts.push(/^since\s/i.test(entry.since)
          ? entry.since.charAt(0).toUpperCase() + entry.since.slice(1)
          : "Since " + entry.since);
      }
      if (entry.note) {
        facts.push(entry.note);
      }
      if (facts.length) {
        item.appendChild(element("span", "doc-facts", facts.join(". ")));
      }
      entries.appendChild(item);
    });
    feeling.appendChild(entries);
  });
  doc.appendChild(feeling);

  var pills = docSection("My pills");
  if (!page.pills.length) {
    pills.appendChild(element("p", "empty", "No pills set up."));
  }
  page.pills.forEach(function (pill) {
    var item = element("div", "doc-pill");
    item.appendChild(element("p", "doc-pill-name", pill.name));
    if (pill.label) {
      item.appendChild(element("p", "doc-pill-label", pill.label));
    }
    item.appendChild(element("p", "doc-count", pill.total ? "Taken " + pill.taken + " of " + pill.total : "No reminders in these days"));
    if (pill.missed.length) {
      var missed = element("p", "doc-missed");
      missed.innerHTML = VERDICT_ICONS.suspicious; // circle-alert: words and an icon, never color alone
      missed.appendChild(document.createTextNode("Missed: " + pill.missed.join("; ")));
      item.appendChild(missed);
    }
    pills.appendChild(item);
  });
  doc.appendChild(pills);

  var mood = docSection("My mood");
  if (page.moods.length) {
    var moods = element("ul", "doc-moods");
    moods.setAttribute("role", "list");
    page.moods.forEach(function (day) {
      moods.appendChild(element("li", "", day.day + ": " + day.mood));
    });
    mood.appendChild(moods);
  } else {
    mood.appendChild(element("p", "empty", "No check-ins in these days."));
  }
  doc.appendChild(mood);

  doc.appendChild(element("p", "doc-footer",
    "Written down by Grandma Buddy, an AI helper, from what " + (page.her_name || "she") +
    " told it. It is not medical advice. Made on " + page.made_on + "."));
}

// "Asked": the question leaves the page (it is kept, never deleted), with Undo.
function markAsked(question) {
  var line = document.getElementById("notes-undo");
  api("/api/doctor-questions/" + question.id + "/asked", "POST")
    .then(function () {
      line.textContent = "Marked “" + question.question + "” as asked. ";
      var undo = smallButton("Undo", "Undo: put back “" + question.question + "”", function () {
        api("/api/doctor-questions/" + question.id + "/reopen", "POST")
          .then(function () {
            line.textContent = "";
            focusScreenHeading(); // the Undo button she tapped is gone
            showNotes();
          })
          .catch(function () {
            line.textContent = "I couldn’t put it back just now. Please try again.";
          });
      });
      line.appendChild(undo);
      undo.focus();
      showNotes();
    })
    .catch(function () {
      toast("I couldn’t save that just now. Please try again.", true);
    });
}

// "Add a question": straight onto the page.
function addQuestion(event) {
  event.preventDefault();
  var box = document.getElementById("question-text");
  clearProblem(event.target);
  if (!box.value.trim()) {
    showProblem(box, "Please type the question first.");
    return;
  }
  api("/api/doctor-questions", "POST", { question: box.value })
    .then(function () {
      box.value = "";
      toast("Added to doctor notes");
      showNotes();
    })
    .catch(function () {
      showProblem(box, "I couldn’t add that just now. Please try again.");
    });
}

// ---------- Check a message ----------

// Words and an icon for each verdict (Lucide octagon-x, circle-alert,
// circle-check): never color alone.
var VERDICT_ICONS = {
  likely_scam: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m15 9-6 6"></path><path d="M2.586 16.726A2 2 0 0 1 2 15.312V8.688a2 2 0 0 1 .586-1.414l4.688-4.688A2 2 0 0 1 8.688 2h6.624a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 1-.586 1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586z"></path><path d="m9 9 6 6"></path></svg>',
  suspicious: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><line x1="12" x2="12" y1="8" y2="12"></line><line x1="12" x2="12.01" y1="16" y2="16"></line></svg>',
  looks_safe: '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><path d="m16 9-5.5 5.5L8 12"></path></svg>',
};
var SCAM_READ_LIMIT_MS = 2 * 60 * 1000; // reading out loud stops by itself after 2 minutes
var scamSpoken = ""; // the verdict, for "Say it again"
var scamRecording = false;
var scamTimer = null;

function scamStatus(text) {
  setText(document.getElementById("scam-status"), text);
}

// Send the message (words, or a photo as a data URL) to /api/scam-check,
// with a shimmer while Buddy reads it.
function checkMessage(kind, photo) {
  var text = document.getElementById("scam-text").value.trim();
  if (!text && !photo) {
    scamStatus("Please paste the message, read it out loud, or take a photo of it.");
    document.getElementById("scam-text").focus();
    return;
  }
  var buttons = document.querySelectorAll("#scam-compose button");
  buttons.forEach(function (button) { button.disabled = true; });
  document.getElementById("scam-reading").hidden = false;
  scamStatus("Buddy is reading it…");
  api("/api/scam-check", "POST", photo ? { image: photo, kind: "photo" } : { text: text, kind: kind })
    .then(function (result) {
      scamStatus("");
      showVerdict(result, photo);
    })
    .catch(function (problem) {
      scamStatus(typeof problem.detail === "string" ? problem.detail
        : "I couldn’t check that just now. Please try again in a moment, or call your family about it.");
    })
    .then(function () {
      document.getElementById("scam-reading").hidden = true;
      buttons.forEach(function (button) { button.disabled = false; });
    });
}

// The verdict card: read aloud, with focus on the verdict so a screen
// reader starts there too.
function showVerdict(result, photo) {
  var verdict = document.getElementById("scam-verdict");
  verdict.className = "verdict-pill verdict-pill--" + result.verdict;
  verdict.innerHTML = VERDICT_ICONS[result.verdict] || "";
  verdict.appendChild(document.createTextNode(result.title));
  setText(document.getElementById("scam-explanation"), result.explanation);
  fillList("scam-flags", result.red_flags);
  document.getElementById("scam-flags-block").hidden = result.red_flags.length === 0;
  fillList("scam-todo", result.what_to_do);
  fillList("scam-paid-list", result.if_you_paid);
  document.getElementById("scam-paid").hidden = result.if_you_paid.length === 0;
  var actions = document.getElementById("scam-actions");
  actions.textContent = "";
  result.actions.forEach(function (action) {
    if (isCallLink(action.href)) {
      actions.appendChild(callLink(action, "call-pill"));
    }
  });
  actions.hidden = actions.children.length === 0;
  var slot = document.getElementById("scam-checked-photo");
  slot.textContent = "";
  if (photo) {
    var picture = document.createElement("img");
    picture.className = "verdict-photo";
    picture.alt = "The photo you checked";
    picture.src = photo;
    slot.appendChild(picture);
  }
  slot.hidden = !photo;
  document.getElementById("scam-compose").hidden = true;
  document.getElementById("scam-result").hidden = false;
  verdict.focus();
  scamSpoken = result.title + ". " + result.explanation;
  speak(scamSpoken);
}

// Her words and Buddy's are always set as text, never as HTML.
function fillList(id, lines) {
  var list = document.getElementById(id);
  list.textContent = "";
  lines.forEach(function (line) {
    addText(list, "li", "", line);
  });
}

// "Check another message": back to an empty box.
function checkAnother() {
  stopSpeaking();
  document.getElementById("scam-result").hidden = true;
  document.getElementById("scam-compose").hidden = false;
  var box = document.getElementById("scam-text");
  box.value = "";
  scamStatus("");
  box.focus();
}

// "Read it out loud": tap, read the message, tap "I’m done reading". Her
// voice is written down (/api/transcribe, as in voice mode), then checked.
function readMessageAloud() {
  var label = document.getElementById("scam-read-label");
  if (!scamRecording) {
    stopSpeaking(); // the microphone must never hear Buddy
    startRecording()
      .then(function () {
        scamRecording = true;
        label.textContent = "I’m done reading";
        scamStatus("I’m listening. Read the message out loud, then tap “I’m done reading”.");
        scamTimer = setTimeout(readMessageAloud, SCAM_READ_LIMIT_MS);
      })
      .catch(function () {
        scamStatus("I can’t hear you yet. At the top of the window, click the microphone or lock picture, choose Allow, then try again. Or paste the message.");
      });
    return;
  }
  clearTimeout(scamTimer);
  scamRecording = false;
  label.textContent = "Read it out loud";
  scamStatus("Writing it down…");
  stopRecording()
    .then(sendForTranscript)
    .then(function (result) {
      if (!result.transcript) {
        throw problem("NotHeard");
      }
      document.getElementById("scam-text").value = result.transcript;
      checkMessage("voice");
    })
    .catch(function () {
      scamStatus("I didn’t catch that. Please try again, or paste the message.");
    });
}

// "Use a photo": the picture is shrunk on this device (about 1600 pixels
// on its long side, JPEG) and checked right away.
function choosePhoto(event) {
  var file = event.target.files[0];
  event.target.value = ""; // so the same photo can be chosen again
  if (!file) {
    return;
  }
  shrinkPhoto(file)
    .then(function (photo) {
      checkMessage("photo", photo);
    })
    .catch(function () {
      scamStatus("That picture didn’t work. Please try another photo.");
    });
}

function shrinkPhoto(file) {
  return new Promise(function (resolve, reject) {
    var image = new Image();
    image.onload = function () {
      var scale = Math.min(1, 1600 / Math.max(image.width, image.height));
      var canvas = document.createElement("canvas");
      canvas.width = Math.round(image.width * scale);
      canvas.height = Math.round(image.height * scale);
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(image.src);
      resolve(canvas.toDataURL("image/jpeg", 0.85));
    };
    image.onerror = reject;
    image.src = URL.createObjectURL(file);
  });
}

// ---------- Family and settings ----------

// The text entries on the form, named like the profile fields.
var PROFILE_TEXT_FIELDS = ["name", "preferred_name", "family_name", "family_phone", "family_email", "doctor_name", "doctor_phone"];
var VOICE_RATES = ["0.75", "0.9", "1.1"]; // Slower, Normal, Faster

// Big call buttons for the family member and the doctor, when their
// numbers are set up.
function showFamilyCalls() {
  var row = document.getElementById("family-calls");
  row.textContent = "";
  var people = [
    { name: profile.family_name || "family", phone: profile.family_phone },
    { name: profile.doctor_name || "the doctor", phone: profile.doctor_phone },
  ];
  people.forEach(function (person) {
    var href = "tel:" + person.phone;
    if (person.phone && isCallLink(href)) {
      row.appendChild(callLink({ label: "Call " + person.name, href: href }, "call-pill"));
    }
  });
  row.hidden = row.children.length === 0;
  document.getElementById("family-calls-empty").hidden = row.children.length > 0;
}

// Put the saved profile into the form. Profile entries that aren't saved
// yet stay as typed, so nothing is lost by going to another screen.
function fillSettingsForm() {
  var form = document.getElementById("settings-form");
  if (!form.hasAttribute("data-unsaved")) {
    PROFILE_TEXT_FIELDS.forEach(function (field) {
      form.elements[field].value = profile[field] || "";
    });
    clearProblem(form);
    document.getElementById("settings-status").textContent = "";
  }
  form.elements.theme.value = themeChoice();
  form.elements.text_size.value = String(wordStep());
  form.elements.voice_on.checked = profile.voice_on !== false;
  form.elements.calm_mode.checked = profile.calm_mode === true;
  form.elements.chime.checked = profile.chime === true;
  // The closest of Slower, Normal, Faster to the saved speed.
  var rate = Number(profile.voice_rate) || 0.9;
  var closest = VOICE_RATES.reduce(function (best, option) {
    return Math.abs(option - rate) < Math.abs(best - rate) ? option : best;
  });
  form.elements.voice_rate.value = closest;
}

function clearProblem(form) {
  form.querySelectorAll("[aria-invalid]").forEach(function (input) {
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
  });
  form.querySelectorAll(".field-problem").forEach(function (note) {
    note.remove();
  });
}

// Mark the entry the server sent back, say why right under it, and put
// the cursor there. (Used by the Family form and the pill form.)
function showProblem(input, message) {
  var note = document.createElement("p");
  note.id = input.form.id + "-problem";
  note.className = "field-problem";
  note.textContent = message;
  input.insertAdjacentElement("afterend", note);
  input.setAttribute("aria-invalid", "true");
  input.setAttribute("aria-describedby", note.id);
  input.focus();
}

// Switches and choices save the moment she changes them. The theme and
// text size change on screen at once; text size is kept on this device.
function saveChoice(event) {
  var input = event.target;
  var field = input.name;
  if (PROFILE_TEXT_FIELDS.indexOf(field) !== -1) {
    return; // profile entries wait for "Save profile"
  }
  if (field === "text_size") {
    setWords(Number(input.value));
    toast("Text size changed");
    return;
  }
  var change = {};
  change[field] = input.type === "checkbox" ? input.checked
    : field === "voice_rate" ? Number(input.value) : input.value;
  if (field === "theme") {
    changeScreen(function () {
      profile.theme = input.value;
      applyTheme();
    });
  }
  api("/api/profile", "PUT", change)
    .then(function (saved) {
      useProfile(saved);
      toast("Settings saved");
    })
    .catch(function () {
      fillSettingsForm(); // back to what is really saved
      document.getElementById("settings-status").textContent = "I couldn’t save that just now. Please try again.";
    });
}

// "Save profile": the names and numbers. The server checks every entry; if
// one needs another look, that entry is marked, focused, and named.
function saveSettings(event) {
  event.preventDefault();
  var form = event.target;
  var status = document.getElementById("settings-status");
  var changes = {};
  PROFILE_TEXT_FIELDS.forEach(function (field) {
    changes[field] = form.elements[field].value;
  });
  clearProblem(form);
  status.textContent = "Saving…";

  api("/api/profile", "PUT", changes)
    .then(function (saved) {
      form.removeAttribute("data-unsaved");
      useProfile(saved);
      showFamilyCalls();
      status.textContent = "";
      toast("Profile saved");
    })
    .catch(function (problem) {
      var detail = problem.detail || {};
      var input = detail.field && form.elements[detail.field];
      if (input) {
        showProblem(input, detail.message);
        status.textContent = detail.message;
      } else {
        status.textContent = "I couldn’t save that just now. Please try again.";
      }
    });
}

function startScreens() {
  document.getElementById("pill-taken").addEventListener("click", function () { answerReminder("taken"); });
  document.getElementById("pill-snooze").addEventListener("click", function () { answerReminder("snooze"); });
  document.getElementById("pill-again").addEventListener("click", function () {
    if (talkState === "idle") {
      speak(pillState.due_words); // never into an open microphone
    }
  });
  document.getElementById("pill-form").addEventListener("submit", savePill);
  document.getElementById("pill-add-time").addEventListener("click", function () {
    var input = addTimeInput("");
    if (input) {
      input.focus();
    }
  });
  document.getElementById("pill-cancel").addEventListener("click", function () {
    resetPillForm();
    document.getElementById("pill-status").textContent = "";
  });
  document.getElementById("confirm-yes").addEventListener("click", removePill);
  document.getElementById("confirm-no").addEventListener("click", function () {
    document.getElementById("confirm-dialog").close();
  });

  var form = document.getElementById("settings-form");
  form.addEventListener("submit", saveSettings);
  form.addEventListener("change", saveChoice);
  form.addEventListener("input", function (event) {
    if (PROFILE_TEXT_FIELDS.indexOf(event.target.name) !== -1) {
      form.setAttribute("data-unsaved", "");
    }
  });
  document.getElementById("today-take").addEventListener("click", function () { answerReminder("taken"); });
  document.getElementById("check-in-skip").addEventListener("click", skipCheckIn);

  // Doctor notes.
  document.querySelectorAll('input[name="notes-days"]').forEach(function (choice) {
    choice.addEventListener("change", showNotes);
  });
  document.getElementById("notes-print").addEventListener("click", function () {
    window.print();
  });
  document.getElementById("question-form").addEventListener("submit", addQuestion);

  // Check a message.
  document.getElementById("scam-check").addEventListener("click", function () { checkMessage("text"); });
  document.getElementById("scam-read").addEventListener("click", readMessageAloud);
  document.getElementById("scam-photo").addEventListener("click", function () {
    document.getElementById("scam-photo-input").click();
  });
  document.getElementById("scam-photo-input").addEventListener("change", choosePhoto);
  document.getElementById("scam-again").addEventListener("click", function () { speak(scamSpoken); });
  document.getElementById("scam-another").addEventListener("click", checkAnother);
  // Closing the tab with unsaved entries: the browser asks first.
  window.addEventListener("beforeunload", function (event) {
    if (form.hasAttribute("data-unsaved")) {
      event.preventDefault();
      event.returnValue = ""; // older browsers need this too
    }
  });
}
