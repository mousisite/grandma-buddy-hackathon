// Grandma Buddy's service worker: the app shell (the page, its styles,
// scripts, fonts, and icons) is kept on this device, so Buddy opens from
// its home-screen icon even when its server isn't running, and shows a
// kind page saying so. Everything is fetched from the network first, so a
// change to the app arrives at once; the copy here is only for when the
// network can't answer.
//
// Her data and the AI are never kept here: nothing under /api/ is ever
// cached (every answer there is hers, and fresh).

"use strict";

var VERSION = "buddy-shell-v1";
var NEVER_CACHED = "/api/";
var OFFLINE_PAGE = "/static/offline.html";
var SHELL = [
  "/",
  OFFLINE_PAGE,
  "/static/styles.css",
  "/static/app.js",
  "/static/buddy.js",
  "/static/speech.js",
  "/static/talk.js",
  "/static/listen.js",
  "/static/screens.js",
  "/static/sayit.js",
  "/static/welcome.js",
  "/static/find.js",
  "/static/read.js",
  "/static/sharing.js",
  "/static/herdata.js",
  "/static/recorder.js",
  "/static/pcm-worklet.js",
  "/static/fonts/Figtree.ttf",
  "/static/fonts/Figtree-Italic.ttf",
  "/static/fonts/Newsreader.ttf",
  "/static/icons/buddy-192.png",
  "/static/icons/buddy-512.png",
  "/static/manifest.webmanifest",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(VERSION).then(function (cache) { return cache.addAll(SHELL); }).then(function () {
      return self.skipWaiting();
    })
  );
});

// A new version: old shells are let go.
self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(names.filter(function (name) { return name !== VERSION; }).map(function (name) {
        return caches.delete(name);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var request = event.request;
  var url = new URL(request.url);
  // Only this app's own pages and files; never her data or the AI, never another site.
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith(NEVER_CACHED)) {
    return;
  }
  event.respondWith(
    fetch(request).then(function (response) {
      // Fresh from the network; keep a copy for next time.
      if (response.ok && (request.mode === "navigate" || SHELL.indexOf(url.pathname) !== -1)) {
        var copy = response.clone();
        caches.open(VERSION).then(function (cache) { cache.put(request.mode === "navigate" ? "/" : request, copy); });
      }
      return response;
    }).catch(function () {
      // The server isn't answering: the kept page, else the "Buddy isn't running" page.
      return caches.match(request.mode === "navigate" ? "/" : request).then(function (kept) {
        return kept || (request.mode === "navigate" ? caches.match(OFFLINE_PAGE) : Response.error());
      });
    })
  );
});
