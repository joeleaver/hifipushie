"""The model's side: the ring, `model`, its crease and brow. Part of the eye ruler (eye_ruler.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import eye_ruler
from .eye_ruler import frames, patch
from .eye_ruler_picture import _smooth1

# ---- the model -------------------------------------------------------------------------------------------------------
def _ring(ht, c):
    """The lid margin ring's vertex rows around the eye centred at c (skin rows next to the socket lining)."""
    from . import blockin_eyes_reader
    from . import base_identity
    g = base_identity._gnm_data()
    Vh = np.asarray(ht["verts"], float)
    F = blockin_eyes_reader._tris(ht["faces"])
    sk = np.flatnonzero(np.asarray(g["skin"]))
    sock = np.zeros(len(Vh), bool)
    sock[:len(sk)] = np.asarray(g["groups"]["eye_sockets"])[sk] > 0.5
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    m = sock[e[:, 0]] != sock[e[:, 1]]
    ring = np.unique(np.where(sock[e[m, 0]], e[m, 1], e[m, 0]))
    ring = ring[np.linalg.norm(Vh[ring] - c, axis=1) < 2.0 * float(ht["eye_r"])]
    Fs = F[np.all(~sock[F], axis=1)]
    return ring, Fs[np.all(np.linalg.norm(Vh[Fs] - c, axis=2) < 0.04, axis=1)]


def model(spec: dict, cam: dict, brows: bool = True, px_mm: float = eye_ruler.STEP) -> list:
    """The measures on the model (its spec) through a fitted camera, per eye (subject's right, left), same keys as
    read() + "c" (the iris centre in picture px), "gap" (mm of socket lining showing between the lid margin ring and
    the eyeball, per COLS, upper / lower), "ring" (the margin ring in the eye frame), "platform" (the lid skin under
    the fold that a front view shows), "crease_depth". brows=False skips the brow decal's read."""
    from . import humanfit
    from . import humanfit_views
    from . import likeness_render
    base = spec["base"]
    st = humanfit.state(base)
    ht = st["head"]
    mesh = likeness_render.model_mesh_from_state(st)
    mm = likeness_render._mm_per_px(cam, st["L"][27:48])
    fwd = np.asarray(ht.get("forward", [0, -1, 0]), float)
    r = float(ht["eye_r"])
    eyes = sorted([np.asarray(c, float) for c in ht["eyes"]], key=lambda c: c[0])      # subject's right (-x) first
    poles = humanfit_views.project(cam, np.array([c + 0.985 * r * fwd for c in eyes]))
    fr2 = frames(poles[0], poles[1])
    pad = 26.0 / mm
    lo_, hi_ = poles.min(0) - pad, poles.max(0) + pad
    box = (lo_[0], lo_[1] - 6.0 / mm, hi_[0], hi_[1])
    kk = mm / px_mm                                  # raster px per picture px
    _, k, ps = likeness_render.render(mesh, cam, box, px=int(round((box[2] - box[0]) * kk)), brows=False, passes=True)
    part = ps["part"]
    from . import base_implied
    r_iris = 1000.0 * base_implied.drawn_iris(spec, r)   # the dressing's own iris (skin.eyes.iris_size), else GNM's limbus
    # for the identity (its eyeball: eyes_000), else our own ball's 0.51 r
    Vh = np.asarray(ht["verts"], float)
    out = []
    for s in (0, 1):
        fr = {"c": (fr2[s]["c"] - np.array(box[:2])) * k, "ex": fr2[s]["ex"], "ey": fr2[s]["ey"]}
        M = patch((part == 1).astype(float)[..., None], fr, k / mm)[..., 0] > 0.5
        ring, tri = _ring(ht, eyes[s])
        d = (humanfit_views.project(cam, Vh[ring]) - fr2[s]["c"]) * mm
        ruv = np.c_[d @ fr2[s]["ex"], -(d @ fr2[s]["ey"])]
        anyc = M.any(0)
        ucols = eye_ruler.U[anyc]
        top = np.array([eye_ruler.V[np.flatnonzero(M[:, j])[-1]] + eye_ruler.STEP / 2 for j in np.flatnonzero(anyc)])
        bot = np.array([eye_ruler.V[np.flatnonzero(M[:, j])[0]] - eye_ruler.STEP / 2 for j in np.flatnonzero(anyc)])
        # the inner canthus: the ring's medial end (the caruncle's corner). The outer one: where the visible eyeball
        # ends (the ring's own lateral end is tucked ~1 mm behind the lids' meeting: nothing a picture shows)
        ii = int(np.argmin(ruv[:, 0]))
        inner, outer = ruv[ii], np.array([ucols[-1], 0.5 * (top[-1] + bot[-1])])

        def at(arr, x):
            return float(np.interp(x, ucols, arr, left=np.nan, right=np.nan))
        m = {"inner": inner.tolist(), "outer": outer.tolist(), "sclera_in": float(ucols[0]), "sclera_out": float(ucols[-1]),
             "fissure": float(np.linalg.norm(outer - inner)),
             "tilt": float(np.degrees(np.arctan2(outer[1] - inner[1], outer[0] - inner[0]))),
             "caruncle": float(ucols[0] - inner[0]), "up": [at(top, x) for x in eye_ruler.COLS], "lo": [at(bot, x) for x in eye_ruler.COLS],
             "iris": 2 * r_iris, "c": fr2[s]["c"].tolist(), "ring": ruv.tolist()}
        li = (humanfit_views.project(cam, np.asarray(st["L"][39 if s == 0 else 42], float)[None])[0] - fr2[s]["c"]) * mm
        m["inner_lm"] = [float(li @ fr2[s]["ex"]), -float(li @ fr2[s]["ey"])]   # GNM's own inner-corner landmark: the
        # canthal pocket's tip (the caruncle's corner), ~1.9 mm medial of the ring's end
        m["open"] = [a - b for a, b in zip(m["up"], m["lo"])]
        sm = _smooth1(top, 0.6)
        m["peak_u"], m["peak_v"] = float(ucols[int(np.argmax(sm))]), float(sm.max())
        m["mrd1"], m["mrd2"] = m["up"][3], -m["lo"][3]
        m["cover_up"], m["cover_lo"] = r_iris - m["mrd1"], r_iris - m["mrd2"]
        # the ring against the eyeball: lining that shows between the margin and the ball
        ang = np.arctan2(ruv[:, 1] - ruv[:, 1].mean(), ruv[:, 0] - ruv[:, 0].mean())
        o = np.argsort(ang)
        poly = ruv[o]
        gu, gl = [], []
        for x in eye_ruler.COLS:
            ys = _poly_cross(poly, x)
            if len(ys) < 2 or not np.isfinite(at(top, x)):
                gu.append(float("nan"))
                gl.append(float("nan"))
                continue
            gu.append(max(ys) - at(top, x))
            gl.append(at(bot, x) - min(ys))
        m["gap"] = {"up": gu, "lo": gl}
        m.update(_model_crease(ht, tri, eyes[s], r, fwd, s))
        out.append(m)
    if brows:
        _model_brow(out, st, cam, spec, fr2, mm)
    else:
        for m in out:
            m["brow"] = [float("nan")] * len(eye_ruler.COLS)
    return out


def _poly_cross(poly, x):
    ys = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[0] - x) * (b[0] - x) < 0:
            t = (x - a[0]) / (b[0] - a[0])
            ys.append(a[1] + t * (b[1] - a[1]))
    return ys


def _model_crease(ht, tri, c, r, fwd, s) -> dict:
    """The fold's height over the margin (blockin_eyes' sagittal profile reader: the deepest narrow valley 2-12 mm up)
    and the platform visible from the front, at COLS (world x = the eye centre's + u toward the outer corner)."""
    from . import blockin_eyes_reader
    Vh = np.asarray(ht["verts"], float)
    up = np.array([0, 0, 1.0]) - fwd * fwd[2]
    up /= np.linalg.norm(up)
    sg = -1.0 if s == 0 else 1.0
    cr, show, dep = [], [], []
    for x in eye_ruler.COLS:
        best = None
        for L in blockin_eyes_reader._chain(blockin_eyes_reader._slice(Vh, tri, float(c[0] + sg * x * 0.001))):
            d = np.linalg.norm(L - c, axis=1)
            ok = (d > r + 0.0003) & ((L - c) @ up > -0.001) & ((L - c) @ fwd > 0) & ((L - c) @ up < 0.03)
            runs, cur = [], []
            for i, o in enumerate(ok):
                if o:
                    cur.append(i)
                elif cur:
                    runs.append(cur)
                    cur = []
            if cur:
                runs.append(cur)
            for rr in runs:
                if best is None or len(rr) > len(best[1]):
                    best = (L, rr)
        if best is None or len(best[1]) < 4:
            cr.append(float("nan"))
            show.append(float("nan"))
            dep.append(float("nan"))
            continue
        L, rr = best
        P = np.c_[(L[rr] - c) @ fwd, (L[rr] - c) @ up]
        if P[0, 1] > P[-1, 1]:
            P = P[::-1]
        q = blockin_eyes_reader._profile(P)
        cr.append(float(q["height"]))
        show.append(float(q["show"]))
        dep.append(float(q["local"]))
    return {"crease": cr, "platform": show, "crease_depth": dep,
            "crease_dark": float(np.nanmedian(dep)) if np.isfinite(dep).any() else 0.0}


def _model_brow(out, st, cam, spec, fr2, mm) -> None:
    """The brow decal's lower edge (blockin_brows.model_band: calibrated on a dressed render) over the model's upper
    margin at COLS."""
    from . import blockin_brows as bb, skin_look
    hb = ((spec.get("skin") or {}).get("hair") or {}).get("brows")
    o = dict(hb) if isinstance(hb, dict) else {}
    ex, ey = -fr2[0]["ex"], fr2[0]["ey"]
    xs = [np.array([(fr["c"] + x / mm * fr["ex"]) @ ex for x in eye_ruler.COLS]) for fr in fr2]
    mb = bb.model_band(skin_look._J(spec), np.asarray(st["tpl"]["P"], float), cam, o,
                       float(o.get("thickness", bb.default_thickness(spec))), xs, ex, ey)
    for s in (0, 1):
        v = (fr2[s]["c"] @ ey - np.asarray(mb[s]["low"], float)) * mm
        out[s]["brow"] = (v - np.asarray(out[s]["up"], float)).tolist()
