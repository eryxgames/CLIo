# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Quests: multi-stage objectives that advance themselves.

    "power": {
      "title": "Lights on",
      "description": "Restore main power.",
      "auto_start": true,                       # or a condition
      "stages": [
        {"text": "Find a fission relay", "done_when": "has:fission_relay"},
        {"text": "Install it in the reactor", "done_when": "reactor_online",
         "do": [{"say": "The deck hums back to life."}]}
      ],
      "on_complete": [{"xp": 50}]
    }

After every turn each active quest checks the ``done_when`` of its current
stage; when it holds, the stage's ``do`` runs and the quest moves on.
"""
from __future__ import annotations

from . import conditions


class QuestLog:
    def __init__(self, game):
        self.g = game

    @property
    def defs(self):
        return self.g.data.quests

    @property
    def state(self):
        return self.g.world.quests

    def status(self, qid):
        return self.state.get(qid, {}).get("status", "inactive")

    def is_state(self, qid, want):
        st = self.state.get(qid, {})
        status = st.get("status", "inactive")
        if want in ("active", "done", "failed", "inactive"):
            return status == want
        if want == "started":
            return status != "inactive"
        try:                                    # a stage number / stage id reached
            return st.get("stage", 0) >= int(want)
        except (TypeError, ValueError):
            stages = self.defs.get(qid, {}).get("stages", [])
            ids = [s.get("id") for s in stages]
            return want in ids and (status == "done" or st.get("stage", 0) >= ids.index(want))

    def start(self, qid):
        q = self.defs.get(qid)
        if not q or self.status(qid) != "inactive":
            return
        self.state[qid] = {"status": "active", "stage": 0}
        self.g.audio.sfx("quest")
        self.g.say("{quest}%s New quest:{/} {key}%s{/}" % (self.g.ui.g("flag"), q.get("title", qid)), "quest")
        if q.get("description"):
            self.g.say(q["description"], "hint")
        stage = self._stage(qid)
        if stage and stage.get("text"):
            self.g.say("%s %s" % (self.g.ui.g("arrow"), stage["text"]), "quest")

    def _stage(self, qid):
        q = self.defs.get(qid, {})
        st = self.state.get(qid, {})
        stages = q.get("stages", [])
        i = st.get("stage", 0)
        return stages[i] if 0 <= i < len(stages) else None

    def advance(self, qid, announce=True):
        q = self.defs.get(qid)
        st = self.state.get(qid)
        if not q or not st or st["status"] != "active":
            return
        stage = self._stage(qid)
        st["stage"] = st.get("stage", 0) + 1
        if stage and stage.get("do"):
            conditions.run(stage["do"], self.g)
        if st["stage"] >= len(q.get("stages", [])):
            self.complete(qid)
        elif announce and not self.g.over:
            nxt = self._stage(qid)
            if nxt and nxt.get("text"):
                self.g.audio.sfx("quest")
                self.g.say("{quest}%s %s:{/} %s" % (self.g.ui.g("flag"), q.get("title", qid), nxt["text"]), "quest")

    def complete(self, qid):
        q = self.defs.get(qid)
        if not q or self.status(qid) == "done":
            return
        self.state.setdefault(qid, {})["status"] = "done"
        self.state[qid]["stage"] = len(q.get("stages", []))
        self.g.world.flags["quest_%s_done" % qid] = True
        if self.g.over:
            return
        self.g.audio.sfx("quest_done")
        self.g.say("{quest}%s Quest complete:{/} {key}%s{/}" % (self.g.ui.g("check"), q.get("title", qid)), "quest")
        if q.get("on_complete"):
            conditions.run(q["on_complete"], self.g)

    def fail(self, qid):
        q = self.defs.get(qid)
        if not q or self.status(qid) != "active":
            return
        self.state[qid]["status"] = "failed"
        self.g.say("{error}%s Quest failed:{/} %s" % (self.g.ui.g("cross"), q.get("title", qid)), "error")
        if q.get("on_fail"):
            conditions.run(q["on_fail"], self.g)

    def update(self):
        """Called after every turn."""
        for qid, q in self.defs.items():
            if self.g.over:
                return
            status = self.status(qid)
            if status == "inactive":
                auto = q.get("auto_start")
                if auto is True or (auto not in (None, False) and conditions.check(auto, self.g)):
                    self.start(qid)
                    status = self.status(qid)
            guard = 0
            while status == "active" and guard < 12:
                stage = self._stage(qid)
                if not stage or "done_when" not in stage or not conditions.check(stage["done_when"], self.g):
                    break
                self.advance(qid)
                status = self.status(qid)
                guard += 1
            if status == "active" and q.get("fail_when") and conditions.check(q["fail_when"], self.g):
                self.fail(qid)

    def show(self):
        ui = self.g.ui
        active = [(qid, q) for qid, q in self.defs.items() if self.status(qid) == "active"]
        done = [(qid, q) for qid, q in self.defs.items() if self.status(qid) == "done"]
        failed = [(qid, q) for qid, q in self.defs.items() if self.status(qid) == "failed"]
        if not (active or done or failed):
            self.g.say("Your journal is empty.", "system")
            return
        ui.heading("JOURNAL")
        for qid, q in active:
            stages = q.get("stages", [])
            i = self.state[qid].get("stage", 0)
            lines = []
            for n, s in enumerate(stages):
                if not s.get("text") or (n > i and not q.get("show_all")):
                    continue
                if n < i:
                    lines.append("{success}%s{/} {hint}%s{/}" % (ui.g("check"), s["text"]))
                elif n == i:
                    lines.append("{quest}%s{/} %s" % (ui.g("arrow"), s["text"]))
                else:
                    lines.append("{hint}%s %s{/}" % (ui.g("dot"), s["text"]))
            ui.bullets(lines, "default", title="{quest}%s{/}" % q.get("title", qid), bullet="")
            if q.get("description"):
                self.g.say("  " + q["description"], "hint")
        if done:
            ui.bullets(["{hint}%s{/}" % q.get("title", qid) for qid, q in done], "default",
                       title="Completed", bullet=ui.g("check"))
        if failed:
            ui.bullets(["{hint}%s{/}" % q.get("title", qid) for qid, q in failed], "default",
                       title="Failed", bullet=ui.g("cross"))
