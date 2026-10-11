"""The VERMILION BORDER traced along its length on a picture (faces5's spikes/facesliders/lipborder.py, moved here for
the block-in's lips step, blockin_lips.py; coordinator on f5_20: "the
detector's lip contour evidently isn't constraining the border shape (11 points per border)"; her Cupid's bow,
tubercle and the lower lip's widest-at-centre red were missing on every fit).

Start: MediaPipe's outer lip contour (upper 61..291 over the bow, lower 61..291 under the lip). The border is then
found along each contour normal (N samples per border): the strongest edge of a lip-vs-skin channel within +-REACH mm,
where the channel falls going OUTWARD (lip inside, skin outside). The channel is CIELAB a* (redness) plus a little
lightness edge (a pale lip on pale skin has a weak a* step but a lightness / sheen step): w_a * a* - w_L * |dL|.
Outliers along the border are rejected (a running median of the offsets, then a smooth), and the corners (where the
two borders meet the commissure) are left to the detector. Scale: the iris (11.7 mm) unless given.

read(img, P) -> {"upper": (N, 2) px, "lower": (N, 2) px, "off_up", "off_lo" (mm, + = outward of MediaPipe's contour),
"conf_up", "conf_lo" (edge strength), "mmpx"}. As a script: overlay png (MediaPipe's contour blue, the traced border
red)."""
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter, map_coordinates, median_filter

UPPER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291]
LOWER = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291]
IRIS_RIM = ((469, 470, 471, 472), (474, 475, 476, 477))
IRIS_C = (468, 473)
N = 61
REACH = 2.5        # mm either side of the detector's contour
INNER = (0.08, 0.92)   # the share of the border's length traced (the corners are the detector's)


def _lab(img):
    a = np.asarray(img.convert("RGB"), float) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    X = lin @ M.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(X > 0.008856, np.cbrt(X), 7.787 * X + 16 / 116)
    L = 116 * f[..., 1] - 16
    A = 500 * (f[..., 0] - f[..., 1])
    return L, A


def _curve(P, idx, n):
    Q = P[idx, :2]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    t = np.linspace(0, s[-1], n)
    C = np.stack([np.interp(t, s, Q[:, 0]), np.interp(t, s, Q[:, 1])], 1)
    tan = np.gradient(C, axis=0)
    tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
    nrm = np.c_[tan[:, 1], -tan[:, 0]]
    return C, nrm


def mmpx_of(P):
    r = []
    for s in (0, 1):
        r.append(np.mean([np.linalg.norm(P[i, :2] - P[IRIS_C[s], :2]) for i in IRIS_RIM[s]]))
    return 11.7 / (2 * float(np.mean(r)))


def read(img, P, mmpx=None, sigma_mm=0.25):
    P = np.asarray(P, float)
    mmpx = mmpx or mmpx_of(P)
    L, A = _lab(img)
    sg = max(sigma_mm / mmpx, 0.7)
    A = gaussian_filter(A, sg)
    L = gaussian_filter(L, sg)
    mouth = P[[13, 14], :2].mean(0)
    out = {"mmpx": mmpx}
    for name, idx in (("up", UPPER), ("lo", LOWER)):
        C, nrm = _curve(P, idx, N)
        # outward = away from the mouth's centre
        sgn = np.sign(((C - mouth) * nrm).sum(1))
        nrm = nrm * np.where(sgn == 0, 1, sgn)[:, None]
        ts = np.arange(-REACH, REACH + 1e-9, 0.05) / mmpx       # px along the normal
        X = C[:, None, :] + ts[None, :, None] * nrm[:, None, :]
        a = map_coordinates(A, [X[..., 1].ravel(), X[..., 0].ravel()], order=1).reshape(X.shape[:2])
        lum = map_coordinates(L, [X[..., 1].ravel(), X[..., 0].ravel()], order=1).reshape(X.shape[:2])
        da = np.gradient(a, axis=1)            # per step outward: the lip's a* falls -> negative
        dl = np.abs(np.gradient(lum, axis=1))
        score = -da + 0.15 * dl
        k = np.argmax(score, 1)
        conf = score[np.arange(N), k]
        off = ts[k] * mmpx                     # mm
        # (a running median rejects a single grabbed shadow / highlight; then a light smooth along the border)
        off_m = median_filter(off, size=7, mode="nearest")
        bad = np.abs(off - off_m) > 0.4
        off = np.where(bad, off_m, off)
        off = np.convolve(np.pad(off, 2, mode="edge"), np.ones(5) / 5, mode="valid")
        u = np.linspace(0, 1, N)
        keep = (u >= INNER[0]) & (u <= INNER[1])
        off = np.where(keep, off, 0.0)
        out["upper" if name == "up" else "lower"] = C + (off / mmpx)[:, None] * nrm
        out["mp_" + name] = C
        out["off_" + name] = off
        out["conf_" + name] = conf
        out["keep"] = keep
    return out


def overlay(img, r, path, crop_pad=0.35):
    im = img.convert("RGB").copy()
    d = ImageDraw.Draw(im)
    for k, col in (("mp_up", (60, 120, 255)), ("mp_lo", (60, 120, 255)), ("upper", (255, 30, 30)), ("lower", (255, 30, 30))):
        Q = r[k]
        d.line([tuple(p) for p in Q], fill=col, width=1)
    Q = np.r_[r["upper"], r["lower"]]
    lo, hi = Q.min(0), Q.max(0)
    w = hi[0] - lo[0]
    box = (int(lo[0] - crop_pad * w), int(lo[1] - crop_pad * w), int(hi[0] + crop_pad * w), int(hi[1] + crop_pad * w))
    c = im.crop(box)
    c = c.resize((900, int(900 * c.height / c.width)), Image.LANCZOS)
    c.save(path)
    return path


if __name__ == "__main__":
    from hifipushie import likeness
    img = Image.open(sys.argv[1]).convert("RGB")
    P = likeness.detect([img])[0]
    r = read(img, P)
    print("mm/px", round(r["mmpx"], 4), "| offsets from MediaPipe (mm, + outward): upper",
          np.round(r["off_up"][r["keep"]][::6], 2).tolist(), "| lower", np.round(r["off_lo"][r["keep"]][::6], 2).tolist())
    print("wrote", overlay(img, r, sys.argv[2] if len(sys.argv) > 2 else "/tmp/lipborder.png"))
