# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""What a font can draw: every symbol the engine and its games show has a stand-in in the Windows
console's fonts (WGL4), in Windows Terminal's font, and in plain ASCII - no '?' or empty boxes."""
import ast
import io
import os
import sys
import unicodedata
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import term as term_mod  # noqa: E402
from engine.frame import Screen  # noqa: E402
from engine.term import CONSOLE_FONT, FONT_GAPS, TERMINAL_FONT, WGL4, Term, to_ascii  # noqa: E402


def shown_characters():
    """Every character outside ASCII the engine's code and the games' files can show: in the code's
    strings, in the games' JSON, and the braille the dots are made of."""
    found = {}

    def take(text, where):
        for ch in text:
            c = ord(ch)
            if c < 0xA0 or ch == "﻿" or 0xE000 <= c <= 0xF8FF:     # keys' escape codes, a BOM, private keys
                continue
            found.setdefault(ch, where)

    for base in ("engine", "clio.py"):
        paths = [os.path.join(ROOT, base)] if base.endswith(".py") else [
            os.path.join(d, f) for d, _, fs in os.walk(os.path.join(ROOT, base)) for f in fs
            if f.endswith(".py") and "web" not in d and "ballistic" not in d]
        for p in paths:
            with open(p, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            lists = set()                                   # the lists of what fonts have: not shown
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(getattr(t, "id", "") in ("WGL4", "TERMINAL_FONT")
                                                        for t in node.targets):
                    lists.update(id(n) for n in ast.walk(node))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in lists:
                    take(node.value, os.path.relpath(p, ROOT))
    for d, _, fs in os.walk(os.path.join(ROOT, "games")):
        for f in fs:
            if f.endswith(".json"):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    take(fh.read(), os.path.relpath(os.path.join(d, f), ROOT))
    take("".join(chr(0x2800 + i) for i in range(256)), "the dots")
    return found


def term(env=None, windows=False, glyphs=None):
    with mock.patch.object(term_mod, "_WINDOWS", windows):
        return Term(out=io.StringIO(), width=100, height=30, color=3, unicode=True, animate=False,
                    env=env or {}, glyphs=glyphs)


class Coverage(unittest.TestCase):
    def test_every_shown_character_has_a_stand_in(self):
        missing = {"console": [], "Windows Terminal": [], "ASCII": []}
        for ch, where in sorted(shown_characters().items()):
            if not all(ord(c) in WGL4 for c in ch.translate(CONSOLE_FONT)):
                missing["console"].append("%s (%s, %s)" % (ch, unicodedata.name(ch, "?"), where))
            if not all(ord(c) in TERMINAL_FONT for c in ch.translate(FONT_GAPS)):
                missing["Windows Terminal"].append("%s (%s, %s)" % (ch, unicodedata.name(ch, "?"), where))
            if "?" in to_ascii(ch):
                missing["ASCII"].append("%s (%s, %s)" % (ch, unicodedata.name(ch, "?"), where))
        for font, chars in missing.items():
            self.assertEqual(chars, [], "no stand-in for %s: add one to engine/term.py" % font)

    def test_stand_ins_are_in_their_fonts(self):
        self.assertTrue(all(ord(c) in WGL4 for v in CONSOLE_FONT.values() for c in v))
        self.assertTrue(all(ord(c) in TERMINAL_FONT for v in FONT_GAPS.values() for c in v))
        self.assertFalse(any(k in WGL4 for k in CONSOLE_FONT))          # only what the font lacks is swapped


class WhichFont(unittest.TestCase):
    def test_the_windows_console_gets_its_fonts(self):
        t = term(windows=True)
        self.assertEqual((t.glyph_mode, t.font), ("console", "console"))
        t.write("▁▂▃ ↗ ★ ✔ ╭─╮ " + chr(0x28FF) + "\n")
        self.assertEqual(t.out.getvalue(), "__▄ / * √ ┌─┐ █\n")

    def test_windows_terminal_and_others_keep_the_full_set(self):
        for env in ({"WT_SESSION": "1"}, {"TERM_PROGRAM": "vscode"}, {"TERM": "xterm-256color"}):
            t = term(env, windows=True)
            self.assertEqual((t.glyph_mode, t.font), ("full", "windows"), env)
            t.write("▁▂▃ ↗ ★ ✔\n")
            self.assertEqual(t.out.getvalue(), "▁▂▃ ◥ * ✓\n")
        t = term({"TERM": "xterm-256color"})
        self.assertEqual((t.glyph_mode, t.font, t.subst), ("full", "full", None))
        self.assertEqual(term({"TERM": "linux"}).glyph_mode, "console")       # the Linux console's font, as small

    def test_chosen_by_hand(self):
        self.assertEqual(term(windows=True, glyphs="full").font, "windows")
        self.assertEqual(term({"CLIO_GLYPHS": "console"}).font, "console")
        self.assertEqual(term(windows=True, glyphs="safe").glyph_mode, "safe")


class OnScreen(unittest.TestCase):
    """Real pictures through the screen: only what the font has reaches the terminal."""

    def screen(self, t):
        sc = Screen(t, None, {}, animate=False, out=io.StringIO())
        sc.size = lambda: (100, 30)
        return sc

    def drawn(self, sc):
        return {c for c in sc.out.getvalue() if ord(c) > 0x7F}

    def run_sim(self, sid, sc):
        from engine import sim as S
        from engine.data import GameData
        from engine.realtime import Controls
        sim = S.make(GameData(os.path.join(ROOT, "games", "rootless")), sid)
        runner = S.Runner(sim, sc)
        sim.step(Controls(0, frozenset(["enter"]), ("enter",), ()))
        held, plan = set(), set()
        for t in range(1, 900):
            if sim.result:
                break
            if sim.mode == "systems":
                if t % 40 == 1:
                    plan = S.best_controls(sim, 2.0)
                keys = set(plan)
            else:
                keys = S.autopilot_keys(sim)
            sim.step(Controls(t, frozenset(keys), tuple(sorted(keys - held)), tuple(sorted(held - keys))))
            held = keys
            if t % 15 == 0:
                runner.draw()

    def test_the_hopper_and_the_reactor(self):
        for sid in ("sim8", "sim9"):                       # the hopper turns; the reactor draws its chart
            sc = self.screen(term(windows=True))
            self.run_sim(sid, sc)
            bad = {c for c in self.drawn(sc) if ord(c) not in WGL4}
            self.assertEqual(bad, set(), sid)
            sc = self.screen(term({"WT_SESSION": "1"}, windows=True))
            self.run_sim(sid, sc)
            bad = {c for c in self.drawn(sc) if ord(c) not in TERMINAL_FONT}
            self.assertEqual(bad, set(), sid)
        sc = self.screen(term({"WT_SESSION": "1"}, windows=True))
        self.assertEqual(sc.glyphs["heading"], "▲◥►◢▼◣◄◤")         # eight it has: no NW-SE muddle

    def test_the_display_test(self):
        import clio
        for t, font in ((term(windows=True), WGL4), (term({"WT_SESSION": "1"}, windows=True), TERMINAL_FONT)):
            clio.display_test(t)
            text = t.out.getvalue()
            self.assertIn("Fine shapes", text)
            self.assertEqual({c for c in text if ord(c) > 0x7F and ord(c) not in font}, set())

    def test_dots_in_the_console(self):
        sys.path.insert(0, HERE)
        from test_levels import level, put
        from engine.firstperson import FX, View
        lv = level()
        put(lv, 15, 22, 0)
        rows = View(80, 17, "dots").render(lv, FX(), 0)
        sc = self.screen(term(windows=True))
        sc.frame(rows)
        self.assertEqual({c for c in self.drawn(sc) if ord(c) not in WGL4}, set())
        self.assertTrue(self.drawn(sc) & set("·░▒▓█"))             # the dots, as shades


if __name__ == "__main__":
    unittest.main()
