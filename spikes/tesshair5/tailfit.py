"""tailfit.py <model> [<model> ...]: the TAIL measured against her mask, like with like through the profile's fitted
camera (and the three-quarter's): our hair's ID mask against the trace's hair mask ($T/trace_*_mask.png), both cut at
the tie (its pixel read off her picture: TIE below). Per view, hers | ours:
  below   px of hair below the tie's row (the tail + the nape's hair)
  length  mm from the tie down to the mask's lowest rows (the 99th percentile row)
  width   mm: the widest stretch across the tail (the 90th percentile of the row widths below tie + 15 mm)
  back    mm the hair reaches behind the tie's column
and the whole mask's IoU. Prints one line a model and view; saves $TOUT/tailfit_<model>_<view>.png (hers red, ours
blue, both purple, the tie's cross)."""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

import stage
from hifipushie import hair, resources, scene, store

T = os.environ["T"]
TOUT = os.environ["TOUT"]
TR = {1: "trace_tq", 2: "trace_profile"}
TIE = {2: (875, 545), 1: (905, 550)}  # the tie's pixel in her 1152 x 1536 pictures (profile_left, three_quarter_left)
W, H = 1152, 1536
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]
PX = 768


def idmask(name, frames):
    """Our hair's pixels: blender_scene.hair_look's ID pass (hair objects flat red / green, everything else black) of
    the model's CURRENT hair on the shared stage. (A stage's own .blend keeps the hair it was built with: hscore's
    ID pass through mode "render" measures THAT, stale after a regrow.)"""
    spec = store.load(name)
    sn = stage.ensure(os.environ.get("STAGE_MODEL", "th_T04"))
    st = json.loads((store._dir(sn) / "spec.json").read_text())
    st["hair"] = spec["hair"]
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        fr = [{**f, "out": str(Path(tmp) / f"{f['name']}.png")} for f in frames]
        idv = [{**f, "out": str(Path(tmp) / f"{f['name']}_id.png")} for f in frames]
        job = {"blend": str(scene.blend_path(sn)), "views": fr[:1], "size": PX, "samples": 1, "hide": [], "flat": False,
               "transparent": True, "lighting": {**stage.FRONT_LIGHT, "target": fr[0]["center"]}, "eevee": stage.STAGE_EEVEE,
               "mode": "hair_look", "hair": hair.job(sn, st), "clay_views": [], "id_views": idv, "look_engine": "eevee"}
        scene._blender(job, 2400)
        for f in idv:
            a = np.asarray(Image.open(f["out"]).convert("RGBA"), float)
            if os.environ.get("KEEP_ID"):
                Image.open(f["out"]).save(f"{TOUT}/tailfit_id_{name}_{f['name']}.png")
            out[f["name"]] = (a[..., 3] > 127) & (a[..., :3].max(-1) > 60)
    return out


def measure(m, tx, ty, mm):
    rows = np.nonzero(m.any(1))[0]
    below = m[ty:]
    ys = np.nonzero(below.any(1))[0]
    if not len(ys):
        return {"below": 0, "length": 0.0, "width": 0.0, "back": 0.0}
    cnt = below.sum(1)
    yy = np.repeat(np.arange(len(cnt)), cnt)
    length = float(np.percentile(yy, 99)) * mm
    k = int(15 / mm)
    wd = below[k:].sum(1)
    wd = wd[wd > 0]
    xs = np.nonzero(m.any(0))[0]
    del rows
    return {"below": int(below.sum()), "length": length, "width": float(np.percentile(wd, 90)) * mm if len(wd) else 0.0,
            "back": float(xs.max() - tx) * mm}


def main():
    views = [int(v) for v in os.environ.get("VIEWS", "2,1").split(",")]
    for name in sys.argv[1:]:
        refs = json.loads((store.HOME / name / "human_refs.json").read_text())
        frames = [stage.fitted_frame(refs["cameras"][v], BOX, f"v{v}") for v in views]
        with resources.heavy(f"tesshair5 tailfit {name}", gb=6):
            ids = idmask(name, frames)
        for v in views:
            hm = Image.new("L", (H, H), 0)
            hm.paste(Image.open(f"{T}/{TR[v]}_mask.png").convert("L"), (int(-BOX[0]), 0))
            mh = np.asarray(hm.resize((PX, PX))) > 127
            mo = ndi.binary_closing(ndi.binary_opening(ids[f"v{v}"], iterations=1), iterations=3)
            cam = refs["cameras"][v]
            mm = cam["t"][2] / cam["f"] * 1000 * H / PX
            tx, ty = int((TIE[v][0] - BOX[0]) * PX / H), int(TIE[v][1] * PX / H)
            a, b = measure(mh, tx, ty, mm), measure(mo, tx, ty, mm)
            iou = (mh & mo).sum() / max((mh | mo).sum(), 1)
            print(f"{name} v{v}: IoU {iou:.3f} | below hers {a['below']} ours {b['below']} ({100 * (b['below'] / max(a['below'], 1) - 1):+.0f}%)"
                  f" | length {a['length']:.0f} / {b['length']:.0f} mm | width {a['width']:.0f} / {b['width']:.0f} mm"
                  f" | back {a['back']:.0f} / {b['back']:.0f} mm", flush=True)
            im = np.full((PX, PX, 3), 235, np.uint8)
            im[mh & ~mo] = (220, 90, 90)
            im[mo & ~mh] = (90, 110, 220)
            im[mh & mo] = (150, 90, 170)
            im[max(ty - 1, 0):ty + 2, max(tx - 12, 0):tx + 13] = 0
            im[max(ty - 12, 0):ty + 13, max(tx - 1, 0):tx + 2] = 0
            Image.fromarray(im).save(f"{TOUT}/tailfit_{name}_{v}.png")


main()
