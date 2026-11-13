"""Auto-map: draws the explored part of the world from the scene graph.

Rooms are laid out on a grid.  Scenes may give explicit coordinates
(``"map": [x, y]`` or ``[x, y, level]``) and exits may give a direction
(``"dir": "n"``); anything left unspecified is placed automatically.

The drawing is deliberately compact - a room is three characters, so ten
rooms fit across a 40-column phone screen::

    [·]─[@]─[?]
         │
        [$]
"""
from __future__ import annotations

from .term import pad_to, visible_len

DIRS = {
    "n": (0, -1, 0), "s": (0, 1, 0), "e": (1, 0, 0), "w": (-1, 0, 0),
    "u": (0, 0, 1), "d": (0, 0, -1),
    "ne": (1, -1, 0), "nw": (-1, -1, 0), "se": (1, 1, 0), "sw": (-1, 1, 0),
}
OPPOSITE = {"n": "s", "s": "n", "e": "w", "w": "e", "u": "d", "d": "u",
            "ne": "sw", "sw": "ne", "nw": "se", "se": "nw"}
DIR_WORDS = {
    "north": "n", "south": "s", "east": "e", "west": "w", "up": "u", "down": "d",
    "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
    "n": "n", "s": "s", "e": "e", "w": "w", "u": "u", "d": "d",
    "ne": "ne", "nw": "nw", "se": "se", "sw": "sw",
    "fore": "n", "aft": "s", "port": "w", "starboard": "e",
    "forward": "n", "back": "s", "left": "w", "right": "e",
}
DIR_NAMES = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down",
             "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest"}
_AUTO_ORDER = ("e", "s", "w", "n")


def norm_dir(value):
    if not value:
        return None
    return DIR_WORDS.get(str(value).strip().lower())


def layout(scenes, start):
    """Assign grid coordinates to every reachable scene.

    Returns ``{scene_id: (x, y, z)}``.  Exits without a direction get one
    assigned (stored on the exit as ``_dir``) so drawing and "go east" agree.
    """
    pos, taken = {}, {}

    def place(sid, p):
        pos[sid] = p
        taken[p] = sid

    for sid, sc in scenes.items():                 # explicit coordinates first
        m = sc.get("map")
        if isinstance(m, (list, tuple)) and len(m) >= 2:
            p = (int(m[0]), int(m[1]), int(m[2]) if len(m) > 2 else 0)
            if p not in taken:
                place(sid, p)
    order = [start] + [s for s in scenes if s != start]
    for root in order:
        if root not in scenes:
            continue
        if root not in pos:
            # a disconnected region: start it well away from everything else
            x = (max((p[0] for p in taken), default=-3) + 3) if taken else 0
            place(root, _free(taken, (x, 0, 0)))
        queue = [root]
        seen = {root}
        while queue:
            sid = queue.pop(0)
            x, y, z = pos[sid]
            for ex in scenes[sid].get("exits", []):
                to = ex.get("scene_id")
                if to not in scenes:
                    continue
                d = norm_dir(ex.get("dir")) or ex.get("_dir")
                if to in pos:
                    if not d:
                        d = _dir_between(pos[sid], pos[to])
                        if d:
                            ex["_dir"] = d
                    if to not in seen:
                        seen.add(to)
                        queue.append(to)
                    continue
                if d:
                    dx, dy, dz = DIRS[d]
                    target = (x + dx, y + dy, z + dz)
                    if target in taken:
                        target = _free(taken, target)
                else:
                    target = None
                    for cand in _AUTO_ORDER:
                        dx, dy, dz = DIRS[cand]
                        if (x + dx, y + dy, z) not in taken:
                            target, d = (x + dx, y + dy, z), cand
                            break
                    if target is None:
                        target = _free(taken, (x + 1, y, z))
                        d = None
                    if d:
                        ex["_dir"] = d
                place(to, target)
                # give the way back a matching direction when it has none
                if d:
                    for back in scenes[to].get("exits", []):
                        if back.get("scene_id") == sid and not norm_dir(back.get("dir")) \
                                and not back.get("_dir"):
                            back["_dir"] = OPPOSITE[d]
                            break
                seen.add(to)
                queue.append(to)
    return pos


def _free(taken, p):
    """Nearest unoccupied cell on the same level, spiralling outward."""
    if p not in taken:
        return p
    x, y, z = p
    for r in range(1, 40):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) == r and (x + dx, y + dy, z) not in taken:
                    return (x + dx, y + dy, z)
    return (x + 41, y, z)


def _dir_between(a, b):
    delta = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    for d, v in DIRS.items():
        if v == delta:
            return d
    return None


def exit_dir(ex):
    return norm_dir(ex.get("dir")) or ex.get("_dir")


def render(ui, scenes, pos, current, visited, max_width=None, max_height=None,
           hidden_fn=None, title=None):
    """Draw the current level. Returns ``(map_lines, legend_entries)``."""
    term = ui.term
    if current not in pos:
        return [], []
    level = pos[current][2]
    max_width = max_width or ui.width - 2
    hidden_fn = hidden_fn or (lambda sid, ex: False)

    known = set(v for v in visited if v in pos)
    edges = {}                         # frozenset((a, b)) -> locked?
    stairs = {}                        # sid -> set("u","d")
    for sid in list(known):
        if sid not in scenes:
            continue
        for ex in scenes[sid].get("exits", []):
            to = ex.get("scene_id")
            if to not in pos or hidden_fn(sid, ex):
                continue
            d = exit_dir(ex)
            if d in ("u", "d") or pos[to][2] != pos[sid][2]:
                stairs.setdefault(sid, set()).add("u" if pos[to][2] > pos[sid][2] else "d")
                continue
            known.add(to)
            locked = bool(ex.get("locked") or ex.get("blocked"))
            key = frozenset((sid, to))
            edges[key] = edges.get(key, True) and locked
    cells = {pos[s][:2]: s for s in known if pos[s][2] == level}
    if not cells:
        return [], []
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)

    # crop to a window around the player when the level is larger than the screen
    px, py = pos[current][:2]
    max_cols = max(3, (max_width + 1) // 4)
    max_rows = max(3, ((max_height or 21) + 1) // 2)
    if maxx - minx + 1 > max_cols:
        minx = max(minx, min(px - max_cols // 2, maxx - max_cols + 1))
        maxx = minx + max_cols - 1
    if maxy - miny + 1 > max_rows:
        miny = max(miny, min(py - max_rows // 2, maxy - max_rows + 1))
        maxy = miny + max_rows - 1

    W = (maxx - minx) * 4 + 3
    H = (maxy - miny) * 2 + 1
    grid = [[(" ", None)] * W for _ in range(H)]

    def put(cx, cy, text, spec):
        for i, ch in enumerate(text):
            if 0 <= cy < H and 0 <= cx + i < W:
                grid[cy][cx + i] = (ch, spec)

    theme = ui.theme
    col_room = theme.color("system")
    col_here = theme.color("key")
    col_new = theme.color("hint")
    col_lock = theme.color("error")
    col_icon = theme.color("quest")
    hbar = "─" if term.unicode else "-"
    vbar = "│" if term.unicode else "|"
    dot = "·" if term.unicode else "."

    legend_icons = {}
    for (x, y), sid in cells.items():
        if not (minx <= x <= maxx and miny <= y <= maxy):
            continue
        cx, cy = (x - minx) * 4, (y - miny) * 2
        sc = scenes.get(sid, {})
        seen = sid in visited
        if sid == current:
            glyph, spec, bspec = "@", col_here, col_here
        elif not seen:
            glyph, spec, bspec = "?", col_new, col_new
        else:
            icon = sc.get("map_icon")
            st = stairs.get(sid, ())
            if icon:
                glyph, spec = str(icon)[0], col_icon
                legend_icons[glyph] = sc.get("map_label") or sc.get("name", sid)
            elif "d" in st and "u" in st:
                glyph, spec = "x", col_icon
            elif "d" in st:
                glyph, spec = ">", col_icon
            elif "u" in st:
                glyph, spec = "<", col_icon
            else:
                glyph, spec = dot, col_room
            bspec = col_room
        put(cx, cy, "[", bspec)
        put(cx + 1, cy, glyph, spec)
        put(cx + 2, cy, "]", bspec)
    for key, locked in edges.items():
        a, b = tuple(key)
        if pos[a][2] != level or pos[b][2] != level:
            continue
        (ax, ay), (bx, by) = pos[a][:2], pos[b][:2]
        if abs(ax - bx) + abs(ay - by) != 1:
            continue                    # only neighbours get a drawn corridor
        spec = col_lock if locked else col_room
        if ay == by:
            x = min(ax, bx)
            if minx <= x < maxx and miny <= ay <= maxy:
                put((x - minx) * 4 + 3, (ay - miny) * 2, "x" if locked else hbar, spec)
        else:
            y = min(ay, by)
            if miny <= y < maxy and minx <= ax <= maxx:
                put((ax - minx) * 4 + 1, (y - miny) * 2 + 1, "x" if locked else vbar, spec)

    lines = []
    for row in grid:
        parts, run, run_spec = [], [], None
        for ch, spec in row:
            if spec != run_spec:
                if run:
                    parts.append(term.paint("".join(run), run_spec) if run_spec else "".join(run))
                run, run_spec = [], spec
            run.append(ch)
        if run:
            parts.append(term.paint("".join(run), run_spec) if run_spec else "".join(run))
        lines.append("".join(parts))
    # trim trailing blanks but keep a rectangle for centring
    width = max(visible_len(l.rstrip()) for l in lines) if lines else 0
    lines = [pad_to(l.rstrip(), width) for l in lines]

    legend = ["%s you" % term.paint("@", col_here), "%s seen" % term.paint(dot, col_room),
              "%s unexplored" % term.paint("?", col_new)]
    if any(edges.values()):
        legend.append("%s locked" % term.paint("x", col_lock))
    if any("d" in s for s in stairs.values()):
        legend.append("%s down" % term.paint(">", col_icon))
    if any("u" in s for s in stairs.values()):
        legend.append("%s up" % term.paint("<", col_icon))
    for glyph, label in sorted(legend_icons.items()):
        legend.append("%s %s" % (term.paint(glyph, col_icon), label))
    return lines, legend
