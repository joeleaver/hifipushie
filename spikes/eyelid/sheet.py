"""sheet.py <best tag> <before tag> <donor tag> [variant tag]: el_01 (reference | best | before | #376: dressed row, clay
row, numbers under each tile from surf.json / prof.json) and, with a variant tag, el_04 (the orbit: the model drawn on
the side pictures, before | variant; then photo | variant dressed | best dressed | variant clay)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

G = os.environ["G"] + "/out/"
OUT = os.environ["R"] + "/"
C = (860, 640, 1480, 1030)
Z = 1.5
W, H = int((C[2] - C[0]) * Z), int((C[3] - C[1]) * Z)
HEAD = 96
MMPX = 0.0792 / Z      # mm per sheet px (shot.py: 0.0792 mm per shot px)
surf = json.load(open(G + "surf.json"))
prof = json.load(open(G + "prof.json"))
names = {"photo": "REFERENCE: Tess, front picture"}


def nums(tag):
    out = []
    if tag in surf:
        mid = [surf[tag]["cols"][k] for k in ("-3", "0", "3") if k in surf[tag]["cols"]]
        m = lambda k: float(np.mean([q.get(k, np.nan) for q in mid]))  # noqa: E731
        out.append(f"mesh: fold {m('crease_h'):.1f} mm over the margin, turn at the fold {m('tuck'):.0f} deg, fold wall {m('wall'):.0f} deg, drape {m('drape'):.1f} mm")
    return out


def lumline(tag, kind="s"):
    import prof as _p  # noqa: F401  (not importable as a module without side effects: recompute here)
    return ""


def feat(p, Hh):
    from scipy.ndimage import gaussian_filter1d
    st = Hh[1] - Hh[0]
    sm = gaussian_filter1d(p, 0.15 / st)
    wide = gaussian_filter1d(p, 1.5 / st)
    sel = (Hh >= 2.5) & (Hh <= 8.0)
    d = wide - sm
    i = int(np.flatnonzero(sel)[np.argmax(d[sel])])
    h = float(Hh[i])
    dr = (Hh >= h + 1.0) & (Hh <= h + 3.5)
    return h, float(d[i]), float(sm[dr].mean())


def lum(tag, kind):
    if tag not in prof or kind not in prof[tag]:
        return None
    p = np.array(prof[tag][kind]).mean(0)
    Hh = np.arange(p.shape[1]) * 0.05
    f = np.array([feat(x, Hh) for x in p]).mean(0)
    ph = np.array(prof["photo"]["s"]).mean(0)
    sel = (Hh >= 1) & (Hh <= 12)
    rms = float(np.sqrt(((p - ph)[:, sel] ** 2).mean()))
    return f, rms


def tile(S, d, x, y, file, title, lines):
    im = Image.open(G + file + ".png").convert("RGB").crop(C).resize((W, H), Image.LANCZOS)
    S.paste(im, (x, y + HEAD))
    d.text((x + 10, y + 4), title, fill=(0, 0, 0), font_size=28)
    for i, t in enumerate(lines[:2]):
        d.text((x + 10, y + 40 + i * 25), t, fill=(0, 0, 0), font_size=19)
    bx, by = x + 16, y + HEAD + H - 22
    d.line([(bx, by), (bx + 10 / MMPX, by)], fill=(255, 255, 255), width=6)
    d.line([(bx, by), (bx + 10 / MMPX, by)], fill=(0, 0, 0), width=2)
    d.text((bx + 10 / MMPX + 6, by - 12), "10 mm", fill=(0, 0, 0), font_size=18)


best, before, donor = sys.argv[1:4]
var = sys.argv[4] if len(sys.argv) > 4 else None
lab = {best: f"BEST: {surf[best]['model']} (whole-lid solve)", before: f"BEFORE: {surf[before]['model'] if before in surf else before} (eye ruler result)", donor: "GNM sample #376 ('reads right' to Joe)"}
notes = open(G + "sheet1_notes.txt").read().splitlines() if os.path.exists(G + "sheet1_notes.txt") else []
TAB = 30 + 26 * len(notes)
S = Image.new("RGB", (4 * W, 2 * (H + HEAD) + TAB), "white")
d = ImageDraw.Draw(S)
f, _ = lum("photo", "s")
tile(S, d, 0, 0, "s_photo", names["photo"], [f"picture: fold line {f[0]:.1f} mm over the margin, line contrast {f[1]:.2f}, skin above the fold at {f[2]:.2f} of the lit skin", "(luminance up 5 columns from the lash line; same read on every tile)"])
tile(S, d, 0, H + HEAD, "s_photo", "REFERENCE (again, beside the clay)", ["clay tiles: the stage's mesh, one hard light 39 deg above the front + weak fill", "a fold casts an edge; a soft valley only shades"])
for i, tag in enumerate((best, before, donor)):
    x = (i + 1) * W
    f, rms = lum(tag, "s")
    tile(S, d, x, 0, "s_" + tag, lab[tag] + ", dressed", nums(tag) + [f"dressed: line contrast {f[1]:.2f} at {f[0]:.1f} mm, skin above the fold {f[2]:.2f}; whole profile vs the picture rms {rms:.3f}"])
    fk = lum(tag, "k")
    tile(S, d, x, H + HEAD, "k_" + tag, lab[tag].split(":")[0].split(" (")[0] + ", clay, hard light", [f"clay: shadow edge contrast {fk[0][1]:.2f} at {fk[0][0]:.1f} mm, skin above the fold {fk[0][2]:.2f}"] if fk else [])
y = 2 * (H + HEAD) + 12
for k, t in enumerate(notes):
    d.text((14, y + k * 26), t, fill=(0, 0, 0), font_size=20)
S.save(OUT + "el_01_upper_lid_whole_structure.png")
print(OUT + "el_01_upper_lid_whole_structure.png", S.size)

if var:
    notes = open(G + "sheet4_notes.txt").read().splitlines() if os.path.exists(G + "sheet4_notes.txt") else []
    TAB = 30 + 26 * len(notes)
    OW = W
    S = Image.new("RGB", (4 * W, (OW + HEAD) + (H + HEAD) + TAB), "white")
    d = ImageDraw.Draw(S)
    bm, vm = surf[before]["model"] if before in surf else "er_s4", surf[var]["model"]
    for i, (m, v, t) in enumerate(((bm, 2, f"BEFORE {bm} on her PROFILE picture"), (vm, 2, f"VARIANT {vm} (eye unit forward) on her profile"),
                                   (bm, 1, f"BEFORE {bm} on her 3/4 picture"), (vm, 1, f"VARIANT {vm} on her 3/4 picture"))):
        p = f"{G}orbit_{m}_{v}.png"
        if os.path.exists(p):
            S.paste(Image.open(p).convert("RGB").resize((OW, OW), Image.LANCZOS), (i * W, HEAD))
        d.text((i * W + 10, 4), t, fill=(0, 0, 0), font_size=26)
        d.text((i * W + 10, 38), "yellow: the model's eyeball and corneal apex; cyan: its lid section at the pupil;", fill=(0, 0, 0), font_size=18)
        d.text((i * W + 10, 60), "green: its mid-line profile; red: nasion; magenta: brow landmarks", fill=(0, 0, 0), font_size=18)
    y0 = OW + HEAD
    f, _ = lum("photo", "s")
    tile(S, d, 0, y0, "s_photo", names["photo"], [f"skin above the fold at {f[2]:.2f} of the lit skin (no hollow under the brow)"])
    for i, (tg, pre, t) in enumerate(((var, "s_", f"VARIANT {vm}, dressed"), (best, "s_", f"BEST {surf[best]['model']} (orbit as it was), dressed"), (var, "k_", f"VARIANT {vm}, clay"))):
        ff = lum(tg, pre[0])
        tile(S, d, (i + 1) * W, y0, pre + tg, t, nums(tg)[:1] + ([f"line contrast {ff[0][1]:.2f}, skin above the fold {ff[0][2]:.2f}" + (f", profile vs picture rms {ff[1]:.3f}" if pre == 's_' else "")] if ff else []))
    y = y0 + H + HEAD + 12
    for k, t in enumerate(notes):
        d.text((14, y + k * 26), t, fill=(0, 0, 0), font_size=20)
    S.save(OUT + "el_04_orbit_eye_depth.png")
    print(OUT + "el_04_orbit_eye_depth.png", S.size)
