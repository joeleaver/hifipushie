"""Do render-calibrated normals transfer to a PHOTOGRAPH? No truth exists for a photo, so three things are read:
  (1) agreement of a model's normals with a head fitted to that photo WITHOUT any normals (g3_f, humanfit_map's
      camera), by region, after one global rotation (camera-axis conventions and the crop's off-axis view);
  (2) the calibration's own quantities, on the photo and on front renders with the SAME code:
      gain g = slope of (head - mean head) on (model - mean head), their correlation, and what is left;
  (3) noise: a vertex's normal against the mean of its neighbours within 5 mm (the head's own value = real relief).
run.sh photo.py head | crops | photo [models] | renders [models] | sheet"""
import json
import sys

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

import mm
import rs

HF = mm.MM / "out" / "g3_head.npz"
REGS = ("forehead", "cheeks", "nose", "brow", "chin", "lips", "eyes", "jaw")
TRUST = ("forehead", "cheeks", "nose")
G = "/home/joe/dev/hifipushie/workspace/garrett_v20/"
SRC = "concept_v8_front_apose.png"
CROPS = ("garrett_front", "garrett_front_tight", "garrett_front_tight384")
LABEL = {"david": "DAViD (MIT)", "marigold": "Marigold v1-1 (OpenRAIL++-M)", "marigold_lcm": "Marigold LCM v0-1 (Apache-2.0)",
         "sapiens2": "Sapiens2 1B (no biometric use)", "moge2": "MoGe-2 (MIT)"}


def head():
    """The fitted head of g3_f (world, template pose), triangles, its 68 landmarks, the front picture's camera."""
    from hifipushie import onemesh, store
    spec = store.load("g3_f")
    ht = onemesh.head_rest(spec["base"])
    q = np.asarray(ht["faces"])
    T = np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]]
    refs = json.loads(open("/home/joe/dev/hifipushie/workspace/g3_f/human_refs.json").read())
    np.savez(HF, V=np.asarray(ht["verts"], float), T=T, L=np.asarray(ht["lm68"], float), cam=json.dumps(refs["cameras"][0]))
    print("head", np.asarray(ht["verts"]).shape, T.shape)


def load_head():
    z = np.load(HF)
    return z["V"], z["T"].astype(np.int64), z["L"], json.loads(str(z["cam"]))


def tri_normals(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    vn = np.zeros_like(V)
    for c in range(3):
        np.add.at(vn, T[:, c], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)


def crops():
    """The tight crops of the front photo: the head's box + 18%, square, at 768 and at 384 px."""
    V, T, L, cam = load_head()
    P = rs.humanfit.project(cam, V)
    c = (P.min(0) + P.max(0)) / 2
    half = (P.max(0) - P.min(0)).max() / 2 * 1.18
    box = [int(c[0] - half), int(c[1] - half), int(c[0] + half), int(c[1] + half)]
    im = Image.open(G + SRC).convert("RGB")
    for name, px in (("garrett_front_tight", 768), ("garrett_front_tight384", 384)):
        im.crop(box).resize((px, px), Image.LANCZOS).save(mm.MM / "img" / f"{name}.png")
        (mm.MM / "img" / f"{name}.json").write_text(json.dumps({"source": SRC, "box": box, "scale": px / (box[2] - box[0])}))
    print("box", box, "head px in the source", (P.max(0) - P.min(0)).round(), "px/mm", round(cam["f"] / cam["t"][2] / 1000, 2))


def view_rot(cam, box):
    """Rotation taking camera-frame vectors into the frame whose z looks through the crop's centre."""
    w, h = cam["size"]
    d = np.array([((box[0] + box[2]) / 2 - w / 2) / cam["f"], ((box[1] + box[3]) / 2 - h / 2) / cam["f"], 1.0])
    d /= np.linalg.norm(d)
    z = np.array([0, 0, 1.0])
    v = np.cross(d, z)
    s, c = np.linalg.norm(v), d @ z
    if s < 1e-9:
        return np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / s ** 2)


def photo_item(crop):
    """The fitted head as this crop pictures it: visible vertices, their pixels in the crop, normals (crop's view
    frame), the mean head's normals there, a region per vertex."""
    V, T, L, cam = load_head()
    meta = json.loads((mm.MM / "img" / f"{crop}.json").read_text())
    box, sc = meta["box"], meta["scale"]
    g = rs.gnm()
    # the mean head on this head (landmarks), for regions and for "what is this head's own"
    s, R, t = rs.similarity(g["L0"][:68], L)
    A = s * g["V0"] @ R.T + t
    ext = np.flatnonzero(g["ext"])
    d, j = cKDTree(A[ext]).query(V)
    reg, face = mm.region_of()
    r = np.where(d < 0.006, reg[ext[j]], "")
    w, h = cam["size"]
    Rc = rs.humanfit._cam_rot(cam)
    Xc = rs.cam_xform(cam, V)
    P = rs.humanfit.project(cam, V)
    from hifipushie import likeness
    if "run" not in mm._C:
        mm._C["run"] = likeness._raster()
    fn = np.cross(Xc[T[:, 1]] - Xc[T[:, 0]], Xc[T[:, 2]] - Xc[T[:, 0]])
    keep = (fn * Xc[T].mean(1)).sum(1) < 0
    img = np.zeros((h, w, 3))
    zb = np.full((h, w), np.inf)
    mm._C["run"](P[:, 0].copy(), P[:, 1].copy(), Xc[:, 2].copy(), np.ascontiguousarray(T[keep]), np.zeros((len(V), 3)), w, h, img, zb)
    u, v = np.clip(P[:, 0].astype(int), 0, w - 1), np.clip(P[:, 1].astype(int), 0, h - 1)
    Rv = view_rot(cam, box)
    n = tri_normals(V, T) @ Rc.T @ Rv.T
    nA = mm.vnormals(A)
    n0 = (nA @ Rc.T @ Rv.T)[ext[j]]
    zax = Rc.T @ Rv.T[:, 2]                      # the crop's view axis in the world
    dn = ((V - A[ext[j]]) * nA[ext[j]]).sum(1)   # signed distance from the mean head's surface
    cz = nA[ext[j]] @ zax
    dz = np.where(np.abs(cz) > 0.4, dn / np.where(np.abs(cz) > 0.4, cz, 1.0), np.nan)   # this head - mean head, along the view
    zc = (Xc @ Rv.T)[:, 2]
    ok = (Xc[:, 2] < zb[v, u] + 0.003) & (n[:, 2] < -0.15) & (r != "")
    i = np.flatnonzero(ok)
    pix = (P[i] - np.asarray(box[:2], float)) * sc
    return {"idx": i, "pix": pix, "n": n[i], "n0": n0[i], "reg": r[i], "X": V[i], "gidx": ext[j][i], "z": zc[i], "dz": dz[i], "scale_px_mm": cam["f"] / cam["t"][2] / 1000 * sc, "size": int(round((box[2] - box[0]) * sc))}


def render_item(iid):
    it = mm.item(iid)
    X0, n0 = mm.mean_head(it)
    return {"gidx": it["idx"], "z": it["Xc"][:, 2], "dz": it["Xc"][:, 2] - X0[:, 2], "idx": it["idx"], "pix": it["pix"], "n": it["n"], "n0": n0, "reg": it["reg"], "X": it["V"][it["idx"]], "size": it["cam"]["size"][0]}


def flips(model):
    f = mm.MM / f"dense_{model}.npz"
    if f.exists():
        return np.load(f)["flip"].astype(float)
    return np.array({"david": (1, -1, -1), "marigold": (1, -1, -1), "marigold_lcm": (1, -1, -1), "sapiens2": (1, -1, -1), "moge2": (1, 1, 1)}[model], float)


def kabsch(a, b):
    """R with b ~ a R^T."""
    U, _, Vt = np.linalg.svd(b.T @ a)
    d = np.sign(np.linalg.det(U @ Vt))
    return U @ np.diag([1, 1, d]) @ Vt


def stats(N, it, flip, model=None, view="front"):
    """N: the model's normal map for this item. With model + it["gidx"] (GNM vertex per point): `cal` = the angle to
    the head of the RENDER-calibrated normal, mean + gain x (model - mean), gain per vertex from dense_<model>.npz."""
    if N.shape[0] != it["size"]:
        z = it["size"] / N.shape[0]
        N = ndimage.zoom(N.astype(np.float32), (z, z, 1), order=1)
    nm = mm.sample(N.astype(float), it["pix"]) * flip
    nm /= np.maximum(np.linalg.norm(nm, axis=1, keepdims=True), 1e-9)
    tr = np.isin(it["reg"], REGS)
    R = kabsch(nm[tr], it["n"][tr])
    rot = np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))
    raw = np.degrees(np.arccos(np.clip((nm * it["n"]).sum(1), -1, 1)))
    nm = nm @ R.T
    ang = np.degrees(np.arccos(np.clip((nm * it["n"]).sum(1), -1, 1)))
    n0 = it["n0"] @ kabsch(it["n0"][tr], it["n"][tr]).T     # the mean head's own tilt against this head is not relief
    it = {**it, "n0": n0}
    a0 = np.degrees(np.arccos(np.clip((it["n0"] * it["n"]).sum(1), -1, 1)))
    acal = np.full(len(a0), np.nan)
    f = mm.MM / f"dense_{model}.npz"
    if model and "gidx" in it and f.exists():
        import dense
        gq = np.clip(dense.table(model)[f"g_n_{dense.VC[view]}"][it["gidx"]].astype(float) * GSCALE, 0, 1.2)
        tg = n0 + gq[:, None] * (nm - n0)
        tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
        acal = np.degrees(np.arccos(np.clip((tg * it["n"]).sum(1), -1, 1)))
    tree = cKDTree(it["X"])
    nb = tree.query_ball_point(it["X"], 0.008)

    def hp(M):
        out = np.full(len(M), np.nan)
        for k, b in enumerate(nb):
            if len(b) >= 4:
                m = M[b].mean(0)
                out[k] = np.degrees(np.arccos(np.clip(M[k] @ m / np.linalg.norm(m), -1, 1)))
        return out
    hm_, hh = hp(nm), hp(it["n"])
    dm, dh = (nm - it["n0"])[:, :2], (it["n"] - it["n0"])[:, :2]
    out = {"rot": float(rot)}
    for k in REGS + ("trusted",):
        m = np.isin(it["reg"], TRUST) if k == "trusted" else it["reg"] == k
        if m.sum() < 25:
            continue
        gq = float((dm[m] * dh[m]).sum() / max((dm[m] ** 2).sum(), 1e-12))
        corr = float((dm[m] * dh[m]).sum() / np.sqrt(max((dm[m] ** 2).sum() * (dh[m] ** 2).sum(), 1e-12)))
        left = float(np.degrees(np.sqrt(((dh[m] - gq * dm[m]) ** 2).mean())))
        pop = float(np.degrees(np.sqrt((dh[m] ** 2).mean())))
        out[k] = {"n": int(m.sum()), "raw": float(raw[m].mean()), "ang": float(ang[m].mean()), "mean_head": float(a0[m].mean()), "cal": float(np.nanmean(acal[m])) if np.isfinite(acal[m]).any() else float("nan"), "gain": gq, "corr": corr,
                  "left": left, "pop": pop, "noise": float(np.sqrt(np.nanmean(hm_[m] ** 2))), "noise_head": float(np.sqrt(np.nanmean(hh[m] ** 2)))}
    return out


def nsample(N, it, flip):
    if N.shape[0] != it["size"]:
        z = it["size"] / N.shape[0]
        N = ndimage.zoom(N.astype(np.float32), (z, z, 1), order=1)
    nm = mm.sample(N.astype(float), it["pix"]) * flip
    nm /= np.maximum(np.linalg.norm(nm, axis=1, keepdims=True), 1e-9)
    tr = np.isin(it["reg"], REGS)
    return nm @ kabsch(nm[tr], it["n"][tr]).T


def pair(Na, Nb, it, fa, fb):
    """Two models against each other on the trusted regions: mean angle, correlation of their deviations from the mean head."""
    a, b = nsample(Na, it, fa), nsample(Nb, it, fb)
    m = np.isin(it["reg"], TRUST)
    da, db = (a - it["n0"])[m, :2], (b - it["n0"])[m, :2]
    ang = np.degrees(np.arccos(np.clip((a[m] * b[m]).sum(1), -1, 1))).mean()
    return float(ang), float((da * db).sum() / np.sqrt((da ** 2).sum() * (db ** 2).sum()))


def depth_stats(pr, it, inverse):
    """A model's depth against the head's: scale + shift on the face, then mm rms; the mean head's rms; correlation and
    gain of the deviations from the mean head (as score_geo's table)."""
    D = pr["points"][..., 2] if "points" in pr else pr["depth"]
    D = np.where(np.isfinite(D), D, np.nanmedian(D[np.isfinite(D)])).astype(float)
    if D.shape[0] != it["size"]:
        D = ndimage.zoom(D, it["size"] / D.shape[0], order=1)
    d = mm.sample(D, it["pix"])
    ok = np.isfinite(it["dz"]) & np.isin(it["reg"], REGS)
    zf = mm.fit_z(d, it["z"], ok.astype(float), inverse)
    out = {}
    for k in ("face",) + TRUST + ("chin", "brow"):
        m = ok & (np.isin(it["reg"], REGS) if k == "face" else it["reg"] == k)
        if m.sum() < 25:
            continue
        e = (zf - it["z"])[m] * 1000
        dh = it["dz"][m] * 1000
        dm = e + dh
        out[k] = {"model": float(np.sqrt((e ** 2).mean())), "mean": float(np.sqrt((dh ** 2).mean())),
                  "corr": float((dm * dh).sum() / np.sqrt((dm ** 2).sum() * (dh ** 2).sum())), "gain": float((dm * dh).sum() / (dm ** 2).sum())}
    return out


def inv(model):
    f = mm.MM / f"dense_{model}.npz"
    return bool(np.load(f)["inverse"]) if f.exists() else False


def depth(models):
    print("DEPTH, mm rms along the view after scale + shift on the face | the mean head's | corr and gain of deviations from the mean head")
    for m in models:
        rows = {}
        for crop in CROPS[:2]:
            f = mm.PRED / m / f"{crop}.npz"
            if f.exists() and ("depth" in np.load(f) or "points" in np.load(f)):
                rows[f"photo {crop[8:]}"] = [depth_stats(dict(np.load(f)), photo_item(crop), inv(m))]
        acc = []
        for iid in mm.ids(view="front"):
            pr = mm.pred(m, iid)
            if pr is not None and ("depth" in pr or "points" in pr):
                acc.append(depth_stats(pr, render_item(iid), inv(m)))
        if acc:
            rows[f"renders ({len(acc)} fronts)"] = acc
        for tag, L in rows.items():
            for k in ("face",) + TRUST + ("chin", "brow"):
                v = np.array([[x[k][q] for q in ("model", "mean", "corr", "gain")] for x in L if k in x])
                if len(v):
                    print(f"{m:9s} {tag:22s} {k:9s} | {v[:, 0].mean():5.2f} {v[:, 1].mean():5.2f} | {v[:, 2].mean():5.2f} {v[:, 3].mean():5.2f}" + (f"   (sd of corr over pictures {v[:, 2].std():.2f})" if len(v) > 1 else ""))


def pairs(models):
    print("MODEL AGAINST MODEL on the trusted regions (forehead, cheeks, nose): mean angle deg / correlation of deviations from the mean head")
    for a in range(len(models)):
        for b in range(a + 1, len(models)):
            ma, mb = models[a], models[b]
            txt = f"{ma:13s} vs {mb:13s}"
            for crop in CROPS[:2]:
                fa, fb = mm.PRED / ma / f"{crop}.npz", mm.PRED / mb / f"{crop}.npz"
                if fa.exists() and fb.exists():
                    an, co = pair(np.load(fa)["normal"], np.load(fb)["normal"], photo_item(crop), flips(ma), flips(mb))
                    txt += f" | photo {crop[8:]:11s} {an:4.1f} / {co:4.2f}"
            acc = []
            for iid in mm.ids(view="front"):
                pa, pb = mm.pred(ma, iid), mm.pred(mb, iid)
                if pa is not None and pb is not None:
                    acc.append(pair(pa["normal"], pb["normal"], render_item(iid), flips(ma), flips(mb)))
            if acc:
                acc = np.array(acc)
                txt += f" | renders {acc[:, 0].mean():4.1f} / {acc[:, 1].mean():4.2f} (sd {acc[:, 1].std():.2f})"
            print(txt)


GSCALE = 1.0     # the render calibration's gains x this (lps.py gains)
KEYS = ("n", "raw", "ang", "mean_head", "cal", "gain", "corr", "left", "pop", "noise", "noise_head")
HEAD = f"{'':34s} {'region':9s} {'n':>5s} | {'raw':>5s} {'ang':>5s} {'mean':>5s} {'cal':>5s} | {'gain':>5s} {'corr':>5s} {'left':>5s} {'of':>5s} | {'noise':>5s} {'head':>5s}"


def line(tag, k, s):
    return (f"{tag:34s} {k:9s} {s['n']:5d} | {s['raw']:5.1f} {s['ang']:5.1f} {s['mean_head']:5.1f} {s.get('cal', float('nan')):5.1f} | {s['gain']:5.2f} {s['corr']:5.2f} {s['left']:5.2f} {s['pop']:5.2f} | "
            f"{s['noise']:5.2f} {s['noise_head']:5.2f}")


def photo(models):
    res = {}
    print("PHOTO (Garrett front; head = g3_f, fitted without normals). deg. raw = before the global rotation; ang = after; mean = the mean head's "
          "angle to the fitted head;\n gain/corr/left/of = the calibration's quantities (deviation from the mean head); noise = against neighbours within 5 mm\n" + HEAD)
    for crop in CROPS:
        it = photo_item(crop)
        for m in models:
            f = mm.PRED / m / f"{crop}.npz"
            if not f.exists():
                continue
            s = stats(np.load(f)["normal"], it, flips(m), m)
            res[f"{m}/{crop}"] = s
            print(f"-- {m} on {crop} ({it['scale_px_mm']:.1f} px/mm; fitted rotation {s['rot']:.1f} deg)")
            for k in ("trusted",) + REGS:
                if k in s:
                    print(line(f"{m}/{crop[8:]}", k, s[k]))
    (mm.MM / "out" / "photo_stats.json").write_text(json.dumps(res, indent=1))


def renders(models):
    res = {}
    print("RENDERS (the truth heads' 10 front pictures of the skinned set: mean and sd over pictures)\n" + HEAD)
    for m in models:
        acc = {}
        fl = flips(m)
        for iid in mm.ids("truth", "front"):          # the calibration heads' own pictures would flatter `cal`
            pr = mm.pred(m, iid)
            if pr is None or "normal" not in pr:
                continue
            s = stats(pr["normal"], render_item(iid), fl, m)
            for k, v in s.items():
                if isinstance(v, dict):
                    acc.setdefault(k, []).append([v[q] for q in KEYS])
        res[m] = {}
        for k in ("trusted",) + REGS:
            if k not in acc:
                continue
            a = np.array(acc[k])
            mu, sd = a.mean(0), a.std(0)
            res[m][k] = {"mean": mu.tolist(), "sd": sd.tolist(), "pictures": len(a)}
            d = dict(zip(KEYS, mu))
            d["n"] = int(d["n"])
            print(line(f"{m} renders ({len(a)})", k, d))
            print(f"{'   sd over pictures':34s} {'':9s} {'':5s} | {sd[1]:5.1f} {sd[2]:5.1f} {sd[3]:5.1f} {sd[4]:5.1f} | {sd[5]:5.2f} {sd[6]:5.2f} {sd[7]:5.2f} {sd[8]:5.2f} | {sd[9]:5.2f} {sd[10]:5.2f}")
    (mm.MM / "out" / "render_stats.json").write_text(json.dumps(res, indent=1))


def ncol(n):
    c = np.stack([n[..., 0], -n[..., 1], -n[..., 2]], -1) * 0.5 + 0.5
    return (np.clip(c, 0, 1) * 255).astype(np.uint8)


def sheet(models):
    """Per crop: photo | the fitted head's normals | each model's normals (person only where a mask exists) | its angle
    to the fitted head on the face (0..30 deg)."""
    import os
    from PIL import ImageDraw
    S = 384
    R = os.environ.get("R", "/home/joe/dev/hifipushie/workspace/human_renders")
    cr = [c for c in CROPS if any((mm.PRED / m / f"{c}.npz").exists() for m in models)]
    out = Image.new("RGB", (S * (2 + 2 * len(models)), S * len(cr)), (30, 30, 30))
    for r, crop in enumerate(cr):
        it = photo_item(crop)
        im = Image.open(mm.MM / "img" / f"{crop}.png").convert("RGB").resize((S, S), Image.LANCZOS)
        ImageDraw.Draw(im).text((6, 4), f"{crop} ({it['scale_px_mm']:.1f} px/mm)", fill=(255, 255, 0))
        out.paste(im, (0, r * S))
        z = S / it["size"]
        hd = np.full((S, S, 3), 128, np.uint8)
        u, v = np.clip((it["pix"] * z).astype(int), 0, S - 1).T
        for du in (0, 1):
            for dv in (0, 1):
                hd[np.clip(v + dv, 0, S - 1), np.clip(u + du, 0, S - 1)] = ncol(it["n"])
        t = Image.fromarray(hd)
        ImageDraw.Draw(t).text((6, 4), "fitted head g3_f (visible face vertices)", fill=(255, 255, 0))
        out.paste(t, (S, r * S))
        for k, m in enumerate(models):
            f = mm.PRED / m / f"{crop}.npz"
            if not f.exists():
                continue
            d = np.load(f)
            N = d["normal"].astype(float) * flips(m)
            N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-9)
            c = ncol(N)
            if "mask" in d:
                mk = d["mask"].astype(float)
                mk = mk / max(mk.max(), 1e-9) > 0.5
                c = np.where(mk[..., None], c, 128)
            t = Image.fromarray(c).resize((S, S), Image.LANCZOS)
            ImageDraw.Draw(t).text((6, 4), LABEL.get(m, m), fill=(255, 255, 0))
            out.paste(t, ((2 + 2 * k) * S, r * S))
            Nz = ndimage.zoom(N.astype(np.float32), (it["size"] / N.shape[0],) * 2 + (1,), order=1) if N.shape[0] != it["size"] else N
            nm = mm.sample(Nz, it["pix"])
            nm /= np.maximum(np.linalg.norm(nm, axis=1, keepdims=True), 1e-9)
            tr = np.isin(it["reg"], REGS)
            nm = nm @ kabsch(nm[tr], it["n"][tr]).T
            ang = np.degrees(np.arccos(np.clip((nm * it["n"]).sum(1), -1, 1)))
            x = np.clip(ang / 30, 0, 1)
            col = (np.stack([np.clip(1.5 - np.abs(4 * x - 3), 0, 1), np.clip(1.5 - np.abs(4 * x - 2), 0, 1), np.clip(1.5 - np.abs(4 * x - 1), 0, 1)], 1) * 255).astype(np.uint8)
            e = np.full((S, S, 3), 30, np.uint8)
            for du in (0, 1):
                for dv in (0, 1):
                    e[np.clip(v + dv, 0, S - 1), np.clip(u + du, 0, S - 1)] = col
            t = Image.fromarray(e)
            ImageDraw.Draw(t).text((6, 4), f"angle to the fitted head 0..30 deg (face mean {ang[tr].mean():.1f})", fill=(255, 255, 0))
            out.paste(t, ((3 + 2 * k) * S, r * S))
    out.save(f"{R}/mm_04_photo_normals.png")
    print(f"{R}/mm_04_photo_normals.png")


if __name__ == "__main__":
    a = sys.argv[1]
    ms = sys.argv[2:] or ["david", "marigold", "marigold_lcm", "sapiens2"]
    {"head": head, "crops": crops, "photo": lambda: photo(ms), "renders": lambda: renders(ms), "sheet": lambda: sheet(ms), "pairs": lambda: pairs(ms), "depth": lambda: depth(ms)}[a]()
