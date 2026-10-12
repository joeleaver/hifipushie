"""jval.py [--photo] <model>...: the JAW-UNDER read (face_ruler._jaw_obs) validated.
default: the picture = the model's own dressed shot through each fitted front / 3/4 camera (the judging sheets' cached
  d_<model>_<view>.png in $SHOTS dirs), the reader's model = (a) the same head: every read's truth is 0 mm (NULL: bias,
  rms); (b) the head with a KNOWN change (mm:chin_width +5, mm:chin_length +4, mm:jaw_width +6, mm:under_chin +4, a
  random |dc| 3): the reads must equal J (-change): slope, corr, residual rms.
--photo: on the model's reference pictures (what a solve would get): counts, mean, rms, an overlay.
Overlays: $OUT/jval_<model>.png (green = the model's contour point, yellow line to the picture's step in red)."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import blockin as bi, face_ruler as fr, store, gnm_mm

OUT = os.environ.get("OUT", "/mnt/data/hifipushie/solvereads/out")
SHOTS = os.environ.get("SHOTS", "/mnt/data/hifipushie/reruns/out:/mnt/data/hifipushie/garrettgood/out").split(":")
photo = "--photo" in sys.argv
models = [a for a in sys.argv[1:] if not a.startswith("--")]
rng = np.random.default_rng(3)
rnd = rng.normal(0, 1, 170)
rnd *= 3.0 / np.linalg.norm(rnd)
CH = {"chin_width+5": 5 * gnm_mm.direction("chin_width"), "chin_length+4": 4 * gnm_mm.direction("chin_length"),
      "jaw_width+6": 6 * gnm_mm.direction("jaw_width"), "under_chin+4": 4 * gnm_mm.direction("under_chin"), "random3": rnd}


def jaw(head, view):
    return [o for o in fr.observe(head, [dict(view, jaw=True, limbus=False)], outline=False, colour=False) if o["type"] == "jaw"]


def draw(img, obs, k=1.0):
    t = img.copy()
    d = ImageDraw.Draw(t)
    for x in obs:
        d.line([tuple(x["p"]), tuple(x["q"])], fill=(255, 235, 0), width=2)
        d.ellipse([x["p"][0] - 2, x["p"][1] - 2, x["p"][0] + 2, x["p"][1] + 2], fill=(0, 220, 0))
        d.ellipse([x["q"][0] - 2, x["q"][1] - 2, x["q"][0] + 2, x["q"][1] + 2], fill=(255, 0, 0))
    return t


def stat(o):
    o = np.asarray(o, float)
    return f"n {len(o):3d}  bias {o.mean():+5.2f}  rms {np.sqrt((o ** 2).mean()):5.2f}  p90 {np.percentile(np.abs(o), 90):5.2f}" if len(o) else "n   0"


tot = {}
for m in models:
    spec, rj = store.load(m), bi._refs(m)
    head = fr.model_head(spec)
    tiles = []
    if photo:
        _, views, _ = fr.reference_views(m, parse=False, anchors="none")
        for v in views:
            if v["kind"] == "profile":
                continue
            ob = jaw(head, v)
            print(f"{m:10s} {v['kind']:6s} PHOTO  {stat([x['o'] for x in ob])}  step {np.mean([x['step'] for x in ob]) if ob else 0:.3f}")
            xs = [x["p"] for x in ob] or [[0, 0], list(v["img"].size)]
            cx, cy = np.mean(xs, 0)
            r = 0.75 * max(np.ptp(np.array(xs)[:, 0]), 200)
            tiles.append(draw(v["img"], ob).crop((int(cx - r), int(cy - r), int(cx + r), int(cy + r))).resize((700, 700), Image.LANCZOS))
    else:
        for vi, (v, cam, box) in enumerate(zip(rj["views"], rj["cameras"], rj["blockin"]["boxes"])):
            f = next((f"{d}/d_{m}_{vi}.png" for d in SHOTS if os.path.exists(f"{d}/d_{m}_{vi}.png")), None)
            kind = fr.kind_of(v.get("yaw", 0))
            if f is None or kind == "profile":
                continue
            shot = Image.open(f).convert("RGB")
            ib = [int(round(x)) for x in box]
            sc = shot.size[0] / float(ib[2] - ib[0])
            view = {"cam": cam, "kind": kind, "style": "photo", "hair": False, "face_only": True, "scale": sc, "origin": (ib[0], ib[1]), "img": shot}
            ob = jaw(head, view)
            o = [x["o"] for x in ob]
            print(f"{m:10s} {kind:6s} NULL   {stat(o)}")
            tot.setdefault((kind, "null"), []).append(np.array(o))
            tiles.append(draw(shot, ob).resize((700, 700), Image.LANCZOS))
            for nm, dlt in CH.items():
                h2 = head["rebuild"](head["c"] + dlt)
                ob2 = jaw(h2, view)
                if len(ob2) < 4:
                    print(f"{m:10s} {kind:6s} {nm:14s} n {len(ob2)}")
                    continue
                o2 = np.array([x["o"] for x in ob2])
                pr = np.array([x["J"] @ (-dlt) for x in ob2])
                sl = float(o2 @ pr / max(pr @ pr, 1e-12))
                print(f"{m:10s} {kind:6s} {nm:14s} n {len(o2):3d}  predicted rms {np.sqrt((pr ** 2).mean()):.2f}  read rms {np.sqrt((o2 ** 2).mean()):.2f}  "
                      f"slope {sl:+.2f}  corr {np.corrcoef(o2, pr)[0, 1]:+.2f}  residual rms {np.sqrt(((o2 - pr) ** 2).mean()):.2f}")
                tot.setdefault((kind, nm), []).append(np.c_[o2, pr])
    if tiles:
        Wd = Image.new("RGB", (700 * len(tiles), 700))
        for i, t_ in enumerate(tiles):
            Wd.paste(t_, (700 * i, 0))
        Wd.save(f"{OUT}/jval_{'photo_' if photo else ''}{m}.png")
if tot:
    print("\nALL MODELS:")
    for (kind, nm), L in sorted(tot.items()):
        if nm == "null":
            print(f"  {kind:6s} NULL            views {len(L):2d}  {stat(np.concatenate(L))}")
        else:
            A = np.concatenate(L)
            o2, pr = A[:, 0], A[:, 1]
            print(f"  {kind:6s} {nm:14s}  n {len(A):4d}  predicted rms {np.sqrt((pr ** 2).mean()):.2f}  slope {float(o2 @ pr / (pr @ pr)):+.2f}  "
                  f"corr {np.corrcoef(o2, pr)[0, 1]:+.2f}  residual rms {np.sqrt(((o2 - pr) ** 2).mean()):.2f}")
