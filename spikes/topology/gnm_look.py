"""gnm_look.py out.png: Google GNM's head (mean, a sampled identity, and a stylised mean: eyes x1.25, planes
simplified) next to the Blender Studio template's head, clay, front / three-quarter / side. GNM data in
workspace/_templates/gnm (Apache 2.0)."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import topo_eval as E  # noqa: F401  (blender job runner)
from hifipushie import retopo

GNM = Path("/home/joe/dev/hifipushie/workspace/_templates/gnm/gnm/shape/data/versions/v3_0/gnm_head.npz")
OUT = Path(sys.argv[1])
TMP = OUT.parent


def gnm_mesh(identity=None, expression=None, stylise=False):
    z = np.load(GNM)
    V = z["template_vertex_positions"].astype(np.float64)
    if identity is not None:
        V = V + np.tensordot(identity, z["vertex_identity_basis"], 1)
    if expression is not None:
        V = V + np.tensordot(expression, z["expression_basis"], 1)
    names = list(z["vertex_group_names"])
    keep = (z["vertex_groups"][names.index("skin")] > 0.5) | (z["vertex_groups"][names.index("eyes")] > 0.5)
    if stylise:  # eyes (and the orbit round them) scaled up about each eye joint, fading out over 45 mm
        for j in (2, 3):
            c = z["template_joint_positions"][j]
            d = np.linalg.norm(V - c, axis=1)
            k = 1 + 0.25 * np.exp(-(d / 0.03) ** 2)
            V = c + (V - c) * k[:, None]
    Q = z["quads"]
    Q = Q[keep[Q].all(1)]
    V = np.c_[V[:, 0], -V[:, 2], V[:, 1]]  # GNM: Y up, facing +Z -> ours: Z up, facing -Y
    return V, Q


def template_head():
    t = retopo.load_template()
    V = t["P"]
    faces, _, _ = retopo.topology(t["L"], t["S"])
    F = [f for f in faces if (V[f][:, 2] > 1.43).all()]
    return V, F


def save(V, F, path):
    np.savez(path, verts=V, loops=np.array([v for f in F for v in f]), sizes=np.array([len(f) for f in F]))


def render(path, center, scale, tag):
    vs = []
    for n, d in (("front", [0, -1, 0]), ("tq", [0.7, -1, 0.15]), ("side", [1, 0, 0])):
        vs.append({"dir": d, "up": [0, 0, 1], "center": list(map(float, center)), "scale": scale, "wire": False,
                   "out": str(TMP / f"g_{tag}_{n}.png")})
    E.blender({"mode": "render", "mesh": str(path), "views": vs, "size": 420}, TMP)
    return [Image.open(v["out"]).convert("RGB") for v in vs]


rows = []
Vt, Ft = template_head()
save(Vt, Ft, TMP / "g_tpl.npz")
ct = np.array([0, -0.03, 1.64])
rows.append(("Blender Studio template (CC0)", render(TMP / "g_tpl.npz", ct, 0.34, "tpl")))
rng = np.random.default_rng(3)
z = np.load(GNM)
idn = np.zeros(len(z["identity_names"]))
for label, kw in (("GNM mean (Apache 2.0)", {}),
                  ("GNM sampled identity", {"identity": np.where([n.startswith("head") for n in z["identity_names"]],
                                                                 rng.normal(0, 1.0, len(idn)), 0.0)}),
                  ("GNM mean, stylised: eyes x1.25", {"stylise": True})):
    V, Q = gnm_mesh(**kw)
    save(V, Q, TMP / "g_gnm.npz")
    c = 0.5 * (V.min(0) + V.max(0))
    rows.append((label, render(TMP / "g_gnm.npz", c + np.array([0, 0, -0.01]), 0.34 * (V.max(0) - V.min(0))[2] / 0.35, label[:8].replace(" ", ""))))
W = 420
im = Image.new("RGB", (W * 3, (W + 24) * len(rows)), (30, 31, 35))
d = ImageDraw.Draw(im)
for i, (label, ims) in enumerate(rows):
    d.text((8, i * (W + 24) + 6), label, fill=(230, 230, 230))
    for j, x in enumerate(ims):
        im.paste(x, (j * W, i * (W + 24) + 24))
im.save(OUT)
print(OUT, "gnm verts", len(z["template_vertex_positions"]))
