# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""A first-person picture kept in CLIo Picture (0.4 and later), from the floor to the cells.

``Frame`` owns the pixels (and in open land each pixel's distance) as C buffers. The View draws into them by the
library's calls where it has one (faces, pictures, models, colour changes), and by ``FrameRow``s - which behave
as the picture's rows did (``px[y][x]``), including DepthRow's rule in open land - for the rest (glows, blasts,
the cockpit). ``CoverView`` stands in for the View's ``cover`` dict over the frame's grid."""
from __future__ import annotations

from array import array

try:                                        # not in every Python
    import ctypes
except ImportError:                         # pragma: no cover
    ctypes = None

from . import _Dots, _Frame, _More, _Tone, _chars, _colours, _ptr, _rgb, _texture, load, steps

FAR = 99.0
_U32 = "I" if array("I").itemsize == 4 else "L"


class FrameRow:
    """A row of the frame's pixels, as a list of (r, g, b) would be; in open land a write lands only where the
    land is further off than ``view.cur_z`` (as DepthRow) - and while things are drawn over a G-buffer, as
    surface.GRow."""
    __slots__ = ("rgb", "depth", "view", "base", "pw", "frame")

    def __init__(self, frame, y):
        self.rgb, self.view, self.base, self.pw = frame.rgb, frame.view, y * frame.pw, frame.pw
        self.depth = None
        self.frame = frame

    def __len__(self):
        return self.pw

    def __getitem__(self, x):
        if isinstance(x, slice):
            return [_rgb[v] for v in self.rgb[self.base:self.base + self.pw][x]]
        if x < 0:
            x += self.pw
        if not 0 <= x < self.pw:
            raise IndexError("list index out of range")
        return _rgb[self.rgb[self.base + x]]

    def __setitem__(self, x, c):
        if x < 0:
            x += self.pw
        if not 0 <= x < self.pw:
            raise IndexError("list assignment index out of range")
        i = self.base + x
        d = self.depth
        view = self.view
        if self.frame.marking and view.cur_thing and d is not None:     # a thing over lit surfaces
            z = view.cur_z
            if d[i] >= z:
                self.rgb[i] = (c[0] << 16) | (c[1] << 8) | c[2]
                if z > -1e8:
                    d[i] = z
                fr = self.frame
                fr.kinds[i] = 7
                fr.mats[i] = 0x80 if view.cur_glow else 0
            return
        if d is None or d[i] > view.cur_z:
            self.rgb[i] = (c[0] << 16) | (c[1] << 8) | c[2]

    def __iter__(self):
        return iter([_rgb[v] for v in self.rgb[self.base:self.base + self.pw]])


class FramePx(list):
    """The picture's rows (FrameRows), with its frame."""
    frame = None


class CoverView:
    """View.cover over the frame's grid: the nearest wall or thing over each character cell."""
    __slots__ = ("buf", "W", "VR")

    def __init__(self, buf, W, VR):
        self.buf, self.W, self.VR = buf, W, VR

    def get(self, key, default=None):
        r, c = key
        if 0 <= r < self.VR and 0 <= c < self.W:
            v = self.buf[r * self.W + c]
            if v < FAR:
                return v
        return default

    def __getitem__(self, key):
        v = self.get(key)
        if v is None:
            raise KeyError(key)
        return v

    def __setitem__(self, key, v):
        r, c = key
        if 0 <= r < self.VR and 0 <= c < self.W:
            self.buf[r * self.W + c] = v

    def __contains__(self, key):
        return self.get(key) is not None


class Frame:
    """A View's picture in the library: made once for its size, started again for each picture."""

    def __init__(self, lib, view):
        self.lib, self.view = lib, view
        self.pw, self.ph, self.sx, self.sy = view.PW, view.PH, view.sx, view.sy
        self.W, self.VR = self.pw // self.sx, self.ph // self.sy
        n = self.pw * self.ph
        self.rgb = (ctypes.c_uint32 * n)()
        self.depth = (ctypes.c_double * n)()
        self.cover = (ctypes.c_double * (self.W * self.VR))()
        self.far = array("d", [FAR]) * (self.W * self.VR)
        self.zbuf = (ctypes.c_double * n)()
        self.zgen = (ctypes.c_uint32 * n)()
        self.s = _Frame(self.pw, self.ph, self.sx, self.sy, ctypes.addressof(self.rgb), None, 0.0,
                        ctypes.addressof(self.cover), ctypes.addressof(self.zbuf), ctypes.addressof(self.zgen), 0)
        self.ref = ctypes.byref(self.s)
        self.rows = [FrameRow(self, y) for y in range(self.ph)]
        self.px = FramePx(self.rows)
        self.px.frame = self
        self.cover_view = CoverView(self.cover, self.W, self.VR)
        self.land = False
        self.kinds = self.mats = self.own = None              # the G-buffer (CLIo Picture 0.8), made when wanted
        self.more = None
        self.marking = self.gbuf = False
        self._held = ()

    def fits(self, view):
        return (view.PW, view.PH, view.sx, view.sy) == (self.pw, self.ph, self.sx, self.sy) and view is self.view

    def start(self, land):
        """A new picture: nothing covered yet; distances kept (open land) or not (rooms)."""
        ctypes.memmove(self.cover, self.far.buffer_info()[0], len(self.far) * 8)
        self.more_off()
        self.land = land
        self.s.depth = ctypes.addressof(self.depth) if land else None
        d = self.depth if land else None
        for r in self.rows:
            r.depth = d
        return self.px

    def put_picture(self, rows, depth):
        """A picture made in Python (rows of (r, g, b)) and each pixel's distance (pw * ph)."""
        n = self.pw * self.ph
        flat = array("I", [(c[0] << 16) | (c[1] << 8) | c[2] for row in rows for c in row])
        ctypes.memmove(self.rgb, flat.buffer_info()[0], n * 4)
        ctypes.memmove(self.depth, depth.buffer_info()[0], n * 8)

    def put_bytes(self, data):
        """The pixels as kept by bytes(frame.rgb)."""
        ctypes.memmove(self.rgb, data, len(data))

    def sync(self):
        """The View's cur_z, for the library's depth test (and what is drawn now, over a G-buffer)."""
        self.s.cur_z = self.view.cur_z
        m = self.more
        if m is not None:
            m.thing = 1 if self.view.cur_thing else 0
            m.glow = 1 if self.view.cur_glow else 0

    # ---- 0.8: the G-buffer, lit surfaces ------------------------------------------------------------ #
    def more_on(self, faces, materials, gbuf, low):
        """What 0.8 adds, handed over beside the frame until more_off: a G-buffer (``gbuf``) the rooms fill - each
        face's material (Face.mat) and the glowing colours of each material - and floors at half width (``low``)."""
        n = self.pw * self.ph
        if gbuf and self.kinds is None:
            self.kinds, self.mats, self.own = (ctypes.c_uint8 * n)(), (ctypes.c_uint8 * n)(), (ctypes.c_uint8 * n)()
        face_mat = array("i", [f.mat for f in faces] or [0])
        glow_at, glow_rgb = array("i"), array(_U32)
        for m in materials:                                   # each material's glowing colours, one after another
            glow_at.append(len(glow_rgb))
            glow_rgb.extend((c[0] << 16) | (c[1] << 8) | c[2] for c in sorted(m.glow))
        glow_at.append(len(glow_rgb))
        glow_rgb.append(0)                                    # never empty: an address to hand over
        self._held = (face_mat, glow_at, glow_rgb)
        addr = ctypes.addressof
        self.more = _More(addr(self.kinds) if gbuf else None, addr(self.mats) if gbuf else None,
                          addr(self.own) if gbuf else None, 0, 1, 0, len(faces), _ptr(face_mat), len(materials),
                          _ptr(glow_at), _ptr(glow_rgb), 1 if low else 0)
        self.lib.clio_frame_more(self.ref, ctypes.byref(self.more))
        self.gbuf = bool(gbuf)

    def more_off(self):
        if self.more is not None and hasattr(self.lib, "clio_frame_more"):
            self.lib.clio_frame_more(self.ref, None)
        self.more = None
        self.marking = self.gbuf = False

    def mark(self, on):
        """Things drawn from now on mark the G-buffer (or not)."""
        self.marking = bool(on) and self.more is not None and self.gbuf
        if self.more is not None:
            self.more.marking = 1 if self.marking else 0

    def surface(self, s):
        """clio_frame_surface: the picture lit by its G-buffer; False if the library would not."""
        self.mark(False)
        return self.lib.clio_frame_surface(self.ref, ctypes.byref(s)) == 0

    def flip(self):
        self.lib.clio_frame_flip(self.ref)

    # ---- drawing ----------------------------------------------------------------------------------- #
    def front(self, tex, X0, X1, Y0, Y1, x0, w, y0, h, opened, fog, dist):
        _rows, tw, th, texels = _texture(tex)
        self.sync()
        self.lib.clio_frame_front(self.ref, texels.buffer_info()[0], tw, th, X0, X1, Y0, Y1, x0, w, y0, h,
                                  float(opened), fog, dist)

    def side(self, tex, xs, zcs, fogs, half, span, yh, ch, fs, opened, z):
        _rows, tw, th, texels = _texture(tex)
        self.lib.clio_frame_side(self.ref, texels.buffer_info()[0], tw, th, len(xs), _ptr(xs), _ptr(zcs),
                                 _ptr(fogs), half, span, yh, ch, fs, float(opened), z)

    def blit(self, rows, x0, y0, s, sw, sh, tone, dist):
        _rows, nw, nh, texels = _texture(rows)
        self.sync()
        self.lib.clio_frame_blit(self.ref, texels.buffer_info()[0], nw, nh, x0, y0, s, sw, sh,
                                 None if tone is None else ctypes.byref(tone), 0 if dist is None else 1,
                                 0.0 if dist is None else float(dist))

    def darken(self, x_from, x_to, y_from, y_to, k):
        self.sync()
        self.lib.clio_frame_darken(self.ref, x_from, x_to, y_from, y_to, k)

    def triangles(self, tris):
        """A model's triangles: [(pts, cols)] as model.raster takes them, nearer hiding further."""
        self.lib.clio_frame_model(self.ref)
        self.sync()
        pts, cols = (ctypes.c_double * 9)(), (ctypes.c_double * 9)()
        for p, c in tris:
            pts[0], pts[1], pts[2] = p[0]
            pts[3], pts[4], pts[5] = p[1]
            pts[6], pts[7], pts[8] = p[2]
            smooth = isinstance(c[0], (list, tuple))
            if smooth:
                cols[0], cols[1], cols[2] = c[0]
                cols[3], cols[4], cols[5] = c[1]
                cols[6], cols[7], cols[8] = c[2]
            else:
                cols[0], cols[1], cols[2] = c
            self.lib.clio_frame_triangle(self.ref, pts, cols, 1 if smooth else 0)

    def model_draw(self, m, held):
        """A model (clio_model_draw ``m``; ``held`` keeps its arrays alive): [shown, top, x min, x max], or False."""
        self.sync()
        out = (ctypes.c_double * 4)()
        if self.lib.clio_frame_model_draw(self.ref, ctypes.byref(m), out) != 0:
            return False
        return list(out)

    meshes = True                         # models from kept meshes (CLIo Picture 0.6), where the library has them

    def mesh_draw(self, mesh, inst, m, held):
        """A model from its kept mesh (``inst``: its posed corners and where it stands; ``held`` keeps the corners'
        array alive): [shown, top, x min, x max], or False."""
        self.sync()
        out = (ctypes.c_double * 4)()
        if self.lib.clio_frame_mesh_draw(self.ref, mesh.ref, ctypes.byref(inst), ctypes.byref(m), out) != 0:
            return False
        return list(out)

    def recolour(self, how, k=0.0, colour=(0, 0, 0)):
        self.lib.clio_frame_recolour(self.ref, how, float(k), (colour[0] << 16) | (colour[1] << 8) | colour[2])

    def vignette(self, hurt, where):
        self.sync()
        self.lib.clio_frame_vignette(self.ref, float(hurt), {"left": 1, "right": 2, "back": 3}.get(where, 0))

    def shake(self, s):
        self.lib.clio_frame_shake(self.ref, s)

    def canopy(self, colour):
        self.sync()
        self.lib.clio_frame_canopy(self.ref, (colour[0] << 16) | (colour[1] << 8) | colour[2])

    def dashboard(self, colour, h, y0, x0, x1, gx0, gx1, gy, lit, low):
        self.sync()
        self.lib.clio_frame_dashboard(self.ref, (colour[0] << 16) | (colour[1] << 8) | colour[2], h, y0, x0, x1, gx0,
                                      gx1, gy, lit, 1 if low else 0)

    def cage(self):
        self.sync()
        self.lib.clio_frame_cage(self.ref)

    # ---- to cells ---------------------------------------------------------------------------------- #
    def halves(self, over, shade, mix):
        """View.halves: a character cell is two pixels, top over bottom."""
        PW, W = self.pw, self.W
        get = _rgb.__getitem__
        nones = [None] * W
        rgb = self.rgb
        cells = []
        for r in range(self.VR):
            a = 2 * r * PW
            cells.append(list(zip(nones, map(get, rgb[a:a + W]), map(get, rgb[a + PW:a + PW + W]))))
        for (r, x), o in over.items():
            if o and 0 <= r < self.VR and 0 <= x < W:
                top, bot = cells[r][x][1], cells[r][x][2]
                cells[r][x] = (o[0], o[1], o[2] or shade(mix(top, bot, 0.5), 0.45))
        return cells

    def dots(self, fill, level, reach=215.0, most=1.9, flat=9.0):
        """View.braille's cells (without its labels), or None."""
        cols, rows = self.W, self.VR
        key = (bool(fill), level, reach, most, flat)
        style = _dot_styles.get(key)
        if style is None:
            style = _dot_styles[key] = _Dots(1 if fill else 0, (ctypes.c_double * 8)(*steps(level)), reach, most, flat)
        out = ctypes.create_string_buffer(cols * rows * 8)
        if self.lib.clio_dots32(self.rgb, cols, rows, ctypes.byref(style), out) != 0:
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

    def lists(self):
        """The picture as plain rows of (r, g, b): to go on in Python."""
        get = _rgb.__getitem__
        PW = self.pw
        return [list(map(get, self.rgb[y * PW:(y + 1) * PW])) for y in range(self.ph)]


_dot_styles = {}


def tone(kind, fog=1.0, haze=(0, 0, 0), k=0.0, gone=0.0, step=1.0, mid=0, flash=False, tint=None):
    t = _Tone()
    t.kind, t.fog, t.k = kind, float(fog), float(k)
    t.haze = (haze[0] << 16) | (haze[1] << 8) | haze[2]
    t.gone, t.step, t.id = float(gone or 0.0), float(step), int(mid)
    t.flash = 1 if flash else 0
    if tint:
        t.tinted, t.tint = 1, (tint[0] << 16) | (tint[1] << 8) | tint[2]
    return t


def surfaces_ok():
    """Whether the library lights surfaces by their materials (engine/surface.py) - CLIo Picture 0.8."""
    lib = load()
    return lib is not None and hasattr(lib, "clio_frame_surface")


def frame_for(view):
    """The View's Frame (made when its size changes), or None without a library that has frames."""
    lib = load()
    if lib is None or not hasattr(lib, "clio_frame_blit"):
        return None
    fr = view.__dict__.get("_frame")
    if fr is None or not fr.fits(view):
        fr = view._frame = Frame(lib, view)
    return fr
