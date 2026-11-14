# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Can the game be finished?  Play its walkthrough and see.

No program can tell in general whether an adventure can be won; a locked case
with the code on a note three rooms away defeats any blind search.  What can be
checked, exactly and every time, is that a *known* way through still works.

A game keeps that way in ``walkthrough.txt``: one command per line, as a player
would type them, answers to the game's questions included.  ``#`` starts a
comment.  A line ``== name`` starts another walkthrough, played from a fresh
start - one for each ending, say.  A line ``seed 7`` sets the dice for the
walkthrough it stands in, for games where fights could go either way.

    == the quiet way out
    take wire
    unlock locker
    ...

``play`` runs them on the real engine, on the game as it would be with unsaved
changes, and reports for each how it ended, where it stopped, and which lines
the game refused; and across all of them, what was never seen.
"""
import io
import os
import re

from . import EditorError, workdir

FILE = "walkthrough.txt"
LIMIT = 5000                # commands in one walkthrough


def read(game_dir):
    path = os.path.join(os.path.abspath(game_dir), FILE)
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(game_dir, text):
    """Keep ``text`` as the game's walkthrough. Returns the file's name."""
    if not isinstance(text, str):
        raise EditorError("A walkthrough is text.")
    path = os.path.join(os.path.abspath(game_dir), FILE)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") or not text else text + "\n")
    return FILE


def parse(text):
    """``[{"name", "seed", "lines": [(line number, command), ...]}, ...]``"""
    out, current = [], None
    for number, raw in enumerate((text or "").splitlines(), 1):
        line = re.sub(r"(^|\s{2,})#.*$", "", raw).strip()
        if not line:
            continue
        if line.startswith("=="):
            current = {"name": line.strip("= ").strip() or "walkthrough %d" % (len(out) + 1), "seed": 1, "lines": []}
            out.append(current)
            continue
        if current is None:
            current = {"name": "walkthrough", "seed": 1, "lines": []}
            out.append(current)
        m = re.match(r"seed\s+(-?\d+)$", line, re.I)
        if m and not current["lines"]:
            current["seed"] = int(m.group(1))
            continue
        current["lines"].append((number, line))
    return out


def _play_one(work, walk):
    from ..audio import Audio
    from ..audio.backends import NullBackend
    from ..game import Game
    from ..term import QuitGame, Term
    queue = list(walk["lines"])[:LIMIT]
    out = io.StringIO()
    state = {"at": None, "starved": False}

    def answer(_prompt):
        if not queue:
            state["starved"] = True
            raise EOFError
        state["at"] = queue.pop(0)
        return state["at"][1]

    term = Term(out=out, inp=answer, width=80, height=40, color=0, unicode=False, animate=False, env={})
    game = Game(work, term=term, audio=Audio(backend=NullBackend(), enabled=False), seed=walk["seed"])
    game.mode_request = next(iter(game.modes), None)
    refused = []
    say = game.say

    def listening(*args, **kw):                             # what the game says in its "error" voice is a refusal
        role = kw.get("role", args[1] if len(args) > 1 else None)
        if role == "error" and state["at"] is not None:
            refused.append({"line": state["at"][0], "command": state["at"][1], "said": str(args[0]) if args else ""})
        return say(*args, **kw)

    game.say = listening
    used = 0
    try:
        game.begin_story()
        while queue and not game.over:
            state["at"] = queue.pop(0)
            used += 1
            game.execute(state["at"][1])
    except EOFError:
        pass
    except QuitGame:
        pass
    lines = [ln.rstrip() for ln in out.getvalue().splitlines() if ln.strip()]
    stopped = None
    if game.over != "win":
        why = ("the game ended here" if game.over else "the game asked a question and the walkthrough had no more lines"
               if state["starved"] else "the walkthrough ends here and the game is not over")
        stopped = {"line": state["at"][0] if state["at"] else None, "command": state["at"][1] if state["at"] else "", "why": why}
    return {"name": walk["name"], "result": game.over, "won": game.over == "win", "total": len(walk["lines"]),
            "left": len(queue), "stopped": stopped, "refused": refused, "tail": lines[-10:],
            "turns": game.world.turn, "_scenes": set(game.world.visited),
            "_quests": {q for q in game.data.quests if game.quests.status(q) == "done"}}


def play(game_dir, text=None, pending=None):
    """Play the walkthroughs (``text``, or the game's own file) on the game as it would be with ``pending``.

    Returns ``{"finished", "walkthroughs": [...], "coverage": {"scenes": {...}, "quests": {...}}}``:
    the rooms no walkthrough entered and the quests none completed.
    ``finished`` is true when there is at least one walkthrough and every one is won.
    """
    walks = parse(read(game_dir) if text is None else text)
    with workdir(game_dir, pending) as work:
        from ..data import GameData
        data = GameData(work)
        results = [_play_one(work, w) for w in walks if w["lines"]]
        seen = set().union(*[r.pop("_scenes") for r in results]) if results else set()
        done = set().union(*[r.pop("_quests") for r in results]) if results else set()
        coverage = {"quests": {"total": len(data.quests), "missing": [q for q in data.quests if q not in done]}}
        if not data.config.get("generator"):                # rooms made in play cannot be listed beforehand
            coverage["scenes"] = {"total": len(data.scenes), "missing": [s for s in data.scenes if s not in seen]}
        return {"finished": bool(results) and all(r["won"] for r in results), "walkthroughs": results,
                "coverage": coverage if results else {}}
