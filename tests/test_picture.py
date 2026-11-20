"""CLIo Picture, the C library for the pictures: found and checked as Ballistic's is, and giving exactly what the
Python gives - the land's heights and the dots styles' braille cells. The tests that need the library skip
without it (set CLIO_PICTURE_LIB to a build; CLIO_PICTURE_REQUIRE=1 makes them fail instead)."""
import hashlib
import io
import os
import random
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(ROOT))
sys.path.insert(0, ROOT)

from engine import land as land_mod  # noqa: E402
from engine import picture  # noqa: E402
from engine.firstperson import FX, View, dot_level  # noqa: E402
from engine.picture import fetch  # noqa: E402


def with_library(test):
    """Run with the library in use (skipped without it), and leave it as it was."""
    def run(self):
        picture.use(True)
        if picture.load() is None:
            if os.environ.get("CLIO_PICTURE_REQUIRE"):
                self.fail("CLIo Picture is required here: %s" % picture.status())
            self.skipTest("CLIo Picture is not here: %s" % picture.status())
        try:
            test(self)
        finally:
            picture.use(True)
    run.__name__, run.__doc__ = test.__name__, test.__doc__
    return run


def python_too(fn):
    """What ``fn()`` gives with the library and without it."""
    fast = fn()
    picture.use(False)
    try:
        slow = fn()
    finally:
        picture.use(True)
    return fast, slow


def pixels(cols, rows, rng, palette=None):
    pick = (lambda: rng.choice(palette)) if palette else (lambda: (rng.randrange(256), rng.randrange(256),
                                                                     rng.randrange(256)))
    return [[pick() for _x in range(2 * cols)] for _y in range(4 * rows)]


def braille(px, cols, rows, style, over=None):
    v = View(cols, rows, style)
    v.W, v.VR = cols, rows
    return v.braille(px, over or {})


class Shape:
    def __init__(self, seed, scale, warp, rough, ridges):
        self.seed, self.scale, self.warp, self.rough, self.ridges = seed, scale, warp, rough, ridges


class Finding(unittest.TestCase):
    def tearDown(self):
        picture.use(True)

    def test_off_means_python(self):
        picture.use(False)
        self.assertIsNone(picture.load())
        self.assertEqual(picture.status(), "turned off")
        self.assertIsNone(picture.land_raw(Shape(1, 40.0, 0.5, 0.5, 0.3), 0, 0, 4, 4))
        self.assertIsNone(picture.dots(pixels(2, 2, random.Random(1)), 2, 2, False, dot_level))
        self.assertIsNone(picture.version())

    def test_where_it_is_looked_for(self):
        self.assertIsNone(picture.find_lib({"CLIO_PICTURE_LIB": "none"}))
        self.assertEqual(picture.find_lib({"CLIO_PICTURE_LIB": "/x/libclio_picture.so"}), "/x/libclio_picture.so")
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        plat = fetch.platform_name()
        if plat is None or os.path.isdir(os.path.join(picture.HERE, "lib")):
            self.skipTest("no release for this machine, or a library of your own comes first")
        folder = os.path.join(d, "picture", fetch.RELEASE)
        os.makedirs(folder)
        lib = os.path.join(folder, fetch.library_name(plat))
        open(lib, "wb").close()
        self.assertEqual(picture.find_lib({"CLIO_DATA": d}), lib)

    def test_a_library_that_does_not_load_is_not_used(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        bad = os.path.join(d, "libclio_picture.so")
        with open(bad, "wb") as f:
            f.write(b"not a library")
        picture.use(True, {"CLIO_PICTURE_LIB": bad})
        self.assertIsNone(picture.load())
        self.assertIn("does not load", picture.status())

    def test_a_library_that_differs_is_not_used(self):
        class Liar:
            def clio_hash(self, x, y, s):
                return 0.5
        self.assertIn("noise differs", picture._agrees(Liar()))

    def test_the_steps_are_where_the_dots_light(self):
        st = picture.steps(dot_level)
        self.assertEqual(st, sorted(st))
        for k, s in enumerate(st):
            below = struct.unpack("<d", struct.pack("<q", struct.unpack("<q", struct.pack("<d", s))[0] - 1))[0]
            self.assertGreater(dot_level(s), k + 0.5)                    # the least float that lights
            self.assertLessEqual(dot_level(below), k + 0.5)


class Download(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.env = {"CLIO_DATA": self.dir}

    def release_zip(self, plat):
        buf = io.BytesIO()
        top = "clio-picture-%s-%s/" % (fetch.RELEASE, plat)
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(top + "lib/" + fetch.library_name(plat), b"not really a library")
            z.writestr(top + "LICENSE", "Apache-2.0")
            z.writestr(top + "NOTICE", "CLIo Picture")
            z.writestr(top + "include/clio_picture.h", "/* */")
        return buf.getvalue()

    def test_names(self):
        self.assertEqual(fetch.library_name("windows-x64"), "clio_picture.dll")
        self.assertEqual(fetch.library_name("macos-universal"), "libclio_picture.dylib")
        self.assertEqual(fetch.library_name("android-arm64-v8a"), "libclio_picture.so")
        self.assertEqual(fetch.platform_name("linux", "aarch64", False), "linux-arm64")
        self.assertEqual(fetch.home(self.env), os.path.join(self.dir, "picture"))

    def test_no_release_listed_says_how_to_build_it(self):
        said = []
        with mock.patch.dict(fetch.SHA256, {}, clear=True):
            self.assertEqual(fetch.get(said.append, self.env, "linux-x64"), 1)
        self.assertIn("make", said[-1])
        self.assertIn("CLIO_PICTURE_LIB", said[-1])

    def test_it_installs_the_library_and_its_licence_and_checks_it(self):
        data = self.release_zip("linux-x64")
        said, urls = [], []

        def opener(url, timeout=None):
            urls.append(url)
            return io.BytesIO(data)
        picture.use(True)
        before = picture.load()
        with mock.patch.dict(fetch.SHA256, {"linux-x64": hashlib.sha256(data).hexdigest()}):
            os.makedirs(os.path.join(self.dir, "picture", "0.0.1"))       # an older release: cleared away
            code = fetch.get(said.append, self.env, "linux-x64", opener)
        folder = os.path.join(self.dir, "picture", fetch.RELEASE)
        self.assertEqual(sorted(os.listdir(folder)), ["LICENSE", "NOTICE", "libclio_picture.so"])
        self.assertEqual(os.listdir(os.path.join(self.dir, "picture")), [fetch.RELEASE])
        self.assertIn("clio-picture-%s-linux-x64.zip" % fetch.RELEASE, urls[0])
        self.assertEqual(code, 1)                                        # a fake library does not load
        self.assertIn("does not load", said[-1])
        self.assertIs(picture.load(), before)                            # and the one in use stays

    def test_a_download_that_does_not_match_installs_nothing(self):
        said = []
        with mock.patch.dict(fetch.SHA256, {"linux-x64": "0" * 64}):
            code = fetch.get(said.append, self.env, "linux-x64", lambda url, timeout=None: io.BytesIO(b"x"))
        self.assertEqual(code, 1)
        self.assertIn("checksum", said[-1])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "picture")))


class SameAsPython(unittest.TestCase):
    @with_library
    def test_noise(self):
        lib, rng = picture.load(), random.Random(5)
        for _ in range(2000):
            ix, iy = rng.randrange(-1 << 40, 1 << 40), rng.randrange(-1 << 40, 1 << 40)
            s = rng.randrange(0, 1 << 33)
            self.assertEqual(lib.clio_hash(ix, iy, s), land_mod._h(ix, iy, s))
        for _ in range(2000):
            x, y = rng.uniform(-5000, 5000), rng.uniform(-5000, 5000)
            s, octaves, rough = rng.randrange(70000), rng.randrange(1, 7), rng.uniform(0.2, 0.8)
            self.assertEqual(lib.clio_value(x, y, s), land_mod.value(x, y, s))
            self.assertEqual(lib.clio_fbm(x, y, s, octaves, rough), land_mod.fbm(x, y, s, octaves, rough))

    @with_library
    def test_heights_of_many_lands(self):
        rng = random.Random(9)
        for shape in [Shape(1, 40.0, 0.5, 0.5, 0.3), Shape(65535, 4.0, 0.0, 0.7, 0.0), Shape(7, 120.0, 1.0, 0.3, 1.0)] + \
                [Shape(rng.randrange(65536), rng.uniform(4, 90), rng.choice([0.0, rng.random()]), rng.uniform(0.2, 0.8),
                       rng.choice([0.0, rng.random()])) for _ in range(8)]:
            x0, y0 = rng.randrange(-3000, 3000), rng.randrange(-3000, 3000)
            got = picture.land_raw(shape, x0, y0, 18, 18)
            want = [land_mod.Land.raw(shape, x, y) for y in range(y0, y0 + 18) for x in range(x0, x0 + 18)]
            self.assertEqual(got, want)

    @with_library
    def test_chunks_of_a_level_are_the_same(self):
        from engine.data import GameData
        from engine.level import Level
        from test_levels import ROOTLESS

        def chunks():
            land_mod._SHARED.clear()
            lv = Level(GameData(ROOTLESS), "e1m4", seed=1)
            return [lv.land.build(kx, ky) for kx in range(-2, 3) for ky in (-1, 0, 7)]
        fast, slow = python_too(chunks)
        self.assertEqual(fast, slow)
        land_mod._SHARED.clear()

    @with_library
    def test_braille_of_any_pixels(self):
        rng = random.Random(3)
        palette = [(0, 0, 0), (1, 1, 1), (255, 255, 255), (12, 200, 7), (60, 60, 60), (61, 62, 60), (200, 0, 0)]
        for style in ("dots", "dots-fill"):
            for cols, rows, pal in ((1, 1, None), (7, 3, None), (13, 5, palette), (40, 9, palette[:3])):
                px = pixels(cols, rows, rng, pal)
                over = {(0, 0): ("A", (255, 0, 0), None), (rows - 1, cols - 1): ("B", (0, 0, 255), (9, 9, 9)),
                        (rows + 3, 0): ("C", None, None)}
                fast, slow = python_too(lambda: braille(px, cols, rows, style, over))
                self.assertEqual(fast, slow, (style, cols, rows))

    @with_library
    def test_every_grey_and_ramp(self):
        greys = [[(v, v, v) for v in range(256)] for _ in range(4)]           # 128 cells: each step of the dither
        ramp = [[(v, 255 - v, (v * 7) % 256) for v in range(256)] for _ in range(4)]
        for px in (greys, ramp):
            for style in ("dots", "dots-fill"):
                fast, slow = python_too(lambda: braille(px, 128, 1, style))
                self.assertEqual(fast, slow)

    @with_library
    def test_a_level_in_dots_is_the_same(self):
        from engine.data import GameData
        from engine.level import Level
        from test_levels import FX, ROOTLESS, Quiet

        def frames(style):
            lv = Level(GameData(ROOTLESS), "e1m1", seed=1)
            lv.console = Quiet()
            v = View(90, 20, style)
            return [v.render(lv, FX(), i) for i in range(2)]
        for style in ("dots", "dots-fill"):
            fast, slow = python_too(lambda: frames(style))
            self.assertEqual(fast, slow)

    @with_library
    def test_land_frames_are_the_same(self):
        """The ground caster and the sky in C: frames of E1M3, E1M4 and SIM-1 from a few places, each style."""
        from engine.data import GameData
        from engine.level import Level
        from test_levels import ROOTLESS, Quiet
        for lvl, styles in (("e1m4", (("pixel", "high"), ("pixel", "low"), ("dots", "high"), ("dots-fill", "low"))),
                            ("e1m3", (("dots", "high"),)), ("sim1", (("pixel", "high"),))):
            lv = Level(GameData(ROOTLESS), lvl, seed=1)
            lv.console = Quiet()
            p = lv.player
            for style, detail in styles:
                def frames():
                    v = View(64, 16, style, detail)
                    out = []
                    for i, (dx, dy, face) in enumerate(((0, 0, None), (0.5, 0, 1), (-2, 3.25, 2), (1, -1, 3))):
                        fx = FX()
                        fx.cam, fx.face = (p.x + dx, p.y + dy), face
                        out.append(v.render(lv, fx, i))
                    return out
                fast, slow = python_too(frames)
                self.assertEqual(fast, slow, (lvl, style, detail))

    @with_library
    def test_a_map_on_the_land_is_the_same(self):
        """E1M4's compound (cells a map stands on, with their floor tiles), seen from the south, near and far."""
        from engine.data import GameData
        from engine.level import Level
        from test_levels import ROOTLESS, Quiet

        def frames():
            lv = Level(GameData(ROOTLESS), "e1m4", seed=1)
            lv.console = Quiet()
            self.assertTrue(lv.land.stamp)
            v = View(70, 18, "pixel")
            out = []
            for y in (19.5, 23, 34, 60):
                fx = FX()
                fx.cam, fx.face = (95.0, y), 0
                out.append(v.render(lv, fx, 3))
            return out
        fast, slow = python_too(frames)
        self.assertEqual(fast, slow)

    @with_library
    def test_skies_are_the_same(self):
        from engine.firstperson import sky_picture, sky_spec
        specs = [sky_spec({}), sky_spec({"stars": 0.4, "clouds": {"amount": 0.7},
                                         "sun": {"at": 0.1, "height": 0.4, "size": 0.2, "bands": "#aa6644", "glow": 0.6}}),
                 sky_spec({"sun": {"at": 0.9, "height": 0.1, "size": 0.05, "glow": 0},
                           "ridges": [{"near": 1, "height": 0.4, "seed": 5}]}),
                 sky_spec({"sun": {"at": 0.4, "size": 0}, "ridges": []})]
        for spec in specs:
            for f in range(4):
                for PW, yh in ((40, 9), (97, 21)):
                    for lateral, phase in ((0.0, 0), (-13.25, 7), (401.5, 1234)):
                        fast, slow = python_too(lambda: sky_picture(spec, PW, yh, f, lateral, phase))
                        self.assertEqual(fast, slow, (spec, f, PW, lateral, phase))

    @with_library
    def test_a_chunk_that_fails_to_build_fails_as_in_python(self):
        from engine.data import GameData
        from engine.level import Level
        from test_levels import ROOTLESS, Quiet
        land_mod._SHARED.clear()
        lv = Level(GameData(ROOTLESS), "e1m4", seed=1)
        lv.console = Quiet()
        v = View(60, 16, "pixel")
        v.render(lv, FX(), 0)
        built = lv.land.build

        def broken(kx, ky):
            if kx > 9:
                raise RuntimeError("no ground here")
            return built(kx, ky)
        lv.land.build = broken
        lv.land.chunks.clear()
        fx = FX()
        fx.cam, fx.face = (150.0, 80.0), 1
        for on in (True, False):
            picture.use(on)
            with self.assertRaises(RuntimeError):
                v.render(lv, fx, 1)
        picture.use(True)
        land_mod._SHARED.clear()

    @with_library
    def test_a_phase_that_is_not_whole_goes_to_the_python(self):
        from engine.firstperson import sky_spec
        self.assertIsNone(picture.sky(sky_spec({}), 20, 5, 0, 0.0, 1.5, [(0, 0, 0)] * 5, [(1, 1, 1)] * 2))

    @with_library
    def test_pixels_it_cannot_take_go_to_the_python(self):
        px = pixels(2, 1, random.Random(4))
        px[1][1] = (1.5, 2, 3)
        self.assertIsNone(picture.dots(px, 2, 1, False, dot_level))
        px[1][1] = (1, 2, 3, 4)
        self.assertIsNone(picture.dots(px, 2, 1, False, dot_level))
        self.assertIsNone(picture.dots(px[:3], 2, 1, False, dot_level))
        px[1][1] = (1, 2, 3)
        self.assertIsNotNone(picture.dots(px, 2, 1, False, dot_level))


if __name__ == "__main__":
    unittest.main()
