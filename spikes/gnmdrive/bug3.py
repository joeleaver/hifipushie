import sys

import numpy as np
from PIL import Image

a = np.asarray(Image.open(sys.argv[1]).convert("RGB")).astype(float)
# grid: title 24 + col labels 18 = 42 top; left 120; cell 240 + pad 4
top, left, h = 42, 120, 244
for r in range(3):
    print(r, [round(float(np.abs(a[top + r * h: top + r * h + 240, left + c * h: left + c * h + 240] -
                                a[top + 1 * h: top + 1 * h + 240, left + c * h: left + c * h + 240]).mean()), 2) for c in range(3)])
