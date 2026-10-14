"""standoff.py <model> [tiles=<dir with s_<model>_v{0,1,2}.png>] [tag=..]: how far the hair's OUTLINE stands off the
bare skull, hers | ours, like with like: the model's scalp (hair.scalp rays) projected through each reference's fitted
camera is the skull's silhouette; the hair's outline is read off her picture and off our render through the same
camera (dark, non-background pixels, single hairs opened away). Along rays from the head centre's pixel, per 10 deg of
image angle (0 = straight up, + = image right): mm from the skull's edge to the hair's edge. No Blender.
Saves $TOUT/standoff_<model>_v<i>.png (skull green, her outline red, ours blue)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

import stage
from hifipushie import hair, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
TOUT = os.environ["TOUT"]
tiles = kw.get("tiles", TOUT)
N = 1536
W, H = 1152, 1536
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]
spec = store.load(m)
sc = hair.scalp(m, spec)
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
A, E = np.meshgrid(np.arange(0, 360, 1.0), np.arange(float(sc.EL[0]) + 2, 90, 1.0))
P = sc.point(A.ravel(), E.ravel(), 0.0)


def hairmask(im, bg_tol=26):
    a = np.asarray(im.convert("RGB"), float)
    bg = np.median(a[:40, :40].reshape(-1, 3), 0)
    lum = a @ [0.2126, 0.7152, 0.0722]
    notbg = np.abs(a - bg).max(-1) > bg_tol
    mk = notbg & (lum < 0.52 * (bg @ [0.2126, 0.7152, 0.0722]))
    return ndi.binary_opening(mk, iterations=2)


res = {}
for i in (0, 1, 2):
    cam = refs["cameras"][i]
    fm = stage.fitted_frame(cam, BOX, f"v{i}")
    uv, z = hair._project_frame(fm, P, N)
    sk = np.zeros((N, N), bool)
    q = np.round(uv).astype(int)
    ok = (q[:, 0] >= 0) & (q[:, 0] < N) & (q[:, 1] >= 0) & (q[:, 1] < N)
    sk[q[ok, 1], q[ok, 0]] = True
    sk = ndi.binary_fill_holes(ndi.binary_closing(sk, iterations=6))
    c, zc = hair._project_frame(fm, sc.C[None], N)
    c = c[0]
    mm = float(zc[0]) / float(cam["f"]) * 1000.0  # (the square is the picture's own pixels)
    pic = hair.ref_square(Image.open(refs["views"][i]["image"]).convert("RGB"), N)
    hers = hairmask(pic)
    f_ours = f"{tiles}/s_{m}_v{i}.png"
    ours = hairmask(Image.open(f_ours).resize((N, N))) if os.path.exists(f_ours) else None
    rr = np.arange(0, 0.2 * 1000 / mm)
    rows = []
    for ang in range(-110, 111, 10):
        d = np.array([np.sin(np.radians(ang)), -np.cos(np.radians(ang))])
        xy = np.round(c[None] + rr[:, None] * d[None]).astype(int)
        okk = (xy[:, 0] >= 0) & (xy[:, 0] < N) & (xy[:, 1] >= 0) & (xy[:, 1] < N)
        xy = xy[okk]
        s_ = sk[xy[:, 1], xy[:, 0]]
        r_sk = float(np.nonzero(s_)[0].max()) if s_.any() else np.nan

        def edge(mk):
            if mk is None:
                return np.nan
            v = mk[xy[:, 1], xy[:, 0]] | s_
            # (the hair's edge: the first ray pixel past the skull's edge with 4 mm of no hair after it)
            k = int(r_sk)
            gap = int(4 / mm)
            while k < len(v) - gap and v[k:k + gap].any():
                k += 1
            return (k - r_sk) * mm
        rows.append((ang, edge(hers), edge(ours)))
    res[i] = rows
    im = pic.copy().convert("RGB")
    ov = np.asarray(im).copy()
    for mk, col in ((sk, (0, 255, 0)), (hers, (255, 0, 0)), (ours, (0, 90, 255))):
        if mk is None:
            continue
        e = ndi.binary_dilation(mk ^ ndi.binary_erosion(mk), iterations=1)
        ov[e] = col
    im = Image.fromarray(ov)
    ImageDraw.Draw(im).ellipse([c[0] - 5, c[1] - 5, c[0] + 5, c[1] + 5], fill=(255, 255, 0))
    im.resize((768, 768)).save(f"{TOUT}/standoff_{m}_{kw.get('tag', 'a')}_v{i}.png")
    print(f"view v{i}  mm/px {mm:.3f}   angle: hers | ours (mm off the skull)")
    print("  " + "  ".join(f"{a:+d}: {h:.0f}|{o:.0f}" for a, h, o in rows))
json.dump(res, open(f"{TOUT}/standoff_{m}_{kw.get('tag', 'a')}.json", "w"))
