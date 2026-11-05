"""Sheet: ONE smooth, seamless thick sheet along a spine curve: a floppy ear folded through 100 degrees, a leaf, a
flap, a cape, a tongue. `blade` only bends gently; blades hinged at an edge read as two plates, and a chain of short
blades along a curve comes out lumpy (each blade's round ends make a knuckle). A sheet has neither.

    {"shape": "sheet",
     "spine": [[x, y, z], ...],          # 2+ points, the sheet's centre line from root to tip (world, + at/offset)
     "curve": "spline",                  # a natural cubic spline through them (C2), or "bezier": the points are
                                         #   cubic Bezier controls p0 c c p1 [c c p2 ...] (3n + 1)
     "width_axis": [x, y, z],            # the width direction at the root (made square to the spine there);
                                         #   default: the normal of the spine's best-fit plane (the fold's axis)
     "stations": [{"t": 0..1,            # along the spine by arc length (default: evenly spaced)
                   "half_width", "half_thickness",
                   "cup": 0,             # m: the side edges lift toward +normal (an ear's hollow); - curls under
                   "twist": 0,           # degrees about the spine, on top of the untwisting frame
                   "puff": 0}, ...],     # cross-section: 0 a slab with round edges, 1 a lens (an ellipse,
                                         #   thickest mid-width: pillowy clay, a leaf), between: a blend
     "root": m, "tip": m,                # how far the outline rounds off at each end (default: the end's
                                         #   half width, a round end); the thickness always rounds the edge
     "at", "offset"}                     # move the whole spine

The width axis follows the curve without twisting (a rotation-minimising frame, by double reflection), the normal
is spine tangent x width axis (".R" mirrors keep it on the same side). Every station value is a natural cubic
spline in arc length. A point's sheet coordinates are (s, w, n): arc length to its nearest spine point, and its
offsets along the width axis and the normal there. The core is |w| <= half_width - half_thickness, rounded at the
ends, and the sheet is that core thickened by half_thickness (edges fully round). So the fold is seamless as long
as the spine's bend radius stays above the half thickness (refused otherwise) and any in-plane turn (about the
normal) stays wide next to the half width. Distance estimate: exact across the thickness, close elsewhere.
`fit` moves the spine points (group "pos") and the stations' half sizes ("size").
"""

from __future__ import annotations

import numpy as np

from .softforms import _natural, _spline

STATION_KEYS = ("t", "half_width", "half_thickness", "cup", "twist", "puff")
_DENSE = 256  # spine table samples (frames, arc length)
_SEARCH = 96  # segments searched for the nearest spine point before Newton refines it


# ---------------------------------------------------------------- the spine

def _spine_eval(sp: dict, u: np.ndarray):
    """Position, first and second derivative at curve parameter u (0..1 over the whole spine)."""
    u = np.clip(u, 0.0, 1.0)
    if sp["kind"] == "bezier":
        C = sp["C"]  # (pieces, 4, 3)
        m = len(C)
        x = u * m
        i = np.minimum(x.astype(int), m - 1)
        t = (x - i)[:, None]
        p0, p1, p2, p3 = C[i, 0], C[i, 1], C[i, 2], C[i, 3]
        s = 1 - t
        P = s ** 3 * p0 + 3 * s * s * t * p1 + 3 * s * t * t * p2 + t ** 3 * p3
        D = 3 * (s * s * (p1 - p0) + 2 * s * t * (p2 - p1) + t * t * (p3 - p2)) * m
        DD = 6 * (s * (p2 - 2 * p1 + p0) + t * (p3 - 2 * p2 + p1)) * m * m
        return P, D, DD
    k, Y, M = sp["k"], sp["Y"], sp["M"]  # natural spline per coordinate over knots k (chord length, 0..1)
    i = np.clip(np.searchsorted(k, u) - 1, 0, len(k) - 2)
    h = (k[i + 1] - k[i])[:, None]
    a = (k[i + 1] - u)[:, None] / h
    b = 1.0 - a
    P = a * Y[i] + b * Y[i + 1] + ((a ** 3 - a) * M[i] + (b ** 3 - b) * M[i + 1]) * h * h / 6
    D = (Y[i + 1] - Y[i]) / h + h * (-(3 * a * a - 1) * M[i] + (3 * b * b - 1) * M[i + 1]) / 6
    DD = a * M[i] + b * M[i + 1]
    return P, D, DD


def _rmf(T: np.ndarray, P: np.ndarray, W0: np.ndarray) -> np.ndarray:
    """Rotation-minimising width axes along a sampled curve (Wang et al. 2008, double reflection)."""
    W = np.empty_like(T)
    W[0] = W0
    for i in range(len(T) - 1):
        v1 = P[i + 1] - P[i]
        c1 = v1 @ v1
        if c1 < 1e-20:
            W[i + 1] = W[i]
            continue
        rL = W[i] - (2 / c1) * (v1 @ W[i]) * v1
        tL = T[i] - (2 / c1) * (v1 @ T[i]) * v1
        v2 = T[i + 1] - tL
        c2 = v2 @ v2
        w = rL - (2 / c2) * (v2 @ rL) * v2 if c2 > 1e-20 else rL
        w -= (w @ T[i + 1]) * T[i + 1]
        W[i + 1] = w / np.linalg.norm(w)
    return W


def sheet_params(name: str, bl: dict, base: np.ndarray, err) -> tuple[dict, np.ndarray, np.ndarray]:
    try:
        pts = np.array(bl.get("spine") or [], float) + base
    except (TypeError, ValueError):
        raise err(f"blob {name!r}: a sheet's spine is a list of [x, y, z] points") from None
    if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) < 2:
        raise err(f"blob {name!r}: a sheet needs a spine of 2+ [x, y, z] points, root to tip")
    kind = bl.get("curve", "spline")
    if kind == "bezier":
        if (len(pts) - 1) % 3:
            raise err(f"blob {name!r}: a Bezier spine has 3n + 1 points (p0 c c p1 c c p2 ...), not {len(pts)}")
        n = (len(pts) - 1) // 3
        sp = {"kind": "bezier", "C": np.stack([pts[3 * j:3 * j + 4] for j in range(n)])}
    elif kind == "spline":
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        if np.any(seg < 1e-6):
            raise err(f"blob {name!r}: two spine points coincide")
        k = np.concatenate([[0.0], np.cumsum(seg)]) / seg.sum()
        sp = {"kind": "spline", "k": k, "Y": pts, "M": np.stack([_natural(k, pts[:, j]) for j in range(3)], 1)}
    else:
        raise err(f"blob {name!r}: a sheet's curve is \"spline\" or \"bezier\"")

    u = np.linspace(0.0, 1.0, _DENSE + 1)
    P, D, DD = _spine_eval(sp, u)
    sp_ = np.linalg.norm(D, axis=1)
    if sp_.min() < 1e-6:
        raise err(f"blob {name!r}: the spine stops dead somewhere (a Bezier control on its end point?)")
    T = D / sp_[:, None]
    S = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    L = float(S[-1])
    if L < 1e-4:
        raise err(f"blob {name!r}: the spine has no length")
    kappa = np.linalg.norm(np.cross(D, DD), axis=1) / sp_ ** 3

    wa = bl.get("width_axis")
    if wa is not None:
        W0 = np.array(wa, float)
    else:
        X = P - P.mean(0)
        _, sv, vt = np.linalg.svd(X, full_matrices=False)
        if sv[1] < 1e-3 * max(sv[0], 1e-12):
            raise err(f"blob {name!r}: a straight spine needs a width_axis")
        W0 = vt[2]
    W0 = W0 - (W0 @ T[0]) * T[0]
    if np.linalg.norm(W0) < 1e-6:
        raise err(f"blob {name!r}: width_axis runs along the spine")
    W = _rmf(T, P, W0 / np.linalg.norm(W0))

    st = bl.get("stations") or []
    if not st:
        raise err(f"blob {name!r}: a sheet needs stations [{{half_width, half_thickness}}, ...]")
    rows = []
    for i, s in enumerate(st):
        if unknown := set(s) - set(STATION_KEYS):
            raise err(f"blob {name!r}: station {i}: unknown {sorted(unknown)} (have {', '.join(STATION_KEYS)})")
        try:
            t = float(s.get("t", i / max(len(st) - 1, 1)))
            hw, ht = float(s["half_width"]), float(s["half_thickness"])
        except (KeyError, TypeError, ValueError):
            raise err(f"blob {name!r}: station {i} needs half_width and half_thickness") from None
        if ht <= 0 or hw <= ht:
            raise err(f"blob {name!r}: station {i}: half_thickness must be positive and under the half_width")
        puff = float(s.get("puff", 0.0))
        if not 0 <= puff <= 1:
            raise err(f"blob {name!r}: station {i}: puff is 0 (slab) .. 1 (lens)")
        rows.append([t, hw, ht, float(s.get("cup", 0.0)), float(s.get("twist", 0.0)), puff])
    R = np.array(rows)
    if len(R) == 1:
        R = np.vstack([R, R + [1.0, 0, 0, 0, 0, 0]])
        R[0, 0] = 0.0
    if np.any(np.diff(R[:, 0]) <= 0) or R[0, 0] < 0 or R[-1, 0] > 1:
        raise err(f"blob {name!r}: station t values rise from 0 to 1")
    ts, V = R[:, 0] * L, R[:, 1:]
    VM = np.stack([_natural(ts, V[:, j]) for j in range(V.shape[1])], 1)
    pr = {"sp": sp, "P": P, "T": T, "W": W, "S": S, "L": L, "ts": ts, "V": V, "VM": VM,
          "hand": float(bl.get("hand", 1.0)),
          "WM": np.stack([_natural(S, W[:, j]) for j in range(3)], 1)}
    hw_s, ht_s, *_ = _stations(pr, S)
    if np.any(kappa * ht_s >= 0.9):
        i = int(np.argmax(kappa * ht_s))
        raise err(f"blob {name!r}: the spine bends tighter (radius {1 / kappa[i]:.3f} m at {S[i] / L:.2f} of its "
                  f"length) than the sheet is thick ({ht_s[i]:.3f}): ease the fold or thin the sheet there")
    ends = []
    for key, j in (("root", 0), ("tip", -1)):
        r = float(bl.get(key, hw_s[j] - ht_s[j]))
        if r <= 0:
            raise err(f"blob {name!r}: {key} (the end's rounding length) must be positive")
        ends.append(r)
    pr["ends"] = (ends[0], ends[1], float(ht_s[0]), float(ht_s[-1]))
    if ends[0] + ends[1] + ht_s[0] + ht_s[-1] > L:
        raise err(f"blob {name!r}: root + tip rounding ({ends[0] + ends[1]:.3f} m) is longer than the sheet")
    Rmax = float((V[:, 0] + np.abs(V[:, 2])).max() + V[:, 1].max())
    return pr, P.min(0) - Rmax, P.max(0) + Rmax


def _stations(pr, s):
    """Half width, half thickness, cup, twist (rad) and puff at arc lengths s (held past the end stations)."""
    sc = np.clip(s, pr["ts"][0], pr["ts"][-1])
    v = _spline(pr["ts"], pr["V"], pr["VM"], sc) if len(pr["ts"]) > 2 else \
        pr["V"][0] + (pr["V"][1] - pr["V"][0]) * ((sc - pr["ts"][0]) / (pr["ts"][1] - pr["ts"][0]))[:, None]
    return v[:, 0], v[:, 1], v[:, 2], np.radians(v[:, 3]), np.clip(v[:, 4], 0.0, 1.0)


def _nearest(q: np.ndarray, pr: dict):
    """Arc length s of each point's nearest spine point, that point and the tangent there (straight past the ends)."""
    sp, L = pr["sp"], pr["L"]
    us = np.linspace(0.0, 1.0, _SEARCH + 1)
    Ps = _spine_eval(sp, us)[0]
    a, d = Ps[:-1], np.diff(Ps, axis=0)
    r = q[:, None, :] - a[None]
    t = np.clip((r * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-20), 0, 1)
    dist = ((r - t[..., None] * d) ** 2).sum(-1)
    j = np.argmin(dist, 1)
    u = (j + t[np.arange(len(q)), j]) / _SEARCH
    du = 1.0 / _SEARCH
    for _ in range(4):  # Newton on (C(u) - q) . C'(u) = 0, kept within a segment of the start
        C, D, DD = _spine_eval(sp, u)
        e = C - q
        g = (e * D).sum(1)
        h = (D * D).sum(1) + (e * DD).sum(1)
        step = np.where(h > 1e-12, -g / np.maximum(h, 1e-12), 0.0)
        u = np.clip(u + np.clip(step, -du, du), 0.0, 1.0)
    C, D, _ = _spine_eval(sp, u)
    T = D / np.linalg.norm(D, axis=1)[:, None]
    # arc length: the dense table at u (linear between samples of a smooth curve: sub-0.1 mm)
    s = np.interp(u, np.linspace(0, 1, _DENSE + 1), pr["S"])
    past = ((q - C) * T).sum(1)
    lo, hi = u <= 0.0, u >= 1.0
    over = np.where(lo, np.minimum(past, 0), np.where(hi, np.maximum(past, 0), 0.0))
    return s + over, C + over[:, None] * T, T


def sd_sheet(p: np.ndarray, pr: dict) -> np.ndarray:
    shp = p.shape[:-1]
    Q = p.reshape(-1, 3).astype(np.float64)
    out = np.empty(len(Q))
    for c0 in range(0, len(Q), 4096):
        q = Q[c0:c0 + 4096]
        s, C, T = _nearest(q, pr)
        W = _spline(pr["S"], pr["W"], pr["WM"], np.clip(s, 0, pr["L"]))
        W -= (W * T).sum(1)[:, None] * T
        W /= np.linalg.norm(W, axis=1)[:, None]
        N = pr["hand"] * np.cross(T, W)
        hw, ht, cup, tw, puff = _stations(pr, s)
        if np.any(tw):
            c, sn = np.cos(tw)[:, None], np.sin(tw)[:, None]
            W, N = c * W + sn * N, c * N - sn * W
        r = q - C
        w, n = (r * W).sum(1), (r * N).sum(1)
        a = np.maximum(hw - ht, 1e-4)
        n = n - cup * (w / hw) ** 2
        # the core outline in (s, w): |w| <= a(s), each end rounded off over its length (an ellipse quadrant)
        er, et, htr, htt = pr["ends"]
        s0, s1 = htr + er, pr["L"] - htt - et
        vr = np.maximum(s0 - s, 0) / er
        vt = np.maximum(s - s1, 0) / et
        uu = np.abs(w) / a
        rho = np.sqrt(uu * uu + vr * vr + vt * vt)
        # gradient of rho over (s, w); a(s)'s slope from the station spline (small: ignore its share)
        gw = uu / a
        gs = (vt / et - vr / er)
        g = np.sqrt(gw * gw + gs * gs) / np.maximum(rho, 1e-9)
        e = (rho - 1.0) / np.maximum(g, 1e-9)
        e = np.where(rho < 1e-9, -np.minimum(a, np.minimum(s - htr, pr["L"] - htt - s)), e)
        h = np.abs(n)
        d = np.hypot(np.maximum(e, 0.0), h) + np.minimum(np.maximum(e, h), 0.0) - ht
        d = np.maximum(d, -ht)
        if np.any(puff > 0):  # the lens: an ellipse (hw, ht) across, the same end rounding along; a convex blend of
            # two distance estimates stays one (and stays as smooth as both)
            vr2 = np.maximum(er - s, 0) / er
            vt2 = np.maximum(s - (pr["L"] - et), 0) / et
            uw, un = w / hw, n / ht
            k0 = np.sqrt(uw * uw + un * un + vr2 * vr2 + vt2 * vt2)
            gk = np.sqrt((uw / hw) ** 2 + (un / ht) ** 2 + (vr2 / er) ** 2 + (vt2 / et) ** 2) / np.maximum(k0, 1e-9)
            dl = np.where(k0 > 1e-9, (k0 - 1.0) / np.maximum(gk, 1e-9), -ht)
            d = (1 - puff) * d + puff * np.maximum(dl, -ht)
        out[c0:c0 + 4096] = d
    return out.reshape(shp)
