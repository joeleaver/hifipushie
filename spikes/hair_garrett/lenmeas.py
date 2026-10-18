# lenmeas.py <pairs dir> [names...]: visible LENGTH / SWEEP of the hair (2026-10-16, successor 18).
# The checklist had lay / stand-off / colour, but "a short crew cut vs longer, swept-back strands" was unmeasured.
# Per crop (hair px only, texmeas.hairmask), ref | res, same framing:
#  streak : streak length, px: along-strand autocorrelation length (to 0.5) of the lock band (DoG 2-8), 96 px patches,
#           median. Long continuous light / dark strands = long; a short pile of tips = short.
#  sfine  : the same on the fine band (DoG 1-4)
#  sline  : streamline length, px: orientation-field streamlines (structure tensor s=6) from a seed grid, followed both
#           ways while inside the hair, coherence > .25 and the band value stays correlated (running |dv| check); p75.
#  ratio  : streak / across-streak width (aspect of a lock)
import sys, numpy as np
from scipy import ndimage as nd
from texmeas import load, hairmask, dog, orient

def aclen2(img, mask, th, P=96, thr=0.5, R=90):
    al, ac_, h, w = [], [], *img.shape
    for y in range(0, h - P, P // 2):
        for x in range(0, w - P, P // 2):
            if mask[y:y + P, x:x + P].mean() < 0.85: continue
            p = img[y:y + P, x:x + P]; p = (p - p.mean()) * np.hanning(P)[:, None] * np.hanning(P)[None]
            F = np.fft.fft2(p, s=(2 * P, 2 * P)); A = np.fft.fftshift(np.real(np.fft.ifft2(np.abs(F) ** 2)))
            A /= A[P, P] + 1e-12
            t = np.angle(np.mean(np.exp(2j * th[y:y + P, x:x + P]))) / 2
            r = np.arange(0, R, 0.5); out = []
            for ang in (t, t + np.pi / 2):
                v = nd.map_coordinates(A, [P - r * np.sin(ang), P + r * np.cos(ang)], order=1)
                k = np.argmax(v < thr); out.append(r[k] if v[k] < thr else R)
            al.append(out[0]); ac_.append(out[1])
    return (float(np.median(al)), float(np.median(ac_)), len(al)) if al else (np.nan, np.nan, 0)

def streamlines(band, mask, th, coh, step=1.0, smax=300, seed=12, paths=None):
    h, w = band.shape; c2, s2 = np.cos(2 * th), np.sin(2 * th)
    def dirat(y, x):
        a = nd.map_coordinates(c2, [[y], [x]], order=1)[0]; b = nd.map_coordinates(s2, [[y], [x]], order=1)[0]
        t = 0.5 * np.arctan2(b, a); return np.cos(t), np.sin(t)  # (x = column, y = row DOWN, as orient)
    sd = band[mask].std() + 1e-9; Ls = []
    for y0 in range(seed, h - seed, seed):
        for x0 in range(seed, w - seed, seed):
            if not mask[y0, x0]: continue
            v0 = band[y0, x0]; tot = 0; pth = []
            for sgn in (1, -1):
                y, x = float(y0), float(x0); dx, dy = dirat(y, x); dx, dy = dx * sgn, dy * sgn; n = 0; dev = 0
                while n < smax:
                    nx_, ny_ = dirat(y, x)
                    if nx_ * dx + ny_ * dy < 0: nx_, ny_ = -nx_, -ny_
                    dx, dy = nx_, ny_; x += dx * step; y += dy * step; n += 1
                    iy, ix = int(round(y)), int(round(x))
                    if not (0 <= iy < h and 0 <= ix < w) or not mask[iy, ix] or coh[iy, ix] < 0.25: break
                    dev = 0.9 * dev + 0.1 * abs(band[iy, ix] - v0) / sd
                    if dev > 0.8: break
                    if paths is not None: pth.append((x, y))
                tot += n
            Ls.append(tot)
            if paths is not None: paths.append((tot, pth))
    return float(np.percentile(Ls, 75)) if Ls else np.nan

def overlay(f, out):
    from PIL import Image, ImageDraw
    L, C = load(f); m = hairmask(L, C); th, coh = orient(L, 6); P = []
    streamlines(nd.gaussian_filter(L, 2), m, th, coh, seed=20, paths=P)
    im = Image.open(f).convert('RGB'); d = ImageDraw.Draw(im)
    for n, p in P:
        if len(p) > 1: d.line(p, fill=(255, 40, 40) if n > 120 else (40, 160, 255) if n > 60 else (255, 220, 0), width=1)
    im.save(out)

def measure(f):
    L, C = load(f); m = hairmask(L, C)
    if m.sum() < 500: return None
    th, coh = orient(L, 6)
    b = dog(L, 2, 8); al, ac, n = aclen2(b, m, th)
    r = dict(n=int(m.sum()), np=n, streak=al, across=ac, ratio=al / max(ac, .5))
    r['sfine'] = aclen2(dog(L, 1, 4), m, th)[0]
    r['sline'] = streamlines(nd.gaussian_filter(L, 2), m, th, coh)
    return r

NAMES = ['three_quarter', 'profile', 'direction__three_quarter__top_front', 'direction__profile__top_front',
         'front', 'temple__his_left', 'temple__his_right', 'back', 'crown__back']
KEYS = ['streak', 'sfine', 'sline', 'across', 'ratio', 'np']

if __name__ == '__main__':
    if sys.argv[1] == 'overlay':
        for f in sys.argv[2:-1]: overlay(f, sys.argv[-1] + '_' + f.split('/')[-1])
        sys.exit()
    D = sys.argv[1]; names = sys.argv[2:] or NAMES
    print('%-38s %s' % ('crop ref|res', ' '.join('%13s' % k for k in KEYS)))
    for nm in names:
        a = measure(f'{D}/{nm}_ref.png'); b = measure(f'{D}/{nm}_res.png')
        if a is None or b is None: print(nm, 'too few hair px'); continue
        print('%-38s %s' % (nm[:38], ' '.join('%6.1f|%-6.1f' % (a[k], b[k]) for k in KEYS)), flush=True)
