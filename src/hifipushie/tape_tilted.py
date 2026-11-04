"""A TILTED GIRTH (C359), for any body: a tape round a limb's root in the plane through two landmarks, the way a tailor
takes an armhole: over the shoulder point and under the arm. {"name", "kind": "girth", "through": [A, B], "around":
"arm.L"}: the plane holds A and B and faces along the limb (its normal is the limb's direction, square to A -> B);
the tape is the section's convex hull (it bridges the creases). t s3-1..s3-4: a girth square to the arm near its top
runs into the body, so the armhole was a sum of two arcs; the loop gives the same length (Garrett 405 mm, the arcs 403;
0.42-0.44 of the chest on four bodies) as one tape.

ROOT: the section must go round the limb alone: within ROOT_R of the limb's axis where the plane cuts it. Where the
plane through B cuts into the torso too (Garrett: a 1518 mm loop round both), B is stepped down STEP_M at a time, up to
MAX_DROP_M, and the drop used is said in the answer.
"""
from __future__ import annotations

import numpy as np

STEP_M = 0.01
MAX_DROP_M = 0.04
ROOT_R = 0.12  # m: a loop round a limb's root stays within this of the limb's axis (an arm's root ~ 0.07)


def _unit(v):
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def girth(tape, it: dict):
    """(girth m, how, tape line) of a tilted girth, or TapeError by name."""
    from . import tailor
    from .body_tape import LIMBS, TapeError
    th, around = it.get("through"), it.get("around")
    if not (isinstance(th, list) and len(th) == 2 and all(isinstance(x, str) for x in th)):
        raise TapeError("a tilted girth: \"through\": [two landmarks] (e.g. shoulder_point.L, side_armpit.L) and "
                        "\"around\": a limb (arm.L, thigh.L...)")
    limb, _, side = str(around).partition(".")
    if limb not in LIMBS or limb == "neck":
        raise TapeError(f"around {around!r}: a limb: {', '.join(k + '.L' for k in LIMBS if k != 'neck')} (or .R)")
    ja, jb = (j + (f".{side}" if side else "") for j in LIMBS[limb])
    if ja not in tape.J or jb not in tape.J:
        raise TapeError(f"around {around!r}: needs the joints {ja} and {jb}")
    ax0, d = tape.J[ja], _unit(tape.J[jb] - tape.J[ja])
    A, B0 = (tape.point(x, need_surface=True) for x in th)
    for k in range(int(round(MAX_DROP_M / STEP_M)) + 1):
        B = B0 - np.array([0.0, 0.0, k * STEP_M])
        e = _unit(B - A)
        n = _unit(d - (d @ e) * e)
        if float(np.linalg.norm(d - (d @ e) * e)) < 1e-3:
            raise TapeError(f"through {th}: the line between them runs along the {around}; the plane can't face along it")
        c = ax0 + d * float((A - ax0) @ n) / max(float(d @ n), 1e-6)  # (where the plane cuts the limb's axis)
        for L in tailor.slice_loops(tape.V, tape.T, A, n):
            far = max(np.min(np.linalg.norm(L - A, axis=1)), np.min(np.linalg.norm(L - B, axis=1)))
            if far < 0.03 and float(np.max(np.linalg.norm(L - c, axis=1))) < ROOT_R:  # (through both; round the limb)
                drop = f", {k * STEP_M * 100:.0f} cm under {th[1]} (there the plane cut into the body too)" if k else ""
                return (tailor.girth(L, n), f"round the root of the {around}, in the plane through {th[0]} and "
                        f"{th[1]}{drop}, facing along the {around}; convex hull (bridges the creases)", tape._hull(L, n))
    raise TapeError(f"no loop round the {around} alone through {th[0]} and {th[1]} (down to {MAX_DROP_M * 100:.0f} cm "
                    "under it): its plane runs into the body; try other landmarks, or a sum of two arcs")
