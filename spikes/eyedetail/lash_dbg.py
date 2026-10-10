"""lash_dbg.py <model>: the lid lines and lashes of a model's head: counts, rim sizes, root heights; a front-plane
plot of the rim and the lashes (out/lash_dbg_<model>.png)."""
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import lashes, store, base as basemod
from hifipushie.spec import expand_mirror

name = sys.argv[1]
spec = store.load(name)
t = time.time()
s = expand_mirror(spec)
head = basemod.head_of(s, s["base"])
print("head", len(head["verts"]), "eye_r", head["eye_r"], f"{time.time() - t:.1f} s")
t = time.time()
L = lashes.lid_lines(head)
print(f"lid lines {time.time() - t:.1f} s")
for i, l in enumerate(L):
    ci, co = l["corners"]
    w = l["rho"][ci] + l["rho"][co]
    up = l["rho"][np.argmax(l["dirs"] @ l["up"])]
    dn = l["rho"][np.argmin(l["dirs"] @ l["up"])]
    print(f"eye {i}: width {w * 1000:.1f} mm, top {up * 1000:.1f} bottom {dn * 1000:.1f} mm, corners {ci} {co}")
t = time.time()
m = lashes.build(head, lashes.wanted(spec) or lashes.wanted({"base": {"lashes": True}}))
print(f"lashes: {len(m['verts'])} verts, {len(m['tris'])} tris, {time.time() - t:.1f} s")
# front-plane plot of eye 0
l = L[0]
S = 40
img = Image.new("RGB", (1000, 800), (240, 240, 240))
d = ImageDraw.Draw(img)
def px(P):
    q = P - l["centre"]
    return np.c_[500 + (q @ l["side"]) * 1000 * S / 1.5, 400 - (q @ l["up"]) * 1000 * S / 1.5]
rim = l["o2"] + np.c_[np.cos(l["theta"]) * l["rho"], np.sin(l["theta"]) * l["rho"]]
pts = np.c_[500 + rim[:, 0] * 1000 * S / 1.5, 400 - rim[:, 1] * 1000 * S / 1.5]
d.line([tuple(p) for p in np.r_[pts, pts[:1]]], fill=(0, 120, 255), width=2)
sel = m["eye"] == 0
V = m["verts"][sel]
Q = px(V)
for k in range(0, len(Q) - 1, 2):
    d.line([tuple(Q[k]), tuple(Q[k + 2])] if k + 2 < len(Q) else [tuple(Q[k]), tuple(Q[k])], fill=(30, 20, 20))
img.save(f"/mnt/data/hifipushie/eyedetail/out/lash_dbg_{name}.png")
print("saved")
