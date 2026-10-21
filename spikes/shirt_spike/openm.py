"""openm.py <tag>...: the open-collar reads vs the concept / photos: band ends apart (bottom / top), band end lean,
collar points apart (147 +- 20) and below HPS (50-61), V bottom below HPS (~60: the lowest z where the two fronts' edges
are > 6 mm apart near CF), roll turned, collar / band mirror p95."""
import sys, pickle
import numpy as np
from scipy.spatial import cKDTree
for t in sys.argv[1:]:
    d = pickle.load(open(f'/mnt/data/hifipushie/shirt_spike/{t}.pkl', 'rb')); X = np.asarray(d['A']); M = d['mesh']; P = M['points']; I = d['A_info']
    g = lambda k: X[P[k]] * 1000
    hps = np.asarray(d['at']['hps.L']).reshape(-1)[-3:] * 1000
    pid = np.asarray(M['piece']); nm = list(M['names'])
    # V: front edges = front vertices nearest CF per height band; the V bottom = lowest band where L and R front edges are apart
    fl, fr = X[pid == nm.index('front.L')] * 1000, X[pid == nm.index('front.R')] * 1000
    zs = np.arange(hps[2] - 200, hps[2] - 20, 4); vb = None
    for z in zs:
        a = fl[np.abs(fl[:, 2] - z) < 3]; b = fr[np.abs(fr[:, 2] - z) < 3]
        a = a[a[:, 1] < -60]; b = b[b[:, 1] < -60]
        if len(a) and len(b):
            gap = a[:, 0].min() - b[:, 0].max()   # L front's innermost x minus R front's outermost x (fronts overlap: < 0)
            if gap > 6 and vb is None: vb = z
    lean = lambda a, b: np.degrees(np.arctan2(abs((g(a) - g(b))[0]), (g(a) - g(b))[2]))
    Xm = X * [-1, 1, 1]; dist, _ = cKDTree(X).query(Xm); cs = np.isin(pid, [nm.index('collar'), nm.index('stand')])
    print(f"{t:5s} roll {[f['deg'] for f in I['folds'] if 'open' in f['fold']]} band apart bottom {np.linalg.norm(g('stand:leftBottomCf')-g('stand:rightBottomCf')):3.0f} top {np.linalg.norm(g('stand:leftTopCf')-g('stand:rightTopCf')):3.0f}"
          f" lean {lean('stand:leftTopCf','stand:leftBottomCf'):3.0f}/{lean('stand:rightTopCf','stand:rightBottomCf'):3.0f} | points apart {np.linalg.norm(g('collar:leftTopEdge')-g('collar:rightTopEdge')):4.0f} (147) below HPS {hps[2]-g('collar:leftTopEdge')[2]:3.0f}/{hps[2]-g('collar:rightTopEdge')[2]:3.0f} (50-61)"
          f" | V below HPS {('%3.0f' % (hps[2]-vb)) if vb else ' - '} (~60) | collar+band mirror p95 {np.percentile(dist[cs],95)*1000:4.1f} | worn_open {I.get('worn_open_mm')}")
