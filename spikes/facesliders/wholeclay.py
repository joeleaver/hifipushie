"""wholeclay.py <out png> <camera model> <model>...: faces6, WHOLE-FACE clay comparison (the coordinator: dressed renders
were masking what the shape reads as): photo | each model, front / 3/4 / profile, all through the SAME cameras (the
camera model's fitted ones), fast clay with AO + a soft key (likeness.render), brows drawn. Prints per model |c| (head
comps) and a few whole-face widths (mm): bizygomatic-ish (landmarks 1-15), jaw (4-12), chin (6-10), face height
(27-8)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import humanfit, likeness, store

T = int(os.environ.get("T", "360"))
SHADE = os.environ.get("SHADE", "1") == "1"
BROW_MM = float(os.environ.get("BROW_MM", "4"))   # drawn brows' thickness (0: none; the 4 mm default pushes male)


def draw_brows(im, mesh, cam, box, k):
    if BROW_MM <= 0:
        return im
    L = humanfit.project(cam, mesh["L"])
    d = ImageDraw.Draw(im)
    wpx = max(1, int(round(BROW_MM / likeness._mm_per_px(cam, mesh["L"]) * k)))
    for a, b in ((17, 22), (22, 27)):
        d.line([((L[i, 0] - box[0]) * k, (L[i, 1] - box[1]) * k) for i in range(a, b)], fill=(70, 52, 40), width=wpx,
               joint="curve")
    return im


HAIRCAP = os.environ.get("HAIRCAP", "0") == "1"
LIGHTS = os.environ.get("LIGHTS", "key").split(",")   # key (the clay's top-front key) | photo (HER fitted light + AO share)   # a neutral dark cap over the scalp (bald clay reads male)
HAIR_RGB = np.array([62.0, 46.0, 36.0])


def haircap(mesh, st):
    """per-vertex colour: skin, and hair over GNM's scalp (outside its hockey_mask face region, not the ears, above the
    ears' bottom), softened along the mask's own gradient."""
    from hifipushie import base as basemod, onemesh
    g = basemod._gnm_data()
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])]
    ok = gid >= 0
    hm_ = np.zeros(len(gid))
    hm_[ok] = np.asarray(g["groups"]["hockey_mask"], float)[gid[ok]]
    ear = np.zeros(len(gid))
    ear[ok] = np.asarray(g["groups"]["ears"], float)[gid[ok]]
    L = st["L"]
    zcut = 0.5 * (L[1, 2] + L[15, 2])
    V = mesh["V"]
    w = ok * (1 - hm_) * (1 - ear) * np.clip((V[:, 2] - zcut) / 0.01, 0, 1)
    return (1 - w)[:, None] * likeness.SKIN + w[:, None] * HAIR_RGB


BROWS_R = ([70, 63, 105, 66, 107], [46, 53, 52, 65, 55])
BROWS_L = ([300, 293, 334, 296, 336], [276, 283, 282, 295, 285])


def draw_photo_brows(im, P, to):
    """HER brows on the clay (coordinator: the drawn 2-4 mm line on GNM's brow landmarks sat low and heavy and biased
    every read): the photo detector's brow band (upper and lower contour) as a filled shape, through `to` (picture
    pixels -> this image's, the eye registration included)."""
    d = ImageDraw.Draw(im)
    P = np.asarray(P, float)[:, :2]
    for up, lo in (BROWS_R, BROWS_L):
        poly = to(np.r_[P[up], P[lo][::-1]])
        d.polygon([tuple(p) for p in poly], fill=(70, 52, 40))
    return im


def eye_presentation(mesh, iris=(128, 112, 82)):
    """A cheaper-than-real eye for whole-face reads (coordinator: the dark iris caps dominated every clay read): a
    lighter iris (hazel-ish, set by `iris`) with a darker limbal ring and pupil, and a LASH LINE: the skin vertices
    hugging the upper half of each eyeball (within 1.5 mm of its surface, above its centre) darkened."""
    out = []
    fwd = np.asarray(mesh["state"]["head"].get("forward", [0, -1, 0]), float)
    for V, F_, col in mesh["eyes"]:
        c = V.mean(0)
        d = (V - c) / np.linalg.norm(V - c, axis=1, keepdims=True)
        cs = d @ (fwd / np.linalg.norm(fwd))
        col = np.where(cs[:, None] > 0.97, [20, 16, 14], np.where(cs[:, None] > 0.885, list(iris),
                       np.where(cs[:, None] > 0.86, [60, 50, 40], [238, 234, 228]))).astype(float)
        out.append((V, F_, col))
    mesh["eyes"] = out
    C = np.asarray(mesh.get("C") if mesh.get("C") is not None else np.tile(likeness.SKIN, (len(mesh["V"]), 1)), float).copy()
    for V, _, _ in out:
        c = V.mean(0)
        r = float(np.median(np.linalg.norm(V - c, axis=1)))
        dist = np.linalg.norm(mesh["V"] - c, axis=1) - r
        near = (dist < 0.0015) & (mesh["V"][:, 2] > c[2] - 0.0005) & ((mesh["V"] - c) @ fwd > 0.3 * r)
        C[near] = C[near] * 0.35
    mesh["C"] = C
    return mesh


def ident(sp):
    idn = sp["base"]["head"].get("identity") or {}
    return np.array([v for k, v in idn.items() if k.startswith("head")]) if isinstance(idn, dict) else np.asarray(idn)


if __name__ == "__main__":
    out, cm, models = sys.argv[1], sys.argv[2], sys.argv[3:]
    refs = json.loads((store.HOME / cm / "human_refs.json").read_text())
    views = [i for i in range(len(refs["views"]))]
    meshes = {}
    for m in models:
        sp = store.load(m)
        st = humanfit.state(sp["base"])
        meshes[m] = likeness.model_mesh_from_state(st)
        if HAIRCAP:
            meshes[m]["C"] = haircap(meshes[m], st)
        L = st["L"]
        w = lambda a, b: float(np.linalg.norm(L[a] - L[b])) * 1000  # noqa: E731
        print(f"{m}: |c| {np.linalg.norm(ident(sp)):.2f} ({len(ident(sp))} comps); widths 1-15 {w(1, 15):.1f}, jaw 4-12 "
              f"{w(4, 12):.1f}, chin 6-10 {w(6, 10):.1f}, height 27-8 {w(27, 8):.1f}", flush=True)
    rowsdef = [(vi, lt) for vi in views for lt in LIGHTS]
    sheet = Image.new("RGB", (T * (1 + len(models)), (T + 18) * len(rowsdef) + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(["photo"] + models):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    ref_st = humanfit.state(store.load(cm)["base"])
    for i, (vi, lt) in enumerate(rowsdef):
        cam = refs["cameras"][vi]
        P = humanfit.project(cam, ref_st["L"])
        c = 0.5 * (P.min(0) + P.max(0))
        side = 1.35 * float(np.max(P.max(0) - P.min(0)))
        box = (c[0] - side / 2, c[1] - side / 2 - 0.05 * side, c[0] + side / 2, c[1] + side / 2 - 0.05 * side)
        img = Image.open(refs["views"][vi]["image"]).convert("RGB")
        y = 18 + i * (T + 18)
        dr.text((4, y), f"view {vi} (cameras of {cm}), light: {'her fitted light + AO share' if lt == 'photo' else 'clay key'}", fill=(0, 0, 0))
        sheet.paste(img.crop(tuple(int(round(b)) for b in box)).resize((T, T), Image.LANCZOS), (0, y + 16))
        for j, m in enumerate(models):
            kw = dict(ao=True, shadow=8.0) if SHADE else {}
            if lt == "photo":
                from noserender import lit_render
                im, _, _ = lit_render(meshes[m], cam, img, box=box, px=2 * T)
                k = 2 * T / max(box[2] - box[0], box[3] - box[1])
            else:
                im, k = likeness.render(meshes[m], cam, box, px=2 * T, brows=False, **kw)[:2]
            im = draw_brows(im, meshes[m], cam, box, k)
            sheet.paste(im.resize((T, T), Image.LANCZOS), ((j + 1) * T, y + 16))
    sheet.save(out)
    print("wrote", out)
