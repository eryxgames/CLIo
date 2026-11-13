"""Built-in sound effects, described as synth voices (see synth.render_sfx).

Games can override any of these or add their own in ``sounds.json``.
"""

SFX = {
    # ---- interface
    "select":  {"wave": "square", "duty": 0.25, "freq": 880, "dur": 0.04, "vol": 0.3},
    "back":    {"wave": "square", "duty": 0.25, "freq": [660, 440], "dur": 0.06, "vol": 0.3},
    "error":   [{"wave": "square", "freq": 160, "dur": 0.09, "vol": 0.35},
                {"wave": "square", "freq": 120, "dur": 0.12, "vol": 0.35, "delay": 0.1}],
    "save":    {"notes": "c5 e5 g5 c6:2", "tempo": 420, "wave": "triangle", "vol": 0.4},
    "tick":    {"wave": "square", "duty": 0.125, "freq": 1400, "dur": 0.012, "vol": 0.18},
    "page":    {"wave": "noise", "noise_rate": 6000, "freq": 0, "dur": 0.08, "vol": 0.2, "decay": 0.07, "sustain": 0},
    "map":     {"notes": "e5 b5", "tempo": 600, "wave": "triangle", "vol": 0.35},
    # ---- world
    "step":    {"wave": "noise", "noise_rate": 1800, "freq": 0, "dur": 0.05, "vol": 0.3, "decay": 0.05, "sustain": 0},
    "door":    [{"wave": "noise", "noise_rate": 900, "freq": 0, "dur": 0.16, "vol": 0.3, "decay": 0.15, "sustain": 0},
                {"wave": "triangle", "freq": [90, 60], "dur": 0.16, "vol": 0.5}],
    "airlock": [{"wave": "noise", "noise_rate": 12000, "freq": 0, "dur": 0.5, "vol": 0.28, "attack": 0.02, "decay": 0.45, "sustain": 0},
                {"wave": "sine", "freq": [70, 45], "dur": 0.4, "vol": 0.5, "delay": 0.05}],
    "locked":  [{"wave": "square", "duty": 0.2, "freq": 220, "dur": 0.05, "vol": 0.3},
                {"wave": "square", "duty": 0.2, "freq": 220, "dur": 0.05, "vol": 0.3, "delay": 0.09}],
    "unlock":  {"notes": "g4 c5 e5:2", "tempo": 520, "wave": "square", "duty": 0.25, "vol": 0.35},
    "pickup":  {"notes": "e5 a5", "tempo": 720, "wave": "square", "duty": 0.25, "vol": 0.35},
    "drop":    {"wave": "triangle", "freq": [300, 140], "dur": 0.09, "vol": 0.45},
    "open":    {"wave": "triangle", "freq": [180, 320], "dur": 0.12, "vol": 0.45},
    "use":     {"wave": "square", "duty": 0.5, "freq": [500, 700], "dur": 0.07, "vol": 0.3},
    "craft":   {"notes": "c5 . e5 . g5 e5 c6:3", "tempo": 600, "wave": "square", "duty": 0.125, "vol": 0.32},
    "read":    {"wave": "noise", "noise_rate": 5000, "freq": 0, "dur": 0.1, "vol": 0.16, "decay": 0.1, "sustain": 0},
    "computer": {"notes": "c6 g5 c6 e6 g6 e6", "tempo": 900, "wave": "square", "duty": 0.125, "vol": 0.22},
    "power":   [{"wave": "saw", "freq": [50, 220], "dur": 0.9, "vol": 0.3, "attack": 0.3},
                {"wave": "sine", "freq": [100, 440], "dur": 0.9, "vol": 0.3, "attack": 0.3}],
    "teleport": {"wave": "sine", "freq": [200, 1600], "dur": 0.35, "vol": 0.4, "vibrato": [18, 0.05]},
    "secret":  {"notes": "g5 f#5 d#5 a4 g#4 e5 g#5 c6:3", "tempo": 520, "wave": "square", "duty": 0.25, "vol": 0.32},
    "coin":    {"notes": "b5 e6:3", "tempo": 700, "wave": "square", "duty": 0.25, "vol": 0.3},
    "quest":   {"notes": "c5 e5 g5 . c6:4", "tempo": 480, "wave": "triangle", "vol": 0.45},
    "quest_done": {"notes": "c5 e5 g5 c6 . g5 c6:5", "tempo": 500, "wave": "square", "duty": 0.25, "vol": 0.36},
    "levelup": {"notes": "c5 d5 e5 g5 c6 e6 g6:4", "tempo": 640, "wave": "square", "duty": 0.25, "vol": 0.36},
    "heal":    {"notes": "e5 g#5 b5 e6:3", "tempo": 520, "wave": "sine", "vol": 0.45},
    "trap":    [{"wave": "noise", "noise_rate": 3000, "freq": 0, "dur": 0.12, "vol": 0.4, "decay": 0.12, "sustain": 0},
                {"wave": "square", "freq": [400, 100], "dur": 0.2, "vol": 0.3}],
    "alarm":   {"notes": "a5:2 e5:2 a5:2 e5:2", "tempo": 360, "wave": "square", "duty": 0.5, "vol": 0.3},
    # ---- combat
    "encounter": {"notes": "e4 g4 a#4 e5 a#4 e5:3", "tempo": 720, "wave": "saw", "vol": 0.3},
    "hit":     [{"wave": "noise", "noise_rate": 4000, "freq": 0, "dur": 0.07, "vol": 0.45, "decay": 0.07, "sustain": 0},
                {"wave": "square", "freq": [220, 90], "dur": 0.08, "vol": 0.3}],
    "crit":    [{"wave": "noise", "noise_rate": 7000, "freq": 0, "dur": 0.12, "vol": 0.5, "decay": 0.12, "sustain": 0},
                {"wave": "square", "duty": 0.25, "freq": [900, 200], "dur": 0.16, "vol": 0.35}],
    "miss":    {"wave": "noise", "noise_rate": 14000, "freq": 0, "dur": 0.09, "vol": 0.18, "attack": 0.03, "decay": 0.06, "sustain": 0},
    "hurt":    [{"wave": "square", "freq": [180, 70], "dur": 0.16, "vol": 0.4},
                {"wave": "noise", "noise_rate": 2500, "freq": 0, "dur": 0.1, "vol": 0.3, "decay": 0.1, "sustain": 0}],
    "guard":   {"wave": "triangle", "freq": [240, 200], "dur": 0.08, "vol": 0.5},
    "focus":   {"wave": "sine", "freq": [440, 880], "dur": 0.18, "vol": 0.35},
    "special": {"wave": "saw", "freq": [300, 1200], "dur": 0.2, "vol": 0.3, "vibrato": [30, 0.04]},
    "flee":    {"notes": "g5 e5 c5 g4", "tempo": 900, "wave": "square", "duty": 0.25, "vol": 0.3},
    "enemy_down": [{"wave": "noise", "noise_rate": 2000, "freq": 0, "dur": 0.3, "vol": 0.4, "decay": 0.3, "sustain": 0},
                   {"wave": "square", "freq": [300, 40], "dur": 0.35, "vol": 0.3}],
    "win":     {"notes": "c5 c5 c5 c5:2 g#4:2 a#4:2 c5 . a#4 c5:6", "tempo": 620, "wave": "square", "duty": 0.25, "vol": 0.36},
    "lose":    {"notes": "c5:2 b4:2 a#4:2 a4:2 g#4:6", "tempo": 300, "wave": "triangle", "vol": 0.45},
    "explosion": [{"wave": "noise", "noise_rate": 1500, "freq": 0, "dur": 0.7, "vol": 0.6, "decay": 0.7, "sustain": 0},
                  {"wave": "sine", "freq": [120, 30], "dur": 0.6, "vol": 0.6}],
}


def voice_blip(pitch=220.0, wave="square", seed=0, syllables=5):
    """A short 'talking' babble for a character, as an sfx spec."""
    import random
    rnd = random.Random("voice:%s:%s" % (pitch, seed))
    voices, t = [], 0.0
    for _ in range(syllables):
        f = pitch * rnd.choice((0.84, 0.94, 1.0, 1.0, 1.12, 1.26, 1.5))
        d = rnd.choice((0.045, 0.055, 0.07))
        voices.append({"wave": wave, "duty": 0.25, "freq": [f, f * rnd.choice((0.92, 1.0, 1.08))],
                       "dur": d, "vol": 0.22, "delay": t, "attack": 0.005, "release": 0.02})
        t += d + rnd.choice((0.015, 0.03, 0.05))
    return voices
