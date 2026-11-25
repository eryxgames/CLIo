# Erebus: Last Watch

The terminals demo of the CLIo engine: the last watch aboard the cargo hauler Erebus, played on
five consoles from a wheel of orders on the bridge.

| Console | What it shows of the engine |
| --- | --- |
| Reactor | Panels: gauges, a big number, lamps, plots over time; functions done at once (vent) and held (scram). |
| Scan | A model coming into a scope as it is scanned; a planet and a scan of its real relief; a beacon that unfolds as far as its key is held (a model's `tracks`, a scope's `clip` and `at`). |
| Bay 2 | A switch, a control and two held functions that have to be done in order; a hatch that is as far open as a value says, in two views. |
| Approach | The view ahead in lines as space: rocks that tumble, marks to fly by; the field of rocks as a scope. |
| Descent | The view ahead over ground, the map, and a scan of the ground under the lander. |

On the bridge `orders` opens the wheel (`menus.json`): each order is locked until the one before
is done and says why. In a console Esc (or P) is the game's menu with that console's keys; a tap
or a click on a line that names a key is that key.

```
python clio.py erebus                  # play it
python clio.py erebus --check          # check the data
python -m engine.sim games/erebus      # the autopilot does each console and says how it went
python clio.py erebus --view-model     # its models; P plays their clips
```

The story is a frame for the consoles and the names are placeholders. Everything here is data:
`sims.json` (the consoles), `models.json` (mast, beacon, bay; three haulers - the simple
`hauler` of the tests, and `hauler_heavy` and `hauler_light`, built of parts after two design
drawings), `planets.json`,
`menus.json`, `scenes.json`.
