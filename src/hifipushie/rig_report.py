"""The rig's report, and rig_bones. Part of rig (rig.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import rig
from .rig_head import head_check, head_field
from .rig_humanoid import humanoid
from .rig_twist import chains, twist_check

def report(spec: dict, bones: list[dict], V: np.ndarray, F: np.ndarray, J: np.ndarray, W: np.ndarray) -> list[str]:
    """The rig tool's numbers: each twist chain's test and the head's."""
    names = [b["name"] for b in bones]
    out = []
    tests = [("RightHand", 75.0), ("RightHand", 105.0), ("RightArm", 60.0), ("RightFoot", 40.0),
             ("RightUpLeg", 40.0)]
    tw = [b for b in bones if b.get("twist")]
    if rig.PREFIX + "RightHand" in names:
        out.append("twist tests (a driver rolled about its limb; twist = how far the skin has turned by station "
                   "along the segment, joint to joint; area = the worst cross-section against rest):")
        for drv, deg in tests:
            if rig.PREFIX + drv not in names:
                continue
            chain = [b for b in tw if b["twist"]["driver"] == rig.PREFIX + drv]
            for drive in ((True, False) if chain and drv == "RightHand" and deg == 75.0 else (bool(chain),)):
                r = twist_check(bones, V, F, J, W, rig.PREFIX + drv, deg, drive)
                if not r["twist"]:
                    continue
                follow = drv.endswith(rig.ROLL_OF_PARENT)
                left = r["at_end"] if follow else r["at_start"]
                where = ("the wrist" if "Hand" in drv else "the ankle") if follow else \
                    ("the shoulder" if "Arm" in drv else "the hip")
                kind = f"{len(chain)} twist bones driven" if drive else \
                    ("twist bones NOT driven" if chain else "no twist bones")
                bad = " <- CANDY WRAPPER" if r["area_min"] < 0.8 or (r["step"] or 0) > 0.6 * deg else ""
                out.append(f"  {drv} {deg:g} deg, {kind}: twist {' '.join(f'{x:.0f}' for x in r['twist'])}; "
                           f"{abs(left) if follow else abs(left):.0f} deg {'left at' if follow else 'turned at'} "
                           f"{where}, largest step {r['step']:.0f} deg, area min {r['area_min']:.2f}, triangle "
                           f"quality against rest: worst 1% {r['tri_p1']:.2f}, worst {r['tri_min']:.2f}{bad}")
    hc = head_check(bones, V, J, W)
    if hc:
        hf = head_field(spec, bones)
        out.append(f"head (rigid by {hf['how'] if hf else 'nothing: rig.rigid_head is off'}); front of the face by "
                   f"height over the Head joint, Head turned {hc['deg']:g} deg:")
        out += [f"  {r['rel']:+.1f} head (z {r['z']:.3f}): Head {r['head']:.2f} Neck {r['neck']:.2f} "
                f"clavicles/arms {r['arms']:.2f}, {r['lag_mm']:.1f} mm behind a rigid head" for r in hc["rows"]]
    return out


def rig_bones(spec: dict) -> list[dict]:
    r = spec.get("rig") or {}
    if r.get("type") == "chains":
        return chains(spec)
    b = humanoid(spec)
    if b is None:
        raise ValueError("no humanoid joints (pelvis, chest, neck, head, shoulder/elbow/wrist/hip/knee/ankle .L/.R): "
                         "give spec[\"rig\"] = {\"type\": \"chains\", \"root\": ..., \"chains\": {...}}")
    return b
