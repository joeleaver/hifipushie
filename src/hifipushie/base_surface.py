"""The base as a surface: `surface` (the point set of body, graft and head), the sealed mouth's field, `sd_base`. Part of base (base.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np
from scipy.spatial import cKDTree

from . import base
from . import base as base_mod
from . import retopo
from . import retopo_warp
from .base import _source_key, source
from .base_gnm_parts import mouth_mode, mouth_open, sock_points
from .base_imls import _catmull_clark, _normals_and_h, _sd_body
from .base_measures import head_of
from .base_tubes import _neck_tube, _push, _soften, _tube_weight

def _sealed_field(W, faces, sf: dict):
    """A sealed mouth (lip_seal) for the field only (the template's quads, the export's and the face shapes', keep the
    lips' inner rolls): the rolls from the open mouth loop to the contact ring are left out, and the two lips' contact
    rows overlap by 2 x SEAL_OVERLAP. With the rolls in, the lips touching closed a pocket of 'outside' behind the
    seam, and with them only touching the slit between them was a zero-thickness sliver: the mesher left a row of
    pits and fragments along the seam (Tess, ts_w / ts_x). Returns (vertices, faces) with unused vertices dropped."""
    drop = np.zeros(len(W), bool)
    drop[np.asarray(sf["drop"], int)] = True
    F = [f for f in faces if not drop[np.asarray(f)].all()]
    W = np.array(W, float)
    W[np.asarray(sf["up"], int), 2] -= base.SEAL_OVERLAP
    W[np.asarray(sf["lo"], int), 2] += base.SEAL_OVERLAP
    # the V between the closed lips' fronts made shallower: the next rows out drawn toward the seam (by the vertical
    # gap between the two lips' rows at that x). Left as GNM shapes them, the V narrowed to the mesher's ~1 mm before
    # it closed and came out as a row of specks along the seam (Tess ts_h7)
    for (ru, rl), wgt in zip(sf.get("outer") or [], sf.get("v") or base.SEAL_V):
        ru, rl = np.asarray(ru, int), np.asarray(rl, int)
        if len(ru) < 3 or len(rl) < 3:
            continue
        ou, ol = ru[np.argsort(W[ru, 0])], rl[np.argsort(W[rl, 0])]
        zl_at_u = np.interp(W[ou, 0], W[ol, 0], W[ol, 2])
        zu_at_l = np.interp(W[ol, 0], W[ou, 0], W[ou, 2])
        du = np.maximum(W[ou, 2] - zl_at_u, 0.0)
        dl = np.maximum(zu_at_l - W[ol, 2], 0.0)
        W[ou, 2] -= 0.5 * wgt * du
        W[ol, 2] += 0.5 * wgt * dl
    used = np.unique(np.concatenate([np.asarray(f) for f in F]))
    rm = np.full(len(W), -1)
    rm[used] = np.arange(len(used))
    return W[used], [list(rm[np.asarray(f)]) for f in F]


def surface(spec_expanded: dict, base: dict) -> dict:
    """The posed, subdivided base: {"verts", "faces", "normals", "h", "quads" (the unsubdivided warp), "src" (each
    quad vertex's index in the template's own vertices, -1 for a grafted neck's: what carries the template's
    hand-made skin weights, rig.py), "tree"}.
    Cached by the template, the joints it uses and the settings."""
    name = _source_key(base)
    tpl = source(base)
    used = {}
    for k in tpl["J"]:
        for n in (k, retopo._model_name(k)):
            if n in spec_expanded["joints"]:
                used[k] = spec_expanded["joints"][n]["pos"]
                break
    settings = {k: base.get(k) for k in ("girth", "subdivide", "smooth", "head", "soften", "push", "body", "style")}
    if (base.get("body") or {}).get("source") == "human":  # (onemesh.py) its own version: old paths keep their keys
        from . import onemesh
        settings["one"] = onemesh.VERSION if not onemesh.native(base) else onemesh.build_version(base)
    used["_eyes"] = [spec_expanded["joints"][e]["pos"] for e in ("eye.L", "eye.R") if e in spec_expanded["joints"]]
    key = hashlib.sha1(json.dumps([name, used, settings, base_mod.VERSION], sort_keys=True, default=float).encode()).hexdigest()
    if key in base_mod._CACHE:
        return base_mod._CACHE[key]
    girth = dict(base.get("girth") or {})
    for j, g in list(girth.items()):  # mirrored
        if j.endswith(".L"):
            girth.setdefault(j[:-2] + ".R", g)
    W, *_ = retopo_warp._skeleton_warp(tpl["P"], tpl["J"], spec_expanded, [], girth=girth)
    faces, _, _ = retopo.topology(tpl["L"], tpl["S"])
    soften = base.get("soften")
    if soften:  # (the style's simplify is the head's only: softening the body with it left a ridge at the neck's
        # base, where the soften fades out under the neck loop)
        W = _soften(W, tpl, spec_expanded, float(soften))
    if base.get("push"):
        W = _push(W, tpl, base["push"])
    head = head_of(spec_expanded, base)
    one = head is not None and bool(head.get("one_mesh"))  # (onemesh.py) the head is in the template's own quads
    own_neck = head is not None and bool(head.get("own_neck")) and not one
    if one:
        src = np.arange(len(W))
    elif own_neck:  # (headfit.py) the head IS this body's head, a few mm apart everywhere: the body keeps its own neck,
        # throat and nape and the two are cross-faded at the plane under the jaw. A tube from a neck loop up to the
        # head's own (adult) neck gave a toddler, who has no neck to speak of, a long thin one
        src = np.arange(len(W))
    elif head is not None:  # a grafted head: the template's own head cut off at a neck loop under its jaw and the
        # neck extruded straight up as quads (its chin and jaw, bigger and lower than a real head's, stood out of the
        # graft band; columns of points built from its vertices left lips and ruffs)
        W, faces, src = _neck_tube(W, faces, tpl, spec_expanded, head)
    else:
        src = np.arange(len(W))
    V, F = W, faces
    if one and tpl.get("seal_field"):  # (faceslide: lip_seal) the closed mouth as the field sees it
        V, F = _sealed_field(W, faces, tpl["seal_field"])
    for _ in range(int(base.get("subdivide", 1))):
        V, F = _catmull_clark(V, F)
    N, h = _normals_and_h(V, F)
    if one and tpl.get("seal_field"):  # the seam's narrow V between closed lips, wider kernels there: at the field's
        # own width the mesher (~1 mm) cut it into a row of pits (Tess ts_h7: dark specks along the seam)
        cs = np.asarray(W, float)[np.r_[np.asarray(tpl["seal_field"]["up"], int), np.asarray(tpl["seal_field"]["lo"], int)]]
        dz = cKDTree(cs).query(V)[0]
        h = h * (1 + (base_mod.SEAL_H - 1) * np.clip(1 - dz / base_mod.SEAL_H_REACH, 0, 1))
    if own_neck:  # MakeHuman's neck is rings of long thin quads: with the mean edge as the kernel's width the field
        # was faceted between the rings (fine level lines down the neck). The longest edge at each vertex instead.
        # (Tried on the one mesh, 2026-10-08: no visible change, and a wider kernel over its neck bridge, or one
        # never much narrower than its neighbour's, SPECKLED the bridge: the k-nearest truncation. Left out there.)
        E = np.array(sorted({(min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)])) for f in F for k in range(len(f))}))
        ln = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
        hm = np.zeros(len(V))
        np.maximum.at(hm, E[:, 0], ln)
        np.maximum.at(hm, E[:, 1], ln)
        h = np.maximum(h, 0.9 * hm)
    h = h * float(base.get("smooth", 1.0))
    if head is not None and not one:  # one point set: the body under the graft plane, the head over it (the tube tapers to the
        # head's neck at the plane, so they meet). Blending two fields across a band instead showed the band: where
        # the two surfaces differ, the blend weight's gradient tilts the normals (a collar in every render)
        c, pn, _ = head["plane"]
        axis_d = np.linalg.norm(np.cross(V - c, pn), axis=1)
        # both sets overlap across +-SEAM and their points are weighted down across it (C2 ramps): cut hard at the
        # plane, the two surfaces' few-mm mismatch left a ragged crack
        ub = (V - c) @ pn
        kb = (ub <= base_mod.SEAM) | (axis_d > 0.2)
        def ramp(x):
            x = np.clip(x, 0, 1)
            return x ** 3 * (x * (6 * x - 15) + 10)
        H = head["verts"]
        uh = (H - c) @ pn
        if own_neck:  # the head's skin eased onto the body's own head where they meet (they differ by millimetres:
            # cross-faded as they were, the seam showed as a soft step), fading out OWN_REACH above the plane
            reach = base_mod.OWN_REACH * float(head["carry"]["s"])
            near = np.flatnonzero((uh > -2 * base_mod.SEAM) & (uh < reach))
            nh = head["normals"][near]
            # each head point's closest point of the body's own SKIN (its triangles; only skin facing the same way: a
            # baby's chin lies on its chest), and the normal there. (The weighted mean of the nearest body VERTICES
            # sat under the surface and drew the points onto the mesh's rings: a ribbed band round the throat.)
            from . import rig_template
            T = np.array([(q[0], q[j], q[j + 1]) for q in F for j in range(1, len(q) - 1)])
            T = T[(((V[T].mean(1) - c) @ pn) > -4 * base_mod.SEAM) & (((V[T].mean(1) - c) @ pn) < reach + 0.03)]
            Q = rig_template.from_surface(V, T, np.c_[V, N], H[near], nh)
            tgt, nb_ = Q[:, :3], Q[:, 3:]
            # how far each point is trusted to be the same skin: by its distance and by facing the same way, without
            # steps (a point eased next to one left alone tore the skin under a child's jaw into shards)
            dist = np.linalg.norm(tgt - H[near], axis=1)
            cosn = (nb_ * nh).sum(1) / np.maximum(np.linalg.norm(nb_, axis=1), 1e-12)
            ok = (1 - ramp((dist - 0.02) / 0.015)) * ramp((cosn + 0.2) / 0.5)
            off = ok * ((tgt - H[near]) * nh).sum(1)  # along the head's normal only (no sliding)
            f = 1 - ramp(np.clip(uh[near], 0, None) / reach)
            H = H.copy()
            H[near] += (f * off)[:, None] * nh
            # (the whole way inside the overlap, sideways too, with the body's normals: a ribbed band round the throat)
            # (a last step onto the body's field itself, tried against the fine lines on the throat, tore a ring
            # round the neck at the plane: the lines were the body's own kernel width, see h above)
        kh = uh > -base_mod.SEAM

        wb = np.where(axis_d[kb] > 0.2, 1.0, 1 - ramp((ub[kb] + base_mod.SEAM) / (2 * base_mod.SEAM)))
        wh = ramp((uh[kh] + base_mod.SEAM) / (2 * base_mod.SEAM))
        hh = head["h"]
        if own_neck:  # where the two skins still stand apart in the overlap (under a child's jaw the body's and the
            # head's are different surfaces, 5-10 mm apart) each point's kernel is as wide as the gap, so the field
            # blends them into one closed skin; with their own few-mm kernels the sheets ended in free edges: a slot
            # across the throat with shards in it
            gap = np.linalg.norm(tgt - H[near], axis=1) * (1 - ramp((uh[near] - base_mod.SEAM) / base_mod.SEAM))
            hh = hh.copy()
            hh[near] = np.maximum(hh[near], 1.3 * gap)
            bn = np.flatnonzero(kb & (ub > -2 * base_mod.SEAM) & (axis_d <= 0.2))
            db, _ = cKDTree(H[near]).query(V[bn])
            h = h.copy()
            h[bn] = np.maximum(h[bn], 1.3 * np.minimum(db, 0.03) * ramp((ub[bn] + 2 * base_mod.SEAM) / base_mod.SEAM))
        V = np.r_[V[kb], H[kh]]
        N = np.r_[N[kb], head["normals"][kh]]
        h = np.r_[h[kb], hh[kh]]
        wt = np.maximum(np.r_[wb, wh], 1e-4)
    if head is not None and mouth_mode(base, head) == "gnm" and mouth_open(base, head):
        sk = sock_points(head)
        if sk is not None:  # GNM's mouth bag behind parted lips (points only: the faces and quads stay the skin's)
            V, N, h = np.r_[V, sk["verts"]], np.r_[N, sk["normals"]], np.r_[h, sk["h"] * float(base.get("smooth", 1.0))]
            if head is not None and not one:
                wt = np.r_[wt, np.ones(len(sk["verts"]))]
    out = {"verts": V, "faces": F, "normals": N, "h": h, "hmax": float(h.max()), "quads": (W, faces), "tree": cKDTree(V),
           "key": key, "head": None, "graft": None if one else head, "src": src, "template": tpl.get("name"),
           "wt": wt if head is not None and not one else None,
           "seam": (head["plane"][0], head["plane"][1], 0.2) if head is not None and not one else None}
    if len(base_mod._CACHE) > 8:
        base_mod._CACHE.pop(next(k for k in base_mod._CACHE if not isinstance(k, tuple)))
    base_mod._CACHE[key] = out
    return out


def sd_base(p: np.ndarray, pr: dict) -> np.ndarray:
    """IMLS distance to the base (see the module docstring). A grafted head is part of the same point set. A
    garment with a torso tube is two point sets mixed by weight (_tube_weight)."""
    if pr.get("mix"):
        X = p.reshape(-1, 3)
        W = np.array([_tube_weight(X, m) for m in pr["weights"]])
        tot = W.sum(0)
        W = W / np.maximum(tot, 1.0)
        out = _sd_body(X, pr["mix"][0]) * (1 - W.sum(0))
        for w, t in zip(W, pr["mix"][1:]):
            on = w > 1e-4
            if on.any():
                out[on] += w[on] * _sd_body(X[on], t)
        return out.reshape(p.shape[:-1])
    return _sd_body(p, pr)
