"""crease_trace.py: the upper-lid crease traced in a picture (shared by lidfit.py and creasepath.py).
  ridge(img, mmpx)                       dark-line response (Hessian, ~0.8 mm) of the picture's log luminance
  follow(resp, seed, ex, mmpx, cen)      the line followed both ways from a seed (0.5 mm steps, +-35 deg turns), (n, 2) px
  seed_near(resp, p, upv, ex, mmpx)      the strongest line within +-3 mm (up) / +-1.5 mm (across) of a point"""
import numpy as np
from scipy import ndimage


def ridge(img, mmpx):
    lum = np.log(np.maximum(np.asarray(img, float) @ [0.2126, 0.7152, 0.0722] / 255.0, 1e-3))
    s = max(0.8 / mmpx, 1.0)
    hxx = ndimage.gaussian_filter(lum, s, order=(0, 2)) * s * s
    hyy = ndimage.gaussian_filter(lum, s, order=(2, 0)) * s * s
    hxy = ndimage.gaussian_filter(lum, s, order=(1, 1)) * s * s
    tr, df = hxx + hyy, np.sqrt((hxx - hyy) ** 2 + 4 * hxy ** 2)
    return np.clip(0.5 * (tr + df), 0, None)


def seed_near(resp, p, upv, ex, mmpx, lo=-3.0, hi=3.0):
    best, bp = -1.0, None
    for h in np.arange(lo, hi + 0.01, 0.2):
        for a in np.linspace(-1.5, 1.5, 7):
            q = p + upv * h / mmpx + ex * a / mmpx
            yi, xi = int(round(q[1])), int(round(q[0]))
            if 0 <= yi < resp.shape[0] and 0 <= xi < resp.shape[1] and resp[yi, xi] > best:
                best, bp = resp[yi, xi], q
    return bp, best


def follow(resp, bp, best, ex, mmpx, cen, reach_mm=25.0):
    path = {1: [bp], -1: [bp]}
    for sg in (1, -1):
        hd = ex * sg
        p = bp.copy()
        for _ in range(int(40 / 0.5)):
            cands = []
            for da in np.radians(np.arange(-35, 36, 5)):
                c, s_ = np.cos(da), np.sin(da)
                d = np.array([c * hd[0] - s_ * hd[1], s_ * hd[0] + c * hd[1]])
                q = p + d * 0.5 / mmpx
                yi, xi = int(round(q[1])), int(round(q[0]))
                if not (0 <= yi < resp.shape[0] and 0 <= xi < resp.shape[1]):
                    continue
                cands.append((resp[yi, xi] - 0.002 * abs(np.degrees(da)) * best / 35, q, d))
            if not cands:
                break
            r, q, d = max(cands, key=lambda t: t[0])
            if resp[int(round(q[1])), int(round(q[0]))] < best / 3 or np.linalg.norm(q - cen) * mmpx > reach_mm:
                break
            path[sg].append(q)
            p, hd = q, d
    return np.array(path[-1][::-1] + path[1][1:])
