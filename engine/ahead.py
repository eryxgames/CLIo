# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""What is ahead, in lines: the view forward from a vehicle over its own map, and a field of rocks.

A vehicle simulator's map (engine/sim.py) is drawn from above; this draws the same map as the pilot
sees it, on a vector display (engine/vector.py) - a net on the ground that fades with distance, rock as
ridges and peaks, buildings as blocks, trees, the pad as a ring, the marks to pass as posts with their numbers, a
horizon and stars. ``"look": "space"`` draws the same map as open space: what is solid floats there as
tumbling rocks, the pad is a ring to fly to, the marks are lamps, and there is no ground.

A simulator's screen of panels shows it with the widget ``{"ahead": true}``, or with what to change::

    {"ahead": {"look": "space", "far": 14, "fov": 80, "tilt": -6, "solid": true}}

:func:`field` is the same rocks with nothing else: a flight through them that never ends (the vector
reel's scene ``asteroids``, and ``{"scope": {"scene": "asteroids"}}`` in any panel).

Everything here is drawn from where things are and from the time: nothing is kept between frames but
the display's own afterglow, and nothing here changes a simulator."""
from __future__ import annotations

import math

from . import vector
from .vector import Camera, Wire

LOOKS = ("terrain", "space")
FAR = 12.0                        # how far it draws (tiles)
EYE = 0.45                        # the eye above where the vehicle is
STARS = 70
T = (1.0 + 5 ** 0.5) / 2.0
ICO = [(-1, T, 0), (1, T, 0), (-1, -T, 0), (1, -T, 0), (0, -1, T), (0, 1, T), (0, -1, -T), (0, 1, -T),
       (T, 0, -1), (T, 0, 1), (-T, 0, -1), (-T, 0, 1)]
ICO_FACES = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
             (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
             (8, 6, 7), (9, 8, 1)]
_made = {}


def chance(*key):
    """A number from 0 to 1 that is always the same for the same key (whole numbers): no dice are thrown."""
    h = 2166136261
    for k in key:
        h = ((h ^ (int(k) & 0xffffffff)) * 16777619) & 0xffffffff
        h ^= h >> 13
        h = (h * 0x5bd1e995) & 0xffffffff
        h ^= h >> 15
    return (h & 0xffffff) / float(0x1000000)


def lump(seed=0, rough=0.38):
    """A rock adrift: twenty sides, no two the same, about one across. The same for the same ``seed``."""
    key = ("lump", seed, rough)
    if key not in _made:
        squash = [0.75 + 0.5 * chance(seed, 90 + i) for i in range(3)]
        verts = []
        for i, p in enumerate(ICO):
            n = math.sqrt(sum(c * c for c in p))
            r = 0.5 * (1.0 - rough / 2.0 + rough * chance(seed, i))
            verts.append(tuple(p[k] / n * r * squash[k] for k in range(3)))
        _made[key] = _solid(verts, ICO_FACES)
    return _made[key]


def ridge(sim, tx, ty):
    """The rock of one tile, as part of all the rock round it: a corner stands as high as the rock is
    where rock is on every side of it, and on the ground where the rock ends - so rock beside rock is
    the ground's own net going up over a ridge. A rock alone is a peak. The same for the same place."""
    high = _height("rock")

    def corner(i, j):
        if all(sim.kind(i + dx, j + dy) == "rock" for dx in (-1, 0) for dy in (-1, 0)):
            return high * (0.55 + 0.45 * chance(i, j, 11))
        return 0.0
    verts = [(tx, -(ty + 1), corner(tx, ty + 1)), (tx + 1, -(ty + 1), corner(tx + 1, ty + 1)),
             (tx + 1, -ty, corner(tx + 1, ty)), (tx, -ty, corner(tx, ty))]
    if any(v[2] for v in verts):
        return Wire(verts, [(0, 1), (1, 2), (2, 3), (3, 0)], [(0, 1, 2), (0, 2, 3)], wound=True)
    verts.append((tx + 0.35 + 0.3 * chance(tx, ty, 12), -(ty + 0.35 + 0.3 * chance(tx, ty, 13)),
                  high * (0.8 + 0.2 * chance(tx, ty, 14))))
    return _solid(verts, [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)])


def block(height=2.0, wide=0.7):
    """A building on one tile."""
    key = ("block", height, wide)
    if key not in _made:
        h = wide / 2.0
        v = [(x, y, z) for z in (0.0, height) for y in (-h, h) for x in (-h, h)]
        quads = [(4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
        e = [(0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        _made[key] = Wire(v, e, quads, wound=True)
    return _made[key]


def tree(seed=0, height=1.0):
    """A tree: a stem and a crown of four sides."""
    key = ("tree", seed % 4, height)
    if key not in _made:
        r, low = 0.26 + 0.06 * (seed % 4) / 3.0, height * 0.3
        verts = [(r, r, low), (-r, r, low), (-r, -r, low), (r, -r, low), (0.0, 0.0, height), (0.0, 0.0, 0.0), (0.0, 0.0, low)]
        faces = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4), (3, 2, 1, 0)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4), (5, 6)]
        _made[key] = Wire(verts, edges, faces, wound=True)
    return _made[key]


def _solid(verts, tris):
    """Triangles wound the way that looks out, as a thing of lines with every edge."""
    edges = sorted({(min(a, b), max(a, b)) for f in tris for a, b in zip(f, f[1:] + f[:1])})
    return Wire(list(verts), edges, [tuple(f) for f in tris], wound=True)


def _ring(r=0.42, n=8, z=0.02):
    return vector.polyline([(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z) for i in range(n)],
                           closed=True)


def stars(scope, cam, count=STARS, above=None, bright=0.5):
    """Stars where the eye looks: always the same sky. ``above``: only over that row of dots (a horizon)."""
    for i in range(count):
        a = 2 * math.pi * chance(7, i)
        up = -0.25 + 1.25 * chance(8, i) if above is not None else 2 * chance(8, i) - 1
        flat = math.sqrt(max(0.0, 1 - up * up))
        p = (cam.eye[0] + 900 * flat * math.cos(a), cam.eye[1] + 900 * flat * math.sin(a), cam.eye[2] + 900 * up)
        s = scope.project(cam, p)
        if s and 0 <= s[0] < scope.W and 0 <= s[1] < (scope.H if above is None else above):
            scope.dot(int(s[0]), int(s[1]), bright * (0.5 + chance(9, i)))


def eye_of(sim, tilt=-6.0, fov=78.0, height=EYE):
    """The camera of a vehicle: where it is, a little above, looking the way it heads. A map's rows go
    south; here north is +y and up is +z."""
    from .sim import degrees
    a = math.radians(degrees(sim.heading))
    ex, ey, ez = sim.x, -sim.y, sim.z + height
    fx, fy = math.sin(a), math.cos(a)
    return Camera((ex, ey, ez), (ex + fx, ey + fy, ez + math.tan(math.radians(tilt))), fov=fov, near=0.08), (fx, fy)


def draw(scope, sim, spec=None, t=0.0):
    """Draw what is ahead of a simulator's vehicle on a vector display. ``spec``: the widget's own
    ``look`` (``terrain``, ``space``), ``far``, ``fov``, ``tilt``, ``solid`` (false: everything shows
    through everything), ``stars`` (false: none)."""
    spec = spec if isinstance(spec, dict) else {}
    look = spec.get("look") if spec.get("look") in LOOKS else "terrain"
    far = max(3.0, min(40.0, _num(spec.get("far"), FAR)))
    space = look == "space"
    cam, (fx, fy) = eye_of(sim, _num(spec.get("tilt"), 0.0 if space else -6.0), _num(spec.get("fov"), 78.0))
    ex, ey = cam.eye[0], cam.eye[1]
    scope.cue = (far * 0.25, far)
    scope.dim = 0.12
    solid = spec.get("solid", True) is not False
    horizon = None
    if not space:                                        # where the ground ends
        s = scope.project(cam, (ex + fx * 5000, ey + fy * 5000, 0.0))
        if s:
            horizon = int(s[1])
            if 0 <= horizon < scope.H:
                scope.line2(0, horizon, scope.W - 1, horizon, 0.35)
    if spec.get("stars", True) is not False:
        stars(scope, cam, above=horizon)
    x0, x1 = int(math.floor(sim.x - far)), int(math.ceil(sim.x + far))
    y0, y1 = int(math.floor(sim.y - far)), int(math.ceil(sim.y + far))
    things, flat, strong = [], [], []

    def seen(px, py, slack=1.5):                         # (world) in front, and not too far
        dx, dy = px - ex, py - ey
        return dx * fx + dy * fy > -slack and dx * dx + dy * dy <= far * far

    if not space:                                        # the net on the ground: tile edges, none over water
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                if not seen(tx, -ty, 1.0):
                    continue
                here = sim.kind(tx, ty)
                for ox, oy, ax, ay in ((1, 0, tx, ty - 1), (0, 1, tx - 1, ty)):      # the edge east, the edge south
                    other = sim.kind(ax, ay)
                    if here == "water" and other == "water":
                        continue
                    a, b = (tx, -ty, 0.0), (tx + ox, -(ty + oy), 0.0)
                    (strong if "road" in (here, other) and here != other else flat).append((a, b))
    edge = 0 if space else 1                             # the rock round a map: one tile of it
    for ty in range(max(-edge, y0), min(sim.H + edge, y1 + 1)):
        for tx in range(max(-edge, x0), min(sim.W + edge, x1 + 1)):
            cx, cy = tx + 0.5, -(ty + 0.5)
            if not seen(cx, cy):
                continue
            kind = sim.kind(tx, ty)
            seed = tx * 131 + ty * 7919
            high = _height(kind)
            if space:
                if high:
                    size = 0.55 + 0.25 * high * (0.6 + 0.4 * chance(seed, 1))
                    rate = 8 + 30 * chance(seed, 2)
                    things.append(lump(seed % 23).placed((cx, cy, 0.8 + 2.4 * chance(seed, 3)), yaw=t * rate,
                                                        pitch=t * rate * 0.6 + 360 * chance(seed, 4), scale=size))
                elif kind == "pad":
                    for r in (0.45, 0.3):
                        strong.extend(_edges(vector.ring(r, 12, axis="z").placed((cx, cy, 0.05))))
            elif kind == "rock":
                things.append(ridge(sim, tx, ty))
            elif kind == "building":
                things.append(block(high, 0.6 + 0.2 * chance(seed, 6)).placed((cx, cy, 0.0)))
            elif kind == "trees":
                things.append(tree(seed, high).placed((cx, cy, 0.0), yaw=90 * chance(seed, 7)))
            elif kind in ("pad", "fuel"):
                strong.extend(_edges(_ring(0.42 if kind == "pad" else 0.25).placed((cx, cy, 0.0))))
                if kind == "pad":
                    strong += [((cx - 0.18, cy - 0.2, 0.02), (cx - 0.18, cy + 0.2, 0.02)),
                               ((cx + 0.18, cy - 0.2, 0.02), (cx + 0.18, cy + 0.2, 0.02)),
                               ((cx - 0.18, cy, 0.02), (cx + 0.18, cy, 0.02))]
    if solid:
        for thing in things:
            scope.hide(cam, thing)
    for a, b in flat:
        scope.line(cam, a, b, 0.6)
    for a, b in strong:
        scope.line(cam, a, b, 1.0)
    for thing in things:
        scope.draw(cam, thing, bright=0.95, solid=solid)
    marks(scope, cam, sim, space, far, t)
    cx, cy = scope.W // 2, scope.H // 2                  # where it heads
    for dx, dy in ((-3, 0), (-2, 0), (2, 0), (3, 0), (0, -2), (0, 2)):
        scope.dot(cx + dx, cy + dy, 0.9)
    return look


def marks(scope, cam, sim, space=False, far=FAR, t=0.0):
    """The marks to pass: posts with a lamp (in space, lamps alone), numbered; the next one is the
    brightest and blinks, and when it is not in sight an arrow at the side says which way to turn."""
    order = list(getattr(sim, "order", []) or [])
    passed = int(getattr(sim, "passed", 0) or 0)
    nxt = order[passed] if passed < len(order) else None
    was = scope.cue
    scope.cue = None                                     # a mark shows however far it is
    for n in order:
        mx, my = sim.checks[n]
        p = (mx, -my, 1.4 if space else 0.0)
        top = (mx, -my, 1.4 if space else 2.2)
        light = 0.3 if order.index(n) < passed else (1.3 if n == nxt else 0.7)
        if n == nxt and int(t * 3) % 2:
            light = 0.9
        if not space:
            scope.line(cam, p, top, light)
        r = 0.16
        for i in range(4):                               # a lamp: a diamond
            a, b = math.pi / 2 * i, math.pi / 2 * (i + 1)
            scope.line(cam, (top[0] + r * math.cos(a), top[1], top[2] + r * math.sin(a)),
                       (top[0] + r * math.cos(b), top[1], top[2] + r * math.sin(b)), light)
            scope.line(cam, (top[0], top[1] + r * math.cos(a), top[2] + r * math.sin(a)),
                       (top[0], top[1] + r * math.cos(b), top[2] + r * math.sin(b)), light)
        s = scope.project(cam, top)                      # its number beside its lamp (at the top, if that is out of sight above)
        if s and 0 <= s[0] < scope.W and s[1] < scope.H:
            scope.text(min(scope.cols - len(str(n)), int(s[0]) // 2 + 1), max(0, int(s[1]) // 4 - 1), str(n),
                       bright=max(0.6, light))
    scope.cue = was
    if nxt is not None:                                  # the next one, when it is not in the picture
        mx, my = sim.checks[nxt]
        side, _up, front = cam.see((mx, -my, 1.4))
        s = scope.project(cam, (mx, -my, 1.4)) if front > 0 else None
        if s is None or not 0 <= s[0] < scope.W:
            row = scope.rows_n // 2
            if side < 0:
                scope.text(0, row, "< %d" % nxt, bright=1.2)
            else:
                scope.text(scope.cols - 3 - len(str(nxt)), row, "%d >" % nxt, bright=1.2)


def field(scope, t=0.0, speed=2.6, count=26, reach=34.0, seed=3):
    """A flight through rocks that never ends: the same rocks come round again every ``reach`` of the
    way. Returns the words for it."""
    way = t * speed
    sway = 0.5 * math.sin(t * 0.31)
    cam = Camera((sway, way, 0.25 * math.sin(t * 0.23)), (sway * 0.6 + 0.8 * math.sin(t * 0.17), way + 6.0, 0.0), fov=74.0,
                 roll=6.0 * math.sin(t * 0.21), near=0.1)
    scope.cue, scope.dim = (reach * 0.15, reach * 0.9), 0.08
    stars(scope, cam)
    things = []
    lap = math.floor(way / reach)
    for i in range(count):
        along = chance(seed, i, 1) * reach
        y = (lap + (1 if along < way - lap * reach - 1.0 else 0)) * reach + along
        a, r = 2 * math.pi * chance(seed, i, 2), 0.9 + 5.0 * chance(seed, i, 3)
        size = 0.5 + 2.2 * chance(seed, i, 4) ** 2
        rate = 6 + 40 * chance(seed, i, 5)
        things.append(lump(i % 23).placed((r * math.cos(a), y, r * math.sin(a) * 0.6), yaw=t * rate + 360 * chance(seed, i, 6),
                                          pitch=t * rate * 0.7, scale=size))
    scope.render(cam, things, solid=True)
    scope.text(1, 0, "ASTEROIDS")
    scope.text(1, 1, "WAY %6.1f" % way, bright=0.6)
    return "A field of rocks, flown through"


def rows(sim, cols, lines, spec=None, colour="green", t=0.0, unicode=True, scope=None):
    """What is ahead of a simulator's vehicle, as rows of cells. ``scope``: one kept from the last frame
    (for its afterglow)."""
    if scope is None:
        scope = vector.Scope(cols, lines, colour=colour)
    scope.captions = True
    scope.clear()
    draw(scope, sim, spec, t)
    return scope.rows("dots" if unicode else "strokes", unicode)


def problems(spec, where="ahead"):
    """What is wrong in an ``ahead`` widget's own settings."""
    out = []
    if spec is True:
        return out
    if not isinstance(spec, dict):
        return ["%s: it should be true, or a map (look, far, fov, tilt, solid, stars)" % where]
    if spec.get("look") not in (None,) + LOOKS:
        out.append("%s: unknown look '%s' (%s)" % (where, spec["look"], ", ".join(LOOKS)))
    for k, low, high in (("far", 3, 40), ("fov", 30, 120), ("tilt", -45, 45)):
        v = spec.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not low <= v <= high):
            out.append("%s: \"%s\" should be a number from %d to %d" % (where, k, low, high))
    return out


def _edges(wire):
    return [(wire.verts[a], wire.verts[b]) for a, b in wire.edges]


def _height(kind):
    from .sim import GROUND
    return float(GROUND.get(kind, {}).get("height", 0))


def _num(v, default):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else float(default)


def main(argv=None):
    """``python -m engine.ahead [GAME SIM] [--space] [--print]``: the view ahead in a simulator of a game
    as its autopilot flies it (no game: the field of rocks)."""
    import sys
    import time
    from .term import Term
    argv = list(sys.argv[1:] if argv is None else argv)
    names = [a for a in argv if not a.startswith("-")]
    spec = {"look": "space"} if "--space" in argv else {}
    sim = None
    if len(names) >= 2:
        from . import sim as S
        from .data import GameData
        sim = S.make(GameData(names[0]), names[1])
        sim.paused = None
    term = Term()
    cols, lines = term.size()
    cols, lines = max(40, min(cols - 1, 120)), max(12, min(lines - 2, 40))
    scope = vector.Scope(cols, lines, colour="amber" if sim is not None else "green", afterglow=0.3)
    scope.captions = True

    def frame(t):
        scope.clear()
        if sim is not None:
            from . import sim as S
            from .realtime import Controls
            for _ in range(2):
                if not sim.result:
                    sim.step(Controls(sim.tick, frozenset(S.autopilot_keys(sim))))
            draw(scope, sim, spec, t)
        else:
            field(scope, t)
    if "--print" in argv or not term.out.isatty():
        for i in range(40):
            frame(i / 10.0)
        print(scope.plain("dots" if term.unicode else "strokes", term.unicode))
        return 0
    from .frame import Screen
    screen = Screen(term, None, {}, True)
    screen.start()
    try:
        t0 = time.monotonic()
        while True:
            frame(time.monotonic() - t0)
            screen.frame(scope.rows("dots", screen.unicode), status="Ctrl-C ends")
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        screen.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
