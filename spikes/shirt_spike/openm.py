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
    # V: each front's EDGE (front.L: its fold edge, pattern x < placketTopFold1 + 3 mm; front.R: x > placketTopOut - 3 mm).
    # Closed, the edges overlap (L's edge lies on the -x side of R's). The V bottom = the lowest height above which the
    # L edge stays on the +x side of the R edge (the fronts parted), scanning down from the neck in 3 mm bands.
    uv_ = np.asarray(M['uv']); Xm_ = X * 1000
    eL = (pid == nm.index('front.L')) & (uv_[:, 0] < uv_[P['front.L:placketTopFold1'], 0] + 0.003)
    eR = (pid == nm.index('front.R')) & (uv_[:, 0] > uv_[P['front.R:placketTopOut'], 0] - 0.003)
    top = max(Xm_[P['front.L:cfNeck'], 2], Xm_[P['front.R:cfNeck'], 2]); vb = None
    for z in np.arange(top, hps[2] - 250, -3.0):
        a = Xm_[eL & (np.abs(Xm_[:, 2] - z) < 3)]; b = Xm_[eR & (np.abs(Xm_[:, 2] - z) < 3)]
        if not len(a) or not len(b): continue
        if a[:, 0].min() - b[:, 0].max() > 2.0: vb = z
        else: break
    lean = lambda a, b: np.degrees(np.arctan2(abs((g(a) - g(b))[0]), (g(a) - g(b))[2]))
    Xm = X * [-1, 1, 1]; dist, _ = cKDTree(X).query(Xm); cs = np.isin(pid, [nm.index('collar'), nm.index('stand')])
    print(f"{t:5s} roll {[f['deg'] for f in I['folds'] if 'open' in f['fold']]} band apart bottom {np.linalg.norm(g('stand:leftBottomCf')-g('stand:rightBottomCf')):3.0f} top {np.linalg.norm(g('stand:leftTopCf')-g('stand:rightTopCf')):3.0f}"
          f" lean {lean('stand:leftTopCf','stand:leftBottomCf'):3.0f}/{lean('stand:rightTopCf','stand:rightBottomCf'):3.0f} | points apart {np.linalg.norm(g('collar:leftTopEdge')-g('collar:rightTopEdge')):4.0f} (147) below HPS {hps[2]-g('collar:leftTopEdge')[2]:3.0f}/{hps[2]-g('collar:rightTopEdge')[2]:3.0f} (50-61)"
          f" | V below HPS {('%3.0f' % (hps[2]-vb)) if vb else ' - '} (~60) | collar+band mirror p95 {np.percentile(dist[cs],95)*1000:4.1f} | worn_open {I.get('worn_open_mm')}")
