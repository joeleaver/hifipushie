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
- Topology payoff: `retopo.wrap` of a base-built body starts from the same template, so the export quads follow.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
from scipy.spatial import cKDTree

from . import retopo

K = 32
FAR = 0.03  # m
_CACHE: dict = {}


def template_joints(name: str = "male_stylized") -> dict:
    """The template's joints (centre and .L) as spec joints {name: {"pos", "r"}}, radii from its cross-sections."""
    key = ("joints", name)
    if key not in _CACHE:
        tpl = retopo.load_template(name)
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
    name = b.get("template", "male_stylized")
    joints = dict(spec.get("joints") or {})
    tj = template_joints(name)
    for k, j in tj.items():
        joints.setdefault(k, j)
    eb = retopo.load_template(name)["face"].get("eyeball")
    if eb:  # eye.L: the template eyeball's centre, riding the head joint (paint anchors, the eyes part)
        off = np.array(eb["centre"]) - np.array(tj["head"]["pos"])
        joints.setdefault("eye.L", {"pos": [round(float(x), 4) for x in np.array(joints["head"]["pos"]) + off],
                                    "r": eb["r"]})
        if b.get("eyes"):  # eyeballs as their own part, filling the base's open sockets
            blobs = dict(spec.get("blobs") or {})
            blobs.setdefault("eye.L", {"at": "eye.L", "size": [eb["r"]] * 3, "part": b["eyes"]})
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
    name = base.get("template", "male_stylized")
    tpl = retopo.load_template(name)
    used = {}
    for k in tpl["J"]:
        for n in (k, retopo._model_name(k)):
            if n in spec_expanded["joints"]:
                used[k] = spec_expanded["joints"][n]["pos"]
                break
    settings = {k: base.get(k) for k in ("girth", "subdivide", "smooth")}
    key = hashlib.sha1(json.dumps([name, used, settings], sort_keys=True, default=float).encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]
    girth = dict(base.get("girth") or {})
    for j, g in list(girth.items()):  # mirrored
        if j.endswith(".L"):
            girth.setdefault(j[:-2] + ".R", g)
    W, *_ = retopo._skeleton_warp(tpl["P"], tpl["J"], spec_expanded, [], girth=girth)
    faces, _, _ = retopo.topology(tpl["L"], tpl["S"])
    V, F = W, faces
    for _ in range(int(base.get("subdivide", 1))):
        V, F = _catmull_clark(V, F)
    N, h = _normals_and_h(V, F)
    h = h * float(base.get("smooth", 1.0))
    out = {"verts": V, "faces": F, "normals": N, "h": h, "hmax": float(h.max()), "quads": (W, faces), "tree": cKDTree(V),
           "key": key}
    if len(_CACHE) > 8:
        _CACHE.pop(next(k for k in _CACHE if not isinstance(k, tuple)))
    _CACHE[key] = out
    return out


def sd_base(p: np.ndarray, pr: dict) -> np.ndarray:
    """IMLS distance to the base (see the module docstring)."""
    shape = p.shape[:-1]
    X = p.reshape(-1, 3)
    d, i = pr["tree"].query(X, k=K)
    P, N, h = pr["verts"][i], pr["normals"][i], pr["h"][i]
    # the kernel widens with distance (h at least 0.7 x the nearest vertex's distance): off the surface the field
    # is a plane fit over a patch as wide as the distance, so shells (clothes, 5-15 mm out) are smooth offsets
    # (with a fixed h the far field was the distance to the nearest vertex: a shirt came out dimpled)
    h = np.maximum(h, 0.7 * d[:, :1])
    s = ((X[:, None, :] - P) * N).sum(-1)
    q = np.clip(d / (2 * h), 0.0, 1.0)  # Wendland C2, support 2 h: compact, so a vertex entering or leaving the
    w = (1 - q) ** 4 * (4 * q + 1)      # k nearest carries no weight (a Gaussian's tail there speckled the creases)
    ws = w.sum(1)
    imls = (w * s).sum(1) / np.maximum(ws, 1e-300)
    far = np.sign(imls) * np.maximum(d[:, 0] - pr["hmax"], 0.0)
    t = np.clip((d[:, 0] - FAR) / FAR, 0.0, 1.0)  # past FAR from every vertex: conservative distance, for culling
    out = np.where(ws > 1e-12, (1 - t) * imls + t * far, far)
    return out.reshape(shape)
