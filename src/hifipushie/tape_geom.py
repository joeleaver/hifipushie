"""TAPE GEOMETRY (F4, C312): every measurement step 3 takes keeps WHERE it was taken on the body.

Joe (2026-11-02): "shouldn't they just build like any other garment pattern?" A piece starts where its OWN
measurements were taken, so the tape's numbers are not enough: each row of step 3 keeps its geometry.

- A GIRTH keeps its LOOP (closed polyline round the body section it was taken on: tailor.measure's loops, the legs'
  too since F4).
- A LENGTH / ARC / HEIGHT keeps its PATH (the polyline the tape ran along: body_tape's own lines; FreeSewing's
  vertical lengths without a tape line are run down the body's surface here: `waistTo*` from the waist level down by
  its value on the outer side, `inseam` from the crotch down on the inner side of the measured (+X) leg, `height`).
- Compact: metres, 0.1 mm, at most MAX_PTS points (`compact`). Saved with step 3's record by body_tape.run as
  row["loop"] or row["path"].

`geometry(tape, row)` -> {"loop": [[x, y, z], ...]} | {"path": [...]} | {} for one body_tape row.
`tapes(step3)` -> {name: {"kind", "loop" | "path" (np arrays)}} read back from a step-3 record (rows without geometry
are left out: an older record).
"""
from __future__ import annotations

import numpy as np

from . import tailor

MAX_PTS = 64
# FreeSewing lengths taken joint to joint (tailor.measure's definitions): their path runs through those joints
JOINT_PATHS = {"shoulderToWrist": ("shoulder.L", "elbow.L", "wrist.L"), "shoulderToElbow": ("shoulder.L", "elbow.L")}
Z = np.array([0.0, 0.0, 1.0])
GIRTH_KINDS = ("girth",)


def compact(P, closed: bool = False) -> list:
    """Metres at 0.1 mm, resampled evenly along its length to at most MAX_PTS points."""
    P = np.asarray(P, float).reshape(-1, 3)
    if closed and len(P) > 2 and np.linalg.norm(P[0] - P[-1]) > 1e-9:
        P = np.r_[P, P[:1]]
    if len(P) > MAX_PTS:
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        q = np.linspace(0, s[-1], MAX_PTS)
        P = np.column_stack([np.interp(q, s, P[:, k]) for k in range(3)])
    return np.round(P, 4).tolist()


def _leg_loop(tape, z):
    kn = tape.J.get("knee.L")
    Ls = [L for L in tailor.slice_loops(tape.V, tape.T, [0, 0, z], Z) if L[:, 0].mean() > 0.02 and
          (kn is None or np.hypot(L[:, 0].mean() - kn[0], L[:, 1].mean() - kn[1]) < 0.25)]
    return max(Ls, key=lambda L: tailor.girth(L, Z)) if Ls else None


def side_path(tape, z_top: float, z_bot: float, inner: bool = False, step: float = 0.02) -> np.ndarray | None:
    """The tape run down the body's +X side from z_top to z_bot: on the torso's section above the crotch, on the
    measured leg's below it; its outermost point (inner: the leg's innermost)."""
    cz = float(tape.R["at"].get("crotch_z", -1e9))
    out = []
    for z in np.arange(z_top, z_bot - 1e-6, -step).tolist() + [z_bot]:
        z = max(float(z), tape.zmin + 0.005)
        L = _leg_loop(tape, z) if (z < cz - 0.005 or inner) else tape.torso(z)
        if L is None:
            continue
        L = np.asarray(L, float)
        out.append(L[np.argmin(L[:, 0])] if inner else L[np.argmax(L[:, 0])])
    return np.array(out) if len(out) >= 2 else None


def _freesewing_path(tape, fs: str, mm: float) -> np.ndarray | None:
    at = tape.R["at"]
    v = mm / 1000.0
    if fs.startswith("waistTo") and "waist_z" in at:
        w = float(at["waist_z"])
        lvl = at.get(fs[7].lower() + fs[8:] + "_z")  # (a level above the waist, waistToArmpit: run from it down)
        return side_path(tape, float(lvl), w) if lvl is not None and float(lvl) > w else side_path(tape, w, w - v)
    if fs == "inseam" and "crotch_z" in at:
        c = float(at["crotch_z"])
        return side_path(tape, c, c - v, inner=True)
    if fs in JOINT_PATHS and all(j in tape.J for j in JOINT_PATHS[fs]):
        return np.array([tape.J[j] for j in JOINT_PATHS[fs]], float)
    if fs == "height":
        x = float(tape.V[:, 0].max())
        return np.array([[x, 0.0, tape.zmax], [x, 0.0, tape.zmin]])
    return None


def geometry(tape, row: dict) -> dict:
    """{"loop": ...} for a girth, {"path": ...} for anything else, {} when the tape has no line for it."""
    nm = row["name"]
    fs = row.get("measure", nm) if row.get("kind") == "freesewing" else None
    girth = row.get("kind") in GIRTH_KINDS
    P = tape.lines.get(nm)
    if fs is not None:
        L = tape.R["loops"].get({"shoulderToShoulder": "shoulders"}.get(fs, fs))
        girth = L is not None and np.asarray(L).ndim == 2 and len(L) > 8 and _closed_like(np.asarray(L, float))
        if L is not None:
            P = L
        elif P is None and "mm" in row:
            P = _freesewing_path(tape, fs, float(row["mm"]))
            if P is not None:
                tape.lines[nm] = P  # (drawn on step 3's look with the rest)
    if P is None or len(np.asarray(P)) < 2:
        return {}
    return {"loop": compact(P, closed=True)} if girth else {"path": compact(P)}


def _closed_like(L: np.ndarray) -> bool:
    """A loop round a section (not a tape run between two points): its ends meet within a tenth of its span."""
    return float(np.linalg.norm(L[0] - L[-1])) < 0.1 * float(np.ptp(L, axis=0).max()) + 0.02


def tapes(step3: dict) -> dict:
    out = {}
    for r in (step3 or {}).get("measurements") or []:
        for k in ("loop", "path"):
            if r.get(k):
                out[r["name"]] = {"kind": k, k: np.asarray(r[k], float), "mm": r.get("mm")}
    return out
