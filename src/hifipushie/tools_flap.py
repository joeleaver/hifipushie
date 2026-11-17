"""The flap tool (a lump grown from the figure and bent over: an ear, a comb, a tongue, a tab; flap.py is the spec of
the shape) and the bend tool (any masses carried along a path; bend.py)."""
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


_VIEW_OF = ("the side", "the front", "above")


def _views_broad(F) -> str:
    a = np.abs(np.asarray(F, float))
    o = np.argsort(-a)
    if a[o[1]] > 0.6 * a[o[0]]:  # (e15: a 1-degree turn flipped "broad from the front" to "from the side")
        return f"broad from {_VIEW_OF[o[0]]} and {_VIEW_OF[o[1]]} alike: its face looks between them"
    return ("broad from the side (it is edge-on from the front)", "broad from the front and back (it is edge-on from "
            "the side)", "broad from above")[o[0]]


@mcp.tool(structured_output=False)
def flap(name: str, mass: str, base: list[float], length: float, width: float, rise: str | list = "up",
         face: str | list = "forward", fold: float = 0.0, fold_at: float = 0.5, round: float | None = None,  # noqa: A002
         thickness: float | None = None, pointed: float = 0.4, flare: float | None = None,
         blend: float | None = None, part: str | None = None, note: str = ""):
    """A flap of clay made as a modeller makes an ear: a thick lump standing on the figure, blocked straight, its
    top then BENT over. A folded ear, a comb, a tongue, a tab. base: [x, y, z], the middle of where it grows from,
    ON the surface of the mass it grows from (read off look's rulers; it is sunk in a little by itself). rise: the
    way it stands, words ("up", "up out", "up out back": out is away from the centre line) or [x, y, z]. face: the
    way its broad face looks ("forward", "forward out"); it is made square to rise; the fold bends toward it.
    length: base to tip laid straight, m; width: across its base; thickness: through its base (default 0.6 of the
    width: clay ears are thick lumps, not straps); pointed 0..1 (0 the same width to its end, 1 narrowing to a soft
    point). fold: degrees its top bends over toward its face (0 none; 90 the top sticks out forward; 150 to 180 it
    lies down along the standing part); fold_at: where along its length the bend starts; round: the bend's radius,
    m: how broad the rim over the top is (default 0.6 of the thickness: a soft rim; under half the thickness the
    inside of the fold creases). The
    bend keeps the clay's thickness and makes the cup inside the fold. flare: metres the root swells into the clay
    it grows from (default a quarter of the width; 0 none). A name ending ".L" is made on the left (+x) and
    mirrored. The same name again replaces it: change ONE thing at a time. It builds only where the part has been
    read first: study_part, then study_part with your reading.
    Then look_beside with focus=[mass]. The bend is the model's bend "flap:<mass>"; the bend tool bends any other
    mass the same way. Details: guide(topic="flap")."""
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
    from . import study
    if study.reading_near(name, b0) is None:  # (e15 to e19: the one modeller who read the part first read it right;
        # the ones who skipped it misread the ear the same way and turned it edge-on)
        raise ValueError(f"read the part before you build it: study_part(\"{name}\", what=\"the left ear\", at={[round_(float(c), 3) for c in b0]}) "
                         "shows it in every reference picture with the steps to read it in; write the steps out and pass "
                         "them back as study_part(..., reading=...). Then flap builds here.")
    try:
        R, F = _aim_vec(rise, "rise"), _aim_vec(face, "face")
    except SpecError as e:
        raise ValueError(str(e)) from None
    width, length = float(width), float(length)
    thick = float(thickness) if thickness is not None else 0.6 * width
    if not (0 < thick <= width) or length < 1.2 * thick:
        raise ValueError(f"width across the base, length base to tip and thickness through it, in metres: the thickness "
                         f"no more than the width and the length over 1.2 times the thickness (got {width:g}, {length:g}, {thick:g})")
    if not (0 <= float(pointed) <= 1 and 0.15 <= float(fold_at) <= 0.9 and 0 <= float(fold) <= 180):
        raise ValueError("pointed is 0..1, fold_at 0.15..0.9 (where along its length the bend starts), fold 0..180 degrees")
    if round is not None and not 0.002 <= float(round) <= length:
        raise ValueError("round is the bend's radius in metres (a few millimetres is a crease, about the thickness a soft rim)")
    # mass is the NEW flap's name: an existing mass that is no flap is refused, never replaced (e4 passed the head's
    # name for "the mass it grows from" and the head became an ear)
    stem, J, label = flapmod.parts(mass)
    bones0 = spec.get("bones") or {}
    mine = mass in bones0 and "flap" in bones0[mass]
    taken = [n for n in (mass,) if n in (spec.get("blobs") or {}) or (n in bones0 and not mine)]
    taken += [j for j in J.values() if j in (spec.get("joints") or {}) and not mine]
    if taken:
        raise ValueError(f"mass is the name of the NEW flap, and {taken[0]!r} is already part of this model: give the flap a "
                         "name of its own (e.g. \"ear.L\"); where it grows from is `base`")
    try:
        g = flapmod.lump(mass, b0, R, F, length, width, thick, float(fold_at), float(fold), float(pointed),
                         round_=round, flare=0.25 * width if flare is None else float(flare))
    except ValueError as e:
        raise ValueError(str(e)) from None
    bones, joints = spec.setdefault("bones", {}), spec.setdefault("joints", {})
    old = bones.get(mass) or {}
    side = mass[-2:] if mass.endswith((".L", ".R")) else ""
    for n in (f"{stem}_foot{side}",):
        bones.pop(n, None)
    for j in (f"{stem}_foot{side}", f"{stem}_collar{side}"):
        joints.pop(j, None)
    joints.update(g["joints"])
    for n, bdef in g["bones"].items():
        keep = {k: (bones.get(n) or {})[k] for k in ("part", "tags") if k in (bones.get(n) or {})}
        bones[n] = {**bdef, **keep}
    if part:
        for n in g["bones"]:
            bones[n]["part"] = part
    bl = blend if blend is not None else old.get("blend")
    bones[mass]["blend"] = float(bl) if bl is not None else min(float(spec.get("blend", 0.03)), 0.02)
    bones[mass]["flap"] = {"base": [float(x) for x in b0], "rise": rise, "face": face, "length": length,
                           "width": width, "thickness": thick, "fold": float(fold), "fold_at": float(fold_at),
                           "round": round, "pointed": float(pointed), "flare": flare}
    bends = spec.setdefault("bends", {})
    bends.pop(label, None)
    if g["bend"]:
        bends[label] = g["bend"]
    if not bends:
        spec.pop("bends", None)
    try:
        compile_prims(spec)
    except SpecError as e:
        raise ValueError(f"{e}") from None
    bare = copy.deepcopy(spec)
    bare.pop("strokes", None)  # (strokes laid on the flap can't be seated without it; they don't change its base)
    (bare.get("bends") or {}).pop(label, None)
    if not bare.get("bends"):
        bare.pop("bends", None)
    for n in (mass, mirror_name(mass), f"{stem}_foot{side}", mirror_name(f"{stem}_foot{side}") or ""):
        (bare.get("bones") or {}).pop(n, None)
    from .sdf import field_at
    rest = [p for p in compile_prims(bare) if p.op == "add"] if (bare.get("bones") or bare.get("blobs")) else []
    off = float(field_at(rest, b0[None], clip=False)[0]) if rest else 0.0
    v = store.save(name, spec, note or f"flap {mass}: length {length:g}, fold {fold:g} at {fold_at:g}")
    twin = mirror_name(mass)
    r3 = lambda p: [round_(float(x), 3) for x in p]  # noqa: E731
    lines = [f"{name} v{v}: {mass} is a lump {width * 100:.1f} cm across its base, {thick * 100:.1f} cm thick and "
             f"{length * 100:.0f} cm long, standing from {r3(b0)} toward {r3(g['rise'])}, its broad face toward "
             f"{r3(g['face'])}: {_views_broad(g['face'])}. "
             + (f"It stands {fold_at * length * 100:.1f} cm straight, then bends {fold:.0f} degrees round a rim "
                f"{g['round'] * 100:.1f} cm in radius; its end is at {r3(g['end'])}." if g["bend"] else "It is not folded.")
             + (f" Mirrored as {twin}." if twin and bool(spec.get("symmetry", True)) else "")]
    if g["bend"] and g["round"] < 0.5 * thick:
        lines.append(f"The bend's radius ({g['round'] * 100:.1f} cm) is under half the thickness: the inside of the fold is "
                     "squeezed into a crease. For a cup inside it, a round of at least half the thickness.")
    if g["bend"]:
        lines.append(f"Its bent-over part points {_words(g['toward'])} (it bends toward its face, so past 90 degrees it comes "
                     "back against the way it rises: a flap leaning out bends back in). For a top that hangs out as well "
                     "as forward, turn face out too (\"forward out\").")
    if off > 0.004:
        lines.append(f"ITS BASE IS {off * 100:.1f} cm OUTSIDE the clay it should grow from: it floats. Put base on that "
                     "mass's surface (read it off look_beside's or look's rulers).")
    elif off < -0.03:
        lines.append(f"Its base is {-off * 100:.1f} cm INSIDE the mass it grows from: part of the pad is buried. Put base on "
                     "that mass's surface.")
    lines.append(f"In the spec it is the bone {mass} (with the tool's numbers under \"flap\") on joints "
                 f"{', '.join(J.values())}, and the bend {label!r} under \"bends\": a put_model of a whole new spec drops "
                 "them unless carried over.")
    lines.append(f"next: look_beside(\"{name}\", focus=[\"{mass}\"]): the flap close up beside each reference view and the "
                 f"painting; once it looks right to you, review_part(\"{name}\", [\"{mass}\"], \"the ear\") for a fresh "
                 "reviewer's eyes on it. Then change ONE thing: where it stands (base), which way it rises or looks (rise, "
                 "face), its size (length, width, thickness, pointed), or the bend (fold, fold_at, round).")
    return tools_reshape._with_look(name, ["front", "side", "three_quarter"], "\n".join(lines))


round_ = round  # (the flap tool's own parameter is called round)


def _lead_in(spec: dict, masses: list[str], path: list) -> list | None:
    """A point before the path's start along the first bent bone's own line, when the path's first step leaves that
    line: the path's first direction is the line the clay is carried from, and a path that set off across the bone
    sheared it (a tail bent from its side)."""
    from .spec import resolve_point
    bones = spec.get("bones") or {}
    b = next((bones[m] for m in masses if m in bones), None)
    if b is None:
        return None
    try:
        a, c = np.asarray(resolve_point(spec, b["a"]), float), np.asarray(resolve_point(spec, b["b"]), float)
    except Exception:  # noqa: BLE001  (a bone the spec can't place: leave the path as given)
        return None
    ax = (c - a) / max(np.linalg.norm(c - a), 1e-9)
    p0, p1 = np.asarray(path[0], float), np.asarray(path[1], float)
    d = (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-9)
    if d @ ax < 0:
        ax = -ax
    if d @ ax > 0.999:
        return None
    return [round_(float(v), 4) for v in p0 - 0.3 * np.linalg.norm(p1 - p0) * ax]


@mcp.tool(structured_output=False)
def bend(name: str, masses: list[str], path: list[list[float]], label: str | None = None, remove: bool = False,
         note: str = ""):
    """Bend masses along a path, as a modeller bends clay: a tail curled, a horn swept back, a trunk, a finger, a
    drooping brim, an ear's top laid over. Block the mass STRAIGHT first (put_model / edit_model), then bend it.
    path: two or more points [[x, y, z], ...] in metres: the first is where the bending starts, ON the mass's own
    line (for a bone, a short first step along its own line is added for you); the clay past the start
    is carried along the path keeping its length and thickness, and past the path's end it goes on straight. A
    gentle curve gives a round rim, a tight one squeezes the inside into a crease. Clay before the start stays put.
    masses: the masses to bend (".L" ones bend mirrored on the right too). label: the bend's name (default
    "bend1", ...); the same label again replaces it; remove=True takes it off. Details: guide(topic="bend")."""
    from . import bend as bendmod
    from .spec import SpecError
    spec = store.load(name)
    bends = dict(spec.get("bends") or {})
    if remove:
        if label not in bends:
            raise ValueError(f"no bend called {label!r}. This model's bends: {', '.join(bends) or 'none'}")
        del bends[label]
    else:
        known = set(spec.get("bones") or {}) | set(spec.get("blobs") or {})
        gone = [m for m in masses if m not in known]
        if gone or not masses:
            raise ValueError(f"masses: no mass called {gone} (this model's: {sorted(known)[:40]})")
        path = [[float(c) for c in q] for q in path]
        if len(path) < 2:
            raise ValueError("a bend's path is two or more points [[x, y, z], ...]")
        led = _lead_in(spec, masses, path)
        if led is not None:
            path = [led] + path
        try:
            g = bendmod.geometry(path)
        except ValueError as e:
            raise ValueError(str(e)) from None
        if label is None:
            i = 1
            while f"bend{i}" in bends:
                i += 1
            label = f"bend{i}"
        bends[label] = {"of": list(masses), "path": path}
    trial = dict(spec)
    if bends:
        trial["bends"] = bends
    else:
        trial.pop("bends", None)
    try:
        compile_prims(trial)
    except SpecError as e:
        raise ValueError(str(e)) from None
    v = store.save(name, trial, note or (f"bend {label} removed" if remove else f"bend {label}: {', '.join(masses)}"))
    if remove:
        text = f"{name} v{v}: bend {label!r} taken off."
    else:
        text = (f"{name} v{v}: bend {label!r} carries {', '.join(masses)} along a path {g['L'] * 100:.1f} cm long, starting at "
                f"{[round_(c, 3) for c in path[0]]} and heading {_words(g['T'][0])} there, ending heading "
                f"{_words(g['T'][-1])}; its tightest curve has a radius of {100 / max(g['kmax'], 1e-6):.1f} cm (clay "
                "thicker than that squeezes into a crease on the inside). In the spec under \"bends\".")
    return tools_reshape._with_look(name, ["front", "side", "three_quarter"],
                                    text + "\nnext: look at it beside the reference (look_beside); change the path, ONE point at a time.")
