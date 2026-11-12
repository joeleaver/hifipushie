"""The rigid head: its field, the rigid set, what lies near it, the head check. Part of rig (rig.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import rig
from .spec import expand_mirror, resolve_point
from .rig import _joint
from .rig_flesh import _flesh_tree
from .rig_model import _flesh, pose

def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def head_field(spec: dict, rb: list[dict]) -> dict | None:
    """{"h": f(points) -> 0..1 (1 = moves rigidly with the Head bone), "bone": Head's index, "band" (m), "how"}, or
    None (no Head bone, or spec["rig"]["rigid_head"] = false). spec["rig"]["rigid_head"] = {"band": m, "under": m}
    sets the falloff's height and the floor's drop."""
    opts = (spec.get("rig") or {}).get("rigid_head", True)
    names = [b["name"] for b in rb]
    if opts is False or rig.PREFIX + "Head" not in names:
        return None
    opts = opts if isinstance(opts, dict) else {}
    hi = names.index(rig.PREFIX + "Head")
    s = expand_mirror(spec)
    Jn = s["joints"]
    # sizes are counted from the modelling "neck" joint (the Head bone's own head on kit characters; a template's rig
    # hint may put Head higher)
    hj = _joint(s, "neck") if "neck" in Jn else rb[hi]["head"]
    top = rb[names.index(rig.PREFIX + "HeadTop_End")]["head"] if rig.PREFIX + "HeadTop_End" in names else hj + [0, 0, 0.25]
    size = max(float(np.linalg.norm(top - hj)), 1e-3)
    band = float(opts.get("band", rig.HEAD_BAND * size))
    under = float(opts.get("under", rig.HEAD_UNDER * size))
    fall = float(opts.get("fall", opts.get("band", rig.HEAD_FALL * size)))
    nape = float(opts.get("nape", rig.HEAD_NAPE))
    hy = float(rb[hi]["head"][1])
    col = opts.get("column", rig.HEAD_COLUMN)
    hd = np.asarray(rb[hi]["head"], float)
    nk = np.asarray(rb[rb[hi]["parent"]]["head"], float) if rb[hi]["parent"] >= 0 else hd - [0, 0, 0.4 * size]
    if spec.get("base"):
        if "lm_chin" in Jn and "lm_jaw_4.L" in Jn:
            pts = [resolve_point(s, "lm_chin")] + [0.5 * (resolve_point(s, f"lm_jaw_{i}.L")
                                                          + resolve_point(s, f"lm_jaw_{i}.R") * [-1, 1, 1])
                                                   for i in (7, 6, 5, 4)]
            pts = np.array(pts)[:, 1:]  # (y, z): the jaw's border from the chin back to its angle
            how = "jaw landmarks"
        else:
            pts = np.array([[hj[1] - 0.65 * size, hj[2]], [hj[1] - 0.28 * size, hj[2] + 0.10 * size]])
            how = "generic (no jaw landmarks: typical proportions from the Head joint)"
        y0, z0, (y1, z1) = float(pts[:, 0].min()), float(pts[:, 1].min()), pts[-1]
        slope = (z1 - z0) / max(y1 - y0, 1e-6)
        z0 -= max(0.0, float(np.max(z0 + slope * (pts[:, 0] - y0) - pts[:, 1])))  # under every border point

        # behind the jaw's angle the floor climbs a little up the ramus and runs level from the Head joint back:
        # level at the jaw angle's own height, more of the nape under the skull was head than a skull covers.
        fy, fz = [y0, float(y1)], [z0, z0 + slope * (float(y1) - y0)]
        if how == "jaw landmarks" and "lm_jaw_3.L" in Jn:
            # one landmark up the ramus, reached at the Head joint: the ear lobes (the next landmark's height) stay
            # above it. Up to the Head joint itself (the skull's base on MakeHuman) the lobes fell in the band and
            # 30 triangles under each ear turned inside out at 33 deg.
            sy, sz = float(rb[hi]["head"][1]), float(resolve_point(s, "lm_jaw_3.L")[2]) - (float(z1) - fz[-1])
            if sz > fz[-1] and sy > fy[-1] + 0.01:
                fy.append(sy)
                fz.append(sz)

        # at the nape the floor climbs on to the skull's base (HEAD_OCCIPUT under the Head joint, reached HEAD_BACK
        # behind it): level at the jaw's height, the back of the neck down to its base was Head 1.0 and a nod swung
        # it 22-28 mm back and 40 up, out over a collar's stand (the golfer's lump of nape skin)
        occ = opts.get("occiput", rig.HEAD_OCCIPUT)
        if occ is not None and occ is not False:
            by, bz = hy + rig.HEAD_BACK * size, float(rb[hi]["head"][2]) - float(occ) * size
            if by > fy[-1] + 0.005 and bz > fz[-1]:
                fy.append(by)
                fz.append(bz)

        def h(V):
            V = np.asarray(V, np.float64)
            floor = np.interp(V[:, 1], fy, fz) - under
            back = _ss((V[:, 1] - hy) / (0.35 * size))  # 0 at the Head joint and in front, 1 at the nape
            long = 1.0 - _ss((floor - V[:, 2]) / (fall * (1.0 + (nape - 1.0) * back)))
            # the long falloff is the NECK's: by height alone it reached the tops of the shoulders (a 33 deg turn
            # moved trapezius skin 70 mm). Past the neck's column only the short one counts.
            tn = np.clip((V[:, 2] - nk[2]) / max(hd[2] - nk[2], 1e-6), -0.5, 1.5)
            r = np.linalg.norm(V[:, :2] - (nk[:2] + tn[:, None] * (hd[:2] - nk[:2])), axis=1)
            long *= 1.0 - _ss((r - col[0] * size) / ((col[1] - col[0]) * size))
            return np.maximum(long, short(V))

        def short(V):  # which PART is head or worn is judged on this one: under the long falloff a collar averaged
            V = np.asarray(V, np.float64)  # over 0.5 head, took the head rule and turned with the face (57 mm)
            return 1.0 - _ss((np.interp(V[:, 1], fy, fz) - under - V[:, 2]) / min(fall, rig.HEAD_SHORT * size))
        return {"h": h, "part": short, "bone": hi, "band": float(opts.get("band", rig.HEAD_NEAR * size)),
                "how": f"{how}, floor {under * 1e3:.0f} mm under the jaw"}
    ids, carry = _flesh_tree(spec, rb)
    if hi not in ids:
        return None
    n = list(ids).index(hi)

    def h(V):
        V = np.asarray(V, np.float64)
        D = [np.min([_flesh(p, c.get("cuts", ()), V) for p in c["prims"]], 0) for c in carry]
        rest = np.min([d for i, d in enumerate(D) if i != n], 0) if len(D) > 1 else np.full(len(V), np.inf)
        return 1.0 - _ss((D[n] - rest) / band)
    return {"h": h, "bone": hi, "band": band, "how": f"flesh ({len(carry[n]['prims'])} head primitives)"}


def _rigid_head(J: np.ndarray, W: np.ndarray, h: np.ndarray, bone: int):
    """Weights blended toward the head bone by h: (1 - h) x what they were + h on Head."""
    k = J.shape[1]
    h = np.clip(np.asarray(h, np.float64), 0.0, 1.0)
    h[h > 0.995] = 1.0
    if not (h > 0).any():
        return J, W
    J2 = np.concatenate([J, np.full((len(J), 1), bone, J.dtype)], 1)
    W2 = np.concatenate([W * (1 - h[:, None]), h[:, None]], 1)
    same = J == bone  # already among its bones: its weight joins the new slot
    W2[:, k] += (W2[:, :k] * same).sum(1)
    W2[:, :k][same] = 0.0
    order = np.argsort(-W2, axis=1, kind="stable")[:, :k]
    Jk = np.take_along_axis(J2, order, 1)
    Wk = np.take_along_axis(W2, order, 1)
    Wk /= np.maximum(Wk.sum(1, keepdims=True), 1e-12)
    Jk[Wk <= 0] = 0
    return Jk, Wk


def rigid_near(rb: list[dict], skins: dict, verts: dict, moved: dict, band: float | None = None,
               cover: dict | None = None, field=None) -> dict:
    """Everything a face shape moves is head too: {part: (J, W)} with every vertex some shape moves MOVED[1] or more
    (`moved`: {part: the largest move per vertex, m}) weighted 1.0 to Head, the vertices within `band` of one
    blended toward it, and vertices moved less (down to MOVED[0]) in proportion (the export, after the face shapes
    are made)."""
    from scipy.spatial import cKDTree
    names = [b["name"] for b in rb]
    if rig.PREFIX + "Head" not in names or not moved:
        return skins
    hi = names.index(rig.PREFIX + "Head")
    if band is None:
        top = rb[names.index(rig.PREFIX + "HeadTop_End")]["head"] if rig.PREFIX + "HeadTop_End" in names else None
        band = rig.HEAD_BAND * (float(np.linalg.norm(top - rb[hi]["head"])) if top is not None else 0.25)
    lo, hi_ = rig.MOVED
    full = {p: np.asarray(m, np.float64) >= hi_ for p, m in moved.items() if p in verts}
    pts = [np.asarray(verts[p], np.float64)[m] for p, m in full.items() if m.any()]
    tree = cKDTree(np.concatenate(pts)) if pts else None
    out = dict(skins)
    for pn, (J, W) in skins.items():
        if pn not in verts or pn not in moved:  # a part no shape moves is worn or a prop: a collar beside the
            # throat took Head 0.56 from the moved skin near it and turned with the face (26 mm off the shirt)
            continue
        h = np.zeros(len(verts[pn]))
        if tree is not None:
            d, _ = tree.query(np.asarray(verts[pn], np.float64), distance_upper_bound=band)
            d = np.where(np.isfinite(d), d, band)
            h = 1.0 - _ss(d / band)
            if field is not None:  # past NEAR_SHORT of the band the head field's own falloff rules: down the throat
                # the band reached past it (jawOpen moves throat skin 3 mm+ down to the Adam's apple; Garrett's
                # notch 2.5 cm under that was Head 0.80, field 0.38, v23 0.16: a 33 deg turn dragged it 25 mm)
                h = np.maximum(1.0 - _ss(d / (rig.NEAR_SHORT * band)), np.minimum(h, field(verts[pn])))
            if cover and pn in cover:  # skin under a collar follows the collar (`skin_cover`), not the face near it
                h = h * (1.0 - cover[pn])
        if pn in moved:  # moved a little (skin sliding on the throat, a chest a big jaw's field reaches): a little
            h = np.maximum(h, _ss((np.asarray(moved[pn], np.float64) - lo) / (hi_ - lo)))
        if field is not None:  # h is the Head share wanted, not a second blend on top of the head rule skin_parts
            # applied (two blends of 0.38 made 0.62 at Garrett's notch)
            Wf = np.asarray(W, np.float64)
            cur = np.where(np.asarray(J) == hi, Wf, 0.0).sum(1)
            h = np.clip((h - cur) / np.maximum(1.0 - cur, 1e-9), 0.0, 1.0)
        if (h > 0).any():
            out[pn] = _rigid_head(np.asarray(J), np.asarray(W, np.float64), h, hi)
    return out


def head_check(bones: list[dict], V: np.ndarray, J: np.ndarray, W: np.ndarray, deg: float = 33.0) -> dict | None:
    """The head's test: its weights on the front of the face by height (rows of {"z", "rel" (height over the Head
    joint / the head's size), "head", "neck", "arms" (clavicles and arms), "lag_mm"}), where lag is how far a vertex
    ends from where a rigid head would put it with the Head bone turned `deg` about the vertical. A rigid face reads
    head 1.00 / lag 0 down to the jaw, and the falloff sits below."""
    names = [b["name"] for b in bones]
    if rig.PREFIX + "Head" not in names or rig.PREFIX + "HeadTop_End" not in names:
        return None
    hi = names.index(rig.PREFIX + "Head")
    hj, top = bones[hi]["head"], bones[names.index(rig.PREFIX + "HeadTop_End")]["head"]
    size = float(np.linalg.norm(top - hj))
    wh = (W * (J == hi)).sum(1)
    wn = (W * (J == names.index(rig.PREFIX + "Neck"))).sum(1) if rig.PREFIX + "Neck" in names else np.zeros(len(V))
    arms = [i for i, n in enumerate(names) if "Shoulder" in n or "Arm" in n]
    wa = (W * np.isin(J, arms)).sum(1)
    P = pose(bones, V, J, W, {rig.PREFIX + "Head": ([0, 0, 1], deg)})
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    rigid = (V - hj) @ np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]).T + hj
    lag = np.linalg.norm(P - rigid, axis=1)
    front = (np.abs(V[:, 0] - hj[0]) < 0.25 * size) & (V[:, 1] < hj[1] - 0.15 * size)
    rows = []
    for rel in np.arange(-0.3, 0.55, 0.1):
        m = front & (np.abs(V[:, 2] - hj[2] - rel * size) < 0.05 * size)
        if m.sum() > 3:
            rows.append({"z": round(float(hj[2] + rel * size), 3), "rel": round(float(rel), 2),
                         "head": round(float(wh[m].mean()), 2), "neck": round(float(wn[m].mean()), 2),
                         "arms": round(float(wa[m].mean()), 2), "lag_mm": round(float(lag[m].mean() * 1e3), 1)})
    return {"deg": deg, "size": size, "rows": rows, "head_weight": wh, "lag": lag}
