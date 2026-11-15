"""Reshaping what is already there, the way a modeller's hands do it, instead of retyping a shape's numbers.

A modeller blocks a figure in as rough masses, then works on the figure itself: two lumps that are one form are
smoothed into each other, and an outline that is off is taken hold of and moved. These are those two acts.

fuse: two (or more) masses worked into one. Elements that carry the same "fuse" tag are joined first, smooth by
    "fill" metres (how far the two are worked into each other: the hollow between them fills by about a sixth of
    it; 0.05 leaves a soft crease, 0.25 makes one mass with a slight pinch), and blended into the rest of the
    model once (spec._fuse). The tools write the tag; by hand it is
        "blobs": {"head": {..., "fuse": "head+torso", "fill": 0.08}, "torso": {..., "fuse": "head+torso", "fill": 0.08}}
    "fill_sides": {side: 0..1} (front, back, left, right, up, down; front is where the figure faces) works in only
    that part of the fill on that side of the fuse's middle: {"front": 0.2} leaves a head smooth into the body
    behind and at the sides, and creased under the chin (spec._fuse_sides; the same fill all round can only trade
    a snowman's neck for a bean).
    `waist` measures the narrowest place between two stacked masses, so a fill can be set from the width the
    reference shows there (`solve_fill`).

grab: the move brush. spec["grabs"] = {label: {"of": [element names], "view": "front" | "side" | "top",
    "at": [u, v], "to": [u, v], "radius": metres}}. In that flat view (front: u, v = x, z; side: y, z, the figure
    facing -y; top: x, y) the clay of the masses `of` at `at` goes to `to`; clay within `radius` of `at` in the
    view follows by (1 - t^2)^2, all the way through the depth, so an outline is moved whole. Only the named
    masses move; they blend with their neighbours as before, so the surface stays one smooth piece. A grab moves
    clay by at most MOVE of its radius (further would fold the clay): a bigger move takes a bigger radius, or is
    a move of the mass itself. With symmetry on, a grab on a ".L" mass is made on its ".R" twin, and a grab made
    off the centre line of a centre mass is made on the other side too ("mirror": false turns that off).
"""
from __future__ import annotations

import numpy as np

from .deform import GRAB_AXES
from .spec import SpecError, mirror_name

STEEP = 1.54  # the falloff (1 - t^2)^2 changes by at most this much per radius
MOVE = 0.5  # the furthest a grab moves clay, as a part of its radius
BEND = 0.8  # the most a mass's grabs may bend space together (deform.stretch's own limit)


def check(label: str, g: dict) -> dict:
    """One grab, checked: raises SpecError saying what to give instead."""
    if not isinstance(g, dict):
        raise SpecError(f"grab {label!r}: {{\"of\": [masses], \"view\", \"at\": [u, v], \"to\": [u, v], \"radius\"}}")
    miss = [k for k in ("of", "view", "at", "to", "radius") if k not in g]
    if miss:
        raise SpecError(f"grab {label!r}: needs {', '.join(miss)}")
    if g["view"] not in GRAB_AXES:
        raise SpecError(f"grab {label!r}: view is \"front\" (points [x, z]), \"side\" ([y, z]) or \"top\" ([x, y])")
    for k in ("at", "to"):
        if not (isinstance(g[k], (list, tuple)) and len(g[k]) == 2):
            raise SpecError(f"grab {label!r}: {k} is two numbers in the view's own axes, read off look's rulers")
    r = float(g["radius"])
    if r <= 0:
        raise SpecError(f"grab {label!r}: radius is metres, more than 0")
    d = float(np.hypot(g["to"][0] - g["at"][0], g["to"][1] - g["at"][1]))
    if d > MOVE * r + 1e-9:
        raise SpecError(f"grab {label!r}: it moves the clay {d * 100:.1f} cm with a radius of {r * 100:.1f} cm. A grab "
                        f"moves clay by at most half its radius (further folds it): give a radius of {d / MOVE * 100:.1f} cm "
                        "or more, or move the mass itself (its joint or its `at`) and grab the rest")
    of = [g["of"]] if isinstance(g["of"], str) else list(g["of"])
    if not of:
        raise SpecError(f"grab {label!r}: of names the masses whose clay moves")
    return {"of": of, "view": g["view"], "at": [float(v) for v in g["at"]], "to": [float(v) for v in g["to"]],
            "radius": r, "mirror": bool(g.get("mirror", True))}


def effective(grabs: dict, symmetry: bool, names: list[str]) -> list[tuple[dict, set]]:
    """The grabs as they act on the mirrored model: [(grab op, the element names it moves)], twins included."""
    if not isinstance(grabs, dict):
        raise SpecError("grabs is {label: {\"of\", \"view\", \"at\", \"to\", \"radius\"}}")
    known, out = set(names), []
    for label, g in grabs.items():
        g = check(label, g)
        of = set(g["of"])
        gone = sorted(n for n in of if n not in known)
        if gone:
            raise SpecError(f"grab {label!r}: no mass called {', '.join(map(repr, gone))} (the model has: "
                            f"{', '.join(sorted(known)[:30])})")
        op = {k: g[k] for k in ("view", "at", "to", "radius")}
        twins = {mirror_name(n) for n in of if mirror_name(n) in known} if symmetry and g["mirror"] else set()
        if g["view"] == "side":  # the view looks along x: the same grab holds both sides
            out.append((op, of | twins))
            continue
        out.append((op, of))
        centre = of - {n for n in of if mirror_name(n) in known}
        off = abs(g["at"][0]) > 1e-6 or abs(g["to"][0]) > 1e-6
        if symmetry and g["mirror"] and (twins or (centre and off)):
            m = dict(op, at=[-g["at"][0], g["at"][1]], to=[-g["to"][0], g["to"][1]])
            out.append((m, twins | (centre if off else set())))
    return out


def stretch(ops: list[dict], names: list[str]) -> tuple[float, float]:
    """(lip, reach) of a set of grabs on the same masses: how much steeper than a distance the warped field can be,
    and how far the clay moves. The bound is the grabs' own (their sum), not a sample of the box."""
    bend = reach = 0.0
    for op in ops:
        g = op["grab"]
        d = float(np.hypot(g["to"][0] - g["at"][0], g["to"][1] - g["at"][1]))
        bend += STEEP * d / g["radius"]
        reach = max(reach, d)
    if bend >= BEND + 1e-9:
        raise SpecError(f"the grabs on {', '.join(names[:4])} together bend the clay too sharply ({bend:.2f}; the "
                        f"limit is {BEND}): give them bigger radii, move less, or take one off")
    return float(1.0 / (1.0 - min(bend, 0.95))), reach


# ---------------------------------------------------------------- the waist between two fused masses

def _pair(prims, a: str, b: str):
    def of(n):
        got = [p for p in prims if p.name in (n, mirror_name(n))]
        if not got:
            raise SpecError(f"no mass called {n!r} (the model has: {', '.join(sorted({p.name for p in prims})[:30])})")
        return got
    return of(a), of(b)


def _field(pa, pb, pts, fill: float, sides=None):
    from .sdf import SDF, sides_mul, smin, smin_var
    da = np.min([SDF[p.kind](pts, p.params) for p in pa], 0)
    db = np.min([SDF[p.kind](pts, p.params) for p in pb], 0)
    return smin(da, db, fill) if sides is None else smin_var(da, db, fill * sides_mul(sides, pts))


def waist(prims, a: str, b: str, fill: float, sides=None) -> dict | None:
    """The narrowest place between two masses that sit one above the other, with `fill` worked in: {"z", "width",
    "depth"} in metres (across x and across y, through the middle of the pair). None when the two are not stacked
    (one beside or in front of the other), or when nothing narrows between them."""
    pa, pb = _pair(prims, a, b)
    ca = np.mean([(p.lo + p.hi) / 2 for p in pa], 0)
    cb = np.mean([(p.lo + p.hi) / 2 for p in pb], 0)
    ax = cb - ca
    if abs(ax[2]) < 0.6 * np.linalg.norm(ax) or abs(ax[2]) < 1e-4:
        return None
    zs = np.linspace(min(ca[2], cb[2]), max(ca[2], cb[2]), 41)[1:-1]
    mid = (ca + cb) / 2
    R = float(max(np.max([p.hi - p.lo for p in pa + pb]), 0.05))
    t = np.linspace(-R, R, 801)
    span = np.zeros((len(zs), 2))
    for k, axis in enumerate((0, 1)):
        P = np.zeros((len(zs), len(t), 3))
        P[..., 0], P[..., 1] = mid[0], mid[1]
        P[..., axis] = mid[axis] + t[None, :]
        P[..., 2] = zs[:, None]
        inside = _field(pa, pb, P.reshape(-1, 3), fill, sides).reshape(len(zs), len(t)) < 0
        span[:, k] = inside.sum(1) * (t[1] - t[0])
        if axis == 1:  # how far the front (-y) and the back (+y) stand from the middle, each
            front = (inside & (t[None, :] < 0)).sum(1) * (t[1] - t[0])
    w = span[:, 0]
    i = int(np.argmin(w))
    if i in (0, len(zs) - 1) or w[i] >= min(w[0], w[-1]) - 1e-4:
        return None
    return {"z": float(zs[i]), "width": float(w[i]), "depth": float(span[i, 1]), "front": float(front[i]),
            "back": float(span[i, 1] - front[i])}


def solve_fill(prims, a: str, b: str, width: float, sides=None) -> tuple[float, str]:
    """The fill that makes the waist between a and b `width` metres across, and a line about it when it can't."""
    pa, pb = _pair(prims, a, b)
    ca = np.mean([(p.lo + p.hi) / 2 for p in pa], 0)
    cb = np.mean([(p.lo + p.hi) / 2 for p in pb], 0)
    top = 0.8 * float(np.linalg.norm(cb - ca))
    w0 = waist(prims, a, b, 0.0)
    if w0 is None:
        raise SpecError(f"{a!r} and {b!r} are not one above the other with a narrowing between them, so there is no "
                        "waist to set a width for: give fill in metres instead")
    if width <= w0["width"]:
        return 0.0, (f"they are already {w0['width'] * 100:.1f} cm across at their narrowest with nothing worked in: a "
                     "narrower waist is a matter of the masses' own sizes or places")
    lo, hi = 0.0, top
    wt = waist(prims, a, b, top, sides)
    if wt is not None and wt["width"] < width:
        return top, (f"with all the clay a fuse can work in the waist is {wt['width'] * 100:.1f} cm: for more, make the "
                     "masses overlap further or thicker there")
    for _ in range(18):
        m = (lo + hi) / 2
        wm = waist(prims, a, b, m, sides)
        if wm is None or wm["width"] >= width:
            hi = m
        else:
            lo = m
    return float(hi), ""
