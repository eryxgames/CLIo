# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""--get-motion and the launcher's download of CLIo Motion's C library: nothing without a release that is followed,
nothing that does not match its checksum, nothing that does not agree with the Python."""
import hashlib
import io
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine import downloads, motion  # noqa: E402
from engine.motion import fetch  # noqa: E402

PLAT = fetch.platform_name() or "linux-x64"


def env():
    return {"CLIO_DATA": tempfile.mkdtemp(prefix="clio-test-motion-fetch-"), "CLIO_PICTURE_LIB": "none",
            "CLIO_BALLISTIC_LIB": "none", "CLIO_NODE": "none"}


def release_zip(lib, plat=PLAT, top=None, name=None):
    top = top or "clio-motion-%s-%s/" % (fetch.RELEASE, plat)
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as z:
        z.writestr(top + "lib/" + (name or fetch.library_name(plat)), lib)
        z.writestr(top + "LICENSE", "Apache")
        z.writestr(top + "NOTICE", "CLIo Motion")
        z.writestr(top + "include/clio_motion.h", "/* */")
    return blob.getvalue()


class Served:
    """Stands in for the network: gives what it was made with, and keeps what was asked for."""

    def __init__(self, data):
        self.data, self.asked = data, []

    def __call__(self, url, timeout=None):
        self.asked.append(url)
        if isinstance(self.data, Exception):
            raise self.data
        return io.BytesIO(self.data)


class GetMotion(unittest.TestCase):
    def get(self, data, pins=None, e=None):
        said, served = [], Served(data)
        with mock.patch.dict(fetch.SHA256, pins if pins is not None else {PLAT: hashlib.sha256(data).hexdigest()}, clear=True):
            code = fetch.get(out=said.append, env=e or env(), plat=PLAT, opener=served)
        return code, " ".join(said), served

    def test_without_a_release_that_is_followed_nothing_is_asked_for(self):
        code, said, served = self.get(b"", pins={})
        self.assertEqual((code, served.asked), (1, []))
        self.assertIn("does not follow a release", said)

    def test_a_machine_that_is_not_listed(self):
        code, said, served = self.get(b"", pins={"some-other": "0" * 64})
        self.assertEqual((code, served.asked), (1, []))
        self.assertIn("no library listed for this machine", said)

    def test_no_network(self):
        code, said, _served = self.get(OSError("no route"), pins={PLAT: "0" * 64})
        self.assertEqual(code, 1)
        self.assertIn("Could not download", said)
        self.assertNotIn("certificate", said)
        code, said, _served = self.get(OSError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"), pins={PLAT: "0" * 64})
        self.assertEqual(code, 1)
        self.assertIn("could not check GitHub's certificate", said)

    def test_a_download_that_does_not_match_is_not_installed(self):
        e = env()
        code, said, served = self.get(release_zip(b"x"), pins={PLAT: "0" * 64}, e=e)
        self.assertEqual(code, 1)
        self.assertIn("does not match the checksum", said)
        self.assertEqual(served.asked, [fetch.URL.format(v=fetch.RELEASE, p=PLAT)])
        self.assertIsNone(fetch.installed(e, PLAT))

    def test_a_zip_that_is_not_the_releases(self):
        code, said, _served = self.get(release_zip(b"x", top="elsewhere/"))
        self.assertEqual(code, 1)
        self.assertIn("not as expected", said)
        code, said, _served = self.get(b"not a zip at all")
        self.assertIn("not as expected", said)

    def test_a_library_that_does_not_load_is_said_not_to_be_used(self):
        e = env()
        code, said, _served = self.get(release_zip(b"this is no library"), e=e)
        self.assertEqual(code, 1)
        self.assertIn("Installed", said)
        self.assertIn("It is not used", said)

    def test_the_real_one_is_installed_checked_and_found(self):
        real = os.environ.get("CLIO_MOTION_LIB")
        if not real or not os.path.isfile(real):
            self.skipTest("no library to serve (CLIO_MOTION_LIB)")
        e = env()
        old = os.path.join(fetch.home(e), "0.1.0")
        os.makedirs(old)
        with open(real, "rb") as f:
            code, said, _served = self.get(release_zip(f.read()), e=e)
        self.assertEqual(code, 0, said)
        self.assertIn("loads and agrees with CLIo's Python", said)
        here = fetch.installed(e, PLAT)
        self.assertTrue(here and os.path.isfile(os.path.join(os.path.dirname(here), "LICENSE")))
        self.assertFalse(os.path.isdir(old))                    # a release CLIo no longer follows is cleared away
        self.assertEqual(motion.find_lib(e), here)
        self.assertIsNone(motion.find_lib(dict(e, CLIO_MOTION_LIB="none")))
        self.assertEqual(motion.find_lib(dict(e, CLIO_MOTION_LIB="/somewhere/else.so")), "/somewhere/else.so")


class TheLaunchersDownloads(unittest.TestCase):
    def test_it_is_offered_once_a_release_is_followed(self):
        e = env()
        with mock.patch.dict(fetch.SHA256, {}, clear=True):
            self.assertNotIn("motion", [o.key for o in downloads.offers(e, "linux-x64")])
        with mock.patch.dict(fetch.SHA256, {"linux-x64": "0" * 64}, clear=True), \
                mock.patch.dict(downloads.MOTION_SIZE, {"linux-x64": 152000}, clear=True), \
                mock.patch.object(downloads, "_motion_found", lambda env: None):
            got = {o.key: o for o in downloads.offers(e, "linux-x64")}
            self.assertEqual(list(got)[:2], ["picture", "motion"])
            o = got["motion"]
            self.assertFalse(o.here)
            self.assertEqual(o.label(), "CLIo Motion %s - crowds of bodies run live (152 KB)" % fetch.RELEASE)
            self.assertIn("github.com/eryxgames/clio-motion", o.question("linux-x64"))
            self.assertNotIn("motion", [x.key for x in downloads.offers(e, "plan9-vax")])

    def test_a_yes_in_the_launcher_fetches_it(self):
        class UI:
            def __init__(self):
                self.menus, self.asked, self.said = [], [], []

            def g(self, name):
                return "-"

            def menu(self, labels, title=None, cancel_label=None, **k):
                self.menus.append(list(labels))
                return 1 if len(self.menus) == 1 else None

            def confirm(self, question, default=False):
                self.asked.append(question)
                return True

            def say(self, text="", *a, **k):
                self.said.append(str(text))

            def __getattr__(self, name):                         # whatever else the menu shows with
                return lambda *a, **k: self.said.extend(str(x) for x in a)

        def fake(out=print, env=None, plat=None, opener=None):
            out("Installed somewhere")
            return 0
        ui = UI()
        with mock.patch.dict(fetch.SHA256, {"linux-x64": "0" * 64}, clear=True), \
                mock.patch.dict(downloads.MOTION_SIZE, {"linux-x64": 152000}, clear=True), \
                mock.patch.object(downloads, "_motion_found", lambda env: None), \
                mock.patch.object(fetch, "get", side_effect=fake) as got:
            downloads.menu(None, ui, env(), "linux-x64")
        got.assert_called_once()
        self.assertEqual(got.call_args.kwargs["plat"], "linux-x64")
        self.assertIn("CLIo Motion", ui.menus[0][1])
        self.assertIn("CLIo Motion", ui.asked[0])
        self.assertIn("Installed somewhere", ui.said)

    def test_every_listed_machine_has_a_size(self):
        self.assertEqual(sorted(fetch.SHA256), sorted(downloads.MOTION_SIZE))
        for plat in fetch.SHA256:
            self.assertRegex(fetch.SHA256[plat], "^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
