"""fit3d.py <tag> [prior=1] [expr=0|1] [scale=fixed|free] [out=<name>]: GNM fitted DIRECTLY to a scan's head surface
in 3D (no pictures): the representational CEILING. Variables: the scan's pose (rigid; + scale when asked or when the
scan has no real scale), GNM's 170 head identity components (prior N(class mean, 1) x `prior`), optionally the
expression nuisance (blockin's set: 20 lower-face + 6 + 6 eye-region components, their own sd). Data: two-sided
point-to-plane distances, GNM's fit vertices -> the scan's surface and an even 1.5 mm sampling of the scan's skin ->
GNM's surface (Gauss-Newton, correspondences found again every round, Huber at 3 mm, the reach coming down from 20 to
8 mm). Weight ("normal"): the two sets together count as N_EFF = 2000 independent reads at SIGMA = 1 mm (about the
information of a three-view picture solve: face_ruler's outline reads at 0.3-0.5 mm + dense at ~1 mm with NEFF 80).
-> work/<tag>/fit_<out>.json {c, e, S, table, measures}; out defaults to p<prior>[e]."""
import json
import sys
import time
import numpy as np
import gt

N_EFF, SIGMA, HUBER = 2000.0, 1.0, 3.0      # reads, mm, mm


def fit(scan, S0, prior=1.0, expr=False, scale_free=False, rounds=40, log=print, c_start=None, cmax=None, pose_only=False, skin_v=None):
    G = gt.gnm()
    F, B, E = G["F"], G["B"], G["E"]
    Bt = np.ascontiguousarray(np.transpose(B, (1, 2, 0)))        # (V, 3, 170)
    Et = np.ascontiguousarray(np.transpose(E, (1, 2, 0)))
    c0 = gt.class_mean(scan["info"]["sex"])
    c = c0.copy() if c_start is None else np.asarray(c_start, float).copy()
    if pose_only:          # the head as it is: only the scan's pose (and scale) is fitted
        c0, prior = c.copy(), 1e10
    e = np.zeros(len(E))
    S = S0
    skin_v = gt.scan_skin(scan, S0) if skin_v is None else skin_v
    skin_f = skin_v[scan["F"]].all(1)
    # the scan's samples: skin, near the head (within 25 mm of the start head's fit surface)
    Vg0 = gt.verts(c)
    P0 = gt.apply(S0, scan["V"])
    from scipy.spatial import cKDTree
    near = cKDTree(Vg0[G["fit"]]).query(P0)[0] < 0.025
    cand = np.flatnonzero(near & skin_v)
    samp = cand[gt.voxel_sample(P0[cand], 0.0015)]
    bnd = gt.boundary_vertices(F, len(G["T"]))
    gfit = np.flatnonzero(G["fit"] & ~(G["gr"]["ears"] & (gt.vertex_normals(Vg0, F)[:, 1] > 0.5)))      # ears' backs out
    nk, ne = len(c), (len(e) if expr else 0)
    sgn = gt.outward_sign(scan["V"], scan["F"])
    hist = []
    for it in range(rounds):
        reach = max(0.008, 0.020 * (0.85 ** it))
        Vg = gt.verts(c, e if expr else None)
        vn = gt.vertex_normals(Vg, F)
        Vs = gt.apply(S, scan["V"])
        sc = gt.Surface(Vs, scan["F"]) if it == 0 else sc
        if it:
            sc.V = Vs
            sc.tree, sc.ctree, sc.fn = cKDTree(Vs), cKDTree(Vs[scan["F"]].mean(1)), gt.face_normals(Vs, scan["F"])
        o = Vg[G["regions"]["face"]].mean(0)
        # A: GNM vertices -> scan (point to the scan's plane)
        Q, d, fi, _ = sc.closest(Vg[gfit])
        n = sgn * sc.fn[fi]
        okA = (d < reach) & ((n * vn[gfit]).sum(1) > 0.5) & skin_f[fi]
        ia = gfit[okA]
        nA, qA = n[okA], Q[okA]
        rA = ((Vg[ia] - qA) * nA).sum(1)
        JA_c = np.einsum("nd,ndk->nk", nA, Bt[ia])
        JA_e = np.einsum("nd,ndk->nk", nA, Et[ia]) if expr else np.zeros((len(ia), 0))
        p = qA - o
        JA_p = np.c_[-np.cross(p, nA), -nA, -(nA * p).sum(1)]
        # B: scan samples -> GNM's surface (point to GNM's plane)
        sg = gt.Surface(Vg, F)
        q = Vs[samp]
        Qg, dg, fg, bw = sg.closest(q)
        tri = F[fg]
        onb = (bw * bnd[tri]).sum(1) > 0.999              # on an opening's edge (lid aperture, mouth, the neck's cut)
        vmax = tri[np.arange(len(tri)), bw.argmax(1)]
        m = sg.fn[fg]
        sn = sgn * gt.vertex_normals(Vs, scan["F"])[samp]
        okB = (dg < reach) & ~onb & G["fit"][vmax] & np.isin(vmax, gfit) & ((sn * m).sum(1) > 0.3)
        m = m[okB]
        qB, QgB, triB, bwB = q[okB], Qg[okB], tri[okB], bw[okB]
        rB = ((qB - QgB) * m).sum(1)
        JB_c = -sum(np.einsum("nd,ndk->nk", m * bwB[:, [k]], Bt[triB[:, k]]) for k in range(3))
        JB_e = -sum(np.einsum("nd,ndk->nk", m * bwB[:, [k]], Et[triB[:, k]]) for k in range(3)) if expr else np.zeros((len(m), 0))
        p = qB - o
        JB_p = np.c_[np.cross(p, m), m, (m * p).sum(1)]
        rows_r, rows_J = [], []
        for r, Jc, Je, Jp in ((rA, JA_c, JA_e, JA_p), (rB, JB_c, JB_e, JB_p)):
            r_mm = r * 1000 / S[0]          # in the SCAN's own millimetres: a free scale must not win by shrinking the errors
            w = np.sqrt(np.where(np.abs(r_mm) <= HUBER, 1.0, HUBER / np.maximum(np.abs(r_mm), 1e-9)))
            k = np.sqrt(N_EFF / 2 / max(len(r), 1)) / SIGMA
            J = np.c_[Jc, Je, Jp if scale_free else Jp[:, :6]] * 1000 / S[0]
            rows_r.append(w * k * r_mm)
            rows_J.append((w * k)[:, None] * J)
        npose = 7 if scale_free else 6
        # priors
        Pc = np.zeros((nk, nk + ne + npose))
        Pc[:, :nk] = np.sqrt(prior) * np.eye(nk)
        rows_J.append(Pc)
        rows_r.append(np.sqrt(prior) * (c - c0))
        if expr:
            Pe = np.zeros((ne, nk + ne + npose))
            Pe[:, nk:nk + ne] = np.diag(1.0 / G["esd"])
            rows_J.append(Pe)
            rows_r.append(e / G["esd"])
        J, r = np.vstack(rows_J), np.concatenate(rows_r)
        H = J.T @ J
        H[np.diag_indices_from(H)] += 1e-6 + (1e-2 if prior == 0 else 0)
        gvec = J.T @ r
        free = np.ones(len(gvec), bool)
        for _ in range(6):          # the bound as an ACTIVE SET: a component at +-cmax whose step points further out is held
            dx = np.zeros(len(gvec))
            dx[free] = -np.linalg.solve(H[np.ix_(free, free)], gvec[free])
            if not cmax:
                break
            out_ = np.zeros(len(gvec), bool)
            out_[:nk] = np.abs(c + dx[:nk] - c0) > cmax + 1e-9
            if not (out_ & free).any():
                break
            # the worst offenders are stepped exactly to the bound and held
            t = np.clip(c + dx[:nk], c0 - cmax, c0 + cmax) - c
            at = np.zeros(len(gvec), bool)
            at[:nk] = out_[:nk]
            gvec = gvec + H[:, at] @ np.r_[t, np.zeros(len(gvec) - nk)][at]
            c = np.where(out_[:nk], c + t, c)
            free &= ~at
        dcn = np.linalg.norm(dx[:nk])
        if dcn > 3.0 and not cmax:
            dx *= 3.0 / dcn
        c = c + dx[:nk]
        if cmax:
            c = c0 + np.clip(c - c0, -cmax, cmax)
        if expr:
            e = e + dx[nk:nk + ne]
        dp = dx[nk + ne:]
        Rd = gt.rotvec(dp[:3])
        sd = 1.0 + (dp[6] if scale_free else 0.0)
        S = gt.compose((sd, Rd, o - sd * Rd @ o + dp[3:6]), S)
        ma = float(np.abs(np.r_[rA, rB]).mean() * 1000)
        hist.append(ma)
        log(f"  {it:2d} reach {reach * 1000:4.1f} mm | A {len(rA)} B {len(rB)} | mean |r| {ma:.3f} mm | |dc| {dcn:.3f} |c-c0| {np.linalg.norm(c - c0):.2f} max {np.abs(c - c0).max():.2f}"
            + (f" |e| {np.linalg.norm(e):.2f}" if expr else "") + f" scale {S[0]:.4f}")
        if (it > 12 and dcn < 0.01) or (pose_only and it > 10 and np.linalg.norm(dp) < 2e-5):
            break
    return {"c": c, "e": e if expr else None, "S": S, "samples": samp, "skin_v": skin_v, "hist": hist}


def evaluate(scan, c, e, S, skin_v, samp=None):
    """The region table of a GNM head (c, e) against the scan under S (two-sided, the scan's skin only)."""
    Vs = gt.apply(S, scan["V"])
    sc = gt.Surface(Vs, scan["F"])
    if samp is None:
        from scipy.spatial import cKDTree
        near = cKDTree(gt.verts(c)[gt.gnm()["fit"]]).query(Vs)[0] < 0.025
        cand = np.flatnonzero(near & skin_v)
        samp = cand[gt.voxel_sample(Vs[cand], 0.0015)]
    sn = gt.outward_sign(scan["V"], scan["F"]) * gt.vertex_normals(Vs, scan["F"])[samp]
    return gt.gaps(gt.verts(c, e), sc, skin=skin_v[scan["F"]].all(1), samples=Vs[samp], sample_skin=skin_v[samp], sample_normals=sn)


if __name__ == "__main__":
    tag = sys.argv[1]
    kw = dict(a.split("=") for a in sys.argv[2:])
    prior, expr = float(kw.get("prior", 1)), kw.get("expr", "0") == "1"
    scan = gt.load_scan(tag)
    free = kw.get("scale", "fixed") == "free"
    cmax = float(kw["cmax"]) if kw.get("cmax") else None
    name = kw.get("out") or (f"p{prior:g}" + ("e" if expr else "") + ("s" if free else "") + (f"b{cmax:g}" if cmax else ""))
    S0 = gt.load_sim(gt.WORK / tag / "S0.json")
    t = time.time()
    print(f"== {tag} fit_{name}: prior x{prior:g} expr {expr} scale {'free' if free else 'fixed'}")
    r = fit(scan, S0, prior=prior, expr=expr, scale_free=free, cmax=cmax,
            log=print if kw.get('v') == '1' else (lambda *a: None))
    g = evaluate(scan, r["c"], r["e"], r["S"], r["skin_v"])
    c0 = gt.class_mean(scan["info"]["sex"])
    import errmap
    meas = errmap.measures(r["c"])
    out = {"tag": tag, "name": name, "prior": prior, "expr": expr, "scale_free": free, "c": r["c"].tolist(), "e": None if r["e"] is None else r["e"].tolist(),
           "enames": gt.gnm()["enames"], "S": {"s": float(r["S"][0]), "R": np.asarray(r["S"][1]).tolist(), "t": np.asarray(r["S"][2]).tolist()},
           "table": g["table"], "c_off": float(np.linalg.norm(r["c"] - c0)), "c_max": float(np.abs(r["c"] - c0).max()), "measures": meas,
           "seconds": time.time() - t}
    (gt.WORK / tag / f"fit_{name}.json").write_text(json.dumps(out))
    np.save(gt.WORK / tag / "skin_v.npy", r["skin_v"])
    print(gt.table_text(g["table"], f"{tag} fit_{name}: |c - mean| {out['c_off']:.2f} (max {out['c_max']:.2f} sd); scale {r['S'][0]:.4f}; {time.time() - t:.0f} s"))
