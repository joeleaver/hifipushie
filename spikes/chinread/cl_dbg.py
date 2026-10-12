"""cl_dbg.py <model> <out.png>: the model's jaw-set occluding contour (jaw_contour) on its 3/4 and front pictures, and
why _cloth_obs keeps or drops each point."""
import sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import face_ruler as fr

m, out = sys.argv[1], sys.argv[2]
head, views, _ = fr.reference_views(m, lids=False, lips=False, parse="auto", chin={"cloth": True})
tiles = []
for v in views[:2]:
    cam = v["cam"]
    im_m, ps = fr.clay(head, cam, passes=True)
    E, t, X, p, n2 = fr.jaw_contour(head, cam)
    zb = ps["zb"]
    print(v["kind"], "contour points", len(E), "zb", zb.shape, "img", v["img"].size)
    mm1 = X[:, 2] / cam["f"] * 1000.0
    zat = lambda q: zb[np.clip(np.round(q[:, 1]).astype(int), 0, zb.shape[0] - 1), np.clip(np.round(q[:, 0]).astype(int), 0, zb.shape[1] - 1)]  # noqa: E731
    qo = p + n2 * (2.5 / mm1)[:, None]
    qi = p - n2 * (1.0 / mm1)[:, None]
    a = zat(qo) - X[:, 2] > 0.004
    b = np.abs(zat(qi) - X[:, 2]) < 0.006
    print("  drop behind:", int(a.sum()), "visible:", int(b.sum()), "both:", int((a & b).sum()))
    print("  z samples: X", np.round(X[:5, 2], 4), "zb at p", np.round(zat(p)[:5], 4), "zb at qi", np.round(zat(qi)[:5], 4), "zb at qo", np.round(zat(qo)[:5], 4))
    pm = fr._parse_maps(v, head)
    im = v["img"].copy()
    d = ImageDraw.Draw(im)
    for i in range(len(E)):
        col = (0, 255, 0) if a[i] and b[i] else ((255, 255, 0) if b[i] else (255, 0, 0))
        d.ellipse([p[i, 0] - 2, p[i, 1] - 2, p[i, 0] + 2, p[i, 1] + 2], fill=col)
        d.line([tuple(p[i]), tuple(p[i] + 12 * n2[i])], fill=col)
    P = fr._cam_points(cam, np.asarray(head["L"], float)[:68])[1]
    s = 1.5 * (P[8, 1] - P[33, 1])
    cx, cy = P[[48, 54, 8]].mean(0)
    tiles.append(im.crop((int(cx - 1.2 * s), int(cy - s), int(cx + 1.2 * s), int(cy + 1.2 * s))).resize((720, 660)))
W = Image.new("RGB", (1440, 660))
W.paste(tiles[0], (0, 0)); W.paste(tiles[1], (720, 0))
W.save(out)
