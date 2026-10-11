"""freedom.py: what is in GNM beyond the 170 head comps at the lid, and how much freedom each ring row has.
Per ring pair (k, k+1) on radial chains over the lid's middle: the template spacing in v (front-view height), and the
sd under N(0, I) of the pair's relative v and w motion (identity 170; eye expression 100), per vertex pair and for
the pair's MEAN over the middle of the lid (a fold is coherent along the lid)."""
import numpy as np

import ohlib as oh

g = oh.g
ch = oh.chains(7.0)
print("chains", ch.shape)
ids = ch.ravel()
print("identity comps 170..252 (eyes 3, teeth 80) at lid rings 0..12: max |basis| mm",
      np.abs(g["IB"][170:253][:, ids]).max() * 1000)
print("  eyes comps at the eyeball verts: max", np.abs(g["IB"][170:173][:, g["groups"]["eyes"]]).max() * 1000,
      "; eyes comps at skin: max", np.abs(g["IB"][170:173][:, g["groups"]["skin"]]).max() * 1000,
      "; teeth comps at skin_exterior: max", np.abs(g["IB"][173:253][:, g["groups"]["skin_exterior"]]).max() * 1000)
en = g["ex_names"]
for lab in ("left_eye", "right_eye", "lower", "tongue", "pupil"):
    sl = [i for i, n in enumerate(en) if n.startswith(lab)]
    print(f"expression {lab:10s} n {len(sl):3d}: max |basis| at the left lid rings {np.abs(g['EB'][sl][:, ids]).max() * 1000:.3f} mm")
print("skinning weights at the lid rings (neck, head, left_eye, right_eye): max per joint", g["W"][:, ids].max(1).round(3),
      "| left_eye joint: skin verts with weight > 0:", int(((g["W"][2] > 0) & g["groups"]["skin"]).sum()),
      "of", int((g["W"][2] > 0).sum()), "weighted verts")
IB = oh.basis(ids).reshape(170, *ch.shape, 3)
EBn = [i for i, n in enumerate(en) if n.startswith("left_eye")]
EB = (g["EB"][EBn][:, ids].astype(float) * 1000).reshape(len(EBn), *ch.shape, 3)
v, w = oh.profile(oh.T, ch)
print("\nring pair | template dv (mean) | identity: sd(dv) per pair, sd(mean dv), z = dv / sd(mean) | sd(dw) mean | eye expr: sd(mean dv), sd(mean dw)")
for k in range(0, ch.shape[1] - 1):
    dv0 = (v[:, k + 1] - v[:, k])
    d = IB[:, :, k + 1] - IB[:, :, k]                 # (170, n, 3)
    sd_pair = np.sqrt((d[..., 1] ** 2).sum(0)).mean()
    sd_mean = np.sqrt((d[..., 1].mean(1) ** 2).sum())
    sdw = np.sqrt((d[..., 2].mean(1) ** 2).sum())
    de = EB[:, :, k + 1] - EB[:, :, k]
    print(f"  {k:2d}-{k + 1:<2d} | {dv0.mean():5.2f} | {sd_pair:5.2f} {sd_mean:5.2f} z {dv0.mean() / sd_mean:5.1f} | {sdw:5.2f} | "
          f"{np.sqrt((de[..., 1].mean(1) ** 2).sum()):5.2f} {np.sqrt((de[..., 2].mean(1) ** 2).sum()):5.2f}")
print("\nsd(mean dv) of ring pairs 4-5, 5-6, 6-7, 7-8 by identity block:")
for a, b in ((0, 10), (10, 40), (40, 80), (80, 120), (120, 170)):
    print(f"  comps {a:3d}-{b:3d}:", " ".join(f"{np.sqrt((((IB[a:b, :, k + 1] - IB[a:b, :, k])[..., 1].mean(1)) ** 2).sum()):.3f}" for k in (4, 5, 6, 7)))
print("\nfront-view reversal needed for an overhang: template v[k+2] - v[k], sd of its mean over the lid's middle (identity):")
for k in range(2, 9):
    d = (IB[:, :, k + 2] - IB[:, :, k])[..., 1].mean(1)
    m = np.mean(v[:, k + 2] - v[:, k])
    s = np.sqrt((d ** 2).sum())
    print(f"  rings {k}->{k + 2}: template {m:5.2f} mm, sd {s:.2f} -> least |dc| for 0 mm: {m / s:.1f}, for a 1 mm overhang: {(1 + m) / s:.1f}")
