# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""ASCII art files.

An ``.art`` file is plain text with optional sections::

    # comment lines start with '#'
    @palette
    h = steel            # one-letter key = colour spec (' # ' after it starts a comment)
    w = #ffffff b        # hex colours may follow a space; '#fff on_#000' too
    @effect shine        # optional: how the art animates when it is shown (see engine/fx.py)
    @fps 8               # optional: speed of the @frame drawings
    @art
      .----.
     /  oo  \\
    @mask                # same shape as the art; each letter picks a colour
      hhhhhh
     h  ww  h
    @small               # optional narrower variant (with its own @mask)
     [oo]
    @ascii               # optional hand-made version for terminals without Unicode
     (oo)
    @frame               # optional extra animation frames (each may have @mask)
      .----.

Art without a ``@mask`` may use inline ``{colour}`` markup instead.  When a
drawing is wider than the space available the ``@small`` variant is used; if
that does not fit either, the art is simply left out.  Without Unicode the
``@ascii`` variant comes first, when there is one.
"""
from __future__ import annotations

import os
import re

from .term import visible_len

_TAGS = ("@palette", "@art", "@small", "@ascii", "@frame", "@mask")
# " #" starts a comment in a palette line - unless what follows is a hex colour
_COMMENT = re.compile(r"\s#(?![0-9a-fA-F]{6}\b|[0-9a-fA-F]{3}\b)")
ENGINE_ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art")
LOGO_DIR = os.path.join(ENGINE_ART, "logos")


class Art:
    def __init__(self, name=""):
        self.name = name
        self.palette = {}
        self.variants = {}       # "art" | "small" | "ascii" -> (lines, mask_lines)
        self.frames = []         # extra animation frames: (lines, mask_lines)
        self.default_color = ""
        self.effect = None       # {"name": ..., options} from an @effect line
        self.fps = 8.0           # speed of the @frame drawings

    # -- parsing ----------------------------------------------------------- #
    @classmethod
    def parse(cls, text, name=""):
        art = cls(name)
        section, target = None, "art"
        buf = {"art": [], "small": [], "ascii": []}
        masks = {"art": [], "small": [], "ascii": []}
        frames = []
        for raw in text.splitlines():
            tag = raw.strip().lower()
            if tag.startswith("@effect") and (len(tag) == 7 or tag[7] in " \t"):
                from . import fx
                art.effect = fx.parse(raw.strip()[len("@effect"):].strip())
                continue
            if tag.startswith("@fps ") or tag.startswith("@fps\t"):
                try:
                    art.fps = max(0.5, min(60.0, float(tag[4:].strip())))
                except ValueError:
                    pass
                continue
            if tag in _TAGS or tag.startswith("@color "):
                if tag == "@palette":
                    section = "palette"
                elif tag in ("@art", "@small", "@ascii"):
                    section, target = "art", tag[1:]
                elif tag == "@frame":
                    frames.append(([], []))
                    section, target = "art", len(frames) - 1
                elif tag == "@mask":
                    section = "mask"
                else:
                    art.default_color = raw.strip()[len("@color "):].strip()
                continue
            if section is None:
                if raw.startswith("#") or not raw.strip():
                    continue                    # preamble comments
                section = "art"
            if section == "palette":
                line = _COMMENT.split(raw, 1)[0]
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip():
                        art.palette[k.strip()[0]] = v.strip()
                continue
            if isinstance(target, int):
                dest = frames[target][0 if section == "art" else 1]
            else:
                dest = (buf if section == "art" else masks)[target]
            dest.append(raw)
        for key in ("art", "small", "ascii"):
            lines = _trim(buf[key])
            if lines:
                art.variants[key] = (lines, _trim_mask(masks[key], buf[key], len(lines)))
        for lines, mask in frames:
            trimmed = _trim(lines)
            if trimmed:
                art.frames.append((trimmed, _trim_mask(mask, lines, len(trimmed))))
        return art

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as f:
            return cls.parse(f.read(), os.path.splitext(os.path.basename(path))[0])

    def to_text(self, title=""):
        """The art as ``.art`` file text (what :meth:`parse` reads back)."""
        out = ["# " + (title or self.name or "art")]
        if self.default_color:
            out.append("@color " + self.default_color)
        if self.palette:
            out.append("@palette")
            for k, spec in self.palette.items():
                toks = spec.split()
                toks = [t for t in toks if t.startswith("#")] + [t for t in toks if not t.startswith("#")]
                out.append("%s=%s" % (k, " ".join(toks)))
        if self.effect:
            from . import fx
            out.append("@effect " + fx.describe(self.effect))
        if self.frames:
            out.append("@fps %g" % self.fps)
        sections = [("@" + k, self.variants[k]) for k in ("art", "small", "ascii") if k in self.variants]
        sections += [("@frame", fr) for fr in self.frames]
        for tag, (lines, mask) in sections:
            out.append(tag)
            out.extend(lines)
            if mask and any(m.strip() for m in mask):
                out.append("@mask")
                out.extend(m.rstrip() for m in mask)
        return "\n".join(out) + "\n"

    # -- rendering --------------------------------------------------------- #
    def _render(self, term, lines, mask, palette=None):
        palette = self.palette if palette is None else palette
        out = []
        width = max((visible_len(term.strip_markup(l)) for l in lines), default=0)
        for y, line in enumerate(lines):
            mrow = mask[y] if mask and y < len(mask) else ""
            if not mask:
                out.append(term.markup(line, self.default_color))
                continue
            parts, run, run_key = [], [], None

            def close():
                if run:
                    spec = palette.get(run_key, self.default_color) if run_key else self.default_color
                    parts.append(term.paint("".join(run), spec) if spec else "".join(run))

            for x, ch in enumerate(line):
                key = mrow[x] if x < len(mrow) and mrow[x] not in " ." else None
                if key != run_key:
                    close()
                    run, run_key = [], key
                run.append(ch)
            close()
            out.append("".join(parts))
        # pad to a rectangle so the block can be centred or put beside text
        return [l + " " * (width - visible_len(l)) for l in out]

    def size(self, variant="art"):
        lines = self.variants.get(variant, ([], None))[0]
        return (max((len(l) for l in lines), default=0), len(lines))

    def pick(self, term, max_width=None, max_height=None):
        """The variant that fits (``"art"``, ``"small"`` or ``"ascii"``), or None."""
        order = ("art", "small") if term.unicode else ("ascii", "art", "small")
        for key in order:
            if key not in self.variants:
                continue
            lines, _mask = self.variants[key]
            w = max(visible_len(term.strip_markup(l)) for l in lines)
            if (max_width is None or w <= max_width) and (max_height is None or len(lines) <= max_height):
                return key
        return None

    def render(self, term, max_width=None, max_height=None):
        """Rendered lines of the best-fitting variant ([] if nothing fits)."""
        key = self.pick(term, max_width, max_height)
        return self._render(term, *self.variants[key]) if key else []

    def render_frames(self, term, max_width=None):
        """All animation frames (first is the base art) if they fit."""
        base = self.render(term, max_width)
        if not base or not self.frames or "art" not in self.variants:
            return [base] if base else []
        w = max(len(l) for l in self.variants["art"][0])
        if max_width is not None and w > max_width:
            return [base]
        return [base] + [self._render(term, l, m) for l, m in self.frames]

    def animation(self, term, max_width=None, max_height=None, effect=None, seed=0):
        """How the art animates once it is on screen.

        Returns ``(frames, reveals)``: ``frames`` is a list of ``(lines, seconds)``
        that ends on the art itself, every frame the same size as the art;
        ``reveals`` is True when the animation starts from nothing (``type``),
        so the art should not be shown before it.  ``effect`` overrides the
        file's own ``@effect`` (``"none"`` turns it off); with neither, the
        ``@frame`` drawings play if there are any."""
        from . import fx
        key = self.pick(term, max_width, max_height)
        if key is None:
            return [], False
        spec = fx.parse(effect) if effect is not None else (self.effect or ({"name": "frames"} if self.frames else None))
        if not spec or spec["name"] == "none":
            return [], False
        lines, mask = self.variants[key]
        base = self._render(term, lines, mask)
        if spec["name"] == "frames":
            if key != "art" or not self.frames:
                return [], False
            delay = fx.seconds(1.0 / self.fps, spec)
            seq = [(self._render(term, l, m), delay) for l, m in self.frames] + [(base, delay)]
            frames = seq * max(1, min(20, int(spec.get("loops", 1) or 1)))
            reveals = bool(spec.get("reveal"))     # the frames build the picture up: do not show it first
        else:
            frames, reveals = fx.frames(spec, lines, mask, self.palette, self.default_color, term, seed,
                                        lambda l, m, p: self._render(term, l, m, p))
            if frames:
                frames = frames + [(base, 0.0)]
        return _fit_frames(frames, base), reveals


def _fit_frames(frames, base):
    """Every frame padded or cut to the size of the base drawing."""
    h = len(base)
    w = max((visible_len(l) for l in base), default=0)
    out = []
    for lines, secs in frames:
        lines = list(lines[:h]) + [""] * (h - len(lines))
        fixed = []
        for l in lines:
            n = visible_len(l)
            fixed.append(l + " " * (w - n) if n <= w else l)
        out.append((fixed, secs))
    return out


def _trim(lines):
    lines = list(lines)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return [l.rstrip() for l in lines]


def _trim_mask(mask, raw_lines, n):
    """Align a mask with its art: drop as many leading rows as the art lost."""
    if not any(m.strip() for m in mask):
        return None
    lead = 0
    for l in raw_lines:
        if l.strip():
            break
        lead += 1
    mask = list(mask)
    # masks are usually written without the blank lead-in; only strip blank rows
    while lead and mask and not mask[0].strip():
        mask.pop(0)
        lead -= 1
    return mask[:n]


class ArtLibrary:
    """Loads and caches the ``.art`` files of a game.  ``sprites`` (the game's
    sprites.json) are pictures too: a name with no file is looked up there."""

    def __init__(self, *dirs, sprites=None):
        self.dirs = [d for d in dirs if d]
        self.sprites = sprites if sprites is not None else {}
        self._cache = {}

    def get(self, name):
        if not name:
            return None
        if name in self._cache:
            return self._cache[name]
        art = None
        for d in self.dirs:
            for cand in (name, name + ".art", name + ".txt"):
                path = os.path.join(d, cand)
                if os.path.isfile(path):
                    try:
                        art = Art.load(path)
                    except (OSError, UnicodeDecodeError):
                        art = None
                    break
            if art:
                break
        if art is None and isinstance(self.sprites.get(name), dict) and self.sprites[name].get("pixels"):
            from .pixels import picture
            art = picture(self.sprites[name], name)
        self._cache[name] = art
        return art


# "clio" is engine/art/clio_logo.art (the terminal window); the rest are in engine/art/logos
# (a test keeps this list level with the folder)
LOGOS = ("clio", "classic", "badge", "braille", "chrome", "constellation", "glitch", "led", "neon", "pixel",
         "reflect", "shadow", "slant", "sword", "synthwave")
LOGO_ALIASES = {"terminal": "clio", "clio_logo": "clio", "default": "clio"}


def logo_names():
    """The CLIo logos a game or the launcher can choose (``"logo"`` in game.json, ``--logo``)."""
    names = list(LOGOS)
    if os.path.isdir(LOGO_DIR):
        names += sorted(n for n in (os.path.splitext(f)[0] for f in os.listdir(LOGO_DIR) if f.endswith(".art"))
                        if n not in names)
    return names


def load_logo(name=None):
    """A CLIo logo by name; ``None``, ``"clio"`` or ``"terminal"`` is the engine's own ``clio_logo.art``."""
    name = LOGO_ALIASES.get(name, name)
    if not name or name == "clio":
        return ArtLibrary(ENGINE_ART).get("clio_logo")
    return ArtLibrary(LOGO_DIR).get(name)
