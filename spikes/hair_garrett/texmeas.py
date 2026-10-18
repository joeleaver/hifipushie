# texmeas.py <pairs dir> [names...]: the strand-texture items the stand-off / colour checklist missed (2026-10-16).
# Per crop, ref and res (same framing for fitted views), hair pixels only (neutral, textured, not backdrop, eroded):
#  lay      : mean angle of the visible strand direction to the image horizontal, deg (coherence-weighted, axial 0-90).
#             In the top-front crops the hairline runs ~horizontal: ~90 = strands stand / run straight back (bristle),
#             low = they lie and sweep along the head.
#  coh      : structure-tensor coherence at 4 px (1 = all parallel)
#  disp     : orientation spread inside 32 px windows (1 - |mean e^{2i theta}|): flowing / crossing tips > uniform
#  len      : visible strand length, px: p75 of skeletonised light-ridge pieces (sato sigma 1, top 15 %)
#  wid      : the same ACROSS the strands; clump = across length of the coarse band (DoG 3-12)
#  stripe   : brightness std of the fine band (DoG 1.5-4), L* units (dark / light striping across strands)
#  edge     : hairline sparse-tail width, px (50 % -> 10 % hair score down each column); edgec: fine-band L* std in the
#             25 px below the line (hard lined edge = high). band: DoG 3-10 std = lock-scale dark / light striping
import sys, numpy as np
from PIL import Image
from skimage.color import rgb2lab
from scipy import ndimage as nd

def load(f):
    im = np.asarray(Image.open(f).convert('RGB'), float) / 255
    lab = rgb2lab(im); return lab[..., 0], np.hypot(lab[..., 1], lab[..., 2])

def hairmask(L, C):
    sd = np.sqrt(np.maximum(nd.uniform_filter(L * L, 7) - nd.uniform_filter(L, 7) ** 2, 0))
    m = (C < 9) & (L > 8) & (L < 85) & (sd > 2.0)
    m = nd.binary_closing(m, iterations=3); m = nd.binary_opening(m, iterations=2)
    return nd.binary_erosion(m, iterations=6)

def dog(L, a, b): return nd.gaussian_filter(L, a) - nd.gaussian_filter(L, b)

def orient(L, s=4):
    gx = nd.gaussian_filter(L, 1, order=(0, 1)); gy = nd.gaussian_filter(L, 1, order=(1, 0))
    jxx = nd.gaussian_filter(gx * gx, s); jyy = nd.gaussian_filter(gy * gy, s); jxy = nd.gaussian_filter(gx * gy, s)
    th = 0.5 * np.arctan2(2 * jxy, jxx - jyy) + np.pi / 2   # strand direction = across the gradient
    tr = jxx + jyy + 1e-9; coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / tr
    return th, coh

def aclen(img, mask, th, P=64, thr=0.5):
    al, ac_, h, w = [], [], *img.shape
    for y in range(0, h - P, P // 2):
        for x in range(0, w - P, P // 2):
            if mask[y:y + P, x:x + P].mean() < 0.9: continue
            p = img[y:y + P, x:x + P]; p = (p - p.mean()) * np.hanning(P)[:, None] * np.hanning(P)[None]
            F = np.fft.fft2(p, s=(2 * P, 2 * P)); A = np.fft.fftshift(np.real(np.fft.ifft2(np.abs(F) ** 2)))
            A /= A[P, P] + 1e-12
            t = np.angle(np.mean(np.exp(2j * th[y:y + P, x:x + P]))) / 2
            r = np.arange(0, 60, 0.5); out = []
            for ang in (t, t + np.pi / 2):
                v = nd.map_coordinates(A, [P - r * np.sin(ang), P + r * np.cos(ang)], order=1)
                k = np.argmax(v < thr); out.append(r[k] if v[k] < thr else 60)
            al.append(out[0]); ac_.append(out[1])
    return (np.median(al), np.median(ac_), len(al)) if al else (np.nan, np.nan, 0)

def edge(L, C):
    """(width, contrast): width = px from the 50 % hair-score line down to 10 % (the sparse tail); contrast = fine-band
    (DoG 1-4) L* std in the 25 px below the 50 % line (dark lined edge strands on skin = high; soft fine hairs = low)."""
    sd = np.sqrt(np.maximum(nd.uniform_filter(L * L, 5) - nd.uniform_filter(L, 5) ** 2, 0))
    score = nd.gaussian_filter(((C < 9) & (L < 75) & (sd > 2)).astype(float), 3)
    fb = dog(L, 1, 4); ws, cs = [], []
    for x in range(0, score.shape[1], 4):
        col = score[:, x]; top = np.where(col > 0.5)[0]
        if not len(top) or top[-1] > len(col) - 30: continue
        y0 = top[-1]; below = np.where(col[y0:] < 0.1)[0]
        if len(below): ws.append(below[0])
        cs.append(fb[y0:y0 + 25, max(0, x - 2):x + 2].std())
    return (np.median(ws) if ws else np.nan), (np.median(cs) if cs else np.nan)

def strandlen(L, m):
    """visible strand length, px: light ridges (sato, sigma 1) in the top 15 % within the hair, skeletonised;
    p75 of the connected pieces' pixel counts (pieces >= 4 px)."""
    from skimage.filters import sato
    from skimage.morphology import skeletonize
    rd = sato(L, sigmas=[1], black_ridges=False)
    t = np.percentile(rd[m], 85); sk = skeletonize((rd > t) & m)
    lab, n = nd.label(sk, structure=np.ones((3, 3)))
    sz = np.bincount(lab.ravel())[1:]; sz = sz[sz >= 4]
    return float(np.percentile(sz, 75)) if len(sz) else np.nan

def measure(f, isedge):
    L, C = load(f); m = hairmask(L, C)
    if m.sum() < 500: return None
    th, coh = orient(L)
    w = coh[m]; lay = np.degrees(np.abs(np.arcsin(np.abs(np.sin(th[m])))))
    z = np.exp(2j * th); zz = nd.uniform_filter(z.real, 32) + 1j * nd.uniform_filter(z.imag, 32)
    r = dict(n=int(m.sum()), lay=float((lay * w).sum() / w.sum()), coh=float(coh[m].mean()),
             disp=float(1 - np.abs(zz[m]).mean()))
    fine = dog(L, 1, 6); _, r['wid'], r['np'] = aclen(fine, m, th)
    r['len'] = strandlen(L, m)
    r['clump'] = aclen(dog(L, 3, 12), m, th)[1]
    r['stripe'] = float(dog(L, 1.5, 4)[m].std()); r['band'] = float(dog(L, 3, 10)[m].std()); r['Lmean'] = float(L[m].mean())
    if isedge: r['edge'], r['edgec'] = map(float, edge(L, C))
    return r

if __name__ == '__main__':
    D = sys.argv[1]; names = sys.argv[2:] or ['direction__three_quarter__top_front', 'direction__profile__top_front',
        'three_quarter', 'profile', 'front', 'hairline__front', 'temple__his_left', 'temple__his_right', 'back',
        'crown__back', 'nape__back']
    keys = ['lay', 'coh', 'disp', 'len', 'wid', 'clump', 'stripe', 'band', 'Lmean', 'edge', 'edgec']
    print('%-38s %s' % ('crop ref|res', ' '.join('%12s' % k for k in keys)))
    for n in names:
        a = measure(f'{D}/{n}_ref.png', 'hairline' in n or 'temple' in n)
        b = measure(f'{D}/{n}_res.png', 'hairline' in n or 'temple' in n)
        if a is None or b is None: print(n, 'too few hair px'); continue
        print('%-38s %s' % (n[:38], ' '.join('%5.2f|%-6.2f' % (a.get(k, np.nan), b.get(k, np.nan)) for k in keys)))
