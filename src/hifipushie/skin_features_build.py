"""`build`: every feature's layers for a spec. Part of the skin features (skin_features.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import skin_features
from .spec import SpecError
from .skin_features import _has, _opt, _where, _zones
from .skin_features_eyes import _eyes
from .skin_features_hair import _hair
from .skin_features_marks import _freckle_map, _scars, _tattoos, _wrinkles, freckle_options
from .skin_features_mouth import _gnm_mouth

def build(spec: dict, p: dict, J: dict, out: dict, T, ctx: dict) -> list:
    """Adds the feature layers to `out`. Broad, soft layers are "_pre" (composited per vertex into the skin's base,
    paint_apply.precomposite); what needs detail finer than the mesh (hairs, dots, lines, ink) stays a layer of the node
    program, built from tiling swatches, images and spots only: a renderer's shader has room for a few dozen such
    layers, and none for a hundred procedural ones. Returns the masks of skin without pores (scar tissue)."""
    part, t, seed, age = p["part"], p["tone"], p["seed"], p["age"]
    old, child, thin, base_r = ctx["old"], ctx["child"], ctx["thin"], ctx["base_r"]
    dark = t["melanin"]
    ctx = {**ctx, "torso": "chest" in J, "spec": spec}
    ctx["smooth"] = []
    if p.get("stack") and ctx["face"]:   # (skin_layers) the colour as a stack of layer maps from the reference: over the
        from . import skin_layers       # broad colour layers laid so far, under every fine generator below
        skin_layers.layers(spec, p["stack"], out, part)
    from . import paint as _paint
    ctx["eyes"] = all(e in (_paint._expanded(spec).get("blobs") or {}) for e in ("eye.L", "eye.R"))  # eyeballs: lid margins
    from . import lashes as _lashes
    ctx["lash_geometry"] = ctx["eyes"] and bool(_lashes.wanted(spec))  # lash ribbons (lashes.py) over the painted lines
    if ctx["lash_geometry"]:
        lm_ = _lashes.for_spec(spec)
        ctx["lash_curves"] = None if lm_ is None else {k: [np.round(c, 5).tolist() for c in v] for k, v in lm_["curves"].items()}
    from .skin_makeup import resolve as _mk_resolve
    f0 = _mk_resolve(p["makeup"]).get("foundation")
    cover = float(np.clip(f0 if isinstance(f0, (int, float)) else (f0 or {}).get("amount", 1.0 if f0 else 0.0), 0, 1)) if f0 else 0.0
    ctx["show"] = 1.0 - 0.75 * cover  # how much of the skin's own marks shows through foundation

    def layer(name, extra_mask=None, pre=False, **ly):
        if extra_mask:
            ly["mask"] = list(ly.get("mask") or []) + [{"mask": extra_mask}]
        if "opacity" in ly:
            ly["opacity"] = round(float(np.clip(ly["opacity"], 0, 1)), 4)
        if pre:
            ly.pop("height", None)
            ly["_pre"] = True
        out[f"skin:{name}"] = {"part": part, **ly}

    f = p["features"]
    bad = set(f) - set(skin_features.FEATURES)
    if bad:
        raise SpecError(f"skin features: unknown {sorted(bad)} (have {', '.join(skin_features.FEATURES)})")
    show = ctx["show"]

    # ---- broad colour: tan, sunburn, flush
    o = _opt(f.get("tan"), "features.tan")
    if o:
        bare = [z for z in ("palm", "sole", "lips") if _has(z, ctx)]  # what never tans
        layer("tan", o.get("mask"), pre=True, color=T(melanin=1 + 1.0 * o["amount"], blood=1.1), opacity=0.8,
              mask=(_where(o, [], ctx) or [{"levels": [0.0, 1.0]}]) + [{"mask": _zones(bare), "blend": "subtract"}] if bare else _where(o, [], ctx))
    o = _opt(f.get("sunburn"), "features.sunburn")
    if o:
        w = _where(o, ["forehead", "nose", "cheekbone", "shoulder", "collarbone"], ctx)
        layer("sunburn", o.get("mask"), pre=True, color=T(blood=4.5, oxygenation=0.85), opacity=0.6 * o["amount"],
              mask=w + [{"noise": {"scale": 0.03, "range": [0.2, 0.75], "seed": seed + 40}, "weight": 0.5}])
    o = _opt(f.get("flush"), "features.flush")
    if o:
        layer("flush", o.get("mask"), pre=True, color=T(blood=4.0, oxygenation=0.85), opacity=0.55 * o["amount"],
              mask=_where(o, ["cheek", "cheekbone", "nose_tip", "ear", "chin"], ctx) +
              [{"noise": {"scale": 0.012, "range": [0.25, 0.8], "seed": seed + 41, "warp": 0.8}, "weight": 0.6}])

    # ---- pigment spots
    o = _opt(f.get("freckles"), "features.freckles", ("size", "clump", "dark", "zones", "engine"))
    if o and o.get("engine", "map") == "map" and ctx["face"] and "lm_jaw_1.L" in J:
        _freckle_map(ctx["spec"], p, J, o, layer, T, ctx)
        o = None
    if o:
        a = float(o["amount"])
        k = float(o.get("size", 0.0018)) / 0.0018
        w = _where(o, ["nose", "cheek", "cheekbone", "forehead", "upper_lip", "chin", "shoulder", "forearm", "collarbone"], ctx)
        lo = float(np.clip(0.42 - 0.3 * min(a, 1.2), 0.04, 0.6))  # more of the swatch's faint macules show as it rises
        layer("freckles", o.get("mask"), color=T(melanin=2.6 + 1.6 * (1 - dark), blood=1.3), opacity=min(0.4 + 0.3 * a, 0.75) * show,
              mask=[{"tile": {"swatch": "freckles", "size": round(0.042 * k, 5), "range": [round(lo, 3), round(lo + 0.55, 3)], "vary": False}}] + w)
    o = _opt(f.get("moles"), "features.moles", ("at", "size"))
    if o:
        sz = float(o.get("size", 0.0025))
        sd = seed + int(o.get("seed", 0))
        stacks = []
        scattered = not o.get("at") or (isinstance(f.get("moles"), dict) and "amount" in f["moles"])
        if scattered and ctx["face"] and "lm_jaw_1.L" in J and not o.get("where"):
            # a few on the face from the mark map (the swatch's "strongest marks" were nearly invisible): ~12 at amount 1
            from . import skin_marks
            q = {**freckle_options({"amount": 1e-4}), "moles": int(round(12 * float(o["amount"]))), "seed": int(o.get("seed", 0))}
            path, place, _ = skin_marks.freckle_map(ctx["spec"], p["part"], J, q)
            stacks.append([{"image": {"file": path, **place, "channel": "b"}}])
        elif scattered:
            hi = float(np.clip(0.955 - 0.05 * o["amount"], 0.8, 0.96))  # only the swatch's few strongest marks
            stacks.append([{"tile": {"swatch": "freckles", "size": round(0.06 * sz / 0.0016, 4), "range": [round(hi, 3), round(hi + 0.04, 3)],
                                     "vary": False, "rotate": True}}] + (_where(o, [], ctx)))
        if o.get("at"):
            pts = o["at"] if isinstance(o["at"], list) and not (len(o["at"]) == 3 and all(isinstance(x, (int, float)) for x in o["at"])) else [o["at"]]
            stacks.append([{"spot": {"at": pts, "radius": 0.5 * sz, "soft": 0.35}}])
        m = [{"mask": st, **({"blend": "max"} if i else {})} for i, st in enumerate(stacks)]
        layer("moles", o.get("mask"), color=T(melanin=9.0, blood=1.3), opacity=0.92, roughness=min(base_r + 0.08, 0.9), height=0.00022, mask=m)
    spots = f.get("age_spots", max(0.0, old * (0.35 + 1.2 * p["sun"])))
    o = _opt(spots, "features.age_spots", ("size",))
    if o:
        sz = float(o.get("size", 0.006))
        w = _where(o, ["temple", "cheekbone", "cheek_side", "back_of_hand", "forearm"], ctx) + \
            [{"vertex": True, "mask": _zones(["forehead", "scalp"]), "blend": "max", "weight": 0.35}] if ctx["face"] else _where(o, ["back_of_hand", "forearm"], ctx)
        a = float(np.clip(o["amount"], 0, 1.5))
        layer("age_spots", o.get("mask"), pre=True, color=T(melanin=1.6 + 2.9 * (1 - dark), blood=0.9), opacity=0.55 * show * (1 - 0.4 * dark),
              mask=[{"noise": {"scale": sz, "range": [0.74 - 0.14 * a, 0.78 - 0.14 * a], "seed": seed + 57, "octaves": 2, "warp": 0.5}}] + w)
        layer("age_spots_small", o.get("mask"), color=T(melanin=1.8 + 1.8 * (1 - dark), blood=0.9), opacity=0.5 * show * (1 - 0.4 * dark),
              mask=[{"tile": {"swatch": "freckles", "size": 0.11, "range": [0.62 - 0.2 * min(a, 1), 0.8 - 0.2 * min(a, 1)], "vary": False}}] + w)
    o = _opt(f.get("blemishes"), "features.blemishes", ("size",))
    if o:
        sz = float(o.get("size", 0.003))
        sd = seed + int(o.get("seed", 0))
        a = float(o["amount"])
        w = _where(o, ["cheek", "cheek_side", "chin", "forehead", "jaw", "nose_wing"], ctx)
        # the freckle swatch's marks at a larger size, another way up: the halo is a mark's whole extent, the bump its core
        size = round(0.06 * sz / 0.0013, 4)
        lo = float(np.clip(0.75 - 0.5 * min(a, 1.2), 0.1, 0.8))
        tile = {"swatch": "freckles", "size": size, "vary": False, "rotate": True}
        layer("blemish_halo", o.get("mask"), color=T(blood=5.5, oxygenation=0.8), opacity=0.75 * (0.5 + 0.5 * show),
              mask=[{"tile": {**tile, "range": [round(lo, 3), round(lo + 0.25, 3)]}}] + w)
        # (under a measured stack: colour only, no height: a stacked head's material is near Cycles' shader stack limit,
        # and the blemishes' bump tipped Tess's and a test head's over: "would render black")
        hk = {} if p.get("stack") else {"height": 0.0004}
        layer("blemish_bump", o.get("mask"), color=T(blood=6.5, melanin=1.15), opacity=0.6 * (0.5 + 0.5 * show), roughness=max(base_r - 0.14, 0.2),
              mask=[{"tile": {**tile, "range": [round(lo + 0.3, 3), round(lo + 0.5, 3)]}}] + w, **hk)

    # ---- veins
    v_def = max(0.0, 0.25 * thin - 0.05 + 0.6 * old) * (1 - 0.6 * dark)
    o = _opt(f.get("veins", v_def), "features.veins")
    if o and o["amount"] > 0.05:
        a = float(o["amount"])
        groups = []
        if ctx["hands"] and ctx["arms"]:
            for sx in (".L", ".R"):
                d = J[f"wrist{sx}"] - J[f"elbow{sx}"]
                d = (d / max(np.linalg.norm(d), 1e-9)).round(3).tolist()
                groups.append((sx, d, [f"back_of_hand{sx}", f"wrist_inner{sx}", f"forearm{sx}"]))
        if ctx["face"] and (a > 0.5 or old > 0.3):
            groups.append(("", [0.3, 0.2, 1.0], ["temple"]))
        for i, (sx, d, zs) in enumerate(groups):
            zs = o.get("where") or zs
            rot = abs(d[2]) > 0.6  # the swatch's lines run across it: turned to run along the limb
            m = [{"tile": {"swatch": "wrinkles", "size": 0.075, "rotate": bool(rot), "range": [0.25, 0.8], "vary": False}}, {"vertex": True, "mask": _zones(zs)}]
            layer(f"veins{sx.replace('.', '_')}", o.get("mask"), color=[0.72, 0.84, 0.86], mix="multiply", opacity=min(0.5 * a, 0.9) * (0.6 if not sx else 1) * show,
                  mask=m, **({"height": round(0.0005 * old * min(a, 1.5), 6)} if sx and old > 0.2 else {}))

    _eyes(spec, p, J, out, layer, T, ctx)
    # the eye corners' wet red (caruncle, canthus) fades as the lid closes: on a closed eye it showed as red lines at the
    # seam's ends (a blind review read the closed lid as a cut)
    wb_ = float(np.clip(float((((spec.get("base") or {}).get("head") or {}).get("pose") or {}).get("lid_upper", 0.0) or 0.0) / 0.0095, 0.0, 1.0))
    if wb_ > 0:
        for k_ in [k for k in out if any(t in k for t in ("caruncle", "canthus", "eye_shade"))]:
            if out[k_].get("opacity") is not None:
                out[k_]["opacity"] = round(float(out[k_]["opacity"]) * (1 - wb_), 4)
    _gnm_mouth(spec, out, part)
    _wrinkles(p, J, layer, T, ctx)
    from . import skin_folds
    skin_folds.build(spec, p, J, layer, ctx)
    _hair(p, J, layer, T, ctx)
    if p.get("projection") and ctx["face"]:   # the references as albedo (skin_project): over our colours and painted hair
        from . import skin_project_model
        skin_project_model.layers(spec, p["projection"], out, part)
    _scars(spec, p, J, layer, T, ctx)
    _tattoos(spec, p, layer, ctx)
    from . import skin_makeup
    skin_makeup.build(spec, p, J, layer, T, ctx)
    return ctx["smooth"]
