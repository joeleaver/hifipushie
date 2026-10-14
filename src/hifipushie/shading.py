"""Engine-agnostic shading notes for an exported asset (Joe, 2026-10-14: "ideally it would return some generic
shader-building tips along with the model"): export_asset writes <asset>_shading.json (machine-readable) and
<asset>_shading.md (for a person) beside the GLB. Per material: the maps (file, channels, colour space, uv set, size,
texel density, meaning), the intended shading model as formulas (not node names), which glTF extensions carry what and
what a plain glTF viewer misses, and one or two lines per mainstream engine. Plus the face shapes (ARKit names,
couplings) and the LODs (files, triangles, switch distances).

The game-like EEVEE check (spikes/game_ready/game_eevee.py) builds its materials FROM this json, so the notes are tested
every export: if a render made by following them doesn't match the approved look, the notes are wrong."""
from __future__ import annotations

import json
from pathlib import Path

VERSION = 1
# a LOD's switch distance (m) for a human-sized character on a 1080p screen at ~60 deg vertical fov: where its share of
# LOD0's triangles still puts ~1 triangle per few pixels (screen height covered ~ 1.8 m * 1080 / (2 d tan 30))
LOD_DISTANCE = {1: 4.0, 2: 9.0, 3: 18.0}

ENGINES = {
    "skin": {"unity": "HDRP Lit, Material Type Subsurface Scattering + a Diffusion Profile from subsurface.mean_free_path_m; "
                      "URP: Lit + a wrap-lighting custom node (no SSS)",
             "unreal": "Subsurface Profile shading model (Mean Free Path Color = radius / max, Distance = max in cm)",
             "godot": "StandardMaterial3D with subsurf_scatter (strength ~0.3) + transmittance off; or a spatial shader with wrap"},
    "eye": {"unity": "HDRP Eye shader (Cornea + Iris) or Lit with Clear Coat", "unreal": "Eye shading model (or Default Lit + "
            "Clear Coat)", "godot": "StandardMaterial3D with clearcoat 1.0, clearcoat_roughness from the json"},
    "hair_cards": {"unity": "HDRP Hair shader (Kajiya-Kay / Marschner), alpha clip + alpha to mask; URP: Lit alpha clip",
                   "unreal": "Hair shading model on cards (Hair Cards), Masked blend, dither temporal AA",
                   "godot": "spatial shader: spikes/godot_hair/hair_cards.gdshader (two shifted lobes, aux texture)"},
    "lashes": {"unity": "Lit, alpha clip, two-sided", "unreal": "Default Lit, Masked, two-sided", "godot": "alpha scissor, cull disabled"},
    "cloth": {"unity": "HDRP Fabric (Cotton/Wool or Silk) / URP Lit", "unreal": "Cloth shading model (fuzz colour = base colour x 1.2)",
              "godot": "StandardMaterial3D with rim (0.3) for fuzz"},
    "standard": {"unity": "Lit (metallic workflow)", "unreal": "Default Lit", "godot": "StandardMaterial3D"},
}

GLTF_NOTES = {
    "KHR_materials_specular": "specular level in the alpha of the specular texture (0.5 = F0 0.04): plain viewers use 0.04 everywhere",
    "KHR_materials_clearcoat": "the tear film / skin oil lobe: viewers without it lose the eyes' catchlight sharpness",
    "KHR_materials_sheen": "skin / cloth sheen: viewers without it draw cloth a little flat",
    "KHR_materials_anisotropy": "hair cards' highlight along the strand (flow texture): viewers without it draw an isotropic highlight",
    "KHR_materials_transmission": "glass / clear parts",
}



# Where each term of a hair card's albedo lives (applied ONCE: the shader adds no shade of its own, "aux_shade": None).
# hair_cards.atlas bakes the clump depth and the value per strand into the colour; hair_cards.mesh puts the root
# ramp, the tip lift and the lock's tone into COLOR_0. The notes once had the shader multiply all three again from aux.
HAIR_ALBEDO_TERMS = {"clump_depth": "atlas", "strand_value": "atlas", "root_ramp": "COLOR_0", "tip_lift": "COLOR_0",
                     "lock_tone": "COLOR_0"}

def _kind(pn: str, r: dict, skin_part: str, eyes: str | None) -> str:
    if r.get("curves") or r.get("cards"):
        return "hair_cards"
    if r.get("lashes"):
        return "lashes"
    if r.get("cloth"):
        return "cloth"
    if pn == skin_part:
        return "skin"
    if eyes and pn == eyes:
        return "eye"
    return "standard"


def _map(path: str, key: str) -> dict:
    space = "sRGB" if key in ("basecolor", "blink") else "linear"
    meaning = {
        "basecolor": "albedo (RGB); for cards straight alpha = coverage in A",
        "normal": "tangent-space normal, OpenGL convention (+Y up), MikkTSpace tangents from the GLB",
        "orm": "R ambient occlusion, G roughness, B metallic",
        "roughness": "roughness alone (= orm G)", "metallic": "metallic alone (= orm B)", "ao": "ambient occlusion alone (= orm R)",
        "specular": "specular level (0.5 = F0 0.04)", "height": "16-bit height: 0.5 = the low-poly surface, +-height_range_m",
        "blink": "the blink-multiply map: lid crease line + the lid's share of occlusion, NOT in basecolor",
        "aux": "R root gradient (1 at the root), G a value per strand, B depth in the clump (0 deep), A alpha",
        "flow": "strand direction in tangent space (RG) + strength (B): KHR_materials_anisotropy's texture",
    }.get(key, key)
    size = None
    try:
        from PIL import Image
        with Image.open(path) as im:
            size = list(im.size)
    except Exception:
        pass
    return {"file": Path(path).name, "space": space, "uv": 0, "size": size, "meaning": meaning}


def notes(info: dict, aname: str, looks: dict | None = None, hair_look: dict | None = None,
          eyes_part: str | None = None) -> dict:
    """The shading json from the export's report (asset._export's info)."""
    skin = info.get("skin") or {}
    skin_part = skin.get("part", "body")
    mats = []
    for an, a in (info.get("atlases") or {}).items():
        pns = a.get("parts") or []
        groups: dict = {}
        for pn in pns:
            k = _kind(pn, info["parts"].get(pn, {}), skin_part, eyes_part)
            groups.setdefault(k, []).append(pn)
        for k, ps in groups.items():
            maps = {key: _map(p, key) for key, p in (a.get("maps") or {}).items() if key in (
                "basecolor", "normal", "orm", "specular", "blink", "aux", "flow")}
            if k != "skin":
                maps.pop("blink", None)
            m = {"name": f"{aname}_{an}" + ("" if len(groups) == 1 else f"_{k}"), "atlas": an, "parts": ps, "model": k,
                 "maps": maps, "texel_mm": {pn: info["parts"][pn].get("mm_per_texel") for pn in ps
                                            if info["parts"][pn].get("mm_per_texel")}, "formulas": [], "params": {},
                 "engines": ENGINES[k]}
            f = m["formulas"]
            if k == "skin":
                f += ["albedo = basecolor * lerp(1, blink, 1 - eyeBlink)   (eyeBlink = max of the eyeBlinkLeft / Right "
                      "morph weights; the open eye shows the crease line, a closed one does not)" if "blink" in maps else
                      "albedo = basecolor",
                      "roughness = orm.g (lips and nose oilier: already in the map); specular level 0.5 (F0 0.04)",
                      "diffuse: subsurface with per-channel mean free path subsurface.mean_free_path_m (red furthest); "
                      "without SSS: wrap lighting  max(0, (N.L + w) / (1 + w)), w = 0.35, tinted toward the blood red "
                      "(1.0, 0.55, 0.45) in the wrapped part",
                      "occlusion: orm.r multiplies ambient / indirect light only (the warm crease and lid occlusion are "
                      "already in basecolor and the blink map: do not multiply direct light by it)",
                      "micro detail: the tiling normal maps in skin.detail, laid by position at period_m, blended over the "
                      "baked normal (whiteout), faded out past ~1.5 m"]
                m["params"] = {"subsurface": skin.get("subsurface"), "detail": skin.get("detail"),
                               "detail_recipe": skin.get("detail_recipe"), "specular": skin.get("specular"),
                               "sheen": skin.get("sheen"), "ao_direct": 0.0}
            elif k == "eye":
                f += ["a wet cornea: clear coat 1.0 over the iris and sclera, coat roughness ~0.03 (the catchlight)",
                      "iris: basecolor as painted; optional parallax: offset the iris uv by the view vector x 0.3 mm "
                      "depth inside the limbus ring", "sclera: roughness ~0.25, no subsurface needed at game distance"]
                m["params"] = {"clearcoat": 1.0, "clearcoat_roughness": 0.03}
            elif k == "hair_cards":
                lk = hair_look or {}
                f += ["albedo = basecolor.rgb * COLOR_0.rgb (COLOR_0: root-to-tip ramp and a value per lock / card: "
                      "glTF says COLOR_0 multiplies; the atlas is lifted to carry it)",
                      "coverage: basecolor.a: alpha TEST at alphaCutoff (0.33) with dithering + temporal AA, or "
                      "alpha-to-coverage with MSAA; no sorting (cards write depth like opaque geometry); keep the alpha's "
                      "coverage in the mip chain (scale alpha per mip to the base level's coverage)",
                      "two-sided with ONE normal for both faces: do not flip the normal on back faces",
                      "shade: NONE in the shader. Each term is applied once, where it lives: the clump depth "
                      "(0.45 + 0.55 depth^0.8 between the gap and lit colours) and the value per strand are BAKED IN "
                      "THE ATLAS (basecolor); the root-to-tip ramp, the tip lift and the tone per lock / card are in "
                      "COLOR_0. Do not multiply aux.r / aux.g / aux.b into the albedo again (that darkened the cards "
                      "twice: front L* 13 against the strands' 26.7). aux is for what the atlas can't hold: the "
                      "specular shift jitter (aux.g), backscatter weighted to thin hair (aux.b), an engine's own "
                      "root / depth masks",
                      "specular: two Kajiya-Kay lobes along T' = normalize(T + shift N): lobe 1 white, power ~90, shift "
                      "+0.06 (toward the tip), strength 0.35; lobe 2 tinted by the albedo, power ~22, shift -0.10, strength "
                      "0.45; per-strand shift jitter 0.3 x (aux.g - 0.5)  (T = the bitangent of TANGENT: the atlas's v "
                      "runs root to tip)",
                      "diffuse: wrapped  max(0, (N.L + 0.45) / 1.45); keep ~0.55 of the shadow map (hair lets light through)",
                      "scalp: the cap carries the scalp chart; under it the skin's own scalp tint"]
                m["params"] = {"alpha_mode": "MASK", "alpha_cutoff": 0.33, "two_sided": True,
                               "albedo_terms": dict(HAIR_ALBEDO_TERMS), "aux_shade": None,
                               "look": {k_: lk.get(k_) for k_ in ("lit", "gap", "sheen", "gloss", "tip_alpha",
                                                                  "backscatter", "scatter", "root_dark", "sun")
                                        if lk.get(k_) is not None},
                               "game_terms": "tip_alpha (alpha falls over the last 30 % of a strand: already in the atlas), "
                                             "backscatter (a warm transmission from lights behind, weighted to thin hair: "
                                             "aux.b high), scatter (depth: aux.b low = darker, more saturated)"}
            elif k == "lashes":
                f += ["albedo = basecolor; alpha test at 0.5; two-sided; they ride the lids by the face shapes"]
                m["params"] = {"alpha_mode": "MASK", "two_sided": True}
            elif k == "cloth":
                f += ["albedo = basecolor (seams, topstitching, hems painted in); normal map carries seams and fine folds "
                      "(strength 1.0)", "sheen / fuzz: a rim term  fuzz = (1 - N.V)^4 x 0.25 x albedo luminance for knits "
                      "and brushed cotton; denim and twill: roughness 0.85, no sheen",
                      "two-sided: the inner shell is real geometry (open fronts, cuffs show their inside)"]
            else:
                f += ["metallic-roughness PBR: albedo = basecolor, roughness = orm.g, metallic = orm.b, AO = orm.r on "
                      "indirect light"]
            ext = set()
            for pn in ps:
                for e in (((looks or {}).get(pn) or {}).get("ext") or {}):
                    ext.add(e)
            if k == "hair_cards":
                ext |= {"KHR_materials_anisotropy", "KHR_materials_sheen"}
            ext.add("KHR_materials_specular")
            m["gltf"] = {e: GLTF_NOTES.get(e, "") for e in sorted(ext)}
            mats.append(m)
    fs = info.get("face_shapes") or {}
    lods = [{"lod": 0, "file": Path(info["glb"]).name, "triangles": info["triangles"], "switch_m": 0.0}]
    for L in info.get("lods") or []:
        lods.append({"lod": L["lod"], "file": Path(L["glb"]).name, "triangles": L["triangles"],
                     "switch_m": LOD_DISTANCE.get(L["lod"], 18.0 * 2 ** (L["lod"] - 3))})
    return {"version": VERSION, "asset": aname, "conventions": info.get("conventions"), "materials": mats,
            "face_shapes": {"names": fs.get("names"), "couplings": [
                "eyeBlinkLeft / eyeBlinkRight also fade the skin's blink map: albedo = basecolor * lerp(1, blink, 1 - eyeBlink)",
                *[f"{c}: set each frame to {v}" for c, v in (fs.get("correctives") or {}).items()]]} if fs else None,
            "twist": (info.get("rig") or {}).get("twist_recipe"),
            "lods": lods,
            "lod_rule": "switch by distance for a human-sized character on a 1080p, ~60 deg vertical fov screen; scale "
                        "the distances by (screen height / 1080) x (tan 30 deg / tan(fov / 2)). The LODs share LOD0's "
                        "skeleton, maps and face shapes"}


def markdown(n: dict) -> str:
    out = [f"# {n['asset']}: shading notes", "", "Engine-agnostic: formulas, not node names. Colour: sRGB maps are "
           "base colour / blink; everything else is linear. glTF axes: +Y up, +Z front, metres.", ""]
    for m in n["materials"]:
        out += [f"## {m['name']}  ({m['model']}; parts: {', '.join(m['parts'])})", "", "Maps:"]
        for k, v in m["maps"].items():
            out.append(f"- `{v['file']}` ({k}, {v['space']}, uv {v['uv']}, {v['size'][0]}x{v['size'][1]}" if v.get("size")
                       else f"- `{v['file']}` ({k}, {v['space']}, uv {v['uv']}")
            out[-1] += f"): {v['meaning']}"
        if m.get("texel_mm"):
            out.append("- texel size (mm): " + ", ".join(f"{p} {t}" for p, t in m["texel_mm"].items()))
        out += ["", "Shading:"] + [f"- {f}" for f in m["formulas"]]
        if m["gltf"]:
            out += ["", "glTF extensions:"] + [f"- {e}: {t}" for e, t in m["gltf"].items()]
        out += ["", "Engines:"] + [f"- {e}: {t}" for e, t in m["engines"].items()] + [""]
    if n.get("face_shapes"):
        out += ["## Face shapes", "", "ARKit names (glTF morph targets, mesh.extras.targetNames): "
                + ", ".join(n["face_shapes"]["names"] or []), ""] + [f"- {c}" for c in n["face_shapes"]["couplings"]] + [""]
    if n.get("twist"):
        out += ["## Twist joints", "", n["twist"] if isinstance(n["twist"], str) else json.dumps(n["twist"]), ""]
    out += ["## LODs", "", n["lod_rule"], ""] + [f"- LOD{L['lod']}: `{L['file']}`, {L['triangles']} triangles, from "
                                                 f"{L['switch_m']:g} m" for L in n["lods"]]
    return "\n".join(out) + "\n"


def write(info: dict, out_dir: Path, aname: str, **kw) -> tuple[Path, Path]:
    n = notes(info, aname, **kw)
    pj, pm = Path(out_dir) / f"{aname}_shading.json", Path(out_dir) / f"{aname}_shading.md"
    pj.write_text(json.dumps(n, indent=1, default=str))
    pm.write_text(markdown(n))
    return pj, pm
