"""foldmask.py <model with lid_fold> <out.png>: GNM's left-eye lid region front-on (x, y in mm), each skin vertex a dot
coloured by the fold's displacement (black = unmoved, yellow = largest), rings 0 / 5 / 10 / 12 traced in cyan; left =
the fold's chain targets only (how it was: a comb), right = with every ring vertex filled and the fade past the patch."""
import sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import gnm_fold as gf, store
m, outp = sys.argv[1:3]
cfg = store.load(m)["base"]["head"]["lid_fold"]
V = gf.vertices() / 1000.0
T = gf.gc.gnm()["T"] * 1000.0
J = gf.gc.gnm()["J"][2] * 1000.0
t = gf.topo()
fill = gf._fill_rings
gf._fill_rings = lambda *a, **k: None
d0 = gf.mesh_delta(V, None, cfg) * 1000.0
gf._fill_rings = fill
d1 = gf.mesh_delta(V, None, cfg) * 1000.0
sel = (np.abs(T[:, 0] - J[0]) < 22) & (np.abs(T[:, 1] - J[1]) < 18) & (T[:, 0] > 0) & (t["ring"] >= 0) & (t["ring"] < 99)
S, k = 700, 700 / 44.0
img = Image.new("RGB", (2 * S, S), (15, 15, 15))
dr = ImageDraw.Draw(img)
mx = max(float(np.linalg.norm(d1, axis=1).max()), 1e-6)
for j, d in enumerate((d0, d1)):
    for v in np.flatnonzero(sel):
        x, y = j * S + (T[v, 0] - J[0] + 22) * k, (J[1] - T[v, 1] + 18) * k + 30
        a = float(np.linalg.norm(d[v])) / mx
        c = (int(255 * min(1, 2 * a)), int(255 * a), 40) if a > 0 else (70, 70, 70)
        dr.ellipse([x - 3, y - 3, x + 3, y + 3], fill=c)
    for r in (0, 5, 10, 12):
        q = np.flatnonzero(sel & (t["ring"] == r))
        ang = np.arctan2(T[q, 1] - J[1], T[q, 0] - J[0])
        q = q[np.argsort(ang)]
        pts = [(j * S + (T[v, 0] - J[0] + 22) * k, (J[1] - T[v, 1] + 18) * k + 30) for v in q]
        if len(pts) > 2:
            dr.line(pts + [pts[0]], fill=(0, 200, 230), width=1)
    dr.text((j * S + 10, 8), ("BEFORE: chain vertices only (a comb)" if j == 0 else "NOW: every ring vertex + fade past rings / ends") + "   (outer corner to the right)", fill=(255, 255, 255))
img.save(outp)
print("max mm", round(mx, 2))
