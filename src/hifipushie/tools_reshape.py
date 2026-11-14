"""Reshaping tools: the two things a modeller's hands do to a blockout that typing a shape's numbers can't.
`fuse` works two masses into one flowing mass; `grab` takes hold of clay that is already there and moves it
(reshape.py is the spec)."""
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
def fuse(name: str, a: str, b: str, fill: float | None = None, width: float | None = None, note: str = ""):
    """Work two masses into ONE flowing mass, as a modeller smooths two lumps of clay together: the hollow between `a`
    and `b` fills and the line between them goes (a head and body that should read as one pear, not two balls with
    a neck crease). Give fill (how far the two are worked into each other, in metres: 0.05 leaves a soft crease,
    0.15 a clear waist, 0.25 one mass with a slight pinch) OR width (how wide the figure is at its narrowest between the two, in metres, read off the
    reference: the fill is found for you). fill=0 parts them again. Returns the look and the waist as measured.
    Details: guide(topic="fuse")."""
    spec = store.load(name)
    els = _need(spec, (a, b))
    if a == b:
        raise ValueError("a and b are two different masses")
    if (fill is None) == (width is None):
        raise ValueError("give fill (how far the two are worked into each other, in metres) or width (metres across at the narrowest "
                         "place between them, read off the reference): one of the two")
    bare = copy.deepcopy(spec)
    for n in (a, b):
        for k in ("fuse", "fill"):
            _elements(bare)[n].pop(k, None)
    prims0 = compile_prims(bare)
    k0 = max(float(els[n].get("blend", spec.get("blend", 0.03)) or 0.0) for n in (a, b))
    before = reshape.waist(prims0, a, b, k0)
    said = ""
    if width is not None:
        fill, said = reshape.solve_fill(prims0, a, b, float(width))
    fill = float(fill)
    if fill < 0:
        raise ValueError("fill is how far the two are worked into each other, in metres: 0 (parted) or more")
    old = [els[n].get("fuse") for n in (a, b) if els[n].get("fuse")]
    if fill == 0:
        for n in (a, b):
            els[n].pop("fuse", None)
            els[n].pop("fill", None)
        for t in old:  # a tag left on one mass alone means nothing
            left = [e for e in _elements(spec).values() if e.get("fuse") == t]
            if len(left) == 1:
                left[0].pop("fuse", None)
                left[0].pop("fill", None)
    else:
        tag = old[0] if old else f"{a}+{b}"
        for e in _elements(spec).values():
            if e.get("fuse") in old:
                e["fuse"], e["fill"] = tag, round(fill, 4)
        for n in (a, b):
            els[n]["fuse"], els[n]["fill"] = tag, round(fill, 4)
    compile_prims(spec)
    v = store.save(name, spec, note or (f"fuse {a} + {b}, fill {fill:.3f}" if fill else f"{a} and {b} parted"))
    after = reshape.waist(prims0, a, b, fill if fill else k0)

    def cm(w):
        return f"{w['width'] * 100:.1f} cm across (x) and {w['depth'] * 100:.1f} cm deep (y) at z {w['z']:.3f}"
    lines = [f"{name} v{v}: " + (f"{a} and {b} worked into one mass, fill {fill * 100:.1f} cm." if fill
                                 else f"{a} and {b} parted again.")]
    if after is not None:
        lines.append(f"Narrowest between them: {cm(after)}" + (f" (before: {cm(before)})." if before is not None else "."))
    elif before is not None:
        lines.append(f"Nothing narrows between them any more (before: {cm(before)}): they are one mass with no waist.")
    else:
        lines.append("They are not one above the other, so there is no waist to measure: judge the join in the look.")
    if said:
        lines.append(said)
    lines.append("The fuse is in the spec as \"fuse\" and \"fill\" on both masses: a put_model of a whole new spec drops it "
                 "unless those keys are carried over.")
    lines.append("next: look at this beside the reference from the front and the side. The waist's width is the one "
                 "number the reference's outline gives you there: fuse again with that width (or another fill) to "
                 "change it; fill=0 parts them. A mass whose own outline is off is a job for grab.")
    return _with_look(name, ["front", "side"], "\n".join(lines))


@mcp.tool(structured_output=False)
def grab(name: str, of: list[str], view: str, at: list[float], to: list[float], radius: float, label: str = "",
         remove: bool = False, note: str = ""):
    """Take hold of clay that is already there and move it, as a modeller's move brush does: in a flat view, the clay
    of the masses `of` at the point `at` goes to `to`, and the clay within `radius` of `at` follows, less the
    further out it is, so the surface stays smooth and the outline moves whole. view "front" (points are [x, z]),
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
                f"{g['to']}, with everything within {g['radius'] * 100:.1f} cm following.")
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
