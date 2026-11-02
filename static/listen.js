// Grandma Buddy: hands-free talking ("Talk without tapping" in Settings, on
// unless she turns it off).
// In voice mode Buddy listens on its own: her words show under the orb as
// she says them, and when she stops talking, Buddy answers. Then it listens
// again. Buddy and she never talk at once: while Buddy thinks or speaks,
// only silence is sent, so the microphone never hears Buddy's own voice
// (which could otherwise sound like her words). A tap pauses listening, or,
// while Buddy speaks, stops Buddy so she can talk. After a minute of quiet it
// stops by itself. If anything goes wrong, it falls back to "Tap to talk".
//
// The sound goes to our server (/api/listen, app/routes/listen.py), which
// passes it to Meta's realtime speech-to-text and sends her words back. Her
// finished words go to /api/chat like any others: the safety net first.

"use strict";

var QUIET_LIMIT_MS = 60 * 1000; // a minute without her talking: stop listening
var CONNECT_LIMIT_MS = 15 * 1000;
var SPEECH_START_MS = 7000; // how long Buddy's voice may take to start after a reply
var SILENCE = new ArrayBuffer(2560); // 80 ms of quiet at 16 kHz, 16-bit
// A turn that ends at a short pause may be the middle of her sentence
// ("my chest" … "hurts a lot"): wait this long before Buddy answers, and
// join the parts, so the safety net sees the whole sentence. (Meta already
// waits about a second of quiet before it ends a turn, and the server joins
// her last few messages for the safety net too, so half a second is enough.)
var JOIN_MS = 500;
var STILL_TALKING_MS = 6000; // she went on, but no end came: answer what we have
// Her turn ends here, in the page, once she has been quiet after talking
// (her microphone's loudness, with no library), without waiting for Meta to
// say so (Meta took 0.5 to 4.7 seconds, measured Nov 1). Meta's live words
// trail her: her last word shows up in a live update 0.5 to 1.1 seconds
// after she said it (earlier updates may lack it), so the turn ends only
// once a live update has come 0.65 seconds after her last sound (0.4
// seconds is enough when it ends a sentence, with a full stop or a question
// mark) and then held still for 0.5 seconds: about 1 to 1.6 seconds after
// her last word. A short pause inside a sentence doesn't end it. Her live words
// are what Buddy answers; Meta's own end of that turn is dropped when it
// comes (unless it carries more words than were sent: those go to Buddy
// next, never lost).
var QUIET_TURN_MS = 700; // quiet at least this long after her last sound
var LIVE_AFTER_QUIET_MS = 650; // and a live update came this long after her last sound (it has her last word)…
var SENTENCE_AFTER_QUIET_MS = 400; // …or this long, when the words end a sentence
var LIVE_SETTLED_MS = 500; // and her live words haven't changed for this long
var SENTENCE_SETTLED_MS = 500; // (the same, in the sentence case)
var ENDS_SENTENCE = /[.?!]["'\u2019]?$/;
var LOUD = 0.05; // her voice, on the orb's 0 to 1 level (a quiet room stays under it)
var handsFree = null; // while on: the session from startHandsFree()

// Can this browser listen hands-free, and does she want it?
function handsFreeWanted() {
  return profile.hands_free !== false && "AudioWorkletNode" in window && "WebSocket" in window &&
    Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

function handsFreeOn() {
  return handsFree !== null;
}

// May Buddy say something now (a pill reminder, a thank-you)? Not while
// the microphone is open for tap-to-talk, nor while she is in the middle of
// saying something hands-free.
function buddyMaySpeak() {
  return talkState === "idle" || (handsFree !== null && talkState === "listening" && !handsFree.hearing);
}

// Open the microphone and the relay. Resolves once Meta is listening;
// rejects with "NoLiveSound" when live speech-to-text can't be used here
// (then tap to talk), or with the microphone's own problem.
function startHandsFree() {
  var session = { socket: null, context: null, stream: null, ready: false, hearing: false,
    heardAt: Date.now(), replyAt: 0, buddySpoke: true, level: 0,
    said: "", joinTimer: null, waiting: "", // said: her sentence so far; waiting: words for after Buddy's answer
    liveText: "", liveAt: 0, liveTurn: null, // her live words in this turn, when they last changed, Meta's number for it
    lastLoudAt: 0, endedTurn: null, endedText: "", dropNextTurn: false }; // the turn ended here, and what was sent
  handsFree = session;
  setTalkState("working"); // "One moment…" while it gets ready
  return navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  })
    .then(function (stream) {
      session.stream = stream;
      if (handsFree !== session) {
        throw problem("Stopped");
      }
      session.context = new AudioContext({ sampleRate: 16000 });
      if (session.context.sampleRate !== 16000) {
        throw problem("NoLiveSound"); // this browser can't make 16 kHz sound: tap to talk
      }
      session.context.resume();
      return session.context.audioWorklet.addModule("/static/pcm-worklet.js");
    })
    .then(function () {
      var microphone = new AudioWorkletNode(session.context, "buddy-microphone");
      session.context.createMediaStreamSource(session.stream).connect(microphone);
      microphone.port.onmessage = function (event) {
        onSound(session, event.data);
      };
      return openRelay(session);
    })
    .then(function () {
      if (handsFree !== session) {
        throw problem("Stopped");
      }
      session.heardAt = Date.now();
      setTalkState("listening");
      showHandsFreeWords();
    })
    .catch(function (reason) {
      endHandsFree(session);
      if (talkState === "working") {
        setTalkState("idle");
      }
      throw reason;
    });
}

// The relay on our server: ready when Meta is listening.
function openRelay(session) {
  return new Promise(function (resolve, reject) {
    var socket = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/api/listen");
    socket.binaryType = "arraybuffer";
    session.socket = socket;
    var timer = setTimeout(function () {
      reject(problem("NoLiveSound"));
    }, CONNECT_LIMIT_MS);
    socket.onmessage = function (event) {
      var message = JSON.parse(event.data);
      if (message.type === "ready") {
        clearTimeout(timer);
        session.ready = true;
        resolve();
      } else if (message.type === "unavailable") {
        clearTimeout(timer);
        reject(problem("NoLiveSound"));
      } else {
        onHeard(session, message);
      }
    };
    socket.onclose = function () {
      clearTimeout(timer);
      if (session.ready) {
        endHandsFree(session); // the relay ended (15 minutes, or Meta stopped): tap to talk
      } else {
        reject(problem("NoLiveSound"));
      }
    };
  });
}

// 80 ms of microphone sound. Listen or speak, never both: while Buddy
// thinks or speaks, silence goes instead, so the microphone never hears
// Buddy. (Meta needs sound all the time, so silence, not nothing.)
function onSound(session, sound) {
  var socket = session.socket;
  if (handsFree !== session || !session.ready || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  var hers = talkState === "listening" && !isSpeaking() && !safetySpeaking;
  if (socket.bufferedAmount < 64 * 1024) { // the network is behind: skip a piece rather than pile up
    socket.send(hers ? sound : SILENCE);
  }
  session.level = hers ? loudness(sound) : 0;
  if (hers && session.level > LOUD) {
    session.lastLoudAt = Date.now();
  }
  if (hers && session.hearing && session.liveText && Date.now() - session.lastLoudAt > QUIET_TURN_MS && herLastWordIsIn(session)) {
    endTurnHere(session); // she has been quiet long enough, and her last word is in: her turn is over
  }
  if (isSpeaking()) {
    session.buddySpoke = true;
    session.heardAt = Date.now(); // a minute of quiet counts from when Buddy stopped
  }
  // Buddy has finished its answer (or its voice never started): listen again.
  var buddyDone = session.buddySpoke || !voiceSettings.on || Date.now() - session.replyAt > SPEECH_START_MS;
  if (talkState === "idle" && !isSpeaking() && !safetySpeaking && buddyDone && currentScreen() === "talk") {
    session.heardAt = Date.now();
    setTalkState("listening");
  }
  if (talkState === "listening" && !session.hearing && Date.now() - session.heardAt > QUIET_LIMIT_MS) {
    stopHandsFree();
    say("I’ll stop listening for now. Tap “Tap to talk” when you’d like to talk again.");
    return;
  }
  showHandsFreeWords();
}

// How loud: 0 to 1, for the orb to swell with her voice.
function loudness(sound) {
  var samples = new Int16Array(sound);
  var sum = 0;
  for (var i = 0; i < samples.length; i++) {
    sum += (samples[i] / 32768) * (samples[i] / 32768);
  }
  return Math.min(1, Math.sqrt(sum / samples.length) * 6);
}

// What Meta heard, through the relay.
function onHeard(session, message) {
  if (handsFree !== session) {
    return;
  }
  session.heardAt = Date.now();
  if (message.type === "hearing") {
    session.hearing = true;
    session.liveTurn = message.turn === undefined ? null : message.turn;
    session.liveText = "";
    session.lastLoudAt = Date.now(); // the quiet count starts now: she has just begun
    if (session.said) {
      // She goes on talking: wait for the rest of her sentence.
      clearTimeout(session.joinTimer);
      session.joinTimer = setTimeout(function () { answerHer(session); }, STILL_TALKING_MS);
    }
  } else if (message.type === "live") {
    if (session.endedTurn !== null && session.endedTurn === session.liveTurn) {
      return; // this turn was ended here already; its end from Meta brings any words that are missing
    }
    session.liveText = String(message.text || "");
    session.liveAt = Date.now();
    showLiveWords((session.said ? session.said + " " : "") + message.text);
  } else if (message.type === "turn") {
    var words = String(message.text || "").trim();
    var endedHere = session.dropNextTurn || (message.turn !== undefined && message.turn !== null && message.turn === session.endedTurn);
    if (endedHere) {
      // Meta's end of a turn that ended here: only words it has beyond what
      // was sent (she went on while Buddy started thinking) go to Buddy.
      session.dropNextTurn = false;
      session.endedTurn = null;
      words = wordsAfter(session.endedText, words);
      session.endedText = "";
      if (!words) {
        return;
      }
    }
    turnHeard(session, words, JOIN_MS);
  }
}

// Her turn is over (Meta said so, or she has been quiet long enough): Buddy
// answers after joinMs, in case she goes on.
function turnHeard(session, words, joinMs) {
  session.hearing = false;
  if (talkState === "working") {
    // Buddy is thinking about her last words: these wait their turn, never lost.
    session.waiting = (session.waiting ? session.waiting + " " : "") + words;
    return;
  }
  if (talkState === "idle" && words) {
    stopSpeaking(); // she talked over Buddy: Buddy stops and listens
    setTalkState("listening");
  }
  session.said = (session.said ? session.said + " " : "") + words;
  session.said = session.said.trim();
  clearTimeout(session.joinTimer);
  session.joinTimer = setTimeout(function () { answerHer(session); }, joinMs);
}

// Do her live words have her last word yet? A live update that came long
// enough after her last sound, and has held still since.
function herLastWordIsIn(session) {
  var cameAfterQuiet = session.liveAt - session.lastLoudAt;
  var heldStill = Date.now() - session.liveAt;
  if (cameAfterQuiet >= LIVE_AFTER_QUIET_MS && heldStill > LIVE_SETTLED_MS) {
    return true;
  }
  return ENDS_SENTENCE.test(session.liveText.trim()) && cameAfterQuiet >= SENTENCE_AFTER_QUIET_MS && heldStill > SENTENCE_SETTLED_MS;
}

// She has been quiet long enough: her live words so far are her turn, and
// Buddy answers at once (no join wait: she has already been quiet).
function endTurnHere(session) {
  var words = session.liveText.trim();
  session.endedTurn = session.liveTurn;
  session.endedText = words;
  session.dropNextTurn = session.liveTurn === null; // no turn numbers: drop Meta's next end instead
  session.liveText = "";
  turnHeard(session, words, 0);
}

// The words in full that come after the words already sent ("my knee hurts"
// then "my knee hurts when I walk" gives "when I walk"), or "" when full
// doesn't start with them.
function wordsAfter(sent, full) {
  var plain = function (text) { return text.toLowerCase().replace(/[^a-z0-9' ]+/g, " ").split(/\s+/).filter(Boolean); };
  var sentWords = plain(sent);
  var fullWords = full.split(/\s+/).filter(Boolean);
  if (!sentWords.length || fullWords.length <= sentWords.length) {
    return "";
  }
  var fullPlain = plain(full);
  for (var i = 0; i < sentWords.length; i++) {
    if (fullPlain[i] !== sentWords[i]) {
      return "";
    }
  }
  return fullWords.slice(sentWords.length).join(" ");
}

// Her sentence is complete: Buddy answers it.
function answerHer(session) {
  clearTimeout(session.joinTimer);
  var words = session.said;
  session.said = "";
  if (handsFree !== session) {
    return;
  }
  if (words && talkState === "listening") {
    herTurn(session, words);
  } else {
    document.getElementById("you-said").classList.remove("live");
  }
}

// Her words as she says them, a little lighter until she has finished.
function showLiveWords(text) {
  if (!text || talkState !== "listening") {
    return;
  }
  var card = document.getElementById("you-said");
  if (!card.classList.contains("live")) {
    // A new turn: the last exchange moves to "Earlier".
    moveToEarlier();
    say("");
    card.classList.add("live");
  }
  document.getElementById("you-said-text").textContent = text;
  card.hidden = false;
}

// She finished a turn: Buddy answers, then listens again.
function herTurn(session, words) {
  document.getElementById("you-said").classList.remove("live");
  newExchange(words);
  setTalkState("working"); // "Let me think…"
  askBuddy(words)
    .then(function () {
      if (handsFree !== session) {
        return;
      }
      if (document.getElementById("safety-screen").open) {
        stopHandsFree(); // she has someone to call: the microphone goes off
        return;
      }
      if (session.waiting) {
        // She said more while Buddy was thinking: that is next.
        var next = session.waiting;
        session.waiting = "";
        herTurn(session, next);
        return;
      }
      // Buddy's turn: it listens again once it has finished speaking (onSound).
      session.replyAt = Date.now();
      session.buddySpoke = false;
      setTalkState("idle");
      showHandsFreeWords();
    })
    .catch(function (reason) {
      stopHandsFree();
      talkProblem(reason);
      setTalkState("idle");
    });
}

// The talk button (or the orb) while hands-free: stop Buddy so she can
// talk, or pause listening.
function handsFreeTap() {
  if (talkState === "working") {
    return; // Buddy is getting ready or thinking: taps wait
  }
  if (talkState === "idle" || isSpeaking()) {
    stopSpeaking();
    handsFree.heardAt = Date.now();
    setTalkState("listening");
    showHandsFreeWords();
    return;
  }
  stopHandsFree(); // "Pause"
}

// The button says what a tap does now, and the orb shows who is talking.
function showHandsFreeWords() {
  if (!handsFree || talkState === "working") {
    return;
  }
  var speaking = isSpeaking() || talkState === "idle";
  setText(document.getElementById("talk-label"), speaking ? "Stop and talk" : "Pause");
  document.getElementById("talk-button").setAttribute("data-hands-free", speaking ? "buddy" : "her");
  var orb = speaking ? (isSpeaking() ? "speaking" : "idle") : "listening";
  if (buddyState !== orb) {
    setBuddyState(orb);
  }
}

// Stop listening: the microphone goes off, and "Tap to talk" is back.
function stopHandsFree() {
  if (handsFree) {
    endHandsFree(handsFree);
  }
}

function endHandsFree(session) {
  clearTimeout(session.joinTimer);
  if (handsFree === session) {
    handsFree = null;
  }
  if (session.socket) {
    session.socket.onclose = null;
    session.socket.onmessage = null;
    if (session.socket.readyState <= WebSocket.OPEN) {
      session.socket.close();
    }
  }
  if (session.stream) {
    session.stream.getTracks().forEach(function (track) { track.stop(); });
  }
  if (session.context) {
    session.context.close().catch(function () {});
  }
  document.getElementById("you-said").classList.remove("live");
  document.getElementById("talk-button").removeAttribute("data-hands-free");
  if (talkState === "listening" || (talkState === "idle" && document.getElementById("talk-label").textContent !== TALK_LABELS.idle)) {
    setTalkState("idle"); // "Tap to talk"
  }
}

function startHandsFreeListening() {
  // A page left in the background stops listening (her privacy).
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      stopHandsFree();
    }
  });
}
