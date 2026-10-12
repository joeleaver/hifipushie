"""clay.py <model> <folds.json | - | ''> <tag> [az=0,35] [box=eyes|mouth|face] [px=0.25] [relief=geometry]
The skin part's exact FIELD ray-marched as clay (no mesh, no Blender; ~1 min a view): frontal light | raking light from
the side | raking light from above, per azimuth. '-' keeps the model's own skin.folds, '' strips them.
The fast loop for the folds' geometry (skin_folds.prims): what the field itself is, before any mesher."""
import json, os, sys, time
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import store, sdf, images
from hifipushie.spec import expand_mirror

name, folds, tag = sys.argv[1:4]
kw = dict(a.split("=") for a in sys.argv[4:])
G = os.environ.get("G", ".") + "/out"


def render(spec, part, az, centre, size, mmpx):
    prims = images.prims_on(spec, [part])
    lip = max([p.lip for p in prims] + [1.0])
    a = np.radians(az)
    d = np.array([-np.sin(a), np.cos(a), 0.0])           # the ray's direction (from the camera into the head)
    right = np.array([np.cos(a), np.sin(a), 0.0])
    up = np.array([0.0, 0.0, 1.0])
    w, h = int(size[0] / mmpx), int(size[1] / mmpx)
    xs = (np.arange(w) - w / 2 + 0.5) * mmpx * 0.001
    zs = (h / 2 - np.arange(h) - 0.5) * mmpx * 0.001
    O = centre + xs[None, :, None] * right + zs[:, None, None] * up - 0.09 * d
    P = O.reshape(-1, 3).copy()
    alive = np.ones(len(P), bool)
    hit = np.zeros(len(P), bool)
    trav = np.zeros(len(P))
    for it in range(70):
        i = np.flatnonzero(alive)
        if not len(i):
            break
        f = sdf.field_at(prims, P[i])
        done = np.abs(f) < 2e-5
        hit[i[done]] = True
        step = np.clip(f / lip, -0.002, 0.004)
        P[i] += step[:, None] * d
        trav[i] += step
        alive[i[done]] = False
        alive[i[trav[i] > 0.2]] = False
    e = 0.00015
    hi = np.flatnonzero(hit)
    g = np.stack([sdf.field_at(prims, P[hi] + e * ax) - sdf.field_at(prims, P[hi] - e * ax) for ax in np.eye(3)], 1)
    n = np.zeros((len(P), 3))
    n[hi] = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
    out = []
    for L in ((0.1, -1.0, 0.25), (1.0, -0.25, 0.1), (0.0, -0.3, 1.0)):       # frontal, raking from the side, from above
        Lc = np.array(L, float)
        Lw = Lc[0] * right + Lc[1] * d + Lc[2] * up
        Lw /= np.linalg.norm(Lw)
        sh = 0.12 + 0.88 * np.clip(n @ Lw, 0, 1)
        img = np.where(hit, sh, 0.0).reshape(h, w)
        out.append(Image.fromarray(np.round(255 * np.clip(img, 0, 1) ** (1 / 2.2)).astype(np.uint8)))
    return out, (P.reshape(h, w, 3), hit.reshape(h, w))


spec = store.load(name)
if folds != "-":
    sk = dict(spec.get("skin") or {})
    sk.pop("folds", None)
    if folds:
        sk["folds"] = json.load(open(folds)) if os.path.exists(folds) else json.loads(folds)
    spec["skin"] = sk
if "relief" in kw:
    spec["skin"]["fold_relief"] = kw["relief"]
part = (spec.get("skin") or {}).get("part", "body")
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}
eyes = 0.5 * (J["eye.L"] + J["eye.R"])
mouth = 0.5 * (J["lm_mouth_corner.L"] + J["lm_mouth_corner.R"])
box = {"eyes": (eyes + [0, 0, -0.004], (104, 56)), "mouth": (mouth + [0, 0, 0.006], (104, 76)),
       "face": (0.5 * (eyes + mouth) + [0, 0, 0.0], (150, 150))}[kw.get("box", "face")]
mmpx = float(kw.get("px", 0.3))
t = time.time()
rows = []
for az in [float(x) for x in kw.get("az", "0,40").split(",")]:
    ims, _ = render(spec, part, az, box[0], box[1], mmpx)
    rows.append(ims)
W, H = rows[0][0].size
sheet = Image.new("RGB", (3 * W + 8, len(rows) * (H + 4) + 22), (20, 20, 22))
dr = ImageDraw.Draw(sheet)
dr.text((4, 4), f"{name} {tag}: clay of the field | frontal | raking side | raking above   ({time.time() - t:.0f} s)", fill=(230, 230, 230))
for r, ims in enumerate(rows):
    for c, im in enumerate(ims):
        sheet.paste(im.convert("RGB"), (c * (W + 4), 22 + r * (H + 4)))
out = f"{G}/clay_{name}_{tag}.png"
sheet.save(out)
print(out, f"{time.time() - t:.0f} s")
