"""lidsec.py <model> ...: the upper lid's sagittal section (subject's left eye) at u = -5 / 0 / +5 mm from the pupil, on
the mesh: how the lid sits on the ball and what the platform and fold are made of. Prints a table, saves the sections
(out/lidsec.json) and a plot (out/lidsec.png): forward (mm) vs up (mm), margin at the origin, the ball drawn.
  gap        the margin ring's distance to the eyeball's surface (+ = a gap showing lining, - = inside the ball)
  margin     the lid margin's thickness: how far FORWARD of the ring the lid's front face is at 1 mm up
  platform   the crease's height over the margin (blockin_eyes._profile) and how far the crease is BEHIND the lid's
             front face at 1 mm (recede), and the platform's bulge over the chord margin-front -> crease (+ = convex)
  crease     depth in a 2.5 mm chord / in a 0.75 mm chord (narrow = crisp)
  fold       how far the skin comes FORWARD of the crease within 4 mm above it
"""
import json
import os
import sys

import numpy as np

from hifipushie import blockin_eyes as be, eye_ruler as er, onemesh, store

G = os.environ["G"] + "/out"
US = (-5.0, 0.0, 5.0)


def section(ht, tri, c, r, fwd, x):
    Vh = np.asarray(ht["verts"], float)
    up = np.array([0, 0, 1.0]) - fwd * fwd[2]
    up /= np.linalg.norm(up)
    best = None
    for L in be._chain(be._slice(Vh, tri, float(c[0] + x * 0.001))):
        d = np.linalg.norm(L - c, axis=1)
        ok = (d > r - 0.0015) & ((L - c) @ up > -0.002) & ((L - c) @ fwd > 0) & ((L - c) @ up < 0.03)
        runs, cur = [], []
        for i, o in enumerate(ok):
            if o:
                cur.append(i)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        for rr in runs:
            if best is None or len(rr) > len(best[1]):
                best = (L, rr)
    if best is None:
        return None
    L, rr = best
    P = np.c_[(L[rr] - c) @ fwd, (L[rr] - c) @ up] * 1000
    if P[0, 1] > P[-1, 1]:
        P = P[::-1]
    return P


def narrow(P, w):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    s = np.arange(0, d[-1], 0.05)
    Q = np.c_[np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])]
    k = int(round(w / 0.05))
    best = 0.0
    for i in range(k, len(Q) - k):
        if not 1.5 < Q[i, 1] - Q[0, 1] < 9:
            continue
        a, b = Q[i - k], Q[i + k]
        ab = b - a
        n = np.array([ab[1], -ab[0]]) / max(np.linalg.norm(ab), 1e-9)
        best = max(best, -float((Q[i] - a) @ n))
    return best


def measure(P, r_mm):
    out = {}
    out["gap"] = float(np.linalg.norm(P[0]) - r_mm)
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    s = np.arange(0, d[-1], 0.05)
    Q = np.c_[np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])] - P[0]
    i1 = int(np.argmin(np.abs(Q[:, 1] - 1.0) + 1e3 * (s < 0.3)))
    out["margin"] = float(Q[:i1 + 1, 0].max())
    q = be._profile(P / 1000)
    h = float(q["height"]) if np.isfinite(q["height"]) else float("nan")
    out["crease_h"], out["crease_d"], out["show"] = h, float(q["local"]), float(q["show"])
    out["crease_narrow"] = narrow(P, 0.75)
    if np.isfinite(h):
        ic = int(np.argmin(np.abs(Q[:, 1] - h) + 1e3 * (s < 0.5)))
        out["recede"] = float(Q[i1, 0] - Q[ic, 0])
        a, b = Q[i1], Q[ic]
        ab = b - a
        n = np.array([ab[1], -ab[0]]) / max(np.linalg.norm(ab), 1e-9)      # toward the front
        seg = Q[i1:ic + 1]
        out["bulge"] = float(((seg - a) @ n).max()) if len(seg) > 2 else 0.0
        above = Q[(Q[:, 1] > h) & (Q[:, 1] < h + 4.0)]
        out["fold"] = float(above[:, 0].max() - Q[ic, 0]) if len(above) else 0.0
    return out


res = {}
print(f"{'model':12s} {'u':>3s} {'gap':>6s} {'margin':>6s} {'crease h':>8s} {'shown':>6s} {'recede':>6s} {'bulge':>6s} {'depth':>6s} {'narrow':>6s} {'fold':>6s}")
for name in sys.argv[1:]:
    ht = onemesh.head_template(store.load(name)["base"])
    c = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float)
    r = float(ht["eye_r"])
    fwd = np.asarray(ht["forward"], float)
    _, tri = er._ring(ht, c)
    res[name] = {"r": r * 1000, "sections": {}}
    for u in US:
        P = section(ht, tri, c, r, fwd, u)
        if P is None:
            continue
        m = measure(P, r * 1000)
        res[name]["sections"][str(u)] = {"P": P.tolist(), **m}
        print(f"{name:12s} {u:3.0f} {m['gap']:6.2f} {m['margin']:6.2f} {m['crease_h']:8.2f} {m['show']:6.2f} {m.get('recede', np.nan):6.2f} "
              f"{m.get('bulge', np.nan):6.2f} {m['crease_d']:6.2f} {m['crease_narrow']:6.2f} {m.get('fold', np.nan):6.2f}")
json.dump(res, open(G + "/lidsec.json", "w"))
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(15, 6))
    for k, u in enumerate(US):
        for name, v in res.items():
            sc = v["sections"].get(str(u))
            if sc is None:
                continue
            P = np.array(sc["P"])
            ax[k].plot(P[:, 0] - P[0, 0], P[:, 1] - P[0, 1], label=name, lw=1.6)
        ax[k].set_aspect("equal")
        ax[k].set_xlim(-8, 4)
        ax[k].set_ylim(-1, 13)
        ax[k].grid(alpha=0.3)
        ax[k].set_title(f"upper lid section at u = {u:+.0f} mm (forward ->, up; margin at 0)")
    ax[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(G + "/lidsec.png", dpi=110)
except Exception as e:  # noqa: BLE001
    print("no plot:", e)
