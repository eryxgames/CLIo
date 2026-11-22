# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Light and weather in first-person levels: how lit a place is, lamps, and the sky's rain, snow and fog.

A level's ``"lights"``::

    "lights": {"ambient": 0.55, "tint": [200, 210, 255],
               "day": {"beats": 240, "start": 0.3},
               "events": {"alarm": {"ambient": 0.35, "tint": [255, 70, 50], "pulse": 0.5}}}

and lamps on map cells (``"lamp": {"colour": [255, 200, 140], "reach": 4, "power": 1.0, "flicker": 0.3,
"pulse": 0, "off": false, "on_on": event, "off_on": event}``, or ``"lamp": true``). A level's ``"weather"``::

    "weather": {"kind": "rain", "amount": 0.6, "wind": 0.3, "fog": 0.04, "fog_colour": [150, 160, 170],
                "cycle": [{"beats": 40, "kind": "clear"}, {"beats": 30, "kind": "storm", "amount": 1}],
                "events": {"purge": {"kind": "fog", "fog": 0.25, "fog_colour": [190, 200, 170]}}}

Kinds: clear, rain, storm (rain, wind and lightning), snow, fog, dust. Everything is worked out from the
level's beat and the events it has had, so a save needs nothing of its own and a replay sees the same.

The picture: where it keeps each pixel's distance (the mesh view, open land) each pixel is lit by the light
of the cell it shows and fogged by its distance, and rain and snow fall in front of what is further than
them, only over cells open to the sky. The classic picture is lit as a whole by the light where the player
stands. Sight: fog shortens it, both ways; in the dark (under 0.22) a monster more than two cells off is not
seen, unless the player wears the goggles."""
from __future__ import annotations

import math

KINDS = ("clear", "rain", "storm", "snow", "fog", "dust")
FOG = {"clear": 0.0, "rain": 0.035, "storm": 0.05, "snow": 0.045, "fog": 0.14, "dust": 0.09}   # each kind's own
FOG_COLOUR = {"clear": (150, 160, 170), "rain": (120, 130, 140), "storm": (90, 96, 108), "snow": (205, 210, 220),
              "fog": (170, 176, 182), "dust": (176, 140, 96)}
OVERCAST = {"rain": 0.75, "storm": 0.9, "snow": 0.8, "fog": 0.95, "dust": 0.8}   # how much the sky is clouded
DARK = 0.22                  # under this light a monster further than DARK_SIGHT is not seen
DARK_SIGHT = 2
NONE = 1e9


def _rgb(v, default):
    try:
        r, g, b = (max(0, min(255, int(c))) for c in v)
        return r, g, b
    except (TypeError, ValueError):
        return default


def _hash(*k):
    """0..1, the same for the same numbers."""
    h = 2166136261
    for v in k:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    return (h & 0xFFFFFF) / float(0x1000000)


class Lamp:
    __slots__ = ("x", "y", "colour", "reach", "power", "flicker", "pulse", "off", "on_on", "off_on", "lit")

    def __init__(self, x, y, spec):
        spec = spec if isinstance(spec, dict) else {}
        self.x, self.y = x, y
        c = _rgb(spec.get("colour"), (255, 214, 160))
        self.colour = (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)
        self.reach = max(1.0, float(spec.get("reach", 4)))
        self.power = max(0.0, float(spec.get("power", 1.0)))
        self.flicker = max(0.0, min(1.0, float(spec.get("flicker", 0.0))))
        self.pulse = max(0.0, float(spec.get("pulse", 0.0)))
        self.off = bool(spec.get("off"))
        self.on_on, self.off_on = spec.get("on_on"), spec.get("off_on")
        self.lit = None              # (x, y) -> how much of its light reaches the cell (0..1), worked out once

    def on(self, events):
        on = not self.off
        if self.off_on and self.off_on in events:
            on = False
        if self.on_on and self.on_on in events:
            on = True
        return on

    def level(self, t):
        k = 1.0
        if self.flicker:                                   # a bad tube: dips, a few times a beat
            k *= 1.0 - self.flicker * (1.0 if _hash(self.x, self.y, int(t * 7)) < 0.3 else 0.25 *
                                       _hash(self.y, self.x, int(t * 7)))
        if self.pulse:
            k *= 0.55 + 0.45 * math.cos(2 * math.pi * self.pulse * t)
        return k


class Atmosphere:
    """A level's light and weather, as they are at a beat (and a moment of it)."""

    def __init__(self, lv):
        self.lv = lv
        spec = lv.spec.get("lights") if isinstance(lv.spec.get("lights"), dict) else {}
        self.spec = spec
        self.ambient0 = float(spec.get("ambient", 1.0))
        self.tint0 = _rgb(spec.get("tint"), (255, 255, 255))
        day = spec.get("day") if isinstance(spec.get("day"), dict) else None
        self.day = (max(8, int(day.get("beats", 240))), float(day.get("start", 0.3))) if day else None
        self.light_events = spec.get("events") if isinstance(spec.get("events"), dict) else {}
        self.lamps = []
        for row in ([] if getattr(lv, "world", None) is not None else lv.grid):   # a world: no lamps of the map
            for c in row:
                sp = getattr(c, "lamp", None)
                if sp:
                    self.lamps.append(Lamp(c.x, c.y, sp))
        w = lv.spec.get("weather") if isinstance(lv.spec.get("weather"), dict) else None
        self.weather = w or {}
        self.lighting = bool(spec) or bool(self.lamps)
        self._key = None
        self._cells = {}

    @staticmethod
    def wanted(lv):
        if isinstance(lv.spec.get("lights"), dict) or isinstance(lv.spec.get("weather"), dict):
            return True
        return getattr(lv, "world", None) is None and any(getattr(c, "lamp", None) for row in lv.grid for c in row)

    # ---- light ---------------------------------------------------------------------------------------- #
    def ambient(self, t):
        """(level, (r, g, b) 0..1, pulse) of the light everywhere at time ``t`` (beats)."""
        a, tint, pulse = self.ambient0, self.tint0, 0.0
        events = self.lv.events
        for name, ch in self.light_events.items():           # in the order the level lists them
            if name in events and isinstance(ch, dict):
                a = float(ch.get("ambient", a))
                tint = _rgb(ch.get("tint"), tint)
                pulse = float(ch.get("pulse", pulse))
        if self.day:                                          # the sun: 0 dawn, 0.25 noon, 0.5 dusk, 0.75 midnight
            beats, start = self.day
            k = math.sin(2 * math.pi * ((t / beats + start) % 1.0))
            sun = 0.24 + 0.76 * max(0.0, k) ** 0.6             # the night: moonlight, a quarter
            low = max(0.0, 1.0 - abs(k) * 3)                 # dawn and dusk: warm
            a *= sun
            if k < 0:                                         # the night: blue
                tint = (int(tint[0] * 0.7), int(tint[1] * 0.8), tint[2])
            tint = (tint[0], int(tint[1] * (1 - 0.25 * low)), int(tint[2] * (1 - 0.45 * low)))
        if pulse:
            a *= 0.6 + 0.4 * math.cos(2 * math.pi * pulse * t)
        return a, (tint[0] / 255.0, tint[1] / 255.0, tint[2] / 255.0), pulse

    def lamp_map(self, lamp):
        if lamp.lit is None:
            lv = self.lv
            lit = {}
            R = int(math.ceil(lamp.reach))
            for y in range(lamp.y - R, lamp.y + R + 1):
                for x in range(lamp.x - R, lamp.x + R + 1):
                    d = math.hypot(x - lamp.x, y - lamp.y)
                    if d >= lamp.reach:
                        continue
                    c = lv.cell(x, y)
                    if c is None or c.solid:                  # a wall shows its room's light
                        continue
                    if (x, y) == (lamp.x, lamp.y) or lv.line_of_sight(lamp.x, lamp.y, x, y):
                        k = 1.0 - d / lamp.reach
                        lit[(x, y)] = k * k
            lamp.lit = lit
        return lamp.lit

    def begin(self, t):
        """The light of each cell for a picture at time ``t``: worked out as cells are asked for."""
        a, tint, _p = self.ambient(t)
        events = self.lv.events
        on = [(lp, lp.level(t)) for lp in self.lamps if lp.on(events)]
        self._base = (a * tint[0], a * tint[1], a * tint[2])
        self._on = on
        self._cells = {}

    def at(self, x, y):
        """(r, g, b) multipliers of the light in cell (x, y) - after ``begin``."""
        got = self._cells.get((x, y))
        if got is None:
            r, g, b = self._base
            for lp, k in self._on:
                w = self.lamp_map(lp).get((x, y))
                if w:
                    w *= lp.power * k
                    r += w * lp.colour[0]
                    g += w * lp.colour[1]
                    b += w * lp.colour[2]
            got = self._cells[(x, y)] = (min(1.6, r), min(1.6, g), min(1.6, b))
        return got

    def blend(self, wx, wy):
        """The light at a point between cells' middles (whole numbers): the four round it, by nearness - the
        open ones only, so a wall does not darken the floor beside it. In steps of 1/32."""
        x0, y0 = int(math.floor(wx)), int(math.floor(wy))
        ux, uy = wx - x0, wy - y0
        r = g = b = w = 0.0
        cell = self.lv.cell
        for x, y, k in ((x0, y0, (1 - ux) * (1 - uy)), (x0 + 1, y0, ux * (1 - uy)), (x0, y0 + 1, (1 - ux) * uy),
                        (x0 + 1, y0 + 1, ux * uy)):
            if k <= 0.0:
                continue
            c = cell(x, y)
            if c is None or c.solid:
                continue
            f = self.at(x, y)
            r += f[0] * k
            g += f[1] * k
            b += f[2] * k
            w += k
        if w <= 0.0:
            return self.at(int(math.floor(wx + 0.5)), int(math.floor(wy + 0.5)))
        return (int(r / w * 32) / 32.0, int(g / w * 32) / 32.0, int(b / w * 32) / 32.0)

    def light_here(self, x, y, t=None):
        """How lit cell (x, y) is now, 0..1.6 (its brightest channel)."""
        self.begin(self.lv.beat if t is None else t)
        return max(self.at(x, y))

    # ---- weather -------------------------------------------------------------------------------------- #
    def sky(self, t):
        """(kind, amount, wind, fog density, fog colour) of the weather at time ``t``."""
        w = self.weather
        kind = w.get("kind", "clear")
        state = dict(w)
        cycle = w.get("cycle") if isinstance(w.get("cycle"), list) else None
        if cycle:
            total = sum(max(1, int(s.get("beats", 30))) for s in cycle if isinstance(s, dict))
            if total:
                at = int(t) % total
                for s in cycle:
                    if not isinstance(s, dict):
                        continue
                    n = max(1, int(s.get("beats", 30)))
                    if at < n:
                        state.update(s)
                        kind = s.get("kind", kind)
                        break
                    at -= n
        evs = w.get("events") if isinstance(w.get("events"), dict) else {}
        for name, ch in evs.items():
            if name in self.lv.events and isinstance(ch, dict):
                state.update(ch)
                kind = ch.get("kind", kind)
        kind = kind if kind in KINDS else "clear"
        amount = max(0.0, min(1.0, float(state.get("amount", 0.6))))
        fog = float(state["fog"]) if "fog" in state else FOG[kind] * (0.5 + amount)
        colour = _rgb(state.get("fog_colour"), FOG_COLOUR[kind])
        wind = float(state.get("wind", 0.5 if kind in ("storm", "dust") else 0.15))
        return kind, amount, wind, max(0.0, fog), colour

    def sight(self, t=None):
        """How many cells one sees through the fog (None: no limit worth saying)."""
        if not self.weather:
            return None
        fog = self.sky(self.lv.beat if t is None else t)[3]
        return None if fog < 0.08 else max(3, int(2.2 / fog))

    def flash(self, beat):
        """Lightning on this beat (a storm): how bright, 0 if none."""
        if not self.weather:
            return 0.0
        kind, amount = self.sky(beat)[:2]
        if kind != "storm":
            return 0.0
        return 0.55 if _hash(beat, 911) < 0.12 * (0.5 + amount) else 0.0

    # ---- the picture ---------------------------------------------------------------------------------- #
    def apply(self, view, px, cam, t, depth_known):
        """Light, fog and rain on a picture before the hands are drawn. Returns the picture (plain rows when
        it had to leave CLIo Picture's frame)."""
        lv = self.lv
        kind, amount, wind, fog, fog_c = self.sky(t) if self.weather else ("clear", 0.0, 0.0, 0.0, (0, 0, 0))
        flash = self.flash(int(t)) * max(0.0, 1.0 - (t - int(t)) * 3) if self.weather else 0.0
        if not depth_known:                                   # the classic picture: lit as a whole
            if not self.lighting and not flash:
                return px
            self.begin(t)
            p = lv.player
            r, g, b = self.at(p.x, p.y) if self.lighting else (1.0, 1.0, 1.0)
            r, g, b = r + flash, g + flash, b + flash
            return _scaled(view, px, (r, g, b))
        fr = getattr(px, "frame", None)
        PW, PH = view.PW, view.PH
        if fr is not None:
            rows = fr.lists()
            flat = fr.depth
            depths = [flat[y * PW:(y + 1) * PW] for y in range(PH)] if flat is not None else None
        else:
            rows = px
            depths = [getattr(r, "depth", None) for r in rows]
            if any(d is None for d in depths):
                depths = None
            rows = [list(r) for r in rows]
        if depths is None:
            return _scaled(view, rows, (1.0 + flash,) * 3)
        Z0 = view.persp or 1.6
        cx, cy, fx, fy, rx, ry = cam
        ex, ey = cx - fx * Z0, cy - fy * Z0
        lx = view.LW * Z0
        half = view.half
        dirx = [fx + ((x + 0.5 - half) / lx) * rx for x in range(PW)]
        diry = [fy + ((x + 0.5 - half) / lx) * ry for x in range(PW)]
        lighting = self.lighting
        if lighting:
            self.begin(t)
        cover = OVERCAST.get(kind, 0.0) * (0.4 + 0.6 * amount) if self.weather else 0.0
        if cover and lv.down_at(lv.player.x, lv.player.y) is not None if hasattr(lv, "down_at") else False:
            cover *= 0.4                                      # on a wall: half the "sky" is the city below
        sky_k = None                                          # the sky: dark at night, clouded over in weather
        if lighting and self.day:
            a, tint, _p = self.ambient(t)
            sky_k = (min(1.0, a * tint[0]), min(1.0, a * tint[1]), min(1.0, a * tint[2]))
        sky_fog = fog_c
        if lighting:
            a, tint, _p = self.ambient(t)
            sky_fog = (int(fog_c[0] * min(1.0, a * tint[0])), int(fog_c[1] * min(1.0, a * tint[1])),
                       int(fog_c[2] * min(1.0, a * tint[2])))
        lift = flash * 128
        floor_ = math.floor
        exp = math.exp
        done = {}
        smooth = {}
        fogs = {}
        plain = (1.0, 1.0, 1.0)
        for y in range(PH):
            row, dep = rows[y], depths[y]
            for x in range(PW):
                z = dep[x]
                c = row[x]
                if z >= NONE:                                 # the sky
                    if sky_k is None and not cover and not lift:
                        continue
                    key = (c, None)
                    v = done.get(key)
                    if v is None:
                        r, g, b = c
                        if sky_k is not None:
                            r, g, b = r * sky_k[0], g * sky_k[1], b * sky_k[2]
                        if cover:
                            r += (sky_fog[0] - r) * cover
                            g += (sky_fog[1] - g) * cover
                            b += (sky_fog[2] - b) * cover
                        v = done[key] = (min(255, int(r + lift)), min(255, int(g + lift)), min(255, int(b + lift)))
                    row[x] = v
                    continue
                if lighting:
                    d = z + Z0 - 0.04                         # a hair nearer: a wall's light is its room's
                    q = (int(floor_((ex + d * dirx[x]) * 4)), int(floor_((ey + d * diry[x]) * 4)))
                    f = smooth.get(q)
                    if f is None:                             # blended from the four cells round the point
                        f = smooth[q] = self.blend((q[0] + 0.5) / 4.0, (q[1] + 0.5) / 4.0)
                else:
                    f = plain
                k = 0.0
                if fog:
                    zq = int(z * 4) if z > 0 else 0
                    k = fogs.get(zq)
                    if k is None:
                        k = fogs[zq] = int((1.0 - exp(-zq / 4.0 * fog)) * 32) / 32.0
                key = (c, f, k)
                v = done.get(key)
                if v is None:
                    r = c[0] * f[0] + lift
                    g = c[1] * f[1] + lift
                    b = c[2] * f[2] + lift
                    if k:
                        r += (sky_fog[0] - r) * k
                        g += (sky_fog[1] - g) * k
                        b += (sky_fog[2] - b) * k
                    v = done[key] = (min(255, max(0, int(r))), min(255, max(0, int(g))), min(255, max(0, int(b))))
                row[x] = v
        if kind in ("rain", "storm", "snow", "dust") and amount > 0:
            self.fall(view, rows, depths, (ex, ey, dirx, diry, Z0, rx, ry), t, kind, amount, wind)
        if kind in ("rain", "storm") and amount > 0 and getattr(view, "detail", "high") != "low":
            from .surface import splashes                     # the drops striking the ground
            splashes(lv, view, rows, depths, None, cam, Z0, view.EYE, t, amount)
        return rows

    def fall(self, view, rows, depths, ray, t, kind, amount, wind):
        """Rain, snow or dust in the air: each drop at its own distance, drawn where nothing nearer stands and
        only over cells open to the sky."""
        lv = self.lv
        ex, ey, dirx, diry, Z0, rx, ry = ray
        PW, PH = view.PW, view.PH
        p = lv.player
        down = lv.down_at(p.x, p.y) if hasattr(lv, "down_at") else None
        sideways = None
        if down is not None:                                  # on a wall: it falls the world's way down - across
            from .level import DIRS                           # the screen, or straight away from or at him
            sideways = DIRS[down][0] * rx + DIRS[down][1] * ry
        per = {"rain": 26, "storm": 18, "snow": 40, "dust": 30}[kind]
        n = min(600, int(PW * PH * amount / per))
        speed = {"rain": 2.2, "storm": 3.0, "snow": 0.35, "dust": 0.25}[kind]
        drift = wind * (0.5 if kind in ("rain", "storm") else 2.4)
        open_sky = {}
        floor_ = math.floor
        for i in range(n):
            z = 0.4 + _hash(i, 3) * 9.0
            x0 = _hash(i, 1) * PW
            y0 = _hash(i, 2) * PH
            near = 1.0 / (0.6 + z * 0.35)                     # nearer drops: longer, brighter
            if sideways is None:
                y = (y0 + speed * PH * t * (0.6 + 0.4 * near)) % PH
                x = int((x0 + drift * PW * 0.25 * t * (0.6 + 0.4 * near)) % PW)
            else:
                y = (y0 + drift * PH * 0.1 * t) % PH
                x = int((x0 + sideways * speed * PW * t * (0.6 + 0.4 * near)) % PW)
            iy0 = int(y)
            d = z + Z0
            cell = (int(floor_(ex + d * dirx[x] + 0.5)), int(floor_(ey + d * diry[x] + 0.5)))
            ok = open_sky.get(cell)
            if ok is None:
                c = lv.cell(*cell)
                ok = open_sky[cell] = c is not None and c.sky and not getattr(c, "vacuum", False)   # no air: no rain
            if not ok:
                continue
            if kind in ("rain", "storm"):
                length = 1 + int(near * 3) if sideways is None or abs(sideways) > 0.5 else 1
                for k in range(length):
                    yy = iy0 + k if sideways is None else iy0
                    xx = x + int(drift * k * 0.6) if sideways is None else x - int(k * (sideways or 0))
                    if 0 <= yy < PH and 0 <= xx < PW and depths[yy][xx] > z:
                        c = rows[yy][xx]
                        rows[yy][xx] = ((c[0] + 170) // 2, (c[1] + 185) // 2, (c[2] + 205) // 2)
            else:
                colour = (235, 238, 245) if kind == "snow" else (196, 160, 110)
                size = 2 if near > 0.9 else 1
                for yy in range(iy0, iy0 + size):
                    for xx in range(x, x + size):
                        if 0 <= yy < PH and 0 <= xx < PW and depths[yy][xx] > z:
                            c = rows[yy][xx]
                            rows[yy][xx] = colour if kind == "snow" else ((c[0] + colour[0]) // 2,
                                                                          (c[1] + colour[1]) // 2,
                                                                          (c[2] + colour[2]) // 2)


def _scaled(view, px, f):
    """The whole picture in one light: (r, g, b) multipliers (in CLIo Picture's frame where it can)."""
    r, g, b = f
    if abs(r - 1) < 0.01 and abs(g - 1) < 0.01 and abs(b - 1) < 0.01:
        return px
    fr = getattr(px, "frame", None)
    rows = fr.lists() if fr is not None else px
    done = {}
    out = []
    for row in rows:
        line = []
        for c in row:
            v = done.get(c)
            if v is None:
                v = done[c] = (min(255, int(c[0] * r)), min(255, int(c[1] * g)), min(255, int(c[2] * b)))
            line.append(v)
        out.append(line)
    return out


def problems(lid, spec, legend):
    """What is wrong with a level's "lights", "weather" and lamps, for --check."""
    out = []

    def colour_ok(v):
        return isinstance(v, list) and len(v) == 3 and all(isinstance(c, (int, float)) and not isinstance(c, bool)
                                                           for c in v)

    def number(v, lo=None, hi=None):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and (lo is None or v >= lo) and \
            (hi is None or v <= hi)
    lights = spec.get("lights")
    if lights is not None:
        if not isinstance(lights, dict):
            out.append("level '%s': \"lights\" should be an object (ambient, tint, day, events)" % lid)
        else:
            changes = [lights] + [v for v in (lights.get("events") or {}).values()] \
                if isinstance(lights.get("events") or {}, dict) else [lights]
            for ch in changes:
                if not isinstance(ch, dict):
                    out.append("level '%s': each of the lights' \"events\" should be an object" % lid)
                    continue
                if "ambient" in ch and not number(ch["ambient"], 0, 2):
                    out.append("level '%s': the lights' ambient should be 0 (dark) to 2 (1: as drawn)" % lid)
                if "tint" in ch and not colour_ok(ch["tint"]):
                    out.append("level '%s': the lights' tint should be [r, g, b]" % lid)
                if "pulse" in ch and not number(ch["pulse"], 0):
                    out.append("level '%s': the lights' pulse should be how many times a beat (0: none)" % lid)
            if lights.get("events") is not None and not isinstance(lights["events"], dict):
                out.append("level '%s': the lights' \"events\" should map an event to a change" % lid)
            day = lights.get("day")
            if day is not None and (not isinstance(day, dict) or not number(day.get("beats", 240), 8)
                                    or not number(day.get("start", 0.3), 0, 1)):
                out.append("level '%s': the lights' \"day\" should be {\"beats\": 8 or more, \"start\": 0 to 1}" % lid)
    weather = spec.get("weather")
    if weather is not None:
        if not isinstance(weather, dict):
            out.append("level '%s': \"weather\" should be an object (kind, amount, cycle, events)" % lid)
        else:
            states = [weather] + [s for s in (weather.get("cycle") or []) if isinstance(s, dict)] + \
                [s for s in (weather.get("events") or {}).values() if isinstance(s, dict)] \
                if isinstance(weather.get("events") or {}, dict) else [weather]
            for st in states:
                if "kind" in st and st["kind"] not in KINDS:
                    out.append("level '%s': weather kind '%s' should be one of %s" % (lid, st["kind"], ", ".join(KINDS)))
                if "amount" in st and not number(st["amount"], 0, 1):
                    out.append("level '%s': the weather's amount should be 0 to 1" % lid)
                if "fog" in st and not number(st["fog"], 0, 2):
                    out.append("level '%s': the weather's fog should be a density, 0 (none) to 2" % lid)
                if "fog_colour" in st and not colour_ok(st["fog_colour"]):
                    out.append("level '%s': the weather's fog_colour should be [r, g, b]" % lid)
            cycle = weather.get("cycle")
            if cycle is not None and (not isinstance(cycle, list) or not all(
                    isinstance(s, dict) and number(s.get("beats", 30), 1) for s in cycle)):
                out.append("level '%s': the weather's \"cycle\" should be a list of {\"beats\": n, \"kind\": ...}" % lid)
    for ch, sp in (legend or {}).items():
        lamp = sp.get("lamp") if isinstance(sp, dict) else None
        if lamp is None or lamp is True:
            continue
        if not isinstance(lamp, dict):
            out.append("level '%s': '%s' lamp should be true or an object (colour, reach, power...)" % (lid, ch))
            continue
        if "colour" in lamp and not colour_ok(lamp["colour"]):
            out.append("level '%s': '%s' lamp colour should be [r, g, b]" % (lid, ch))
        if "reach" in lamp and not number(lamp["reach"], 1):
            out.append("level '%s': '%s' lamp reach should be 1 cell or more" % (lid, ch))
        if "power" in lamp and not number(lamp["power"], 0):
            out.append("level '%s': '%s' lamp power should be 0 or more" % (lid, ch))
        if "flicker" in lamp and not number(lamp["flicker"], 0, 1):
            out.append("level '%s': '%s' lamp flicker should be 0 to 1" % (lid, ch))
    if "surfaces" in spec and not isinstance(spec["surfaces"], bool):
        out.append("level '%s': \"surfaces\" should be true or false" % lid)
    if "wet" in spec and not number(spec["wet"], 0, 1):
        out.append("level '%s': \"wet\" (how much its floors mirror) should be 0 to 1" % lid)
    return out
