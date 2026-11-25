# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Vector displays: things in three dimensions drawn in lines, as the terminals of old films drew them.

A :class:`Wire` is points, the lines between them and - so that what is behind can be hidden - faces.
A :class:`Camera` looks at them; a :class:`Scope` is the display they are drawn on: braille dots (two
across and four down in a character, so 80 x 24 characters are 160 x 96 dots), or strokes (``- | / \\``
and their box-drawing kin) for a terminal without braille. The same scene is drawn as a **wire** frame
(every line) or **solid** (hidden lines removed: faces are filled into a depth buffer first and a line
is drawn only where nothing is in front of it)::

    ship = box((1, 3, 0.6)) + tube(0.4, 1.0).placed(at=(0, -2, 0))
    cam = Camera(eye=(4, -6, 3), look=(0, 0, 0))
    scope = Scope(80, 24, colour="green", afterglow=0.5)
    scope.clear()
    scope.render(cam, [ship.placed(yaw=30)], solid=True)
    scope.text(1, 0, "HULL 100%")
    rows = scope.rows()                      # rows of (character, colour, background) for Screen.frame

Space is CLIo's model space: x to the right, y forward, z up. Brightness is a number a dot (1 is full;
lines that cross add up towards white), dimmed by distance when the scope has a ``cue``; with
``afterglow`` what was drawn fades over the next frames instead of going out at once.

Nothing here is random and nothing reads the clock: the same scene gives the same picture.

    python -m engine.vector            # a reel: a hauler, an approach, an orbit, a surface scan, signals, rocks
    python -m engine.vector scan 3.5   # one picture of a scene at a time, as text (strokes when piped)
"""
from __future__ import annotations

import math

COLOURS = {"green": (70, 255, 140), "amber": (255, 176, 40), "cyan": (90, 230, 255), "white": (236, 240, 232),
           "red": (255, 84, 64), "blue": (110, 150, 255), "violet": (190, 130, 255)}
OFFSET = 0.004                                           # faces stand this much (of their depth) behind their lines
BITS = ((1, 8), (2, 16), (4, 32), (64, 128))             # braille: the dot at (row, column) of a character
STROKES = "─╲│╱"                                         # by the way a line runs: flat, down to the right, up, up to the right
PLAIN = "-\\|/"


def colour_of(c, default=(70, 255, 140)):
    if c is None:
        return default
    if isinstance(c, str):
        if c in COLOURS:
            return COLOURS[c]
        c = c.lstrip("#")
        try:
            return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
        except (ValueError, IndexError):
            return default
    return tuple(int(x) for x in c[:3])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


def turned(p, yaw=0.0, pitch=0.0, roll=0.0):
    """A point turned: rolled about y (the way a thing faces), pitched about x (nose up), then yawed
    about z (to the left). Degrees."""
    x, y, z = p
    if roll:
        a = math.radians(roll)
        c, s = math.cos(a), math.sin(a)
        x, z = x * c + z * s, -x * s + z * c
    if pitch:
        a = math.radians(pitch)
        c, s = math.cos(a), math.sin(a)
        y, z = y * c - z * s, y * s + z * c
    if yaw:
        a = math.radians(yaw)
        c, s = math.cos(a), math.sin(a)
        x, y = x * c - y * s, x * s + y * c
    return (x, y, z)


# --------------------------------------------------------------------------- #
# Things made of lines
# --------------------------------------------------------------------------- #
class Wire:
    """Points, lines (pairs of points) and faces (points in order, counter-clockwise seen from outside
    when ``wound``). ``colour`` and ``bright`` are how a scope draws it unless told otherwise."""

    def __init__(self, verts=(), edges=(), faces=(), colour=None, bright=1.0, wound=True):
        self.verts = [(float(v[0]), float(v[1]), float(v[2])) for v in verts]
        self.edges = [(int(a), int(b)) for a, b in edges]
        self.faces = [tuple(int(i) for i in f) for f in faces]
        self.colour, self.bright, self.wound = colour, bright, wound
        self._sides = None

    def sides(self):
        """For each line, the faces it is an edge of."""
        if self._sides is None:
            by = {}
            for fi, f in enumerate(self.faces):
                for i in range(len(f)):
                    a, b = f[i], f[(i + 1) % len(f)]
                    by.setdefault((a, b) if a < b else (b, a), []).append(fi)
            self._sides = [by.get((a, b) if a < b else (b, a), ()) for a, b in self.edges]
        return self._sides

    def placed(self, at=(0.0, 0.0, 0.0), yaw=0.0, pitch=0.0, roll=0.0, scale=1.0):
        """The same thing made bigger, turned (see :func:`turned`) and moved - in that order."""
        sx, sy, sz = (scale, scale, scale) if isinstance(scale, (int, float)) else scale
        out = Wire((), self.edges, (), self.colour, self.bright, self.wound)
        out.faces, out._sides = self.faces, self.sides()
        verts = []
        for x, y, z in self.verts:
            x, y, z = turned((x * sx, y * sy, z * sz), yaw, pitch, roll)
            verts.append((x + at[0], y + at[1], z + at[2]))
        out.verts = verts
        return out

    def lit(self, colour=None, bright=None):
        out = Wire((), self.edges, (), self.colour if colour is None else colour,
                   self.bright if bright is None else bright, self.wound)
        out.verts, out.faces, out._sides = self.verts, self.faces, self._sides
        return out

    def __add__(self, other):
        n = len(self.verts)
        return Wire(self.verts + other.verts, self.edges + [(a + n, b + n) for a, b in other.edges],
                    self.faces + [tuple(i + n for i in f) for f in other.faces],
                    self.colour if self.colour is not None else other.colour, self.bright,
                    self.wound and other.wound)


def polyline(points, closed=False, colour=None):
    n = len(points)
    return Wire(points, [(i, (i + 1) % n) for i in range(n if closed else n - 1)], (), colour)


def box(size=(1.0, 1.0, 1.0), colour=None):
    """A box about the origin, ``size`` across (x), along (y) and high (z)."""
    hx, hy, hz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
    v = [(x, y, z) for z in (-hz, hz) for y in (-hy, hy) for x in (-hx, hx)]
    f = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    e = [(0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    return Wire(v, e, f, colour)


def grid(nx=8, ny=8, step=1.0, colour=None):
    """Lines on the ground (z = 0), ``nx`` by ``ny`` squares of ``step``, about the origin. No faces."""
    w, d = nx * step / 2.0, ny * step / 2.0
    v, e = [], []
    for i in range(nx + 1):
        v += [(-w + i * step, -d, 0.0), (-w + i * step, d, 0.0)]
        e.append((len(v) - 2, len(v) - 1))
    for j in range(ny + 1):
        v += [(-w, -d + j * step, 0.0), (w, -d + j * step, 0.0)]
        e.append((len(v) - 2, len(v) - 1))
    return Wire(v, e, (), colour)


def ring(r=1.0, n=24, axis="z", colour=None):
    """A circle about the origin, round ``axis``."""
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        c, s = r * math.cos(a), r * math.sin(a)
        pts.append({"z": (c, s, 0.0), "y": (c, 0.0, s), "x": (0.0, c, s)}[axis])
    return polyline(pts, True, colour)


def frame(w=2.0, h=1.0, colour=None):
    """An upright rectangle facing along y: a gate of a corridor."""
    return polyline([(-w / 2, 0.0, -h / 2), (w / 2, 0.0, -h / 2), (w / 2, 0.0, h / 2), (-w / 2, 0.0, h / 2)], True, colour)


def tube(r=0.5, length=1.0, n=10, taper=1.0, colour=None):
    """A cylinder along y, about the origin; ``taper`` is the far end's radius as a part of the near
    one's (0: a cone)."""
    v, e, f = [], [], []
    for k, (y, rr) in enumerate(((-length / 2.0, r), (length / 2.0, r * taper))):
        for i in range(n):
            a = 2 * math.pi * i / n
            v.append((rr * math.cos(a), y, rr * math.sin(a)))
    for i in range(n):
        j = (i + 1) % n
        e += [(i, j), (n + i, n + j), (i, n + i)]
        f.append((i, n + i, n + j, j))
    f += [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    return Wire(v, e, f, colour)


def globe(r=1.0, lats=5, lons=12, colour=None):
    """A sphere of circles of latitude (``lats`` between the poles) and half-circles of longitude."""
    v = [(0.0, 0.0, r)]
    for i in range(1, lats + 1):
        phi = math.pi * i / (lats + 1)
        for j in range(lons):
            a = 2 * math.pi * j / lons
            v.append((r * math.sin(phi) * math.cos(a), r * math.sin(phi) * math.sin(a), r * math.cos(phi)))
    v.append((0.0, 0.0, -r))
    south = len(v) - 1
    e, f = [], []

    def at(i, j):
        return 1 + (i - 1) * lons + j % lons
    for j in range(lons):
        e.append((0, at(1, j)))
        f.append((0, at(1, j), at(1, j + 1)))
        e.append((at(lats, j), south))
        f.append((south, at(lats, j + 1), at(lats, j)))
        for i in range(1, lats + 1):
            e.append((at(i, j), at(i, j + 1)))
            if i < lats:
                e.append((at(i, j), at(i + 1, j)))
                f.append((at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)))
    return Wire(v, e, f, colour)


def terrain(heights, step=1.0, colour=None, lines="both"):
    """Ground from rows of heights (``heights[row][column]``, rows going forward), about the origin.
    ``step``: the distance between heights (one number, or across and forward). ``lines``: along the
    ``rows`` (profiles, one behind another), the ``columns``, or ``both`` (a net)."""
    ny, nx = len(heights), len(heights[0])
    sx, sy = (step, step) if isinstance(step, (int, float)) else step
    x0, y0 = -(nx - 1) * sx / 2.0, -(ny - 1) * sy / 2.0
    v = [(x0 + i * sx, y0 + j * sy, float(heights[j][i])) for j in range(ny) for i in range(nx)]
    e, f = [], []
    for j in range(ny):
        for i in range(nx):
            k = j * nx + i
            if i + 1 < nx and lines != "columns":
                e.append((k, k + 1))
            if j + 1 < ny and lines != "rows":
                e.append((k, k + nx))
            if i + 1 < nx and j + 1 < ny:
                f.append((k, k + 1, k + nx + 1, k + nx))
    return Wire(v, e, f, colour, wound=False)


def orbit(a=1.0, e=0.0, n=48, colour=None):
    """An ellipse in the ground plane with a focus at the origin: half the long axis ``a``, eccentricity
    ``e``; its nearest point is on -x."""
    b = a * math.sqrt(max(0.0, 1.0 - e * e))
    return polyline([(a * e + a * math.cos(2 * math.pi * i / n), b * math.sin(2 * math.pi * i / n), 0.0)
                     for i in range(n)], True, colour)


def on_orbit(a, e, turn):
    """The point of :func:`orbit` a part of the way round (0: farthest, 0.5: nearest)."""
    b = a * math.sqrt(max(0.0, 1.0 - e * e))
    t = 2 * math.pi * turn
    return (a * e + a * math.cos(t), b * math.sin(t), 0.0)


def from_triangles(verts, tris, crease=25.0, colour=None, wound=False, apart=None, origin=None):
    """A mesh of triangles as lines: only the edges where the surface folds by more than ``crease``
    degrees (0: every edge), and the edges of holes - so a flat side is one outline, not a net of
    triangles. Corners in one place are one corner - unless ``apart`` (a mark for each of ``verts``)
    says they are of different things, which may then move apart. ``origin``: a list that is filled
    with, for each corner of the lines, which of ``verts`` it was."""
    key, verts2, index = {}, [], []
    for n, p in enumerate(verts):
        k = (round(p[0], 4), round(p[1], 4), round(p[2], 4), apart[n] if apart is not None else None)
        if k not in key:
            key[k] = len(verts2)
            verts2.append((float(p[0]), float(p[1]), float(p[2])))
            if origin is not None:
                origin.append(n)
        index.append(key[k])
    faces, normals, by = [], [], {}
    for t in tris:
        a, b, c = index[t[0]], index[t[1]], index[t[2]]
        if a == b or b == c or a == c:
            continue
        n = _unit(_cross(_sub(verts2[b], verts2[a]), _sub(verts2[c], verts2[a])))
        fi = len(faces)
        faces.append((a, b, c))
        normals.append(n)
        for p, q in ((a, b), (b, c), (c, a)):
            by.setdefault((p, q) if p < q else (q, p), []).append(fi)
    limit = math.cos(math.radians(crease))
    edges = []
    for (p, q), fs in sorted(by.items()):
        if len(fs) != 2 or crease <= 0 or abs(_dot(normals[fs[0]], normals[fs[1]])) < limit:
            edges.append((p, q))
    return Wire(verts2, edges, faces, colour, wound=wound)


def from_model(model, clip="idle", t=0.0, crease=25.0, colour=None):
    """One of CLIo's 3D models (engine/model.py) as lines, posed at time ``t``."""
    verts = model.pose(clip, t)
    s = model.scale
    return from_triangles([(x * s, y * s, z * s) for x, y, z in verts], [f[:3] for f in model.faces], crease, colour)


# --------------------------------------------------------------------------- #
# The eye
# --------------------------------------------------------------------------- #
class Camera:
    """An eye at ``eye`` looking at ``look``; ``fov`` is the angle seen from side to side, ``roll``
    tips the horizon (degrees). Nothing nearer than ``near`` is drawn."""

    def __init__(self, eye=(0.0, -5.0, 2.0), look=(0.0, 0.0, 0.0), fov=60.0, roll=0.0, near=0.05):
        self.eye, self.fov, self.near = tuple(float(c) for c in eye), float(fov), float(near)
        ahead = _unit(_sub(look, eye))
        if abs(ahead[2]) > 0.9999:                        # straight up or down: any side will do
            right = (1.0, 0.0, 0.0)
        else:
            right = _unit(_cross(ahead, (0.0, 0.0, 1.0)))
        up = _cross(right, ahead)
        if roll:
            a = math.radians(roll)
            c, s = math.cos(a), math.sin(a)
            right, up = (tuple(right[i] * c + up[i] * s for i in range(3)),
                         tuple(-right[i] * s + up[i] * c for i in range(3)))
        self.right, self.up, self.ahead = right, up, ahead

    def see(self, p):
        """A point as the eye has it: to its right, above it, in front of it."""
        d = (p[0] - self.eye[0], p[1] - self.eye[1], p[2] - self.eye[2])
        return (_dot(d, self.right), _dot(d, self.up), _dot(d, self.ahead))


# --------------------------------------------------------------------------- #
# The display
# --------------------------------------------------------------------------- #
class Scope:
    """A display of ``cols`` by ``rows`` characters. ``colour``: the lines' (a name of COLOURS, #rrggbb
    or a triple); ``afterglow``: the part of a dot's light left in the next frame (0: none); ``cue``:
    ``(near, far)`` distances between which lines dim to ``dim`` of their light; ``glow``: lit
    characters also light their background a little."""

    def __init__(self, cols=80, rows=24, colour="green", afterglow=0.0, cue=None, dim=0.3, glow=True, paper=None):
        self.cols, self.rows_n = int(cols), int(rows)
        self.W, self.H = self.cols * 2, self.rows_n * 4
        self.colour = colour_of(colour)
        self.afterglow, self.cue, self.dim, self.glow, self.paper = float(afterglow), cue, float(dim), glow, paper
        n = self.W * self.H
        self.light = [0.0] * n                           # each dot's light
        self.depth = None                                # 1 / distance of the nearest face at each dot, or None
        cells = self.cols * self.rows_n
        self.best = [0.0] * cells                        # the brightest thing drawn in each character this frame
        self.ink = [self.colour] * cells                 # and its colour
        self.way = [-1] * cells                          # the way lines run through it (-1 none, 4 several)
        self.words = []

    # ---- a frame ----------------------------------------------------- #
    def clear(self):
        """A new frame: what was drawn fades (or goes out), faces are forgotten."""
        k = self.afterglow
        if k > 0:
            self.light = [v * k if v * k > 0.07 else 0.0 for v in self.light]
        else:
            self.light = [0.0] * (self.W * self.H)
        self.depth = None
        cells = self.cols * self.rows_n
        self.best = [0.0] * cells
        self.way = [-1] * cells
        self.words = []

    def project(self, cam, p):
        """Where a point shows: ``(x, y, 1 / distance)`` in dots, or None behind the eye."""
        x, y, z = cam.see(p)
        if z < cam.near:
            return None
        f = (self.W / 2.0) / math.tan(math.radians(cam.fov) / 2.0)
        return (self.W / 2.0 + x / z * f, self.H / 2.0 - y / z * f, 1.0 / z)

    def _ends(self, cam, a, b):
        """A line's two ends on the display (cut where it passes behind the eye), or None."""
        ax, ay, az = cam.see(a)
        bx, by, bz = cam.see(b)
        near = cam.near
        if az < near and bz < near:
            return None
        if az < near:
            k = (near - az) / (bz - az)
            ax, ay, az = ax + (bx - ax) * k, ay + (by - ay) * k, near
        elif bz < near:
            k = (near - bz) / (az - bz)
            bx, by, bz = bx + (ax - bx) * k, by + (ay - by) * k, near
        f = (self.W / 2.0) / math.tan(math.radians(cam.fov) / 2.0)
        cx, cy = self.W / 2.0, self.H / 2.0
        return (cx + ax / az * f, cy - ay / az * f, 1.0 / az, cx + bx / bz * f, cy - by / bz * f, 1.0 / bz)

    # ---- lines ------------------------------------------------------- #
    def dot(self, x, y, bright=1.0, colour=None, way=-1):
        """Light one dot (x across, y down, in dots)."""
        if 0 <= x < self.W and 0 <= y < self.H:
            i = y * self.W + x
            v = self.light[i]
            self.light[i] = bright if v <= 0.0 else min(2.0, max(v, bright) + 0.35 * min(v, bright))
            c = (y >> 2) * self.cols + (x >> 1)
            if bright >= self.best[c]:
                self.best[c] = bright
                self.ink[c] = self.colour if colour is None else colour
            if way >= 0:
                w = self.way[c]
                self.way[c] = way if w < 0 or w == way else 4

    def line2(self, x0, y0, x1, y1, bright=1.0, colour=None, w0=None, w1=None):
        """A line on the display, in dots. With ``w0`` and ``w1`` (1 / distance at its ends) it is hidden
        where a face is in front, and dimmed by distance."""
        W, H = self.W, self.H
        dx, dy = x1 - x0, y1 - y0
        t0, t1 = 0.0, 1.0                                # keep the part of it that is on the display
        for p, q in ((-dx, x0 + 1.0), (dx, W - x0), (-dy, y0 + 1.0), (dy, H - y0)):
            if abs(p) < 1e-12:
                if q < 0:
                    return
            else:
                r = q / p
                if p < 0:
                    t0 = r if r > t0 else t0
                else:
                    t1 = r if r < t1 else t1
        if t0 > t1:
            return
        if t0 > 0.0 or t1 < 1.0:
            if w0 is not None:
                w0, w1 = w0 + (w1 - w0) * t0, w0 + (w1 - w0) * t1
            x0, y0, x1, y1 = x0 + dx * t0, y0 + dy * t0, x0 + dx * t1, y0 + dy * t1
            dx, dy = x1 - x0, y1 - y0
        n = max(1, int(max(abs(dx), abs(dy)) + 0.5))
        if colour is not None:
            colour = colour_of(colour)
        a = math.degrees(math.atan2(dy, dx)) % 180.0
        way = int((a + 22.5) // 45) % 4
        depth, cue = self.depth, self.cue
        sx, sy = dx / n, dy / n
        sw = (w1 - w0) / n if w0 is not None else 0.0
        last = None
        for i in range(n + 1):
            x, y = int(x0 + sx * i + 0.5), int(y0 + sy * i + 0.5)
            if not (0 <= x < W and 0 <= y < H) or (x, y) == last:      # a dot is lit once by a line
                continue
            last = (x, y)
            b = bright
            if w0 is not None:
                w = w0 + sw * i
                if depth is not None and w < depth[y * W + x] and self._behind(x, y, w):
                    continue
                if cue:
                    d = 1.0 / w
                    k = (d - cue[0]) / (cue[1] - cue[0])
                    b *= 1.0 - (1.0 - self.dim) * (0.0 if k < 0 else 1.0 if k > 1 else k)
            self.dot(x, y, b, colour, way)

    def _behind(self, x, y, w):
        """Is a point of a line behind the faces all round its dot? (A face's edge is not behind its
        own face: the faces stand a little back, and a dot beside the face's rim lets it show.)"""
        W, depth = self.W, self.depth
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < W and 0 <= ny < self.H and w >= depth[ny * W + nx]:
                return False
        return True

    def line(self, cam, a, b, bright=1.0, colour=None):
        """A line between two points in space."""
        ends = self._ends(cam, a, b)
        if ends:
            self.line2(ends[0], ends[1], ends[3], ends[4], bright, colour, ends[2], ends[5])

    def circle2(self, x, y, r, bright=1.0, colour=None, n=None):
        """A circle on the display, in dots (a reticle, a lock)."""
        n = n or max(8, int(r * 2))
        px, py = x + r, y
        for i in range(1, n + 1):
            a = 2 * math.pi * i / n
            qx, qy = x + r * math.cos(a), y + r * math.sin(a)
            self.line2(px, py, qx, qy, bright, colour)
            px, py = qx, qy

    captions = True                                      # False: text() writes nothing (a scope too small for words)

    def text(self, col, row, text, colour=None, bright=1.0):
        """Words over the picture, in characters."""
        if self.captions:
            self.words.append((int(col), int(row), str(text), colour_of(colour, self.colour), bright))

    def label(self, cam, p, text, colour=None, bright=1.0, dx=1, dy=0):
        """Words beside a point in space (nothing when it is behind the eye or off the display)."""
        s = self.project(cam, p)
        if s and 0 <= s[0] < self.W and 0 <= s[1] < self.H:
            self.text(int(s[0]) // 2 + dx, int(s[1]) // 4 + dy, text, colour, bright)

    # ---- faces ------------------------------------------------------- #
    def hide(self, cam, wire):
        """Fill a thing's faces into the depth buffer: lines drawn after this do not show through them."""
        if not wire.faces:
            return
        W, H = self.W, self.H
        if self.depth is None:
            self.depth = [0.0] * (W * H)
        depth = self.depth
        near = cam.near
        f = (W / 2.0) / math.tan(math.radians(cam.fov) / 2.0)
        cx, cy = W / 2.0, H / 2.0
        seen = [cam.see(p) for p in wire.verts]
        back = 1.0 - OFFSET
        for face in wire.faces:
            pts = [seen[i] for i in face]
            if any(p[2] < near for p in pts):            # cut the face where it passes behind the eye
                cut = []
                for i, p in enumerate(pts):
                    q = pts[(i + 1) % len(pts)]
                    if p[2] >= near:
                        cut.append(p)
                    if (p[2] >= near) != (q[2] >= near):
                        k = (near - p[2]) / (q[2] - p[2])
                        cut.append((p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k, near))
                pts = cut
                if len(pts) < 3:
                    continue
            scr = [(cx + p[0] / p[2] * f, cy - p[1] / p[2] * f, back / p[2]) for p in pts]
            for k in range(1, len(scr) - 1):
                self._fill(depth, scr[0], scr[k], scr[k + 1])

    def _fill(self, depth, a, b, c):
        W, H = self.W, self.H
        (x0, y0, w0), (x1, y1, w1), (x2, y2, w2) = sorted((a, b, c), key=lambda p: p[1])
        if y2 - y0 < 1e-9:
            return
        ys, ye = max(0, int(math.ceil(y0 - 0.5))), min(H - 1, int(math.floor(y2 - 0.5)))
        for y in range(ys, ye + 1):
            yc = y + 0.5
            k = (yc - y0) / (y2 - y0)
            xa, wa = x0 + (x2 - x0) * k, w0 + (w2 - w0) * k
            if yc < y1:
                k = (yc - y0) / (y1 - y0) if y1 - y0 > 1e-9 else 0.0
                xb, wb = x0 + (x1 - x0) * k, w0 + (w1 - w0) * k
            else:
                k = (yc - y1) / (y2 - y1) if y2 - y1 > 1e-9 else 0.0
                xb, wb = x1 + (x2 - x1) * k, w1 + (w2 - w1) * k
            if xa > xb:
                xa, xb, wa, wb = xb, xa, wb, wa
            xs, xe = max(0, int(math.ceil(xa - 0.5))), min(W - 1, int(math.floor(xb - 0.5)))
            if xs > xe:
                continue
            dw = (wb - wa) / (xb - xa) if xb - xa > 1e-9 else 0.0
            w = wa + (xs + 0.5 - xa) * dw
            row = y * W
            for x in range(xs, xe + 1):
                if w > depth[row + x]:
                    depth[row + x] = w
                w += dw

    # ---- things ------------------------------------------------------ #
    def draw(self, cam, wire, colour=None, bright=None, solid=False):
        """A thing's lines. ``solid``: of a thing whose faces are wound, only the lines of faces that
        look this way (with :meth:`hide` first, the rest is hidden too)."""
        colour = colour_of(colour if colour is not None else wire.colour, self.colour)
        bright = wire.bright if bright is None else bright
        verts = wire.verts
        skip = None
        if solid and wire.wound and wire.faces:
            eye = cam.eye
            front = []
            for f in wire.faces:
                a, b, c = verts[f[0]], verts[f[1]], verts[f[2]]
                front.append(_dot(_cross(_sub(b, a), _sub(c, a)), _sub(eye, a)) > 0)
            skip = [bool(s) and not any(front[i] for i in s) for s in wire.sides()]
        for i, (a, b) in enumerate(wire.edges):
            if skip is not None and skip[i]:
                continue
            ends = self._ends(cam, verts[a], verts[b])
            if ends:
                self.line2(ends[0], ends[1], ends[3], ends[4], bright, colour, ends[2], ends[5])

    def render(self, cam, things, solid=False):
        """Draw things together: as wire frames, or solid - every thing's faces first, then every
        thing's lines, so one hides another."""
        if solid:
            for t in things:
                self.hide(cam, t)
        for t in things:
            self.draw(cam, t, solid=solid)

    # ---- the picture ------------------------------------------------- #
    def tone(self, colour, bright):
        """A colour at a brightness: dim to full, and towards white where lines cross."""
        k = 0.2 + 0.8 * min(1.0, bright)
        hot = max(0.0, min(1.0, bright - 1.0)) * 0.7
        return tuple(int(min(255, c * k + (255 - c * k) * hot)) for c in colour)

    def rows(self, style="dots", unicode=True):
        """The picture as rows of ``(character, colour, background)``: ``dots`` (braille) or ``strokes``
        (lines by the way they run; ``unicode`` false: in ASCII)."""
        W, cols = self.W, self.cols
        light, best, ink, way = self.light, self.best, self.ink, self.way
        marks = (STROKES if unicode else PLAIN) + ("┼" if unicode else "+")
        out = []
        for r in range(self.rows_n):
            row = []
            for c in range(cols):
                x0, y0 = c * 2, r * 4
                i = y0 * W + x0
                vals = (light[i], light[i + 1], light[i + W], light[i + W + 1],
                        light[i + 2 * W], light[i + 2 * W + 1], light[i + 3 * W], light[i + 3 * W + 1])
                most = max(vals)
                bits = 0
                if most > 0.0:
                    floor = most * 0.55                   # beside a fresh line its afterglow does not show
                    for k in range(8):
                        if vals[k] >= floor:
                            bits |= BITS[k >> 1][k & 1]
                if not bits:
                    row.append((" ", None, self.paper))
                    continue
                ci = r * cols + c
                fg = self.tone(ink[ci], most)
                bg = self.paper
                if self.glow and most > 0.5:
                    g = 0.05 + 0.05 * min(1.0, most - 0.5)
                    bg = tuple(int(v * g) for v in ink[ci]) if bg is None else \
                        tuple(int(min(255, p + v * g)) for p, v in zip(bg, ink[ci]))
                if style == "dots":
                    ch = chr(0x2800 + bits)
                else:
                    w = way[ci]
                    ch = marks[w] if w >= 0 else ("·" if unicode else ".")
                row.append((ch, fg, bg))
            out.append(row)
        for col, r, text, colour, bright in self.words:
            if 0 <= r < self.rows_n:
                fg = self.tone(colour, bright)
                for i, ch in enumerate(text):
                    if 0 <= col + i < cols:
                        out[r][col + i] = (ch, fg, self.paper)
        return out

    def plain(self, style="strokes", unicode=False):
        """The picture as text without colour (strokes in ASCII unless said otherwise)."""
        return "\n".join("".join(ch for ch, _, _ in row).rstrip() for row in self.rows(style, unicode))


# --------------------------------------------------------------------------- #
# A reel: what the module can draw, for looking at and for the tests
# --------------------------------------------------------------------------- #
def hauler():
    """A cargo hauler: a spine, six pods, a bridge, a dish, three engine bells. Faces forward (+y)."""
    ship = box((0.5, 5.0, 0.5))
    for y in (-0.9, 0.5, 1.9):
        for x in (-0.85, 0.85):
            ship += box((1.1, 1.2, 0.9)).placed(at=(x, y - 0.6, 0.0))
    ship += box((1.2, 0.9, 0.7)).placed(at=(0.0, 2.9, 0.25))
    ship += tube(0.16, 0.9, 6).placed(at=(0.0, 3.6, 0.25))
    ship += box((2.6, 0.5, 0.25)).placed(at=(0.0, -2.2, 0.0))
    for x in (-0.9, 0.0, 0.9):
        ship += tube(0.42, 0.9, 8, taper=0.55).placed(at=(x, -2.85, 0.0), yaw=180)
    ship += ring(0.5, 10, "x").placed(at=(0.0, 2.9, 0.95), pitch=20)
    return ship


HILLS = ((2.5, 6.0, 1.5, 5.0), (-4.5, 14.0, 1.1, 7.0), (6.0, 18.0, 0.9, 3.0), (-1.0, 2.0, -0.7, 2.5), (0.5, 21.5, 1.0, 4.0),
         (-8.0, 8.0, 0.8, 5.0))


def _height(x, y):
    """Ground for the scan: a plain with a few hills and a crater, the same whoever asks; it comes
    round again every 24 forward."""
    h = 0.10 * math.sin(x * 0.9) * math.cos(y * math.pi / 6.0)
    for hx, hy, high, wide in HILLS:
        dy = (y - hy + 12.0) % 24.0 - 12.0
        h += high * math.exp(-((x - hx) ** 2 + dy * dy) / wide)
    return h


SCENES = ("hauler", "approach", "orbit", "scan", "signals", "asteroids")
GLOW = {"hauler": 0.25, "approach": 0.45, "orbit": 0.3, "scan": 0.0, "signals": 0.4, "asteroids": 0.2}     # the afterglow that suits each
TRACK = {"mood": "tense", "seed": 7, "bars": 8}          # the reel's music, and what "signals" moves to
_sheet = []


def reel_sheet():
    """The cue sheet of the reel's own track (engine/cues.py), made once."""
    if not _sheet:
        from . import cues
        from .audio.compose import compose
        _sheet.append(cues.from_song(compose(TRACK["seed"], TRACK["mood"], TRACK["bars"])))
    return _sheet[0]


def scene(name, t, scope, sheet=None):
    """Draw a scene of the reel at time ``t`` (seconds) on a scope. Returns a caption. ``sheet``: the
    cue sheet "signals" moves to (the reel's own track's unless given)."""
    cols, rows = scope.cols, scope.rows_n
    if name == "asteroids":                              # a flight through rocks (engine/ahead.py)
        from . import ahead
        # with a cue sheet (the reel's own track, a game's music) the rocks flare with its low hits
        return ahead.field(scope, t, beat=sheet.level("hit.low", t) if sheet is not None else 0.0)
    if name == "signals":
        sheet = sheet or reel_sheet()
        scope.cue = None
        punch, shock, sparks = sheet.level("punch", t), sheet.level("shockwave", t), sheet.level("sparks", t)
        hue = ("green", "amber", "cyan", "violet")[int(sheet.turns("palette", t)) % 4]
        cx, cy = scope.W // 2, scope.H // 2 - 6
        unit = scope.H / 96.0
        scope.circle2(cx, cy, (11 + 8 * punch) * unit, 0.55 + 0.9 * punch, hue)            # the low hits: a ring that jumps
        if shock > 0.02:                                                                 # the middle: a ring going out
            scope.circle2(cx, cy, (22 + 24 * (1 - shock)) * unit, shock, "white")
        for i in range(16):                                                              # the high: sparks round it
            a = 2 * math.pi * i / 16 + 0.2
            r0, r1 = 30 * unit, (31 + 12 * sparks) * unit
            scope.line2(cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                        0.35 + 0.9 * sparks, hue)
        base, back = scope.H - 5, 0.02                                                   # the last seconds, as traces
        for action, lift, colour in (("punch", 0, hue), ("sparks", 9, "white")):
            px = py = None
            for x in range(0, scope.W, 2):
                y = base - lift * unit - 7 * unit * sheet.level(action, t - (scope.W - x) * back)
                if px is not None:
                    scope.line2(px, py, x, y, 0.75, colour)
                px, py = x, y
        for x in range(0, scope.W, 2):
            if sheet.level("bar", t - (scope.W - x) * back) > 0.9:
                scope.line2(x, base + 1, x, base + 4, 0.6, hue)
        scope.text(1, 0, "SIGNALS  %s" % (sheet.doc.get("source") or {}).get("name", "").upper()[:40], hue)
        scope.text(1, 1, "LOW %3d  MID %3d  HIGH %3d" % (punch * 100, shock * 100, sparks * 100), hue, 0.6)
        scope.text(cols - 12, 0, "T %7.2f" % sheet.when(t), hue, 0.7)
        return "Signals: the screen moves with the sound, from a cue sheet - nothing is listened to while it plays"
    if name == "hauler":
        solid = int(t / 6.0) % 2 == 1
        cam = Camera(eye=(6.5, -7.5, 3.2), look=(0, 0.3, 0), fov=44)
        ship = hauler().placed(yaw=t * 24.0, roll=8 * math.sin(t * 0.7))
        scope.cue = (7.0, 13.0)
        scope.render(cam, [ship], solid=solid)
        scope.text(1, 0, "CH EREBUS  HULL SURVEY", bright=1.0)
        scope.text(1, 1, "MODE %s" % ("SOLID  hidden lines off" if solid else "WIRE   all lines"), bright=0.6)
        scope.text(1, rows - 1, "YAW %05.1f  ROLL %+05.1f" % ((t * 24.0) % 360, 8 * math.sin(t * 0.7)), bright=0.6)
        return "A hauler in lines: every line, then only the lines in sight"
    if name == "approach":
        z = (t * 3.0) % 4.0
        sway = 0.6 * math.sin(t * 0.8)
        cam = Camera(eye=(sway, -z, 0.25 * math.sin(t * 1.1)), look=(0.3 * math.sin(t * 0.5), 20, 0), fov=70,
                     roll=6 * math.sin(t * 0.6))
        scope.cue = (2.0, 34.0)
        for i in range(8):
            y = i * 5.0
            k = 1.0 + 0.04 * i
            gate = frame(4.6 * k, 2.6 * k).placed(at=(0.9 * math.sin(y * 0.11), y, 0.4 * math.sin(y * 0.07)))
            scope.draw(cam, gate, colour="amber" if i == 3 else None, bright=1.0 if i == 3 else 0.8)
        for x in (-1.0, 1.0):
            scope.line(cam, (x * 2.3, -2, -1.3), (x * 2.3 + 0.9 * math.sin(4.4), 40, -1.3), bright=0.5)
        pad = grid(4, 4, 1.5).placed(at=(0.9 * math.sin(4.0), 38.0, -1.6))
        scope.draw(cam, pad, colour="cyan")
        cx, cy = scope.W // 2, scope.H // 2
        scope.circle2(cx, cy, 9, 0.7, "amber")
        scope.line2(cx - 16, cy, cx - 11, cy, 0.7, "amber")
        scope.line2(cx + 11, cy, cx + 16, cy, 0.7, "amber")
        scope.text(1, 0, "APPROACH  CORRIDOR 7", bright=1.0)
        scope.text(cols - 22, 0, "RANGE %5.1f KM" % (38.0 - z), bright=0.7)
        scope.text(1, rows - 1, "DRIFT %+0.2f  ROLL %+04.1f" % (sway, 6 * math.sin(t * 0.6)), bright=0.6)
        scope.text(cols - 16, rows - 1, "GATE 3 LOCKED", "amber", 0.9)
        return "A way in: gates, a pad, a reticle - lines in space and lines on the glass"
    if name == "orbit":
        cam = Camera(eye=(9.0 * math.cos(t * 0.15), -9.0 * math.sin(t * 0.15) - 6.0, 5.0), look=(0, 0, 0), fov=50)
        scope.cue = (6.0, 20.0)
        moon = globe(1.6, 5, 12).placed(yaw=t * 9.0, pitch=12)
        giant = globe(4.2, 7, 16).placed(at=(-9.5, 9.0, -1.0), yaw=t * 3.0, pitch=8).lit("amber", 0.55)
        way = orbit(4.2, 0.25, 64).lit("cyan", 0.7)
        p = on_orbit(4.2, 0.25, (t * 0.06) % 1.0)
        ship = box((0.25, 0.5, 0.2)).placed(at=p, yaw=t * 40).lit("white")
        scope.render(cam, [giant, moon, way, ship], solid=True)
        scope.label(cam, p, "EREBUS", "white")
        scope.label(cam, (0, 0, 1.9), "GORDIAN MOON", dy=-1)
        scope.label(cam, on_orbit(4.2, 0.25, 0.5), "PERIAPSIS", "cyan", 0.7)
        scope.text(1, 0, "ORBIT INSERTION  ER / GORD", bright=1.0)
        scope.text(1, rows - 1, "E 0.25  PERIOD 3.55 D", bright=0.6)
        return "An orbit: globes that hide what is behind them, a path, names that follow points"
    # scan
    nx, ny, sx, sy = 44, 22, 0.32, 0.62
    off = t * 1.2
    hs = [[_height((i - nx / 2) * sx * 1.6, j * sy * 1.3 + off) for i in range(nx)] for j in range(ny)]
    ground = terrain(hs, (sx, sy), lines="rows")
    cam = Camera(eye=(0.0, -17.5, 8.0), look=(0, 0.4, -0.9), fov=40)
    scope.cue = (13.0, 28.0)
    scope.render(cam, [ground], solid=True)
    row = int(t * 6) % ny                                 # the sweep: one profile of the ground, bright
    y = -(ny - 1) * sy / 2.0 + row * sy
    for i in range(nx - 1):
        a = (-(nx - 1) * sx / 2.0 + i * sx, y, hs[row][i] + 0.03)
        b = (-(nx - 1) * sx / 2.0 + (i + 1) * sx, y, hs[row][i + 1] + 0.03)
        scope.line(cam, a, b, 1.6, "white")
    scope.text(1, 0, "SURFACE SCAN  GORDIAN MOON  WHORL IV", bright=1.0)
    scope.text(1, rows - 1, "PROFILE %02d/%02d  RELIEF %+0.2f KM" % (row + 1, ny, max(hs[row])), bright=0.6)
    return "A surface scan: profiles of the ground, each hiding what lies behind it, and a sweep"


def reel(term=None, seconds=8.0, style=None, colours=("green", "amber", "cyan", "green", "green", "cyan"), sound=True):
    """Play the scenes in turn on a terminal, in frame mode (Ctrl-C ends), with their track when
    this machine can play one: "signals" then moves by the sound's own clock."""
    from .frame import Screen
    from .term import Term
    term = term or Term()
    audio = None
    if sound:
        try:
            from .audio import Audio
            audio = Audio()
            audio.music({"generate": dict(TRACK)})
        except Exception:
            audio = None
    screen = Screen(term)
    style = style or ("dots" if term.unicode and not getattr(term, "subst", None) else "strokes")
    screen.start()
    try:
        for name, colour in zip(SCENES, colours):
            W, H = screen.size()
            scope = Scope(W, max(6, H - 2), colour=colour, afterglow=GLOW[name])
            caption = [""]

            def draw(t, scope=scope, name=name, caption=caption):
                scope.clear()
                if name == "signals" and audio is not None and audio.clock() is not None:
                    t = audio.clock()                    # the sound's own time, not the picture's
                caption[0] = scene(name, t, scope, reel_sheet() if name == "asteroids" else None)
                screen.frame(scope.rows(style, term.unicode), status=" " + caption[0])
            screen.play([i / 15.0 for i in range(int(seconds * 15))], draw, 1 / 15.0)
            if screen.skip:
                break
    finally:
        screen.stop()
        if audio is not None:
            audio.shutdown()


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in SCENES:
        scope = Scope(78, 22)
        scene(argv[0], float(argv[1]) if len(argv) > 1 else 0.0, scope)
        unicode = (sys.stdout.encoding or "").lower().startswith("utf")
        print(scope.plain("dots" if "--dots" in argv and unicode else "strokes", unicode and "--ascii" not in argv))
        return 0
    if not sys.stdout.isatty():
        print(__doc__.strip().splitlines()[-2].strip())
        print(__doc__.strip().splitlines()[-1].strip())
        return 2
    reel(style="strokes" if "--strokes" in argv else None)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
