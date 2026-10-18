"""screen.py <model> <outdir> [patch.json ...] [lay=1] [count=0]: the PRE-RENDER screen of a groom (no Blender render).
The model's EVALUATED strands (hair.job + hair_strands.strands_of_model, as laycal strands) drawn as a FLAT raster
through the same cameras the gate renders use, and the gate's geometry rows measured on it with the gate's own code:
  standoff_<region>  hair_read.hairness / outline_rays on a flat image (backdrop, skull, strands as optical density)
                     through the fitted views 0, 1, 2, median over views (as hair_read.summarise)
  hairline_*         the hair / skin boundary of the flat image cast onto the scalp (hlinetrace's code) vs the photos'
                     traced line, per |az| bin, view 0 (+ views 1, 2 printed): hairline_centre = bins 0-20, temple_corners
                     = 30-50; M-shape = (centre - temple) ours vs photo; sideburn = profile view bins 70-90
  coverage_*         hcover's magenta test on a flat ID raster (scalp inside the hairline magenta, strands' transmittance
                     over it, 2x supersampled as size=1024 ss=2): t60 = above, y180 = behind
  lay_top            laycal.strands (lay=1; the spec's render strand count: 120k read the profile ~10 deg low)
Strands at the render's count (count=0: the groom's own), width max(2 r, one render pixel) (EEVEE draws every strand
at least a pixel wide). Calibrate against renders before trusting a row (docs/notes/hair.md, successor 8)."""
import copy
import json
import os
import sys
import time

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from hifipushie import hair, hair_read as hr, hair_strands as hs, humanfit, store
from laygeo import merge

HAIR_RGB = np.array([62.0, 52.0, 44.0])
SKIN_RGB = np.array([196.0, 150.0, 128.0])
BG = 0.86 * 255
HL_BIAS = 1.9
AREA = {"t60": 325000.0, "y180": 386000.0}
F = 4.0 / 3.0  # raster px a picture px: the gate renders are 1024 squares over the picture's 1536 px, ss=2


def rot(kind, deg):
    a = np.radians(deg)
    if kind == "y":  # hgshots.turned: the camera turned deg about z through C
        R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    else:  # hgshots.tipped
        a = -a
        R = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    return R.T  # the world turned the other way under the fixed camera


class Flat:
    def __init__(self, m, spec, D, sc, sd):
        self.m, self.spec, self.sc = m, spec, sc
        lk = sd.get("look") or {}
        self.tint = float(lk.get("scalp_tint", 0.85))
        self.tint_rgb = np.array([int(lk.get("scalp", "#3c3938")[k:k + 2], 16) for k in (1, 3, 5)], float)
        pts, cnt = D["pts"].astype(float), D["counts"]
        first = np.r_[0, np.cumsum(cnt)[:-1]]
        sid = np.repeat(np.arange(len(cnt)), cnt)
        ok = np.ones(len(pts), bool)
        ok[first + cnt - 1] = False
        ia = np.where(ok)[0]
        self.A, self.B = pts[ia], pts[ia + 1]
        self.rad = D["radius"].astype(float)[sid[ia]]
        self.refs = json.loads((store.HOME / m / "human_refs.json").read_text())
        g = hair.fit_to_head(copy.deepcopy(hair.groom_params(spec)), sc)
        self.line = hair.hairline(sc, g)
        A_, E_ = np.meshgrid(np.arange(0, 360, 0.25), np.arange(-60, 90, 0.25))
        self.saz, self.sel = A_.ravel(), E_.ravel()
        self.S = sc.point(self.saz, self.sel, 0.0)
        self.sin = hair.inside(sc, self.line, self.saz, self.sel) > 0
        # the strands job's scalp: its hp_density is the alpha of the root-shadow tint (blender_strands.scalp_object:
        # density x look.scalp_tint over the skin; hcover's magenta = density x 1.0)
        from scipy.spatial import cKDTree
        z = np.load(sd["scalp"])
        V = z["verts"].astype(float)
        if np.linalg.norm(V.mean(0) - sc.C) > 0.05:
            V = V + sc.C
        dd, j = cKDTree(V).query(self.S)
        # (off the scalp mesh, e.g. the forehead, the nearest vertex is its edge's: no tint there)
        self.sdn = np.where(dd < 0.003, z["hp_density"].astype(float)[j], 0.0)
        print(f"scalp mesh: {len(V)} verts, grid points on it {np.mean(dd < 0.003):.2f}", flush=True)

    def raster(self, ci, Rw=None):
        """-> dict: T (strand transmittance over everything, raster px), Ts (over the scalp: strands in front of it),
        head (bool), ins (scalp inside the hairline), size, cam, mm (mm a picture px)."""
        cam = self.refs["cameras"][ci]
        C = self.sc.C
        W, H = cam["size"]
        w, h = int(round(W * F)), int(round(H * F))
        eye, R = hr.cam_eye(cam)

        def tr(P):
            return P if Rw is None else C + (P - C) @ Rw.T

        S = tr(self.S)
        q = humanfit.project(cam, S) * F
        dz = (S - eye) @ R[2]
        # the head's depth on 3 px cells (the 0.25 deg grid is ~0.4 mm apart, a raster px ~0.2 mm: per-pixel it had
        # holes the back of the groom showed through), nearest scalp point per cell, gaps closed, back to pixels
        K = 3
        hc, wc = -(-h // K), -(-w // K)
        qi = np.floor(q / K).astype(int)
        ok = (qi[:, 0] >= 0) & (qi[:, 0] < wc) & (qi[:, 1] >= 0) & (qi[:, 1] < hc)
        o = np.where(ok)[0]
        o = o[np.argsort(-dz[o])]  # far first: the nearest scalp point written last wins
        zc = np.full((hc, wc), np.inf)
        ic = np.full((hc, wc), -1)
        zc[qi[o, 1], qi[o, 0]] = dz[o]
        ic[qi[o, 1], qi[o, 0]] = o
        hm = ndi.binary_fill_holes(ndi.binary_closing(np.isfinite(zc), iterations=2))
        zf = ndi.minimum_filter(np.where(np.isfinite(zc), zc, 1e9), 3)
        zc = np.where(hm, np.where(np.isfinite(zc), zc, zf), np.inf)
        _, (iy, ix) = ndi.distance_transform_edt(ic < 0, return_indices=True)
        ic = np.where(hm, ic[iy, ix], -1)
        yy, xx = np.arange(h) // K, np.arange(w) // K
        zb, idx, head = zc[yy][:, xx], ic[yy][:, xx], hm[yy][:, xx]
        insr = np.zeros((h, w), bool)
        insr[idx >= 0] = self.sin[idx[idx >= 0]]
        insr = ndi.binary_closing(insr, iterations=2) & head
        dn = np.zeros((h, w))
        dn[idx >= 0] = self.sdn[idx[idx >= 0]]
        dn = np.where(head, ndi.grey_closing(dn, 3), 0.0)
        Xc = (C - np.asarray(cam["centre"], float)) @ humanfit._cam_rot(cam).T + np.asarray(cam["t"], float)
        mm = float(Xc[2]) / float(cam["f"]) * 1000.0  # mm a picture px at the head centre
        dens = np.zeros(h * w)
        dens_s = np.zeros(h * w)
        n = len(self.A)
        for k0 in range(0, n, 400000):
            A, B = tr(self.A[k0:k0 + 400000]), tr(self.B[k0:k0 + 400000])
            qa, qb = humanfit.project(cam, A) * F, humanfit.project(cam, B) * F
            L = np.hypot(*(qb - qa).T)
            ns = np.maximum(1, np.ceil(L / 0.5)).astype(int)
            wpx = np.maximum(2 * self.rad[k0:k0 + 400000] * 1000 / mm * F, 1.0)
            seg = np.repeat(np.arange(len(A)), ns)
            t = (np.arange(ns.sum()) - np.repeat(np.cumsum(ns) - ns, ns) + 0.5) / np.repeat(ns, ns)
            p = qa[seg] + (qb - qa)[seg] * t[:, None]
            z = ((A[seg] + (B - A)[seg] * t[:, None]) - eye) @ R[2]
            pi = np.floor(p).astype(int)
            ok = (pi[:, 0] >= 0) & (pi[:, 0] < w) & (pi[:, 1] >= 0) & (pi[:, 1] < h)
            pi, z, seg = pi[ok], z[ok], seg[ok]
            zh = zb[pi[:, 1], pi[:, 0]]
            vis = z < zh + 0.0005  # not behind the head
            wt = (wpx * L / ns)[seg]
            key = pi[:, 1] * w + pi[:, 0]
            dens += np.bincount(key[vis], wt[vis], h * w)
            dens_s += np.bincount(key[vis], wt[vis], h * w)  # (in front of the scalp = not behind it)
        return {"T": np.exp(-dens.reshape(h, w)), "head": head, "ins": insr, "size": (W, H), "cam": cam, "mm": mm,
                "wh": (w, h), "dn": dn}

    def image(self, r, magenta=False):
        T, head = r["T"][..., None], r["head"][..., None]
        a = r["dn"][..., None] * (1.0 if magenta else self.tint)
        col = np.array([255.0, 0, 255]) if magenta else self.tint_rgb
        under = np.where(head, a * col + (1 - a) * SKIN_RGB, BG)
        return T * under + (1 - T) * HAIR_RGB

    def frame(self, ci):
        """A hair_read.frames()-like dict from the flat raster of fitted view ci (picture px)."""
        r = self.raster(ci)
        W, H = r["size"]
        w, h = r["wh"]
        im = Image.fromarray(np.clip(self.image(r), 0, 255).astype(np.uint8))
        # as the gate: a 2048 render (F) averaged to 1024, then render_as_picture back up to the picture's pixels
        im = im.resize((w // 2, h // 2), Image.LANCZOS).resize((W, H), Image.LANCZOS)

        def up(x):
            return np.asarray(Image.fromarray(x.astype(np.float32)).resize((w // 2, h // 2), Image.BILINEAR)
                              .resize((W, H), Image.BILINEAR), float)
        hp = np.clip(up(1 - r["T"] * (1 - r["dn"] * self.tint)), 0, 1)
        headp = up(r["head"].astype(float)) > 0.5
        hpm = hp > 0.5
        skin = (headp & ~hpm).astype(float)
        bg = (~headp & ~hpm).astype(float)
        sk = np.zeros((H, W), bool)
        uv = humanfit.project(r["cam"], self.sc.point(self.saz[::16], self.sel[::16], 0.0))  # (as frames' skull)
        q = np.round(uv).astype(int)
        ok = (q[:, 0] >= 0) & (q[:, 0] < W) & (q[:, 1] >= 0) & (q[:, 1] < H)
        sk[q[ok, 1], q[ok, 0]] = True
        sk = ndi.binary_fill_holes(ndi.binary_closing(sk, iterations=4))
        return {"i": ci, "image": im, "cam": r["cam"], "mm": r["mm"], "c": humanfit.project(r["cam"], self.sc.C[None])[0],
                "hair": hp, "skin": skin, "bg": bg, "skull": sk}


def standoff(sc, f):
    hn = hr.hairness(f["image"], f["hair"], f["bg"], f["mm"])
    o = hr.outline_rays(f["skull"], hn["solid"], hn["a"], f["bg"], f["c"], f["mm"])
    ks = np.nonzero(o["meets"])[0]
    if not len(ks):
        return {}
    th = np.radians(o["ang"][ks])
    uv = np.stack([f["c"][0] + np.sin(th) * o["skull_px"][ks], f["c"][1] - np.cos(th) * o["skull_px"][ks]], 1)
    _, _, G = hr.onto_scalp(sc, f["cam"], uv, step=0.0015)
    az, el, _ = sc.coords(G)
    reg = hr.region_name(az, el)
    return {r: float(np.nanmedian(o["standoff_mm"][ks][reg == r])) for r in hr.REGIONS if (reg == r).sum() >= 3}


def hline(sc, f):
    """hlinetrace's line: (|az|, height z) of the hair / skin boundary cast onto the scalp, front-facing."""
    pts, _ = hr.hairline_pixels(f["hair"], f["skin"], step=2)
    if not len(pts):
        return None
    P, hit, _ = hr.onto_scalp(sc, f["cam"], pts, step=0.001)
    az, el, _ = sc.coords(P)
    eye, _ = hr.cam_eye(f["cam"])
    nn = sc.normal(az, el)
    face = ((eye - P) / np.linalg.norm(eye - P, axis=1, keepdims=True) * nn).sum(1)
    fa = np.abs(((az + 180) % 360) - 180)
    ok = hit & (face > 0.35) & ((fa > 110) | (el > -12))
    return fa[ok], P[ok, 2]


def bins(lo, lp):
    out = {}
    for a0 in range(0, 100, 10):
        mo = (lo[0] >= a0) & (lo[0] < a0 + 10)
        mp = (lp[0] >= a0) & (lp[0] < a0 + 10)
        if mo.sum() > 3 and mp.sum() > 3:
            out[a0] = (1000 * float(np.median(lo[1][mo])), 1000 * float(np.median(lp[1][mp])))
    return out


def coverage(fl, view):
    k, deg = view[0], float(view[1:])
    r = fl.raster(0, rot(k, deg))
    im = fl.image(r, magenta=True)
    w, h = r["wh"]
    im = np.asarray(Image.fromarray(np.clip(im, 0, 255).astype(np.uint8)).resize((w // 2, h // 2), Image.LANCZOS), float)
    R_, G_, B_ = im[..., 0], im[..., 1], im[..., 2]
    mag = (R_ - G_ > 35) & (B_ - G_ > 35) & (np.abs(R_ - B_) < 0.5 * np.maximum(R_, B_))
    # hcover's share is over the whole figure (head, neck, shoulders: not backdrop), which the flat has no body for:
    # the gate renders' figure areas at 1024 (hg_G59b / G60k1 / G60s1 within 2 %) stand in
    return 100 * float(mag.sum()) / AREA[view], im, mag


def descent(lo, lp, z0=1.730, tol=0.003):
    """The temple descent's POSITION: median |az| of the line's points within tol of height z0 (ours, photo). The old
    temple_side (median z per |az| bin 40-50 of view 0) measured where in the bin a near-vertical stretch falls."""
    out = []
    for l in (lo, lp):  # the first 2-deg bin from |az| 30 out whose median height is under z0 (the line's own points)
        a = None
        for a0 in np.arange(30.0, 100.0, 2.0):
            k = (l[0] >= a0) & (l[0] < a0 + 2)
            if k.sum() >= 2 and np.median(l[1][k]) < z0:
                a = round(float(a0 + 1), 1)
                break
        out.append(a)
    return out


def widths(sc, f, dz=(40, 60, 80, 100, 0, -20, -40)):
    """Front view: the head + hair silhouette's width (mm) at heights dz mm over the head centre (not backdrop)."""
    sil = np.asarray(f["bg"], float) < 0.5
    out = {}
    for d in dz:
        uv = humanfit.project(f["cam"], np.array([[sc.C[0], sc.C[1], sc.C[2] + d / 1000.0]]))[0]
        r = int(round(uv[1]))
        if not 0 <= r < sil.shape[0]:
            continue
        xs = np.nonzero(sil[r])[0]
        xs = xs[np.abs(xs - uv[0]) < 160.0 / f["mm"]]
        if len(xs):
            out[d] = round(float((xs.max() - xs.min()) * f["mm"]), 1)
    return out


def back_extent(sc, f, dz=(0, -20, -40)):
    """Profile view (2): how far the head + hair silhouette reaches BEHIND the head centre (mm, along the image's
    horizontal) at heights dz mm over C: the stand-off behind the ear (dz 0 .. -40 = ear height), where the reviewers
    saw a flare / skirt that the stand-off rays (median over the back region) and the front widths (+40..+80) miss."""
    sil = np.asarray(f["bg"], float) < 0.5
    c = humanfit.project(f["cam"], sc.C[None])[0]
    b = humanfit.project(f["cam"], (sc.C + np.array([0, 0.06, 0]))[None])[0]
    sgn = np.sign(b[0] - c[0]) or 1.0
    out = {}
    for d in dz:
        uv = humanfit.project(f["cam"], np.array([[sc.C[0], sc.C[1], sc.C[2] + d / 1000.0]]))[0]
        r = int(round(uv[1]))
        if not 0 <= r < sil.shape[0]:
            continue
        xs = np.nonzero(sil[r])[0]
        dx = (xs - c[0]) * sgn * f["mm"]
        dx = dx[(dx > 0) & (dx < 160.0)]
        if len(dx):  # the outermost run joined to the head (no stray strands past a gap)
            dx = np.sort(dx)
            gaps = np.nonzero(np.diff(dx) > 3.0)[0]
            out[d] = round(float(dx[gaps[0]] if len(gaps) else dx[-1]), 1)
    return out


def hem(sc, f):
    """Profile view, behind the ear (40-90 mm behind the head centre): the hair's lowest edge (mm under the centre,
    median over columns), its softness (mm from hair 0.8 to 0.2 going down) and its spread (mm, p90 - p10 of the
    edge's height: a level blunt cut is small)."""
    hp = np.asarray(f["hair"], float)
    c = humanfit.project(f["cam"], sc.C[None])[0]
    b = humanfit.project(f["cam"], (sc.C + np.array([0, 0.06, 0]))[None])[0]
    sgn = np.sign(b[0] - c[0]) or 1.0
    mm = f["mm"]
    zs, soft = [], []
    for dx in np.arange(40, 91, 2.0):
        x = int(round(c[0] + sgn * dx / mm))
        if not 0 <= x < hp.shape[1]:
            continue
        col = hp[:, x]
        k = np.nonzero(col > 0.5)[0]
        if not len(k):
            continue
        y = k.max()
        y8 = np.nonzero(col[:y + 1] > 0.8)[0]
        y2 = y + int(np.argmax(col[y:] < 0.2)) if (col[y:] < 0.2).any() else y
        zs.append((y - c[1]) * mm)
        if len(y8):
            soft.append((y2 - y8.max()) * mm)
    if len(zs) < 5:
        return None
    return {"z": round(float(np.median(zs)), 1), "soft": round(float(np.median(soft)), 1) if soft else None,
            "spread": round(float(np.percentile(zs, 90) - np.percentile(zs, 10)), 1),
            "cols": [round(float(np.median(zs[i_:i_ + 5])), 0) for i_ in range(0, len(zs), 5)]}  # z by 10 mm, 40 mm behind first


# the gate's targets (workspace/checklists/garrett_hair.json) and the screen's pass rule per row
SO_REF = {"front": 14.5, "top": 12.7, "crown": 10.9, "sides": 12.6, "back": 12.1, "nape": 9.3}
LAY_REF = {"direction__three_quarter__top_front": 17.1, "direction__profile__top_front": 31.4, "hairline__front": 17.8}


def table(res):
    rows = []
    for k, v in res["standoff"].items():
        rows.append((f"standoff_{k}", f"{SO_REF[k]} +- 3", v, abs(v - SO_REF[k]) <= 3))
    for k, tol in (("hairline_centre", 2), ("temple_corner", 6)):
        v = res.get(k)
        rows.append((k, f"0 +- {tol}", v, None if v is None else abs(v) <= tol))
    rows.append(("temple_side (uncal.)", "0 +- 6", res.get("temple_side"), None))
    td = res.get("temple_descent") or [None, None]
    rows.append(("temple_descent |az| at z 1730 (v1)", f"photo {td[1]} +- 4", td[0],
                 None if None in td else abs(td[0] - td[1]) <= 4))
    for k, (o, p_) in (res.get("widths") or {}).items():
        rows.append((f"width_front {int(k):+d} mm", f"photo {p_} +- 6", o, abs(o - p_) <= 6))
    for k, (o, p_) in (res.get("back_extent") or {}).items():  # behind the ear (v2): the side / back flare
        rows.append((f"back_extent {int(k):+d} mm (v2)", f"photo {p_} +- 4", o, abs(o - p_) <= 4))
    hm = res.get("hem") or {}
    if hm.get("ours") and hm.get("photo"):
        o, p_ = hm["ours"], hm["photo"]
        rows.append(("hem_z (mm under C, v2)", f"photo {p_['z']} +- 8", o["z"], abs(o["z"] - p_["z"]) <= 8))
        on = hm.get("net") or {}
        rows.append(("hem_soft (net, as the photo)", f"photo {p_['soft']} +- 2.5", on.get("soft"),
                     on.get("soft") is not None and abs(on["soft"] - p_["soft"]) <= 2.5))
        rows.append(("hem_soft (coverage, uncal.)", f"photo net {p_['soft']}", o["soft"], None))
        rows.append(("hem_spread (uncal.)", f"photo {p_['spread']}", o["spread"], None))
    ms = res.get("m_shape")
    rows.append(("m_shape (temple - centre)", ms and ms[1], ms and ms[0], None if not ms else abs(ms[0] - ms[1]) <= 6))
    # coverage: flat = render + 0.1 .. 0.3 (G59b .20 / .13, k1 1.69 / 1.41, s1 .38 / .19)
    for k, v, mx in (("coverage_above", "t60", 1.0), ("coverage_behind", "y180", 0.5)):
        x = res["coverage"].get(v)
        rows.append((k, f"<= {mx} (flat reads +0.1..0.3)", x, None if x is None else x <= mx + 0.15))
    for k, v in (res.get("lay") or {}).items():
        rows.append((f"lay {k[:22]}", f"{LAY_REF[k]} +- 5 (screen)", v, abs(v - LAY_REF[k]) <= 5))
    print(f"SCREEN {res['tag']}:")
    for r in rows:
        print(f"  {r[0]:34s} {str(r[1]):30s} {str(r[2]):14s} {'PASS' if r[3] else 'FAIL' if r[3] is False else '--'}")
    res["pass"] = {r[0]: r[3] for r in rows}


def screen(m, out, patch=None, lay=True, count=0):
    t0 = time.time()
    spec = store.load(m)
    tag = m
    if patch:
        spec = copy.deepcopy(spec)
        merge(spec["hair"], json.load(open(patch)))
        tag = m + "_" + patch.rsplit("/", 1)[-1].replace(".json", "")
    sc = hair.scalp(m, spec)
    sd = hair.job(m, spec, count=count or None)["strands"]
    D = hs.strands_of_model(sd)
    fl = Flat(m, spec, D, sc, sd)
    print(f"{tag}: {len(D['counts'])} strands, {len(fl.A)} segments, {time.time() - t0:.0f} s", flush=True)
    res = {"tag": tag}
    fp = {f["i"]: f for f in hr.frames(m, spec)}
    so, lines, raw = [], {}, {}
    for ci in (0, 1, 2):
        f = fl.frame(ci)
        if ci == 0:
            wo, wp = widths(sc, f), widths(sc, fp[ci])
            res["widths"] = {k: (wo[k], wp[k]) for k in wo if k in wp}
        if ci == 2:
            res["hem"] = {"ours": hem(sc, f), "photo": hem(sc, fp[ci])}
            # (the photo's "hair" is the parsing NET's probability, ours above is strand COVERAGE: a classifier's ramp
            # against an opacity ramp, hem_soft never moved, 4.2-5.2 vs 8.2. The same net on our flat image instead)
            pth = f"{out}/scr_{tag}_v{ci}_net.png"
            f["image"].save(pth)
            fn = hr.frames(m, spec, views=[ci], images={ci: pth})[0]
            res["hem"]["net"] = hem(sc, {**f, "hair": fn["hair"]})
            bo, bp = back_extent(sc, f), back_extent(sc, fp[ci])
            res["back_extent"] = {k: (bo[k], bp[k]) for k in bo if k in bp}
        f["image"].save(f"{out}/scr_{tag}_v{ci}.png")
        so.append(standoff(sc, f))
        lo, lp = hline(sc, f), hline(sc, fp[ci])
        if lo is not None and lp is not None:
            lines[ci] = bins(lo, lp)
            raw[ci] = (lo, lp)
    res["standoff"] = {r: round(float(np.median([s[r] for s in so if r in s])), 1) for r in hr.REGIONS
                       if any(r in s for s in so)}
    res["hairline"] = lines

    def d(v, keys):
        x = [lines.get(v, {}).get(k) for k in keys]
        x = [a - b for a, b in (y for y in x if y)]
        return round(float(np.mean(x)), 1) if x else None

    def lvl(v, keys, i):
        x = [lines.get(v, {}).get(k) for k in keys]
        x = [y[i] for y in x if y]
        return float(np.mean(x)) if x else None
    # CALIBRATED (hg_G59b / G60k1 renders through hlinetrace, per bin): the flat's line sits +1.9 mm over the
    # render's (G59b 4.7/5.0/5.8/8.9 vs 2.6/3.3/4.2/6.8 at |az| 0/10/20/30): HL_BIAS taken off
    res["hairline_centre"] = None if d(0, (0, 10)) is None else round(d(0, (0, 10)) - HL_BIAS, 1)
    res["temple_corner"] = None if d(0, (30,)) is None else round(d(0, (30,)) - HL_BIAS, 1)
    # |az| 40-50 in the front view: the photo's line runs DOWN the temple toward the sideburn there; the gate's
    # temple_corners averages it in only when the render's parser finds > 3 points (k1 +21.7 = bin 30 +6.7 and bin 40
    # +36.7; G59b's render had no bin 40: +6.8 = bin 30 alone). Reported apart, uncalibrated.
    res["temple_side"] = d(0, (40,))
    res["temple_descent"] = descent(*raw[1]) if 1 in raw else None
    c_o, t_o, c_p, t_p = lvl(0, (0, 10), 0), lvl(0, (30,), 0), lvl(0, (0, 10), 1), lvl(0, (30,), 1)
    res["m_shape"] = (round(t_o - c_o, 1), round(t_p - c_p, 1)) if None not in (c_o, t_o, c_p, t_p) else None
    res["side_line"] = d(2, (20, 30, 40))
    cov = {}
    for v in ("t60", "y180"):
        pct, im, mag = coverage(fl, v)
        cov[v] = round(pct, 2)
        vis = im.copy()
        vis[mag] = [0, 255, 0]
        Image.fromarray(vis.astype(np.uint8)).save(f"{out}/scr_{tag}_mag_{v}.png")
    res["coverage"] = cov
    print(f"{tag}: stand-off {res['standoff']} | hairline_centre {res['hairline_centre']} temple_corner (az 30) "
          f"{res['temple_corner']} temple_side (az 40) {res['temple_side']} M (temple - centre, ours | photo) "
          f"{res['m_shape']} descent (v1, ours | photo) {res['temple_descent']} widths {res['widths']} hem {res['hem']} side line (profile view) {res['side_line']} | "
          f"coverage {cov} | {time.time() - t0:.0f} s", flush=True)
    for v, b in lines.items():
        print(f"  hairline view {v} ours - photo mm by |az|: " + ", ".join(f"{a}: {x - y:+.1f}" for a, (x, y) in b.items()))
    if lay:
        import laycal
        lr = laycal.strands(m, 0, out, patch)  # the render's strand count (successor 17)
        res["lay"] = {k: round(v["raster"]["lay"], 1) for k, v in lr.items()}
        print(f"{tag}: lay 3q / profile / hairline " + " / ".join(str(x) for x in res["lay"].values()), flush=True)
    table(res)
    json.dump(res, open(f"{out}/scr_{tag}.json", "w"), indent=1, default=str)
    return res


if __name__ == "__main__":
    kw = dict(a.split("=", 1) for a in sys.argv[3:] if "=" in a)
    pats = [a for a in sys.argv[3:] if "=" not in a] or [None]
    for p in pats:
        screen(sys.argv[1], sys.argv[2], p, kw.get("lay", "1") == "1", int(kw.get("count", 0)))
