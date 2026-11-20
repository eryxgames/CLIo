# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Picture: the inner loops of the pictures in C, when the library is installed - as Ballistic Engine is
for sound.  A game never needs it: without it CLIo draws everything in Python, as before.

What it does now (CLIo Picture 0.1): the land's heights for a chunk at once (``land_raw``), and the dots and
dots-fill styles' braille cells from a frame's pixels (``dots``).  Both give exactly what the Python gives - the
same floats, to the last bit - so a game looks and plays the same with it or without it; only faster.  When the
library is loaded it is checked against the Python on a few known values first, and not used if anything
differs (``status()`` says why).

The library is found as Ballistic's is: ``CLIO_PICTURE_LIB`` if set (``none`` for none), else one put in
engine/picture/lib/ (a build of your own), else the one ``clio.py --get-picture`` put in your data folder, else
``clio_picture`` where the system keeps libraries.  Source: https://github.com/eryxgames/clio-picture
"""
from __future__ import annotations

import itertools
import os
import struct
import sys

try:                                    # not in every Python (the editor's in a browser has none)
    import ctypes
    import ctypes.util
except ImportError:                     # pragma: no cover
    ctypes = None

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = {"win32": "clio_picture.dll", "darwin": "libclio_picture.dylib"}

_lib = None                             # the loaded library, False when there is none (or it is off)
_why = "not looked for yet"
_chars = [chr(0x2800 + i) for i in range(256)]
_colours = {}                           # the same colour, the same tuple (fewer tuples; the painter's cache hits)


def library_name(plat=None):
    return NAMES.get(sys.platform if plat is None else plat, "libclio_picture.so")


def find_lib(env=None):
    """The library's path, or None."""
    env = os.environ if env is None else env
    want = env.get("CLIO_PICTURE_LIB")
    if want:
        return None if want.lower() in ("none", "off", "no", "0") else want
    p = os.path.join(HERE, "lib", library_name())
    if os.path.isfile(p):
        return p
    from . import fetch
    got = fetch.installed(env)
    if got:
        return got
    if ctypes is None:
        return None
    return ctypes.util.find_library("clio_picture")


class _Land(ctypes.Structure if ctypes else object):
    _fields_ = [("seed", ctypes.c_int64), ("scale", ctypes.c_double), ("warp", ctypes.c_double),
                ("rough", ctypes.c_double), ("ridges", ctypes.c_double)] if ctypes else []


class _Dots(ctypes.Structure if ctypes else object):
    _fields_ = [("fill", ctypes.c_int), ("steps", ctypes.c_double * 8), ("reach", ctypes.c_double),
                ("most", ctypes.c_double), ("flat", ctypes.c_double)] if ctypes else []


def _open(path):
    lib = ctypes.CDLL(path)
    D, I64, I, P = ctypes.c_double, ctypes.c_int64, ctypes.c_int, ctypes.c_void_p
    lib.clio_picture_version.restype = ctypes.c_char_p
    lib.clio_picture_version.argtypes = []
    lib.clio_hash.restype, lib.clio_hash.argtypes = D, [I64, I64, I64]
    lib.clio_value.restype, lib.clio_value.argtypes = D, [D, D, I64]
    lib.clio_fbm.restype, lib.clio_fbm.argtypes = D, [D, D, I64, I, D]
    lib.clio_land_raw.restype = I
    lib.clio_land_raw.argtypes = [ctypes.POINTER(_Land), I64, I64, I, I, P]
    lib.clio_dots.restype = I
    lib.clio_dots.argtypes = [P, I, I, ctypes.POINTER(_Dots), P]
    return lib


def _agrees(lib):
    """Whether the library gives what the Python gives, on a few values of each thing it does; or why not."""
    from .. import land as land_mod
    for x, y, s in ((0, 0, 0), (-3, 7, 12345), (1 << 20, -(1 << 20), 4207), (17, 5, 3000000000)):
        if lib.clio_hash(x, y, s) != land_mod._h(x, y, s):
            return "its noise differs from CLIo's"
    for x, y, s in ((12.75, -3.5, 4207), (-0.001, 0.999, 7)):
        if lib.clio_fbm(x, y, s, 5, 0.55) != land_mod.fbm(x, y, s, 5, 0.55):
            return "its noise differs from CLIo's"

    class Shape:
        seed, scale, warp, rough, ridges = 4207, 30.0, 0.6, 0.5, 0.25
    want = [land_mod.Land.raw(Shape, x, y) for y in range(-2, 1) for x in range(5, 9)]
    if _raw_block(lib, Shape, 5, -2, 4, 3) != want:
        return "its land differs from CLIo's"
    return None


def check(path):
    """Open the library at ``path`` and check it against the Python: (library, None) or (None, why not)."""
    try:
        lib = _open(path)
        bad = _agrees(lib)
    except (OSError, AttributeError) as e:
        return None, "%s does not load: %s" % (path, e)
    if bad:
        return None, "%s is not used: %s" % (path, bad)
    return lib, None


def load(env=None):
    """The library (loaded once), or None."""
    global _lib, _why
    if _lib is None:
        _lib = False
        try:
            path = find_lib(env) if ctypes is not None else None
        except Exception as e:                           # a Python with no way to look (in a browser)
            path, _why = None, "cannot look for it here: %s" % e
        else:
            _why = "not installed (python clio.py --get-picture)" if ctypes is not None else "no ctypes here"
        if path:
            lib, bad = check(path)
            if lib is None:
                _why = bad
            else:
                _lib = lib
                _why = "CLIo Picture %s (%s)" % (lib.clio_picture_version().decode("ascii", "replace"), path)
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
    return lib.clio_picture_version().decode("ascii", "replace") if lib else None


# --------------------------------------------------------------------------- #
# the land's heights
# --------------------------------------------------------------------------- #
def _raw_block(lib, land, x0, y0, w, h):
    shape = _Land(int(land.seed), float(land.scale), float(land.warp or 0.0), float(land.rough),
                  float(land.ridges or 0.0))
    out = (ctypes.c_double * (w * h))()
    if lib.clio_land_raw(ctypes.byref(shape), x0, y0, w, h, out) != 0:
        return None
    return out[:]


def land_raw(land, x0, y0, w, h):
    """``land.raw(x, y)`` for x0 <= x < x0 + w, y0 <= y < y0 + h, row by row - or None without the library."""
    lib = load()
    if lib is None or w <= 0 or h <= 0:
        return None
    return _raw_block(lib, land, int(x0), int(y0), int(w), int(h))


# --------------------------------------------------------------------------- #
# braille cells
# --------------------------------------------------------------------------- #
def steps(level):
    """For each Bayer value k (0..7) the least luminance a pixel needs to be lit, ``level(l) > k + 0.5``:
    found among the floats themselves, so the library's ``l >= steps[k]`` agrees with ``level`` exactly."""
    bits = lambda f: struct.unpack("<q", struct.pack("<d", f))[0]   # noqa: E731 - floats >= 0 sort as their bits
    flt = lambda i: struct.unpack("<d", struct.pack("<q", i))[0]    # noqa: E731
    out = []
    for k in range(8):
        lo, hi = bits(0.0), bits(255.0)
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if level(flt(mid)) > k + 0.5:
                hi = mid
            else:
                lo = mid
        out.append(flt(hi))
    return out


_styles = {}


def dots(px, cols, rows, fill, level, reach=215.0, most=1.9, flat=9.0):
    """The braille cells of 2 * cols by 4 * rows pixels (rows of (r, g, b) whole numbers 0..255): rows of
    (character, colour, background) as View.braille makes them, without its labels - or None without the
    library, or for pixels it cannot take (then the Python does them)."""
    lib = load()
    if lib is None or cols <= 0 or rows <= 0 or len(px) < 4 * rows:
        return None
    w = 2 * cols
    try:
        flat_px = bytes(itertools.chain.from_iterable(itertools.chain.from_iterable(
            row if len(row) == w else row[:w] for row in px[:4 * rows])))
    except (TypeError, ValueError):                      # not whole numbers 0..255
        return None
    if len(flat_px) != w * 4 * rows * 3:                 # a short row, or colours that are not (r, g, b)
        return None
    key = (bool(fill), level, reach, most, flat)
    style = _styles.get(key)
    if style is None:
        style = _styles[key] = _Dots(1 if fill else 0, (ctypes.c_double * 8)(*steps(level)), reach, most, flat)
    out = ctypes.create_string_buffer(cols * rows * 8)
    if lib.clio_dots(flat_px, cols, rows, ctypes.byref(style), out) != 0:
        return None
    raw = out.raw
    chars, colours = _chars, _colours
    if len(colours) > 50000:
        colours.clear()
    cells = []
    i = 0
    for _r in range(rows):
        line = []
        for _c in range(cols):
            kind = raw[i + 1]
            if kind == 0:
                line.append((" ", None, None))
            else:
                fg = bg = None
                if kind & 2:
                    k = raw[i + 2:i + 5]
                    fg = colours.get(k)
                    if fg is None:
                        fg = colours[k] = (k[0], k[1], k[2])
                if kind & 1:
                    k = raw[i + 5:i + 8]
                    bg = colours.get(k)
                    if bg is None:
                        bg = colours[k] = (k[0], k[1], k[2])
                line.append((chars[raw[i]] if kind & 2 else " ", fg, bg))
            i += 8
        cells.append(line)
    return cells
