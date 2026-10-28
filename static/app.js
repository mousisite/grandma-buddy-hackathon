// Grandma Buddy: the page shell.
// Greets her (by name once the family has set it up), shows the date,
// grows the words on request (and remembers her choice), and shows a kind
// note for features that aren't built yet. Talking lives in talk.js,
// reading aloud in speech.js, and recording in recorder.js.

"use strict";

// Her profile from /api/profile: names, phone numbers, voice settings.
var profile = { preferred_name: "", name: "", family_name: "", family_phone: "" };

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

// Load her profile, then update the greeting and voice settings.
function loadProfile() {
  return fetch("/api/profile")
    .then(function (response) {
      return response.ok ? response.json() : profile;
    })
    .then(function (saved) {
      profile = saved;
      voiceSettings.on = saved.voice_on !== false;
      voiceSettings.rate = saved.voice_rate || 0.9;
      showGreeting();
    })
    .catch(function () {
      // No connection to our own server: keep the simple greeting.
    });
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

  // She is already on Today: the Today button just goes back to the top.
  document.getElementById("home-tab").addEventListener("click", function () {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

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
