"""Exported neutral head (GLB 'body' mesh, base pose, no morphs) vs the approved tp_k19 head (base.head_of on tp_k19's spec)."""
import sys, json, numpy as np
from scipy.spatial import cKDTree
from hifipushie import store, spec as specm, base
glb = sys.argv[1]
raw = json.load(open("/home/joe/dev/hifipushie/workspace/tp_k19/spec.json"))
ex = specm.expand_mirror(raw)
H = base.head_of(ex, ex["base"])
print("head keys", sorted(k for k in H if not k.startswith("_"))[:40])
Vk = None
for k in ("V", "verts", "vertices", "v"):
    if k in H: Vk = np.asarray(H[k], float); break
print("k19 head verts", None if Vk is None else Vk.shape)
from hifipushie import rig_audit as ra
g = ra.read_glb(glb)
for n, m in g["meshes"].items(): print(n, m["V"].shape, m["V"].min(0).round(3), m["V"].max(0).round(3))
name = "head"; Vb = np.asarray(g["meshes"]["head"]["V"], float)
lo, hi = Vk.min(0) + [0.01, 0.01, 0.03], Vk.max(0) - [0.01, 0.01, 0.0]
print("k19 bbox", Vk.min(0).round(4), Vk.max(0).round(4))
sel = np.all((Vb > lo) & (Vb < hi), 1)
d, _ = cKDTree(Vk).query(Vb[sel])
print(f"export {name}: {sel.sum()} verts inside the k19 head box (minus neck); dist to k19 verts mm: "
      f"median {np.median(d)*1e3:.3f} p95 {np.percentile(d,95)*1e3:.3f} max {d.max()*1e3:.3f}")
d2, _ = cKDTree(Vb).query(Vk[(Vk[:, 2] > lo[2])])
print(f"k19 -> export: median {np.median(d2)*1e3:.3f} p95 {np.percentile(d2,95)*1e3:.3f} max {d2.max()*1e3:.3f}")
for ax, n in ((0, "width x"), (1, "depth y"), (2, "height z")):
    print(n, "k19", round(float(np.ptp(Vk[Vk[:,2]>lo[2], ax])), 4), "export", round(float(np.ptp(Vb[sel, ax])), 4))
far = d > 5e-4
P = Vb[sel][far]
print(f"export verts > 0.5 mm from k19: {far.sum()} ({far.mean()*100:.1f}%)")
if far.sum():
    print(" their bbox", P.min(0).round(3), P.max(0).round(3))
    for lab, m in (("front face y<-0.1,z>1.45", (P[:,1] < -0.1) & (P[:,2] > 1.45)), ("z<1.40 (neck)", P[:,2] < 1.40),
                   ("inside mouth |x|<.03,y>-.14,z 1.44-1.49", (abs(P[:,0])<.03)&(P[:,1]>-.14)&(P[:,2]>1.44)&(P[:,2]<1.49))):
        print(" ", lab, int(m.sum()))
face = (Vb[sel][:,1] < -0.1) & (Vb[sel][:,2] > 1.45)
print(f"front face verts {face.sum()}: median {np.median(d[face])*1e3:.3f} p95 {np.percentile(d[face],95)*1e3:.3f} p99 {np.percentile(d[face],99)*1e3:.3f} mm")
Nk = np.asarray(H["normals"], float)
inb = np.all((Vk > Vb.min(0)) & (Vk < Vb.max(0)), 1)
d3, j3 = cKDTree(Vb).query(Vk[inb])
print(f"k19 verts inside export head bbox {inb.sum()}: -> export median {np.median(d3)*1e3:.3f} p95 {np.percentile(d3,95)*1e3:.3f} p99 {np.percentile(d3,99)*1e3:.3f} max {d3.max()*1e3:.2f} mm")
Q = Vk[inb][d3 > 5e-4]; print(" k19 verts > 0.5 mm off:", len(Q), "bbox", Q.min(0).round(3) if len(Q) else "", Q.max(0).round(3) if len(Q) else "")
# far export verts: signed offset along the nearest k19 normal (negative = inside the k19 skin)
dd, jj = cKDTree(Vk).query(P)
sg = np.einsum("ij,ij->i", P - Vk[jj], Nk[jj])
print(f" far export verts signed offset along k19 normal mm: <-1: {(sg<-1e-3).sum()}  -1..1: {(abs(sg)<=1e-3).sum()}  >1: {(sg>1e-3).sum()}")
out = P[sg > 1e-3]
if len(out): print(" outward far verts bbox", out.min(0).round(3), out.max(0).round(3), "max out mm", round(sg.max()*1e3, 2))
# point-to-surface: dense samples on k19's triangles
Fk = np.asarray(H["faces"], int)
rng = np.random.default_rng(0); n = 24
u = rng.random((n, 2)); u[u.sum(1) > 1] = 1 - u[u.sum(1) > 1]
T = Vk[Fk]; S = (T[:, None, 0] + u[None, :, :1] * (T[:, None, 1] - T[:, None, 0]) + u[None, :, 1:] * (T[:, None, 2] - T[:, None, 0])).reshape(-1, 3)
S = np.vstack([S, Vk])
ds, _ = cKDTree(S).query(Vb)
regions = {"eyes |x|.015-.05 z1.51-1.55": (abs(Vb[:,0])>.015)&(abs(Vb[:,0])<.05)&(Vb[:,2]>1.51)&(Vb[:,2]<1.55)&(Vb[:,1]<-.1),
           "nose |x|<.02 z1.48-1.53": (abs(Vb[:,0])<.02)&(Vb[:,2]>1.48)&(Vb[:,2]<1.53)&(Vb[:,1]<-.12),
           "mouth |x|<.03 z1.44-1.48": (abs(Vb[:,0])<.03)&(Vb[:,2]>1.44)&(Vb[:,2]<1.48)&(Vb[:,1]<-.12),
           "cheeks |x|.035-.07 z1.45-1.52": (abs(Vb[:,0])>.035)&(abs(Vb[:,0])<.07)&(Vb[:,2]>1.45)&(Vb[:,2]<1.52)&(Vb[:,1]<-.07),
           "brow z1.55-1.58": (Vb[:,2]>1.55)&(Vb[:,2]<1.58)&(Vb[:,1]<-.1),
           "skull back y>-0.03": Vb[:,1]>-0.03, "all": np.ones(len(Vb), bool)}
for k, m in regions.items():
    x = ds[m]; print(f"surf {k}: n {m.sum()} median {np.median(x)*1e3:.3f} p95 {np.percentile(x,95)*1e3:.3f} max {x.max()*1e3:.2f} mm, >0.5mm {np.mean(x>5e-4)*100:.1f}%")
def width(V, z, dz=0.003, front=-0.06):
    m = (abs(V[:,2]-z) < dz) & (V[:,1] < front); return np.ptp(V[m,0]) if m.sum() else float("nan")
for z, lab in ((1.57, "brow"), (1.53, "eyes"), (1.50, "nose base / cheekbone"), (1.46, "mouth"), (1.42, "jaw")):
    print(f"face width at z {z} ({lab}): k19 {width(Vk,z)*1e3:.2f} export {width(Vb,z)*1e3:.2f} mm")
m = lambda V: (abs(V[:,2]-1.497)<.004)&(V[:,1]<-.12)
print("nose width (front, y<-0.12, z~1.497): k19", round(np.ptp(Vk[m(Vk),0])*1e3,2), "export", round(np.ptp(Vb[m(Vb),0])*1e3,2))
Nb = np.asarray(g["meshes"]["head"]["N"], float)
for lab, base_m in (("mouth", regions["mouth |x|<.03 z1.44-1.48"]), ("eyes", regions["eyes |x|.015-.05 z1.51-1.55"]), ("nose", regions["nose |x|<.02 z1.48-1.53"])):
    fr = base_m & (Nb[:,1] < -0.5); bk = base_m & ~(Nb[:,1] < -0.5)
    print(f"{lab} front-facing n {fr.sum()}: median {np.median(ds[fr])*1e3:.3f} p95 {np.percentile(ds[fr],95)*1e3:.3f} max {ds[fr].max()*1e3:.2f};"
          f" other n {bk.sum()}: p95 {np.percentile(ds[bk],95)*1e3:.2f} mm")
