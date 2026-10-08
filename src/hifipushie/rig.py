"""An armature and skin weights from the spec's skeleton, for export_asset(rig=True).

Every additive bone of the (mirrored, kit-expanded) spec becomes an armature bone. The joint graph is walked
breadth first from a root joint ("pelvis", "hips" or "root" if there is one, else the graph's centre), which
orients each bone parent -> child: its head is the joint it was reached from (the pivot it turns about), its parent
the bone that reached that joint. Pieces of the skeleton not joined to the rest (a buckle, a tail made separately)
hang from the bone nearest to them.

Skin weights come from the bones' own round cones: at each vertex, every bone's exact distance (`sdf.field_at` of
that one primitive: thickness counts, so a thick thigh claims the flesh a thin bone axis would lose), weighted
exp(-(d - d_nearest) / falloff) with the falloff half the radius of the thinner of the bone and the nearest one (the
fat torso's own radius spread it halfway down the upper arm: the raised arm bent mid-bicep), among the nearest bone's
family (two steps of parents, children, siblings), smoothed over the mesh, the four strongest kept and normalised.
Where a limb continues through a joint (collar -> upper arm -> forearm), each cone stops at the plane bisecting the
two bones, so the collar's round end doesn't claim the top of the upper arm. Blobs (a belly, a head) go with the bones
they sit on and aren't cut. Parts (clothes, eyes) are skinned to the same bones. A limb fused to the body (the
goblin's arms blend into its belly) webs when raised whatever the weights: model limbs clear of the torso.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from . import sdf
from .spec import compile_prims, expand_mirror, resolve_point

ROOTS = ("pelvis", "hips", "root", "hip")
FALLOFF = 0.5  # weight falls by e over this fraction of a bone's radius past the nearest bone
SMOOTH = 10  # rounds of averaging weights with neighbouring vertices
WORN_SMOOTH = 0  # rounds of the same over a worn part's own mesh after it read the skin's weights (parts.<p>.rig_smooth). 0 since
# 2026-10-07: layers smoothed each over its own mesh drift apart (a jacket's hem toward the pelvis, the trousers under it
# on down the thigh) and cross when posed: s0urc3's seated Garrett. What 6 rounds were for (a collar's two faces reading
# two places) is cured at the lookup (rig_template.from_surface two_sided).


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
        if pr is None or pr.kind not in ("ellipsoid", "box", "cylinder", "blade", "lids", "csg"):
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
    D = np.stack([np.min([_flesh(p, b.get("cuts", ()), V) for p in b["prims"]], 0) for b in bones], 1)
    r = np.array([b["falloff_r"] if "falloff_r" in b else 0.5 * (b["prim"].params["ra"] + b["prim"].params["rb"])
                  for b in bones])
    near = D.argmin(1)
    # the blend's width is set by the thinner bone: the fat torso's own radius would spread it down the arm
    fall = np.maximum(falloff * np.minimum(r[None, :], r[near][:, None]), 1e-3)
    d0 = D.min(1, keepdims=True)
    W = np.exp(-(D - d0) / fall)
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


def _flesh(p, cuts, V: np.ndarray) -> np.ndarray:
    """A flesh primitive's distance; a bone's cone stops at its joints' planes ({"cuts": [(point, normal)]}, keeping
    the -normal side). Blobs aren't cut: a belly on the spine would lose its sides to a hanging arm."""
    d = sdf.field_at([p], V, clip=False)
    if p.kind == "cone":
        for q, n in cuts:
            d = np.maximum(d, (V - q) @ n)
    return d


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
    collar = chest + t * (neck - chest)  # the spine at shoulder height: where the clavicles start
    # Where Neck and Head pivot. Kit characters: the "neck" joint is the skull's base (the head bone starts there), so
    # Head sits on it and Neck at shoulder height. A template may say otherwise (`rig` in its dict: {rig joint: [joint
    # a, joint b, t]}): MakeHuman's "neck" joint is the neck's BASE (C7) and its head bone starts 63% of the way to
    # the "head" joint; Head on the "neck" joint there pivoted the head at the bottom of the neck, 10 cm low, and the
    # whole neck's turn had to happen in the skin under the jaw.
    hint = {}
    if spec.get("base"):
        from . import base as basemod
        hint = basemod.source(spec["base"]).get("rig") or {}

    def hinted(name, default):
        if name in hint:
            a, b, f = hint[name]
            return _joint(s, a) + float(f) * (_joint(s, b) - _joint(s, a))
        return default
    add("Neck", hinted("Neck", collar), "Spine2", src="template" if "Neck" in hint else "placed")
    add("Head", hinted("Head", neck), "Neck", src="template" if "Head" in hint else "neck")
    up = (head - neck) / max(np.linalg.norm(head - neck), 1e-9)
    add("HeadTop_End", _surface_along(spec, head, up, 2 * np.linalg.norm(head - neck) + 0.5), "Head", True)
    for side, S in (("L", "Left"), ("R", "Right")):
        j = {k: _joint(s, f"{k}.{side}") for k in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")}
        add(f"{S}Shoulder", collar + 0.2 * (j["shoulder"] - collar), "Spine2")
        add(f"{S}Arm", j["shoulder"], f"{S}Shoulder", src=f"shoulder.{side}")
        add(f"{S}ForeArm", j["elbow"], f"{S}Arm", src=f"elbow.{side}")
        add(f"{S}Hand", j["wrist"], f"{S}ForeArm", src=f"wrist.{side}")
        # the hand kit's chains, or a base body's own (the template's names: finger1 = index .. finger4 = pinky)
        kit = f"hand_th_0.{side}" in J or f"hand_f1_0.{side}" in J
        th = (lambda k: f"hand_th_{k}.{side}") if kit else (lambda k: f"thumb_{k}.{side}")
        fg = (lambda f, k: f"hand_f{f}_{k}.{side}") if kit else (lambda f, k: f"finger{f}_{k}.{side}")
        thumb = [th(k) for k in range(4)]
        if all(x in J for x in thumb):
            for k, x in enumerate(thumb):
                add(f"{S}HandThumb{k + 1}", _joint(s, x), f"{S}Hand" if k == 0 else f"{S}HandThumb{k}", k == 3, x)
        fingers = sorted((f for f in range(1, 6) if all(fg(f, k) in J for k in range(4))),
                         key=lambda f: np.linalg.norm(_joint(s, fg(f, 0)) - _joint(s, thumb[0]))
                         if thumb[0] in J else f)
        names = FINGERS if len(fingers) >= 4 else ("Index", "Middle", "Ring")[:len(fingers) - 1] + ("Pinky",) \
            if len(fingers) > 1 else ("Index",)
        for f, fn in zip(fingers, names):
            for k in range(4):
                add(f"{S}Hand{fn}{k + 1}", _joint(s, fg(f, k)),
                    f"{S}Hand" if k == 0 else f"{S}Hand{fn}{k}", k == 3, fg(f, k))
        add(f"{S}UpLeg", j["hip"], "Hips", src=f"hip.{side}")
        add(f"{S}Leg", j["knee"], f"{S}UpLeg", src=f"knee.{side}")
        add(f"{S}Foot", j["ankle"], f"{S}Leg", src=f"ankle.{side}")
        toe = _joint(s, f"toe.{side}") if f"toe.{side}" in J else j["ankle"] + np.array([0, -0.1, -0.05])
        add(f"{S}ToeBase", toe, f"{S}Foot", src=f"toe.{side}")
        fwd = toe - j["ankle"]
        fwd[2] = 0
        fwd /= max(np.linalg.norm(fwd), 1e-9)
        add(f"{S}Toe_End", _surface_along(spec, toe, fwd, 0.5), f"{S}ToeBase", True)
    return _add_twist(bones, twist_counts(spec))


# ---- twist bones ------------------------------------------------------------------------------------------------
# A limb segment's roll about its own axis is not a rotation of one joint in a person: pronation is the radius
# turning over the ulna along the whole forearm, and the upper arm's roll is taken up at the shoulder, not by the
# deltoid's skin. With one bone per segment the whole roll lands on one joint (a hand turned 75 deg was wrung at the
# wrist: s0urc3's Garrett). So each segment gets a TWIST CHAIN, as Unreal's mannequin has (upperarm_twist_01/02,
# lowerarm_twist_01/02, thigh_twist, calf_twist) and VRM's roll constraint describes: extra LEAF bones, children of
# the segment's own bone, standing at stations along it, each turning about the segment's axis by a share of a
# driver's roll.
#   follow  (forearm, calf): the driver is the segment's CHILD (Hand, Foot). Share k/n at station k/n: nothing at the
#           elbow, the hand's whole roll at the wrist, so the wrist joint itself doesn't twist.
#   counter (upper arm, thigh): the driver is the segment's OWN bone. Share -(1 - (k-1)/n) at station (k-1)/n: the
#           bone at the shoulder turns back the whole of the arm's roll (the deltoid stays with the clavicle), the
#           elbow end follows the bone.
# The Mixamo set is untouched: the twist bones come after it in the list, nothing hangs from them, and with no
# driver they sit still on their parent, where the skin is exactly what it was without them (their weights are their
# parent's weight shared out along the segment, `_spread_twist`). An engine drives them (glTF has no constraints):
# node extras "hifipushie_twist" and the export json's rig.twist carry driver, axis and share.
TWIST = {"Arm": ("counter", "arm", "ForeArm"), "ForeArm": ("follow", "forearm", "Hand"),
         "UpLeg": ("counter", "upleg", "Leg"), "Leg": ("follow", "leg", "Foot")}
# Linear blend skinning between two stations turned apart by d loses cos^2(d / 2) of a section's area half way, so
# the count follows how far a segment rolls. Upper arm: two, as Unreal's mannequin (60 deg: 0.93 of the area kept).
# Forearm: three: a hand turns 75 deg palm down and 105 in gestures; measured at 105 on the MakeHuman body, none
# 0.49, two 0.80, three 0.87. Legs: one each (a foot or thigh rolls 30-45 deg: 0.88).
TWIST_DEFAULT = {"arm": 2, "forearm": 3, "upleg": 1, "leg": 1}
TWIST_MAX = 4
TWIST_MERGE = 3.0  # at a fifth bone: a split whose smaller half is under this x the smallest weight goes back together
ROLL_OF_PARENT = ("Hand", "Foot")  # their "roll" is about the segment they end


def twist_counts(spec: dict) -> dict:
    """spec["rig"]["twist"]: false / 0 (none), an int (that many on every segment), or {"arm", "forearm", "upleg",
    "leg": count}; left out = TWIST_DEFAULT."""
    t = (spec.get("rig") or {}).get("twist", True)
    if t is True or t is None:
        return dict(TWIST_DEFAULT)
    if t is False:
        return {k: 0 for k in TWIST_DEFAULT}
    if isinstance(t, (int, float)):
        t = {k: int(t) for k in TWIST_DEFAULT}
    bad = [k for k in t if str(k).lower() not in TWIST_DEFAULT]
    if bad:
        raise ValueError(f"rig.twist: unknown segment(s) {bad} (have {', '.join(TWIST_DEFAULT)})")
    out = dict(TWIST_DEFAULT)
    for k, v in t.items():
        n = int(v)
        if not 0 <= n <= TWIST_MAX:
            raise ValueError(f"rig.twist.{k}: {v} (0 to {TWIST_MAX} twist bones a segment)")
        out[str(k).lower()] = n
    return out


def _add_twist(bones: list[dict], counts: dict) -> list[dict]:
    """The twist chains, appended after the Mixamo set (its names, order and indices stay as they were)."""
    idx = {b["name"]: i for i, b in enumerate(bones)}
    extra = []
    for S in ("Left", "Right"):
        for seg, (mode, key, child) in TWIST.items():
            n = counts.get(key, 0)
            i, c = idx.get(PREFIX + S + seg), idx.get(PREFIX + S + child)
            if not n or i is None or c is None:
                continue
            a, b = bones[i]["head"], bones[c]["head"]
            L = float(np.linalg.norm(b - a))
            if L < 1e-6:
                continue
            for k in range(1, n + 1):
                t = k / n if mode == "follow" else (k - 1) / n
                share = k / n if mode == "follow" else -(1.0 - (k - 1) / n)
                driver = PREFIX + S + (child if mode == "follow" else seg)
                extra.append({"name": f"{PREFIX}{S}{seg}Twist{k}", "head": a + t * (b - a), "parent": i, "end": False,
                              "src": f"twist, {t:.2f} along {S}{seg}",
                              "twist": {"of": bones[i]["name"], "driver": driver, "mode": mode,
                                        "share": round(share, 4), "station": round(t, 4), "length": L,
                                        "axis": (b - a) / L}})
    return bones + extra


def twist_table(bones: list[dict]) -> list[dict]:
    """What an engine needs to drive the twist bones: [{"bone", "parent", "driver", "mode", "share", "station",
    "axis" (unit, Blender axes, the rest pose; the bone's local +Y in the GLB)}]."""
    return [{"bone": b["name"], "parent": b["twist"]["of"], "driver": b["twist"]["driver"], "mode": b["twist"]["mode"],
             "share": b["twist"]["share"], "station": b["twist"]["station"],
             "axis": [round(float(x), 6) for x in b["twist"]["axis"]]} for b in bones if b.get("twist")]


def _spread_twist(rb: list[dict], verts: np.ndarray, J: np.ndarray, W: np.ndarray, k: int = 4):
    """Each twisted segment's weight shared out along it: a vertex's weight on the segment's bone is split between
    the two stations it lies between (the bone itself is the station at the undriven end), linearly. Undriven, the
    twist bones move with their parent, so the skin is what it was; driven, the roll runs linearly joint to joint."""
    chains: dict = {}
    for i, b in enumerate(rb):
        if b.get("twist"):
            chains.setdefault(b["parent"], []).append(i)
    if not chains:
        return J, W
    V = np.asarray(verts, np.float64)
    kk = J.shape[1]
    J2 = np.concatenate([J, np.zeros_like(J)], 1)
    W2 = np.concatenate([W, np.zeros_like(W)], 1)
    for seg, tw in chains.items():
        t0 = rb[tw[0]]["twist"]
        st = sorted([(rb[i]["twist"]["station"], i) for i in tw] + [(0.0 if t0["mode"] == "follow" else 1.0, seg)])
        ts = np.array([s[0] for s in st])
        bi = np.array([s[1] for s in st])
        rows, cols = np.nonzero((J == seg) & (W > 0))
        if not len(rows):
            continue
        t = np.clip(((V[rows] - rb[seg]["head"]) @ t0["axis"]) / t0["length"], ts[0], ts[-1])
        hi = np.clip(np.searchsorted(ts, t, side="right"), 1, len(ts) - 1)
        lo = hi - 1
        f = (t - ts[lo]) / np.maximum(ts[hi] - ts[lo], 1e-9)
        w = W[rows, cols]
        J2[rows, cols], W2[rows, cols] = bi[lo], w * (1 - f)
        J2[rows, kk + cols], W2[rows, kk + cols] = bi[hi], w * f
    # more than k bones now. Dropping the smallest weight moves undriven skin (a belly vertex on Spine, Spine1, Hips
    # and the arm, the arm split in two: 10 mm when Spine1's 0.13 went); putting a split back together steps the twist
    # against the neighbours' when driven (thigh vertices with 2-4% of three other bones: sheared triangles). So the
    # cheaper of the two: the split goes back only if its smaller half is within TWIST_MERGE x the smallest weight.
    for _ in range(kk):
        over = np.flatnonzero((W2 > 0).sum(1) > k)
        if not len(over):
            break
        r = np.arange(len(over))
        a, b = W2[over, :kk], W2[over, kk:]
        pair = np.where((a > 0) & (b > 0), np.minimum(a, b), np.inf)
        c = pair.argmin(1)
        alone = np.where(W2[over] > 0, W2[over], np.inf)
        s = alone.argmin(1)
        merge = np.isfinite(pair[r, c]) & (pair[r, c] <= TWIST_MERGE * alone[r, s])
        mo, mc = over[merge], c[merge]
        keep_b = W2[mo, kk + mc] > W2[mo, mc]
        tot = W2[mo, mc] + W2[mo, kk + mc]
        J2[mo, mc] = np.where(keep_b, J2[mo, kk + mc], J2[mo, mc])
        W2[mo, mc], W2[mo, kk + mc] = tot, 0.0
        W2[over[~merge], s[~merge]] = 0.0
    order = np.argsort(-W2, axis=1, kind="stable")[:, :k]
    Jk = np.take_along_axis(J2, order, 1)
    Wk = np.take_along_axis(W2, order, 1)
    Wk /= np.maximum(Wk.sum(1, keepdims=True), 1e-12)
    Jk[Wk <= 0] = 0
    return Jk, Wk


def _quat(axis, deg) -> np.ndarray:
    ax = np.asarray(axis, float)
    ax = ax / max(np.linalg.norm(ax), 1e-12)
    h = np.radians(deg) / 2
    return np.r_[np.cos(h), np.sin(h) * ax]


def roll_about(axis, turn) -> float:
    """The roll (degrees) of a turn (axis, degrees) about a unit axis: the twist of its swing-twist decomposition.
    This is the driver's side of every engine recipe: decompose the driver's LOCAL rotation from rest about the
    segment's axis, keep the twist angle."""
    q = _quat(turn[0], turn[1])
    return float(np.degrees(2 * np.arctan2(q[1:] @ np.asarray(axis, float), q[0])))


def roll_axis(bones: list[dict], name: str) -> np.ndarray:
    """The axis a bone rolls about: the segment it ends for hands and feet (the forearm, the shin), else its own."""
    i = [b["name"] for b in bones].index(name)
    b = bones[i]
    if name.endswith(ROLL_OF_PARENT) and b["parent"] >= 0:
        d = b["head"] - bones[b["parent"]]["head"]
    else:
        seg = _segments(bones)
        d = seg[i][1] - seg[i][0] if i in seg else np.array([0, 0, 1.0])
    return d / max(np.linalg.norm(d), 1e-12)


def resolve_turns(bones: list[dict], turns: dict) -> dict:
    """Turns with the axis "roll" given their bone's roll axis (`roll_axis`)."""
    return {k: ((roll_axis(bones, k) if isinstance(ax, str) else ax), deg) for k, (ax, deg) in turns.items()}


def drive_twist(bones: list[dict], turns: dict) -> dict:
    """The turns plus every twist bone's own: its share of its driver's roll about the segment's axis (what an
    engine's driver does each frame; the documented shares, so a pose made with this is the proof of them)."""
    out = dict(turns)
    for b in bones:
        tw = b.get("twist")
        if tw and tw["driver"] in turns and b["name"] not in turns:
            ang = tw["share"] * roll_about(tw["axis"], turns[tw["driver"]])
            if abs(ang) > 1e-9:
                out[b["name"]] = (tw["axis"], ang)
    return out


def twist_check(bones: list[dict], V: np.ndarray, F: np.ndarray, J: np.ndarray, W: np.ndarray, driver: str,
                deg: float = 75.0, drive: bool = True, bins: int = 10) -> dict:
    """A segment's twist test: its driver rolled `deg` about the segment's axis (twist bones driven by their shares,
    or left still: what an engine without drivers shows), measured on the segment's skin by station along it:
    "twist" (how far the skin has turned about the axis, deg), "area" (cross-section area against rest, from the
    skin's distance to the axis: the candy wrapper is a dip), plus "at_end" / "at_start" (the twist left to the
    joints: hand roll minus the skin's turn by the wrist; the skin's turn by the elbow), "step" (the largest change
    of twist between neighbouring stations), "area_min", "tri_min" (the worst triangle's quality against its rest
    quality, 4 sqrt(3) area / sum of squared edges)."""
    names = [b["name"] for b in bones]
    d = names.index(driver)
    follow = driver.endswith(ROLL_OF_PARENT)
    seg = bones[d]["parent"] if follow else d
    a = bones[seg]["head"]
    ax = roll_axis(bones, driver)
    kids = [b["head"] for b in bones if b["parent"] == seg and not b.get("twist") and not b["end"]]
    L = max(float((k - a) @ ax) for k in kids)
    own = {seg} | {i for i, b in enumerate(bones) if b.get("twist") and b["parent"] == seg}
    if follow:
        own.add(d)
    turns = {driver: (ax, deg)}
    P = pose(bones, V, J, W, drive_twist(bones, turns) if drive else turns)
    t = ((V - a) @ ax) / L
    wown = (W * np.isin(J, list(own))).sum(1)
    rel0 = V - a
    rad0 = rel0 - np.outer(rel0 @ ax, ax)
    rel1 = P - a
    rad1 = rel1 - np.outer(rel1 @ ax, ax)
    r0, r1 = np.linalg.norm(rad0, axis=1), np.linalg.norm(rad1, axis=1)
    sel = (wown > 0.6) & (t > -0.05) & (t < 1.1) & (r0 > 1e-4)
    ang = np.degrees(np.arctan2(np.cross(rad0, rad1) @ ax, (rad0 * rad1).sum(1)))
    edges = np.linspace(0.0, 1.0, bins + 1)
    tw, ar, st = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = sel & (t >= lo) & (t < hi)
        if m.sum() < 6:
            continue
        st.append(round(float(0.5 * (lo + hi)), 3))
        tw.append(round(float(np.median(ang[m])), 1))
        ar.append(round(float((r1[m].mean() / r0[m].mean()) ** 2), 3))
    Fm = F[sel[F].all(1)]

    def quality(X):
        e = [X[Fm[:, (i + 1) % 3]] - X[Fm[:, i]] for i in range(3)]
        A = 0.5 * np.linalg.norm(np.cross(e[0], -e[2]), axis=1)
        return 4 * np.sqrt(3) * A / np.maximum(sum((x * x).sum(1) for x in e), 1e-18)
    q = quality(P) / np.maximum(quality(V), 1e-9) if len(Fm) else np.ones(1)
    return {"driver": driver, "deg": deg, "driven": bool(drive), "station": st, "twist": tw, "area": ar,
            "at_start": tw[0] if tw else None, "at_end": round(deg - tw[-1], 1) if tw else None,
            "step": round(float(np.max(np.abs(np.diff([0.0] + tw + [deg])))), 1) if tw else None,
            "area_min": min(ar) if ar else None, "tri_min": round(float(q.min()), 3),
            "tri_p1": round(float(np.percentile(q, 1)), 3)}


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
                "RightLeg": ([1, 0, 0], 60), "Spine1": ([0, 1, 0], 12), "Neck": ([0, 0, 1], 25),
                "RightHand": ("roll", 75)}  # palm turned: the forearm's twist bones take it (`drive_twist`)
        return resolve_turns(bones, {PREFIX + k: v for k, v in want.items() if PREFIX + k in names})
    return {b["name"]: ([1, 0, 0], 35) for b in bones if b["name"].endswith("_02")}


PART_WEIGHTS = ("surface", "around", "distance")
TWO_SIDED = True  # worn parts read the skin they lie on from both their faces (rig_template.from_surface)
WORN_WEIGHTS = "surface"  # what a worn part reads without parts.<p>.rig_weights


def part_weights(spec: dict, pn: str, is_skin: bool) -> str:
    """How a part of a character with a base body gets its weights: parts.<p>.rig_weights, else "surface" for the
    skin and WORN_WEIGHTS for what is worn. "surface": the base's weights at the closest point of its surface
    facing the same way; "around": an average of the base's weights round that point, wider the farther the cloth
    is from the skin (rig_template.around_surface); "distance": the part's own distance weights to the rig's bones."""
    how = ((spec.get("parts") or {}).get(pn) or {}).get("rig_weights")
    if how is None:
        return "surface" if is_skin else WORN_WEIGHTS
    if how not in PART_WEIGHTS:
        raise ValueError(f"parts.{pn}.rig_weights: {how!r} (one of {', '.join(PART_WEIGHTS)})")
    return how


def skin_parts(spec: dict, rb: list[dict], meshes: dict, smooth: int = SMOOTH) -> dict:
    """Weights for every part {name: (verts, tris)} -> {name: (J, W)}. parts.<p>.rig_bone (a rig bone, the prefix
    optional) binds a part rigidly (a bag on the hip, a disc in the hand: split between bones they tore); with a base
    body every other part reads the base body's weights off its surface (clothes move with the skin under them:
    weighted on their own they drifted from it and the body poked through), and those are the template's own
    hand-made weights when it has them (MakeHuman: rig_template.py; spec["rig"]["weights"] = "distance" for ours)."""
    from . import rig_template
    defs = spec.get("parts") or {}
    names = [b["name"] for b in rb]
    out = {}
    ref = None
    hf = head_field(spec, rb)
    opts = spec.get("rig") or {}
    sp = opts.get("skin_part") or ("body" if "body" in meshes else None)
    if sp is None and hf is not None:  # no part called "body": the skin is the part with the most of the head
        n = {pn: int((hf["h"](V) > 0.999).sum()) for pn, (V, F) in meshes.items()
             if len(V) and not (defs.get(pn) or {}).get("rig_bone") and float(hf.get("part", hf["h"])(V).mean()) < HEAD_PART}
        sp = max(n, key=n.get) if n else None
    skin = {sp} | set((spec.get("face_shapes") or {}).get("parts") or ())
    if spec.get("base"):  # the reference: the base body's own quads, whole (the export's skin under clothes is gone)
        from . import base as basemod
        from .spec import expand_mirror as _em
        surf = basemod.surface(basemod.inject(_em(spec)), spec["base"])
        Wq, fq = surf["quads"]
        Wq = np.asarray(Wq, float)
        Tq = np.array([(f[0], f[j], f[j + 1]) for f in fq for j in range(1, len(f) - 1)])
        # a template with hand-made weights (MakeHuman): its own, by topology (rig_template.py); else ours by distance
        ref = rig_template.template_weights(spec, rb, surf)
        spread = ref is not None  # the template knows no twist bones: shared out per part, after the transfer
        if ref is None:
            Jr, Wr = rig_weights(spec, rb, Wq, Tq, smooth=smooth)
            ref = np.zeros((len(Wq), len(rb)))
            np.add.at(ref, (np.repeat(np.arange(len(Wq)), Jr.shape[1]), Jr.ravel()), Wr.ravel())
    for pn, (V, F) in meshes.items():
        bone = (defs.get(pn) or {}).get("rig_bone")
        if bone:
            full = bone if bone in names else PREFIX + bone
            if full not in names:
                raise ValueError(f"parts.{pn}.rig_bone: no rig bone {bone!r}")
            J = np.zeros((len(V), 4), int)
            J[:, 0] = names.index(full)
            W = np.zeros((len(V), 4))
            W[:, 0] = 1.0
            out[pn] = (J, W)
        elif ref is not None and part_weights(spec, pn, pn in skin) == "distance":
            out[pn] = rig_weights(spec, rb, V, F, smooth=smooth)  # this part on its own, whatever the base has
        elif ref is not None:
            # read off the base's SURFACE where it faces the way the vertex does (rig_template.from_surface): the
            # nearest base VERTICES of a finger's side are as often the next finger's (weights bled 0.4-0.57 across)
            V = np.asarray(V, float)
            F = np.asarray(F)
            N = np.zeros_like(V)
            if len(F):
                fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
                for c in range(3):
                    np.add.at(N, F[:, c], fn)
                N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-30)
            if part_weights(spec, pn, pn in skin) == "around":
                D = rig_template.around_surface(Wq, Tq, ref, V, N if len(F) else None)
            else:
                D = rig_template.from_surface(Wq, Tq, ref, V, N if len(F) else None,
                                              two_sided=pn not in skin and TWO_SIDED)
            rounds = int((defs.get(pn) or {}).get("rig_smooth", 0 if pn in skin else WORN_SMOOTH))
            if len(F) and rounds:
                # cloth is a sheet of its own: the weights it read off the skin are evened over ITS mesh, as a rigger
                # smooths a transfer. A collar's two faces and its edge read three places on the shoulder, and its
                # wing crumpled when the arm rose. Seam-split vertices are one vertex here (or they'd crack).
                _, inv = np.unique(np.round(V / 1e-5).astype(np.int64), axis=0, return_inverse=True)
                inv = inv.ravel()
                cnt = np.bincount(inv).astype(np.float64)[:, None]
                Dw = np.zeros((len(cnt), D.shape[1]))
                np.add.at(Dw, inv, D)
                D = _smooth(Dw / cnt, inv[F], rounds)[inv]
            J, W = rig_template.top_k(D)
            out[pn] = _spread_twist(rb, V, J, W) if spread else (J, W)
        else:
            out[pn] = rig_weights(spec, rb, V, F, smooth=smooth)
    cov = skin_cover(spec, rb, meshes, hf, skin) if hf is not None else {}
    for pn, (V, F) in meshes.items():
        bone = (defs.get(pn) or {}).get("rig_bone")
        if hf is not None and not bone and len(V):  # the head is rigid: the falloff to the neck is on the throat
            h = hf["h"](V)
            kind = _head_kind(spec, hf, pn, V, skin)
            if kind == "head":  # a part of the head (teeth, tongue, eyes, lashes): all of it
                h = np.ones(len(V))
            elif kind == "worn":
                # a collar, a scarf, a strap over the shoulder: it sits on the body and reaches up beside the jaw.
                # It keeps the weights of the neck under it (the golfer's collar top, 1-2 cm above the floor at the
                # nape, was Head 1.0 and turned with the face: 47 mm off the shirt, 299 triangles inside out)
                continue
            elif pn in cov:  # skin under what is worn follows its cover (which takes no head rule): see skin_cover
                h = h * (1.0 - cov[pn])
            out[pn] = _rigid_head(np.asarray(out[pn][0]), np.asarray(out[pn][1], np.float64), h, hf["bone"])
    # parts.<p>.rig_drop = [joints]: a garment never follows these joints; their weight goes up the chain to the
    # nearest joint it keeps. What a rigger does after a weight transfer: prune the influences a garment has no
    # business with. Shorts that end at the knee read the skin's knee blend, so the shin bent their hem (17-27 mm
    # on the golfer): ["Leg"] gives it to the thigh, and the hem stays a tube. A name without a side is both sides;
    # a segment's twist joints go with it.
    for pn in meshes:
        drop = (defs.get(pn) or {}).get("rig_drop")
        if not drop or pn not in out or (defs.get(pn) or {}).get("rig_bone"):
            continue
        # {joint: share}: only that share of the joint's weight goes up. A shirt's hem over the hips, {"UpLeg": 0.5}:
        # half with the pelvis, half with the thigh, what a rigger paints on an untucked hem.
        shares = dict(drop) if isinstance(drop, dict) else {d: 1.0 for d in ([drop] if isinstance(drop, str) else drop)}
        J, W = np.asarray(out[pn][0]), np.asarray(out[pn][1], np.float64)
        D = np.zeros((len(J), len(rb)))
        np.add.at(D, (np.repeat(np.arange(len(J)), J.shape[1]), J.ravel()), W.ravel())
        share = np.zeros(len(rb))
        for nm, s in shares.items():
            if not 0.0 <= float(s) <= 1.0:
                raise ValueError(f"parts.{pn}.rig_drop: {nm!r}'s share must be 0..1, got {s!r}")
            share[drop_joints(rb, [nm], f"parts.{pn}.rig_drop")] = float(s)
        gone = share >= 1.0

        def depth(i):
            n = 0
            while rb[i]["parent"] >= 0:
                i, n = rb[i]["parent"], n + 1
            return n
        for i in sorted(np.flatnonzero(share > 0), key=lambda i: -depth(i)):  # leaves first: weight climbs
            q = rb[i]["parent"]
            while q >= 0 and (gone[q] or share[q] >= share[i]):  # a twist joint shares like its segment: past both
                q = rb[q]["parent"]
            if q < 0:
                raise ValueError(f"parts.{pn}.rig_drop: nothing is left above {rb[i]['name']}")
            D[:, q] += share[i] * D[:, i]
            D[:, i] *= 1.0 - share[i]
        J = np.argsort(-D, axis=1, kind="stable")[:, :J.shape[1]]
        W = np.take_along_axis(D, J, 1)
        J[W <= 0] = 0
        out[pn] = (J, W / np.maximum(W.sum(1, keepdims=True), 1e-12))
    # parts.<p>.rig_attach = "<part>" | [parts]: where this part comes within rig_attach_length (ATTACH) of a part
    # bound to one joint (rig_bone), it blends to that joint: a strap's end goes with the bag it carries, the rest
    # of it with the body it lies on. (The golfer's strap read the thigh next to a bag bound to Hips and tore.)
    from scipy.spatial import cKDTree
    for pn, (V, F) in meshes.items():
        d_ = defs.get(pn) or {}
        to = d_.get("rig_attach")
        if not to or d_.get("rig_bone") or not len(V):
            continue
        reach = float(d_.get("rig_attach_length", ATTACH))
        for other in ([to] if isinstance(to, str) else to):
            ob = (defs.get(other) or {}).get("rig_bone")
            if other not in meshes or not ob or not len(meshes[other][0]):
                raise ValueError(f"parts.{pn}.rig_attach: {other!r} must be an exported part with a rig_bone")
            dist, _ = cKDTree(np.asarray(meshes[other][0], float)).query(np.asarray(V, float), distance_upper_bound=reach)
            h = 1.0 - _ss(np.where(np.isfinite(dist), dist, reach) / reach)
            out[pn] = _rigid_head(np.asarray(out[pn][0]), np.asarray(out[pn][1], np.float64), h,
                                  names.index(ob if ob in names else PREFIX + ob))
    return out


def _head_kind(spec: dict, hf: dict, pn: str, V: np.ndarray, skin: set) -> str:
    """What the head rule makes of a part: "head" (all of it rigid: teeth, eyes), "worn" (no head rule: a collar) or
    "skin" (the falloff). parts.<p>.rig_head = true | false overrides worn."""
    share = float(hf.get("part", hf["h"])(V).mean())
    worn = ((spec.get("parts") or {}).get(pn) or {}).get("rig_head")
    worn = (not (pn in skin or share >= HEAD_WORN)) if worn is None else not worn
    return "head" if share >= HEAD_PART else "worn" if worn else "skin"


COVER_REACH = 0.03  # m: skin with a worn part's surface this near, outward of it, is covered by it
COVER_OUT = True    # the hand-over lies on the visible skin beside the cover (else on the covered skin under it)
COVER_EASE = 0.02   # m in from where the cover starts over which covered skin hands over to its cover's weights
COVER_SMOOTH = 4    # rounds of smoothing the share over the mesh (spec.rig.rigid_head.cover.smooth)


def skin_cover(spec: dict, rb: list[dict], meshes: dict, hf: dict | None = None, skin: set | None = None) -> dict:
    """{skin part: 0..1 per vertex}: how much a vertex of the skin lies UNDER something worn (a collar, a jacket's
    neck; parts the head rule leaves alone). Skin hidden under clothing follows what covers it, as a rigger has it
    (or deletes it): worn parts take no head rule, so the neck's long head falloff (HEAD_FALL, rigid_near's band) on
    skin under a collar turned and nodded that skin through the collar (Garrett: neck skin 12-16 cm under the Head
    joint Head 0.70, his collar there 0.16; 52 skin vertices through the jacket's collar in the game's idle, 73 at a
    33 deg head turn). 0 on visible skin and COVER_EASE in from the cover's edge 1: there the head rule doesn't
    apply. A vertex is covered when a ray out along its normal meets a worn part's surface within COVER_REACH; the share
    is then smoothed COVER_SMOOTH rounds over the mesh. spec.rig.rigid_head.cover = false turns it off, {"reach",
    "ease", "smooth"} set it."""
    from scipy.spatial import cKDTree

    from .rig_template import _closest_on_triangles
    hf = hf or head_field(spec, rb)
    opts = (spec.get("rig") or {}).get("rigid_head", True)
    opts = opts if isinstance(opts, dict) else {}
    co = opts.get("cover", True)
    if hf is None or co is False:
        return {}
    co = co if isinstance(co, dict) else {}
    reach, ease = float(co.get("reach", COVER_REACH)), float(co.get("ease", COVER_EASE))
    rounds = int(co.get("smooth", COVER_SMOOTH))
    defs = spec.get("parts") or {}
    if skin is None:
        sp = (spec.get("rig") or {}).get("skin_part") or ("body" if "body" in meshes else None)
        skin = {sp} | set((spec.get("face_shapes") or {}).get("parts") or ())
    kinds = {pn: _head_kind(spec, hf, pn, np.asarray(V, float), skin) for pn, (V, F) in meshes.items()
             if len(V) and len(F) and not (defs.get(pn) or {}).get("rig_bone")}
    worn = [pn for pn, k in kinds.items() if k == "worn"]
    if not worn:
        return {}
    A, B, C = (np.concatenate([np.asarray(meshes[pn][0], float)[np.asarray(meshes[pn][1])[:, j]] for pn in worn])
               for j in range(3))
    tree = cKDTree((A + B + C) / 3)
    out = {}
    for pn, k in kinds.items():
        if k != "skin":
            continue
        V, F = np.asarray(meshes[pn][0], float), np.asarray(meshes[pn][1])
        todo = np.flatnonzero(hf["h"](V) > 0)  # only where the head rule would act
        if not len(todo):
            continue
        # normals of the welded mesh (uv seams split vertices)
        _, inv = np.unique(np.round(V / 1e-5).astype(np.int64), axis=0, return_inverse=True)
        inv = inv.ravel()
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        N = np.zeros((inv.max() + 1, 3))
        for j in range(3):
            np.add.at(N, inv[F[:, j]], fn)
        N = (N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-30))[inv]
        kk = min(12, len(A))
        covered = np.zeros(len(V), bool)
        # a ray out along the normal, as points every 4 mm: covered when one of them lies on a worn surface (the
        # nearest point of the cover alone is its EDGE for skin just under a neckline, and off to the side)
        for t in np.arange(0.0, reach + 1e-9, 0.004):
            ia = todo[~covered[todo]]
            if not len(ia):
                break
            X = V[ia] + t * N[ia]
            d, c = tree.query(X, k=kk, distance_upper_bound=0.06)
            d, c = d.reshape(len(ia), kk), c.reshape(len(ia), kk)
            near = np.isfinite(d[:, 0])
            if not near.any():
                continue
            ia, X = ia[near], X[near]
            c = np.where(np.isfinite(d[near]), c[near], c[near][:, :1]).ravel()
            _, dist = _closest_on_triangles(np.repeat(X, kk, 0), A[c], B[c], C[c])
            covered[ia] = dist.reshape(len(ia), kk).min(1) < 0.003
        if not covered.any():
            continue
        w = covered.astype(float)
        if COVER_OUT and (~covered).any():  # the hand-over on the visible side: the skin at a neckline's edge stays
            # with the cloth it disappears under, and the long falloff starts `ease` above it
            dd, _ = cKDTree(V[covered]).query(V[~covered])
            w[~covered] = 1.0 - _ss(dd / max(ease, 1e-6))
        elif (~covered).any():
            dd, _ = cKDTree(V[~covered]).query(V[covered])
            w[covered] = _ss(dd / max(ease, 1e-6))
        if rounds > 0:  # smoothed over the welded mesh: the ray test is per vertex, so at a collar's top edge on a
            # 20k low poly (edges ~1.5 cm) the share stepped 0 -> 1 inside one triangle, and single vertices whose
            # ray grazed the cover read covered among visible ones. Garrett, Head turned 33 deg: 38 triangles
            # inside out at the nape and the throat's sides, all with a Head 0 and a Head ~1 corner -> 2.
            Fw = inv[F]
            e = np.r_[Fw[:, [0, 1]], Fw[:, [1, 2]], Fw[:, [2, 0]]]
            e = np.r_[e, e[:, ::-1]]
            n = int(inv.max()) + 1
            x = np.zeros(n)
            np.maximum.at(x, inv, w)
            deg = np.maximum(np.bincount(e[:, 0], minlength=n), 1)
            for _ in range(rounds):
                x = 0.5 * x + 0.5 * np.bincount(e[:, 0], weights=x[e[:, 1]], minlength=n) / deg
            w = x[inv]
        out[pn] = w
    return out


def drop_joints(rb: list[dict], names: list[str], what: str = "rig_drop") -> np.ndarray:
    """Which rig joints a list of names means (bool per joint): "LeftLeg" is that joint, "Leg" both sides', each
    with the twist joints of its segment; the prefix is optional. An unknown name raises, listing what there is."""
    import re

    def base(n):  # "mixamorig:LeftLegTwist1" -> ("Left", "Leg")
        n = re.sub(r"Twist\d+$", "", n[len(PREFIX):] if n.startswith(PREFIX) else n)
        m = re.match(r"(Left|Right)(.+)", n)
        return (m.group(1), m.group(2)) if m else ("", n)
    have = [base(b["name"]) for b in rb]
    gone = np.zeros(len(rb), bool)
    for nm in names:
        side, core = base(nm)
        hit = np.array([c == core and (not side or sd == side) for sd, c in have])
        if not hit.any():
            raise ValueError(f"{what}: no rig joint {nm!r} (have {', '.join(sorted({c for _, c in have}))}; "
                             f"prefix a side, e.g. \"LeftLeg\", for one side only)")
        gone |= hit
    return gone


ATTACH = 0.08  # m: the length over which a part hands over to the bound part it is attached to (parts.<p>.rig_attach)


# ---- the rigid head -----------------------------------------------------------------------------------------------
# A skull doesn't bend: riggers weight the whole head (cranium, face, jaw, and everything in it: eyes, teeth, tongue)
# 1.0 to the head joint and put the falloff to the neck on the throat, under the jawline. Distance-based weights
# don't: the chin hangs in front of the neck, as near the neck's and the clavicles' bones as the skull's (Garrett's
# chin was Head 0.42 / Neck 0.42 / shoulders 0.16 and followed a head turn half way; the goblin's 0.34 / 0.32 / 0.33).
# `head_field` says how much of the head a point is (1 = rigid); `_rigid_head` blends each vertex's weights toward
# Head by it. Three sources, in order:
#   landmarks  a GNM head's lm_chin / lm_jaw_*: the floor is the mandible's lower border from the chin back to the
#              jaw's angle, level behind it, dropped HEAD_UNDER (the soft skin under the chin moves with the jaw);
#   flesh      modelling prims: a point is head where the Head bone's flesh (skull, jaw, face kit) is no farther than
#              any other bone's; the falloff runs by how much farther it is;
#   generic    a base body without landmarks: the landmark floor at a typical head's proportions from the rig joints.
HEAD_BAND = 0.12   # the falloff's height below the floor, x the head's size (Head joint -> HeadTop_End): ~3 cm
HEAD_FALL = 0.44   # on a base body (a floor by height): the falloff's height, ~11 cm = the neck's length, as a rigger
#                    paints it (the head's weight fades down the whole neck; a narrow band is a hinge). With
#                    HEAD_NEAR, bare human (15k), Head alone: skin fold p99 / max at a 33 deg turn 24.7 / 159 ->
#                    9.7 / 26 deg, at a 25 deg nod 35.7 / 150 -> 14.1 / 31 (renders wc_throat_fall_gnm.png). Either one
#                    alone did half of it. History: at 3 cm a Head-only turn of 33 deg
#                    sheared the throat into a shelf under the jaw (skin fold p99 40 deg on the bare human, 20 on the
#                    golfer; at 5 cm 24 / 12, nod 56 -> 43). Longer on the FRONT only changed nothing: the fold is at
#                    the sides and the nape. spec.rig.rigid_head.band sets it in metres.
HEAD_OCCIPUT = 0.1  # x head size (neck joint -> head top, ~34 cm on a MakeHuman body) under the Head joint: the floor's
#                    height at the nape, the skull's base. Golfer, nod 25 deg Head-only: nape skin by the collar's top
#                    Head 0.98 -> 0.86, swung past the collar's back by +8.4 mm (38 vertices) -> -2.9 (none); shared with
#                    Neck -4.8 -> -11.5. Bare human folds unchanged (turn p99 11.7 -> 10.7, nod 14.5 -> 15.8). Higher
#                    (0.05, 0) clears more and folds the bare nape (nod p99 17-19, max 40-59); spec.rig.rigid_head.occiput
HEAD_BACK = 0.3    # x head size behind the Head joint where the floor reaches it
HEAD_NAPE = 1.0    # x the falloff's height at the nape (behind the Head joint); spec.rig.rigid_head.nape
HEAD_SHORT = 0.2   # the falloff's height outside the neck's column (what HEAD_FALL was): ~5 cm
HEAD_COLUMN = (0.36, 0.62)  # the neck's column: within 0.36 x head size (9 cm) of the Neck -> Head line the long
#                    falloff counts in full, past 0.62 (15.5 cm) not at all. (0.26, 0.46) cut into the neck's own
#                    sides (bare human turn p99 20 deg, a 127 deg crease); wider gains nothing and creases at 160.
HEAD_NEAR = 0.32   # on a base body: the band round face-shape vertices (`rigid_near`), ~8 cm (kit characters keep
#                    HEAD_BAND: a big jaw's field reaches the goblin's chest)
HEAD_UNDER = 0.04  # the floor's drop under the jaw's border, x the head's size: ~1 cm
HEAD_PART = 0.9    # a part this much head on average is all head (teeth, tongue, eyes, lashes, brows)
HEAD_WORN = 0.5    # a part other than the skin and less head than this is worn on the body: no head rule (a collar);
#                    parts.<p>.rig_head = true | false says so outright, spec.rig.skin_part names the skin ("body")
NEAR_SHORT = 0.375  # x rigid_near's band: within it the band counts in full, past it no more than the head field
MOVED = (5e-4, 3e-3)  # m: a vertex a face shape moves this far is a little / wholly the head's (`rigid_near`)


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def head_field(spec: dict, rb: list[dict]) -> dict | None:
    """{"h": f(points) -> 0..1 (1 = moves rigidly with the Head bone), "bone": Head's index, "band" (m), "how"}, or
    None (no Head bone, or spec["rig"]["rigid_head"] = false). spec["rig"]["rigid_head"] = {"band": m, "under": m}
    sets the falloff's height and the floor's drop."""
    opts = (spec.get("rig") or {}).get("rigid_head", True)
    names = [b["name"] for b in rb]
    if opts is False or PREFIX + "Head" not in names:
        return None
    opts = opts if isinstance(opts, dict) else {}
    hi = names.index(PREFIX + "Head")
    s = expand_mirror(spec)
    Jn = s["joints"]
    # sizes are counted from the modelling "neck" joint (the Head bone's own head on kit characters; a template's rig
    # hint may put Head higher)
    hj = _joint(s, "neck") if "neck" in Jn else rb[hi]["head"]
    top = rb[names.index(PREFIX + "HeadTop_End")]["head"] if PREFIX + "HeadTop_End" in names else hj + [0, 0, 0.25]
    size = max(float(np.linalg.norm(top - hj)), 1e-3)
    band = float(opts.get("band", HEAD_BAND * size))
    under = float(opts.get("under", HEAD_UNDER * size))
    fall = float(opts.get("fall", opts.get("band", HEAD_FALL * size)))
    nape = float(opts.get("nape", HEAD_NAPE))
    hy = float(rb[hi]["head"][1])
    col = opts.get("column", HEAD_COLUMN)
    hd = np.asarray(rb[hi]["head"], float)
    nk = np.asarray(rb[rb[hi]["parent"]]["head"], float) if rb[hi]["parent"] >= 0 else hd - [0, 0, 0.4 * size]
    if spec.get("base"):
        if "lm_chin" in Jn and "lm_jaw_4.L" in Jn:
            pts = [resolve_point(s, "lm_chin")] + [0.5 * (resolve_point(s, f"lm_jaw_{i}.L")
                                                          + resolve_point(s, f"lm_jaw_{i}.R") * [-1, 1, 1])
                                                   for i in (7, 6, 5, 4)]
            pts = np.array(pts)[:, 1:]  # (y, z): the jaw's border from the chin back to its angle
            how = "jaw landmarks"
        else:
            pts = np.array([[hj[1] - 0.65 * size, hj[2]], [hj[1] - 0.28 * size, hj[2] + 0.10 * size]])
            how = "generic (no jaw landmarks: typical proportions from the Head joint)"
        y0, z0, (y1, z1) = float(pts[:, 0].min()), float(pts[:, 1].min()), pts[-1]
        slope = (z1 - z0) / max(y1 - y0, 1e-6)
        z0 -= max(0.0, float(np.max(z0 + slope * (pts[:, 0] - y0) - pts[:, 1])))  # under every border point

        # behind the jaw's angle the floor climbs a little up the ramus and runs level from the Head joint back:
        # level at the jaw angle's own height, more of the nape under the skull was head than a skull covers.
        fy, fz = [y0, float(y1)], [z0, z0 + slope * (float(y1) - y0)]
        if how == "jaw landmarks" and "lm_jaw_3.L" in Jn:
            # one landmark up the ramus, reached at the Head joint: the ear lobes (the next landmark's height) stay
            # above it. Up to the Head joint itself (the skull's base on MakeHuman) the lobes fell in the band and
            # 30 triangles under each ear turned inside out at 33 deg.
            sy, sz = float(rb[hi]["head"][1]), float(resolve_point(s, "lm_jaw_3.L")[2]) - (float(z1) - fz[-1])
            if sz > fz[-1] and sy > fy[-1] + 0.01:
                fy.append(sy)
                fz.append(sz)

        # at the nape the floor climbs on to the skull's base (HEAD_OCCIPUT under the Head joint, reached HEAD_BACK
        # behind it): level at the jaw's height, the back of the neck down to its base was Head 1.0 and a nod swung
        # it 22-28 mm back and 40 up, out over a collar's stand (the golfer's lump of nape skin)
        occ = opts.get("occiput", HEAD_OCCIPUT)
        if occ is not None and occ is not False:
            by, bz = hy + HEAD_BACK * size, float(rb[hi]["head"][2]) - float(occ) * size
            if by > fy[-1] + 0.005 and bz > fz[-1]:
                fy.append(by)
                fz.append(bz)

        def h(V):
            V = np.asarray(V, np.float64)
            floor = np.interp(V[:, 1], fy, fz) - under
            back = _ss((V[:, 1] - hy) / (0.35 * size))  # 0 at the Head joint and in front, 1 at the nape
            long = 1.0 - _ss((floor - V[:, 2]) / (fall * (1.0 + (nape - 1.0) * back)))
            # the long falloff is the NECK's: by height alone it reached the tops of the shoulders (a 33 deg turn
            # moved trapezius skin 70 mm). Past the neck's column only the short one counts.
            tn = np.clip((V[:, 2] - nk[2]) / max(hd[2] - nk[2], 1e-6), -0.5, 1.5)
            r = np.linalg.norm(V[:, :2] - (nk[:2] + tn[:, None] * (hd[:2] - nk[:2])), axis=1)
            long *= 1.0 - _ss((r - col[0] * size) / ((col[1] - col[0]) * size))
            return np.maximum(long, short(V))

        def short(V):  # which PART is head or worn is judged on this one: under the long falloff a collar averaged
            V = np.asarray(V, np.float64)  # over 0.5 head, took the head rule and turned with the face (57 mm)
            return 1.0 - _ss((np.interp(V[:, 1], fy, fz) - under - V[:, 2]) / min(fall, HEAD_SHORT * size))
        return {"h": h, "part": short, "bone": hi, "band": float(opts.get("band", HEAD_NEAR * size)),
                "how": f"{how}, floor {under * 1e3:.0f} mm under the jaw"}
    ids, carry = _flesh_tree(spec, rb)
    if hi not in ids:
        return None
    n = list(ids).index(hi)

    def h(V):
        V = np.asarray(V, np.float64)
        D = [np.min([_flesh(p, c.get("cuts", ()), V) for p in c["prims"]], 0) for c in carry]
        rest = np.min([d for i, d in enumerate(D) if i != n], 0) if len(D) > 1 else np.full(len(V), np.inf)
        return 1.0 - _ss((D[n] - rest) / band)
    return {"h": h, "bone": hi, "band": band, "how": f"flesh ({len(carry[n]['prims'])} head primitives)"}


def _rigid_head(J: np.ndarray, W: np.ndarray, h: np.ndarray, bone: int):
    """Weights blended toward the head bone by h: (1 - h) x what they were + h on Head."""
    k = J.shape[1]
    h = np.clip(np.asarray(h, np.float64), 0.0, 1.0)
    h[h > 0.995] = 1.0
    if not (h > 0).any():
        return J, W
    J2 = np.concatenate([J, np.full((len(J), 1), bone, J.dtype)], 1)
    W2 = np.concatenate([W * (1 - h[:, None]), h[:, None]], 1)
    same = J == bone  # already among its bones: its weight joins the new slot
    W2[:, k] += (W2[:, :k] * same).sum(1)
    W2[:, :k][same] = 0.0
    order = np.argsort(-W2, axis=1, kind="stable")[:, :k]
    Jk = np.take_along_axis(J2, order, 1)
    Wk = np.take_along_axis(W2, order, 1)
    Wk /= np.maximum(Wk.sum(1, keepdims=True), 1e-12)
    Jk[Wk <= 0] = 0
    return Jk, Wk


def rigid_near(rb: list[dict], skins: dict, verts: dict, moved: dict, band: float | None = None,
               cover: dict | None = None, field=None) -> dict:
    """Everything a face shape moves is head too: {part: (J, W)} with every vertex some shape moves MOVED[1] or more
    (`moved`: {part: the largest move per vertex, m}) weighted 1.0 to Head, the vertices within `band` of one
    blended toward it, and vertices moved less (down to MOVED[0]) in proportion (the export, after the face shapes
    are made)."""
    from scipy.spatial import cKDTree
    names = [b["name"] for b in rb]
    if PREFIX + "Head" not in names or not moved:
        return skins
    hi = names.index(PREFIX + "Head")
    if band is None:
        top = rb[names.index(PREFIX + "HeadTop_End")]["head"] if PREFIX + "HeadTop_End" in names else None
        band = HEAD_BAND * (float(np.linalg.norm(top - rb[hi]["head"])) if top is not None else 0.25)
    lo, hi_ = MOVED
    full = {p: np.asarray(m, np.float64) >= hi_ for p, m in moved.items() if p in verts}
    pts = [np.asarray(verts[p], np.float64)[m] for p, m in full.items() if m.any()]
    tree = cKDTree(np.concatenate(pts)) if pts else None
    out = dict(skins)
    for pn, (J, W) in skins.items():
        if pn not in verts or pn not in moved:  # a part no shape moves is worn or a prop: a collar beside the
            # throat took Head 0.56 from the moved skin near it and turned with the face (26 mm off the shirt)
            continue
        h = np.zeros(len(verts[pn]))
        if tree is not None:
            d, _ = tree.query(np.asarray(verts[pn], np.float64), distance_upper_bound=band)
            d = np.where(np.isfinite(d), d, band)
            h = 1.0 - _ss(d / band)
            if field is not None:  # past NEAR_SHORT of the band the head field's own falloff rules: down the throat
                # the band reached past it (jawOpen moves throat skin 3 mm+ down to the Adam's apple; Garrett's
                # notch 2.5 cm under that was Head 0.80, field 0.38, v23 0.16: a 33 deg turn dragged it 25 mm)
                h = np.maximum(1.0 - _ss(d / (NEAR_SHORT * band)), np.minimum(h, field(verts[pn])))
            if cover and pn in cover:  # skin under a collar follows the collar (`skin_cover`), not the face near it
                h = h * (1.0 - cover[pn])
        if pn in moved:  # moved a little (skin sliding on the throat, a chest a big jaw's field reaches): a little
            h = np.maximum(h, _ss((np.asarray(moved[pn], np.float64) - lo) / (hi_ - lo)))
        if field is not None:  # h is the Head share wanted, not a second blend on top of the head rule skin_parts
            # applied (two blends of 0.38 made 0.62 at Garrett's notch)
            Wf = np.asarray(W, np.float64)
            cur = np.where(np.asarray(J) == hi, Wf, 0.0).sum(1)
            h = np.clip((h - cur) / np.maximum(1.0 - cur, 1e-9), 0.0, 1.0)
        if (h > 0).any():
            out[pn] = _rigid_head(np.asarray(J), np.asarray(W, np.float64), h, hi)
    return out


def head_check(bones: list[dict], V: np.ndarray, J: np.ndarray, W: np.ndarray, deg: float = 33.0) -> dict | None:
    """The head's test: its weights on the front of the face by height (rows of {"z", "rel" (height over the Head
    joint / the head's size), "head", "neck", "arms" (clavicles and arms), "lag_mm"}), where lag is how far a vertex
    ends from where a rigid head would put it with the Head bone turned `deg` about the vertical. A rigid face reads
    head 1.00 / lag 0 down to the jaw, and the falloff sits below."""
    names = [b["name"] for b in bones]
    if PREFIX + "Head" not in names or PREFIX + "HeadTop_End" not in names:
        return None
    hi = names.index(PREFIX + "Head")
    hj, top = bones[hi]["head"], bones[names.index(PREFIX + "HeadTop_End")]["head"]
    size = float(np.linalg.norm(top - hj))
    wh = (W * (J == hi)).sum(1)
    wn = (W * (J == names.index(PREFIX + "Neck"))).sum(1) if PREFIX + "Neck" in names else np.zeros(len(V))
    arms = [i for i, n in enumerate(names) if "Shoulder" in n or "Arm" in n]
    wa = (W * np.isin(J, arms)).sum(1)
    P = pose(bones, V, J, W, {PREFIX + "Head": ([0, 0, 1], deg)})
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    rigid = (V - hj) @ np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]).T + hj
    lag = np.linalg.norm(P - rigid, axis=1)
    front = (np.abs(V[:, 0] - hj[0]) < 0.25 * size) & (V[:, 1] < hj[1] - 0.15 * size)
    rows = []
    for rel in np.arange(-0.3, 0.55, 0.1):
        m = front & (np.abs(V[:, 2] - hj[2] - rel * size) < 0.05 * size)
        if m.sum() > 3:
            rows.append({"z": round(float(hj[2] + rel * size), 3), "rel": round(float(rel), 2),
                         "head": round(float(wh[m].mean()), 2), "neck": round(float(wn[m].mean()), 2),
                         "arms": round(float(wa[m].mean()), 2), "lag_mm": round(float(lag[m].mean() * 1e3), 1)})
    return {"deg": deg, "size": size, "rows": rows, "head_weight": wh, "lag": lag}


def report(spec: dict, bones: list[dict], V: np.ndarray, F: np.ndarray, J: np.ndarray, W: np.ndarray) -> list[str]:
    """The rig tool's numbers: each twist chain's test and the head's."""
    names = [b["name"] for b in bones]
    out = []
    tests = [("RightHand", 75.0), ("RightHand", 105.0), ("RightArm", 60.0), ("RightFoot", 40.0),
             ("RightUpLeg", 40.0)]
    tw = [b for b in bones if b.get("twist")]
    if PREFIX + "RightHand" in names:
        out.append("twist tests (a driver rolled about its limb; twist = how far the skin has turned by station "
                   "along the segment, joint to joint; area = the worst cross-section against rest):")
        for drv, deg in tests:
            if PREFIX + drv not in names:
                continue
            chain = [b for b in tw if b["twist"]["driver"] == PREFIX + drv]
            for drive in ((True, False) if chain and drv == "RightHand" and deg == 75.0 else (bool(chain),)):
                r = twist_check(bones, V, F, J, W, PREFIX + drv, deg, drive)
                if not r["twist"]:
                    continue
                follow = drv.endswith(ROLL_OF_PARENT)
                left = r["at_end"] if follow else r["at_start"]
                where = ("the wrist" if "Hand" in drv else "the ankle") if follow else \
                    ("the shoulder" if "Arm" in drv else "the hip")
                kind = f"{len(chain)} twist bones driven" if drive else \
                    ("twist bones NOT driven" if chain else "no twist bones")
                bad = " <- CANDY WRAPPER" if r["area_min"] < 0.8 or (r["step"] or 0) > 0.6 * deg else ""
                out.append(f"  {drv} {deg:g} deg, {kind}: twist {' '.join(f'{x:.0f}' for x in r['twist'])}; "
                           f"{abs(left) if follow else abs(left):.0f} deg {'left at' if follow else 'turned at'} "
                           f"{where}, largest step {r['step']:.0f} deg, area min {r['area_min']:.2f}, triangle "
                           f"quality against rest: worst 1% {r['tri_p1']:.2f}, worst {r['tri_min']:.2f}{bad}")
    hc = head_check(bones, V, J, W)
    if hc:
        hf = head_field(spec, bones)
        out.append(f"head (rigid by {hf['how'] if hf else 'nothing: rig.rigid_head is off'}); front of the face by "
                   f"height over the Head joint, Head turned {hc['deg']:g} deg:")
        out += [f"  {r['rel']:+.1f} head (z {r['z']:.3f}): Head {r['head']:.2f} Neck {r['neck']:.2f} "
                f"clavicles/arms {r['arms']:.2f}, {r['lag_mm']:.1f} mm behind a rigid head" for r in hc["rows"]]
    return out


def skin_mesh(spec: dict, rb: list[dict], V: np.ndarray, F: np.ndarray, part: np.ndarray, part_names,
              smooth: int = SMOOTH) -> tuple[np.ndarray, np.ndarray]:
    """(J, W) for a built model's one mesh (store.build's verts / faces / per-vertex part), skinned part by part as
    the export does (`skin_parts`)."""
    J, W = np.zeros((len(V), 4), int), np.zeros((len(V), 4))
    fp = part[F[:, 0]]
    meshes = {}
    for i, pn in enumerate(part_names):
        sel = np.flatnonzero(part == i)
        if len(sel):
            rm = np.full(len(V), -1)
            rm[sel] = np.arange(len(sel))
            meshes[str(pn)] = (V[sel], rm[F[fp == i]], sel)
    for pn, (Jp, Wp) in skin_parts(spec, rb, {k: v[:2] for k, v in meshes.items()}, smooth).items():
        J[meshes[pn][2]], W[meshes[pn][2]] = Jp, Wp
    return J, W


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
        if b["parent"] >= 0 and not b.get("twist"):
            kids.setdefault(b["parent"], []).append(i)
    seg = {}
    for i, b in enumerate(rb):
        if b["end"] or b.get("noweight") or b.get("twist"):  # twist bones take their share after (_spread_twist)
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
    """The part of a bone's cone between t0 and t1 along it (a -> b, radii interpolated): a rig bone's own flesh where
    it lies along the modelling bone. The skeleton walk can reach a bone from its far end (the goblin's arms, from
    the hand), so a -> b may run against the cone's own axis: the piece is laid along the cone's axis either way."""
    import copy
    q = copy.copy(p)
    pr = dict(p.params)
    L = pr["len"]
    ra, rb = pr["ra"], pr["rb"]
    if np.linalg.norm(a - pr["a"]) > np.linalg.norm(b - pr["a"]):  # reached from the cone's far end
        t0, t1 = 1.0 - t1, 1.0 - t0
    ax = pr["frame"][1]
    s, e = pr["a"] + t0 * L * ax, pr["a"] + t1 * L * ax
    pr["a"] = s
    pr["len"] = max((t1 - t0) * L, 1e-4)
    pr["ra"], pr["rb"] = ra + t0 * (rb - ra), ra + t1 * (rb - ra)
    pr["cut"] = 0.0
    q.params = pr
    q.lo, q.hi = np.minimum(s, e) - max(ra, rb) * 2, np.maximum(s, e) + max(ra, rb) * 2
    return q


def rig_weights(spec: dict, rb: list[dict], verts: np.ndarray, faces: np.ndarray | None = None,
                k: int = 4, smooth: int = SMOOTH) -> tuple[np.ndarray, np.ndarray]:
    """Skin weights on the rig bones. Each rig bone gets flesh of its own from the modelling geometry: the piece
    of every modelling cone it lies along (Spine, Spine1, Spine2 split the one spine cone), modelling bones lying
    inside its segment (a finger's pieces), and the rest of the modelling bones (a tusk, an ear, a collar) with
    go to the rig bone nearest their middle, blobs to the rig bone nearest their middle; a rig bone left with none (a hand, the toes) gets a cone
    along its own segment. Then `weights` on the rig tree: nearest-flesh distances, family-limited, smoothed. Then
    the twist chains take their segments' weight (`_spread_twist`)."""
    ids, carry = _flesh_tree(spec, rb)
    J, W = weights(carry, verts, faces, k=k, smooth=smooth)
    return _spread_twist(rb, verts, np.asarray(ids)[J], W, k)


def _flesh_tree(spec: dict, rb: list[dict]):
    """(rig bone indices, [{"name", "parent", "prims", "prim", "cuts"}]): the weight-carrying rig bones with their
    flesh, as `weights` takes them."""
    seg = _segments(rb)
    ids = list(seg)
    A = np.array([seg[i][0] for i in ids])
    B = np.array([seg[i][1] for i in ids])
    flesh = {i: [] for i in ids}
    base_r = None
    if spec.get("base"):  # a base body has no modelling bones (its bones are clothes, straps): each rig bone's
        # flesh is a cone along its own segment as thick as the base body there (the median distance of the base's
        # vertices that lie nearest it), measured once, so every part (skin, shirt, shoes) gets the same weights
        from . import base as basemod
        from .spec import expand_mirror as _em
        s = basemod.inject(_em(spec))
        W = np.asarray(basemod.surface(s, spec["base"])["quads"][0], float)
        D = np.stack([_seg_dist(W, A[q], B[q]) for q in range(len(ids))], 1)
        near = D.argmin(1)
        base_r = np.array([float(np.median(D[near == q, q])) if (near == q).sum() > 3 else np.nan
                           for q in range(len(ids))])
        mb = []
    else:
        mb = skeleton(spec)
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
        if inside:  # a curled finger's pieces find their phalanx
            flesh[ids[inside[0]]].append(p)
            continue
        # else each quarter of it goes to the rig bone nearest that quarter's middle: a tusk is all the head's, but a
        # sheet from the ribs to the arm (a lat) blends from the chest to the arm instead of dragging the ribs along
        near = [int(np.argmin(_seg_dist(h + (k + 0.5) / 4 * (t - h), A, B))) for k in range(4)]
        if len(set(near)) == 1:
            flesh[ids[near[0]]].append(p)
        else:
            for k, q in enumerate(near):
                flesh[ids[q]].append(_cone_piece(p, h, t, k / 4, (k + 1) / 4))
    for q, i in enumerate(ids):  # nothing of its own: a cone along its segment, as thick as its neighbours
        if not flesh[i]:
            have = [n for n, j in enumerate(ids) if any(x.kind == "cone" and "rb" in x.params for x in flesh[j])]
            nq = min(have, key=lambda n: float(_seg_dist(A[q], A[n], B[n]))) if have else None
            ref = next(x for x in flesh[ids[nq]] if x.kind == "cone" and "rb" in x.params) if nq is not None else None
            r = 0.4 * (min(ref.params["ra"], ref.params["rb"]) if ref is not None else 0.03)
            if base_r is not None and np.isfinite(base_r[q]):
                r = 0.8 * float(base_r[q])
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
    for n, i in enumerate(ids):  # where a chain continues through a joint, parent and child flesh meet at the plane
        pn = carry[n]["parent"]  # bisecting the two bones (the elbow's crease), so a collar's round end doesn't
        if pn < 0:  # reach over the top of the upper arm
            continue
        (a0, a1), (b0, b1) = seg[ids[pn]], seg[i]
        la, lb = np.linalg.norm(a1 - a0), np.linalg.norm(b1 - b0)
        if la < 1e-3 or lb < 1e-3 or np.linalg.norm(a1 - b0) > 1e-6:
            continue
        if carry[pn]["prim"].name == carry[n]["prim"].name:  # pieces of one cone (the spine) keep blending softly
            continue
        nrm = (a1 - a0) / la + (b1 - b0) / lb
        if np.linalg.norm(nrm) < 1e-6:
            continue
        nrm /= np.linalg.norm(nrm)
        carry[pn].setdefault("cuts", []).append((b0, nrm))
        carry[n].setdefault("cuts", []).append((b0, -nrm))
    for c in carry:
        if "ra" not in c["prim"].params:  # a blob-only bone: its falloff from the blob's size
            sz = float(np.min(c["prim"].hi - c["prim"].lo)) / 2
            c["falloff_r"] = sz
    return ids, carry


