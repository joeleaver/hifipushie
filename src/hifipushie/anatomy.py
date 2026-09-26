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
Hinge: every joint inside a limb's chain (elbow, knee, ankle; a fox's hock). A bony point sits on the extensor side,
the convex side of the rest bend in the body's plane of front and back (mammal limbs flex there; an arm hanging out
from the body bends sideways at rest, which isn't flexion): the olecranon, the kneecap, the heel. It's close under
the skin: small, crisp (a small blend). The limb's bones slim at the joint (flesh thins over joints). A straight limb
has no side to put it on: none, unless "point" gives the direction.
A limb's bones are joined in one group ("join", x the thinnest hinge's radius: 0.15, a root param) and blended into
the body once: blended one by one they swell all round every joint.
Hinge params: "off", "point" ([x, y, z] extensor side), "size" (1), "narrow" (0.9).
Digits: a fan of digit chains on one mass (the hand and foot kits' "<kit>_f1.L" ... chains, "<kit>_th.L" the opposed
thumb): a crisp knuckle on the back of each digit's root (the metacarpal heads) and smaller ones at its joints; a web
between neighbouring digits on the palm side, a third of the way up the first bone; a pad across the palm before
the roots; a pad at the opposed digit's base. The palm side is where the digits curl. Params under the kit's name
({"hand.L": {...}}): "off", "knuckles", "webs", "pads" (sizes, 1).
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
    for fan in digit_fans(out):
        fp = conf.get(fan["kit"], {})
        if not fp.get("off"):
            o = _Out(out, f"anatomy {fan['kit']}")
            _digits(out, fan, {**{k: v for k, v in conf.items() if k == "part"}, **fp}, o)
            for kind in ("joints", "bones", "blobs"):
                out.setdefault(kind, {}).update(getattr(o, kind))
    for root in limb_roots(out):
        p = {**{k: v for k, v in conf.items() if not isinstance(v, dict)}, **conf.get(root["joint"], {})}
        if p.get("off"):
            continue
        o = _Out(out, f"anatomy {root['joint']}")
        _limb_root(out, surf, root, p, o)
        _one_form(out, root, conf.get(root["joint"], {}))
        for i in range(1, len(root["chain"]) - 1):
            h = root["chain"][i]
            hp = {**{k: v for k, v in conf.items() if not isinstance(v, dict) and k in ("part",)}, **conf.get(h, {})}
            if not hp.get("off"):
                _hinge(out, root["chain"][i - 1], h, root["chain"][i + 1], hp, o)
        for kind in ("joints", "bones"):
            out.setdefault(kind, {}).update(getattr(o, kind))
    return out


def loop_planes(spec: dict) -> list[dict]:
    """Where a deforming mesh wants its edge loops, from the same lore: [{"label", "joint", "point", "normal", "r"}].
    A limb root's loop is the plane through three landmarks the rule places: over the joint (the top of the cap),
    the front pit and the back pit (armpit folds; at a hip the groin and the glute fold), so it runs the way an
    armhole runs. A hinge's is the plane bisecting its two bones (the crease). spec: kit-expanded, as limb_roots."""
    out = []
    for root in limb_roots(spec):
        j = root["joint"]
        J, N, C = _pos(spec, j), _pos(spec, root["next"]), _pos(spec, root["centre"])
        r = _rad(spec, j)
        L1 = float(np.linalg.norm(N - J))
        d = _unit(N - J)
        o_ = J - C
        o_ = _unit(o_ - d * (o_ @ d))
        fr = np.cross(d, o_)
        fr = _unit(fr if fr @ [0, -1, 0] >= 0 else -fr)
        top = J - d * 0.3 * r + o_ * 0.6 * r
        beside = _beside(spec, root, d)
        pf = J + d * (0.2 if beside else 0.15) * L1 + fr * 0.3 * r - o_ * 0.5 * r
        pb = J + d * (0.18 if beside else 0.35) * L1 - fr * 0.3 * r - o_ * 0.5 * r
        nrm = np.cross(pf - top, pb - top)
        nrm = _unit(nrm if nrm @ d >= 0 else -nrm)
        out.append({"label": j, "joint": j, "point": (top + pf + pb) / 3, "normal": nrm, "r": r})
        ch = root["chain"]
        for i in range(1, len(ch) - 1):
            A, K, Cc = _pos(spec, ch[i - 1]), _pos(spec, ch[i]), _pos(spec, ch[i + 1])
            nrm = _unit(_unit(K - A) + _unit(Cc - K))
            out.append({"label": ch[i], "joint": ch[i], "point": K, "normal": nrm, "r": _rad(spec, ch[i])})
    return out


def _beside(spec: dict, root: dict, d: np.ndarray) -> bool:
    """A limb hanging beside the body (an arm) rather than leaving the body's end (a leg): see _limb_root."""
    C = _pos(spec, root["centre"])
    nb = [bb["b"] if bb["a"] == root["centre"] else bb["a"] for bb in spec["bones"].values()
          if root["centre"] in (bb["a"], bb["b"]) and bb.get("op", "add") == "add" and not bb.get("group")]
    nb = [q for q in nb if q in spec["joints"] and "pos" in spec["joints"][q] and abs(_pos(spec, q)[0]) < CENTRE * _rad(spec, q)]
    end = _unit(C - _pos(spec, max(nb, key=lambda q: _rad(spec, q)))) if nb else -d
    return bool(d @ end < -0.5)


def digit_fans(spec: dict) -> list[dict]:
    """[{"kit": "hand.L", "digits": [[root, k1, k2, ..., tip] joint names, across the fan], "thumb": [...] | None}]
    from the kits' digit chains (joints <prefix>_0<sfx> .. <prefix>_N<sfx>)."""
    import re
    J = spec.get("joints", {})
    chains: dict = {}
    for n in J:
        m = re.fullmatch(r"(.+?)_(f\d+|t\d+|th)_(\d+)(\.L|\.R)?", n)
        if m:
            chains.setdefault((m[1], m[2], m[4] or ""), {})[int(m[3])] = n
    fans: dict = {}
    for (base, dig, sfx), js in chains.items():
        if 0 not in js or len(js) < 3:
            continue
        seq = [js[k] for k in sorted(js)]
        f = fans.setdefault((base, sfx), {"kit": base + sfx, "digits": [], "thumb": None})
        if dig == "th":
            f["thumb"] = seq
        else:
            f["digits"].append((int(dig[1:]), seq))
    out = []
    for f in fans.values():
        if len(f["digits"]) >= 2:
            f["digits"] = [seq for _, seq in sorted(f["digits"])]
            out.append(f)
    return out


def _digits(spec: dict, fan: dict, p: dict, o: _Out):
    kit, digits = fan["kit"], fan["digits"]
    b, sfx = _base(kit)
    part = p.get("part")
    extra = {"part": part} if part else {}
    P = lambda j: _pos(spec, j)
    flex = []
    for seq in digits + ([fan["thumb"]] if fan["thumb"] else []):
        d0, d1 = _unit(P(seq[1]) - P(seq[0])), _unit(P(seq[-1]) - P(seq[-2]))
        f = d1 - d0 * (d1 @ d0)
        flex.append(f)
    n = _unit(sum(flex[:len(digits)]))  # the palm side: where the digits curl, on average
    kn, wb, pd = (float(p.get(key, 1.0)) for key in ("knuckles", "webs", "pads"))
    for i, seq in enumerate(digits + ([fan["thumb"]] if fan["thumb"] else [])):
        r0 = _rad(spec, seq[0])
        d = _unit(P(seq[1]) - P(seq[0]))
        e = _unit(-(n - d * (n @ d)))  # the back of the digit
        tag = seq[0].rsplit("_", 1)[0].removesuffix(sfx)
        for k, j in enumerate(seq[:-1]):  # the root's knuckle, then smaller ones at the digit's joints
            if kn <= 0:
                continue
            rj = _rad(spec, j)
            scale = (0.55 if k == 0 else 0.4) * kn
            dj = _unit(P(seq[k + 1]) - P(j))
            ej = _unit(e - dj * (e @ dj))
            o.joint(f"{tag}_kn{k}a{sfx}", P(j) + ej * 0.55 * rj - dj * 0.1 * rj, scale * rj)
            o.joint(f"{tag}_kn{k}b{sfx}", P(j) + ej * 0.55 * rj + dj * 0.25 * rj, 0.8 * scale * rj)
            o.bone(f"{tag}_kn{k}{sfx}", f"{tag}_kn{k}a{sfx}", f"{tag}_kn{k}b{sfx}", flat=[1.0, 0.7], up=_r(ej),
                   blend=round(0.25 * rj, 5), **extra)
    if wb > 0:
        for i in range(len(digits) - 1):
            A, B = digits[i], digits[i + 1]
            ra, rb = _rad(spec, A[0]), _rad(spec, B[0])
            m0 = 0.5 * (P(A[0]) + P(B[0])) + n * 0.25 * (ra + rb)
            m1 = 0.5 * (P(A[0]) + 0.3 * (P(A[1]) - P(A[0])) + P(B[0]) + 0.3 * (P(B[1]) - P(B[0]))) + n * 0.2 * (ra + rb)
            w = 0.5 * np.linalg.norm(P(A[0]) - P(B[0]))
            o.joint(f"{b}_web{i}a{sfx}", m0, w * wb)
            o.joint(f"{b}_web{i}b{sfx}", m1, 0.7 * w * wb)
            o.bone(f"{b}_web{i}{sfx}", f"{b}_web{i}a{sfx}", f"{b}_web{i}b{sfx}", flat=[1.0, 0.35], up=_r(n),
                   blend=round(0.3 * min(ra, rb), 5), **extra)
    if pd > 0:
        first, last = digits[0], digits[-1]
        back = _unit(sum(_unit(P(sq[0]) - P(sq[1])) for sq in digits))  # toward the wrist
        r = np.mean([_rad(spec, sq[0]) for sq in digits])
        o.joint(f"{b}_pad_a{sfx}", P(first[0]) + back * 0.6 * r + n * 0.45 * r, 0.6 * r * pd)
        o.joint(f"{b}_pad_b{sfx}", P(last[0]) + back * 0.6 * r + n * 0.45 * r, 0.55 * r * pd)
        o.bone(f"{b}_pad{sfx}", f"{b}_pad_a{sfx}", f"{b}_pad_b{sfx}", flat=[1.0, 0.6], up=_r(n),
               blend=round(0.6 * r, 5), **extra)
        if fan["thumb"]:
            th = fan["thumb"]
            rt = _rad(spec, th[0])
            base = P(th[0]) + (P(th[0]) - P(th[1])) * 0.3 + n * 0.5 * rt
            o.joint(f"{b}_thenar_a{sfx}", base, 0.8 * rt * pd)
            o.joint(f"{b}_thenar_b{sfx}", P(th[1]) + n * 0.35 * rt, 0.55 * rt * pd)
            o.bone(f"{b}_thenar{sfx}", f"{b}_thenar_a{sfx}", f"{b}_thenar_b{sfx}", flat=[1.0, 0.7], up=_r(n),
                   blend=round(0.6 * rt, 5), **extra)


def _one_form(spec: dict, root: dict, p: dict):
    """A limb is one continuous form: its bones joined in a group (small join) and blended into the body once. Blended
    one by one, two cones overlapping at a joint swell all round it (the smooth minimum adds where they coincide)."""
    ch = root["chain"]
    names = [n for n, bb in spec["bones"].items() if bb.get("op", "add") == "add" and not bb.get("group")
             and any({bb["a"], bb["b"]} == {ch[i], ch[i + 1]} for i in range(len(ch) - 1))]
    if len(names) < 2:
        return
    b, sfx = _base(root["joint"])
    r = min(_rad(spec, j) for j in ch[1:-1]) if len(ch) > 2 else _rad(spec, ch[0])
    join = round(float(p.get("join", 0.15)) * r, 5)
    first = list(spec["bones"]).index(names[0])
    moved = {n: spec["bones"].pop(n) for n in names}
    for bb in moved.values():
        bb["group"], bb["join"] = f"{b}_limb{sfx}", join
    items = list(spec["bones"].items())
    spec["bones"] = dict(items[:first] + list(moved.items()) + items[first:])


def _hinge(spec: dict, a: str, j: str, c: str, p: dict, o: _Out):
    """A bony point on the hinge's extensor side, and the joint's bones slimmed (see the module docstring)."""
    b, sfx = _base(j)
    A, K, Cc = _pos(spec, a), _pos(spec, j), _pos(spec, c)
    d1, d2 = _unit(K - A), _unit(Cc - K)
    if "point" in p:
        e = np.asarray(p["point"], float)
    else:
        e = d1 - d2
        e[0] = 0.0  # in the plane of front and back
    e = e - d2 * (e @ d2)
    if np.linalg.norm(e) < 0.05:  # straight at rest: no side to put it on
        return
    e = _unit(e)
    r = _rad(spec, j)
    narrow = float(p.get("narrow", 0.9))
    for bb in spec["bones"].values():
        if bb.get("op", "add") == "add" and not bb.get("group") and j in (bb["a"], bb["b"]) and \
                bb.get("part", "body") == "body":
            end = "r_a" if bb["a"] == j else "r_b"
            bb[end] = round(narrow * float(bb.get(end) or r), 5)
    size = float(p.get("size", 1.0))
    part = p.get("part")
    extra = {"part": part} if part else {}
    # a flattened knob just proud of the slimmed joint, a little along the lower bone (the olecranon, the kneecap)
    o.joint(f"{b}_point_a{sfx}", K + e * 0.6 * r - d2 * 0.15 * r, 0.32 * r * size)
    o.joint(f"{b}_point_b{sfx}", K + e * 0.6 * r + d2 * 0.25 * r, 0.26 * r * size)
    o.bone(f"{b}_point{sfx}", f"{b}_point_a{sfx}", f"{b}_point_b{sfx}", flat=[1.0, 0.7], up=_r(e),
           blend=round(0.3 * r, 5), **extra)


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
    s = 1.0 if _beside(spec, root, d) else -1.0
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
