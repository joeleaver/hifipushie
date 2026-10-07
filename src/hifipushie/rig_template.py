"""Skin weights the way riggers get them: transferred from a hand-weighted template of the same topology.

A base body made from MakeHuman keeps MakeHuman's vertices (warped onto the spec's joints), and MakeHuman ships
hand-made weights for its default skeleton (CC0, rigs/default_weights.mhw). So each base vertex takes its template
vertex's own weights, with MakeHuman's 139 weighted bones folded onto the Mixamo joints: no distances, no neighbouring
fingers bleeding into each other. Two things don't come by topology: the grafted neck's and head's vertices (new
geometry: they copy the nearest template-weighted vertex and the rigid head rule takes over), and the other meshes
(the export's low poly, clothes, hair shells), which read the base's weights at the closest point of its SURFACE
whose normal agrees with theirs (`from_surface`): the nearest VERTEX of a finger's side is as often the next finger's.

Distance weights (`rig.rig_weights`) stay for everything without such a template: kit characters, the stylised
template, creatures."""
from __future__ import annotations

import numpy as np

PREFIX = "mixamorig:"
DIGIT = {1: "Thumb", 2: "Index", 3: "Middle", 4: "Ring", 5: "Pinky"}
# MakeHuman default-skeleton bones -> Mixamo joints, by name; the spine and neck go by where they lie (`_central`).
# Twist splits (upperarm01/02...) fold into their segment's joint: our own twist bones share it out again by station.
SIDE = {"clavicle": "Shoulder", "shoulder01": "Shoulder", "upperarm01": "Arm", "upperarm02": "Arm",
        "lowerarm01": "ForeArm", "lowerarm02": "ForeArm", "wrist": "Hand", "upperleg01": "UpLeg",
        "upperleg02": "UpLeg", "lowerleg01": "Leg", "lowerleg02": "Leg", "foot": "Foot", "pelvis": None,
        "breast": None}
CENTRAL = ("root", "spine05", "spine04", "spine03", "spine02", "spine01", "neck01", "neck02", "neck03", "head")


def _mixamo(mh: str) -> str | None:
    """The Mixamo joint a MakeHuman bone's weights go to (None: decided by `_central`; face bones: Head)."""
    side = {"L": "Left", "R": "Right"}.get(mh[-1]) if mh[-2:] in (".L", ".R") else None
    stem = mh[:-2] if side else mh
    if side:
        if stem in ("pelvis",):
            return "Hips"
        if stem == "breast":
            return "Spine2"
        if stem in SIDE:
            return side + SIDE[stem]
        if stem.startswith("metacarpal"):
            return side + "Hand"
        if stem.startswith("finger"):
            d, k = stem[len("finger"):].split("-")
            return f"{side}Hand{DIGIT[int(d)]}{int(k)}"
        if stem.startswith("toe"):
            return side + "ToeBase"
    if stem in CENTRAL and stem != "head":
        return None
    return "Head"  # head, jaw, eyes, tongue and the face's muscle bones: one rigid head (face shapes move the face)


def _central(tpl: dict, names: list[str]) -> dict:
    """{central MakeHuman bone: {Mixamo joint: share}} by where the bone lies along pelvis -> chest -> neck -> head
    in the template's own rest: each of our spine joints takes the part of a MakeHuman spine bone that overlaps its
    own stretch (our Hips / Spine / Spine1 split pelvis -> chest in thirds, Spine2 runs to the Neck joint at shoulder
    height: `rig.humanoid`)."""
    J = tpl["J"]
    pelvis, chest, neck, head = (np.asarray(J[k], float) for k in ("pelvis", "chest", "neck", "head"))
    sh_z = 0.5 * (J["shoulder.L"][2] + J["shoulder.R"][2])
    t = float(np.clip((sh_z - chest[2]) / max(neck[2] - chest[2], 1e-6), 0.2, 0.8))
    hint = tpl.get("rig") or {}

    def at(name, default):  # as rig.humanoid places Neck and Head
        if name in hint:
            a, b, f = hint[name]
            return np.asarray(J[a], float) + float(f) * (np.asarray(J[b], float) - np.asarray(J[a], float))
        return default
    nk, hd = at("Neck", chest + t * (neck - chest)), at("Head", neck)
    pts = [pelvis, pelvis + (chest - pelvis) / 3, pelvis + 2 * (chest - pelvis) / 3, chest, nk, hd,
           hd + 4 * (head - neck)]
    cum = np.r_[0, np.cumsum([np.linalg.norm(b - a) for a, b in zip(pts, pts[1:])])]
    stretch = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"]

    def along(p):  # arc length of the polyline's nearest point
        best, u = np.inf, 0.0
        for k, (a, b) in enumerate(zip(pts, pts[1:])):
            ab = b - a
            s = float(np.clip((p - a) @ ab / (ab @ ab), 0, 1))
            d = float(np.linalg.norm(a + s * ab - p))
            if d < best:
                best, u = d, cum[k] + s * (cum[k + 1] - cum[k])
        return u
    out = {}
    for b in CENTRAL[:-1]:
        if b not in tpl["bones"]:
            continue
        u0, u1 = sorted(along(np.asarray(x, float)) for x in tpl["bones"][b])
        if b == "root" or u1 - u0 < 1e-6:
            k = int(np.clip(np.searchsorted(cum, 0.5 * (u0 + u1), side="right") - 1, 0, len(stretch) - 1))
            out[b] = {"Hips" if b == "root" else stretch[k]: 1.0}
            continue
        sh = {stretch[k]: max(0.0, min(u1, cum[k + 1]) - max(u0, cum[k])) / (u1 - u0) for k in range(len(stretch))}
        tot = sum(sh.values())
        out[b] = {k: v / tot for k, v in sh.items() if v > 0.02 * tot}
    return {b: {PREFIX + k: v for k, v in sh.items() if PREFIX + k in names} for b, sh in out.items()}


def weights_note(spec: dict) -> str | None:
    """A WARNING when this spec would take MakeHuman's hand-made weights but the pack on this machine lacks them."""
    b = spec.get("base") or {}
    if ((b.get("body") or {}).get("source") != "makehuman"
            or (spec.get("rig") or {}).get("weights", "template") == "distance"):
        return None
    from . import makehuman
    return makehuman.weights_note()


def template_weights(spec: dict, rb: list[dict], surf: dict) -> np.ndarray | None:
    """Dense weights (base quad vertices x rig bones) from the base's template, or None when it has none (a
    template other than MakeHuman, the weights file not in the pack, spec["rig"]["weights"] = "distance", or a
    rig that isn't the Mixamo humanoid). Twist bones get nothing here (`rig._spread_twist` shares them after)."""
    from scipy.spatial import cKDTree
    names = [b["name"] for b in rb]
    if (spec.get("rig") or {}).get("weights", "template") == "distance" or PREFIX + "Hips" not in names:
        return None
    if surf.get("template") == "human" and surf.get("src") is not None:
        return _one_mesh(spec, rb, surf, names)
    if surf.get("template") != "makehuman" or surf.get("src") is None:
        return None
    from . import base as basemod
    from . import makehuman
    mw = makehuman.weights()
    if mw is None:
        return None
    tpl = basemod.source(spec["base"])
    full = -np.ones(int(max(tpl["vid"].max(), max(int(i.max()) for i, _ in mw.values()))) + 1, int)
    full[tpl["vid"]] = np.arange(len(tpl["vid"]))  # base.obj's numbering -> the body's own vertices
    central = _central(tpl, names)
    D = np.zeros((len(tpl["vid"]), len(rb)))
    lost = []
    for mh, (idx, w) in mw.items():
        to = central.get(mh) if _mixamo(mh) is None else {PREFIX + _mixamo(mh): 1.0}
        k = full[idx]
        ok = k >= 0
        if not ok.any():
            continue
        for nm, share in (to or {}).items():
            if nm not in names:  # a hand without that finger, a rig without toes: its parent keeps the skin
                lost.append(nm)
                nm = _fallback(nm, names)
            np.add.at(D[:, names.index(nm)], k[ok], share * w[ok])
    tot = D.sum(1)
    src = np.asarray(surf["src"])
    Wq = np.asarray(surf["quads"][0], float)
    have = (src >= 0) & (tot[np.maximum(src, 0)] > 1e-6)
    out = np.zeros((len(src), len(rb)))
    out[have] = D[src[have]] / tot[src[have], None]
    if (~have).any():
        # the grafted neck and head: the nearest weighted vertex's (the neck loop's) next to it, handing over to the
        # Neck joint alone within GRAFT_REACH (the rigid head rule makes the head Head after). Copied all the way
        # up, the loop's shoulder and upper-arm shares (0.38 / 0.19 on the golfer) held the whole neck and the
        # throat's falloff band: an arm raised 60 deg pulled the neck's side and the collar round it 25-36 mm.
        d, k = cKDTree(Wq[have]).query(Wq[~have])
        out[~have] = out[np.flatnonzero(have)[k]]
        if PREFIX + "Neck" in names:
            t = np.clip(d / GRAFT_REACH, 0.0, 1.0)
            t = (t * t * (3 - 2 * t))[:, None]
            neck = np.zeros(len(rb))
            neck[names.index(PREFIX + "Neck")] = 1.0
            out[~have] = (1 - t) * out[~have] + t * neck
    return out


def _one_mesh(spec: dict, rb: list[dict], surf: dict, names: list[str]) -> np.ndarray:
    """One human mesh (onemesh.py): every vertex has hand-made weights of its own in the asset (MakeHuman's by index
    on the body, through the head's binding above the stitch), folded onto the rig's joints as below. Above the
    stitch the arm's side of the weights (clavicle, shoulder: MakeHuman runs them a little way up the neck's side)
    is handed to the Neck joint within GRAFT_REACH, as a grafted neck's was: an arm must not pull the neck."""
    from scipy.spatial import cKDTree

    from . import base as basemod
    from . import onemesh
    tpl = basemod.source(spec["base"])
    bones, idx, w = onemesh.weights(tpl)
    central = _central(tpl, names)
    D = np.zeros((len(idx), len(rb)))
    rows = np.arange(len(idx))
    for k, mh in enumerate(bones):
        to = central.get(mh) if _mixamo(mh) is None else {PREFIX + _mixamo(mh): 1.0}
        wk = np.where(idx == k, w, 0.0).sum(1)
        if not to or not wk.any():
            continue
        for nm, share in to.items():
            if nm not in names:
                nm = _fallback(nm, names)
            D[rows, names.index(nm)] += share * wk
    src = np.asarray(surf["src"])
    out = D[src] / np.maximum(D[src].sum(1, keepdims=True), 1e-12)
    if PREFIX + "Neck" in names:
        Wq = np.asarray(surf["quads"][0], float)
        up = src >= tpl["n_mh"]  # the bridge and the head
        side = np.array([any(s in n for s in ("Shoulder", "Arm", "ForeArm", "Hand")) for n in names])
        if up.any() and side.any():
            d, _ = cKDTree(Wq[~up]).query(Wq[up])
            t = np.clip(d / GRAFT_REACH, 0.0, 1.0)
            t = t * t * (3 - 2 * t)
            moved = out[np.ix_(np.flatnonzero(up), np.flatnonzero(side))] * t[:, None]
            rws = np.flatnonzero(up)
            out[np.ix_(rws, np.flatnonzero(side))] -= moved
            out[rws, names.index(PREFIX + "Neck")] += moved.sum(1)
    return out


GRAFT_REACH = 0.04  # m from the template's own vertices over which a grafted neck's weights become the Neck joint's


def _fallback(name: str, names: list[str]) -> str:
    stem = name[len(PREFIX):]
    for side in ("Left", "Right"):
        if stem.startswith(side + "Hand") and PREFIX + side + "Hand" in names:
            return PREFIX + side + "Hand"
        if stem.startswith(side + "Toe") and PREFIX + side + "Foot" in names:
            return PREFIX + side + "Foot"
    return PREFIX + "Hips"


def top_k(D: np.ndarray, k: int = 4):
    """(J, W) of the k largest weights per row, normalised."""
    J = np.argsort(-D, axis=1, kind="stable")[:, :k]
    W = np.take_along_axis(D, J, 1)
    W[W < 0.01 * W[:, :1]] = 0.0
    W /= np.maximum(W.sum(1, keepdims=True), 1e-12)
    J[W <= 0] = 0
    return J, W


def _closest_on_triangles(P: np.ndarray, A: np.ndarray, B: np.ndarray, C: np.ndarray):
    """Closest points of triangles (A, B, C) to points P (all (n, 3)): (barycentric (n, 3), distance (n,)).
    Ericson's regions, vectorised."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = P - B
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = P - C
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    den = np.maximum(va + vb + vc, 1e-30)
    v, w = vb / den, vc / den
    bary = np.stack([1 - v - w, v, w], 1)
    def put(mask, vals):
        bary[mask] = vals[mask]
    z, o = np.zeros(len(P)), np.ones(len(P))
    t = np.clip((d4 - d3) / np.maximum((d4 - d3) + (d5 - d6), 1e-30), 0, 1)
    put((va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0), np.stack([z, 1 - t, t], 1))
    t = np.clip(d2 / np.maximum(d2 - d6, 1e-30), 0, 1)
    put((vb <= 0) & (d2 >= 0) & (d6 <= 0), np.stack([1 - t, z, t], 1))
    t = np.clip(d1 / np.maximum(d1 - d3, 1e-30), 0, 1)
    put((vc <= 0) & (d1 >= 0) & (d3 <= 0), np.stack([1 - t, t, z], 1))
    put((d6 >= 0) & (d5 <= d6), np.stack([z, z, o], 1))
    put((d3 >= 0) & (d4 <= d3), np.stack([z, o, z], 1))
    put((d1 <= 0) & (d2 <= 0), np.stack([o, z, z], 1))
    Q = bary[:, :1] * A + bary[:, 1:2] * B + bary[:, 2:] * C
    return bary, np.linalg.norm(Q - P, axis=1)


AGAINST = 0.03  # m: what a candidate point pays for facing away from the vertex (another finger's side, 1-3 mm off)


def from_surface(Vq: np.ndarray, Tq: np.ndarray, Dq: np.ndarray, V: np.ndarray, N: np.ndarray | None, k: int = 16,
                 two_sided: bool = False):
    """Dense weights for points V (normals N, or None) read off a weighted surface (vertices Vq, triangles Tq, dense
    weights Dq): at each point's closest point of the surface, among the k triangles with the nearest centres,
    preferring one that faces the way the point does. Barycentric, so weights vary smoothly over the surface.
    two_sided (cloth): a point may also face the skin squarely. A sheet of cloth has an inside: a collar's under
    face looks AT the shoulder it lies on, and "facing the same way" sent it to skin somewhere else, so the
    collar's two faces read two places."""
    from scipy.spatial import cKDTree
    V = np.asarray(V, np.float64)
    A, B, C = Vq[Tq[:, 0]], Vq[Tq[:, 1]], Vq[Tq[:, 2]]
    fn = np.cross(B - A, C - A)
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-30)
    k = min(k, len(Tq))
    _, cand = cKDTree((A + B + C) / 3).query(V, k=k)
    cand = cand.reshape(len(V), k)
    out = np.zeros((len(V), Dq.shape[1]))
    step = max(1, 2_000_000 // k)
    for s in range(0, len(V), step):
        c = cand[s:s + step]
        n = len(c)
        Pp = np.repeat(V[s:s + step], k, 0)
        t = c.ravel()
        bary, d = _closest_on_triangles(Pp, A[t], B[t], C[t])
        if N is not None:
            facing = (fn[t] * np.repeat(np.asarray(N, float)[s:s + step], k, 0)).sum(1)
            if two_sided:
                facing = np.abs(facing)
            d = d + AGAINST * np.clip(0.3 - facing, 0, 1)
        best = d.reshape(n, k).argmin(1)
        pick = np.arange(n) * k + best
        tri = Tq[t[pick]]
        bw = bary[pick]
        for j in range(3):
            out[s:s + n] += bw[:, j:j + 1] * Dq[tri[:, j]]
    return out


SOFT = 0.6        # a worn vertex reads the skin within this x its own distance from the skin (the kernel's width)
SOFT_MIN = 0.008  # m: and never narrower than this
SOFT_MAX = 0.08   # m: nor wider
SOFT_FACING = (-0.1, 0.5)  # skin facing the way the vertex does counts fully (dot >= 0.5), across it (<= -0.1) not


def around_surface(Vq: np.ndarray, Tq: np.ndarray, Dq: np.ndarray, V: np.ndarray, N: np.ndarray | None,
                   soft: float = SOFT):
    """Dense weights for points V (normals N) read off a weighted surface as an AVERAGE of the skin round each
    point's nearest skin: every triangle counts by its area x a Gaussian of how much farther it is than the nearest
    one, as wide as `soft` x that nearest distance (SOFT_MIN..SOFT_MAX) x how far it faces the way the point does.
    A continuous function of where the point is: cloth close on the skin reads the skin under it (a sleeve, a
    trouser leg), cloth hanging away from it reads everything about as near (a jacket's hem between the thighs:
    both thighs; the crotch seam: both thighs and the pelvis). The closest point alone (`from_surface`) jumps
    wherever two bits of skin are equally near: s0urc3's seated Garrett, whose jacket hem and trouser front
    alternated between thigh and pelvis from vertex to vertex and folded into a sawtooth at 90 deg of hip.
    A point whose normal faces the skin (a shell's inner face) is read with the normal turned."""
    from scipy.spatial import cKDTree
    V = np.asarray(V, np.float64)
    A, B, C = Vq[Tq[:, 0]], Vq[Tq[:, 1]], Vq[Tq[:, 2]]
    fn = np.cross(B - A, C - A)
    area = 0.5 * np.linalg.norm(fn, axis=1)
    fn /= np.maximum(2 * area[:, None], 1e-30)
    cen = (A + B + C) / 3
    Dt = (Dq[Tq[:, 0]] + Dq[Tq[:, 1]] + Dq[Tq[:, 2]]) / 3
    tree = cKDTree(cen)
    d0, _ = tree.query(V)
    sig = np.clip(soft * d0, SOFT_MIN, SOFT_MAX)
    near = tree.query_ball_point(V, d0 + 3.0 * sig)
    out = np.zeros((len(V), Dq.shape[1]))
    lo, hi = SOFT_FACING
    for i, idx in enumerate(near):
        idx = np.asarray(idx, int)
        ex = np.linalg.norm(cen[idx] - V[i], axis=1) - d0[i]
        w = area[idx] * np.exp(-0.5 * (ex / sig[i]) ** 2)
        if N is not None:
            dot = fn[idx] @ N[i]
            wp = w * np.clip((dot - lo) / (hi - lo), 0.0, 1.0)
            wm = w * np.clip((-dot - lo) / (hi - lo), 0.0, 1.0)
            w = wp if wp.sum() >= wm.sum() else wm
            if w.sum() < 1e-12:  # nothing faces either way: by distance alone
                w = area[idx] * np.exp(-0.5 * (ex / sig[i]) ** 2)
        out[i] = w @ Dt[idx] / max(w.sum(), 1e-30)
    return out
