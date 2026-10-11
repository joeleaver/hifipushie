"""lidsolve.py <src model> <donor model> <dst el_*> [key=value ...]: the WHOLE upper lid as one structure, solved in
GNM's identity in ONE linear step, on GNM's own vertex rings (lidmap).
Target = the donor's lid (default gk_s376: margin roll, a platform lying on the ball, the tuck at GNM's crease rings,
the drape over it) re-proportioned to the source person: each donor lid vertex (rings 1..RT, upper half) keeps its
STAND-OFF from the ball and its place across the lid; its height over the margin is stretched below the donor's
crease so the crease lands at the person's fold height (hc, mm at the model per column; default the eye ruler's fold
line) and shifted above it (the fold and drape unchanged, lifted). Ring 0 (the margin: the eye ruler's numbers) and
everything else on the head are HELD at the source.
  min |W_t (V(c) - target)|^2 + |W_h (V(c) - V(c0))|^2 + lam |c - c0|^2      (V linear in c: exact, no iterations)
keys: sharp=<mm> (the skin above the crease this much further forward than the donor's, the crease 0.3 x deeper);
margins=<identity source> (ring 0 of both lids put where that head has them in its eye frame; default held at the source);
hc=4.7 (mm at the model, one number) | hc=ruler; rt=8 (last target ring); sig=0.1 (mm, target); hold=0.3 (mm);
lam=1 (|dc| prior); hold=<mm>[,<mm>..] (each solved, the last written); tw=0.25 (weight along the surface); scale=<world mm per
raw mm> (default measured from the source's head)."""
import copy
import json
import os
import shutil
import sys

import numpy as np
from scipy.spatial import cKDTree

import lidmap as lm
from hifipushie import blockin as bi, gnm_controls as gc, onemesh, store

g = gc.gnm()
t = lm.topo()
NC = 170


def mirror_map():
    T = g["T"]
    return cKDTree(T).query(T * [-1, 1, 1])[1]


MIR = mirror_map()


def reflect(V):
    return (V * [-1, 1, 1])[MIR]


def upper_ids(k):
    ids = t["loops"][k]
    return ids[g["T"][ids, 1] > g["J"][2][1] + 0.0005]


def lid_frame(V, ctr, r):
    """Per ring k: (ids, u, v, s) of the upper half in the eye frame."""
    out = {}
    for k in range(0, lm.NR + 1):
        ids = upper_ids(k)
        P = V[ids] - ctr
        o = np.argsort(P[:, 0])
        ids, P = ids[o], P[o]
        out[k] = (ids, P[:, 0], P[:, 1], np.linalg.norm(P, axis=1) - r)
    return out


def crease_of(F, U):
    """Per column u: the donor's crease height over its margin (the lowest stand-off among rings 3..8) and ring."""
    hc = []
    for u in U:
        col = []
        for k in range(0, 10):
            ids, uu, vv, ss = F[k]
            if u < uu[0] or u > uu[-1]:
                col.append((np.nan, np.nan))
                continue
            col.append((float(np.interp(u, uu, vv)), float(np.interp(u, uu, ss))))
        col = np.array(col)
        k = 3 + int(np.nanargmin(col[3:9, 1]))
        hc.append(col[k, 0] - col[0, 0])
    return np.array(hc)


def design(Vd, cd, Vs, cs, r, hc_person, rt, sharp=0.0):
    """Targets for the LEFT eye: {vertex id: target xyz (raw GNM mm)} for rings 1..rt, from the donor's lid Vd (eye
    centre cd) onto the source's eye (Vs, cs). hc_person(f) = the person's fold height over the margin (raw mm) at the
    fraction f across the margin (0 inner .. 1 outer)."""
    Fd, Fs = lid_frame(Vd, cd, r), lid_frame(Vs, cs, r)
    ad, bd = Fd[0][1][0], Fd[0][1][-1]
    as_, bs = Fs[0][1][0], Fs[0][1][-1]
    Ud = np.linspace(ad + 0.3, bd - 0.3, 61)
    hcd = crease_of(Fd, Ud)
    k5 = np.ones(7) / 7
    hcd = np.convolve(np.pad(hcd, 3, mode="edge"), k5, mode="valid")
    out, info = {}, []
    for k in range(1, rt + 1):
        ids, u, v, s = Fd[k]
        f = (u - ad) / (bd - ad)
        ok = (f > 0.02) & (f < 0.98)
        md = np.interp(u, Fd[0][1], Fd[0][2])               # the donor's margin under this vertex
        sd0 = np.interp(u, Fd[0][1], Fd[0][3])
        h = v - md
        hd = np.interp(u, Ud, hcd)
        us = as_ + f * (bs - as_)
        ms = np.interp(us, Fs[0][1], Fs[0][2])
        ss0 = np.interp(us, Fs[0][1], Fs[0][3])
        H = hc_person(f)
        h2 = np.where(h <= hd, h * H / np.maximum(hd, 0.3), H + (h - hd))
        s2 = s + (ss0 - sd0) * np.exp(-np.maximum(h2, 0) / 1.5)
        if sharp:   # a sharper tuck than the donor's: the skin above the crease further forward (fading over 2.5 mm),
            # the crease itself a little deeper
            s2 = s2 + np.where(h > hd + 0.15, sharp * np.exp(-np.maximum(h - hd, 0) / 2.5), 0.0) - 0.3 * sharp * np.exp(-((h - hd) / 0.35) ** 2)
        v2 = ms + h2
        w2 = np.sqrt(np.maximum((r + s2) ** 2 - us ** 2 - v2 ** 2, 0.0))
        # the corners fade to the source's own lid (the structure merges into the canthi there)
        wt = np.clip((f - 0.02) / 0.13, 0, 1) * np.clip((0.98 - f) / 0.13, 0, 1)
        for i, vid in enumerate(ids):
            if ok[i]:
                out[int(vid)] = (np.array([us[i], v2[i], w2[i]]) + cs, float(wt[i]))
        info.append((k, float(np.nanmedian(h)), float(np.nanmedian(h2))))
    return out, info


def main():
    src, donor, dst = sys.argv[1:4]
    kw = dict(a.split("=", 1) for a in sys.argv[4:])
    assert dst.startswith("el_"), "scratch models are el_*"
    rt, sig, lam = int(kw.get("rt", 8)), float(kw.get("sig", 0.1)), float(kw.get("lam", 1.0))
    sp = copy.deepcopy(store.load(src))
    c0 = bi.identity(sp)
    cdn = bi.identity(store.load(donor))
    assert not sp["base"]["head"].get("expression"), "the source carries an eye expression: clear it first"
    Vs, Vd = gc.vertices(c0) * 1000, gc.vertices(cdn) * 1000
    cs, r = lm.eye_frame_raw(c0)
    cd, _ = lm.eye_frame_raw(cdn)
    # world mm per raw mm round the eye (the head's scale x the body's hook x eyes)
    if "scale" in kw:
        sc = float(kw["scale"])
    else:
        ht = onemesh.head_template(sp["base"])
        sk = lm.skin_ids()
        loc = -np.ones(len(g["T"]), int)
        loc[sk] = np.arange(len(sk))
        ids = np.concatenate([upper_ids(k) for k in range(0, 9)])
        A, B = Vs[ids], np.asarray(ht["verts"], float)[loc[ids]] * 1000
        sc = float(np.sqrt(((B - B.mean(0)) ** 2).sum() / ((A - A.mean(0)) ** 2).sum()))
    hc = kw.get("hc", "ruler")
    if hc == "ruler":
        from hifipushie import blockin_eyes as be
        rv = be.ruler_evidence(src)
        cr = np.asarray(rv["crease"], float)
        okc = np.isfinite(cr)
        inner, outer = rv["inner"][0], rv["outer"][0]
        fcol = (be.RULER_COLS[okc] - inner) / (outer - inner)
        print("ruler fold line over the margin (mm at the model) at u", be.RULER_COLS[okc].tolist(), "->", np.round(cr[okc], 2).tolist())
        hc_person = lambda f: np.interp(f, fcol, cr[okc]) / sc   # noqa: E731
    else:
        hc_person = lambda f: np.full(np.shape(f), float(hc) / sc)   # noqa: E731
    print(f"world / raw scale at the lid {sc:.4f}; GNM ball r {r:.2f}")
    tgt = {}
    tl, info = design(Vd, cd, Vs, cs, r, hc_person, rt, float(kw.get('sharp', 0)))
    tgt.update(tl)
    # the right eye: the same design on the reflected heads, reflected back
    cs_r, cd_r = lm.eye_frame_raw(c0)[0], None
    Vs_m, Vd_m = reflect(Vs), reflect(Vd)
    gR = g["groups"]["right_eye"] & g["groups"]["scleras"]

    def ball(V, m):
        P = V[m]
        A = np.c_[2 * P, np.ones(len(P))]
        sol = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
        return sol[:3]
    cs_r = ball(Vs, gR) * [-1, 1, 1]
    cd_r = ball(Vd, gR) * [-1, 1, 1]
    tr, _ = design(Vd_m, cd_r, Vs_m, cs_r, r, hc_person, rt, float(kw.get('sharp', 0)))
    for vid, (p, w) in tr.items():
        tgt[int(MIR[vid])] = (p * [-1, 1, 1], w)
    if kw.get("margins"):   # the lid margins (ring 0, both lids, both eyes) put where ANOTHER model has them in its eye frame
        import lidstruct
        cm = lidstruct.ident(kw["margins"])
        Vm = gc.vertices(cm) * 1000
        r0 = t["loops"][0]
        for ids0, grp in ((r0, "left_eye"), (MIR[r0], "right_eye")):
            m = g["groups"][grp] & g["groups"]["scleras"]
            cm_, cs_ = ball(Vm, m), ball(Vs, m)
            for vid in ids0:
                tgt[int(vid)] = (Vm[vid] - cm_ + cs_, 2.0)
    print("rings: donor median height over its margin -> target", " ".join(f"{k}:{a:.2f}->{b:.2f}" for k, a, b in info))
    ids = np.array(sorted(tgt))
    P = np.array([tgt[i][0] for i in ids])
    wt = np.array([tgt[i][1] for i in ids])
    IB = g["IB"][:NC] * 1000.0                      # (NC, V, 3) mm per unit
    # holds: every skin vertex not targeted + the eyeballs, at the source
    hm = (g["groups"]["skin_exterior"] | g["groups"]["eyes"]).copy()
    hm[ids] = False
    hid = np.flatnonzero(hm)
    tw = float(kw.get("tw", 0.25))   # weight of a target miss ALONG the surface (a vertex sliding in the skin is not a shape error)
    full = (wt > 0.99) & (wt < 1.5)
    m0 = (np.abs(t["ring"][hid]) <= 0) | (np.abs(t["ring"][MIR[hid]]) <= 0)     # the lid margins, both lids, both eyes
    D0 = P - Vs[ids]
    IBt = IB[:, ids].astype(np.float64)
    rk = t["ring"][ids]
    dc = np.zeros(NC)
    for hold in [float(x) for x in str(kw.get("hold", "0.3")).split(",")]:
        hw = np.where(m0, 1.0 / float(kw.get("mh", 0.05)), 1.0 / hold)
        Ah = (IB[:, hid] * hw[None, :, None]).reshape(NC, -1).T.astype(np.float64)
        AhA = Ah.T @ Ah
        dc = np.zeros(NC)
        for _ in range(3):
            Nn = gc.normals(gc.vertices(c0 + dc))[ids]          # the surface's normals (first round: the source's)
            M = tw * np.eye(3)[None] + (1 - tw) * Nn[:, :, None] * Nn[:, None, :]
            At = (np.einsum("vij,cvj->cvi", M, IBt) * (wt / sig)[None, :, None]).reshape(NC, -1).T
            bt = (np.einsum("vij,vj->vi", M, D0) * (wt / sig)[:, None]).ravel()
            dc = np.linalg.solve(At.T @ At + AhA + lam * np.eye(NC), At.T @ bt)
        res = D0 - np.tensordot(dc, IBt, 1)
        rn = (res * Nn).sum(1)
        mv = np.tensordot(dc, IB[:, hid], 1)
        print(f"SOLVE hold {hold}: target miss rms {np.sqrt((res[full] ** 2).sum(1).mean()):.3f} mm, along the normal {np.sqrt((rn[full] ** 2).mean()):.3f} "
              f"(start {np.sqrt((D0[full] ** 2).sum(1).mean()):.3f}); |dc| {np.linalg.norm(dc):.2f}; |c| {np.linalg.norm(c0):.2f} -> {np.linalg.norm(c0 + dc):.2f}; "
              f"held moved rms {np.sqrt((mv ** 2).sum(1).mean()):.3f} mm, max {np.linalg.norm(mv, axis=1).max():.2f}; margins moved rms {np.sqrt((mv[m0] ** 2).sum(1).mean()):.3f}")
        print("   normal miss per ring (rms mm):", " ".join(f"{k}:{np.sqrt((rn[(rk == k) & full] ** 2).mean()):.2f}" for k in range(1, rt + 1)))
    c1 = c0 + dc
    V1 = gc.vertices(c1) * 1000
    for lab, V, cc in (("source", Vs, c0), ("donor", Vd, cdn), ("result", V1, c1)):
        ctr, _ = lm.eye_frame_raw(cc)
        col = {k: (v, w) for k, v, w in lm.column(V, ctr, 0.0)}
        print(f"   {lab:7s} pupil column, stand-off rings 0..10:", " ".join(f"{np.hypot(*col[k]) - r:5.2f}" for k in range(0, 11)), "| v:", " ".join(f"{col[k][0]:5.2f}" for k in range(0, 11)))
    bi.set_identity(sp, c1)
    sp.pop("hair", None)
    d = store._dir(dst)
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.json").write_text(json.dumps(sp))
    shutil.copy(store._dir(src) / "human_refs.json", d / "human_refs.json")
    np.savez(os.environ["G"] + f"/out/lidsolve_{dst}.npz", c0=c0, c1=c1, ids=ids, P=P, wt=wt)
    print("wrote", dst)


if __name__ == "__main__":
    main()
