"""sheet.py: ob_01 (the orbit on her side pictures: reference | best | before | other; rows = profile, 3/4; the
overlays are spikes/eyelid/orbit.py's: green = the model's mid-sagittal profile, yellow = the near eyeball + corneal
apex, cyan = the lid's section at the pupil, red = nasion) and ob_02 (dressed front through the fitted camera:
reference | best | before | others). Also prints the eye ruler's rows for the models (mesh vs picture)."""
import os

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import blockin as bi, eye_ruler as er, humanfit, likeness, store

G = os.environ["G"] + "/out"
R = os.environ["R"]
BEST, BEFORE, OTHER = "ob_T1e", "er_s4", "ob_T3"
T = 760


def label(im, txt):
    im = im.convert("RGB").resize((T, T), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, T, 58], fill=(0, 0, 0))
    for i, line in enumerate(txt.split("\n")):
        d.text((8, 4 + 26 * i), line, fill=(255, 255, 255), font_size=21)
    return im


def ref_crop(name, vi):
    rj = bi._refs(name)
    v, cam = rj["views"][vi], rj["cameras"][vi]
    st = humanfit.state(store.load(name)["base"])
    ht = st["head"]
    Rm = humanfit._cam_rot(cam)
    eye_c = np.asarray(cam["centre"], float) - Rm.T @ np.asarray(cam["t"], float)
    c = min([np.asarray(e, float) for e in ht["eyes"]], key=lambda e: np.linalg.norm(e - eye_c))
    apex = c + float(ht["eye_r"]) * np.asarray(ht["forward"], float)
    mm = likeness._mm_per_px(cam, st["L"][27:48])
    pa = humanfit.project(cam, apex[None])[0]
    half = 30.0 / mm
    return Image.open(v["image"]).convert("RGB").crop(tuple(int(round(x)) for x in (pa[0] - half, pa[1] - half, pa[0] + half, pa[1] + half)))


def apex(name):
    st = humanfit.state(store.load(name)["base"])
    ht = st["head"]
    f = np.asarray(ht["forward"], float)
    c = np.asarray(ht["eyes"][0], float)
    return float((st["L"][27] - (c + float(ht["eye_r"]) * f)) @ f) * 1000


ap = {m: apex(m) for m in (BEST, BEFORE, OTHER)}
rows = []
for vi, kind in ((2, "PROFILE"), (1, "3/4")):
    tiles = [label(ref_crop(BEFORE, vi), f"REFERENCE {kind} (60 mm square at the eye)\nher picture, nothing drawn")]
    for m, lab in ((BEST, f"BEST {BEST}: eye unit +1.7 mm (joint read), profile\ncamera turned -4.6 deg, eye step; apex {ap[BEST]:.1f} mm behind nasion"),
                   (BEFORE, f"BEFORE {BEFORE} (fitted cameras as they were)\napex {ap[BEFORE]:.1f} mm behind nasion"),
                   (OTHER, f"OTHER {OTHER}: eye unit +3.7 mm (profile camera\ntrusted, yaw held); apex {ap[OTHER]:.1f} mm behind nasion")):
        tiles.append(label(Image.open(f"{G}/orbit_{m}_{vi}.png"), lab))
    rows.append(tiles)
W = Image.new("RGB", (4 * T, 2 * T), "white")
for j, tiles in enumerate(rows):
    for i, t in enumerate(tiles):
        W.paste(t, (i * T, j * T))
W.save(f"{R}/ob_01_orbit_side_views.png")
T = 900
tiles = [label(Image.open(f"{G}/s_photo.png"), "REFERENCE: her front picture\n(the crop every render is framed to)"),
         label(Image.open(f"{G}/s_T1e.png"), "BEST ob_T1e: orbit +1.7 mm, then the eye step\n(identity only; lid as one structure; ball guard)"),
         label(Image.open(f"{G}/s_s4.png"), "BEFORE er_s4 (eyeruler's solve: margins on the\nruler, no lid solve, orbit never set)"),
         label(Image.open(f"{G}/s_a6.png"), "OTHER el_a6 (eyelid agent: lidsolve.py on er_s4,\nno orbit move)"),
         label(Image.open(f"{G}/s_T1.png"), "OTHER ob_T1 (orbit +1.7 mm only, no eye step)")]
W = Image.new("RGB", (3 * T, 2 * T), "white")
for i, t in enumerate(tiles):
    W.paste(t, ((i % 3) * T, (i // 3) * T))
W.save(f"{R}/ob_02_dressed_front.png")
print("saved ob_01_orbit_side_views.png, ob_02_dressed_front.png")
for m in (BEFORE, "el_a6", BEST):
    c = er.compare(m)
    keep = [r for r in c["rows"] if any(k in r["measure"] for k in ("fissure", "inner canthus u", "outer canthus u", "upper margin at u +0", "upper margin at u -3", "upper margin at u +3", "lower margin at u +0", "iris hidden", "pupils", "tilt"))]
    print(m, "| " + "; ".join(f"{r['measure']}: model {r['model']:.2f} vs picture {r['photo']:.2f}{' *' if r['off'] else ''}" for r in keep))
