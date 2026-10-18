"""laycal.py: calibrate the strand LAY measures (2026-10-16, hair-garrett successor 7).

  laycal.py synth [outdir]        synthetic strand patches at KNOWN image angles (15 / 30 / 60 / 85 deg; long strands,
                                  short dense dashes, clumped locks, isotropic dashes, dots = strands seen end-on), each
                                  measured by texmeas's `lay` and the candidate measures below
  laycal.py geo <model> [...]     the lock curves projected through the FITTED review cameras into the gate crops
                                  (direction 3q / profile top-front, hairline front), front-most strands only (z-buffer):
                                  the true image angle of what the render shows, from geometry

Measures (all axial, deg to the image horizontal, 0 = lying across the image, 90 = vertical):
  lay   texmeas: coherence-weighted mean of |angle| per pixel (structure tensor at 4 px)
  flow  doubled-angle orientation averaged in 48 px windows; |angle| of each window's resultant, weighted by the
        resultant length (isotropic windows: ~0 weight). Follows curved flows, ignores dash noise.
  R     mean resultant length of those windows (0 = no common direction, 1 = all parallel)"""
import json
import sys

import numpy as np
from scipy import ndimage as nd

import texmeas

SS = 3  # supersampling of the synthetic patches
import os
HEADOCC = os.environ.get("LAYCAL_HEADOCC", "1") == "1"  # head z-buffer occlusion (successor 17); 0 = the old normal test


def flow(L, m, s=4, win=48):
    gx = nd.gaussian_filter(L, 1, order=(0, 1)); gy = nd.gaussian_filter(L, 1, order=(1, 0))
    jxx = nd.gaussian_filter(gx * gx, s); jyy = nd.gaussian_filter(gy * gy, s); jxy = nd.gaussian_filter(gx * gy, s)
    tr = jxx + jyy + 1e-9
    z = ((jxx - jyy) + 2j * jxy) / tr  # doubled gradient angle, magnitude = coherence
    mf = m.astype(float)
    zr = nd.uniform_filter(z.real * mf, win) + 1j * nd.uniform_filter(z.imag * mf, win)
    cnt = nd.uniform_filter(mf, win) + 1e-9
    zr = zr / cnt
    th = 0.5 * np.angle(zr) + np.pi / 2  # strand direction = across the gradient
    R = np.abs(zr)
    ang = np.degrees(np.abs(np.arcsin(np.abs(np.sin(th)))))
    k = m & (cnt > 0.6)
    w = R[k]
    return float((ang[k] * w).sum() / max(w.sum(), 1e-9)), float(R[k].mean())


def measure(L, C):
    m = texmeas.hairmask(L, C)
    th, coh = texmeas.orient(L)
    w = coh[m]
    lay = float((np.degrees(np.abs(np.arcsin(np.abs(np.sin(th[m]))))) * w).sum() / w.sum())
    f, R = flow(L, m)
    return dict(lay=lay, flow=f, R=R, coh=float(coh[m].mean()), npx=int(m.sum()))


# ---------------------------------------------------------------------------------------------------- synthetic
def patch(angle, kind, rng, N=520):
    """A grey strand patch (L*, chroma) at a known image angle: strands as anti-aliased polylines drawn at SS x."""
    from PIL import Image, ImageDraw
    S = N * SS
    im = Image.new("L", (S, S), 70)
    d = ImageDraw.Draw(im)
    a0 = np.radians(angle)
    if kind == "long":
        n, ln, spread, curl, wid = 2600, (90, 200), 6, 0.004, 1.4
    elif kind == "dash":
        n, ln, spread, curl, wid = 22000, (8, 16), 6, 0.0, 1.4
    elif kind == "clump":  # locks: strands share a lock's direction, locks differ by 15 deg
        n, ln, spread, curl, wid = 2600, (60, 140), 2, 0.002, 1.2
    elif kind == "iso":
        n, ln, spread, curl, wid = 22000, (8, 16), 180, 0.0, 1.4
    elif kind == "dots":  # strands seen end-on (standing at the camera): blobs 1-3 px with a short random tail
        n, ln, spread, curl, wid = 30000, (1, 4), 180, 0.0, 2.0
    locks = rng.uniform(-15, 15, 400)
    for i in range(n):
        a = a0 + np.radians(rng.normal(0, spread) if spread < 90 else rng.uniform(0, 180))
        if kind == "clump":
            a = a0 + np.radians(locks[i % 400] + rng.normal(0, spread))
        L = rng.uniform(*ln) * SS
        p = rng.uniform(-0.2, 1.2, 2) * S
        pts = [tuple(p)]
        k = rng.normal(0, curl)
        for t in range(12):
            a += k * L / 12 / SS
            p = p + L / 12 * np.array([np.cos(a), -np.sin(a)])
            pts.append(tuple(p))
        d.line(pts, fill=int(np.clip(rng.normal(120, 35), 30, 220)), width=max(1, int(wid * SS)))
    g = np.asarray(im.resize((N, N), Image.LANCZOS), float) / 255 * 100
    g = nd.gaussian_filter(g, 0.5)
    return g, np.zeros_like(g)


def synth(out=None):
    rng = np.random.default_rng(0)
    rows = []
    for kind in ("long", "clump", "dash", "iso", "dots"):
        for ang in ((15, 30, 60, 85) if kind not in ("iso", "dots") else (0,)):
            L, C = patch(ang, kind, rng)
            r = measure(L, C)
            rows.append((kind, ang, r))
            print(f"{kind:6s} true {ang:3d}  lay {r['lay']:5.1f}  flow {r['flow']:5.1f}  R {r['R']:.2f}  coh {r['coh']:.2f}",
                  flush=True)
            if out:
                from PIL import Image
                Image.fromarray(np.clip(L * 2.55, 0, 255).astype(np.uint8)).save(f"{out}/syn_{kind}_{ang}.png")
    return rows


# ---------------------------------------------------------------------------------------------------- geometry
CROPS = {"direction__three_quarter__top_front": ("v1", 30.0, 60.0, 85.0),
         "direction__profile__top_front": ("v2", 45.0, 58.0, 85.0),
         "hairline__front": ("v0", 0.0, 38.0, 95.0)}


def geo(m):
    import copy
    from hifipushie import hair, hair_loose as hl, hair_read as hr, humanfit, store
    spec = store.load(m)
    sc = hair.scalp(m, spec)
    col = hl.collider(m, spec, sc)
    g = hair.fit_to_head(copy.deepcopy(hair.groom_params(spec)), sc)
    line = hair.hairline(sc, g)
    locks = hl.grow(sc, g, line, np.random.default_rng(int(g.get("seed", 0))), col)
    P = [np.asarray(lk["pts"], float) + sc.C for lk in locks.values()]
    A = np.concatenate([p[:-1] for p in P]); B = np.concatenate([p[1:] for p in P])
    refs = json.loads((store.HOME / m / "human_refs.json").read_text())
    res = {}
    for name, (v, az, el, mm) in CROPS.items():
        cam = refs["cameras"][int(v[1:])]
        uv = humanfit.project(cam, sc.point(np.array([az]), np.array([el]), 0.01))[0]
        eye, R = hr.cam_eye(cam)
        s = mm / 1000.0 * cam["f"] / np.linalg.norm(sc.C - eye)
        ua, ub = humanfit.project(cam, A), humanfit.project(cam, B)
        M = (A + B) / 2
        depth = (M - eye) @ R[2]
        x0, y0 = uv - s / 2
        q = ((ua + ub) / 2 - [x0, y0]) / s * 520  # crop pixels (520 px tiles)
        inb = (q[:, 0] >= 0) & (q[:, 0] < 520) & (q[:, 1] >= 0) & (q[:, 1] < 520)
        # z-buffer on 4 px cells: front-most strand depth; keep segments within 2 mm of it (the visible layer)
        cell = (q[inb] // 4).astype(int)
        key = cell[:, 0] * 200 + cell[:, 1]
        zb = np.full(200 * 200, np.inf)
        np.minimum.at(zb, key, depth[inb])
        vis = np.zeros(len(A), bool)
        vis[np.where(inb)[0]] = depth[inb] < zb[key] + 0.002
        d = (ub - ua)[vis] / s * 520
        lpx = np.hypot(d[:, 0], d[:, 1])
        ang = np.degrees(np.arctan2(np.abs(d[:, 1]), np.abs(d[:, 0])))
        mean = float((ang * lpx).sum() / lpx.sum())
        z = (lpx * np.exp(2j * np.arctan2(d[:, 1], d[:, 0])))
        # windowed resultant, as `flow`: 48 px windows of the crop
        wk = (q[vis] // 48).astype(int)
        wkey = wk[:, 0] * 20 + wk[:, 1]
        zs = np.bincount(wkey, z.real, 400) + 1j * np.bincount(wkey, z.imag, 400)
        ls = np.bincount(wkey, lpx, 400)
        ok = ls > 0
        Rw = np.abs(zs[ok]) / ls[ok]
        aw = np.degrees(np.abs(np.arcsin(np.abs(np.sin(np.angle(zs[ok]) / 2)))))
        fl = float((aw * Rw).sum() / Rw.sum())
        res[name] = dict(segs=int(vis.sum()), mean=mean, flow=fl, R=float(Rw.mean()), px=float(np.median(lpx)))
        print(f"{tag:10s} {name[:24]:24s} {time.time() - t0:4.0f}s visible segs {vis.sum():6d}  mean|ang| {mean:5.1f}  flow {fl:5.1f}  R {Rw.mean():.2f}"
              f"  seg px {np.median(lpx):.1f}", flush=True)
    return res


def strands(m, count=120000, out=None, patch=None):
    """The model's EVALUATED strands (Blender geometry, no render; hair.job + hair_strands.strands_of_model), projected
    through the review cameras: per crop the front-most strand segments' image angle (all / per object), and a FLAT
    raster of them (anti-aliased lines, per-strand grey) measured by texmeas: lay of the geometry as the measure sees it."""
    from PIL import Image, ImageDraw
    from hifipushie import hair, hair_read as hr, hair_strands as hs, humanfit, store
    import copy, time
    from laygeo import merge
    spec = store.load(m)
    tag = m
    if patch:  # {"groom": ..., "strands": ...} deep-merged into spec["hair"] in memory (nothing saved)
        spec = copy.deepcopy(spec); merge(spec["hair"], json.load(open(patch)))
        tag = m + ":" + patch.rsplit("/", 1)[-1].replace(".json", "")
    t0 = time.time()
    if not count:  # (successor 17) the render's own count: at 120k the under layers show through and the profile read ~10 deg low
        count = int((spec["hair"].get("strands") or {}).get("count", 120000))
    sd = hair.job(m, spec, count=count)["strands"]
    D = hs.strands_of_model(sd)
    sc = hair.scalp(m, spec)
    pts, cnt, obj, names = D["pts"].astype(float), D["counts"], D["obj"], list(D["names"])
    first = np.r_[0, np.cumsum(cnt)[:-1]]
    sid = np.repeat(np.arange(len(cnt)), cnt)
    ok = np.ones(len(pts), bool); ok[first + cnt - 1] = False  # segment i -> i+1 within a strand
    ia = np.where(ok)[0]; ib = ia + 1
    A, B, S_ = pts[ia], pts[ib], sid[ia]
    refs = json.loads((store.HOME / m / "human_refs.json").read_text())
    if HEADOCC:
        A_, E_ = np.meshgrid(np.arange(0, 360, 0.25), np.arange(-60, 90, 0.25))
        HS = sc.point(A_.ravel(), E_.ravel(), 0.0)
    rng = np.random.default_rng(1)
    shade = rng.normal(120, 35, len(cnt)).clip(30, 220)
    res = {}
    for name, (v, az, el, mm) in CROPS.items():
        cam = refs["cameras"][int(v[1:])]
        uv = humanfit.project(cam, sc.point(np.array([az]), np.array([el]), 0.01))[0]
        eye, R = hr.cam_eye(cam)
        s = mm / 1000.0 * cam["f"] / np.linalg.norm(sc.C - eye)
        x0, y0 = uv - s / 2
        qa = (humanfit.project(cam, A) - [x0, y0]) / s * 520
        qb = (humanfit.project(cam, B) - [x0, y0]) / s * 520
        q = (qa + qb) / 2
        depth = ((A + B) / 2 - eye) @ R[2]
        inb = (q[:, 0] >= 0) & (q[:, 0] < 520) & (q[:, 1] >= 0) & (q[:, 1] < 520)
        # head occlusion (successor 17): a z-buffer of the HEAD surface (sc.point grid, el -60..90, as screen.Flat) on
        # 2 px crop cells; a segment shows only if its midpoint is not behind it. The old test (the segment's scalp
        # normal faces the camera) let the far side's hairline strands print over the forehead in the profile crop
        # (screen 35 vs render 45).
        if HEADOCC:
            hq = (humanfit.project(cam, HS) - [x0, y0]) / s * 520
            hz = (HS - eye) @ R[2]
            hc = (hq // 2).astype(int)
            hk = (hc[:, 0] >= 0) & (hc[:, 0] < 260) & (hc[:, 1] >= 0) & (hc[:, 1] < 260)
            zh = np.full((260, 260), np.inf)
            np.minimum.at(zh, (hc[hk, 1], hc[hk, 0]), hz[hk])
            hm = nd.binary_fill_holes(nd.binary_closing(np.isfinite(zh), iterations=2))
            zf = nd.minimum_filter(np.where(np.isfinite(zh), zh, 1e9), 3)
            zh = np.where(hm, np.where(np.isfinite(zh), zh, zf), np.inf)
            qc = np.clip((q // 2).astype(int), 0, 259)
            inb &= depth < zh[qc[:, 1], qc[:, 0]] + 0.0005
        else:
            nrm = (A + B) / 2 - sc.C; nrm /= np.linalg.norm(nrm, axis=1)[:, None]
            inb &= ((eye - (A + B) / 2) * nrm).sum(1) > 0
        cell = (q[inb] // 2).astype(int); key = cell[:, 0] * 300 + cell[:, 1]
        zb = np.full(300 * 300, np.inf); np.minimum.at(zb, key, depth[inb])
        vis = np.zeros(len(A), bool); vis[np.where(inb)[0]] = depth[inb] < zb[key] + 0.0015
        d = (qb - qa)[vis]; lpx = np.hypot(d[:, 0], d[:, 1])
        ang = np.degrees(np.arctan2(np.abs(d[:, 1]), np.abs(d[:, 0])))
        mean = float((ang * lpx).sum() / max(lpx.sum(), 1e-9))
        per = {}
        for oi, on in enumerate(names):
            k = obj[S_[vis]] == oi
            if k.sum() > 50:
                per[on] = (int(k.sum()), float((ang[k] * lpx[k]).sum() / lpx[k].sum()))
        # per scalp REGION (hair_read.region_name of the segment's point): which part of the groom makes the crop's lay
        az_, el_, _ = sc.coords((A[vis] + B[vis]) / 2)
        rg = hr.region_name(az_, el_)
        per_reg = {}
        for rn in np.unique(rg):
            k = rg == rn
            if lpx[k].sum() > 0 and k.sum() > 50:
                per_reg[str(rn)] = (round(float(lpx[k].sum() / lpx.sum()), 2), round(float((ang[k] * lpx[k]).sum() / lpx[k].sum()), 1))
        # (kept apart from per: res["region"])
        # flat raster of every in-box segment, back to front (painter's), 3x supersampled
        im = Image.new("L", (520 * SS, 520 * SS), 225); dr = ImageDraw.Draw(im)
        bi = np.where(inb)[0]; bi = bi[np.argsort(-depth[bi])]
        for i in bi:
            dr.line([tuple(qa[i] * SS), tuple(qb[i] * SS)], fill=int(shade[S_[i]]), width=SS)
        g = np.asarray(im.resize((520, 520), Image.LANCZOS), float) / 255 * 100
        r = measure(g, np.zeros_like(g))
        if out:
            Image.fromarray(np.clip(g * 2.55, 0, 255).astype(np.uint8)).save(f"{out}/flat_{tag.replace(':', '_')}_{name}.png")
        res[name] = dict(geo=mean, raster=r, per=per, region=per_reg)
        print(f"{tag:10s} {name[:24]:24s} {time.time() - t0:4.0f}s vis {vis.sum():7d} geo mean|ang| {mean:5.1f} | flat raster: lay {r['lay']:5.1f} "
              f"flow {r['flow']:5.1f} R {r['R']:.2f} coh {r['coh']:.2f} | per object "
              + ", ".join(f"{k} {n} {a:.0f}" for k, (n, a) in per.items())
              + " | by region (share, deg) " + ", ".join(f"{k} {w} {a}" for k, (w, a) in per_reg.items()), flush=True)
    return res


if __name__ == "__main__":
    if sys.argv[1] == "synth":
        synth(sys.argv[2] if len(sys.argv) > 2 else None)
    elif sys.argv[1] == "strands":
        for pf in sys.argv[5:] or [None]:
            strands(sys.argv[2], int(sys.argv[3]), sys.argv[4], pf)
    else:
        for m in sys.argv[2:]:
            geo(m)
