# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion's C library under Python: the same motion, many times as fast, when the library is there.

Nothing needs it: without it everything runs in Python, as before.  With it a body is stepped in C and its
skeleton, its model's corners and its events come back as plain numbers:

    from clio_motion import native
    if native.load():                               # None when there is no library, or it does not agree with the Python
        b = native.Body("hyena")                    # a character's name; style=dict(STYLE, bounce=1.3)
        b.step(1 / 60, {"speed": 1.4})              # the same inputs as clio_motion.step takes
        b.step(1 / 60)                              # the same again
        b.x, b.z, b.heading, b.speed, b.mode        # where it is and what it is doing
        b.joints()                                  # twelve numbers a joint: place, x, y, z axes
        m = native.bind(mesh.build(rig))            # once for a model; b.points(m) are its corners, three numbers each

The library is looked for in ``CLIO_MOTION_LIB`` if set (``none`` for none), then beside this package (``lib/``
here or one folder up), then in the folders listed in ``DIRS``, then where the system keeps libraries.  It is built
from c/ (``make shared``; ``build.bat`` on Windows).  When it is loaded it is first run against the Python on a
short walk, and not used if the two differ (``status()`` says why): C and Python agree to about nine digits, not to
the last one, so over a long time two bodies given the same inputs can come to step differently.
"""
from __future__ import annotations

import os
import sys
from array import array

try:                                    # not in every Python (one in a browser has none)
    import ctypes
    import ctypes.util
except ImportError:                     # pragma: no cover
    ctypes = None

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {"win32": "clio_motion.dll", "darwin": "libclio_motion.dylib"}
DIRS = []                               # more folders to look in (a program that fetches the library adds its own)
NIN, NEV = 82, 22
EVENTS = ("hit", "jump", "land", "fire", "reload", "loaded", "throw", "grab", "putdown", "punch", "strike", "drop", "bite",
          "pounce", "pinch", "sting", "ink", "grip", "top", "die", "mount", "dismount")
MODES = ("ground", "ladder", "ragdoll", "swim", "fly", "ledge", "ride")
CALLS = {"enter_swim": 1, "leave_swim": 2, "enter_fly": 3, "leave_fly": 4, "enter_ladder": 5, "leave_ladder": 6, "grab_ledge": 7,
         "place": 8, "stand": 9, "dismount": 11}
_KIT = {"rifle": 1, "pistols": 2, "sword": 3, "hands": 4, "case": 5, "trolley": 6}
_PUNCH = {"jab": 1, "cross": 2, "hook": 3}
_SWING = {"slash": 1, "chop": 2, "thrust": 3}

_lib = None                             # the loaded library; False when there is none, or it is off
_why = "not looked for yet"


def library_name(plat=None):
    return NAMES.get(sys.platform if plat is None else plat, "libclio_motion.so")


def find_lib(env=None):
    """The library's path, or None."""
    env = os.environ if env is None else env
    want = env.get("CLIO_MOTION_LIB")
    if want:
        return None if want.lower() in ("none", "off", "no", "0") else want
    name = library_name()
    for folder in [os.path.join(HERE, "lib"), os.path.join(os.path.dirname(HERE), "lib")] + list(DIRS):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            return p
    return ctypes.util.find_library("clio_motion") if ctypes is not None else None


def _declare(lib):
    c, D, I, P = ctypes, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int), ctypes.c_void_p
    for name, res, args in (
            ("cm_version", c.c_char_p, []), ("cm_body_size", c.c_int, []), ("cm_body_init", c.c_int, [P, c.c_char_p, D]),
            ("cm_body_ground_flat", None, [P]), ("cm_body_ground_waves", c.c_int, [P, c.c_int, D, c.c_int, c.c_double, c.c_double]),
            ("cm_body_ground_grid", c.c_int, [P, c.c_double, c.c_double, c.c_double, c.c_int, c.c_int, D]),
            ("cm_body_reset", None, [P]), ("cm_body_place", None, [P, c.c_double, c.c_double, c.c_double]),
            ("cm_body_step", c.c_int, [P, D, c.c_double]), ("cm_body_call", c.c_int, [P, c.c_int, D]),
            ("cm_body_mount", c.c_int, [P, P]), ("cm_body_state", None, [P, D]), ("cm_body_events", None, [P, I]),
            ("cm_body_rig", c.c_char_p, [P]), ("cm_body_joints", c.c_int, [P, D]), ("cm_body_moves", c.c_int, [P, D]),
            ("cm_body_points", c.c_int, [P, c.c_int, I, D, D, D]), ("cm_body_skin", c.c_int, [P, c.c_int, D, I, I, D, D, D])):
        f = getattr(lib, name)
        f.restype, f.argtypes = res, args


def check(path):
    """The library at ``path``, loaded and found to agree with the Python: ``(library, None)``, or ``(None, why not)``."""
    if ctypes is None:
        return None, "no ctypes here"
    try:
        lib = ctypes.CDLL(path)
        _declare(lib)
    except (OSError, AttributeError) as e:
        return None, "cannot be loaded (%s): %s" % (path, e)
    try:
        worst = _agreement(lib)
    except Exception as e:                               # anything at all: it is not used
        return None, "does not run (%s): %s" % (path, e)
    if not worst < 1e-6:
        return None, "differs from the Python by %.3g on a short walk (%s)" % (worst, path)
    return lib, None


def _agreement(lib):
    """How far the library's skeleton is from the Python's after a short walk, a turn and an attack: the largest
    difference in any number of any joint."""
    from . import STYLE, characters, create_state, rig, step
    worst = 0.0
    for name, act in (("hyena", "bite"), ("soldier", "fire"), ("scorpion", "sting")):
        ch = characters()[name]

        def flat(x, z):
            return 0.0
        S = create_state(ch, flat)
        b = Body(name, lib=lib)
        sk, pose = None, None
        for i in range(90):
            inp = {"speed": 1.2 if i < 60 else 0.0, "heading": 0.7 if i > 30 else None, "armed": True}
            if i == 70:
                inp[act] = True if act == "fire" else {}
            pose = step(S, ch, inp, STYLE, flat, 1 / 60)
            del S.events[:]
            b.step(1 / 60, inp)
            if i % 30 == 29:
                sk = rig.skeleton(ch, pose, sk)
                got = b.joints()
                for j, f in enumerate(sk["frames"]):
                    want = f["o"] + f["x"] + f["y"] + f["z"]
                    worst = max(worst, max(abs(got[12 * j + k] - want[k]) for k in range(12)))
        worst = max(worst, abs(b.x - S.px), abs(b.heading - S.h))
    return worst


def load(env=None):
    """The library (loaded once), or None."""
    global _lib, _why
    if _lib is None:
        _lib = False
        try:
            path = find_lib(env) if ctypes is not None else None
        except Exception as e:                           # a Python with no way to look
            path, _why = None, "cannot look for it here: %s" % e
        else:
            _why = "not here (built from c/ with make shared, or build.bat)" if ctypes is not None else "no ctypes here"
        if path:
            lib, bad = check(path)
            if lib is None:
                _why = bad
            else:
                _lib = lib
                _why = "CLIo Motion %s in C (%s)" % (lib.cm_version().decode("ascii", "replace"), path)
    return _lib or None


def use(on=True, env=None):
    """Turn the library off (``use(False)``: everything in Python), or look for it again."""
    global _lib, _why
    _lib = None
    if not on:
        _lib, _why = False, "turned off"
    else:
        load(env)


def status():
    """What is in use, in a line."""
    load()
    return _why


def version():
    lib = load()
    return lib.cm_version().decode("ascii", "replace") if lib else None


# ---------------------------------------------------------------- the inputs as numbers ----------------
def encode(inp, out):
    """A dictionary of inputs (what ``clio_motion.step`` takes) written into ``out`` as the library's 82 numbers.
    The order is the one the recorded runs keep them in (tools/golden.js: inputLine, inputLine3)."""
    g = inp.get

    def v3(at, a):
        out[at], out[at + 1], out[at + 2] = (a[0], a[1], a[2] if len(a) > 2 else 0.0) if a else (0.0, 0.0, 0.0)

    def aimed(at, x):
        t = x.get("target") if isinstance(x, dict) else None
        out[at] = 0.0 if x is None or x is False else 2.0 if t else 1.0
        v3(at + 1, t)
    hit = g("hit")
    h = hit.get("impulse") if isinstance(hit, dict) else None
    mv, pc = g("move"), g("pounce")
    out[0], out[1], out[2] = g("speed") or 0.0, g("crouch") or 0.0, g("steer") or 0.0
    out[3], out[4], out[5], out[6] = (0.0 if g("heading") is None else 1.0), g("heading") or 0.0, g("dir") or 0.0, 1.0 if g("jump") else 0.0
    out[7] = 1.0 if h else 0.0
    v3(8, h)
    out[11], out[12], out[13] = (1.0, mv[0], mv[1]) if mv else (0.0, 0.0, 0.0)
    t = pc.get("target") if isinstance(pc, dict) else None
    out[14], out[15] = (0.0 if pc is None or pc is False else 1.0), (1.0 if t else 0.0)
    v3(16, t)
    a = g("aim")
    out[19] = float(len(a)) if a else 0.0
    v3(20, a)
    out[23], out[24], out[25], out[26] = (1.0 if g("fire") else 0.0), (1.0 if g("armed") else 0.0), float(_KIT.get(g("kit"), 0)), \
        (1.0 if g("reload") else 0.0)
    th = g("throw")
    t = th.get("target") if isinstance(th, dict) else None
    out[27] = 0.0 if th is None or th is False else 2.0 if t else 1.0
    v3(28, t)
    pk = g("pickup")
    pk = pk if isinstance(pk, dict) else ({} if pk else None)
    at_, sz = (pk.get("at"), pk.get("size")) if pk is not None else (None, None)
    out[31], out[32] = (1.0 if pk is not None else 0.0), (1.0 if at_ else 0.0)
    v3(33, at_)
    hd = pk.get("heading") if pk is not None else None
    out[36], out[37], out[38] = (0.0 if hd is None else 1.0), hd or 0.0, (1.0 if sz else 0.0)
    out[39], out[40], out[41] = (sz["d"], sz["h"], sz["w"]) if sz else (0.0, 0.0, 0.0)
    out[42], out[43], out[44] = (1.0 if g("putdown") else 0.0), (1.0 if g("guard") else 0.0), (1.0 if g("block") else 0.0)
    pu = g("punch")
    t = pu.get("target") if isinstance(pu, dict) else None
    out[45], out[46] = (float(_PUNCH.get(pu.get("kind"), 1)) if isinstance(pu, dict) else 0.0), (1.0 if t else 0.0)
    v3(47, t)
    tr = g("track")
    out[50] = 1.0 if tr else 0.0
    v3(51, tr)
    sw = g("swing")
    out[54] = float(_SWING.get(sw.get("kind"), 1)) if isinstance(sw, dict) else 0.0
    aimed(55, g("bite"))
    aimed(59, g("pinch"))
    aimed(63, g("sting"))
    aimed(67, g("grab"))
    out[71] = 1.0 if g("ink") else 0.0
    out[72], out[73] = (0.0, 0.0) if g("depth") is None else (1.0, g("depth"))
    out[74], out[75] = (0.0, 0.0) if g("height") is None else (1.0, g("height"))
    out[76], out[77] = (1.0 if g("climb") else 0.0), (1.0 if g("drop") else 0.0)
    die = g("die")
    imp = die.get("impulse") if isinstance(die, dict) else None
    out[78] = 0.0 if die is None or die is False else 2.0 if imp else 1.0
    v3(79, imp)
    return out


# ---------------------------------------------------------------- a model bound, a body ----------------
class Bound:
    """A model's corners made ready for the library (see ``bind``): which joint carries each, and where."""

    def __init__(self, joint, local, order=None):
        k = range(len(joint)) if order is None else order
        self.n = len(k)
        self.joint = (ctypes.c_int * self.n)(*[joint[i] for i in k])
        self.local = (ctypes.c_double * (3 * self.n))(*[c for i in k for c in local[i]])


def bind(model, order=None):
    """What ``mesh.build`` or ``mesh.lines`` gave, made ready for ``Body.points``. ``order``: the corners wanted, in
    the order wanted (all of them, as they come, if not said)."""
    return Bound(model["joint"], model["local"], order)


class Skin:
    """A skin made ready for ``Body.skin``: ``rest`` are the corners in the template pose (glTF's axes, metres) and
    ``carried`` for each its ``[(joint, weight), ...]``."""

    def __init__(self, rest, carried):
        self.n = len(rest)
        self.rest = (ctypes.c_double * (3 * self.n))(*[c for p in rest for c in p])
        self.count = (ctypes.c_int * self.n)(*[len(c) for c in carried])
        pairs = [jw for c in carried for jw in c]
        self.joint = (ctypes.c_int * max(1, len(pairs)))(*[j for j, _w in pairs])
        self.weight = (ctypes.c_double * max(1, len(pairs)))(*[w for _j, w in pairs])


class Body:
    """One body in the library. ``character``: its name; ``style``: a dictionary as ``clio_motion.STYLE``."""

    def __init__(self, character, style=None, lib=None):
        lib = lib or load()
        if lib is None:
            raise RuntimeError("CLIo Motion's library is not in use: %s" % _why)
        self.lib, self.character = lib, character
        self.mem = ctypes.create_string_buffer(lib.cm_body_size())
        self.ptr = ctypes.cast(self.mem, ctypes.c_void_p)
        st = None
        if style:
            st = (ctypes.c_double * 7)(*[float(style[k]) for k in ("bounce", "stride", "arm", "lean", "step", "snap", "still")])
        if lib.cm_body_init(self.ptr, character.encode("ascii"), st) != 0:
            from . import characters
            if character in characters():           # known here, so the library is an older one
                raise ValueError("the library (CLIo Motion %s) has no character called '%s': it is older than this package (%s)"
                                 % (lib.cm_version().decode("ascii", "replace"), character, __import__(__package__).__version__))
            raise ValueError("there is no character called '%s'" % character)
        self._in = (ctypes.c_double * NIN)()
        self._in[24] = 1.0                               # armed
        self._state = (ctypes.c_double * 8)()
        self._ev = (ctypes.c_int * NEV)()
        self._frame = (ctypes.c_double * 12)()
        self._nums = (ctypes.c_double * (16 * 56))()
        self._kept = []                                  # what the library points at, kept alive: a grid, a mount
        self._out = {}
        self._fresh = False

    # the ground (then reset: the body starts again on it)
    def ground_flat(self):
        self.lib.cm_body_ground_flat(self.ptr)

    def ground_waves(self, waves, wall=None):
        """``waves``: ``[height, kx, kz, phase]`` each; ``wall``: ``(x, h)``, a step up beyond x."""
        flat = (ctypes.c_double * max(1, 4 * len(waves)))(*[c for w in waves for c in w])
        if self.lib.cm_body_ground_waves(self.ptr, len(waves), flat, 1 if wall else 0, wall[0] if wall else 0.0, wall[1] if wall else 0.0):
            raise ValueError("at most eight waves")

    def ground_grid(self, x0, z0, cell, nx, nz, heights):
        """Heights at the points of a grid, ``nx`` by ``nz``, ``cell`` apart, from (x0, z0), row after row along x."""
        grid = (ctypes.c_double * (nx * nz))(*heights)
        self._kept.append(grid)
        if self.lib.cm_body_ground_grid(self.ptr, x0, z0, cell, nx, nz, grid):
            raise ValueError("a grid needs a size and a cell above 0")

    def reset(self):
        self.lib.cm_body_reset(self.ptr)
        self._fresh = False

    def place(self, x, z, heading=0.0):
        self.lib.cm_body_place(self.ptr, x, z, heading)
        self._fresh = False

    def step(self, dt, inp=None):
        """One step; ``inp``: the inputs (a dictionary), or None for the same as the last step."""
        if inp is not None:
            encode(inp, self._in)
            ok = self.lib.cm_body_step(self.ptr, self._in, dt)
        else:
            ok = self.lib.cm_body_step(self.ptr, None, dt)
        self._fresh = False
        if ok != 0:
            raise ValueError("the step failed")

    def step_numbers(self, dt, numbers):
        """One step with the inputs as the 82 numbers themselves (a ctypes array of doubles)."""
        self._fresh = False
        return self.lib.cm_body_step(self.ptr, numbers, dt)

    def call(self, name, *args):
        """``enter_swim``, ``leave_swim``, ``enter_fly``, ``leave_fly``, ``enter_ladder`` (x, y0, spacing[, amp, freq,
        phase]), ``leave_ladder``, ``grab_ledge`` (x, y, z), ``place`` (x, z, heading), ``stand``, ``dismount``."""
        a = (ctypes.c_double * 6)(*(list(args) + [0.0] * 6)[:6])
        self._fresh = False
        return self.lib.cm_body_call(self.ptr, CALLS[name] if isinstance(name, str) else int(name), a)

    def mount(self, other):
        """On to ``other`` (a Body with a saddle): from then on step it first, then this one. False if it cannot be."""
        ok = bool(self.lib.cm_body_mount(self.ptr, other.ptr))
        if ok:
            self._kept.append(other)
        return ok

    def _see(self):
        if not self._fresh:
            self.lib.cm_body_state(self.ptr, self._state)
            self._fresh = True
        return self._state

    x = property(lambda self: self._see()[0])
    z = property(lambda self: self._see()[1])
    heading = property(lambda self: self._see()[2])
    speed = property(lambda self: self._see()[3])
    height = property(lambda self: self._see()[4])
    mode = property(lambda self: MODES[int(self._see()[5])])
    still = property(lambda self: bool(self._see()[6]))

    def events(self):
        """The events since the last call, by name: ``["land", "land", "bite"]``."""
        self.lib.cm_body_events(self.ptr, self._ev)
        return [EVENTS[k] for k in range(NEV) for _ in range(self._ev[k])]

    def rig(self):
        return self.lib.cm_body_rig(self.ptr).decode("ascii")

    def joints(self):
        """Twelve numbers a joint (place, x, y, z axes), in the rig's order: a list."""
        n = self.lib.cm_body_joints(self.ptr, self._nums)
        if n < 0:
            raise ValueError("the pose fits no rig")
        return self._nums[:12 * n]

    def moves(self):
        """Sixteen numbers a joint: its move from the template pose (glTF's axes, column after column)."""
        n = self.lib.cm_body_moves(self.ptr, self._nums)
        if n < 0:
            raise ValueError("the pose fits no rig")
        return self._nums[:16 * n]

    def _into(self, what, n):
        out = self._out.get(id(what))
        if out is None or out[0] is not what:
            flat = array("d", bytes(24 * n))
            out = self._out[id(what)] = (what, flat, (ctypes.c_double * (3 * n)).from_buffer(flat))
        return out[1], out[2]

    def _framed(self, frame):
        if frame is None:
            return None
        self._frame[:] = frame
        return self._frame

    def points(self, bound, frame=None):
        """A bound model's corners as they are now: an ``array('d')`` of three numbers each, in the pose's axes - or
        ``frame``'s (twelve numbers: three rows of a matrix, then an offset) times each. The same array is written
        again by the next call for this model: take what is wanted from it before."""
        flat, buf = self._into(bound, bound.n)
        if self.lib.cm_body_points(self.ptr, bound.n, bound.joint, bound.local, self._framed(frame), buf) < 0:
            raise ValueError("the model is not this body's rig's")
        return flat

    def skin(self, skin, frame=None):
        """A skin's corners as they are now (as ``points``), from glTF's axes."""
        flat, buf = self._into(skin, skin.n)
        if self.lib.cm_body_skin(self.ptr, skin.n, skin.rest, skin.count, skin.joint, skin.weight, self._framed(frame), buf) < 0:
            raise ValueError("the pose fits no rig")
        return flat


def speed_of(character="hyena", steps=20000):
    """Whole steps a second for a walking body, in the library and in Python: ``(library, python)``."""
    import time
    from . import STYLE, characters, create_state, step
    ch = characters()[character]
    b = Body(character)
    b.step(1 / 60, {"speed": 1.2, "armed": True})
    t = time.perf_counter()
    for _ in range(steps):
        b.step(1 / 60)
    fast = steps / (time.perf_counter() - t)

    def flat(x, z):
        return 0.0
    S, inp, n = create_state(ch, flat), {"speed": 1.2, "armed": True}, max(200, steps // 40)
    t = time.perf_counter()
    for _ in range(n):
        step(S, ch, inp, STYLE, flat, 1 / 60)
        del S.events[:]
    return fast, n / (time.perf_counter() - t)


if __name__ == "__main__":
    print(status())
    if load():
        print("a walking hyena: %.0f steps a second in the library, %.0f in Python" % speed_of())

