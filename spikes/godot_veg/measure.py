"""check.gd's pictures compared: per view and sun, the mean colour (sRGB 0..1) of foliage and wood pixels of each GLB,
and the impostor's difference from the mesh LOD before it; a contact sheet.

  python spikes/godot_veg/measure.py <prefix> <sheet.png> <stem a> <stem b> ...     (the last stem is judged against the one before it)
"""
import sys
import numpy as np
from PIL import Image, ImageDraw

prefix, sheet = sys.argv[1:3]
stems = sys.argv[3:]
views = ["front", "diag", "side", "back20"]
suns = ["left", "front", "behind"]


def split(im):
    a = np.asarray(im.convert("RGB"), float) / 255
    bg = (a[..., 0] > 0.9) & (a[..., 1] < 0.15) & (a[..., 2] > 0.9)
    mix = (a[..., 0] > a[..., 1] + 0.25) & (a[..., 2] > a[..., 1] + 0.25)  # (edge pixels mixed with the background)
    fg = ~bg & ~mix
    mx, mn = a.max(-1), a.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    wood = fg & (sat < 0.22)
    fol = fg & ~wood
    return a, fol, wood, fg


rows = []
cells = []
for sn in suns:
    for vn in views:
        got = {}
        strip = []
        for st in stems:
            im = Image.open(f"{prefix}_{st}_{vn}_{sn}.png")
            a, fol, wood, fg = split(im)
            got[st] = (a[fol].mean(0) if fol.any() else np.zeros(3), a[wood].mean(0) if wood.any() else np.zeros(3), fg.mean(), fol.mean(), wood.mean())
            strip.append(im.resize((256, 256)))
        cells.append((f"{vn} / sun {sn}", strip))
        ref, imp = got[stems[-2]], got[stems[-1]]
        lum = lambda c: float(c @ [0.2126, 0.7152, 0.0722])
        rows.append((vn, sn, lum(ref[0]), lum(imp[0]), lum(ref[1]), lum(imp[1]), ref[2], imp[2], ref[0], imp[0], ref[1], imp[1]))
print(f"{stems[-2]} (mesh) vs {stems[-1]} (impostor): mean luma of foliage / wood pixels (display sRGB values), covered share of the frame")
print("view    sun     foliage mesh  imp   ratio | wood mesh  imp   ratio | cover mesh  imp")
fr, wr = [], []
for vn, sn, fm, fi, wm, wi, cm, ci, *rest in rows:
    fr.append(fi / max(fm, 1e-6))
    wr.append(wi / max(wm, 1e-6))
    print(f"{vn:7s} {sn:7s} {fm:11.3f} {fi:6.3f} {fr[-1]:6.2f} | {wm:8.3f} {wi:6.3f} {wr[-1]:6.2f} | {cm:9.3f} {ci:6.3f}")
print(f"foliage ratio impostor / mesh: mean {np.mean(fr):.2f}, range {min(fr):.2f} .. {max(fr):.2f};  wood: mean {np.mean(wr):.2f}, range {min(wr):.2f} .. {max(wr):.2f}")
for vn, sn, *_, rf, ri, rw, rwi in rows:
    print(f"  {vn:7s} {sn:7s} foliage rgb mesh {rf.round(3)} imp {ri.round(3)}   wood mesh {rw.round(3)} imp {rwi.round(3)}")
W = 256 * len(stems)
out = Image.new("RGB", (W * len(views), (256 + 14) * len(suns)), (30, 30, 30))
d = ImageDraw.Draw(out)
for i, (lab, strip) in enumerate(cells):
    r, c = divmod(i, len(views))
    for j, im in enumerate(strip):
        out.paste(im, (c * W + j * 256, r * 270 + 14))
    d.text((c * W + 3, r * 270 + 1), lab + "   " + " | ".join(stems), fill=(255, 255, 255))
out.save(sheet)
print("sheet", sheet)
