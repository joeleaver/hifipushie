"""Reading the eye, the nose and the mouth from a render, and the least-change fit of the sliders. Part of the face sliders (faceslide.py has the overview)."""
from __future__ import annotations

import numpy as np

from .faceslide import fit_window, template

# ---- reading the eye from a render, and the least-change fit --------------------------------------------------------
def eye_camera(st: dict, yaw: float = 0.0) -> dict:
    """A fixed front camera at the subject's left eye (humanfit_views.project's dict), 0.5 m away, f 4000 px."""
    L = np.asarray(st["L"], float)
    return {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.5], "f": 4000.0, "size": [2000, 2000],
            "centre": (0.5 * (L[42] + L[45])).tolist(), "yaw": float(yaw)}


def _rows_of(st: dict, gids) -> np.ndarray:
    from . import onemesh
    gid = np.asarray(onemesh.asset()["gnm_exact"], int)[np.asarray(st["tpl"]["fid"])]
    row = {int(g): i for i, g in enumerate(gid) if g >= 0}
    return np.array([row[int(g)] for g in gids if int(g) in row], int)


def read_eyes(st: dict, cam: dict | None = None, px: int = 700) -> dict:
    """The subject's left eye read from a clay render through `cam` (default eye_camera): {"crease": mm from the
    upper lid margin up to the darkest line on the lid (2.5-12 mm over the pupil: the crease / the fold's edge;
    luminance, sub-pixel minimum), "crease_dark": lid luminance under it over the line's, "canthal_tilt": deg (the
    rim's inner -> outer corner as projected, + = outer up), "open": mm (the rim's upper -> lower edge over the
    pupil)}. Luminance reads the render (the loops and every slider show there); corners and opening read the
    rim's projected vertices."""
    from scipy.ndimage import map_coordinates

    from . import humanfit_views
    from . import likeness_render
    cam = cam or eye_camera(st)
    P = np.asarray(st["tpl"]["P"], float)
    L = np.asarray(st["L"], float)
    eye = 0.5 * (L[42] + L[45])
    rim = _rows_of(st, template()["rim"])
    rim = rim[np.linalg.norm(P[rim] - eye, axis=1) < 0.025]
    uv = humanfit_views.project(cam, P[rim])
    d = uv[int(np.argmax(uv[:, 0]))] - uv[int(np.argmin(uv[:, 0]))]
    mm_px = 0.001 * cam["f"] / float(cam["t"][2])  # px per mm at the eye's depth
    mid = 0.5 * (L[43] + L[44])
    c = humanfit_views.project(cam, mid[None])[0]
    near = np.abs(uv[:, 0] - c[0]) < 1.5 * mm_px
    top, bot = float(uv[near, 1].min()), float(uv[near, 1].max())
    out = {"canthal_tilt": float(np.degrees(np.arctan2(-d[1], abs(d[0])))), "open": (bot - top) / mm_px}
    box = (c[0] - 16 * mm_px, c[1] - 16 * mm_px, c[0] + 16 * mm_px, c[1] + 8 * mm_px)
    im, k = likeness_render.render(likeness_render.model_mesh_from_state(st), cam, box, px=px, brows=False)
    a = np.asarray(im.convert("RGB"), float) / 255.0
    Y = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    hs = np.arange(0.0, 14.0, 0.1)
    ys = (top - hs * mm_px - box[1]) * k
    prof = np.mean([map_coordinates(Y, [ys, (c[0] + dx * mm_px - box[0]) * k + 0 * hs], order=1)
                    for dx in (-0.6, 0.0, 0.6)], axis=0)
    win = np.flatnonzero((hs >= 2.5) & (hs <= 12.0))
    j = int(win[np.argmin(prof[win])])
    off = 0.0
    if 0 < j < len(hs) - 1:
        den = prof[j - 1] - 2 * prof[j] + prof[j + 1]
        off = float(np.clip(0.5 * (prof[j - 1] - prof[j + 1]) / den, -1, 1)) if abs(den) > 1e-12 else 0.0
    out["crease"] = float(hs[j] + 0.1 * off)
    under = prof[(hs >= 1.0) & (hs <= max(hs[j] - 1.0, 1.0))]
    out["crease_dark"] = float(np.median(under) / max(prof[j], 1e-6))
    return out


def nose_widths(img, P, mmpx: float) -> dict:
    """The nose's dorsal width read by SHADING, like with like on any picture lit by one light (the photo, or a render
    under the photo's fitted light): across the face (the detector's own axes) at the radix (MediaPipe 168) and the
    mid-dorsum (between 6 and 4), the luminance profile +-14 mm, smoothed over 1 mm; the dorsum is the bright band
    round the middle: its width at half the drop from its peak to the side walls' darkest (mm). The detector has
    no point on the dorsal lines: this is what an eye reads as the nose's width partway down."""
    from scipy.ndimage import gaussian_filter1d, map_coordinates

    from .likeness_eyes import frame
    P = np.asarray(P, float)
    a = np.asarray(img.convert("RGB"), float) / 255.0
    Y = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    ex, _ = frame(P)
    out = {}
    for name, c in (("radix_w", P[168]), ("dorsum_w", 0.5 * (P[6] + P[4]))):
        t = np.arange(-14.0, 14.01, 0.1)
        pts = c[None] + (t / mmpx)[:, None] * ex[None]
        prof = gaussian_filter1d(map_coordinates(Y, [pts[:, 1], pts[:, 0]], order=1), 1.0 / 0.1 / 2.355)
        mid = np.abs(t) <= 3.0
        j = int(np.flatnonzero(mid)[np.argmax(prof[mid])])
        peak = prof[j]
        edges = []
        for sgn in (-1, 1):
            k = np.arange(j, len(t)) if sgn > 0 else np.arange(j, -1, -1)
            low = float(prof[k].min())
            half = peak - 0.5 * (peak - low)
            hit = k[np.argmax(prof[k] <= half)] if (prof[k] <= half).any() else k[-1]
            edges.append(t[hit])
        out[name] = float(edges[1] - edges[0])
    return out


def read_mouth(st: dict, cam: dict | None = None, px: int = 500) -> dict:
    """The lips read from a clay render's depth pass through a front camera at the mouth: {"upper_proj", "lower_proj":
    mm the upper / lower vermilion's middle stands in front of the subnasale (lm 33), sampled over 1.5 mm}."""
    from . import humanfit_views
    from . import likeness_render
    L = np.asarray(st["L"], float)
    c3 = 0.5 * (L[51] + L[57])
    cam = cam or {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.5], "f": 6000.0, "size": [2000, 2000],
                  "centre": c3.tolist(), "yaw": 0.0}
    mm_px = 0.001 * cam["f"] / float(cam["t"][2])
    c = humanfit_views.project(cam, c3[None])[0]
    box = (c[0] - 30 * mm_px, c[1] - 30 * mm_px, c[0] + 30 * mm_px, c[1] + 20 * mm_px)
    _, k, ps = likeness_render.render(likeness_render.model_mesh_from_state(st), cam, box, px=px, brows=False, passes=True)
    zb = ps["zb"]

    def z_at(p):
        q = (humanfit_views.project(cam, np.asarray(p)[None])[0] - box[:2]) * k
        r = max(1, int(round(0.75 * mm_px * k)))
        y, x = int(round(q[1])), int(round(q[0]))
        w = zb[max(y - r, 0):y + r + 1, max(x - r, 0):x + r + 1]
        return float(np.median(w[np.isfinite(w)])) if np.isfinite(w).any() else float("nan")
    z0 = z_at(L[33])
    return {"upper_proj": 1000 * (z0 - z_at(0.4 * L[62] + 0.6 * L[51])),
            "lower_proj": 1000 * (z0 - z_at(0.5 * L[66] + 0.5 * L[57]))}


def fit(base: dict, targets: dict, names, read=None, hold: float = 0.15, iters: int = 4, step: float = 0.15,
        log=None, on_base: bool = False) -> dict:
    """The least change of the named sliders (both eyes together) that brings the read measures to their targets:
    targets {measure: (value, tolerance)}; read(state) -> {measure: value} (default read_eyes). Gauss-Newton on
    sum(((m - target) / tol)^2) + hold * sum((x - x0)^2), the Jacobian by central differences THROUGH the built head
    (humanfit.state: GNM's vertices, the loops' and every op after the sliders), x held to fit_window (centred on body.sex).
    Returns {"sliders", "before", "after", "steps"}."""
    import copy

    from . import humanfit
    read = read or read_eyes
    names = list(names)
    b0 = copy.deepcopy(base)
    sl0 = dict((b0.get("head") or {}).get("sliders") or {})
    x0 = np.array([float(np.mean(sl0.get(n, 0.0))) for n in names])
    sex = (b0.get("body") or {}).get("sex", 0.5)
    sex = {"female": 0.0, "male": 1.0}.get(sex, 0.5) if isinstance(sex, str) else float(sex)
    lo_, hi_ = np.array([fit_window(n, sex) for n in names]).T  # (centred on the head's sex: SEX_OFFSET)
    keys = list(targets)
    t = np.array([targets[k][0] for k in keys], float)
    tol = np.array([targets[k][1] for k in keys], float)

    def with_x(x):
        b = copy.deepcopy(b0)
        s = dict(sl0)
        s.update({n: round(float(v), 4) for n, v in zip(names, x)})
        b.setdefault("head", {})["sliders"] = s
        return b

    def r_of(x):
        m = read(with_x(x)) if on_base else read(humanfit.state(with_x(x)))  # (on_base: read(base), e.g. a matched pair)
        return np.array([m[k] for k in keys], float), m

    def cost(m_, x_):
        return float(np.sum(((m_ - t) / tol) ** 2) + hold * np.sum((x_ - x0) ** 2))

    x = x0.copy()
    m, before = r_of(x)
    steps = []
    for _ in range(iters):
        Jc = np.zeros((len(keys), len(names)))
        for j in range(len(names)):
            e = np.zeros(len(names))
            e[j] = step
            Jc[:, j] = (r_of(x + e)[0] - r_of(x - e)[0]) / (2 * step)
        A = Jc / tol[:, None]
        dx = -np.linalg.solve(A.T @ A + hold * np.eye(len(names)), A.T @ ((m - t) / tol) + hold * (x - x0))
        xn = np.clip(x + dx, lo_, hi_)
        mn, _ = r_of(xn)
        if cost(mn, xn) > cost(m, x):
            xn = np.clip(x + 0.5 * dx, lo_, hi_)
            mn, _ = r_of(xn)
            if cost(mn, xn) > cost(m, x):  # no better (a noisy reading, e.g. a detector): keep what we had
                steps.append({"x": [round(float(v), 4) for v in x], "miss": [round(float(v), 3) for v in (m - t) / tol],
                              "stopped": "no step improved"})
                break
        steps.append({"x": [round(float(v), 4) for v in xn], "miss": [round(float(v), 3) for v in (mn - t) / tol]})
        if log:
            log(steps[-1])
        x, m = xn, mn
        if np.all(np.abs(dx) < 0.01):
            break
    return {"sliders": {n: round(float(v), 4) for n, v in zip(names, x)}, "before": before,
            "after": dict(zip(keys, m.tolist())), "steps": steps}
