"""The mesh view (engine/mesh.py): rooms as faces in a true perspective, and floors at their own heights."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import mesh, picture  # noqa: E402
from engine.data import GameData  # noqa: E402
from engine.firstperson import FX, TEXTURES, View  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import ROOTLESS, Quiet, put, told, with_level  # noqa: E402

HALL = ["#########",
        "#.......#",
        "#.......#",
        "#.......#",
        "#.......#",
        "#.......#",
        "#...@...#",
        "#.......#",
        "#########"]


def room(rows, legend=None, seed=1, **more):
    spec = {"map": rows, "legend": legend or {}, "render": "mesh"}
    spec.update(more)
    lv = Level(with_level(spec), "t", seed=seed)
    lv.console = Quiet()
    return lv


def view(W=60, VR=20, frame=False, **kw):
    v = View(W, VR, "pixel", "high", **kw)
    v.use_frame = frame
    return v


def picture_of(lv, v=None):
    """The mesh's own picture of the level from the player: rows, distances, View."""
    v = v or view()
    v.set_eye_abs(lv.ground(lv.player.x, lv.player.y) + v.EYE0)
    v.persp = mesh.Z0
    from engine.firstperson import DIRS
    f = lv.player.facing
    cam = (lv.player.x, lv.player.y) + DIRS[f] + DIRS[(f + 1) % 4]
    rgb, zbuf, _cover, labels = mesh.Mesh(v).draw(lv, cam, v.EYE, 0, {}, None)
    return rgb, zbuf, v, labels


class PictureTests(unittest.TestCase):
    def test_the_wall_ahead_stands_where_open_lands_perspective_puts_it(self):
        lv = room(HALL)
        rgb, zbuf, v, _ = picture_of(lv)
        mid = v.PW // 2
        z = 6 - 0.5                                          # the north wall's face, 5.5 cells ahead of the player
        t = mesh.Z0 / (z + mesh.Z0)
        top, bottom = v.yh - v.CH * t, v.yh + v.FS * t      # View.front_face's rows in open land's perspective
        rows = [y for y in range(v.PH) if abs(zbuf[y * v.PW + mid] - z) < 1e-9]
        self.assertTrue(rows)
        self.assertLessEqual(abs(min(rows) - top), 1.0)
        self.assertLessEqual(abs(max(rows) + 1 - bottom), 1.0)

    def test_the_floor_is_as_far_off_as_its_row_says(self):
        lv = room(HALL)
        rgb, zbuf, v, _ = picture_of(lv)
        y = v.PH - 3
        d = (v.EYE - 0.0) * v.TALL * mesh.Z0 / (y + 0.5 - v.yh)    # a floor row's distance from the camera
        self.assertAlmostEqual(zbuf[y * v.PW + v.PW // 2], d - mesh.Z0, places=9)

    def test_a_pillar_hides_what_is_behind_it(self):
        open_ = room(HALL)
        pillar = room([r if i != 4 else "#...#...#" for i, r in enumerate(HALL)])
        _, za, v, _ = picture_of(open_)
        _, zb, _, _ = picture_of(pillar)
        mid = (v.PH // 2) * v.PW + v.PW // 2
        self.assertAlmostEqual(zb[mid], 6 - 4 - 0.5 - 0.0, places=9)    # its face, 1.5 cells ahead
        self.assertGreater(za[mid], zb[mid])

    def test_nothing_right_behind_the_player_covers_the_picture(self):
        a = room(HALL)
        b = room([r if i != 7 else "#...#...#" for i, r in enumerate(HALL)])   # a pillar at his back
        ra, _, _, _ = picture_of(a)
        rb, _, _, _ = picture_of(b)
        self.assertEqual(ra, rb)

    def test_a_monster_behind_a_pillar_is_hidden(self):
        rows = [r for r in HALL]
        rows[2] = "#...z...#"
        seen = room(rows, {"z": "zombie"})
        rows[4] = "#...#...#"
        hidden = room(rows, {"z": "zombie"})
        for lv, hides in ((seen, False), (hidden, True)):
            with_it = view().render(lv, FX(), 0)
            lv.monsters[0].gone = True
            without = view().render(lv, FX(), 0)
            self.assertEqual(with_it == without, hides)

    def test_classic_unless_someone_says_mesh(self):
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
        self.assertFalse(view().meshed(lv))
        self.assertTrue(view(render="mesh").meshed(lv))
        self.assertTrue(view(render_game="mesh").meshed(lv))
        lv.render = "mesh"                                    # the level's own wish
        self.assertTrue(view().meshed(lv))
        self.assertFalse(view(render="classic").meshed(lv))   # the player's choice wins

    def test_a_door_half_open_shows_what_is_under_it(self):
        rows = list(HALL)
        rows[4] = "####D####"
        lv = room(rows, {"D": {"door": True}})
        door = lv.cell(4, 4)
        _, shut, v, _ = picture_of(lv)
        door.open = 0.5
        _, half, _, _ = picture_of(lv)
        low = (v.yh + 9) * v.PW + v.PW // 2                   # under the raised panel: beyond the door
        high = (v.yh - 2) * v.PW + v.PW // 2
        z = 6 - 4 - 0.5
        self.assertAlmostEqual(shut[high], z, places=9)
        self.assertAlmostEqual(half[high], z, places=9)       # the panel's top still there
        self.assertGreater(half[low], shut[low])

    def test_labels_of_walls_close_by(self):
        rows = list(HALL)
        rows[4] = "####L####"
        lv = room(rows, {"L": {"locker": ["medkit"], "label": "07"}})
        _, _, _, labels = picture_of(lv)
        self.assertEqual([l[1] for l in labels], ["07"])
        cells = view().render(lv, FX(), 0)
        self.assertIn("07", "".join(c[0] or "" for row in cells for c in row))

    def test_the_frame_and_python_give_the_same_picture(self):
        if picture.load() is None:
            self.skipTest("CLIo Picture is not installed")
        data = GameData(ROOTLESS)
        for lid in ("e1m1", "e1m3"):
            lv = Level(data, lid, seed=2)
            a = view(80, 24, frame=False, render="mesh").render(lv, FX(), 1)
            b = view(80, 24, frame=True, render="mesh").render(lv, FX(), 1)
            self.assertEqual(a, b, lid)

    def test_every_rootless_room_level_draws_as_a_mesh(self):
        data = GameData(ROOTLESS)
        for lid in data.levels:
            lv = Level(data, lid, seed=3)
            if lv.land is not None:
                continue
            for style in ("pixel", "dots"):
                v = View(60, 18, style, "high", render="mesh")
                v.use_frame = False
                cells = v.render(lv, FX(), 0)
                self.assertEqual((len(cells), len(cells[0])), (18, 60), lid)


STAIRS = ["#########",
          "#PPPPPPP#",
          "#PPPPPPP#",
          "#..321..#",
          "#.......#",
          "#.......#",
          "#...@...#",
          "#########"]
STEPS = {"1": {"height": 0.24}, "2": {"height": 0.48}, "3": {"height": 0.72}, "P": {"height": 0.96}}


class HeightTests(unittest.TestCase):
    def test_a_step_up_is_drawn_as_a_riser(self):
        flat = room(HALL)
        stepped = room([r if i != 3 else "#...1...#" for i, r in enumerate(HALL)], {"1": {"height": 0.24}})
        _, za, v, _ = picture_of(flat)
        rgb, zb, _, _ = picture_of(stepped)
        z = 6 - 3 - 0.5                                      # the riser: the step's near edge
        mid = v.PW // 2
        riser = [y for y in range(v.PH) if abs(zb[y * v.PW + mid] - z) < 1e-9]
        self.assertTrue(riser)
        self.assertFalse([y for y in range(v.PH) if abs(za[y * v.PW + mid] - z) < 1e-9])
        lip = rgb[min(riser)][mid]                           # its top row: the step tile's bright lip, in the fog
        self.assertGreater(sum(lip), sum(rgb[max(riser)][mid]))

    def test_floors_and_eyes_rise_with_the_cells(self):
        lv = room(STAIRS, STEPS)
        self.assertTrue(lv.heights)
        self.assertEqual(lv.ground(4, 3), 0.48)
        self.assertEqual(lv.ground(4, 1), 0.96)
        self.assertAlmostEqual(lv.floor_at(4, 3.5), (0.48 + 0.0) / 2)      # half way off the step: blended
        self.assertEqual(lv.floor_at(1, 1.0), 0.96)           # beside a wall: walls do not pull the floor down

    def test_a_step_too_high_is_not_walked_up(self):
        lv = room(["#####",
                   "#.H.#",
                   "#.@.#",
                   "#####"], {"H": {"height": 0.8}})
        put(lv, 2, 2, 0)
        self.assertFalse(lv.step(0, 1))
        self.assertEqual((lv.player.x, lv.player.y), (2, 2))
        self.assertIn("Too high a step", told(lv))
        lv.cell(2, 1).height = 0.5                           # under climb (0.55): up he goes
        self.assertTrue(lv.step(0, 1))
        self.assertEqual((lv.player.x, lv.player.y), (2, 1))
        lv.cell(2, 1).height = 2.0
        put(lv, 2, 1, 2)
        self.assertTrue(lv.step(0, 1))                       # down any drop
        self.assertEqual((lv.player.x, lv.player.y), (2, 2))

    def test_a_level_says_how_high_a_step_it_climbs(self):
        lv = room(["#####",
                   "#.H.#",
                   "#.@.#",
                   "#####"], {"H": {"height": 0.8}}, climb=1.0)
        put(lv, 2, 2, 0)
        self.assertTrue(lv.step(0, 1))

    def test_monsters_find_the_stairs_round_a_ledge(self):
        lv = room(["#######",
                   "#PPPPP#",
                   "#P123P#",
                   "#.....#",
                   "#.....#",
                   "#######"], {"P": {"height": 0.96}, "1": {"height": 0.24}, "2": {"height": 0.48},
                                "3": {"height": 0.72}})
        far = lv.distances(1, 1)                              # steps to the platform's corner
        self.assertEqual(far.get((1, 2)), 1)                 # along the platform
        self.assertGreater(far[(1, 3)], 2)                   # from below: round by the stairs
        flat = room(["#######",
                     "#.....#",
                     "#.....#",
                     "#.....#",
                     "#.....#",
                     "#######"])
        self.assertEqual(flat.distances(1, 1)[(1, 3)], 2)

    def test_a_monster_does_not_step_up_a_ledge(self):
        lv = room(["#####",
                   "#.H.#",
                   "#.z.#",
                   "#@..#",
                   "#####"], {"H": {"height": 0.8}, "z": "zombie"})
        m = lv.monsters[0]
        lv.moved = []
        self.assertFalse(lv.move_mob(m, 2, 1))
        self.assertTrue(lv.move_mob(m, 3, 2))

    def test_rooms_without_heights_are_as_they_were(self):
        data = GameData(ROOTLESS)
        for lid in data.levels:
            lv = Level(data, lid, seed=1)
            if lv.land is None:
                self.assertFalse(lv.heights, lid)
                self.assertEqual(lv.ground(lv.player.x + 0.3, lv.player.y), 0.0)

    def test_the_check_names_bad_heights(self):
        data = with_level({"map": ["#####", "#@H.#", "#####"], "legend": {"H": {"height": "high"}}, "render": "3d"})
        problems = " | ".join(validate(data))
        self.assertIn("'H' height should be a number", problems)
        self.assertIn("render should be classic or mesh", problems)
        data = with_level({"map": ["#####", "#@H.#", "#####"], "legend": {"H": {"height": 1, "ceiling_height": 0.5}}})
        self.assertIn("ceiling at or under its floor", " | ".join(validate(data)))

    def test_the_step_tile_is_the_engines(self):
        self.assertIn("step", TEXTURES)
        self.assertEqual(len(TEXTURES["step"]), 32)


if __name__ == "__main__":
    unittest.main()
