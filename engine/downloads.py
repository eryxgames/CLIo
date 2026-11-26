# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""The optional downloads, offered from the launcher: CLIo Picture (faster first-person pictures), CLIo Motion's C
core (crowds of bodies run live) and Ballistic's C engine (sounds without Node.js) - the same as
``--get-picture``, ``--get-motion`` and ``--get-ballistic``, asked about first, with the size and where it comes
from. Nothing is downloaded unless the player says yes; CLIo plays without any of them.
"""
from __future__ import annotations

import os

from .term import is_termux

# the release zips' sizes, for asking first (bytes; from the releases CLIo follows)
PICTURE_SIZE = {
    "android-arm64-v8a": 74778, "android-armeabi-v7a": 75937, "android-x86_64": 77768, "linux-arm64": 70521,
    "linux-x64": 72449, "macos-universal": 117616, "windows-arm64": 109058, "windows-x64": 126736,
}
MOTION_SIZE = {
    "android-arm64-v8a": 175625, "android-armeabi-v7a": 169959, "android-x86_64": 179903, "linux-arm64": 174114,
    "linux-x64": 184871, "macos-universal": 287304, "windows-arm64": 202323, "windows-x64": 228687,
}
BALLISTIC_SIZE = {
    "android-arm64-v8a": 1206755, "android-armeabi-v7a": 1111941, "android-x86_64": 1332340, "linux-arm64": 703726,
    "linux-x64": 796846, "macos-universal": 1289301, "windows-arm64": 596742, "windows-x64": 561021,
}


def size_text(n):
    """45 KB, 1.2 MB."""
    if n is None:
        return "size unknown"
    if n < 1000 * 1000:
        return "%d KB" % max(1, round(n / 1000.0))
    return "%.1f MB" % (n / 1000.0 / 1000.0)


def node_hint(env=None):
    """How to get Node.js here, in a few words."""
    env = os.environ if env is None else env
    if is_termux(env):
        return "pkg install nodejs"
    if os.name == "nt":
        return "from nodejs.org"
    return "from nodejs.org or your package manager"


class Offer:
    """One download: what it is, how big, whether it is here already, and the function that gets it."""

    def __init__(self, key, name, what, release, size, source, here, get):
        self.key, self.name, self.what, self.release = key, name, what, release
        self.size, self.source, self.here, self.get = size, source, here, get

    def label(self):
        state = "installed" if self.here else size_text(self.size)
        return "%s %s - %s (%s)" % (self.name, self.release, self.what, state)

    def question(self, plat):
        return ("Download %s %s for %s (%s) from %s? It is checked against its SHA-256 before anything is "
                "installed, into CLIo's data folder." % (self.name, self.release, plat, size_text(self.size),
                                                         self.source.replace("https://", "")))


def offers(env=None, plat=None):
    """What can be downloaded for this machine: ``[Offer]`` (none where no release is listed for it)."""
    from . import web
    if web.in_browser():                                  # a page cannot fetch and load a library
        return []
    from .audio import ballistic
    from .audio.ballistic import fetch as ballistic_fetch
    from .picture import fetch as picture_fetch
    plat = plat or ballistic_fetch.platform_name()
    out = []
    if plat in picture_fetch.SHA256:
        here = bool(picture_fetch.installed(env, plat)) or bool(_picture_found(env))
        out.append(Offer("picture", "CLIo Picture", "faster first-person pictures", picture_fetch.RELEASE,
                         PICTURE_SIZE.get(plat), picture_fetch.SOURCE, here,
                         lambda out_fn: picture_fetch.get(out=out_fn, env=env, plat=plat)))
    from .motion import fetch as motion_fetch
    if plat in motion_fetch.SHA256:
        here = bool(motion_fetch.installed(env, plat)) or bool(_motion_found(env))
        out.append(Offer("motion", "CLIo Motion", "crowds of bodies run live", motion_fetch.RELEASE,
                         MOTION_SIZE.get(plat), motion_fetch.SOURCE, here,
                         lambda out_fn: motion_fetch.get(out=out_fn, env=env, plat=plat)))
    if plat in ballistic_fetch.SHA256:
        here = bool(ballistic_fetch.installed(env, plat)) or bool(ballistic.find_clib(env))
        source = getattr(ballistic_fetch, "SOURCE", "https://github.com/eigensoundlab/ballistic-engine")
        out.append(Offer("ballistic", "Ballistic's C engine", "sounds without Node.js", ballistic_fetch.RELEASE,
                         BALLISTIC_SIZE.get(plat), source, here,
                         lambda out_fn: ballistic_fetch.get(out=out_fn, env=env, plat=plat)))
    return out


def _picture_found(env):
    from . import picture
    try:
        return picture.find_lib(env)
    except Exception:
        return None


def _motion_found(env):
    from . import motion
    try:
        return motion.find_lib(env)
    except Exception:
        return None


def wanted(env=None, plat=None):
    """Whether the launcher offers downloads: something for this machine is not here yet."""
    return any(not o.here for o in offers(env, plat))


def menu(term, ui, env=None, plat=None):
    """The launcher's Downloads: pick one, say yes, and it is fetched and checked; Node.js is only explained."""
    from .audio import ballistic
    from .audio.ballistic import fetch as ballistic_fetch
    plat = plat or ballistic_fetch.platform_name()
    while True:
        got = offers(env, plat)
        node = ballistic.find_node(env)
        labels = ["{key}%s{/}" % o.label() for o in got]
        labels.append("{key}Node.js{/} {hint}%s all of Ballistic's sounds - %s{/}"
                      % (ui.g("dot"), "found" if node else node_hint(env)))
        pick = ui.menu(labels, title="Optional downloads (CLIo plays without them):", cancel_label="Back")
        if pick is None:
            return
        if pick == len(got):
            if node:
                ui.say("Node.js is here (%s): every Ballistic sound can be made." % node, "hint")
            else:
                ui.say("Node.js makes every Ballistic sound; Ballistic's C engine makes some of them without it. "
                       "Get Node.js %s, then start the game again." % node_hint(env), "hint")
            ui.pause()
            continue
        o = got[pick]
        if o.here and not ui.confirm("%s %s is installed already. Download it again?" % (o.name, o.release)):
            continue
        if not o.here and not ui.confirm(o.question(plat)):
            continue
        lines = []
        code = o.get(lines.append)
        for line in lines:
            ui.say(line, "hint" if code == 0 else "alert")
        ui.pause()
