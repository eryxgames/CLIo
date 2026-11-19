# Ballistic's sound engine in CLIo

Sound effects modelled from physics: shots, ricochets, blasts, impacts, arcs, energy fields. They come from
[Ballistic Foley Lab](https://github.com/eigensoundlab/ballistic), by the same author and under the same licence
(Apache-2.0).

| File | What it is |
| --- | --- |
| `engine.js` | A copy of Ballistic's `src/engine.js`, unchanged: version 0.1.0, commit `45a3f91` (2026-11-16) |
| `render.cjs` | Runs the engine in Node.js: a request per line in, an answer per line out, a WAV per take |
| `__init__.py` | The Python side: which takes are ready, which to play next, rendering in the background, baking |

How a game uses it is in [docs/AUTHORING.md](../../../docs/AUTHORING.md), under *Sound and music*.

## Updating the engine

1. Copy `src/engine.js` from Ballistic over `engine.js`, and note its version and commit above.
2. Run `python -m unittest tests.test_ballistic`. The tests render every sound of RØØTLESS's set and check that
   `known()` (the presets and parameters read from `engine.js` for `--check`) matches what the engine reports.
3. A new engine renders every take again, by itself: its hash is part of each take's name in the cache. A game's
   baked takes count as out of date: with Node the game renders fresh ones instead, without Node it plays the
   baked ones. `--bake-sounds` brings them up to date.

## Without Node.js

Nothing breaks. A sound from Ballistic plays its baked takes if the game has them, else the spec's `"fallback"`,
else the game's own sound of the same name, else nothing. The `sound` command says what was found.

A portable C version of the engine, for game engines and for playing without Node, is being written in
[eigensoundlab/ballistic-engine](https://github.com/eigensoundlab/ballistic-engine).
