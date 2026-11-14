# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Pixel sprites for the editor: grow one as the game would, and say what colour a palette entry is.

The game draws a character with ``"sprite": "auto"`` by growing a creature from
its name (``engine.sprite.generate``).  ``grow`` returns that same creature as
data that can be written into ``sprites.json`` and then drawn over by hand.
"""
from .. import sprite


def _hex(rgb):
    return None if rgb is None else "#%02x%02x%02x" % tuple(int(v) for v in rgb)


def grow(seed, size=12):
    """The sprite the game would grow from ``seed``, as ``{"palette": {letter: "#rrggbb"}, "pixels": [rows]}``."""
    size = max(6, min(32, int(size or 12)))
    made = sprite.generate(str(seed), size)
    used = set("".join(made.pixels))
    return {"palette": {k: _hex(v) for k, v in made.palette.items() if v is not None and k in used},
            "pixels": list(made.pixels)}


def colours(palette):
    """``{letter: "#rrggbb" or None}`` for a palette written in any way the engine accepts (names, numbers, hex)."""
    return {str(k): _hex(sprite._rgb(v)) for k, v in (palette or {}).items()}
