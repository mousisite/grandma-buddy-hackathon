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
// join the parts, so the safety net sees the whole sentence.
var JOIN_MS = 800;
var STILL_TALKING_MS = 6000; // she went on, but no end came: answer what we have
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
    said: "", joinTimer: null, waiting: "" }; // said: her sentence so far; waiting: words for after Buddy's answer
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
    if (session.said) {
      // She goes on talking: wait for the rest of her sentence.
      clearTimeout(session.joinTimer);
      session.joinTimer = setTimeout(function () { answerHer(session); }, STILL_TALKING_MS);
    }
  } else if (message.type === "live") {
    showLiveWords((session.said ? session.said + " " : "") + message.text);
  } else if (message.type === "turn") {
    session.hearing = false;
    var words = String(message.text || "").trim();
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
    session.joinTimer = setTimeout(function () { answerHer(session); }, JOIN_MS);
  }
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
