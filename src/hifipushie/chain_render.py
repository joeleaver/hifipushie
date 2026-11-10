"""CHAIN RENDER: render_views, the pictures of a chain build (look_chain; chain_garment.py's docstring is the spec). Moved
out of chain_garment.py (R3a, behaviour-preserving); call it as chain_garment.render_views (tests patch it there)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .chain_core import (joined_faces)


def render_views(X, M, bV, bT, out: str, views=None, focus: str | None = None, size: int = 640, log=print) -> list:
    """Sewn vertices joined, every piece facing outward. focus None: the whole figure, on the body; "neck": the collar
    close, on the body; a piece's name: that piece ALONE, large, four sides. Returns [(view, path)]."""
    from . import cloth, resources
    X = np.asarray(X, float)
    F = joined_faces(X, M, bV, bT)
    names = list(M["names"])
    pc = np.asarray(M["piece"])
    cloth_part = {"name": "shirt", "V": X, "F": F, "color": "#a9c4e6"}
    body_part = {"name": "body", "V": bV, "F": bT, "color": "#c4bcb4"}
    if focus in names:
        Fp = np.asarray(M["F"])[pc[np.asarray(M["F"])[:, 0]] == names.index(focus)]
        ids = np.unique(Fp)
        P = X[ids]
        parts = [dict(cloth_part, F=joined_faces(X, M, bV, bT)[pc[np.asarray(M["F"])[:, 0]] == names.index(focus)])]
        lo, hi = P.min(0), P.max(0)
        c, r = 0.5 * (lo + hi), 0.55 * float((hi - lo).max()) + 0.005
        box = [(c - r).tolist(), (c + r).tolist()]
        views = views or [("front", [0, -1, 0.1]), ("back", [0, 1, 0.1]), ("left", [1, 0, 0.1]), ("right", [-1, 0, 0.1])]
    elif focus == "neck":
        z = float(X[pc == names.index(next(n for n in names if n in ("collar", "stand")) if any(n in names for n in ("collar", "stand")) else names[0]), 2].mean())
        parts = [body_part, cloth_part]
        box = [[-0.14, -0.2, z - 0.1], [0.14, 0.09, z + 0.09]]
        views = views or [("front", [0, -1, 0.1]), ("three", [-0.6, -0.8, 0.15]), ("side", [-1, 0, 0.05]), ("back", [0, 1, 0.3])]
    else:
        parts = [body_part, cloth_part]
        lo, hi = X.min(0), X.max(0)
        box = [[lo[0] - 0.05, lo[1] - 0.05, lo[2] - 0.03], [hi[0] + 0.05, hi[1] + 0.05, float(np.asarray(bV)[:, 2].max()) + 0.02]]
        views = views or [("front", [0, -1, 0.05]), ("three", [-0.6, -0.8, 0.1]), ("side", [-1, 0, 0.05]), ("back", [0, 1, 0.05])]
    res = []
    with resources.heavy(f"look chain {Path(out).name}", gb=3.0, gpu=True, log=log):
        for nm, dv in views:
            p = cloth.render(parts, f"{out}_{nm}", views=[{"name": nm, "dir": list(dv)}], resolution=size, box=box)[0]
            res.append((nm, str(p)))
    return res
