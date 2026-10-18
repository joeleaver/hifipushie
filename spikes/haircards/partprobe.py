import numpy as np, sys
Z = np.load('/mnt/data/hifipushie/haircards/exp/strands_hc_s2.npz', allow_pickle=True)
Q = Z['Q'].astype(float); cls = Z['cls']
C = np.array([float(x) for x in sys.argv[1].split(',')])
h = cls == 'head'; Q = Q[h]
fin = np.isfinite(Q[..., 0])
for reach_st in (4, 8):
    last = np.minimum(reach_st, fin.sum(1) - 1)
    p0 = Q[:, 0]; pk = Q[np.arange(len(Q)), np.maximum(last, 0)]
    d = pk - p0; v = p0 - C
    el = np.degrees(np.arcsin(np.clip(v[:, 2] / np.linalg.norm(v, axis=1), -1, 1)))
    xs = d[:, 0] / np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    top = el > 35
    print('reach', reach_st, 'top roots', top.sum(), 'xs pct', np.round(np.percentile(xs[top], [5, 25, 50, 75, 95]), 2))
    for thr in (0.15, 0.25, 0.35):
        print('  thr', thr, '+x', int((top & (xs >= thr)).sum()), '-x', int((top & (xs <= -thr)).sum()))
    # sweep by root x position near the front top
    fr = top & (v[:, 1] < 0)
    for lo in np.arange(-0.04, 0.041, 0.01):
        m = fr & (v[:, 0] >= lo) & (v[:, 0] < lo + 0.01)
        if m.sum(): print(f'   root x {lo*1000:+.0f}..{(lo+0.01)*1000:+.0f} mm: n {m.sum():5d} mean xs {xs[m].mean():+.2f}')
