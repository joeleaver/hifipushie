"""edgewidth.py <ref.png> <res.png> [...pairs]: the HAIRLINE EDGE'S WIDTH (successor 17). hairline_edge (texmeas) passed while
every review called our hairline a hard cut-out. Per image column of a front hairline crop (hair above, skin below): a
hair COVER profile down the column (skin-likeness from the crop's own skin colour: chroma and lightness distance, 9 px box),
the edge = the band where cover falls from 80 % to 20 % of the column's hair level; width = its height in px (crops are
the same framing on both sides, so px compare). Prints the median and p75 width and the share of columns with a band
< 6 px (a cut)."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as nd
from skimage import color

BOX, HI, LO = 3, 0.9, 0.1  # cover smoothing (px) and the band's top / bottom (x the column's hair level)


def cover(p):
    a = np.asarray(Image.open(p).convert("RGB"), float) / 255
    lab = color.rgb2lab(a)
    h = lab.shape[0]
    sk = lab[int(h * .85):, :].reshape(-1, 3)  # skin reference: the crop's bottom band (the forehead)
    hr = lab[:int(h * .2), :].reshape(-1, 3)
    ms, mh = np.median(sk, 0), np.median(hr, 0)
    # project each pixel onto the skin -> hair colour axis (Lab), smoothed: 0 = skin, 1 = hair
    ax = mh - ms
    t = ((lab - ms) @ ax) / (ax @ ax)
    return nd.uniform_filter(np.clip(t, 0, 1.2), BOX)


def width(p):
    c = cover(p)
    h, w = c.shape
    ws = []
    for x in range(10, w - 10, 4):
        col = nd.gaussian_filter1d(nd.uniform_filter1d(c, 9, axis=1)[:, x], 1)
        hi = np.percentile(col[:int(h * .3)], 50)
        if hi < 0.5:
            continue
        # walking down from the hair: the first crossings of 0.8 hi and 0.2 hi
        y8 = np.argmax(col < HI * hi)
        if col[y8] >= HI * hi:
            continue
        rest = col[y8:]
        if not (rest < LO * hi).any():
            continue
        y2 = y8 + int(np.argmax(rest < LO * hi))
        ws.append(y2 - y8)
    ws = np.array(ws, float)
    return dict(n=len(ws), med=float(np.median(ws)), p75=float(np.percentile(ws, 75)), cut=float((ws < 6).mean()))


if __name__ == "__main__":
    a = sys.argv[1:]
    for i in range(0, len(a), 2):
        r, o = width(a[i]), width(a[i + 1])
        print(f"{a[i + 1].rsplit('/', 2)[-2]:22s} photo med {r['med']:5.1f} px p75 {r['p75']:5.1f} cut {r['cut']:.2f} (n {r['n']}) | "
              f"ours med {o['med']:5.1f} p75 {o['p75']:5.1f} cut {o['cut']:.2f} (n {o['n']})")
