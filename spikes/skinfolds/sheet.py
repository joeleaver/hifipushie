"""sheet.py <out png> <a1 model> <sr model> <sf model> <title> [rake_a1=1]: the skinfolds sheet.
Columns: REFERENCE | AFTER (sf_*) | BEFORE (sr_*: skinread) | BEFORE THAT (the a1 dressing) | references projected.
Rows: one per reference view (its fitted camera, its fitted light); then the front view's close-ups, each under the
PHOTO light and under a RAKING light (low, from the side): eye (their right), eye (their left), mouth; then two unseen
angles under another light. Large labels.
The BEFORE models are shown as they WERE: the photo-light tiles are skinread's own cached shots
(/mnt/data/hifipushie/skinread/out/sh_*), new tiles of them are rendered with the old lips and painted folds.
Shots are cached in $G/out/sh_<model>_<key>.png (delete to re-render)."""
import copy, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import stage as g3stage
import shots as S
from hifipushie import skin_read as sr, blockin as bi, humanfit, resources, skin_look, store

out, a1, srm, sfm, title = sys.argv[1:6]
kw = dict(a.split("=") for a in sys.argv[6:])
G = os.environ["G"] + "/out"
OLD = "/mnt/data/hifipushie/skinread/out"
PDIRS = ["/mnt/data/hifipushie/reruns/out", "/mnt/data/hifipushie/refread/out"]
T = 560
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
SMALL = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
LIGHT = {**g3stage.FRONT_LIGHT}
BLANK = Image.new("RGB", (T, T), (235, 235, 235))


def old_look(spec):
    """A before model as it was dressed before this thread: flat lips with the 1 mm border, folds as painted height."""
    s = copy.deepcopy(spec)
    sk = s.setdefault("skin", {})
    sk["lips"] = {**(sk.get("lips") or {}), "gradient": 0.0, "border": 0.96}
    sk["fold_relief"] = "paint"
    return s


def shots(m, jobs, old=False):
    res, todo = {}, {}
    for k, (fr, lt) in jobs.items():
        f = f"{G}/sh_{m}_{k}.png"
        fo = f"{OLD}/sh_{m}_{k}.png"
        if os.path.exists(f):
            res[k] = Image.open(f).convert("RGB").resize((T, T), Image.LANCZOS)
        elif old and os.path.exists(fo):
            res[k] = Image.open(fo).convert("RGB").resize((T, T), Image.LANCZOS)
        else:
            todo[k] = (fr, lt, f)
    if todo:
        with resources.heavy(f"skinfolds sheet {m}", gb=6):
            spec = store.load(m)
            sn = sr.stage(m, old_look(spec) if old else spec, log=lambda s: None)
            for k, (fr, lt, f) in todo.items():
                a = sr.shoot(sn, [{**fr, "name": "v"}], lt, size=2 * T, samples=32)["v"]
                im = Image.fromarray(a)
                im = Image.alpha_composite(Image.new("RGBA", im.size, (205, 205, 205, 255)), im).convert("RGB").resize((T, T), Image.LANCZOS)
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


rj = bi._refs(a1)
boxes = sr.boxes(a1)
front = bi._front(rj)
L = humanfit.state(store.load(a1)["base"])["L"]
jobs = {}
for vi, (cam, box) in enumerate(zip(rj["cameras"], boxes)):
    jobs[f"v{vi}"] = (sr.fitted_frame(cam, box, "v"), bi.photo_lighting(a1, LIGHT, vi))
cam = rj["cameras"][front]
P = humanfit.project(cam, L)
sq = lambda cx, cy, side: [cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2]  # noqa: E731
eye_w = float(np.linalg.norm(P[45] - P[36]))
crops = {"eyeR": sq(*(P[36:42].mean(0) + [0, 0.05 * eye_w]), 0.62 * eye_w), "eyeL": sq(*(P[42:48].mean(0) + [0, 0.05 * eye_w]), 0.62 * eye_w),
         "mouth": sq(*(0.5 * (P[33] + P[8]) - [0, 0.12 * eye_w]), 1.0 * eye_w)}
rake_jobs = {}
for k, cb in crops.items():
    jobs[k] = (sr.fitted_frame(cam, cb, "v"), bi.photo_lighting(a1, LIGHT, front))
    rake_jobs[k + "_rake"] = (sr.fitted_frame(cam, cb, "v"), S.RAKE)
spec = store.load(a1)
for fr in g3stage.view_frames(spec, ("three_quarter_other", "profile_right", "low_angle")):
    jobs["u_" + fr["name"]] = (fr, skin_look.STUDIO)
A = shots(sfm, {**jobs, **rake_jobs})
B = shots(srm, {**jobs, **rake_jobs}, old=True)
C = shots(a1, {**jobs, **(rake_jobs if kw.get("rake_a1") else {})}, old=True)

rows = []
for vi, (v, box) in enumerate(zip(rj["views"], boxes)):
    ph = Image.open(v["image"]).convert("RGB").crop(tuple(int(round(x)) for x in box)).resize((T, T), Image.LANCZOS)
    pj = None
    for d in PDIRS:
        for nm in (a1, "gr_G05" if a1 == "garrett_a1" else a1, "tk_T07" if a1 == "tess_a1" else a1):
            f = f"{d}/j_{nm}_{vi}.png"
            if pj is None and os.path.exists(f):
                pj = Image.open(f).convert("RGB").resize((T, T), Image.LANCZOS)
    rows.append([label(ph, "REFERENCE"), label(A[f"v{vi}"], "AFTER (skinfolds)"), label(B[f"v{vi}"], "BEFORE (skinread)"),
                 label(C[f"v{vi}"], "BEFORE THAT (a1)"), label(pj, "refs projected") if pj is not None else BLANK])
img = Image.open(rj["views"][front]["image"]).convert("RGB")
for k, name in (("eyeR", "EYE (their right)"), ("eyeL", "EYE (their left)"), ("mouth", "MOUTH")):
    ph = img.crop(tuple(int(round(x)) for x in crops[k])).resize((T, T), Image.LANCZOS)
    rows.append([label(ph, f"REFERENCE: {name}", SMALL), label(A[k], "AFTER, photo light", SMALL), label(B[k], "BEFORE, photo light", SMALL),
                 label(C[k], "BEFORE THAT, photo light", SMALL), BLANK])
    rows.append([label(ph, f"REFERENCE: {name}", SMALL), label(A[k + "_rake"], "AFTER, RAKING light", SMALL), label(B[k + "_rake"], "BEFORE, RAKING light", SMALL),
                 label(C[k + "_rake"], "BEFORE THAT, RAKING", SMALL) if k + "_rake" in C else BLANK, BLANK])
rows.append([label(A["u_three_quarter_other"], "UNSEEN, other light: AFTER", SMALL), label(B["u_three_quarter_other"], "BEFORE", SMALL),
             label(C["u_three_quarter_other"], "BEFORE THAT", SMALL), label(A["u_profile_right"], "UNSEEN profile: AFTER", SMALL), label(B["u_profile_right"], "BEFORE", SMALL)])
rows.append([label(A["u_low_angle"], "UNSEEN, low angle: AFTER", SMALL), label(B["u_low_angle"], "BEFORE", SMALL), label(C["u_low_angle"], "BEFORE THAT", SMALL), BLANK, BLANK])
HEAD = 70
W = Image.new("RGB", (5 * T, HEAD + T * len(rows)), "white")
ImageDraw.Draw(W).text((14, 12), title, fill=(0, 0, 0), font=FONT)
for r, row in enumerate(rows):
    for c, t in enumerate(row):
        W.paste(t, (c * T, HEAD + r * T))
W.save(out)
print(out, W.size)
