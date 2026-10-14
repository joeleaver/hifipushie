"""bands.py <png> ...: colour_bands + colour_variation of the HAIR in our own renders (dark, non-backdrop pixels,
largest piece, eroded 2 px): ours vs ours (a render as the target), at the render's own pixels (mm_px given)."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from hifipushie import hair

for f in sys.argv[1:]:
    im = Image.open(f).convert("RGB")
    a = np.asarray(im, float)
    bg = np.median(a[:40, :40].reshape(-1, 3), 0)
    lum = a @ [0.2126, 0.7152, 0.0722]
    m = (np.abs(a - bg).max(-1) > 26) & (lum < 0.52 * (bg @ [0.2126, 0.7152, 0.0722]))
    L, A, B = hair._lab(a)
    m &= (np.hypot(A, B) < 25)  # (not skin: skin is more saturated than this hair)
    m = ndi.binary_opening(m, iterations=2)
    lab, k = ndi.label(m)
    m = lab == (1 + int(np.argmax(ndi.sum(m, lab, range(1, k + 1)))))
    m = ndi.binary_erosion(m, iterations=2)
    b = hair.colour_bands(im, m, 0.3)
    v = b["variation"]
    print(f.split("/")[-1], " ".join(f"{k_} L {b[k_]['L']:.1f} C {b[k_]['chroma']:.1f} h {b[k_]['hue']:.0f}" for k_ in ("mean", "shadow", "highlight")),
          f"| L_sd {v['L_sd']} ribbons {v['ribbons']['share']} / {v['ribbons']['contrast']} edge {v.get('edge_L')} core {v.get('core_L')}")
