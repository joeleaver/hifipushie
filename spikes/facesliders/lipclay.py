"""lipclay.py <model> [view=0] [levers]: the lower lip's shading (lipshade.read's features), photo vs the model's CLAY lit
like the photo, and each lever's effect (finite differences), so the lip's form in depth can be solved for.

Light: likeness_shape.fit_light on the photo's linear luminance against the start model's normals (passes) over the
lower face's skin (the face oval under the nose, lips and a margin round them out: their albedo isn't skin's), kept
fixed for every lever. The model's shading = c0 + w . n (linear, no cast shadows); the photo's = its linear luminance.
Both read on their own lip grid (the detector on the photo crop, on the lit clay render for the model).

Levers (comma list; default all): c:<attribute>  the identity's coupled direction (faceatlas.direction, +1 sd within
sex), s:<slider>  a residual morph slider (+STEP). Prints the features of photo / model / each lever and the
Jacobian rows (per unit)."""
import copy
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import lipshade as LS
import rs
import sheet1
from hifipushie import faceatlas, likeness, likeness_shape as ls, store

PX = 640
STEP = {"c": 1.0, "s": 0.5}
FEATS = ("hl_v", "hl", "roll", "roll_u0", "roll_u1", "roll_u3", "roll_u4", "pad_w", "shadow", "shadow_u0", "shadow_u2")
DEFAULT = "c:lower_lip_proj,c:lower_vermilion,s:lip_lower_roll,s:mh_lowerlip_ext,s:lip_lower_width"


def flat(r):
    if r is None:
        return None
    return np.array([r["hl_v"], r["hl"], r["roll"], r["roll_u"][0], r["roll_u"][1], r["roll_u"][3], r["roll_u"][4],
                     r["pad_w"], r["shadow"], r["shadow_u"][0], r["shadow_u"][2]])


def setup(name, vi):
    sp = store.load(name)
    refs = __import__("json").loads((store.HOME / name / "human_refs.json").read_text())
    v, cam = refs["views"][vi], refs["cameras"][vi]
    crop = [int(round(x)) for x in sheet1.crop_of(v)]
    mesh = likeness.model_mesh(sp["base"])
    im, k, ps = likeness.render(mesh, cam, crop, px=PX, passes=True)
    ph = Image.open(v["image"]).convert("RGB").crop(tuple(crop)).resize(im.size, Image.LANCZOS)
    Y = ls._lin(ph)
    a = np.asarray(ph)
    P = rs.detect([a])[0]["P"][:, :2]
    H, W = Y.shape
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in P[likeness.OVAL]], fill=1)
    mask = np.asarray(m, bool).copy()
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    mask &= yy > P[2, 1] + 3
    mw = np.linalg.norm(P[61] - P[291])
    c = 0.5 * (P[13] + P[14])
    mask &= ((xx - c[0]) / (0.65 * mw)) ** 2 + ((yy - c[1]) / (0.5 * np.linalg.norm(P[0] - P[17]) + 6)) ** 2 > 1
    mask &= ps["part"] == 0
    c0, w, rms = ls.fit_light(Y, ps["nrm"], mask)
    return {"sp": sp, "cam": cam, "crop": crop, "Y": Y, "photo": a, "light": (c0, w), "rms": rms, "mask": mask}


def model_read(S, base):
    mesh = likeness.model_mesh(base)
    c0, w = S["light"]
    im, k, ps = likeness.render(mesh, S["cam"], S["crop"], px=PX, passes=True, light=(c0, w))
    pred = np.where(ps["part"] >= 0, c0 + ps["nrm"] @ np.asarray(w), 0.0)
    P = rs.detect([np.asarray(im.convert("RGB"))])[0]
    if P is None:
        return None, im
    return LS.read_values(P["P"], np.clip(pred, 0, None)), im


def with_lever(base, lever, amt):
    b = copy.deepcopy(base)
    kind, nm = lever.split(":")
    h = b["head"]
    if kind == "c":
        t = faceatlas.table()
        dc = faceatlas.direction({nm: amt * float(t["sd"][t["index"][nm]])})
        idn = h["identity"]
        for i in range(faceatlas.K):
            idn[f"head_{i:03d}"] = float(idn.get(f"head_{i:03d}", 0.0)) + float(dc[i])
    else:
        sl = h.setdefault("sliders", {})
        v = sl.get(nm, 0.0)
        sl[nm] = [x + amt for x in v] if isinstance(v, list) else v + amt
    return b


def main():
    name = sys.argv[1]
    vi = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    levers = (sys.argv[3] if len(sys.argv) > 3 else DEFAULT).split(",")
    S = setup(name, vi)
    print("light rms", round(S["rms"], 4), "c0", round(S["light"][0], 3), "w", np.round(S["light"][1], 3))
    fp = flat(LS.read_values(rs.detect([S["photo"]])[0]["P"], S["Y"]))
    r0, im0 = model_read(S, S["sp"]["base"])
    f0 = flat(r0)
    print(f"{'':22s}" + " ".join(f"{x:>9s}" for x in FEATS))
    print(f"{'photo':22s}" + " ".join(f"{x:9.3f}" for x in fp))
    print(f"{'model':22s}" + " ".join(f"{x:9.3f}" for x in f0))
    J = {}
    ims = [Image.fromarray(S["photo"]), im0]
    for lv in levers:
        amt = STEP[lv[0]]
        r, im = model_read(S, with_lever(S["sp"]["base"], lv, amt))
        if r is None:
            print(lv, "no face")
            continue
        J[lv] = (flat(r) - f0) / amt
        ims.append(im)
        print(f"{'d/d ' + lv:22s}" + " ".join(f"{x:9.3f}" for x in J[lv]))
    np.savez(f"{os.environ.get('F', '/mnt/data/hifipushie/faces2')}/out/lipclay_{name}_{vi}.npz", fp=fp, f0=f0,
             levers=np.array(list(J)), J=np.array([J[k] for k in J]), feats=np.array(FEATS))
    return S, fp, f0, J


if __name__ == "__main__":
    main()
