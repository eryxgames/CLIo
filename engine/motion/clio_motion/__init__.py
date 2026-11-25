# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Daniel Sandner
"""CLIo Motion: characters that move by rule, not by keyframe.  Pure Python, standard library only.

Stage 1 is the numeric kernel (springs, two-bone IK, the gait rules) with the built-in characters as data;
stage 2 is the ground step (``create_state``, ``step_ground``): legs and hips for every character; stage 3 is
the whole body on the ground (``step``), for every character: weapons, actions, spines, tails, claws, arms.
Stage 4 is off the ground: swimming, flight, the ladder, the ledge, the ragdoll and riding.  Stage 5 is showing
it: the skeleton of a pose (``rig``), clips recorded from the core (``clips``), a stand-in model in triangles
(``mesh``).  Each stage is checked against the JavaScript reference.
Source: https://github.com/eryxgames/clio-motion
"""
from __future__ import annotations

import json
import os

from .body import KITS, PROPS, start_reload, upper_body
from . import clips, mesh, rig
from .ground import STYLE, State, create_state, pose_to_world, step_ground
from .modes import (Ladder, dismount, enter_fly, enter_ladder, enter_swim, grab_ledge, leave_fly, leave_ladder, leave_swim, mount_up, place, stand, step, step_fly,
                    step_ladder, step_ledge, step_swim)
from .kernel import (G, TAU, GaitState, Spring, clamp, decay, ease, frac, gait_params, idle_noise, idle_period,
                     ik2, lerp, lob, reach_chain, smooth, wrap_pi)

__version__ = "0.23.0"
__all__ = ["rig", "clips", "mesh", "G", "TAU", "GaitState", "STYLE", "Spring", "State", "characters", "create_state", "step_ground", "step", "upper_body", "start_reload", "pose_to_world", "KITS", "PROPS", "Ladder", "enter_fly", "enter_ladder", "enter_swim", "grab_ledge", "leave_fly", "leave_ladder", "leave_swim", "place", "stand", "mount_up", "dismount",
           "step_fly", "step_ladder", "step_ledge", "step_swim", "clamp", "decay", "ease", "frac", "gait_params",
           "idle_noise", "idle_period", "ik2", "lerp", "lob", "reach_chain", "smooth", "wrap_pi"]

_characters = None


def characters():
    """The built-in characters, by id: the same data the JavaScript and C versions use."""
    global _characters
    if _characters is None:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "characters.json"), encoding="utf-8") as f:
            _characters = json.load(f)
    return _characters
