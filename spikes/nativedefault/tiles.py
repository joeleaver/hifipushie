"""tiles.py <model> [boxes=<model>] [light=<model>] [hair=1] [feats=..] [tile=640] [sub=dressed]: DRESSED EEVEE tiles
of a model, one small file per feature and view, through ITS OWN fitted cameras, for looking at one at a time:
  $G/out/<model>/<sub>/<feature>_v<i>.png (+ <feature>_v<i>_ref.png: the painting's own crop)
features (hair off): eyes, eyeR, eyeL, nose, mouth, chin, mouth_chin, chin_jaw, brow_forehead, face
[views=0,1] [vlight=<view>] [suffix=..]; with hair=1 (hair on): head_v0, head_v1 (the whole head through the fitted cameras) and the unseen angles profile,
three_quarter_other (no reference).
boxes=<model>: the crop boxes (picture pixels) of ANOTHER model's landmarks, so two models' tiles are the same crop of
the same picture. light=<model>: that model's fitted light at the picture's measured exposure (skin_read.photo_light:
needs a skin read on it; the judging template's -0.55 EV reads as a tan)."""
import os
import sys

import numpy as np
from PIL import Image

_S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_S, "garrett3"), os.path.join(_S, "tour")]
import stage  # noqa: E402
import tour  # noqa: E402,F401

from hifipushie import blockin as bi, humanfit, resources, skin_read, store  # noqa: E402

F = bi.FEATURES
F.setdefault("face", {"lm": list(range(0, 68)), "pairs": [], "lines": [], "stages": (), "squint_mm": 6.0, "pad": 1.25})
F.setdefault("eyeR", {"lm": list(range(36, 42)) + [17, 21], "pairs": [], "lines": [], "stages": (), "squint_mm": 2.0, "pad": 1.5})
F.setdefault("eyeL", {"lm": list(range(42, 48)) + [22, 26], "pairs": [], "lines": [], "stages": (), "squint_mm": 2.0, "pad": 1.5})
F.setdefault("mouth_chin", {"lm": list(range(48, 68)) + [6, 7, 8, 9, 10, 33], "pairs": [], "lines": [], "stages": (), "squint_mm": 3.0, "pad": 1.35})
G = "/mnt/data/hifipushie/nativedefault/out"


def head_box(L2):
    lo, hi = L2.min(0), L2.max(0)
    w = float(max(hi - lo))
    c = 0.5 * (lo + hi)
    s = 1.75 * w
    return (c[0] - s / 2, c[1] - 0.16 * w - s / 2, c[0] + s / 2, c[1] - 0.16 * w + s / 2)


def boxes_of(m, feats):
    spec, rj = store.load(m), bi._refs(m)
    VI = list(range(len(rj["views"])))
    meshes = bi._per_view(spec["base"], rj, VI, lambda b: bi.presented_mesh(b, rj=rj))
    out = {}
    for vi in VI:
        L2 = humanfit.project(rj["cameras"][vi], meshes[vi]["state"]["L"])
        for f in feats:
            out[(f, vi)] = [float(x) for x in (head_box(L2) if f == "head" else bi._feature_box(f, L2))]
    return out


def main():
    m = sys.argv[1]
    kw = dict(a.split("=", 1) for a in sys.argv[2:])
    T = int(kw.get("tile", 640))
    out = f"{G}/{m}/{kw.get('sub', 'dressed')}"
    os.makedirs(out, exist_ok=True)
    feats = [f for f in kw.get("feats", "eyes,eyeR,eyeL,nose,mouth,chin,mouth_chin,chin_jaw,brow_forehead,face").split(",") if f]
    hair_on = kw.get("hair", "1") == "1"
    rj = bi._refs(m)
    VI = [int(x) for x in kw["views"].split(",")] if kw.get("views") else list(range(len(rj["views"])))
    B = boxes_of(kw.get("boxes", m), feats + ["head"])
    sfx = kw.get("suffix", "")
    lm = kw.get("light", m)
    spec = store.load(m)
    for vi in VI:
        cam = rj["cameras"][vi]
        light = skin_read.photo_light(lm, int(kw.get("vlight", vi)))   # vlight=0: the front picture's light on every view
        print(f"view {vi}: light of {lm}, exposure {light.get('exposure'):+.2f} EV (measured: {light.get('measured')})")
        fr = [stage.fitted_frame(cam, B[(f, vi)], f"{f}_v{vi}") for f in feats]
        with resources.heavy(f"nativedefault tiles {m} v{vi}", gb=6):
            own = stage.shoot(m, fr, light, size=T, hair_on=False) if fr else {}
            if hair_on and spec.get("hair"):
                hf = [stage.fitted_frame(cam, B[("head", vi)], f"head_v{vi}")]
                if vi == 0:
                    hf += stage.view_frames(spec, names=("profile_right", "three_quarter_other"))
                own.update(stage.shoot(m, hf, light, size=T, hair_on=True))
        for k, im in own.items():
            im.convert("RGB").resize((T, T), Image.LANCZOS).save(f"{out}/{k}{sfx}.png")
            print(f"{out}/{k}{sfx}.png")
        img = Image.open(rj["views"][vi]["image"]).convert("RGB")
        for f in feats + ["head"]:
            img.crop(tuple(int(round(x)) for x in B[(f, vi)])).resize((T, T), Image.LANCZOS).save(f"{out}/{f}_v{vi}_ref.png")


main()
