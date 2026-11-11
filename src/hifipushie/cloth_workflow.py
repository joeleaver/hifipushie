"""The staged clothing workflow: how a pattern maker / Marvelous Designer artist works, as checkable stages.

  1 design        the design sheet (garment_design): kind, fabric with physical numbers, fit, every construction
                  choice (collar, cuff, placket, closure, hem, ...), defaults filled from garment_kb.json; a choice the
                  draft source can't make, or one that needs another (a barrel cuff needs a sleeve placket), fails.
  2 pattern       the draft laid flat and LOOKED at (pattern_sheet, shape only: names, grain, notches, seam pairs by
                  colour, folds, interfacing; the numbers in the text); checks: every sheet choice evidenced in the
                  pieces and seam table, every
                  seam's ease in its band (cloth_check; the sleeve cap by kind), notches, ease vs the body per girth in
                  the fit's band, every piece sewn to something, the details' dimensions.
  3 construction  the making plan: sewing order, layers and which side laps, fold/press lines with angles, interfacing
                  and what rests "as made", fabric and interfacing stiffness, the sim's stage schedule; checks: nothing
                  that must roll is frozen as made, made pieces are the ones the knowledge base says.
  4 place         the pieces arranged round the body (or dressed for the hanger), before any sim: crossings at the
                  start, how far the start was pushed off the body, start stretch past the solver's limit, layer gaps.
  5 sim           after dress (draft first, then final): the report's verdict plus the numeric targets of
                  garment_kb.json (layer gaps, collar cover and points, hem level, waistband height, sleeves hung,
                  crest radius, strain), judged at the quality they belong to.
Each stage returns {"stage", "fail", "warn", "info", "images"}; `text` prints failures first. `gate` is what `dress`
runs before it starts a sim (stages 1-3): hard failures stop it unless forced.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import cloth, cloth_check, garment_design


def falls_straight_design(g: dict) -> bool:
    """True when the garment's design declares the plumb fall (C179): waist_suppression silhouette plumb, no tube cut."""
    return any(o.get("op") == "waist_suppression" and o.get("silhouette") == "plumb" and not o.get("tube")
               for o in (((g or {}).get("design") or {}).get("ops") or []))


# ---------------------------------------------------------------- 1 design


# ---------------------------------------------------------------- 2 pattern


# ---------------------------------------------------------------- 3 construction


# ---------------------------------------------------------------- 4 place


START_STANDOFF = 0.003  # ZOZO's body contact offset (2 mm) + contact gap (1 mm)


def _point_tri_dist(P: np.ndarray, A: np.ndarray, B: np.ndarray, C: np.ndarray) -> np.ndarray:
    """Distance of each point P[i] from triangle (A[i], B[i], C[i]) (Ericson's closest-point regions)."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = P - B
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = P - C
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = np.where(np.abs(va + vb + vc) > 1e-30, va + vb + vc, 1e-30)
    v, w = vb / den, vc / den
    Q = A + ab * v[:, None] + ac * w[:, None]  # inside the face
    e = lambda X0, X1, t: X0 + (X1 - X0) * np.clip(t, 0, 1)[:, None]  # noqa: E731
    cases = [
        ((d1 <= 0) & (d2 <= 0), A),
        ((d3 >= 0) & (d4 <= d3), B),
        ((d6 >= 0) & (d5 <= d6), C),
        ((vc <= 0) & (d1 >= 0) & (d3 <= 0), e(A, B, d1 / np.where(d1 - d3 != 0, d1 - d3, 1e-30))),
        ((vb <= 0) & (d2 >= 0) & (d6 <= 0), e(A, C, d2 / np.where(d2 - d6 != 0, d2 - d6, 1e-30))),
        ((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0),
         e(B, C, (d4 - d3) / np.where((d4 - d3) + (d5 - d6) != 0, (d4 - d3) + (d5 - d6), 1e-30))),
    ]
    done = np.zeros(len(P), bool)
    for m, R in cases:
        m = m & ~done
        Q[m] = R[m]
        done |= m
    return np.linalg.norm(P - Q, axis=1)


def start_in_standoff(X: np.ndarray, M: dict, body, standoff: float = START_STANDOFF) -> dict:
    """{piece: (closest mm, pattern uv)} for the pieces whose start comes closer to the body than the solver's contact
    standoff (vertices against the collider's vertices, triangle centres and edge midpoints). Tess's jumper (tess2_c2):
    its neckband's folded end 0.84 mm off the neck, the sim stopped at its first step ("failed to advance")."""
    from scipy.spatial import cKDTree
    V, T = np.asarray(body.V), np.asarray(body.T)
    if not len(V):
        return {}
    # exact point-triangle distances to the 8 triangles whose centres are nearest
    _, cand = cKDTree(V[T].mean(1)).query(X, k=min(8, len(T)))
    cand = np.asarray(cand).reshape(len(X), -1)
    d = np.full(len(X), np.inf)
    for c in range(cand.shape[1]):
        A, B_, C = V[T[cand[:, c], 0]], V[T[cand[:, c], 1]], V[T[cand[:, c], 2]]
        d = np.minimum(d, _point_tri_dist(X, A, B_, C))
    out = {}
    for k, nm in enumerate(M["names"]):
        sel = np.where(M["piece"] == k)[0]
        if len(sel) and d[sel].min() < standoff:
            i = sel[np.argmin(d[sel])]
            out[nm] = (round(float(d[i]) * 1000, 2), np.round(M["uv"][i], 3).tolist())
    return out


def sewn_crossings(cr: list, M: dict) -> list:
    """The crossing piece pairs that are sewn or stitched to each other (or a piece crossing itself where it is sewn
    or stitched to itself: a cuff's lap, a sleeve's underarm). A piece crossing itself with no seam to itself is NOT
    one of them (dress-tess: jeans legs whose gathered hem folded through itself on a taller shoe were only warned
    about, and the sim crawled at 4.7 s a frame until its 8 min limit)."""
    jn = set()
    for key in ("sew", "stitch"):
        pr = np.asarray(M.get(key, []), np.int64).reshape(-1, 2)
        jn |= {tuple(sorted((M["names"][M["piece"][a]], M["names"][M["piece"][b]]))) for a, b in pr}
    # (and a piece folded over itself by construction: a lapel pressed onto its forepart, a band folded in half)
    jn |= {(f["piece"], f["piece"]) for f in M.get("folds") or [] if f.get("piece")}
    return [p for p in cr if tuple(sorted(p)) in jn]


# ---------------------------------------------------------------- 5 sim targets


# ---------------------------------------------------------------- running stages

