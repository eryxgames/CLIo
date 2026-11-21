// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Daniel Sandner
//
// A service worker that makes play.html cross-origin isolated on a host that cannot send the headers itself (a
// static site such as GitHub Pages): every page and script of this folder is given them on its way in. Playing needs
// it - the game in its worker and the page share memory for the keys (SharedArrayBuffer). Hosts that send the
// headers themselves (itch.io's "SharedArrayBuffer support") never need it.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.cache === "only-if-cached" && req.mode !== "same-origin") return;
  if (new URL(req.url).origin !== self.location.origin) return;     // other sites' files go as they are (CORS)
  event.respondWith(fetch(req).then((res) => {
    if (res.status === 0) return res;
    const headers = new Headers(res.headers);
    headers.set("Cross-Origin-Embedder-Policy", "require-corp");
    headers.set("Cross-Origin-Opener-Policy", "same-origin");
    headers.set("Cross-Origin-Resource-Policy", "same-origin");
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  }).catch(() => fetch(req)));
});
