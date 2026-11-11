"""A base mesh as the start of a character: spec["base"] = {"template": "male_stylized", ...} puts the CC0 template
body (Blender Studio's Human Base Meshes, `templates/`) into the field as one primitive, posed and stretched onto the
spec's skeleton, so a human starts from real planes (jaw, cheekbones, lids, lips, hands) and everything else (blobs,
bones, strokes, kits, shell parts, paint) edits on top of it.

- Joints: the template's skeleton (pelvis, chest, neck, head, shoulder/elbow/wrist, hip/knee/ankle/toe, fingerN_k,
  thumb_k .L) is added to the spec's joints where the spec doesn't give them (`inject`, before kits), with radii
  measured from the template. Moving a joint moves the base with it (`retopo._skeleton_warp`: per bone segment a
  rotation and a stretch, radii kept, times "girth" {segment start joint: scale}, e.g. {"shoulder.L": 1.15} for a
  thicker upper arm). Rotations by forward kinematics down every chain from rigid fits where several bones start
  (pelvis + hips, chest, palm; `retopo._body_rotations`), a bone ending at a fit twisting into it along its length
  (forearm -> palm), blended only between related bones: symmetric specs give symmetric bodies, a rigidly moved
  skeleton a rigidly moved body. Hands move by FK from a rigid fit of the palm (`retopo._hand_rotations`): joints
  that keep the template's hand pose move it as one piece, blended into the forearm over 3 cm past the wrist.
- Surface: the warped quads are Catmull-Clark subdivided ("subdivide", default 1) and become an implicit surface
  (`sd_base`): IMLS over the vertices (Kolluri 2005): f(x) = sum w_i n_i.(x - p_i) / sum w_i, w_i Wendland's C2 kernel of support 2 h_i, h_i
  the vertex's own edge length x "smooth" (default 1), 24 nearest vertices. Smooth (no facets),
  follows the quads' density (1-2 mm round the eyes, ~8 mm on the back), and ~ a signed distance near the surface.
  The kernel widens with distance (h >= 0.7 x the nearest vertex's distance), so off the surface it's a plane fit
  over a patch as wide as the distance: shells 5-15 mm out are smooth. Past 3 cm it fades to the distance to the
  nearest vertex minus the largest h (conservative, for culling).
- Body sources (`source`): the template (default) or MakeHuman (`body: {"source": "makehuman", "age", "weight",
  "muscle", "height", "race"}`, makehuman.py): no hand edits for age and build.
- Head graft (`head: {"source": "gnm", ...}`, Google GNM): the body's head is cut at one of its own neck loops ~2.5 cm under
  its chin and the loop extruded as a quad tube (`_neck_tube`) whose rings leave the loop along the body's slope (Hermite)
  and then follow the head's own neck slice by slice through the overlap; body points under the (tilted) graft plane
  and head points over it make one IMLS point set, weighted by C2 ramps across +-SEAM (the k nearest are raised
  there). Blending two fields across a band showed as a collar; points cut hard at the plane left a crack; a tube
  matched only at the plane stood proud of the head's narrowing neck and flecked.
- Topology payoff: `retopo.wrap` of a base-built body starts from the same template, so the export quads follow.

Where the code is (split by responsibility, C417): this module holds the constants, `source` and `template_joints`.
base_imls: Catmull-Clark, normals, the IMLS field. base_identity: GNM's data, identity fits, the posed expression,
region weights. base_head_shape: nose tip, chin, jawline, lean, ears, hood, planes. base_gnm_parts: GNM's eyes and
mouth, the lips' close and zip. base_gnm_head: `gnm_head`. base_measures: `head_of` and the head's measures and
landmark joints. base_tubes: the neck tube, garment tubes, `garment`. base_surface: `surface`, the sealed mouth's
field, `sd_base`. base_implied: `inject`, the implied parts, the mouth's interior, the eye's own measures.
"""
from __future__ import annotations

import json

import numpy as np

from . import retopo

VERSION = 107  # bump when the base field changes: builds and live grids are keyed on it (107: GNM's own eyeball and mouth)
K = 32
FAR = 0.03  # m
SEAM = 0.012  # m: half-width of the head graft's overlap
TUBE_BAND = 0.08  # m: where a garment's torso tube hands over to the cloth from the body
OWN_REACH = 0.035  # m (x the head's scale): how far over the graft plane a followed head eases onto its body's own
LOW_LOOP = 0.004  # the neck loop's least clearance under the graft's overlap (see _neck_tube)
_CACHE: dict = {}
_WARNED: set = set()  # deprecation messages already given (faceslide.deprecated)


def source(b: dict) -> dict:
    """The body the base starts from, as a template dict (retopo.load_template's): the Blender Studio template
    (b["template"], default), or MakeHuman shaped by its macro targets (b["body"] = {"source": "makehuman", "age",
    "weight", "muscle", "height"})."""
    body = b.get("body") or {}
    if body.get("source") == "makehuman":
        from . import makehuman
        return makehuman.body(body)
    if body.get("source") == "human":  # one human mesh (onemesh.py): MakeHuman's body and GNM's head, stitched once
        from . import onemesh
        return onemesh.template(b)
    if body.get("source") not in (None, "template"):
        raise ValueError('base body: {"source": "makehuman" | "human", ...} or the template (default)')
    return retopo.load_template(b.get("template", "male_stylized"))


def _source_key(b: dict) -> str:
    if (b.get("body") or {}).get("source") == "human":
        # the one mesh's joints follow its HEAD too (identity, attach, size, style): keyed on the body alone, the first
        # head a process evaluated gave every later head of that body its head / landmark / eye joints (solvecams,
        # 2026-10-12: after block_in_start + a new identity in ONE process the build stood 14 mm and 4 % off the
        # model the solve reads; a long-lived MCP server does exactly that)
        from . import onemesh
        return onemesh._tkey(b)
    return json.dumps([b.get("template", "male_stylized"), b.get("body")], sort_keys=True, default=float)


def template_joints(name="male_stylized") -> dict:
    """The body source's joints (centre and .L) as spec joints {name: {"pos", "r"}}, radii from its cross-sections.
    name: a template name or the base dict."""
    b = name if isinstance(name, dict) else {"template": name}
    key = ("joints", _source_key(b))
    if key not in _CACHE:
        tpl = source(b)
        P = tpl["P"]
        out = {}
        J = {k: v for k, v in tpl["J"].items() if not k.endswith(".R")}
        for k, p in J.items():
            d = np.linalg.norm(P - p, axis=1)
            out[k] = {"pos": [round(float(x), 4) for x in p], "r": round(float(np.percentile(d, 0.3)), 4)}
        _CACHE[key] = out
    return json.loads(json.dumps(_CACHE[key]))


CORNEA_BIG = 0.2  # m: the near-flat spheres that cut the iris plane (sag 0.09 mm over the iris; at the other eye, 6 cm
# across, their surface is ~9 mm off its plane: each touches only its own eye)

SEALED_BACK = 0.006  # m: a sealed mouth's slit starts this far behind the lips' front; its bag moves back by it too

SEAL_OVERLAP = 0.0  # m: the contact rows pushed past each other for the FIELD (0.4 mm made the two lip sheets cross:
# small holes in the field along the seam, Tess ts_h7)
SEAL_H = 1.0  # the field's kernel widened this much at a sealed seam (2.0 tried: it blurred the seam's V into bigger holes)
SEAL_H_REACH = 0.0025
SEAL_V = (0.5, 0.25, 0.1)  # share of the vertical gap the 1st, 2nd, 3rd rows out from a sealed contact close (field only)

GNM = "gnm/shape/data/versions/v3_0/gnm_head.npz"  # in the assets pack "gnm" (assets.py; Apache 2.0, see SOURCE.txt)
GNM_CUT = 0.19  # GNM's own frame (Y up): the graft plane's height, above its bib's open edge (0.135), under its chin
GNM_BAND = 0.028
GNM_CHIN = 0.1912  # the mean head's chin landmark height, GNM's frame
EYE_SEAT = 0.0008  # m: the lid rims' clearance outside the eyeball (head.eye_radius, the override, only)
GNM_TILT = 20.0  # degrees
LIP_RING = 2  # GNM: the inner-lip contact ring (landmarks 61-63, 65-67), rings out from the skin's open mouth loop

IRIS_SPOT = 1.83  # an iris paint spot's diameter on the eyeball seen from the front, over its "width" (measured in renders)

# face landmarks as joints (iBUG 68 order, GNM's head_sparse_68: barycentric on its mesh), subject's left = ".L"
LANDMARKS = {"lm_chin": 8, "lm_nose_tip": 30, "lm_nose_base": 33, "lm_nose_bridge": 27, "lm_lip_upper": 51,
             "lm_lip_lower": 57, "lm_mouth_corner.L": 54, "lm_nostril.L": 35, "lm_eye_inner.L": 42,
             "lm_eye_outer.L": 45, "lm_brow_inner.L": 22, "lm_brow_mid.L": 24, "lm_brow_outer.L": 26,
             **{f"lm_jaw_{k}.L": 16 - k for k in range(8)},
             # the lips' outline (outer vermilion edge, the subject's left half) and the inner lip line, for paint
             # outlines: upper peak, upper side, lower side, lower mid-side; inner upper/lower
             "lm_lip_peak.L": 52, "lm_lip_upper_side.L": 53, "lm_lip_lower_side.L": 55, "lm_lip_lower_mid.L": 56,
             "lm_lip_inner_upper.L": 63, "lm_lip_inner_lower.L": 65, "lm_lip_inner_upper": 62,
             "lm_lip_inner_lower": 66}

VERM_N = 17  # points along each edge of the lips' outlines (skin.OUTLINES_DENSE)

FIT_KEYS = ("face_width", "jaw_width", "chin_width", "eye_chin", "eye_mouth", "eye_nose", "nose_width",
            "mouth_width", "eye_seam")

# pose: landmark moves (world m, before the head's scale) solved as the least change of GNM's regional expression
# components; every other landmark is held. Keys -> (landmark ids, direction in GNM's frame: x = the head's left,
# y up, z forward); ".L" landmarks mirror (x flips)
POSE = {"smile": ([48, 54], [0.35, 1.0, -0.15]),  # mouth corners up (and a little out and back)
        "mouth_width": ([48, 54], [1.0, 0.0, 0.0]),  # each corner out
        "lid_upper": ([37, 38, 43, 44], [0.0, -1.0, 0.0]),  # upper lid margins down (closes the eye)
        "lid_lower": ([40, 41, 46, 47], [0.0, 1.0, 0.0]),  # lower lid margins up (a smile's lower lid)
        "mouth_raise": (list(range(48, 68)), [0.0, 1.0, 0.0]),  # the whole mouth up (a shorter philtrum)
        "brow_inner": ([20, 21, 22, 23], [0.0, 1.0, 0.0]),  # inner brow up (open, kind; negative: a frown)
        "brow_outer": ([17, 18, 25, 26], [0.0, 1.0, 0.0])}  # outer brow up (negative: drooping, relaxed)
POSE_HOLD = 0.35  # weight of holding every landmark not moved (the rest of the face stays put)

HOLLOW_RADIUS = 0.016  # m: a hollow cheek's reach
JAW_RADIUS = 0.009     # m: a bony jaw corner's reach (crisp: a soft one is a jowl)
JAW_TUCK_RADIUS = 0.014  # m: the tucked under-jaw's reach
HOOD_FORWARD = 0.4  # a hooded lid's fold comes down and this share of that forward, over the lid
HOOD_REACH = 0.5    # its fold's height: this share of the lid-to-brow distance (and its centre 0.45 of the way up)

JAWLINE_RADIUS = 0.034   # m: how far from the old jaw line the skin still follows its move
JAWLINE_SIGMA = 0.014    # m: along the line, each point follows the stretch of jaw line nearest it
JAWLINE_TUCK = 0.016     # m: depth of the band under the new border / behind the new ramus that is drawn in
JAWLINE_SMOOTH = 2       # rounds of smoothing of the move over the mesh

LEAN_RADIUS = 0.03    # m: how far from the jaw's border the thinning reaches
LEAN_KEEP = 0.004     # m: the border itself (this near the line) keeps its place: the bone doesn't thin

EAR_BLEND = 0.004  # m: the band at an ear's root over which its turn fades in (the skin round it is untouched)
EAR_ROOT = 0.003   # m: ear vertices this near the rest of the skin are its attachment

PLANES_KEEP = {("nose_region",): 10, ("upper_lip_region", "lower_lip_region", "chin_region"): 30}  # features _planes
# leaves alone (group names: feather rounds); the lips and chin fade out wide: feathered at 10 the kept muzzle met the
# pushed cheek in a crease (a smile fold beside the mouth)

MOUTH_PUSHED = 0.001  # m: lips a style moved this far off GNM's own surface no longer fit GNM's teeth (the kit's interior)
MOUTH_PARTED = 0.0015  # m: inner lips further apart than this = an open mouth (the bag is cut; closed, a fill)
EYE_PART_VOXEL = 0.00025   # m: the eyes part's own voxel (see implied_parts)
# GNM's two tooth rows are separate parts: in one part's field the rows touch at the bite and were meshed as ONE
# piece, so jawOpen (the lower row's move, the upper row's none) stretched the triangles joining them into shards.
# min_triangles per row: at 600 for both rows a decimated row bulged out through the closed lips; the export now takes
# GNM's own quads for the rows (asset.own_mouth_meshes, 2828 triangles a row) and the floor keeps them whole.
TEETH_PARTS = ("teeth", "teeth_lower")  # (upper row, lower row), each with its gums
MOUTH_PARTS = {"teeth": {"color": [0.86, 0.83, 0.74], "roughness": 0.3, "voxel": 0.0004, "min_triangles": 4000},
               "teeth_lower": {"color": [0.86, 0.83, 0.74], "roughness": 0.3, "voxel": 0.0004, "min_triangles": 4000},
               "tongue": {"color": [0.62, 0.46, 0.43], "roughness": 0.45, "voxel": 0.0008, "min_triangles": 4000}}
GUM_COLOR = [0.68, 0.32, 0.33]
BAG_COLOR = [0.2, 0.07, 0.07]
MOUTH_SUBDIVIDE = 2  # Catmull-Clark rounds on GNM's teeth / tongue before their field (edges ~2 mm -> ~0.5 mm)

TEETH_CROWN_GROW = 1.35  # GNM's crowns are ~7 mm tall where a front incisor's is ~10.5 (adult mean); reviews expr_r7 /
# r8 and the coordinator: "small pegs", the reference's incisors about twice the height below the lip
TEETH_ARC = 0.0008  # m: the biting edge rises this much from the centrals to the canines (16 mm out), on a parabola
TEETH_LEVEL_BAND = 0.0012  # m across: the neighbourhood a vertex reads its tooth's edge from
TEETH_WIDEN = 1.05  # the arch across (GNM's 27 mm at 6 mm behind the front; inter-canine ~34 mm)

MOUTH_SHELL = {"teeth": 0.003, "teeth_lower": 0.003, "tongue": 0.008}  # m: how deep under GNM's surface a piece's solid reaches

LIP_CLOSE = {"n": 40, "span": 0.97, "x": 15, "gap": 0.15, "overlap": 0.2, "lead": 0.3, "hold": 0.3, "corner": 0.6, "iters": 4}
_LIPC: dict = {}

# The modules this one was split into (C417). What hashed base.py by its file name (skin_read, skin_look) hashes these too.
MODULES = ("base_imls", "base_identity", "base_head_shape", "base_gnm_parts", "base_gnm_head", "base_measures",
           "base_tubes", "base_surface", "base_implied")
