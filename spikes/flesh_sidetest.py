"""sidetest.py <model> <npz> <falloff...>: raise arms, report how much of the side under the arm moves."""
import sys, numpy as np
from hifipushie import store, rig as rigmod, retopo, sdf
from hifipushie.spec import compile_prims
name, path = sys.argv[1], sys.argv[2]; spec = store.load(name); bones = rigmod.rig_bones(spec); P_ = rigmod.PREFIX
names = {b["name"] for b in bones}
pose = rigmod.drive_twist(bones, {b: v for b, v in {P_ + "LeftArm": ([0, 1, 0], -80), P_ + "RightArm": ([0, 1, 0], 80)}.items() if b in names})
z = np.load(path); V, L, S = z["verts"].astype(float), z["loops"], z["sizes"]; F = retopo.tris(L, S)
E = retopo.edges(L, S); L0 = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
d0 = rigmod.weights.__defaults__
arm = [p for p in compile_prims(spec) if p.name in ('upperarm.L','forearm.L','trotter.L','shoulderroll.L')]
da = sdf.field_at(arm, V, clip=False)
SIDE = (da > 0.002) & (V[:, 0] > 0.12) & (V[:, 2] > 0.2) & (V[:, 2] < 0.33)
print('side verts (body, not arm, x>0.12, z .2-.33):', SIDE.sum())
for fo in [float(x) for x in sys.argv[3:]]:
    dd = list(d0); dd[2] = fo; rigmod.weights.__defaults__ = tuple(dd)
    J, W = rigmod.skin_mesh(spec, bones, V, F, np.zeros(len(V), int), ["body"])
    P = rigmod.pose(bones, V, J, W, pose); d = np.linalg.norm(P - V, axis=1)
    side = SIDE
    r = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1) / np.maximum(L0, 1e-9)
    print(f"falloff {fo}: side moved >3cm {100*(d[side]>0.03).mean():.0f}% max {100*d[side].max():.1f} cm; edges >3x {(r>3).sum()} p99.9 {np.percentile(r,99.9):.2f}x")
    np.savez(path.replace(".npz", f"_arms_f{fo}.npz"), verts=P, loops=L, sizes=S)
