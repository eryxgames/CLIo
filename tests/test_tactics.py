# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Tactics that pay (engine/ai, engine/level.py): cover that stops shots both ways, crossfire, grenades that
flush one out of cover, mines, and squads that fight as squads - a swarm, a sweep, an ambush, an assault."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import ai, levelbot, snapshot  # noqa: E402
from engine.ai import brain  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import ROOTLESS, Quiet, put, told, with_level  # noqa: E402

PILLAR = [
    "##########",
    "#........#",
    "#........#",
    "#...#....#",
    "#........#",
    "#........#",
    "##########",
]


def room(rows, legend=None, squads=None, seed=1, monsters=None):
    spec = {"map": rows, "legend": dict({"b": "barrel", "z": "zombie"}, **(legend or {}))}
    if squads is not None:
        spec["squads"] = squads
    data = with_level(spec)
    if monsters:
        data.monsters = dict(data.monsters, **monsters)
    lv = Level(data, "t", seed=seed)
    lv.console = Quiet()
    return lv


def mons(lv, kind=None):
    return sorted((m for m in lv.monsters if not m.barrel and (kind is None or m.kind == kind)), key=lambda m: m.id)


def hall(marks, rows=None, **kw):
    g = [list(r) for r in (rows or ["####################"] + ["#" + "." * 18 + "#"] * 8 + ["####################"])]
    for ch, (x, y) in marks:
        g[y][x] = ch
    return room(["".join(r) for r in g], **kw)


class CoverTests(unittest.TestCase):
    def test_a_corner_the_line_grazes_is_cover(self):
        lv = room(PILLAR)
        self.assertTrue(lv.covered(2, 1, 5, 3) and lv.line_of_sight(2, 1, 5, 3))   # past the pillar's corner
        self.assertFalse(lv.covered(8, 3, 5, 3))              # from the open side
        self.assertFalse(lv.covered(5, 2, 5, 3))              # at arm's length nothing covers
        corridor = room(["########", "#......#", "########"])
        self.assertFalse(corridor.covered(1, 1, 5, 1))        # walls along the line are no cover
        door = room(["#####", "#...#", "##.##", "#...#", "#...#", "#####"])
        self.assertFalse(door.covered(2, 4, 2, 2))            # a doorway, shot at straight on

    def test_cover_stops_the_players_shots(self):
        def rate(covered):
            lv = room(PILLAR, {"z": "zombie"}, seed=3)
            z = lv.add_monster("zombie", 5, 3)
            z.hp = z.max_hp = 10 ** 6
            p = lv.player
            p.weapon, p.ammo["bullets"] = "2", 999
            put(lv, *((2, 1, 1) if covered else (8, 3, 3)))
            lv.target = z
            z.seen = True
            hits = sum(1 for _ in range(200) if lv.fire(tag=z.tag))
            return hits, told(lv)
        open_hits, _ = rate(False)
        cover_hits, said = rate(True)
        self.assertLess(cover_hits, open_hits * 0.75)
        self.assertIn("Your shot hits the cover in front of z1", said)

    def test_cover_stops_their_shots_too_and_crossfire_beats_it(self):
        legend = {"k": {"monster": "kworker", "squad": "a"}}
        lv = room(PILLAR, legend, seed=5)
        k = lv.add_monster("kworker", 2, 1)
        ai.squad.join(lv, k, "a")
        put(lv, 5, 3, 3)
        self.assertTrue(lv.covered(k.x, k.y, 5, 3))
        lv.player.hp = 10 ** 6
        for _ in range(60):
            lv.ranged(k, None, 3)
        self.assertIn("k1's shot hits your cover.", told(lv))
        self.assertEqual(lv.crossfire(k), 0.0)
        k2 = lv.add_monster("kworker", 8, 3)                  # the same squad, from the other side
        ai.squad.join(lv, k2, "a")
        k2.awake = k.awake = True
        self.assertAlmostEqual(lv.crossfire(k), 0.1)
        k3 = lv.add_monster("kworker", 5, 5)
        ai.squad.join(lv, k3, "a")
        k3.awake = True
        self.assertAlmostEqual(lv.crossfire(k), 0.2)          # two at most
        lone = lv.add_monster("kworker", 8, 1)
        lone.awake = True
        self.assertEqual(lv.crossfire(lone), 0.0)             # no squad, no crossfire


class GrenadeAndMineTests(unittest.TestCase):
    def test_a_grenade_flushes_him_out_of_cover(self):
        lv = room(PILLAR)
        K = lv.add_monster("commando", 2, 5)
        K.awake = True
        put(lv, 5, 3, 3)                                       # beside the pillar: covered from it
        self.assertTrue(lv.covered(K.x, K.y, 5, 3) and lv.line_of_sight(K.x, K.y, 5, 3))
        lv.run_line("w")
        self.assertEqual((K.grenades_left, len(lv.grenades)), (1, 1))
        g = lv.grenades[0]
        self.assertLessEqual(max(abs(g.x - 5), abs(g.y - 3)), 1)
        self.assertEqual(g.fuse, 2)                            # three beats: two left to get out
        self.assertIn("K1 throws a grenade - it lands", told(lv))
        lv.run_line("w")
        self.assertEqual(K.grenades_left, 1)                   # not again so soon
        lv.run_line("w")
        self.assertIn("The blast catches you", told(lv))

    def test_no_grenade_for_a_clear_shot_or_where_its_own_would_be_caught(self):
        lv = room(PILLAR)
        K = lv.add_monster("commando", 8, 1)
        K.awake = True
        put(lv, 8, 4, 0)                                       # in the open, in its sight: it shoots
        self.assertIsNone(brain.throw_spot(lv, K, (8, 4), True, True))
        put(lv, 5, 2, 3)
        K.x, K.y = 2, 5
        friend = lv.add_monster("kworker", 6, 2)               # next to him: no grenade
        friend.awake = True
        lv.add_monster("kworker", 5, 1).awake = True
        lv.add_monster("kworker", 4, 1).awake = True
        self.assertIsNone(brain.throw_spot(lv, K, (5, 2), True, True))

    def test_the_bot_steps_out_of_a_grenade(self):
        lv = room(PILLAR)
        put(lv, 5, 4, 0)
        from engine.level import Grenade
        lv.grenades.append(Grenade(5, 4, 3, 30))
        bot = levelbot.Bot(lv, ["E"])
        cmd = bot.decide(lv)
        lv.run_line(cmd)
        self.assertEqual(max(abs(lv.player.x - 5), abs(lv.player.y - 4)), 1)
        lv.run_line(bot.decide(lv))
        self.assertGreaterEqual(max(abs(lv.player.x - 5), abs(lv.player.y - 4)), 2)

    def test_mines(self):
        lv = room(["#########", "#.......#", "####.####", "#.......#", "#########"], {"M": "mine", "m": "medkit"})
        mine = lv.add_item("mine", 4, 2)
        lv.add_item("medkit", 6, 3)
        self.assertTrue(mine.mine)
        self.assertEqual(lv.total_items, 0)                    # added after the count; and a mine is never counted
        fresh = room(["#####", "#.M.#", "#.m.#", "#####"], {"M": "mine", "m": "medkit"})
        self.assertEqual(fresh.total_items, 1)
        put(lv, 4, 1, 2)
        hp = lv.player.hp
        lv.run_line("k")                                       # on to the mine
        self.assertTrue(mine.taken)
        self.assertLess(lv.player.hp, hp)
        self.assertIn("Click. A mine!", told(lv))
        self.assertEqual(lv.stats["items"], 0)

    def test_blasts_set_mines_off_and_the_bot_walks_round_them(self):
        lv = room(["#########", "#.......#", "#.......#", "#.......#", "#########"])
        a, b = lv.add_item("mine", 3, 2), lv.add_item("mine", 4, 2)
        put(lv, 7, 3, 3)
        lv.add_monster("zombie", 5, 3)
        lv.blast(2, 2, 10)
        self.assertTrue(a.taken and b.taken)                   # one after the other
        self.assertIn("A mine goes up: z1", told(lv))
        lv = room(["#########", "#.......#", "#.......#", "#.......#", "#########"])
        lv.add_item("mine", 4, 2)
        put(lv, 2, 2, 1)
        bot = levelbot.Bot(lv, ["E"])
        bot.look_for_mines(lv)
        self.assertEqual(bot.mines, {(4, 2)})
        path = bot.window_path(lv, 6, 2, 10)
        self.assertNotIn((4, 2), path)
        far = levelbot.Bot(lv, ["E"])
        put(lv, 7, 3, 3)
        lv.items[0].x = 1
        far.look_for_mines(lv)
        self.assertEqual(far.mines, set())                     # six cells off: not seen

    def test_a_sweeper_marks_a_doorway_it_holds(self):
        lv = room(["##########", "#........#", "####.#####", "#........#", "##########"])
        c = lv.add_monster("sweeper", 4, 2)
        c.awake, c.role = True, "overwatch"
        put(lv, 8, 1, 1)                                       # looking away: it is not seen
        lv.update_seen()
        c.seen_at = (8, 1, lv.beat)
        self.assertTrue(brain.narrow(lv, 4, 2))
        self.assertTrue(brain.mine_here(lv, c, (8, 1), "hold"))
        lv.lay_mine(c)
        self.assertEqual(c.mines_left, 0)
        self.assertTrue(any(it.mine and (it.x, it.y) == (4, 2) for it in lv.items))
        self.assertFalse(brain.mine_here(lv, c, (8, 1), "hold") and c.mines_left > 0)


class SquadKindTests(unittest.TestCase):
    def test_a_swarm_circles_then_comes_from_all_sides_then_scatters(self):
        legend = {"u": {"monster": "bugrat", "squad": "pack"}}
        lv = hall([("u", (2, 1)), ("u", (17, 1)), ("u", (17, 8)), ("u", (2, 8)), ("u", (10, 8))], legend=legend,
                  squads={"pack": {"tactic": "swarm", "gather": 3}})
        us = mons(lv)
        for u in us:
            u.awake = True
        put(lv, 10, 4, 0)
        sq = lv.squads["pack"]
        sq.seen_at = (10, 4, 0)
        us[4].x, us[4].y = 10, 7
        ai.squad.beat(lv)
        self.assertFalse(sq.stirred)                           # one near: they keep off
        self.assertEqual({u.role for u in us}, {"circle"})
        for u, c in zip(us, ((9, 2), (12, 4), (10, 6))):
            u.x, u.y = c
        lv.update_seen()
        ai.squad.beat(lv)
        self.assertTrue(sq.stirred)
        self.assertIn("The pack comes at you from all sides!", told(lv))
        spots = [u.spot for u in us if u.spot]
        self.assertEqual(len(spots), 4)
        self.assertEqual(len(set(spots)), 4)                   # each to its own side
        us[0].dead = us[1].dead = us[2].dead = True
        ai.squad.beat(lv)
        self.assertTrue(sq.broken)
        self.assertEqual({u.role for u in us if not u.dead}, {"rout"})

    def test_a_pack_bites_harder_together(self):
        def bite(pack):
            lv = room(["#######", "#.....#", "#.....#", "#.....#", "#######"],
                      {"u": {"monster": "bugrat", "squad": "p"}}, seed=9)
            put(lv, 3, 2, 0)
            us = []
            for x, y in ((3, 1), (2, 2), (4, 2), (3, 3))[:1 + pack]:
                u = lv.add_monster("bugrat", x, y)
                ai.squad.join(lv, u, "p")
                us.append(u)
            hp = lv.player.hp = 1000
            lv.bite(us[0], None, (4, 4))
            return hp - lv.player.hp, told(lv)
        self.assertEqual(bite(0)[0], 4)
        self.assertEqual(bite(1)[0], 5)                        # a quarter more for each other one at him
        hurt, said = bite(3)
        self.assertEqual(hurt, 7)
        self.assertIn("the pack is all over you", said)

    def test_a_sweep_bounds_by_halves(self):
        legend = {"c": {"monster": "sweeper", "squad": "s"}}
        lv = hall([("c", (14, 2)), ("c", (15, 4)), ("c", (14, 6)), ("c", (15, 8))], legend=legend,
                  squads={"s": {"tactic": "sweep", "bound": 3}})
        cs = mons(lv)
        for c in cs:
            c.awake = True
        lv.squads["s"].seen_at = (2, 4, 0)
        first = None
        for beat in (0, 1, 2, 3):
            lv.beat = beat
            ai.squad.beat(lv)
            roles = [c.role for c in cs]
            self.assertEqual(sorted(roles), ["advance", "advance", "overwatch", "overwatch"])
            if beat == 0:
                first = roles
            elif beat < 3:
                self.assertEqual(roles, first)
            else:
                self.assertEqual(roles, ["overwatch" if r == "advance" else "advance" for r in first])

    def test_an_assault_sends_the_short_guns_in_and_pins_with_the_long(self):
        legend = {"K": {"monster": "commando", "squad": "a"}, "k": {"monster": "kworker", "squad": "a"},
                  "u": {"monster": "bugrat", "squad": "a"}}
        lv = hall([("K", (14, 2)), ("k", (15, 4)), ("u", (14, 6))], legend=legend, squads={"a": {"tactic": "assault"}})
        for m in mons(lv):
            m.awake = True
        lv.squads["a"].seen_at = (2, 4, 0)
        ai.squad.beat(lv)
        self.assertEqual({m.kind: m.role for m in mons(lv)}, {"commando": "point", "kworker": "suppress", "bugrat": "point"})

    def test_an_ambush_waits_then_fires_at_once(self):
        legend = {"c": {"monster": "sweeper", "squad": "a"}, "&": {"crate": True}}
        rows = ["####################",
                "#..................#",
                "#.........&c.......#",
                "#..................#",
                "#.........&c.......#",
                "#..................#",
                "####################"]
        lv = room(rows, legend, squads={"a": {"tactic": "ambush", "guard": 3}})
        cs = mons(lv)
        self.assertTrue(all(c.awake for c in cs))              # awake from the start, and quiet
        put(lv, 2, 3, 1)
        for _ in range(3):
            lv.run_line("w")
        self.assertEqual({c.role for c in cs}, {"hide"})
        self.assertNotIn("notices you", told(lv))
        self.assertFalse(any(c.intent for c in cs))
        put(lv, 8, 3, 1)                                       # three cells off one of them
        lv.run_line("w")
        self.assertTrue(lv.squads["a"].stirred)
        self.assertIn("Ambush! c1, c2 open up", told(lv))

    def test_squads_fight_as_their_members_would(self):
        lv = hall([("u", (3, 3)), ("u", (4, 3)), ("u", (3, 4)), ("k", (15, 3)), ("k", (16, 3))],
                  legend={"u": "bugrat", "k": "kworker"})
        ai.group(lv, {"radius": 3})
        got = {sq.tactic for sq in lv.squads.values()}
        self.assertEqual(got, {"swarm", "pincer"})
        self.assertEqual(ai.squad.tactic_of(mons(lv)), "swarm")

    def test_packs_in_rooms_and_on_land(self):
        data = GameData(ROOTLESS)
        lv = Level(data, "sim3", seed=4)
        W = lv.world
        for kx in range(-4, 5):
            for ky in range(-4, 5):
                W.wake((W.here[0] + kx, W.here[1] + ky))
        swarms = [sq for sq in lv.squads.values() if sq.tactic == "swarm"]
        self.assertTrue(swarms)                                # bugrats come in packs, and squad by themselves
        self.assertTrue(all(m.kind == "bugrat" for sq in swarms for m in sq.members))
        sim2 = Level(data, "sim2", seed=1, depth=3)
        self.assertTrue(any(sq.tactic in ("swarm", "sweep", "assault") for sq in sim2.squads.values()))

    def test_the_kill_house(self):
        lv = Level(GameData(ROOTLESS), "sim4", seed=1)
        self.assertEqual({n: sq.tactic for n, sq in lv.squads.items()},
                         {"pack": "swarm", "sweep": "sweep", "ambush": "ambush", "assault": "assault"})
        self.assertEqual(sorted(m.kind for m in lv.squads["ambush"].members), ["commando", "sweeper", "sweeper"])
        outcome, lv = levelbot.play(GameData(ROOTLESS), "sim4", 1)
        self.assertEqual(outcome, "exit")


class SaveAndCheckTests(unittest.TestCase):
    def test_a_fight_with_grenades_and_mines_forks_the_same(self):
        data = GameData(ROOTLESS)
        lv = Level(data, "sim4", seed=2)
        bot = levelbot.Bot(lv, lv.spec["bot"])
        read = bot.read
        bot.read = lambda prompt: None if lv.beat >= 260 else read(prompt)
        lv.run(bot)
        lines = lv.journal
        self.assertTrue(any(it.mine for it in lv.items) or lv.grenades or any("grenade" in l for l in bot.lines))
        for k in (len(lines) // 2, len(lines) * 3 // 4):
            a = Level(data, "sim4", seed=2)
            a.replay(lines[:k])
            b = snapshot.restore(Level(data, "sim4", seed=2), json.loads(json.dumps(snapshot.capture(a))))
            self.assertEqual(b.state_hash(), a.state_hash())
            a.replay(lines[k:])
            b.replay(lines[k:])
            self.assertEqual(b.state_hash(), a.state_hash())

    def test_checks(self):
        data = GameData(ROOTLESS)
        data.monsters = dict(data.monsters)
        data.monsters["bugrat"] = dict(data.monsters["bugrat"], squad_tactic="conga")
        data.monsters["commando"] = dict(data.monsters["commando"], grenades={"count": "two"})
        data.monsters["sweeper"] = dict(data.monsters["sweeper"], mines={"count": 1, "item": "medkit"})
        data.levels = dict(data.levels)
        sim3 = json.loads(json.dumps(data.levels["sim3"]))
        sim3["world"]["monsters"].append({"monster": "bugrat", "pack": [5, 2]})
        data.levels["sim3"] = sim3
        sim2 = json.loads(json.dumps(data.levels["sim2"]))
        sim2["generate"]["monsters"].append({"monster": "bugrat", "pack": [1, 9]})
        data.levels["sim2"] = sim2
        got = "\n".join(validate(data))
        self.assertIn("monster 'bugrat': squad_tactic should be one of", got)
        self.assertIn("monster 'commando': grenades count should be a whole number", got)
        self.assertIn("monster 'sweeper': its mines should be an item with \"pickup\": {\"mine\": ...}", got)
        self.assertIn("level 'sim3': world: pack should be [fewest, most]", got)
        self.assertIn("level 'sim2': generate: pack should be [fewest, most]", got)
        self.assertEqual(validate(GameData(ROOTLESS)), [])


if __name__ == "__main__":
    unittest.main()
