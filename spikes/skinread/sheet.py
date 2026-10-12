"""sheet.py <out png> <before model> <after model> <title> [projected dir]: the skinread sheet.
One row per reference view: REFERENCE | AFTER (own dressing) | BEFORE (own dressing) | the references projected as skin
(the judging sheets' cached shot, if there). Then close-up rows of the front view: EYES and MOUTH (reference | after |
before), and one row of UNSEEN angles under another light (after, after | before, before). Labels in large type.
Shots are cached in $G/out/sh_<model>_<key>.png (delete to re-render)."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import stage as g3stage
from hifipushie import skin_read as sr, blockin as bi, humanfit, likeness as lk, resources, skin_look, store

out, before, after, title = sys.argv[1:5]
pdirs = sys.argv[5:] or ["/mnt/data/hifipushie/reruns/out", "/mnt/data/hifipushie/refread/out"]
G = os.environ["G"] + "/out"
T = 640
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
SMALL = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
LIGHT = {**g3stage.FRONT_LIGHT}


def shots(m, jobs):
    """jobs: {key: (frame, lighting)} -> {key: RGB image T x T}, cached."""
    res, todo = {}, {}
    for k, (fr, lt) in jobs.items():
        f = f"{G}/sh_{m}_{k}.png"
        if os.path.exists(f):
            res[k] = Image.open(f).convert("RGB")
        else:
            todo[k] = (fr, lt, f)
    if todo:
        with resources.heavy(f"skinread sheet {m}", gb=6):
            sn = sr.stage(m, log=lambda s: None)
            for k, (fr, lt, f) in todo.items():
                a = sr.shoot(sn, [{**fr, "name": "v"}], lt, size=2 * T, samples=32)["v"]
                im = Image.fromarray(a)
                bg = Image.new("RGBA", im.size, (205, 205, 205, 255))
                im = Image.alpha_composite(bg, im).convert("RGB").resize((T, T), Image.LANCZOS)
                im.save(f)
                res[k] = im
    return res


def label(im, text, font=FONT):
    im = im.copy()
    d = ImageDraw.Draw(im)
    w = d.textlength(text, font=font)
    d.rectangle([0, 0, w + 24, font.size + 18], fill=(255, 255, 255))
    d.text((12, 6), text, fill=(0, 0, 0), font=font)
    return im


rj = bi._refs(before)
boxes = sr.boxes(before)
front = bi._front(rj)
L = humanfit.state(store.load(before)["base"])["L"]
jobs = {}
for vi, (cam, box) in enumerate(zip(rj["cameras"], boxes)):
    jobs[f"v{vi}"] = (sr.fitted_frame(cam, box, "v"), bi.photo_lighting(before, LIGHT, vi))
# close-ups of the front view: eyes (both, brows to under the bags) and mouth (nose base to chin)
cam = rj["cameras"][front]
P = humanfit.project(cam, L)
def sq(cx, cy, side):
    return [cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2]
eye_w = float(np.linalg.norm(P[45] - P[36]))
crops = {"eyeR": sq(*(P[36:42].mean(0) + [0, 0.05 * eye_w]), 0.62 * eye_w), "eyeL": sq(*(P[42:48].mean(0) + [0, 0.05 * eye_w]), 0.62 * eye_w),
         "mouth": sq(*(0.5 * (P[33] + P[8]) - [0, 0.12 * eye_w]), 1.0 * eye_w)}
for k, cb in crops.items():
    jobs[k] = (sr.fitted_frame(cam, cb, "v"), bi.photo_lighting(before, LIGHT, front))
# unseen angles under another light
spec = store.load(before)
for fr in g3stage.view_frames(spec, ("three_quarter_other", "profile_right", "low_angle")):
    jobs["u_" + fr["name"]] = (fr, skin_look.STUDIO)
A, B = shots(after, jobs), shots(before, jobs)

rows = []
for vi, (v, box) in enumerate(zip(rj["views"], boxes)):
    ph = Image.open(v["image"]).convert("RGB").crop(tuple(int(round(x)) for x in box)).resize((T, T), Image.LANCZOS)
    pj = None
    for d in pdirs:
        for nm in (before, "gr_G05" if before == "garrett_a1" else before, "tk_T07" if before == "tess_a1" else before):
            f = f"{d}/j_{nm}_{vi}.png"
            if pj is None and os.path.exists(f):
                pj = Image.open(f).convert("RGB").resize((T, T), Image.LANCZOS)
    tiles = [label(ph, "REFERENCE"), label(A[f"v{vi}"], "AFTER (own skin)"), label(B[f"v{vi}"], "BEFORE (own skin)")]
    tiles.append(label(pj, "references projected") if pj is not None else Image.new("RGB", (T, T), (235, 235, 235)))
    rows.append(tiles)
img = Image.open(rj["views"][front]["image"]).convert("RGB")
for k, name in (("eyeR", "EYE (their right)"), ("eyeL", "EYE (their left)"), ("mouth", "MOUTH")):
    cb = crops[k]
    ph = img.crop(tuple(int(round(x)) for x in cb)).resize((T, T), Image.LANCZOS)
    rows.append([label(ph, f"REFERENCE: {name}", SMALL), label(A[k], "AFTER", SMALL), label(B[k], "BEFORE", SMALL), Image.new("RGB", (T, T), (235, 235, 235))])
rows.append([label(A["u_three_quarter_other"], "UNSEEN, other light: AFTER", SMALL), label(A["u_profile_right"], "AFTER", SMALL),
             label(B["u_three_quarter_other"], "BEFORE", SMALL), label(B["u_profile_right"], "BEFORE", SMALL)])
rows.append([label(A["u_low_angle"], "UNSEEN, low angle: AFTER", SMALL), label(B["u_low_angle"], "BEFORE", SMALL),
             Image.new("RGB", (T, T), (235, 235, 235)), Image.new("RGB", (T, T), (235, 235, 235))])
HEAD = 70
W = Image.new("RGB", (4 * T, HEAD + T * len(rows)), "white")
ImageDraw.Draw(W).text((14, 12), title, fill=(0, 0, 0), font=FONT)
for r, row in enumerate(rows):
    for c, t in enumerate(row):
        W.paste(t, (c * T, HEAD + r * T))
W.save(out)
print(out, W.size)
