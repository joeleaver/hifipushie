"""The scene's objects: part voxels, refine boxes, the face's refine and gap, the live grid, `objects`, the
cache's pruning. Part of the live Blender scene (scene.py has the overview)."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np

from . import scene
from . import sdf, store
from . import asset_split
from .scene import _hash
from .scene_inputs import _paint_inputs

def thinnest(ps: list) -> float:
    """The thinnest feature among additive primitives (m): a box's or cylinder's least extent, a bone's
    diameter, an ellipsoid's least axis, a hollow wall. About 2.5 voxels across it meshes cleanly."""
    t = np.inf
    for p in ps:
        if p.op != "add":
            continue
        pr = p.params["p"] if p.kind == "csg" else p.params
        kind = p.params["kind"] if p.kind == "csg" else p.kind
        if kind in ("box", "cylinder", "ellipsoid", "blade"):
            t = min(t, 2 * float(np.min(pr["size"])))
        elif kind == "cone":
            t = min(t, 2 * min(pr["ra"], pr["rb"]) * min(1.0, *pr["flat"]))
        elif kind == "collar":  # a sheet of cloth 2 t thick
            t = min(t, 2 * pr["t"])
        elif kind == "sweep":  # a collar's cloth (2 t), a placket strip's thickness
            v = pr["V"]
            t = min(t, 2 * float(v["t"].min()) if "t" in v else float((v["u1"] - v["u0"]).min()))
        if p.kind == "csg" and p.params.get("hollow"):
            t = min(t, float(p.params["hollow"]))
    return float(t) if np.isfinite(t) else 0.05


def part_voxel(ps: list, voxel: float) -> tuple[float, str]:
    """A scene part's voxel: fine enough for its thinnest element (2.5 voxels across its thinnest feature, 8
    along its whole length: a lantern's glass, a basin's wall), never coarser than the scene voxel nor finer than
    a quarter of it (one thin element makes the whole part fine). Returns (voxel, why)."""
    need, why = voxel, ""
    for p in ps:
        if p.op != "add" or p.kind in ("shell", "displace", "flatten"):
            continue
        t, ext = thinnest([p]), float(np.max(p.hi - p.lo))
        v = min(t / 2.5, ext / 8)
        if v < need:
            need, why = v, f"{p.name}: {t * 1000:.0f} mm thin, {ext * 1000:.0f} mm long"
    floor = voxel / 4
    if need < floor:
        why += f"; capped at {floor * 1000:.1f} mm"
    return float(np.round(max(need, floor), 4)), why


def _split_plane(V, N, F, axis: int, value: float):
    """Triangles cut by the plane x[axis] = value: (verts, normals, faces below, faces above) over one vertex array (V,
    N extended by the cut points, normals interpolated). Triangles wholly on one side are kept whole."""
    s = V[:, axis] - value
    sf = s[F]
    below = (sf <= 0).all(1)
    above = (sf >= 0).all(1) & ~below
    cut = ~(below | above)
    Vn, Nn, memo = [V], [N], {}
    nv = [len(V)]

    def mid(i, j):
        k = (min(i, j), max(i, j))
        if k not in memo:
            t = s[i] / (s[i] - s[j])
            Vn.append((V[i] + t * (V[j] - V[i]))[None])
            n = N[i] + t * (N[j] - N[i])
            Nn.append((n / max(np.linalg.norm(n), 1e-12))[None])
            memo[k] = nv[0]
            nv[0] += 1
        return memo[k]

    tb, ta = [], []
    for tri in F[cut]:
        for side, acc in ((-1.0, tb), (1.0, ta)):
            pts = []
            for k in range(3):
                i, j = int(tri[k]), int(tri[(k + 1) % 3])
                si, sj = s[i] * side, s[j] * side
                if si >= 0:
                    pts.append(i)
                if (si > 0 > sj) or (si < 0 < sj):
                    pts.append(mid(i, j))
            for k in range(1, len(pts) - 1):
                acc.append([pts[0], pts[k], pts[k + 1]])
    fb = np.r_[F[below], np.array(tb, np.int64).reshape(-1, 3)]
    fa = np.r_[F[above], np.array(ta, np.int64).reshape(-1, 3)]
    return np.concatenate(Vn), np.concatenate(Nn), fb, fa


def _box_split(V, N, F, lo, hi):
    """A mesh cut exactly at a box's faces: (verts, normals, faces inside, faces outside)."""
    V, N = np.asarray(V, np.float64), np.asarray(N, np.float64)
    inside, outside = np.asarray(F, np.int64), []
    for ax in range(3):
        for val, keep_below in ((lo[ax], False), (hi[ax], True)):
            V, N, fb, fa = _split_plane(V, N, inside, ax, float(val))
            inside, out = (fb, fa) if keep_below else (fa, fb)
            outside.append(out)
    return V, N, inside, np.concatenate(outside)


def _compact(V, N, F):
    used = np.unique(F)
    rm = np.full(len(V), -1)
    rm[used] = np.arange(len(used))
    return V[used], N[used], rm[F]


def refine_box(ps: list, verts, faces, normals, voxel: float, r: dict):
    """A finer mesh inside one box of a part (parts.<p>.refine: [{"lo", "hi", "voxel"}]): the box meshed on its own
    grid at r["voxel"] and projected onto the same exact field; both meshes are cut exactly at the box's faces (the
    coarse one keeps what lies outside, the fine one what lies inside) and joined. Both cut lines lie on the same
    surface, so they meet within the chords' sagitta (~0.01 mm at 1 mm): no visible crack, and no overlap (an
    overlapping band cast a thin shadow line round the box on Garrett). The grid is uniform per part: this is how a
    face stage gets 0.5 mm lids (a 1 mm voxel can't hold the lid margin, which came out ragged) without four times
    the mesh everywhere. Returns (verts, faces, normals, fine faces kept)."""
    lo, hi, fv = np.asarray(r["lo"], float), np.asarray(r["hi"], float), float(r["voxel"])
    a = np.floor((lo - 3 * voxel) / fv) * fv
    shape = np.ceil((hi + 3 * voxel - a) / fv).astype(int) + 1
    field, _ = sdf.PartGrid().update(ps, (a, fv, shape))
    m = store._mesh_part(ps, field, a, fv, [], {})
    if m is False:
        return verts, faces, normals, 0
    fvv, ffc, fn, _ = m
    Vf, Nf, fin, _ = _box_split(fvv, fn, ffc, lo, hi)
    Vc, Nc, _, cout = _box_split(verts, normals, faces, lo, hi)
    Vf, Nf, fin = _compact(Vf, Nf, fin)
    Vc, Nc, cout = _compact(Vc, Nc, cout)
    V = np.r_[Vc, Vf].astype(np.float32)
    N = np.r_[Nc, Nf].astype(np.float32)
    F = np.r_[cout, fin + len(Vc)].astype(np.int32)
    return V, F, N, int(len(fin))


def kept_face(spec: dict) -> np.ndarray | None:
    """World positions of the face the export KEEPS as the low poly itself (retopo.FACE_KEEP: GNM's expression-basis
    eyes / mouth / nose / ears skin of a base's GNM head, one mesh or grafted), or None without one. The scene meshes
    its part at the part's voxel (7 mm on a body): there the bake's source surface lay 1.0 mm median, 3-6 mm along the
    alae, off the kept face (game_ready.md r67), which is what face_refine fixes."""
    from . import retopo
    from . import base_identity, base_measures
    from .spec import expand_mirror
    b = spec.get("base") or {}
    if not retopo.FACE_KEEP or not b.get("head") or (b.get("head") or {}).get("source", "gnm") != "gnm":
        return None
    h = base_measures.head_of(expand_mirror(spec), b)
    if h is None:
        return None
    g = base_identity._gnm_data()
    V = np.asarray(h["verts"], float)
    ids = np.asarray(h["skin_index"], int) if h.get("skin_index") is not None else np.arange(len(V))
    m = np.zeros(len(V), bool)
    for k in retopo.FACE_KEEP_GROUPS:
        grp = np.asarray(g["groups"][k]) > 0.5
        ok = (ids >= 0) & (ids < len(grp))
        m[ok] |= grp[ids[ok]]
    return V[m] if m.any() else None


def face_refine(P: np.ndarray, voxel: float, cell: float = 0.01) -> list:
    """Refine boxes (parts.<p>.refine's form) over a kept face's points P: one box per cluster (points within `cell`
    of each other: the face, each ear), padded by FACE_REFINE_PAD, at FACE_REFINE_VOXEL. [] when the part is no
    coarser than that."""
    from scipy import ndimage
    if P is None or not len(P) or voxel <= scene.FACE_REFINE_VOXEL * 1.0001:
        return []
    a = P.min(0) - cell
    ijk = np.floor((P - a) / cell).astype(int)
    occ = np.zeros(ijk.max(0) + 2, bool)
    occ[tuple(ijk.T)] = True
    lab, n = ndimage.label(occ, np.ones((3, 3, 3)))
    which = lab[tuple(ijk.T)]
    out = []
    for c in range(1, n + 1):
        Q = P[which == c]
        if len(Q) < 8:
            continue
        out.append({"lo": np.round(Q.min(0) - scene.FACE_REFINE_PAD, 4).tolist(),
                    "hi": np.round(Q.max(0) + scene.FACE_REFINE_PAD, 4).tolist(), "voxel": scene.FACE_REFINE_VOXEL, "auto": "face"})
    return out


def point_mesh_distance(P: np.ndarray, V: np.ndarray, F: np.ndarray, k: int = 24) -> np.ndarray:
    """Distance from each point to a triangle mesh (closest point on the k triangles with the nearest centroids;
    Ericson's region test)."""
    from scipy.spatial import cKDTree
    P, V, F = np.asarray(P, float), np.asarray(V, float), np.asarray(F, int)
    T = V[F]
    k = min(k, len(F))
    _, J = cKDTree(T.mean(1)).query(P, k=k)
    J = J.reshape(len(P), k)
    A, B, C = T[J, 0], T[J, 1], T[J, 2]
    p = P[:, None, :]
    ab, ac, ap = B - A, C - A, p - A
    d1, d2 = (ab * ap).sum(-1), (ac * ap).sum(-1)
    bp = p - B
    d3, d4 = (ab * bp).sum(-1), (ac * bp).sum(-1)
    cp = p - C
    d5, d6 = (ab * cp).sum(-1), (ac * cp).sum(-1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = np.where(np.abs(va + vb + vc) < 1e-30, 1e-30, va + vb + vc)
    v, w = vb / den, vc / den
    Q = A + ab * v[..., None] + ac * w[..., None]  # inside the face
    def seg(X, Y, t):
        return X + (Y - X) * np.clip(t, 0, 1)[..., None]
    eps = 1e-30
    r_ab = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    Q = np.where(r_ab[..., None], seg(A, B, d1 / np.where(np.abs(d1 - d3) < eps, eps, d1 - d3)), Q)
    r_ac = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    Q = np.where(r_ac[..., None], seg(A, C, d2 / np.where(np.abs(d2 - d6) < eps, eps, d2 - d6)), Q)
    r_bc = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    t_bc = (d4 - d3) / np.where(np.abs((d4 - d3) + (d5 - d6)) < eps, eps, (d4 - d3) + (d5 - d6))
    Q = np.where(r_bc[..., None], seg(B, C, t_bc), Q)
    Q = np.where(((d1 <= 0) & (d2 <= 0))[..., None], A, Q)
    Q = np.where(((d3 >= 0) & (d4 <= d3))[..., None], B, Q)
    Q = np.where(((d6 >= 0) & (d5 <= d6))[..., None], C, Q)
    return np.linalg.norm(Q - p, axis=-1).min(1)


def face_gap(P: np.ndarray, verts, faces) -> dict:
    """The kept face's distance to a scene part's mesh, in mm (median, p90, max)."""
    d = point_mesh_distance(P, verts, faces) * 1000
    return {"median": float(np.median(d)), "p90": float(np.percentile(d, 90)), "max": float(d.max()), "n": int(len(d))}


def _frame(ps: list, voxel: float, pad: float = 0.03):
    """A grid around a stream's primitives, snapped to a lattice of `voxel` fixed in space."""
    own = [q for q in ps if q.kind != "shell" and q.op in ("add", "intersect")]
    a = np.min([q.lo for q in own], 0) - pad
    b = np.max([q.hi for q in own], 0) + pad
    # region primitives that come after every add (a crop box round a head: skin_look's stages) bound the part: the
    # grid is theirs, not the whole body's (a 1 mm head stage of a 1.8 m base was a 1e9-cell grid: 12 GB, killed)
    last_add = max([i for i, q in enumerate(own) if q.op == "add"], default=-1)
    tail = [q for q in own[last_add + 1:] if q.op == "intersect"]
    if tail and last_add >= 0:
        ra = np.min([q.lo - float(np.max(q.blend)) for q in tail], 0) - pad
        rb = np.max([q.hi + float(np.max(q.blend)) for q in tail], 0) + pad
        a, b = np.maximum(a, ra), np.minimum(b, rb)
    a = np.floor(a / voxel) * voxel
    return a, voxel, np.ceil((b - a) / voxel).astype(int) + 1


def _live_grid(name: str, key: str, fr) -> dict:
    parts = scene._LIVE.setdefault(name, {})
    st = parts.pop(key, None) or {"grid": sdf.PartGrid()}
    parts[key] = st  # most recently used last
    st["cells"] = int(np.prod(np.asarray(fr[2], np.int64) + sdf.BLOCK))
    while sum(p.get("cells", 0) for p in parts.values()) > scene.LIVE_CELLS and len(parts) > 1:
        parts.pop(next(iter(parts)))
    return st


def objects(name: str, resolution: int = 256, log: list | None = None) -> tuple[list, list]:
    """The scene's objects (meshed or from the cache) and instances, from the current spec."""
    log = [] if log is None else log
    spec = store.load(name)
    ctx = asset_split.split(spec, resolution, True, log, min_share=1)  # every instance its own movable object
    vx = float(np.round(ctx["voxel"], 3))  # a round voxel: resolution edits that don't change it keep the cache
    cache = store._dir(name) / "scene_cache"
    cache.mkdir(exist_ok=True)
    from .base_implied import part_defs
    defs = part_defs(spec)  # (the base's implied parts too: a clear cornea's lens)
    pf_of = {pn: pf for pf, d in ctx["prefabs"].items() for pn in d["parts"]}
    from . import hides as hidesmod
    hide = hidesmod.rules(defs)
    objs, meshed = [], 0
    kept_P = False  # (the kept face's points: worked out once, for the part that carries the base)
    for key, ps in ctx["streams"].items():
        pf = pf_of.get(key)
        if pf is None:  # a scene part: its own voxel, from its thinnest element
            pv, why = part_voxel(ps, vx)
            if (defs.get(key) or {}).get("voxel") and float(defs[key]["voxel"]) < pv:  # asked finer (paint detail:
                pv, why = float(defs[key]["voxel"]), "the part's own voxel"  # an iris on a big eyeball)
            if why:
                log.append(f"{key}: {pv * 1000:.1f} mm voxel ({why})")
            fr = _frame(ps, pv)
        else:  # a prefab: one voxel for all its parts, from its thinnest feature (a cup's wall, a chair's slat)
            own = [q for k in ctx["prefabs"][pf]["parts"] for q in ctx["streams"][k]]
            ext = float((np.max([q.hi for q in own if q.op == "add"], 0) -
                         np.min([q.lo for q in own if q.op == "add"], 0)).max())
            fr = _frame(ps, min(vx, float(np.round(max(thinnest(own) / 2.5, ext / 400), 4))))
        M0 = ctx["prefabs"][pf]["instances"][ctx["prefabs"][pf]["bake"]] if pf else None
        refine = (defs.get(key) or {}).get("refine") if pf is None else None
        face = None
        if pf is None and any(q.kind == "base" and q.name == "base" for q in ps):  # (r68) the part carrying a base: refined over the face
            # the export keeps (whatever head that is), BEFORE the spec's own boxes (a finer lid / lip box still wins)
            if kept_P is False:
                kept_P = kept_face(spec)
            face = kept_P
            auto = face_refine(face, fr[1])
            if auto:
                refine = auto + list(refine or [])
        if pf is None:
            h = _hash(ps, fr, json.dumps(refine, sort_keys=True) if refine else "")
        else:  # the same shape in its own frame wherever its first instance stands: keyed on the definition
            h = hashlib.sha1(json.dumps([spec["prefabs"][pf], key, fr[1], round(float(np.cbrt(np.linalg.det(M0[:3, :3]))), 6)],
                                        sort_keys=True).encode()).hexdigest()[:16]
        f = cache / f"{h}.npz"
        if not f.exists():
            lo, v, shape = fr
            if pf is None:  # a scene part: keep its grid, so an edit re-meshes only the blocks it can reach
                st = _live_grid(name, key, fr)
                try:
                    field, boxes = st["grid"].update(ps, fr)
                    m = store._mesh_part(ps, field, lo, v, boxes, st)
                except BaseException:
                    scene._LIVE.get(name, {}).pop(key, None)  # possibly half updated: start that part cold next time
                    raise
            else:
                field, _ = sdf.PartGrid().update(ps, fr)
                m = store._mesh_part(ps, field, lo, v, [], {})
            if m is False:
                continue
            verts, faces, normals, _ = m
            for r in refine or []:
                t0 = time.time()
                verts, faces, normals, nf = refine_box(ps, verts, faces, normals, fr[1], r)
                log.append(f"{key}: refined {np.round(r['lo'], 3).tolist()}..{np.round(r['hi'], 3).tolist()} at "
                           f"{float(r['voxel']) * 1000:.2f} mm ({nf} faces, {time.time() - t0:.1f} s)")
            if M0 is not None:  # into the prefab's own frame
                A = np.linalg.inv(M0[:3, :3])
                verts = (verts.astype(np.float64) - M0[:3, 3]) @ A.T
                normals = normals @ A.T
                normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
            np.savez(f, verts=verts.astype(np.float32), faces=faces, normals=normals.astype(np.float32))
            meshed += 1
        if face is not None and len(face):  # (r68) the gate: the bake's source must be the export's face here
            z = np.load(f)
            gp = face_gap(face, z["verts"], z["faces"])
            log.append(f"{key}: kept face -> scene mesh {gp['median']:.2f} mm median, p90 {gp['p90']:.2f}, max "
                       f"{gp['max']:.1f} ({gp['n']} points)" + (f"  WARNING: over {scene.FACE_GAP_MAX_MM} mm: the bake's source "
                                                                f"is not the export's face" if gp["median"] > scene.FACE_GAP_MAX_MM else ""))
        rule = hide.get(ctx["origin"][key]) if pf is None else None
        cov = hidesmod.covers(rule, {ctx["origin"][k]: q for k, q in ctx["streams"].items()
                                     if k not in pf_of}) if rule else []
        if cov:  # faces the covering parts enclose (spec parts.<p>.hides): not drawn
            hk = hidesmod.key(rule, cov)
            fh = cache / f"{h}_hide_{hk}.npz"
            if not fh.exists():
                z = dict(np.load(f))
                kf = hidesmod.keep_faces(z["verts"], z["faces"], cov, rule)
                v_, n_, f_ = _compact(z["verts"], z["normals"], z["faces"][kf])  # (Blender drops loose vertices)
                np.savez(fh, verts=v_, faces=f_, normals=n_)
                log.append(f"{key}: {int((~kf).sum())} faces hidden under {', '.join(rule['covers'])}")
            src, f, h = str(f), fh, f"{h}:{hk}"
        else:
            src = None
        objs.append({"key": key, "mesh": str(f), "src_mesh": src, "hash": h, "part": ctx["origin"][key], "prefab": pf, "voxel": fr[1],
                     "color": store.part_colour(ctx["origin"][key], defs, len(objs)).tolist()})
    insts = [{"name": inst, "prefab": pf, "matrix": M.tolist()}
             for pf, d in ctx["prefabs"].items() for inst, M in d["instances"].items()]
    log.append(f"{len(objs)} objects ({meshed} meshed, {len(objs) - meshed} from the cache), {len(insts)} instances")
    prog = _paint_inputs(spec, ctx, objs, insts, cache, log)
    used = {o["mesh"] for o in objs} | {o["inputs"] for o in objs if o.get("inputs")} | {
        o["src_mesh"] for o in objs if o.get("src_mesh")}  # (a hidden part's full mesh: the next edit's start)
    st = cache / "inputs_state.json"
    if st.exists():  # the field and mask files of the last full measuring run: the next edit reuses them
        used |= set(json.loads(st.read_text()).get("files", []))
    freed = prune_cache(cache, used)
    if freed:
        log.append(f"scene cache: {freed / 1e9:.2f} GB of files no recent sync used deleted")
    return objs, insts, prog


def prune_cache(cache: Path, used: set) -> int:
    """Delete the cache's content-named files (meshes, measured inputs, masks) that none of the last KEEP_SYNCS
    syncs used: every edit writes new ones, and unpruned the cabin's cache grew to 8.8 GB. Returns bytes freed."""
    log_f = cache / "used.json"
    recent = json.loads(log_f.read_text()) if log_f.exists() else []
    recent = (recent + [sorted(Path(u).name for u in used)])[-scene.KEEP_SYNCS:]
    log_f.write_text(json.dumps(recent))
    keep = {n for r in recent for n in r}
    freed = 0
    for f in cache.glob("*.npz"):
        if f.name not in keep:
            freed += f.stat().st_size
            f.unlink()
    return freed
