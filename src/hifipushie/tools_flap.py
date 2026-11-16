"""The flap tool: a pad of clay that grows from the figure and folds over (an ear, a comb, a tongue, a tab).
flap.py is the spec of the shape."""
from __future__ import annotations

import copy

import numpy as np

from . import store, tools_reshape
from .mcp_app import mcp
from .spec import compile_prims


def _views_broad(F) -> str:
    k = int(np.argmax(np.abs(F)))
    return ("from the side (it is edge-on from the front)", "from the front and back (it is edge-on from the side)",
            "from above")[k]


@mcp.tool(structured_output=False)
def flap(name: str, mass: str, base: list[float], length: float, width: float, rise: str | list = "up",
         face: str | list = "forward", fold: float = 0.0, fold_at: float = 0.6, thickness: float | None = None,
         pointed: float = 0.6, blend: float | None = None, part: str | None = None, note: str = ""):
    """A flap of clay made as a modeller makes an ear: a thick lump standing on the figure, its top folded over. A
    folded ear, a comb, a tongue, a tab. base: [x, y, z], the middle of where it grows from, ON the surface of the
    mass it grows from (read off look's rulers; it is sunk in a little by itself). rise: the way it stands, words
    ("up", "up out", "up out back": out is away from the centre line) or [x, y, z]. face: the way its broad face
    looks ("forward", "forward out"); it is made square to rise. length: base to tip laid flat, m; width: across its
    base, m; thickness: through its base (default 0.6 of the width: clay ears are thick lumps, not straps); pointed
    0..1 (0 round, 1 narrowing to a soft point). fold: degrees its top folds over toward its face (0 none; 90 the top sticks out
    forward; 150 to 180 it lies down along the standing part); fold_at: where along its length the fold is (0.6:
    the top 40 % folds over, round a knuckle). A name ending ".L" is made on
    the left (+x) and mirrored. The same name again replaces it: change ONE thing at a time. Then look_beside with
    focus=[mass] to see it close up beside the reference. Details: guide(topic="flap")."""
    from . import flap as flapmod
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
    width, length = float(width), float(length)
    thick = float(thickness) if thickness is not None else 0.6 * width
    if not (0 < thick <= width) or length < 1.2 * thick:
        raise ValueError(f"width across the base, length base to tip and thickness through it, in metres: the thickness "
                         f"no more than the width and the length over 1.2 times the thickness (got {width:g}, {length:g}, {thick:g})")
    if not (0 <= float(pointed) <= 1 and 0.15 <= float(fold_at) <= 0.95 and 0 <= float(fold) <= 180):
        raise ValueError("pointed is 0..1, fold_at 0.15..0.95 (where along its length it folds), fold 0..180 degrees")
    if mass in (spec.get("blobs") or {}) and (spec["blobs"][mass].get("shape") != "sheet"):
        raise ValueError(f"{mass!r} is a blob of this model: give the flap another name")
    try:
        g = flapmod.lump(mass, b0, R, F, length, width, thick, float(fold_at), float(fold), float(pointed))
    except ValueError as e:
        raise ValueError(str(e)) from None
    bones, joints = spec.setdefault("bones", {}), spec.setdefault("joints", {})
    old = bones.get(mass) or {}
    stem, J, top = flapmod.parts(mass)
    for n in (mass, mirror_name(mass)):  # an older flap made as a sheet blob goes
        (spec.get("blobs") or {}).pop(n, None)
    joints.update(g["joints"])
    for n, bdef in g["bones"].items():
        keep = {k: (bones.get(n) or {})[k] for k in ("part", "tags") if k in (bones.get(n) or {})}
        bones[n] = {**bdef, **keep}
    if part:
        for n in g["bones"]:
            bones[n]["part"] = part
    bl = blend if blend is not None else old.get("blend")
    bones[mass]["blend"] = float(bl) if bl is not None else min(float(spec.get("blend", 0.03)), 0.02)
    bones[top]["blend"] = bones[mass]["blend"]
    bones[mass]["flap"] = {"base": [float(x) for x in b0], "rise": rise, "face": face, "length": length,
                           "width": width, "thickness": thick, "fold": float(fold), "fold_at": float(fold_at),
                           "pointed": float(pointed)}
    try:
        compile_prims(spec)
    except SpecError as e:
        raise ValueError(f"{e}") from None
    bare = copy.deepcopy(spec)
    for n in (mass, mirror_name(mass), top, mirror_name(top)):
        (bare.get("bones") or {}).pop(n, None)
    from .sdf import field_at
    rest = [p for p in compile_prims(bare) if p.op == "add"] if (bare.get("bones") or bare.get("blobs")) else []
    off = float(field_at(rest, b0[None], clip=False)[0]) if rest else 0.0
    v = store.save(name, spec, note or f"flap {mass}: length {length:g}, fold {fold:g} at {fold_at:g}")
    twin = mirror_name(mass)
    r3 = lambda p: [round(float(x), 3) for x in p]  # noqa: E731
    lines = [f"{name} v{v}: {mass} is a lump {width * 100:.1f} cm across its base, {thick * 100:.1f} cm thick and {length * 100:.0f} "
             f"cm long, standing from {r3(b0)} toward {r3(g['rise'])}, its broad face toward {r3(g['face'])}: broad "
             f"{_views_broad(g['face'])}. " + (f"It folds {fold:.0f} degrees toward its face at {r3(g['hinge'])}; its tip is "
                                              f"at {r3(g['tip'])}." if fold else "It is not folded.")
             + (f" Mirrored as {twin}." if twin and bool(spec.get("symmetry", True)) else "")]
    if off > 0.004:
        lines.append(f"ITS BASE IS {off * 100:.1f} cm OUTSIDE the clay it should grow from: it floats. Put base on that "
                     "mass's surface (read it off look_beside's or look's rulers).")
    elif off < -0.03:
        lines.append(f"Its base is {-off * 100:.1f} cm INSIDE the mass it grows from: part of the pad is buried. Put base on "
                     "that mass's surface.")
    lines.append(f"In the spec it is two bones, {mass} (base to fold, with the tool's numbers under \"flap\") and {top} (the "
                 f"folded part), on joints {', '.join(J.values())}: a put_model of a whole new spec drops them unless carried over.")
    lines.append(f"next: look_beside(\"{name}\", focus=[\"{mass}\"]): the flap close up beside each reference view and the "
                 "painting. Then change ONE thing: where it stands (base), which way it rises or looks (rise, face), its "
                 "size (length, width, thickness, pointed), or the fold (fold, fold_at).")
    return tools_reshape._with_look(name, ["front", "side", "three_quarter"], "\n".join(lines))
