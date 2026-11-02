"""The skin route as tools carry it (readiness audit 2026-11-01): a blind agent gets one path and its gate from the
replies alone. What a reply must say that a guide can't enforce lives here: the read's route (photographs -> the atlas
and its layer stack, paintings by flag), a stale atlas, the keys that do nothing under a stack (r5-r8 lost rounds to
them), fold relief and the approved head before the 24 GB export finds them, the "next:" line of every skin tool.

The route: approved head -> forms into the head -> skin(tone, age) -> skin_from_reference -> brow_read(match=True) ->
hand finish with skin -> look_skin(beside=<region>) -> review_view, one region per call."""
from __future__ import annotations

import copy
import json
import time

from . import store

ROUTE = ("Skin: approved head -> forms into the head -> skin (age, tone) -> skin_from_reference (photographs: atlas + "
         "layer stack) -> brow_read(match=True) -> hand finish with skin -> look_skin(beside=<region>) -> review_view, "
         "one region per call")
STEPS = ["skin", "skin_from_reference", "brow_read", "look_skin"]
# find_tool: words that mean the skin, whatever other tool's text also has them ("stubble" is a groom_hair word too)
FIND_WORDS = {"skin", "por", "stubble", "makeup", "cosmet", "freckl", "wrinkl", "blemish", "mole"}
REGIONS = ("face", "forehead", "brows", "eye", "cheek", "nose", "mouth", "jaw")   # look_skin(beside=...), order of review
BODY_ONLY = ("tone",)   # under a stack the face's colour is the stack's: these move what it doesn't cover (neck, body)
DIFF_SECONDS = 25.0   # no_effect's budget: each key is one build of the layers, a skin edit must stay quick
NOT_LAYERS = ("folds", "hair", "eyes", "stack", "projection", "only", "part")  # geometry or strands: no layer diff tells


def find_bias(q: set, scores: dict) -> dict:
    """find_tool: a skin query starts the skin route, and the superseded decal route is not offered for it."""
    if not q & FIND_WORDS:
        return scores
    out = {t: s for t, s in scores.items() if t != "texture_from_reference"}
    out["skin"] = 1.01 * max(out.values(), default=0.0) + 0.01
    return out


def has_refs(name: str) -> bool:
    return (store.HOME / name / "human_refs.json").exists()


def _atlas(spec: dict) -> bool:
    """A de-lit atlas the read can use (skin_read.atlas_source, without opening the images)."""
    from . import skin_project
    pj = (spec.get("skin") or {}).get("projection")
    return bool(isinstance(pj, dict) and pj.get("albedo") and pj.get("confidence") and pj.get("delight", True)
                and not skin_project.stale(spec))


def stale_line(spec: dict) -> str:
    from . import skin_project
    if not skin_project.stale(spec):
        return ""
    return ("STALE: skin.projection was made on another head shape, so no read uses it: skin_from_reference "
            "projects again\n")


def plan_read(spec: dict, project: bool | None, painting: bool, read_only: bool) -> tuple[bool, str]:
    """skin_from_reference's route: (run the projection first?, a line for the reply). Default for photographs: the
    atlas, reused when it is fresh; the per-picture read needs painting=True (brushwork lands in an atlas)."""
    if read_only and project:
        raise ValueError("skin_from_reference: read_only=True changes nothing, so project=True would be ignored: drop one")
    if painting and project:
        raise ValueError("skin_from_reference: painting=True is the per-picture read: an atlas of a painting bakes its brushwork")
    line = stale_line(spec)
    if read_only:
        return False, line
    if painting:
        return False, line + "route: per-picture read (painting=True)\n"
    if project is not True and _atlas(spec):
        return False, "route: the fresh atlas on the model (project=True remakes it)\n"
    if project is False:
        raise ValueError("skin_from_reference: project=False needs a fresh atlas on the model; the per-picture read is for "
                         "paintings only: pass painting=True, or leave project alone for photographs")
    if not (spec.get("skin") or {}).get("tone"):
        raise ValueError("skin_from_reference: no skin.tone: the atlas takes the model's tone as its exposure, so set it "
                         "first: skin(name, {\"tone\": {\"fitzpatrick\": ...}, \"age\": ...}). Reading it needs no key: "
                         "read_only=True")
    return True, line + "route: de-lit atlas, then the layer stack (photographs)\n"


def _live(spec: dict, J: dict) -> tuple[dict, dict]:
    """What shows on a stacked face: the layers but the coloured "_pre" ones (composited into the base the stack paints
    over; skin.layers' comment has the lever checks), and the base's channels but its colour."""
    from . import skin
    sk = spec["skin"]   # (its map layers and the joints: they don't depend on these keys, and cost most of a build)
    light = {**spec, "skin": {**sk, "stack": {**sk["stack"], "layers": []}}}
    ls = {k: v for k, v in skin._build(light, J).items() if not (v.get("_pre") and "color" in v)}
    base = (skin.part_base(spec) or (None, {}))[1]
    return ls, {k: v for k, v in base.items() if k != "color"}


def _leaves(patch: dict) -> list[tuple]:
    out = []
    for k, v in patch.items():
        if k in NOT_LAYERS:
            continue
        out += [(k, q) for q in v] if isinstance(v, dict) and v else [(k,)]
    return out


def _get(d: dict, path: tuple):
    for k in path:
        d = (d or {}).get(k) if isinstance(d, dict) else None
    return d


def _with(sk: dict, path: tuple, v) -> dict:
    s = copy.deepcopy(sk)
    d = s
    for k in path[:-1]:
        d = d.setdefault(k, {})
    if v is None:
        d.pop(path[-1], None)
    else:
        d[path[-1]] = v
    return s


def no_effect(old: dict, new: dict, patch: dict) -> str:
    """The keys of this patch that change nothing on a stacked face, by diffing what shows with and without each."""
    if not ((new.get("skin") or {}).get("stack")) or not patch:
        return ""
    from . import skin
    dead, body, late = [], [], []
    t0 = time.monotonic()
    J = skin._joints(new)
    now = json.dumps(_live(new, J), sort_keys=True, default=str)
    for path in _leaves(patch):
        was, is_ = _get(old.get("skin"), path), _get(new.get("skin"), path)
        if was == is_:
            continue
        if path[0] in BODY_ONLY:
            body.append(".".join(path))
        elif time.monotonic() - t0 > DIFF_SECONDS:
            late.append(".".join(path))
        elif json.dumps(_live({**new, "skin": _with(new["skin"], path, was)}, J), sort_keys=True, default=str) == now:
            dead.append(".".join(path))
    out = ""
    if dead:
        out += (f"NO EFFECT under this skin's stack (the colour is the stack's): {', '.join(dead)}. Levers that do work: "
                "stack_edit, zones.lid_shade / under_eye_shade, hair.brows.shadow, lips.over_stack: true\n")
    if body:
        out += f"BODY ONLY under the stack (the face keeps the stack's colour): {', '.join(body)}\n"
    if late:
        out += f"not checked against the stack (out of time): {', '.join(late)}: set fewer keys a call\n"
    return out


def stack_edit(spec: dict, arg) -> tuple[dict, str]:
    """skin(stack_edit=...): skin_layers.edit by name ("blush", ["pale", "tired"]) or {layer: strength} (1 = as
    measured). Returns the spec and the reply's line."""
    from . import skin_layers
    st = (spec.get("skin") or {}).get("stack")
    if not st:
        raise ValueError("skin: stack_edit needs skin.stack: skin_from_reference makes it")
    if isinstance(arg, str):
        arg = [arg]
    names = [a for a in arg] if isinstance(arg, list) else []
    strengths = dict(arg) if isinstance(arg, dict) else {}
    have = {l["name"].rstrip("+") for l in st["layers"]}
    bad = [n for n in names if n not in skin_layers.EDITS] + [k for k in strengths if k not in have]
    if bad:
        raise ValueError(f"skin: stack_edit: unknown {bad}: named edits {', '.join(skin_layers.EDITS)}; layers {', '.join(sorted(have))}")
    return skin_layers.edit(spec, *names, **strengths), (f"stack_edit {arg}: every other layer back at its measured "
                                                         "strength (edits don't add up: pass them together)\n")


def form_lines(spec: dict) -> str:
    """Fold relief in mm against what skin may carry, and the head against the approval record: the two export gates,
    said here (they used to fire only in the export, after a 24 GB job)."""
    from . import asset
    out = ""
    folds = (spec.get("skin") or {}).get("folds") or {}
    if folds:
        mm = {k: asset.fold_form(k, v) for k, v in folds.items()}
        out += "fold relief: " + ", ".join(f"{k} {v:.2f} mm" for k, v in mm.items()) + f" (skin carries <= {asset.FOLD_FORM_MAX_MM:g} mm)\n"
        over = [k for k, v in mm.items() if v > asset.FOLD_FORM_MAX_MM + 1e-9]
        if over:
            out += (f"WARNING {', '.join(over)}: past that it is head FORM: the export clamps it unless the approved head "
                    "has the same fold. Lower it, or put the form in the head and have the head approved\n")
    why = head_unapproved(spec)
    return out + (f"WARNING head: {why}: skin laid now sits on forms nobody approved, and a head change makes the atlas "
                  "stale. Only Joe or the coordinator approves\n" if why else "")


def head_unapproved(spec: dict) -> str:
    """Why this model's base.head isn't an approved head ("" when it is, or the model has no head)."""
    from . import asset
    head = (spec.get("base") or {}).get("head")
    if not head:
        return ""
    want = spec["base"].get("head_approved")
    try:
        rec = json.loads((store.HOME / "approved.json").read_text()).get("approved") or {}
    except (OSError, ValueError):
        rec = {}
    keys = [want] if want else [k for k in rec if k.startswith("head/")]
    strip = lambda h: {k: v for k, v in (h or {}).items() if k not in asset.HEAD_KEEP_FROM_BUILD}  # noqa: E731
    for k in keys:
        try:
            other = json.loads((store.HOME / rec[k]["model"] / "spec.json").read_text())
        except (KeyError, OSError, ValueError):
            continue
        if strip((other.get("base") or {}).get("head")) == strip(head):
            return ""
    return f"base.head is not the approved {want}" if want else "base.head is no approved head in approved.json"


def refuse_decals(spec: dict) -> None:
    if (spec.get("skin") or {}).get("stack"):
        raise ValueError("texture_from_reference: this model's skin is a measured stack (skin.stack): decals would paint the "
                         "picture's light and hair over it. Change it with skin(stack_edit=...) or skin_from_reference")


def refuse_photo_skin(spec: dict) -> None:
    """The export's check: skin_project(opacity > 0) is a judging overlay; the photo's pixels never ship."""
    pj = (spec.get("skin") or {}).get("projection")
    if isinstance(pj, dict) and float(pj.get("opacity", 0) or 0) > 0:
        raise ValueError(f"skin.projection.opacity is {pj['opacity']}: that overlay is the photograph itself and photo pixels "
                         "never ship: skin_project(opacity=0) keeps the atlas as a measurement")


def _beside(name: str, region: str = "eye") -> str:
    return f"look_skin(\"{name}\", beside=\"{region}\")"


def next_look(args: dict, rest: list) -> str:
    """look_skin(beside=)'s closing line: the review_view call, ready to run."""
    from . import next_steps
    how = "call_tool(\"review_view\", " + json.dumps(args) + f"), then the other regions: {', '.join(rest)}"
    return next_steps.after_look("skin", True, how=how)


def after_look(name: str) -> str:
    """look_skin's closing line (a look with no reference beside it)."""
    from . import next_steps
    how = f"{_beside(name)} renders one region of model and reference at the same framing ({', '.join(REGIONS)})"
    return next_steps.after_look("skin", has_refs(name), how=how if has_refs(name) else "")


def after_skin(name: str, old: dict, new: dict, patch: dict, edited: str = "") -> str:
    """skin's closing lines."""
    t = "\n" + edited + no_effect(old, new, patch) + stale_line(new) + form_lines(new)
    sk = new.get("skin") or {}
    if sk.get("only"):
        return t + f"next: look_skin(\"{name}\", views=[\"eye\"]) to judge the groups it set"
    if has_refs(name) and not sk.get("stack"):
        return t + f"next: skin_from_reference(\"{name}\") measures the pictures (read_only=True to see the read first)"
    if has_refs(name):
        return t + f"next: {_beside(name)}: the region this change touched, beside its reference crop"
    return t + f"next: look_skin(\"{name}\", views=[\"bust\"], flat=True), then the lit close-ups; no fitted references, so nothing proves it's the person"


def after_read(name: str, read_only: bool = False, painting: bool = False) -> str:
    """skin_from_reference's closing lines."""
    if read_only:
        return f"\nnext: check the read by eye, then skin_from_reference(\"{name}\") applies it (read_only=False)"
    sp = store.load(name)
    # (the atlas route skips the irises and the folds: say so, the guide's list is the per-picture read's)
    skip = "" if painting else "\nnot read on this route: irises (skin.eyes.iris), folds (skin.folds), roughness, pores: set them by hand against the crops"
    return (f"\n{stale_line(sp)}{form_lines(sp).rstrip()}{skip}\nnext: brow_read(\"{name}\", match=True) places the brows; "
            f"then {_beside(name, 'brows')}")


def after_project(name: str, opacity: float = 0.0, removed: bool = False, report_only: bool = False) -> str:
    """skin_project's closing lines."""
    if removed:
        return f"\nnext: skin_from_reference(\"{name}\") makes a new atlas"
    if report_only:
        return f"\nnext: skin_project(\"{name}\") saves it, or put the forms the report names into the head first"
    sp = store.load(name)
    t = "\n" + form_lines(sp)
    if opacity > 0:
        return t + (f"opacity {opacity:g}: a judging overlay; the export refuses it\n"
                    f"next: {_beside(name)} to judge, then skin_project(\"{name}\", opacity=0)")
    return t + f"next: skin_from_reference(\"{name}\") fits the skin to this atlas"


def after_brows(name: str, matched: bool) -> str:
    if matched:
        return f"next: {_beside(name, 'brows')} judges them beside the reference"
    return f"next: brow_read(\"{name}\", match=True) fits them to the picture's hair band"


def after_reference() -> str:
    return "next: read the reference first (guide(topic=\"skin\"), stage 0), then skin(name, {\"age\": ..., \"tone\": ...})"
