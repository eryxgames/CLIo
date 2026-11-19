# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Sheets: a game's pictures laid out on one PNG image, with an atlas that says where each one is -
and the way back: a PNG read (:func:`read_png`), a picture made a sprite (:func:`to_sprite`), an
edited sheet taken back into the game (:func:`import_sheet`).

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


def _sum(drawing):
    """A short check of a drawing of colours: the same drawing, the same number."""
    flat = bytearray()
    for r in drawing:
        for c in r:
            flat.extend(c if c is not None else (1, 2, 3, 4))
        flat.append(255)
    return zlib.crc32(bytes(flat)) & 0xFFFFFFFF


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
    if background:                                        # a background no picture has: clear, when read back
        used = {c for p_ in places for r in p_[2] for c in r if c is not None}
        while bg[:3] in used:
            bg = (bg[0], bg[1], (bg[2] + 1) % 256, 255)
    img = [[bg] * W for _ in range(H)]
    atlas = {"frames": {}, "animations": {}, "meta": {
        "app": "CLIo", "image": "%s-%s.png" % (data.id, what), "format": "RGBA8888",
        "size": {"w": W, "h": H}, "scale": str(scale), "clio": {"what": what, "scale": scale, "game": data.id, "sums": {}}}}
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
        atlas["meta"]["clio"]["sums"][name] = _sum(drawing)
        atlas["frames"][name] = {"frame": {"x": ox, "y": py, "w": w * scale, "h": h * scale}, "rotated": False,
                                 "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": w * scale, "h": h * scale},
                                 "sourceSize": {"w": w * scale, "h": h * scale}}
        if "/step" in name:
            atlas["animations"].setdefault(name.split("/")[0] + "/walk", []).append(name)
    return png(img), atlas


# --------------------------------------------------------------------------- #
# Back in: a PNG read, a picture made a sprite, an edited sheet taken back
# --------------------------------------------------------------------------- #
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


class PictureError(ValueError):
    """A picture that cannot be read or used, said in words for the person."""


def read_png(data):
    """The bytes of a PNG file -> ``(width, height, rows of (r, g, b, a))``.

    Every colour type, 1 to 16 bits (16 is read as its top 8), palettes with transparency;
    not interlaced pictures (saved "progressive")."""
    if not isinstance(data, (bytes, bytearray)) or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise PictureError("That is not a PNG file.")
    pos, head, plte, trns, idat = 8, None, b"", None, []
    while pos + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if not head:
        raise PictureError("The PNG file has no header.")
    w, h, depth, ctype, _, _, interlace = head
    if interlace:
        raise PictureError("The PNG is interlaced: save it again without interlacing (not \"progressive\").")
    if not w or not h or w * h > 4096 * 4096:
        raise PictureError("The picture is too big (%d x %d)." % (w, h))
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if channels is None or depth not in (1, 2, 4, 8, 16) or (depth < 8 and ctype not in (0, 3)) \
            or (depth == 16 and ctype == 3):
        raise PictureError("This kind of PNG cannot be read (colour type %d, %d bits)." % (ctype, depth))
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error:
        raise PictureError("The PNG file is damaged.")
    bpp = max(1, channels * depth // 8)
    stride = (w * channels * depth + 7) // 8
    if len(raw) < h * (stride + 1):
        raise PictureError("The PNG file is cut short.")
    pal = [tuple(plte[k:k + 3]) for k in range(0, len(plte) - 2, 3)]
    alpha = list(trns) if (trns and ctype == 3) else []
    key = None
    if trns and ctype == 0 and len(trns) >= 2:
        key = struct.unpack(">H", trns[:2])[0]
    elif trns and ctype == 2 and len(trns) >= 6:
        key = struct.unpack(">HHH", trns[:6])
    top = (1 << depth) - 1
    rows, prev, at = [], bytearray(stride), 0
    for _ in range(h):
        f, line = raw[at], bytearray(raw[at + 1:at + 1 + stride])
        at += 1 + stride
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b, c = prev[x], (prev[x - bpp] if x >= bpp else 0)
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        elif f:
            raise PictureError("The PNG file is damaged (filter %d)." % f)
        prev = line
        if depth == 16:
            full = [(line[k] << 8) | line[k + 1] for k in range(0, len(line), 2)]
            vals = [v >> 8 for v in full]
        elif depth == 8:
            full = vals = line
        else:
            per = 8 // depth
            vals = [(byte >> (8 - depth * (k + 1))) & top for byte in line for k in range(per)][:w * channels]
            full = vals
        row = []
        for x in range(w):
            s = vals[x * channels:(x + 1) * channels]
            if ctype == 3:
                i = s[0]
                r, g, b = pal[i] if i < len(pal) else (0, 0, 0)
                row.append((r, g, b, alpha[i] if i < len(alpha) else 255))
            elif ctype == 0:
                v = s[0] * 255 // top if depth < 8 else s[0]
                row.append((v, v, v, 0 if key is not None and full[x] == key else 255))
            elif ctype == 4:
                row.append((s[0], s[0], s[0], s[1]))
            elif ctype == 2:
                hit = key is not None and tuple(full[x * 3:x * 3 + 3]) == key
                row.append((s[0], s[1], s[2], 0 if hit else 255))
            else:
                row.append((s[0], s[1], s[2], s[3]))
        rows.append(row)
    return w, h, rows


def _block(px):
    """How many times as big a pixel picture is drawn: the size of the squares of one colour it is made of."""
    from math import gcd
    h, w = len(px), len(px[0]) if px else 0
    g = 0
    for line in px + [list(col) for col in zip(*px)]:
        run = 1
        for a, b in zip(line, line[1:]):
            if a == b:
                run += 1
            else:
                g = gcd(g, run)
                run = 1
                if g == 1:
                    return 1
        g = gcd(g, run)
    for k in sorted((d for d in range(2, min(g, 32) + 1) if g % d == 0), reverse=True):
        if w % k or h % k:
            continue
        if all(px[y][x] == px[y - y % k][x - x % k] for y in range(h) for x in range(w)):
            return k
    return 1


def _shrink(px, W, H):
    """A picture made ``W`` x ``H``: each new pixel the mean of what it covers, clear when mostly clear."""
    h, w = len(px), len(px[0])
    out = []
    for Y in range(H):
        y0, y1 = Y * h // H, max(Y * h // H + 1, (Y + 1) * h // H)
        row = []
        for X in range(W):
            x0, x1 = X * w // W, max(X * w // W + 1, (X + 1) * w // W)
            seen = [px[y][x] for y in range(y0, y1) for x in range(x0, x1)]
            solid = [c for c in seen if c is not None]
            if len(solid) * 2 < len(seen):
                row.append(None)
            else:
                n = len(solid)
                row.append(tuple(sum(c[i] for c in solid) // n for i in range(3)))
        out.append(row)
    return out


def _fewer(px, colours):
    """At most ``colours`` colours (median cut, weighted by how much of each there is)."""
    count = {}
    for r in px:
        for c in r:
            if c is not None:
                count[c] = count.get(c, 0) + 1
    if len(count) <= colours:
        return px
    boxes = [list(count)]
    while len(boxes) < colours:
        def spread(box):
            return max(max(c[i] for c in box) - min(c[i] for c in box) for i in range(3)) * sum(count[c] for c in box)
        box = max((b for b in boxes if len(b) > 1), key=spread, default=None)
        if box is None:
            break
        ch = max(range(3), key=lambda i: max(c[i] for c in box) - min(c[i] for c in box))
        box.sort(key=lambda c: c[ch])
        total, run, cut = sum(count[c] for c in box), 0, 1
        for i, c in enumerate(box):
            run += count[c]
            if run * 2 >= total:
                cut = max(1, min(len(box) - 1, i + 1))
                break
        boxes.remove(box)
        boxes += [box[:cut], box[cut:]]
    means = []
    for box in boxes:
        n = sum(count[c] for c in box)
        means.append(tuple(round(sum(c[i] * count[c] for c in box) / n) for i in range(3)))
    near = {c: min(means, key=lambda m: sum((a - b) ** 2 for a, b in zip(c, m))) for c in count}
    return [[near[c] if c is not None else None for c in r] for r in px]


def lettered(drawings, base=None, keep_all=False, near=6):
    """Drawings of colours -> ``(drawings of letters, palette)``. A colour within ``near`` of one of the
    ``base`` palette's keeps that letter; new colours get letters not yet used. With ``keep_all`` the base
    palette is kept whole (other drawings use it), otherwise only what is used."""
    base = dict(base or {})
    known = {k: _rgb(v) for k, v in base.items()}
    count = {}
    for d in drawings:
        for r in d:
            for c in r:
                if c is not None:
                    count[c] = count.get(c, 0) + 1
    letter, pal = {}, dict(base) if keep_all else {}
    free = [ch for ch in LETTERS if ch not in base]
    for c in sorted(count, key=lambda c: -count[c]):
        best = min(known, key=lambda k: max(abs(a - b) for a, b in zip(known[k], c)), default=None)
        if best is not None and max(abs(a - b) for a, b in zip(known[best], c)) <= near:
            letter[c] = best
            if best in base:
                pal[best] = base[best]
        elif free:
            ch = free.pop(0)
            letter[c] = ch
            pal[ch] = "#%02x%02x%02x" % c
            known[ch] = c
        else:                                         # no letters left: the nearest colour there is
            letter[c] = min(known, key=lambda k: sum((a - b) ** 2 for a, b in zip(known[k], c)))
    return [["".join(letter[c] if c is not None else "." for c in r) for r in d] for d in drawings], pal


def _flood(px, x, y, near=24, back=None):
    """Clear the colour at (x, y) (or ``back``) and every pixel of about that colour joined to it (corners too)."""
    h, w = len(px), len(px[0])
    if not (0 <= x < w and 0 <= y < h) or px[y][x] is None:
        return
    back, todo = back or px[y][x], [(x, y)]
    while todo:
        x, y = todo.pop()
        if not (0 <= x < w and 0 <= y < h):
            continue
        c = px[y][x]
        if c is None or max(abs(a - b) for a, b in zip(c, back)) > near:
            continue
        px[y][x] = None
        todo += [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def _specks(px):
    """Clear the small islands (dust, noise) apart from the picture: under 2% of the biggest, at least 2 pixels."""
    h, w = len(px), len(px[0])
    seen, parts = set(), []
    for y in range(h):
        for x in range(w):
            if px[y][x] is None or (x, y) in seen:
                continue
            part, todo = [], [(x, y)]
            seen.add((x, y))
            while todo:
                cx, cy = todo.pop()
                part.append((cx, cy))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < w and 0 <= ny < h and px[ny][nx] is not None and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            todo.append((nx, ny))
            parts.append(part)
    if len(parts) < 2:
        return
    small = max(2, max(len(p_) for p_ in parts) // 50)
    for part in parts:
        if len(part) < small:
            for x, y in part:
                px[y][x] = None


def to_sprite(rows, height=None, colours=16, clear="alpha", base=None, outline=False, limit=64, clear_at=(),
              specks=True):
    """A picture (rows of ``(r, g, b, a)``) as a sprite: ``{"pixels", "palette", "scale", "colours"}``.

    Clear is what is see-through; with ``clear="edges"`` also the commonest colour round its edges,
    as far as it reaches from them (a picture on a plain background), and the colour at each point of ``clear_at``
    (``(x, y)`` of the picture: a click on its background), with its like joined to it. Small
    islands left apart are dust (``specks``). The picture is cut to what is drawn; a pixel picture
    drawn bigger (every pixel a square of 4 x 4, say) is taken back to its own pixels; one higher
    than ``height`` (or wider or higher than ``limit``) is made smaller; it is given at most
    ``colours`` colours, the ``base`` palette's letters kept for the colours it has, and with
    ``outline`` a dark line round it."""
    px = [[(c[0], c[1], c[2]) if len(c) < 4 or c[3] >= 128 else None for c in r] for r in rows]
    if not px or not px[0]:
        raise PictureError("The picture is empty.")
    h, w = len(px), len(px[0])
    if clear in ("edges", "corners"):                  # the background: the commonest colour round the edges
        edge = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + \
               [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
        seen = {}
        for x, y in edge:
            c = px[y][x]
            if c is not None:
                k = tuple(v // 16 for v in c)
                seen.setdefault(k, []).append(c)
        if seen:
            most = max(seen.values(), key=len)
            back = tuple(sum(c[i] for c in most) // len(most) for i in range(3))
            for x, y in edge:
                c = px[y][x]
                if c is not None and max(abs(a - b) for a, b in zip(c, back)) <= 24:
                    _flood(px, x, y, back=back)
    for point in clear_at or ():
        try:
            _flood(px, int(point[0]), int(point[1]))
        except (TypeError, ValueError, IndexError):
            continue
    if specks:
        _specks(px)
    ys = [y for y in range(h) if any(c is not None for c in px[y])]
    xs = [x for x in range(w) if any(px[y][x] is not None for y in range(h))]
    if not ys:
        raise PictureError("Everything in the picture is clear.")
    px = [r[xs[0]:xs[-1] + 1] for r in px[ys[0]:ys[-1] + 1]]
    k = _block(px)
    if k > 1:
        px = [r[::k] for r in px[::k]]
    h, w = len(px), len(px[0])
    room = limit - (2 if outline else 0)
    want = min(h, int(height) if height else h)
    s = min(1.0, want / float(h), room / float(h), room / float(w))
    if s < 1.0:
        px = _shrink(px, max(1, round(w * s)), max(1, round(h * s)))
    px = _fewer(px, max(2, min(int(colours or 16), len(LETTERS))))
    if outline:
        h, w = len(px), len(px[0])
        big = [[None] * (w + 2)] + [[None] + r + [None] for r in px] + [[None] * (w + 2)]
        solid = [c for r in px for c in r if c is not None]
        ink = min(solid, key=sum)
        ink = tuple(max(0, v // 3) for v in ink)
        line = [(x, y) for y in range(h + 2) for x in range(w + 2)
                if big[y][x] is None and any(0 <= y + dy < h + 2 and 0 <= x + dx < w + 2 and big[y + dy][x + dx] is not None
                                             for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        for x, y in line:
            big[y][x] = ink
        px = big
    (pixels,), pal = lettered([px], base)
    return {"pixels": pixels, "palette": pal, "scale": k, "colours": len(pal)}


def from_rgba(data, w, h):
    """Bytes of RGBA, row after row (as a browser's canvas gives them) -> rows of ``(r, g, b, a)``."""
    w, h = int(w), int(h)
    if w <= 0 or h <= 0 or w * h > 4096 * 4096 or len(data) < w * h * 4:
        raise PictureError("The picture's pixels do not match its size.")
    return [[tuple(data[(y * w + x) * 4:(y * w + x) * 4 + 4]) for x in range(w)] for y in range(h)]


def _frame(rows, rect, scale, back):
    """One picture of a sheet, back at its own size: each square of ``scale`` x ``scale`` is its most
    common colour (clear where the sheet is see-through, or of the sheet's own background ``back``;
    ``back`` False: the background colour taken as a colour)."""
    x0, y0, fw, fh = (int(rect[k]) for k in ("x", "y", "w", "h"))
    out = []
    for y in range(0, fh, scale):
        row = []
        for x in range(0, fw, scale):
            votes = {}
            for yy in range(y0 + y, min(y0 + y + scale, len(rows))):
                for xx in range(x0 + x, min(x0 + x + scale, len(rows[yy]))):
                    c = rows[yy][xx]
                    key = None if c[3] < 128 or (back and tuple(c[:3]) == back) else tuple(c[:3])
                    votes[key] = votes.get(key, 0) + 1
            row.append(max(votes, key=lambda c: (votes[c], c is not None)) if votes else None)
        out.append(row)
    return out


def import_sheet(files, rows, atlas):
    """An edited sheet taken back: ``files`` (``{"sprites": ..., "tiles": ..., "monsters": ...}``, the
    game's data), ``rows`` the sheet's pixels, ``atlas`` the JSON written with it. Only what was changed
    is taken in. Returns ``{"files": {key: data that changed}, "report": {"changed": [...], "same": n,
    "skipped": [...], "unknown": [...]}}``."""
    import copy
    from .sprite import walk_frames
    meta = atlas.get("meta") or {} if isinstance(atlas, dict) else {}
    frames = atlas.get("frames") if isinstance(atlas, dict) else None
    if not isinstance(frames, dict) or not frames:
        raise PictureError("That atlas lists no pictures: take the JSON written with the sheet.")
    own = meta.get("clio") or {}
    what = own.get("what") or next((k for k in WHAT if str(meta.get("image", "")).endswith("-%s.png" % k)), None)
    if what not in WHAT:
        raise PictureError("The atlas does not say what kind of sheet it is (monsters, sprites or tiles).")
    try:
        scale = max(1, int(own.get("scale") or meta.get("scale") or 1))
    except (TypeError, ValueError):
        scale = 1
    size = meta.get("size") or {}
    if size and (size.get("w") != len(rows[0]) or size.get("h") != len(rows)):
        raise PictureError("The picture is %d x %d, but the atlas is of one %s x %s: is it the sheet it was written with?"
                           % (len(rows[0]), len(rows), size.get("w"), size.get("h")))
    corner = rows[0][0]
    back = tuple(corner[:3]) if corner[3] >= 128 else None
    sums = own.get("sums") if isinstance(own.get("sums"), dict) else {}
    sprites = copy.deepcopy(files.get("sprites") or {})
    tiles = copy.deepcopy(files.get("tiles") or {})
    monsters = files.get("monsters") or {}
    report = {"changed": [], "same": 0, "skipped": [], "unknown": []}
    touched = set()

    def drawing_of(pixels, palette):
        return [[c for c in r] for r in _drawing(pixels, palette)]

    def take(name, now_pixels, palette, put):
        """Compare the sheet's picture ``name`` with the drawing it was made from; if changed, ``put`` it."""
        rect = (frames.get(name) or {}).get("frame")
        if not rect:
            return False
        new = _frame(rows, rect, scale, back)
        if name in sums and _sum(new) == sums[name]:          # not painted over since it was written
            report["same"] += 1
            return False
        old = drawing_of(now_pixels, palette)
        if (len(new), len(new[0]) if new else 0) != (len(old), len(old[0]) if old else 0):
            report["skipped"].append("%s: drawn %d x %d on the sheet, but %d x %d in the game now"
                                     % (name, len(new[0]) if new else 0, len(new), len(old[0]) if old else 0, len(old)))
            return False
        (letters,), pal = lettered([new], palette, keep_all=True)
        if drawing_of(letters, pal) == old:
            report["same"] += 1
            return False
        put(letters, pal)
        report["changed"].append(name)
        return True

    if what == "monsters":
        for kind, spec in monsters.items():
            if not isinstance(spec, dict):
                continue
            name = spec.get("sprite") or kind
            sp = sprites.get(name)
            if not isinstance(sp, dict) or not sp.get("pixels") or kind not in frames:
                continue
            before = list(sp["pixels"])

            def put_base(letters, pal, sp=sp):
                sp["pixels"], sp["palette"] = letters, pal
            if take(kind, sp["pixels"], sp.get("palette"), put_base):
                touched.add("sprites")
            walk = sp["walk"] if isinstance(sp.get("walk"), list) else walk_frames(before)
            steps = [n for n in ("%s/step1" % kind, "%s/step2" % kind) if n in frames]
            new_walk, changed = list(walk), False
            for i, n in enumerate(steps):
                if i < len(walk):
                    def put_step(letters, pal, i=i, sp=sp):
                        new_walk[i] = letters
                        sp["palette"] = pal
                    changed = take(n, walk[i], sp.get("palette"), put_step) or changed
            if changed:
                sp["walk"] = new_walk
                touched.add("sprites")
            if "%s/attack" % kind in frames and sp.get("attack"):
                def put_attack(letters, pal, sp=sp):
                    sp["attack"], sp["palette"] = letters, pal
                if take("%s/attack" % kind, sp["attack"], sp.get("palette"), put_attack):
                    touched.add("sprites")
        known = {k for k in monsters} | {"%s/%s" % (k, f) for k in monsters for f in ("step1", "step2", "attack")}
    elif what == "sprites":
        for name, sp in sprites.items():
            if isinstance(sp, dict) and sp.get("pixels") and name in frames:
                def put_sprite(letters, pal, sp=sp):
                    sp["pixels"], sp["palette"] = letters, pal
                if take(name, sp["pixels"], sp.get("palette"), put_sprite):
                    touched.add("sprites")
        known = set(sprites)
    else:
        from .firstperson import TEXTURES, tile_data
        for name in list(frames):
            base, _, nth = name.partition("/")
            if base in tiles and isinstance(tiles[base], dict):
                tl = tiles[base]
                i = int(nth) if nth.isdigit() else 0
                now = tl.get("pixels") if i == 0 else (tl.get("frames") or [None] * i)[i - 1] if len(tl.get("frames") or []) >= i else None
                if not now:
                    continue

                def put_tile(letters, pal, tl=tl, i=i):
                    if i == 0:
                        tl["pixels"] = letters
                    else:
                        tl["frames"][i - 1] = letters
                    tl["palette"] = pal
                if take(name, now, tl.get("palette"), put_tile):
                    touched.add("tiles")
            elif base in TEXTURES and not nth:
                made = tile_data(base)

                def put_engine(letters, pal, base=base):
                    tiles[base] = {"pixels": letters, "palette": pal}
                if take(name, made["pixels"], made["palette"], put_engine):
                    touched.add("tiles")
        known = set(tiles) | set(TEXTURES) | {n for n in frames if n.partition("/")[0] in tiles}
    report["unknown"] = sorted(n for n in frames if n not in known)
    out = {}
    if "sprites" in touched:
        out["sprites"] = sprites
    if "tiles" in touched:
        out["tiles"] = tiles
    return {"files": out, "report": report}
