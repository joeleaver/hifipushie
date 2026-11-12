"""Anatomical zones: the body's and the face's zones by name, on the model's own joints. Part of skin (skin.py has the spec)."""
from __future__ import annotations

import json

import numpy as np

from . import skin
from .spec import SpecError

def _joints(spec: dict) -> dict:
    from . import paint
    return {k: np.asarray(v["pos"], float) for k, v in paint._expanded(spec)["joints"].items() if "pos" in v}


def _radius(spec: dict, name: str) -> float:
    from . import paint
    return float(paint._expanded(spec)["joints"][name].get("r", 0.03))


def interocular(J: dict) -> float:
    for a, b in (("eye_front.L", "eye_front.R"), ("eye.L", "eye.R")):
        if a in J and b in J:
            return float(np.linalg.norm(J[a] - J[b]))
    if "lm_eye_inner.L" in J and "lm_eye_outer.L" in J:
        return float(2 * abs(0.5 * (J["lm_eye_inner.L"][0] + J["lm_eye_outer.L"][0])))
    return 0.063


def _side(name: str, side: str) -> str:
    return name[:-2] + side if side and name.endswith(".L") else name


def _mx(v, side: str):
    return [(-v[0] if side == ".R" else v[0]), v[1], v[2]]


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([0.0, 0.0, 1.0])


def _palm_normal(J: dict, s: str) -> np.ndarray:
    """Out of the palm of hand `s` (".L" / ".R"): across the knuckle row and the hand's length, the way the relaxed
    fingers curl."""
    w, a, b = J[f"wrist{s}"], J[f"finger1_0{s}"], J[f"finger4_0{s}"]
    n = _unit(np.cross(a - w, b - w))
    curl = sum(np.dot(J[f"finger{k}_3{s}"] - J[f"finger{k}_1{s}"] - (J[f"finger{k}_1{s}"] - J[f"finger{k}_0{s}"]) *
                      np.dot(J[f"finger{k}_3{s}"] - J[f"finger{k}_1{s}"], _unit(J[f"finger{k}_1{s}"] - J[f"finger{k}_0{s}"])) /
                      max(np.linalg.norm(J[f"finger{k}_1{s}"] - J[f"finger{k}_0{s}"]), 1e-9), n) for k in range(1, 5))
    if abs(curl) < 1e-4:  # straight fingers: the thumb sits on the palm's side of the index finger... use its root
        curl = np.dot(J[f"thumb_1{s}"] - a, n)
    return n if curl > 0 else -n


def _extensor(J: dict, a: str, j: str, b: str, fallback) -> np.ndarray:
    """The outer side of hinge j between a and b (the elbow's point, the kneecap)."""
    u, f = _unit(J[a] - J[j]), _unit(J[b] - J[j])
    inner = u + f
    return -_unit(inner) if np.linalg.norm(inner) > 0.12 else np.asarray(fallback, float)


def _sp(points, radii, soft=0.6, line=False) -> dict:
    return {"spot": {"at": [[round(float(x), 5) for x in p] for p in points],
                     "radius": [[round(float(x), 5) for x in (r if np.ndim(r) else [r] * 3)] for r in radii] if not line
                     else [round(float(r), 5) for r in radii], "soft": soft, **({"line": True} if line else {})}}


def _body_zone(spec: dict, J: dict, name: str, s: str, grow: float) -> list:
    """A body zone's mask entries on side s."""
    r = lambda j: _radius(spec, j) * grow  # noqa: E731
    need = lambda *js: [j for j in js if j not in J]  # noqa: E731
    base = name[:-2] if name.endswith(".L") else name
    if base == "shoulder":
        return [_sp([J[f"shoulder{s}"] + [0, 0, 0.4 * r(f"shoulder{s}")]], [1.5 * r(f"shoulder{s}")])]
    if base == "elbow":
        e = _extensor(J, f"shoulder{s}", f"elbow{s}", f"wrist{s}", [0, 1, 0])
        return [_sp([J[f"elbow{s}"] + 0.75 * r(f"elbow{s}") * e], [1.0 * r(f"elbow{s}")])]
    if base == "knee":
        e = _extensor(J, f"hip{s}", f"knee{s}", f"ankle{s}", [0, -1, 0])
        return [_sp([J[f"knee{s}"] + 0.8 * r(f"knee{s}") * e], [1.05 * r(f"knee{s}")])]
    if base in ("forearm", "upper_arm"):
        a, b = (f"elbow{s}", f"wrist{s}") if base == "forearm" else (f"shoulder{s}", f"elbow{s}")
        return [_sp([J[a], J[b]], [1.35 * r(a), 1.5 * r(b)], line=True)]
    if base == "chest":
        return [_sp([J["chest"] + [0, -1.0 * r("chest"), 1.6 * r("chest")]], [[2.4 * r("chest"), 1.6 * r("chest"), 2.2 * r("chest")]])]
    if base == "collarbone":
        return [_sp([J["neck"] + [0.9 * sx * r("neck"), -0.6 * r("neck"), -1.2 * r("neck")] for sx in (-1, 1)],
                    [[1.3 * r("neck"), 0.9 * r("neck"), 0.5 * r("neck")]] * 2)]
    if base in ("foot", "sole"):
        if need(f"ankle{s}", f"toe{s}"):
            raise SpecError(f"zone {name!r}: the model has no ankle/toe joints")
        c = 0.5 * (J[f"ankle{s}"] + J[f"toe{s}"])
        ball = _sp([c], [0.75 * np.linalg.norm(J[f"toe{s}"] - J[f"ankle{s}"]) * grow])
        return [ball] if base == "foot" else [ball, {"facing": [0, 0, -1], "range": [0.2, 0.7]}]
    # the hand
    miss = need(f"wrist{s}", *[f"finger{k}_{j}{s}" for k in range(1, 5) for j in range(4)])
    if miss:
        raise SpecError(f"zone {name!r}: the model has no hand joints ({miss[0]}...): a base body gives them")
    pn = _palm_normal(J, s)
    roots = [J[f"finger{k}_0{s}"] for k in range(1, 5)]
    centre = (J[f"wrist{s}"] + np.mean(roots, 0)) / 2
    width = np.linalg.norm(roots[0] - roots[3])
    tips = [J[f"finger{k}_3{s}"] for k in range(1, 5)] + [J[f"thumb_3{s}"]]
    span = max(np.linalg.norm(t - centre) for t in tips)
    hand = _sp([centre + 0.35 * (np.mean(tips, 0) - centre)], [1.25 * span * grow], soft=0.3)
    if base == "hand":
        return [hand]
    if base == "palm":
        return [hand, {"facing": [round(float(x), 4) for x in pn], "range": [0.0, 0.55]}]
    if base == "back_of_hand":
        return [_sp([centre - 0.3 * width * pn], [0.85 * width * grow]),
                {"facing": [round(float(x), 4) for x in -pn], "range": [0.1, 0.6]}]
    if base == "wrist_inner":
        return [_sp([J[f"wrist{s}"] + 0.6 * r(f"wrist{s}") * pn + 1.2 * r(f"wrist{s}") * _unit(J[f"elbow{s}"] - J[f"wrist{s}"])],
                    [1.5 * r(f"wrist{s}")])]
    chains = [[J[f"finger{k}_{j}{s}"] for j in range(4)] for k in range(1, 5)] + [[J[f"thumb_{j}{s}"] for j in range(4)]]
    rads = [[_radius(spec, f"finger{k}_{j}{s}") for j in range(4)] for k in range(1, 5)] + \
           [[_radius(spec, f"thumb_{j}{s}") for j in range(4)]]
    if base == "knuckles":  # the back of every finger joint
        pts, rr = [], []
        for ch, ra in zip(chains, rads):
            for j in range(3):
                rj = min(ra[j], 0.014)
                pts.append(ch[j] - 0.75 * rj * pn)
                rr.append((0.95 if j else 1.15) * rj * grow)
        return [_sp(pts, rr)]
    if base == "fingertips":
        return [_sp([0.3 * ch[2] + 0.7 * ch[3] for ch in chains], [1.1 * min(ra[2], 0.012) * grow for ra in rads])]
    if base == "nails":
        pts, rr = [], []
        for ch, ra in zip(chains, rads):
            rj = min(ra[2], 0.011)
            ax = _unit(ch[3] - ch[2])
            for t in (0.45, 0.75):
                pts.append(ch[2] + t * (ch[3] - ch[2]) - 0.85 * rj * pn)
                rr.append(0.62 * rj * grow)
        return [_sp(pts, rr, soft=0.35), {"facing": [round(float(x), 4) for x in -pn], "range": [0.15, 0.6]}]
    raise SpecError(f"no zone {name!r}")


def zone_names() -> list:
    names = set(skin.FACE) | set(skin.UNIONS) | set(skin.LINES) | set(skin.OUTLINES) | set(skin.BODY) | set(skin.EXTRA)
    return sorted(names | {n[:-2] + ".R" for n in names if n.endswith(".L")} | {n[:-2] for n in names if n.endswith(".L")})


def zone(spec: dict, name: str, grow: float = 1.0, what: str = "zone") -> list:
    """A zone as mask stack entries (spot / outline / facing generators)."""
    J = _joints(spec)
    io = interocular(J)
    stem, side = (name[:-2], name[-2:]) if name.endswith((".L", ".R")) else (name, "")
    sides = [side] if side else [".L", ".R"]
    try:
        if stem in ("lash_upper", "lash_lower"):
            # the lid's margin is the skin that touches the eyeball: found from the eyeballs themselves (a line drawn
            # from the lid landmarks sat behind the rim on one head and in the air on the next)
            eyes = [f"eye{sd}" for sd in sides]
            if any(e not in J for e in eyes):
                raise KeyError(eyes[0])
            up = stem == "lash_upper"
            out = [{"near": eyes, "within": round((0.0024 if up else 0.0015) * grow, 5), "soft": round(0.0018 * grow, 5)},
                   {"axis": {"dir": [0, 0, 1], "at": eyes[0], "from": 0.0003 if up else -0.0003, "to": 0.0022 if up else -0.0022}}]
            # ... and only along the margin itself: the pretarsal lid lies on the eyeball too, so "near the eyeball"
            # alone painted the whole lid up to the fold (a dark grey band over the iris on an open lid, Tess 2026-10-09).
            # A tube through the margin's landmarks (corner -> the two margin points -> corner) keeps it a line.
            mid = ("lm_lid_upper_in", "lm_lid_upper_out") if up else ("lm_lid_lower_in", "lm_lid_lower_out")
            if all(f"{m}{sd}" in J for m in mid for sd in sides):
                tube = []
                for sd in sides:
                    pl = [J[f"lm_eye_inner{sd}"], J[f"{mid[0]}{sd}"], J[f"{mid[1]}{sd}"], J[f"lm_eye_outer{sd}"]]
                    r = io * grow * (0.03 if up else 0.022)
                    tube.append({"mask": [_sp(pl, [0.6 * r, r, r, 0.8 * r], soft=0.7, line=True)], **({"blend": "max"} if tube else {})})
                out.append({"mask": tube})
            return out
        if stem in skin.OUTLINES:
            pts = skin.OUTLINES[stem]
            if stem in skin.OUTLINES_DENSE and "verm_u00" in J:  # (a GNM head: the vermilion's own edges, base_measures.VERM_N
                # points each; the 68 landmarks' seven chords cut the bow and corners off, and the face's pale
                # pores / stubble layers ("lips" subtracted) painted there: the upper lip read pale whatever
                # skin.lips said)
                pts = skin.OUTLINES_DENSE[stem]
            return [{"outline": {"points": pts, "dir": [0, 1, 0], "soft": 0.0012 * grow, "depth": 0.03}}]
        key = stem + ".L" if stem + ".L" in skin.FACE or stem + ".L" in skin.UNIONS or stem + ".L" in skin.LINES or stem + ".L" in skin.BODY else stem
        if key in skin.UNIONS:
            out = []
            for m in skin.UNIONS[key]:
                for sd in (sides if key.endswith(".L") else [""]):
                    sub = zone(spec, _side(m, sd) if m.endswith(".L") else m, grow, what)
                    out.append({"mask": sub, **({"blend": "max"} if out else {})})
            return out
        if key in skin.FACE:
            pts, rr = [], []
            for sd in (sides if key.endswith(".L") else [""]):
                for anchor, off, rad in skin.FACE[key]:
                    pts.append(J[_side(anchor, sd)] + io * np.asarray(_mx(off, sd)))
                    rr.append(io * grow * np.asarray(rad))
            return [_sp(pts, rr)]
        if key in skin.LINES:
            out = []
            for sd in sides:
                pl, rad = skin.LINES[key]
                e = _sp([J[_side(a, sd)] + io * np.asarray(_mx(off, sd)) for a, off in pl], [io * grow * x for x in rad], soft=0.7, line=True)
                out.append({**e, **({"blend": "max"} if out else {})})
            return out
        if key in skin.BODY:
            if not key.endswith(".L"):
                return _body_zone(spec, J, key, "", grow)
            out = []
            for sd in sides:
                out.append({"mask": _body_zone(spec, J, key, sd, grow), **({"blend": "max"} if out else {})})
            return out
    except KeyError as err:
        raise SpecError(f"{what}: zone {name!r} needs joint {err.args[0]!r}, which this model doesn't have (zones are "
                        f"placed from a base body's joints and a GNM head's lm_* landmarks)")
    raise SpecError(f"{what}: no zone {name!r} (zones: {', '.join(zone_names())})")


def uses_zones(layers_: dict) -> bool:
    return '"zone"' in json.dumps(layers_, default=str)


def expand_zones(spec: dict, ly: dict, what: str = "paint") -> dict:
    """A layer (or mask entry) with every "zone" generator replaced by the zone's own mask entries."""
    if not isinstance(ly, dict) or '"zone"' not in json.dumps(ly, default=str):
        return ly
    out = dict(ly)
    stack = [expand_zones(spec, e, what) for e in out.get("mask") or []]
    if "zone" in out:
        z = out.pop("zone")
        z = {"name": z} if isinstance(z, str) else z
        if not (isinstance(z, dict) and isinstance(z.get("name"), str) and set(z) <= {"name", "grow"}):
            raise SpecError(f"{what}: zone is a name or {{\"name\", \"grow\"}}")
        entries = zone(spec, z["name"], float(z.get("grow", 1.0)), what)
        if any(k in out for k in ("blend", "weight", "breakup", "levels", "invert", "blur")) and "mask" not in ly:
            out["mask"] = entries  # an entry of a stack: its zone becomes its nested mask
            return out
        stack = [{"mask": entries}] + stack  # a layer's flat key: multiplies what follows
    if stack:
        out["mask"] = stack
    return out
