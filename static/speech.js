// Grandma Buddy read-aloud.
// Meta has no text-to-speech model, so Buddy speaks in one of two ways:
// - Buddy's natural voice (Kokoro, running on this computer: app/voice.py),
//   which sounds the same in every browser. The page asks /api/speak for
//   one sentence at a time and plays it, making the next one meanwhile.
// - The browser's own voice (speechSynthesis): if the natural voice isn't
//   set up, if she chose a browser voice in Settings, or whenever the
//   natural voice has any trouble, so Buddy (and a safety message) always
//   speaks.
//
// Things browsers need for this to be reliable:
// - The list of browser voices arrives late, so we pick again when it does.
// - Browsers only make sound after the person has tapped something on the page.
// - Chrome cuts off long speech, so we speak one sentence at a time.
// - We never wait for speech to finish; some browsers never say it did.
// - While a safety screen is open, nothing else may interrupt it.

"use strict";

var voiceSettings = { on: true, rate: 0.9 }; // updated from her profile
var chosenVoice = null; // the browser voice (used when the natural one isn't)
var naturalVoice = { available: false, default: "", voices: [] }; // from /api/voice
var lastSpoken = "";
var safetySpeaking = false;
var currentUtterances = []; // kept here so the browser doesn't drop them early
var naturalAudio = null; // the natural-voice sentence playing now
var naturalTalk = 0; // which speak() is current: an older one stops when a newer starts
var NATURAL = "natural:"; // her choice in Settings: "natural:af_heart", or a browser voice's name
// Where her choice is kept on this device. (A new name: a browser voice
// picked before Buddy had natural voices doesn't hide them.)
var VOICE_KEY = "buddy-voice";
var NATURAL_WAIT_MS = 6000; // a sentence that takes longer is said with the browser voice
var FIRST_WAIT_MS = 1800; // the first sentence of a reply: past this, the whole reply is said with the browser voice
var SAFETY_WAIT_MS = 2500; // a safety message never waits longer than this to be heard

function canSpeak() {
  return "speechSynthesis" in window;
}

// ---------- Which voice ----------

// Browser voices from best to worst. Microsoft Edge has natural-sounding
// voices ("Online (Natural)"), Chrome has Google's, and a Mac or iPad has
// Apple's. The old Windows voices (David, Mark, Zira) sound robotic, so
// they come last, Zira first among them as the clearest.
var VOICE_RANKING = [
  /(Ava|Emma|Jenny|Aria).*Natural/i, // warm, clear Edge voices
  /Natural/i,                         // Edge's other natural voices
  /Online/i,                          // other online voices sound natural too
  /^Google (US|UK) English/i,         // Chrome
  /Samantha|Karen|Moira|Daniel/i,     // Safari
  /Zira/i,                            // the old Windows voices
];
var ROBOTIC_RANK = VOICE_RANKING.length - 1; // Zira and below

function voiceRank(voice) {
  for (var i = 0; i < VOICE_RANKING.length; i++) {
    if (VOICE_RANKING[i].test(voice.name)) {
      return i;
    }
  }
  return VOICE_RANKING.length;
}

// Every English browser voice, best first (American English first among equals).
function englishVoices() {
  if (!canSpeak()) {
    return [];
  }
  var notAmerican = function (voice) { return /^en[-_]us/i.test(voice.lang) ? 0 : 1; };
  return speechSynthesis.getVoices()
    .filter(function (voice) { return /^en[-_]/i.test(voice.lang); })
    .sort(function (a, b) { return voiceRank(a) - voiceRank(b) || notAmerican(a) - notAmerican(b); });
}

// True when this browser has only the old robotic voices (and no natural
// voice is set up): Settings then suggests Microsoft Edge.
function onlyRoboticVoices() {
  var best = englishVoices()[0];
  return !best || voiceRank(best) >= ROBOTIC_RANK;
}

function savedVoice() {
  try {
    return localStorage.getItem(VOICE_KEY) || "";
  } catch (e) {
    return "";
  }
}

// The natural voice to use ("af_heart"), or "" for the browser's voice:
// her choice in Settings (kept on this device), else the natural default.
function chosenNatural() {
  if (!naturalVoice.available) {
    return "";
  }
  var saved = savedVoice();
  var id = saved.indexOf(NATURAL) === 0 ? saved.slice(NATURAL.length) : "";
  if (naturalVoice.voices.some(function (voice) { return voice.id === id; })) {
    return id;
  }
  var choseBrowserVoice = englishVoices().some(function (voice) { return voice.name === saved; });
  return choseBrowserVoice ? "" : naturalVoice.default;
}

// The browser voice: her choice, or else the best one there is.
function pickVoice() {
  var voices = englishVoices();
  var saved = savedVoice();
  chosenVoice = voices.find(function (voice) { return voice.name === saved; }) || voices[0] || null;
  if (typeof showVoiceChoices === "function") {
    showVoiceChoices(); // screens.js: the list in Settings, once the voices arrive
  }
}

function chooseVoice(value) {
  try {
    localStorage.setItem(VOICE_KEY, value);
  } catch (e) {}
  pickVoice();
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

// Is Buddy's natural voice set up on this computer?
var voiceStatus = fetch("/api/voice")
  .then(function (response) { return response.json(); })
  .then(function (status) {
    naturalVoice = status;
    pickVoice();
    if (status.loading) {
      askAgainWhenReady(24); // the model is still loading on the server: look again, up to two minutes
    }
  })
  .catch(function () {
    // No answer: the browser's voice it is.
  });

// On a host the natural voice loads in the background after a start: the
// browser's voice speaks until /api/voice says it is ready, then Buddy's
// voices appear in Settings and the next reply is in Heart.
function askAgainWhenReady(triesLeft) {
  if (triesLeft <= 0) {
    return;
  }
  setTimeout(function () {
    fetch("/api/voice")
      .then(function (response) { return response.json(); })
      .then(function (status) {
        if (status.available) {
          naturalVoice = status;
          pickVoice();
        } else if (status.loading) {
          askAgainWhenReady(triesLeft - 1);
        }
      })
      .catch(function () {});
  }, 5000);
}

// Have the natural voice make these words ahead of time (the server keeps
// what it made), so when they are said there is no wait. Used for the demo
// reminder, which should be heard the moment it shows.
function warmVoice(text) {
  voiceStatus.then(function () {
    var natural = chosenNatural();
    if (!natural) {
      return;
    }
    sentencesOf(text).forEach(function (sentence) {
      fetch("/api/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: sentence.trim(), voice: natural, speed: voiceSettings.rate }),
      }).catch(function () {});
    });
  });
}

// ---------- Speaking ----------

// The sentences of a text, one per utterance. Split only where . ! ? or ;
// is followed by a space, so "1.5 tablets" and "0.5 mg" are never broken
// apart (and each pill in a reminder is its own sentence).
function sentencesOf(text) {
  return text.split(/(?<=[.!?;])\s+/).filter(function (sentence) { return sentence.trim(); });
}

// How many words come before a point in a sentence: which word the voice
// is on, from the character position a "boundary" event reports.
function wordsBefore(sentence, charIndex) {
  return sentence.slice(0, charIndex).split(/\s+/).filter(Boolean).length;
}

// Read text aloud.
//   options.safety   a safety-screen message, which nothing else may cut off
//   options.preview  "Try it" in Settings: heard even if replies aren't read aloud
//   options.onStart  runs when the voice actually starts (browsers stay
//                    silent until her first tap on the page)
//   options.onWord   runs with the number of the word being said (0, 1, 2…
//                    in the whole text), for the karaoke highlight. Voices
//                    that send no word events simply never call it.
//   options.onEnd    runs when the last sentence is done
// Buddy's light (buddy.js) shows "speaking" meanwhile and pulses gently
// with the words.
function speak(text, options) {
  options = options || {};
  // Safety messages are always read aloud, even if voice is turned off.
  if (!text || (!voiceSettings.on && !options.safety && !options.preview)) {
    return;
  }
  if (safetySpeaking && !options.safety) {
    return;
  }
  lastSpoken = text;
  stopVoices();
  var natural = chosenNatural();
  if (natural) {
    speakNaturally(text, natural, options);
  } else {
    speakWithBrowser(text, options);
  }
}

// The longest these words could take, if the end is never reported.
function longestSeconds(text) {
  return text.split(/\s+/).filter(Boolean).length / (2.2 * voiceSettings.rate) + 3;
}

// Each sentence's first word, counted in words from the start of the text.
function sentenceStarts(sentences) {
  var firstWord = 0;
  return sentences.map(function (sentence) {
    var startsAt = firstWord;
    firstWord += sentence.trim().split(/\s+/).length;
    return startsAt;
  });
}

// The browser's own voice, one sentence at a time.
function speakWithBrowser(text, options) {
  if (!canSpeak()) {
    return;
  }
  var sentences = sentencesOf(text);
  var starts = sentenceStarts(sentences);
  currentUtterances = sentences.map(function (sentence, index) {
    var spoken = sentence.trim();
    var utterance = new SpeechSynthesisUtterance(spoken);
    if (index === 0) {
      utterance.onstart = function () {
        buddySpeaking(true, longestSeconds(text));
        if (options.onStart) {
          options.onStart();
        }
      };
    }
    utterance.onboundary = function (event) {
      if (event.name === "word") {
        pulseBuddy();
        if (options.onWord) {
          options.onWord(starts[index] + wordsBefore(spoken, event.charIndex));
        }
      }
    };
    if (index === sentences.length - 1) {
      utterance.onend = function () {
        buddySpeaking(false);
        if (options.onEnd) {
          options.onEnd();
        }
      };
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

// One sentence in the natural voice, as a sound file from our server.
// Fails (so the browser voice takes over) if it doesn't come in time.
function naturalSound(sentence, voiceId, waitMs) {
  var waited = new AbortController();
  var timer = setTimeout(function () { waited.abort(); }, waitMs);
  return fetch("/api/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: sentence.trim(), voice: voiceId, speed: voiceSettings.rate }),
    signal: waited.signal,
  }).then(function (response) {
    clearTimeout(timer);
    if (!response.ok) {
      throw new Error("No natural voice");
    }
    return response.blob();
  });
}

// Buddy's natural voice: the sentences play one after another, and the
// next one is made while the one before it plays. On any trouble, the
// rest is said with the browser's voice.
function speakNaturally(text, voiceId, options) {
  var talk = naturalTalk;
  var sentences = sentencesOf(text);
  var starts = sentenceStarts(sentences);
  var waitMs = options.safety ? SAFETY_WAIT_MS : NATURAL_WAIT_MS;

  function stillCurrent() {
    return talk === naturalTalk;
  }

  function fallBack(index) {
    if (stillCurrent()) {
      naturalAudio = null;
      speakWithBrowser(sentences.slice(index).join(" "), options);
    }
  }

  function play(index, sound) {
    sound.then(function (blob) {
      if (!stillCurrent()) {
        return;
      }
      var next = index + 1 < sentences.length ? naturalSound(sentences[index + 1], voiceId, waitMs) : null;
      var audio = new Audio(URL.createObjectURL(blob));
      naturalAudio = audio;
      audio.addEventListener("playing", function () {
        if (index === 0) {
          buddySpeaking(true, longestSeconds(text));
          if (options.onStart) {
            options.onStart();
          }
        }
        followWords(audio, sentences[index].trim(), starts[index], options);
      });
      audio.addEventListener("ended", function () {
        URL.revokeObjectURL(audio.src);
        if (!stillCurrent()) {
          return;
        }
        if (next) {
          play(index + 1, next);
        } else {
          naturalAudio = null;
          buddySpeaking(false);
          if (options.onEnd) {
            options.onEnd();
          }
        }
      });
      audio.play().catch(function () { fallBack(index); });
    }).catch(function () { fallBack(index); });
  }

  play(0, naturalSound(sentences[0], voiceId, options.safety ? SAFETY_WAIT_MS : FIRST_WAIT_MS));
}

// The karaoke highlight for the natural voice: a sound file says nothing
// about where each word is, so the place in the sentence is estimated from
// how far the sound has played (longer words take longer).
function followWords(audio, sentence, startsAt, options) {
  var words = sentence.split(/\s+/);
  var marks = []; // where each word starts, from 0 to 1
  var characters = 0;
  words.forEach(function (word) {
    marks.push(characters / sentence.length);
    characters += word.length + 1;
  });
  var shown = -1;
  (function step() {
    if (naturalAudio !== audio || audio.paused || audio.ended) {
      return;
    }
    var done = audio.duration ? audio.currentTime / audio.duration : 0;
    var word = 0;
    while (word + 1 < marks.length && marks[word + 1] <= done) {
      word++;
    }
    if (word !== shown) {
      shown = word;
      pulseBuddy();
      if (options.onWord) {
        options.onWord(startsAt + word);
      }
    }
    requestAnimationFrame(step);
  })();
}

// Stop whatever is being said, by either voice.
function stopVoices() {
  naturalTalk++;
  if (naturalAudio) {
    naturalAudio.pause();
    naturalAudio = null;
  }
  if (canSpeak()) {
    speechSynthesis.cancel();
  }
}

// True while Buddy is reading something aloud.
function isSpeaking() {
  return naturalAudio !== null || (canSpeak() && speechSynthesis.speaking);
}

function stopSpeaking() {
  stopVoices();
  buddySpeaking(false);
}

// "Say it again": repeat the last thing Buddy said (with the karaoke
// highlight when it is the reply on the Talk screen).
function sayAgain() {
  speak(lastSpoken, { safety: safetySpeaking, onWord: highlightWord, onEnd: clearHighlight });
}
