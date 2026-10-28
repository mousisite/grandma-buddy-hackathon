// Grandma Buddy: the page shell.
// Greets her (by name once the family has set it up), shows the date,
// grows the words on request (and remembers her choice), moves between
// screens (the router), opens the Menu on phones, and shows a kind note for
// features that aren't built yet. Talking lives in talk.js, the other
// screens in screens.js, reading aloud in speech.js, and recording in
// recorder.js.

"use strict";

// Her profile from /api/profile: names, phone numbers, voice settings.
var profile = { preferred_name: "", name: "", family_name: "", family_phone: "" };

// Ask our own server. Resolves with its answer. If the server says no,
// rejects with an error whose .detail says why (for example which entry
// on the Family form needs another look). If there is no connection,
// rejects with no .detail.
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

// Morning, afternoon, or evening, based on the real time, with her name
// when it is known. From 6 AM to 6 PM the page is light; otherwise dark.
function showGreeting() {
  var hour = new Date().getHours();
  var greeting = "Good evening";
  if (hour < 12) {
    greeting = "Good morning";
  } else if (hour < 18) {
    greeting = "Good afternoon";
  }
  var name = profile.preferred_name || profile.name;
  document.getElementById("greeting").textContent = name ? greeting + ", " + name : greeting;
  var isDay = hour >= 6 && hour < 18;
  document.documentElement.setAttribute("data-time", isDay ? "day" : "night");
  // Phones color their top bar to match the page.
  document.querySelector('meta[name="theme-color"]').content = isDay ? "#FFFFFF" : "#111216";
}

// Fill in the date line, like "Monday, October 26".
function showToday() {
  document.getElementById("today-date").textContent = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

// Use a freshly loaded or saved profile: greeting and voice settings.
function useProfile(saved) {
  profile = saved;
  voiceSettings.on = saved.voice_on !== false;
  voiceSettings.rate = saved.voice_rate || 0.9;
  showGreeting();
}

// Load her profile, then refresh the screen she is on (the Family screen
// shows the names and numbers).
function loadProfile() {
  return api("/api/profile")
    .then(function (saved) {
      useProfile(saved);
      loadScreen(currentScreen());
    })
    .catch(function () {
      // No connection to our own server: keep the simple greeting.
    });
}

// ---------- Screens (the router) ----------

// Each screen has its own address: #/diary, #/family… Today is #/ (or nothing).
var SCREEN_TITLES = {
  today: "Today",
  diary: "My diary",
  pills: "My pills",
  notes: "Doctor notes",
  scam: "Is this a scam?",
  family: "Family",
};

function currentScreen() {
  var name = location.hash.replace(/^#\/?/, "");
  return SCREEN_TITLES.hasOwnProperty(name) ? name : "today";
}

// Fill a screen with fresh information (SCREEN_LOADERS is in screens.js).
function loadScreen(name) {
  if (SCREEN_LOADERS[name]) {
    SCREEN_LOADERS[name]();
  }
}

// Show the screen named in the address and hide the others. When she moved
// there herself, start at the top with keyboard and screen-reader focus on
// the screen's heading, so she hears where she is.
function showScreen(moveFocus) {
  var name = currentScreen();
  // Leaving Today while Buddy is listening: finish up, so her words still
  // reach the safety net.
  if (name !== "today" && talkState === "listening") {
    finishTalking();
  }
  document.querySelectorAll("[data-screen]").forEach(function (screen) {
    screen.hidden = screen.getAttribute("data-screen") !== name;
  });
  document.querySelectorAll("[data-nav]").forEach(function (link) {
    if (link.getAttribute("data-nav") === name) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
  document.title = name === "today" ? "Grandma Buddy" : SCREEN_TITLES[name] + " · Grandma Buddy";
  closeMenu();
  loadScreen(name);
  if (moveFocus) {
    window.scrollTo(0, 0);
    document.querySelector('[data-screen="' + name + '"] h1').focus();
  }
}

// ---------- The Menu on phones and upright tablets ----------

// The sidebar slides in over the page. While it is open, the page behind it
// can't be reached (inert), so keyboard focus stays in the menu.
function openMenu() {
  document.getElementById("sidebar").setAttribute("data-open", "");
  document.getElementById("scrim").hidden = false;
  document.querySelector(".main").inert = true;
  document.getElementById("menu-button").setAttribute("aria-expanded", "true");
  document.querySelector(".side-item[aria-current]").focus();
}

function closeMenu() {
  document.getElementById("sidebar").removeAttribute("data-open");
  document.getElementById("scrim").hidden = true;
  document.querySelector(".main").inert = false;
  document.getElementById("menu-button").setAttribute("aria-expanded", "false");
}

// Closed with "Close", a tap beside it, or Escape: focus goes back to "Menu".
function closeMenuAndReturn() {
  closeMenu();
  document.getElementById("menu-button").focus();
}

// Restart a short CSS animation (see "Motion" in styles.css), so
// something new on screen gently eases in every time, not just the first.
function replay(element, className) {
  element.classList.remove(className);
  void element.offsetWidth; // makes the browser notice the class was removed
  element.classList.add(className);
}

// Show Buddy's words (screen readers announce them too). Each word gets
// its own span, so they appear one after another, like an AI answer.
// Long messages speed up so every message is fully shown within about
// 1.2 seconds, and urgent ones (options.instant) appear all at once.
function say(text, options) {
  var message = document.getElementById("message");
  message.textContent = "";
  // Short questions are shown very big; long messages a little smaller,
  // so the buttons under them stay on the screen.
  message.classList.toggle("long", text.split(" ").length > 12);
  if (options && options.instant) {
    message.textContent = text;
    return;
  }
  var words = text.split(" ");
  var step = Math.min(70, 1200 / words.length); // milliseconds between words
  words.forEach(function (word, index) {
    var span = document.createElement("span");
    span.className = "word";
    span.style.animationDelay = Math.round(index * step) + "ms";
    span.textContent = word;
    message.appendChild(span);
    message.appendChild(document.createTextNode(" "));
  });
}

function sayComingSoon(what) {
  say("“" + what + "” isn’t ready yet. It’s coming soon.");
}

// The words button cycles: normal -> big -> biggest -> normal.
var WORD_SIZES = [100, 115, 130];
var WORD_NAMES = ["normal", "big", "biggest"];
// The button always says what tapping it will do next.
// Labels are short so they fit on one line on a phone, even at biggest.
var WORD_GLYPHS = ["A+", "A+", "A−"];
var WORD_LABELS = ["Bigger words", "Even bigger", "Smaller words"];
var wordStep = 0;

function setWords(step) {
  wordStep = step;
  document.documentElement.style.fontSize = WORD_SIZES[step] + "%";
  document.getElementById("text-size-glyph").textContent = WORD_GLYPHS[step];
  document.getElementById("text-size-label").textContent = WORD_LABELS[step];
  // Remember her choice on this device. Some browsers block this
  // (private windows); then the words just start at normal next time.
  try {
    localStorage.setItem("words", String(step));
  } catch (e) {}
}

function growWords() {
  setWords((wordStep + 1) % WORD_SIZES.length);
  say("The words are now " + WORD_NAMES[wordStep] + ".");
}

// Start with the size she chose last time, if there is one.
function loadWords() {
  var saved = 0;
  try {
    saved = Number(localStorage.getItem("words"));
  } catch (e) {}
  if (WORD_SIZES[saved]) {
    setWords(saved);
  }
}

function start() {
  showGreeting();
  showToday();
  loadWords();
  loadProfile();
  // Buddy's first question appears word by word when the app opens.
  say(document.getElementById("message").textContent);

  startTalking(); // talk.js
  startScreens(); // screens.js

  // Show the screen in the address (Today when there is none), and follow
  // every change after that, including the browser's Back button.
  showScreen(false);
  window.addEventListener("hashchange", function () {
    showScreen(true);
  });

  document.getElementById("skip-link").addEventListener("click", function () {
    document.querySelector('[data-screen="' + currentScreen() + '"] h1').focus();
  });
  document.getElementById("menu-button").addEventListener("click", openMenu);
  document.getElementById("menu-close").addEventListener("click", closeMenuAndReturn);
  document.getElementById("scrim").addEventListener("click", closeMenuAndReturn);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && document.getElementById("sidebar").hasAttribute("data-open")) {
      closeMenuAndReturn();
    }
  });
  // A tablet turned sideways shows the sidebar for good: close the drawer
  // so the page behind it can be used again.
  matchMedia("(min-width: 1000px)").addEventListener("change", closeMenu);

  document.querySelectorAll("[data-coming-soon]").forEach(function (button) {
    button.addEventListener("click", function () {
      sayComingSoon(button.getAttribute("data-coming-soon"));
    });
  });

  document.getElementById("text-size-button").addEventListener("click", growWords);
}

// Start right away. This script sits at the end of <body>, so the page above
// it is already there, and the page shows the right time of day from the
// very first frame (no bright flash at night).
start();
