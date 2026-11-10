"""flesh_headturn.py <model> <npz> <outdir> <tag>: the head turned 45 deg and nodded 30 deg (LBS). The shoulder
tops (x > 0.12, z 0.38-0.46, the body's own skin: off the arm's shapes, nearer the loft / shoulder roll than the head ball) moving, the Head's weight there, stretched edges."""
import sys, numpy as np
from hifipushie import store, rig as R, retopo, sdf
from hifipushie.spec import compile_prims
name, path, out, tag = sys.argv[1:5]
spec = store.load(name); rb = R.rig_bones(spec); P_ = R.PREFIX; names = [b["name"] for b in rb]
z = np.load(path); V, L, S = z["verts"].astype(float), z["loops"], z["sizes"]; F = retopo.tris(L, S)
E = retopo.edges(L, S); L0 = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
arm = [p for p in compile_prims(spec) if p.name in ('upperarm.L', 'forearm.L', 'trotter.L', 'upperarm.R', 'forearm.R', 'trotter.R')]
da = sdf.field_at(arm, V, clip=False)
pr = compile_prims(spec); dh = sdf.field_at([p for p in pr if p.name == "headball"], V, clip=False)
dbody = sdf.field_at([p for p in pr if p.name in ("body", "shoulderroll.L", "shoulderroll.R")], V, clip=False)
TOP = (da > 0.002) & (dbody < dh - 0.001)  # the body's own skin there (the loft / shoulder roll), not the head ball's
HB = (np.abs(V[:, 0]) > 0.12) & (V[:, 2] > 0.38) & (V[:, 2] < 0.46) & (dh < dbody - 0.001)
TOP &= (np.abs(V[:, 0]) > 0.12) & (V[:, 2] > 0.38) & (V[:, 2] < 0.46)
J, W = R.skin_mesh(spec, rb, V, F, np.zeros(len(V), int), ["body"])
hw = np.where(J == names.index(P_ + "Head"), W, 0).sum(1)
print(f"{tag}: head-ball skin in the box {HB.sum()} (Head weight mean {hw[HB].mean():.2f})")
print(f"{tag}: shoulder-top verts {TOP.sum()}, Head weight there >0.1: {(hw[TOP] > 0.1).sum()}, mean {hw[TOP].mean():.3f}, max {hw[TOP].max():.2f}")
for k, turn in {"turn45": ([0, 0, 1], 45), "nod30": ([1, 0, 0], 30)}.items():
    pose = R.drive_twist(rb, {P_ + "Head": turn})
    P = R.pose(rb, V, J, W, pose); d = np.linalg.norm(P - V, axis=1)
    r = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1) / np.maximum(L0, 1e-9)
    print(f"  {k}: head-ball skin in the box moving >1 cm {100*(d[HB] > 0.01).mean():.1f}%")
    print(f"  {k}: shoulder tops moving >1 cm {100*(d[TOP] > 0.01).mean():.1f}% max {100*d[TOP].max():.1f} cm; edges >2x {(r > 2).sum()} >3x {(r > 3).sum()} p99.9 {np.percentile(r, 99.9):.2f}x")
    np.savez(f"{out}/{tag}_{k}.npz", verts=P, loops=L, sizes=S)
