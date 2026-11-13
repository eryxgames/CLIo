# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""ASCII art files.

An ``.art`` file is plain text with optional sections::

    # comment lines start with '#'
    @palette
    h = steel            # one-letter key = colour spec
    w = b white
    @art
      .----.
     /  oo  \\
    @mask                # same shape as the art; each letter picks a colour
      hhhhhh
     h  ww  h
    @small               # optional narrower variant (with its own @mask)
     [oo]
    @frame               # optional extra animation frames (each may have @mask)
      .----.

Art without a ``@mask`` may use inline ``{colour}`` markup instead.  When a
drawing is wider than the space available the ``@small`` variant is used; if
that does not fit either, the art is simply left out.
"""
from __future__ import annotations

import os

from .term import visible_len


class Art:
    def __init__(self, name=""):
        self.name = name
        self.palette = {}
        self.variants = {}       # "art" | "small" -> (lines, mask_lines)
        self.frames = []         # extra animation frames: (lines, mask_lines)
        self.default_color = ""

    # -- parsing ----------------------------------------------------------- #
    @classmethod
    def parse(cls, text, name=""):
        art = cls(name)
        section, target = None, "art"
        buf = {"art": [], "small": []}
        masks = {"art": [], "small": []}
        frames = []
        for raw in text.splitlines():
            tag = raw.strip().lower()
            if tag in ("@palette", "@art", "@small", "@frame", "@mask") or tag.startswith("@color "):
                if tag == "@palette":
                    section = "palette"
                elif tag in ("@art", "@small"):
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
                line = raw.split(" #")[0]
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
        for key in ("art", "small"):
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

    # -- rendering --------------------------------------------------------- #
    def _render(self, term, lines, mask):
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
                    spec = self.palette.get(run_key, self.default_color) if run_key else self.default_color
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

    def render(self, term, max_width=None, max_height=None):
        """Rendered lines of the best-fitting variant ([] if nothing fits)."""
        for key in ("art", "small"):
            if key not in self.variants:
                continue
            lines, mask = self.variants[key]
            w = max(visible_len(term.strip_markup(l)) for l in lines)
            if (max_width is None or w <= max_width) and (max_height is None or len(lines) <= max_height):
                return self._render(term, lines, mask)
        return []

    def render_frames(self, term, max_width=None):
        """All animation frames (first is the base art) if they fit."""
        base = self.render(term, max_width)
        if not base or not self.frames or "art" not in self.variants:
            return [base] if base else []
        w = max(len(l) for l in self.variants["art"][0])
        if max_width is not None and w > max_width:
            return [base]
        return [base] + [self._render(term, l, m) for l, m in self.frames]


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
    """Loads and caches the ``.art`` files of a game."""

    def __init__(self, *dirs):
        self.dirs = [d for d in dirs if d]
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
        self._cache[name] = art
        return art
