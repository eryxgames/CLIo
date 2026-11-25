# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Panels: a screen of instruments - the bridge of a ship, an engineering console, a war room.

A screen is laid out as panels, side by side (``"cols"``) or one over another (``"rows"``), each
in a frame with a title, each holding **widgets** that show the numbers of whatever is running
under it (a simulator's systems and controls, a realm's stocks - any names with values)::

    {"colour": "green", "border": "single", "rows": [
        {"size": 3, "title": "EREBUS  REACTOR", "widgets": [{"text": "CORE {heat:.0f} K   OUTPUT {power:.0f}%"}]},
        {"cols": [
            {"title": "CORE", "size": 34, "widgets": [
                {"gauge": "heat", "max": 1200, "warn": 0.7, "hot": 0.9, "unit": "K"},
                {"center": "drift", "max": 10},
                {"number": "power", "big": true, "unit": "%"},
                {"lamps": [{"label": "COOLANT", "if": "flow > 20"}, {"label": "SCRAM", "if": "rods > 95", "tone": "hot"}]},
                {"plot": ["heat", "power"], "rows": 5}]},
            {"title": "HULL", "widgets": [{"scope": {"model": "hauler", "turn": 12, "reveal": "scan"}}]}]}]}

Widgets: ``gauge`` (a bar: ``max``, ``min``, ``warn`` and ``hot`` as parts of the way, a negative one
for "this low and lower"), ``center`` (a bar either way from zero), ``number`` (``big``: in letters of
lines), ``control`` (a gauge with the keys that move it), ``compass``, ``lamps`` (each lit while its
``if`` holds), ``text`` (with ``{name}`` and ``{name:.1f}`` in it; ``"align": "center"``), ``plot`` (lines over time, in dots),
``scope`` (a vector display: one of the reel's scenes, or a 3D model of the game's turning in lines,
drawn as far as ``reveal`` says and solid when it is whole), ``map`` (what the host draws there),
``ahead`` (the view forward from the host's vehicle over its map, in lines: engine/ahead.py), ``scan``
(a surface scan of real ground - the host's map, or a planet by its legend's heights),
``functions`` (what the console does when asked: each with its key and its state - ready, locked, held
so far, on for so long), ``rule`` and ``space``. A panel's ``colour`` is its phosphor (green, amber, cyan, white, red, blue,
violet); its ``border`` one of the menus' frames (engine/menu.py); ``pulse`` names a cue the frame
brightens with (engine/cues.py).

:class:`View` draws a layout as rows of cells for a frame (engine/frame.py); :func:`problems` says
what is wrong in one. ``python -m engine.panels`` shows a sample. A simulator takes a layout as its
``"panels"`` (engine/sim.py).
"""
from __future__ import annotations

import math
import string

from . import vector
from .menu import BORDERS, border as border_of, wrap

WIDGETS = ("gauge", "center", "number", "control", "compass", "lamps", "text", "plot", "scope", "planet", "map",
           "ahead", "scan", "functions", "rule", "space")
FLEX = ("scope", "planet", "map", "ahead", "scan")                        # these take what room is left
TONES = {"good": (110, 240, 130), "warn": (255, 176, 40), "hot": (255, 84, 64), "off": None}
BITS = ((1, 8), (2, 16), (4, 32), (64, 128))             # braille: the dot at (row, column) of a character
KEEP = 600                                               # values kept of what is plotted


def shade(c, k):
    return (min(255, int(c[0] * k)), min(255, int(c[1] * k)), min(255, int(c[2] * k)))


def bright(c, k=0.55):
    return (int(c[0] + (255 - c[0]) * k), int(c[1] + (255 - c[1]) * k), int(c[2] + (255 - c[2]) * k))


def number(v, scale=1.0):
    v = float(v) * scale
    return ("%.0f" % v) if abs(v) >= 100 or v == int(v) else ("%.1f" % v)


class Canvas:
    """Cells ``(char, fg, bg)`` to draw on."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.rows = [[(" ", None, None)] * w for _ in range(h)]

    def put(self, x, y, text, fg=None):
        if 0 <= y < self.h:
            row = self.rows[y]
            for i, ch in enumerate(text):
                if 0 <= x + i < self.w:
                    row[x + i] = (ch, fg, None)

    def paste(self, x, y, rows):
        for j, r in enumerate(rows):
            if 0 <= y + j < self.h:
                for i, cell in enumerate(r):
                    if 0 <= x + i < self.w:
                        self.rows[y + j][x + i] = cell

    def plain(self):
        return ["".join(c[0] if c[0] is not None else "▀" for c in row).rstrip() for row in self.rows]


def split(nodes, room):
    """How much of ``room`` each node gets: its ``size`` in cells if it has one, else a share of the
    rest by its ``weight`` (1 unless given)."""
    fixed = [int(n["size"]) if isinstance(n.get("size"), (int, float)) and not isinstance(n.get("size"), bool) else None
             for n in nodes]
    left = max(0, room - sum(f for f in fixed if f is not None))
    weights = [float(n.get("weight", 1) or 1) if f is None else 0.0 for n, f in zip(nodes, fixed)]
    total = sum(weights) or 1.0
    out, used = [], 0.0
    for f, w in zip(fixed, weights):
        if f is not None:
            out.append(min(f, room))
        else:
            a = int(round(used * left / total))
            used += w
            out.append(int(round(used * left / total)) - a)
    over = sum(out) - room
    for i in range(len(out) - 1, -1, -1):                # too much asked for: the last give way
        if over <= 0:
            break
        give = min(over, max(0, out[i] - 1))
        out[i] -= give
        over -= give
    return out


class View:
    """A layout, drawn. ``formula(text)`` makes a function of the values out of a condition (a
    simulator's formulas); ``models``: the game's 3D models by name, for scopes."""

    def __init__(self, spec, formula=None, models=None, planets=None):
        self.spec = spec if isinstance(spec, dict) else {}
        self.formula = formula
        self.models = models or {}
        self.planets = planets or {}                     # a game's planets.json, for planet widgets
        self.looks = {}                                  # how each model is to be drawn (viewer.looks): the host's
        self.hits = []                                   # where a tap stands for a key (as last drawn)
        self.subjects, self.worlds = {}, {}
        self.scopes = {}                                 # a scope each, kept for its afterglow
        self.wires = {}
        self.conds = {}
        self.history = {}
        self.plotted = sorted({n for w in self.widgets(self.spec) for n in _names(w.get("plot"))})
        self.functions = []                              # the host's functions as they are now (dicts)

    def widgets(self, node):
        for w in node.get("widgets") or []:
            if isinstance(w, dict):
                yield w
        for key in ("rows", "cols"):
            for child in node.get(key) or []:
                if isinstance(child, dict):
                    yield from self.widgets(child)

    def holds(self, text, env):
        if text is None or text == "":
            return True
        if self.formula is None:
            return bool(env.get(str(text)))
        f = self.conds.get(text)
        if f is None:
            try:
                f = self.conds[text] = self.formula(str(text))
            except Exception:
                f = self.conds[text] = lambda e: 0
        try:
            return bool(f(env))
        except Exception:
            return False

    # ---- drawing -------------------------------------------------------- #
    def rows(self, W, H, env, t=0.0, parts=None, unicode=True, level=None, sheet=None, functions=None):
        """The layout in ``W`` by ``H`` cells for the values ``env`` at time ``t`` (seconds). ``parts``:
        what the host draws (``{"map": fn(w, h) -> rows of cells}``); ``level(action)``: how strongly a cue
        is on now, for panels that pulse; ``sheet``: the cue sheet a ``signals`` scope moves to;
        ``functions``: what the host does when asked, as it is now - a list of ``{"id", "label", "key",
        "state", "word", "charge", "left", "wait", "tone", "flash"}`` (a simulator's ``shown_functions()``)."""
        self.functions = list(functions or [])
        self.level = level
        self.hits = []                                   # (x0, y0, x1, y1, key): where a tap stands for a key
        for n in self.plotted:
            h = self.history.setdefault(n, [])
            h.append(float(env.get(n, 0.0)))
            del h[:-KEEP]
        cv = Canvas(W, H)
        self._node(cv, self.spec, 0, 0, W, H, env, t, parts or {}, unicode, level, sheet,
                   self.spec.get("colour") or "green", self.spec.get("border") or "single")
        return cv.rows

    def plain(self, W, H, env, t=0.0, unicode=True):
        cv = Canvas(W, H)
        cv.rows = self.rows(W, H, env, t, unicode=unicode)
        return cv.plain()

    def _node(self, cv, node, x, y, w, h, env, t, parts, uni, level, sheet, colour, frame):
        colour = node.get("colour") or colour
        frame = node.get("border") or frame
        for key in ("rows", "cols"):
            kids = [k for k in node.get(key) or [] if isinstance(k, dict)]
            if kids:
                at = y if key == "rows" else x
                for kid, size in zip(kids, split(kids, h if key == "rows" else w)):
                    if size > 0:
                        if key == "rows":
                            self._node(cv, kid, x, at, w, size, env, t, parts, uni, level, sheet, colour, frame)
                        else:
                            self._node(cv, kid, at, y, size, h, env, t, parts, uni, level, sheet, colour, frame)
                    at += size
                return
        self._panel(cv, node, x, y, w, h, env, t, parts, uni, level, sheet, colour, frame)

    def _panel(self, cv, node, x, y, w, h, env, t, parts, uni, level, sheet, colour, frame):
        if w < 4 or h < 2:
            return
        ink = vector.colour_of(colour)
        bd = border_of(frame if uni else "ascii")
        edge = shade(ink, 0.55)
        if node.get("pulse") and level is not None:
            try:
                edge = shade(ink, 0.55 + 0.6 * max(0.0, min(1.0, float(level(node["pulse"])))))
            except Exception:
                pass
        cv.put(x, y, bd.tl + bd.top * (w - 2) + bd.tr, edge)
        cv.put(x, y + h - 1, bd.bl + bd.bottom * (w - 2) + bd.br, edge)
        for yy in range(y + 1, y + h - 1):
            cv.put(x, yy, bd.left, edge)
            cv.put(x + w - 1, yy, bd.right, edge)
        title = str(node.get("title") or "")
        if title:
            cv.put(x + 2, y, " " + title[:w - 6] + " ", bright(ink))
        ix, iy, iw, ih = x + 2, y + 1, w - 4, h - 2
        if iw < 2 or ih < 1:
            return
        items = [wd for wd in node.get("widgets") or [] if isinstance(wd, dict) and self.holds(wd.get("when"), env)]
        labels = [str(wd.get("label") or wd.get(k) or "").upper() for wd in items for k in ("gauge", "center", "control", "number")
                  if k in wd and not wd.get("big")]
        lw = min(12, max([len(s) for s in labels] or [0]))
        tall = [self._tall(wd, iw, env) for wd in items]
        flex = [i for i, wd in enumerate(items) if tall[i] is None]
        left = max(0, ih - sum(tl for tl in tall if tl is not None))
        for n, i in enumerate(flex):
            tall[i] = left // len(flex) + (1 if n < left % len(flex) else 0)
        yy = iy
        for wd, rows in zip(items, tall):
            rows = min(rows, iy + ih - yy)
            if rows <= 0:
                break
            self._widget(cv, wd, ix, yy, iw, rows, env, t, parts, uni, sheet, ink, lw, id(node))
            yy += rows

    def _tall(self, wd, w, env):
        if "scope" in wd or "map" in wd or "planet" in wd or "ahead" in wd or "scan" in wd:
            return int(wd["rows"]) if wd.get("rows") else None
        if "plot" in wd:
            return max(2, int(wd.get("rows", 4)))
        if "number" in wd and wd.get("big"):
            return 3
        if "space" in wd:
            return max(1, int(wd.get("space") or 1))
        if "lamps" in wd:
            lamps = [lm for lm in wd.get("lamps") or [] if isinstance(lm, dict)]
            return max(1, len(_flow([len(str(lm.get("label", ""))) + 2 for lm in lamps], w, 2)))
        if "text" in wd:
            return max(1, len(_lines(_fill(wd.get("text"), env), w)))
        if "functions" in wd:
            return max(1, len(self._listed(wd)))
        return 1

    def _listed(self, wd):
        """The functions a ``functions`` widget lists: all of them, or those it names, in its order."""
        names = wd.get("functions")
        if isinstance(names, (list, tuple, str)):
            by = {f.get("id"): f for f in self.functions}
            return [by[n] for n in _names(names) if n in by]
        return list(self.functions)

    def _widget(self, cv, wd, x, y, w, h, env, t, parts, uni, sheet, ink, lw, owner):
        dim, hi = shade(ink, 0.45), bright(ink)
        full, rest = ("█", "░") if uni else ("#", "-")

        def value(name):
            try:
                return float(env.get(name, 0.0))
            except (TypeError, ValueError):
                return 0.0

        def limit(key, default):
            v = wd.get(key, default)
            return value(v) if isinstance(v, str) else float(v)
        kind = next((k for k in WIDGETS if k in wd), None)
        if kind in ("gauge", "control", "center"):
            name = wd[kind]
            v, top, low = value(name), limit("max", 100), limit("min", 0)
            label = str(wd.get("label") or name).upper()[:lw]
            unit = str(wd.get("unit") or "")
            keys = ""
            if kind == "control" and wd.get("keys"):
                keys = " " + "/".join(_key(k, uni) for k in list(wd["keys"])[:2])
            text = number(v, float(wd.get("scale", 1))) + unit
            n = max(3, w - lw - 1 - len(keys) - 8)
            tone = ink
            span = (top - low) or 1.0
            part = (v - low) / span
            for key, col in (("warn", TONES["warn"]), ("hot", TONES["hot"])):
                at = wd.get(key)
                if at is not None and ((at >= 0 and part >= at) or (at < 0 and part <= -at)):
                    tone = col
            cv.put(x, y, label, dim)
            cv.put(x + lw + 1, y, keys.strip(), dim)
            bx = x + lw + 1 + len(keys)
            if keys:                                     # a tap on its line: left of the bar's middle less, right more
                pair = [str(k) for k in list(wd["keys"])[:2]]
                mid = bx + n // 2
                self.hits.append((mid, y, x + w, y + 1, pair[0]))
                if len(pair) > 1:
                    self.hits.append((x, y, mid, y + 1, pair[1]))
            if kind == "center":
                half = n // 2
                k = max(-half, min(half, int(round(v / (top or 1.0) * half))))
                cv.put(bx, y, rest * n, dim)
                cv.put(bx + min(half, half + k), y, full * abs(k), tone)
                cv.put(bx + half, y, "|" if not uni else "│", hi)
                text = ("%+.1f" % (v * float(wd.get("scale", 1)))) + unit
            else:
                k = max(0, min(n, int(round(part * n))))
                cv.put(bx, y, full * k, tone)
                cv.put(bx + k, y, rest * (n - k), dim)
            cv.put(x + w - len(text[:7]), y, text[:7], hi if tone is ink else tone)
        elif kind == "number":
            name = wd["number"]
            text = number(value(name), float(wd.get("scale", 1)))
            unit = str(wd.get("unit") or "")
            label = str(wd.get("label") or name).upper()
            if wd.get("big") and uni and h >= 3:
                from .banner import line_rows
                rows, _owner = line_rows(text)
                cv.put(x, y, label[:max(0, w - len(rows[0]) - len(unit) - 2)], dim)
                for i in range(3):
                    cv.put(x + w - len(rows[i]) - len(unit) - (1 if unit else 0), y + i, rows[i], hi)
                cv.put(x + w - len(unit), y + 2, unit, dim)
            else:
                cv.put(x, y, label[:max(0, w - len(text) - len(unit) - 2)], dim)
                cv.put(x + w - len(text) - len(unit) - (1 if unit else 0), y, text, hi)
                cv.put(x + w - len(unit), y, unit, dim)
        elif kind == "compass":
            from .sim import compass
            deg = value(wd["compass"])
            strip = compass(deg, max(5, w - 5))
            cv.put(x, y, strip if uni else strip.replace("·", "."), ink)
            cv.put(x + w - 4, y, "%3d" % (round(deg) % 360) + ("°" if uni else " "), hi)
        elif kind == "lamps":
            lamps = [lm for lm in wd.get("lamps") or [] if isinstance(lm, dict)]
            on, off = ("●", "○") if uni else ("*", "o")
            lines = _flow([len(str(lm.get("label", ""))) + 2 for lm in lamps], w, 2)
            i = 0
            for row, count in enumerate(lines[:h]):
                xx = x
                for lm in lamps[i:i + count]:
                    lit = self.holds(lm.get("if"), env)
                    col = (TONES.get(lm.get("tone")) or ink) if lit else dim
                    text = (on if lit else off) + " " + str(lm.get("label", ""))
                    cv.put(xx, y + row, text, col)
                    xx += len(text) + 2
                i += count
        elif kind == "text":
            col = TONES.get(wd.get("tone")) or (hi if wd.get("bright") else ink)
            for i, line in enumerate(_lines(_fill(wd.get("text"), env), w)[:h]):
                cv.put(x + ((w - len(line)) // 2 if wd.get("align") == "center" else 0), y + i, line, col)
        elif kind == "plot":
            self._plot(cv, wd, x, y, w, h, uni, ink)
        elif kind == "scope":
            self._scope(cv, wd, x, y, w, h, env, t, uni, sheet, ink, owner)
        elif kind == "planet":
            from . import viewer
            name = wd["planet"]
            world = self.worlds.get(name) if isinstance(name, str) else None
            if world is None:
                world = viewer.Planet(self.planets.get(name) if isinstance(name, str) else name, str(name))
                if isinstance(name, str):
                    self.worlds[name] = world
            turn = wd.get("turn")
            sites = [st for st in wd.get("sites") or [] if isinstance(st, dict) and self.holds(st.get("if"), env)]
            cv.paste(x, y, viewer.draw_planet(world, wd.get("view", "surface"), w, h, t,
                                              value(turn) if isinstance(turn, str) else turn, uni, sites=sites))
        elif kind == "map":
            fn = parts.get("map")
            if fn is not None:
                cv.paste(x, y, fn(w, h))
            else:
                cv.put(x, y, "NO MAP", dim)
        elif kind == "scan":                             # a surface scan of real ground: the host's map, or a planet
            from . import ahead, vector
            spec = wd["scan"] if isinstance(wd["scan"], dict) else {}
            key = (owner, id(wd), w, h)
            scope = self.scopes.get(key)
            if scope is None:
                scope = self.scopes[key] = vector.Scope(w, h, colour=spec.get("colour") or ink)
            scope.captions = True
            scope.clear()
            beat = float(self.level(spec["pulse"])) if spec.get("pulse") and self.level else 0.0
            world = None
            if isinstance(self.planets.get(spec.get("planet")), dict):
                from . import viewer
                made = self.__dict__.setdefault("_worlds", {})
                world = made.get(spec["planet"]) or made.setdefault(spec["planet"],
                                                                    viewer.Planet(self.planets[spec["planet"]], spec["planet"]))
            if world is not None:
                turn = spec.get("turn")                  # how far round it has turned: a number, a value's name
                turn = value(turn) if isinstance(turn, str) else (turn if isinstance(turn, (int, float)) else world.spin * t)
                grid = ahead.planet_heights(world, turn)
                title, at = spec.get("title") or "", None
            else:
                grid, at, title = parts["scan"]() if "scan" in parts else (None, None, "")
                title = spec.get("title") or title
            if grid:
                ahead.scan(scope, grid, t, title, str(spec.get("unit") or ""), beat, at)
            else:
                scope.text(1, 0, "NOTHING TO SCAN")
            cv.paste(x, y, scope.rows("dots" if uni else "strokes", uni))
        elif kind == "ahead":                            # what is ahead of the host's vehicle, in lines
            fn = parts.get("ahead")
            if fn is not None:
                cv.paste(x, y, fn(w, h, wd["ahead"], ink, t, uni, (owner, id(wd))))
            else:
                cv.put(x, y, "NO VIEW AHEAD", dim)
        elif kind == "functions":
            for i, f in enumerate(self._listed(wd)[:h]):
                self._function(cv, f, x, y + i, w, uni, ink, wd.get("keys", True))
        elif kind == "rule":
            cv.put(x, y, ("─" if uni else "-") * w, dim)

    def _function(self, cv, f, x, y, w, uni, ink, keys=True):
        """A function on a line: ``[X] SCRAM ......... READY`` - its key, its name, dots, and its state in
        a word, the seconds it has left, or how far its key has been held."""
        from .sim import function_word
        dim, hi = shade(ink, 0.45), bright(ink)
        state = f.get("state", "ready")
        tone = TONES.get(f.get("tone")) or hi
        word = function_word(f, uni, bar=max(4, min(10, w // 5)))
        key = ("[%s] " % _key(str(f.get("key") or "?"), uni)) if keys else ""
        label = str(f.get("label") or f.get("id") or "").upper()
        room = max(0, w - len(key) - len(word) - 2)
        label = label[:room]
        live = state in ("on", "hold", "done")
        idle = state in ("locked", "wait", "spent")
        cv.put(x, y, key, dim if idle else ink)
        cv.put(x + len(key), y, label, dim if idle else (tone if live else hi))
        if f.get("key"):
            self.hits.append((x, y, x + w, y + 1, str(f["key"])))     # a tap on its line is its key
        dots = w - len(key) - len(label) - len(word) - 2
        if dots > 0:
            cv.put(x + len(key) + len(label) + 1, y, ("·" if uni else ".") * dots, dim)
        spent = TONES.get(f.get("tone")) if state == "spent" else None   # used up, and it has left its mark
        cv.put(x + w - len(word), y, word, spent or (dim if idle else (tone if live else ink)))
        if f.get("flash"):                               # just done: the line lit for a moment
            lit = TONES.get(f.get("tone")) or ink
            for xx in range(max(0, x), min(cv.w, x + w)):
                if 0 <= y < cv.h:
                    cv.rows[y][xx] = (cv.rows[y][xx][0], (8, 10, 12), lit)

    def _plot(self, cv, wd, x, y, w, h, uni, ink):
        names = _names(wd.get("plot"))
        series = [self.history.get(n, [])[-2 * w:] for n in names]
        vals = [v for s in series for v in s]
        lo = float(wd["min"]) if isinstance(wd.get("min"), (int, float)) else (min(vals) if vals else 0.0)
        hi = float(wd["max"]) if isinstance(wd.get("max"), (int, float)) else (max(vals) if vals else 1.0)
        if hi - lo < 1e-9:
            hi = lo + 1.0
        tones = [ink, TONES["warn"], bright(ink), TONES["hot"]]
        if not uni:                                      # no dots: a line of marks for each
            marks = "_.-=#"
            for i, s in enumerate(series[:h]):
                cv.put(x, y + i, "".join(marks[int((max(lo, min(hi, v)) - lo) / (hi - lo) * 4)] for v in s[-w:]), tones[i % 4])
            return
        H = h * 4
        dots = {}
        for i, s in enumerate(series):
            px = py = None
            off = 2 * w - len(s)
            for j, v in enumerate(s):
                qx, qy = off + j, int(round((1 - (max(lo, min(hi, v)) - lo) / (hi - lo)) * (H - 1)))
                if px is not None:
                    for k in range(abs(qy - py) + 1):    # the way up or down between two values
                        dots[(qx, py + (k if qy >= py else -k))] = i
                dots[(qx, qy)] = i
                px, py = qx, qy
        cells = {}
        for (dx, dy), i in dots.items():
            bits, who = cells.get((dx // 2, dy // 4), (0, i))
            cells[(dx // 2, dy // 4)] = (bits | BITS[dy % 4][dx % 2], who)
        for (cx, cy), (bits, i) in cells.items():
            cv.put(x + cx, y + cy, chr(0x2800 + bits), tones[i % 4])
        label = "  ".join("%s %s" % (n.upper(), number(self.history[n][-1]) if self.history.get(n) else "-") for n in names)
        cv.put(x, y, label[:w], shade(ink, 0.45))

    def _scope(self, cv, wd, x, y, w, h, env, t, uni, sheet, ink, owner):
        spec = wd["scope"] if isinstance(wd["scope"], dict) else {"scene": wd["scope"]}
        key = (owner, id(wd), w, h)
        scope = self.scopes.get(key)
        if scope is None:
            scope = self.scopes[key] = vector.Scope(w, h, colour=ink, afterglow=float(spec.get("afterglow", 0.0)))
            scope.captions = w >= 60 and h >= 16         # a scene's own words want room
        scope.clear()
        scene = spec.get("scene")
        if scene in vector.SCENES:
            vector.scene(scene, t, scope, sheet)
        elif spec.get("view"):                           # one of the viewer's views of a model
            from . import viewer

            def of(v, default):
                if isinstance(v, str):
                    return float(env.get(v, 0.0))
                return default if v is None else float(v)
            name = spec.get("model")
            subject = self.subjects.get(name)
            if subject is None and name in self.models:
                subject = self.subjects[name] = viewer.Subject(self.models[name], look=self.looks.get(name))
            if subject is None:
                cv.put(x, y, "NO MODEL", shade(ink, 0.45))
                return
            view = spec["view"]
            top = float(spec.get("max", 1) or 1)
            vals = None
            if isinstance(spec.get("values"), dict):
                vals = {g: max(0.0, min(1.0, of(src, 0.0) / top)) for g, src in spec["values"].items()}
            cut_at = None if spec.get("cut") is None else of(spec["cut"], 0.5) / float(spec.get("whole", 1) or 1)
            yaw = float(spec.get("yaw", 0.0 if view == "plan" else 30.0)) + (0.0 if view == "plan" else float(spec.get("turn", 12)) * t)
            cv.paste(x, y, viewer.draw(subject, view, w, h, yaw, float(spec.get("pitch", 20)), float(spec.get("zoom", 1)),
                                       spec.get("colour") or (None if subject.look.get("ink") else ink), uni, cut_at, {"x": 0, "y": 1, "z": 2}.get(spec.get("axis"), 1),
                                       int(of(spec.get("levels"), 1)), int(of(spec.get("level"), 0)), vals, t, scope))
            return
        else:
            wire = self._wire(spec.get("model"))
            reveal = spec.get("reveal")
            shown = 1.0 if reveal is None else max(0.0, min(1.0, float(env.get(reveal, 0.0)) / float(spec.get("whole", 1) or 1)))
            turn = math.radians(float(spec.get("turn", 15)) * t + float(spec.get("yaw", 0)))
            fov = float(spec.get("fov", 46))
            reach = math.tan(math.radians(fov) / 2.0)        # how far to stand for the whole of it to be in sight
            tall = (wire.high - wire.low) / 2.0
            far = float(spec.get("far", 1.0)) * max(wire.wide * 1.5 / reach, tall * 1.25 / (reach * (h * 4.0) / (w * 2.0)))
            cam = vector.Camera((far * math.sin(turn), -far * math.cos(turn), wire.mid + far * float(spec.get("height", 0.25))),
                                (0.0, 0.0, wire.mid), fov=fov)
            if shown >= 1.0:
                scope.render(cam, [wire], solid=bool(spec.get("solid", True)))
            else:                                        # as far as it is known: from the ground up
                z = wire.low + (wire.high - wire.low) * shown
                scope.draw(cam, below(wire, z), bright=0.8)
                r = wire.wide * 1.5
                scope.draw(cam, vector.polyline([(-r, -r, z), (r, -r, z), (r, r, z), (-r, r, z), (-r, -r, z)]), bright=1.5)
        cv.paste(x, y, scope.rows("dots" if uni else "strokes", uni))

    def _wire(self, name):
        wire = self.wires.get(name)
        if wire is None:
            model = self.models.get(name)
            wire = vector.from_model(model) if model is not None else vector.box((1.0, 1.0, 1.0))
            zs = [v[2] for v in wire.verts] or [0.0]
            wire.low, wire.high = min(zs), max(zs)
            wire.mid = (wire.low + wire.high) / 2.0
            wire.wide = max([max(abs(v[0]), abs(v[1])) for v in wire.verts] or [0.5])
            wire.size = max(wire.wide, (wire.high - wire.low) / 2.0, 0.5)
            self.wires[name] = wire
        return wire


def below(wire, z):
    """The part of a wire under the height ``z``: its lines cut off there."""
    verts, edges = list(wire.verts), []
    for a, b in wire.edges:
        pa, pb = wire.verts[a], wire.verts[b]
        if pa[2] <= z and pb[2] <= z:
            edges.append((a, b))
        elif pa[2] <= z or pb[2] <= z:
            lo, hi = (pa, pb) if pa[2] <= z else (pb, pa)
            k = (z - lo[2]) / ((hi[2] - lo[2]) or 1.0)
            verts.append((lo[0] + (hi[0] - lo[0]) * k, lo[1] + (hi[1] - lo[1]) * k, z))
            edges.append((a if pa[2] <= z else b, len(verts) - 1))
    return vector.Wire(verts, edges, (), wire.colour)


def _lines(text, w):
    """A text as it is when it fits, wrapped when it does not."""
    return [text] if len(text) <= w else wrap(text, w)


def _names(v):
    return [str(n) for n in v] if isinstance(v, (list, tuple)) else ([str(v)] if v else [])


def _key(k, uni):
    return {"up": "↑", "down": "↓", "left": "←", "right": "→"}.get(k, k.upper()) if uni else \
        {"up": "Up", "down": "Dn", "left": "Lt", "right": "Rt"}.get(k, k.upper())


def _flow(widths, room, gap):
    """How many of some things go on each line."""
    lines, n, used = [], 0, 0
    for w in widths:
        if n and used + gap + w > room:
            lines.append(n)
            n, used = 0, 0
        used += w + (gap if n else 0)
        n += 1
    if n:
        lines.append(n)
    return lines or [0]


class _Values(dict):
    def __missing__(self, key):
        return 0.0


def _fill(text, env):
    """A text with ``{name}`` and ``{name:.1f}`` filled in from the values (a name there is not: 0)."""
    try:
        return string.Formatter().vformat(str(text or ""), (), _Values(env))
    except (ValueError, IndexError, KeyError, AttributeError, TypeError):
        return str(text or "")


def problems(spec, names=None, where="panels", formula=None, models=None, planets=None, functions=None, ahead=None):
    """What is wrong in a layout. ``names``: the values there are to show; ``formula``: checks a condition;
    ``functions``: the names of what the host does when asked."""
    out = []
    if not isinstance(spec, dict):
        return ["%s: it should be a map" % where]
    known = set(names) if names is not None else None

    def name_ok(at, n):
        if known is not None and isinstance(n, str) and n not in known:
            out.append("%s: there is no value called '%s'" % (at, n))

    def cond_ok(at, text):
        if text and formula is not None:
            try:
                formula(str(text))
            except Exception as e:
                out.append("%s: %s" % (at, e))

    def walk(node, at):
        if not isinstance(node, dict):
            out.append("%s: it should be a map" % at)
            return
        if node.get("colour") is not None and node["colour"] not in vector.COLOURS:
            out.append("%s: unknown colour '%s' (%s)" % (at, node["colour"], ", ".join(vector.COLOURS)))
        if node.get("border") is not None and str(node["border"]).split()[:1] not in [[n] for n in BORDERS]:
            out.append("%s: unknown border '%s' (%s)" % (at, node["border"], ", ".join(BORDERS)))
        kids = [k for k in ("rows", "cols") if node.get(k) is not None]
        if len(kids) > 1 or (kids and node.get("widgets") is not None):
            out.append("%s: one of \"rows\", \"cols\" or \"widgets\"" % at)
        for key in kids:
            if not isinstance(node[key], list) or not node[key]:
                out.append("%s: \"%s\" should be a list of panels" % (at, key))
                continue
            for i, kid in enumerate(node[key]):
                walk(kid, "%s %s %d" % (at, key[:-1], i + 1))
        for i, wd in enumerate(node.get("widgets") or []):
            wat = "%s widget %d" % (at, i + 1)
            kind = next((k for k in WIDGETS if isinstance(wd, dict) and k in wd), None)
            if kind is None:
                out.append("%s: it should be one of %s" % (wat, ", ".join(WIDGETS)))
                continue
            cond_ok(wat, wd.get("when"))
            if kind in ("gauge", "center", "number", "control", "compass"):
                name_ok(wat, wd[kind])
                for key in ("max", "min"):
                    if isinstance(wd.get(key), str):
                        name_ok(wat, wd[key])
            elif kind == "plot":
                for n in _names(wd["plot"]):
                    name_ok(wat, n)
            elif kind == "lamps":
                if not isinstance(wd["lamps"], list):
                    out.append("%s: \"lamps\" should be a list" % wat)
                for lm in wd["lamps"] if isinstance(wd["lamps"], list) else []:
                    if not isinstance(lm, dict) or not lm.get("label"):
                        out.append("%s: a lamp needs a \"label\"" % wat)
                    else:
                        cond_ok("%s lamp '%s'" % (wat, lm["label"]), lm.get("if"))
                        if lm.get("tone") not in (None,) + tuple(TONES):
                            out.append("%s lamp '%s': unknown tone '%s' (%s)" % (wat, lm["label"], lm["tone"], ", ".join(TONES)))
            elif kind == "scope":
                sc = wd["scope"] if isinstance(wd["scope"], dict) else {"scene": wd["scope"]}
                if sc.get("scene") is not None and sc["scene"] not in vector.SCENES:
                    out.append("%s: unknown scene '%s' (%s)" % (wat, sc["scene"], ", ".join(vector.SCENES)))
                if sc.get("scene") is None and not sc.get("model"):
                    out.append("%s: a scope needs a \"scene\" or a \"model\"" % wat)
                if sc.get("model") and models is not None and sc["model"] not in models:
                    out.append("%s: there is no model called '%s'" % (wat, sc["model"]))
                if sc.get("reveal"):
                    name_ok(wat, sc["reveal"])
                if sc.get("view") is not None:
                    from .viewer import VIEWS
                    if sc["view"] not in VIEWS:
                        out.append("%s: unknown view '%s' (%s)" % (wat, sc["view"], ", ".join(VIEWS)))
                    for key in ("cut", "level", "levels"):
                        name_ok(wat, sc.get(key))
                    for src in (sc.get("values") or {}).values() if isinstance(sc.get("values"), dict) else []:
                        name_ok(wat, src)
            elif kind == "planet":
                from .viewer import PLANET_VIEWS
                if isinstance(wd["planet"], str) and planets is not None and wd["planet"] not in planets:
                    out.append("%s: there is no planet called '%s'" % (wat, wd["planet"]))
                if wd.get("view") not in (None,) + PLANET_VIEWS:
                    out.append("%s: unknown view '%s' (%s)" % (wat, wd["view"], ", ".join(PLANET_VIEWS)))
                if wd.get("sites") is not None and not isinstance(wd["sites"], list):
                    out.append("%s: \"sites\" should be a list" % wat)
                for st in wd["sites"] if isinstance(wd.get("sites"), list) else []:
                    if not isinstance(st, dict) or not all(isinstance(st.get(k), (int, float)) for k in ("lat", "lon")):
                        out.append("%s: a site needs \"lat\" and \"lon\" (and a \"name\")" % wat)
                    else:
                        cond_ok("%s site '%s'" % (wat, st.get("name", "")), st.get("if"))
            elif kind == "scan":
                spec = wd["scan"]
                if spec is not True and not isinstance(spec, dict):
                    out.append("%s: \"scan\" should be true (the map here), or a map (planet, title, unit, pulse)" % wat)
                elif isinstance(spec, dict) and spec.get("planet") is not None:
                    world = (planets or {}).get(spec["planet"])
                    if planets is not None and world is None:
                        out.append("%s: there is no planet called '%s'" % (wat, spec["planet"]))
                    elif isinstance(world, dict) and not any(isinstance(v, dict) and v.get("height")
                                                             for v in (world.get("legend") or {}).values()):
                        out.append("%s: planet '%s' has no heights to scan (give its legend's grounds a \"height\")"
                                   % (wat, spec["planet"]))
                elif ahead is False:
                    out.append("%s: there is no map here to scan (a simulator with a map has one; or name a planet)" % wat)
            elif kind == "ahead":
                from . import ahead as forward
                out.extend(forward.problems(wd["ahead"], wat))
                if ahead is False:
                    out.append("%s: there is no vehicle here to look ahead of (a simulator with a map has one)" % wat)
            elif kind == "functions":
                listed = wd["functions"]
                if listed is not True and not isinstance(listed, (list, str)):
                    out.append("%s: \"functions\" should be true (all of them) or a list of their names" % wat)
                elif functions is not None:
                    if listed is True and not functions:
                        out.append("%s: there are no functions to list" % wat)
                    for n in _names(listed) if listed is not True else []:
                        if n not in functions:
                            out.append("%s: there is no function called '%s'" % (wat, n))
    walk(spec, where)
    return out


SAMPLE = {"colour": "green", "rows": [
    {"size": 3, "title": "EREBUS  ENGINEERING", "widgets": [
        {"text": "CORE {heat:.0f} K   OUTPUT {power:.0f} %   T+ {time:.0f} s", "bright": True}]},
    {"cols": [
        {"title": "REACTOR", "size": 38, "pulse": "bar", "widgets": [
            {"gauge": "heat", "max": 1200, "warn": 0.7, "hot": 0.9, "unit": "K"},
            {"gauge": "flow", "max": 100, "warn": -0.2, "unit": "%"},
            {"control": "rods", "max": 100, "keys": ["up", "down"]},
            {"center": "drift", "max": 10},
            {"space": 1},
            {"number": "power", "big": True, "unit": "%"},
            {"lamps": [{"label": "COOLANT", "if": "flow"}, {"label": "GRID", "if": "power"},
                       {"label": "SCRAM", "if": "scram", "tone": "hot"}]},
            {"plot": ["heat", "power"], "rows": 5},
            {"rule": True},
            {"functions": True}]},
        {"title": "HULL SCAN", "colour": "cyan", "widgets": [{"scope": {"scene": "hauler"}}]}]}]}


def main(argv=None):
    """``python -m engine.panels``: a sample screen, drawn once as text (``--live``: on the terminal, moving)."""
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    view = View(SAMPLE)

    def env(t):
        return {"heat": 640 + 300 * math.sin(t / 3.0), "flow": 60 + 30 * math.cos(t / 2.0), "rods": 40.0,
                "drift": 6 * math.sin(t), "power": 62 + 20 * math.sin(t / 4.0), "scram": 0, "time": t}
    def does(t):                                         # what a console does when asked, as a host gives it
        held = (t % 8.0) / 2.0 if t % 8.0 < 2.0 else 0.0
        return [{"id": "scram", "label": "Scram", "key": "x", "state": "ready", "word": "READY", "tone": "hot"},
                {"id": "vent", "label": "Vent steam", "key": "v", "state": "wait", "word": "WAIT",
                 "wait": 1 + int(12 - t % 12)},
                {"id": "pumps", "label": "Reserve pumps", "key": "r", "state": "on", "word": "ON", "tone": "good"},
                {"id": "beacon", "label": "Deploy beacon", "key": "b", "state": "hold" if held else "locked",
                 "word": "HOLD" if held else "LOCKED", "charge": held}]
    if "--live" not in argv:
        for i in range(60):
            view.rows(96, 28, env(i / 4.0), i / 4.0)
        cv = Canvas(96, 28)
        cv.rows = view.rows(96, 28, env(15.0), 15.0, unicode="--ascii" not in argv, functions=does(17.0))
        print("\n".join(cv.plain()))
        return 0
    import time
    from .frame import Screen
    from .term import Term
    screen = Screen(Term())
    screen.start()
    try:
        start = time.monotonic()
        while True:
            t = time.monotonic() - start
            W, H = screen.size()
            screen.frame(view.rows(W, H - 2, env(t), t, unicode=screen.unicode, functions=does(t)),
                         status="Ctrl-C ends")
            time.sleep(0.08)
    except KeyboardInterrupt:
        pass
    finally:
        screen.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
