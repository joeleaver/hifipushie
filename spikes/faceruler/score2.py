"""score2.py: the driving test's PASS rule, with its two known flaws fixed (faceruler; gnmdrive2's verdict, point 5).

OLD  region closed >= 0.4  AND  ID distance closed >= 0.25  AND  face error <= 1.1 x the start's.
NEW  region closed >= 0.4  (unchanged)
     AND perceived: ID distance closed >= 0.25; a pair whose change includes the SKULL may pass instead on the head's
         OUTLINE (front + profile silhouettes: the mean distance between the head's outline and the target's, closed
         >= 0.4) with the ID distance no more than 10 % worse: the ID nets crop the face and do not see the vault
         (oracle: region 0.7-0.8 closed, ID -0.04 / -0.12).
     AND face error <= max(1.1 x start, start + 0.5 mm): under ~2 mm rms a 10 % band is 0.1-0.2 mm, below anything
         visible (s5_03: region 0.61, ID 0.59, face 1.8 -> 2.1 mm: failed on 0.12 mm).
grade(cA, cB, [c...], regions) -> [{region, id, face, outline, pass_old, pass}]."""
import numpy as np

import drv
import score as sc
from hifipushie import face_ruler as fr

_CAMS = {}


def _masks(c):
    out = []
    for k in ("front", "profile"):
        if k not in _CAMS:
            _CAMS[k] = fr.camera(k, px=360)
        _, ps = fr.clay(fr.gnm_head(c), _CAMS[k], passes=True)
        out.append(ps["part"] >= 0)
    return out


def outline_dist(ma, mb):
    """mean distance (mm) between two heads' outlines: the area between them over the target outline's length."""
    d = []
    mm = 300.0 / 360
    for a, b in zip(ma, mb):
        edge = b & ~(np.roll(b, 1, 0) & np.roll(b, -1, 0) & np.roll(b, 1, 1) & np.roll(b, -1, 1))
        d.append((a ^ b).sum() / max(edge.sum(), 1) * mm)
    return float(np.mean(d))


def grade(cA, cB, cs, regs):
    F = sc.face_basis()
    e0 = drv.zone_err(cA, cB)
    f0 = float(np.linalg.norm(F @ (cB - cA)))
    ids = sc.idist([cA] + list(cs), cB)
    mB = _masks(cB)
    o0 = outline_dist(_masks(cA), mB)
    res = []
    for c, i1 in zip(cs, ids[1:]):
        e1 = drv.zone_err(c, cB)
        f1 = float(np.linalg.norm(F @ (cB - c)))
        rc = float(np.mean([1 - e1[f"R:{r}"] / e0[f"R:{r}"] for r in regs]))
        idc = 1 - i1 / ids[0]
        oc = 1 - outline_dist(_masks(c), mB) / o0
        old = bool(rc >= 0.4 and idc >= 0.25 and f1 <= 1.1 * f0)
        seen = idc >= 0.25 or ("skull" in regs and oc >= 0.4 and idc >= -0.1)
        new = bool(rc >= 0.4 and seen and f1 <= max(1.1 * f0, f0 + 0.5))
        res.append({"region": round(rc, 3), "id": round(float(idc), 3), "face": [round(f0, 2), round(f1, 2)],
                    "outline": round(float(oc), 3), "pass_old": old, "pass": new})
    return res
