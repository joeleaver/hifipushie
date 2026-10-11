"""gc.py: GNM's raw head for control studies: coefficients -> vertices (identity 253, expression 383, joints), and fast
clay renders (likeness.render: hair cap, GNM's own eyes with a presentable iris, drawn brows) through front / 3/4 /
profile cameras. World frame = the repo's (Z up, facing -Y)."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from hifipushie import base as basemod, likeness

g = basemod._gnm_data()
TPL = np.asarray(g["template_vertex_positions"], float)
NV = len(TPL)
IB = np.asarray(g["vertex_identity_basis"], np.float32)
EB = np.asarray(g["expression_basis"], np.float32)
ID_NAMES = [str(x) for x in g["identity_names"]]
EX_NAMES = [str(x) for x in g["expression_names"]]
HEAD = np.array([n.startswith("head") for n in ID_NAMES])
grp = lambda k: np.asarray(g["groups"][k], float) > 0.5  # noqa: E731
GROUPS = {k: grp(k) for k in g["groups"]}
Q = np.asarray(g["quads"], int)
EXT = GROUPS["skin_exterior"]
try:
    FONT = ImageFont.truetype("DejaVuSans.ttf", 13)
    FONT_B = ImageFont.truetype("DejaVuSans-Bold.ttf", 15)
except OSError:
    FONT = FONT_B = ImageFont.load_default()


def faces(mask):
    q = Q[mask[Q].all(1)]
    return np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]].astype(np.int64)


SKIN_MASK = GROUPS["skin"] & ~GROUPS["mouth_sock"]
F_SKIN = faces(GROUPS["skin"])
F_MOUTH = faces(GROUPS["mouth_sock"] | GROUPS["teeth"])
EYE_PARTS = [(faces(GROUPS["scleras"]), np.array([236.0, 232.0, 226.0])),
             (faces(GROUPS["irises"] & ~GROUPS["pupils"]), np.array([128.0, 112.0, 82.0])),
             (faces(GROUPS["pupils"]), np.array([22.0, 18.0, 16.0]))]
WLM = np.zeros((68, NV))
for i, r in enumerate(g["lm68"]):
    for v, w in zip(r[0::2], r[1::2]):
        WLM[i, int(v)] += float(w)
HAIR = np.array([62.0, 46.0, 36.0])


def world(V):
    """GNM frame (x left, y up, z forward) -> world (Z up, facing -Y)."""
    return np.c_[V[:, 0], -V[:, 2], V[:, 1]]


def verts(c=None, e=None, D=None):
    V = TPL.copy()
    if c is not None and np.any(c):
        c = np.asarray(c, np.float32)
        V = V + np.tensordot(c, IB[:len(c)], 1)
    if e is not None and np.any(e):
        e = np.asarray(e, np.float32)
        V = V + np.tensordot(e, EB[:len(e)], 1)
    if D is not None:
        V = V + D
    return V


def cap_colours(Vw):
    """Per-vertex colour: skin, a dark hair cap outside GNM's hockey mask above the ears' bottom (bald clay reads male)."""
    L = WLM @ Vw
    zcut = 0.5 * (L[1, 2] + L[15, 2])
    w = (~GROUPS["hockey_mask"]) * (~GROUPS["ears"]) * np.clip((Vw[:, 2] - zcut) / 0.01, 0, 1)
    C = (1 - w)[:, None] * likeness.SKIN + w[:, None] * HAIR
    # vermilion tint (the lips group), presentation only
    lip = GROUPS["upper_lip"] | GROUPS["lower_lip"]
    C[lip] = C[lip] * np.array([0.98, 0.78, 0.76])
    return C


YAWS = {"front": 0.0, "3q": -35.0, "profile": -90.0}


def render(V, view="front", px=220, light=None, half=0.105, centre=None, cap=True, brows=True, passes=False):
    """V in GNM's frame. view: front | 3q | profile | yaw degrees. light: None (likeness' key) | 'rake' | (c0, w)."""
    W = world(V)
    L = WLM @ W
    yaw = YAWS.get(view, view) if isinstance(view, str) else float(view)
    cen = L[[36, 45, 48, 54]].mean(0) if centre is None else np.asarray(centre, float)
    cam = {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.8], "f": px / 2 * 0.8 / half, "size": [px, px],
           "centre": list(map(float, cen)), "yaw": float(yaw)}
    mesh = {"V": W, "F": F_SKIN, "eyes": [(W, f, col) for f, col in EYE_PARTS], "L": L}
    if cap:
        mesh["C"] = cap_colours(W)
    lt = None
    if isinstance(light, str) and light == "rake":
        w = np.array([-0.85, -0.35, -0.25])
        lt = (0.40, 0.62 * w / np.linalg.norm(w), 0.6)
    elif light is not None:
        lt = light
    if passes:
        im, _, ps = likeness.render(mesh, cam, (0, 0, px, px), px=px, brows=brows, light=lt, passes=True)
        return im, ps
    im, _ = likeness.render(mesh, cam, (0, 0, px, px), px=px, brows=brows, light=lt)
    return im


def label(im, text, xy=(4, 3), fill=(30, 30, 30), font=None):
    d = ImageDraw.Draw(im)
    d.text(xy, text, fill=fill, font=font or FONT)
    return im


def grid(rows, cols_labels=None, rows_labels=None, title=None, pad=4, bg=(250, 250, 248), lw=150):
    """rows: list of lists of PIL images (same size)."""
    h, w = rows[0][0].size[1], rows[0][0].size[0]
    nr, nc = len(rows), max(len(r) for r in rows)
    top = (24 if title else 0) + (18 if cols_labels else 0)
    left = lw if rows_labels else 0
    S = Image.new("RGB", (left + nc * (w + pad), top + nr * (h + pad)), bg)
    d = ImageDraw.Draw(S)
    if title:
        d.text((6, 4), title, fill=(20, 20, 20), font=FONT_B)
    if cols_labels:
        for j, t in enumerate(cols_labels):
            d.text((left + j * (w + pad) + 4, top - 16), t, fill=(40, 40, 40), font=FONT)
    for i, r in enumerate(rows):
        if rows_labels:
            y = top + i * (h + pad) + 4
            for k, line in enumerate(str(rows_labels[i]).split("\n")):
                d.text((4, y + 14 * k), line, fill=(20, 20, 20), font=FONT)
        for j, im in enumerate(r):
            S.paste(im, (left + j * (w + pad), top + i * (h + pad)))
    return S
