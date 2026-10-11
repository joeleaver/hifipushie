"""pipe.py <model> ...: what each pipeline stage does to GNM's upper lid, vertex for vertex (left eye, rings 0..10).
  raw     GNM's own mesh for the model's identity (+ expression): gnm_controls.vertices
  carried base.gnm_head's vertices after the body's hook (MakeHuman base x gnm_base, dimorphism field, eyes x 1.05 ...):
          head_template()["carry"]["V"], GNM frame
  world   the one mesh's skin vertices (head_template()["verts"])
  stage   the dressed stage's mesh (Catmull-Clark + IMLS field, marching cubes 0.5 mm at the eyes, Taubin, projection)
Prints: raw -> carried after the best similarity over the lid's rings (what is NOT a scale / move: mm along the
surface normal per ring, + rms), the lid's rows against OUR eyeball (seat, radius), world -> stage distance of every
lid vertex to the stage surface (signed along the normal) and the stage's own sagittal section numbers."""
import glob
import sys

import numpy as np
from scipy.spatial import cKDTree

import lidmap as lm
from hifipushie import blockin as bi, gnm_controls as gc, onemesh, store

g = gc.gnm()
t = lm.topo()
sk = lm.skin_ids()
loc = -np.ones(len(g["T"]), int)
loc[sk] = np.arange(len(sk))
RINGS = range(0, 11)


def expr(spec):
    e = np.zeros(len(g["ex_names"]))
    for k, x in (spec["base"]["head"].get("expression") or {}).items():
        e[g["ex_names"].index(k)] = float(x)
    return e


def similarity(A, B):
    """s, R, t with B ~ s A R^T + t."""
    ca, cb = A.mean(0), B.mean(0)
    A0, B0 = A - ca, B - cb
    U, S, Vt = np.linalg.svd(A0.T @ B0)
    d = np.sign(np.linalg.det(U @ Vt))
    R = (U @ np.diag([1, 1, d]) @ Vt).T
    s = (S * [1, 1, d]).sum() / (A0 ** 2).sum()
    return s, R, cb - s * ca @ R.T


for name in sys.argv[1:]:
    sp = store.load(name)
    c = bi.identity(sp)
    Vr = gc.vertices(c, expr(sp)) * 1000
    ht = onemesh.head_template(sp["base"])
    Vc = np.asarray(ht["carry"]["V"], float) * 1000
    ids = np.concatenate([t["loops"][k] for k in RINGS])
    rk = np.concatenate([[k] * len(t["loops"][k]) for k in RINGS])
    up = (g["T"][ids, 1] > g["J"][2][1])
    s, R, tr = similarity(Vr[ids], Vc[ids])
    D = Vc[ids] - (s * Vr[ids] @ R.T + tr)
    N = gc.normals(Vc)[ids]
    dn = (D * N).sum(1)
    print(f"\n=== {name}: raw -> carried: similarity scale {s:.4f}; residual over the lid rings rms {np.sqrt((D ** 2).sum(1).mean()):.3f} mm (normal part {np.sqrt((dn ** 2).mean()):.3f})")
    print("   per ring (upper half): mean / max |normal residual| mm:", " ".join(f"{k}:{np.abs(dn[(rk == k) & up]).mean():.2f}/{np.abs(dn[(rk == k) & up]).max():.2f}" for k in RINGS))
    # raw rows against GNM's ball, carried rows against OUR ball (in GNM-frame mm: world / s_world)
    cr, rr = lm.eye_frame_raw(c)
    car = ht["carry"]
    W = np.asarray(ht["verts"], float)
    ce = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float)
    # world -> GNM frame of the carried mesh: X_gnm = mid + (X_w - eye_mid) @ R / s
    Rw, sw, mid, em = np.asarray(car["R"]), float(car["s"]), np.asarray(car["mid"]), np.asarray(car["eye_mid"])
    ce_g = (mid + (ce - em) @ Rw / sw) * 1000
    r_g = float(ht["eye_r"]) / sw * 1000
    print(f"   GNM's own ball r {rr:.2f} at {np.round(cr, 1)}; OUR ball r {r_g:.2f} (GNM units; world {ht['eye_r'] * 1000:.2f} mm, head scale {sw:.3f}) at {np.round(ce_g, 1)}"
          f" = {np.round(ce_g - (s * cr @ R.T + tr), 2)} from GNM's ball carried (x left, y up, z fwd)")
    print("   pupil column, ring: raw v / to GNM ball | carried v / to OUR ball (GNM units)")
    a = {k: (v, w) for k, v, w in lm.column(Vr, cr, 0.0)}
    b = {k: (v, w) for k, v, w in lm.column(Vc, ce_g, 0.0)}
    for k in range(-1, 11):
        if k in a and k in b:
            print(f"     {k:3d}  {a[k][0]:6.2f} /{np.hypot(*a[k]) - rr:5.2f}   |  {b[k][0]:6.2f} /{np.hypot(*b[k]) - r_g:5.2f}")
    # the stage mesh
    best = lm.stage_mesh(name)
    if best is None:
        print("   no stage mesh cached (shoot it first)")
        continue
    Vs, Ns, _ = best
    Rs, ts, med = lm.to_stage(name, ht, Vs)
    Wl = W[loc[ids]] @ Rs.T + ts
    ces = ce @ Rs.T + ts
    tree = cKDTree(Vs)
    d, j = tree.query(Wl)
    sd = ((Wl - Vs[j]) * Ns[j]).sum(1) * 1000
    near = cKDTree(Vs[np.linalg.norm(Vs - ces, axis=1) < 0.03])
    dd = near.query(near.data, k=2)[0][:, 1]
    print(f"   world -> stage (aligned, face median {med * 1000:.2f} mm): lid vertices' signed distance to the stage surface (mm, + = GNM's vertex OUTSIDE the stage skin): rms {np.sqrt((sd ** 2).mean()):.3f}; stage vertex spacing near the eye {np.median(dd) * 1000:.2f} mm")
    print("   per ring (upper half) mean / min / max:", " ".join(f"{k}:{sd[(rk == k) & up].mean():+.2f}/{sd[(rk == k) & up].min():+.2f}/{sd[(rk == k) & up].max():+.2f}" for k in RINGS))
