"""sheet1.py <before tag> <after tag> <out name> ["after label"]: er_01: photo | before | after, three rows:
(1) both eyes through the photo's fitted camera, one crop, the PHOTO's canthi as vertical lines on every tile, each
tile's own canthi as circles; (2) the subject's left eye closer, with that image's own ruler read drawn; (3) the ruler
table (every image read by the SAME reader; the models' mesh reads beside). Reads from out/rule.json (rule.py)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import blockin_brows as bb, eye_ruler as er

G = os.environ["G"] + "/out/"
R = json.load(open(G + "rule.json"))
bx = json.load(open(G + "box.json"))
K, box = bx["K"], np.array(bx["box"][:2])
q = bb._inputs("gd_T12")
mm = q["mm"]
before, after, name = sys.argv[1], sys.argv[2], sys.argv[3]
lab_after = sys.argv[4] if len(sys.argv) > 4 else "RESULT"
TILES = [("photo", "Tess photo (through its fitted camera)"), (before, "BEFORE: gb_fx (gb_01's FIXED)"), (after, lab_after)]
CROP = (240, 610, 1440, 1090)
W, H = CROP[2] - CROP[0], CROP[3] - CROP[1]
C2 = (840, 670, 1500, 1030)
H2 = int(round((C2[3] - C2[1]) * W / (C2[2] - C2[0])))
HEAD, TAB = 64, 640
S = Image.new("RGB", (3 * W, HEAD + H + 8 + H2 + TAB), "white")
d = ImageDraw.Draw(S)


def shot_xy(e, u, v):
    fr = er.frames(R["photo"]["read"][0]["c"], R["photo"]["read"][1]["c"]) if False else None
    return None


def frame_of(read, s):
    return er.frames(read[0]["c"], read[1]["c"])[s]


def to_shot(read, s, u, v):
    fr = frame_of(read, s)
    p = np.asarray(read[s]["c"]) + (u / mm) * fr["ex"] - (v / mm) * fr["ey"]
    return (p - box) * K


ph = R["photo"]["read"]
for i, (tag, lab) in enumerate(TILES):
    x0 = i * W
    im = Image.open(f"{G}s_{tag}.png").convert("RGB")
    S.paste(im.crop(CROP), (x0, HEAD))
    rd = R[tag]["read"]
    for s in (0, 1):                                    # the photo's canthi on every tile
        for key in ("inner", "outer"):
            px = to_shot(ph, s, *ph[s][key])
            d.line([(x0 + px[0] - CROP[0], HEAD), (x0 + px[0] - CROP[0], HEAD + H)], fill=(230, 30, 30), width=2)
            p2 = to_shot(rd, s, *rd[s][key])           # this tile's own
            cx, cy = x0 + p2[0] - CROP[0], HEAD + p2[1] - CROP[1]
            d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], outline=(255, 235, 0), width=3)
    m = er.mean(rd)
    d.text((x0 + 10, 4), lab, fill=(0, 0, 0), font_size=26)
    d.text((x0 + 10, 36), f"fissure {m['fissure']:.1f} mm; inner canthus {m['inner'][0]:.1f}, outer {m['outer'][0]:.1f} mm from the iris centre; "
                          f"opening {m['mrd1'] + m['mrd2']:.1f}; iris {m['iris']:.1f}", fill=(0, 0, 0), font_size=19)
    bx0, by0 = x0 + 16, HEAD + H - 20
    d.line([(bx0, by0), (bx0 + 10 / mm * K, by0)], fill=(255, 255, 255), width=6)
    d.line([(bx0, by0), (bx0 + 10 / mm * K, by0)], fill=(0, 0, 0), width=2)
    d.text((bx0 + 10 / mm * K + 6, by0 - 12), "10 mm", fill=(0, 0, 0), font_size=18)
    # row 2: the left eye, the tile's own read drawn
    z = W / (C2[2] - C2[0])
    t = im.crop(C2).resize((W, H2), Image.LANCZOS)
    dt = ImageDraw.Draw(t)
    e = rd[1]
    f2 = lambda u, v: tuple((to_shot(rd, 1, u, v) - C2[:2]) * z)  # noqa: E731
    cols = er.COLS
    for arr, colr in ((e["up"], (0, 235, 0)), (e["lo"], (0, 235, 0))):
        pts = [f2(u, v) for u, v in zip(cols, arr) if np.isfinite(v)]
        pts = [f2(*e["inner"])] + pts + [f2(*e["outer"])]
        dt.line(pts, fill=colr, width=3)
        for p in pts[1:-1]:
            dt.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], fill=colr)
    rr = e["iris"] / 2 / mm * K * z
    c0 = f2(0, 0)
    dt.ellipse([c0[0] - rr, c0[1] - rr, c0[0] + rr, c0[1] + rr], outline=(255, 235, 0), width=2)
    dt.line([(c0[0] - 10, c0[1]), (c0[0] + 10, c0[1])], fill=(255, 235, 0), width=2)
    for key in ("inner", "outer"):
        p = f2(*ph[1][key])
        dt.line([(p[0], 0), (p[0], H2)], fill=(230, 30, 30), width=2)
    S.paste(t, (x0, HEAD + H + 8))
# row 3: the table
y = HEAD + H + 8 + H2 + 12
a, b, c = (er.mean(R[t]["read"]) for t in ("photo", before, after))
mb, mc = (er.mean(R[t]["model"]) if R[t].get("model") else None for t in (before, after))
rows = [("fissure length (inner canthus -> where the eyeball ends)", "fissure", None, 1.0),
        ("inner canthus, mm from the iris centre (- = toward the nose)", "inner", 0, 0.6),
        ("outer canthus", "outer", 0, 0.45),
        ("canthal tilt, degrees (coarse)", "tilt", None, 1.8),
        ("upper margin over the iris centre at u = -6", "up", 1, 0.25), ("   at u = -3", "up", 2, 0.25), ("   at the pupil", "up", 3, 0.25),
        ("   at u = +3", "up", 4, 0.25), ("   at u = +6", "up", 5, 0.25),
        ("lower margin at u = -6", "lo", 1, 0.25), ("   at the pupil", "lo", 3, 0.25), ("   at u = +6", "lo", 5, 0.25),
        ("mm of iris hidden by the upper lid", "cover_up", None, 0.2),
        ("iris diameter (limbus circle)", "iris", None, 0.12)]
d.text((14, y), "THE RULER: every image read by the same edge reader (eye_ruler.read), mm at the model, each eye's frame from its iris centre, both eyes' mean."
                "  err = the reader's rms error on 14 dressed renders of known heads.", fill=(0, 0, 0), font_size=21)
y += 34
X = (14, 760, 930, 1100, 1270, 1390)
for xx, t in zip(X, ("measure", "photo", "before", "after", "err", "after - photo")):
    d.text((xx, y), t, fill=(0, 0, 0), font_size=21)
y += 30
for lab, key, j, err in rows:
    va, vb, vc = ((m[key] if j is None else m[key][j]) for m in (a, b, c))
    df = vc - va
    bad = abs(vb - va) > 2 * err
    good = abs(df) <= 2 * err
    d.text((X[0], y), lab, fill=(0, 0, 0), font_size=20)
    d.text((X[1], y), f"{va:6.1f}", fill=(0, 0, 0), font_size=20)
    d.text((X[2], y), f"{vb:6.1f}", fill=(200, 0, 0) if bad else (0, 0, 0), font_size=20)
    d.text((X[3], y), f"{vc:6.1f}", fill=(0, 130, 0) if good else (200, 0, 0), font_size=20)
    d.text((X[4], y), f"{err:.2f}", fill=(90, 90, 90), font_size=20)
    d.text((X[5], y), f"{df:+.1f}", fill=(0, 130, 0) if good else (200, 0, 0), font_size=20)
    y += 27
notes = open(G + "sheet1_notes.txt").read().splitlines() if os.path.exists(G + "sheet1_notes.txt") else []
yy = HEAD + H + 8 + H2 + 46
for k, t in enumerate(notes):
    d.text((1600, yy + k * 27), t, fill=(0, 0, 0), font_size=20)
out = os.environ["R"] + "/" + name
S.save(out)
print(out, S.size)
