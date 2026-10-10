"""hscore.py <model> [views csv: 0,1,2]: the hair scored against the traces, like with like through each fitted
camera: the model's stage rendered with and without its groom (the difference = our hair's mask), against the trace's
hair mask (trace.py) of that picture:
  silhouette: IoU, and the chamfer between the two masks' outlines (mean of both directions, mm at the head)
  coverage by region (rows / columns relative to the face): hair where hers has none (+) / missing (-), % of hers
  flow: the structure-tensor strand angle on our render vs the photo's, inside both masks, per region (deg, |diff|)
Saves $T/out/hscore_<model>_<view>.png (photo | ours | masks: hers red, ours blue, both purple)."""
import json, os, sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

import stage
from hifipushie import store

T = os.environ["T"]
TOUT = os.environ.get("TOUT", f"{T}/out")  # (where the sheets go: the traces stay in $T)
name = sys.argv[1]
views = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "0,1,2").split(",")]
TR = {0: "trace_front", 1: "trace_tq", 2: "trace_profile"}
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
W, H = 1152, 1536
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]  # the square around the whole picture
PX = 768
LIGHT = {**stage.FRONT_LIGHT, "exposure": -0.1}


def orient(L, mask):
    g = ndi.gaussian_filter(L, 1.0)
    gx, gy = ndi.sobel(g, 1), ndi.sobel(g, 0)
    J = [ndi.gaussian_filter(v, 3.0) for v in (gx * gx, gy * gy, gx * gy)]
    ang = (0.5 * np.arctan2(2 * J[2], J[0] - J[1]) + np.pi / 2) % np.pi
    coh = np.sqrt((J[0] - J[1]) ** 2 + 4 * J[2] ** 2) / np.maximum(J[0] + J[1], 1e-9)
    return ang, coh


frames = [stage.fitted_frame(refs["cameras"][v], BOX, f"v{v}") for v in views]
def idmask(frames):
    """Our hair as an ID pass (blender_scene's id_parts: every object of the named parts flat white, everything else
    flat black, transparent background): hair = opaque AND black. No luminance enters (the stage's hair objects carry
    no part of their own)."""
    import tempfile
    from pathlib import Path
    from hifipushie import scene
    sn = stage.ensure(name)
    st = json.loads((store._dir(sn) / "spec.json").read_text())
    white = {p: [1.0, 1.0, 1.0] for p in list(st.get("parts") or {}) + ["body"] if p != "hair"}
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        fr = [{**f, "out": str(Path(tmp) / f"{f['name']}.png")} for f in frames]
        job = {"mode": "render", "blend": str(scene.blend_path(sn)), "views": fr, "size": PX, "samples": 4, "hide": [],
               "flat": True, "transparent": True, "id_parts": white}
        scene._blender(job, 2400)
        for f in fr:
            a = np.asarray(Image.open(f["out"]).convert("RGBA"), float)
            out[f["name"]] = (a[..., 3] > 127) & (a[..., :3].max(-1) < 60)
    return out


ids = idmask(frames)
on = stage.shoot(name, frames, LIGHT, size=PX, hair_on=True)
for v in views:
    tr = json.load(open(f"{T}/{TR[v]}.json"))
    photo = Image.open(tr["photo"]).convert("RGB")
    sq = Image.new("RGB", (H, H), (200, 200, 200))
    sq.paste(photo, (int(-BOX[0]), 0))
    P = np.asarray(sq.resize((PX, PX), Image.LANCZOS)).astype(float) / 255
    hm = Image.new("L", (H, H), 0)
    hm.paste(Image.open(f"{T}/{TR[v]}_mask.png").convert("L"), (int(-BOX[0]), 0))
    mh = np.asarray(hm.resize((PX, PX))) > 127
    a = np.asarray(on[f"v{v}"]).astype(float) / 255
    raw_o = ids[f"v{v}"]  # our hair pixels, the ID pass (no luminance), unfilled
    mo = ndi.binary_closing(ndi.binary_opening(raw_o, iterations=1), iterations=3)
    # her hair PIXELS (the trace's classifier without its hole filling: the gaps between strands stay gaps)
    c = P
    Lc = c @ [0.299, 0.587, 0.114]
    bgc = np.median(c[:20, -20:].reshape(-1, 3), 0)
    raw_h = ((Lc < 0.42) & (c[..., 0] >= c[..., 2] - 0.02)) | ((Lc < 0.5) & (c.max(-1) - c.min(-1) > 0.12)
                                                            & (np.abs(c - bgc).sum(-1) > 0.25) & (c[..., 0] - c[..., 2] > 0.09))
    raw_h &= mh
    cam = refs["cameras"][v]
    mm = cam["t"][2] / cam["f"] * 1000 * H / PX
    iou = (mh & mo).sum() / max((mh | mo).sum(), 1)
    eh, eo = mh ^ ndi.binary_erosion(mh), mo ^ ndi.binary_erosion(mo)
    dh, do = ndi.distance_transform_edt(~eh), ndi.distance_transform_edt(~eo)
    ch = 0.5 * (do[eh].mean() + dh[eo].mean()) * mm
    print(f"view {v} ({TR[v]}): IoU {iou:.3f}  outline chamfer {ch:.1f} mm  hers {mh.sum()} px, ours {mo.sum()} px")
    # HAIRLINE: her hair within 15 mm of her face (the trace's face hull, grown) that is bare in ours
    if tr.get("face_hull"):
        from PIL import ImageDraw as _D
        hull = Image.new("L", (H, H), 0)
        _D.Draw(hull).polygon([(float(x) - BOX[0], float(y)) for x, y in tr["face_hull"]], fill=255)
        fh = np.asarray(hull.resize((PX, PX))) > 127
        band = mh & (ndi.distance_transform_edt(~fh) * mm < 15.0)
        bare = band & ~mo
        print(f"   hairline band (her hair within 15 mm of the face): {band.sum()} px, bare in ours {100 * bare.sum() / max(band.sum(), 1):.1f}%"
              f"  (unfilled: {100 * (band & ~raw_o).sum() / max(band.sum(), 1):.1f}%: scalp between strands counts)")
    # SCALP SHOWING (faces2): the ID pass counts a sparse fan of strands as hair (closed or not: one strand per few px
    # is "hair"), so a bare V under the part scored as covered. On the beauty render: skin-coloured pixels (warm,
    # light) inside HER hair mask, in the band within 30 mm of her face, ours vs hers (her photo the same way)
    if tr.get("face_hull"):
        band30 = ndi.binary_erosion(mh, iterations=2) & (ndi.distance_transform_edt(~fh) * mm < 30.0)

        def skin(img):
            r, g_, b = img[..., 0], img[..., 1], img[..., 2]
            Lx = img @ [0.299, 0.587, 0.114]
            return (Lx > 0.45) & (r - b > 0.12) & (r >= g_) & (g_ >= b)
        print(f"   scalp showing in her hair band (30 mm): ours {100 * (skin(a) & band30).sum() / max(band30.sum(), 1):.1f}%"
              f"  hers {100 * (skin(P) & band30).sum() / max(band30.sum(), 1):.1f}%")
    # FOREHEAD ARCH (faces3): the hair's lower edge over the forehead, per column, against her face hull's top (her
    # traced hair edge), front view: mm ours - hers (+ = our hair edge lower) across the forehead in 5 bins from her
    # right temple to her left, and the arch's height (the centre's edge over the temples' mean), ours and hers
    if tr.get("face_hull") and v == 0:
        top = np.where(fh.any(0), fh.argmax(0), PX)
        hi = int(top.min())
        cols = np.flatnonzero(top < hi + 35.0 / mm)
        start = (top[cols] + 30.0 / mm).astype(int)
        ours_e = np.full(len(cols), np.nan)
        for i, (cx, s) in enumerate(zip(cols, start)):
            colm = mo[: max(s, 1), cx]
            hit = np.flatnonzero(colm)
            if len(hit):
                ours_e[i] = hit.max()
        dif = (ours_e - top[cols]) * mm
        bins = np.array_split(np.arange(len(cols)), 5)
        prof = [float(np.nanmean(dif[b])) for b in bins]
        def arch(e):
            c = np.nanmean(e[bins[2]])
            return float((np.nanmean(np.r_[e[bins[0]], e[bins[4]]]) - c) * mm)
        print(f"   forehead arch: ours - hers (mm, + = ours lower), R temple .. L temple: "
              + " ".join(f"{p:+.1f}" for p in prof)
              + f"  | arch height (temples' edge below the centre's) hers {arch(top[cols].astype(float)):.1f} ours {arch(ours_e):.1f} mm")
    # COLOUR like with like: luminance bands (shadow 0-20 %, mid 40-60, highlight 85-98) inside each hair mask, eroded
    def bands(img, m):
        m = ndi.binary_erosion(m, iterations=2)
        L = img @ [0.299, 0.587, 0.114]
        out = []
        for lo, hi in ((0, 20), (40, 60), (85, 98)):
            a0, a1 = np.percentile(L[m], [lo, hi])
            out.append("#%02x%02x%02x" % tuple(int(255 * x) for x in img[m & (L >= a0) & (L <= a1)].mean(0)))
        return out
    print(f"   colour shadow / mid / highlight: hers {bands(P, raw_h)}  ours {bands(a, raw_o)}")
    # regions: by rows of the picture in thirds of the hair's own height, and left / right of the hair's centre
    ys, xs = np.nonzero(mh)
    y0, y1, xc = ys.min(), ys.max(), np.median(xs)
    yy, xx = np.mgrid[:PX, :PX]
    t = (yy - y0) / max(y1 - y0, 1)
    regs = {"top": t < 0.25, "upper sides": (t >= 0.25) & (t < 0.5), "lower": t >= 0.5}
    La, Lp = a @ [0.299, 0.587, 0.114], P @ [0.299, 0.587, 0.114]
    aa, ca = orient(La, mo)
    ap, cp = orient(Lp, mh)
    for rn, rm in regs.items():
        for side, sm in (("R", xx < xc), ("L", xx >= xc)):
            m = rm & sm
            her, our = (mh & m).sum(), (mo & m).sum()
            if her < 200 and our < 200:
                continue
            both = mh & mo & m & (ca > 0.3) & (cp > 0.3)
            d = np.abs(aa[both] - ap[both])
            d = np.degrees(np.minimum(d, np.pi - d))
            # coverage: how opaque the hair is there (0 = the background shows, 1 = solid hair), over the union of
            # both masks in the region: a dense sheet and airy wisps have the same outline, not the same coverage
            u = (mh | mo) & m
            # coverage = the share of the region's pixels (both masks' union) that ARE hair: a sheet ~1, wisps low
            cvh = float(raw_h[u].mean()) if u.sum() else float("nan")
            cvo = float(raw_o[u].mean()) if u.sum() else float("nan")
            print(f"   {rn:12s} {side}: coverage hers {cvh:.2f} ours {cvo:.2f} ({cvo - cvh:+.2f})  extra {100 * (mo & ~mh & m).sum() / max(her, 1):5.1f}%  missing "
                  f"{100 * (mh & ~mo & m).sum() / max(her, 1):5.1f}%  flow diff {np.median(d) if len(d) else float('nan'):5.1f} deg (n {len(d)})")
    vis = np.zeros((PX, PX, 3))
    vis[..., 0] = mh
    vis[..., 2] = mo
    out = Image.new("RGB", (PX * 3, PX))
    out.paste(Image.fromarray((P * 255).astype(np.uint8)), (0, 0))
    out.paste(on[f"v{v}"].resize((PX, PX)), (PX, 0))
    out.paste(Image.fromarray((vis * 255).astype(np.uint8)), (2 * PX, 0))
    out.save(f"{TOUT}/hscore_{name}_{v}.png")
