# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Picture: the inner loops of the pictures in C, when the library is installed - as Ballistic Engine is
for sound.  A game never needs it: without it CLIo draws everything in Python, as before.

What it does now (CLIo Picture 0.10): the land's heights for a chunk at once (``land_raw``), the open land's
ground caster (``land_draw``), the sky over open cells but for the sun (``sky``), the rooms' floor and
ceiling but for teleporters' rings (``room``), the dots and dots-fill styles' braille cells (``dots``), from
0.4 the whole picture kept in the library (``frame.py``), and from 0.5 the models projected and shaded there
(``model_draw``: with this Python's own pow and exp, checked against model.pbr first, ``models_agree``), and
from 0.10 the vector display's dots, lines, hidden lines and characters (``scope``; engine/vector.py).  All give exactly what the Python gives - the same floats, to the last bit - so a game looks and
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
from itertools import chain

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


class _Material(ctypes.Structure if ctypes else object):
    _fields_ = [("r", ctypes.c_double), ("g", ctypes.c_double), ("b", ctypes.c_double), ("metal", ctypes.c_double),
                ("rough", ctypes.c_double), ("glow", ctypes.c_double)] if ctypes else []


class _Instance(ctypes.Structure if ctypes else object):
    _fields_ = [("verts", ctypes.c_void_p), ("wx", ctypes.c_double), ("wy", ctypes.c_double), ("fx", ctypes.c_double),
                ("fy", ctypes.c_double), ("lift", ctypes.c_double)] if ctypes else []


class _ModelDraw(ctypes.Structure if ctypes else object):
    _fields_ = [("ntri", ctypes.c_int), ("pts", ctypes.c_void_p), ("corner", ctypes.c_void_p),
                ("mat", ctypes.c_void_p), ("own", ctypes.c_void_p), ("colour", ctypes.c_void_p),
                ("nverts", ctypes.c_int), ("mats", ctypes.c_void_p), ("nmats", ctypes.c_int),
                ("cull", ctypes.c_int), ("smooth", ctypes.c_int)] + \
               [(n, ctypes.c_double) for n in ("cx", "cy", "fx", "fy", "rx", "ry", "half", "lw", "yh", "fs", "ch",
                                               "persp", "flat", "zm", "eye")] + \
               [("light", ctypes.c_double * 3), ("air", ctypes.c_int), ("haze", ctypes.c_uint32),
                ("vis", ctypes.c_double), ("flash", ctypes.c_int), ("tinted", ctypes.c_int),
                ("tint", ctypes.c_uint32)] if ctypes else []


class _Rooms(ctypes.Structure if ctypes else object):
    D_, P_ = (ctypes.c_double, ctypes.c_void_p) if ctypes else (None, None)
    _fields_ = [("pw", ctypes.c_int), ("ph", ctypes.c_int), ("half", D_), ("yh", D_), ("lx", D_), ("ly", D_),
                ("cx", D_), ("cy", D_), ("fx", D_), ("fy", D_), ("rx", D_), ("ry", D_), ("z0", D_), ("eye", D_),
                ("far", D_), ("fade", D_), ("near", D_), ("side", D_), ("none", D_), ("phase", ctypes.c_int64),
                ("sky", P_), ("sky_rows", ctypes.c_int), ("nfaces", ctypes.c_int), ("ints", P_), ("geo", P_),
                ("xy", P_), ("ntex", ctypes.c_int), ("texels", P_), ("tw", P_), ("th", P_)] if ctypes else []


class _Tone(ctypes.Structure if ctypes else object):
    _fields_ = [("kind", ctypes.c_int), ("fog", ctypes.c_double), ("haze", ctypes.c_uint32), ("k", ctypes.c_double),
                ("gone", ctypes.c_double), ("step", ctypes.c_double), ("id", ctypes.c_int64),
                ("flash", ctypes.c_int), ("tinted", ctypes.c_int), ("tint", ctypes.c_uint32)] if ctypes else []


class _More(ctypes.Structure if ctypes else object):
    P_ = ctypes.c_void_p if ctypes else None
    _fields_ = [("kinds", P_), ("mats", P_), ("own", P_), ("marking", ctypes.c_int), ("thing", ctypes.c_int),
                ("glow", ctypes.c_int), ("nfaces", ctypes.c_int), ("face_mat", P_), ("nmat", ctypes.c_int),
                ("glow_at", P_), ("glow_rgb", P_), ("low", ctypes.c_int)] if ctypes else []


class _Lamp(ctypes.Structure if ctypes else object):
    D_ = ctypes.c_double if ctypes else None
    _fields_ = [("x", D_), ("y", D_), ("h", D_), ("r", D_), ("g", D_), ("b", D_), ("reach", D_), ("k", D_),
                ("lit_x0", ctypes.c_int64), ("lit_y0", ctypes.c_int64), ("lit_w", ctypes.c_int),
                ("lit_h", ctypes.c_int), ("lit", ctypes.c_void_p)] if ctypes else []


class _Surface(ctypes.Structure if ctypes else object):
    D_, P_, I_ = (ctypes.c_double, ctypes.c_void_p, ctypes.c_int) if ctypes else (None, None, None)
    _fields_ = [("pw", I_), ("ph", I_), ("half", D_), ("yh", D_), ("lx", D_), ("ly", D_), ("cx", D_), ("cy", D_),
                ("fx", D_), ("fy", D_), ("rx", D_), ("ry", D_), ("z0", D_), ("eye", D_), ("far", D_), ("fade", D_),
                ("none", D_), ("t", D_), ("amb", D_ * 3), ("nlamps", I_), ("lamps", P_), ("key", D_ * 3),
                ("nmat", I_), ("metal", P_), ("rough", P_), ("reflect", P_), ("fog", D_), ("cover", D_),
                ("lift", D_), ("amount", D_), ("wet_sky", D_), ("wet_all", D_), ("fog_rgb", D_ * 3),
                ("has_sky_k", I_), ("sky_k", D_ * 3), ("raining", I_), ("mirrors", I_), ("px", D_), ("py", D_),
                ("cells_x0", ctypes.c_int64), ("cells_y0", ctypes.c_int64), ("cells_w", I_), ("cells_h", I_),
                ("cells", P_), ("heights", P_)] if ctypes else []


class _Scope(ctypes.Structure if ctypes else object):      # clio_scope: a vector display's state (engine/vector.py)
    D_, P_, I_ = (ctypes.c_double, ctypes.c_void_p, ctypes.c_int) if ctypes else (None, None, None)
    _fields_ = [("cols", I_), ("rows", I_), ("light", P_), ("depth", P_), ("best", P_), ("ink", P_), ("way", P_),
                ("has_cue", I_), ("cue_near", D_), ("cue_far", D_), ("dim", D_)] if ctypes else []


class _Eye(ctypes.Structure if ctypes else object):        # clio_eye: where a camera is and how it is turned
    D_ = ctypes.c_double if ctypes else None
    _fields_ = [("eye", D_ * 3), ("right", D_ * 3), ("up", D_ * 3), ("ahead", D_ * 3), ("near_z", D_), ("f", D_)] \
        if ctypes else []


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
    if hasattr(lib, "clio_frame_model_draw"):           # 0.5 and later
        lib.clio_maths.restype = None
        lib.clio_maths.argtypes = [P, P]
        lib.clio_frame_model_draw.restype = I
        lib.clio_frame_model_draw.argtypes = [ctypes.POINTER(_Frame), ctypes.POINTER(_ModelDraw), P]
        lib.clio_shade.restype = None
        lib.clio_shade.argtypes = [ctypes.POINTER(_Material), P, P, P, P, P]
        lib.clio_room_scale.restype = D
        lib.clio_room_scale.argtypes = [D]
        lib.clio_haze.restype = D
        lib.clio_haze.argtypes = [D, D]
    if hasattr(lib, "clio_mesh_new"):                   # 0.6 and later
        lib.clio_mesh_new.restype = P
        lib.clio_mesh_new.argtypes = [I, I, P, P, P, P, P, I]
        lib.clio_mesh_free.restype = None
        lib.clio_mesh_free.argtypes = [P]
        lib.clio_frame_mesh_draw.restype = I
        lib.clio_frame_mesh_draw.argtypes = [ctypes.POINTER(_Frame), P, ctypes.POINTER(_Instance),
                                             ctypes.POINTER(_ModelDraw), P]
    if hasattr(lib, "clio_frame_rooms"):                # 0.7 and later
        lib.clio_frame_rooms.restype = I
        lib.clio_frame_rooms.argtypes = [ctypes.POINTER(_Frame), ctypes.POINTER(_Rooms), P, ctypes.POINTER(I)]
    if hasattr(lib, "clio_frame_surface"):              # 0.8 and later
        lib.clio_frame_more.restype = None
        lib.clio_frame_more.argtypes = [ctypes.POINTER(_Frame), P]
        lib.clio_frame_surface.restype = I
        lib.clio_frame_surface.argtypes = [ctypes.POINTER(_Frame), ctypes.POINTER(_Surface)]
        lib.clio_ggx.restype = D
        lib.clio_ggx.argtypes = [P, P, P, D, D]
        lib.clio_frame_flip.restype = None
        lib.clio_frame_flip.argtypes = [ctypes.POINTER(_Frame)]
        if hasattr(lib, "clio_frame_rooms2"):            # 0.9 and later
            lib.clio_frame_rooms2.restype = I
            lib.clio_frame_rooms2.argtypes = [ctypes.POINTER(_Frame), ctypes.POINTER(_Rooms), P, P, ctypes.POINTER(I)]
        lib.clio_tilt.restype = I
        lib.clio_tilt.argtypes = [P, I, I, D, D, ctypes.c_uint32, P]
        lib.clio_land_terraced.restype = I
        lib.clio_land_terraced.argtypes = [ctypes.POINTER(_Ground), I, P, P, CHUNK_FN, P, P, I, P, P]
    if hasattr(lib, "clio_scope_cells"):                # 0.10 and later: the vector display
        S, E = ctypes.POINTER(_Scope), ctypes.POINTER(_Eye)
        lib.clio_scope_clear.restype, lib.clio_scope_clear.argtypes = None, [S, D]
        lib.clio_scope_dot.restype, lib.clio_scope_dot.argtypes = None, [S, I, I, D, ctypes.c_int32, I]
        lib.clio_scope_line2.restype = None
        lib.clio_scope_line2.argtypes = [S, D, D, D, D, D, ctypes.c_int32, I, D, D]
        lib.clio_scope_wire.restype = I
        lib.clio_scope_wire.argtypes = [S, E, P, I, P, I, P, D, ctypes.c_int32]
        lib.clio_scope_hide.restype = I
        lib.clio_scope_hide.argtypes = [S, E, P, I, P, P, I, D]
        lib.clio_scope_cells.restype = I
        lib.clio_scope_cells.argtypes = [S, P, I, I, I, ctypes.c_uint32, P]
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


def scope():
    """The library, if it has the vector display (0.10 and later); else None. (engine/vector.py checks it
    against its own Python before it draws with it.)"""
    lib = load()
    return lib if lib is not None and hasattr(lib, "clio_scope_cells") and array("i").itemsize == 4 else None


def use(on=True, env=None):
    """Turn the library off (``use(False)``: everything in Python), or look for it again."""
    global _lib, _why, _models_ok
    _lib = None
    _models_ok = None
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
rgb_of = _rgb.__getitem__                                    # 0xRRGGBB -> (r, g, b), the same tuple each time


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


def tilt(px, w, h, ca, sa, dark):
    """firstperson.tilt's turn in C (0.8): rows of h pixel rows of w (r, g, b) turned - flat 0xRRGGBB out, or None
    without the library."""
    lib = load()
    if lib is None or not hasattr(lib, "clio_tilt"):
        return None
    src = array(U32, [(c[0] << 16) | (c[1] << 8) | c[2] for row in px for c in row])
    out = array(U32, bytes(4 * w * h))
    if lib.clio_tilt(_ptr(src), w, h, ca, sa, (dark[0] << 16) | (dark[1] << 8) | dark[2], _ptr(out)) != 0:
        return None
    return out


def land_draw(land, view, cam, eye, phase, sky_rows, frame=None):
    """``Land.cast`` in C: (rows of colours, rows of distances) - or None without the library, or for a
    picture it cannot take (then the Python does it). ``eye``: the eye's height counted from the ground's
    zero (Land.cast's eye plus the land's base). With a ``frame`` (0.4): drawn into it, its cells covered
    marked; True when done."""
    lib = load()
    if lib is None or not hasattr(lib, "clio_land_draw") or not isinstance(phase, int) or \
            (land.terrace and not hasattr(lib, "clio_land_terraced")):
        return None                                       # terraces: the Python draws them (the library: 0.8)
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
    if land.terrace:                                      # 0.8: cells standing higher than the pad
        try:
            txy = array("q", [v for key in land.terrace for v in key])
            th = array("d", [float(v) for v in land.terrace.values()])
        except (TypeError, ValueError, OverflowError):
            return None
        r = lib.clio_land_terraced(ctypes.byref(g), len(th), _ptr(txy), _ptr(th), fn, None, sky[2], sky[1], rgb,
                                   dep)
    else:
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


# --------------------------------------------------------------------------- #
# models (0.5)
# --------------------------------------------------------------------------- #
_models_ok = None
_why_models = "not checked yet"


def _python_maths():
    """The pow and exp this Python uses, as C functions: the process's own (the system's maths library), on
    Windows the Universal C Runtime's."""
    names = ["ucrtbase"] if sys.platform == "win32" else [None]
    if sys.platform != "win32":
        found = ctypes.util.find_library("m")
        if found:
            names.append(found)
    for name in names:
        try:
            crt = ctypes.CDLL(name)
            return ctypes.cast(crt.pow, ctypes.c_void_p), ctypes.cast(crt.exp, ctypes.c_void_p)
        except (OSError, AttributeError):
            continue
    return None


def models_agree():
    """Whether the library may draw models: it has them (0.5), it has this Python's pow and exp, and its shading
    gives model.pbr's numbers, its rooms' scale 0.64 ** z and its haze 1 - e^(-d/vis) exactly, on a few hundred
    values. Worked out once."""
    global _models_ok, _why_models
    lib = load()
    if lib is None or not hasattr(lib, "clio_frame_model_draw"):
        return False
    if _models_ok is None:
        _models_ok = False
        maths = _python_maths()
        if maths is None:
            _why_models = "no pow and exp of this Python's to give it"
            return False
        lib.clio_maths(maths[0], maths[1])
        import math
        import random
        from .. import model as model_mod

        class Mat:
            pass
        rng = random.Random(20261120)

        def unit():
            while True:
                v = (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
                n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
                if n > 1e-3:
                    return v[0] / n, v[1] / n, v[2] / n
        out = (ctypes.c_int * 3)()
        for i in range(400):
            m = Mat()
            m.metal, m.rough = rng.choice([0.0, 1.0, rng.random()]), max(0.04, rng.random())
            m.glow = rng.choice([0.0, 0.0, rng.uniform(0, 4)])
            rgb = (rng.random(), rng.random(), rng.random())
            n, light, view = unit(), unit(), unit()
            if i % 7 == 0:
                view = n                                  # straight on: 1 - ndv is 0 or a hair below
            want = model_mod.pbr(m, rgb, n, light, view)
            lib.clio_shade(ctypes.byref(_Material(rgb[0], rgb[1], rgb[2], m.metal, m.rough, m.glow)),
                           (ctypes.c_double * 3)(*rgb), (ctypes.c_double * 3)(*n), (ctypes.c_double * 3)(*light),
                           (ctypes.c_double * 3)(*view), out)
            if list(out) != list(want):
                _why_models = "its shading differs from CLIo's (another maths library?)"
                return False
            z, d, vis = rng.uniform(-0.5, 12.0), rng.uniform(0, 200), rng.uniform(10, 120)
            if lib.clio_room_scale(z) != 0.64 ** z or lib.clio_haze(d, vis) != 1.0 - math.exp(-d / vis):
                _why_models = "its powers differ from CLIo's (another maths library?)"
                return False
        _models_ok, _why_models = True, "the models too"
    return _models_ok


def models_status():
    models_agree()
    return _why_models


_materials = {}


class _Mesh:
    """A model's faces kept in the library (0.6): handed over once, freed when the model is forgotten (without a
    library - a recording frame - just the numbers)."""

    def __init__(self, lib, mdl, nverts):
        self.lib, self.model, self.nverts, self.ref = lib, mdl, nverts, None
        faces, mat, own, colour = array("i"), array("i"), array("b"), array("d")
        for f in mdl.faces:
            faces.extend(f[:3])
            mat.append(f[3])
            if f[4]:
                own.append(1)
                colour.extend(f[4][:3])
            else:
                own.append(0)
                colour.extend((0.0, 0.0, 0.0))
        mats = mdl.materials
        self.mats = (_Material * len(mats))(*[_Material(m.rgb[0], m.rgb[1], m.rgb[2], m.metal, m.rough, m.glow)
                                              for m in mats])
        self.ntri = len(mat)
        self.faces, self.mat, self.own, self.colour = faces, mat, own, colour
        if lib:
            self.ref = lib.clio_mesh_new(nverts, self.ntri, _ptr(faces), _ptr(mat), _ptr(own), _ptr(colour),
                                         ctypes.addressof(self.mats), len(mats))

    def __del__(self):
        ref, self.ref = self.ref, None
        if ref and self.lib:
            try:
                self.lib.clio_mesh_free(ref)
            except Exception:                           # the interpreter closing: the memory goes with it
                pass


_meshes = {}


def mesh_of(lib, mdl, nverts):
    """The library's copy of ``mdl``'s faces, made the first time it is drawn (None: it cannot be made)."""
    got = _meshes.get(id(mdl))
    if got is not None and got.model is mdl and got.nverts == nverts and got.lib is lib:
        return got
    if len(_meshes) > 128:
        _meshes.clear()
    got = _Mesh(lib, mdl, nverts)
    if not lib:
        return got                                      # a recording frame's: kept nowhere
    if not got.ref:
        return None
    _meshes[id(mdl)] = got
    return got


def mesh_draw(frame, mdl, verts, wx, wy, fxw, fyw, lift, cam, view, flat, zm, light, flash, tint, smooth):
    """CLIo Picture 0.6: a model drawn from its kept mesh - only its posed corners and where it stands are handed
    over - (top, middle x) of what showed, None if none did, or False when this library cannot (then
    ``model_draw`` does, with the triangles)."""
    if not getattr(frame, "meshes", False) or not hasattr(frame, "mesh_draw"):
        return False
    lib = getattr(frame, "lib", None)
    if getattr(frame, "record", False):
        lib = None                                      # the library's tests keep the numbers handed over
    elif not lib or not hasattr(lib, "clio_frame_mesh_draw") or not models_agree():
        return False
    try:
        mesh = mesh_of(lib, mdl, len(verts))
        if mesh is None:
            return False
        flat_v = array("d", chain.from_iterable(verts))
        if len(flat_v) != 3 * mesh.nverts:
            return False
        inst = _Instance(_ptr(flat_v), float(wx), float(wy), float(fxw), float(fyw), float(lift))
        m = _template(view, cam, light)
        m.cull, m.smooth = 1, int(bool(smooth))
        m.flat, m.zm = float(flat), float(zm)
        m.flash = 1 if flash else 0
        if tint:
            m.tinted, m.tint = 1, (tint[0] << 16) | (tint[1] << 8) | tint[2]
        else:
            m.tinted, m.tint = 0, 0
    except (TypeError, ValueError, OverflowError, IndexError):
        return False
    out = frame.mesh_draw(mesh, inst, m, flat_v)
    if out is False or not out[0]:
        return out if out is False else None
    return out[1], (out[2] + out[3]) / 2


_tpl = {}


def _template(view, cam, light):
    """The numbers every model of a picture shares (the camera, the View's, the light), set once a picture."""
    air = view.air
    key = (id(view), tuple(cam), tuple(light), view.half, view.LW, view.yh, view.FS, view.CH, view.persp, view.EYE,
           None if air is None else (air[0], air[1]))
    m = _tpl.get(key)
    if m is not None:
        return m
    if len(_tpl) > 16:
        _tpl.clear()
    cx, cy, fx, fy, rx, ry = cam
    m = _ModelDraw()
    m.cx, m.cy, m.fx, m.fy, m.rx, m.ry = float(cx), float(cy), float(fx), float(fy), float(rx), float(ry)
    m.half, m.lw, m.yh, m.fs, m.ch = float(view.half), float(view.LW), float(view.yh), float(view.FS), float(view.CH)
    m.persp = float(view.persp) if view.persp is not None else 0.0
    m.eye = float(view.EYE)
    m.light[0], m.light[1], m.light[2] = light
    if air is not None:
        m.air, m.haze, m.vis = 1, (air[0][0] << 16) | (air[0][1] << 8) | air[0][2], float(air[1])
    _tpl[key] = m
    return m


def model_draw(frame, mdl, tris, cull, smooth, nverts, cam, view, flat, zm, light, flash, tint):
    """``View.draw_model``'s triangles in C: (top, middle x) of what showed, or None if none did - or False when
    the library cannot draw it (then the Python does)."""
    if not getattr(frame, "record", False) and not models_agree():
        return False
    try:
        got = _materials.get(id(mdl))
        if got is None or got[0] is not mdl:
            if len(_materials) > 64:
                _materials.clear()
            mats = mdl.materials
            arr = (_Material * len(mats))(*[_Material(m.rgb[0], m.rgb[1], m.rgb[2], m.metal, m.rough, m.glow)
                                            for m in mats])
            got = _materials[id(mdl)] = (mdl, arr, len(mats))
        pts, corner, mat, own, colour = array("d"), array("i"), array("i"), array("b"), array("d")
        for (p0, p1, p2), f in tris:
            pts.extend(p0)
            pts.extend(p1)
            pts.extend(p2)
            if smooth:
                corner.extend(f[:3])
            mat.append(f[3])
            if f[4]:
                own.append(1)
                colour.extend(f[4][:3])
            else:
                own.append(0)
                colour.extend((0.0, 0.0, 0.0))
        if len(pts) != 9 * len(mat):
            return False
        cx, cy, fx, fy, rx, ry = cam
        air = view.air
        m = _ModelDraw()
        m.ntri, m.pts, m.corner, m.mat, m.own, m.colour = (len(mat), _ptr(pts), _ptr(corner), _ptr(mat), _ptr(own),
                                                          _ptr(colour))
        m.nverts, m.mats, m.nmats, m.cull, m.smooth = nverts, ctypes.addressof(got[1]), got[2], int(cull), int(smooth)
        m.cx, m.cy, m.fx, m.fy, m.rx, m.ry = float(cx), float(cy), float(fx), float(fy), float(rx), float(ry)
        m.half, m.lw, m.yh, m.fs, m.ch = float(view.half), float(view.LW), float(view.yh), float(view.FS), float(view.CH)
        m.persp = float(view.persp) if view.persp is not None else 0.0
        m.flat, m.zm, m.eye = float(flat), float(zm), float(view.EYE)
        m.light[0], m.light[1], m.light[2] = light
        if air is not None:
            m.air, m.haze, m.vis = 1, (air[0][0] << 16) | (air[0][1] << 8) | air[0][2], float(air[1])
        m.flash = 1 if flash else 0
        if tint:
            m.tinted, m.tint = 1, (tint[0] << 16) | (tint[1] << 8) | tint[2]
    except (TypeError, ValueError, OverflowError, IndexError):
        return False
    out = frame.model_draw(m, (pts, corner, mat, own, colour, got[1]))
    if out is False or not out[0]:
        return out if out is False else None
    return out[1], (out[2] + out[3]) / 2


# ---- 0.7: rooms as faces (engine/mesh.py's mesh view) ------------------------------------------------------- #
_skies = {}                                           # id(sky rows) -> (rows, bytes)


def _sky_bytes(rows):
    got = _skies.get(id(rows))
    if got is None or got[0] is not rows:
        if len(_skies) > 16:
            _skies.clear()
        got = _skies[id(rows)] = (rows, bytes(v for row in rows for c in row for v in c))
    return got[1]


def floor_kind(cell):
    """A floor's clio_room_cell kind and belt, as View._backdrop_c works them out."""
    kind = belt = 0
    if getattr(cell, "plate", None):
        kind = 2 if cell.down else 1
    elif getattr(cell, "sunk", False):
        kind = 3
    elif getattr(cell, "teleport", None):
        kind = 4
    elif getattr(cell, "lift", None):
        kind = 5
    elif getattr(cell, "conveyor", None) is not None:
        kind, belt = 6, cell.conveyor
        if not isinstance(belt, int) or not 0 <= belt < 4:
            raise Odd("a belt's way")
    elif getattr(cell, "oil", False):
        kind = 7
    elif getattr(cell, "slick", False):
        kind = 8
    elif getattr(cell, "scorched", False):
        kind = 9
    return kind, belt


def pack_rooms(faces, mesh_mod):
    """The faces as clio_rooms takes them: ints, geo, xy, and the tiles (each once). Raises Odd for what the library
    does not take."""
    ints, geo, xy = array("i"), array("d"), array("q")
    tiles, index = [], {}

    def tile(rows):
        if rows is None:
            return -1
        i = index.get(id(rows))
        if i is None:
            i = index[id(rows)] = len(tiles)
            tiles.append(_texture(rows))
        return i

    FLOOR, CEILING = mesh_mod.FLOOR, mesh_mod.CEILING
    for f in faces:
        kind = f.kind
        if kind == FLOOR:
            cell, tex, fixed, toxic, fire, mark = f.info
            k, belt = floor_kind(cell) if fixed else (0, 0)
            px, py = (cell.x, cell.y) if k in (7, 9) else (f.ix, f.iy)
            ints.extend((kind, 0, tile(tex), 0, k, belt, 1 if toxic else 0, 1 if fire else 0,
                         1 if mark == "warn" else 2 if mark == "burn" else 0))
            xy.extend((f.ix, f.iy, px, py))
        elif kind == CEILING:
            sky = f.info == "sky"
            ints.extend((kind, 0, -1 if sky else tile(f.info), 0, 10 if sky else 0, 0, 0, 0, 0))
            xy.extend((f.ix, f.iy, f.ix, f.iy))
        else:
            ints.extend((kind, f.side, tile(f.tex), 1 if f.wall else 0, 0, 0, 0, 0, 0))
            xy.extend((0, 0, 0, 0))
        geo.extend((float(f.at), float(f.lo), float(f.hi), float(f.h0), float(f.h1), float(f.top), float(f.opened)))
    return ints, geo, xy, tiles


def rooms(frame, view, mesh_mod, faces, cam, eye, phase, sky_rows):
    """The mesh view's faces drawn into the frame by the library (0.7): the (pixel, face) pairs left to the caller,
    or None when the library cannot draw them (then the Python does)."""
    lib = load()
    if lib is None or not hasattr(lib, "clio_frame_rooms") or not isinstance(phase, int) or not models_agree():
        return None
    sloped = any(f.gx or f.gy or f.h0b != f.h0 or f.h1b != f.h1 for f in faces)
    if sloped and not hasattr(lib, "clio_frame_rooms2"):
        return None                                       # slopes: the Python draws them (the library: 0.9)
    try:
        ints, geo, xy, tiles = pack_rooms(faces, mesh_mod)
    except (Odd, TypeError, ValueError, OverflowError, IndexError):
        return None
    n = len(tiles)
    texels = (ctypes.c_void_p * max(1, n))(*[t[3].buffer_info()[0] for t in tiles])
    tw = array("i", [t[1] for t in tiles] or [0])
    th = array("i", [t[2] for t in tiles] or [0])
    sky = ctypes.c_char_p(_sky_bytes(sky_rows)) if sky_rows else None
    cx, cy, fx, fy, rx, ry = cam
    r = _Rooms(view.PW, view.PH, view.half, float(view.yh), view.LW * mesh_mod.Z0, view.TALL * mesh_mod.Z0,
               float(cx), float(cy), float(fx), float(fy), float(rx), float(ry), mesh_mod.Z0, float(eye),
               float(mesh_mod.FAR), mesh_mod.FADE, mesh_mod.NEAR, mesh_mod.SIDE, mesh_mod.NONE, phase,
               ctypes.cast(sky, ctypes.c_void_p) if sky else None, len(sky_rows) if sky_rows else 0, len(faces),
               _ptr(ints) if len(ints) else None, _ptr(geo) if len(geo) else None, _ptr(xy) if len(xy) else None, n,
               ctypes.addressof(texels), _ptr(tw), _ptr(th))
    later = (ctypes.c_int32 * (2 * view.PW * view.PH))()
    count = ctypes.c_int(0)
    if sloped:                                            # 0.9: each face's hi-end bottom and top, its rise
        slopes = array("d", [v for f in faces for v in (float(f.h0b), float(f.h1b), float(f.gx), float(f.gy))])
        if lib.clio_frame_rooms2(frame.ref, ctypes.byref(r), _ptr(slopes), later, ctypes.byref(count)) != 0:
            return None
    elif lib.clio_frame_rooms(frame.ref, ctypes.byref(r), later, ctypes.byref(count)) != 0:
        return None
    return [(later[2 * k], later[2 * k + 1]) for k in range(count.value)]
