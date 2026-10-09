"""calib.py <garrett model> <out.json>: what face-ID numbers mean here.
photo vs: lightly altered photo, Garrett's other reference pictures, unrelated photos (skin_refs); the Garrett clay
render vs strangers' clay renders (other one-mesh humans, aligned onto his landmarks, same camera / light); the photo
vs those stranger renders. Also writes a contact strip <out>.jpg of the stranger renders."""
import json
import sys

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from hifipushie import faceid, likeness, likeness_pair, store

W = store.HOME
STRANGERS = ["om_new_man_30", "om_new_man_75", "om_new_woman_30", "om_new_woman_75", "om_new_teen_boy_16",
             "om_fit_man", "lk_garrett", "om_garrett"]
PHOTOS = ["ref_01_light_man_stubble", "ref_03_dark_man", "ref_05_olive_man_stubble", "ref_06_medium_man_tika",
          "ref_10_elderly_light_man", "ref_18_east_asian_man", "ref_02_light_woman_freckles", "ref_19_light_woman_plain"]


def aligned(mesh, ref):
    """mesh moved / scaled so its 68 landmarks' centroid and spread match ref's."""
    L, R = np.asarray(mesh["L"], float), np.asarray(ref["L"], float)
    ok = np.isfinite(L).all(1) & np.isfinite(R).all(1)
    cl, cr = L[ok].mean(0), R[ok].mean(0)
    s = np.sqrt(((R[ok] - cr) ** 2).sum() / ((L[ok] - cl) ** 2).sum())
    f = lambda X: (np.asarray(X, float) - cl) * s + cr  # noqa: E731
    out = dict(mesh)
    out["V"], out["L"] = f(mesh["V"]), f(mesh["L"])
    out["eyes"] = [(f(V), F, c) for V, F, c in mesh["eyes"]]
    return out


def main(name, out):
    m = likeness_pair.matched(name, face_id=False)
    ph, md = m["ph"], m["md"]
    photo, ren = m["photo"], m["render"]
    box, k = m["box"], m["k"]
    lm_p = likeness_pair._lm5(ph["side"], box, k)
    res = {}
    # altered copies of the photo
    alts = {"blur1": photo.filter(ImageFilter.GaussianBlur(2)),
            "bright": ImageEnhance.Brightness(photo).enhance(1.25),
            "rot4": photo.rotate(4, resample=Image.BICUBIC, fillcolor=(230, 230, 230)),
            "grey": photo.convert("L").convert("RGB"),
            "small": photo.resize((photo.size[0] // 6, photo.size[1] // 6), Image.BILINEAR).resize(photo.size, Image.BICUBIC)}
    sc = faceid.scores(photo, list(alts.values()))
    res["photo_vs_altered"] = dict(zip(alts, sc))
    # Garrett's other reference pictures
    refs = likeness._refs(name)
    others = []
    for v in refs["views"][1:]:
        img = Image.open(v["image"]).convert("RGB")
        b = likeness._box(v["points"], img.size)
        others.append(likeness_pair._crop(img, b, (900, int(900 * (b[3] - b[1]) / (b[2] - b[0])))))
    res["photo_vs_other_views"] = faceid.scores(photo, others)
    # unrelated photos
    imgs = [Image.open(W / "skin_refs" / f"{p}.jpg").convert("RGB") for p in PHOTOS]
    imgs = [im.resize((min(im.size[0], 1400), int(im.size[1] * min(im.size[0], 1400) / im.size[0]))) for im in imgs]
    res["photo_vs_strangers_photos"] = dict(zip(PHOTOS, faceid.scores(photo, imgs)))
    # stranger clay renders, same camera and light
    sh = md["shade"]
    light = (sh["c0"], sh["w"], sh["med"])
    rens, names, lms = [], [], []
    for s in STRANGERS:
        try:
            base = store.load(s)["base"]
            mesh = aligned(likeness.model_mesh(base), md["mesh"])
            im = likeness.render(mesh, ph["cam"], box, light=light)[0]
        except Exception as e:  # noqa: BLE001
            print("skip", s, e)
            continue
        P = likeness.detect([im])[0]
        rens.append(im)
        names.append(s)
        lms.append(None if P is None else faceid.lm5_from_mediapipe(P))
    lm_r = likeness_pair._lm5(md["side"], box, k)
    res["garrett_clay_vs_stranger_clay"] = dict(zip(names, faceid.scores(ren, rens, lm_r, lms)))
    res["photo_vs_stranger_clay"] = dict(zip(names, faceid.scores(photo, rens, lm_p, lms)))
    res["photo_vs_garrett_clay"] = faceid.scores(photo, [ren], lm_p, [lm_r])[0]
    res["photo_vs_garrett_clay_unlit"] = faceid.scores(photo, [m["clay"]], lm_p, [lm_r])[0]
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res, indent=1))
    strip = Image.new("RGB", (220 * (len(rens) + 2), 260), (20, 20, 20))
    for i, im in enumerate([photo, ren] + rens):
        strip.paste(im.resize((220, int(220 * im.size[1] / im.size[0]))).crop((0, 0, 220, 260)), (220 * i, 0))
    strip.save(out.rsplit(".", 1)[0] + ".jpg", quality=80)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
