// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 Daniel Sandner
//
// The editor without a server. When the page is opened from a web address instead of `clio.py --edit`, this
// worker runs Python in the browser (Pyodide), loads the CLIo engine into it unchanged, and answers the page's
// questions with the same function the local server uses (engine/editor/service.py). The game lives in this
// worker's memory; nothing is sent anywhere.
// This is a module worker (see app.js): current Pyodide refuses classic ones.

const PYODIDE_VERSION = "314.0.7";
const query = new URL(self.location.href).searchParams;
// ?pyodide=/some/path/ takes Pyodide from elsewhere (a local copy, another mirror)
const INDEX = new URL(query.get("pyodide") || `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`, self.location.href).href;
const ROOT = new URL("../../../", self.location.href).href;       // the repository root, as served

let pyodide = null;
let py = null;

const say = (text) => postMessage({ type: "status", text });

const BOOT = `
import json, sys
sys.path.insert(0, "/app")
from engine import __version__ as VERSION
from engine.editor import EditorError, hosted, service

def _pairs(files):
    return [(str(path), bytes(data)) for path, data in files.to_py()]

def _placed(folder):
    return json.dumps({"game": folder, "home": hosted.found_in[folder]})

def _open(name, files):
    return _placed(hosted.place(name, _pairs(files)))

def _open_zip(name, data):
    return _placed(hosted.place(name, hosted.unzip(bytes(data.to_py()))))

def _changed(game):
    return hosted.changed(game)

def _api(game, path, body):
    try:
        out = service.handle(game, path, json.loads(body))
    except EditorError as err:
        return json.dumps({"ok": False, "error": str(err)})
    except Exception as err:
        return json.dumps({"ok": False, "error": "%s: %s" % (type(err).__name__, err)})
    return out if isinstance(out, bytes) else json.dumps({"ok": True, "data": out})
`;

async function grab(path) {
  const res = await fetch(ROOT + path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`Could not load ${path} (${res.status})`);
  return new Uint8Array(await res.arrayBuffer());
}

async function init() {
  say("Fetching Python…");
  const { loadPyodide } = await import(INDEX + "pyodide.mjs");
  pyodide = await loadPyodide({ indexURL: INDEX });
  say("Loading the CLIo engine…");
  const manifest = await (await fetch(new URL("manifest.json", self.location.href), { cache: "no-cache" })).json();
  const sources = await Promise.all(manifest.engine.map(grab));
  manifest.engine.forEach((path, i) => {
    const to = "/app/" + path;
    pyodide.FS.mkdirTree(to.slice(0, to.lastIndexOf("/")));
    pyodide.FS.writeFile(to, sources[i]);
  });
  pyodide.runPython(BOOT);
  py = { open: pyodide.globals.get("_open"), openZip: pyodide.globals.get("_open_zip"), changed: pyodide.globals.get("_changed"),
         api: pyodide.globals.get("_api") };
  return { version: pyodide.globals.get("VERSION"), python: pyodide.version };
}

// Python's (path, bytes) pairs as [path, Uint8Array] pairs that can cross to the page
function pairs(proxy) {
  const out = proxy.toJs({ create_proxies: false });
  proxy.destroy();
  return out.map(([path, data]) => [path, data instanceof Uint8Array ? data : new Uint8Array(data)]);
}

function tidy(err) {                    // the last line of a Python traceback is the part worth reading
  const lines = String((err && err.message) || err).trim().split("\n");
  return lines[lines.length - 1].replace(/^[A-Za-z_.]*(Error|Exception): /, "");
}

self.onmessage = async (event) => {
  const { id, cmd } = event.data;
  try {
    if (cmd === "init") return postMessage({ id, ok: true, about: await init() });
    if (cmd === "open") {               // a game from the site (paths), or from the user's folder (files)
      let files = event.data.files;
      if (event.data.fetch) {
        say("Fetching the game…");
        const from = event.data.fetch;
        const got = await Promise.all(from.files.map(grab));
        files = from.files.map((path, i) => [path.slice(from.folder.length + 1), got[i]]);
      }
      return postMessage(Object.assign({ id, ok: true }, JSON.parse(py.open(event.data.name, files))));
    }
    if (cmd === "open-zip") return postMessage(Object.assign({ id, ok: true }, JSON.parse(py.openZip(event.data.name, event.data.bytes))));
    if (cmd === "changed") {
      const files = pairs(py.changed(event.data.game));
      return postMessage({ id, ok: true, files }, files.map(([, data]) => data.buffer));
    }
    if (cmd === "api") {
      const out = py.api(event.data.game, event.data.path, event.data.body || "{}");
      if (typeof out === "string") return postMessage({ id, ok: true, json: out });
      const bytes = out.toJs();         // Python bytes -> Uint8Array (a copy)
      out.destroy();
      return postMessage({ id, ok: true, bytes }, [bytes.buffer]);
    }
    throw new Error("unknown command " + cmd);
  } catch (err) {
    postMessage({ id, ok: false, error: tidy(err) });
  }
};
