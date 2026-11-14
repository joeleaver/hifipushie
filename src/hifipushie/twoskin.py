"""A solid made of two skins: its front surface and its back surface, as two height maps over one view plane,
inside its outline. The shape a creature's head (or its trunk) has when it is built straight from what the
reference pictures show: the front picture's surface, the back picture's, and the outlines.

Over the plane (u to the right, v down, t towards the front viewer) the solid is, inside the footprint `foot`
(a signed distance, metres, negative inside): everything between the front skin t = front(u, v) and the back skin
t = -back(u, v) (`back` is measured towards the back viewer). Where the skins do not meet at the outline, the
outline itself closes the solid (a wall along the view). Whatever lies between the two skins along a ray is
filled: a horn curling back over the skull joins it where the two overlap in the picture.

A SIDE OUTLINE can cut it as well (`side`: a second footprint, over the side view's plane): the solid is then also
inside what the side picture shows of it, so its profile and its crown are that picture's. Every meeting of
skin, skin and outline is rounded (ROUND).

An outline pushed straight through the solid carries through everything only its own picture shows: every tuft
of its fringe as a rib, an eye's surround standing out sideways as a slab. So the outlines come separately: the
front picture's as drawn (`foot`) holds only NEAR the front skin (within NEAR of its surface), the back picture's
(`foot_b`) only near the back skin, and in between holds `wall`: what both pictures agree is the solid, smoothed.
The side outline is a smoothed one too, and stands back from the skins by the same token.

THE SIDES ARE A SKIN TOO (`side` with "top"): a head's sides are a third of its surface and only the side picture
shows them. Its read surface, a height map over the side view's plane, bounds the solid from both sides (a middle
part: the one picture serves left and right). WHO RULES WHERE: a picture rules what it sees squarely. The side
skin stands AWAY (bounds nothing) in two places: near its OWN outline (IN_SIDE: the profile, where it sees the face
edge-on and its read is wrong: left to cut there it carved the face into a wedge along the middle line), and in the
layer under the front or the back skin (down to NEAR) where that skin is well inside its own outline (IN_FRONT).
Everywhere else it rules, right up to the surface: so the rim of the face, where the front picture sees the surface
turning away, is the side picture's to shape, and the face does not overhang the side like the edge of a mask.
(Making every skin stand back where it is steep wrecked the face: tried.)

The arrays live with the reliefs' (<HOME>/_reliefs/<sha>.npz) and a blob names them:
    {"shape": "twoskin", "skins": "<sha>"}        ("flip": true = mirrored left-right)
twoskin_build.py makes them from the pictures' read surfaces; surfacefuse.py then lets every view shape the result.
"""
from __future__ import annotations

import hashlib
import io

import numpy as np

from . import relief

MAPS = ("front", "back", "foot", "cf", "cb")
ROUND = 0.006       # m: the radius of the edge where skins and outlines meet
NEAR = (0.004, 0.014)   # m under a skin: the outline as drawn holds down to the first, the smoothed one from the second
FRINGE = (0.0, 0.002)      # m under a skin: its picture's outline AS DRAWN holds down to the first, the agreed
#                            smoothed one from the second (a fringe is as deep as fur tips, not a rib through the head)
IN_SIDE = (0.004, 0.015)   # m inside the side outline: the side skin stands away nearer than the first, rules from the second
IN_FRONT = (0.005, 0.015)  # m inside the AGREED outline: a front / back skin's layer is its own from the second on
#                            (inside its own outline as drawn is not enough: a mark drawn as a wide box let the back
#                            skin spread out to it as an overhanging shell)
SIDE_ROUND = 0.015  # m: the side skin meets the front and back layers over this much (two pictures' versions of
#                     one eye surround never end at the same place: a sharp meeting leaves a lip)
NEVER, ALWAYS = (1e3, 1e3 + 1.0), (-1e3, -1e3 + 1.0)   # (as IN_FRONT / IN_SIDE: a layer that is nobody's own, a side
#                                                        skin that rules everywhere)
AWAY = 0.06         # m: how far the side skin stands away where the front or the back skin rules
SLACK = 0.012       # m: how far the side outline stands back where a skin rules


def put(frame: dict, maps: dict, side: dict | None = None, agreed: bool = False) -> str:
    """Store a skin pair; returns its name (a hash of its content). side = {"foot", "o", "U", "V", "px"}: the side
    view's outline as a signed distance over that view's plane. agreed: the skins were made to agree where they
    meet (twoskin_agree.py): the solid is plainly what all of them leave, and no skin stands away for another."""
    arrs = {k: np.asarray(maps[k], np.float32) for k in MAPS}
    if len({a.shape for a in arrs.values()}) != 1 or arrs["front"].ndim != 2:
        raise ValueError(f"a skin's maps {MAPS} are 2-D arrays of one shape")
    for k in ("o", "U", "V", "F"):
        arrs[k] = np.asarray(frame[k], np.float64)
    arrs["px"] = np.float64(frame["px"])
    arrs["rule"] = np.array([NEAR[0], NEAR[1], AWAY, SLACK, ROUND, *(NEVER if agreed else IN_FRONT),
                             *(ALWAYS if agreed else IN_SIDE), *FRINGE, SIDE_ROUND], np.float64)   # a solid is its data: the measures
    for k in ("wall", "foot_b", "front_s", "back_s"):                               # it was made with travel with it
        if maps.get(k) is not None:
            arrs[k] = np.asarray(maps[k], np.float32)
    if side is not None:
        arrs["side_foot"] = np.asarray(side["foot"], np.float32)
        if side.get("top") is not None:
            arrs["side_top"], arrs["side_cos"] = np.asarray(side["top"], np.float32), np.asarray(side["cos"], np.float32)
            arrs["sF"] = np.asarray(side["F"], np.float64)
        for k in ("o", "U", "V"):
            arrs["s" + k] = np.asarray(side[k], np.float64)
        arrs["spx"] = np.float64(side["px"])
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrs)
    sha = hashlib.sha1(b"".join(np.ascontiguousarray(arrs[k]).tobytes() for k in sorted(arrs))).hexdigest()[:20]
    p = relief.pool() / f"{sha}.npz"
    if not p.exists():
        p.write_bytes(buf.getvalue())
    return sha


def _sample(q: np.ndarray, o, U, V, px: float, shape):
    """Where points fall on a map: (bilinear sampler, how far outside the map they are in metres)."""
    q = q - o
    u, v = q @ U / px, q @ V / px
    H, W = shape
    uc, vc = np.clip(u, 0.0, W - 1.001), np.clip(v, 0.0, H - 1.001)
    off = np.hypot(u - uc, v - vc) * px
    j, i = np.floor(uc).astype(int), np.floor(vc).astype(int)
    fu, fv = uc - j, vc - i

    def at(m):
        return m[i, j] * (1 - fu) * (1 - fv) + m[i, j + 1] * fu * (1 - fv) + m[i + 1, j] * (1 - fu) * fv \
            + m[i + 1, j + 1] * fu * fv

    return at, off


def sd_twoskin(p: np.ndarray, pr: dict) -> np.ndarray:
    """Distance-like field of the skin pair (a lower bound outside, as an intersection's is)."""
    from .sdf import smin
    shp = p.shape[:-1]
    q = p.reshape(-1, 3).astype(np.float64)
    at, off = _sample(q, pr["o"], pr["U"], pr["V"], pr["px"], pr["front"].shape)
    t = (q - pr["o"]) @ pr["F"]
    rule = tuple(pr.get("rule", ())) + (NEAR[0], NEAR[1], AWAY, SLACK, ROUND, *IN_FRONT, *IN_SIDE, *FRINGE, SIDE_ROUND)[len(pr.get("rule", ())):]
    near0, near1, away, slack, rnd, f0, f1, s0, s1, g0, g1, srnd = rule
    ramp = lambda x, a, b: (lambda s: s * s * (3 - 2 * s))(np.clip((x - a) / (b - a), 0.0, 1.0))
    both = lambda x, y: -smin(-x, -y, rnd)          # an intersection with a rounded edge
    tf, tb = at(pr["front"]), at(pr["back"])
    d = both((t - tf) * at(pr["cf"]), (-tb - t) * at(pr["cb"]))
    foot = at(pr["foot"])
    deep = np.ones(len(q))
    mine = np.zeros(len(q))        # how much this place is the front or the back skin's own
    if "wall" in pr:       # how far under each skin: its own picture's outline near it, the agreed one deeper
        ease = lambda x: (lambda s: s * s * (3 - 2 * s))(np.clip((x - near0) / (near1 - near0), 0.0, 1.0))
        # (the depth is taken under the skins' broad lie, `front_s` / `back_s`: under the skin itself, every tuft and
        # every noisy pixel at its edge would shift where the outlines change over, and rib the wall)
        nf = ease((at(pr["front_s"]) if "front_s" in pr else tf) - t)
        nb = ease(t + (at(pr["back_s"]) if "back_s" in pr else tb))
        wall = at(pr["wall"])
        fb = at(pr["foot_b"]) if "foot_b" in pr else foot
        mine = np.maximum(1 - nf, 1 - nb) * ramp(-wall, f0, f1)
        df = (at(pr["front_s"]) if "front_s" in pr else tf) - t
        db = t + (at(pr["back_s"]) if "back_s" in pr else tb)
        foot = wall + (foot - wall) * (1 - ramp(df, g0, g1)) + (fb - wall) * (1 - ramp(db, g0, g1))
        deep = np.minimum(nf, nb)
    d = both(d, foot + off)
    if "side_foot" in pr:
        ats, offs = _sample(q, pr["so"], pr["sU"], pr["sV"], pr["spx"], pr["side_foot"].shape)
        sfoot = ats(pr["side_foot"]) + offs
        d = both(d, sfoot - slack * (1 - deep))
        if "side_top" in pr:    # the side picture's own surface, from both sides, where it rules
            out = np.maximum(mine, 1 - ramp(-sfoot, s0, s1))
            d = -smin(-d, -(np.abs((q - pr["so"]) @ pr["sF"]) - ats(pr["side_top"]) - away * out) * ats(pr["side_cos"]), srnd)
    return (d * (0.5 if "wall" in pr else 1.0)).reshape(shp)     # the mix steepens the field: halved, a lower bound


def prim(name: str, bl: dict, k: float):
    """The additive primitive of a twoskin blob."""
    from .spec import Prim, SpecError
    if not isinstance(bl.get("skins"), str):
        raise SpecError(f"twoskin {name!r}: needs \"skins\": the name build_skins gave it")
    try:
        m = relief.get(bl["skins"])
    except FileNotFoundError as e:
        raise SpecError(f"twoskin {name!r}: {e}") from None
    sx = np.array([-1.0, 1.0, 1.0]) if bl.get("flip") else np.ones(3)
    pr = {key: m[key] for key in MAPS}
    pr.update(o=m["o"] * sx, U=m["U"] * sx, V=m["V"] * sx, F=m["F"] * sx, px=float(m["px"]))
    if "side_foot" in m:
        pr.update(side_foot=m["side_foot"], so=m["so"] * sx, sU=m["sU"] * sx, sV=m["sV"] * sx, spx=float(m["spx"]))
        if "side_top" in m:
            pr.update(side_top=m["side_top"], side_cos=m["side_cos"], sF=m["sF"] * sx)
    if "rule" in m:
        pr["rule"] = tuple(float(v) for v in m["rule"])
    for key in ("wall", "foot_b", "front_s", "back_s"):
        if key in m:
            pr[key] = m[key]
    on = (np.minimum(m["foot"], m["foot_b"]) if "foot_b" in m else m["foot"]) < 0
    if not on.any():
        raise SpecError(f"twoskin {name!r} is empty")
    rows, cols = np.where(on)
    ts = (float(-m["back"][on].max()), float(m["front"][on].max()))
    corners = np.array([pr["o"] + pr["U"] * c * pr["px"] + pr["V"] * r * pr["px"] + pr["F"] * t
                        for c in (cols.min(), cols.max()) for r in (rows.min(), rows.max()) for t in ts])
    return Prim(name, "twoskin", bl.get("op", "add"), k, int(bl.get("layer", 0)), corners.min(0), corners.max(0), pr,
                reach=8.0 if "wall" in m else 4.0)   # the field is a lower bound (slopes scaled down to 1/4 at most): a blend reaches further
