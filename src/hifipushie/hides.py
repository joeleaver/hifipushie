"""Hiding a part under the parts that cover it (game studios' body masking under shoes, gloves, tight garments).

`spec["parts"][cover]["hides"] = ["body"]` (or {"parts": [...], "margin", "reach", "rim"}): faces of the hidden
part that the covering part encloses are left out of renders (clay `look`, the Blender scene) and culled from the
export, so footwear can take its real shape (a toe spring over bare toes) and nothing of the body pokes through.
The hidden part's own shape is never changed: only which of its faces are drawn.

A vertex of the hidden part is covered when it is
  - INSIDE the covering field (the union of every part that hides it) by more than `margin`, or
  - on a POKE-THROUGH island: a patch of the mesh outside the cover that is ringed by covered vertices and never
    gets farther than `reach` from the cover (toes under a sprung sole, skin through a shoe's throat). Skin that
    leads out into the open (the ankle above the collar) is connected to vertices farther than `reach`: it shows.
Covered vertices within `rim` of a showing vertex stay (the cut lies under the cover, never at an opening's edge).
A face is dropped when all three of its corners are covered. Deterministic; `key` hashes everything it reads.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

MARGIN = 0.001  # m: inside the cover by more than this
REACH = 0.02  # m: an outside patch never farther than this from the cover is a poke-through
RIM = 0.004  # m: covered vertices this near showing ones stay


def rules(defs: dict) -> dict:
    """{hidden part: {"covers": [covering parts], "margin", "reach", "rim"}} from spec["parts"]. Several parts hiding
    the same one cover it together (shoes + soles); the tightest margin / rim and the widest reach win."""
    out: dict = {}
    for cover, d in sorted((defs or {}).items()):
        h = (d or {}).get("hides")
        if not h:
            continue
        opts = {"parts": h} if isinstance(h, (list, str)) else dict(h)
        hidden = [opts["parts"]] if isinstance(opts["parts"], str) else list(opts["parts"])
        for p in hidden:
            if p == cover:
                raise ValueError(f"parts.{cover}.hides names the part itself")
            r = out.setdefault(p, {"covers": [], "margin": None, "reach": None, "rim": None})
            r["covers"].append(cover)
            for k, dflt, pick in (("margin", MARGIN, min), ("reach", REACH, max), ("rim", RIM, min)):
                v = float(opts.get(k, dflt))
                r[k] = v if r[k] is None else pick(r[k], v)
    return out


def hiders(defs: dict) -> dict:
    """{covering part: set of parts it hides}: a hidden part doesn't bury its cover's faces (export pruning)."""
    out: dict = {}
    for p, r in rules(defs).items():
        for c in r["covers"]:
            out.setdefault(c, set()).add(p)
    return out


def key(rule: dict, covers: list) -> str:
    """Content key of a rule and its covering parts' primitives (`covers`: one primitive list per part)."""
    from . import sdf
    h = hashlib.sha1(json.dumps({k: rule[k] for k in ("margin", "reach", "rim")}, sort_keys=True).encode())
    for p in (q for ps in covers for q in ps):
        h.update(sdf.fingerprint(p).encode())
        if p.kind == "shell":
            for q in p.params["prims"]:
                h.update(sdf.fingerprint(q).encode())
    return h.hexdigest()[:12]


def covered(V: np.ndarray, F: np.ndarray, covers: list, margin: float = MARGIN, reach: float = REACH,
            rim: float = RIM) -> np.ndarray:
    """Per vertex of a triangle mesh (V, F): True where the cover hides it (module docstring). covers: one primitive
    list per covering part (each its own field, hard-unioned, as parts are)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    from . import sdf
    V = np.asarray(V, np.float64)
    F = np.asarray(F, np.int64).reshape(-1, 3)
    n = len(V)
    out = np.zeros(n, bool)
    covers = [ps for ps in covers if any(p.op == "add" for p in ps)]
    adds = [p for ps in covers for p in ps if p.op == "add"]
    if not n or not len(F) or not adds:
        return out
    lo = np.min([p.lo for p in adds], 0) - reach - rim
    hi = np.max([p.hi for p in adds], 0) + reach + rim
    cand = np.flatnonzero(np.all((V >= lo) & (V <= hi), 1))
    if not len(cand):
        return out
    c = np.full(n, np.inf)
    c[cand] = np.min([sdf.field_at(ps, V[cand]) for ps in covers], 0)
    inside = c < -margin
    if not inside.any():
        return out
    far = c > reach  # (every vertex outside the box too: inf)
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    ia, ib = inside[E[:, 0]], inside[E[:, 1]]
    rim_v = np.r_[E[ia & ~ib, 1], E[ib & ~ia, 0]]  # uncovered vertices next to covered ones
    E = E[~ia & ~ib]  # edges of the uncovered mesh
    g = coo_matrix((np.ones(len(E), np.int8), (E[:, 0], E[:, 1])), shape=(n, n))
    _, lab = connected_components(g, directed=False)
    open_lab = np.ones(lab.max() + 1, bool)  # a patch shows unless it touches covered skin and stays near the cover
    open_lab[lab[rim_v]] = False
    open_lab[lab[far & ~inside]] = True
    show = ~inside & open_lab[lab]
    hid = ~show
    if rim > 0 and show.any():
        near = cand[hid[cand]]
        vis = cand[show[cand]]
        if len(near) and len(vis):
            d = cKDTree(V[vis]).query(V[near], distance_upper_bound=rim)[0]
            hid[near[np.isfinite(d)]] = False
    return hid


def keep_faces(V: np.ndarray, F: np.ndarray, covers: list, rule: dict) -> np.ndarray:
    """Per face: False where all three corners are covered."""
    F = np.asarray(F, np.int64).reshape(-1, 3)
    hid = covered(V, F, covers, rule["margin"], rule["reach"], rule["rim"])
    return ~hid[F].all(1)


def covers(rule: dict, streams: dict) -> list:
    """The covering parts' primitive lists, from {part: prims} (parts not in `streams` are skipped: a close-up box
    without the shoes)."""
    return [streams[c] for c in rule["covers"] if c in streams]
