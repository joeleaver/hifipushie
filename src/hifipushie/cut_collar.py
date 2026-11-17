"""garment_cut's COLLAR (R3f, C497): the collar is DRAPED ON THE TOILE at step 4 (toile_collar.py: the stand rising from
the neck seam to the roll line, the fall turned down over it and lying on the shoulders), so step 6 only cuts it and
flattens it, as the lapel: the folded surface flattened by UNFOLDING the fall about the roll line (the flatten is
intrinsic: each triangle keeps its own shape, so the fall comes off the stand across the roll row, landing on the far
side of it). Five runs (R2-R3e) drafted the collar flat here and fitted it round the neck afterwards: it always stood
round the neck like a band. Nothing is drafted or fitted here.

NOTHING STRETCHED (R3f-7, C504): the collar is flattened as draped (R3f-6's held_flatten stretched the stand 31-40 %
along its neck edge to match the fronts: a tuned length, deleted). Each neck run's flat length is reported beside the
garment edge's, flat and in 3D (seams: collar_mm / garment_mm, collar_3d_mm / garment_3d_mm): a mismatch is fixed where
the toile's collar and the garment's neck edge disagree in 3D (step 4), never in the flat. SHAPED (R3f-11, C510): the tailor's steam shaping is DECLARED (garment_cut's `shaped`, cut_shape.py): the
flat cut to the shaped target, a neck seam then held to its garment edge within its declared ease; the row reports what
each run asks and the collar's cone points (curvature no shaping along a run removes: step 4's fault).

THE PIECES: each declared collar piece (an undercollar, a top collar) gets the flat; its edges are named from the toile:
the neck row's runs by the garment neck edge each lies on in 3D (the nearest of the declared neck edges and their
mirrors), named by step 1 (the collar's edge sewn to that garment edge, or to a layer cut from its piece: a facing's
gorge, or caught in its seam: a top collar's stand in the back neck seam); the outer row `outer`; the ends `end` (the
left end, +X) and its ".R" mirror. The roll row is the fold (planned_folds' row). Rows: the neck edge's flat length per
garment edge against that edge's own flat (the seams equal), the outer edge flat / where it lies on the toile (both
halves), the roll, the flat's span and the neck edge's bow (a crescent, not a band), the strain left.

THE DECLARATION (garment_cut's `collar`): {"pieces": [collar pieces], "neck": [garment neck edges of the left half, from
the front end to CB], "outer": edge name, "end": edge name (".L"), "fold": step 2's roll fold name, "fold_on": the piece
step 2 turns it on, "past": the name of a neck edge's run past the gorge corner (default "notch", split_gorge)}; the collar's heights are step 4's (garment_toile's collar part). Nothing here knows a garment."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

NEEDS = ("pieces", "neck", "outer", "end")
SPLIT_ON_M = 0.006  # m: the collar's neck end this near a garment neck edge is on it (else that edge is not cut)


class CollarRefused(ValueError):
    """A collar declaration the garment can't answer, or a toile with no collar part (named)."""


def mirror(e: str) -> str:
    return re.sub(r"\.L$", ".R", e) if e.endswith(".L") else re.sub(r"\.L:", ".R:", e)


def neck_edge(c: str, g: str, s1: dict, layers: dict) -> str | None:
    """The edge of collar piece c sewn to garment edge g (or to a layer cut from g's piece, or caught in g's seam)."""
    gp, ge = g.split(":", 1)
    via = {f"{lay}:{(d.get('edges') or {}).get(ge, ge)}" for lay, d in layers.items() if d.get("host") == gp}
    for s in s1.get("seams") or []:
        for mine, other in ((s["a"], s["b"]), (s["b"], s["a"])):
            if mine.split(":")[0] == c and (other == g or other in via):
                return mine.split(":", 1)[1]
    for s in s1.get("seams") or []:
        if g in (s["a"], s["b"]):
            for x in s.get("caught") or []:
                if x.split(":")[0] == c:
                    return x.split(":", 1)[1]
    return None


def grid_loop(nr, nc):
    return ([c for c in range(nc)] + [r * nc + nc - 1 for r in range(1, nr)] +
            [(nr - 1) * nc + c for c in range(nc - 2, -1, -1)] + [r * nc for r in range(nr - 2, 0, -1)])


def _len(P):
    return float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())


def _edge_pts(f, idx, key="V"):
    pos = list(idx) + [(idx[-1] + 1) % len(f["lp"])]
    return f[key][np.asarray(f["lp"])[pos]]


def toile_collar(out4: dict):
    """(V, F, (rows, cols, roll row), step 4's collar numbers) from step 4's toile; refused without a collar part."""
    from .mark_flap import load
    Z = load(out4["toile"])  # (R3f-9: the collar is the flap's region behind its gorge marks)
    if "collar:V" not in Z or "collar_grid" not in Z:
        raise CollarRefused("collar: step 4's toile has no collar part: garment_toile parts \"collar\" {stand_mm, "
                            "fall_mm, notch} (the collar is draped on the toile, then cut here)")
    info = {}
    if out4.get("numbers") and Path(out4["numbers"]).exists():
        info = json.loads(Path(out4["numbers"]).read_text()).get("collar") or {}
    return Z["collar:V"].astype(float), Z["collar:F"].astype(int), tuple(int(x) for x in Z["collar_grid"]), info


def split_gorge(pcs: dict, edges: dict, d: dict, out4: dict) -> list:
    """The garment's neck edges cut where the collar's neck edge ends (the gorge corner, where the collar meets the
    lapel): a front's neck edge runs on along the lapel's top to its point, but only the run from the shoulder to the
    gorge corner is sewn to the collar; the rest is named d["past"] (default "notch"), a free edge. Before the layers
    are traced, so a facing's gorge is the same run. Returns what was cut (for the log)."""
    from .mark_flap import load
    Z = load(out4["toile"])
    if "collar:V" not in Z or "collar_grid" not in Z:
        return []
    nr, nc, _ = (int(x) for x in Z["collar_grid"])
    row = Z["collar:V"].astype(float).reshape(nr, nc, 3)[0]
    past, done = d.get("past", "notch"), []
    for g in d.get("neck") or []:
        for gg in (g, mirror(g)):
            pp, ee = gg.split(":", 1)
            if pp not in pcs or ee not in edges.get(pp, {}):
                continue
            segs = list(edges[pp][ee])
            P = _edge_pts(pcs[pp], segs)
            dist = np.min(np.linalg.norm(P[:, None] - row[None], axis=2), axis=1)
            end = min((row[0], row[-1]), key=lambda q: np.min(np.linalg.norm(P - q, axis=1)))
            k = int(np.argmin(np.linalg.norm(P - end, axis=1)))
            if not 0 < k < len(segs):
                continue
            a, b = segs[:k], segs[k:]
            far = b if dist[k:].mean() > dist[: k + 1].mean() else a
            if np.linalg.norm(P[k] - end) > SPLIT_ON_M or float(np.max(dist[k:] if far is b else dist[: k + 1])) < SPLIT_ON_M:
                continue
            edges[pp][ee] = a if far is b else b
            edges[pp][past] = far
            done.append(f"{gg} cut at the gorge corner: {len(far)} segments past it named {pp}:{past}")
    return done


def build(pcs: dict, edges: dict, d: dict, s1: dict, layers: dict, out4: dict, shaped: dict | None = None):
    """({piece: f}, {piece: edges}, folds, report, bad): the toile's collar cut, unfolded and named (module doc);
    shaped: garment_cut's `shaped` (cut_shape.py: the tailor's declared shrink / stretch per run)."""
    from .cut import _group
    from .flatten import strain
    from .mark_split import areas
    for k in NEEDS:
        if k not in d:
            raise CollarRefused(f"collar: needs {k!r} (module doc)")
    V, F, (nr, nc, ks), info = toile_collar(out4)
    garm = {}
    for g in d["neck"]:
        for gg in (g, mirror(g)):
            pp, ee = gg.split(":", 1)
            if pp not in pcs or ee not in edges.get(pp, {}):
                raise CollarRefused(f"collar: neck edge {gg!r} is not a cut edge")
            garm[gg] = _edge_pts(pcs[pp], edges[pp][ee])
    Vg = V.reshape(nr, nc, 3)
    # the neck row's runs: by the garment neck edge each lies on in 3D
    seg_g = []
    for c in range(nc - 1):
        m = 0.5 * (Vg[0, c] + Vg[0, c + 1])
        seg_g.append(min(garm, key=lambda g: np.min(np.linalg.norm(garm[g] - m, axis=1))))
    from .cut_shape import flatten_shaped, resolve
    lines = {"roll": (ks, list(range(nc - 1))), "outer": (nr - 1, list(range(nc - 1)))}
    lines.update({f"neck:{g}": (0, [c for c in range(nc - 1) if seg_g[c] == g]) for g in garm})
    alias = {cp: {"roll": "roll", d.get("fold") or "roll": "roll", "outer": "outer", d["outer"]: "outer",
                  **{n: f"neck:{g}" for g in garm if (n := neck_edge(cp, g, s1, layers))}} for cp in d["pieces"]}
    want = resolve(shaped, alias)  # (ShapeRefused: beyond what wool takes, or no such run)
    U, S, Fk, shape = flatten_shaped(V, F, (nr, nc, ks), {k: v for k, v in lines.items() if v[1]}, want)
    bad_f = strain(S)
    loop = np.asarray(grid_loop(nr, nc))
    P = U[loop]
    if np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(P[:, 1], np.roll(P[:, 0], -1)) < 0:
        U = U * [-1.0, 1.0]  # (the flat seen from the cloth's right side: the outline anticlockwise)
    Ug = U.reshape(nr, nc, 2)
    out_pcs, out_edges, bad = {}, {}, []
    for cp in d["pieces"]:
        names = {g: neck_edge(cp, g, s1, layers) for g in garm}
        miss = [g for g in d["neck"] if names[g] is None]
        if miss:
            bad.append(f"collar: {cp} has no edge sewn to (or caught in) {miss[0]} in step 1")
            continue
        keys = []
        for i in range(len(loop)):
            a, b = loop[i], loop[(i + 1) % len(loop)]
            ra, ca, rb, cb = a // nc, a % nc, b // nc, b % nc
            if ra == 0 and rb == 0:
                keys.append(names[seg_g[min(ca, cb)]])
            elif ra == nr - 1 and rb == nr - 1:
                keys.append(d["outer"])
            else:
                keys.append(d["end"] if ca == nc - 1 else mirror(d["end"]))
        out_edges[cp] = {key: idx for key, idx in _group(keys)}
        ar = areas(V, Fk)
        out_pcs[cp] = {"name": cp, "U": U, "F": Fk, "V": V, "bad": bad_f, "lp": loop, "loop": list(loop),
                       "rep": {"faces": int(len(Fk)), "area_cm2": round(float(ar.sum()) * 1e4, 1),
                               "strain_mean_pct": round(float((bad_f * ar).sum() / ar.sum() * 100), 2),
                               "area_over_2pct": round(float(ar[bad_f > 0.02].sum() / ar.sum() * 100), 1),
                               "from_toile": True},
                       "landing": {"line": _len(Vg[-1]) - 2 * np.pi * _lift(), "behind": _behind(Vg, seg_g, d),
                                   "d": (info.get("fall_mm", 0) - info.get("stand_mm", 0)) / 1000}}
    folds = [{"name": d["fold"], "piece": d.get("fold_on") or d["pieces"][-1], "line": Ug[ks].tolist(), "kind": "roll"}] \
        if d.get("fold") else []
    seams = {}
    for g in garm:
        cols = [c for c in range(nc - 1) if seg_g[c] == g]
        if not cols:
            bad.append(f"collar: no part of its neck edge lies on {g} on the toile")
            continue
        flat_c = sum(float(np.linalg.norm(Ug[0, c + 1] - Ug[0, c])) for c in cols)
        pp, ee = g.split(":", 1)
        seams[g] = {"collar_mm": round(flat_c * 1000, 1), "garment_mm": round(_len(_edge_pts(pcs[pp], edges[pp][ee], "U")) * 1000, 1),
                    "shaped_pct": round(want.get(f"neck:{g}", 0.0) * 100, 2),
                    "collar_3d_mm": round(sum(float(np.linalg.norm(Vg[0, c + 1] - Vg[0, c])) for c in cols) * 1000, 1),
                    "garment_3d_mm": round(_len(_edge_pts(pcs[pp], edges[pp][ee])) * 1000, 1),
                    **_apart(garm[g], Vg[0, min(cols): max(cols) + 2])}
    chord = Ug[0, -1] - Ug[0, 0]
    cu, dv = chord / np.linalg.norm(chord), Ug[0] - Ug[0, 0]
    bow = float(np.abs(cu[0] * dv[:, 1] - cu[1] * dv[:, 0]).max())
    Uf = U.reshape(-1, 2)
    neck_f, outer_f = _len(Ug[0]), _len(Ug[-1])
    rep = {"neck_flat_mm": round(neck_f * 1000, 1), "outer_flat_mm": round(outer_f * 1000, 1),
           "outer_3d_mm": round(_len(Vg[-1]) * 1000, 1), "roll_flat_mm": round(_len(Ug[ks]) * 1000, 1),
           "roll_3d_mm": round(_len(Vg[ks]) * 1000, 1), "outer_over_neck": round(outer_f / neck_f, 3),
           "flat_span_mm": [round(float(np.ptp(Uf[:, 0])) * 1000, 1), round(float(np.ptp(Uf[:, 1])) * 1000, 1)],
           "neck_bow_mm": round(bow * 1000, 1), "seams": seams, "shaped": shape,
           "strain_mean_pct": next(iter(out_pcs.values()))["rep"]["strain_mean_pct"] if out_pcs else None,
           "toile": {k: info.get(k) for k in ("stand_mm", "fall_mm", "lands_below_seam_cb_mm", "outer_off_toile_mm")},
           "gorge": gorge_seam(out4, Ug, Vg, ks)}
    return out_pcs, out_edges, folds, rep, bad


def gorge_seam(out4, Ug, Vg, ks) -> dict | None:
    """The gorge seam (R3f-9): the collar's end column (the roll -> the outer edge, the left end) and the lapel's first
    column are ONE line of step 4's flap (mark_flap): their 3D lengths equal by construction; each side's flat length
    (the collar flattened above, the lapel flattened alone) reported, never stretched."""
    from .flatten import flatten
    from .mark_flap import load
    Z = load(out4["toile"])
    if "lapel.L:V" not in Z or "flap_layout" not in Z:
        return None
    nr, ncf, _, nl = (int(x) for x in Z["flap_layout"])
    Ul = flatten(Z["lapel.L:V"].astype(float), Z["lapel.L:F"].astype(int))[0].reshape(nr - ks, nl, 2)
    Yl = Z["lapel.L:V"].reshape(nr - ks, nl, 3)
    return {"collar_flat_mm": round(_len(Ug[ks:, -1]) * 1000, 1), "lapel_flat_mm": round(_len(Ul[:, 0]) * 1000, 1),
            "collar_3d_mm": round(_len(Vg[ks:, -1]) * 1000, 1), "lapel_3d_mm": round(_len(Yl[:, 0]) * 1000, 1)}


APART_M = 0.003  # m: a garment neck edge's point farther than this from the collar's neck row is off it


def _apart(G, R) -> dict:
    """Where a garment neck edge G and the collar's neck row R (its run on G) disagree in 3D (C504: fixed there, never
    in the flat): the length of G off R (> APART_M) at each end and in between, G's wiggle (its length over its
    smoothed length) and the largest gap."""
    from scipy.spatial import cKDTree
    d = cKDTree(R).query(G)[0]
    seg = np.linalg.norm(np.diff(G, axis=0), axis=1)
    off = (d[:-1] > APART_M) | (d[1:] > APART_M)
    on = np.where(~off)[0]
    k0, k1 = (int(on[0]), int(on[-1])) if len(on) else (len(seg), len(seg))
    Gs = G.copy()
    for _ in range(4):
        Gs[1:-1] = 0.25 * Gs[:-2] + 0.5 * Gs[1:-1] + 0.25 * Gs[2:]
    return {"off_row_mm": {"start": round(float(seg[:k0].sum()) * 1000, 1), "end": round(float(seg[k1 + 1:].sum()) * 1000, 1),
                           "between": round(float(seg[k0:k1 + 1][off[k0:k1 + 1]].sum()) * 1000, 1)},
            "gap_max_mm": round(float(d.max()) * 1000, 1), "gap_at_mm": np.round(G[int(np.argmax(d))] * 1000, 1).tolist(),
            "edge_ends_mm": np.round(G[[0, -1]] * 1000, 1).tolist(), "wiggle_pct": round((_len(G) / max(_len(Gs), 1e-9) - 1) * 100, 2)}


def _lift():
    from . import draft_fall
    return draft_fall.LIFT


def _behind(Vg, seg_g, d):
    """The outer edge's 3D length over the columns whose neck run lies on the back neck edge (d's last)."""
    back = {d["neck"][-1], mirror(d["neck"][-1])}
    cols = [c for c in range(len(seg_g)) if seg_g[c] in back]
    return float(sum(np.linalg.norm(Vg[-1, c + 1] - Vg[-1, c]) for c in cols))
