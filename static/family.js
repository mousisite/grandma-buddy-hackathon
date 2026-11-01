// Grandma Buddy: the family page (/family), for the people who help her.
// Sign in, or join with an invite code from her Settings; then her day as
// she shares it (/api/family/dashboard, app/family.py day_facts): what
// needs a look (a missed pill, a safety screen), whether she talked with
// Buddy, her mood, her pills, her diary in her words, and her memory book
// pages. It asks again every 30 seconds while the page is open, and can
// show a notification on this device when something new needs a look.
// This page has no tab bar and no orb: it is for the family, not for her.

"use strict";

var POLL_MS = 30 * 1000;
var NOTIFY_KEY = "buddy-family-notify"; // "on" when she asked for notifications on this device
var VIEWS = ["family-signin", "family-join", "family-day"];
var dayPoll = null;
var herName = "She";
var shownAlerts = null; // today's alerts last shown (their words), to notice a new one
var shownMessages = null; // today's messages last shown, to notice a new one

// Ask our own server (like app.js's api()). Rejects with .detail when it says no.
function api(path, method, body) {
  var options = { method: method || "GET" };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  return fetch(path, options).then(function (response) {
    return response.json().catch(function () { return {}; }).then(function (answer) {
      if (!response.ok) {
        var refused = new Error("Refused");
        refused.detail = answer.detail;
        refused.status = response.status;
        throw refused;
      }
      return answer;
    });
  });
}

function setText(element, text) {
  if (element.textContent !== text) {
    element.textContent = text;
  }
}

function element(tag, className, text) {
  var made = document.createElement(tag);
  made.className = className;
  if (text !== undefined) {
    made.textContent = text;
  }
  return made;
}

// ---------- Which view ----------

function show(view) {
  VIEWS.forEach(function (id) {
    document.getElementById(id).hidden = id !== view;
  });
  document.getElementById("sign-out").hidden = view !== "family-day";
  clearTimeout(dayPoll);
  window.scrollTo(0, 0);
  document.querySelector("#" + view + " h1").focus();
}

// A refused entry: marked under its field, saying how to fix it; or a line.
function showProblem(form, status, problem) {
  var detail = problem.detail || {};
  form.querySelectorAll("[aria-invalid]").forEach(function (input) { input.removeAttribute("aria-invalid"); });
  if (detail.field && form.elements[detail.field]) {
    form.elements[detail.field].setAttribute("aria-invalid", "true");
    form.elements[detail.field].focus();
    status.textContent = detail.message;
  } else {
    status.textContent = typeof problem.detail === "string" ? problem.detail
      : "I couldn’t do that just now. Please try again in a moment.";
  }
}

// ---------- Signing in and joining ----------

function signIn(event) {
  event.preventDefault();
  var form = event.target;
  var status = document.getElementById("signin-status");
  status.textContent = "Signing in…";
  api("/api/family/sign-in", "POST", { email: form.elements.email.value, password: form.elements.password.value })
    .then(function () {
      form.reset();
      status.textContent = "";
      showDay();
    })
    .catch(function (problem) { showProblem(form, status, problem); });
}

function join(event) {
  event.preventDefault();
  var form = event.target;
  var status = document.getElementById("join-status");
  status.textContent = "One moment…";
  api("/api/family/account", "POST", {
    code: form.elements.code.value, name: form.elements.name.value,
    email: form.elements.email.value, password: form.elements.password.value,
  })
    .then(function () {
      form.reset();
      status.textContent = "";
      showDay();
    })
    .catch(function (problem) { showProblem(form, status, problem); });
}

// "Try the demo as Maria": the made-up account, in demo mode only.
function tryTheDemo() {
  var status = document.getElementById("signin-status");
  status.textContent = "Signing in as Maria…";
  api("/api/family/demo-sign-in", "POST", {})
    .then(function () {
      status.textContent = "";
      showDay();
    })
    .catch(function (problem) {
      status.textContent = typeof problem.detail === "string" ? problem.detail
        : "I couldn’t open the demo just now. Please try again in a moment.";
    });
}

function signOut() {
  api("/api/family/sign-out", "POST", {}).catch(function () {}).then(function () {
    shownAlerts = null;
    shownMessages = null;
    document.title = "Family · Grandma Buddy";
    show("family-signin");
  });
}

// ---------- Her day ----------

function daysBack() {
  return Number(document.querySelector('input[name="family-day"]:checked').value);
}

// "2026-10-30" for today (0), yesterday (1), the day before (2).
function dayDate(back) {
  var day = new Date();
  day.setDate(day.getDate() - back);
  var two = function (number) { return (number < 10 ? "0" : "") + number; };
  return day.getFullYear() + "-" + two(day.getMonth() + 1) + "-" + two(day.getDate());
}

function showDay() {
  show("family-day");
  loadDay();
  loadPlan();
  afterCheckout();
}

function loadDay() {
  clearTimeout(dayPoll);
  var back = daysBack();
  var status = document.getElementById("day-status");
  api("/api/family/dashboard?date=" + dayDate(back))
    .then(function (day) {
      status.hidden = true;
      drawDay(day, back === 0);
      // Today keeps itself fresh while the page is open.
      if (back === 0 && !document.hidden) {
        dayPoll = setTimeout(loadDay, POLL_MS);
      }
    })
    .catch(function (problem) {
      if (problem.status === 401) {
        show("family-signin"); // the session ended
        return;
      }
      status.hidden = false;
      status.textContent = "I couldn’t get her day just now. Please try again in a moment.";
    });
}

// A line for a part she doesn't share.
function notShared(what) {
  return herName + " hasn’t shared " + what + ". She can turn it on in Buddy’s Settings, under “What your family can see”.";
}

function drawDay(day, today) {
  herName = day.her_name;
  setText(document.getElementById("day-title"), herName + "’s day");
  setText(document.getElementById("day-words"), day.day_words);

  setText(document.getElementById("talked"), day.talked.yes
    ? "Yes, last at " + day.talked.last_time
    : (today ? "Not yet today" : "Not that day"));

  setText(document.getElementById("mood"), !day.shares.mood ? notShared("her mood")
    : day.mood ? day.mood.words + ", at " + day.mood.time : (today ? "No check-in yet today" : "No check-in that day"));

  var pills = document.getElementById("pills");
  var notTaken = document.getElementById("pills-not-taken");
  if (!day.shares.pills) {
    setText(pills, notShared("her pills"));
    setText(notTaken, "");
  } else if (!day.pills.total) {
    setText(pills, "No pill reminders that day");
    setText(notTaken, "");
  } else {
    setText(pills, day.pills.taken + " of " + day.pills.total + " taken");
    setText(notTaken, day.pills.not_taken.map(function (pill) {
      return pill.state + ": " + pill.name + " at " + pill.time;
    }).join(". "));
  }

  setText(document.getElementById("safety"), !day.shares.safety ? notShared("safety screens")
    : day.safety.length ? day.safety.map(function (screen) { return screen.time + ": " + screen.words; }).join(" ")
    : (today ? "None today" : "None that day"));

  var diaryNote = document.getElementById("diary-note");
  var diaryList = document.getElementById("diary-list");
  diaryList.textContent = "";
  if (!day.shares.diary) {
    setText(diaryNote, notShared("her diary"));
  } else if (!day.diary.length) {
    setText(diaryNote, today ? "Nothing written down yet today." : "Nothing written down that day.");
  } else {
    setText(diaryNote, "");
    day.diary.forEach(function (entry) {
      var item = element("li", "entry");
      item.appendChild(element("p", "entry-when", entry.time));
      item.appendChild(element("p", "entry-words", entry.quoted ? "“" + entry.words + "”" : entry.words));
      if (entry.note) {
        item.appendChild(element("p", "entry-note", entry.note));
      }
      diaryList.appendChild(item);
    });
  }

  // The messages between her and the family that day, both ways, and the
  // postcard she sent.
  setText(document.getElementById("messages-title"), "Messages with " + herName);
  setText(document.getElementById("reply-label"), "Write to " + herName);
  setText(document.getElementById("reply-send"), "Send to " + herName);
  var messages = document.getElementById("messages-list");
  messages.textContent = "";
  setText(document.getElementById("messages-note"), day.messages.length ? ""
    : (today ? "No messages yet today." : "No messages that day."));
  day.messages.forEach(function (message) {
    var item = element("li", "entry");
    var who = message.from === "family" ? (message.name || "Family") : herName;
    item.appendChild(element("p", "entry-when", who + ", " + message.time));
    if (message.voice) {
      var play = element("button", "pill-button pill-button--quiet pill-button--small entry-voice", "Play");
      play.type = "button";
      play.setAttribute("aria-label", "Play " + who + "’s voice message");
      play.addEventListener("click", function () {
        var sound = new Audio(message.voice);
        play.textContent = "Playing…";
        sound.addEventListener("ended", function () { play.textContent = "Play again"; });
        sound.play().catch(function () { play.textContent = "Play"; });
      });
      item.appendChild(play);
    }
    item.appendChild(element("p", "entry-words", message.text ? "“" + message.text + "”" : "A voice message"));
    messages.appendChild(item);
  });
  var postcardPart = document.getElementById("postcard-part");
  postcardPart.hidden = !day.postcard;
  if (day.postcard) {
    // The painting, made once and kept while it is the same one (the page
    // asks again every 30 seconds).
    var holder = document.getElementById("postcard-picture");
    var picture = holder.querySelector("img");
    if (!picture || picture.getAttribute("src") !== day.postcard.picture) {
      holder.textContent = "";
      picture = element("img", "postcard-img");
      picture.id = "postcard-img";
      picture.width = 1536;
      picture.height = 1024;
      picture.src = day.postcard.picture;
      holder.appendChild(picture);
    }
    picture.alt = "Painting: " + day.postcard.scene;
    setText(document.getElementById("postcard-sentence"), "“" + day.postcard.sentence + "”");
    setText(document.getElementById("postcard-time"), "Sent at " + day.postcard.time + ", in her own words.");
  }

  var memories = document.getElementById("memories-list");
  memories.textContent = "";
  setText(document.getElementById("memories-note"), !day.memories ? notShared("her memory book pages")
    : day.memories.length ? "" : (today ? "No new pages today." : "No new pages that day."));
  (day.memories || []).forEach(function (title) {
    var row = element("li", "row");
    var text = element("span", "row-text");
    text.appendChild(element("span", "row-title", title));
    row.appendChild(text);
    memories.appendChild(row);
  });

  var alerts = document.getElementById("alerts");
  var list = document.getElementById("alerts-list");
  list.textContent = "";
  day.alerts.forEach(function (alert) {
    var item = document.createElement("li");
    item.appendChild(element("span", "alert-time", alert.time));
    item.appendChild(element("span", "alert-words", alert.words));
    list.appendChild(item);
  });
  alerts.hidden = day.alerts.length === 0;
  document.title = (day.alerts.length && today ? "(" + day.alerts.length + ") " : "") + "Family · Grandma Buddy";

  if (today) {
    tellAboutNewAlerts(day.alerts.map(function (alert) { return alert.words; }));
    tellAboutNewMessages(day.messages.filter(function (message) { return message.from !== "family"; })
      .map(function (message) { return message.time + " " + message.text; }));
  }
}

// ---------- The Family plan ----------

// Free, or the Family plan and when it renews (or ends). Stripe's own page
// takes any payment, in test mode; with no key the demo flow has no card.
function loadPlan() {
  var status = document.getElementById("plan-status");
  api("/api/billing")
    .then(drawPlan)
    .catch(function () {
      status.textContent = "I couldn’t check your plan just now.";
    });
}

function drawPlan(plan) {
  var family = plan.plan === "family";
  setText(document.getElementById("plan-name"), !family ? "Free plan"
    : "Family plan" + (plan.demo ? " (demo mode, no real charge)" : ""));
  var words;
  if (!family) {
    words = "Everything Buddy does for her, free. The Family plan is " + plan.price + "." +
      (plan.mode === "demo" ? " Demo mode: nothing is ever charged." : " Paid through Stripe in test mode: nothing is ever really charged.");
  } else if (plan.cancel_at_period_end) {
    words = "It stays on until " + plan.ends_on + ", then ends. Nothing more is charged.";
  } else {
    words = "Renews on " + plan.renews_on + ", " + plan.price + ".";
  }
  setText(document.getElementById("plan-words"), words);
  document.getElementById("plan-start").hidden = family;
  document.getElementById("plan-cancel").hidden = !family || plan.cancel_at_period_end;
  document.getElementById("plan-cancel-ask").hidden = true;
  document.getElementById("plan-demo").hidden = true;
}

// "Start the Family plan": Stripe's page, or the demo box.
function startPlan() {
  var status = document.getElementById("plan-status");
  var button = document.getElementById("plan-start");
  button.disabled = true;
  status.textContent = "One moment…";
  api("/api/billing/checkout", "POST", {})
    .then(function (answer) {
      status.textContent = "";
      if (answer.url) {
        location.href = answer.url; // Stripe's own page (test mode)
        return;
      }
      var demo = document.getElementById("plan-demo");
      demo.hidden = false;
      document.getElementById("plan-demo-start").focus();
    })
    .catch(function (problem) {
      status.textContent = typeof problem.detail === "string" ? problem.detail
        : "I couldn’t open the payment page just now. Please try again in a moment.";
    })
    .then(function () {
      button.disabled = false;
    });
}

function startDemoPlan() {
  var status = document.getElementById("plan-status");
  api("/api/billing/demo", "POST", {})
    .then(function (plan) {
      drawPlan(plan);
      status.textContent = "You’re on the Family plan, in demo mode. Nothing was charged.";
      document.getElementById("plan-cancel").focus();
    })
    .catch(function (problem) {
      status.textContent = typeof problem.detail === "string" ? problem.detail : "I couldn’t start it just now. Please try again.";
    });
}

function cancelPlan() {
  var status = document.getElementById("plan-status");
  api("/api/billing/cancel", "POST", {})
    .then(function (plan) {
      drawPlan(plan);
      status.textContent = "Cancelled.";
      document.getElementById("plan-title").focus();
    })
    .catch(function (problem) {
      status.textContent = typeof problem.detail === "string" ? problem.detail : "I couldn’t cancel it just now. Please try again.";
    });
}

// Back from Stripe's page (/billing/return sends her to #billing, or to
// #billing-problem when the payment didn't check out).
function afterCheckout() {
  var came = location.hash;
  if (came !== "#billing" && came !== "#billing-problem") {
    return;
  }
  history.replaceState(null, "", location.pathname);
  var status = document.getElementById("plan-status");
  status.textContent = came === "#billing" ? "Welcome to the Family plan. Thank you!"
    : "That payment didn’t go through, so nothing changed. You can try again.";
  document.getElementById("billing").scrollIntoView();
  document.getElementById("plan-title").focus();
}

// ---------- Notifications on this device ----------

function notifyWanted() {
  var remembered = "";
  try { remembered = localStorage.getItem(NOTIFY_KEY) || ""; } catch (e) {}
  return remembered === "on" && "Notification" in window && Notification.permission === "granted";
}

// A new alert since the last look at today: a notification, when she asked for them.
function tellAboutNewAlerts(words) {
  if (shownAlerts !== null && notifyWanted()) {
    words.forEach(function (line) {
      if (shownAlerts.indexOf(line) === -1) {
        var note = new Notification(herName + " needs a look", { body: line, tag: "buddy-family-" + line });
        note.addEventListener("click", function () { window.focus(); note.close(); });
      }
    });
  }
  shownAlerts = words;
}

// "Write to Rose": sent to her Family screen as this family member's words.
function reply(event) {
  event.preventDefault();
  var form = event.target;
  var status = document.getElementById("reply-status");
  var text = form.elements.text.value.trim();
  if (!text) {
    status.textContent = "Write a short message first.";
    form.elements.text.focus();
    return;
  }
  status.textContent = "Sending…";
  api("/api/family/reply", "POST", { text: text })
    .then(function () {
      form.reset();
      status.textContent = "Sent. Buddy will read it to " + herName + ".";
      loadDay();
    })
    .catch(function (problem) {
      if (problem.status === 401) {
        show("family-signin");
        return;
      }
      status.textContent = typeof problem.detail === "string" ? problem.detail
        : "I couldn’t send that just now. Please try again in a moment.";
    });
}

// "Record a voice message": tap, speak, tap "I'm done". The recording goes
// to her Family screen as this family member's own voice.
var recordingVoice = false;
var VOICE_LIMIT_MS = 2 * 60 * 1000;
var voiceTimer = null;

function recordVoice() {
  var status = document.getElementById("reply-status");
  var label = document.getElementById("reply-voice-label");
  if (!recordingVoice) {
    startRecording()
      .then(function () {
        recordingVoice = true;
        label.textContent = "I’m done";
        status.textContent = "Recording… say a few words, then tap “I’m done”.";
        voiceTimer = setTimeout(recordVoice, VOICE_LIMIT_MS);
      })
      .catch(function () {
        status.textContent = "I can’t use the microphone here. Allow it at the top of the window, or write a message instead.";
      });
    return;
  }
  clearTimeout(voiceTimer);
  recordingVoice = false;
  label.textContent = "Record a voice message";
  status.textContent = "Sending your voice…";
  stopRecording()
    .then(function (wav) {
      var form = new FormData();
      form.append("audio", wav, "voice.wav");
      return fetch("/api/family/voice", { method: "POST", body: form }).then(function (response) {
        if (response.status === 401) {
          show("family-signin");
          throw new Error("signed out");
        }
        if (!response.ok) {
          throw new Error("refused");
        }
      });
    })
    .then(function () {
      status.textContent = "Sent. Buddy will play it to " + herName + ".";
      loadDay();
    })
    .catch(function () {
      status.textContent = "I couldn’t send that recording just now. Please try again, or write a message.";
    });
}

// A new message from her since the last look at today: a notification too.
function tellAboutNewMessages(lines) {
  if (shownMessages !== null && notifyWanted()) {
    lines.forEach(function (line) {
      if (shownMessages.indexOf(line) === -1) {
        var note = new Notification(herName + " sent a message", {
          body: line.replace(/^\S+ \S+ /, ""), tag: "buddy-message-" + line,
        });
        note.addEventListener("click", function () { window.focus(); note.close(); });
      }
    });
  }
  shownMessages = lines;
}

function showNotifySwitch() {
  var box = document.getElementById("notify-switch");
  var status = document.getElementById("notify-status");
  if (!("Notification" in window)) {
    box.disabled = true;
    status.textContent = "This browser can’t show notifications.";
    return;
  }
  box.checked = notifyWanted();
}

function changeNotify() {
  var box = document.getElementById("notify-switch");
  var status = document.getElementById("notify-status");
  if (!box.checked) {
    try { localStorage.setItem(NOTIFY_KEY, "off"); } catch (e) {}
    status.textContent = "";
    return;
  }
  Notification.requestPermission().then(function (permission) {
    if (permission === "granted") {
      try { localStorage.setItem(NOTIFY_KEY, "on"); } catch (e) {}
      status.textContent = "You’ll get a notification here when something new needs a look.";
    } else {
      box.checked = false;
      status.textContent = "Notifications are blocked for this page. Allow them in the browser’s settings, then try again.";
    }
  });
}

// ---------- Setting up ----------

function start() {
  document.getElementById("signin-form").addEventListener("submit", signIn);
  document.getElementById("reply-form").addEventListener("submit", reply);
  document.getElementById("reply-voice").addEventListener("click", recordVoice);
  document.getElementById("join-form").addEventListener("submit", join);
  document.getElementById("show-join").addEventListener("click", function () { show("family-join"); });
  document.getElementById("show-signin").addEventListener("click", function () { show("family-signin"); });
  document.getElementById("sign-out").addEventListener("click", signOut);
  document.querySelectorAll('input[name="family-day"]').forEach(function (choice) {
    choice.addEventListener("change", loadDay);
  });
  document.getElementById("notify-switch").addEventListener("change", changeNotify);
  document.getElementById("plan-start").addEventListener("click", startPlan);
  document.getElementById("plan-demo-start").addEventListener("click", startDemoPlan);
  document.getElementById("plan-demo-no").addEventListener("click", function () {
    document.getElementById("plan-demo").hidden = true;
    document.getElementById("plan-start").focus();
  });
  document.getElementById("plan-cancel").addEventListener("click", function () {
    document.getElementById("plan-cancel-ask").hidden = false;
    document.getElementById("plan-cancel-no").focus();
  });
  document.getElementById("plan-cancel-no").addEventListener("click", function () {
    document.getElementById("plan-cancel-ask").hidden = true;
    document.getElementById("plan-cancel").focus();
  });
  document.getElementById("plan-cancel-yes").addEventListener("click", cancelPlan);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && !document.getElementById("family-day").hidden) {
      loadDay(); // back to the page: fresh at once
    }
  });
  showNotifySwitch();
  document.getElementById("family-demo-signin").addEventListener("click", tryTheDemo);
  api("/api/family/me")
    .then(function (me) {
      if (me.signed_in) {
        showDay();
      } else {
        document.getElementById("family-demo").hidden = !(me.demo && me.demo_account);
        show("family-signin");
      }
    })
    .catch(function () { show("family-signin"); });
}

start();
