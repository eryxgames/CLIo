# A station starter

Three consoles of a ship's bridge: the helm (a hopper flown to a pad), the reactor (a core brought
to power) and the scan (a beam held on a drifting target while a 3D model comes into the scope).
Each is a CLIo simulator (`sims.json`) with a screen of its own under `"panels"`: frames, gauges,
big numbers, lamps, plots over time, a map, and vector scopes. The consoles do things when asked
(`"functions"`): the reactor vents steam (`V`) and scrams (hold `X`); the scan narrows its beam
(`N`) and is done by deploying a beacon (hold `B`) once the picture is whole; the helm flushes its
coolant (`F`).

```
python clio.py templates/station            # play it
python clio.py templates/station --check    # check the data
python -m engine.sim templates/station      # the autopilot plays each sim and says how it went
```

Copy the folder to `games/yourgame/` and change it. The panels and the functions are described
in `docs/AUTHORING.md` under "Simulators", the menus (`menu`, `options`) under "Menus".
