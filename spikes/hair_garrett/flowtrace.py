"""flowtrace.py <model> <out.json> [views=0,1,2] [bin=6]: the photo's STRAND FLOW traced through the fitted cameras onto the
scalp (successor 18, 2026-10-16), for groom.loose.comb_trace, and ours compared at the same scalp points.

Per fitted view: the hair's orientation field (structure tensor, texmeas.orient s=6) and streamlines along it (lenmeas:
followed while inside the hair, coherent and the smoothed L* stays correlated). Each seed (8 px grid) is cast onto the hair
shell (hair_read.onto_scalp at `height` 8 mm) together with a point 8 px along its strand: the 3D strand direction, laid
in the scalp's tangent plane. Strands are axial: the sign is the one toward the region's fall (top / front / crown: back;
sides: back-and-down; back / nape: down). The streamline's length (image px x mm a px) is the VISIBLE RUN in mm (a lower
bound of the lock's laid length). Seeds are binned by (az, el) (`bin` deg): coherence-weighted mean direction, median run.
Ours: the model's built locks (spec["hair"]["locks"]): each root's direction 6-20 mm along, laid in the scalp, and the
angle to the traced direction of the nearest bin within 1.5 bins; printed per region (median angle, back / down shares).
"""
import json
import sys

import numpy as np
from scipy import ndimage as nd
from skimage.color import rgb2lab

from hifipushie import hair, hair_read as hr, store
from texmeas import orient

FALL = {"top": (0, 1, -0.15), "front": (0, 1, -0.15), "crown": (0, 1, -0.3), "sides": (0, 0.7, -0.7),
        "back": (0, 0.15, -1), "nape": (0, 0.05, -1)}


def runs(band, mask, th, coh, seeds, smax=400):
    """streamline length (px, both ways) from each seed (y, x)."""
    h, w = band.shape
    c2, s2 = np.cos(2 * th), np.sin(2 * th)
    sd = band[mask].std() + 1e-9
    out = []
    for y0, x0 in seeds:
        v0, tot = band[y0, x0], 0
        for sgn in (1, -1):
            y, x = float(y0), float(x0)
            t = 0.5 * np.arctan2(s2[y0, x0], c2[y0, x0])
            dx, dy = sgn * np.cos(t), sgn * np.sin(t)
            n, dev = 0, 0.0
            while n < smax:
                iy, ix = int(round(y)), int(round(x))
                t = 0.5 * np.arctan2(s2[iy, ix], c2[iy, ix])
                nx_, ny_ = np.cos(t), np.sin(t)
                if nx_ * dx + ny_ * dy < 0:
                    nx_, ny_ = -nx_, -ny_
                dx, dy = nx_, ny_
                x += dx
                y += dy
                n += 1
                iy, ix = int(round(y)), int(round(x))
                if not (0 <= iy < h and 0 <= ix < w) or not mask[iy, ix] or coh[iy, ix] < 0.25:
                    break
                dev = 0.9 * dev + 0.1 * abs(band[iy, ix] - v0) / sd
                if dev > 0.8:
                    break
            tot += n
        out.append(tot)
    return np.asarray(out, float)


def trace_view(sc, f, height=0.008, grid=8, along=8.0):
    a = np.asarray(f["image"], float)[..., :3] / 255
    L = rgb2lab(a)[..., 0]
    mm = float(f["mm"])
    hm = nd.binary_erosion(np.asarray(f["hair"], float) > 0.5, iterations=max(1, int(round(3.0 / mm))))
    th, coh = orient(L, 6)
    ys, xs = np.mgrid[grid:L.shape[0] - grid:grid, grid:L.shape[1] - grid:grid]
    k = hm[ys, xs] & (coh[ys, xs] > 0.3)
    ys, xs = ys[k], xs[k]
    t = th[ys, xs]
    uv0 = np.stack([xs, ys], 1).astype(float)
    uv1 = uv0 + along * np.stack([np.cos(t), np.sin(t)], 1)  # (x = column, y = row down: orient's frame)
    P0, h0, _ = hr.onto_scalp(sc, f["cam"], uv0, height=height, step=0.0015)
    P1, h1, _ = hr.onto_scalp(sc, f["cam"], uv1, height=height, step=0.0015)
    ok = h0 & h1
    az, el, _ = sc.coords(P0[ok])
    nrm = sc.normal(az, el)
    d = P1[ok] - P0[ok]
    d = d - (d * nrm).sum(1, keepdims=True) * nrm
    nd_ = np.linalg.norm(d, axis=1)
    reg = hr.region_name(az, el)
    pri = np.array([FALL[str(r)] for r in reg], float)
    d = d / np.maximum(nd_, 1e-9)[:, None]
    d = d * np.sign((d * pri).sum(1) + 1e-9)[:, None]
    band = nd.gaussian_filter(L, 2)
    seeds = list(zip(ys[ok], xs[ok]))
    run = runs(band, hm, th, coh, seeds) * mm
    good = nd_ > 1e-4
    return dict(az=az[good], el=el[good], d=d[good], run=run[good], coh=coh[ys[ok], xs[ok]][good], reg=reg[good])


def binned(S, b):
    key = {}
    for i in range(len(S["az"])):
        kk = (int(np.floor(((S["az"][i] + 180) % 360 - 180) / b)), int(np.floor(S["el"][i] / b)))
        key.setdefault(kk, []).append(i)
    out = []
    for (ka, ke), ix in key.items():
        if len(ix) < 4:
            continue
        ix = np.asarray(ix)
        w = S["coh"][ix]
        d = (S["d"][ix] * w[:, None]).sum(0)
        nrm_ = np.linalg.norm(d)
        if nrm_ < 0.3 * w.sum():  # (directions disagree: not a flow)
            continue
        d = d / nrm_
        out.append([round((ka + 0.5) * b % 360, 2), round((ke + 0.5) * b, 2), *[round(float(v), 4) for v in d],
                    round(float(np.median(S["run"][ix])), 1), int(len(ix))])
    return out


def ours(m, spec, sc, samples, b):
    locks = {i: lk for i, lk in enumerate(hair.job(m, spec)["locks"])}
    A = np.asarray([[s[0], s[1]] for s in samples], float)
    D = np.asarray([s[2:5] for s in samples], float)
    rows = []
    for lk in locks.values():
        P = np.asarray(lk.get("pts") or [], float)
        if len(P) < 3:
            continue
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
        if s[-1] < 0.02:
            continue
        q0 = np.array([np.interp(0.006, s, P[:, c]) for c in range(3)])
        q1 = np.array([np.interp(0.02, s, P[:, c]) for c in range(3)])
        az, el, _ = sc.coords(P[:1])
        n = sc.normal(az, el)[0]
        d = q1 - q0
        d = d - d.dot(n) * n
        if np.linalg.norm(d) < 1e-5:
            continue
        d /= np.linalg.norm(d)
        da = np.abs(((A[:, 0] - az[0] + 180) % 360) - 180) * np.cos(np.radians(el[0]))
        dist = np.hypot(da, A[:, 1] - el[0])
        j = int(np.argmin(dist))
        if dist[j] > 1.5 * b:
            continue
        ang = np.degrees(np.arccos(np.clip(d.dot(D[j]), -1, 1)))
        rows.append((str(hr.region_name(az, el)[0]), ang, d, D[j], s[-1] * 1000))
    return rows


def main(m, out, views=(0, 1, 2), b=6.0):
    spec = store.load(m)
    sc = hair.scalp(m, spec)
    S = {}
    for f in hr.frames(m, spec, views=list(views)):
        t = trace_view(sc, f)
        print(f"view {f['i']}: {len(t['az'])} seeds, run median {np.median(t['run']):.1f} mm", flush=True)
        for k, v in t.items():
            S[k] = np.concatenate([S[k], v]) if k in S else v
    smp = binned(S, b)
    print("PHOTO by region: n bins, visible run mm (median, p75), mean direction (back y, down -z)")
    for r in ("front", "top", "crown", "sides", "back", "nape"):
        k = S["reg"] == r
        if k.sum() < 10:
            continue
        d = S["d"][k].mean(0)
        print(f"  {r:6s} seeds {k.sum():5d} run {np.median(S['run'][k]):5.1f} / {np.percentile(S['run'][k], 75):5.1f} mm  "
              f"dir x {d[0]:+.2f} back {d[1]:+.2f} up {d[2]:+.2f}")
    R = ours(m, spec, sc, smp, b)
    print(f"OURS {m} vs photo flow: angle (deg) median / p75, our dir mean | photo dir mean, our lock length mm")
    for r in ("front", "top", "crown", "sides", "back", "nape"):
        rr = [x for x in R if x[0] == r]
        if not rr:
            continue
        a = np.array([x[1] for x in rr])
        do = np.mean([x[2] for x in rr], 0)
        dp = np.mean([x[3] for x in rr], 0)
        print(f"  {r:6s} n {len(rr):4d} angle {np.median(a):5.1f} / {np.percentile(a, 75):5.1f}  ours [{do[0]:+.2f} {do[1]:+.2f} "
              f"{do[2]:+.2f}] photo [{dp[0]:+.2f} {dp[1]:+.2f} {dp[2]:+.2f}] len {np.median([x[4] for x in rr]):.0f}")
    a = np.array([x[1] for x in R]) if R else np.array([np.nan])
    print(f"FLOW angle all: median {np.median(a):.1f} p75 {np.percentile(a, 75):.1f} (n {len(R)})")
    json.dump({"model": m, "bin": b, "samples": smp,
               "fields": "az, el, x, y, z (laid comb direction, world), visible run mm, seeds"}, open(out, "w"))
    print("WROTE", out, len(smp))


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if "=" not in x]
    kw = dict(x.split("=", 1) for x in sys.argv[1:] if "=" in x)
    main(a[0], a[1], tuple(int(v) for v in kw.get("views", "0,1,2").split(",")), float(kw.get("bin", 6)))
