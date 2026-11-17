"""SHAPED CLOTH: a piece flattened with the tailor's shrink / stretch DECLARED (step 6 of drape first; R3f-11, C510).
A tailor makes an undercollar from a flat piece by shaping it with heat and steam: the fall's outer edge stretched, the
roll line shrunk, the neck edge eased into the neckline. The flat piece's run is then shorter (stretched on) or longer
(shrunk on) than where it lies on the toile. That is DECLARED ease, never a length silently changed (C504).

THE DECLARATION (garment_cut's `shaped`): {"<piece>:<run>": pct}, + a stretch (the toile's run longer than the flat's
by pct), - a shrink (shorter). A grid piece's runs (the collar, cut_collar.py): its outer edge's name, "roll" (or the
fold's name), "neck" (every neck run) or one neck run by the piece's own edge name (".L" serves ".R"). The pieces cut
from one flat (an undercollar and its top collar) share one shaping: different amounts on one run are refused.

HOW: the amounts are laid on the grid's rows (a neck run's on its columns of the neck row, the roll's on the roll row,
the outer's on the outer row; linear between them, 0 where nothing is declared) and the piece is flattened against
that rest shape (flatten.flatten(rest=...): each face's rest stretched along the run by 1 / (1 + d)), CAL_PASSES
calibrating each declared run until its flat / toile length is the declared amount (cut_ease does the same for the cap).
The strain left is measured against the shaped target.

THE LIMIT: SHAPE_MAX_PCT (8 %) either way: wool takes about what a tailored sleeve cap is shrunk by (3-4 cm over a
~45 cm crown, 7-9 %, the most a tailor shrinks wool along one run; a bias undercollar stretches about as far). A
declared amount beyond it is REFUSED by name (ShapeRefused); what the toile ASKS (each run's toile / unshaped flat
length) beyond it is reported: then the piece's shape on the toile is wrong (back to step 4), not the ease. Metres."""
from __future__ import annotations

import re

import numpy as np

SHAPE_MAX_PCT = 8.0
RESIDUAL_PCT = 3.0  # the strain (mean) a shaped collar may keep against its shaped target (R3f-9 unshaped: 6.0)
CAL_PASSES = 5
CAL_TOL = 0.002


class ShapeRefused(ValueError):
    """A shaping beyond what wool takes, on a run the piece hasn't, or two amounts on one run (named)."""


def _mir(e: str) -> str:
    return re.sub(r"\.L$", ".R", e) if e.endswith(".L") else e


def resolve(shaped: dict, pieces: dict) -> dict:
    """{internal run: d (fraction)} from the declaration; pieces {piece: {its run name: internal run}} (a neck run
    "neck:<garment edge>", "roll", "outer"); refused by name (module doc)."""
    out, src = {}, {}
    for k, pct in (shaped or {}).items():
        piece, _, run = k.partition(":")
        if piece not in pieces:
            continue
        pct, al = float(pct), pieces[piece]
        if abs(pct) > SHAPE_MAX_PCT:
            raise ShapeRefused(f"shaped.{k}: {pct:+g} % is beyond what wool takes under steam (+-{SHAPE_MAX_PCT:g} %, "
                               "cut_shape.SHAPE_MAX_PCT): the piece's shape on the toile is wrong, not the ease")
        keys = sorted({v for v in al.values() if v.startswith("neck:")}) if run == "neck" else \
            sorted({al[r] for r in al if r in (run, _mir(run))})
        if not keys:
            raise ShapeRefused(f"shaped.{k}: {piece} has no run {run!r} (its runs: neck, {', '.join(sorted(al))})")
        for r in keys:
            if r in out and abs(out[r] - pct / 100) > 1e-9:
                raise ShapeRefused(f"shaped.{k}: {r} is shaped {out[r] * 100:+g} % by {src[r]}: one flat, one shaping")
            out[r], src[r] = pct / 100, k
    return out


def _rows(nr, nc, ks, neck_d, roll_d, outer_d):
    """Per-vertex d on the grid: neck row per column (neck_d: nc values), roll row, outer row; linear between."""
    D = np.zeros((nr, nc))
    for r in range(nr):
        a = r / ks if r <= ks else (r - ks) / max(nr - 1 - ks, 1)
        D[r] = (1 - a) * neck_d + a * roll_d if r <= ks else (1 - a) * roll_d + a * outer_d
    return D.ravel()


def _tangents(Vg):
    T = np.zeros_like(Vg)
    T[:, 1:-1] = Vg[:, 2:] - Vg[:, :-2]
    T[:, 0], T[:, -1] = Vg[:, 1] - Vg[:, 0], Vg[:, -1] - Vg[:, -2]
    return T.reshape(-1, 3)


def _len(P):
    return float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())


def run_ratio(Vg, Ug, lines: dict) -> dict:
    """{run: toile / flat - 1} over each run's grid edges ({run: (row, [columns])})."""
    out = {}
    for k, (r, cols) in lines.items():
        l3 = sum(float(np.linalg.norm(Vg[r, c + 1] - Vg[r, c])) for c in cols)
        lf = sum(float(np.linalg.norm(Ug[r, c + 1] - Ug[r, c])) for c in cols)
        out[k] = l3 / max(lf, 1e-12) - 1
    return out


def cone_points(V, F, grid, top=3) -> list:
    """Where the grid piece is curved in itself (each interior vertex's angle defect, 360 deg less the angles round
    it): no shaping ALONG a run removes a point defect (a cone point: a corner in the roll the fall can't follow).
    The `top` largest as [row, column, deg] (+ dome: cloth missing; - saddle: cloth over)."""
    nr, nc, _ = grid
    ang = np.zeros(len(V))
    for k in range(3):
        a, b, c = F[:, k], F[:, (k + 1) % 3], F[:, (k + 2) % 3]
        u, v = V[b] - V[a], V[c] - V[a]
        cs = (u * v).sum(1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1) + 1e-12)
        np.add.at(ang, a, np.arccos(np.clip(cs, -1, 1)))
    K = np.degrees(2 * np.pi - ang).reshape(nr, nc)
    K[[0, -1]], K[:, [0, -1]] = 0, 0
    Ks = K.copy()  # (summed over 5 columns: a cone point spreads over a few)
    for j in range(nc):
        Ks[:, j] = K[:, max(j - 2, 0): j + 3].sum(1)
    out = []
    for i in np.argsort(-np.abs(Ks).ravel()):
        r, c = divmod(int(i), nc)
        if all(abs(r - a) > 1 or abs(c - b) > 4 for a, b, _ in out):
            out.append([r, c, round(float(Ks[r, c]), 1)])
        if len(out) == top:
            break
    return out


CONE_MAX_DEG = 15.0  # a collar grid's cone point (angle defect summed over 5 columns) a flat piece can still be shaped to
#                     (8 % along a ~45 mm fall turns its edge ~ 0.08 x 170 / 45 rad ~ 17 deg per half: R3f-12)


def crease(V, grid) -> dict:
    """The roll as a FOLD (R3f-12, C511): at each roll-row vertex of a grid piece (rows neck -> roll (ks) -> outer)
    the roll's turning seen in the stand (the cells below: pi less their angles there) and in the fall (above). A fold
    lies in flat cloth only where the two cancel (the fall turns the other way: its outer edge longer): their sum IS
    the angle defect, so a roll that turns in the stand's surface (round the neck, then down to the gorge) needs the
    fall to flare as much, or stand off. Degrees; per half (CB at the middle column, CB counted once)."""
    nr, nc, ks = grid
    X = np.asarray(V, float).reshape(nr, nc, 3)
    ang = lambda p, a, b: np.arccos(np.clip(((a - p) @ (b - p)) / (np.linalg.norm(a - p) * np.linalg.norm(b - p) + 1e-12), -1, 1))
    side = lambda c, r: float(np.degrees(np.pi - ang(X[ks, c], X[ks, c - 1], X[r, c]) - ang(X[ks, c], X[r, c], X[ks, c + 1])))
    h = nc // 2
    st = np.array([side(c, ks - 1) for c in range(h, nc - 1)])
    fa = np.array([side(c, ks + 1) for c in range(h, nc - 1)])
    k = int(np.argmax(np.abs(st + fa)))
    return {"stand_turn_deg": round(float(st[1:].sum() + st[0] / 2), 1), "fall_turn_deg": round(float(fa[1:].sum() + fa[0] / 2), 1),
            "worst_col_from_cb": k, "worst_deg": round(float(st[k] + fa[k]), 1)}


def flatten_shaped(V, F, grid, lines: dict, want: dict):
    """(U, S, F kept, report): the grid piece flattened against its shaped rest (module doc). grid (nr, nc, ks);
    lines {run: (row, [columns])} (row 0: the neck runs, ks: "roll", nr - 1: "outer"); want {run: d}."""
    from .flatten import flatten
    nr, nc, ks = grid
    Vg = V.reshape(nr, nc, 3)
    U, S, Fk = flatten(V, F)
    asks = run_ratio(Vg, U.reshape(nr, nc, 2), lines)
    rep = {"limit_pct": SHAPE_MAX_PCT, "cone_points": cone_points(V, F, grid), "roll_row": grid[2],
           "runs": {k: {"asks_pct": round(asks[k] * 100, 2), "asks_within": abs(asks[k]) * 100 <= SHAPE_MAX_PCT}
                    for k in lines}}
    if not want:
        return U, S, Fk, rep
    T = _tangents(Vg)
    a = {k: v for k, v in want.items()}  # (the applied amounts, calibrated)
    hist = []
    for _ in range(CAL_PASSES):
        neck = np.zeros(nc - 1)
        for k, (r, cols) in lines.items():
            if r == 0 and k in a:
                neck[cols] = a[k]
        nd = np.r_[neck[0], 0.5 * (neck[1:] + neck[:-1]), neck[-1]]
        dv = _rows(nr, nc, ks, nd, a.get("roll", 0.0), a.get("outer", 0.0))

        def rest(Vc, Fc, dv=dv):
            t = T[Fc].mean(1)
            return t / (np.linalg.norm(t, axis=1, keepdims=True) + 1e-12), 1 / (1 + dv) - 1  # (per vertex: on the edges)
        U, S, Fk = flatten(V, F, rest=rest)
        got = run_ratio(Vg, U.reshape(nr, nc, 2), lines)
        hist.append({k: round(got[k] * 100, 2) for k in want})
        if all(abs(got[k] - want[k]) < CAL_TOL for k in want):
            break
        a = {k: a[k] + (want[k] - got[k]) for k in a}
    for k in lines:
        rep["runs"][k].update({"declared_pct": round(want.get(k, 0.0) * 100, 2), "flat_pct": round(got[k] * 100, 2)})
    rep["passes"] = hist
    return U, S, Fk, rep
