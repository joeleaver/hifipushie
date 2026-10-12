"""nlpath.py <model> [..]: the NOMINAL fold paths against anatomy, per head (frontal plane, mm; x from the midline,
z from the subnasale): the nasolabial path's start (against the alar crease), where it passes the mouth's level (against
the cheilion = the vermilion's own corner), its end, and its angle from the vertical; the marionette's start / end /
angle; the tear trough's depth under the lid margin. Norms beside them (see docs/notes/skin.md "## skinfolds2")."""
import sys
import numpy as np
from hifipushie import store, skin as skinmod, skin_folds as sf, skin_read as sr

for name in sys.argv[1:]:
    try:
        spec = store.load(name)
        st = sr.stage_spec(spec)
        J = skinmod._joints(st)
        part = (st.get("skin") or {}).get("part", "body")
        ps = sf.paths(st, part, J, None, names=["nasolabial", "marionette", "tear_trough"])
    except Exception as e:  # noqa: BLE001
        print(name, "FAILED", str(e)[:120]); continue
    right, front, up = sf.head_frame(J)
    io = skinmod.interocular(J)
    o = np.asarray(J["lm_nose_base"], float)
    xz = lambda p: np.array([(np.asarray(p, float) - o) @ right, (np.asarray(p, float) - o) @ up]) * 1000  # noqa: E731
    vn = sorted(k for k in J if k.startswith("verm_u") and k[6:].isdigit())
    che = xz(J[vn[-1]]) if vn else xz(J["lm_mouth_corner.L"])
    cor = xz(J["lm_mouth_corner.L"])
    al = xz(J["lm_nostril.L"])
    P = np.array([xz(p) for p in ps[("nasolabial", ".L")]["P"]])
    i = int(np.argmin(np.abs(P[:, 1] - che[1])))
    ang = np.degrees(np.arctan2(P[-1, 0] - P[0, 0], -(P[-1, 1] - P[0, 1])))
    ang2 = np.degrees(np.arctan2(P[i, 0] - P[0, 0], -(P[i, 1] - P[0, 1])))
    M = np.array([xz(p) for p in ps[("marionette", ".L")]["P"]])
    am = np.degrees(np.arctan2(M[-1, 0] - M[0, 0], -(M[-1, 1] - M[0, 1])))
    T = np.array([xz(p) for p in ps[("tear_trough", ".L")]["P"]])
    lid = xz(J["lm_lid_lower.L"])
    print(f"{name:14s} io {io * 1000:.0f}  cheilion {che.round(0)} lm_mouth_corner {cor.round(0)} nostril lm {al.round(0)}\n"
          f"   NASOLABIAL start {P[0].round(1)} | at the mouth's level x {P[i, 0]:.1f} = cheilion + {P[i, 0] - che[0]:.1f} | end {P[-1].round(1)} "
          f"(= {P[-1, 1] - che[1]:+.1f} under the cheilion) | angle from vertical: whole {ang:.0f} deg, to the mouth's level {ang2:.0f} deg, length {np.linalg.norm(np.diff(P, axis=0), axis=1).sum():.0f}\n"
          f"   MARIONETTE start {M[0].round(1)} (cheilion + {M[0, 0] - che[0]:.1f}, {M[0, 1] - che[1]:+.1f}) end {M[-1].round(1)} angle {am:.0f} deg length {np.linalg.norm(np.diff(M, axis=0), axis=1).sum():.0f}\n"
          f"   OWN CREASE (the nominal nasolabial path snapped onto the head's own fold: median offset mm, share of stations): L {ps[('nasolabial', '.L')]['snapped']} R {ps[('nasolabial', '.R')]['snapped']}\n"
          f"   TEAR TROUGH lowest {T[:, 1].min() - lid[1]:+.1f} mm under the lower lid's margin, x {T[0, 0]:.0f}..{T[-1, 0]:.0f}")
