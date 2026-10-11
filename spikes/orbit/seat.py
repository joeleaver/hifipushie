"""seat.py [n=150] <model>...: the EYEBALL SEAT against the lid's surface (not changed anywhere: a measurement for the
coordinator). base.gnm_head seats each ball as far forward as its six lid LANDMARKS allow (EYE_SEAT 0.8 mm clear).
Here, per head: the lid skin's least stand-off from that ball over rings 0..7 (blockin_lid.ball_clearance; < 0 = the
ball is through the skin, < 0.25 = the stage's 0.04 mm skin can show it), and how far BACK along the face each ball
would move if it were seated against the lid's skin instead (every vertex of rings 1..7 clear by 0.25 mm, the six
landmarks still by 0.8): the proposed seat. Named models, then n random GNM identities (N(0, I)) on the first model's
body."""
import copy
import sys

import numpy as np

from hifipushie import blockin as bi, blockin_lid as bl, onemesh, store

args = sys.argv[1:]
n = int(args.pop(0)) if args and args[0].isdigit() else 150
CLEAR = 0.25e-3


def head(base):
    ht = onemesh.head_template(base)
    for kk in [k for k in onemesh._CACHE if isinstance(k, tuple) and k and k[0] == "head_t"]:
        onemesh._CACHE.pop(kk, None)
    return ht


def reseat(ht):
    """mm each ball moves back so that rings 1..7 clear it by CLEAR (0 when they already do)."""
    ring, _ = bl._skin_rings()
    V = np.asarray(ht["verts"], float)[:len(ring)]
    sel = np.isin(ring, range(1, 8))
    back = -np.asarray(ht["forward"], float)
    r = float(ht["eye_r"])
    out = []
    for c in ht["eyes"]:
        c = np.asarray(c, float)
        P = V[sel & (np.linalg.norm(V - c, axis=1) < 2.2 * r)]
        if np.linalg.norm(P - c, axis=1).min() >= r + CLEAR:
            out.append(0.0)
            continue
        lo, hi = 0.0, 0.01
        for _ in range(30):
            m = 0.5 * (lo + hi)
            if np.linalg.norm(P - (c + m * back), axis=1).min() >= r + CLEAR:
                hi = m
            else:
                lo = m
        out.append(hi * 1000)
    return out


print("model            ball r   lid over ball: least / upper lid / landmarks (mm)   least per ring 1..7                      reseat: back by (mm, R / L)")
rows = []
for name in args:
    ht = head(store.load(name)["base"])
    b = bl.ball_clearance(ht)
    mv = reseat(ht)
    rows.append((name, b, mv))
    print(f"{name:16s} {1000 * ht['eye_r']:5.2f}   {b['min']:+.2f} / {b['upper']:+.2f} / {b['landmarks']:+.2f}      "
          + " ".join(f"{b['rings'][k]:+.2f}" for k in range(1, 8)) + f"      {mv[0]:.2f} / {mv[1]:.2f}", flush=True)
if n and args:
    base = copy.deepcopy(store.load(args[0])["base"])
    base["head"].pop("expression", None)
    rng = np.random.default_rng(5)
    mins, moves, ups = [], [], []
    for i in range(n):
        bi.set_identity({"base": base}, rng.normal(size=170))
        ht = head(base)
        b = bl.ball_clearance(ht)
        mins.append(b["min"])
        ups.append(b["upper"])
        moves.append(max(reseat(ht)))
    mins, moves, ups = np.array(mins), np.array(moves), np.array(ups)
    print(f"\n{n} random GNM identities on {args[0]}'s body: lid over ball least stand-off p5 / p50 / p95 {np.percentile(mins, 5):+.2f} / "
          f"{np.percentile(mins, 50):+.2f} / {np.percentile(mins, 95):+.2f} mm; through the skin (< 0): {100 * np.mean(mins < 0):.0f} %; under 0.25 mm: "
          f"{100 * np.mean(mins < 0.25):.0f} %; the upper lid alone under 0.25: {100 * np.mean(ups < 0.25):.0f} %")
    print(f"   reseat against the lid's skin: balls that move {100 * np.mean(moves > 0):.0f} %; the move back p50 / p90 / max of those "
          f"{np.percentile(moves[moves > 0], 50) if (moves > 0).any() else 0:.2f} / {np.percentile(moves[moves > 0], 90) if (moves > 0).any() else 0:.2f} / {moves.max():.2f} mm")
