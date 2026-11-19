# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Frame mode and keys: escape sequences, the redrawn screen's line, far versions of sprites."""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from engine import keys as keys_mod  # noqa: E402
from engine import sprite  # noqa: E402
from engine.frame import Screen  # noqa: E402
from engine.term import Term  # noqa: E402


class KeyTests(unittest.TestCase):
    def test_sequences(self):
        d = keys_mod.decode
        self.assertEqual(d("[A"), "up")
        self.assertEqual(d("OD"), "left")
        self.assertEqual(d("[1;5D"), "ctrl-left")
        self.assertEqual(d("[1;3C"), "alt-right")
        self.assertEqual(d("[1;2A"), "shift-up")
        self.assertEqual(d("[2~"), "insert")
        self.assertEqual(d("Os"), "3")                       # keypad in application mode
        self.assertEqual(d("x"), "alt-x")
        self.assertEqual(d(""), "esc")
        self.assertEqual(d("[99Q"), "esc")

    def test_windows_codes(self):
        self.assertEqual(keys_mod.WIN["s"], "ctrl-left")
        self.assertEqual(keys_mod.WIN["H"], "up")


class ScreenTests(unittest.TestCase):
    def screen(self, presses, keymap=None):
        term = Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False, env={})
        sc = Screen(term, keys_mod.ScriptedKeys(presses), keymap or {"up": "k", "space": "f", "1": "1"},
                    animate=False, out=io.StringIO())
        sc.last_size = sc.size()
        return sc

    def test_a_key_acts_only_while_nothing_is_typed(self):
        sc = self.screen(["up"])
        self.assertEqual(sc.read(lambda: None), "k")
        sc = self.screen(["f", "space", "z", "1", "enter"])
        self.assertEqual(sc.read(lambda: None), "f z1")

    def test_line_editing(self):
        sc = self.screen(["x", "y", "backspace", "esc", "w", "enter"])
        self.assertEqual(sc.read(lambda: None), "w")

    def test_typeahead_keeps_text_and_one_action_key(self):
        sc = self.screen([])
        sc.typeahead(["up", "up", "up"])
        self.assertEqual((sc.pending, sc.typed), ("up", ""))
        sc.typeahead([";", "space", "f"])
        self.assertEqual((sc.pending, sc.typed), (None, "; f"))

    def test_only_what_changed_is_written(self):
        sc = self.screen([])
        red, blue = (200, 0, 0), (0, 0, 200)
        row = [(None, red, blue)] * 30
        sc.frame([row, "a line"], prompt=None, status="")
        whole = sc.out.getvalue()
        self.assertIn("▀", whole)
        sc.out.seek(0)
        sc.out.truncate()
        sc.frame([list(row), "a line"], prompt=None, status="")
        self.assertNotIn("▀", sc.out.getvalue())                 # the same: not written again
        self.assertNotIn("a line", sc.out.getvalue())
        sc.out.seek(0)
        sc.out.truncate()
        changed = list(row)
        changed[7] = changed[9] = (None, blue, red)
        sc.frame([changed, "a line"], prompt=None, status="")
        out = sc.out.getvalue()
        self.assertIn("\x1b[1;8H", out)                         # from its first changed cell...
        self.assertEqual(out.count("▀"), 3)                     # ...to its last
        sc.out.seek(0)
        sc.out.truncate()
        sc.frame([changed, "a line"], prompt=None, status="", whole=True)
        self.assertEqual(sc.out.getvalue().count("▀"), 30)       # whole: all of it

    def test_colours_are_set_as_they_change(self):
        from engine.frame import Painter
        p = Painter(3)
        red, blue = (200, 0, 0), (0, 0, 200)
        out = p.cells([("a", red, blue), ("b", red, blue), ("c", blue, blue), (" ", None, red), ("d", None, red)])
        self.assertEqual(out, "\x1b[0;38;2;200;0;0;48;2;0;0;200mab\x1b[38;2;0;0;200mc"
                              "\x1b[48;2;200;0;0m \x1b[39md")    # a blank keeps the foreground it has
        plain = Painter(0).cells([("a", red, blue), (None, red, blue)])
        self.assertEqual((plain[0], len(plain), "\x1b" in plain), ("a", 2, False))   # no colours: a shade of ink

    def test_an_animation_keeps_its_time(self):
        import time
        sc = self.screen([])
        sc.animate, drawn = True, []

        def slow(fx):
            drawn.append(fx)
            time.sleep(0.03)
        sc.play(range(8), slow, 0.01)                           # each frame takes three turns to draw
        self.assertEqual(drawn[0], 0)
        self.assertEqual(drawn[-1], 7)                           # the last is never left out
        self.assertLess(len(drawn), 8)
        drawn[:] = []
        sc.play(range(5), drawn.append, 0.01)
        self.assertEqual(drawn, [0, 1, 2, 3, 4])                 # in time: every frame


class SpriteTests(unittest.TestCase):
    def test_far_versions_keep_the_eyes(self):
        pixels = [".bbbb.", "bebbeb", "bbbbbb", "bbmmbb", ".bbbb.", ".b..b."]
        small = sprite.shrink(pixels, 2)
        self.assertEqual(len(small), 3)
        self.assertIn("e", "".join(small))
        self.assertEqual(sprite.shrink(["....", "....", "b...", "...."], 2), ["..", ".."])

    def test_monsters_from_every_body_plan(self):
        for body in sprite.BODIES:
            a = sprite.monster("seed", body, 18)
            self.assertEqual(a, sprite.monster("seed", body, 18), body)
            rows = a["pixels"]
            self.assertTrue(rows and all(len(r) == len(rows[0]) for r in rows), body)
            used = set("".join(rows)) - {"."}
            self.assertTrue(used <= set(a["palette"]), body)
            self.assertTrue(a["lod"] and all(len(l["pixels"]) < len(rows) for l in a["lod"]), body)
        self.assertNotEqual(sprite.monster("a", "beast")["pixels"], sprite.monster("b", "beast")["pixels"])


if __name__ == "__main__":
    unittest.main()
