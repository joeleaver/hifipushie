"""The upper lid's FOLD (eyedetail, 2026-10-09; Joe: "that eye detail work we did still doesn't get us the creases we
need"). GNM's lids have no fold of their own (faceatlas: crease height R2 0.13 on the identity; fold overhang 0.70), and
a soft groove morph lands on down-facing skin in shadow. A real lid, front to back from the lashes up: the pretarsal
PLATFORM (the skin over the tarsus, facing forward / up), then the supratarsal CREASE, a tight invagination where the
levator's fibres pull the skin in (~0.5-1 mm wide, deep enough to hold its own shadow), then the preseptal skin and
fat ROLLING over it (the fold), up to the brow.

Measures (photo-anthropometry, primary gaze, mm on the face's axes, the iris 11.7 mm across as the scale where a
photo has nothing better; `read_lid`):
  tps    tarsal platform show: lash line -> the visible fold line (what the eye sees as "the crease" when open)
  bfs    brow fat span: the fold line -> the brow's lower edge
  line   the fold line's darkness (valley depth over its neighbours, 0..1) and width (FWHM, mm)
Norms (Price et al. 2009, Plast Reconstr Surg 124:615, 164 adults 20-80, via the review table in PMC5665901; crease
height = clinical margin-crease distance, measured in downgaze): Caucasian crease height men 6.2, women 7.5 mm;
pretarsal skin height (platform show) men 2.0, women 3.3; African American crease 7.2 / 7.7, platform 3.1 / 3.6. A
celebrity sample (38 photographs) read platform show women 3.9, men 2.5 mm. Platform show falls with age (the
preseptal skin descends: dermatochalasis), the crease rises (levator disinsertion).

Geometry (`blobs`, mod `sdf.mod_fold`): a modifier on the body's field along each upper lid's crease line (the opening's
own rim, lifted by the crease height in the front plane and seated on the skin: no landmark lines), pushing the skin
along its normal by a profile across the line: the platform a little in (`platform`), the crease a narrow deep
invagination (`crease_depth`, `crease_width`), the fold's roll out over it (`fold_overhang`, `fold_width`, peaking
`fold_drop` above the line: a larger overhang hangs lower and hides the platform). Parameters per lid end
(`inner` / `outer` scale the crease height, the platform show tapering into both canthi). In the field, so it is
meshed at the face stage's 0.5 mm (scene.refine_box) and baked into the export's normal / AO maps; the one mesh's
quads follow its overhang (rows ~0.6 mm there with the lid loops).
"""
from __future__ import annotations

import numpy as np

MM = 0.001
IRIS_MM = 11.7  # the visible iris' mean diameter (adults), the scale of a photo with nothing better

# MediaPipe 478: (subject's right, left)
UPPER = ((33, 246, 161, 160, 159, 158, 157, 173, 133), (263, 466, 388, 387, 386, 385, 384, 398, 362))
BROW_LOW = ((46, 53, 52, 65, 55), (276, 283, 282, 295, 285))
INNER, OUTER = (133, 362), (33, 263)
IRIS_RIM = ((469, 470, 471, 472), (474, 475, 476, 477))
IRIS_C = (468, 473)

NORMS = {  # mm (Price et al. 2009; see the module docstring)
    "crease_height": {"male": 6.2, "female": 7.5},
    "platform_show": {"male": 2.0, "female": 3.3},
}


def _lum(img) -> np.ndarray:
    a = np.asarray(img.convert("RGB"), float) / 255.0
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def _bilinear(L, x, y):
    h, w = L.shape
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (L[y0, x0] * (1 - fx) * (1 - fy) + L[y0, x0 + 1] * fx * (1 - fy) + L[y0 + 1, x0] * (1 - fx) * fy
            + L[y0 + 1, x0 + 1] * fx * fy)


def _interp_curve(P, idx, t, ex, ey, o):
    """A landmark contour's height (along ey) at position t (along ex), both relative to origin o."""
    Q = P[list(idx)] - o
    u, v = Q @ ex, Q @ ey
    k = np.argsort(u)
    return float(np.interp(t, u[k], v[k]))


def _hsv(rgb):
    import colorsys
    return np.array(colorsys.rgb_to_hsv(*np.clip(rgb, 0, 1)))


def _line_colour(A, base, ey, strip, ex, lid, up, k, i) -> dict:
    """The fold line's colour against the skin round it (a shadow keeps the skin's hue and saturation and drops
    its value; paint shifts hue / saturation): value ratio, saturation and hue differences of the line (its own
    0.15 mm) to the skin 1.5-2.5 mm either side; and the shading either side: the band 0.3-1.3 mm above (the fold's
    underside) and below (the platform) over the skin 2.5-4 mm above / below."""
    def rgb(lo_mm, hi_mm):
        u = up[(up >= up[i] + lo_mm) & (up <= up[i] + hi_mm)]
        if not len(u):
            return np.full(3, np.nan)
        hh = lid - u / k
        vals = [np.stack([_bilinear(A[..., c], *(base + w * ex + hh[:, None] * ey).T) for c in range(3)], 1)
                for w in strip]
        return np.mean(np.concatenate(vals), 0)
    line = _hsv(rgb(-0.15, 0.15))
    skin = _hsv(0.5 * (rgb(1.5, 2.5) + rgb(-2.5, -1.5)))
    above, below = _hsv(rgb(0.3, 1.3)), _hsv(rgb(-1.3, -0.3))
    far_up, far_dn = _hsv(rgb(2.5, 4.0)), _hsv(rgb(-4.0, -2.5))
    dh = (line[0] - skin[0] + 0.5) % 1.0 - 0.5
    return {"line_v": round(float(line[2] / max(skin[2], 1e-6)), 3), "line_ds": round(float(line[1] - skin[1]), 3),
            "line_dh": round(float(dh * 360), 1), "above_v": round(float(above[2] / max(far_up[2], 1e-6)), 3),
            "below_v": round(float(below[2] / max(far_dn[2], 1e-6)), 3)}


def read_lid(img, P, mmpx: float | None = None, fractions=(0.25, 0.5, 0.75), lash_mm: float = 1.2,
             reach_mm: float = 14.0) -> list:
    """Per eye (subject's right, left), per column (fraction inner -> outer corner): {"tps", "bfs", "dark", "width"}
    (mm; dark 0..1) from a picture and its 478 detector points P (pixels). The luminance profile up the lid along the
    face's own up axis, averaged over a 1 mm strip; the fold line = the strongest valley 1.2-14 mm over the lash line
    (dark against the brighter skin 1.5 mm either side), past the lashes' own dark band."""
    from .likeness_eyes import frame
    P = np.asarray(P, float)[:, :2]
    L = _lum(img)
    A = np.asarray(img.convert("RGB"), float) / 255.0
    ex, ey = frame(P)  # ex across, ey DOWN the face
    ex, ey = np.asarray(ex, float), np.asarray(ey, float)
    out = []
    for s in (0, 1):
        if mmpx is None:
            r = np.mean([np.linalg.norm(P[i] - P[IRIS_C[s]]) for i in IRIS_RIM[s]])
            k = IRIS_MM / (2 * r)
        else:
            k = mmpx
        pi, po = P[INNER[s]], P[OUTER[s]]
        o = pi
        span = float((po - pi) @ ex)
        cols = []
        for f in fractions:
            t = f * span
            lid = _interp_curve(P, UPPER[s], t, ex, ey, o)
            brow = _interp_curve(P, BROW_LOW[s], t, ex, ey, o)
            up = np.arange(0.0, reach_mm, 0.05)  # mm over the lash line
            hh = lid - up / k  # (ey points down: up the face is -ey)
            strip = np.linspace(-0.5, 0.5, 9) / k
            prof = np.mean([_bilinear(L, *(o + (t + w) * ex + hh[:, None] * ey).T) for w in strip], 0)
            prof = np.convolve(prof, np.ones(3) / 3, mode="same")
            brow_mm = (lid - brow) * k
            lo = int(lash_mm / 0.05)
            hi = int(min(reach_mm, brow_mm - 1.0) / 0.05)
            if hi <= lo + 10:
                cols.append({"tps": np.nan, "bfs": np.nan, "dark": 0.0, "width": np.nan, "brow": round(brow_mm, 2)})
                continue
            nb = int(1.5 / 0.05)
            best = (0.0, None)
            for i in range(lo, hi):
                a, b = prof[max(i - nb, 0):i], prof[i + 1:i + 1 + nb]
                if len(a) == 0 or len(b) == 0:
                    continue
                if prof[i] > prof[max(i - 1, 0)] or prof[i] > prof[min(i + 1, len(prof) - 1)]:
                    continue
                dark = (min(a.max(), b.max()) - prof[i]) / max(min(a.max(), b.max()), 1e-6)
                if dark > best[0]:
                    best = (dark, i)
            if best[1] is None:
                cols.append({"tps": np.nan, "bfs": np.nan, "dark": 0.0, "width": np.nan, "brow": round(brow_mm, 2)})
                continue
            i = best[1]
            ref = min(prof[max(i - nb, 0):i].max(), prof[i + 1:i + 1 + nb].max())
            half = prof[i] + 0.5 * (ref - prof[i])
            j0, j1 = i, i
            while j0 > 0 and prof[j0] < half:
                j0 -= 1
            while j1 < len(prof) - 1 and prof[j1] < half:
                j1 += 1
            col = {"tps": round(up[i], 2), "bfs": round(brow_mm - up[i], 2), "dark": round(float(best[0]), 3),
                   "width": round((j1 - j0) * 0.05, 2), "brow": round(brow_mm, 2)}
            col.update(_line_colour(A, o + t * ex, ey, strip, ex, lid, up, k, i))
            cols.append(col)
        out.append(cols)
    return out


# ---- geometry ----------------------------------------------------------------------------------------------------

# the fold's parameters, mm (base.head.fold = true | {...}); the defaults by sex (body.sex 1 male .. 0 female)
KEYS = ("crease_height", "crease_depth", "crease_width", "fold_overhang", "fold_width", "platform", "inner", "outer",
        "start", "end")
DEFAULTS = {"crease_depth": 1.0, "crease_width": 0.8, "fold_overhang": 0.4, "fold_width": 1.6, "platform": 0.15,
            "inner": 0.8, "outer": 0.85, "start": 0.06, "end": 0.96}


def config(spec: dict) -> dict | None:
    """The fold's parameters (mm) if the spec's head asks for it (base.head.fold), else None. crease_height: the
    VISIBLE fold line over the lash line in front view (what read_lid measures; default women 4.0, men 3.0: the
    pretarsal show of Price et al. plus the fold edge's own thickness); fold_overhang: the roll's height over the
    skin round it; inner / outer: the crease height at the inner / outer third over the middle's."""
    b = spec.get("base") or {}
    hd = b.get("head") or {}
    f = hd.get("fold")
    if not f:
        return None
    f = {} if f is True else dict(f)
    bad = set(f) - set(KEYS)
    if bad:
        from .spec import SpecError
        raise SpecError(f"base.head.fold: unknown keys {sorted(bad)} (have {', '.join(KEYS)})")
    sex = float(np.clip((b.get("body") or {}).get("sex", 1.0), 0, 1))
    out = {**DEFAULTS, "crease_height": 4.0 - 1.0 * sex}
    out.update({k: float(v) for k, v in f.items()})
    if hd.get("slider_mode") == "coupled" and "fold_overhang" in f:  # the identity carries what GNM can express of it
        out["fold_overhang"] = float(f["fold_overhang"]) * (1.0 - coupled_share())
    return out


def coupled_share() -> float:
    """The share of fold overhang GNM's identity expresses (faceatlas R2 of fold_overhang, ~0.70)."""
    from . import faceatlas
    t = faceatlas.table()
    return float(np.clip(t["r2"][t["index"]["fold_overhang"]], 0, 1)) if "fold_overhang" in t["index"] else 0.0


def identity_change(head: dict) -> np.ndarray | None:
    """(120,) the identity move for base.head.fold.fold_overhang in "coupled" slider mode (faceatlas.direction: the
    conditional mean given the attribute, so the brow ridge and eye depth come along as the population couples them,
    r 0.74): R2 of the asked overhang through the identity, the rest is the fold's own roll (config). The asked value
    is a CHANGE of the atlas' attribute (mm)."""
    f = head.get("fold")
    if not (isinstance(f, dict) and "fold_overhang" in f and head.get("slider_mode") == "coupled"):
        return None
    from . import faceatlas
    return faceatlas.direction({"fold_overhang": float(f["fold_overhang"]) * coupled_share()},
                               head.get("slider_hold") or ())


def profile(t: np.ndarray, pr: dict, j: np.ndarray) -> np.ndarray:
    """The skin's move along its normal (m, + = out) at signed distance t (m) across the crease line, up the lid +:
    the platform a little in below (fading out toward the lashes), the crease a narrow Gaussian invagination, the
    fold's roll out just over it. Per sample j's parameters (pr arrays)."""
    G, sg = pr["G"][j], pr["sg"][j]
    O, so = pr["O"][j], pr["so"][j]
    Pl, ph = pr["Pl"][j], pr["ph"][j]
    groove = -G * np.exp(-0.5 * (t / sg) ** 2)
    # (the roll rises from the crease line itself: a symmetric bump there half filled the crease)
    ur = np.clip(t / so, 0, 1)  # (a soft shoulder: a steep one caught the key light as a bright ridge)
    roll = O * ur * ur * (3 - 2 * ur) * np.exp(-0.5 * ((t - 0.9 * so) / so) ** 2)
    x = np.clip(-t / np.maximum(ph, 1e-6), 0, 1)
    plat = -Pl * np.where(t < 0, np.sin(np.pi * x) ** 2, 0.0)
    return groove + roll + plat


def _seat(field, L, X2, reach: float = 0.03, step: float = 0.00025):
    """Front-plane points (m, the eye's frame) -> where a ray from in front along -forward first meets the field's
    surface (the visible skin). The head mesh's own lid can stand mm away from the built field (Tess: 3.8 mm behind
    it over the lid, where the pose and sliders moved it): the fold must sit on what is meshed."""
    O = L["centre"] + X2[:, :1] * L["side"] + X2[:, 1:] * L["up"] + reach * L["fwd"]
    ts = np.arange(0.0, 2 * reach, step)
    Q = O[:, None, :] - ts[None, :, None] * L["fwd"]
    f = field(Q.reshape(-1, 3)).reshape(len(X2), len(ts))
    inside = f < 0
    i = np.argmax(inside, 1)
    i = np.where(inside.any(1), np.maximum(i, 1), len(ts) - 1)
    a, b = f[np.arange(len(X2)), i - 1], f[np.arange(len(X2)), i]
    t = ts[i - 1] + step * np.clip(a / np.maximum(a - b, 1e-12), 0, 1)
    return O - t[:, None] * L["fwd"]


def line_distance(X: np.ndarray, pr: dict, side: str | None = None) -> np.ndarray:
    """(n,) distance (m) of points from a fold's crease line, across it and along the skin (paint's `near` on a fold:
    the crease's own tone follows its geometry), weighted by the crease's depth there (a faded end reads as far).
    side "up" / "down": only that side of the line counts (the other is far): paint's near {"side": ...}."""
    X = np.asarray(X, float).reshape(-1, 3)
    k = int(min(len(pr["pts"]), max(pr["k"], 12)))
    d, j = pr["tree"].query(X, k=k)
    r = X[:, None, :] - pr["pts"][j]
    t = (r * pr["up"][j]).sum(-1)
    h = (r * pr["nrm"][j]).sum(-1)
    a = (r * pr["along"][j]).sum(-1)
    # (the samples' Gaussian along the line, as mod_fold weighs them: nearest-sample weights striped the tone)
    w = np.exp(-0.5 * (a / pr["sa"]) ** 2) + 1e-12
    ws = w.sum(1)
    ts = (w * t).sum(1) / ws
    tt = np.abs(ts)
    if side == "up":  # only up the lid from the line (the fold's underside); below it: far
        tt = np.where(ts >= 0, ts, 1.0)
    elif side == "down":
        tt = np.where(ts <= 0, -ts, 1.0)
    hh = np.abs((w * h).sum(1) / ws)
    G = (w * pr["G"][j]).sum(1) / ws
    tap = (w * pr["taper"][j]).sum(1) / ws * np.clip(ws / (0.3 * pr["wfull"]), 0, 1)
    dist = np.hypot(tt, np.maximum(hh - 2 * G, 0))
    return dist / np.maximum(tap, 0.05) + (d[:, 0] > 0.01) * 1.0


def curves(head: dict, cfg: dict, n: int = 72, field=None) -> list:
    """Per eye: the crease line's samples {"pts", "nrm", "up", "along", "s", "h"} (world, m): the opening's upper rim
    (lashes.lid_lines) lifted by the crease height (front plane, with the inner / outer scaling) and seated on the
    visible skin (`field`: the built surface; else the head mesh's front-most skin); normals from the field (or the
    head's vertices), `up` the line's across direction up the lid."""
    from scipy.ndimage import gaussian_filter1d

    from . import lashes
    out = []
    HN = np.asarray(head["normals"], float)
    tree = head["tree"]
    for L in lashes.lid_lines(head):
        idx = lashes._arc(L, "upper")
        rim2 = L["o2"] + np.c_[(L["dirs"][idx] @ L["side"]) * L["rho"][idx], (L["dirs"][idx] @ L["up"]) * L["rho"][idx]]
        seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(rim2, axis=0), axis=1))]
        s_all = seg / seg[-1]
        s = np.linspace(cfg["start"], cfg["end"], n)
        R2 = np.c_[np.interp(s, s_all, rim2[:, 0]), np.interp(s, s_all, rim2[:, 1])]
        # the crease height along the lid: a parabola through inner (s 0.2), middle (0.5), outer (0.8)
        A = np.c_[np.ones(3), [0.2, 0.5, 0.8], np.square([0.2, 0.5, 0.8])]
        coef = np.linalg.solve(A, np.array([cfg["inner"], 1.0, cfg["outer"]]))
        hk = np.clip(coef[0] + coef[1] * s + coef[2] * s * s, 0.3, 1.5) * cfg["crease_height"] * MM
        C2 = R2 + np.c_[np.zeros(n), hk]
        seat = (lambda X: _seat(field, L, X)) if field is not None else (lambda X: lashes._on_skin(L, X))

        def smooth(Q):  # the seated depth along the line, median-filtered first: on a hooded lid the ray meets the
            # fold's edge for some samples and the lid under it for the next (a corrugated fold on Garrett)
            from scipy.ndimage import median_filter
            dep = (Q - L["centre"]) @ L["fwd"]
            ds = gaussian_filter1d(median_filter(dep, size=9, mode="nearest"), 3.0, mode="nearest")
            return gaussian_filter1d(Q + (ds - dep)[:, None] * L["fwd"], 1.5, axis=0, mode="nearest")
        P = smooth(seat(C2))
        Pu = smooth(seat(C2 + np.c_[np.zeros(n), np.full(n, 0.3 * MM)]))
        if field is not None:  # the field's own normals (central differences)
            e = 0.1 * MM
            N = np.stack([field(P + e * ax) - field(P - e * ax) for ax in np.eye(3)], 1)
        else:
            _, k = tree.query(P, k=6)
            N = HN[k].mean(1)
        N = gaussian_filter1d(N / np.linalg.norm(N, axis=1, keepdims=True), 2.0, axis=0, mode="nearest")
        N /= np.linalg.norm(N, axis=1, keepdims=True)
        T = np.gradient(P, axis=0)
        T -= (T * N).sum(1, keepdims=True) * N
        T /= np.linalg.norm(T, axis=1, keepdims=True)
        U = Pu - P
        U -= (U * N).sum(1, keepdims=True) * N
        U -= (U * T).sum(1, keepdims=True) * T
        U /= np.linalg.norm(U, axis=1, keepdims=True)
        out.append({"pts": P, "nrm": N, "up": U, "along": T, "s": s, "h": hk})
    return out


def prims(s: dict, base_prim=None) -> list:
    """The fold modifiers for an expanded spec (spec._compile, right after the base `base_prim`, on whose surface the
    lines are seated): one per eye, the base's part."""
    cfg = config(s)
    if cfg is None:
        return []
    from scipy.spatial import cKDTree

    from . import base as basemod
    from .spec import Prim
    head = basemod.head_of(s, s["base"])
    if head is None:
        return []
    out = []
    field = None
    if base_prim is not None:
        from . import sdf
        field = lambda X: sdf.field_at([base_prim], X)  # noqa: E731  (clip=False read a different surface here)
    for i, c in enumerate(curves(head, cfg, field=field)):
        P = c["pts"]
        n = len(P)
        sp = float(np.median(np.linalg.norm(np.diff(P, axis=0), axis=1)))
        sa = 1.5 * sp  # (wide enough that uneven spacing never leaves a gap between samples)
        e = np.clip(np.minimum(c["s"] - cfg["start"], cfg["end"] - c["s"]) / 0.12, 0, 1)
        taper = e * e * (3 - 2 * e)
        G = np.full(n, cfg["crease_depth"] * MM)
        sg = np.full(n, cfg["crease_width"] * MM / 2.355)
        O = np.full(n, cfg["fold_overhang"] * MM)
        so = np.full(n, cfg["fold_width"] * MM)
        Pl = np.full(n, cfg["platform"] * MM)
        ph = np.maximum(c["h"] - 0.8 * MM, 0.5 * MM)
        reach = 3.0 * MM
        Rr = float(max(4 * so.max() + 2 * MM, 3 * sa, ph.max() + MM))
        params = {"pts": P, "nrm": c["nrm"], "up": c["up"], "along": c["along"], "taper": taper, "sa": sa,
                  "wfull": float(np.sqrt(2 * np.pi) * sa / sp) * 0.98, "reach": reach, "G": G, "sg": sg, "O": O,
                  "so": so, "Pl": Pl, "ph": ph, "radius": float(np.hypot(Rr, 2 * reach)),
                  "k": int(min(n, 2 * (3.5 * sa) / sp + 6)), "tree": cKDTree(P)}
        lo, hi = P.min(0) - Rr - reach, P.max(0) + Rr + reach
        lip = 1.0 + 0.61 * float(G.max() / sg.min()) + 0.61 * float(O.max() / so.min())
        out.append(Prim(f"lid_fold{'.L' if i == 0 else '.R'}", "fold", "modify", 0.0, 0, lo, hi, params, lip=lip,
                        part=s["base"].get("part", "body")))
    return out
