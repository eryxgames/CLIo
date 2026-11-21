"""Doors and gates: lockers, supply crates, bars, force fields, timed doors and one-way doors."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import levelbot, snapshot  # noqa: E402
from engine.firstperson import FX, View  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import Quiet, put, told, with_level  # noqa: E402


def room(rows, legend, seed=1, **more):
    spec = {"map": rows, "legend": legend}
    spec.update(more)
    lv = Level(with_level(spec), "t", seed=seed)
    lv.console = Quiet()
    return lv


def facing(lv, x, y, f):
    put(lv, x, y, f)
    return lv


class LockerTests(unittest.TestCase):
    def test_a_locker_gives_what_is_in_it(self):
        lv = room(["#####",
                   "##L##",
                   "#.@.#",
                   "#####"], {"L": {"locker": ["shells", "medkit"]}})
        lv.player.hp = 50
        self.assertEqual(lv.total_items, 2)
        self.assertTrue(lv.cell(2, 1).solid)
        self.assertEqual(lv.cell(2, 1).texture(), "locker")
        shells = lv.player.ammo.get("shells", 0)
        self.assertTrue(lv.use())
        self.assertGreater(lv.player.ammo["shells"], shells)
        self.assertGreater(lv.player.hp, 50)
        self.assertEqual(lv.stats["items"], 2)
        self.assertEqual(lv.cell(2, 1).texture(), "locker_open")
        self.assertIn("You open the locker", told(lv))
        self.assertFalse(lv.use())                           # and then it is empty
        self.assertIn("An empty locker", told(lv))
        self.assertEqual(lv.beat, 1)

    def test_walking_into_a_locker_opens_it(self):
        lv = room(["#####",
                   "##L##",
                   "#.@.#",
                   "#####"], {"L": {"locker": "clip"}})
        lv.step(0, 1)
        self.assertTrue(lv.cell(2, 1).opened)

    def test_what_he_cannot_use_lies_at_his_feet(self):
        lv = room(["#####",
                   "##L##",
                   "#.@.#",
                   "#####"], {"L": {"locker": ["medkit"]}})
        lv.use()                                             # full health: the medkit stays
        it = [i for i in lv.items if i.iid == "medkit"]
        self.assertEqual(len(it), 1)
        self.assertFalse(it[0].taken)
        self.assertEqual((it[0].x, it[0].y), (2, 2))

    def test_a_locked_locker_needs_its_key_and_opening_sets_off_an_event(self):
        lv = room(["#######",
                   "##L####",
                   "#.@..1#",
                   "#######"], {"L": {"locker": ["clip"], "key": "r", "on_open": "alarm"},
                                "1": {"wall": "steel", "opens_on": "alarm"}})
        self.assertEqual(lv.cell(2, 1).texture(), "locker_r")
        self.assertFalse(lv.use())
        self.assertIn("needs the r-- key", told(lv))
        lv.player.keys.add("r")
        self.assertTrue(lv.use())
        self.assertEqual(lv.cell(5, 2).kind, "floor")


class SupplyCrateTests(unittest.TestCase):
    def test_a_supply_crate_opens_and_still_stands(self):
        lv = room(["######",
                   "#.$..#",
                   "#.@..#",
                   "######"], {"$": {"supply": ["clip", "shells"]}})
        c = lv.cell(2, 1)
        self.assertTrue(c.crate)
        self.assertTrue(lv.use())
        self.assertIn("pry the crate open", told(lv))
        self.assertTrue(c.crate and c.opened and c.supply == ())
        self.assertFalse(lv.use())

    def test_pushed_or_thrown_it_keeps_what_is_in_it(self):
        lv = room(["######",
                   "#....#",
                   "#.$..#",
                   "#.@..#",
                   "######"], {"$": {"supply": ["clip"]}})
        lv.step(0, 1)                                        # walking into it pushes it
        self.assertFalse(lv.cell(2, 2).crate)
        moved = lv.cell(2, 1)
        self.assertEqual((moved.crate, moved.supply), (True, ("clip",)))
        self.assertIsNone(lv.cell(2, 2).supply)
        lv.blast_push(3, 1)                                  # a blast to its east throws it west
        self.assertEqual(lv.cell(1, 1).supply, ("clip",))
        self.assertIsNone(lv.cell(2, 1).supply)

    def test_it_is_drawn_shut_and_open(self):
        from engine.firstperson import SUPPLY, SUPPLY_OPEN
        lv = room(["#####",
                   "#.$.#",
                   "#...#",
                   "#.@.#",
                   "#####"], {"$": {"supply": ["clip"]}})
        before = View(40, 12, "pixel").render(lv, FX(), 0)
        lv.cell(2, 1).opened = True
        after = View(40, 12, "pixel").render(lv, FX(), 0)
        self.assertNotEqual(before, after)
        self.assertNotEqual(SUPPLY.rows, SUPPLY_OPEN.rows)


class BarsAndFieldTests(unittest.TestCase):
    def test_bars_are_seen_and_shot_through_not_walked(self):
        lv = room(["#######",
                   "#..z..#",
                   "###G###",
                   "#..@..#",
                   "#######"], {"G": {"gate": True, "opens_on": "go"}, "z": "zombie"})
        g = lv.cell(3, 2)
        self.assertTrue(g.solid and g.clear and g.sealed)
        self.assertEqual(g.texture(), "bars")
        self.assertIn("bars", lv.see_through)
        self.assertTrue(lv.line_of_sight(3, 3, 3, 1))
        z = lv.monsters[0]
        self.assertTrue(z.seen)
        self.assertFalse(lv.step(0, 1))                      # sealed: no way through
        self.assertEqual((lv.player.x, lv.player.y), (3, 3))
        hp = z.hp
        lv.player.ammo["bullets"] = 50
        lv.fire()
        self.assertLess(z.hp, hp)                            # shot through the bars
        lv.event("go")
        self.assertEqual(g.open, 1.0)

    def test_a_field_zaps_and_drops_when_its_emitter_dies(self):
        lv = room(["#######",
                   "#..e..#",
                   "###F###",
                   "#..@..#",
                   "#######"], {"F": {"field": True, "opens_on": "down", "zap": 7},
                                "e": {"monster": "zombie", "on_death": "down"}})
        f = lv.cell(3, 2)
        self.assertEqual((f.kind, f.texture()), ("field", "field"))
        self.assertTrue(lv.line_of_sight(3, 3, 3, 1))
        hp = lv.player.hp
        self.assertTrue(lv.step(0, 1))                       # walked into: it throws him back, and costs a beat
        self.assertEqual(lv.player.hp, hp - 7)
        self.assertEqual((lv.player.x, lv.player.y), (3, 3))
        self.assertIn("The field throws you back", told(lv))
        lv.kill(lv.monsters[0])
        self.assertEqual(f.kind, "floor")
        self.assertTrue(lv.step(0, 1))
        self.assertEqual((lv.player.x, lv.player.y), (3, 2))

    def test_a_field_comes_back_on(self):
        lv = room(["#####",
                   "#.F.#",
                   "#.@.#",
                   "#####"], {"F": {"field": True, "opens_on": "off", "closes_on": "on"}})
        lv.event("off")
        self.assertEqual(lv.cell(2, 1).kind, "floor")
        lv.event("on")
        self.assertEqual(lv.cell(2, 1).kind, "field")

    def test_monsters_do_not_pass_bars_or_fields(self):
        lv = room(["#####",
                   "#.G.#",
                   "#.F.#",
                   "#.@.#",
                   "#####"], {"G": {"gate": True, "opens_on": "x"}, "F": {"field": True, "opens_on": "y"}})
        self.assertFalse(lv.passable(2, 1))
        self.assertFalse(lv.passable(2, 2))
        self.assertNotIn((2, 1), lv.distances(2, 3))


class TimedAndOneWayDoorTests(unittest.TestCase):
    def timed(self):
        return room(["#########",
                     "#...T...#",
                     "#.......#",
                     "#.@.s...#",
                     "#########"], {"T": {"door": True, "open_for": 3, "opens_on": "run"},
                                    "s": {"switch": "run"}}, facing="e")

    def test_a_timed_door_shuts_and_its_switch_opens_it_again(self):
        lv = self.timed()
        lv.player.x = 3                                      # at the switch, facing it
        lv.update_seen()
        d = lv.cell(4, 1)
        self.assertEqual(d.texture(), "door_timed")
        self.assertTrue(lv.use())                            # the switch: the door opens for three beats
        self.assertEqual(d.open, 1.0)
        self.assertIn("shut again in 3 beats", told(lv))
        for _ in range(2):                                   # three moves: at the end of the third, it shuts
            lv.run_line("w")
            self.assertEqual(d.open, 1.0)
        lv.run_line("w")
        self.assertEqual(d.open, 0.0)
        self.assertTrue(d.sealed)
        self.assertIn("A door starts to close!", told(lv))
        self.assertIn("A door slams shut.", told(lv))
        self.assertFalse(lv.cell(4, 3).pressed)              # the switch is back
        self.assertTrue(lv.use())
        self.assertEqual(d.open, 1.0)

    def test_it_does_not_shut_on_him(self):
        lv = self.timed()
        lv.player.x = 3
        lv.use()
        put(lv, 4, 1, 0)                                     # standing in the doorway
        for _ in range(6):
            lv.run_line("w")
        self.assertEqual(lv.cell(4, 1).open, 1.0)
        put(lv, 4, 2, 0)
        lv.run_line("w")
        self.assertEqual(lv.cell(4, 1).open, 0.0)

    def test_a_door_opened_by_hand_shuts_again(self):
        lv = room(["#####",
                   "#.T.#",
                   "#.@.#",
                   "#####"], {"T": {"door": True, "open_for": 2}})
        self.assertTrue(lv.use())
        self.assertEqual(lv.cell(2, 1).open, 1.0)
        for _ in range(3):
            lv.run_line("w")
        self.assertEqual(lv.cell(2, 1).open, 0.0)
        self.assertFalse(lv.cell(2, 1).sealed)               # no switch to it: it opens by hand again

    def test_a_one_way_door(self):
        lv = room(["#####",
                   "#.@.#",
                   "##O##",
                   "#...#",
                   "#####"], {"O": {"door": True, "from": "s"}}, facing="s")
        o = lv.cell(2, 2)
        self.assertEqual(o.texture(), "door_oneway")
        self.assertFalse(lv.use())
        self.assertIn("does not open from this side", told(lv))
        facing(lv, 2, 3, 0)
        self.assertTrue(lv.use())
        self.assertEqual(o.open, 1.0)


class KeepingTests(unittest.TestCase):
    def test_a_save_keeps_them(self):
        def build():
            return room(["########",
                         "#.L.$..#",
                         "#......#",
                         "#.T.s..#",
                         "#......#",
                         "########"], {"L": {"locker": ["clip"]}, "$": {"supply": ["shells"]},
                                       "T": {"door": True, "open_for": 5, "opens_on": "go"}, "s": {"switch": "go"}})
        lv = build()
        facing(lv, 2, 2, 0)
        lv.use()                                             # the locker
        facing(lv, 4, 2, 0)
        lv.use()                                             # the crate
        facing(lv, 4, 2, 2)
        lv.use()                                             # the switch: the timed door opens
        facing(lv, 5, 1, 3)
        snap = snapshot.capture(lv)
        again = build()
        snapshot.restore(again, snap)
        for x, y in ((2, 1), (4, 1), (2, 3), (4, 3)):
            self.assertEqual(snapshot.cell_states(again)[y * lv.w + x], snapshot.cell_states(lv)[y * lv.w + x])
        self.assertTrue(again.cell(2, 1).opened)
        self.assertEqual(again.cell(4, 1).supply, ())
        self.assertEqual(again.cell(2, 3).closes_at, lv.cell(2, 3).closes_at)
        for _ in range(6):
            lv.run_line("w")
            again.run_line("w")
        self.assertEqual(again.cell(2, 3).open, 0.0)
        self.assertEqual(snapshot.digest(snapshot.capture(again)), snapshot.digest(snapshot.capture(lv)))


class CheckTests(unittest.TestCase):
    def problems(self, legend, rows=None):
        data = with_level({"map": rows or ["#####",
                                           "#@AE#",
                                           "#####"], "legend": legend})
        return [p for p in validate(data) if "level 't'" in p]

    def test_what_is_wrong_is_said(self):
        got = " | ".join(self.problems({"A": {"locker": ["clip", "nothing_like_it"]}}))
        self.assertIn("holds an unknown item 'nothing_like_it'", got)
        got = " | ".join(self.problems({"A": {"door": True, "from": "up"}}))
        self.assertIn("it should be n, e, s or w", got)
        got = " | ".join(self.problems({"A": {"wall": "steel", "from": "n"}}))
        self.assertIn("only a door opens from one side", got)
        got = " | ".join(self.problems({"A": {"door": True, "open_for": 0}}))
        self.assertIn("open_for should be the beats", got)
        got = " | ".join(self.problems({"A": {"locker": True, "on_open": "nobody_listens"}}))
        self.assertIn("nothing opens, closes or wakes on it", got)
        self.assertEqual(self.problems({"A": {"supply": ["clip"], "on_open": "x"}, "B": {"wall": "steel",
                                                                                         "opens_on": "x"}}, ["######",
                                                                                                             "#@ABE#",
                                                                                                             "######"]), [])


class BotTests(unittest.TestCase):
    def test_the_bot_opens_them_on_its_way(self):
        rows = ["###########",
                "#....L....#",
                "#.........#",
                "#.$...@...#",
                "#......s..#",
                "####T######",
                "#.........#",
                "#.........#",
                "#####O#####",
                "#.........#",
                "#.......E.#",
                "###########"]
        legend = {"L": {"locker": ["clip"]}, "$": {"supply": ["shells"]},
                  "T": {"door": True, "open_for": 8, "opens_on": "run"},
                  "s": {"switch": "run"}, "O": {"door": True, "from": "n"}}
        data = with_level({"map": rows, "legend": legend, "bot": ["$", "L", "s", "T", "O", "E"]})
        for seed in range(3):
            out, lv = levelbot.play(data, "t", seed=seed)
            self.assertEqual(out, "exit", seed)
            self.assertTrue(lv.cell(5, 1).opened)
            self.assertTrue(lv.cell(2, 3).opened)
            self.assertEqual(lv.stats["items"], 2)


class UserSpaceTests(unittest.TestCase):
    """RØØTLESS's E1M5: every one of them, in a level the Fens lead to."""

    def test_it_checks_clean_and_has_them_all(self):
        from engine.data import GameData
        from test_levels import ROOTLESS
        data = GameData(ROOTLESS)
        self.assertEqual([q for q in validate(data) if "e1m5" in q], [])
        lv = Level(data, "e1m5", seed=1)
        cells = [c for row in lv.grid for c in row]
        self.assertGreaterEqual(sum(1 for c in cells if c.kind == "locker"), 7)
        self.assertGreaterEqual(sum(1 for c in cells if c.supply is not None), 5)
        self.assertTrue(any(c.gate and not c.sealed for c in cells))
        self.assertTrue(any(c.kind == "field" for c in cells))
        self.assertEqual(len(lv.timed_cells), 1)
        self.assertTrue(any(c.from_side is not None for c in cells))
        self.assertEqual(sorted(m.on_death for m in lv.monsters if m.on_death), ["mmu_east", "mmu_west"])
        scenes = {s["id"]: s for s in data.scenes} if isinstance(data.scenes, list) else data.scenes
        self.assertIn({"goto": "user_space"}, scenes["xantrium_fens"]["on_level_exit"])
        self.assertIn({"win": "outro_demo"}, scenes["user_space"]["on_level_exit"])

    def test_the_bot_gets_through_and_a_save_holds_it(self):
        from engine.data import GameData
        from test_levels import ROOTLESS
        data = GameData(ROOTLESS)
        for seed in (0, 3):
            out, lv = levelbot.play(data, "e1m5", seed=seed)
            self.assertEqual(out, "exit", seed)
            self.assertTrue(lv.cell(0, 14).opened)               # his own locker
            self.assertIn("own_locker", lv.events)
        lines = [l for _b, l in lv.journal]
        again = Level(data, "e1m5", seed=3)
        again.console = Quiet()
        snap = None
        for i, line in enumerate(lines):
            if i == len(lines) // 2:
                snap = snapshot.capture(again)
            again.run_line(line)
        third = Level(data, "e1m5", seed=3)
        third.console = Quiet()
        snapshot.restore(third, snap)
        for line in lines[len(lines) // 2:]:
            third.run_line(line)
        self.assertEqual(snapshot.digest(snapshot.capture(third)), snapshot.digest(snapshot.capture(again)))


if __name__ == "__main__":
    unittest.main()
