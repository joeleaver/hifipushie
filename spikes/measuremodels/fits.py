"""Evidence on the SKINNED set for fitlib's MAP, and the method table.   run.sh fits.py [prefix ...]

Landmark tables (where each of MediaPipe's 478 points lies on GNM, per view class):
  clay  = refstudy's calib.npz (calibrated on numba clay / tinted renders)
  skin  = the same calibration redone on this set's 80 skinned calibration pictures (MM/calib_skin.npz)
  xr    = XR Blocks' FaceCorrespondence (473 landmark -> vertex pairs; one table for every view)
  xrref = xr's vertices + its "reference" offsets (where the landmarker puts the point on a neutral head)
"""
import base64
import json
import sys
import time

import numpy as np
from scipy.spatial import cKDTree

import fitlib
import mm
import rs
import subjects

CLS = {"front": 0, "tq": 1, "profile": 2, "tq2": 3}
_T = {}
_DET = {}


def det(iid):
    if iid not in _DET:
        _DET[iid] = rs.detect([mm.image(iid)])[0]
    return _DET[iid]


def calibrate(points_of, n_pts, name, min_n=12):
    """calib.py's method on this set's calibration pictures. points_of(iid) -> (n_pts, 2) pixels or None."""
    g = rs.gnm()
    ext = np.flatnonzero(g["ext"] | g["gr"]["eyes"])
    vid = np.zeros((4, n_pts, 3), np.int64)
    w = np.zeros((4, n_pts, 3))
    sd = np.full((4, n_pts), np.inf)
    found = {}
    tree0 = cKDTree(g["V0"][ext])
    for k, ci in CLS.items():
        T = []
        ids = mm.ids("cal", k)
        for iid in ids:
            P = points_of(iid)
            if P is None:
                continue
            it = mm.item(iid)
            X = rs.unproject(it["cam"], P[:, :2], it["zb"])
            ok = np.isfinite(X[:, 0])
            vis = rs.visible(it["V"], it["cam"], ext, it["zb"])
            dd, jj = cKDTree(it["V"][ext[vis]]).query(np.nan_to_num(X), k=3)
            ii = ext[vis][jj]
            ww = 1.0 / np.maximum(dd, 1e-5)
            ww /= ww.sum(1, keepdims=True)
            tpl = (g["V0"][ii] * ww[..., None]).sum(1)
            tpl[~ok | (dd[:, 0] > 0.004)] = np.nan
            T.append(tpl)
        found[k] = (len(T), len(ids))
        if len(T) < min_n:
            continue
        T = np.array(T)
        med = np.nanmedian(T, 0)
        s = np.sqrt(np.nanmean(((T - med) ** 2).sum(-1), 0)) * 1000
        s[np.isfinite(T[..., 0]).mean(0) < 0.9] = np.inf
        dd, jj = tree0.query(np.nan_to_num(med), k=3)
        ww = 1.0 / np.maximum(dd, 1e-5)
        vid[ci], w[ci], sd[ci] = ext[jj], ww / ww.sum(1, keepdims=True), s
    np.savez(mm.MM / f"calib_{name}.npz", vid=vid, w=w, sd=sd)
    return found, sd


def xr_table():
    src = (mm.MM / "xrblocks" / "dl" / "FaceCorrespondence.js").read_text()
    packed = "".join(ln.strip().strip("';+ ") for ln in src.split("const PACKED =")[1].split("function decode")[0].splitlines())
    buf = base64.b64decode(packed.rstrip(";"))
    n = 473
    ref = np.frombuffer(buf, np.float32, n * 3, 0).reshape(n, 3)
    lm = np.frombuffer(buf, np.uint16, n, 5676)
    vx = np.frombuffer(buf, np.uint16, n, 6622)
    rigid = np.frombuffer(buf, np.uint8, n, 7568)
    return {"ref": rs.to_world(ref.astype(float)), "lm": lm.astype(int), "vx": vx.astype(int), "rigid": rigid.astype(bool)}


def table(name):
    if name in _T:
        return _T[name]
    if name in ("clay", "skin") or name.startswith("cal:"):
        f = rs.D / "calib.npz" if name == "clay" else mm.MM / f"calib_{name.split(':')[-1]}.npz"
        z = np.load(f)
        t = {"vid": z["vid"], "w": z["w"], "sd": z["sd"].copy()}
    else:
        x = xr_table()
        vid = np.zeros((4, 478, 3), np.int64)
        w = np.zeros((4, 478, 3))
        sd = np.full((4, 478), np.inf)
        vid[:, x["lm"], :] = x["vx"][None, :, None]
        w[:, x["lm"], 0] = 1.0
        sd[:, x["lm"]] = 1.5
        t = {"vid": vid, "w": w, "sd": sd}
        if name == "xrref":
            off = np.zeros((478, 3))
            off[x["lm"]] = x["ref"] - rs.gnm()["V0"][x["vx"]]
            t["off"] = off
    _T[name] = t
    return t


def ev478(iid, tab="skin", infl=2.0, floor=0.7, cut=2.5, sd_from=None):
    d = det(iid)
    if d is None:
        return None
    it = mm.item(iid)
    t = table(tab)
    k = CLS[it["view"]]
    sd = t["sd"][k] if sd_from is None else np.where(np.isfinite(t["sd"][k]), table(sd_from)["sd"][k], np.inf)
    ok = sd < cut
    if ok.sum() < 20:
        return None
    pts = fitlib.points_tri(t["vid"][k][ok], t["w"][k][ok])
    if "off" in t:
        pts["X0"] = pts["X0"] + t["off"][ok]
    return {"pts": pts, "uv": d["P"][ok, :2], "sig": np.sqrt(sd[ok] ** 2 + floor ** 2) * infl, "size": it["cam"]["size"],
            "yaw": subjects.VIEWS[it["view"]], "expr": True}


def evs(sub, views, **kw):
    out = [ev478(f"{sub}_{v}", **kw) for v in views]
    return [e for e in out if e is not None]


def truth(sub):
    return subjects.load(sub)


def run(methods, want=None, out="fits"):
    res_f = mm.MM / "out" / f"{out}.json"
    res = json.loads(res_f.read_text()) if res_f.exists() else {}
    subs = subjects.names()
    mean = rs.head()
    res["-- mean head (no fit)"] = {s: rs.score(mean, truth(s)["V"]) for s in subs}
    for m, fn in methods.items():
        if want and not any(m.startswith(w) for w in want):
            continue
        t0 = time.time()
        res[m] = {}
        for s in subs:
            try:
                f = fn(s)
                if f is None:
                    continue
                c = f["c"] if isinstance(f, dict) else f
                sc = rs.score(rs.head(c), truth(s)["V"])
                sc["sigma"] = float(np.sqrt((np.asarray(c) ** 2).mean()))
                res[m][s] = sc
            except Exception as ex:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                print("FAILED", m, s, repr(ex)[:200])
        res[m]["_time"] = (time.time() - t0) / max(len(subs), 1)
        res_f.write_text(json.dumps(res, indent=1))
        show(res, [m])
    return res


def show(res, only=None):
    print(f"{'method':52s} {'set':3s} {'n':>2s} " + rs.HEADER + "  sigma    s", flush=True)
    for m, r in res.items():
        if only and m not in only:
            continue
        for tag in ("S", "O"):
            rows = [v for k, v in r.items() if k.startswith(tag)]
            if not rows:
                continue
            avg = {k: float(np.mean([x[k] for x in rows])) for k in rs.REGIONS}
            sg = np.mean([x.get("sigma", 0.0) for x in rows])
            print(f"{m[:52]:52s} {tag:3s} {len(rows):2d} " + rs.row(avg) + f"  {sg:5.2f} {r.get('_time', 0):4.1f}", flush=True)


def mp_points(iid):
    d = det(iid)
    return None if d is None else d["P"]


FT = ["front", "tq"]
BASE = {
    "L0 mp478 clay table, front+tq": lambda s: fitlib.fit(evs(s, FT, tab="clay"), robust=True),
    "L1 mp478 skin table, front+tq": lambda s: fitlib.fit(evs(s, FT, tab="skin"), robust=True),
    "L1f mp478 skin table, front only": lambda s: fitlib.fit(evs(s, ["front"], tab="skin"), robust=True),
    "L2 xr vertices (sigma 1.5), front+tq": lambda s: fitlib.fit(evs(s, FT, tab="xr"), robust=True),
    "L2f xr vertices, front only": lambda s: fitlib.fit(evs(s, ["front"], tab="xr"), robust=True),
    "L3 xr vertices + xr reference offsets, front+tq": lambda s: fitlib.fit(evs(s, FT, tab="xrref"), robust=True),
    "L3f xr + reference offsets, front only": lambda s: fitlib.fit(evs(s, ["front"], tab="xrref"), robust=True),
}


if __name__ == "__main__":
    if not (mm.MM / "calib_skin.npz").exists() or "recal" in sys.argv:
        found, sd = calibrate(mp_points, 478, "skin")
        print("MediaPipe on the skinned calibration pictures, found / of:", found)
        for k, ci in CLS.items():
            ok = sd[ci] < 2.5
            print(f"  {k}: usable points {ok.sum()}, median scatter {np.median(sd[ci][np.isfinite(sd[ci])]) if np.isfinite(sd[ci]).any() else float('nan'):.2f} mm")
        # the two tables' definitions against each other, and against XR Blocks'
        g = rs.gnm()
        a, b = table("clay"), np.load(mm.MM / "calib_skin.npz")
        x = xr_table()
        for k, ci in CLS.items():
            ok = (a["sd"][ci] < 2.5) & (b["sd"][ci] < 2.5)
            if ok.sum() < 10:
                continue
            pa = (g["V0"][a["vid"][ci]] * a["w"][ci][..., None]).sum(1)
            pb = (g["V0"][b["vid"][ci]] * b["w"][ci][..., None]).sum(1)
            d = np.linalg.norm(pa - pb, axis=1)[ok] * 1000
            dx = np.linalg.norm(pb[x["lm"]] - g["V0"][x["vx"]], axis=1) * 1000
            okx = b["sd"][ci][x["lm"]] < 2.5
            dr = np.linalg.norm(pb[x["lm"]] - x["ref"], axis=1) * 1000
            print(f"  {k}: clay vs skin table: median {np.median(d):.2f} mm, p90 {np.quantile(d, 0.9):.2f} | XR Blocks vertex vs skin table ({okx.sum()} pts): median {np.median(dx[okx]):.2f}, p90 {np.quantile(dx[okx], 0.9):.2f}, max {dx[okx].max():.1f} | XR reference cloud vs skin table: median {np.median(dr[okx]):.2f}")
    res = run(BASE, [a for a in sys.argv[1:] if a != "recal"])
    print()
    show(res)
