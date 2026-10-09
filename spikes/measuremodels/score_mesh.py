"""Generated head meshes (TRELLIS.2 via Oxidegen) against truth, in their own terms.   run.sh score_mesh.py

Each mesh is laid on its TRUE head by a similarity (ICP on the face: the best case), then at every truth vertex:
  a = the mesh surface's signed offset from the truth surface along the normal (mm)   -> the mesh's error
  b = the same for GNM's mean head (laid on the face by a similarity)                 -> what knowing nothing costs
"Does it see THIS head": corr(a - b, -b) = the mesh's deviation from the mean against the truth's, by region and
for profile features (nose tip, nasion, brow, subnasale, lips, chin, under-chin, gonion, ear, occiput).
"""
import json

import numpy as np

import mm
import rs
import tmesh

G = None
FEATS = {"nose tip": [30], "nasion": [27], "brow (glabella)": [21, 22], "subnasale": [33], "upper lip": [51], "lower lip": [57],
         "chin": [8], "jaw angle": [4, 12], "jaw mid": [6, 10], "cheekbone": [1, 15]}


def feature_sets(V):
    """Vertex sets round profile / outline features (within 7 mm of the landmark on the truth head), + a few by region."""
    g = rs.gnm()
    L = rs.landmarks(V)
    ext = np.flatnonzero(g["ext"])
    out = {}
    for k, ii in FEATS.items():
        m = np.zeros(len(ext), bool)
        for i in ii:
            m |= np.linalg.norm(V[ext] - L[i], axis=1) < 0.007
        out[k] = ext[m]
    zc = L[8, 2]
    under = ext[(np.abs(V[ext, 0]) < 0.012) & (V[ext, 2] < zc - 0.004) & (V[ext, 2] > zc - 0.03) & (V[ext, 1] < L[8, 1] + 0.05) & (V[ext, 1] > L[8, 1] + 0.012)]
    out["under-chin"] = under
    cr = g["regions"]["cranium"]
    out["occiput"] = cr[(V[cr, 1] > V[cr, 1].max() - 0.02)]
    out["crown"] = cr[(V[cr, 2] > V[cr, 2].max() - 0.012)]
    nk = g["regions"]["neck"]
    out["neck side"] = nk[(np.abs(V[nk, 0]) > np.abs(V[nk, 0]).max() * 0.0 + 0.04) & (V[nk, 2] > zc - 0.05) & (V[nk, 2] < zc - 0.02)]
    out["ear"] = g["regions"]["ears"]
    return out


def one(name):
    it = mm.item(name)
    Vt = it["V"]
    g = rs.gnm()
    me = tmesh.Mesh(name)
    e = tmesh.align(me, Vt)
    ext = np.flatnonzero(g["ext"])
    a, ok, q, nq = tmesh.offsets(me, Vt, ext)
    V0 = g["V0"]
    f = g["regions"]["face"]
    s, R, t = rs.similarity(V0[f], Vt[f])
    M = s * V0 @ R.T + t
    nt = mm.vnormals(Vt)
    b = ((M - Vt) * nt).sum(1)[ext]
    reg, _ = mm.region_of()
    A = np.full(len(Vt), np.nan)
    A[ext] = np.where(ok, a, np.nan) * 1000
    B = np.zeros(len(Vt))
    B[ext] = b * 1000
    if it["look"]["hair"]:    # under the hair stand-in nothing was shown
        hid = g["regions"]["cranium"]
        A[hid] = np.nan
    np.savez_compressed(mm.MM / "out" / f"mesh_{name}.npz", A=A, B=B, T_s=me.T[0], T_R=me.T[1], T_t=me.T[2])
    fs = feature_sets(Vt)
    feat = {k: (float(np.nanmean(A[i])), float(B[i].mean())) for k, i in fs.items() if np.isfinite(A[i]).sum() > 3}
    return {"name": name, "view": it["view"], "icp_mm": e * 1000, "start": me.start, "A": A, "B": B, "feat": feat, "scale": me.T[0]}


def main():
    g = rs.gnm()
    names = sorted(p.stem for p in tmesh.TR.glob("*.npz") if not p.stem.startswith("garrett"))
    rows = []
    for n in names:
        r = one(n)
        rows.append(r)
        print(f"{n:28s} icp {r['icp_mm']:5.2f} mm  start yaw {r['start'][0]:4d} head share {r['start'][1]:.2f}  scale {r['scale']:.4f}", flush=True)
    (mm.MM / "out" / "mesh_feats.json").write_text(json.dumps({r["name"]: r["feat"] for r in rows}))
    res = {}
    for vw in ("front", "tq", "profile"):
        rr = [r for r in rows if r["view"] == vw]
        if not rr:
            continue
        print(f"\nmeshes from {vw} pictures ({len(rr)}): surface offset from truth, mm (after ICP on the true face)")
        print(f"{'region':10s} {'n':>6s} | {'mesh mean|a|':>12s} {'rms':>6s} | {'mean head |b|':>13s} {'rms':>6s} | {'corr':>5s} {'gain':>5s} | {'left with gain':>14s}")
        for k in mm.REG + ("head",):
            idx = g["regions"][k]
            a = np.concatenate([r["A"][idx] for r in rr])
            b = np.concatenate([r["B"][idx] for r in rr])
            m = np.isfinite(a)
            if m.sum() < 100:
                continue
            a, b = a[m], b[m]
            dm, dt = a - b, -b
            cc = float(np.corrcoef(dm, dt)[0, 1])
            gain = float((dm @ dt) / (dm @ dm))
            left = float(np.sqrt(((b + gain * dm) ** 2).mean()))
            print(f"{k:10s} {m.sum():6d} | {np.abs(a).mean():12.2f} {np.sqrt((a ** 2).mean()):6.2f} | {np.abs(b).mean():13.2f} {np.sqrt((b ** 2).mean()):6.2f} | {cc:5.2f} {gain:5.2f} | {left:14.2f}")
            res[f"{vw}/{k}"] = {"mesh_abs": float(np.abs(a).mean()), "mesh_rms": float(np.sqrt((a ** 2).mean())), "mean_abs": float(np.abs(b).mean()),
                                "mean_rms": float(np.sqrt((b ** 2).mean())), "corr": cc, "gain": gain, "left": left}
        print(f"\n  features, {vw}: one number per head (mm along the normal); across heads: does the mesh's deviation follow the truth's?")
        print(f"  {'feature':16s} {'n':>3s} | {'mesh err rms':>12s} {'mean-head err rms':>17s} | {'corr':>5s} {'gain':>5s}")
        for k in list(FEATS) + ["under-chin", "ear", "occiput", "crown", "neck side"]:
            ab = np.array([r["feat"][k] for r in rr if k in r["feat"]])
            if len(ab) < 3:
                continue
            dm, dt = ab[:, 0] - ab[:, 1], -ab[:, 1]
            cc = float(np.corrcoef(dm, dt)[0, 1]) if len(ab) > 2 else float("nan")
            gain = float((dm @ dt) / max(dm @ dm, 1e-9))
            print(f"  {k:16s} {len(ab):3d} | {np.sqrt((ab[:, 0] ** 2).mean()):12.2f} {np.sqrt((ab[:, 1] ** 2).mean()):17.2f} | {cc:5.2f} {gain:5.2f}")
            res[f"{vw}/feat/{k}"] = {"mesh_rms": float(np.sqrt((ab[:, 0] ** 2).mean())), "mean_rms": float(np.sqrt((ab[:, 1] ** 2).mean())), "corr": cc, "gain": gain, "n": len(ab)}
    (mm.MM / "out" / "mesh_scores.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
