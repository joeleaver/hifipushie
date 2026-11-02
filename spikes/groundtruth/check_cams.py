"""check_cams.py <pose>: (1) which rig cameras see the head, from where (azimuth round the head from its front,
elevation, distance, the head's size in the photo); (2) the calibration's frame checked: the scan's head vertices
through three cameras drawn on their photos -> out/cams_<pose>.png (LOOK: the dots must lie on the head)."""
import json
import sys
import numpy as np
from PIL import Image, ImageDraw
import gt, hsrd

pose = sys.argv[1]
Image.MAX_IMAGE_PIXELS = None
scan = gt.load_scan(pose)
S0 = gt.load_sim(gt.WORK / pose / "S0.json")
j = json.loads((gt.WORK / pose / "S0.json").read_text())
Lm = np.asarray(j["landmarks_scan"])
ctr = np.nanmean(Lm[[36, 45, 48, 54, 30]], 0)
Si = gt.inverse(S0)
fwd = np.asarray(Si[1]) @ np.array([0.0, -1.0, 0.0])      # the face's forward, scan frame
left = np.asarray(Si[1]) @ np.array([1.0, 0.0, 0.0])
up = np.asarray(Si[1]) @ np.array([0.0, 0.0, 1.0])
if (gt.WORK / pose / "T_rig.json").exists():      # the scan's frame is NOT the rig's (register.py): everything into the rig's
    T = gt.load_sim(gt.WORK / pose / "T_rig.json")
    ctr = gt.apply(T, ctr[None])[0]
    fwd, left, up = (np.asarray(T[1]) @ v for v in (fwd, left, up))
    scan["V"] = gt.apply(T, scan["V"])
else:
    print("NO T_rig.json yet: azimuths below are in the scan's frame and WRONG for the rig; run register.py, then this again")
C = hsrd.cams(pose)
rows = []
for n, c in C.items():
    if c["image"] is None:
        continue
    d = c["C"] - ctr
    dist = np.linalg.norm(d)
    az = np.degrees(np.arctan2(d @ left, d @ fwd))
    el = np.degrees(np.arcsin(d @ up / dist))
    with Image.open(c["image"]) as im:
        size = im.size
    p, z = hsrd.project(c, ctr[None], size)
    inside = 0 < p[0, 0] < size[0] and 0 < p[0, 1] < size[1] and z[0] > 0
    ppm = c["f35"] / 36 * max(size) / dist
    rows.append((n, az, el, dist, inside, ppm, size, p[0]))
print(f"{pose}: {len(rows)} photos; head centre (scan frame) {ctr.round(3)}")
see = [r for r in rows if r[4]]
for r in sorted(see, key=lambda r: abs(r[1])):
    print(f"  {r[0]:5s} az {r[1]:+7.1f} el {r[2]:+6.1f} dist {r[3]:.2f} m | {r[5]:.0f} px/m (a 15 cm face = {0.15 * r[5]:.0f} px) | {r[6]} | head at {r[7].round(0)}")
json.dump({r[0]: {"az": r[1], "el": r[2], "dist": r[3], "px_per_m": r[5], "inside": bool(r[4])} for r in rows}, open(gt.WORK / pose / "rig.json", "w"))
pick = [r for r in sorted(see, key=lambda r: abs(r[1]) + abs(r[2]))][:1] + [r for r in sorted(see, key=lambda r: abs(abs(r[1]) - 90) + abs(r[2]))][:2]
tiles = []
V = scan["V"][::7]
for r in pick:
    c = C[r[0]]
    im = Image.open(c["image"]).convert("RGB")
    P, z = hsrd.project(c, V, im.size)
    d = ImageDraw.Draw(im)
    for x, y in P[::3]:
        d.point((x, y), fill=(0, 255, 0))
    b = (P[:, 0].min() - 100, P[:, 1].min() - 100, P[:, 0].max() + 100, P[:, 1].max() + 100)
    t = im.crop(tuple(int(v) for v in b))
    t.thumbnail((900, 900))
    tiles.append(t)
W = sum(t.width for t in tiles)
sh = Image.new("RGB", (W, max(t.height for t in tiles)))
x = 0
for t in tiles:
    sh.paste(t, (x, 0))
    x += t.width
sh.save(gt.OUT / f"cams_{pose}.png")
print(gt.OUT / f"cams_{pose}.png", [r[0] for r in pick])
