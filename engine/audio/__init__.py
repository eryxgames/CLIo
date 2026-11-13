"""The sound system: synthesized music and effects, plus ordinary audio files.

    audio = Audio(game_dir, songs=..., sounds=...)
    audio.music("engine_room")        # a song from music.json, looped
    audio.music({"generate": {"mood": "dark", "seed": 7}})
    audio.music("music/theme.ogg")    # a real file, if a player can handle it
    audio.sfx("pickup")               # built-in or game-defined effect

Everything is optional and failure-proof: with no audio player on the machine
the calls simply do nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading

from . import synth
from .backends import INSTALL_HINTS, NullBackend, detect, platform_name
from .compose import MOODS, compose
from .sfx import SFX, voice_blip

SYNTH_VERSION = "3"
AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".oga", ".flac", ".m4a", ".aac", ".opus", ".aiff", ".wma")


def default_cache_dir(env=None):
    env = os.environ if env is None else env
    base = env.get("CLIO_CACHE") or env.get("XDG_CACHE_HOME")
    if not base:
        if os.name == "nt":
            base = env.get("LOCALAPPDATA") or os.path.expanduser("~")
        else:
            base = os.path.join(os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "clio", "audio")
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".w")
        with open(probe, "w"):
            pass
        os.remove(probe)
        return path
    except OSError:
        path = os.path.join(tempfile.gettempdir(), "clio-audio")
        os.makedirs(path, exist_ok=True)
        return path


class Audio:
    def __init__(self, game_dir=None, songs=None, sounds=None, enabled=True, backend=None,
                 cache_dir=None, env=None):
        self.game_dir = game_dir
        self.songs = dict(songs or {})
        self.sounds = dict(sounds or {})
        self.enabled = enabled
        self.music_on = True
        self.sfx_on = True
        self.music_volume = 0.6
        self.sfx_volume = 0.8
        self.env = env
        self._backend = backend
        self.note = "" if backend is None else getattr(backend, "description", "")
        self._cache_dir = cache_dir
        self._mem = {}                  # cache key -> path
        self._lock = threading.Lock()
        self._token = 0
        self.wanted = None              # the track the game asked for (canonical key)
        self._wanted_track = None
        self.playing = None
        self.last_error = ""

    # ------------------------------------------------------------------ #
    @property
    def backend(self):
        if self._backend is None:
            if not self.enabled:
                self._backend, self.note = NullBackend(), "sound disabled"
            else:
                try:
                    self._backend, self.note = detect(self.env)
                except Exception as e:            # never let audio break the game
                    self._backend, self.note = NullBackend(), "audio unavailable (%s)" % e.__class__.__name__
        return self._backend

    @property
    def available(self):
        return self.enabled and not isinstance(self.backend, NullBackend) or \
            (isinstance(self.backend, NullBackend) and self.backend.record)

    @property
    def cache_dir(self):
        if self._cache_dir is None:
            self._cache_dir = default_cache_dir(self.env)
        return self._cache_dir

    # ------------------------------------------------------------------ #
    # rendering + cache
    # ------------------------------------------------------------------ #
    def _cached(self, kind, spec, volume, render):
        blob = json.dumps([SYNTH_VERSION, synth.RATE, kind, spec, round(volume, 1)],
                          sort_keys=True, default=str)
        key = hashlib.sha1(blob.encode("utf-8")).hexdigest()[:20]
        path = self._mem.get(key)
        if path and os.path.isfile(path):
            return path
        path = os.path.join(self.cache_dir, "%s-%s.wav" % (kind, key))
        if not os.path.isfile(path) or os.path.getsize(path) < 64:
            samples = render()
            if not samples:
                return None
            tmp = "%s.%d.tmp" % (path, threading.get_ident())
            synth.write_wav(tmp, samples, gain=volume)
            os.replace(tmp, path)
        self._mem[key] = path
        return path

    def _file(self, name):
        """Resolve a game-relative audio file name to an existing path."""
        if not isinstance(name, str) or not name.lower().endswith(AUDIO_EXTS):
            return None
        for base in (self.game_dir, os.getcwd()):
            if base:
                p = name if os.path.isabs(name) else os.path.join(base, name)
                if os.path.isfile(p):
                    return p
        return None

    # ------------------------------------------------------------------ #
    # sound effects
    # ------------------------------------------------------------------ #
    def sfx(self, name, fallback=None):
        """Play a sound effect by name (or file). Never raises."""
        if not (self.enabled and self.sfx_on and name):
            return False
        try:
            if not self.available:
                return False
            path, baked = self._sfx_path(name)
            if path is None and fallback:
                path, baked = self._sfx_path(fallback)
            if path is None:
                return False
            self.backend.play(path, 1.0 if baked else self.sfx_volume)
            return True
        except Exception as e:
            self.last_error = "%s: %s" % (e.__class__.__name__, e)
            return False

    def _sfx_path(self, name):
        spec = name
        if isinstance(name, str):
            spec = self.sounds.get(name, None)
            if spec is None:
                f = self._file(name)
                if f:
                    return (f, False) if self.backend.can_play(f) else (None, False)
                spec = SFX.get(name)
            elif isinstance(spec, str):
                f = self._file(spec)
                if f and self.backend.can_play(f):
                    return f, False
                spec = SFX.get(spec) or SFX.get(name)
        if not spec:
            return None, False
        path = self._cached("sfx", spec, self.sfx_volume, lambda: synth.render_sfx(spec))
        if path and not self.backend.can_play(path):
            return None, True
        return path, True

    def voice(self, pitch=220, wave="square", seed=0):
        """A short babble in a character's 'voice'."""
        if not (self.enabled and self.sfx_on):
            return False
        return self.sfx(voice_blip(float(pitch), wave, seed))

    # ------------------------------------------------------------------ #
    # music
    # ------------------------------------------------------------------ #
    def resolve_track(self, track):
        """Normalise a track reference to ``(key, kind, payload)``."""
        if not track or track in ("off", "none", "silence"):
            return None
        if isinstance(track, dict):
            if "generate" in track:
                g = track["generate"] or {}
                payload = {"mood": g.get("mood", "mystery"), "seed": g.get("seed", 0),
                           "bars": g.get("bars", 16)}
                return ("gen:%(mood)s:%(seed)s:%(bars)s" % payload, "gen", payload)
            if "patterns" in track:
                return ("song:" + hashlib.sha1(json.dumps(track, sort_keys=True).encode()).hexdigest()[:12],
                        "song", track)
            if "file" in track:
                return self.resolve_track(track["file"])
            return None
        name = str(track)
        if name in self.songs:
            song = self.songs[name]
            if isinstance(song, str):
                return self.resolve_track(song)
            if isinstance(song, dict) and "generate" in song:
                return self.resolve_track(song)
            return ("song:" + name, "song", song)
        f = self._file(name)
        if f:
            return ("file:" + f, "file", f)
        if name.startswith("gen:"):
            parts = name.split(":")
            payload = {"mood": parts[1] if len(parts) > 1 else "mystery",
                       "seed": parts[2] if len(parts) > 2 else 0, "bars": 16}
            return ("gen:%(mood)s:%(seed)s:%(bars)s" % payload, "gen", payload)
        if name in MOODS:
            return ("gen:%s:0:16" % name, "gen", {"mood": name, "seed": 0, "bars": 16})
        return None

    def music(self, track, fallback=None):
        """Start looping a track (no-op if it is already the current one)."""
        try:
            resolved = self.resolve_track(track)
            if resolved is None and fallback:
                resolved = self.resolve_track(fallback)
            if resolved and resolved[1] == "file" and self.available \
                    and not self.backend.can_play(resolved[2]) and fallback:
                resolved = self.resolve_track(fallback) or resolved
            key = resolved[0] if resolved else None
            if key == self.wanted:
                return
            self.wanted = key
            self._wanted_track = resolved
            self._start()
        except Exception as e:
            self.last_error = "%s: %s" % (e.__class__.__name__, e)

    def stop_music(self):
        self.music(None)

    def _start(self):
        with self._lock:
            self._token += 1
            token = self._token
        resolved = self._wanted_track
        if not (self.enabled and self.music_on and self.available) or resolved is None:
            if self._backend is not None:
                self.backend.stop_loop()
            self.playing = None
            return

        def work():
            try:
                key, kind, payload = resolved
                if kind == "file":
                    path, vol = payload, self.music_volume
                else:
                    song = compose(payload["seed"], payload["mood"], payload.get("bars", 16)) \
                        if kind == "gen" else payload
                    path = self._cached("music", song if kind == "song" else payload,
                                        self.music_volume, lambda: synth.render_song(song))
                    vol = 1.0
                if path is None or token != self._token:
                    return
                if not self.backend.can_play(path):
                    self.backend.stop_loop()
                    return
                self.backend.loop(path, vol)
                self.playing = key
            except Exception as e:
                self.last_error = "%s: %s" % (e.__class__.__name__, e)

        if getattr(self.backend, "record", False):
            work()                                  # tests: deterministic, no thread
        else:
            threading.Thread(target=work, name="clio-render", daemon=True).start()

    # ------------------------------------------------------------------ #
    # settings
    # ------------------------------------------------------------------ #
    def set_music(self, on):
        self.music_on = bool(on)
        self._start()

    def set_sfx(self, on):
        self.sfx_on = bool(on)

    def set_volume(self, music=None, sfx=None):
        if sfx is not None:
            self.sfx_volume = max(0.0, min(1.0, float(sfx)))
        if music is not None:
            self.music_volume = max(0.0, min(1.0, float(music)))
            self._start()

    def status(self):
        """Human-readable lines describing the audio setup."""
        b = self.backend
        lines = []
        if isinstance(b, NullBackend) and not b.record:
            lines.append("Output: none - %s" % (self.note or "silent"))
            if "no audio player" not in self.note and self.enabled and "off" not in self.note:
                lines.append("Hint: " + INSTALL_HINTS.get(platform_name(self.env), ""))
        else:
            lines.append("Output: %s" % (self.note or b.description))
        lines.append("Music: %s (volume %d%%)" % ("on" if self.music_on else "off", round(self.music_volume * 100)))
        lines.append("Effects: %s (volume %d%%)" % ("on" if self.sfx_on else "off", round(self.sfx_volume * 100)))
        if self.wanted:
            lines.append("Track: %s" % self.wanted.split(":", 1)[-1])
        if self.last_error:
            lines.append("Last problem: %s" % self.last_error)
        return lines

    def shutdown(self):
        with self._lock:
            self._token += 1
        if self._backend is not None:
            try:
                self._backend.shutdown()
            except Exception:
                pass


class Silent(Audio):
    """An Audio that never touches the system (for tests and --no-sound)."""

    def __init__(self, *a, **k):
        k["enabled"] = False
        super().__init__(*a, **k)
