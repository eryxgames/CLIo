# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Themes: colours, frames and text effects for every kind of message.

Theme files live in ``engine/style/configs/*.json`` (and optionally in a
game's own ``themes/`` folder).  The original CLIo schema is still read as is:
``colors`` maps a role to a colour, ``styles`` maps a role to frame / padding /
alignment / delays / effects.  CLIo 2 adds an optional ``ui`` block.
"""
from __future__ import annotations

import json
import os

BUILTIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style", "configs")

# role -> role to borrow from when a theme does not define it
FALLBACK = {
    "scene": "description", "story": "description", "title": "list_title",
    "character": "greeting", "exit": "menu", "quest": "success", "hud": "system",
    "prompt": "system", "map": "system", "reading": "description",
    "greeting": "dialogue", "ambient": "default", "item": "default",
    "combat": "warning", "warning": "error", "success": "default",
    "error": "default", "system": "default", "menu": "default",
    "list_title": "default", "list_category": "menu", "list_content": "default",
    "dialogue": "default", "description": "default", "speaker": "character",
    "choice": "menu", "hint": "ambient", "loot": "item", "damage": "error",
    "heal": "success", "intent": "warning", "key": "list_title",
}

DEFAULT_COLORS = {
    "default": "38;5;252", "description": "silver", "dialogue": "38;5;180", "greeting": "38;5;175",
    "system": "steel", "error": "bred", "warning": "amber", "success": "bgreen",
    "ambient": "gray", "item": "gold", "character": "sky", "exit": "mint",
    "menu": "38;5;146", "reading": "38;5;251", "combat": "bred", "list_title": "b sky",
    "list_category": "38;5;147", "list_content": "38;5;252", "hud": "steel", "prompt": "b white",
    "quest": "byellow", "story": "white", "scene": "b white", "title": "b sky",
    "hint": "i gray", "key": "b white",
}

DEFAULT_UI = {
    "prompt": "> ", "max_width": 78, "hud": True, "margin": 1,
    "transition": "wipe", "typewriter_cap": 1.4, "title_gradient": [39, 45, 51, 87, 123],
    "frame_color": "", "art": True,
}


class Theme:
    def __init__(self, name="default", data=None):
        data = data or {}
        self.name = name
        self.description = data.get("description", "")
        self.text_speed = float(data.get("text_speed", 0.02))
        self.padding = int(data.get("horizontal_padding", 1))
        self.colors = dict(DEFAULT_COLORS)
        self.colors.update(data.get("colors", {}))
        self._own_colors = set(data.get("colors", {}))
        self.styles = {k: dict(v) for k, v in data.get("styles", {}).items()}
        self.ui = dict(DEFAULT_UI)
        self.ui.update(data.get("ui", {}))

    # -- lookup ------------------------------------------------------------ #
    def _resolve(self, role, table):
        seen = 0
        while role not in table and role in FALLBACK and seen < 6:
            role = FALLBACK[role]
            seen += 1
        return role if role in table else None

    def color(self, role):
        r = role
        for _ in range(8):                 # a colour the theme itself defines wins
            if r in self._own_colors:
                return self.colors[r]
            if r not in FALLBACK:
                break
            r = FALLBACK[r]
        r = role
        for _ in range(8):                 # otherwise the engine default
            if r in DEFAULT_COLORS:
                return DEFAULT_COLORS[r]
            if r not in FALLBACK:
                break
            r = FALLBACK[r]
        return self.colors.get("default", "")

    def style(self, role):
        key = self._resolve(role, self.styles)
        st = self.styles.get(key, {}) if key else {}
        frame = str(st.get("frame", "NONE")).upper()
        return {
            "frame": frame,
            "padding": int(st.get("padding", self.padding)),
            "alignment": st.get("alignment", "left"),
            "character_delay": float(st.get("character_delay", 0) or 0),
            "paragraph_delay": float(st.get("paragraph_delay", 0) or 0),
            "fade_in": bool(st.get("fade_in", False)),
            "gradient": st.get("gradient", False),
            "flash": bool(st.get("flash", st.get("flash_effect", False))),
            "glitch": bool(st.get("glitch", False)),
            "animate_frame": bool(st.get("animate_frame", False)),
        }

    def roles(self):
        """Every role name with its colour spec (for inline ``{role}`` markup)."""
        names = set(DEFAULT_COLORS) | set(FALLBACK) | set(self.colors)
        return {n: self.color(n) for n in names}


def theme_dirs(game_dir=None):
    dirs = []
    if game_dir:
        dirs.append(os.path.join(game_dir, "themes"))
    dirs.append(BUILTIN_DIR)
    return dirs


def available_themes(game_dir=None):
    names = []
    for d in theme_dirs(game_dir):
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".json") and f[:-5] not in names:
                    names.append(f[:-5])
    return names


def load_theme(name, game_dir=None):
    name = (name or "default").replace(".json", "")
    for d in theme_dirs(game_dir):
        path = os.path.join(d, name + ".json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return Theme(name, json.load(f))
    return Theme(name if name == "default" else "default", {})
