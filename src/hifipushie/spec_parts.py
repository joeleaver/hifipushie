"""Parts and their shapes, compiled: `_parts`, sweeps and lids, a profile and its norm, modifiers, and the reach of each primitive (`_set_reach`). Part of the spec module (spec.py has the format and every constant)."""
from __future__ import annotations

import numpy as np

from . import spec
from .spec import Prim, SpecError

def _parts(prims: list[Prim], defs: dict, k_default: float, joints: dict | None = None) -> list[Prim]:
    """Order primitives part by part (body first, shells after the part they follow), each part sorted and
    clipped on its own. A shell part ({"shell": base, "offset", "thickness"?}) is its base part's surface pushed
    out by offset (solid; or only a layer `thickness` deep), cut to the union of its own layer-0 additive
    primitives (its region); its higher-layer adds (buttons, a buckle) and its strokes go on top."""
    by_part: dict[str, list[Prim]] = {}
    for p in prims:
        by_part.setdefault(p.part, []).append(p)
    for name, d in defs.items():
        if d.get("shell"):
            by_part.setdefault(name, [])
    done: dict[str, list[Prim]] = {}
    pending = sorted(by_part, key=lambda n: (n != "body", n))
    while pending:
        progressed = False
        for name in list(pending):
            d = defs.get(name) or {}
            base = d.get("shell")
            if base and base not in done:
                if base not in by_part:
                    raise SpecError(f"part {name!r}: shell of unknown part {base!r}")
                continue
            ps = list(by_part[name])
            if base:
                off, th = float(d.get("offset", 0.006)), float(d.get("thickness") or 0.0)
                bp = done[base]
                badds = [q for q in bp if q.op == "add"]
                pad = off
                bq = next((q for q in bp if q.kind == "base"), None)
                if d.get("garment") and bq is None:
                    raise SpecError(f"part {name!r}: a garment is built from a base body (spec base)")
                if d.get("garment"):  # a garment with its own volume: from the base mesh, closed and eased (base.py)
                    from . import base_tubes
                    gs = base_tubes.garment(bq.params["key"], d["garment"], off, joints or {})
                    shells = [Prim(f"{name}:garment{k or ''}", "base", "add", float(d.get("garment_blend", 0.02)), 0,
                                   g["verts"].min(0) - 0.05, g["verts"].max(0) + 0.05, g, reach=1.0, part=name)
                              for k, g in enumerate(gs)]
                else:
                    shells = [Prim(f"{name}:shell", "shell", "add", k_default, 0,
                                   np.min([q.lo for q in badds], 0) - pad, np.max([q.hi for q in badds], 0) + pad,
                                   {"prims": bp, "offset": off, "thickness": th}, part=name)]
                for q in ps:  # the region: layer-0 adds, unioned (by `blend`) then intersected with the shell
                    if q.op == "add" and q.layer == 0:
                        q.op, q.group, q.join = "intersect", f"region:{name}", float(d.get("blend", 0.01))
                ps[:0] = shells
            ps.sort(key=lambda p: (p.layer, spec.OP_ORDER[p.op], p.group or ""))
            _set_reach(ps)
            done[name] = ps
            pending.remove(name)
            progressed = True
        if not progressed:
            raise SpecError(f"parts {pending}: shells form a cycle")
    return [p for ps in done.values() for p in ps]


def _sweep(name: str, bl: dict, k: float) -> Prim:
    """A "sweep" blob: {"path": [[x,y,z], ...], "N": outward dirs, "U": up dirs (per vertex), "profile": "collar" |
    "band", "values": {key: number or per-vertex list}, "mirror"?: evaluate at |x|, "open_start"?: no cap at the
    path's start (a mirrored path starting on x = 0)}. Usually written by a kit (kits "garment")."""
    P = np.asarray(bl.get("path") or [], float)
    prof = bl.get("profile", "band")
    if prof not in spec.SWEEP_KEYS:
        raise SpecError(f"blob {name!r}: sweep profile {prof!r} (have {', '.join(spec.SWEEP_KEYS)})")
    if P.ndim != 2 or P.shape[1] != 3 or len(P) < 2:
        raise SpecError(f"blob {name!r}: a sweep's path is a list of 2+ points")
    d = P[1:] - P[:-1]
    L = np.linalg.norm(d, axis=1)
    if np.any(L < 1e-9):
        raise SpecError(f"blob {name!r}: repeated point in the sweep's path")
    T = d / L[:, None]
    Sv = np.concatenate([[0.0], np.cumsum(L)])

    def unit(key):
        A = np.asarray(bl.get(key), float)
        if A.shape != P.shape:
            raise SpecError(f"blob {name!r}: sweep {key} needs one direction per path point")
        return A / np.maximum(np.linalg.norm(A, axis=1, keepdims=True), 1e-12)
    vals = {}
    for key in spec.SWEEP_KEYS[prof]:
        v = np.broadcast_to(np.asarray((bl.get("values") or {}).get(key, 0.0), float), (len(P),)).copy()
        vals[key] = v
    if prof == "collar":
        R = np.max(vals["stand"] + vals["sink"] + 2 * vals["t"] + vals["lean"] + vals["fall"] * (1 + vals["point"]))
    else:
        R = np.max(np.abs(np.concatenate([vals["n0"], vals["n1"], vals["u0"], vals["u1"]])))
    lo, hi = P.min(0) - R, P.max(0) + R
    if bl.get("mirror"):
        m = max(abs(lo[0]), abs(hi[0]))
        lo[0], hi[0] = -m, m
    pr = {"P": P, "T": T, "L": L, "S": Sv[:-1], "Sv": Sv, "N": unit("N"), "U": unit("U"), "profile": prof,
          "V": vals, "mirror": bool(bl.get("mirror")),
          "open_start": bool(bl.get("open_start")), "lip": float(bl.get("lip", 1.3))}
    return Prim(name, "sweep", bl.get("op", "add"), k, int(bl.get("layer", 0)), lo, hi, pr, reach=4.0)


def _lids(name: str, bl: dict, c: np.ndarray, rot: np.ndarray, k: float) -> Prim:
    """Eyelids blob: {"shape": "lids", "at", "rot", "r": eyeball radius, "thickness", "upper"/"lower": how
    much of the eye each lid covers (0..1, from its own edge), "width": corner half-width / r}."""
    r = float(bl["r"])
    ro = r + float(bl.get("thickness", 0.25 * r))
    hu = r * (1 - 2 * float(bl.get("upper", 0.35)))    # margin heights at the middle
    hl = -r * (1 - 2 * float(bl.get("lower", 0.15)))
    w = r * float(bl.get("width", 0.85))
    params = {"c": c, "rot": rot, "r": r, "ro": ro, "round": 0.5 * (ro - r), "closed": hu - hl < 0.02 * r}
    if not params["closed"]:
        zc = 0.35 * hu + 0.65 * hl                      # corners sit low, so the upper lid arches more
        au, al = hu - zc, zc - hl
        cu = (au * au - w * w) / (2 * au)               # circle through both corners and the margin's middle
        cl = (al * al - w * w) / (2 * al)
        params.update(cu=zc + cu, Ru=au - cu, cl=zc - cl, Rl=al - cl)
    return Prim(name, "lids", bl.get("op", "add"), k, int(bl.get("layer", 0)), c - ro, c + ro, params, reach=1.0)


def _profile_norm(prof: str) -> float:
    """A dab's integral along a straight trail (per unit width), which normalises a stroke to its depth."""
    if prof not in spec._NORMS:
        from .sdf import PROFILES
        v = np.linspace(-1, 1, 2001)
        spec._NORMS[prof] = float(np.trapezoid(PROFILES[prof][0](np.abs(v)), v))
    return spec._NORMS[prof]


def _tree(P: np.ndarray):
    """KD-tree over a stroke's samples, reused while the stroke doesn't move."""
    import hashlib
    from scipy.spatial import cKDTree
    key = hashlib.sha1(np.ascontiguousarray(P).tobytes()).digest()
    if key not in spec._TREES:
        if len(spec._TREES) > 2000:
            spec._TREES.clear()
        spec._TREES[key] = cKDTree(P)
    return spec._TREES[key]


def _modifier(name: str, bl: dict, c: np.ndarray) -> Prim:
    """Stroke output: {"shape": "displace", "pts", "nrm", "width", "depth" (per point), "profile"} or
    {"shape": "flatten", "pts": 1-2 plane points, "nrm": [normal], "width", "soft", "height", "blend"}.
    Modifiers reshape everything combined before them (layer order), only inside their box."""
    P = np.asarray(bl["pts"], float) + c
    N = np.asarray(bl["nrm"], float)
    if bl["shape"] == "flatten":
        w, soft, height = float(bl["width"]), float(bl["soft"]), float(bl["height"])
        R = w + soft
        params = {"pts": P, "nrm": N / np.linalg.norm(N, axis=1, keepdims=True), "width": w, "soft": soft,
                  "height": height, "blend": float(bl.get("blend", 0.0))}
        lo, hi = P.min(0) - R, P.max(0) + R
        lip = 1.0 + 1.5 / soft * 2 * height
    else:
        W, D = np.asarray(bl["width"], float), np.asarray(bl["depth"], float)
        if not (len(P) == len(N) == len(W) == len(D)) or np.any(W <= 0):
            raise SpecError(f"stroke {name!r}: needs one nrm/width/depth per point, widths > 0")
        prof = bl.get("profile", "soft")
        from .sdf import PROFILES
        if prof not in PROFILES:
            raise SpecError(f"stroke {name!r}: unknown profile {prof!r} (have {', '.join(PROFILES)})")
        # full strength within `reach` of the path along the normal, fading to nothing at twice that: enough to
        # cover the displaced surface (|depth| away) with a gentle fade, without reaching through thin parts
        reach = float(max(2 * np.abs(D).max(), 0.25 * W.max(), 1e-3))
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1) if len(P) > 1 else np.zeros(0)
        ds = np.concatenate([seg, [0.0]]) / 2 + np.concatenate([[0.0], seg]) / 2  # arc length per sample
        norm = _profile_norm(prof)
        radius = float(np.hypot(W.max(), 2 * reach))  # a dab can reach a point this far away, at most
        step = float(ds[ds > 0].min()) if (ds > 0).any() else 1.0
        params = {"pts": P, "nrm": N / np.linalg.norm(N, axis=1, keepdims=True), "width": W, "depth": D,
                  "profile": prof, "reach": reach, "ds": ds, "norm": norm,
                  "radius": radius, "k": int(min(len(P), 2 * radius / step + 4))}
        params["tree"] = _tree(P)
        R = float(max(W.max(), 2 * reach))
        lo, hi = P.min(0) - R, P.max(0) + R
        lip = 1.0 + float((np.abs(D) / W).max()) * PROFILES[prof][1] + float(np.abs(D).max()) * 1.5 / reach
    return Prim(name, bl["shape"], "modify", 0.0, int(bl.get("layer", 0)), lo, hi, params, lip=lip)


def _set_reach(prims: list[Prim]) -> None:
    """Turn each primitive's reach-per-unit-blend (set above) into a distance past its AABB beyond which
    it can be skipped without changing the combined field. That needs its value to stay out of its own
    blend and out of the blend of every later primitive that overlaps it (a fillet from a later part
    rounds toward everything already combined), plus k/4 for the dip smooth union adds."""
    widest: dict = {}  # a fused mass also rounds toward its fellows, by as much as the widest fill in its fuse
    for q in prims:
        if (q.group or "").startswith("fuse:"):
            widest[q.group] = max(widest.get(q.group, 0.0), q.join)

    def blend(q: Prim) -> float:
        return max(q.blend, widest[q.group]) if q.group in widest else q.blend

    scale = [np.broadcast_to(np.asarray(p.reach, float), (3,)) for p in prims]
    for i in range(len(prims) - 1, -1, -1):
        p, k = prims[i], blend(prims[i])
        if p.op == "modify":  # applied exactly within its box, not blended: nothing to widen
            p.reach, p.inert = 0.0, 0.0
            continue
        for q in prims[i + 1:]:
            # (a fuse's fill rounds its own fellows only: the fused mass meets everything else by its blend. Taken
            # for every neighbour, a folded ear beside a fused head and body reached 0.8 m and a 0.2 s build took 6 s)
            kq = blend(q) if q.group == p.group else q.blend
            if q.op != "modify" and kq * 1.25 > k and np.all(p.lo - scale[i] * kq * 1.25 <= q.hi + q.reach) \
                    and np.all(q.lo - q.reach <= p.hi + scale[i] * kq * 1.25):
                k = kq * 1.25
        p.reach, p.inert = scale[i] * k, k
