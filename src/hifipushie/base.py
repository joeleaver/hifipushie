"""A base mesh as the start of a character: spec["base"] = {"template": "male_stylized", ...} puts the CC0 template
body (Blender Studio's Human Base Meshes, `templates/`) into the field as one primitive, posed and stretched onto the
spec's skeleton, so a human starts from real planes (jaw, cheekbones, lids, lips, hands) and everything else (blobs,
bones, strokes, kits, shell parts, paint) edits on top of it.

- Joints: the template's skeleton (pelvis, chest, neck, head, shoulder/elbow/wrist, hip/knee/ankle/toe, fingerN_k,
  thumb_k .L) is added to the spec's joints where the spec doesn't give them (`inject`, before kits), with radii
  measured from the template. Moving a joint moves the base with it (`retopo._skeleton_warp`: per bone segment a
  rotation and a stretch, radii kept, times "girth" {segment start joint: scale}, e.g. {"shoulder.L": 1.15} for a
  thicker upper arm).
- Surface: the warped quads are Catmull-Clark subdivided ("subdivide", default 1) and become an implicit surface
  (`sd_base`): IMLS over the vertices (Kolluri 2005): f(x) = sum w_i n_i.(x - p_i) / sum w_i, w_i Wendland's C2 kernel of support 2 h_i, h_i
  the vertex's own edge length x "smooth" (default 1), 24 nearest vertices. Smooth (no facets),
  follows the quads' density (1-2 mm round the eyes, ~8 mm on the back), and ~ a signed distance near the surface.
  The kernel widens with distance (h >= 0.7 x the nearest vertex's distance), so off the surface it's a plane fit
  over a patch as wide as the distance: shells 5-15 mm out are smooth. Past 3 cm it fades to the distance to the
  nearest vertex minus the largest h (conservative, for culling).
- Body sources (`source`): the template (default) or MakeHuman (`body: {"source": "makehuman", "age", "weight",
  "muscle", "height", "race"}`, makehuman.py): no hand edits for age and build.
- Head graft (`head: {"source": "gnm", ...}`, Google GNM): the body's head is cut at one of its own neck loops ~2.5 cm under
  its chin and the loop extruded as a quad tube (`_neck_tube`) whose rings leave the loop along the body's slope (Hermite)
  and then follow the head's own neck slice by slice through the overlap; body points under the (tilted) graft plane
  and head points over it make one IMLS point set, weighted by C2 ramps across +-SEAM (the k nearest are raised
  there). Blending two fields across a band showed as a collar; points cut hard at the plane left a crack; a tube
  matched only at the plane stood proud of the head's narrowing neck and flecked.
- Topology payoff: `retopo.wrap` of a base-built body starts from the same template, so the export quads follow.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
from scipy.spatial import cKDTree

from . import retopo

VERSION = 44  # bump when the base field changes: builds and live grids are keyed on it
K = 32
FAR = 0.03  # m
SEAM = 0.012  # m: half-width of the head graft's overlap
LOW_LOOP = 0.004  # the neck loop's least clearance under the graft's overlap (see _neck_tube)
_CACHE: dict = {}


def source(b: dict) -> dict:
    """The body the base starts from, as a template dict (retopo.load_template's): the Blender Studio template
    (b["template"], default), or MakeHuman shaped by its macro targets (b["body"] = {"source": "makehuman", "age",
    "weight", "muscle", "height"})."""
    body = b.get("body") or {}
    if body.get("source") == "makehuman":
        from . import makehuman
        return makehuman.body(body)
    if body.get("source") not in (None, "template"):
        raise ValueError('base body: {"source": "makehuman", ...} or the template (default)')
    return retopo.load_template(b.get("template", "male_stylized"))


def _source_key(b: dict) -> str:
    return json.dumps([b.get("template", "male_stylized"), b.get("body")], sort_keys=True, default=float)


def template_joints(name="male_stylized") -> dict:
    """The body source's joints (centre and .L) as spec joints {name: {"pos", "r"}}, radii from its cross-sections.
    name: a template name or the base dict."""
    b = name if isinstance(name, dict) else {"template": name}
    key = ("joints", _source_key(b))
    if key not in _CACHE:
        tpl = source(b)
        P = tpl["P"]
        out = {}
        J = {k: v for k, v in tpl["J"].items() if not k.endswith(".R")}
        for k, p in J.items():
            d = np.linalg.norm(P - p, axis=1)
            out[k] = {"pos": [round(float(x), 4) for x in p], "r": round(float(np.percentile(d, 0.3)), 4)}
        _CACHE[key] = out
    return json.loads(json.dumps(_CACHE[key]))


def inject(spec: dict) -> dict:
    """The template's joints added to a spec with a "base" where it doesn't give them (its own win)."""
    b = spec.get("base")
    if not b:
        return spec
    if not isinstance(b, dict):
        raise ValueError('base is {"template": "male_stylized", ...}')
    out = dict(spec)
    joints = dict(spec.get("joints") or {})
    tj = template_joints(b)
    for k, j in tj.items():
        joints.setdefault(k, j)
    eb = source(b)["face"].get("eyeball")
    head = head_of({"joints": joints}, b)
    if head is not None:  # the grafted head's own eyes
        eb = {"centre": head["eyes"][0], "r": head["eye_r"]}
        joints.setdefault("eye.L", {"pos": [round(float(x), 4) for x in eb["centre"]], "r": round(eb["r"], 4)})
        for k, j in _landmark_joints(head).items():  # face landmarks to address strokes and paint by
            joints.setdefault(k, j)
        # the mouth closed behind the lips (GNM's mouth bag is left out of the field: its walls made the lips sparkle,
        # and without it parted lips showed a hole into the head)
        iu, il = head["lm68"][62], head["lm68"][66]  # inner lip midpoints
        mc = np.array(joints["lm_mouth_corner.L"]["pos"])
        if float(np.linalg.norm(iu - il)) > 0.0015:  # parted lips (a fill behind closed ones made them pout)
            blobs = dict(out.get("blobs") or spec.get("blobs") or {})
            blobs.setdefault("mouth_fill", {"at": [round(float(x), 4) for x in 0.5 * (iu + il) + [0, 0.012, 0]],
                                            "size": [round(float(mc[0]) * 0.8, 4), 0.008,
                                                     round(float(np.linalg.norm(iu - il)) * 0.5 + 0.001, 4)],
                                            "blend": 0.003})
            out["blobs"] = blobs
    elif eb:  # eye.L: the template eyeball's centre, riding the head joint (paint anchors, the eyes part)
        off = np.array(eb["centre"]) - np.array(tj["head"]["pos"])
        joints.setdefault("eye.L", {"pos": [round(float(x), 4) for x in np.array(joints["head"]["pos"]) + off],
                                    "r": eb["r"]})
    if eb and b.get("eyes"):  # eyeballs as their own part, filling the base's sockets
        blobs = dict(out.get("blobs") or spec.get("blobs") or {})
        blobs.setdefault("eye.L", {"at": "eye.L", "size": [round(float(eb["r"]), 4)] * 3, "part": b["eyes"]})
        out["blobs"] = blobs
    out["joints"] = joints
    return out


def _catmull_clark(V, faces):
    """One Catmull-Clark step on a closed polygon mesh: (verts, quads)."""
    V = np.asarray(V, float)
    nv = len(V)
    fp = np.array([V[f].mean(0) for f in faces])
    edge_id, efaces, ends = {}, [], []
    fe = []
    for fi, f in enumerate(faces):
        ids = []
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            key = (min(a, b), max(a, b))
            if key not in edge_id:
                edge_id[key] = len(ends)
                ends.append(key)
                efaces.append([])
            efaces[edge_id[key]].append(fi)
            ids.append(edge_id[key])
        fe.append(ids)
    ends = np.array(ends)
    ep = np.array([(V[a] + V[b] + fp[fs].sum(0)) / (2 + len(fs)) if len(fs) == 2 else (V[a] + V[b]) / 2
                   for (a, b), fs in zip(ends, efaces)])
    # vertex points: (F + 2R + (n - 3) P) / n
    n = np.zeros(nv)
    Fsum = np.zeros_like(V)
    for fi, f in enumerate(faces):
        for v in f:
            Fsum[v] += fp[fi]
            n[v] += 1
    Rsum = np.zeros_like(V)
    m = np.zeros(nv)
    mid = (V[ends[:, 0]] + V[ends[:, 1]]) / 2
    for k in range(2):
        np.add.at(Rsum, ends[:, k], mid)
        np.add.at(m, ends[:, k], 1)
    vp = (Fsum / n[:, None] + 2 * Rsum / m[:, None] + (n[:, None] - 3) * V) / n[:, None]
    newV = np.r_[vp, ep, fp]
    e0, f0 = nv, nv + len(ep)
    quads = []
    for fi, f in enumerate(faces):
        L = len(f)
        for k in range(L):
            quads.append([f[k], e0 + fe[fi][k], f0 + fi, e0 + fe[fi][k - 1]])
    return newV, quads


def _normals_and_h(V, faces):
    T = np.array([(f[0], f[j], f[j + 1]) for f in faces for j in range(1, len(f) - 1)])
    N = retopo._vnormals(V, T)
    e = np.array(sorted({(min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)])) for f in faces
                         for k in range(len(f))}))
    ln = np.linalg.norm(V[e[:, 0]] - V[e[:, 1]], axis=1)
    s = np.zeros(len(V))
    c = np.zeros(len(V))
    for k in range(2):
        np.add.at(s, e[:, k], ln)
        np.add.at(c, e[:, k], 1)
    return N, s / np.maximum(c, 1)


def surface(spec_expanded: dict, base: dict) -> dict:
    """The posed, subdivided base: {"verts", "faces", "normals", "h", "quads" (the unsubdivided warp), "tree"}.
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
    used["_eyes"] = [spec_expanded["joints"][e]["pos"] for e in ("eye.L", "eye.R") if e in spec_expanded["joints"]]
    key = hashlib.sha1(json.dumps([name, used, settings, VERSION], sort_keys=True, default=float).encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]
    girth = dict(base.get("girth") or {})
    for j, g in list(girth.items()):  # mirrored
        if j.endswith(".L"):
            girth.setdefault(j[:-2] + ".R", g)
    W, *_ = retopo._skeleton_warp(tpl["P"], tpl["J"], spec_expanded, [], girth=girth)
    faces, _, _ = retopo.topology(tpl["L"], tpl["S"])
    soften = base.get("soften")
    if soften:  # (the style's simplify is the head's only: softening the body with it left a ridge at the neck's
        # base, where the soften fades out under the neck loop)
        W = _soften(W, tpl, spec_expanded, float(soften))
    if base.get("push"):
        W = _push(W, tpl, base["push"])
    head = head_of(spec_expanded, base)
    if head is not None:  # a grafted head: the template's own head cut off at a neck loop under its jaw and the
        # neck extruded straight up as quads (its chin and jaw, bigger and lower than a real head's, stood out of the
        # graft band; columns of points built from its vertices left lips and ruffs)
        W, faces = _neck_tube(W, faces, tpl, spec_expanded, head)
    V, F = W, faces
    for _ in range(int(base.get("subdivide", 1))):
        V, F = _catmull_clark(V, F)
    N, h = _normals_and_h(V, F)
    h = h * float(base.get("smooth", 1.0))
    if head is not None:  # one point set: the body under the graft plane, the head over it (the tube tapers to the
        # head's neck at the plane, so they meet). Blending two fields across a band instead showed the band: where
        # the two surfaces differ, the blend weight's gradient tilts the normals (a collar in every render)
        c, pn, _ = head["plane"]
        axis_d = np.linalg.norm(np.cross(V - c, pn), axis=1)
        # both sets overlap across +-SEAM and their points are weighted down across it (C2 ramps): cut hard at the
        # plane, the two surfaces' few-mm mismatch left a ragged crack
        ub = (V - c) @ pn
        kb = (ub <= SEAM) | (axis_d > 0.2)
        H = head["verts"]
        uh = (H - c) @ pn
        kh = uh > -SEAM

        def ramp(x):
            x = np.clip(x, 0, 1)
            return x ** 3 * (x * (6 * x - 15) + 10)
        wb = np.where(axis_d[kb] > 0.2, 1.0, 1 - ramp((ub[kb] + SEAM) / (2 * SEAM)))
        wh = ramp((uh[kh] + SEAM) / (2 * SEAM))
        V = np.r_[V[kb], H[kh]]
        N = np.r_[N[kb], head["normals"][kh]]
        h = np.r_[h[kb], head["h"][kh]]
        wt = np.maximum(np.r_[wb, wh], 1e-4)
    out = {"verts": V, "faces": F, "normals": N, "h": h, "hmax": float(h.max()), "quads": (W, faces), "tree": cKDTree(V),
           "key": key, "head": None, "graft": head, "wt": wt if head is not None else None,
           "seam": (head["plane"][0], head["plane"][1], 0.2) if head is not None else None}
    if len(_CACHE) > 8:
        _CACHE.pop(next(k for k in _CACHE if not isinstance(k, tuple)))
    _CACHE[key] = out
    return out


GNM = "gnm/shape/data/versions/v3_0/gnm_head.npz"  # under workspace/_templates/gnm (Apache 2.0, see SOURCE.txt)
GNM_CUT = 0.19  # GNM's own frame (Y up): the graft plane's height, above its bib's open edge (0.135), under its chin
GNM_BAND = 0.028
GNM_TILT = 20.0  # degrees


def head_of(s: dict, base: dict):
    """The grafted head (gnm_head) for a base with "head": {"source": "gnm", ...}, placed on the template's eye
    midpoint (the head joint's ride) and the neck -> head direction; None without one. Cached."""
    head = base.get("head")
    if not head:
        return None
    if head.get("source", "gnm") != "gnm":
        raise ValueError('base head: {"source": "gnm", ...} (the only head source so far)')
    tpl = source(base)
    tj = template_joints(base)
    J = s["joints"]
    eb = np.array((tpl["face"].get("eyeball") or {}).get("centre") or tpl["face"]["landmarks"]["eye.L"]) * [0, 1, 1]
    mid = np.array(J["head"]["pos"], float) + eb - np.array(tj["head"]["pos"])
    up = np.array(J["head"]["pos"], float) - np.array(J["neck"]["pos"], float)
    up0 = np.array(tj["head"]["pos"]) - np.array(tj["neck"]["pos"])
    up = retopo._rot_between(_unit(up0), _unit(up)) @ np.array([0, 0, 1.0])
    st = base.get("style") or {}
    if st:  # the stylisation layer, reusable across characters: bigger eyes, a bigger head, simpler planes
        head = {**head, "eyes": float(head.get("eyes", 1.0)) * float(st.get("eyes", 1.0)),
                "scale": float(head.get("scale", 1.4)) * float(st.get("head", 1.0)),
                "simplify": float(head.get("simplify", 0.0)) + float(st.get("simplify", 0.0))}
    key = ("head", json.dumps([head, mid.round(5).tolist(), up.round(5).tolist()], sort_keys=True))
    if key not in _CACHE:
        _CACHE[key] = gnm_head(head, mid, up)
    return _CACHE[key]


def _unit(v):
    return v / np.linalg.norm(v)


# face landmarks as joints (iBUG 68 order, GNM's head_sparse_68: barycentric on its mesh), subject's left = ".L"
LANDMARKS = {"lm_chin": 8, "lm_nose_tip": 30, "lm_nose_base": 33, "lm_nose_bridge": 27, "lm_lip_upper": 51,
             "lm_lip_lower": 57, "lm_mouth_corner.L": 54, "lm_nostril.L": 35, "lm_eye_inner.L": 42,
             "lm_eye_outer.L": 45, "lm_brow_inner.L": 22, "lm_brow_mid.L": 24, "lm_brow_outer.L": 26,
             **{f"lm_jaw_{k}.L": 16 - k for k in range(8)}}


def _landmark_joints(head: dict) -> dict:
    lm = head["lm68"]
    out = {}
    for name, i in LANDMARKS.items():
        p = lm[i]
        out[name] = {"pos": [round(float(x), 4) for x in p], "r": 0.005}
    for name in ("lm_lid_upper.L", "lm_lid_lower.L"):
        i, j = (43, 44) if "upper" in name else (46, 47)
        out[name] = {"pos": [round(float(x), 4) for x in 0.5 * (lm[i] + lm[j])], "r": 0.004}
    return out


def _push(W, tpl, pushes):
    """Big soft volume changes on the base mesh itself: base["push"] = [{"at": [x, y, z], "radius": m, "amount": m},
    ...] moves vertices along their normals by amount x a smooth bump (1 at the centre, 0 at radius); a centre with
    x > 0 is mirrored. A belly or love handles: blobs with big blends or deep clay strokes reach past where the base's
    field is exact (a few cm off its surface) and came out as plates."""
    T = retopo.tris(tpl["L"], tpl["S"])
    N = retopo._vnormals(W, T)
    D = np.zeros_like(W)
    for p in pushes:
        c, r, a = np.array(p["at"], float), float(p["radius"]), float(p["amount"])
        for cc in ([c, c * [-1, 1, 1]] if abs(c[0]) > 1e-6 else [c]):
            x = np.clip(np.linalg.norm(W - cc, axis=1) / r, 0, 1)
            D += (a * (1 - x * x) ** 2)[:, None] * N
    return W + D


def _soften(W, tpl, s, amount):
    """Muscle definition smoothed away (Taubin, so the volume stays): the template is a heroic physique (abs, pecs,
    big deltoids); amount ~ 1 softens it to an ordinary body, 2 to a soft one. Hands, feet and the head are left
    alone (fading over a few cm from the wrists, ankles and neck)."""
    E = retopo.edges(tpl["L"], tpl["S"])
    deg = np.bincount(E.ravel(), minlength=len(W))
    J = s["joints"]
    w = np.ones(len(W))
    for side in "LR":  # past the wrist along the forearm (the hand), and below the ankle (the foot)
        e, wr = np.array(J[f"elbow.{side}"]["pos"]), np.array(J[f"wrist.{side}"]["pos"])
        ax = _unit(wr - e)
        near = np.linalg.norm(W - wr, axis=1) < 0.25
        w *= np.where(near, np.clip(((wr - W) @ ax + 0.01) / 0.05, 0, 1), 1.0)
        an = np.array(J[f"ankle.{side}"]["pos"])
        near = (np.abs(W[:, 0] - an[0]) < 0.12) & (W[:, 2] < an[2] + 0.1)
        w *= np.where(near, np.clip((W[:, 2] - an[2] - 0.01) / 0.05, 0, 1), 1.0)
    neck = np.array(J["neck"]["pos"])
    w *= np.clip((neck[2] + 0.04 - W[:, 2]) / 0.06, 0, 1)
    w = w[:, None]
    X = W.copy()
    for _ in range(int(round(10 * amount))):
        for lam in (0.5, -0.53):
            X = X + lam * w * retopo._lap(X, E, deg)
    return X


def _neck_loops(tpl):
    """The template's closed edge loops round the neck under its chin (loops there tilt: low at the throat, high at
    the nape), highest first: ([loops], the head's top vertex)."""
    key = ("neck_loops", tpl["name"], len(tpl["P"]), float(tpl["P"][:, 2].max()))
    if key not in _CACHE:
        P = tpl["P"]
        faces, nb, ef = retopo.topology(tpl["L"], tpl["S"])
        eye = np.array(tpl["face"]["landmarks"]["eye.L"])
        chin_z = tpl.get("chin_z", eye[2] - 0.15)
        near = set(np.flatnonzero((P[:, 2] > chin_z - 0.14) & (P[:, 2] < chin_z + 0.05) & (np.abs(P[:, 0]) < 0.14)))
        top = int(np.argmax(P[:, 2]))
        found = []
        for path in retopo._loops_round(P, faces, nb, ef, near, 200):
            Q = P[path]
            ang = np.arctan2(Q[:, 1] - Q[:, 1].mean(), Q[:, 0])
            wn = np.sum((np.diff(np.r_[ang, ang[:1]]) + np.pi) % (2 * np.pi) - np.pi) / (2 * np.pi)
            if abs(round(wn)) != 1 or Q[:, 2].max() > chin_z - 0.025 or np.abs(Q[:, 0]).max() > 0.12:
                continue
            found.append((float(Q[:, 2].max()), path))
        found.sort(key=lambda f: -f[0])
        _CACHE[key] = ([f[1] for f in found], top)
    return _CACHE[key]


def _neck_tube(W, faces, tpl, s, head, step=0.006):
    """Everything above the neck loop dropped; the loop extruded along the neck -> head axis in rings `step` apart up
    past the head's top and capped (quads; subdivided with the rest). Each ring vertex tapers (smoothstep) from the
    loop's radius to the grafted head's neck radius at its angle, reaching it at the graft plane: a straight tube
    read as a collar with an edge at each end."""
    loops, top = _neck_loops(tpl)
    pc, pn, band = head["plane"]
    # the highest loop wholly LOW_LOOP under the overlap with the head: a loop reaching into it (a bigger head's plane
    # sits lower) left the taper no room, and the seam showed as a ridge with flecks
    loop = next((lp for lp in loops if ((W[lp] - pc) @ pn).max() < -(SEAM + LOW_LOOP)), loops[-1])
    J = s["joints"]
    n = _unit(np.array(J["head"]["pos"], float) - np.array(J["neck"]["pos"], float))
    ring0 = W[loop]
    c0 = ring0.mean(0)
    e1 = _unit(np.cross(n, [0, 1.0, 0]) if abs(n[1]) < 0.9 else np.cross(n, [1.0, 0, 0]))
    e2 = np.cross(n, e1)
    q0 = ring0 - c0 - np.outer((ring0 - c0) @ n, n)
    th = np.arctan2(q0 @ e2, q0 @ e1)
    r0 = np.linalg.norm(q0, axis=1)
    hp = float((pc - c0) @ n)  # the plane's height over the loop's centre, along the axis
    H = head["verts"]
    bins = 36
    x_th = (th + np.pi) / (2 * np.pi) * bins - 0.5
    d = q0 / np.maximum(r0, 1e-9)[:, None]
    foot0 = c0 + np.outer((ring0 - c0) @ n, n)  # each loop vertex's axis point

    def head_r(u):
        """The head's neck radius per loop vertex (its angle about the axis) in a slice at u along the plane's
        normal: its vertices within a few mm, median per angle bin."""
        sl = H[np.abs((H - pc) @ pn - u) < 0.004]
        qs = sl - c0 - np.outer((sl - c0) @ n, n)
        ang = np.arctan2(qs @ e2, qs @ e1)
        rad = np.linalg.norm(qs, axis=1)
        k = ((ang + np.pi) / (2 * np.pi) * bins).astype(int) % bins
        rb = np.array([np.median(rad[k == i]) if (k == i).sum() else np.nan for i in range(bins)])
        ok = np.isfinite(rb)
        rb = np.interp(np.arange(bins), np.flatnonzero(ok), rb[ok], period=bins)
        return np.interp(x_th, np.arange(bins), rb, period=bins)
    # through the whole overlap with the head (u in -SEAM..+SEAM about the plane) the tube follows the head's own
    # neck, slice by slice: matched only at the plane, the tube stood up to 1 cm proud of the head's narrowing neck
    # just above it and the blended points made flecks; below the overlap a cubic Hermite from the loop's radius and
    # slope
    us = np.linspace(-SEAM, SEAM, 9)
    R = np.array([head_r(u) for u in us])  # (levels, loop)
    npn = float(n @ pn)
    h_start = ((pc - foot0 - R[0][:, None] * d) @ pn - SEAM) / npn  # the height where each vertex enters the overlap
    s1 = (R[1] - R[0]) / ((us[1] - us[0]) / npn)  # the head's slope there, per metre of height
    height = float((W[top] - c0) @ n) + 0.02
    # the body's slope under the loop (radius change per metre of height), so the tube leaves the loop along the
    # neck's own surface: starting straight up it left a crease round the neck's base
    below = ring0 - 0.012 * n
    rest = np.setdiff1d(np.arange(len(W)), loop)
    Wb = W[rest][cKDTree(W[rest]).query(below)[1]]
    qb = Wb - c0 - np.outer((Wb - c0) @ n, n)
    s0 = np.clip((r0 - np.linalg.norm(qb, axis=1)) / np.maximum((ring0 - Wb) @ n, 1e-3), -1.5, 1.5)
    L = np.maximum(h_start, 1e-3)
    rings = []
    for kk in range(int(height / step) + 1):
        hh = kk * step
        t = np.clip(hh / L, 0, 1)
        h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        r = h00 * r0 + h10 * L * s0 + h01 * R[0] + h11 * L * s1
        over = hh > L  # in the overlap: the head's radius at this vertex's u
        if over.any():
            u = (hh - L[over]) * npn - SEAM
            j = np.clip(np.searchsorted(us, u) - 1, 0, len(us) - 2)
            f = np.clip((u - us[j]) / (us[j + 1] - us[j]), 0, 1)
            cols = np.flatnonzero(over)
            r[over] = (1 - f) * R[j, cols] + f * R[j + 1, cols]
        rings.append(foot0 + hh * n + r[:, None] * d)
    tip = rings[-1].mean(0) + step * n
    V, fl, _, _ = retopo._stitch(W, faces, {"neck": (list(loop), top, (rings, tip))})
    return V, fl


def _gnm_data():
    if "gnm" not in _CACHE:
        from . import store
        path = store.HOME / "_templates" / "gnm" / GNM
        if not path.exists():
            raise FileNotFoundError(f"the GNM head needs {path} (github.com/google/GNM, Apache 2.0)")
        z = np.load(path)
        names = list(z["vertex_group_names"])
        _CACHE["gnm"] = {k: z[k] for k in ("template_vertex_positions", "vertex_identity_basis", "expression_basis",
                                           "template_joint_positions", "joint_identity_basis", "quads",
                                           "identity_names", "expression_names")}
        # the skin without the mouth bag: its walls sit a few mm inside the lips and made the IMLS sparkle there
        _CACHE["gnm"]["skin"] = (z["vertex_groups"][names.index("skin")] > 0.5) & ~(z["vertex_groups"][names.index("mouth_sock")] > 0.5)
        rows = (path.parent.parent.parent / "landmarks" / "head_sparse_68.txt").read_text().split("\n")
        _CACHE["gnm"]["lm68"] = [[float(x) for x in r.split()] for r in rows if r.strip()]
        _CACHE["gnm"]["eye"] = [z["vertex_groups"][names.index(g)] > 0.5 for g in ("left_eye", "right_eye")]
    return _CACHE["gnm"]


def _gnm_coeffs(names, given, seed=None, spread=1.0):
    c = np.zeros(len(names))
    if seed is not None:
        rng = np.random.default_rng(int(seed))
        head = np.array([n.startswith("head") for n in names])
        c[head] = rng.normal(0, spread, head.sum())
    for k, v in (given or {}).items():
        c[list(names).index(k)] = float(v)
    return c


FIT_KEYS = ("face_width", "jaw_width", "chin_width", "eye_chin", "eye_mouth", "eye_nose")


def _measures(V, J, lm):
    """Front-view face proportions (GNM frame, Y up), in metres: widths across the jaw line at the ears, at the
    jaw's angle and at the chin; drops from the eye line to the chin, the lower lip and the nose base; interocular."""
    io = J[2][0] - J[3][0]
    ey = 0.5 * (J[2][1] + J[3][1])
    return np.array([lm(16)[0] - lm(0)[0], lm(12)[0] - lm(4)[0], lm(10)[0] - lm(6)[0], ey - lm(8)[1],
                     ey - lm(57)[1], ey - lm(33)[1], io])


def fit_identity(target: dict, n: int = 80, lam: float = 2e-6) -> dict:
    """GNM head components (the first n) that give these face proportions, in interocular units (FIT_KEYS; e.g.
    {"face_width": 2.1, "jaw_width": 1.6}; keys left out keep the mean's), interocular held: ridge least squares
    on the landmark measurements (linear in the identity), components clipped to +-2.5 sigma. Cached."""
    key = ("fit", json.dumps(target, sort_keys=True), n)
    if key in _CACHE:
        return _CACHE[key]
    g = _gnm_data()
    V0, J0 = g["template_vertex_positions"].astype(float), g["template_joint_positions"].astype(float)

    def meas(V, J):
        return _measures(V, J, lambda i: sum(w * V[int(v)] for v, w in zip(g["lm68"][i][0::2], g["lm68"][i][1::2])))
    m0 = meas(V0, J0)
    head = [i for i, nm in enumerate(g["identity_names"]) if str(nm).startswith("head")][:n]
    A = np.array([meas(V0 + g["vertex_identity_basis"][i], J0 + g["joint_identity_basis"][i]) - m0 for i in head]).T
    unknown = set(target) - set(FIT_KEYS)
    if unknown:
        raise ValueError(f"base head fit: unknown {sorted(unknown)}; use {FIT_KEYS} (interocular units)")
    t = np.array([float(target.get(k, m0[j] / m0[-1])) for j, k in enumerate(FIT_KEYS)] + [1.0]) * m0[-1]
    w = np.array([1.0] * len(FIT_KEYS) + [2.0])
    c = np.linalg.solve((A * w[:, None]).T @ (A * w[:, None]) + lam * np.eye(len(head)), (A * w[:, None]).T @ ((t - m0) * w))
    out = {str(g["identity_names"][i]): float(v) for i, v in zip(head, np.clip(c, -2.5, 2.5))}
    _CACHE[key] = out
    return out


def gnm_head(head: dict, eye_mid: np.ndarray, up: np.ndarray) -> dict:
    """Google GNM's head skin, posed for the base: identity/expression applied (head["identity"] {name: value},
    head["seed"] for a random identity), eyes scaled about their centres (head["eyes"], e.g. 1.45: a stylised look),
    the head narrowed across (head["narrow"]), then scaled (head["scale"], default 1.4: the template's head height)
    and placed with its eye midpoint on eye_mid, its up along `up`. Returns the skin IMLS arrays, eye centres and
    radius, and the graft plane (point, normal, band) in world space."""
    g = _gnm_data()
    ident = dict(fit_identity(head["fit"])) if head.get("fit") else {}
    ident.update(head.get("identity") or {})  # given components win over fitted ones
    ci = _gnm_coeffs(g["identity_names"], ident, head.get("seed"), head.get("spread", 1.0))
    ce = _gnm_coeffs(g["expression_names"], head.get("expression"))
    V = g["template_vertex_positions"] + np.tensordot(ci, g["vertex_identity_basis"], 1) + \
        np.tensordot(ce, g["expression_basis"], 1)
    J = g["template_joint_positions"] + np.tensordot(ci, g["joint_identity_basis"], 1)
    V, J = V.astype(float), J.astype(float)
    k_eye = float(head.get("eyes", 1.0))
    r_eye = [float(np.median(np.linalg.norm(V[m] - J[2 + i], axis=1))) for i, m in enumerate(g["eye"])]
    if k_eye != 1.0:  # the eyes and the orbits round them scaled about each eye centre, fading out over ~2 radii
        for j in (2, 3):
            d = np.linalg.norm(V - J[j], axis=1)
            V = J[j] + (V - J[j]) * (1 + (k_eye - 1) * np.exp(-(d / (2.2 * r_eye[j - 2])) ** 2))[:, None]
    mid = 0.5 * (J[2] + J[3])
    V[:, 0] = mid[0] + (V[:, 0] - mid[0]) * float(head.get("narrow", 1.0))
    J[:, 0] = mid[0] + (J[:, 0] - mid[0]) * float(head.get("narrow", 1.0))
    R = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # GNM: Y up, facing +Z -> Z up, facing -Y
    up = up / np.linalg.norm(up)
    R = retopo._rot_between(np.array([0, 0, 1.0]), up) @ R
    s = float(head.get("scale", 1.4))

    def place(X):
        return eye_mid + s * (X - mid) @ R.T
    # the graft plane through the neck's axis, tilted GNM_TILT down at the front: level, it ran into the jaw under the
    # chin (the chin sits ~6 mm over GNM_CUT) while the back must stay above the bib's open edge
    cut = place(np.array([mid[0], GNM_CUT, J[0][2]]))
    ta = np.radians(GNM_TILT)
    pn = R @ np.array([0.0, np.cos(ta), np.sin(ta)])
    lm = place(np.array([sum(float(w) * V[int(v)] for v, w in zip(row[0::2], row[1::2])) for row in g["lm68"]]))
    skin = g["skin"]
    Q = g["quads"][skin[g["quads"]].all(1)]
    remap = -np.ones(len(V), int)
    remap[np.flatnonzero(skin)] = np.arange(skin.sum())
    W = place(V[skin])
    faces = [list(q) for q in remap[Q]]
    if float(head.get("simplify", 0.0)) > 0:  # simpler planes (a feature-animation face): small forms smoothed away,
        # the lid rims, lips and nostrils kept (their weight fades to 0 within ~1.5 cm of those landmarks)
        E = retopo.edges(np.array([v for f in faces for v in f]), np.array([len(f) for f in faces]))
        deg = np.bincount(E.ravel(), minlength=len(W))
        keep = [lm[i] for i in (37, 38, 40, 41, 43, 44, 46, 47, 48, 51, 54, 57, 62, 66, 31, 33, 35)]
        dk = np.min([np.linalg.norm(W - p, axis=1) for p in keep], axis=0)
        wv = np.clip((dk - 0.006 * s) / (0.015 * s), 0, 1)
        # and the neck left as it is near the graft plane (its open edge moved under the smoothing: a ridge and
        # flecks round the neck's base, where the body's tube must meet it)
        wv = (wv * np.clip(((W - cut) @ pn - 0.02) / 0.03, 0, 1))[:, None]
        for _ in range(int(round(12 * float(head["simplify"])))):
            for lam in (0.5, -0.53):
                W = W + lam * wv * retopo._lap(W, E, deg)
    for _ in range(int(head.get("subdivide", 1))):
        W, faces = _catmull_clark(W, faces)
    N, h = _normals_and_h(W, faces)
    h = h * float(head.get("smooth", 1.0))
    return {"verts": W, "faces": faces, "normals": N, "h": h, "hmax": float(h.max()), "tree": cKDTree(W),
            "eyes": [place(J[2]), place(J[3])], "eye_r": 1.04 * s * k_eye * float(np.mean(r_eye)),  # through the lids' lining (it lies at 0.9-1 x GNM's eye radius): at the lining, the two coincided and flecked the rims
             "lm68": lm,
            "plane": (cut, pn, s * GNM_BAND)}


def _imls(X, pr, k=K):
    """IMLS over one surface's vertices at points X (n, 3)."""
    d, i = pr["tree"].query(X, k=k)
    P, N, h = pr["verts"][i], pr["normals"][i], pr["h"][i]
    # the kernel widens with distance (h at least 0.7 x the nearest vertex's distance): off the surface the field
    # is a plane fit over a patch as wide as the distance, so shells (clothes, 5-15 mm out) are smooth offsets
    # (with a fixed h the far field was the distance to the nearest vertex: a shirt came out dimpled)
    h = np.maximum(h, 0.7 * d[:, :1])
    s = ((X[:, None, :] - P) * N).sum(-1)
    q = np.clip(d / (2 * h), 0.0, 1.0)  # Wendland C2, support 2 h: compact, so a vertex entering or leaving the
    w = (1 - q) ** 4 * (4 * q + 1)      # k nearest carries no weight (a Gaussian's tail there speckled the creases)
    if pr.get("wt") is not None:  # per-point weights (a grafted head's seam)
        w = w * pr["wt"][i]
    ws = w.sum(1)
    imls = (w * s).sum(1) / np.maximum(ws, 1e-300)
    far = np.sign(imls) * np.maximum(d[:, 0] - pr["hmax"], 0.0)
    t = np.clip((d[:, 0] - FAR) / FAR, 0.0, 1.0)  # past FAR from every vertex: conservative distance, for culling
    return np.where(ws > 1e-12, (1 - t) * imls + t * far, far)


def sd_base(p: np.ndarray, pr: dict) -> np.ndarray:
    """IMLS distance to the base (see the module docstring). A grafted head is part of the same point set."""
    return _sd_body(p, pr)


def _sd_body(p: np.ndarray, pr: dict) -> np.ndarray:
    X = p.reshape(-1, 3)
    if pr.get("seam") is None:
        return _imls(X, pr).reshape(p.shape[:-1])
    # near a head graft's seam the two point sets overlap with ramped weights; there the k nearest must reach both
    # (the head's points are twice as dense: 32 nearest were all one set's, and the surface stepped where it switched)
    c, pn, r = pr["seam"]
    near = np.abs((X - c) @ pn) < 2 * SEAM
    near &= np.linalg.norm(np.cross(X - c, pn), axis=1) < r
    out = np.empty(len(X))
    if (~near).any():
        out[~near] = _imls(X[~near], pr)
    if near.any():
        out[near] = _imls(X[near], pr, k=4 * K)
    return out.reshape(p.shape[:-1])
