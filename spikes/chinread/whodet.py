"""whodet.py <model>: who.py's saved per-read pushes, per landmark (front / 3q anchors) and per outline stretch."""
import sys, numpy as np
d = np.load(f"/mnt/data/hifipushie/chinread/out/who_{sys.argv[1]}.npz")
mn = list(d["mnames"]); typ, view, nm, push, e = d["typ"], d["view"], d["names"], d["push"], d["e"]
cols = [mn.index(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else ("chin_width", "jaw_width", "gonial_width"))]
for vw in ("front", "3q"):
    ii = np.flatnonzero((typ == "landmark") & (view == vw))
    lm = {}
    for i in ii:
        lm.setdefault(nm[i].split(".")[0], []).append(i)
    rows = sorted(((k, push[v][:, cols].sum(0), [float(e[j]) for j in v]) for k, v in lm.items()), key=lambda t: -abs(t[1][0]) - abs(t[1][1]))
    print(f"-- landmark {vw}: push on chin_width / jaw_width / gonial_width (mm), error x, y (mm)")
    for k, p, ee in rows[:16]:
        print(f"   {k:6s} {p[0]:+.2f} {p[1]:+.2f} {p[2]:+.2f}   e {ee[0]:+.2f} {ee[1]:+.2f}")
    grp = {"jaw 0-16": range(0, 17), "brows 17-26": range(17, 27), "nose 27-35": range(27, 36), "eyes 36-47": range(36, 48), "mouth 48-67": range(48, 68)}
    for g, r in grp.items():
        jj = [j for k, v in lm.items() if int(k[2:]) in r for j in v]
        if jj:
            print(f"   {g:12s} n {len(jj):3d} push {push[jj][:, cols].sum(0).round(2)} bias {e[jj].mean():+.2f} rms {np.sqrt((e[jj]**2).mean()):.2f}")
for vw in ("front", "3q", "profile"):
    ii = np.flatnonzero((typ == "outline") & (view == vw))
    X = d["X"][ii]
    z = X[:, 2]
    print(f"-- outline {vw}: by height band (world z, m) and side: n, bias, push on chin_width / jaw_width / gonial")
    for lo in np.arange(z.min(), z.max(), 0.03):
        hi = lo + 0.03
        for sd, mk in (("x<0", X[:, 0] < 0), ("x>0", X[:, 0] >= 0)):
            k = ii[(z >= lo) & (z < hi) & mk]
            if len(k):
                print(f"   z {lo:.3f}-{hi:.3f} {sd} n {len(k):3d} bias {e[k].mean():+.2f} push {push[k][:, cols].sum(0).round(2)}")
