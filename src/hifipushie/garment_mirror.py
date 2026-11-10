"""A mark's mirrored pass (garment_details: `mirror: true` places it again on the .L <-> .R piece): on a pair's other
copy, whose flat is the drafted one's mirror image, a point's sideways offset runs the other way."""
from __future__ import annotations

import numpy as np


def flipped(fl: object, p: str, q: str) -> bool:
    """q's flat is p's mirror image across its vertical (a pair's other copy: draft_pairs): their shared named
    points sit at (-du, dv) of each other, within 1 mm."""
    try:
        common = sorted(k.split(":", 1)[1] for k in fl.pts if k.startswith(p + ":") and f"{q}:{k.split(':', 1)[1]}" in fl.pts)
    except Exception:
        return False
    if len(common) < 3:
        return False
    A = np.array([fl.uv[fl.pts[f"{p}:{n}"]] for n in common])
    B = np.array([fl.uv[fl.pts[f"{q}:{n}"]] for n in common])
    A, B = A - A[0], B - B[0]
    return bool(np.allclose(B, A * [-1.0, 1.0], atol=1e-3)) and not bool(np.allclose(B, A, atol=1e-3))


def flip_dx(x, fl, p: str, q: str):
    """The mirrored pass of a mark: on a mirrored flat a point's offset dx runs the other way (C381, t s4-11: a
    {point, dx} chest braid mirrored onto front.R landed 100 mm off it)."""
    return _neg_dx(x) if flipped(fl, p, q) else x


def _neg_dx(x):
    if isinstance(x, list):
        return [_neg_dx(v) for v in x]
    if isinstance(x, dict):
        y = {k: _neg_dx(v) for k, v in x.items()}
        if "point" in y and "dx" in y:
            y["dx"] = -float(y["dx"])
        return y
    return x
