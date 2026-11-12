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


Where the code is (split by responsibility, C415; constants back here, C422): this module holds EVERY constant of
the family (set at hair.NAME by specs, scripts and tests; the other modules read hair.NAME), HairError and the small shared
helpers; hair_head the scalp; hair_groom, hair_seat and hair_grow the groom; hair_spec the spec and hair_lockmesh the
lock geometry; hair_job, hair_cards_job and hair_card_fit the Blender jobs; hair_look the looks and gates;
hair_export the export; hair_drawn the drawn clumps; hair_reference and hair_trace a reference picture.
Module-level imports among them only point back up this list. A function that calls into a later module imports it
itself; a name a test or a spec may rebind (hair_head.scalp, any constant: hair.export.constants) is read as
module.name at call time, as every name was when this was one file."""
from __future__ import annotations

import numpy as np
from . import moved

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


_SCALPS: dict = {}

GREY_AGES = (30.0, 50.0)   # the default groom grey: none before the first age, all of it from the second

POCKET = 0.012  # m: (one mesh) air this deep along a scalp ray is outside the head, not a pocket in it (an ear canal)
HAIRLINE_JOIN = 25.0  # deg of azimuth over which the default line past traced front_points eases onto their end


EAR_OPEN = 19  # cells of azimuth (x Scalp.STEP deg = 38): what stands off the head narrower than this is "a bump"
EAR_BUMP = 0.004  # m a ray must stand off the head without the bump to count as ear
EAR_LOW = 0.0015  # m: ... and what the ear is grown into from there
EAR_OVER = 0.006  # m the line runs over the found ear's top by default (groom.hairline.ear)
EAR_CLEAR = 0.003  # m: the hairline never runs lower over the found ear than this above its top
SIDEBURNS = 0.014  # m the sideburn reaches below the found ear's top by default

_LINES: dict = {}

_FILLS: dict = {}

# the groom's keys in metres (scaled with the head by `fit`); lists of [az, z] keep az and scale z about the centre
_METRE_KEYS = {("length",), ("volume",), ("hairline", "temples"), ("hairline", "temple_dip"), ("hairline", "ear"),
               ("hairline", "sideburns"), ("hairline", "nape"), ("parting", "offset"), ("parting", "width"),
               ("parting", "length"), ("parting", "front"), ("loose", "length"), ("loose", "spacing"), ("loose", "lift"), ("loose", "lift_ramp"),
               ("loose", "body"), ("loose", "thickness"), ("loose", "level"), ("loose", "swoop", "depth"),
               ("loose", "swoop", "length"), ("loose", "fringe", "length"), ("loose", "fringe", "depth"),
               ("loose", "fringe", "level"), ("tie", "out"), ("tie", "gather", "lift"), ("tie", "gather", "width"),
               ("tie", "tail", "length"), ("tie", "tail", "fullness"), ("tie", "curtain", "lift"),
               ("tie", "frame", "length"), ("tie", "frame", "width")}
_UNITLESS = {"across", "ramp"}  # (volume.across / ramp are shares, not metres)
# The tie's own geometry that a tied STYLE writes in absolute metres (hair_flow.style: the dome's stand-off, wisp and
# stray lengths, the tail's sway / air / lock waves). Until 2026-10-14 fit_to_head did not scale these: th_W18 carried
# onto tp_h3 (a 15 % bigger scalp) kept its dome and face wisps at the old head's size while its tail scaled (review:
# "shorter face wisps", a flatter top). They scale by this head over the one they were last GROWN at (`fit.abs_r`,
# stamped by carry), so a groom regrown on its own head is unchanged. Value: the dict's keys that are NOT metres.
_TIE_KEYS = {("tie", "gather", "volume"): {"arc", "layers", "locks", "cross", "hold"}, ("tie", "gather", "puff"): set(),
             ("tie", "gather", "zig"): set(), ("tie", "gather", "above"): set(), ("tie", "wisps", "length"): set(),
             ("tie", "wisps", "over"): set(), ("tie", "tail", "stray_length"): set(), ("tie", "tail", "sway"): set(),
             ("tie", "tail", "sway_length"): set(), ("tie", "tail", "flick"): set(), ("tie", "tail", "air"): set(),
             ("tie", "tail", "lock_wave"): set(), ("tie", "tail", "lock_wavelength"): set(),
             ("tie", "tail", "coil_radius"): set(), ("tie", "escaped", "length"): set()}

SEAT_NEAR, SEAT_FAR = 0.03, 0.09  # m off the source scalp: closer, a point keeps its scalp address (az, el, h x k);
# further (a hanging tail, wisps below the jaw), it moves rigidly with the head (scaled about its centre); between, a blend
SEAT_STRAND_M = ("wave", "wavelength", "roots_m", "clump_size", "curl")  # lock strand dials in metres


SEAT_EAR_FADE = (25.0, 35.0)  # deg: the ear warp fades out this far above the ear's top / round the ear's azimuths

FOLD_LIMIT = 1.0  # in-plane bend x half width: at 1 the lock's inner edge runs backwards (folds over itself)

ROOT_END_MM = 15.0  # a root end wider than this where it rises out of the layer reads as a blunt end

ROOT_RISE = 0.003  # m
FIN_MM = 3.0  # an edge standing this much more than the lock's own thickness over the layer reads as a fin

LIFT_RAMP = 0.03  # m: a lift grows to its full height this far in from the hairline

GATE_VIEWS = (("front", 0.0, ("left", "right")), ("three_quarter", 40.0, ("left",)),
              ("three_quarter_r", -40.0, ("right",)))

SHELL_MIN_GAP = 0.0004  # (sh6) m: each shell stands at least this far over the layer below it, the hairline included
# (eased to 0 there, cap and shells were the same triangles: coincident alpha-tested layers render as holes / z-fight)
SHELL_HROW_DROP = None  # (sh6) {"fa": [a0, a1], "el_max": deg}: the shells style's hairline-row cards whose middle lies
# a0..a1 deg from the front and under el_max deg over the scalp centre are dropped (Garrett's sideburn: dense cards drew
# flat grey dabs with round ends at game distance; the cap's tapered strands are the sideburn there)

SHELL_EDGE_LIFT = None  # (sh4) m: the shells cap's lift at the hairline (None = the full lift everywhere)
SHELL_LIFT_EASE = 0.005  # (sh4) m in from the hairline over which the lift eases to SHELL_EDGE_LIFT
CAP_RELAX_FLOOR = True  # (round 30) the relaxed cap keeps the floor cap_under_cards gave it (lift off the scalp)
CAP_RELAX = 60  # (round 26) iterations: the card cap's radius relaxed over its mesh, only lowered (0 = off)
CAP_SMOOTH = 0.0  # deg: the mass cap's height smoothed over this (gaussian sigma, 0 = off; round 26)

# Card budgets by what the hair is for (triangles for the whole hair: cards, cap, baby hairs, tie). Epic's Hair Card
# Generator tutorial spends ~54k on a hero's LOD 0 in five layers (coverage 4%, mid 14%, top 46%, fly-aways 18%, short
# hairs 18%); a game character whose whole body is ~46k can't. The layers below are ours: 0 = the opaque coverage
# (dense / hairline tiles), 1 = mid, 2+ = top and break-up, fly-aways and baby hairs on top; the cap is the scalp chart.
# group: how big a clump of strands one card stands for (hair_cards.clump_cards): a lower tier has FEWER, WIDER cards
# from bigger clumps, never the same thin cards thinned out; "free" = only hair off the head gets cards, the cap
# (the scalp chart) and the tail's core carry the rest.
SHELL_FINS = 0.0  # (sh3) shells style: keep the flow-top / arch cards whose middle lies within this share of the head's
# radius of the front or side OUTLINE (|unit dir . y| or |. x| under it) and above SHELL_FIN_EL: fins for the top's
# volume / outline (0 = off: hairline rows only). hair.export.shells.fins overrides.
SHELL_FIN_EL = 20.0  # deg over the head centre
SHELL_FIN_TIERS = ("hero", "main")

SHELL_CARD_VALUE = 1.0  # (sh4) shells style: the kept cards' (hairline rows, fins) colour x this, toned to the cap
SHELL_TIERS = {"hero": 2, "main": 2, "npc": 1, "far": 0}  # (sh1) shells per tier (hair.export.shells.tiers overrides)
_CHARTS: dict = {}  # the last short chart baked (every tier of an export wears the same one)
MASS_MIN = 0.06  # m: loose hair shorter than this (mean lock length) gets no mass shell under its cards
# A SHORT cut (loose hair under MASS_MIN) as game artists build it: the cap, wearing the scalp chart with EVERY strand
# of the groom drawn where it lies (1 texel a strand at a 2048 chart: ~0.3 mm), carries the look; over it only a
# sparse layer of cards for what stands off the head (the lifted front, the silhouette's breakup), each on a tile of
# many fine strands with soft tips and no opaque base, plus single-hair cards along the hairline. Cards cut one per
# clump and worn on the dense tile read as torn paper / leaf litter at bust distance (Garrett's crop).
SHORT_TIERS = {"hero": {"triangles": 16000, "cap_step": 6.0, "group": "pair", "layers": 2, "baby": 0.0, "fly": 2},
               "main": {"triangles": 8000, "cap_step": 7.5, "group": "pair", "layers": 1, "baby": 0.0, "fly": 1},
               "npc": {"triangles": 4000, "cap_step": 10.0, "group": "lock", "layers": 1, "baby": 0.0, "fly": 0},
               "far": {"triangles": 1500, "group": "lock", "layers": 1, "baby": 0.0, "fly": 0}}
EVEN_SHORT_CAP = 1  # (c1, 2026-10-18) an EVEN short groom (clumps-cut cards) still wears the short cut's baked cap
# (hair_cap.chart: every strand drawn, grey by lock): hs.cap_chart reads no hair_even strands (G88a c1c: bare scalp patches)
EVEN_CAP_KEEP = 0.6  # (c3) x the even cap's mid height: the least it keeps under its cards (0: the scalp floor, c2's hero holes)
EVEN_CLUMPS = 1  # (c2) an even groom is cut by visual clumps at every tier (0: the hero tier only, before c2)
EVEN_SHORT_LIFT = 1  # and that cap stands at the hair's mid height (the short cut's mass) when 1 (c1e: default); 0 = on the scalp (c1d: under the skin, bare patches)
SHORT_TOP = 0.6  # x a clump's spread along its normal: a short cut's card stands at the top of its clump
SHORT_TIP = 0.0015  # m: how far a short cut's card tips rise off the cap (x 0.2-1.6 per card)
SWOOP_CARDS = 3  # a swoop's dedicated cards (one lock)
CUT_GROUPS = ["sub", "pair", "lock", "free"][:3]  # finer -> coarser card cuts (clump_cards' groups; "free" drops lying hair)
PRIO_FLY = 2.0  # budget priority offsets (lower = kept first): single hairs after every coverage layer
PRIO_FREE = -0.6  # hanging hair (free locks: a tail) before the second layer of hair lying on the head
PRIO_HALO = 0.35  # pooled single hairs (the halo as ~30 fly cards, ~400 triangles): kept just before a tail's second layer
PRIO_FACE = -0.8  # face-framing hair (wisps, curls at the temples) before anything but the coverage layer's core
FACE_IN, FACE_AZ = 0.02, 115.0  # m inside the hairline, deg from the front: where a free lock's root counts as face-framing
ARCH_TIERS: dict = {"main": 0.6, "npc": 0.4, "far": 0.25}  # (round 35; default from round 36 = f1) tier -> share of hair_clumps.ARCH arch cards per run at that tier (e.g. {"main": 0.6,
# "npc": 0.4, "far": 0.25}; {} = off): the crown arch (and with hair_clumps.ARCH_FILL its cap fill) carried to LOD1-3, fewer
# and wider, so the crown doesn't drop at the LOD0 -> LOD1 switch
COVER_TIERS: dict = {}  # (round 33) tier -> share of hair_clumps.PART_COVER cover cards per side at that tier (e.g.
# {"main": 0.6, "npc": 0.4}; {} = off): the part cover row thinned with the tiers
CUT_SHARE = 0.45  # the coverage layer of every lock must fit this share of a tier's triangles, else the cut coarsens
SWOOP_WIDTH = 0.026  # m: their width
SWOOP_BACK = 0.003  # m inside the hairline where they start
SWOOP_LAYERS = 3  # each swoop card is this many stacked cards of the fine short tiles
SWOOP_GAP = 0.0012  # m between those layers
SWOOP_LIFT = 0.007  # m the swoop's cards rise mid-lock over where its strands lie (its wave)
BABY_TONE = 1.0  # (round 43, opt-in) baby-hair cards' vertex tone x this. Tess's "nape tick marks" (18-38 mm dark dashes
# under the tie, vertex colour .32-.49 vs the tail's .65) are THESE cards (baby_locks all round the hairline, kind "baby",
# cls None: hair_clumps' NAPE_LIFT / NAPE_SHORT only see clump cards, so round 42's lever never reached them; t43/trace.py)
BABY_NAPE = (0.05, 0.02)  # (round 44; default after a blind A/B vs r42c NEW 2 / OLD 0 / SAME 2) (z, y) m: on a TIED groom, baby cards rooted lower than z under the scalp's
# centre AND more than y behind it are dropped (the groom has no baby hairs at the nape under a gather: they drew
# Tess's dark tick marks there; t43/ticks.py found them at z < -0.06, y > +0.025). () = off
SHORT_BABY_PRIO = 0.3  # a short cut's baby hairs (the hero tier's soft hairline) are kept before second-layer cards
SHORT_STRAIGHT = 0.6  # share a short cut's card is drawn toward its straight chord (no hooks)
SHORT_EDGE = 0.0  # m inside the hairline where a short cut's cards end (past it their thick strands stood as wires)
SHORT_GREY = 0.45  # a short cut's card is darker by this x (the greyest locks' grey share - its own lock's)
SHORT_ATLAS = 2048
CARD_TIERS = {
    "hero": {"cap_step": 6.0, "group": "sub", "layers": 3, "card_width": 0.012, "segment": 0.008,
             "fly": 2, "baby": 2.0, "core_sides": 12, "mass": 5000, "cut": "clumps"},
    "main": {"cap_step": 5.0, "group": "pair", "layers": 2, "card_width": 0.02, "segment": 0.012,
             "baby": 0.6, "core_sides": 10, "mass": 3500},
    "npc": {"cap_step": 8.0, "group": "lock", "layers": 1, "card_width": 0.028, "segment": 0.025,
            "baby": 0.0, "core_sides": 8, "mass": 1800},
    "far": {"cap_step": 14.0, "cap": "mass", "group": "free", "layers": 1, "card_width": 0.07, "segment": 0.05,
            "baby": 0.0, "core_sides": 6, "mass": 800},
}
# the tiers ARE the hair's LODs: their triangles come from the export budgets (budgets.json, a hero character's
# hair_cards at LOD0..3: sourced, not chosen here; it was a made-up 40k / 16k / 6k / 1.5k). A groom's own
# hair.export.tier_triangles {tier: n} or hair.export.role (hero / main_npc / secondary_npc / crowd) overrides
CARD_TIER_LOD = {"hero": 0, "main": 1, "npc": 2, "far": 3}

# (c13, coordinator 2026-10-19) a tier's DRAWN triangles (back faces included) stay within its role's RANGE maximum in
# budgets.json (hair_cards range[1]): the tiers are the roles' hair (hero 50k, main_npc 20k, secondary_npc 8k, crowd 1.5k)
CARD_CUT_SHARE = 0.8  # the clumps cut aims at this share of the tier's budget (card faces; the budget fit trims the rest:
# c13a's hero cut made 15.3k card faces for a 25k-face allowance, main / npc / far are bound by their drawn maxima)
TIER_ROLE = {"hero": "hero", "main": "main_npc", "npc": "secondary_npc", "far": "crowd"}

FRONT_SHORT = 0.0  # (round 46, opt-in) m: clump cards (not face / fly) shorter than this rooted in front of and above the
# head centre (FRONT_SHORT_YZ: y < [0], z > [1] from C) are dropped: r45a's dark splintered patch where the part meets the
# forehead was 17-20 mm, 6-vertex cards at vcol .37-.46 wearing a long card's tile squashed (its tips = the serrations)
FRONT_SHORT_YZ = (-0.05, 0.02)
CAP_TONE = 1.4  # (round 45; default after the blind A/B r45a vs r44d NEW 2 / OLD 0 / SAME 2) x the card cap's vertex colour under the colour model (0.9 / peak:
# ~0.35 on Tess vs the cards' ~0.65; the cap's albedo 52 vs the cards' 85-93 in the crown box): where it shows between
# cards it is ~40 % of the darkest crown pixels at 2x its area share (t45/capshare.py)
CAP_TONE_TIERS: dict = {}  # (round 47, opt-in) tier -> CAP_TONE there: the far tier (group "free") keeps no head cards, so
# its whole head IS the cap at CAP_TONE's darker-than-cards value: LOD3's head read a shade darker than LOD0's
CAP_BARE_FLOOR = True  # a cap vertex with no coverage card within CAP_FAR lies at the floor (False: its mass height, before round 18)
CAP_UNDER = 0.0025  # m: the cap stays this far under the lowest coverage card over it
CAP_FAR = 12.0  # deg: a cap vertex with no card within CAP_REACH takes the nearest cards' height within this
CAP_TOP_EL = 0.0  # (round 32; opt-in) deg: over this elevation a cap vertex with no card within CAP_REACH takes the
# HIGHEST of the nearest cards' heights within CAP_FAR (not the lowest less CAP_UNDER): no card passes over el 80, so the
# top of the dome was the cap at the seated roots' height, a dip between the crown's cards (Joe: "chopped off"); 0 = off
CAP_REACH = 4.0  # deg: the cards over a cap vertex are those within this angle of it (seen from the head's centre)

CARD_CLEAR = 0.0015  # m: every card vertex stays this far outside the head (None: measure only)

VIEWS = {"front": (0.0, 5.0), "three_quarter": (40.0, 12.0), "side": (90.0, 5.0), "back": (180.0, 10.0),
         "top": (20.0, 60.0), "three_quarter_r": (-40.0, 12.0), "side_r": (-90.0, 5.0),
         "back_quarter": (140.0, 8.0), "wide_r": (-95.0, 4.0, 0.95), "wide_back": (165.0, 6.0, 0.95),
         "wide_front": (-20.0, 4.0, 0.9), "close": (-30.0, 25.0, 0.45),
         "close_back": (150.0, 20.0, 0.45), "close_front": (12.0, 8.0, 0.4), "close_side": (75.0, 15.0, 0.42),
         # (az, el, distance, m the target sits under the head centre): the bust, for hair that falls
         "bust_front": (0.0, 4.0, 1.25, 0.14), "bust_three_quarter": (40.0, 8.0, 1.25, 0.14),
         "bust_side": (90.0, 4.0, 1.25, 0.14), "bust_back": (180.0, 6.0, 1.25, 0.14), "bust_side_r": (-90.0, 4.0, 1.25, 0.14),
         "bust_back_quarter": (140.0, 8.0, 1.25, 0.14), "long_back": (180.0, 4.0, 1.9, 0.26),
         "long_side": (90.0, 4.0, 1.9, 0.26)}

# Lights for strand / card looks (each a sun; "dir" points from the head toward the light). Hair is read by its
# highlight band and by light coming through its edge: a key from the front, a soft fill, and a rim from behind
# (what a portrait photographer calls the hair light). Solid locks keep the stage's single sun.
LIGHTS = {
    "salon": {"lights": [{"dir": [-0.45, -0.75, 0.55], "energy": 3.0, "angle": 8.0},
                         {"dir": [0.8, -0.45, 0.15], "energy": 0.7, "angle": 30.0, "specular": 0.0,
                          "color": [0.86, 0.9, 1.0]},
                         {"dir": [0.35, 0.8, 0.5], "energy": 4.5, "angle": 5.0, "color": [1.0, 0.96, 0.9]}],
              "world": {"color": [0.77, 0.81, 0.86], "strength": 0.5}},
    "flat": {"lights": [{"dir": [-0.4, -0.7, 0.6], "energy": 3.5, "angle": 3.0}]},
}

BARE_BAND = 0.015  # m inside the hairline: bare volume there is reported as "<region> hairline"

GATE_MM = 1.5  # the deepest dent allowed in the hair's outline (front and 3/4), mm, from the brows up to...
GATE_SCALE = 0.012  # m: the outline is gated on shapes at least one lock row tall (smoothed over it): a waist or
# divot is tens of mm; a clump's step where one lock ends over the next is a notch, the relief we want
NOTCH_SCALE = 0.006  # m: notches (clump steps at the outline) are measured on this and reported, target 2-5 mm
CROWN_BAND = 0.02  # ...this far under the top (the top's outline is the lock crowns: reported, not gated)

EXPORT = {"segments": 24, "sides": 10}  # per lock (spec["hair"]["export"] overrides): 12 x 8 read faceted in the
# export (the lens's thin edges shaded as flat planes), 24 x 10 is ~20k triangles for 45 locks

EXPORT_CARDS = {"triangles": 12000, "tier": None, "cap_step": 6.0, "alpha_cutoff": 0.33, "shadow_proxy": True}  # spec["hair"]["export"] overrides
CARD_RECIPE = (
    "Hair cards. Draw two-sided with one normal for both faces (the mesh's normals are already bent toward the hair "
    "volume: do not flip them on back faces). Alpha: the base colour's alpha, alpha-tested at alpha_cutoff with "
    "dithering + temporal AA, or alpha-to-coverage with MSAA; keep the alpha's coverage in the mips (or bias mips "
    "-1). COLOR_0 multiplies the base colour: the root-to-tip ramp, a value per lock and per card, lower layers "
    "darker. Anisotropic highlight along the hair: TANGENT's bitangent (the atlas's v) runs root to tip. The aux "
    "texture holds R = root gradient (1 at the root), G = a value per strand (shift the highlight and the value "
    "with it), B = depth in the clump (0 deep: darker, less specular; usable as pixel depth offset), A = alpha. "
    "LODs: drop the cards of `layer` 2, then 1 (extras.layers gives each layer's triangle range).")


BACK_FACES = 1  # (c6) export each card's back face as its own triangles (outward normals) + a single-sided material
BUDGET_UNIT = "card_faces"  # (hair-budget rule 2026-10-19) a tier's budget counts card faces (one side);
# drawn triangles (back faces included) must fit the role's range max (checked at export: asset.hair_budget)
CARD_RECIPE_FACES = CARD_RECIPE.replace(
    "Draw two-sided with one normal for both faces (the mesh's normals are already bent toward the hair "
    "volume: do not flip them on back faces).",
    "Every card's back is its own triangles (reversed winding, the SAME outward normal): draw single-sided with "
    "back-face culling (the material is not doubleSided), so no engine flips a normal.")

CARD_ROUGH_MIN = 0.6  # (r59) the cards' roughness floor in the export's ORM: the outer, lit hair (aux.b high) came out at
# 0.425 (the 0.5 floor x 0.85), and an isotropic engine lobe at that mirrored the key light off the crown's flat cards as
# one white plate (Tess rc2i's "white glossy crown"; 0.65 / 0.75 in the game preview took it away, 0.6 + the tinted half
# specular below leaves a faint warm sheen). The baked-cap path already says it: "glossy, it was tin foil".
CARD_SPECULAR = 0.5  # (r59) the combined character GLB's hair KHR_materials_specular factor (half a dielectric's) ...

ROOT_TILT = 0.5  # the climbing root's tilt, x the lie's tilt behind it (1: nape rows folded at their roots)
ROOT_CLIMB = 0.012  # m: the shortest run over which a drawn clump's root rises from under the layer to lie on it
TILT_MAX = 1.3  # rad: the most a drawn clump's flat side turns off facing away from the head centre
BEND_EASE = 0.7  # drawn clumps are eased until their spine's in-plane bend x half width is under this

EDGE_SMOOTH = 0.008  # m: the hairline edge's own sweep is the edge with tips/notches narrower than ~this taken out
EDGE_REACH = 0.03  # m: how far either side of the traced hairline the rendered edge is looked for

FLOW_BAND = (0.004, 0.028)  # m inside the traced hairline: the band whose strand direction front_flow compares
FLOW_BINS = 6

REGION_NAMES = ("front", "top", "side.L", "side.R", "back.L", "back.R", "back")

OUTLINE_STEP = 3.0  # deg: the matched view's outline is sampled on rays from the head centre this far apart

# The modules this one was split into (C415). Their constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("hair", "hair_head", "hair_groom", "hair_seat", "hair_grow", "hair_spec", "hair_lockmesh", "hair_job",
           "hair_cards_job", "hair_card_fit", "hair_look", "hair_export", "hair_drawn", "hair_reference", "hair_trace")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
