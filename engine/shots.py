# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""Pictures of a game without playing it: ``python clio.py GAME --shots DIR``.

Every simulator with a screen (at a few moments of the autopilot's run), every menu of ``menus.json``
and every 3D model (as its look has it, and through its clips) is drawn by the code the game runs and
written as one page, ``DIR/index.html`` - each picture painted cell by cell, nothing to install - with
the same as plain text beside it (``DIR/NAME.txt``). An author changes the data and looks.

``--shots-size 112x34`` is the size of a console's screen; ``--shots-as full,ascii`` the kinds of
terminal it is shown on (full, 256, 16, none, console - the Windows console's font -, ascii).
"""
from __future__ import annotations

import html
import io
import os

PAPER, INK = "#0b0e14", "#c8cfdb"
MOMENTS = (0.0, 0.35, 0.7, 1.0)                           # of the autopilot's run


def runs_of(rows, terminal="full"):
    """Rows of a frame - lists of cells, or escape-coded lines - as runs ``[text, fg, bg, bold]``, as a
    terminal of that kind shows them."""
    from .editor.looks import TERMINALS, as_terminal, cells
    from .frame import Painter
    from .term import strip_ansi
    depth, uni, _ = TERMINALS.get(terminal, TERMINALS["full"])
    out = []
    for r in rows:
        if isinstance(r, list):
            out.append(as_terminal([r], terminal)[0])
        elif depth == 3 and uni:
            out.append(cells(r))
        else:                                             # a painted line: its words in that terminal's colours
            got = []
            for text, fg, bg, bold in cells(r):
                rgb = tuple(int(fg[i:i + 2], 16) for i in (1, 3, 5)) if fg else None
                line = Painter(depth).text([(text if uni else text.encode("ascii", "replace").decode(), rgb)], len(text))
                got += cells(line) if depth else [[strip_ansi(line), None, None, False]]
            out.append(got)
    return out


def plain(runs):
    return "\n".join("".join(r[0] for r in row).rstrip() for row in runs)


def block(runs):
    """Runs as HTML: a <pre> of coloured spans."""
    lines = []
    for row in runs:
        spans = []
        for text, fg, bg, bold in row:
            style = ("color:%s;" % fg if fg else "") + ("background:%s;" % bg if bg else "") + ("font-weight:bold;" if bold else "")
            spans.append('<span style="%s">%s</span>' % (style, html.escape(text)) if style else html.escape(text))
        lines.append("".join(spans))
    return '<pre class="shot">%s</pre>' % "\n".join(lines)


def consoles(data, size=(112, 34), terminals=("full",), moments=MOMENTS):
    """Each simulator as its screen stands at moments of the autopilot's run: ``[(title, note, runs)]``."""
    from . import sim as S
    from .realtime import replay
    out = []
    W, H = size
    for sid in sorted(getattr(data, "sims", None) or {}):
        try:
            flown = S.make(data, sid)
            journal = S.fly(flown)
        except Exception as e:                            # a sim that cannot be made is said, not a crash
            out.append(("%s" % sid, "it cannot be drawn: %s" % e, []))
            continue
        last = flown.ticks
        how = "the autopilot %s in %.1f s" % ({"won": "does it", "lost": "fails (%s)" % flown.why}.get(
            flown.result, "does not finish it"), last / float(flown.rate))
        for k in moments:
            sim = S.make(data, sid)
            if k > 0:
                upto = max(1, int(last * k) - (3 if k >= 1.0 else 0))
                cut = [e for e in journal if e[0] <= upto]
                replay(sim, cut, rate=sim.rate, exact=True, ticks=max(0, upto - (cut[-1][0] if cut else 0)))
            runner = S.Runner(sim)
            rows = None
            for _ in range(2):                            # (twice: displays with an afterglow have something to show)
                rows = runner.rows(W, H, 3, True)
            for t in terminals:
                from .editor.looks import TERMINALS
                uni = TERMINALS.get(t, TERMINALS["full"])[1]
                shown = rows if uni else S.Runner(sim).rows(W, H, 3, False)
                out.append(("%s  %s" % (sid, "before it begins" if k == 0 else "%d%% through" % round(k * 100)),
                            "%s; %d by %d, %s" % (how, W, H, t), runs_of(shown, t)))
    return out


def menus(game, size=(78, 24), terminals=("full",)):
    """Each menu of the game's own, in its look, as it stands at the start: ``[(title, note, runs)]``."""
    from . import menu as M
    out = []
    for name in sorted(getattr(game.data, "menus", None) or {}):
        m = M.from_data(game, name)
        if m is None:
            continue
        b = M.board(m, size[0], size[1], game.term, M.frame_of(game.ui))
        rows = M.cells(b, M.palette(game.ui))
        for t in terminals:
            out.append(("menu %s" % name, "look %s; %s" % (m.look_now(), t), runs_of(rows, t)))
    return out


def models(data, size=(60, 22), terminals=("full",)):
    """Each model as its look has it, and through each of its clips: ``[(title, note, runs)]``."""
    from . import viewer
    out = []
    for thing in viewer.things_of(data):
        if isinstance(thing, viewer.Planet):
            for t in terminals:
                out.append(("planet %s" % thing.name, t, runs_of(viewer.draw_planet(thing, "surface", size[0], size[1], 0.0), t)))
            continue
        view = thing.look.get("view") or "shaded"
        ink = None if thing.look.get("ink") else "green"
        for t in terminals:
            out.append(("model %s" % thing.name, "%s; %s" % (view, t),
                        runs_of(viewer.draw(thing, None, size[0], size[1], colour=ink), t)))
        for clip in thing.model.clips:
            for at in (0.0, 0.5, 1.0):
                out.append(("model %s  %s at %d%%" % (thing.name, clip, at * 100), "solid",
                            runs_of(viewer.draw(thing, "solid", size[0], size[1], colour=ink, clip=clip, at=at), terminals[0])))
    return out


def painter():
    """The editor's own painter of cells (engine/editor/web/app.js, between its marks): braille as dots,
    blocks and shades as boxes, frames as lines - each in its cell, whatever font the browser has."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "editor", "web", "app.js")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return text[text.index("// ---- cells: begin"):text.index("// ---- cells: end")]


def page(title, shots):
    """The page: each picture a canvas, painted cell by cell by the editor's painter when it comes into
    sight - so dots, blocks and frames stand in their cells in any browser."""
    import json
    parts = ["<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>%s</title><style>" % html.escape(title),
             "body{background:#06080c;color:%s;font:14px system-ui,sans-serif;margin:1.5rem}" % INK,
             "h1{font-size:1.3rem}h2{font-size:1rem;margin:2rem 0 .2rem}p{color:#8a93a3;margin:.1rem 0 .5rem}",
             "canvas.shot{background:%s;display:block;max-width:100%%}nav a{color:#7fb4ff;margin-right:1em}" % PAPER,
             "</style></head><body><h1>%s</h1><nav>" % html.escape(title)]
    seen = []
    for name, _note, _runs in shots:
        head = name.split("  ")[0]
        if head not in seen:
            seen.append(head)
            parts.append('<a href="#%s">%s</a>' % (html.escape(head.replace(" ", "-")), html.escape(head)))
    parts.append("</nav>")
    done, data = set(), []
    for name, note, runs in shots:
        head = name.split("  ")[0]
        anchor = ' id="%s"' % html.escape(head.replace(" ", "-")) if head not in done else ""
        done.add(head)
        cols = max([sum(len(r[0]) for r in row) for row in runs] or [1])
        parts.append("<h2%s>%s</h2><p>%s</p>" % (anchor, html.escape(name), html.escape(note)))
        if runs:
            parts.append('<canvas class="shot" data-n="%d" role="img" aria-label="%s" style="width:%dch;height:%dem"></canvas>'
                         % (len(data), html.escape(name), cols, len(runs) + 2))
            data.append({"rows": runs, "cols": cols, "lines": len(runs)})
    parts.append('<script type="application/json" id="shots">%s</script><script>\n%s\n' % (
        json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"), painter()))
    parts.append("""const SHOTS = JSON.parse(document.getElementById("shots").textContent);
const paint = (c) => { const s = SHOTS[+c.dataset.n]; c.style.height = ""; paintCells(c, s.rows, s.cols, s.lines - 2); };
const seen = new IntersectionObserver((es) => { for (const e of es) if (e.isIntersecting) { seen.unobserve(e.target); paint(e.target); } },
  { rootMargin: "600px" });
document.querySelectorAll("canvas.shot").forEach((c) => seen.observe(c));
</script></body></html>
""")
    return "".join(parts)


def write(game_dir, out_dir, size=(112, 34), terminals=("full",), say=print):
    """Draw the game's consoles, menus and models into ``out_dir``. Returns how many pictures."""
    from .audio import Silent
    from .game import Game
    from .term import Term
    term = Term(out=io.StringIO(), inp=lambda prompt: "", width=100, height=40, color=3, unicode=True, animate=False,
                env={}, glyphs="full")
    game = Game(game_dir, term=term, audio=Silent())
    shots = consoles(game.data, size, terminals) + menus(game, terminals=terminals) + models(game.data, terminals=terminals)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page("%s: its consoles, menus and models" % game.data.title, shots))
    for n, (name, note, runs) in enumerate(shots):
        slug = "%02d-%s" % (n + 1, "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-"))
        with open(os.path.join(out_dir, slug + ".txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("%s\n%s\n\n%s\n" % (name, note, plain(runs)))
    say("%d pictures of %s in %s (open index.html)." % (len(shots), game.data.title, out_dir))
    return len(shots)
