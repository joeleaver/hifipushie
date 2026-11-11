"""Hair as locks: Bezier curves swept with a lens profile, living in the Blender scene.

spec["hair"] = {
  "groom":  the designer's words and numbers; `groom()` grows the first pass of locks from them (hairline from the
            face landmarks, a parting, volume per region, flow per region, lock tiers). Parameters come first: change
            these and regrow before editing locks by hand.
  "locks":  {name: lock}: what the scene shows. Written by `groom()`, then edited by numbers or in Blender (pull
            brings moved control points, handles, radius, tilt and the modifier numbers back).
  "look":   the material: {"gap", "lit", "sheen", "grey" (sRGB hex), "roughness", "sheen_amount", "vary",
            "grooves" (strand ridges across a lock), "groove_depth", "anisotropic", "seen" (the colour the hair
            should READ, e.g. a photo's lit hair: derives the colour keys for the renderer's loss; see SEEN)}.
  "cap":    the dark underlayer on the scalp inside the hairline (m, default 0.002; 0 = none).
  "stage":  "mass" shows the groom's volume as one smooth shell (stage a: silhouette), else the locks.
  "part":   the export part (default "hair").
}
A lock: {"pts": [[az, el, h], ...], "width", "thickness", "cup", "taper", "belly", "root", "twist", "flip", "grey",
"radius"?: [per point], "tilt"?: [per point, radians], "handles"?: [[az, el, h, az, el, h] | null per point],
"tier"?: "big" | "fill" | "edge"}. Every point is an address on the head: azimuth in degrees round the head centre
(0 = the front, 90 = his left ear, 180 = the back), elevation in degrees up from the centre's level, and h metres
above the scalp along that ray (pts[0] is the root: h ~ 0). The centre comes from the face landmarks (between the
jaw tops, at the brows' height), so locks follow the head when it changes. Widths etc. in metres: width across the
lock at its widest (Belly: where along, 0..1), Root = the width at the scalp / the widest, Taper 1 = to a point,
Cup = how far the edges curl toward the head, Twist = degrees turned root to tip, Flip = degrees turned everywhere.

In Blender every lock is a curve object in the "hair" collection with the "hp_lock" Geometry Nodes modifier
(`blender_hair.py`): grab its control points and the mesh follows live.


Where the code is (split by responsibility, C415): this module holds the constants, HairError and the small shared
helpers; hair_head the scalp; hair_groom, hair_seat and hair_grow the groom; hair_spec the spec and hair_lockmesh the
lock geometry; hair_job, hair_cards_job and hair_card_fit the Blender jobs; hair_look the looks and gates;
hair_export the export; hair_drawn the drawn clumps; hair_reference and hair_trace a reference picture.
Module-level imports among them only point back up this list. A function that calls into a later module imports it
itself; a name a test or a spec may rebind (hair_head.scalp, any constant: hair.export.constants) is read as
module.name at call time, as every name was when this was one file."""
from __future__ import annotations

import numpy as np

def under(g: dict, H, az, el, d_in):
    """The underlayer's height (m): the mass sunk by about one lock thickness (the big locks' on top, the fill's
    round the sides), so the locks lying on it make the silhouette (a fraction of the volume buried the big locks)."""
    from . import hair_groom
    W = hair_groom.weights(az, el, d_in)
    top = W[..., 0] + W[..., 1]
    tb = float((g["tiers"].get("big") or {}).get("thickness", 0.0))
    tf = max(float((g["tiers"].get("fill") or {}).get("thickness", 0.0)),
             float((g["tiers"].get("strip") or {}).get("thickness", 0.0)))
    # not sunk over the upper sides, where the top locks lie down onto the side mass (sunk there too, the mass left
    # a waist under the top locks: a divot at each temple in the front view)
    side = side_tuck(az, el, W)
    # the fill (sides, back) is relief on the mass, not its volume: sunk a whole fill thickness, the gaps between
    # fill locks showed the sunk mass and the sides pinched in under the top again
    tw = top * (1 - side)  # the top proper: sunk by the big locks; the sides (and the top where it lies down) by theirs
    # the front edge not sunk (between generated front-row roots the sunk mass read as black pits along the hairline),
    # unless volume.edge_sink (0..1): a front lock laid on the hairline (drawn "to_hairline") covers the edge, and an
    # unsunk edge stood out under it as a dark lip (the band under the quiff)
    es = float(g["volume"].get("edge_sink", 0.0))
    depth = tw * tb * (es + (1 - es) * _ss(d_in / 0.006)) + FILL_SINK * (1 - tw) * tf
    return np.maximum(H - depth, np.minimum(H, 0.0015))



SIDE_TUCK = (0.25, 0.65)  # |lateral| of the head direction where a top lock starts / ends lying down on the side


def side_tuck(az, el, W=None):
    """0 on the crown, 1 over the upper sides: where a top lock lies down onto the side mass. (By elevation alone,
    sides and back, it did worse: the back's crown then stood proud of the tucked back.)"""
    fa = np.abs(((np.asarray(az, float) + 180) % 360) - 180)
    lat = np.abs(dirs(az, el)[..., 0])
    down = np.cos(np.radians(np.asarray(el, float))) * _ss((fa - 90) / 40)  # the back, turning down
    return _ss((np.maximum(lat, down) - SIDE_TUCK[0]) / (SIDE_TUCK[1] - SIDE_TUCK[0]))


TIP_STEP = 0.25  # how far a top lock's tip lifts off the lock under it, x its thickness
SIDE_NARROW = 0.35  # and how much narrower it gets there
FILL_SINK = 1.0  # how much of a fill lock's thickness the side/back mass sinks under it
REGIONS = ("front", "top", "sides", "back", "nape")
GROOM = {
    "fit": None,  # head_ref() of the head this groom was made on: lengths / volumes in metres scale with the head
    "hairline": {"front": 0.85, "temples": 0.008, "sideburns": None, "nape": 0.0, "ear": None, "ear_from": "mesh"},
    # ear: m the line runs over the ear's top (default 0.01); sideburns: m they reach below the ear's top (default
    # SIDEBURNS). ear_from "mesh": the ear is FOUND on the head (hair.ear); "brow": the old guess (its top at the
    # outer brow + 4 mm, sideburns default 0.028 below that), for a groom that must keep the line it was made with
    "parting": {"side": "left", "offset": 0.03, "length": 0.1},
    "volume": {"front": 0.045, "top": 0.036, "crown": 0.02, "sides": 0.012, "back": 0.013, "nape": 0.005},
    "length": {"front": 0.17, "top": 0.15, "sides": 0.055, "back": 0.06, "nape": 0.03},
    "flow": {"front": {"back": 1, "up": 0.3, "away": 0.6}, "top": {"back": 1, "away": 0.55},
             "sides": {"back": 1, "down": 0.45}, "back": {"down": 1}, "nape": {"down": 1}},
    "tiers": {"crown": {"width": 0.042, "thickness": 0.009, "spacing": 0.7, "where": ["top"]},
              "big": {"width": 0.05, "thickness": 0.011, "spacing": 0.6, "where": ["front", "top"],
                      "layout": "part", "front_away": 7, "front_part": 3, "root": 1.0, "part_row": 3, "front_span": 42},
              "fill": {"width": 0.026, "thickness": 0.007, "spacing": 0.8,
                       "where": ["sides", "back", "nape", "top"]},
              "gap": {"width": 0.026, "thickness": 0.004, "spacing": 0.8, "length": 0.05},
              "edge": {"width": 0.011, "thickness": 0.0028, "spacing": 0.9, "length": 0.022}},
    "grey": {"temples": 0.35, "sideburns": 0.5},
    "drawn": [],
    "drawn_under": True,  # an under clump between neighbours of a row: true, false, a sink (x thickness under the
    # row: 0.35 shows between the wedges, 1 is buried under the underlayer) or per row {stem: sink | false}
    "hairline_edge": None,  # {"inset": m (negative: tucked into the skin), "reach": m}: every drawn clump whose edge
    # comes within reach of the hairline lays that edge on it (the volume's rim showed between clump edges and skin)
    "tied": None,  # a tied STYLE (hair_flow.style: {"tie": low | mid | high.., "side", "tightness", "part", "tail",
    # "escaped", "neatness", "half", ...}): makes `tie`, the parting and strand dials. The way to ask for a ponytail.
    "tie": None,  # tied hair (hair_tied.py): {"at": [az, el], "out", "gather", "tail", "escape", "band"} or a list
    "loose": None,  # loose hair (hair_loose.py): grown all over the scalp, combed at the roots, then falling / standing:
    # {"length", "level", "spacing", "body", "lift", "stiff", "out", "back", "messy", "uneven", "ends", "fringe"}
    "noise": 0.3,
    "seed": 0,
    "centre": "head",  # without face landmarks (a kit-built head): the joint (or [x, y, z]) the scalp is measured from
}
LOOK = {"gap": "#221310", "lit": "#56352d", "sheen": "#86524a", "grey": "#9a948d", "roughness": 0.42,
        "sheen_amount": 0.45, "vary": 0.25, "grooves": 5, "groove_depth": 0.12, "anisotropic": 0.7,
        "edge": 0.55, "root": 0.12, "specular": 0.5, "band_shift": 0.25, "tip": "#7a5038", "tip_amount": 0.0,
        "band": "#23252b", "strand_relief": 0.6, "scalp_tint": 0.85, "grey_amount": 0.0, "grey_locks": 1.0, "eevee_gain": 1.6, "eevee_sat": 0.35, "light": None, "card_gain": 1.0, "card_sat": 1.0, "card_grey": 0.5,
        "cycles_fit": None, "seen": None, "fine_alpha": 0.5, "cycles_width": None, "cycles_sat": None,
        # cycles_melanin 0..1 (+ cycles_redness 0..1, cycles_random_color): Cycles renders the hair BSDF from MELANIN
        # (physical colour and light transport), the look's colour model as a tint on it; None = from the colour
        "cycles_melanin": None, "cycles_redness": None, "cycles_random_color": None,
        # the colour model (tesshair7; strands only): natural hair is never one colour, so the defaults vary
        # variation 0..1: locks differ in lightness, sub clumps / strands a little in hue and saturation
        # sun 0..1: sun-lightened lengths: the hair lightens and warms with its age (m from the scalp, full by 28 cm;
        #   a ponytail's ends are its oldest hair); roots stay the look's colour
        # highlights 0..1: the share of sub clumps that are lighter, warmer ribbons (gathered on some locks, starting
        #   a few cm off the root); highlight_contrast 0..1.5: how much lighter
        # fly_light 0..1: single fine hairs (fly-aways, halo, wisps, the hairline's rim) read lighter
        # (grey_amount: a share of grey strands; vary: the per-strand / sub-clump value noise under all of it)
        # depth 0..1: the under-layers of hair with volume are darker (a lock's "shade": the shadow strands do not cast
        #   on each other in EEVEE)
        # root_dark 0..1: how dark the first stretch (`root` of the length) is, 1 = the gap colour
        # gloss 0..1 (EEVEE strands): the two highlight lobes where light catches the hair (a sharp pale one toward
        #   the root, a broader one in the hair's own warm colour toward the tip); 0 = the matt strand of before
        "variation": 0.4, "sun": 0.2, "highlights": 0.0, "highlight_contrast": 0.6, "fly_light": 0.3, "depth": 0.5,
        "root_dark": 0.5, "gloss": 0.0,
        # the game-shader terms (EEVEE strands; each a game hair / card shader can do): tip_alpha 0..1 (see-through
        # tips), backscatter 0..1 (warm light through thin / back-lit hair), scatter 0..1 (fake multiple scattering:
        # a darker, richer core by depth, lighter outer layers). 0 = off (the default: other models unchanged)
        "tip_alpha": 0.0, "backscatter": 0.0, "scatter": 0.0,
        # sun_length m: the hair's age (m from the scalp) by which `sun` lightening is full (default 0.28); shorter =
        # the dome lightens too, not only the lengths (the front view sees the first cm of every strand)
        "sun_length": None, "sun_warm": None}  # sun_warm 0..1 (default 1): the sun-lightened lengths also warm; 0 = ash  # fine_alpha: EEVEE's opacity of single hairs (the halo, locks of `hairs`)  # band: a tie's colour; strand_relief: the cards' normal map  # edge: how far across a lock its edges darken; root: how far
# along the root darkens (0..1 of the length)
# seen: the hair's colour as it should READ (sRGB hex; e.g. the brighter half of a photo's hair pixels). The colour
# keys are asked for the renderer, which gives back about eevee_sat of their saturation (Cycles' hair BSDF; EEVEE's
# strands copy it with a Hue/Saturation node: HSV saturation x eevee_sat, scene-linear), so a photo's light brown
# typed into lit rendered grey-blond (2026-10-10), and at 0.35 no lit at all could reach a saturated brown in
# EEVEE. seen derives lit (seen's hue and value, saturation / eevee_sat, capped at 1), gap, sheen and tip around it,
# and eevee_sat = seen's saturation / lit's (EEVEE then draws seen exactly; Cycles gets what the gamut allows).
# Keys given in the look still win.
SEEN = {"gap": 0.3, "sheen": 1.45, "tip": 1.12}  # x lit (linear)
CARD_SAT_EXP = 0.55  # card_sat = eevee_sat ** this when the look has eevee_sat and no card_sat (full_look)


def _lin(c) -> np.ndarray:
    """A colour as linear RGB: "#rrggbb", or [r, g, b] sRGB 0..1 floats (look.seen from the hair reader's colour step:
    near-grey hair's hue does not survive 8 bits: at chroma ~5 one step of a hex digit is 5-10 deg of hue)."""
    if not isinstance(c, str):
        s = np.clip(np.asarray(c, float)[:3], 0.0, 1.0)
        return np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4)
    s = np.array([int(c.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    return np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4)


def _hexl(v) -> str:
    v = np.clip(np.asarray(v, float), 0, 1)
    s = np.where(v <= 0.0031308, v * 12.92, 1.055 * v ** (1 / 2.4) - 0.055)
    return "#" + "".join("%02x" % int(round(255 * x)) for x in s)


def seen_look(seen: str, sat: float = 0.35) -> dict:
    """lit / gap / sheen / tip / eevee_sat for hair that should read as `seen` through a renderer keeping `sat` of the
    (linear HSV) saturation."""
    import colorsys
    h, s, v = colorsys.rgb_to_hsv(*_lin(seen))
    s_lit = min(s / max(sat, 0.05), 1.0)
    lit = np.array(colorsys.hsv_to_rgb(h, s_lit, v))
    out = {"lit": _hexl(lit), "eevee_sat": round(float(s / s_lit), 4) if s_lit > 0 else sat}
    for k, f in SEEN.items():
        out[k] = _hexl(lit * f)
    # what reads lit WITHOUT the strands' desaturation (the scalp's tint, the cards' atlas) gets seen's own colour:
    # the boosted lit showed as an orange scalp between partings
    out["scalp"] = _hexl(_lin(seen) * (0.5 + 0.5 * SEEN["gap"]))
    out["card_sat"] = out["eevee_sat"]
    return out


def full_look(look: dict | None) -> dict:
    """The look with its defaults and, if it has `seen`, the colours derived from it (explicit colour keys win)."""
    lk = dict(look or {})
    if lk.get("seen"):
        lk = {**seen_look(lk["seen"], float(lk.get("eevee_sat", LOOK["eevee_sat"]))), **lk}
    if "card_sat" not in lk and "eevee_sat" in lk:
        # the cards are drawn by a plain material, as EEVEE draws the strands: the same desaturation of the look's
        # colours (asked for Cycles' hair BSDF). Tess's W18 look sets eevee_sat 0.3 and no card_sat: her cards came
        # out 1.8x the strands' saturation (check_tiers), orange beside the approved strand look
        # measured (check_tiers on Tess's W18 hero cards: card_sat 1.0 -> 1.8x the strands' saturation, 0.3 -> 0.7x):
        # the cards' atlas is not the strands' colour pipeline, so not the same factor: eevee_sat ** CARD_SAT_EXP
        lk["card_sat"] = round(float(lk["eevee_sat"]) ** CARD_SAT_EXP, 3)
    if lk.get("seen") and "card_gain" not in lk:
        # a look from a photo's colour (seen_look) sets lit = seen and leaves the lift to the renderer: the EEVEE strands
        # draw lit x eevee_gain (1.6), so the cards' atlas, at card_gain 1.0, came out AS the photo's seen colour (G88a:
        # atlas mean sRGB [0.242 0.232 0.227] == seen) and Garrett's 96 cards read near-black beside the grey strand
        # look. The cards take the strands' lift (an explicit card_gain, measured by check_tiers, wins)
        lk["card_gain"] = float(lk.get("eevee_gain", LOOK["eevee_gain"]))
    return {**LOOK, **lk}
LOCK_KEYS = {"pts", "width", "thickness", "cup", "taper", "belly", "root", "twist", "flip", "grey", "radius", "tilt",
             "handles", "tier", "edge", "hand", "free", "space", "core", "strands", "swoop", "hairs"}
# hairs: n > 0 = the lock is n SINGLE strands (strand grooms: loose hairs beside a face; hair_strands.WISPS)
# free: 0..1, the lock hangs clear of the head (its underside is hair too, not the dark gap side); space "xyz": pts
# are metres from the head centre [x, y, z] (hair that leaves the head: a tail), not [az, el, h]; core: a polyline
# (same space) the lock's outward side faces away from (a tail's own axis); strands: this lock's own card numbers
MOD = {"width": "Width", "thickness": "Thickness", "cup": "Cup", "taper": "Taper", "belly": "Belly", "root": "Root",
       "twist": "Twist", "flip": "Flip", "grey": "Grey", "edge": "Edge", "free": "Free"}
LOCK_DEFAULTS = {"taper": 1.0, "belly": 0.3, "root": 0.6, "twist": 0.0, "flip": 0.0, "grey": 0.0, "cup": 0.002, "edge": 0.8,
                 "free": 0.0}
STYLES = ("locks", "cards", "strands")  # hair.style: solid sculpted locks (stylised), or strand cards (hair_cards.py)
WORDS = {"back": (0, 1, 0), "forward": (0, -1, 0), "down": (0, 0, -1), "up": (0, 0, 1), "left": (1, 0, 0),
         "right": (-1, 0, 0), "away": None}


class HairError(ValueError):
    pass


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _part_side(side) -> float:
    """parting.side as the part's offset direction: left / right / centre (or center)."""
    v = {"left": 1.0, "right": -1.0, "centre": 0.0, "center": 0.0}.get(side)
    if v is None:
        raise ValueError(f"hair parting side {side!r}: one of left, right, centre (or center), none")
    return v


def dirs(az, el):
    """Unit directions for azimuth / elevation in degrees (0 = front -Y, 90 = +X his left)."""
    a, e = np.radians(az), np.radians(el)
    return np.stack([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)], -1)


def az_el(v):
    u = _unit(np.asarray(v, float))
    return np.degrees(np.arctan2(u[..., 0], -u[..., 1])) % 360, np.degrees(np.arcsin(np.clip(u[..., 2], -1, 1)))


# The modules this one was split into (C415). hair.export.constants finds a constant named "hair.X" in any of them.
MODULES = ("hair", "hair_head", "hair_groom", "hair_seat", "hair_grow", "hair_spec", "hair_lockmesh", "hair_job",
           "hair_cards_job", "hair_card_fit", "hair_look", "hair_export", "hair_drawn", "hair_reference", "hair_trace")
