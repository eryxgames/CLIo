# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Menus (engine/menu.py): items and their values, the keys, pages, finding, what cannot be chosen, the
picture of a menu and what a click on it means, colours from a theme, the three ways a menu is shown
(numbered lines, in the text, over a frame), the menus every game has, a game's own menus as data, and
the menu in a first-person level and a realm."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from helpers import Session  # noqa: E402
from engine import menu as M  # noqa: E402
from engine.frame import Screen  # noqa: E402
from engine.keys import ScriptedKeys  # noqa: E402
from engine.menu import Item, Menu  # noqa: E402
from engine.term import QuitGame, Term, strip_ansi  # noqa: E402
from engine.theme import load_theme  # noqa: E402
from engine.ui import UI  # noqa: E402

STARTER = os.path.join(ROOT, "templates", "starter")


def menu(**more):
    return Menu(title="Paused", items=[
        {"id": "resume", "label": "Resume", "hint": "Back to it."},
        {"label": "Sound", "items": [
            {"id": "music", "kind": "check", "label": "Music", "value": True},
            {"id": "loud", "kind": "slide", "label": "Volume", "value": 6},
            {"id": "set", "kind": "cycle", "label": "Set", "choices": ["chip", ["rich", "Rich one"], "ballistic"]}]},
        {"kind": "head", "label": "The game"},
        {"id": "save", "label": "Save", "key": "s", "note": "slot 2"},
        {"id": "sell", "label": "Sell the ship", "locked": "Nobody is buying."},
        {"id": "quit", "label": "Leave", "confirm": "Leave the game?"}], **more)


def keys(m, *names):
    for k in names:
        m.key(k)
    return m


def term(inp=None, width=80, uni=True, color=0, glyphs=None):
    return Term(out=io.StringIO(), inp=inp, width=width, height=30, color=color, unicode=uni, animate=False,
                env={}, glyphs=glyphs)


def ui_of(lines=(), theme="default", **kw):
    feed = list(lines)

    def inp(prompt):
        if not feed:
            raise EOFError
        return feed.pop(0)
    return UI(term(inp, **kw), load_theme(theme))


def screen(presses):
    sc = Screen(term(color=3), ScriptedKeys(presses) if presses is not None else None, {}, animate=False,
                out=io.StringIO())
    sc.size = lambda: (80, 24)
    sc.started = True
    return sc


class ItemTests(unittest.TestCase):
    def test_kinds_ids_and_first_values(self):
        m = menu()
        self.assertEqual([(i.kind, i.id) for i in m.items],
                         [("do", "resume"), ("go", "sound"), ("head", "the_game"), ("do", "save"), ("do", "sell"), ("do", "quit")])
        self.assertEqual(Item(label="Sell the ship!").id, "sell_the_ship")
        self.assertEqual(m.values(), {"music": True, "loud": 6, "set": "chip"})
        self.assertEqual([Item(kind=k).value for k in ("check", "slide", "text", "bind")], [False, 0, "", ""])
        self.assertEqual(Item(kind="cycle", choices=["a", "b"]).value, "a")
        self.assertEqual(Item(kind="no such", label="X").kind, "do")
        self.assertEqual(m.find("loud").says(), "6")
        self.assertEqual([Item(kind="check", value=v).says() for v in (True, False)], ["on", "off"])
        self.assertEqual(Item(kind="slide", value=0.5, unit=" s").says(), "0.5 s")
        self.assertEqual(Item(kind="cycle", choices=[["rich", "Rich one"]]).says(), "Rich one")
        self.assertIsNone(m.find("nothing"))


class KeyTests(unittest.TestCase):
    def test_the_cursor_goes_round_and_never_onto_a_heading(self):
        m = menu()
        self.assertEqual(m.current().id, "resume")
        self.assertEqual(keys(m, "down").current().id, "sound")
        self.assertEqual(keys(m, "down").current().id, "save")               # over the heading
        self.assertEqual(keys(m, "up").current().id, "sound")
        self.assertEqual(keys(m, "up", "up").current().id, "quit")           # round the top
        self.assertEqual(keys(m, "down").current().id, "resume")
        self.assertEqual(keys(m, "end").current().id, "quit")
        self.assertEqual(keys(m, "home").current().id, "resume")
        self.assertEqual(keys(m, "pgdn").current().id, "quit")
        self.assertEqual(keys(m, "pgup", "tab").current().id, "sound")
        self.assertEqual(keys(m, "shift-tab").current().id, "resume")

    def test_enter_chooses_and_the_menu_is_done(self):
        m = keys(menu(), "enter")
        self.assertTrue(m.done)
        self.assertEqual(m.result.id, "resume")
        m = keys(menu(), "esc")
        self.assertEqual((m.done, m.result), (True, None))
        m = keys(menu(cancel=False), "esc", "backspace")
        self.assertFalse(m.done)                                             # no way out but a choice

    def test_digits_letters_and_keys_of_their_own(self):
        self.assertEqual(keys(menu(), "3").result.id, "save")                # the third that can be chosen
        self.assertEqual(keys(menu(), "9").done, False)
        m = keys(menu(), "s")                                                # its own key: straight to it, and done
        self.assertEqual(m.result.id, "save")
        m = keys(menu(), "l")                                                # a first letter: the cursor goes there
        self.assertEqual((m.done, m.current().id), (False, "quit"))
        m = keys(menu(), "j", "j")
        self.assertEqual(m.current().id, "save")
        self.assertEqual(keys(m, "k").current().id, "sound")
        m = Menu(items=[{"label": "Salt"}, {"label": "Sand"}, {"label": "Tin"}])
        self.assertEqual([keys(m, "s").current().label for _ in range(3)], ["Sand", "Salt", "Sand"])

    def test_values_change_and_are_kept_within_what_they_can_be(self):
        heard = []
        m = menu(on_change=lambda i: heard.append((i.id, i.value)))
        keys(m, "down", "enter")
        self.assertEqual(m.title_now(), "Sound")
        keys(m, "enter")                                                     # a check: Enter, or left and right
        self.assertFalse(m.find("music").value)
        keys(m, "right", "left")
        self.assertFalse(m.find("music").value)
        keys(m, "down", "right", "right", "right", "right", "right", "right")
        self.assertEqual(m.find("loud").value, 10)                           # no further than its end
        keys(m, "left", "enter")
        self.assertEqual((m.find("loud").value, m.said), (9, "Left and right change it."))
        keys(m, "down", "left")
        self.assertEqual(m.find("set").value, "ballistic")                   # round
        keys(m, "enter", "right")
        self.assertEqual(m.find("set").value, "rich")
        self.assertEqual(heard[0], ("music", False))
        self.assertEqual(heard[-1], ("set", "rich"))
        self.assertEqual(m.values(), {"music": False, "loud": 9, "set": "rich"})
        self.assertFalse(m.set(m.find("set"), "no such"))
        self.assertFalse(m.set(m.find("loud"), "loud"))
        keys(m, "esc")
        self.assertEqual((m.title_now(), m.current().id, m.done), ("Paused", "sound", False))
        keys(m, "right")                                                     # right goes in, left comes back
        self.assertEqual(m.title_now(), "Sound")
        self.assertEqual(m.current().id, "set")                              # where the cursor was
        keys(m, "up", "up", "up")
        self.assertEqual(keys(m, "backspace").title_now(), "Paused")

    def test_a_typed_line_and_a_key(self):
        heard = []
        m = Menu(items=[{"id": "name", "kind": "text", "label": "Name", "value": "Er", "long": 5,
                         "on": lambda i, m: heard.append(i.value)},
                        {"id": "fire", "kind": "bind", "label": "Fire", "value": "space"}])
        keys(m, "enter", "a", "space", "b", "c", "backspace", "x", "enter")
        self.assertEqual((m.find("name").value, heard, m.editing), ("Era x", ["Era x"], None))   # five at most
        keys(m, "enter", "backspace", "esc")
        self.assertEqual(m.find("name").value, "Era x")                      # Esc leaves it as it was
        self.assertFalse(m.done)
        keys(m, "down", "enter", "ctrl-left")
        self.assertEqual(m.find("fire").value, "ctrl-left")
        keys(m, "enter", "esc")
        self.assertEqual((m.find("fire").value, m.done), ("ctrl-left", False))
        self.assertEqual(m.find("name").value, "Era x")

    def test_what_cannot_be_chosen_says_why(self):
        m = keys(menu(), "end", "up", "enter")
        self.assertEqual((m.done, m.said), (False, "Nobody is buying."))
        keys(m, "down")
        self.assertEqual(m.said, "")
        flags = {"dock": False}
        m = Menu(test=lambda cond: flags.get(cond.lstrip("!"), False) != cond.startswith("!"), items=[
            {"label": "Sail", "locked": "!dock", "why": "The ship is at sea."},
            {"label": "Trade", "when": "dock"},
            {"id": "n", "kind": "slide", "label": "Crew", "locked": lambda: "No berths." if not flags["dock"] else ""}])
        self.assertEqual([r.label for r in m.rows()], ["Sail", "Crew"])
        self.assertEqual(keys(m, "enter").said, "The ship is at sea.")
        self.assertEqual(keys(m, "down", "right").said, "No berths.")
        self.assertEqual(m.find("n").value, 0)
        flags["dock"] = True
        self.assertEqual([r.label for r in m.rows()], ["Sail", "Trade", "Crew"])
        self.assertEqual(keys(m, "home", "enter").result.label, "Sail")

    def test_a_thing_that_asks_first(self):
        m = keys(menu(), "end", "enter")
        self.assertEqual((m.done, m.title_now(), [r.label for r in m.rows()]), (False, "Leave the game?", ["No", "Yes"]))
        keys(m, "enter")                                                     # No: back where it was
        self.assertEqual((m.done, m.title_now(), m.current().id), (False, "Paused", "quit"))
        keys(m, "enter", "down", "enter")
        self.assertEqual((m.done, m.result.id), (True, "quit"))
        m = keys(menu(), "end", "enter", "esc")
        self.assertEqual((m.done, m.title_now()), (False, "Paused"))

    def test_a_thing_done_that_keeps_the_menu(self):
        done = []
        m = Menu(items=[{"id": "test", "label": "Test", "stay": True, "on": lambda i, m: done.append(i.id)},
                        {"id": "go", "label": "Go"}])
        keys(m, "enter", "enter")
        self.assertEqual((done, m.done, m.result), (["test", "test"], False, None))
        self.assertEqual(keys(m, "down", "enter").result.id, "go")


class PageTests(unittest.TestCase):
    def pages(self):
        return Menu(title="Options", look="tabs", items=[
            {"label": "Sound", "items": [{"id": "music", "kind": "check", "label": "Music"},
                                         {"id": "test", "label": "Test the sound", "hint": "Plays one sound, as loud as it is set."}]},
            {"label": "Screen", "items": [{"id": "style", "kind": "cycle", "label": "Style", "choices": ["a", "b"]}]},
            {"label": "Keys", "when": lambda: False, "items": [{"label": "None"}]}])

    def test_tab_turns_the_pages(self):
        m = self.pages()
        self.assertEqual([t.label for t in m.tabs()], ["Sound", "Screen"])
        self.assertEqual([r.id for r in m.rows()], ["music", "test"])
        keys(m, "down", "tab")
        self.assertEqual(([r.id for r in m.rows()], m.current().id), (["style"], "style"))
        keys(m, "tab")
        self.assertEqual((m.tab, m.current().id), (0, "test"))                # each page keeps its cursor
        keys(m, "right")                                                     # on a thing to do, right turns the page
        self.assertEqual(m.tab, 1)
        keys(m, "right")                                                     # on a value it changes the value
        self.assertEqual((m.tab, m.find("style").value), (1, "b"))
        keys(m, "shift-tab", "shift-tab")
        self.assertEqual(m.tab, 1)
        self.assertTrue(keys(m, "esc").done)

    def test_the_box_keeps_its_size_from_page_to_page(self):
        m = self.pages()
        a = M.board(m, 80, 24)
        b = M.board(keys(m, "tab"), 80, 24)
        self.assertEqual((a.w, a.h), (b.w, b.h))
        self.assertIn(" Sound   Screen", a.plain()[1])
        self.assertIn("Tab page", a.keys)
        self.assertEqual(a.at(11, 1), ("tab", 1))
        m.click(("tab", 0))
        self.assertEqual(m.tab, 0)

    def test_as_lines_the_pages_are_a_list(self):
        m = self.pages()
        m.plain = True
        self.assertEqual([r.label for r in m.rows()], ["Sound", "Screen"])


class FindTests(unittest.TestCase):
    def works(self):
        names = ["Palms", "Forge", "Lodge of the Fold", "Ford wall", "Quarry", "Wall", "Foundry pit", "Beds"]
        return Menu(title="Build what?", look="find", items=[{"label": n, "note": "%d stone" % (10 * i)}
                                                             for i, n in enumerate(names)])

    def test_typing_narrows_the_list(self):
        m = keys(self.works(), "f", "o")
        self.assertEqual([r.label for r in m.rows()], ["Forge", "Ford wall", "Foundry pit", "Lodge of the Fold"])
        self.assertEqual(m.current().label, "Forge")                         # what begins with it comes first
        keys(m, "space", "w")
        self.assertEqual([r.label for r in m.rows()], ["Ford wall"])
        keys(m, "backspace", "backspace", "backspace", "backspace")
        self.assertEqual(len(m.rows()), 8)
        keys(m, "w", "a", "l", "l", "down")
        self.assertEqual(m.current().label, "Ford wall")
        self.assertEqual(keys(m, "enter").result.label, "Ford wall")
        m = keys(self.works(), "z", "z")
        self.assertEqual((m.rows(), m.current()), ([], None))
        keys(m, "enter", "esc")                                              # Esc: first what was typed goes
        self.assertEqual((m.query, m.done), ("", False))
        self.assertTrue(keys(m, "esc").done)
        self.assertEqual(keys(self.works(), "2").query, "2")                 # a digit is typed like the rest

    def test_the_picture_says_what_matched_and_how_many(self):
        m = keys(self.works(), "f", "o")
        b = M.board(m, 80, 24)
        text = b.plain()
        self.assertIn("fo_", text[1])
        self.assertIn("4 of 8", text[-1])
        self.assertEqual("".join(ch for ch, style, _ in b.rows[3] if style == "match"), "Fo")
        self.assertEqual("".join(ch for ch, style, _ in b.rows[6] if style == "match"), "Fo")   # of the Fold
        self.assertEqual(M.board(self.works(), 80, 24).h, b.h)               # the box keeps its size
        self.assertIn("Nothing called that.", "\n".join(M.board(keys(m, "z"), 80, 24).plain()))
        self.assertIn("type to find", b.keys)


class BoardTests(unittest.TestCase):
    def test_the_picture_of_a_menu(self):
        b = M.board(keys(menu(), "down"), 60, 20)
        self.assertEqual(b.plain(), [
            "┌─ Paused ────────────────┐",
            "│   Resume                │",
            "│ ► Sound               › │",
            "│ The game                │",
            "│   Save           slot 2 │",
            "│   Sell the ship         │",
            "│   Leave                 │",
            "├─────────────────────────┤",
            "│                         │",
            "└─────────────────────────┘"])
        self.assertEqual({on for _c, _s, on in b.rows[2][1:-1]}, {True})      # the bar: the whole row
        self.assertEqual({on for _c, _s, on in b.rows[1]}, {False})
        self.assertEqual(b.rows[5][4][1], "dim")                             # what cannot be chosen
        self.assertEqual((b.rows[3][2][1], b.rows[0][3][1], b.rows[0][0][1]), ("head", "title", "frame"))
        self.assertEqual(b.keys, "↑↓ move   Enter choose   Esc back")
        self.assertIn("Back to it.", M.board(menu(), 60, 20).plain()[8])
        said = M.board(keys(menu(), "end", "up", "enter"), 60, 20)
        self.assertIn("Nobody is buying.", said.plain()[8])
        self.assertEqual(said.rows[8][2][1], "warn")

    def test_values_and_clicks(self):
        m = keys(menu(), "down", "enter")
        b = M.board(m, 60, 20)
        self.assertEqual(b.plain()[1:4], ["│ ► Music             [■] on  │", "│   Volume  ◄ ██████░░░░ ► 6  │",
                                          "│   Set              ‹ chip › │"])
        self.assertIn("←→ change", b.keys)
        self.assertEqual((b.at(4, 1), b.at(4, 2), b.at(0, 0), b.at(4, 7)), (("item", 0), ("item", 1), None, None))
        self.assertEqual((b.at(12, 2), b.at(26, 2), b.at(14, 2), b.at(23, 2)),
                         (("less", 1), ("more", 1), ("set", 1, 1), ("set", 1, 10)))
        m.click(b.at(14, 2))
        self.assertEqual((m.find("loud").value, m.current().id), (1, "loud"))
        m.click(("more", 1))
        m.click(("item", 0))                                                 # a click on a check turns it
        self.assertEqual((m.find("loud").value, m.find("music").value), (2, False))
        m.click(("item", 2))
        self.assertEqual(m.find("set").value, "rich")
        m.click(("less", 2))
        self.assertEqual(m.find("set").value, "chip")
        m.click(("wheel", 1))
        self.assertEqual(m.current().id, "music")
        m.click(None)
        m.click(("item", 99))
        top = menu()
        top.click(("item", 3))
        self.assertEqual(top.result.id, "save")
        locked = menu()
        locked.click(("item", 4))
        self.assertEqual((locked.done, locked.said), (False, "Nobody is buying."))

    def test_a_long_list_scrolls_and_a_long_label_wraps(self):
        m = Menu(title="Many", items=[{"label": "Item %d" % i} for i in range(1, 31)])
        b = M.board(m, 40, 10)
        self.assertEqual((b.h, b.plain()[1].rstrip("│ "), b.plain()[-1][-13:]), (10, "│ ► Item 1", " 1 of 30 ↓ ─┘"))
        self.assertEqual(len([l for l in b.plain() if "Item" in l]), 8)
        b = M.board(keys(m, "pgdn", "pgdn"), 40, 10)
        text = b.plain()
        self.assertIn("► Item 17", "\n".join(text))
        self.assertIn(" ↑ 17 of 30 ↓ ", text[-1])
        b = M.board(keys(m, "end"), 40, 10)
        self.assertIn("► Item 30", b.plain()[-2])
        self.assertNotIn("↓", b.plain()[-1])
        b = M.board(keys(m, "home"), 40, 10)
        self.assertIn("► Item 1 ", b.plain()[1])
        talk = Menu(items=[{"label": "Tell me again what happened on the night the hauler came down in the marsh."},
                           {"label": "Goodbye."}])
        b = M.board(talk, 40, 20)
        self.assertEqual(b.plain()[1:4], ["│ ► Tell me again what happened on the │",
                                          "│   night the hauler came down in the  │", "│   marsh.                             │"])
        self.assertEqual({b.at(5, y) for y in (1, 2, 3)}, {("item", 0)})
        self.assertEqual(b.at(5, 4), ("item", 1))
        self.assertLessEqual(b.w, 40)

    def test_plain_terminals_and_wide_letters(self):
        b = M.board(keys(menu(), "down", "enter"), 60, 20, term(uni=False))
        self.assertEqual(b.plain()[:3], ["+- Sound ---------------------+", "| > Music             [x] on  |",
                                         "|   Volume  < ######---- > 6  |"])
        self.assertEqual(len({len(l) for l in b.plain()}), 1)
        self.assertTrue(all(ch.isascii() for row in b.rows for ch, _s, _l in row))
        self.assertTrue(b.keys.isascii())
        safe = M.board(menu(), 60, 20, term(glyphs="safe"))
        self.assertIn("│ > Resume", safe.plain()[1])
        wide = M.board(Menu(items=[{"label": "東京"}, {"label": "Er"}]), 40, 10)
        self.assertEqual(len({len(row) for row in wide.rows}), 1)
        self.assertEqual([c[0] for c in wide.rows[1][4:8]], ["東", "", "京", ""])
        numbered = M.board(menu(), 60, 20, numbers=True)
        self.assertIn("1. Resume", numbered.plain()[1])
        self.assertIn("3. Save", numbered.plain()[4])
        roomy = M.board(menu(), 60, 30, roomy=True)
        self.assertEqual(roomy.h, 10 + 7)                                    # a blank row between, above and below


def console(**more):
    return Menu(title="Engineering", look="terminal", status="REACTOR 62%", items=[
        {"id": "probe", "label": "Survey probe", "state": "ready", "tone": "good", "note": "3 aboard", "key": "f2",
         "hint": "A probe to the surface."},
        {"id": "beacon", "label": "Relay beacon", "state": "ready", "hold": True, "key": "f3"},
        {"id": "scan", "label": "Hull scan", "state": "running", "tone": "warn", "note": "41%"},
        {"id": "cage", "label": "Field cage", "locked": "The reactor is under 80%."},
        {"id": "boat", "label": "Lifeboat 2", "state": "gone", "tone": "off"}], **more)


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class BorderTests(unittest.TestCase):
    def small(self, border=None, **more):
        return Menu(title="Box", border=border, items=[{"label": "Resume", "hint": "Back."}, {"label": "More", "items": [
            {"label": "Deeper"}]}], **more)

    def test_every_frame_draws_a_box_of_the_same_size(self):
        sizes = set()
        for name, chars in M.BORDERS.items():
            self.assertEqual(len(chars), 11, name)
            b = M.board(self.small(name), 60, 12)
            sizes.add((b.w, b.h))
            text = b.plain()
            self.assertIn("Box", text[0])
            self.assertIn("Resume", text[1])
            self.assertIn("Back.", text[4])
        self.assertEqual(len(sizes), 1)
        text = M.board(self.small("dos"), 60, 12).plain()
        self.assertEqual((text[0][0], text[0][-1], text[3], text[5]), ("╒", "╕", "╞" + "═" * 24 + "╡", "╘" + "═" * 24 + "╛"))
        self.assertEqual(M.board(self.small("corners"), 60, 12).plain()[::5], ["┌  Box                   ┐", "└                        ┘"])
        self.assertEqual(M.board(self.small("cut"), 60, 12).plain()[5], "╲" + "─" * 24 + "╱")
        self.assertEqual(M.board(self.small("block"), 60, 12).plain()[5], "▙" + "▄" * 24 + "▟")
        self.assertEqual(M.board(self.small("nonsense"), 60, 12).plain(), M.board(self.small("single"), 60, 12).plain())
        self.assertEqual(M.board(self.small(), 60, 12, frame="═║╔╗╚╝").plain()[3], "╟" + "─" * 24 + "╢")   # an engine frame
        self.assertEqual(M.board(self.small(), 60, 12, frame="heavy").plain()[0][0], "┏")
        self.assertEqual(M.board(self.small("double"), 60, 12, frame="heavy").plain()[0][0], "╔")           # its own wins

    def test_a_shadow_a_centred_title_and_caps(self):
        plain, shade = M.board(self.small("double"), 60, 12), M.board(self.small("double shadow"), 60, 12)
        self.assertEqual((shade.w, shade.h), (plain.w + 1, plain.h + 1))
        self.assertEqual(shade.plain()[1][-1], "░")
        self.assertEqual(shade.plain()[-1], " " + "░" * plain.w)
        self.assertEqual(shade.plain()[0], plain.plain()[0])
        self.assertEqual(shade.at(4, 1), ("item", 0))
        self.assertEqual(shade.rows[1][-1][1], "shade")
        self.assertLessEqual(M.board(self.small("double shadow"), 27, 12).w, 27)
        self.assertEqual(M.board(self.small("single caps center"), 60, 12).plain()[0], "┌────────┤ Box ├─────────┐")
        self.assertEqual(M.board(self.small("single center"), 60, 12).plain()[0], "┌───────── Box ──────────┐")
        self.assertEqual(M.board(self.small("heavy caps"), 60, 12).plain()[0], "┏┫ Box ┣━━━━━━━━━━━━━━━━━┓")

    def test_a_terminal_without_the_characters_gets_the_nearest(self):
        for name in M.BORDERS:
            b = M.board(self.small(name + " shadow"), 60, 12, term(uni=False))
            self.assertTrue(all(ch.isascii() for row in b.rows for ch, _s, _l in row), name)
        self.assertEqual(M.board(self.small("cut"), 60, 12, term(uni=False)).plain()[0], "+- Box ------------------+")
        self.assertEqual(M.board(self.small("none"), 60, 12, term(uni=False)).plain()[3].strip(), "-" * 24)
        linux = term()
        linux.limited_glyphs = True
        self.assertEqual(M.border("heavy", linux).name, "single")
        self.assertEqual(M.border("double shadow", linux).name, "double")
        self.assertTrue(M.border("double shadow", linux).shadow)
        self.assertIs(M.border(M.border("dots")).__class__, M.Border)

    def test_a_menu_within_a_menu_keeps_the_frame_unless_it_names_its_own(self):
        m = self.small("double")
        self.assertEqual(M.board(keys(m, "down", "enter"), 60, 12).plain()[0][0], "╔")
        m = Menu(border="double", items=[{"label": "More", "border": "heavy", "items": [{"label": "Deeper"}]}])
        self.assertEqual(M.board(keys(m, "enter"), 60, 12).plain()[0][0], "┏")
        self.assertEqual(M.board(keys(m, "esc"), 60, 12).plain()[0][0], "╔")

    def test_a_game_and_a_theme_name_the_frame(self):
        ui = ui_of(theme="techno")
        self.assertEqual(M.frame_of(ui), "double")
        ui.menu_border = "cut shadow"
        self.assertEqual(M.frame_of(ui), "cut shadow")
        M.inline(ui, self.small(), ScriptedKeys(["esc"]))
        self.assertIn("╱─ Box ", strip_ansi(ui.term.out.getvalue()))
        ui.theme.ui["menu_frame"] = "dos"
        ui.menu_border = None
        self.assertEqual(M.frame_of(ui), "dos")
        self.assertIsNone(M.frame_of(None))
        from engine.game import Game
        g = Game(STARTER, term=term(), audio=Session("templates/starter").audio,
                 settings={"menu_border": "heavy", "menu_look": "line"})
        self.assertEqual((g.ui.menu_border, g.ui.menu_look), ("heavy", "line"))
        self.assertEqual(M.game_menu(g).look, "line")
        self.assertIsNone(Game(STARTER, term=term(), audio=Session("templates/starter").audio,
                               settings={"menu_look": "wheel"}).ui.menu_look)

        class Data:
            menus = {"m": {"border": "wavy", "items": [{"label": "A", "border": "double shadow"}, {"label": "B", "border": ""}]}}
            config = {"menu_look": "wheel", "menu_border": "wavy shadow"}
        text = "\n".join(M.problems(Data()))
        for part in ("game.json: unknown menu_look 'wheel' (bar, line, terminal, cards)", "game.json: unknown menu_border 'wavy shadow'",
                     "menu 'm': unknown border 'wavy' (single, rounded, double, dos, heavy, block, cut, dots, ascii, corners,",
                     "menu 'm' item 2: unknown border ''"):
            self.assertIn(part, text)
        self.assertNotIn("item 1: unknown border", text)
        Data.config = {"menu_look": "cards", "menu_border": "rule"}
        Data.menus = {}
        self.assertEqual(M.problems(Data()), [])


class LineTests(unittest.TestCase):
    def realm(self):
        return Menu(title="Gordian Moon", look="line", items=[
            {"id": "continue", "label": "Continue", "note": "Fer, Year 19", "hint": "Go on."},
            {"kind": "head", "label": "Or"}, {"id": "new", "label": "New realm"},
            {"id": "lamp", "kind": "check", "label": "The lamp", "value": True},
            {"id": "old", "label": "The old road", "locked": "It is under water."}])

    def test_letters_of_lines_rules_and_a_rail(self):
        b = M.board(keys(self.realm(), "down"), 76, 24)
        text = b.plain()
        self.assertEqual(text[:3], ["┏━╸┏━┓┏━┓╺┳┓╻┏━┓┏┓╻  ┏┳┓┏━┓┏━┓┏┓╻", "┃╺┓┃ ┃┣┳┛ ┃┃┃┣━┫┃┗┫  ┃┃┃┃ ┃┃ ┃┃┗┫",
                                    "┗━┛┗━┛╹┗╸╺┻┛╹╹ ╹╹ ╹  ╹ ╹┗━┛┗━┛╹ ╹"])
        self.assertEqual(text[4], "━" * b.w)
        self.assertEqual(text[5:12], ["┏━╸", "┃   CONTINUE         Fer, Year 19", "┃   OR", "┣━╸ NEW REALM",
                                      "┃   THE LAMP              [■] on", "┃   THE OLD ROAD", "┗━╸"])
        self.assertEqual((b.rows[8][0][1], b.rows[8][4][1], b.rows[6][4][1], b.rows[10][4][1], b.rows[0][0][1]),
                         ("sel", "sel", "item", "dim", "title"))
        self.assertEqual((b.at(6, 6), b.at(6, 9), b.at(6, 7)), (("item", 0), ("item", 3), None))
        roomy = M.board(self.realm(), 76, 30, roomy=True).plain()
        self.assertEqual(roomy[6:9], ["┣━╸ CONTINUE         Fer, Year 19", "┃", "┃   OR"])
        self.assertIn("Go on.", roomy[-1])
        said = M.board(keys(self.realm(), "end", "enter"), 76, 24)
        self.assertIn("It is under water.", said.plain()[-1])

    def test_where_it_does_not_fit_or_the_font_has_not_the_lines(self):
        narrow = M.board(self.realm(), 30, 24).plain()
        self.assertEqual(narrow[0], "GORDIAN MOON")                          # no room for the letters
        self.assertEqual(narrow[2][0], "━")
        plain = M.board(self.realm(), 76, 24, term(uni=False)).plain()
        self.assertEqual((plain[0], plain[2][:3], plain[3], plain[4][:12]), ("GORDIAN MOON", "---", "+--", "+-> CONTINUE"))
        linux = term()
        linux.limited_glyphs = True
        self.assertEqual(M.board(self.realm(), 76, 24, linux).plain()[3:5], ["┌─", "├─  CONTINUE       Fer, Year 19"])
        many = Menu(title="Many", look="line", items=[{"label": "Item %d" % i} for i in range(1, 31)])
        b = M.board(keys(many, "pgdn", "pgdn"), 60, 14)
        self.assertLessEqual(b.h, 14)
        self.assertIn("┣━╸ ITEM 17", "\n".join(b.plain()))
        self.assertIn("↑ 17 OF 30 ↓", "\n".join(b.plain()))
        self.assertIn("3. NEW", "\n".join(M.board(self.realm(), 76, 24, numbers=True).plain()).replace("2. NEW", "3. NEW"))

    def test_a_banner_in_letters_of_lines(self):
        from engine import banner
        art = banner.make({"text": "Fer 2049", "style": "line"}, 60)
        self.assertEqual(art.style, "line")
        rows, owner = banner.line_rows("Fer")
        self.assertEqual((rows, owner), (["┏━╸┏━╸┏━┓", "┣╸ ┣╸ ┣┳┛", "╹  ┗━╸╹┗╸"], [0, 0, 0, 1, 1, 1, 2, 2, 2]))
        self.assertEqual(banner.line_width("I I"), 4)
        self.assertEqual(len({len(r) for r in banner.line_rows("The quick brown fox, 0123456789: yes - no? a/b + c!")[0]}), 1)
        self.assertEqual(banner.make({"text": "A very long title that cannot fit", "style": "line"}, 30).style, "line")   # wrapped
        self.assertNotEqual(banner.make({"text": "Unbreakablelongword", "style": "line"}, 20).style, "line")
        for g in banner.LINE.values():
            self.assertEqual((len(g), len({len(r) for r in g})), (3, 1))


class TerminalTests(unittest.TestCase):
    def test_functions_with_how_they_stand(self):
        b = M.board(console(), 76, 24)
        self.assertEqual(b.plain(), [
            "ENGINEERING                      REACTOR 62%",
            "─" * 44,
            "▌1 SURVEY PROBE  READY             3 aboard",
            " 2 RELAY BEACON  READY",
            " 3 HULL SCAN     RUNNING                41%",
            " 4 FIELD CAGE    LOCKED",
            " 5 LIFEBOAT 2    GONE",
            "─" * 44,
            " A probe to the surface.",
            " F2  SURVEY PROBE   F3  RELAY BEACON"])
        self.assertEqual([b.rows[y][17][1] for y in (2, 3, 4, 5, 6)], ["good", "val", "warn", "dim", "dim"])
        self.assertEqual({on for _c, _s, on in b.rows[2]}, {True})
        self.assertEqual((b.at(5, 4), b.at(2, 9), b.at(25, 9)), (("item", 2), ("item", 0), ("item", 1)))
        self.assertEqual(M.board(console(), 76, 24, term(uni=False)).plain()[2][:3], "|1 ")
        self.assertIn("NO FUNCTIONS.", "\n".join(M.board(Menu(look="terminal", items=[]), 60, 10).plain()))
        inner = Menu(items=[{"label": "Deck", "look": "terminal", "status": "FLUX HIGH", "items": [{"label": "Pump"}]}])
        self.assertIn("FLUX HIGH", M.board(keys(inner, "enter"), 76, 24).plain()[0])   # a menu within, with its own word
        sc = screen(["esc"])
        M.over(sc, console(), [[(None, (200, 100, 50), (20, 40, 60))] * 80 for _ in range(22)], ui_of(color=3))
        self.assertIn("\x1b[48;2;8;9;12m  \x1b[38;2", sc.out.getvalue())     # no box of its own: room round it
        many = Menu(title="Many", look="terminal", items=[{"label": "Item %d" % i} for i in range(1, 31)])
        b = M.board(keys(many, "end"), 60, 12)
        self.assertEqual(b.h, 12)
        self.assertIn("ITEM 30", b.plain()[-2])

    def test_a_key_with_a_name_does_its_item(self):
        self.assertEqual(keys(console(), "f2").result.id, "probe")
        m = keys(console(), "f9", "ctrl-left")
        self.assertEqual((m.done, m.current().id), (False, "probe"))
        m = keys(console(), "f3")                                            # held to be done: only armed
        self.assertEqual((m.done, m.armed.id), (False, "beacon"))

    def test_held_to_be_done(self):
        clock = Clock()
        with mock.patch.object(M, "now", clock):
            m = keys(console(), "down", "enter")
            self.assertEqual((m.armed.id, m.charge, m.done), ("beacon", 0, False))
            b = M.board(m, 76, 24)
            text = "\n".join(b.plain())
            self.assertIn("RELAY BEACON  ARMED", text)
            self.assertIn("ARMED hold Enter ░░░░░ Esc lets go", text)
            self.assertEqual(b.keys, "Hold Enter to do it   Esc lets go")
            self.assertEqual((b.rows[3][0][0], b.rows[3][0][1], b.rows[3][17][1], b.rows[8][1][1]), ("▌", "hot", "hot", "hot"))
            keys(m, "enter", "enter")
            self.assertIn("██░░░", "\n".join(M.board(m, 76, 24).plain()))
            clock.t += 5                                                     # let go for too long: from the start
            keys(m, "enter")
            self.assertEqual((m.charge, m.done), (1, False))
            keys(m, "enter", "enter", "enter")
            self.assertFalse(m.done)
            keys(m, "enter")
            self.assertEqual((m.done, m.result.id, m.armed), (True, "beacon", None))
            m = keys(console(), "down", "enter", "enter", "esc")             # Esc lets go, and no more
            self.assertEqual((m.armed, m.done, m.charge), (None, False, 0))
            m = keys(console(), "down", "enter", "enter", "down")
            self.assertEqual((m.armed, m.current().id), (None, "scan"))
            m = keys(console(), "down", "enter")
            m.click(("item", 0))
            self.assertEqual((m.armed, m.result.id), (None, "probe"))
            self.assertIn("Enter arm", M.board(keys(console(), "down"), 76, 24).keys)
            box = Menu(items=[{"id": "fire", "label": "Fire", "hold": True}])
            self.assertIn("ARMED", M.board(keys(box, "enter", "enter"), 60, 12).plain()[3])   # in a box too

    def test_where_keys_are_typed_it_asks_instead(self):
        ui = ui_of(["2", "1", "2", "2"])
        got = M.lines(ui, console())
        text = strip_ansi(ui.term.out.getvalue())
        self.assertEqual(got.id, "beacon")
        for part in ("1. Survey probe (3 aboard)", "4. Field cage - The reactor is under 80%.", "Relay beacon?", "1. No", "2. Yes"):
            self.assertIn(part, text)
        sc = screen(None)
        with mock.patch("builtins.input", side_effect=["2", "2"]):
            self.assertEqual(M.over(sc, console(), None, ui_of(color=3)).id, "beacon")
        self.assertIn("Relay beacon?", strip_ansi(sc.out.getvalue()))


class CardTests(unittest.TestCase):
    def slots(self, n=5, pictures=True):
        pic = [[(10 * x, 20 * y, 200) for x in range(8)] for y in range(4)]
        return Menu(title="Saved realms", look="cards", items=[
            {"id": "s%d" % i, "label": "Realm %d" % i, "note": "Year %d" % i, "hint": "Kept.",
             "picture": pic if pictures else None, "locked": "Lost." if i == 4 else None} for i in range(1, n + 1)])

    def test_tiles_in_rows_and_arrows_four_ways(self):
        m = self.slots()
        b = M.board(m, 60, 30)
        self.assertEqual((m.columns, b.w, b.h), (3, 50, 2 + 2 * 6 + 1))
        text = b.plain()
        self.assertEqual(text[0], "Saved realms")
        self.assertEqual(text[2], "┏━━━━━━━━━━ 1 ━┓ ┌────────── 2 ─┐ ┌────────── 3 ─┐")
        self.assertEqual(text[5][:16], "┃ ► Realm 1    ┃")
        self.assertEqual(text[6][:16], "┃ Year 1       ┃")
        self.assertIn("Kept.", text[-1])
        self.assertEqual(b.keys, "↑↓ ←→ move   Enter choose   Esc back")
        self.assertEqual((b.at(20, 4), b.at(40, 9), b.at(0, 0)), (("item", 1), None, None))
        self.assertEqual(b.at(20, 10), ("item", 4))
        keys(m, "right", "right", "right")                                   # no further than the row's end
        self.assertEqual(m.current().id, "s3")
        keys(m, "down")                                                      # nothing under it
        self.assertEqual(m.current().id, "s3")
        keys(m, "left", "down")
        self.assertEqual(m.current().id, "s5")
        keys(m, "up", "up", "left", "left")
        self.assertEqual(m.current().id, "s1")
        self.assertEqual(keys(m, "4").said, "Lost.")
        self.assertEqual(keys(self.slots(), "2").result.id, "s2")
        m.click(("item", 2))
        self.assertEqual(m.result.id, "s3")

    def test_pictures_in_cells_and_in_text(self):
        m = self.slots()
        b = M.board(m, 60, 30)
        self.assertEqual(b.rows[3][4], ("▀", ("px", (0, 0, 200), (0, 20, 200)), False))       # the card chosen: as it is
        self.assertEqual(b.rows[3][21][1][1], (0, 0, 110))                   # the others: darker
        ui = ui_of(color=3)
        cells = M.cells(b, M.palette(ui))
        self.assertEqual(cells[3][4], (None, (0, 0, 200), (0, 20, 200)))
        self.assertIn("38;2;0;0;200;48;2;0;20;200m▀", M.painted(b, ui)[3])
        plain = M.painted(b, ui_of())[3]
        self.assertNotIn("\x1b", plain)
        self.assertNotIn("▀", plain)                                         # no colours: shades in characters
        self.assertEqual(len(strip_ansi(plain)), b.w)
        sc = screen(["right", "enter"])
        self.assertEqual(M.over(sc, self.slots(), None, ui).id, "s2")
        self.assertIn("38;2;10;0;200;48;2;10;20;200m▀", sc.out.getvalue())

    def test_narrow_tall_and_plain(self):
        m = self.slots(pictures=False)
        b = M.board(m, 30, 12)
        self.assertEqual((m.columns, b.h), (1, 2 + 2 * 4 + 1))               # one a row, two rows of them in sight
        keys(m, "down", "down", "down")
        text = M.board(m, 30, 12).plain()
        self.assertIn("↑ 4 of 5 ↓", text[0])
        self.assertIn("Realm 4", "\n".join(text))
        self.assertNotIn("Realm 1 ", "\n".join(text))
        wide = self.slots(9)
        M.board(wide, 120, 30)
        self.assertEqual(wide.columns, 4)                                    # four a row at most
        plain = M.board(self.slots(), 60, 30, term(uni=False))
        self.assertEqual(plain.plain()[2][:16], "#========== 1 =#")
        self.assertTrue(all(ch.isascii() for row in plain.rows for ch, s_, _l in row if not isinstance(s_, tuple)))
        ui = ui_of(["2"])
        self.assertEqual(M.lines(ui, self.slots()).id, "s2")
        self.assertIn("2. Realm 2 (Year 2)", strip_ansi(ui.term.out.getvalue()))


class ColourTests(unittest.TestCase):
    def test_a_colour_spec_as_a_colour(self):
        self.assertEqual(M.rgb_of("amber"), (255, 176, 0))
        self.assertEqual(M.rgb_of("b #ff8800 on_blue"), (255, 136, 0))
        self.assertEqual(M.rgb_of("38;5;146"), (175, 175, 215))
        self.assertEqual(M.rgb_of("1;38;2;1;2;3"), (1, 2, 3))
        self.assertEqual(M.rgb_of("208"), (255, 135, 0))
        self.assertEqual(M.rgb_of("1;31"), (170, 0, 0))
        self.assertEqual(M.rgb_of("menu", {"menu": "38;5;146"}), (175, 175, 215))
        self.assertEqual(M.rgb_of("key", {"key": "list_title", "list_title": "b sky"}), (130, 200, 255))
        self.assertIsNone(M.rgb_of("b"))
        self.assertIsNone(M.rgb_of(""))

    def test_a_themes_colours_and_frame(self):
        frames = {}
        for name in ("default", "elegant", "retro", "techno", "modern", "minimal", "console"):
            ui = ui_of(theme=name, color=3)
            pal = M.palette(ui)
            self.assertEqual(set(pal), set(M.STYLES) | {"lit"})
            self.assertTrue(all(len(pal[s][1]) == 3 for s in M.STYLES), name)
            self.assertLess(sum(pal["lit"]), sum(pal["item"][1]))
            frames[name] = M.frame_of(ui)
        self.assertEqual((frames["default"], frames["techno"], frames["retro"], frames["minimal"], frames["modern"]),
                         ("rounded", "double", "ascii", "single", "heavy"))
        b = M.board(menu(), 60, 20, frame=frames["techno"])
        self.assertEqual((b.plain()[0][0], b.plain()[7][0], b.plain()[7][-1]), ("╔", "╟", "╢"))
        heavy = M.board(menu(), 60, 20, frame=frames["modern"]).plain()[7]
        self.assertEqual((heavy[0], heavy[1], heavy[-1]), ("┣", "━", "┫"))
        ui = ui_of(color=3)
        text = M.painted(M.board(menu(), 60, 20), ui)
        self.assertIn("48;2;", text[1])                                      # the bar is lit
        self.assertNotIn("48;2;", text[4])
        self.assertEqual([strip_ansi(l).rstrip() for l in M.painted(M.board(menu(), 60, 20), ui_of())],
                         M.board(menu(), 60, 20).plain())                     # no colours: the same picture
        cells = M.cells(M.board(menu(), 60, 20), M.palette(ui))
        self.assertEqual((cells[1][4][2], cells[2][4][2]), (M.palette(ui)["lit"], M.PAPER))
        self.assertEqual(cells[1][4][1], M.palette(ui)["sel"][1])


class LinesTests(unittest.TestCase):
    def test_numbered_lines_answered_by_typing(self):
        ui = ui_of(["2", "1", "2", "8", "2", "loud", "3", "0", "4", "5", "0", "0"])
        m = menu()
        got = M.show(ui, m)
        text = strip_ansi(ui.term.out.getvalue())
        self.assertIsNone(got)
        self.assertEqual(m.values(), {"music": False, "loud": 8, "set": "rich"})
        for part in ("Paused", "1. Resume", "2. Sound", "3. Save (slot 2)", "4. Sell the ship - Nobody is buying.", "0. Done",
                     "1. Music: on", "2. Volume: 6", "3. Set: chip", "0. Back", "Volume (0 to 10)", "A number from 0 to 10.",
                     "1. Music: off", "3. Set: Rich one", " Nobody is buying."):
            self.assertIn(part, text)
        self.assertNotIn("The game", text)
        self.assertFalse(m.plain)
        self.assertEqual(M.show(ui_of(["3"]), menu()).id, "save")
        self.assertEqual(M.show(ui_of(["5", "2"]), menu()).id, "quit")       # it asks first: 1 No, 2 Yes
        named = Menu(items=[{"id": "n", "kind": "text", "label": "Name"}, {"id": "ok", "label": "Done"}])
        M.lines(ui_of(["1", "Er", "2"]), named)
        self.assertEqual(named.values(), {"n": "Er"})

    def test_pages_as_lines(self):
        m = PageTests().pages()
        ui = ui_of(["2", "1", "0", "0"])
        M.lines(ui, m)
        text = strip_ansi(ui.term.out.getvalue())
        self.assertEqual(m.find("style").value, "b")
        for part in ("Options", "1. Sound", "2. Screen", "1. Style: a", "1. Style: b"):
            self.assertIn(part, text)

    def test_a_terminal_that_cannot_read_keys_gets_lines(self):
        ui = ui_of(["1"])
        self.assertFalse(M.able(ui))
        self.assertEqual(M.show(ui, menu()).id, "resume")
        real = UI(term(color=3), load_theme("default"))
        real.term.is_tty = real.term.ansi = True
        self.assertTrue(M.able(real))
        real.menus = "lines"
        self.assertFalse(M.able(real))


class InlineTests(unittest.TestCase):
    def test_a_menu_in_the_text_is_redrawn_in_place_and_leaves_a_line(self):
        ui = ui_of(color=3)
        m = menu()
        got = M.inline(ui, m, ScriptedKeys(["down", "down", "enter"]))
        raw = ui.term.out.getvalue()
        self.assertEqual(got.id, "save")
        height = M.board(menu(), 79, 28).h + 1                               # the box and the line of keys
        self.assertEqual(raw.count("\x1b[%dA\r" % height), 3)                # twice redrawn, once taken away
        self.assertTrue(raw.startswith("\x1b[?25l"))
        self.assertIn("\x1b[J\x1b[?25h", raw)
        self.assertTrue(strip_ansi(raw).rstrip().endswith("► Save"))         # what was chosen stays in the text
        self.assertIn("Enter choose", strip_ansi(raw))

    def test_going_back_leaves_nothing_and_the_end_of_input_ends_it(self):
        ui = ui_of()
        self.assertIsNone(M.inline(ui, menu(), ScriptedKeys(["esc"])))
        self.assertNotIn("►", strip_ansi(ui.term.out.getvalue()).splitlines()[-1])
        self.assertIsNone(M.inline(ui_of(), menu(), ScriptedKeys([])))       # Ctrl-D: out of it
        with self.assertRaises(QuitGame):
            M.inline(ui_of(), menu(cancel=False), ScriptedKeys([]))          # no way out: the game ends, as at a prompt
        self.assertIsNone(M.inline(ui_of(), menu(), ScriptedKeys(["mouse:0:4:2", "esc"])))   # no clicks in the text

    def test_a_box_that_changes_its_size_is_cleared_below(self):
        ui = ui_of()
        M.inline(ui, menu(), ScriptedKeys(["end", "enter", "down", "enter"]))  # the question is a smaller box
        self.assertIn("\x1b[J", ui.term.out.getvalue())
        self.assertTrue(strip_ansi(ui.term.out.getvalue()).rstrip().endswith("► Leave"))

    def test_nothing_typed_for_a_while(self):
        ui = ui_of()
        played = []
        clock = [0.0]

        def tick():                                                          # a clock of its own: 4 s a look
            clock[0] += 4.0
            return clock[0]
        with mock.patch.object(M, "now", tick):
            got = M.inline(ui, menu(), ScriptedKeys([None, None, "enter"]), idle=(5, lambda: played.append(1)))
        self.assertEqual((played, got.id), ([1], "resume"))
        self.assertEqual(strip_ansi(ui.term.out.getvalue()).count("─ Paused ─"), 2)   # drawn again after it

    def test_a_list_of_choices(self):
        ui = ui_of()
        self.assertEqual(M.choose(ui, ["{key}North{/}", "South"], "Where to?", keys=ScriptedKeys(["down", "enter"])), 1)
        text = strip_ansi(ui.term.out.getvalue())
        self.assertIn("─ Where to? ─", text)
        self.assertIn("North", text)
        self.assertNotIn("{key}", text)
        self.assertIsNone(M.choose(ui_of(), ["a", "b"], cancel_label="Stay", keys=ScriptedKeys(["end", "enter"])))
        self.assertIsNone(M.choose(ui_of(), ["a", "b"], keys=ScriptedKeys(["esc"])))
        many = ["Thing %d" % i for i in range(20)]
        ui = ui_of()
        self.assertEqual(M.choose(ui, many, keys=ScriptedKeys(["1", "7", "enter"])), 17)          # found by typing
        self.assertIn("type to find", strip_ansi(ui.term.out.getvalue()))

    def test_a_games_lists_of_choices_take_keys_when_asked_to(self):
        ui = ui_of(["2"])
        self.assertEqual(ui.menu(["a", "b"]), 1)                             # as ever
        ui = ui_of(["2"])
        ui.menus = "bar"
        self.assertEqual(ui.menu(["a", "b"]), 1)                             # asked to, but keys cannot be read here
        with mock.patch.object(M, "able", return_value=True), \
                mock.patch.object(M, "choose", return_value=0) as choose:
            self.assertEqual(ui.menu(["a", "b"], title="Which?", cancel_label="Back"), 0)
            self.assertEqual(choose.call_args[0][1:5], (["a", "b"], "Which?", True, "Back"))
            choose.reset_mock()
            ui2 = ui_of(["1"])
            ui2.menus = "bar"
            self.assertEqual(ui2.menu(["Strike", "Guard"], compact=True, aliases={"s": 0}), 0)   # typed words: lines
            choose.assert_not_called()


class OverTests(unittest.TestCase):
    def test_a_menu_over_a_picture(self):
        sc = screen(["down", "down", "enter"])
        back = [[(None, (200, 100, 50), (20, 40, 60))] * 80 for _ in range(22)]
        ui = ui_of(color=3)
        got = M.over(sc, menu(), back, ui)
        raw = sc.out.getvalue()
        self.assertEqual(got.id, "save")
        self.assertTrue(raw.startswith(M.MOUSE_ON))
        self.assertTrue(raw.endswith(M.MOUSE_OFF))
        text = strip_ansi(raw)
        for part in ("Paused", "Resume", "Sell the ship", "Enter choose"):
            self.assertIn(part, text)
        self.assertIn("38;2;64;32;16", raw)                                  # the picture behind, gone dark
        self.assertNotIn("38;2;200;100;50", raw)
        sc = screen(["esc"])
        self.assertIsNone(M.over(sc, menu(), back, ui, mouse=False, after="!"))
        self.assertNotIn(M.MOUSE_ON, sc.out.getvalue())
        sc = screen([])                                                      # the end of input
        self.assertIsNone(M.over(sc, menu(), None, None))
        sc = screen(["esc"])
        sc.keys.win = True                                                   # Windows' reader: no reports asked for
        M.over(sc, menu(), back, ui)
        self.assertNotIn(M.MOUSE_ON, sc.out.getvalue())
        sc = screen(["esc"])
        M.over(sc, menu(), ["a line of \x1b[1mtext\x1b[0m"], ui, after="\x1b[?1002h")
        self.assertIn("a line of text", strip_ansi(sc.out.getvalue()))
        self.assertTrue(sc.out.getvalue().endswith(M.MOUSE_OFF + "\x1b[?1002h"))

    def test_clicks_and_the_wheel(self):
        m = menu()
        b = M.board(m, 66, 21, roomy=True)
        x0, y0 = (80 - b.w) // 2, (22 - b.h) // 2
        row = next(y for y, line in enumerate(b.plain()) if "Save" in line)
        sc = screen(["mouse:65:1:1", "mouse:64:1:1", "mouseup:0:1:1", "mouse:0:0:0", "mouse:0:x",
                     "mouse:0:%d:%d" % (x0 + 6, y0 + row)])
        self.assertEqual(M.over(sc, m, None, ui_of(color=3)).id, "save")

    def test_a_screen_that_reads_typed_lines_numbers_the_items(self):
        sc = screen(None)
        m = menu()
        with mock.patch("builtins.input", side_effect=["9", "x", "2", "2 9", "1", "", "3"]):
            got = M.over(sc, m, None, ui_of(color=3))
        text = strip_ansi(sc.out.getvalue())
        self.assertEqual((got.id, m.values()), ("save", {"music": False, "loud": 9, "set": "chip"}))
        for part in ("1. Resume", "3. Save", "2. Volume", "menu> ", "Its number, from 1 to 5."):
            self.assertIn(part, text)
        self.assertNotIn(M.MOUSE_ON, sc.out.getvalue())
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertIsNone(M.over(screen(None), menu(), None, None))

    def test_show_takes_a_started_screen(self):
        sc = screen(["enter"])
        self.assertEqual(M.show(ui_of(color=3), menu(), sc).id, "resume")
        sc.started = False
        self.assertEqual(M.show(ui_of(["3"]), menu(), sc).id, "save")        # not started: the text


class GameTests(unittest.TestCase):
    def test_options_do_what_the_typed_commands_do(self):
        s = Session("templates/starter", record_audio=True).start()
        g = s.game
        m = M.options(g)
        self.assertEqual([t.label for t in m.tabs()], ["Sound", "Screen"])
        self.assertEqual([r.id for r in m.rows()], ["music", "music_volume", "effects", "effects_volume", "sound_test"])
        keys(m, "enter")
        self.assertFalse(g.audio.music_on)
        keys(m, "enter", "down", "left", "left")
        self.assertTrue(g.audio.music_on)
        self.assertAlmostEqual(g.audio.music_volume, 0.4)
        keys(m, "down", "enter", "down", "right")
        self.assertFalse(g.audio.sfx_on)
        self.assertAlmostEqual(g.audio.sfx_volume, 0.9)
        keys(m, "end", "enter")
        self.assertFalse(m.done)                                             # the test stays in the menu
        self.assertTrue(m.said)
        keys(m, "tab")
        self.assertEqual([r.id for r in m.rows()], ["style", "speed", "art", "frame", "menus"])
        before = g.ui.theme.name
        keys(m, "right")
        self.assertNotEqual(g.ui.theme.name, before)
        keys(m, "left", "down", "left", "down", "enter", "down", "right", "right")
        self.assertEqual((g.ui.theme.name, g.term.speed, g.settings["art"], g.ui.menu_border), (before, 0.4, False, "rounded"))
        self.assertEqual(M.frame_of(g.ui), "rounded")
        keys(m, "left", "left")
        self.assertIsNone(g.ui.menu_border)                                  # the style's own again
        keys(m, "down", "right")
        self.assertEqual(g.ui.menus, "bar")
        keys(m, "left")
        self.assertEqual(g.ui.menus, "")
        resumed = []
        m = M.options(g, lambda: resumed.append(1))
        keys(m, "enter", "enter")
        self.assertEqual(resumed, [1])

    def test_the_options_and_the_game_menu_at_a_prompt(self):
        s = Session("templates/starter").start()
        g = s.game
        text = s.do("options", "1", "3", "0", "2", "3", "0", "0")
        self.assertFalse(g.audio.sfx_on)
        self.assertFalse(g.settings["art"])
        for part in ("Options", "1. Sound", "2. Screen", "3. Effects: on", "3. Effects: off", "3. Pictures: on",
                     "4. Menu frame: the style's"):
            self.assertIn(part, text)
        turn = g.world.turn
        text = s.do("menu", "6")
        self.assertIn("Made with CLIo", text)                                # about
        for part in ("1. Resume", "2. Options (sound, screen)", "3. Save", "4. Load", "5. Help", "6. About", "7. Leave the game"):
            self.assertIn(part, text)
        s.do("settings", "0")
        s.do("pause", "1")
        self.assertEqual(g.world.turn, turn)                                 # none of it takes a turn
        s.do("menu", "3")
        self.assertIn("Game saved", s.text)
        s.do("menu", "7", "1", "0")                                          # leave? no
        self.assertIsNone(g.over)
        text = s.do("menu", "7", "2")
        self.assertEqual(g.over, "quit")
        self.assertIn("Leave the game? Unsaved progress will be lost.", text)
        self.assertIn("Goodbye", text)

    def test_how_a_game_asks_for_its_menus(self):
        self.assertIsNone(Session("templates/starter").game.ui.menus)
        from engine.game import Game
        t = term()
        self.assertEqual(Game(STARTER, term=t, audio=Session("templates/starter").audio, settings={"menus": "bar"}).ui.menus, "bar")
        self.assertEqual(Game(STARTER, term=term(), audio=Session("templates/starter").audio,
                              settings={"menus": "bar", "lines": True}).ui.menus, "lines")
        self.assertIsNone(Game(STARTER, term=term(), audio=Session("templates/starter").audio,
                               settings={"menus": "nonsense"}).ui.menus)


class DataTests(unittest.TestCase):
    CAMP = {"camp": {"title": "Camp", "items": [
        {"id": "rest", "label": "Rest", "effects": [{"heal": "full"}, {"say": "You sleep."}, {"set": "rested"}]},
        {"id": "cook", "label": "Cook", "when": "has_pot", "effects": [{"say": "Stew."}], "again": True},
        {"id": "watch", "label": "Keep watch", "locked": "!rested", "why": "You are too tired.", "effects": [{"var": ["watches", "+=", 1]}]},
        {"label": "Orders", "items": [
            {"id": "pace", "kind": "cycle", "label": "Pace", "var": "pace", "choices": ["slow", "fast"]},
            {"id": "guard", "kind": "check", "label": "Post a guard", "flag": "guarded"},
            {"id": "ration", "kind": "slide", "label": "Rations", "var": "ration", "low": 1, "high": 3}]}]}}

    def game(self, menus=None, scenes=None):
        folder = os.path.join(tempfile.mkdtemp(prefix="clio-menu-test-"), "starter")
        shutil.copytree(STARTER, folder)
        self.addCleanup(shutil.rmtree, os.path.dirname(folder), True)
        with open(os.path.join(folder, "menus.json"), "w", encoding="utf-8") as f:
            json.dump(menus if menus is not None else self.CAMP, f)
        return folder

    def test_a_games_own_menu(self):
        s = Session(self.game()).start()
        g = s.game
        self.assertIsNone(M.from_data(g, "nowhere"))
        m = M.from_data(g, "camp")
        self.assertEqual([r.id for r in m.rows()], ["rest", "watch", "orders"])     # no pot: no cooking
        self.assertEqual(m.why_not(m.find("watch")), "You are too tired.")
        g.world.flags["has_pot"] = True
        g.world.vars["pace"] = "fast"
        m = M.from_data(g, "camp")
        self.assertEqual(([r.id for r in m.rows()], m.find("pace").value, m.find("guard").value, m.find("ration").value),
                         (["rest", "cook", "watch", "orders"], "fast", False, 1))
        s.queue.extend(["4", "1", "2", "3", "3", "0", "1"])                    # orders: pace, a guard, rations 3; rest
        got = M.play(g, "camp")
        self.assertEqual(got.id, "rest")
        self.assertEqual((g.world.vars["pace"], g.world.flags.get("guarded"), g.world.vars["ration"]), ("slow", True, 3))
        self.assertTrue(g.world.flags.get("rested"))
        self.assertIn("You sleep.", s.text)
        s.queue.extend(["2", "0"])                                           # guard off again
        m = M.from_data(g, "camp")
        self.assertTrue(m.find("guard").value)
        s.queue[:] = ["4", "2", "0", "0"]
        self.assertIsNone(M.play(g, "camp"))
        self.assertNotIn("guarded", g.world.flags)
        s.queue[:] = ["2", "2", "3"]                                         # cook, and the menu is back; cook; watch
        got = M.play(g, "camp")
        self.assertEqual((got.id, s.text.count("Stew."), g.world.vars["watches"]), ("watch", 2, 1))

    def test_the_effect_opens_it_and_a_missing_one_says_so(self):
        s = Session(self.game()).start()
        from engine import conditions
        s.queue[:] = ["1"]
        conditions.run([{"menu": "camp"}], s.game)
        self.assertIn("You sleep.", s.text)
        conditions.run([{"menu": "larder"}], s.game)
        self.assertIn("There is no menu called 'larder'.", s.text)

    def test_what_is_wrong_in_menus_json_is_said(self):
        from engine.data import GameData
        self.assertEqual(GameData(self.game()).validate(), [])
        bad = {"camp": {"look": "wheel", "items": [
            {"label": "A"}, {"label": "A"}, {"kind": "dial", "label": "B"}, {"kind": "cycle", "label": "C", "var": "c"},
            {"kind": "slide", "label": "D", "low": 5, "high": 5, "var": "d"}, {"kind": "check", "label": "E"},
            {"kind": "do"}, 7, {"label": "F", "items": []}, {"label": "G", "look": "ring"}]},
            "empty": {}, "list": []}
        text = "\n".join(GameData(self.game(bad)).validate())
        for part in ("menu 'camp': unknown look 'wheel' (lines, bar, tabs, find, line, terminal, cards)",
                     "menu 'camp' item 2: the id 'a' is used twice in this menu",
                     "menu 'camp' item 3: unknown kind 'dial'", "menu 'camp' item 4: a cycle needs \"choices\"",
                     "menu 'camp' item 5: a slide needs \"low\" under \"high\"",
                     "menu 'camp' item 6: a value needs a \"var\" (or a \"flag\") to be kept in",
                     "menu 'camp' item 7: it needs a \"label\"", "menu 'camp' item 8: it should be a map",
                     "menu 'camp' item 9: it needs a list of \"items\"", "menu 'camp' item 10: unknown look 'ring'",
                     "menu 'empty': it needs a list of \"items\"", "menu 'list': it should be a map"):
            self.assertIn(part, text)

        class Odd:
            menus = []
        self.assertEqual(M.problems(Odd()), ["menus.json should be a map of menus by name"])
        folder = self.game({})                                               # no menus of its own: game.json is still read
        with open(os.path.join(folder, "game.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.update(menu_look="wheel", menu_border="double shadow")
        with open(os.path.join(folder, "game.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        self.assertEqual(GameData(folder).validate(), ["game.json: unknown menu_look 'wheel' (bar, line, terminal, cards)"])


class LevelTests(unittest.TestCase):
    def test_esc_is_the_menu_in_a_level(self):
        from engine import level as L
        self.assertEqual(L.KEYMAP["esc"], "menu")
        self.assertIn("Esc  the menu", "\n".join(t for t, _r in L.HELP))

    def test_the_menu_over_a_levels_picture(self):
        from engine import level as L
        from test_level_saves import Host, ROOTLESS, Silent
        from engine.game import Game
        g = Game(ROOTLESS, term=term(lambda p: "q", color=3), audio=Silent())
        lv = L.Level(g.data, "e1m1", seed=g.seed)
        lone = L.Level(g.data, "e1m1", seed=g.seed)
        said = []
        lone.say = lambda text, role="text": said.append(text)
        self.assertIsNone(lone.menu())
        self.assertEqual(said, ["The menu needs the game round the level."])
        lv.host = Host(g)
        con = L.FrameConsole(g.term, keys=False, animate=False)
        con.screen.keys = ScriptedKeys(["down", "enter", "tab", "esc", "end", "enter", "down", "enter"])
        con.screen.out = io.StringIO()
        con.screen.size = lambda: (80, 24)
        con.screen.started = True
        con.size = (80, 24)
        lv.console = con
        self.assertEqual(lv.menu(), "quit")                                  # options, its pages, back; leave, yes
        self.assertEqual(lv.over, "quit")
        text = strip_ansi(con.screen.out.getvalue())
        for part in ("Resume", "Options", "sound, screen", "Music volume", "Style", "Leave the game", "Enter choose"):
            self.assertIn(part, text)
        lv.over = None
        con.screen.keys = ScriptedKeys(["esc"])
        self.assertIsNone(lv.menu("options"))
        pages = []
        con.page = lambda lv_, lines, **kw: pages.append(lines)
        con.screen.keys = ScriptedKeys(["h"])
        self.assertEqual((lv.menu(), len(pages)), ("help", 1))


class RealmTests(unittest.TestCase):
    def test_a_realm_has_the_menu_at_its_prompt(self):
        s = Session("templates/realm", ["menu", "2", "1", "1", "0", "0", "0", "options", "0", "menu", "5", "e",
                                        "menu", "6", "2"])
        text = s.run()
        self.assertFalse(s.game.audio.music_on)
        for part in ("1. Resume", "2. Options (sound, screen)", "1. Music: on", "1. Music: off", "6. Leave the game",
                     "end the season", "Year 1, High Sun", "Leave the game? Unsaved progress will be lost."):
            self.assertIn(part, text)
        self.assertEqual(s.game.over, "quit")


if __name__ == "__main__":
    unittest.main()
