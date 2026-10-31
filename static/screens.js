// Grandma Buddy: the screens, the pill reminders, and toasts.
// Each time the router (app.js) shows a screen, it runs that screen's
// loader below, so the screen always shows fresh information.
// Checking a message and Doctor notes are designed, and arrive in the next
// steps.

"use strict";

var SCREEN_LOADERS = {
  today: function () {
    showTodayWeather();
    showCheckIn();
    showTodayDiary();
  },
  diary: showDiary,
  pills: showPillsScreen,
  notes: showNotes,
  family: function () {
    showFamilyCalls();
    showFamilyUpdate();
  },
  memories: showMemories,
  memory: showMemoryPage,
  settings: function () {
    fillSettingsForm();
    showLearned();
  },
  help: showHelp,
};

// ---------- Pill reminders (on every screen) ----------

// Today's reminders from /api/reminders, checked every 30 seconds (app.js).
// One answer drives the reminder card, the "My pills" card on Today, and
// the Pills screen's list.
var pillState = { reminders: [], due_title: "", due_words: "", has_pills: false };
var shownReminders = ""; // which reminder the card was already brought into view for
var spokenReminders = ""; // which reminder was already read aloud
var shownLabels = ""; // the labels on the card, drawn again only when they change

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

// The hidden demo (?demo=reminder in the address): the card for her next
// pill, as if it were due now, so it can be shown in a demo video without
// waiting for its time (/api/reminders/demo). Nothing is saved: its buttons
// answer the same way, and her real reminders stay as they are.
var demoReminder = null;
var DEMO_WAIT_MS = 2000;

function startDemoReminder() {
  if (new URLSearchParams(location.search).get("demo") !== "reminder") {
    return;
  }
  api("/api/reminders/demo")
    .then(function (demo) {
      // Her words and the thanks, made ahead in the natural voice: no wait.
      warmVoice(demo.words + " " + REMINDER_THANKS.taken + " " + REMINDER_THANKS.snooze);
      // A browser keeps a new page silent until its first tap, so the card
      // pops up 2 seconds after that tap (or key), and Buddy says it at once.
      var popUp = function () {
        document.removeEventListener("pointerdown", popUp, true);
        document.removeEventListener("keydown", popUp, true);
        setTimeout(function () {
          demoReminder = demo;
          showPillBanner();
        }, DEMO_WAIT_MS);
      };
      if (!navigator.userActivation || navigator.userActivation.hasBeenActive) {
        popUp();
      } else {
        document.addEventListener("pointerdown", popUp, true);
        document.addEventListener("keydown", popUp, true);
      }
    })
    .catch(function () {
      toast("Set up a pill first to see its reminder.", true);
    });
}

// What the card shows: the pills due now, or else the demo's.
function cardReminder() {
  var due = duePills();
  if (due.length) {
    return {
      key: due.map(function (r) { return r.id; }).join(","),
      pills: due,
      title: pillState.due_title,
      words: pillState.due_words,
    };
  }
  if (demoReminder) {
    return { key: "demo", pills: demoReminder.reminders, title: demoReminder.title, words: demoReminder.words, demo: true };
  }
  return null;
}

// Each pill on the card as on its bottle: the name, then the label word
// for word (a pill with no label shows just its name).
function showCardLabels(pills) {
  var drawn = JSON.stringify(pills.map(function (r) { return [r.name, r.label_dose]; }));
  if (drawn === shownLabels) {
    return;
  }
  shownLabels = drawn;
  var list = document.getElementById("pill-banner-labels");
  list.textContent = "";
  pills.forEach(function (reminder) {
    var item = element("li", "pill-banner-label");
    item.appendChild(element("p", "pill-name", reminder.name));
    if (reminder.label_dose) {
      item.appendChild(element("p", "pill-banner-label-words", reminder.label_dose));
    }
    list.appendChild(item);
  });
}

// "8:00 AM" from "2026-10-27T08:00:00" (local time) or from "08:00". The
// space before AM or PM never breaks, so a time is never split over 2 lines.
function clockTime(text) {
  var time = new Date(text.length === 5 ? "2000-01-01T" + text : text);
  return time.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).replace(/\s(?=[AP]M)/, "\u00a0");
}

// The card: Buddy says it with her name ("Rose, it's time for your evening
// Metformin."), each label exactly as the family typed it, "I took it", and
// "Remind me in 10 minutes". Read aloud once for each new reminder, but
// never while she is talking (the microphone would hear it), never over a
// safety message, and never cutting Buddy off mid-sentence (then it waits
// for the next check, 30 seconds later, or her next tap).
function showPillBanner() {
  var card = cardReminder();
  var banner = document.getElementById("pill-banner");
  var hadFocus = banner.contains(document.activeElement);
  banner.hidden = !card;
  if (!card) {
    shownReminders = "";
    spokenReminders = "";
    if (hadFocus) {
      focusScreenHeading(); // the button she tapped is gone
    }
    return;
  }
  var which = card.key;
  if (which !== shownReminders) {
    setText(document.getElementById("pill-banner-note"), ""); // an old note is about old pills
  }
  setText(document.getElementById("pill-banner-time"), clockTime(card.pills[0].due_at));
  setText(document.getElementById("pill-banner-words"), card.title);
  showCardLabels(card.pills);
  setText(document.getElementById("pill-taken"), card.pills.length > 1 ? "I took them" : "I took it");
  // After a Poison Control screen today: the fixed Poison Control message
  // with its call button, and the reminder is not read aloud.
  var poison = document.getElementById("pill-banner-poison");
  poison.hidden = !pillState.after_poison_control;
  setText(document.getElementById("pill-banner-poison-words"), pillState.poison_control_words || "");
  // A new reminder is brought into view once, unless she is talking or
  // someone is typing in a box. The banner is the first thing on the page,
  // so going to the top shows all of it (even while it is still easing in).
  var typing = document.activeElement && document.activeElement.matches("input, textarea, select");
  if (which !== shownReminders && buddyMaySpeak() && !typing) {
    shownReminders = which;
    window.scrollTo(0, 0);
  }
  // It counts as read only once the voice really starts (Chrome stays
  // silent until her first tap), so a blocked reminder is tried again.
  var quiet = !buddyMaySpeak() || safetySpeaking || isSpeaking() || pillState.after_poison_control;
  if (which !== spokenReminders && !quiet) {
    speak(card.words, { onStart: function () { spokenReminders = which; } });
  }
}

// A browser keeps a page silent until its first tap. A reminder that came
// before then is read aloud right after her first tap or key anywhere else
// (a tap on the card itself is her answer), once that tap's own work is done.
function readWaitingReminder(event) {
  var banner = document.getElementById("pill-banner");
  if (!banner.hidden && !banner.contains(event.target)) {
    setTimeout(showPillBanner, 0);
  }
}

var REMINDER_THANKS = {
  taken: "Thank you. I wrote that down.",
  snooze: "Okay. I’ll remind you again in 10 minutes.",
};

// Buddy's answer to "I took it" or "Remind me in 10 minutes".
function thankForAnswer(answer) {
  if (answer === "taken") {
    toast("Marked as taken");
  }
  if (currentScreen() === "talk") {
    say(REMINDER_THANKS[answer]);
  }
  if (buddyMaySpeak()) {
    speak(REMINDER_THANKS[answer]); // never into an open microphone (hands-free sends silence meanwhile)
  }
}

// "I took it" or "Remind me in 10 minutes", for every pill on the card.
function answerReminder(answer) {
  var card = cardReminder();
  var buttons = document.querySelectorAll("#pill-banner button, #today-take");
  var note = document.getElementById("pill-banner-note");
  if (!card) {
    return;
  }
  if (card.demo) {
    // The demo: the same thanks, and the card closes. Nothing is saved.
    demoReminder = null;
    showPillBanner();
    thankForAnswer(answer);
    return;
  }
  var ids = card.pills.map(function (r) { return r.id; });
  buttons.forEach(function (button) { button.disabled = true; });
  note.textContent = "";
  var mine = ++reminderRequests;
  api("/api/reminders/" + answer, "POST", { ids: ids })
    .then(function (state) {
      if (mine === reminderRequests) {
        showReminders(state);
      }
      thankForAnswer(answer);
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
    // "Next: evening pill at 6:00 PM", or "morning pills" for several.
    var together = reminders.filter(function (r) { return r.status === "upcoming" && r.due_at === next.due_at; });
    text = "Next: " + partOfDay(new Date(next.due_at)) + (together.length > 1 ? " pills at " : " pill at ") +
      clockTime(next.due_at);
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

// The "Are you sure?" sheet, shared by Remove (a pill) and Forget this
// (something Buddy learned). Keep it is where the cursor starts.
var onConfirm = null;

function askFirst(title, text, yesWords, action) {
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-text").textContent = text;
  document.getElementById("confirm-yes").textContent = yesWords;
  onConfirm = action;
  document.getElementById("confirm-dialog").showModal();
}

function confirmRemove(pill) {
  pillToRemove = pill;
  askFirst("Remove this pill?", "Buddy will stop reminding her about " + pill.name + ". You can undo this.",
    "Yes, remove it", removePill);
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

// The check-in row, first in the Today list. Once she has told Buddy how
// she feels in today's check-in: her mood, and a check with "Done" instead
// of "Start".
function showCheckIn() {
  api("/api/check-in")
    .then(function (today) {
      var words = today.skipped ? "Skipped for today" : "Not done yet";
      if (today.done) {
        words = (MOOD_WORDS[today.mood.mood] || "Checked in") + ", at " + clockTime(today.mood.at);
      }
      setText(document.getElementById("today-check-in"), words);
      document.getElementById("check-in-start").hidden = today.done;
      document.getElementById("check-in-done").hidden = !today.done;
    })
    .catch(function () {
      // No connection to our own server: keep what is shown.
    });
}

// Home's weather row: today's weather in her town, looked up on the web
// with Meta's web search (kept 3 hours on the server), and where it came
// from. Hidden when her town isn't set up or nothing was found.
var todayWeather = "";

function showTodayWeather() {
  var row = document.getElementById("today-weather");
  api("/api/briefing/weather")
    .then(function (weather) {
      todayWeather = weather.text;
      row.hidden = !weather.text; // empty: no town yet, or nothing to share just now
      setText(document.getElementById("today-weather-text"), weather.text);
      setText(document.getElementById("today-weather-from"), "From " + weather.sites.join(", "));
    })
    .catch(function () {
      row.hidden = true; // no connection to our own server
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
      list.appendChild(questionItem(question));
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

// One question: still to ask, with a quiet "Mark as asked"; or asked, with
// a check, "Asked", and Undo.
function questionItem(question) {
  var item = element("li", question.asked ? "doc-question-row is-asked" : "doc-question-row");
  item.appendChild(element("span", "doc-question", question.question));
  var answer = element("span", "doc-question-answer");
  if (question.asked) {
    var asked = element("span", "doc-asked");
    asked.innerHTML = CHECK_ICON; // a check and the word: never color alone
    asked.appendChild(document.createTextNode("Asked"));
    answer.appendChild(asked);
    var undo = element("button", "text-button doc-undo", "Undo");
    undo.type = "button";
    undo.setAttribute("aria-label", "Undo: not asked yet: " + question.question);
    undo.addEventListener("click", function () { setAsked(question, false, item); });
    answer.appendChild(undo);
  } else {
    answer.appendChild(smallButton("Mark as asked", "Mark as asked: " + question.question, function () {
      setAsked(question, true, item);
    }));
  }
  item.appendChild(answer);
  return item;
}

// "Mark as asked" or Undo. The question stays where it is (it is kept,
// never deleted); only its line changes, and the cursor stays on it.
function setAsked(question, asked, item) {
  var button = item.querySelector("button");
  button.disabled = true;
  api("/api/doctor-questions/" + question.id + (asked ? "/asked" : "/reopen"), "POST")
    .then(function () {
      question.asked = asked;
      var changed = questionItem(question);
      item.replaceWith(changed);
      changed.querySelector("button").focus();
      if (asked) {
        toast("Marked as asked");
      }
    })
    .catch(function () {
      button.disabled = false;
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

// ---------- The Memory book ----------

// Her stories as pages, newest first (/api/memories). A page is written and
// painted in the background after she tells it, so while any page is
// "writing" or "painting" the screen asks again every 3 seconds.
var MEMORY_POLL_MS = 3000;
var memoryPoll = null;
var shownMemories = ""; // what the screen shows now, so a poll redraws only on a change

function memoryPages() {
  return api("/api/memories").then(function (answer) {
    return answer.pages;
  });
}

function stillPainting(pages) {
  return pages.some(function (page) {
    return page.status === "writing" || page.status === "painting";
  });
}

// A page she watched being painted is ready: say so (toasts are read out
// by screen readers too).
var memoryStatuses = {}; // page id -> its status last time

function tellWhenReady(pages) {
  var ready = pages.some(function (page) {
    var before = memoryStatuses[page.id];
    return page.status === "ready" && (before === "writing" || before === "painting");
  });
  pages.forEach(function (page) { memoryStatuses[page.id] = page.status; });
  if (ready) {
    toast("Your memory page is ready");
  }
}

// Ask again in a moment, while she is still on that screen.
function pollMemories(pages, screen, load) {
  clearTimeout(memoryPoll);
  if (stillPainting(pages)) {
    memoryPoll = setTimeout(function () {
      if (currentScreen() === screen) {
        load();
      }
    }, MEMORY_POLL_MS);
  }
}

// The picture: a soft wash of Buddy's colors with a calm shimmer while
// Buddy writes or paints, and the painting fading in once it has loaded.
// A painting that didn't work gets "Paint it again" (on the page itself).
var PICTURE_WORDS = { writing: "Writing your page…", painting: "Painting your picture…" };

function memoryPicture(page, onItsPage) {
  var picture = element("div", "memory-picture");
  picture.setAttribute("data-status", page.status);
  if (page.picture) {
    var image = element("img", "memory-img");
    image.alt = page.scene ? "Painting: " + page.scene : "A painting for this memory";
    image.width = 1536;
    image.height = 1024;
    image.decoding = "async";
    image.loading = onItsPage ? "eager" : "lazy"; // the book's lower pages load as she scrolls
    image.addEventListener("load", function () { image.classList.add("shown"); });
    image.addEventListener("error", function () { image.remove(); });
    image.src = page.picture;
    picture.appendChild(image);
  } else if (PICTURE_WORDS[page.status]) {
    var words = element("p", "memory-picture-words", PICTURE_WORDS[page.status]);
    if (page.status === "writing") {
      words.setAttribute("aria-hidden", "true"); // the title already says "Writing your page…"
    }
    picture.appendChild(words);
  } else if (onItsPage) {
    var again = element("button", "pill-button pill-button--quiet pill-button--small memory-paint-again", "Paint it again");
    again.type = "button";
    again.addEventListener("click", function () {
      again.disabled = true;
      api("/api/memories/" + page.id + "/paint", "POST")
        .then(showMemoryPage)
        .catch(function () {
          again.disabled = false;
          toast("I couldn’t paint it just now. Please try again in a moment.", true);
        });
    });
    picture.appendChild(again);
  }
  return picture;
}

function showMemories() {
  var list = document.getElementById("memory-cards");
  var status = document.getElementById("memories-status");
  memoryPages()
    .then(function (pages) {
      status.hidden = pages.length > 0;
      status.textContent = "Your memory book is empty. Tap “Tell Buddy a memory” to make the first page.";
      tellWhenReady(pages);
      var drawn = JSON.stringify(pages);
      if (drawn !== shownMemories) {
        shownMemories = drawn;
        // Redrawing keeps keyboard focus on the card she was on.
        var focused = document.activeElement.closest && document.activeElement.closest(".memory-card");
        var focusedPage = focused ? focused.getAttribute("href") : "";
        list.textContent = "";
        pages.forEach(function (page) {
          var card = element("a", "memory-card");
          card.href = "#/memory/" + page.id;
          card.appendChild(memoryPicture(page, false));
          var words = element("span", "memory-card-text");
          words.appendChild(element("h2", "memory-card-title", page.title || "Writing your page…"));
          words.appendChild(element("span", "memory-card-date", page.date));
          card.appendChild(words);
          var item = document.createElement("li");
          item.appendChild(card);
          list.appendChild(item);
          if (card.getAttribute("href") === focusedPage) {
            card.focus();
          }
        });
      }
      list.removeAttribute("aria-busy");
      pollMemories(pages, "memories", showMemories);
    })
    .catch(function () {
      list.removeAttribute("aria-busy");
      status.hidden = false;
      status.textContent = "I couldn’t open your memory book just now. Please try again in a moment.";
    });
}

var memoryOnScreen = null; // the page shown at #/memory/3, for "Read it to me"

function showMemoryPage() {
  var id = Number(screenDetail());
  var status = document.getElementById("memory-status");
  memoryPages()
    .then(function (pages) {
      var page = pages.filter(function (one) { return one.id === id; })[0];
      document.querySelector(".memory-page").hidden = !page;
      document.getElementById("memory-actions").hidden = !page || !page.mailto;
      document.querySelector(".memory-share-note").hidden = !page || !page.mailto;
      status.hidden = Boolean(page);
      if (!page) {
        status.textContent = "I couldn’t find that page. It may be in your memory book under another day.";
        return;
      }
      tellWhenReady([page]);
      document.title = (page.title || "Memory book") + " · Grandma Buddy";
      var drawn = JSON.stringify(page);
      if (drawn !== JSON.stringify(memoryOnScreen)) {
        memoryOnScreen = page;
        var picture = document.getElementById("memory-picture");
        picture.textContent = "";
        picture.appendChild(memoryPicture(page, true));
        setText(document.getElementById("memory-title"), page.title || "Writing your page…");
        setText(document.getElementById("memory-date"), page.date);
        var story = document.getElementById("memory-story");
        story.textContent = "";
        page.paragraphs.forEach(function (paragraph) {
          story.appendChild(element("p", "", paragraph));
        });
      }
      var send = document.getElementById("memory-send");
      send.href = page.mailto;
      setText(send, "Send to " + (profile.family_name || "family"));
      document.getElementById("memory-read").hidden = !voiceSettings.on; // it would stay silent
      pollMemories([page], "memory", showMemoryPage);
    })
    .catch(function () {
      status.hidden = false;
      status.textContent = "I couldn’t open this page just now. Please try again in a moment.";
    });
}

// "Read it to me": the title, then the story, in Buddy's voice.
function readMemory() {
  if (memoryOnScreen && talkState === "idle") {
    speak(memoryOnScreen.title + ". " + memoryOnScreen.paragraphs.join(" "));
  }
}

// ---------- Family and settings ----------

// The text entries on the form, named like the profile fields.
var PROFILE_TEXT_FIELDS = ["name", "preferred_name", "family_name", "family_phone", "family_email", "family2_name",
  "family2_phone", "doctor_name", "doctor_phone", "city"];
var VOICE_RATES = ["0.75", "0.9", "1.1"]; // Slower, Normal, Faster

// Big call buttons for the family member and the doctor, when their
// numbers are set up.
function showFamilyCalls() {
  var row = document.getElementById("family-calls");
  row.textContent = "";
  var people = [
    { name: profile.family_name || "family", phone: profile.family_phone },
    { name: profile.family2_name || "family", phone: profile.family2_phone },
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

// ---------- The family update ----------

var familyUpdate = null; // the update on screen: its words, and its email link

// "2026-10-28" for today (0) or yesterday (1), on this computer's clock.
function updateDay(daysBack) {
  var day = new Date();
  day.setDate(day.getDate() - daysBack);
  var two = function (number) { return (number < 10 ? "0" : "") + number; };
  return day.getFullYear() + "-" + two(day.getMonth() + 1) + "-" + two(day.getDate());
}

// Ask for the day's update and show it exactly as it will be sent.
function showFamilyUpdate() {
  var back = Number(document.querySelector('input[name="update-day"]:checked').value);
  var box = document.getElementById("update-text");
  var status = document.getElementById("update-status");
  var send = document.getElementById("update-send");
  var name = profile.family_name || "family";
  box.setAttribute("aria-busy", "true");
  setText(document.getElementById("update-title"), (back ? "Yesterday’s" : "Today’s") + " update for " + name);
  setText(send, "Send to " + name);
  api("/api/family/summary?date=" + updateDay(back))
    .then(function (update) {
      familyUpdate = update;
      status.hidden = true;
      setText(box, update.text);
      send.href = update.mailto;
      document.getElementById("update-no-email").hidden = Boolean(update.to);
    })
    .catch(function () {
      status.hidden = false;
      status.textContent = "I couldn’t write the update just now. Please try again in a moment.";
    })
    .then(function () {
      box.removeAttribute("aria-busy");
    });
}

// "Copy": the same words, for a text message or anywhere else.
function copyUpdate() {
  if (!familyUpdate) {
    return;
  }
  var copying = navigator.clipboard ? navigator.clipboard.writeText(familyUpdate.text) : Promise.reject();
  copying
    .then(function () {
      toast("Copied");
    })
    .catch(function () {
      toast("I couldn’t copy it. Please select the words and copy them yourself.", true);
    });
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
  showVoiceChoices();
  form.elements.chime.checked = profile.chime === true;
  form.elements.hands_free.checked = profile.hands_free !== false;
  // The closest of Slower, Normal, Faster to the saved speed.
  var rate = Number(profile.voice_rate) || 0.9;
  var closest = VOICE_RATES.reduce(function (best, option) {
    return Math.abs(option - rate) < Math.abs(best - rate) ? option : best;
  });
  form.elements.voice_rate.value = closest;
}

// ---------- What Buddy has learned ----------

// The facts Buddy remembers about her life, and its notes on how she likes
// to talk (/api/learned). Each can be forgotten ("Are you sure?", then Undo).
var KIND_WORDS = { person: "Someone she loves", pet: "A pet", hobby: "Something she enjoys",
  show: "A favorite show", event: "A plan", other: "About her" };

function showLearned() {
  api("/api/learned")
    .then(function (learned) {
      setText(document.getElementById("learned-lead"), learned.days_learned >= 2
        ? "Buddy has learned from " + learned.days_learned + " days of talks, to talk with her like a friend. Nothing here is about her health."
        : "Buddy is still getting to know her. After a couple of days of talks, it learns how she likes to talk. Nothing here is about her health.");
      learnedRows(document.getElementById("learned-notes"), learned.notes, "notes", "Nothing yet.", function (note) {
        return { words: note.note, hint: "" };
      });
      learnedRows(document.getElementById("learned-facts"), learned.facts, "facts", "Nothing yet.", function (fact) {
        return { words: fact.fact, hint: KIND_WORDS[fact.kind] + (fact.follow_up ? " · Buddy will ask: “" + fact.follow_up + "”" : "") };
      });
    })
    .catch(function () {
      setText(document.getElementById("learned-undo"), "I couldn’t open this just now. Please try again in a moment.");
    });
}

function learnedRows(group, items, what, emptyWords, describe) {
  group.textContent = "";
  if (!items.length) {
    group.appendChild(element("p", "group-row empty", emptyWords));
    return;
  }
  items.forEach(function (item) {
    var shown = describe(item);
    var row = element("div", "group-row");
    row.setAttribute("role", "listitem");
    var words = element("span", "group-label", shown.words);
    if (shown.hint) {
      words.appendChild(element("span", "group-hint", shown.hint));
    }
    row.appendChild(words);
    row.appendChild(smallButton("Forget this", "Forget: " + shown.words, function () {
      askFirst("Forget this?", "Buddy will no longer remember “" + shown.words + "”. You can undo this.",
        "Yes, forget it", function () { forgetLearned(what, item.id, shown.words); });
    }));
    group.appendChild(row);
  });
}

function forgetLearned(what, id, words) {
  document.getElementById("confirm-dialog").close();
  var line = document.getElementById("learned-undo");
  api("/api/learned/" + what + "/" + id + "/forget", "POST")
    .then(function () {
      showLearned();
      line.textContent = "Forgot “" + words + "”. ";
      var undo = smallButton("Undo", "Undo: remember “" + words + "” again", function () {
        api("/api/learned/" + what + "/" + id + "/restore", "POST")
          .then(function () {
            line.textContent = "Buddy remembers it again.";
            focusScreenHeading(); // the Undo button she tapped is gone
            showLearned();
          })
          .catch(function () {
            line.textContent = "I couldn’t bring it back just now. Please try again.";
          });
      });
      line.appendChild(undo);
      undo.focus();
    })
    .catch(function () {
      line.textContent = "I couldn’t forget that just now. Please try again.";
    });
}

// ---------- Buddy's voice ----------

// "Microsoft Ava Online (Natural) - English (United States)" -> "Ava (natural), United States"
function voiceLabel(voice) {
  return voice.name.replace(/^Microsoft /, "").replace(/ Online \(Natural\)/, " (natural)")
    .replace(/ - English \((.+)\)$/, ", $1");
}

// A group of choices in the voice list.
function voiceGroup(select, label, choices) {
  if (!choices.length) {
    return;
  }
  var group = document.createElement("optgroup");
  group.label = label;
  choices.forEach(function (choice) {
    var option = document.createElement("option");
    option.value = choice.value;
    option.textContent = choice.label;
    group.appendChild(option);
  });
  select.appendChild(group);
}

// The voices in Settings: Buddy's natural voices first (when they are set
// up on this computer), then this browser's own, best first, with hers
// chosen. Called again when the voices arrive late (speech.js).
function showVoiceChoices() {
  var select = document.getElementById("voice-choice");
  select.textContent = "";
  var natural = naturalVoice.available ? naturalVoice.voices : [];
  voiceGroup(select, "Buddy’s natural voices", natural.map(function (voice) {
    return { value: NATURAL + voice.id, label: voice.name };
  }));
  voiceGroup(select, "This browser’s voices", englishVoices().map(function (voice) {
    return { value: voice.name, label: voiceLabel(voice) };
  }));
  var current = chosenNatural();
  select.value = current ? NATURAL + current : chosenVoice ? chosenVoice.name : "";
  select.disabled = select.options.length === 0;
  document.getElementById("voice-try").disabled = select.options.length === 0;
  document.getElementById("voice-hint").hidden = natural.length > 0 || !onlyRoboticVoices();
}

// "Try it": a few words in the chosen voice and speed.
function tryVoice() {
  if (talkState === "idle") {
    speak("Hello, I’m Buddy. I’m here whenever you’d like to talk.", { preview: true });
  }
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
  if (field === "voice_name") {
    chooseVoice(input.value);
    tryVoice(); // she hears her choice at once
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

// ---------- Help: how Buddy works ----------

// The four Meta models, then every feature with the models behind it
// (/api/how reads them from the app's settings), and a call button for
// her family when their number is set up.
var helpDrawn = false;

function showHelp() {
  var call = document.getElementById("help-call-family");
  var href = "tel:" + (profile.family_phone || "");
  call.hidden = !(profile.family_phone && isCallLink(href));
  call.href = href;
  setText(document.getElementById("help-call-label"), "Call " + (profile.family_name || "family"));
  if (helpDrawn) {
    return;
  }
  var models = document.getElementById("help-models");
  var status = document.getElementById("help-status");
  api("/api/how")
    .then(function (how) {
      helpDrawn = true;
      status.hidden = true;
      var names = {};
      models.textContent = "";
      how.models.forEach(function (model) {
        names[model.id] = model.name;
        var card = element("li", "help-model");
        card.appendChild(element("p", "help-model-name", model.name));
        card.appendChild(element("p", "help-model-does", model.does));
        models.appendChild(card);
      });
      var features = document.getElementById("help-features");
      features.textContent = "";
      how.features.forEach(function (feature) {
        var row = element("li", "row help-feature");
        var text = element("div", "row-text");
        text.appendChild(element("p", "row-title", feature.name));
        text.appendChild(element("p", "row-meta", feature.what));
        // Which Meta models it uses, or "No AI" when it uses none.
        var chips = element("p", "tags");
        feature.models.forEach(function (id) {
          chips.appendChild(element("span", "tag", names[id] || id));
        });
        if (!feature.models.length) {
          chips.appendChild(element("span", "tag tag--no-ai", "No AI"));
        }
        text.appendChild(chips);
        if (feature.here) {
          text.appendChild(element("p", "help-here", feature.here));
        }
        row.appendChild(text);
        features.appendChild(row);
      });
    })
    .catch(function () {
      status.hidden = false;
      status.textContent = "I couldn’t show this just now. Please try again in a moment.";
    })
    .then(function () {
      models.removeAttribute("aria-busy");
    });
}

// A tap anywhere on a Today row does what its button or link says, so the
// targets are big for shaky hands. (Keyboards use the button or link itself.)
function tapWholeRow(event) {
  var row = event.target.closest(".today .row");
  if (!row || event.target.closest("a, button")) {
    return;
  }
  var target = row.querySelector(".row-link:not([hidden])");
  if (target) {
    target.click();
  }
}

function startScreens() {
  document.getElementById("pill-taken").addEventListener("click", function () { answerReminder("taken"); });
  document.getElementById("pill-snooze").addEventListener("click", function () { answerReminder("snooze"); });
  document.getElementById("pill-again").addEventListener("click", function () {
    var card = cardReminder();
    if (card && buddyMaySpeak()) {
      speak(card.words); // never into an open microphone
    }
  });
  document.addEventListener("click", readWaitingReminder, true);
  document.querySelector(".today").addEventListener("click", tapWholeRow);
  document.getElementById("today-weather-say").addEventListener("click", function () {
    if (todayWeather && buddyMaySpeak()) {
      speak(todayWeather);
    }
  });
  document.addEventListener("keydown", readWaitingReminder, true);
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
  document.getElementById("confirm-yes").addEventListener("click", function () { onConfirm(); });
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
  document.getElementById("voice-try").addEventListener("click", tryVoice);

  // The family update.
  document.querySelectorAll('input[name="update-day"]').forEach(function (choice) {
    choice.addEventListener("change", showFamilyUpdate);
  });
  document.getElementById("update-copy").addEventListener("click", copyUpdate);

  // Doctor notes.
  document.querySelectorAll('input[name="notes-days"]').forEach(function (choice) {
    choice.addEventListener("change", showNotes);
  });
  document.getElementById("notes-print").addEventListener("click", function () {
    window.print();
  });
  document.getElementById("question-form").addEventListener("submit", addQuestion);

  // The Memory book.
  document.getElementById("memory-print").addEventListener("click", function () {
    window.print();
  });
  document.getElementById("memory-read").addEventListener("click", readMemory);

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
