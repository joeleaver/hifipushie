"""Marks on the skin: wrinkles, freckles, scars, tattoos. Part of the skin features (skin_features.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import skin_features
from .spec import SpecError
from .skin_features import _has, _hex, _zones

def _wrinkles(p, J, layer, T, ctx) -> None:
    w = p["wrinkles"]
    bad = set(w) - set(skin_features.WRINKLES)
    if bad:
        raise SpecError(f"skin wrinkles: unknown {sorted(bad)} (have {', '.join(skin_features.WRINKLES)})")
    if not ctx["face"]:
        return
    from .skin_params import _age_curve
    from .skin_zones import interocular
    age, det = p["age"], p["detail"]
    k_all = float(w.get("amount", 1.0)) * det
    io = interocular(J)
    base_r = ctx["base_r"]
    dflt = {"forehead": _age_curve(age, 26, 72), "glabella": _age_curve(age, 36, 75), "crows_feet": _age_curve(age, 28, 70),
            "under_eye": _age_curve(age, 30, 75), "nasolabial": 0.12 + 0.88 * _age_curve(age, 24, 80),
            "marionette": _age_curve(age, 42, 82), "lip_lines": _age_curve(age, 48, 85), "neck": 0.1 + 0.9 * _age_curve(age, 35, 80),
            "crepe": _age_curve(age, 50, 88)}
    amt = {k: float(w.get(k, d)) * k_all for k, d in dflt.items()}
    # multiplied in: a crease is a little darker and redder (thin skin); its shadow is the geometry's. (It was [0.7, 0.58,
    # 0.55] at 0.75: over a stubble shadow on facesliders' joint Garrett, where the landmark line lay beside his own
    # deep fold, it painted a dark red-brown streak beside the mouth.)
    crease = [0.84, 0.77, 0.75]

    def groove(name, a, depth, mask, tint=0.5):
        if a <= 0.02:
            return
        layer(f"wrinkle_{name}", height=-round(depth * min(a, 2.0), 7), color=crease, mix="multiply", opacity=min(tint * a, 0.8),
              roughness=min(base_r + 0.1, 0.95), mask=mask)

    def pt(j, off):
        return {"at": j, "offset": [round(float(x) * io, 5) for x in off]}

    def rays(lines, radius):
        """Lines as tapered spots: [(joint, start offset, end offset)] in interocular units, both sides mirrored."""
        stack = []
        for j, a0, a1 in lines:
            for sd, sx in ((".L", 1), (".R", -1)) if j.endswith(".L") else (("", 1),):
                jj = j[:-2] + sd if sd else j
                mid = [(a0[i] + a1[i]) / 2 for i in range(3)]
                P = [pt(jj, [sx * q[0], q[1], q[2]]) for q in (a0, mid, a1)]
                stack.append({"spot": {"at": P, "radius": [round(radius * io * k, 6) for k in (0.9, 1.0, 0.35)], "soft": 0.9, "line": True},
                              **({"blend": "max"} if stack else {})})
        return stack

    # (r18: the frown lines were two straight tapered strokes, mirrored: "11" marks; Garrett's photo has a soft broad furrow
    # rising from the brow's head and bowing toward the midline, one side much stronger than the other, of uneven depth)
    def furrow(sd, k):
        """One side's frown furrow: a broad soft core along a bowed path plus a wider shallow trough, faded at both ends."""
        sx = 1 if sd == ".L" else -1
        j = "lm_brow_inner" + sd
        # (g2: on the brow heads it read as two smudges over the brows; the photo's lies medial of the brow head, ~60 %
        # of the way to the midline, from the brows' lower edge up)
        P = [pt(j, [sx * q[0], q[1], q[2]]) for q in knots]
        core = {"spot": {"at": P, "radius": [round(r * io, 6) for r in (0.06, 0.075, 0.07, 0.05)], "soft": 1.0, "line": True}}
        wide = {"spot": {"at": P, "radius": [round(r * io, 6) for r in (0.12, 0.15, 0.14, 0.1)], "soft": 1.0, "line": True},
                "blend": "max", "weight": 0.45}
        mid = pt(j, [sx * -0.06, -0.012, 0.14])
        fade = {"spot": {"at": mid, "radius": [round(r * io, 6) for r in (0.2, 0.42, 0.2)], "soft": 1.0}, "blend": "multiply"}
        crease = {"spot": {"at": P[:3], "radius": [round(r * io, 6) for r in (0.025, 0.035, 0.03)], "soft": 1.0, "line": True},
                  "blend": "max", "weight": 0.7}   # (the furrow's floor: the photo's has a line in it, at one side)
        return {"mask": [core, crease, wide, fade], "weight": k}   # (weight: the second side's share, blended by max)
    # (r22: the photo's furrows rise from the brow heads ~2.5x as far, into the forehead lines, and lie nearer the brow
    # heads; at -.07..-.095 io and .3 io long the two sides merged into one short pink spot between the brows)
    knots = [(-0.04, -0.012, -0.08), (-0.055, -0.012, 0.06), (-0.05, -0.012, 0.24), (-0.03, -0.012, 0.42)]  # the furrow's bowed path
    gside = str(w.get("glabella_side", "R" if int(p.get("seed", 0) or 0) % 2 == 0 else "L")).upper()
    lead, other = (".R", ".L") if gside == "R" else (".L", ".R")
    # uneven depth along the furrow and between the sides (a muscle's crease, not a ruled line): soft spots of seeded
    # place and size along both paths, multiplied in (was a per-pixel "noise" at .12 io: skin features carry no
    # procedural noise in the shader; spots are cheap and follow the landmarks)
    rng = np.random.default_rng(int(p.get("seed", 0) or 0) * 7919 + 211)
    lumps, lrad = [], []
    for sd in (".L", ".R"):
        sx = 1 if sd == ".L" else -1
        for t in np.sort(rng.uniform(0.05, 2.95, 4)):
            i = int(t)
            q = [knots[i][c] + (t - i) * (knots[i + 1][c] - knots[i][c]) for c in range(3)]
            lumps.append(pt("lm_brow_inner" + sd, [sx * (q[0] + rng.uniform(-0.01, 0.01)), q[1], q[2]]))
            lrad.append(round(float(rng.uniform(0.045, 0.09)) * io, 6))
    glabella = [furrow(lead, 1.0), {**furrow(other, 0.35), "blend": "max"},
                {"spot": {"at": lumps, "radius": lrad, "soft": 1.0}, "blend": "multiply", "weight": 0.25}]

    # the lines of expression, each a tapered groove, in one layer: every group's strength scales its own mask
    groups = [
        # (r17: the frown lines run from ~.2 io up between the brows down to the nasion, a soft furrow; were +-.09, half the photo's)
        # (r18: 0.9 -> 3.2: the broad furrow spreads the same depth wider, faded at its ends, x uneven spots: at .9 it vanished)
        ("glabella", 3.2, glabella),
        ("crows_feet_rays", 0.7, rays([("lm_eye_outer.L", (0.06, 0.03, 0.01), (0.34, 0.22, 0.14)), ("lm_eye_outer.L", (0.07, 0.03, -0.02), (0.38, 0.25, -0.02)),
                                  ("lm_eye_outer.L", (0.06, 0.03, -0.05), (0.33, 0.22, -0.18)), ("lm_eye_outer.L", (0.05, 0.03, -0.09), (0.24, 0.16, -0.3))], 0.014)),
        ("under_eye_rays", 0.65, rays([("lm_lid_lower.L", (-0.22, 0.02, -0.07), (0.24, 0.06, -0.11)), ("lm_lid_lower.L", (-0.2, 0.02, -0.15), (0.28, 0.08, -0.2)),
                                  ("lm_lid_lower.L", (-0.12, 0.01, -0.24), (0.3, 0.1, -0.3))], 0.014)),
        # the folds lie where the surface itself folds: the landmark line finds the region, the surface's concavity the
        # fold (a head with its own deep fold beside the line keeps only a trace of the line)
        ("nasolabial", 1.0, [{"mask": _zones(["nasolabial"], 1.8)}, {"cavity": "concave", "radius": [0.06, 0.012], "weight": 0.7}]),
        ("marionette", 0.9, [{"mask": _zones(["marionette"], 1.7)}, {"cavity": "concave", "radius": [0.06, 0.012], "weight": 0.7}])]
    amt["crows_feet_rays"], amt["under_eye_rays"] = 0.5 * amt["crows_feet"], 0.4 * amt["under_eye"]
    for nm, zs, size, rot in (("crows_feet", ["crows_feet"], 0.022, False), ("under_eye", ["under_eye"], 0.026, False)):
        a = amt[nm]
        if a > 0.02:  # a fan of fine creases of uneven depth, under the few drawn ones
            groove(nm + "_fine", a, 0.0004, [{"tile": {"swatch": "wrinkles", "size": size, "rotate": rot, "range": [0.5 - 0.42 * min(a, 1), 1.0],
                                                       "vary": False}}, {"vertex": True, "mask": _zones(zs, 1.1)}], 0.2)
    for lname, members in (("folds", ("nasolabial", "marionette")), ("glabella", ("glabella",)), ("crows_feet", ("crows_feet_rays",)), ("under_eye", ("under_eye_rays",))):
        stack = []
        for name, k, m in groups:
            a = float(np.clip(amt[name] * k, 0, 1.6))
            if name not in members or a <= 0.03:
                continue
            stack.append({"mask": m + [{"levels": [0.0, round(1.6 / a, 3)]}], **({"blend": "max"} if stack else {})})
        if stack:  # (one mask of all ~20 tapered lines ran Cycles out of stack under the bump)
            # (r22: the glabella's furrows a neutral grey and fainter: with the shared reddish crease tint at .75 they read as a
            # pink spot, glabella a* - cheek -0.1 vs the photo's -1.4)
            gl = lname == "glabella"
            layer(f"wrinkle_{lname}", height=-0.00065, color=[0.86, 0.86, 0.865] if gl else crease, mix="multiply", opacity=0.8 if gl else 0.75,
                  roughness=min(base_r + 0.1, 0.95), mask=stack)
    # fields of lines: a tiling swatch of wandering lines, laid across (forehead, neck) or turned (above the lip)
    a = amt["forehead"]
    if a > 0.02:
        # (r17: long even lines in a band over the brows, "forehead_lines"; were the "forehead" colour zone's upper dome)
        groove("forehead", a, 0.00035, [{"tile": {"swatch": "brow_lines", "size": 0.032, "range": [0.3 - 0.25 * min(a, 1), 1.0], "vary": False}},
                                        {"vertex": True, "mask": _zones(["forehead_lines"], 1.0)}], 0.08)
    a = amt["lip_lines"]
    if a > 0.02:
        groove("lip_lines", a, 0.00022, [{"tile": {"swatch": "wrinkles", "size": 0.02, "rotate": True, "range": [0.55 - 0.45 * min(a, 1), 1.0], "vary": False}},
                                         {"vertex": True, "mask": _zones(["upper_lip", "soul_patch"], 0.95)}, {"zone": "lips", "blend": "subtract"}], 0.35)
    a = amt["neck"]
    if a > 0.02:
        groove("neck", a, 0.0005, [{"tile": {"swatch": "wrinkles", "size": 0.1, "range": [0.5 - 0.42 * min(a, 1), 1.0], "vary": False}}, {"vertex": True, "mask": _zones(["neck"], 0.9)}], 0.2)
    a = amt["crepe"]
    if a > 0.02:  # old skin: the primary lines deepen into a visible cross-hatch, the fine ones go
        # (relief first, hardly any tint: at bust distance crepe is a change of sheen, not drawn lines)
        zs = ["cheek", "cheek_side", "under_eye", "neck", "upper_lip", "jaw"] + \
             (["back_of_hand", "forearm"] if ctx["hands"] and ctx["arms"] else [])
        groove("crepe", a, 0.00016, [{"tile": {"swatch": "coarse", "size": 0.024, "range": [0.12, 1.0]}}, {"vertex": True, "mask": _zones(zs, 1.1)}], 0.1)
        groove("cheek_lines", a, 0.00026, [{"tile": {"swatch": "wrinkles", "size": 0.04, "rotate": True, "range": [0.35, 1.0], "vary": False}},
                                          {"vertex": True, "mask": _zones(["cheek", "cheek_side", "jaw"], 1.0)}], 0.1)


def freckle_options(o: dict) -> dict:
    from . import skin_marks
    z = dict(skin_marks.FRECKLE_ZONES)
    zo = o.get("zones") or {}
    if not isinstance(zo, dict) or set(zo) - set(z):
        raise SpecError(f"skin features.freckles: zones is {{zone: weight}} over {', '.join(z)}")
    z.update({k: float(v) for k, v in zo.items()})
    return {"amount": float(np.clip(o["amount"], 0, 3)), "size": float(o.get("size", 0.0004)), "clump": float(np.clip(o.get("clump", 0.6), 0, 1)),
            "dark": float(np.clip(o.get("dark", 0.2), 0, 1)), "moles": 0, "zones": z, "seed": int(o.get("seed", 0))}


def _freckle_map(spec, p, J, o, layer, T, ctx) -> None:
    """Freckles on the face as a unique map (skin_marks_freckles.freckle_map: irregular macules, clustered, where the sun falls),
    on the body (shoulders, forearms, the chest's V) from the freckle swatch at two sizes mixed (vary: no repeat)."""
    from . import skin_marks_freckles
    t = p["tone"]
    dark = t["melanin"]
    show = ctx["show"]
    a = float(o["amount"])
    q = freckle_options(o)
    path, place, _ = skin_marks_freckles.freckle_map(spec, p["part"], J, q)
    im = lambda ch: {"image": {"file": path, **place, "channel": ch}}  # noqa: E731
    # ephelides: more melanin in the same skin (light tan to brown on fair skin; on dark skin hardly a change)
    # (one layer: each freckle's darkness is its value in the map, faint tan to brown)
    layer("freckles", o.get("mask"), color=T(melanin=3.2 + 2.0 * (1 - dark), blood=1.7, oxygenation=0.8), opacity=round(min(0.75 + 0.12 * a, 0.95) * show, 3), mask=[im("r")])
    body = [z for z in ("shoulder", "forearm", "chest") if _has(z, ctx)] + (["collarbone"] if ctx["torso"] else [])
    if body:
        lo = float(np.clip(0.42 - 0.3 * min(a, 1.2), 0.04, 0.6))
        k = q["size"] / 0.0016
        layer("freckles_body", o.get("mask"), color=T(melanin=2.6 + 1.6 * (1 - dark), blood=1.3), opacity=min(0.4 + 0.3 * a, 0.75) * show,
              mask=[{"tile": {"swatch": "freckles", "size": round(0.042 * k, 5), "range": [round(lo, 3), round(lo + 0.55, 3)], "vary": True, "rotate": True}},
                    {"vertex": True, "mask": _zones(body)}])


def _points(v, what):
    ok = isinstance(v, list) and len(v) >= 2 and not all(isinstance(x, (int, float)) for x in v)
    if not ok:
        raise SpecError(f"{what}: \"path\" is a list of 2+ points (joint | [x, y, z] | {{\"at\": joint, \"offset\"}})")
    return v


def _scars(spec, p, J, layer, T, ctx) -> None:
    from . import paint_patterns
    base_r, seed = ctx["base_r"], p["seed"]
    for i, sc in enumerate(p["scars"]):
        what = f"skin scars[{i}]"
        if not isinstance(sc, dict) or sc.get("kind") not in skin_features.SCARS:
            raise SpecError(f"{what}: {{\"kind\": {' | '.join(skin_features.SCARS)}, ...}}")
        bad = set(sc) - {"kind", "path", "at", "radius", "zone", "width", "age", "normal", "seed", "mask", "amount"}
        if bad:
            raise SpecError(f"{what}: unknown keys {sorted(bad)}")
        kind, old = sc["kind"], float(np.clip(sc.get("age", 1.0), 0, 1))
        sd = seed + 120 + 7 * i + int(sc.get("seed", 0))
        amt = float(sc.get("amount", 1.0))
        n = f"scar{i}_{kind}"
        # fresh: red-purple, swollen; healed: paler than the skin (no melanocytes), flat or sunk, smooth and a bit shiny
        col = T(melanin=1.0 - 0.75 * old, blood=4.5 - 3.9 * old, oxygenation=0.55 + 0.2 * old)
        if "path" in sc:
            pts = _points(sc["path"], what)
            w = float(sc.get("width", {"cut": 0.0016, "surgical": 0.0014, "keloid": 0.005}.get(kind, 0.002)))
            line = {"spot": {"at": pts, "radius": [round(0.5 * w * (0.55 if j in (0, len(pts) - 1) else 1.0), 6) for j in range(len(pts))],
                             "soft": 0.6, "line": True}}
            wide = {"spot": {"at": pts, "radius": round(1.6 * w, 6), "soft": 0.9, "line": True}}
            area = [line]
        else:
            if "zone" in sc:
                area = [{"zone": sc["zone"]}]
            elif "at" in sc:
                area = [{"spot": {"at": sc["at"], "radius": float(sc.get("radius", 0.02)), "soft": 0.35}}]
            else:
                raise SpecError(f"{what}: needs \"path\" (a line), or \"at\" + \"radius\" or \"zone\" (a patch)")
            plain = list(area)
            wide = None
            if kind in ("cut", "surgical"):
                raise SpecError(f"{what}: a {kind} scar runs along a \"path\"")
        m_extra = sc.get("mask")
        if kind in ("cut", "surgical"):
            layer(n + "_halo", m_extra, pre=True, color=T(blood=2.4 - 1.6 * old, melanin=1.1), opacity=0.35 * amt, mask=[wide])
            layer(n, m_extra, color=col, opacity=0.85 * amt, roughness=max(base_r - 0.14, 0.2),
                  height=round((0.00035 - 0.0005 * old) * amt, 7), mask=area)
            if kind == "surgical":  # stitch marks: paired dots either side, ~6 mm apart
                C = paint_patterns.resolve_spot(spec, {"at": pts, "radius": 0.001})["c"]
                nrm = np.asarray(sc.get("normal", [0, -1, 0]), float)
                seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
                s = np.concatenate([[0], np.cumsum(seg)])
                dots = []
                for d in np.arange(0.004, s[-1] - 0.002, 0.006):
                    j = min(int(np.searchsorted(s, d) - 1), len(seg) - 1)
                    q = C[j] + (C[j + 1] - C[j]) * (d - s[j]) / max(seg[j], 1e-9)
                    side = np.cross(C[j + 1] - C[j], nrm)
                    side /= max(np.linalg.norm(side), 1e-9)
                    dots += [(q + 2.6 * w * side).round(5).tolist(), (q - 2.6 * w * side).round(5).tolist()]
                if dots:
                    layer(n + "_stitches", m_extra, color=col, opacity=0.7 * amt, height=-0.00012,
                          mask=[{"spot": {"at": dots, "radius": round(0.45 * w, 6), "soft": 0.6}}])
        elif kind == "keloid":
            layer(n, m_extra, color=T(melanin=1.25 - 0.3 * old, blood=4.2 - 1.6 * old, oxygenation=0.5), opacity=0.9 * amt,
                  roughness=max(base_r - 0.2, 0.18), height=round(0.0009 * amt, 6), mask=area)
        elif kind == "burn":
            ragged = area + [{"breakup": {"amount": 0.35, "scale": 0.008, "sharpness": 0.6, "seed": sd}}]
            layer(n, m_extra, pre=True, color=T(melanin=0.45, blood=2.4 - 1.2 * old), opacity=0.85 * amt, roughness=max(base_r - 0.17, 0.2), mask=ragged)
            layer(n + "_red", m_extra, pre=True, color=T(melanin=1.5, blood=4.0 - 1.5 * old, oxygenation=0.6), opacity=0.6 * amt,
                  mask=[{"noise": {"scale": 0.007, "range": [0.5, 0.62], "seed": sd + 1, "warp": 0.9}}, {"mask": ragged}])
            layer(n + "_webs", m_extra, height=round(-0.0006 * amt, 6),  # a net of taut furrows in contracted tissue
                  mask=[{"tile": {"swatch": "coarse", "size": 0.05, "vary": False}}, {"mask": area}])
        elif kind == "pockmarks":
            w = float(sc.get("width", 0.002))
            dots = [{"tile": {"swatch": "stubble", "size": round(0.012 * w / 0.00018, 4), "range": [0.2, 0.8], "vary": False}}, {"mask": area}]
            layer(n, m_extra, color=T(melanin=0.8, blood=1.3 - 0.4 * old), opacity=0.4, height=round(-0.00038 * amt, 6), mask=dots)
            continue  # the skin between the pits keeps its pores
        ctx["smooth"].append(area if not m_extra else area + [{"mask": m_extra}])


def tattoo_image(img: dict, age: float, ink) -> tuple[dict, bool]:
    """The tattoo's image as it has aged: (a paint image dict pointing at the processed file, has its own colours).
    Lines spread (a blur growing with the years, in the picture's own millimetres), black turns blue-green and thins,
    colours lose saturation (yellows and reds first)."""
    from PIL import Image, ImageFilter
    from . import images
    src = images.source_path(img)
    text = "text" in img
    sz = img.get("size") or [None, None]
    key = hashlib.sha1(json.dumps([str(src), round(age, 2), ink, sz, 3], default=str).encode()).hexdigest()[:16]
    out = images.store_dir() / f"tt_{key}.png"
    if not out.exists():
        im = Image.open(src).convert("RGBA")
        W, H = im.size
        width_m = float(sz[0]) if sz and sz[0] else (float(sz[1]) * W / H if sz and sz[1] else 0.08)
        a = np.asarray(im, np.float32) / 255.0
        rgb, al = a[..., :3].copy(), a[..., 3].copy()
        if text or (np.ptp(rgb.reshape(-1, 3), axis=0).max() < 0.02 and al.min() < 0.5):  # ink given by coverage alone
            rgb[...] = np.asarray(ink, np.float32)
            own = False
        else:
            own = True
            if al.min() > 0.98:  # an opaque picture on white paper: the paper isn't ink
                al = np.clip((1.0 - rgb.min(-1)) * 4.0, 0, 1) if rgb.reshape(-1, 3).mean() > 0.6 else al
        yrs = float(np.clip(age, 0, 60))
        fade = float(np.exp(-yrs / 45.0))
        # colours fade toward grey; darks drift blue-green
        grey = rgb.mean(-1, keepdims=True)
        rgb = grey + (rgb - grey) * (0.35 + 0.65 * fade)
        darkness = np.clip(1.0 - grey * 1.6, 0, 1)
        rgb = rgb + darkness * (1 - fade) * (np.array([0.10, 0.2, 0.22], np.float32) - rgb) * 0.9
        rgb = rgb + (1 - fade) * 0.25 * (1 - rgb) * 0.6  # thinner ink: lighter
        px_per_mm = W / (width_m * 1000.0)
        blur = (0.12 + 0.03 * yrs) * px_per_mm  # mm of spread
        vis = al > 0.05  # where there's no ink, carry the ink's mean colour (a blur would pull in the paper)
        if vis.any() and not vis.all():
            rgb[~vis] = rgb[vis].mean(0)
        rgba = np.dstack([rgb, al])
        im2 = Image.fromarray(np.round(np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA")
        if blur > 0.3:
            r, g, b, al_ = im2.split()
            al_ = al_.filter(ImageFilter.GaussianBlur(blur))
            rgbb = Image.merge("RGB", (r, g, b)).filter(ImageFilter.GaussianBlur(blur * 0.6))
            im2 = Image.merge("RGBA", (*rgbb.split(), al_))
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp.png")
        im2.save(tmp)
        tmp.replace(out)
        (out.with_suffix(".own")).write_text("1" if own else "0")
    own = out.with_suffix(".own").read_text() == "1" if out.with_suffix(".own").exists() else not text
    new = {k: v for k, v in img.items() if k not in ("file", "id", "text", "name", "channel")}
    new["id"] = images.ingest(out)
    return new, own


def _tattoos(spec, p, layer, ctx) -> None:
    for i, tt in enumerate(p["tattoos"]):
        what = f"skin tattoos[{i}]"
        if not (isinstance(tt, dict) and isinstance(tt.get("image"), dict)):
            raise SpecError(f"{what}: {{\"image\": {{a paint image: \"file\" | \"text\", \"at\", \"size\", ...}}, \"age\", \"opacity\", \"ink\"}}")
        bad = set(tt) - {"image", "age", "opacity", "ink", "mask"}
        if bad:
            raise SpecError(f"{what}: unknown keys {sorted(bad)} (have image, age, opacity, ink, mask)")
        age = float(tt.get("age", 2.0))
        ink = _hex(tt.get("ink", "#1c2026"))
        img, own = tattoo_image(tt["image"], age, ink)
        op = float(tt.get("opacity", 0.9)) * (0.6 + 0.4 * float(np.exp(-age / 30.0)))
        # ink lies in the dermis: it multiplies into the skin's own colour; melanin above it mutes it on dark skin
        op *= 1.0 - 0.35 * p["tone"]["melanin"]
        layer(f"tattoo{i}", tt.get("mask"), color="image", image=img, mix="multiply", opacity=op)


def reference() -> str:
    # (C456) the docstring this quotes stayed in skin_features.py when the file was split: a bare __doc__ here is this
    # module's one line, and the tool's text was an IndexError. Its last paragraph there ("Where the code is") is for
    # whoever edits the package, not for the tool's reader.
    return skin_features.__doc__.split("\n\n", 1)[1].split("\n\nWhere the code is", 1)[0].strip()
