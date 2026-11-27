# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""The status bar of a text game kept on the top line of the screen (``"hud": "top"``)."""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine.audio import Silent  # noqa: E402
from engine.game import Game  # noqa: E402
from engine.term import ESC, Term, strip_ansi  # noqa: E402

DERELICT = os.path.join(ROOT, "games", "derelict")


class Screen(io.StringIO):
    def isatty(self):
        return True


def screen(rows=30):
    """A terminal that takes escape sequences, as far as its writing goes (what it is asked, it answers Enter)."""
    t = Term(out=Screen(), inp=lambda prompt: "", width=80, height=rows, color=3, unicode=True, animate=False, env={})
    t.is_tty = t.ansi = True
    return t


class Pinned(unittest.TestCase):
    def test_a_line_is_kept_at_the_top(self):
        t = screen()
        self.assertTrue(t.pin("HEALTH 60"))
        out = t.out.getvalue()
        self.assertEqual(out, "\n" + ESC + "7" + ESC + "[2;30r" + ESC + "8" +          # the rest scrolls, from row 2
                         ESC + "7" + ESC + "[1;1H" + ESC + "[2K" + "HEALTH 60" + ESC + "[0m" + ESC + "8")
        self.assertEqual(t.pinned, 30)
        t.out.truncate(0), t.out.seek(0)
        self.assertTrue(t.pin("HEALTH 50"))                     # again: only the line is written
        self.assertNotIn("r" + ESC + "8", t.out.getvalue())
        self.assertNotIn("\n", t.out.getvalue())
        self.assertIn("HEALTH 50", t.out.getvalue())

    def test_the_window_changes_its_height(self):
        t = screen()
        t.pin("A")
        t.forced_height = 40
        t.out.truncate(0), t.out.seek(0)
        t.pin("A")
        self.assertIn(ESC + "[2;40r", t.out.getvalue())
        self.assertFalse(t.out.getvalue().startswith("\n"))

    def test_too_long_a_line_is_cut(self):
        t = screen()
        t.pin("x" * 200)
        self.assertNotIn("x" * 81, t.out.getvalue())

    def test_what_takes_the_screen_lets_it_go(self):
        for taker in (lambda t: t.clear_screen(), lambda t: t.write(ESC + "[H"), lambda t: t.write(ESC + "[?1049h"),
                      lambda t: t.unpin()):
            t = screen()
            t.pin("A")
            t.out.truncate(0), t.out.seek(0)
            taker(t)
            self.assertTrue(t.out.getvalue().startswith(ESC + "7" + ESC + "[r" + ESC + "8"))
            self.assertEqual(t.pinned, 0)
        t = screen()
        t.unpin()                                               # (nothing pinned: nothing written)
        t.line("words")
        self.assertEqual(t.out.getvalue(), "words\n")

    def test_where_it_cannot_be_kept(self):
        plain = Term(out=io.StringIO(), width=80, height=30, color=0, unicode=True, animate=False, env={})
        self.assertFalse(plain.pin("A"))                        # not a terminal
        self.assertEqual(plain.out.getvalue(), "")
        dumb = screen()
        dumb.ansi = False
        self.assertFalse(dumb.pin("A"))                         # one that takes no escape sequences
        small = screen(rows=9)
        self.assertFalse(small.pin("A"))                        # too few rows to give one away


class InAGame(unittest.TestCase):
    def game(self, term, **settings):
        g = Game(DERELICT, term=term, audio=Silent(), settings=dict(settings, force_hud=True))
        g.start()
        term.out.truncate(0), term.out.seek(0)
        return g

    def test_the_bar_goes_to_the_top_and_is_not_printed(self):
        t = screen()
        g = self.game(t, hud="top")
        g.show_hud()
        out = t.out.getvalue()
        self.assertIn(ESC + "[1;1H" + ESC + "[2K", out)
        bar = strip_ansi(out.split(ESC + "[2K")[1].split(ESC + "8")[0])
        self.assertIn("turn 0", bar)
        self.assertNotIn("turn 0", strip_ansi(out.split(ESC + "8")[-1]))        # ...and nowhere below
        g.term.unpin()

    def test_printed_as_ever_without_the_setting_or_without_a_terminal(self):
        t = screen()
        g = self.game(t)
        g.show_hud()
        self.assertNotIn(ESC + "[1;1H", t.out.getvalue())
        self.assertIn("turn 0", strip_ansi(t.out.getvalue()))
        plain = Term(out=io.StringIO(), inp=lambda p: "", width=80, height=30, color=0, unicode=True, animate=False, env={})
        g = self.game(plain, hud="top")
        g.show_hud()
        self.assertEqual(strip_ansi(plain.out.getvalue()).count("turn 0"), 1)
        self.assertNotIn(ESC, plain.out.getvalue())

    def test_the_games_that_have_it(self):
        from engine.data import GameData
        for name, has in (("erebus", "top"), ("depths", "top"), ("derelict", None)):
            self.assertEqual((GameData(os.path.join(ROOT, "games", name)).config.get("settings") or {}).get("hud"), has)

    def test_the_screen_is_given_back_when_the_game_ends(self):
        t = screen()
        g = Game(DERELICT, term=t, audio=Silent(), settings={"hud": "top"})
        t.pin("A")
        g.play = lambda: None
        g.run()
        self.assertEqual(t.pinned, 0)


if __name__ == "__main__":
    unittest.main()
