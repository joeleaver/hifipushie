"""eyetone.py: the eye-tone bands skincheck reads (sclera, iris, upper-lid skin, and the reference skin the lid is
compared with), in each image's own MediaPipe frame. Importable without side effects (skincheck.py runs on import).

The reference band ("cheek") must lie OUTSIDE every eye-region paint zone (skin.FACE eyelid / under_eye / eye_corner,
periorbital = their union grown 1.15): up to r7 it was 9-12 mm under the iris centre, inside the under_eye zone, so
darkening the under-eye made "lid / cheek" read LIGHTER while the lid itself got darker (Garrett lid_shade 2.0 +
under_eye_shade 1.5: lid R -8.2 -> +4.6). It is now the upper cheek CHEEK_MM below the lower-lid margin's middle
landmark (the under_eye zone's own anchor, lm_lid_lower); tests/test_eyetone.py checks the clearance against skin.FACE."""
import numpy as np
from PIL import Image, ImageDraw

# MediaPipe eye contours (upper lid inner -> outer, lower lid), iris landmarks (centre, 4 rim)
EYE = {"R": {"up": (133, 173, 157, 158, 159, 160, 161, 246, 33), "lo": (33, 7, 163, 144, 145, 153, 154, 155, 133), "iris": (468, 469, 470, 471, 472)},
       "L": {"up": (362, 398, 384, 385, 386, 387, 388, 466, 263), "lo": (263, 249, 390, 373, 374, 380, 381, 382, 362), "iris": (473, 474, 475, 476, 477)}}
IRIS_MM = 5.9            # iris radius (mm): the image's own ruler
CHEEK_MM = (21.0, 26.0)  # the reference band, mm below the lower-lid margin's middle (EYE[..]["lo"][4] = 145 / 374)
CHEEK_HALF_W = 6.0       # its half width (mm) about the iris centre
LID_MM = 2.0             # the lid skin band's height above the lash line (eyetone.lash_line)


def bands(shape, P, nm):
    """boolean masks (opening, lid, cheek) and (iris centre, iris radius px, px per mm) for one eye; None without landmarks"""
    from scipy import ndimage
    e = EYE[nm]
    if P is None or len(P) <= max(e["iris"]):
        return None
    c = P[e["iris"][0]]; rad = float(np.mean(np.linalg.norm(P[list(e["iris"][1:])] - c, axis=1)))
    mm = rad / IRIS_MM
    h, w = shape
    poly = [tuple(P[i]) for i in e["up"]] + [tuple(P[i]) for i in e["lo"]]
    mk = Image.new("L", (w, h), 0); ImageDraw.Draw(mk).polygon(poly, fill=1)
    op = ndimage.binary_erosion(np.asarray(mk, bool), iterations=max(1, int(round(0.5 * mm))))
    yy, xx = np.mgrid[0:h, 0:w]
    lid = np.zeros((h, w), bool)
    for a, b in zip(e["up"][1:-2], e["up"][2:-1]):   # the band above the upper margin, its middle part
        for t in np.linspace(0, 1, 6):
            q = P[a] * (1 - t) + P[b] * t
            lid[int(round(q[1] - 3 * mm)):int(round(q[1] - 1 * mm)), int(round(q[0])) - 1:int(round(q[0])) + 2] = True
    lo = P[e["lo"][4]]
    cheek = (np.abs(xx - c[0]) < CHEEK_HALF_W * mm) & (yy > lo[1] + CHEEK_MM[0] * mm) & (yy < lo[1] + CHEEK_MM[1] * mm)
    return op, lid, cheek, (c, rad, mm)


def lash_line(Lm, P, nm, mm):
    """(skin band, lash band) masks above the upper margin. Per column along the margin's middle part, the lash line is the
    dark run rising from the margin (darker than its own min + 50 % of the way to the skin 2-6 mm up); the lid skin band
    is LID_MM tall, starting 0.3 mm above the run's top. At face distance (~4.5 px / mm) a photo's lashes on a hooded lid
    merge into one dark band 1-2.5 mm tall: the fixed 1-3 mm band sat on it (Tess: lid .39 vs skin above ~.6; 2026-10-16)."""
    e = EYE[nm]; h, w = Lm.shape
    skin = np.zeros((h, w), bool); lash = np.zeros((h, w), bool)
    for a, b in zip(e["up"][1:-2], e["up"][2:-1]):
        for t in np.linspace(0, 1, 6):
            q = P[a] * (1 - t) + P[b] * t; x = int(round(q[0])); y0 = int(round(q[1]))
            ys = np.arange(y0, max(0, y0 - int(round(6 * mm))) - 1, -1)
            if len(ys) < 4 or not 1 <= x < w - 1:
                continue
            prof = Lm[ys, x - 1:x + 2].mean(axis=1)
            ref = np.median(prof[int(2 * mm):]) if len(prof) > int(2 * mm) + 1 else prof.max()
            lo = prof[:max(2, int(round(2.5 * mm)))].min(); T = lo + 0.5 * (ref - lo)
            k = 0
            while k < min(len(prof), int(round(3 * mm))) and (prof[k] < T or k < int(np.argmin(prof[:int(round(2.5 * mm)) + 1]))):
                k += 1
            lash[ys[:k], x - 1:x + 2] = True
            s0 = k + int(round(0.3 * mm)); s1 = s0 + max(2, int(round(LID_MM * mm)))
            skin[ys[min(s0, len(ys) - 1):min(s1, len(ys))], x - 1:x + 2] = True
    return skin & ~lash, lash


def eye_tone(im, P, nm):
    """luminance (Rec.709 of the encoded image, as contrast.py) of the sclera (opening minus iris, 0.5 mm in from the
    margins), the iris (ring 1.8 mm .. r - 0.8 mm), the upper-lid skin (1-3 mm above the margin; "lid_skin" = the band just above the lash line, "lash" = the lash line's share of the 1-3 mm band) and the upper cheek
    (CHEEK_MM below the lower-lid margin, outside every eye-region zone); mm from the iris (radius = 5.9 mm). None if the
    landmarks are missing."""
    A = np.asarray(im, float) / 255.0; Lm = 0.2126 * A[..., 0] + 0.7152 * A[..., 1] + 0.0722 * A[..., 2]
    bd = bands(Lm.shape, P, nm)
    if bd is None:
        return None
    op, lid, cheek, (c, rad, mm) = bd
    h, w = Lm.shape
    yy, xx = np.mgrid[0:h, 0:w]; rr = np.hypot(xx - c[0], yy - c[1])
    scl = op & (rr > rad + 0.6 * mm); iri = op & (rr < rad - 0.8 * mm) & (rr > 1.8 * mm)
    if not (scl.any() and iri.any() and lid.any() and cheek.any()):
        return None
    lv = float(np.median(Lm[lid])); white = op & (rr > rad) & (Lm > lv)   # (wfrac keeps the whole band's median: unchanged row)
    skin, la = lash_line(Lm, P, nm, mm)
    ls = float(np.median(Lm[skin])) if skin.any() else lv
    return {"scl": float(np.median(Lm[scl])), "iris": float(np.median(Lm[iri])), "lid": lv, "lid_skin": ls,
            "lash": float((la & lid).sum() / max(lid.sum(), 1)), "cheek": float(np.median(Lm[cheek])),
            "wfrac": float(white.sum() / max((op & (rr > rad)).sum(), 1))}
