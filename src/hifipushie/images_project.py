"""Placement: mirrored copies, the surface map, wrap coordinates, projection, sampling, `evaluate`, the
frames of a spec, footprint and coverage. Part of images (images.py has the spec)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import images
from .images import layer_images, pixels
from .images_frame import frame

def mirrored(fr: dict) -> dict:
    """The placement reflected across X with the picture still reading the right way."""
    M = np.array([-1.0, 1.0, 1.0])
    c, d, up = np.array(fr["c"]) * M, np.array(fr["dir"]) * M, np.array(fr["up"]) * M
    right = np.cross(up, d)
    if fr.get("mirror_image") and fr.get("wrap", "planar") == "planar":  # the whole frame reflected: the picture too
        right = np.array(fr["right"]) * M
    out = {**fr, "c": c.tolist(), "dir": d.tolist(), "up": up.tolist(), "right": right.tolist(), "mirror": False}
    if fr.get("wrap") in ("cylinder", "sphere"):  # the seam's place mirrored too (angles run the other way)
        out.update(o=(np.array(fr["o"]) * M).tolist(), k=up.tolist(), seam=-fr["seam"],
                   dc=float(np.mod(fr["seam"], 2 * np.pi)))
    return out


def _ramp(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def surface_map(fr: dict) -> dict:
    """A surface decal's exponential map (decalmap.build), on the primitives its frame was made from."""
    from . import decalmap
    prims = images._PRIMS.get(fr["geo"])
    if prims is None:
        raise RuntimeError("a surface decal's frame must be made in this process (images_frame.frame) before it's used")
    return decalmap.build(prims, fr)


def wrap_coords(fr: dict, pos: np.ndarray):
    """A cylinder/sphere wrap's (u, v, distance off its surface, outward unit) at points (before flip). The
    cylinder's surface is the local cone fitted at the centre (radius r0 + m t), "arc": u = arc length at the point's
    own radius, v = height along the axis; "cone": the label fan-cut onto that cone (u = angle x the centre's radius,
    v = slant distance: columns run along the cone's generators, rows round it, even height)."""
    q = np.asarray(pos, float) - fr["o"]
    k, e1, e2 = (np.asarray(fr[x], float) for x in ("k", "dir", "right"))
    t, x, y = q @ k, q @ e1, q @ e2
    D = np.mod(np.arctan2(y, x) - fr["seam"], 2 * np.pi) - fr["dc"]
    rho = np.hypot(x, y)
    if fr["wrap"] == "cylinder":
        m = fr.get("m", 0.0)
        s = np.sqrt(1 + m * m)
        radial = (x[:, None] * e1 + y[:, None] * e2) / np.maximum(rho, 1e-12)[:, None]
        out = (radial - m * k) / s
        err = (rho - (fr["r0"] + m * t)) / s
        if fr.get("unroll") == "cone":
            u = (D / fr["su"] if fr["su"] else fr["r0"] * D / fr["w"]) + 0.5
            v = fr["sg"] * (fr["Rc"] - np.hypot(rho, t - fr["ta"])) / fr["h"] + 0.5
        else:
            u = (D / fr["su"] if fr["su"] else rho * D / fr["w"]) + 0.5
            v = t / fr["h"] + 0.5
    else:
        u = (D / fr["su"] if fr["su"] else rho * D / fr["w"]) + 0.5
        R = np.linalg.norm(q, axis=1)
        phi = np.arcsin(np.clip(t / np.maximum(R, 1e-12), -1, 1)) - fr["phic"]
        v = (phi / fr["sv"] if fr["sv"] else R * phi / fr["h"]) + 0.5
        err = R - fr["r0"]
        out = q / np.maximum(R, 1e-12)[:, None]
    return u, v, err, out


def project(fr: dict, pos: np.ndarray, nrm: np.ndarray, both: bool = False):
    """(u, v, weight) per point: u, v in 0..1 across the decal (v up), weight = inside its depth x facing.
    both=True: (u, v, weight, u2, v2, s): wrap "uv" has a second coordinate set near the atlas' cut, the image sampled
    at both and mixed by s (skin_project_lookup.lookup(both=True)); other wraps give (u, v) again and s = 0."""
    nn = np.asarray(nrm, float)
    nn = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
    wrap = fr.get("wrap", "planar")
    if wrap in ("cylinder", "sphere"):
        u, v, err, out = wrap_coords(fr, pos)
        wgt = _ramp(np.abs(err), fr["depth"], 0.8 * fr["depth"])
        wgt = wgt * _ramp((nn * out).sum(1), fr["facing"] - 0.15, fr["facing"])
    elif wrap == "surface":
        from . import decalmap
        U, dist, N = decalmap.lookup(surface_map(fr), pos)
        off = ~np.isfinite(U).all(1)
        U[off] = -1e3
        u = U[:, 0] / fr["w"] + 0.5
        v = U[:, 1] / fr["h"] + 0.5
        wgt = _ramp(dist, fr["depth"], 0.8 * fr["depth"]) * _ramp((nn * N).sum(1), fr["facing"] - 0.15, fr["facing"])
        wgt = wgt * _ramp(np.linalg.norm(U, axis=1), fr["reach"], 0.9 * fr["reach"])
        wgt[off] = 0
    elif wrap == "uv":
        from . import skin_project_lookup
        b = images._UVBASE.get(fr["geo"])
        if b is None:
            raise RuntimeError("a uv image's frame must be made in this process (images_frame.frame) before it's used")
        u0, v0, u1, v1 = fr["box"]
        if both:  # the image's coordinates are the atlas' (no flip, no mirror for this wrap)
            ua, va, ub, vb, s, wgt = skin_project_lookup.lookup(b, pos, both=True)
            return ((ua - u0) / (u1 - u0), (va - v0) / (v1 - v0), wgt, (ub - u0) / (u1 - u0), (vb - v0) / (v1 - v0), s)
        ua, va, wgt = skin_project_lookup.lookup(b, pos)
        u, v = (ua - u0) / (u1 - u0), (va - v0) / (v1 - v0)
    else:
        p = np.asarray(pos, float) - fr["c"]
        u = p @ fr["right"] / fr["w"] + 0.5
        v = p @ fr["up"] / fr["h"] + 0.5
        s = np.abs(p @ fr["dir"])
        wgt = _ramp(s, fr["depth"], 0.8 * fr["depth"])
        wgt = wgt * _ramp(nn @ fr["dir"], fr["facing"] - 0.15, fr["facing"])
    if fr["flip"]:
        u = 1 - u
    if both:
        return u, v, wgt, u, v, np.zeros(len(u))
    return u, v, wgt


def sample(pix: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinear lookup at (u, v) (v up), 0 outside the image (as Blender's CLIP extension)."""
    H, W = pix.shape[:2]
    x, y = u * W - 0.5, (1 - v) * H - 0.5
    inside = (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    x0c, x1c = np.clip(x0, 0, W - 1), np.clip(x0 + 1, 0, W - 1)
    y0c, y1c = np.clip(y0, 0, H - 1), np.clip(y0 + 1, 0, H - 1)
    out = (pix[y0c, x0c] * (1 - fx) * (1 - fy) + pix[y0c, x1c] * fx * (1 - fy)
           + pix[y1c, x0c] * (1 - fx) * fy + pix[y1c, x1c] * fx * fy)
    out[~inside] = 0
    return out


def _one(fr: dict, pos, nrm):
    u, v, wgt, u2, v2, s = project(fr, pos, nrm, both=True)
    pix = pixels(Path(fr["path"]))

    def inside(a, b):
        return ((a >= 0) & (a <= 1) & (b >= 0) & (b <= 1)).astype(float)
    rgba, cov = sample(pix, u, v), inside(u, v)
    if s.any():  # across the atlas' cut: the second coordinate set's sample, mixed by side B's share
        rgba = rgba * (1 - s)[:, None] + sample(pix, u2, v2) * s[:, None]
        cov = cov * (1 - s) + inside(u2, v2) * s
    ch = fr["channel"]
    if ch == "coverage":
        val = cov
    elif ch == "alpha":
        val = rgba[:, 3]
    elif ch == "luma":
        val = rgba[:, :3] @ np.array([0.2126, 0.7152, 0.0722])
    else:
        val = rgba[:, "rgb".index(ch)]
    return val * wgt, rgba[:, :3]


def evaluate(fr: dict, pos: np.ndarray, nrm: np.ndarray):
    """(mask (n,), sRGB colour (n, 3)) of a decal at surface points; with "mirror", the stronger placement wins."""
    m, col = _one(fr, pos, nrm)
    if fr["mirror"]:
        m2, col2 = _one(mirrored(fr), pos, nrm)
        col = np.where((m2 > m)[:, None], col2, col)
        m = np.maximum(m, m2)
    return m, col


def frames_of(spec: dict, ly: dict, expanded: dict | None = None) -> list[dict]:
    from .spec import expand_mirror
    imgs = layer_images(ly)
    if not imgs:
        return []
    s = expanded if expanded is not None else expand_mirror(spec)
    return [frame(spec, img, s, parts=ly.get("part", "body")) for img in imgs]


def footprint(fr: dict, n: int = 24) -> np.ndarray:
    """World points over the decal's rectangle as it lies on the surface (texel focus, coverage): a grid on the
    plane, on the wrap's cylinder/sphere at the centre's radius, or the surface map's own vertices inside it."""
    a = (np.arange(n) + 0.5) / n
    gu, gv = (x.ravel() for x in np.meshgrid(a, a))
    if fr["wrap"] == "surface":
        m = surface_map(fr)
        U = m["U"].astype(float)
        ok = np.isfinite(U).all(1)
        ok[ok] = (np.abs(U[ok, 0]) <= 0.5 * fr["w"]) & (np.abs(U[ok, 1]) <= 0.5 * fr["h"])
        return m["V"][ok].astype(float)
    return _place(fr, gu, gv)


def _place(fr: dict, gu: np.ndarray, gv: np.ndarray) -> np.ndarray:
    """World points at (u, v) in 0..1 across the decal: on its plane (planar and surface decals: the tangent
    plane), or on the wrap's cylinder/cone/sphere at the centre's radius."""
    if fr["wrap"] in ("planar", "surface"):
        return (np.asarray(fr["c"]) + ((gu - 0.5) * fr["w"])[:, None] * np.asarray(fr["right"])
                + ((gv - 0.5) * fr["h"])[:, None] * np.asarray(fr["up"]))
    o, k, e1, e2 = (np.asarray(fr[x], float) for x in ("o", "k", "dir", "right"))
    r0, phic = fr["r0"], fr["phic"]
    rho0 = r0 * np.cos(phic)
    D = (gu - 0.5) * (fr["su"] if fr["su"] else fr["w"] / rho0)
    if fr["flip"]:
        D = -D
    if fr["wrap"] == "cylinder":
        m = fr.get("m", 0.0)
        if fr.get("unroll") == "cone":  # back from the fan: slant distance -> height and radius on the cone
            R = fr["Rc"] - fr["sg"] * (gv - 0.5) * fr["h"]
            s = np.sqrt(1 + m * m)
            t = fr["ta"] - fr["sg"] * R / s
            rho = R * abs(m) / s
        else:
            t = (gv - 0.5) * fr["h"]
            rho = rho0 + m * t
            if not fr["su"]:
                D = D * rho0 / rho  # arc length at the point's own radius
        return o + rho[:, None] * (np.cos(D)[:, None] * e1 + np.sin(D)[:, None] * e2) + t[:, None] * k
    phi = phic + (gv - 0.5) * (fr["sv"] if fr["sv"] else fr["h"] / r0)
    return o + r0 * (np.cos(phi)[:, None] * (np.cos(D)[:, None] * e1 + np.sin(D)[:, None] * e2)
                     + np.sin(phi)[:, None] * k)


def coverage(fr: dict, prims: list, n: int = 7, steps: int = 48) -> float:
    """The share of an n x n grid over the decal whose ray (from depth in front of its surface to depth behind)
    crosses the surface of these primitives: 0 = the placement hits nothing."""
    from . import sdf
    if not prims:
        return 0.0
    if fr["wrap"] == "surface":
        return 1.0 if len(footprint(fr)) else 0.0  # seated on the surface already
    a = (np.arange(n) + 0.5) / n - 0.5
    if fr["wrap"] == "planar":
        c, r, u, d = (np.asarray(fr[k], float) for k in ("c", "right", "up", "dir"))
        gu, gv = np.meshgrid(a * fr["w"], a * fr["h"])
        base = c + gu.reshape(-1, 1) * r + gv.reshape(-1, 1) * u
        dirs = np.broadcast_to(d, base.shape)
    else:
        base = footprint(fr, n)
        rel = base - np.asarray(fr["o"], float)
        if fr["wrap"] == "cylinder":
            k = np.asarray(fr["k"], float)
            rel = rel - (rel @ k)[:, None] * k
        dirs = rel / np.maximum(np.linalg.norm(rel, axis=1, keepdims=True), 1e-12)
    t = np.linspace(fr["depth"], -fr["depth"], steps)
    pts = base[:, None, :] + t[None, :, None] * dirs[:, None, :]
    f = sdf.field_at(prims, pts.reshape(-1, 3)).reshape(len(base), steps)
    hit = ((f[:, :-1] > 0) & (f[:, 1:] <= 0)).any(1)
    return float(hit.mean())
