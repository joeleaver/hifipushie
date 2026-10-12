"""bscheck.py <image> ...: the detector's blendshape scores per picture (the ones over 0.08 in any), side by side:
does the detector tell a known expression (the benchmark's _x pictures) from the neutral (_n)?"""
import sys
from PIL import Image
from hifipushie import likeness
ims = sys.argv[1:]
D = likeness.detect_info([Image.open(f).convert("RGB") for f in ims])
keys = sorted({k for d in D if d for k, v in (d.get("bs") or {}).items() if v > 0.08})
print(" " * 22 + "  ".join(f.split("/")[-1][-12:-4] for f in ims))
for k in keys:
    print(f"{k:22s}" + "  ".join(f"{(d.get('bs') or {}).get(k, 0):8.2f}" if d else "    none" for d in D))
