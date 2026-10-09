"""A REAL head with ground truth: Lee Perry-Smith's scan (Infinite-Realities, CC BY 3.0: real geometry, photographed
albedo, its own normal map), path-traced in Cycles through known cameras. Not a photograph, but real skin, brows,
lashes, pores and a real face's relief: the nearest thing to a photo with truth we may use.
run.sh lps.py prep | render | stats [models] | sheet [models]"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import mm
import photo
import rs
import tmesh

L = mm.MM / "lps"
VIEWS = (("front", 0.0), ("tq", 40.0), ("tq2", -38.0))
LIGHTS = {"a": {"lc": (-0.2, -0.35, -0.9), "sun_w": 2.2, "sky": 1.0, "soft": 25.0, "back": (0.75, 0.76, 0.78)},      # soft, frontal
          "b": {"lc": (-0.75, -0.45, -0.5), "sun_w": 4.0, "sky": 0.45, "soft": 5.0, "back": (0.32, 0.36, 0.42)}}     # hard, from the side


def placed():
    if "lps" not in mm._C:
        me = tmesh.Mesh("lps")
        H0 = rs.head()
        e = tmesh.align(me, H0, yaw_hint=0)
        mm._C["lps"] = (me, H0, e)
    return mm._C["lps"]


def cams():
    me, H0, e = placed()
    out = {}
    for vn, yaw in VIEWS:
        for ln in LIGHTS:
            out[f"lps_{vn}_{ln}"] = rs.make_cam(H0, yaw=yaw, pitch=3.0, lens=70.0, fill=0.6)
    return out


def prep():
    me, H0, e = placed()
    Vw, _ = me.placed()
    print("scan on the mean head: icp residual", round(e * 1000, 2), "mm; scale", me.T[0], "start", getattr(me, "start", None))
    z = np.load(tmesh.TR / "lps.npz")
    (L / "set").mkdir(parents=True, exist_ok=True)
    np.savez(L / "job.npz", V=Vw.astype(np.float32), F=me.F, uv=np.c_[z["uv"][:, 0], 1 - z["uv"][:, 1]])
    views = []
    for iid, cam in cams().items():
        Rc = rs.humanfit._cam_rot(cam)
        pos = np.asarray(cam["centre"]) - Rc.T @ np.asarray(cam["t"])
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = Rc.T @ [1, 0, 0], Rc.T @ [0, -1, 0], Rc.T @ [0, 0, -1], pos
        lk = LIGHTS[iid[-1]]
        lc = np.asarray(lk["lc"], float)
        views.append({"id": iid, "M": M.tolist(), "lens": cam["f"] / cam["size"][0] * 36.0, "size": cam["size"], "sun": (Rc.T @ (lc / np.linalg.norm(lc))).tolist(),
                      "sun_w": lk["sun_w"], "sky": lk["sky"], "soft": lk["soft"], "back": lk["back"]})
    d = str(L / "dl")
    (L / "job.json").write_text(json.dumps({"albedo": d + "/Map-COL.jpg", "normal": d + "/Infinite-Level_02_Tangent_SmoothUV.jpg", "spec": d + "/Map-SPEC.jpg", "views": views}))


def render():
    here = Path(__file__).parent
    subprocess.run(["blender", "-b", "--factory-startup", "-P", str(here / "bl_scan.py"), "--", str(L / "job.npz"), str(L / "job.json"), str(L / "set")], check=True)


def item(iid):
    """The scan as pictured, read at the mean head's face vertices' nearest scan points."""
    key = "it" + iid
    if key in mm._C:
        return mm._C[key]
    me, H0, e = placed()
    cam = cams()[iid]
    g = rs.gnm()
    reg, _ = mm.region_of()
    idx = np.flatnonzero(g["ext"] & np.isin(reg, photo.REGS))
    q, nq, d = me.near(H0[idx])
    Rc = rs.humanfit._cam_rot(cam)
    Vw, _ = me.placed()
    w, h = cam["size"]
    Xc = rs.cam_xform(cam, Vw)
    P = rs.humanfit.project(cam, Vw)
    from hifipushie import likeness
    if "run" not in mm._C:
        mm._C["run"] = likeness._raster()
    T = np.asarray(me.F, np.int64)
    fn = np.cross(Xc[T[:, 1]] - Xc[T[:, 0]], Xc[T[:, 2]] - Xc[T[:, 0]])
    keep = (fn * Xc[T].mean(1)).sum(1) < 0
    if keep.mean() < 0.3:
        keep = ~keep
    img = np.zeros((h, w, 3))
    zb = np.full((h, w), np.inf)
    mm._C["run"](P[:, 0].copy(), P[:, 1].copy(), Xc[:, 2].copy(), np.ascontiguousarray(T[keep]), np.zeros((len(Vw), 3)), w, h, img, zb)
    pq = rs.humanfit.project(cam, q)
    zq = rs.cam_xform(cam, q)[:, 2]
    u, v = np.clip(pq[:, 0].astype(int), 0, w - 1), np.clip(pq[:, 1].astype(int), 0, h - 1)
    tr = np.asarray(Image.open(L / "set" / f"{iid}_truth.png")).astype(float) / 255.0   # PIL reads the 16-bit RGBA as 8
    nw = mm.sample(tr[..., :3], pq) * 2 - 1
    al = mm.sample(tr[..., 3], pq)
    nw /= np.maximum(np.linalg.norm(nw, axis=1, keepdims=True), 1e-9)
    n = nw @ Rc.T
    n0 = (mm.vnormals(H0) @ Rc.T)[idx]
    ok = (d < 0.012) & (zq < zb[v, u] + 0.004) & (al > 0.98) & (n[:, 2] < -0.15) & (pq[:, 0] > 2) & (pq[:, 0] < w - 2) & (pq[:, 1] > 2) & (pq[:, 1] < h - 2)
    k = np.flatnonzero(ok)
    out = {"gidx": idx[k], "idx": idx[k], "pix": pq[k], "n": n[k], "n0": n0[k], "reg": reg[idx[k]], "X": q[k], "size": w, "z": zq[k],
           "dz": zq[k] - rs.cam_xform(cam, H0[idx[k]])[:, 2]}
    mm._C[key] = out
    return out


def stats(models):
    res = {}
    print("THE SCANNED HEAD (real geometry and albedo, path-traced; truth = its own shading normals). deg, as photo.py's table;\n"
          "mean and sd over 6 pictures (front, two three-quarters x soft / hard light)\n" + photo.HEAD)
    for m in models:
        acc = {}
        for iid in cams():
            f = mm.PRED / m / f"{iid}.npz"
            if not f.exists():
                continue
            s = photo.stats(np.load(f)["normal"], item(iid), photo.flips(m), m, iid.split("_")[1])
            res[f"{m}/{iid}"] = s
            for k, v in s.items():
                if isinstance(v, dict):
                    acc.setdefault(k, []).append([v[q] for q in photo.KEYS])
        for k in ("trusted",) + photo.REGS:
            if k not in acc:
                continue
            a = np.array(acc[k])
            mu, sd = a.mean(0), a.std(0)
            d = dict(zip(photo.KEYS, mu))
            d["n"] = int(d["n"])
            print(photo.line(f"{m} scan ({len(a)})", k, d) + f"   sd corr {sd[6]:.2f} ang {sd[2]:.1f}")
    (mm.MM / "out" / "lps_stats.json").write_text(json.dumps(res, indent=1))
    print("\nby picture, trusted regions: angle after rotation / corr")
    for iid in cams():
        print(f"  {iid:14s} " + "  ".join(f"{m} {res[f'{m}/{iid}']['trusted']['ang']:4.1f}/{res[f'{m}/{iid}']['trusted']['corr']:4.2f}" for m in models if f"{m}/{iid}" in res))


def sheet(models):
    from PIL import ImageDraw
    S = 320
    R = os.environ.get("R", "/home/joe/dev/hifipushie/workspace/human_renders")
    ids = ["lps_front_a", "lps_tq_b", "lps_tq2_a"]
    out = Image.new("RGB", (S * (2 + len(models)), S * len(ids)), (30, 30, 30))
    for r, iid in enumerate(ids):
        im = Image.open(L / "set" / f"{iid}.png").convert("RGB").resize((S, S), Image.LANCZOS)
        ImageDraw.Draw(im).text((6, 4), iid + " (scan: Lee Perry-Smith / Infinite-Realities, CC BY 3.0)", fill=(255, 255, 0))
        out.paste(im, (0, r * S))
        tr = np.asarray(Image.open(L / "set" / f"{iid}_truth.png")).astype(float) / 255.0   # PIL reads the 16-bit RGBA as 8
        Rc = rs.humanfit._cam_rot(cams()[iid])
        nc = (tr[..., :3] * 2 - 1) @ Rc.T
        mk = tr[..., 3] > 0.5
        t = Image.fromarray(np.where(mk[..., None], photo.ncol(nc), 128).astype(np.uint8)).resize((S, S), Image.LANCZOS)
        ImageDraw.Draw(t).text((6, 4), "truth", fill=(255, 255, 0))
        out.paste(t, (S, r * S))
        for k, m in enumerate(models):
            f = mm.PRED / m / f"{iid}.npz"
            if not f.exists():
                continue
            N = np.load(f)["normal"].astype(float) * photo.flips(m)
            N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-9)
            t = Image.fromarray(np.where(mk[..., None], photo.ncol(N), 128).astype(np.uint8)).resize((S, S), Image.LANCZOS)
            ImageDraw.Draw(t).text((6, 4), photo.LABEL.get(m, m), fill=(255, 255, 0))
            out.paste(t, ((2 + k) * S, r * S))
    out.save(f"{R}/mm_05_scan_normals.png")
    print(f"{R}/mm_05_scan_normals.png")


def gains(models):
    """The render calibration's gains x k on the scan: the calibrated normal's angle to truth, trusted regions and face."""
    print("render-calibrated normals on the scan, gains x k: angle to truth deg, trusted regions | all face regions  (raw model; mean head)")
    for m in models:
        txt = []
        for k in (0.0, 1.0, 1.5, 2.0, 3.0):
            photo.GSCALE = k
            a = []
            for iid in cams():
                f = mm.PRED / m / f"{iid}.npz"
                it = item(iid)
                N = np.load(f)["normal"]
                s = photo.stats(N, it, photo.flips(m), m, iid.split("_")[1])
                fa = np.mean([s[r]["cal"] * s[r]["n"] for r in photo.REGS if r in s]) / np.mean([s[r]["n"] for r in photo.REGS if r in s])
                fr = np.mean([s[r]["ang"] * s[r]["n"] for r in photo.REGS if r in s]) / np.mean([s[r]["n"] for r in photo.REGS if r in s])
                a.append((s["trusted"]["cal"], fa, s["trusted"]["ang"], fr))
            a = np.mean(a, 0)
            txt.append(f"x{k:g} {a[0]:4.1f} | {a[1]:4.1f}")
        print(f"{m:13s} " + "   ".join(txt) + f"   (raw {a[2]:4.1f} | {a[3]:4.1f})")
    photo.GSCALE = 1.0


def depth(models):
    print("DEPTH on the scan (truth), mm rms along the view after scale + shift on the face | the mean head's | corr, gain of deviations from the mean head")
    for m in models:
        acc = []
        for iid in cams():
            f = mm.PRED / m / f"{iid}.npz"
            if f.exists():
                pr = dict(np.load(f))
                if "depth" in pr or "points" in pr:
                    acc.append(photo.depth_stats(pr, item(iid), photo.inv(m)))
        for k in ("face",) + photo.TRUST + ("chin", "brow"):
            v = np.array([[x[k][q] for q in ("model", "mean", "corr", "gain")] for x in acc if k in x])
            if len(v):
                print(f"{m:9s} scan ({len(v)}) {k:9s} | {v[:, 0].mean():5.2f} {v[:, 1].mean():5.2f} | {v[:, 2].mean():5.2f} {v[:, 3].mean():5.2f}  (sd of corr {v[:, 2].std():.2f})")


if __name__ == "__main__":
    ms = sys.argv[2:] or ["david", "marigold", "marigold_lcm", "moge2"]
    {"prep": prep, "render": render, "stats": lambda: stats(ms), "sheet": lambda: sheet(ms), "gains": lambda: gains(ms), "depth": lambda: depth(ms)}[sys.argv[1]]()
