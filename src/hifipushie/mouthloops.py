"""Edge loops round an opening modelled into a part (a mouth, a beak's gape, any subtracted blob that breaks the
skin), for parts.<p>.topology = "limbs" (limbloops.build calls `openings`). No template: an opening is a limb turned
inside out, so it takes the same steps.

1. Cavity: the skin that exists only because of the cut (CAVITY_DEPTH inside the part without it); its edge on the
   part's fine mesh is the rim, wherever it runs (a gape wrapping round a muzzle's sides has no flat section
   across it). Ring count from the rim's perimeter over the part's own edge length (even, OPEN_RING_MIN..MAX).
2. Rings: the rim respaced at equal arc length; OPEN_WALLS rings walked from it across the surface toward the
   cavity's back (where the axis, the mean of the rays that escape from the cut's centre, meets the part again)
   until they close up, then a fan of quads; OPEN_JUNCTION rings walked out from the rim over the face.
3. The part's fine mesh inside the outer ring and shallower than the cavity's back (plus two steps) cut, zipped and
   decimated with the rings as border, as a limb's (limbloops.build).
"""
from __future__ import annotations

import numpy as np

from . import sdf

OPEN_RING_MIN, OPEN_RING_MAX = 16, 48  # vertices round an opening's rings
OPEN_JUNCTION = 2  # rings from the rim out over the face
OPEN_WALLS = 6     # at most this many rings down the walls (fewer once a ring's perimeter is under 3 steps)
CAVITY_DEPTH = 0.002  # m: skin this deep inside the part without the cut is the cavity's


def _unit(v):
    v = np.asarray(v, float)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def _enter(prims, c, dirs, reach, steps=240):
    """Where rays from c (outside the part: in the cavity's air) first enter it: (points, distances; inf = never)."""
    t = np.linspace(0, reach, steps)
    f = sdf.field_at(prims, c[None, None] + t[None, :, None] * dirs[:, None], margin=0.02)
    inn = f < 0
    hit = inn.any(1)
    k = np.maximum(inn.argmax(1), 1)
    i = np.arange(len(dirs))
    f0, f1 = f[i, k - 1], f[i, k]
    tt = t[k - 1] + (t[k] - t[k - 1]) * np.clip(f0 / np.where(f0 - f1 == 0, 1, f0 - f1), 0, 1)
    tt = np.where(hit, tt, np.inf)
    return c + np.where(hit, tt, reach)[:, None] * dirs, tt


def _axis(prims, c, reach):
    """The way out of a cut at c: the mean of the rays (a sphere of them) that never meet the part again."""
    g = np.random.default_rng(0).normal(size=(600, 3))
    d = _unit(g)
    _, t = _enter(prims, c, d, reach)
    out = ~np.isfinite(t)
    return _unit(d[out].mean(0)) if out.sum() >= 3 else None


def _edge(V, F, triangles):
    """The part's edge length at `triangles` over its surface (equilateral)."""
    area = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1).sum()
    return float(np.sqrt(4 * area / np.sqrt(3) / max(triangles, 1)))


def _walk_rings(prims, R, target, step, voxel, count, stop_per=0.0, sub=8):
    """Rings walked across the surface from ring R, each point toward target(P) (a direction per point), one step a
    ring, respaced along itself; stops early when a ring's perimeter falls under stop_per."""
    from . import limbloops as LL
    rings, P = [], R.copy()
    for _ in range(count):
        for _ in range(sub):
            g = _unit(sdf.gradient(prims, P, 1e-4))
            t = target(P)
            t = t - g * (g * t).sum(1, keepdims=True)
            P = LL._project(prims, P + _unit(t) * step / sub, voxel, 4)
        P = LL._even(prims, P, voxel)
        if _perimeter(P) < stop_per:
            break
        rings.append(P.copy())
    return rings


def _perimeter(R):
    return float(np.linalg.norm(np.diff(np.r_[R, R[:1]], axis=0), axis=1).sum())


def _resample(P, n):
    Q = np.r_[P, P[:1]]
    cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    s = np.arange(n) / n * cum[-1]
    return np.stack([np.interp(s, cum, Q[:, k]) for k in range(3)], 1)


def opening(prims, cut, V, F, edge, voxel, label):
    """Rings for one opening, outermost first: {label, rings, labels, tip, co, no (into the cavity), step, depth}
    or None when the cut never breaks the skin. The cavity is the skin that exists only because of the cut (inside
    the part without it); its edge on the part's fine mesh (V, F) is the rim, wherever it runs (a gape wrapping
    round a muzzle's sides has no flat section across it)."""
    from . import limbloops as LL
    rest = [p for p in prims if p is not cut]
    pr = cut.params
    c = np.asarray(pr.get("c", (cut.lo + cut.hi) / 2), float)
    size = float(np.max(pr["size"])) if "size" in pr else float(np.max(cut.hi - cut.lo) / 2)
    near = np.linalg.norm(V - c, axis=1) < 3 * size
    cav = np.zeros(len(V), bool)
    cav[near] = sdf.field_at(rest, V[near], margin=0.02) < -CAVITY_DEPTH
    Fc = F[cav[F].all(1)]
    if len(Fc) < 8:
        return None
    Fc = LL._largest(V, Fc)
    loops = LL._boundary_loops(Fc)
    if not loops:
        return None  # a closed cavity: no opening
    rim = V[max(loops, key=len)]
    per = _perimeter(rim)
    n = int(np.clip(2 * round(per / edge / 2), OPEN_RING_MIN, OPEN_RING_MAX))
    step = per / n
    rim = LL._even(prims, _resample(rim, n), voxel)
    a = _axis(prims, c, 4 * size)
    if a is None:
        a = _unit(rim.mean(0) - c)
    if abs(c[0]) < 1e-6:
        a[0] = 0.0  # a cut on the midline opens straight ahead (the random rays aren't symmetric)
        a = _unit(a)
    t_back = _enter(prims, c, -a[None], 4 * size)[1][0]
    back = c - a * (t_back if np.isfinite(t_back) else size)
    walls = _walk_rings(prims, rim, lambda P: back - P, step, voxel, OPEN_WALLS, stop_per=3 * step)
    m = rim.mean(0)
    border = _walk_rings(prims, rim, lambda P: _unit((P - m) - np.outer((P - m) @ a, a)) + 0.5 * a, step, voxel,
                         OPEN_JUNCTION)
    rings = border[::-1] + [rim] + walls
    tip = LL._project(prims, rings[-1].mean(0)[None], voxel, 8)[0]  # (the axis' point sat off the last ring's middle:
    # the fan's quads turned)
    labels = [None] * len(border) + [label + " rim"] + [label + f" wall {i + 1}" for i in range(len(walls))]
    return {"label": label, "rings": rings, "labels": labels, "tip": tip, "co": rings[0].mean(0), "no": -a, "n": n,
            "step": step, "depth": float((rings[0].mean(0) - back) @ a)}


def openings(spec, prims, V, F, part, voxel, triangles, log):
    """Every subtracted blob of the part that breaks its skin, as limbloops features with their cut masks."""
    from . import limbloops as LL
    out = []
    edge = None
    for p in prims:
        if p.op != "subtract" or p.part != part:
            continue
        if edge is None:
            edge = _edge(V, F, triangles)
        op = opening(prims, p, V, F, edge, voxel, p.name)
        if op is None:
            continue
        O, co, no = op["rings"][0], op["co"], op["no"]
        depth = (V - co) @ no
        op["cut"] = LL._inside(V, O, co, no, op["step"]) & (depth < op["depth"] + 2 * op["step"])
        op["planes"] = {}  # an opening's rim needn't be flat: quality checks its rings' own loops (build's "rings")
        log.append(f"{op['label']}: opening, {len(op['rings'])} rings of {op['n']} (rim, "
                   f"{sum(1 for x in op['labels'] if x and 'wall' in x)} down the walls, {OPEN_JUNCTION} over the face), "
                   f"step {op['step'] * 1000:.0f} mm, cavity {op['depth'] * 1000:.0f} mm deep")
        out.append(op)
    return out
