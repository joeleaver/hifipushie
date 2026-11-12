"""Masks: hand-painted values, element random, axis, outline, near and path masks. Part of paint (paint.py has the spec)."""
from __future__ import annotations

import copy

import numpy as np

from . import paint
from .spec import SpecError
from .paint import _ramp, layers, painted_path

def hand_painted(spec: dict) -> dict:
    """The spec's layers with a hand-painted mask: {layer: (id or "new", parts)}; the id is the layer's flat
    "painted" key, else its mask stack's first painted entry."""
    out = {}
    for name, ly in (spec.get("paint") or {}).items():
        pid = ly.get("painted") or next((e["painted"] for e in ly.get("mask") or []
                                         if isinstance(e, dict) and "painted" in e), None)
        if pid:
            parts = ly.get("part", "body")
            out[name] = (pid, [parts] if isinstance(parts, str) else list(parts))
    return out


def set_painted(spec: dict, layer: str, pid: str) -> None:
    """Point the layer's hand-painted entry (as `hand_painted` finds it) at a new cloud, or add one as a flat key."""
    ly = spec["paint"][layer]
    if "painted" in ly:
        ly["painted"] = pid
        return
    for e in ly.get("mask") or []:
        if isinstance(e, dict) and "painted" in e:
            e["painted"] = pid
            return
    ly["painted"] = pid


def save_painted(pos: np.ndarray, nrm: np.ndarray, val: np.ndarray, spacing: np.ndarray) -> str:
    """Store a painted mask (points with value > 0, plus the zeros next to them so it fades out where the person
    stopped; spacing: each point's mesh voxel) and return its id."""
    import hashlib
    from scipy.spatial import cKDTree
    val = np.clip(np.asarray(val, np.float64), 0, 1)
    spacing = np.broadcast_to(np.asarray(spacing, np.float64), val.shape)
    on = val > 1e-3
    keep = on.copy()
    if on.any() and (~on).any():
        d, _ = cKDTree(pos[on]).query(pos[~on], distance_upper_bound=3 * float(spacing.max()))
        keep[np.flatnonzero(~on)[d < 3 * spacing[~on]]] = True
    arrays = {"pos": np.asarray(pos, np.float32)[keep], "nrm": np.asarray(nrm, np.float32)[keep],
              "val": val.astype(np.float32)[keep], "spacing": spacing.astype(np.float32)[keep]}
    h = hashlib.sha1()
    for k in sorted(arrays):
        h.update(k.encode() + np.round(arrays[k], 5).tobytes())
    pid = h.hexdigest()[:16]
    f = painted_path(pid)
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        np.savez(f, **arrays)
    return pid


def painted_values(pid: str, v: np.ndarray, n: np.ndarray) -> np.ndarray:
    """A painted mask at surface points: the painted points within two of their spacings that face the same way,
    weighted by distance (so it doesn't bleed through a thin board to the other side). 0 where nothing was
    painted."""
    from scipy.spatial import cKDTree
    if pid == "new":
        return np.zeros(len(v))
    if pid not in paint._PAINTED:
        f = painted_path(pid)
        if not f.exists():
            raise SpecError(f"hand-painted mask {pid!r} is missing ({f})")
        with np.load(f) as z:
            c = {k: z[k] for k in z.files}
        c["tree"] = cKDTree(c["pos"]) if len(c["pos"]) else None
        paint._PAINTED[pid] = c
    c = paint._PAINTED[pid]
    out = np.zeros(len(v))
    if c["tree"] is None:
        return out
    d, i = c["tree"].query(v, k=8, distance_upper_bound=2.0 * float(c["spacing"].max()))
    ok = np.isfinite(d)
    i = np.where(ok, i, 0)
    r = 2.0 * c["spacing"][i].astype(np.float64)
    face = np.clip(np.einsum("nkc,nc->nk", c["nrm"][i].astype(np.float64), n) * 2 - 0.4, 0, 1)
    w = np.where(ok & (d < r), (1 - np.minimum(d, r) / r) ** 2 * face, 0.0)
    ws = w.sum(1)
    has = ws > 1e-9
    out[has] = (w[has] * c["val"][i][has]).sum(1) / ws[has]
    return out


def element_random(seed: np.ndarray, salt: int = 0) -> np.ndarray:
    """A uniform 0..1 value per element from its grain_seed (a hash of its name), different for each salt."""
    x = np.sin(np.asarray(seed, np.float64) * 12989.8 + salt * 78.233 + 0.5) * 43758.5453
    return x - np.floor(x)


def _axis_mask(spec: dict, name: str, ax: dict, v: np.ndarray) -> np.ndarray:
    if "bone" in ax:
        from .spec import expand_mirror, resolve_point
        s = expand_mirror(spec)
        b = s["bones"].get(ax["bone"])
        if b is None:
            raise SpecError(f"paint {name!r}: unknown bone {ax['bone']!r}")
        a, bb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
        d = bb - a
        t = (v - a) @ d / (d @ d)
        return _ramp(t, float(ax.get("from", 0.0)), float(ax.get("to", 1.0)))
    d = np.asarray(ax.get("dir", [0, 0, 1]), float)
    d = d / np.linalg.norm(d)
    off = 0.0
    if "at" in ax:  # from/to measured from a joint's position along dir
        from .spec import expand_mirror, resolve_point
        off = float(resolve_point(expand_mirror(spec), ax["at"]) @ d)
    return _ramp(v @ d - off, float(ax["from"]), float(ax["to"]))


def _tag_names(spec: dict) -> set:
    """Every tag in the expanded spec (an array's first copy is named like its tag)."""
    import hashlib
    import json
    from .spec import expand_mirror, geometry
    key = hashlib.sha1(json.dumps(geometry(spec), sort_keys=True, default=float).encode()).hexdigest()
    if key not in paint._TAGS:
        if len(paint._TAGS) > 16:
            paint._TAGS.pop(next(iter(paint._TAGS)))
        s = expand_mirror(spec)
        paint._TAGS[key] = {t for k in ("bones", "blobs") for el in s.get(k, {}).values() for t in el.get("tags") or []}
    return paint._TAGS[key]


def _outline_mask(spec: dict, name: str, o: dict, v: np.ndarray, n: np.ndarray) -> np.ndarray:
    """1 inside a closed outline of named points (joints/landmarks, or {"at", "offset"}), as seen along "dir" (a
    region drawn on the model as if on a photo of it: lips, a beard's border), fading over "soft" (m) across its
    edge; only skin facing the viewer (normal . -dir > 0) and within "depth" (m, 0.03) of the outline's own points
    along dir (not the back of the head behind it)."""
    from .spec import expand_mirror, resolve_point
    s = expand_mirror(spec)
    d = np.asarray(o.get("dir", [0, 1, 0]), float)
    d /= np.linalg.norm(d)
    P = []
    for p in o["points"]:
        if isinstance(p, dict):
            q = resolve_point(s, p["at"]) + np.asarray(p.get("offset", [0, 0, 0]), float)
        elif isinstance(p, str):
            q = resolve_point(s, p)
        else:
            q = np.asarray(p, float)
        P.append(q)
    P = np.array(P)
    if len(P) < 3:
        raise SpecError(f"paint {name!r}: an outline needs 3+ points")
    up = np.array([0, 0, 1.0]) if abs(d[2]) < 0.9 else np.array([0, 1.0, 0])
    a = np.cross(up, d)
    a /= np.linalg.norm(a)
    b = np.cross(d, a)
    Q = np.c_[P @ a, P @ b]
    X = np.c_[v @ a, v @ b]
    inside = np.zeros(len(v), bool)
    dist = np.full(len(v), np.inf)
    for i in range(len(Q)):
        p0, p1 = Q[i], Q[(i + 1) % len(Q)]
        cross = ((p0[1] > X[:, 1]) != (p1[1] > X[:, 1]))
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = p0[0] + (X[:, 1] - p0[1]) * (p1[0] - p0[0]) / (p1[1] - p0[1])
        inside ^= cross & (X[:, 0] < xint)
        e = p1 - p0
        t = np.clip(((X - p0) @ e) / max(float(e @ e), 1e-12), 0, 1)
        dist = np.minimum(dist, np.linalg.norm(X - (p0 + t[:, None] * e), axis=1))
    soft = max(float(o.get("soft", 0.001)), 1e-5)
    sd = np.where(inside, dist, -dist)  # + inside
    val = np.clip(0.5 + sd / (2 * soft), 0, 1)
    val = val * val * (3 - 2 * val)
    dep = v @ d
    lo, hi = float((P @ d).min()), float((P @ d).max())
    band = float(o.get("depth", 0.03))
    val *= ((dep > lo - band) & (dep < hi + band)).astype(float)
    return val * _ramp(-(n @ d), 0.0, 0.3)


def _near_mask(spec: dict, name: str, ly: dict, v: np.ndarray) -> np.ndarray:
    from . import sdf
    from .spec import compile_prims
    want = [ly["near"]] if isinstance(ly["near"], str) else list(ly["near"])
    prims = {p.name: p for p in compile_prims(spec)}
    tagged = _tag_names(spec)
    for w in list(want):  # a kit name stands for everything it generates (hand.L -> hand_*.L)
        if w in (spec.get("kits") or {}) and w not in prims:
            stem, sfx = (w[:-2], w[-2:]) if w.endswith((".L", ".R")) else (w, "")
            want.remove(w)
            want += [n for n, p in prims.items() if n.startswith(stem + "_") and n.endswith(sfx) and p.kind in sdf.SDF
                     and p.kind != "shell" and p.op == "add"]
    if any(w not in prims or w in tagged for w in want):  # tags: instances, arrays, "tags" lists
        from .assemble import select
        from .spec import expand_mirror
        asked = set(want)
        # a tag's members include targeted cuts, which are folded into their targets (no primitive of their own)
        want = [w for w in select(expand_mirror(spec), want) if w in prims or w in asked]
    missing = [w for w in want if w not in prims]
    if missing:
        raise SpecError(f"paint {name!r}: no bone or blob {missing} (kit output names are listed by get_model)")
    d = np.full(len(v), np.inf)
    for w in want:
        p = prims[w]
        if p.kind == "fold":  # a lid fold (lidfold.py): the distance across from its crease line
            from .lidfold import line_distance
            d = np.minimum(d, line_distance(v, p.params, ly.get("side")))
            continue
        if p.kind not in sdf.SDF or p.kind == "shell":
            raise SpecError(f"paint {name!r}: {w!r} is a {p.kind}, not a shape")
        dd = sdf.SDF[p.kind](v, p.params)
        # "side": "both" = the unsigned distance (a point inside the shape is not "near" unless it is near its surface:
        # an eyeball in a head's socket lies inside the head's field, so its lids' shadow band covered the whole ball)
        d = np.minimum(d, np.abs(dd) if ly.get("side") == "both" else dd)
    within, soft = float(ly.get("within", 0.0)), float(ly.get("soft", 0.01))
    return 1 - _ramp(d, within, within + max(soft, 1e-6))


def _seated_paths(spec: dict, name: str, ly: dict) -> list[dict]:
    """The layer's path seated on the surface, as stroke samples (pts, nrm, width per sample), one per copy."""
    from . import anatomy, kits, strokes
    from .spec import geometry
    base = strokes.seat_joints(anatomy.expand(kits.expand(geometry(spec))))
    base = copy.copy(base)
    base.pop("strokes", None)
    st = {"op": "clay", "path": ly["path"], "width": ly.get("width", 0.01), "depth": 0.001}
    for k in ("repeat", "scatter"):
        if k in ly:
            st[k] = ly[k]
    part = ly.get("part", "body")
    if isinstance(part, str) and part != "*" and part != "body":
        st["part"] = part
    return list(strokes._generate(base, {f"paint:{name}": st})["blobs"].values())


def _path_entries(ly: dict, part):
    """(entry, part) for every path a layer gives, its mask stack's (nested) included; a stack entry is seated
    on the layer's part."""
    if "path" in ly:
        yield ly, ly.get("part", part)
    for e in ly.get("mask") or []:
        if isinstance(e, dict):
            yield from _path_entries(e, part)


def check_paths(spec: dict) -> None:
    """Seat every paint path now (cached by content, so the sync reuses it): a path that can't be seated fails
    the edit that made it, not a sync or look minutes later."""
    for name, ly in layers(spec).items():
        part = ly.get("part", "body")
        for e, pn in _path_entries(ly, part):
            if not isinstance(pn, str) or pn == "*":
                continue  # seated per part the points are on, at paint time
            _seated_paths(spec, name, {**e, "part": pn})


def _path_mask(spec: dict, name: str, ly: dict, v: np.ndarray, n: np.ndarray) -> np.ndarray:
    from scipy.spatial import cKDTree
    from .sdf import PROFILES
    from .spec import _profile_norm
    prof_name = ly.get("profile", "flat")
    if prof_name not in PROFILES:
        raise SpecError(f"paint {name!r}: unknown profile {prof_name!r} (have {', '.join(PROFILES)})")
    prof = PROFILES[prof_name][0]
    out = np.zeros(len(v))
    for bl in _seated_paths(spec, name, ly):
        P, N, W = (np.asarray(bl[k], float) for k in ("pts", "nrm", "width"))
        N = N / np.linalg.norm(N, axis=1, keepdims=True)
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1) if len(P) > 1 else np.zeros(0)
        ds = np.concatenate([seg, [0.0]]) / 2 + np.concatenate([[0.0], seg]) / 2
        gain = ds / (W * _profile_norm(prof_name)) if len(P) > 1 else np.ones(1)
        reach = np.maximum(W, 0.02)  # along the normal: covers what strokes pushed in or out
        R = float(np.hypot(W.max(), 2 * reach.max()))
        step = float(ds[ds > 0].min()) if (ds > 0).any() else 1.0
        K = int(min(len(P), 2 * W.max() / step + 4))
        box = np.all((v >= P.min(0) - R) & (v <= P.max(0) + R), axis=1)
        sel = np.flatnonzero(box)
        if not len(sel):
            continue
        q = v[sel]
        dist, idx = cKDTree(P).query(q, k=K, distance_upper_bound=R)
        idx = idx.reshape(len(q), K)
        ok = idx < len(P)
        j = np.where(ok, idx, 0)
        r = q[:, None, :] - P[j]
        h = (r * N[j]).sum(-1)
        lat = np.sqrt(np.maximum((r * r).sum(-1) - h * h, 0.0)) / W[j]
        k = np.where(ok & (lat < 1.0), prof(np.minimum(lat, 1.0)), 0.0)
        k *= 1 - _ramp(np.abs(h), reach[j], 2 * reach[j])
        k *= _ramp((n[sel][:, None, :] * N[j]).sum(-1), 0.0, 0.3)  # skin facing the path's way: no print-through
        out[sel] = np.maximum(out[sel], np.clip((k * gain[j]).sum(1), 0, 1))
    return out
