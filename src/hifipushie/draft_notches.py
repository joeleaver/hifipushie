"""NOTCHES ON THEIR PIECE (C412): every notch a piece carries lies on that piece.

Trial s4-22 (2026-11-10, the suit jacket): the agent drew its facing and canvas from the front's points and its
undersleeve from jaeger's top sleeve; FreeSewing's notch snippets came along. The flat sheet showed 30 notches floating
off their pieces (facing.L's armholeHollow-notch 148 mm off it, canvas.L's frontPocketBottomLeft-notch 275 mm, the
undersleeve's top-notch 85 mm): the front's armhole, waist and pocket notches on pieces that have no such place. Every row
passed: the seams row's notch check (C387) reads only notches a seam pairs.

A notch outside its piece is a FAIL: it marks a place the piece doesn't have, and anything matched by it (a seam's
balance, a detail) is matched wrong. A notch INSIDE the piece but off its outline is a placement mark (a pocket's corner):
listed as INFO.
"""
from __future__ import annotations

import numpy as np

TOL = 0.002  # m: a notch this near the outline is on it (the sheet's sewing line, sampled)


def _dist(P, q) -> float:
    A = np.asarray(P, float)
    s = np.roll(A, -1, 0) - A
    t = np.clip(((q - A) * s).sum(1) / np.maximum((s * s).sum(1), 1e-12), 0, 1)
    return float(np.min(np.linalg.norm(A + t[:, None] * s - q, axis=1)))


def _inside(P, q) -> bool:
    P = np.asarray(P, float)
    x, y = q
    c = False
    for (x1, y1), (x2, y2) in zip(P, np.roll(P, -1, 0)):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-15) + x1:
            c = not c
    return c


def row(B: dict) -> dict:
    off, inner = [], []
    n = 0
    for nm, pc in (B.get("pieces") or {}).items():
        P = pc.get("P")
        if P is None or len(P) < 3:
            continue
        for k, v in (pc.get("marks") or {}).items():
            v = np.asarray(v, float)
            if v.shape != (2,) or "notch" not in k.lower():
                continue
            n += 1
            d = _dist(P, v)
            if d <= TOL:
                continue
            (inner if _inside(P, v) else off).append(f"{nm}:{k} {d * 1e3:.0f} mm")
    st = "FAIL" if off else ("INFO" if inner else "PASS")
    why = ""
    if off:
        why = ("; ".join(off[:8]) + (f" (+{len(off) - 8} more)" if len(off) > 8 else "") + ": outside their piece, "
               "copied from the part a piece was drawn from. change: in your design, drop the snippets a drawn-from part "
               "brings that this piece has no place for (or move them with the outline), draft_pattern again")
    elif inner:
        why = "inside the piece, off its outline (placement marks): " + "; ".join(inner[:8])
    return {"id": "notches_placed", "status": st, "value": f"{n} notches, {len(off)} outside their piece, "
            f"{len(inner)} inside off the outline", "target": "every notch lies on its piece (on the outline, or a "
            "placement mark inside it)", "why": why, "back_to": "4", "source": "draft_notches.py (C412)"}
