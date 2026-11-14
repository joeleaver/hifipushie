"""Gates at the export: cloth decimation, the approved head, the face's light, fold form, the default hair tier. Part of the game-ready export (asset.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from . import asset
from . import validated

def decimate_cloth(cparts: list, cloth_triangles: int, log: list) -> list:
    """The garments [(name, part, files)] decimated together to at most `cloth_triangles` (one ratio for all)."""
    from . import lods_part
    n_c = sum(len(cp["corner_vert"]) // 3 for _, cp, _ in cparts)
    ratio_c = cloth_triangles / n_c
    got = n_c
    msgs, dec = [], list(cparts)
    for round_c in range(asset.CLOTH_BUDGET_ROUNDS):  # parts' floors (made pieces, held borders) keep more than the
        # ratio asks (Garrett v5: 27,032 of 25,000): the ratio is scaled by the overshoot until the sum fits
        dec, msgs = [], []
        for pn_c, cpart, cfiles in cparts:
            q, _, r_ = lods_part.lod_part(cpart, None, ratio_c)
            msgs.append(f"cloth {pn_c}: {r_['triangles0']} -> {r_['triangles']} triangles (cloth_triangles "
                        f"{cloth_triangles} over {n_c}, ratio {ratio_c:.3f})")
            dec.append((pn_c, q, cfiles))
        got = sum(len(q["corner_vert"]) // 3 for _, q, _ in dec)
        if got <= cloth_triangles:
            break
        ratio_c *= cloth_triangles / got * 0.99
    log.extend(msgs)
    if got > cloth_triangles:
        log.append(f"WARNING cloth: {got} triangles after {asset.CLOTH_BUDGET_ROUNDS} rounds, over cloth_triangles "
                   f"{cloth_triangles}")
    return dec


def approved_head(spec: dict, log: list, approved_path: Path | None = None) -> dict:
    """(Garrett s7, coordinator's rule) spec base.head_approved = an approval key in workspace/approved.json (e.g.
    "head/garrett" -> gp_h6c): the export's head GEOMETRY is that approved model's base.head (the build keeps only
    HEAD_KEEP_FROM_BUILD); skin TEXTURES still come from the build's skin. Garrett v6 carried s21's lid_fold and shape
    (eye_bag, cheek_flat), which Joe never approved: the face drifted. Every key dropped or changed is logged; an
    unknown key / missing model raises (never a silent fallback to the unapproved head)."""
    key = (spec.get("base") or {}).get("head_approved")
    if not key:
        return spec
    from . import store
    ap = approved_path or (store.HOME / "approved.json")
    ent = (json.loads(Path(ap).read_text()).get("approved") or {}).get(key)
    if not ent or not ent.get("model"):
        raise ValueError(f"base.head_approved {key!r}: no such approval in {ap}")
    sp_ = Path(ap).parent / ent["model"] / "spec.json"
    head0 = (json.loads(sp_.read_text()).get("base") or {}).get("head")
    if not head0:
        raise ValueError(f"base.head_approved {key!r}: {sp_} has no base.head")
    build = spec["base"].get("head") or {}
    head = {**head0, **{k: build[k] for k in asset.HEAD_KEEP_FROM_BUILD if k in build}}
    diff = sorted(k for k in set(build) | set(head) if build.get(k) != head.get(k))
    log.append(f"head: the APPROVED head {key} = {ent['model']}'s base.head; the build's "
               + (f"{', '.join(diff)} replaced / dropped" if diff else "head was already it"))
    out = dict(spec)
    out["base"] = {**spec["base"], "head": head}
    approved_folds = (json.loads(sp_.read_text()).get("skin") or {}).get("folds") or {}
    out = fold_form_gate(out, log, approved_folds)
    from . import skin_layers_stack
    return skin_layers_stack.stack_on_head(out, log)


def _lstar(a: np.ndarray) -> np.ndarray:
    c = np.asarray(a, float)[..., :3] / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    Y = c @ np.array([0.2126, 0.7152, 0.0722])
    return np.where(Y > 0.008856, 116 * np.cbrt(Y) - 16, 903.3 * Y)


def face_light(img, eyes=None) -> dict:
    """(Garrett s10, coordinator) lightness of a FRONT eyes render (the eyes in the middle band, brows and cheeks in
    frame): the upper-lid band and the under-eye band against the cheek (L* differences, both eyes averaged) and the
    forehead's fine texture (std of L* minus its blur at 1/25 of the eye distance: grooves / wrinkles). Eyes are the
    darkest blurred point in each half between 40 and 75% of the height (the pupils), or given (px). Regions are boxes
    in eye-distance units d: lid -0.15..-0.07 d above the pupil, under +0.08..+0.2 d, cheek +0.3..+0.42 d (each
    +-0.15 d wide), forehead -0.85..-0.6 d, +-0.4 d about the midpoint."""
    from scipy import ndimage as nd
    L = _lstar(np.asarray(Image.open(img).convert("RGB")) if isinstance(img, (str, Path)) else np.asarray(img))
    h, w = L.shape
    if eyes is None:
        b = nd.gaussian_filter(L, w / 150)
        eyes = []
        for x0, x1 in ((0, w // 2), (w // 2, w)):
            s_ = b[int(.4 * h):int(.75 * h), x0:x1]
            y, x = np.unravel_index(np.argmin(s_), s_.shape)
            eyes.append((x + x0, y + int(.4 * h)))
    (x1, y1), (x2, y2) = eyes
    d = float(np.hypot(x2 - x1, y2 - y1))

    def box(A, cx, cy, a, b, c, e):
        return A[max(0, int(cy + c * d)):int(cy + e * d), max(0, int(cx + a * d)):int(cx + b * d)]
    m = {k: float(np.mean([box(L, x, y, a, b, c, e).mean() for x, y in eyes]))
         for k, (a, b, c, e) in {"lid": (-.15, .15, -.15, -.07), "under": (-.15, .15, .08, .2),
                                 "cheek": (-.15, .15, .3, .42)}.items()}
    hp = L - nd.gaussian_filter(L, d / 25)
    tex = float(box(hp, (x1 + x2) / 2, (y1 + y2) / 2, -.4, .4, -.85, -.6).std())
    return {"lid-cheek": m["lid"] - m["cheek"], "under-cheek": m["under"] - m["cheek"], "forehead_tex": tex,
            "eyes": [list(map(int, e)) for e in eyes]}


class MixedViewTransform(ValueError):
    """Two renders compared for colour / lightness were made under different view transforms (rule 5)."""


def view_of(lighting, default: str = "AgX") -> str:
    """The view transform a render was made under: a name as given, or a lighting dict's "view" (blender_scene's
    default AgX when it names none; flat / clay renders are "Standard")."""
    if isinstance(lighting, str):
        return lighting
    return str((lighting or {}).get("view") or default)


def same_view(a, b, what: str = "colour comparison") -> str:
    """(rule 5, codified) refuse a colour / lightness comparison between renders made under different view transforms
    (AgX vs Khronos PBR Neutral vs Standard): the transform alone moved a lid band ~8 L* and the cheek's b* x2 (s12),
    which reads as a texture fault. `a`, `b`: view names or lighting dicts. Returns the shared view."""
    va, vb = view_of(a), view_of(b)
    if va != vb:
        raise MixedViewTransform(f"{what}: the renders mix view transforms ({va!r} vs {vb!r}); render both under one "
                                 f"(game: GAME_LIGHT's {asset.GAME_LIGHT['view']!r})")
    return va


def game_light_view(lighting, what: str = "render") -> None:
    """(rule 5) a render lit by the GAME rig (GAME_LIGHT's lights) must use its view transform too: the game rig under
    AgX / Standard is not the game's picture, and comparing it with the shipped GLB's game render mixes transforms."""
    if isinstance(lighting, dict) and lighting.get("lights") == asset.GAME_LIGHT["lights"]:
        same_view(lighting, asset.GAME_LIGHT, f"{what} under the game light rig")


def _selftest_face_light_check():
    """Known answers on a synthetic front eyes render (pupils 270 px apart): the same render passes; a lid band 80
    grey levels darker is a lid-cheek WARNING; forehead stripes are a texture WARNING; mixed views are refused."""
    base = np.full((520, 520, 3), 200.0)
    for x in (130, 400):
        base[280:300, x - 10:x + 10] = 20.0
    lid = base.copy()
    for x in (130, 400):
        lid[250:271, x - 40:x + 40] = 120.0
    groove = base.copy()
    groove[60:125:8, 100:430] = 150.0
    v = ("Khronos PBR Neutral",) * 2
    ok = face_light_check(base, base, views=v)
    assert not any(ln.startswith("WARNING") for ln in ok), ok
    bad = face_light_check(base, lid, views=v)
    assert bad[0].startswith("WARNING") and "lid-cheek" in bad[0] and not bad[1].startswith("WARNING"), bad
    gr = face_light_check(base, groove, views=v)
    assert gr[2].startswith("WARNING") and "forehead" in gr[2], gr
    try:
        face_light_check(base, base, views=("AgX", asset.GAME_LIGHT))
        raise AssertionError("AgX vs PBR Neutral must be refused")
    except MixedViewTransform:
        pass


@validated.known_answer(_selftest_face_light_check)
def face_light_check(stage, shipped, label: str = "", *, views=None) -> list[str]:
    """The shipped head's render against the APPROVED head's stage render through the same camera and light (e.g.
    eyes_v0 photo / game): lid band and under-eye vs cheek within FACE_LIGHT_TOL L*, forehead texture within
    FACE_LIGHT_TEX_RATIO. Lines to log; WARNING lines name the numbers. (Garrett v6 / v7: lid-cheek -33 vs the approved
    -16 under the photo light: the blink map's lid_fold crease + occlusion; forehead 2.1 vs 1.2 in the game rig: s21's
    wrinkles in the normal map.) Eyes are found on the stage render and used for both (same camera). The two renders
    must share the light rig AND the view transform (game: GAME_LIGHT): a different view transform alone moved the
    lid band ~8 L* and the cheek's b* x2 (Garrett s12). views = (stage's, shipped's) view transform names or lighting
    dicts: REQUIRED, and different ones raise MixedViewTransform (rule 5)."""
    if views is None or len(views) != 2:
        raise ValueError("face_light_check: views=(stage view, shipped view) is required (rule 5: a comparison "
                         "across view transforms is refused, so each render must declare its own)")
    same_view(views[0], views[1], f"face light{(' ' + label) if label else ''}")
    a = face_light(stage)
    b = face_light(shipped, eyes=a["eyes"])
    out = []
    for k, tol in asset.FACE_LIGHT_TOL.items():
        bad = abs(b[k] - a[k]) > tol
        out.append(("WARNING " if bad else "") + f"face light{(' ' + label) if label else ''}: {k} {b[k]:.1f} L* vs the "
                   f"approved render's {a[k]:.1f} (tolerance {tol})" + (": the shipped maps darken / lighten it" if bad else ""))
    bad = b["forehead_tex"] > asset.FACE_LIGHT_TEX_RATIO * max(a["forehead_tex"], 0.5)
    out.append(("WARNING " if bad else "") + f"face light{(' ' + label) if label else ''}: forehead texture "
               f"{b['forehead_tex']:.2f} vs the approved render's {a['forehead_tex']:.2f} (at most x{asset.FACE_LIGHT_TEX_RATIO})"
               + (": grooves / wrinkles the approved head doesn't have (normal map)" if bad else ""))
    return out


def fold_form(name: str, v) -> float:
    """The most a skin fold moves the surface, in mm: its groove, its roll (the swell beside it), its platform, at its
    largest amount (a side's amount x the fold's)."""
    from . import skin_folds
    q = skin_folds.options({name: v}).get(name)
    if not q:
        return 0.0
    rl = skin_folds.RELIEF[name]
    a = q["amount"] * max([sd["amount"] for sd in q["sides"].values()] or [1.0])
    return a * max(rl["depth"] * q["depth"], (rl["roll"][2] * q["roll"]) if rl.get("roll") else 0.0,
                   rl["plat"][0] if rl.get("plat") else 0.0)


def fold_form_gate(spec: dict, log: list, approved: dict | None = None) -> dict:
    """(coordinator, Garrett s8) the approved-geometry rule for skin.folds: a fold whose relief is at most
    FOLD_FORM_MAX_MM ships (skin detail); a larger one, unless the approved head carries the same fold, is clamped to
    it (its roll and groove scaled: the crease line stays, the form change goes) with a WARNING naming it."""
    from . import skin_folds
    folds = (spec.get("skin") or {}).get("folds") or {}
    if not folds:
        return spec
    out_f, msgs = {}, []
    for name, v in folds.items():
        mm = fold_form(name, v)
        if mm <= asset.FOLD_FORM_MAX_MM + 1e-9 or (approved or {}).get(name) == v:
            out_f[name] = v
            msgs.append(f"{name} {mm:.2f} mm ok")
            continue
        q = {"amount": float(v)} if isinstance(v, (int, float)) else dict(v)
        rl = skin_folds.RELIEF[name]
        k = asset.FOLD_FORM_MAX_MM / mm
        if rl.get("roll"):
            q["roll"] = float(q.get("roll", 1.0)) * k
        q["depth"] = float(q.get("depth", 1.0)) * min(1.0, k * mm / max(fold_form(name, {**q, "roll": 0.0}), 1e-9))
        out_f[name] = q
        log.append(f"WARNING head: skin.folds.{name} changes the head's FORM ({mm:.2f} mm > {asset.FOLD_FORM_MAX_MM} mm: a roll / "
                   f"bag / overhang is head geometry, not approved): clamped to {fold_form(name, q):.2f} mm for the export "
                   "(Joe approves it into the head, or the skin thread lowers it)")
    if msgs:
        log.append("head: skin.folds within the skin-detail depth: " + ", ".join(msgs))
    return {**spec, "skin": {**spec["skin"], "folds": out_f}}


def hair_tier_default(spec: dict, role: str | None, log: list) -> dict:
    """LOD0's card tier: the groom's hair.export.tier, else the role's (ROLE_HAIR_TIER). Unset, hair.EXPORT_CARDS cut
    the cards to its 12000-triangle budget per lock (Garrett v3 / v4: 96 cards + cap, a helmet, while LOD1-3 got the
    tiers). Only card / strand grooms have tiers; no role keeps the old cut and says so."""
    h = spec.get("hair") or {}
    if h.get("style") not in ("cards", "strands") or (h.get("export") or {}).get("tier"):
        return spec
    tier = asset.ROLE_HAIR_TIER.get(role or "")
    if tier is None:
        log.append("WARNING hair: no hair.export.tier and no role: LOD0 cards cut to hair.EXPORT_CARDS' budget, not a "
                   "card tier (pass role= or set hair.export.tier)")
        return spec
    log.append(f"hair: LOD0 card tier {tier!r} from role {role!r} (hair.export.tier unset)")
    return {**spec, "hair": {**h, "export": {**(h.get("export") or {}), "tier": tier}}}
