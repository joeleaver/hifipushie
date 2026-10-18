"""mbord.py <ref> <model> [tag]: the vermilion's COLOUR border (lipborder.read) on the photo and on our dressed renders
(out/r_<tag>_{lit,flat}.png from mebr.py), against the model's GNM border rows (upper_lip / lower_lip group edges, what
the skin's lip paint is drawn through) projected through the same camera. Vertical mm on the photo's face axes at 5
positions along each border (u = 0.2 .. 0.8); + = the border lies OUTWARD (above for upper, below for lower)."""
from __future__ import annotations

import json
import sys

import numpy as np
from PIL import Image

import meb

US = (0.15, 0.25, 0.35, 0.5, 0.65, 0.75, 0.85)


def border_rows(spec, cam):
    """(upper (17, 2), lower (17, 2)) picture px of the head's GNM vermilion border rows."""
    from hifipushie import base as bm, face_ruler as fr
    head = fr.model_head(spec)
    g2m = fr._gnm_to_model(head)
    V = np.asarray(head["V"], float)
    E = bm._vermilion_edges()
    out = []
    for k in ("u", "l", "iu", "il"):
        X = V[[g2m[int(g)] for g in E[k]]]
        out.append(fr._cam_points(cam, X)[1])
    iu, il = out[2], out[3]
    # the contact ring's halves may differ in length: resample both on the same x
    return out[0], out[1], iu, np.array([[x, np.interp(x, *zip(*sorted(zip(il[:, 0], il[:, 1]))))] for x in iu[:, 0]])


def at_u(C, ex, u):
    """the curve's point at the share u of its x extent (C ordered right -> left in the picture or either way)."""
    x = C @ ex
    t = x.min() + u * (x.max() - x.min())
    i = np.argsort(x)
    return np.array([np.interp(t, x[i], C[i, 0]), np.interp(t, x[i], C[i, 1])])


SEAM = (78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95)


def heights(up, lo, seam, ex, ey, mmpx):
    """per u: (upper vermilion thickness = border above the seam, lower = border below the seam), mm. seam: (n, 2)
    points of the lips' meeting line (the picture's own MediaPipe inner contour, or the model's contact ring); the
    u share is taken over the OUTER border's x extent (corner to corner)."""
    r = []
    x0 = min((up @ ex).min(), (lo @ ex).min())
    x1 = max((up @ ex).max(), (lo @ ex).max())
    for u in US:
        t = x0 + u * (x1 - x0)
        def y(C):
            i = np.argsort(C @ ex)
            return float(np.interp(t, (C @ ex)[i], (C @ ey)[i]))
        r.append(((y(seam) - y(up)) * mmpx, (y(lo) - y(seam)) * mmpx))
    return np.array(r)


def contrast(img, up, lo, seam, ex, mmpx):
    """(upper, lower): Lab (lip - skin) between a band inside each vermilion (35-65 % of the way from the border to the
    seam) and a band of skin 1.5-2.5 mm outside the border, over the middle 60 % of the mouth."""
    from hifipushie import lipborder
    L, A = lipborder._lab(img)
    _, B = None, None
    out = []
    x = up @ ex
    for brd in (up, lo):
        ins, outs = [], []
        for u in np.linspace(0.2, 0.8, 13):
            t = x.min() + u * (x.max() - x.min())
            def pt(C):
                i = np.argsort(C @ ex)
                return np.array([np.interp(t, (C @ ex)[i], C[i, 0]), np.interp(t, (C @ ex)[i], C[i, 1])])
            b, sm = pt(brd), pt(seam)
            d = (b - sm) / max(np.linalg.norm(b - sm), 1e-9)
            for f in (0.35, 0.5, 0.65):
                q = b + f * (sm - b)
                ins.append((L[int(q[1]), int(q[0])], A[int(q[1]), int(q[0])]))
            for mm in (1.5, 2.0, 2.5):
                q = b + d * mm / mmpx
                outs.append((L[int(q[1]), int(q[0])], A[int(q[1]), int(q[0])]))
        out.append(np.median(np.array(ins), 0) - np.median(np.array(outs), 0))
        out[-1] = np.r_[out[-1], np.median(np.array(ins), 0)[0], np.median(np.array(outs), 0)[0]]
    return out


def main(ref, model, tag):
    from hifipushie import lipborder, store
    rj, vi, ph = meb.setup(ref)
    Pp, mmpx, cam = ph["side"].P, ph["mmpx"], ph["cam"]
    ex, ey = meb.frame_of(Pp)
    mouth = 0.5 * (Pp[13] + Pp[14])           # one fixed reference point: the photo's seam centre
    res = {}
    rp = lipborder.read(ph["img"], Pp, mmpx=mmpx)
    sp = Pp[list(SEAM)]
    res["photo"] = heights(rp["upper"], rp["lower"], sp, ex, ey, mmpx)
    res["photo_mp"] = heights(rp["mp_up"], rp["mp_lo"], sp, ex, ey, mmpx)
    con = {"photo": contrast(ph["img"], rp["upper"], rp["lower"], sp, ex, mmpx)}
    up, lo, iu, il = border_rows(store.load(model), cam)
    res["geom_rows"] = heights(up, lo, 0.5 * (iu + il), ex, ey, mmpx)
    from hifipushie import skin_read as sr
    box = sr.boxes(ref)[vi]
    for k in ("flat", "lit"):
        try:
            P = np.load(f"{meb.OUT}/P_{k}_{tag}.npy")
            im = Image.open(f"{meb.OUT}/r_{tag}_{k}.png").convert("RGB")
        except FileNotFoundError:
            continue
        side = max(box[2] - box[0], box[3] - box[1])
        s = im.size[0] / side
        Pc = (P - np.array(box[:2])) * s
        r = lipborder.read(im, Pc, mmpx=mmpx / s)
        res[k] = heights(r["upper"] / s + box[:2], r["lower"] / s + box[:2], P[list(SEAM)], ex, ey, mmpx)
        con[k] = contrast(im, r["upper"], r["lower"], Pc[list(SEAM)], ex, mmpx / s)
        res[k + "_mp"] = heights(r["mp_up"] / s + box[:2], r["mp_lo"] / s + box[:2], P[list(SEAM)], ex, ey, mmpx)
    lines = [f"{ref} / {tag}: border above (upper) / below (lower) the photo's seam centre, mm, at u = {US}"]
    for k, v in res.items():
        lines.append(f"{k:10s} upper " + " ".join(f"{x:5.2f}" for x in v[:, 0]) + " | lower " + " ".join(f"{x:5.2f}" for x in v[:, 1]))
    print("\n".join(lines))
    for k, v in res.items():
        c = len(US) // 2
        print(f"{k:10s} centre {v[c,0]:5.2f} / {v[c,1]:5.2f}  side taper (u .25/.75 over centre) upper {np.mean(v[[1,-2],0])/v[c,0]:.2f} lower {np.mean(v[[1,-2],1])/v[c,1]:.2f}")
    for k, (cu, cl) in con.items():
        print(f"{k:10s} lip - skin (dL, da*): upper {cu[0]:+6.1f} {cu[1]:+6.1f}  lower {cl[0]:+6.1f} {cl[1]:+6.1f}   L lip/skin: upper {cu[2]:.0f}/{cu[3]:.0f} lower {cl[2]:.0f}/{cl[3]:.0f}")
    json.dump({**{k: v.tolist() for k, v in res.items()}, "contrast": {k: [list(map(float, c)) for c in v] for k, v in con.items()}}, open(f"{meb.OUT}/mbord_{tag}.json", "w"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else sys.argv[2])
