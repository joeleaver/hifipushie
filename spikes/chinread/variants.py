"""variants.py <model> <out.png> <label>=<move>[,<move>..] ...: WHAT CAN GNM DO at the chin? The model's lower face under
the picture's fitted light (blockin.lit_render) beside the picture, front and 3/4, for identity variants. A move =
<measure>:<amount> (gnm_mm `mm:` direction in mm when the measure is one of gnm_mm.NAMES, others held; else the
least-norm change of a solve_report row, mm or sd). Columns: REFERENCE | the model | each variant."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import face_ruler as fr, blockin as bi, gnm_mm, solve_report as sr, store

m, out = sys.argv[1], sys.argv[2]
var = [("as solved", [])] + [(a.split("=")[0], [(x.split(":")[0], float(x.split(":")[1])) for x in a.split("=")[1].split(",")]) for a in sys.argv[3:]]
rj = bi._refs(m)
spec = store.load(m)
c0 = bi.identity(spec)
rw = sr.rows()


def moved(c, moves):
    c = c.copy()
    for nm, amt in moves:
        if nm in gnm_mm.NAMES:
            c += gnm_mm.direction(nm) * amt
        else:
            r = rw["R"][rw["names"].index(nm)]
            c += r / (r @ r) * amt
    return c


font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
rows_ = []
for vi in (0, 1):
    v, cam = rj["views"][vi], rj["cameras"][vi]
    img = Image.open(v["image"]).convert("RGB")
    h0 = fr.model_head(spec)
    P = fr._cam_points(cam, np.asarray(h0["L"], float)[:68])[1]
    cx, cy = P[[48, 54, 8]].mean(0)
    s = 1.35 * (P[8, 1] - P[33, 1])
    box = (cx - s, cy - 0.9 * s, cx + s, cy + 1.1 * s)
    tiles = [("REFERENCE", img.crop(tuple(int(x) for x in box)))]
    for lab, mv in var:
        c = moved(c0, mv)
        h = fr.model_head(spec, c, h0["kappa"])
        im, lt, ps = bi.lit_render(h["mesh"], cam, img)
        k = im.size[1] / img.size[1]
        tiles.append((lab + f"  |c| {np.linalg.norm(c):.1f} max {np.abs(c).max():.1f}", im.crop(tuple(int(x * k) for x in box))))
        print(vi, lab, "chin_width", round(float(rw["R"][rw["names"].index("chin_width")] @ c), 1), "jaw_width", round(float(rw["R"][rw["names"].index("jaw_width")] @ c), 1), flush=True)
    rows_.append(tiles)
S = 520
W = Image.new("RGB", (S * len(rows_[0]), (S + 34) * len(rows_)), "white")
d = ImageDraw.Draw(W)
for r, tiles in enumerate(rows_):
    for i, (lab, t) in enumerate(tiles):
        W.paste(t.resize((S, S), Image.LANCZOS), (i * S, r * (S + 34) + 34))
        d.text((i * S + 6, r * (S + 34) + 4), lab, fill=(150, 0, 0) if i else (0, 0, 0), font=font)
W.save(out)
print(out)
