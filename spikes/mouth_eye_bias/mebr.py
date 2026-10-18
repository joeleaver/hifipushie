"""mebr.py <refname> <model> [tag]: the dressed Blender stages (flat albedo, lit by the photo's fitted light) of
<model> at <refname>'s front camera, MediaPipe on each, measures like meb.py. Saves the renders (out/r_<tag>_*.png)
and points. Heavy: takes resources.heavy."""
from __future__ import annotations

import json
import sys

import numpy as np
from PIL import Image

import meb

OUT = meb.OUT


def world_fill(lt: dict) -> dict:
    """the frontal fill (a sun from the camera, no shadow) moved into the world: the same irradiance on an open
    surface (pi x strength x colour), but occluded like a room's ambient (under the lower lip, the nostrils)."""
    import copy
    lt = copy.deepcopy(lt)
    fills = [l for l in lt["lights"][1:] if l.get("shadow") is False]
    E = sum(float(l["energy"]) for l in fills)
    lt["lights"] = [l for l in lt["lights"] if l not in fills]
    w = lt.setdefault("world", {"color": [0.8, 0.8, 0.8], "strength": 0.0})
    w["strength"] = round(float(w.get("strength", 0.0)) + E / (np.pi * float(np.mean(w.get("color", [0.8] * 3)))), 4)
    return lt


LIGHT_VARIANT = None


def shots(refname: str, model: str, spec=None, tag: str | None = None, size: int = 1024) -> dict:
    from hifipushie import likeness, resources, skin_read as sr, store
    sr.STAGE = "_meb_"
    rj, vi, ph = meb.setup(refname)
    spec = spec or store.load(model)
    box = sr.boxes(refname)[vi]
    fr_ = sr.fitted_frame(rj["cameras"][vi], box, "v")
    out = {}
    with resources.heavy(f"meb {model}", gb=6):
        sn = sr.stage(refname, spec)
        lt = sr.photo_light(refname, vi)
        if LIGHT_VARIANT == "worldfill":
            lt = world_fill(lt)
        if LIGHT_VARIANT == "hardkey":
            lt["lights"][0]["angle"] = 8
            lt["lights"][0].pop("window", None)
        lit = sr.shoot(sn, [fr_], lt, size=size)["v"]
        flat = sr.shoot(sn, [fr_], None, size=size, flat=True)["v"]
    side = max(box[2] - box[0], box[3] - box[1])
    for k, im in (("lit", lit), ("flat", flat)):
        a = im.astype(float)
        rgb = a[..., :3] * (a[..., 3:] / 255) + 128 * (1 - a[..., 3:] / 255)
        img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
        img.save(f"{OUT}/r_{tag or model}_{k}.png")
        P = likeness.detect([img])[0]
        out[k] = None if P is None else np.asarray(P, float)[:, :2] * side / size + np.array(box[:2])
    out["box"] = box
    return out


def variant(model: str, var: str) -> dict:
    """the model's spec with parts of the drawing taken out: var = '+'-joined of nolash, noskin, nolips (the lip
    layers' strength 0), noeyepaint (skin.eyes.canthus 0)."""
    import copy
    from hifipushie import store
    sp = copy.deepcopy(store.load(model))
    for v in var.split("+"):
        if v == "nolash":
            sp["base"]["lashes"] = False
        elif v == "noskin":
            sp.pop("skin", None)
            sp.pop("paint", None)
        elif v == "nolips":
            sp.setdefault("skin", {}).setdefault("lips", {})["strength"] = 0.2
        elif v.startswith("us"):
            sp.setdefault("skin", {}).setdefault("lips", {})["under_shade"] = int(v[2:]) / 100
        elif v.startswith("occ"):
            sp.setdefault("skin", {}).setdefault("eyes", {})["occlusion"] = int(v[3:]) / 100
        elif v in ("noocc", "nowater", "notear"):
            sp.setdefault("skin", {}).setdefault("eyes", {})[{"noocc": "occlusion", "nowater": "waterline", "notear": "tear"}[v]] = 0.0
        elif v in ("worldfill", "hardkey"):
            pass
        elif v == "norims":
            sp.setdefault("skin", {}).setdefault("eyes", {}).update({"waterline": 0.0, "occlusion": 0.0, "tear": 0.0})
        elif v == "norimlow":
            sp.setdefault("skin", {}).setdefault("lips", {})["rim_lower"] = 0.0
        elif v == "caruncle":
            sp.setdefault("skin", {}).setdefault("eyes", {})["caruncle"] = 1.0
        elif v == "nocanthus":
            sp.setdefault("skin", {}).setdefault("eyes", {})["canthus"] = 0.0
    return sp


if __name__ == "__main__":
    ref, model = sys.argv[1], sys.argv[2]
    var = sys.argv[3] if len(sys.argv) > 3 else ""
    for lv in ("worldfill", "hardkey"):
        if lv in var:
            LIGHT_VARIANT = lv
    tag = model + (f"_{var.replace('+', '_')}" if var else "")
    rj, vi, ph = meb.setup(ref)
    ex, ey = meb.frame_of(ph["side"].P)
    s = shots(ref, model, spec=variant(model, var) if var else None, tag=tag)
    rows = {"photo": meb.measures(ph["side"].P, ex, ey, ph["mmpx"])}
    for k in ("flat", "lit"):
        if s[k] is not None:
            rows[f"{k}:{tag}"] = meb.measures(s[k], ex, ey, ph["mmpx"])
            np.save(f"{OUT}/P_{k}_{tag}.npy", s[k])
    r = {"ref": ref, "view": vi, "mmpx": ph["mmpx"], "rows": rows}
    json.dump(r, open(f"{OUT}/mebr_{tag}.json", "w"), indent=1)
    print(meb.text(r))
