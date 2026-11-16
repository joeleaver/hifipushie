"""The flap tool: an ear, a tab, a fin, as a modeller makes one: a flat outline of clay, thick, with a rounded rim,
standing on the figure, its top folded over. slab.py is the spec of the shape."""
from __future__ import annotations

import copy

import numpy as np

from . import store, tools_reshape
from .mcp_app import mcp
from .spec import compile_prims


def _words(v) -> str:
    v = np.asarray(v, float)
    out = []
    for i, (pos, neg) in ((2, ("up", "down")), (1, ("back", "forward")), (0, ("out", "in"))):
        if abs(v[i]) > 0.3:
            out.append(pos if v[i] > 0 else neg)
    return " and ".join(out) or "sideways"


def _views_broad(F) -> str:
    k = int(np.argmax(np.abs(F)))
    return ("from the side (it is edge-on from the front)", "from the front and back (it is edge-on from the side)",
            "from above")[k]


@mcp.tool(structured_output=False)
def flap(name: str, mass: str, base: list[float], length: float, width: float, rise: str | list = "up",
         face: str | list = "forward", tip_width: float = 0.0, thickness: float | None = None,
         tip_thickness: float | None = None, fold: float = 0.0, fold_at: float = 0.6, blend: float | None = None,
         part: str | None = None, note: str = ""):
    """An ear, a tab, a fin, made as a modeller makes one: its outline drawn flat (a triangle or a tapering tab with
    rounded corners), given a thickness with a rounded rim, stood on the figure, and its top folded over. base:
    [x, y, z], the middle of its base, ON the surface of the mass it grows from (read off look's rulers). rise: the
    way it stands ("up", "up out"; out is away from the centre line) or [x, y, z]. face: the way its broad face looks
    ("forward", "forward out"), made square to rise. length: base to tip laid flat; width: across the base;
    tip_width: across the tip (0: a point, a triangle; = width: a strip). thickness: through the base (default 0.35
    of the width), tip_thickness (default half that). fold: degrees its top folds over toward its face (0 upright,
    90 the top sticks out forward, 180 it lies flat against the standing part); fold_at: where along its length the
    fold line is (0.6: the top 40 % folds). A name ending ".L" is made on the left (+x) and mirrored. The same name
    again replaces it: change ONE thing at a time, then look_beside with focus=[mass] to see it close up beside the
    reference. Details: guide(topic="flap")."""
    from .spec import SpecError, mirror_name
    from .spec_hands import _aim_vec
    spec = store.load(name)
    if mass.endswith(".R"):
        raise ValueError(f"name the left one ({mass[:-2]}.L, on +x): its right twin is made by mirroring")
    if not (isinstance(base, (list, tuple)) and len(base) == 3):
        raise ValueError("base is a point [x, y, z] in metres on the surface it grows from (x, z in the front view; y, z "
                         "in the side view)")
    b0 = np.array(base, float)
    try:
        R, F = _aim_vec(rise, "rise"), _aim_vec(face, "face")
    except SpecError as e:
        raise ValueError(str(e)) from None
    F = F - (F @ R) * R
    if np.linalg.norm(F) < 0.2:
        raise ValueError("face is where the flap's broad face looks: it has to be away from the way it rises (an ear "
                         "rising up looks forward, not up)")
    F = F / np.linalg.norm(F)
    width, length = float(width), float(length)
    thick = float(thickness) if thickness is not None else 0.35 * width
    tthick = float(tip_thickness) if tip_thickness is not None else 0.5 * thick
    if not (0 < thick < width and 0 < tthick <= thick) or length < 1.5 * thick or not 0 <= float(tip_width) <= width:
        raise ValueError(f"in metres: thickness under the width, tip_thickness up to the thickness, tip_width up to the "
                         f"width, length over 1.5 times the thickness (got width {width:g}, length {length:g}, thickness "
                         f"{thick:g}, tip_thickness {tthick:g}, tip_width {tip_width:g})")
    if not (0.15 <= float(fold_at) <= 0.95 and 0 <= float(fold) <= 180):
        raise ValueError("fold_at is 0.15..0.95 (where along its length it folds), fold 0..180 degrees")
    blobs = spec.setdefault("blobs", {})
    old = blobs.get(mass) or {}
    if mass in (spec.get("bones") or {}):
        raise ValueError(f"{mass!r} is a bone of this model: give the flap another name")
    joints = spec.get("joints") or {}
    if not joints:
        raise ValueError("this model has no joints yet: a flap rides on one (put the skeleton in first)")
    at = old.get("at") if isinstance(old.get("at"), str) and old.get("at") in joints else \
        min(joints, key=lambda j: float(np.linalg.norm(np.array(joints[j]["pos"], float) - b0)))
    from .spec import resolve_point
    j = resolve_point(spec, at)
    r4 = lambda p: [round(float(x), 4) for x in p]  # noqa: E731
    new = {"shape": "slab", "at": at, "offset": r4(b0 - j), "rise": r4(R), "face": r4(F), "length": length,
           "width": width, "tip_width": float(tip_width), "thickness": thick, "tip_thickness": tthick,
           "fold": float(fold), "fold_at": float(fold_at)}
    for k in ("part", "fuse", "fill", "fill_sides", "tags"):
        if k in old:
            new[k] = old[k]
    if part:
        new["part"] = part
    bl = blend if blend is not None else old.get("blend")
    new["blend"] = float(bl) if bl is not None else min(float(spec.get("blend", 0.03)), 0.02)
    blobs[mass] = new
    try:
        compile_prims(spec)
    except SpecError as e:
        raise ValueError(str(e)) from None
    bare = copy.deepcopy(spec)
    for n in (mass, mirror_name(mass)):
        bare["blobs"].pop(n, None)
    from .sdf import field_at
    rest = [p for p in compile_prims(bare) if p.op == "add"] if (bare.get("bones") or bare.get("blobs")) else []
    off = float(field_at(rest, b0[None], clip=False)[0]) if rest else 0.0
    v = store.save(name, spec, note or f"flap {mass}: length {length:g}, fold {fold:g} at {fold_at:g}")
    th = np.radians(float(fold))
    toward = np.cos(th) * R + np.sin(th) * F
    hinge = b0 + float(fold_at) * length * R
    tip = hinge + (1 - float(fold_at)) * length * toward + (thick if fold else 0) * np.sin(th / 2) * F
    twin = mirror_name(mass)
    r3 = lambda p: [round(float(x), 3) for x in p]  # noqa: E731
    lines = [f"{name} v{v}: {mass} is a slab of clay {width * 100:.1f} cm across its base narrowing to {tip_width * 100:.1f} at "
             f"its tip, {length * 100:.0f} cm long, {thick * 100:.1f} cm thick at the base, standing from {r3(b0)} "
             f"{_words(R)}, its broad face {_words(F)}: broad {_views_broad(F)}. "
             + (f"Its top folds {fold:.0f} degrees toward its face along a line at {r3(hinge)}, so the folded part points "
                f"{_words(toward)} and its tip is near {r3(tip)}." if fold else "It is not folded.")
             + (f" Mirrored as {twin}." if twin and bool(spec.get("symmetry", True)) else "")]
    if off > 0.004:
        lines.append(f"ITS BASE IS {off * 100:.1f} cm OUTSIDE the clay it should grow from: it floats. Put base on that "
                     "mass's surface (read it off look_beside's or look's rulers).")
    elif off < -0.03:
        lines.append(f"Its base is {-off * 100:.1f} cm INSIDE the mass it grows from: part of it is buried. Put base on "
                     "that mass's surface.")
    if fold > 90:
        lines.append("Past 90 degrees the folded part comes back against the way the flap rises (a flap leaning out "
                     "folds back in): for a top that hangs out as well as forward, give face the outward part and rise "
                     "less of it.")
    lines.append("In the spec it is a \"slab\" blob: a put_model of a whole new spec drops it unless that blob is carried over.")
    lines.append(f"next: look_beside(\"{name}\", focus=[\"{mass}\"]): the flap close up beside each reference view and the "
                 "painting. Then change ONE thing: where it stands (base), which way it rises or looks (rise, face), its "
                 "outline (length, width, tip_width), its thickness, or the fold (fold, fold_at).")
    return tools_reshape._with_look(name, ["front", "side", "three_quarter"], "\n".join(lines))
