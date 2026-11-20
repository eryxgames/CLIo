# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Picture: the inner loops of the pictures in C, when the library is installed - as Ballistic Engine is
for sound.  A game never needs it: without it CLIo draws everything in Python, as before.

What it does now (CLIo Picture 0.3): the land's heights for a chunk at once (``land_raw``), the open land's
ground caster (``land_draw``), the sky over open cells but for the sun (``sky``), the rooms' floor and
ceiling but for teleporters' rings (``room``), and the dots and dots-fill styles' braille cells from a
frame's pixels (``dots``).  All give exactly what the Python gives - the same floats, to the last bit - so a game looks and
plays the same with it or without it; only faster.  When the
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
from array import array

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


class _Ground(ctypes.Structure if ctypes else object):
    _fields_ = [("pw", ctypes.c_int), ("ph", ctypes.c_int), ("yh", ctypes.c_int), ("step", ctypes.c_int),
                ("half", ctypes.c_double), ("lw", ctypes.c_double), ("tall", ctypes.c_double),
                ("z0", ctypes.c_double), ("cx", ctypes.c_double), ("cy", ctypes.c_double),
                ("fx", ctypes.c_double), ("fy", ctypes.c_double), ("rx", ctypes.c_double),
                ("ry", ctypes.c_double), ("eye", ctypes.c_double), ("base", ctypes.c_double),
                ("phase", ctypes.c_int64), ("haze", ctypes.c_uint32), ("steps", ctypes.c_int),
                ("d", ctypes.c_void_p), ("fog", ctypes.c_void_p), ("stamps", ctypes.c_int),
                ("stamp_xy", ctypes.c_void_p), ("stamp_tex", ctypes.c_void_p), ("tex_w", ctypes.c_void_p),
                ("tex_h", ctypes.c_void_p), ("tex_at", ctypes.c_void_p), ("texels", ctypes.c_void_p)] \
        if ctypes else []


class _Sky(ctypes.Structure if ctypes else object):
    _fields_ = [("pw", ctypes.c_int), ("yh", ctypes.c_int), ("f", ctypes.c_double), ("lateral", ctypes.c_double),
                ("phase", ctypes.c_int64), ("base", ctypes.c_void_p), ("stars", ctypes.c_double),
                ("clouds", ctypes.c_int), ("cloud_rgb", ctypes.c_uint32), ("cloud_amount", ctypes.c_double),
                ("ridges", ctypes.c_int), ("ridge_rgb", ctypes.c_void_p), ("ridge_height", ctypes.c_void_p),
                ("ridge_near", ctypes.c_void_p), ("ridge_rough", ctypes.c_void_p), ("ridge_seed", ctypes.c_void_p),
                ("sun", ctypes.c_int), ("sun_at", ctypes.c_double), ("sun_height", ctypes.c_double),
                ("sun_size", ctypes.c_double), ("sun_glow", ctypes.c_double)] if ctypes else []


class _Room(ctypes.Structure if ctypes else object):
    _fields_ = [("pw", ctypes.c_int), ("ph", ctypes.c_int), ("yh", ctypes.c_int), ("step", ctypes.c_int),
                ("half", ctypes.c_double), ("cx", ctypes.c_double), ("cy", ctypes.c_double),
                ("fx", ctypes.c_double), ("fy", ctypes.c_double), ("rx", ctypes.c_double), ("ry", ctypes.c_double),
                ("phase", ctypes.c_int64), ("row_kind", ctypes.c_void_p), ("row_z", ctypes.c_void_p),
                ("row_fog", ctypes.c_void_p), ("row_span", ctypes.c_void_p), ("sky", ctypes.c_void_p)] \
        if ctypes else []


class _RoomCell(ctypes.Structure if ctypes else object):
    _fields_ = [("tex", ctypes.c_void_p), ("tex_w", ctypes.c_int32), ("tex_h", ctypes.c_int32),
                ("kind", ctypes.c_int32), ("belt", ctypes.c_int32), ("toxic", ctypes.c_int32),
                ("fire", ctypes.c_int32), ("mark", ctypes.c_int32), ("x", ctypes.c_int64), ("y", ctypes.c_int64)] \
        if ctypes else []


ROOM_CELL_FN = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int64, ctypes.c_int64,
                                ctypes.POINTER(_RoomCell)) if ctypes else None
CLEAR = 0xFFFFFFFF
class _Frame(ctypes.Structure if ctypes else object):
    _fields_ = [("pw", ctypes.c_int), ("ph", ctypes.c_int), ("sx", ctypes.c_int), ("sy", ctypes.c_int),
                ("rgb", ctypes.c_void_p), ("depth", ctypes.c_void_p), ("cur_z", ctypes.c_double),
                ("cover", ctypes.c_void_p), ("zbuf", ctypes.c_void_p), ("zgen", ctypes.c_void_p),
                ("gen", ctypes.c_uint32)] if ctypes else []


class _Tone(ctypes.Structure if ctypes else object):
    _fields_ = [("kind", ctypes.c_int), ("fog", ctypes.c_double), ("haze", ctypes.c_uint32), ("k", ctypes.c_double),
                ("gone", ctypes.c_double), ("step", ctypes.c_double), ("id", ctypes.c_int64),
                ("flash", ctypes.c_int), ("tinted", ctypes.c_int), ("tint", ctypes.c_uint32)] if ctypes else []


CHUNK_FN = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64, ctypes.c_int64) if ctypes else None
CHUNK_BYTES = 256 * 8 + 256 * 4 + 256 * 2                    # clio_chunk: heights, colours, kinds
U32 = "I" if array("I").itemsize == 4 else "L"


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
    if hasattr(lib, "clio_land_draw"):                  # 0.2 and later; an older library does the rest
        lib.clio_land_draw.restype = I
        lib.clio_land_draw.argtypes = [ctypes.POINTER(_Ground), CHUNK_FN, P, P, I, P, P]
        lib.clio_sky_draw.restype = I
        lib.clio_sky_draw.argtypes = [ctypes.POINTER(_Sky), P, P, P, ctypes.POINTER(I)]
    if hasattr(lib, "clio_frame_blit"):                 # 0.4 and later
        F = ctypes.POINTER(_Frame)
        lib.clio_frame_land_cover.restype = None
        lib.clio_frame_land_cover.argtypes = [F]
        lib.clio_frame_front.restype = None
        lib.clio_frame_front.argtypes = [F, P, I, I, I, I, I, I, D, D, D, D, D, D, D]
        lib.clio_frame_side.restype = None
        lib.clio_frame_side.argtypes = [F, P, I, I, I, P, P, P, D, D, D, D, D, D, D]
        lib.clio_frame_blit.restype = None
        lib.clio_frame_blit.argtypes = [F, P, I, I, I, I, D, I, I, ctypes.POINTER(_Tone), I, D]
        lib.clio_frame_darken.restype = None
        lib.clio_frame_darken.argtypes = [F, I, I, I, I, D]
        lib.clio_frame_model.restype = None
        lib.clio_frame_model.argtypes = [F]
        lib.clio_frame_triangle.restype = None
        lib.clio_frame_triangle.argtypes = [F, P, P, I]
        lib.clio_frame_recolour.restype = None
        lib.clio_frame_recolour.argtypes = [F, I, D, ctypes.c_uint32]
        lib.clio_frame_vignette.restype = None
        lib.clio_frame_vignette.argtypes = [F, D, I]
        lib.clio_frame_shake.restype = None
        lib.clio_frame_shake.argtypes = [F, I]
        U = ctypes.c_uint32
        lib.clio_frame_canopy.restype = None
        lib.clio_frame_canopy.argtypes = [F, U]
        lib.clio_frame_dashboard.restype = None
        lib.clio_frame_dashboard.argtypes = [F, U, I, I, I, I, I, I, I, I, I]
        lib.clio_frame_cage.restype = None
        lib.clio_frame_cage.argtypes = [F]
        lib.clio_dots32.restype = I
        lib.clio_dots32.argtypes = [P, I, I, ctypes.POINTER(_Dots), P]
    if hasattr(lib, "clio_room_draw"):                  # 0.3 and later
        lib.clio_room_draw.restype = I
        lib.clio_room_draw.argtypes = [ctypes.POINTER(_Room), ROOM_CELL_FN, P, P, P, ctypes.POINTER(I)]
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


# --------------------------------------------------------------------------- #
# the open land's ground
# --------------------------------------------------------------------------- #
class _Colours(dict):
    """0xRRGGBB -> (r, g, b), each made once."""
    def __missing__(self, v):
        t = self[v] = (v >> 16, (v >> 8) & 255, v & 255)
        return t


_rgb = _Colours()


def _pack_chunk(ch):
    """A chunk as Land.build keeps it -> clio_chunk's bytes (kept alive by whoever holds them)."""
    heights, cols, kinds = ch[0], ch[1], ch[2]
    b = (array("d", heights).tobytes() + array(U32, [(c[0] << 16) | (c[1] << 8) | c[2] for c in cols]).tobytes()
         + array("h", kinds).tobytes())
    if len(b) != CHUNK_BYTES:
        raise ValueError("a chunk of %d bytes" % len(b))
    return (ctypes.c_char * CHUNK_BYTES).from_buffer_copy(b)


def _stamps(land):
    """The cells a map stands on, for clio_ground: (count, xy, tex, widths, heights, starts, texels), kept."""
    stamp = land.stamp
    if not stamp:
        return 0, None, None, None, None, None, None
    texs = land.__dict__.setdefault("_tex", {})          # id -> (rows, index) for this picture
    order, ws, hs, ats, texels = {}, array("i"), array("i"), array("i"), array(U32)
    xy, tx = array("q"), array("i")
    for (x, y), t in stamp.items():
        xy.append(x)
        xy.append(y)
        if not t:
            tx.append(-1)
            continue
        i = order.get(id(t))
        if i is None:
            got = texs.get(id(t))
            if got is None or got[0] is not t:
                w, h = len(t[0]), len(t)
                px = array(U32)
                for row in t:
                    for k in range(w):
                        c = row[k] or (60, 60, 64)
                        px.append((c[0] << 16) | (c[1] << 8) | c[2])
                got = texs[id(t)] = (t, w, h, px)
            i = order[id(t)] = len(ws)
            ws.append(got[1])
            hs.append(got[2])
            ats.append(len(texels))
            texels.extend(got[3])
        tx.append(i)
    if len(texs) > 64:
        texs.clear()
    return len(tx), xy, tx, ws, hs, ats, texels


def _ptr(a):
    """An array's address (None for none or empty)."""
    if a is None or not len(a):
        return None
    return a.buffer_info()[0]


def land_draw(land, view, cam, eye, phase, sky_rows, frame=None):
    """``Land.cast`` in C: (rows of colours, rows of distances) - or None without the library, or for a
    picture it cannot take (then the Python does it). ``eye``: the eye's height counted from the ground's
    zero (Land.cast's eye plus the land's base). With a ``frame`` (0.4): drawn into it, its cells covered
    marked; True when done."""
    lib = load()
    if lib is None or not hasattr(lib, "clio_land_draw") or not isinstance(phase, int):
        return None
    PW, PH = view.PW, view.PH
    step = 2 if view.detail == "low" else 1
    try:
        sky = view.__dict__.get("_sky_bytes")
        if sky is None or sky[0] is not sky_rows:
            n = min(len(sky_rows), PH)
            data = bytes(itertools.chain.from_iterable(itertools.chain.from_iterable(sky_rows[:n]))) if n else b""
            if len(data) != n * PW * 3:
                return None
            sky = view._sky_bytes = (sky_rows, n, data)
        ds, fog = land.steps()
        steps = land.__dict__.get("_steps_c")
        if steps is None or steps[0] is not ds:
            steps = land._steps_c = (ds, array("d", ds), array("d", fog))
        nst, xy, tx, ws, hs, ats, texels = _stamps(land)
        hr, hg, hb = land.haze
        cx, cy, fx, fy, rx, ry = cam
        g = _Ground(PW, PH, int(view.yh), step, float(view.half), float(view.LW), float(view.TALL),
                    float(land.Z0), float(cx), float(cy), float(fx), float(fy), float(rx), float(ry),
                    float(eye), float(land.base), phase, (hr << 16) | (hg << 8) | hb, len(ds),
                    _ptr(steps[1]), _ptr(steps[2]), nst, _ptr(xy), _ptr(tx), _ptr(ws), _ptr(hs), _ptr(ats),
                    _ptr(texels))
    except (TypeError, ValueError, OverflowError, IndexError, AttributeError):
        return None
    packed = land.__dict__.setdefault("_packed", {})      # (kx, ky) -> (the chunk, its bytes)
    chunks, build = land.chunks, land.build
    if len(packed) > 2 * max(600, len(chunks)):
        for key in [k for k, v in packed.items() if chunks.get(k) is not v[0]]:
            del packed[key]
    held, failed, odd = [], [], []

    def need(_user, kx, ky):
        key = (kx, ky)
        try:
            ch = chunks.get(key)
            if ch is None:
                ch = build(kx, ky)
        except BaseException as e:                     # noqa: BLE001 - raised again below, as the Python would
            failed.append(e)
            return None
        try:
            got = packed.get(key)
            if got is None or got[0] is not ch:
                got = packed[key] = (ch, _pack_chunk(ch))
        except (TypeError, ValueError, OverflowError, IndexError) as e:     # not as clio_chunk has it
            odd.append(e)
            return None
        held.append(got[1])                             # alive until the picture is done, whatever happens
        return ctypes.addressof(got[1])
    fn = CHUNK_FN(need)
    n = PW * PH
    if frame is not None:
        rgb, dep = frame.rgb, frame.depth
    else:
        rgb = (ctypes.c_uint32 * n)()
        dep = (ctypes.c_double * n)()
    r = lib.clio_land_draw(ctypes.byref(g), fn, None, sky[2], sky[1], rgb, dep)
    if failed:
        raise failed[0]
    if r != 0:
        return None
    if frame is not None:
        lib.clio_frame_land_cover(frame.ref)
        return True
    if len(_rgb) > 200000:
        _rgb.clear()
    get = _rgb.__getitem__
    rows = [list(map(get, rgb[y * PW:(y + 1) * PW])) for y in range(PH)]
    depth = [dep[y * PW:(y + 1) * PW] for y in range(PH)]
    return rows, depth


# --------------------------------------------------------------------------- #
# the sky over open cells
# --------------------------------------------------------------------------- #
def _u32(c):
    return (c[0] << 16) | (c[1] << 8) | c[2]


def sky(spec, PW, yh, f, lateral, phase, base, ridge_rgb):
    """``sky_picture`` in C, all but the sun: (rows of colours, each ridge's heights by column, the pixels
    y * PW + x the sun may reach - left before the sun and the ridges) - or None without the library.
    ``base``: each row's colour (the gradient); ``ridge_rgb``: each ridge's colour."""
    lib = load()
    if lib is None or not hasattr(lib, "clio_sky_draw") or not isinstance(phase, int) or PW <= 0 or yh <= 0:
        return None
    ridges, sun, clouds = spec["ridges"], spec["sun"], spec["clouds"]
    try:
        bases = array(U32, [_u32(c) for c in base])
        rrgb = array(U32, [_u32(c) for c in ridge_rgb])
        rh = array("d", [r[1] for r in ridges])
        rseed = array("q", [r[2] for r in ridges])
        rnear = array("d", [r[3] for r in ridges])
        rrough = array("d", [r[4] for r in ridges])
        s = _Sky(PW, yh, float(f), float(lateral), phase, _ptr(bases), float(spec["stars"] or 0.0),
                 1 if clouds else 0, _u32(clouds[0]) if clouds else 0, float(clouds[1]) if clouds else 0.0,
                 len(ridges), _ptr(rrgb), _ptr(rh), _ptr(rnear), _ptr(rrough), _ptr(rseed),
                 1 if sun is not None else 0, *(float(v) for v in ((sun[0], sun[1], sun[2], sun[4]) if sun is not None
                                                                   else (0, 0, 0, 0))))
    except (TypeError, ValueError, OverflowError, IndexError):
        return None
    n = PW * yh
    rgb = (ctypes.c_uint32 * n)()
    hs = (ctypes.c_double * max(1, len(ridges) * PW))()
    spots = (ctypes.c_int32 * (n if sun is not None else 1))()
    count = ctypes.c_int(0)
    if lib.clio_sky_draw(ctypes.byref(s), rgb, hs, spots, ctypes.byref(count)) != 0:
        return None
    if len(_rgb) > 200000:
        _rgb.clear()
    get = _rgb.__getitem__
    rows = [list(map(get, rgb[y * PW:(y + 1) * PW])) for y in range(yh)]
    return rows, [hs[i * PW:(i + 1) * PW] for i in range(len(ridges))], spots[:count.value]


# --------------------------------------------------------------------------- #
# the rooms' floor and ceiling
# --------------------------------------------------------------------------- #
class Odd(Exception):
    """What a cell or a tile holds is not what the library takes: the Python draws the picture."""


_textures = {}                                        # id(rows) -> (rows, w, h, texels)


def _texture(rows):
    got = _textures.get(id(rows))
    if got is None or got[0] is not rows:
        if len(_textures) > 256:
            _textures.clear()
        w, h = len(rows[0]), len(rows)
        if not w or any(len(r) != w for r in rows):
            raise Odd("a tile of uneven rows")
        texels = array(U32, [CLEAR if c is None else (c[0] << 16) | (c[1] << 8) | c[2] for r in rows for c in r])
        got = _textures[id(rows)] = (rows, w, h, texels)
    return got


texture = _texture


def room(PW, PH, yh, step, half, cam, phase, rows, sky_rows, info, held, out=None):
    """``View._backdrop`` in C: (rows of colours, the pixels y * PW + x left for the caller - teleporters with
    no tile over them, drawn as haze) - or None without the library, or for a picture it cannot take.
    ``rows``: (kinds, distances, fogs, spans) for each pixel row; ``info(what, ix, iy)``: a cell's floor
    (what 0) or ceiling (1) as (tile rows or None, kind, belt, toxic, fire, mark, x, y) - raising Odd for what
    the library cannot draw. ``held`` keeps the tiles alive meanwhile."""
    lib = load()
    if lib is None or not hasattr(lib, "clio_room_draw") or not isinstance(phase, int):
        return None
    kinds, zs, fogs, spans = rows
    sky = None
    if sky_rows is not None:
        try:
            sky = bytes(itertools.chain.from_iterable(itertools.chain.from_iterable(sky_rows[:yh])))
        except (TypeError, ValueError):
            return None
        if len(sky) != yh * PW * 3 or len(sky_rows) < yh:
            return None
    cx, cy, fx, fy, rx, ry = cam
    try:
        r = _Room(PW, PH, yh, step, float(half), float(cx), float(cy), float(fx), float(fy), float(rx),
                  float(ry), phase, _ptr(kinds), _ptr(zs), _ptr(fogs), _ptr(spans), None)
    except (TypeError, ValueError, OverflowError):
        return None
    failed, odd = [], []

    def ask(_user, what, ix, iy, out):
        try:
            tex, kind, belt, toxic, fire, mark, x, y = info(what, ix, iy)
            o = out.contents
            if tex is not None:
                got = _texture(tex)
                held.append(got)
                o.tex, o.tex_w, o.tex_h = got[3].buffer_info()[0], got[1], got[2]
            o.kind, o.belt, o.toxic, o.fire, o.mark, o.x, o.y = kind, belt, toxic, fire, mark, x, y
            return 0
        except (Odd, TypeError, ValueError, OverflowError, IndexError) as e:
            odd.append(e)
            return 1
        except BaseException as e:                     # noqa: BLE001 - raised again below, as the Python would
            failed.append(e)
            return 1
    fn = ROOM_CELL_FN(ask)
    n = PW * PH
    rgb = (ctypes.c_uint32 * n)() if out is None else out
    later = (ctypes.c_int32 * n)()
    count = ctypes.c_int(0)
    skybuf = None
    if sky is not None:
        skybuf = ctypes.create_string_buffer(sky, len(sky))
        r.sky = ctypes.addressof(skybuf)
    res = lib.clio_room_draw(ctypes.byref(r), fn, None, rgb, later, ctypes.byref(count))
    if failed:
        raise failed[0]
    if res != 0:
        return None
    if out is not None:
        return None, later[:count.value]
    if len(_rgb) > 200000:
        _rgb.clear()
    get = _rgb.__getitem__
    return [list(map(get, rgb[y * PW:(y + 1) * PW])) for y in range(PH)], later[:count.value]
