"""colour.py <tag> [views] : hair L* of the cards vs the groom (gS) on the COMMON hair mask (both ID passes, eroded),
and the albedo scale k that brings the cards' mean L* to the groom's, through the AgX display curve (out/agx_ramp.png:
Blender's AgX of a grey ramp, so pixel L* -> scene-linear grey, x k, -> L*). Diffuse scales with albedo; the specular
does not, so k is a lower bound on the darkening needed (the result lands a little light)."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as nd
from scipy.optimize import brentq
from skimage.color import rgb2lab
sys.path.insert(0, "/mnt/data/hifipushie/haircards")
from gsheet_lite import crop_box, idmask
D = "/mnt/data/hifipushie/haircards"
v_in = np.load(f"{D}/out/agx_ramp_in.npy")
ramp = np.asarray(Image.open(f"{D}/out/agx_ramp.png").convert("RGB"), float)[0] / 255
Lr = rgb2lab(ramp[None])[0, :, 0]
Lr = np.maximum.accumulate(Lr)
lv = np.log(v_in)
def to_lin(L): return np.exp(np.interp(L, Lr, lv))
def to_L(y): return np.interp(np.log(np.maximum(y, 1e-6)), lv, Lr)
tag = sys.argv[1]
views = (sys.argv[2] if len(sys.argv) > 2 else "g1v0,g1v1,g1v2,g1backl,g3v0,g3backl").split(",")
for v in views:
    dist = int(v[1]); box = crop_box(dist)
    try:
        m = idmask(f"{D}/out/id_hc_s2_gS_{v}.png", box) & idmask(f"{D}/out/id_hc_s2_{tag}_{v}.png", box)
    except FileNotFoundError:
        print(v, "missing"); continue
    m = nd.binary_erosion(m, iterations=3 if dist == 1 else 1)
    LABg = rgb2lab(np.asarray(Image.open(f"{D}/out/s_hc_s2_gS_{v}.png").convert("RGB").crop(box), float) / 255)[m]
    LABt = rgb2lab(np.asarray(Image.open(f"{D}/out/s_hc_s2_{tag}_{v}.png").convert("RGB").crop(box), float) / 255)[m]
    Lg, Lt = LABg[:, 0], LABt[:, 0]
    Cg, Ct = np.hypot(LABg[:, 1], LABg[:, 2]).mean(), np.hypot(LABt[:, 1], LABt[:, 2]).mean()
    hg, ht = (np.degrees(np.arctan2(X[:, 2].mean(), X[:, 1].mean())) for X in (LABg, LABt))
    y = to_lin(Lt)
    k = brentq(lambda k: to_L(y * k).mean() - Lg.mean(), 0.05, 5)
    print(f"{v}: px {m.sum():6d}  groom L* {Lg.mean():5.1f}  {tag} {Lt.mean():5.1f}  k {k:.3f}  (lin mean ratio {to_lin(Lg).mean() / y.mean():.3f})  C* {Cg:4.1f} / {Ct:4.1f}  hue {hg:3.0f} / {ht:3.0f}")
