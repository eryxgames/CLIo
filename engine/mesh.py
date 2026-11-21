# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""The mesh view: a level's rooms as faces seen through a true perspective, with floors and ceilings at
their own heights.

The classic picture of a room shrinks things to 0.64 of their size a cell (:mod:`engine.firstperson`). The
mesh view sees rooms as open land is seen: from a camera ``Z0`` cells behind the player, things ``z`` cells
ahead are ``Z0 / (z + Z0)`` as big. Near cells become faces - each open cell's floor and ceiling at its own
heights (``"height"``, ``"ceiling_height"`` in the map's legend), the faces of the walls turned to it, and the
steps and lintels between cells of different heights - and each face is filled pixel by pixel: the pixel's
ray meets the face's plane, which gives the point of the world it shows, so its texel, its distance and its
fog. Each pixel keeps its distance, and what is drawn after the faces (monsters, items, fire, models) lands
only where it is nearer, as in open land (DepthRow's rule).

Fog is open land's (a thing as big as ``t`` keeps 0.18 + 0.82 t^0.75 of its colour), a face seen from the
side is darker (0.72), and the last cells before ``FAR`` fade out. Colours are worked out in 256 steps of
light, so that each colour in each light is made once a picture.

Faces behind the player's cell are drawn only when they are turned sideways to him (as the classic picture
draws the walls beside and behind him): the camera stands behind him, and a pillar at his back would hide
everything otherwise."""
from __future__ import annotations

import math
import sys
from array import array

from . import firstperson as fp

Z0 = 1.6                     # the camera stands this far behind the player (cells), as in open land
FAR = 16                     # cells of rooms drawn ahead
FADE = 4.0                   # the last cells before FAR fade to black
NEAR = 0.05                  # nothing nearer the camera than this (cells)
BEHIND = -0.5                # behind this (the player's cell's back edge) only faces turned sideways
SIDE = 0.72                  # a face seen side on is this much darker (as the classic side faces)
NONE = 1e9                   # the distance of a pixel no face covers

FLOOR, CEILING, XWALL, YWALL = 0, 1, 2, 3


def fog_of(z):
    """How much of a colour is left z cells ahead: open land's fog, and the fade before FAR."""
    t = Z0 / (z + Z0)
    fog = 0.18 + 0.82 * min(1.0, t) ** 0.75
    fade = (FAR - z) / FADE
    return fog, (0.0 if fade < 0.0 else 1.0 if fade > 1.0 else fade)


class Face:
    """One face of the rooms: a floor or ceiling (``kind`` FLOOR / CEILING, the cell (ix, iy) at height ``at``)
    or an upright face on the line x = ``at`` (XWALL) or y = ``at`` (YWALL), from ``lo`` to ``hi`` along the
    line, ``h0`` to ``h1`` high, turned towards ``side`` (+1 or -1 along x or y)."""
    __slots__ = ("kind", "at", "lo", "hi", "h0", "h1", "side", "tex", "top", "opened", "ix", "iy", "info", "wall",
                 "label", "cell")

    def __init__(self, kind, at, lo=0.0, hi=0.0, h0=0.0, h1=0.0, side=1, tex=None, top=1.0, opened=0.0, ix=0, iy=0,
                 info=None, wall=False):
        self.kind, self.at, self.lo, self.hi, self.h0, self.h1, self.side = kind, at, lo, hi, h0, h1, side
        self.tex, self.top, self.opened, self.ix, self.iy, self.info, self.wall = tex, top, opened, ix, iy, info, wall
        self.label = self.cell = None

    def corners(self):
        """The face's four corners (x, y, height), going round."""
        if self.kind in (FLOOR, CEILING):
            x, y, h = self.ix, self.iy, self.at
            return [(x - 0.5, y - 0.5, h), (x + 0.5, y - 0.5, h), (x + 0.5, y + 0.5, h), (x - 0.5, y + 0.5, h)]
        h0 = self.h0 + self.opened * (self.h1 - self.h0) if self.opened else self.h0     # a door slides up
        if self.kind == XWALL:
            return [(self.at, self.lo, h0), (self.at, self.hi, h0), (self.at, self.hi, self.h1), (self.at, self.lo, self.h1)]
        return [(self.lo, self.at, h0), (self.hi, self.at, h0), (self.hi, self.at, self.h1), (self.lo, self.at, self.h1)]


def heights(cell):
    """A cell's floor and ceiling heights (in walls' heights; the classic room is 0 and 1)."""
    h = float(getattr(cell, "height", 0.0) or 0.0)
    c = getattr(cell, "ceiling_height", None)
    return h, (h + 1.0 if c is None else float(c))


class Mesh:
    """The faces of the rooms near the camera, and their picture."""

    def __init__(self, view):
        self.view = view

    # ---- the faces ------------------------------------------------------------------------------------ #
    def faces(self, lv, cam, eye, doors, phase, ex, ey):
        """The faces a camera at (ex, ey, eye) can see near the player, each turned towards it."""
        view = self.view
        cx, cy, fx, fy, rx, ry = cam
        cell_at = lv.cell
        see_through = getattr(lv, "see_through", ())
        nv = getattr(getattr(lv, "player", None), "nightvision", False)
        texture_of, floor_info, ceiling_of = {}, {}, {}
        out = []

        def opened_of(c, x, y):
            return doors.get((x, y), c.open) if c.kind == "door" else 0.0

        def walled(c, x, y):                                 # drawn as a wall
            return c is None or c.drawn_as_wall(doors.get((x, y)) if c.kind == "door" else None)

        def opaque(c, x, y):                                 # a wall nothing is seen through
            if c is None:
                return True
            if c.kind == "door":
                return opened_of(c, x, y) <= 0.0 and c.texture() not in see_through
            return c.drawn_as_wall() and c.texture() not in see_through

        def tex(c, name=None):
            name = name or c.texture()
            t = texture_of.get((name, c.kind == "panel"))
            if t is None:
                t = view.texture(lv, name, phase)
                if c.kind == "panel" and nv:                 # the goggles show what is hollow
                    t = [[None if v is None else fp.mix(v, (200, 110, 255), 0.55) for v in row] for row in t]
                texture_of[(name, c.kind == "panel")] = t
            return t

        def upright(x, y, d, h0, h1, top, c, opened=0.0, wall=False, name=None):
            """The face on the edge of cell (x, y) towards DIRS[d], turned back into (x, y)."""
            dx, dy = fp.DIRS[d]
            if dx:
                f = Face(XWALL, x + 0.5 * dx, y - 0.5, y + 0.5, h0, h1, -dx, tex(c, name), top, opened, wall=wall)
                if (ex - f.at) * f.side <= 0:
                    return None
            else:
                f = Face(YWALL, y + 0.5 * dy, x - 0.5, x + 0.5, h0, h1, -dy, tex(c, name), top, opened, wall=wall)
                if (ey - f.at) * f.side <= 0:
                    return None
            if h1 - h0 <= 1e-9:
                return None
            out.append(f)
            return f

        reach0 = view.half / (view.LW * Z0)                   # half the picture's width in cells, a cell per Z0 away
        for x, y in self.cells_near(cam, reach0):
            if True:
                c = cell_at(x, y)
                if c is None or opaque(c, x, y):
                    continue
                h, top = heights(c)
                if not walled(c, x, y) or c.kind == "door" or c.clear:      # the floor and ceiling of the cell
                    if eye > h:
                        info = floor_info.get((x, y))
                        if info is None:
                            info = floor_info[(x, y)] = self.under(lv, c, x, y, phase)
                        out.append(Face(FLOOR, h, ix=x, iy=y, info=info))
                    if eye < top:
                        ceil = ceiling_of.get((x, y))
                        if ceil is None:
                            ceil = ceiling_of[(x, y)] = self.above(lv, c, phase)
                        out.append(Face(CEILING, top, ix=x, iy=y, info=ceil))
                if walled(c, x, y):                           # a door, bars or a field: faces come from the cells beside
                    for d in range(4):
                        nx, ny = x + fp.DIRS[d][0], y + fp.DIRS[d][1]
                        n = cell_at(nx, ny)
                        if opaque(n, nx, ny):
                            upright(x, y, d, h, top, top, n if n is not None else c, wall=True)
                    continue
                for d in range(4):
                    nx, ny = x + fp.DIRS[d][0], y + fp.DIRS[d][1]
                    n = cell_at(nx, ny)
                    if walled(n, nx, ny):                     # a wall's face, from this cell's floor to its ceiling
                        f = upright(x, y, d, h, top, top, n if n is not None else c, opened_of(n, nx, ny) if n else 0.0,
                                    wall=True)
                        if f is not None and n is not None and n.label:
                            f.label, f.cell = n.label, n
                        continue
                    nh, ntop = heights(n)
                    if nh > h + 1e-9:                         # a step up to the next cell: its riser
                        upright(x, y, d, h, min(nh, top), min(nh, top), n, name=getattr(n, "step", None) or "step")
                    if ntop < top - 1e-9 and not getattr(n, "sky", False):      # a lintel down to the next cell
                        upright(x, y, d, max(ntop, h), top, top, n)
        return out

    @staticmethod
    def cells_near(cam, reach0):
        """The cells that can show, nearest rows first: for the four facings row by row ahead of the player, as the
        classic picture walks them; between two facings (a turn being drawn), every cell round him inside the
        picture's wedge, by distance ahead."""
        cx, cy, fx, fy, rx, ry = cam
        icx, icy = int(round(cx)), int(round(cy))
        if all(float(v).is_integer() for v in (fx, fy, rx, ry)):
            fx, fy, rx, ry = int(fx), int(fy), int(rx), int(ry)
            for dz in range(-fp.BACK, FAR + 1):
                reach = int(reach0 * (dz + 0.5 + Z0)) + 2
                for da in range(-reach, reach + 1):
                    yield icx + fx * dz + rx * da, icy + fy * dz + ry * da
            return
        r = FAR + fp.BACK + 2
        found = []
        for y in range(icy - r, icy + r + 1):
            for x in range(icx - r, icx + r + 1):
                dz = (x - cx) * fx + (y - cy) * fy
                if dz < -fp.BACK - 0.5 or dz > FAR + 0.5:
                    continue
                da = (x - cx) * rx + (y - cy) * ry
                if abs(da) > reach0 * (dz + 0.5 + Z0) + 2.5:
                    continue
                found.append((round(dz, 9), round(da, 9), x, y))
        found.sort()
        for _dz, _da, x, y in found:
            yield x, y

    @staticmethod
    def under(lv, cell, ix, iy, phase):
        """How a cell's floor is drawn (as View._backdrop's ``under``): the cell, its tile, whether something is
        set in it, toxic, burning, its mark."""
        tiles = getattr(lv, "tiles", None) or {}
        wet = getattr(getattr(lv, "player", None), "diving", False) and "seabed" in tiles
        tile = getattr(cell, "floor", None) or (None if cell.toxic else getattr(lv, "floor_tile", None))
        if wet and getattr(cell, "deep", False):
            tile = "seabed"
        fixed = bool(getattr(cell, "plate", None) or getattr(cell, "sunk", False) or getattr(cell, "teleport", None)
                     or getattr(cell, "lift", None) or getattr(cell, "conveyor", None) is not None
                     or getattr(cell, "oil", False) or getattr(cell, "slick", False) or getattr(cell, "scorched", False))
        fires = getattr(lv, "fires", None) or ()
        return (cell, fp.View.texture(lv, tile, phase) if tile else None, fixed, cell.toxic, (ix, iy) in fires,
                lv.marks.get((ix, iy)))

    @staticmethod
    def above(lv, cell, phase):
        """A cell's ceiling: "sky", its tile, or None (the engine's own)."""
        tiles = getattr(lv, "tiles", None) or {}
        wet = getattr(getattr(lv, "player", None), "diving", False) and "seabed" in tiles
        if getattr(lv, "sky_look", None) is not None and getattr(cell, "sky", False):
            return "sky"
        tile = ("surface" if wet and getattr(cell, "deep", False) and "surface" in tiles else
                getattr(cell, "ceiling", None)) or getattr(lv, "ceiling_tile", None)
        return fp.View.texture(lv, tile, phase) if tile else None

    # ---- the picture ---------------------------------------------------------------------------------- #
    def draw(self, lv, cam, eye, phase, doors, sky, later=None):
        """The picture (rows of (r, g, b)), each pixel's distance ahead of the player (``z``; NONE where no face
        is), the nearest wall over each character cell, and the labels of walls seen close by. With ``later`` (a
        list), teleporters' floors are left as CLIo Picture leaves them - haze, their distance set - and their
        (pixel, face) pairs go into it: what the library's own test is made from."""
        view = self.view
        PW, PH, half, yh = view.PW, view.PH, view.half, view.yh
        cx, cy, fx, fy, rx, ry = cam
        ex, ey = cx - fx * Z0, cy - fy * Z0                    # the camera
        lx, ly = view.LW * Z0, view.TALL * Z0                 # pixels to a cell across, to a wall's height, Z0 off
        dirx, diry = [], []                                   # each column's ray: how far across it goes a cell ahead
        for x in range(PW):
            sa = (x + 0.5 - half) / lx
            dirx.append(fx + sa * rx)
            diry.append(fy + sa * ry)
        sb = [(y + 0.5 - yh) / ly for y in range(PH)]          # each row's ray: how far down it goes a cell ahead
        rgb = [[fp.HAZE] * PW for _ in range(PH)]
        zbuf = array("d", [NONE]) * (PW * PH)
        walls = bytearray(PW * PH)
        lit = {}

        def light(z, k):                                      # the light at z ahead, times k: 0..256
            fog, fade = fog_of(z)
            return int(fog * k * fade * 256.0)

        def colour(c, q):
            key = (c, q)
            v = lit.get(key)
            if v is None:
                v = lit[key] = fp.shade(c, q / 256.0)
            return v

        labels = []
        for k, face in enumerate(self.faces(lv, cam, eye, doors, phase, ex, ey)):
            spans = self.spans(face, cam, eye, ex, ey)
            if not spans:
                continue
            kind = face.kind
            if kind in (FLOOR, CEILING):
                self.flat(face, spans, rgb, zbuf, sb, dirx, diry, ex, ey, eye, light, colour, sky, phase,
                          later=None if later is None else (later, k))
                continue
            n = (face.side, 0) if kind == XWALL else (0, face.side)
            k = SIDE + (1.0 - SIDE) * abs(n[0] * fx + n[1] * fy)
            TH, TW = len(face.tex), len(face.tex[0])
            ux, uy = n[1], -n[0]                              # along the face, left to right as seen from its front
            left = min(ux * a + uy * b for a, b, _h in face.corners())
            cols = {}
            for y, x0, x1 in spans:
                row, sby, base = rgb[y], sb[y], y * PW
                for x in range(x0, x1):
                    col = cols.get(x)
                    if col is None:
                        if kind == XWALL:
                            dd = dirx[x]
                            d = (face.at - ex) / dd if dd else -1.0
                        else:
                            dd = diry[x]
                            d = (face.at - ey) / dd if dd else -1.0
                        if d <= NEAR:
                            col = cols[x] = (None,)
                        else:
                            wx, wy = ex + d * dirx[x], ey + d * diry[x]
                            u = ux * wx + uy * wy - left
                            u = 0 if u < 0 else TW - 1 if u >= 1 else int(u * TW)
                            z = d - Z0
                            col = cols[x] = (d, z, u, light(z, k))
                    if col[0] is None:
                        continue
                    d, z, u, q = col
                    i = base + x
                    if z >= zbuf[i]:
                        continue
                    v = face.top - (eye - sby * d) + face.opened
                    v -= math.floor(v)
                    c = face.tex[min(TH - 1, int(v * TH))][u]
                    if c is None:
                        continue
                    zbuf[i] = z
                    walls[i] = 1
                    row[x] = colour(c, q)
            if face.label is not None and face.side * (fx if kind == XWALL else fy) < 0:   # a wall facing the player
                labels.append(face)
        self.holes(lv, cam, eye, doors, rgb, zbuf)
        cover = self.cover(zbuf, walls)
        over = []
        for face in labels:                                   # labels of walls seen close by, as View.front_face's
            hit = self.label_at(face, cam, eye, zbuf)
            if hit is not None:
                over.append((hit, face.label, getattr(face.cell, "label_role", None), hit[4]))
        return rgb, zbuf, cover, [(h[:4], t, r, z) for h, t, r, z in over]

    def draw_frame(self, lv, cam, eye, phase, doors, sky, frame):
        """The picture drawn by CLIo Picture (0.7) into the frame - pixels, distances, the walls' cover - and the
        labels; None when the library cannot (the Python draws it then)."""
        from . import picture
        view = self.view
        cx, cy, fx, fy, rx, ry = cam
        ex, ey = cx - fx * Z0, cy - fy * Z0
        faces = self.faces(lv, cam, eye, doors, phase, ex, ey)
        later = picture.rooms(frame, view, sys.modules[__name__], faces, cam, eye, phase, sky)
        if later is None:
            return None
        zbuf = frame.depth
        if later:                                             # teleporters' rings, as the Python draws them
            PW, half, yh = view.PW, view.half, view.yh
            lx, ly = view.LW * Z0, view.TALL * Z0
            dirx = [fx + ((x + 0.5 - half) / lx) * rx for x in range(PW)]
            diry = [fy + ((x + 0.5 - half) / lx) * ry for x in range(PW)]
            sb = [(y + 0.5 - yh) / ly for y in range(view.PH)]
            lit = {}

            def colour(c, q):
                v = lit.get((c, q))
                if v is None:
                    v = lit[(c, q)] = fp.shade(c, q / 256.0)
                return v
            cur, view.cur_z = view.cur_z, -1e9
            try:
                for pixel, k in later:
                    y, x = divmod(pixel, PW)
                    self.flat(faces[k], [(y, x, x + 1)], frame.rows, zbuf, sb, dirx, diry, ex, ey, eye, None, colour,
                              sky, phase, force=True)
            finally:
                view.cur_z = cur
        self.holes(lv, cam, eye, doors, frame.rows, zbuf)
        labels = []
        for face in faces:
            if face.label is not None and face.side * (fx if face.kind == XWALL else fy) < 0 and \
                    self.spans(face, cam, eye, ex, ey):
                hit = self.label_at(face, cam, eye, zbuf)
                if hit is not None:
                    labels.append((hit[:4], face.label, getattr(face.cell, "label_role", None), hit[4]))
        return labels

    def spans(self, face, cam, eye, ex, ey):
        """The pixels the face covers: (row, first column, column after the last), clipped to the picture."""
        view = self.view
        cx, cy, fx, fy, rx, ry = cam
        lx, ly = view.LW * Z0, view.TALL * Z0
        pts = []
        side_on = face.kind in (XWALL, YWALL) and abs((face.side if face.kind == XWALL else 0) * fx +
                                                       (face.side if face.kind == YWALL else 0) * fy) < 0.5
        behind = True
        for wx, wy, h in face.corners():                      # into the camera's space: across, ahead (d), height
            dx, dy = wx - ex, wy - ey
            d = dx * fx + dy * fy
            if d - Z0 > BEHIND:
                behind = False
            pts.append((dx * rx + dy * ry, d, h))
        if behind and not side_on:
            return None
        poly = []                                             # clipped at NEAR ahead of the camera
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            ina, inb = a[1] >= NEAR, b[1] >= NEAR
            if ina:
                poly.append(a)
            if ina != inb:
                p, q = (a, b) if a[1] < b[1] else (b, a)     # the same point whichever way the edge is walked
                t = (NEAR - p[1]) / (q[1] - p[1])
                poly.append((p[0] + (q[0] - p[0]) * t, NEAR, p[2] + (q[2] - p[2]) * t))
        if len(poly) < 3:
            return None
        half, yh = view.half, view.yh
        scr = [(half + a * lx / d, yh + (eye - h) * ly / d) for a, d, h in poly]
        ys = [p[1] for p in scr]
        y0 = max(0, int(math.ceil(min(ys) - 0.5)))
        y1 = min(view.PH, int(math.ceil(max(ys) - 0.5)))
        out = []
        m = len(scr)
        for y in range(y0, y1):
            yc = y + 0.5
            lo, hi = None, None
            for i in range(m):
                p, q = scr[i], scr[(i + 1) % m]
                if p[1] > q[1]:
                    p, q = q, p
                if p[1] <= yc < q[1]:
                    xc = p[0] + (yc - p[1]) * (q[0] - p[0]) / (q[1] - p[1])
                    if lo is None or xc < lo:
                        lo = xc
                    if hi is None or xc > hi:
                        hi = xc
            if lo is None:
                continue
            xa = max(0, int(math.ceil(lo - 0.5)))
            xb = min(view.PW, int(math.ceil(hi - 0.5)))
            if xa < xb:
                out.append((y, xa, xb))
        return out

    def flat(self, face, spans, rgb, zbuf, sb, dirx, diry, ex, ey, eye, light, colour, sky, phase, force=False,
             later=None):
        """A floor or a ceiling: each row of it is one distance off. With ``force``, pixels the library left to
        the Python (a teleporter's rings): drawn where the pixel still holds this floor's distance."""
        PW = self.view.PW
        floor = face.kind == FLOOR
        dh = eye - face.at
        ix, iy = face.ix, face.iy
        if floor:
            cell, tex, fixed, toxic, fire, mark = face.info
            pad = later is not None and fixed and not getattr(cell, "plate", None) and \
                not getattr(cell, "sunk", False) and getattr(cell, "teleport", None)    # the library's kind 4
        else:
            tex = face.info
        step = 2 if later is None and not force and getattr(self.view, "detail", "high") == "low" else 1
        for y, x0, x1 in spans:                              # low detail: every other pixel, each drawn twice
            s = sb[y]
            if s == 0.0:
                continue
            d = dh / s
            if d <= NEAR:
                continue
            z = d - Z0
            fog, fade = fog_of(z)
            q = int(fog * fade * 256.0)
            row, base = rgb[y], y * PW
            for x in range(x0 - (x0 & 1) if step == 2 else x0, x1, step):    # low: pairs from an even column
                i = base + x
                if force:
                    if zbuf[i] != z:
                        continue
                    one, two = True, False
                else:
                    one = x >= x0 and z < zbuf[i]
                    two = step == 2 and x + 1 < x1 and z < zbuf[i + 1]
                    if not (one or two):
                        continue
                xs = x if x >= x0 else x + 1                 # the pixel whose ray gives the colour
                ux = ex + d * dirx[xs] - ix
                uy = ey + d * diry[xs] - iy
                ux = -0.5 if ux < -0.5 else 0.4999 if ux > 0.4999 else ux
                uy = -0.5 if uy < -0.5 else 0.4999 if uy > 0.4999 else uy
                if not floor:
                    if tex == "sky":
                        v = sky[y][xs] if sky is not None and y < len(sky) else fp.HAZE
                    else:
                        c = None
                        if tex is not None:
                            th, tw = len(tex), len(tex[0])
                            c = tex[min(th - 1, int((uy + 0.5) * th))][min(tw - 1, int((ux + 0.5) * tw))]
                        if c is None:
                            c = fp.CEIL
                            if abs(ux) > 0.47 or abs(uy) > 0.47:
                                c = fp.CEIL_LINE
                            elif (ix * 7 + iy * 3) % 4 == 0 and abs(ux) < 0.24 and abs(uy) < 0.24:
                                c = fp.LIGHT
                        v = colour(c, q)
                else:
                    c = None                                 # the floor: as View._backdrop draws it
                    if tex is not None:
                        th, tw = len(tex), len(tex[0])
                        c = tex[min(th - 1, int((uy + 0.5) * th))][min(tw - 1, int((ux + 0.5) * tw))]
                    if c is None and fixed:
                        if pad:                              # left as the library leaves it
                            zbuf[i] = z
                            row[x] = fp.HAZE
                            later[0].append((i, later[1]))
                            continue
                        c = fp.View.fixture(cell, ux, uy, phase)
                    if c is None and toxic:
                        c = fp.TOXIC_HI if fp.noise(int(ux * 8) + ix * 8, int(uy * 8) + iy * 8, phase) < 0.07 else fp.TOXIC
                        v = colour(c, int((0.45 + 0.55 * fog) * fade * 256.0))
                    else:
                        if c is None:
                            c = fp.FLOOR_A if (ix + iy) & 1 else fp.FLOOR_B
                            if abs(ux) > 0.46 or abs(uy) > 0.46:
                                c = fp.FLOOR_LINE
                        if fire:
                            c = fp.mix(c, (255, 120, 30), 0.3 + 0.25 * fp.noise(int(ux * 6) + ix * 6, int(uy * 6) + iy * 6, phase))
                        if mark == "warn":                   # fire is coming here: hatched and glowing
                            hatch = int((ux + uy + 1.0) * 6) % 2 == 0
                            c = fp.mix(c, (255, 90, 30) if hatch else (150, 30, 20), 0.55 + 0.2 * (phase % 2))
                            v = colour(c, int((0.6 + 0.4 * fog) * fade * 256.0))
                        elif mark == "burn":
                            k = fp.noise(int(ux * 10) + ix * 10, int(uy * 10) + iy * 10, phase + 5)
                            c = (255, 230, 120) if k < 0.25 else (255, 140, 40) if k < 0.7 else (200, 50, 20)
                            v = colour(c, int(fade * 256.0))
                        else:
                            v = colour(c, q)
                if one:
                    zbuf[i] = z
                    row[x] = v
                if two:
                    zbuf[i + 1] = z
                    row[x + 1] = v

    def holes(self, lv, cam, eye, doors, rows, zbuf):
        """Bullet holes in the walls seen (the level's ``holes``), as the classic view's dents: each where its wall
        shows at its middle - a hole is as high on a wall as a shot flies, so from the floor up."""
        spots = getattr(lv, "holes", None)
        if not spots:
            return
        view = self.view
        PW, PH, half, yh = view.PW, view.PH, view.half, view.yh
        cx, cy, fx, fy, rx, ry = cam
        ex, ey = cx - fx * Z0, cy - fy * Z0
        lx = view.LW * Z0
        for x, y, n, along, down in spots:
            dx, dy = fp.DIRS[n]
            ax, ay = fp.DIRS[(n + 1) % 4]
            wx, wy = x + 0.5 * dx + along * ax, y + 0.5 * dy + along * ay     # the hole, on the face turned to DIRS[n]
            if (ex - wx) * dx + (ey - wy) * dy <= 0:                      # the face is turned away from the camera
                continue
            c = lv.cell(x, y)
            if c is None or (c.kind == "door" and doors.get((x, y), c.open) > 0.0):
                continue
            h, top = heights(lv.cell(x + dx, y + dy))
            wh = min(top - 0.02, h + 1.0 - down)
            ddx, ddy = wx - cx, wy - cy
            z = ddx * fx + ddy * fy
            d = z + Z0
            if d <= NEAR:
                continue
            t = Z0 / d
            px_ = half + (ddx * rx + ddy * ry) * view.LW * t
            py_ = yh + (eye - wh) * view.TALL * t
            xi, yi = int(px_), int(py_)
            if not (0 <= xi < PW and 0 <= yi < PH):
                continue
            sa = (xi + 0.5 - half) / lx                           # where that pixel's ray meets the face
            if dx:
                ray = fx + sa * rx
                dp = (wx - ex) / ray if ray else -1.0
            else:
                ray = fy + sa * ry
                dp = (wy - ey) / ray if ray else -1.0
            zp = dp - Z0
            if dp <= NEAR or abs(zbuf[yi * PW + xi] - zp) > 0.02 + 0.002 * zp:
                continue                                          # something nearer hides it, or no wall is there
            fog, fade = fog_of(z)
            view.dents(rows, [(px_, py_, max(1, int(round(view.TALL * t * 0.05))))], fog * fade, 0, PW)

    def cover(self, zbuf, walls):
        """The nearest wall over each character cell (View.cover's rule)."""
        view = self.view
        PW, sx, sy = view.PW, view.sx, view.sy
        out = {}
        for r in range(view.VR):
            for col in range(view.W):
                best = NONE
                for y in range(r * sy, r * sy + sy):
                    base = y * PW
                    for x in range(col * sx, col * sx + sx):
                        i = base + x
                        if walls[i] and zbuf[i] < best:
                            best = zbuf[i]
                if best < NONE:
                    out[(r, col)] = best
        return out

    def label_at(self, face, cam, eye, zbuf):
        """Where a wall's label goes, as View.front_face gives it: (middle x, top y, bottom y, size, z), or None
        when the face is further than 3.2 cells, opened, or hidden at its middle."""
        view = self.view
        cx, cy, fx, fy, rx, ry = cam
        if face.opened:
            return None
        mx = face.at if face.kind == XWALL else (face.lo + face.hi) / 2
        my = (face.lo + face.hi) / 2 if face.kind == XWALL else face.at
        dx, dy = mx - cx, my - cy
        z = dx * fx + dy * fy
        a = dx * rx + dy * ry
        if z <= 0.0 or z + 0.5 > 3.2:
            return None
        t = Z0 / (z + Z0)
        x = view.half + a * view.LW * t
        y0 = view.yh + (view.FS - face.h1 * view.TALL) * t
        y1 = view.yh + (view.FS - face.h0 * view.TALL) * t
        xi, yi = int(x), int((y0 + y1) / 2)
        if not (0 <= xi < view.PW and 0 <= yi < view.PH) or zbuf[yi * view.PW + xi] < z - 0.05:
            return None
        return (x, y0, y1, t, z + 0.5)
