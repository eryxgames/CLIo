// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Daniel Sandner
//
// Playing CLIo in the browser: this module worker runs Python (Pyodide), loads the engine, clio.py and the games
// into it, and runs clio.py on the page's terminal through engine/web.py. The page (play.mjs) and this worker share
// memory: the page puts the keys the player types into it, and this worker waits on it (Atomics.wait) - a game can
// then wait for a key as it does in a real terminal. Sharing memory needs a page that is cross-origin isolated.

const PYODIDE_VERSION = "314.0.7";
const query = new URL(self.location.href).searchParams;
// ?pyodide=/some/path/ takes Pyodide from elsewhere (a local copy, another mirror)
const INDEX = new URL(query.get("pyodide") || `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`, self.location.href).href;
const ROOT = new URL("../../../", self.location.href).href;       // the repository root, as served
const RING = 65536;                                                // the keys' buffer (bytes)

let ctl = null;     // Int32Array: [0] bytes the page has written, [1] bytes read here, [2] columns, [3] rows,
                    // [4] how often the terminal changed size (back to the same size too: its rows moved all the same)
let ring = null;    // Uint8Array: the keys
const nap = new Int32Array(new SharedArrayBuffer(4));              // waited on to sleep

const say = (text) => postMessage({ type: "status", text });

function bytesOf(data) {                                           // Python bytes (a proxy) -> Uint8Array
  if (data === null || data === undefined) return null;
  if (data instanceof Uint8Array) return data;
  if (typeof data.toJs === "function") {
    const out = data.toJs();
    if (typeof data.destroy === "function") data.destroy();
    return out instanceof Uint8Array ? out : new Uint8Array(out);
  }
  return new Uint8Array(data);
}

// what engine/web.py calls: see its run()
const io = {
  write(text) { postMessage({ type: "out", text }); },
  read(n, ms) {
    let written = Atomics.load(ctl, 0);
    let done = Atomics.load(ctl, 1);
    if (written === done && ms !== 0) {
      Atomics.wait(ctl, 0, written, ms < 0 ? Infinity : ms);
      written = Atomics.load(ctl, 0);
    }
    const k = Math.min(n, written - done);
    if (k <= 0) return new Uint8Array(0);
    const out = new Uint8Array(k);
    for (let i = 0; i < k; i++) out[i] = ring[(done + i) % RING];
    Atomics.store(ctl, 1, done + k);
    return out;
  },
  size() { return [Atomics.load(ctl, 2) || 80, Atomics.load(ctl, 3) || 24]; },
  changes() { return Atomics.load(ctl, 4); },
  sleep(ms) { if (ms > 0) Atomics.wait(nap, 0, 0, ms); },
  sound(what, path, data, volume) {
    const bytes = bytesOf(data);
    postMessage({ type: "sound", what, path, data: bytes, volume }, bytes ? [bytes.buffer] : []);
  },
  saved(path, data) {
    const bytes = bytesOf(data);
    postMessage({ type: "saved", path, data: bytes }, [bytes.buffer]);
  },
  removed(path) { postMessage({ type: "removed", path }); },
};

// One file of the site. A host that is asked for a few hundred files at once says "not now" to some (429, 5xx):
// those are asked for again, a little later each time, before the page gives up.
async function grab(path) {
  for (let turn = 0; ; turn++) {
    let res = null;
    try {
      res = await fetch(ROOT + path, { cache: "no-cache" });
    } catch (e) {
      if (turn >= 3) throw new Error(`Could not load ${path} (${e.message || e})`);
    }
    if (res && res.ok) return new Uint8Array(await res.arrayBuffer());
    if (res && (turn >= 3 || (res.status < 500 && res.status !== 429))) {
      throw new Error(`Could not load ${path} (${res.status})`);
    }
    await new Promise((done) => setTimeout(done, 400 * (turn + 1) * (turn + 1)));
  }
}

async function start({ shared, argv, kept, game }) {
  ctl = new Int32Array(shared, 0, 8);
  ring = new Uint8Array(shared, 32, RING);
  say("Fetching Python…");
  const { loadPyodide } = await import(INDEX + "pyodide.mjs");
  const pyodide = await loadPyodide({ indexURL: INDEX });
  say("Loading CLIo and its games…");
  const manifest = await (await fetch(new URL("manifest.json", self.location.href), { cache: "no-cache" })).json();
  // a game from the editor needs only the engine's own files, not the games that come with CLIo
  const paths = manifest.engine.concat(game ? manifest.play.filter((p) => !p.startsWith("games/")) : manifest.play);
  const files = await Promise.all(paths.map(grab));
  paths.forEach((path, i) => {
    const to = "/app/" + path;
    pyodide.FS.mkdirTree(to.slice(0, to.lastIndexOf("/")));
    pyodide.FS.writeFile(to, files[i]);
  });
  for (const [path, data] of game ? game.files : []) {             // the game the editor handed over, as saved there
    const parts = String(path).split("/").filter((p) => p && p !== "." && p !== "..");
    if (!parts.length) continue;
    const to = game.dir + "/" + parts.join("/");
    pyodide.FS.mkdirTree(to.slice(0, to.lastIndexOf("/")));
    pyodide.FS.writeFile(to, data);
  }
  for (const [path, data] of kept || []) {                         // saves and records from earlier visits
    if (!path.startsWith("/data/")) continue;
    pyodide.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
    pyodide.FS.writeFile(path, data);
  }
  pyodide.registerJsModule("clio_page", io);
  say("");
  postMessage({ type: "started" });
  pyodide.globals.set("ARGV", argv || []);
  const code = pyodide.runPython(`
import os, sys
sys.path.insert(0, "/app")
os.chdir("/app")
import clio_page
from engine import web
web.run(clio_page, list(ARGV))
`);
  postMessage({ type: "ended", code });
}

self.onmessage = async (event) => {
  if (event.data.cmd !== "start") return;
  try {
    await start(event.data);
  } catch (err) {
    const lines = String((err && err.message) || err).trim().split("\n");
    postMessage({ type: "failed", error: lines.slice(-12).join("\n") });
  }
};
