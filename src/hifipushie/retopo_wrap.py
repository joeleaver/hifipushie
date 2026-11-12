"""`wrap` and what it starts from: base_quads, the lid and face keep regions, the mouth sock. Part of retopo (retopo.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import retopo
from . import sdf, surface
from .spec import compile_prims, expand_mirror
from .retopo import _seg_dist, edges, load_template, topology
from .retopo_fit import _fit, _untangle, graft_head
from .retopo_patches import _patches, _plan_cuts, _stitch
from .retopo_warp import _face_warp, _skeleton_warp, _smooth_away

# ---------------------------------------------------------------------------------------------------- main
def base_quads(spec: dict, log: list) -> dict | None:
    """A base body's OWN quads as its topology (the same dict as `wrap`): the posed body mesh the field is made from
    (`base_surface.surface()["quads"]`: MakeHuman's or the template's animation topology, fingers and all), its vertices
    dropped onto the field (a subdivision cage stands a little off its limit surface; pushes and strokes count),
    a grafted head bridged on as before. Carrying ANOTHER template onto a base (the stylised male's digit tubes
    onto MakeHuman's close-set fingers) tore both hands at the webs and the thumb's root, at rest: the golfer's
    "cracked" disc hand, 2251 faces still turned after the untangle. parts.body.topology = "template" for that path.
    None when the base has no quads of its own."""
    from . import base as basemod
    from . import base_identity, base_surface
    s = expand_mirror(spec)
    sf = base_surface.surface(s, spec["base"])
    if not sf.get("quads"):
        return None
    Vq, fq = sf["quads"]
    V = np.array(Vq, float)
    L = np.array([v for f in fq for v in f])
    S = np.array([len(f) for f in fq])
    prims = [p for p in compile_prims(spec) if p.part == "body"]
    lo = np.min([p.lo for p in prims], 0)
    hi = np.max([p.hi for p in prims], 0)
    voxel = float((hi - lo).max()) / 200
    V0 = V.copy()
    one = (spec["base"].get("body") or {}).get("source") == "human"
    gnm = None
    if one:  # (onemesh.py) which GNM vertex each is (-1: MakeHuman's body or the bridge): face shapes go by index
        from . import onemesh
        tpl = basemod.source(spec["base"])
        gnm = np.asarray(onemesh.asset()["gnm_exact"], int)[np.asarray(tpl["fid"])]  # (gnmloops: the lids' new
        # vertices carry their own ids, >= gnmloops.N_RAW; GNM's tables are read at their first parent's: raw_id)
        g = base_identity._gnm_data()
        from . import gnmloops
        rid = np.maximum(gnmloops.raw_id(gnm), 0)
        ext = np.asarray(g["groups"]["skin_exterior"]) > 0.5
        inner = (gnm >= 0) & ~ext[rid]  # lid insides, inner lip rolls, nostrils' depths
        ears = np.asarray(g["groups"]["ears"]) > 0.5  # (thin folded shells: dropped onto the smoothed field their
        inner |= (gnm >= 0) & ears[rid]  # quads folded: TORN at the head, 60 spots on Garrett's ears)
        lf = (spec["base"].get("head") or {}).get("lid_fold")
        if lf:   # (projskin) the lid FOLD is re-entrant (the hood hangs over its own slit): projected onto the field its
            # sheets collapsed into each other, TORN OR TANGLED at both lids (300 folded edges on an older head, 82 without the
            # fold): the fold's own vertices stay as base.head.lid_fold built them (exact; the field is the smoothed copy)
            from . import gnm_fold
            dlt = gnm_fold.mesh_delta(gnm_fold.vertices() / 1000.0, None, lf)
            moved = np.linalg.norm(dlt, axis=1) > 1e-6
            inner |= (gnm >= 0) & moved[np.clip(rid, 0, len(moved) - 1)]
    V = surface.newton(prims, V, voxel * 0.125, voxel, iterations=12)[0]
    if one and (retopo.FACE_KEEP or retopo.LID_KEEP):  # GNM's face stays as the approved head has it (see face_keep)
        w = face_keep(gnm, fq) if retopo.FACE_KEEP else lid_keep(gnm, fq)
        V = V0 + (1.0 - w)[:, None] * (V - V0)
    # (the cage stands <= ~2.5 mm off; what moves further is the neck tube's upper rings inside a grafted head, cut
    # away below, or a step that went astray)
    far = np.linalg.norm(V - V0, axis=1) > 0.004
    if one:  # GNM's own interior surfaces (they roll back under the lids, behind the lips) aren't the field's
        # surface: dropped onto it they folded (TORN OR TANGLED at both eyes). They stay as GNM placed them.
        far |= inner
    V[far] = V0[far]
    mv = np.linalg.norm(V - V0, axis=1)[~far] * 1e3
    log.append(f"wrapped: the base body's own quads, {len(V)} verts, {len(S)} faces ({(S == 4).mean():.0%} quads); "
               f"moved onto the field by mean {mv.mean():.2f} p95 {np.percentile(mv, 95):.2f} max {mv.max():.1f} mm"
               + (f", {int(far.sum())} left where they were" if far.any() else ""))
    # (a fused one-mesh source, body.source "human", has its head in these quads already: no graft)
    if (spec["base"].get("head") or {}).get("source", "gnm") == "gnm" and spec["base"].get("head") \
            and (spec["base"].get("body") or {}).get("source") != "human":
        V, L, S = graft_head(V, L, S, spec, prims, log)
    out = {"verts": V, "loops": L, "sizes": S, "origin": np.zeros(len(V), int), "log": log, "patches": {}}
    if one:
        V, L, S, gnm = _with_mouth_sock(V, L, S, gnm, spec, s, log)
        out.update(verts=V, loops=L, sizes=S, origin=np.zeros(len(V), int), gnm=gnm)
    return out


def lid_keep(gnm, faces, rings: int | None = None) -> np.ndarray:
    """(one mesh) per cage vertex, 0..1: how much of its drop onto the field is undone. 1 on GNM's eye regions
    (expression_basis_left_eye / _right_eye: the lids and the skin round them), fading to 0 over LID_KEEP_RINGS rings."""
    return face_keep(gnm, faces, rings, retopo.FACE_KEEP_GROUPS[:2])


def face_keep(gnm, faces, rings: int | None = None, groups=None) -> np.ndarray:
    """(one mesh) per cage vertex, 0..1: how much of its drop onto the field is undone: 1 on GNM's face (the
    FACE_KEEP_GROUPS: eyes, mouth, nose; the cage there is the approved head), fading to 0 over LID_KEEP_RINGS rings."""
    from . import base_identity
    from . import gnmloops
    g = base_identity._gnm_data()
    gnm = np.asarray(gnm, int)
    rid = np.maximum(gnmloops.raw_id(gnm), 0)
    eye = np.zeros(len(rid), bool)
    for k in (retopo.FACE_KEEP_GROUPS if groups is None else groups):
        eye |= (np.asarray(g["groups"][k]) > 0.5)[rid]
    eye &= gnm >= 0
    w = eye.astype(float)
    if not eye.any():
        return w
    a, b = [], []
    for f in faces:
        f = list(f)
        a += f; b += f[1:] + f[:1]
    a, b = np.array(a), np.array(b)
    n = retopo.LID_KEEP_RINGS if rings is None else rings
    for i in range(n):  # ring by ring outward: ring k keeps 1 - k / (n + 1)
        nb = np.zeros(len(w), bool)
        nb[b[w[a] > 0]] = True
        nb[a[w[b] > 0]] = True
        new = nb & (w == 0)
        w[new] = 1.0 - (i + 1) / (n + 1)
    return w


def _with_mouth_sock(V, L, S, gnm, spec, s, log):
    """(onemesh.py) GNM's mouth sock added to the one mesh's own quads: the skin's open mouth loop (the end of the
    inner lip rolls) closed by GNM's own oral cavity, placed as the head places its skin, so a parted or opened mouth
    shows a mouth, not the inside of the head. Not with zipped lips (a closed mouth has no loop)."""
    from . import base_identity
    from . import onemesh_head
    h = onemesh_head.head(s, spec["base"])
    if h.get("lips_zipped"):
        return V, L, S, gnm
    g = base_identity._gnm_data()
    c = h["carry"]
    sock = np.asarray(g["groups"]["mouth_sock"]) > 0.5
    where = np.full(len(sock), -1)
    ok = (gnm >= 0) & (gnm < len(sock))  # (gnmloops' new vertices: not GNM's own, never by the sock)
    where[gnm[ok]] = np.flatnonzero(ok)
    Q = np.asarray(g["quads"])
    skin = np.asarray(g["skin"], bool)
    q = Q[(sock[Q] | skin[Q]).all(1) & sock[Q].any(1) & ((where[Q] >= 0) | sock[Q]).all(1)]
    new = np.unique(q[where[q] < 0])
    if not len(new):
        return V, L, S, gnm
    where[new] = len(V) + np.arange(len(new))
    place = lambda X: c["eye_mid"] + c["s"] * (np.asarray(X, float) - c["mid"]) @ np.asarray(c["R"], float).T  # noqa: E731
    Xw = place(np.asarray(c["V"], float)[new])
    # what the head did to its skin after placing it (pushes, the drop onto the field), carried onto the sock from
    # the skin it hangs from: left as placed, a corner push left the sock standing out through the lips' corners
    own = np.flatnonzero(ok)
    near = own[np.linalg.norm(np.asarray(c["V"], float)[gnm[own]][:, None] - np.asarray(c["V"], float)[new][None], axis=2)
               .argmin(0)] if len(own) * len(new) < 4e7 and retopo.SOCK_CARRY else None
    if retopo.SOCK_FALLOFF > 0:
        Xw = _sock_falloff(V, Xw, where[q], len(V), gnm, place, np.asarray(c["V"], float), int(retopo.SOCK_FALLOFF))
        near = None
    if near is not None:
        Xw = Xw + (V[near] - place(np.asarray(c["V"], float)[gnm[near]]))
    # and tucked in behind the lips: GNM's sock is as wide as ITS mouth, and a narrowed, pushed or fitted face
    # (Garrett's) left the sock's sides standing out through the lips' corners. Past the loop it narrows toward the
    # mouth's middle and sinks back, by how far in it is
    loop = np.unique(where[q][~sock[q]])
    if len(loop) and (retopo.SOCK_FALLOFF <= 0 or retopo.SOCK_FALLOFF_NARROW > 0):
        from scipy.spatial import cKDTree as _T
        d = _T(V[loop]).query(Xw)[0]
        t = np.clip(d / retopo.SOCK_TUCK, 0, 1)[:, None] * (retopo.SOCK_FALLOFF_NARROW if retopo.SOCK_FALLOFF > 0 else 1)
        mid = V[loop].mean(0)
        fwd = np.asarray(h["forward"], float)
        Xw = mid + (Xw - mid) * np.c_[1 - retopo.SOCK_NARROW * t, np.ones_like(t), np.ones_like(t)] - fwd * (retopo.SOCK_SINK * t)
    V = np.r_[V, Xw]
    L = np.r_[L, where[q].ravel()]
    S = np.r_[S, np.full(len(q), 4)]
    gnm = np.r_[gnm, new]
    log.append(f"mouth: GNM's mouth sock added to the quads ({len(new)} vertices, {len(q)} faces)")
    return V, L, S, gnm


def _sock_falloff(V, Xw, Wq, n0, gnm, place, CV, rings):
    """The sock's placed vertices Xw (indices n0.. in the quads Wq) moved by the lips' loop's offset from GNM's rest
    (V[loop] - place(GNM[loop]): the head's pushes, the drop onto the field, gnmloops), extended into the sock as a
    harmonic (umbrella-Laplace) field held at the loop and at 0 from `rings` rings in, then eased by a smoothstep of
    the ring: no nearest-vertex carry (it sheared the first rings: rest roughness 3.4 mm at ring 1 vs GNM's 0.85)."""
    nn = len(Xw)
    loop = np.unique(Wq[Wq < n0])
    ok = gnm[loop] >= 0
    loop = loop[ok]
    D0 = V[loop] - place(CV[gnm[loop]])
    # graph over loop + sock vertices: local ids, loop first
    ids = np.r_[loop, n0 + np.arange(nn)]
    lid = {v: i for i, v in enumerate(ids)}
    E = []
    for k in range(Wq.shape[1]):
        a, b = Wq[:, k], Wq[:, (k + 1) % Wq.shape[1]]
        E += [(lid[x], lid[y]) for x, y in zip(a, b) if x in lid and y in lid]
    E = np.unique(np.sort(np.array(E), 1), axis=0)
    m = len(ids)
    nb = [[] for _ in range(m)]
    for x, y in E:
        nb[x].append(y)
        nb[y].append(x)
    ring = np.full(m, -1)
    ring[:len(loop)] = 0
    fr = list(range(len(loop)))
    r = 0
    while fr:
        r += 1
        nx = [y for x in fr for y in nb[x] if ring[y] < 0]
        nx = list(set(nx))
        ring[nx] = r
        fr = nx
    ring[ring < 0] = 10 ** 6
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve
    fixed = (ring == 0) | (ring >= rings)
    val = np.zeros((m, 3))
    val[:len(loop)] = D0
    A = coo_matrix((np.ones(2 * len(E)), (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), (m, m)).tocsr()
    deg = np.asarray(A.sum(1)).ravel()
    from scipy.sparse import diags
    Lp = (diags(deg) - A).tocsr()
    fr_ = np.flatnonzero(~fixed)
    fx = np.flatnonzero(fixed)
    if len(fr_):
        rhs = -(Lp[fr_][:, fx] @ val[fx])
        sol = spsolve(Lp[fr_][:, fr_].tocsc(), rhs)
        val[fr_] = np.asarray(sol).reshape(-1, 3)
    t = np.clip(ring / float(rings), 0, 1)
    w = 1 - t * t * (3 - 2 * t)
    # the harmonic field already reaches 0 at `rings`; the ease flattens its slope at the far end
    off = val * (w[:, None] if retopo.SOCK_FALLOFF_EASE else 1.0)
    return Xw + off[len(loop):]


def wrap(spec: dict, template: str = "male_stylized", log: list | None = None) -> dict:
    """The model's body as the template's quads: {"verts", "loops", "sizes", "origin" (0 template, 1/2 generated),
    "log"}. The spec needs the humanoid joints (see is_humanoid); a face kit, hand kit and ear bones are used when
    present."""
    log = [] if log is None else log
    if spec.get("base") and ((spec.get("parts") or {}).get("body") or {}).get("topology") != "template":
        r = base_quads(spec, log)
        if r is not None:
            return r
    tpl = load_template(template)
    s = expand_mirror(spec)
    prims = [p for p in compile_prims(spec) if p.part == "body"]
    lo = np.min([p.lo for p in prims], 0)
    hi = np.max([p.hi for p in prims], 0)
    voxel = float((hi - lo).max()) / 200
    P = tpl["P"]
    W, segs, dom, apply, Jm = _skeleton_warp(P, tpl["J"], s, prims)
    cuts = _plan_cuts(W, tpl, s, prims)
    base = bool(spec.get("base"))
    if base:  # a base body has a real head with ears (they fit by projection: cut and capped for want of ear bones,
        # they were lost) and its own finger joints under the template's names: digits are tubes along those
        # (projected, the template's coarse fingers jumped between the base's close-set fingers)
        for k, c in cuts.items():
            if c["kind"] == "digit":
                c["model"], c["carry"] = k.split(".")[0], True
        cuts = {k: c for k, c in cuts.items() if c["kind"] == "eye" or "chain" in c
                or (c["kind"] == "digit" and f"{c['model']}_0.{c['side']}" in s["joints"])}
    if "face" in (spec.get("kits") or {}) or any(k.startswith("face_") for k in s["blobs"]) or base:
        extra = [(W[c["loop"][i]], c["target"][i]) for c in cuts.values() if "target" in c
                 for i in range(0, len(c["loop"]), max(1, len(c["loop"]) // 6))]
        face = tpl["face"]
        W = _face_warp(W, apply, face, s, log, extra, retopo.BASE_FACE if base else None)
    E0 = edges(tpl["L"], tpl["S"])
    if not any(n.startswith("foot_t") for n in s["joints"]):  # no toes: smooth the template's into the foot
        toe = np.zeros(len(P), bool)
        for side in "LR":
            a, t = tpl["J"][f"ankle.{side}"], tpl["J"][f"toe.{side}"]
            dirn = t - a
            dirn[2] = 0
            dirn /= np.linalg.norm(dirn)
            toe |= ((P - t) @ dirn > -0.02) & (P[:, 2] < 0.09) & (np.sign(P[:, 0]) == np.sign(t[0]))
        W = _smooth_away(W, E0, toe)
        log.append(f"toes smoothed away ({toe.sum()} vertices)")
    keep0 = np.zeros(len(P), bool)  # the mouth and nostril cavities follow their neighbours: projected they poke
    keep0[tpl["face"].get("cavities", [])] = True  # through the lips (the old rule, "inside the model near the head",
    # also caught the goblin's cheeks and jaw: they sat 15-25 mm inside the surface)
    faces, _, _ = topology(tpl["L"], tpl["S"])
    cuts = _patches(W, cuts, s, prims, voxel, log)
    V, fl, origin, remap = _stitch(W, faces, cuts)
    L = np.array([v for f in fl for v in f])
    S = np.array([len(f) for f in fl])
    # per new vertex: its template vertex's dominant segment and keep flag (generated ones: none)
    n_t = len(V)
    dom2 = np.full(n_t, -1)
    keep = np.zeros(n_t, bool)
    ok = remap >= 0
    dom2[remap[ok]] = dom[ok]
    keep[remap[ok]] = keep0[ok]
    fixed = origin == 1
    keep &= ~fixed
    # regions: a vertex first projects onto the primitives of its segment and the neighbouring ones (a hand never
    # lands on a thigh)
    cen = np.array([0.5 * (p.lo + p.hi) for p in prims])
    owner = np.stack([_seg_dist(cen, Jm[a], Jm[b]) for a, b in segs], 1).argmin(1)
    regions = [[p for p, o in zip(prims, owner) if o in [i for i, (c, d) in enumerate(segs) if {c, d} & {a, b}]]
               for a, b in segs]
    if base:  # one primitive is the whole body (owned by the torso): every segment projects onto all of it (the
        # hands had nothing to land on and collapsed into strings; the mouth landed on a small blob behind the lips)
        regions = [prims for _ in segs]
    V, missed = _fit(V, L, S, prims, voxel, regions, dom2, keep, fixed)
    V = _untangle(V, L, S, prims, voxel, fixed | keep, log=log)
    fv = np.abs(sdf.field_at(prims, V, margin=0.05))[~keep] * 1000
    log.append(f"wrapped: {len(V)} verts, {len(S)} faces ({(S == 4).mean():.0%} quads); {missed} missed the surface "
               f"along their normal; |field| mean {fv.mean():.2f} p95 {np.percentile(fv, 95):.2f} max {fv.max():.1f} mm")
    if base and (spec["base"].get("head") or {}).get("source", "gnm") == "gnm" and spec["base"].get("head"):
        V, L, S = graft_head(V, L, S, spec, prims, log)
        origin = np.zeros(len(V), int)
    return {"verts": V, "loops": L, "sizes": S, "origin": origin, "log": log,
            "patches": {k: c[2][0] for k, c in cuts.items() if c[2] is not None}}
