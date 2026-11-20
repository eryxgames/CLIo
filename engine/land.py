# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Open land: a landscape grown from a seed - water, shores, fens, heath, rock and snow - as far as the eye goes.

A level with ``"land"`` is open country.  Its ground is a height field worked out from the seed for any cell,
inside the level or beyond it (so the land goes on to the horizon; a level's ``size`` only says where the player
may go).  Heights are in the room's units: 1 is a wall's height and a cell's width.  The level's map, if it has
one, stands on a flattened pad (``at``: where its top-left corner goes); a space in the map is the land.

Drawn, the land is not the rooms' exponential distance (which squeezes everything past ten cells on to the
horizon) but a true perspective from a camera ``Z0`` cells behind the player - equal to it close by - so hills
and mountains far off keep their size.  The ground is drawn column by column, near to far, each new rise
painted only where nothing nearer stands (a "voxel space" picture), and it keeps the depth of every pixel:
walls, monsters and models are drawn over it only where they are nearer (``DepthRow``).
"""
import json
import math

from .firstperson import _colour, mix

CHUNK = 16                                  # cells a side, worked out together
Z0 = 1.6                                    # the camera stands this far behind the player (cells)
INF = 1e9


def _h(ix, iy, s):
    n = (ix * 374761393 + iy * 668265263 + s * 2246822519) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


_LATTICE = {}
_SHARED = {}                                # lands with the same numbers share their chunks (a level built again)


def _lat(ix, iy, s):
    """``_h`` remembered: neighbouring cells share their lattice's corners."""
    key = (ix, iy, s)
    v = _LATTICE.get(key)
    if v is None:
        if len(_LATTICE) > 400000:
            _LATTICE.clear()
        v = _LATTICE[key] = _h(ix, iy, s)
    return v


def value(x, y, s, _get=_LATTICE.get, _floor=math.floor):
    """Smooth noise, 0..1, about one bump a unit."""
    ix, iy = _floor(x), _floor(y)
    fx, fy = x - ix, y - iy
    ux, uy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    ix1, iy1 = ix + 1, iy + 1
    a = _get((ix, iy, s))
    if a is None:
        a = _lat(ix, iy, s)
    b = _get((ix1, iy, s))
    if b is None:
        b = _lat(ix1, iy, s)
    c = _get((ix, iy1, s))
    if c is None:
        c = _lat(ix, iy1, s)
    d = _get((ix1, iy1, s))
    if d is None:
        d = _lat(ix1, iy1, s)
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy


def fbm(x, y, s, octaves=5, rough=0.5):
    """Noise of noises: big shapes, then smaller ones over them, each ``rough`` as strong as the last."""
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total += amp * value(x, y, s + o * 1013)
        norm += amp
        amp *= rough
        x, y = x * 2.03 + 17.1, y * 2.03 - 9.7
    return total / norm


class DepthRow(list):
    """A row of the picture that knows how far its land is: a write lands only where it is nearer
    (``view.cur_z``) than the ground already there."""
    __slots__ = ("depth", "view")

    def __setitem__(self, i, c):
        if self.depth[i] > self.view.cur_z:
            list.__setitem__(self, i, c)


BIOMES = [                                  # the default land: by height above the water, low to high
    {"name": "shore", "below": 0.05, "color": "#8c7c55", "color2": "#7a6c4a", "char": ","},
    {"name": "grass", "below": 0.35, "color": "#4c6a30", "color2": "#5d7a38", "char": "."},
    {"name": "forest", "below": 0.6, "color": "#2f4a26", "color2": "#3a5a2c", "char": "\""},
    {"name": "rock", "below": 0.85, "color": "#6b6660", "color2": "#5a5650", "char": "^"},
    {"name": "snow", "below": 9.0, "color": "#d8dde0", "color2": "#c4cbd0", "char": "*"},
]


class Biome:
    def __init__(self, spec, i):
        self.name = str(spec.get("name") or "land%d" % i)
        self.below = float(spec.get("below", 1.0))
        self.rgb = _colour(spec.get("color"), (90, 100, 70))
        self.rgb2 = _colour(spec.get("color2"), self.rgb)
        self.char = str(spec.get("char") or ".")[:1]
        self.toxic = bool(spec.get("toxic"))
        self.props = []
        for p in spec.get("props") or []:
            if isinstance(p, dict) and (p.get("sprite") or p.get("model")):
                self.props.append(p)
        self.density = sum(float(p.get("density", 0.05)) for p in self.props)


class Land:
    """The ground of an open level: heights, what grows where, and its picture."""
    Z0 = Z0

    def __init__(self, spec, seed=1):
        spec = spec if isinstance(spec, dict) else {}
        self.spec = spec
        size = spec.get("size") or [96, 96]
        self.w, self.h = int(size[0]), int(size[1])
        self.seed = int(spec.get("seed", seed if isinstance(seed, int) else 1)) & 0xFFFF
        self.scale = max(4.0, float(spec.get("scale", 40)))        # cells across a hill
        self.top = float(spec.get("height", 5.0))                 # the highest ground, in walls' heights
        self.sea = float(spec.get("sea", 0.3))                    # 0..1 of the heights: under it, water
        self.ridges = float(spec.get("ridges", 0.3))              # 0..1: how much of it is mountain ridges
        self.rough = float(spec.get("rough", 0.5))
        self.warp = float(spec.get("warp", 0.5))                  # 0..1: how far the shapes are twisted
        self.edge = spec.get("edge", "rim")                       # beyond the size: "rim" (hills rise), "open"
        self.climb = float(spec.get("climb", 0.55))               # steeper than this a cell, a walker cannot go
        self.view = float(spec.get("view", 150))                  # cells to the horizon
        self.see = float(spec.get("see", 24))                     # monsters and things are drawn this far
        self.props_view = float(spec.get("props_view", 18))
        self.vis = float(spec.get("haze", 70))                    # half the ground's colour is gone this far off
        self.altitude = float(spec.get("altitude", 2.6))          # a flying machine's eye above the ground
        water = spec.get("water") or {}
        self.water_rgb = _colour(water.get("color"), (40, 80, 90))
        self.deep_rgb = _colour(water.get("deep"), (18, 44, 56))
        self.water_toxic = bool(water.get("toxic"))
        self.shallow = float(water.get("shallow", 0.06))          # this far under the water line, a walker wades
        self.cliff_rgb = _colour(spec.get("cliff"), (92, 88, 82))
        self.biomes = [Biome(b, i) for i, b in enumerate(spec.get("biomes") or BIOMES) if isinstance(b, dict)]
        self.biomes.sort(key=lambda b: b.below)
        self.marks = [m for m in spec.get("landmarks") or [] if isinstance(m, dict) and isinstance(m.get("at"), list)]
        self.blocked = {(int(m["at"][0]), int(m["at"][1])) for m in self.marks if m.get("solid")}
        self.pads = []                                            # flattened ground: (x0, y0, x1, y1, height, blend)
        self.at = tuple(int(v) for v in (spec.get("at") or [0, 0])[:2])
        self.base = 0.0                                           # the height things are counted from (the pad's)
        self.stamp = {}                                           # (x, y) of a map cell -> its floor tile's rows
        try:
            self.numbers = json.dumps(spec, sort_keys=True, default=str)
        except (TypeError, ValueError):
            self.numbers = repr(id(spec))
        self.chunks = {}
        self.sun = (0.55, -0.45, 0.7)
        self.haze = (70, 70, 80)
        self.sea_h = self.sea * self.top
        self.share()

    # ---- the ground ------------------------------------------------------ #
    def share(self):
        """The chunks of a land with the same numbers, pads and sun: worked out once for all of them."""
        key = (self.numbers, tuple(self.pads), self.sun)
        ch = _SHARED.get(key)
        if ch is None:
            if len(_SHARED) > 6:
                _SHARED.clear()
            ch = _SHARED[key] = {}
        self.chunks = ch

    def raw(self, x, y):
        """The height at (x, y), 0..1 of ``top``, before pads and the edge."""
        s, sc = self.seed, self.scale
        u, v = x / sc, y / sc
        if self.warp:
            w = self.warp * 0.9
            u, v = (u + w * (fbm(u * 0.5, v * 0.5, s + 31, 3) - 0.5),
                    v + w * (fbm(u * 0.5 + 5.2, v * 0.5, s + 47, 3) - 0.5))
        base = fbm(u, v, s, 5, self.rough)
        if self.ridges:
            r = 1.0 - abs(2.0 * fbm(u * 0.8 + 3.1, v * 0.8, s + 91, 4, 0.5) - 1.0)
            base = base * (1 - self.ridges) + (r * r) * self.ridges
        return min(1.0, max(0.0, (base - 0.22) / 0.56))

    def set_pad(self, x0, y0, x1, y1, height=None, blend=6):
        """Flatten the ground of the cells x0..x1, y0..y1 (the map's), at ``height`` or the ground's middle,
        kept above the water, blended into the land over ``blend`` cells."""
        if height is None:
            height = self.raw((x0 + x1) / 2.0, (y0 + y1) / 2.0) * self.top
        height = max(height, self.sea_h + 0.25)
        self.pads.append((x0, y0, x1, y1, float(height), max(1.0, float(blend))))
        self.base = float(height)
        self.share()

    def surface(self, x, y):
        """The ground's height at a cell (pads and the edge counted), and whether it is under water."""
        h = self.raw(x, y) * self.top
        for x0, y0, x1, y1, ph, blend in self.pads:
            dx = max(x0 - x, 0, x - x1)
            dy = max(y0 - y, 0, y - y1)
            d = math.hypot(dx, dy)
            if d < blend:
                k = 1.0 - d / blend
                k = k * k * (3 - 2 * k)
                h = h + (ph - h) * k
        if self.edge == "rim":                                    # past the size, the land climbs into hills
            out = max(-x, x - (self.w - 1), -y, y - (self.h - 1), 0)
            inside = min(x, self.w - 1 - x, y, self.h - 1 - y)
            if out > 0 or inside < 3:                             # a ring of hills, then the land goes on
                rise = max(0.0, 3 - inside) * 0.6 + min(out, 10) * 0.35
                h += min(rise, 1.5 + self.top * 0.5) * (1.0 if out < 14 else max(0.0, 1.0 - (out - 14) / 10.0))
        return h

    def build(self, kx, ky):
        """The ground of one chunk: heights (the water's top where it is under), colours lit by the sun,
        which biome, how steep, and what stands there."""
        n = CHUNK
        x0, y0 = kx * n, ky * n
        raw = {}
        for y in range(y0 - 1, y0 + n + 1):
            for x in range(x0 - 1, x0 + n + 1):
                raw[(x, y)] = self.surface(x, y)
        heights, cols, kinds, steep, props = [], [], [], [], []
        sea, top = self.sea_h, max(0.01, self.top)
        lx, ly, lz = self.sun
        for y in range(y0, y0 + n):
            for x in range(x0, x0 + n):
                h = raw[(x, y)]
                gx = raw[(x + 1, y)] - raw[(x - 1, y)]
                gy = raw[(x, y + 1)] - raw[(x, y - 1)]
                slope = max(abs(raw[(x + 1, y)] - h), abs(raw[(x - 1, y)] - h), abs(raw[(x, y + 1)] - h),
                            abs(raw[(x, y - 1)] - h))
                if h < sea:                                       # water: flat, its colour by its depth
                    depth = (sea - h) / top
                    k = min(1.0, depth / max(0.01, self.shallow * 2))
                    heights.append(sea)
                    cols.append(mix(self.water_rgb, self.deep_rgb, k))
                    kinds.append(-2 if depth > self.shallow else -1)
                    steep.append(False)
                    props.append(None)
                    continue
                f = (h - sea) / max(0.01, top - sea)
                b = self.biomes[-1] if self.biomes else None
                bi = len(self.biomes) - 1
                for i, bb in enumerate(self.biomes):
                    if f < bb.below:
                        b, bi = bb, i
                        break
                vary = value(x / 3.0, y / 3.0, self.seed + 5)
                rgb = mix(b.rgb, b.rgb2, vary) if b else (90, 100, 70)
                cliff = slope > self.climb
                if cliff:
                    rgb = mix(rgb, self.cliff_rgb, 0.75)
                nl = math.sqrt(gx * gx + gy * gy + 4.0)
                lit = max(0.0, (-gx * lx - gy * ly + 2.0 * lz) / nl)
                light = 0.42 + 0.75 * lit
                heights.append(h)
                cols.append((min(255, int(rgb[0] * light)), min(255, int(rgb[1] * light)),
                             min(255, int(rgb[2] * light))))
                kinds.append(bi)
                steep.append(cliff)
                prop = None
                if b and b.props and not cliff:
                    r = _h(x, y, self.seed + 77)
                    acc = 0.0
                    for p in b.props:
                        acc += float(p.get("density", 0.05))
                        if r < acc:
                            prop = p
                            break
                props.append(prop)
        ch = (heights, cols, kinds, steep, props)
        self.chunks[(kx, ky)] = ch
        if len(self.chunks) > 600:                                # a long way travelled: forget the oldest
            for key in list(self.chunks)[:200]:
                del self.chunks[key]
            self.chunks[(kx, ky)] = ch
        return ch

    def chunk_of(self, x, y):
        key = (x >> 4, y >> 4)
        ch = self.chunks.get(key)
        return ch if ch is not None else self.build(*key)

    def at_cell(self, x, y):
        """(height, colour, biome index (-1 shallow water, -2 deep), steep, prop) of a cell."""
        ch = self.chunk_of(x, y)
        k = ((y & 15) << 4) | (x & 15)
        return ch[0][k], ch[1][k], ch[2][k], ch[3][k], ch[4][k]

    def height(self, x, y):
        return self.chunk_of(x, y)[0][((y & 15) << 4) | (x & 15)]

    def ground(self, x, y):
        """The ground under a point between cells (cells' middles are whole numbers), blended."""
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = x - x0, y - y0
        h00, h10 = self.height(x0, y0), self.height(x0 + 1, y0)
        h01, h11 = self.height(x0, y0 + 1), self.height(x0 + 1, y0 + 1)
        return (h00 * (1 - fx) + h10 * fx) * (1 - fy) + (h01 * (1 - fx) + h11 * fx) * fy

    def uses(self):
        """The sprites and the models the land's props and landmarks are drawn with."""
        pics, mdls = set(), set()
        for b in self.biomes:
            for p in b.props:
                pics.add(p.get("sprite"))
                mdls.add(p.get("model"))
        for m in self.marks:
            pics.add(m.get("sprite"))
            mdls.add(m.get("model"))
        return pics - {None}, mdls - {None}

    def biome_of(self, x, y):
        k = self.at_cell(x, y)[2]
        return "deep water" if k == -2 else "water" if k == -1 else self.biomes[k].name

    def cell_spec(self, x, y):
        """What the level's cell at (x, y) is: open to the sky; water (toxic, deep); steep; a prop that blocks."""
        h, _c, k, steep, prop = self.at_cell(x, y)
        spec = {"sky": True}
        if k < 0:
            spec["toxic"] = self.water_toxic
            if k == -2:
                spec["deep"] = True
        elif steep:
            spec["steep"] = True
        elif self.biomes[k].toxic:
            spec["toxic"] = True
        if (prop is not None and prop.get("solid")) or (x, y) in self.blocked:
            spec["steep"] = True                     # a tree, a rock, a mast: in the way on foot
        return spec

    def char(self, x, y):
        k = self.at_cell(x, y)[2]
        return "~" if k < 0 else self.biomes[k].char

    # ---- the picture ----------------------------------------------------- #
    def look(self, sky):
        """Light and haze from the level's sky: the sun's way lights the slopes, the horizon tints the far land."""
        if sky is None:
            return
        sun = sky.get("sun")
        if sun is not None:
            at, height = sun[0], sun[1]
            el = math.radians(15 + 60 * max(0.0, min(1.0, height)))
            az = 2 * math.pi * at
            new = (math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))
        else:
            new = (0.55, -0.45, 0.7)
        haze = _colour(self.spec.get("haze_color"), mix(sky["horizon"], sky["top"], 0.35))
        if new != self.sun:
            self.sun = new
            self.share()
        self.haze = haze

    def draw(self, view, cam, eye, phase, sky_rows, stamp_floor=None):
        """The sky and the ground as the player sees them, his eye ``eye`` above the pad's height: rows of the
        picture (``DepthRow``) that keep each pixel's distance."""
        PW, PH, yh, half = view.PW, view.PH, view.yh, view.half
        LW, TALL = view.LW, view.TALL
        cx, cy, fx, fy, rx, ry = cam
        ox, oy = cx - fx * Z0, cy - fy * Z0
        haze = self.haze
        hr, hg, hb = haze
        rows = [list(sky_rows[y]) if y < len(sky_rows) else [haze] * PW for y in range(PH)]
        depth = [[INF] * PW for _ in range(PH)]
        ybuf = [PH] * PW
        step = 2 if view.detail == "low" else 1
        cols = list(range(0, PW, step))
        offs = [x + step * 0.5 - half for x in cols]
        eye_abs = eye + self.base
        chunks, build = self.chunks, self.build
        stamp = self.stamp
        sx0, sy0 = self.at
        sx1, sy1 = sx0 + (stamp_floor or (0, 0))[0], sy0 + (stamp_floor or (0, 0))[1]
        D = Z0 * 0.8
        alive = len(cols)
        cover = view.cover
        while D < self.view and alive:
            tD = Z0 / D
            syk = TALL * tD
            inv = 1.0 / (LW * tD)
            bx, by = ox + fx * D, oy + fy * D
            z = D - Z0
            fogk = 1.0 - math.exp(-D / self.vis)
            keep = 1.0 - fogk
            near = D < 9.0
            for i, x in enumerate(cols):
                yb = ybuf[x]
                if yb <= 0:
                    continue
                o = offs[i] * inv
                wx, wy = bx + rx * o, by + ry * o
                ix = int(wx + 0.5) if wx >= -0.5 else int(wx + 0.5) - 1     # cells' middles are whole numbers
                iy = int(wy + 0.5) if wy >= -0.5 else int(wy + 0.5) - 1
                key = (ix >> 4, iy >> 4)
                ch = chunks.get(key)
                if ch is None:
                    ch = build(*key)
                k = ((iy & 15) << 4) | (ix & 15)
                kind = ch[2][k]
                if sx0 <= ix < sx1 and sy0 <= iy < sy1 and (ix, iy) in stamp:
                    h = self.base
                    tex = stamp[(ix, iy)]
                    if tex:
                        u, v = wx + 0.5 - ix, wy + 0.5 - iy
                        c = tex[min(len(tex) - 1, int(v * len(tex)))][min(len(tex[0]) - 1, int(u * len(tex[0])))]
                        col = c or (60, 60, 64)
                    else:
                        col = (70, 70, 74) if (ix + iy) % 2 else (62, 62, 66)
                else:
                    h = self.ground(wx + 0.5, wy + 0.5) if near and kind >= 0 else ch[0][k]
                    col = ch[1][k]
                    if near and kind >= 0:                              # close by, the ground has a grain
                        g = 0.9 + 0.2 * _h(int(wx * 4), int(wy * 4), 3)
                        col = (min(255, int(col[0] * g)), min(255, int(col[1] * g)), min(255, int(col[2] * g)))
                ytop = yh + (eye_abs - h) * syk
                it = int(ytop) if ytop >= 0 else -1
                if it < yb:
                    if kind < 0:                                        # water: the sky in it, and a glint
                        ym = 2 * yh - it
                        if 0 <= ym < yh:
                            col = mix(col, rows[ym][x], 0.35)
                        if _h(ix, iy, phase) < 0.05:
                            col = mix(col, (230, 230, 220), 0.4)
                    c = (int(col[0] * keep + hr * fogk), int(col[1] * keep + hg * fogk), int(col[2] * keep + hb * fogk))
                    top = it if it > 0 else 0
                    for yy in range(top, yb):
                        rr, dr = rows[yy], depth[yy]
                        rr[x] = c
                        dr[x] = z
                        if step == 2 and x + 1 < PW:
                            rr[x + 1] = c
                            dr[x + 1] = z
                    ybuf[x] = top
                    if top <= 0:
                        alive -= 1
            D = D * (1.02 if D < 12 else 1.035 if D < 50 else 1.05) + 0.02
        out = []
        sy = view.sy
        for y in range(PH):
            r = DepthRow(rows[y])
            r.depth, r.view = depth[y], view
            out.append(r)
            cy_ = y // sy
            dr = depth[y]
            for x in range(0, PW, view.sx * 2):                         # labels hide behind the hills
                d = dr[x]
                if d < INF:
                    key = (cy_, x // view.sx)
                    if d < cover.get(key, 99.0):
                        cover[key] = d
        return out

    def props_near(self, cx, cy, radius):
        """The props (reeds, rocks, trees...) of the cells within ``radius``: (x, y, prop)."""
        out = []
        r = int(radius)
        for y in range(int(cy) - r, int(cy) + r + 1):
            for x in range(int(cx) - r, int(cx) + r + 1):
                if (x, y) in self.stamp:
                    continue
                prop = self.at_cell(x, y)[4]
                if prop is not None:
                    out.append((x, y, prop))
        return out


def problems(spec, sprites, models, where="land"):
    """What is wrong with a level's ``"land"`` (for --check)."""
    out = []
    if not isinstance(spec, dict):
        return ["%s should be an object" % where]
    size = spec.get("size")
    if size is not None and not (isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) and 8 <= v <= 2048
                                                                                   for v in size)):
        out.append("%s: size should be [width, height], 8 to 2048 cells each" % where)
    for key in ("scale", "height", "sea", "ridges", "rough", "warp", "climb", "view", "see", "haze", "altitude"):
        if key in spec and not isinstance(spec[key], (int, float)):
            out.append("%s: %s should be a number" % (where, key))
    if spec.get("edge", "rim") not in ("rim", "open"):
        out.append("%s: edge should be \"rim\" or \"open\"" % where)
    for i, b in enumerate(spec.get("biomes") or []):
        if not isinstance(b, dict) or not isinstance(b.get("below", 1), (int, float)):
            out.append("%s: biome %d should be an object with a number \"below\"" % (where, i + 1))
            continue
        for p in b.get("props") or []:
            if not isinstance(p, dict):
                out.append("%s: biome '%s': a prop should be an object" % (where, b.get("name")))
            elif p.get("sprite") and p["sprite"] not in sprites:
                out.append("%s: biome '%s': no sprite '%s'" % (where, b.get("name"), p["sprite"]))
            elif p.get("model") and p["model"] not in models:
                out.append("%s: biome '%s': no model '%s'" % (where, b.get("name"), p["model"]))
    for m in spec.get("landmarks") or []:
        if not isinstance(m, dict) or not isinstance(m.get("at"), list) or len(m["at"]) != 2:
            out.append("%s: a landmark should be {\"at\": [x, y], \"model\": ...}" % where)
        elif m.get("model") and m["model"] not in models:
            out.append("%s: landmark: no model '%s'" % (where, m["model"]))
    for s in spec.get("scatter") or []:
        if not isinstance(s, dict) or not (s.get("monster") or s.get("item")):
            out.append("%s: a scatter should name a monster or an item" % where)
    return out
