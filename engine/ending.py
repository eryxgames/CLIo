# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The end of a game played in first-person levels: a screen of its own.

When a game with ``"end_screen"`` in game.json is won on a real terminal, the
screen is redrawn in place one last time (as a level is, see :mod:`engine.frame`):
the title as a banner, a picture (a sprite), a heading, the totals of every level
played counting up, the ending's text, what comes next, the credits, and a line
at the bottom that keeps ticking - a crontab line, say.  Any key goes on to the
usual "THE END".  Piped, or on a small screen, nothing is shown here and the
usual ending says it all.

    "end_screen": {"heading": "EPISODE 1 COMPLETE", "picture": ["marine", "cron"],
                   "next": "Next: User Space", "credits": ["..."],
                   "tick": "*/3 * * * *  cron  rain"}
"""
from __future__ import annotations

import textwrap
import time

from .frame import Painter, Screen
from .term import visible_len

DARK = (12, 12, 16)
COUNT = (("kills", "kills_total", "kills"), ("items", "items_total", "items"), ("secrets", "secrets_total", "secrets"))


def totals(levels):
    """Every level's numbers added up (``levels``: the variable a game keeps them in)."""
    keys = ("kills", "kills_total", "items", "items_total", "secrets", "secrets_total", "beats", "par", "fired",
            "hits", "taken")
    t = dict.fromkeys(keys, 0)
    for st in (levels or {}).values():
        if isinstance(st, dict):
            for k in keys:
                try:
                    t[k] += int(st.get(k, 0) or 0)
                except (TypeError, ValueError):
                    pass
    return t


def picture(data, name, lines):
    """A sprite as rows of cells (half blocks), ``lines`` rows high at most, on the dark of the screen."""
    from .sprite import _rgb
    sp = (data.sprites or {}).get(name) if name else None
    if not isinstance(sp, dict) or not sp.get("pixels") or lines < 3:
        return []
    pal = {k: _rgb(v) for k, v in (sp.get("palette") or {}).items()}
    rows = [[pal.get(ch) for ch in r] for r in sp["pixels"]]
    h, w = len(rows), max(len(r) for r in rows)
    k = min(4.0, max(1, (lines * 2) // h)) if h <= lines * 2 else lines * 2 / float(h)   # whole pixels when it can
    H, Wd = max(1, int(h * k)), max(1, int(w * k))
    px = [[(rows[int(y / k)][int(x / k)] if int(x / k) < len(rows[int(y / k)]) else None) for x in range(Wd)]
          for y in range(H)]
    if len(px) % 2:
        px.append([None] * Wd)
    return [[(None, px[r][x] or DARK, px[r + 1][x] or DARK) for x in range(Wd)] for r in range(0, len(px), 2)]


def can_show(game):
    term = game.term
    try:
        cols, rows = term.size()
    except Exception:
        return False
    return bool(term.is_tty and term.ansi and term.inp is None and cols >= 50 and rows >= 18
                and not game.settings.get("scroll_levels"))


def rows_of(game, spec, body, t, k, now, W, H, paint):
    """The screen's lines at ``k`` (0..1) of the count, ``now`` seconds since it opened."""
    data, out = game.data, []
    art = None
    if game.cfg.get("title_banner"):
        try:
            art = game.make_banner(game.cfg["title_banner"], text=data.title, max_width=W - 4, max_height=6)
        except Exception:
            art = None
    head = art.render(game.term, W - 4) if art else []
    head = head or [paint.text([(data.title, "title")], W)]
    for line in head:
        out.append(" " * max(0, (W - visible_len(line)) // 2) + line)
    out.append("")
    room = H - len(out) - 4
    names = spec.get("picture")
    pics = [picture(data, n, min(14, room)) for n in (names if isinstance(names, list) else [names])]
    pics = [p_ for p_ in pics if p_]
    pic = []                                                  # several pictures stand side by side, feet level
    if pics:
        tall = max(len(p_) for p_ in pics)
        for i in range(tall):
            row = []
            for j, p_ in enumerate(pics):
                if j:
                    row += [(" ", None, DARK)] * 2
                off = tall - len(p_)
                row += p_[i - off] if i >= off else [(None, DARK, DARK)] * len(p_[0])
            pic.append(row)
    pw = len(pic[0]) if pic else 0
    right = W - pw - (4 if pic else 2) - 1
    lines = [(spec.get("heading") or "THE END", "title"), ("", "text")]
    for have, of, label in COUNT:
        n, total = int(round(t[have] * k)), t[of]
        if not total and have != "kills":
            continue
        pct = " %3d%%" % (100 * n // total) if total else ""
        lines.append(("%-9s %4d / %-4d%s" % (label, n, total, pct), "good" if total and n == total and k >= 1 else "text"))
    beats = int(round(t["beats"] * k))
    lines.append(("%-9s %4d beats%s" % ("time", beats, ("   par %d" % t["par"]) if t["par"] else ""),
                  "good" if t["par"] and t["beats"] <= t["par"] and k >= 1 else "text"))
    if t["fired"]:
        lines.append(("%-9s %4d%%" % ("accuracy", int(round(100 * k * t["hits"] / t["fired"]))), "text"))
    if body and k >= 1:
        lines.append(("", "text"))
        for para in str(body).split("\n"):
            lines += [(w, "dim") for w in (textwrap.wrap(para, max(20, right)) or [""])]
    tall = max(len(pic), len(lines))
    for i in range(tall):
        left = paint.cells(pic[i]) if i < len(pic) else ""
        gap = " " * ((pw if i >= len(pic) else 0) + (3 if pic else 1))
        text, role = lines[i] if i < len(lines) else ("", "text")
        out.append(" " + left + gap + paint.text([(text, role)], right))
    if k >= 1:
        out.append("")
        if spec.get("next"):
            out.append(" " * max(0, (W - len(spec["next"])) // 2) + paint.text([(spec["next"], "alert")], W))
        for c in spec.get("credits") or []:
            out.append(" " * max(0, (W - len(str(c))) // 2) + paint.text([(str(c), "dim")], W))
    return out[:H - 2]


def tick_line(spec, now, paint, W):
    tick = spec.get("tick")
    if not tick:
        return paint.text([("(Enter)", "dim")], W)
    every = 3
    left = every - int(now) % every
    running = (now % every) > every - 0.6
    return paint.text([(" " + str(tick), "boss"), ("   " + ("running..." if running else "next run in %d" % left),
                                                     "hurt" if running else "dim"), ("   (Enter)", "dim")], W)


def show(game, spec, body=None):
    """Show the end screen; True if it was shown (a real terminal big enough), else False."""
    if not isinstance(spec, dict) or not can_show(game):
        return False
    from .keys import KeyReader
    screen = Screen(game.term, KeyReader(), {}, game.term.animate)
    paint = Painter(game.term.color_depth)
    t = totals(game.world.vars.get("levels"))
    start = time.time()
    count = 1.6 if game.term.animate else 0.0
    screen.start()
    try:
        while True:
            now = time.time() - start
            k = 1.0 if count <= 0 else min(1.0, now / count)
            W, H = screen.size()
            screen.frame(rows_of(game, spec, body, t, k, now, W, H, paint), prompt=None, status="",
                         footer=tick_line(spec, now, paint, W))
            key = screen.keys.get(0.05 if k < 1 else 0.25)
            if key is None:
                continue
            if k < 1:
                count = 0.0                                 # a key while it counts: straight to the end of it
                continue
            if key in ("enter", "space", "esc", "q", "ctrl-d", "ctrl-c"):
                return True
    finally:
        screen.stop()
