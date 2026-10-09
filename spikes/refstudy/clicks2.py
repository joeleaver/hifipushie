"""The click test as a measurement (round 2): several placers per picture, a zoomed refine round, per-point bias
and scatter, bias calibration held out by picture, and the fit rows with the REAL placed points.
  run.sh clicks2.py zoom <subject> <first-pass answers.json> <out tag>     -> D/clicks/<subject>_<tag>_zoom.png
  run.sh clicks2.py score                                                  -> reads D/clicks/runs.json
runs.json: [{"subject", "placer", "pass1": answers.json, "zoom": refined.json | null, "zoom_from": tag}]"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

import clicks
import exp2
import fitlib
import rs
import subjects
import table as tb
from hifipushie import humanmacro as hm

OUT = clicks.OUT
HALF, ZS = 24, 6   # a zoom tile shows +-24 picture pixels at 6x


def to_px(s, ans):
    box = clicks.crop_box(s)
    return {k: np.array(v, float) / clicks.SCALE + box[:2] for k, v in ans.items() if k in clicks.POINTS}


def zoom(name, ans_f, tag):
    s = subjects.load(name)
    P = to_px(s, json.load(open(ans_f)))
    img = Image.fromarray(subjects.image(name, "front"))
    T = 2 * HALF * ZS
    cols = 6
    names = list(P)
    rows = (len(names) + cols - 1) // cols
    W = Image.new("RGB", (cols * (T + 8), rows * (T + 30)), (255, 255, 255))
    meta = {}
    for i, k in enumerate(names):
        c = np.round(P[k]).astype(int)
        t = img.crop((c[0] - HALF, c[1] - HALF, c[0] + HALF, c[1] + HALF)).resize((T, T), Image.LANCZOS)
        d = ImageDraw.Draw(t)
        for g in range(0, T + 1, 24):
            col = (60, 120, 255) if g % 48 == 0 else (170, 200, 255)
            d.line([(g, 0), (g, T)], fill=col)
            d.line([(0, g), (T, g)], fill=col)
            if g % 48 == 0 and g < T:
                d.text((g + 2, 1), str(g), fill=(0, 0, 200))
                d.text((1, g + 2), str(g), fill=(0, 0, 200))
        x0, y0 = (i % cols) * (T + 8), (i // cols) * (T + 30)
        W.paste(t, (x0, y0 + 26))
        ImageDraw.Draw(W).text((x0 + 4, y0 + 6), f"{k}: {clicks.POINTS[k][1][:58]}", fill=(0, 0, 0))
        meta[k] = [int(c[0] - HALF), int(c[1] - HALF)]
    W.save(OUT / f"{name}_{tag}_zoom.png")
    (OUT / f"{name}_{tag}_zoom.json").write_text(json.dumps(meta))
    print(OUT / f"{name}_{tag}_zoom.png", W.size)


def refined_px(name, tag, ans):
    meta = json.loads((OUT / f"{name}_{tag}_zoom.json").read_text())
    return {k: np.array(meta[k], float) + np.array(v, float) / ZS for k, v in ans.items() if k in meta}


def score():
    runs = json.loads((OUT / "runs.json").read_text())
    rec = []   # (subject, placer, stage, point, err vector mm in the picture: x right, y down)
    clicks_px = {}
    for r in runs:
        s = subjects.load(r["subject"])
        cam, V = tb.view_true(s, "front")
        Lp = rs.humanfit.project(cam, rs.landmarks(V))
        mmpx = cam["t"][2] / cam["f"] * 1000
        P1 = to_px(s, json.load(open(r["pass1"])))
        stages = [("pass1", P1)]
        if r.get("zoom"):
            stages.append(("zoom", refined_px(r["subject"], r["zoom_from"], json.load(open(r["zoom"])))))
        for st, P in stages:
            for k, q in P.items():
                rec.append((r["subject"], r["placer"], st, k, (q - Lp[clicks.POINTS[k][0]]) * mmpx))
            clicks_px[(r["subject"], r["placer"], st)] = P
    names = list(clicks.POINTS)

    def table_for(stage, sel=lambda r: True):
        E = {k: np.array([e for (su, pl, st, kk, e) in rec if st == stage and kk == k and sel((su, pl))]) for k in names}
        return {k: v for k, v in E.items() if len(v)}
    for stage in ("pass1", "zoom"):
        E = table_for(stage)
        if not E:
            continue
        n = max(len(v) for v in E.values())
        print(f"\n{stage}: {n} placements per point. bias (mean dx, dy mm; x = picture right, y = down), scatter sd about the bias, rms")
        allv = np.concatenate(list(E.values()))
        for k, v in E.items():
            b, sd = v.mean(0), np.sqrt(((v - v.mean(0)) ** 2).sum(1).mean())
            print(f"  {k:16s} bias {b[0]:+5.1f} {b[1]:+5.1f}   scatter {sd:4.1f}   rms {np.sqrt((v ** 2).sum(1).mean()):4.1f}")
        d = np.linalg.norm(allv, axis=1)
        print(f"  ALL: median {np.median(d):.2f} mm, mean {d.mean():.2f}, p90 {np.percentile(d, 90):.2f}")
    # repeatability: the same picture, different placers (pass 1)
    for su in sorted({r["subject"] for r in runs}):
        pls = [r["placer"] for r in runs if r["subject"] == su]
        if len(pls) < 2:
            continue
        D = []
        for k in names:
            pts = [clicks_px[(su, p, "pass1")][k] for p in pls if k in clicks_px[(su, p, "pass1")]]
            if len(pts) > 1:
                pts = np.array(pts)
                s = subjects.load(su)
                mmpx = s["views"]["front"]["cam"]["t"][2] / s["views"]["front"]["cam"]["f"] * 1000
                D.append(np.sqrt(((pts - pts.mean(0)) ** 2).sum(1).mean()) * mmpx)
        print(f"repeatability on {su}: {len(pls)} placers, sd between placers per point median {np.median(D):.2f} mm, max {np.max(D):.2f}")
    # bias calibration held out by picture, then the fits with the real points
    res = {}
    subs = sorted({r["subject"] for r in runs})
    for su in subs:
        s = subjects.load(su)
        cam, V = tb.view_true(s, "front")
        mmpx = cam["t"][2] / cam["f"] * 1000
        E = table_for("pass1", lambda sp: sp[0] != su)   # the other pictures' errors
        bias = {k: v.mean(0) for k, v in E.items()}
        sig = {k: max(float(np.sqrt(((v - v.mean(0)) ** 2).sum(1).mean())), 0.8) for k, v in E.items()}
        raw = {k: max(float(np.sqrt((v ** 2).sum(1).mean())), 0.8) for k, v in E.items()}
        pl = [r["placer"] for r in runs if r["subject"] == su][0]
        P = clicks_px[(su, pl, "pass1")]
        ks = [k for k in P if k in bias]
        ids = np.array([clicks.POINTS[k][0] for k in ks])
        Lp = rs.humanfit.project(cam, rs.landmarks(V))
        uv_raw = np.array([P[k] for k in ks])
        uv_cal = np.array([P[k] - bias[k] / mmpx for k in ks])
        e_raw = np.linalg.norm(uv_raw - Lp[ids], axis=1) * mmpx
        e_cal = np.linalg.norm(uv_cal - Lp[ids], axis=1) * mmpx
        print(f"{su}: placed points off by median {np.median(e_raw):.2f} mm (mean {e_raw.mean():.2f}); after taking out the other pictures' "
              f"per-point bias: median {np.median(e_cal):.2f} (mean {e_cal.mean():.2f})")
        det = exp2.ev(s, ["front"])
        rd = hm.prior_rows(exp2.reader(s))
        mk = lambda uv, sg: {"pts": fitlib.points_lm(ids), "uv": uv, "sig": np.array([sg[k] for k in ks]), "size": cam["size"], "yaw": 0.0}  # noqa: E731
        for tag, fn in (("front: detector MAP", lambda: fitlib.fit(det, robust=True)),
                        ("front: detector + read", lambda: fitlib.fit(det, robust=True, rows=rd)),
                        ("front: detector + placed (raw, own rms as sigma)", lambda: fitlib.fit(det + [mk(uv_raw, raw)], robust=True)),
                        ("front: detector + placed (bias out, scatter as sigma)", lambda: fitlib.fit(det + [mk(uv_cal, sig)], robust=True)),
                        ("front: det + placed (bias out) + read", lambda: fitlib.fit(det + [mk(uv_cal, sig)], robust=True, rows=rd)),
                        ("front: placed (bias out) alone", lambda: fitlib.fit([mk(uv_cal, sig)]))):
            res.setdefault(tag, {})[su] = rs.score(rs.head(fn()["c"]), s["V"])
    print()
    tb.show(res)


if __name__ == "__main__":
    if sys.argv[1] == "zoom":
        zoom(*sys.argv[2:5])
    else:
        score()
