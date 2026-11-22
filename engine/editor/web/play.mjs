// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Daniel Sandner
//
// play.html: a terminal (xterm.js) for CLIo running in a worker (play.js). The keys typed go into memory the worker
// shares; what the game writes comes back as messages; sounds are played with WebAudio; saves and records are kept
// in this browser (IndexedDB) and handed back on the next visit.
//
//   play.html?game=rootless      a game (rootless, depths, derelict); none: CLIo's own menu of games
//   play.html?demo               the tech demo
//   play.html?edited=ID          the game the editor hands over (its Play button), as last saved
//   ?pyodide=URL ?npm=URL        Python and xterm.js from elsewhere than jsDelivr (a local copy, another mirror)

const query = new URLSearchParams(location.search);
const NPM = query.get("npm") || "https://cdn.jsdelivr.net/npm/";
const XTERM = NPM + "@xterm/xterm@6.0.0/";
const FIT = NPM + "@xterm/addon-fit@0.11.0/lib/addon-fit.mjs";
const WEBGL = NPM + "@xterm/addon-webgl@0.19.0/lib/addon-webgl.mjs";
const RING = 65536;
const GAMES = { rootless: "RØØTLESS", depths: "The Hollow", derelict: "Derelict" };
const $ = (id) => document.getElementById(id);
const EMBEDDED = (() => { try { return window.top !== window.self; } catch (err) { return true; } })();
const EDITED = query.get("edited");
const EDITED_DIR = "/edited/" + (String(EDITED || "").replace(/[^A-Za-z0-9_.-]+/g, "_").replace(/^\.+/, "") || "game");

function cover(text, choices = [], error = "") {
  $("say").textContent = text;
  const box = $("choices");
  box.replaceChildren(...choices.map(([label, act, quiet]) => {
    const el = typeof act === "string" ? Object.assign(document.createElement("a"), { href: act })
      : Object.assign(document.createElement("button"), { type: "button", onclick: act });
    if (typeof act === "string" && act.startsWith("http")) el.target = "_blank";
    el.textContent = label;
    if (quiet) el.className = "quiet";
    return el;
  }));
  if (error) box.append(Object.assign(document.createElement("pre"), { textContent: error }));
  $("cover").hidden = false;
}

function argv() {
  if (EDITED) return [EDITED_DIR];
  if (query.has("demo")) return ["--demo"];
  const game = query.get("game");
  return game && GAMES[game] ? [game] : [];
}

// ---------------------------------------------------------------- shared memory: needs cross-origin isolation
async function isolate() {
  if (self.crossOriginIsolated) return true;
  if (!EMBEDDED && "serviceWorker" in navigator && !sessionStorage.getItem("clio-coi-tried")) {
    // a static site (GitHub Pages) cannot send the headers: a service worker of ours adds them, then a reload
    sessionStorage.setItem("clio-coi-tried", "1");
    try {
      await navigator.serviceWorker.register("coi.js");
      await navigator.serviceWorker.ready;
      location.reload();
      return false;
    } catch (err) { /* fall through */ }
  }
  const here = location.href;
  if (EDITED && EMBEDDED) {                                  // a new tab would not see the game the editor handed over
    cover("This frame does not let a game and its keys share memory. Open the editor in a tab of its own, open your game there and press Play.",
      [["The editor in a new tab", editorUrl()], ["Back to the editor", backToEditor, true]]);
    return false;
  }
  cover(EMBEDDED
    ? "This page can play CLIo only in a tab of its own here (the game and its keys share memory, which this frame does not allow)."
    : "This browser did not allow the game and its keys to share memory, which playing needs.",
  EMBEDDED ? [["Play in a new tab", here]] : [["Try again", () => { sessionStorage.removeItem("clio-coi-tried"); location.reload(); }]]);
  return false;
}

// ---------------------------------------------------------------- the game from the editor
function editorUrl(more = {}) {
  const url = new URL("index.html", location.href);
  for (const [k, v] of Object.entries(more)) url.searchParams.set(k, v);
  for (const k of ["pyodide", "npm"]) if (query.get(k)) url.searchParams.set(k, query.get(k));
  return url.href;
}
function backToEditor() {
  let opener = null;
  try { opener = window.opener && !window.opener.closed ? window.opener : null; } catch (err) { /* another site's */ }
  if (opener) {                                              // the editor is still open in the tab that opened this one
    try { opener.focus(); } catch (err) { /* it is there all the same */ }
    window.close();
    setTimeout(() => { location.href = editorUrl(); }, 300);   // a tab the browser would not close
    return;
  }
  location.href = editorUrl({ open: EDITED });               // played in the editor's own frame: open the game there again
}
function handedOver(id) {
  return new Promise((resolve) => {
    let opening;
    try { opening = indexedDB.open("clio-editor-play", 1); } catch (err) { return resolve(null); }
    opening.onupgradeneeded = () => opening.result.createObjectStore("games", { keyPath: "id" });
    opening.onerror = () => resolve(null);
    opening.onsuccess = () => {
      let req;
      try { req = opening.result.transaction("games").objectStore("games").get(id); } catch (err) { opening.result.close(); return resolve(null); }
      req.onsuccess = () => { opening.result.close(); resolve(req.result || null); };
      req.onerror = () => { opening.result.close(); resolve(null); };
    };
  });
}

// ---------------------------------------------------------------- saves kept between visits
function db() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open("clio-play", 1);
    req.onupgradeneeded = () => req.result.createObjectStore("files");
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function keptFiles() {
  try {
    const d = await db();
    return await new Promise((resolve) => {
      const out = [], tx = d.transaction("files").objectStore("files").openCursor();
      tx.onsuccess = () => { const c = tx.result; if (c) { out.push([c.key, c.value]); c.continue(); } else resolve(out); };
      tx.onerror = () => resolve(out);
    });
  } catch (err) { return []; }
}
async function keep(path, data) {
  try { const d = await db(); d.transaction("files", "readwrite").objectStore("files").put(data, path); } catch (err) { /* not kept */ }
}
async function forget(path) {
  try { const d = await db(); d.transaction("files", "readwrite").objectStore("files").delete(path); } catch (err) { /* gone anyway */ }
}

// ---------------------------------------------------------------- sound
const sound = { ctx: null, buffers: new Map(), raw: new Map(), loop: null, queue: [] };
function audio() {
  if (!sound.ctx) {
    try { sound.ctx = new AudioContext(); } catch (err) { return null; }
  }
  if (sound.ctx.state === "suspended") sound.ctx.resume();
  return sound.ctx;
}
async function buffer(path) {
  if (sound.buffers.has(path)) return sound.buffers.get(path);
  const data = sound.raw.get(path);
  if (!data || !audio()) return null;
  const got = sound.ctx.decodeAudioData(data.slice().buffer);
  sound.buffers.set(path, got);
  return got;
}
async function play({ what, path, data, volume }) {
  if (data) sound.raw.set(path, data);
  if (what === "stop") {
    if (sound.loop) { try { sound.loop.stop(); } catch (err) { /* stopped */ } sound.loop = null; }
    sound.wanted = null;
    return;
  }
  if (what === "loop") sound.wanted = path;
  const ctx = audio();
  if (!ctx || ctx.state !== "running") {                    // no key pressed yet: the browser keeps it quiet
    if (what === "loop") sound.pending = { what, path, volume };
    return;
  }
  const buf = await buffer(path);
  if (!buf || (what === "loop" && sound.wanted !== path)) return;
  const src = ctx.createBufferSource();
  const gain = ctx.createGain();
  gain.gain.value = Math.max(0, Math.min(1, volume));
  src.buffer = buf;
  src.connect(gain).connect(ctx.destination);
  if (what === "loop") {
    if (sound.loop) { try { sound.loop.stop(); } catch (err) { /* stopped */ } }
    src.loop = true;
    sound.loop = src;
  }
  src.start();
}
function unmute() {                                         // the first key or tap: sound may start
  const ctx = audio();
  if (ctx && sound.pending) {
    const p = sound.pending;
    sound.pending = null;
    ctx.resume().then(() => play(p));
  }
}

// ---------------------------------------------------------------- the terminal and the game
async function main() {
  if (!(await isolate())) return;
  let edited = null;
  if (EDITED) {
    edited = await handedOver(EDITED);
    if (!edited) {
      return cover("There is no game from the editor here. Open it in the editor and press Play there.", [["Back to the editor", backToEditor]]);
    }
    document.title = edited.title + " - CLIo";
    $("bar-title").textContent = `${edited.title}, as saved in the editor`;
    $("bar-again").addEventListener("click", () => location.reload());
    $("bar-back").addEventListener("click", backToEditor);
    $("bar").hidden = false;
  }
  cover("Fetching the terminal…");
  const link = Object.assign(document.createElement("link"), { rel: "stylesheet", href: XTERM + "css/xterm.css" });
  document.head.append(link);
  const [{ Terminal }, { FitAddon }] = await Promise.all([import(XTERM + "lib/xterm.mjs"), import(FIT)]);
  const touch = matchMedia("(pointer: coarse)").matches;
  if (touch) document.body.classList.add("touch");
  const size = Math.max(9, Math.min(17, Math.floor(window.innerWidth / (touch ? 60 : 105) / 0.6)));
  const term = new Terminal({
    fontFamily: '"DejaVu Sans Mono", "Cascadia Mono", "Cascadia Code", Consolas, Menlo, "Liberation Mono", monospace',
    fontSize: size, lineHeight: 1, letterSpacing: 0, cursorBlink: false, scrollback: 0, convertEol: true,    // a newline returns to the left, as a terminal does
    theme: { background: "#0b0b10", foreground: "#d6ecff" }, allowProposedApi: true,
  });
  const fit = new FitAddon();
  term.loadAddon(fit);
  term.open($("screen"));
  try {                                                      // blocks and braille drawn exactly, where WebGL is there
    const { WebglAddon } = await import(WEBGL);
    term.loadAddon(new WebglAddon());
  } catch (err) { /* the DOM renderer draws them with the font */ }
  fit.fit();
  term.focus();
  window.clio = { term };                                    // for a look from the browser's console, and tests

  const shared = new SharedArrayBuffer(16 + RING);
  const ctl = new Int32Array(shared, 0, 4);
  const ring = new Uint8Array(shared, 16, RING);
  const sizeTo = () => { Atomics.store(ctl, 2, term.cols); Atomics.store(ctl, 3, term.rows); Atomics.notify(ctl, 0); };
  sizeTo();
  term.onResize(sizeTo);
  new ResizeObserver(() => fit.fit()).observe($("screen"));
  const encode = new TextEncoder();
  const send = (text) => {
    unmute();
    const bytes = encode.encode(text);
    const written = Atomics.load(ctl, 0);
    if (written - Atomics.load(ctl, 1) + bytes.length > RING) return;     // far behind: dropped, as a terminal would
    for (let i = 0; i < bytes.length; i++) ring[(written + i) % RING] = bytes[i];
    Atomics.store(ctl, 0, written + bytes.length);
    Atomics.notify(ctl, 0);
  };
  term.onData(send);
  term.onTitleChange((title) => { document.title = title || (edited ? edited.title + " - CLIo" : "CLIo"); });
  for (const b of document.querySelectorAll("#keys button[data-key]")) {
    b.addEventListener("pointerdown", (e) => { e.preventDefault(); send(b.dataset.key); });
  }
  $("type").addEventListener("click", () => term.focus());
  $("screen").addEventListener("pointerdown", unmute);

  cover("Fetching Python… (about 10 MB the first time; the browser keeps it after)");
  const worker = new Worker("play.js" + location.search, { type: "module" });
  worker.onmessage = (event) => {
    const m = event.data;
    if (m.type === "out") term.write(m.text);
    else if (m.type === "status") { if (m.text) cover(m.text); }
    else if (m.type === "started") { $("cover").hidden = true; term.focus(); }
    else if (m.type === "sound") play(m);
    else if (m.type === "saved") keep(m.path, m.data);
    else if (m.type === "removed") forget(m.path);
    else if (m.type === "ended") {
      play({ what: "stop" });
      cover("The game is over.", edited ? [["Play again", () => location.reload()], ["Back to the editor", backToEditor, true]]
        : [["Play again", () => location.reload()], ["All games", "play.html", true], ["Back", "../../../index.html", true]]);
    } else if (m.type === "failed") {
      cover("CLIo could not start here.", [["Try again", () => location.reload()]], m.error);
    }
  };
  worker.onerror = (e) => cover("CLIo could not start here.", [["Try again", () => location.reload()]], e.message || "");
  const game = edited ? { dir: EDITED_DIR, files: edited.files } : null;
  worker.postMessage({ cmd: "start", shared, argv: argv(), kept: await keptFiles(), game });
}

main().catch((err) => cover("CLIo could not start here.", [["Try again", () => location.reload()]], String(err && err.stack || err)));
