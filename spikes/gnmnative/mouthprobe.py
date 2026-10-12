"""gnmnative: GNM's mouth pieces: are they closed meshes, where the tongue's tip is and which tongue components move
it, the sock's extent, and how the teeth sit behind the lips on built heads (mouthprobe.py [model ...])."""
import sys

import numpy as np

from hifipushie import base as basemod
from hifipushie import onemesh, store

g = basemod._gnm_data()
G = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
T = g["template_vertex_positions"].astype(float)
Q = np.asarray(g["quads"])
E = g["expression_basis"]
enm = [str(x) for x in g["expression_names"]]
for nm in ("upper_teeth_and_gums", "lower_teeth_and_gums", "tongue", "mouth_sock"):
    m = G[nm]
    q = Q[m[Q].all(1)]
    e = np.sort(np.concatenate([q[:, [0, 1]], q[:, [1, 2]], q[:, [2, 3]], q[:, [3, 0]]]), 1)
    u, cnt = np.unique(e, axis=0, return_counts=True)
    ln = np.linalg.norm(T[u[:, 0]] - T[u[:, 1]], axis=1) * 1000
    print(f"{nm:22s} verts {m.sum()} quads {len(q)} edges {len(u)} boundary edges {(cnt == 1).sum()} non-manifold {(cnt > 2).sum()} "
          f"edge mm median {np.median(ln):.2f} max {ln.max():.2f} bbox mm {((T[m].max(0) - T[m].min(0)) * 1000).round(1)}")
    if nm.endswith("gums"):
        tq = Q[(m & G["teeth"])[Q].all(1)]
        gq = Q[(m & G["gums"])[Q].all(1)]
        both = m & G["teeth"] & G["gums"]
        print(f"   teeth-only quads {len(tq)}, gum-only quads {len(gq)}, quads in neither set alone {len(q) - len(tq) - len(gq)}, "
              f"shared verts {both.sum()}")
# the tongue: tip = the most forward vertex; what each component does to it
tg = np.flatnonzero(G["tongue"])
tip = tg[np.argmax(T[tg, 2])]
print("tongue tip vertex", tip, (T[tip] * 1000).round(1), "lip midpoint z", "(lm62)", end=" ")
lm = np.array([sum(float(w) * T[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]])
print((lm[62] * 1000).round(1), (lm[66] * 1000).round(1), "front teeth z max", (T[G["upper_teeth_and_gums"]][:, 2].max() * 1000).round(1))
ti = [i for i, n in enumerate(enm) if n.startswith("tongue")]
rows = sorted(((enm[i], E[i][tip] * 1000, float(np.abs(E[i]).max() * 1000)) for i in ti), key=lambda t: -abs(t[1][2]))
for n, d, mx in rows[:10]:
    print(f"   {n:12s} tip move mm x {d[0]:+.2f} y {d[1]:+.2f} z {d[2]:+.2f}   max vertex {mx:.2f}")
# lower-face comps that move the tongue most (the jaw carries it)
for name in sys.argv[1:]:
    b = store.load(name)["base"]
    ht = onemesh.head_rest(b)
    W = ht["gnm_world"]
    fwd = np.asarray(ht["forward"], float)
    lmw = np.asarray(ht["lm68"], float)
    up_t, lo_t = W[G["upper_teeth_and_gums"] & G["teeth"]], W[G["lower_teeth_and_gums"] & G["teeth"]]
    print(f"{name}: lip front (lm51 / lm57) ahead of the teeth's front (mm): upper {((lmw[51] - up_t[np.argmax(up_t @ fwd)]) @ fwd) * 1000:.1f}, "
          f"lower {((lmw[57] - lo_t[np.argmax(lo_t @ fwd)]) @ fwd) * 1000:.1f}; inner lips (62 / 66) ahead of the teeth: "
          f"{((lmw[62] - up_t[np.argmax(up_t @ fwd)]) @ fwd) * 1000:.1f} / {((lmw[66] - lo_t[np.argmax(lo_t @ fwd)]) @ fwd) * 1000:.1f}; "
          f"upper incisors' edge below the lips' line: {(0.5 * (lmw[62] + lmw[66])[2] - up_t[:, 2].min()) * 1000:.1f} mm; "
          f"teeth outside the skin: ", end="")
    # which teeth vertices lie outside the head's skin (in front of the lips): by the skin's field
    from hifipushie import spec as specmod
    sp = store.load(name)
    prims = [p for p in specmod.compile_prims(sp) if p.part == "body"]
    from hifipushie import sdf
    d = sdf.field_at(prims, np.r_[up_t, lo_t], clip=False)
    print(f"{(d > 0).sum()} of {len(d)} vertices (max {d.max() * 1000:.2f} mm out)")
