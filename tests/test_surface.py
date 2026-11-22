# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Surfaces lit by their materials (engine/surface.py): tiles' metal, roughness, polish and glowing texels, the
mesh view's G-buffer, lamps' light and highlights, dim reflections in floors, wet floors and the rain's
splashes."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from engine import surface  # noqa: E402
from engine.firstperson import FX, View  # noqa: E402
from engine.level import Level, validate  # noqa: E402
from test_levels import Quiet, put, with_level  # noqa: E402

HALL = ["#########",
        "#.......#",
        "#.......#",
        "#.......#",
        "#.......#",
        "#...@...#",
        "#########"]
# a bright wall with a lit window in it (the "w" texels glow), a mirror-like floor, a plain one
TILES = {
    "panel_lit": {"pixels": ["mmmm", "mwwm", "mwwm", "mmmm"], "palette": {"m": "#606060", "w": "#ffd080"},
                  "material": {"metal": 0.1, "rough": 0.3, "glow": "w"}},
    "white": {"pixels": ["aa", "aa"], "palette": {"a": "#f0f0f0"}, "material": {"rough": 0.9}},
    "polish": {"pixels": ["aa", "aa"], "palette": {"a": "#303030"}, "material": {"rough": 0.05, "reflect": 0.8}},
    "matte": {"pixels": ["aa", "aa"], "palette": {"a": "#303030"}, "material": {"rough": 0.9}},
    "chrome": {"pixels": ["aa", "aa"], "palette": {"a": "#8090a0"}, "material": {"metal": 1.0, "rough": 0.25}},
}


def level(rows=HALL, legend=None, tiles=TILES, wall=None, **more):
    legend = dict(legend or {})
    if wall:
        legend["#"] = {"wall": wall}
    spec = {"map": rows, "legend": legend, "render": "mesh"}
    spec.update(more)
    lv = Level(with_level(spec, tiles=tiles), "t", seed=1)
    lv.console = Quiet()
    lv.weapons = {}
    return lv


def render(lv, t=0.0, W=60, VR=20, detail="high"):
    v = View(W, VR, "pixel", detail)
    v.use_frame = False
    lv.beat = int(t)
    return v, v.render(lv, FX(tick=t - int(t), hands=False), 1)


class Captured:
    """surface.shade's arguments while a picture is lit: the G-buffer, the picture before and after."""

    def __enter__(self):
        self.calls = []
        self.real = surface.shade

        def spy(lv, atm, view, rows, depths, gbuf, *rest):
            before = [list(r) for r in rows]
            self.real(lv, atm, view, rows, depths, gbuf, *rest)
            self.calls.append({"gbuf": tuple(bytes(b) for b in gbuf), "before": before,
                               "after": [list(r) for r in rows], "depths": [list(d) for d in depths],
                               "PW": view.PW, "PH": view.PH})
        surface.shade = spy
        return self

    def __exit__(self, *exc):
        surface.shade = self.real


def light(rows):
    return sum(sum(c) for r in rows for c in r)


class MaterialTests(unittest.TestCase):
    def test_tiles_say_what_they_are_made_of(self):
        lv = level(lights={"ambient": 0.5})
        mats, index = lv.materials, lv.material_index
        lit = mats[index["panel_lit"]]
        self.assertEqual((lit.metal, lit.rough), (0.1, 0.3))
        self.assertEqual(lit.glow, frozenset([(255, 208, 128)]))     # the palette's "w": its colour glows
        self.assertEqual(mats[index["polish"]].reflect, 0.8)
        self.assertGreater(mats[index["steel"]].metal, 0.5)        # the engine's own tiles have theirs
        self.assertTrue(mats[index["screens"]].glow)
        self.assertNotIn("racks_unknown", index)
        self.assertEqual(mats[0].metal, 0.0)                       # plain: what a tile without one is

    def test_check_says_what_is_wrong_with_a_material(self):
        bad = dict(TILES, odd={"pixels": ["ab"], "palette": {"a": "#000000", "b": "#ffffff"},
                               "material": {"metal": 2, "rough": "very", "glow": "z"}})
        problems = validate(with_level({"map": HALL, "legend": {}, "surfaces": "yes", "wet": 3}, tiles=bad))
        text = "\n".join(problems)
        self.assertIn("tile 'odd' material metal should be 0 to 1", text)
        self.assertIn("tile 'odd' material rough should be 0 to 1", text)
        self.assertIn("tile 'odd' material glow should be letters of its palette", text)
        self.assertIn("\"surfaces\" should be true or false", text)
        self.assertIn("\"wet\" (how much its floors mirror) should be 0 to 1", text)
        self.assertEqual([p for p in validate(with_level({"map": HALL, "legend": {}}, tiles=TILES))
                          if "material" in p], [])

    def test_surfaces_are_lit_where_there_is_light_or_weather_or_the_level_says(self):
        self.assertFalse(level().surfaces)                         # as it was: the engine's picture
        self.assertTrue(level(lights={"ambient": 0.6}).surfaces)
        self.assertTrue(level(weather={"kind": "rain"}).surfaces)
        self.assertFalse(level(lights={"ambient": 0.6}, surfaces=False).surfaces)
        self.assertTrue(level(surfaces=True).surfaces)

    def test_the_highlight(self):
        n, l = (0.0, 0.0, 1.0), (0.0, 0.6, 0.8)
        mirror, aside = (0.0, -0.6, 0.8), (0.6, 0.0, 0.8)
        sharp = surface.ggx(n, l, mirror, 0.2, 0.04)
        self.assertGreater(sharp, surface.ggx(n, l, aside, 0.2, 0.04) * 5)     # where the light is mirrored
        self.assertLess(surface.ggx(n, l, mirror, 0.9, 0.04), sharp)          # rough: spread, lower
        self.assertGreater(surface.ggx(n, l, mirror, 0.2, 0.64), sharp * 5)  # a metal gives back more
        self.assertEqual(surface.ggx(n, (0.0, 0.0, -1.0), mirror, 0.2, 0.04), 0.0)   # from behind: none
        self.assertGreater(surface.ggx(n, (0.0, 0.95, 0.31), (0.0, -0.95, 0.31), 0.5, 0.04),
                           surface.ggx(n, (0.0, 0.3, 0.95), (0.0, -0.3, 0.95), 0.5, 0.04))   # grazing: Fresnel


class GBufferTests(unittest.TestCase):
    def test_each_pixel_knows_what_it_shows(self):
        lv = level(legend={"G": {"floor": "polish"}}, lights={"ambient": 0.6}, wall="panel_lit")
        with Captured() as cap:
            v, _cells = render(lv)
        self.assertEqual(len(cap.calls), 1)
        kinds, mats, own = cap.calls[0]["gbuf"]
        PW, PH = cap.calls[0]["PW"], cap.calls[0]["PH"]
        top, bottom = kinds[:PW], kinds[(PH - 1) * PW:]
        self.assertEqual(set(top), {surface.CEILING})
        self.assertEqual(set(bottom), {surface.FLOOR})
        middle = kinds[(PH // 2) * PW:(PH // 2 + 1) * PW]
        self.assertTrue(set(middle) <= {surface.WALL_PX, surface.WALL_NX, surface.WALL_PY, surface.WALL_NY})
        self.assertIn(surface.WALL_PY, middle)                     # the wall ahead (north) faces south: +y
        glowing = [i for i in range(PW * PH) if mats[i] & surface.GLOW]
        self.assertTrue(glowing)                                  # the window's texels (and the ceiling's lights)
        self.assertTrue(all(cap.calls[0]["before"][i // PW][i % PW] in ((255, 208, 128), (168, 162, 122))
                            for i in glowing))
        self.assertTrue(all(0 < own[i] <= 255 for i in range(PW * PH) if kinds[i]))

    def test_things_are_marked_with_their_distance(self):
        rows = [r if i != 3 else "#...z...#" for i, r in enumerate(HALL)]
        lv = level(rows, legend={"z": "zombie"}, lights={"ambient": 0.6})
        put(lv, 4, 5, 0)
        with Captured() as cap:
            render(lv)
        c = cap.calls[0]
        kinds, PW = c["gbuf"][0], c["PW"]
        things = [i for i in range(len(kinds)) if kinds[i] == surface.THING]
        self.assertTrue(things)
        z = [c["depths"][i // PW][i % PW] for i in things]
        self.assertTrue(all(abs(d - 2.0) < 0.6 for d in z), z[:5])  # two cells ahead, not the wall behind

    def test_without_light_or_weather_the_picture_is_as_it_was(self):
        lv = level()
        with Captured() as cap:
            render(lv)
        self.assertEqual(cap.calls, [])


class LightTests(unittest.TestCase):
    def test_glowing_texels_keep_their_light_in_the_dark(self):
        lv = level(lights={"ambient": 0.1}, wall="panel_lit")
        with Captured() as cap:
            render(lv)
        c = cap.calls[0]
        kinds, mats, _own = c["gbuf"]
        PW = c["PW"]
        for i in range(len(kinds)):
            before, after = c["before"][i // PW][i % PW], c["after"][i // PW][i % PW]
            if mats[i] & surface.GLOW:
                self.assertEqual(after, before)
            elif kinds[i] in (surface.WALL_PY,) and sum(before) > 60:
                self.assertLess(sum(after), sum(before) * 0.3)

    def test_a_lamp_lights_the_side_turned_to_it(self):
        rows = ["#########",
                "#.......#",
                "#...#...#",
                "#.L.#...#",
                "#...#...#",
                "#.......#",
                "#########"]
        lv = level(rows, legend={"L": {"lamp": {"colour": [255, 255, 255], "reach": 4, "power": 1.2}}},
                   lights={"ambient": 0.15}, wall="white")
        atm = lv.atmosphere
        sh = surface.Shader(lv, atm, (4.0, 5.0, 0.0, -1.0, 1.0, 0.0), 1.6, 0.5, 0.0, lv.materials)
        mi = lv.material_index["white"]
        # the pillar's west face (turned to the lamp at x=2) and its east face (turned away), at its middle
        west = sh.light(int(3.45 * 4), int(3.0 * 4), 2, surface.WALL_NX, mi)
        east = sh.light(int(4.55 * 4), int(3.0 * 4), 2, surface.WALL_PX, mi)
        self.assertGreater(west[0], 0.3)
        self.assertEqual(east, (0.0, 0.0, 0.0))                   # the lamp does not see that side's cells
        floor_under = sh.light(2 * 4 + 1, 3 * 4 + 1, 0, surface.FLOOR, mi)
        floor_off = sh.light(int(1.4 * 4), 1 * 4, 0, surface.FLOOR, mi)
        self.assertGreater(floor_under[0], floor_off[0])

    def test_metal_shines_where_the_light_is_mirrored(self):
        lv = level(lights={"ambient": 0.3}, wall="chrome")
        sh = surface.Shader(lv, lv.atmosphere, (4.0, 5.0, 0.0, -1.0, 1.0, 0.0), 1.6, 0.5, 0.0, lv.materials)
        mi = lv.material_index["chrome"]
        ahead = sh.spec(int(4.0 * 16), int(0.55 * 16), int(0.6 * 16), surface.WALL_PY, mi)[3]
        aside = sh.spec(int(1.0 * 16), int(0.55 * 16), int(0.6 * 16), surface.WALL_PY, mi)[3]
        self.assertGreater(ahead, aside * 3)                       # the player's own light, back from straight ahead
        plain = sh.spec(int(4.0 * 16), int(0.55 * 16), int(0.6 * 16), surface.WALL_PY, 0)[3]
        self.assertGreater(ahead, plain * 3)

    def test_a_lamp_far_off_lights_what_is_by_it(self):
        rows = ["#####",
                "#.L.#",
                "#...#",
                "#...#",
                "#...#",
                "#...#",
                "#...#",
                "#...#",
                "#.@.#",
                "#####"]
        lamp = {"L": {"lamp": {"colour": [255, 60, 30], "reach": 3, "power": 1.5}}}
        lit = level(rows, legend=lamp, lights={"ambient": 0.2}, wall="white")
        with Captured() as cap:
            render(lit)
        c = cap.calls[0]
        PW = c["PW"]
        kinds = c["gbuf"][0]
        far_wall = [c["after"][i // PW][i % PW] for i in range(len(kinds)) if kinds[i] == surface.WALL_PY]
        self.assertGreater(sum(p[0] for p in far_wall), 2 * sum(p[2] for p in far_wall))   # its red, seven off


    def test_models_are_lit_by_the_same_lamps(self):
        rows = ["#########",
                "#.......#",
                "#.......#",
                "#..LwR..#",
                "#.......#",
                "#...@...#",
                "#########"]
        legend = {"w": "warden", "L": {"lamp": {"colour": [255, 40, 20], "reach": 3, "power": 2.0}},
                  "R": {"lamp": {"colour": [20, 60, 255], "reach": 3, "power": 2.0}}}
        lv = level(rows, legend=legend, lights={"ambient": 0.4})
        for m in lv.monsters:
            m.facing = 2                                           # turned to the player
        with Captured() as cap:
            render(lv)
        c = cap.calls[0]
        kinds, mats, _own = c["gbuf"]
        PW = c["PW"]
        model = [i for i in range(len(kinds)) if kinds[i] == surface.THING]
        self.assertTrue(model)
        self.assertTrue(all(mats[i] & surface.GLOW for i in model))     # lit already: left as it is
        xs = sorted(i % PW for i in model)
        mid = (xs[0] + xs[-1]) / 2
        left = [c["after"][i // PW][i % PW] for i in model if i % PW < mid]
        right = [c["after"][i // PW][i % PW] for i in model if i % PW > mid]
        self.assertGreater(sum(p[0] - p[2] for p in left) / len(left), sum(p[0] - p[2] for p in right) / len(right))


class ReflectionTests(unittest.TestCase):
    def floor_light(self, floor, **more):
        legend = {".": {"floor": floor}, "@": {"floor": floor, "start": True}}
        lv = level(legend=legend, wall="white", **more)
        with Captured() as cap:
            render(lv, **{k: v for k, v in (("t", more.pop("t", 0.0)),)})
        c = cap.calls[0]
        PW = c["PW"]
        kinds = c["gbuf"][0]
        floor_px = [c["after"][i // PW][i % PW] for i in range(len(kinds)) if kinds[i] == surface.FLOOR]
        return sum(sum(p) for p in floor_px) / max(1, len(floor_px)), c

    def test_a_polished_floor_mirrors_the_bright_wall_dimly(self):
        shiny, c = self.floor_light("polish", lights={"ambient": 0.8})
        matte, _ = self.floor_light("matte", lights={"ambient": 0.8})
        self.assertGreater(shiny, matte * 1.15)
        # dim: the floor is never as bright as the wall it mirrors
        PW = c["PW"]
        kinds = c["gbuf"][0]
        wall = [c["after"][i // PW][i % PW] for i in range(len(kinds)) if kinds[i] == surface.WALL_PY]
        self.assertLess(shiny, sum(sum(p) for p in wall) / len(wall) * 0.6)

    def test_rain_wets_the_floor_open_to_the_sky(self):
        rows = ["#########",
                "#ssssss.#",
                "#ssssss.#",
                "#ssssss.#",
                "#ssssss.#",
                "#sss@ss.#",
                "#########"]
        legend = {"s": {"sky": True, "floor": "matte"}, "@": {"sky": True, "floor": "matte", "start": True},
                  ".": {"floor": "matte"}}
        dry = level(rows, legend=legend, wall="white", lights={"ambient": 0.8}, weather={"kind": "clear"})
        wet = level(rows, legend=legend, wall="white", lights={"ambient": 0.8},
                    weather={"kind": "rain", "amount": 1.0, "fog": 0.0})
        out = []
        for lv in (dry, wet):
            with Captured() as cap:
                render(lv, detail="high")
            c = cap.calls[0]
            out.append(c)
        a, b = out
        PW = a["PW"]
        kinds = a["gbuf"][0]
        floor = [i for i in range(len(kinds)) if kinds[i] == surface.FLOOR and b["gbuf"][0][i] == surface.FLOOR]
        diff = sum(1 for i in floor if a["after"][i // PW][i % PW] != b["after"][i // PW][i % PW])
        self.assertGreater(diff, len(floor) // 4)

    def test_low_detail_draws_no_reflections(self):
        legend = {".": {"floor": "polish"}, "@": {"floor": "polish", "start": True}}
        lv = level(legend=legend, wall="white", lights={"ambient": 0.8})
        with Captured() as cap:
            render(lv, detail="low")
        c = cap.calls[0]
        PW = c["PW"]
        kinds = c["gbuf"][0]
        lv2 = level(legend={".": {"floor": "matte"}, "@": {"floor": "matte", "start": True}}, wall="white",
                    lights={"ambient": 0.8})
        with Captured() as cap2:
            render(lv2, detail="low")
        c2 = cap2.calls[0]
        same = all(c["after"][i // PW][i % PW] == c2["after"][i // PW][i % PW]
                   for i in range(len(kinds)) if kinds[i] == surface.FLOOR)
        self.assertTrue(same)                                    # polish and matte the same colour: no mirror


class SplashTests(unittest.TestCase):
    ROWS = ["###########",
            "#sssssssss#",
            "#sssssssss#",
            "#sssssssss#",
            "#sssssssss#",
            "#sssssssss#",
            "#ssss@ssss#",
            "###########"]
    LEGEND = {"s": {"sky": True}, "@": {"sky": True, "start": True}}

    def test_drops_strike_the_ground_open_to_the_sky(self):
        lv = level(self.ROWS, legend=self.LEGEND, weather={"kind": "rain", "amount": 1.0, "fog": 0.0})
        v = View(80, 24, "pixel", "high")
        v.use_frame = False
        v.render(lv, FX(hands=False), 1)                           # sizes, the eye
        PW, PH = v.PW, v.PH
        cam = (lv.player.x, lv.player.y, 0.0, -1.0, 1.0, 0.0)
        rows = [[(40, 40, 40)] * PW for _ in range(PH)]
        kinds = bytearray(PW * PH)
        depths = []
        Z0, ly = 1.6, v.TALL * 1.6
        for y in range(PH):                                        # a flat ground under the sky's rows
            sb = (y + 0.5 - v.yh) / ly
            d = v.EYE / sb if sb > 0 else 1e9
            depths.append([d - Z0 if sb > 0 else 1e9] * PW)
            if sb > 0:
                kinds[y * PW:(y + 1) * PW] = bytes([surface.FLOOR]) * PW
        struck = 0
        for t in (0.0, 0.2, 0.4):
            rr = [list(r) for r in rows]
            surface.splashes(lv, v, rr, depths, kinds, cam, Z0, v.EYE, t, 1.0)
            changed = [(y, x) for y in range(PH) for x in range(PW) if rr[y][x] != (40, 40, 40)]
            self.assertTrue(all(kinds[y * PW + x] == surface.FLOOR for y, x in changed))
            self.assertTrue(all(rr[y][x][2] > 40 for y, x in changed))     # light caught, a little blue
            struck += len(changed)
            again = [list(r) for r in rows]
            surface.splashes(lv, v, again, depths, kinds, cam, Z0, v.EYE, t, 1.0)
            self.assertEqual(again, rr)                                   # the same moment: the same drops
        self.assertGreater(struck, 20)
        none = [list(r) for r in rows]
        surface.splashes(lv, v, none, depths, kinds, cam, Z0, v.EYE, 0.0, 0.0)
        self.assertEqual(none, rows)

    def test_no_drops_under_a_roof(self):
        rows = [r.replace("s", ".") for r in self.ROWS]
        lv = level(rows, legend={}, weather={"kind": "rain", "amount": 1.0})
        v = View(80, 24, "pixel", "high")
        v.use_frame = False
        v.render(lv, FX(hands=False), 1)
        PW, PH = v.PW, v.PH
        rows_ = [[(40, 40, 40)] * PW for _ in range(PH)]
        depths = [[2.0] * PW for _ in range(PH)]
        surface.splashes(lv, v, rows_, depths, None, (5, 6, 0.0, -1.0, 1.0, 0.0), 1.6, v.EYE, 0.3, 1.0)
        self.assertTrue(all(c == (40, 40, 40) for r in rows_ for c in r))


class PictureTests(unittest.TestCase):
    def test_the_rooms_turned_over_and_tipped_still_lit(self):
        lv = level(lights={"ambient": 0.4}, wall="panel_lit")
        v = View(60, 20, "pixel", "high")
        v.use_frame = False
        upright = v.render(lv, FX(hands=False), 1)
        over = v.render(lv, FX(hands=False, flip=True), 1)
        self.assertNotEqual(upright, over)
        rolled = v.rolled(lv, 30.0)
        self.assertEqual(len(rolled), len(upright))

    def test_a_shot_glows_in_the_dark(self):
        lv = level(lights={"ambient": 0.05})
        v = View(60, 20, "pixel", "high")
        v.use_frame = False
        with Captured() as cap:
            v.render(lv, FX(hands=False, shots=[(4, 3)]), 1)
        c = cap.calls[0]
        kinds, mats, _own = c["gbuf"]
        PW = c["PW"]
        hot = [i for i in range(len(kinds)) if kinds[i] == surface.THING and mats[i] & surface.GLOW]
        self.assertTrue(hot)
        self.assertTrue(all(c["after"][i // PW][i % PW] == c["before"][i // PW][i % PW] for i in hot))
        self.assertFalse(v.cur_glow)                              # left as it was for what is drawn next

    def test_the_library_leaves_lit_surfaces_to_the_python_until_it_can(self):
        from engine.picture import frame as picture_frame
        lib = picture_frame.load()
        self.assertEqual(picture_frame.surfaces_ok(), lib is not None and hasattr(lib, "clio_frame_surface"))
        lv = level(lights={"ambient": 0.5}, wall="panel_lit")
        a = View(60, 20, "pixel", "high")
        a.use_frame = False
        b = View(60, 20, "pixel", "high")
        b.use_frame = True
        if not picture_frame.surfaces_ok():
            self.assertEqual(a.render(lv, FX(hands=False), 1), b.render(lv, FX(hands=False), 1))

    def test_a_save_keeps_none_of_it(self):
        from engine import snapshot
        lv = level(lights={"ambient": 0.5}, wall="panel_lit")
        state = snapshot.capture(lv)
        text = repr(state)
        self.assertNotIn("material", text)
        lv2 = level(lights={"ambient": 0.5}, wall="panel_lit")
        snapshot.restore(lv2, state)
        self.assertTrue(lv2.surfaces)
        self.assertEqual(lv2.material_index, lv.material_index)


if __name__ == "__main__":
    unittest.main()


def surfaces_library(test):
    """Run with CLIo Picture 0.8 in use (skipped without it, failed if one is required), and leave it as it was."""
    from engine import picture
    from engine.picture import frame as picture_frame

    def run(self):
        picture.use(True)
        if not picture_frame.surfaces_ok():
            if os.environ.get("CLIO_PICTURE_REQUIRE") and picture.load() is not None and \
                    hasattr(picture.load(), "clio_frame_rooms") and os.environ.get("CLIO_PICTURE_08"):
                self.fail("CLIo Picture 0.8 is required here: %s" % picture.status())
            self.skipTest("CLIo Picture 0.8 is not here: %s" % picture.status())
        try:
            test(self)
        finally:
            picture.use(True)
    run.__name__, run.__doc__ = test.__name__, test.__doc__
    return run


class LibraryTests(unittest.TestCase):
    """CLIo Picture 0.8 gives the Python's pictures, to the pixel."""

    def same(self, make, W=60, VR=18, style="pixel", detail="high", t=0.0, flip=None):
        from engine import picture
        out = []
        for on in (False, True):
            picture.use(on)
            lv = make()
            lv.beat = int(t)
            v = View(W, VR, style, detail)
            v.use_frame = on
            out.append(v.render(lv, FX(tick=t - int(t), hands=False, flip=flip), 1))
        picture.use(True)
        self.assertEqual(out[0], out[1])
        return out[1]

    @surfaces_library
    def test_lit_surfaces_are_the_same(self):
        hall = ["#########",
                "#.......#",
                "#.......#",
                "#..LwR..#",
                "#.......#",
                "#...@...#",
                "#########"]
        legend = {"w": "warden", "L": {"lamp": {"colour": [255, 40, 20], "reach": 3, "power": 2.0}},
                  "R": {"lamp": {"colour": [20, 60, 255], "reach": 3, "power": 2.0}},
                  ".": {"floor": "polish"}, "@": {"floor": "polish", "start": True}}
        for style, detail in (("pixel", "high"), ("dots", "high"), ("pixel", "low")):
            for wall in ("chrome", "panel_lit"):
                self.same(lambda: level(hall, legend=legend, wall=wall, lights={"ambient": 0.4}), style=style,
                          detail=detail)
        rain = {"kind": "rain", "amount": 1.0, "fog": 0.05}
        yard = dict(SplashTests.LEGEND, s={"sky": True, "floor": "polish"})
        for t in (0.0, 3.4, 7.75):
            self.same(lambda: level(SplashTests.ROWS, legend=yard, wall="panel_lit", lights={"ambient": 0.3},
                                    weather=rain), t=t)
        self.same(lambda: level(lights={"ambient": 0.5}, wall="chrome"), flip=True)     # on the ceiling

    @surfaces_library
    def test_the_lit_episode_is_the_same(self):
        from engine.data import GameData
        from test_levels import ROOTLESS
        data = GameData(ROOTLESS)
        for lid, where in (("e1m8", None), ("e1m8", (6, 30, 1)), ("e1m6", (13, 19, 0)), ("e1m7", None)):
            def make(lid=lid, where=where):
                lv = Level(data, lid, seed=0)
                lv.console = Quiet()
                if where:
                    put(lv, *where)
                return lv
            for t in (0.0, 2.6):
                self.same(make, W=80, VR=22, t=t)

    @surfaces_library
    def test_low_detail_rooms_are_the_same(self):
        rows = ["#########",
                "#..%....#",
                "#.......#",
                "#...=...#",
                "#.......#",
                "#...@...#",
                "#########"]
        for style in ("pixel", "dots"):
            self.same(lambda: level(rows), style=style, detail="low")

    @surfaces_library
    def test_terraces_and_the_turn_are_the_same(self):
        from engine import firstperson as fp, picture
        from test_land import land_level
        rows = ["#######", "#.....#", "#.@12T#", "#...TT#", "##.####"]
        legend = {"1": {"height": 0.3}, "2": {"height": 0.6}, "T": {"height": 0.9}}
        for where in ((22, 22, 1), (23, 22, 1), (25, 23, 3)):
            def make(where=where):
                lv = land_level(rows=rows, legend=legend, land={"at": [20, 20], "start": None})
                put(lv, *where)
                return lv
            for style, detail in (("pixel", "high"), ("pixel", "low"), ("dots", "high")):
                self.same(make, W=70, VR=20, style=style, detail=detail)
        cells = render(level(lights={"ambient": 0.6}, wall="panel_lit"))[1]
        for deg in (6.0, 30.0, -90.0, 135.5):
            picture.use(False)
            slow = fp.tilt(cells, deg)
            picture.use(True)
            self.assertEqual(fp.tilt(cells, deg), slow)
