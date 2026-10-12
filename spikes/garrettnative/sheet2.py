"""sheet2.py <out.png> <title> <label>=<model> ...: Joe's sheet with any number of model columns after REFERENCE (the
first model's reference crops); rows as sheet.py: whole head front (hair), three-quarter (hair, the front painting's
light), profile (NO REFERENCE), eyes, mouth and chin, clay front. Tiles: tiles.py / clayface.py under $G/out/<model>/."""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gnmnative"))
from strip import row, stack  # noqa: E402

G = "/mnt/data/hifipushie/garrettnative/out"
out, title = sys.argv[1:3]
cols = [a.split("=", 1) for a in sys.argv[3:] if not a.startswith("tile=")]
T = int(next((a[5:] for a in sys.argv[3:] if a.startswith("tile=")), 520))
first = cols[0][1]


def t(m, f, sub="dressed"):
    p = f"{G}/{m}/{sub}/{f}.png"
    return p if os.path.exists(p) else None


def clay(m, col):
    p = t(m, "face_v0", "clay")
    if not p:
        return None
    im = Image.open(p)
    s = im.height
    return im.crop((col * s, 0, (col + 1) * s, s))


def r(ref_label, ref, f, labels=False, fn=None):
    return row([(ref_label, ref)] + [((lab if labels else ""), (fn(m) if fn else t(m, f))) for lab, m in cols], T, fs=max(18, T // 17))


rows = [
    r("REFERENCE (painting 1)", t(first, "head_v0_ref"), "head_v0", labels=True),
    r("REFERENCE (painting 2); ours: 3/4, front light", t(first, "head_v1_ref"), "head_v1_fl"),
    r("profile: NO REFERENCE", None, "profile_right"),
    r("eyes", t(first, "eyes_v0_ref"), "eyes_v0"),
    r("mouth and chin", t(first, "mouth_chin_v0_ref"), "mouth_chin_v0"),
    r("clay, front (base shape only)", clay(first, 0), None, fn=lambda m: clay(m, 1)),
]
stack(rows, title, fs=40).save(out)
print(out)
