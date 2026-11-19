# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""Sound effects from the engine of Ballistic Foley Lab: shots, blasts, ricochets, impacts, arcs and fields,
modelled from physics rather than drawn as waves.

A game names one in ``sounds.json``, or in a sound set (``sounds.<set>.json``), like any other sound::

    "pistol": {"ballistic": "pistol", "p": {"D": 0, "env": "indoor"}, "vol": 0.8, "variations": 6, "length": 1.2}

``"ballistic"`` is one of Ballistic's presets (or an object of parameters), ``"p"`` changes some of its
parameters, ``"action"`` adds Ballistic's finishing for action (``"game"``: punch, weight and loudness, as a
game wants; or an object of action parameters), ``"vol"`` is the peak level, ``"variations"`` how many takes
to render (each shot plays another), ``"length"`` where to cut, ``"channels"`` 1 for mono.

The engine is JavaScript: ``engine.js`` is a copy of Ballistic's ``src/engine.js`` (see README.md), and
``render.cjs`` runs it in Node.js - one process for the whole game, rendering in the background, the takes
kept in CLIo's audio cache.  Where the C port of the engine (Ballistic Engine, libballistic) is installed, the
kinds it has ported render through it instead, in this process and several times faster, without Node.  A game can also ship the takes as WAV files (``clio.py GAME --bake-sounds SET``),
which play without Node.  With neither, the game's own sound of that name plays instead (or the spec's
``"fallback"``), so a game never goes silent for want of Node.
"""
from __future__ import annotations

import collections
import ctypes
import ctypes.util
import hashlib
import heapq
import itertools
import json
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from array import array

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "engine.js")
RUNNER = os.path.join(HERE, "render.cjs")
BAKED = "baked.json"
BAKED_FORMAT = "clio-ballistic-baked"
RENDER_TIMEOUT = 30.0           # seconds one take may take before Node is thought stuck
MAX_CRASHES = 3                 # Node is started again after it stops on its own, this many times
ENGINE_COMMIT = "3603078"       # the Ballistic commit engine.js is a copy of; the C engine must follow the same

_known = None
_engine_id = None


class RenderError(Exception):
    """Node could not render: it is missing, stopped, or took too long."""


# --------------------------------------------------------------------------- #
# the spec
# --------------------------------------------------------------------------- #
def is_spec(raw):
    """Whether a sound in sounds.json is one of Ballistic's."""
    return isinstance(raw, dict) and "ballistic" in raw


def _num(v, default, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    if v != v:
        return default
    return max(lo, min(hi, v))


def spec_of(raw):
    """A Ballistic sound, normalised: preset, parameters, level, takes, length, channels, first seed."""
    if not is_spec(raw):
        return None
    b = raw.get("ballistic")
    over = raw.get("p") if isinstance(raw.get("p"), dict) else {}
    if isinstance(b, dict):
        preset, p = "", dict(b)
        p.update(over)
    else:
        preset, p = str(b or ""), dict(over)
    action = raw.get("action")
    if not isinstance(action, (str, dict)) or action in ("", "none"):
        action = None
    return {"preset": preset, "p": p, "action": action,
            "vol": _num(raw.get("vol"), 0.7, 0.0, 1.0),
            "variations": int(_num(raw.get("variations"), 4, 1, 12)),
            "length": _num(raw.get("length"), 2.5, 0.05, 30.0),
            "channels": 1 if raw.get("channels") == 1 else 2,
            "seed": int(_num(raw.get("seed"), 1, 1, 1e9))}


def engine_id():
    """Changes when the engine or the runner changes, so their takes are rendered again."""
    global _engine_id
    if _engine_id is None:
        h = hashlib.sha1()
        for path in (ENGINE, RUNNER):
            try:
                with open(path, "rb") as f:
                    h.update(f.read())
            except OSError:
                h.update(b"-")
        _engine_id = h.hexdigest()[:12]
    return _engine_id


def _block(text, head):
    """The bracketed block that starts at ``head`` (strings and comments skipped), or ''."""
    i = text.find(head)
    if i < 0:
        return ""
    i += len(head) - 1
    depth, j, n = 0, i, len(text)
    while j < n:
        c = text[j]
        if c in "'\"`":
            k = j + 1
            while k < n and text[k] != c:
                k += 2 if text[k] == "\\" else 1
            j = k
        elif text.startswith("//", j):
            j = text.find("\n", j)
            if j < 0:
                return ""
        elif text.startswith("/*", j):
            j = text.find("*/", j)
            if j < 0:
                return ""
            j += 1
        elif c in "[{(":
            depth += 1
        elif c in "]})":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
        j += 1
    return ""


def _top_keys(block):
    """The keys of a JavaScript object literal, at its top level."""
    keys, depth, j, n = [], 0, 0, len(block)
    expect = False
    while j < n:
        c = block[j]
        if c in "'\"`":
            k = j + 1
            while k < n and block[k] != c:
                k += 2 if block[k] == "\\" else 1
            j = k + 1
            expect = False
            continue
        if block.startswith("//", j):
            j = block.find("\n", j)
            j = n if j < 0 else j
            continue
        if block.startswith("/*", j):
            j = block.find("*/", j)
            j = n if j < 0 else j + 2
            continue
        if c in "[{(":
            depth += 1
            expect = depth == 1
        elif c in "]})":
            depth -= 1
        elif c == "," and depth == 1:
            expect = True
        elif expect and not c.isspace():
            m = re.match(r"([A-Za-z_$][\w$]*)\s*:", block[j:])
            if m:
                keys.append(m.group(1))
                j += m.end()
            expect = False
            continue
        j += 1
    return keys


def known():
    """``(presets, parameters, action presets, action parameters)``: the names engine.js knows, read from it
    without running it.  Empty sets where the engine is not there (the editor in a browser has only the Python)."""
    global _known
    if _known is None:
        try:
            with open(ENGINE, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return set(), set(), set(), set()

        def ids(head):
            return set(re.findall(r"\{\s*id:\s*'([^']+)'", _block(text, head)))

        _known = (ids("var PRESETS = ["), set(_top_keys(_block(text, "var DEFAULTS = {"))),
                  ids("var ACTION_PRESETS = ["), set(_top_keys(_block(text, "var ACTION_DEFAULTS = {"))))
    return _known


def problems(raw, where):
    """What is wrong with a Ballistic sound, as lines for ``--check``."""
    out = []
    b = raw.get("ballistic")
    if not isinstance(b, (str, dict)) or b == "":
        return ["%s: \"ballistic\" should be the name of a preset or an object of parameters" % where]
    if "p" in raw and not isinstance(raw["p"], dict):
        out.append("%s: \"p\" should be an object of parameters" % where)
    presets, keys, actions, action_keys = known()
    if not presets:
        return out
    s = spec_of(raw)
    if s["preset"] and s["preset"] not in presets:
        out.append("%s: Ballistic has no preset '%s'" % (where, s["preset"]))
    bad = sorted(k for k in s["p"] if k not in keys)
    if bad:
        out.append("%s: Ballistic has no parameter%s %s" % (where, "s" if len(bad) > 1 else "", ", ".join(bad)))
    a = raw.get("action")
    if isinstance(a, str) and a not in actions and a != "none":
        out.append("%s: Ballistic has no action preset '%s' (there are: %s)" % (where, a, ", ".join(sorted(actions))))
    elif isinstance(a, dict):
        bad = sorted(k for k in a if k not in action_keys)
        if bad:
            out.append("%s: Ballistic has no action parameter%s %s" % (where, "s" if len(bad) > 1 else "", ", ".join(bad)))
    elif a is not None and not isinstance(a, str):
        out.append("%s: \"action\" should be an action preset or an object of action parameters" % where)
    if "channels" in raw and raw["channels"] not in (1, 2):
        out.append("%s: \"channels\" should be 1 or 2" % where)
    return out


def find_node(env=None):
    """The Node.js to run the engine with: ``CLIO_NODE`` if set (``none`` for none), else node on the PATH."""
    env = os.environ if env is None else env
    want = env.get("CLIO_NODE")
    if want:
        if want.lower() in ("none", "off", "no", "0"):
            return None
        return want if os.path.isfile(want) else shutil.which(want)
    return shutil.which("node") or shutil.which("nodejs")


def find_clib(env=None):
    """The C engine's library: ``CLIO_BALLISTIC_LIB`` if set (``none`` for none), else one in
    engine/audio/ballistic/lib/, else ``ballistic`` where the system keeps libraries."""
    env = os.environ if env is None else env
    want = env.get("CLIO_BALLISTIC_LIB")
    if want:
        return None if want.lower() in ("none", "off", "no", "0") else want
    names = {"win32": ["ballistic.dll"], "darwin": ["libballistic.dylib"]}.get(sys.platform, ["libballistic.so"])
    for name in names:
        p = os.path.join(HERE, "lib", name)
        if os.path.isfile(p):
            return p
    return ctypes.util.find_library("ballistic")


# --------------------------------------------------------------------------- #
# the C engine (Ballistic Engine), when it is installed
# --------------------------------------------------------------------------- #
class _Sound(ctypes.Structure):
    _fields_ = [("L", ctypes.POINTER(ctypes.c_float)), ("R", ctypes.POINTER(ctypes.c_float)),
                ("n", ctypes.c_int), ("rate", ctypes.c_int), ("peak_pa", ctypes.c_double), ("spl", ctypes.c_double),
                ("events", ctypes.c_void_p), ("n_events", ctypes.c_int)]


class CEngine:
    """libballistic through ctypes. Answers the same requests as render.cjs, for the kinds it has ported."""

    def __init__(self, path):
        lib = ctypes.CDLL(path)
        P, S, C, D, I = ctypes.c_void_p, ctypes.POINTER(_Sound), ctypes.c_char_p, ctypes.c_double, ctypes.c_int
        for name, res, args in (
                ("be_params_new", P, []), ("be_params_free", None, [P]), ("be_params_preset", I, [P, C]),
                ("be_params_set", I, [P, C, D]), ("be_params_set_text", I, [P, C, C]), ("be_check", I, [P]),
                ("be_render", I, [P, I, S]), ("be_finish", I, [S, C, ctypes.POINTER(C), ctypes.POINTER(D), I]),
                ("be_cut", None, [S, D, D]), ("be_set_peak", None, [S, D]), ("be_write_wav", I, [S, C, I]),
                ("be_sound_free", None, [S]), ("be_status_text", C, [I]), ("be_version", C, []),
                ("be_reference", C, [])):
            fn = getattr(lib, name)
            fn.restype, fn.argtypes = res, args
        self.loops = hasattr(lib, "be_is_loop") and hasattr(lib, "be_finish_loop")    # 0.3.0 and later
        if self.loops:
            lib.be_is_loop.restype, lib.be_is_loop.argtypes = I, [P]
            lib.be_finish_loop.restype = I
            lib.be_finish_loop.argtypes = [S, C, ctypes.POINTER(C), ctypes.POINTER(D), I]
        self.lib = lib
        self.path = path
        self.version = lib.be_version().decode()
        self.reference = lib.be_reference().decode()
        self._can = {}
        self._lock = threading.Lock()

    def _params(self, preset, p):
        """New parameters, or ``(None, why)``."""
        lib = self.lib
        h = lib.be_params_new()
        if not h:
            return None, "out of memory"
        if preset and lib.be_params_preset(h, preset.encode()):
            lib.be_params_free(h)
            return None, 'Ballistic has no preset called "%s"' % preset
        for key, value in (p or {}).items():
            if isinstance(value, str):
                st = lib.be_params_set_text(h, key.encode(), value.encode())
            else:
                st = lib.be_params_set(h, key.encode(), float(value))
            if st:
                lib.be_params_free(h)
                if st == 1:
                    return None, "Ballistic has no parameter %s" % key
                return None, "%s: %s" % (key, lib.be_status_text(st).decode())
        return h, ""

    def supports(self, req):
        """Whether this engine renders that preset with those parameters (a kind it has ported, no recording)."""
        key = json.dumps([req.get("preset"), req.get("p")], sort_keys=True)
        with self._lock:
            if key not in self._can:
                h, _why = self._params(req.get("preset"), req.get("p"))
                self._can[key] = bool(h) and self.lib.be_check(h) == 0
                if h:
                    self.lib.be_params_free(h)
            return self._can[key]

    def call(self, req):
        """A render request as render.cjs takes it; the answer as render.cjs gives it."""
        lib, t0 = self.lib, time.monotonic()
        h, why = self._params(req.get("preset"), req.get("p"))
        if not h:
            return {"ok": False, "error": why}
        s = _Sound()
        try:
            st = lib.be_render(h, max(1, int(req.get("seed") or 1)), ctypes.byref(s))
            if st:
                return {"ok": False, "error": lib.be_status_text(st).decode()}
            a = req.get("action")
            finish = lib.be_finish_loop if self.loops and lib.be_is_loop(h) else lib.be_finish   # a hum stays a loop
            if isinstance(a, str) and a not in ("", "none"):
                st = finish(ctypes.byref(s), a.encode(), None, None, 0)
                if st:
                    return {"ok": False, "error": 'Ballistic has no action preset called "%s"' % a}
            elif isinstance(a, dict) and a:
                keys = (ctypes.c_char_p * len(a))(*[k.encode() for k in a])
                vals = (ctypes.c_double * len(a))(*[float(v) for v in a.values()])
                st = finish(ctypes.byref(s), None, keys, vals, len(a))
                if st:
                    return {"ok": False, "error": "Ballistic has no action parameter %s" % ", ".join(a)}
            lib.be_cut(ctypes.byref(s), _num(req.get("length"), 3, 0.05, 30), 0.04)
            gain = _num(req.get("gain"), 1, 0, 1)
            out = str(req.get("out") or "")
            if not out:
                return {"ok": False, "error": "no file to write"}
            tmp = "%s.%d.%d.tmp" % (out, os.getpid(), threading.get_ident())
            if req.get("channels") == 1:
                _write_mono(s, gain, tmp)
            else:
                lib.be_set_peak(ctypes.byref(s), gain)
                if lib.be_write_wav(ctypes.byref(s), os.fsencode(tmp), 16):
                    return {"ok": False, "error": "cannot write %s" % tmp}
            os.replace(tmp, out)
            return {"ok": True, "seconds": round(s.n / 48000.0, 3), "ms": round((time.monotonic() - t0) * 1000, 2)}
        finally:
            lib.be_sound_free(ctypes.byref(s))
            lib.be_params_free(h)


def _write_mono(s, gain, path):
    import math
    import wave
    n = s.n
    L = ctypes.cast(s.L, ctypes.POINTER(ctypes.c_float * n)).contents
    R = ctypes.cast(s.R, ctypes.POINTER(ctypes.c_float * n)).contents
    m = [0.5 * (L[i] + R[i]) for i in range(n)]
    pk = max(map(abs, m)) if m else 0
    g = gain / (pk or 1)
    pcm = array("h", (int(math.floor(max(-1.0, min(1.0, v * g)) * 32767 + 0.5)) for v in m))
    if sys.byteorder == "big":
        pcm.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(pcm.tobytes())


# --------------------------------------------------------------------------- #
# the Node process
# --------------------------------------------------------------------------- #
class Renderer:
    """One Node process running render.cjs: a request per line in, an answer per line out."""

    def __init__(self, node):
        self.node = node
        self.proc = None
        self.crashes = 0
        self.answers = None
        self.ids = itertools.count(1)
        self.lock = threading.Lock()
        self.errors = collections.deque(maxlen=6)       # Node's last lines on stderr

    def _start(self):
        if self.crashes >= MAX_CRASHES:
            raise RenderError("Node stopped %d times; not starting it again" % self.crashes)
        flags = 0x08000000 if os.name == "nt" else 0    # CREATE_NO_WINDOW: no console flashing up on Windows
        try:
            proc = subprocess.Popen([self.node, RUNNER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, universal_newlines=True, encoding="utf-8",
                                    bufsize=1, creationflags=flags)
        except OSError as e:
            self.crashes = MAX_CRASHES
            raise RenderError("cannot start %s (%s)" % (self.node, e))
        answers = queue.Queue()

        def read():
            with proc.stdout:
                for line in proc.stdout:
                    try:
                        answers.put(json.loads(line))
                    except ValueError:
                        pass
            answers.put(None)

        def drain():
            with proc.stderr:
                for line in proc.stderr:
                    if line.strip():
                        self.errors.append(line.strip())

        threading.Thread(target=read, name="clio-ballistic-out", daemon=True).start()
        threading.Thread(target=drain, name="clio-ballistic-err", daemon=True).start()
        self.proc, self.answers = proc, answers

    def call(self, req, timeout=RENDER_TIMEOUT):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            rid = next(self.ids)
            try:
                self.proc.stdin.write(json.dumps(dict(req, id=rid)) + "\n")
                self.proc.stdin.flush()
            except (OSError, ValueError) as e:
                self._stop(crashed=True)
                raise RenderError("Node stopped (%s)" % e)
            end = time.monotonic() + timeout
            while True:
                left = end - time.monotonic()
                if left <= 0:
                    self._stop(crashed=True)
                    raise RenderError("Node took longer than %d s" % timeout)
                try:
                    a = self.answers.get(timeout=left)
                except queue.Empty:
                    continue
                if a is None:
                    self._stop(crashed=True)
                    raise RenderError("Node stopped" + (": " + self.errors[-1] if self.errors else ""))
                if a.get("id") == rid:
                    return a

    def _stop(self, crashed=False):
        proc, self.proc = self.proc, None
        if proc is None:
            return
        self.crashes += crashed
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            proc.wait(timeout=1)
        except Exception:
            proc.kill()

    def close(self):
        with self.lock:
            self._stop()


# --------------------------------------------------------------------------- #
# the takes
# --------------------------------------------------------------------------- #
class Sounds:
    """The takes of a game's Ballistic sounds: which are ready, which to play next, which to render.

    ``cache_dir`` and ``game_dir`` are functions, read when needed.  With ``sync`` (the tests' recording
    backend) a take is rendered when it is asked for and nothing runs in the background."""

    def __init__(self, cache_dir, game_dir=lambda: None, sync=False, env=None):
        self.cache_dir = cache_dir
        self.game_dir = game_dir
        self.sync = sync
        self.env = env
        self._node = False                      # not looked for yet
        self._clib = False
        self.c_problem = ""
        self.renderer = None
        self.ready = set()                      # paths of takes on disk
        self.failed = {}                        # sound name -> what went wrong
        self.broken = ""                        # why Node cannot be used, once it cannot
        self.cond = threading.Condition()
        self.jobs = []
        self.queued = {}                        # path -> the priority it is queued at
        self.order = itertools.count()
        self.worker = None
        self.working = False
        self.closed = False
        self.last = {}                          # sound name -> the take played last
        self.turn = collections.Counter()
        self.rng = random.Random(0 if sync else None)
        self.rendered, self.rendered_c, self.ms = 0, 0, 0.0
        self.version = ""
        self._baked = {}

    # ---- Node ---------------------------------------------------------- #
    @property
    def node(self):
        if self._node is False:
            self._node = find_node(self.env)
        return self._node

    @property
    def clib(self):
        """The C engine, when it is installed and follows the same Ballistic as engine.js; else None."""
        if self._clib is False:
            self._clib = None
            path = find_clib(self.env)
            if path:
                try:
                    c = CEngine(path)
                    if ENGINE_COMMIT in c.reference:
                        self._clib = c
                    else:
                        self.c_problem = "%s follows %s, not engine.js %s" % (path, c.reference, ENGINE_COMMIT)
                except (OSError, AttributeError) as e:
                    self.c_problem = "%s: %s" % (path, e)
        return self._clib

    def node_ok(self):
        return bool(self.node) and not self.broken

    def available(self):
        """Whether anything here renders Ballistic's sounds."""
        return bool(self.clib) or self.node_ok()

    def can_render(self, spec):
        c = self.clib
        if c and c.supports({"preset": spec["preset"], "p": spec["p"]}):
            return True
        return self.node_ok()

    def _render(self, name, req, path):
        c = self.clib
        if c and c.supports(req):
            a = c.call(dict(req, out=path))
            with self.cond:
                if a.get("ok"):
                    self.ready.add(path)
                    self.rendered += 1
                    self.rendered_c += 1
                    self.ms += float(a.get("ms") or 0)
                else:
                    self.failed[name] = a.get("error") or "the engine gave no reason"
                self.cond.notify_all()
            return bool(a.get("ok"))
        if not self.node_ok():
            with self.cond:
                self.failed.setdefault(name, "needs Node.js: this kind is not in the C engine yet")
                self.cond.notify_all()
            return False
        if self.renderer is None:
            self.renderer = Renderer(self.node)
        try:
            a = self.renderer.call(dict(req, out=path))
        except RenderError as e:
            with self.cond:
                if self.renderer.crashes >= MAX_CRASHES:
                    self.broken = str(e)
                self.failed.setdefault(name, str(e))
                self.cond.notify_all()
            return False
        with self.cond:
            if a.get("ok"):
                self.ready.add(path)
                self.rendered += 1
                self.ms += float(a.get("ms") or 0)
            else:
                self.failed[name] = a.get("error") or "the engine gave no reason"
            self.cond.notify_all()
        return bool(a.get("ok"))

    # ---- names -------------------------------------------------------- #
    def _req(self, spec, k, gain):
        return {"cmd": "render", "preset": spec["preset"], "p": spec["p"], "action": spec["action"],
                "seed": spec["seed"] + k, "gain": round(gain, 3), "length": spec["length"], "channels": spec["channels"]}

    def _path(self, req):
        blob = json.dumps([engine_id(), req], sort_keys=True)
        return os.path.join(self.cache_dir(), "ballistic-%s.wav" % hashlib.sha1(blob.encode("utf-8")).hexdigest()[:20])

    def _takes(self, spec, volume):
        reqs = [self._req(spec, k, spec["vol"] * volume) for k in range(spec["variations"])]
        return reqs, [self._path(r) for r in reqs]

    def _on_disk(self, path):
        if path in self.ready:
            return True
        if os.path.isfile(path) and os.path.getsize(path) > 44:
            self.ready.add(path)
            return True
        return False

    # ---- baked takes, shipped with a game ------------------------------ #
    def baked_dir(self, set_name):
        g = self.game_dir()
        return os.path.join(g, "sounds", set_name or "default") if g else None

    def _baked_list(self, set_name):
        folder = self.baked_dir(set_name)
        if not folder:
            return {}
        if folder not in self._baked:
            listed = {}
            try:
                with open(os.path.join(folder, BAKED), encoding="utf-8") as f:
                    blob = json.load(f)
                if blob.get("format") == BAKED_FORMAT:
                    listed = blob.get("sounds") or {}
            except (OSError, ValueError, AttributeError):
                pass
            self._baked[folder] = listed
        return self._baked[folder]

    def baked(self, set_name, name, spec):
        """``(files, fresh)``: the baked takes of a sound, and whether they were baked from this very spec."""
        entry = self._baked_list(set_name).get(name)
        if not isinstance(entry, dict):
            return [], False
        folder = self.baked_dir(set_name)
        files = [os.path.join(folder, f) for f in entry.get("files") or [] if isinstance(f, str)
                 and os.path.isfile(os.path.join(folder, f))]
        return files, entry.get("spec") == spec_hash(spec)

    # ---- playing -------------------------------------------------------- #
    def _pick(self, name, paths):
        if len(paths) == 1:
            return paths[0]
        others = [p for p in paths if p != self.last.get(name)] or paths
        return others[self.rng.randrange(len(others))]

    def path_for(self, name, raw, volume, set_name=None, wait=0.3):
        """``(path, gain_in_file)`` of a take to play now, or ``(None, False)``.

        A take rendered here carries the effects volume (play it at full volume); a baked take does not."""
        spec = spec_of(raw)
        if spec is None:
            return None, False
        files, fresh = self.baked(set_name, name, spec)
        if files and (fresh or not self.can_render(spec)):
            pick = self._pick(name, files)
            self.last[name] = pick
            return pick, False
        if not self.can_render(spec):
            return None, False
        reqs, paths = self._takes(spec, volume)
        if self.sync:
            k = self.turn[name] % len(paths)
            self.turn[name] += 1
            if not self._on_disk(paths[k]) and not self._render(name, reqs[k], paths[k]):
                return None, False
            return paths[k], True
        with self.cond:
            ready = [p for p in paths if self._on_disk(p)]
            if not ready and name not in self.failed:
                self._queue(-1, name, reqs[0], paths[0])
                end = time.monotonic() + wait
                while not self._on_disk(paths[0]) and name not in self.failed and not self.broken:
                    left = end - time.monotonic()
                    if left <= 0:
                        break
                    self.cond.wait(left)
                ready = [p for p in paths if self._on_disk(p)]
            if len(ready) < len(paths):
                for r, p in zip(reqs, paths):
                    if p not in self.ready:
                        self._queue(0, name, r, p)
        if not ready:
            return None, False
        pick = self._pick(name, ready)
        self.last[name] = pick
        return pick, True

    def _queue(self, priority, name, req, path):
        if path in self.queued and self.queued[path] <= priority:
            return
        self.queued[path] = priority
        heapq.heappush(self.jobs, (priority, next(self.order), name, req, path))
        if self.worker is None or not self.worker.is_alive():
            self.worker = threading.Thread(target=self._work, name="clio-ballistic", daemon=True)
            self.worker.start()
        self.cond.notify_all()

    def prepare(self, sounds, volume, set_name=None):
        """Render every take of these ``(name, spec)`` in the background, in their order, before they are needed.
        Takes already on disk, or baked from the same spec, are left alone."""
        if self.sync or not self.available():
            return 0
        n = 0
        with self.cond:
            self.jobs = [j for j in self.jobs if j[0] < 0]
            heapq.heapify(self.jobs)
            self.queued = {j[4]: j[0] for j in self.jobs}
            for i, (name, raw) in enumerate(sounds):
                spec = spec_of(raw)
                if spec is None or self.baked(set_name, name, spec)[1] or not self.can_render(spec):
                    continue
                reqs, paths = self._takes(spec, volume)
                for k, (r, p) in enumerate(zip(reqs, paths)):
                    if not self._on_disk(p):
                        self._queue(1 + (k > 0) * 1000 + i, name, r, p)     # every first take, then the rest
                        n += 1
        return n

    def _work(self):
        while True:
            with self.cond:
                while not self.jobs and not self.closed:
                    if not self.cond.wait(20):
                        if not self.jobs:                                       # idle: let Node go
                            if self.renderer is not None:
                                self.renderer.close()
                            self.worker = None
                            return
                if self.closed:
                    return
                _p, _n, name, req, path = heapq.heappop(self.jobs)
                self.queued.pop(path, None)
                if self._on_disk(path) or name in self.failed or self.broken:
                    continue
                self.working = True
            try:
                self._render(name, req, path)
            finally:
                with self.cond:
                    self.working = False
                    self.cond.notify_all()

    def pending(self):
        """How many takes are waiting to be rendered."""
        with self.cond:
            return len(self.queued)

    def settle(self, timeout=60.0):
        """Wait until the background work is done (for tools and tests)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.cond:
                if not self.jobs and not self.working:
                    return True
                self.cond.wait(0.05)
        return False

    # ---- tools -------------------------------------------------------- #
    def info(self):
        """Node's version, the presets and the parameters, asked of the engine itself."""
        if not self.available():
            raise RenderError(self.broken or "Node.js was not found")
        if self.renderer is None:
            self.renderer = Renderer(self.node)
        a = self.renderer.call({"cmd": "info"})
        self.version = a.get("node") or ""
        return a

    def bake(self, set_name, sounds, report=lambda line: None):
        """Render every take of these ``(name, spec)`` into the game's ``sounds/<set>/``, at the sound's own
        level, and list them in baked.json.  Returns the problems (an empty list when all went well)."""
        folder = self.baked_dir(set_name)
        if not folder:
            return ["no game folder"]
        if not self.available():
            return [self.broken or "neither Node.js nor the C engine (libballistic) was found; one is needed to bake"]
        os.makedirs(folder, exist_ok=True)
        listed, bad = {}, []
        old = self._baked_list(set_name)
        for name, raw in sounds:
            spec = spec_of(raw)
            if spec is None:
                continue
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
            files = []
            t0 = time.monotonic()
            for k in range(spec["variations"]):
                req = self._req(spec, k, spec["vol"])
                fn = "%s.%d.wav" % (safe, k + 1)
                if not self._render(name, req, os.path.join(folder, fn)):
                    bad.append("%s: %s" % (name, self.failed.get(name, "not rendered")))
                    break
                files.append(fn)
            else:
                listed[name] = {"spec": spec_hash(spec), "files": files}
                report("%-16s %d take%s, %.1f s" % (name, len(files), "" if len(files) == 1 else "s",
                                                    time.monotonic() - t0))
        kept = set(f for e in listed.values() for f in e["files"])
        for entry in old.values():                           # takes no longer listed go
            for fn in (entry.get("files") or []) if isinstance(entry, dict) else []:
                if isinstance(fn, str) and fn not in kept and "/" not in fn and "\\" not in fn \
                        and os.path.isfile(os.path.join(folder, fn)):
                    os.remove(os.path.join(folder, fn))
        with open(os.path.join(folder, BAKED), "w", encoding="utf-8") as f:
            json.dump({"format": BAKED_FORMAT, "version": 1, "engine": engine_id(), "sounds": listed}, f, indent=1)
            f.write("\n")
        self._baked.pop(folder, None)
        return bad

    def status(self, uses):
        """A line for the ``sound`` command, when the game uses Ballistic sounds."""
        if not uses:
            return []
        c = self.clib
        if not c and not self.node:
            return ["Ballistic sounds: neither Node.js nor the C engine found - the game's own sounds play instead "
                    "(install Node.js, or set CLIO_BALLISTIC_LIB to libballistic)"]
        if not c and self.broken:
            return ["Ballistic sounds: not working (%s) - the game's own sounds play instead" % self.broken]
        if c:
            whole = all(c.supports({"preset": spec_of(s)["preset"], "p": spec_of(s)["p"]}) for _n, s in uses)
            engines = "C engine %s" % c.version + ("" if whole else (", Node.js for the rest" if self.node_ok()
                                                                     else ", the rest needs Node.js"))
        else:
            engines = "Node.js"
        line = "Ballistic sounds (%s): %d take%s rendered" % (engines, self.rendered, "" if self.rendered == 1 else "s")
        if self.rendered:
            line += ", %.0f ms each" % (self.ms / self.rendered)
        if self.pending():
            line += ", %d to go" % self.pending()
        out = [line]
        if self.failed:
            out.append("Ballistic could not render: " + "; ".join("%s (%s)" % kv for kv in sorted(self.failed.items())))
        return out

    def close(self):
        with self.cond:
            self.closed = True
            self.jobs = []
            self.cond.notify_all()
        if self.renderer is not None:
            self.renderer.close()


def spec_hash(spec):
    return hashlib.sha1(json.dumps([engine_id(), spec], sort_keys=True).encode("utf-8")).hexdigest()[:16]
