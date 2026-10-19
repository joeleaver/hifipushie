"""forehead_rows.py (r17, Garrett: forehead lines placed high) <dir> [<dir> ...]: forehead lines, photo vs ours, on forehead_v<i>.png / forehead_v<i>_ref.png (cu.py only=forehead).
Heights t = (brow top - y) / (brow top - hairline), both found on the PHOTO crop (same box both sides): brow top = the upper
edge of the darkest band over the brows, hairline = the first row above it where the skin chroma falls under 70 % (grey hair).
Lines = dark horizontal valleys: L - blur(6 px), smoothed along x (sigma 18 px); the row profile is their mean depth over the
forehead's middle 70 %. Peaks over 35 % of the photo's max: t, depth (L units), length (share of columns where the valley holds
half the peak depth at that row +-3 px). Vertical (glabella) lines: the same across x between the brows' inner ends."""
import sys, numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from skimage.color import rgb2lab

def lab(p): return rgb2lab(np.asarray(Image.open(p).convert("RGB"), float) / 255)

def frame(R):
    H, W = R.shape[:2]; L = R[..., 0]; c0, c1 = int(.3 * W), int(.7 * W)
    rows = gaussian_filter1d(L[:, c0:c1].mean(1), 3)
    lo = int(.35 * H) + int(np.argmin(rows[int(.35 * H): int(.75 * H)]))      # the brows' darkest row
    top = lo - int(np.argmax(np.diff(rows[lo::-1]) <= 0.15 * 0 + 0) if False else 0)
    # brow top: going up from the darkest row, where L recovers 70 % of the way to the forehead's level
    fl = np.median(rows[int(.15 * H): lo - 20]); y = lo
    while y > 0 and rows[y] < rows[lo] + .7 * (fl - rows[lo]): y -= 1
    chroma = gaussian_filter1d(np.hypot(R[..., 1], R[..., 2])[:, int(.4 * W): int(.6 * W)].mean(1), 2)
    sk = np.median(chroma[y - 40: y - 5]); h = y - 5
    while h > 0 and chroma[h] > .7 * sk: h -= 1
    return y, h

def valleys(L, axis):
    hp = L - gaussian_filter(L, 6)
    return -gaussian_filter1d(hp, 18, axis=1 - axis)

def peaks(prof, thr):
    return [i for i in range(2, len(prof) - 2) if prof[i] > thr and prof[i] == prof[max(i - 8, 0): i + 9].max()]

for D in sys.argv[1:]:
    for vi in (0, 1):
        try: R, O = lab(f"{D}/forehead_v{vi}_ref.png"), lab(f"{D}/forehead_v{vi}.png")
        except FileNotFoundError: continue
        H, W = R.shape[:2]; yb, yh = frame(R); span = yb - yh
        c0, c1 = int(.15 * W), int(.85 * W)
        print(f"== {D.rstrip('/').split('/')[-1]} view {vi}: brow top y {yb}, hairline y {yh} (px, {W} crop)")
        out = {}
        for nm, X in (("photo", R), ("ours", O)):
            V = valleys(X[..., 0], 0)[:, c0:c1]; prof = np.clip(V, 0, None).mean(1); dome = prof[max(yh - 120, 0): yh].mean(); prof[yb - 3:] = 0; prof[: yh + 15] = 0
            out[nm] = (V, prof, dome)
        thr = .5 * out["photo"][1].max()
        for nm, (V, prof, dome) in out.items():
            P = peaks(prof, thr)
            desc = [f"t {(yb - p) / span:.2f} d {prof[p]:.2f} len {(V[max(p - 3, 0):p + 4].max(0) > .5 * prof[p]).mean():.2f}" for p in P]
            band = lambda a, b: prof[int(yb - b * span): int(yb - a * span)].mean()
            print(f"  {nm:5s} lines {len(P)} | mean depth t 0-.33 {band(0, .33):.2f}  .33-.66 {band(.33, .66):.2f}  .66-1 {band(.66, 1):.2f}  | above the hairline (the photo: hair) {dome:.2f}")
            print(f"        {len(P)} lines (spacing {np.median(np.diff(P)) / span if len(P) > 1 else 0:.2f} t): " + "; ".join(desc))
        # glabella: vertical valleys in the middle 16 % of the width, from the brow top down 8 % of the crop
        for nm, X in (("photo", R), ("ours", O)):
            Vg = -gaussian_filter1d(X[..., 0] - gaussian_filter(X[..., 0], 5), 12, axis=0)[yb - int(.1 * H): yb + int(.06 * H), int(.42 * W): int(.58 * W)]
            pc = np.clip(Vg, 0, None).mean(0)
            print(f"  glabella {nm}: peak {pc.max():.2f} mean {pc.mean():.2f}")
