"""Reshaping what is already there, the way a modeller's hands do it, instead of retyping a shape's numbers.

A modeller blocks a figure in as rough masses, then works on the figure itself: two lumps that are one form are
smoothed into each other, and an outline that is off is taken hold of and moved. These are those two acts.

fuse: two (or more) masses worked into one. Elements that carry the same "fuse" tag are joined first, each by
    its own "fill" (how far that mass is worked into the others, the widest first), smooth by
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
    facing -y; top: x, y) the clay of the masses `of` at `at` goes to `to`; clay within `radius` of the point
    taken hold of follows by (1 - t^2)^2: a ball, centred in depth at the middle of the named clay on the view's
    ray through `at` (the outline's own depth when `at` is on the outline). Through the whole depth instead, a pull
    on a chin drew a shelf across the face and a push on a back cut a trench across it (p5, p6). Only the named
    masses move; they blend with their neighbours as before, so the surface stays one smooth piece. A grab moves
    clay by at most MOVE of its radius (further would fold the clay): a bigger move takes a bigger radius, or is
    a move of the mass itself. With symmetry on, a grab on a ".L" mass is made on its ".R" twin, and a grab made
    off the centre line of a centre mass is made on the other side too ("mirror": false turns that off).

trim: the knife. spec["trims"] = {label: {"of": [element names] | "all", "view", "a": [u, v], "b": [u, v],
    "off": "up" | "down" | "left" | "right" | "front" | "back", "soft": metres}}. In that flat view a straight line
    runs through a and b; the clay of the masses `of` on the `off` side of it is cut away, all the way through the
    depth, flat (a sole under a hoof, the flat front of a snout, a seat). `soft` rounds the cut's edge (0: knife
    sharp). The cut is made where the figure stands now: after the grabs, in the view's own coordinates. Mirrored
    as a grab is. A mass used as a cutter instead of a line is the spec's own "op": "subtract" with "targets"
    (the carve tool sets it).

flap: no kind of its own: the flap tool writes a "sheet" (sheet.py) from three points read off the pictures.
"""
from __future__ import annotations

import numpy as np

from .deform import GRAB_AXES
from .spec import SpecError, mirror_name

STEEP = 1.54  # the falloff (1 - t^2)^2 changes by at most this much per radius
MOVE = 0.5  # the furthest a grab moves clay, as a part of its radius
BEND = 0.8  # the most a mass's grabs may bend space together (deform.stretch's own limit)
BROAD = 0.2  # the grab TOOL: clay moves by at most this part of the radius (a broad, gentle move of a form) ...
MASS = 0.3  # ... and the radius is at least this part of the mass it moves, across the view


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


def broad(label: str, g: dict, across: dict) -> None:
    """The grab tool's own check, on top of `check`: a grab is a BROAD move of a mass's form. across: {mass: its
    smaller size in the grab's view, m}. Raises SpecError saying the radius it needs and what the job is otherwise.
    Why: in four blind blockouts grabs of a few centimetres with a radius near their own size chased an outline's
    last centimetre and left a shelf under a snout, a trench across a back, saddlebags, a crease across a belly
    (p5, p6, p8: 0.24 to 0.45 of the radius); the one that did no harm moved 0.16 of its radius (p7)."""
    d = float(np.hypot(g["to"][0] - g["at"][0], g["to"][1] - g["at"][1]))
    r = float(g["radius"])
    big = max(across, key=across.get) if across else None
    need = max(d / BROAD, MASS * across[big] if big else 0.0)
    if r >= need - 1e-9:
        return
    on = f" ({big} is {across[big] * 100:.0f} cm across in this view)" if big else ""
    raise SpecError(f"grab {label!r}: it moves the clay {d * 100:.1f} cm with a radius of {r * 100:.1f} cm. A grab is a BROAD "
                    f"move of a mass's form: the clay goes at most a fifth of the radius, and the radius is at least "
                    f"{MASS:g} of the mass it moves{on}. Give a radius of {need * 100:.1f} cm or more. A smaller bump or "
                    "dent than that is a later pass's work, and an outline that is off along a mass is the mass's own "
                    "size, place or shape (or a fuse, a flap, a trim): change that instead of pulling at it")


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
        if g["view"] == "side":  # the view looks along x: the same grab holds both sides, each at its own depth
            out.append((op, of))
            if twins - of:
                out.append((dict(op), twins - of))
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
    gs = [op["grab"] for op in ops]
    ds = [float(np.hypot(g["to"][0] - g["at"][0], g["to"][1] - g["at"][1])) for g in gs]
    reach = max(ds, default=0.0)

    def centre(g):  # where the grab's ball is, once spec._grabs has found its depth
        dep, i, j = GRAB_AXES[g["view"]]
        c = np.zeros(3)
        c[i], c[j], c[dep] = g["at"][0], g["at"][1], g["depth"]
        return c

    def meet(a, b):  # two grabs bend the same clay unless their balls are apart (a grab and its mirror image)
        if a.get("depth") is not None and b.get("depth") is not None:
            return float(np.linalg.norm(centre(a) - centre(b))) < a["radius"] + b["radius"]
        return a["view"] != b["view"] or np.hypot(a["at"][0] - b["at"][0], a["at"][1] - b["at"][1]) < a["radius"] + b["radius"]
    bend = max((sum(STEEP * ds[j] / gs[j]["radius"] for j in range(len(gs)) if j == i or meet(gs[i], gs[j]))
                for i in range(len(gs))), default=0.0)
    if bend >= BEND + 1e-9:
        raise SpecError(f"the grabs on {', '.join(names[:4])} together bend the clay too sharply ({bend:.2f}; the "
                        f"limit is {BEND}): give them bigger radii, move less, or take one off")
    return float(1.0 / (1.0 - min(bend, 0.95))), reach


# ---------------------------------------------------------------- trims

SIDES = {"front": (1, -1.0), "back": (1, 1.0), "left": (0, 1.0), "right": (0, -1.0), "up": (2, 1.0), "down": (2, -1.0)}


def check_trim(label: str, t: dict) -> dict:
    """One trim, checked: {"of", "point", "normal" (3D, toward the clay that goes), "soft", ...}."""
    if not isinstance(t, dict):
        raise SpecError(f"trim {label!r}: {{\"of\": [masses], \"view\", \"a\": [u, v], \"b\": [u, v], \"off\"}}")
    miss = [k for k in ("of", "view", "a", "b", "off") if k not in t]
    if miss:
        raise SpecError(f"trim {label!r}: needs {', '.join(miss)}")
    if t["view"] not in GRAB_AXES:
        raise SpecError(f"trim {label!r}: view is \"front\" (points [x, z]), \"side\" ([y, z]) or \"top\" ([x, y])")
    for k in ("a", "b"):
        if not (isinstance(t[k], (list, tuple)) and len(t[k]) == 2):
            raise SpecError(f"trim {label!r}: {k} is two numbers in the view's own axes, read off look's rulers")
    a, b = np.array(t["a"], float), np.array(t["b"], float)
    run = b - a
    if np.hypot(*run) < 1e-6:
        raise SpecError(f"trim {label!r}: a and b are the same point: the line runs through two different points")
    if t["off"] not in SIDES:
        raise SpecError(f"trim {label!r}: off is the side of the line that is cut away: {', '.join(SIDES)}")
    _, i, j = GRAB_AXES[t["view"]]
    ax, sgn = SIDES[t["off"]]
    ok = [w for w, (x, _) in SIDES.items() if x in (i, j)]
    if ax not in (i, j):
        raise SpecError(f"trim {label!r}: in the {t['view']} view a line has no {t['off']} side (that is the view's "
                        f"own depth): off is one of {', '.join(ok)}")
    n2 = np.array([-run[1], run[0]]) / np.hypot(*run)  # square to the line, in the view
    want = sgn * n2[0 if ax == i else 1]
    if abs(want) < 0.25:
        other = [w for w in ok if SIDES[w][0] != ax]
        raise SpecError(f"trim {label!r}: the line runs {t['off']} and {[w for w in ok if SIDES[w][0] == ax and w != t['off']][0]}"
                        f", so neither side of it is the {t['off']} one: off is {' or '.join(other)}")
    n2 = n2 * np.sign(want)
    point, normal = np.zeros(3), np.zeros(3)
    point[[i, j]], normal[[i, j]] = a, n2
    soft = float(t.get("soft", 0.004))
    if soft < 0:
        raise SpecError(f"trim {label!r}: soft is how far the cut's edge is rounded, in metres: 0 or more")
    of = t["of"] if t["of"] == "all" else ([t["of"]] if isinstance(t["of"], str) else list(t["of"]))
    if not of:
        raise SpecError(f"trim {label!r}: of names the masses that are cut (or \"all\")")
    return {"of": of, "view": t["view"], "a": [float(v) for v in a], "b": [float(v) for v in b], "off": t["off"],
            "soft": soft, "mirror": bool(t.get("mirror", True)), "point": point, "normal": normal}


def trims_effective(trims: dict, symmetry: bool, names: list[str]) -> list[tuple[np.ndarray, np.ndarray, float, set]]:
    """The trims as they act on the mirrored model: [(a point on the cut, its normal toward the clay that goes,
    soft, the element names it cuts)], twins included."""
    if not isinstance(trims, dict):
        raise SpecError("trims is {label: {\"of\", \"view\", \"a\", \"b\", \"off\"}}")
    known, out = set(names), []
    for label, t in trims.items():
        t = check_trim(label, t)
        of = set(known) if t["of"] == "all" else set(t["of"])
        gone = sorted(n for n in of if n not in known)
        if gone:
            raise SpecError(f"trim {label!r}: no mass called {', '.join(map(repr, gone))} (the model has: "
                            f"{', '.join(sorted(known)[:30])})")
        twins = {mirror_name(n) for n in of if mirror_name(n) in known} if symmetry and t["mirror"] else set()
        p, n = t["point"], t["normal"]
        if t["view"] == "side" or not (symmetry and t["mirror"]):  # the view looks along x: one cut holds both sides
            out.append((p, n, t["soft"], of | twins))
            continue
        flip = np.array([-1.0, 1.0, 1.0])
        if abs(n[0]) < 1e-9:  # a cut that does not lean left or right is its own mirror image
            out.append((p, n, t["soft"], of | twins))
            continue
        out.append((p, n, t["soft"], of))
        centre = of - {m for m in of if mirror_name(m) in known}
        out.append((p * flip, n * flip, t["soft"], twins | centre))
    return out


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
