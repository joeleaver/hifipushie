"""drv.py: the GNM driving test's core: heads (identity 170 -> GNM vertices), regions, the regional transplant that
makes B from A and a donor, renders / sheets, metrics. GNM frame (x left, y up, z forward), metres; renders via gnmc."""
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import gnmc
from hifipushie import gnm_controls as gcm, humanmacro as hm

G = Path(os.environ.get("G", "/mnt/data/hifipushie/gnmdrive"))
CASES = G / "cases"
HIDDEN = G / "hidden"
MM = 1000.0
IBH = gnmc.IB[:170].astype(np.float64)          # (170, V, 3)

# the test's regions: zones (gnm_controls.ZONES) a structured change lives in
REGIONS = {
    "skull": ["cranium", "forehead", "temples"],
    "jaw": ["jawline", "jaw_angle", "jowls", "under_chin", "chin", "pogonion", "parotid"],
    "jaw_full": ["jawline", "jaw_angle", "jowls", "under_chin", "parotid", "cheeks", "marionette"],   # "fluffy": fuller
    "chin": ["chin", "pogonion", "mentolabial_sulcus", "under_chin"],
    "mouth": ["upper_vermilion", "lower_vermilion", "vermilion_border_upper", "vermilion_border_lower", "cupids_bow",
              "mouth_corners", "philtrum", "upper_lip_skin", "mentolabial_sulcus"],
    "nose": ["dorsum", "radix", "bridge_walls", "nose_tip", "columella", "nostrils", "alae", "alar_crease"],
    "eyes": ["upper_lid", "lid_fold", "lower_lid", "inner_canthi", "outer_canthi", "tear_trough"],
    "brows": ["brows", "glabella", "upper_orbital_rim"],
    "cheeks": ["malar", "cheeks", "infraorbital", "lower_orbital_rim", "nasolabial"],
}
# per region, the macros whose change makes the difference NAMEABLE (donor choice: the largest of these, in sd)
REGION_MACROS = {
    "skull": ["cranium_width", "cranium_height", "head_depth", "forehead_slope"],
    "jaw": ["jaw_width", "jaw_square", "jaw_angle", "gonial_height", "chin_width", "under_chin"],
    "jaw_full": ["cheek_fullness", "under_chin", "neck_width", "jaw_width"],
    "chin": ["chin_height", "chin_projection", "chin_width"],
    "mouth": ["lip_projection", "lip_fullness", "mouth_width", "philtrum"],
    "nose": ["nose_projection", "nose_upturn", "nose_width", "bridge_height", "bridge_hump", "nose_length"],
    "eyes": ["eye_height", "eye_width", "eye_tilt", "eye_spacing", "eye_depth"],
    "brows": ["brow_ridge", "brow_height", "orbital_rim"],
    "cheeks": ["cheekbone_width", "cheek_fullness", "lower_orbit"],
}


def mask(zones_):
    Z = gcm.zones()
    m = np.zeros(gnmc.NV, bool)
    for z in zones_:
        m[Z[z]] = True
    return m


def verts(c):
    """GNM-frame vertices of a 170-comp identity (expression 0)."""
    return gnmc.TPL + np.tensordot(np.asarray(c, float), IBH, 1)


def transplant(cA, cD, region, amount=1.0, hold_w=1.0, ridge=0.05, near_mm=8.0):
    """B's identity: A with `region` moved toward the donor's (least-change in the 170 comps): the region's vertices
    match the donor's (relative to A) x amount, the face beyond near_mm of it held, a small ridge."""
    key = ("tp", region, hold_w, ridge, near_mm)
    if key not in _TP:
        from scipy.spatial import cKDTree
        Z = gcm.zones()
        R = mask(REGIONS[region])
        face = np.zeros(gnmc.NV, bool)
        face[Z["face"]] = True
        face[Z["neck"]] = True
        face[Z["cranium"]] = True
        T = gnmc.TPL
        d = cKDTree(T[R]).query(T)[0]
        O = face & ~R & (d > near_mm / MM)
        A_R = IBH[:, R, :].reshape(170, -1).T * MM
        A_O = IBH[:, O, :].reshape(170, -1).T * MM
        nr, no = R.sum(), O.sum()
        GR = A_R.T @ A_R / nr
        M = GR + hold_w * A_O.T @ A_O / no + ridge * np.eye(170)
        _TP[key] = np.linalg.solve(M, GR)      # dc = P (cD - cA) * amount  (the target lies in the basis' span)
    P = _TP[key]
    return np.asarray(cA, float) + amount * P @ (np.asarray(cD, float) - np.asarray(cA, float))


_TP: dict = {}


def zone_err(c, cB):
    """rms vertex distance (mm) per zone between two identities, + per region and the face."""
    D = np.tensordot(np.asarray(c, float) - np.asarray(cB, float), IBH, 1) * MM
    n = np.sqrt((D ** 2).sum(1))
    Z = gcm.zones()
    out = {k: float(np.sqrt((n[v] ** 2).mean())) for k, v in Z.items() if len(v) and k not in ("teeth_upper", "teeth_lower", "tongue")}
    for r, zs in REGIONS.items():
        m = mask(zs)
        out[f"R:{r}"] = float(np.sqrt((n[m] ** 2).mean()))
    return out


def macros(c):
    return hm.read(np.asarray(c, float)[:hm.K])


def macro_z(c):
    """macros in population sd (read gives sd already)"""
    return macros(c)


# ---------------------------------------------------------------- renders

VIEWS = {"front": 0.0, "3q": -35.0, "profile": -90.0}
FOCUS = {   # feature: (centre landmarks (68), half-size m, views)
    "eyes": ([36, 39, 42, 45, 27], 0.050, ["front", "3q", "profile"]),
    "brows": ([17, 21, 22, 26, 27], 0.055, ["front", "3q", "profile"]),
    "nose": ([27, 30, 31, 35, 33], 0.042, ["front", "3q", "profile"]),
    "mouth": ([48, 54, 51, 57, 33], 0.042, ["front", "3q", "profile"]),
    "chin_jaw": ([5, 8, 11, 57, 4, 12], 0.072, ["front", "3q", "profile"]),
    "cheeks": ([1, 15, 29, 31, 35], 0.078, ["front", "3q", "profile"]),
    "head": ([0, 16, 8, 27], 0.135, ["front", "3q", "profile"]),
}


def lms(V):
    return gnmc.WLM @ gnmc.world(V)


def render(c, view, px=300, half=0.13, centre=None, light=None):
    V = verts(c)
    return gnmc.render(V, view, px=px, half=half, centre=centre, light=light)


def focus_centre(cref, feature):
    L = lms(verts(cref))
    idx, half, _ = FOCUS[feature]
    return L[idx].mean(0), half


def view_imgs(c, cref, feature="head", px=300, light=None, views=None, fg=False):
    """renders of identity c at feature framing taken from cref (both heads framed alike: the TARGET's framing)."""
    if feature == "head":
        cen = lms(verts(cref))[[36, 45, 48, 54]].mean(0) + np.array([0, 0, -0.012])
        half = 0.135
    else:
        cen, half = focus_centre(cref, feature)
    vs = views or FOCUS[feature][2]
    if fg:
        out = [gnmc.render(verts(c), v, px=px, half=half, centre=cen, light=light, passes=True) for v in vs]
        return [o[0] for o in out], [np.isfinite(o[1]["zb"]) for o in out]
    return [gnmc.render(verts(c), v, px=px, half=half, centre=cen, light=light) for v in vs]


def outline(fg):
    """silhouette edge of a render's coverage mask (bool array)."""
    er = np.asarray(Image.fromarray(fg.astype(np.uint8) * 255).filter(ImageFilter.MinFilter(3))) > 0
    e = fg & ~er
    e = np.asarray(Image.fromarray(e.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(3))) > 0
    return e, fg


def trace(im_cur, fg_cur, fg_tgt):
    """the current render with the TARGET's silhouette (red) and the current's (green) traced over it (tracing paper)."""
    e1, _ = outline(fg_cur)
    e2, _ = outline(fg_tgt)
    a = np.asarray(im_cur.convert("RGB")).copy()
    a = (0.55 * a + 0.45 * 250).astype(np.uint8)
    a[e1] = [40, 170, 60]
    a[e2] = [215, 40, 40]
    return Image.fromarray(a)


def blend(a, b):
    return Image.blend(a.convert("RGB"), b.convert("RGB"), 0.5)


def sheet(rows, labels, cols, title, px):
    return gnmc.grid(rows, cols_labels=cols, rows_labels=labels, title=title, lw=120)
