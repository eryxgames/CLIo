# A cookbook for consoles

Short answers to "how do I make...". Each is a piece of JSON that works as it stands - the test
suite builds every block marked *checked* and fails if one stops working. The reference for
every key is [AUTHORING.md](AUTHORING.md) under "Simulators" and "Menus".

Three commands do most of the looking for you:

```
python clio.py mygame --add console reactor     # paste a working console in (--add console list)
python clio.py mygame --shots out               # every console, menu and model as pictures: out/index.html
python -m engine.panels --gallery               # every widget once, with the JSON that makes it
```

## A thing that has to be held

A function with `hold` is done only when its key has been down that many seconds; its line fills
while it is held and falls back when it is let go. `uses` makes it once only.

<!-- checked: sim -->
```json
{"title": "PUMP  prime it", "mode": "systems", "time": 30,
 "functions": {"prime": {"label": "Prime the pump", "key": "k", "hold": 2, "uses": 1, "tone": "good",
                         "says": "Primed."}},
 "win_if": "prime_done >= 1",
 "panels": {"title": "PUMP", "widgets": [{"functions": true}]}}
```

A function's key is one key the console uses for nothing else (`p`, `q`, Esc and Enter are the
simulator's own; leave `key` out and the functions get `1` to `9` in order).

## A switch that drains something while it is on

A `toggle` is on at a press and off at the next. A stock (a system with a `rate`) reads it by its
name: 1 while it is on.

<!-- checked: sim -->
```json
{"title": "TANK  empty it", "mode": "systems", "time": 40,
 "functions": {"valve": {"label": "Drain valve", "key": "v", "toggle": true, "tone": "warn"}},
 "systems": {"level": {"rate": "-12 * valve", "start": 100, "min": 0, "max": 100}},
 "win_if": "level <= 0",
 "panels": {"title": "TANK", "widgets": [{"gauge": "level", "max": 100, "unit": "%"}, {"functions": true}]}}
```

## Things that have to be done in order

`if` locks a function until it holds, and `why` is what the console says when it is asked for too
early. Each function's `NAME_done` counts how often it has been done.

<!-- checked: sim -->
```json
{"title": "AIRLOCK  cycle it", "mode": "systems", "time": 60,
 "functions": {
   "seal":  {"label": "Seal inner door", "key": "s", "uses": 1},
   "bleed": {"label": "Bleed the air", "key": "b", "hold": 1.5, "if": "seal_done >= 1",
             "why": "the inner door is open", "uses": 1},
   "open":  {"label": "Open outer door", "key": "o", "hold": 1, "if": "bleed_done >= 1",
             "why": "there is still air in the lock", "uses": 1}},
 "win_if": "open_done >= 1",
 "panels": {"title": "AIRLOCK", "widgets": [
   {"lamps": [{"label": "SEALED", "if": "seal_done >= 1", "tone": "good"},
              {"label": "VACUUM", "if": "bleed_done >= 1", "tone": "warn"}]},
   {"functions": true}]}}
```

## A hatch that is as far open as a value says

Two pieces. The model moves its named parts along **tracks** (`models.json`); a scope shows it
with `"clip"` and, with `"at"`, as far through the clip as a value says - whatever the time.

<!-- checked: model -->
```json
{"materials": {"steel": {"color": "#b4bac2", "metal": 0.7, "rough": 0.45}},
 "parts": [{"shape": "box", "size": [0.15, 0.15, 2.0], "at": [0, 0, 1.0], "material": "steel"},
           {"shape": "box", "size": [1.2, 0.1, 1.9], "at": [0.65, 0, 1.0], "material": "steel", "group": "leaf"}],
 "tracks": {"open": {"length": 2, "loop": false, "parts": {
   "leaf": {"t": [0, 2], "about": [0, 0, 1.0], "turn": [[0, 0, 0], [95, 0, 0]]}}}}}
```

In a console (the model is called `door` here; `python clio.py mygame --add model door` pastes
one like it):

<!-- checked: sim with door -->
```json
{"title": "HATCH  wind it open", "mode": "systems", "time": 60,
 "controls": {"crank": {"label": "Crank", "keys": ["up", "down"], "min": 0, "max": 100, "start": 0, "step": 30}},
 "win_if": "crank >= 100",
 "panels": {"cols": [
   {"size": 34, "title": "HATCH", "widgets": [{"control": "crank", "max": 100, "keys": ["up", "down"]}]},
   {"title": "FROM INSIDE", "widgets": [
     {"scope": {"model": "door", "view": "solid", "clip": "open", "at": "crank", "whole": 100, "turn": 0, "yaw": 200}}]}]}}
```

## A device that unfolds while its key is held

A held function's `NAME_charge` goes from 0 to 1 while the key is down. Give it to a scope's `at`
and the model unfolds under the player's finger - and folds again if the key is let go too soon.
Keep it open afterwards with a value of your own:

<!-- checked: sim with door -->
```json
{"title": "PROBE  deploy it", "mode": "systems", "time": 40,
 "functions": {"deploy": {"label": "Deploy", "key": "d", "hold": 2, "uses": 1, "tone": "good"}},
 "systems": {"unfold": {"value": "max(deploy_charge, min(1, deploy_done))"}},
 "win_if": "deploy_done >= 1",
 "panels": {"cols": [
   {"size": 30, "title": "PROBE", "widgets": [{"functions": true}]},
   {"title": "PROBE", "widgets": [{"scope": {"model": "door", "view": "solid", "clip": "open", "at": "unfold"}}]}]}}
```

## A scan of the ground

`{"scan": true}` in a vehicle simulator scans its own map with the vehicle marked.
`{"scan": {"planet": "moon"}}` scans a planet of `planets.json` (give each ground of its legend a
`"height"`); `"turn"` moves the strip with a value, `"pulse"` makes the relief swell with a cue of
the music.

```json
{"title": "BELOW  relief", "widgets": [{"scan": {"planet": "moon", "unit": "KM", "turn": "time", "pulse": "hit.low"}}]}
```

## A frame that beats with the music

A panel's `"pulse"` names a cue of the track that plays (`bar`, `beat`, `hit.low`, `hit.mid`,
`hit.high` for a generated song; any action of a Playhead cue sheet beside a recording):

```json
{"title": "SIGNALS", "pulse": "bar", "widgets": [{"scope": {"scene": "signals"}}]}
```

## A wheel of orders, each locked until the one before

`menus.json`. `locked` is a condition (`!flag`: while the flag is not set) and `why` is said in
its place; `when` shows an item only while it holds, so a done order can be another item.

<!-- checked: menu -->
```json
{"title": "Orders", "look": "wheel", "hub": "Watch", "items": [
  {"id": "core", "label": "Core", "state": "ready", "when": "!core_done", "effects": [{"goto": "core"}]},
  {"id": "core_ok", "label": "Core", "state": "done", "tone": "good", "when": "core_done", "locked": "core_done",
   "why": "The core holds."},
  {"id": "scan", "label": "Scan", "state": "ready", "locked": "!core_done", "why": "No power yet: wake the core.",
   "effects": [{"goto": "scan"}]},
  {"id": "close", "label": "Stand by"}]}
```

A scene opens it with an action: `"actions": {"orders": {"do": [{"menu": "orders"}]}}`.

## One look for every console

```json
"console": "amber"
```

in `game.json`: panels' colour and frame, menus' look and frame, how models are drawn. `green`,
`amber`, `ice`, `paper`, `alert`, `violet`, or `{"like": "ice", "border": "heavy"}`. What a
console or a model says itself goes over it.

## Taps, and the pause

Nothing to write. A line that names a key is that key under a finger or a mouse - a function's
line (held as long as the finger is down), a control's line (left of the bar's middle less, right
more), `[MENU]`. Esc or P opens the game's menu over any console with that console's keys.

## A model from Blender

What CLIo takes from a glTF 2.0 file (`.glb`, or `.gltf` with its data), and how to lay a model
out so that it comes in useful. (These are the importer's rules; the tests build glTF files in
code, and no file from Blender itself has been through this version - try it on a small model
first and look at what `--import-model` says.)

| In Blender | In CLIo |
| --- | --- |
| An object with a mesh | A named **part** of the model (`mesh.parts`): its own colour in the structure and plan views, its own value in the heat view, a part a look's `groups` can colour. Name objects for what they are: `reactor`, `bridge`, `door_left`. |
| An action that moves, turns or sizes objects | A **clip** of **tracks**: a few keys for each object, played smoothly at any speed. Name actions for what they do: `open`, `deploy`; `idle`, `walk`, `attack` are the ones a monster in a level plays. |
| An armature bending a skin | A clip of **frames** of the whole mesh (four a beat, 48 at most), kept packed. |
| Materials: base colour, metallic, roughness, emission | The same. A base colour texture (PNG) or vertex colours become a colour per triangle. |
| Shape keys, JPEG textures | Not taken; the importer says so. |
| +Y up, metres | z up; `--model-scale` cells per metre (0.4: a 2.5 m room is one cell high). |

Keep it low: a few hundred triangles. A terminal picture is about 100 by 60 dots, and every
triangle is lit and filled for each frame. Parent an object to another and it moves with it; an
object sized unevenly whose child turns is sheared, and that clip falls back to frames (the
importer says which).

```
python clio.py mygame --import-model lander.glb --model-name lander
python clio.py mygame --view-model lander        # P plays its clips; V changes the view
python clio.py mygame --shots out                # and it is in the page of pictures
```
