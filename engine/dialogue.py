# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Conversations: branching dialogue trees.

    "robot": {
      "start": [{"if": "robot_fixed", "node": "thanks"}, "hello"],
      "nodes": {
        "hello": {
          "text": "Beep! A visitor. I am UNIT-7.",
          "choices": [
            {"text": "What happened here?", "say": "Everyone left in a hurry.", "once": true},
            {"text": "Can you open the door?", "if": "!door_open", "goto": "door"},
            {"text": "Take this.", "if": "has:battery", "do": [{"take": "battery"}], "goto": "thanks"}
          ]
        },
        "door": {"text": "I need a new battery first.", "do": [{"quest": ["battery", "start"]}], "goto": "hello"},
        "thanks": {"text": "Thank you, friend."}
      }
    }

A choice may answer inline with ``say`` and stay on the node, jump with
``goto`` (a node name, ``"end"`` or ``"back"``), run effects with ``do``, be
conditional with ``if`` and disappear after use with ``once``.  A node with
``goto`` and no choices continues automatically; a node with neither ends the
conversation.  The original flat ``dialogue_options`` format still works.
"""
from __future__ import annotations

import zlib

from . import conditions

MAX_STEPS = 200


def legacy_tree(char, texts):
    """Build a one-node tree from the original ``dialogue_options`` format."""
    dlg = char.get("dialogue") if isinstance(char.get("dialogue"), dict) else {}
    greet = dlg.get("greet") or char.get("greeting") or "..."
    choices = []
    for opt, resp in (char.get("dialogue_options") or {}).items():
        text = resp
        if isinstance(resp, str) and " " not in resp.strip():
            # the old data sometimes stored a text key instead of the line
            entry = texts.get(resp)
            text = entry.get("text") if isinstance(entry, dict) else (dlg.get(resp.split("_")[-1]) or "")
            if not text:
                text = dlg.get("calm_down") or dlg.get("objective") or "..."
        choices.append({"text": opt, "say": text})
    for opt, rw in (char.get("dialogue_rewards") or {}).items():
        flag = "reward:%s:%s" % (char.get("id"), opt)
        choices.append({
            "text": opt, "if": "!" + flag,
            "do": [{"if": rw.get("required_progress") or True,
                    "then": [{"say": rw.get("success_message", "Here, take this."), "style": "dialogue"},
                             {"give": rw.get("item")}, {"set": flag}],
                    "else": [{"say": rw.get("failure_message", "Not yet."), "style": "dialogue"}]}],
        })
    if not choices:
        return {"start": "root", "nodes": {"root": {"text": greet}}}
    return {"start": "root", "nodes": {"root": {"text": greet, "choices": choices}}}


def _start_node(tree, g):
    start = tree.get("start")
    nodes = tree.get("nodes", {})
    if isinstance(start, list):
        for entry in start:
            if isinstance(entry, str):
                return entry
            if conditions.check(entry.get("if"), g):
                return entry.get("node") or entry.get("goto")
        return None
    if start in nodes:
        return start
    return next(iter(nodes), None)


def _node_text(node, g):
    for v in node.get("variants", []) or []:
        if conditions.check(v.get("if"), g):
            return v.get("text")
    return node.get("text")


def run_dialogue(g, char, tree=None):
    """Run a conversation with a character. Returns when it ends."""
    ui = g.ui
    if tree is None:
        tid = char.get("dialogue_tree")
        tree = g.data.dialogues.get(tid) if tid else None
        if tree is None:
            tree = g.data.dialogues.get(char.get("template") or char["id"])
        if tree is None:
            tree = legacy_tree(char, g.data.texts)
    nodes = tree.get("nodes", {})
    node_id = _start_node(tree, g)
    cid = char.get("template") or char["id"]
    name = char.get("name", "?")
    portrait = g.art_lines(char.get("portrait"), 18, 9)
    voice = char.get("voice") or {}
    pitch = voice.get("pitch") or (140 + zlib.crc32(cid.encode()) % 260)
    wave = voice.get("wave", "square")
    ctx = {"end": False, "char": char["id"]}
    history = []
    first = True
    show_text = True
    steps = 0

    def gone():
        return ctx["end"] or g.over or not g.char_here(char["id"])

    while node_id and node_id in nodes and steps < MAX_STEPS and not g.over:
        steps += 1
        node = nodes[node_id]
        if show_text:
            text = _node_text(node, g)
            if text:
                g.audio.voice(pitch, wave, steps)
                g.dialogue_box(node.get("speaker", name), text, portrait if first else None)
                first = False
            if node.get("do"):
                conditions.run(node["do"], g, ctx)
                if gone():
                    break
        show_text = True
        choices = []
        for i, ch in enumerate(node.get("choices", []) or []):
            flag = "dlg:%s:%s:%d" % (cid, node_id, i)
            if ch.get("once") and g.world.flags.get(flag):
                continue
            if not conditions.check(ch.get("if"), g):
                continue
            choices.append((flag, ch))
        if not choices:
            nxt = node.get("goto")
            if nxt == "back" and history:
                node_id = history.pop()
            elif nxt and nxt not in ("end", "back"):
                history.append(node_id)
                node_id = nxt
            else:
                break
            continue
        labels = []
        for _flag, ch in choices:
            label = ch.get("text", "...")
            if ch.get("tag"):
                label += " {hint}[%s]{/}" % ch["tag"]
            labels.append(label)
        leave = None if node.get("no_exit") else node.get("exit_text", "Leave")
        pick = ui.menu(labels, role="choice", cancel=leave is not None, cancel_label=leave)
        if pick is None:
            if node.get("on_exit"):
                conditions.run(node["on_exit"], g, ctx)
            break
        flag, ch = choices[pick]
        if ch.get("once"):
            g.world.flags[flag] = True
        if ch.get("say"):
            g.audio.voice(pitch, wave, steps + 50)
            g.dialogue_box(ch.get("speaker", name), ch["say"], None)
        if ch.get("do"):
            conditions.run(ch["do"], g, ctx)
        if gone():
            break
        nxt = ch.get("goto")
        if nxt == "end":
            break
        if nxt == "back":
            if history:
                node_id = history.pop()
        elif nxt:
            history.append(node_id)
            node_id = nxt
        else:
            show_text = False            # stay here; do not repeat the node's line
    g.world.flags["talked:%s" % cid] = True
