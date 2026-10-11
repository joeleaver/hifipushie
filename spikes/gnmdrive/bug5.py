import sys

import numpy as np
from PIL import Image

a = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(int)
H, W, _ = a.shape
print(a.shape)
# find the row bands by the left label column being background and cells non-background: scan for identical bands
top, h = 42, 244
r0 = a[top:top + 240, 120:120 + 240 * 3 + 8]
r1 = a[top + h:top + h + 240, 120:120 + 240 * 3 + 8]
print("row0 vs row1 max abs diff", np.abs(r0 - r1).max(), "mean", np.abs(r0 - r1).mean())
d = np.clip(np.abs(r0 - r1).sum(2) * 10, 0, 255).astype(np.uint8)
Image.fromarray(d).save(sys.argv[2])
Image.fromarray(r0.astype(np.uint8)).save(sys.argv[2].replace(".png", "_r0.png"))
Image.fromarray(r1.astype(np.uint8)).save(sys.argv[2].replace(".png", "_r1.png"))
