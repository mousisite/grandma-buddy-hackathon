// Grandma Buddy: the page shell.
// Greets her (by name once the family has set it up), shows the date, sets
// the theme (Auto, Light, or Dark) and the text size, turns on Calm motion,
// and moves between screens (the router) with a soft cross-fade, or the
// orb morphing into voice mode. Buddy's orb lives in buddy.js, talking in
// talk.js, the other screens in screens.js, reading aloud in speech.js,
// and recording in recorder.js.

"use strict";

// Her profile from /api/profile: names, phone numbers, voice settings,
// Calm motion, the chime, and the theme.
var profile = { preferred_name: "", name: "", family_name: "", family_phone: "", calm_mode: false, chime: false, theme: "" };

// Ask our own server. Resolves with its answer. If the server says no,
// rejects with an error whose .detail says why (for example which entry
// on a form needs another look). If there is no connection, rejects with
// no .detail.
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
        throw refused;
      }
      return answer;
    });
  });
}

// Remember a choice on this device. Some browsers block this (private
// windows); then the choice just isn't remembered.
function remember(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (e) {}
}

function remembered(key) {
  try {
    return localStorage.getItem(key);
  } catch (e) {
    return null;
  }
}

// ---------- The time of day ----------

// Morning 5:00 to 11:59, afternoon 12:00 to 16:59, evening 17:00 to 20:59,
// night 21:00 to 4:59 (at night the greeting is still "Good evening").
function partOfDay(date) {
  var hour = date.getHours();
  if (hour >= 5 && hour < 12) {
    return "morning";
  }
  if (hour >= 12 && hour < 17) {
    return "afternoon";
  }
  return hour >= 17 && hour < 21 ? "evening" : "night";
}

// "Good afternoon, Rose" (or just "Good afternoon" when no name is set up).
function showGreeting() {
  var part = partOfDay(new Date());
  var greeting = "Good " + (part === "night" ? "evening" : part);
  var name = profile.preferred_name || profile.name;
  setText(document.getElementById("greeting"), name ? greeting + ", " + name : greeting);
}

// "Wednesday, October 28"
function showToday() {
  var date = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  setText(document.getElementById("today-date"), date);
}

// ---------- Theme ----------

// Auto follows the computer's light or dark setting. If the computer says
// neither, it is dark from 7 PM to 7 AM. The page head already set the
// theme before the first paint (index.html); this keeps it right after.
var computerWantsDark = matchMedia("(prefers-color-scheme: dark)");
var computerWantsLight = matchMedia("(prefers-color-scheme: light)");

function themeChoice() {
  return profile.theme || remembered("theme") || "auto";
}

function applyTheme() {
  var choice = themeChoice();
  var dark = choice === "dark";
  if (choice === "auto") {
    var hour = new Date().getHours();
    dark = computerWantsDark.matches || (!computerWantsLight.matches && (hour >= 19 || hour < 7));
  }
  var theme = dark ? "dark" : "light";
  var page = document.documentElement;
  if (page.getAttribute("data-theme") !== theme) {
    page.setAttribute("data-theme", theme);
  }
  document.querySelector('meta[name="theme-color"]').setAttribute("content", dark ? "#131211" : "#F7F7F5");
  remember("theme", choice);
}

// ---------- Text size ----------

// Standard, Large, Largest (Settings). Everything is sized in rem, so the
// whole app grows together. It starts at Large, so it is easy to read from
// the first visit. Remembered on this device; the page head sets it before
// the first paint.
var WORD_SIZES = [100, 118, 135];

function wordStep() {
  var saved = remembered("words");
  var step = saved === null ? 1 : Number(saved);
  return WORD_SIZES[step] ? step : 0;
}

function setWords(step) {
  document.documentElement.style.fontSize = WORD_SIZES[step] + "%";
  remember("words", String(step));
}

// ---------- Calm motion ----------

// No movement anywhere (styles.css, the end). On when she turns it on in
// Settings, or when the computer asks for reduced motion.
var computerWantsLessMotion = matchMedia("(prefers-reduced-motion: reduce)");

function isCalm() {
  return profile.calm_mode === true || computerWantsLessMotion.matches;
}

function applyCalm() {
  document.documentElement.toggleAttribute("data-calm", isCalm());
}

// Use a freshly loaded or saved profile: greeting, voice, theme, Calm motion.
function useProfile(saved) {
  profile = saved;
  voiceSettings.on = saved.voice_on !== false;
  voiceSettings.rate = saved.voice_rate || 0.9;
  showGreeting();
  applyTheme();
  applyCalm();
}

// Load her profile, then refresh the screen she is on (Family and
// Settings show the names and numbers).
function loadProfile() {
  return api("/api/profile")
    .then(function (saved) {
      useProfile(saved);
      if (!saved.preferred_name && !saved.name) {
        location.hash = "#/welcome"; // the first time: Buddy says hello and sets her up
      }
      loadScreen(currentScreen());
    })
    .catch(function () {
      // No connection to our own server: keep the simple greeting.
    });
}

// ---------- Screens (the router) ----------

// Each screen has its own address: #/talk, #/pills… Home is #/ (or nothing).
var SCREEN_TITLES = {
  today: "Home",
  talk: "Talk with Buddy",
  diary: "My diary",
  pills: "My pills",
  notes: "Doctor notes",
  scam: "Check a message",
  family: "Family",
  memories: "Memory book",
  memory: "Memory book", // one page: #/memory/3
  find: "Find my things", // #/find/glasses fills in what she's looking for (find.js)
  read: "Read it to me", // a photo of a letter, a bill, or a form (read.js)
  settings: "Settings",
  help: "Help", // how Buddy works, privacy, questions
  welcome: "Welcome", // the first time, while no name is saved (welcome.js)
};

function currentScreen() {
  var name = location.hash.replace(/^#\/?/, "").split("/")[0];
  return SCREEN_TITLES.hasOwnProperty(name) ? name : "today";
}

// What comes after the screen's name: "3" in #/memory/3.
function screenDetail() {
  return location.hash.replace(/^#\/?/, "").split("/")[1] || "";
}

// Fill a screen with fresh information (SCREEN_LOADERS is in screens.js).
function loadScreen(name) {
  if (SCREEN_LOADERS[name]) {
    SCREEN_LOADERS[name]();
  }
}

// Change what is on screen with a View Transition: the old screen fades,
// the new one rises 8px into place, and the orb morphs between Home and
// voice mode (styles.css). Browsers without View Transitions, and Calm
// motion, just switch.
function changeScreen(update) {
  if (!document.startViewTransition || isCalm()) {
    update();
    return;
  }
  document.startViewTransition(update);
}

// Show the screen named in the address and hide the others. When she moved
// there herself, start at the top with keyboard and screen-reader focus on
// the screen's heading, so she hears where she is.
function showScreen(moveFocus) {
  var name = currentScreen();
  // Leaving voice mode while Buddy is listening: finish up, so her words
  // still reach the safety net.
  if (name !== "talk" && talkState === "listening") {
    finishTalking();
  }
  // Leaving voice mode stops hands-free listening (the microphone goes off).
  if (name !== "talk") {
    stopHandsFree();
  }
  // Leaving voice mode ends a "Something hurts" talk or the check-in
  // (unless her last words are still on their way, which belong to it).
  if (name !== "talk" && talkMode !== "chat" && talkState === "idle") {
    backToChat();
  }
  document.querySelectorAll("section[data-screen]").forEach(function (screen) {
    screen.hidden = screen.getAttribute("data-screen") !== name;
  });
  // The tab bar and sidebar show where she is (a memory page is in the
  // Memory book; on a phone, Help is under Settings: data-nav-also).
  var place = name === "memory" ? "memories" : name;
  document.querySelectorAll("[data-nav]").forEach(function (link) {
    if (link.getAttribute("data-nav") === place || link.getAttribute("data-nav-also") === place) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
  document.documentElement.setAttribute("data-view", name);
  document.title = name === "today" ? "Grandma Buddy" : SCREEN_TITLES[name] + " · Grandma Buddy";
  setBuddyState(buddyState); // a newly shown orb picks up Buddy's state
  loadScreen(name);
  if (moveFocus) {
    document.documentElement.setAttribute("data-moved", "");
    window.scrollTo(0, 0);
    document.querySelector('[data-screen="' + name + '"] h1').focus();
  }
}

// Show Buddy's words in voice mode (screen readers announce them too).
// Each word gets its own span: the words stream in one after another, and
// light up as each is read aloud (talk.js).
function say(text) {
  var message = document.getElementById("message");
  message.textContent = "";
  message.setAttribute("data-text", text);
  message.classList.remove("fresh", "reading");
  // Short answers are shown very big; long ones a little smaller.
  message.classList.toggle("long", text.split(" ").length > 12);
  text.split(" ").forEach(function (word, index) {
    if (index > 0) {
      message.appendChild(document.createTextNode(" "));
    }
    var span = document.createElement("span");
    span.className = "word";
    span.style.setProperty("--i", index);
    span.textContent = word;
    message.appendChild(span);
  });
  if (text) {
    void message.offsetWidth; // makes the browser start the stream again
    message.classList.add("fresh");
  }
}

// ---------- Pressing ----------

// Every press shows the moment it lands: the button squeezes and darkens a
// little (data-pressed, styles.css "Pressing"), and a circle of light
// spreads from the spot she touched. Calm motion keeps only the color.
var PRESSABLE = ".pill-button, .text-button, .chip, .tab, .nav-link, .row-link, .call-pill, .check, .for-family-summary, .memory-card, .segmented label, label.group-row, .row--link, .faq-question";

function showPress(event) {
  var target = event.target.closest(PRESSABLE);
  if (!target || target.disabled || event.button > 0) {
    return;
  }
  target.setAttribute("data-pressed", "");
  if (isCalm()) {
    return;
  }
  var box = target.getBoundingClientRect();
  var size = Math.max(box.width, box.height) * 2;
  var ripple = document.createElement("span");
  ripple.className = "ripple";
  ripple.setAttribute("aria-hidden", "true");
  ripple.style.width = ripple.style.height = size + "px";
  ripple.style.left = event.clientX - box.left - size / 2 + "px";
  ripple.style.top = event.clientY - box.top - size / 2 + "px";
  target.appendChild(ripple);
  setTimeout(function () { ripple.remove(); }, 700);
}

// The finger lifted (or slid away to scroll): let go, a moment later, so
// even a very quick tap is seen.
function endPress() {
  document.querySelectorAll("[data-pressed]").forEach(function (pressed) {
    setTimeout(function () { pressed.removeAttribute("data-pressed"); }, 140);
  });
}

function start() {
  applyTheme();
  applyCalm();
  computerWantsLessMotion.addEventListener("change", applyCalm);
  computerWantsDark.addEventListener("change", applyTheme);
  startBuddy(); // buddy.js: Buddy wakes up
  showGreeting();
  showToday();
  // The greeting, the date, and Auto's evening switch follow the clock.
  setInterval(function () {
    showGreeting();
    showToday();
    applyTheme();
  }, 60 * 1000);
  loadProfile();
  say(document.getElementById("message").textContent);

  startTalking(); // talk.js
  startScreens(); // screens.js

  // Pill reminders: check now and every 30 seconds while the app is open.
  loadReminders();
  setInterval(loadReminders, 30 * 1000);
  startDemoReminder(); // only with ?demo=reminder in the address (screens.js)

  // Show the screen in the address (Home when there is none), and follow
  // every change after that, including the browser's Back button.
  showScreen(false);
  window.addEventListener("hashchange", function () {
    changeScreen(function () {
      showScreen(true);
    });
  });

  document.addEventListener("pointerdown", showPress);
  document.addEventListener("pointerup", endPress);
  document.addEventListener("pointercancel", endPress);

  document.getElementById("skip-link").addEventListener("click", function () {
    document.querySelector('[data-screen="' + currentScreen() + '"] h1').focus();
  });
}

// Start right away. This script sits at the end of <body>, so the page
// above it is already there.
start();
