"""Lids by measure: the lid read on the photo and the model, lid_read, lid_match. Part of the block-in (blockin.py has the overview)."""
from __future__ import annotations

import copy

import numpy as np

from . import blockin_models
from .blockin_clay import _front, detect_view
from .blockin_expression import view_base, view_expression
from .blockin_steps import step

# ---------------------------------------------------------------- lids by measure
def _iris_radius_px(P, rim, c):
    return float(np.mean(np.linalg.norm(P[rim] - P[c], axis=1)))


def lid_photo(img, view: dict | None = None) -> dict | None:
    """The photo's lid margins against the iris (MediaPipe iris 468 / 473 and radius, upper lid 159 / 386, lower
    145 / 374), in iris radii from the iris centre (MRD1 / MRD2 style, scale-free), and the opening's aspect."""
    P = detect_view(img, view or {})
    if P is None:
        return None
    P = np.asarray(P, float)[:, :2]
    if len(P) < 478:
        return None
    out = {}
    for s, (c, rim, up, lo, a, b) in {"R": (468, [469, 470, 471, 472], 159, 145, 33, 133),
                                      "L": (473, [474, 475, 476, 477], 386, 374, 263, 362)}.items():
        r = _iris_radius_px(P, rim, c)
        out[s] = {"upper": float((P[c, 1] - P[up, 1]) / r), "lower": float((P[lo, 1] - P[c, 1]) / r),
                  "aspect": float(np.linalg.norm(P[a] - P[b]) / max(P[lo, 1] - P[up, 1], 1e-6))}
    return out


def lid_model(base: dict, cam: dict) -> dict:
    """The model's lid margins read the same way on its front render: the visible eyeball (render part 1) in the column
    through the iris centre (the eyeball's forward pole), in the drawn iris cap's projected radius."""
    from . import humanfit
    from . import likeness_render
    st = humanfit.state(base)
    mesh = likeness_render.model_mesh_from_state(st)
    P = humanfit.project(cam, st["L"])
    c = 0.5 * (P.min(0) + P.max(0))
    s = 1.4 * float(np.max(P.max(0) - P.min(0)))
    box = (c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2)
    _, k, ps = likeness_render.render(mesh, cam, box, px=1400, brows=False, passes=True)
    fwd = np.asarray(st["head"].get("forward", [0, -1, 0]), float)
    r = float(st["head"].get("eye_r", 0.012)) * 0.985
    out = {}
    for ce in st["head"]["eyes"]:
        ce = np.asarray(ce, float)
        pole = humanfit.project(cam, (ce + r * fwd)[None])[0]
        u = np.cross(fwd, [0, 0, 1.0])
        u /= np.linalg.norm(u)
        ring = [ce + r * (0.86 * fwd + 0.51 * (np.cos(t) * u + np.sin(t) * np.array([0, 0, 1.0])))
                for t in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
        R_ = float(np.mean(np.linalg.norm(humanfit.project(cam, np.array(ring)) - pole, axis=1))) * k
        x, y = (pole[0] - box[0]) * k, (pole[1] - box[1]) * k
        xi = int(round(x))
        if not (0 <= xi < ps["part"].shape[1]):
            continue
        col = np.flatnonzero(ps["part"][:, xi] == 1)
        col = col[np.abs(col - y) < 4 * R_]
        if len(col) == 0:
            continue
        a, b = (42, 45) if ce[0] > 0 else (36, 39)   # the eye's corners: the model's own landmarks, as the photo's
        wpx = float(np.linalg.norm(P[a] - P[b])) * k
        out["L" if ce[0] > 0 else "R"] = {"upper": float((y - col.min()) / R_), "lower": float((col.max() - y) / R_),
                                          "aspect": wpx / max(float(col.max() - col.min()), 1.0)}
    return out


def lid_read(name: str) -> dict:
    """{"photo": {R/L: {upper, lower, aspect}}, "model": {...}, "pose": base.head.pose} on the front picture."""
    from PIL import Image
    from . import store
    rj = blockin_models._refs(name)
    vi = _front(rj)
    v = rj["views"][vi]
    base = store.load(name)["base"]
    return {"view": vi, "photo": lid_photo(Image.open(v["image"]).convert("RGB"), v),
            "model": lid_model(view_base(base, rj, vi), rj["cameras"][vi]), "pose": dict(base["head"].get("pose") or {}),
            "expression": bool(view_expression(rj, vi))}


def lid_text(r: dict) -> str:
    s = [f"lid margins vs the iris (in iris radii from its centre; front view {r['view']}): upper (MRD1-like), lower "
         "(MRD2-like), aspect = opening width / height"]
    for side in ("R", "L"):
        p = (r["photo"] or {}).get(side)
        m = (r["model"] or {}).get(side)
        f = lambda d: "-" if d is None else f"upper {d['upper']:.2f} lower {d['lower']:.2f} aspect {d['aspect']:.2f}"  # noqa: E731
        s.append(f"  {side}: photo {f(p)} | model {f(m)}")
    s.append(f"  pose now: {r['pose'] or '{}'} (lid_upper / lid_lower, m: -0.001 = that lid 1 mm up)"
             + ("; model read WITH the picture's fitted expression" if r.get("expression") else ""))
    if r["photo"] is None:
        s.append("  (the detector found no face on the front picture: no photo read)")
    return "\n".join(s)


def lid_match(name: str, out: str | None = None, seen: str = "") -> dict:
    """Lids by measure: lid_upper / lid_lower set so the model's margins (mean of both eyes) equal the photo's: two
    secant steps each (the read is ~linear in the pose), written as a block-in step."""
    from . import store
    r = lid_read(name)
    if not r["photo"]:
        raise ValueError("lid_match: no photo lid read (the detector missed the front picture)")
    tgt = {k: float(np.mean([r["photo"][s][k] for s in r["photo"]])) for k in ("upper", "lower")}
    rj = blockin_models._refs(name)
    cam = rj["cameras"][r["view"]]
    base = copy.deepcopy(store.load(name)["base"])
    pose = base["head"].setdefault("pose", {})

    def read(p):
        base["head"]["pose"] = {**pose, **p}
        m = lid_model(view_base(base, rj, r["view"]), cam)   # (the picture's expression on top, if fitted)
        return {k: float(np.mean([m[s][k] for s in m])) for k in ("upper", "lower")}
    p = {"lid_upper": float(pose.get("lid_upper", 0.0)), "lid_lower": float(pose.get("lid_lower", 0.0))}
    sgn = {"lid_upper": ("upper", -1.0), "lid_lower": ("lower", 1.0)}   # lid_upper - = up: the upper margin grows
    cur = read(p)
    for key, (m, s) in sgn.items():
        for _ in range(2):
            h = 0.0005
            q = {**p, key: p[key] + s * h}
            alt = read(q)
            slope = (alt[m] - cur[m]) / h
            if abs(slope) < 1e-6:
                break
            p[key] = float(np.clip(p[key] + s * (tgt[m] - cur[m]) / slope, -0.004, 0.004))
            cur = read(p)
    rep = step(name, {k: round(v, 5) for k, v in p.items()}, out=out, seen=seen or "lid margins vs the iris",
               why=f"lids by measure: photo upper {tgt['upper']:.2f} lower {tgt['lower']:.2f} iris radii; model now "
                   f"{cur['upper']:.2f} / {cur['lower']:.2f}")
    rep["lids"] = {"target": tgt, "model": cur, "pose": p}
    return rep
