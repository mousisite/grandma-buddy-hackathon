// Grandma Buddy: the first-time welcome (docs/DESIGN.md, "Welcome").
// While no name is saved, the app opens here (app.js). Three steps: her
// name, one or two people she loves, and her pills now or later. Each can be
// typed, or said with "Say it": what she says goes through the safety net
// first (/api/check-words), never to the AI, then fills the fields, which
// she can correct. Buddy reads each question aloud (after her first tap:
// browsers stay silent until then, which is what "Let's begin" is for).

"use strict";

var WELCOME_STEPS = [
  { title: "Hello! I’m Buddy.",
    words: "I’m an AI helper here to keep you company, remind you about your pills, and help you stay close to your family.",
    spoken: "" },
  { title: "What should I call you?",
    words: "Type your name, or tap “Say it” and tell me.",
    spoken: "Hello! I'm Buddy. What should I call you?" },
  { title: "Who should I call when you’d like to talk to someone?",
    words: "One or two people you love, with their phone numbers. Type them, or tap “Say it”.",
    spoken: "Lovely to meet you, {name}! Who should I call when you'd like to talk to someone?" },
  { title: "Would you like to set up your pills now?",
    words: "I can remind you when it’s time for each one. A family member can help with this, now or later.",
    spoken: "Would you like to set up your pills now? A family member can help, now or later." },
];
var SAY_IT_WORDS = { idle: "Say it", listening: "I’m done", working: "One moment…" };
var SAY_IT_LIMIT_MS = 20 * 1000; // she can say a name and a number in this
var welcomeStep = 0;
var sayingIt = null; // the "Say it" button that is listening
var sayItTimer = null;

// The screen loader (screens.js): show the step she is on.
function showWelcome() {
  showWelcomeStep(welcomeStep, false);
}

function showWelcomeStep(step, speakIt) {
  welcomeStep = step;
  var shown = WELCOME_STEPS[step];
  setText(document.getElementById("welcome-title"), shown.title);
  setText(document.getElementById("welcome-words"), shown.words);
  document.querySelectorAll(".welcome-step").forEach(function (part) {
    part.hidden = Number(part.getAttribute("data-step")) !== step;
  });
  document.querySelectorAll("[data-dot]").forEach(function (dot) {
    var number = Number(dot.getAttribute("data-dot"));
    dot.toggleAttribute("data-done", number <= step);
    if (number === step) {
      dot.setAttribute("aria-current", "step");
    } else {
      dot.removeAttribute("aria-current");
    }
  });
  document.getElementById("welcome-status").textContent = "";
  if (speakIt && shown.spoken) {
    speak(shown.spoken.replace("{name}", profile.preferred_name || profile.name || "you"));
  }
  document.getElementById("welcome-title").focus(); // screen readers hear the new question
}

// A refused entry is marked under its field, saying how to fix it.
function welcomeProblem(form, problem) {
  var detail = problem.detail || {};
  var input = detail.field && form.elements[detail.field];
  if (input) {
    showProblem(input, detail.message);
  } else {
    document.getElementById("welcome-status").textContent = "I couldn’t save that just now. Please try again.";
  }
}

function saveName(event) {
  event.preventDefault();
  var form = event.target;
  var input = form.elements.preferred_name;
  clearProblem(form);
  if (!input.value.trim()) {
    showProblem(input, "Please type your name, or tap “Say it” and tell me.");
    return;
  }
  api("/api/profile", "PUT", { preferred_name: input.value.trim() })
    .then(function (saved) {
      useProfile(saved); // Home will say "Good evening, Rose"
      showWelcomeStep(2, true);
    })
    .catch(function (problem) { welcomeProblem(form, problem); });
}

function saveFamily(event) {
  event.preventDefault();
  var form = event.target;
  clearProblem(form);
  var changes = {};
  ["family_name", "family_phone", "family2_name", "family2_phone"].forEach(function (field) {
    changes[field] = form.elements[field].value.trim();
  });
  api("/api/profile", "PUT", changes)
    .then(function (saved) {
      useProfile(saved);
      showWelcomeStep(3, true);
    })
    .catch(function (problem) { welcomeProblem(form, problem); });
}

// The last step: set up pills now (Pills, with "Set up pills" open), or Home.
function finishWelcome(withPills) {
  stopSpeaking();
  if (withPills) {
    document.getElementById("pills-setup").open = true;
    location.hash = "#/pills";
  } else {
    location.hash = "#/";
  }
}

// ---------- "Say it" ----------

// Busy, never disabled: disabling a button she just tapped would drop
// keyboard focus and leave its pressed look stuck.
function setSayIt(button, state) {
  button.setAttribute("data-state", state);
  button.setAttribute("aria-disabled", String(state === "working"));
  button.querySelector("span").textContent = SAY_IT_WORDS[state];
  setBuddyState(state === "listening" ? "listening" : state === "working" ? "thinking" : "idle");
}

function sayIt(button) {
  if (button.getAttribute("data-state") === "working") {
    return; // still working out what she said
  }
  if (sayingIt) {
    stopSayingIt();
    return;
  }
  stopSpeaking(); // the microphone never hears Buddy
  sayingIt = button;
  setSayIt(button, "listening");
  startRecording()
    .then(function () {
      sayItTimer = setTimeout(stopSayingIt, SAY_IT_LIMIT_MS);
    })
    .catch(function (reason) {
      sayingIt = null;
      setSayIt(button, "idle");
      var blocked = reason && (reason.name === "NotAllowedError" || reason.name === "SecurityError");
      document.getElementById("welcome-status").textContent = blocked
        ? "I can’t hear you yet. Allow the microphone at the top of the window, or type it instead."
        : "I can’t find a microphone. You can type it instead.";
    });
}

function stopSayingIt() {
  clearTimeout(sayItTimer);
  var button = sayingIt;
  sayingIt = null;
  setSayIt(button, "working");
  stopRecording()
    .then(sendForTranscript)
    .then(function (result) {
      var words = (result.transcript || "").trim();
      if (!words) {
        throw problem("NotHeard");
      }
      // The safety net first, like everything she says to Buddy.
      return api("/api/check-words", "POST", { text: words }).then(function (answer) {
        if (answer.show) {
          openSafetyScreen(answer.show, answer.reply, answer.actions);
        } else {
          fillFromWords(button.form, words);
        }
      });
    })
    .catch(function () {
      document.getElementById("welcome-status").textContent = "I didn’t catch that. Please try again, or type it.";
    })
    .then(function () {
      setSayIt(button, "idle");
    });
}

function capitalized(word) {
  return word.charAt(0).toUpperCase() + word.slice(1);
}

// "My name is Rose" -> "Rose"
function heardName(words) {
  var name = words.replace(/[.,!?]/g, " ").trim()
    .replace(/^(hi|hello|well|oh)\s+/i, "")
    .replace(/^(my name is|my name's|you can call me|call me|i'm|i am|it's|it is|this is)\s+/i, "");
  return name.split(/\s+/).filter(Boolean).slice(0, 3).map(capitalized).join(" ");
}

// "My son Daniel, 555 0144" -> { name: "Daniel", phone: "555 0144" }
var NOT_A_NAME = /\b(my|daughter|son|grandson|granddaughter|sister|brother|niece|nephew|friend|neighbor|her|his|name|is|number|phone|and|it's|at|call|the)\b/gi;

function heardPerson(words) {
  var number = words.match(/\+?\d[\d\s().-]{2,}\d/);
  var before = number ? words.slice(0, number.index) : words;
  var name = before.replace(/[.,!?]/g, " ").replace(NOT_A_NAME, " ").trim()
    .split(/\s+/).filter(Boolean).slice(0, 2).map(capitalized).join(" ");
  return { name: name, phone: number ? number[0].replace(/\s+/g, " ").trim() : "" };
}

// What she said, into the step's fields (the first empty person, on the family step).
function fillFromWords(form, words) {
  if (form.id === "welcome-name-form") {
    form.elements.preferred_name.value = heardName(words);
    return;
  }
  var person = heardPerson(words);
  var prefix = form.elements.family_name.value.trim() ? "family2" : "family";
  form.elements[prefix + "_name"].value = person.name;
  form.elements[prefix + "_phone"].value = person.phone;
}

function startWelcome() {
  document.getElementById("welcome-begin").addEventListener("click", function () { showWelcomeStep(1, true); });
  document.getElementById("welcome-name-form").addEventListener("submit", saveName);
  document.getElementById("welcome-family-form").addEventListener("submit", saveFamily);
  document.querySelectorAll("[data-say-it]").forEach(function (button) {
    button.addEventListener("click", function () { sayIt(button); });
  });
  document.querySelectorAll("[data-welcome-back]").forEach(function (button) {
    button.addEventListener("click", function () { showWelcomeStep(welcomeStep - 1, false); });
  });
  document.querySelector("[data-welcome-skip]").addEventListener("click", function () { showWelcomeStep(3, true); });
  document.getElementById("welcome-pills").addEventListener("click", function () { finishWelcome(true); });
  document.getElementById("welcome-later").addEventListener("click", function () { finishWelcome(false); });
  SCREEN_LOADERS.welcome = showWelcome;
}

startWelcome();
