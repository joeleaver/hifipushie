"""The export rig: a clean, retargetable humanoid skeleton over the modelling one. Part of rig (rig.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import rig
from . import sdf
from .spec import compile_prims, expand_mirror
from .rig import _joint
from .rig_bend import _add_bend, bend_on
from .rig_twist import _add_twist, twist_counts

def _surface_along(spec: dict, p: np.ndarray, d: np.ndarray, reach: float) -> np.ndarray:
    """Where a ray from inside the body leaves it (the top of the head, the tip of the toes)."""
    prims = [q for q in compile_prims(spec) if q.part == "body"]
    t = np.linspace(0, reach, 200)
    f = sdf.field_at(prims, p + t[:, None] * d, clip=False)
    out = np.flatnonzero(f > 0)
    return p + (t[out[0]] if len(out) else reach) * d


def humanoid(spec: dict) -> list[dict] | None:
    """The Mixamo skeleton fitted to the spec's joints: [{"name", "head", "parent" (index), "end": bool}] (end
    joints like HeadTop_End carry no weight), or None if the usual joints aren't there."""
    s = expand_mirror(spec)
    J = s["joints"]
    over = (spec.get("rig") or {}).get("joints") or {}
    need = ["pelvis", "chest", "neck", "head"] + [f"{j}.{side}" for j in ("shoulder", "elbow", "wrist", "hip", "knee",
                                                                            "ankle") for side in "LR"]
    if not all(j in J for j in need) and not over:
        return None
    P = {k: _joint(s, v) for k, v in over.items()}

    def at(name, default):
        return P.get(name, default)
    pelvis, chest, neck, head = (_joint(s, j) for j in ("pelvis", "chest", "neck", "head"))
    sh_z = 0.5 * (_joint(s, "shoulder.L")[2] + _joint(s, "shoulder.R")[2])
    t = float(np.clip((sh_z - chest[2]) / max(neck[2] - chest[2], 1e-6), 0.2, 0.8))
    bones = []

    def add(name, pos, parent, end=False, src="placed"):
        bones.append({"name": rig.PREFIX + name, "head": np.asarray(at(name, pos), float), "end": end,
                      "src": "spec rig.joints" if name in P else src,
                      "parent": next(i for i, b in enumerate(bones) if b["name"] == rig.PREFIX + parent) if parent else -1})
    add("Hips", pelvis, None, src="pelvis")
    add("Spine", pelvis + (chest - pelvis) / 3, "Hips")
    add("Spine1", pelvis + 2 * (chest - pelvis) / 3, "Spine")
    add("Spine2", chest, "Spine1", src="chest")
    collar = chest + t * (neck - chest)  # the spine at shoulder height: where the clavicles start
    # Where Neck and Head pivot. Kit characters: the "neck" joint is the skull's base (the head bone starts there), so
    # Head sits on it and Neck at shoulder height. A template may say otherwise (`rig` in its dict: {rig joint: [joint
    # a, joint b, t]}): MakeHuman's "neck" joint is the neck's BASE (C7) and its head bone starts 63% of the way to
    # the "head" joint; Head on the "neck" joint there pivoted the head at the bottom of the neck, 10 cm low, and the
    # whole neck's turn had to happen in the skin under the jaw.
    hint = {}
    if spec.get("base"):
        from . import base as basemod
        hint = basemod.source(spec["base"]).get("rig") or {}

    def hinted(name, default):
        if name in hint:
            a, b, f = hint[name]
            return _joint(s, a) + float(f) * (_joint(s, b) - _joint(s, a))
        return default
    add("Neck", hinted("Neck", collar), "Spine2", src="template" if "Neck" in hint else "placed")
    add("Head", hinted("Head", neck), "Neck", src="template" if "Head" in hint else "neck")
    up = (head - neck) / max(np.linalg.norm(head - neck), 1e-9)
    add("HeadTop_End", _surface_along(spec, head, up, 2 * np.linalg.norm(head - neck) + 0.5), "Head", True)
    for side, S in (("L", "Left"), ("R", "Right")):
        j = {k: _joint(s, f"{k}.{side}") for k in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle")}
        add(f"{S}Shoulder", collar + 0.2 * (j["shoulder"] - collar), "Spine2")
        add(f"{S}Arm", j["shoulder"], f"{S}Shoulder", src=f"shoulder.{side}")
        add(f"{S}ForeArm", j["elbow"], f"{S}Arm", src=f"elbow.{side}")
        add(f"{S}Hand", j["wrist"], f"{S}ForeArm", src=f"wrist.{side}")
        # the hand kit's chains, or a base body's own (the template's names: finger1 = index .. finger4 = pinky)
        kit = f"hand_th_0.{side}" in J or f"hand_f1_0.{side}" in J
        th = (lambda k: f"hand_th_{k}.{side}") if kit else (lambda k: f"thumb_{k}.{side}")
        fg = (lambda f, k: f"hand_f{f}_{k}.{side}") if kit else (lambda f, k: f"finger{f}_{k}.{side}")
        thumb = [th(k) for k in range(4)]
        if all(x in J for x in thumb):
            for k, x in enumerate(thumb):
                add(f"{S}HandThumb{k + 1}", _joint(s, x), f"{S}Hand" if k == 0 else f"{S}HandThumb{k}", k == 3, x)
        fingers = sorted((f for f in range(1, 6) if all(fg(f, k) in J for k in range(4))),
                         key=lambda f: np.linalg.norm(_joint(s, fg(f, 0)) - _joint(s, thumb[0]))
                         if thumb[0] in J else f)
        names = rig.FINGERS if len(fingers) >= 4 else ("Index", "Middle", "Ring")[:len(fingers) - 1] + ("Pinky",) \
            if len(fingers) > 1 else ("Index",)
        for f, fn in zip(fingers, names):
            for k in range(4):
                add(f"{S}Hand{fn}{k + 1}", _joint(s, fg(f, k)),
                    f"{S}Hand" if k == 0 else f"{S}Hand{fn}{k}", k == 3, fg(f, k))
        add(f"{S}UpLeg", j["hip"], "Hips", src=f"hip.{side}")
        add(f"{S}Leg", j["knee"], f"{S}UpLeg", src=f"knee.{side}")
        add(f"{S}Foot", j["ankle"], f"{S}Leg", src=f"ankle.{side}")
        toe = _joint(s, f"toe.{side}") if f"toe.{side}" in J else j["ankle"] + np.array([0, -0.1, -0.05])
        add(f"{S}ToeBase", toe, f"{S}Foot", src=f"toe.{side}")
        fwd = toe - j["ankle"]
        fwd[2] = 0
        fwd /= max(np.linalg.norm(fwd), 1e-9)
        add(f"{S}Toe_End", _surface_along(spec, toe, fwd, 0.5), f"{S}ToeBase", True)
    return _add_bend(_add_twist(bones, twist_counts(spec)), bend_on(spec))
