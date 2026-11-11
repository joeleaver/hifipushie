"""Clutter kit: the small solids a terrain is scattered with by the ten thousand (boulders, water-worn river rocks,
cobble patches, bank slabs, driftwood), as game assets in a style.

How prop artists make them: sculpt a HIGH form, decimate to a few LODs, bake the high form's normals / occlusion /
colour onto the low ones, scatter with yaw / scale / squash so three or four shapes never read as clones. Here the high
form is a signed distance (as the terrain's rock is), so the rock speaks the cliffs' language: a block bounded by two
JOINT families and BEDDING planes (terrain_stack / terrain_blocks), corners chipped off, soft beds set back, weathered
round by a smooth max (`bevel`) or water-worn toward an ellipsoid (`round`). Driftwood is crooked round cones with
stubs. A preset (`clutter_presets/<kind>.json`) says what the thing is; a style sheet (`clutter_styles/<style>.json`)
says how that style shapes and paints it (blobby = pebbles, anime = crisp planes + painted bands, cartoon = few big
facets + a dark edge, pixar = soft sculpt + gradient); colours start from the terrain's rock colour turned by the
terrain style's saturation / value.

Each variant (a seed) is meshed once, decimated per LOD (pyfqmr), put back on the field; ONE atlas per asset holds
every variant: six box-projected charts a variant (a texel = the first surface a ray along that axis meets, so every
LOD reads the same picture by POSITION and nothing is unwrapped), baked from the field itself + a bake-only micro
relief: albedo, tangent normal (TANGENT written: the chart's own axes), occlusion / roughness. Files and json follow
the plant contract (veg_export.CONTRACT; `<stem>_seasons.json` with grade "clutter").

Metres, Z up; the asset is authored at scale 1 = 1 m largest plan dimension, pivot at the ground line (`sink_m` of it
is below).

Where the code is (split by responsibility, C423): this module holds EVERY constant of the family, the presets,
styles and `resolve`. clutter_forms: Stone, Wood, Bush. clutter_solid: cells, spray tile, bush cards, `Solid`.
clutter_mesh: meshing, checks, silhouettes, charts, LODs. clutter_bake: paint, micro relief, `bake_variant`.
clutter_build: `build`. clutter_export: the GLB writer, litter, `export`. clutter_kit: `look`, the manifest, `kit`."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
ROCK_SRGB = [0.36, 0.34, 0.31]  # terrain_rock.base_colour's grey rock: the reference a style turns
WOOD_SRGB = [0.44, 0.41, 0.36]   # weathered, barkless wood (silver grey)

FORM = {  # a rock's form; ranges are drawn per variant
    "aspect": [[0.6, 0.85], [0.42, 0.62]],  # mid / long and short / long axis (long = 1: the largest plan dimension)
    "faces": [6, 9],          # major faces, at oblique angles all round
    "jitter": 16.0,           # deg: how far each face's direction strays from an even spread
    "face_in": [0.7, 0.95],   # each face's distance from the middle, as a share of the ellipsoid's reach that way
    "bedded": 0.7,            # probability of a pair of off-parallel bedding faces (a flat-ish top and underside)
    "tilt": 8.0,              # deg: how far off parallel they are
    "dip": [5.0, 35.0],       # deg: the bedding's tilt (a fallen block's beds are never level)
    "tumble": 14.0,           # deg: the whole block tipped
    "chips": [4, 8],          # corners / edges broken off (planes), of which
    "broken": [1, 2],         # are deep breaks
    "break": [0.2, 0.42],     # a deep break's depth, as a share of the block's reach in that direction
    "chip": [0.04, 0.14],     # a shallow chip's
    "bevel": 0.06,            # m: arrises rounded (weathering)
    "top_round": 1.5,         # the top's arrises rounded this much more than the foot's (x bevel, added)
    "taper": 0.22,            # wider at the base than at the top (0 = a prism)
    "round": 0.0,             # 0..1: toward an ellipsoid (water-worn)
    "bend": 0.0,              # a bean: the long axis bowed, x the height
    "dent": 0.0,              # probability of one soft dent
    "split": 0.0,             # probability of a crack through the block
    "split_gap": [0.012, 0.03],  # m: its half width
    "beds": [0, 2],           # partings along the bedding (thin grooves round part of the block)
    "bed_set": [0.008, 0.02],  # m: their depth
    "bed_thick": [0.006, 0.016],  # m: their half width
    "lumps": 0.02,            # m: slow unevenness of the faces
    "lump_size": 0.35,        # m
    "sink": 0.26,             # share of the height below the ground line (the mass sits IN the ground)
    "lean": 0.0,              # probability of a second, smaller block leaning on the first
    "cluster": None,          # {"count": [7, 13], "stone": [0.1, 0.26], "pile": 0.3}: many small stones as one asset
}
PAINT = {  # how the surface is painted (albedo multipliers round 1) and what relief only the maps carry
    "tone": 0.1, "tone_size": 0.25,   # slow tone patches
    "face_tone": 0.06,                # each joint / chip face its own tone
    "speckle": 0.05,                  # mineral grain (per texel-ish)
    "edge_light": 0.12,               # worn arrises paler (convex)
    "cavity": 0.25,                   # cracks and hollows darker (concave)
    "ink": 0.0, "ink_width": 0.012,   # a dark line along arrises (cartoon)
    "bands": 0.0, "band_thick": [0.03, 0.12], "band_tones": [-0.6, 0.2, 0.7, -0.25],  # painted strata along the bedding
    "gradient": 0.0,                  # lighter top, darker foot (0..1)
    "top_light": 0.0,                 # up-facing faces lighter (a clear top plane)
    "foot": 0.3, "foot_height": 0.1,  # the band above the ground line darker (damp, soil-stained): m at 1 m across
    "top": 0.25, "top_color": [0.5, 0.52, 0.36], "top_size": 0.12,  # lichen / moss on up-facing rock
    "lichen": 0.35, "lichen_size": 0.13,  # crusts: round patches in clusters, on tops and on one side (the weather side)
    "lichen_colors": [[0.5, 0.53, 0.45], [0.56, 0.57, 0.5], [0.62, 0.55, 0.3], [0.6, 0.61, 0.56], [0.47, 0.5, 0.44]],  # grey-greens, one ochre, pale
    "streaks": 0.2, "streak_width": 0.035,  # darker rain streaks running down steep faces from the top
    "foot_color": [0.2, 0.2, 0.12], "foot_tint": 0.35,  # the foot band stained toward soil / algae (with `foot`)
    "minerals": [[1.0, 1.0, 1.0], [1.05, 1.0, 0.94], [0.96, 0.99, 1.03], [1.03, 0.98, 0.92]],  # each variant's own rock: x the colour
    "moss": 0.0, "moss_color": [0.25, 0.36, 0.14], "moss_band": [0.15, 0.6],  # a mossy band (share of height)
    "moss_up": 0.0, "moss_vary": None,  # moss only on faces turned up that far (0 = sides too); x moss per variant
    "ao": 0.6,                        # occlusion strength (also baked half into the albedo's foot)
    "tone_range": [0.62, 1.45],       # the albedo's linear luminance p5 .. p95 over its mean (see tone_range): a cliff's rock
    "roughness": 0.9,
    "grain": 0.0015, "grain_size": 0.02,     # m: bake-only relief
    "cracks": 0.004, "crack_size": 0.3,
    "laminae": 0.0, "lamina": 0.012,
    "pits": 0.0,
    "normals": 30.0,                  # deg: LOD faces meeting sharper than this keep their own normals (0 = all smooth)
}
WOOD = {
    "pieces": [1, 1],          # logs in the asset (a jam: several)
    "length": [0.85, 1.0],     # of the main piece (x = 1)
    "radius": [0.075, 0.105],  # at the butt
    "taper": [0.45, 0.8],      # tip radius / butt radius
    "crook": 0.05,             # sideways wander of the axis, x length
    "stubs": [1, 4],           # broken branch stubs
    "stub": [0.05, 0.16],      # their length
    "fork": 0.3,               # probability the piece forks (a branch)
    "roots": [0, 0],           # root stubs fanning from the butt (a root plate)
    "broken": 0.6,             # how jagged the broken ends are (0 = sawn)
    "bevel": 0.012,
    "lumps": 0.006, "lump_size": 0.12,
    "sink": 0.18,
    "pile": 0.5,               # a jam: how far pieces lie across each other (0 = parallel)
}
WOOD_PAINT = {
    "tone": 0.12, "tone_size": 0.2, "streak": 0.2, "streak_size": [0.25, 0.012], "speckle": 0.03,
    "edge_light": 0.1, "cavity": 0.3, "ink": 0.0, "ink_width": 0.008, "gradient": 0.1, "ao": 0.6, "roughness": 0.85,
    "grooves": 0.003, "groove_size": 0.012, "cracks": 0.003, "crack_size": 0.2, "normals": 40.0,
    "top": 0.0, "top_color": [0.5, 0.52, 0.36], "top_size": 0.1, "moss": 0.0, "moss_color": [0.25, 0.36, 0.14],
    "moss_band": [0.0, 0.5], "top_light": 0.0, "foot": 0.25, "foot_height": 0.03,
    "lichen": 0.1, "lichen_size": 0.04, "lichen_colors": [[0.62, 0.65, 0.56], [0.72, 0.62, 0.3]], "streaks": 0.0, "streak_width": 0.03,
    "foot_color": [0.2, 0.2, 0.12], "foot_tint": 0.3, "minerals": [[1.0, 1.0, 1.0], [1.06, 1.0, 0.92], [0.94, 0.98, 1.04], [1.04, 0.97, 0.9]],
    "bark": 0.35, "bark_color": [0.2, 0.14, 0.09], "bark_size": 0.18,   # patches of bark still on (dark, rough, proud)
    "bleach": 0.25,           # sun-bleached paler on top
}
BUSH = {  # a clutter bush: a lumpy leafy dome (closed, opaque) + leaf sprays on alpha cards breaking its outline
    "open": True,             # an OPEN bush made from a grown shrub (clutter_bush: stems + spray cards -> a share of them -> crossed
                              # cards); False = closed leafy lumps standing on the ground (the blobby / cartoon way)
    "height": 0.75,           # an open bush's height / width
    "stems": 6, "stem_angle": 28.0,  # the shrub's stems from its stool and how far they lean out (deg)
    "clumps": [4, 6],         # closed lumps (when not open): separate, of different sizes, each on its own stem
    "aspect": [[0.8, 1.0], [0.6, 0.8]],  # depth / width and height / width of the dome
    "lobes": [3, 6],          # lobes round the main dome
    "lobe": [0.2, 0.3],       # their radius, x the width
    "lobe_out": [0.5, 0.85],  # how far out from the middle they sit (1 = at the dome's edge)
    "join": 0.1,              # m: how softly lobes run together (small = distinct clumps)
    "lumps": 0.03, "lump_size": 0.22,
    "cards": [36, 42],        # leaf sprays standing out of the dome at LOD 0 (0 = none: a closed style)
    "card": [0.3, 0.46],      # their length, m
    "card_out": 0.58,          # the share of a spray standing out past the dome's surface
    "card_up": 0.35,          # how far sprays turn upward from straight out
    "cards_lod": [1.0, 0.5, 0.2],  # the share of the sprays each LOD keeps (kept ones drawn larger)
    "sink": 0.0,
}
BUSH_PAINT = {
    "tone": 0.1, "tone_size": 0.3, "face_tone": 0.1, "speckle": 0.0, "edge_light": 0.1, "cavity": 0.35, "ink": 0.0, "ink_width": 0.02,
    "gradient": 0.3, "top_light": 0.15, "foot": 0.12, "foot_height": 0.1, "ao": 0.45, "roughness": 0.96, "normals": 0.0,
    "top": 0.0, "top_color": [0.5, 0.52, 0.36], "top_size": 0.1, "moss": 0.0, "moss_color": [0.25, 0.36, 0.14], "moss_band": [0.0, 0.5],
    "lichen": 0.0, "lichen_size": 0.05, "lichen_colors": [[0.6, 0.6, 0.5]], "streaks": 0.0, "streak_width": 0.03, "foot_color": [0.12, 0.14, 0.08],
    "foot_tint": 0.0, "minerals": [[1.0, 1.0, 1.0], [1.06, 1.02, 0.9], [0.92, 1.0, 1.0], [1.0, 0.95, 0.85]],
    "leaf_size": 0.04,        # m: the painted leaves on the dome (cells); 0 = none (a flat colour)
    "leaf_tone": 0.25,        # each leaf's own tone
    "leaf_gap": 0.42,         # how dark the gaps between leaves are
    "leaf_bump": 0.004,       # m: each leaf a small dome in the normal map
    "steps": 0,               # tones cut into this many flat steps (painted look); 0 = continuous
    "flowers": 0.25, "flower_color": [0.95, 0.8, 0.15], "flower_size": 0.014,  # in the spring picture
    "spray": {"leaves": [16, 22], "leaf": [0.045, 0.068], "round": 0.4, "tones": 0.28, "outline": 0.0, "midrib": 0.2},  # a card's picture
}
LITTER = {  # a debris patch: fallen leaves, twigs and bits lying on the ground, as one alpha card (a decal with a mesh)
    "leaves": [70, 110],      # in the summer picture (autumn x `autumn`, winter x `winter`)
    "leaf": [0.05, 0.085],    # m: a leaf's length at 1 m across
    "round": 0.55,            # width / length
    "lobed": 0.0,             # 0..1: how deeply lobed (oak)
    "twigs": [5, 10], "twig": [0.12, 0.3],
    "bits": [20, 40],         # bark and stone crumbs
    "tones": 0.3,             # each leaf's own tone
    "steps": 0,               # tones cut into steps (painted)
    "outline": 0.0,           # a dark line round each leaf (x the tile)
    "shadow": 0.45,           # each leaf darkens what lies under its edge
    "autumn": 1.7, "winter": 0.8, "spring": 0.7,
    "colors": {"summer": [[0.36, 0.27, 0.16], [0.42, 0.33, 0.2], [0.3, 0.24, 0.15]],
               "autumn": [[0.72, 0.5, 0.14], [0.66, 0.3, 0.1], [0.78, 0.62, 0.2], [0.5, 0.3, 0.14]],
               "winter": [[0.24, 0.18, 0.12], [0.3, 0.23, 0.15], [0.2, 0.16, 0.12]],
               "spring": [[0.3, 0.23, 0.15], [0.36, 0.28, 0.17], [0.38, 0.44, 0.2]]},
    "twig_color": [0.22, 0.17, 0.12],
    "dome": 0.02,             # m: the patch's middle lifted (it lies over the ground's small bumps)
    "sink": 0.0,
}
LEAF_SRGB = [0.26, 0.36, 0.17]  # scrub (sage / gorse green)
LEAF_SEASONS = {"spring": {"mix": [0.42, 0.6, 0.2], "amount": 0.35, "flowers": 1.0}, "summer": {},
                "autumn": {"mix": [0.5, 0.44, 0.2], "amount": 0.3}, "winter": {"mix": [0.27, 0.3, 0.22], "amount": 0.5}}
LODS = {"bush": [170, 80, 40], "rock": [300, 100, 44], "cluster": [360, 120, 40], "wood": [220, 80, 24], "jam": [520, 170, 56]}
LOD_IOU = 0.9  # a LOD's outline against LOD 0's, mean of 8 directions: under it a single stone's LOD is its hull
LOD_SWITCH = [14.0, 40.0, 130.0]  # m x the instance's scale: LOD 1 from, LOD 2 from, gone at (fade over the last fifth)
ATLAS = 1024


# ---------------------------------------------------------------------------------------------------------- specs
def presets() -> list:
    return sorted(p.stem for p in (HERE / "clutter_presets").glob("*.json"))


def styles() -> list:
    return ["realistic"] + sorted(p.stem for p in (HERE / "clutter_styles").glob("*.json") if p.stem != "realistic")


def _merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def style_sheet(style) -> dict:
    """A style's clutter sheet (name or {"sheet": name, ...overrides})."""
    over = {}
    if isinstance(style, dict):
        over = {k: v for k, v in style.items() if k != "sheet"}
        style = style.get("sheet", "realistic")
    style = style or "realistic"
    p = HERE / "clutter_styles" / f"{style}.json"
    if not p.exists():
        raise ValueError(f"clutter style {style!r} unknown ({', '.join(styles())})")
    st = _merge(json.loads(p.read_text()), over)
    st["name"] = style
    return st


def _layered(layers, variant):
    """A form from its layers: the preset's, a variant's own (proportions), the style's, the style's multipliers, the
    spec's. The style comes after the variant: a pebble style rounds every variant, whatever its proportions."""
    pre, st_form, st_scale, own = layers
    form = _merge(_merge(_merge(pre, variant), st_form), own)
    for k, x in (st_scale or {}).items():
        if k in form and form[k] is not None:
            form[k] = (np.asarray(form[k], float) * x).tolist() if isinstance(form[k], list) else form[k] * x
    return form


def resolve(spec: dict) -> dict:
    """A clutter spec with its preset under it and its style's numbers laid over the form and paint:
    {"kind": preset, "style": name | {...}, "seed", "variants", "form": {...}, "paint": {...}, "color": sRGB,
    "lods": [triangles...], "atlas": px, "moss", "wet"}. Unknown keys are refused."""
    kind = spec.get("kind", "boulder")
    p = HERE / "clutter_presets" / f"{kind}.json"
    if not p.exists():
        raise ValueError(f"clutter kind {kind!r} unknown ({', '.join(presets())})")
    pre = json.loads(p.read_text())
    st = style_sheet(spec.get("style"))
    mat = pre.get("material", "rock")
    base_form, base_paint = ((WOOD, WOOD_PAINT) if mat == "wood" else (BUSH, BUSH_PAINT) if mat == "leaf" else (LITTER, {}) if mat == "litter"
                             else (FORM, PAINT))
    S = st.get(mat) or {}
    layers = (_merge(base_form, pre.get("form")), S.get("form"), S.get("scale"), spec.get("form"))
    form = _layered(layers, None)
    paint = _merge(_merge(_merge(base_paint, pre.get("paint")), S.get("paint")), spec.get("paint"))
    for name, d, ref in (("form", form, base_form), ("paint", paint, base_paint)):
        bad = set(d) - set(ref)
        if bad:
            raise ValueError(f"clutter {name} keys {sorted(bad)} unknown ({', '.join(sorted(ref))})")
    known = {"kind", "style", "seed", "variants", "form", "paint", "color", "lods", "atlas", "name", "moss", "wet"}
    bad = set(spec) - known
    if bad:
        raise ValueError(f"clutter spec keys {sorted(bad)} unknown ({', '.join(sorted(known))})")
    if spec.get("moss") is not None:
        paint["moss"] = float(spec["moss"])
    from .terrain_style import _hsv
    col = st.get("colour") or {}
    ref = spec.get("color") or S.get("color") or pre.get("color") or (WOOD_SRGB if mat == "wood" else LEAF_SRGB if mat == "leaf" else ROCK_SRGB)
    color = spec.get("color") or _hsv(ref, col.get("saturation", 1.0) * S.get("saturation", 1.0),
                                      col.get("value", 1.0) * S.get("value", 1.0))
    shape = pre.get("shape") or ("cluster" if form.get("cluster") else "rock")
    if mat == "litter":
        LODS.setdefault("litter", [8, 2])
    return {"kind": kind, "material": mat, "shape": shape, "style": st["name"], "seed": int(spec.get("seed", 1)),
            "variants": int(spec.get("variants", pre.get("variants", 4))), "form": form, "paint": paint,
            "color": [float(c) for c in color], "lods": list(spec.get("lods") or pre.get("lods") or LODS[shape]),
            "atlas": int(spec.get("atlas", pre.get("atlas", ATLAS))), "about": pre.get("about", ""),
            "collision": pre.get("collision", "convex" if shape == "rock" else None),
            "wet": _merge({"darken": 0.55, "roughness": 0.25, "band": pre.get("wet_band", 0.0)}, spec.get("wet") if isinstance(spec.get("wet"), dict) else None),
            "variant_forms": pre.get("variant_forms"), "_layers": layers,
            "seasons": ({se: dict(v, mix=_hsv(v["mix"], col.get("saturation", 1.0), col.get("value", 1.0))) if v else {} for se, v in LEAF_SEASONS.items()}
                        if mat == "leaf" else {"summer": {}}),
            "snow": st.get("snow"), "size_range": pre.get("size_range"), "place": pre.get("place")}


CHARTS = [(0, 1), (0, -1), (1, 1), (1, -1), (2, 1), (2, -1)]  # (axis, sign)

ALPHA_MIPS = ("import the albedo WITH mipmaps and scale alpha up by the mip level in the shader so thin leaves survive (as the groundcover grade): "
              "alpha = (a - cutoff) * (1 + lod * 0.25) / max(fwidth(a), 1e-4) + 0.5 for alpha to coverage, or a *= 1 + lod * 0.25 before the "
              "cut; the dome itself is opaque (alpha 1), so a far bush never thins to nothing")
WET_RECIPE = ("wet rock, per instance from the clutter.csv row's `water` column (m: the water surface over the row's z; > 0 standing in "
              "water, <= 0 that far above it, empty = dry land): line = z + water; wet = 1 below the line, fading to 0 over `band` x the "
              "instance's height (height_m x scale x squash) above it (splash and capillary rise), and anywhere it rains; "
              "albedo *= mix(1, darken, wet), roughness = mix(roughness, wet roughness, wet). The row's `sink` column (m) buries the "
              "instance that much deeper than its own sink_m x scale (half-buried river rocks)")
TINT_RECIPE = ("ROCK MATCHES ITS CLIFFS BY A PER-INSTANCE COLOUR: the pictures hold this style's default rock colour (`color_linear`). Per "
               "instance (MultiMesh instance colour / INSTANCE_CUSTOM, multiplied into the albedo in linear RGB): tint = (the rock colour of the "
               "terrain where it stands, linear: the terrain styles manifest's styles[].layers.rock.color_linear for the style region; with no "
               "styles manifest (realistic terrain) the tiles manifest's materials.layers[name = rock].color, sRGB -> linear) / color_linear x "
               "instance_tints[hash(row) % n] x (0.92 + 0.16 x hash). The pictures' mean luminance IS color_linear's and their tone range "
               "is a cliff's (p5 .. p95 of the luminance within `tone_range` x the mean), so the tint alone lands a stone in its cliff's tones. "
               "Lichen, moss and the damp foot shift a little with it, which reads fine. "
               "The four variants already differ in mineral tone (baked); instance_tints adds warm / cool / brown stones on top")
INSTANCE_TINTS = [[1.0, 1.0, 1.0], [1.05, 1.0, 0.94], [0.96, 0.99, 1.03], [1.04, 0.98, 0.91], [0.95, 0.95, 0.95]]
INSTANCE_RECIPE = ("(the last LOD casts no shadow: a bush's two crossed cards shadow each other) one MultiMesh per variant per LOD (per cell of the world): instance = translate(row x, y, z) * rotate_up(yaw) * "
                   "scale(s, s, s * squash); variant = hash(row) % variants; switch LODs by distance / s at `lod_switch_m` "
                   "(x the instance's scale), fade out over the last fifth before `cull`. The pivot is the ground line: the "
                   "mesh below it (sink_m x scale) is buried. Never scale below ~0.6 or above ~1.8 of size_range without "
                   "another kind: texel and facet sizes are made for that range")

SHORT = {"realistic": "real"}
# terrain clutter kinds -> what to draw them with (assets of this kit, or plants delivered beside them)
TERRAIN_KINDS = {
    "bush": {"asset": "bush", "z": "surface", "what": "scrub bush; squash < 1 near cliff lips (wind-shorn)"},
    "boulder": {"asset": "boulder", "z": "sunk 0.12 x scale already (old rows): lift by sink_m x scale, or accept it", "what": "angular boulders on rock and shores"},
    "river_rock": {"asset": "river_rock", "z": "surface", "what": "water-worn boulders in and beside a channel"},
    "cobbles": {"asset": "cobbles", "z": "surface", "what": "a patch of cobbles as one asset"},
    "slab": {"asset": "slab", "z": "surface", "what": "flat bank stones"},
    "driftwood": {"asset": "driftwood", "z": "surface, or the water surface - 6 cm when afloat", "what": "logs, branches, a jam (variants)"},
    "litter": {"asset": "litter", "z": "surface", "what": "a leaf / twig debris card"},
    "reeds": {"plant": "reed_ground", "z": "surface (root at or just under the water line)", "what": "reed clump, groundcover grade: scale = width / the json's clump width"},
    "sedge": {"plant": "grass_ground", "z": "surface", "what": "a bank tussock: the grass tuft (groundcover grade, cards), scale = width / 0.45; a `sedge` preset of its own is not made yet"},
    "tussock": {"plant": "grass_ground", "z": "surface", "what": "a grass tuft (groundcover grade), 0.45 m"},
    "tallgrass": {"plant": "grass_ground", "z": "surface", "what": "the same tuft drawn taller (scale 1.5); or leave it to the sward"},
}


# The modules this one was split into (C423). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("clutter_forms", "clutter_solid", "clutter_mesh", "clutter_bake", "clutter_build", "clutter_export",
           "clutter_kit")
