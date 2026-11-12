"""What does not show: skin under cloth, culling under garments, deep hidden faces, hidden export parts. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import asset
from . import sdf, surface

def under_cloth_keep(p: dict, cloth: list[dict]) -> np.ndarray:
    """Per triangle of an export part (the skin): False where all three corners are covered by a garment (one of
    `cloth`'s export parts lies within UNDER_CLOTH_REACH along the vertex normal, inside a UNDER_CLOTH_TUBE line) and
    no uncovered vertex is within UNDER_CLOTH_RIM: the skin under clothes, which games leave out (never seen; in a pose
    it pokes through the cloth)."""
    from scipy.spatial import cKDTree
    V = np.asarray(p["verts"], np.float64)
    cv = np.asarray(p["corner_vert"], np.int64)
    N = np.zeros_like(V)
    np.add.at(N, cv, np.asarray(p["normal"], np.float64))
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    tris = []
    for c in cloth:
        Vc = np.asarray(c["verts"], np.float64)
        tris.append(Vc[np.asarray(c["corner_vert"], np.int64).reshape(-1, 3)])
    T = np.concatenate(tris)  # (m, 3, 3)
    A, E1, E2 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    cen = T.mean(1)
    rad = np.linalg.norm(T - cen[:, None], axis=2).max()
    tree = cKDTree(cen)
    used = np.unique(cv)
    covered = np.zeros(len(V), bool)
    for s in range(0, len(used), 20000):
        ids = used[s:s + 20000]
        for i, nb in zip(ids, tree.query_ball_point(V[ids], asset.UNDER_CLOTH_REACH + rad)):
            if not nb:
                continue
            nb = np.asarray(nb)
            d = N[i]  # Moller-Trumbore: the ray from the vertex along its normal against the nearby cloth triangles
            pv = np.cross(d, E2[nb])
            det = (E1[nb] * pv).sum(1)
            ok = np.abs(det) > 1e-12
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            tv = V[i] - A[nb]
            u = (tv * pv).sum(1) * inv
            qv = np.cross(tv, E1[nb])
            v = (qv @ d) * inv
            t = (E2[nb] * qv).sum(1) * inv
            eps = 1e-4  # (a ray through a shared edge or vertex hits)
            hit = ok & (u >= -eps) & (v >= -eps) & (u + v <= 1 + eps) & (t > -0.002) & (t < asset.UNDER_CLOTH_REACH)
            covered[i] = bool(hit.any())
    open_ = used[~covered[used]]
    if len(open_):
        near = cKDTree(V[open_]).query(V[used], distance_upper_bound=asset.UNDER_CLOTH_RIM)[0] < asset.UNDER_CLOTH_RIM
        covered[used[near]] = False
    return ~covered[cv.reshape(-1, 3)].all(1)


def skin_pose_exposed(p: dict, P0: np.ndarray, covers: list[dict], name: str, cover_names: list[str], poses) -> np.ndarray:
    """(Garrett s14) per LOD0 point P0 (lods_under.under_at_lod0's, vertices of p): True where a triangle using that vertex is
    uncovered (under_cloth_keep, its rim included) in any frame of the `poses` dumps; all False without poses."""
    from scipy.spatial import cKDTree
    out = np.zeros(len(P0), bool)
    if not poses or not len(P0):
        return out
    nt = len(p["corner_vert"]) // 3
    k, _ = cull_exposed_keep(p, covers, name, cover_names, poses, np.zeros(nt, bool))
    if not k.any():
        return out
    vid = np.unique(np.asarray(p["corner_vert"], np.int64).reshape(-1, 3)[k])
    d, nn = cKDTree(np.asarray(p["verts"], np.float64)[vid]).query(np.asarray(P0, np.float64))
    return d < 1e-6


def _over_chain(over: dict, g: str) -> list:
    """The garments under `g` by its chain of "over" (coat -> sweater -> jeans)."""
    out, x = [], over.get(g)
    while x is not None and x not in out and x != g:
        out.append(x)
        x = over.get(x)
    return out


def cloth_under_keep(p: dict, covers: list[dict]) -> np.ndarray:
    """under_cloth_keep for a garment part under other garments. A two-sided garment (p["shell"]: outer triangles, then
    their inner twins, then made pieces / buttons) is tested on its OUTER shell only (the inner shell's vertices face in:
    as "uncovered" vertices they would have kept every rim); each inner triangle goes with its outer twin, the rest stay."""
    nt = len(p["corner_vert"]) // 3
    if not p.get("shell"):
        return under_cloth_keep(p, covers)
    n = int(p["shell"]["outer"])
    po = {"verts": p["verts"], "corner_vert": np.asarray(p["corner_vert"])[:3 * n],
          "normal": np.asarray(p["normal"])[:3 * n]}
    ko = under_cloth_keep(po, covers)
    return np.r_[ko, ko, np.ones(nt - 2 * n, bool)]


def _posed(p: dict, rest: np.ndarray, posed: np.ndarray) -> dict:
    """p with its vertices moved as a dump's mesh moved (each vertex takes its nearest rest vertex's posed position) and
    per-corner normals from the posed triangles' winding."""
    from scipy.spatial import cKDTree
    V = np.asarray(p["verts"], np.float64)
    d, nn = cKDTree(rest).query(V)
    P = np.where((d < 0.002)[:, None], posed[nn], 1e3)  # (a vertex the dump lacks goes far away: never "covered")
    cv = np.asarray(p["corner_vert"], np.int64)
    T = cv.reshape(-1, 3)
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    q = {**p, "verts": P, "normal": np.repeat(fn, 3, axis=0)}
    if p.get("shell"):  # (two-sided: the inner shell's corners keep the winding's own normal, unused by the test)
        q["shell"] = p["shell"]
    return q


def cull_exposed_keep(p: dict, covers: list[dict], name: str, cover_names: list[str], poses, keep: np.ndarray):
    """(r54) The garment-under-garment cull (cloth_under_keep at rest) checked over posed frames: `poses` = npz dumps
    (blender_game shot "dump": "<mesh>:rest" / "<mesh>:posed" per mesh, the clip's frame with skinning, twist, shapes;
    or a glob / list of them) of an export WITHOUT the garment cull. In every frame the under garment and its covers
    are posed (nearest rest vertex) and tested again; a triangle uncovered in any frame is kept. Returns (keep, report)."""
    import glob as glob_
    files = sorted(glob_.glob(poses)) if isinstance(poses, str) else list(poses)
    k = np.asarray(keep, bool).copy()
    rep = {"frames": 0, "restored": 0, "worst": None}
    worst = 0
    for f in files:
        z = np.load(f) if isinstance(f, (str, Path)) else f
        if f"{name}:rest" not in z or not all(f"{c}:rest" in z for c in cover_names):
            continue
        pp = _posed(p, z[f"{name}:rest"], z[f"{name}:posed"])
        cp = [_posed(c, z[f"{cn}:rest"], z[f"{cn}:posed"]) for c, cn in zip(covers, cover_names)]
        kf = cloth_under_keep(pp, cp)
        new = kf & ~k
        rep["frames"] += 1
        if new.sum() > worst:
            worst, rep["worst"] = int(new.sum()), Path(str(f)).stem if isinstance(f, (str, Path)) else str(rep["frames"])
        k |= kf
    rep["restored"] = int(k.sum() - np.asarray(keep, bool).sum())
    return k, rep


def cull_tris(p: dict, keep: np.ndarray) -> dict:
    """p without the triangles `keep` is False for (per-corner arrays cut; vertices, weights, shapes kept), its shell
    layout (outer, inner twins) recounted."""
    cm = np.repeat(keep, 3)
    q = dict(p)
    for k_ in ("corner_vert", "uv", "normal", "tangent", "sign"):
        if q.get(k_) is not None:
            q[k_] = np.asarray(q[k_])[cm]
    if p.get("shell"):
        n = int(p["shell"]["outer"])
        q["shell"] = dict(p["shell"], outer=int(keep[:n].sum()))
    return q


def garment_cull_masks(parts: dict, layer_stack: dict, garments: list) -> dict:
    """(Garrett s10) {under garment: (its LOD0 outward points, whether each is under its covers there, the covers)} for
    cull_under_garments (lods_under.under_at_lod0 against the garments over it in layer_stack)."""
    from . import lods as lodmod
    from . import lods_under
    out = {}
    if not lodmod.LOD_UNDER_CULL_GARMENTS_FROM:
        return out
    for un_, ovs_ in (layer_stack or {}).items():
        cov_ = [parts[o] for o in ovs_ if o in parts]
        if un_ in garments and un_ in parts and cov_:
            P0_, un0_ = lods_under.under_at_lod0(parts[un_], cov_)
            if un0_.any():
                out[un_] = (P0_, un0_, [o for o in ovs_ if o in parts])
    return out


def cull_under_garments(lp: dict, masks: dict, k: int, log: list, rep_l: dict) -> None:
    """(Garrett s10) at LOD k >= lods.LOD_UNDER_CULL_GARMENTS_FROM, each under garment in `lp` (this LOD's parts) drops
    the faces that were deep under its covers at LOD0 (lods_under.cull_covered: beyond LOD_UNDER_CULL_RIM from what showed).
    v7's LOD1 right forearm: the decimated sleeve dips more than the push-under cap under the shirt, a white shard."""
    from . import lods as lodmod
    from . import lods_under
    if not lodmod.LOD_UNDER_CULL_GARMENTS_FROM or k < lodmod.LOD_UNDER_CULL_GARMENTS_FROM:
        return
    for pn, (P0_, un0_, ovs_) in masks.items():
        if pn not in lp:
            continue
        kc_ = lods_under.cull_covered(lp[pn], P0_, un0_)
        if not kc_.all():  # only faces that touch the cover at this LOD (a corner less than LOD_UNDER_GAP under it, or
            # through): the rest still sit under it, and a seated pose that lifts a cover (the jacket's skirt off the
            # trousers) must not open a hole the LOD0 cull (posed) kept closed
            covs_ = [lp[o] for o in ovs_ if o in lp]  # this LOD's (decimated) covers
            vid_, _, _, t_ = lods_under.under_depth(lp[pn], covs_)
            near_ = np.zeros(len(lp[pn]["verts"]), bool)
            near_[vid_] = np.isfinite(t_) & (t_ < lodmod.LOD_UNDER_GAP)
            T_ = np.asarray(lp[pn]["corner_vert"], np.int64).reshape(-1, 3)
            kc_ |= ~near_[T_].any(1)
        if not kc_.all():
            lp[pn] = cull_tris(lp[pn], kc_)
            rep_l.setdefault(pn, {})["covered_culled"] = int((~kc_).sum())
            rep_l[pn]["triangles"] = len(lp[pn]["corner_vert"]) // 3
            log.append(f"LOD{k}: {pn}: {int((~kc_).sum())} of {len(kc_)} triangles deep under its covers at LOD0 dropped "
                       f"(lods_under.cull_covered, {lodmod.LOD_UNDER_CULL_RIM * 1000:.0f} mm rim)")


def _deep_hidden(V: np.ndarray, hidden: np.ndarray, part: np.ndarray, rim: float = asset.HIDDEN_RIM) -> np.ndarray:
    """Hidden vertices with no visible vertex of their own part within `rim`. Faces were dropped right where a part
    goes under another, so the cut ran along every hem, cuff and neckline as a ragged edge one triangle deep (the
    golfer's shirt hem: a solid shell whose inside was cut away exactly at its rounded rim, wavy at rest and
    shedding shards over a lifted thigh). The cut now lies `rim` inside, where nothing looks."""
    from scipy.spatial import cKDTree
    deep = np.asarray(hidden, bool).copy()
    for pi in np.unique(part):
        m = part == pi
        vis = m & ~deep
        hid = np.flatnonzero(m & deep)
        if vis.any() and len(hid):
            d, _ = cKDTree(V[vis]).query(V[hid], distance_upper_bound=rim)
            deep[hid[np.isfinite(d)]] = False
    return deep


def own_mouth_meshes(mesh: Path, mp: dict, log: list) -> None:
    """GNM's tooth rows and tongue as their OWN quads (triangulated) in place of the parts' field meshes in the high mesh: the
    field (IMLS shell, 0.4 mm) decimated to 1200 triangles a row read "jagged, separate pegs with gaps, fang tips"
    (expr_r4 / r5) where GNM's 1414 quads are clean teeth. The parts' min_triangles (base_gnm_parts.MOUTH_PARTS) keep them whole.
    Normals: area-weighted from the quads, turned so the front of the row faces forward."""
    from . import base
    z = dict(np.load(mesh))
    names = [str(n) for n in z["part_names"]]
    V, F, N, P = z["verts"].astype(np.float64), z["faces"], z["normals"].astype(np.float64), z["part"]
    for gn, pn in (("teeth_upper", base.TEETH_PARTS[0]), ("teeth_lower", base.TEETH_PARTS[1]), ("tongue", "tongue")):
        if pn not in names:
            continue
        i = names.index(pn)
        Vg = np.asarray(mp[gn]["verts"], np.float64)
        Q = np.asarray(mp[gn]["faces"])
        T = np.concatenate([Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]])
        c = Vg[T]
        fn = np.cross(c[:, 1] - c[:, 0], c[:, 2] - c[:, 0])
        Ng = np.zeros_like(Vg)
        for k in range(3):
            np.add.at(Ng, T[:, k], fn)
        Ng /= np.maximum(np.linalg.norm(Ng, axis=1, keepdims=True), 1e-12)
        front = Vg[:, 1] < np.percentile(Vg[:, 1], 15)  # (Blender axes: the face looks toward -y; the tongue's tip)
        if (Ng[front, 1] > 0).mean() > 0.5:
            T, Ng = T[:, [0, 2, 1]], -Ng
        keepv = P != i
        remap = np.cumsum(keepv) - 1
        keepf = keepv[F].all(1)
        F = remap[F[keepf]]
        V, N, P = V[keepv], N[keepv], P[keepv]
        F = np.concatenate([F, T + len(V)])
        V, N = np.concatenate([V, Vg]), np.concatenate([N, Ng])
        P = np.concatenate([P, np.full(len(Vg), i, P.dtype)])
        log.append(f"{pn}: GNM's own {gn} quads as its mesh ({len(T)} triangles), not the field's")
    z.update(verts=V.astype(z["verts"].dtype), faces=F.astype(z["faces"].dtype), normals=N.astype(z["normals"].dtype), part=P)
    np.savez(mesh, **z)


def _hide_covered(ctx: dict, z: dict, names: list, hidden: np.ndarray, log: list) -> None:
    """spec parts.<p>.hides (hides.py) on the high mesh, in place on `hidden`: the hidden part's faces its covers
    enclose go (poke-through islands too), and a cover's faces buried only in the hidden part come back where that
    part is now gone (a shoe's inside under toes it hides would leave a see-through hole)."""
    from scipy.spatial import cKDTree
    from . import hides as hidesmod
    rules = hidesmod.rules(ctx.get("defs") or {})
    if not rules:
        return
    origin = ctx["origin"]
    by_part = {k: ps for k, ps in ctx["streams"].items() if origin.get(k, k) == k}
    V = z["verts"].astype(np.float64)
    for i, nm in enumerate(names):
        rule = rules.get(origin.get(nm, nm))
        cov = hidesmod.covers(rule, by_part) if rule else []
        if not cov:
            continue
        sel = np.flatnonzero(z["part"] == i)
        fsel = z["faces"][z["part"][z["faces"][:, 0]] == i]
        loc = np.full(len(V), -1, np.int64)
        loc[sel] = np.arange(len(sel))
        hid = hidesmod.covered(V[sel], loc[fsel], cov, rule["margin"], rule["reach"], rule["rim"])
        hidden[sel] |= hid
        log.append(f"{nm}: {int(hid.sum())} vertices hidden under {', '.join(rule['covers'])}")
        if not hid.any():
            continue
        tree = cKDTree(V[sel])
        for c in rule["covers"]:
            if c not in names:
                continue
            cs = np.flatnonzero((z["part"] == names.index(c)) & hidden)
            if not len(cs):
                continue
            inB = sdf.field_at(ctx["streams"][nm], V[cs]) < -0.5 * ctx["voxel"]
            gone = hid[tree.query(V[cs])[1]]
            others = {k: q for k, q in ctx["streams"].items() if k != nm}
            still = surface.hidden(others, V[cs], np.zeros(len(cs), int), [c], ctx["voxel"]) > 0.5
            back = inB & gone & ~still
            hidden[cs[back]] = False
            if back.any():
                log.append(f"{c}: {int(back.sum())} vertices inside {nm} kept (that part is hidden there)")


def hide_export_part(ctx: dict, pn: str, p: dict, log: list) -> int:
    """spec parts.<p>.hides on a finished export part (its corner arrays, after decimation or a template wrap):
    triangles whose corners the covers enclose are culled. Returns how many were dropped."""
    from . import hides as hidesmod
    rule = hidesmod.rules(ctx.get("defs") or {}).get(ctx["origin"].get(pn, pn))
    by_part = {k: ps for k, ps in ctx["streams"].items() if ctx["origin"].get(k, k) == k}
    cov = hidesmod.covers(rule, by_part) if rule else []
    if not cov:
        return 0
    cv = np.asarray(p["corner_vert"], np.int64)
    keep = hidesmod.keep_faces(np.asarray(p["verts"], np.float64), cv.reshape(-1, 3), cov, rule)
    if keep.all():
        return 0
    cm = np.repeat(keep, 3)
    for k_ in ("corner_vert", "uv", "normal", "tangent", "sign"):
        if k_ in p:
            p[k_] = np.asarray(p[k_])[cm]
    n = int((~keep).sum())
    log.append(f"{pn}: {n} of {len(keep)} triangles under {', '.join(rule['covers'])} culled (parts hides)")
    return n


def prune_hidden(ctx: dict, mesh: Path, log: list, own_surface: dict | None = None) -> Path:
    """Drop faces buried inside another part (skin under solid clothing shells, the back of an eyeball in its
    socket, tooth roots, a chair's feet in the floor): nobody sees them, and they'd take triangles and atlas space.
    own_surface {part: (n, 3) points}: parts that are hidden only in the neutral (GNM's own teeth and tongue behind
    closed lips: a jaw shape brings them out): of those, the faces ON these points (the piece's own outer surface)
    are kept and the rest (the inside of its shell) dropped, whatever covers them."""
    z = dict(np.load(mesh))
    names = [str(n) for n in z["part_names"]]
    hidden = surface.hidden(ctx["streams"], z["verts"].astype(np.float64), z["part"], names, ctx["voxel"],
                            ctx.get("apart")) > 0.5
    hidden = _deep_hidden(z["verts"].astype(np.float64), hidden, z["part"])
    _hide_covered(ctx, z, names, hidden, log)
    for pn, pts in (own_surface or {}).items():
        from scipy.spatial import cKDTree
        for i, nm in enumerate(names):
            if ctx["origin"].get(nm, nm) == pn or nm == pn:
                m = z["part"] == i
                hidden[m] = cKDTree(pts).query(z["verts"][m].astype(np.float64))[0] > asset.OWN_SURFACE
    faces = z["faces"]
    keep = ~hidden[faces].all(1)
    dropped = {pn: int((~keep & (z["part"][faces[:, 0]] == i)).sum()) for i, pn in enumerate(names)}
    log.append("hidden faces dropped: " + ", ".join(f"{k} {v}" for k, v in dropped.items() if v) if any(
        dropped.values()) else "no hidden faces")
    z["faces"] = faces[keep]
    np.savez(mesh, **z)
    return mesh
