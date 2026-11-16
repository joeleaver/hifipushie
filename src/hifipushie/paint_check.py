"""Checks on a paint spec: validate, side warnings, references, stacks and generators. Part of paint (paint.py has the spec)."""
from __future__ import annotations

import re

import numpy as np

from . import paint
from .spec import SpecError
from .paint import colour, layers, painted_path

def validate(spec: dict) -> None:
    st = spec.get("style") or {}
    bad = set(st) - {"name", "shape", "paint", "look", "sheet"}
    if bad:
        raise SpecError(f"style: unknown keys {sorted(bad)} (have name, shape, paint, look, sheet)")
    lk = st.get("look") or {}
    bad = set(lk) - {"lights", "world", "look", "exposure", "view"}
    if bad:
        raise SpecError(f"style.look: unknown keys {sorted(bad)} (have lights, world, look, exposure, view)")
    for i, L in enumerate(lk.get("lights") or []):
        if "dir" not in L or set(L) - {"dir", "energy", "color", "angle", "shadow"}:
            raise SpecError(f"style.look.lights[{i}]: needs dir; takes dir, energy, color, angle, shadow")
    bad = set(st.get("paint") or {}) - set(paint.STYLE_PAINT)
    if bad:
        raise SpecError(f"style.paint: unknown keys {sorted(bad)} (have {', '.join(paint.STYLE_PAINT)})")
    for name, ly in layers(spec).items():
        if not any(c in ly for c in (*paint.CHANNELS, "height")):
            raise SpecError(f"paint {name!r}: needs at least one of {', '.join(paint.CHANNELS)}, height")
        if "height" in ly and not isinstance(ly["height"], (int, float)):
            raise SpecError(f"paint {name!r}: height is a number (m, + out of the surface, times the mask)")
        if ly.get("color") == "image":
            if not isinstance(ly.get("image"), dict):
                raise SpecError(f"paint {name!r}: \"color\": \"image\" takes the colours of the layer's own "
                                f"\"image\" key (a flat key on the layer, not in its mask stack)")
        elif "color" in ly:
            colour(ly["color"], f"paint {name!r}")
        for c in ("roughness", "metallic", "specular"):
            if c in ly and not 0 <= float(ly[c]) <= 1:
                raise SpecError(f"paint {name!r}: {c} is 0..1")
        flat = {g: ly[g] for g in paint.GENERATORS if g in ly and g != "mask"}
        unknown = set(ly) - {*paint.CHANNELS, "height", "opacity", "part", "mask", "mix", "_of", "_pre", "_detail", "_blink", *paint.GENERATORS, *(k for v in paint.PARAMS.values() for k in v)}
        if ly.get("mix", "mix") not in paint.MIXES:
            raise SpecError(f"paint {name!r}: mix is one of {', '.join(paint.MIXES)}")
        if unknown:
            raise SpecError(f"paint {name!r}: unknown keys {sorted(unknown)}")
        for g in flat:
            _check_generator(name, g, ly)
        if "mask" in ly:
            _check_stack(name, ly["mask"])


def _nears(ly: dict):
    """Every "near" a layer (or a mask stack entry) names, nested stacks included."""
    if "near" in ly:
        yield ly["near"]
    for e in ly.get("mask") or []:
        if isinstance(e, dict):
            yield from _nears(e)


def _gens(ly: dict, key: str):
    """Every value of generator `key` a layer (or a mask stack entry) gives, nested stacks included."""
    if key in ly:
        yield ly[key]
    for e in ly.get("mask") or []:
        if isinstance(e, dict):
            yield from _gens(e, key)


def side_warnings(spec: dict) -> list[str]:
    """Centre-named layers that point only at one side's elements: a ".L" name on the elements doesn't make the
    layer mirror (only the layer's own name does), so these paint one side. Returned for the edit summary."""
    out = []
    for name, ly in (spec.get("paint") or {}).items():
        if not isinstance(ly, dict) or name.endswith((".L", ".R")):
            continue
        names = []
        for near in _nears(ly):
            names += [near] if isinstance(near, str) else [n for n in near if isinstance(n, str)]
        for path in _gens(ly, "path"):
            for pt in path if isinstance(path, list) else []:
                if isinstance(pt, dict):
                    names += [pt[k] for k in ("bone", "at", "on") if isinstance(pt.get(k), str)]
                    if isinstance(pt.get("at"), dict) and isinstance(pt["at"].get("bone"), str):
                        names.append(pt["at"]["bone"])
        for side, other in ((".L", ".R"), (".R", ".L")):
            if names and all(n.endswith(side) for n in names):
                what = "near/path" if any(True for _ in _gens(ly, "path")) else "near"
                out.append(f"paint {name!r}: {what} names only {'left' if side == '.L' else 'right'}-side elements "
                           f"({', '.join(sorted(set(names)))}), so it paints one side; name the layer "
                           f"'{name}.L' to paint both sides, or add the '{other}' names for one-sided paint")
    return out


def check_refs(spec: dict, prims: list) -> None:
    """Names paint points at must exist: each "near" resolves to primitives, each "part" is a part of the model,
    each axis bone is a bone.
    Checked when the spec is saved, not minutes into a sync or export."""
    from .paintnodes import resolve_near
    from .spec import expand_mirror
    by_name = {p.name: p for p in prims}
    expanded = None
    parts = {p.part for p in prims} | set(spec.get("parts") or {}) | {"body"}
    els = {**(spec.get("bones") or {}), **(spec.get("blobs") or {})}
    for name, ly in layers(spec).items():
        lp = ly.get("part", "body")
        for pn in ([lp] if isinstance(lp, str) else lp):
            if pn != "*" and pn not in parts:
                raise SpecError(f"paint {name!r}: no part {pn!r} (parts: {', '.join(sorted(parts))})")
        for near in _nears(ly):
            if expanded is None:
                expanded = expand_mirror(spec)
            got, missing = resolve_near(spec, near, by_name, expanded)
            from . import sdf_shapes
            # (a lid fold, lidfold.py, is a modifier but has a line to be near: its crease, lidfold.line_distance)
            shapeless = [g for g in got if (by_name[g].kind not in sdf_shapes.SDF and by_name[g].kind != "fold")
                         or by_name[g].kind == "shell"]
            if shapeless:
                raise SpecError(f"paint {name!r}: near {shapeless} reshape the surface (strokes) and have no surface "
                                f"of their own to be near: name the element under them, or paint a path along the "
                                f"stroke's path instead")
            asked = [near] if isinstance(near, str) else list(near)
            empty = [a for a in asked if a not in by_name and not any(g == a or g.startswith((a + "/", a + "#"))
                                                                        for g in got)] if not got else missing
            bad = sorted(set(missing) | set(empty))
            if not bad:
                continue
            why = []
            for b in bad:
                el = els.get(b)
                if el is not None and el.get("op") in ("subtract", "intersect") and el.get("targets"):
                    why.append(f"{b!r} is a cut, folded into its targets {el['targets']}: it has no surface of "
                               f"its own to be near; name what it cuts, or elements beside the cut")
            raise SpecError(f"paint {name!r}: near names nothing for {bad}" + (": " + "; ".join(why) if why else
                            " (element, tag, instance, array or kit names)"))
        for img in _gens(ly, "image"):  # a decal must resolve and land on the layer's own parts
            from . import images_frame, images_project
            if expanded is None:
                expanded = expand_mirror(spec)
            if not isinstance(img, dict):
                continue
            fr = images_frame.frame(spec, img, expanded, what=f"paint {name!r} image", parts=lp)
            on = [p for p in prims if p.op == "add" and (lp == "*" or p.part in ([lp] if isinstance(lp, str) else lp))]
            on = [p for p in prims if p.part in {q.part for q in on}]  # with their cuts
            if fr["wrap"] != "uv" and images_project.coverage(fr, on) == 0:
                raise SpecError(f"paint {name!r}: image at {img.get('at', img.get('axis'))!r} hits nothing on part(s) "
                                f"{lp!r} within its depth {fr['depth']:.3f} m of the decal's {fr['wrap']} surface (centre {np.round(fr['c'], 3).tolist()}, "
                                f"dir {np.round(fr['dir'], 2).tolist()}): check at/dir, or raise depth")
        for ax in _gens(ly, "axis"):
            if isinstance(ax, dict) and "bone" in ax:
                if expanded is None:
                    expanded = expand_mirror(spec)
                if ax["bone"] not in expanded["bones"]:
                    raise SpecError(f"paint {name!r}: axis bone {ax['bone']!r} doesn't exist (removed or renamed?)")


def _check_stack(name: str, stack) -> None:
    if not isinstance(stack, list):
        raise SpecError(f"paint {name!r}: mask is a list of entries, e.g. [{{\"ao\": [0.9, 0.5]}}, "
                        f"{{\"noise\": {{}}, \"blend\": \"multiply\"}}]")
    for i, e in enumerate(stack):
        where = f"paint {name!r} mask[{i}]"
        if not isinstance(e, dict):
            raise SpecError(f"{where}: an entry is an object")
        gens = [g for g in paint.GENERATORS if g in e]
        if len(gens) > 1:
            raise SpecError(f"{where}: one generator per entry, got {gens}")
        allowed = {*paint.ENTRY_OPS, *gens, *(paint.PARAMS.get(gens[0], ()) if gens else ())}
        unknown = set(e) - allowed
        if unknown:
            raise SpecError(f"{where}: unknown keys {sorted(unknown)} (allowed here: {sorted(allowed)})")
        if not gens and not any(k in e for k in ("levels", "invert", "blur", "breakup")):
            raise SpecError(f"{where}: needs a generator ({', '.join(paint.GENERATORS)}) or an op (levels, invert, blur, breakup)")
        if gens:
            _check_generator(name, gens[0], e)
            if gens[0] == "mask":
                _check_stack(name, e["mask"])
        if e.get("blend", "multiply") not in paint.BLENDS:
            raise SpecError(f"{where}: blend is one of {', '.join(paint.BLENDS)}")
        if "levels" in e and not (isinstance(e["levels"], list) and len(e["levels"]) in (2, 3)):
            raise SpecError(f"{where}: levels is [lo, hi] or [lo, hi, gamma]")


def _check_generator(name: str, g: str, e: dict) -> None:
    if g in ("tiles", "weave") and not isinstance(e[g], dict):
        raise SpecError(f"paint {name!r}: {g} is an object of parameters")
    if g == "tiles" and e[g].get("mode", "gaps") not in ("gaps", "bevel", "id"):
        raise SpecError(f"paint {name!r}: tiles mode is \"gaps\", \"bevel\" or \"id\"")
    if g == "cells" and (not isinstance(e[g], dict) or e[g].get("mode", "edges") not in ("edges", "distance", "id")):
        raise SpecError(f"paint {name!r}: cells is {{\"scale\", \"mode\": \"edges\" | \"distance\" | \"id\", ...}}")
    if g == "rings" and not (isinstance(e[g], dict) and set(e[g]) <= {"spacing", "warp", "range", "seed"}):
        raise SpecError(f"paint {name!r}: rings is {{\"spacing\"?: m, \"warp\"?: 0..1, \"range\"?: [lo, hi], \"seed\"?}}")
    if g == "random" and not (isinstance(e[g], dict) and set(e[g]) <= {"range", "seed"}):
        raise SpecError(f"paint {name!r}: random is {{\"range\"?: [lo, hi], \"seed\"?: n}}: one value per element")
    if g == "painted" and not (isinstance(e[g], str) and (e[g] == "new" or (
            re.fullmatch(r"[0-9a-f]{16}", e[g]) and painted_path(e[g]).exists()))):
        from . import store
        raise SpecError(f"paint {name!r}: painted is the id of a hand-painted mask (a point cloud `pull` stores "
                        f"under {store.HOME / '_painted'}/<id>.npz), or \"new\" to start one; {e[g]!r} isn't one")
    if g == "image":
        from . import images
        img = e[g]
        if not isinstance(img, dict):
            raise SpecError(f"paint {name!r}: image is an object: {{\"file\" | \"id\" | \"text\", \"at\", "
                            f"\"dir\", \"size\": [w, h], ...}}")
        bad = set(img) - images.KEYS
        if bad:
            raise SpecError(f"paint {name!r}: image: unknown keys {sorted(bad)} (have {', '.join(sorted(images.KEYS))})")
        if sum(k in img for k in ("file", "id", "text")) != 1:
            raise SpecError(f"paint {name!r}: image takes one of \"file\", \"id\", \"text\"")
        if "text" in img:
            t = img["text"]
            if not (isinstance(t, dict) and isinstance(t.get("string"), str)):
                raise SpecError(f"paint {name!r}: image text is {{\"string\": \"...\", \"font\", \"size\", ...}}")
            bad = set(t) - images.TEXT_KEYS
            if bad:
                raise SpecError(f"paint {name!r}: image text: unknown keys {sorted(bad)} "
                                f"(have {', '.join(sorted(images.TEXT_KEYS))})")
            if t.get("align", "left") not in ("left", "center", "right", "justify"):
                raise SpecError(f"paint {name!r}: image text align is left, center, right or justify")
        if img.get("channel", "alpha") not in images.CHANNELS:
            raise SpecError(f"paint {name!r}: image channel is one of {', '.join(images.CHANNELS)}")
        wrap = img.get("wrap", "planar")
        if wrap not in images.WRAPS:
            raise SpecError(f"paint {name!r}: image wrap is one of {', '.join(images.WRAPS)}")
        sz = img.get("size")
        if wrap == "uv":  # the model's own texture space: no placement (images_frame._uv_frame checks its keys)
            pass
        elif not ((isinstance(sz, list) and len(sz) == 2 and any(sz) and all(x is None or float(x) > 0 for x in sz))
                or ("span" in img and wrap in ("cylinder", "sphere"))):
            raise SpecError(f"paint {name!r}: image size is [width, height] in m, > 0 (one may be null: from the "
                            f"image's aspect)" + ("; or a span in degrees" if wrap in ("cylinder", "sphere") else ""))
        if "at" not in img and not (wrap == "cylinder" and "axis" in img) and wrap != "uv":
            raise SpecError(f"paint {name!r}: image needs \"at\" (its centre: a joint, a blob, [x, y, z])")
    if g == "spot":
        sp = e[g]
        if not (isinstance(sp, dict) and "at" in sp and "radius" in sp and set(sp) <= {"at", "radius", "soft", "line"}):
            raise SpecError(f"paint {name!r}: spot is {{\"at\": point | [points], \"radius\": m | [rx, ry, rz], "
                            f"\"soft\"?: 0..1, \"line\"?: true}}")
    if g == "tile":
        t = e[g]
        from . import skin_swatch
        if not (isinstance(t, dict) and (("swatch" in t) != ("file" in t)) and set(t) <= {"swatch", "file", "size", "range", "vary", "seed", "rotate"}):
            raise SpecError(f"paint {name!r}: tile is {{\"swatch\": name | \"file\": path, \"size\"?: m, \"range\"?, \"vary\"?}}")
        if "swatch" in t and t["swatch"] not in skin_swatch.KINDS:
            raise SpecError(f"paint {name!r}: tile swatch is one of {', '.join(skin_swatch.KINDS)}")
        if "file" in t and "size" not in t:
            raise SpecError(f"paint {name!r}: a tile from a file needs \"size\" (m of surface per repeat)")
    if g == "cavity" and e[g] not in ("concave", "convex"):
        raise SpecError(f"paint {name!r}: cavity is \"concave\" or \"convex\"")
    if g in ("ao", "thickness", "sky") and not (isinstance(e[g], list) and len(e[g]) == 2):
        raise SpecError(f"paint {name!r}: {g} is [value at 0, value at 1], e.g. " +
                        ("[0.9, 0.5] (1 in occluded places)" if g == "ao" else "[0.03, 0.01] (1 where thin)"))
