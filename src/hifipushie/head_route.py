"""The route of a head from pictures, held by the tools (2026-11-01 readiness audit, blockers 3-7).

- KEYWORDS: the plain words people use for a job; find_tool weighs them like a tool's name. pin_block_in: a person +
  a picture lands on the start.
- refuse_off_route / require_solved: the fit tools refuse a block-in model (its moves are `mm:` block_in_steps); a hand
  step refuses a head no joint solve has seen, and any step refuses a posed model.
- pose: set_expression. An expression is a mix of GNM's expression parameters, added to the head's neutral on a NEW
  model. No sculpting: a shape with no parameters is refused.
- with_next: every human / likeness reply ends in `next:`. Tools that know their result better write their own.
"""
import copy
import inspect
import json
import re

from . import store

KEYWORDS = {
    "block_in_start": "portrait real person likeness",
    "set_expression": "pose expression finished head face smile frown blink surprise open mouth jaw posed arkit mix preset",
}


_PERSON = set("person people head face portrait character man woman someone likeness actor".split())
_PICTURE = set("photo photos photograph photographs picture pictures image images".split())
_ELSEWHERE = set("hair skin texture cloth clothes garment dress shirt jacket plant tree terrain".split())


def pin_block_in(query: str, scores: dict) -> dict:
    """A person + a picture, and no other domain named: the block-in leads. Pinned, not weighted: on word weights
    "a tree from a photo" came back to the head too."""
    w = set(re.findall(r"[a-z]+", query.lower()))
    if w & _PERSON and w & _PICTURE and not w & _ELSEWHERE:
        return {**scores, "block_in_start": 1.01 * max(scores.values()) + 1.0}
    return scores


def is_block_in(name: str) -> bool:
    """A model made by the block-in chain (its references carry the chain's record)."""
    p = store.HOME / name / "human_refs.json"
    return p.exists() and "blockin" in json.loads(p.read_text())


def refuse_off_route(name: str, tool: str) -> None:
    """The sequential fit tools don't run on a block-in model: they move the identity outside the chain's log, and
    nudge_human writes the local layer the block-in does without."""
    if is_block_in(name):
        raise ValueError(f"{tool}: REFUSED on {name}, a block-in model: hand moves are block_in_step(\"{name}\", "
                         '{"mm:<measure>": mm}, seen=..., why=...); face_ruler lists each gap with its `mm:` move, '
                         'gnm_controls(query="mm") every measure.')


def require_solved(name: str, hand_first: bool = False) -> None:
    """A hand step needs the joint solve first (and a neutral head): the step's vocabulary reads off a solved base."""
    posed = (store.load(name).get("base", {}).get("head") or {}).get("posed")
    if posed:
        raise ValueError(f"block_in_step: REFUSED on {name}: it is {posed['from']} posed by set_expression. Identity steps "
                         f"go on the neutral head: step from {posed['from']}, then pose the result.")
    p = store.HOME / name / "human_refs.json"
    bi = json.loads(p.read_text()).get("blockin") if p.exists() else None
    if bi is None or hand_first or "last_dc" in bi or "cam_done" in bi:
        return
    raise ValueError(f"block_in_step: REFUSED on {name}: no joint solve yet. Run block_in_solve(\"{name}\") first, 3-4 calls "
                     "until |dc| < 2: hand moves on the class mean get redone by it. hand_first=True overrides, for "
                     "pictures the solve can't read.")


def pose(name: str, mix, out: str | None = None) -> dict:
    """<out> = <name>'s head in the mix: the ARKit shapes' GNM expression coefficients summed on top of the head's own
    base.head.expression (a lips step's closing stays). -> {"out", "weights", "components", "largest"}."""
    from . import faceshapes
    sp = copy.deepcopy(store.load(name))
    head = (sp.get("base") or {}).get("head") or {}
    if head.get("posed"):
        raise ValueError(f"set_expression: {name} is {head['posed']['from']} posed; pose from {head['posed']['from']}, the "
                         "neutral (mixes don't stack).")
    weights = faceshapes.expression(mix)
    if not any(weights.values()):
        raise ValueError("set_expression: every weight is 0; the neutral is the model itself")
    face = faceshapes.face_of(sp)
    if not isinstance(face, faceshapes.GnmFace):
        raise ValueError(f"set_expression: {name} has no GNM head, so no expression parameters")
    none = sorted(k for k, v in weights.items() if v and (k in faceshapes.NO_COEFFS or faceshapes.family(k) == "look"))
    if none:
        raise ValueError(f"set_expression: {none} have no GNM expression parameters (eyeLook turns the eyeballs; cheekPuff "
                         "is an export-only shape): leave them out of the mix")
    label = mix if isinstance(mix, str) else "expression"
    out = out or f"{name}_{label}"
    if (store.HOME / out / "spec.json").exists():
        raise ValueError(f"{out} exists: choose out= (a posed head is a new model; {name} stays neutral)")
    ex = dict(head.get("expression") or {})
    for shape, w in faceshapes.playback(weights).items():
        if w:
            for k, c in face.shape_coeffs(shape).items():
                ex[k] = ex.get(k, 0.0) + w * c
    ex = {k: round(float(v), 5) for k, v in ex.items() if abs(v) > 1e-6}
    if is_block_in(name):
        from . import blockin as bi
        bi.fork(name, out)
        sp = store.load(out)
    sp["base"]["head"]["expression"] = ex
    sp["base"]["head"]["posed"] = {"from": name, "mix": weights}
    store.save(out, sp, f"set_expression from {name}: {label if isinstance(mix, str) else json.dumps(mix)}", checked=False)
    return {"out": out, "weights": weights, "components": len(ex), "largest": max(abs(v) for v in ex.values())}


def pose_text(name: str, r: dict) -> str:
    return (f"{r['out']}: {name} posed, written to base.head.expression ({r['components']} GNM components, largest "
            f"{r['largest']:.2f}): " + ", ".join(f"{k} {v:g}" for k, v in r["weights"].items() if v)
            + f". {name} stays neutral.\nnext: look(\"{r['out']}\", views=[\"front\", \"side\"]) beside a reference of the "
              "expression; change a weight with set_expression from the neutral.")


def _to(text: str, name: str) -> str:
    """The model a step wrote, from its reply (step_text's first line), else name."""
    m = re.search(r"^(\S+) \(round \d+, from ", text, re.M)
    return m.group(1) if m else name


def _solve_next(args: dict, text: str) -> str:
    to = _to(text, args["name"])
    m = re.search(r"\|dc\| ([\d.]+), \|c\|", text)
    if m and float(m.group(1)) >= 2.0:
        return f'block_in_solve("{to}") again (|dc| {float(m.group(1)):.2f}; until it is under 2)'
    return (f'face_ruler("{to}"), then block_in_look: name the single biggest difference and take a hand step '
            "(block_in_step)")


def _likeness_next(args: dict, text: str) -> str:
    if is_block_in(args["name"]):
        return 'take the largest miss to block_in_step with `mm:` or `sculpt:` (fit_likeness is refused here)'
    return "fit_likeness(name, stage), big to small" if args.get("targets") else "fix the first miss, then likeness(name) again"


def _lid_next(args: dict, text: str) -> str:
    to = _to(text, args["name"])
    return (f'eye_ruler("{to}") to confirm, then lip_read("{to}", match=True)' if args.get("match")
            else f'eye_ruler("{args["name"]}") for the numbers to trust; lid_read(match=True) is the eye step')


def _lip_next(args: dict, text: str) -> str:
    to = _to(text, args["name"])
    return (f'block_in_expression("{to}") if a picture is not neutral, then likeness("{to}")' if args.get("match")
            else f'lip_read("{args["name"]}", match=True) is the lips step')


NEXT = {
    "human": lambda a, t: 'for a person in pictures: block_in_start (guide(topic="block_in")); else look(name) beside the description',
    "measure_human": lambda a, t: ("block_in_step with the `mm:` move for one gap" if is_block_in(a["name"])
                                   else "change ONE thing (fit_human), then measure_human(name, since=<version>)"),
    "fit_human": lambda a, t: "read UNINTENDED, then look(name) at the whole figure",
    "nudge_human": lambda a, t: "read UNINTENDED, then look(name) at the whole figure",
    "human_reference": lambda a, t: f'block_in_start("<new name>", refs="{a["name"]}", sex=...): the head comes from there',
    "block_in_start": lambda a, t: ("block_in_solve (the joint step; its first call lays the cameras on this head), 3-4 calls "
                                    "until |dc| < 2; then squint at the sheet and name the single biggest difference in "
                                    "masses and planes"),
    "block_in_look": lambda a, t: ("name the single biggest difference; gnm_controls(phrase=...) gives the move; "
                                   "block_in_step takes it, 0.3-0.7 sd"),
    "block_in_step": lambda a, t: f'block_in_look("{_to(t, a["name"])}", read=..., keep=...), then step from the better head',
    "block_in_solve": _solve_next,
    "block_in_expression": lambda a, t: f'likeness("{_to(t, a["name"])}"), the checklist after the block-in',
    "face_ruler": lambda a, t: "block_in_step with the largest row's `mm:` move, skipping rows inside their error; all inside: lid_read(match=True)",
    "eye_ruler": lambda a, t: 'set the orbit first (face_ruler\'s ORBIT rows); then lid_read(name, match=True)',
    "lid_read": _lid_next,
    "lip_read": _lip_next,
    "brow_read": lambda a, t: 'block_in_look(name, focus="eyes"): judge it beside the picture',
    "gnm_controls": lambda a, t: "block_in_step with the control you picked (`gnm:`, `mm:` or `sculpt:`), one move",
    "likeness": _likeness_next,
    "fit_likeness": lambda a, t: "judge the panels, then likeness(name), or the next stage",
    "likeness_points": lambda a, t: "block_in_solve or likeness(name): both read these points",
    "character_read": lambda a, t: "fill the form or diff the read; likeness(name) is the measured side",
    "project_reference": lambda a, t: "where it smears the geometry is wrong: block_in_step there",
    "texture_from_reference": lambda a, t: "judge the head beside the pictures; remove=True before anything ships",
    "reference_brief": lambda a, t: "get the pictures, then check_references on them",
    "check_references": lambda a, t: 'block_in_start(name, refs=[{"image": ..., "yaw": ...}, ...], sex=..., age=...)',
}


def with_next(fn, a: tuple, k: dict, result):
    """A tool's reply with its `next:` line (after any it has none of its own), for the tools in NEXT."""
    make = NEXT.get(fn.__name__)
    if make is None:
        return result
    text = result if isinstance(result, str) else next((x for x in reversed(result) if isinstance(x, str)), "") \
        if isinstance(result, list) else None
    if text is None or "\nnext:" in text.lower() or text.lower().startswith("next:"):
        return result
    args = inspect.signature(fn).bind_partial(*a, **k).arguments
    line = text + ("\n" if text else "") + "next: " + make(args, text) + "."
    if isinstance(result, str):
        return line
    out = list(result)
    for i in range(len(out) - 1, -1, -1):
        if isinstance(out[i], str):
            out[i] = line
            return out
    return [*out, line]
