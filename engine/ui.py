# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The renderer: frames, panels, lists, menus, the HUD and text effects.

All game output goes through :class:`UI`.  It lays text out for whatever width
the terminal has (a 40-column phone works), and plays effects - typewriter,
fade, glitch, flash, wipes - only on a real interactive terminal.  When output
is piped (tests, logs) everything is printed plainly and instantly.
"""
from __future__ import annotations

import math
import random

from .term import (RESET, ANSI_RE, FRAMES, pad_to, strip_ansi,
                   truncate, visible_len, wrap_ansi)

CANCEL_WORDS = {"", "0", "back", "exit", "cancel", "leave", "nevermind", "never mind",
                "bye", "q", "quit", "no", "n", "stop", "done"}
_NOISE = "▓▒░#%&$?/\\<>=+*"
_FRAME_CHARS = set("".join(FRAMES.values()))


class UI:
    def __init__(self, term, theme, audio=None):
        self.term = term
        self.theme = theme
        self.audio = audio
        self._last = "blank"        # blank | text | frame
        self._skip = False          # player pressed Ctrl-C during an effect
        self.effects_on = True
        self.apply_theme(theme)

    # ------------------------------------------------------------------ #
    # basics
    # ------------------------------------------------------------------ #
    def apply_theme(self, theme):
        self.theme = theme
        self.term.set_roles(theme.roles())

    @property
    def width(self):
        cols = self.term.cols
        if cols < 60 and self.term.forced_width is None:
            cols -= 1          # on a narrow screen keep the last column free: no accidental wraps
        return max(24, min(cols, int(self.theme.ui.get("max_width", 78))))

    @property
    def narrow(self):
        return self.width < 60

    @property
    def animated(self):
        return self.term.animate and self.effects_on and not self._skip and self.term.speed > 0

    def g(self, name):
        return self.term.glyphs.get(name, "")

    def line(self, s=""):
        self.term.line(s)
        self._last = "blank" if not strip_ansi(s).strip() else "text"

    def gap(self):
        """Make sure there is exactly one blank line before the next block."""
        if self._last != "blank":
            self.term.line("")
            self._last = "blank"

    def c(self, text, role):
        """Colour plain text with a theme role (or any colour spec)."""
        return self.term.paint(text, self.theme.color(role) if role in self.term.roles else role)

    def fmt(self, text, role="default"):
        """Markup -> ANSI, with the role's colour as the base."""
        return self.term.markup(str(text), self.theme.color(role))

    def wrap(self, text, role="default", width=None, indent="", subsequent_indent=None):
        width = width or self.width
        return wrap_ansi(self.fmt(text, role), width, indent, subsequent_indent)

    # ------------------------------------------------------------------ #
    # frames
    # ------------------------------------------------------------------ #
    def frame_chars(self, name):
        name = (name or "NONE").upper()
        if name in ("NONE", ""):
            return None
        if self.term.limited_glyphs and name in ("ROUNDED", "HEAVY", "BLOCK", "DOTS"):
            name = "SINGLE"
        return FRAMES.get(name, FRAMES["SINGLE"])

    def box_lines(self, lines, role="default", title=None, frame="SINGLE", padding=1,
                  align="left", width=None, footer=None):
        """Wrap already-rendered lines in a frame. Returns the framed lines."""
        ch = self.frame_chars(frame)
        width = width or self.width
        if not ch:
            return list(lines)
        h, v, tl, tr, bl, br = ch
        inner = width - 2 - 2 * padding
        col = self.theme.ui.get("frame_color") or self.theme.color(role)
        paint = lambda s: self.term.paint(s, col)   # noqa: E731

        def edge(left, right, label):
            if label:
                label = truncate(self.term.strip_markup(str(label)), max(4, width - 8))
                text = " " + label + " "
                fill = width - 2 - 1 - visible_len(text)
                return (paint(left + h) + self.term.paint(text, self.theme.color("key"))
                        + paint(h * max(0, fill) + right))
            return paint(left + h * (width - 2) + right)

        out = [edge(tl, tr, title)]
        pad = " " * padding
        for ln in lines:
            if visible_len(ln) > inner:
                ln = truncate(ln, inner)
            out.append(paint(v) + pad + pad_to(ln, inner, align) + pad + paint(v))
        out.append(edge(bl, br, footer))
        return out

    # ------------------------------------------------------------------ #
    # text output
    # ------------------------------------------------------------------ #
    def say(self, text, role="default", title=None, frame=None, align=None,
            effect=None, typewriter=None):
        """Print a message in the theme's style for ``role``.

        ``text`` may be a string, a list of paragraphs, or the legacy
        ``{"text": ..., "style": ...}`` form.
        """
        if isinstance(text, dict):
            role = text.get("style", role)
            text = text.get("text", "")
        if isinstance(text, (list, tuple)):
            text = "\n\n".join(str(t) for t in text if t)
        if text is None:
            return
        text = str(text)
        if not text.strip():
            return
        st = self.theme.style(role)
        frame_name = st["frame"] if frame is None else frame
        ch = self.frame_chars(frame_name)
        align = align or st["alignment"]
        margin = int(self.theme.ui.get("margin", 1))
        pad = min(st["padding"], 1 if self.narrow else 3)
        if ch:
            inner = self.width - 2 - 2 * pad
            lines = wrap_ansi(self.fmt(text, role), inner)
            if st["gradient"]:
                lines = self.gradient(lines, st["gradient"])
            block = self.box_lines(lines, role, title, frame_name, pad, align)
            self.gap()
        else:
            lines = wrap_ansi(self.fmt(text, role), self.width - margin, " " * margin)
            if align == "center":
                lines = [pad_to(l.strip(), self.width, "center").rstrip() for l in lines]
            if st["gradient"]:
                lines = self.gradient(lines, st["gradient"])
            if title:
                label = truncate(self.term.strip_markup(str(title)), self.width - margin)
                lines.insert(0, " " * margin + self.term.paint(label, self.theme.color("key")))
            block = lines
            if self._last == "frame":
                self.gap()

        delay = st["character_delay"]
        if typewriter is False:
            delay = 0
        if effect is None:
            effect = ("glitch" if st["glitch"] else "fade" if st["fade_in"] else None)
        self.emit(block, delay=delay, effect=effect, framed=bool(ch), flash=st["flash"])
        self._last = "frame" if ch else "text"
        if ch:
            self.gap()
        if st["paragraph_delay"] and self.animated:
            self.term.sleep(min(st["paragraph_delay"], 0.6))

    def emit(self, block, delay=0.0, effect=None, framed=False, flash=False):
        """Write a block of finished lines, optionally with an effect."""
        try:
            if not self.animated or len(block) >= self.term.rows - 2:
                self._plain(block)
                return
            if effect == "glitch":
                self._glitch(block)
            elif effect == "fade":
                self._fade(block)
            elif delay > 0:
                self._typewrite(block, delay, framed)
            else:
                self._plain(block)
            if flash:
                self._flash(block)
        except KeyboardInterrupt:
            # Ctrl-C skips the rest of this turn's animations
            self._skip = True
            self.term.write(RESET + "\n")
            self._plain(block)

    def _plain(self, block):
        self.term.write("\n".join(block) + "\n")
        self.term.flush()

    def _typewrite(self, block, delay, framed):
        term = self.term
        total = sum(visible_len(l) for l in block) or 1
        cap = float(self.theme.ui.get("typewriter_cap", 1.4))
        delay = min(delay, cap / total)
        tick = 0.004
        chunk = max(1, int(math.ceil(tick / delay))) if delay < tick else 1
        wait = max(delay, tick)
        for i, ln in enumerate(block):
            if framed and i in (0, len(block) - 1):
                term.write(ln + "\n")
                continue
            count = 0
            pos = 0
            for m in ANSI_RE.finditer(ln):
                count = self._type_run(ln[pos:m.start()], chunk, wait, count)
                term.write(m.group(0))
                pos = m.end()
            self._type_run(ln[pos:], chunk, wait, count)
            term.write("\n")
        term.flush()

    def _type_run(self, text, chunk, wait, count):
        term = self.term
        i = 0
        # frame borders and padding appear instantly; only words are "typed"
        while i < len(text):
            piece = text[i:i + chunk]
            term.write(piece)
            i += chunk
            if piece.strip() and not set(piece.strip()) <= _FRAME_CHARS:
                count += 1
                term.sleep(wait)
                if wait >= 0.012 and piece[-1] in ".!?":
                    term.sleep(wait * 5)
            if self._skip:
                term.write(text[i:])
                break
        return count

    def _recolor(self, block, spec):
        return [self.term.paint(strip_ansi(l), spec) for l in block]

    def _replay(self, frames, pause):
        n = len(frames[0])
        for fr in frames[:-1]:
            self._plain(fr)
            self.term.sleep(pause)
            self.term.cursor_up(n)
        self._plain(frames[-1])

    def _fade(self, block):
        if self.term.color_depth < 2:
            return self._plain(block)
        frames = [self._recolor(block, str(c)) for c in (236, 240, 245)] + [block]
        self._replay(frames, 0.05)

    def _glitch(self, block):
        rnd = random.Random(len(block) * 7 + visible_len(block[0]))
        plain = [strip_ansi(l) for l in block]
        frames = []
        for level in (0.5, 0.3, 0.15, 0.05):
            fr = []
            for l in plain:
                chars = [(_NOISE[rnd.randrange(len(_NOISE))] if (c != " " and rnd.random() < level) else c)
                         for c in l]
                fr.append(self.term.paint("".join(chars), "dim " + (self.theme.color("system") or "gray")))
            frames.append(fr)
        frames.append(block)
        self._replay(frames, 0.045)

    def _flash(self, block):
        n = len(block)
        inv = [self.term.paint(strip_ansi(l), "inv") for l in block]
        for _ in range(2):
            self.term.cursor_up(n)
            self._plain(inv)
            self.term.sleep(0.05)
            self.term.cursor_up(n)
            self._plain(block)
            self.term.sleep(0.05)

    def gradient(self, lines, colors=True):
        """Colour lines with a vertical gradient (list of 256-colour indexes)."""
        if self.term.color_depth < 2:
            return lines
        if not isinstance(colors, (list, tuple)):
            colors = self.theme.ui.get("title_gradient", [39, 45, 51, 87, 123])
        n = max(1, len(lines) - 1)
        out = []
        for i, l in enumerate(lines):
            c = colors[min(len(colors) - 1, int(round(i * (len(colors) - 1) / n)))]
            out.append(self.term.paint(strip_ansi(l), str(c)))
        return out

    # ------------------------------------------------------------------ #
    # composite blocks
    # ------------------------------------------------------------------ #
    def panel(self, parts, role="description", title=None, footer=None, frame=None,
              effect=None, delay=0.0):
        """A framed panel built from several parts.

        Each part is ``("text", markup, role)``, ``("art", lines)``,
        ``("lines", lines)`` or ``("rule",)``.
        """
        st = self.theme.style(role)
        frame_name = st["frame"] if frame is None else frame
        ch = self.frame_chars(frame_name)
        pad = min(st["padding"], 1 if self.narrow else 2)
        inner = self.width - (2 + 2 * pad if ch else 1)
        body = []
        for part in parts:
            kind = part[0]
            if kind == "text" and part[1]:
                prole = part[2] if len(part) > 2 else role
                body.extend(wrap_ansi(self.fmt(part[1], prole), inner))
            elif kind == "art" and part[1]:
                for l in part[1]:
                    body.append(pad_to(l, inner, "center") if visible_len(l) <= inner else truncate(l, inner))
            elif kind == "lines" and part[1]:
                body.extend(part[1])
            elif kind == "rule":
                body.append(self.term.paint(self.g("hr") * inner, "dim " + self.theme.color("system")))
            elif kind == "blank":
                body.append("")
        while body and not strip_ansi(body[-1]).strip():
            body.pop()
        if not body:
            return
        self.gap()
        if ch:
            block = self.box_lines(body, role, title, frame_name, pad, "left", footer=footer)
        else:
            label = truncate(self.term.strip_markup(str(title or "")), self.width - 1)
            block = ([" " + self.term.paint(label, self.theme.color("key"))] if title else []) + \
                    [" " + l for l in body]
        if effect is None:
            effect = "glitch" if st["glitch"] else "fade" if st["fade_in"] else None
        self.emit(block, delay=delay, effect=effect, framed=bool(ch))
        self._last = "frame"
        self.gap()

    def side_by_side(self, left, right, gap=2):
        """Merge two blocks of lines into columns."""
        lw = max((visible_len(l) for l in left), default=0)
        n = max(len(left), len(right))
        out = []
        for i in range(n):
            a = left[i] if i < len(left) else ""
            b = right[i] if i < len(right) else ""
            out.append(pad_to(a, lw) + " " * gap + b)
        return out

    def bullets(self, items, role="default", title=None, bullet=None, title_role=None):
        """A (possibly titled) bulleted list. Items are markup strings."""
        items = [i for i in items if i]
        if not items:
            return
        if self._last == "frame":
            self.gap()
        margin = " " * int(self.theme.ui.get("margin", 1))
        if title:
            for l in wrap_ansi(self.fmt(title, title_role or "list_category"), self.width - len(margin), margin):
                self.line(l)
        b = (bullet if bullet is not None else self.g("bullet")) + " "
        for it in items:
            for l in wrap_ansi(self.fmt(it, role), self.width - len(margin) - 1,
                               margin + " " + self.c(b, "system"), margin + " " + " " * len(b)):
                self.line(l)
        self._last = "text"

    def rule(self, label=None, role="system"):
        w = self.width
        h = self.g("hr")
        if label:
            text = " " + self.term.strip_markup(str(label)) + " "
            left = 2
            s = (self.c(h * left, role) + self.term.paint(text, self.theme.color("key"))
                 + self.c(h * max(0, w - left - visible_len(text)), role))
        else:
            s = self.c(h * w, role)
        self.line(s)

    def heading(self, text, role="list_title"):
        """A section title (framed or not, as the theme says)."""
        self.say(text, role, align=self.theme.style(role)["alignment"])

    def bar(self, value, maximum, width=10, spec="red", empty_spec="darkgray"):
        maximum = max(1, maximum)
        filled = int(round(width * max(0, min(value, maximum)) / float(maximum)))
        if value > 0 and filled == 0:
            filled = 1
        return (self.term.paint(self.g("bar_full") * filled, spec)
                + self.term.paint(self.g("bar_empty") * (width - filled), empty_spec))

    def table(self, rows, role="default", header=None):
        """Simple left-aligned columns. Cells are markup strings."""
        rendered = [[self.fmt(c, role) for c in r] for r in rows]
        if header:
            rendered.insert(0, [self.fmt(c, "list_category") for c in header])
        if not rendered:
            return
        ncol = max(len(r) for r in rendered)
        widths = [max((visible_len(r[i]) for r in rendered if i < len(r)), default=0) for i in range(ncol)]
        for r in rendered:
            cells = [pad_to(r[i], widths[i]) if i < len(r) - 1 else r[i] for i in range(len(r))]
            ln = " " + "  ".join(cells)
            self.line(truncate(ln, self.width))

    # ------------------------------------------------------------------ #
    # HUD, prompt, input
    # ------------------------------------------------------------------ #
    def hud(self, parts, right=""):
        """One status line: ``── ♥ 82/100 · Room · turn 12 ─────── ♪ ──``."""
        w = self.width
        h = self.g("hr")
        sep = self.c(" " + self.g("vr") + " ", "hud")
        body = sep.join(p for p in parts if p)
        if visible_len(body) > w - 8:                       # drop parts until it fits
            keep = list(p for p in parts if p)
            while len(keep) > 1 and visible_len(sep.join(keep)) > w - 8:
                keep.pop()
            body = truncate(sep.join(keep), w - 8)
        right_len = visible_len(right) + (2 if right else 0)
        fill = max(1, w - 4 - visible_len(body) - right_len - 2)
        s = self.c(h * 2 + " ", "hud") + body + " " + self.c(h * fill, "hud")
        if right:
            s += " " + right + " "
        s += self.c(h * 2, "hud")
        if self._last != "blank":
            self.term.line("")
        self.term.line(s)
        self._last = "text"

    def prompt(self, text=None):
        self._skip = False
        p = self.theme.ui.get("prompt", "> ") if text is None else text
        if self.term.glyph_mode != "full" and any(ord(c) > 0xFF for c in p):
            p = "".join(c if ord(c) <= 0xFF else ">" for c in p)
        value = self.term.read(self.term.paint(p, self.theme.color("prompt")))
        self._last = "text"
        return value

    def ask(self, question, role="menu"):
        """Ask for a free-text answer on one line."""
        self._skip = False
        lines = wrap_ansi(self.fmt(question, role), self.width - 4, " ")
        for l in lines[:-1]:
            self.term.line(l)
        last = lines[-1]
        if visible_len(last) > self.width - 12:      # leave room to type on a narrow screen
            self.term.line(last)
            last = " " + self.c(self.g("arrow"), "key")
        value = self.term.read(last + " ")
        self._last = "text"
        return value.strip()

    def confirm(self, question, default=False):
        ans = self.ask(question + " (y/n)").lower()
        if not ans:
            return default
        return ans in ("y", "yes", "yep", "yeah", "sure", "ok", "1")

    def pause(self, text=None):
        """Wait for Enter - only when a person is actually at the keyboard."""
        if not self.term.interactive:
            return
        self._skip = False
        msg = text or ("[Enter]" if self.narrow else "[press Enter]")
        self.term.read(" " + self.c(msg, "hint"))
        self._last = "blank"

    def menu(self, options, title=None, role="menu", cancel=True, prompt=None,
             cancel_label=None, aliases=None, compact=False):
        """Numbered menu. Returns the chosen index, or None if cancelled.

        The player may type the number, or any distinctive part of an option.
        """
        options = list(options)
        if not options:
            return None
        if self._last == "frame":
            self.gap()
        margin = " " * int(self.theme.ui.get("margin", 1))
        if title:
            self.line(margin + self.fmt(title, "list_category"))
        numw = len(str(len(options)))
        if compact:
            # one wrapped line: "1 Strike  2 Heavy  3 Guard" (used for repeated menus)
            # non-breaking spaces keep each number glued to its label while wrapping
            cells = ["%s\u00a0%s" % (self.c(str(i), "key"),
                                     self.fmt(self.term.strip_markup(opt).replace(" ", "\u00a0"), role))
                     for i, opt in enumerate(options, 1)]
            sep = " " + self.c(self.g("dot"), "hint") + " "
            for l in wrap_ansi(sep.join(cells), self.width - len(margin) - 1, margin + " "):
                self.line(l.replace("\u00a0", " "))
        for i, opt in enumerate(options if not compact else [], 1):
            num = self.c(("%*d" % (numw, i)) + ".", "key")
            ind = margin + " "
            for l in wrap_ansi(self.fmt(opt, role), self.width - len(ind) - numw - 2,
                               ind + num + " ", ind + " " * (numw + 2)):
                self.line(l)
        if cancel and cancel_label:
            self.line(margin + " " + self.c(("%*d" % (numw, 0)) + ".", "key") + " " + self.fmt(cancel_label, "hint"))
        plain = [self.term.strip_markup(o).lower() for o in options]
        ptxt = prompt or ("#" + self.theme.ui.get("prompt", "> "))
        for _ in range(6):
            raw = self.prompt(margin + ptxt).strip().lower()
            if raw in CANCEL_WORDS:
                if cancel:
                    return None
                if raw == "":
                    continue
            if aliases and raw in aliases:
                return aliases[raw]
            if raw.isdigit():
                n = int(raw)
                if 1 <= n <= len(options):
                    return n - 1
                self.say("Pick a number from 1 to %d." % len(options), "error")
                continue
            exact = [i for i, o in enumerate(plain) if o == raw]
            starts = [i for i, o in enumerate(plain) if o.startswith(raw)]
            words = [i for i, o in enumerate(plain) if raw in o.split()]
            inside = [i for i, o in enumerate(plain) if raw in o]
            for group in (exact, starts, words, inside):
                if len(group) == 1:
                    return group[0]
            self.say("Type the number of your choice%s." % (", or just press Enter to back out" if cancel else ""),
                     "error")
        return None

    # ------------------------------------------------------------------ #
    # set pieces
    # ------------------------------------------------------------------ #
    def transition(self):
        """A quick wipe between scenes (interactive terminals only)."""
        kind = self.theme.ui.get("transition", "wipe")
        if not self.animated or kind == "none":
            return
        w = self.width
        h = self.g("hr")
        term = self.term
        try:
            self.gap()
            steps = 8
            for i in range(1, steps + 1):
                n = w * i // steps
                term.write("\r" + self.c(h * n, "system"))
                term.sleep(0.012)
            for i in range(1, steps + 1):
                n = w * i // steps
                term.write("\r" + " " * n + self.c(h * (w - n), "system"))
                term.sleep(0.012)
            term.clear_line()
        except KeyboardInterrupt:
            self._skip = True
            term.clear_line()
        self._last = "blank"

    def starfield(self, width, height, seed=0, density=0.06, twinkle=0):
        """Lines of a random star field (procedural background art)."""
        rnd = random.Random(seed)
        stars = ".·'*+" if self.term.unicode else ".'*+"
        out = []
        for y in range(height):
            row = []
            for x in range(width):
                r = rnd.random()
                if r < density:
                    idx = rnd.randrange(len(stars))
                    if twinkle and (x * 7 + y * 13 + twinkle) % 5 == 0:
                        idx = (idx + twinkle) % len(stars)
                    row.append(stars[idx])
                else:
                    row.append(" ")
            out.append("".join(row))
        return out

    def title_screen(self, art_lines, title, subtitle="", credit=""):
        """Animated title card: art fades in over a twinkling star field."""
        term = self.term
        w = self.width
        art_lines = list(art_lines or [])
        art_h = len(art_lines)
        rows = max(art_h + 2, 5)
        if rows > term.rows - 6:
            rows = art_h
        top = (rows - art_h) // 2

        def compose(step, reveal):
            field = self.starfield(w, rows, seed=11, twinkle=step)
            out = []
            for y in range(rows):
                bg = self.term.paint(field[y], "darkgray" if (y + step) % 3 else "gray")
                ai = y - top
                if 0 <= ai < art_h and ai < reveal:
                    art = art_lines[ai]
                    aw = visible_len(art)
                    left = max(0, (w - aw) // 2)
                    out.append(self.term.paint(field[y][:left], "darkgray") + art
                               + self.term.paint(field[y][left + aw:], "darkgray"))
                else:
                    out.append(bg)
            return out

        self.gap()
        try:
            if self.animated and rows < term.rows - 4:
                term.hide_cursor(True)
                steps = art_h + 3
                for s in range(steps):
                    self._plain(compose(s, s))
                    term.sleep(0.06)
                    term.cursor_up(rows)
                self._plain(compose(0, art_h))
            else:
                self._plain(compose(0, art_h))
        except KeyboardInterrupt:
            self._skip = True
            term.write(RESET + "\n")
        finally:
            term.hide_cursor(False)
        self._last = "text"
        def centred(text, role):
            for l in wrap_ansi(self.fmt(text, role), w - 2):
                self.line(pad_to(l, w, "center").rstrip())

        if title:
            for l in wrap_ansi(title, w - 2):
                t = self.gradient([pad_to(l, w, "center").rstrip()])[0]
                self.line(self.term.style("b") + t)
        if subtitle:
            centred(subtitle, "ambient")
        if credit:
            centred(credit, "hint")
        self.gap()

    def clear(self):
        self.term.clear_screen()
        self._last = "blank"
