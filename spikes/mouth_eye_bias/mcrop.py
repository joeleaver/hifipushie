"""mcrop.py <ref> <tag> [tag2 ..] [--dots]: mouth and eye crops of the photo and each dressed lit render (out/r_<tag>_lit.png)
at the same framing (the photo's MediaPipe points set the box). Writes out/crop_<ref>_<region>_<photo|tag>.png and a strip
out/strip_<ref>_<region>.png (photo | tags ...)."""
from __future__ import annotations

import sys

import numpy as np
from PIL import Image, ImageDraw

import meb

MOUTH = (61, 291, 0, 17, 2, 18)
EYES = (33, 133, 263, 362, 159, 145, 386, 374, 105, 334)
DOTS = (61, 291, 0, 13, 14, 17, 37, 267, 33, 133, 263, 362, 159, 145, 386, 374)


def box_of(P, idx, pad, aspect):
    Q = P[list(idx)]
    lo, hi = Q.min(0), Q.max(0)
    c = (lo + hi) / 2
    w = (hi[0] - lo[0]) * (1 + pad)
    h = max((hi[1] - lo[1]) * (1 + pad), w / aspect)
    return (c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2)


def crop_picture(img, box, px):
    w = px
    h = int(round(px * (box[3] - box[1]) / (box[2] - box[0])))
    return img.transform((w, h), Image.EXTENT, tuple(float(v) for v in box), Image.BICUBIC)


def main(ref, tags, dots=False):
    from hifipushie import skin_read as sr
    rj, vi, ph = meb.setup(ref)
    Pp = ph["side"].P
    sb = sr.boxes(ref)[vi]
    side = max(sb[2] - sb[0], sb[3] - sb[1])
    for region, idx, pad, asp in (("mouth", MOUTH, 0.35, 1.6), ("eyes", EYES, 0.08, 2.6)):
        bx = box_of(Pp, idx, pad, asp)
        tiles = []
        srcs = [("photo", ph["img"], bx, Pp)]
        for t in tags:
            im = Image.open(f"{meb.OUT}/r_{t}_lit.png").convert("RGB")
            s = im.size[0] / side
            b2 = tuple((np.array(bx).reshape(2, 2) - np.array(sb[:2])).ravel() * s)
            try:
                P = np.load(f"{meb.OUT}/P_lit_{t}.npy")
            except FileNotFoundError:
                P = None
            srcs.append((t, im, b2, None if P is None else (P - np.array(sb[:2])) * s))
        for name, im, b, P in srcs:
            c = crop_picture(im, b, 700)
            if dots and P is not None:
                d = ImageDraw.Draw(c)
                k = 700 / (b[2] - b[0])
                for i in DOTS:
                    x, y = (P[i] - np.array(b[:2])) * k
                    d.ellipse((x - 3, y - 3, x + 3, y + 3), outline=(0, 255, 0))
            c.save(f"{meb.OUT}/crop_{ref}_{region}_{name}{'_d' if dots else ''}.png")
            tiles.append(c)
        W = sum(t.size[0] for t in tiles) + 8 * (len(tiles) - 1)
        st = Image.new("RGB", (W, tiles[0].size[1]), (20, 20, 20))
        x = 0
        for t in tiles:
            st.paste(t, (x, 0))
            x += t.size[0] + 8
        st.save(f"{meb.OUT}/strip_{ref}_{region}{'_d' if dots else ''}.png")


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--dots"]
    main(a[0], a[1:], "--dots" in sys.argv)
