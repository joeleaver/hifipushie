"""section.py <stage model> [dx mm] [out png]: a sagittal section through eye.L (+dx) of the scene's meshes (every part)
and the lashes, zoomed on the lids: the margin's thickness, the lids against the ball, the lashes' path. 20 px/mm."""
import glob
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import store
from hifipushie.spec import expand_mirror

name = sys.argv[1]
dx = float(sys.argv[2]) / 1000 if len(sys.argv) > 2 else 0.0
out = sys.argv[3] if len(sys.argv) > 3 else f"/mnt/data/hifipushie/eyedetail/out/sec_{name}.png"
spec = store.load(name)
J = {k: np.asarray(v["pos"], float) for k, v in expand_mirror(spec)["joints"].items() if "pos" in v}
c = J["eye.L"]
x0 = c[0] + dx
S, W, H = 20.0, 900, 900  # px/mm; y from -30..+15 mm (forward is -y: drawn to the left), z -22..+22
img = Image.new("RGB", (W, H), (250, 250, 250))
d = ImageDraw.Draw(img)


def P(y, z):
    return (W * 0.62 + (y - c[1]) * 1000 * S, H / 2 - (z - c[2]) * 1000 * S)


for k in range(-20, 21, 5):  # mm grid
    d.line([P(c[1] - 0.03, c[2] + k / 1000), P(c[1] + 0.015, c[2] + k / 1000)], fill=(225, 225, 225))
    d.line([P(c[1] + k / 1000, c[2] - 0.022), P(c[1] + k / 1000, c[2] + 0.022)], fill=(225, 225, 225))
cols = [(40, 40, 40), (0, 110, 230), (200, 60, 0), (0, 150, 60)]
files = sorted(glob.glob(str(store._dir(name) / "scene_cache" / "*.npz")))
k = 0
for f in files:
    z = np.load(f, allow_pickle=True)
    if "verts" not in z.files:
        continue
    V = z["verts"].astype(float)
    F = z["faces"] if "faces" in z.files else z["tris"]
    col = (30, 20, 20) if "lashes" in f else cols[k % len(cols)]
    if "lashes" not in f:
        k += 1
    s = V[F][..., 0] - x0
    m = (s.min(1) < 0) & (s.max(1) > 0)
    near = np.abs(V[F[m]].mean(1) - c).max(1) < 0.035
    for tri in F[m][near]:
        p, sv = V[tri], V[tri][:, 0] - x0
        q = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if sv[a] * sv[b] < 0:
                t = sv[a] / (sv[a] - sv[b])
                q.append(p[a] + t * (p[b] - p[a]))
        if len(q) == 2:
            d.line([P(q[0][1], q[0][2]), P(q[1][1], q[1][2])], fill=col, width=2 if "lashes" not in f else 1)
d.text((10, 10), f"{name}: section x = eye.L {dx * 1000:+.1f} mm (forward to the left), 1 mm grid lines every 5", fill=(0, 0, 0))
img.save(out)
print(out)
