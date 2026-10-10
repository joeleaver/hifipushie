"""lipshade.py <refs model> <view index> <png> [png ...]: the lower lip's SHADING, photo vs renders (the "narrower and
poutier" read: the lip's form in depth, which the outline items can't see). Each image: MediaPipe 478 on it, the lower
vermilion as a lip-local grid (u = corner to corner along the detector's 11-point borders, v = 0 at the stomion's
border, 1 at the lower border, > 1 extended past it onto the skin under the lip). Luminance is divided by the lip's own
median (the red's colour cancels: shading only) or, under the lip, by the chin's skin.

Prints per image:
  hl_v      v of the brightest row at the middle (where the pad faces the light: a pout's highlight sits high)
  hl        that row over the lip's median (how strongly the pad is lit vs the rest)
  roll      top band (v .15-.45) over bottom band (v .65-.95) at the middle: an everted pad is lit on top, turns under
  roll_u    roll at u = .15 .3 .5 .7 .85 (the pad's lateral shape: a cushion's roll falls off early to the sides)
  pad_w     the u-width where roll is over half its middle excess (the lit pad's width / the mouth's)
  shadow    darkest row under the lip (v 1.0-1.7) over the chin's skin (v 2.0-2.4), middle: depth of the lip's overhang
  shadow_u  the same at u = .3 .5 .7
Photo = the reference view's crop (sheet1.crop_of) at the renders' size. Writes $F/out/lipshade_<tag>.png: the lip
crops photo | renders with the grid's rows drawn."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import rs
import sheet1
from hifipushie import store

INNER = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]
OUTER = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291]
LUM = np.array([0.2126, 0.7152, 0.0722])


def _line(P, idx, u):
    Q = P[idx, :2]
    t = np.linspace(0, 1, len(Q))
    return np.stack([np.interp(u, t, Q[:, 0]), np.interp(u, t, Q[:, 1])], -1)


def grid(P, U, V):
    """Pixel positions (len(U), len(V), 2) of the lip-local grid."""
    a, b = _line(P, INNER, U), _line(P, OUTER, U)
    return a[:, None, :] + (b - a)[:, None, :] * V[None, :, None]


def sample(L, X):
    from scipy.ndimage import gaussian_filter, map_coordinates
    L = gaussian_filter(L, 1.2)
    return map_coordinates(L, [X[..., 1].ravel(), X[..., 0].ravel()], order=1).reshape(X.shape[:-1])


def read(img):
    """lipshade features of an RGB image (uint8): the detector's points on it, its luminance (sRGB-weighted)."""
    P = rs.detect([img.astype(np.uint8)])[0]
    if P is None:
        return None
    return read_values(P["P"], (img.astype(float) / 255.0) @ LUM)


def read_values(P, L):
    """lipshade features of a luminance image L (any linear scale: every feature is a ratio) on the lip grid of the
    detector points P (478, 2+)."""
    U = np.linspace(0.08, 0.92, 43)
    V = np.linspace(0.0, 2.4, 97)
    S = sample(L, grid(P, U, V))
    lipm = np.median(S[(U > 0.3) & (U < 0.7)][:, (V > 0.1) & (V < 0.95)])
    mid = (U > 0.42) & (U < 0.58)
    Ln = S / lipm
    inlip = (V >= 0.05) & (V <= 0.95)
    prof = Ln[mid].mean(0)
    k = np.argmax(np.where(inlip, prof, -1))

    def roll_at(sel):
        top = Ln[sel][:, (V >= 0.15) & (V <= 0.45)].mean()
        bot = Ln[sel][:, (V >= 0.65) & (V <= 0.95)].mean()
        return top / bot

    ru = np.array([roll_at(np.abs(U - u) < 0.05) for u in U])
    r0 = roll_at(mid)
    half = 1 + 0.5 * (r0 - 1)
    c = len(U) // 2
    lo = c
    while lo > 0 and ru[lo - 1] > half:
        lo -= 1
    hi = c
    while hi < len(U) - 1 and ru[hi + 1] > half:
        hi += 1
    under = (V >= 1.0) & (V <= 1.7)
    chin = (V >= 2.0) & (V <= 2.4)

    def shadow_at(sel):
        return S[sel][:, under].mean(0).min() / S[sel][:, chin].mean()

    return {"P": P, "hl_v": float(V[k]), "hl": float(prof[k]), "roll": float(r0),
            "roll_u": [float(np.interp(u, U, ru)) for u in (0.15, 0.3, 0.5, 0.7, 0.85)],
            "pad_w": float(U[hi] - U[lo]) if r0 > 1.0 else 0.0, "shadow": float(shadow_at(mid)),
            "shadow_u": [float(shadow_at(np.abs(U - u) < 0.06)) for u in (0.3, 0.5, 0.7)], "prof": prof}


def crop_img(img, P, pad=0.9):
    Q = P[INNER + OUTER, :2]
    lo, hi = Q.min(0), Q.max(0)
    w = hi[0] - lo[0]
    box = (int(lo[0] - 0.15 * w), int(lo[1] - pad * 0.5 * w), int(hi[0] + 0.15 * w), int(hi[1] + pad * 0.6 * w))
    return box


def main():
    refm, vi = sys.argv[1], int(sys.argv[2])
    pngs = sys.argv[3:]
    refs = json.loads((store.HOME / refm / "human_refs.json").read_text())
    v = refs["views"][vi]
    crop = [int(round(x)) for x in sheet1.crop_of(v)]
    size = Image.open(pngs[0]).size
    ims = [("photo", np.asarray(Image.open(v["image"]).convert("RGB").crop(tuple(crop)).resize(size, Image.LANCZOS)))]
    ims += [(os.path.basename(p).replace("_big.png", ""), np.asarray(Image.open(p).convert("RGB"))) for p in pngs]
    tiles = []
    ref = None
    for nm, im in ims:
        r = read(im)
        if r is None:
            print(nm, "no face found")
            continue
        if ref is None:
            ref = r
        f = lambda x: round(x, 3)  # noqa: E731
        print(f"{nm:24s} hl_v {f(r['hl_v'])} hl {f(r['hl'])} roll {f(r['roll'])} roll_u {[f(x) for x in r['roll_u']]} "
              f"pad_w {f(r['pad_w'])} shadow {f(r['shadow'])} shadow_u {[f(x) for x in r['shadow_u']]}")
        box = crop_img(im, r["P"])
        t = Image.fromarray(im).crop(box)
        d = ImageDraw.Draw(t)
        X = grid(r["P"], np.linspace(0.08, 0.92, 22), np.array([0.0, 0.3, 0.6, 1.0, 1.7, 2.0, 2.4])) - [box[0], box[1]]
        for j, col in enumerate([(255, 255, 0), (0, 255, 0), (0, 255, 0), (255, 0, 0), (0, 128, 255), (0, 0, 255), (0, 0, 255)]):
            d.line([tuple(p) for p in X[:, j]], fill=col, width=1)
        t = t.resize((360, int(360 * t.height / t.width)))
        d = ImageDraw.Draw(t)
        d.rectangle([0, 0, 8 + 6 * len(nm), 14], fill=(0, 0, 0))
        d.text((3, 2), nm, fill=(255, 255, 255))
        tiles.append(t)
    H = max(t.height for t in tiles)
    S = Image.new("RGB", (360 * len(tiles), H), (20, 20, 20))
    for i, t in enumerate(tiles):
        S.paste(t, (360 * i, 0))
    tag = os.environ.get("TAG", os.path.basename(pngs[-1]).replace("_big.png", ""))
    out = f"{os.environ.get('F', '/mnt/data/hifipushie/faces2')}/out/lipshade_{tag}.png"
    S.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
