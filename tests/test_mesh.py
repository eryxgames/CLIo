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


FEATURES = ["#############",
            "#BBBBBBBBBBB#",
            "#BBB###BBBBB#",
            "#..321...SSS#",
            "#.TXCOKP.SSS#",
            "#..f.....GD.#",
            "#LLLLL......#",
            "#...........#",
            "#...........#",
            "#.....@.....#",
            "#############"]
FEATURE_LEGEND = {"1": {"height": 0.12, "ceiling_height": 1.6}, "2": {"height": 0.24, "ceiling_height": 1.6},
                  "3": {"height": 0.36, "ceiling_height": 1.6}, "B": {"height": 0.48, "ceiling_height": 1.48},
                  "S": {"sky": True}, "T": {"teleport": "t"}, "X": {"toxic": True}, "C": {"conveyor": "e"},
                  "O": {"oil": True}, "K": {"slick": True}, "P": {"plate": "p"}, "f": {"floor": "grate"},
                  "G": {"gate": True}, "D": {"door": True}, "L": {"ceiling_height": 0.8}}


def features_room():
    """A room with every kind of face and floor the mesh view draws: stairs up to a balcony, a lintel, cells open
    to the sky, a teleporter, toxic water, a belt, oil, slick floor, a plate, a tiled floor, bars, a half-open door,
    fire to come and fire now, a scorched floor, a sunk crate."""
    lv = room(FEATURES, FEATURE_LEGEND)
    lv.marks[(5, 7)] = "warn"
    lv.marks[(4, 7)] = "burn"
    lv.fires = {(7, 7): 3}
    lv.cell(8, 8).scorched = True
    lv.cell(3, 8).sunk = True
    lv.cell(10, 5).open = 0.4
    return lv


FEATURE_VIEWS = [  # where from, facing, the camera between cells (None: at the player), beat
    ((6, 9), 0, None, 0), ((6, 9), 0, (6.0, 8.6), 3), ((9, 7), 3, None, 1), ((2, 8), 1, None, 2), ((4, 4), 2, None, 5),
    ((11, 7), 0, None, 2)]                                    # the east wall runs on past the camera: clipped near it


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

    def test_bullet_holes_show_on_the_walls(self):
        lv = room(HALL)
        before, _z, v, _ = picture_of(lv)
        lv.hole(4, 0, 2, 0.0, 0.5)                            # the far wall's face turned south, to the player
        after, _z, v, _ = picture_of(lv)
        changed = [(y, x) for y in range(v.PH) for x in range(v.PW) if before[y][x] != after[y][x]]
        self.assertTrue(changed)
        for y, x in changed:
            self.assertLess(sum(after[y][x]), sum(before[y][x]))      # dark
            self.assertLessEqual(abs(x - v.PW // 2), 1)               # in the middle of the wall ahead
            self.assertLessEqual(abs(y - v.yh), 2)                    # halfway up it, about at the eye
        lv.hole(4, 0, 0, 0.0, 0.5)                            # the face turned north, away: not seen
        self.assertEqual(picture_of(lv)[0], after)

    def test_a_hole_hidden_behind_a_pillar_is_not_drawn(self):
        rows = list(HALL)
        rows[3] = "#...#...#"
        lv = room(rows)
        before = picture_of(lv)[0]
        lv.hole(4, 0, 2, 0.0, 0.5)
        self.assertEqual(picture_of(lv)[0], before)
        lv.hole(4, 3, 2, 0.1, 0.4)                            # on the pillar itself: seen
        self.assertNotEqual(picture_of(lv)[0], before)

    def test_low_detail_draws_the_floor_at_half_width(self):
        lv = room(HALL)
        high, zh, v, _ = picture_of(lv, view())
        low, zl, v, _ = picture_of(lv, View(60, 20, "pixel", "low"))
        self.assertNotEqual(high, low)
        self.assertEqual(list(zh), list(zl))                  # the same faces, as near
        def alike(px):                                        # pairs of floor pixels of one colour, of all pairs
            pairs = [(y, x) for y in range(v.yh + 3, v.PH) for x in range(0, v.PW - 1, 2)
                     if zl[y * v.PW + x] == zl[y * v.PW + x + 1]]
            return sum(px[y][x] == px[y][x + 1] for y, x in pairs) / float(len(pairs))
        self.assertGreater(alike(low), 0.95)                  # all but where one cell's floor meets the next
        self.assertLess(alike(high), alike(low) - 0.04)

    def test_holes_are_drawn_the_same_by_clio_picture(self):
        if picture.load() is None:
            self.skipTest("CLIo Picture is not installed")
        lv = room(HALL)
        for along, down in ((0.0, 0.5), (0.3, 0.4), (-0.4, 0.6)):
            lv.hole(4, 0, 2, along, down)
        lv.hole(0, 3, 1, 0.2, 0.5)                            # the west wall's face, turned east
        a = view(80, 24, frame=False, render="mesh").render(lv, FX(), 1)
        b = view(80, 24, frame=True, render="mesh").render(lv, FX(), 1)
        self.assertEqual(a, b)
        self.assertNotEqual(a, view(80, 24, frame=False, render="mesh").render(room(HALL), FX(), 1))

    def test_clio_picture_draws_every_face_and_floor_as_the_python_does(self):
        lib = picture.load()
        if lib is None or not hasattr(lib, "clio_frame_rooms"):
            self.skipTest("CLIo Picture 0.7 is not installed")
        from engine import mesh as mesh_mod
        drawn = []
        real = mesh_mod.Mesh.draw_frame

        def spy(self_, *a, **k):
            got = real(self_, *a, **k)
            drawn.append(got is not None)
            return got
        mesh_mod.Mesh.draw_frame = spy
        try:
            for (x, y), f, cam, phase in FEATURE_VIEWS:
                for style in ("pixel", "dots"):
                    pics = []
                    for frame in (False, True):
                        lv = features_room()
                        put(lv, x, y, f)
                        fx = FX()
                        fx.cam = cam
                        pics.append(view(64, 20, frame=frame, render="mesh").render(lv, fx, phase))
                    self.assertEqual(pics[0], pics[1], (x, y, f, cam, style))
        finally:
            mesh_mod.Mesh.draw_frame = real
        self.assertTrue(drawn and all(drawn))                 # the library drew them all, not the Python

    def test_the_features_room_has_its_features_in_sight(self):
        lv = features_room()
        put(lv, 6, 9, 0)
        rgb, zbuf, v, labels = picture_of(lv)
        self.assertTrue(lv.sky_look is not None)
        colours = {c for row in rgb for c in row}
        self.assertGreater(len(colours), 150)

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


class TurnAndLookTests(unittest.TestCase):
    def test_a_turn_is_drawn_at_angles_between(self):
        import math
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
        north = view(render="mesh").render(lv, FX(), 0)
        self.assertEqual(view(render="mesh").render(lv, FX(yaw=0.0), 0), north)   # a facing's own angle: the same
        east = view(render="mesh").render(lv, FX(face=1), 0)
        between = view(render="mesh").render(lv, FX(yaw=math.pi / 4), 0)
        self.assertNotEqual(between, north)
        self.assertNotEqual(between, east)

    def test_the_console_turns_the_mesh_view_through_its_angles(self):
        import io
        import math
        from engine.level import KEYMAP, FrameConsole
        from engine.term import Term
        term = Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False, env={})
        con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False, render="mesh")
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
        con.layout()
        yaws = []
        real = View.render

        def spy(self_, lv_, fx, phase=0):
            yaws.append(fx.yaw)
            return real(self_, lv_, fx, phase)
        con.screen.play = lambda frames, draw, dt: list(frames)
        View.render = spy
        try:
            lv.player.facing = 1
            con.turn(lv, None, 1)                              # turned right, north to east
        finally:
            View.render = real
        self.assertEqual([round(y / (math.pi / 2), 2) for y in yaws], [0.25, 0.5, 0.75])

    def test_the_rolled_view_is_the_picture_turned_with_rooms_in_its_corners(self):
        from engine.firstperson import tilt
        lv = room(HALL)
        v = view(60, 20, render="mesh")
        flat = v.render(lv, FX(hands=False), 1)
        self.assertEqual(v.rolled(lv, 0, 1), flat)            # drawn bigger at the same scale, cut to size: the same
        dark = (10, 10, 14)

        def darks(cells):
            return sum((fg == dark) + (bg == dark) for row in cells for _ch, fg, bg in row)
        self.assertGreater(darks(tilt(flat, 90)), 100)        # the picture turned: dark corners
        turned = v.rolled(lv, 90, 1)
        self.assertEqual(darks(turned), 0)                    # the view turned: the rooms there
        self.assertEqual((len(turned), len(turned[0])), (20, 60))
        if picture.load() is not None:
            self.assertEqual(view(60, 20, frame=True, render="mesh").rolled(lv, 52, 1), v.rolled(lv, 52, 1))

    def test_magboots_up_a_wall_roll_the_mesh_view(self):
        import io
        from engine.level import KEYMAP, TIP, TIP_BACK, FrameConsole
        from engine.term import Term
        import test_deep
        for render, want in (("mesh", list(TIP) + list(TIP_BACK)), ("classic", [])):
            term = Term(out=io.StringIO(), width=80, height=24, color=3, unicode=True, animate=False, env={})
            con = FrameConsole(term, "pixel", keys=False, keymap=KEYMAP, animate=False)
            lv = test_deep.room(test_deep.Rides.MAP, render=render)
            lv.console = con
            con.layout()
            played, angles, real = [], [], View.rolled

            def spy(self_, lv_, degrees, phase=0):
                angles.append(degrees)
                return real(self_, lv_, degrees, phase)
            con.screen.play = lambda frames, draw, dt: played.append(list(frames))
            View.rolled = spy
            try:
                test_deep.at(lv, 5, 8, 0)                     # under the plating, facing north
                lv.player.magboots = lv.player.mag_on = True
                lv.run_line("k")
            finally:
                View.rolled = real
            self.assertEqual((lv.player.x, lv.player.y), (5, 5), render)
            self.assertEqual(angles, want, render)
            ride = [f for f in played if len(f) == 15]
            self.assertEqual(len(ride), 1, render)
            if render == "mesh":
                self.assertEqual(ride[0][-1], con.snapshot(lv, style="pixel"))     # back on his feet

    def test_looking_up_and_down_moves_the_horizon_in_the_mesh_view(self):
        lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
        lv.console = Quiet()
        beat = lv.beat
        lv.run_line("look up")
        lv.run_line("look up")
        lv.run_line("look up")
        self.assertEqual(lv.player.look, 2)                    # two steps at most
        self.assertEqual(lv.beat, beat)                        # free, as turning is
        v = view(render="mesh")
        up = v.render(lv, FX(), 0)
        self.assertEqual(v.yh, v.yh0 + round(2 * v.PH * 0.12))
        lv.run_line("look")
        self.assertEqual(lv.player.look, 0)
        ahead = v.render(lv, FX(), 0)
        self.assertEqual(v.yh, v.yh0)
        self.assertNotEqual(up, ahead)
        lv.run_line("look down")
        classic = view()
        down = classic.render(lv, FX(), 0)
        lv.player.look = 0
        self.assertEqual(classic.render(lv, FX(), 0), down)   # the classic picture looks straight ahead

    def test_the_keys_look_up_and_down(self):
        from engine.level import KEYMAP
        self.assertEqual((KEYMAP["shift-up"], KEYMAP["shift-down"], KEYMAP["ctrl-up"]), ("look up", "look down",
                                                                                         "look up"))

    def test_the_library_turns_and_looks_as_the_python_does(self):
        lib = picture.load()
        if lib is None or not hasattr(lib, "clio_frame_rooms"):
            self.skipTest("CLIo Picture 0.7 is not installed")
        lv = features_room()
        put(lv, 6, 9, 0)
        for look, yaw in ((1, 0.3), (-2, 1.1), (2, -0.6)):
            lv.player.look = look
            a = view(64, 20, frame=False, render="mesh").render(lv, FX(yaw=yaw), 2)
            b = view(64, 20, frame=True, render="mesh").render(lv, FX(yaw=yaw), 2)
            self.assertEqual(a, b, (look, yaw))


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

    def test_a_ledge_or_a_low_ceiling_hides_what_is_behind_it(self):
        rows = ["#########",
                "#...z...#",
                "#.BBBBB.#",
                "#.......#",
                "#...@...#",
                "#########"]
        legend = {"B": {"height": 0.8}, "z": "zombie", "T": {"height": 1.5}, "c": {"ceiling_height": 0.3}}
        lv = room(rows, legend)
        m = lv.monsters[0]
        self.assertFalse(lv.line_of_sight(4, 4, 4, 1))         # a block as high as his chest, from the floor
        lv.update_seen()
        self.assertFalse(m.seen)
        self.assertFalse(lv.line_of_sight(4, 1, 4, 4))         # both ways
        self.assertTrue(lv.line_of_sight(1, 4, 1, 1))          # beside it: seen
        tower = room(rows[:3] + ["#@TTTTTT#", "#TTTTTTT#", rows[5]], legend)
        put(tower, 4, 4, 0)
        self.assertTrue(tower.line_of_sight(4, 4, 4, 1))       # from up on a tower: over it
        tower.update_seen()
        self.assertTrue(tower.monsters[0].seen)
        low = room(rows[:2] + ["#.ccccc.#"] + rows[3:], legend)
        self.assertFalse(low.line_of_sight(4, 4, 4, 1))        # a crawlspace's ceiling at his knees
        flat = room(rows[:2] + ["#.......#"] + rows[3:], legend)
        self.assertTrue(flat.line_of_sight(4, 4, 4, 1))

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
            if lv.land is None and lid not in ("sim12", "sim13", "e1m6", "e1m7", "e1m8"):     # built on heights
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


class StairwellTests(unittest.TestCase):
    """RØØTLESS SIM-12: a hall, stairs up to a mezzanine, a pump pit, a low passage and a ramp down."""

    def test_it_is_checked_and_drawn_as_a_mesh(self):
        data = GameData(ROOTLESS)
        self.assertEqual([q for q in validate(data) if "sim12" in q], [])
        lv = Level(data, "sim12", seed=1)
        self.assertTrue(lv.heights)
        self.assertTrue(view().meshed(lv))
        self.assertFalse(view(render="classic").meshed(lv))  # a player may still ask for the classic picture
        cells = view(render=None).render(lv, FX(), 0)
        self.assertEqual(len(cells), 20)

    def test_the_mezzanine_is_reached_only_by_the_stairs(self):
        lv = Level(GameData(ROOTLESS), "sim12", seed=1)
        steps = lv.distances(2, 2)                            # walked to a cell of the mezzanine
        self.assertGreater(steps[(2, 4)], 6)                 # from the hall just below: round by the stairs
        self.assertEqual(steps[(2, 3)], 1)                   # along the mezzanine

    def test_the_bot_plays_it_through(self):
        from engine import levelbot
        data = GameData(ROOTLESS)
        for seed in (1, 4):
            out, lv = levelbot.play(data, "sim12", seed=seed)
            self.assertEqual(out, "exit", seed)
            self.assertLessEqual(lv.beat, 90)



class KernelSpaceTests(unittest.TestCase):
    """RØØTLESS E1M6 Kernel Space: a hall of many floors - the gallery a storey up, the scheduler's dais in
    tiers, the interrupt well, a low crawlway - drawn as a mesh."""

    def test_it_is_checked_and_drawn_as_a_mesh(self):
        data = GameData(ROOTLESS)
        self.assertEqual([q for q in validate(data) if "e1m6" in q], [])
        lv = Level(data, "e1m6", seed=1)
        self.assertTrue(lv.heights and view().meshed(lv))
        self.assertEqual(data.scenes["user_space"]["on_level_exit"][-1], {"goto": "kernel_space"})   # after E1M5

    def test_the_gallery_and_the_well_are_reached_their_own_ways(self):
        lv = Level(GameData(ROOTLESS), "e1m6", seed=1)
        self.assertGreater(lv.distances(6, 3)[(6, 4)], 6)     # the gallery from just below it: round by the stairs
        self.assertGreater(lv.distances(3, 15)[(3, 16)], 6)   # out of the well: up its ramp
        self.assertEqual(lv.distances(3, 16)[(3, 15)], 1)     # into it: a drop

    def test_the_cache_lines_hide_the_trench_but_not_from_the_gallery(self):
        lv = Level(GameData(ROOTLESS), "e1m6", seed=1)
        self.assertFalse(lv.line_of_sight(18, 10, 16, 5))
        self.assertTrue(lv.line_of_sight(16, 3, 16, 5))

    def test_the_crontab_opens_the_gallery_door(self):
        lv = Level(GameData(ROOTLESS), "e1m6", seed=1)
        lv.console = Quiet()
        self.assertTrue(lv.cell(25, 2).solid)
        put(lv, 13, 14, 2)                                    # on the dais top, facing the console
        lv.run_line("use")
        self.assertIn("crontab", " ".join(t for t, _r in lv.log[-3:]))
        self.assertFalse(lv.cell(25, 2).solid)

    def test_the_bot_plays_it_through(self):
        from engine import levelbot
        data = GameData(ROOTLESS)
        for seed in (1, 4):
            out, lv = levelbot.play(data, "e1m6", seed=seed)
            self.assertEqual(out, "exit", seed)
            self.assertLessEqual(lv.beat, 150)


if __name__ == "__main__":
    unittest.main()
