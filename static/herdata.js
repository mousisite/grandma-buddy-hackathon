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
