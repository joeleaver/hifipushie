"""The stack in use: apply, re-baked on the export's head, check, layers, only, edit, even_out. Part of the skin's layer stack (skin_layers.py has the overview)."""
from __future__ import annotations

import copy
import json

import numpy as np

from . import skin_layers
from . import skin_project as sp
from . import skin_project_atlas, skin_project_detail
from . import skin_layers_shade
from .skin_layers_decompose import _multiplier, decompose
from .skin_layers_shade import crease_tint

def apply(name: str, out: str | None = None, note: str = "", freckles: bool = True, log=print, lips: str = "texels") -> dict:
    """decompose() + each map stored as an image + spec["skin"]["stack"] saved (on `out`, a copy with the references,
    or on `name`). The stack then IS the head's skin colour (skin layers "skin:stack_*"): the procedural zones and lip
    colours under it are covered on the head, the fine generators (pores, freckle dots, hairs, the lid rims) lie over
    it. The files (one PNG a layer, the provenance, the recomposition, report) go to <model>/skin_layers/."""
    from pathlib import Path
    from PIL import Image
    from . import images, likeness_texture as lt, store
    from . import blockin_models
    spec = copy.deepcopy(store.load(name))
    r = decompose(name, spec, log=log, lips=lips)
    at = r["at"]
    dst = out or name
    d = store._dir(dst) / "skin_layers"
    d.mkdir(parents=True, exist_ok=True)
    H, W = at["shape"]
    valid = skin_project_atlas.image(at, np.ones(len(at["ii"]), bool), False)
    fade = np.clip(skin_project_atlas.interp(at, at["fade"]), 0, 1)
    # every map fades out toward the head island's own border in the atlas (where the body's mesh takes over): at the raw
    # fade the stack stopped on the island's ragged edge, a soft band and a jagged line across the neck
    from scipy import ndimage as _nd
    dist_mm = _nd.distance_transform_edt(valid)[at["ii"], at["jj"]] * at["mm"]
    edge = np.clip(dist_mm / skin_layers.COVER_EDGE_MM, 0, 1)
    fade = fade * edge * edge * (3 - 2 * edge)
    # ... and the fade itself softened: per vertex it stepped ring by ring (a ragged colour edge across the neck)
    fade = np.clip(skin_project_atlas._blur(at, fade, None, skin_layers.COVER_SOFT_MM), 0, 1)

    def save_rgb(lin_or_mult, fname, alpha=None, srgb=True):
        a = np.zeros((H, W, 4), np.uint8)
        v = sp._srgb(lin_or_mult) if srgb else lin_or_mult
        a[..., :3] = skin_project_detail._bleed(skin_project_atlas.image(at, (np.clip(v, 0, 1) * 255 + 0.5).astype(np.uint8)), valid)
        a[..., 3] = skin_project_detail._bleed(skin_project_atlas.image(at, ((fade if alpha is None else alpha) * 255).astype(np.uint8)), valid)
        Image.fromarray(a, "RGBA").save(d / fname)
        return images.ingest(d / fname)
    layers_ = []
    for lname, l in r["layers"].items():
        if float(np.abs(l["od"]).max()) < 0.01:
            continue
        iid = save_rgb(_multiplier(l["od"]), f"{lname}.png")
        layers_.append({"name": lname, "image": iid, "opacity": skin_layers.OPACITY.get(lname, skin_layers.P0)})
    cov = save_rgb(np.ones((len(fade), 3)), "coverage.png")
    Image.fromarray(skin_project_atlas.image(at, r["provenance"])).save(d / "provenance.png")
    save_rgb(r["recomposed"], "recomposed.png")
    fr_id = save_rgb(np.repeat(r["freckles"][:, None], 3, 1), "freckles.png", alpha=np.ones(len(fade)), srgb=False)
    fine_id = save_rgb(np.repeat(r["fine"][:, None], 3, 1), "fine.png", alpha=np.ones(len(fade)), srgb=False)
    (d / "report.txt").write_text(r["text"])
    (d / "report.json").write_text(json.dumps({"residual": r["residual"], "ica": r["ica"], "axes": r["axes"].tolist(),
                                               "base": r["base"].tolist()}, indent=1))
    box = [round(float(x), 6) for x in at["box"]]
    occ_id = save_rgb(skin_layers_shade.occlusion(spec, at, "still"), "occlusion.png", alpha=np.ones(len(fade)))
    occ_lid_id = save_rgb(skin_layers_shade.occlusion(spec, at, "lid"), "occlusion_lid.png", alpha=np.ones(len(fade)))
    cm = skin_layers_shade.crease_map(spec, at)
    cr_id = save_rgb(np.tile(crease_tint(spec, at), (len(cm), 1)), "crease.png", alpha=cm) if cm.max() > 0 else None
    spec["skin"]["stack"] = {"box": box, "base": [round(float(x), 4) for x in sp._srgb(r["base"])], "coverage": cov, "layers": layers_,
                             "freckles": fr_id, "fine": fine_id, "occlusion": occ_id, "occlusion_lid": occ_lid_id, "occlusion_strength": skin_layers.OCC_STRENGTH,
                             **({"crease": cr_id, "crease_strength": skin_layers.CREASE_STRENGTH} if cr_id else {}),
                             "head": lt.head_key(spec["base"]), "version": skin_layers.VERSION}
    notes = []
    sk = spec["skin"]
    if freckles:   # the freckle GENERATOR confined to the density map (dots are ours; where and how many is the picture's)
        ft = dict(sk.get("features") or {})
        dens = float(np.mean(r["freckles"][skin_project_detail._plain(at) & r["meas"]] > 0.5))
        if dens > 0.03:
            ft["freckles"] = {"amount": round(min(0.3 + 2.0 * dens, 1.2), 3), "mask": [{"image": {"id": fr_id, "wrap": "uv", "box": box, "channel": "luma"}}]}
            notes.append(f"  features.freckles: amount {ft['freckles']['amount']} inside the density map ({100 * dens:.0f} % of the plain skin over half density)")
        else:
            ft.pop("freckles", None)
            notes.append("  features.freckles: none (the fine melanin band is even)")
        sk["features"] = ft
    if freckles:   # blemishes the same way: our generator, inside the picture's own density map, as strong as its p99
        ft = dict(sk.get("features") or {})
        ab = float(np.clip((r["blemish_p99"] - skin_layers.BLEMISH_FLOOR) / (2 * skin_layers.BLEMISH_REF - 2 * skin_layers.BLEMISH_FLOOR + 1e-9) * 1.5, 0, 1))
        if ab > 0.1:
            bl_id = save_rgb(np.repeat(r["blemishes"][:, None], 3, 1), "blemishes.png", alpha=np.ones(len(fade)), srgb=False)
            ft["blemishes"] = {"amount": round(0.6 * ab, 3), "size": 0.0012, "mask": [{"image": {"id": bl_id, "wrap": "uv", "box": box, "channel": "luma"}}]}
            notes.append(f"  features.blemishes: amount {ft['blemishes']['amount']} inside the density map (p99 {r['blemish_p99']:.4f})")
        else:
            ft.pop("blemishes", None)
        sk["features"] = ft
    h = dict(sk.get("hair") or {})
    bd = r["layers"].get("beard")
    if bd is not None and not h.get("stubble"):   # a measured beard SHADOW without hairs read as a blue-grey smear (the
        # older test head man's stubble): our stubble's hairs where the beard layer is, its own shadow off (the layer is it)
        sup_ = bd["amount"]["d"] > 0.05
        md = float(np.mean(bd["amount"]["d"][sup_])) if sup_.any() else 0.0
        if md > 0.12:
            h["stubble"] = {"amount": round(float(np.clip(md / 0.35, 0.3, 1.0)), 2), "style": "short"}
            notes.append(f"  hair.stubble: amount {h['stubble']['amount']} (the beard layer's mean {md:.2f} e-folds: hairs over its shadow)")
    if h.get("stubble"):   # one, not both: the beard layer is the shadow; our stubble keeps its hairs, not its shadow
        st = h["stubble"] if isinstance(h["stubble"], dict) else {"amount": float(h["stubble"])}
        h["stubble"] = {**st, "shadow": 0.0}
        sk["hair"] = h
        notes.append("  hair.stubble.shadow -> 0: the beard LAYER is the shadow now (our stubble keeps its hair dots)")
    if dst != name:
        rj = copy.deepcopy(blockin_models._refs(name))
        if rj.get("blockin"):
            rj["blockin"] = {**rj["blockin"], "root": dst}
        blockin_models._save(dst, spec, note or f"skin layer stack from {name}'s atlas", rj)
    else:
        store.save(dst, spec, note or "skin layer stack from the atlas", checked=False)
    r["text"] += "\n" + "\n".join([f"  saved: {dst} skin.stack ({len(layers_)} layers; files in {d})"] + notes)
    r["dir"] = str(d)
    return r


def stack_on_head(spec: dict, log: list) -> dict:
    """(Garrett s9 / Tess rc2, coordinator: "the export's eyes read smaller and hooded, a dark band over the upper lids")
    The stack's GEOMETRY-MEASURED layers (occlusion, occlusion_lid, crease: the blink map and the lid shading) belong to
    the head they were baked on (stack.head). When the export's head differs (asset_gates.approved_head swapped in the approved
    head; the stack was measured on a lid_fold head), they are re-baked on the export's head: occlusion / occlusion_lid by
    occlusion(), the crease by crease_map() (a head without lid_fold has no crease line: dropped). The colour layers stay."""
    import tempfile
    from pathlib import Path
    from PIL import Image
    from . import images, likeness_texture as lt
    sk = spec.get("skin") or {}
    st = sk.get("stack")
    if not st or not any(st.get(k) for k in ("occlusion", "occlusion_lid", "crease")):
        return spec
    key = lt.head_key(spec["base"])
    if st.get("head") == key:
        return spec
    at = skin_project_atlas.atlas(spec["base"])
    H, W = at["shape"]
    valid = skin_project_atlas.image(at, np.ones(len(at["ii"]), bool), False)
    d = Path(tempfile.mkdtemp(prefix="hp_stack_"))

    def save(v, fname, alpha=None):
        a = np.zeros((H, W, 4), np.uint8)
        a[..., :3] = skin_project_detail._bleed(skin_project_atlas.image(at, (np.clip(sp._srgb(v), 0, 1) * 255 + 0.5).astype(np.uint8)), valid)
        al = np.ones(len(at["ii"])) if alpha is None else alpha
        a[..., 3] = skin_project_detail._bleed(skin_project_atlas.image(at, (np.clip(al, 0, 1) * 255).astype(np.uint8)), valid)
        Image.fromarray(a, "RGBA").save(d / fname)
        return images.ingest(d / fname)
    st = dict(st)
    done = []
    if st.get("occlusion"):
        st["occlusion"] = save(skin_layers_shade.occlusion(spec, at, "still"), "occlusion.png"); done.append("occlusion")
    if st.get("occlusion_lid"):
        st["occlusion_lid"] = save(skin_layers_shade.occlusion(spec, at, "lid"), "occlusion_lid.png"); done.append("occlusion_lid")
    if st.get("crease"):
        cm = skin_layers_shade.crease_map(spec, at)
        if cm.max() > 0:
            st["crease"] = save(np.tile(crease_tint(spec, at), (len(cm), 1)), "crease.png", alpha=cm); done.append("crease")
        else:
            st.pop("crease", None); st.pop("crease_strength", None); done.append("crease DROPPED (no lid_fold on this head)")
    log.append(f"skin stack: measured on head {st.get('head')}, exported on {key}: {', '.join(done)} re-baked on the export's head")
    st["head"] = key
    return {**spec, "skin": {**sk, "stack": st}}


def check(st) -> dict | None:
    from .spec import SpecError
    if st in (None, False, {}):
        return None
    if not isinstance(st, dict) or set(st) - {"box", "base", "coverage", "layers", "freckles", "fine", "fine_strength", "head", "version", "opacity", "base_opacity", "occlusion", "occlusion_lid", "occlusion_strength", "crease", "crease_strength"} or not isinstance(st.get("layers"), list):
        raise SpecError("skin stack: {box, base, coverage, layers: [{name, image, opacity}]} (made by skin_layers_stack.apply / skin_from_reference)")
    return st


def layers(spec: dict, st: dict, out: dict, part: str) -> None:
    """spec["skin"]["stack"] as paint layers (skin_features_build.build calls it FIRST: over the skin's broad colour layers,
    under every fine generator): the base colour over the head, then one multiply layer a map."""
    if not st or not st.get("layers"):
        return
    box = [float(x) for x in st["box"]]
    k = float(st.get("opacity", 1.0))
    if k <= 0:
        return
    img = lambda iid: {"id": iid, "wrap": "uv", "box": box, "channel": "alpha"}  # noqa: E731
    if float(st.get("base_opacity", 1.0)) > 0:
        out["skin:stack_base"] = {"part": part, "color": [float(x) for x in st["base"]], "opacity": round(k * float(st.get("base_opacity", 1.0)), 4), "image": img(st["coverage"])}
    for l in st["layers"]:
        op = float(l.get("opacity", skin_layers.P0)) * k
        if op > 0:
            out[f"skin:stack_{l['name']}"] = {"part": part, "color": "image", "mix": "multiply", "opacity": round(min(op, 1.0), 4), "image": img(l["image"])}
    if any(l["name"] == "parting" and float(l.get("opacity", skin_layers.P0)) > 0 for l in st["layers"]):
        # the seam's own surfaces (the lips' inner faces in a hairline gap, outside the head's atlas, so no stack layer
        # reaches them): dark in world space, a thin deep band along the closed lips' line (a pale jagged line showed
        # through a hand-edited mouth's seam)
        out["skin:stack_seam"] = {"part": part, "color": [0.22, 0.12, 0.12], "opacity": round(0.85 * k, 4),
                                  "mask": [{"spot": {"at": ["lm_mouth_corner.R", "lm_lip_seam", "lm_mouth_corner.L"],
                                                     "radius": [0.0016, 0.006, 0.0018], "soft": 0.6, "line": True}},
                                           # only the seam's own faces (they face up or down into the gap), never the lips'
                                           # front (a wide dark smudge on the lower lip)
                                           {"facing": [0, -1, 0], "range": [0.55, 0.25], "blend": "multiply"}]}
    # the pose's own lid close (base.head.pose lid_upper; a full blink = BLINK_POSE): the crease line and the lid's
    # occlusion fade with it (open = full, closed = clean); "_blink" lets the export bake them as their own map
    pose = (((spec.get("base") or {}).get("head") or {}).get("pose") or {})
    wb = float(np.clip(float(pose.get("lid_upper", 0.0) or 0.0) / skin_layers.BLINK_POSE, 0.0, 1.0))
    oc = float(st.get("occlusion_strength", skin_layers.OCC_STRENGTH)) * k
    if st.get("occlusion") and oc > 0:   # the baked occlusion (skin_layers_shade.occlusion): linear multiplier in the image
        out["skin:stack_occlusion"] = {"part": part, "color": "image", "mix": "multiply", "opacity": round(min(oc, 1.0), 4),
                                       "image": img(st["occlusion"])}
    if st.get("occlusion_lid") and oc * (1 - wb) > 0:
        out["skin:stack_occlusion_lid"] = {"part": part, "color": "image", "mix": "multiply", "_blink": True,
                                           "opacity": round(min(oc, 1.0) * (1 - wb), 4), "image": img(st["occlusion_lid"])}
    cs = float(st.get("crease_strength", skin_layers.CREASE_STRENGTH)) * k
    if st.get("crease") and cs * (1 - wb) > 0:   # the fold's crease line (skin_layers_shade.crease_map): its own strength
        out["skin:stack_crease"] = {"part": part, "color": "image", "mix": "multiply", "_blink": True,
                                    "opacity": round(min(cs, 1.0) * (1 - wb), 4), "image": img(st["crease"])}
    fs = float(st.get("fine_strength", 1.0)) * k
    if st.get("fine") and fs > 0:   # OUR fine texture (noise at two scales), as strong as the reference's fine band is there
        # PORE GRAIN: small dark speckles at the scale a photograph resolves pores (~0.4-0.5 mm, a few pixels at a face
        # close-up; the swatch pores are ~0.15 mm, sub-pixel there: a blind review read the stacked face as wax), and a
        # broad soft warm mottle; both as strong as the reference's fine band (the map) allows
        fm = {"image": {"id": st["fine"], "wrap": "uv", "box": box, "channel": "luma"}, "blend": "multiply"}
        out["skin:stack_fine0"] = {"part": part, "color": list(skin_layers.PORE_TINT), "mix": "multiply", "opacity": round(min(0.22 * fs, 1.0), 4),
                                   "mask": [{"noise": {"scale": skin_layers.PORE_SCALE, "range": [0.63, 0.72], "seed": 31}}]}   # (everywhere: the map kept it off the cheeks)
        out["skin:stack_fine1"] = {"part": part, "color": list(skin_layers.MOTTLE_TINT), "mix": "multiply", "opacity": round(min(0.6 * fs, 1.0), 4),
                                   "mask": [{"noise": {"scale": skin_layers.MOTTLE_SCALE, "range": [0.35, 0.85], "seed": 32}}, fm]}


# named edits: {layer: strength}, strength in units of the layer as measured (1 = as it is, 2 = twice the pigment, 0 = off)
def only(spec: dict, names=("lips",)) -> dict:
    """A copy whose stack lays ONLY these layers over the model's own skin (no stack base, no fine layer), and whose own
    description's groups that the layers replace are off (lips: our painted vermilion). A one-cause change."""
    from . import skin
    s = copy.deepcopy(spec)
    st = s["skin"]["stack"]
    st["base_opacity"] = 0.0
    st["fine_strength"] = 0.0
    for l in st["layers"]:
        if l["name"].rstrip("+") not in names and not (l["name"] == "parting" and "lips" in names):
            l["opacity"] = 0.0
    if "lips" in names:
        s["skin"]["only"] = [g for g in skin.GROUPS if g != "lips"]
    return s


def edit(spec: dict, *names, **strengths) -> dict:
    """A copy of the spec with layer STRENGTHS changed: named edits (EDITS: blush, pale, tan, older, no_stubble, rested,
    tired) and / or layer=strength (1 = as measured). One map each: the others are untouched. A strength over 1.25 lays
    the same map a second time (a layer's stored multiplier is exact at opacity P0 and tops out at 1.25 x)."""
    s = copy.deepcopy(spec)
    want = {}
    for nm in names:
        want.update(skin_layers.EDITS[nm])
    want.update(strengths)
    new = []
    for l in s["skin"]["stack"]["layers"]:
        if l["name"].endswith("+"):
            continue                                  # (an earlier edit's second pass)
        k = float(want.get(l["name"], 1.0))
        base_op = float(skin_layers.OPACITY.get(l["name"], skin_layers.P0))
        op = base_op * k
        new.append({**l, "opacity": round(min(op, 1.0), 4)})
        if op > 1.0:
            new.append({**l, "name": l["name"] + "+", "opacity": round(min(op - 1.0, 1.0), 4)})
    s["skin"]["stack"]["layers"] = new
    if "older" in names:   # ten years in the skin only: the description's own age cues (spots, thinner drier skin, lines) + the maps above
        s["skin"]["age"] = float(s["skin"].get("age", 30)) + 10.0
        ft = dict(s["skin"].get("features") or {})
        ft["age_spots"] = max(float(ft.get("age_spots", 0.0)) if isinstance(ft.get("age_spots", 0.0), (int, float)) else 0.0, 0.5)
        s["skin"]["features"] = ft
    return s


def even_out(spec: dict, centre, radius: float = 0.006, ring: tuple = (1.6, 2.6), amount: float = 0.7,
             layers=("pigment", "redness", "shade"), mirror: bool = True, log=print) -> dict:
    """A copy of the spec whose stack maps are EVENED round `centre` (neutral head coordinates, m; + its mirror across X):
    inside a soft sphere of `radius`, each named multiply map's darkening is pulled toward its own surroundings (the
    median over a ring of `ring` x radius), by `amount` (0 = unchanged, 1 = no darker than the ring). For the photo's
    shading that survived the de-light as pigment (a groove deeper in the picture than on the model: Tess's alar-cheek
    junction read as a brown / red blob in 3/4 views, r24). Lighter texels are kept (only excess darkness goes). New
    images are ingested; the layer entries point at them (the old ones are untouched)."""
    import tempfile
    from pathlib import Path
    from PIL import Image
    from . import images
    s = copy.deepcopy(spec)
    st = s["skin"]["stack"]
    at = skin_project_atlas.atlas(s["base"])
    ii, jj = at["ii"], at["jj"]
    Xn = skin_project_atlas.interp(at, at["neutral"])
    cs = [np.asarray(centre, float)] + ([np.asarray(centre, float) * [-1, 1, 1]] if mirror else [])
    w = np.zeros(len(ii))
    rings = []
    for c in cs:
        d = np.linalg.norm(Xn - c, axis=1)
        w = np.maximum(w, np.clip(1.0 - (d / radius) ** 2, 0, 1) ** 2)   # smooth to 0 at the radius
        rings.append((d > ring[0] * radius) & (d < ring[1] * radius))
    w = w * float(amount)
    side = [np.linalg.norm(Xn - c, axis=1) < ring[1] * radius for c in cs]
    new = []
    for l in st["layers"]:
        base_name = l["name"].rstrip("+")
        if base_name not in layers:
            new.append(l)
            continue
        a = np.asarray(Image.open(images.id_path(l["image"])).convert("RGBA"), float)
        v = a[ii, jj, :3]
        out = v.copy()
        for c, rg, sd in zip(cs, rings, side):
            ref = np.median(v[rg], 0)
            sel = sd & (w > 0)
            out[sel] = v[sel] + (np.maximum(v[sel], ref) - v[sel]) * w[sel, None]
        a[ii, jj, :3] = out
        p = Path(tempfile.mkdtemp()) / f"even_{base_name}.png"
        Image.fromarray(np.clip(a + 0.5, 0, 255).astype(np.uint8), "RGBA").save(p)
        iid = images.ingest(p)
        dv = (out - v).mean(1)
        log(f"  even_out {l['name']}: {int((w > 0.05).sum())} texels, mean lift {dv[w > 0.05].mean():+.4f}, max {dv.max():+.4f} -> {iid}")
        new.append({**l, "image": iid})
    st["layers"] = new
    return s
