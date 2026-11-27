# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""IRONLID, the test demo: its files are right, its two levels play as they are meant to - the outpost is cleaned,
its staff kept alive, and he falls to the Spider; the yard is won in lines - and the game goes from one to the
other."""
import io
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import demo, firstperson, levelbot, motion  # noqa: E402
from engine.audio import Silent  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.game import Game  # noqa: E402
from engine.level import KEYMAP, FrameConsole, Level  # noqa: E402
from engine.term import Term, strip_ansi  # noqa: E402
from test_demo import player  # noqa: E402

IRONLID = os.path.join(ROOT, "games", "ironlid")


class Files(unittest.TestCase):
    def test_nothing_is_wrong_with_them(self):
        data = GameData(IRONLID)
        self.assertEqual(data.validate(), [])
        self.assertEqual(sorted(data.levels), ["outpost", "relocation", "ship"])

    def test_everybody_is_moved_by_clio_motion(self):
        data = GameData(IRONLID)
        for mid, m in data.monsters.items():
            self.assertIn(m["model"], data.models, mid)
            self.assertIn("motion", data.models[m["model"]], mid)
        kinds = {motion.spec_of(spec)["character"] for spec in data.models.values()}
        self.assertEqual(kinds, {"soldier", "gunner", "hyena", "raptor", "mantis", "wasp", "spider", "scientist",
                                 "technician", "hazmat", "woman"})
        civil = [mid for mid, m in data.monsters.items() if m.get("civilian")]
        self.assertEqual(sorted(civil), ["hazmat", "researcher", "scientist", "technician"])
        self.assertTrue(data.monsters["trooper"]["ally"])
        self.assertTrue(data.monsters["spider"]["spares_civilians"])

    def test_every_sound_and_sprite_named_is_there(self):
        data = GameData(IRONLID)
        for mid, m in data.monsters.items():
            for what, name in (m.get("sounds") or {}).items():
                self.assertIn(name, data.sounds, "%s %s" % (mid, what))
        for wid, w in data.weapons.items():
            self.assertIn(w["sound"], data.sounds, wid)
            self.assertIn(w["sprite"], data.sprites, wid)
        for iid, it in data.items.items():
            self.assertIn(it["pickup"]["sprite"], data.sprites, iid)


class TheOutpost(unittest.TestCase):
    def test_cleaned_then_he_falls_to_the_spider(self):
        data = GameData(IRONLID)
        for seed in (0, 1, 2):
            outcome, lv = levelbot.play(data, "outpost", seed)
            self.assertEqual(outcome, "fallen", seed)
            self.assertEqual(lv.stats["kills"], lv.total_kills - 1, seed)        # everybody but the Spider
            self.assertEqual(sorted(lv.events), ["alarm", "second_wave", "spider"], seed)
            alive = lv.total_civil - lv.stats["lost"]
            self.assertEqual(lv.total_civil, 6)
            self.assertGreaterEqual(alive, 2, seed)
            self.assertIsNone(lv.failed)
            spider = next(m for m in lv.monsters if m.kind == "spider")
            self.assertTrue(spider.awake and not spider.dead and spider.grudge is None)
            self.assertEqual(lv.end_lines()[0], ("THANE IS DOWN", "hurt"))
            self.assertTrue(any("civilians" in t and "of 6 alive" in t for t, _r in lv.end_lines()))

    def test_nothing_happens_until_he_leaves_the_barracks(self):
        lv = Level(GameData(IRONLID), "outpost", seed=1)
        for _ in range(12):
            lv.end_beat()
        self.assertEqual((lv.events, lv.stats["lost"]), (set(), 0))
        self.assertFalse(any(m.awake for m in lv.monsters if not m.ours))

    def test_the_helmet_shows_one_colour_and_the_scanner_the_whole_outpost(self):
        lv = Level(GameData(IRONLID), "outpost", seed=1)
        self.assertTrue(firstperson.tinted(lv))
        os.environ["COLUMNS"], os.environ["LINES"] = "120", "38"
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("COLUMNS", "LINES")])
        term = Term(out=io.StringIO(), color=3, unicode=True, animate=False, env={})
        con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False)
        con.layout()
        self.assertEqual(con.view_for(lv).__class__.__name__, "View")
        colours = [c for row in con.snapshot(lv) for cell in row for c in cell[1:] if c]
        self.assertTrue(all(g >= r and g >= b for r, g, b in colours))
        bot = levelbot.Bot(lv, ["scanner"])
        lv.console = bot
        for _ in range(6):
            if lv.player.goggles:
                break
            lv.run_line(bot.read(lv))
        self.assertTrue(lv.player.nightvision)                  # taken from the bench: it is on
        self.assertEqual(con.view_for(lv).style, "plan")
        text = "\n".join("".join(c[0] or " " for c in row) for row in con.snapshot(lv))
        for word in ("PLAN", "YOU: BARRACKS", "LABS", "REACTOR", "STORAGE", "LANDING PAD", "SHELTER", "EXIT", "+", "*"):
            self.assertIn(word, text)
        self.assertEqual(sorted(lv.spec["sectors"]), ["ARMOURY", "BARRACKS", "COMLINK", "DUST LAB", "LABS", "LANDING PAD",
                                                      "MOTOR POOL", "QUARTERS", "REACTOR", "STORAGE", "WORKSHOP"])


    def test_the_staff_are_brought_to_the_barracks(self):
        lv = Level(GameData(IRONLID), "outpost", seed=1)
        self.assertEqual(lv.shelters, [(4, 1)])
        lv.console = None
        c = next(m for m in lv.monsters if m.civil and (m.x, m.y) == (10, 2))      # the scientist next door
        c.spec = dict(c.spec, roam=0)
        lv.event("alarm")
        for m in lv.monsters:
            if not m.ours:
                m.stun = 999                                    # (hold them where they are)
        p = lv.player
        p.x, p.y = 9, 2
        lv.end_beat()
        self.assertTrue(c.follows)
        for at in ((8, 2), (7, 2), (6, 2), (5, 2), (4, 2), (3, 2), (3, 2), (3, 2), (3, 2), (3, 2)):
            p.x, p.y = at
            lv.end_beat()
            if c.gone:
                break
        self.assertTrue(c.secured)
        self.assertEqual(lv.stats["secured"], 1)

    def test_the_garrison_fights(self):
        data = GameData(IRONLID)
        fought = 0
        for seed in (0, 1, 2):
            lv = Level(data, "outpost", seed=seed)
            troopers = [m for m in lv.monsters if m.ally]
            self.assertEqual(len(troopers), 3)
            lv.event("alarm")
            lv.console = None
            hurt = sum(m.max_hp - m.hp for m in lv.monsters if not m.ours)
            lv.player.x, lv.player.y = 2, 2                     # (he stays in the barracks)
            for _ in range(40):
                lv.player.hp = 100
                lv.end_beat()
                fought += sum(1 for m in troopers if m.grudge is not None and not m.dead)
            self.assertGreater(sum(m.max_hp - m.hp for m in lv.monsters if not m.ours and not m.dead) +
                               sum(m.max_hp for m in lv.monsters if not m.ours and m.dead), hurt, seed)
        self.assertGreater(fought, 10)


class TheYard(unittest.TestCase):
    def test_won_in_lines_with_criticals(self):
        data = GameData(IRONLID)
        for seed in (0, 1, 2):
            outcome, lv = levelbot.play(data, "relocation", seed)
            self.assertEqual(outcome, "exit", seed)
            self.assertIn("ramp", lv.events)                    # the gunner was the lock
            self.assertGreater(lv.stats["criticals"], 0, seed)
            self.assertGreater(lv.player.hp, 0)

    def test_he_begins_it_as_what_was_made_of_him(self):
        lv = Level(GameData(IRONLID), "relocation", seed=1, player={"health": 12, "armor": 0, "weapons": ["1", "2", "3"],
                                                                     "weapon": "3"})
        p = lv.player
        self.assertEqual((p.hp, p.max_hp, p.armor, p.weapons, p.weapon), (130, 130, 25, ["1", "4"], "4"))
        self.assertEqual(lv.weapons["4"]["name"], "arm cannon")
        self.assertEqual(lv.criticals, 2.0)
        term = Term(out=io.StringIO(), width=100, height=30, color=3, unicode=True, animate=False, env={})
        con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False)
        con.layout()
        self.assertEqual((con.view_for(lv).__class__.__name__, con.view_for(lv).style), ("LevelView", "lines"))


class TheShip(unittest.TestCase):
    def test_the_spider_is_beaten_where_it_is_open(self):
        data = GameData(IRONLID)
        for seed in (0, 1, 2):
            outcome, lv = levelbot.play(data, "ship", seed)
            self.assertEqual(outcome, "exit", seed)
            spider = next(m for m in lv.monsters if m.kind == "spider_gun")
            self.assertTrue(spider.dead)
            self.assertIn("taken", lv.events)                   # its fall opens the helm
            self.assertGreater(lv.stats["criticals"], 5, seed)

    def test_it_is_open_as_its_turret_comes_round(self):
        lv = Level(GameData(IRONLID), "ship", seed=1)
        spider = next(m for m in lv.monsters if m.kind == "spider_gun")
        spider.awake, spider.heading = True, 0.0
        lv.player.x, lv.player.y = spider.x + 3, spider.y      # before it: shut
        self.assertIsNone(lv.open_to(spider))
        spider.intent = "spin"
        self.assertEqual(lv.open_to(spider), "as it aims")
        self.assertEqual((lv.player.weapon, lv.player.max_hp, lv.criticals), ("4", 130, 2.0))
        self.assertEqual(lv.sector(spider.x, spider.y), "BRIDGE")


class TheGame(unittest.TestCase):
    def play(self):
        term = Term(out=io.StringIO(), inp=lambda p: "", width=80, height=24, color=0, unicode=True, animate=False, env={})
        g = Game(IRONLID, term=term, audio=Silent())
        real, outcomes = Level.run, []

        def by_its_bot(lv, console):
            outcomes.append((lv.id, real(lv, levelbot.Bot(lv, lv.spec.get("bot") or ["E"]))))
            return outcomes[-1][1]
        with mock.patch.object(Level, "run", by_its_bot):
            g.run()
        return g, outcomes, strip_ansi(term.out.getvalue())

    def test_from_the_outpost_to_the_ship(self):
        g, outcomes, out = self.play()
        self.assertEqual(outcomes, [("outpost", "fallen"), ("relocation", "exit"), ("ship", "exit")])
        self.assertEqual(g.over, "win")
        for words in ("a hundred years late", "The spider does not hurry", "The ramp comes down", "The bridge has no seat", "END OF THE TEST DEMO"):
            self.assertIn(words, out)
        self.assertNotIn("Thane is down. Halden goes quiet", out)                # (the text for losing)
        w = g.world
        self.assertTrue(w.flags.get("outpost_fallen"))
        self.assertGreaterEqual(w.vars["levels"]["outpost"]["saved"], 2)
        self.assertEqual(w.vars["levels"]["outpost"]["civilians_total"], 6)
        self.assertGreater(w.vars["levels"]["relocation"]["criticals"], 0)

    def test_a_death_before_the_spider_is_a_death(self):
        term = Term(out=io.StringIO(), inp=lambda p: "", width=80, height=24, color=0, unicode=True, animate=False, env={})
        g = Game(IRONLID, term=term, audio=Silent())

        def shot(lv, console):
            lv.over = "dead"
            return "dead"
        with mock.patch.object(Level, "run", shot):
            g.run()
        self.assertEqual(g.over, "lose")
        self.assertIn("Halden goes quiet", strip_ansi(term.out.getvalue()))


class TheDemo(unittest.TestCase):
    def test_its_clips_are_right_and_play(self):
        spec = demo.of_game(IRONLID)
        self.assertEqual(demo.problems(spec, GameData(IRONLID)), [])
        self.assertEqual([demo.kind_of(c) for c in spec["clips"]], ["card", "crowd", "crowd", "crowd", "level", "card"])
        clips = [dict(c, seconds=min(2.0, float(c.get("seconds", 3))), count=min(8, int(c.get("count", 8))))
                 if demo.kind_of(c) == "crowd" else dict(c, seconds=min(2.0, float(c.get("seconds", 3))))
                 for c in spec["clips"]]
        p, seen, fc = player(clips, W=80, H=24, game=IRONLID, title=spec["title"])
        self.assertEqual(p.run(), "done")
        out = strip_ansi(p.term.out.getvalue())
        self.assertNotIn("(level:", out)
        self.assertNotIn("(crowd:", out)


if __name__ == "__main__":
    unittest.main()
