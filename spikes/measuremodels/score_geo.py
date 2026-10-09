"""A dense model's depth and normals against truth, in its own terms.   run.sh score_geo.py <model> [inverse] [flip=xyz signs]

DEPTH: per picture the model's depth is laid on the true depth by a scale + shift on the visible face (what a fit
would have to solve anyway); what is left along the camera's depth, mm rms by region, beside the same for GNM's MEAN
head laid on the face by a similarity. Then the question that matters: does the model see THIS head? dev_model =
model - mean head, dev_true = truth - mean head (both mm along depth): their correlation, the gain (the factor to
multiply the model's deviation by), and the residual left when the model's deviation x gain is used (gain from the
CALIBRATION heads, applied to the truth heads).
NORMALS: angle to the true normal by region (deg), beside the mean head's; correlation / gain of deviations likewise.
"""
import json
import sys

import numpy as np

import mm
import score_mesh

VIEWS = ("front", "tq", "tq2", "profile")


def collect(model, inverse=False, flip=(1, 1, 1)):
    rows = []
    for iid in mm.ids():
        p = mm.pred(model, iid)
        if p is None:
            continue
        it = mm.item(iid)
        if it["face"].sum() < 50:
            continue
        Xm, nm = mm.mean_head(it)
        r = {"id": iid, "view": it["view"], "cal": iid.startswith("C"), "reg": it["reg"], "face": it["face"]}
        fs = score_mesh.feature_sets(it["V"])
        pos = -np.ones(len(it["V"]), int)
        pos[it["idx"]] = np.arange(len(it["idx"]))
        r["fs"] = {k: pos[v][pos[v] >= 0] for k, v in fs.items()}
        zt = it["Xc"][:, 2] * 1000
        if "depth" in p or "points" in p:
            D = p["depth"] if "depth" in p else p["points"][..., 2]
            D = np.nan_to_num(np.where(np.isfinite(D), D, 0.0))
            d = mm.sample(D.astype(float), it["pix"])
            z = mm.fit_z(d, zt, it["face"].astype(float), inverse=inverse)
            r["dz"] = z - zt
            r["dz_mean"] = Xm[:, 2] * 1000 - zt
        if "normal" in p:
            n = mm.sample(p["normal"].astype(float), it["pix"]) * np.asarray(flip, float)
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
            r["n"], r["nt"], r["nm"] = n, it["n"], nm
        rows.append(r)
    return rows


def regs(r):
    out = {"face": r["face"]}
    for k in mm.REG[1:]:
        out[k] = r["reg"] == k
    return out


def table(rows, model, out):
    cal = [r for r in rows if r["cal"]]
    tru = [r for r in rows if not r["cal"]]
    res = {}
    if rows and "dz" in rows[0]:
        print(f"\n{model} DEPTH: mm rms along the camera's depth after scale + shift on the face; truth heads ({len(tru)} pictures), calibration ({len(cal)})")
        print(f"{'view':8s} {'region':9s} {'n':>6s} | {'model':>6s} {'mean':>6s} | {'corr':>5s} {'gain':>5s} | {'mean+g*dev':>10s}  (gain from calibration heads)")
        for vw in VIEWS:
            for k in mm.REG:
                def stack(rr, key):
                    xs = [r[key][regs(r)[k]] for r in rr if r["view"] == vw]
                    return np.concatenate(xs) if xs else np.zeros(0)
                a, b = stack(tru, "dz"), stack(tru, "dz_mean")
                if len(a) < 200:
                    continue
                ca, cb = stack(cal, "dz"), stack(cal, "dz_mean")
                dm, dt = a - b, -b                       # model - mean, truth - mean
                cdm, cdt = ca - cb, -cb
                gain = float((cdm @ cdt) / max(cdm @ cdm, 1e-9)) if len(cdm) else float("nan")
                cc = float(np.corrcoef(dm, dt)[0, 1])
                blend = float(np.sqrt(((b + gain * dm) ** 2).mean()))
                rm, rb = float(np.sqrt((a ** 2).mean())), float(np.sqrt((b ** 2).mean()))
                print(f"{vw:8s} {k:9s} {len(a):6d} | {rm:6.2f} {rb:6.2f} | {cc:5.2f} {gain:5.2f} | {blend:10.2f}")
                res[f"depth/{vw}/{k}"] = {"model": rm, "mean": rb, "corr": cc, "gain": gain, "blend": blend, "n": len(a)}
    if rows and "dz" in rows[0]:
        print(f"\n{model} FEATURES (depth): one number per picture = mean depth error over the feature's patch, mm; across ALL heads (truth + calibration): does the model's deviation from the mean head follow the head's own?")
        print(f"{'view':8s} {'feature':16s} {'n':>3s} | {'model rms':>9s} {'mean rms':>8s} | {'corr':>5s} {'gain':>5s}")
        for vw in VIEWS:
            for k in list(score_mesh.FEATS) + ["under-chin", "ear", "neck side"]:
                ab = np.array([[r["dz"][r["fs"][k]].mean(), r["dz_mean"][r["fs"][k]].mean()] for r in rows if r["view"] == vw and len(r["fs"][k]) > 5])
                if len(ab) < 8:
                    continue
                dm, dt = ab[:, 0] - ab[:, 1], -ab[:, 1]
                cc = float(np.corrcoef(dm, dt)[0, 1])
                print(f"{vw:8s} {k:16s} {len(ab):3d} | {np.sqrt((ab[:, 0] ** 2).mean()):9.2f} {np.sqrt((ab[:, 1] ** 2).mean()):8.2f} | {cc:5.2f} {(dm @ dt) / max(dm @ dm, 1e-9):5.2f}")
                res[f"feat/{vw}/{k}"] = {"model": float(np.sqrt((ab[:, 0] ** 2).mean())), "mean": float(np.sqrt((ab[:, 1] ** 2).mean())), "corr": cc, "n": len(ab)}
    if rows and "n" in rows[0]:
        print(f"\n{model} NORMALS: mean angle to the true normal, deg")
        print(f"{'view':8s} {'region':9s} {'n':>6s} | {'model':>6s} {'mean':>6s} | {'corr':>5s} {'gain':>5s} | {'mean+g*dev':>10s}")
        ang = lambda x, y: np.degrees(np.arccos(np.clip((x * y).sum(1), -1, 1)))  # noqa: E731
        for vw in VIEWS:
            for k in mm.REG:
                def stack(rr, key):
                    xs = [r[key][regs(r)[k]] for r in rr if r["view"] == vw]
                    return np.concatenate(xs) if xs else np.zeros((0, 3))
                n, nt, nm = stack(tru, "n"), stack(tru, "nt"), stack(tru, "nm")
                if len(n) < 200:
                    continue
                cn, cnt, cnm = stack(cal, "n"), stack(cal, "nt"), stack(cal, "nm")
                dm, dt = n - nm, nt - nm
                cdm, cdt = cn - cnm, cnt - cnm
                gain = float((cdm * cdt).sum() / max((cdm * cdm).sum(), 1e-9)) if len(cdm) else float("nan")
                cc = float((dm * dt).sum() / np.sqrt((dm * dm).sum() * (dt * dt).sum()))
                bl = nm + gain * dm
                bl /= np.linalg.norm(bl, axis=1, keepdims=True)
                am, ab, abl = float(ang(n, nt).mean()), float(ang(nm, nt).mean()), float(ang(bl, nt).mean())
                print(f"{vw:8s} {k:9s} {len(n):6d} | {am:6.2f} {ab:6.2f} | {cc:5.2f} {gain:5.2f} | {abl:10.2f}")
                res[f"normal/{vw}/{k}"] = {"model": am, "mean": ab, "corr": cc, "gain": gain, "blend": abl, "n": len(n)}
    (mm.MM / "out" / f"geo_{out}.json").write_text(json.dumps(res, indent=1))


def best_flip(model):
    """The model's normal axis signs, found on the first pictures (conventions differ: y up / z toward the camera)."""
    best = None
    for sx in (1, -1):
        for sy in (1, -1):
            for sz in (1, -1):
                tot, k = 0.0, 0
                for iid in mm.ids()[:6]:
                    p = mm.pred(model, iid)
                    if p is None or "normal" not in p:
                        continue
                    it = mm.item(iid)
                    n = mm.sample(p["normal"].astype(float), it["pix"]) * [sx, sy, sz]
                    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
                    tot += float((n * it["n"]).sum(1).mean())
                    k += 1
                if k and (best is None or tot / k > best[0]):
                    best = (tot / k, (sx, sy, sz))
    return best


if __name__ == "__main__":
    model = sys.argv[1]
    inverse = "inverse" in sys.argv[2:]
    flip = (1, 1, 1)
    b = best_flip(model)
    if b:
        flip = b[1]
        print("normal axis signs", flip, "mean cos", round(b[0], 3))
    rows = collect(model, inverse, flip)
    table(rows, model, model + ("_inv" if inverse else ""))
