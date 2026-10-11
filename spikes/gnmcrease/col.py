"""col.py: the crease across the eye (gnmcrease 2): the eye step's profile reader at 7 columns from the inner to the outer
corner (fractions of the corner-to-corner width), per column: crease height over the margin (hsoft / height), its depth
on 2.5 and 0.75 mm chords, the fold edge's convexity above, the platform shown, the brow's height. Summaries: the mid
height, the height's spread across the middle 5 columns (parallel to the lashes or arching up), the crease's reach
(columns where the narrow valley > 0.15 mm), the mid fold's convexity.

  col.py samples           all N(0, I) + ICT samples (geo only), -> out/col_<file>.npz
  col.py one <spec>...     <kind_seed>:<i> | model:<name> (its eye expression kept) | npy:<path>[@model]
"""
import json
import sys

import numpy as np

import gk
from hifipushie import blockin as bi, blockin_eyes as be, store

FR = (0.12, 0.25, 0.37, 0.5, 0.63, 0.75, 0.88)
_RD = {}


def eye_e(spec):
    ex = spec["base"]["head"].get("expression") or {}
    return np.array([0.5 * (float(ex.get(gk.LN[k], 0)) + float(ex.get(gk.RN[k], 0))) for k in range(be.NE)])


PROF = []


def columns(c, e=None, model="gd_T12"):
    PROF.clear()
    ht = gk.head(c, e, model)
    if model not in _RD:
        _RD[model] = be.Reader(ht)
    rd = _RD[model]
    V = np.asarray(ht["verts"], float)
    cen = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float)
    r = float(ht["eye_r"])
    fwd = np.asarray(ht["forward"], float)
    up = np.array([0, 0, 1.0]) - fwd * fwd[2]
    up /= np.linalg.norm(up)
    L = np.asarray(ht["lm68"], float)
    xi, xo = L[42, 0], L[45, 0]      # the subject's left eye: inner / outer corner
    brow_z = L[17:27][L[17:27, 0] > 0][:, 2].mean() if (L[17:27, 0] > 0).any() else np.nan
    out = []
    for f in FR:
        x0 = xi + f * (xo - xi)
        best = None
        for Lc in be._chain(be._slice(V, rd.tri, x0)):
            d = np.linalg.norm(Lc - cen, axis=1)
            ok = (d > r + 0.0003) & ((Lc - cen) @ up > -0.004) & ((Lc - cen) @ fwd > -0.004) & ((Lc - cen) @ up < 0.03)
            runs, cur = [], []
            for i, o in enumerate(ok):
                if o:
                    cur.append(i)
                elif cur:
                    runs.append(cur); cur = []
            if cur:
                runs.append(cur)
            for rr in runs:
                if best is None or len(rr) > len(best[1]):
                    best = (Lc, rr)
        if best is None:
            out.append(None); PROF.append(None); continue
        Lc, rr = best
        P = np.c_[(Lc[rr] - cen) @ fwd, (Lc[rr] - cen) @ up]
        if P[0, 1] > P[-1, 1]:
            P = P[::-1]
        # start at the margin: the lowest point that is in front of the globe's equator
        PROF.append(P.copy())
        q = be._profile(P)
        x = gk.extras(P)
        out.append({"h": q["hsoft"], "depth": q["lsoft"], "narrow": x["narrow"], "lip": x["lip"], "krad": x["krad"],
                    "show": q["show"], "drop": q["drop"], "margin_z": float(P[0, 1] * 1000), "brow": float((brow_z - cen[2]) * 1000 - P[0, 1] * 1000)})
    return out


def summary(cols):
    mid = [c for c in cols[1:6] if c]
    if not mid:
        return {}
    h = np.array([c["h"] for c in mid])
    m = cols[3] or mid[len(mid) // 2]
    return {"h_mid": m["h"], "h_spread": float(np.nanmax(h) - np.nanmin(h)), "h_arch": float(m["h"] - 0.5 * (mid[0]["h"] + mid[-1]["h"])),
            "depth_mid": m["depth"], "narrow_mid": m["narrow"], "narrow_mean": float(np.mean([c["narrow"] for c in mid])),
            "reach": int(sum(1 for c in cols if c and c["narrow"] > 0.15)), "lip_mid": m["lip"], "show_mid": m["show"],
            "brow_mid": m["brow"], "h_over_brow": m["h"] / max(m["brow"], 1e-3), "drop_max": float(max(c["drop"] for c in mid))}


def src(s):
    if s.startswith("model:"):
        sp = store.load(s[6:])
        return bi.identity(sp), eye_e(sp), s[6:]
    if s.startswith("npy:"):
        p, _, m = s[4:].partition("@")
        return np.load(p), (eye_e(store.load(m)) if m else None), s
    k, i = s.split(":")
    return np.load(f"/mnt/data/hifipushie/gnmcrease/out/s_{k}.npz")["C"][int(i)], None, s


if __name__ == "__main__":
    if sys.argv[1] == "samples":
        for f in ("gnm_1", "ict_2"):
            C = np.load(f"/mnt/data/hifipushie/gnmcrease/out/s_{f}.npz")["C"]
            S, Cols = [], []
            for i, c in enumerate(C):
                cols = columns(c)
                S.append(summary(cols)); Cols.append(cols)
                if i % 100 == 0:
                    print(f, i, flush=True)
            np.savez(f"/mnt/data/hifipushie/gnmcrease/out/col_{f}.npz", S=json.dumps(S), cols=json.dumps(Cols))
    elif sys.argv[1] == "dump":      # dump <out json> <spec>...: the columns' profiles + reads
        D = {}
        for s in sys.argv[3:]:
            c, e, lab = src(s)
            cols = columns(c, e)
            D[lab] = {"cols": cols, "prof": [p.tolist() if p is not None else None for p in PROF]}
        json.dump(D, open(sys.argv[2], "w"))
    else:
        for s in sys.argv[2:]:
            c, e, lab = src(s)
            cols = columns(c, e)
            sm = summary(cols)
            print(f"{lab:28s} " + " ".join(f"{k} {v:.2f}" for k, v in sm.items()))
            print("   h per column " + " ".join(f"{c['h']:.1f}" if c else "-" for c in cols) + " | narrow " +
                  " ".join(f"{c['narrow']:.2f}" if c else "-" for c in cols) + " | depth " + " ".join(f"{c['depth']:.2f}" if c else "-" for c in cols))
