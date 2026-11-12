"""An armature and skin weights from the spec's skeleton, for export_asset(rig=True).

Every additive bone of the (mirrored, kit-expanded) spec becomes an armature bone. The joint graph is walked
breadth first from a root joint ("pelvis", "hips" or "root" if there is one, else the graph's centre), which
orients each bone parent -> child: its head is the joint it was reached from (the pivot it turns about), its parent
the bone that reached that joint. Pieces of the skeleton not joined to the rest (a buckle, a tail made separately)
hang from the bone nearest to them.

Skin weights come from the bones' own round cones: at each vertex, every bone's exact distance (`sdf.field_at` of
that one primitive: thickness counts, so a thick thigh claims the flesh a thin bone axis would lose), weighted
exp(-(d - d_nearest) / falloff) with the falloff half the radius of the thinner of the bone and the nearest one (the
fat torso's own radius spread it halfway down the upper arm: the raised arm bent mid-bicep), among the nearest bone's
family (two steps of parents, children, siblings), smoothed over the mesh, the four strongest kept and normalised.
Where a limb continues through a joint (collar -> upper arm -> forearm), each cone stops at the plane bisecting the
two bones, so the collar's round end doesn't claim the top of the upper arm. Blobs (a belly, a head) go with the bones
they sit on and aren't cut. Parts (clothes, eyes) are skinned to the same bones. A limb fused to the body (the
goblin's arms blend into its belly) webs when raised whatever the weights: model limbs clear of the torso.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at rig.NAME: C422). rig_model: the modelling rig: the skeleton from a spec, weights against its flesh,
settling and smoothing, `pose`. rig_humanoid: the export rig: a clean, retargetable humanoid skeleton over the
modelling one. rig_bend: bend helpers (half-angle joints): bend_on, the arc frames, limb girth, the arc and shared
bends. rig_twist: twist bones: counts, the spread of twist, rolls, drive and check; chains; the test pose. rig_flesh:
the flesh a rig weights against: cone pieces and the flesh tree. rig_head: the rigid head: its field, the rigid set,
what lies near it, the head check. rig_skin: skinning: part weights, skin_parts, the cover over the skin, dropped
joints, skin_mesh, rig_weights. rig_report: the rig's report, and rig_bones.
"""
from __future__ import annotations

import numpy as np

from .spec import resolve_point
from . import moved

ROOTS = ("pelvis", "hips", "root", "hip")
FALLOFF = 0.5  # weight falls by e over this fraction of a bone's radius past the nearest bone
SMOOTH = 10  # rounds of averaging weights with neighbouring vertices
WORN_SMOOTH = 0  # rounds of the same over a worn part's own mesh after it read the skin's weights (parts.<p>.rig_smooth). 0 since
# 2026-10-07: layers smoothed each over its own mesh drift apart (a jacket's hem toward the pelvis, the trousers under it
# on down the thigh) and cross when posed: s0urc3's seated Garrett. What 6 rounds were for (a collar's two faces reading
# two places) is cured at the lookup (rig_template.from_surface two_sided).
SOFT = ("super", "loft", "sheet")  # the soft primary forms (softforms.py, sheet.py): flesh like any blob

CHAIN_ROOT_CAP = True

# ---- the export rig: a clean, retargetable skeleton over the modelling one ----------------------------------------
# The spec's bones are for modelling (a tusk, lip chains, a shorts leg are bones); the exported armature is a
# separate, standard one fitted to the joints: spec["rig"] = {"type": "humanoid" (default when the usual joints
# exist) | "chains", "joints": {rig joint: spec joint or [x, y, z]} (overrides), "chains": {...} (type chains)}.
# Humanoid: Mixamo's names and hierarchy (mixamorig:Hips ... LeftHandIndex4), which Mixamo animations, Unity's
# Humanoid avatar and Unreal's IK retargeter map without a hand-made mapping. Chains: a root and named chains of
# joints (spine, neck, tail, legs), each bone "<chain>_01", "<chain>_02"...
# Skin weights are the modelling skin (`weights`: cones and blobs, family-limited, smoothed) handed on to the rig
# bones lying along each modelling bone (split along it where several do: the one spine bone feeds Spine, Spine1,
# Spine2); a modelling bone with no rig bone along it (a tusk, an ear) goes to the nearest one (Head).
PREFIX = "mixamorig:"
FINGERS = ("Index", "Middle", "Ring", "Pinky")


def _joint(s: dict, j):
    return np.asarray(j, float) if isinstance(j, (list, tuple)) else resolve_point(s, j)


# ---- bend helpers (half-angle joints) -----------------------------------------------------------------------------
# Linear blend skinning across a hinge averages two rotations: at 90 deg the skin between them collapses toward the
# chord (the elbow's and knee's flat "squared" corner, the pinched crease, the deltoid that flattens when the arm
# rises: rig_r1's review). Games add a HELPER joint at the hinge that turns HALF the joint's rotation (Unreal's
# "corrective" / "half-angle" bones, Maya's "twist/bend helpers"): the blend zone's skin rides it, so it is carried
# round the arc instead of across the chord. A leaf bone after the Mixamo set (and after the twist chains), a child of
# the joint's PARENT, standing at the joint's head; driven: local rotation = slerp(identity, the joint's local rotation
# from rest, share). Undriven it sits on its parent: the skin is what it was only if the driver is at rest, so an
# engine MUST drive it (the json's rig.bend and node extras.hifipushie_bend carry driver and share).
BEND = {"ForeArm": "Arm", "Leg": "UpLeg", "Arm": "Shoulder", "UpLeg": "Hips"}  # joint: its parent
BEND_SHARE = 0.5   # the helper turns this share of its joint's rotation
BEND_TAKE = 1.0    # share of a vertex's overlap min(w parent, w joint) x 2 the helper takes (the blend zone)

# Arc weights (2026-10-14, rig_r3 STUCK on the flat knee front, the back-of-knee pinch, the seated buttock bag and the
# deltoid tube). The helpers above only took MakeHuman's own blend zone (2 x min(w parent, w joint)): a knee's zone is a
# few cm wide and the same front and back, so at 90 deg the front still ran straight across the chord. A rigger paints a
# hinge by SIDE: the outer skin (knee front, olecranon, buttock, armpit) is a wide zone that must be carried round the
# arc; the inner skin (back of the knee, crook of the elbow, groin, top of the shoulder) a narrow one that folds into a
# crease. So the hinge's skin is repainted from geometry: across the joint (axial s from the pivot along the limb) a
# vertex's turn phi goes 0 -> 1 over a zone whose half width depends on its side (outer wide, inner narrow); phi 0..0.5
# blends parent -> helper (half angle), 0.5..1 helper -> joint. The skin is turned round the pivot in two 45 deg steps
# at 90 (radius kept to cos 22.5 = 92 %, LBS over one blend: 71 %, the chord). Purely geometric, so every part (skin,
# briefs, socks) gets the same weights where it lies: the garment rides the skin under it.
#   joint: (outer side in rest (world dir) or "rest" (the convex side of the rest bend), zone half width outer, inner,
#           radial reach (all x the joint's own segment length), axis "hinge" (bisector) | "ball" (the joint's bone))
BEND_ARC = {"ForeArm": ("rest", 0.13, 0.05, 0.30, "hinge"),
            "Leg": ((0.0, -1.0, 0.0), 0.12, 0.04, 0.28, "hinge"),
            "UpLeg": ((0.0, 1.0, 0.0), 0.20, 0.10, 0.36, "ball"),
            "Arm": ((0.0, 0.0, -1.0), 0.18, 0.16, 0.36, "ball")}  # a narrow top crease kinked the raised shoulder
BEND_WEIGHTS = "arc"  # "arc" (BEND_ARC) | "overlap" (the helpers take MakeHuman's own zone, before 2026-10-14)
ARC_MID = 0.04  # m: the side mask runs from 0 to 1 over this across the midline (half each side at the crotch)
ARC_AXIAL = 3.0  # x the outer half width: past it along the limb (and one more) a vertex keeps its weights
ARC_CHILD = {"ForeArm": "Hand", "Leg": "Foot", "UpLeg": "Leg", "Arm": "ForeArm"}
# The zone is sized by the segment's length, which is a person's proportion (a thigh ~5x as long as it is thick). A
# stylised limb can be shorter than it is thick (Puddles' thigh: 5.5 cm long, 6.3 cm round): its zone (2 cm reach)
# missed the skin, the raw distance blend carried the thigh's weight 13 cm up the belly and seated, the belly tore
# into a web. A limb whose girth (`limb_girth`) is over ARC_GIRTH x its length is a STUB: its zone's unit is
# girth / ARC_STUB_UNIT instead. A person's limbs (girth / length ~0.2) are as before.
ARC_GIRTH = 0.25
# A STUB limb (its unit raised by its girth) starts inside the body's mass, so two more rules hold for it (a person's
# limbs, unit = length, are untouched): the zone has no radial reach (past it the distance blend had carried the
# thigh's weight 9-18 cm round its axis up the belly), and skin farther from the limb's axis than ARC_BODY (from, to)
# x its girth is the parent's (the seat below and behind a pig's hip is body, not thigh: it swung forward and tore).
ARC_BODY = (1.1, 2.5)
ARC_ROOTS = ("UpLeg", "Arm")  # only where a limb leaves the body: a stub's knee is an ordinary hinge (as a stub too,
#                              its zone covered the whole shin and the seat behind it went with the knee)
ARC_STUB_UNIT = 0.1  # a stub's zone unit is its girth / this. Swept on Puddles seated (edges stretched > 3x; seat
#  skin behind the thigh moved): unit = length (before stubs) 2442; 0.1 + ARC_BODY (1.1, 2.5) 60 (48 mm). From < 1.1 the leg's own skin (at ~1x) went to the hips: (0.5, 1.5) 2 (0 mm) was the thigh half turned

# ---- twist bones ------------------------------------------------------------------------------------------------
# A limb segment's roll about its own axis is not a rotation of one joint in a person: pronation is the radius
# turning over the ulna along the whole forearm, and the upper arm's roll is taken up at the shoulder, not by the
# deltoid's skin. With one bone per segment the whole roll lands on one joint (a hand turned 75 deg was wrung at the
# wrist: s0urc3's Garrett). So each segment gets a TWIST CHAIN, as Unreal's mannequin has (upperarm_twist_01/02,
# lowerarm_twist_01/02, thigh_twist, calf_twist) and VRM's roll constraint describes: extra LEAF bones, children of
# the segment's own bone, standing at stations along it, each turning about the segment's axis by a share of a
# driver's roll.
#   follow  (forearm, calf): the driver is the segment's CHILD (Hand, Foot). Share k/n at station k/n: nothing at the
#           elbow, the hand's whole roll at the wrist, so the wrist joint itself doesn't twist.
#   counter (upper arm, thigh): the driver is the segment's OWN bone. Share -(1 - (k-1)/n) at station (k-1)/n: the
#           bone at the shoulder turns back the whole of the arm's roll (the deltoid stays with the clavicle), the
#           elbow end follows the bone.
# The Mixamo set is untouched: the twist bones come after it in the list, nothing hangs from them, and with no
# driver they sit still on their parent, where the skin is exactly what it was without them (their weights are their
# parent's weight shared out along the segment, `_spread_twist`). An engine drives them (glTF has no constraints):
# node extras "hifipushie_twist" and the export json's rig.twist carry driver, axis and share.
TWIST = {"Arm": ("counter", "arm", "ForeArm"), "ForeArm": ("follow", "forearm", "Hand"),
         "UpLeg": ("counter", "upleg", "Leg"), "Leg": ("follow", "leg", "Foot")}
# Linear blend skinning between two stations turned apart by d loses cos^2(d / 2) of a section's area half way, so
# the count follows how far a segment rolls. Upper arm: two, as Unreal's mannequin (60 deg: 0.93 of the area kept).
# Forearm: three: a hand turns 75 deg palm down and 105 in gestures; measured at 105 on the MakeHuman body, none
# 0.49, two 0.80, three 0.87. Legs: one each (a foot or thigh rolls 30-45 deg: 0.88).
TWIST_DEFAULT = {"arm": 2, "forearm": 3, "upleg": 1, "leg": 1}
TWIST_MAX = 4
TWIST_MERGE = 3.0  # at a fifth bone: a split whose smaller half is under this x the smallest weight goes back together
ROLL_OF_PARENT = ("Hand", "Foot")  # their "roll" is about the segment they end

PART_WEIGHTS = ("surface", "around", "distance")
TWO_SIDED = True  # worn parts read the skin they lie on from both their faces (rig_template.from_surface)
WORN_WEIGHTS = "surface"  # what a worn part reads without parts.<p>.rig_weights

COVER_REACH = 0.03  # m: skin with a worn part's surface this near, outward of it, is covered by it
COVER_OUT = True    # the hand-over lies on the visible skin beside the cover (else on the covered skin under it)
COVER_EASE = 0.02   # m in from where the cover starts over which covered skin hands over to its cover's weights
COVER_SMOOTH = 4    # rounds of smoothing the share over the mesh (spec.rig.rigid_head.cover.smooth)

ATTACH = 0.08  # m: the length over which a part hands over to the bound part it is attached to (parts.<p>.rig_attach)


# ---- the rigid head -----------------------------------------------------------------------------------------------
# A skull doesn't bend: riggers weight the whole head (cranium, face, jaw, and everything in it: eyes, teeth, tongue)
# 1.0 to the head joint and put the falloff to the neck on the throat, under the jawline. Distance-based weights
# don't: the chin hangs in front of the neck, as near the neck's and the clavicles' bones as the skull's (Garrett's
# chin was Head 0.42 / Neck 0.42 / shoulders 0.16 and followed a head turn half way; the goblin's 0.34 / 0.32 / 0.33).
# `head_field` says how much of the head a point is (1 = rigid); `_rigid_head` blends each vertex's weights toward
# Head by it. Three sources, in order:
#   landmarks  a GNM head's lm_chin / lm_jaw_*: the floor is the mandible's lower border from the chin back to the
#              jaw's angle, level behind it, dropped HEAD_UNDER (the soft skin under the chin moves with the jaw);
#   flesh      modelling prims: a point is head where the Head bone's flesh (skull, jaw, face kit) is no farther than
#              any other bone's; the falloff runs by how much farther it is;
#   generic    a base body without landmarks: the landmark floor at a typical head's proportions from the rig joints.
HEAD_BAND = 0.12   # the falloff's height below the floor, x the head's size (Head joint -> HeadTop_End): ~3 cm
HEAD_FALL = 0.44   # on a base body (a floor by height): the falloff's height, ~11 cm = the neck's length, as a rigger
#                    paints it (the head's weight fades down the whole neck; a narrow band is a hinge). With
#                    HEAD_NEAR, bare human (15k), Head alone: skin fold p99 / max at a 33 deg turn 24.7 / 159 ->
#                    9.7 / 26 deg, at a 25 deg nod 35.7 / 150 -> 14.1 / 31 (renders wc_throat_fall_gnm.png). Either one
#                    alone did half of it. History: at 3 cm a Head-only turn of 33 deg
#                    sheared the throat into a shelf under the jaw (skin fold p99 40 deg on the bare human, 20 on the
#                    golfer; at 5 cm 24 / 12, nod 56 -> 43). Longer on the FRONT only changed nothing: the fold is at
#                    the sides and the nape. spec.rig.rigid_head.band sets it in metres.
HEAD_OCCIPUT = 0.1  # x head size (neck joint -> head top, ~34 cm on a MakeHuman body) under the Head joint: the floor's
#                    height at the nape, the skull's base. Golfer, nod 25 deg Head-only: nape skin by the collar's top
#                    Head 0.98 -> 0.86, swung past the collar's back by +8.4 mm (38 vertices) -> -2.9 (none); shared with
#                    Neck -4.8 -> -11.5. Bare human folds unchanged (turn p99 11.7 -> 10.7, nod 14.5 -> 15.8). Higher
#                    (0.05, 0) clears more and folds the bare nape (nod p99 17-19, max 40-59); spec.rig.rigid_head.occiput
HEAD_BACK = 0.3    # x head size behind the Head joint where the floor reaches it
HEAD_NAPE = 1.0    # x the falloff's height at the nape (behind the Head joint); spec.rig.rigid_head.nape
HEAD_SHORT = 0.2   # the falloff's height outside the neck's column (what HEAD_FALL was): ~5 cm
HEAD_COLUMN = (0.36, 0.62)  # the neck's column: within 0.36 x head size (9 cm) of the Neck -> Head line the long
#                    falloff counts in full, past 0.62 (15.5 cm) not at all. (0.26, 0.46) cut into the neck's own
#                    sides (bare human turn p99 20 deg, a 127 deg crease); wider gains nothing and creases at 160.
HEAD_NEAR = 0.32   # on a base body: the band round face-shape vertices (`rigid_near`), ~8 cm (kit characters keep
#                    HEAD_BAND: a big jaw's field reaches the goblin's chest)
HEAD_UNDER = 0.04  # the floor's drop under the jaw's border, x the head's size: ~1 cm
HEAD_PART = 0.9    # a part this much head on average is all head (teeth, tongue, eyes, lashes, brows)
HEAD_WORN = 0.5    # a part other than the skin and less head than this is worn on the body: no head rule (a collar);
#                    parts.<p>.rig_head = true | false says so outright, spec.rig.skin_part names the skin ("body")
NEAR_SHORT = 0.375  # x rigid_near's band: within it the band counts in full, past it no more than the head field
MOVED = (5e-4, 3e-3)  # m: a vertex a face shape moves this far is a little / wholly the head's (`rigid_near`)


def _segments(rb: list[dict]):
    """Each weight-carrying rig bone as a segment: its head to its (first non-end or only) child's head."""
    kids: dict = {}
    for i, b in enumerate(rb):
        if b["parent"] >= 0 and not b.get("twist"):
            kids.setdefault(b["parent"], []).append(i)
    seg = {}
    for i, b in enumerate(rb):
        if b["end"] or b.get("noweight") or b.get("twist") or b.get("bend"):  # twist bones take their share after (_spread_twist)
            continue
        if "tail" in b:
            seg[i] = (b["head"], b["tail"])
            continue
        ch = kids.get(i, [])
        if ch:  # the child that continues the chain: the one straightest ahead (Spine2 -> Neck, not a clavicle)
            prev = b["head"] - rb[b["parent"]]["head"] if b["parent"] >= 0 else np.array([0, 0, 1.0])
            c = max(ch, key=lambda k: np.dot(rb[k]["head"] - b["head"], prev) / (np.linalg.norm(rb[k]["head"] - b["head"]) + 1e-9))
            seg[i] = (b["head"], rb[c]["head"])
        else:
            seg[i] = (b["head"], b["head"] + 1e-3)
    return seg


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("rig_model", "rig_humanoid", "rig_bend", "rig_twist", "rig_flesh", "rig_head", "rig_skin", "rig_report")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
