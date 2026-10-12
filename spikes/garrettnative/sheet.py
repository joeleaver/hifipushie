"""sheet.py <out.png> new=<model> old=<model> [tile=560]: Joe's sheet: REFERENCE | GNM-native Garrett | current
garrett_a1; rows whole head front (hair), three-quarter (hair), profile (NO REFERENCE), eyes, mouth and chin, clay
front. Tiles are tiles.py's ($G/out/<model>/dressed/...) and tour.py's clay ($G/out/<model>/clay/face_v0.png)."""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gnmnative"))
from strip import row, stack  # noqa: E402

G = "/mnt/data/hifipushie/garrettnative/out"
out = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
T = int(kw.get("tile", 560))
new, old = kw["new"], kw["old"]


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


rows = [
    row([("REFERENCE (painting 1)", t(new, "head_v0_ref")), ("GNM-NATIVE garrett_n1", t(new, "head_v0")), ("CURRENT garrett_a1", t(old, "head_v0"))], T),
    row([("REFERENCE (painting 2)", t(new, "head_v1_ref")), ("three-quarter", t(new, "head_v1")), ("", t(old, "head_v1"))], T),
    row([("NO REFERENCE", None), ("profile (unseen angle)", t(new, "profile_right")), ("", t(old, "profile_right"))], T),
    row([("eyes", t(new, "eyes_v0_ref")), ("", t(new, "eyes_v0")), ("", t(old, "eyes_v0"))], T),
    row([("mouth and chin", t(new, "mouth_chin_v0_ref")), ("", t(new, "mouth_chin_v0")), ("", t(old, "mouth_chin_v0"))], T),
    row([("clay, front", clay(new, 0)), ("(shape only)", clay(new, 1)), ("", clay(old, 1))], T),
]
stack(rows, kw.get("title", "GARRETT, GNM-native (two paintings only)"), fs=46).save(out)
print(out)
