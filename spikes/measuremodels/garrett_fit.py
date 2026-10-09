"""Garrett's two references through the study's stack (GNM fast lane): detector points (skin-calibrated table) +
DAViD normals (+ generated meshes when present) -> identity c, its macros with honest sigmas (the truth set's
per-macro error of the same method).   run.sh garrett_fit.py"""
import json

import numpy as np
from PIL import Image

import dense
import fitlib
import fits
import fits2
import mm
import rs
import tmesh
from hifipushie import humanmacro as hm

FACE = ["nose", "chin", "lips", "eyes", "brow", "cheeks", "jaw", "forehead"]
PICS = {"garrett_front": "front", "garrett_desk": "tq"}


def ev(name, view):
    im = np.asarray(Image.open(mm.MM / "img" / f"{name}.png").convert("RGB"))
    d = rs.detect([im])[0]
    t = fits.table("skin")
    k = fits.CLS[view]
    ok = t["sd"][k] < 2.5
    return {"pts": fitlib.points_tri(t["vid"][k][ok], t["w"][k][ok]), "uv": d["P"][ok, :2], "sig": np.sqrt(t["sd"][k][ok] ** 2 + 0.7 ** 2) * 2.0,
            "size": [im.shape[1], im.shape[0]], "yaw": {"front": 0.0, "tq": 40.0}[view], "expr": True}


def fit(pics, normals=True, meshes=(), rounds=3, normal_pics=None):
    E = [ev(n, PICS[n]) for n in pics]
    f = fitlib.fit(E, robust=True)
    M = []
    for m in meshes:
        if (tmesh.TR / f"{m}.npz").exists():
            me = tmesh.Mesh(m)
            tmesh.align(me, rs.head(f["c"]))
            M.append(me)
    g = rs.gnm()
    reg, _ = mm.region_of()
    okm = g["ext"] & np.isin(reg, FACE + ["ears", "neck"]) if True else None     # hair hides his cranium; a collar his lower neck
    idx = np.flatnonzero(okm)[::5]
    sg = np.array([fits2.SIG[r] for r in reg[idx]]) * 2.0
    for _ in range(rounds):
        rr = []
        if normals:
            for n, cam in zip(pics, f["cams"]):
                if normal_pics is not None and n not in normal_pics:
                    continue
                rr.append(dense.rows("david", mm.pred("david", n), f["c"], cam, PICS[n], use=("n",), infl=4.0, regions=FACE))
        for me in M:
            rr.append(tmesh.rows(me, f["c"], idx, sg))
        R = fits2.stack(*rr)
        f = fitlib.fit(E, robust=True, rows=R, c_init=f["c"])
    return f


if __name__ == "__main__":
    out = {}
    runs = {"points (front + desk)": dict(pics=list(PICS), normals=False),
            "points + DAViD normals (front picture's normals only)": dict(pics=list(PICS), normal_pics=["garrett_front"]),
            "points + DAViD normals (both)": dict(pics=list(PICS)),
            "points + normals(front) + TRELLIS mesh(front)": dict(pics=list(PICS), normal_pics=["garrett_front"], meshes=["garrett_front"]),
            "points + normals(front) + TRELLIS meshes (front, desk)": dict(pics=list(PICS), normal_pics=["garrett_front"], meshes=["garrett_front", "garrett_desk"])}
    for k, kw in runs.items():
        if kw.get("meshes") and not all((tmesh.TR / f"{m}.npz").exists() for m in kw["meshes"]):
            continue
        f = fit(**kw)
        z = hm.read(c=f["c"])
        out[k] = {"c": [float(x) for x in f["c"]], "macros": z, "sigma": float(np.sqrt((f["c"] ** 2).mean())),
                  "cams": [{kk: (vv if not isinstance(vv, np.ndarray) else vv.tolist()) for kk, vv in c.items()} for c in f["cams"]]}
        print(f"\n{k}: {out[k]['sigma']:.2f} sigma rms; lens {[round(c['f'] / c['size'][0] * 36) for c in f['cams']]} mm")
        print("   " + hm.text(z, top=14).replace("\n", "\n   "))
    (mm.MM / "out" / "garrett_fits.json").write_text(json.dumps(out, indent=1))
