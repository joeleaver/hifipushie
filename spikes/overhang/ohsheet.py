"""ohsheet.py <out name> <notes file | -> <tag>|<title> ...: a sheet of fitted-camera shots, 2 rows (dressed, clay under
the hard top light), one column per tag; the first tag may be "photo" (the reference, shown in both rows). Numbers on
every tile from out/nums.json (raw mesh), out/stagehang.json (the rendered mesh), out/prof.json (luminance read:
the dark line's contrast; the photo's is the target). Env C (crop of the shot), Z (zoom)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter1d

G = os.environ["G"] + "/out/"
OUT = os.environ["R"] + "/"
C = tuple(int(x) for x in os.environ.get("C", "860,640,1480,1030").split(","))
Z = float(os.environ.get("Z", "1.5"))
W, H = int((C[2] - C[0]) * Z), int((C[3] - C[1]) * Z)
HEAD = 124
MMPX = 0.0792 / Z


def J(f):
    return json.load(open(G + f)) if os.path.exists(G + f) else {}


nums, stg, prof = J("nums.json"), J("stagehang.json"), J("prof.json")


def feat(p, Hh):
    st = Hh[1] - Hh[0]
    sm = gaussian_filter1d(p, 0.15 / st)
    wide = gaussian_filter1d(p, 1.5 / st)
    sel = (Hh >= 2.5) & (Hh <= 8.0)
    d = wide - sm
    i = int(np.flatnonzero(sel)[np.argmax(d[sel])])
    return float(Hh[i]), float(d[i])


def lum(tag, kind):
    if tag not in prof or kind not in prof[tag]:
        return None
    p = np.array(prof[tag][kind]).mean(0)
    Hh = np.arange(p.shape[1]) * 0.05
    return np.array([feat(x, Hh) for x in p]).mean(0)


def lines(tag, kind):
    out = []
    if tag == "photo":
        f = lum("photo", "s")
        return [f"her picture: the fold's dark line {f[0]:.1f} mm over the lid margin,", f"line contrast {f[1]:.2f} (the target for every dressed tile)"] if f is not None else []
    n = nums.get(tag)
    if kind == "s":
        if n:
            out.append(f"raw GNM mesh: overhang {n['hang']:.2f} mm (max {n['hang_max']:.2f}), " + (f"turn {n['turn']:.0f} deg" if n['hang'] < 0.3 else "folded back") + f", crease {n['h']:.1f} mm up")
            if "dc" in n:
                out.append(f"cost vs {n['src']}: |dc| {n['dc']:.1f} (|c| {n['c']:.1f}), brow {n['brow_drop']:+.1f} mm down, other skin {n['held_rms']:.2f} rms / {n['held_max']:.1f} max")
            else:
                out.append(f"|c| {n['c']:.1f}")
        f = lum(tag, "s")
        if f is not None:
            out.append(f"dressed: line contrast {f[1]:.2f} at {f[0]:.1f} mm (hers 0.19 at 4.7)")
    else:
        s = stg.get(tag)
        if s:
            out.append(f"rendered mesh: skin hidden behind skin {np.mean([c['hang'] for c in s['cols']]):.1f} mm tall, gap {np.mean([c['gap'] for c in s['cols']]):.1f} mm")
        f = lum(tag, "k")
        if f is not None:
            out.append(f"clay: shadow edge contrast {f[1]:.2f} at {f[0]:.1f} mm")
        if n and n.get("measures"):
            out.append("moved: " + ", ".join(f"{k} {v:+.1f}" for k, v in n["measures"][:3]))
    return out


def tile(S, d, x, y, file, title, ls):
    if os.path.exists(G + file + ".png"):
        S.paste(Image.open(G + file + ".png").convert("RGB").crop(C).resize((W, H), Image.LANCZOS), (x, y + HEAD))
    d.text((x + 10, y + 4), title, fill=(0, 0, 0), font_size=28)
    for i, t in enumerate(ls[:3]):
        d.text((x + 10, y + 42 + i * 26), t, fill=(0, 0, 0), font_size=20)
    bx, by = x + 16, y + HEAD + H - 22
    d.line([(bx, by), (bx + 10 / MMPX, by)], fill=(255, 255, 255), width=6)
    d.line([(bx, by), (bx + 10 / MMPX, by)], fill=(0, 0, 0), width=2)
    d.text((bx + 10 / MMPX + 6, by - 12), "10 mm", fill=(0, 0, 0), font_size=18)


name, nf = sys.argv[1:3]
items = [a.split("|", 1) for a in sys.argv[3:]]
notes = open(nf).read().splitlines() if nf != "-" else []
S = Image.new("RGB", (len(items) * W, 2 * (H + HEAD) + 20 + 27 * len(notes)), "white")
d = ImageDraw.Draw(S)
for i, (tag, title) in enumerate(items):
    for r, kind in enumerate(("s", "k")):
        f = "s_photo" if tag == "photo" else f"{kind}_{tag}"
        tt = title + ("" if tag == "photo" else (", dressed" if kind == "s" else ", clay, hard light"))
        if tag == "photo" and r == 1:
            ls = ["clay row: the rendered mesh, one hard light 39 deg above the front", "an overhang casts a hard shadow; a soft valley only shades"]
        else:
            ls = lines(tag, kind)
        tile(S, d, i * W, r * (H + HEAD), f, tt, ls)
y = 2 * (H + HEAD) + 10
for k, t in enumerate(notes):
    d.text((14, y + k * 27), t, fill=(0, 0, 0), font_size=21)
S.save(OUT + name)
print(OUT + name, S.size)
