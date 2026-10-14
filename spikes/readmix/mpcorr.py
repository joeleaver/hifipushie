"""mpcorr.py proj | learn: the one-time CORRESPONDENCE MediaPipe's 478 face-mesh points -> GNM's surface, learned
empirically on denselm's training renders (dressed GNM heads of sampled identity / expression / camera / light, every
vertex's pixel known): which GNM surface point (a triangle + barycentric weights) each MediaPipe point TRACKS, and its
bias and scatter by the head's turn.

  proj   per sample: GNM's vertices for its identity + expression, the stage's lip closing fitted on the stored lip
         landmarks, a similarity + thin-plate warp on the sample's 570 stored landmark positions (leave-out error
         printed), projected by the camera recovered from the same landmarks (DLT). -> corr/proj.npz {Q (S, C, 2) px,
         cand (C,) GNM ids, vis (S, C), mmpp (S,), yaw, pitch, Pm (S, 478, 2), bs (S, 52) blendshape scores, mix}
  learn  per MediaPipe point: the candidate vertex with the least robust mean distance over near-frontal samples,
         refined to a barycentric point in its best incident triangle; then the residual's bias (x, y mm in the picture)
         and scatter per yaw bin. -> corr/mp_gnm.json (copied to src/hifipushie/mp_gnm.json when accepted).
Needs corr/mp_data.npz (mpdet.py, MediaPipe's venv)."""
import json
import os
import sys
from pathlib import Path

import numpy as np

RM = Path(os.environ.get("HIFIPUSHIE_READMIX", "/mnt/data/hifipushie/readmix"))
DL = Path("/mnt/data/hifipushie/denselm")
YAW_BINS = (-90, -55, -35, -15, 15, 35, 55, 90)


def dlt(X, x):
    """3x4 projective camera from 3D-2D pairs (normalised DLT)."""
    mX, sX = X.mean(0), X.std()
    mx, sx = x.mean(0), x.std()
    Xn, xn = (X - mX) / sX, (x - mx) / sx
    Xh = np.c_[Xn, np.ones(len(X))]
    A = np.zeros((2 * len(X), 12))
    A[0::2, 0:4], A[0::2, 8:12] = Xh, -xn[:, :1] * Xh
    A[1::2, 4:8], A[1::2, 8:12] = Xh, -xn[:, 1:] * Xh
    P = np.linalg.svd(A, full_matrices=False)[2][-1].reshape(3, 4)
    Tx = np.array([[sx, 0, mx[0]], [0, sx, mx[1]], [0, 0, 1]])
    TX = np.eye(4)
    TX[:3, :3] /= sX
    TX[:3, 3] = -mX / sX
    return Tx @ P @ TX


def proj(P, X):
    h = np.c_[X, np.ones(len(X))] @ P.T
    return h[:, :2] / h[:, 2:3]


def umeyama(A, B):
    ma, mb = A.mean(0), B.mean(0)
    U, S, Vt = np.linalg.svd((B - mb).T @ (A - ma))
    d = np.sign(np.linalg.det(U @ Vt))
    R = U @ np.diag([1, 1, d]) @ Vt
    s = (S * [1, 1, d]).sum() / ((A - ma) ** 2).sum()
    return s, R, mb - s * R @ ma


def stage_proj():
    """Each sample's GNM vertices in the stage's world, from what is stored: GNM's own formula for its identity and
    expression (T + c IB + e EB), + the stage head's lip closing (base.lip_close_delta is a combination of the first 40
    lower-face expression components, re-solved per head: here those 40 are FITTED to the sample's stored lip / mouth /
    chin landmark positions), a similarity, and a thin-plate warp of what is left on the 570 stored landmarks (the eyes'
    local scaling, the neck). The leave-out error (fitted on every other landmark, tested on the rest) is printed.
    Only the gen2 sets (data_s1: GNM-NATIVE heads; gen.py's heads in data/ are body-carried, 1.5-3 mm off GNM's formula
    with a leave-out error of 1.5 mm). (TRIED: evaluating each head again through humanfit.state: 3 s a sample.)"""
    from scipy.interpolate import RBFInterpolator
    from hifipushie import base as basemod, denselm, face_ruler as fr, gnm_controls
    g = fr._gnm()
    sp_, gr = g["sp"], g["gr"]
    T, IB = sp_["T"], sp_["IB"]
    EB = gnm_controls.gnm()["EB"]
    gd = basemod._gnm_data()
    lower = [i for i, nm in enumerate(gd["expression_names"]) if str(nm).startswith("lower_face")][:40]
    Lm = denselm.landmarks()
    ns = int(Lm["n_skin"])
    lg = np.asarray(Lm["gnm"], int)[:ns]
    reg = np.asarray(Lm["region"])[:ns]
    mouth = np.isin(reg, ("lips", "mouth", "chin"))
    from hifipushie import humanmacro as hm
    face = gr["hockey_mask"].copy()
    face[np.asarray(hm.space()["sets"]["under_chin"], int)] = True
    cand = np.where(face & gr["skin_exterior"])[0]
    sub = np.unique(np.r_[cand, lg, g["F"].ravel()])          # the vertices evaluated (normals need the skin's triangles)
    pos = np.full(len(T), -1)
    pos[sub] = np.arange(len(sub))
    Ts, IBs, EBs = fr._world(T[sub]), fr._world(IB[:, sub]).astype(np.float64), fr._world(EB[:, sub]).astype(np.float64)
    BL = EBs[lower]                                            # (40, n, 3)
    lgs, cs, Fs = pos[lg], pos[cand], pos[g["F"]]
    print("candidates", len(cand), "of", len(T), "evaluated", len(sub), flush=True)
    D = np.load(RM / "corr" / "mp_data.npz")
    Pm_all, dirs, idxs, BS = D["P"], D["dir"], D["idx"], D["bs"]
    cap = int(os.environ.get("PROJ_CAP", "220"))
    out = {k: [] for k in ("Q", "vis", "mmpp", "yaw", "pitch", "roll", "Pm", "sid", "bs", "hold", "mix", "lipc")}

    def place(c, e, LMw, fit_idx):
        """the sample's vertices (sub) in the stage's world, fitted on the landmarks fit_idx."""
        V0 = Ts + np.tensordot(c, IBs, 1) + np.tensordot(e, EBs[:len(e)], 1)
        nm_ = fit_idx[~mouth[fit_idx]]
        s_, R_, t_ = umeyama(V0[lgs[nm_]], LMw[nm_])
        back = lambda X: (X - t_) @ R_ / s_                     # noqa: E731  (stage world -> GNM world)
        mi = fit_idx[mouth[fit_idx]]
        A = BL[:, lgs[mi]].reshape(len(lower), -1).T            # (3m, 40)
        r = (back(LMw[mi]) - V0[lgs[mi]]).ravel()
        cl = np.linalg.solve(A.T @ A + 1e-10 * np.eye(len(lower)), A.T @ r)
        V1 = V0 + np.tensordot(cl, BL, 1)
        s_, R_, t_ = umeyama(V1[lgs[fit_idx]], LMw[fit_idx])
        A1 = s_ * V1 @ R_.T + t_
        warp = RBFInterpolator(A1[lgs[fit_idx]], LMw[fit_idx] - A1[lgs[fit_idx]], kernel="thin_plate_spline", smoothing=1e-10)
        return A1, warp, float(np.linalg.norm(cl))
    for dname in sorted(set(dirs)):
        dd = DL / "data_s1" / dname
        if not (dd / "meta.npz").exists():
            continue
        me, lab = np.load(dd / "meta.npz"), np.load(dd / "labels.npz")
        sel = [j for j in np.where(dirs == dname)[0] if int(idxs[j]) < len(me["yaw"]) and np.isfinite(Pm_all[j, 0, 0]) and abs(me["yaw"][int(idxs[j])]) <= 90][:cap]
        nk, hold = 0, []
        for j in sel:
            i = int(idxs[j])
            c, e = me["identity"][i].astype(float), me["expression"][i].astype(float)
            LMw = me["LM"][i][:ns].astype(float)
            if nk % 25 == 0:        # the leave-out error: fitted on even landmarks, tested on odd
                A2, w2, _ = place(c, e, LMw, np.arange(0, ns, 2))
                odd = np.arange(1, ns, 2)
                er = np.linalg.norm(A2[lgs[odd]] + w2(A2[lgs[odd]]) - LMw[odd], axis=1) * 1000
                hold.append([np.sqrt((er ** 2).mean()), np.sqrt((er[np.isin(reg[odd], ("lips", "mouth"))] ** 2).mean()), np.sqrt((er[reg[odd] == "nose"] ** 2).mean()),
                             np.sqrt((er[np.isin(reg[odd], ("lids", "eyes"))] ** 2).mean())])
            A1, warp, cl = place(c, e, LMw, np.arange(ns))
            Xc = A1[cs] + warp(A1[cs])
            Pc = dlt(me["LM"][i].astype(float), lab["xy"][i].astype(float))
            dcam = np.asarray(me["cam_R"][i], float)[:, 2]            # from the head toward the camera
            Vall = A1.copy()
            Vall[cs] = Xc
            fn = np.cross(Vall[Fs[:, 1]] - Vall[Fs[:, 0]], Vall[Fs[:, 2]] - Vall[Fs[:, 0]])
            vn = np.zeros_like(Vall)
            for k in range(3):
                np.add.at(vn, Fs[:, k], fn)
            vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
            out["vis"].append((vn[cs] @ dcam).astype(np.float32))
            right = np.asarray(me["cam_R"][i], float)[:, 0]
            ctr = Xc.mean(0)
            out["mmpp"].append(1.0 / np.linalg.norm(proj(Pc, (ctr + 1e-3 * right)[None]) - proj(Pc, ctr[None])))
            out["Q"].append(proj(Pc, Xc).astype(np.float32))
            for k_ in ("yaw", "pitch", "roll"):
                out[k_].append(float(me[k_][i]))
            out["Pm"].append(Pm_all[j])
            out["bs"].append(BS[j])
            out["sid"].append(f"{dname}/{i:06d}")
            out["mix"].append(str(me["expr_mix"][i]))
            out["lipc"].append(cl)
            nk += 1
        out["hold"] += hold
        print(dname, nk, "kept; leave-out rms mm (all / lips+mouth / nose / lids+orbit)", np.round(np.mean(hold, 0), 3) if hold else None, flush=True)
    np.savez(RM / "corr" / "proj.npz", cand=cand, bs_names=D["bs_names"], **{k: np.array(v) for k, v in out.items()})
    h = np.array(out["hold"])
    print("samples", len(out["Q"]), "leave-out rms mm (all / lips+mouth / nose / lids+orbit): mean", np.round(h.mean(0), 3), "worst", np.round(h.max(0), 3))


# MediaPipe's named point sets (its canonical face mesh; the subject's left = picture right)
SETS = {
    "lip_outer": [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185],
    "lip_inner": [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191],
    "eye_l": [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466],
    "eye_r": [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246],
    "brow_l": [276, 283, 282, 295, 285, 300, 293, 334, 296, 336],
    "brow_r": [46, 53, 52, 65, 55, 70, 63, 105, 66, 107],
    "oval": [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150,
             136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109],
    "iris": list(range(468, 478)),
}


def huber_mean(d, k):
    return np.where(d < k, 0.5 * d * d, k * (d - 0.5 * k)).mean(0)


def stage_learn():
    from hifipushie import denselm, face_ruler as fr
    Z = np.load(RM / "corr" / "proj.npz")
    Q, cand, vis, mmpp, yaw, pitch, Pm = Z["Q"], Z["cand"], Z["vis"], Z["mmpp"], Z["yaw"], Z["pitch"], Z["Pm"]
    S, C = Q.shape[:2]
    g = fr._gnm()
    gr, T = g["gr"], fr._world(g["sp"]["T"])
    at = np.full(len(T), -1)
    at[cand] = np.arange(C)
    F = at[g["F"]]
    F = F[(F >= 0).all(1)]
    tris_of = [[] for _ in range(C)]
    for fi, f in enumerate(F):
        for v in f:
            tris_of[v].append(fi)
    Lm = denselm.landmarks()
    regs, dgr = {}, denselm._groups()[1]
    for name, groups in denselm.REGIONS:
        m = np.zeros(len(T), bool)
        for gname in groups:
            m |= np.asarray(dgr[gname])
        regs[name] = m
    # sanity of the whole chain: MediaPipe's 68-subset against the projected standard landmarks' vertices, frontal
    front = (np.abs(yaw) < 20) & (np.abs(pitch) < 15)
    print("samples", S, "frontal", int(front.sum()), "candidates", C, flush=True)
    mm = mmpp[:, None]
    pts, RES = [], {}
    setof = {i: k for k, v in SETS.items() for i in v}
    for m in range(478):
        if setof.get(m) == "iris":
            continue
        p = Pm[:, m]                                   # (S, 2)
        fs = np.where(front)[0]
        d = np.linalg.norm(Q[fs] - p[fs, None, :], axis=2) * mm[fs]        # (Sf, C) mm
        cost = huber_mean(d, 4.0)
        v0 = int(np.argmin(cost))
        best = (float(cost[v0]), (v0, v0, v0), (1.0, 0.0, 0.0))
        for fi in tris_of[v0]:                          # the barycentric point in each incident triangle (least squares, clipped)
            a, b, c = F[fi]
            A0, B0, C0 = Q[fs, a].astype(float), Q[fs, b].astype(float), Q[fs, c].astype(float)
            M = np.stack([(B0 - A0).ravel(), (C0 - A0).ravel()], 1)
            w = np.sqrt(np.repeat(1.0 / np.maximum(np.linalg.norm(p[fs] - (A0 + B0 + C0) / 3, axis=1) * mmpp[fs], 2.0), 2))
            uv = np.linalg.lstsq(M * w[:, None], (p[fs] - A0).ravel() * w, rcond=None)[0]
            uv = np.clip(uv, 0, 1)
            if uv.sum() > 1:
                uv = uv / uv.sum()
            ww = (1 - uv.sum(), uv[0], uv[1])
            r = np.linalg.norm(ww[0] * A0 + ww[1] * B0 + ww[2] * C0 - p[fs], axis=1) * mmpp[fs]
            cst = float(huber_mean(r[:, None], 4.0)[0])
            if cst < best[0]:
                best = (cst, (int(a), int(b), int(c)), tuple(float(x) for x in ww))
        tri, w3 = best[1], np.array(best[2])
        qb = sum(w3[k] * Q[:, tri[k]].astype(float) for k in range(3))
        r = (p - qb) * mm                               # (S, 2) mm, picture axes
        vz = sum(w3[k] * vis[:, tri[k]] for k in range(3))
        bins = {}
        for b0, b1 in zip(YAW_BINS[:-1], YAW_BINS[1:]):
            sel = (yaw >= b0) & (yaw < b1) & (np.abs(pitch) < 20)
            if sel.sum() < 15:
                continue
            rr = r[sel]
            med = np.median(rr, 0)
            sd = 1.4826 * np.median(np.abs(rr - med), 0)
            bins[f"{b0}:{b1}"] = {"n": int(sel.sum()), "bias": [round(float(x), 3) for x in med], "sd": [round(float(x), 3) for x in sd],
                                  "rms": round(float(np.sqrt(np.median((rr ** 2).sum(1)) / 2 * 1.4826 ** 2)), 3), "facing": round(float(np.median(vz[sel])), 3)}
        fp = (np.abs(yaw) < 15)
        pit = {}
        for nm, sel in (("up", fp & (pitch > 8)), ("down", fp & (pitch < -8))):
            if sel.sum() >= 15:
                pit[nm] = [round(float(x), 3) for x in np.median(r[sel], 0)]
        RES[m] = r
        gv = int(cand[tri[int(np.argmax(w3))]])
        region = next((n for n, mk in regs.items() if mk[gv]), "face_other")
        pts.append({"mp": m, "tri": [int(cand[t]) for t in tri], "w": [round(float(x), 5) for x in w3], "set": setof.get(m, ""), "region": region,
                    "x": round(float(sum(w3[k] * T[cand[tri[k]]][0] for k in range(3))), 5), "bins": bins, "pitch_bias": pit,
                    "cost": round(best[0], 4)})
        if m % 40 == 0:
            print(m, region, setof.get(m, ""), "front sd", bins.get("-15:15", {}).get("sd"), flush=True)
    # EFFECTIVE N: one network regresses the whole mesh, so its points err TOGETHER. The participation ratio of the residuals'
    # covariance over the near-frontal samples ((sum l)^2 / sum l^2 of its eigenvalues) = how many independent reads a group is
    neff = {}
    grp_ids = {"lips": SETS["lip_outer"] + SETS["lip_inner"], "eyes": SETS["eye_l"] + SETS["eye_r"], "brows": SETS["brow_l"] + SETS["brow_r"],
               "oval": SETS["oval"], "inner": [m for m in RES if setof.get(m) not in ("oval",)],
               "nose": [p["mp"] for p in pts if p["region"] == "nose"]}
    for gname, ids in grp_ids.items():
        M_ = np.concatenate([RES[m][front] for m in ids if m in RES], 1)
        M_ = np.clip(M_ - np.median(M_, 0), -6, 6)
        lam = np.linalg.svd(M_ - M_.mean(0), compute_uv=False) ** 2
        neff[gname] = {"reads": int(M_.shape[1]), "neff": round(float(lam.sum() ** 2 / (lam ** 2).sum()), 1)}
    print("effective N (participation ratio):", neff, flush=True)
    out = {"version": 1, "provenance": {
        "what": "MediaPipe Face Landmarker (478 points, Apache 2.0) -> GNM surface points (a GNM triangle's vertex ids + barycentric weights), learned on "
                "denselm's dressed synthetic renders: the point each MediaPipe landmark tracks, its bias / scatter (mm, picture x right / y down) by yaw bin "
                "(deg, + = the camera on the subject's left)", "samples": int(S), "frontal": int(front.sum()),
        "data": "denselm data_s1 (gen2: GNM-native dressed heads, 320 px renders; MediaPipe run at x2.4)", "script": "spikes/readmix/mpcorr.py", "date": "2026-10-13"},
        "yaw_bins": list(YAW_BINS), "neff": neff, "points": pts}
    (RM / "corr" / "mp_gnm.json").write_text(json.dumps(out))
    # summary by set / region
    print("\n| group | n | frontal sd mm (median over points) | worst | 15-35 deg rms | 35-55 deg rms |")
    grp = {}
    for pt in pts:
        grp.setdefault(pt["set"] or pt["region"], []).append(pt)
    for k, v in sorted(grp.items()):
        f0 = [np.hypot(*p["bins"]["-15:15"]["sd"]) / np.sqrt(2) for p in v if "-15:15" in p["bins"]]
        t1 = [np.mean([p["bins"][b]["rms"] for b in ("-35:-15", "15:35") if b in p["bins"]]) for p in v]
        t2 = [np.mean([p["bins"][b]["rms"] for b in ("-55:-35", "35:55") if b in p["bins"]]) for p in v]
        print(f"| {k} | {len(v)} | {np.median(f0):.2f} | {np.max(f0):.2f} | {np.nanmedian(t1):.2f} | {np.nanmedian(t2):.2f} |")




def stage_expr():
    """The detector's BLENDSHAPE SCORES against the expression each render really carries (gen2's ARKit-named weights):
    per shape the score's level on pictures WITHOUT it (the null: what a neutral face reads), the fit true = a * score + b
    on pictures with it, and the residual. -> corr/mp_expr.json (the calibration of face_ruler's expression evidence)."""
    Z = np.load(RM / "corr" / "proj.npz")
    yaw, pitch, bs, names = Z["yaw"], Z["pitch"], Z["bs"], [str(x) for x in Z["bs_names"]]
    mix = [json.loads(str(m)) for m in Z["mix"]]
    out = {}
    print("| shape (both sides' mean) | n with | score on pictures WITHOUT it: median / p90 / p98 | true = a * score + b | residual sd | corr |")
    print("|---|---|---|---|---|---|")
    for sh in ("mouthSmile", "eyeSquint", "mouthFrown", "browDown", "eyeBlink", "eyeWide", "mouthPress", "mouthUpperUp", "mouthLowerDown", "jawOpen", "mouthPucker", "browInnerUp"):
        pair = [n for n in names if n in (sh, sh + "Left", sh + "Right")]
        if not pair:
            continue
        sc = bs[:, [names.index(n) for n in pair]].mean(1)
        tr = np.array([np.mean([m.get(n, 0.0) for n in pair]) for m in mix])
        other = np.array([bool(m) for m in mix])
        for nm, sel in (("front", (np.abs(yaw) < 20) & (np.abs(pitch) < 20)), ("3q", (np.abs(yaw) >= 20) & (np.abs(yaw) < 50))):
            null = sel & (tr == 0)
            neut = sel & ~other
            has = sel & (tr > 0.05)
            if has.sum() < 8:
                continue
            A = np.c_[sc[has | neut], np.ones((has | neut).sum())]
            co = np.linalg.lstsq(A, tr[has | neut], rcond=None)[0]
            res = tr[has | neut] - A @ co
            out[f"{sh}:{nm}"] = {"n": int(has.sum()), "null": [float(np.median(sc[null])), float(np.percentile(sc[null], 90)), float(np.percentile(sc[null], 98))],
                                 "neutral": [float(np.median(sc[neut])), float(np.percentile(sc[neut], 90))], "a": float(co[0]), "b": float(co[1]),
                                 "sd": float(res.std()), "corr": float(np.corrcoef(sc[has | neut], tr[has | neut])[0, 1])}
            o = out[f"{sh}:{nm}"]
            print(f"| {sh} ({nm}) | {o['n']} | {o['null'][0]:.3f} / {o['null'][1]:.3f} / {o['null'][2]:.3f} | {o['a']:.2f} x + {o['b']:+.3f} | {o['sd']:.3f} | {o['corr']:.2f} |")
    (RM / "corr" / "mp_expr.json").write_text(json.dumps(out))


if __name__ == "__main__":
    {"proj": stage_proj, "learn": stage_learn, "expr": stage_expr}[sys.argv[1]]()
