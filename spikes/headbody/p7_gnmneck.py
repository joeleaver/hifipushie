"""p7_gnmneck.py: GNM's OWN neck and bib: girths by ring for the class means and the models' identities, which identity
components carry a model's neck girth, GNM's own chin -> pit of the throat and where its trapezius leaves the neck;
PIL tiles of the raw template with its bib."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "onemesh"))
import wire
from hifipushie import base as B, blockin as bi, onemesh, store
from p1_measure import gnm_eval, lm, g, SKIN
from p2_neck import ring_loop, lev

OUT = "/mnt/data/hifipushie/headbody/out"
D = bi.data()
IB = np.asarray(g["vertex_identity_basis"])
names = [str(n) for n in g["identity_names"]]


def girth(V, k):
    X = V[ring_loop(k)]
    return float(np.linalg.norm(X - np.roll(X, -1, 0), axis=1).sum())


ids = {"template": {}, "female class mean": {f"head_{i:03d}": float(x) for i, x in enumerate(D["m_f"][:170])},
       "male class mean": {f"head_{i:03d}": float(x) for i, x in enumerate(D["m_m"][:170])}}
for m in sys.argv[1:]:
    ids[m] = store.load(m)["base"]["head"].get("identity") or {}
print("girth mm at ring:          13     16     19 (narrowest)  22    | chin->front of ring 13, halfwidth ring 13 / 19")
G = {}
for nm, idn in ids.items():
    V, J = gnm_eval(idn)
    G[nm] = V
    ch = lm(V, 8)
    r13 = V[lev == 13]
    print(f"{nm:22s} {1e3*girth(V,13):6.0f} {1e3*girth(V,16):6.0f} {1e3*girth(V,19):6.0f} {1e3*girth(V,22):12.0f}      {1e3*(ch[1]-r13[np.argmax(r13[:,2])][1]):5.0f}   {1e3*np.abs(r13[:,0]).max():.0f} / {1e3*np.abs(V[lev==19][:,0]).max():.0f}")
# which components carry the neck's girth (ring 19), per model against its sex's class mean
lp = ring_loop(19)
Vt = G["template"]
def dgirth():
    X = Vt[lp]
    e = X - np.roll(X, -1, 0)
    u = e / np.linalg.norm(e, axis=1, keepdims=True)
    out = []
    for i in range(170):
        dX = IB[i][lp]
        out.append(float((u * (dX - np.roll(dX, -1, 0))).sum()))
    return np.array(out)
dg = dgirth()
print("neck girth (ring 19) per +1 sd of a component, mm, the 8 largest:", [(names[i], round(1e3 * dg[i], 1)) for i in np.argsort(-np.abs(dg))[:8]])
print(f"sd of the neck's girth over GNM's identity prior (N(0,1) components): {1e3*np.linalg.norm(dg):.1f} mm")
for m in sys.argv[1:]:
    idn = ids[m]
    c = np.array([float(idn.get(f"head_{i:03d}", 0.0)) for i in range(170)])
    sex = store.load(m)["base"]["body"].get("sex", 1.0)
    c0 = np.asarray(D["m_f"] if float(sex) < 0.5 else D["m_m"])[:170]
    con = dg * (c - c0)
    top = np.argsort(-np.abs(con))[:8]
    print(f"{m}: neck girth {1e3*girth(G[m],19):.0f} vs its class mean {1e3*girth(G['female class mean' if float(sex)<0.5 else 'male class mean'],19):.0f}: linear change {1e3*con.sum():+.1f} mm; by component:",
          [(names[i], round(float(c[i]-c0[i]), 2), f"{1e3*con[i]:+.1f}mm") for i in top])
# GNM's own bib: front midline profile under the chin; the side silhouette by ring
V = Vt
ch = lm(V, 8)
mid = SKIN & (np.abs(V[:, 0]) < 0.002) & (V[:, 2] > 0.03) & (V[:, 1] < ch[1] - 0.005)
o = np.argsort(-V[mid, 1])
print("GNM template front midline under the chin (mm under chin, mm behind chin):", [(round(1e3*(ch[1]-y)), round(1e3*(ch[2]-z))) for y, z in V[mid][o][:, 1:3]][::2])
print("GNM side silhouette by ring (ring, halfwidth mm, side point's mm under chin):", [(k, round(1e3*np.abs(V[lev==k][:,0]).max()), round(1e3*(ch[1]-V[lev==k][np.argmax(V[lev==k][:,0])][1]))) for k in range(0, 24, 2)])
quads = np.asarray(g["quads"])
Q = [q for q in quads if SKIN[q].all()]
W = V @ np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]]).T
c = np.array([0, -0.02, ch[1] - 0.03])
col = [(205, 200, 192) if (lev[q] >= 13).all() or (lev[q] < 0).any() else (215, 190, 150) for q in Q]
ims = [wire.view(W, Q, c, 0.42, az=az, el=0, px=700, colors=col, line=0, title=f"GNM template, its own bib (tan: rings 0-12, not in our mesh) {nm}") for nm, az in (("front", 0), ("3q", 40), ("side", 90), ("back", 180))]
wire.sheet(ims, 4, f"{OUT}/gnm_bib.png")
