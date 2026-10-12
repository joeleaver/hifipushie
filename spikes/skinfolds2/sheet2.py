"""sheet2.py <out png> <a1 model> <jobs.json> <after tag> <before tag> <title>: the sg_* sheet from tiles.py's tiles.
Columns: REFERENCE | AFTER (sg_*) | BEFORE (sf_*) | references projected. Rows: one per reference view (fitted camera,
fitted light at the picture's measured exposure, the same for AFTER and BEFORE); eye / eye / mouth close-ups of the
front view under the photo light, then under a raking light; then the front view and three unseen angles under a
neutral light (AFTER | BEFORE pairs). Under each photo-light render: the face's Lab against the reference's at the
same pixels (the middle of the face)."""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import blockin as bi, skin_read as sr

out, a1, jpath, ta, tb, title = sys.argv[1:7]
G = os.environ["G"] + "/out"
PDIRS = ["/mnt/data/hifipushie/reruns/out", "/mnt/data/hifipushie/refread/out"]
T = 560
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
SMALL = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 27)
TINY = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 21)
J = json.load(open(jpath))
rj = bi._refs(a1)
boxes = sr.boxes(a1)
BLANK = Image.new("RGB", (T, T), (235, 235, 235))


def tile(tag, k):
    f = f"{G}/t_{tag}_{k}.png"
    return Image.open(f).convert("RGB") if os.path.exists(f) else BLANK


def label(im, text, font=FONT, foot=None):
    im = im.copy()
    d = ImageDraw.Draw(im)
    w = d.textlength(text, font=font)
    d.rectangle([0, 0, w + 24, font.size + 18], fill=(255, 255, 255))
    d.text((12, 6), text, fill=(0, 0, 0), font=font)
    if foot:
        d.rectangle([0, T - 34, d.textlength(foot, font=TINY) + 16, T], fill=(255, 255, 255))
        d.text((8, T - 30), foot, fill=(0, 0, 0), font=TINY)
    return im


def face_lab(im):
    a = sr._lin(np.asarray(im, float) / 255.0)[int(0.3 * T):int(0.66 * T), int(0.32 * T):int(0.68 * T)].reshape(-1, 3)
    return sr.lab(np.median(a, 0))


def crop(vi, box):
    return Image.open(rj["views"][vi]["image"]).convert("RGB").crop(tuple(int(round(x)) for x in box)).resize((T, T), Image.LANCZOS)


rows = []
nums = []
for vi in range(J["views"]):
    ph = crop(vi, boxes[vi])
    pj = None
    for d in PDIRS:
        for nm in (a1, "gr_G05" if a1 == "garrett_a1" else a1, "tk_T07" if a1 == "tess_a1" else a1):
            f = f"{d}/j_{nm}_{vi}.png"
            if pj is None and os.path.exists(f):
                pj = Image.open(f).convert("RGB").resize((T, T), Image.LANCZOS)
    lr, la, lb = face_lab(ph), face_lab(tile(ta, f"v{vi}")), face_lab(tile(tb, f"v{vi}"))
    nums.append((vi, lr, la, lb))
    ft = lambda l: f"mid-face Lab {l[0]:.0f} {l[1]:.0f} {l[2]:.0f}"  # noqa: E731
    ev = J["ev"][str(vi)] if str(vi) in J["ev"] else J["ev"][vi]
    rows.append([label(ph, "REFERENCE", foot=ft(lr)), label(tile(ta, f"v{vi}"), "AFTER", foot=ft(la) + f"  (light {ev[0]:+.2f} EV)"),
                 label(tile(tb, f"v{vi}"), "BEFORE (sf)", foot=ft(lb)), label(pj, "refs projected") if pj is not None else BLANK])
front = J["front"]
for k, name in (("eyeR", "EYE (their right)"), ("eyeL", "EYE (their left)"), ("mouth", "MOUTH")):
    ph = crop(front, J["crops"][k])
    rows.append([label(ph, f"REFERENCE: {name}", SMALL), label(tile(ta, k), "AFTER, photo light", SMALL), label(tile(tb, k), "BEFORE, photo light", SMALL), BLANK])
    rows.append([label(ph, f"REFERENCE: {name}", SMALL), label(tile(ta, k + "_rk"), "AFTER, RAKING light", SMALL), label(tile(tb, k + "_rk"), "BEFORE, RAKING light", SMALL), BLANK])
rows.append([label(tile(ta, "n_front"), "NEUTRAL light: AFTER", SMALL), label(tile(tb, "n_front"), "NEUTRAL: BEFORE", SMALL),
             label(tile(ta, "n_three_quarter_other"), "UNSEEN, neutral: AFTER", SMALL), label(tile(tb, "n_three_quarter_other"), "UNSEEN: BEFORE", SMALL)])
rows.append([label(tile(ta, "n_profile_right"), "UNSEEN profile: AFTER", SMALL), label(tile(tb, "n_profile_right"), "BEFORE", SMALL),
             label(tile(ta, "n_low_angle"), "UNSEEN low angle: AFTER", SMALL), label(tile(tb, "n_low_angle"), "BEFORE", SMALL)])
HEAD = 70
W = Image.new("RGB", (4 * T, HEAD + T * len(rows)), "white")
ImageDraw.Draw(W).text((14, 14), title, fill=(0, 0, 0), font=SMALL)
for r, row in enumerate(rows):
    for c, t in enumerate(row):
        W.paste(t, (c * T, HEAD + r * T))
W.save(out)
print(out, W.size)
for vi, lr, la, lb in nums:
    print(f"view {vi}: mid-face Lab reference {lr.round(1)}  AFTER {la.round(1)} (d {(la - lr).round(1)})  BEFORE {lb.round(1)} (d {(lb - lr).round(1)})")
