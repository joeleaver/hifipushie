"""tour.py <model> [out dir] [features=eyes,nose,...] [tile=480]: THE FEATURE TOUR. After a solve, one SMALL image per
feature and view (reference crop | model clay under the photo's light | 50 % overlay | clay under raking light), at
the picture's own resolution where it has it, for looking at ONE feature at a time (Joe, 2026-10-12: whole contact
sheets overwhelm the viewer; a 6240 px sheet seen at 2000 px hid Garrett's notched chin). Built on blockin.focus
(feature-local registration); adds a tight "chin" and a "brow_forehead" feature. Prints the files; the reader then
looks at each and writes, per feature: what differs, and WHAT IS HERE THAT THE MODEL HAS NO PARAMETER FOR."""
import os, sys
from PIL import Image
from hifipushie import blockin as bi

bi.FEATURES.setdefault("chin", {"lm": [6, 7, 8, 9, 10, 56, 57, 58], "pairs": [(8, 152), (57, 17)], "lines": [],
                                "stages": (), "squint_mm": 3.0, "pad": 1.6})
bi.FEATURES.setdefault("brow_forehead", {"lm": list(range(17, 27)) + [27], "pairs": [(19, 105), (24, 334), (27, 168)],
                                         "lines": [], "stages": (), "squint_mm": 4.0, "pad": 1.5})
m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
out = next((a for a in sys.argv[2:] if "=" not in a), f"/mnt/data/hifipushie/tour/{m}")
os.makedirs(out, exist_ok=True)
T = int(kw.get("tile", 480))
feats = kw.get("features", "eyes,brow_forehead,nose,mouth,chin,chin_jaw,cheeks,ears").split(",")
nv = len(bi._refs(m)["views"])
KEEP = (0, 1, 2, 4)   # photo | clay | overlay | raking
for f in feats:
    for vi in range(nv):
        tmp = f"{out}/_{f}_{vi}.png"
        try:
            bi.focus(m, f, tmp, views=[vi], T=T)
        except Exception as e:  # noqa: BLE001
            print(f"{f} view {vi}: skipped ({str(e)[:80]})")
            continue
        im = Image.open(tmp)
        W = Image.new("RGB", (T * len(KEEP), T), "white")
        for k, c in enumerate(KEEP):
            W.paste(im.crop((c * T, 18, (c + 1) * T, 18 + T)), (k * T, 0))
        p = f"{out}/{f}_v{vi}.png"
        W.save(p); os.remove(tmp)
        print(p)
