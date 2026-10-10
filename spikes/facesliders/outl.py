"""outl.py: face outlines for the joint solve's chamfer term.

front_outline(view): the face's contour on a FRONT picture (temples, cheekbones, cheeks, jaw, chin): MediaPipe's face
oval (the detector's guess of it, 2-4 mm loose at the cheeks) snapped along its normal to the picture's strongest
luminance edge within SNAP of it (a Gaussian preference for the detector's place). Forehead points (under hair) left
out. traced(name, image): hand traces (likeness_points.json lines) of a picture, e.g. the desk painting's jaw and profile.
Run as `outl.py <model> <out.jpg>`: draws both on the pictures, to check by eye."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from hifipushie import humanfit_map as hm, likeness, store

SIDE = likeness.OVAL[5:32]     # 251 (upper temple, right) round the chin to 21 (upper temple, left)
SNAP = 0.05                   # of the face's width: how far the edge is searched each side of the detector's oval


def front_outline(view, det=None):
    det = hm.detector_points(view) if det is None else det
    if det is None:
        return None
    im = Image.open(view["image"]).convert("L").filter(ImageFilter.GaussianBlur(1.5))
    I = np.asarray(im, float)
    O = det[SIDE]
    # densify x3 along the chain
    t = np.linspace(0, len(O) - 1, 3 * len(O) - 2)
    O = np.c_[np.interp(t, np.arange(len(O)), O[:, 0]), np.interp(t, np.arange(len(O)), O[:, 1])]
    fw = float(np.linalg.norm(det[454] - det[234]))
    L = SNAP * fw
    tan = np.gradient(O, axis=0)
    nrm = np.c_[-tan[:, 1], tan[:, 0]]
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    s = np.linspace(-L, L, int(4 * L) + 1)
    out = []
    for p, n in zip(O, nrm):
        q = p[None] + s[:, None] * n[None]
        x = np.clip(q[:, 0], 0, I.shape[1] - 1)
        y = np.clip(q[:, 1], 0, I.shape[0] - 1)
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        x1, y1 = np.minimum(x0 + 1, I.shape[1] - 1), np.minimum(y0 + 1, I.shape[0] - 1)
        fx, fy = x - x0, y - y0
        v = (I[y0, x0] * (1 - fx) * (1 - fy) + I[y0, x1] * fx * (1 - fy) + I[y1, x0] * (1 - fx) * fy + I[y1, x1] * fx * fy)
        g = np.abs(np.gradient(v)) * np.exp(-0.5 * (s / (0.6 * L)) ** 2)
        out.append(p + s[int(np.argmax(g))] * n)
    out = np.array(out)
    # a light smoothing along the chain (one bad snap is a kink, not a feature)
    k = np.array([0.25, 0.5, 0.25])
    sm = out.copy()
    sm[1:-1] = k[0] * out[:-2] + k[1] * out[1:-1] + k[2] * out[2:]
    return sm


def traced(name, image, lines=("jaw.R", "jaw.L", "profile")):
    from hifipushie import likeness_shape as ls
    tr = ls.load_points(name).get(image) or {}
    return [np.asarray(tr["lines"][k], float) for k in lines if k in (tr.get("lines") or {})]


if __name__ == "__main__":
    name, out = sys.argv[1], sys.argv[2]
    tr_from = sys.argv[3] if len(sys.argv) > 3 else name
    refs = json.loads((store.HOME / name / "human_refs.json").read_text())
    tiles = []
    for i, v in enumerate(refs["views"]):
        im = Image.open(v["image"]).convert("RGB")
        d = ImageDraw.Draw(im)
        lines = [front_outline(v)] if abs(float(v.get("yaw", 0))) < 20 else traced(tr_from, v["image"])
        det = hm.detector_points(v)
        if det is not None and abs(float(v.get("yaw", 0))) < 20:
            d.line([tuple(p) for p in det[SIDE]], fill=(0, 120, 255), width=2)
        for o in lines:
            if o is not None:
                d.line([tuple(p) for p in o], fill=(255, 40, 40), width=2)
        pts = np.concatenate([o for o in lines if o is not None]) if any(o is not None for o in lines) else None
        if pts is not None:
            lo, hi = pts.min(0), pts.max(0)
            c, r = 0.5 * (lo + hi), 0.6 * max(hi - lo)
            im = im.crop((int(c[0] - r), int(c[1] - r), int(c[0] + r), int(c[1] + r)))
        tiles.append(im.resize((600, 600)))
    S = Image.new("RGB", (600 * len(tiles), 600))
    for i, t in enumerate(tiles):
        S.paste(t, (600 * i, 0))
    S.save(out, quality=85)
    print("wrote", out)


def profile_auto(view, step=6):
    """A true profile's front contour where the SKIN meets a plain background (the photo's own pixels), rows from the
    brow (just above the nasion) to the chin's underside, for a left-facing picture (the face toward small u). Per row
    the first pixel that starts a run of 6 skin-bright pixels: hair strands and lashes (dark, thin) crossing in front
    of the forehead / at the eye are skipped; the contour stops where it jumps back (the throat: the neck is not
    the head's). The forehead above the brow is left out (crossed and framed by hair in Tess's photo)."""
    a = np.asarray(Image.open(view["image"]).convert("RGB"), float)
    pts = view.get("points") or {}
    yb, yc = float(pts["nose_bridge"][1]), float(pts["chin"][1])
    y0, y1 = int(yb - 0.12 * (yc - yb)), int(yc + 0.22 * (yc - yb))
    bg = np.median(a[:, :15].reshape(-1, 3), 0)
    lum = a.mean(-1)
    fg = (np.abs(a - bg).sum(-1) > 40) & (lum > 0.55 * np.median(lum[int(yb):int(yc), :]))
    out = []
    for y in range(max(y0, 0), min(y1, a.shape[0]), step):
        r = fg[y]
        run = np.convolve(r.astype(float), np.ones(6), "valid") >= 6
        if not run.any():
            continue
        x = float(np.argmax(run))
        if out and y > yc and x - out[-1][0] > 12.0 * step / 6:   # (the throat, below the chin)
            break
        out.append([x, float(y)])
    return np.array(out)
