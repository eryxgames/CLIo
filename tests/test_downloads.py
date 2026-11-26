"""The optional downloads the launcher offers: CLIo Picture and Ballistic's C engine - asked about first, with
their size and source, and fetched only on a yes."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine import downloads  # noqa: E402
from engine.audio.ballistic import fetch as ballistic_fetch  # noqa: E402
from engine.motion import fetch as motion_fetch  # noqa: E402
from engine.picture import fetch as picture_fetch  # noqa: E402


def empty_env(**more):
    env = {"CLIO_DATA": tempfile.mkdtemp(prefix="clio-test-downloads-"), "CLIO_PICTURE_LIB": "none",
           "CLIO_BALLISTIC_LIB": "none", "CLIO_NODE": "none"}
    env.update(more)
    return env


class FakeUI:
    """Answers menus and questions from a script, and keeps what was said."""

    def __init__(self, picks, answers=()):
        self.picks, self.answers = list(picks), list(answers)
        self.menus, self.asked, self.said = [], [], []

    def g(self, name):
        return "-"

    def menu(self, labels, title=None, cancel_label=None, **k):
        self.menus.append(list(labels))
        return self.picks.pop(0) if self.picks else None

    def confirm(self, question, default=False):
        self.asked.append(question)
        return self.answers.pop(0) if self.answers else False

    def say(self, text, role="default", **k):
        self.said.append(text)

    def pause(self, *a, **k):
        return ""


class DownloadTests(unittest.TestCase):
    def setUp(self):
        # CLIo Picture and Ballistic here, whether or not a release of CLIo Motion is followed
        # (that one's offer is in tests/test_motion_fetch.py)
        followed = mock.patch.dict(motion_fetch.SHA256, {}, clear=True)
        followed.start()
        self.addCleanup(followed.stop)

    def test_sizes_in_words(self):
        self.assertEqual(downloads.size_text(45098), "45 KB")
        self.assertEqual(downloads.size_text(1206755), "1.2 MB")
        self.assertEqual(downloads.size_text(None), "size unknown")

    def test_every_listed_machine_has_a_size(self):
        self.assertEqual(set(downloads.PICTURE_SIZE), set(picture_fetch.SHA256))
        self.assertEqual(set(downloads.BALLISTIC_SIZE), set(ballistic_fetch.SHA256))

    def test_node_is_explained_for_termux(self):
        self.assertEqual(downloads.node_hint({"TERMUX_VERSION": "0.118"}), "pkg install nodejs")
        self.assertIn("nodejs.org", downloads.node_hint({}))

    def test_what_a_phone_is_offered(self):
        got = downloads.offers(empty_env(), "android-arm64-v8a")
        self.assertEqual([o.key for o in got], ["picture", "ballistic"])
        self.assertFalse(any(o.here for o in got))
        size = downloads.size_text(downloads.PICTURE_SIZE["android-arm64-v8a"])
        self.assertRegex(size, r"^\d+ KB$")                # tens of kilobytes, as the release has it
        self.assertIn(size, got[0].label())
        self.assertIn("1.2 MB", got[1].label())
        q = got[0].question("android-arm64-v8a")
        self.assertIn(size, q)
        self.assertIn("github.com/eryxgames/clio-picture", q)
        self.assertIn("SHA-256", q)
        self.assertTrue(downloads.wanted(empty_env(), "android-arm64-v8a"))

    def test_a_machine_without_releases_is_offered_nothing(self):
        self.assertEqual(downloads.offers(empty_env(), "plan9-mips"), [])
        self.assertFalse(downloads.wanted(empty_env(), "plan9-mips"))

    def test_nothing_is_fetched_without_a_yes(self):
        ui = FakeUI([0, 1], answers=[False, False])
        with mock.patch.object(picture_fetch, "get") as pg, mock.patch.object(ballistic_fetch, "get") as bg:
            downloads.menu(None, ui, empty_env(), "linux-x64")
        pg.assert_not_called()
        bg.assert_not_called()
        self.assertEqual(len(ui.asked), 2)

    def test_a_yes_fetches_it_and_says_what_happened(self):
        ui = FakeUI([0], answers=[True])
        env = empty_env()

        def fake(out=print, env=None, plat=None, opener=None):
            out("Installed somewhere")
            return 0
        with mock.patch.object(picture_fetch, "get", side_effect=fake) as pg:
            downloads.menu(None, ui, env, "linux-x64")
        pg.assert_called_once()
        self.assertEqual(pg.call_args.kwargs["plat"], "linux-x64")
        self.assertIn("Installed somewhere", ui.said)
        self.assertEqual(len(ui.menus), 2)                 # and back to the list

    def test_node_is_explained_not_installed(self):
        ui = FakeUI([2])
        downloads.menu(None, ui, empty_env(TERMUX_VERSION="1"), "android-arm64-v8a")
        self.assertIn("pkg install nodejs", ui.menus[0][2])
        self.assertTrue(any("pkg install nodejs" in t for t in ui.said))


if __name__ == "__main__":
    unittest.main()
