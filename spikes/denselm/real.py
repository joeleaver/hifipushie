"""real.py <tag> [subjects..]: the detector on the REAL pictures we have (sim-to-real, judged by eye): per picture and
feature (eyes, nose, mouth, chin_jaw) one SMALL tile: ours | MediaPipe, in /mnt/data/hifipushie/denselm/out/real_<tag>/;
per subject one simple sheet for Joe (whole face: ours | MediaPipe) in workspace/human_renders/dl_<tag>_<subject>.png;
and, where a fitted model + camera exists, the distance of both detectors' 68 standard points from the model's own
(NOT a truth: the model was solved with MediaPipe's points and outlines; it says which detector the solve agreed with).
Needs HIFIPUSHIE_DENSELM = the trained model.pt; main's workspace (WS=main)."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from hifipushie import blockin as bi, denselm, face_ruler as fr, likeness, store

T = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/"
G = "/home/joe/dev/s0urc3/docs/img/garrett_ref_full/"
SUBJECTS = {
    "tess": [("front", "tess_a1", 0, None), ("3q", "tess_a1", 1, None), ("profile", "tess_a1", 2, None),
             ("smile", None, None, T + "tess_head_front_smile.png")],
    "garrett_paintings": [("front", "garrett_a1", 0, None), ("desk", "garrett_a1", 1, None)],
    "garrett_good": [("front", "gc_C06", 0, None), ("3q", "gc_C06", 1, None), ("profile", "gc_C06", 2, None),
                     ("smile_teeth", None, None, G + "garrett_head_front_smile_teeth.png"),
                     ("jaw_open", None, None, G + "garrett_head_front_jaw_open.png"),
                     ("eyes_closed", None, None, G + "garrett_head_front_eyes_closed.png"),
                     ("true45", None, None, G + "garrett_head_three_quarter_left_true45.png")],
}
# feature -> (the standard landmarks its crop is laid on, pad): TIGHT crops, one feature a tile
FEATS = {"eye": (list(range(42, 48)) + [22, 26], 1.7), "eyes": (list(range(36, 48)), 1.25), "nose": (list(range(27, 36)), 1.7),
         "mouth": (list(range(48, 68)), 1.5), "chin_jaw": (list(range(5, 12)) + [57], 1.2)}
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
SMALL = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)


def col(sig_mm):
    return (40, 230, 60) if sig_mm < 1.0 else (250, 220, 30) if sig_mm < 2.0 else (255, 60, 50)


def panel(img, box, pts, cols, px=520, r=2.0, big=None):
    """big: the 68 standard points among pts (indices): drawn as rings, so the two detectors' SAME points can be compared."""
    x0, y0, x1, y1 = box
    k = px / (x1 - x0)
    im = img.crop((int(x0), int(y0), int(x1), int(y1))).resize((px, px), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    for p, c in zip(pts, cols):
        x, y = (p[0] - int(x0)) * k, (p[1] - int(y0)) * k
        if -5 < x < px + 5 and -5 < y < px + 5:
            d.ellipse((x - r, y - r, x + r, y + r), fill=c, outline=(0, 0, 0))
    for i in (big if big is not None else ()):
        x, y = (pts[i][0] - int(x0)) * k, (pts[i][1] - int(y0)) * k
        if -5 < x < px + 5 and -5 < y < px + 5:
            d.ellipse((x - 5, y - 5, x + 5, y + 5), outline=(255, 255, 255), width=2)
    return im


def square(P, pad):
    lo, hi = P.min(0), P.max(0)
    c, s = (lo + hi) / 2, (hi - lo).max() * pad
    return c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2


def titled(tiles, labels, title):
    w, h = sum(t.size[0] for t in tiles) + 8 * (len(tiles) - 1), tiles[0].size[1]
    S = Image.new("RGB", (w, h + 76), (20, 20, 20))
    d = ImageDraw.Draw(S)
    d.text((8, 4), title, fill=(255, 255, 255), font=FONT)
    x = 0
    for t, lb in zip(tiles, labels):
        S.paste(t, (x, 76))
        d.text((x + 8, 44), lb, fill=(230, 230, 230), font=SMALL)
        x += t.size[0] + 8
    return S


def main():
    tag = sys.argv[1]
    subs = sys.argv[2:] or list(SUBJECTS)
    out = Path(f"/mnt/data/hifipushie/denselm/out/real_{tag}")
    out.mkdir(parents=True, exist_ok=True)
    L = denselm.landmarks()
    reg = L["region"]
    for sub in subs:
        rows = []
        for vname, model, vi, path in SUBJECTS[sub]:
            cam = head = None
            if model:
                rj = bi._refs(model)
                v, cam = rj["views"][vi], rj["cameras"][vi]
                img = Image.open(v["image"]).convert("RGB")
                pts = {k: p for k, p in (v.get("points") or {}).items()}
                head = fr.model_head(store.load(model))
                _, q68 = fr._cam_points(cam, np.asarray(head["L"], float)[:68])
                box0 = likeness._box({str(i): p for i, p in enumerate(q68)}, img.size)
                mp = likeness.detect_region(img, box0)
                init = q68
            else:
                img = Image.open(path).convert("RGB")
                mp = likeness.detect([img])[0]
                if mp is None:
                    w, h = img.size
                    mp = likeness.detect_region(img, (w * 0.15, h * 0.1, w * 0.85, h * 0.75))
                init = None if mp is None else np.asarray(mp, float)[likeness.MP68]
            if init is None:
                print(f"{sub} {vname}: no face box (MediaPipe found none and no model): skipped")
                continue
            pr = denselm.predict(img, init)
            xy, sg = pr["xy"], pr["sigma"]
            o68 = xy[L["lm68"]]
            ext = float(np.ptp(o68[:, 1]))
            mmpx = 120.0 / max(ext, 1.0) if cam is None else likeness._mm_per_px(cam, np.asarray(head["L"], float)[27:48])
            # (no camera: ~120 mm brow-to-chin over the 68's height: a rough scale for the sigma colours only)
            sgmm = sg * mmpx
            line = f"{sub} {vname}: face {ext:.0f} px ({mmpx:.2f} mm/px); our sigma (mm) median by region: " + ", ".join(
                f"{r} {np.median(sgmm[reg == r]):.2f}" for r in ("lids", "eyes", "nose", "lips", "mouth", "chin", "cheeks", "forehead", "ears", "eyeball"))
            if mp is not None:
                m68 = np.asarray(mp, float)[likeness.MP68]
                d = np.linalg.norm(o68 - m68, axis=1) * mmpx
                line += f"\n    ours vs MediaPipe on the 68: median {np.median(d):.2f} mm, chin (7-9) {d[7:10].mean():.2f}, jaw (0-16) {d[:17].mean():.2f}, inner (17-67) {d[17:].mean():.2f}"
                if cam is not None:
                    do, dm = np.linalg.norm(o68 - q68, axis=1) * mmpx, np.linalg.norm(m68 - q68, axis=1) * mmpx
                    line += (f"\n    against the FITTED MODEL's 68 (not a truth): ours median {np.median(do):.2f} mm (inner {np.median(do[17:]):.2f}, jaw {np.median(do[:17]):.2f}); "
                             f"MediaPipe {np.median(dm):.2f} (inner {np.median(dm[17:]):.2f}, jaw {np.median(dm[:17]):.2f})")
                    hv = head.get("dense_v")
                    if hv is None:
                        fr._dense_obs(head, {"cam": cam, "kind": "front"}, {"xy": xy, "sigma": sg})
                        hv = head["dense_v"]
                    _, Q = fr._cam_points(cam, head["V"][hv])
                    dd = np.linalg.norm(xy[:len(hv)] - Q, axis=1) * mmpx
                    sure = sgmm[:len(hv)] < 2.0
                    line += "\n    dense, ours vs the fitted model (sure landmarks, median mm): " + ", ".join(
                        f"{r} {np.median(dd[(reg[:len(hv)] == r) & sure]):.2f}" for r in ("lids", "eyes", "nose", "lips", "mouth", "chin", "cheeks", "forehead")
                        if ((reg[:len(hv)] == r) & sure).any())
            print(line, flush=True)
            cols = [col(s) for s in sgmm]
            for f, (ids, pad) in FEATS.items():
                bx = square(o68[ids], pad)
                a = panel(img, bx, xy, cols, big=L["lm68"])
                b = panel(img, bx, [] if mp is None else mp, [(60, 220, 255)] * 478, big=None if mp is None else likeness.MP68)
                c = panel(img, bx, [], [])
                titled([c, a, b], ["the picture", "ours (green < 1 mm sigma, yellow < 2, red unsure; rings = the 68)", "MediaPipe (478; rings = its 68)"],
                       f"{sub} {vname}: {f}").save(out / f"{sub}_{vname}_{f}.png")
            bx = square(o68, 1.55)
            rows.append((vname, panel(img, bx, xy, cols, 640, 2.2), panel(img, bx, [] if mp is None else mp, [(60, 220, 255)] * 478, 640, 2.2)))
        for part, k0 in enumerate(range(0, len(rows), 3)):       # at most three views a sheet: ours | MediaPipe, large labels
            rs = rows[k0:k0 + 3]
            S = Image.new("RGB", (2 * 640 + 8, len(rs) * (640 + 50) + 60), (20, 20, 20))
            d = ImageDraw.Draw(S)
            d.text((8, 10), f"{sub}: OUR dense landmarks (green = sure, red = unsure)  |  MediaPipe", fill=(255, 255, 255), font=FONT)
            for i, (vn, a, b) in enumerate(rs):
                y = 60 + i * 690
                d.text((8, y + 8), vn, fill=(255, 255, 255), font=FONT)
                S.paste(a, (0, y + 50))
                S.paste(b, (648, y + 50))
            p = Path(f"/home/joe/dev/hifipushie/workspace/human_renders/dl_{tag}_{sub}{'_' + str(part + 1) if len(rows) > 3 else ''}.png")
            S.save(p)
            print("sheet", p)

main()
