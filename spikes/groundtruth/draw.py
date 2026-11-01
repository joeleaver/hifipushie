"""groundtruth: tiles. A scan (clay, in GNM world under a fit's similarity) beside a GNM head and the signed gap, through
one camera and one light. views(): front / three-quarter / profile; feature(): a close tile on one feature."""
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import gt, rast

CLAY = np.array([208.0, 202.0, 196.0])
VIEWS = (("front", 0, 0), ("three-quarter", 40, 0), ("profile", 90, 0))
# feature: (yaw, pitch, the 68 landmarks whose box frames it, margin mm)
FEATURES = {"eyes": (0, 0, list(range(17, 27)) + list(range(36, 48)), 14), "eye 3q": (35, 0, list(range(22, 27)) + list(range(42, 48)), 16),
            "nose front": (0, 0, list(range(27, 36)), 18), "nose profile": (90, 0, [27, 30, 33], 26), "nose under": (0, -35, list(range(27, 36)), 18),
            "mouth": (0, 0, list(range(48, 68)), 16), "mouth 3q": (40, 0, list(range(48, 68)), 20), "lips profile": (90, 0, [33, 51, 57, 8], 24),
            "chin + jaw front": (0, 0, [4, 8, 12, 57], 14), "jaw 3q": (45, -10, [8, 10, 12, 14, 54], 26), "jaw profile": (90, 0, [8, 12, 14, 16, 57], 30),
            "cheek 3q": (40, 0, [1, 3, 30, 36, 48], 14), "forehead profile": (90, 0, [19, 27, 30], 45), "ear": (90, 0, [14, 15, 16], 42),
            "under-chin": (30, -40, [5, 8, 11, 57], 30)}


def font(sz):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def label(im, text, sz=34, fill=(0, 0, 0)):
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, im.width, sz + 14], fill=(255, 255, 255))
    d.text((10, 5), text, fill=fill, font=font(sz))
    return im


def clay(V, F, cam, colour=None, ss=2):
    vis = rast.visibility(V, F, cam, ss=ss)
    return rast.shade(vis, V, F, np.broadcast_to(CLAY, V.shape) if colour is None else colour, bg=(246, 246, 246))


def head_cam(L, yaw, pitch=0.0, size=(560, 700), half=0.155):
    ctr = L[[36, 45, 48, 54]].mean(0) + np.array([0.0, 0.05 if abs(yaw) > 60 else 0.02 if abs(yaw) > 25 else 0.0, 0.015])
    cam = rast.look_cam(ctr, yaw=yaw, pitch=pitch, dist=1.5, lens=85, size=size)
    cam["f"] = size[1] / 2 * 1.5 / half
    return cam


def box_cam(L, ids, yaw, pitch, margin_mm, size=(480, 480)):
    """A camera framing the box of landmarks `ids` (+ margin) from (yaw, pitch)."""
    cam = rast.look_cam(L[ids].mean(0), yaw=yaw, pitch=pitch, dist=1.5, lens=85, size=size)
    _, P = rast.cam_points(cam, L[ids])
    mm = 1.5 / cam["f"] * 1000
    ext = max(np.ptp(P[:, 0]), np.ptp(P[:, 1])) * mm + 2 * margin_mm
    c = 0.5 * (P.min(0) + P.max(0)) - np.asarray(size) / 2
    cam["f"] *= size[0] * mm / ext
    k = size[0] * mm / ext
    cam["t"] = [float(cam["t"][0] - c[0] * mm / 1000), float(cam["t"][1] - c[1] * mm / 1000), cam["t"][2]]
    return cam


def gnm_mesh(c, e=None):
    G = gt.gnm()
    V = gt.verts(c, e)
    return V, G["F"], G["WL"] @ V


def scan_in_gnm(scan, S, box_L=None):
    """The scan under S, cut to what stands near the head (the shoulders off) for drawing."""
    V = gt.apply(S, scan["V"])
    if box_L is not None:
        lo = box_L[8, 2] - 0.075
        keep = V[:, 2] > lo
        V2, F2, idx = gt.submesh(V, scan["F"], keep)
        return V2, F2, idx
    return V, scan["F"], np.arange(len(V))


def hstack(ims, pad=6, bg=(255, 255, 255)):
    h = max(i.height for i in ims)
    out = Image.new("RGB", (sum(i.width for i in ims) + pad * (len(ims) - 1), h), bg)
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + pad
    return out


def vstack(ims, pad=6, bg=(255, 255, 255)):
    w = max(i.width for i in ims)
    out = Image.new("RGB", (w, sum(i.height for i in ims) + pad * (len(ims) - 1)), bg)
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + pad
    return out


def legend(w, lim=4.0, h=48):
    im = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    n = 400
    for i in range(n):
        v = (i / (n - 1) * 2 - 1) * lim
        col = tuple(int(x) for x in rast.gap_colours(np.array([v]), lim)[0])
        d.rectangle([20 + i, 8, 21 + i, 30], fill=col)
    f = font(30 if w > 3200 else 24)
    d.text((20 + n + 30, 4), f"BLUE -{lim:g} mm: scan INSIDE GNM (GNM too big)  |  RED +{lim:g} mm: scan OUTSIDE (GNM too small)  |  dark grey: not compared (hair, cloth, eye)", fill=(0, 0, 0), font=f)
    return im
