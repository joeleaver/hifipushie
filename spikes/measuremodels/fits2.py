"""The method table with dense models and generated meshes as evidence.   run.sh fits2.py [prefix ...]"""
import sys

import numpy as np

import dense
import fitlib
import fits
import mm
import rs
import tmesh

sys.path.insert(0, str(mm.MM))
FT = ["front", "tq"]


def stack(*rr):
    rr = [r for r in rr if r is not None and len(r[1])]
    if not rr:
        return None
    return np.vstack([r[0] for r in rr]), np.concatenate([r[1] for r in rr])


def read_rows(s):
    import exp2
    from hifipushie import humanmacro as hm
    return hm.prior_rows(exp2.reader(fits.truth(s)))


def dense_fit(s, views, model, use=("z", "n"), rounds=3, extra=None, infl=2.0, regions=None, tab="skin", cut=0.9):
    ev = fits.evs(s, views, tab=tab)
    vs = [v for v in views if fits.ev478(f"{s}_{v}", tab=tab) is not None]
    f = fitlib.fit(ev, robust=True, rows=extra)
    for _ in range(rounds):
        rr = []
        for v, cam in zip(vs, f["cams"]):
            iid = f"{s}_{v}"
            it = mm.item(iid)
            pr = mm.pred(model, iid)
            rr.append(dense.rows(model, pr, f["c"], cam, v, hair=it["hair"] if it["look"]["hair"] else None, use=use, infl=infl, regions=regions, cut=cut))
        f = fitlib.fit(ev, robust=True, rows=stack(extra, *rr), c_init=f["c"])
    return f


def feat_fit(s, views, model, rounds=3, extra=None, normals=False, infl=1.3):
    ev = fits.evs(s, views)
    vs = [v for v in views if fits.ev478(f"{s}_{v}") is not None]
    f = fitlib.fit(ev, robust=True, rows=extra)
    for _ in range(rounds):
        rr = []
        for v, cam in zip(vs, f["cams"]):
            iid = f"{s}_{v}"
            it = mm.item(iid)
            hair = it["hair"] if it["look"]["hair"] else None
            rr.append(dense.rows_feat(model, mm.pred(model, iid), f["c"], cam, v, hair=hair, infl=infl))
            if normals:
                rr.append(dense.rows(model, mm.pred(model, iid), f["c"], cam, v, hair=hair, use=("n",), infl=4.0))
        f = fitlib.fit(ev, robust=True, rows=stack(extra, *rr), c_init=f["c"])
    return f


def methods(model):
    return {
        f"E1 {model} feature depths, front+tq": lambda s: feat_fit(s, FT, model),
        f"E1f {model} feature depths, front only": lambda s: feat_fit(s, ["front"], model),
        f"E2 {model} feature depths + normals x4, front+tq": lambda s: feat_fit(s, FT, model, normals=True),
        f"E3 {model} feature depths + read, front+tq": lambda s: feat_fit(s, FT, model, extra=read_rows(s)),
        f"N1 {model} normals x4, front only": lambda s: dense_fit(s, ["front"], model, use=("n",), infl=4.0),
        f"N2 {model} normals x6, front+tq": lambda s: dense_fit(s, FT, model, use=("n",), infl=6.0),
        f"N3 {model} normals x3, front+tq": lambda s: dense_fit(s, FT, model, use=("n",), infl=3.0),
        f"N4 {model} normals x4 + read, front+tq": lambda s: dense_fit(s, FT, model, use=("n",), infl=4.0, extra=read_rows(s)),
        f"N5 {model} normals x4 + read, front only": lambda s: dense_fit(s, ["front"], model, use=("n",), infl=4.0, extra=read_rows(s)),
        f"N6 {model} normals x4, front+tq+tq2": lambda s: dense_fit(s, FT + ["tq2"], model, use=("n",), infl=4.0),
        f"N7 {model} normals x4, all vertices (cut 2)": lambda s: dense_fit(s, FT, model, use=("n",), infl=4.0, cut=2.0),
        f"D1b {model} normals sigma x4, front+tq": lambda s: dense_fit(s, FT, model, use=("n",), infl=4.0),
        f"D1 {model} normals, front+tq": lambda s: dense_fit(s, FT, model, use=("n",)),
        f"D2 {model} depth, front+tq": lambda s: dense_fit(s, FT, model, use=("z",)),
        f"D3 {model} depth + normals, front+tq": lambda s: dense_fit(s, FT, model),
        f"D3f {model} depth + normals, front only": lambda s: dense_fit(s, ["front"], model),
        f"D4 {model} depth + normals, sigma x1": lambda s: dense_fit(s, FT, model, infl=1.0),
        f"D5 {model} depth + normals, sigma x4": lambda s: dense_fit(s, FT, model, infl=4.0),
        f"D6 {model} depth + normals + read, front+tq": lambda s: dense_fit(s, FT, model, extra=read_rows(s)),
    }


# ---- generated meshes (TRELLIS.2) ------------------------------------------------------------------------------------
SIG = {"face": 2.2, "nose": 3.0, "chin": 3.0, "lips": 2.0, "eyes": 1.6, "brow": 2.3, "cheeks": 2.1, "forehead": 1.5, "jaw": 2.8,
       "ears": 4.1, "cranium": 5.9, "neck": 6.8}      # mm rms of the meshes' surface offset from truth, by region (score_mesh)
GAIN = {"nose": 0.49, "chin": 0.26, "lips": 0.51, "eyes": 0.46, "brow": 0.47, "cheeks": 0.62, "forehead": 0.71, "jaw": 0.73, "cranium": 0.75,
        "neck": 0.70, "ears": 0.6}     # truth's deviation from the mean ~ gain x the mesh's (score_mesh, the same heads: in-sample)
LEFT = {"nose": 1.85, "chin": 2.7, "lips": 1.6, "eyes": 1.1, "brow": 1.6, "cheeks": 1.4, "forehead": 1.3, "jaw": 1.75, "cranium": 5.3, "neck": 5.2, "ears": 3.2}
_M = {}


def gain_fit(s, lm_views, mesh_views, infl=2.0, extra=None, rounds=20, regions=None, face_align=True, normals=None):
    ev = fits.evs(s, lm_views)
    vs = [v for v in lm_views if fits.ev478(f"{s}_{v}") is not None]
    idx, _ = mesh_idx(s, regions)
    reg, _ = mm.region_of()
    gq = np.array([GAIN[r] for r in reg[idx]])
    sg = np.array([LEFT[r] for r in reg[idx]]) * infl
    meshes = []
    for v in mesh_views:
        k = f"{s}_{v}"
        if not (tmesh.TR / f"{k}.npz").exists():
            return None
        _M.setdefault(k, tmesh.Mesh(k))
        meshes.append(_M[k])
    f = fitlib.fit(ev, robust=True, rows=extra)
    for me in meshes:
        tmesh.align(me, rs.head(f["c"]))
    for _ in range(rounds):
        rr = [tmesh.rows(me, f["c"], idx, sg, gain=gq, face_align=face_align) for me in meshes]
        if normals:
            for v, cam in zip(vs, f["cams"]):
                it = mm.item(f"{s}_{v}")
                rr.append(dense.rows(normals, mm.pred(normals, f"{s}_{v}"), f["c"], cam, v, hair=it["hair"] if it["look"]["hair"] else None, use=("n",), infl=4.0))
        f = fitlib.fit(ev, robust=True, rows=stack(extra, *rr), c_init=f["c"])
    return f


def mesh_idx(s, regions=None, step=5):
    g = rs.gnm()
    reg, _ = mm.region_of()
    ok = g["ext"] & (reg != "") & (reg != "ears")      # nearest-point pairs on ears are garbage
    if regions:
        ok &= np.isin(reg, regions)
    if mm.item(f"{s}_front")["look"]["hair"]:
        ok &= reg != "cranium"            # under the hair stand-in the picture showed no skull
    idx = np.flatnonzero(ok)[::step]
    return idx, np.array([SIG[r] for r in reg[idx]])


def mesh_fit(s, lm_views, mesh_views, regions=None, infl=2.0, extra=None, rounds=20, step=5, sig_scale=None):
    ev = fits.evs(s, lm_views) if lm_views else []
    idx, sg = mesh_idx(s, regions, step)
    if sig_scale:
        reg, _ = mm.region_of()
        sg = sg * np.array([sig_scale.get(r, 1.0) for r in reg[idx]])
    meshes = []
    for v in mesh_views:
        k = f"{s}_{v}"
        if not (tmesh.TR / f"{k}.npz").exists():
            return None
        if k not in _M:
            _M[k] = tmesh.Mesh(k)
        meshes.append(_M[k])
    if ev:
        f = fitlib.fit(ev, robust=True, rows=extra)
    else:
        f = {"c": np.zeros(rs.K_FIT)}
        if extra is not None:
            f["c"] = np.linalg.solve(extra[0].T @ extra[0] + np.eye(rs.K_FIT), extra[0].T @ extra[1])
    for me in meshes:
        tmesh.align(me, rs.head(f["c"]))        # from scratch: the mesh's yaw and scale are not known
    for _ in range(rounds):
        rr = [tmesh.rows(me, f["c"], idx, sg * infl) for me in meshes]
        R = stack(extra, *rr)
        if ev:
            f = fitlib.fit(ev, robust=True, rows=R, c_init=f["c"])
        else:
            f = {"c": np.linalg.solve(R[0].T @ R[0] + np.eye(rs.K_FIT), R[0].T @ R[1])}
    return f


def normals_rows_fn(model="david", infl=4.0):
    return lambda s, views: None


def stack_fit(s, lm_views, mesh_views, normals="david", read=False, infl=2.0, regions=None, rounds=20):
    """Detector points + calibrated normals + generated mesh (+ read)."""
    ev = fits.evs(s, lm_views)
    vs = [v for v in lm_views if fits.ev478(f"{s}_{v}") is not None]
    extra = read_rows(s) if read else None
    idx, sg = mesh_idx(s, regions)
    meshes = []
    for v in mesh_views:
        k = f"{s}_{v}"
        if not (tmesh.TR / f"{k}.npz").exists():
            return None
        _M.setdefault(k, tmesh.Mesh(k))
        meshes.append(_M[k])
    f = fitlib.fit(ev, robust=True, rows=extra)
    for me in meshes:
        tmesh.align(me, rs.head(f["c"]))
    for _ in range(rounds):
        rr = [tmesh.rows(me, f["c"], idx, sg * infl) for me in meshes]
        if normals:
            for v, cam in zip(vs, f["cams"]):
                it = mm.item(f"{s}_{v}")
                rr.append(dense.rows(normals, mm.pred(normals, f"{s}_{v}"), f["c"], cam, v, hair=it["hair"] if it["look"]["hair"] else None, use=("n",), infl=4.0))
        f = fitlib.fit(ev, robust=True, rows=stack(extra, *rr), c_init=f["c"])
    return f


HIDDEN = ["jaw", "cranium", "ears", "neck"]
MESH = {
    "T0 mesh(front) ALONE, no landmarks": lambda s: mesh_fit(s, [], ["front"]),
    "T1 front lm + mesh(front), all regions": lambda s: mesh_fit(s, ["front"], ["front"]),
    "T1a   same, sigma x1": lambda s: mesh_fit(s, ["front"], ["front"], infl=1.0),
    "G1 front lm + mesh(front) with gains": lambda s: gain_fit(s, ["front"], ["front"]),
    "G2 front lm + mesh(front) with gains, sigma x1": lambda s: gain_fit(s, ["front"], ["front"], infl=1.0),
    "G3 front lm + mesh(front) gains, hidden regions only": lambda s: gain_fit(s, ["front"], ["front"], regions=HIDDEN),
    "G4 front+tq lm + normals + mesh(front) gains + read": lambda s: gain_fit(s, FT, ["front"], normals="david", extra=read_rows(s)),
    "G5 front+tq lm + normals + mesh(front) gains": lambda s: gain_fit(s, FT, ["front"], normals="david"),
    "G7 front+tq lm + mesh(tq) with gains": lambda s: gain_fit(s, FT, ["tq"]),
    "G6 front+tq lm + mesh(front) + mesh(tq) gains": lambda s: gain_fit(s, FT, ["front", "tq"]),
    "T1c   same, sigma x0.5": lambda s: mesh_fit(s, ["front"], ["front"], infl=0.5),
    "T1b   same, sigma x4": lambda s: mesh_fit(s, ["front"], ["front"], infl=4.0),
    "T2 front lm + mesh(front), hidden regions only": lambda s: mesh_fit(s, ["front"], ["front"], regions=HIDDEN),
    "T3 front+tq lm + mesh(front)": lambda s: mesh_fit(s, FT, ["front"]),
    "T4 front+tq lm + mesh(front) + mesh(tq)": lambda s: mesh_fit(s, FT, ["front", "tq"]),
    "T5 front+tq lm + mesh(tq)": lambda s: mesh_fit(s, FT, ["tq"]),
    "T6 front lm + mesh(front) + read": lambda s: mesh_fit(s, ["front"], ["front"], extra=read_rows(s)),
    "T7 front+tq lm + david normals + mesh(front)": lambda s: stack_fit(s, FT, ["front"]),
    "T8 front+tq lm + david normals + mesh(front) + read": lambda s: stack_fit(s, FT, ["front"], read=True),
    "T9 front+tq lm + normals + mesh(front) + mesh(tq) + read": lambda s: stack_fit(s, FT, ["front", "tq"], read=True),
    "T10 front lm + david normals + mesh(front) + read": lambda s: stack_fit(s, ["front"], ["front"], read=True),
}

if __name__ == "__main__" and sys.argv[1] == "mesh":
    fits.run(MESH, sys.argv[2:], out="fits")


BASE2 = {
    "R1 mp478 skin + read, front+tq": lambda s: fitlib.fit(fits.evs(s, FT), robust=True, rows=read_rows(s)),
    "R1f mp478 skin + read, front only": lambda s: fitlib.fit(fits.evs(s, ["front"]), robust=True, rows=read_rows(s)),
}

if __name__ == "__main__" and sys.argv[1] != "mesh":
    model = sys.argv[1]
    M = dict(BASE2)
    M.update(methods(model))
    res = fits.run(M, sys.argv[2:], out="fits")




# ---- the generated mesh read at FEATURES (a few numbers, gains from the OTHER heads) ---------------------------------
def _feat_cal(view, leave):
    import json
    import score_mesh
    key = ("fc", view, leave)
    if key not in _M:
        F = json.loads((mm.MM / "out" / "mesh_feats.json").read_text())
        out = {}
        names = [n for n in F if n.endswith("_" + view) and not n.startswith(leave)]
        for k in list(score_mesh.FEATS) + ["under-chin", "neck side", "crown", "occiput"]:
            ab = np.array([F[n][k] for n in names if k in F[n]])
            if len(ab) < 5:
                continue
            dm, dt = ab[:, 0] - ab[:, 1], -ab[:, 1]
            gq = float((dm @ dt) / max(dm @ dm, 1e-9))
            out[k] = (gq, float(np.sqrt(((dt - gq * dm) ** 2).mean())), float(np.sqrt((dt ** 2).mean())))
        _M[key] = out
    return _M[key]


def mesh_feat_rows(me, c, view, leave, K=rs.K_FIT, infl=1.3, cut=0.85):
    import score_mesh
    g = rs.gnm()
    H = rs.head(c)
    tmesh.align(me, H, T0=me.T)
    cal = _feat_cal(view, leave)
    A, y = [], []
    for k, idx in score_mesh.feature_sets(H).items():
        if k not in cal or len(idx) < 4:
            continue
        gq, left, pop = cal[k]
        if left > cut * pop or gq < 0.1:
            continue
        a, ok, q, nq = tmesh.offsets(me, H, idx)
        if ok.sum() < 4:
            continue
        i = idx[ok]
        tgt = g["V0"][i] + gq * (q[ok] - g["V0"][i])
        Ak = np.einsum("nd,knd->k", nq[ok], g["IB"][:K, i].astype(float)) / len(i)
        yk = float((nq[ok] * (tgt - g["V0"][i])).sum(1).mean())
        sg = left * infl / 1000.0
        A.append(Ak / sg)
        y.append(yk / sg)
    return (np.array(A), np.array(y)) if A else (np.zeros((0, K)), np.zeros(0))


def featmesh_fit(s, lm_views, mesh_views, normals=None, read=False, rounds=6, infl=1.3):
    ev = fits.evs(s, lm_views)
    vs = [v for v in lm_views if fits.ev478(f"{s}_{v}") is not None]
    extra = read_rows(s) if read else None
    meshes = []
    for v in mesh_views:
        k = f"{s}_{v}"
        if not (tmesh.TR / f"{k}.npz").exists():
            return None
        _M.setdefault(k, tmesh.Mesh(k))
        meshes.append((_M[k], v))
    f = fitlib.fit(ev, robust=True, rows=extra)
    for me, v in meshes:
        tmesh.align(me, rs.head(f["c"]))
    for _ in range(rounds):
        rr = [mesh_feat_rows(me, f["c"], v, s, infl=infl) for me, v in meshes]
        if normals:
            for v, cam in zip(vs, f["cams"]):
                it = mm.item(f"{s}_{v}")
                rr.append(dense.rows(normals, mm.pred(normals, f"{s}_{v}"), f["c"], cam, v, hair=it["hair"] if it["look"]["hair"] else None, use=("n",), infl=4.0))
        f = fitlib.fit(ev, robust=True, rows=stack(extra, *rr), c_init=f["c"])
    return f


FEATM = {
    "F1 front lm + mesh(front) features": lambda s: featmesh_fit(s, ["front"], ["front"]),
    "F2 front+tq lm + mesh(tq) features": lambda s: featmesh_fit(s, FT, ["tq"]),
    "F3 front+tq lm + mesh(front) + mesh(tq) features": lambda s: featmesh_fit(s, FT, ["front", "tq"]),
    "F4 front+tq lm + david normals + mesh features (both)": lambda s: featmesh_fit(s, FT, ["front", "tq"], normals="david"),
    "F5 front+tq lm + david normals + mesh features + read": lambda s: featmesh_fit(s, FT, ["front", "tq"], normals="david", read=True),
    "F6 front+tq lm + sapiens2 normals + mesh features + read": lambda s: featmesh_fit(s, FT, ["front", "tq"], normals="sapiens2", read=True),
    "F7 front lm + david normals + mesh(front) features + read": lambda s: featmesh_fit(s, ["front"], ["front"], normals="david", read=True),
}
if __name__ == "__main__" and sys.argv[1] == "featmesh":
    fits.run(FEATM, sys.argv[2:], out="fits")


def oracle_align_fit(s, view="tq", infl=2.0, rounds=20, gain=True):
    """Diagnosis: the mesh laid on the TRUE head once (not available in practice), then dense rows."""
    ev = fits.evs(s, ["front"])
    idx, sg0 = mesh_idx(s)
    reg, _ = mm.region_of()
    gq = np.array([GAIN[r] for r in reg[idx]]) if gain else None
    sg = (np.array([LEFT[r] for r in reg[idx]]) if gain else sg0) * infl
    k = f"{s}_{view}"
    if not (tmesh.TR / f"{k}.npz").exists():
        return None
    me = tmesh.Mesh(k)
    tmesh.align(me, mm.item(k)["V"] if mm.item(k)["V"] is not None else None)
    f = fitlib.fit(ev, robust=True)
    for _ in range(rounds):
        R = tmesh.rows(me, f["c"], idx, sg, gain=gq, realign=False)
        f = fitlib.fit(ev, robust=True, rows=R, c_init=f["c"])
    return f


if __name__ == "__main__" and sys.argv[1] == "oracle":
    fits.run({"X1 front lm + mesh(tq), ORACLE alignment, gains": lambda s: oracle_align_fit(s),
              "X2 front lm + mesh(tq), ORACLE alignment, no gains x1": lambda s: oracle_align_fit(s, gain=False, infl=1.0)}, sys.argv[2:], out="fits")
