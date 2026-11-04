"""BODY MARKS FROM STEP 0 (C351), for any garment: the marks that place a step-2 view on the body (structure_outline) are
step 0's own fit landmarks on that view, already read, checked against each other and approved, never placed a second
time (t s2-1: the agent marked the shoulders, wrists and waist again by eye, on the same picture step 0 had read).

The fit view's landmarks map onto structure_outline.MARKS: a height (armpit, chest, waist, high_hip, hips, seat, crotch)
-> its "_z" mark (v only; u at the garment's centre); a point landmark given as [u, v] or as both sides [[u, v], [u, v]]
(shoulder, elbow, wrist) -> ".L" / ".R" by which side of the centre it sits on (a front view shows the wearer's left on
the picture's right; a back view the other way). Seen landmarks first; inferred ones (step 0's {at, from}) only when
fewer than two are seen. A view step 0 didn't fit can still be placed by the plan's own body_marks.
"""
from __future__ import annotations

HEIGHTS = {k: f"{k}_z" for k in ("armpit", "chest", "waist", "high_hip", "hips", "seat", "crotch")}
POINTS = ("shoulder", "elbow", "wrist")


def _pt(q) -> bool:
    return isinstance(q, (list, tuple)) and len(q) == 2 and all(isinstance(x, (int, float)) for x in q)


def from_read(read: dict, centre=None) -> dict | None:
    """{view, at: {mark: [u, v]}, source} from step 0's fit landmarks, or None (no fit)."""
    fr = read.get("fit_read") or {}
    lms, vi = fr.get("landmarks") or {}, fr.get("view", 0)
    views = read.get("views") or []
    if not lms or not isinstance(vi, int) or not 0 <= vi < len(views):
        return None
    side = views[vi].get("view")
    if side not in ("front", "back"):
        return None
    if centre is None:
        ws = [w.get("garment") for w in fr.get("widths") or [] if isinstance(w, dict)]
        us = [(a[0] + b[0]) / 2 for a, b in (g for g in ws if isinstance(g, list) and len(g) == 2 and all(map(_pt, g)))]
        centre = sum(us) / len(us) if us else None
    if centre is None:
        return None
    seen, inferred = {}, {}
    for name, x in lms.items():
        into = seen
        if isinstance(x, dict):
            x, into = x.get("at"), inferred
        if name in HEIGHTS:
            v = x if isinstance(x, (int, float)) else x[1] if _pt(x) else \
                sum(q[1] for q in x) / len(x) if isinstance(x, list) and x and all(map(_pt, x)) else None
            if v is not None:
                into[HEIGHTS[name]] = [float(centre), float(v)]
        elif name in POINTS:
            pts = [x] if _pt(x) else x if isinstance(x, list) and all(map(_pt, x)) else []
            for q in pts:
                left = (q[0] > centre) == (side == "front")  # (the wearer's left: +X)
                into[f"{name}.{'L' if left else 'R'}"] = [float(q[0]), float(q[1])]
    at = dict(seen)
    if len(at) < 2:
        at.update({k: v for k, v in inferred.items() if k not in at})
    if len(at) < 2:
        return None
    return {"view": vi, "at": at, "from_step0": True,
            "source": f"step 0's fit landmarks on view {vi} (approved), not placed again: " + ", ".join(sorted(at))}
