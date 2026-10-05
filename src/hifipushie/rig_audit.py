"""The skin weights' audit: an export read back as an engine gets it, and a test of every joint turned alone.

The user, on a sheet of twisted forearms: "the fingers are getting mangled and so is the jaw. We might have serious
issues with how our skin weights are getting made." Two things were tangled in that sheet: the mesh (the rig tool's
look build was ~11 mm voxels: fingers fused at REST) and the weights. So: `read_glb` gives the real export's mesh,
joints and weights, and `audit` measures weights on whatever mesh it is given, with numbers that don't need an eye:
what should be rigid, what leaks onto other bones' skin, what a joint loses, what turns inside out."""
from __future__ import annotations

import numpy as np

from .rig import PREFIX, _seg_dist, _segments, pose


def read_glb(path) -> dict:
    """An exported GLB's rig as an engine gets it, in Blender axes: {"bones": [{"name", "head", "parent", "end",
    "twist"?}], "meshes": {name: {"V", "F", "N", "J", "W", "moved" (the largest face-shape move per vertex, or
    None), "targets": {shape: (count, 3) moves}}}}. Vertices are the GLB's own (split at uv seams)."""
    import json
    import struct
    from pathlib import Path
    raw = Path(path).read_bytes()
    jl = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20:20 + jl])
    b0 = 28 + jl
    ct = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
    nc = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

    def view(bv, c, n, k, off=0):
        return np.frombuffer(raw, ct[c], n * k, b0 + doc["bufferViews"][bv].get("byteOffset", 0) + off).reshape(n, k)

    def acc(i):
        a = doc["accessors"][i]
        k = nc[a["type"]]
        out = (view(a["bufferView"], a["componentType"], a["count"], k, a.get("byteOffset", 0)).astype(np.float64)
               if "bufferView" in a else np.zeros((a["count"], k)))
        if "sparse" in a:
            s = a["sparse"]
            idx = view(s["indices"]["bufferView"], s["indices"]["componentType"], s["count"], 1)[:, 0]
            out = out.copy()
            out[idx] = view(s["values"]["bufferView"], a["componentType"], s["count"], k)
        return out
    y2z = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)  # glTF (Y up, +Z front) -> Blender (Z up, -Y front)
    nodes = doc["nodes"]
    skin = doc["skins"][0]
    joints = skin["joints"]
    ibm = acc(skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
    head = np.array([np.linalg.inv(m)[:3, 3] for m in ibm]) @ y2z.T
    par = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    order = {j: k for k, j in enumerate(joints)}
    bones = []
    for k, j in enumerate(joints):
        n = nodes[j]
        tw = (n.get("extras") or {}).get("hifipushie_twist")
        leaf = not any(c in order for c in n.get("children", []))
        b = {"name": n["name"], "head": head[k], "parent": order.get(par.get(j), -1),
             "end": leaf and not tw and (n["name"].lower().endswith("_end") or n["name"][-1:] == "4")}
        if tw:
            ax = y2z @ np.asarray(tw["axis_parent"], float)
            seg = order[par[j]]
            ch = [head[order[c]] for c in nodes[par[j]].get("children", [])
                  if c in order and "hifipushie_twist" not in (nodes[c].get("extras") or {})]
            b["twist"] = {"of": nodes[par[j]]["name"], "driver": tw["driver"], "mode": tw["mode"],
                          "share": tw["share"], "station": tw["station"], "axis": ax,
                          "length": max((float((c - head[seg]) @ ax) for c in ch), default=1e-3)}
        bones.append(b)
    meshes = {}
    for n in nodes:
        if "mesh" not in n or "skin" not in n:
            continue
        me = doc["meshes"][n["mesh"]]
        p = me["primitives"][0]
        a = p["attributes"]
        mv, tg = None, {}
        if "targets" in p:
            tn = (me.get("extras") or {}).get("targetNames") or [str(i) for i in range(len(p["targets"]))]
            mv = np.zeros(doc["accessors"][a["POSITION"]]["count"])
            for nm, t in zip(tn, p["targets"]):
                tg[nm] = acc(t["POSITION"]) @ y2z.T
                mv = np.maximum(mv, np.linalg.norm(tg[nm], axis=1))
        meshes[me["name"]] = {"V": acc(a["POSITION"]) @ y2z.T, "F": acc(p["indices"]).astype(int).reshape(-1, 3),
                              "N": acc(a["NORMAL"]) @ y2z.T, "J": acc(a["JOINTS_0"]).astype(int),
                              "W": acc(a["WEIGHTS_0"]), "moved": mv, "targets": tg}
    return {"bones": bones, "meshes": meshes}


def joined(meshes: dict, shape: dict | None = None):
    """(V, F, J, W, part index per vertex, part names) of several skinned meshes as one; shape = {name: weight} adds
    those face shapes' moves to the vertices."""
    Vs, Fs, Js, Ws, ps, off = [], [], [], [], [], 0
    for i, m in enumerate(meshes.values()):
        V = m["V"].copy()
        for nm, w in (shape or {}).items():
            if nm in (m.get("targets") or {}):
                V += w * m["targets"][nm]
        Vs.append(V), Fs.append(m["F"] + off), Js.append(m["J"]), Ws.append(m["W"])
        ps.append(np.full(len(V), i))
        off += len(V)
    return (np.concatenate(Vs), np.concatenate(Fs), np.concatenate(Js), np.concatenate(Ws), np.concatenate(ps),
            list(meshes))


def weld(V: np.ndarray, F: np.ndarray, tol: float = 1e-6):
    """Vertices at one position made one (a GLB splits them at uv seams): (index of each vertex's representative,
    faces on representatives). For measures that need a connected surface."""
    key = np.round(V / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    rep = first[inv.ravel()]
    return rep, rep[F]


# What a joint is turned through in the audit (degrees), by the bone's name: about what it does in use.
AUDIT_TURN = (("Thumb", 45), ("Index", 70), ("Middle", 70), ("Ring", 70), ("Pinky", 70), ("ForeArm", 90),
              ("Shoulder", 15), ("Arm", 60), ("Hand", 45), ("UpLeg", 60), ("Leg", 90), ("Foot", 30), ("Toe", 30),
              ("Spine", 20), ("Neck", 25), ("Head", 33))
DIGITS = ("Thumb", "Index", "Middle", "Ring", "Pinky")
BAD = {"rigid": 3.0, "leak": 6.0, "leak_digit": 3.0, "flipped": 20, "bleed": 0.15}  # mm, mm, mm, triangles, weight
# Bones that lie inside a mass their own segment doesn't carry rigidly (the clavicle over the ribs, the thumb's
# metacarpal in the palm): what must follow them is their descendants' skin, away from the next joint's own blend.
BURIED = ("Shoulder", "HandThumb1")


def owners(bones: list[dict], V: np.ndarray, F: np.ndarray | None = None):
    """Per vertex: the weight-carrying bone it belongs to, each bone's girth (the median distance of its own
    vertices), the segments. Belonging = the nearest bone segment, corrected over the surface: a patch labelled
    with a bone but not connected to that bone's main patch (thigh skin beside a hanging hand, a finger's side
    nearer its neighbour's bone) goes to the next nearest bone whose patch it does touch. Without faces: distance
    alone."""
    seg = _segments(bones)
    ids = np.array(list(seg))
    D = np.stack([_seg_dist(V, seg[i][0], seg[i][1]) for i in ids], 1)
    near = D.argmin(1)
    D0 = D.copy()
    if F is not None and len(F):
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        e = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
        used = np.zeros(len(V), bool)
        used[F.ravel()] = True
        for _ in range(4):
            same = near[e[:, 0]] == near[e[:, 1]]
            g = coo_matrix((np.ones(same.sum()), (e[same, 0], e[same, 1])), shape=(len(V), len(V)))
            _, comp = connected_components(g, directed=False)
            key = near.astype(np.int64) * (len(V) + 1) + comp  # a patch = (label, component)
            _, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
            inv = inv.ravel()
            best = np.zeros(len(ids), int)
            np.maximum.at(best, near, cnt[inv])
            touches = np.zeros(len(cnt), bool)  # the patch borders another bone's skin (a loose piece doesn't)
            touches[inv[e[~same].ravel()]] = True
            idx = np.flatnonzero(used & (cnt[inv] < best[near]) & touches[inv])
            if not len(idx):
                break
            D[idx, near[idx]] = np.inf
            near[idx] = D[idx].argmin(1)
    girth = {int(ids[q]): (float(np.median(D0[near == q, q])) if (near == q).sum() > 3 else 0.02)
             for q in range(len(ids))}
    return ids[near], girth, seg, (ids, D0)


CLEAR = 0.7  # a vertex is clearly one side's when that side's nearest bone is this much nearer than the other's


def bound(meshes: dict) -> np.ndarray:
    """Per vertex of `joined(meshes)`: in a mesh bound whole to one joint (parts.<p>.rig_bone: a bag on the hip, a
    disc in the hand, hair on the head). Such a prop follows its joint, not the bones it happens to lie near, so the
    audit leaves it out."""
    out = []
    for m in meshes.values():
        J, W = np.asarray(m["J"]), np.asarray(m["W"])
        top = J[np.arange(len(J)), W.argmax(1)]
        out.append(np.full(len(J), bool(len(J)) and bool((W.max(1) > 0.999).all()) and bool((top == top[0]).all())))
    return np.concatenate(out)


def audit(bones: list[dict], V: np.ndarray, F: np.ndarray, J: np.ndarray, W: np.ndarray, only=None,
          skip: np.ndarray | None = None) -> dict:
    """The skin's test on any skinned mesh (the look's build, or an export read back by `read_glb`).
    Static: weights summing to 1, influences per vertex, left / right asymmetry, and digit BLEED: weight one
    digit's bones hold on another digit's skin (neighbouring fingers are millimetres apart: what distance weighting
    gets wrong).
    Posed: each joint turned alone through its usual range (AUDIT_TURN), about two axes across its bone:
      rigid    how far the skin that should follow the bone rigidly (its own and its descendants', past the joint's
               blend) ends from where a rigid turn puts it (mm, p95 / worst);
      leak     how far skin that belongs to other bones (not its descendants, past the joint's blend) moved (mm),
               and whose skin moved most;
      volume   the mesh's volume change as a share of the joint's own size (a rigid turn changes none);
      flipped  triangles turned inside out (of those wholly on one side of the joint).
    {"static": {...}, "bones": [rows, worst first by a score in mm]}. Self-intersection isn't measured: flipped
    triangles and leak are its usual signs. skip: vertices left out of every measure (`bound`: rigid props)."""
    from scipy.spatial import cKDTree
    names = [b["name"] for b in bones]
    n = len(bones)
    V = np.asarray(V, np.float64)
    keep = np.ones(len(V), bool) if skip is None else ~np.asarray(skip, bool)
    fam = np.arange(n)
    for i, b in enumerate(bones):
        if b.get("twist"):
            fam[i] = b["parent"]
    dense = np.zeros((len(V), n))
    np.add.at(dense, (np.repeat(np.arange(len(V)), J.shape[1]), fam[J].ravel()), W.ravel())
    own, girth, seg, (ids, D0) = owners(bones, V, F)
    col = {int(b): q for q, b in enumerate(ids)}

    def nearest(mask):  # distance to the nearest segment of the bones in mask (n,), inf when there is none
        cols = [col[b] for b in np.flatnonzero(mask) if b in col]
        return D0[:, cols].min(1) if cols else np.full(len(V), np.inf)
    par = np.array([b["parent"] for b in bones])
    desc = np.eye(n, dtype=bool)  # desc[a, b]: b is a or under a
    for i in range(n):
        p = par[i]
        while p >= 0:
            desc[p, i] = True
            p = par[p]
    static = {"vertices": int(len(V)), "skipped": int((~keep).sum()), "sum_error": float(np.abs(W.sum(1) - 1).max()),
              "negative": int((W < -1e-9).sum()), "influences_max": int((W > 1e-6).sum(1).max()),
              "influences_mean": float((W > 1e-6).sum(1).mean())}
    swap = np.arange(n)
    for i, nm in enumerate(names):
        for a, b in (("Left", "Right"), ("Right", "Left")):
            if a in nm and nm.replace(a, b) in names:
                swap[i] = names.index(nm.replace(a, b))
    left = np.flatnonzero(V[:, 0] > 0.01)
    if len(left):
        d, k = cKDTree(V).query(V[left] * [-1, 1, 1])
        ok = d < 0.004
        if ok.any():
            diff = 0.5 * np.abs(dense[left[ok]][:, swap] - dense[k[ok]]).sum(1)
            static["asymmetry"] = {"compared": int(ok.sum()), "of": int(len(left)), "mean": float(diff.mean()),
                                   "p99": float(np.percentile(diff, 99)), "max": float(diff.max())}
    chain = {}
    for i, nm in enumerate(names):
        for dname in DIGITS:
            if "Hand" + dname in nm:
                chain[i] = nm.replace(PREFIX, "").split("Hand")[0] + dname
    bleed = []
    digs = sorted(set(chain.values()))
    own_chain = np.array([chain.get(int(o), "") for o in own])
    for a in digs:
        wa = dense[:, [i for i, c in chain.items() if c == a]].sum(1)
        for b in digs:
            if a == b or a[:4] != b[:4]:
                continue
            ib = np.zeros(n, bool)
            ib[[i for i, c in chain.items() if c == b]] = True
            ia = np.zeros(n, bool)
            ia[[i for i, c in chain.items() if c == a]] = True
            # b's skin, clearly: its bone nearer than a's by CLEAR (the web between two fingers is nobody's)
            first = min(i for i, c in chain.items() if c == b)  # past the knuckle: the web there is shared
            m = (keep & (own_chain == b) & (nearest(ib) < CLEAR * nearest(ia))
                 & (np.linalg.norm(V - bones[first]["head"], axis=1) > 2.5 * girth.get(first, 0.008)))
            if m.any() and wa[m].max() > 0.02:
                bleed.append({"holder": a, "on": b, "max": float(wa[m].max()),
                              "over": int((wa[m] > 0.1).sum()), "of": int(m.sum())})
    static["digit_bleed"] = sorted(bleed, key=lambda r: -r["max"])
    area0 = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vol0 = float((V[F[:, 0]] * area0).sum() / 6)
    ed = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    closed = bool((np.unique(ed, axis=0, return_counts=True)[1] == 2).all())  # volume means nothing on an open mesh
    static["closed"] = closed
    rows = []
    for i, b in enumerate(bones):
        if i not in seg or b["parent"] < 0 or (only and not any(o in b["name"] for o in only)):
            continue
        deg = next((d for key, d in AUDIT_TURN if key in b["name"]), 30)
        a0, a1 = seg[i]
        ax = a1 - a0
        L = float(np.linalg.norm(ax))
        if L < 2e-3:
            continue
        ax = ax / L
        e1 = np.cross(ax, [0, 0, 1.0]) if abs(ax[2]) < 0.9 else np.cross(ax, [1.0, 0, 0])
        e1 /= np.linalg.norm(e1)
        r = max(girth.get(i, 0.02), girth.get(int(par[i]), 0.0), 0.004)
        dj = np.linalg.norm(V - a0, axis=1)
        mine = desc[i][own]
        # the joint's own blend runs back along its parent and onto the bones that share the joint: their skin
        # within three girths of the joint isn't a leak
        rel = (par[own] == par[i]) | (own == par[i])
        gp = par[par[i]] if par[i] >= 0 else -1
        rel = rel | ((own == gp) & (gp >= 0))  # and its grandparent's (pec and lat ride the arm from the chest)
        dm, do = nearest(desc[i]), nearest(~desc[i])
        strict = desc[i].copy()
        buried = b["name"].endswith(BURIED)
        strict[i] = not buried
        follow = keep & strict[own] & (dj > 1.6 * r) & (dm < CLEAR * do)
        if buried:
            for c in np.flatnonzero(par == i):
                if c in seg:
                    follow &= np.linalg.norm(V - bones[c]["head"], axis=1) > 3.0 * girth.get(int(c), 0.02)
        r_own = max(girth.get(i, 0.02), 0.004)  # (a finger's blend reaches a finger's width, not the palm's)
        stay = keep & ~mine & ~(rel & (dj < 3.0 * r_own)) & (dj > 1.6 * r_own) & (do < CLEAR * dm)
        worst = None
        for e in (e1, np.cross(ax, e1)):
            t = np.radians(deg)
            K = np.array([[0, -e[2], e[1]], [e[2], 0, -e[0]], [-e[1], e[0], 0]])
            R = np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K
            P = pose(bones, V, J, W, {b["name"]: (e, deg)})
            er = np.linalg.norm(P - ((V - a0) @ R.T + a0), axis=1)[follow]
            ls = np.linalg.norm(P - V, axis=1)[stay]
            ar = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
            fm = mine[F].all(1)
            pure = (fm | (~mine[F]).all(1)) & keep[F].all(1)
            exp = np.where(fm[:, None], area0 @ R.T, area0)
            row = {"bone": b["name"], "deg": deg, "digit": i in chain,
                   "rigid_p95": float(np.percentile(er, 95) * 1e3) if len(er) else 0.0,
                   "rigid_max": float(er.max() * 1e3) if len(er) else 0.0,
                   "leak_n": int((ls > 1e-3).sum()),
                   "leak_max": float(ls.max() * 1e3) if len(ls) else 0.0,
                   "volume": float(((P[F[:, 0]] * ar).sum() / 6 - vol0) / (np.pi * r * r * 2 * r)) if closed else None,
                   "flipped": int((((ar * exp).sum(1) < 0) & pure).sum()), "follow": int(follow.sum())}
            if len(ls) and ls.max() > 1e-4:
                big = np.flatnonzero(stay)[ls > 0.5 * ls.max()]
                o, c = np.unique(own[big], return_counts=True)
                row["leak_on"] = names[int(o[c.argmax()])]
            row["score"] = max(row["rigid_p95"], row["leak_max"] if row["leak_n"] >= 5 else 0.0) + 0.1 * row["rigid_max"]
            if worst is None or row["score"] > worst["score"]:
                worst = row
        rows.append(worst)
    rows.sort(key=lambda r: -r["score"])
    return {"static": static, "bones": rows}


def is_bad(r: dict) -> bool:
    return (r["rigid_p95"] > BAD["rigid"]
            or (r["leak_max"] > BAD["leak_digit" if r.get("digit") else "leak"] and r["leak_n"] >= 5)
            or r["flipped"] > BAD["flipped"])


def audit_text(a: dict, top: int = 12) -> list[str]:
    """The audit as lines to read: the static checks, then the worst joints."""
    s = a["static"]
    nb = sum(1 for r in a["bones"] if is_bad(r))
    out = [f"weights audit ({s['vertices']} vertices, {len(a['bones'])} joints turned): {nb} joints BAD; sums off by "
           f"{s['sum_error']:.0e}, {s['negative']} negative weights, influences max {s['influences_max']} (mean "
           f"{s['influences_mean']:.2f})"]
    y = s.get("asymmetry")
    if y:
        out.append(f"  left/right: {y['compared']} of {y['of']} left vertices have a mirror within 4 mm; weights "
                   f"differ mean {y['mean']:.3f}, p99 {y['p99']:.3f}, worst {y['max']:.2f} (0 = symmetric)")
    if s["digit_bleed"]:
        out.append("  digit bleed (weight one digit's bones hold on another digit's skin; over "
                   f"{BAD['bleed']} is BAD):")
        out += [f"    {r['holder']} on {r['on']}: up to {r['max']:.2f}, {r['over']} of {r['of']} vertices over 0.1"
                + (" <- BAD" if r["max"] > BAD["bleed"] else "") for r in s["digit_bleed"][:8]]
    else:
        out.append("  digit bleed: none over 0.02")
    out.append("  each joint turned alone, worst of two axes (rigid = its own skin against a rigid turn; leak = "
               "other bones' skin moved more than 1 mm; volume = change / the joint's size"
               + ("" if s["closed"] else ", not measured: the mesh is open") + "; flipped = triangles inside out):")
    for r in a["bones"][:top]:
        vol = f", volume {r['volume'] * 100:+.0f}%" if r["volume"] is not None else ""
        out.append(f"    {r['bone'].replace(PREFIX, '')} {r['deg']} deg: rigid p95 {r['rigid_p95']:.1f} mm (worst "
                   f"{r['rigid_max']:.1f}, {r['follow']} vertices), leak {r['leak_n']} vertices (worst "
                   f"{r['leak_max']:.1f} mm" + (f" on {r['leak_on'].replace(PREFIX, '')}" if r.get("leak_on") else "")
                   + f"){vol}, flipped {r['flipped']}" + (" <- BAD" if is_bad(r) else ""))
    return out
