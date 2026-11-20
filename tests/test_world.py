"""Levels made as one goes (engine/chunks.py) and from a seed (engine/levelgen.py): chunks woken, put to
sleep and forgotten round the player, what changed in them kept; open land without end with its sites;
dungeons without end; dungeon floors made new each run; and RØØTLESS's Simulatron levels."""
import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import firstperson as fp  # noqa: E402
from engine import levelbot  # noqa: E402
from engine.chunks import N, ORIGIN  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.level import Level, level_depth, resume, validate  # noqa: E402
from test_levels import ROOTLESS, Quiet, with_level  # noqa: E402

DUNGEON = {"kind": "dungeon", "rooms": 0.8, "links": 0.7, "doors": 0.4, "exit": {"away": 3},
           "monsters": [{"monster": "zombie", "weight": 3}, {"monster": "kworker", "from": 1}],
           "per_room": [1, 2], "items": [{"item": "medkit"}], "items_per_room": [1, 1]}
LAND = {"kind": "land", "awake": 2,
        "sites": [{"name": "home", "at": [0, 0], "map": ["#####", "#...#", "#.@.#", "#...#", "##.##"]},
                  {"name": "goal", "at": [60, -40], "map": ["#####", "#.E.#", "#...#", "##.##"],
                   "landmarks": [{"at": [2, -2], "model": "relay_mast", "solid": True}]},
                  {"name": "hut", "chance": 0.3, "away": 20, "spacing": 1, "map": ["###", "#m#", "#.#"],
                   "legend": {"m": "medkit"}}],
        "spawns": [{"monster": "scout", "per_chunk": 0.6, "on": ["grass", "forest"], "away": 20},
                   {"item": "stimpack", "per_chunk": 0.5, "away": 10}]}


def world(spec, seed=1, land=None, **more):
    lv_spec = dict({"world": spec, "bot": ["E"]}, **more)
    if land is not None:
        lv_spec["land"] = land
    lv = Level(with_level(lv_spec), "t", seed=seed)
    lv.console = Quiet()
    return lv


def walk(lv, dx, dy):
    """Carry the player straight off (no beats played): the world follows him."""
    p = lv.player
    p.x, p.y = p.x + dx, p.y + dy
    lv.world.follow()


def snapshot(lv):
    p = lv.player
    W = lv.world
    return ((p.x, p.y, p.facing, p.hp, sorted(p.ammo.items())), lv.beat, sorted(lv.stats.items()), lv.rng.getstate(),
            sorted((m.kind, m.x, m.y, m.hp, m.dead) for m in lv.monsters),
            sorted((it.iid, it.x, it.y, it.taken) for it in lv.items), sorted(W.awake),
            [(c.open, c.crate, c.found) for k in sorted(W.awake) for c in W.loaded[k]])


class ChunkTests(unittest.TestCase):
    def test_only_what_is_near_is_made(self):
        lv = world(DUNGEON)
        W = lv.world
        r = W.r
        self.assertEqual(W.awake, {((lv.player.x >> 4) + i, (lv.player.y >> 4) + j)
                                   for i in range(-r, r + 1) for j in range(-r, r + 1)})
        self.assertLessEqual(len(W.loaded), (2 * r + 1) ** 2 + len(W.pinned))
        self.assertEqual(lv.cell(lv.player.x, lv.player.y).kind, "floor")
        far = (lv.player.x + 50 * N, lv.player.y)
        self.assertNotIn((far[0] >> 4, far[1] >> 4), W.loaded)
        lv.cell(*far)                                        # looking far off makes that chunk, and no more
        self.assertIn((far[0] >> 4, far[1] >> 4), W.loaded)
        self.assertTrue(all(abs((m.x >> 4) - (lv.player.x >> 4)) <= r + 1 for m in lv.monsters))

    def test_the_same_seed_makes_the_same_world(self):
        a, b, c = world(DUNGEON, seed=4), world(DUNGEON, seed=4), world(DUNGEON, seed=5)
        here = (a.player.x, a.player.y)
        grid = lambda lv: [lv.cell(here[0] + x, here[1] + y).ch for y in range(-40, 40) for x in range(-40, 40)]  # noqa: E731
        who = lambda lv: sorted((m.kind, m.x, m.y) for m in lv.monsters)  # noqa: E731
        self.assertEqual(grid(a), grid(b))
        self.assertEqual(who(a), who(b))
        self.assertNotEqual(grid(a), grid(c))

    def test_what_changed_is_there_when_he_comes_back(self):
        lv = world(DUNGEON, seed=3)
        W, p = lv.world, lv.player
        home = (p.x, p.y)
        m = next(m for m in lv.monsters if (m.x >> 4, m.y >> 4) not in W.pinned)
        it = next(i for i in lv.items if (i.x >> 4, i.y >> 4) != (m.x >> 4, m.y >> 4))
        m.hp -= 5
        it.taken = True
        door = next((c for cells in W for c in cells if c.kind == "door" and (c.x >> 4, c.y >> 4) not in W.pinned), None)
        if door is not None:
            door.open = 1.0
        walk(lv, 30 * N, 0)
        self.assertNotIn(m, lv.monsters)
        self.assertIn(m, W.sleepers[(m.x >> 4, m.y >> 4)])
        if door is not None:
            self.assertNotIn((door.x >> 4, door.y >> 4), W.loaded)            # forgotten, but not what changed
            self.assertIn((door.x >> 4, door.y >> 4), W.changes)
        lv.player.x, lv.player.y = home
        W.follow()
        self.assertIn(m, lv.monsters)
        self.assertEqual(m.hp, m.max_hp - 5)
        self.assertFalse(any(i is it for i in lv.items))
        if door is not None:
            self.assertEqual(lv.cell(door.x, door.y).open, 1.0)

    def test_an_untouched_chunk_is_made_again_the_same(self):
        lv = world(DUNGEON, seed=6)
        W = lv.world
        before = sorted((m.kind, m.x, m.y) for m in lv.monsters)
        home = (lv.player.x, lv.player.y)
        walk(lv, 30 * N, 0)
        self.assertEqual(sum(len(v) for v in W.sleepers.values()), 0)     # nothing kept: all as it was made
        lv.player.x, lv.player.y = home
        W.follow()
        self.assertEqual(sorted((m.kind, m.x, m.y) for m in lv.monsters), before)

    def test_a_long_way_keeps_little(self):
        lv = world(DUNGEON, seed=2)
        W = lv.world
        for _ in range(40):
            walk(lv, N, N // 2)
        self.assertLessEqual(len(W.loaded), (2 * W.keep_r + 1) ** 2 + len(W.pinned))
        self.assertTrue(all((m.x >> 4, m.y >> 4) in W.awake for m in lv.monsters))

    def test_a_game_played_back_is_the_same(self):
        data = GameData(ROOTLESS)
        outcome, lv = levelbot.play(data, "sim3", 2)
        again = Level(data, "sim3", seed=2)
        again.replay(lv.journal)
        self.assertEqual(snapshot(again), snapshot(lv))
        half = Level(data, "sim3", seed=2)
        half.replay(lv.journal[:len(lv.journal) // 2])
        back, note = resume(data, half.save_block())
        self.assertIsNone(note)
        self.assertEqual(snapshot(back), snapshot(half))


class LandWorldTests(unittest.TestCase):
    def setUp(self):
        self.lv = world(LAND, seed=7)

    def test_the_start_is_in_its_site(self):
        lv = self.lv
        self.assertEqual((lv.player.x, lv.player.y), (ORIGIN, ORIGIN))
        self.assertEqual(lv.cell(ORIGIN - 2, ORIGIN - 2).kind, "wall")
        self.assertIn((ORIGIN - 2, ORIGIN - 2), lv.land_walls)      # a site's walls stand on the land
        self.assertEqual(lv.ground(ORIGIN, ORIGIN), 0.0)
        self.assertTrue(lv.cell(ORIGIN + 9, ORIGIN + 9).sky)

    def test_a_fixed_site_is_known_from_the_start(self):
        lv = self.lv
        (ex, ey), = lv.world.known("E")
        self.assertEqual((ex - ORIGIN, ey - ORIGIN), (60, -41))
        self.assertIn((ex >> 4, ey >> 4), lv.world.loaded)
        self.assertEqual(lv.cell(ex, ey).kind, "exit")
        mast = [m for m in lv.land.marks if m.get("model") == "relay_mast"]
        self.assertEqual(len(mast), 1)
        self.assertTrue(lv.cell(*mast[0]["at"]).steep)
        self.assertIn(levelbot.Bot(lv, ["E"]).goal_cell(lv), [(ex + 1, ey), (ex - 1, ey), (ex, ey + 1)])

    def test_sites_by_chance_spread_out_and_come_again(self):
        lv = self.lv
        found = [(kx, ky) for kx in range(-12, 13) for ky in range(-12, 13)
                 if lv.world.maker.site_at((ORIGIN >> 4) + kx, (ORIGIN >> 4) + ky)]
        self.assertTrue(found)
        for a in found:
            self.assertFalse(any(b != a and max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1 for b in found))
        again = world(LAND, seed=7)
        self.assertEqual(found, [(kx, ky) for kx in range(-12, 13) for ky in range(-12, 13)
                                 if again.world.maker.site_at((ORIGIN >> 4) + kx, (ORIGIN >> 4) + ky)])
        s, x0, y0 = lv.world.maker.site_at((ORIGIN >> 4) + found[0][0], (ORIGIN >> 4) + found[0][1])
        self.assertEqual(lv.cell(x0 + 1, y0 + 1).ch, "m")
        self.assertEqual(lv.ground(x0 + 1, y0 + 2), 0.0)                  # flattened, at the start's height

    def test_spawns_keep_their_rules(self):
        lv = self.lv
        for _ in range(6):
            walk(lv, N, 0)
        scouts = [m for m in lv.monsters if m.kind == "scout"]
        self.assertTrue(scouts)
        for m in scouts:
            k = lv.land.at_cell(m.spawned[0], m.spawned[1])[2]
            self.assertIn(lv.land.biomes[k].name, ("grass", "forest"))
            self.assertGreaterEqual(abs(complex(m.spawned[0] - ORIGIN, m.spawned[1] - ORIGIN)), 20)

    def test_a_picture_of_it(self):
        v = fp.View(100, 24, "pixel")
        rows = v.render(self.lv, fp.FX(), 0)
        self.assertEqual((len(rows), len(rows[0])), (24, 100))
        lines = levelbot.TextConsole(lambda t: None, lambda p: None).whole_map(self.lv)
        self.assertEqual(len(lines), 41)                                 # the part round the player
        self.assertEqual(lines[20][38], "^")


class DungeonFloorTests(unittest.TestCase):
    SPEC = {"type": "dungeon", "size": [44, 32], "rooms": [7, 9], "key": {"door": "W", "item": "key_w"},
            "secret": "armor", "pools": 0.3, "monsters": [{"monster": "zombie"}, {"monster": "daemon", "from": 2}],
            "items": [{"item": "medkit"}], "guard": "kswapd", "walls": ["#", "%"]}

    def floor(self, seed=1, depth=0, **more):
        lv = Level(with_level({"generate": dict(self.SPEC, **more), "bot": ["key_w", "E"]}), "t", seed=seed, depth=depth)
        lv.console = Quiet()
        return lv

    def test_a_floor_has_a_start_an_exit_a_key_and_a_secret(self):
        from engine.levelgen import _flood, generate
        import random
        rows, extra = generate(self.SPEC, random.Random(3), 0, GameData(ROOTLESS))
        text = "".join(rows)
        self.assertEqual(text.count("@"), 1)
        self.assertEqual(text.count("E"), 1)
        self.assertEqual(text.count("S"), 1)
        self.assertIn("key_w", extra.values())
        g = [list(r) for r in rows]
        start = next((x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch == "@")
        reach = _flood(g, start, stop="W")
        key = next(c for c, v in extra.items() if v == "key_w")
        self.assertTrue(any(rows[y][x] == key for (x, y) in reach))      # the key, without going through its door
        ex, ey = next((x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch == "E")
        self.assertFalse(any(abs(x - ex) + abs(y - ey) == 1 for (x, y) in reach))   # the exit is behind the door

    def test_the_bot_finishes_floors(self):
        for seed in (0, 1):
            lv = self.floor(seed=seed)
            self.assertEqual(lv.run(levelbot.Bot(lv, ["key_w", "E"])), "exit", "seed %d" % seed)

    def test_a_new_floor_each_run_unless_a_seed_is_given(self):
        data = with_level({"generate": dict(self.SPEC, seed="run")})
        a, b = Level(data, "t"), Level(data, "t")
        self.assertNotEqual(a.seed, b.seed)
        again = resume(data, a.save_block())[0]
        self.assertEqual([again.cell(x, y).ch for y in range(32) for x in range(44)],
                         [a.cell(x, y).ch for y in range(32) for x in range(44)])
        self.assertEqual(Level(data, "t", seed=9).seed, 9)

    def test_deeper_is_worse(self):
        shallow = sum(len(self.floor(seed=s).monsters) for s in range(4))
        deep = sum(len(self.floor(seed=s, depth=4).monsters) for s in range(4))
        self.assertGreater(deep, shallow)
        self.assertTrue(any(m.kind == "daemon" for s in range(4) for m in self.floor(seed=s, depth=4).monsters))
        self.assertFalse(any(m.kind == "daemon" for s in range(4) for m in self.floor(seed=s).monsters))

    def test_how_deep_comes_from_a_game_variable(self):
        data = with_level({"generate": dict(self.SPEC, depth="swap_depth")})
        self.assertEqual(level_depth(data, "t", {"swap_depth": 3}), 3)
        self.assertEqual(level_depth(data, "t", {}), 0)
        lv = Level(data, "t", seed=2, depth=3)
        self.assertIn(("floor 4", "info"), lv.intro_lines())
        self.assertEqual(resume(data, lv.save_block())[0].depth, 3)


class CheckTests(unittest.TestCase):
    def check(self, spec):
        return [p for p in validate(with_level(spec)) if "'t'" in p]

    def test_good_ones_pass(self):
        self.assertEqual(self.check({"world": DUNGEON}), [])
        self.assertEqual(self.check({"world": LAND}), [])
        self.assertEqual(self.check({"generate": DungeonFloorTests.SPEC}), [])

    def test_what_is_wrong(self):
        text = " | ".join(self.check({"world": {"kind": "cave", "awake": 40, "spawns": [{"monster": "dragon"}],
                                                 "sites": [{"name": "big", "chance": 0.1, "map": ["#" * 20] * 3},
                                                           {"name": "lost", "map": ["#"]}]}}))
        for bit in ("kind should be", "awake should be", "unknown monster 'dragon'", "fits in 14 x 14",
                    "needs an \"at\" or a \"chance\""):
            self.assertIn(bit, text)
        text = " | ".join(self.check({"world": {"kind": "land", "sites": []}, "map": ["@E"]}))
        self.assertIn("no exit", text)
        self.assertIn("leave \"map\" out", text)
        text = " | ".join(self.check({"generate": {"type": "maze", "size": [5, 5], "key": {"door": "Q"},
                                                    "monsters": [{"monster": "dragon"}]}}))
        for bit in ("type should be", "size should be", "key should be", "unknown monster dragon"):
            self.assertIn(bit, text)


class SimulatronTests(unittest.TestCase):
    def test_the_programs_check_out_and_are_scenes(self):
        data = GameData(ROOTLESS)
        self.assertEqual([p for p in validate(data) if "sim" in p], [])
        scenes = {s.get("level"): k for k, s in data.scenes.items() if s.get("level")}
        for lid in ("sim1", "sim2", "sim3"):
            self.assertIn(lid, scenes)

    def test_the_bot_runs_them(self):
        data = GameData(ROOTLESS)
        for lid, seed in (("sim1", 3), ("sim2", 1), ("sim3", 2)):
            outcome, lv = levelbot.play(data, lid, seed)
            self.assertEqual(outcome, "exit", "%s seed %d" % (lid, seed))

    def test_deep_swap_goes_down_a_floor_at_a_time(self):
        from unittest import mock
        from engine import level as level_mod
        from engine.audio import Silent
        from engine.game import Game
        from engine.term import Term
        term = Term(out=io.StringIO(), inp=lambda p: "", width=80, height=24, color=0, unicode=True, animate=False, env={})
        g = Game(ROOTLESS, term=term, audio=Silent())
        played = []

        def run(lv, console):
            played.append((lv.id, lv.depth, lv.seed))
            if len(played) == 3:
                return "dead"
            lv.exit_kind = "exit"
            return "exit"
        with mock.patch.object(level_mod.Level, "run", run):
            level_mod.play_scene(g, g.world.scenes["sim_deep_swap"])
        self.assertEqual([(i, d) for i, d, _s in played], [("sim2", 0), ("sim2", 1), ("sim2", 2)])
        self.assertEqual(len({s for _i, _d, s in played}), 3)              # a new floor every time
        self.assertEqual(g.world.vars["swap_depth"], 2)
        self.assertIn("next floor", term.out.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
