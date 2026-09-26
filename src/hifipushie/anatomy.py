"""Anatomy: modelling lore applied by joint type, instead of a kit per body part.

spec["anatomy"] = {} turns it on; entries override per joint: {"shoulder.L": {"bulk": 1.3, "back": 0}, "hip.L":
{"off": true}}. It expands after kits (fingers exist, seating sees them) and before strokes and mirroring, into
ordinary joints and bones named "<joint base>_<piece><sfx>" (shoulder_cap0.L, hip_front.L, ...), so strokes, paint,
measure and the rig see plain elements.

Limb root: where a limb (a side chain of two bones or more) leaves the body: the shoulder, the hip, a fox's
shoulder. Found by walking each side chain in from its free end: the root is the joint next to a centre-line hub
(the troll's collar runs from the chest to the shoulder) or the chain's inner end (a hip with no bone to the
pelvis). A limb isn't plugged into the body; masses from the body cross the joint and insert on the limb:
  cap: a thick curved shell over the joint's outer side (a bowed, flattened bone) from above the joint to its
       insertion part-way down the limb (the deltoid; at a hip, the glute's flare);
  front, back: for a limb hanging beside the body (s > 0, an arm), sheets from the body's surface to the inner
       front and back of the limb's root (pec and lat), whose lower edges make the folds that frame the pit; for a
       limb leaving the body's end (s < 0, a leg), no front sheet (the groin is a fold) and behind, a round belly
       bowed back from above the joint to the back of the limb (the glute; a quadruped's triceps). The cap is
       smaller there (0.5).
The frame is the limb's direction d, "out" (away from the body's centre joint, across the limb) and "front" (-Y
across both). Beside the body (s = 1: the limb runs back along the body from the end it's rooted at, an arm, held out or
not) or leaving its end (s = -1: a leg, a quadruped's legs under a level spine), from the limb's direction against
the body's axis at the root (the hub's thickest centre-line neighbour to the hub). Sizes follow the limb's radius r at the root.
Root params: "off", "bulk" (all sizes, 1), "cap" (1), "insert" (where the cap inserts, fraction of the first bone,
0.45), "front" (1), "back" (1), "blend" (x r, 0.4), "narrow" (the bones' radius at the joint, x r: 0.8), "part"
(the generated masses in a part of their own, to look at them).
"""

from __future__ import annotations

import copy
import hashlib
import json

import numpy as np

from .kits import KitError, _Out, _Surface, _base, _r, _unit

CENTRE = 0.25  # a joint is on the centre line within this fraction of its radius of x = 0

_CACHE: dict[str, dict] = {}


def expand(spec: dict) -> dict:
    """spec with its anatomy expanded into joints and bones (cached by content, strokes aside)."""
    if "anatomy" not in spec:
        return spec
    bare = {k: v for k, v in spec.items() if k != "strokes"}
    key = hashlib.sha1(json.dumps(bare, sort_keys=True, default=float).encode()).hexdigest()
    if key not in _CACHE:
        if len(_CACHE) > 32:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = _expand(bare)
    out = copy.deepcopy(_CACHE[key])
    if "strokes" in spec:
        out["strokes"] = copy.deepcopy(spec["strokes"])
    return out


def _pos(spec, j):
    return np.array(spec["joints"][j]["pos"], float)


def _rad(spec, j):
    return float(spec["joints"][j].get("r", 0.05))


def limb_roots(spec: dict) -> list[dict]:
    """[{"joint", "next" (the limb's first bone's far joint), "bone", "centre" (the body's joint it leaves),
    "chain" (root to free end)}] for every side limb (".L" or unsuffixed off the centre line)."""
    J = spec.get("joints", {})
    adj: dict = {}
    for n, b in spec.get("bones", {}).items():
        if b.get("op", "add") != "add" or b.get("group") or b.get("part", "body") != "body":
            continue
        if b["a"] not in J or b["b"] not in J or "pos" not in J[b["a"]] or "pos" not in J[b["b"]]:
            continue
        adj.setdefault(b["a"], []).append((n, b["b"]))
        adj.setdefault(b["b"], []).append((n, b["a"]))
    centre = {j for j in adj if abs(_pos(spec, j)[0]) < CENTRE * _rad(spec, j)}
    out = []
    for leaf, nb in adj.items():
        if len(nb) != 1 or leaf in centre:
            continue
        path, prev = [leaf], None
        cur = leaf
        while True:  # inward while the chain doesn't branch
            nxt = [o for _, o in adj[cur] if o != prev]
            if len(nxt) != 1:
                break
            prev, cur = cur, nxt[0]
            path.append(cur)
            if len(adj[cur]) != 2 or cur in centre:
                break
        # the root: next to a centre-line hub, or the chain's inner end; a chain free at both ends (a hip with no
        # bone to the pelvis) is walked from its end farther from the centre line only
        if path[-1] not in centre and len(adj[path[-1]]) == 1:
            dist = lambda q: min((np.linalg.norm(_pos(spec, q) - _pos(spec, c)) for c in centre), default=0.0)
            if dist(leaf) < dist(path[-1]):
                continue
        root = path[-2] if path[-1] in centre and len(path) >= 2 else path[-1]
        k = path.index(root)
        if k < 2 or root in centre:  # a limb has two bones or more (not an ear or a tusk)
            continue
        cs = [c for c in centre]
        inner = path[k + 1] if k + 1 < len(path) else None
        C = inner if inner in centre else min(cs, key=lambda c: np.linalg.norm(_pos(spec, c) - _pos(spec, root))) \
            if cs else None
        if C is None:
            continue
        bone = next(n for n, o in adj[root] if o == path[k - 1])
        out.append({"joint": root, "next": path[k - 1], "bone": bone, "centre": C, "chain": path[k::-1]})
    return sorted(out, key=lambda r: r["joint"])


def _expand(spec: dict) -> dict:
    conf = spec.get("anatomy") or {}
    out = copy.deepcopy(spec)
    out.pop("anatomy")
    base = copy.deepcopy(out)
    from .strokes import without_seated
    surf = _Surface(without_seated(base))
    for root in limb_roots(out):
        p = {**{k: v for k, v in conf.items() if not isinstance(v, dict)}, **conf.get(root["joint"], {})}
        if p.get("off"):
            continue
        o = _Out(out, f"anatomy {root['joint']}")
        _limb_root(out, surf, root, p, o)
        for kind in ("joints", "bones"):
            out.setdefault(kind, {}).update(getattr(o, kind))
    return out


def _exit(surf: _Surface, q: np.ndarray, direction: np.ndarray, reach: float = 0.6):
    """Where a ray from q (inside the body) along direction leaves it, and the normal there: the body's own surface
    at that spot. Seating from outside (surf.seat) landed on whatever lay in front: the fox's glute on its tail."""
    from . import sdf
    ts = np.linspace(0.0, reach, 600)
    f = sdf.field_at(surf.prims, q + ts[:, None] * direction)
    if f[0] >= 0:  # q isn't inside: the first surface met coming in
        try:
            return surf.seat(q, direction, "anatomy")
        except KitError:
            return None
    out = np.flatnonzero(f >= 0)
    if not len(out):
        return None
    lo, hi = ts[out[0] - 1], ts[out[0]]
    for _ in range(30):
        mid = (lo + hi) / 2
        if sdf.field_at(surf.prims, (q + mid * direction)[None])[0] < 0:
            lo = mid
        else:
            hi = mid
    x = q + hi * direction
    return x, _unit(sdf.gradient(surf.prims, x[None], 1e-4)[0])


def _limb_root(spec: dict, surf: _Surface, root: dict, p: dict, o: _Out):
    j = root["joint"]
    b, sfx = _base(j)
    J, N, C = _pos(spec, j), _pos(spec, root["next"]), _pos(spec, root["centre"])
    bone = spec["bones"][root["bone"]]
    a_end = bone["a"] == j
    r = float(bone.get("r_a" if a_end else "r_b") or _rad(spec, j))
    L1 = float(np.linalg.norm(N - J))
    d = _unit(N - J)
    out = J - C
    out = _unit(out - d * (out @ d))
    front = np.cross(d, out)
    front = _unit(front if front @ [0, -1, 0] >= 0 else -front)
    # beside the body (an arm: it runs back along the body from the end it's rooted at) or leaving the body's end (a
    # leg; a quadruped's legs, across a level spine). The body's end direction at the root: from the hub's thickest
    # centre-line neighbour (the torso's other end) to the hub. s = 1 beside, -1 leaving
    nb = [bb["b"] if bb["a"] == root["centre"] else bb["a"] for bb in spec["bones"].values()
          if root["centre"] in (bb["a"], bb["b"]) and bb.get("op", "add") == "add" and not bb.get("group")]
    nb = [q for q in nb if q in spec["joints"] and "pos" in spec["joints"][q] and abs(_pos(spec, q)[0]) < 0.25 * _rad(spec, q)]
    end = _unit(C - _pos(spec, max(nb, key=lambda q: _rad(spec, q)))) if nb else -d
    s = 1.0 if d @ end < -0.5 else -1.0
    # a limb hanging beside the body (an arm) is framed by sheets of like weight in front and behind (pec, lat); a
    # limb leaving the body's end (a leg, a quadruped's leg) is driven from behind: the back mass dominates (glute,
    # triceps), the front is only a fold, the side cap is smaller
    p = {**({} if s > 0 else {"cap": 0.5, "front": 0.0, "back": 1.0}), **p}
    bulk = float(p.get("bulk", 1.0))
    k = float(p.get("blend", 0.4)) * r
    part = p.get("part") or bone.get("part")  # "part": show the generated masses as their own mesh (debugging)
    extra = {"part": part} if part else {}

    # the joint itself slims to bone size: the limb's first bone and the body's bone arriving at the joint (a collar)
    # end narrow there, so the round ball their caps made is gone and the masses below carry the shoulder
    narrow = float(p.get("narrow", 0.8))
    if narrow < 1:
        for bn, bb in spec["bones"].items():
            if bb.get("op", "add") == "add" and not bb.get("group") and j in (bb["a"], bb["b"]) and \
                    bb.get("part", "body") == bone.get("part", "body"):
                end = "r_a" if bb["a"] == j else "r_b"
                bb[end] = round(narrow * float(bb.get(end) or _rad(spec, j)), 5)

    # cap: one thick curved shell over the joint's outer side (a bowed, flattened bone: wide around the limb, thin
    # across it), from above the joint to its insertion down the limb; separate heads read as lumps
    cap = float(p.get("cap", 1.0)) * bulk
    if cap > 0:
        O = J - d * 0.05 * r + out * 0.1 * r  # thin where it starts, under the body's mass at the joint
        I = J + d * float(p.get("insert", 0.45)) * L1 + out * 0.25 * r  # sinks into the limb: no ledge at its end
        o.joint(f"{b}_cap_o{sfx}", O, 0.55 * r * cap)
        o.joint(f"{b}_cap_i{sfx}", I, 0.15 * r * cap)
        o.bone(f"{b}_cap{sfx}", f"{b}_cap_o{sfx}", f"{b}_cap_i{sfx}", flat=[1.2, 0.7], up=_r(out),
               bow=[0.0, round(0.4 * r, 5)], blend=round(2.0 * k, 5), **extra)

    # front and back sheets: from the body's surface to the limb's inner front and back
    # the sheets end on the limb's inner side (into the pit), not its front and back: bridging to the back of an arm
    # held out from a narrow body stood off it as a fin
    for side, sign, default_at, ins in (("front", 1.0, 0.0, (0.2, 0.3, -0.45)), ("back", -1.0, 0.9, (0.18, 0.3, -0.5))):
        size = float(p.get(side, 1.0)) * bulk
        if size <= 0:
            continue
        round_back = s < 0 and side == "back"
        if round_back:  # its origin by the sacrum, off the midline (a cleft between the two), not far above the joint
            default_at = 0.3
        Q = C + (J - C) * (0.65 if round_back else 0.45) + s * d * float(p.get(f"{side}_drop", default_at)) * r
        got = _exit(surf, Q, sign * front)
        if got is None:
            continue
        hit, n = got
        if round_back:  # the driving mass behind a limb leaving the body's end: a round belly
            ra, rb = 0.6 * r * size, 0.35 * r * size
            O = hit - n * 0.7 * ra
            I = J + d * 0.35 * L1 - front * 0.5 * r
            o.joint(f"{b}_{side}_o{sfx}", O, ra)
            o.joint(f"{b}_{side}_i{sfx}", I, rb)
            o.bone(f"{b}_{side}{sfx}", f"{b}_{side}_o{sfx}", f"{b}_{side}_i{sfx}", flat=[1.0, 0.8], up=_r(-front),
                   bow=[0.0, round(0.45 * r, 5)], blend=round(2.0 * k, 5), **extra)
            continue
        ra, rb, flat = 1.0 * r * size, 0.35 * r * size, 0.3
        O = hit - n * 0.5 * ra * flat
        I = J + d * ins[0] * L1 + sign * front * ins[1] * r + out * ins[2] * r
        o.joint(f"{b}_{side}_o{sfx}", O, ra)
        o.joint(f"{b}_{side}_i{sfx}", I, rb)
        o.bone(f"{b}_{side}{sfx}", f"{b}_{side}_o{sfx}", f"{b}_{side}_i{sfx}", flat=[1.0, flat], up=_r(n),
               blend=round(2.0 * k, 5), **extra)
