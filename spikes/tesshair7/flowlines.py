"""flowlines.py <out.png> <model> [<model2> ...] [view=1] [size=1024] [tiles=<dir>,<dir>]: Joe's markup redone by
measure: the STRAND PATHS FROM THE PARTING drawn on her picture and on ours, the same way on both.

For each picture (hers; then each model's tile s_<model>_v<view>.png through the same fitted camera): the hair's
direction field is read off the image (structure tensor of the lightness, 2.5 mm window: strands are the streaks),
and stream lines are traced through it from the SAME seeds: points 8 mm off each bank of the model's parting, every
1.2 cm along it (the model's scalp projected through the reference's camera: so the seeds sit on the same place of
the head in every panel). A line starts out AWAY from the part and runs 11 cm or until it leaves the hair. RED.
On our panels the model's own lock spines rooted on the part are drawn too, thin CYAN: the truth the red lines
should follow. No Blender."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

import stage
from hifipushie import hair, hair_cards as hc, store

out = sys.argv[1]
names = [a for a in sys.argv[2:] if "=" not in a]
kw = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
vi, N = int(kw.get("view", 1)), int(kw.get("size", 1024))
dirs_ = kw.get("tiles", os.environ["TOUT"] + ",/mnt/data/hifipushie/tesshair6/out").split(",")
W, H = 1152, 1536
BOX = [-(H - W) / 2, 0, W + (H - W) / 2, H]
m0 = names[0]
spec = store.load(m0)
sc = hair.scalp(m0, spec)
refs = json.loads((store.HOME / m0 / "human_refs.json").read_text())
cam = refs["cameras"][vi]
fm = stage.fitted_frame(cam, BOX, f"v{vi}")
mm = float(hair._project_frame(fm, sc.C[None], N)[1][0]) / float(cam["f"]) * 1000.0 * max(cam["size"]) / N
try:
    F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", N // 22)
except OSError:
    F = ImageFont.load_default()


def hairmask(im, bg_tol=26):
    a = np.asarray(im.convert("RGB"), float)
    bg = np.median(a[:40, :40].reshape(-1, 3), 0)
    lum = a @ [0.2126, 0.7152, 0.0722]
    return ndi.binary_closing((np.abs(a - bg).max(-1) > bg_tol) & (lum < 0.55 * (bg @ [0.2126, 0.7152, 0.0722])), iterations=2)


# the seeds: off both banks of the (centre) parting, on the scalp, lifted 1 cm (the hair's surface, not the skin)
g = hair.groom_params(spec)
xp = hair._part_x(g) or 0.0
y0 = -float(sc.r(0.0, 30.0)) * np.cos(np.radians(30.0))
seeds, away = [], []
for sd in (-1.0, 1.0):
    for dy in np.arange(0.012, 0.085, 0.012):
        a_, e_ = hair.top_to_azel(sc, np.array([[xp + sd * 0.008, y0 + dy]]))
        p = sc.point(a_, e_, 0.008)[0]
        q = sc.point(*hair.top_to_azel(sc, np.array([[xp + sd * 0.03, y0 + dy]])), 0.008)[0]
        seeds.append(p)
        away.append(q)
S2, zs = hair._project_frame(fm, np.asarray(seeds), N)
A2, _ = hair._project_frame(fm, np.asarray(away), N)
front = (np.asarray(seeds) - sc.C) @ (np.asarray(fm["eye"], float) - sc.C) > 0  # (banks the camera sees)


def field(im):
    L = np.asarray(im.convert("L"), float)
    L = ndi.gaussian_filter(L, 0.8)
    gx, gy = ndi.sobel(L, 1), ndi.sobel(L, 0)
    sg = 2.5 / mm
    jxx, jyy, jxy = (ndi.gaussian_filter(v, sg) for v in (gx * gx, gy * gy, gx * gy))
    th = 0.5 * np.arctan2(2 * jxy, jxx - jyy) + np.pi / 2  # along the streaks
    coh = np.hypot(jxx - jyy, 2 * jxy) / np.maximum(jxx + jyy, 1e-6)
    return np.cos(th), np.sin(th), coh


def trace(im, mk):
    tx, ty, coh = field(im)
    lines = []
    for s, a, ok in zip(S2, A2, front):
        if not ok:
            continue
        p = np.array(s, float)
        d = (a - s) / max(np.linalg.norm(a - s), 1e-6)
        pts = [p.copy()]
        for _ in range(int(110 / mm / 2)):
            x, y = int(round(p[0])), int(round(p[1]))
            if not (0 <= x < N and 0 <= y < N) or not mk[y, x]:
                break
            t = np.array([tx[y, x], ty[y, x]])
            if t @ d < 0:
                t = -t
            w = float(np.clip(coh[y, x] * 2.0, 0.15, 0.8))  # (where the image has no streaks the line keeps its heading)
            d = (1 - w) * d + w * t
            d = d / max(np.linalg.norm(d), 1e-6)
            p = p + 2.0 * d
            pts.append(p.copy())
        if len(pts) > 6:
            lines.append(np.asarray(pts))
    return lines


def panel(im, label, lines, truth=None):
    im = im.convert("RGB").copy()
    dr = ImageDraw.Draw(im)
    for t in truth or []:
        dr.line([tuple(q) for q in t], fill=(0, 230, 255), width=max(1, N // 500))
    for ln in lines:
        dr.line([tuple(q) for q in ln], fill=(255, 0, 0), width=max(3, N // 220))
    im.info["label"] = label
    return im


def bend(lines):
    """How far a line bows off its own chord, mm (median over lines) and which way it leaves: deg below horizontal."""
    b, a0 = [], []
    for ln in lines:
        ch = ln[-1] - ln[0]
        n_ = np.array([-ch[1], ch[0]]) / max(np.linalg.norm(ch), 1e-6)
        b.append(np.abs((ln - ln[0]) @ n_).max() * mm)
        d0 = ln[min(8, len(ln) - 1)] - ln[0]
        a0.append(np.degrees(np.arctan2(d0[1], abs(d0[0]))))
    return (round(float(np.median(b)), 1), round(float(np.median(a0)), 0), round(float(np.median([len(l) * 2 * mm for l in lines])), 0)) if b else (0, 0, 0)


pic = hair.ref_square(Image.open(refs["views"][vi]["image"]).convert("RGB"), N)
lh = trace(pic, hairmask(pic))
panels = [panel(pic, "HERS", lh)]
print(f"view v{vi}  {mm:.2f} mm/px   bow off the chord mm | first heading deg below horizontal | length mm")
print("  hers", bend(lh))
for m in names:
    f = next((f"{d}/s_{m}_v{vi}.png" for d in dirs_ if os.path.exists(f"{d}/s_{m}_v{vi}.png")), None)
    if f is None:
        continue
    im = Image.open(f).convert("RGB").resize((N, N), Image.LANCZOS)
    sp = store.load(m)
    truth = []
    for n_, lk in sp["hair"]["locks"].items():
        if lk.get("space") == "xyz" or lk.get("hairs") or not n_.startswith("tg1_"):
            continue
        P = hair.lock_world(sc, lk, lk["pts"])
        if abs(P[0][0] - sc.C[0] - xp) > 0.012 or (P[0] - sc.C)[1] > y0 + 0.09 or (P[0] - sc.C)[2] < 0.04:
            continue
        P = hc.spine({**lk, "pts": P.tolist()}, 60)[0]
        if (P[0] - sc.C) @ (np.asarray(fm["eye"], float) - sc.C) <= 0:
            continue
        # (only the stretch the camera sees: up to where the lock passes behind the head)
        vis = (P - sc.C) @ (np.asarray(fm["eye"], float) - sc.C) > 0.02 * np.linalg.norm(np.asarray(fm["eye"], float) - sc.C)
        k_ = int(np.argmin(vis)) if not vis.all() else len(P)
        if k_ > 4:
            truth.append(hair._project_frame(fm, P[:k_], N)[0])
    lo = trace(im, hairmask(im))
    print(f"  {m}", bend(lo))
    panels.append(panel(im, m.replace("th_", "") + (" (NEW)" if m == names[0] else ""), lo, truth))
cr = [float(x) for x in kw.get("crop", "0.2,0.02,0.85,0.67").split(",")]
labels = [p.info.get("label", "") for p in panels]
panels = [p.crop((int(cr[0] * N), int(cr[1] * N), int(cr[2] * N), int(cr[3] * N))) for p in panels]
for p, lb in zip(panels, labels):
    ImageDraw.Draw(p).text((14, 10), lb, fill="black", font=F, stroke_width=4, stroke_fill="white")
sheet = Image.new("RGB", (sum(p.width for p in panels), panels[0].height), "white")
x = 0
for p in panels:
    sheet.paste(p, (x, 0))
    x += p.width
sheet.save(out)
print("saved", out)
