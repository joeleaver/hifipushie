"""Step-4 row `turned_width`: a part turned back along a traced fold is as wide on the flat as the reference shows it.

Why (trial s4-27, the suit jacket, 2026-11-15): "the lapel is a little narrow": its ~65 mm was the FreeSewing block's
(jaeger), never read off the picture, though step 2 had traced both the roll line and the lapel's free edge (T15). The
flat gate checked the fold was declared (planned_folds), not how much cloth it turns back.

THE REFERENCE: each step-2 bend with a `trace` (its fold line traced: a roll line) and the edge trace of the same view
that runs past the fold trace's end (the front edge through the break). The turned part's width SEEN = the farthest
edge-trace point beside the fold (one whose nearest point on the fold trace is not an end) from the fold trace, in mm
on the body (structure_outline.placement: the view placed by its body marks). THE FLAT: the fold line on its piece
(pattern.fold_line), the outline points beside it (projecting inside its ends) split by side; the turned part is the
NARROWER side (a lapel, a cuff: the part turned back is the narrow one); its width = its farthest point from the line.
FAIL: the two differ by more than max(TOL_MM, two traced places at the view's scale + the marks' residual), naming the
piece, the fold, both widths and the mm to move its free edge. A trace the marks can't place: INFO (said why). The
seen width is a lapel lying on a curved chest: it reads a little short, inside the tolerance. Nothing knows a garment."""
from __future__ import annotations

import numpy as np

TOL_MM = 8.0  # mm: two traced places at ~1.5 mm/px plus the curve of the chest the lapel lies on


def _proj(X: np.ndarray, P: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(distance, interior) of each point of X to polyline P; interior: its nearest point isn't an end of P."""
    A, Bv = P[:-1], P[1:]
    d = Bv - A
    L2 = np.maximum((d * d).sum(1), 1e-18)
    t = ((X[:, None, :] - A[None]) * d[None]).sum(2) / L2[None]
    tc = np.clip(t, 0, 1)
    D = np.linalg.norm(X[:, None, :] - (A[None] + tc[..., None] * d[None]), axis=2)
    k = D.argmin(1)
    n = len(A)
    tk = t[np.arange(len(X)), k]
    inner = ~(((k == 0) & (tk <= 0)) | ((k == n - 1) & (tk >= 1)))
    return D[np.arange(len(X)), k], inner


def seen(style: dict, plan: dict, at: dict, fold_trace: str) -> dict:
    """{mm, edge, tol, how} of the part turned back along trace fold_trace, or {why}."""
    from . import structure_outline as so
    tr = {t.get("id"): t for t in style.get("traces") or [] if isinstance(t, dict)}
    f = tr.get(fold_trace)
    if not f:
        return {"why": f"trace {fold_trace!r} is not among step 2's traces"}
    vi = f.get("view", 0)
    try:
        pl = so.placement(so._view_of(plan, vi), so._marks(style, vi), at or {})
    except (ValueError, KeyError, IndexError, TypeError, np.linalg.LinAlgError) as e:
        return {"why": f"the body marks don't place view {vi}: {e}"}
    F = so.to_mm(f["points"], pl)
    best = None
    for t in tr.values():
        if t is f or t.get("view", 0) != vi or t.get("what") == f.get("what"):
            continue
        E = so.to_mm(t["points"], pl)
        near = min(_proj(F[[0, -1]], E)[0])
        if best is None or near < best[0]:
            best = (near, t, E)
    if best is None or best[0] > 4 * so.TRACE_PX * pl["s"] + pl["residual_mm"]:
        return {"why": f"no edge trace on view {vi} runs past {fold_trace}'s end (the free edge of the part it turns back)"}
    d, inner = _proj(best[2], F)
    if not inner.any():
        return {"why": f"no point of {best[1].get('id')} lies beside {fold_trace}"}
    return {"mm": float(d[inner].max()), "edge": best[1].get("id"), "tol": max(TOL_MM, 2 * so.TRACE_PX * pl["s"] +
            pl["residual_mm"]), "how": f"{best[1].get('id')} beside {fold_trace} on view {vi} ({pl['how']})"}


def flat(B: dict, f: dict) -> float | None:
    """The width (mm) of the narrower part of f's piece beside its fold line, or None."""
    from . import pattern
    try:
        L = np.asarray(pattern.fold_line(B["pieces"], f), float)
    except (KeyError, ValueError, IndexError, TypeError):
        return None
    P = np.asarray(B["pieces"][f["piece"]]["P"], float)
    d, inner = _proj(P, L)
    u = L[-1] - L[0]
    s = np.sign((P[:, 0] - L[0, 0]) * u[1] - (P[:, 1] - L[0, 1]) * u[0])
    w = [float(d[inner & (s == k)].max()) for k in (-1, 1) if (inner & (s == k)).any()]
    return 1000 * min(w) if w else None


def row(B: dict, decl: dict, step2: dict | None, look: dict | None) -> dict | None:
    """Row `turned_width` (module docstring); None when no planned fold has a trace."""
    style = (step2 or {}).get("output") or step2 or {}
    bends = [b for b in style.get("bends") or [] if isinstance(b, dict) and b.get("trace") and b.get("fold")]
    if not bends:
        return None
    vals, why, info = [], [], []
    for b in bends:
        f = next((x for x in B.get("folds") or [] if x.get("piece") == b.get("on") and x.get("name") == b["fold"]), None)
        if f is None:
            continue  # (the planned_folds row names a planned fold not declared)
        if not look or not look.get("plan"):
            info.append(f"{b['on']} {b['fold']}: the body's landmarks aren't available to place the trace")
            continue
        r = seen(style, look["plan"], look.get("at") or {}, b["trace"])
        w = flat(B, f)
        if "why" in r or w is None:
            info.append(f"{b['on']} {b['fold']}: " + (r.get("why") or "its fold line can't be drawn on the flat"))
            continue
        vals.append(f"{b['on']} {b['fold']}: turns back {w:.0f} mm, the reference {r['mm']:.0f} ({r['how']})")
        if abs(w - r["mm"]) > r["tol"]:
            k = r["mm"] - w
            why.append(f"{b['on']}'s {b['fold']} turns back a part {w:.0f} mm wide at most; the reference shows "
                       f"{r['mm']:.0f} mm ({r['edge']} beside {b['trace']}): {'widen' if k > 0 else 'narrow'} it by "
                       f"{abs(k):.0f} mm (move {b['on']}'s free edge beyond the fold {'out' if k > 0 else 'in'}; "
                       f"tolerance {r['tol']:.0f})")
    if not vals and not why:
        return {"id": "turned_width", "status": "INFO", "value": "not measured", "why": "; ".join(info),
                "target": "a traced fold's turned part as wide as the reference shows it"}
    return {"id": "turned_width", "status": "FAIL" if why else "PASS", "value": "; ".join(vals + info),
            "target": "a traced fold's turned part as wide on the flat as the reference shows it (its traces, mm on "
                      "the body)", "why": "; ".join(why), "back_to": "4",
            "fix": "move the free edge of the turned part (a lapel's front edge above the break) by the named mm"
                   if why else ""}
