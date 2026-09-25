"""An armature and skin weights from the spec's skeleton, for export_asset(rig=True).

Every additive bone of the (mirrored, kit-expanded) spec becomes an armature bone. The joint graph is walked
breadth first from a root joint ("pelvis", "hips" or "root" if there is one, else the graph's centre), which
orients each bone parent -> child: its head is the joint it was reached from (the pivot it turns about), its parent
the bone that reached that joint. Pieces of the skeleton not joined to the rest (a buckle, a tail made separately)
hang from the bone nearest to them.

Skin weights come from the bones' own round cones: at each vertex, every bone's exact distance (`sdf.field_at` of
that one primitive: thickness counts, so a thick thigh claims the flesh a thin bone axis would lose), weighted
exp(-(d - d_nearest) / falloff) with the falloff half the bone's radius, among the nearest bone's family (two steps of parents,
children, siblings), smoothed over the mesh, the four strongest kept and normalised. Blobs (a belly, a head) go with the bones they sit on. Parts (clothes, eyes) are skinned to the same
bones.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from . import sdf
from .spec import compile_prims, expand_mirror, resolve_point

ROOTS = ("pelvis", "hips", "root", "hip")
FALLOFF = 0.5  # weight falls by e over this fraction of a bone's radius past the nearest bone
SMOOTH = 10  # rounds of averaging weights with neighbouring vertices


def skeleton(spec: dict) -> list[dict]:
    """[{"name", "head", "tail" (world, Blender axes), "parent" (index, -1 for the root's bones), "prim" (its
    cone), "prims" (its cone and the blobs on it)}] in an order where every parent comes before its children."""
    s = expand_mirror(spec)
    prims = {p.name: p for p in compile_prims(spec) if p.op == "add"}
    bones = {n: b for n, b in s["bones"].items() if b.get("op", "add") == "add" and n in prims}
    if not bones:
        return []
    pos = {j: resolve_point(s, j) for b in bones.values() for j in (b["a"], b["b"])}
    adj: dict = {}
    for n, b in bones.items():
        adj.setdefault(b["a"], []).append((n, b["b"]))
        adj.setdefault(b["b"], []).append((n, b["a"]))
    root = next((r for r in ROOTS if r in adj), None) or _centre(adj)
    out, index, reached = [], {}, {root: -1}  # joint -> the bone that reached it

    def walk(start):
        q = deque([start])
        while q:
            j = q.popleft()
            for n, other in adj[j]:
                if n in index:
                    continue
                index[n] = len(out)
                out.append({"name": n, "head": pos[j], "tail": pos[other], "parent": reached[j], "prim": prims[n]})
                if other not in reached:
                    reached[other] = index[n]
                    q.append(other)
    walk(root)
    heads, tails = None, None
    while len(index) < len(bones):  # a piece not joined to the rest: from its joint nearest the skeleton so far
        rest = [j for j in adj if j not in reached]
        heads = np.array([b["head"] for b in out])
        tails = np.array([b["tail"] for b in out])
        d = [(_seg_dist(pos[j], heads, tails), j) for j in rest]
        (dist, near), j = min(((float(v.min()), int(v.argmin())), j) for v, j in d)
        reached[j] = near
        walk(j)
    # blobs go with the bone they sit on: at a joint, the bone that reached it (the root's first bone for the
    # root); on a bone, that bone; anywhere else, the bone nearest their centre
    heads = np.array([b["head"] for b in out])
    tails = np.array([b["tail"] for b in out])
    for b in out:
        b["prims"] = [b["prim"]]
    for n, bl in s["blobs"].items():
        pr = prims.get(n)
        if pr is None or pr.kind not in ("ellipsoid", "box", "cylinder", "lids", "csg"):
            continue
        at = bl.get("at")
        if isinstance(at, dict) and at.get("bone") in index:
            i = index[at["bone"]]
        elif isinstance(at, str) and at in reached:
            i = max(reached[at], 0)
        else:
            c = resolve_point(s, at if at is not None else [0, 0, 0]) + np.array(bl.get("offset", [0, 0, 0]), float)
            i = int(np.argmin(_seg_dist(c, heads, tails)))
        out[i]["prims"].append(pr)
    return out


def _centre(adj: dict) -> str:
    """The joint whose farthest joint (in bones) is nearest: the middle of the skeleton."""
    best, key = None, None
    for j in adj:
        seen, q = {j: 0}, deque([j])
        while q:
            x = q.popleft()
            for _, y in adj[x]:
                if y not in seen:
                    seen[y] = seen[x] + 1
                    q.append(y)
        k = (max(seen.values()), -len(seen))
        if key is None or k < key:
            best, key = j, k
    return best


def _seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = np.clip(((p - a) * ab).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12), 0, 1)
    return np.linalg.norm(a + t[..., None] * ab - p, axis=-1)


def weights(bones: list[dict], verts: np.ndarray, faces: np.ndarray | None = None, k: int = 4,
            falloff: float = FALLOFF, smooth: int = SMOOTH) -> tuple[np.ndarray, np.ndarray]:
    """(bone indices (n, k), weights (n, k), rows summing to 1) for vertices, from each bone's own cone and blobs,
    then averaged with the vertices around (`smooth` rounds over the faces' edges) so that where one bone's flesh
    meets another's the weights blend instead of stepping (a crease down the chest when an arm lifts)."""
    V = np.asarray(verts, np.float64)
    D = np.stack([np.min([sdf.field_at([p], V, clip=False) for p in b["prims"]], 0) for b in bones], 1)
    fall = np.array([max(falloff * (b["falloff_r"] if "falloff_r" in b else
                                    0.5 * (b["prim"].params["ra"] + b["prim"].params["rb"])), 1e-3) for b in bones])
    d0 = D.min(1, keepdims=True)
    W = np.exp(-(D - d0) / fall[None])
    # a vertex blends only between its nearest bone and that bone's family (two steps of parents, children and
    # siblings): unrelated
    # bones that happen to be near (a tusk by the jaw, the other thigh) would crowd the four kept and step
    n = len(bones)
    fam = np.eye(n, dtype=bool)
    par = np.array([b["parent"] for b in bones])
    for i, p in enumerate(par):
        if p >= 0:
            fam[i, p] = fam[p, i] = True
    for p in set(par.tolist()):
        kids = np.flatnonzero(par == p)
        fam[np.ix_(kids, kids)] = True
    fam = (fam.astype(np.int32) @ fam.astype(np.int32)) > 0  # two steps: a fat upper arm's grandparent spine too
    W *= fam[D.argmin(1)]
    W /= W.sum(1, keepdims=True)
    W = _smooth(W, faces, smooth)
    k = min(k, len(bones))
    J = np.argsort(-W, axis=1)[:, :k]
    Wk = np.take_along_axis(W, J, 1)
    Wk[Wk < 0.01 * Wk[:, :1]] = 0.0
    Wk /= Wk.sum(1, keepdims=True)
    return J.astype(np.int64), _settle(J, Wk, faces, smooth)


def _settle(J: np.ndarray, W: np.ndarray, faces, rounds: int) -> np.ndarray:
    """Smooth weights once each vertex's bones are chosen, each vertex keeping only its own: where a bone
    drops out of a vertex's four its weight fades to zero on the way there instead of stepping (a hairline crack
    when posed)."""
    if faces is None or not rounds:
        return W
    F = np.asarray(faces, np.int64)
    a = np.r_[F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]]
    b = np.r_[F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]]
    deg = np.maximum(np.bincount(a, minlength=len(W)), 1).astype(np.float64)[:, None]
    for _ in range(rounds):
        # each neighbour's weight for each of this vertex's bones (0 if the neighbour doesn't have it)
        match = (J[b][:, None, :] == J[a][:, :, None])  # (edges, my slot, its slot)
        got = (match * W[b][:, None, :]).sum(2)
        acc = np.zeros_like(W)
        np.add.at(acc, a, got)
        W = 0.5 * W + 0.5 * acc / deg
        W /= np.maximum(W.sum(1, keepdims=True), 1e-12)
    return W


def _smooth(W: np.ndarray, faces, rounds: int) -> np.ndarray:
    """Each vertex's weights averaged half-and-half with its neighbours' (over the faces' edges), `rounds` times."""
    if faces is None or not rounds:
        return W
    F = np.asarray(faces, np.int64)
    a = np.r_[F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]]
    b = np.r_[F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]]
    deg = np.maximum(np.bincount(a, minlength=len(W)), 1).astype(np.float64)[:, None]
    for _ in range(rounds):
        acc = np.zeros_like(W)
        np.add.at(acc, a, W[b])
        W = 0.5 * W + 0.5 * acc / deg
    return W


def pose(bones: list[dict], verts: np.ndarray, J: np.ndarray, W: np.ndarray, turns: dict) -> np.ndarray:
    """Linear blend skinning of the rest vertices with some bones turned: {bone: (axis [x, y, z], degrees)} about
    their heads, children following. For checking weights (bend an elbow, look at it)."""
    n = len(bones)
    M = np.tile(np.eye(4), (n, 1, 1))
    for i, b in enumerate(bones):  # parents come first
        L = np.eye(4)
        if b["name"] in turns:
            ax, deg = turns[b["name"]]
            ax = np.asarray(ax, float) / np.linalg.norm(ax)
            t = np.radians(deg)
            K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
            R = np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K
            h = np.asarray(b["head"], float)
            L[:3, :3], L[:3, 3] = R, h - R @ h
        M[i] = (M[b["parent"]] if b["parent"] >= 0 else np.eye(4)) @ L
    V4 = np.c_[verts, np.ones(len(verts))]
    out = np.zeros((len(verts), 3))
    for c in range(J.shape[1]):
        out += W[:, c:c + 1] * np.einsum("nij,nj->ni", M[J[:, c]], V4)[:, :3]
    return out


# ---- the export rig: a clean, retargetable skeleton over the modelling one ----------------------------------------
# The spec's bones are for modelling (a tusk, lip chains, a shorts leg are bones); the exported armature is a
# separate, standard one fitted to the joints: spec["rig"] = {"type": "humanoid" (default when the usual joints
# exist) | "chains", "joints": {rig joint: spec joint or [x, y, z]} (overrides), "chains": {...} (type chains)}.
# Humanoid: Mixamo's names and hierarchy (mixamorig:Hips ... LeftHandIndex4), which Mixamo animations, Unity's
# Humanoid avatar and Unreal's IK retargeter map without a hand-made mapping. Chains: a root and named chains of
# joints (spine, neck, tail, legs), each bone "<chain>_01", "<chain>_02"...
# Skin weights are the modelling skin (`weights`: cones and blobs, family-limited, smoothed) handed on to the rig
# bones lying along each modelling bone (split along it where several do: the one spine bone feeds Spine, Spine1,
# Spine2); a modelling bone with no rig bone along it (a tusk, an ear) goes to the nearest one (Head).

PREFIX = "mixamorig:"
FINGERS = ("Index", "Middle", "Ring", "Pinky")


def _joint(s: dict, j):
    return np.asarray(j, float) if isinstance(j, (list, tuple)) else resolve_point(s, j)


def _surface_along(spec: dict, p: np.ndarray, d: np.ndarray, reach: float) -> np.ndarray:
    """Where a ray from inside the body leaves it (the top of the head, the tip of the toes)."""
    prims = [q for q in compile_prims(spec) if q.part == "body"]
    t = np.linspace(0, reach, 200)
    f = sdf.field_at(prims, p + t[:, None] * d, clip=False)
    out = np.flatnonzero(f > 0)
    return p + (t[out[0]] if len(out) else reach) * d


def humanoid(spec: dict) -> list[dict] | None:
    """The Mixamo skeleton fitted to the spec's joints: [{"name", "head", "parent" (index), "end": bool}] (end
    joints like HeadTop_End carry no weight), or None if the usual joints aren't there."""
    s = expand_mirror(spec)
    J = s["joints"]
    over = (spec.get("rig") or {}).get("joints") or {}
    need = ["pelvis", "chest", "neck", "head"] + [f"{j}.{side}" for j in ("shoulder", "elbow", "wrist", "hip", "knee",
                                                                            "ankle") for side in "LR"]
    if not all(j in J for j in need) and not over:
        return None
    P = {k: _joint(s, v) for k, v in over.items()}

    def at(name, default):
        return P.get(name, default)
    pelvis, chest, neck, head = (_joint(s, j) for j in ("pelvis", "chest", "neck", "head"))
    sh_z = 0.5 * (_joint(s, "shoulder.L")[2] + _joint(s, "shoulder.R")[2])
    t = float(np.clip((sh_z - chest[2]) / max(neck[2] - chest[2], 1e-6), 0.2, 0.8))
    bones = []

    def add(name, pos, parent, end=False, src="placed"):
        bones.append({"name": PREFIX + name, "head": np.asarray(at(name, pos), float), "end": end,
                      "src": "spec rig.joints" if name in P else src,
                      "parent": next(i for i, b in enumerate(bones) if b["name"] == PREFIX + parent) if parent else -1})
    add("Hips", pelvis, None, src="pelvis")
    add("Spine", pelvis + (chest - pelvis) / 3, "Hips")
    add("Spine1", pelvis + 2 * (chest - pelvis) / 3, "Spine")
    add("Spine2", chest, "Spine1", src="chest")
    add("Neck", chest + t * (neck - chest), "Spine2")
    add("Head", neck, "Neck", src="neck")
    up = (head - neck) / max(np.linalg.norm(head - neck), 1e-9)
    add("HeadTop_End", _surface_along(spec, head, up, 2 * np.linalg.norm(head - neck) + 0.5), "Head", True)
    for side, S in (("L", "Left"), ("R", "Right")):
        j = {k: _joint(s, f"{k}.{side}") for k in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")}
        base = bones[[b["name"] for b in bones].index(PREFIX + "Neck")]["head"]
        add(f"{S}Shoulder", base + 0.2 * (j["shoulder"] - base), "Spine2")
        add(f"{S}Arm", j["shoulder"], f"{S}Shoulder", src=f"shoulder.{side}")
        add(f"{S}ForeArm", j["elbow"], f"{S}Arm", src=f"elbow.{side}")
        add(f"{S}Hand", j["wrist"], f"{S}ForeArm", src=f"wrist.{side}")
        thumb = [f"hand_th_{k}.{side}" for k in range(4)]
        if all(x in J for x in thumb):
            for k, x in enumerate(thumb):
                add(f"{S}HandThumb{k + 1}", _joint(s, x), f"{S}Hand" if k == 0 else f"{S}HandThumb{k}", k == 3, x)
        fingers = sorted((f for f in range(1, 6) if all(f"hand_f{f}_{k}.{side}" in J for k in range(4))),
                         key=lambda f: np.linalg.norm(_joint(s, f"hand_f{f}_0.{side}") - _joint(s, thumb[0]))
                         if thumb[0] in J else f)
        names = FINGERS if len(fingers) >= 4 else ("Index", "Middle", "Ring")[:len(fingers) - 1] + ("Pinky",) \
            if len(fingers) > 1 else ("Index",)
        for f, fn in zip(fingers, names):
            for k in range(4):
                add(f"{S}Hand{fn}{k + 1}", _joint(s, f"hand_f{f}_{k}.{side}"),
                    f"{S}Hand" if k == 0 else f"{S}Hand{fn}{k}", k == 3, f"hand_f{f}_{k}.{side}")
        add(f"{S}UpLeg", j["hip"], "Hips", src=f"hip.{side}")
        add(f"{S}Leg", j["knee"], f"{S}UpLeg", src=f"knee.{side}")
        add(f"{S}Foot", j["ankle"], f"{S}Leg", src=f"ankle.{side}")
        toe = _joint(s, f"toe.{side}") if f"toe.{side}" in J else j["ankle"] + np.array([0, -0.1, -0.05])
        add(f"{S}ToeBase", toe, f"{S}Foot", src=f"toe.{side}")
        fwd = toe - j["ankle"]
        fwd[2] = 0
        fwd /= max(np.linalg.norm(fwd), 1e-9)
        add(f"{S}Toe_End", _surface_along(spec, toe, fwd, 0.5), f"{S}ToeBase", True)
    return bones


def chains(spec: dict) -> list[dict]:
    """spec["rig"] = {"type": "chains", "root": joint, "chains": {name: {"from": parent chain (default: the
    root), "joints": [spec joints or [x, y, z], first to last]}}}: a weightless "root" bone on the ground under the
    root joint (root motion), then per chain bones "<name>_01", "<name>_02"... from each joint to the next and a
    "<name>_end" leaf at the last. A chain hangs from its parent chain's bone nearest its first joint (a neck
    starting where the spine ends hangs from the spine's last bone, no duplicate)."""
    s = expand_mirror(spec)
    r = spec["rig"]
    r0 = _joint(s, r["root"])
    bones = [{"name": "root", "head": np.array([r0[0], r0[1], 0.0]), "parent": -1, "end": False,
              "noweight": True, "src": "ground under " + str(r["root"])}]
    idx = {"root": [0]}
    todo = dict(r["chains"])
    while todo:
        done = [n for n, c in todo.items() if c.get("from", "root") in idx]
        if not done:
            raise ValueError(f"rig chains {sorted(todo)} hang from chains that don't exist")
        for n in done:
            c = todo.pop(n)
            pts = [_joint(s, j) for j in c["joints"]]
            if len(pts) < 2:
                raise ValueError(f"rig chain {n!r} needs two joints or more")
            cand = idx[c.get("from", "root")]
            # the nearest bone of the parent chain; at a joint two share, the later one (legs from the chest bone)
            par = min(cand, key=lambda i: (round(float(_seg_dist(pts[0], bones[i]["head"],
                                                                  bones[i].get("tail", bones[i]["head"]))), 2), -i))
            idx[n] = []
            for k, p in enumerate(pts):
                end = k == len(pts) - 1
                bones.append({"name": f"{n}_end" if end else f"{n}_{k + 1:02d}", "head": p, "parent": par,
                              "end": end, "src": str(c["joints"][k]), **({} if end else {"tail": pts[k + 1]})})
                par = len(bones) - 1
                if not end:
                    idx[n].append(par)
    return bones


def test_pose(bones: list[dict]) -> dict:
    """Turns that show off weights: humanoid elbow, shoulder, hip, knee, spine and head; chains: each chain's
    second bone 35 degrees."""
    names = {b["name"] for b in bones}
    if PREFIX + "Hips" in names:
        want = {"LeftForeArm": ([1, 0, 0], -75), "RightArm": ([0, 1, 0], 45), "LeftUpLeg": ([1, 0, 0], -35),
                "RightLeg": ([1, 0, 0], 60), "Spine1": ([0, 1, 0], 12), "Neck": ([0, 0, 1], 25)}
        return {PREFIX + k: v for k, v in want.items() if PREFIX + k in names}
    return {b["name"]: ([1, 0, 0], 35) for b in bones if b["name"].endswith("_02")}


def rig_bones(spec: dict) -> list[dict]:
    r = spec.get("rig") or {}
    if r.get("type") == "chains":
        return chains(spec)
    b = humanoid(spec)
    if b is None:
        raise ValueError("no humanoid joints (pelvis, chest, neck, head, shoulder/elbow/wrist/hip/knee/ankle .L/.R): "
                         "give spec[\"rig\"] = {\"type\": \"chains\", \"root\": ..., \"chains\": {...}}")
    return b


def _segments(rb: list[dict]):
    """Each weight-carrying rig bone as a segment: its head to its (first non-end or only) child's head."""
    kids: dict = {}
    for i, b in enumerate(rb):
        if b["parent"] >= 0:
            kids.setdefault(b["parent"], []).append(i)
    seg = {}
    for i, b in enumerate(rb):
        if b["end"] or b.get("noweight"):
            continue
        if "tail" in b:
            seg[i] = (b["head"], b["tail"])
            continue
        ch = kids.get(i, [])
        if ch:  # the child that continues the chain: the one straightest ahead (Spine2 -> Neck, not a clavicle)
            prev = b["head"] - rb[b["parent"]]["head"] if b["parent"] >= 0 else np.array([0, 0, 1.0])
            c = max(ch, key=lambda k: np.dot(rb[k]["head"] - b["head"], prev) / (np.linalg.norm(rb[k]["head"] - b["head"]) + 1e-9))
            seg[i] = (b["head"], rb[c]["head"])
        else:
            seg[i] = (b["head"], b["head"] + 1e-3)
    return seg


def _cone_piece(p, a: np.ndarray, b: np.ndarray, t0: float, t1: float):
    """The part of a bone's cone between t0 and t1 along it (radii interpolated): a rig bone's own flesh where it
    lies along the modelling bone."""
    import copy
    q = copy.copy(p)
    pr = dict(p.params)
    L = pr["len"]
    ra, rb = pr["ra"], pr["rb"]
    pr["a"] = a + t0 * (b - a)
    pr["len"] = max((t1 - t0) * L, 1e-4)
    pr["ra"], pr["rb"] = ra + t0 * (rb - ra), ra + t1 * (rb - ra)
    pr["cut"] = 0.0
    q.params = pr
    lo = np.minimum(pr["a"], a + t1 * (b - a)) - max(ra, rb) * 2
    q.lo, q.hi = lo, np.maximum(pr["a"], a + t1 * (b - a)) + max(ra, rb) * 2
    return q


def rig_weights(spec: dict, rb: list[dict], verts: np.ndarray, faces: np.ndarray | None = None,
                k: int = 4, smooth: int = SMOOTH) -> tuple[np.ndarray, np.ndarray]:
    """Skin weights on the rig bones. Each rig bone gets flesh of its own from the modelling geometry: the piece
    of every modelling cone it lies along (Spine, Spine1, Spine2 split the one spine cone), modelling bones lying
    inside its segment (a finger's pieces), and the rest of the modelling bones (a tusk, an ear, a collar) with
    go to the rig bone nearest their middle, blobs to the rig bone nearest their middle; a rig bone left with none (a hand, the toes) gets a cone
    along its own segment. Then `weights` on the rig tree: nearest-flesh distances, family-limited, smoothed."""
    mb = skeleton(spec)
    seg = _segments(rb)
    ids = list(seg)
    A = np.array([seg[i][0] for i in ids])
    B = np.array([seg[i][1] for i in ids])
    flesh = {i: [] for i in ids}
    for b in mb:
        p, h, t = b["prim"], b["head"], b["tail"]
        ax = t - h
        L = max(float(np.linalg.norm(ax)), 1e-9)
        tol = max(0.002, 0.02 * L)
        on_m = [(_seg_dist(A[q], h, t) < tol) and (_seg_dist(B[q], h, t) < tol) for q in range(len(ids))]
        pieces = []
        for q, on in enumerate(on_m):  # rig segments lying along this bone: their piece of its cone
            if on and np.linalg.norm(B[q] - A[q]) > tol:
                t0, t1 = sorted(float(((x - h) @ ax) / L ** 2) for x in (A[q], B[q]))
                t0, t1 = max(t0, 0.0), min(t1, 1.0)
                if t1 - t0 > 0.02:
                    pieces.append((ids[q], t0, t1))
        for bl in b["prims"][1:]:  # blobs: the rig bone nearest their middle (a palm the hand, not a finger)
            flesh[ids[int(np.argmin(_seg_dist(0.5 * (bl.lo + bl.hi), A, B)))]].append(bl)
        if pieces:
            for i, t0, t1 in pieces:
                flesh[i].append(_cone_piece(p, h, t, t0, t1))
            continue
        inside = [q for q in range(len(ids)) if _seg_dist(h, A[q], B[q]) < tol and _seg_dist(t, A[q], B[q]) < tol]
        # else the rig bone nearest its middle: a curled finger's pieces find their phalanx, a tusk the head
        q = inside[0] if inside else int(np.argmin(_seg_dist(0.5 * (h + t), A, B)))
        flesh[ids[q]].append(p)
    for q, i in enumerate(ids):  # nothing of its own: a cone along its segment, as thick as its neighbours
        if not flesh[i]:
            have = [n for n, j in enumerate(ids) if any(x.kind == "cone" and "rb" in x.params for x in flesh[j])]
            nq = min(have, key=lambda n: float(_seg_dist(A[q], A[n], B[n]))) if have else None
            ref = next(x for x in flesh[ids[nq]] if x.kind == "cone" and "rb" in x.params) if nq is not None else None
            r = 0.4 * (min(ref.params["ra"], ref.params["rb"]) if ref is not None else 0.03)
            from .spec import Prim, bone_frame
            a, bb = A[q], B[q] if np.linalg.norm(B[q] - A[q]) > 1e-3 else A[q] + np.array([0, 0, 1e-3])
            flesh[i].append(Prim(rb[i]["name"], "cone", "add", 0.0, 0, np.minimum(a, bb) - r, np.maximum(a, bb) + r,
                                 {"a": a, "frame": bone_frame(a, bb), "len": float(np.linalg.norm(bb - a)), "ra": r,
                                  "rb": r, "flat": [1.0, 1.0], "bow": (0.0, 0.0), "cut": 0.0}))
    carry = [{"name": rb[i]["name"], "parent": -1, "prims": flesh[i],
              "prim": next((x for x in flesh[i] if x.kind == "cone"), flesh[i][0])} for i in ids]
    pos = {i: n for n, i in enumerate(ids)}
    for n, i in enumerate(ids):  # the rig tree among the weight-carrying bones (end joints skipped)
        par = rb[i]["parent"]
        while par >= 0 and par not in pos:
            par = rb[par]["parent"]
        carry[n]["parent"] = pos.get(par, -1)
    for c in carry:
        if "ra" not in c["prim"].params:  # a blob-only bone: its falloff from the blob's size
            sz = float(np.min(c["prim"].hi - c["prim"].lo)) / 2
            c["falloff_r"] = sz
    J, W = weights(carry, verts, faces, k=k, smooth=smooth)
    return np.asarray(ids)[J], W


