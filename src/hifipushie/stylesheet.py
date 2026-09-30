"""Style sheets: a style as a reusable bundle of shape, detail, paint and look decisions.

spec["style"]["sheet"] = "<name>" makes a model take the sheet `styles/<name>.json` (in the package, or
<HIFIPUSHIE_HOME>/_styles/<name>.json for your own). A sheet is a partial spec ("spec": base style and head fit/pose
defaults, part settings such as skin subsurface, paint layers addressed on the base's landmark joints, the style's
look preset) plus "rules": the checkable targets the style was written from (face ratios, plane corners and muzzle, eye opening, skin colour).

Resolution (`resolve`, done by `store.load`): the sheet's spec is the default and the model's own spec wins, key by
key, recursively (lists replace; a key set to null in the model deletes the sheet's). Sheet paint layers come first,
in the sheet's order, then the model's own layers. `store.save` writes back only what differs from the sheet
(`strip`), so editing the sheet restyles every model that takes it, and a model's spec.json holds its own decisions.

`check(name)` measures a model against its sheet's rules (face proportions from the GNM landmarks, the eye
opening from the head mesh) and says which rules pass.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent / "styles"
_CACHE: dict = {}


def _paths(name: str) -> list[Path]:
    home = Path(os.environ.get("HIFIPUSHIE_HOME", "workspace"))
    return [home / "_styles" / f"{name}.json", HERE / f"{name}.json"]


def names() -> list[str]:
    out = {p.stem for p in HERE.glob("*.json")}
    home = Path(os.environ.get("HIFIPUSHIE_HOME", "workspace")) / "_styles"
    out |= {p.stem for p in home.glob("*.json")} if home.exists() else set()
    return sorted(out)


def load(name: str) -> dict:
    for p in _paths(name):
        if p.exists():
            key = (str(p), p.stat().st_mtime)
            if key not in _CACHE:
                _CACHE[key] = json.loads(p.read_text())
            return _CACHE[key]
    raise ValueError(f"no style sheet {name!r}; sheets: {names()}")


def sheet_of(spec: dict) -> str | None:
    return ((spec or {}).get("style") or {}).get("sheet")


def _merge(base, over):
    if isinstance(base, dict) and isinstance(over, dict):
        out = {}
        for k, v in base.items():
            if k in over:
                if over[k] is None:
                    continue
                out[k] = _merge(v, over[k])
            else:
                out[k] = copy.deepcopy(v)
        for k, v in over.items():
            if k not in base and v is not None:
                out[k] = copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def _strip(resolved, base):
    """What `resolved` holds beyond `base` (so that _merge(base, _strip(resolved, base)) == resolved)."""
    out = {}
    for k, v in resolved.items():
        if k not in base:
            out[k] = v
        elif v == base[k]:
            continue
        elif isinstance(v, dict) and isinstance(base[k], dict):
            out[k] = _strip(v, base[k])
        else:
            out[k] = v
    for k in base:
        if k not in resolved:
            out[k] = None
    return out


def resolve(spec: dict) -> dict:
    """The model's spec over its sheet's (unchanged without a sheet)."""
    name = sheet_of(spec)
    if not name:
        return spec
    return _merge(load(name).get("spec") or {}, spec)


def strip(spec: dict) -> dict:
    """The model's own decisions: a resolved spec minus what its sheet gives."""
    name = sheet_of(spec)
    if not name:
        return spec
    return _strip(spec, load(name).get("spec") or {})


# ---- checks -------------------------------------------------------------------------------------------------------

def _within(v, rng):
    lo, hi = rng
    return (lo is None or v >= lo) and (hi is None or v <= hi)


def check(name: str) -> list[dict]:
    """The model against its sheet's rules: [{"rule", "value", "target", "ok"}]. Measured: face ratios from the GNM
    fit (interocular units: the chin against the philtrum, nose and mouth widths), the planes (base.plane_measures:
    the front/side corner's radius, the muzzle), the eye opening (height/width and how much of the iris the lids
    cover, from the posed head mesh)."""
    from . import base, store
    from . import spec as S
    spec = store.load(name)
    sh = sheet_of(spec)
    if not sh:
        raise ValueError(f"{name}: no style sheet (spec.style.sheet)")
    rules = load(sh).get("rules") or {}
    out = []
    head = (spec.get("base") or {}).get("head")
    if head:
        e = S.expand_mirror(spec)
        h = base.head_of(e, spec["base"])
        m = base.posed_measures(h)
        vals = {"chin_over_philtrum": (m["eye_chin"] - m["eye_seam"]) / (m["eye_seam"] - m["eye_nose"]),
                "nose_width": m["nose_width"], "mouth_width": m["mouth_width"], "ala_width": base.ala_width(h),
                "mouth_corner_lift": 1000 * float(0.5 * (h["lm68"][48][2] + h["lm68"][54][2])
                                                  - 0.5 * (h["lm68"][62][2] + h["lm68"][66][2]))}
        vals.update(base.plane_measures(h))
        op = base.eye_opening(h)[0]
        if op:
            vals["eye_h_over_w"] = op["h"] / op["w"]
            iris = 1000 * float(((spec.get("paint") or {}).get("iris.L") or {}).get("width", 0)) * base.IRIS_SPOT
            if iris:
                vals["iris_over_eye_w"] = iris / op["w"]
                vals["lid_cover_top"] = max(0.0, (iris / 2 - op["top"]) / iris)
                vals["lid_cover_bottom"] = max(0.0, (iris / 2 - op["bottom"]) / iris)
        for k, v in vals.items():
            if k in rules:
                out.append({"rule": k, "value": round(float(v), 3), "target": rules[k],
                            "ok": _within(v, rules[k]), "why": (rules.get("_why") or {}).get(k, "")})
    return out


# skin sample points on a GNM head, from its landmark joints (world offsets, m): (name, joint, offset, lit?)
SKIN_SAMPLES = [("forehead", "lm_nose_bridge", [0.0, 0.004, 0.04], "lit"),
                ("cheek_lit", "lm_nostril.R", [-0.03, 0.012, 0.006], "lit"),
                ("temple_shadow", "lm_eye_outer.L", [0.012, 0.012, -0.012], "shadow"),
                ("nose_side_shadow", "lm_nostril.L", [0.002, 0.004, 0.01], "shadow"),
                ("nose_tip", "lm_nose_tip", [0.0, 0.0, 0.0], None)]


def _project(cam: dict, p: np.ndarray, size: int) -> tuple[float, float]:
    eye, tgt = np.asarray(cam["eye"], float), np.asarray(cam["target"], float)
    f = (tgt - eye) / np.linalg.norm(tgt - eye)
    r = np.cross(f, [0, 0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    d = p - eye
    k = 1 / np.tan(np.radians(cam["fov"]) / 2)
    return (0.5 + 0.5 * k * (d @ r) / (d @ f)) * size, (0.5 - 0.5 * k * (d @ u) / (d @ f)) * size


def colour_check(name: str, size: int = 512, save: str | None = None) -> list[dict]:
    """Skin colour against the sheet's rules, rendered in the style's look (the scene must be synced): a front
    camera on the face, HSV sampled in 7x7 px patches at SKIN_SAMPLES (lit: forehead, the key side's cheek;
    shadow: the far side of the face, above the stubble). Returns rules as check() does, plus the samples."""
    import colorsys
    from . import scene, store
    from . import spec as S
    spec = store.load(name)
    rules = load(sheet_of(spec)).get("rules") or {}
    J = S.expand_mirror(spec)["joints"]
    mid = np.array(J["lm_nose_tip"]["pos"], float)
    cam = {"eye": (mid + [0, -0.85, 0.01]).tolist(), "target": mid.tolist(), "fov": 16, "name": "style_front"}
    scene.look(name, [], [cam], size, save)
    im = np.asarray(scene.look.images[0][1].convert("RGB"), float) / 255
    samples = {}
    for nm, j, off, kind in SKIN_SAMPLES:
        if j not in J:
            continue
        x, y = _project(cam, np.array(J[j]["pos"], float) + off, size)
        x, y = int(round(x)), int(round(y))
        patch = im[max(0, y - 3):y + 4, max(0, x - 3):x + 4].reshape(-1, 3).mean(0)
        h, s, v = colorsys.rgb_to_hsv(*patch)
        samples[nm] = {"hsv": [round(h * 360, 1), round(s, 3), round(v, 3)], "px": [x, y], "kind": kind,
                       "hex": "#%02x%02x%02x" % tuple(int(c * 255) for c in patch)}
    lit = [v["hsv"] for v in samples.values() if v["kind"] == "lit"]
    sh = [v["hsv"] for v in samples.values() if v["kind"] == "shadow"]
    vals = {}
    if lit and sh:
        vals = {"skin_sat_lit": float(np.mean([s[1] for s in lit])), "skin_sat_shadow": float(np.mean([s[1] for s in sh])),
                "skin_hue_shift_to_shadow": float(np.mean([s[0] for s in lit]) - np.mean([s[0] for s in sh]))}
    out = [{"rule": k, "value": round(v, 3), "target": rules[k], "ok": _within(v, rules[k]),
            "why": (rules.get("_why") or {}).get(k, "")} for k, v in vals.items() if k in rules]
    return out + [{"samples": samples}]
