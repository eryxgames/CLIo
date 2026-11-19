# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Sheets: a game's pictures laid out on one PNG image, with an atlas that says where each one is.

    png, atlas = sheet(data, "monsters", scale=4)

``what`` is ``"monsters"`` (each monster in a row: standing, its two steps, its attack -
made by the engine when not drawn), ``"sprites"`` (every sprite of sprites.json) or
``"tiles"`` (the game's tiles and the engine's, with their frames). Each picture is drawn
``scale`` times as big, its name written under it in a small pixel font (``labels``).
The atlas is in the "JSON hash" form many engines read (TexturePacker's): ``frames``
(name -> where), ``animations`` (a monster's walk) and ``meta``. Only the standard
library: the PNG is written with :mod:`zlib`.
"""
from __future__ import annotations

import struct
import zlib

WHAT = ("monsters", "sprites", "tiles")
INK = (200, 200, 190, 255)                                   # names on a dark sheet
GREY = (128, 128, 124, 255)                                  # on a clear one: read on light and dark alike
DARK = (22, 22, 28, 255)

# A small pixel font, 3 x 5: enough for names.
_GLYPHS = {
    "a": "010101111101101", "b": "110101110101110", "c": "011100100100011", "d": "110101101101110",
    "e": "111100110100111", "f": "111100110100100", "g": "011100101101011", "h": "101101111101101",
    "i": "111010010010111", "j": "001001001101010", "k": "101101110101101", "l": "100100100100111",
    "m": "101111111101101", "n": "110101101101101", "o": "010101101101010", "p": "110101110100100",
    "q": "010101101110011", "r": "110101110101101", "s": "011100010001110", "t": "111010010010010",
    "u": "101101101101111", "v": "101101101101010", "w": "101101111111101", "x": "101101010101101",
    "y": "101101010010010", "z": "111001010100111", "0": "111101101101111", "1": "010110010010111",
    "2": "110001010100111", "3": "110001010001110", "4": "101101111001001", "5": "111100110001110",
    "6": "011100110101010", "7": "111001010010010", "8": "010101010101010", "9": "010101011001110",
    "-": "000000111000000", "_": "000000000000111", ".": "000000000000010", "/": "001001010100100",
    "(": "010100100100010", ")": "010001001001010", ":": "000010000010000", " ": "000000000000000",
    "#": "101111101111101", "+": "000010111010000", "'": "010010000000000",
}


def _rgb(value):
    from .sprite import _rgb as rgb
    return rgb(value)


def text_width(text, size):
    return max(0, len(text) * 4 * size - size)


def draw_text(img, x, y, text, size, colour=INK):
    for i, ch in enumerate(str(text).lower()):
        bits = _GLYPHS.get(ch, _GLYPHS["#"] if ch.strip() else _GLYPHS[" "])
        for k, b in enumerate(bits):
            if b == "1":
                gx, gy = x + (i * 4 + k % 3) * size, y + (k // 3) * size
                for yy in range(gy, gy + size):
                    for xx in range(gx, gx + size):
                        if 0 <= yy < len(img) and 0 <= xx < len(img[0]):
                            img[yy][xx] = colour


def png(img):
    """``img``: rows of ``(r, g, b, a)`` -> the bytes of a PNG file."""
    h, w = len(img), len(img[0]) if img else 0
    raw = bytearray()
    for row in img:
        raw.append(0)
        for px in row:
            raw.extend(px)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def _drawing(pixels, palette):
    """Letters and a palette -> rows of colours (None: clear)."""
    pal = {k: _rgb(v) for k, v in (palette or {}).items()}
    rows = [[pal.get(ch) for ch in r] for r in pixels if isinstance(r, str)]
    w = max((len(r) for r in rows), default=0)
    return [r + [None] * (w - len(r)) for r in rows]


def _monsters(data):
    from .sprite import walk_frames
    groups = []
    for kind, spec in (data.monsters or {}).items():
        if not isinstance(spec, dict):
            continue
        name = spec.get("sprite") or kind
        sp = (data.sprites or {}).get(name)
        if not isinstance(sp, dict) or not sp.get("pixels"):
            continue
        pal = sp.get("palette")
        frames = [(kind, _drawing(sp["pixels"], pal))]
        moves = not spec.get("float") and (spec.get("attack") or {}).get("kind") not in ("barrel", "spawner", "cron")
        if moves:
            walk = sp["walk"] if isinstance(sp.get("walk"), list) else walk_frames(sp["pixels"])
            frames += [("%s/step%d" % (kind, i + 1), _drawing(f, pal)) for i, f in enumerate(walk) if f]
        if sp.get("attack"):
            frames.append(("%s/attack" % kind, _drawing(sp["attack"], pal)))
        groups.append(frames)
    return groups


def _sprites(data):
    out = []
    for name, sp in (data.sprites or {}).items():
        if isinstance(sp, dict) and sp.get("pixels"):
            out.append((name, _drawing(sp["pixels"], sp.get("palette"))))
    return [out]


def _tiles(data):
    from .firstperson import TEXTURES, tile_frames
    out, own = [], data.tiles or {}
    for name, tl in own.items():
        if isinstance(tl, dict):
            for i, drawing in enumerate(tile_frames(tl)):
                out.append((name if not i else "%s/%d" % (name, i), drawing))
    for name, rows in TEXTURES.items():
        if name not in own:
            out.append((name, [[tuple(c) if c is not None else None for c in r] for r in rows]))
    return [out]


def sheet(data, what="monsters", scale=4, labels=True, background=None, width=1024):
    """``(png bytes, atlas)`` for one kind of picture of a game (``data``: :class:`engine.data.GameData`)."""
    if what not in WHAT:
        raise ValueError("A sheet is of %s." % ", ".join(WHAT))
    scale = max(1, min(16, int(scale or 1)))
    groups = {"monsters": _monsters, "sprites": _sprites, "tiles": _tiles}[what](data)
    font = max(1, scale // 2) if labels else 0
    pad = 2 * scale + 2
    caption = (5 * font + font + 2) if labels else 0
    places, x, y, row_h, W = [], pad, pad, 0, pad
    width = max(256, int(width or 1024))
    for frames in groups:                                 # each group starts a row; a long one wraps
        for name, drawing in frames:
            h, w = len(drawing), len(drawing[0]) if drawing else 0
            label = name.split("/")[-1] if "/" in name else name
            cw = max(w * scale, text_width(label, font) if labels else 0)
            ch = h * scale + caption
            if x > pad and x + cw + pad > width:
                x, y, row_h = pad, y + row_h + pad, 0
            places.append((name, label, drawing, x, y, w, h, cw))
            x += cw + pad
            row_h = max(row_h, ch)
            W = max(W, x)
        x, y, row_h = pad, y + row_h + pad, 0
    H = max(y, pad * 2)
    bg = tuple(background) if background else (0, 0, 0, 0)
    img = [[bg] * W for _ in range(H)]
    atlas = {"frames": {}, "animations": {}, "meta": {
        "app": "CLIo", "image": "%s-%s.png" % (data.id, what), "format": "RGBA8888",
        "size": {"w": W, "h": H}, "scale": str(scale)}}
    for name, label, drawing, px, py, w, h, cw in places:
        ox = px + (cw - w * scale) // 2
        for yy, r in enumerate(drawing):
            for xx, c in enumerate(r):
                if c is None:
                    continue
                colour = (c[0], c[1], c[2], 255)
                for sy in range(py + yy * scale, py + (yy + 1) * scale):
                    line = img[sy]
                    for sx in range(ox + xx * scale, ox + (xx + 1) * scale):
                        line[sx] = colour
        if labels:
            draw_text(img, px + (cw - text_width(label, font)) // 2, py + h * scale + font + 1, label, font,
                      INK if background else GREY)
        atlas["frames"][name] = {"frame": {"x": ox, "y": py, "w": w * scale, "h": h * scale}, "rotated": False,
                                 "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": w * scale, "h": h * scale},
                                 "sourceSize": {"w": w * scale, "h": h * scale}}
        if "/step" in name:
            atlas["animations"].setdefault(name.split("/")[0] + "/walk", []).append(name)
    return png(img), atlas
