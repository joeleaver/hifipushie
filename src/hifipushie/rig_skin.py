"""Skinning: part weights, skin_parts, the cover over the skin, dropped joints, skin_mesh, rig_weights. Part of rig (rig.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import rig
from . import rig_bend
from .rig_flesh import _flesh_tree
from .rig_head import _rigid_head, _ss, head_field
from .rig_model import _smooth, weights
from .rig_twist import _spread_twist

def part_weights(spec: dict, pn: str, is_skin: bool) -> str:
    """How a part of a character with a base body gets its weights: parts.<p>.rig_weights, else "surface" for the
    skin and WORN_WEIGHTS for what is worn. "surface": the base's weights at the closest point of its surface
    facing the same way; "around": an average of the base's weights round that point, wider the farther the cloth
    is from the skin (rig_template.around_surface); "distance": the part's own distance weights to the rig's bones."""
    how = ((spec.get("parts") or {}).get(pn) or {}).get("rig_weights")
    if how is None:
        return "surface" if is_skin else rig.WORN_WEIGHTS
    if how not in rig.PART_WEIGHTS:
        raise ValueError(f"parts.{pn}.rig_weights: {how!r} (one of {', '.join(rig.PART_WEIGHTS)})")
    return how


def skin_parts(spec: dict, rb: list[dict], meshes: dict, smooth: int = rig.SMOOTH) -> dict:
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
             if len(V) and not (defs.get(pn) or {}).get("rig_bone") and float(hf.get("part", hf["h"])(V).mean()) < rig.HEAD_PART}
        sp = max(n, key=n.get) if n else None
    skin = {sp} | set((spec.get("face_shapes") or {}).get("parts") or ())
    if spec.get("base"):  # the reference: the base body's own quads, whole (the export's skin under clothes is gone)
        from . import base_implied, base_surface
        from .spec import expand_mirror as _em
        surf = base_surface.surface(base_implied.inject(_em(spec)), spec["base"])
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
            full = bone if bone in names else rig.PREFIX + bone
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
                                              two_sided=pn not in skin and rig.TWO_SIDED)
            rounds = int((defs.get(pn) or {}).get("rig_smooth", 0 if pn in skin else rig.WORN_SMOOTH))
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
        reach = float(d_.get("rig_attach_length", rig.ATTACH))
        for other in ([to] if isinstance(to, str) else to):
            ob = (defs.get(other) or {}).get("rig_bone")
            if other not in meshes or not ob or not len(meshes[other][0]):
                raise ValueError(f"parts.{pn}.rig_attach: {other!r} must be an exported part with a rig_bone")
            dist, _ = cKDTree(np.asarray(meshes[other][0], float)).query(np.asarray(V, float), distance_upper_bound=reach)
            h = 1.0 - _ss(np.where(np.isfinite(dist), dist, reach) / reach)
            out[pn] = _rigid_head(np.asarray(out[pn][0]), np.asarray(out[pn][1], np.float64), h,
                                  names.index(ob if ob in names else rig.PREFIX + ob))
    return out


def _head_kind(spec: dict, hf: dict, pn: str, V: np.ndarray, skin: set) -> str:
    """What the head rule makes of a part: "head" (all of it rigid: teeth, eyes), "worn" (no head rule: a collar) or
    "skin" (the falloff). parts.<p>.rig_head = true | false overrides worn."""
    share = float(hf.get("part", hf["h"])(V).mean())
    worn = ((spec.get("parts") or {}).get(pn) or {}).get("rig_head")
    worn = (not (pn in skin or share >= rig.HEAD_WORN)) if worn is None else not worn
    return "head" if share >= rig.HEAD_PART else "worn" if worn else "skin"


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
    reach, ease = float(co.get("reach", rig.COVER_REACH)), float(co.get("ease", rig.COVER_EASE))
    rounds = int(co.get("smooth", rig.COVER_SMOOTH))
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
        if rig.COVER_OUT and (~covered).any():  # the hand-over on the visible side: the skin at a neckline's edge stays
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
        n = re.sub(r"(Twist\d+|Bend)$", "", n[len(rig.PREFIX):] if n.startswith(rig.PREFIX) else n)  # (its twist joints and bend helper with it)
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


def skin_mesh(spec: dict, rb: list[dict], V: np.ndarray, F: np.ndarray, part: np.ndarray, part_names,
              smooth: int = rig.SMOOTH) -> tuple[np.ndarray, np.ndarray]:
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


def rig_weights(spec: dict, rb: list[dict], verts: np.ndarray, faces: np.ndarray | None = None,
                k: int = 4, smooth: int = rig.SMOOTH) -> tuple[np.ndarray, np.ndarray]:
    """Skin weights on the rig bones. Each rig bone gets flesh of its own from the modelling geometry: the piece
    of every modelling cone it lies along (Spine, Spine1, Spine2 split the one spine cone), modelling bones lying
    inside its segment (a finger's pieces), and the rest of the modelling bones (a tusk, an ear, a collar) with
    go to the rig bone nearest their middle, blobs to the rig bone nearest their middle; a rig bone left with none (a hand, the toes) gets a cone
    along its own segment. Then `weights` on the rig tree: nearest-flesh distances, family-limited, smoothed. Then
    the twist chains take their segments' weight (`_spread_twist`)."""
    ids, carry = _flesh_tree(spec, rb)
    J, W = weights(carry, verts, faces, k=k, smooth=smooth)
    J, W = _spread_twist(rb, verts, np.asarray(ids)[J], W, k)
    from .rig_join import limb_join  # a limb's weight blended across the seam its skin really has with the body's
    return limb_join(spec, rb, verts, faces, J, W, carry, rig_bend.limb_girth(rb, verts, J, W))
