"""The EYE RULER (eyeruler, 2026-10-11; Joe on a matched photo / render sheet: "I notice some measurement errors": our
eye was narrower corner to corner than hers and nobody had measured it). One set of eye measures, in mm AT THE MODEL,
read two ways:

  read(img, P, mmpx, ...)   on a PICTURE (the photo, or a dressed render through the same fitted camera): edges, not
                            detector points. MediaPipe's eye points only say where to look (a +-2.5 mm band).
  model(base, cam, ...)     on the MODEL's mesh through the fitted camera (exact: the truth the image reader was
                            validated against on dressed renders of known GNM heads; ERR below).

Everything is in the EYE FRAME of each eye: origin = the iris (limbus) centre, u = mm toward the outer corner along
the line through the two iris centres, v = mm up. Measures (per eye; `mean()` averages the two):
  inner / outer        the canthi (u, v); fissure = their distance; tilt = the outer canthus over the inner (degrees)
  sclera_in / _out     where the visible eyeball ends; caruncle = sclera_in - inner (the pink corner that shows)
  up[k] / lo[k]        the lid margins (v) at COLS (u = -9 .. 9 mm); open = up - lo; peak_u = where the upper lid peaks
  mrd1 / mrd2          the margins over / under the iris centre; cover_up / cover_lo = iris radius - mrd (mm hidden)
  iris                 the limbus diameter
  crease[k]            the fold line over the upper margin at COLS (= the visible lid platform's height); crease_dark
  brow[k]              the brow hair's lower edge over the upper margin at COLS
How the picture is read: the lash line, liner, waterline and caruncle are all DARK AND WARM against both the skin and
the eyeball, so the opening is ringed by a ridge of f = (R - B) / (R + G + B). The upper and lower ridges are tracked
by dynamic programming inside the detector's band; a margin is the ridge's flank toward the eyeball (half level); the
eyeball ends where the valley between the ridges closes; the inner canthus is the medial tip of the warm ridge past it.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at eye_ruler.NAME: C422). eye_ruler_picture: the picture's side: `read`, the limbus circle, one patch's read,
the crease and the brow. eye_ruler_model: the model's side: the ring, `model`, its crease and brow. eye_ruler_compare:
comparing picture and model: `mean`, `compare`, `text`, the overlay, the crease path.
"""
from __future__ import annotations

import numpy as np
from . import moved

STEP = 0.05                                # mm per patch pixel
U = np.arange(-19.0, 19.0001, STEP)        # across: + = toward the outer corner
V = np.arange(-11.0, 24.0001, STEP)        # up
COLS = np.array([-9.0, -6.0, -3.0, 0.0, 3.0, 6.0, 9.0])
BAND = 2.5                                 # mm either side of the detector's lid contours searched for a ridge
PAST = 4.5                                 # mm past the detector's corners searched
IRIS_SECTOR = 28.0                         # degrees either side of the eye line: the iris' own radial picture is read there
IRIS_OUT = 1.1                             # x the limbus radius: inside it the eyeball's edge is not read from f
RIM = 2.2                                  # mm: the most a lid rim (lash line, liner, waterline) is thick
SKIN_LUM = 0.7                             # x the local luminance: darker than this is not skin
# MediaPipe eye contours, outer corner -> inner corner (subject's right eye, left eye)
UPPER = ((33, 246, 161, 160, 159, 158, 157, 173, 133), (263, 466, 388, 387, 386, 385, 384, 398, 362))
LOWER = ((33, 7, 163, 144, 145, 153, 154, 155, 133), (263, 249, 390, 373, 374, 380, 381, 382, 362))
BROW_LOW = ((46, 53, 52, 65, 55), (276, 283, 282, 295, 285))
# The image reader's error on dressed fitted-camera renders of known heads, against model() (mm; rms over heads, both
# eyes; spikes/eyeruler/validate.py -> docs/notes/gnm_atlas.md "## eyeruler"). A difference under ~2 x this is not one.
# rms incl. bias, 14 heads x 2 eyes (2026-10-11); the lower margin's bias (+0.35: it reads the waterline's top) is
# taken off in compare() instead.
ERR = {"iris": 0.12, "centre": 0.13, "up": 0.25, "lo": 0.25, "mrd1": 0.19, "mrd2": 0.2, "open": 0.4, "inner": 0.63,
       "outer": 0.45, "fissure": 0.96, "tilt": 1.8, "peak_u": 0.56, "caruncle": 1.0, "brow": 0.7, "crease": 1.0}
LO_BIAS = 0.35
FLAGGED = ("crease",)   # on a RENDER the fold reads +-3 mm (a soft fold is not a line): the model's crease is the mesh's
                        # (blockin_eyes' section profile); on a photo with a crisp line it is used, error not measured

CREASE_MIN = 0.08       # the picture's line darkness under which the fold line is "not read"


# ---- patches ---------------------------------------------------------------------------------------------------------
def _bilinear(A, x, y):
    h, w = A.shape[:2]
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    return (A[y0, x0] * (1 - fx) * (1 - fy) + A[y0, x0 + 1] * fx * (1 - fy) + A[y0 + 1, x0] * (1 - fx) * fy
            + A[y0 + 1, x0 + 1] * fx * fy)


def frames(c_r, c_l) -> list:
    """The two eye frames from the iris centres (image px; subject's right eye first = the picture's left):
    [{"c", "ex" (toward the OUTER corner), "ey" (image down)}]."""
    c_r, c_l = np.asarray(c_r, float), np.asarray(c_l, float)
    e = (c_l - c_r) / np.linalg.norm(c_l - c_r)
    down = np.array([-e[1], e[0]])
    if down[1] < 0:
        down = -down
    return [{"c": c_r, "ex": -e, "ey": down}, {"c": c_l, "ex": e, "ey": down}]


def patch(A, fr: dict, k: float) -> np.ndarray:
    """The eye-frame patch (len(V), len(U), channels) of image array A; k = image px per mm. Row 0 = V[0] (lowest)."""
    X = fr["c"][None, None] + (U[None, :, None] * k) * fr["ex"] - (V[:, None, None] * k) * fr["ey"]
    return _bilinear(A, X[..., 0], X[..., 1])


def _iu(u):
    return int(round((u - U[0]) / STEP))


def _iv(v):
    return int(round((v - V[0]) / STEP))


def _smooth(a, mm):
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(a, mm / STEP)


# ---- ridges ----------------------------------------------------------------------------------------------------------
def _ridge(S, cols, lo, hi, lam=4.0, jump=3):
    """The best path through score S (rows v, columns u) over column indices cols, rows within [lo[j], hi[j]]: max of
    sum S - lam * (row step / jump)^2. Returns the row per column."""
    n = len(cols)
    R = S.shape[0]
    rows = np.arange(R)
    NEG = -1e9
    cost = np.full((n, R), NEG)
    back = np.zeros((n, R), int)
    ok = (rows >= lo[0]) & (rows <= hi[0])
    cost[0, ok] = S[ok, cols[0]]
    offs = np.arange(-jump, jump + 1)
    pen = lam * (offs / jump) ** 2
    for j in range(1, n):
        prev = cost[j - 1]
        cand = np.full((len(offs), R), NEG)
        for i, o in enumerate(offs):
            if o >= 0:
                cand[i, o:] = prev[:R - o] - pen[i]
            else:
                cand[i, :R + o] = prev[-o:] - pen[i]
        b = np.argmax(cand, 0)
        best = cand[b, rows]
        ok = (rows >= lo[j]) & (rows <= hi[j])
        cost[j, ok] = best[ok] + S[ok, cols[j]]
        back[j] = rows - offs[b]
    out = np.zeros(n, int)
    out[-1] = int(np.argmax(cost[-1]))
    for j in range(n - 1, 0, -1):
        out[j - 1] = back[j, out[j]]
    return out


def _contour(P, idx, fr, k):
    """Detector contour points in the eye frame (u, v), sorted by u."""
    d = (np.asarray(P, float)[list(idx), :2] - fr["c"]) / k
    uv = np.c_[d @ fr["ex"], -(d @ fr["ey"])]
    return uv[np.argsort(uv[:, 0])]


CREASE_LO, CREASE_HI = 1.5, 10.0     # mm over the upper margin searched for the fold line
CREASE_MIN_DARK = 0.035             # a line fainter than this against the skin either side is "not read"

# ---- comparing -------------------------------------------------------------------------------------------------------
SCALARS = ("fissure", "tilt", "caruncle", "iris", "mrd1", "mrd2", "cover_up", "cover_lo", "peak_u", "sclera_in", "sclera_out")
VECTORS = ("up", "lo", "open", "crease", "brow")


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("eye_ruler_picture", "eye_ruler_model", "eye_ruler_compare")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
