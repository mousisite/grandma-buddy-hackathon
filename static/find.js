// Grandma Buddy: "Find my things" (docs/SPEC.md feature 12; docs/DESIGN.md,
// "Find my things").
//
// She says or types what she's looking for ("my glasses"), then takes a
// photo of the room. /api/find runs the safety net on her words, then SAM
// 3.1 finds the thing and Muse Spark says where it is. Here, the photo
// shows with a soft halo in Buddy's colors around her thing (the rest of
// the room dims a little), and Buddy reads the sentence aloud.
//
// Her photo stays in this page only while she looks; it is never saved.
// "Buddy, where are my glasses?" opens #/find/glasses (talk.js), with the
// thing already filled in.

"use strict";

var findSentence = ""; // what Buddy said, for "Say it again"
var findLook = 0; // counts looks, so an answer that comes back after she moved on is ignored

// ---------- Asking ----------

// The screen loader (screens.js): every visit starts fresh with the
// question. #/find/glasses fills in "glasses".
function showFind() {
  var thing = "";
  try {
    thing = decodeURIComponent(screenDetail());
  } catch (e) {} // a broken address: just ask
  showFindAsk();
  setFindThing(thing);
}

function setFindThing(thing) {
  document.getElementById("find-thing").value = thing;
  clearProblem(document.getElementById("find-ask"));
  document.querySelectorAll("[data-find-pick]").forEach(function (pick) {
    pick.setAttribute("aria-pressed", String(pick.getAttribute("data-find-pick") === thing));
  });
}

function findStatus(words) {
  document.getElementById("find-status").textContent = words;
}

// Before a photo: she has to say what she's looking for.
function knowsWhatToFind() {
  var input = document.getElementById("find-thing");
  clearProblem(input.form);
  if (input.value.trim()) {
    return true;
  }
  showProblem(input, "Please tell me what you’re looking for: type it, tap one above, or tap “Say it”.");
  input.focus();
  return false;
}

// Back to the question, with the photo gone (and any look still going forgotten).
function showFindAsk() {
  findLook += 1;
  stopSpeaking();
  document.getElementById("find-ask").hidden = false;
  document.getElementById("find-result").hidden = true;
  document.getElementById("find-image").removeAttribute("src");
  document.getElementById("find-halo").textContent = "";
  findStatus("");
}

// ---------- Looking ----------

// A photo from the camera or her pictures: shrunk on this device (about
// 1600 pixels on its long side, JPEG, screens.js), then sent.
function useFindPhoto(event) {
  var file = event.target.files[0];
  event.target.value = ""; // so the same photo can be chosen again
  if (!file) {
    return;
  }
  shrinkPhoto(file)
    .then(lookForIt)
    .catch(function () {
      findStatus("That photo didn’t work. Please try another photo.");
    });
}

function lookForIt(photo) {
  stopSpeaking();
  findLook += 1;
  var look = findLook;
  var image = document.getElementById("find-image");
  var figure = document.getElementById("find-photo");
  image.src = photo;
  image.alt = "Your photo";
  document.getElementById("find-halo").textContent = "";
  setText(document.getElementById("find-answer"), "");
  document.getElementById("find-after").hidden = true;
  document.getElementById("find-other").hidden = true;
  figure.setAttribute("data-state", "looking");
  document.getElementById("find-ask").hidden = true;
  document.getElementById("find-result").hidden = false;
  findStatus("Buddy is looking…");
  setBuddyState("thinking");

  image.decode()
    .catch(function () {}) // the size is still known once it shows
    .then(function () {
      // The frame takes the photo's shape, so the halo lines up with it.
      figure.style.setProperty("--photo-aspect", String(image.naturalWidth / image.naturalHeight || 1.5));
      return api("/api/find", "POST", {
        thing: document.getElementById("find-thing").value.trim(),
        image: photo,
        width: image.naturalWidth,
        height: image.naturalHeight,
      });
    })
    .then(function (answer) {
      if (look !== findLook) {
        return; // she went back or left: this answer is old
      }
      if (answer.show) {
        // Her words needed the safety net (like "I took my pills twice").
        showFindAsk();
        openSafetyScreen(answer.show, answer.reply, answer.actions);
        return;
      }
      showFindAnswer(answer);
    })
    .catch(function (refused) {
      if (look !== findLook) {
        return;
      }
      showFindAsk();
      findStatus((refused && refused.detail) || "I couldn’t look just now. Please check the internet and try again.");
    })
    .then(function () {
      setBuddyState("idle");
    });
}

// What Buddy found: the halo (if it found it), the sentence, read aloud.
function showFindAnswer(answer) {
  var figure = document.getElementById("find-photo");
  findStatus("");
  findSentence = answer.sentence;
  figure.setAttribute("data-state", answer.found ? "found" : "missing");
  if (answer.found) {
    drawHalo(answer.box, answer.width, answer.height);
  }
  // A screen reader hears the sentence as the photo's description.
  document.getElementById("find-image").alt = answer.sentence;
  var words = document.getElementById("find-answer");
  setText(words, answer.sentence);
  document.getElementById("find-after").hidden = false;
  document.getElementById("find-other").hidden = false;
  words.focus();
  speak(answer.sentence);
}

// ---------- The halo ----------

// A soft ring in Buddy's colors around her thing, a little bigger than it
// (never too small to see, even for keys), and the rest of the photo dimmed
// like a spotlight. The SVG uses the photo's own pixels, like SAM's box.
// It draws itself once; with Calm motion it is simply there (styles.css).
function drawHalo(box, width, height) {
  var longest = Math.max(width, height);
  var centerX = (box.x1 + box.x2 + 1) / 2;
  var centerY = (box.y1 + box.y2 + 1) / 2;
  var radiusX = Math.max((box.x2 - box.x1 + 1) * 0.68 + longest * 0.02, longest * 0.06);
  var radiusY = Math.max((box.y2 - box.y1 + 1) * 0.68 + longest * 0.02, longest * 0.06);
  var line = Math.max(3, longest * 0.007);
  var shape = 'cx="' + centerX.toFixed(1) + '" cy="' + centerY.toFixed(1) +
    '" rx="' + radiusX.toFixed(1) + '" ry="' + radiusY.toFixed(1) + '"';
  var halo = document.getElementById("find-halo");
  halo.setAttribute("viewBox", "0 0 " + width + " " + height);
  // Only numbers go into this drawing, never words from anyone.
  halo.innerHTML =
    '<defs>' +
      '<linearGradient id="find-orb" x1="0" y1="0" x2="1" y2="1">' +
        '<stop offset="0" style="stop-color: var(--orb-amber)"></stop>' +
        '<stop offset="0.35" style="stop-color: var(--orb-peach)"></stop>' +
        '<stop offset="0.7" style="stop-color: var(--orb-rose)"></stop>' +
        '<stop offset="1" style="stop-color: var(--orb-violet)"></stop>' +
      '</linearGradient>' +
      '<filter id="find-soft" x="-50%" y="-50%" width="200%" height="200%">' +
        '<feGaussianBlur stdDeviation="' + (line * 1.6).toFixed(1) + '"></feGaussianBlur>' +
      '</filter>' +
      '<filter id="find-feather" x="-50%" y="-50%" width="200%" height="200%">' +
        '<feGaussianBlur stdDeviation="' + (longest * 0.03).toFixed(1) + '"></feGaussianBlur>' +
      '</filter>' +
      '<mask id="find-spot" maskUnits="userSpaceOnUse" x="0" y="0" width="' + width + '" height="' + height + '">' +
        '<rect width="' + width + '" height="' + height + '" fill="white"></rect>' +
        '<ellipse ' + shape + ' fill="black" filter="url(#find-feather)"></ellipse>' +
      '</mask>' +
    '</defs>' +
    '<rect class="find-dim" width="' + width + '" height="' + height + '" mask="url(#find-spot)"></rect>' +
    '<ellipse class="find-glow" ' + shape + ' stroke="url(#find-orb)" stroke-width="' + (line * 3).toFixed(1) +
      '" filter="url(#find-soft)" pathLength="1"></ellipse>' +
    '<ellipse class="find-edge" ' + shape + ' stroke-width="' + (line * 1.9).toFixed(1) + '" pathLength="1"></ellipse>' +
    '<ellipse class="find-ring" ' + shape + ' stroke="url(#find-orb)" stroke-width="' + line.toFixed(1) +
      '" pathLength="1"></ellipse>';
}

// ---------- Setting up ----------

function startFind() {
  var form = document.getElementById("find-ask");
  var camera = document.getElementById("find-camera");
  var library = document.getElementById("find-library");

  document.querySelectorAll("[data-find-pick]").forEach(function (pick) {
    pick.addEventListener("click", function () { setFindThing(pick.getAttribute("data-find-pick")); });
  });
  // Typing her own words: no quick pick is chosen any more.
  document.getElementById("find-thing").addEventListener("input", function () {
    document.querySelectorAll("[data-find-pick]").forEach(function (pick) {
      pick.setAttribute("aria-pressed", "false");
    });
  });
  // "Take a photo" opens the camera (on a computer, her pictures).
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (knowsWhatToFind()) {
      camera.click();
    }
  });
  document.getElementById("find-choose").addEventListener("click", function () {
    if (knowsWhatToFind()) {
      library.click();
    }
  });
  camera.addEventListener("change", useFindPhoto);
  library.addEventListener("change", useFindPhoto);

  document.getElementById("find-say-again").addEventListener("click", function () { speak(findSentence); });
  document.getElementById("find-retake").addEventListener("click", function () { camera.click(); });
  document.getElementById("find-other").addEventListener("click", function () {
    showFindAsk();
    setFindThing("");
    if (screenDetail()) {
      location.hash = "#/find"; // forget "glasses" from the address too (that shows Find afresh)
    }
    document.getElementById("find-thing").focus();
  });

  // "Say it": her words go through the safety net first (sayit.js), then here.
  SAY_IT_FILL["find-ask"] = function (askForm, words) {
    setFindThing(words);
    speak("Now take a photo of the room.");
  };
  SCREEN_LOADERS.find = showFind;
}

startFind();
