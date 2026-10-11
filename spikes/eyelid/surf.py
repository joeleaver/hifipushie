"""surf.py <tag>=<model> ...: the upper lid as ONE SURFACE on the dressed stage's own mesh (what is rendered), left eye.
Eye frame (mm): origin the eyeball's centre, u toward the outer corner, v up, w forward (the head's forward). A front
view height map: for each (u, v) the skin's STAND-OFF = its distance from the ball's centre minus the ball's radius
(0 = lying on the ball; the ball itself is r = our seated sphere).
Per column u = -9..9 the structure in numbers (h = mm up from the lid margin, s = stand-off):
  margin   v of the margin (lowest lid skin over the ball) and the margin roll (max s within 1.5 mm - s at the crease)
  platform height h_c of the crease (the lowest s between 1.5 and 9 mm up), its mean stand-off, its slope (deg from the
           ball's surface: 0 = hugging) and its bulge (max over the chord margin-roll -> crease)
  tuck     how sharply the surface turns at the crease: the change of slope (deg) within +-0.6 mm of it
  wall     the steepest slope of the fold above the crease within 3 mm (deg from the ball's surface; 90 = straight
           out, > 90 would overhang), and its width (mm from the crease to where the slope falls under half of it)
  drape    how far forward of the crease the skin stands 3 mm above it (mm)
Writes out/surf_<tag>.npz (maps) and out/surf.json (columns); surfplot.py draws them."""
import json
import os
import sys

import numpy as np
from scipy.interpolate import LinearNDInterpolator

import lidmap as lm
from hifipushie import onemesh, store

G = os.environ["G"] + "/out"
COLS = np.arange(-9.0, 9.01, 3.0)
STEP = 0.1


def eye_frame(name):
    """(verts in the eye frame (mm), normals, r mm) of the stage mesh near the subject's left eye."""
    sp = store.load(name)
    ht = onemesh.head_template(sp["base"])
    Vs, Ns, _ = lm.stage_mesh(name)
    R, t, med = lm.to_stage(name, ht, Vs)
    c = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float) @ R.T + t
    fwd = R @ np.asarray(ht["forward"], float)
    up = R @ np.array([0.0, 0.0, 1.0])
    up = up - fwd * (up @ fwd)
    up /= np.linalg.norm(up)
    left = np.cross(up, fwd)       # the subject's left = +x in world; (up x fwd) with fwd = -y, up = z gives +x
    if left[0] < 0:
        left = -left
    m = np.linalg.norm(Vs - c, axis=1) < 0.045
    X = (Vs[m] - c) * 1000
    P = np.c_[X @ left, X @ up, X @ fwd]
    N = np.c_[Ns[m] @ left, Ns[m] @ up, Ns[m] @ fwd]
    # the lid margin from GNM's own ring 0 (the upper half), in the same frame
    g = lm.gc.gnm()
    sk = lm.skin_ids()
    loc = -np.ones(len(g["T"]), int)
    loc[sk] = np.arange(len(sk))
    r0 = lm.topo()["loops"][0]
    r0 = r0[g["T"][r0, 1] > g["J"][2][1] + 0.0005]
    M = ((np.asarray(ht["verts"], float)[loc[r0]] @ R.T + t) - c) * 1000
    M = np.c_[M @ left, M @ up]
    M = M[np.argsort(M[:, 0])]
    return P, N, float(ht["eye_r"]) * 1000, med * 1000, M


def height_map(P, N, r, ulim=(-16, 16), vlim=(-4, 22)):
    """Front view: per (u, v) cell the most forward skin with a forward-facing normal. Returns U, V, W (forward)."""
    f = (N[:, 2] > 0.05) & (P[:, 2] > 0)
    Q = P[f]
    # the outermost layer: bin at 0.25 mm, keep points within 0.4 mm of the bin's most forward
    b = np.floor(Q[:, :2] / 0.3).astype(int)
    key = b[:, 0] * 100003 + b[:, 1]
    o = np.lexsort((-Q[:, 2], key))
    first = np.r_[True, key[o][1:] != key[o][:-1]]
    top = np.zeros(len(Q))
    top[o] = np.maximum.accumulate(np.where(first, Q[o, 2], -1e9))  # per bin (sorted desc inside a bin, so first = max)
    idx = np.cumsum(first) - 1
    mx = Q[o][first][:, 2]
    keep = np.zeros(len(Q), bool)
    keep[o] = Q[o, 2] > mx[idx] - 0.5
    Q = Q[keep]
    U = np.arange(ulim[0], ulim[1] + 1e-6, STEP)
    Vv = np.arange(vlim[0], vlim[1] + 1e-6, STEP)
    UU, VV = np.meshgrid(U, Vv)
    W = LinearNDInterpolator(Q[:, :2], Q[:, 2])(UU, VV)
    return U, Vv, W


def column(U, Vv, W, r, u):
    j = int(np.argmin(np.abs(U - u)))
    w = np.nanmean(W[:, max(j - 2, 0):j + 3], axis=1)
    s = np.sqrt(u * u + Vv ** 2 + w ** 2) - r
    return Vv, w, s


def read_column(Vv, w, s, mv):
    """The structure's numbers on one column (see the module's docstring); mv = the margin's v there (GNM's ring 0)."""
    out = {}
    ok = np.isfinite(s)
    i0 = int(np.argmin(np.abs(Vv - mv)))
    h = Vv - Vv[i0]
    out["margin_v"] = float(Vv[i0])
    sel = (h >= 0) & (h <= 12) & ok
    hh, ss, ww = h[sel], s[sel], w[sel]
    # stand-off's slope against the ball's surface, in degrees: atan(ds / d arc); arc ~ dh / cos(elevation) ~ dh here
    sm = np.convolve(ss, np.ones(5) / 5, mode="same")
    sl = np.degrees(np.arctan(np.gradient(sm, hh)))
    c0 = (hh >= 1.5) & (hh <= 9.0)
    if not c0.any():
        return None
    # the crease: the lowest stand-off before the fold; where the surface never comes back down, the start of the
    # steepest rise (largest slope increase)
    ic = int(np.flatnonzero(c0)[np.argmin(sm[c0])])
    if ic == np.flatnonzero(c0)[0] or ic == np.flatnonzero(c0)[-1]:
        k = int(0.6 / STEP)
        turn = np.array([sl[min(i + k, len(sl) - 1)] - sl[max(i - k, 0)] if c0[i] else -1e9 for i in range(len(sl))])
        ic = int(np.argmax(turn))
    out["crease_h"] = float(hh[ic])
    out["crease_s"] = float(sm[ic])
    lo = hh <= 1.5
    out["roll"] = float(sm[lo].max() - sm[ic])
    pl = (hh >= 0.3) & (hh <= hh[ic])
    out["platform_s"] = float(sm[pl].mean())
    ir = int(np.argmax(np.where(lo, sm, -1e9)))
    if ic > ir + 2:
        a = np.array([hh[ir], sm[ir]])
        b = np.array([hh[ic], sm[ic]])
        seg = np.c_[hh[ir:ic + 1], sm[ir:ic + 1]]
        ab = b - a
        n = np.array([-ab[1], ab[0]]) / np.linalg.norm(ab)
        out["bulge"] = float(((seg - a) @ n).max())
        out["platform_slope"] = float(np.degrees(np.arctan2(ab[1], ab[0])))
    k = int(0.6 / STEP)
    out["tuck"] = float(sl[min(ic + k, len(sl) - 1)] - sl[max(ic - k, 0)])
    ab_ = (hh > hh[ic]) & (hh <= hh[ic] + 3.0)
    if ab_.any():
        iw = int(np.flatnonzero(ab_)[np.argmax(sl[ab_])])
        out["wall"] = float(sl[iw])
        out["wall_h"] = float(hh[iw] - hh[ic])
        j = iw
        while j < len(sl) - 1 and sl[j] > 0.5 * sl[iw]:
            j += 1
        out["wall_w"] = float(hh[j] - hh[ic])
    i3 = int(np.argmin(np.abs(hh - (hh[ic] + 3.0))))
    out["drape"] = float(sm[i3] - sm[ic])
    out["h"], out["s"], out["slope"] = hh.round(3).tolist(), sm.round(3).tolist(), sl.round(2).tolist()
    return out


if __name__ == "__main__":
    res = json.load(open(G + "/surf.json")) if os.path.exists(G + "/surf.json") else {}
    keys = ("margin_v", "roll", "crease_h", "platform_s", "platform_slope", "bulge", "tuck", "wall", "wall_w", "drape")
    for a in sys.argv[1:]:
        tag, name = a.split("=", 1)
        P, N, r, med, M = eye_frame(name)
        U, Vv, W = height_map(P, N, r)
        np.savez_compressed(f"{G}/surf_{tag}.npz", U=U, V=Vv, W=W, r=r, M=M)
        res[tag] = {"model": name, "r": r, "cols": {}}
        print(f"\n{tag} ({name}); ball r {r:.2f} mm; stage aligned to {med:.2f} mm")
        print("    u  " + " ".join(f"{k:>9s}" for k in keys))
        for u in COLS:
            q = read_column(*column(U, Vv, W, r, u), float(np.interp(u, M[:, 0], M[:, 1])))
            if q is None:
                continue
            res[tag]["cols"][f"{u:.0f}"] = q
            print(f"  {u:+3.0f}  " + " ".join(f"{q.get(k, float('nan')):9.2f}" for k in keys))
        mid = [res[tag]["cols"][k] for k in ("-3", "0", "3") if k in res[tag]["cols"]]
        print("  mid  " + " ".join(f"{np.mean([q.get(k, np.nan) for q in mid]):9.2f}" for k in keys))
    json.dump(res, open(G + "/surf.json", "w"))
