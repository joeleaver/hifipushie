"""shapesolve.py <model> <donor spec> <out npz> [iters]: the eye step aimed at a crease SHAPE (gnmcrease 2; Joe: #376 /
#540 have the right fold, gd_T30 the wrong one): identity 170 + the 20 symmetric eye-region expression pairs, MAP, with the
eye step's holds (68 landmarks off the eyes 0.3 mm, brows 1 mm, the socket readings 0.15 sd, the lid margins vs the
iris at their start 0.05 r), and the evidence = the donor's upper-lid sagittal sections at the inner third / pupil / outer
third (col.py columns 0.25 / 0.5 / 0.75), relative to the lid margin, resampled by arclength 0.5 .. 8 mm, sigma SIG mm.
Writes the identity + expression pairs and the reads before / after."""
import json
import os
import sys
import time

import numpy as np

import col
import gk
from hifipushie import blockin as bi, blockin_eyes as be, store

SIG = float(os.environ.get("SIG", "0.3"))
CI = (1, 3, 5)
S = np.arange(0.5, float(os.environ.get("SMAX", "8")) + 0.01, 0.5)
CURV = float(os.environ.get("CURV", "0"))   # sigma (mm) on the sections' second differences (the fold's crest); 0 = off


def resample(P):
    P = np.asarray(P, float) * 1000
    P = P - P[0]
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    s = np.clip(S, 0, d[-1])
    return np.c_[np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])]


def sections(c, e, model):
    cols = col.columns(c, e, model)
    return [resample(col.PROF[i]) if col.PROF[i] is not None else None for i in CI], cols


def main(model, donor, out, iters=5):
    sp = store.load(model)
    c0 = bi.identity(sp)
    e0 = col.eye_e(sp)
    gk.base(model)
    cd, ed, _ = col.src(donor)
    tgt, tcols = sections(cd, ed, "gd_T12")
    Ln, Rn = gk.LN, gk.RN
    ex_other = {k: v for k, v in (sp["base"]["head"].get("expression") or {}).items() if k not in set(Ln) | set(Rn)}
    ht0 = gk.head(c0, e0, model)
    rd = be.Reader(ht0)
    q0 = rd.read(ht0)
    L0 = np.asarray(ht0["lm68"], float)

    def sock(c, e):
        return be.socket(c, {**ex_other, **{Ln[k]: e[k] for k in range(be.NE)}, **{Rn[k]: e[k] for k in range(be.NE)}})
    s0 = sock(c0, e0)

    def resid(x):
        c, e = c0 + x[:170], e0 + x[170:]
        sec, cols = sections(c, e, model)
        ht = gk.head(c, e, model)
        q = rd.read(ht)
        r = []
        for a, b in zip(sec, tgt):
            r += list(((a - b) / SIG).ravel()) if a is not None and b is not None else [20.0] * (2 * len(S))
            if CURV:
                r += list(((np.diff(a, 2, axis=0) - np.diff(b, 2, axis=0)) / CURV).ravel()) if a is not None and b is not None else [20.0] * (2 * len(S) - 4)
        r += [(q["up"] - q0["up"]) / 0.05, (q["lo"] - q0["lo"]) / 0.05]
        s = sock(c, e)
        r += [(s[k] - s0[k]) / be.SIG_SOCKET for k in be.SOCKET]
        L = np.asarray(ht["lm68"], float)
        r += list(((L[be.HOLD] - L0[be.HOLD]) * 1000 / be.SIG_HOLD).ravel())
        r += list(((L[be.BROWS] - L0[be.BROWS]) * 1000 / be.SIG_BROW).ravel())
        return np.array(r), cols
    n = 170 + be.NE
    x = np.zeros(n)
    r, cols0 = resid(x)
    nsec = 3 * 2 * len(S)    # (the shape rms printed is over the first section's points + curvature terms when CURV)
    f = float(r @ r + x @ x)
    print(f"start: shape rms {np.sqrt(np.mean((r[:nsec] * SIG) ** 2)):.2f} mm, cost {f:.1f}", flush=True)
    lam = 0.01
    t0 = time.time()
    for it in range(iters):
        J = np.zeros((len(r), n))
        h = 0.25
        for j in range(n):
            ej = np.zeros(n); ej[j] = h
            J[:, j] = (resid(x + ej)[0] - r) / h
        while True:
            step = np.linalg.solve(J.T @ J + (1 + lam) * np.eye(n), -(J.T @ r + x))
            rn, _ = resid(x + step)
            fn = float(rn @ rn + (x + step) @ (x + step))
            if fn < f:
                x, r, f, lam = x + step, rn, fn, lam * 0.5
                break
            lam *= 4
            if lam > 1e4:
                break
        print(f"it {it}: shape rms {np.sqrt(np.mean((r[:nsec] * SIG) ** 2)):.2f} mm, cost {f:.1f}, |dc| {np.linalg.norm(x[:170]):.2f}, "
              f"|de| {np.linalg.norm(x[170:]):.2f} ({time.time() - t0:.0f} s)", flush=True)
        if lam > 1e4:
            break
    c1, e1 = c0 + x[:170], e0 + x[170:]
    cols1 = col.columns(c1, e1, model)
    s1 = sock(c1, e1)
    for nm, cl in (("start", cols0), ("after", cols1), ("donor", tcols)):
        sm = col.summary(cl)
        print(f"{nm:6s} " + " ".join(f"{k} {v:.2f}" for k, v in sm.items()))
        print("       h per column " + " ".join(f"{q['h']:.1f}" if q else "-" for q in cl))
    print("socket " + ", ".join(f"{k} {s0[k]:+.2f} -> {s1[k]:+.2f}" for k in be.SOCKET))
    m0, m1 = gk.macro(c0), gk.macro(c1)
    ch = sorted(m0, key=lambda q: -abs(m1[q] - m0[q]))[:8]
    print("macros (identity only): " + ", ".join(f"{q} {m0[q]:+.2f}->{m1[q]:+.2f}" for q in ch))
    np.savez(out, c=c1, e=e1, dc=np.linalg.norm(x[:170]), de=np.linalg.norm(x[170:]))
    print("done", out, flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 5)
