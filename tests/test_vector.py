# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Vector displays (engine/vector.py): shapes whose faces look outward, the eye and where points show,
lines cut at the eye and at the display's rim, wire frames and solid ones (hidden lines), one thing
hiding another, ground hiding what is behind it, afterglow, dimming by distance, strokes for terminals
without braille, words that follow points, CLIo's models as lines, and the reel's scenes."""
import io
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from engine import vector as V  # noqa: E402
from engine.vector import Camera, Scope  # noqa: E402


def lit(scope):
    return sum(1 for v in scope.light if v > 0)


def on(scope, x, y):
    return 0 <= int(x) < scope.W and 0 <= int(y) < scope.H and scope.light[int(y) * scope.W + int(x)] > 0


class ShapeTests(unittest.TestCase):
    def test_faces_look_outward(self):
        for name, w in (("box", V.box((1, 2, 3))), ("tube", V.tube()), ("cone", V.tube(taper=0.4)),
                        ("globe", V.globe(2.0, 4, 10))):
            for f in w.faces:
                a, b, c = w.verts[f[0]], w.verts[f[1]], w.verts[f[2]]
                n = V._cross(V._sub(b, a), V._sub(c, a))
                mid = [sum(w.verts[i][k] for i in f) / len(f) for k in range(3)]
                self.assertGreater(V._dot(n, mid), 0, name)
            self.assertTrue(all(len(s) == 2 for s in w.sides()), name)      # every line between two faces

    def test_counts_and_placing(self):
        b = V.box((2, 2, 2))
        self.assertEqual((len(b.verts), len(b.edges), len(b.faces)), (8, 12, 6))
        self.assertEqual(len(V.grid(4, 3).edges), 9)
        self.assertEqual(len(V.ring(1, 12).edges), 12)
        p = V.box((2, 2, 2)).placed(at=(10, 0, 0), yaw=90, scale=2)
        xs = sorted(v[0] for v in p.verts)
        self.assertAlmostEqual(xs[0], 8.0)
        self.assertAlmostEqual(xs[-1], 12.0)
        self.assertEqual(V.turned((1, 0, 0), yaw=90)[1], 1.0)                # yaw turns to the left
        self.assertAlmostEqual(V.turned((0, 1, 0), pitch=90)[2], 1.0)        # pitch lifts the nose
        both = b + V.ring(1, 6)
        self.assertEqual((len(both.verts), len(both.edges), len(both.faces)), (14, 18, 6))
        self.assertEqual(V.box().lit("amber", 0.5).bright, 0.5)

    def test_an_orbit_has_its_focus_at_the_origin(self):
        near, far = V.on_orbit(4, 0.25, 0.5), V.on_orbit(4, 0.25, 0.0)
        self.assertAlmostEqual(near[0], -3.0)
        self.assertAlmostEqual(far[0], 5.0)
        self.assertEqual(len(V.orbit(4, 0.25, 32).edges), 32)

    def test_triangles_become_outlines(self):
        square = V.from_triangles([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 1, 2), (0, 2, 3)])
        self.assertEqual(len(square.edges), 4)                               # not the line across it
        v = V.box().verts
        tris = []
        for f in V.box().faces:
            tris += [(f[0], f[1], f[2]), (f[0], f[2], f[3])]
        self.assertEqual(len(V.from_triangles(v, tris).edges), 12)
        self.assertEqual(len(V.from_triangles(v, tris, crease=0).edges), 18)


class EyeTests(unittest.TestCase):
    def test_where_points_show(self):
        s = Scope(40, 10)
        cam = Camera(eye=(0, -10, 0), look=(0, 0, 0), fov=90)
        x, y, w = s.project(cam, (0, 0, 0))
        self.assertEqual((x, y), (40.0, 20.0))
        self.assertAlmostEqual(w, 0.1)
        self.assertGreater(s.project(cam, (1, 0, 0))[0], 40)                 # to the right
        self.assertLess(s.project(cam, (0, 0, 1))[1], 20)                    # up is up
        self.assertAlmostEqual(s.project(cam, (10, 0, 0))[0], 80.0)          # the rim, at 90 degrees
        self.assertIsNone(s.project(cam, (0, -11, 0)))                       # behind the eye
        tipped = Camera(eye=(0, -10, 0), look=(0, 0, 0), fov=90, roll=90)
        self.assertAlmostEqual(s.project(tipped, (1, 0, 0))[0], 40.0)
        down = Camera(eye=(0, 0, 10), look=(0, 0, 0))                        # straight down: still a picture
        self.assertEqual(s.project(down, (0, 0, 0))[:2], (40.0, 20.0))

    def test_a_line_is_cut_at_the_eye_and_at_the_rim(self):
        s = Scope(40, 10)
        cam = Camera(eye=(0, 0, 0), look=(0, 1, 0), fov=90)
        s.clear()
        s.line(cam, (0.0, -5, -1), (0.0, 5, -1))                             # from behind the eye to ahead
        self.assertGreater(lit(s), 5)
        self.assertTrue(on(s, 40, 30))
        s.clear()
        s.line(cam, (-5000, 5, 0), (5000, 5, 0))                             # far past both rims
        self.assertEqual(lit(s), s.W)
        s.clear()
        s.line(cam, (0, -3, 0), (1, -2, 0))                                  # all of it behind
        s.line2(-50, -9, -5, -2)                                             # all of it off the display
        self.assertEqual(lit(s), 0)


class HidingTests(unittest.TestCase):
    def setUp(self):
        self.cam = Camera(eye=(4.5, -6, 3.75), look=(0, 0, 0), fov=40)
        self.box = V.box((2, 2, 2))

    def test_a_solid_box_shows_nine_of_its_twelve_lines(self):
        wire, solid = Scope(60, 20), Scope(60, 20)
        wire.clear()
        wire.render(self.cam, [self.box])
        solid.clear()
        solid.render(self.cam, [self.box], solid=True)
        self.assertLess(lit(solid), lit(wire))
        x, y, _ = wire.project(self.cam, (-1, 1, -1))                        # the corner at the back
        self.assertTrue(on(wire, x + 0.5, y + 0.5))
        self.assertFalse(on(solid, x + 0.5, y + 0.5))
        for corner in ((1, -1, 1), (1, -1, -1), (-1, -1, 1), (1, 1, 1)):     # those in front are there
            x, y, _ = solid.project(self.cam, corner)
            self.assertTrue(on(solid, x + 0.5, y + 0.5), corner)

    def test_one_thing_hides_another(self):
        far = V.ring(0.6, 16, "y").placed(at=(-1.5, 2.5, -1.2))
        s = Scope(40, 12)
        s.clear()
        s.render(self.cam, [far])
        alone = lit(s)
        s.clear()
        s.render(self.cam, [self.box, far], solid=True)
        s2 = Scope(40, 12)
        s2.clear()
        s2.render(self.cam, [self.box], solid=True)
        self.assertLess(lit(s) - lit(s2), alone)                             # part of the ring is behind the box
        s.clear()
        s.render(self.cam, [self.box, far])                                  # as wire frames nothing hides
        self.assertGreater(lit(s), lit(s2) + alone - 12)

    def test_ground_hides_what_lies_behind_a_ridge(self):
        hs = [[2.0 if j == 4 else 0.0 for _ in range(12)] for j in range(10)]
        ground = V.terrain(hs, (0.6, 0.8), lines="rows")
        cam = Camera(eye=(0, -9, 1.0), look=(0, 0, 0.6), fov=50)
        wire, solid = Scope(60, 20), Scope(60, 20)
        wire.clear()
        wire.render(cam, [ground])
        solid.clear()
        solid.render(cam, [ground], solid=True)
        self.assertLess(lit(solid), lit(wire) * 0.7)
        x, y, _ = solid.project(cam, (0.3, 2.4, 0.0))                        # a row beyond the ridge
        self.assertTrue(on(wire, x, y) or on(wire, x, y + 1) or on(wire, x, y - 1))
        self.assertFalse(on(solid, x, y) or on(solid, x, y + 1) or on(solid, x, y - 1))
        self.assertEqual(len(V.terrain(hs, 1.0, lines="both").edges), 10 * 11 + 9 * 12)
        self.assertEqual(len(V.terrain(hs, 1.0, lines="columns").edges), 9 * 12)

    def test_a_face_cut_by_the_eye_still_hides(self):
        s = Scope(40, 12)
        cam = Camera(eye=(0, 0, 0.5), look=(0, 1, 0.5), fov=70)
        floor = V.Wire([(-2, -3, 0), (2, -3, 0), (2, 8, 0), (-2, 8, 0)], [], [(0, 1, 2, 3)])
        under = V.polyline([(-1, 4, -1), (1, 4, -1)])
        s.clear()
        s.render(cam, [floor, under], solid=True)
        self.assertEqual(lit(s), 0)


class LightTests(unittest.TestCase):
    def test_afterglow_fades_and_does_not_thicken_a_fresh_line(self):
        s = Scope(20, 5, afterglow=0.5)
        s.clear()
        s.line2(0, 9, 39, 9)
        self.assertEqual(s.light[9 * s.W + 5], 1.0)
        s.clear()
        self.assertEqual(s.light[9 * s.W + 5], 0.5)
        s.line2(0, 10, 39, 10)                                               # a new line right under the old
        cell = s.rows()[2][2]
        self.assertEqual(cell[0], chr(0x2800 + 4 + 32))                      # only the fresh row of dots
        for _ in range(4):
            s.clear()
        self.assertEqual(lit(s), 0)
        plain = Scope(20, 5)
        plain.line2(0, 9, 39, 9)
        plain.clear()
        self.assertEqual(lit(plain), 0)

    def test_lines_dim_with_distance_and_brighten_where_they_cross(self):
        s = Scope(40, 12, cue=(5.0, 15.0), dim=0.25)
        cam = Camera(eye=(0, 0, 0), look=(0, 1, 0), fov=60)
        s.clear()
        s.line(cam, (-1, 5, 1), (1, 5, 1))
        s.line(cam, (-3, 15, -3), (3, 15, -3))
        near, far = max(s.light[:s.W * 20]), max(s.light[s.W * 28:])
        self.assertAlmostEqual(near, 1.0)
        self.assertAlmostEqual(far, 0.25)
        s.clear()
        s.line2(0, 20, 79, 20)
        s.line2(40, 0, 40, 47)
        self.assertGreater(s.light[20 * s.W + 40], 1.0)
        self.assertGreater(s.tone((70, 255, 140), 1.6)[0], s.tone((70, 255, 140), 1.0)[0])   # towards white
        self.assertLess(s.tone((70, 255, 140), 0.3)[1], s.tone((70, 255, 140), 1.0)[1])

    def test_colours(self):
        self.assertEqual(V.colour_of("amber"), (255, 176, 40))
        self.assertEqual(V.colour_of("#102030"), (16, 32, 48))
        self.assertEqual(V.colour_of("no such"), (70, 255, 140))
        s = Scope(10, 3, colour="cyan", glow=False)
        s.line2(0, 5, 19, 5, colour="red")
        row = s.rows()[1]
        self.assertEqual(row[0][1], s.tone(V.COLOURS["red"], 1.0))
        self.assertIsNone(row[0][2])
        s2 = Scope(10, 3, paper=(0, 0, 0))
        s2.line2(0, 5, 19, 5)
        self.assertNotEqual(s2.rows()[1][0][2], (0, 0, 0))                   # a lit character glows a little
        self.assertEqual(s2.rows()[0][0], (" ", None, (0, 0, 0)))


class PictureTests(unittest.TestCase):
    def test_rows_are_cells_and_strokes_follow_the_lines(self):
        s = Scope(12, 4)
        s.line2(0, 6, 23, 6)                                                 # flat
        s.line2(11, 0, 11, 15)                                               # upright, crossing it
        s.line2(0, 15, 6, 9)                                                 # rising to the right
        rows = s.rows("strokes")
        self.assertEqual((len(rows), len(rows[0])), (4, 12))
        self.assertEqual(rows[1][1][0], "─")
        self.assertEqual(rows[0][5][0], "│")
        self.assertEqual(rows[1][5][0], "┼")
        self.assertEqual(rows[3][0][0], "╱")
        text = s.plain()
        self.assertTrue(text.isascii())
        self.assertIn("-", text)
        self.assertIn("|", text)
        self.assertIn("+", text)
        self.assertIn("/", text)
        dots = s.rows("dots")
        self.assertTrue(0x2800 < ord(dots[1][1][0]) <= 0x28FF)

    def test_words_over_the_picture_and_beside_points(self):
        s = Scope(40, 10)
        cam = Camera(eye=(0, -10, 0), look=(0, 0, 0), fov=90)
        s.clear()
        s.text(1, 0, "RANGE 12", "amber")
        s.label(cam, (0, 0, 0), "EREBUS")
        s.label(cam, (0, -20, 0), "BEHIND")
        s.label(cam, (50, 0, 0), "OFF")
        text = s.plain()
        self.assertIn("RANGE 12", text.splitlines()[0])
        self.assertEqual(text.splitlines()[5][21:27], "EREBUS")
        self.assertNotIn("BEHIND", text)
        self.assertNotIn("OFF", text)
        self.assertEqual(s.rows()[0][1][1], s.tone(V.COLOURS["amber"], 1.0))
        s.clear()
        self.assertNotIn("RANGE", s.plain())

    def test_a_circle_on_the_glass(self):
        s = Scope(20, 10)
        s.circle2(20, 20, 8)
        self.assertTrue(on(s, 28, 20) and on(s, 12, 20) and on(s, 20, 12) and on(s, 20, 28))
        self.assertFalse(on(s, 20, 20))


class ModelTests(unittest.TestCase):
    def test_clios_models_are_drawn_in_lines(self):
        from engine.data import GameData
        from engine import model
        models = model.load(GameData(os.path.join(ROOT, "games", "rootless")).models)
        hopper = models["hopper"]
        wire = V.from_model(hopper)
        self.assertGreater(len(wire.edges), 20)
        self.assertLess(len(wire.edges), len(hopper.faces) * 3 // 2)         # outlines, not every triangle
        cam = Camera(eye=(2.2, -2.6, 1.6), look=(0, 0, 0.4), fov=45)
        a, b = Scope(60, 20), Scope(60, 20)
        a.clear()
        a.render(cam, [wire])
        b.clear()
        b.render(cam, [wire], solid=True)
        self.assertGreater(lit(b), 100)
        self.assertLess(lit(b), lit(a))


class ReelTests(unittest.TestCase):
    def test_every_scene_draws_the_same_twice_and_fits(self):
        for name in V.SCENES:
            pictures = []
            for _ in range(2):
                s = Scope(78, 22)
                s.clear()
                caption = V.scene(name, 7.5, s)
                pictures.append(s.plain("dots", True))
                self.assertTrue(caption)
                self.assertGreater(lit(s), 300, name)
            self.assertEqual(pictures[0], pictures[1], name)
            self.assertLessEqual(max(len(l) for l in pictures[0].splitlines()), 78, name)
            s = Scope(40, 12)
            s.clear()
            V.scene(name, 2.0, s)
            self.assertTrue(s.plain().isascii(), name)

    def test_the_hauler_is_wire_then_solid(self):
        counts = []
        for t in (2.0, 8.0):                                                 # the same turn of the ship: 24 * 15 = 360
            s = Scope(78, 22)
            s.cue = None
            s.clear()
            V.scene("hauler", t + (15.0 if t > 6 else 0.0), s)
            counts.append(lit(s))
        self.assertGreater(len(V.hauler().edges), 100)

    def test_a_scene_from_the_command_line(self):
        out, old = io.StringIO(), sys.stdout
        sys.stdout = out
        try:
            self.assertEqual(V.main(["scan", "2"]), 0)
            self.assertEqual(V.main([]), 2)                                  # not a terminal: how to use it
        finally:
            sys.stdout = old
        text = out.getvalue()
        self.assertIn("SURFACE SCAN", text)
        self.assertIn("python -m engine.vector", text)
        self.assertTrue(text.isascii())

    def test_a_frame_is_quick_enough_to_animate(self):
        import time
        s = Scope(80, 24)
        t0 = time.time()
        for name in V.SCENES:
            s.clear()
            V.scene(name, 3.0, s)
            s.rows()
        self.assertLess((time.time() - t0) / len(V.SCENES), 0.5)             # generous: a slow machine, under tests


if __name__ == "__main__":
    unittest.main()
