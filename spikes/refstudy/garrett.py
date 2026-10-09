"""Garrett with the study's fit (the REAL tools: humanfit_map through the one mesh): a fresh head (lk_garrett v1:
his body, mean identity) fitted to his two references, without and with Joe's read as evidence.
Models saved: rs_garrett_map, rs_garrett_read (workspace). Sheets: R/rs_10_garrett_*.png.
  run.sh garrett.py [fit] [sheet] [views]"""
import copy
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import rs
from hifipushie import humanfit, humanfit_map, humanmacro as hm, likeness, likeness_read, store

R = os.environ.get("R", str(rs.D / "out"))
# Joe: "a chunky, handsome guy with a square jaw, cleft chin, cute nose" -> macros (population sigmas)
READ = {"cheek_fullness": 1.2, "face_width": 0.8, "neck_width": 1.0, "jaw_square": 1.5, "jaw_width": 1.0,
        "chin_projection": 1.0, "chin_width": 0.8, "nose_length": -0.8, "nose_upturn": 1.0}


# the same read with what it does NOT mean said too: in GNM's population a square jaw comes with fat (cheek fullness
# +0.44, under-chin fullness): "chunky, handsome" = bone, not fat: a clean jaw-to-neck line, a brow, moderate cheeks
READ3 = {"jaw_square": 1.5, "jaw_width": 1.0, "chin_projection": 1.0, "chin_width": 0.8, "under_chin": 0.8, "cheek_fullness": 0.3,
         "neck_width": 1.0, "nose_length": -0.8, "nose_upturn": 0.8, "brow_ridge": 0.8, "eye_depth": 0.5, "eye_height": -0.6,
         "cheekbone_width": 0.8, "ear_out": -0.5}


def refs():
    r = json.load(open(store.HOME / "om_garrett" / "human_refs.json"))
    return [{k: v for k, v in vw.items() if k in ("image", "size", "yaw", "points")} for vw in r["views"]]


def hist(name, v):
    s = json.load(open(store.HOME / name / "history" / f"{v:04d}.json"))
    return s.get("spec", s)


def fit():
    sp = hist("lk_garrett", 1)
    vs = refs()
    for tag, read, rsd in (("rs_garrett_map", None, 0.8), ("rs_garrett_read", READ, 0.8), ("rs_garrett_read2", READ, 0.4), ("rs_garrett_read3", READ3, 0.4))[int(os.environ.get("ONLY", 0)):]:
        b, rep = humanfit_map.fit(sp["base"], vs, read=read, read_sd=rsd)
        print(tag, humanfit.verdict(rep["integrity"])[:300], "refused" if rep.get("refused") else "")
        if rep.get("refused"):
            b, rep = humanfit_map.fit(sp["base"], vs, read=read, read_sd=rsd, force=True)
            print("  FORCED:", humanfit.verdict(rep["integrity"])[:300])
        print("  ", [(v["evidence"], v["rms_mm"], v["lens_mm"]) for v in rep["views"]], rep["plausibility"])
        if rep.get("read"):
            print("   read:", rep["read"])
        print(rep["macros"])
        store.save(tag, {**copy.deepcopy(sp), "base": b}, "refstudy: MAP fit to Garrett's two references" + (" + Joe's read" if read else ""))
        (store.HOME / tag / "human_refs.json").write_text(json.dumps({"views": vs, "cameras": rep["cameras"]}, indent=1))


MODELS = [("pass 6 (om_garrett v16)", lambda: hist("om_garrett", 16)["base"]), ("v23 dense fit (om_garrett v15)", lambda: hist("om_garrett", 15)["base"]),
          ("NEW: MAP, pictures only", lambda: store.load("rs_garrett_map")["base"]), ("NEW: MAP + read", lambda: store.load("rs_garrett_read")["base"]),
          ("NEW: MAP + read held firmly (+-0.4)", lambda: store.load("rs_garrett_read2")["base"]),
          ("NEW: MAP + fuller read (bone, not fat)", lambda: store.load("rs_garrett_read3")["base"])]


def sheet(px=620):
    vs = refs()
    rows = [[], []]
    for vi, v in enumerate(vs):
        img = Image.open(v["image"]).convert("RGB")
        box = likeness._box(v["points"], img.size)
        c = img.crop([int(x) for x in box])
        k = px / max(c.size)
        rows[vi].append(("reference", c.resize((int(c.size[0] * k), int(c.size[1] * k)), Image.LANCZOS)))
    for label, get in MODELS:
        b = get()
        _, rep = humanfit_map.fit(b, vs, free=())   # this head's own best cameras on the same evidence
        mesh = likeness.model_mesh(b)
        z = hm.read(humanfit.identity(b))
        for vi, v in enumerate(vs):
            img = Image.open(v["image"])
            box = likeness._box(v["points"], img.size)
            im, _ = likeness.render(mesh, rep["cameras"][vi], box, px=px)
            rows[vi].append((f"{label}  [{rep['views'][vi]['rms_mm']} mm]", im.convert("RGB")))
        print(label, "plausibility", humanfit.plausibility(b), "\n" + hm.text(z, 6))
    W = sum(im.size[0] for _, im in rows[0]) + 8 * len(rows[0])
    H = sum(max(im.size[1] for _, im in r) + 24 for r in rows)
    S = Image.new("RGB", (W, H), (238, 238, 238))
    y = 0
    for r in rows:
        x = 0
        for label, im in r:
            S.paste(im, (x, y + 20))
            ImageDraw.Draw(S).text((x + 6, y + 4), label, fill=(0, 0, 0))
            x += im.size[0] + 8
        y += max(im.size[1] for _, im in r) + 24
    out = f"{R}/rs_10_garrett_reference_vs_fits.png"
    S.save(out)
    print(out)


def views():
    for tag, name, get in (("pass6", "om_garrett", MODELS[0][1]), ("v23", "om_garrett", MODELS[1][1]), ("map", "rs_garrett_map", MODELS[2][1]), ("read", "rs_garrett_read", MODELS[3][1]), ("read2", "rs_garrett_read2", MODELS[4][1]), ("read3", "rs_garrett_read3", MODELS[5][1]))[int(os.environ.get("ONLYV", 0)):]:
        o = likeness_read.render_views("rs_garrett_read", f"{R}/rs_11_garrett_six_views_{tag}.png", base=get())
        print(o)


if __name__ == "__main__":
    for a in sys.argv[1:]:
        {"fit": fit, "sheet": sheet, "views": views}[a]()
