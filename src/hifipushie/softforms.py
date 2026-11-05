"""Soft primary forms: smooth stylised masses that blended blobs can't make without seams.

"super": a superellipsoid blob, between an ellipsoid and a box with no band where a plane turns into an edge
(a rounded box has one). Fuller than an ellipsoid, softer than a box: toy and cartoon "soft blocks".

    {"shape": "super", "at", "offset", "rot", "size": [rx, ry, rz],
     "squareness": 2.0}            # |x/rx|^n + |y/ry|^n + |z/rz|^n = 1; 2 = ellipsoid, rising toward a box
     or "exponents": [nx, ny, nz]  # one per local axis (a pebble square from the front, round from the side)

"loft": ONE smooth mass through cross-sections along its local z (world Z unless "rot" turns it): a head and
body that flow as one pear, a trunk, a bottle. Overlapping blobs leave a groove at every overlap; a loft has none.

    {"shape": "loft", "at": [x, y, z] (origin), "rot",
     "sections": [{"z", "half_width", "half_depth", "squareness": 2, "offset_y": 0}, ...],   # 2+, z rising
     "top": {"z", "round": 3}, "bottom": {"z", "round": 3}}   # the caps (default: half the end section's size)

Each section is a superellipse |x/hw|^n + |(y - offset_y)/hd|^n = 1 at height z (local frame). Every value is
a natural cubic spline through the sections (curvature-continuous: no crease where sections change), carried on
straight past the end sections (still curvature-continuous: a natural spline has no curvature at its ends) and
closed by a dome from the end section to the cap's z: the section shrinks by (1 - t^round)^(1/round), t = 0..1
over the cap. round 2 is an elliptic dome; 3+ is broader and flatter on top and stays curvature-continuous where
the cap starts (2 is only tangent-continuous there). A section's depth is front..back: half_depth is half the
y-extent and offset_y its centre (faces -Y, so a deeper belly front is a negative offset_y).

Both are distance estimates (f / |grad f|), exact on the surface and close near it, and lower bounds well away
from it (the reach set at compile time covers the rest). `fit` moves sizes, section half sizes, offsets, cap
heights and squareness (group "shape").
"""

from __future__ import annotations

import numpy as np

SQ_MIN, SQ_MAX = 1.2, 12.0
_CLIP = 1e2  # |q / size| past this only needs to stay positive: keeps |t|^n finite


def _squareness(name, v, err):
    v = float(v)
    if not SQ_MIN <= v <= SQ_MAX:
        raise err(f"blob {name!r}: squareness {v} (use {SQ_MIN}..{SQ_MAX}; 2 = round, higher = squarer)")
    return v


# ---------------------------------------------------------------- super

def super_params(name: str, bl: dict, c: np.ndarray, rot: np.ndarray, size: np.ndarray, err) -> tuple[dict, float]:
    if np.any(size <= 0):
        raise err(f"blob {name!r}: a super's size is three positive half extents")
    ex = bl.get("exponents")
    if ex is not None:
        if len(ex) != 3:
            raise err(f"blob {name!r}: exponents are [nx, ny, nz]")
        n = np.array([_squareness(name, e, err) for e in ex])
    else:
        n = np.full(3, _squareness(name, bl.get("squareness", 3.0), err))
    # the estimate under-reports by up to max(n) / min(n) off the squarer axes, and by the aspect ratio
    # (as an ellipsoid does) off the long ones
    reach = (np.abs(rot) @ size) / size.min() * float(n.max() / n.min())
    return {"c": c, "size": size, "rot": rot, "n": n}, reach


def sd_super(p: np.ndarray, pr: dict) -> np.ndarray:
    q = (p - pr["c"]) @ pr["rot"]
    r, n = pr["size"], pr["n"]
    a = np.minimum(np.abs(q) / r, _CLIP)
    nm = float(n.min())
    an = a ** n
    F = np.maximum(an.sum(axis=-1), 1e-12)
    dF = n * an / np.maximum(a, 1e-12) / r  # |dF/dq_i|
    G = F ** (1.0 / nm)  # degree-1 homogeneous along the roundest axis: G - 1 ~ distance in its units
    gG = G / (nm * F) * np.linalg.norm(dF, axis=-1)
    d = (G - 1.0) / np.maximum(gG, 1e-9)
    return np.maximum(d, -float(r.min()))  # never deeper than the centre is


# ---------------------------------------------------------------- loft

SECTION_KEYS = ("z", "half_width", "half_depth", "squareness", "offset_y")


def _natural(z: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Second derivatives of the natural cubic spline through (z, y) (zero at both ends)."""
    m = len(z)
    M = np.zeros(m)
    if m < 3:
        return M
    h = np.diff(z)
    A = np.zeros((m - 2, m - 2))
    rhs = 6 * (np.diff(y[1:]) / h[1:] - np.diff(y[:-1]) / h[:-1])
    for i in range(m - 2):
        A[i, i] = 2 * (h[i] + h[i + 1])
        if i:
            A[i, i - 1] = h[i]
        if i < m - 3:
            A[i, i + 1] = h[i + 1]
    M[1:-1] = np.linalg.solve(A, rhs)
    return M


def _spline(z, Y, M, x):
    """Natural cubic spline (values Y, second derivatives M, columns per channel) at x; straight past the ends."""
    xc = np.clip(x, z[0], z[-1])
    i = np.clip(np.searchsorted(z, xc) - 1, 0, len(z) - 2)
    h = (z[i + 1] - z[i])[:, None]
    a = ((z[i + 1] - xc)[:, None]) / h
    b = 1.0 - a
    v = a * Y[i] + b * Y[i + 1] + ((a ** 3 - a) * M[i] + (b ** 3 - b) * M[i + 1]) * h * h / 6.0
    s = (Y[i + 1] - Y[i]) / h + h * (-(3 * a * a - 1) * M[i] + (3 * b * b - 1) * M[i + 1]) / 6.0
    return v + s * (x - xc)[:, None]


def loft_params(name: str, bl: dict, c: np.ndarray, rot: np.ndarray, err) -> tuple[dict, np.ndarray, np.ndarray]:
    secs = bl.get("sections") or []
    if len(secs) < 2:
        raise err(f"blob {name!r}: a loft needs 2+ sections [{{z, half_width, half_depth}}, ...]")
    rows = []
    for i, s in enumerate(secs):
        try:
            z, hw, hd = float(s["z"]), float(s["half_width"]), float(s["half_depth"])
        except (KeyError, TypeError, ValueError):
            raise err(f"blob {name!r}: section {i} needs z, half_width and half_depth") from None
        if hw <= 0 or hd <= 0:
            raise err(f"blob {name!r}: section {i}'s half_width and half_depth must be positive")
        if unknown := set(s) - set(SECTION_KEYS):
            raise err(f"blob {name!r}: section {i}: unknown {sorted(unknown)} (have {', '.join(SECTION_KEYS)})")
        rows.append([z, hw, hd, _squareness(name, s.get("squareness", 2.0), err), float(s.get("offset_y", 0.0))])
    T = np.array(rows)
    if np.any(np.diff(T[:, 0]) <= 0):
        raise err(f"blob {name!r}: loft sections must be listed with z rising")
    z, Y = T[:, 0], T[:, 1:]
    M = np.stack([_natural(z, Y[:, j]) for j in range(4)], 1)
    caps = []
    for end, sign, zi in (("bottom", -1, 0), ("top", 1, -1)):
        cap = bl.get(end) or {}
        if isinstance(cap, (int, float)):
            cap = {"z": cap}
        zc = float(cap.get("z", z[zi] + sign * 0.5 * min(Y[zi, 0], Y[zi, 1])))
        h = (zc - z[zi]) * sign
        if h <= 1e-4:
            raise err(f"blob {name!r}: the {end} cap's z must lie beyond the {end} section")
        caps.append((zc, h, float(cap.get("round", 3.0))))
        if not 1.5 <= caps[-1][2] <= 12:
            raise err(f"blob {name!r}: a cap's round is 1.5..12 (2 elliptic, 3+ broader and flatter)")
    pr = {"c": c, "rot": rot, "z": z, "Y": Y, "M": M, "caps": tuple(caps)}
    zs = np.linspace(caps[0][0], caps[1][0], 257)
    A, B, n, cy = _sections(pr, zs)
    loc_lo = np.array([-A.max(), (cy - B).min(), caps[0][0]])
    loc_hi = np.array([A.max(), (cy + B).max(), caps[1][0]])
    ctr, half = (loc_lo + loc_hi) / 2, (loc_hi - loc_lo) / 2 * 1.02
    ext = np.abs(rot) @ half
    mid = c + rot @ ctr
    return pr, mid - ext, mid + ext


def _sections(pr: dict, zl: np.ndarray, capped: bool = True):
    """Half width, half depth, squareness and y centre of the section at local heights zl (the caps' shrink
    applied when `capped`; the field itself takes the caps as a superellipse in (section radius, cap height))."""
    V = _spline(pr["z"], pr["Y"], pr["M"], zl)
    floor = 0.05 * min(pr["Y"][:, 0].min(), pr["Y"][:, 1].min())
    k = 1.0
    if capped:
        tb, rb, tt, rt = _cap_t(pr, zl)
        k = np.maximum((1.0 - np.minimum(tb, 1) ** rb) ** (1.0 / rb) * (1.0 - np.minimum(tt, 1) ** rt) ** (1.0 / rt),
                       1e-4)
    return np.maximum(V[:, 0], floor) * k, np.maximum(V[:, 1], floor) * k, V[:, 2], V[:, 3]


def _cap_t(pr, zl):
    (zb, hb, rb), (zt, ht, rt) = pr["caps"]
    return np.maximum((pr["z"][0] - zl) / hb, 0.0), rb, np.maximum((zl - pr["z"][-1]) / ht, 0.0), rt


def _norm(u, v, n):
    """Superellipse norm (|u|^n + |v|^n)^(1/n), its gradient over (u, v)."""
    au, av = np.abs(u), np.abs(v)
    m = np.maximum(np.maximum(au, av), 1e-12)
    su, sv = au / m, av / m
    pu, pv = su ** n, sv ** n
    R = m * (pu + pv) ** (1.0 / n)
    rr = np.maximum(R, 1e-12)
    gu = np.sign(u) * (au / rr) ** (n - 1)
    gv = np.sign(v) * (av / rr) ** (n - 1)
    return R, gu, gv


def _loft_f(q, pr):
    """f = 0 on the surface; its x and y derivatives. Past an end section the cap is the superellipse
    rho^r + t^r = 1 (rho: the section norm carried on past the end, t: 0..1 up the cap), which keeps f well
    scaled up to the tip (shrinking the section instead makes f blow up there)."""
    A, B, n, cy = _sections(pr, q[:, 2], capped=False)
    u, v = q[:, 0] / A, (q[:, 1] - cy) / B
    rho, gu, gv = _norm(u, v, n)
    tb, rb, tt, rt = _cap_t(pr, q[:, 2])
    R, grho, _ = _norm(rho, tb + tt, np.where(tb > 0, rb, rt))  # one of tb, tt is 0
    return R - 1.0, grho * gu / A, grho * gv / B, A, B


def sd_loft(p: np.ndarray, pr: dict) -> np.ndarray:
    shp = p.shape[:-1]
    q = ((p - pr["c"]) @ pr["rot"]).reshape(-1, 3)
    f, fx, fy, A, B = _loft_f(q, pr)
    h = 1e-4
    dz = np.array([0.0, 0.0, h])
    fz = (_loft_f(q + dz, pr)[0] - _loft_f(q - dz, pr)[0]) / (2 * h)
    # a superellipse norm's in-plane gradient is at least 1/sqrt(2) of its axis value: floor |grad| there
    g = np.maximum(np.sqrt(fx * fx + fy * fy + fz * fz), 0.7 / np.maximum(A, B))
    d = f / g
    zb, zt = pr["caps"][0][0], pr["caps"][1][0]
    d = np.maximum(d, np.maximum(q[:, 2] - zt, zb - q[:, 2]))  # past a cap's tip: at least that far
    d = np.maximum(d, -np.minimum(A, B))  # never deeper than the section's centre
    return d.reshape(shp)
