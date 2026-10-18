"""teethshape.py img ...: what the open smile SHOWS, along the corner line (MediaPipe 478, % io, + = below the line):
at 9 stations (0.1..0.9 of corner -> corner) inside the inner lip contour, the top and bottom of the teeth (pixels with
HSV s < 0.30 and v > 0.40), and the red band (s >= 0.30, hue red) above / below them. Plus lip heights at the middle:
upper vermilion (0 -> 13) and lower (14 -> 17). A crescent: teeth bottom sags in the middle like the lower lip, no red band."""
import sys, numpy as np
from PIL import Image, ImageDraw
from hifipushie import likeness
IN = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95]
fs = sys.argv[1:]; ims = [Image.open(f).convert("RGB") for f in fs]; L = likeness.detect(ims)
for f, im, l in zip(fs, ims, L):
    name = "/".join(f.split("/")[-4:]) if "offload" in f else f.split("/")[-1]
    l = np.asarray(l, float)[:, :2]; io = np.linalg.norm(l[[33, 133]].mean(0) - l[[362, 263]].mean(0))
    a, b = l[61], l[291]; t = (b - a) / np.linalg.norm(b - a); n = np.array([-t[1], t[0]]); n = n if n[1] > 0 else -n
    W = np.linalg.norm(b - a)
    m = Image.new("L", im.size, 0); ImageDraw.Draw(m).polygon([tuple(p) for p in l[IN]], fill=1); m = np.asarray(m) > 0
    hsv = np.asarray(im.convert("HSV"), float) / 255; H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    teeth = m & (S < 0.30) & (V > 0.40); red = m & (S >= 0.30) & ((H < 0.07) | (H > 0.9)) & (V > 0.25)
    rows = []
    for u in np.linspace(0.1, 0.9, 9):
        ss = np.linspace(-0.25, 0.4, 260) * io; P = a + u * W * t + ss[:, None] * n
        xi, yi = np.clip(P[:, 0].round().astype(int), 0, im.width - 1), np.clip(P[:, 1].round().astype(int), 0, im.height - 1)
        T, R, Mm = teeth[yi, xi], red[yi, xi], m[yi, xi]
        st = 100 * ss / io
        if T.sum() < 2: rows.append((np.nan, np.nan, 100 * R.sum() * (ss[1] - ss[0]) / io, 100 * Mm.sum() * (ss[1] - ss[0]) / io, 0)); continue
        tt, tb = st[T].min(), st[T].max(); d = (ss[1] - ss[0]) / io * 100
        rows.append((tt, tb, R[st < tt].sum() * d, Mm.sum() * d, R[st > tb].sum() * d))
    r = np.array(rows)
    up = 100 * np.linalg.norm(l[0] - l[13]) / io; lo = 100 * np.linalg.norm(l[14] - l[17]) / io
    f1 = lambda v: " ".join(f"{x:+.1f}" for x in v)
    print(f"{name}: lips up {up:.1f} lo {lo:.1f} | teeth top [{f1(r[:, 0])}] | teeth bottom [{f1(r[:, 1])}] bottom bow {r[4, 1] - (r[2, 1] + r[6, 1]) / 2:+.1f}"
          f" | opening [{f1(r[:, 3])}] | red above [{f1(r[:, 2])}] red below [{f1(r[:, 4])}]")
