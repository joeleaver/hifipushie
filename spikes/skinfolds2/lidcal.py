"""lidcal.py <head> <tag> <amount> [shift=1.6] [hood=0] [roll=1]: how DARK our own lid crease renders, read as the
picture's is (skin_read._lid_read -> lidfold.read_lid on the render at its full size, the front view, the picture's
fitted light). The head (a copy sg_lc_<tag>, smooth young skin) gets skin.folds.lid_fold at `amount` with `shift` mm on
both sides. Prints the darkness per column and side beside the picture's own (the calibration of the crease's
occlusion colour / width and of skin_read.LID_REF), and saves the eye crops (render | picture) to $G/out/lidcal_<tag>.png."""
import json, os, sys
import numpy as np
from PIL import Image
from hifipushie import skin_read as sr, skin_folds as sf, skin as skinmod, blockin as bi, store

head, tag, amount = sys.argv[1], sys.argv[2], float(sys.argv[3])
kw = dict(a.split("=") for a in sys.argv[4:])
G = os.environ["G"] + "/out"
vm = f"sg_lc_{tag}"
bi.fork(head, vm, replace=True)
sp = store.load(vm)
sh = float(kw.get("shift", 1.6))
sk = {"sex": 0, "age": 22, "tone": {"fitzpatrick": 1}, "wrinkles": {"amount": 0}}
if amount > 0:
    sk["folds"] = {"lid_fold": {"amount": amount, "roll": float(kw.get("roll", 1)), "L": {"shift": [sh] * 3}, "R": {"shift": [sh] * 3},
                                **({"hood": float(kw["hood"])} if float(kw.get("hood", 0)) else {})}}
sp["skin"] = sk; sp["paint"] = {}
store.save(vm, sp, "skinfolds2 lid calibration")
front = bi._front(bi._refs(vm))
frames = sr.capture(vm, views=[front], log=lambda s: None)
c = sr.context(vm, frames=frames, log=lambda s: None)
J = skinmod._joints(c.st)
nominal = sf.paths(c.st, "body", J, None, names=["lid_fold"])
lash = sr._lid_read(c, nominal)
for sd, q in lash.items():
    cols = q["lash"]["columns"]
    print(f"lid_fold{sd} amount {amount}: OURS dark {[c_['dark_ours'] for c_ in cols]} at {[c_['tps_ours'] for c_ in cols]} mm | PICTURE dark {[c_['dark'] for c_ in cols]} at {[c_['tps'] for c_ in cols]} mm"
          f" | median ours {np.median([c_['dark_ours'] for c_ in cols]):.3f} picture {np.median([c_['dark'] for c_ in cols]):.3f}")
f = frames[0]
R2 = f["R2"]
n = R2.shape[0]
P = Image.open(f["image"]).convert("RGB").crop(tuple(int(round(x)) for x in f["box"])).resize((n, n), Image.LANCZOS)
g = np.asarray(c.views[0]["gain"])
Rg = np.round(255 * sr._srgb(np.clip(sr._lin(R2 / 255.0) * g, 0, 1))).astype(np.uint8)
y0, y1 = int(float(kw.get("y0", 0.26)) * n), int(float(kw.get("y1", 0.42)) * n)
x0, x1 = int(0.2 * n), int(0.8 * n)
im = np.concatenate([Rg[y0:y1, x0:x1], np.asarray(P)[y0:y1, x0:x1]], 0)
Image.fromarray(im).resize((im.shape[1] * 2, im.shape[0] * 2), Image.LANCZOS).save(f"{G}/lidcal_{tag}.png")
print(f"{G}/lidcal_{tag}.png")
