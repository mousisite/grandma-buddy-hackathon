// Grandma Buddy: "Say it" buttons, for answering a form by voice (the
// welcome, and "What are you looking for?" in Find my things).
//
// Tap once to talk, tap again when done. What she says is written down
// (/api/transcribe), then goes through the safety net first
// (/api/check-words), never to the AI. If it needs a safety screen, that
// opens; otherwise her words go into the form, where she can correct them.
//
// In the page: <button data-say-it="welcome-status"> inside a form, where
// "welcome-status" is the line that says what went wrong. Each form says
// what to do with her words: SAY_IT_FILL["welcome-name-form"] = function (form, words) {…}.

"use strict";

var SAY_IT_FILL = {};
var SAY_IT_WORDS = { idle: "Say it", listening: "I’m done", working: "One moment…" };
var SAY_IT_LIMIT_MS = 20 * 1000; // she can say a name and a number in this
var sayingIt = null; // the "Say it" button that is listening
var sayItTimer = null;

function sayItStatus(button, words) {
  document.getElementById(button.getAttribute("data-say-it")).textContent = words;
}

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
      sayItStatus(button, blocked
        ? "I can’t hear you yet. Allow the microphone at the top of the window, or type it instead."
        : "I can’t find a microphone. You can type it instead.");
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
          sayItStatus(button, "");
          SAY_IT_FILL[button.form.id](button.form, words);
        }
      });
    })
    .catch(function () {
      sayItStatus(button, "I didn’t catch that. Please try again, or type it.");
    })
    .then(function () {
      setSayIt(button, "idle");
    });
}

document.querySelectorAll("[data-say-it]").forEach(function (button) {
  button.addEventListener("click", function () { sayIt(button); });
});
