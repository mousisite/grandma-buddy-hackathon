// Grandma Buddy: "Read it to me" (docs/SPEC.md feature 16; docs/DESIGN.md,
// "Read it to me").
//
// She takes a photo of a letter, a bill, or a form. /api/read (app/reader.py)
// says what it is and what it says, and Buddy reads that aloud. Then she can
// hear it word for word (the words also show big on the screen), check it
// for a scam (the scam checker, with the words filled in), or call someone.
// A paper about her health is never explained, only read word for word,
// with her doctor's call button first (docs/SAFETY.md section 8d).
//
// Her photo stays in this page only; it is never saved. The last paper
// stays on the screen until she taps "Read another paper", so she can come
// back to it after checking it for a scam.

"use strict";

var readAnswer = null; // the paper on screen, for "Say it again" and "Read it word for word"
var readLook = 0; // counts reads, so an answer that comes back after "Read another paper" is ignored
var readingWords = false; // true while the words on the paper are read aloud

function readStatus(words) {
  setText(document.getElementById("read-status"), words);
}

// ---------- Reading ----------

// A photo from the camera or her pictures: shrunk on this device (about
// 1600 pixels on its long side, JPEG, screens.js), then sent.
function useReadPhoto(event) {
  var file = event.target.files[0];
  event.target.value = ""; // so the same photo can be chosen again
  if (!file) {
    return;
  }
  shrinkPhoto(file)
    .then(readIt)
    .catch(function () {
      readStatus("That photo didn’t work. Please try another photo.");
    });
}

// While Buddy reads it: her photo goes quiet, and the orb thinks on top.
function readIt(photo) {
  stopSpeaking();
  readLook += 1;
  var look = readLook;
  var image = document.getElementById("read-image");
  var figure = document.getElementById("read-photo");
  image.src = photo;
  document.getElementById("read-thumb").src = photo;
  document.getElementById("read-start").hidden = true;
  document.getElementById("read-result").hidden = true;
  figure.hidden = false;
  readStatus("Buddy is reading it…");
  setBuddyState("thinking");

  image.decode()
    .catch(function () {}) // the size is still known once it shows
    .then(function () {
      figure.style.setProperty("--photo-aspect", String(image.naturalWidth / image.naturalHeight || 0.75));
      return api("/api/read", "POST", { image: photo });
    })
    .then(function (answer) {
      if (look === readLook) {
        showReadAnswer(answer);
      }
    })
    .catch(function (refused) {
      if (look !== readLook) {
        return;
      }
      figure.hidden = true;
      document.getElementById("read-start").hidden = false;
      readStatus(typeof refused.detail === "string" ? refused.detail
        : "I couldn’t read it just now. Please check the internet and try again.");
    })
    .then(function () {
      if (look === readLook) {
        setBuddyState("idle");
      }
    });
}

// What it is and what it says, read aloud. Facts (the amount, the date)
// only when they are printed on the paper; the scam warning in words and
// an icon, never color alone.
function showReadAnswer(answer) {
  readAnswer = answer;
  readStatus("");
  document.getElementById("read-photo").hidden = true;
  var title = document.getElementById("read-kind");
  setText(title, answer.title);
  title.hidden = !answer.title;
  // Spark's summary, or Buddy's own fixed words for a health paper.
  var summary = document.getElementById("read-summary");
  setText(summary, answer.summary || answer.note);
  summary.hidden = !summary.textContent;

  var facts = document.getElementById("read-facts");
  facts.textContent = "";
  answer.facts.forEach(function (fact) {
    var pair = document.createElement("div");
    addText(pair, "dt", "", fact.label);
    addText(pair, "dd", "", fact.value);
    facts.appendChild(pair);
  });
  facts.hidden = answer.facts.length === 0;

  document.getElementById("read-scam").hidden = !answer.scam;
  if (answer.scam) {
    fillList("read-scam-flags", answer.scam.flags);
  }

  // The words themselves show when she asks for them.
  var text = document.getElementById("read-text");
  setText(text, answer.words);
  text.hidden = true;
  showReadingWords(false);

  // A photo it couldn't read: only "Take another photo".
  var unreadable = answer.kind === "unreadable";
  document.getElementById("read-words").hidden = unreadable;
  document.getElementById("read-retake").hidden = !unreadable;
  document.getElementById("read-check-scam").hidden = unreadable || answer.kind === "pill_label";
  showReadCalls(answer.kind);

  var result = document.getElementById("read-result");
  // The card is named by what it is, or by Buddy's words when it has no title.
  result.setAttribute("aria-labelledby", title.hidden ? "read-summary" : "read-kind");
  result.hidden = false;
  (title.hidden ? summary : title).focus();
  speak(answer.spoken);
}

// Call buttons after "Check it for a scam": her doctor first for a letter
// about her health, then her family.
function showReadCalls(kind) {
  var calls = document.getElementById("read-more");
  calls.querySelectorAll("a").forEach(function (link) { link.remove(); });
  var people = [{ name: profile.family_name || "family", phone: profile.family_phone }];
  if (kind === "medical") {
    people.unshift({ name: profile.doctor_name || "your doctor", phone: profile.doctor_phone });
  }
  people.forEach(function (person) {
    var href = "tel:" + person.phone;
    if (person.phone && isCallLink(href)) {
      calls.appendChild(callLink({ label: "Call " + person.name, href: href }, "call-pill call-pill--quiet"));
    }
  });
}

// ---------- Word for word ----------

// "Read it word for word": the words on the paper, big on the screen (under
// the button, so "Stop reading" stays where her finger is) and read aloud.
// While they are read, the button says "Stop reading".
function readWordForWord() {
  if (readingWords) {
    stopSpeaking();
    showReadingWords(false);
    return;
  }
  // The words appear right under the button, and the page doesn't scroll:
  // "Stop reading" stays under her finger, and she scrolls when she likes.
  document.getElementById("read-text").hidden = false;
  if (voiceSettings.on) {
    showReadingWords(true);
    speak(linesToSay(readAnswer.words), { onEnd: function () { showReadingWords(false); } });
  }
}

// The paper's lines, read one after another: a line without its own full
// stop (a heading, an address) still ends with a pause.
function linesToSay(words) {
  return words.split("\n").map(function (line) {
    return /[.!?;:,]$/.test(line) ? line : line + ".";
  }).join(" ");
}

function showReadingWords(on) {
  readingWords = on;
  setText(document.getElementById("read-words-label"), on ? "Stop reading" : "Read it word for word");
}

// ---------- Starting over, and the scam checker ----------

// "Read another paper": back to the photo buttons, the last paper gone.
function readAnother() {
  readLook += 1;
  readAnswer = null;
  stopSpeaking();
  showReadingWords(false);
  setBuddyState("idle");
  document.getElementById("read-result").hidden = true;
  document.getElementById("read-photo").hidden = true;
  document.getElementById("read-image").removeAttribute("src");
  document.getElementById("read-thumb").removeAttribute("src");
  document.getElementById("read-start").hidden = false;
  readStatus("");
  document.getElementById("read-title").focus();
}

// "Check it for a scam": the scam checker, with the paper's words filled in
// and checked right away (its own plain rules and Muse Spark, screens.js).
function checkPaperForScam() {
  stopSpeaking();
  showReadingWords(false);
  checkAnother(); // the scam screen's empty box, not an old verdict
  document.getElementById("scam-text").value = readAnswer.words;
  location.hash = "#/scam";
  checkMessage("text");
}

// ---------- Setting up ----------

function startRead() {
  var camera = document.getElementById("read-camera");
  var library = document.getElementById("read-library");
  document.getElementById("read-take").addEventListener("click", function () { camera.click(); });
  document.getElementById("read-choose").addEventListener("click", function () { library.click(); });
  document.getElementById("read-retake").addEventListener("click", function () { camera.click(); });
  camera.addEventListener("change", useReadPhoto);
  library.addEventListener("change", useReadPhoto);
  document.getElementById("read-again").addEventListener("click", function () {
    showReadingWords(false);
    speak(readAnswer.spoken);
  });
  document.getElementById("read-words").addEventListener("click", readWordForWord);
  document.getElementById("read-check-scam").addEventListener("click", checkPaperForScam);
  document.getElementById("read-another").addEventListener("click", readAnother);
  // Leaving the screen while the paper is read word for word stops the
  // reading: those words belong to this screen, not the next one.
  window.addEventListener("hashchange", function () {
    if (readingWords && currentScreen() !== "read") {
      stopSpeaking();
      showReadingWords(false);
    }
  });
}

startRead();
