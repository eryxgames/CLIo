# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Views: one thing seen several ways - a ship as it looks, as lines, cut open, deck by deck, by
its heat; a world lit by its sun, by its heat, as a grid.

A **model** (engine/model.py) has these views:

* ``shaded`` - as a level draws it: its materials under a light, in half-block pixels;
* ``wire`` - every line; ``solid`` - the lines in front only (engine/vector.py);
* ``structure`` - what is inside: every line, each group of parts in a colour of its own, the hull
  faint; with a ``cut`` the near part is taken away along an axis;
* ``plan`` - from straight above, as a map: with ``levels`` it is cut into that many floors or decks
  and one ``level`` is shown;
* ``heat`` - each group in the colour of a value from 0 to 1 (cold, dark; hot, white); the hull (the
  first group) is seen through when there are others, so what is hot inside shows.

A **planet** (a game's ``planets.json``) is a ball with a ``field`` - rows of characters from pole to
pole, each a kind of ground from the ``legend`` - a ``tilt``, a sun, and ``sites``. Its views:
``surface`` (lit by its sun, the night side dark), ``heat`` (each kind of ground by its ``heat``) and
``grid`` (circles of latitude and longitude, in lines).

:func:`draw` and :func:`draw_planet` give rows of cells for a frame (engine/frame.py); a panel's
scope takes a ``view`` (engine/panels.py). To look at things::

    python clio.py GAME --view-model [NAME]     # the game's models (and planets), turned with the arrows
    python -m engine.viewer FILE.glb            # a glTF file, as CLIo would have it
    python -m engine.viewer GAME NAME --print heat
"""
from __future__ import annotations

import math

from . import vector
from .model import pbr

VIEWS = ("shaded", "wire", "solid", "structure", "plan", "heat")
PLANET_VIEWS = ("surface", "heat", "grid")
PAPER = (6, 8, 10)
TONES = ("cyan", "amber", "violet", "red", "white", "blue", "green")      # a colour a group, in the structure view
THERMAL = ((0.0, (8, 8, 40)), (0.2, (40, 20, 130)), (0.4, (150, 30, 140)), (0.6, (230, 60, 50)), (0.8, (255, 170, 40)),
           (1.0, (255, 250, 220)))


def thermal(k):
    """The colour of a heat from 0 (cold) to 1 (hot)."""
    k = max(0.0, min(1.0, float(k)))
    for (a, ca), (b, cb) in zip(THERMAL, THERMAL[1:]):
        if k <= b:
            u = (k - a) / (b - a)
            return (int(ca[0] + (cb[0] - ca[0]) * u), int(ca[1] + (cb[1] - ca[1]) * u), int(ca[2] + (cb[2] - ca[2]) * u))
    return THERMAL[-1][1]


def cut(wire, axis, at, keep=-1):
    """The part of a wire on one side of a plane across ``axis`` (0 x, 1 y, 2 z) at ``at``: under it
    (``keep`` -1) or over it (1). Its lines are cut off there."""
    verts, edges = list(wire.verts), []
    for a, b in wire.edges:
        pa, pb = wire.verts[a], wire.verts[b]
        ia, ib = (pa[axis] - at) * keep >= 0, (pb[axis] - at) * keep >= 0
        if ia and ib:
            edges.append((a, b))
        elif ia or ib:
            near, far = (pa, pb) if ia else (pb, pa)
            k = (at - near[axis]) / ((far[axis] - near[axis]) or 1.0)
            verts.append(tuple(near[i] + (far[i] - near[i]) * k for i in range(3)))
            edges.append((a if ia else b, len(verts) - 1))
    return vector.Wire(verts, edges, (), wire.colour)


LOOK_KEYS = ("view", "ink", "palette", "shades", "dither", "light", "groups")


def looks(data):
    """How each of a game's models is to be drawn: the game's own ``"model_look"`` (``game.json``), with
    what a model's ``"look"`` says over it. ``{name: look}``; a look's ``palette`` is made colours here."""
    cfg = getattr(data, "config", None) or {}
    base = cfg.get("model_look") if isinstance(cfg.get("model_look"), dict) else {}
    out = {}
    for name, spec in (getattr(data, "models", None) or {}).items():
        own = spec.get("look") if isinstance(spec, dict) and isinstance(spec.get("look"), dict) else {}
        look = dict(base, **own)
        if isinstance(base.get("groups"), dict) and isinstance(own.get("groups"), dict):
            look["groups"] = dict(base["groups"], **own["groups"])
        if look.get("palette") is not None:
            look["colours"] = palette(look["palette"], cfg.get("palettes"))
        out[name] = look
    return out


def palette(value, own=None):
    """A look's palette as colours: a name of the game's own ``palettes`` or of the banner's, or a list
    of ``#rrggbb``. None when it is none of them."""
    from . import banner
    if isinstance(value, str):
        if isinstance(own, dict) and value in own:
            got = banner.own_palette(own[value])
            value = (list(got[0]) + list(got[1] or [])) if got else None
        elif value in banner.PALETTES:
            main, accent = banner.PALETTES[value]
            value = list(main) + list(accent or [])
        else:
            return None
    if not isinstance(value, (list, tuple)):
        return None
    cols = [_hex(c) if isinstance(c, str) else (tuple(int(v) for v in c) if isinstance(c, (list, tuple)) and len(c) == 3
                                                else None) for c in value]
    cols = [c for c in cols if c]
    return cols or None


def _hex(c):
    """``#rrggbb`` as numbers; None when it is not that."""
    try:
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) if isinstance(c, str) and c.startswith("#") and len(c) == 7 else None
    except ValueError:
        return None


BAYER = ((0.125, 0.625), (0.875, 0.375))                 # which of two colours a pixel takes, by where it is


def to_palette(px, colours, shades=3, dither=True):
    """Repaint a picture (rows of ``(r, g, b)`` or None) in a palette's colours only: each pixel becomes
    the nearest of the colours at ``shades`` strengths, or - dithered - one of the two nearest by where
    it lies between them, in a pattern. The same picture gives the same picture."""
    shades = max(1, min(8, int(shades or 1)))
    table = sorted({tuple(int(c * k / float(shades)) for c in col) for col in colours for k in range(1, shades + 1)})
    known = {}
    for y, row in enumerate(px):
        for x, c in enumerate(row):
            if c is None:
                continue
            got = known.get(c)
            if got is None:
                ranked = sorted((((c[0] - t[0]) ** 2 * 3 + (c[1] - t[1]) ** 2 * 4 + (c[2] - t[2]) ** 2 * 2), t) for t in table)
                d0 = math.sqrt(ranked[0][0])
                d1 = math.sqrt(ranked[1][0]) if len(ranked) > 1 else 0.0
                got = known[c] = (ranked[0][1], ranked[1][1] if len(ranked) > 1 else ranked[0][1],
                                  d0 / (d0 + d1) if d0 + d1 > 0 else 0.0)
            row[x] = got[1] if dither and got[2] > BAYER[y % 2][x % 2] else got[0]
    return px


class Subject:
    """A model made ready to be seen: its triangles, its lines whole and group by group, how big it is."""

    def __init__(self, model, clip="idle", look=None):
        self.model, self.clip = model, clip
        self.name = model.name
        self.look = dict(look or {})                     # how it is to be drawn (see looks())
        self.groups = list(model.groups)
        verts = model.pose(clip, 0.0)
        # a model whose parts move (tracks, frames): corners of different parts stay apart, and each
        # corner of the lines remembers which of the model's it is, to be put where a pose has it
        self.moving = bool(model.tracks or model.frames or model.motion is not None)
        apart = None
        if self.moving:
            apart = [0] * len(verts)
            for f in model.faces:
                for i in f[:3]:
                    apart[i] = f[5]
        self._origin = [] if self.moving else None
        self.wire = vector.from_triangles(verts, [f[:3] for f in model.faces], apart=apart, origin=self._origin)
        self.parts = []                                  # (group, its lines)
        self._origins = []
        for g, name in enumerate(self.groups):
            tris = [f[:3] for f in model.faces if f[5] == g]
            if tris:
                back = [] if self.moving else None
                self.parts.append((name, vector.from_triangles(verts, tris, origin=back)))
                self._origins.append(back)
        self._posed = None                               # (clip, time, the lines whole, the lines part by part)
        xs, ys, zs = ([v[i] for v in verts] or [0.0] for i in range(3))
        self.low, self.high = (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))
        self.mid = tuple((self.low[i] + self.high[i]) / 2.0 for i in range(3))
        self.half = tuple(max(0.05, (self.high[i] - self.low[i]) / 2.0) for i in range(3))
        self.reach = math.sqrt(sum(h * h for h in self.half))                # the ball it fits in

    def posed(self, clip=None, when=0.0):
        """Its lines whole and part by part as it is ``when`` beats into ``clip``: the lines at rest, their
        corners where the pose has them. A model that never moves is always as it was."""
        if not self.moving:
            return self.wire, self.parts
        clip = clip or self.clip
        if self._posed is not None and self._posed[:2] == (clip, when):
            return self._posed[2], self._posed[3]
        verts = self.model.pose(clip, when)

        def moved(wire, origin):
            return vector.Wire([verts[i] for i in origin], wire.edges, wire.faces, wire.colour, wound=wire.wound)
        whole = moved(self.wire, self._origin)
        parts = [(name, moved(wire, origin)) for (name, wire), origin in zip(self.parts, self._origins)]
        self._posed = (clip, when, whole, parts)
        return whole, parts

    def when(self, t, clip=None, at=None):
        """The time (beats) to pose it at: ``t`` as it runs, or ``at`` (0..1) of the way through the clip."""
        if at is None:
            return t
        return max(0.0, min(1.0, float(at))) * self.model.beats(clip or self.clip) * 0.999999

    def camera(self, yaw, pitch, zoom, w, h, fov=40.0):
        """An eye that has all of it in sight in ``w`` by ``h`` dots, from ``yaw`` round it and ``pitch`` up."""
        reach = math.tan(math.radians(fov) / 2.0)
        far = self.reach * 0.86 / (reach * min(1.0, h / float(w))) / max(0.2, zoom)
        a, p = math.radians(yaw), math.radians(max(-89.0, min(89.9, pitch)))
        eye = (self.mid[0] + far * math.sin(a) * math.cos(p), self.mid[1] - far * math.cos(a) * math.cos(p),
               self.mid[2] + far * math.sin(p))
        return vector.Camera(eye, self.mid, fov=fov)


def _tone(subject, name, n, colour):
    """The colour of a model's named part in the views that tell parts apart: its look's, else the hull
    in the display's own and the others in turn."""
    own = (subject.look.get("groups") or {}).get(name)
    if own:
        return own
    return colour if n == 0 else TONES[(n - 1) % len(TONES)]


def _cells(scope, unicode):
    return scope.rows("dots" if unicode else "strokes", unicode)


def draw(subject, view="shaded", cols=60, rows=24, yaw=30.0, pitch=20.0, zoom=1.0, colour="green", unicode=True,
         cut_at=None, axis=1, levels=1, level=0, values=None, t=0.0, scope=None, clip=None, at=None):
    """A model in a view, as rows of cells. ``cut_at`` (0..1): how far along ``axis`` the cut stands (the
    structure view); ``levels`` and ``level``: the floors of a plan (which ``yaw`` turns on the page); ``values``: a heat for each group by
    name (0..1; a group without one is cold); ``t``: the time, for a model that moves; ``clip``: what it
    plays (its tracks or frames; None: ``idle``); ``at`` (0..1): how far through the clip it is shown,
    whatever the time - a door as far open as a value says."""
    if view is None:                                     # the model's own view (its look), else shaded
        view = subject.look.get("view")
    view = view if view in VIEWS else "shaded"
    clip = clip or subject.clip
    when = subject.when(t, clip, at)
    if view in ("shaded", "heat"):
        return _raster(subject, view, cols, rows, yaw, pitch, zoom, values, when, unicode, clip)
    whole, in_parts = subject.posed(clip, when)
    mine = colour or subject.look.get("ink")             # asked for here, else the model's own, else the display's
    if scope is None:
        scope = vector.Scope(cols, rows, colour=mine or "green")
    elif mine:
        scope.colour = vector.colour_of(mine)
    colour = mine or "green"
    scope.clear()
    W, H = scope.W, scope.H
    if view == "plan":
        levels = max(1, int(levels))
        level = max(0, min(levels - 1, int(level)))
        z0 = subject.low[2] + (subject.high[2] - subject.low[2]) * level / levels
        z1 = subject.low[2] + (subject.high[2] - subject.low[2]) * (level + 1) / levels
        fov = 14.0
        reach = math.tan(math.radians(fov) / 2.0)
        across, along = subject.half[0], subject.half[1]
        # turned a quarter if it is drawn bigger so: the long way of it along the long way of the screen
        lying = min(W / along, H / across) > min(W / across, H / along) * 1.001
        if lying:
            across, along = along, across
        far = max(across * 1.15 / reach, along * 1.15 / (reach * H / float(W))) / max(0.2, zoom)
        cam = vector.Camera((subject.mid[0], subject.mid[1], subject.mid[2] + far), subject.mid, fov=fov,
                            roll=yaw + (90.0 if lying else 0.0))
        for n, (name, wire) in enumerate(in_parts):
            part = wire if levels == 1 else cut(cut(wire, 2, z1 + 1e-6, -1), 2, z0 - 1e-6, 1)
            scope.draw(cam, part, colour=_tone(subject, name, n, colour), bright=0.7 if n == 0 else 1.1)
        return _cells(scope, unicode)
    cam = subject.camera(yaw, pitch, zoom, W, H)
    if view == "wire":
        scope.draw(cam, whole)
    elif view == "solid":
        scope.render(cam, [whole], solid=True)
    else:                                                # structure
        plane = None
        if cut_at is not None:
            plane = subject.low[axis] + (subject.high[axis] - subject.low[axis]) * max(0.0, min(1.0, float(cut_at)))
        for n, (name, wire) in enumerate(in_parts):
            part = wire if plane is None else cut(wire, axis, plane, 1)
            scope.draw(cam, part, colour=_tone(subject, name, n, colour), bright=0.45 if n == 0 else 1.2)
        if plane is not None:                            # where it is cut: the outline of the plane
            lo, hi = list(subject.low), list(subject.high)
            lo[axis] = hi[axis] = plane
            others = [i for i in range(3) if i != axis]
            ring = []
            for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
                p = [plane, plane, plane]
                p[others[0]] = (lo, hi)[u][others[0]]
                p[others[1]] = (lo, hi)[v][others[1]]
                ring.append(tuple(p))
            scope.draw(cam, vector.polyline(ring, closed=True), colour="white", bright=0.9)
    return _cells(scope, unicode)


def _raster(subject, view, cols, rows, yaw, pitch, zoom, values, t, unicode, clip=None):
    """The shaded and heat views: triangles filled, the nearest in front."""
    from .model import raster
    model = subject.model
    W, H = cols, rows * 2
    probe = vector.Scope(cols, rows)                     # its dots are half a pixel: the same eye as the line views
    cam = subject.camera(yaw, pitch, zoom, probe.W, probe.H)
    verts = model.pose(clip or subject.clip, t) if model.moves else model.pose(subject.clip, 0.0)
    pts = []
    for p in verts:
        s = probe.project(cam, p)
        pts.append(None if s is None else (s[0] / 2.0, s[1] / 2.0, 1.0 / s[2]))
    lr, lu, lt = subject.look.get("light") or (0.5, 0.8, 0.6)     # from the right, from above, from the eye's side
    light = vector._unit((cam.right[0] * lr + cam.up[0] * lu - cam.ahead[0] * lt,
                          cam.right[1] * lr + cam.up[1] * lu - cam.ahead[1] * lt,
                          cam.right[2] * lr + cam.up[2] * lu - cam.ahead[2] * lt))
    back = (-cam.ahead[0], -cam.ahead[1], -cam.ahead[2])
    heat = {}
    if view == "heat":
        given = values or {}
        for g, name in enumerate(subject.groups):
            heat[g] = thermal(given.get(name, 0.0)) if values is not None else \
                thermal(g / float(max(1, len(subject.groups) - 1)) if len(subject.groups) > 1 else 0.5)
    px = [[None] * W for _ in range(H)]
    zbuf = {}
    through = view == "heat" and len(subject.parts) > 1    # the hull is seen through: what is hot inside shows
    for a, b, c, mi, tint, g in model.faces:
        if through and g == 0:
            continue
        pa, pb, pc = pts[a], pts[b], pts[c]
        if pa is None or pb is None or pc is None:
            continue
        va, vb, vc = verts[a], verts[b], verts[c]
        n = vector._cross(vector._sub(vb, va), vector._sub(vc, va))
        ln = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2])
        if ln < 1e-12:
            continue
        n = (n[0] / ln, n[1] / ln, n[2] / ln)
        facing = n[0] * back[0] + n[1] * back[1] + n[2] * back[2]
        if facing < 0:                                   # seen from behind: lit as its other side
            n = (-n[0], -n[1], -n[2])
        if view == "heat":
            k = 0.62 + 0.38 * max(0.0, n[0] * light[0] + n[1] * light[1] + n[2] * light[2])
            base = heat.get(g, THERMAL[0][1])
            col = (int(base[0] * k), int(base[1] * k), int(base[2] * k))
        else:
            mat = model.materials[mi]
            col = tuple(pbr(mat, tint or mat.rgb, n, light, back))
        raster(px, zbuf, W, H, (pa, pb, pc), col)
    if through:                                          # the hull as faint lines round what is inside it
        faint = thermal((values or {}).get(subject.groups[0], 0.0) * 0.6 + 0.12)
        hull = subject.parts[0][1]
        for i, j in hull.edges:
            sa, sb = probe.project(cam, hull.verts[i]), probe.project(cam, hull.verts[j])
            if sa is None or sb is None:
                continue
            n = int(max(abs(sb[0] - sa[0]), abs(sb[1] - sa[1])) / 2.0) + 1
            for k in range(n + 1):
                x, y = int((sa[0] + (sb[0] - sa[0]) * k / n) / 2.0), int((sa[1] + (sb[1] - sa[1]) * k / n) / 2.0)
                if 0 <= x < W and 0 <= y < H and px[y][x] is None:
                    px[y][x] = faint
    if view == "shaded" and subject.look.get("colours"):     # in the game's colours only
        to_palette(px, subject.look["colours"], subject.look.get("shades", 3), subject.look.get("dither", True))
    out = []
    for y in range(0, H, 2):
        row = []
        for x in range(W):
            up, down = px[y][x], px[y + 1][x]
            if up is None and down is None:
                row.append((" ", None, None))
            elif unicode:
                row.append((None, tuple(up) if up else PAPER, tuple(down) if down else PAPER))
            else:
                c = up or down
                row.append((" .:-=+*#%@"[min(9, int(sum(c) / 765.0 * 10 * 1.4))], None, None))
        out.append(row)
    return out


# --------------------------------------------------------------------------- #
# Planets
# --------------------------------------------------------------------------- #
class Planet:
    """A world: ``field`` (rows of characters, the north pole first; each row all the way round),
    ``legend`` (a character: ``{"name", "colour", "heat"}``), ``tilt`` (degrees its axis leans towards
    the eye), ``spin`` (degrees a second it turns), ``sun`` (degrees round from the eye its sun
    stands), ``sites`` (``{"name", "lat", "lon"}``), ``colour`` (the phosphor of its grid)."""

    def __init__(self, spec, name=""):
        spec = spec if isinstance(spec, dict) else {}
        self.name = str(spec.get("name") or name)
        self.field = [str(r) for r in spec.get("field") or ["."]]
        self.legend = {}
        self.high = {ch: float(v.get("height", 0.0)) if isinstance(v, dict) and isinstance(v.get("height"), (int, float))
                     else 0.0 for ch, v in (spec.get("legend") or {}).items()}     # for a surface scan (engine/ahead.py)
        for ch, v in (spec.get("legend") or {}).items():
            v = v if isinstance(v, dict) else {"colour": v}
            self.legend[ch] = (str(v.get("name") or ch), vector.colour_of(_rgb(v.get("colour")), (120, 120, 120)),
                               float(v.get("heat", 0.5)))
        self.tilt = float(spec.get("tilt", 20.0))
        self.spin = float(spec.get("spin", 6.0))
        self.sun = float(spec.get("sun", 50.0))
        self.sites = [s for s in spec.get("sites") or [] if isinstance(s, dict) and "lat" in s and "lon" in s]
        self.colour = spec.get("colour") or "cyan"

    def at(self, lat, lon):
        """The ground at a latitude (90 north to -90) and a longitude (degrees east): name, colour, heat."""
        rows = self.field
        row = rows[max(0, min(len(rows) - 1, int((90.0 - lat) / 180.0 * len(rows))))] or "."
        ch = row[int((lon % 360.0) / 360.0 * len(row)) % len(row)]
        return self.legend.get(ch, (ch, (120, 120, 120), 0.5))

    def height(self, lat, lon):
        """How high the ground stands there, by its legend's ``height`` (0 when it gives none)."""
        rows = self.field
        row = rows[max(0, min(len(rows) - 1, int((90.0 - lat) / 180.0 * len(rows))))] or "."
        return self.high.get(row[int((lon % 360.0) / 360.0 * len(row)) % len(row)], 0.0)


def _rgb(c):
    if isinstance(c, str) and c.startswith("#") and len(c) == 7:
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    return c


def draw_planet(planet, view="surface", cols=40, rows=20, t=0.0, turn=None, unicode=True, scope=None, sites=None):
    """A planet in a view, as rows of cells. ``turn``: how far round it has turned (degrees; else by its
    ``spin`` and the time ``t``); ``sites``: more places to name on it than its own."""
    view = view if view in PLANET_VIEWS else "surface"
    turn = planet.spin * t if turn is None else float(turn)
    tilt = math.radians(planet.tilt)
    ct, st = math.cos(tilt), math.sin(tilt)

    def seen(lat, lon):
        """A place on it as the eye has it: right, up, towards the eye (of a ball of radius 1)."""
        la, lo = math.radians(lat), math.radians(lon + turn)
        x, y, z = math.cos(la) * math.sin(lo), math.sin(la), math.cos(la) * math.cos(lo)
        return x, y * ct - z * st, y * st + z * ct
    if view == "grid":
        scope = scope or vector.Scope(cols, rows, colour=planet.colour)
        scope.clear()
        cx, cy = scope.W / 2.0, scope.H / 2.0
        R = min(scope.W, scope.H) / 2.0 - 2
        for lat in range(-60, 61, 30):
            _arc(scope, [seen(lat, lon) for lon in range(0, 361, 6)], cx, cy, R, 1.0 if lat == 0 else 0.6)
        for lon in range(0, 360, 30):
            _arc(scope, [seen(lat, lon) for lat in range(-90, 91, 6)], cx, cy, R, 0.6)
        scope.circle2(cx, cy, R, 1.2)
        out = _cells(scope, unicode)
    else:
        W, H = cols, rows * 2
        R = min(W, H) / 2.0 - 0.5
        cx, cy = W / 2.0, H / 2.0
        sun = math.radians(planet.sun)
        sx, sz = math.sin(sun), math.cos(sun)
        px = [[None] * W for _ in range(H)]
        for y in range(H):
            vy = (cy - (y + 0.5)) / R
            if abs(vy) >= 1:
                continue
            row = px[y]
            for x in range(W):
                vx = ((x + 0.5) - cx) / R
                d = 1.0 - vx * vx - vy * vy
                if d <= 0:
                    continue
                vz = math.sqrt(d)
                py, pz = vy * ct + vz * st, -vy * st + vz * ct              # out of the tilt
                lat = math.degrees(math.asin(max(-1.0, min(1.0, py))))
                lon = math.degrees(math.atan2(vx, pz)) - turn
                _name, col, hot = planet.at(lat, lon)
                if view == "heat":
                    c, k = thermal(hot), 0.55 + 0.45 * vz
                else:
                    c, k = col, 0.10 + 0.95 * max(0.0, vx * sx + vz * sz) * (0.75 + 0.25 * vz)
                row[x] = (min(255, int(c[0] * k)), min(255, int(c[1] * k)), min(255, int(c[2] * k)))
        out = []
        for y in range(0, H, 2):
            line = []
            for x in range(W):
                up, down = px[y][x], px[y + 1][x]
                if up is None and down is None:
                    line.append((" ", None, None))
                elif unicode:
                    line.append((None, up or PAPER, down or PAPER))
                else:
                    c = up or down
                    line.append((" .:-=+*#%@"[min(9, int(sum(c) / 765.0 * 10 * 1.4))], None, None))
            out.append(line)
    radius = (min(cols * 2, rows * 4) / 2.0 - 2) / 2.0 if view == "grid" else min(cols, rows * 2) / 2.0 - 0.5
    for s in list(planet.sites) + [x for x in sites or [] if isinstance(x, dict)]:   # the places on the near side
        try:
            x, y, z = seen(float(s["lat"]), float(s["lon"]))
        except (TypeError, ValueError):
            continue
        if z <= 0.05:
            continue
        col = int(cols / 2.0 + x * radius)
        line = int(rows / 2.0 - y * radius / 2.0)
        mark, name = "+" if not unicode else "┼", str(s.get("name", ""))
        text = mark + " " + name
        if name and col + len(text) > cols and col - len(name) - 1 >= 0:
            text, col = name + " " + mark, col - len(name) - 1   # no room after its mark: its name before it
        if 0 <= line < rows:
            for i, ch in enumerate(text):
                if 0 <= col + i < cols:
                    out[line][col + i] = (ch, (255, 255, 255), None)
    return out


def _arc(scope, points, cx, cy, R, bright):
    prev = None
    for x, y, z in points:
        cur = (cx + x * R, cy - y * R) if z > 0 else None
        if prev is not None and cur is not None:
            scope.line2(prev[0], prev[1], cur[0], cur[1], bright)
        prev = cur


def look_problems(data):
    """What is wrong in a game's ``"model_look"`` and in its models' ``"look"``s."""
    out = []
    cfg = getattr(data, "config", None) or {}
    table = getattr(data, "models", None) or {}
    places = [("game.json: model_look", cfg.get("model_look"))] if cfg.get("model_look") is not None else []
    places += [("model '%s': look" % name, spec["look"]) for name, spec in table.items()
               if isinstance(spec, dict) and spec.get("look") is not None]
    for where, look in places:
        if not isinstance(look, dict):
            out.append("%s should be a map (%s)" % (where, ", ".join(LOOK_KEYS)))
            continue
        for k in look:
            if k not in LOOK_KEYS:
                out.append("%s: unknown key '%s' (%s)" % (where, k, ", ".join(LOOK_KEYS)))
        if look.get("view") not in (None,) + VIEWS:
            out.append("%s: unknown view '%s' (%s)" % (where, look["view"], ", ".join(VIEWS)))
        inks = [("ink", look.get("ink"))] + [("groups %s" % g, c) for g, c in (look["groups"].items()
                                                                               if isinstance(look.get("groups"), dict) else [])]
        if look.get("groups") is not None and not isinstance(look["groups"], dict):
            out.append("%s: \"groups\" should be a map of a part's name to a colour" % where)
        for what, c in inks:
            if c is not None and not (isinstance(c, str) and (c in vector.COLOURS or _hex(c))):
                out.append("%s: %s is not a colour (%s, or #rrggbb)" % (where, what, ", ".join(sorted(vector.COLOURS))))
        if look.get("palette") is not None and palette(look["palette"], cfg.get("palettes")) is None:
            out.append("%s: there is no palette '%s' (one of the game's own \"palettes\", a built-in one, or a list "
                       "of #rrggbb)" % (where, look["palette"]))
        shades = look.get("shades")
        if shades is not None and (isinstance(shades, bool) or not isinstance(shades, int) or not 1 <= shades <= 8):
            out.append("%s: \"shades\" should be a whole number from 1 to 8" % where)
        if look.get("dither") not in (None, True, False):
            out.append("%s: \"dither\" should be true or false" % where)
        light = look.get("light")
        if light is not None and not (isinstance(light, list) and len(light) == 3
                                      and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in light)
                                      and any(light)):
            out.append("%s: \"light\" should be three numbers: from the right, from above, from the eye's side" % where)
    return out


def planet_problems(data):
    """What is wrong in a game's ``planets.json``."""
    out = []
    table = getattr(data, "planets", None)
    if not table:
        return out
    if not isinstance(table, dict):
        return ["planets.json should be a map of planets by name"]
    for name, spec in table.items():
        where = "planet '%s'" % name
        if not isinstance(spec, dict):
            out.append("%s: it should be a map" % where)
            continue
        field = spec.get("field")
        if not isinstance(field, list) or not field or not all(isinstance(r, str) and r for r in field):
            out.append("%s: it needs a \"field\": rows of characters, the north pole first" % where)
            continue
        legend = spec.get("legend") if isinstance(spec.get("legend"), dict) else {}
        lost = sorted({ch for r in field for ch in r} - set(legend))
        if lost:
            out.append("%s: the field has characters the legend does not explain: %s" % (where, " ".join(lost)))
        for ch, v in legend.items():
            if isinstance(v, dict) and isinstance(v.get("heat"), (int, float)) and not 0 <= v["heat"] <= 1:
                out.append("%s: the heat of '%s' should be from 0 to 1" % (where, ch))
        if spec.get("colour") is not None and spec["colour"] not in vector.COLOURS:
            out.append("%s: unknown colour '%s' (%s)" % (where, spec["colour"], ", ".join(vector.COLOURS)))
        for s in spec.get("sites") or []:
            if not isinstance(s, dict) or not all(isinstance(s.get(k), (int, float)) for k in ("lat", "lon")):
                out.append("%s: a site needs a \"name\", a \"lat\" and a \"lon\"" % where)
    return out


# --------------------------------------------------------------------------- #
# Looking at things
# --------------------------------------------------------------------------- #
class Look:
    """Where a viewer stands and what it shows: turned by keys (:meth:`key`), drawn by :meth:`rows`."""

    def __init__(self, things):
        self.things = list(things)                       # Subjects and Planets
        self.n = 0
        self.view = 0
        self.yaw, self.pitch, self.zoom = 30.0, 20.0, 1.0
        self.turning = True
        self.cut, self.axis = None, 1
        self.levels, self.level = 1, 0
        self.over = False
        self.scopes = {}
        self.clip = None                                 # the clip a model plays (None: as it stands)

    @property
    def thing(self):
        return self.things[self.n]

    def views(self):
        return PLANET_VIEWS if isinstance(self.thing, Planet) else VIEWS

    def key(self, k):
        views = self.views()
        if k in ("q", "esc", "ctrl-d"):
            self.over = True
        elif k in ("left", "right"):
            self.yaw += 10 if k == "right" else -10
            self.turning = False
        elif k in ("up", "down"):
            self.pitch = max(-80.0, min(89.0, self.pitch + (10 if k == "up" else -10)))
        elif k in ("+", "="):
            self.zoom = min(4.0, self.zoom * 1.2)
        elif k in ("-", "_"):
            self.zoom = max(0.3, self.zoom / 1.2)
        elif k in ("v", "enter"):
            self.view = (self.view + 1) % len(views)
        elif len(k) == 1 and k.isdigit() and 1 <= int(k) <= len(views):
            self.view = int(k) - 1
        elif k == "space":
            self.turning = not self.turning
        elif k in ("tab", "n"):
            self.n = (self.n + 1) % len(self.things)
            self.view = min(self.view, len(self.views()) - 1)
            self.clip = None
        elif k == "p":                                   # play its next clip (after the last: still again)
            clips = [None] + list(getattr(getattr(self.thing, "model", None), "clips", []))
            self.clip = clips[(clips.index(self.clip) + 1) % len(clips)] if self.clip in clips else None
        elif k == "c":
            self.cut = 0.5 if self.cut is None else None
        elif k in ("[", "]") and self.cut is not None:
            self.cut = max(0.0, min(1.0, self.cut + (0.1 if k == "]" else -0.1)))
        elif k == "x":
            self.axis = (self.axis + 1) % 3
        elif k == "l":
            self.levels = self.levels % 6 + 1
            self.level = min(self.level, self.levels - 1)
        elif k in (",", "."):
            self.level = max(0, min(self.levels - 1, self.level + (1 if k == "." else -1)))

    def rows(self, cols, rows, t=0.0, unicode=True):
        thing, view = self.thing, self.views()[self.view % len(self.views())]
        yaw = self.yaw + (12.0 * t if self.turning else 0.0)
        scope = self.scopes.get((cols, rows))
        if scope is None:
            scope = self.scopes[(cols, rows)] = vector.Scope(cols, rows)
        if isinstance(thing, Planet):
            scope.colour = vector.colour_of(thing.colour)
            return draw_planet(thing, view, cols, rows, t, None if self.turning else self.yaw, unicode, scope)
        scope.colour = vector.colour_of("green")
        if view == "plan":                               # a map lies still: the arrows turn it
            yaw = self.yaw - 30.0
        return draw(thing, view, cols, rows, yaw, self.pitch, self.zoom, None, unicode, self.cut, self.axis,
                    self.levels, self.level, None, t * 2.0 if self.clip else t, scope, clip=self.clip)

    def status(self):
        thing, views = self.thing, self.views()
        view = views[self.view % len(views)]
        more = ""
        if view == "structure":
            more = "  cut %s at %d%% (C, [ ], X)" % ("xyz"[self.axis], round(self.cut * 100)) if self.cut is not None else "  C cuts it"
        elif view == "plan":
            more = "  level %d of %d (L, , .)" % (self.level + 1, self.levels)
        elif view == "heat" and not isinstance(thing, Planet):
            more = "  by group: " + " ".join(thing.groups)
        clips = list(getattr(getattr(thing, "model", None), "clips", []))
        if clips:
            more += "  P plays %s" % (self.clip or "/".join(clips))
        return "%s  %s (%d/%d)%s   arrows  +/-  V view  Tab next  Space turn  Q" % (
            thing.name.upper(), view, self.view % len(views) + 1, len(views), more)


def things_of(data):
    """A game's models and planets, ready to be looked at."""
    from . import model
    how = looks(data)
    out = [Subject(m, look=how.get(name)) for name, m in model.load(getattr(data, "models", None) or {}).items()]
    out += [Planet(spec, name) for name, spec in (getattr(data, "planets", None) or {}).items() if isinstance(spec, dict)]
    return out


def run(term, things, start=None, view=None, keys=None, clock=None, frames=None):
    """Look at things on the terminal until Q. ``frames``: draw so many and leave (tests)."""
    import time
    from .frame import Screen
    from .keys import KeyReader
    look = Look(things)
    if start is not None:
        look.n = next((i for i, th in enumerate(look.things) if th.name == start), 0)
    if view in look.views():
        look.view = look.views().index(view)
    clock = clock or time.monotonic
    screen = Screen(term, keys if keys is not None else KeyReader(), {}, False)
    screen.start()
    began = clock()
    try:
        n = 0
        while not look.over:
            W, H = screen.size()
            screen.frame(look.rows(W, H - 2, clock() - began, screen.unicode), status=look.status())
            n += 1
            if frames is not None and n >= frames:
                break
            k = screen.keys.get(0.08 if look.turning else 0.5)
            while k is not None and not look.over:
                look.key(k)
                k = screen.keys.get(0)
    except KeyboardInterrupt:
        pass
    finally:
        screen.stop()
    return look


def plain(rows):
    return ["".join(c[0] if c[0] is not None else "▀" for c in r).rstrip() for r in rows]


def main(argv=None):
    """``python -m engine.viewer GAME [NAME]`` or ``FILE.glb``; ``--view NAME``; ``--print VIEW`` one picture as text."""
    import os
    import sys
    from .term import Term
    argv = list(sys.argv[1:] if argv is None else argv)

    def after(flag):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None
    asked = [after("--view"), after("--print")]
    names = [a for a in argv if not a.startswith("-") and a not in asked]
    if not names:
        print(main.__doc__)
        return 2
    path = names[0]
    if os.path.isfile(path) and path.lower().endswith((".glb", ".gltf")):
        from . import gltf
        from .model import Model
        name = os.path.splitext(os.path.basename(path))[0]
        things = [Subject(Model(name, gltf.to_model(path)))]
    else:
        from .data import GameData
        for cand in (path, os.path.join("games", path)):
            if os.path.isdir(cand):
                path = cand
                break
        things = things_of(GameData(path))
    if not things:
        print("Nothing to look at there: no models, no planets.")
        return 1
    want = names[1] if len(names) > 1 else None
    if want and want not in [th.name for th in things]:
        print("Nothing called '%s'. There is: %s" % (want, ", ".join(th.name for th in things)))
        return 1
    if after("--print"):
        thing = next((th for th in things if th.name == want), things[0])
        view = after("--print")
        rows = draw_planet(thing, view, 60, 24, 3.0) if isinstance(thing, Planet) else \
            draw(thing, view, 72, 24, yaw=0.0 if view == "plan" else 30.0)
        print("\n".join(plain(rows)))
        return 0
    term = Term()
    if not (term.is_tty and term.ansi):
        print("Looking at things needs a terminal. Things here: %s" % ", ".join(th.name for th in things))
        return 0
    run(term, things, want, after("--view"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
