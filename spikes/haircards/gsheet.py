"""gsheet.py <out.png> <tags,comma> [crop1=460] [crop3=160]: the GAME-DISTANCE sheet (gates.md: 1 m / 3 m at 1080p,
native pixels, the photo scaled to the same pixels per metre beside it). Renders: out/s_hc_s2<tag>_<g view>.png from
shots.py game views (size 1080, fov 59). Columns: photo (vN views only) | each tag. Also prints the coherence /
striping measures on hair pixels (hair = the strand render's id pass, eroded; the same mask on the photo crop):
  coh    : structure-tensor coherence (grad sigma 1, window 2.5 px), mean: 1 = parallel strands
  fine   : L* std of DoG(0.8, 2.5): strand-scale speckle / needles
  band   : L* std of DoG(2.5, 8): lock-scale dark / light banding
  L      : mean L*"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd
from skimage.color import rgb2lab

from hifipushie import humanfit, skin_look, store

D = "/mnt/data/hifipushie/haircards"
out, tags = sys.argv[1], sys.argv[2].split(",")
kw = dict(a.split("=", 1) for a in sys.argv[3:])
C1, C3 = int(kw.get("crop1", 540)), int(kw.get("crop3", 180))
VIEWS = kw.get("views", "g1v0,g1v1,g1v2,g1backl,g3v0,g3backl").split(",")
refs = json.loads((store.HOME / "th_W18" / "human_refs.json").read_text())
J = skin_look._J(store.load("th_W18"))
nt = J["lm_nose_tip"]
c = np.array([0.0, nt[1] + 0.11, nt[2] - 0.03])  # shots.py's head centre (th_W18 space)
GPXM1 = 540 / np.tan(np.radians(29.5))  # game pixels per metre at 1 m


def crop_box(n, dist):
    s = C1 if dist == 1 else C3
    dy = int(0.05 * GPXM1 / dist)  # the tail hangs: centre the crop a little below the head centre
    return (540 - s // 2, 540 - s // 2 + dy, 540 + s // 2, 540 + s // 2 + dy)


def photo(v, box, dist):
    i = int(v[1:])
    cam = refs["cameras"][i]
    Xc = (c - np.asarray(cam["centre"])) @ humanfit._cam_rot(cam).T + np.asarray(cam["t"])
    pxm = cam["f"] / Xc[2]
    s = (GPXM1 / dist) / pxm
    u, w = humanfit.project(cam, c[None])[0]
    im = Image.open(refs["views"][i]["image"].replace("@refs/", str(store.HOME / "_refs") + "/")).convert("RGB")
    x0, y0, x1, y1 = box
    pb = (u + (x0 - 540) / s, w + (y0 - 540) / s, u + (x1 - 540) / s, w + (y1 - 540) / s)
    P = 2000  # pad (the crop can run past the picture's edge): grey
    bg = Image.new("RGB", (im.size[0] + 2 * P, im.size[1] + 2 * P), (128, 128, 128))
    bg.paste(im, (P, P))
    return bg.resize((x1 - x0, y1 - y0), Image.LANCZOS, box=tuple(q + P for q in pb)), s


def idmask(f, box):
    i = np.asarray(Image.open(f).convert("RGB").crop(box), int)
    return np.abs(i[..., 0] - i[..., 1]) > 60  # measure_hc's hair test


def measures(im, mask):
    L = rgb2lab(np.asarray(im, float) / 255)[..., 0]
    gx, gy = nd.gaussian_filter(L, 1, order=(0, 1)), nd.gaussian_filter(L, 1, order=(1, 0))
    jxx, jyy, jxy = (nd.gaussian_filter(a, 2.5) for a in (gx * gx, gy * gy, gx * gy))
    coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / (jxx + jyy + 1e-9)
    fine = nd.gaussian_filter(L, 0.8) - nd.gaussian_filter(L, 2.5)
    band = nd.gaussian_filter(L, 2.5) - nd.gaussian_filter(L, 8)
    m = mask
    return {"coh": round(float(coh[m].mean()), 3), "fine": round(float(fine[m].std()), 2),
            "band": round(float(band[m].std()), 2), "L": round(float(L[m].mean()), 1), "px": int(m.sum())}


rows, report = [], {}
for v in VIEWS:
    dist, b = int(v[1]), v[2:]
    box = crop_box(1080, dist)
    idm = idmask(f"{D}/out/id_hc_s2_gS_{v}.png", box)
    mask = nd.binary_erosion(idm, iterations=3 if dist == 1 else 1)
    cells, names = [], []
    if b[0] == "v":
        p, s = photo(b, box, dist)
        cells.append(p); names.append("photo")
        report[f"{v} photo"] = measures(p, mask)
    for t in tags:
        import os
        if not os.path.exists(f"{D}/out/s_hc_s2_{t}_{v}.png"):  # a tag rendered at 1 m only (e.g. gb21u): blank cell
            cells.append(Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (60, 0, 0))); names.append(t + " (none)")
            report[f"{v} {t}"] = {"missing": True}
            continue
        im = Image.open(f"{D}/out/s_hc_s2_{t}_{v}.png").convert("RGB").crop(box)
        cells.append(im); names.append(t)
        tm = idmask(f"{D}/out/id_hc_s2_{t}_{v}.png", box)
        tm = nd.binary_erosion(tm, iterations=3 if dist == 1 else 1)
        report[f"{v} {t}"] = {**measures(im, tm), "own_mask": True}
    rows.append((v, cells, names))
for k, r in report.items():
    print(k, r)
# sheet: native pixels, rows of views, a 18 px label strip on each cell; 3 m rows have small cells (no upscale)
pad, lab = 8, 18
Wd = max(sum(cl.size[0] + pad for cl in cells) for _, cells, _ in rows) + pad
Ht = sum(max(cl.size[1] for cl in cells) + lab + pad for _, cells, _ in rows) + pad
sh = Image.new("RGB", (Wd, Ht), (30, 30, 30))
dr = ImageDraw.Draw(sh)
y = pad
for v, cells, names in rows:
    x = pad
    for cl, n in zip(cells, names):
        dr.text((x + 2, y + 3), f"{v} {n}"[:40], fill=(230, 230, 230))
        sh.paste(cl, (x, y + lab))
        x += cl.size[0] + pad
    y += max(cl.size[1] for cl in cells) + lab + pad
sh.save(out)
json.dump(report, open(out.rsplit(".", 1)[0] + ".json", "w"), indent=1)
print("sheet", out, sh.size)
