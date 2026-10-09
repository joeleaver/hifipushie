"""lightfit.py <tag>...: one light (luminance = c0 + w . n, likeness_shape.fit_light) fitted on the photo and on each
dressed render ($L/out/<tag>_front_big.png) over the same skin mask and the same normals (ll_garrett's head through
the photo's camera): c0, |w|, hardness |w| / (c0 + |w|), the light's direction in WORLD axes, and the luminance
ratio of the eye sockets (upper lid + under the brow) to the cheeks on each picture."""
import os
import sys

import numpy as np
from PIL import Image

import sheet1
from hifipushie import humanfit, likeness, likeness_pair
from hifipushie import likeness_shape as ls

L = os.environ["L"]


def socket_ratio(Y, P, to_px, mask):
    """mean luminance in disks over each upper lid / brow gap vs over each cheek (detector points of the photo)."""
    H, W = Y.shape
    yy, xx = np.mgrid[0:H, 0:W]

    def disk(idx, wts, r):
        c = to_px(sum(w * P[i] for i, w in zip(idx, wts)))
        return (np.hypot(xx - c[0], yy - c[1]) < r)
    r = 0.012 * W
    out = {}
    cheek = (disk([205], [1], 2 * r) | disk([425], [1], 2 * r)) & mask
    for name, a, b in (("lid", 0.75, 0.25), ("fold", 0.45, 0.55)):     # upper lid skin; between it and the brow
        sock = (disk([159, 52], [a, b], r) | disk([386, 282], [a, b], r))
        out[name] = round(float(Y[sock].mean() / max(Y[cheek].mean(), 1e-6)), 3)
    under = disk([145, 230], [0.5, 0.5], r) | disk([374, 450], [0.5, 0.5], r)
    out["under_eye"] = round(float(Y[under].mean() / max(Y[cheek].mean(), 1e-6)), 3)
    return out


def fit(Yimg, md, ph):
    ps = md["passes"]
    H, W = ps["zb"].shape
    Y = ls._lin(Yimg)
    to_px = lambda P: (np.asarray(P, float) - [ph["box"][0], ph["box"][1]]) * md["k"]  # noqa: E731
    mask = ls.skin_mask(ph["side"], (H, W), to_px, md["k"] / md["mmpx"]) & (ps["part"] == 0)
    c0, w, rms = ls.fit_light(Y, ps["nrm"], mask)
    Rc = humanfit._cam_rot(md["cam"])
    dw = Rc.T @ (np.asarray(w) / max(np.linalg.norm(w), 1e-9))
    return {"c0": round(c0, 4), "w": round(float(np.linalg.norm(w)), 4), "hard": round(float(np.linalg.norm(w) / (c0 + np.linalg.norm(w))), 3),
            "dir_world": np.round(dw, 3).tolist(), "rms": round(rms, 4),
            "vs_cheek": socket_ratio(Y, ph["side"].P, to_px, mask)}


m = likeness_pair.matched("ll_garrett", face_id=False)
ph, md = m["ph"], m["md"]
H, W = md["passes"]["zb"].shape
box = ph["box"]
print("photo", fit(ph["img"].transform((W, H), Image.EXTENT, tuple(box), Image.BICUBIC), md, ph))
crop = sheet1.crop_of(likeness._refs("ll_garrett")["views"][0])
for tag in sys.argv[1:]:
    im = Image.open(f"{L}/out/{tag}_front_big.png").convert("RGB")
    s = im.size[0] / (crop[2] - crop[0])
    b = ((box[0] - crop[0]) * s, (box[1] - crop[1]) * s, (box[2] - crop[0]) * s, (box[3] - crop[1]) * s)
    print(tag, fit(im.transform((W, H), Image.EXTENT, b, Image.BICUBIC), md, ph))
