"""Skin tools: the layered skin, its looks, and reading skin from references."""
from __future__ import annotations

import json

from . import skin_route, store
from .mcp_app import mcp
from .tool_common import _out, _spec_arg

# ---------------------------------------------------------------- cloth
def _merge_patch(base, patch):
    """patch merged into base: objects key by key, null deletes, anything else replaces."""
    if not isinstance(patch, dict) or not isinstance(base, dict):
        return patch
    out = dict(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = _merge_patch(out.get(k), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


@mcp.tool(structured_output=False)
def skin(name: str, skin: dict | None = None, replace: bool = False, note: str = "",
         stack_edit: dict | list | str | None = None) -> str:
    """Describe a human's skin (spec["skin"]: tone, age, features, wrinkles, stubble, pores, scars, tattoos, makeup,
    zones, only) as a patch (replace=True starts over); it expands into "skin:<layer>" paint and shading. skin_reference
    lists every key. stack_edit: a measured stack's layers: a name (blush, pale, tan, older, no_stubble, rested, tired),
    a list of names, or {layer: strength}. The reply names keys with no effect. Details: guide(topic="skin")."""
    from . import paint
    from . import skin as skinmod
    spec = store.load(name)
    patch = _spec_arg(skin) if skin is not None else {}
    cur = {} if replace else (spec.get("skin") or {})
    new = _merge_patch(cur, patch)
    new_spec = {**spec, "skin": new}
    edited = ""
    if stack_edit is not None:
        new_spec, edited = skin_route.stack_edit(new_spec, json.loads(stack_edit) if isinstance(stack_edit, str) and stack_edit[:1] in "[{" else stack_edit)
        new = new_spec["skin"]
    tail = skin_route.after_skin(name, spec, new_spec, patch, edited)
    p = skinmod.params(new_spec)
    layers = [k[5:] for k in paint.layers(new_spec) if k.startswith("skin:")]
    v = store.save(name, new_spec, note=note or "skin")
    hx = lambda c: "#" + "".join(f"{int(round(x * 255)):02x}" for x in c)  # noqa: E731
    if not skinmod.shaded(new_spec):  # skin.only without "shading": some layers, the part's own shading untouched
        return (f"saved {name} v{v}: skin only {p['only']}: the skin part's shading and everything else are left as "
                f"they are\n{len(layers)} layers: {', '.join(layers)}\n"
                "sync + look (or look(paint_layer=\"skin:<layer>\")) to see them" + tail)
    base = skinmod.part_base(new_spec)[1]
    t = new.get("tone")
    return (f"saved {name} v{v}: skin on part {p['part']!r}, melanin {p['tone']['melanin']:.2f} blood {p['tone']['blood']:.2f} "
            f"undertone {p['tone']['undertone']:+.1f}, age {p['age']:.0f}\n"
            f"base {hx(base['color'])}, cheeks {hx(skinmod.tone_rgb(t, blood=2.7))}, lips {hx(skinmod.tone_rgb(t, melanin=0.7, blood=10, epidermis=0.45))}, "
            f"palms {hx(skinmod.tone_rgb(t, melanin=0.25, blood=1.7))}; roughness {base['roughness']:.2f}, subsurface "
            f"{base['subsurface_scale'] * 1000:.1f} mm, coat {base['coat']:.2f}\n"
            f"{len(layers)} layers: {', '.join(layers)}\n"
            f"look_skin(\"{name}\") renders close-ups and measures them; look(paint_layer=\"skin:<layer>\") or "
            f"look_skin(layer=...) shows one layer's mask" + _head_hint(new_spec) + tail)


def _head_hint(spec: dict) -> str:
    b = spec.get("base") or {}
    h = b.get("head") or {}
    if (b.get("body") or {}).get("source") != "makehuman" or h.get("source", "gnm") != "gnm" or "follow_body" in h:
        return ""
    return ("\nHINT: this head doesn't follow its body: base.head.follow_body is unset, so the face keeps one adult shape "
            "and its own size whatever the body's age and sex. For a new character set base.head.follow_body: true "
            "(guide(topic=\"skin\"), stage 0); leave it for a character whose head is already approved.")


@mcp.tool(structured_output=False)
def brow_read(name: str, match: bool = False, out: str | None = None):
    """The groomed brow HAIR (skin.hair.brows) against the front picture's, through its fitted camera: lower edge /
    middle line miss in mm at the model, and the picture's iris (limbus, mm at the model; its colour) against the
    drawn one. match=True: skin.hair.brows' placement (drop, tilt, apart, fall, thickness, taper) fitted to the
    picture's hair band and written to `out` (default: the model itself). Paint only. Details: guide(topic="brow_read")."""
    from . import blockin_brows as bb, blockin_eyes as be
    try:
        iris = be.iris_check(name)["text"]
    except Exception as e:  # noqa: BLE001  (no readable iris: the brows still read)
        iris = f"IRIS: not read ({e})"
    if not match:
        return bb.check(name)["text"] + "\n" + iris + "\n" + skin_route.after_brows(name, False)
    r = bb.apply(name, out=out)
    return (r["text"] + f"\nwritten to {r['model']} (skin.hair.brows)\n" + iris + "\n" + skin_route.after_brows(r["model"], True))


@mcp.tool(structured_output=False)
def skin_from_reference(name: str, out: str = "", groups: list[str] | None = None, rounds: int = 2, read_only: bool = False,
                        stubble: bool | None = None, anchor: str = "auto", tone: float | dict | None = None,
                        white: list[dict] | None = None, project: bool | None = None, layers: bool = True,
                        painting: bool = False) -> str:
    """Set the skin from the model's fitted reference pictures, used as a MEASUREMENT (the photo's pixels never ship).
    Photographs (the default): the de-lit atlas (skin_project, as a measurement; a fresh one is reused, project=True
    remakes it), the read on it, and layers=True stores the skin as a STACK OF LAYER MAPS decomposed from it (pigment,
    redness, periorbital, brows, lips, beard, shade: skin.stack). painting=True: the per-picture read instead (tone, zones,
    lips, beard, brows, freckles, folds). read_only=True: the read alone. No pores or roughness are read. out: save to a
    copy. Details: guide(topic="skin_from_reference")."""
    from . import skin_layers, skin_project as spj, skin_read, store
    dst = out or name
    project, pre = skin_route.plan_read(store.load(name), project, painting, read_only)
    if project:
        a = spj.apply(name, out=out or None, opacity=0.0, log=lambda s: None)
        pre += a["text"] + "\n\n"
        name = dst
    if read_only:
        return pre + skin_read.read(name, anchor=anchor, log=lambda s: None, white=white)["text"] + skin_route.after_read(dst, read_only=True)
    has_atlas = skin_read.atlas_source(store.load(name)) is not None
    g = tuple(groups) if groups else (tuple(x for x in skin_read.DEFAULT_GROUPS if x not in ("eyes", "folds")) if has_atlas else skin_read.DEFAULT_GROUPS)
    r = skin_read.apply(name, out=(out or None) if not project else None, groups=g, rounds=rounds,
                        anchor=anchor, stubble=stubble, log=lambda s: None, tone=tone, white=white)
    text = pre + r["text"]
    if layers and has_atlas:
        text += "\n\n" + skin_layers.apply(dst, log=lambda s: None)["text"]
    return text + skin_route.after_read(dst, painting=not has_atlas)


@mcp.tool(structured_output=False)
def skin_project(name: str, out: str = "", views: list[int] | None = None, remove: bool = False, report_only: bool = False,
                 delight: bool = True, ears: bool = False, mirror: bool = True, tone: str = "model", opacity: float = 0.0,
                 detail_depth: float = 0.00012, parse: str = "mediapipe", eyes: bool = False, stubble: str = "picture") -> str:
    """The fitted reference pictures as a de-lit ATLAS in the head's own texture space (the measurement
    skin_from_reference fits the skin's layer stack to; it runs this itself): projected, DE-LIT into albedo, the unseen
    filled, fine lines as relief; saved as skin.projection. opacity 0 (default): nothing of the photo is laid as colour;
    > 0: a judging overlay only, which the export refuses. The reply says what was left out and what is ambiguous. out:
    save to a copy; remove=True takes it out. Details: guide(topic="skin_project")."""
    from . import skin_project as spj
    kw = dict(views=views, delight=delight, ears=ears, mirror=mirror, tone=tone, parse=parse or None, log=lambda s: None)
    dst = out or name
    if remove:
        return spj.apply(name, out=out or None, remove=True)["text"] + skin_route.after_project(dst, removed=True)
    if report_only:
        return spj.make(name, **kw)["text"] + skin_route.after_project(dst, report_only=True)
    return spj.apply(name, out=out or None, opacity=opacity, detail_depth=detail_depth, eyes=eyes, stubble=stubble, **kw)["text"] + skin_route.after_project(dst, opacity)


@mcp.tool(structured_output=False)
def skin_reference() -> str:
    """Everything the `skin` description takes: zones, tone model, features, wrinkles, hair, scars, tattoos and
    make-up, with keys and defaults. Details: guide(topic="skin_reference")."""
    from . import skin as skinmod
    from . import skin_makeup
    return skinmod.reference() + "\n\n" + skin_makeup.reference() + "\n" + skin_route.after_reference()


@mcp.tool(structured_output=False)
def look_skin(name: str, views: list[str] | None = None, size: int = 768, light: str | None = None,
              flat: bool = False, layer: str | None = None, save: str | None = None, beside: str = "",
              view: int | None = None):
    """Fast bare-skin close-ups with measurements vs real-skin photos. views (face, three_quarter, cheek, eye, mouth,
    ear, hand, ...), light "studio"|"soft"|"back"|"rake" (low side light: relief), flat (unlit colour), layer (one mask),
    size, save. beside: ONE region (face, forehead, brows, eye, cheek, nose, mouth, jaw) beside the reference crop at the
    same framing (view: which picture, default the front), written as the two files review_view takes: the skin gate.
    Details: guide(topic="look_skin")."""
    from . import skin_look
    if beside:
        im, text = skin_look.beside(name, beside, view=view, size=size, light=light, views=views, flat=flat, layer=layer)
        return [_out(im, save), text]
    sheet, text, _ = skin_look.look(name, views=tuple(views) if views else skin_look.DEFAULT, size=size, light=light,
                                    flat=flat, layer=layer)
    return [_out(sheet, save), text + "\n" + skin_route.stale_line(store.load(name)) + skin_route.after_look(name)]
