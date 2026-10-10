"""nosereader.py <image> [out png]: NOSE readers on a front picture (faces5; the nose base was the biggest visible miss:
wide alae, no nostril show, the base row ~5 mm low, while MediaPipe's nose points scatter 2-4 mm).

  nostrils   the dark nostril openings: in a box under the tip between the alae (MediaPipe 1, 2, 98, 327, 64, 294),
             pixels darker than NOSTRIL_K x the nose skin's median luminance, the two largest blobs left / right of the
             midline: area (mm^2), top / bottom / centroid height over the subnasale row (mm), inner / outer x (mm)
  alae       the alar width: per side, along rows at the alar lobule's height, the outermost strong DARKENING going
             outward (the alar-facial groove's shadow / the lobule's edge) within +-6 mm of MediaPipe's alar point
             (64 / 294 / 129 / 358): al-al (mm), each side's x from the midline
  base       the columella-lip junction (subnasale): the lowest dark-to-skin transition under the nostrils at the
             midline (mm over MediaPipe 2)
Scale: the iris (11.7 mm). Returns a dict; as a script writes an overlay (nostril blobs, alar edges, base row)."""
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import lipborder as LB

NOSTRIL_K = 0.62


def read(img, P, mmpx=None):
    P = np.asarray(P, float)[:, :2]
    mmpx = mmpx or LB.mmpx_of(P)
    a = np.asarray(img.convert("RGB"), float) / 255.0
    L = a @ np.array([0.2126, 0.7152, 0.0722])
    L = ndimage.gaussian_filter(L, max(0.15 / mmpx, 0.5))
    tip, sn = P[1], P[2]
    axl, axr = P[64], P[294]                     # (the alar base points, subject's right / left)
    mid_x = 0.5 * (axl[0] + axr[0])
    half = 0.5 * abs(axr[0] - axl[0])
    x0, x1 = int(mid_x - 1.3 * half), int(mid_x + 1.3 * half)
    y0, y1 = int(tip[1] - 0.3 * (sn[1] - tip[1])), int(sn[1] + 0.6 * (sn[1] - tip[1]) + 2 / mmpx)
    box = L[y0:y1, x0:x1]
    skin = np.median(L[int(P[4][1]):int(tip[1]), int(mid_x - half * 0.5):int(mid_x + half * 0.5)])
    dark = box < NOSTRIL_K * skin
    lab, n = ndimage.label(dark)
    out = {"mmpx": mmpx, "box": (x0, y0, x1, y1)}
    blobs = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        if len(ys) * mmpx ** 2 < 0.5:
            continue
        blobs.append((len(ys), xs + x0, ys + y0))
    for side, sgn in (("R", -1), ("L", 1)):
        cand = [b for b in blobs if sgn * (b[1].mean() - mid_x) > 0]
        if not cand:
            out["nostril_" + side] = None
            continue
        area, xs, ys = max(cand, key=lambda b: b[0])
        out["nostril_" + side] = {"area": area * mmpx ** 2, "top": (sn[1] - ys.min()) * mmpx, "bottom": (sn[1] - ys.max()) * mmpx,
                                  "cy": (sn[1] - ys.mean()) * mmpx, "inner": abs(xs.mean() - mid_x) * mmpx - 0.5 * np.ptp(xs) * mmpx,
                                  "outer": (abs(xs - mid_x).max()) * mmpx, "px": (xs, ys)}
    # alae: rows over the lobule's height (from the nostrils' top to the alar base), outermost darkening outward
    rows = np.arange(int(tip[1]), int(max(axl[1], axr[1]) + 1))
    edges = {}
    for side, ap, sgn in (("R", axl, -1), ("L", axr, 1)):
        xsr = []
        for y in rows:
            xs = np.arange(int(ap[0] - sgn * 4 / mmpx), int(ap[0] + sgn * 4 / mmpx), sgn)
            xs = xs[(xs > 0) & (xs < L.shape[1] - 1)]
            prof = L[y, xs]
            # the lobule's edge: the strongest luminance edge either way (on the lit side the cheek is darker than
            # the ala's flank, on the shaded side lighter: "falling outward" found cheek texture on the lit side)
            dprof = np.abs(np.gradient(prof))
            j = int(np.argmax(dprof))
            xsr.append(xs[j])
        edges[side] = np.array(xsr, float)
    if edges:
        out["alar_R"] = (mid_x - np.percentile(edges["R"], 10)) * mmpx
        out["alar_L"] = (np.percentile(edges["L"], 90) - mid_x) * mmpx
        out["alar_width"] = out["alar_R"] + out["alar_L"]
        out["edges"] = (rows, edges)
    return out


def overlay(img, r, path):
    im = img.convert("RGB").copy()
    d = ImageDraw.Draw(im)
    for side in ("R", "L"):
        nb = r.get("nostril_" + side)
        if nb:
            xs, ys = nb["px"]
            for x, y in zip(xs[::3], ys[::3]):
                d.point((int(x), int(y)), fill=(255, 0, 255))
    rows, edges = r["edges"]
    for side, xs in edges.items():
        for x, y in zip(xs, rows):
            d.point((int(x), int(y)), fill=(0, 255, 0))
    x0, y0, x1, y1 = r["box"]
    c = im.crop((x0 - 30, y0 - 30, x1 + 30, y1 + 30))
    c = c.resize((c.width * 4, c.height * 4), Image.NEAREST)
    c.save(path)


if __name__ == "__main__":
    from hifipushie import likeness
    img = Image.open(sys.argv[1]).convert("RGB")
    P = likeness.detect([img])[0]
    r = read(img, P)
    for k in ("alar_width", "alar_R", "alar_L"):
        print(k, round(r[k], 2))
    for side in ("R", "L"):
        nb = r.get("nostril_" + side)
        print("nostril", side, None if nb is None else {k: round(v, 2) for k, v in nb.items() if k != "px"})
    overlay(img, r, sys.argv[2] if len(sys.argv) > 2 else "/tmp/nose.png")
