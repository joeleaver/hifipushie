"""The method table on the ground-truth set. Every row: 3D error by region (mm, after similarity alignment on the
face), averaged over subjects (in-model S*, out-of-model O*).  run.sh table.py [method-prefix ...]"""
import json
import sys
import time

import numpy as np

import fitlib
import rs
import subjects

CAL = None
CLS = {"front": 0, "tq": 1, "profile": 2, "tq2": 3}
HAND = [27, 30, 33, 51, 57, 8, 36, 45, 48, 54]   # what a person can click in a profile / any picture


def calib():
    global CAL
    if CAL is None:
        z = np.load(rs.D / "calib.npz")
        CAL = {"vid": z["vid"], "w": z["w"], "sd": z["sd"].copy()}
        CAL["sd"][2] = np.inf   # the detector doesn't find profiles
    return CAL


_DET = {}


def det(name, view):
    if (name, view) not in _DET:
        _DET[(name, view)] = rs.detect([subjects.image(name, view)])[0]
    return _DET[(name, view)]


def view_true(sub, view):
    cam = sub["views"][view]["cam"]
    V = sub["V"] + (sub["e"] if (sub["e"] is not None and sub["views"][view]["expression"]) else 0.0)
    return cam, V


def ev_oracle(sub, view, noise=0.0, ids=None, seed=0, sig=None):
    cam, V = view_true(sub, view)
    ids = np.arange(70) if ids is None else np.asarray(ids)
    L = rs.landmarks(V)[ids]
    vis = np.ones(len(ids), bool)
    if abs(cam["yaw"]) > 20:   # a turned picture: only what the camera sees
        Xc = rs.cam_xform(cam, L)
        zb = np.load(subjects.OUT / f"{sub['name']}_{view}_zb.npy")
        P = rs.humanfit.project(cam, L)
        u, v = np.clip(P[:, 0].astype(int), 0, cam["size"][0] - 1), np.clip(P[:, 1].astype(int), 0, cam["size"][1] - 1)
        vis = Xc[:, 2] < zb[v, u] + 0.006
    ids = ids[vis]
    uv = rs.humanfit.project(cam, L[vis])
    mmpx = cam["t"][2] / cam["f"] * 1000
    uv = uv + np.random.default_rng(seed + CLS[view]).normal(0, noise / mmpx, uv.shape)
    return {"pts": fitlib.points_lm(ids), "uv": uv, "sig": sig if sig else max(noise, 0.3), "size": cam["size"], "yaw": subjects.VIEWS[view]}


def ev_mp68(sub, view, sig=0.86, jaw=False):
    d = det(sub["name"], view)
    if d is None:
        return None
    ids = np.arange(70) if jaw else np.arange(17, 70)
    uv = d["P"][rs.LM_FROM_MP, :2][ids]
    cam = sub["views"][view]["cam"]
    return {"pts": fitlib.points_lm(ids), "uv": uv, "sig": sig, "size": cam["size"], "yaw": subjects.VIEWS[view]}


def ev_mp478(sub, view, infl=1.0, floor=0.7, cut=2.5):
    d = det(sub["name"], view)
    if d is None:
        return None
    ca = calib()
    k = CLS[view]
    ok = ca["sd"][k] < cut
    cam = sub["views"][view]["cam"]
    return {"pts": fitlib.points_tri(ca["vid"][k][ok], ca["w"][k][ok]), "uv": d["P"][ok, :2],
            "sig": np.sqrt(ca["sd"][k][ok] ** 2 + floor ** 2) * infl, "size": cam["size"], "yaw": subjects.VIEWS[view]}


def with_outline(ev, sub, view, sig_o=1.5):
    cam, V = view_true(sub, view)
    zb = np.load(subjects.OUT / f"{sub['name']}_{view}_zb.npy")
    o = rs.outline(zb, cam, V)
    return {**ev, "outline": o[::2], "sig_o": sig_o}


def evidence(sub, views, kind, outline=False, **kw):
    out = []
    for v in views:
        if v == "profile" and kind.startswith("mp"):   # no detection in a profile: hand points (+-1.5 mm) + its outline
            e = ev_oracle(sub, v, noise=1.5, ids=HAND, seed=hash(sub["name"]) % 1000)
            e = with_outline(e, sub, v)
        else:
            e = {"oracle": ev_oracle, "mp68": ev_mp68, "mp478": ev_mp478}[kind](sub, v, **kw)
            if e is None:
                continue
            if outline:
                e = with_outline(e, sub, v)
        e["expr"] = True
        out.append(e)
    return out


FT = ["front", "tq"]
METHODS = {
    # -- how much do the 70 landmarks hold at all (no noise, exact definitions)?
    "A0 oracle lm, no noise, MAP": lambda s: fitlib.fit(evidence(s, FT, "oracle", noise=0.0)),
    "A1 oracle lm +-1.5mm, today's weights": lambda s: fitlib.fit(evidence(s, FT, "oracle", noise=1.5, sig=0.86), lam=0.01, rows=fitlib.cranium_rows(rs.K_FIT)),
    "A2 oracle lm +-1.5mm, MAP": lambda s: fitlib.fit(evidence(s, FT, "oracle", noise=1.5)),
    # -- the detector
    "B0 mp68 with jaw, today's weights": lambda s: fitlib.fit(evidence(s, FT, "mp68", jaw=True), lam=0.01, rows=fitlib.cranium_rows(rs.K_FIT)),
    "B1 mp68 no jaw, today's weights (fit_views)": lambda s: fitlib.fit(evidence(s, FT, "mp68"), lam=0.01, rows=fitlib.cranium_rows(rs.K_FIT)),
    "B2 mp68 no jaw, MAP sigma 3mm": lambda s: fitlib.fit(evidence(s, FT, "mp68", sig=3.0)),
    "B3 mp478 calibrated, MAP": lambda s: fitlib.fit(evidence(s, FT, "mp478"), robust=True),
    "B3b mp478 calibrated, sigma x2": lambda s: fitlib.fit(evidence(s, FT, "mp478", infl=2.0), robust=True),
    "B3c mp478 calibrated, sigma x4": lambda s: fitlib.fit(evidence(s, FT, "mp478", infl=4.0), robust=True),
    "B4 B3b + outline": lambda s: fitlib.fit(evidence(s, FT, "mp478", infl=2.0, outline=True), robust=True, rounds=5),
    "B5 B3b + expression": lambda s: fitlib.fit(evidence(s, FT, "mp478", infl=2.0), robust=True, expr=True),
    "B6 B3b + outline + expression": lambda s: fitlib.fit(evidence(s, FT, "mp478", infl=2.0, outline=True), robust=True, expr=True, rounds=5),
    # -- which pictures
    "V1 front only (B6)": lambda s: fitlib.fit(evidence(s, ["front"], "mp478", infl=2.0, outline=True), robust=True, expr=True, rounds=5),
    "V2 front + tq (B6)": lambda s: fitlib.fit(evidence(s, FT, "mp478", infl=2.0, outline=True), robust=True, expr=True, rounds=5),
    "V3 front + tq + tq2": lambda s: fitlib.fit(evidence(s, FT + ["tq2"], "mp478", infl=2.0, outline=True), robust=True, expr=True, rounds=5),
    "V4 front + tq + profile": lambda s: fitlib.fit(evidence(s, FT + ["profile"], "mp478", infl=2.0, outline=True), robust=True, expr=True, rounds=5),
    "V5 front + profile": lambda s: fitlib.fit(evidence(s, ["front", "profile"], "mp478", infl=2.0, outline=True), robust=True, expr=True, rounds=5),
    "V6 all four": lambda s: fitlib.fit(evidence(s, FT + ["tq2", "profile"], "mp478", infl=2.0, outline=True), robust=True, expr=True, rounds=5),
}


def main():
    want = sys.argv[1:]
    res_f = rs.D / "out" / "table.json"
    res = json.loads(res_f.read_text()) if res_f.exists() else {}
    subs = [subjects.load(n) for n in subjects.names()]
    mean = rs.head()
    res["-- mean head (no fit)"] = {s["name"]: rs.score(mean, s["V"]) for s in subs}
    for m, fn in METHODS.items():
        if want and not any(m.startswith(w) for w in want):
            continue
        t0 = time.time()
        res[m] = {}
        for s in subs:
            try:
                f = fn(s)
                sc = rs.score(rs.head(f["c"]), s["V"])
                sc["sigma"] = float(np.sqrt((f["c"] ** 2).mean()))
                res[m][s["name"]] = sc
            except Exception as ex:  # noqa: BLE001
                print("FAILED", m, s["name"], repr(ex)[:200])
        res[m]["_time"] = (time.time() - t0) / max(len(subs), 1)
        res_f.write_text(json.dumps(res, indent=1))
        show(res, [m])
    print()
    show(res)


def show(res, only=None):
    print(f"{'method':46s} {'set':3s} " + rs.HEADER + "  sigma   s")
    for m, r in res.items():
        if only and m not in only:
            continue
        for tag in ("S", "O"):
            rows = [v for k, v in r.items() if k.startswith(tag)]
            if not rows:
                continue
            avg = {k: float(np.mean([x[k] for x in rows])) for k in rs.REGIONS}
            sg = np.mean([x.get("sigma", 0.0) for x in rows])
            print(f"{m[:46]:46s} {tag:3s} " + rs.row(avg) + f"  {sg:5.2f} {r.get('_time', 0):4.1f}")


if __name__ == "__main__":
    main()
