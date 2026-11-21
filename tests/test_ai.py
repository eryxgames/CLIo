# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Minds for monsters (engine/ai): brains that weigh their tactics, squads that share what they know and
give out parts, and the search for games of moves and answers."""
import json
import os
import random
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import ai, levelbot, snapshot  # noqa: E402
from engine.ai import brain, search  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import ROOTLESS, Quiet, put, told, with_level  # noqa: E402

# a hall with a pillar block in it; k: kworkers (soldiers), s: scouts (skirmishers), z: zombies (no brain)
HALL = [
    "####################",
    "#..................#",
    "#..................#",
    "#......###.........#",
    "#......###.........#",
    "#..................#",
    "#..................#",
    "####################",
]


def hall(marks, legend=None, monsters=None, squads=None, seed=1):
    rows = [list(r) for r in HALL]
    for ch, (x, y) in marks:
        rows[y][x] = ch
    leg = {"b": "barrel", "z": "zombie", "k": {"monster": "kworker"}, "s": {"monster": "scout"}}
    leg.update(legend or {})
    spec = {"map": ["".join(r) for r in rows], "legend": leg}
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


def up(*ms):
    for m in ms:
        m.awake = True


class BrainTests(unittest.TestCase):
    def test_presets_and_brains_of_their_own(self):
        lv = hall([("@", (2, 2)), ("k", (15, 2)), ("z", (15, 5))],
                  monsters={"heavyk": {"name": "heavy k", "tag": "q", "sprite": "kworker", "hp": 30,
                                       "attack": {"kind": "hitscan", "damage": [1, 2], "range": 8},
                                       "brain": {"kind": "heavy", "flank": 0.9, "range": [2, 4]}}},
                  legend={"q": {"monster": "heavyk"}})
        k, z = mons(lv, "kworker")[0], mons(lv, "zombie")[0]
        b = brain.params(lv, k)
        self.assertEqual((b["kind"], b["range"], b["ranged"]), ("soldier", [3, 7], True))   # its "keep" is its range
        self.assertTrue(brain.has(lv, k))
        self.assertIsNone(brain.params(lv, z))                 # no brain: it hunts as monsters always have
        self.assertFalse(brain.has(lv, z))
        m = lv.add_monster("heavyk", 10, 6)
        b = brain.params(lv, m)
        self.assertEqual((b["kind"], b["flank"], b["hold"], b["range"]), ("heavy", 0.9, 0.9, [2, 4]))

    def test_monsters_without_a_brain_do_as_they_did(self):
        lv = hall([("@", (2, 2)), ("z", (8, 2))])
        z = mons(lv, "zombie")[0]
        up(z)
        for _ in range(4):
            lv.run_line("w")
        self.assertEqual((z.tactic, z.role, z.seen_at, z.squad), (None, None, None, None))
        self.assertIn("z1", told(lv))                          # it fought all the same

    def test_it_knows_only_what_it_sees_and_remembers(self):
        lv = hall([("@", (4, 6)), ("k", (12, 6))])
        k = mons(lv, "kworker")[0]
        up(k)
        put(lv, 4, 6, 0)
        lv.run_line("w")
        self.assertEqual(k.seen_at[:2], (4, 6))                # it saw him: it knows where
        put(lv, 5, 2, 0)                                       # gone behind the pillar, where it cannot see
        k.x, k.y = 12, 6
        self.assertFalse(brain.sees(lv, k))
        lv.run_line("w")
        self.assertEqual((k.tactic, k.seen_at[:2]), ("close", (4, 6)))     # it goes where he was last seen ...
        k.x, k.y = 12, 6
        k.seen_at = (4, 6, lv.beat - 15)
        lv.run_line("w")
        self.assertEqual(k.tactic, "search")                   # ... looks about when he is not there ...
        self.assertEqual(brain.stat(k), "?")
        k.x, k.y = 12, 6
        k.seen_at = (4, 6, lv.beat - 40)
        lv.run_line("w")
        self.assertEqual((k.tactic, k.seen_at), ("hold", None))   # ... until it has forgotten him

    def test_hurt_and_frightened_it_falls_back(self):
        lv = hall([("@", (4, 1)), ("k", (8, 1))])
        k = mons(lv, "kworker")[0]
        up(k)
        put(lv, 4, 1, 1)
        k.hp = 2
        before = abs(k.x - 4) + abs(k.y - 1)
        for _ in range(4):
            lv.run_line("w")
        self.assertEqual(k.tactic, "retreat")
        self.assertGreater(abs(k.x - 4) + abs(k.y - 1), before)
        self.assertIn("k1 falls back", told(lv))
        self.assertEqual(brain.stat(k), "B")

    def test_cover_is_out_of_his_sight_with_a_place_to_lean_out(self):
        lv = hall([("@", (2, 3)), ("k", (6, 5))])
        k = mons(lv, "kworker")[0]
        put(lv, 2, 3, 1)                                       # looking east, at it
        spot = brain.cover_spot(lv, k, 2, 3, True)
        self.assertIsNotNone(spot)
        self.assertFalse(lv.line_of_sight(2, 3, *spot))
        self.assertTrue(any(lv.line_of_sight(spot[0] + dx, spot[1] + dy, 2, 3) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))))
        up(k)
        k.cool = 1                                             # it has just shot: in the open, in front of him
        self.assertEqual(brain.think(lv, k, brain.params(lv, k), (2, 3), True, 4, True), "cover")

    def test_a_flank_is_off_his_eyes_on_the_side_it_was_given(self):
        lv = hall([("@", (9, 6)), ("k", (14, 1))])
        k = mons(lv, "kworker")[0]
        put(lv, 9, 6, 0)                                       # looking north
        for side in (1, -1):
            x, y = brain.flank_spot(lv, k, 9, 6, 3, 7, side)
            self.assertFalse(brain.exposed(lv, x, y))
            self.assertGreater((x - 9) * side, 0)              # 1: his right hand (east, facing north)
            self.assertTrue(lv.line_of_sight(x, y, 9, 6))

    def test_manual_pages_and_ps_tell_minds(self):
        lv = Level(GameData(ROOTLESS), "e1m2", seed=1)
        page = " | ".join(t for t, _s in lv.man_lines("kworker"))
        self.assertIn("mind: soldier - takes cover, keeps its distance, works round your side", page)
        self.assertNotIn("mind:", " | ".join(t for t, _s in lv.man_lines("zombie")))
        k = next(m for m in lv.monsters if m.kind == "kworker")
        k.awake, k.tactic, k.intent = True, "cover", None
        lv.player.x, lv.player.y = k.x - 2, k.y
        lv.update_seen()
        ps = " | ".join(t for t, _s in lv.ps_lines())
        self.assertIn("D in cover", ps)

    def test_the_same_game_the_same_minds(self):
        a = levelbot.play(GameData(ROOTLESS), "e1m2", 4)[1]
        b = levelbot.play(GameData(ROOTLESS), "e1m2", 4)[1]
        self.assertEqual(a.state_hash(), b.state_hash())
        self.assertTrue(any(m.tactic for m in a.monsters))


class SquadTests(unittest.TestCase):
    def test_what_one_sees_they_all_know(self):
        lv = hall([("@", (2, 1)), ("k", (5, 1)), ("s", (16, 6))], legend={"k": {"monster": "kworker", "squad": "a"},
                                                                     "s": {"monster": "scout", "squad": "a"}})
        k, s = mons(lv, "kworker")[0], mons(lv, "scout")[0]
        up(k, s)
        put(lv, 2, 1, 1)
        sq = lv.squads["a"]
        self.assertEqual(sq.members, [k, s])
        self.assertFalse(brain.sees(lv, s))
        lv.run_line("w")
        self.assertEqual(sq.knows(lv), (2, 1))
        self.assertIsNotNone(s.tactic)
        self.assertNotIn(s.tactic, ("hold", "search"))         # it never saw him, but it is on its way

    def test_one_woken_calls_the_others(self):
        lv = hall([("@", (2, 1)), ("k", (5, 1)), ("s", (17, 6)), ("z", (15, 6))],
                  legend={"k": {"monster": "kworker", "squad": "a"}, "s": {"monster": "scout", "squad": "a"}})
        k, s, z = mons(lv, "kworker")[0], mons(lv, "scout")[0], mons(lv, "zombie")[0]
        put(lv, 2, 1, 1)
        up(k)
        lv.run_line("w")
        self.assertTrue(s.awake)
        self.assertFalse(z.awake)                              # not of the squad: it sleeps on
        self.assertIn("k1 calls the others: s1", told(lv))

    def test_roles_by_tactic(self):
        def roles(tactic, marks):
            legend = {"k": {"monster": "kworker", "squad": "a"}, "z": {"monster": "zombie", "squad": "a"}}
            lv = hall([("@", (2, 1))] + marks, legend=legend, squads={"a": {"tactic": tactic}})
            ms = mons(lv)
            up(*ms)
            put(lv, 2, 1, 1)
            lv.squads["a"].seen_at = (2, 1, 0)
            ai.squad.beat(lv)
            return [(m.tag, m.role, m.side) for m in ms]
        five = [("k", (10, 1)), ("k", (11, 1)), ("k", (12, 1)), ("k", (13, 1)), ("k", (14, 1))]
        self.assertEqual(roles("pincer", five), [("k1", "point", 0), ("k2", "flank", 1), ("k3", "flank", -1),
                                                 ("k4", "flank", 1), ("k5", "flank", -1)])
        self.assertEqual(roles("fire_team", five), [("k1", "point", 0), ("k2", "suppress", 0), ("k3", "suppress", 0),
                                                    ("k4", "flank", 1), ("k5", "flank", -1)])
        self.assertEqual({r for _t, r, _s in roles("rush", five)}, {"point"})

    def test_a_holding_squad_waits_by_its_post(self):
        legend = {"k": {"monster": "kworker", "squad": "relay"}}
        lv = hall([("@", (1, 1)), ("k", (16, 5)), ("k", (17, 6))], legend=legend,
                  squads={"relay": {"tactic": "hold", "guard": 6}})
        ks = mons(lv)
        up(*ks)
        put(lv, 1, 1, 1)
        lv.run_line("w")
        sq = lv.squads["relay"]
        self.assertEqual((sq.anchor, sq.stirred), ((16, 5), False))
        self.assertEqual({m.role for m in ks}, {"guard"})
        self.assertEqual([(m.x, m.y) for m in ks], [(16, 5), (17, 6)])   # it holds
        put(lv, 11, 5, 1)                                       # within its guard: the fight starts
        lv.run_line("w")
        self.assertTrue(sq.stirred)
        self.assertIn("point", {m.role for m in ks})

    def test_the_hurt_stir_a_holding_squad_too(self):
        lv = hall([("@", (1, 1)), ("k", (16, 5)), ("k", (17, 6))], legend={"k": {"monster": "kworker", "squad": "r"}},
                  squads={"r": {"tactic": "hold", "guard": 2}})
        ks = mons(lv)
        up(*ks)
        put(lv, 9, 5, 1)                                       # seen, but further off than its guard
        lv.run_line("w")
        self.assertFalse(lv.squads["r"].stirred)
        ks[1].hp -= 5
        lv.run_line("w")
        self.assertTrue(lv.squads["r"].stirred)

    def test_a_new_leader_when_the_old_one_falls(self):
        lv = hall([("@", (1, 1)), ("k", (14, 1)), ("s", (15, 1))], legend={"k": {"monster": "kworker", "squad": "a"},
                                                                     "s": {"monster": "scout", "squad": "a"}})
        k, s = mons(lv, "kworker")[0], mons(lv, "scout")[0]
        up(k, s)
        lv.run_line("w")
        self.assertIs(lv.squads["a"].leader, k)                # the stronger
        k.dead = True
        lv.run_line("w")
        self.assertEqual((lv.squads["a"].members, lv.squads["a"].leader), ([s], s))
        s.dead = True
        lv.run_line("w")
        self.assertNotIn("a", lv.squads)

    def test_squads_made_by_where_they_stand(self):
        lv = hall([("@", (1, 1)), ("k", (3, 5)), ("k", (5, 6)), ("s", (8, 6)), ("k", (15, 1)), ("s", (17, 2)),
                   ("z", (16, 1)), ("k", (18, 6))])
        ai.group(lv, {"radius": 3})
        got = sorted(sorted((m.x, m.y) for m in sq.members) for sq in lv.squads.values())
        self.assertEqual(got, [[(3, 5), (5, 6), (8, 6)], [(15, 1), (17, 2)]])   # a chain; no zombie; no lone one
        self.assertEqual(sorted(lv.squads), ["auto", "auto2"])
        self.assertEqual(ai.squad.free_name(lv, "auto"), "auto3")

    def test_levels_ask_for_them(self):
        lv = Level(GameData(ROOTLESS), "e1m4", seed=1)
        self.assertEqual(sorted(lv.squads), ["relay"])
        sq = lv.squads["relay"]
        self.assertEqual((sq.tactic, sq.guard, sorted(m.kind for m in sq.members)), ("hold", 8, ["warden", "warden"]))
        lv = Level(GameData(ROOTLESS), "e1m2", seed=1)
        self.assertTrue(lv.squads and all(n.startswith("auto") for n in lv.squads))


class WorldSquadTests(unittest.TestCase):
    def pack_chunk(self, lv):
        W = lv.world
        for r in range(2, 30):
            for kx in range(-r, r + 1):
                for ky in (-r, r):
                    key = (W.here[0] + kx, W.here[1] + ky)
                    got = [e for e in W.maker.spawns(*key) if e[0] == "monster" and e[4].get("squad")]
                    if got:
                        return key, got
        self.fail("no pack anywhere near")

    def test_packs_on_open_land(self):
        lv = Level(GameData(ROOTLESS), "sim1", seed=3)
        key, got = self.pack_chunk(lv)
        names = {e[4]["squad"] for e in got}
        for name in names:
            spots = [(x, y) for _w, _n, x, y, e in got if e["squad"] == name]
            self.assertEqual(len(spots), 2)
            self.assertLessEqual(max(abs(spots[0][0] - spots[1][0]), abs(spots[0][1] - spots[1][1])), 2)
        lv.world.wake(key)
        sq = lv.squads["%s@%d,%d" % (sorted(names)[0], key[0], key[1])]
        self.assertEqual(len(sq.members), 2)
        self.assertTrue(all(m.home == key for m in sq.members))

    def test_a_chunk_made_again_makes_its_squads_again(self):
        lv = Level(GameData(ROOTLESS), "sim1", seed=3)
        W = lv.world
        key, got = self.pack_chunk(lv)
        W.wake(key)
        name = next(n for n in lv.squads if n.endswith("@%d,%d" % key))
        first = list(lv.squads[name].members)
        W.awake.discard(key)
        W.sleep_strays()                                       # nobody touched them: forgotten, squad and all
        self.assertNotIn(name, lv.squads)
        self.assertTrue(all(m.squad is None for m in first))
        W.wake(key)
        again = lv.squads[name].members
        self.assertEqual([(m.kind, m.x, m.y) for m in again], [(m.kind, m.x, m.y) for m in first])
        self.assertFalse(any(m in first for m in again))

    def test_a_squad_asleep_in_a_chunk_is_kept_in_a_save(self):
        data = GameData(ROOTLESS)
        lv = Level(data, "sim1", seed=3)
        W = lv.world
        key, got = self.pack_chunk(lv)
        W.wake(key)
        name = next(n for n in lv.squads if n.endswith("@%d,%d" % key))
        lv.squads[name].members[0].hp -= 1                     # touched: it is kept, not made again
        W.awake.discard(key)
        W.sleep_strays()
        self.assertIn(name, lv.squads)
        b = snapshot.restore(Level(data, "sim1", seed=3), json.loads(json.dumps(snapshot.capture(lv))))
        sq = b.squads[name]
        asleep = b.world.sleepers[key]
        self.assertTrue(all(any(m is o for o in asleep) for m in sq.members))   # the same monsters, not copies
        self.assertTrue(all(m.squad is sq for m in sq.members))
        self.assertEqual(b.state_hash(), lv.state_hash())

    def test_dungeon_rooms_make_squads(self):
        lv = Level(GameData(ROOTLESS), "sim3", seed=2)
        W = lv.world
        for kx in range(-3, 4):
            for ky in range(-3, 4):
                W.wake((W.here[0] + kx, W.here[1] + ky))
        self.assertTrue(lv.squads)
        for sq in lv.squads.values():
            self.assertEqual(len({m.home for m in sq.members}), 1)      # a room's own


class FakeNim:
    """Take 1-3 from a pile; who takes the last wins. The side to play loses on a multiple of 4."""

    def __init__(self, n):
        self.n = n

    def moves(self):
        return [k for k in (1, 2, 3) if k <= self.n]

    def play(self, k):
        return FakeNim(self.n - k)

    def done(self):
        return self.n == 0

    def score(self):
        return -1.0 if self.n == 0 else 0.0


class TicTacToe:
    LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]

    def __init__(self, cells="." * 9, side="x"):
        self.cells, self.side = cells, side

    def won(self, who):
        return any(all(self.cells[i] == who for i in line) for line in self.LINES)

    def moves(self):
        return [] if self.done() else [i for i, c in enumerate(self.cells) if c == "."]

    def play(self, i):
        return TicTacToe(self.cells[:i] + self.side + self.cells[i + 1:], "o" if self.side == "x" else "x")

    def done(self):
        return self.won("x") or self.won("o") or "." not in self.cells

    def score(self):
        other = "o" if self.side == "x" else "x"
        return -1.0 if self.won(other) else 1.0 if self.won(self.side) else 0.0


class SearchTests(unittest.TestCase):
    def test_minimax_plays_nim(self):
        for n, take in ((5, 1), (6, 2), (7, 3), (10, 2)):
            self.assertEqual(search.best(FakeNim(n), depth=12)[0], take, "pile of %d" % n)

    def test_minimax_finds_a_win_and_blocks_one(self):
        self.assertEqual(search.best(TicTacToe("xx.oo....", "x"), depth=9)[0], 2)
        self.assertEqual(search.best(TicTacToe("xx..o....", "o"), depth=9)[0], 2)

    def test_two_minimaxes_draw(self):
        s = TicTacToe()
        while not s.done():
            s = s.play(search.best(s, depth=9, nodes=200000)[0])
        self.assertFalse(s.won("x") or s.won("o"))

    def test_mcts_plays_nim_and_does_not_lose_to_chance(self):
        self.assertEqual(search.mcts(FakeNim(5), random.Random(1), playouts=600), 1)
        rng = random.Random(7)
        lost = 0
        for g in range(6):
            s, me = TicTacToe(), g % 2 == 0
            while not s.done():
                if me:
                    mv = search.mcts(s, rng, playouts=300)
                else:
                    ms = s.moves()
                    mv = ms[rng.randrange(len(ms))]
                s, me = s.play(mv), not me
            lost += s.score() == -1.0 and me                   # the side to play now lost, and that is mcts
        self.assertEqual(lost, 0)

    def test_a_budget_not_a_clock(self):
        a = search.best(TicTacToe(), depth=9, nodes=300)
        b = search.best(TicTacToe(), depth=9, nodes=300)
        self.assertEqual(a, b)
        self.assertEqual(search.mcts(TicTacToe(), random.Random(3), 200), search.mcts(TicTacToe(), random.Random(3), 200))
        self.assertIsNone(search.mcts(TicTacToe("xxxoo....", "o"), random.Random(1)))   # over: no move
        self.assertAlmostEqual(search._ln(12345.0), 9.421006, places=6)


class CheckTests(unittest.TestCase):
    def test_brains_squads_and_packs_are_checked(self):
        data = GameData(ROOTLESS)
        data.monsters = dict(data.monsters)
        data.monsters["kworker"] = dict(data.monsters["kworker"], brain="genius")
        data.monsters["scout"] = dict(data.monsters["scout"], brain={"kind": "soldier", "cover": "lots", "wit": 1})
        data.levels = dict(data.levels)
        data.levels["e1m2"] = dict(data.levels["e1m2"], squads={"a": {"tactic": "chess"}, "auto": {"radius": -1}})
        sim1 = json.loads(json.dumps(data.levels["sim1"]))
        sim1["world"]["spawns"][1]["pack"] = [3, 1]
        data.levels["sim1"] = sim1
        got = "\n".join(validate(data))
        self.assertIn("monster 'kworker': unknown brain 'genius'", got)
        self.assertIn("monster 'scout': brain cover should be a number", got)
        self.assertIn("monster 'scout': the brain has no 'wit'", got)
        self.assertIn("level 'e1m2': squads: 'a' has an unknown tactic 'chess'", got)
        self.assertIn("level 'e1m2': squads: 'auto' radius should be a whole number", got)
        self.assertIn("pack should be [fewest, most]", got)
        self.assertEqual(validate(GameData(ROOTLESS)), [])


class SaveTests(unittest.TestCase):
    def test_a_snapshot_from_before_minds_loads(self):
        data = GameData(ROOTLESS)
        before = GameData(ROOTLESS)                            # the game as it was: no squads
        before.levels = dict(before.levels, e1m1={k: v for k, v in before.levels["e1m1"].items() if k != "squads"})
        lv = Level(before, "e1m1", seed=2)
        self.assertEqual(lv.squads, {})
        snap = json.loads(json.dumps(snapshot.capture(lv)))
        old = set(type(lv.monsters[0]).DEFAULTS)

        def strip(x):
            if isinstance(x, dict):
                if x.get("$c") == "Monster":
                    for k in old:
                        del x["f"][k]
                for v in x.values():
                    strip(v)
            elif isinstance(x, list):
                for v in x:
                    strip(v)
        strip(snap)
        del snap["attrs"]["squads"]
        fresh = Level(data, "e1m1", seed=2)
        self.assertTrue(fresh.squads)
        b = snapshot.restore(fresh, snap)
        m = next(m for m in b.monsters if m.kind == "sudo")
        self.assertEqual((m.tactic, m.role, m.squad, m.side, m.seen_at), (None, None, None, 0, None))
        self.assertEqual(b.squads, {})                         # not the new level's, with its own monsters in
        for _ in range(3):
            b.run_line("w")                                    # and it plays on


def old_distances(lv, x0, y0, limit=40, floats=False):
    """The flood fill as it was before ways were worked out lazily: the reference."""
    dist = {(x0, y0): 0}
    frontier = [(x0, y0)]
    while frontier:
        nxt = []
        for (x, y) in frontier:
            d = dist[(x, y)]
            if d >= limit:
                continue
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                n = (x + dx, y + dy)
                if n not in dist and lv.passable(n[0], n[1], floats=floats):
                    dist[n] = d + 1
                    nxt.append(n)
            for n in lv.pad_links().get((x, y), ()):
                if n not in dist:
                    dist[n] = d + 1
                    nxt.append(n)
        frontier = nxt
    return dist


def crowd(level, kind, n, seed=1):
    lv = Level(GameData(ROOTLESS), level, seed=seed)
    lv.console = Quiet()
    lv.anim = lambda *a, **k: None
    p, rng, placed = lv.player, random.Random(7), 0
    for _ in range(n * 60):
        if placed >= n:
            break
        x, y = p.x + rng.randint(-12, 12), p.y + rng.randint(-12, 12)
        if lv.free(x, y) and (x, y) != (p.x, p.y):
            lv.add_monster(kind, x, y)
            placed += 1
    for m in lv.monsters:
        if not m.dead:
            lv.wake(m, quiet=True)
    return lv


def beats(lv, n):
    out = []
    for _ in range(n):
        lv.player.hp = 10 ** 6
        lv.over = False
        lv.end_beat()
        out.append([(m.id, m.x, m.y, m.hp, m.dead, m.intent) for m in lv.monsters] + [lv.rng.random()])
    return out


class CrowdTests(unittest.TestCase):
    """Crowds think faster - ways worked out only as far as asked, line of sight over the land's own heights -
    and exactly as before."""

    def test_ways_are_the_distances_they_were(self):
        rng = random.Random(4)
        for level in ("e1m1", "e1m4"):                   # teleport pads; open land with deep water and slopes
            lv = Level(GameData(ROOTLESS), level, seed=1)
            lv.console = Quiet()
            p = lv.player
            for _ in range(6):
                x0, y0 = p.x + rng.randint(-8, 8), p.y + rng.randint(-8, 8)
                for limit, floats in ((6, False), (24, True), (40, False)):
                    want = old_distances(lv, x0, y0, limit, floats)
                    self.assertEqual(list(lv.distances(x0, y0, limit, floats).items()), list(want.items()))
                    f = lv.ways(x0, y0, limit, floats)
                    asks = [(x0 + rng.randint(-30, 30), y0 + rng.randint(-30, 30)) for _ in range(40)]
                    for at in asks:
                        self.assertEqual(f.get(at, 999), want.get(at, 999), (level, x0, y0, limit, at))
                    f.finish()
                    self.assertEqual(f.dist, want)

    def test_ways_asked_before_the_map_changes_are_as_they_were(self):
        """A wall opens halfway through a beat: a way asked for before is finished on the map as it was."""
        rows = [list(r) for r in HALL]
        for y in range(1, 7):
            rows[y][12] = "#"
        rows[3][12] = "1"
        data = with_level({"map": ["".join(r) for r in rows],
                           "legend": {"1": {"wall": "steel", "opens_on": "go"}}})
        lv = Level(data, "t", seed=1)
        lv.console = Quiet()
        lv.anim = lambda *a, **k: None
        before = lv.ways(2, 3)
        self.assertEqual(before.get((3, 3)), 1)          # one ring worked out, no more
        lv.event("go")                                   # the wall opens
        self.assertEqual(lv.cell(12, 3).kind, "floor")
        self.assertIsNone(before.get((15, 3)))           # as it was: no way round
        now = lv.ways(2, 3).get((15, 3))                 # a way asked for now goes through
        self.assertIsNotNone(now)
        self.assertEqual(now, old_distances(lv, 2, 3)[(15, 3)])

    def test_line_of_sight_over_land_is_as_it_was(self):
        lv = Level(GameData(ROOTLESS), "e1m4", seed=1)
        lv.console = Quiet()
        p, rng = lv.player, random.Random(9)
        from engine.level import bresenham

        def old(x0, y0, x1, y1):
            cells = bresenham(x0, y0, x1, y1)
            if any(lv.cell(x, y).solid for (x, y) in cells[1:-1]):
                return False
            h0, h1 = lv.eye_height(x0, y0), lv.eye_height(x1, y1)
            n = len(cells) - 1
            return not any(lv.ground(x, y) > h0 + (h1 - h0) * i / n + 0.05 for i, (x, y) in enumerate(cells[1:-1], 1))
        seen = 0
        for _ in range(600):
            a = (p.x + rng.randint(-14, 14), p.y + rng.randint(-14, 14))
            b = (p.x + rng.randint(-14, 14), p.y + rng.randint(-14, 14))
            got = lv.line_of_sight(a[0], a[1], b[0], b[1])
            self.assertEqual(got, old(a[0], a[1], b[0], b[1]), (a, b))
            seen += got
        self.assertTrue(50 < seen < 550)                 # hills hide some, not all

    def test_a_crowd_thinks_as_with_whole_ways(self):
        """Beat after beat, a crowd awake goes where it went when every way was worked out whole."""
        whole = lambda self, x, y, limit=40, floats=False: self.distances(x, y, limit, floats)   # noqa: E731
        for level, kind, n in (("e1m1", "kworker", 20), ("e1m4", "scout", 30)):
            lazy = beats(crowd(level, kind, n), 8)
            with mock.patch.object(Level, "ways", whole):
                eager = beats(crowd(level, kind, n), 8)
            self.assertEqual(lazy, eager, level)
            self.assertNotEqual(lazy[0][:-1], lazy[-1][:-1])     # they did move


if __name__ == "__main__":
    unittest.main()
