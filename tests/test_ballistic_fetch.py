"""clio.py --get-ballistic: the C engine's library from its release into the user's data folder (no network here:
the download is a zip made in the test)."""
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.audio import ballistic  # noqa: E402
from engine.audio.ballistic import fetch  # noqa: E402


def release_zip(plat, lib=b"not really a library"):
    buf = io.BytesIO()
    top = "ballistic-engine-%s-%s/" % (fetch.RELEASE, plat)
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(top + "lib/" + fetch.library_name(plat), lib)
        z.writestr(top + "LICENSE", "Apache-2.0")
        z.writestr(top + "NOTICE", "Ballistic")
        z.writestr(top + "bin/ballistic-render", "x")
    return buf.getvalue()


class Opener:
    def __init__(self, data):
        self.data, self.urls = data, []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        return io.BytesIO(self.data)


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.env = {"CLIO_DATA": self.dir}

    def test_platforms(self):
        self.assertEqual(fetch.platform_name("linux", "x86_64", False), "linux-x64")
        self.assertEqual(fetch.platform_name("linux", "aarch64", False), "linux-arm64")
        self.assertEqual(fetch.platform_name("linux", "aarch64", True), "android-arm64-v8a")
        self.assertEqual(fetch.platform_name("linux", "armv7l", True), "android-armeabi-v7a")
        self.assertEqual(fetch.platform_name("darwin", "arm64", False), "macos-universal")
        self.assertEqual(fetch.platform_name("win32", "AMD64", False), "windows-x64")
        self.assertEqual(fetch.platform_name("win32", "ARM64", False), "windows-arm64")
        self.assertIsNone(fetch.platform_name("win32", "x86", False))
        self.assertIsNone(fetch.platform_name("freebsd13", "amd64", False))
        self.assertEqual(set(fetch.SHA256), {"linux-x64", "linux-arm64", "macos-universal", "windows-x64",
                                             "windows-arm64", "android-arm64-v8a", "android-armeabi-v7a",
                                             "android-x86_64"})

    def test_it_installs_only_the_library_and_its_licence_in_the_data_folder(self):
        data = release_zip("linux-x64")
        said = []
        opener = Opener(data)
        with mock.patch.dict(fetch.SHA256, {"linux-x64": hashlib.sha256(data).hexdigest()}):
            os.makedirs(os.path.join(self.dir, "ballistic", "0.0.1"))      # an older release: cleared away
            code = fetch.get(said.append, self.env, "linux-x64", opener)
        folder = os.path.join(self.dir, "ballistic", fetch.RELEASE)
        self.assertEqual(sorted(os.listdir(folder)), ["LICENSE", "NOTICE", "libballistic.so"])
        self.assertEqual(os.listdir(os.path.join(self.dir, "ballistic")), [fetch.RELEASE])
        self.assertIn("ballistic-engine-%s-linux-x64.zip" % fetch.RELEASE, opener.urls[0])
        self.assertEqual(code, 1)                                            # a fake library does not load
        self.assertTrue(any("does not load" in s for s in said))
        self.assertEqual(fetch.installed(self.env, "linux-x64"), os.path.join(folder, "libballistic.so"))

    def test_a_download_that_does_not_match_installs_nothing(self):
        said = []
        code = fetch.get(said.append, self.env, "linux-x64", Opener(release_zip("linux-x64")))
        self.assertEqual(code, 1)
        self.assertIn("checksum", said[-1])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "ballistic")))

    def test_no_network_says_so(self):
        def fail(url, timeout=None):
            raise OSError("no route to host")
        said = []
        self.assertEqual(fetch.get(said.append, self.env, "linux-x64", fail), 1)
        self.assertIn("no route to host", said[-1])

    def test_find_clib_looks_in_the_data_folder_after_lib(self):
        plat = fetch.platform_name()
        if plat is None:
            self.skipTest("no release for this machine")
        folder = os.path.join(self.dir, "ballistic", fetch.RELEASE)
        os.makedirs(folder)
        lib = os.path.join(folder, fetch.library_name(plat))
        open(lib, "wb").close()
        own = os.path.join(ballistic.HERE, "lib")
        if os.path.isdir(own):
            self.skipTest("a library in engine/audio/ballistic/lib comes first here")
        self.assertEqual(ballistic.find_clib(self.env), lib)
        self.assertIsNone(ballistic.find_clib(dict(self.env, CLIO_BALLISTIC_LIB="none")))


if __name__ == "__main__":
    unittest.main()
