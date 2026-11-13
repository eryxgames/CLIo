# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 Daniel Sandner
"""Audio output backends.

CLIo does not link against any audio library.  It renders WAV files and hands
them to whatever the machine already has:

* ``pygame`` if it happens to be installed (optional, never required)
* a command-line player found on PATH - PipeWire/PulseAudio/ALSA on Linux,
  ``afplay`` on macOS, ``play-audio`` / ``mpv`` / ``termux-media-player`` on
  Termux, and the usual ``mpv`` / ``ffplay`` / ``sox`` / ``vlc`` anywhere
* the Windows multimedia API (MCI) through ctypes
* nothing at all - the game simply stays silent

Set ``CLIO_AUDIO`` to pick one by name (``aplay``, ``mpv``, ``pygame`` ...),
to ``off`` for silence, or to a full command such as ``"myplayer --quiet {file}"``.
"""
from __future__ import annotations

import atexit
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time

from ..term import is_termux

WAV = (".wav",)
COMMON = (".wav", ".mp3", ".ogg", ".oga", ".flac", ".m4a", ".aac", ".opus", ".aiff")

# name -> (argv template, extensions, volume flag builder or None)
CLI_PLAYERS = {
    "pw-play": (["pw-play", "{file}"], (".wav", ".flac", ".ogg", ".oga", ".aiff"),
                lambda v: ["--volume=%.2f" % v]),
    "paplay": (["paplay", "{file}"], (".wav", ".flac", ".ogg", ".oga", ".aiff"),
               lambda v: ["--volume=%d" % int(65536 * v)]),
    "aplay": (["aplay", "-q", "{file}"], WAV, None),
    "afplay": (["afplay", "{file}"], (".wav", ".mp3", ".m4a", ".aac", ".aiff", ".flac"),
               lambda v: ["-v", "%.2f" % v]),
    "play-audio": (["play-audio", "{file}"], COMMON, None),
    "mpv": (["mpv", "--no-video", "--really-quiet", "--no-terminal", "{file}"], COMMON,
            lambda v: ["--volume=%d" % int(100 * v)]),
    "ffplay": (["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "{file}"], COMMON,
               lambda v: ["-volume", "%d" % int(100 * v)]),
    "play": (["play", "-q", "{file}"], (".wav", ".flac", ".ogg", ".aiff", ".mp3"),
             lambda v: ["-v", "%.2f" % v]),
    "cvlc": (["cvlc", "--play-and-exit", "--quiet", "--intf", "dummy", "{file}"], COMMON, None),
    "mpg123": (["mpg123", "-q", "{file}"], (".mp3",), None),
    "ogg123": (["ogg123", "-q", "{file}"], (".ogg", ".oga", ".flac"), None),
    "gst-play-1.0": (["gst-play-1.0", "--quiet", "--no-interactive", "{file}"], COMMON, None),
}

ORDER_LINUX = ["pw-play", "paplay", "aplay", "mpv", "ffplay", "play", "cvlc", "gst-play-1.0",
               "mpg123", "ogg123"]
ORDER_TERMUX = ["play-audio", "mpv", "paplay", "ffplay", "play", "cvlc", "mpg123"]
ORDER_MAC = ["afplay", "mpv", "ffplay", "play", "cvlc", "mpg123"]
ORDER_WINDOWS = ["mpv", "ffplay", "cvlc"]

INSTALL_HINTS = {
    "termux": "pkg install play-audio   (or: pkg install mpv)",
    "linux": "install one of: pipewire (pw-play), pulseaudio-utils (paplay), alsa-utils (aplay), mpv",
    "mac": "afplay ships with macOS - check that /usr/bin is on PATH",
    "windows": "no extra software needed; if sound is missing, install mpv or ffmpeg",
}


def platform_name(env=None):
    if is_termux(env):
        return "termux"
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


class Backend:
    """Interface. ``play`` is fire-and-forget; ``loop`` repeats until stopped."""
    name = "none"
    description = "silent"

    def can_play(self, path):
        return False

    def play(self, path, volume=1.0):
        pass

    def loop(self, path, volume=1.0):
        pass

    def stop_loop(self):
        pass

    def shutdown(self):
        self.stop_loop()


class NullBackend(Backend):
    """Silence. Also records what would have been played (used by the tests)."""
    name = "none"

    def __init__(self, record=False):
        self.record = record
        self.log = []

    def can_play(self, path):
        return self.record

    def play(self, path, volume=1.0):
        if self.record:
            self.log.append(("play", path))

    def loop(self, path, volume=1.0):
        if self.record:
            self.log.append(("loop", path))

    def stop_loop(self):
        if self.record:
            self.log.append(("stop", None))


class CliBackend(Backend):
    """Plays files by spawning command-line players (several may be combined)."""

    def __init__(self, players, max_sfx=4):
        # players: list of (name, argv, exts, volfn) in priority order
        self.players = players
        self.name = players[0][0]
        self.description = "command-line player: " + ", ".join(p[0] for p in players)
        self.max_sfx = max_sfx
        self._sfx = []
        self._loop_proc = None
        self._loop_thread = None
        self._loop_token = 0
        self._lock = threading.Lock()
        atexit.register(self.shutdown)

    def _player_for(self, path):
        ext = os.path.splitext(path)[1].lower()
        for p in self.players:
            if ext in p[2]:
                return p
        return None

    def can_play(self, path):
        return self._player_for(path) is not None

    def _spawn(self, path, volume):
        p = self._player_for(path)
        if p is None:
            return None
        _name, argv, _exts, volfn = p
        cmd = []
        for a in argv:
            if a == "{file}":
                if volfn and abs(volume - 1.0) > 0.01:
                    cmd.extend(volfn(max(0.0, min(1.5, volume))))
                cmd.append(path)
            else:
                cmd.append(a.replace("{file}", path))
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                  "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000        # CREATE_NO_WINDOW
        try:
            return subprocess.Popen(cmd, **kwargs)
        except (OSError, ValueError):
            return None

    def play(self, path, volume=1.0):
        with self._lock:
            self._sfx = [p for p in self._sfx if p.poll() is None]
            if len(self._sfx) >= self.max_sfx:
                return
            proc = self._spawn(path, volume)
            if proc:
                self._sfx.append(proc)

    def loop(self, path, volume=1.0):
        self.stop_loop()
        with self._lock:
            self._loop_token += 1
            token = self._loop_token

        def run():
            failures = 0
            while True:
                with self._lock:
                    if token != self._loop_token:
                        return
                    proc = self._spawn(path, volume)
                    self._loop_proc = proc
                if proc is None:
                    return
                started = time.time()
                proc.wait()
                with self._lock:
                    if token != self._loop_token:
                        return
                # a player that dies instantly is broken: do not spin
                if time.time() - started < 0.4:
                    failures += 1
                    if failures >= 3:
                        return
                    time.sleep(0.5)
                else:
                    failures = 0

        t = threading.Thread(target=run, name="clio-music", daemon=True)
        self._loop_thread = t
        t.start()

    def stop_loop(self):
        with self._lock:
            self._loop_token += 1
            proc, self._loop_proc = self._loop_proc, None
        _kill(proc)

    def shutdown(self):
        self.stop_loop()
        with self._lock:
            procs, self._sfx = self._sfx, []
        for p in procs:
            _kill(p)


def _kill(proc):
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                proc.kill()
    except OSError:
        pass


class TermuxMediaBackend(Backend):
    """``termux-media-player`` (Termux:API): one stream, used for music only."""
    name = "termux-media-player"
    description = "Termux:API media player (music only)"

    def __init__(self):
        self._token = 0
        self._lock = threading.Lock()
        atexit.register(self.shutdown)

    def can_play(self, path):
        return os.path.splitext(path)[1].lower() in COMMON

    def _run(self, *args):
        try:
            return subprocess.run(["termux-media-player"] + list(args), stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None

    def play(self, path, volume=1.0):
        pass                                # would cut the music off; stay quiet

    def loop(self, path, volume=1.0):
        with self._lock:
            self._token += 1
            token = self._token

        def run():
            while token == self._token:
                self._run("play", path)
                time.sleep(1.0)
                while token == self._token:
                    r = self._run("info")
                    if r is None or b"Playing" not in (r.stdout or b""):
                        break
                    time.sleep(1.0)

        threading.Thread(target=run, name="clio-music", daemon=True).start()

    def stop_loop(self):
        with self._lock:
            self._token += 1
        self._run("stop")


class PygameBackend(Backend):
    """Optional: uses pygame.mixer when pygame is installed."""
    name = "pygame"
    description = "pygame mixer"

    def __init__(self):
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame                                   # noqa: F401 (optional dependency)
        self.pg = pygame
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=1024)
        self._cache = {}
        atexit.register(self.shutdown)

    def can_play(self, path):
        return os.path.splitext(path)[1].lower() in (".wav", ".ogg", ".mp3", ".flac")

    def play(self, path, volume=1.0):
        try:
            snd = self._cache.get(path)
            if snd is None:
                snd = self._cache[path] = self.pg.mixer.Sound(path)
            snd.set_volume(max(0.0, min(1.0, volume)))
            snd.play()
        except Exception:
            pass

    def loop(self, path, volume=1.0):
        try:
            self.pg.mixer.music.load(path)
            self.pg.mixer.music.set_volume(max(0.0, min(1.0, volume)))
            self.pg.mixer.music.play(-1, fade_ms=400)
        except Exception:
            pass

    def stop_loop(self):
        try:
            self.pg.mixer.music.fadeout(300)
        except Exception:
            pass

    def shutdown(self):
        try:
            self.pg.mixer.music.stop()
            self.pg.mixer.quit()
        except Exception:
            pass


class WindowsBackend(Backend):
    """Windows MCI (winmm) via ctypes: mixes several sounds, loops music.

    MCI devices belong to the thread that opened them, so every command goes
    through one worker thread.
    """
    name = "winmm"
    description = "Windows multimedia (MCI)"

    def __init__(self):
        import ctypes
        import queue
        self._winmm = ctypes.windll.winmm
        self._ctypes = ctypes
        self._q = queue.Queue()
        self._n = 0
        self._open = []
        self._music = None
        threading.Thread(target=self._worker, name="clio-audio", daemon=True).start()
        atexit.register(self.shutdown)

    def _mci(self, command):
        buf = self._ctypes.create_unicode_buffer(256)
        err = self._winmm.mciSendStringW(command, buf, 255, 0)
        return err, buf.value

    def _worker(self):
        while True:
            job = self._q.get()
            if job is None:
                for alias in list(self._open):
                    self._mci("close %s" % alias)
                return
            kind, path, volume = job
            try:
                if kind == "stop":
                    if self._music:
                        self._mci("close %s" % self._music)
                        if self._music in self._open:
                            self._open.remove(self._music)
                        self._music = None
                    continue
                # close finished one-shots
                for alias in list(self._open):
                    if alias != self._music and self._mci("status %s mode" % alias)[1] != "playing":
                        self._mci("close %s" % alias)
                        self._open.remove(alias)
                self._n += 1
                alias = "clio%d" % self._n
                err, _ = self._mci('open "%s" type mpegvideo alias %s' % (path, alias))
                if err:
                    continue
                self._open.append(alias)
                self._mci("setaudio %s volume to %d" % (alias, int(1000 * max(0.0, min(1.0, volume)))))
                if kind == "loop":
                    if self._music:
                        self._mci("close %s" % self._music)
                        if self._music in self._open:
                            self._open.remove(self._music)
                    self._music = alias
                    self._mci("play %s repeat" % alias)
                else:
                    self._mci("play %s" % alias)
            except Exception:
                pass

    def can_play(self, path):
        return os.path.splitext(path)[1].lower() in (".wav", ".mp3", ".wma", ".aiff", ".m4a")

    def play(self, path, volume=1.0):
        self._q.put(("play", os.path.abspath(path), volume))

    def loop(self, path, volume=1.0):
        self._q.put(("loop", os.path.abspath(path), volume))

    def stop_loop(self):
        self._q.put(("stop", None, 0))

    def shutdown(self):
        self._q.put(None)


class ChainBackend(Backend):
    """Tries several backends in turn for each file (first that can play it)."""

    def __init__(self, backends):
        self.backends = backends
        self.name = "+".join(b.name for b in backends)
        self.description = "; ".join(b.description for b in backends)
        self._looping = None

    def _pick(self, path, for_loop=False):
        for b in self.backends:
            if b.can_play(path):
                return b
        return None

    def can_play(self, path):
        return self._pick(path) is not None

    def play(self, path, volume=1.0):
        b = self._pick(path)
        if b:
            b.play(path, volume)

    def loop(self, path, volume=1.0):
        self.stop_loop()
        b = self._pick(path, True)
        if b:
            self._looping = b
            b.loop(path, volume)

    def stop_loop(self):
        if self._looping:
            self._looping.stop_loop()
            self._looping = None

    def shutdown(self):
        for b in self.backends:
            b.shutdown()


def detect(env=None, which=shutil.which):
    """Pick the best available backend. Returns ``(backend, note)``."""
    env = os.environ if env is None else env
    choice = (env.get("CLIO_AUDIO") or "").strip()
    plat = platform_name(env)

    if choice.lower() in ("off", "none", "0", "no", "false", "silent"):
        return NullBackend(), "sound is switched off (CLIO_AUDIO=%s)" % choice
    if choice and ("{file}" in choice or " " in choice):
        argv = shlex.split(choice)
        if "{file}" not in argv:
            argv.append("{file}")
        if which(argv[0]):
            return CliBackend([("custom", argv, COMMON, None)]), "custom player: " + argv[0]
        return NullBackend(), "CLIO_AUDIO player not found: " + argv[0]

    def cli(names):
        found = []
        for n in names:
            if n in CLI_PLAYERS and which(CLI_PLAYERS[n][0][0]):
                argv, exts, volfn = CLI_PLAYERS[n]
                found.append((n, argv, exts, volfn))
        return found

    if choice:
        low = choice.lower()
        if low == "pygame":
            try:
                return PygameBackend(), "pygame mixer"
            except Exception as e:
                return NullBackend(), "pygame is not usable (%s)" % e.__class__.__name__
        if low in ("winmm", "mci", "windows") and plat == "windows":
            try:
                return WindowsBackend(), "Windows multimedia"
            except Exception:
                return NullBackend(), "Windows multimedia is not usable"
        if low == "termux-media-player" and which("termux-media-player"):
            return TermuxMediaBackend(), "Termux:API media player"
        found = cli([choice])
        if found:
            return CliBackend(found), "command-line player: " + choice
        return NullBackend(), "requested player '%s' was not found" % choice

    # ---- automatic selection
    import importlib.util
    try:
        has_pygame = importlib.util.find_spec("pygame") is not None
    except (ImportError, ValueError):
        has_pygame = False
    if has_pygame and not env.get("CLIO_NO_PYGAME"):
        try:
            return PygameBackend(), "pygame mixer"
        except Exception:
            pass
    order = {"termux": ORDER_TERMUX, "mac": ORDER_MAC, "windows": ORDER_WINDOWS}.get(plat, ORDER_LINUX)
    found = cli(order)
    backends = []
    if plat == "windows":
        try:
            backends.append(WindowsBackend())
        except Exception:
            pass
    if found:
        backends.append(CliBackend(found))
    if plat == "termux" and not found and which("termux-media-player"):
        backends.append(TermuxMediaBackend())
    if not backends:
        return NullBackend(), "no audio player found - " + INSTALL_HINTS.get(plat, "")
    if len(backends) == 1:
        return backends[0], backends[0].description
    chain = ChainBackend(backends)
    return chain, chain.description
