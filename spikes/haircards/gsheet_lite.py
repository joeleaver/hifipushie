"""gsheet.py's crop box and ID mask without its argv (colour.py)."""
import numpy as np
from PIL import Image
C1, C3 = 540, 180
GPXM1 = 540 / np.tan(np.radians(29.5))  # game pixels per metre at 1 m


def crop_box(dist):
    s = C1 if dist == 1 else C3
    dy = int(0.05 * GPXM1 / dist)  # the tail hangs: centre the crop a little below the head centre
    return (540 - s // 2, 540 - s // 2 + dy, 540 + s // 2, 540 + s // 2 + dy)


def idmask(f, box):
    i = np.asarray(Image.open(f).convert("RGB").crop(box), int)
    return np.abs(i[..., 0] - i[..., 1]) > 60  # measure_hc's hair test


