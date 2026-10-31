// Grandma Buddy: Settings, "Family accounts" (for a family member).
// - Invite a family member: a six-letter code (/api/family/invite) they
//   type on the family page (/family) to join. It works once, for 24 hours.
// - Who can sign in: the family accounts, each with "Remove" (asks first;
//   removing ends their sessions at once).
// - "What your family can see" are ordinary switches, saved like the
//   others (screens.js saveChoice).
// - "Remind me even when Buddy is hidden" asks the browser's permission for
//   notifications first; it is saved only when that is given.

"use strict";

function showFamilyAccounts() {
  var group = document.getElementById("family-accounts");
  api("/api/family/accounts")
    .then(function (accounts) {
      group.textContent = "";
      if (!accounts.length) {
        group.appendChild(element("p", "group-row empty", "No one yet. Invite a family member below."));
        return;
      }
      accounts.forEach(function (account) {
        var row = element("div", "group-row");
        row.setAttribute("role", "listitem");
        var words = element("span", "group-label", account.name);
        words.appendChild(element("span", "group-hint", account.email));
        row.appendChild(words);
        row.appendChild(smallButton("Remove", "Remove " + account.name + "’s account", function () {
          askFirst("Remove this account?", account.name + " will no longer be able to sign in to the family page.",
            "Yes, remove it", function () { removeFamilyAccount(account); });
        }));
        group.appendChild(row);
      });
    })
    .catch(function () {
      setText(document.getElementById("family-accounts-status"), "I couldn’t show the accounts just now. Please try again in a moment.");
    });
}

function removeFamilyAccount(account) {
  document.getElementById("confirm-dialog").close();
  var status = document.getElementById("family-accounts-status");
  api("/api/family/accounts/" + account.id, "DELETE")
    .then(function () {
      status.textContent = "Removed " + account.name + "’s account.";
      focusScreenHeading(); // the Remove button she tapped is gone
      showFamilyAccounts();
    })
    .catch(function () {
      status.textContent = "I couldn’t remove that just now. Please try again.";
    });
}

// "Invite a family member": the code, shown big, with how to use it.
function inviteFamilyMember() {
  var button = document.getElementById("family-invite");
  var card = document.getElementById("family-invite-card");
  button.disabled = true;
  api("/api/family/invite", "POST", {})
    .then(function (invite) {
      setText(document.getElementById("family-invite-code"), invite.code);
      card.hidden = false;
      button.textContent = "Make another code";
    })
    .catch(function () {
      setText(document.getElementById("family-accounts-status"), "I couldn’t make a code just now. Please try again.");
    })
    .then(function () {
      button.disabled = false;
    });
}

// "Remind me even when Buddy is hidden": the browser's permission first.
// Saved only once it is given; the form's own saving is skipped meanwhile.
function changeNotifyHidden(event) {
  var box = event.target;
  if (!box.checked) {
    return; // turning it off saves like any switch (screens.js)
  }
  event.stopPropagation();
  var status = document.getElementById("settings-status");
  if (!("Notification" in window)) {
    box.checked = false;
    status.textContent = "This browser can’t show notifications.";
    return;
  }
  Notification.requestPermission().then(function (permission) {
    if (permission !== "granted") {
      box.checked = false;
      status.textContent = "Notifications are blocked for Buddy. Allow them in the browser’s settings, then try again.";
      return;
    }
    api("/api/profile", "PUT", { notify_hidden: true })
      .then(function (saved) {
        useProfile(saved);
        status.textContent = "";
        toast("Settings saved");
      })
      .catch(function () {
        box.checked = false;
        status.textContent = "I couldn’t save that just now. Please try again.";
      });
  });
}

// A pill reminder as a system notification while Buddy is hidden behind
// another window (screens.js showPillBanner calls this for each new one).
var notifiedReminders = "";

function notifyWhenHidden(card, which) {
  if (which === notifiedReminders || !document.hidden || profile.notify_hidden !== true ||
      !("Notification" in window) || Notification.permission !== "granted") {
    return;
  }
  notifiedReminders = which;
  var labels = card.pills.map(function (pill) {
    return pill.label_dose ? pill.name + ": " + pill.label_dose : pill.name;
  }).join("\n");
  var note = new Notification(card.title, { body: labels, tag: "buddy-pill-" + which });
  note.addEventListener("click", function () {
    window.focus();
    note.close();
  });
}

function startSharing() {
  document.getElementById("family-invite").addEventListener("click", inviteFamilyMember);
  document.querySelector('input[name="notify_hidden"]').addEventListener("change", changeNotifyHidden);
  // The accounts load when the Settings screen opens (screens.js).
  var loadSettings = SCREEN_LOADERS.settings;
  SCREEN_LOADERS.settings = function () {
    loadSettings();
    showFamilyAccounts();
  };
}

startSharing();
