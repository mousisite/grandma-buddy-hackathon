// Grandma Buddy: Settings, "Her data" (for a family member).
// - Export everything is a plain link to /api/data/export: one zip file.
// - Delete everything opens a sheet that asks for the word DELETE, typed,
//   before the button works (app/her_data.py). Afterward this device's
//   remembered choices are cleared too, and Buddy opens on the welcome.

"use strict";

function startHerData() {
  var dialog = document.getElementById("delete-dialog");
  var word = document.getElementById("delete-word");
  var yes = document.getElementById("delete-yes");
  var status = document.getElementById("delete-status");

  document.getElementById("data-delete").addEventListener("click", function () {
    word.value = "";
    yes.disabled = true;
    status.textContent = "";
    dialog.showModal();
  });
  word.addEventListener("input", function () {
    yes.disabled = word.value.trim() !== "DELETE";
  });
  document.getElementById("delete-no").addEventListener("click", function () {
    dialog.close();
  });
  // "Reset the demo week", in demo mode only (the server says).
  var resetBox = document.getElementById("demo-reset-box");
  var reset = document.getElementById("demo-reset");
  var resetStatus = document.getElementById("demo-reset-status");
  // Plain fetch: app.js (which defines api) loads after this file.
  fetch("/api/demo")
    .then(function (response) { return response.json(); })
    .then(function (state) {
      resetBox.hidden = !state.demo;
      if (state.public) {
        // A public demo on the web: her data isn't taken or wiped there.
        document.getElementById("data-export").hidden = true;
        document.getElementById("data-delete").hidden = true;
        document.getElementById("demo-fresh").hidden = true; // the public demo keeps Rose's week
      }
    })
    .catch(function () {});
  reset.addEventListener("click", function () {
    askFirst("Reset the demo week?",
      "A copy of what is here is saved first. Then Buddy is filled with Rose’s made-up week again, ending today.",
      "Yes, reset it", function () {
        document.getElementById("confirm-dialog").close();
        reset.disabled = true;
        resetStatus.textContent = "Resetting…";
        api("/api/demo/reset", "POST", {})
          .then(function (done) {
            resetStatus.textContent = "The demo week is back, ending today." +
              (done.painting ? " The Memory book pictures are being painted (about a minute)." : "");
            try { localStorage.removeItem("checkin-seen"); } catch (e) {}
            setTimeout(function () { window.location.replace("/"); }, 1500); // Home, loaded afresh
          })
          .catch(function (problem) {
            reset.disabled = false;
            resetStatus.textContent = typeof problem.detail === "string" ? problem.detail
              : "I couldn’t reset it just now. Please try again.";
          });
      });
  });

  // "Start fresh for a real person": a backup, an empty Buddy, the welcome
  // screen next (app.js opens it when no name is saved), and the demo week
  // never loaded by itself again (app/demo.py remembers "F").
  var fresh = document.getElementById("demo-fresh");
  fresh.addEventListener("click", function () {
    askFirst("Start fresh for a real person?",
      "A copy of what is here is saved first. Then Buddy is emptied, as on its first day, and opens its welcome screen so you can set it up for her. The demo week won’t come back on the next start.",
      "Yes, start fresh", function () {
        document.getElementById("confirm-dialog").close();
        fresh.disabled = true;
        resetStatus.textContent = "Clearing the demo week…";
        api("/api/demo/fresh", "POST", {})
          .then(function () {
            resetStatus.textContent = "Done. Opening the welcome screen…";
            try { localStorage.removeItem("checkin-seen"); } catch (e) {}
            setTimeout(function () { window.location.replace("/"); }, 1200);
          })
          .catch(function (problem) {
            fresh.disabled = false;
            resetStatus.textContent = typeof problem.detail === "string" ? problem.detail
              : "I couldn’t clear it just now. Please try again.";
          });
      });
  });

  yes.addEventListener("click", function () {
    yes.disabled = true;
    status.textContent = "Deleting…";
    api("/api/data/delete", "POST", { confirm: word.value.trim() })
      .then(function () {
        try { localStorage.clear(); } catch (e) {}
        window.location.href = "/"; // the first day again: the welcome
        window.location.reload();
      })
      .catch(function (problem) {
        yes.disabled = false;
        status.textContent = typeof problem.detail === "string" ? problem.detail
          : "I couldn’t delete it just now. Please try again.";
      });
  });
}

startHerData();
