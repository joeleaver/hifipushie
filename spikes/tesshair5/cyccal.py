"""cyccal.py <model> [look='{json}'] [engine=cycles] [views=0,2] [size=512] [samples=24] [tag=x]: the hair's LOOK
measured against her pictures, like with like: the model's current hair (look merged with `look`) on the shared stage
through the references' fitted cameras under the fitted photo light, and inside each hair mask (ours: the ID pass;
hers: the trace's mask and hscore's hair-pixel classifier) the colour of three luminance bands (shadow 0-20 %, mid
40-60, highlight 85-98; hscore's `bands`) + the mean, as sRGB hex and as L (0..100, CIE L*) / chroma hue.
Prints one line a view; saves $TOUT/cyc_<model>_<tag>_v<n>.png. JSON summary on the last line (fit.py reads it)."""
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

T, TOUT = os.environ["T"], os.environ["TOUT"]
TR = {0: "trace_front", 1: "trace_tq", 2: "trace_profile"}
W, H = 1152, 1536
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]


def lin(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lab(rgb):
    """sRGB 0..1 -> (L*, chroma, hue deg)."""
    r = lin(rgb)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    x, y, z = (M @ r) / np.array([0.9505, 1.0, 1.089])
    f = lambda t: np.cbrt(t) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
    L, a, b = 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))
    return float(L), float(np.hypot(a, b)), float(np.degrees(np.arctan2(b, a)))


def bands(img, m):
    m = ndi.binary_erosion(m, iterations=2)
    L = img @ [0.299, 0.587, 0.114]
    out = []
    for lo, hi in ((0, 20), (40, 60), (85, 98)):
        a0, a1 = np.percentile(L[m], [lo, hi])
        out.append(img[m & (L >= a0) & (L <= a1)].mean(0))
    out.append(img[m].mean(0))
    return out


def hexs(c):
    return "#%02x%02x%02x" % tuple(int(round(255 * float(x))) for x in c)


def main():
    name = sys.argv[1]
    kw = dict(a.split("=", 1) for a in sys.argv[2:])
    views = [int(v) for v in kw.get("views", "0,2").split(",")]
    eng, PX = kw.get("engine", "cycles"), int(kw.get("size", 512))
    tag = kw.get("tag", "x")
    spec = store.load(name)
    if kw.get("look"):
        lk_ = kw["look"]
        spec["hair"]["look"] = {**(spec["hair"].get("look") or {}), **json.loads(open(lk_[1:]).read() if lk_.startswith("@") else lk_)}
    refs = json.loads((store.HOME / name / "human_refs.json").read_text())
    sn = stage.ensure(os.environ.get("STAGE_MODEL", "th_T04"))
    st = json.loads((store._dir(sn) / "spec.json").read_text())
    st["hair"] = spec["hair"]
    res = {}
    with resources.heavy(f"tesshair5 cyccal {name}", gb=8), tempfile.TemporaryDirectory() as tmp:
        for v in views:
            f = stage.fitted_frame(refs["cameras"][v], BOX, f"v{v}")
            fr = {**f, "out": str(Path(tmp) / f"v{v}.png")}
            idv = {**f, "out": str(Path(tmp) / f"v{v}_id.png")}
            lt = stage.photo_light(name, v)
            job = {"blend": str(scene.blend_path(sn)), "views": [fr], "size": PX, "samples": int(kw.get("samples", 24)), "hide": [],
                   "flat": False, "transparent": True, "lighting": {**lt, "target": fr["center"]}, "eevee": stage.STAGE_EEVEE,
                   "mode": "hair_look", "hair": hair.job(sn, st), "clay_views": [], "id_views": [idv], "look_engine": eng}
            if eng == "cycles":  # (as hair.look_hair renders strands: the spikes' stage.shoot left Cycles at 2
                # transmission bounces, which "leaves fair hair grey and dark hair flat": the dark Cycles columns)
                job.update(hair_bounces=int(kw.get("bounces", 10)), denoise=True, adaptive_threshold=0.01,
                           samples=int(kw.get("samples", 64)))
            scene._blender(job, 3600)
            im = Image.open(fr["out"])
            if im.mode == "RGBA":
                bg = Image.new("RGBA", im.size, tuple(int(255 * min(1.0, c)) for c in lt.get("backdrop", [0.86, 0.86, 0.86])) + (255,))
                im = Image.alpha_composite(bg, im)
            im = im.convert("RGB")
            im.save(f"{TOUT}/cyc_{name}_{tag}_v{v}.png")
            a = np.asarray(im, float) / 255
            idm = np.asarray(Image.open(idv["out"]).convert("RGBA"), float)
            mo = (idm[..., 3] > 127) & (idm[..., :3].max(-1) > 60)
            tr = json.load(open(f"{T}/{TR[v]}.json"))
            sq = Image.new("RGB", (H, H), (200, 200, 200))
            sq.paste(Image.open(tr["photo"]).convert("RGB"), (int(-BOX[0]), 0))
            P = np.asarray(sq.resize((PX, PX), Image.LANCZOS)).astype(float) / 255
            hm = Image.new("L", (H, H), 0)
            hm.paste(Image.open(f"{T}/{TR[v]}_mask.png").convert("L"), (int(-BOX[0]), 0))
            mh = np.asarray(hm.resize((PX, PX))) > 127
            Lc = P @ [0.299, 0.587, 0.114]
            bgc = np.median(P[:20, -20:].reshape(-1, 3), 0)
            raw_h = ((Lc < 0.42) & (P[..., 0] >= P[..., 2] - 0.02)) | ((Lc < 0.5) & (P.max(-1) - P.min(-1) > 0.12)
                                                                    & (np.abs(P - bgc).sum(-1) > 0.25) & (P[..., 0] - P[..., 2] > 0.09))
            raw_h &= mh
            # (the dense hair only, where both have hair: thin wisps over skin are skin-coloured pixels in a path
            # tracer's render, and her classifier's edge pixels are backdrop-tinted)
            core = ndi.binary_erosion(mo & mh, iterations=max(2, PX // 128))
            bh, bo = bands(P, raw_h & core), bands(a, core)
            res[v] = {"hers": [list(map(float, c)) for c in bh], "ours": [list(map(float, c)) for c in bo]}
            print(f"v{v} {eng}: hers " + " ".join(hexs(c) for c in bh) + " | ours " + " ".join(hexs(c) for c in bo))
            print("      L* C h  hers " + " ".join("%.0f/%.0f/%.0f" % lab(c) for c in bh) + " | ours "
                  + " ".join("%.0f/%.0f/%.0f" % lab(c) for c in bo), flush=True)
    print("JSON " + json.dumps(res))


main()
