"""m3prior.py [analyse|build]: faces5 M3, the joint identity prior. GNM's own block (170 head components, whitened:
GNM's prior is N(0, I)) re-estimated from ICT FaceKit Light's 100 identity modes carried onto GNM (ictreg.py,
out/ict_modes.npz; ICT's weights are N(0, 1) in its own sampler, so each carried mode is a 1-sd population draw axis).

Per ICT mode y (over GNM's face skin) one MAP fit of
    similarity (7 dof, free)  +  GNM identity c (170, prior N(0, I))  +  GNM expression e (prior N(0, EXPR_SD^2 I))
at NOISE m per coordinate. The similarity is the scan's placement / size normalisation (ICT's mode 0 is 96% scale), the
expression part is the scans' "neutral" not being neutral (lips parted, brows raised: ICT modes 9, 20, 25, 28 have their
GNM residual in the lips / forehead). Only c is identity: Sigma_ICT = C C^T in GNM's whitened coordinates.

analyse: shares per mode (similarity / identity / expression / residual), Sigma_ICT's spectrum, its diagonal by
component band, the variance ICT puts along GNM's similarity directions.
build: writes out/m3_prior.npz (see build())."""
import os
import sys
from pathlib import Path

import numpy as np

from hifipushie import base as basemod

F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces5"))
OUT = F / "out"
NOISE = float(os.environ.get("NOISE", "0.0003"))
EXPR_SD = float(os.environ.get("EXPR_SD", "0.3"))   # GNM's expression units are sds of its whole expressive range

g = basemod._gnm_data()
names = [str(x) for x in g["identity_names"]]
hc = [i for i, x in enumerate(names) if x.startswith("head")]
IB = np.asarray(g["vertex_identity_basis"], float)[hc]
EB = np.asarray(g["expression_basis"], float)
ex_names = [str(x) for x in g["expression_names"]]
TPL = np.asarray(g["template_vertex_positions"], float)
grp = lambda k: np.asarray(g["groups"][k], float) > 0.5  # noqa: E731
ext = grp("skin_exterior")
face = np.zeros(len(TPL), bool)
for r in g["groups"]:
    if r.endswith("_region"):
        face |= grp(r)
FITREG = os.environ.get("FITREG", "head")
# head (default): the face + cranium + ears, where ICT's carried modes are bound (not the neck below the chin: ICT's
# neck varies 2.3x GNM's there, the scans' head pose). Fitted over the face alone, the fine GNM comps' large moves of
# the ears / cranium went unconstrained: prior samples flapped the ears and swelled the jowls (f5_01 first version).
if FITREG == "face":
    sk = np.flatnonzero(ext & face)
else:
    _bound = np.load(OUT / "ict_modes.npz")["bound"].astype(bool)
    _chin = TPL[np.asarray(g["groups"]["chin_region"], float) > 0.5, 1].min()
    sk = np.flatnonzero(ext & _bound & ((TPL[:, 1] >= _chin) | face))
P = TPL[sk] - TPL[sk].mean(0)
S = np.zeros((len(sk) * 3, 7))
S[:, :3] = np.tile(np.eye(3), (len(sk), 1))
S[0::3, 4], S[0::3, 5] = P[:, 2], -P[:, 1]
S[1::3, 3], S[1::3, 5] = -P[:, 2], P[:, 0]
S[2::3, 3], S[2::3, 4] = P[:, 1], -P[:, 0]
S[:, 6] = P.ravel()
S /= np.linalg.norm(S, axis=0)          # unit columns: the similarity is free (tiny ridge only)
Bf = IB[:, sk].reshape(len(hc), -1)     # (170, 3n)
NEX_EYE = int(os.environ.get("NEX_EYE", "20"))     # per eye region: the first comps are the lids / brows' motions
NEX_LOW = int(os.environ.get("NEX_LOW", "30"))     # lower face: lips parting, corners, jaw
# (the rest are 0.01-0.03 mm per unit: with them free the fit traded fine identity detail against expression)
ekeep = [i for i, x in enumerate(ex_names) if (x.startswith(("left_eye", "right_eye")) and int(x[-3:]) < NEX_EYE)
         or (x.startswith("lower_face") and int(x[-3:]) < NEX_LOW)]
Be = EB[ekeep][:, sk].reshape(len(ekeep), -1)
M = np.load(OUT / "ict_modes.npz")["modes"].astype(float)
Y = np.stack([M[k][sk].ravel() for k in range(len(M))])   # (100, 3n)
NC = len(hc)


def fit(Y, use_expr=True, use_sim=True):
    """MAP of every row of Y on [S | Bf | Be]: returns dict of coefficient blocks and the parts' shapes."""
    blocks = []
    if use_sim:
        blocks.append(("sim", S.T, 1e3))
    blocks.append(("id", Bf, 1.0))
    if use_expr:
        blocks.append(("ex", Be, EXPR_SD))
    A = np.concatenate([b for _, b, _ in blocks])           # (p, 3n)
    pri = np.concatenate([np.full(len(b), 1.0 / s ** 2) for _, b, s in blocks])
    H = A @ A.T / NOISE ** 2 + np.diag(pri)
    X = np.linalg.solve(H, A @ Y.T / NOISE ** 2)            # (p, m)
    out, i = {}, 0
    for nm, b, _ in blocks:
        out[nm] = X[i:i + len(b)]
        out[nm + "_shape"] = (b.T @ out[nm]).T             # (m, 3n)
        i += len(b)
    return out


def sim_dirs():
    """(170, 7) orthonormal c-directions that make GNM's best similarity moves over the face (the c-space subspace the
    similarity normalisation of ICT's scans hides)."""
    G = Bf @ Bf.T + NOISE ** 2 * np.eye(NC)
    A = np.linalg.solve(G, Bf @ S)
    q, _ = np.linalg.qr(A)
    return q


def analyse():
    for label, ue in (("identity + similarity", False), ("identity + similarity + expression", True)):
        r = fit(Y, use_expr=ue)
        tot = np.sum(Y ** 2, 1)
        sh = {k: np.sum(r[k + "_shape"] ** 2, 1) / tot for k in ("sim", "id", "ex") if k + "_shape" in r}
        res = Y - sum(r[k + "_shape"] for k in ("sim", "id", "ex") if k + "_shape" in r)
        sh["res"] = np.sum(res ** 2, 1) / tot
        print(f"== {label}: share of each ICT mode's face variance (median over modes / variance-weighted)")
        for k, v in sh.items():
            wv = float(np.sum(v * tot) / np.sum(tot))
            print(f"   {k:4s} median {np.median(v):.3f}  weighted {wv:.3f}")
        if ue:
            top = np.argsort(-sh["ex"])[:12]
            print("   most expression-like ICT modes:", ", ".join(f"{k}:{sh['ex'][k]:.2f}" for k in top))
            # which expression comps carry it
            ev = np.sum(r["ex"] ** 2, 1)
            top = np.argsort(-ev)[:10]
            print("   expression comps used most (sum of squares over modes):",
                  ", ".join(f"{ex_names[ekeep[k]]}:{ev[k]:.2f}" for k in top))
        C = r["id"]
        Sig = C @ C.T
        w, V = np.linalg.eigh(Sig)
        w = w[::-1]
        d = np.diag(Sig)
        print(f"   Sigma_ICT trace {np.trace(Sig):.0f} (GNM: {NC}); eigenvalues top {np.round(w[:6], 1)} | 10th {w[9]:.1f} 50th "
              f"{w[49]:.2f} 90th {w[89]:.2f} 100th {w[99]:.3f}")
        print("   diag by band: " + " | ".join(f"{a}-{b - 1} {np.mean(d[a:b]):.2f}" for a, b in
                                                ((0, 5), (5, 10), (10, 50), (50, 120), (120, 170))))
        q = sim_dirs()
        print(f"   ICT variance along GNM's similarity directions (7, GNM = 1 each): {np.round(np.diag(q.T @ Sig @ q), 2)}")


def _sim(ids, centre, scale=None):
    Pp = TPL[ids] - centre
    Sx = np.zeros((len(ids) * 3, 7))
    Sx[:, :3] = np.tile(np.eye(3), (len(ids), 1))
    Sx[0::3, 4], Sx[0::3, 5] = Pp[:, 2], -Pp[:, 1]
    Sx[1::3, 3], Sx[1::3, 5] = -Pp[:, 2], Pp[:, 0]
    Sx[2::3, 3], Sx[2::3, 4] = Pp[:, 1], -Pp[:, 0]
    Sx[:, 6] = Pp.ravel()
    if scale is None:
        scale = np.linalg.norm(Sx, axis=0)
    return Sx / scale, scale


def cv():
    """How much identity should take: fit every ICT mode on the FACE (similarity free + GNM identity at noise sigma,
    prior N(0, I); + expression when EXPR=1), predict the cranium + ears (held out: ICT's carried modes are bound there)
    with the same similarity and c, and compare to ICT's own off-face values. Too little noise: c blows up along
    face-cheap / skull-expensive directions and the skull prediction is worse than predicting nothing."""
    bound = np.load(OUT / "ict_modes.npz")["bound"].astype(bool)
    chin = TPL[grp("chin_region"), 1].min()
    fi = np.flatnonzero(ext & face)
    oi = np.flatnonzero(ext & bound & ~face & (TPL[:, 1] >= chin))
    cen = TPL[fi].mean(0)
    Sf, sc = _sim(fi, cen)
    So, _ = _sim(oi, cen, sc)
    Bff = IB[:, fi].reshape(NC, -1)
    Bo = IB[:, oi].reshape(NC, -1)
    Yf = np.stack([M[k][fi].ravel() for k in range(len(M))])
    Yo = np.stack([M[k][oi].ravel() for k in range(len(M))])
    use_e = os.environ.get("EXPR", "0") == "1"
    A = [Sf.T, Bff] + ([EB[ekeep][:, fi].reshape(len(ekeep), -1)] if use_e else [])
    A = np.concatenate(A)
    for sg in [float(x) * 1e-3 for x in os.environ.get("SIGMAS", "0.1,0.3,0.6,1,2,4,8,16").split(",")]:
        pri = np.r_[np.full(7, 1e-6), np.ones(NC)] if not use_e else np.r_[np.full(7, 1e-6), np.ones(NC),
                                                                             np.full(len(ekeep), 1 / EXPR_SD ** 2)]
        H = A @ A.T / sg ** 2 + np.diag(pri)
        X = np.linalg.solve(H, A @ Yf.T / sg ** 2)
        a, c = X[:7], X[7:7 + NC]
        pf = (Sf @ a + Bff.T @ c).T
        po = (So @ a + Bo.T @ c).T
        po_sim = (So @ a).T                         # the similarity alone, no identity
        ef = np.sum((Yf - pf) ** 2) / np.sum(Yf ** 2)
        eo = np.sum((Yo - po) ** 2) / np.sum(Yo ** 2)
        eo0 = np.sum((Yo - po_sim) ** 2) / np.sum(Yo ** 2)
        Sig = c @ c.T
        print(f"noise {sg * 1e3:.1f} mm: face unexplained {ef:.3f} | skull+ears held out: unexplained {eo:.3f} "
              f"(similarity only {eo0:.3f}) | trace C C^T {np.trace(Sig):.0f}, diag 0-9 {np.mean(np.diag(Sig)[:10]):.2f} "
              f"120-169 {np.mean(np.diag(Sig)[120:]):.2f}", flush=True)


def em(tau=1.0, iters=60, use_expr=True, log=print):
    """Empirical-Bayes (EM, population level) estimate of the joint prior over z = [c (170), h (habitual expression)]
    from ICT's carried modes: y = S a + B^T z + noise, a (similarity) free, z ~ N(0, Sz), the noise isotropic PER
    REGION (face, skull + ears) with its own ML variance (ICT's skull is weakly tied to its face: it weighs itself).
    E-step: posterior mean m_k of every mode and the shared posterior covariance; M-step:
        Sz <- (tau * S0 + (M M^T + Post)) / (tau + 1)
    (S0 = GNM's prior blockdiag(I, EXPR_SD^2 I): an inverse-Wishart pull toward GNM with tau = GNM's weight relative to
    ICT's sample, a CHOICE: ICT's number of subjects isn't published; GNM's training set is larger), and the region
    noise <- mean squared residual + its posterior part. Returns dict(cov, sig_face, sig_off, history)."""
    bound = np.load(OUT / "ict_modes.npz")["bound"].astype(bool)
    chin = TPL[grp("chin_region"), 1].min()
    fi = np.flatnonzero(ext & face)
    oi = np.flatnonzero(ext & bound & ~face & (TPL[:, 1] >= chin))
    ids = np.r_[fi, oi]
    reg = np.r_[np.zeros(3 * len(fi), int), np.ones(3 * len(oi), int)]
    Ss, _ = _sim(ids, TPL[fi].mean(0))
    Q, _ = np.linalg.qr(Ss)
    proj = lambda X: X - (X @ Q) @ Q.T  # noqa: E731   rows: similarity removed over the whole fit region
    Bz = IB[:, ids].reshape(NC, -1)
    nh = 0
    if use_expr:
        Bh = EB[ekeep][:, ids].reshape(len(ekeep), -1)
        Bz = np.r_[Bz, Bh]
        nh = len(ekeep)
    Bz = proj(Bz)
    Yp = proj(np.stack([M[k][ids].ravel() for k in range(len(M))]))
    S0 = np.diag(np.r_[np.ones(NC), np.full(nh, EXPR_SD ** 2)])
    Sz = S0.copy()
    s2 = np.array([0.001 ** 2, 0.002 ** 2])
    hist = []
    for it in range(iters):
        w = 1.0 / s2[reg]
        A = (Bz * w) @ Bz.T
        Post = np.linalg.inv(np.linalg.inv(Sz) + A)
        Mm = Post @ ((Bz * w) @ Yp.T)                       # (p, 100) posterior means
        R = Yp - Mm.T @ Bz
        # per region: residual + posterior spread (tr(B_r^T Post B_r))
        BP = Post @ Bz
        tr = np.sum(Bz * BP, 0)                             # per row: b^T Post b
        for r_ in (0, 1):
            m_ = reg == r_
            s2[r_] = (np.sum(R[:, m_] ** 2) + len(M) * 0 + np.sum(tr[m_])) / m_.sum()
        Sz = (tau * S0 + Mm @ Mm.T + Post) / (tau + 1.0)
        Sz = 0.5 * (Sz + Sz.T)
        if it % 10 == 0 or it == iters - 1:
            d = np.diag(Sz)[:NC]
            fe = np.sum(R[:, reg == 0] ** 2) / np.sum(Yp[:, reg == 0] ** 2)
            hist.append((it, float(np.trace(Sz[:NC, :NC])), float(np.sqrt(s2[0]) * 1e3), float(np.sqrt(s2[1]) * 1e3), fe))
            log(f"  it {it:3d}: trace c {np.trace(Sz[:NC, :NC]):6.1f} | diag 0-9 {np.mean(d[:10]):.2f} 10-49 {np.mean(d[10:50]):.2f} "
                f"50-119 {np.mean(d[50:120]):.2f} 120-169 {np.mean(d[120:]):.2f} | h trace {np.trace(Sz[NC:, NC:]):.2f} | noise "
                f"face {np.sqrt(s2[0]) * 1e3:.2f} skull {np.sqrt(s2[1]) * 1e3:.2f} mm | face unexplained {fe:.3f}", flush=True)
    return {"cov": Sz, "sig_face": float(np.sqrt(s2[0])), "sig_off": float(np.sqrt(s2[1])), "hist": hist, "nh": nh,
            "Mm": Mm}


H_FLOOR = float(os.environ.get("H_FLOOR", "0.05"))   # DESIGNED: habitual-expression sd ICT doesn't see (GNM units)


def build(path=None):
    """The joint prior over z = [c (170 identity), h (habitual expression, ekeep comps)], GNM-whitened c.
    c block = GNM UNION ICT: in the eigenbasis of ICT's identity covariance C C^T, each direction keeps the larger of
    GNM's variance (1) and ICT's (the coarse comps keep GNM's spread, calibrated on ANSUR; the fine ones take ICT's
    larger one; similarity-like directions, which ICT's normalised scans can't see, keep GNM's). h block = ICT's
    habitual expression E E^T + a designed floor H_FLOOR^2. Cross block = C E^T (ICT's shape <-> carriage coupling).
    Joint = [C; E][C; E]^T + blockdiag(V max(1 - lam, 0) V^T, H_FLOOR^2 I): PSD by construction."""
    r = fit(Y, use_expr=True)
    C, E = r["id"], r["ex"]                       # (170, 100), (nh, 100)
    lam, V = np.linalg.eigh(C @ C.T)
    lam = np.maximum(lam, 0)
    dc = V @ np.diag(np.maximum(1.0 - lam, 0)) @ V.T
    Z = np.r_[C, E]
    nh = len(E)
    J = Z @ Z.T
    J[:NC, :NC] += dc
    J[NC:, NC:] += H_FLOOR ** 2 * np.eye(nh)
    J = 0.5 * (J + J.T)
    # how much of each ICT mode the prior's three parts take (for the notes)
    tot = np.sum(Y ** 2, 1)
    share = {k: np.sum(r[k + "_shape"] ** 2, 1) / tot for k in ("sim", "id", "ex")}
    out = {"cov": J.astype(np.float64), "nc": NC, "h_names": np.array([ex_names[i] for i in ekeep]),
           "C": C, "E": E, "lam": lam[::-1], "noise": NOISE, "expr_sd": EXPR_SD, "h_floor": H_FLOOR,
           "nex_eye": NEX_EYE, "nex_low": NEX_LOW, "share_ex": share["ex"], "share_id": share["id"]}
    p = Path(path or OUT / "m3_prior.npz")
    np.savez_compressed(p, **out)
    Sc = J[:NC, :NC]
    d = np.diag(Sc)
    print(f"wrote {p}: c block trace {np.trace(Sc):.0f} (GNM {NC}); diag by band "
          + " | ".join(f"{a}-{b - 1} {np.mean(d[a:b]):.2f}" for a, b in ((0, 5), (5, 10), (10, 50), (50, 120), (120, 170)))
          + f"; ICT eigen > 1: {int(np.sum(lam > 1))}; h block trace {np.trace(J[NC:, NC:]):.2f} over {nh} comps; "
          f"|corr(c, h)| max {np.max(np.abs(J[:NC, NC:] / np.sqrt(np.outer(d, np.diag(J[NC:, NC:]))))):.2f}")
    return out


def build_em(path=None):
    tau = float(os.environ.get("TAU", "1"))
    ue = os.environ.get("EXPR", "1") == "1"
    r = em(tau, use_expr=ue)
    nh = r["nh"]
    out = {"cov": r["cov"], "nc": NC, "h_names": np.array([ex_names[i] for i in ekeep][:nh] if nh else [], dtype=str),
           "tau": tau, "sig_face": r["sig_face"], "sig_off": r["sig_off"], "expr_sd": EXPR_SD, "nex_eye": NEX_EYE,
           "nex_low": NEX_LOW, "method": "em"}
    p = Path(path or OUT / f"m3_em_tau{tau:g}{'_h' if ue else ''}.npz")
    np.savez_compressed(p, **out)
    print("wrote", p)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "analyse"
    if what == "build_em":
        build_em()
        sys.exit()
    {"analyse": analyse, "build": build, "cv": cv, "em": lambda: em(float(os.environ.get("TAU", "1")), use_expr=os.environ.get("EXPR", "1") == "1")}[what]()
