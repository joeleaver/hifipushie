"""tonguealb.py <glb>: the tongue's baked albedo (sRGB, at its vertices' UVs) by depth behind its tip (rest, along +y)."""
import sys, numpy as np
sys.argv = [sys.argv[0], sys.argv[1], "/dev/null", "neutral"]
exec(open("/mnt/data/hifipushie/assembly/mouthhits_v1.py").read().split("PARTS = ")[0])
uv, tex = uv_of("tongue"); V = g["meshes"]["tongue"]["V"]; th, tw = tex.shape[:2]
c = tex[np.clip((uv[:, 1] * th).astype(int), 0, th - 1), np.clip((uv[:, 0] * tw).astype(int), 0, tw - 1)].astype(float)
dep = (V[:, 1] - V[:, 1].min()) * 1e3; top = V[:, 2] > np.percentile(V[:, 2], 50)
for a in range(0, 60, 6):
    m = (dep >= a) & (dep < a + 6)
    if m.any(): print(f"{a:2d}-{a+6} mm: n {m.sum():3d} all {c[m].mean(0).round()} upper half {c[m & top].mean(0).round() if (m & top).any() else '-'}")
