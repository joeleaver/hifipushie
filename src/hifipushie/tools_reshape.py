"""Reshaping tools: what a modeller's hands do to a blockout that typing a shape's numbers can't.
`fuse` works two masses into one flowing mass; `grab` takes hold of clay that is already there and moves it;
`trim` cuts clay away along a line drawn in a flat view and `carve` takes one mass out of others; `flap` makes
a leaf of clay that grows out, arches over and hangs, from three points (reshape.py is the spec)."""
from __future__ import annotations

import copy

import numpy as np

from . import reshape, store
from .mcp_app import mcp
from .spec import compile_prims


def _elements(spec: dict) -> dict:
    return {**(spec.get("bones") or {}), **(spec.get("blobs") or {})}


def _need(spec: dict, names) -> dict:
    els = _elements(spec)
    gone = [n for n in names if n not in els]
    if gone:
        raise ValueError(f"no mass called {', '.join(map(repr, gone))}. This model's masses: {', '.join(els)} "
                         "(name the centre or the \".L\" one of a mirrored pair)")
    return els


def _with_look(name: str, views: list[str], text: str):
    from .tools_model import look
    out = look(name, views=views, paint=False)
    if isinstance(out, (list, tuple)):
        return [*out[:-1], text + "\n" + str(out[-1])]
    return text + "\n" + str(out)


@mcp.tool(structured_output=False)
def fuse(name: str, a: str, b: str, fill: float | None = None, width: float | None = None,
         sides: dict | None = None, note: str = ""):
    """Work two masses into ONE flowing mass, as a modeller smooths two lumps of clay together: the hollow between `a`
    and `b` fills and the line between them goes (a head and body that should read as one pear, not two balls with
    a neck crease). Give fill (how far the two are worked into each other, in metres: 0.05 leaves a soft crease,
    0.15 a clear waist, 0.25 one mass with a slight pinch) OR width (how wide the figure is at its narrowest between the two, in metres, read off the
    reference: the fill is found for you). sides: {"front": 0.2} works in only that part of the fill on
    that side (front, back, left, right, up, down): smooth behind and creased in front, which the same fill all
    round can't give (it trades a snowman's neck for a bean). fill=0 parts them again. Returns the look and the
    waist as measured. Details: guide(topic="fuse")."""
    spec = store.load(name)
    els = _need(spec, (a, b))
    if a == b:
        raise ValueError("a and b are two different masses")
    if (fill is None) == (width is None):
        raise ValueError("give fill (how far the two are worked into each other, in metres) or width (metres across at the narrowest "
                         "place between them, read off the reference): one of the two")
    bare = copy.deepcopy(spec)  # the masses with no fuse at all: the pair is measured by itself
    for e in _elements(bare).values():
        for k in ("fuse", "fill", "fill_sides"):
            e.pop(k, None)
    prims0 = compile_prims(bare)
    how = None
    if sides:  # the sides as the compiler reads them (their middle and size come from the two masses)
        from .spec import _fuse_sides
        how = _fuse_sides(f"{a}+{b}", sides, [p for p in prims0 if p.name in (a, b)])
    k0 = max(float(els[n].get("blend", spec.get("blend", 0.03)) or 0.0) for n in (a, b))
    before = reshape.waist(prims0, a, b, k0)
    said = ""
    if width is not None:
        fill, said = reshape.solve_fill(prims0, a, b, float(width), how)
    fill = float(fill)
    if fill < 0:
        raise ValueError("fill is how far the two are worked into each other, in metres: 0 (parted) or more")
    old = [els[n].get("fuse") for n in (a, b) if els[n].get("fuse")]
    others = ""
    if fill == 0:
        # a mass that was in a fuse with others too leaves only when it is the one named second (b); a pair parts
        both = len({els[n].get("fuse") for n in (a, b)}) == 1 and old
        out = (a, b) if both and sum(e.get("fuse") == old[0] for e in _elements(spec).values()) == 2 else (b,)
        for n in out:
            for k in ("fuse", "fill", "fill_sides"):
                els[n].pop(k, None)
        for t in old:  # a tag left on one mass alone means nothing
            left = [e for e in _elements(spec).values() if e.get("fuse") == t]
            if len(left) == 1:
                for k in ("fuse", "fill", "fill_sides"):
                    left[0].pop(k, None)
    else:
        tag = old[0] if old else f"{a}+{b}"
        new = [n for n in (a, b) if not els[n].get("fuse")]  # a mass coming into the fuse; both, for a new pair
        for e in _elements(spec).values():  # two fuses become one; every mass keeps its own fill
            if e.get("fuse") in old:
                e["fuse"] = tag
        for n in (new or (a, b)):  # (both already in it: this is their join being set again)
            els[n]["fuse"], els[n]["fill"] = tag, round(fill, 4)
            els[n].pop("fill_sides", None)
            if sides:
                els[n]["fill_sides"] = {k: float(v) for k, v in sides.items()}
        rest = {n: e for n, e in _elements(spec).items() if e.get("fuse") == tag and n not in (new or (a, b))}
        if rest:
            others = ("This fuse also holds " + ", ".join(f"{n} (fill {float(e.get('fill', 0)) * 100:.1f} cm)" for n, e in rest.items())
                      + ": each mass keeps its own fill and sides, and the widest are worked together first.")
    compile_prims(spec)
    v = store.save(name, spec, note or (f"fuse {a} + {b}, fill {fill:.3f}" if fill else f"{a} and {b} parted"))
    after = reshape.waist(prims0, a, b, fill if fill else k0, how if fill else None)

    def cm(w):
        return (f"{w['width'] * 100:.1f} cm across (x) and {w['depth'] * 100:.1f} cm deep (y: {w['front'] * 100:.1f} to the "
                f"front, {w['back'] * 100:.1f} to the back of the middle) at z {w['z']:.3f}")
    lines = [f"{name} v{v}: " + (f"{a} and {b} worked into one mass, fill {fill * 100:.1f} cm"
                                 + (" (" + ", ".join(f"{k} {float(x):g} of it" for k, x in sides.items()) + ")" if sides else "")
                                 + "." if fill else f"{a} and {b} parted again.")]
    if after is not None:
        lines.append(f"Narrowest between them: {cm(after)}" + (f" (before: {cm(before)})." if before is not None else "."))
    elif before is not None:
        lines.append(f"Nothing narrows between them any more (before: {cm(before)}): they are one mass with no waist.")
    else:
        lines.append("They are not one above the other, so there is no waist to measure: judge the join in the look.")
    if said:
        lines.append(said)
    if others:
        lines.append(others)
    if fill and not sides:
        lines.append("The same fill all round: if one mass should stand over the other on one side (a chin over a chest) "
                     "while they run smooth on the others, give sides, e.g. sides={\"front\": 0.2}.")
    lines.append("The fuse is in the spec as \"fuse\", \"fill\" (and \"fill_sides\") on each mass: a put_model of a whole new spec drops it "
                 "unless those keys are carried over.")
    lines.append("next: look at this beside the reference from the front and the side. The waist's width is the one "
                 "number the reference's outline gives you there: fuse again with that width (or another fill) to "
                 "change it; fill=0 parts them. A mass whose own outline is off is a job for grab.")
    return _with_look(name, ["front", "side"], "\n".join(lines))


@mcp.tool(structured_output=False)
def grab(name: str, of: list[str], view: str, at: list[float], to: list[float], radius: float, label: str = "",
         remove: bool = False, note: str = ""):
    """Take hold of clay that is already there and move it, as a modeller's move brush does: in a flat view, the clay
    of the masses `of` at the point `at` goes to `to`, and the clay within `radius` of it follows, less the
    further out it is (a ball of clay round where you took hold, not the whole depth of the view), so the surface
    stays smooth and the form stays round. view "front" (points are [x, z]),
    "side" ([y, z]; the figure faces -y) or "top" ([x, y]), in metres, read off look's rulers. Use it wherever an
    outline is off against the reference: a round end pulled to a point, a cheek out, a face pushed flatter. A grab
    moves clay by at most half its radius. label names it: the same label replaces it, remove=True takes it off.
    Mirrored on a symmetric model. Details: guide(topic="grab")."""
    spec = store.load(name)
    grabs = dict(spec.get("grabs") or {})
    if remove:
        if label not in grabs:
            raise ValueError(f"no grab called {label!r}. This model's grabs: {', '.join(grabs) or 'none'}")
        del grabs[label]
        what = f"grab {label!r} taken off."
    else:
        of = [of] if isinstance(of, str) else list(of)
        _need(spec, of)
        if not label:
            i = 1
            while f"grab{i}" in grabs:
                i += 1
            label = f"grab{i}"
        g = reshape.check(label, {"of": of, "view": view, "at": at, "to": to, "radius": radius})
        grabs[label] = {k: g[k] for k in ("of", "view", "at", "to", "radius")}
        d = float(np.hypot(g["to"][0] - g["at"][0], g["to"][1] - g["at"][1]))
        ax = {"front": "x, z", "side": "y, z", "top": "x, y"}[view]
        what = (f"grab {label!r}: the clay of {', '.join(of)} at {g['at']} ({view} view: {ax}) moved {d * 100:.1f} cm to "
                f"{g['to']}, with the clay within {g['radius'] * 100:.1f} cm of it following.")
        names = list(_elements(spec))
        made = reshape.effective({label: grabs[label]}, bool(spec.get("symmetry", True)), names)
        if len(made) > 1:
            what += (" MADE ON BOTH SIDES: the model is symmetric, so the same grab is made mirrored on the other side. "
                     "Do not add one there yourself (it would pull that side twice).")
    if grabs:
        spec["grabs"] = grabs
    else:
        spec.pop("grabs", None)
    compile_prims(spec)
    v = store.save(name, spec, note or what)
    lines = [f"{name} v{v}: {what}",
             f"Grabs on this model: {', '.join(grabs) or 'none'}. They are in its spec under \"grabs\": a put_model of a "
             "whole new spec drops them unless it carries that key over (get_model shows it).",
             "next: look at the outline you moved beside the reference in the same view. Off by a little: the same "
             "label again with another `to` or radius. A different place: another grab. The whole mass in the wrong "
             "place or the wrong size: that is the mass's own joint or size, not a grab."]
    views = [view if view in ("front", "side", "top") else "front", "three_quarter"]
    return _with_look(name, views, "\n".join(lines))


def _nearest_joint(spec: dict, point) -> str:
    joints = spec.get("joints") or {}
    if not joints:
        raise ValueError("this model has no joints yet: a flap rides on one (give at, or put the skeleton in first)")
    return min(joints, key=lambda j: float(np.linalg.norm(np.array(joints[j]["pos"], float) - point)))


@mcp.tool(structured_output=False)
def flap(name: str, mass: str, root: list[float], over: list[float], tip: list[float], width: float,
         thickness: float | None = None, pointed: float = 0.6, cup: float = 0.0, at: str | None = None,
         blend: float | None = None, part: str | None = None, note: str = ""):
    """A flap of clay that grows out of the figure, arches over and hangs: a folded ear, a comb, a tongue, a tab, a
    leaf, as a modeller makes one: ONE leaf with thickness, rooted, bent over in a smooth arch (a blade is flat and
    can only lean). Three points say where it goes, [x, y, z] in metres read off look's rulers (x and z in the front
    view, y and z in the side view; the figure faces -y): root (the middle of where it grows out: put it a little
    INSIDE the mass it grows from), over (the top of its arch) and tip (where its tip ends: for an ear folded
    forward, in front of and below `over`). It bends about its own width: its broad face is square to the plane
    the three points make. width: across it at the root; thickness (default a fifth of the width);
    pointed 0..1 (0 a round leaf, 1 narrowing to a soft point); cup: metres its side edges curl toward the inside
    of the fold (an ear's hollow). mass: its name; one ending ".L" is made on the left (+x) and mirrored. The same
    name again replaces it: move ONE point to change where it hangs, how it arches or where it grows from.
    Returns the look and what was made. Details: guide(topic="flap")."""
    from .spec import SpecError, mirror_name, resolve_point
    spec = store.load(name)
    if mass.endswith(".R"):
        raise ValueError(f"name the left one ({mass[:-2]}.L, on +x): its right twin is made by mirroring")
    pts = []
    for label, v in (("root", root), ("over", over), ("tip", tip)):
        if not (isinstance(v, (list, tuple)) and len(v) == 3):
            raise ValueError(f"{label} is a point [x, y, z] in metres, read off look's rulers (x, z in the front view; "
                             "y, z in the side view)")
        pts.append(np.array(v, float))
    r, o, tp = pts
    l1, l2 = float(np.linalg.norm(o - r)), float(np.linalg.norm(tp - o))
    width = float(width)
    thick = float(thickness) if thickness is not None else max(width / 5.0, 0.008)
    if width <= 0 or thick <= 0 or thick >= 0.8 * width:
        raise ValueError(f"width is across the flap at its root and thickness through it, in metres, the thickness "
                         f"well under the width (got {width:g} and {thick:g})")
    if min(l1, l2) < thick:
        raise ValueError(f"root to over is {l1 * 100:.1f} cm and over to tip {l2 * 100:.1f} cm, and the flap is "
                         f"{thick * 100:.1f} cm thick: each stretch has to be longer than the flap is thick")
    axis = np.cross(o - r, tp - o)
    if np.linalg.norm(axis) < 0.05 * l1 * l2:
        raise ValueError("root, over and tip lie in one line: a flap arches over `over`. Move `over` off the line "
                         "between root and tip (for a straight flat leaf use a blade blob)")
    axis = axis / np.linalg.norm(axis)
    if not 0.0 <= float(pointed) <= 1.0:
        raise ValueError("pointed is 0 (a round leaf) to 1 (narrowing to a soft point)")
    blobs = spec.setdefault("blobs", {})
    old = blobs.get(mass) or {}
    if mass in (spec.get("bones") or {}):
        raise ValueError(f"{mass!r} is a bone of this model: give the flap another name")
    at = at or (old.get("at") if isinstance(old.get("at"), str) else None) or _nearest_joint(spec, r)
    base = resolve_point(spec, at)
    W, T = width / 2.0, thick / 2.0
    hw = [W, W * (1 - 0.45 * pointed), max(W * (1 - 0.85 * pointed), 1.4 * T)]
    new = {"shape": "sheet", "at": at, "spine": [[round(float(x), 4) for x in p - base] for p in pts], "curve": "spline",
           "width_axis": [round(float(x), 4) for x in axis], "fold": "crush", "root": round(1.5 * T, 4),
           "stations": [{"t": t_, "half_width": round(h, 4), "half_thickness": round(T, 4),
                         **({"cup": round(-float(cup) * c, 4)} if cup else {})}
                        for t_, h, c in zip((0.0, 0.5, 1.0), hw, (0.0, 1.0, 0.6))]}
    for k in ("part", "fuse", "fill", "fill_sides", "tags"):
        if k in old:
            new[k] = old[k]
    if part:
        new["part"] = part
    b = blend if blend is not None else old.get("blend")
    new["blend"] = float(b) if b is not None else min(float(spec.get("blend", 0.03)), 0.015)
    blobs[mass] = new
    try:
        compile_prims(spec)
    except SpecError as e:
        raise ValueError(f"{e}. The flap turns too sharply for how thick it is: move `over` further from the line "
                         "between root and tip, or make it thinner") from None
    bare = copy.deepcopy(spec)
    for n in (mass, mirror_name(mass)):
        bare["blobs"].pop(n, None)
    from .sdf import field_at
    rest = [p for p in compile_prims(bare) if p.op == "add"] if (bare.get("bones") or bare.get("blobs")) else []
    out = float(field_at(rest, r[None], clip=False)[0]) if rest else 1.0
    v = store.save(name, spec, note or f"flap {mass}: root {root}, over {over}, tip {tip}")
    turn = float(np.degrees(np.arccos(np.clip((o - r) @ (tp - o) / (l1 * l2), -1, 1))))
    twin = mirror_name(mass)
    lines = [f"{name} v{v}: {mass} is a flap about {(l1 + l2) * 100:.0f} cm long: it grows from {[round(float(x), 3) for x in r]}, "
             f"arches over {[round(float(x), 3) for x in o]} and its tip is at {[round(float(x), 3) for x in tp]} (it turns "
             f"{turn:.0f} degrees on the way); {width * 100:.1f} cm across at the root, {thick * 100:.1f} cm thick. It rides on "
             f"joint {at!r}" + (f" and is mirrored as {twin}." if twin and bool(spec.get("symmetry", True)) else ".")]
    k = int(np.argmax(np.abs(axis)))  # a flap is thin only when seen along its width
    runs, thin, broad = (("left to right (x)", "the side view", "the front and back views"),
                         ("front to back (y)", "the front and back views", "the side view"),
                         ("up and down (z)", "from above", "the front and side views"))[k]
    lines.append(f"A flap bends about its own width, and its width runs square to the plane the three points make: here "
                 f"mostly {runs} (width axis {[round(float(x), 2) for x in axis]}), so it shows broad in {broad} and thin, "
                 f"edge-on, in {thin}. For an ear that is broad from the front, keep root, over and tip at about the same "
                 "x (over above the root, tip in front of and below over); moving the tip or over sideways turns the face.")
    if out > 0.002:
        lines.append(f"ITS ROOT IS {out * 100:.1f} cm OUTSIDE the clay it should grow from: it floats. Move root that far "
                     "(and a little more) into the mass.")
    lines.append("It is a \"sheet\" blob in the spec (get_model shows it): a put_model of a whole new spec drops it unless "
                 "that blob is carried over.")
    lines.append("next: look at it beside the reference from the front, the side AND three-quarter (a flap that is right in "
                 "two flat views can still be wrong in the round). One point changes one thing: tip is where it hangs, "
                 "over is how high and which way it arches, root is where it grows from. Call flap again with the same "
                 "name and the one point moved. width, thickness, pointed and cup change the leaf itself.")
    return _with_look(name, ["front", "side", "three_quarter"], "\n".join(lines))


@mcp.tool(structured_output=False)
def trim(name: str, of: list[str] | str, view: str, a: list[float], b: list[float], off: str, soft: float = 0.004,
         label: str = "", remove: bool = False, note: str = ""):
    """Cut clay away along a straight line drawn in a flat view, as a modeller's trim (knife) does: the line runs
    through a and b, and the clay of the masses `of` on its `off` side is cut away all the way through the depth,
    leaving a flat face: the flat front of a snout, a flat sole under a hoof, a seat, a squared-off end. view
    "front" (points are [x, z]), "side" ([y, z]; the figure faces -y) or "top" ([x, y]), in metres read off look's
    rulers. off: the side that goes: up, down, left (+x), right, front (-y) or back. of: the masses cut, or "all".
    soft: how far the cut's edge is rounded, metres (0: knife sharp). label names it: the same label replaces it,
    remove=True takes it off. Mirrored on a symmetric model. To take a SHAPE out instead (a mouth, a socket), use
    carve. Details: guide(topic="trim")."""
    spec = store.load(name)
    trims = dict(spec.get("trims") or {})
    if remove:
        if label not in trims:
            raise ValueError(f"no trim called {label!r}. This model's trims: {', '.join(trims) or 'none'}")
        del trims[label]
        what = f"trim {label!r} taken off."
    else:
        if of != "all":
            of = [of] if isinstance(of, str) else list(of)
            _need(spec, of)
        if not label:
            i = 1
            while f"trim{i}" in trims:
                i += 1
            label = f"trim{i}"
        t = reshape.check_trim(label, {"of": of, "view": view, "a": a, "b": b, "off": off, "soft": soft})
        trims[label] = {k: t[k] for k in ("of", "view", "a", "b", "off", "soft")}
        ax = {"front": "x, z", "side": "y, z", "top": "x, y"}[view]
        what = (f"trim {label!r}: the clay of {'every mass' if of == 'all' else ', '.join(of)} on the {off} side of the line "
                f"through {t['a']} and {t['b']} ({view} view: {ax}) is cut away, flat.")
    if trims:
        spec["trims"] = trims
    else:
        spec.pop("trims", None)
    compile_prims(spec)
    v = store.save(name, spec, note or what)
    lines = [f"{name} v{v}: {what}",
             f"Trims on this model: {', '.join(trims) or 'none'}. They are in its spec under \"trims\": a put_model of a "
             "whole new spec drops them unless it carries that key over.",
             "next: look at the cut face from the view you drew it in and from three-quarter. In the wrong place: the "
             "same label again with the line moved. A mass blended wide with its neighbours fills a cut back in a "
             "little at the join: cut further, or lower that mass's blend."]
    views = [view if view in ("front", "side", "top") else "front", "three_quarter"]
    return _with_look(name, views, "\n".join(lines))


@mcp.tool(structured_output=False)
def carve(name: str, cutter: str, of: list[str], soft: float | None = None, back: bool = False, note: str = ""):
    """Take one mass OUT of others, as a modeller subtracts a shape (a boolean): the mass `cutter` stops being clay
    and becomes a hole of its own shape in the masses `of`, and only in them: a mouth cavity out of a head, an eye
    socket, a nostril, a notch, a slot. First make the cutter as an ordinary mass where the hollow should be (any
    shape, sticking out of the surface it opens through), then carve it. Moving or resizing the cutter afterwards
    moves the hollow. soft: how far the hollow's rim is rounded, metres. back=True makes the cutter clay again.
    To cut along a straight line instead, use trim. Details: guide(topic="carve")."""
    spec = store.load(name)
    of = [of] if isinstance(of, str) else list(of)
    els = _need(spec, [cutter] if back else [cutter, *of])
    el = els[cutter]
    if back:
        if el.get("op") != "subtract":
            raise ValueError(f"{cutter!r} is not a cutter: it is clay already")
        for k in ("op", "targets"):
            el.pop(k, None)
        what = f"{cutter} is clay again; nothing is carved by it."
    else:
        if cutter in of:
            raise ValueError("a mass can't be carved out of itself: of names the masses the cutter makes a hollow in")
        if not of:
            raise ValueError("of names the masses the cutter makes a hollow in")
        for k in ("fuse", "fill", "fill_sides"):
            if k in el:
                raise ValueError(f"{cutter!r} is fused into other masses: part it first (fuse with fill=0), then carve")
        el["op"], el["targets"] = "subtract", of
        if soft is not None:
            el["blend"] = float(soft)
        what = f"{cutter} is taken out of {', '.join(of)}: a hollow of its shape, and no longer clay itself."
    compile_prims(spec)
    v = store.save(name, spec, note or what)
    lines = [f"{name} v{v}: {what}",
             "In the spec the cutter carries \"op\": \"subtract\" and \"targets\": move, resize or reshape it like any mass "
             "and the hollow follows.",
             "next: look into the hollow from the side it opens to, close up (look with closeup or a three-quarter view). "
             "Too shallow or too small: make the cutter bigger or push it further in. Not open: the cutter has to stick "
             "out through the surface."]
    return _with_look(name, ["front", "three_quarter"], "\n".join(lines))
