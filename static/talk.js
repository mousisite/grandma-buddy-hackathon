// Grandma Buddy: talking.
// Tap the voice box once to start, again when done (no holding down).
// Her voice becomes text (/api/transcribe), then goes to /api/chat, where
// the safety net checks it first. If the safety net answers, a full-screen
// safety screen appears with big call buttons. Recording lives in
// recorder.js and reading aloud in speech.js.

"use strict";

var TALK_LIMIT_MS = 2 * 60 * 1000; // recording stops by itself after 2 minutes
var TALK_LABELS = { idle: "Tap to talk", listening: "Tap when you’re done", working: "One moment…" };
var talkState = "idle"; // "idle", "listening", or "working"
var talkTimer = null;
var talkMode = "chat"; // "chat", "check_in", or "diary"

// One conversation per day, so each day's talk is kept together.
function conversationId() {
  var today = new Date();
  return today.getFullYear() + "-" + (today.getMonth() + 1) + "-" + today.getDate();
}

function setTalkState(state) {
  talkState = state;
  document.getElementById("talk-button").setAttribute("data-state", state);
  document.getElementById("talk-label").textContent = TALK_LABELS[state];
  // While listening, the rest of the screen steps back (see styles.css).
  document.documentElement.setAttribute("data-talk", state);
  if (state === "listening") {
    requestAnimationFrame(showVoiceLevel);
  }
}

// The voice level: about 60 times a second while she talks, set --level
// from how loud she is (voiceLevel() in recorder.js). The bars in the voice
// button and the glow behind the voice box follow it. Smoothed so they
// move gently instead of jittering.
var shownLevel = 0;

function showVoiceLevel() {
  var page = document.documentElement;
  if (talkState !== "listening") {
    shownLevel = 0;
    page.style.setProperty("--level", "0");
    return;
  }
  shownLevel = shownLevel * 0.7 + voiceLevel() * 0.3;
  page.style.setProperty("--level", shownLevel.toFixed(3));
  requestAnimationFrame(showVoiceLevel);
}

// A named problem, so talkProblem() can pick the right kind words.
function problem(name) {
  var error = new Error(name);
  error.name = name;
  return error;
}

function onTalkTap() {
  if (talkState === "idle") {
    // Stop Buddy talking first, so the microphone never hears Buddy's voice.
    stopSpeaking();
    setTalkState("working"); // ignore extra taps while the microphone opens
    startRecording()
      .then(function () {
        setTalkState("listening");
        say("Listening…");
        talkTimer = setTimeout(finishTalking, TALK_LIMIT_MS);
      })
      .catch(function (reason) {
        talkProblem(reason);
        setTalkState("idle");
      });
  } else if (talkState === "listening") {
    finishTalking();
  }
  // While "working", extra taps do nothing.
}

function finishTalking() {
  clearTimeout(talkTimer);
  setTalkState("working");
  say("Writing down what you said…");
  stopRecording()
    .then(sendForTranscript)
    .then(function (result) {
      if (!result.transcript) {
        throw problem("NotHeard");
      }
      showYouSaid(result.transcript);
      say("Let me think…"); // shimmers while Buddy works (see styles.css)
      return askBuddy(result.transcript);
    })
    .catch(talkProblem)
    .then(function () {
      setTalkState("idle");
    });
}

// Send the recording to our server, which asks Meta's speech-to-text.
function sendForTranscript(wav) {
  var form = new FormData();
  form.append("audio", wav, "speech.wav");
  return fetch("/api/transcribe", { method: "POST", body: form })
    .catch(function () {
      throw problem("Offline");
    })
    .then(function (response) {
      if (!response.ok) {
        throw problem("NotHeard");
      }
      return response.json();
    });
}

// Send her words to Buddy. The safety net answers first if it needs to.
function askBuddy(text) {
  return fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId(), text: text, mode: talkMode }),
  })
    .catch(function () {
      throw problem("Offline");
    })
    .then(function (response) {
      if (!response.ok) {
        throw problem("NotHeard");
      }
      return response.json();
    })
    .then(function (answer) {
      if (answer.show) {
        openSafetyScreen(answer.show, answer.reply, answer.actions);
      } else {
        say(answer.reply);
        speak(answer.reply);
        showActions(answer.actions || []);
      }
    });
}

// Her words arrived: show them in her bubble, and the voice button nods.
function showYouSaid(text) {
  var card = document.getElementById("you-said");
  document.getElementById("you-said-text").textContent = text;
  card.hidden = false;
  replay(card, "fresh");
  var talkButton = document.getElementById("talk-button");
  replay(talkButton, "heard");
  setTimeout(function () {
    talkButton.classList.remove("heard");
  }, 1600);
}

// ---------- Call buttons ----------

// Only phone and text-message links are ever made into buttons.
function isCallLink(href) {
  return /^(tel|sms):[0-9+()\-. ]+$/.test(href);
}

function callLink(action, className) {
  var link = document.createElement("a");
  link.className = className;
  link.href = action.href;
  link.textContent = action.label;
  return link;
}

// Buttons under Buddy's words: call buttons, "Add to doctor notes", and
// "Open …" (when she asks for a part of the app by voice).
function showActions(actions) {
  var row = document.getElementById("actions");
  row.textContent = "";
  actions.forEach(function (action) {
    if (action.type === "add_question") {
      row.appendChild(addQuestionButton(action));
    } else if (action.type === "open") {
      var open = document.createElement("button");
      open.type = "button";
      open.className = "call-pill call-pill--quiet";
      open.textContent = action.label;
      open.addEventListener("click", function () {
        openScreen(action.screen);
      });
      row.appendChild(open);
    } else if (isCallLink(action.href)) {
      row.appendChild(callLink(action, "call-pill"));
    }
  });
  row.hidden = row.children.length === 0;
}

// "Add to doctor notes": saves her question for her next visit.
function addQuestionButton(action) {
  var button = document.createElement("button");
  button.type = "button";
  button.className = "call-pill call-pill--quiet";
  button.textContent = action.label;
  button.addEventListener("click", function () {
    button.disabled = true;
    fetch("/api/doctor-questions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: action.question }),
    })
      .then(function (response) {
        if (!response.ok) {
          throw problem("NotSaved");
        }
        button.textContent = "Added to doctor notes ✓";
        say("I added that to your doctor notes.");
        speak("I added that to your doctor notes.");
      })
      .catch(function () {
        button.disabled = false;
        say("I couldn’t save that just now. Please tap it again.");
      });
  });
  return button;
}

// Opening another part of the app (the screens arrive in the next step).
function openScreen(screen) {
  sayComingSoon(screen === "notes" ? "Doctor notes" : screen.charAt(0).toUpperCase() + screen.slice(1));
}

// Call 911, and family if their number is set up. Used when the internet
// is down, because then her words can't reach the safety net.
function emergencyCallActions() {
  var actions = [{ label: "Call 911", href: "tel:911" }];
  if (profile.family_phone) {
    actions.push({ label: "Call " + (profile.family_name || "family"), href: "tel:" + profile.family_phone });
  }
  return actions;
}

// ---------- Safety screens ----------

var SAFETY_TITLES = {
  emergency: "Emergency",
  poison_control: "Poison Control",
  crisis: "You are not alone",
};

// A full-screen message with big call buttons, read aloud. It stays until
// she taps "Go back" (it never closes by itself).
function openSafetyScreen(kind, message, actions) {
  var screen = document.getElementById("safety-screen");
  screen.setAttribute("data-kind", kind);
  document.getElementById("safety-title").textContent = SAFETY_TITLES[kind] || "Help";
  document.getElementById("safety-message").textContent = message;
  var buttons = document.getElementById("safety-actions");
  buttons.textContent = "";
  actions.filter(function (a) { return isCallLink(a.href); }).forEach(function (action) {
    buttons.appendChild(callLink(action, "call-big"));
  });
  if (!screen.open) {
    screen.showModal();
  }
  safetySpeaking = true;
  speak(message, { safety: true });
  // Behind the screen, Buddy's words and the call buttons stay too,
  // shown all at once (urgent words never stream in slowly).
  say(message, { instant: true });
  showActions(actions);
}

// After "Go back", she lands on Buddy's words with the call buttons still
// there, and keyboard focus on the first call button.
function closeSafetyScreen() {
  safetySpeaking = false;
  stopSpeaking();
  document.getElementById("safety-screen").close();
  document.getElementById("message").scrollIntoView({ block: "center" });
  var firstCall = document.querySelector("#actions a");
  (firstCall || document.getElementById("talk-button")).focus({ preventScroll: true });
}

// Kind words for each thing that can go wrong. Never technical words.
// Whatever went wrong, Call 911 and Call family appear too: if her words
// can't reach the safety net (no internet, no microphone, words not
// understood, which can happen when someone is gasping or slurring), she
// still has help one tap away.
function talkProblem(reason) {
  var name = reason && reason.name;
  if (name === "NotAllowedError" || name === "SecurityError") {
    say("I can’t hear you yet. At the top of the window, click the microphone or lock picture, choose Allow, then tap the voice box again. If you need help now, call below.");
  } else if (name === "NotFoundError" || name === "NotReadableError") {
    say("I can’t find a microphone. Please check that it’s plugged in and turned on. If you need help now, call below.");
  } else if (name === "Offline") {
    say("I can’t reach the internet right now. If you need help, call below.");
  } else {
    say("I didn’t catch that. Tap the voice box and try again. If you need help now, call below.");
  }
  showActions(emergencyCallActions());
}

function startTalking() {
  document.getElementById("talk-button").addEventListener("click", onTalkTap);
  document.getElementById("safety-close").addEventListener("click", closeSafetyScreen);
  document.getElementById("safety-again").addEventListener("click", sayAgain);
  document.getElementById("say-again").addEventListener("click", sayAgain);
  // The Escape key closes a dialog by itself; keep speech in step with it.
  document.getElementById("safety-screen").addEventListener("close", function () {
    safetySpeaking = false;
  });
}
