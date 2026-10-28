// Grandma Buddy: the screens other than Today.
// Each time the router (app.js) shows a screen, it runs that screen's
// loader below, so the screen always shows fresh information.
// Pills, doctor notes, and scam check arrive in the next steps.

"use strict";

var SCREEN_LOADERS = {
  diary: showDiary,
  family: showFamily,
};

// ---------- My diary ----------

// A short line under an entry that didn't come from a "Something hurts" talk.
var DIARY_SOURCES = {
  safety_net: "Buddy showed the emergency screen.",
  check_in: "From the daily check-in.",
};

// Her entries from the last 30 days, newest first, under a heading per day.
function showDiary() {
  var list = document.getElementById("diary-list");
  var status = document.getElementById("diary-status");
  api("/api/diary?days=30")
    .then(function (entries) {
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
      status.hidden = false;
      status.textContent = "I couldn’t open your diary just now. Please try again in a moment.";
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
  var facts = [
    ["Where:", entry.body_area],
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

// ---------- Family and settings ----------

// The text entries on the form, named like the profile fields.
var PROFILE_TEXT_FIELDS = ["name", "preferred_name", "family_name", "family_phone", "family_email", "doctor_name", "doctor_phone"];
var VOICE_RATES = ["0.75", "0.9", "1.1"]; // Slower, Normal, Faster

function showFamily() {
  showFamilyCalls();
  fillSettingsForm();
}

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

// Put the saved profile into the form, unless it has entries that aren't
// saved yet (then they stay, so nothing typed is lost by going back).
function fillSettingsForm() {
  var form = document.getElementById("settings-form");
  if (form.hasAttribute("data-unsaved")) {
    return;
  }
  PROFILE_TEXT_FIELDS.forEach(function (field) {
    form.elements[field].value = profile[field] || "";
  });
  form.elements.voice_on.checked = profile.voice_on !== false;
  // The closest of Slower, Normal, Faster to the saved speed.
  var rate = Number(profile.voice_rate) || 0.9;
  var closest = VOICE_RATES.reduce(function (best, option) {
    return Math.abs(option - rate) < Math.abs(best - rate) ? option : best;
  });
  form.elements.voice_rate.value = closest;
  clearProblem(form);
  document.getElementById("settings-status").textContent = "";
}

function clearProblem(form) {
  form.querySelectorAll("[aria-invalid]").forEach(function (input) {
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
  });
  var note = document.getElementById("settings-problem");
  if (note) {
    note.remove();
  }
}

// Mark the entry the server sent back, say why right under it, and put
// the cursor there.
function showProblem(input, message) {
  var note = document.createElement("p");
  note.id = "settings-problem";
  note.className = "field-problem";
  note.textContent = message;
  input.insertAdjacentElement("afterend", note);
  input.setAttribute("aria-invalid", "true");
  input.setAttribute("aria-describedby", "settings-problem");
  input.focus();
}

// Save everything at once. The server checks every entry; if one needs
// another look, that entry is marked, focused, and named in the message.
function saveSettings(event) {
  event.preventDefault();
  var form = event.target;
  var status = document.getElementById("settings-status");
  var changes = {
    voice_on: form.elements.voice_on.checked,
    voice_rate: Number(form.elements.voice_rate.value),
  };
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
      status.textContent = "Saved. Buddy will use these from now on.";
      speak("Saved.");
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
  var form = document.getElementById("settings-form");
  form.addEventListener("submit", saveSettings);
  form.addEventListener("input", function () {
    form.setAttribute("data-unsaved", "");
  });
  // Closing the tab with unsaved entries: the browser asks first.
  window.addEventListener("beforeunload", function (event) {
    if (form.hasAttribute("data-unsaved")) {
      event.preventDefault();
      event.returnValue = ""; // older browsers need this too
    }
  });
}
