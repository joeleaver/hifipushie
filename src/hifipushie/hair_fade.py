"""The short-hair EDGE FADE, painted into the head's skin (sh7): what game artists do for short back and sides.

Mesh hair (cap, shells, hairline cards) stops where the hair is long enough to have volume. Below that, at the nape,
the sideburns and round the ears, the hair thins into the skin over a few cm: short sparse cut hairs and the grey
shadow of hair under the skin. That transition is a value and fine-hair gradient in the HEAD's albedo, not geometry.

`hair.export.fade` (spec key; the export writes the map beside the hair GLBs and the look / bake lays it on the skin):
  {"edge": [[fa, el], ...]   the painted hair's edge (density 0.5) by angle from the front (deg, both sides alike)
                             and elevation round the scalp centre (deg). Above it the paint is full (under the cap).
   "fade_mm": [[fa, mm], ...] the fall-off length below the edge (density 1 -> 0), by angle from the front
   "trim": [[fa, el], ...]   the mesh hair (cap and shells) cut away below this elevation (soft over trim_soft mm):
                             the mesh's edge moved up to meet the fade, not the bare skin. Optional; "trim_breakup_mm"
                             makes that edge ragged (a 2D noise moves it by about that much).
   "fa_min": 55              no paint nearer the front than this (the face / forehead hairline stays the mesh's)
   "color": "#4a4642", "grey": "#8a8580", "grey_share": 0.35   the cut hairs (salt and pepper)
   "shadow": "#6a625c", "shadow_opacity": 0.45                 the hair under the skin (a smooth tint)
   "density_gamma": 1.8 (cut hairs thin out faster than the shadow), "hair_opacity": 0.85, "spacing_mm": 0.55, "length_mm": [1.0, 3.5], "width_mm": 0.12, "slant": 0.35, "seed": 0}
The map is in scalp-chart coordinates (u = azimuth / 360, v = elevation EL0..EL1, row 0 = the top), with the head's
skull radius (ears opened away) beside it, so a shader paints only the skull's own skin, never the ear standing off it.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

EL0, EL1 = -75.0, 45.0  # deg: the map's elevation span (the fade never reaches the crown or below the jaw)
RES = 0.1  # deg per texel (~0.16 mm at a 9 cm head radius)
EAR_CLEAR = 0.003  # m: texels whose surface stands more than this off the opened skull are the ear: no paint


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _curve(pts, fa):
    p = np.asarray(sorted(pts), float)
    return np.interp(fa, p[:, 0], p[:, 1])


def _hex(c):
    c = c.lstrip("#")
    return np.array([int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def skull_radius(sc) -> np.ndarray:
    """The scalp's rays with the ears opened away (grey opening along the azimuth, as hair.ear finds them): (360/STEP,
    n_el) radius of the skull's own skin."""
    from .hair import EAR_OPEN
    return ndimage.grey_opening(np.asarray(sc.R, float), size=(EAR_OPEN, 1), mode="wrap")


def trim_mask(o: dict, R: float, el_rows: np.ndarray, W: int) -> np.ndarray | None:
    """(H, W) 0..1 keep-mask for a chart (rows = elevation el_rows, columns = azimuth (j + .5) / W x 360): 0 below the
    spec's trim line, rising to 1 over trim_soft mm above it."""
    if not o or not o.get("trim"):
        return None
    az = (np.arange(W) + 0.5) / W * 360.0
    fa = np.abs(((az + 180.0) % 360.0) - 180.0)
    tl = _curve(o["trim"], fa)
    soft = float(o.get("trim_soft_mm", 3.0)) / 1000.0
    d = np.radians(el_rows[:, None] - tl[None, :]) * R  # m above the trim line
    br = float(o.get("trim_breakup_mm", 0.0)) / 1000.0
    if br > 0:  # a ragged edge, not a ruled line: the threshold moved by a smooth 2D noise (~2 mm features)
        rng = np.random.default_rng(int(o.get("seed", 0)) + 7)
        mv = np.radians(abs(el_rows[1] - el_rows[0])) * R if len(el_rows) > 1 else 1e-4
        mu = np.radians(360.0 / W) * R
        nz = ndimage.gaussian_filter(rng.standard_normal(d.shape), (0.002 / mv, 0.0012 / mu), mode="wrap")
        d = d + br * nz / max(float(nz.std()), 1e-9)
    return _ss(d / max(soft, 1e-6)).astype(np.float32)


def _skull_grid(sc, az, el) -> np.ndarray:
    """The skull's radius (m) on the map's grid (rows = el, columns = az), bilinear on the scalp's 2 deg rays."""
    from scipy.ndimage import map_coordinates
    Rs = skull_radius(sc)
    ia = (az - sc.A[0]) / sc.STEP
    ie = (np.clip(el, sc.EL[0], sc.EL[1]) - sc.EL[0]) / sc.STEP
    Rw = np.concatenate([Rs, Rs[:1]], 0)  # wrap
    # map_coordinates takes coordinates in ARRAY-AXIS order: Rw's axis 0 is azimuth (sh7a passed them reversed)
    return map_coordinates(Rw, np.meshgrid(ia, ie), order=1, mode="nearest")


def build(sc, o: dict) -> dict:
    """The fade map: {"rgba": (H, W, 4) float sRGB straight alpha, "skull": (H, W) m, "el": [EL0, EL1], "C": centre}."""
    rng = np.random.default_rng(int(o.get("seed", 0)))
    W, H = int(round(360.0 / RES)), int(round((EL1 - EL0) / RES))
    az = (np.arange(W) + 0.5) * RES
    el = EL1 - (np.arange(H) + 0.5) * RES
    fa = np.abs(((az + 180.0) % 360.0) - 180.0)
    R = float(np.median(sc.R))
    mm = np.radians(RES) * R * 1000.0  # mm per texel up the head
    edge = _curve(o["edge"], fa)
    fl = _curve(o.get("fade_mm", [[0, 20.0], [180, 20.0]]), fa)
    below = np.radians(edge[None, :] - el[:, None]) * R * 1000.0  # mm below the edge (negative: above it)
    mu = np.radians(RES) * R * 1000.0  # mm per texel round the head at the equator
    skull = _skull_grid(sc, az, el)
    mm_loc = np.full((H, 1), mm)
    if o.get("surface_mm"):  # (sh8) mm measured ON the skin (arc length down the skull map), not on a sphere of the
        # median radius: down the neck r grows fast with falling elevation, and sh8a's 40 "mm" nape fade ran ~6 cm down
        # the neck as long streaks
        dth = np.radians(RES)
        dr = np.gradient(skull, axis=0) / dth
        mm_loc = np.sqrt(skull ** 2 + dr ** 2) * dth * 1000.0  # (H, W) mm per texel row
        s = np.cumsum(mm_loc, 0) - 0.5 * mm_loc
        re = np.clip((EL1 - edge) / RES - 0.5, 0, H - 1)
        r0 = np.floor(re).astype(int)
        r1 = np.minimum(r0 + 1, H - 1)
        cols = np.arange(W)
        se = s[r0, cols] + (re - r0) * (s[r1, cols] - s[r0, cols])
        below = s - se[None, :]

    def noise(seed, f_el_mm, f_az_mm):  # (sh8) a smooth unit-variance 2D noise, features ~ f mm (cheap: drawn coarse)
        k = 4
        g = np.random.default_rng(int(o.get("seed", 0)) + seed).standard_normal((H // k + 1, W // k + 1))
        g = ndimage.gaussian_filter(g, (f_el_mm / mm / k, f_az_mm / mu / k), mode="wrap")
        g = ndimage.zoom(g / max(float(g.std()), 1e-9), k, order=1)[:H, :W]
        return g
    eb = float(o.get("edge_breakup_mm", 0.0))
    if eb > 0:  # (sh8) a ragged painted edge: the threshold moved by a noise, not a ruled curve
        below = below + eb * noise(11, 1.5, 1.2)
    w = 1.0 - _ss((below + 0.5 * fl[None, :]) / np.maximum(fl[None, :], 1e-3))  # 0.5 at the edge, 1 -> 0 over fade_mm
    fmin = float(o.get("fa_min", 55.0))
    fa_e = fa[None, :] + float(o.get("front_breakup_deg", 0.0)) * (noise(23, 2.5, 1.5) if o.get("front_breakup_deg") else 0.0)
    w = w * _ss((fa_e - fmin) / float(o.get("front_soft_deg", 10.0)))  # (sh8) the sideburn's front: dense -> sparse, ragged
    cl = float(o.get("clump", 0.0))
    if cl > 0:  # (sh8) hair grows in patches: the fall-off's middle modulated by a ~3 mm noise (texture, not a flat
        # decal); full density (under the mesh) and bare skin stay as they are: no bald holes in the dense part
        w = np.clip(w + cl * noise(37, 3.0, 2.0) * 4.0 * w * (1.0 - w), 0.0, 1.0)
    w = w.astype(np.float32)
    # the cut hairs: short strokes along the flow, their number and length falling with the density
    sp = float(o.get("spacing_mm", 0.55))
    cos_el = np.maximum(np.cos(np.radians(el)), 0.2)
    area_px = (sp / mm) ** 2  # texels per hair at full density (up the head; across scaled by cos el below)
    p = w ** float(o.get("density_gamma", 1.8)) * cos_el[:, None] / area_px  # (sparse long before the shadow ends)
    keep = rng.random(w.shape, dtype=np.float32) < np.minimum(p, 1.0)
    ys, xs = np.nonzero(keep)
    wt = w[ys, xs]
    l0, l1 = (float(x) for x in o.get("length_mm", [1.0, 3.5]))
    L = (l0 + (l1 - l0) * wt) * (0.7 + 0.6 * rng.random(len(ys))) / mm_loc[ys, np.minimum(xs, mm_loc.shape[1] - 1)]  # texels
    fa_s = fa[xs]
    side = np.sign(((az[xs] + 180.0) % 360.0) - 180.0)  # + his left
    sl = float(o.get("slant", 0.35))
    # the flow: down; at the sides back toward the nape, at the nape in toward the middle
    dx = side * np.where(fa_s < 140.0, sl, -sl * _ss((fa_s - 140.0) / 30.0) * 0.6) + rng.normal(0, 0.15, len(ys))
    dy = np.ones(len(ys))
    n = np.hypot(dx, dy)
    dx, dy = dx / n, dy / n
    cov = np.zeros(w.shape, np.float32)
    grey = np.zeros(w.shape, np.float32)
    isg = rng.random(len(ys)) < float(o.get("grey_share", 0.35))
    steps = int(np.ceil(L.max())) + 1 if len(L) else 0
    for s in range(steps):
        t = s / max(steps - 1, 1)
        on = t * steps <= L + 0.5
        yy = np.clip((ys + dy * t * steps).astype(int), 0, H - 1)[on]
        xx = ((xs + dx * t * steps / cos_el[np.clip(ys, 0, H - 1)]).astype(int) % W)[on]
        fade_tip = (1.0 - 0.6 * t)  # a cut hair thins toward its tip
        np.maximum.at(cov, (yy, xx), fade_tip)
        np.maximum.at(grey, (yy[isg[on]], xx[isg[on]]), fade_tip)
    wd = float(o.get("width_mm", 0.12)) / mm
    if wd > 0.3:
        cov = ndimage.gaussian_filter(cov, 0.4 * wd)
        grey = ndimage.gaussian_filter(grey, 0.4 * wd)
    a_h = np.clip(cov * float(o.get("hair_opacity", 0.85)), 0, 1)
    g_share = np.where(cov > 1e-4, np.clip(grey / np.maximum(cov, 1e-4), 0, 1), 0.0)
    hair_col = (1 - g_share)[..., None] * _hex(o.get("color", "#4a4642")) + g_share[..., None] * _hex(o.get("grey", "#8a8580"))
    a_s = float(o.get("shadow_opacity", 0.45)) * w ** float(o.get("shadow_gamma", 1.3))
    sh = _hex(o.get("shadow", "#6a625c"))
    a = a_s + a_h - a_s * a_h
    rgb = (sh[None, None] * (a_s * (1 - a_h))[..., None] + hair_col * a_h[..., None]) / np.maximum(a, 1e-6)[..., None]
    rgba = np.concatenate([np.clip(rgb, 0, 1), a[..., None]], -1).astype(np.float32)
    return {"rgba": rgba, "skull": skull, "el": [EL0, EL1], "C": [float(x) for x in sc.C], "density": w,
            "hairs": int(len(ys))}


def chart_coords(fm: dict, P: np.ndarray):
    """(n, 3) surface points (model = Blender coords) -> (row, col, r): the fade map's continuous texel coordinates
    (row 0 = the map's top, EL1; col 0 = azimuth 0 = the front, -Y; +X = his left = 90 deg) and the distance from the
    centre. The same mapping as blender_cards.skin_fade's node tree (u = azimuth / 360, v = (el - el0) / (el1 - el0))."""
    H, W = fm["rgba"].shape[:2]
    el0, el1 = (float(x) for x in fm["el"])
    q = np.asarray(P, float) - np.asarray(fm["C"], float)
    r = np.linalg.norm(q, axis=1)
    az = np.degrees(np.arctan2(q[:, 0], -q[:, 1])) % 360.0
    el = np.degrees(np.arcsin(np.clip(q[:, 2] / np.maximum(r, 1e-9), -1, 1)))
    row = (el1 - el) / (el1 - el0) * H - 0.5
    col = az / 360.0 * W - 0.5
    return row, col, r


def sample(fm: dict, P: np.ndarray):
    """The fade at surface points: (rgba (n, 4) sRGB straight alpha, bilinear; alpha 0 off the map's elevation span and
    where the point stands off the skull's own skin by more than EAR_CLEAR (the ear))."""
    from scipy.ndimage import map_coordinates
    row, col, r = chart_coords(fm, P)
    rgba = np.asarray(fm["rgba"], np.float32)
    H, W = rgba.shape[:2]
    wrap = np.concatenate([rgba[:, -1:], rgba, rgba[:, :1]], 1)  # azimuth wraps; elevation clips (Blender CLIP)
    xy = np.stack([row, col + 1.0])  # (axis 0 = rows = elevation, axis 1 = columns = azimuth): the sh7a trap
    out = np.stack([map_coordinates(wrap[..., k], xy, order=1, mode="constant", cval=0.0) for k in range(4)], -1)
    sk = np.concatenate([fm["skull"][:, -1:], fm["skull"], fm["skull"][:, :1]], 1)
    skull = map_coordinates(np.asarray(sk, np.float64), np.stack([np.clip(row, 0, H - 1), col + 1.0]), order=1, mode="nearest")
    out[:, 3] *= (r < skull + EAR_CLEAR) & (row >= -0.5) & (row <= H - 0.5)
    return np.clip(out, 0, 1)


def bake_into(lin: np.ndarray, P: np.ndarray, fm: dict, strength: float = 1.0):
    """(n, 3) LINEAR base colours at surface points P -> the faded colours and the alpha used: mix(base, fade.rgb,
    fade.a x strength) in linear light, as blender_cards.skin_fade mixes it (the image node decodes sRGB)."""
    s = sample(fm, P)
    a = s[:, 3:4] * float(strength)
    rgb = np.where(s[:, :3] <= 0.04045, s[:, :3] / 12.92, ((s[:, :3] + 0.055) / 1.055) ** 2.4)
    return np.asarray(lin, float) * (1 - a) + rgb * a, a[:, 0]


def write(fm: dict, stem: str) -> dict:
    """<stem>_skin_fade.png (RGBA, sRGB) and <stem>_skin_fade_skull.png (16-bit: radius (m) x 10000) + the note."""
    from PIL import Image
    Image.fromarray((np.clip(fm["rgba"], 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(f"{stem}_skin_fade.png")
    Image.fromarray(np.clip(fm["skull"] * 10000.0, 0, 65535).astype(np.uint16)).save(f"{stem}_skin_fade_skull.png")
    return {"file": f"{stem}_skin_fade.png".rsplit("/", 1)[-1], "skull": f"{stem}_skin_fade_skull.png".rsplit("/", 1)[-1],
            "centre": fm["C"], "el": fm["el"], "skull_scale": 10000.0, "ear_clear": EAR_CLEAR,
            "use": "head albedo: mix(base, rgb, alpha) where |p - centre| < skull(u, v) + ear_clear; u = azimuth / 360 "
                   "(0 = front -Y, 90 = +X), v = (el - el0) / (el1 - el0)"}
