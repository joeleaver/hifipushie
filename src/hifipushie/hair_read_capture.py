"""Capture: the frames of a reference (picture, parse, rays), and a render read as a picture. Part of the hair read (hair_read.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import hair_read
from . import store
from .hair_read import cam_eye

def frames(name: str, spec: dict | None = None, views=None, images: dict | None = None) -> list:
    """Per fitted reference view: {"i", "image" (PIL RGB), "cam", "box", "mm" (mm a pixel at the head centre), "c"
    (head centre px), "hair" (hair probability, picture px), "skin" (bare face skin + neck), "bg" (backdrop),
    "skull" (the bare skull's silhouette, bool), "yaw"}. Cached per process by the pictures and cameras."""
    from PIL import Image
    from scipy import ndimage as ndi
    from . import faceparse
    from . import humanfit_views
    from . import hair_card_fit, hair_head
    spec = store.load(name) if spec is None else spec
    sc = hair_head.scalp(name, spec)
    refs = hair_card_fit.human_refs(name)
    out = []
    for i, cam in enumerate(refs.get("cameras") or []):
        if views is not None and i not in views:
            continue
        v = (refs.get("views") or [{}] * (i + 1))[i] or {}
        sub = (images or {}).get(i)
        if images is not None and sub is None:
            continue
        if sub is not None:  # OUR render through this camera instead of the picture (like with like)
            img = render_as_picture(sub, cam["size"])
            ident = hashlib.sha1(np.asarray(img).tobytes()).hexdigest()[:16]
        else:
            img, ident = None, v.get("image")
        key = json.dumps([ident, cam, sc.C.tolist(), hair_read.VERSION], sort_keys=True, default=str)
        if key in hair_read._FRAMES:
            out.append(hair_read._FRAMES[key])
            continue
        img = Image.open(v["image"]).convert("RGB") if img is None else img
        A, E = np.meshgrid(np.arange(0, 360, 1.0), np.arange(-60, 90, 1.0))
        P = sc.point(A.ravel(), E.ravel(), 0.0)
        uv = humanfit_views.project(cam, P)
        x0, y0 = uv.min(0)
        x1, y1 = uv.max(0)
        s = 1.3 * max(x1 - x0, y1 - y0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        box = (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)
        hp, bgp = [], None
        skin = None
        for net in hair_read.NETS:
            res = faceparse.parse(img, box, net)
            g = faceparse.groups(res)
            hp.append(faceparse.to_picture(g["hair"], box, img.size))
            if net == "bisenet":
                skin = faceparse.to_picture(res["p"][list(hair_read.SKIN_CLASSES)].sum(0), box, img.size)
                bgp = faceparse.to_picture(res["p"][0], box, img.size)
                # (to_picture pads with 0 outside the crop: outside it is backdrop as far as this reader goes)
                inside = faceparse.to_picture(np.ones_like(res["p"][0]), box, img.size) > 0.5
                bgp = np.where(inside, bgp, 1.0)
        W, H = img.size
        sk = np.zeros((H, W), bool)
        q = np.round(uv).astype(int)
        ok = (q[:, 0] >= 0) & (q[:, 0] < W) & (q[:, 1] >= 0) & (q[:, 1] < H)
        sk[q[ok, 1], q[ok, 0]] = True
        sk = ndi.binary_fill_holes(ndi.binary_closing(sk, iterations=4))
        eye, _ = cam_eye(cam)
        from . import humanfit_views
        Xc = (sc.C - np.asarray(cam["centre"], float)) @ humanfit_views._cam_rot(cam).T + np.asarray(cam["t"], float)
        f = {"i": i, "image": img, "cam": cam, "box": box, "mm": float(Xc[2]) / float(cam["f"]) * 1000.0,
             "c": humanfit_views.project(cam, sc.C[None])[0], "hair": np.mean(hp, 0), "skin": skin, "bg": bgp, "skull": sk,
             "yaw": float(v.get("yaw", cam.get("yaw", 0.0)) or 0.0), "image_path": v.get("image")}
        hair_read._FRAMES[key] = f
        out.append(f)
    return out


def render_as_picture(img, size):
    """A square render of a "ref<i>" / fitted view (the picture centred in it, hair.ref_square's layout) cropped and
    scaled back to the picture's own pixels (w, h = size)."""
    from PIL import Image
    im = (Image.open(img) if not hasattr(img, "size") else img).convert("RGB")
    w, h = size
    side = max(w, h)
    n = im.size[0]
    k = n / side
    x0, y0 = (side - w) / 2 * k, (side - h) / 2 * k
    return im.crop((int(round(x0)), int(round(y0)), int(round(x0 + w * k)), int(round(y0 + h * k)))).resize((w, h), Image.LANCZOS)
