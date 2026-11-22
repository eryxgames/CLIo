# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Ground that is not flat, and ways over it: sloped floors and ceilings (ramps, a sewer tube) in the mesh view,
wet slopes slid down, jumps and jumps again in the air, a pressure suit and a vacuum, and how the view moves with
each step (a gait: a walk, a suit, a walking machine). RØØTLESS SIM-13 Proving Ground has all of it."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from engine import mesh  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.firstperson import FX, View  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import ROOTLESS, Quiet, put, with_level  # noqa: E402

ROOM = ["##########",
        "#........#",
        "#.WWW....#",
        "#.WWW..H.#",
        "#.....__.#",
        "#.P.ppp..#",
        "#..L.....#",
        "#....@...#",
        "##########"]
LEGEND = {"W": {"slope": "n", "rise": 0.5, "wet": True}, "P": {"pit": True}, "p": {"pit": True},
          "H": {"height": 1.4}, "_": {"height": 0.7}, "L": {"height": 0.8}}
RAMP = ["#######",
        "#GGGGG#",
        "#.RRR.#",
        "#.rrr.#",
        "#.....#",
        "#..@..#",
        "#######"]
RAMP_LEGEND = {"R": {"slope": "n", "rise": 0.4, "height": 0.6}, "r": {"slope": "n", "rise": 0.4, "height": 0.2},
               "G": {"height": 0.8}}


class Frames(Quiet):
    """A console that keeps the frames of each animation played."""

    def __init__(self):
        super().__init__()
        self.played = []

    def play(self, lv, frames, dt):
        self.played.append((list(frames), dt))


def level(rows=ROOM, legend=LEGEND, **more):
    spec = {"map": rows, "legend": legend, "render": "mesh", "jump": True}
    spec.update(more)
    lv = Level(with_level(spec), "t", seed=1)
    lv.console = Frames()
    return lv


class SlopeTests(unittest.TestCase):
    def test_a_slope_rises_across_its_cell(self):
        lv = level(RAMP, RAMP_LEGEND)
        self.assertTrue(lv.heights and lv.slopes)
        r, R = lv.cell(3, 3), lv.cell(3, 2)
        for got, want in zip((r.edge(2), r.edge(0), R.edge(2), R.edge(0)), (0.0, 0.4, 0.4, 0.8)):
            self.assertAlmostEqual(got, want)
        self.assertEqual(r.edge(1), 0.2)                          # across it: its middle
        self.assertAlmostEqual(lv.floor_at(3, 3.5), 0.0)            # on the plane, exactly
        self.assertAlmostEqual(lv.floor_at(3, 3.25), 0.1)
        self.assertAlmostEqual(lv.floor_at(3, 2.0), 0.6)
        self.assertAlmostEqual(lv.floor_at(3, 4.0), 0.0)            # flat beside it
        self.assertFalse(level(RAMP).slopes)

    def test_up_a_ramp_but_not_up_its_side(self):
        lv = level(RAMP, RAMP_LEGEND)
        self.assertTrue(lv.step_ok(3, 4, 3, 3) and lv.step_ok(3, 3, 3, 2) and lv.step_ok(3, 2, 3, 1))
        self.assertFalse(lv.step_ok(1, 2, 2, 2))                     # on to its side, 0.6 up: a step too high
        self.assertTrue(lv.step_ok(2, 3, 1, 3))                      # off its side, down: any
        put(lv, 3, 5, 0)
        for _ in range(4):
            lv.run_line("k")
        self.assertEqual((lv.player.x, lv.player.y), (3, 1))         # up the ramp to the gallery
        steep = level(RAMP, {"R": {"slope": "n", "rise": 1.4, "height": 0.7}, "r": {}})
        self.assertFalse(steep.step_ok(3, 3, 3, 2))                  # a slope too steep to walk up

    def test_monsters_walk_ramps_too(self):
        lv = level(RAMP, dict(RAMP_LEGEND, z="zombie"))
        dist = lv.distances(3, 1, limit=20)                          # the player up on the gallery
        self.assertEqual(dist.get((3, 5)), 4)                        # a monster below comes up the ramp
        self.assertIsNone(level(RAMP, {"R": {"height": 0.8}, "r": {"height": 0.8}, "G": {"height": 0.8}}).distances(
            3, 1, limit=20).get((3, 5)))                             # a block as high: no way up

    def test_the_mesh_draws_a_slope_and_its_sides(self):
        lv = level(RAMP, RAMP_LEGEND)
        put(lv, 3, 5, 0)
        v = View(60, 18, "pixel", "high")
        v.use_frame = False
        sloped = v.render(lv, FX(hands=False), 1)
        flat = level(RAMP)
        put(flat, 3, 5, 0)
        self.assertNotEqual(sloped, v.render(flat, FX(hands=False), 1))
        m = mesh.Mesh(v)
        cam = (1.0, 5.0, 0.0, -1.0, 1.0, 0.0)                       # from beside it: its sides face the camera
        faces = m.faces(lv, cam, v.EYE, {}, 1, 1.0, 5.0 + mesh.Z0)
        ramp = [f for f in faces if f.kind == mesh.FLOOR and (f.ix, f.iy) == (3, 3)][0]
        self.assertEqual((ramp.gx, ramp.gy), (0.0, -0.4))           # rising north: y going down
        self.assertEqual(sorted(h for _x, _y, h in ramp.corners()), [0.0, 0.0, 0.4, 0.4])
        sides = [f for f in faces if f.kind == mesh.XWALL and f.h0b != f.h0 or
                 f.kind == mesh.XWALL and f.h1b != f.h1]
        self.assertTrue(sides)                                       # the ramp's sides: their tops slope

    def test_a_tube_with_sloped_sides(self):
        rows = ["#####", "#ltr#", "#ltr#", "#ltr#", "#.@.#", "#####"]
        legend = {"l": {"height": 0.15, "slope": "w", "rise": 0.3, "ceiling_slope": "e", "ceiling_rise": 0.5,
                        "ceiling_height": 1.05},
                  "r": {"height": 0.15, "slope": "e", "rise": 0.3, "ceiling_slope": "w", "ceiling_rise": 0.5,
                        "ceiling_height": 1.05},
                  "t": {"ceiling_height": 1.4}}
        lv = level(rows, legend)
        self.assertAlmostEqual(lv.ceiling_at(1, 2), 1.05)
        self.assertAlmostEqual(lv.ceiling_at(1.4, 2), 1.25)
        put(lv, 2, 4, 0)
        lv.run_line("k")
        lv.run_line("h")                                             # into the side: up its gentle slope
        self.assertEqual((lv.player.x, lv.player.y), (1, 3))
        v = View(60, 18, "pixel", "high")
        v.use_frame = False
        cells = v.render(lv, FX(hands=False), 1)
        self.assertEqual(len(cells), 18)
        self.assertEqual([p for p in validate(with_level({"map": rows, "legend": legend, "render": "mesh"}))
                          if "slope" in p or "rise" in p], [])


class WetTests(unittest.TestCase):
    def test_a_wet_slope_slides_him_down(self):
        lv = level()
        put(lv, 3, 4, 0)
        lv.run_line("k")                                             # up on to it: back down
        self.assertEqual((lv.player.x, lv.player.y, lv.beat), (3, 4, 1))
        self.assertIn("slide back down", lv.console.told[-1])
        put(lv, 3, 1, 2)
        lv.run_line("k")                                             # down on to it from the top: to the foot
        self.assertEqual((lv.player.x, lv.player.y), (3, 4))
        lv.player.magboots = lv.player.mag_on = True                 # magboots grip
        put(lv, 3, 4, 0)
        lv.run_line("k")
        self.assertEqual((lv.player.x, lv.player.y), (3, 3))

    def test_rain_wets_slopes_under_the_sky(self):
        legend = dict(LEGEND, W={"slope": "n", "rise": 0.5, "sky": True})
        dry = level(legend=legend)
        put(dry, 3, 4, 0)
        dry.run_line("k")
        self.assertEqual((dry.player.x, dry.player.y), (3, 3))       # dry: walked up
        wet = level(legend=legend, weather={"kind": "rain", "amount": 0.7})
        self.assertTrue(wet.slippery(wet.cell(3, 3)))
        put(wet, 3, 4, 0)
        wet.run_line("k")
        self.assertEqual((wet.player.x, wet.player.y), (3, 4))
        space = level(legend=dict(legend, W={"slope": "n", "rise": 0.5, "sky": True, "vacuum": True}),
                      weather={"kind": "rain", "amount": 0.7})
        self.assertFalse(space.slippery(space.cell(3, 3)))           # no air, no rain

    def test_a_slide_into_a_drop(self):
        rows = ["#####", "#.p.#", "#.W.#", "#.@.#", "#####"]
        lv = level(rows, {"p": {"pit": True}, "W": {"slope": "s", "rise": 0.4, "wet": True}})
        put(lv, 2, 3, 0)
        lv.run_line("k")
        self.assertEqual(lv.over, "dead")


class JumpTests(unittest.TestCase):
    def test_over_a_gap_and_up_on_to_a_ledge(self):
        lv = level()
        put(lv, 4, 6, 0)
        lv.run_line("jump")
        self.assertEqual((lv.player.x, lv.player.y, lv.beat), (4, 4, 1))      # over the pit
        lv = level()
        put(lv, 3, 7, 0)
        lv.run_line("k")
        self.assertEqual((lv.player.x, lv.player.y), (3, 7))         # 0.8 up: too high a step
        lv.run_line("jump")
        self.assertEqual((lv.player.x, lv.player.y), (3, 6))         # up on to it, not over it
        lv = level()
        put(lv, 7, 5, 0)
        lv.run_line("jump")
        lv.run_line("jump")
        self.assertEqual((lv.player.x, lv.player.y), (7, 3))         # 0.7, then 1.4

    def test_jumping_again_in_the_air(self):
        rows = ["#########", "#.......#", "#...H...#", "#.p.....#", "#.p.....#", "#.@.....#", "#########"]
        legend = {"p": {"pit": True}, "H": {"height": 1.6}}
        lv = level(rows, legend)
        put(lv, 2, 5, 0)
        lv.run_line("jump")
        self.assertEqual((lv.player.x, lv.player.y), (2, 5))         # two wide: once is not enough
        self.assertIn("Nowhere to land", lv.console.told[-1])
        lv.run_line("jj")
        self.assertEqual((lv.player.x, lv.player.y), (2, 2))
        lv = level(rows, legend)
        put(lv, 4, 3, 0)
        lv.run_line("jump")
        self.assertEqual((lv.player.x, lv.player.y), (4, 3))         # 1.6 up: no
        lv.run_line("jump jump")
        self.assertEqual((lv.player.x, lv.player.y), (4, 2))         # twice as high
        once = level(rows, legend, jump={"double": False})
        put(once, 4, 3, 0)
        once.run_line("jj")
        self.assertIn("once is all you get", once.console.told[-2])

    def said(self, lv, line, at):
        put(lv, *at)
        lv.run_line(line)
        return lv.console.told[-1]

    def test_what_stops_a_jump(self):
        self.assertIn("cannot jump here", self.said(level(jump=False), "jump", (4, 6, 0)))
        suited = level()
        suited.player.suit = True
        self.assertIn("pressure suit", self.said(suited, "jump", (4, 6, 0)))
        low = level(legend=dict(LEGEND, **{".": {"ceiling_height": 0.7}, "@": {"start": True,
                                                                                "ceiling_height": 0.7}}))
        self.assertIn("No room to jump", self.said(low, "jump", (4, 6, 0)))
        walled = level(["#####", "#...#", "###.#", "#.@.#", "#####"], {})
        self.assertIn("Nowhere to land", self.said(walled, "jump", (2, 3, 0)))
        lv = level(["#####", "#...#", "#.z.#", "#.@.#", "#####"], {"z": "zombie"})
        self.assertIn("Nowhere to land", self.said(lv, "jump", (2, 3, 0)))

    def test_a_long_way_down_hurts(self):
        rows = ["#####", "#...#", "#...#", "#.H.#", "#####"]
        lv = level(rows, {"H": {"height": 2.4, "ceiling_height": 3.6}, ".": {"ceiling_height": 3.6}})
        put(lv, 2, 3, 0)
        lv.run_line("jump")
        self.assertEqual((lv.player.x, lv.player.y), (2, 1))
        self.assertLess(lv.player.hp, 100)

    def test_the_jump_is_an_arc_under_the_ceiling(self):
        lv = level()
        put(lv, 4, 6, 0)
        lv.run_line("jump")
        frames, _dt = lv.console.played[-1]
        eyes = [f.eye for f in frames]
        base = 1 / 1.92
        self.assertGreater(max(eyes), base + 0.2)
        self.assertLess(max(eyes), 1.0)                              # the ceiling at 1: not through it
        self.assertAlmostEqual(eyes[-1], base, places=6)
        self.assertEqual(frames[-1].shake, 1)                        # the landing


class GaitTests(unittest.TestCase):
    def step_frames(self, lv):
        put(lv, 8, 7, 0)
        lv.run_line("k")
        return lv.console.played[-1]

    def test_plain_steps_do_not_bob_unless_asked(self):
        frames, dt = self.step_frames(level())
        self.assertTrue(all(f.eye is None and f.bob is None for f in frames))
        frames, dt = self.step_frames(level(headbob=True))
        self.assertTrue(all(f.eye is not None for f in frames))
        self.assertGreater(max(f.eye for f in frames) - min(f.eye for f in frames), 0.015)

    def test_a_pressure_suit_walks_heavily(self):
        lv = level(headbob=False)
        lv.player.suit = True
        self.assertEqual(lv.gait(), "suit")
        frames, dt = self.step_frames(lv)
        self.assertEqual((len(frames), dt), (6, 0.045))             # slower
        self.assertGreater(max(f.eye for f in frames) - min(f.eye for f in frames), 0.05)
        sway = [f.cam[0] - 8 for f in frames]                       # facing north: the sway is across, in x
        self.assertGreater(max(abs(s) for s in sway), 0.02)
        self.assertTrue(any(f.bob and f.bob[0] for f in frames))     # the hands with it
        lv.run_line("k")
        second = lv.console.played[-1][0][2].cam[0] - 8
        self.assertLess(sway[2] * second, 0)                         # the other foot: the other way

    def test_a_walking_machine_shakes_the_deck(self):
        rows = ["#######", "#.....#", "#.....#", "#..M..#", "#..@..#", "#######"]
        lv = level(rows, {"M": "mechwalker"})
        put(lv, 3, 4, 0)
        lv.run_line("k")                                             # into it: aboard
        self.assertIsNotNone(lv.player.vehicle)
        self.assertEqual(lv.gait(), "mech")
        lv.run_line("k")
        frames, dt = lv.console.played[-1]
        self.assertIn(frames[-1].shake, (1, -1))
        self.assertGreater(min(f.eye for f in frames), 0.7)          # up in the cab
        v = View(60, 18, "pixel", "high")
        v.use_frame = False
        self.assertEqual(len(v.render(lv, frames[2], 1)), 18)

    def test_a_vacuum_without_a_suit(self):
        rows = ["#####", "#vvv#", "#vvv#", "#.@.#", "#####"]
        lv = level(rows, {"v": {"vacuum": True, "sky": True}})
        put(lv, 2, 3, 0)
        lv.run_line("k")
        self.assertLess(lv.player.hp, 100)
        suited = level(rows, {"v": {"vacuum": True, "sky": True}})
        suited.player.suit = True
        put(suited, 2, 3, 0)
        suited.run_line("k")
        suited.run_line("w 3")
        self.assertEqual(suited.player.hp, 100)


class CheckTests(unittest.TestCase):
    def test_check_says_what_is_wrong(self):
        legend = {"a": {"slope": "up"}, "b": {"slope": "n", "rise": 5}, "c": {"rise": 0.3}, "d": {"wet": "yes"},
                  "e": {"ceiling_slope": "e", "ceiling_rise": -1}}
        rows = ["#######", "#abcde#", "#..@..#", "#######"]
        text = "\n".join(validate(with_level({"map": rows, "legend": legend, "jump": {"far": 9, "high": 7},
                                              "headbob": "on"})))
        self.assertIn("'a' slope should be n, e, s or w", text)
        self.assertIn("'b' rise should be a number over 0, up to 3", text)
        self.assertIn("'c' has rise but no slope", text)
        self.assertIn("'d' wet should be true or false", text)
        self.assertIn("'e' ceiling_rise should be a number over 0", text)
        self.assertIn("jump far should be 1 to 4 cells", text)
        self.assertIn("jump high should be over 0, up to 3", text)
        self.assertIn("headbob should be true or false", text)


class ProvingGroundTests(unittest.TestCase):
    def test_sim13_can_be_walked(self):
        """Through RØØTLESS SIM-13 without its monsters: the ramp, the tube, a slide down the wet slope, jumps and
        double jumps over the pits and up the ledge, the suit on the vacuum deck, the switch, the mechwalker up
        on to its platform and out."""
        lv = Level(GameData(ROOTLESS), "sim13", seed=1)
        lv.console = Quiet()
        self.assertEqual(validate(lv.data), [])
        lv.monsters = [m for m in lv.monsters if m.vehicle]
        route = [("k", None)] * 14 + [("k", (5, 3)), ("tr", None), ("k", (6, 3)), ("k", (7, 3)), ("jump", (9, 3)),
                                      ("k", (10, 3)), ("jj", (13, 3)), ("tl", None), ("k", (13, 2)), ("tr", None),
                                      ("jj", (14, 2)), ("k", (15, 2)), ("use", None)]
        route += [("k", (x, 2)) for x in range(16, 22)] + [("use", None)] + [("k", (x, 2)) for x in range(22, 33)]
        route += [("tr", None), ("k", (32, 3)), ("tl", None), ("use", None), ("tl", None), ("k", (32, 2)),
                  ("tl", None)] + [("k", (x, 2)) for x in range(31, 18, -1)]
        route += [("tl", None)] + [("k", (19, y)) for y in range(3, 10)] + [("k", (19, 10))]
        route += [("tl", None)] + [("k", (x, 10)) for x in range(20, 33)]
        route += [("tr", None), ("k", (32, 11)), ("k", (32, 12)), ("tl", None), ("use", None)]
        for i, (line, at) in enumerate(route):
            lv.run_line(line)
            if at is not None:
                self.assertEqual((lv.player.x, lv.player.y), at, (i, line, lv.console.told[-3:]))
            if at == (20, 2):
                self.assertTrue(lv.player.suit)
            if at == (19, 10):
                self.assertIsNotNone(lv.player.vehicle)
        self.assertEqual(lv.over, "exit")
        self.assertEqual(lv.player.hp, 100)
        self.assertLess(lv.beat, 100)

    def test_sim13_is_a_free_program(self):
        import json
        scenes = json.load(open(os.path.join(ROOTLESS, "scenes.json"), encoding="utf-8"))
        self.assertTrue(any(s.get("level") == "sim13" for s in scenes))


if __name__ == "__main__":
    unittest.main()


def slopes_library(test):
    """Run with CLIo Picture 0.9 in use (skipped without it), and leave it as it was."""
    from engine import picture
    from engine.picture import frame as picture_frame

    def run(self):
        picture.use(True)
        if not picture_frame.slopes_ok():
            self.skipTest("CLIo Picture 0.9 is not here: %s" % picture.status())
        try:
            test(self)
        finally:
            picture.use(True)
    run.__name__, run.__doc__ = test.__name__, test.__doc__
    return run


class LibraryTests(unittest.TestCase):
    """CLIo Picture 0.9 draws slopes as the Python does, to the pixel."""

    def same(self, make, at, W=70, VR=20, style="pixel", detail="high", t=0.0):
        from engine import picture
        out = []
        for on in (False, True):
            picture.use(on)
            lv = make()
            put(lv, *at)
            lv.beat = int(t)
            v = View(W, VR, style, detail)
            v.use_frame = on
            out.append(v.render(lv, FX(tick=t - int(t)), 1))
        picture.use(True)
        self.assertEqual(out[0], out[1], (at, style, detail))

    @slopes_library
    def test_ramps_and_tubes_are_the_same(self):
        tube = ["#########", "###ltq###", "###ltq###", "###lcq###", "#GGGGGGG#", "#..RRR..#", "#..rrr..#",
                "#...@...#", "#########"]
        legend = dict(RAMP_LEGEND, l={"height": 0.95, "slope": "w", "rise": 0.3, "ceiling_height": 2.3,
                                      "ceiling_slope": "e", "ceiling_rise": 0.5},
                      q={"height": 0.95, "slope": "e", "rise": 0.3, "ceiling_height": 2.3, "ceiling_slope": "w",
                         "ceiling_rise": 0.5},
                      t={"height": 0.8, "ceiling_height": 2.6}, c={"height": 0.8, "ceiling_height": 2.6})
        legend["G"] = {"height": 0.8, "ceiling_height": 2.4}
        for at in ((4, 7, 0), (2, 6, 1), (4, 2, 0), (4, 3, 2)):
            for style, detail in (("pixel", "high"), ("pixel", "low"), ("dots", "high")):
                self.same(lambda: level(tube, legend), at, style=style, detail=detail)
                self.same(lambda: level(tube, legend, lights={"ambient": 0.6}), at, style=style, detail=detail)

    @slopes_library
    def test_the_proving_ground_is_the_same(self):
        data = GameData(ROOTLESS)

        def make():
            lv = Level(data, "sim13", seed=1)
            lv.console = Quiet()
            return lv
        for at in ((5, 19, 0), (5, 9, 0), (5, 3, 1), (13, 3, 0), (19, 6, 2), (24, 3, 3)):
            for t in (0.0, 2.45):
                self.same(make, at, W=80, VR=22, t=t)
