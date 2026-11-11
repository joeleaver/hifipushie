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

Where the code is (split by responsibility, C416): this module holds the constants, `source` and `template_joints`.
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


GNM = "gnm/shape/data/versions/v3_0/gnm_head.npz"  # in the assets pack "gnm" (assets.py; Apache 2.0, see SOURCE.txt)
GNM_CUT = 0.19  # GNM's own frame (Y up): the graft plane's height, above its bib's open edge (0.135), under its chin
GNM_BAND = 0.028
GNM_CHIN = 0.1912  # the mean head's chin landmark height, GNM's frame
EYE_SEAT = 0.0008  # m: the lid rims' clearance outside the eyeball (head.eye_radius, the override, only)
GNM_TILT = 20.0  # degrees
LIP_RING = 2  # GNM: the inner-lip contact ring (landmarks 61-63, 65-67), rings out from the skin's open mouth loop



# The modules this one was split into (C416). What hashed base.py by its file name (skin_read, skin_look) hashes these too.
MODULES = ("base_imls", "base_identity", "base_head_shape", "base_gnm_parts", "base_gnm_head", "base_measures",
           "base_tubes", "base_surface", "base_implied")
