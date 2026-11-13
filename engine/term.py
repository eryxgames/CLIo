# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Terminal layer: capability detection, colour, inline markup, ANSI-aware wrapping.

Everything above this module talks in *markup* (``{red}text{/}``) and plain
strings; this module decides what the terminal can really show and degrades
gracefully: truecolor -> 256 colours -> 16 colours -> no colour, and
Unicode -> plain ASCII.  Nothing here needs anything beyond the standard library.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
import unicodedata

ESC = "\x1b"
RESET = ESC + "[0m"
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_TOKEN_RE = re.compile(r"(\x1b\[[0-9;?]*[A-Za-z]|\n|[ \t]+)")


class QuitGame(Exception):
    """Raised when the player quits or the input stream ends."""


# --------------------------------------------------------------------------- #
# Colour tables
# --------------------------------------------------------------------------- #

PALETTE = {
    "black": (0, 0, 0), "red": (205, 60, 60), "green": (80, 190, 90),
    "yellow": (220, 200, 80), "blue": (70, 120, 220), "magenta": (190, 90, 200),
    "cyan": (70, 200, 210), "white": (220, 220, 220), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "silver": (180, 180, 190), "darkgray": (72, 72, 80),
    "bred": (255, 95, 95), "bgreen": (120, 255, 130), "byellow": (255, 240, 110),
    "bblue": (110, 160, 255), "bmagenta": (255, 130, 255), "bcyan": (120, 245, 255),
    "bwhite": (255, 255, 255), "orange": (255, 150, 50), "pink": (255, 140, 180),
    "purple": (150, 100, 220), "teal": (40, 160, 150), "brown": (150, 100, 60),
    "gold": (255, 200, 60), "lime": (170, 240, 70), "navy": (40, 50, 110),
    "maroon": (130, 40, 50), "olive": (130, 130, 50), "sky": (130, 200, 255),
    "rust": (190, 90, 50), "steel": (110, 130, 150), "mint": (150, 240, 200),
    "amber": (255, 176, 0), "ice": (190, 230, 255), "blood": (160, 20, 30),
}

ATTRS = {
    "b": "1", "bold": "1", "dim": "2", "i": "3", "italic": "3",
    "u": "4", "underline": "4", "inv": "7", "reverse": "7", "blink": "5",
}

# xterm's 16 base colours (index -> rgb) used for nearest-colour fallback
_BASE16 = [
    (0, 0, 0), (170, 0, 0), (0, 170, 0), (170, 85, 0), (0, 0, 170), (170, 0, 170),
    (0, 170, 170), (170, 170, 170), (85, 85, 85), (255, 85, 85), (85, 255, 85),
    (255, 255, 85), (85, 85, 255), (255, 85, 255), (85, 255, 255), (255, 255, 255),
]
_CUBE = (0, 95, 135, 175, 215, 255)


def rgb_to_256(r, g, b):
    """Nearest xterm-256 index for an RGB colour (cube or grayscale ramp)."""
    def near(v):
        return min(range(6), key=lambda i: abs(_CUBE[i] - v))
    ri, gi, bi = near(r), near(g), near(b)
    cube = 16 + 36 * ri + 6 * gi + bi
    cr, cg, cb = _CUBE[ri], _CUBE[gi], _CUBE[bi]
    gray_level = round((r + g + b) / 3)
    gi2 = max(0, min(23, round((gray_level - 8) / 10)))
    gv = 8 + 10 * gi2
    d_cube = (cr - r) ** 2 + (cg - g) ** 2 + (cb - b) ** 2
    d_gray = (gv - r) ** 2 + (gv - g) ** 2 + (gv - b) ** 2
    return 232 + gi2 if d_gray < d_cube else cube


def idx256_to_rgb(n):
    n = int(n)
    if n < 16:
        return _BASE16[n]
    if n >= 232:
        v = 8 + 10 * (n - 232)
        return (v, v, v)
    n -= 16
    return (_CUBE[n // 36], _CUBE[(n // 6) % 6], _CUBE[n % 6])


def rgb_to_16(r, g, b):
    return min(range(16), key=lambda i: sum((a - c) ** 2 for a, c in zip(_BASE16[i], (r, g, b))))


def parse_hex(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(rgb):
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


# --------------------------------------------------------------------------- #
# Width helpers
# --------------------------------------------------------------------------- #

def strip_ansi(s):
    return ANSI_RE.sub("", s)


def char_width(ch):
    o = ord(ch)
    if o < 32 or 0x7F <= o < 0xA0:
        return 0
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def visible_len(s):
    """Number of terminal columns a string occupies (ANSI codes excluded)."""
    if ESC in s:
        s = strip_ansi(s)
    if s.isascii():
        return len(s)
    return sum(char_width(c) for c in s)


def pad_to(s, width, align="left"):
    """Pad a (possibly coloured) string with spaces to a visible width."""
    gap = width - visible_len(s)
    if gap <= 0:
        return s
    if align == "center":
        left = gap // 2
        return " " * left + s + " " * (gap - left)
    if align == "right":
        return " " * gap + s
    return s + " " * gap


def truncate(s, width, ellipsis="…"):
    """Cut a (possibly coloured) string to a visible width."""
    if visible_len(s) <= width:
        return s
    out, used, limit = [], 0, max(0, width - visible_len(ellipsis))
    i, n = 0, len(s)
    while i < n:
        m = ANSI_RE.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        w = char_width(s[i])
        if used + w > limit:
            break
        out.append(s[i])
        used += w
        i += 1
    tail = RESET if ESC in s else ""
    return "".join(out) + tail + ellipsis


def wrap_ansi(text, width, indent="", subsequent_indent=None):
    """Word-wrap text that may contain ANSI colour codes.

    Active colour codes are closed at the end of each line and re-opened on the
    next, so every returned line can be printed (or framed) independently.
    Hard newlines are kept; leading whitespace of a paragraph is preserved.
    """
    width = max(8, width)
    if subsequent_indent is None:
        subsequent_indent = indent
    lines = []
    active = []                      # SGR sequences currently in force
    state = {"ind": indent}

    for para in text.split("\n"):
        cur = list(active)
        cur_w = 0
        space = ""
        has_text = False
        emitted = False
        avail = max(4, width - visible_len(state["ind"]))

        def emit():
            nonlocal cur, cur_w, space, has_text, emitted, avail
            if has_text:
                lines.append(state["ind"] + "".join(cur) + (RESET if active else ""))
            else:
                lines.append("")
            state["ind"] = subsequent_indent
            avail = max(4, width - visible_len(subsequent_indent))
            cur = list(active)
            cur_w = 0
            space = ""
            has_text = False
            emitted = True

        for tok in _TOKEN_RE.split(para):
            if not tok:
                continue
            if tok[0] == ESC:
                if tok in (RESET, ESC + "[m"):
                    active = []
                elif tok.endswith("m"):
                    active.append(tok)
                if space and has_text and cur_w < avail - 1:
                    cur.append(space)       # keep the space outside the new colour
                    cur_w += 1
                    space = ""
                cur.append(tok)
                continue
            if tok.isspace():
                if has_text:
                    space = " "
                else:
                    lead = tok.replace("\t", "    ")
                    if len(lead) < avail - 4:
                        cur.append(lead)
                        cur_w += len(lead)
                continue
            w = visible_len(tok)
            if has_text and cur_w + len(space) + w > avail:
                emit()
            elif space:
                cur.append(space)
                cur_w += 1
            space = ""
            while w > avail - cur_w:            # longer than a whole line: hard split
                room = avail - cur_w
                if room <= 0:
                    emit()
                    continue
                piece, used = [], 0
                for ch in tok:
                    cw = char_width(ch)
                    if used + cw > room:
                        break
                    piece.append(ch)
                    used += cw
                if not piece:
                    emit()
                    continue
                cur.append("".join(piece))
                has_text = True
                tok = tok[len(piece):]
                w = visible_len(tok)
                emit()
            if tok:
                cur.append(tok)
                cur_w += w
                has_text = True
        if has_text or not emitted:
            emit()
    return lines or [""]


# --------------------------------------------------------------------------- #
# Glyph sets
# --------------------------------------------------------------------------- #

GLYPHS_UNICODE = {
    "bullet": "•", "arrow": "▸", "heart": "♥", "note": "♪", "star": "★",
    "bar_full": "█", "bar_part": "▓", "bar_empty": "░", "hr": "─", "vr": "│",
    "ellipsis": "…", "check": "✔", "cross": "✘", "dot": "·", "coin": "◆",
    "flag": "⚑", "shield": "◈", "sword": "†", "up": "▲", "down": "▼",
    "lock": "×", "player": "@", "block": "█",
}
GLYPHS_ASCII = {
    "bullet": "*", "arrow": ">", "heart": "HP", "note": "#", "star": "*",
    "bar_full": "#", "bar_part": "=", "bar_empty": "-", "hr": "-", "vr": "|",
    "ellipsis": "...", "check": "+", "cross": "x", "dot": ".", "coin": "$",
    "flag": "!", "shield": "D", "sword": "/", "up": "^", "down": "v",
    "lock": "x", "player": "@", "block": "#",
}

# Unicode frames and blocks, but plain ASCII for the symbols that some phone and
# console fonts lack or draw as oversized emoji.
GLYPHS_SAFE = dict(GLYPHS_UNICODE, **{
    "arrow": ">", "heart": "HP", "note": "~", "star": "*", "ellipsis": "...", "check": "+",
    "cross": "x", "coin": "$", "flag": "!", "shield": "#", "sword": "x", "up": "^", "down": "v",
    "lock": "x",
})

FRAMES = {
    # horizontal, vertical, top-left, top-right, bottom-left, bottom-right
    "SINGLE": "─│┌┐└┘",
    "DOUBLE": "═║╔╗╚╝",
    "ROUNDED": "─│╭╮╰╯",
    "HEAVY": "━┃┏┓┗┛",
    "ASCII": "-|++++",
    "DOTS": "·:····",
    "BLOCK": "▀█▛▜▙▟",
}

_ASCII_FALLBACK = str.maketrans({
    "─": "-", "━": "-", "═": "=", "│": "|", "┃": "|", "║": "|",
    "┌": "+", "┐": "+", "└": "+", "┘": "+", "╭": "+", "╮": "+", "╰": "+", "╯": "+",
    "╔": "+", "╗": "+", "╚": "+", "╝": "+", "┏": "+", "┓": "+", "┗": "+", "┛": "+",
    "├": "+", "┤": "+", "┬": "+", "┴": "+", "┼": "+", "╠": "+", "╣": "+", "╦": "+",
    "╩": "+", "╬": "+", "╞": "+", "╡": "+", "╪": "+", "╫": "+",
    "█": "#", "▓": "#", "▒": "%", "░": ":", "▀": '"', "▄": "_", "▌": "|", "▐": "|",
    "▛": "#", "▜": "#", "▙": "#", "▟": "#", "■": "#", "□": "o", "▪": ".", "▫": ".",
    "•": "*", "·": ".", "…": ".", "▸": ">", "◂": "<", "▲": "^", "▼": "v", "►": ">",
    "◄": "<", "♥": "v", "♪": "~", "★": "*", "☆": "*", "◆": "*", "◇": "o", "○": "o",
    "●": "O", "◉": "O", "◈": "*", "⚑": "!", "†": "+", "×": "x", "✔": "+", "✘": "x",
    "≈": "~", "∙": ".", "°": "o", "╱": "/", "╲": "\\", "╳": "X", "‖": "|", "═": "=",
    "╶": "-", "╴": "-", "╵": "|", "╷": "|", "⌂": "^", "∩": "n", "√": "v", "¤": "o",
    "«": "<", "»": ">", "—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"',
    "▁": "_", "▂": "_", "▃": "_", "▅": "=", "▆": "=", "▇": "#", "▔": "-", "▏": "|",
    "▕": "|", "◢": "/", "◣": "\\", "◤": "/", "◥": "\\", "∆": "^", "∞": "8",
})


def to_ascii(s):
    """Best-effort transliteration of the engine's Unicode glyphs to ASCII."""
    if s.isascii():
        return s
    s = s.translate(_ASCII_FALLBACK)
    if s.isascii():
        return s
    return unicodedata.normalize("NFKD", s).encode("ascii", "replace").decode("ascii")


# --------------------------------------------------------------------------- #
# Terminal
# --------------------------------------------------------------------------- #

def _enable_windows_vt():
    """Turn on ANSI escape processing in the Windows console. True on success."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if kernel32.SetConsoleMode(handle, mode.value | 0x0004):
            return True
    except Exception:
        pass
    return False


class Term:
    """What the terminal can do, plus the primitives to write to it."""

    def __init__(self, out=None, inp=None, width=None, height=None, color=None,
                 unicode=None, animate=None, env=None, glyphs=None):
        env = os.environ if env is None else env
        self.out = out if out is not None else sys.stdout
        self.inp = inp                      # callable(prompt) -> str, or None
        self.forced_width = width
        self.forced_height = height
        try:
            self.is_tty = bool(self.out.isatty()) and inp is None
        except Exception:
            self.is_tty = False
        self.interactive = self.is_tty
        # can we send escape sequences at all? (old Windows consoles and TERM=dumb cannot)
        self.ansi = self.is_tty
        if self.is_tty and os.name == "nt":
            self.ansi = _enable_windows_vt()
        elif env.get("TERM", "") == "dumb":
            self.ansi = False
        self.roles = {}                     # theme role -> colour spec
        self.speed = 1.0                    # 0 = instant, 2 = slow
        self._cache = {}
        self.at_line_start = True

        # ---- colour depth: 0 none, 1 = 16, 2 = 256, 3 = truecolor
        if color is None:
            color = self._detect_color(env)
        if self.is_tty and not self.ansi:
            color = 0
        self.color_depth = int(color)

        # ---- unicode
        if unicode is None:
            enc = (getattr(self.out, "encoding", None) or "").lower()
            unicode = "utf" in enc
            if env.get("CLIO_ASCII"):
                unicode = False
        self.unicode = bool(unicode)
        self.limited_glyphs = env.get("TERM", "") == "linux"   # kernel console font
        # symbol set: full | safe (frames and blocks stay, symbols become ASCII) | ascii
        mode = (glyphs or env.get("CLIO_GLYPHS") or "full").lower()
        if not self.unicode or mode == "ascii":
            mode = "ascii"
        elif mode != "safe":
            mode = "full"
        self.glyph_mode = mode
        self.glyphs = {"full": GLYPHS_UNICODE, "safe": GLYPHS_SAFE, "ascii": GLYPHS_ASCII}[mode]

        # ---- animation (typewriter, fades...) only on a real terminal
        if animate is None:
            animate = self.is_tty and not env.get("CLIO_FAST")
        self.animate = bool(animate) and (self.ansi or not self.is_tty)

    # -- detection --------------------------------------------------------- #
    def _detect_color(self, env):
        if env.get("NO_COLOR") is not None and env.get("NO_COLOR") != "":
            return 0
        forced = env.get("CLIO_COLOR") or env.get("FORCE_COLOR")
        if forced:
            try:
                return max(0, min(3, int(forced)))
            except ValueError:
                return 2
        if not self.is_tty:
            return 0
        term = env.get("TERM", "")
        if os.name == "nt":
            if not self.ansi:
                return 0
            return 3 if env.get("WT_SESSION") or "truecolor" in env.get("COLORTERM", "") else 2
        if term == "dumb":
            return 0
        if env.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
            return 3
        if "256" in term or "kitty" in term or "alacritty" in term:
            return 2
        if term in ("linux", "ansi", "vt100", "xterm", "screen", "cygwin"):
            return 1
        return 2 if term else 1

    # -- geometry ---------------------------------------------------------- #
    def size(self):
        cols, rows = self.forced_width, self.forced_height
        if cols is None or rows is None:
            sz = shutil.get_terminal_size(fallback=(80, 24))
            cols = cols or sz.columns
            rows = rows or sz.lines
        return max(24, int(cols)), max(8, int(rows))

    @property
    def cols(self):
        return self.size()[0]

    @property
    def rows(self):
        return self.size()[1]

    # -- output ------------------------------------------------------------ #
    def write(self, s):
        if not s:
            return
        if not self.unicode:
            s = to_ascii(s)
        try:
            self.out.write(s)
        except UnicodeEncodeError:
            self.out.write(to_ascii(s))
        self.at_line_start = s.endswith("\n")

    def line(self, s=""):
        self.write(s + "\n")

    def flush(self):
        try:
            self.out.flush()
        except Exception:
            pass

    def sleep(self, seconds):
        if self.animate and seconds > 0 and self.speed > 0:
            self.flush()
            time.sleep(seconds * self.speed)

    def cursor_up(self, n):
        if n > 0 and self.animate:
            self.write("%s[%dA\r" % (ESC, n))

    def clear_line(self):
        if self.animate:
            self.write("\r" + ESC + "[2K")

    def clear_screen(self):
        if self.is_tty and self.ansi:
            self.write(ESC + "[2J" + ESC + "[3J" + ESC + "[H")
            self.flush()

    def hide_cursor(self, hide=True):
        if self.animate:
            self.write(ESC + ("[?25l" if hide else "[?25h"))
            self.flush()

    def set_title(self, title):
        if self.is_tty and self.ansi and os.name != "nt":
            self.write("%s]0;%s\x07" % (ESC, title))

    # -- input ------------------------------------------------------------- #
    def read(self, prompt=""):
        """Read one line from the player. Raises QuitGame on end of input."""
        if self.inp is not None:
            self.write(prompt)
            self.flush()
            try:
                value = self.inp(prompt)
            except (EOFError, StopIteration):
                raise QuitGame()
            if value is None:
                raise QuitGame()
            self.write(str(value) + "\n")     # echo scripted input into the transcript
            return str(value)
        self.flush()
        try:
            if not self.unicode:
                prompt = to_ascii(prompt)
            value = input(prompt)
        except EOFError:
            raise QuitGame()
        if not self.is_tty:
            self.write(value + "\n")          # piped input: keep the transcript readable
        self.at_line_start = True
        return value

    # -- colour ------------------------------------------------------------ #
    def _fg(self, rgb=None, idx=None, bg=False):
        """SGR parameters for a colour at the current depth ('' if no colour)."""
        depth = self.color_depth
        if depth <= 0:
            return ""
        base = 48 if bg else 38
        if rgb is None and idx is not None:
            if depth >= 2:
                return "%d;5;%d" % (base, idx)
            rgb = idx256_to_rgb(idx)
        if depth >= 3:
            return "%d;2;%d;%d;%d" % ((base,) + tuple(rgb))
        if depth == 2:
            return "%d;5;%d" % (base, rgb_to_256(*rgb))
        i = rgb_to_16(*rgb)
        if bg:
            return str(40 + i) if i < 8 else str(100 + i - 8)
        return str(30 + i) if i < 8 else str(90 + i - 8)

    def _adapt_raw(self, code):
        """Adapt a raw SGR parameter string (legacy theme colours) to our depth."""
        depth = self.color_depth
        if depth <= 0:
            return ""
        if depth >= 2:
            return code
        parts = code.split(";")
        out, i = [], 0
        while i < len(parts):
            p = parts[i]
            if p in ("38", "48") and i + 2 < len(parts) and parts[i + 1] == "5":
                out.append(self._fg(idx=int(parts[i + 2]), bg=(p == "48")))
                i += 3
            elif p in ("38", "48") and i + 4 < len(parts) and parts[i + 1] == "2":
                rgb = tuple(int(x) for x in parts[i + 2:i + 5])
                out.append(self._fg(rgb=rgb, bg=(p == "48")))
                i += 5
            else:
                out.append(p)
                i += 1
        return ";".join(x for x in out if x)

    def spec_params(self, spec, _depth=0):
        """Translate a colour spec to SGR parameters, or None if not a spec.

        A spec is space-separated tokens: palette names (``red``), hex
        (``#ff8800``), 256-colour indexes (``208``), attributes (``b``, ``dim``,
        ``u``, ``inv``), backgrounds (``on_blue``, ``on_#102030``), theme roles
        (``item``), or a raw SGR string as used by legacy themes (``38;5;153``).
        """
        spec = spec.strip()
        if not spec:
            return None
        key = (spec, self.color_depth)
        if key in self._cache:
            return self._cache[key]
        params = []
        for tok in spec.split():
            low = tok.lower()
            bg = False
            if low.startswith("on_"):
                bg, low, tok = True, low[3:], tok[3:]
            if low in ATTRS and not bg:
                if self.color_depth > 0:
                    params.append(ATTRS[low])
            elif low in PALETTE:
                params.append(self._fg(rgb=PALETTE[low], bg=bg))
            elif re.fullmatch(r"#[0-9a-f]{3}([0-9a-f]{3})?", low):
                params.append(self._fg(rgb=parse_hex(low), bg=bg))
            elif low.startswith("sgr:") and re.fullmatch(r"\d+(;\d+)*", low[4:]):
                params.append(self._adapt_raw(low[4:]))
            elif re.fullmatch(r"\d{1,3}", low) and int(low) < 256:
                params.append(self._fg(idx=int(low), bg=bg))
            elif re.fullmatch(r"\d+(;\d+)+", low):
                params.append(self._adapt_raw(low))
            elif low in self.roles and _depth < 3 and not bg:
                sub = self.spec_params(self.role_spec(low), _depth + 1)
                if sub is None:
                    self._cache[key] = None
                    return None
                params.append(sub)
            else:
                self._cache[key] = None
                return None
        result = ";".join(p for p in params if p)
        self._cache[key] = result
        return result

    def role_spec(self, role):
        """Colour spec for a theme role. Legacy themes store raw SGR numbers."""
        spec = self.roles.get(role, "") or ""
        if re.fullmatch(r"\d+(;\d+)*", spec):
            return "sgr:" + spec
        return spec

    def style(self, spec):
        """Escape sequence for a colour spec ('' when colour is off/unknown)."""
        if self.color_depth <= 0 or not spec:
            return ""
        params = self.spec_params(spec)
        return "%s[%sm" % (ESC, params) if params else ""

    @property
    def reset(self):
        return RESET if self.color_depth > 0 else ""

    def paint(self, text, spec):
        """Wrap plain text in a colour spec."""
        code = self.style(spec)
        return code + text + RESET if code else text

    def set_roles(self, roles):
        self.roles = dict(roles)
        self._cache.clear()

    # -- markup ------------------------------------------------------------ #
    _MARKUP_RE = re.compile(r"\{\{|\}\}|\{(/?)([^{}\n]{0,48})\}")

    def markup(self, text, base=""):
        """Convert ``{spec}...{/}`` markup to ANSI.

        ``base`` is a colour spec applied to the whole string (text outside any
        tag, and restored after each closing tag).  ``{{`` is a literal brace.
        Braces that do not hold a valid spec are left untouched.
        """
        if "{" not in text and "}" not in text:
            return self.paint(text, base) if base else text
        base_code = self.style(base)
        stack = []
        out = [base_code]
        pos = 0
        for m in self._MARKUP_RE.finditer(text):
            out.append(text[pos:m.start()])
            pos = m.end()
            tok = m.group(0)
            if tok == "{{":
                out.append("{")
            elif tok == "}}":
                out.append("}")
            elif m.group(1) == "/":
                if m.group(2).strip() == "" or stack:
                    if stack:
                        stack.pop()
                    if self.color_depth > 0:
                        out.append(RESET + base_code + "".join(stack))
                else:
                    out.append(tok)
            else:
                params = self.spec_params(m.group(2)) if m.group(2).strip() else None
                if params is None:
                    out.append(tok)            # not markup: literal text
                else:
                    code = "%s[%sm" % (ESC, params) if (params and self.color_depth > 0) else ""
                    stack.append(code)
                    out.append(code)
        out.append(text[pos:])
        result = "".join(out)
        if self.color_depth > 0 and (base_code or ESC in result):
            result += RESET
        return result

    def strip_markup(self, text):
        """Remove markup tags, leaving the visible text."""
        saved = self.color_depth
        self.color_depth = 0
        try:
            # depth-0 cache keys differ, so this is safe
            return self.markup(text)
        finally:
            self.color_depth = saved


def is_termux(env=None):
    env = os.environ if env is None else env
    return bool(env.get("TERMUX_VERSION")) or "com.termux" in env.get("PREFIX", "")
