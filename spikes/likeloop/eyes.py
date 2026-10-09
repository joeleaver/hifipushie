"""eyes.py <out.png> <label=src>...: the eye region like with like. src = clay:<head model> (likeness clay render
through the photo's camera, ~7 s) | shot:<tag> ($L/out/<tag>_front_big.png from garrett4's shot.py: the dressed head
through the same camera) | clay:<model>@<base.json>. Rows: photo | each source at one eye box (the photo's), then the
photo and the last source at 2x; the likeness_eyes table under them (also <out>.txt / .json)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import sheet1
from hifipushie import likeness, likeness_eyes as le, likeness_pair, store

L = os.environ["L"]
NAME = "ll_garrett"


def photo():
    refs = likeness._refs(NAME)
    ph = likeness.photo_sides(refs)[0]
    return refs, ph


def src_side(src, refs, ph):
    """(image in photo pixels' frame: a PIL image + its box in photo px, P in photo px)."""
    kind, arg = src.split(":", 1)
    if kind == "clay":
        model, _, bf = arg.partition("@")
        base = json.load(open(bf)) if bf else store.load(model)["base"]
        m = likeness_pair.matched(model, base, face_id=False)
        return m["render"], m["box"], m["md"]["side"].P
    crop = sheet1.crop_of(refs["views"][0])
    im = Image.open(f"{L}/out/{arg}_front_big.png").convert("RGB")
    P = likeness.detect([im])[0]
    s = (crop[2] - crop[0]) / im.size[0]
    return im, crop, None if P is None else P * s + [crop[0], crop[1]]


def cut(im, box_img, box, w):
    """box (photo px) out of an image covering box_img (photo px), w px wide."""
    sx = im.size[0] / (box_img[2] - box_img[0])
    b = ((box[0] - box_img[0]) * sx, (box[1] - box_img[1]) * sx, (box[2] - box_img[0]) * sx, (box[3] - box_img[1]) * sx)
    h = int(round(w * (box[3] - box[1]) / (box[2] - box[0])))
    return im.transform((w, h), Image.EXTENT, b, Image.BICUBIC)


def main(out, srcs):
    refs, ph = photo()
    box = le.eye_box(ph["side"].P)
    rows = {"photo": le.measures(ph["side"].P, ph["mmpx"])}
    tiles = [("photo", cut(ph["img"], (0, 0, ph["img"].size[0], ph["img"].size[1]), box, 600))]
    for s in srcs:
        lab, src = s.split("=", 1)
        im, bimg, P = src_side(src, refs, ph)
        if P is not None:
            rows[lab] = le.measures(P, ph["mmpx"])
        tiles.append((lab, cut(im, bimg, box, 600)))
    txt = le.table(rows)
    print(txt)
    open(out.rsplit(".", 1)[0] + ".txt", "w").write(txt + "\n")
    json.dump(rows, open(out.rsplit(".", 1)[0] + ".json", "w"), indent=1)
    big = [(lab, t.resize((1200, t.size[1] * 2), Image.LANCZOS)) for lab, t in (tiles[0], tiles[-1])]
    th = tiles[0][1].size[1]
    W, H = 1200, len(tiles) * th + 2 * big[0][1].size[1] + 20 * (len(txt.splitlines()) + 1)
    # small tiles two per row
    n = len(tiles)
    rows_px = (n + 1) // 2
    H = rows_px * th + 2 * big[0][1].size[1] + 20 * (len(txt.splitlines()) + 1)
    S = Image.new("RGB", (W, H), (24, 24, 24))
    d = ImageDraw.Draw(S)
    for i, (lab, t) in enumerate(tiles):
        x, y = (i % 2) * 600, (i // 2) * th
        S.paste(t, (x, y))
        d.rectangle([x, y, x + 8 + 7 * len(lab), y + 16], fill=(0, 0, 0))
        d.text((x + 4, y + 2), lab, fill=(255, 255, 255))
    y = rows_px * th
    for lab, t in big:
        S.paste(t, (0, y))
        d.rectangle([0, y, 8 + 7 * (len(lab) + 3), y + 16], fill=(0, 0, 0))
        d.text((4, y + 2), lab + " 2x", fill=(255, 255, 255))
        y += t.size[1]
    for j, line in enumerate(txt.splitlines()):
        d.text((8, y + 6 + 20 * j), line, fill=(230, 230, 230))
    S.save(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
