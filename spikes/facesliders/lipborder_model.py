"""lipborder_model.py <model> [out png]: the model's vermilion border (GNM's upper_lip / lower_lip groups' outer edge loops,
carried onto the one mesh) projected through the front reference camera onto the photo, beside the photo's traced
border (lipborder.read) and MediaPipe's contour. The border evidence for the one solve is model loop vs traced
polyline, point-to-curve, in mm; this sheet shows both and prints the per-sample miss (mm, + = model outside hers)."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

import lipborder as LB
from hifipushie import base as basemod, humanfit, likeness, onemesh, store

g = basemod._gnm_data()
grp = lambda k: np.asarray(g["groups"][k], float) > 0.5  # noqa: E731
EXT = grp("skin_exterior")
Q = np.asarray(g["quads"], int)
E = np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]]
LIPS = grp("upper_lip") | grp("lower_lip")


def border_loop(name):
    """GNM vertex ids of the lip group's OUTER border (in the group, next to exterior skin outside both lips), ordered
    by x."""
    m = grp(name)
    a, b = E[:, 0], E[:, 1]
    bd = m[a] & ~LIPS[b] & EXT[b]
    v = np.unique(a[bd])
    T = np.asarray(g["template_vertex_positions"], float)
    return v[np.argsort(T[v, 0])]


UP_LOOP, LO_LOOP = border_loop("upper_lip"), border_loop("lower_lip")


def model_border_px(st, cam):
    tpl = st["tpl"]
    P = np.asarray(tpl["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    of = np.full(len(g["template_vertex_positions"]), -1)
    of[gid[gid >= 0]] = np.flatnonzero(gid >= 0)
    out = {}
    for k, loop in (("up", UP_LOOP), ("lo", LO_LOOP)):
        ids = of[loop]
        out[k] = humanfit.project(cam, P[ids[ids >= 0]])
    return out


def miss(model_px, poly, mmpx):
    """per model point: signed distance (mm) to the traced polyline (+ = away from the mouth centre)."""
    d = []
    for p in model_px:
        seg_a, seg_b = poly[:-1], poly[1:]
        ab = seg_b - seg_a
        t = np.clip(((p - seg_a) * ab).sum(1) / np.maximum((ab ** 2).sum(1), 1e-9), 0, 1)
        q = seg_a + t[:, None] * ab
        dist = np.linalg.norm(p - q, axis=1)
        j = int(np.argmin(dist))
        d.append((j, dist[j], q[j]))
    return d


if __name__ == "__main__":
    name = sys.argv[1]
    spec = store.load(name)
    refs = json.loads((store.HOME / name / "human_refs.json").read_text())
    v, cam = refs["views"][0], refs["cameras"][0]
    img = Image.open(v["image"]).convert("RGB")
    P = likeness.detect([img])[0]
    r = LB.read(img, P)
    st = humanfit.state(spec["base"])
    mb = model_border_px(st, cam)
    mouth = np.asarray(P, float)[[13, 14], :2].mean(0)
    for k, poly in (("up", r["upper"]), ("lo", r["lower"])):
        ms = miss(mb[k], poly, r["mmpx"])
        sg = [np.sign((p - mouth) @ (p - q)) * dd * r["mmpx"] for p, (j, dd, q) in zip(mb[k], ms)]
        print(k, "model vs traced (mm, + model outside):", np.round(sg, 2).tolist())
    im = img.copy()
    d = ImageDraw.Draw(im)
    for k, col in (("upper", (255, 30, 30)), ("lower", (255, 30, 30)), ("mp_up", (60, 120, 255)), ("mp_lo", (60, 120, 255))):
        d.line([tuple(p) for p in r[k]], fill=col, width=1)
    for k in ("up", "lo"):
        for p in mb[k]:
            d.ellipse([p[0] - 1.5, p[1] - 1.5, p[0] + 1.5, p[1] + 1.5], fill=(0, 200, 0))
    Qa = np.r_[r["upper"], r["lower"]]
    lo, hi = Qa.min(0), Qa.max(0)
    w = hi[0] - lo[0]
    c = im.crop((int(lo[0] - 0.35 * w), int(lo[1] - 0.35 * w), int(hi[0] + 0.35 * w), int(hi[1] + 0.35 * w)))
    c = c.resize((900, int(900 * c.height / c.width)), Image.LANCZOS)
    p = sys.argv[2] if len(sys.argv) > 2 else "/tmp/lbm.png"
    c.save(p)
    print("wrote", p)
