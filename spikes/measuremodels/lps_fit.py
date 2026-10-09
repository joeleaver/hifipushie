"""End to end on the scanned head (lps.py): detector points (+ a model's render-calibrated normals, gains x k) in the
study's MAP, scored by the fitted head's distance to the scan's surface (similarity ICP on the face, then mm along
the scan's normal by region).   run.sh lps_fit.py"""
import numpy as np
from PIL import Image

import dense
import fitlib
import fits
import fits2
import lps
import mm
import rs
import tmesh

FACE = ["nose", "chin", "lips", "eyes", "brow", "cheeks", "jaw", "forehead"]
SHOW = ["face", "nose", "chin", "brow", "cheeks", "jaw", "forehead", "lips"]


def ev(iid, view):
    im = np.asarray(Image.open(lps.L / "set" / f"{iid}.png").convert("RGB"))
    d = rs.detect([im])[0]
    t = fits.table("skin")
    k = fits.CLS[view]
    ok = t["sd"][k] < 2.5
    return {"pts": fitlib.points_tri(t["vid"][k][ok], t["w"][k][ok]), "uv": d["P"][ok, :2], "sig": np.sqrt(t["sd"][k][ok] ** 2 + 0.7 ** 2) * 2.0,
            "size": [im.shape[1], im.shape[0]], "yaw": {"front": 0.0, "tq": 40.0, "tq2": -38.0}[view], "expr": True}


def scaled(model, k):
    t = dict(np.load(mm.MM / f"dense_{model}.npz"))
    for q in list(t):
        if q.startswith("g_n_"):
            t[q] = np.clip(t[q] * k, 0, 1.2).astype(np.float32)
    dense._C[model] = t


def fit(E, pics, model=None, k=1.0, infl=4.0, rounds=3):
    f = fitlib.fit(E, robust=True)
    if model:
        scaled(model, k)
        for _ in range(rounds):
            rr = [dense.rows(model, dict(np.load(mm.PRED / model / f"{iid}.npz")), f["c"], cam, vw, use=("n",), infl=infl, regions=FACE) for (iid, vw), cam in zip(pics, f["cams"])]
            f = fitlib.fit(E, robust=True, rows=fits2.stack(*rr), c_init=f["c"])
    return f


def score(c):
    me = tmesh.Mesh("lps")
    H = rs.head(c)
    tmesh.align(me, H, yaw_hint=0)
    reg, _ = mm.region_of()
    g = rs.gnm()
    out = {}
    for r in SHOW:
        idx = np.flatnonzero(g["ext"] & (np.isin(reg, FACE) if r == "face" else reg == r))
        a, ok, q, nq = tmesh.offsets(me, H, idx)
        out[r] = float(np.sqrt((a[ok] ** 2).mean()) * 1000)
    return out


if __name__ == "__main__":
    runs = [("mean head", None, 0), ("points", "", 1), ("+ david x1", "david", 1.0), ("+ david x1.6", "david", 1.6), ("+ david x2", "david", 2.0),
            ("+ marigold x1", "marigold", 1.0), ("+ marigold x2", "marigold", 2.0), ("+ marigold_lcm x2", "marigold_lcm", 2.0), ("+ moge2 x1.6", "moge2", 1.6)]
    print("fitted head's distance to the scan's surface, mm rms (2 fits: soft light, hard light; front + three-quarter each)")
    print(f"{'':20s} " + " ".join(f"{r[:6]:>6s}" for r in SHOW) + "   sigma")
    acc = {}
    for lt in "ab":
        pics = [(f"lps_front_{lt}", "front"), (f"lps_tq_{lt}", "tq")]
        E = [ev(*p) for p in pics]
        for name, model, k in runs:
            if model is None:
                c = np.zeros(rs.K_FIT)
            else:
                c = fit(E, pics, model or None, k)["c"]
            s = score(c)
            s["sigma"] = float(np.sqrt((c ** 2).mean()))
            acc.setdefault(name, []).append(s)
    for name, L in acc.items():
        print(f"{name:20s} " + " ".join(f"{np.mean([x[r] for x in L]):6.2f}" for r in SHOW) + f"   {np.mean([x['sigma'] for x in L]):.2f}" +
              "   (" + " / ".join(f"{x['face']:.2f}" for x in L) + ")")
