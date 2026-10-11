"""foldfit.py: a DESIGNED folded upper lid (a real re-entrant fold: platform on the ball, tuck, a roll of drape hanging
d mm over the platform) as vertex targets on GNM's lid rings, and its least-squares fit in GNM's coefficients.
The fit's residual is the span test (can the linear basis make this shape at all?), its |dc| the prior cost.

design(V, ...): per radial chain (both eyes), ring k -> target (x kept, v, w), in the eye frame of the head's own ball:
  ring 0            the margin, kept
  rings 1..ka       the platform: heights spread to H at ring ka (the crease), stand-off sp from the ball (the margin's
                    own stand-off fading out over 1 mm)
  ring ka+1         the top of the slit: 0.35 mm above the crease, 0.45 mm further off the ball
  ring ka+2         the fold's lower edge: d mm BELOW the crease (front view), th mm in front of the platform
  ring ka+3         the roll's front: 0.8 mm up, 0.9 mm further forward
  rings ka+4..kt-1  on the straight line to the head's own ring kt (the drape; default 10), by the template's spacing
fit(c0, tgt, ...): min |W (V(x) - target)|^2 + |held / hold|^2 + |margins / mh|^2 + lam |dc|^2 (+ lam_e |e|^2).

CLI: foldfit.py <identity source> <save tag> [ka=5] [H=4.7] [d=1] [th=0.9] [sp=0.8] [hold=1,3,1000] [lam=1] [expr=0]
[n=170 (identity comps used)] [kt=10]"""
import os
import sys

import numpy as np

import foldopt as fo
import lidmap as lm
import ohlib as oh

g = oh.g
MIR = fo.MIR


def ball(V, grp):
    P = V[g["groups"][grp] & g["groups"]["scleras"]]
    A = np.c_[2 * P, np.ones(len(P))]
    sol = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
    return sol[:3], float(np.sqrt(sol[3] + sol[:3] @ sol[:3]))


def design(V, ka=5, H=4.7, d=1.0, th=0.9, sp=0.8, kt=10, umax=12.0, taper=3.0):
    """{vertex id: (target xyz raw mm, weight)} for both eyes' upper lids, rings 1..kt-1."""
    ch = oh.chains(umax, 0, 12)
    out = {}
    for side, grp in ((1, "left_eye"), (-1, "right_eye")):
        ids = ch if side == 1 else MIR[ch]
        ctr, r = ball(V, grp)
        P = V[ids] - ctr                                  # (n, 13, 3)
        Tm = oh.T[ch]
        hv = Tm[:, :, 1] - Tm[:, :1, 1]                   # the template's heights over the margin per chain
        ue = np.abs(oh.T[ch[:, 0], 0] - oh.JL[0])
        wt = np.clip((umax - ue) / taper, 0.0, 1.0)       # the fold fades into the corners
        for j in range(len(ch)):
            x = P[j, :, 0]
            v0 = P[j, 0, 1]
            s0 = np.linalg.norm(P[j, 0]) - r
            tgt = {}
            f = hv[j, 1:ka + 1] / hv[j, ka]
            for i, k in enumerate(range(1, ka + 1)):
                h = H * f[i]
                tgt[k] = (h, sp + (s0 - sp) * np.exp(-h / 1.0))
            tgt[ka + 1] = (H + 0.35, sp + 0.45)
            tgt[ka + 2] = (H - d, sp + th)
            tgt[ka + 3] = (H - d + 0.8, sp + th + 0.9)
            pts = {}
            for k, (h, s) in tgt.items():
                rho = r + s
                v = v0 + h
                w = np.sqrt(max(rho ** 2 - x[k] ** 2 - v ** 2, 0.0))
                pts[k] = np.array([x[k], v, w])
            a, b = pts[ka + 3], P[j, kt]
            cum = np.cumsum(np.linalg.norm(np.diff(Tm[j, ka + 3:kt + 1], axis=0), axis=1))
            for i, k in enumerate(range(ka + 4, kt)):
                q = a + (b - a) * (cum[i] / cum[-1])
                pts[k] = np.array([x[k], q[1], q[2]])
            for k, p in pts.items():
                # fade the designed lid into the head's own toward the corners
                q = wt[j] * p + (1 - wt[j]) * P[j, k]
                out[int(ids[j, k])] = (q + ctr, 1.0)
    return out


def fit(c0, tgt, ne=0, n=170, hold=1.0, mh=0.05, lam=1.0, lam_e=1.0, sig=0.1, free_all=False, hang=None, inner=3.0):
    """Returns (c1, e1 | None, info). hold: mm for every other exterior skin vertex + the eyeballs (inf: free);
    free_all: no holds at all (the pure projection)."""
    c0 = np.asarray(c0, float)[:170]
    ids = np.array(sorted(tgt))
    P = np.array([tgt[i][0] for i in ids])
    S = fo.setup(ne)
    B = S["B"]
    use = np.r_[np.arange(n), 170 + np.arange(ne)]
    V0 = oh.verts(c0)
    D0 = (P - V0[ids]).ravel() / sig
    At = (B[use][:, ids] / sig).reshape(len(use), -1).T
    Q = At.T @ At
    rhs = At.T @ D0
    hm = np.zeros(len(oh.T), bool)
    if not free_all:
        ext = g["groups"]["skin_exterior"] | g["groups"]["eyes"]
        hm = (g["groups"]["skin"] | g["groups"]["eyes"]).copy()      # the skin's inside (socket lining, mouth bag) held too, looser
        hm[ids] = False
        rr = np.minimum(np.abs(oh.t["ring"]), np.abs(oh.t["ring"][MIR]))
        w = np.where(rr == 0, 1.0 / mh, np.where(ext, 1.0 / hold, 1.0 / (inner * hold)))[hm]
        Ah = (B[use][:, hm] * w[None, :, None]).reshape(len(use), -1)
        Q = Q + Ah @ Ah.T
    Pr = np.diag(np.r_[np.full(n, lam), np.full(ne, lam_e)])
    if hang is None:
        dx = np.linalg.solve(Q + Pr, rhs)
    else:                       # hard rows: the overhang (ring kb's skin d below ring ka's) and the gap in front
        ka, kb, d, gap = hang
        R = fo.rows(S, ka, kb)
        x0 = np.zeros(len(B))
        x0[:170] = c0
        A = np.array([R["hang"][use], R["gap"][use]])
        b = np.array([d - (R["hang0"] + R["hang"] @ x0), gap - (R["gap0"] + R["gap"] @ x0)])
        K = np.block([[Q + Pr, A.T], [A, np.zeros((2, 2))]])
        dx = np.linalg.solve(K, np.r_[rhs, b])[:len(use)]
    res = (D0 - At @ dx).reshape(-1, 3) * sig
    c1 = c0.copy()
    c1[:n] += dx[:n]
    e1 = None
    if ne:
        e1 = np.zeros(len(g["ex_names"]))
        e1[fo.EL[:ne]] = dx[n:]
        e1[fo.ER[:ne]] = dx[n:]
    mv = np.tensordot(dx, B[use][:, hm], 1) if hm.any() else np.zeros((1, 3))
    worst = {}
    if hm.any():
        hid = np.flatnonzero(hm)
        mvn = np.linalg.norm(mv, axis=1)
        for nm, m in g["groups"].items():
            if nm.endswith("_region") or nm in ("ears", "eye_sockets", "eyes", "mouth_sock"):
                if m[hid].any():
                    worst[nm] = float(mvn[m[hid]].max())
        worst = dict(sorted(worst.items(), key=lambda kv: -kv[1])[:5])
    rk = oh.t["ring"][ids]
    rk = np.where(rk == 99, oh.t["ring"][MIR[ids]], rk)
    return c1, e1, {"dc": float(np.linalg.norm(dx[:n])), "c": float(np.linalg.norm(c1)), "e": float(np.linalg.norm(dx[n:])),
                    "res": float(np.sqrt((res ** 2).sum(1).mean())), "res_max": float(np.linalg.norm(res, axis=1).max()),
                    "res_ring": {int(k): float(np.sqrt((res[rk == k] ** 2).sum(1).mean())) for k in np.unique(rk)},
                    "start": float(np.sqrt(((P - V0[ids]) ** 2).sum(1).mean())),
                    "held_rms": float(np.sqrt((mv ** 2).sum(1).mean())), "held_max": float(np.linalg.norm(mv, axis=1).max()), "worst": worst}


if __name__ == "__main__":
    import lidstruct as ls
    src, tag = sys.argv[1:3]
    kw = dict(a.split("=", 1) for a in sys.argv[3:])
    c0 = ls.ident(src)
    V0 = oh.verts(c0)
    ch7 = oh.chains(7.0)
    ka, H, d = int(kw.get("ka", 5)), float(kw.get("H", 4.7)), float(kw.get("d", 1.0))
    tgt = design(V0, ka, H, d, float(kw.get("th", 0.9)), float(kw.get("sp", 0.8)), int(kw.get("kt", 10)))
    Vt = V0.copy()
    for i, (p, _) in tgt.items():
        Vt[i] = p
    print(f"{src}: |c| {np.linalg.norm(c0):.2f}; as is: {oh.fmt(oh.read(V0, ch7))}")
    print(f"  TARGET (ka {ka}, H {H}, d {d}): {oh.fmt(oh.read(Vt, ch7))}")
    np.savez(os.environ["G"] + f"/out/{tag}_target.npz", V=Vt, c=c0)
    ne, n = int(kw.get("expr", 0)), int(kw.get("n", 170))
    c1, e1, I = fit(c0, tgt, ne=ne, n=n, lam=1e-6, lam_e=1e-6, free_all=True)
    print(f"  PROJECTION (lid targets only, no hold, no prior, {n} id + {ne} expr): residual rms {I['res']:.3f} mm (max {I['res_max']:.2f}; start {I['start']:.2f}) "
          f"|dc| {I['dc']:.1f} |e| {I['e']:.1f} | {oh.fmt(oh.read(oh.verts(c1, e1), ch7))}")
    for hold in [float(x) for x in kw.get("hold", "1000,3,1,0.3").split(",")]:
        for lam in [float(x) for x in kw.get("lam", "1").split(",")]:
            hg = (ka, ka + 2, float(kw["hang"]), float(kw.get("gap", 0.6))) if "hang" in kw else None
            c1, e1, I = fit(c0, tgt, ne=ne, n=n, hold=hold, lam=lam, lam_e=float(kw.get("lam_e", lam)), hang=hg, sig=float(kw.get("sig", 0.1)))
            q = oh.read(oh.verts(c1, e1), ch7)
            print(f"  hold {hold:g} lam {lam:g}: residual {I['res']:.3f} (max {I['res_max']:.2f}) |dc| {I['dc']:5.2f} |c| {I['c']:5.2f} |e| {I['e']:.2f} "
                  f"held rms {I['held_rms']:.2f} max {I['held_max']:.2f} | {oh.fmt(q)}")
            print("      residual by ring:", " ".join(f"{k}:{v:.2f}" for k, v in I["res_ring"].items()), "| worst held:", " ".join(f"{k} {v:.1f}" for k, v in I["worst"].items()))
            np.savez(os.environ["G"] + f"/out/{tag}_h{hold:g}_l{lam:g}.npz", c=c1, e=e1 if e1 is not None else np.zeros(383))
