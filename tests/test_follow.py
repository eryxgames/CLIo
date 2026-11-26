# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""python -m engine.follow: the release CLIo follows is written from the release's own list, and only when every
zip in it is right."""
import hashlib
import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine import downloads, follow  # noqa: E402
from engine.motion import fetch as motion_fetch  # noqa: E402
from engine.picture import fetch as picture_fetch  # noqa: E402

V = "9.8.7"


class Release:
    """A release of CLIo Motion that is not on the network: its zips, its checksums.txt, and what was asked for."""

    def __init__(self, machines=("linux-x64", "windows-x64"), spoil=None, lib=None, sums=True):
        self.files, lines = {}, []
        for plat in machines:
            top = "clio-motion-%s-%s/" % (V, plat)
            blob = io.BytesIO()
            with zipfile.ZipFile(blob, "w") as z:
                z.writestr(top + "lib/" + (lib or motion_fetch.library_name(plat)), plat.encode() * 40)
                z.writestr(top + "LICENSE", "Apache")
            name = "clio-motion-%s-%s.zip" % (V, plat)
            self.files[name] = blob.getvalue()
            lines.append("%s  %s" % (hashlib.sha256(self.files[name]).hexdigest(), name))
        lines.append("%s  clio-motion-%s-plan9-vax.zip" % ("0" * 64, V))      # a machine CLIo does not know
        lines.append("not a line of the list")
        if sums:
            self.files["checksums.txt"] = "\n".join(lines).encode()
        if spoil:
            self.files["clio-motion-%s-%s.zip" % (V, spoil)] += b"!"
        self.asked = []

    def __call__(self, url, timeout=None):
        self.asked.append(url)
        name = url.rsplit("/", 1)[1]
        if name not in self.files:
            raise OSError("HTTP Error 404: Not Found")
        return io.BytesIO(self.files[name])


def files_now():
    out = {}
    for path in (motion_fetch.__file__, picture_fetch.__file__, downloads.__file__):
        with open(path, encoding="utf-8") as f:
            out[os.path.abspath(path)] = f.read()
    return out


class Follow(unittest.TestCase):
    def run_it(self, release, args=("motion", V, "--check")):
        said, before = [], files_now()
        code = follow.main(list(args), opener=release, out=said.append)
        self.assertEqual(files_now(), before)                   # --check, or a refusal, writes nothing
        return code, "\n".join(said)

    def test_what_would_be_written(self):
        r = Release()
        code, said = self.run_it(r)
        self.assertEqual(code, 1)                               # --check: there is something to change
        self.assertIn("These would change: engine/motion/fetch.py, engine/downloads.py".replace("/", os.sep), said)
        self.assertTrue(r.asked[0].endswith("/v%s/checksums.txt" % V))
        sums, sizes = follow.gather("motion", V, r, lambda s: None)
        self.assertEqual(sorted(sums), ["linux-x64", "windows-x64"])
        new = follow.written("motion", V, sums, sizes)
        fetch_text = new[os.path.abspath(motion_fetch.__file__)]
        scope = {}
        exec(compile(fetch_text.split("def library_name")[0], "fetch", "exec"), scope)
        self.assertEqual((scope["RELEASE"], scope["SHA256"]), (V, sums))
        text = new[os.path.abspath(downloads.__file__)]
        down = {}
        exec(compile(text[text.index("PICTURE_SIZE = {"):text.index("def size_text")], "downloads", "exec"), down)
        self.assertEqual(down["MOTION_SIZE"], {p: len(r.files["clio-motion-%s-%s.zip" % (V, p)]) for p in sums})
        self.assertEqual(down["PICTURE_SIZE"], downloads.PICTURE_SIZE)          # the others are left as they are
        self.assertEqual(down["BALLISTIC_SIZE"], downloads.BALLISTIC_SIZE)

    def test_a_release_with_no_files(self):
        code, said = self.run_it(Release(sums=False))
        self.assertEqual(code, 1)
        self.assertIn("Could not read", said)
        self.assertIn("one that has no files yet", said)
        self.assertIn("Nothing was changed.", said)

    def test_a_zip_that_is_not_the_one_listed(self):
        code, said = self.run_it(Release(spoil="windows-x64"))
        self.assertEqual(code, 1)
        self.assertIn("windows-x64 does not match the release's own checksums.txt", said)

    def test_a_zip_without_the_library_where_it_is_looked_for(self):
        code, said = self.run_it(Release(lib="other.so"))
        self.assertEqual(code, 1)
        self.assertIn("has no clio-motion-%s-linux-x64/lib/libclio_motion.so" % V, said)

    def test_a_missing_zip(self):
        r = Release()
        del r.files["clio-motion-%s-linux-x64.zip" % V]
        code, said = self.run_it(r)
        self.assertIn("Could not get the zip for linux-x64", said)

    def test_from_a_folder_where_the_network_cannot_be_used(self):
        import tempfile
        r = Release()
        folder = tempfile.mkdtemp(prefix="clio-test-follow-")
        for name, data in r.files.items():
            # the list as a browser saves a sixth copy of it; and an older release's list beside it
            with open(os.path.join(folder, "checksums (6).txt" if name == "checksums.txt" else name), "wb") as f:
                f.write(data)
        with open(os.path.join(folder, "checksums (5).txt"), "w") as f:
            f.write("%s  clio-motion-0.0.1-linux-x64.zip\n" % ("0" * 64))
        code, said = self.run_it(None, ("motion", V, "--from", folder, "--check"))
        self.assertEqual(code, 1, said)
        self.assertIn("These would change", said)
        self.assertIn("linux-x64", said)
        os.remove(os.path.join(folder, "clio-motion-%s-windows-x64.zip" % V))
        code, said = self.run_it(None, ("motion", V, "--from", folder, "--check"))
        self.assertIn("Could not get the zip for windows-x64", said)
        self.assertIn("is not in", said)
        os.remove(os.path.join(folder, "checksums (6).txt"))
        code, said = self.run_it(None, ("motion", V, "--from", folder))
        self.assertEqual(code, 1)
        self.assertIn("checksums.txt is not in", said)
        self.assertNotIn("--from FOLDER", said)                  # (it was asked that way already)
        code, said = self.run_it(None, ("motion", V, "--from", os.path.join(folder, "nowhere")))
        self.assertEqual(code, 2)
        self.assertIn("--from takes a folder that is there", said)

    def test_why_the_network_failed_is_said(self):
        def refused(url, timeout=None):
            raise OSError("<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get issuer certificate>")
        code, said = self.run_it(refused)
        self.assertEqual(code, 1)
        self.assertIn("could not check GitHub's certificate", said)
        self.assertIn("--from FOLDER", said)
        self.assertNotIn("has no files yet", said)               # nothing is known of the release
        code, said = self.run_it(Release(sums=False))
        self.assertIn("no such release, or one that has no files yet", said)
        self.assertIsNone(follow.why(OSError("timed out")))

    def test_what_it_is_asked(self):
        for args in ((), ("motion",), ("sound", "1.0.0"), ("motion", "latest")):
            code, said = self.run_it(Release(), args)
            self.assertEqual(code, 2)
            self.assertIn("usage:", said)

    def test_the_files_are_as_it_writes_them(self):
        """What is committed is what the script would write for the releases followed (so a table is not left
        from an earlier release): the same machines in both tables, in its order and layout."""
        for name, fetch in (("picture", picture_fetch), ("motion", motion_fetch)):
            sizes = getattr(downloads, follow.LIBRARIES[name][1])
            self.assertEqual(sorted(sizes), sorted(fetch.SHA256))
            if not fetch.SHA256:
                continue
            new = follow.written(name, fetch.RELEASE, fetch.SHA256, sizes)
            self.assertEqual({p: t for p, t in new.items()}, {p: files_now()[p] for p in new})


if __name__ == "__main__":
    unittest.main()
