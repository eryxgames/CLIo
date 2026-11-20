# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Cards, more: upgraded cards and the effect that makes them, a shop's card counter (buy, make better,
take out), and card duels started in a first-person level - at a terminal or with a challenger - kept in
the level's journal so a load plays them back without fighting again."""
import io
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import cards, conditions, levelbot  # noqa: E402
from engine.game import Game  # noqa: E402
from engine.level import Host, Level, TextConsole  # noqa: E402
from engine.term import Term, strip_ansi  # noqa: E402
from test_cards import hollow, said  # noqa: E402
from test_level_saves import Silent  # noqa: E402

ROOTLESS = os.path.join(ROOT, "games", "rootless")


def rootless():
    out = io.StringIO()
    term = Term(out=out, inp=lambda p: "q", width=80, height=24, color=0, unicode=True, animate=False, env={})
    return Game(ROOTLESS, term=term, audio=Silent(), settings={"dev": True}), out


class UpgradeTests(unittest.TestCase):
    def test_a_card_made_better(self):
        t = cards.table(None)
        self.assertEqual((t["strike+"]["name"], t["strike+"]["effects"]), ("Strike+", [{"damage": 9}]))
        self.assertIn("strike+", t)
        self.assertNotIn("strike++", t)
        self.assertNotIn("strike+", list(t))                  # not one of the cards to be offered
        self.assertEqual(t.get("nothing+"), None)
        g, _ = rootless()
        rt = cards.table(g.data)
        self.assertEqual((rt["kill9+"]["cost"], rt["kill9+"]["effects"]), (1, [{"damage": 15}]))   # its own
        self.assertEqual(rt["grep+"]["effects"], [{"draw": 3}])
        self.assertEqual(rt["traceroute+"]["effects"][0]["turns"], 3)
        no = cards.upgraded({"name": "Nap", "cost": 2, "effects": [{"exhaust": True}]})
        self.assertEqual(no["cost"], 1)                       # nothing to add to: cheaper
        rt["ping"]["upgrade"] = False
        self.assertNotIn("ping+", rt)

    def test_the_effect_makes_a_card_in_the_deck_better(self):
        s, g = hollow()
        deck = cards.deck_of(g)
        n = len(deck)
        conditions.run([{"upgrade_card": "random"}], g)
        self.assertEqual(sum(c.endswith("+") for c in deck), 1)
        s.queue[:] = ["1"]
        conditions.run([{"upgrade_card": "choose"}], g)
        self.assertEqual(sum(c.endswith("+") for c in deck), 2)
        first = next(c for c in deck if not c.endswith("+"))
        conditions.run([{"upgrade_card": first}], g)
        self.assertIn(first + "+", deck)
        self.assertEqual(len(deck), n)
        self.assertIn("goes", said(s) + "goes")

    def test_an_upgraded_card_plays_better(self):
        s, g = hollow()
        deck = cards.deck_of(g)
        deck[:] = ["strike+"] * len(deck)
        b = cards.CardBattle(g, ["bone_rat"])
        b.draw(5)
        b.energy = 3
        e = b.enemies[0]
        hp = e.hp
        b.play(0, e)
        self.assertEqual(hp - e.hp, max(0, cards.hit(b.player.strength, {}, {}, 9) - e.block))


class ShopTests(unittest.TestCase):
    def test_the_merchant_sells_cards_makes_them_better_and_takes_them_out(self):
        s, g = hollow()
        g.world.player["gold"] = 500
        shop = g.world.characters["merchant"]["shop"]
        deck = cards.deck_of(g)
        n = len(deck)
        g.chars_here = lambda: ["merchant"]
        s.queue[:] = ["3", "1", "1", "2", "1", "3", str(n + 1), "0", "0"]   # buy, make better, take the new one out
        g.open_shop("merchant")
        text = said(s)
        self.assertIn("Cards", text)
        self.assertEqual(len(deck), n)                        # one in, one out
        self.assertNotIn("backstab", shop["cards"])           # sold
        self.assertNotIn("backstab", deck)
        self.assertIn("Backstab", text)
        self.assertEqual(sum(c.endswith("+") for c in deck), 1)
        self.assertEqual(g.world.player["gold"], 500 - cards.price(cards.table(g.data)["backstab"]) - 60 - 50)
        g.world.player["gold"] = 10
        s.queue[:] = ["1", "1", "0", "0"]
        cards.shop_cards(g, shop)
        self.assertIn("You can't afford that.", said(s))
        self.assertEqual(cards.price({"rarity": "rare"}), 110)
        self.assertEqual(cards.price({"price": 33}, 2.0), 66)

    def test_a_shop_without_cards_or_a_game_without_a_deck_shows_no_counter(self):
        s, g = hollow()
        g.world.characters["merchant"]["shop"] = {"sells": ["antidote"]}
        g.chars_here = lambda: ["merchant"]
        s.queue[:] = ["0"]
        g.open_shop("merchant")
        self.assertNotIn("Cards", said(s))

    def test_problems(self):
        class D:
            cards = {"a": {"name": "A", "cost": 1, "effects": [{"damage": 1}], "upgrade": 3},
                     "b": {"name": "B", "cost": 1, "effects": [{"damage": 1}], "upgrade": {"cost": 12}}}
            characters = {"m": {"shop": {"cards": ["zz"], "upgrade": "cheap"}}}
            config = {}
        text = "\n".join(cards.problems(D()))
        for bit in ("card 'a': upgrade should be an object", "card 'b': its upgrade's cost",
                    "its shop sells card 'zz'", "its shop's upgrade price"):
            self.assertIn(bit, text)


class DuelTests(unittest.TestCase):
    def test_a_terminal_is_hacked_by_a_card_duel_and_the_journal_keeps_how_it_went(self):
        g, out = rootless()
        res, lv = levelbot.play(g.data, "sim10", seed=1, host=Host(g, auto_duels=True))
        self.assertEqual(res, "exit")
        duels = [line for _, line in lv.journal if " =" in line]
        self.assertEqual(len(duels), 1)
        self.assertRegex(duels[0], r"^use =won:\d+$")
        self.assertIn("Black ICE", strip_ansi(out.getvalue()))
        again = Level(g.data, "sim10", seed=1)
        again.host = Host(g)
        with mock.patch.object(cards, "fight_duel", side_effect=AssertionError("fought again")):
            again.replay([j for j in lv.journal[:-1]])         # all but the exit
        self.assertTrue(again.cell(3, 4).pressed)              # the terminal is open, as it was

    def lines(self, lv, lines):
        for line in lines:
            lv.run_line(line)

    def level(self, g, result):
        lv = Level(g.data, "sim10", seed=1)
        lv.console = TextConsole(lambda t: None, lambda p: None)
        lv.host = Host(g)
        return lv, mock.patch.object(cards, "fight_duel", return_value=result)

    def test_a_lost_duel_hurts_and_leaves_the_terminal_shut(self):
        g, _ = rootless()
        lv, patch = self.level(g, ("lose", 0))
        with patch:
            self.lines(lv, ["forward", "forward", "turn left", "forward", "forward", "turn right", "use"])
        t = lv.cell(3, 4)
        self.assertFalse(t.pressed)
        self.assertEqual(lv.player.hp, 80)                     # feedback: 20
        self.assertTrue(lv.journal[-1][1].endswith(" =lost"))
        lv, patch = self.level(g, ("fled", 100))
        with patch:
            self.lines(lv, ["forward", "forward", "turn left", "forward", "forward", "turn right", "use"])
        self.assertEqual((lv.player.hp, lv.cell(3, 4).pressed), (100, False))

    def test_a_challenger_is_beaten_at_cards_and_a_won_duel_leaves_its_hurts(self):
        g, _ = rootless()
        lv, patch = self.level(g, ("win", 70))
        s = next(m for m in lv.monsters if m.kind == "sentinel")
        p = lv.player
        p.x, p.y = s.x, s.y - 1                                # just north of it, facing it
        from engine.level import DIRS
        p.facing = DIRS.index((0, 1))
        self.assertEqual(lv.ahead(), (s.x, s.y))
        with patch:
            lv.run_line("use")
        self.assertTrue(s.dead)
        self.assertEqual(p.hp, 70)
        before = lv.beat
        lv.end_beat()
        self.assertGreater(lv.beat, before)

    def test_no_game_no_duel(self):
        g, _ = rootless()
        lv = Level(g.data, "sim10", seed=1)
        said = []
        lv.console = TextConsole(lambda t, *a: said.append(t), lambda p: None)
        for line in ["forward", "forward", "turn left", "forward", "forward", "turn right", "use"]:
            lv.run_line(line)
        self.assertFalse(lv.cell(3, 4).pressed)
        self.assertEqual(lv.journal[-1][1], "use")

    def test_duel_problems(self):
        from engine.level import duel_problems

        class D:
            characters = {}
            monsters = {"x": {"duel": "nobody"}}
            levels = {"l": {"legend": {"t": {"duel": "nobody"}}}}
        text = "\n".join(duel_problems(D()))
        self.assertIn("monster 'x': its duel is with 'nobody'", text)
        self.assertIn("legend 't': a duel is on a switch", text)


if __name__ == "__main__":
    unittest.main()
