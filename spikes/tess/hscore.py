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
def bald(frames):
    """The same stage with its hair objects hidden (the stage's blend carries the synced groom)."""
    import tempfile
    from pathlib import Path
    from hifipushie import scene
    sn = stage.ensure(name, with_hair=False)  # (a stage synced without the groom)
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        fr = [{**f, "out": str(Path(tmp) / f"{f['name']}.png")} for f in frames]
        job = {"blend": str(scene.blend_path(sn)), "views": fr, "size": PX, "samples": 24, "hide": ["hair"], "flat": False,
               "transparent": True, "mode": "render", "lighting": {**LIGHT, "target": fr[0]["center"]}}
        scene._blender(job, 2400)
        for f in fr:
            im = Image.open(f["out"]).convert("RGBA")
            bg = Image.new("RGBA", im.size, tuple(int(255 * 0.86) for _ in range(3)) + (255,))
            out[f["name"]] = Image.alpha_composite(bg, im).convert("RGB").copy()
    return out


off = bald(frames)
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
    b = np.asarray(off[f"v{v}"]).astype(float) / 255
    print("  on/off diff max", float(np.abs(a - b).sum(-1).max()), "on mean", float(a.mean()), "off mean", float(b.mean()))
    on[f"v{v}"].save(f"{T}/out/hs_on_{v}.png"); off[f"v{v}"].save(f"{T}/out/hs_off_{v}.png")
    # our hair by colour (the stage's blend keeps its groom whatever the job hides): dark, or the grey wisps' low
    # saturation off the light background; the face's own dark bits (brows, eyes, nostrils) are small blobs: dropped
    La_ = a @ [0.299, 0.587, 0.114]
    mo = (La_ < 0.36) | ((a.max(-1) - a.min(-1) < 0.06) & (La_ < 0.62))
    mo = ndi.binary_closing(ndi.binary_opening(mo, iterations=1), iterations=2)
    lab, n = ndi.label(mo)
    sz = ndi.sum(mo, lab, range(1, n + 1))
    mo = np.isin(lab, 1 + np.flatnonzero(sz > 0.03 * sz.max())) if n else mo
    cam = refs["cameras"][v]
    mm = cam["t"][2] / cam["f"] * 1000 * H / PX
    iou = (mh & mo).sum() / max((mh | mo).sum(), 1)
    eh, eo = mh ^ ndi.binary_erosion(mh), mo ^ ndi.binary_erosion(mo)
    dh, do = ndi.distance_transform_edt(~eh), ndi.distance_transform_edt(~eo)
    ch = 0.5 * (do[eh].mean() + dh[eo].mean()) * mm
    print(f"view {v} ({TR[v]}): IoU {iou:.3f}  outline chamfer {ch:.1f} mm  hers {mh.sum()} px, ours {mo.sum()} px")
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
            print(f"   {rn:12s} {side}: extra {100 * (mo & ~mh & m).sum() / max(her, 1):5.1f}%  missing "
                  f"{100 * (mh & ~mo & m).sum() / max(her, 1):5.1f}%  flow diff {np.median(d) if len(d) else float('nan'):5.1f} deg (n {len(d)})")
    vis = np.zeros((PX, PX, 3))
    vis[..., 0] = mh
    vis[..., 2] = mo
    out = Image.new("RGB", (PX * 3, PX))
    out.paste(Image.fromarray((P * 255).astype(np.uint8)), (0, 0))
    out.paste(on[f"v{v}"].resize((PX, PX)), (PX, 0))
    out.paste(Image.fromarray((vis * 255).astype(np.uint8)), (2 * PX, 0))
    out.save(f"{T}/out/hscore_{name}_{v}.png")
