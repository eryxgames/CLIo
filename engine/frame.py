# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Frame mode: a picture redrawn in place instead of text that scrolls away.

CLIo normally scrolls.  A first-person level (:mod:`engine.level`) draws a
whole screen at a time, on the terminal's alternate screen (as ``less`` and
``vim`` do), and redraws it in place for every animation frame.  When the
level ends the normal scrollback comes back as it was.

The screen keeps CLIo's way of taking input - a typed line - and adds keys
that act at once (from :mod:`engine.keys`): a key bound in the keymap acts
while nothing is typed; any other key starts a line, finished with Enter.
Keys pressed during an animation go into the line being typed, and of the
action keys only the first waits, so a held arrow does not run on.

While it waits for a key it watches the window's size and draws everything
again at once when it changes (Windows has no signal for that, so it looks).
"""
from __future__ import annotations

import contextlib
import shutil
import sys
import time

from .term import rgb_to_16, rgb_to_256

ESC = "\x1b"
CSI = ESC + "["
RAMP = " .:-=+*#%@"

ROLE = {"text": (205, 205, 195), "dim": (130, 130, 124), "hurt": (255, 95, 85),
        "hit": (255, 215, 95), "alert": (255, 165, 60), "info": (150, 185, 210),
        "good": (140, 225, 120), "title": (240, 232, 210), "tag": (240, 240, 230),
        "aim": (255, 80, 80), "wind": (255, 165, 50), "charge": (255, 120, 200),
        "prompt": (120, 220, 160), "ammo": (240, 200, 90), "key_r": (235, 70, 60),
        "key_w": (240, 205, 60), "key_x": (80, 140, 255), "boss": (170, 120, 255),
        "secret": (210, 160, 255), "root": (255, 255, 255)}

# symbols a level draws; the full set keeps to fonts' common ground (WGL4) where it can
GLYPHS = {"heart": "♥", "armor": "◈", "ammo": "▪", "bar": "│", "dot": "·", "charge": "»",
          "rule": "─", "ell": "…", "fire": "●", "run": "»", "lr": "←→", "ud": "↑↓",
          "facing": "▲►▼◄", "block": "█", "half": "▀"}
SAFE_GLYPHS = dict(GLYPHS, armor="#", ammo="=", heart="HP", facing="^>v<")
ASCII_GLYPHS = {"heart": "HP", "armor": "AR", "ammo": "#", "bar": "|", "dot": ".", "charge": ">",
                "rule": "-", "ell": "~", "fire": "*", "run": ">", "lr": "<>", "ud": "^v",
                "facing": "^>v<", "block": "#", "half": "#"}


def mix(a, b, k):
    return (int(a[0] + (b[0] - a[0]) * k), int(a[1] + (b[1] - a[1]) * k), int(a[2] + (b[2] - a[2]) * k))


def shade(c, f):
    return (min(255, int(c[0] * f)), min(255, int(c[1] * f)), min(255, int(c[2] * f)))


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


class Painter:
    """Colours as escape codes, at whatever depth the terminal has (0 none, 1 = 16, 2 = 256, 3 = 24-bit)."""

    def __init__(self, depth):
        self.depth = depth
        self.cache = {}

    def sgr(self, fg, bg):
        key = (fg, bg)
        s = self.cache.get(key)
        if s is None:
            parts = ["0"]
            if self.depth == 3:
                if fg:
                    parts.append("38;2;%d;%d;%d" % fg)
                if bg:
                    parts.append("48;2;%d;%d;%d" % bg)
            elif self.depth == 2:
                if fg:
                    parts.append("38;5;%d" % rgb_to_256(*fg))
                if bg:
                    parts.append("48;5;%d" % rgb_to_256(*bg))
            elif self.depth == 1:
                if fg:
                    i = rgb_to_16(*fg)
                    parts.append(str(30 + i if i < 8 else 82 + i))
                if bg:
                    i = rgb_to_16(*bg)
                    parts.append(str(40 + i if i < 8 else 92 + i))
            s = CSI + ";".join(parts) + "m" if self.depth else ""
            self.cache[key] = s
        return s

    def text(self, segments, width, ell="…"):
        """``[(text, role or colour)]`` as one line of at most ``width`` visible characters."""
        out, used = [], 0
        for item in segments:
            text, role = item[0], item[1]
            bg = item[2] if len(item) > 2 else None
            if used >= width:
                break
            if used + len(text) > width:
                text = text[:max(0, width - used - len(ell))] + ell
            colour = ROLE.get(role, ROLE["text"]) if isinstance(role, str) else role
            out.append(self.sgr(colour, bg) + text)
            used += len(text)
        return "".join(out) + (CSI + "0m" if self.depth else "")

    def cells(self, row, unicode=True):
        """A row of cells ``(char, fg, bg)`` as escape codes; char None = two pixels (fg over bg)."""
        out, cur = [], None
        depth = self.depth
        for ch, fg, bg in row:
            if ch is None:
                if depth == 0 or not unicode:
                    c = mix(fg, bg, 0.5)
                    ch = RAMP[min(9, int(lum(c) / 255 * 10 * 1.7))]
                    fg, bg = (c if depth else None), None
                elif fg == bg:
                    ch, fg = " ", None
                else:
                    ch = "▀"
            elif depth == 0:
                fg = bg = None
            key = (fg, bg)
            if key != cur:
                out.append(self.sgr(fg, bg))
                cur = key
            out.append(ch)
        return "".join(out)


class Screen:
    """The terminal as one frame: rows written in place, a prompt, keys, pages."""

    def __init__(self, term, keys=None, keymap=None, animate=True, speed=1.0, out=None):
        self.term = term
        self.out = out or term.out or sys.stdout
        self.paint = Painter(term.color_depth)
        self.unicode = term.unicode
        mode = getattr(term, "glyph_mode", "full")
        self.glyphs = ASCII_GLYPHS if not term.unicode or mode == "ascii" else (SAFE_GLYPHS if mode == "safe" else GLYPHS)
        self.keys = keys                  # a KeyReader, or None for typed lines only (input())
        self.keymap = dict(keymap or {})
        self.animate = animate
        self.speed = speed
        self.typed = ""
        self.pending = None
        self.skip = False
        self.prompt_row = 1
        self.prompt_text = ""
        self.last_size = None
        self.started = False

    # ---- the terminal --------------------------------------------------- #
    def write(self, s):
        self.out.write(s)
        self.out.flush()

    def start(self):
        self.write(CSI + "?1049h" + CSI + "?25l" + CSI + "2J")
        if self.keys:
            self.keys.start()
        self.started = True

    def stop(self):
        if not self.started:
            return
        try:
            if self.keys:
                self.keys.stop()
        finally:
            self.write(CSI + "0m" + CSI + "?25h" + CSI + "?1049l")
            self.started = False

    def size(self):
        s = shutil.get_terminal_size((80, 24))
        return max(20, s.columns), max(10, s.lines)

    def resized(self):
        return self.size() != self.last_size

    # ---- drawing -------------------------------------------------------- #
    def frame(self, rows, prompt=None, status=None, footer=None):
        """Write ``rows`` (escape-coded lines) from the top; then the prompt line (or a status
        line) and a footer below it - which also keeps Enter from scrolling the screen."""
        W, H = self.size()
        clear = ""
        if (W, H) != self.last_size:
            clear = CSI + "2J"
            self.last_size = (W, H)
        rows = list(rows)
        self.prompt_row = min(H - 1, len(rows) + 1)
        if prompt is not None:
            self.prompt_text = prompt
            rows.insert(self.prompt_row - 1, self.paint.text([(prompt, "prompt"), (self.typed, "text")], W,
                                                             self.glyphs["ell"]))
        else:
            rows.insert(self.prompt_row - 1, self.paint.text([(status or "", "dim")], W, self.glyphs["ell"]))
        if footer is not None and self.prompt_row < H:
            rows.insert(self.prompt_row, footer)
        buf = [CSI + "?25l", clear]
        for i, r in enumerate(rows[:H]):
            buf.append("%s%d;1H%s%s0m%sK" % (CSI, i + 1, r, CSI, CSI))
        if prompt is not None:
            buf.append("%s%d;%dH%s?25h" % (CSI, self.prompt_row, min(W, len(prompt) + len(self.typed) + 1), CSI))
        self.write("".join(buf))

    def prompt_only(self):
        """Only the line being typed: cheap enough for every key."""
        W = self.last_size[0] if self.last_size else self.size()[0]
        line = self.paint.text([(self.prompt_text, "prompt"), (self.typed, "text")], W, self.glyphs["ell"])
        self.write("%s%d;1H%s%s0m%sK%s%d;%dH" % (CSI, self.prompt_row, line, CSI, CSI, CSI, self.prompt_row,
                                              min(W, len(self.prompt_text) + len(self.typed) + 1)))

    # ---- input ---------------------------------------------------------- #
    def read(self, redraw):
        """The next command line: typed, or the command of a key from the keymap.

        ``redraw()`` draws the whole frame with the prompt; it is called at the
        start and whenever the window changes size.  None at the end of input."""
        self.skip = False
        if self.keys is None:
            self.typed = ""
            redraw()
            try:
                return input()
            except EOFError:
                return None
        redraw()
        while True:
            k, self.pending = self.pending or self.keys.get(0.1), None
            if k is None:
                if self.resized():
                    redraw()
                continue
            if not self.typed and k in self.keymap:
                return self.keymap[k]
            if k == "enter":
                line, self.typed = self.typed, ""
                return line
            if k == "backspace":
                self.typed = self.typed[:-1]
            elif k in ("esc", "ctrl-u"):
                self.typed = ""
            elif k == "ctrl-d" and not self.typed:
                return None
            elif k == "space":
                self.typed += " "
            elif len(k) == 1 and k.isprintable():
                self.typed += k
            self.prompt_only()

    def wait(self, redraw):
        """Wait for Enter (or Space, Esc, q) on a page."""
        self.typed = ""
        if self.keys is None:
            redraw()
            try:
                input()
            except EOFError:
                pass
            return
        redraw()
        while True:
            k = self.keys.get(0.1)
            if k is None:
                if self.resized():
                    redraw()
                continue
            if k in ("enter", "space", "esc", "q", "ctrl-d", "tab"):
                return

    def typeahead(self, keys):
        typed, pending = self.typed, None
        for k in keys:
            if not typed and k in self.keymap:
                pending = pending or k
            elif k == "space":
                typed += " " if typed else ""
            elif k == "backspace":
                typed = typed[:-1]
            elif k in ("esc", "ctrl-u"):
                typed = ""
            elif len(k) == 1 and k.isprintable():
                typed += k
        self.typed, self.pending = typed, (None if typed else pending)

    @contextlib.contextmanager
    def busy(self):
        """While the world moves: no echo; keys pressed meanwhile are kept as typeahead."""
        if self.keys is not None:
            try:
                yield
            finally:
                self.typeahead(self.keys.drain())
            return
        fd, old = None, None
        try:
            import termios
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            new = termios.tcgetattr(fd)
            new[3] &= ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSANOW, new)
        except Exception:
            old = None
        try:
            yield
        finally:
            if old is not None:
                import termios
                termios.tcflush(fd, termios.TCIFLUSH)
                termios.tcsetattr(fd, termios.TCSANOW, old)
            else:
                try:
                    import msvcrt
                    while msvcrt.kbhit():
                        msvcrt.getwch()
                except Exception:
                    pass

    def play(self, frames, draw, dt):
        """Show animation frames: ``draw(fx)`` for each, ``dt`` seconds apart.  Ctrl-C skips the rest."""
        if not self.animate or self.skip:
            return
        try:
            for fx in frames:
                draw(fx)
                time.sleep(dt * self.speed)
        except KeyboardInterrupt:
            self.skip = True
