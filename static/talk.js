// Grandma Buddy: talking.
// "Talk to Buddy" (or tapping the orb) on Home opens voice mode and starts
// listening; tap "I'm done" when finished (no holding down). Her voice
// becomes text (/api/transcribe), then goes to /api/chat, where the safety
// net checks it first. If the safety net answers, a full-screen safety
// screen appears with big call buttons. The orb (buddy.js) shows listening
// and thinking; recording lives in recorder.js and reading aloud in speech.js.

"use strict";

var TALK_LIMIT_MS = 2 * 60 * 1000; // recording stops by itself after 2 minutes
var TALK_LABELS = { idle: "Tap to talk", listening: "I’m done", working: "One moment…" };
var BUDDY_FOR_TALK = { listening: "listening", working: "thinking" };
var talkState = "idle"; // "idle", "listening", or "working"
var talkTimer = null;
// "chat", "check_in" (the daily check-in), "diary" ("Something hurts"), or
// "memory" ("Tell Buddy a memory", for the Memory book)
var talkMode = "chat";
var lastExchange = null; // { her, buddy }: moves to "Earlier" when a new one starts
var EARLIER_MAX = 10;

// "Something hurts" and "Tell Buddy a memory": short talks that end in a
// diary entry or a Memory book page. Each gets its own conversation id, so
// the entry or page holds exactly what she said in it. The server says when
// the talk is done (diary_done or memory_done in its answer).
var OWN_TALKS = {
  diary: { opening: "I’m sorry something hurts. Tell me what you’re feeling.", hint: "Buddy is writing in your diary" },
  memory: { opening: "I’d love to hear one of your memories. What would you like to tell me about?", hint: "Buddy is listening for your memory book" },
};
var OWN_TALK_IDLE_MS = 10 * 60 * 1000; // a talk left alone for 10 minutes is over
var TALK_HINT = "Buddy writes down what you say";
var ownConversation = "";
var ownLastAnswer = 0;

// One conversation per day, so each day's talk is kept together.
function conversationId() {
  var today = new Date();
  return today.getFullYear() + "-" + (today.getMonth() + 1) + "-" + today.getDate();
}

function setTalkState(state) {
  var wasListening = talkState === "listening";
  talkState = state;
  document.getElementById("talk-button").setAttribute("data-state", state);
  document.getElementById("talk-label").textContent = TALK_LABELS[state];
  document.documentElement.setAttribute("data-talk", state);
  // The orb in voice mode says what tapping it does now.
  document.querySelector("[data-talk-orb]").setAttribute("aria-label", state === "listening" ? "I’m done" : "Buddy. Tap to go back");
  // Buddy listens and thinks with her; otherwise it is idle (or speaking,
  // which speech.js tells it).
  setBuddyState(BUDDY_FOR_TALK[state] || (isSpeaking() ? "speaking" : "idle"));
  if (state === "listening") {
    chime("start");
    requestAnimationFrame(showVoiceLevel);
  } else if (wasListening) {
    chime("stop");
  }
}

// The voice level: about 60 times a second while she talks, set --level
// from how loud she is (voiceLevel() in recorder.js). The orb swells with
// it. Smoothed so they move gently instead of jittering.
var shownLevel = 0;

function showVoiceLevel() {
  var page = document.documentElement;
  if (talkState !== "listening") {
    shownLevel = 0;
    page.style.setProperty("--level", "0");
    return;
  }
  shownLevel = shownLevel * 0.85 + (handsFreeOn() ? handsFree.level : voiceLevel()) * 0.15;
  page.style.setProperty("--level", shownLevel.toFixed(3));
  requestAnimationFrame(showVoiceLevel);
}

// A soft, low two-note chime when listening starts (rising) and stops
// (falling), only if it is switched on in Settings. Made with Web Audio,
// no sound files.
var chimeSound = null;

function chime(direction) {
  if (!profile.chime) {
    return;
  }
  try {
    chimeSound = chimeSound || new (window.AudioContext || window.webkitAudioContext)();
    var notes = direction === "start" ? [294, 392] : [392, 294]; // D4 and G4
    notes.forEach(function (frequency, index) {
      var tone = chimeSound.createOscillator();
      var volume = chimeSound.createGain();
      var at = chimeSound.currentTime + index * 0.16;
      tone.type = "sine";
      tone.frequency.value = frequency;
      volume.gain.setValueAtTime(0.0001, at);
      volume.gain.exponentialRampToValueAtTime(0.15, at + 0.02);
      volume.gain.exponentialRampToValueAtTime(0.0001, at + 0.3);
      tone.connect(volume).connect(chimeSound.destination);
      tone.start(at);
      tone.stop(at + 0.32);
    });
  } catch (e) {
    // No sound on this device: the words and the orb still show it.
  }
}

// A named problem, so talkProblem() can pick the right kind words.
function problem(name) {
  var error = new Error(name);
  error.name = name;
  return error;
}

// From Home or the sidebar: open voice mode and start listening at once.
// At the start of a conversation (the first talk today, or after two
// hours), Buddy greets her first ("Good afternoon, Rose! Did Tom make it
// on Sunday?") and starts listening once it has finished speaking, so the
// microphone never hears Buddy. Otherwise it listens at once.
function startTalkFromToday() {
  if (currentScreen() !== "talk") {
    location.hash = "#/talk";
  }
  if (talkState !== "idle") {
    return;
  }
  if (talkMode !== "chat") {
    onTalkTap();
    return;
  }
  setTalkState("working"); // no double taps while Buddy finds its greeting
  api("/api/greeting", "POST", { conversation_id: conversationId() })
    .then(function (answer) { return answer.greeting; })
    .catch(function () { return ""; }) // no greeting: she just talks
    .then(function (words) {
      setTalkState("idle");
      if (!words) {
        onTalkTap();
        return;
      }
      moveToEarlier();
      document.getElementById("you-said").hidden = true;
      var listen = function () {
        // Unless she already tapped "Tap to talk" or left voice mode.
        if (talkState === "idle" && currentScreen() === "talk") {
          onTalkTap();
        }
      };
      showReply(words, voiceSettings.on ? listen : null);
      if (!voiceSettings.on) {
        listen(); // nothing is read aloud, so there is nothing to wait for
      }
    });
}

function onTalkTap() {
  if (handsFreeOn()) {
    handsFreeTap(); // listen.js: stop Buddy so she can talk, or pause
    return;
  }
  if (talkState === "idle") {
    // Stop Buddy talking first, so the microphone never hears Buddy's voice.
    stopSpeaking();
    if (handsFreeWanted()) {
      // Talk without tapping (listen.js). Where live speech-to-text can't
      // be used, tap to talk instead.
      startHandsFree().catch(function (reason) {
        if (reason.name === "NoLiveSound") {
          startRecordingTalk();
        } else if (reason.name !== "Stopped") {
          talkProblem(reason);
        }
      });
      return;
    }
    startRecordingTalk();
  } else if (talkState === "listening") {
    finishTalking();
  }
  // While "working", extra taps do nothing.
}

// Tap to talk: record until she taps "I'm done".
function startRecordingTalk() {
  setTalkState("working"); // ignore extra taps while the microphone opens
  startRecording()
    .then(function () {
      setTalkState("listening");
      talkTimer = setTimeout(finishTalking, TALK_LIMIT_MS);
    })
    .catch(function (reason) {
      talkProblem(reason);
      setTalkState("idle");
    });
}

function finishTalking() {
  clearTimeout(talkTimer);
  setTalkState("working"); // the orb: "Let me think…"
  stopRecording()
    .then(sendForTranscript)
    .then(function (result) {
      if (!result.transcript) {
        throw problem("NotHeard");
      }
      newExchange(result.transcript);
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

// ---------- The latest exchange, and earlier ones ----------

// Her words arrived: the last exchange moves to "Earlier", and hers shows big.
function newExchange(herWords) {
  moveToEarlier();
  var card = document.getElementById("you-said");
  document.getElementById("you-said-text").textContent = herWords;
  card.hidden = false;
  say("");
  lastExchange = { her: herWords, buddy: "" };
}

// The finished exchange goes to the top of "Earlier" (newest first).
function moveToEarlier() {
  if (!lastExchange || !lastExchange.buddy) {
    return;
  }
  var list = document.getElementById("earlier");
  var item = document.createElement("li");
  if (lastExchange.her) {
    addText(item, "p", "earlier-her", "You said: “" + lastExchange.her + "”");
  }
  addText(item, "p", "earlier-buddy", "Buddy: " + lastExchange.buddy);
  list.insertBefore(item, list.firstChild);
  while (list.children.length > EARLIER_MAX) {
    list.removeChild(list.lastChild);
  }
  document.getElementById("earlier-section").hidden = false;
  lastExchange = null;
}

// Buddy's reply: streams in big, and is read aloud with reading progress.
// afterSpeaking (optional) runs once Buddy has finished saying it.
function showReply(text, afterSpeaking) {
  say(text);
  speak(text, {
    onWord: highlightWord,
    onEnd: function () {
      clearHighlight();
      if (afterSpeaking) {
        afterSpeaking();
      }
    },
  });
  lastExchange = { her: lastExchange ? lastExchange.her : "", buddy: text };
}

// Reading progress, like song lyrics: the words already read aloud are full
// ink, the rest a little quieter. Only while the reply on screen is what is
// being read. Voices that send no word events simply leave every word ink.
function highlightWord(index) {
  var message = document.getElementById("message");
  if (message.getAttribute("data-text") !== lastSpoken) {
    return;
  }
  message.classList.add("reading");
  message.querySelectorAll(".word").forEach(function (word, number) {
    word.classList.toggle("said", number <= index);
  });
}

function clearHighlight() {
  document.getElementById("message").classList.remove("reading");
}

// ---------- "Something hurts" and "Tell Buddy a memory" ----------

// Start one of these talks in voice mode: Buddy asks its opening question,
// and the hint under the talk button says what Buddy is writing.
function startOwnTalk(mode) {
  // Not while the microphone is open (it would record Buddy's question) or
  // while Buddy is still answering (that answer belongs to the last talk).
  if (talkState !== "idle") {
    return;
  }
  talkMode = mode;
  ownConversation = conversationId() + "-" + mode + "-" + Date.now();
  ownLastAnswer = Date.now();
  document.getElementById("talk-hint").textContent = OWN_TALKS[mode].hint;
  if (currentScreen() === "talk") {
    window.scrollTo(0, 0);
  } else {
    location.hash = "#/talk";
  }
  // A new talk: the last exchange moves to "Earlier". Call buttons already
  // under Buddy's words (like Call 988) stay.
  moveToEarlier();
  document.getElementById("you-said").hidden = true;
  showReply(OWN_TALKS[mode].opening);
}

// "Start from an old photo" (screens.js): a memory talk that begins with
// Buddy's words about her photo. Its page is already waiting for her story
// (app/memories.py), under the talk id the server gave.
function startMemoryFromPhoto(started) {
  if (talkState !== "idle") {
    return;
  }
  talkMode = "memory";
  ownConversation = started.conversation_id;
  ownLastAnswer = Date.now();
  document.getElementById("talk-hint").textContent = OWN_TALKS.memory.hint;
  if (currentScreen() === "talk") {
    window.scrollTo(0, 0);
  } else {
    location.hash = "#/talk";
  }
  moveToEarlier();
  document.getElementById("you-said").hidden = true;
  showReply(started.opening);
}

// The end of a "Something hurts" talk, a memory talk, or a check-in:
// ordinary talk again.
function backToChat() {
  talkMode = "chat";
  document.getElementById("talk-hint").textContent = TALK_HINT;
}

// ---------- The daily check-in ----------

// The check-in has its own conversation each day, so her diary entry holds
// only what she said in it.
function checkInConversation() {
  return conversationId() + "-check-in";
}

// Start the daily check-in in voice mode. The server gives Buddy's opening
// question ("Good morning, Rose. How are you feeling today?", fixed words)
// and remembers that today's check-in has started. Then the AI asks the
// other two questions in "check_in" mode.
function startCheckIn() {
  // Not while the microphone is open or Buddy is still answering.
  if (talkState !== "idle") {
    return;
  }
  talkMode = "check_in";
  document.getElementById("talk-hint").textContent = "Your daily check-in";
  if (currentScreen() === "talk") {
    window.scrollTo(0, 0);
  } else {
    location.hash = "#/talk";
  }
  moveToEarlier();
  document.getElementById("you-said").hidden = true;
  say("");
  api("/api/check-in/start", "POST", { conversation_id: checkInConversation() })
    .then(function (answer) {
      showReply(answer.opening);
    })
    .catch(function () {
      backToChat();
      talkProblem(problem("Offline"));
    });
}

// The conversation her words belong to right now.
function currentConversation() {
  return OWN_TALKS[talkMode] ? ownConversation : talkMode === "check_in" ? checkInConversation() : conversationId();
}

// Send her words to Buddy. The safety net answers first if it needs to.
// The answer is asked for as events (Accept: application/x-ndjson), so a
// bridge line ("Let me look that up.") can be said while a slow tool runs.
function askBuddy(text) {
  if (OWN_TALKS[talkMode] && Date.now() - ownLastAnswer > OWN_TALK_IDLE_MS) {
    backToChat(); // left alone too long: this is ordinary talk again
  }
  ownLastAnswer = Date.now();
  return fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
    body: JSON.stringify({ conversation_id: currentConversation(), text: text, mode: talkMode }),
  })
    .catch(function () {
      throw problem("Offline");
    })
    .then(function (response) {
      if (!response.ok) {
        throw problem("NotHeard");
      }
      return readChatAnswer(response);
    })
    .then(function (answer) {
      // A diary or memory talk ends when the server says so (saved and
      // Buddy isn't asking anything more, or her last answer), or after a
      // safety screen, so she is never stuck in it.
      if (talkMode !== "chat" && (answer.show || answer.diary_done || answer.memory_done)) {
        backToChat();
      }
      if (answer.show) {
        openSafetyScreen(answer.show, answer.reply, answer.actions);
      } else {
        showReply(answer.reply);
        if (answer.diary_saved) {
          toast("Saved to diary");
        }
        if (answer.memory_saved) {
          toast("Saved to your memory book");
        }
        showActions(answer.actions || []);
        loadReminders(); // she may have told Buddy she took her pills
      }
    });
}

// Buddy's answer as the server sends it: one line of JSON per event, a
// "bridge" line to say right away while a slow tool runs (plain words from
// the server, never the AI's), then "done" with the whole answer. A plain
// answer (one JSON object, with no events) is taken as it is.
function readChatAnswer(response) {
  var type = response.headers.get("content-type") || "";
  if (type.indexOf("x-ndjson") < 0 || !response.body) {
    return response.json();
  }
  var reader = response.body.getReader();
  var decoder = new TextDecoder();
  var leftover = "";
  var answer = null;

  function handle(line) {
    if (!line.trim()) {
      return;
    }
    var event = JSON.parse(line);
    if (event.type === "bridge") {
      say(event.text);
      speak(event.text);
    } else if (event.type === "done") {
      delete event.type;
      answer = event;
    } else if (event.type === "problem") {
      throw problem("NotHeard");
    }
  }

  return reader.read().then(function step(result) {
    leftover += decoder.decode(result.value || new Uint8Array(), { stream: !result.done });
    var lines = leftover.split("\n");
    leftover = result.done ? "" : lines.pop();
    lines.forEach(handle);
    if (result.done) {
      if (!answer) {
        throw problem("NotHeard");
      }
      return answer;
    }
    return reader.read().then(step);
  });
}

// ---------- Call buttons ----------

// Only phone and text-message links are ever made into buttons.
function isCallLink(href) {
  return /^(tel|sms):[0-9+()\-. ]+$/.test(href);
}

var PHONE_ICON = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M13.832 16.568a1 1 0 0 0 1.213-.303l.355-.465A2 2 0 0 1 17 15h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2A18 18 0 0 1 2 4a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v3a2 2 0 0 1-.8 1.6l-.468.351a1 1 0 0 0-.292 1.233 14 14 0 0 0 6.392 6.384"></path></svg>';

function callLink(action, className) {
  var link = document.createElement("a");
  link.className = className;
  link.href = action.href;
  link.innerHTML = PHONE_ICON;
  link.appendChild(document.createTextNode(action.label));
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
    } else if (action.type === "memory") {
      row.appendChild(saveMemoryButton(action));
    } else if (action.type === "open") {
      var open = document.createElement("button");
      open.type = "button";
      open.className = "call-pill call-pill--quiet";
      open.textContent = action.label;
      open.addEventListener("click", function () {
        openScreen(action.screen);
      });
      row.appendChild(open);
    } else if (action.type === "find") {
      // "Buddy, where are my glasses?": Find my things, with "glasses" filled in.
      var find = document.createElement("button");
      find.type = "button";
      find.className = "call-pill";
      find.textContent = action.label;
      find.addEventListener("click", function () {
        location.hash = "#/find/" + encodeURIComponent(action.thing);
      });
      row.appendChild(find);
    } else if (action.type === "message") {
      // "Send this to Maria": the Family screen, with her words in the box
      // to read over and send (screens.js). Buddy never sends it itself.
      var message = document.createElement("button");
      message.type = "button";
      message.className = "call-pill";
      message.textContent = action.label;
      message.addEventListener("click", function () {
        location.hash = "#/family/message/" + encodeURIComponent(action.text);
      });
      row.appendChild(message);
    } else if (action.type === "sources") {
      // Where today's weather (Open-Meteo) or news (Meta's web search) came from.
      var from = document.createElement("p");
      from.className = "sources";
      from.textContent = (action.from || "From the web:") + " " + action.sites.join(", ");
      row.appendChild(from);
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
        button.textContent = "Added to doctor notes";
        toast("Added to doctor notes");
        showReply("I added that to your doctor notes.");
      })
      .catch(function () {
        button.disabled = false;
        say("I couldn’t save that just now. Please tap it again.");
      });
  });
  return button;
}

// "Save it in my memory book": the memory she just told becomes a page.
// Buddy writes it and paints its picture in the background.
function saveMemoryButton(action) {
  // The talk this button belongs to, kept now: it can still be on screen
  // after that talk has ended.
  var talk = { conversation_id: currentConversation(), mode: talkMode === "memory" ? "memory" : "chat" };
  var button = document.createElement("button");
  button.type = "button";
  button.className = "call-pill call-pill--quiet";
  button.textContent = action.label;
  button.addEventListener("click", function () {
    button.disabled = true;
    api("/api/memories", "POST", talk)
      .then(function () {
        toast("Saved to your memory book");
        showReply("I’m writing it into your memory book, and painting a picture for it.");
        showActions([{ type: "open", screen: "memories", label: "Open my memory book" }]);
      })
      .catch(function (problem) {
        button.disabled = false;
        // The server's own kind words when it has them ("Tell Buddy your memory first…").
        say(typeof problem.detail === "string" ? problem.detail : "I couldn’t save that just now. Please tap it again.");
      });
  });
  return button;
}

// Opening another part of the app ("Open My pills"): change the address,
// and the router in app.js shows that screen.
function openScreen(screen) {
  location.hash = screen === "today" ? "#/" : "#/" + screen;
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

// A full-screen message with big call buttons, read aloud. It appears at
// once, with no movement, and stays until she taps "Go back".
function openSafetyScreen(kind, message, actions) {
  stopHandsFree(); // the microphone goes off: she has someone to call
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
  // Behind the screen, Buddy's words and the call buttons stay too.
  say(message);
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
  document.getElementById("you-said").hidden = true; // her last words don't belong to this message
  if (name === "NotAllowedError" || name === "SecurityError") {
    say("I can’t hear you yet. At the top of the window, click the microphone or lock picture, choose Allow, then tap “Tap to talk” again. If you need help now, call below.");
  } else if (name === "NotFoundError" || name === "NotReadableError") {
    say("I can’t find a microphone. Please check that it’s plugged in and turned on. If you need help now, call below.");
  } else if (name === "Offline") {
    say("I can’t reach the internet right now. If you need help, call below.");
  } else {
    say("I didn’t catch that. Tap “Tap to talk” and try again. If you need help now, call below.");
  }
  showActions(emergencyCallActions());
}

// The orb in voice mode: while she talks, tapping it means "I'm done";
// otherwise it closes voice mode, like Done. While Buddy is thinking,
// taps do nothing.
function onOrbTap() {
  if (handsFreeOn()) {
    handsFreeTap();
  } else if (talkState === "listening") {
    finishTalking();
  } else if (talkState === "idle") {
    location.hash = "#/";
  }
}

function startTalking() {
  startHandsFreeListening(); // listen.js
  document.getElementById("talk-button").addEventListener("click", onTalkTap);
  document.querySelectorAll("[data-talk-start]").forEach(function (button) {
    button.addEventListener("click", startTalkFromToday);
  });
  document.querySelectorAll("[data-talk-orb]").forEach(function (orb) {
    orb.addEventListener("click", onOrbTap);
  });
  document.getElementById("safety-close").addEventListener("click", closeSafetyScreen);
  document.getElementById("safety-again").addEventListener("click", sayAgain);
  document.getElementById("say-again").addEventListener("click", sayAgain);
  document.querySelectorAll("[data-start-diary]").forEach(function (button) {
    button.addEventListener("click", function () { startOwnTalk("diary"); });
  });
  document.querySelectorAll("[data-start-memory]").forEach(function (button) {
    button.addEventListener("click", function () { startOwnTalk("memory"); });
  });
  document.querySelectorAll("[data-start-check-in]").forEach(function (button) {
    button.addEventListener("click", startCheckIn);
  });
  // The Escape key closes a dialog by itself; keep speech in step with it.
  document.getElementById("safety-screen").addEventListener("close", function () {
    safetySpeaking = false;
  });
}
