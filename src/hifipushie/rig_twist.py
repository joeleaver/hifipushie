"""Twist bones: counts, the spread of twist, rolls, drive and check; chains; the test pose. Part of rig (rig.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import rig
from .spec import expand_mirror
from .rig import _joint, _segments
from .rig_bend import _share_bend
from .rig_model import _seg_dist, pose

def twist_counts(spec: dict) -> dict:
    """spec["rig"]["twist"]: false / 0 (none), an int (that many on every segment), or {"arm", "forearm", "upleg",
    "leg": count}; left out = TWIST_DEFAULT."""
    t = (spec.get("rig") or {}).get("twist", True)
    if t is True or t is None:
        return dict(rig.TWIST_DEFAULT)
    if t is False:
        return {k: 0 for k in rig.TWIST_DEFAULT}
    if isinstance(t, (int, float)):
        t = {k: int(t) for k in rig.TWIST_DEFAULT}
    bad = [k for k in t if str(k).lower() not in rig.TWIST_DEFAULT]
    if bad:
        raise ValueError(f"rig.twist: unknown segment(s) {bad} (have {', '.join(rig.TWIST_DEFAULT)})")
    out = dict(rig.TWIST_DEFAULT)
    for k, v in t.items():
        n = int(v)
        if not 0 <= n <= rig.TWIST_MAX:
            raise ValueError(f"rig.twist.{k}: {v} (0 to {rig.TWIST_MAX} twist bones a segment)")
        out[str(k).lower()] = n
    return out


def _add_twist(bones: list[dict], counts: dict) -> list[dict]:
    """The twist chains, appended after the Mixamo set (its names, order and indices stay as they were)."""
    idx = {b["name"]: i for i, b in enumerate(bones)}
    extra = []
    for S in ("Left", "Right"):
        for seg, (mode, key, child) in rig.TWIST.items():
            n = counts.get(key, 0)
            i, c = idx.get(rig.PREFIX + S + seg), idx.get(rig.PREFIX + S + child)
            if not n or i is None or c is None:
                continue
            a, b = bones[i]["head"], bones[c]["head"]
            L = float(np.linalg.norm(b - a))
            if L < 1e-6:
                continue
            for k in range(1, n + 1):
                t = k / n if mode == "follow" else (k - 1) / n
                share = k / n if mode == "follow" else -(1.0 - (k - 1) / n)
                driver = rig.PREFIX + S + (child if mode == "follow" else seg)
                extra.append({"name": f"{rig.PREFIX}{S}{seg}Twist{k}", "head": a + t * (b - a), "parent": i, "end": False,
                              "src": f"twist, {t:.2f} along {S}{seg}",
                              "twist": {"of": bones[i]["name"], "driver": driver, "mode": mode,
                                        "share": round(share, 4), "station": round(t, 4), "length": L,
                                        "axis": (b - a) / L}})
    return bones + extra


def twist_table(bones: list[dict]) -> list[dict]:
    """What an engine needs to drive the twist bones: [{"bone", "parent", "driver", "mode", "share", "station",
    "axis" (unit, Blender axes, the rest pose; the bone's local +Y in the GLB)}]."""
    return [{"bone": b["name"], "parent": b["twist"]["of"], "driver": b["twist"]["driver"], "mode": b["twist"]["mode"],
             "share": b["twist"]["share"], "station": b["twist"]["station"],
             "axis": [round(float(x), 6) for x in b["twist"]["axis"]]} for b in bones if b.get("twist")]


def _spread_twist(rb: list[dict], verts: np.ndarray, J: np.ndarray, W: np.ndarray, k: int = 4):
    """Each twisted segment's weight shared out along it: a vertex's weight on the segment's bone is split between
    the two stations it lies between (the bone itself is the station at the undriven end), linearly. Undriven, the
    twist bones move with their parent, so the skin is what it was; driven, the roll runs linearly joint to joint."""
    J, W = _share_bend(rb, J, W, verts)
    chains: dict = {}
    for i, b in enumerate(rb):
        if b.get("twist"):
            chains.setdefault(b["parent"], []).append(i)
    if not chains:
        return J, W
    V = np.asarray(verts, np.float64)
    kk = J.shape[1]
    J2 = np.concatenate([J, np.zeros_like(J)], 1)
    W2 = np.concatenate([W, np.zeros_like(W)], 1)
    for seg, tw in chains.items():
        t0 = rb[tw[0]]["twist"]
        st = sorted([(rb[i]["twist"]["station"], i) for i in tw] + [(0.0 if t0["mode"] == "follow" else 1.0, seg)])
        ts = np.array([s[0] for s in st])
        bi = np.array([s[1] for s in st])
        rows, cols = np.nonzero((J == seg) & (W > 0))
        if not len(rows):
            continue
        t = np.clip(((V[rows] - rb[seg]["head"]) @ t0["axis"]) / t0["length"], ts[0], ts[-1])
        hi = np.clip(np.searchsorted(ts, t, side="right"), 1, len(ts) - 1)
        lo = hi - 1
        f = (t - ts[lo]) / np.maximum(ts[hi] - ts[lo], 1e-9)
        w = W[rows, cols]
        J2[rows, cols], W2[rows, cols] = bi[lo], w * (1 - f)
        J2[rows, kk + cols], W2[rows, kk + cols] = bi[hi], w * f
    # more than k bones now. Dropping the smallest weight moves undriven skin (a belly vertex on Spine, Spine1, Hips
    # and the arm, the arm split in two: 10 mm when Spine1's 0.13 went); putting a split back together steps the twist
    # against the neighbours' when driven (thigh vertices with 2-4% of three other bones: sheared triangles). So the
    # cheaper of the two: the split goes back only if its smaller half is within TWIST_MERGE x the smallest weight.
    for _ in range(kk):
        over = np.flatnonzero((W2 > 0).sum(1) > k)
        if not len(over):
            break
        r = np.arange(len(over))
        a, b = W2[over, :kk], W2[over, kk:]
        pair = np.where((a > 0) & (b > 0), np.minimum(a, b), np.inf)
        c = pair.argmin(1)
        alone = np.where(W2[over] > 0, W2[over], np.inf)
        s = alone.argmin(1)
        merge = np.isfinite(pair[r, c]) & (pair[r, c] <= rig.TWIST_MERGE * alone[r, s])
        mo, mc = over[merge], c[merge]
        keep_b = W2[mo, kk + mc] > W2[mo, mc]
        tot = W2[mo, mc] + W2[mo, kk + mc]
        J2[mo, mc] = np.where(keep_b, J2[mo, kk + mc], J2[mo, mc])
        W2[mo, mc], W2[mo, kk + mc] = tot, 0.0
        W2[over[~merge], s[~merge]] = 0.0
    order = np.argsort(-W2, axis=1, kind="stable")[:, :k]
    Jk = np.take_along_axis(J2, order, 1)
    Wk = np.take_along_axis(W2, order, 1)
    Wk /= np.maximum(Wk.sum(1, keepdims=True), 1e-12)
    Jk[Wk <= 0] = 0
    return Jk, Wk


def _quat(axis, deg) -> np.ndarray:
    ax = np.asarray(axis, float)
    ax = ax / max(np.linalg.norm(ax), 1e-12)
    h = np.radians(deg) / 2
    return np.r_[np.cos(h), np.sin(h) * ax]


def roll_about(axis, turn) -> float:
    """The roll (degrees) of a turn (axis, degrees) about a unit axis: the twist of its swing-twist decomposition.
    This is the driver's side of every engine recipe: decompose the driver's LOCAL rotation from rest about the
    segment's axis, keep the twist angle."""
    q = _quat(turn[0], turn[1])
    return float(np.degrees(2 * np.arctan2(q[1:] @ np.asarray(axis, float), q[0])))


def roll_axis(bones: list[dict], name: str) -> np.ndarray:
    """The axis a bone rolls about: the segment it ends for hands and feet (the forearm, the shin), else its own."""
    i = [b["name"] for b in bones].index(name)
    b = bones[i]
    if name.endswith(rig.ROLL_OF_PARENT) and b["parent"] >= 0:
        d = b["head"] - bones[b["parent"]]["head"]
    else:
        seg = _segments(bones)
        d = seg[i][1] - seg[i][0] if i in seg else np.array([0, 0, 1.0])
    return d / max(np.linalg.norm(d), 1e-12)


def resolve_turns(bones: list[dict], turns: dict) -> dict:
    """Turns with the axis "roll" given their bone's roll axis (`roll_axis`)."""
    return {k: ((roll_axis(bones, k) if isinstance(ax, str) else ax), deg) for k, (ax, deg) in turns.items()}


def drive_twist(bones: list[dict], turns: dict) -> dict:
    """The turns plus every twist bone's own: its share of its driver's roll about the segment's axis (what an
    engine's driver does each frame; the documented shares, so a pose made with this is the proof of them)."""
    out = dict(turns)
    for b in bones:
        tw = b.get("twist")
        if tw and tw["driver"] in turns and b["name"] not in turns:
            ang = tw["share"] * roll_about(tw["axis"], turns[tw["driver"]])
            if abs(ang) > 1e-9:
                out[b["name"]] = (tw["axis"], ang)
        bd = b.get("bend")
        if bd and bd["driver"] in turns and b["name"] not in turns:  # half of the joint's own turn
            ax, deg = turns[bd["driver"]]
            out[b["name"]] = (ax, bd["share"] * float(deg))
    return out


def twist_check(bones: list[dict], V: np.ndarray, F: np.ndarray, J: np.ndarray, W: np.ndarray, driver: str,
                deg: float = 75.0, drive: bool = True, bins: int = 10) -> dict:
    """A segment's twist test: its driver rolled `deg` about the segment's axis (twist bones driven by their shares,
    or left still: what an engine without drivers shows), measured on the segment's skin by station along it:
    "twist" (how far the skin has turned about the axis, deg), "area" (cross-section area against rest, from the
    skin's distance to the axis: the candy wrapper is a dip), plus "at_end" / "at_start" (the twist left to the
    joints: hand roll minus the skin's turn by the wrist; the skin's turn by the elbow), "step" (the largest change
    of twist between neighbouring stations), "area_min", "tri_min" (the worst triangle's quality against its rest
    quality, 4 sqrt(3) area / sum of squared edges)."""
    names = [b["name"] for b in bones]
    d = names.index(driver)
    follow = driver.endswith(rig.ROLL_OF_PARENT)
    seg = bones[d]["parent"] if follow else d
    a = bones[seg]["head"]
    ax = roll_axis(bones, driver)
    kids = [b["head"] for b in bones if b["parent"] == seg and not b.get("twist") and not b["end"]]
    L = max(float((k - a) @ ax) for k in kids)
    own = {seg} | {i for i, b in enumerate(bones) if b.get("twist") and b["parent"] == seg}
    if follow:
        own.add(d)
    turns = {driver: (ax, deg)}
    P = pose(bones, V, J, W, drive_twist(bones, turns) if drive else turns)
    t = ((V - a) @ ax) / L
    wown = (W * np.isin(J, list(own))).sum(1)
    rel0 = V - a
    rad0 = rel0 - np.outer(rel0 @ ax, ax)
    rel1 = P - a
    rad1 = rel1 - np.outer(rel1 @ ax, ax)
    r0, r1 = np.linalg.norm(rad0, axis=1), np.linalg.norm(rad1, axis=1)
    sel = (wown > 0.6) & (t > -0.05) & (t < 1.1) & (r0 > 1e-4)
    ang = np.degrees(np.arctan2(np.cross(rad0, rad1) @ ax, (rad0 * rad1).sum(1)))
    edges = np.linspace(0.0, 1.0, bins + 1)
    tw, ar, st = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = sel & (t >= lo) & (t < hi)
        if m.sum() < 6:
            continue
        st.append(round(float(0.5 * (lo + hi)), 3))
        tw.append(round(float(np.median(ang[m])), 1))
        ar.append(round(float((r1[m].mean() / r0[m].mean()) ** 2), 3))
    Fm = F[sel[F].all(1)]

    def quality(X):
        e = [X[Fm[:, (i + 1) % 3]] - X[Fm[:, i]] for i in range(3)]
        A = 0.5 * np.linalg.norm(np.cross(e[0], -e[2]), axis=1)
        return 4 * np.sqrt(3) * A / np.maximum(sum((x * x).sum(1) for x in e), 1e-18)
    q = quality(P) / np.maximum(quality(V), 1e-9) if len(Fm) else np.ones(1)
    return {"driver": driver, "deg": deg, "driven": bool(drive), "station": st, "twist": tw, "area": ar,
            "at_start": tw[0] if tw else None, "at_end": round(deg - tw[-1], 1) if tw else None,
            "step": round(float(np.max(np.abs(np.diff([0.0] + tw + [deg])))), 1) if tw else None,
            "area_min": min(ar) if ar else None, "tri_min": round(float(q.min()), 3),
            "tri_p1": round(float(np.percentile(q, 1)), 3)}


def chains(spec: dict) -> list[dict]:
    """spec["rig"] = {"type": "chains", "root": joint, "chains": {name: {"from": parent chain (default: the
    root), "joints": [spec joints or [x, y, z], first to last]}}}: a weightless "root" bone on the ground under the
    root joint (root motion), then per chain bones "<name>_01", "<name>_02"... from each joint to the next and a
    "<name>_end" leaf at the last. A chain hangs from its parent chain's bone nearest its first joint (a neck
    starting where the spine ends hangs from the spine's last bone, no duplicate)."""
    s = expand_mirror(spec)
    r = spec["rig"]
    r0 = _joint(s, r["root"])
    bones = [{"name": "root", "head": np.array([r0[0], r0[1], 0.0]), "parent": -1, "end": False,
              "noweight": True, "src": "ground under " + str(r["root"])}]
    idx = {"root": [0]}
    todo = dict(r["chains"])
    while todo:
        done = [n for n, c in todo.items() if c.get("from", "root") in idx]
        if not done:
            raise ValueError(f"rig chains {sorted(todo)} hang from chains that don't exist")
        for n in done:
            c = todo.pop(n)
            pts = [_joint(s, j) for j in c["joints"]]
            if len(pts) < 2:
                raise ValueError(f"rig chain {n!r} needs two joints or more")
            cand = idx[c.get("from", "root")]
            # the nearest bone of the parent chain; at a joint two share, the later one (legs from the chest bone)
            par = min(cand, key=lambda i: (round(float(_seg_dist(pts[0], bones[i]["head"],
                                                                  bones[i].get("tail", bones[i]["head"]))), 2), -i))
            idx[n] = []
            for k, p in enumerate(pts):
                end = k == len(pts) - 1
                bones.append({"name": f"{n}_end" if end else f"{n}_{k + 1:02d}", "head": p, "parent": par,
                              "end": end, "src": str(c["joints"][k]), **({} if end else {"tail": pts[k + 1]})})
                par = len(bones) - 1
                if not end:
                    idx[n].append(par)
    return bones


def test_pose(bones: list[dict]) -> dict:
    """Turns that show off weights: humanoid elbow, shoulder, hip, knee, spine and head; chains: each chain's
    second bone 35 degrees."""
    names = {b["name"] for b in bones}
    if rig.PREFIX + "Hips" in names:
        want = {"LeftForeArm": ([1, 0, 0], -75), "RightArm": ([0, 1, 0], 45), "LeftUpLeg": ([1, 0, 0], -35),
                "RightLeg": ([1, 0, 0], 60), "Spine1": ([0, 1, 0], 12), "Neck": ([0, 0, 1], 25),
                "RightHand": ("roll", 75)}  # palm turned: the forearm's twist bones take it (`drive_twist`)
        return resolve_turns(bones, {rig.PREFIX + k: v for k, v in want.items() if rig.PREFIX + k in names})
    return {b["name"]: ([1, 0, 0], 35) for b in bones if b["name"].endswith("_02")}
