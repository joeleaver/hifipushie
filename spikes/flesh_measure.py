"""flesh_measure.py <model> <npz> <outdir> [tag]: arms raised 80 deg and seated (LBS) on an exported mesh.
Body side under the arm (> 2 mm off the arm's own shapes) moving > 3 cm, stretched edges, and where they are."""
import sys, os, numpy as np
from hifipushie import store, rig as rigmod, rig_audit, retopo, sdf
from hifipushie.spec import compile_prims
name, path, out = sys.argv[1:4]; tag = sys.argv[4] if len(sys.argv) > 4 else "x"
spec = store.load(name); bones = rigmod.rig_bones(spec); P_ = rigmod.PREFIX; names = {b["name"] for b in bones}
poses = {"arms": {P_ + "LeftArm": ([0, 1, 0], -80), P_ + "RightArm": ([0, 1, 0], 80)}, "seated": rig_audit.seated(bones)}
poses = {k: rigmod.drive_twist(bones, {b: v for b, v in p.items() if b in names}) for k, p in poses.items()}
z = np.load(path); V, L, S = z["verts"].astype(float), z["loops"], z["sizes"]; F = retopo.tris(L, S)
E = retopo.edges(L, S); L0 = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
arm = [p for p in compile_prims(spec) if p.name in ('upperarm.L', 'forearm.L', 'trotter.L', 'shoulderroll.L')]
da = sdf.field_at(arm, V, clip=False)
SIDE = (da > 0.002) & (V[:, 0] > 0.12) & (V[:, 2] > 0.2) & (V[:, 2] < 0.33)
J, W = rigmod.skin_mesh(spec, bones, V, F, np.zeros(len(V), int), ["body"])
np.savez(f"{out}/{tag}_w.npz", J=J, W=W)
for k, pose in poses.items():
    P = rigmod.pose(bones, V, J, W, pose); d = np.linalg.norm(P - V, axis=1)
    r = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1) / np.maximum(L0, 1e-9)
    bad = E[r > 3]; mid = V[bad].mean(1) if len(bad) else np.zeros((0, 3))
    zs = np.histogram(mid[:, 2], bins=[-1, .1, .15, .2, .25, .3, .35, 1])[0] if len(mid) else []
    s = f"side moved >3cm {100*(d[SIDE]>0.03).mean():.1f}% | " if k == "arms" else ""
    print(f"{tag} {k}: {s}edges >3x {(r>3).sum()} >2x {(r>2).sum()} p99.9 {np.percentile(r,99.9):.2f}x max {r.max():.1f}x; >3x by z(<.1,.15,.2,.25,.3,.35,+) {list(zs)}")
    np.savez(f"{out}/{tag}_{k}.npz", verts=P, loops=L, sizes=S)
