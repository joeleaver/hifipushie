"""Known answers for fold_checks: one family of rows for every declared fold (Joe 2026-10-20). Planted good / bad folds
on a strip meshed by cloth.mesh (the same fixture as tests/test_pattern_form.py); the form rows read planted
geometry (the flap rotated about its row by a known angle), no assembly, no Blender."""
import math

import numpy as np
import pytest

from hifipushie import cloth
from test_pattern_form import _B, _piece, _flat

P = [[0, 0], [0.3, 0], [0.3, 0.12], [0, 0.12]]


def _strip(kind="press", angle=180, line=((0.0, 0.04), (0.3, 0.04)), run_off=None, radius=None):
    fd = {"piece": "r", "line": [list(line[0]), list(line[1])], "angle": angle, "kind": kind, "name": "f",
          "flap": "top"}
    if run_off:
        fd["run_off"] = run_off
    if radius:
        fd["radius"] = radius
    return _B({"r": _piece(P, marks={"top": [0.15, 0.1]})}, folds=[fd], refine=[{"piece": "r", "h": 0.006}]), fd


def _turned(M, theta_deg, wobble_deg=0.0, through=False):
    """The strip flat (z 0), its flap (y > 0.04) rotated about the row (y = 0.04) by theta (+ a twist along the line:
    wobble_deg x sin(2 pi x / 40 mm)), the flap lifted / sunk one cloth thickness at a full turn."""
    X = _flat(M).copy()
    uv = np.asarray(M["uv"])
    f = uv[:, 1] > 0.04 + 1e-6
    th = np.radians(theta_deg + wobble_deg * np.sin(2 * np.pi * uv[f, 0] / 0.04))
    r = uv[f, 1] - 0.04
    X[f, 1] = 0.04 + r * np.cos(th)
    X[f, 2] = r * np.sin(th) + (-0.004 if through else 0.0015) * np.clip(theta_deg / 180, 0, 1)
    return X


def _collar_flat_case(fall_h=0.055, stand_h=0.035, r0=0.10, span=2.2):
    """A body piece whose neckline is an arc (radius r0: the flattened shoulders round the neck), a straight stand band
    and a straight FALL band (outer edge = its sewn edge: no spring) sewn as a shirt's: stand to the neckline, fall to
    the stand's top, the fall's roll 6 mm above its seam (angle 0)."""
    th = np.linspace(-span / 2, span / 2, 41)
    L = r0 * span
    neck = np.c_[r0 * np.sin(th), -r0 * np.cos(th)]
    outer = np.c_[0.25 * np.sin(th), -0.25 * np.cos(th)][::-1]
    body = _piece(np.r_[neck, outer], names={"nl.l": 0, "nl.c": 20, "nl.r": 40})
    xs = np.linspace(-L / 2, L / 2, 41)

    def band(h, nm):
        P = np.r_[np.c_[xs, np.zeros(41)], np.c_[xs[::-1], np.full(41, h)]]
        return _piece(P, names={f"{nm}L": 0, f"{nm}M": 20, f"{nm}R": 40, f"{nm}TR": 41, f"{nm}TM": 61, f"{nm}TL": 81})
    B = _B({"bodice": body, "stand": band(stand_h, "s"), "collar": band(fall_h, "c")},
           seams=[["stand:sL>sM>sR", ["bodice:nl.l>nl.c>nl.r"]], ["collar:cL>cM>cR", "stand:sTL>sTM>sTR"]],
           folds=[{"name": "collar roll", "piece": "collar", "line": {"edge": "cL>cM>cR", "offset": 0.006}, "angle": 0,
                   "kind": "roll", "radius": 0.0015, "strength": 0.6}])
    return B


def _lapel_piece():
    """A front's lapel in pattern coordinates: the break at (0, 0), the roll line straight up x = 0, the lapel (x > 0)
    widening to its point 80 mm off the line 290 mm up (the flap); the forepart x < 0."""
    P = np.array([[-0.2, -0.3], [0.0, -0.3], [0.0, 0.0], [0.08, 0.29], [0.0, 0.38], [-0.2, 0.38]], float)
    return {"front": {"P": P, "names": {"break": 2, "lapelPoint": 3}, "marks": {}}}


def test_converged_roll_turns_the_lapel_down_to_the_break():
    """C219 (canvas s12): a roll's rows run parallel to its line, so on a lapel narrowing to its break the last row meets
    the lapel edge (and the turned face ends) 35-42 mm above the break (Garrett's jacket: the face ended 330 below HPS vs
    the concept's 386). "converge" [length, "break"] shrinks the rows' offsets within that length of the break: the last
    row reaches within 15 mm of it; off, the rows are the parallel ones (unchanged)."""
    from hifipushie import folds
    pcs = _lapel_piece()
    f = {"piece": "front", "line": [[0.0, 0.0], [0.0, 0.40]], "angle": 15, "kind": "roll", "radius": 0.006,
         "strength": 0.8, "flap": "lapelPoint", "name": "lapel roll"}
    par = folds.rows(pcs, f, 0.006)
    con = folds.rows(pcs, dict(f, converge=[0.08, "break"]), 0.006)
    assert len(par["lines"]) == len(con["lines"]) >= 3 and par["sign"] == con["sign"]
    low = lambda r: float(np.asarray(r["lines"][-1])[:, 1].min())
    assert low(par) > 0.035, low(par)
    assert low(con) < 0.015, low(con)
    # far from the break the converged rows are the parallel ones
    a, b = np.asarray(par["lines"][-1]), np.asarray(con["lines"][-1])
    at = lambda L, y: float(np.interp(y, L[:, 1], L[:, 0]))
    assert abs(at(a, 0.2) - at(b, 0.2)) < 1e-4
