# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Shared helpers: play a game from a script and capture the transcript."""
import io
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Tests never touch real saves or the real audio cache: both go to temporary
# folders outside the repository, removed again when the test run ends.
import atexit                                       # noqa: E402
import shutil                                       # noqa: E402

for _var, _prefix in (("CLIO_SAVES", "clio-test-saves-"), ("CLIO_CACHE", "clio-test-cache-")):
    if _var not in os.environ:
        _dir = tempfile.mkdtemp(prefix=_prefix)
        os.environ[_var] = _dir
        atexit.register(shutil.rmtree, _dir, True)

from engine.audio import Audio                      # noqa: E402
from engine.audio.backends import NullBackend       # noqa: E402
from engine.game import Game                        # noqa: E402
from engine.term import Term, strip_ansi            # noqa: E402


def game_path(name):
    for cand in (os.path.join(ROOT, "games", name), os.path.join(ROOT, name)):
        if os.path.isdir(cand):
            return cand
    raise FileNotFoundError(name)


class Session:
    """A game driven by a list of commands instead of a keyboard."""

    def __init__(self, name, commands=(), seed=1, width=80, color=0, unicode=True, record_audio=False,
                 mode=None):
        self.out = io.StringIO()
        self.queue = list(commands)
        # env={}: the result must not depend on the TERM, NO_COLOR... of whoever runs the tests
        self.term = Term(out=self.out, inp=self._next, width=width, height=40, color=color,
                         unicode=unicode, animate=False, env={})
        self.backend = NullBackend(record=record_audio)
        self.audio = Audio(backend=self.backend, enabled=record_audio)
        # mode: None plays the game's first mode without asking; "?" lets the script answer the menu
        self.game = Game(game_path(name), term=self.term, audio=self.audio, seed=seed)
        if mode is None:
            mode = next(iter(self.game.modes), None)
        self.game.mode_request = None if mode == "?" else mode

    def _next(self, prompt):
        if not self.queue:
            raise EOFError
        return self.queue.pop(0)

    def run(self):
        """Play the queued commands to the end. Returns the plain-text transcript."""
        self.game.run()
        return self.text

    def start(self):
        self.game.begin_story()
        return self

    def do(self, *commands):
        """Run commands one at a time (answers to prompts go in the same list)."""
        start = len(self.out.getvalue())
        self.queue.extend(commands)
        while self.queue and not self.game.over:
            line = self.queue.pop(0)
            self.game.execute(line)
        return strip_ansi(self.out.getvalue()[start:])

    @property
    def text(self):
        return strip_ansi(self.out.getvalue())

    @property
    def world(self):
        return self.game.world


class Scripted(Session):
    """A session that answers any prompt left over after its script with a default."""

    default = "1"

    def _next(self, prompt):
        return self.queue.pop(0) if self.queue else self.default


def private_saves(session):
    """Give a session its own empty folder for saves and records. Returns the path."""
    folder = tempfile.mkdtemp(prefix="clio-test-run-")
    atexit.register(shutil.rmtree, folder, True)
    session.game.save_dir = folder
    return folder
