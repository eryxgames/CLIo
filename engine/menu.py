# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Menus: said once, shown in the look that suits the game and the terminal.

A menu is a list of items - things to do, other menus to go to, and values to set (on or off, a
number, one of a few, a typed line, a key) - each with a label, and if it likes a hint (a line shown
while the cursor is on it), a note at its right, a key that goes straight to it, a condition to be
shown at all (``when``) and a reason it cannot be chosen now (``locked``)::

    from engine import menu
    m = menu.Menu(title="Paused", items=[
        {"id": "resume", "label": "Resume"},
        {"label": "Sound", "items": [
            {"id": "music", "kind": "check", "label": "Music", "value": True},
            {"id": "loud", "kind": "slide", "label": "Volume", "value": 6, "low": 0, "high": 10}]},
        {"id": "quit", "label": "Leave", "confirm": "Leave the game?"}])
    chosen = menu.show(game.ui, m)             # the item chosen, or None: the player went back
    m.values()                                 # {"music": True, "loud": 6}

How it is shown is a **look**: ``bar`` (a lit line that moves, in a frame), ``tabs`` (its menus as
pages across the top: settings), ``find`` (a long list, narrowed by typing) - and ``lines``, CLIo's
numbered lines answered by typing, which every terminal, a pipe and a screen reader can take, and
which the others turn into where single keys cannot be read. Where it is shown is the caller's:
:func:`inline`, a few lines redrawn in place in a game that scrolls; :func:`over`, a box over a frame
kind's picture, which goes dark behind it; :func:`lines`. :func:`show` picks.

Keys: arrows (or j k / w s), Enter or Space, Esc or Backspace to go back, Tab and Shift-Tab for the
next page, Home End PgUp PgDn, a digit for the item of that number, a letter for the item that has it
as its ``key`` (else the next that begins with it), left and right to change a value; over a picture
a click or a tap on anything and the wheel (not on Windows yet, where the keys are read another way).
In ``find`` what is typed narrows the list.

A game's own menus are data: ``menus.json`` (:func:`from_data`, :func:`play`, the effect ``menu``).
Every game has :func:`options` (sound, screen) and :func:`game_menu` behind ``options`` and ``menu``.
``python -m engine.menu`` shows the looks on this terminal.
"""
from __future__ import annotations

import re
import time

from .term import FRAMES, PALETTE, QuitGame, char_width, idx256_to_rgb, parse_hex, strip_ansi

KINDS = ("do", "go", "check", "slide", "cycle", "text", "bind", "head")
VALUES = ("check", "slide", "cycle", "text", "bind")
LOOKS = ("lines", "bar", "tabs", "find", "line", "terminal", "cards")
CSI = "\x1b["
MOUSE_ON, MOUSE_OFF = CSI + "?1000h" + CSI + "?1006h", CSI + "?1000l" + CSI + "?1006l"
FIND_OVER = 12                    # a plain list longer than this is found by typing
BAR = 10                          # cells of a slider
HOLD = 5                          # presses (or repeats of a held key) that do a thing that is held to be done
HOLD_GAP = 1.2                    # seconds between them at most, or the count starts again
# The frames a menu can be drawn in: top, bottom, left, right, the four corners, the two ends of a rule
# across it, and the rule. After the name may come "shadow", "center" (the title) and "caps" (its ends).
BORDERS = {
    "single": "──││┌┐└┘├┤─", "rounded": "──││╭╮╰╯├┤─", "double": "══║║╔╗╚╝╟╢─", "dos": "══││╒╕╘╛╞╡═",
    "heavy": "━━┃┃┏┓┗┛┣┫━", "block": "▀▄▌▐▛▜▙▟▌▐─", "cut": "──││╱╲╲╱├┤─", "dots": "··::····::·",
    "ascii": "--||++++++-", "corners": "    ┌┐└┘  ─", "brackets": "  ││┌┐└┘││─", "rule": "──  ────  ─",
    "none": "          ─",
}
PLAIN_FONT = ("rounded", "heavy", "block", "cut", "dots")   # frames a console's own font draws as "single"

GLYPHS = {"mark": "►", "less": "◄", "more": "►", "on": "■", "open": "‹", "close": "›", "go": "›", "fill": "█",
          "rest": "░", "caret": "_", "ell": "…", "up": "↑", "down": "↓", "rule": "─", "ud": "↑↓", "lr": "←→"}
SAFE = dict(GLYPHS, mark=">", less="<", more=">", on="x", open="<", close=">", go=">", ell="~", up="^", down="v",
            ud="Up/Down", lr="Left/Right")
ASCII = dict(SAFE, fill="#", rest="-", rule="-")
# what each part of a menu is painted as: a theme's role, and whether it is bold
STYLES = {"frame": ("menu", False), "title": ("list_title", True), "item": ("menu", False), "sel": ("key", True),
          "dim": ("hint", False), "val": ("item", False), "valsel": ("key", True), "hint": ("hint", False),
          "head": ("list_category", True), "warn": ("warning", False), "match": ("key", True),
          "tab": ("hint", False), "tabon": ("key", True), "fill": ("item", False), "rest": ("hint", False),
          "shade": ("hint", False), "good": ("success", False), "hot": ("warning", True)}
PAPER = (8, 9, 12)                # behind a menu over a picture
now = time.monotonic              # the clock a menu waits by (tests set their own)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


# --------------------------------------------------------------------------- #
# The menu
# --------------------------------------------------------------------------- #
class Item:
    """One line of a menu. ``kind``: ``do`` (the default), ``go`` (it has ``items``), ``check``,
    ``slide`` (``low``, ``high``, ``step``), ``cycle`` (``choices``: values, or ``[value, label]``),
    ``text``, ``bind`` (a key), ``head`` (a heading; a rule if it has no label)."""

    def __init__(self, spec=None, **more):
        d = dict(spec or {})
        d.update(more)
        self.kind = d.get("kind") or ("go" if d.get("items") is not None else "do")
        if self.kind not in KINDS:
            self.kind = "do"
        self.label = str(d.get("label", d.get("text", "")))
        self.id = str(d.get("id") or slug(self.label))
        self.hint = str(d.get("hint") or "")
        self.note = str(d.get("note") or "")
        self.key = str(d.get("key") or "").lower()
        self.low, self.high, self.step = d.get("low", 0), d.get("high", 10), d.get("step", 1) or 1
        self.unit = str(d.get("unit") or "")
        self.choices = [tuple(c) if isinstance(c, (list, tuple)) else (c, str(c)) for c in d.get("choices") or []]
        self.items = [x if isinstance(x, Item) else Item(x) for x in d.get("items") or []]
        self.look, self.border = d.get("look"), d.get("border")
        self.title = str(d.get("title") or self.label)
        self.state, self.tone = str(d.get("state") or ""), d.get("tone")   # a word for how it stands (a console)
        self.status = str(d.get("status") or "")         # as a menu: a word at its top right
        self.hold = bool(d.get("hold"))                  # done only by holding Enter: armed first, then executed
        self.picture = d.get("picture")                  # rows of (r, g, b), two to a cell's height (cards)
        self.when, self.locked, self.why = d.get("when"), d.get("locked"), str(d.get("why") or "")
        self.confirm, self.stay, self.on = d.get("confirm"), bool(d.get("stay")), d.get("on")
        self.again = bool(d.get("again"))                # a game's own menu: back to it after the effects
        self.effects, self.var, self.flag = d.get("effects"), d.get("var"), d.get("flag")
        self.long = int(d.get("long") or 24)             # a typed line: at most so many characters
        value = d.get("value")
        if value is None:
            value = {"check": False, "slide": self.low, "text": "", "bind": ""}.get(self.kind)
            if self.kind == "cycle" and self.choices:
                value = self.choices[0][0]
        self.value = value

    def __repr__(self):
        return "Item(%s %r)" % (self.kind, self.id)

    def says(self):
        """The value in words (the lines look, and what is at the right of a row)."""
        k, v = self.kind, self.value
        if k == "check":
            return "on" if v else "off"
        if k == "slide":
            return "%s%s" % (("%g" % v) if isinstance(v, float) else v, self.unit)
        if k == "cycle":
            return next((label for val, label in self.choices if val == v), str(v))
        if k in ("text", "bind"):
            return str(v or "")
        return self.note


class Menu:
    """A menu and where the player is in it. ``test(condition)`` answers an item's ``when`` and
    ``locked`` when they are data (callables answer for themselves); ``on_change(item)`` hears every
    value set. After it is shown: ``result`` (the item chosen, or None) and ``values()``."""

    kind = "go"

    def __init__(self, spec=None, items=None, title="", look=None, test=None, on_change=None, cancel=True, **more):
        d = dict(spec or {})
        d.update(more)
        self.id = str(d.get("id") or "")
        self.title = str(d.get("title") or title or "")
        self.look = d.get("look") or look
        self.border = d.get("border")
        self.hint = str(d.get("hint") or "")
        self.status = str(d.get("status") or "")         # a word at the top right (a console)
        self.items = [x if isinstance(x, Item) else Item(x) for x in (items if items is not None else d.get("items") or [])]
        self.test, self.on_change, self.cancel = test, on_change, cancel
        self.plain = False                               # tabs as a list of pages (the lines look)
        self.stack = [self]
        self.tab = 0
        self.where = {}                                  # the cursor of each page, kept
        self.tops = {}                                   # and the first row shown of each, when it scrolls
        self.query = ""
        self.editing, self.draft = None, ""
        self.said = ""                                   # a word for the hint line: why not, what was done
        self.armed, self.charge, self.armed_at = None, 0, 0.0   # a thing held to be done: armed, how far, when
        self.once = False                                # one answer a line (typed): holding becomes asking
        self.columns = 1                                 # cards in a row, as they were last drawn
        self.done, self.result, self.ended = False, None, False

    # ---- where ---------------------------------------------------------- #
    def holder(self):
        return self.stack[-1]

    def look_now(self):
        look = self.holder().look
        return look if look in LOOKS and look != "lines" else "bar"

    def _paged(self, holder):
        return holder.look == "tabs" and not self.plain and any(i.kind == "go" for i in holder.items)

    def tabs(self):
        """The pages across the top, when the menu here is in tabs."""
        h = self.holder()
        return [i for i in h.items if i.kind == "go" and self.seen(i)] if self._paged(h) else []

    def page(self):
        tabs = self.tabs()
        if tabs:
            self.tab = max(0, min(self.tab, len(tabs) - 1))
            return tabs[self.tab]
        return self.holder()

    def spread(self):
        """Every item of the pages side by side here (one page's when there are no tabs): what a box
        has to have room for, so that it keeps its size from page to page."""
        tabs = self.tabs()
        return [[i for i in t.items if self.seen(i)] for t in tabs] if tabs else [[i for i in self.page().items if self.seen(i)]]

    def page_key(self):
        return id(self.page())

    def title_now(self):
        return self.holder().title or self.title

    def border_now(self):
        """The frame asked for where the player is (a submenu's own, else the menu's), or None."""
        for h in reversed(self.stack):
            if h.border:
                return h.border
        return None

    def seen(self, item):
        return self._answer(item.when, True)

    def why_not(self, item):
        """Why an item cannot be chosen now ("" when it can)."""
        lock = item.locked
        if lock is None or lock is False or lock == "":
            return ""
        if callable(lock):
            got = lock()
            return (got if isinstance(got, str) else (item.why or "Not now.")) if got else ""
        if isinstance(lock, str) and self.test is None:
            return lock                                  # in a menu made in code, the reason itself
        return (item.why or "Not now.") if self._answer(lock, False) else ""

    def _answer(self, cond, default):
        if cond is None:
            return default
        if callable(cond):
            return bool(cond())
        if self.test is not None:
            return bool(self.test(cond))
        return bool(cond)

    def rows(self):
        """The items shown here now (what ``when`` hides is out; in ``find``, what does not match)."""
        items = [i for i in self.page().items if self.seen(i)]
        if self.look_now() == "find" and self.query.strip():
            words = self.query.lower().split()
            found = []
            for n, i in enumerate(items):
                label = i.label.lower()
                if i.kind == "head" or not all(w in label for w in words):
                    continue
                first = words[0]
                rank = 0 if label.startswith(first) else (1 if (" " + first) in label else 2)
                found.append((rank, n, i))
            items = [i for _r, _n, i in sorted(found, key=lambda f: f[:2])]
        return items

    @property
    def at(self):
        rows = self.rows()
        i = self.where.get(self.page_key(), 0)
        i = max(0, min(i, len(rows) - 1))
        if rows and rows[i].kind == "head":              # never on a heading
            ok = [n for n, r in enumerate(rows) if r.kind != "head"]
            i = min(ok, key=lambda n: (abs(n - i), n)) if ok else i
        return i

    def current(self):
        rows = self.rows()
        return rows[self.at] if rows and rows[self.at].kind != "head" else None

    def to(self, i):
        rows = self.rows()
        if rows:
            self.where[self.page_key()] = max(0, min(int(i), len(rows) - 1))

    def move(self, d):
        rows = self.rows()
        ok = [n for n, r in enumerate(rows) if r.kind != "head"]
        if not ok:
            return
        at = self.at
        if abs(d) == 1:                                  # one step: round the ends
            here = ok.index(at) if at in ok else 0
            self.to(ok[(here + d) % len(ok)])
        else:                                            # a jump: to the end and no further
            want = max(0, min(at + d, len(rows) - 1))
            self.to(min(ok, key=lambda n: (abs(n - want), n)))

    # ---- doing ---------------------------------------------------------- #
    def set(self, item, value):
        """Give an item a value (kept within what it can be). True if it changed."""
        if item.kind == "check":
            value = bool(value)
        elif item.kind == "slide":
            try:
                value = max(item.low, min(item.high, value))
            except TypeError:
                return False
            if isinstance(item.step, int) and isinstance(item.low, int):
                value = int(round(value))
        elif item.kind == "cycle":
            if value not in [v for v, _l in item.choices]:
                return False
        elif item.kind == "text":
            value = str(value)[:item.long]
        if value == item.value:
            return False
        item.value = value
        if callable(item.on):
            item.on(item, self)
        if self.on_change is not None:
            self.on_change(item)
        return True

    def change(self, item, d):
        """A step down or up: a slider's step, the choice before or after, on to off."""
        if self.why_not(item):
            self.said = self.why_not(item)
            return False
        if item.kind == "check":
            return self.set(item, not item.value)
        if item.kind == "slide":
            return self.set(item, item.value + d * item.step)
        if item.kind == "cycle" and item.choices:
            values = [v for v, _l in item.choices]
            i = values.index(item.value) if item.value in values else 0
            return self.set(item, values[(i + d) % len(values)])
        return False

    def act(self, item=None):
        """Enter on an item."""
        item = item or self.current()
        if item is None:
            return
        why = self.why_not(item)
        if why:
            self.said = why
            return
        k = item.kind
        if k == "go":
            self.stack.append(item)
            self.query = ""
        elif k in ("check", "cycle"):
            self.change(item, 1)
        elif k == "slide":
            self.said = "Left and right change it."
        elif k in ("text", "bind"):
            self.editing, self.draft = item, str(item.value or "") if k == "text" else ""
        elif k == "do":
            if item.hold and not (self.once or self.plain):
                t = now()
                if self.armed is not item:               # the first Enter arms it
                    self.armed, self.charge, self.armed_at = item, 0, t
                    return
                self.charge = self.charge + 1 if t - self.armed_at <= HOLD_GAP else 1
                self.armed_at = t
                if self.charge < HOLD:
                    return
                self.armed, self.charge = None, 0
                self.choose(item)
                return
            if (item.confirm or item.hold) and not getattr(item, "_sure", False):
                ask = item.confirm if isinstance(item.confirm, str) else "%s?" % item.label
                no, yes = Item(id="no", label="No"), Item(id="yes", label="Yes")
                yes.on = lambda _i, m, item=item: m._confirmed(item)
                no.on = lambda _i, m: m.back()
                no.stay = yes.stay = True
                self.stack.append(Item(kind="go", id="confirm", label=ask, items=[no, yes], look="bar"))
                return
            self.choose(item)

    def _confirmed(self, item):
        self.stack.pop()
        self.choose(item)

    def choose(self, item):
        if callable(item.on):
            item.on(item, self)
            if self.done:                                # what it did ended the menu
                return
        if not item.stay:
            self.result, self.done = item, True

    def back(self):
        if self.editing is not None:
            self.editing = None
        elif self.look_now() == "find" and self.query:
            self.query = ""
        elif len(self.stack) > 1:
            self.stack.pop()
            self.query = ""
        elif self.cancel:
            self.done, self.result = True, None

    def leave(self):
        """Out of the menu altogether, nothing chosen."""
        self.done, self.result, self.editing = True, None, None

    def values(self, items=None, out=None):
        """Every value in the menu by its item's id."""
        out = {} if out is None else out
        for i in (self.items if items is None else items):
            if i.kind in VALUES:
                out[i.id] = i.value
            elif i.kind == "go":
                self.values(i.items, out)
        return out

    def find(self, iid, items=None):
        for i in (self.items if items is None else items):
            if i.id == iid:
                return i
            got = self.find(iid, i.items) if i.kind == "go" else None
            if got is not None:
                return got
        return None

    # ---- keys ----------------------------------------------------------- #
    def key(self, k):
        """One key, by its name (engine/keys.py)."""
        self.said = ""
        e = self.editing
        if e is not None:
            if e.kind == "bind":
                self.editing = None
                if k != "esc":
                    self.set(e, k)
            elif k == "enter":
                self.editing = None
                self.set(e, self.draft)
            elif k == "esc":
                self.editing = None
            elif k == "backspace":
                self.draft = self.draft[:-1]
            elif k == "space":
                self.draft += " "
            elif len(k) == 1 and k.isprintable() and len(self.draft) < e.long:
                self.draft += k
            return
        if self.armed is not None and k != "enter":      # anything else lets go of it
            self.armed, self.charge = None, 0
            if k == "esc":
                return
        find = self.look_now() == "find"
        cur = self.current()
        tabs = self.tabs()
        wide = self.columns if self.look_now() == "cards" else 1
        if len(k) > 1 and k not in ("enter", "space", "esc", "tab") and self.named(k):
            return
        if wide > 1 and k in ("up", "down", "left", "right"):                # cards: a grid
            self.grid({"up": -wide, "down": wide, "left": -1, "right": 1}[k], wide)
        elif k in ("up", "shift-tab") and not (tabs and k == "shift-tab"):
            self.move(-1)
        elif k in ("down", "tab") and not (tabs and k == "tab"):
            self.move(1)
        elif k in ("tab", "shift-tab"):
            self.turn(1 if k == "tab" else -1)
        elif k == "home":
            self.move(-10 ** 6)
        elif k == "end":
            self.move(10 ** 6)
        elif k == "pgup":
            self.move(-8)
        elif k == "pgdn":
            self.move(8)
        elif k == "enter" or (k == "space" and not find):
            self.act()
        elif k == "esc" or (k == "backspace" and not (find and self.query)):
            self.back()
        elif k in ("left", "right"):
            d = 1 if k == "right" else -1
            if cur is not None and cur.kind in ("check", "slide", "cycle"):
                self.change(cur, d)
            elif tabs:
                self.turn(d)
            elif d > 0 and cur is not None and cur.kind == "go":
                self.act()
            elif d < 0 and len(self.stack) > 1:
                self.back()
        elif find:
            if k == "backspace":
                self.query = self.query[:-1]
            elif k == "space":
                self.query += " "
            elif len(k) == 1 and k.isprintable():
                self.query += k
            else:
                return
            self.where[self.page_key()] = 0
        elif len(k) == 1 and k.isdigit() and k != "0":
            ok = [n for n, r in enumerate(self.rows()) if r.kind != "head"]
            if int(k) <= len(ok):
                self.to(ok[int(k) - 1])
                self.act()
        elif len(k) == 1 and k.isprintable():
            self.letter(k.lower())

    def turn(self, d):
        tabs = self.tabs()
        if tabs:
            self.tab = (self.tab + d) % len(tabs)

    def grid(self, d, wide):
        """A step in a grid of cards: along a row, or a row up or down; no further than its edges."""
        rows = self.rows()
        to = self.at + d
        if 0 <= to < len(rows) and (abs(d) != 1 or to // wide == self.at // wide) and rows[to].kind != "head":
            self.to(to)

    def named(self, k):
        """A key with a name (f1, ctrl-s) that an item here has as its own: that item, at once."""
        for n, r in enumerate(self.rows()):
            if r.key == k and r.kind != "head":
                self.to(n)
                self.act()
                return True
        return False

    def arming(self, g=GLYPHS):
        """What is said while a thing is armed ("" when nothing is)."""
        if self.armed is None:
            return ""
        return "ARMED   hold Enter %s%s   Esc lets go" % (g["fill"] * self.charge, g["rest"] * (HOLD - self.charge))

    def letter(self, ch):
        rows = self.rows()
        for n, r in enumerate(rows):                     # its own key: straight to it, and done
            if r.key == ch and r.kind != "head":
                self.to(n)
                self.act()
                return
        at = self.at
        order = list(range(at + 1, len(rows))) + list(range(0, at + 1))
        for n in order:                                  # else the next that begins with the letter
            if rows[n].kind != "head" and rows[n].label[:1].lower() == ch:
                self.to(n)
                return
        if ch in "jksw":
            self.move(1 if ch in "js" else -1)

    def click(self, what):
        """A click or a tap on a part of the picture (a board's ``hit``), or the wheel."""
        self.said = ""
        self.armed, self.charge = None, 0
        if self.editing is not None:
            self.editing = None
        if not what:
            return
        rows = self.rows()
        kind = what[0]
        if kind == "wheel":
            self.move(what[1])
        elif kind == "tab":
            self.tab = what[1]
        elif kind in ("item", "less", "more", "set") and 0 <= what[1] < len(rows) and rows[what[1]].kind != "head":
            self.to(what[1])
            item = rows[what[1]]
            if kind == "item":
                self.act(item)
            elif kind == "set":
                if self.why_not(item):
                    self.said = self.why_not(item)
                else:
                    self.set(item, what[2])
            else:
                self.change(item, -1 if kind == "less" else 1)


# --------------------------------------------------------------------------- #
# The picture of a menu: a board of cells
# --------------------------------------------------------------------------- #
class Board:
    """A menu drawn: ``rows`` of cells ``(char, style, lit)`` (styles: :data:`STYLES`), ``hits`` (what a
    click on a cell means) and ``keys``, the line that says which keys do what."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.rows = [[(" ", "item", False)] * w for _ in range(h)]
        self.hits = []
        self.keys = ""

    def put(self, x, y, text, style="item", lit=False):
        if not 0 <= y < self.h:
            return x
        row = self.rows[y]
        for ch in text:
            wide = char_width(ch) == 2
            if x < 0 or x + (1 if wide else 0) >= self.w:
                x += 2 if wide else 1
                continue
            row[x] = (ch, style, lit)
            if wide:
                row[x + 1] = ("", style, lit)
            x += 2 if wide else 1
        return x

    def light(self, x0, x1, y):
        row = self.rows[y]
        for x in range(max(0, x0), min(self.w, x1)):
            row[x] = (row[x][0], row[x][1], True)

    def hit(self, x0, y0, x1, y1, what):
        self.hits.append((x0, y0, x1, y1, what))

    def at(self, x, y):
        for x0, y0, x1, y1, what in reversed(self.hits):
            if x0 <= x < x1 and y0 <= y < y1:
                return what
        return None

    def plain(self):
        """The board as text (tests, a look at it)."""
        return ["".join(c[0] for c in row).rstrip() for row in self.rows]


def cells_wide(text):
    return sum(2 if char_width(c) == 2 else 1 for c in text)


def wrap(text, width):
    width = max(4, width)
    lines, line = [], ""
    for word in str(text).split():
        while cells_wide(word) > width:
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:width])
            word = word[width:]
        if line and cells_wide(line) + 1 + cells_wide(word) > width:
            lines.append(line)
            line = word
        else:
            line = (line + " " + word) if line else word
    if line:
        lines.append(line)
    return lines or [""]


def glyphs_of(term):
    if term is None:
        return GLYPHS
    if not term.unicode or getattr(term, "glyph_mode", "full") == "ascii":
        return ASCII
    return SAFE if getattr(term, "glyph_mode", "full") == "safe" else GLYPHS


def value_wide(item, g):
    """How wide an item's value is at the right of its row - the same whatever the value is now."""
    k = item.kind
    if k == "check":
        return 7                                         # [x] off
    if k == "slide":
        ends = max(len(Item(kind="slide", value=v, unit=item.unit).says()) for v in (item.low, item.high))
        return 2 + BAR + 2 + 1 + ends
    if k == "cycle":
        return 4 + max([cells_wide(label) for _v, label in item.choices] or [1])
    if k == "text":
        return min(item.long, max(12, cells_wide(str(item.value or "")))) + 1
    if k == "bind":
        return 15
    if k == "go":
        return cells_wide(item.note) + 2 if item.note else 1
    return cells_wide(item.note)


def draw_value(b, x, y, item, n, sel, lit, g, menu, wide):
    """An item's value, right-aligned in ``wide`` cells from ``x``, with what a click on it does."""
    k, v = item.kind, item.value
    dim = bool(menu.why_not(item))
    val = "dim" if dim else ("valsel" if sel else "val")
    arrow = "dim" if dim else ("sel" if sel else "dim")
    if k == "check":
        b.put(x + wide - 7, y, "[", arrow, lit)
        b.put(x + wide - 6, y, g["on"] if v else " ", val, lit)
        b.put(x + wide - 5, y, "]", arrow, lit)
        b.put(x + wide - 3, y, "on" if v else "off", val, lit)
    elif k == "slide":
        x0 = x
        span = float(item.high - item.low) or 1.0
        full = int(round(BAR * (v - item.low) / span))
        b.put(x0, y, g["less"], arrow, lit)
        b.put(x0 + 2, y, g["fill"] * full, "dim" if dim else "fill", lit)
        b.put(x0 + 2 + full, y, g["rest"] * (BAR - full), "rest", lit)
        b.put(x0 + 3 + BAR, y, g["more"], arrow, lit)
        b.put(x0 + 5 + BAR, y, item.says(), val, lit)
        b.hit(x0, y, x0 + 2, y + 1, ("less", n))
        b.hit(x0 + 3 + BAR, y, x0 + 5 + BAR, y + 1, ("more", n))
        for i in range(BAR):                             # a click on the bar: that much of it
            at = item.low + span * (i + 1) / BAR
            b.hit(x0 + 2 + i, y, x0 + 3 + i, y + 1, ("set", n, int(round(at)) if isinstance(item.low, int)
                                                    and isinstance(item.step, int) else at))
    elif k == "cycle":
        text = item.says()
        x0 = x + wide - cells_wide(text) - 4
        b.put(x0, y, g["open"], arrow, lit)
        b.put(x0 + 2, y, text, val, lit)
        b.put(x0 + 3 + cells_wide(text), y, g["close"], arrow, lit)
        b.hit(x0, y, x0 + 2, y + 1, ("less", n))
    elif k == "text":
        editing = menu.editing is item
        text = (menu.draft + g["caret"]) if editing else (str(v) or g["ell"])
        text = text[-wide:]
        b.put(x + wide - cells_wide(text), y, text, "valsel" if editing else val, lit)
    elif k == "bind":
        text = "[ press a key ]" if menu.editing is item else "[ %s ]" % (v or "-")
        b.put(x + wide - len(text), y, text, "valsel" if menu.editing is item else val, lit)
    elif k == "go":
        if item.note:
            b.put(x + wide - cells_wide(item.note) - 2, y, item.note, "sel" if sel and not dim else "dim", lit)
        b.put(x + wide - 1, y, g["go"], arrow, lit)
    elif item.note:
        b.put(x + wide - cells_wide(item.note), y, item.note, "val" if sel and not dim else "dim", lit)


class Border:
    """The frame of a menu: its characters, and whether it throws a shadow, centres its title, caps it."""

    def __init__(self, chars, shadow=False, center=False, caps=False, name=""):
        (self.top, self.bottom, self.left, self.right, self.tl, self.tr, self.bl, self.br, self.lt, self.rt,
         self.rule) = chars
        self.shadow, self.center, self.caps, self.name = shadow, center, caps, name


def border(spec=None, term=None):
    """A frame from what was asked for: a name of :data:`BORDERS` (with ``shadow``, ``center``, ``caps``
    after it), the six characters of one of the engine's frames (engine.term.FRAMES), a
    :class:`Border`, or nothing (``single``). A terminal that has not the characters gets the nearest."""
    if isinstance(spec, Border):
        return spec
    g = glyphs_of(term)
    words = str(spec or "single").split()
    name = words[0].lower() if words else "single"
    flags = {w.lower() for w in words[1:]}
    if len(words) == 1 and len(words[0]) == 6 and name not in BORDERS:      # an engine frame: h v and corners
        h, v, tl, tr, bl, br = words[0]
        lt, rt = {"─│": "├┤", "═║": "╟╢", "━┃": "┣┫", "-|": "++"}.get(h + v, v + v)
        rule = {"-|": "-", "━┃": "━"}.get(h + v, g["rule"])
        return Border(h + h + v + v + tl + tr + bl + br + lt + rt + rule, name="frame")
    if name not in BORDERS:
        name = "single"
    if g is ASCII:
        name = name if name in ("none", "ascii") else "ascii"
    elif term is not None and getattr(term, "limited_glyphs", False) and name in PLAIN_FONT:
        name = "single"
    chars = BORDERS[name]
    if g is ASCII and name == "none":
        chars = chars[:-1] + "-"
    return Border(chars, "shadow" in flags, "center" in flags or "centre" in flags, "caps" in flags, name)


def shadowed(b, g):
    """The board with a shadow at its right and under it."""
    out = Board(b.w + 1, b.h + 1)
    for y, row in enumerate(b.rows):
        out.rows[y][:b.w] = row
        if y:
            out.rows[y][b.w] = (g["rest"], "shade", False)
    out.rows[b.h][1:] = [(g["rest"], "shade", False)] * b.w
    out.hits, out.keys = b.hits, b.keys
    return out


def hint_of(menu, g):
    """What the line under the items says now, and how: a thing armed, a reason, a hint."""
    if menu.armed is not None:
        return menu.arming(g), "hot"
    if menu.said:
        return menu.said, "warn"
    cur = menu.current()
    return (cur.hint if cur is not None else "") or menu.holder().hint, "hint"


def keys_line(menu, g, numbers=False):
    """The line that says which keys do what, as the menu stands."""
    look, cur, tabs = menu.look_now(), menu.current(), menu.tabs()
    if menu.editing is not None:
        return "Press the key   Esc keeps the old one" if menu.editing.kind == "bind" \
            else "Type   Enter keeps it   Esc leaves it"
    if numbers:
        return "Its number, Enter   (a value after it: 3 7)   Enter alone goes back"
    if menu.armed is not None:
        return "Hold Enter to do it   Esc lets go"
    parts = ["type to find"] if look == "find" else []
    parts.append("%s %s move" % (g["ud"], g["lr"]) if look == "cards" and menu.columns > 1 else "%s move" % g["ud"])
    if cur is not None and cur.kind in ("slide", "cycle", "check"):
        parts.append("%s change" % g["lr"])
    parts.append("Enter arm" if cur is not None and cur.hold else "Enter choose")
    if tabs and len(tabs) > 1:
        parts.append("Tab page")
    if menu.cancel or len(menu.stack) > 1:
        parts.append("Esc back")
    return "   ".join(parts)


def window(menu, heights, room, at):
    """Which of a page's rows are shown when they do not all fit: ``(first, after the last)``, the cursor
    in sight, and where it was kept from draw to draw."""
    first, last = 0, len(heights)
    if sum(heights) > room:
        first = min(menu.tops.get(menu.page_key(), 0), at)
        while sum(heights[first:at + 1]) > room and first < at:
            first += 1
        last, used = first, 0
        while last < len(heights) and used + heights[last] <= room:
            used += heights[last]
            last += 1
        last = max(last, min(len(heights), at + 1))
        menu.tops[menu.page_key()] = first
    return first, last


def board(menu, cols=80, lines=24, term=None, frame=None, numbers=False, roomy=False):
    """Draw the menu where the player is in it, in at most ``cols`` by ``lines`` cells. ``frame``: the box
    it is drawn in unless the menu names its own (see :func:`border`); ``numbers``: a number before each
    item (for a screen that reads typed lines); ``roomy``: a blank row between items when they fit so."""
    g = glyphs_of(term)
    look = menu.look_now()
    if look == "cards":
        b = _cards(menu, cols, lines, term, g)
    elif look == "terminal":
        b = _terminal(menu, cols, lines, term, g, numbers)
    elif look == "line":
        b = _line(menu, cols, lines, term, g, numbers, roomy)
    else:
        bd = border(menu.border_now() or frame, term)
        b = _box(menu, cols - bd.shadow, lines - bd.shadow, term, bd, numbers, roomy)
        if bd.shadow:
            b = shadowed(b, g)
    b.keys = keys_line(menu, g, numbers)
    return b


def _box(menu, cols, lines, term, bd, numbers, roomy):
    """The bar, tabs and find looks: a box."""
    g = glyphs_of(term)
    look = menu.look_now()
    rows = menu.rows()
    at = menu.at
    tabs = menu.tabs()
    title = menu.title_now()
    inner_most = max(16, cols - 4)
    # ---- how wide
    lead = 2 + (len(str(len(rows))) + 2 if numbers else 0)
    label_w = max([cells_wide(r.label) for r in rows if r.kind != "head"] or [8])
    value_w = max([value_wide(r, g) for r in rows if r.kind != "head"] or [0])
    need = lead + label_w + (2 + value_w if value_w else 0)
    tab_w = sum(cells_wide(t.title) + 3 for t in tabs) + 1 if tabs else 0
    spread = menu.spread()
    every = [r for page in spread for r in page]
    hints = [r.hint for r in every if r.hint] + ([menu.said] if menu.said else [])
    hint_w = min(48, max([cells_wide(t) for t in hints] or [0]))
    W = max(22, need, tab_w, hint_w, cells_wide(title) + 4, 30 if look == "find" else 0)
    for page in spread:                                  # as wide as its pages ever are: nothing jumps
        lw = max([cells_wide(r.label) for r in page if r.kind != "head"] or [0])
        vw = max([value_wide(r, g) for r in page if r.kind != "head"] or [0])
        W = max(W, lead + lw + (2 + vw if vw else 0))
    W = min(W, inner_most)
    label_room = max(6, W - lead - (2 + value_w if value_w else 0))
    # ---- how tall
    hint_rows = 0
    if hints or any(r.locked or r.hold for r in every):
        hint_rows = max(1, min(2, max([len(wrap(t, W)) for t in hints] or [1])))
    top_rows = (2 if tabs else 0) + (2 if look == "find" else 0)
    chrome = 2 + top_rows + (1 + hint_rows if hint_rows else 0)
    heights = []
    for r in rows:
        if r.kind == "head":
            heights.append(1)
        elif r.kind in ("do", "go") and cells_wide(r.label) > label_room:
            heights.append(min(4, len(wrap(r.label, W - lead))))
        else:
            heights.append(1)
    room = max(1, lines - chrome)
    gap = 1 if roomy and rows and sum(heights) + len(rows) + 1 <= room else 0
    need_rows = sum(heights) + gap * (len(rows) + 1)
    first, last = window(menu, heights, room, at) if need_rows > room else (0, len(rows))
    if need_rows > room:                                 # it scrolls: the cursor is kept in sight
        need_rows = min(room, sum(heights[first:last]))
    body = max(need_rows, 1 if not rows else 0)
    if look == "find":                                   # a list that narrows keeps its box
        body = max(body, min(room, 8, len(spread[0]) + 2 * gap))
    elif len(spread) > 1:                                # and pages are as tall as the tallest
        body = max(body, min(room, max(len(page) * (1 + gap) + gap for page in spread)))
    b = Board(W + 4, chrome + body)

    def rule(yy):
        b.put(0, yy, bd.lt + bd.rule * (W + 2) + bd.rt, "frame")
    # ---- the frame and its title
    b.put(0, 0, bd.tl + bd.top * (W + 2) + bd.tr, "frame")
    if title:
        text = title[:W - 2 - (4 if bd.caps else 0)]
        x = (b.w - cells_wide(text) - 2) // 2 if bd.center else 2
        if bd.caps:                                      # the line broken off either side of it
            b.put(x - 1, 0, bd.rt, "frame")
            b.put(x + cells_wide(text) + 2, 0, bd.lt, "frame")
        b.put(x, 0, " " + text + " ", "title")
    for yy in range(1, b.h - 1):
        b.put(0, yy, bd.left, "frame")
        b.put(W + 3, yy, bd.right, "frame")
    b.put(0, b.h - 1, bd.bl + bd.bottom * (W + 2) + bd.br, "frame")
    y = 1
    if tabs:
        x = 2
        for n, t in enumerate(tabs):
            on = n == menu.tab
            text = " %s " % t.title
            b.put(x, y, text, "tabon" if on else "tab", on)
            b.hit(x, y, x + cells_wide(text), y + 1, ("tab", n))
            x += cells_wide(text) + 1
        rule(y + 1)
        y += 2
    if look == "find":
        b.put(2, y, g["close"] + " ", "dim")
        b.put(4, y, (menu.query + g["caret"])[-(W - 2):], "valsel")
        rule(y + 1)
        y += 2
    # ---- the items
    number = 0
    for n in range(0, first):
        number += rows[n].kind != "head"
    if not rows:
        b.put(4, y, "Nothing." if not menu.query else "Nothing called that.", "dim")
    y += gap
    for n in range(first, last):
        r, tall = rows[n], heights[n]
        if y + tall > b.h - 1 - (1 + hint_rows if hint_rows else 0):
            break
        if r.kind == "head":
            if r.label:
                b.put(2, y, r.label[:W], "head")
            else:
                b.put(2, y, g["rule"] * W, "frame")
            y += 1 + gap
            continue
        number += 1
        sel = n == at
        why = menu.why_not(r)
        style = "dim" if why else ("sel" if sel else "item")
        if sel:
            for yy in range(y, y + tall):
                b.light(1, W + 3, yy)
        b.hit(1, y - (1 if gap else 0), W + 3, y + tall, ("item", n))
        x = 2
        if sel:
            b.put(x, y, g["mark"], "sel", True)
        x += 2
        if numbers:
            x = b.put(x, y, "%*d. " % (len(str(len(rows))), number), "dim" if not sel else "sel", sel)
        if tall > 1:
            for i, part in enumerate(wrap(r.label, W - lead)[:tall]):
                b.put(x, y + i, part, style, sel)
        else:
            text = r.label
            if cells_wide(text) > label_room:
                text = text[:max(1, label_room - 1)] + g["ell"]
            b.put(x, y, text, style, sel)
            if look == "find" and menu.query.strip() and not why:      # what matched, lit
                low = text.lower()
                for word in menu.query.lower().split():
                    i = low.find(word)
                    if i >= 0:
                        b.put(x + cells_wide(text[:i]), y, text[i:i + len(word)], "match", sel)
        if value_w and (r.kind != "do" or r.note) and tall == 1:
            draw_value(b, 2 + W - value_w, y, r, n, sel, sel, g, menu, value_w)
        y += tall + gap
    # ---- the hint
    if hint_rows:
        y = b.h - 2 - hint_rows
        rule(y)
        text, how = hint_of(menu, g)
        for i, part in enumerate(wrap(text, W)[:hint_rows]):
            b.put(2, y + 1 + i, part, how)
    # ---- how much there is
    ok = [n for n, r in enumerate(rows) if r.kind != "head"]
    if rows and (first > 0 or last < len(rows) or (look == "find" and menu.query.strip())):
        total = len([i for i in menu.page().items if i.kind != "head" and menu.seen(i)])
        narrowed = look == "find" and menu.query.strip()   # how many were found; else where the cursor is
        text = " %s%d of %d%s " % (g["up"] + " " if first > 0 else "",
                                   len(ok) if narrowed else (ok.index(at) + 1 if at in ok else 0), total,
                                   " " + g["down"] if last < len(rows) else "")
        b.put(max(2, W + 2 - cells_wide(text)), b.h - 1, text, "dim")
    return b


def _line(menu, cols, lines, term, g, numbers, roomy):
    """The line look: a title in letters of heavy lines, rules, and a rail down the items with an arm
    out to the one the cursor is on."""
    from .banner import line_rows
    heavy = g is not ASCII and not (term is not None and getattr(term, "limited_glyphs", False))
    rule_ch, rail, arm, top, end = ("━", "┃", "┣━╸", "┏━╸", "┗━╸") if heavy else \
        (("-", "|", "+->", "+--", "+--") if g is ASCII else ("─", "│", "├─ ", "┌─ ", "└─ "))
    rows, at = menu.rows(), menu.at
    title = menu.title_now()
    letters, owner = line_rows(title) if heavy and title else (None, [])
    lead = 4 + (len(str(len(rows))) + 2 if numbers else 0)
    every = [i for i in menu.page().items if menu.seen(i)]
    label_w = max([cells_wide(r.label) for r in every if r.kind != "head"] or [8])
    value_w = max([value_wide(r, g) for r in every if r.kind != "head"] or [0])
    hints = [r.hint for r in every if r.hint] + ([menu.said] if menu.said else [])
    W = max(28, lead + label_w + (3 + value_w if value_w else 0), min(52, max([cells_wide(t) for t in hints] or [0])),
            cells_wide(title))
    if letters and len(owner) <= cols:
        W = max(W, len(owner))
    else:
        letters = None
    W = min(W, max(20, cols))
    hint_rows = max(1, min(2, max([len(wrap(t, W)) for t in hints] or [1]))) if hints or any(r.locked or r.hold for r in every) else 0
    head = (4 if letters else (2 if title else 0)) + 1                       # the title, a gap, a rule
    foot = 1 + (1 + hint_rows if hint_rows else 0)                           # the rail's end; a rule and the hint
    room = max(1, lines - head - 1 - foot)
    gap = 1 if roomy and 2 * len(rows) - 1 <= room else 0
    first, last = window(menu, [1 + gap] * len(rows), room + gap, at) if len(rows) * (1 + gap) - gap > room else (0, len(rows))
    shown = last - first
    b = Board(W, head + 1 + max(1, shown * (1 + gap) - gap) + foot)
    y = 0
    if letters:
        for i in range(3):
            b.put(0, i, letters[i][:W], "title")
        y = 4
    elif title:
        b.put(0, 0, title.upper()[:W], "title")
        y = 2
    b.put(0, y, rule_ch * W, "frame")
    b.put(0, y + 1, top, "frame")
    y += 2
    number = sum(1 for r in rows[:first] if r.kind != "head")
    if not rows:
        b.put(4, y, "NOTHING.", "dim")
    for n in range(first, last):
        r = rows[n]
        if r.kind == "head":
            b.put(0, y, rail, "frame")
            b.put(4, y, r.label.upper()[:W - 4], "head")
        else:
            number += 1
            sel, why = n == at, menu.why_not(r)
            style = "dim" if why else ("sel" if sel else "item")
            b.put(0, y, arm if sel else rail, "sel" if sel else "frame")
            x = 4
            if numbers:
                x = b.put(x, y, "%*d. " % (len(str(len(rows))), number), "sel" if sel else "dim")
            room_w = max(4, W - x - (3 + value_w if value_w else 0))
            text = r.label.upper()
            b.put(x, y, text if cells_wide(text) <= room_w else text[:room_w - 1] + g["ell"], style)
            if value_w and (r.kind != "do" or r.note):
                draw_value(b, W - value_w, y, r, n, sel, False, g, menu, value_w)
            b.hit(0, y, W, y + 1 + gap, ("item", n))
        y += 1
        if gap and n < last - 1:
            b.put(0, y, rail, "frame")
            y += 1
    y = b.h - foot
    b.put(0, y, end, "frame")
    if first > 0 or last < len(rows):
        ok = [n for n, r in enumerate(rows) if r.kind != "head"]
        text = "%s%d OF %d%s" % (g["up"] + " " if first > 0 else "", ok.index(at) + 1 if at in ok else 0, len(ok),
                                 " " + g["down"] if last < len(rows) else "")
        b.put(W - cells_wide(text), y, text, "dim")
    if hint_rows:
        b.put(0, y + 1, rule_ch * W, "frame")
        text, how = hint_of(menu, g)
        for i, part in enumerate(wrap(text, W)[:hint_rows]):
            b.put(0, y + 2 + i, part, how)
    return b


TONES = {"good": "good", "ok": "good", "warn": "warn", "hot": "hot", "off": "dim", "dim": "dim"}


def state_of(menu, item):
    """How an item stands, in a word, and how the word is painted (the terminal look)."""
    if menu.armed is item:
        return "ARMED", "hot"
    if menu.why_not(item):
        return item.state.upper() or "LOCKED", "dim"
    return item.state.upper(), TONES.get(item.tone, "val")


def _terminal(menu, cols, lines, term, g, numbers):
    """The terminal look: a console's list of functions - a number, a name, how it stands - with the
    keys that have a name (F1...) on a strip under it."""
    rows, at = menu.rows(), menu.at
    every = [i for i in menu.page().items if menu.seen(i)]
    title = menu.title_now().upper()
    bar = "|" if g is ASCII else "▌"
    label_w = max([cells_wide(r.label) for r in every if r.kind != "head"] or [8])
    states = [state_of(menu, r)[0] for r in every if r.kind != "head"] + (["ARMED"] if any(r.hold for r in every) else []) \
        + (["LOCKED"] if any(r.locked for r in every) else [])
    state_w = max([cells_wide(t) for t in states] or [0])
    note_w = max([value_wide(r, g) for r in every if r.kind != "head"] or [0])
    soft = [(n, r) for n, r in enumerate(rows) if re.fullmatch(r"f\d\d?", r.key) and r.kind != "head"]
    strip = sum(len(r.key) + cells_wide(r.label) + 4 for _n, r in soft)
    hints = [r.hint for r in every if r.hint] + ([menu.said] if menu.said else [])
    status = menu.holder().status
    W = max(44, 4 + label_w + 2 + state_w + (2 + note_w if note_w else 0), strip,
            cells_wide(title) + cells_wide(status) + 4, min(60, max([cells_wide(t) for t in hints] or [0])))
    W = min(W, max(24, cols))
    hint_rows = max(1, min(2, max([len(wrap(t, W)) for t in hints] or [1]))) if hints or any(r.locked or r.hold for r in every) else 0
    foot = (1 + hint_rows if hint_rows else 1) + (1 if soft else 0)
    room = max(1, lines - 2 - foot)
    first, last = window(menu, [1] * len(rows), room, at)
    b = Board(W, 2 + max(1, last - first) + foot)
    b.put(0, 0, title[:W], "title")
    if status:
        b.put(max(cells_wide(title) + 2, W - cells_wide(status)), 0, status, "dim")
    b.put(0, 1, g["rule"] * W, "frame")
    y = 2
    number = sum(1 for r in rows[:first] if r.kind != "head")
    if not rows:
        b.put(3, y, "NO FUNCTIONS.", "dim")
    for n in range(first, last):
        r = rows[n]
        if r.kind == "head":
            b.put(1, y, r.label.upper()[:W - 1] or g["rule"] * (W - 1), "head" if r.label else "frame")
            y += 1
            continue
        number += 1
        sel, why = n == at, menu.why_not(r)
        state, tone = state_of(menu, r)
        if sel:
            b.light(0, W, y)
            b.put(0, y, bar, "hot" if menu.armed is r else "sel", True)
        b.put(1, y, "%d" % number if number < 10 else " ", "sel" if sel else "dim", sel)
        text = r.label.upper()
        b.put(3, y, text[:label_w], "dim" if why else ("sel" if sel else "item"), sel)
        b.put(3 + label_w + 2, y, state, tone, sel)
        if note_w and (r.kind != "do" or r.note):
            draw_value(b, W - note_w - 1, y, r, n, sel, sel, g, menu, note_w)
        b.hit(0, y, W, y + 1, ("item", n))
        y += 1
    y = b.h - foot
    b.put(0, y, g["rule"] * W, "frame")
    if first > 0 or last < len(rows):
        text = " %s%s " % (g["up"] if first > 0 else "", g["down"] if last < len(rows) else "")
        b.put(W - cells_wide(text) - 1, y, text, "dim")
    if hint_rows:
        text, how = hint_of(menu, g)
        for i, part in enumerate(wrap(text, W)[:hint_rows]):
            b.put(1, y + 1 + i, part, how)
    if soft:                                             # the keys with a name, as a console's soft keys
        x, y = 0, b.h - 1
        for n, r in soft:
            cap, text = " %s " % r.key.upper(), " %s " % r.label.upper()
            if x + len(cap) + cells_wide(text) > W:
                break
            b.put(x, y, cap, "tabon" if not menu.why_not(r) else "dim", True)
            b.put(x + len(cap), y, text, "dim" if menu.why_not(r) else ("sel" if n == at else "item"))
            b.hit(x, y, x + len(cap) + cells_wide(text), y + 1, ("item", n))
            x += len(cap) + cells_wide(text) + 1
    return b


def _cards(menu, cols, lines, term, g):
    """The cards look: each item a tile - a picture if it has one, its name, a note - in rows; the
    arrows go through them all four ways."""
    rows, at = menu.rows(), menu.at
    every = [i for i in menu.page().items if menu.seen(i)]
    title = menu.title_now()
    limited = term is not None and getattr(term, "limited_glyphs", False)
    light = "-|++++" if g is ASCII else "─│┌┐└┘"
    strong = "=|####" if g is ASCII else ("═║╔╗╚╝" if limited else "━┃┏┓┗┛")
    pics = [r.picture for r in every if r.picture]
    pic_h = max([(len(p) + 1) // 2 for p in pics] or [0])
    pic_w = max([len(p[0]) for p in pics if p] or [0])
    noted = any(r.note or r.kind in VALUES for r in every)
    cw = max(12, min(30, max([cells_wide(r.label) + 2 for r in every] + [cells_wide(r.says()) for r in every] + [pic_w])))
    cw = min(cw, max(8, cols - 4))
    outer = cw + 4
    count = max(1, min(len(rows) or 1, 4, (cols + 1) // (outer + 1)))
    tall = 2 + pic_h + 1 + (1 if noted else 0)
    hints = [r.hint for r in every if r.hint] + ([menu.said] if menu.said else [])
    W = max(count * (outer + 1) - 1, cells_wide(title))
    hint_rows = max(1, min(2, max([len(wrap(t, W)) for t in hints] or [1]))) if hints or any(r.locked or r.hold for r in every) else 0
    head = 2 if title else 0
    room = max(1, (lines - head - hint_rows) // tall)
    bands = (len(rows) + count - 1) // count
    first = min(menu.tops.get(menu.page_key(), 0), at // count)
    first = max(first, at // count - room + 1, 0)
    menu.tops[menu.page_key()] = first
    menu.columns = count
    shown = max(1, min(room, bands - first))
    b = Board(W, head + shown * tall + hint_rows)
    if title:
        b.put(0, 0, title[:W], "title")
        if first > 0 or first + shown < bands:
            ok = [n for n, r in enumerate(rows) if r.kind != "head"]
            text = "%s%d of %d%s" % (g["up"] + " " if first > 0 else "", ok.index(at) + 1 if at in ok else 0, len(ok),
                                     " " + g["down"] if first + shown < bands else "")
            b.put(W - cells_wide(text), 0, text, "dim")
    if not rows:
        b.put(0, head, "Nothing.", "dim")
    for n in range(first * count, min(len(rows), (first + shown) * count)):
        r = rows[n]
        x0, y0 = (n % count) * (outer + 1), head + (n // count - first) * tall
        sel, why = n == at, menu.why_not(r)
        h_, v_, tl, tr, bl, br = strong if sel else light
        fs = "sel" if sel else "frame"
        b.put(x0, y0, tl + h_ * (outer - 2) + tr, fs)
        b.put(x0, y0 + tall - 1, bl + h_ * (outer - 2) + br, fs)
        for yy in range(y0 + 1, y0 + tall - 1):
            b.put(x0, yy, v_, fs)
            b.put(x0 + outer - 1, yy, v_, fs)
        badge = " %d " % (n + 1)
        b.put(x0 + outer - 2 - len(badge), y0, badge, "sel" if sel else "dim", sel)
        pic = r.picture or []
        left = x0 + 2 + (cw - (len(pic[0]) if pic else 0)) // 2
        for py in range(0, len(pic) - 1, 2):
            for px in range(min(cw, len(pic[py]))):
                up, down = tuple(pic[py][px]), tuple(pic[py + 1][px])
                if not sel:
                    up, down = tuple(int(c * 0.55) for c in up), tuple(int(c * 0.55) for c in down)
                b.rows[y0 + 1 + py // 2][left + px] = ("▀", ("px", up, down), False)
        y = y0 + 1 + pic_h
        text = r.label if cells_wide(r.label) <= cw - 2 else r.label[:cw - 3] + g["ell"]
        if sel:
            b.put(x0 + 2, y, g["mark"], "sel")
        b.put(x0 + 4, y, text, "dim" if why else ("sel" if sel else "item"))
        if noted:
            b.put(x0 + 2, y + 1, r.says()[:cw], "dim" if why or not sel else "val")
        b.hit(x0, y0, x0 + outer, y0 + tall, ("item", n))
    if hint_rows:
        text, how = hint_of(menu, g)
        for i, part in enumerate(wrap(text, W)[:hint_rows]):
            b.put(0, b.h - hint_rows + i, part, how)
    return b


# --------------------------------------------------------------------------- #
# Colours: a theme's roles as the board's styles
# --------------------------------------------------------------------------- #
_BASE = [(0, 0, 0), (170, 0, 0), (0, 170, 0), (170, 85, 0), (0, 0, 170), (170, 0, 170), (0, 170, 170), (170, 170, 170),
         (85, 85, 85), (255, 85, 85), (85, 255, 85), (255, 255, 85), (85, 85, 255), (255, 85, 255), (85, 255, 255),
         (255, 255, 255)]


def rgb_of(spec, roles=None, _depth=0):
    """The foreground of a colour spec (engine.term.Term.spec_params) as ``(r, g, b)``: a palette name, a
    hex, a number of the 256, raw escape numbers, or a role of the theme. None if it names no colour."""
    roles = roles or {}
    rgb = None
    for tok in str(spec or "").split():
        low = tok.lower()
        if low.startswith("on_"):
            continue
        if low.startswith("sgr:"):
            low = low[4:]
        if low in PALETTE:
            rgb = PALETTE[low]
        elif re.fullmatch(r"#[0-9a-f]{3}([0-9a-f]{3})?", low):
            rgb = tuple(parse_hex(low))
        elif re.fullmatch(r"\d+(;\d+)+", low) or (tok.lower().startswith("sgr:") and low.isdigit()):
            parts = [int(p) for p in low.split(";")]
            i = 0
            while i < len(parts):
                p = parts[i]
                if p == 38 and i + 2 < len(parts) and parts[i + 1] == 5:
                    rgb = idx256_to_rgb(parts[i + 2])
                    i += 3
                elif p == 38 and i + 4 < len(parts) and parts[i + 1] == 2:
                    rgb = tuple(parts[i + 2:i + 5])
                    i += 5
                else:
                    if 30 <= p <= 37:
                        rgb = _BASE[p - 30]
                    elif 90 <= p <= 97:
                        rgb = _BASE[p - 82]
                    i += 1
        elif re.fullmatch(r"\d{1,3}", low) and int(low) < 256:
            rgb = idx256_to_rgb(int(low))
        elif low in roles and _depth < 4:
            sub = roles[low] or ""
            got = rgb_of(("sgr:" + sub) if re.fullmatch(r"\d+(;\d+)*", sub) else sub, roles, _depth + 1)
            rgb = got or rgb
    return rgb


def palette(ui=None):
    """Each style's colour for this theme: ``{style: (spec, rgb, bold)}`` and ``"lit"``, the bar's colour."""
    roles = dict(ui.term.roles) if ui is not None else {}
    out = {}
    for style, (role, bold) in STYLES.items():
        spec = role
        if style == "frame" and ui is not None and ui.theme.ui.get("frame_color"):
            spec = ui.theme.ui["frame_color"]
        rgb = rgb_of(spec, roles) or {"hint": (130, 130, 124), "key": (255, 255, 255)}.get(role, (190, 190, 200))
        out[style] = (spec, rgb, bold)
    item = out["item"][1]
    out["lit"] = tuple(int(c * 0.3) for c in item)
    return out


def painted(b, ui, pal=None):
    """The board as lines for a terminal that scrolls, in the theme's colours at whatever depth it has."""
    pal = pal or palette(ui)
    term = ui.term
    lit = "on_#%02x%02x%02x" % pal["lit"]
    out = []
    for row in b.rows:
        line, run, key = [], [], None
        for ch, style, on in row + [(None, None, None)]:
            if (style, on) != key:
                if run and isinstance(key[0], tuple):    # a pixel pair of a picture
                    _px, up, down = key[0]
                    if term.color_depth:
                        line.append(term.paint("".join(run), "#%02x%02x%02x on_#%02x%02x%02x" % (up + down)))
                    else:
                        line.append(" .:-=+*#%@"[min(9, int((sum(up) + sum(down)) / 1530.0 * 10 * 1.7))] * len(run))
                elif run:
                    spec, _rgb, bold = pal[key[0]]
                    line.append(term.paint("".join(run), spec + (" b" if bold else "") + (" " + lit if key[1] else "")))
                run, key = [], (style, on)
            if ch is not None:
                run.append(ch)
        out.append("".join(line))
    return out


def cells(b, pal, paper=PAPER):
    """The board as rows of cells ``(char, fg, bg)`` for a frame (engine/frame.py)."""
    lit = pal["lit"]
    return [[(None, style[1], style[2]) if isinstance(style, tuple) else (ch, pal[style][1], lit if on else paper)
             for ch, style, on in row] for row in b.rows]


def frame_of(ui):
    """The frame a game's menus are drawn in unless a menu names its own: the game's (``menu_border``),
    else the theme's (``menu_frame`` in its ``ui``; else the frame of its menus or its descriptions)."""
    if ui is None:
        return None
    theme = ui.theme
    for name in (getattr(ui, "menu_border", None), theme.ui.get("menu_frame"), theme.style("menu")["frame"],
                 theme.style("description")["frame"]):
        if name and str(name).split()[0].lower() in BORDERS and str(name).lower() != "none":
            return str(name).lower()
    return "single"


# --------------------------------------------------------------------------- #
# Showing a menu
# --------------------------------------------------------------------------- #
def able(ui):
    """Whether single keys can be read and lines redrawn in place here."""
    term = ui.term
    return bool(term.is_tty and term.ansi and term.inp is None and getattr(ui, "menus", None) != "lines")


def show(ui, menu, screen=None, backdrop=None, keys=None, idle=None):
    """Show a menu the best way there is here: over ``screen`` (a frame kind's, started), else in the
    text where keys can be read, else as numbered lines. The item chosen, or None."""
    if screen is not None and getattr(screen, "started", False):
        return over(screen, menu, backdrop, ui)
    if keys is not None or able(ui):
        return inline(ui, menu, keys, idle)
    return lines(ui, menu)


def lines(ui, menu):
    """The menu as CLIo's numbered lines, answered by typing: for a pipe, a plain terminal, a reader."""
    menu.plain = True
    while not menu.done:
        rows = [r for r in menu.rows() if r.kind != "head"]
        if not rows:
            menu.back()
            continue
        labels = []
        for r in rows:
            why = menu.why_not(r)
            says = r.says()
            says = (": {item}%s{/}" % says if r.kind in VALUES else " {hint}(%s){/}" % says) if says else ""
            labels.append("%s%s%s" % (r.label, says, (" {hint}- %s{/}" % why) if why else ""))
        top = len(menu.stack) == 1
        pick = ui.menu(labels, title=menu.title_now() or None, cancel=menu.cancel or not top,
                       cancel_label=("Back" if not top else "Done") if (menu.cancel or not top) else None)
        if pick is None:
            if top and not menu.cancel:
                continue
            menu.back()
            continue
        item = rows[pick]
        menu.to(menu.rows().index(item))
        menu.said = ""
        why = menu.why_not(item)
        if why:
            menu.said = why
        elif item.kind == "slide":
            raw = ui.ask("%s (%s to %s)" % (item.label, item.low, item.high))
            try:
                menu.set(item, float(raw) if "." in raw else int(raw))
            except ValueError:
                menu.said = "A number from %s to %s." % (item.low, item.high)
        elif item.kind in ("text", "bind"):
            raw = ui.ask(item.label)
            if raw:
                menu.set(item, raw)
        else:
            menu.act(item)
        if menu.said:
            ui.line(" " + ui.fmt(menu.said, "hint"))
    menu.plain = False
    return menu.result


def inline(ui, menu, keys=None, idle=None):
    """The menu in the text: a few lines, redrawn in place as the cursor moves; when it is done they
    are gone and one line says what was chosen. ``idle``: ``(seconds, fn)``, called when no key comes
    for that long (a demo plays), after which the menu is drawn again."""
    term = ui.term
    if keys is None:
        from .keys import KeyReader
        keys = KeyReader()
    try:
        keys.start()
    except Exception:
        return lines(ui, menu)
    drawn = 0
    quiet = now()
    ended = False
    try:
        term.write(CSI + "?25l")
        while not menu.done:
            cols, rows = term.size()
            b = board(menu, max(24, min(ui.width, cols - 1)), max(6, rows - 2), term, frame_of(ui))
            out = painted(b, ui) + [" " + ui.c(b.keys[:max(8, cols - 3)], "hint")]
            buf = []
            if drawn:
                buf.append("%s%dA\r" % (CSI, drawn))
            buf += ["%s2K%s\r\n" % (CSI, ln) for ln in out]
            if len(out) < drawn:
                buf.append(CSI + "J")
            term.write("".join(buf))
            term.flush()
            drawn = len(out)
            while True:
                k = keys.get(0.1)
                if k is not None:
                    break
                if idle and now() - quiet >= idle[0]:
                    term.write("%s%dA\r%sJ%s?25h" % (CSI, drawn, CSI, CSI))
                    idle[1]()
                    term.write(CSI + "?25l")
                    drawn, quiet = 0, now()
                    break
            if k is None:
                continue
            quiet = now()
            if k == "ctrl-d":                            # the end of input
                ended = True
                menu.leave()
            elif not k.startswith(("mouse:", "mouseup:")):
                menu.key(k)
    finally:
        try:
            keys.stop()
        finally:
            term.write(("%s%dA\r%sJ" % (CSI, drawn, CSI) if drawn else "") + CSI + "?25h")
            term.flush()
    if ended and not menu.cancel:
        raise QuitGame()
    said(ui, menu)
    return menu.result


def said(ui, menu):
    """One line in the text for what a menu came to."""
    r = menu.result
    if r is not None:
        g = glyphs_of(ui.term)
        ui.line(" %s %s" % (ui.c(g["mark"], "key"), ui.fmt(r.label, "menu")))


def dimmed(rows, cols, count, by=0.32):
    """A frame's rows gone dark, ``count`` of them ``cols`` wide: what is behind a menu."""
    out = []
    for r in list(rows or [])[:count]:
        if isinstance(r, list):
            row = [(ch, (int(fg[0] * by), int(fg[1] * by), int(fg[2] * by)) if fg else fg,
                    (int(bg[0] * by), int(bg[1] * by), int(bg[2] * by)) if bg else bg) for ch, fg, bg in r[:cols]]
        else:
            text = strip_ansi(str(r))[:cols]
            row = [(ch, (70, 70, 74), None) for ch in text]
        out.append(row + [(" ", None, None)] * (cols - len(row)))
    while len(out) < count:
        out.append([(" ", None, None)] * cols)
    return out


def over(screen, menu, backdrop=None, ui=None, mouse=True, after=""):
    """The menu in a box over a frame: ``backdrop``, the rows the kind last drew (or a function that
    gives them), goes dark behind it. ``after``: what to write when it is done (a kind's own mouse
    mode back). On a screen that reads typed lines only, the items are numbered."""
    term = ui.term if ui is not None else screen.term
    typed = screen.keys is None
    state = {"board": None, "x": 0, "y": 0}

    def draw():
        W, H = screen.size()
        b = board(menu, min(W - 2, 78), H - 3, term, frame_of(ui), numbers=typed, roomy=True)
        pal = palette(ui)                                # as the theme is now: a style changed in the menu shows
        behind = backdrop() if callable(backdrop) else backdrop
        rows = dimmed(behind, W, H - 2)
        x0, y0 = max(0, (W - b.w) // 2), max(0, (H - 2 - b.h) // 2)
        if menu.look_now() in ("line", "terminal", "cards") or \
                border(menu.border_now() or frame_of(ui), term).name in ("none", "rule", "corners", "brackets"):
            for yy in range(max(0, y0 - 1), min(len(rows), y0 + b.h + 1)):       # no box of its own: room round it
                for xx in range(max(0, x0 - 2), min(W, x0 + b.w + 2)):
                    rows[yy][xx] = (" ", None, PAPER)
        for i, row in enumerate(cells(b, pal)):
            if y0 + i < len(rows):
                rows[y0 + i][x0:x0 + b.w] = row[:W - x0]
        state.update(board=b, x=x0, y=y0)
        menu.once = typed
        if typed:
            screen.frame(rows, prompt="menu> ", footer=screen.paint.text([(b.keys, "dim")], W, screen.glyphs["ell"]))
        else:
            screen.frame(rows, status=b.keys, footer="")   # the kind's own line of keys is not true now

    if typed:
        while not menu.done:
            line = screen.read(draw)
            if line is None:
                menu.leave()
                break
            words = line.split()
            menu.said = ""
            if not words:
                menu.back()
                continue
            ok = [n for n, r in enumerate(menu.rows()) if r.kind != "head"]
            if not words[0].isdigit() or not 1 <= int(words[0]) <= len(ok):
                menu.said = "Its number, from 1 to %d." % len(ok)
                continue
            menu.to(ok[int(words[0]) - 1])
            item = menu.current()
            if len(words) > 1 and item.kind in ("slide", "text", "bind"):
                raw = " ".join(words[1:])
                try:
                    menu.set(item, (float(raw) if "." in raw else int(raw)) if item.kind == "slide" else raw)
                except ValueError:
                    menu.said = "A number from %s to %s." % (item.low, item.high)
            else:
                menu.act(item)
        return menu.result
    # clicks are asked for only where the key reader knows a mouse report when it sees one (not from Windows'
    # msvcrt, which would hand a report over as keys typed)
    mouse = mouse and not getattr(screen.keys, "win", False)
    if mouse:
        screen.write(MOUSE_ON)
    try:
        screen.shown = {}
        dirty = True
        while not menu.done:
            if dirty or screen.resized():
                draw()
            k = screen.keys.get(0.1)
            dirty = k is not None
            if k is None:
                continue
            if k == "ctrl-d":
                menu.leave()
            elif k.startswith("mouse:"):
                try:
                    _m, button, x, y = k.split(":")
                    button, x, y = int(button), int(x), int(y)
                except ValueError:
                    continue
                if button & 64:
                    menu.click(("wheel", 1 if button & 1 else -1))
                else:
                    menu.click(state["board"].at(x - state["x"], y - state["y"]))
            elif not k.startswith("mouseup:"):
                menu.key(k)
    finally:
        if mouse:
            screen.write(MOUSE_OFF + after)
        screen.shown = {}
    return menu.result


def choose(ui, options, title=None, cancel=True, cancel_label=None, idle=None, keys=None):
    """A plain list of choices as a menu in the text (what :meth:`engine.ui.UI.menu` shows when a game's
    menus are answered with keys): the number of the one chosen from 0, or None."""
    items = [Item(id=str(n), label=ui.term.strip_markup(str(o))) for n, o in enumerate(options)]
    if cancel and cancel_label:
        items.append(Item(id="cancel", label=ui.term.strip_markup(str(cancel_label))))
    look = "find" if len(items) > FIND_OVER else (getattr(ui, "menu_look", None) or "bar")
    m = Menu(title=ui.term.strip_markup(str(title)).rstrip(":") if title else "", items=items, look=look, cancel=cancel)
    got = inline(ui, m, keys, idle)
    return None if got is None or got.id == "cancel" else int(got.id)


# --------------------------------------------------------------------------- #
# The menus every game has
# --------------------------------------------------------------------------- #
SPEEDS = [(0.0, "off"), (0.4, "fast"), (1.0, "normal"), (2.0, "slow")]


def options(game, resume=None):
    """Sound and screen, as pages: what ``sound``, ``style``, ``speed`` and ``art`` do when typed.
    ``resume``: what starts the music of where the player is (the game's scene music unless given)."""
    from .theme import available_themes, load_theme
    a, ui, term = game.audio, game.ui, game.term

    def music(i, m):
        a.set_music(i.value)
        if i.value:
            (resume or game.resume_music)()

    def effects_loud(i, m):
        a.set_volume(sfx=i.value / 10.0)
        a.sfx("select")

    def test(i, m):
        m.said = "Played a sound." if a.sfx("quest_done") else "No sound could be played. %s" % (a.note or "")

    sound = [Item(id="music", kind="check", label="Music", value=bool(a.music_on), on=music,
                  hint="The music of the game, on or off."),
             Item(id="music_volume", kind="slide", label="Music volume", value=int(round(a.music_volume * 10)),
                  on=lambda i, m: a.set_volume(music=i.value / 10.0), hint="How loud the music is."),
             Item(id="effects", kind="check", label="Effects", value=bool(a.sfx_on), on=lambda i, m: a.set_sfx(i.value),
                  hint="The sounds of what happens."),
             Item(id="effects_volume", kind="slide", label="Effects volume", value=int(round(a.sfx_volume * 10)),
                  on=effects_loud, hint="How loud the effects are. You hear it as you change it.")]
    if a.sets:
        sound.append(Item(id="sound_set", kind="cycle", label="Sound set", value=a.sound_set or "",
                          choices=[("", "the game's own")] + [(n, n) for n in sorted(a.sets)],
                          on=lambda i, m: a.set_sound_set(i.value), hint="Other sounds for the same things."))
    sound.append(Item(id="sound_test", label="Test the sound", on=test, stay=True, hint="Plays one sound."))
    themes = available_themes(game.data.dir)
    speed = min(SPEEDS, key=lambda s: abs(s[0] - float(term.speed or 0)))[0]

    def style(i, m):
        ui.apply_theme(load_theme(i.value, game.data.dir))

    def menus_now(i, m):
        ui.menus = i.value

    screen = [Item(id="style", kind="cycle", label="Style", value=ui.theme.name if ui.theme.name in themes else themes[0],
                   choices=themes, on=style, hint="The colours and frames of everything. It changes as you choose."),
              Item(id="speed", kind="cycle", label="Text speed", value=speed, choices=SPEEDS,
                   on=lambda i, m: setattr(term, "speed", i.value), hint="How fast text is written out."),
              Item(id="art", kind="check", label="Pictures", value=bool(game.settings.get("art", True)),
                   on=lambda i, m: game.settings.__setitem__("art", i.value), hint="Pictures of places and people."),
              Item(id="frame", kind="cycle", label="Menu frame", value=str(getattr(ui, "menu_border", None) or ""),
                   choices=[("", "the style's")] + [(n, n) for n in BORDERS] + [("double shadow", "double, a shadow")],
                   on=lambda i, m: setattr(ui, "menu_border", i.value or None), hint="The box menus are drawn in."),
              Item(id="menus", kind="cycle", label="Menus", value="bar" if getattr(ui, "menus", None) == "bar" else "",
                   choices=[("", "typed numbers"), ("bar", "keys")], on=menus_now,
                   hint="How lists of choices are answered: by typing a number, or with the arrow keys.")]
    return Menu(id="options", title="Options", look="tabs",
                items=[Item(kind="go", id="sound", label="Sound", items=sound),
                       Item(kind="go", id="screen", label="Screen", items=screen)])


def game_menu(game, can=("save", "load", "help", "quit"), title=None, resume=None):
    """Resume, options, and what of ``can`` the game does here: the menu behind ``menu`` and Esc."""
    opts = options(game, resume)
    items = [Item(id="resume", label="Resume", key="r", hint="Back to the game."),
             Item(kind="go", id="options", label="Options", key="o", look="tabs", items=opts.items,
                  note="sound, screen", hint="Music, effects, the look.")]
    words = {"save": ("Save", "s", "Keep the game as it is now."), "load": ("Load", "l", "Go back to the last save."),
             "help": ("Help", "h", "The keys and the commands."), "records": ("Records", "", "The best runs."),
             "about": ("About", "", "Who made this, and with what."), "quit": ("Leave the game", "q", "It asks first.")}
    sure = "Leave the run? It is saved and will wait for you." if getattr(game, "permadeath", False) \
        else "Leave the game? Unsaved progress will be lost."
    for name in can:
        if name in words:
            label, key, hint = words[name]
            items.append(Item(id=name, label=label, key=key, hint=hint, confirm=sure if name == "quit" else None))
    return Menu(id="game", title=title or game.data.title, look=getattr(game.ui, "menu_look", None) or "bar", items=items)


# --------------------------------------------------------------------------- #
# A game's own menus: menus.json
# --------------------------------------------------------------------------- #
def from_data(game, name):
    """A menu of the game's ``menus.json``, its conditions answered by the game as it stands now and
    its values taken from the world's vars and flags. None if there is none of that name."""
    from . import conditions
    spec = (getattr(game.data, "menus", None) or {}).get(name)
    if not isinstance(spec, dict):
        return None
    w = game.world

    def bind(items):
        for i in items:
            if i.kind == "go":
                bind(i.items)
            elif i.kind in VALUES:
                if i.var and i.var in w.vars:
                    i.value = w.vars[i.var]
                elif i.flag:
                    i.value = bool(w.flags.get(i.flag))

    def changed(i):
        if i.var:
            w.vars[i.var] = i.value
        elif i.flag:
            if i.value:
                w.flags[i.flag] = True
            else:
                w.flags.pop(i.flag, None)

    m = Menu(spec, id=name, test=lambda cond: conditions.check(cond, game), on_change=changed)
    bind(m.items)
    return m


def play(game, name, screen=None, backdrop=None):
    """Show a menu of the game's and run the effects of what is chosen (an item with ``"again"`` brings
    the menu back after them). The item chosen last, or None."""
    from . import conditions
    got = None
    while not game.over:
        m = from_data(game, name)
        if m is None:
            game.say("There is no menu called '%s'." % name, "error")
            return None
        got = show(game.ui, m, screen, backdrop)
        if got is None:
            break
        if got.effects:
            conditions.run(got.effects, game)
        if not got.again:
            break
    return got


def problems(data):
    """What is wrong in a game's ``menus.json`` (for ``--check``)."""
    out = []
    cfg = getattr(data, "config", None) or {}
    if cfg.get("menu_look") not in (None, "bar", "line", "terminal", "cards"):
        out.append("game.json: unknown menu_look '%s' (bar, line, terminal, cards)" % cfg.get("menu_look"))
    if cfg.get("menu_border") is not None and str(cfg["menu_border"]).split()[:1] not in [[n] for n in BORDERS]:
        out.append("game.json: unknown menu_border '%s' (%s)" % (cfg["menu_border"], ", ".join(BORDERS)))
    menus = getattr(data, "menus", None)
    if menus is None or menus == {}:
        return out
    if not isinstance(menus, dict):
        return ["menus.json should be a map of menus by name"]

    def bad_border(where, value):
        if value is not None and (not str(value).split() or str(value).split()[0].lower() not in BORDERS):
            out.append("%s: unknown border '%s' (%s)" % (where, value, ", ".join(BORDERS)))

    def walk(where, items, seen):
        if not isinstance(items, list) or not items:
            out.append("%s: it needs a list of \"items\"" % where)
            return
        for n, i in enumerate(items):
            at = "%s item %d" % (where, n + 1)
            if not isinstance(i, dict):
                out.append("%s: it should be a map" % at)
                continue
            kind = i.get("kind") or ("go" if "items" in i else "do")
            if kind not in KINDS:
                out.append("%s: unknown kind '%s' (%s)" % (at, kind, ", ".join(KINDS)))
                continue
            label = i.get("label", i.get("text"))
            if not label and kind != "head":
                out.append("%s: it needs a \"label\"" % at)
            iid = i.get("id") or slug(label or "")
            if kind != "head":
                if iid in seen:
                    out.append("%s: the id '%s' is used twice in this menu" % (at, iid))
                seen.add(iid)
            if kind == "go":
                walk(at, i.get("items"), seen)
            if kind == "cycle" and not i.get("choices"):
                out.append("%s: a cycle needs \"choices\"" % at)
            if kind == "slide":
                low, high = i.get("low", 0), i.get("high", 10)
                if not all(isinstance(v, (int, float)) for v in (low, high)) or low >= high:
                    out.append("%s: a slide needs \"low\" under \"high\"" % at)
            if kind in VALUES and not (i.get("var") or i.get("flag")):
                out.append("%s: a value needs a \"var\" (or a \"flag\") to be kept in" % at)
            if i.get("look") not in (None,) + LOOKS:
                out.append("%s: unknown look '%s' (%s)" % (at, i.get("look"), ", ".join(LOOKS)))
            bad_border(at, i.get("border"))
    for name, spec in menus.items():
        where = "menu '%s'" % name
        if not isinstance(spec, dict):
            out.append("%s: it should be a map" % where)
            continue
        if spec.get("look") not in (None,) + LOOKS:
            out.append("%s: unknown look '%s' (%s)" % (where, spec.get("look"), ", ".join(LOOKS)))
        bad_border(where, spec.get("border"))
        walk(where, spec.get("items"), set())
    return out


# --------------------------------------------------------------------------- #
# A look at the looks
# --------------------------------------------------------------------------- #
def sample():
    works = ["Palms", "Beds", "Quarry", "Diggings", "Wall", "Watch post", "Forge", "Lodge", "Ring of stones",
             "Stillroom", "Weaving shed", "Canal", "Mycel cellar", "Ironwork", "Sky tablets", "Ford", "Granary"]

    def land(seed):
        import math
        return [[(30 + int(90 * abs(math.sin(x * 0.45 + seed))), 50 + int(110 * abs(math.cos(y * 0.6 + seed * 1.7))),
                  70 + int(60 * abs(math.sin((x + y) * 0.3 + seed)))) for x in range(20)] for y in range(8)]
    return Menu(title="A menu", items=[
        {"id": "resume", "label": "Resume", "hint": "Back to where you were."},
        {"label": "Options", "look": "tabs", "note": "sound, screen", "hint": "Pages of values.", "items": [
            {"label": "Sound", "items": [
                {"id": "music", "kind": "check", "label": "Music", "value": True, "hint": "On or off: Enter, or left and right."},
                {"id": "loud", "kind": "slide", "label": "Volume", "value": 6, "hint": "Left and right, or a click on the bar."},
                {"id": "set", "kind": "cycle", "label": "Sound set", "choices": ["chip", "rich", "ballistic"]}]},
            {"label": "You", "items": [
                {"id": "name", "kind": "text", "label": "Name", "value": "Er", "hint": "Enter, type, Enter."},
                {"id": "fire", "kind": "bind", "label": "Fire", "value": "space", "hint": "Enter, then the key."}]}]},
        {"label": "Build", "look": "find", "hint": "A long list: type to find.",
         "items": [{"label": w, "note": "%d stone" % (20 + 7 * n)} for n, w in enumerate(works)]},
        {"label": "Realm", "title": "Gordian Moon", "look": "line", "hint": "The line look.", "items": [
            {"id": "continue", "label": "Continue", "note": "Fer, Year 19", "hint": "Go on where you left."},
            {"id": "new", "label": "New realm", "hint": "Choose where the Fers begin."},
            {"id": "lamp", "kind": "check", "label": "The lamp", "value": True}, {"id": "leave", "label": "Leave"}]},
        {"label": "Engineering", "title": "Erebus engineering", "look": "terminal", "status": "REACTOR 62%",
         "hint": "The terminal look.", "items": [
            {"id": "probe", "label": "Survey probe", "state": "ready", "tone": "good", "note": "3 aboard", "key": "f2",
             "hint": "A probe to the surface."},
            {"id": "beacon", "label": "Relay beacon", "state": "ready", "tone": "good", "hold": True, "key": "f3",
             "hint": "Enter arms it; hold Enter and it goes. It cannot be taken back."},
            {"id": "scan", "label": "Hull scan", "state": "running", "tone": "warn", "note": "41%", "key": "f4"},
            {"id": "cage", "label": "Field cage", "locked": "The reactor is under 80%."},
            {"id": "boat", "label": "Lifeboat 2", "state": "gone", "tone": "off"}]},
        {"label": "Saved realms", "look": "cards", "hint": "The cards look.", "items": [
            {"id": "s%d" % n, "label": name, "note": when, "picture": land(n), "hint": "A realm kept."}
            for n, (name, when) in enumerate((("Fer", "Year 19, Deep"), ("Taros", "Year 4, Ember"),
                                              ("Rigs", "Year 9, Setting"), ("Bits", "Year 2, Rising")))]
            + [{"id": "new_slot", "label": "New realm", "hint": "An empty place."}]},
        {"id": "cage", "label": "Field cage", "locked": "The reactor is under 80%.", "hint": "Not to be chosen now."},
        {"id": "quit", "label": "Leave", "confirm": "Leave the game?", "hint": "Asks first."}])


def main(argv=None):
    """``python -m engine.menu [THEME]``: try the looks here. ``--border NAME`` (``--borders``: each of
    them), ``--look NAME`` for the top menu, ``--over`` a picture, ``--lines``, ``--print`` as text."""
    import sys
    from .term import Term
    from .theme import available_themes, load_theme
    from .ui import UI
    argv = list(sys.argv[1:] if argv is None else argv)

    def after(flag):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None
    term = Term()
    asked = [after("--border"), after("--look")]
    name = next((a for a in argv if not a.startswith("-") and a not in asked), "elegant")
    ui = UI(term, load_theme(name if name in available_themes() else "default"))
    ui.menu_border = after("--border")
    m = sample()
    if after("--look") in LOOKS:
        m.look = after("--look")
    if "--borders" in argv:
        for bname in list(BORDERS) + ["double shadow", "single caps center"]:
            small = Menu(title=bname.capitalize(), border=bname, items=[
                {"label": "Resume", "hint": "The frame called '%s'." % bname}, {"label": "Options", "items": []}])
            ui.line("\n".join(painted(board(small, 60, 12, term), ui)))
        return 0
    if "--print" in argv:
        for keys in ((), ("down", "enter"), ("down", "down", "enter", "f", "o"), ("3", "down"), ("4", "enter"), ("5",)):
            m = sample()
            for k in keys:
                m.key(k)
            b = board(m, 76, 24, term, frame_of(ui))
            print("\n".join(b.plain()) + "\n " + b.keys + "\n")
        return 0
    ui.menus = "lines" if "--lines" in argv else "bar"
    if "--over" in argv and able(ui):
        from .frame import Screen
        from .keys import KeyReader
        screen = Screen(term, KeyReader(), {}, False)
        screen.start()
        try:
            W, H = screen.size()
            back = [[(None, (20 + 3 * (x % 40), 60 + 2 * y, 90 + x), (10 + 2 * y, 30 + x, 60 + 3 * (y % 20)))
                     for x in range(W)] for y in range(H - 2)]
            got = over(screen, m, back, ui)
        finally:
            screen.stop()
    else:
        ui.line(ui.fmt("The looks of a menu. Arrows, Enter, Esc; a click where --over is given.", "hint"))
        got = show(ui, m)
    ui.line("Chosen: %s    Values: %s" % (got.id if got is not None else "nothing", m.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
