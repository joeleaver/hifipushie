"""Extra edge loops in the one mesh's upper lids (facesliders, 2026-10-09).

GNM's lid has dense loops at the margin but, going up the pupil's column (template, mm above the margin), rows only
at 5.4, 7.2, 9.3, 11.8, 14.6: the supratarsal crease (7-8 mm above the lashes on an adult man) and the hooding
fold's edge (8-12 mm) fell between two rows, so a crease or a fold could only be a V notch on one row (likeloop's
"gash"). Three edge loops are inserted, one in the middle of each of the strips 5.4-7.2, 7.2-9.3 and 9.3-11.8: each
strip is a CLOSED edge ring of GNM's quads (200, 200 and 118 quads; they run round both eyes, the first two down the
nose's sides and through the inner corners, where the rings cross themselves and each other: a quad crossed both
ways is cut in four round a centre vertex), so the loops need no poles and are mirror symmetric with the mesh.

Nothing about GNM's own vertices changes: `base._gnm_data` stays GNM's (every fit, region, Laplacian and binding
runs on it exactly as before) and the new vertices are APPENDED after GNM's 17821 (GNM ids N_RAW + j) and after the
asset's own (asset ids). Each is the mean of its PARENTS (an edge's two ends, or a quad's four corners), applied
where the head's vertices are final (`onemesh.template`), so the old vertices are bit-identical; per-vertex tables
are extended by the same rule (`ext`, `take`). A cut quad keeps its index for the child holding its first vertex;
the other children are appended after GNM's quads (and the asset's faces).
"""
from __future__ import annotations

import os

import numpy as np

ENABLED = not os.environ.get("HIFIPUSHIE_NO_LOOPS")  # False builds the one mesh without the loops (comparisons; the asset tables are extended either way)
N_RAW = 17821  # GNM v3_0's vertices
# one edge of each ring (GNM ids), on the left eye's pupil column: rows 5.4-7.2, 7.2-9.3, 9.3-11.8 mm above the margin
SEEDS = ((435, 436), (435, 4702), (1528, 4702))
_CACHE: dict = {}


def _rings(Q: np.ndarray) -> list:
    """Each seed's closed edge ring: [(quad, k)] where the ring enters quad through its edge (q[k], q[k+1])."""
    ef: dict = {}
    for qi, q in enumerate(Q):
        for k in range(4):
            ef.setdefault(frozenset((int(q[k]), int(q[(k + 1) % 4]))), []).append((qi, k))
    out = []
    for a, b in SEEDS:
        e0 = frozenset((a, b))
        qi, k = ef[e0][0]
        ring = []
        while True:
            ring.append((qi, k))
            q = Q[qi]
            opp = frozenset((int(q[(k + 2) % 4]), int(q[(k + 3) % 4])))
            if opp == e0:
                break
            nxt = [x for x in ef[opp] if x[0] != qi]
            assert len(nxt) == 1 and len(ring) < 2000, "an edge ring must close over quads"
            qi, k = nxt[0]
        out.append(ring)
    return out


def _raw():
    if "raw" not in _CACHE:
        from . import assets
        from . import base as basemod
        z = np.load(assets.path("gnm", basemod.GNM))
        assert len(z["template_vertex_positions"]) == N_RAW
        _CACHE["raw"] = {"quads": np.asarray(z["quads"], int), "mirror": np.asarray(z["mirror_indices"], int)}
    return _CACHE["raw"]


def plan() -> dict:
    """{"parents": (k, 4) GNM ids each new vertex is the mean of (an edge's ends twice, or a quad's corners),
    "cuts": [(quad, [children as GNM-id quads])] (the first child takes the quad's index), "quads": GNM's quads with
    the loops cut in, "mirror": (k,) each new vertex's mirror (a new id), "n_quads": GNM's quad count}."""
    if "plan" in _CACHE:
        return _CACHE["plan"]
    Q, mi = _raw()["quads"], _raw()["mirror"]
    marks: dict = {}
    for ring in _rings(Q):
        for qi, k in ring:
            d = k % 2
            assert d not in marks.get(qi, set()), "two rings through one quad the same way"
            marks.setdefault(qi, set()).add(d)
    ids: dict = {}
    parents = []

    def vid(*ps):
        key = tuple(sorted(int(p) for p in ps))
        if key not in ids:
            ids[key] = N_RAW + len(parents)
            parents.append(list(key) * (4 // len(key)))
        return ids[key]

    cuts, extra = [], []
    Qn = Q.copy()
    for qi in sorted(marks):
        q = [int(x) for x in Q[qi]]
        if len(marks[qi]) == 1:
            k = next(iter(marks[qi]))
            a, b, c, d = q[k], q[(k + 1) % 4], q[(k + 2) % 4], q[(k + 3) % 4]
            m, n = vid(a, b), vid(c, d)
            kids = [[a, m, n, d], [m, b, c, n]]  # same winding as the quad
        else:
            e = [vid(q[i], q[(i + 1) % 4]) for i in range(4)]
            c = vid(*q)
            kids = [[q[0], e[0], c, e[3]], [e[0], q[1], e[1], c], [c, e[1], q[2], e[2]], [e[3], c, e[2], q[3]]]
        kids.sort(key=lambda kd: q[0] not in kd)
        Qn[qi] = kids[0]
        extra.extend(kids[1:])
        cuts.append((qi, kids))
    parents = np.array(parents, int)
    mirror = np.array([ids[tuple(sorted(int(mi[p]) for p in set(row)))] for row in parents.tolist()], int)
    _CACHE["plan"] = {"parents": parents, "cuts": cuts, "quads": np.r_[Qn, np.array(extra, int)], "mirror": mirror,
                      "n_quads": len(Q)}
    return _CACHE["plan"]


def _mean(arr, axis):
    p = plan()["parents"]
    return sum(np.take(arr, p[:, c], axis=axis).astype(float) for c in range(4)) / 4.0


def ext(arr, axis: int = 0, how: str = "mean") -> np.ndarray:
    """A per-GNM-vertex table (N_RAW along `axis`) with the new vertices appended: the mean of each one's parents
    ("mean"), all parents true ("all", masks) or the largest ("max")."""
    arr = np.asarray(arr)
    assert arr.shape[axis] == N_RAW, arr.shape
    p = plan()["parents"]
    if how == "all":
        new = np.logical_and.reduce([np.take(arr, p[:, c], axis=axis) for c in range(4)])
    elif how == "max":
        new = np.maximum.reduce([np.take(arr, p[:, c], axis=axis) for c in range(4)])
    else:
        new = _mean(arr, axis)
        if arr.dtype.kind == "f":
            new = new.astype(arr.dtype)
    return np.concatenate([arr, new], axis=axis)


def take(arr, gid, axis: int = 0) -> np.ndarray:
    """arr (per GNM vertex, N_RAW along axis) at GNM ids that may include new ones (>= N_RAW: their parents' mean);
    ids < 0 come back as row 0 (callers mask them as before)."""
    gid = np.asarray(gid, int)
    arr = np.asarray(arr)
    if not (gid >= N_RAW).any():
        return np.take(arr, np.maximum(gid, 0), axis=axis)
    p = plan()["parents"]
    out = np.take(arr, np.clip(gid, 0, N_RAW - 1), axis=axis)
    out = out.astype(float) if arr.dtype.kind != "f" else out.copy()
    nw = np.flatnonzero(gid >= N_RAW)
    j = gid[nw] - N_RAW
    val = sum(np.take(arr, p[j, c], axis=axis).astype(float) for c in range(4)) / 4.0
    idx = [slice(None)] * out.ndim
    idx[axis] = nw
    out[tuple(idx)] = val
    return out


def raw_id(gid) -> np.ndarray:
    """GNM ids with each new one replaced by its first parent (lookups in GNM's own tables)."""
    gid = np.asarray(gid, int)
    if not (gid >= N_RAW).any():
        return gid
    out = gid.copy()
    nw = gid >= N_RAW
    out[nw] = plan()["parents"][gid[nw] - N_RAW, 0]
    return out


def _cut_faces(F, id_map, uv=None):
    """Faces given as rows of some vertex numbering (id_map: GNM id -> that numbering, new ids included): each cut
    GNM quad found among F (by its vertex set) replaced by its first child, the others appended. Returns the new
    faces (list of lists), the uv per face corner when uv is given (a new corner: its parents' mean in that face), and
    the index of the face each appended one came from."""
    P = plan()
    Q = _raw()["quads"]
    pos = {tuple(sorted(int(v) for v in f)): i for i, f in enumerate(F)}
    F = [list(map(int, f)) for f in F]
    uv = None if uv is None else [np.asarray(u, float) for u in uv]
    src = []
    for qi, kids in P["cuts"]:
        i = pos.get(tuple(sorted(int(v) for v in id_map[Q[qi]])))
        if i is None:
            continue
        if uv is not None:
            cu = {int(g): uv[i][[int(x) for x in F[i]].index(int(id_map[g]))] for g in Q[qi]}

            def uvof(gv):
                if gv < N_RAW:
                    return cu[gv]
                return np.mean([cu[int(p)] for p in P["parents"][gv - N_RAW]], axis=0)
        for c, kid in enumerate(kids):
            row = [int(id_map[v]) for v in kid]
            if c == 0:
                F[i] = row
                if uv is not None:
                    uv[i] = np.array([uvof(v) for v in kid])
            else:
                F.append(row)
                src.append(i)
                if uv is not None:
                    uv.append(np.array([uvof(v) for v in kid]))
    return F, uv, src


def extend_asset(a: dict) -> dict:
    """The asset (human_mesh.npz's arrays) with the loops: g2f and gnm_id over the new GNM ids, new asset vertices
    after the asset's own (each one's parents' mean / all / the largest), the cut head faces' other children after its
    faces (uv by the same cut)."""
    if "n_raw_v" in a:
        return a
    P = plan()
    par = P["parents"]
    nv, k = len(a["gnm_id"]), len(par)
    out = dict(a)
    out["n_raw_v"], out["n_raw_f"] = np.array(nv), np.array(len(a["faces"]))
    g2f = np.asarray(a["g2f"], int)
    fp = g2f[par]  # (k, 4) asset ids of the parents
    assert (fp >= 0).all(), "every new vertex lies in the asset's head"

    def mean(x):
        return (sum(x[fp[:, c]].astype(float) for c in range(4)) / 4.0).astype(x.dtype)
    for key in ("neutral", "gmean", "offset", "fade"):
        out[key] = np.r_[a[key], mean(a[key])]
    out["ring"] = np.r_[a["ring"], np.max(a["ring"][fp], axis=1)]
    out["lips"] = np.r_[a["lips"], np.all(a["lips"][fp], axis=1)]
    out["mh_id"] = np.r_[a["mh_id"], -np.ones(k, a["mh_id"].dtype)]
    # gnm_id: a new vertex reads as its first parent (every lookup of a GNM table by it stays in range and near
    # right); gnm_exact: its own id (N_RAW + j), for what must interpolate (face shapes by index: `take`)
    out["gnm_id"] = np.r_[a["gnm_id"], par[:, 0].astype(a["gnm_id"].dtype)]
    out["gnm_exact"] = np.r_[a["gnm_id"], (N_RAW + np.arange(k)).astype(a["gnm_id"].dtype)]
    out["mirror"] = np.r_[a["mirror"], (nv + P["mirror"] - N_RAW).astype(a["mirror"].dtype)]
    out["bind_tri"] = np.r_[a["bind_tri"], a["bind_tri"][fp[:, 0]]]  # (only the bridge's bindings are read)
    out["bind_w"] = np.r_[a["bind_w"], a["bind_w"][fp[:, 0]]]
    # skin weights: the parents' bones, a quarter each, the largest kept
    nb = a["w_idx"].shape[1]
    nwi, nww = np.zeros((k, nb), a["w_idx"].dtype), np.zeros((k, nb), a["w"].dtype)
    for j in range(k):
        acc: dict = {}
        for c in range(4):
            for b_, w_ in zip(a["w_idx"][fp[j, c]], a["w"][fp[j, c]]):
                if w_ > 0:
                    acc[int(b_)] = acc.get(int(b_), 0.0) + 0.25 * float(w_)
        top = sorted(acc.items(), key=lambda t: -t[1])[:nb]
        tot = sum(w_ for _, w_ in top) or 1.0
        for c, (b_, w_) in enumerate(top):
            nwi[j, c], nww[j, c] = b_, w_ / tot
    out["w_idx"], out["w"] = np.r_[a["w_idx"], nwi], np.r_[a["w"], nww]
    out["g2f"] = np.r_[g2f, nv + np.arange(k)].astype(a["g2f"].dtype)
    # (the g_* tables stay GNM's own: the binding, neck fade and hook run on GNM's vertices; per-vertex lookups at a
    # template's new ids go through `take`)
    F, uv, src = _cut_faces(a["faces"], out["g2f"], list(a["uv"]))
    out["faces"] = np.array(F, a["faces"].dtype)
    out["uv"] = np.array(uv, a["uv"].dtype)
    out["part"] = np.r_[a["part"], a["part"][np.array(src, int)]].astype(a["part"].dtype)
    return out
