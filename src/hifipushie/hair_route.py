"""The hair route: what walks an agent down one correct path using only the tools (hair readiness audit 2026-11-01).

The rules a tool can carry: which style a call gets, what it refuses (`check_style_arg`, `check_export`), the warnings
it adds (`style_warning`, `shells_warning`, `head_warning`) and the `next:` line each hair tool ends with. server.py
only calls these, so the route is read and changed here. The path itself is the block at the top of hair_guide.md.

Hair modules import this lazily and it imports `hair` lazily (hair.validate needs the checks, the checks need
HairError).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

# Every key the code reads from spec["hair"]["export"]; hair.validate refuses the rest ({"styel": "shells"} used to
# pass and silently build cards).
EXPORT_KEYS = {
    "segments", "sides",  # solid locks (hair.EXPORT)
    "triangles", "tier", "cap_step", "alpha_cutoff", "shadow_proxy",  # hair.EXPORT_CARDS
    "role", "tier_triangles", "tier_drawn_max",  # budgets
    "card_gain", "card_sat", "tone_front", "tone_back", "headroom", "tier_look",  # the cards' look
    "style", "shells", "fade", "constants", "strands",  # short cuts, the strand file
}
EXPORT_STYLES = ("cards", "shells")
SHELL_KEYS = {"heights", "base", "cover", "tiers"}
HEAD_MM = 0.5  # the head hash reads the scalp to this: float noise is no head change


def _error(msg: str):
    from . import hair
    return hair.HairError(msg)


def check_export(h: dict) -> None:
    """hair.validate: spec["hair"]["export"] names only keys the code reads."""
    ex = h.get("export") or {}
    bad = set(ex) - EXPORT_KEYS
    if bad:
        raise _error(f"hair export: unknown keys {sorted(bad)} (have {', '.join(sorted(EXPORT_KEYS))})")
    if str(ex.get("style", "cards")) not in EXPORT_STYLES:
        raise _error(f"hair export style is one of {', '.join(EXPORT_STYLES)}")
    bad = set(ex.get("shells") or {}) - SHELL_KEYS
    if bad:
        raise _error(f"hair export shells: unknown keys {sorted(bad)} (have {', '.join(sorted(SHELL_KEYS))})")


def check_style_arg(style: str | None) -> None:
    """groom_hair's style: "cards" is internal, look_hair(tier=...) and the exports set it themselves."""
    if style == "cards":
        raise _error('groom_hair style is "strands" (realistic) or "locks" (stylised). Cards are cut from the strands: '
                     'keep "strands", judge them with look_hair(name, tier="main"), ship them with export_asset')


def default_style(spec: dict) -> None:
    """A realistic human's first groom is strands. Only with no style and no locks yet: a stored style wins, and a
    groom already grown solid stays solid until someone says otherwise (style_warning says it)."""
    h = spec.setdefault("hair", {})
    if h.get("style") is None and not h.get("locks") and spec.get("base"):
        h["style"] = "strands"


def is_short(name: str, spec: dict) -> bool:
    """The mean lock of a loose groom is under hair.MASS_MIN: the test cards_job uses for a short cut."""
    from . import hair
    h = spec.get("hair") or {}
    locks = h.get("locks") or {}
    if not locks or not (h.get("groom") or {}).get("loose"):
        return False
    sc = hair.scalp(name, spec)
    lens = []
    for lk in locks.values():
        if len(lk.get("pts") or []) >= 2:
            lens.append(float(np.linalg.norm(np.diff(hair.lock_world(sc, lk, lk["pts"]), axis=0), axis=1).sum()))
    return bool(lens) and float(np.mean(lens)) < hair.MASS_MIN


def style_warning(spec: dict) -> str:
    """Solid locks on a realistic base: the stylised path, by choice or by an old default."""
    h = spec.get("hair") or {}
    if spec.get("base") and h.get("locks") and h.get("style", "locks") == "locks":
        return ('WARNING style "locks" (solid sculpted) on a realistic base: that is the stylised path. Realistic hair: '
                'groom_hair(name, style="strands", replace=True)')
    return ""


def shells_warning(name: str, spec: dict) -> str:
    """hair.export.style "shells" does nothing on a groom that isn't short."""
    h = spec.get("hair") or {}
    if (h.get("export") or {}).get("style") == "shells" and h.get("locks") and not is_short(name, spec):
        return 'WARNING hair.export.style "shells" is ignored: only a short cut (mean lock under 6 cm) gets shells'
    return ""


def head_key(sc) -> str:
    """The head a groom was grown on: its scalp (centre and radii) to HEAD_MM."""
    q = HEAD_MM / 1000.0
    a = np.round(np.concatenate([np.ravel(sc.C), np.ravel(sc.R)]) / q).astype(np.int64)
    return hashlib.sha1(a.tobytes()).hexdigest()[:16]


def head_warning(name: str, spec: dict | None = None) -> str:
    """hair.head against the model's head now. A groom with no stored hash (grown before it existed) says nothing."""
    from . import hair, store
    spec = store.load(name) if spec is None else spec
    was = (spec.get("hair") or {}).get("head")
    if not was or was == head_key(hair.scalp(name, spec)):
        return ""
    return (f"WARNING the head changed under this groom: {name}'s hair was grown on another head. Re-seat or regrow it "
            "and judge hairline, stand-off and coverage again before trusting anything here")


def _call(tool: str, **args) -> str:
    return f'call_tool("{tool}", {json.dumps(args)})'


def _tail(lines: list[str], step: str) -> str:
    """The warnings, then the one `next:` line, so the reply ends with what to do."""
    return "\n".join([ln for ln in lines if ln] + [f"next: {step}"])


def groom_next(name: str, spec: dict) -> str:
    from .scene import blend_path
    h = spec.get("hair") or {}
    around = _call("look_hair", name=name, views=["around"])
    warn = [style_warning(spec), shells_warning(name, spec), head_warning(name, spec)]
    first = "" if blend_path(name).exists() else _call("sync", name=name) + " once, then "
    if h.get("stage") == "mass":
        step = (f'{first}{around}: judge the silhouette beside the reference; when it matches, '
                f'{_call("groom_hair", name=name, stage="locks")}')
    elif h.get("style", "locks") == "locks":
        step = f'{first}{around}; stylised locks have their own rules: guide(topic="hair_locks")'
    elif is_short(name, spec) and (h.get("export") or {}).get("style") != "shells":
        step = (f'{first}{around}; a short cut ships as shells: edit_model("{name}", [{{"op": "set", "kind": "hair", '
                f'"name": "export", "value": {{"style": "shells"}}}}]) (guide(topic="hair_short"))')
    else:
        step = f"{first}{around} beside the reference, every side"
    return _tail(warn, step)


def look_next(name: str, spec: dict, tier: str | None) -> str:
    """spec: the stored one (look_hair forces style "cards" on its copy for a tier)."""
    h = spec.get("hair") or {}
    warn = [style_warning(spec), shells_warning(name, spec), head_warning(name, spec)]
    if tier:
        step = (f'judge the {tier} tier beside the strand render of the same view (cards against the groom, the groom '
                f'against the photo), then {_call("export_asset", name=name, out_dir="<dir>", role="hero")} ships the '
                "character (role: hero / main_npc / secondary_npc / crowd); export_hair is the hair alone")
    elif h.get("stage") == "mass":
        step = (f'silhouette right beside the reference: {_call("groom_hair", name=name, stage="locks")}; wrong: '
                "change the groom's shape, not a strand dial")
    elif h.get("style", "locks") == "locks":
        step = "judge it beside the reference; shape changes go through groom_hair (fuller, trim) or the locks"
    else:
        step = (f'judge beside the reference (views "ref0".. are its fitted cameras); fix the worst fault at its stage '
                f'(shape, strands, colour), then {_call("look_hair", name=name, tier="main")} shows the game cards')
    return _tail(warn, step)


def export_next(name: str, out_dir, tiers: list[str]) -> str:
    glb = Path(out_dir).expanduser() / f"{name}_hair_{tiers[0]}.glb"
    return _tail([head_warning(name)],
                 f'judge each tier as the engine draws it: {_call("judge_asset", glb=str(glb))}, beside the strand '
                 f'renders. This is the hair alone; {_call("export_asset", name=name, out_dir="<dir>", role="hero")} '
                 "ships the character with it")


def reader_next(name: str, out: str, read_only: bool) -> str:
    dst = out or name
    if read_only:
        return "next: read these lines as measurements, then call hair_from_reference again without read_only to set the start"
    spec = _load(dst)
    tied = _call("tie_hair", name=dst, style={"tie": "low"})
    around = _call("look_hair", name=dst, views=["around"])
    step = (f'write the description first (guide(topic="hair"), Stage 0), then build from it: tied hair {tied}; loose or '
            f'short: look at the start with {around} and patch it with groom_hair')
    return _tail([head_warning(dst, spec)], step)


def compare_next(name: str) -> str:
    return (f'next: apply the colour step to look with {_call("groom_hair", name=name, look={"seen": "<colour>"})}, '
            "then look_hair through the same views and compare again")


def reference_next(name: str, applied: bool) -> str:
    if applied:
        return (f'next: {_call("groom_hair", name=name)} grows the traced groom, then '
                f'{_call("look_hair", name=name, views=["ref0"])} beside the picture')
    return (f'next: check the fit on the sheet, then {_call("hair_reference", name=name, apply=True)} carries the trace '
            "onto the groom. This hand trace is an optional finer fit: hair_from_reference is the start")


def _load(name: str) -> dict:
    from . import store
    return store.load(name)
