"""cost.py: what each orbit move costs and drags (GNM's template; linear, so per mm).
Formulations of "the eye 1 mm less deep-set":
  old      gnm_mm before orbit: eyes_forward +1 with the 22 others + the face's place held; the muzzle chain hung from
           the eye (subnasale_forward = nose base - EYES)
  anchor   the same holds, the chain re-anchored at the nasion (eyes +1, old subnasale -1)
  unit     NEW mm:eyes_forward: + rims (brow ridge, side rim, under-eye), the hollow, lids on the ball, opening,
           corners, glabella / dorsum held
  norims   unit without the three rims and the hollow held (the orbit's surround free to follow)
  dense    el_f4's kind: every eye / lid-margin vertex +1 mm forward (sigma 0.1), profile regions held at 0.25 mm, all
           other skin at 1 mm, lam 1 (a vertex-level least squares, as lidsolve fwd=)
Per formulation: |dc| per mm, the z move (mm per mm, against the skull = the cranium's mean) of the points a profile
shows, the skin's move away from the orbit, the lid's stand-off change (ball through the lid?), the 27 measures dragged."""
import numpy as np

from hifipushie import gnm_controls as gc, gnm_mm, lidrings

sp = gnm_mm._space()
T, IB, gr, S = sp["T"], sp["IB"], sp["gr"], sp["sets"]
J = gnm_mm.jacobian()
H = list(gnm_mm.HELD)
N = list(gnm_mm.NAMES)
sd = gnm_mm.sd()
t = lidrings.topo()
mir = lidrings.mirror()
ring = np.minimum(np.abs(t["ring"]), np.abs(t["ring"][mir]))
far = gr["skin_exterior"] & (ring > 14) & gr["hockey_mask"]
mid = np.abs(T[:, 0]) < 0.004
prof = gr["skin_exterior"] & mid & gr["hockey_mask"]
L = sp["WL"]


def solve(rows, b):
    A = J[rows]
    return A.T @ np.linalg.solve(A @ A.T + 1e-6 * np.eye(len(A)), b)


def old_dir():
    names = N[:23] + ["_face_x", "_face_y", "_face_z"]
    rows = [H.index(n) for n in names]
    A = J[rows].copy()
    A[names.index("subnasale_forward")] -= A[names.index("eyes_forward")]     # the old reader: nose base - eyes
    b = np.zeros(len(names))
    b[names.index("eyes_forward")] = 1
    return A.T @ np.linalg.solve(A @ A.T + 1e-6 * np.eye(len(A)), b)


def anchor_dir():
    names = N[:23] + ["_face_x", "_face_y", "_face_z"]
    rows = [H.index(n) for n in names]
    b = np.zeros(len(names))
    b[names.index("eyes_forward")] = 1
    return solve(rows, b)


def norims_dir():
    names = [n for n in H if n not in ("brow_ridge_forward", "side_rim_forward", "under_eye_forward", "brow_hollow")]
    rows = [H.index(n) for n in names]
    b = np.zeros(len(names))
    b[names.index("eyes_forward")] = 1
    return solve(rows, b)


def dense_dir():
    B = IB * 1000.0                                           # (170, V, 3) mm
    r0 = t["loops"][0]
    tg = np.zeros(len(T), bool)
    tg[gr["eyes"]] = True
    tg[np.r_[r0, mir[r0]]] = True
    hold = gr["skin_exterior"] & ~tg
    pf = gr["nose_region"] | gr["forehead_region"] | gr["middle_brow_region"]
    w = np.where(pf, 1 / 0.25, 1.0)[hold]
    At = (B[:, tg] / 0.1).reshape(170, -1).T
    bt = (np.tile([0, 0, 1.0], (int(tg.sum()), 1)) / 0.1).ravel()
    Ah = (B[:, hold] * w[None, :, None]).reshape(170, -1).T
    return np.linalg.solve(At.T @ At + Ah.T @ Ah + np.eye(170), At.T @ bt)


def report(name, d):
    D = np.tensordot(d, IB, 1) * 1000.0                       # mm per mm of the move
    ref = D[S["cranium"]].mean(0)
    Dz = D[:, 2] - ref[2]
    Lz = L @ D[:, 2] - ref[2]
    e = 0.5 * (D[gr["left_eye"], 2].mean() + D[gr["right_eye"], 2].mean()) - ref[2]
    o = {k: D[ids, 2].mean() - ref[2] for k, ids in sp["orb"].items()}
    sk = np.linalg.norm(D[far] - ref, axis=1)
    pr = np.abs(Dz[prof])
    dm = J @ d
    drag = sorted(((n, dm[H.index(n)]) for n in N if abs(dm[H.index(n)]) > 0.03), key=lambda kv: -abs(kv[1]))
    print(f"\n== {name}: |dc| {np.linalg.norm(d):.2f} per mm ({3 * np.linalg.norm(d):.1f} for 3 mm)")
    print(f"   forward move vs the skull (mm per mm): eye {e:+.2f} | lid margin up {o['margin_up']:+.2f} lo {o['margin_lo']:+.2f} platform "
          f"{o['platform']:+.2f} sulcus {o['sulcus']:+.2f} | nasion {Lz[27]:+.2f} forehead {D[S['forehead'], 2].mean() - ref[2]:+.2f} "
          f"dorsum {Lz[28:30].mean():+.2f} tip {Lz[30]:+.2f} nose base {Lz[33]:+.2f} upper lip {Lz[51]:+.2f} chin {D[S['pog'], 2].mean() - ref[2]:+.2f}")
    print(f"   rims: brow ridge {o['brow_ridge']:+.2f} side rim {o['side_rim']:+.2f} under-eye {o['under_eye']:+.2f} | brow landmarks "
          f"{Lz[[19, 24]].mean():+.2f} | cheekbones (zyg) {D[S['zyg'], 2].mean() - ref[2]:+.2f}")
    print(f"   the face's skin beyond the orbit's rings moves {np.sqrt((sk ** 2).mean()):.2f} mm rms (max {sk.max():.2f}); the profile line "
          f"(midline skin) {np.sqrt((pr ** 2).mean()):.2f} rms (max {pr.max():.2f}); lid - ball: margin {o['margin_up'] - e:+.2f}, platform {o['platform'] - e:+.2f}")
    print("   measures: " + ", ".join(f"{n} {v:+.2f}" for n, v in drag))
    return np.linalg.norm(d)


if __name__ == "__main__":
    print("population sd (mm): " + ", ".join(f"{n} {sd[n]:.1f}" for n in gnm_mm.ORBIT) + f"; subnasale_forward (vs nasion) {sd['subnasale_forward']:.1f}")
    r = gnm_mm.readers(T)
    print("template: " + ", ".join(f"{n} {r[n]:.1f}" for n in gnm_mm.ORBIT))
    print("template, as seen: " + ", ".join(f"{k} {v:.1f}" for k, v in gnm_mm.orbit(T).items()))
    print("sets: " + ", ".join(f"{k} {len(v)}" for k, v in sp["orb"].items()))
    report("old (before orbit)", old_dir())
    report("anchor (chain at the nasion, no orbit holds)", anchor_dir())
    report("unit = NEW mm:eyes_forward", gnm_mm.direction("mm:eyes_forward"))
    report("norims (unit, rims + hollow free)", norims_dir())
    report("dense (el_f4's kind)", dense_dir())
    for n in gnm_mm.ORBIT[1:]:
        report("mm:" + n, gnm_mm.direction("mm:" + n))
    # the 23 older moves: how much the new holds changed them
    print("\nthe older moves with the orbit's holds (|dc| per mm old -> new, cos):")
    names = N[:23] + ["_face_x", "_face_y", "_face_z"]
    rows = [H.index(n) for n in names]
    A = J[rows].copy()
    A[names.index("subnasale_forward")] -= A[names.index("eyes_forward")]
    out = []
    for n in N[:23]:
        b = np.zeros(len(names))
        b[names.index(n)] = 1
        d0 = A.T @ np.linalg.solve(A @ A.T + 1e-6 * np.eye(len(A)), b)
        d1 = gnm_mm.direction(n)
        out.append(f"{n} {np.linalg.norm(d0):.2f} -> {np.linalg.norm(d1):.2f} ({d0 @ d1 / np.linalg.norm(d0) / np.linalg.norm(d1):.2f})")
    print("  " + "; ".join(out))
