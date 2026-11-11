"""Per-picture expression: each view's expression and base, fit_expression. Part of the block-in (blockin.py has the overview)."""
from __future__ import annotations

import copy
import json

import numpy as np

from . import blockin

def view_expression(rj: dict, vi: int) -> dict:
    ex = rj.get("expressions") or []
    return dict(ex[vi] or {}) if vi < len(ex) else {}


def view_base(base: dict, rj: dict, vi: int) -> dict:
    """The base as that picture shows it: base.head.expression + the view's fitted expression (added)."""
    ex = view_expression(rj, vi)
    if not ex:
        return base
    b = copy.deepcopy(base)
    e = dict(b["head"].get("expression") or {})
    for k, v in ex.items():
        e[k] = float(e.get(k, 0.0)) + float(v)
    b["head"]["expression"] = e
    return b


def _per_view(base: dict, rj: dict, VI, make) -> dict:
    """{vi: make(view base)}, one build per distinct expression (views without one share the neutral)."""
    out, by = {}, {}
    for vi in VI:
        key = json.dumps(view_expression(rj, vi), sort_keys=True)
        if key not in by:
            by[key] = make(view_base(base, rj, vi))
        out[vi] = by[key]
    return out


def _expr_names(comps: dict | None = None) -> list:
    from . import base_identity
    names = [str(n) for n in base_identity._gnm_data()["expression_names"]]
    out = []
    for reg, n in (comps or blockin.EXPR_COMPS).items():
        out += [nm for nm in names if nm.rsplit("_", 1)[0] == reg][:int(n)]
    return out


def fit_expression(base: dict, view: dict, cam: dict, comps: dict | None = None, sd: dict | None = None,
                   iters: int = 3) -> dict:
    """One picture's expression on this head (identity and camera held): GNM expression comps (EXPR_COMPS, prior
    N(0, EXPR_SD per region)) by Gauss-Newton on the calibrated detector evidence (humanfit_map._evidence), the
    Jacobian by finite differences at the start (chord iterations: the response is near linear). ~(n + 4) head builds.
    Returns {"expression", "chi2": [before, after], "points", "norm"}."""
    from . import humanfit, humanfit_map as hm
    names = _expr_names(comps)
    sd = {**blockin.EXPR_SD, **(sd or {})}
    prec = np.array([1.0 / float(sd[n.rsplit("_", 1)[0]]) ** 2 for n in names])
    rj1 = {"expressions": [None]}

    def resid(e):
        rj1["expressions"][0] = {n: float(x) for n, x in zip(names, e) if x}
        st = humanfit.state(view_base(base, rj1, 0))
        ev = hm._evidence(st, hm._resolve(st, [view]))[0]
        mm = cam["t"][2] / cam["f"] * 1000
        return ((humanfit.project(cam, ev["X"]) - ev["uv"]) * (mm / ev["sig"])[:, None]).ravel()

    e = np.zeros(len(names))
    r = r_start = resid(e)
    h = 0.25
    J = np.stack([(resid(np.eye(len(names))[k] * h) - r) / h for k in range(len(names))], 1)
    A = J.T @ J + np.diag(prec)
    for _ in range(iters):
        de = np.linalg.solve(A, -(J.T @ r) - prec * e)
        e = e + de
        r = resid(e)
        if np.linalg.norm(de) < 0.02:
            break
    ex = {n: round(float(x), 4) for n, x in zip(names, e) if abs(x) >= 1e-3}
    return {"expression": ex, "chi2": [round(float(r_start @ r_start), 1), round(float(r @ r), 1)],
            "points": len(r) // 2, "norm": round(float(np.linalg.norm(e)), 3)}
