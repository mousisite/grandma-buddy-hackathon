// Grandma Buddy read-aloud.
// Buddy's words are spoken with the browser's built-in voice
// (speechSynthesis), because Meta has no text-to-speech model.
//
// Things browsers need for this to be reliable:
// - The list of voices arrives late, so we pick a voice again when it does.
// - Chrome only speaks after the person has tapped something on the page.
// - Chrome cuts off long speech, so we speak one sentence at a time.
// - We never wait for speech to finish; some browsers never say it did.
// - While a safety screen is open, nothing else may interrupt it.

"use strict";

var voiceSettings = { on: true, rate: 0.9 }; // updated from her profile
var chosenVoice = null;
var lastSpoken = "";
var safetySpeaking = false;
var currentUtterances = []; // kept here so the browser doesn't drop them early

function canSpeak() {
  return "speechSynthesis" in window;
}

// Pick a clear English voice, preferring natural-sounding ones.
function pickVoice() {
  var voices = speechSynthesis.getVoices().filter(function (voice) {
    return /^en[-_]/i.test(voice.lang);
  });
  chosenVoice =
    voices.find(function (voice) { return /natural|aria|jenny|samantha|google us english/i.test(voice.name); }) ||
    voices.find(function (voice) { return /en[-_]us/i.test(voice.lang); }) ||
    voices[0] ||
    null;
}

if (canSpeak()) {
  pickVoice();
  speechSynthesis.addEventListener("voiceschanged", pickVoice);
  // Her first tap anywhere unlocks speech for the rest of the visit.
  document.addEventListener("pointerdown", function unlock() {
    speechSynthesis.speak(new SpeechSynthesisUtterance(""));
    document.removeEventListener("pointerdown", unlock);
  });
}

// The sentences of a text, one per utterance. Split only where . ! ? or ;
// is followed by a space, so "1.5 tablets" and "0.5 mg" are never broken
// apart (and each pill in a reminder is its own sentence).
function sentencesOf(text) {
  return text.split(/(?<=[.!?;])\s+/).filter(function (sentence) { return sentence.trim(); });
}

// Read text aloud. options.safety marks a safety-screen message, which
// nothing else may cut off. options.onStart runs when the voice actually
// starts (Chrome stays silent until her first tap on the page).
function speak(text, options) {
  options = options || {};
  // Safety messages are always read aloud, even if voice is turned off.
  if (!canSpeak() || !text || (!voiceSettings.on && !options.safety)) {
    return;
  }
  if (safetySpeaking && !options.safety) {
    return;
  }
  lastSpoken = text;
  speechSynthesis.cancel();
  currentUtterances = sentencesOf(text).map(function (sentence, index) {
    var utterance = new SpeechSynthesisUtterance(sentence.trim());
    if (index === 0 && options.onStart) {
      utterance.onstart = options.onStart;
    }
    utterance.rate = voiceSettings.rate;
    if (chosenVoice) {
      utterance.voice = chosenVoice;
      utterance.lang = chosenVoice.lang;
    }
    speechSynthesis.speak(utterance);
    return utterance;
  });
}

// True while Buddy is reading something aloud.
function isSpeaking() {
  return canSpeak() && speechSynthesis.speaking;
}

function stopSpeaking() {
  if (canSpeak()) {
    speechSynthesis.cancel();
  }
}

// "Say it again": repeat the last thing Buddy said.
function sayAgain() {
  speak(lastSpoken, { safety: safetySpeaking });
}
