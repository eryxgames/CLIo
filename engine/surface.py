# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Surfaces lit as the models are: the mesh view's walls, floors and ceilings with physically based materials.

A tile can say what it is made of (tiles.json)::

    "facade": {"pixels": [...], "palette": {...},
               "material": {"metal": 0.1, "rough": 0.15, "reflect": 0.25, "glow": "wW"}}

``metal`` 0..1 and ``rough`` 0..1 are glTF's metallic-roughness (as the models' materials); ``reflect`` 0..1
is how much of the room a floor of it mirrors (polish; water); ``glow`` names the palette's letters that give
light of their own (lit windows, screens, a lamp's tube): they are not darkened by the dark or by distance.
The engine's own tiles have materials of their own (steel is metal, screens glow).

When a level has light or weather (engine/atmosphere.py) the mesh view keeps, for every pixel, what it shows -
a floor, a ceiling, a wall turned which way, or a thing - and its material (a G-buffer), and ``shade`` lights
it: the level's ambient light, every lamp that sees the place by how it faces it (diffuse) and a GGX highlight
by its material (as model.pbr: Smith's shadowing, Schlick's Fresnel), glowing texels left glowing, dim
reflections in floors (what stands on them mirrored about where it stands, more at a grazing look - the
Fresnel term), floors under open sky wet in rain (they mirror more, rippled) and the rain's drops splashing on
them, then the fog of the weather by distance."""
from __future__ import annotations

import math

FLOOR, CEILING, WALL_PX, WALL_NX, WALL_PY, WALL_NY, THING = 1, 2, 3, 4, 5, 6, 7
NORMALS = {FLOOR: (0.0, 0.0, 1.0), CEILING: (0.0, 0.0, -1.0), WALL_PX: (1.0, 0.0, 0.0), WALL_NX: (-1.0, 0.0, 0.0),
           WALL_PY: (0.0, 1.0, 0.0), WALL_NY: (0.0, -1.0, 0.0)}
GLOW = 0x80                  # in a pixel's material byte: the texel gives light of its own
NO_SPEC = (0.0, 0.0, 0.0, 0.0)
NONE = 1e9
ENGINE = {"steel": {"metal": 0.75, "rough": 0.42}, "door": {"metal": 0.6, "rough": 0.5},
          "door_r": {"metal": 0.6, "rough": 0.5}, "door_w": {"metal": 0.6, "rough": 0.5},
          "door_x": {"metal": 0.6, "rough": 0.5}, "door_timed": {"metal": 0.6, "rough": 0.5},
          "door_oneway": {"metal": 0.6, "rough": 0.5}, "sealed": {"metal": 0.65, "rough": 0.4},
          "locker": {"metal": 0.55, "rough": 0.5}, "locker_open": {"metal": 0.55, "rough": 0.5},
          "bars": {"metal": 0.8, "rough": 0.35}, "hazard": {"metal": 0.3, "rough": 0.6},
          "screens": {"rough": 0.2, "glow_bright": 150}, "screens2": {"rough": 0.2, "glow_bright": 150},
          "exit": {"metal": 0.5, "rough": 0.4, "glow_bright": 190}, "exit_on": {"rough": 0.4, "glow_bright": 150},
          "switch": {"metal": 0.5, "rough": 0.45}, "switch_on": {"metal": 0.5, "rough": 0.45, "glow_bright": 170},
          "field": {"rough": 0.3, "glow_bright": 120}, "step": {"metal": 0.4, "rough": 0.6}}


class Material:
    __slots__ = ("name", "metal", "rough", "reflect", "glow")

    def __init__(self, name, spec, glow=frozenset()):
        spec = spec if isinstance(spec, dict) else {}
        self.name = name
        self.metal = _unit(spec.get("metal", 0.0))
        self.rough = max(0.05, _unit(spec.get("rough", 0.85)))
        self.reflect = _unit(spec.get("reflect", 0.0))
        self.glow = glow                     # the colours of the texels that glow


def _unit(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def materials_of(tiles_data, frames, engine_textures, extra=None):
    """The level's materials: a list (0: the plain default) and tile name -> index. ``tiles_data``: tiles.json;
    ``frames``: name -> drawings (for which colours glow); ``engine_textures``: the engine's drawings."""
    from .sprite import _rgb
    out = [Material("plain", {}), Material("ceiling", {"rough": 0.9}, frozenset([(168, 162, 122)]))]
    index = {}

    def bright(drawings, limit):
        return frozenset(c for d in drawings for r in d for c in r if c is not None and sum(c) / 3.0 >= limit)
    for name, spec in ENGINE.items():
        rows = engine_textures.get(name)
        glow = bright([rows], spec["glow_bright"]) if rows and "glow_bright" in spec else frozenset()
        index[name] = len(out)
        out.append(Material(name, spec, glow))
    for name, data in (tiles_data or {}).items():
        spec = data.get("material") if isinstance(data, dict) else None
        if not isinstance(spec, dict):
            if name in index:                        # a game's own tile of an engine's name: plain again
                del index[name]
            continue
        glow = frozenset()
        if isinstance(spec.get("glow"), str):
            pal = data.get("palette") or {}
            glow = frozenset(_rgb(pal[ch]) for ch in spec["glow"] if ch in pal)
        elif "glow_bright" in spec:
            glow = bright(frames.get(name) or [], spec["glow_bright"])
        index[name] = len(out)
        out.append(Material(name, spec, glow))
        if len(out) >= GLOW - 1:
            break
    return out, index


def problems(where, name, spec, palette):
    """What is wrong with a tile's "material", for --check."""
    out = []
    if not isinstance(spec, dict):
        return ["%s: tile '%s' material should be an object (metal, rough, reflect, glow)" % (where, name)]
    for k in ("metal", "rough", "reflect"):
        v = spec.get(k)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1):
            out.append("%s: tile '%s' material %s should be 0 to 1" % (where, name, k))
    g = spec.get("glow")
    if g is not None and (not isinstance(g, str) or any(ch not in (palette or {}) for ch in g)):
        out.append("%s: tile '%s' material glow should be letters of its palette" % (where, name))
    return out


# ---- light ------------------------------------------------------------------------------------------------ #
def ggx(n, l, v, rough, f0):
    """The highlight of a light from ``l`` seen from ``v`` on a surface facing ``n`` (all unit vectors): GGX
    distribution, Smith-Schlick shadowing, Schlick's Fresnel - as model.pbr's - times n.l."""
    nl = n[0] * l[0] + n[1] * l[1] + n[2] * l[2]
    nv = n[0] * v[0] + n[1] * v[1] + n[2] * v[2]
    if nl <= 0.0 or nv <= 0.0:
        return 0.0
    hx, hy, hz = l[0] + v[0], l[1] + v[1], l[2] + v[2]
    hn = math.sqrt(hx * hx + hy * hy + hz * hz) or 1.0
    nh = (n[0] * hx + n[1] * hy + n[2] * hz) / hn
    vh = (v[0] * hx + v[1] * hy + v[2] * hz) / hn
    a = max(0.002, rough * rough)
    a2 = a * a
    dd = nh * nh * (a2 - 1.0) + 1.0
    D = a2 / (math.pi * dd * dd)
    k = (rough + 1.0) ** 2 / 8.0
    G = (nl / (nl * (1.0 - k) + k)) * (nv / (nv * (1.0 - k) + k))
    F = f0 + (1.0 - f0) * (1.0 - max(0.0, vh)) ** 5
    return D * G * F / (4.0 * nl * nv + 1e-4) * nl


def lamp_at(lv, lamp):
    """Where a lamp's light comes from: up by the ceiling of its cell, on a wall three quarters up, a street
    lamp's head over the street."""
    c = lv.cell(lamp.x, lamp.y)
    top = lv.top_of(c) if hasattr(lv, "top_of") else c.height + 1.0
    if c.solid:
        h = c.height + 0.75
    elif c.sky:
        h = c.height + 1.6
    else:
        h = top - 0.15
    return (float(lamp.x), float(lamp.y), h)




class Shader:
    """One picture's lighting: what is worked out once per picture, and once per place, kind and material."""

    def __init__(self, lv, atm, cam, Z0, eye, t, mats):
        self.lv, self.mats = lv, mats
        cx, cy, fx, fy, rx, ry = cam
        self.cam = (cx - fx * Z0, cy - fy * Z0, eye)
        self.lamps = []
        if atm is not None and atm.lighting:
            a, tint, _p = atm.ambient(t)
            self.amb = (a * tint[0], a * tint[1], a * tint[2])
            for lp in atm.lamps:
                if lp.on(lv.events):
                    k = lp.level(t) * lp.power
                    if k > 0.0:
                        self.lamps.append((lp, lamp_at(lv, lp), k, atm.lamp_map(lp)))
        else:
            self.amb = (1.0, 1.0, 1.0)
        # the player's own light, as the models' key light: from the camera, a little up and to the left
        self.key = (self.cam[0] - rx * 0.3, self.cam[1] - ry * 0.3, eye + 0.35)
        self.memo, self.smemo = {}, {}

    def light(self, qx, qy, qh, kind, mi):
        """The lamps' diffuse light (rgb) at a place - in quarter cells, ``qh`` quarter heights - on a surface of
        ``kind`` and material ``mi``. Lamps light what they see, by how far across (as the cells' light) and by
        how the surface is turned to them."""
        key = (qx, qy, qh, kind, mi)
        got = self.memo.get(key)
        if got is not None:
            return got
        dr = dg = db = 0.0
        if self.lamps:
            px, py, ph = (qx + 0.5) / 4.0, (qy + 0.5) / 4.0, (qh + 0.5) / 4.0
            m = self.mats[mi] if mi < len(self.mats) else self.mats[0]
            n = NORMALS.get(kind) or self._view(px, py, ph)   # a thing: lit as if it faced the viewer
            cell = (int(math.floor(px + 0.5)), int(math.floor(py + 0.5)))
            for lp, (lx, ly, lh), power, lit in self.lamps:
                if not lit.get(cell):                         # the lamp does not see this place's cell
                    continue
                dx, dy, dh = lx - px, ly - py, lh - ph
                flat = math.sqrt(dx * dx + dy * dy)
                if flat >= lp.reach:
                    continue
                att = (1.0 - flat / lp.reach) ** 2 * power
                d = math.sqrt(flat * flat + dh * dh) or 1e-3
                nl = (n[0] * dx + n[1] * dy + n[2] * dh) / d
                k = att * (0.35 + 0.65 * max(0.0, nl)) * (1.0 - 0.55 * m.metal)
                dr += k * lp.colour[0]
                dg += k * lp.colour[1]
                db += k * lp.colour[2]
        q = 32.0
        got = self.memo[key] = (int(min(1.6, dr) * q) / q, int(min(1.6, dg) * q) / q, int(min(1.6, db) * q) / q)
        return got

    def model_light(self, c, mat, rgb, p, n, v):
        """A model's colour (``c``: model.pbr's, lit by the player's own light) in the level's light: times the
        ambient, and each lamp's light and highlight on it by its own normal ``n`` at ``p`` (x, y, height) -
        the models lit by the same lamps as the rooms. ``rgb``: its colour (linear 0..1)."""
        ar, ag, ab = self.amb
        r, g, b = c[0] * ar, c[1] * ag, c[2] * ab
        if self.lamps:
            from .model import _srgb
            cell = (int(math.floor(p[0] + 0.5)), int(math.floor(p[1] + 0.5)))
            metal, rough = mat.metal, mat.rough
            f0 = 0.04 + 0.6 * metal
            alb = [_srgb(min(1.0, max(0.0, x))) * 255.0 for x in rgb]
            for lp, (lx, ly, lh), power, lit in self.lamps:
                if not lit.get(cell):
                    continue
                dx, dy, dh = lx - p[0], ly - p[1], lh - p[2]
                flat = math.sqrt(dx * dx + dy * dy)
                if flat >= lp.reach:
                    continue
                att = (1.0 - flat / lp.reach) ** 2 * power
                d = math.sqrt(flat * flat + dh * dh) or 1e-3
                l = (dx / d, dy / d, dh / d)
                nl = n[0] * l[0] + n[1] * l[1] + n[2] * l[2]
                k = att * (0.35 + 0.65 * max(0.0, nl)) * (1.0 - 0.55 * metal)
                s = ggx(n, l, v, rough, f0) * att * 0.6
                col = lp.colour
                r += col[0] * (k * alb[0] + s * (255 * (1 - metal) + alb[0] * metal))
                g += col[1] * (k * alb[1] + s * (255 * (1 - metal) + alb[1] * metal))
                b += col[2] * (k * alb[2] + s * (255 * (1 - metal) + alb[2] * metal))
        if mat.glow:                                          # light of its own: not darkened
            r, g, b = max(r, c[0]), max(g, c[1]), max(b, c[2])
        return (min(255, int(r)), min(255, int(g)), min(255, int(b)))

    def _view(self, px, py, ph):
        ex, ey, eh = self.cam
        vx, vy, vh = ex - px, ey - py, eh - ph
        vn = math.sqrt(vx * vx + vy * vy + vh * vh) or 1.0
        return (vx / vn, vy / vn, vh / vn)

    def spec(self, sx, sy, sh, kind, mi, g=16):
        """Highlights at a place in 1/``g`` of a cell (finer than the light near by: a highlight is small): the
        lamps' (rgb) and the player's own light's - before the surface tints them (a metal's are its own
        colour)."""
        key = (sx, sy, sh, kind, mi, g)
        got = self.smemo.get(key)
        if got is not None:
            return got
        px, py, ph = (sx + 0.5) / g, (sy + 0.5) / g, (sh + 0.5) / g
        m = self.mats[mi] if mi < len(self.mats) else self.mats[0]
        v = self._view(px, py, ph)
        n = NORMALS[kind]
        f0 = 0.04 + 0.6 * m.metal
        sr = sg = sb = 0.0
        if self.lamps:
            cell = (int(math.floor(px + 0.5)), int(math.floor(py + 0.5)))
            for lp, (lx, ly, lh), power, lit in self.lamps:
                if not lit.get(cell):
                    continue
                dx, dy, dh = lx - px, ly - py, lh - ph
                flat = math.sqrt(dx * dx + dy * dy)
                if flat >= lp.reach:
                    continue
                att = (1.0 - flat / lp.reach) ** 2 * power
                d = math.sqrt(flat * flat + dh * dh) or 1e-3
                s = ggx(n, (dx / d, dy / d, dh / d), v, m.rough, f0) * att * 0.6
                if s > 0.0:
                    sr += s * lp.colour[0]
                    sg += s * lp.colour[1]
                    sb += s * lp.colour[2]
        kx, ky, kh = self.key
        dx, dy, dh = kx - px, ky - py, kh - ph
        d = math.sqrt(dx * dx + dy * dy + dh * dh) or 1e-3
        own = ggx(n, (dx / d, dy / d, dh / d), v, m.rough, f0) * 0.22
        q = 64.0
        got = self.smemo[key] = (int(min(2.0, sr) * q) / q, int(min(2.0, sg) * q) / q, int(min(2.0, sb) * q) / q,
                                 int(min(2.0, own) * q) / q)
        return got


def weather_of(atm, t):
    """(kind, amount, fog, fog colour lit, sky cover, lightning lift, sky darkening or None) for a picture."""
    if atm is None:
        return ("clear", 0.0, 0.0, (0, 0, 0), 0.0, 0.0, None)
    kind, amount, _wind, fog, fog_c = atm.sky(t) if atm.weather else ("clear", 0.0, 0.0, 0.0, (0, 0, 0))
    flash = atm.flash(int(t)) * max(0.0, 1.0 - (t - int(t)) * 3) if atm.weather else 0.0
    from .atmosphere import OVERCAST
    lv = atm.lv
    cover = OVERCAST.get(kind, 0.0) * (0.4 + 0.6 * amount) if atm.weather else 0.0
    if cover and hasattr(lv, "down_at") and lv.down_at(lv.player.x, lv.player.y) is not None:
        cover *= 0.4                                          # on a wall: half the "sky" is the city below
    sky_k = None
    if atm.lighting:
        a, tint, _p = atm.ambient(t)
        lit = (min(1.0, a * tint[0]), min(1.0, a * tint[1]), min(1.0, a * tint[2]))
        if atm.day:
            sky_k = lit
        fog_c = (int(fog_c[0] * lit[0]), int(fog_c[1] * lit[1]), int(fog_c[2] * lit[2]))
    return kind, amount, fog, fog_c, cover, flash * 128, sky_k


def shade(lv, atm, view, rows, depths, gbuf, cam, Z0, eye, t):
    """Lights the mesh view's picture by its G-buffer (``gbuf``: kinds, materials, the view's own light - flat
    bytearrays, a byte a pixel; see Mesh.draw), in place: surfaces by ambient, lamps and the player's own light
    with their materials' highlights, glowing texels as they are, floors' dim reflections (wet ones more,
    rippled in the rain), the weather's fog and lightning, then the rain's splashes. ``rows`` are lists."""
    from .mesh import FAR, FADE
    PW, PH = view.PW, view.PH
    gk, gm, gq = gbuf
    kind_w, amount, fog, fog_c, cover, lift, sky_k = weather_of(atm, t)
    mats = getattr(lv, "materials", None) or [Material("plain", {})]
    nm = len(mats)
    metal = [m.metal for m in mats]
    reflect = [m.reflect for m in mats]
    blurs = [0 if m.rough < 0.15 else 1 if m.rough < 0.5 else 2 for m in mats]
    shiny = [m.metal > 0.05 or m.rough < 0.6 for m in mats]
    tick = int(t * 8)
    sh = getattr(view, "shader", None) or Shader(lv, atm, cam, Z0, eye, t, mats)
    ar, ag, ab = sh.amb
    cx, cy, fx, fy, rx, ry = cam
    ex, ey = cx - fx * Z0, cy - fy * Z0
    lx, ly = view.LW * Z0, view.TALL * Z0
    half, yh = view.half, view.yh
    dirx = [fx + ((x + 0.5 - half) / lx) * rx for x in range(PW)]
    diry = [fy + ((x + 0.5 - half) / lx) * ry for x in range(PW)]
    d16, d8 = lx / 24.0, lx / 12.0                         # nearer than these a sixteenth (an eighth) of a cell
    raining = kind_w in ("rain", "storm") and amount > 0
    wet_sky = (0.15 + 0.2 * amount) if raining else 0.0
    spec = lv.spec if isinstance(lv.spec, dict) else {}
    wet_all = _unit(spec.get("wet", 0.0))
    mirrors = getattr(view, "detail", "high") != "low"
    floor_ = math.floor
    exp = math.exp
    sqrt = math.sqrt
    cell_at = lv.cell
    dist = {}
    done = {}
    wet_of = {}
    contact = [-1] * PW                                       # per column: the last row above that is not floor
    for y in range(PH):
        row, dep = rows[y], depths[y]
        base = y * PW
        sby = (y + 0.5 - yh) / ly
        for x in range(PW):
            i = base + x
            k = gk[i]
            if k != FLOOR:
                contact[x] = y
            z = dep[x]
            c = row[x]
            if k == 0 or z >= NONE:                           # the sky (or what nothing covers)
                if sky_k is None and not cover and not lift:
                    continue
                key = (c, None)
                v = done.get(key)
                if v is None:
                    r, g, b = c
                    if sky_k is not None:
                        r, g, b = r * sky_k[0], g * sky_k[1], b * sky_k[2]
                    if cover:
                        r += (fog_c[0] - r) * cover
                        g += (fog_c[1] - g) * cover
                        b += (fog_c[2] - b) * cover
                    v = done[key] = (min(255, int(r + lift)), min(255, int(g + lift)), min(255, int(b + lift)))
                row[x] = v
                continue
            zq = int(z * 4) if z > 0 else 0
            fz = dist.get(zq)
            if fz is None:
                fade = (FAR - zq / 4.0) / FADE
                fz = dist[zq] = (int((1.0 - exp(-zq / 4.0 * fog)) * 32) / 32.0 if fog else 0.0,
                                 0.0 if fade < 0.0 else 1.0 if fade > 1.0 else fade)
            fk, fade = fz
            m = gm[i]
            mi = m & 0x7F
            if mi >= nm:
                mi = 0
            d = z + Z0
            wx, wy = ex + d * dirx[x], ey + d * diry[x]
            h = eye - sby * d
            if k == FLOOR or k == CEILING:
                hq = 0
            else:                                             # a wall's light is its room's: a hair towards it
                if k != THING:
                    n = NORMALS[k]
                    wx += n[0] * 0.05
                    wy += n[1] * 0.05
                hq = h
            dl = sh.light(int(floor_(wx * 4)), int(floor_(wy * 4)), int(floor_(hq * 4)), k, mi)
            if shiny[mi] and k != THING and not m & GLOW:      # as fine as the pixels there are
                g = 16 if d < d16 else 8 if d < d8 else 4
                sp = sh.spec(int(floor_(wx * g)), int(floor_(wy * g)), int(floor_(hq * g)), k, mi, g)
            else:
                sp = NO_SPEC
            refl = None
            if k == FLOOR and mirrors and contact[x] >= 0:   # a floor mirrors what stands on it - dim
                cell = (int(floor_(wx + 0.5)), int(floor_(wy + 0.5)), mi)
                wet = wet_of.get(cell)
                if wet is None:
                    cc = cell_at(cell[0], cell[1])
                    wet = wet_of[cell] = 0.0 if cc is None else min(0.9, reflect[mi] + wet_all +
                                                                     (wet_sky if cc.sky else 0.0))
                if wet > 0.0:
                    sy = 2 * contact[x] + 1 - y               # mirrored about where the floor meets what stands
                    if 0 <= sy < y:
                        sx = x
                        if raining and wet > reflect[mi]:     # rain on the puddles: the image trembles
                            jig = ((x >> 1) * 7919 + y * 104729 + tick * 1299709) % 10
                            sx += -1 if jig < 2 else 1 if jig > 7 else 0
                            sx = 0 if sx < 0 else PW - 1 if sx >= PW else sx
                        cos_t = (eye - h) / sqrt(d * d + (eye - h) ** 2)
                        fres = 0.04 + 0.96 * (1.0 - cos_t) ** 5        # more at a grazing look (Schlick)
                        w = min(0.4, wet * (0.3 + 0.7 * fres))
                        if w >= 1 / 32.0:
                            src = rows[sy][sx]
                            blur = blurs[mi]                  # a rough floor smears it down, as wet streets do
                            if blur and sy + blur < y:
                                a2, b2 = rows[sy - blur][sx] if sy >= blur else src, rows[sy + blur][sx]
                                src = ((src[0] * 2 + a2[0] + b2[0]) >> 2, (src[1] * 2 + a2[1] + b2[1]) >> 2,
                                       (src[2] * 2 + a2[2] + b2[2]) >> 2)
                            refl = (src, int(w * 32) / 32.0)
            q = gq[i] if k != THING else 256
            key = (c, q, dl, sp, fz, m & GLOW, mi, refl)
            v = done.get(key)
            if v is None:
                if m & GLOW:                                  # it gives its own light
                    r, g, b = c
                    lit_ = 1.0
                else:
                    a = q / 256.0
                    lr, lg, lb = a * ar + fade * dl[0], a * ag + fade * dl[1], a * ab + fade * dl[2]
                    r, g, b = c[0] * lr, c[1] * lg, c[2] * lb
                    lit_ = max(lr, lg, lb)
                    own = a * sp[3]
                    s0, s1, s2 = fade * sp[0] + own, fade * sp[1] + own, fade * sp[2] + own
                    if s0 or s1 or s2:                        # highlights: white off paint, a metal's own colour
                        mt = metal[mi]
                        r += s0 * (255 * (1 - mt) + min(255, c[0] * 1.4) * mt)
                        g += s1 * (255 * (1 - mt) + min(255, c[1] * 1.4) * mt)
                        b += s2 * (255 * (1 - mt) + min(255, c[2] * 1.4) * mt)
                if refl is not None:
                    s, w = refl
                    r += (s[0] - r) * w
                    g += (s[1] - g) * w
                    b += (s[2] - b) * w
                r, g, b = r + lift, g + lift, b + lift
                if fk:                                        # the fog, as bright as the light it is in
                    lit_ = min(1.0, lit_)
                    r += (fog_c[0] * lit_ - r) * fk
                    g += (fog_c[1] * lit_ - g) * fk
                    b += (fog_c[2] * lit_ - b) * fk
                v = done[key] = (min(255, max(0, int(r))), min(255, max(0, int(g))), min(255, max(0, int(b))))
            row[x] = v
    if raining and mirrors:
        splashes(lv, view, rows, depths, gk, cam, Z0, eye, t, amount)


def splashes(lv, view, rows, depths, kinds, cam, Z0, eye, t, amount):
    """Raindrops striking the ground near the player where it is open to the sky: each a short crown - a
    bright point, then a ring spreading flat and fading - at a place and a moment of its own (the same for the
    same beat). ``kinds``: the G-buffer's kinds (a flat bytearray), or None in open land."""
    PW, PH = view.PW, view.PH
    cx, cy, fx, fy, rx, ry = cam
    ex, ey = cx - fx * Z0, cy - fy * Z0
    lx, ly = view.LW * Z0, view.TALL * Z0
    half, yh = view.half, view.yh
    p = lv.player
    land = getattr(lv, "land", None)
    now = t * 6.0                                             # six moments a beat; a crown lasts two
    slot = int(floor(now))
    count = int(70 * amount)
    for s in (slot, slot - 1):
        age = (now - s) / 2.0
        if not 0.0 <= age < 1.0:
            continue
        for i in range(count):
            wx = p.x + (_h(i, s, 1) - 0.5) * 14.0
            wy = p.y + (_h(i, s, 2) - 0.5) * 14.0
            if land is None:
                c = lv.cell(int(floor(wx + 0.5)), int(floor(wy + 0.5)))
                if c is None or not getattr(c, "sky", False) or c.solid:
                    continue
                gh = float(getattr(c, "height", 0.0) or 0.0)
            else:
                gh = lv.ground(wx, wy)
            dx, dy = wx - ex, wy - ey
            d = dx * fx + dy * fy
            if d <= Z0 * 0.6:
                continue
            x = int(floor(half + (dx * rx + dy * ry) * lx / d))
            y = int(floor(yh + (eye - gh) * ly / d))
            if not (0 <= x < PW and 0 <= y < PH):
                continue
            z = d - Z0
            if abs(depths[y][x] - z) > 0.3 + 0.06 * abs(z) or (kinds is not None and kinds[y * PW + x] != FLOOR):
                continue                                      # something nearer stands there
            row = rows[y]
            k = (1.0 - age) * 0.75
            if age < 0.3:                                     # the strike
                row[x] = _caught(row[x], k)
                if y > 0 and age < 0.15 and (kinds is None or kinds[(y - 1) * PW + x] == FLOOR):
                    rows[y - 1][x] = _caught(rows[y - 1][x], k * 0.6)
            r = 1 + int(age * 3.0 * min(1.5, 4.0 / d))        # the ring, flat: across, not up
            for xx in (x - r, x + r):
                if 0 <= xx < PW and (kinds is None or kinds[y * PW + xx] == FLOOR):
                    row[xx] = _caught(row[xx], k * 0.55)


def floor(v):
    return math.floor(v)


def _caught(c, k):
    """A drop's water catching the light there: brighter, a little blue."""
    r, g, b = c
    return (int(r + (min(255, r * 1.6 + 50) - r) * k), int(g + (min(255, g * 1.6 + 56) - g) * k),
            int(b + (min(255, b * 1.7 + 66) - b) * k))


def _h(*k):
    """0..1, the same for the same numbers."""
    h = 2166136261
    for v in k:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    return (h & 0xFFFFFF) / float(0x1000000)


class GRow(list):
    """A row of the mesh view's picture with its G-buffer: as land.DepthRow, a write lands only where it is
    nearer (``view.cur_z``) than what is there (or as near: the same thing again) - and then it is a thing
    (sprites, models, shots) at that distance, glowing while ``view.cur_glow``."""
    __slots__ = ("depth", "view", "gbuf", "base")

    def __setitem__(self, i, c):
        view = self.view
        z = view.cur_z
        if not view.cur_thing:                               # a mark on what is there: as DepthRow
            if self.depth[i] > z:
                list.__setitem__(self, i, c)
            return
        if self.depth[i] >= z:                               # a thing's own pixels over each other: all of it
            list.__setitem__(self, i, c)
            j = self.base + i
            gk, gm, gq = self.gbuf
            if z > -1e8:
                self.depth[i] = z
            gk[j] = THING
            gm[j] = GLOW if view.cur_glow else 0


def lit(lv, atm, view, px, cam, t):
    """The mesh view's picture (GRow rows, with ``view.gbuf``) lit, then the weather's rain or snow in the air:
    plain rows."""
    from .mesh import Z0 as MZ0
    Z0 = view.persp or MZ0
    rows = [list(r) for r in px]
    depths = [r.depth for r in px]
    shade(lv, atm, view, rows, depths, view.gbuf, cam, Z0, view.EYE, t)
    if atm is not None and atm.weather:
        kind, amount, wind, _fog, _c = atm.sky(t)
        if kind in ("rain", "storm", "snow", "dust") and amount > 0:
            cx, cy, fx, fy, rx, ry = cam
            lx, half = view.LW * Z0, view.half
            dirx = [fx + ((x + 0.5 - half) / lx) * rx for x in range(view.PW)]
            diry = [fy + ((x + 0.5 - half) / lx) * ry for x in range(view.PW)]
            atm.fall(view, rows, depths, (cx - fx * Z0, cy - fy * Z0, dirx, diry, Z0, rx, ry), t, kind, amount, wind)
    return rows


def lit_frame(lv, atm, view, px, cam, t):
    """As lit, in CLIo Picture's frame (0.8): the picture stays there. If the library will not, the Python lights
    it (plain rows then)."""
    from .mesh import Z0 as MZ0
    fr = px.frame
    Z0 = view.persp or MZ0
    s = frame_surface(lv, atm, view, fr, cam, t, Z0)
    PW, PH = view.PW, view.PH
    if s is not None and fr.surface(s):
        rows = px
        depths = [fr.depth[y * PW:(y + 1) * PW] for y in range(PH)]
    else:
        rows = fr.lists()
        depths = [fr.depth[y * PW:(y + 1) * PW] for y in range(PH)]
        shade(lv, atm, view, rows, depths, view.gbuf, cam, Z0, view.EYE, t)
    fr.more_off()
    view.cur_z = -1e9
    if atm is not None and atm.weather:
        kind, amount, wind, _fog, _c = atm.sky(t)
        if kind in ("rain", "storm", "snow", "dust") and amount > 0:
            cx, cy, fx, fy, rx, ry = cam
            lx, half = view.LW * Z0, view.half
            dirx = [fx + ((x + 0.5 - half) / lx) * rx for x in range(PW)]
            diry = [fy + ((x + 0.5 - half) / lx) * ry for x in range(PW)]
            atm.fall(view, rows, depths, (cx - fx * Z0, cy - fy * Z0, dirx, diry, Z0, rx, ry), t, kind, amount, wind)
    return rows


def numbers(lv, atm, view, cam, t, Z0, box=None):
    """What shade() works from, as plain numbers (clio_surface's, in its order): a dict - and the lamps, each
    (x, y, h, r, g, b, reach, k, lit x0, lit y0, lit w, lit h, lit bytes), the cells' window (x0, y0, w, h, flags,
    heights). ``box``: the floors' cells (x0, y0, x1, y1), where floors may mirror. None without a shader."""
    from .mesh import FAR, FADE
    sh = getattr(view, "shader", None)
    if sh is None:
        return None
    kind_w, amount, fog, fog_c, cover, lift, sky_k = weather_of(atm, t)
    mats = getattr(lv, "materials", None) or [Material("plain", {})]
    raining = kind_w in ("rain", "storm") and amount > 0
    spec = lv.spec if isinstance(lv.spec, dict) else {}
    bits = atm.__dict__.setdefault("_bits", {}) if atm is not None else {}
    lamps = []
    for lp, (lx, ly, lh), k, seen in sh.lamps:
        got = bits.get(id(lp))
        if got is None:
            if seen:
                xs, ys = [c[0] for c in seen], [c[1] for c in seen]
                x0, y0, w, h = min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            else:
                x0 = y0 = 0
                w = h = 1
            buf = bytearray(w * h)
            for (cx_, cy_), v in seen.items():
                if v:
                    buf[(cy_ - y0) * w + (cx_ - x0)] = 1
            got = bits[id(lp)] = (x0, y0, w, h, buf)
        lamps.append((lx, ly, lh, lp.colour[0], lp.colour[1], lp.colour[2], lp.reach, k) + got)
    p = lv.player
    x0, y0, x1, y1 = (p.x - 8, p.y - 8, p.x + 8, p.y + 8)
    if box is not None:
        x0, y0, x1, y1 = min(x0, box[0]), min(y0, box[1]), max(x1, box[2]), max(y1, box[3])
    w, h = x1 - x0 + 1, y1 - y0 + 1
    flags, heights = bytearray(w * h), [0.0] * (w * h)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            c = lv.cell(x, y)
            if c is not None:
                i = (y - y0) * w + (x - x0)
                flags[i] = (2 if getattr(c, "sky", False) else 1) | (4 if c.solid else 0)
                heights[i] = float(getattr(c, "height", 0.0) or 0.0)
    cx, cy, fx, fy, rx, ry = cam
    out = {"pw": view.PW, "ph": view.PH, "half": float(view.half), "yh": float(view.yh), "lx": view.LW * Z0,
           "ly": view.TALL * Z0, "cx": float(cx), "cy": float(cy), "fx": float(fx), "fy": float(fy), "rx": float(rx),
           "ry": float(ry), "z0": float(Z0), "eye": float(view.EYE), "far": float(FAR), "fade": float(FADE),
           "none": NONE, "t": float(t), "amb": tuple(sh.amb), "key": tuple(sh.key),
           "metal": [m.metal for m in mats], "rough": [m.rough for m in mats], "reflect": [m.reflect for m in mats],
           "fog": float(fog), "cover": float(cover), "lift": float(lift), "amount": float(amount),
           "wet_sky": (0.15 + 0.2 * amount) if raining else 0.0, "wet_all": _unit(spec.get("wet", 0.0)),
           "fog_rgb": tuple(float(v) for v in fog_c), "has_sky_k": 0 if sky_k is None else 1,
           "sky_k": tuple(sky_k or (0.0, 0.0, 0.0)), "raining": 1 if raining else 0,
           "mirrors": 0 if getattr(view, "detail", "high") == "low" else 1, "px": float(p.x), "py": float(p.y)}
    return out, lamps, (x0, y0, w, h, flags, heights)


def frame_surface(lv, atm, view, fr, cam, t, Z0):
    """clio_surface for this picture (None if it cannot be said)."""
    try:
        import ctypes
        from array import array
        from .picture import _Lamp, _Surface, _ptr
    except ImportError:                                       # pragma: no cover
        return None
    got = numbers(lv, atm, view, cam, t, Z0, getattr(fr, "cells_box", None))
    if got is None:
        return None
    n, lamps_, (x0, y0, w, h, flags, heights) = got
    held = []
    lamps = (_Lamp * max(1, len(lamps_)))()
    for i, lp in enumerate(lamps_):
        buf = lp[12]
        arr = (ctypes.c_uint8 * len(buf)).from_buffer(buf)
        held.append(arr)
        lamps[i] = _Lamp(*(lp[:12] + (ctypes.addressof(arr),)))
    cells = (ctypes.c_uint8 * len(flags)).from_buffer(flags)
    heights = array("d", heights)
    metal, rough, reflect = array("d", n["metal"]), array("d", n["rough"]), array("d", n["reflect"])
    held += [flags, heights, cells, metal, rough, reflect, lamps]
    D3 = ctypes.c_double * 3
    s = _Surface(n["pw"], n["ph"], n["half"], n["yh"], n["lx"], n["ly"], n["cx"], n["cy"], n["fx"], n["fy"],
                 n["rx"], n["ry"], n["z0"], n["eye"], n["far"], n["fade"], n["none"], n["t"], D3(*n["amb"]),
                 len(lamps_), ctypes.addressof(lamps), D3(*n["key"]), len(n["metal"]), _ptr(metal), _ptr(rough),
                 _ptr(reflect), n["fog"], n["cover"], n["lift"], n["amount"], n["wet_sky"], n["wet_all"],
                 D3(*n["fog_rgb"]), n["has_sky_k"], D3(*n["sky_k"]), n["raining"], n["mirrors"], n["px"], n["py"],
                 x0, y0, w, h, ctypes.addressof(cells), _ptr(heights))
    s._held = held
    return s
