// Grandma Buddy: Buddy, the living orb.
// A ball of warm light with no face: four soft color blobs (amber, peach,
// rose, violet) drift inside a circle, with a glow around it (styles.css,
// "Buddy, the orb"). It shows what it is doing with its light, and in words
// under it in voice mode:
//   idle       it breathes slowly; the colors flow over about 12 seconds
//   listening  it brightens and swells gently with her voice
//              ("I'm listening")
//   thinking   the colors flow faster and a soft light sweeps around
//              ("Let me think…")
//   speaking   it lifts softly with each spoken word
// setBuddyState() is the only way to change it, so every orb on the page
// always shows the same thing.

"use strict";

var BUDDY_LABELS = {
  idle: "",
  listening: "I’m listening",
  thinking: "Let me think…",
  speaking: "",
};
// How fast the colors flow in each state (1 is the slow, calm idle flow).
var BUDDY_FLOW = { idle: 1, listening: 1.6, thinking: 3, speaking: 1.8 };
var buddyState = "idle";
var lastPulse = 0;
var speakingTimer = null;

var ORB_PARTS =
  '<span class="orb-glow" aria-hidden="true"></span>' +
  '<span class="orb-core" aria-hidden="true">' +
  '<span class="orb-flow">' +
  '<span class="orb-blob orb-blob--amber"></span>' +
  '<span class="orb-blob orb-blob--peach"></span>' +
  '<span class="orb-blob orb-blob--rose"></span>' +
  '<span class="orb-blob orb-blob--violet"></span>' +
  "</span>" +
  '<span class="orb-swirl"></span>' +
  '<span class="orb-shine"></span>' +
  "</span>";

// Fill every orb on the page (Home and voice mode). It wakes up once, as
// the app opens (styles.css "orb-wake").
function startBuddy() {
  document.querySelectorAll(".orb").forEach(function (orb) {
    orb.innerHTML = ORB_PARTS;
    orb.setAttribute("data-buddy", "idle");
  });
}

// The state machine: "idle", "listening", "thinking", or "speaking".
function setBuddyState(state) {
  buddyState = state;
  document.querySelectorAll(".orb").forEach(function (orb) {
    orb.setAttribute("data-buddy", state);
  });
  flowSpeed(BUDDY_FLOW[state]);
  var label = document.getElementById("buddy-label");
  if (label && label.textContent !== BUDDY_LABELS[state]) {
    label.textContent = BUDDY_LABELS[state];
  }
}

// Speed the color flow up or down without a jump: the running animations
// keep their place and just play faster. (Changing the CSS duration instead
// would make the colors leap.) In Calm motion nothing moves, so there is
// nothing to speed up.
function flowSpeed(rate) {
  document.querySelectorAll(".orb-flow, .orb-blob").forEach(function (part) {
    if (!part.getAnimations) {
      return;
    }
    part.getAnimations().forEach(function (animation) {
      if (animation.updatePlaybackRate) {
        animation.updatePlaybackRate(rate);
      } else {
        animation.playbackRate = rate;
      }
    });
  });
}

// Speech started or ended (speech.js). Buddy shows "speaking" only when it
// isn't listening or thinking. Some browsers never say speech has ended,
// so it goes back to idle after the longest the words could take.
function buddySpeaking(speaking, seconds) {
  clearTimeout(speakingTimer);
  if (speaking) {
    if (buddyState === "idle") {
      setBuddyState("speaking");
    }
    speakingTimer = setTimeout(function () {
      buddySpeaking(false);
    }, (seconds || 10) * 1000);
  } else if (buddyState === "speaking") {
    setBuddyState("idle");
  }
}

// A soft lift for each spoken word, at most one every 400ms (never close
// to 3 a second, so nothing ever flashes).
function pulseBuddy() {
  var now = Date.now();
  if (now - lastPulse < 400) {
    return;
  }
  lastPulse = now;
  document.querySelectorAll(".orb").forEach(function (orb) {
    orb.setAttribute("data-pulse", "");
    setTimeout(function () {
      orb.removeAttribute("data-pulse");
    }, 250);
  });
}
