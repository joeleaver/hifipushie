"""Human proportions by age and sex, from measured references (growth.json, made by spikes/humans/make_growth.py):
WHO growth standards (stature 0-19 y, head circumference 0-5 y; medians per sex) and Snyder et al. 1977 (UMTRI, for
the CPSC: head height, sitting height, breadths, girths, limb segments of US children 2-19 y; infants 0-2 y).

What artists' charts round to "4 heads at one year, 5 at three, 6 at six, 7 at ten, 7.5-8 adult" is, measured
(stature / vertex-to-chin head height): 4.6 at 1, 5.4 at 3, 6.0 at 5, 6.4 at 7, 7.0 at 10, 7.6 at 13, 8.0 adult.

`reference(age, sex)` gives a person's expected measures; `measure(P, J, chin, ...)` reads the same measures off a
body mesh, so the two can be laid side by side (`table`). sex: 0 female .. 1 male, as base.body.sex.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_CACHE: dict = {}
ADULT = 19.0  # the tables end here; older = this


def data() -> dict:
    if "data" not in _CACHE:
        _CACHE["data"] = json.loads(Path(__file__).with_name("growth.json").read_text())
    return _CACHE["data"]


def _by_sex(fn, sex: float) -> float:
    s = float(np.clip(sex, 0, 1))
    return (1 - s) * fn("f") + s * fn("m")


def stature(age: float, sex: float = 0.5) -> float:
    """Median stature (m) at an age in years (WHO; length under 2)."""
    d = data()
    a = float(np.clip(age, 0, ADULT))
    return _by_sex(lambda k: float(np.interp(a, d["ages"], d["stature_cm"][k])), sex) / 100


def _snyder(name: str, age: float, sex: float):
    """A Snyder mean (m) at an age: children's tables from 2.75 y, infants' (sexes together) below, joined linearly."""
    d = data()
    a = float(np.clip(age, 0, ADULT))
    ch = d["snyder_children"].get(name)
    inf = d["snyder_infants"].get(name)

    def one(k):
        pts = [tuple(p) for p in (ch[k] if ch else [])]
        if inf:
            pts = [tuple(p) for p in inf] + pts
        if not pts:
            return np.nan
        x, y = zip(*sorted(pts))
        return float(np.interp(a, x, y))
    return _by_sex(one, sex) / 100


def head_height(age: float, sex: float = 0.5) -> float:
    """Vertex to chin (m). Snyder from 2.75 y; younger from WHO's head circumference x the ratio of the two at 2.75
    (infants' head heights weren't measured): an estimate."""
    d = data()
    a = float(np.clip(age, 0, ADULT))

    def one(k):
        x, y = zip(*d["snyder_children"]["head_height"][k])
        if a >= x[0]:
            return float(np.interp(a, x, y))
        hc = d["head_circ_cm_0_5"][k]
        return y[0] * float(np.interp(a, hc["ages"], hc["cm"])) / float(np.interp(x[0], hc["ages"], hc["cm"]))
    return _by_sex(one, sex) / 100


def heads(age: float, sex: float = 0.5) -> float:
    """Stature in head heights."""
    return stature(age, sex) / head_height(age, sex)


def head_circumference(age: float, sex: float = 0.5) -> float:
    d = data()
    a = float(np.clip(age, 0, ADULT))

    def one(k):
        hc = d["head_circ_cm_0_5"][k]
        x, y = zip(*d["snyder_children"]["head_circ"][k])
        if a <= 2.0:
            return float(np.interp(a, hc["ages"], hc["cm"]))
        if a >= x[0]:
            return float(np.interp(a, x, y))
        t = (a - 2.0) / (x[0] - 2.0)
        return (1 - t) * float(np.interp(2.0, hc["ages"], hc["cm"])) + t * y[0]
    return _by_sex(one, sex) / 100


RATIOS = {  # measure -> the Snyder table it is checked against (each over stature)
    "sitting_height": "sitting_height", "biacromial": "biacromial", "shoulder_breadth": "shoulder_breadth",
    "hip_breadth": "hip_breadth", "trochanter_height": "trochanteric_height", "hand_length": "hand_length",
    "foot_length": "foot_length", "upper_arm": "shoulder_elbow", "chest_circ": "chest_circ", "waist_circ": "waist_circ",
    "hip_circ": "hip_circ", "neck_circ": "neck_circ", "head_breadth": "head_breadth"}


def reference(age: float, sex: float = 0.5) -> dict:
    """Expected measures (m) of a median person: stature, head_height, heads, head_circ and Snyder's segment means
    scaled to WHO's stature (each table's own ratio to Snyder's stature at that age)."""
    H = stature(age, sex)
    out = {"stature": H, "head_height": head_height(age, sex), "heads": heads(age, sex),
           "head_circ": head_circumference(age, sex)}
    a = float(age)
    Hs = _snyder("stature", max(a, 2.75), sex) if a >= 2.0 else _snyder("crown_sole", a, sex)
    for k, name in RATIOS.items():
        v = _snyder(name, a, sex)
        if a < 2.0 and name not in data()["snyder_infants"]:
            v = np.nan
        out[k] = float(v / Hs * H) if np.isfinite(v) else None
    if a < 2.0:  # infants: crown-rump is their sitting height
        out["sitting_height"] = float(_snyder("crown_rump", a, sex) / Hs * H)
    return out


def _hull_len(Q) -> float:
    from scipy.spatial import ConvexHull
    return float(ConvexHull(Q).area) if len(Q) >= 6 else float("nan")


def measure(P, J: dict, chin_z: float, top_z: float | None = None) -> dict:
    """The same measures off a body: P (n, 3) surface points (Z up, feet down, facing -Y), J joints by the base's
    names (pelvis, neck, shoulder.L, elbow.L, wrist.L, hip.L, knee.L, ankle.L, fingerN_k.L), chin_z the chin's
    height. Girths are convex hulls of level slices (a tape's path); the arms must stand clear of the torso."""
    P = np.asarray(P, float)
    J = {k: np.asarray(v, float) for k, v in J.items()}
    z0 = float(P[:, 2].min())
    top = float(P[:, 2].max()) if top_z is None else float(top_z)
    H = top - z0
    head = top - chin_z
    out = {"stature": H, "head_height": head, "heads": H / head}
    dz = 0.004 * H

    def slab(z, xmax=None):
        m = np.abs(P[:, 2] - z) < dz
        if xmax is not None:
            m &= np.abs(P[:, 0]) < xmax
        return P[m]
    hz = np.linspace(chin_z + 0.45 * head, chin_z + 0.85 * head, 9)
    hs = [slab(z) for z in hz]
    out["head_circ"] = float(np.nanmax([_hull_len(s[:, :2]) for s in hs]))
    out["head_breadth"] = float(max(np.ptp(s[:, 0]) for s in hs if len(s)))
    sh = J["shoulder.L"]
    mid = P[(np.abs(P[:, 0]) < 0.004 * H / 0.75) & (P[:, 2] < J["pelvis"][2] + 0.02 * H)]
    crotch = float(mid[:, 2].min())
    out["crotch_height"] = crotch - z0
    out["sitting_height"] = top - crotch  # (seat to vertex: the crotch is ~the seat plane of a standing figure)
    out["trochanter_height"] = float(J["hip.L"][2] - z0)
    out["biacromial"] = float(2 * abs(sh[0]))
    xs = abs(sh[0]) * 0.97
    zs = np.linspace(crotch, sh[2], 48)
    f = (zs - zs[0]) / (zs[-1] - zs[0])
    # (cut at the shoulder joints to leave the arms out: they lie inside a small child's torso, so a toddler's
    # breadths and girths below the chest read a little small)
    sl = [slab(z, xs) for z in zs]
    G = np.array([_hull_len(s[:, :2]) for s in sl])
    B = np.array([np.ptp(s[:, 0]) if len(s) else np.nan for s in sl])
    out["chest_circ"] = float(np.nanmax(G[(f > 0.68) & (f < 0.88)]))
    out["waist_circ"] = float(np.nanmin(G[(f > 0.35) & (f < 0.65)]))
    # the bust: the fullest level of the chest's front off the centre line, its girth, and how far it stands
    # ahead of the breast bone at that level (projection: ~1-2 cm a flat or male chest, 3-4 an A/B cup, 5-6 a C/D)
    fr = np.array([s_[np.abs(s_[:, 0]) > 0.25 * xs][:, 1].min() if len(s_) > 8 else np.nan for s_ in sl])
    kb = int(np.nanargmin(np.where((f > 0.6) & (f < 0.88), fr, np.nan)))
    at = np.abs(zs - zs[kb]) < 0.02 * H
    mid = P[(np.abs(P[:, 2] - zs[kb]) < 0.012 * H) & (P[:, 1] < float(np.median(P[:, 1])))]
    mid = mid[np.argsort(np.abs(mid[:, 0]))[:6]]
    if len(mid):
        out["bust_circ"], out["bust_height"] = float(np.nanmax(G[at])), float(zs[kb] - z0)
        out["bust_projection"] = float(mid[:, 1].min() - fr[kb])
    out["hip_circ"] = float(np.nanmax(G[(f > 0.02) & (f < 0.3)]))
    out["hip_breadth"] = float(np.nanmax(B[(f > 0.02) & (f < 0.3)]))
    out["waist_breadth"] = float(np.nanmin(B[(f > 0.35) & (f < 0.65)]))
    zn = np.linspace(J["neck"][2], chin_z, 10) if chin_z > J["neck"][2] + 0.01 * H else [float(J["neck"][2])]
    out["neck_circ"] = float(np.nanmin([_hull_len(slab(z, 0.6 * abs(sh[0]))[:, :2]) for z in zn]))
    out["neck_length"] = float(chin_z - J["neck"][2])
    L = lambda a, b: float(np.linalg.norm(J[a] - J[b]))  # noqa: E731
    out["upper_arm"] = L("shoulder.L", "elbow.L")
    out["forearm"] = L("elbow.L", "wrist.L")
    tip = next((k for k in ("finger2_3.L", "finger1_3.L") if k in J), None)
    if tip:
        out["hand_length"] = L("wrist.L", tip)
    out["thigh"] = L("hip.L", "knee.L")
    out["shin"] = L("knee.L", "ankle.L")
    foot = P[(P[:, 0] > 0) & (P[:, 2] < J["ankle.L"][2])]
    if len(foot):
        out["foot_length"] = float(np.ptp(foot[:, 1]))
    return out


def table(rows: list, keys=("stature", "heads", "head_height", "head_circ", "sitting_height", "biacromial",
                            "hip_breadth", "trochanter_height", "hand_length", "foot_length", "chest_circ",
                            "waist_circ", "neck_circ")) -> str:
    """rows: [(label, age, sex, measures)] -> text, ours | reference (ratio) per measure. Lengths in cm."""
    out = []
    for label, age, sex, m in rows:
        r = reference(age, sex)
        cells = []
        for k in keys:
            a, b = m.get(k), r.get(k)
            if a is None or b is None or not np.isfinite(a) or not np.isfinite(b):
                continue
            s = 1 if k == "heads" else 100
            cells.append(f"{k} {a * s:.1f}|{b * s:.1f} ({a / b:.2f})")
        out.append(f"{label:16s} " + "  ".join(cells))
    return "\n".join(out)
