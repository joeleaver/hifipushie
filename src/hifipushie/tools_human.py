"""Realistic humans: the body and head from parameters, measuring and fitting, the artist block-in for a head from
pictures, expressions and the face rulers."""
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

from PIL import Image as PILImage

from . import store
from .spec import empty_spec
from .mcp_app import mcp
from .tool_common import _png, _spec_arg
from .tools_model import look

@mcp.tool(structured_output=False)
def human(name: str, age: float = 30, sex: float | str = 0.5, weight: float = 0.5, muscle: float | None = None,
          height: float | None = None, seed: int | None = None, outfit: str | None = None,
          tone: float | dict | None = None, skin: dict | bool | None = None, head: dict | None = None,
          bust: float | None = None, firmness: float | None = None, note: str = "", source: str = "human",
          style: str | dict | None = None) -> str:
    """A whole person from a description, saved as a model: human("mia", age=3, sex="female"). Measured proportions for
    age; dressed. Params: age, sex, weight, muscle, height, seed (the face), outfit, tone, skin, head, bust,
    firmness, source ("human" = one mesh, the default | "makehuman"), style (one-mesh style sheet or sliders). Details:
    guide(topic="human")."""
    from . import humans
    sp = humans.spec(age=age, sex=sex, weight=weight, muscle=muscle, height=height, seed=seed, outfit_kind=outfit,
                     tone=tone, skin=_spec_arg(skin) if isinstance(skin, str) else skin, head=_spec_arg(head) if head else None,
                     bust=bust, firmness=firmness, source=source, style=_spec_arg(style) if isinstance(style, str) and style.strip().startswith("{") else style)
    full = {**empty_spec(), **sp}
    v = store.save(name, full, note or f"human: {humans.stage(float(age))}, {age:g} y")
    return (f"saved {name} v{v}: {humans.describe(full)}\n"
            f"parts: {', '.join(full['parts'])}. look(\"{name}\") for the figure, look_skin(\"{name}\") for the skin; "
            f"guide(topic=\"skin\") stage 0 says what the body and head keys do.")


def _human_base(name: str) -> tuple:
    sp = store.load(name)
    b = sp.get("base") or {}
    if (b.get("body") or {}).get("source") != "human":
        raise ValueError(f'{name}: not a one-mesh human (base.body.source "human"). Make one with human(name, ..., source="human"); '
                         "the measuring and fitting tools read the one mesh's own landmarks.")
    return sp, b


def _human_figure(name: str, spec_after: dict | None) -> PILImage.Image | None:
    """The whole DRESSED figure before | after (front + side), through `look`: an edit is judged on the person, not on
    the eye that was edited. A result that wasn't saved is built under a scratch name and removed."""
    try:
        ims = []
        for label, nm in (("before", name), ("after", None)):
            if nm is None:
                if spec_after is None:
                    break
                nm = name + "__try"
                store.save(nm, spec_after, "scratch: a fit's result for its whole-figure picture")
            r = look(nm, views=["front", "side"], size=360, resolution=220)
            im = PILImage.open(io.BytesIO(next(x for x in r if not isinstance(x, str)).data)).convert("RGB")
            from PIL import ImageDraw
            ImageDraw.Draw(im).text((44, 26), f"whole figure, {label}", fill=(255, 255, 160))
            ims.append(im)
        out = PILImage.new("RGB", (sum(i.width for i in ims), max(i.height for i in ims)), (30, 32, 36))
        x = 0
        for im in ims:
            out.paste(im, (x, 0))
            x += im.width
        return out
    except Exception as e:  # noqa: BLE001  (the picture must not lose the fit's report)
        return None
    finally:
        shutil.rmtree(store.HOME / (name + "__try"), ignore_errors=True)


def _human_apply(name: str, sp: dict, new_base: dict, rep: dict, note: str, force: bool, save: bool, st0, focus=None,
                 figure: bool = True) -> list:
    from . import humanfit
    from . import humanfit_sheet
    ok = rep["integrity"]["ok"]
    fig = _human_figure(name, {**sp, "base": new_base}) if figure else None
    text = humanfit_sheet.report_text(rep)
    saved = ""
    if save and (ok or force):
        v = store.save(name, {**sp, "base": new_base}, note)
        saved = f"saved {name} v{v}" + ("" if ok else " (FORCED over a broken mesh)") + f". revert(\"{name}\", {v - 1}) undoes it."
    elif save:
        saved = "NOT SAVED: the mesh would be broken (the lines above). Ask for less, release fewer measures, or force=True."
    else:
        saved = "not saved (save=False): a dry run."
    im = humanfit_sheet.head_sheet(st0, humanfit.state(new_base), focus=focus)
    if fig is not None:
        both = PILImage.new("RGB", (max(im.width, fig.width), im.height + fig.height), (30, 32, 36))
        both.paste(im, (0, 0))
        both.paste(fig, (0, im.height))
        im = both
    return [_png(im), text + "\n" + saved + "\n(The picture: head before | after | where vertices moved"
            + ("; under it the whole dressed figure before | after. Judge the person, not the part you edited.)" if fig is not None
               else ". look(name) shows the whole dressed figure: look at it before going on.)")]


@mcp.tool(structured_output=False)
def measure_human(name: str, since: int | None = None, picture: bool = True):
    """Measure a one-mesh human: named body (cm) and face (mm) measures, ratios, integrity gates and a head picture.
    since = an earlier version: what changed (UNINTENDED flags). Measure before each change. Details:
    guide(topic="measure_human")."""
    from . import humanfit
    from . import humanfit_integrity, humanfit_sheet
    sp, b = _human_base(name)
    st = humanfit.state(b)
    text = humanfit_integrity.verdict(humanfit_integrity.integrity(b, st)) + "\n" + humanfit_integrity.table(st["measures"])
    from . import onemesh_report
    text += "\n" + onemesh_report.attach_report(b)["text"]  # (headbody) head size, heads tall, the neck at the seam ring
    st0 = None
    if since is not None:
        old = json.loads((store.HOME / name / "history" / f"{int(since):04d}.json").read_text())
        old = old.get("spec", old)
        st0 = humanfit.state(old["base"])
        text += f"\nsince v{since}:\n" + humanfit_integrity.effects_text(humanfit_integrity.side_effects(st0, st, set()), top=30)
    from . import head_route
    if not head_route.is_block_in(name):
        text += "\nlandmarks for nudge_human: " + ", ".join(humanfit.LANDMARKS) + ", eye.L, eye.R"
    if not picture:
        return text
    return [_png(humanfit_sheet.head_sheet(st0, st) if st0 is not None else humanfit_sheet.head_sheet(st)), text]


@mcp.tool(structured_output=False)
def fit_human(name: str, set: dict | str, free: list[str] | None = None, release: list[str] | None = None,
              force: bool = False, save: bool = True, note: str = "", figure: bool = True):
    """Set measures on a one-mesh human and let a minimal-change solver find the sliders: set = {"nose_width": 34 |
    "+2" | "x0.95", "a/b": ratio}. free (["identity"] | "body"), release, force, figure, save, note. Replies
    INTEGRITY, UNINTENDED, before | after; a broken result isn't saved. Details: guide(topic="fit_human")."""
    from . import head_route, humanfit
    from . import humanfit_solve
    head_route.refuse_off_route(name, "fit_human")
    sp, b = _human_base(name)
    want = _spec_arg(set) if isinstance(set, str) else dict(set)
    st0 = humanfit.state(b)
    nb, rep = humanfit_solve.solve(b, want, free=tuple(free or ("identity",)), force=force, release=tuple(release or ()))
    pts = sorted({i for k in want for p in k.split("/") if p.strip() in humanfit.FACE for i in humanfit._points(p.strip())})
    focus = st0["L"][pts].mean(0) if pts else None
    return _human_apply(name, sp, nb, rep, note or f"fit_human {json.dumps(want)}", force, save, st0, focus, figure)


@mcp.tool(structured_output=False)
def nudge_human(name: str, landmark: str, move: list[float] | None = None, to: list[float] | None = None,
                radius: float = 0.015, force: bool = False, save: bool = True, note: str = "", figure: bool = True):
    """Move ONE face landmark by `move` [x,y,z] m or `to` a point; others held, mirror follows; what the sliders can't
    do becomes a local correction (radius) and is reported. Same reply as fit_human. Details:
    guide(topic="nudge_human")."""
    from . import head_route, humanfit
    from . import humanfit_solve, humanfit_views
    head_route.refuse_off_route(name, "nudge_human")
    sp, b = _human_base(name)
    st0 = humanfit.state(b)
    nb, rep = humanfit_solve.nudge(b, landmark, move=move, to=to, radius=radius, force=force)
    return _human_apply(name, sp, nb, rep, note or f"nudge_human {landmark}", force, save, st0,
                        st0["L"][humanfit_views.point_index(landmark)], figure)


@mcp.tool(structured_output=False)
def human_reference(name: str, views: list[dict] | str, fit: bool = True, free: list[str] | None = None,
                    force: bool = False, save: bool = True, note: str = "", figure: bool = True,
                    read: dict | str | None = None, method: str = "map", measure: bool = False):
    """Match a one-mesh human's face to reference images by named points: views = [{"image", "size", "yaw", "points":
    {landmark: [u, v]}}]; a camera per view, shared identity. method "map" (detector + priors, default) | "points";
    read (a character read in macro sigmas), measure, fit, free, force, figure, save. Details:
    guide(topic="human_reference")."""
    from . import head_route, humanfit
    from . import humanfit_views
    if fit:
        head_route.refuse_off_route(name, "human_reference(fit=True)")
    sp, b = _human_base(name)
    vs = json.loads(views) if isinstance(views, str) else views
    st0 = humanfit.state(b)
    if method == "map":
        from . import humanfit_map
        rd = json.loads(read) if isinstance(read, str) else read
        nb, rep = humanfit_map.fit(b, vs, read=rd, force=force, free=tuple(free or ("identity",)) if fit else (), measure=measure)
    else:
        nb, rep = humanfit_views.fit_views(b, vs, free=tuple(free or ("identity",)) if fit else (), force=force)
    rp = store.HOME / name / "human_refs.json"
    kept = {"blockin": json.loads(rp.read_text())["blockin"]} if head_route.is_block_in(name) else {}  # (the chain's record)
    rp.write_text(json.dumps({"views": vs, "cameras": rep["cameras"], **kept}, indent=1))
    out = _human_apply(name, sp, nb, rep, note or "human_reference fit", force, save and fit, st0, None, figure)
    if rep.get("method") == "map":
        extra = "\n".join(f"view {i}: {v['evidence']}, lens ~{v['lens_mm']:.0f} mm" + (" (its lm0..lm67 points ignored: detector re-read)" if v["ignored_lm68"] else "") + (f" DROPPED from the identity: {v['rms_mm']} mm rms against the other pictures (not one projection / another face / wrong yaw?)" if v.get("dropped") else "")
                          for i, v in enumerate(rep["views"]))
        if rep.get("read"):
            extra += "\nread: " + ", ".join(f"{k} asked {v['asked']:+.1f} got {v['got']:+.2f}" for k, v in rep["read"].items())
        if rep.get("measured"):
            m_ = rep["measured"]
            extra += (f"\nMEASURED on view {m_['view']} ({m_['used']}; RENDERS ONLY: not validated on photographs): "
                      + ", ".join(f"{k} {v[0]:+.1f}+-{v[1]:.1f}" for k, v in sorted(m_["macros"].items(), key=lambda t: -abs(t[1][0]))[:12]))
        out[-1] = (out[-1] + "\n" + extra + "\nmacros (population sigmas):\n" + rep.get("macros", "")
                   + "\n(method map: the detector's point table is validated on RENDERS of heads of known shape only, not yet on "
                   "photographs. The result is the most probable head for this evidence: soft; structure comes after.)")
    return out


def _blockin_sheet(name: str, save: str | None, views: list | None = None, table: bool = True,
                   before: str | None = None) -> list:
    """The block-in look as tool output: [the sheet, the target table]."""
    from . import blockin_look, blockin_table
    out = save or str(store.HOME / "human_renders" / f"blockin_{name}.png")
    r = blockin_look.look(name, out, views=views, before=before)
    text = f"sheet: {r['out']} (" + ", ".join(f"view {v['view']} eye shift {v['shift_px']} px" for v in r["views"]) + ")"
    if table:
        text += "\n" + blockin_table.table_text(blockin_table.table(name))
    return [_png(PILImage.open(r["out"])), text]


@mcp.tool(structured_output=False)
def block_in_start(name: str, refs: str | list[dict], sex: str | float | None = None, age: float | None = None,
                   body: dict | None = None, ethnicity: str | dict | None = None,
                   cameras: str = "keep", replace: bool = False, save: str | None = None, expression: bool = False,
                   carry: bool = False):
    """THE DEFAULT START for a person's head from pictures: their body, GNM's class mean for the sex on a GNM-NATIVE
    head (true base, GNM's eyeball / mouth, its own size; the body fitted), nothing of ours on its surface (the reply
    names what was dropped), the cameras, the first look + table. refs = the pictures: a views list [{"image": path,
    "yaw": deg, "lens_mm": mm}, ...] (check_references first) or a one-mesh human with fitted references; sex, age,
    body (base.body keys; nothing reads a body from pictures), ethnicity (a GNM class or a blend {class: weight};
    default the pooled mean), cameras, carry, replace, save, expression. Details: guide(topic="block_in_start")."""
    from . import blockin_models
    e = blockin_models.start(name, _spec_arg(refs) if isinstance(refs, str) and refs.strip().startswith("[") else refs, sex=sex,
                 age=age, body=body, ethnicity=ethnicity, cameras=cameras, replace=replace,
                 expression=expression, carry=carry)
    s = e["start"]
    out = _blockin_sheet(name, save)
    head = ("GNM-NATIVE head (true base, GNM's eyeball / mouth / teeth, GNM's own size; the body fitted)" if s["attach"] == "native"
            else f"body-carried head, gnm_base {s['gnm_base']:.2f}")
    txt = (f"started {name}: {s['sex']} class mean{' (' + s['ethnicity'] + ')' if s['ethnicity'] else ''}, age {s['age']:g}, "
           f"{head}, cameras {s['cameras']}, |c| {e['c_norm']:.2f}\n")
    txt += ("DROPPED from the refs model (not GNM's, not this person's read): " + "; ".join(s["dropped"]) + "\n" if s["dropped"]
            else "DROPPED from the refs model: nothing (it had no strokes, folds, wrinkle relief or head sliders)\n")
    if s.get("carry"):
        txt += "carry=True: the refs model's strokes / skin.folds / skin.wrinkles were KEPT (they are on this head's surface)\n"
    if s.get("left"):
        txt += "LEFT as the refs model had it (ours, not GNM's): " + "; ".join(s["left"]) + "\n"
    if s["attach"] == "native":
        from . import onemesh_report
        txt += onemesh_report.attach_report(store.load(name)["base"])["text"] + "\n"
    out[1] = txt + out[1]
    return out


@mcp.tool(structured_output=False)
def block_in_look(name: str, views: list[int] | None = None, table: bool = True, save: str | None = None,
                  before: str | None = None, focus: str | None = None, read: str = "", keep: bool | None = None,
                  judge: bool = False):
    """The block-in sheet: per picture photo | clay under its light | overlay | outline difference | squints, at the
    eyes, + the target table. focus = a feature (eyes, nose, mouth, chin_jaw, cheeks, ears): ZOOM IN crops + raking
    light + its own rows. judge=True: THE JUDGING SHEET, photo | blend | the pictures projected as the head's skin |
    clay: clay alone reads younger and softer, judge here every few rounds. read / keep log your ZOOM OUT verdict on the
    step that made name. views, table, save, before. Details: guide(topic="block_in_look")."""
    from . import blockin_focus, blockin_lid_measure, blockin_table
    note = ""
    if read or keep is not None:
        blockin_focus.note(name, read, keep)
        note = f"logged on the step that made {name}: zoom-out read" + ("" if keep is None else f", kept={keep}") + "\n"
    if judge:
        from . import blockin_judge as bj
        r = bj.sheet(name, save or str(store.HOME / "human_renders" / f"blockin_{name}_judge.png"), views=views)
        return [_png(PILImage.open(r["out"])), note + f"judging sheet: {r['out']}: where a picture smears or doubles on the "
                "turned head, the geometry is wrong there"]
    if focus:
        out = save or str(store.HOME / "human_renders" / f"blockin_{name}_{focus}.png")
        r = blockin_focus.focus(name, focus, out, views=views, before=before)
        text = note + f"focus sheet {focus}: {r['out']} (" + "; ".join(f"view {v['view']}: {v['registered']}, shift {v['shift_px']} px" for v in r["views"]) + ")"
        if table:
            text += "\n" + blockin_table.table_text(blockin_table.feature_table(name, focus))
            if focus == "eyes":
                text += "\n" + blockin_lid_measure.lid_text(blockin_lid_measure.lid_read(name))
        return [_png(PILImage.open(r["out"])), text]
    out = _blockin_sheet(name, save, views=views, table=table, before=before)
    out[1] = note + out[1]
    return out


@mcp.tool(structured_output=False)
def block_in_step(name: str, moves: dict, out: str | None = None, seen: str = "", why: str = "",
                  cameras: list[int] | None = None, look: bool = True, save: str | None = None,
                  feature: str | None = None, hand_first: bool = False):
    """One block-in round: a NEW model (out, default the next number) = name moved ({"mm:chin_height": 1.5,
    "chin_height": 0.5, "eye_spacing!": 0.3, "sculpt:<zone>": 1}); seen / why logged; feature = the feature zoomed in
    on (its before | after crops come back too); cameras; look; save. Refused before the first block_in_solve
    (hand_first=True overrides). Details: guide(topic="block_in_step")."""
    from . import head_route
    from . import blockin_focus, blockin_models, blockin_steps, blockin_table
    mv = _spec_arg(moves) if isinstance(moves, str) else dict(moves or {})
    if "attach" in mv:   # (nativedefault) the head switched to GNM-native, its cameras carried: a step of its own
        if mv != {"attach": "native"}:
            raise ValueError('block_in_step: {"attach": "native"} is a step of its own (the head switched to GNM-native, the '
                             "cameras carried)")
        r = blockin_models.native_step(name, out=out, seen=seen)
        to = r["entry"]["to"]
        text = (f"{to} (from {name}): the head is GNM-NATIVE now (true base, GNM's own size, the body fitted). CAMERAS CARRIED "
                f"onto its new size and place (x{r['scale']:.3f}, the face moved {1000 * r['shift']:.0f} mm): the next block_in_solve "
                'lays them on this head first (cameras="refit" for that call). '
                + ("DROPPED (no meaning on a native head): " + "; ".join(r["dropped"]) if r["dropped"] else "no head key dropped")
                + ". Hair and clothes made on the old head must be remade.")
        if not look:
            return text
        sh = _blockin_sheet(to, save, before=None)
        return [sh[0], text + "\n" + sh[1]]
    head_route.require_solved(name, hand_first)
    rep = blockin_steps.step(name, mv, out=out, seen=seen, why=why, cameras=cameras, feature=feature)
    text = blockin_steps.step_text(rep)
    if not look:
        return text
    to = rep["entry"]["to"]
    res = []
    if feature:
        fo = str(Path(save).with_name(Path(save).stem + f"_{feature}.png")) if save else \
            str(store.HOME / "human_renders" / f"blockin_{to}_{feature}.png")
        r = blockin_focus.focus(to, feature, fo, before=name)
        res.append(_png(PILImage.open(r["out"])))
        text += f"\nZOOM IN sheet ({feature}, before | after): {r['out']}\n" + blockin_table.table_text(blockin_table.feature_table(to, feature))
    sh = _blockin_sheet(to, save, before=name)
    return [*res, sh[0], text + "\nZOOM OUT (the whole face):\n" + sh[1]]


@mcp.tool(structured_output=False)
def block_in_expression(name: str, out: str | None = None, views: list[int] | None = None, clear: bool = False,
                        eyes: bool = False, seen: str = "", why: str = "", look: bool = True, save: str | None = None):
    """Each picture's OWN expression (a smile, a squint), fitted on this head with the identity and camera held (GNM
    lower-face expression comps, small prior), stored per view in the references and applied in every
    block-in look / focus / table / lid read, never to the model: the neutral identity is then judged against the
    picture as it smiles. A new model (out), shape unchanged; views (default: detector views), clear=True removes them;
    eyes=True adds eye-region comps (a squinting picture; they can fight the lid pose).
    Fit once the big forms are in; refit after large identity moves. Details: guide(topic="block_in_expression")."""
    from . import blockin_steps
    rep = blockin_steps.expression_step(name, out=out, views=views, clear=clear, eyes=eyes, seen=seen, why=why)
    text = blockin_steps.expression_text(rep)
    if not look:
        return text
    to = rep["entry"]["to"]
    sh = _blockin_sheet(to, save, before=name)
    return [sh[0], text + "\nZOOM OUT (before = neutral clay, after = with the picture's expression):\n" + sh[1]]


@mcp.tool(structured_output=False)
def set_expression(name: str, mix: dict | str, out: str | None = None) -> str:
    """Pose a finished head in an expression: a NEW model (out, default <name>_<preset>) whose base.head.expression is
    the mix on top of the neutral; name stays neutral. mix = a preset (smile, open_mouth, frown, surprise, blink) or
    ARKit shape weights 0..1 ({"jawOpen": 0.3, "mouthSmileLeft": 0.5}): GNM's expression parameters only, no sculpting.
    For a picture's own expression while judging: block_in_expression. Details: guide(topic="set_expression")."""
    from . import head_route
    return head_route.pose_text(name, head_route.pose(name, _spec_arg(mix) if isinstance(mix, str) and mix.strip().startswith("{") else mix, out=out))


@mcp.tool(structured_output=False)
def gnm_controls(query: str = "", control: str = "", families: list[str] | None = None, top: int = 12,
                 sort: str = "score", per_family: int = 0, sign: int = 0, zones: bool = False, phrase: str = "",
                 ruler: str = "") -> str:
    """GNM's controls. phrase = a difference you SEE ("the muzzle stands forward in profile", "pupils further apart")
    -> the driving manual's entries (control, sign, size, drags; guide topic gnm_driving): start there. query="mm" =
    the 27 mm measures (mm:<measure> moves). ruler="modelA,modelB" = those measures, B - A, largest first, each
    with the mm: move that closes it. query = a feature ("alar crease", "jowl") -> controls ranked by mm per prior
    cost x locality; control = one described; zones=True; families, sort, per_family, sign. Act: block_in_step
    {"mm:<measure>": mm}, {"gnm:<control>": x} or {"sculpt:<zone>": mm}. Details: guide(topic="gnm_controls")."""
    from . import gnm_controls as gcm
    if ruler:
        from . import blockin as bi, gnm_mm
        a, b = [x.strip() for x in ruler.split(",")][:2]
        return (f"ruler: {b} - {a} (GNM identity; take the largest gaps in sd first; mm: moves add up exactly)\n"
                + gnm_mm.gaps_text(bi.ruler(a, b)))
    if phrase:
        from . import gnm_manual
        return gnm_manual.text(gnm_manual.suggest(phrase, top=3))
    if query.strip().lower() in ("mm", "measures", "ruler"):
        from . import gnm_mm
        s = gnm_mm.sd()
        return ("The millimetre measures (block_in_step {\"mm:<measure>\": mm}: that measure alone, the others held "
                "in mm). Read the gap on the sheet (px x mm per px), type it. Population sd in mm:\n"
                + "\n".join(f"mm:{n} (sd {s[n]:.1f} mm, read in {gnm_mm.SEE[n][0]}): + = {gnm_mm.SEE[n][1]}"
                            for n in gnm_mm.NAMES)
                + "\nThe forward measures " + " -> ".join(gnm_mm.CHAIN) + " are a chain: a link carries everything "
                  "below it (the lower lip alone +2: lower_lip_forward +2 with chin_forward -2).")
    if zones:
        z = gcm.zones()
        return "\n".join(f"{k}: {d} ({len(z[k])} vertices)" for k, (d, _) in gcm.ZONES.items())
    if control:
        return gcm.text(gcm.describe(control))
    if not query:
        return ("gnm_controls: give query= (a feature) or control= (a name) or zones=True. Families: "
                + ", ".join(f"{f} ({len(gcm.names(f))})" for f in gcm.FAMILIES))
    return gcm.text(gcm.query(query, families=families, top=top, sort=sort, sign=sign, per_family=per_family))


@mcp.tool(structured_output=False)
def lid_read(name: str, match: bool | str = False, out: str | None = None, seen: str = "", save: str | None = None,
             expression: bool = False, donor: str | None = None, fold: str | None = None):
    """Lid margins against the iris (MRD-style, iris radii) and the fold line on the front picture vs the model.
    match=True: THE EYE STEP (a block-in step; set the ORBIT first: face_ruler), identity only: the opening (the eye
    ruler's margins and corners in mm), then the lid as ONE structure on GNM's lid rings: a crisp fold on the
    picture's fold line, brows held (fold="crisp", the default; fold="donor" / donor="s376": toward a donor head's
    lid; fold="none": the opening only), with the eyeball guard; nothing painted. expression=True: GNM's eye-region expression too. out, save (focus=eyes
    sheet), seen. Details: guide(topic="lid_read")."""
    from . import blockin as bi
    from . import blockin_focus, blockin_lid_measure, blockin_steps
    if not match:
        return blockin_lid_measure.lid_text(blockin_lid_measure.lid_read(name))
    if match == "pose":
        raise ValueError('lid_read: match="pose" is retired; match=True is the eye step')
    from . import blockin_eyes as be
    lines = []
    rep = be.eye_step(name, out=out, seen=seen, log=lines.append, expression=expression, donor=donor, fold=fold)
    to = rep["entry"]["to"]
    path = save or str(store.HOME / "human_renders" / f"blockin_{to}_eyes.png")
    blockin_focus.focus(to, "eyes", path, before=name)
    e = rep["eyes"]
    txt = (blockin_steps.step_text(rep) + "\n" + "\n".join(lines) + "\n" + be.text(e) + "\n" + blockin_lid_measure.lid_text(blockin_lid_measure.lid_read(to))
           + f"\nfocus=eyes sheet (before | after, raking light): {path}")
    c0_, c1_ = bi.identity(store.load(name)), bi.identity(store.load(to))   # NOTHING FORCED is the solve's rule, not yet
    big = int((abs(c1_) > 3.0).sum())                                       # this step's: say it when the step breaks it
    if big or float(((c1_ - c0_) ** 2).sum()) ** 0.5 > 8.0:
        txt = (f"WARNING: FORCED: the eye step moved the identity |dc| {float(((c1_ - c0_) ** 2).sum()) ** 0.5:.1f} "
               f"(|c| {float((c0_ ** 2).sum()) ** 0.5:.1f} -> {float((c1_ ** 2).sum()) ** 0.5:.1f}; a typical head ~13), "
               f"{big} component(s) past 3 sd (largest {float(abs(c1_).max()):.1f}). Do not keep it: step from {name} "
               'again with fold="none" (the opening only) or leave the lids to block_in_solve.\n' + txt)
    return [_png(PILImage.open(path)), txt]


@mcp.tool(structured_output=False)
def eye_ruler(name: str, model: str | None = None, save: str | None = None):
    """THE EYE RULER: the front picture's eyes read by their edges (iris as a circle through the limbus, lid margins at 7
    columns, canthi, fold line, brow edge) against the model's mesh through the picture's fitted camera, in mm at the
    model, with each difference's tolerance (the reader's measured error) and the move that closes it. model: another
    model read against `name`'s picture. Returns the picture's eyes with the read and the model's lid outline drawn
    over them (save: the path) and the table. Sizes read by eye are 30-50 % off: read this before and after an eye
    step. Details: guide(topic="eye_ruler")."""
    from . import eye_ruler as er
    c = er.compare(name, model)
    path = save or str(store.HOME / "human_renders" / f"eye_ruler_{model or name}.png")
    im = er.overlay(c["image"], c["eyes"], c["mesh"], c["mm"])
    im.save(path)
    return [_png(im), c["text"] + f"\noverlay (picture; green = its margins, red = its canthi, blue = the model's ring / margins / "
                                  f"inner-corner landmark laid over by iris centre): {path}"]


@mcp.tool(structured_output=False)
def block_in_solve(name: str, out: str | None = None, share: float = 1.0, seen: str = "", save: str | None = None,
                   cameras: str = "free", anchors: str = "differential", parse: str = "auto", hold: str = "default",
                   expression: str = "default", chin_points: str = "auto", size: str = "held",
                   neck: str | float = "prior", dense: str = "default", detector: str = "default", hair_edge: str = "default"):
    """ONE JOINT STEP: face_ruler's solve over every reference view (outlines, irises, limbus, lids, lips, anchors;
    GNM's prior on the whole identity) applied as a block-in step, the solve's cameras kept. Use it FIRST from
    block_in_start's head, 3-4 calls until |dc| < 2. The reply says what MOVED WITH NO READ. cameras, size, neck
    (default "prior": ANSUR's girth), dense, detector, hair_edge, hold, expression, chin_points, anchors, parse, out,
    share, seen, save. A known lens (lens_mm / EXIF) keeps its distance. Details: guide(topic="block_in_solve")."""
    from . import blockin_steps
    from . import blockin
    if parse not in ("auto", "on", "off"):
        raise ValueError('block_in_solve: parse = "auto" | "on" | "off"')
    if hold not in ("default", "auto", "none") or expression not in ("default", "view", "shared", "lower", "none"):
        raise ValueError('block_in_solve: hold = "auto" | "none"; expression = "view" | "shared" | "none"')
    if chin_points not in ("auto", "on", "off"):
        raise ValueError('block_in_solve: chin_points = "auto" | "on" | "off"')
    if dense not in ("default", "on", "off") or detector not in ("default", "mesh", "anchors") or hair_edge not in ("default", "on", "off"):
        raise ValueError('block_in_solve: dense = "on" | "off"; detector = "mesh" | "anchors"; hair_edge = "on" | "off" (each also "default")')
    rep = blockin_steps.solve_step(name, out=out, share=share, seen=seen, cameras=cameras, anchors=anchors,
                        parse={"auto": "auto", "on": True, "off": False}[parse],
                        hold={"default": blockin.SOLVE_HOLD, "auto": "auto", "none": None}[hold],
                        expression={"default": blockin.SOLVE_EXPRESSION, "view": "view", "shared": "shared", "lower": "lower", "none": False}[expression],
                        chin={"chin_lm": {"auto": "auto", "on": "xy", "off": "none"}[chin_points],
                              "size": {"held": True, "free": False, "iris": "iris", "iris_pin": "iris_pin"}[size],
                              "neck": {"prior": True, "held": "held", "free": False}[neck] if isinstance(neck, str) else float(neck)},
                        dense={"default": None, "on": True, "off": False}[dense], mp={"default": None, "mesh": True, "anchors": False}[detector],
                        hair_edge={"default": None, "on": True, "off": False}[hair_edge])
    to, so = rep["entry"]["to"], rep["solve"]
    sh = _blockin_sheet(to, save, before=name)
    warn = ""
    if so["n"].get("outline", 0) < 120:
        warn += (f"WARNING: a weak solve: {so['n'].get('outline', 0)} outline reads (it wants ~150+ over 2-3 views). The anchors "
                 "and the prior carry it: expect the class mean's face where nothing was read.\n")
    for x in so.get("notes") or []:          # a VIEW without an outline (the total above hid a hair-covered front picture)
        if x.startswith(("NO OUTLINE:", "STRONG PERSPECTIVE:", "INFERRED (the camera's distance")):
            warn += "WARNING: " + x + "\n"
    if so["relax"] > 1.0:
        warn += (f"WARNING: INCONSISTENT PICTURES: at their own sigmas the solve wanted a component past 3 sd, so every read was "
                 f"down-weighted (sigma x{so['relax']:.2f}) until none did. The references disagree with each other or with any "
                 "one head by that much (paintings, expressions, a wrong camera): the result is a compromise, judge it on "
                 "the judging sheet against the head you had.\n")
    for x in so.get("notes") or []:          # a view's stated kind against its fitted camera
        if x.startswith("VIEW:"):
            warn += "WARNING: " + x + "\n"
    notes = "".join(f"  {x}\n" for x in so.get("notes") or [] if not x.startswith(("VIEW:", "NO OUTLINE:", "STRONG PERSPECTIVE:", "INFERRED (the camera's distance")))
    rp = (so.get("report") or {}).get("text") or ""
    if so.get("neck"):
        n_ = so["neck"]
        rp += ("\n" if rp else "") + (
            f"NECK: girth {1e3 * n_['before']:.0f} -> {1e3 * n_['after']:.0f} mm at its narrowest; "
            + {"held": f"HELD at {1e3 * (n_['target'] or 0):.0f}; no read",
               "prior": f"under the anthropometric PRIOR {1e3 * n_['ansur']:.0f} +- {1e3 * n_['ansur_sd']:.0f}; no direct read (INFERRED)",
               "free": "FREE (neck=\"free\"): moved with no read"}[n_["mode"]]
            + f" (ANSUR II for this sex and stature: {1e3 * n_['ansur']:.0f} +- {1e3 * n_['ansur_sd']:.0f})")
        h_ = so["head_size"]
        rp += (f"\nHEAD SIZE: a GNM-native head: GNM's own size x {h_['size']:.3f} "
               + (f"(the stature's allometry at {h_['stature']:.3f} m)" if h_["allometric"] else "(base.head.size, given)")
               + "; the solve's size hold keeps the identity's size at the start head's on top of that")
    if so.get("held"):
        rp += ("\n" if rp else "") + "HELD at the start head's value (no read looks at them): " + ", ".join(so["held"])
    for pc, d in (so.get("expression") or {}).items():
        big = [f"{fr_say(k)} {v[0]:+.2f}" for k, v in d.items() if abs(v[0]) >= max(0.15, 2 * v[1])]
        rp += ("\n" if rp else "") + (f"expression read in the {pc} picture (1 = GNM's full prototype; taken out of the identity): "
                                      + (", ".join(big) if big else "neutral"))
    return [sh[0], warn + f"joint solve: {so['n']} reads; |dc| {so['dc']:.2f}, |c| {so['c']:.2f}, largest component {so['max_sd']:.2f} sd; "
                   f"cameras' whole move since the start (shift mm, shift mm, scale %, roll, yaw, pitch deg, distance % per view; a prior, not a clip: see the CAMERA lines): {so['cameras']}"
                   f" (this call: {so['camera_step']})\n" + notes + (rp + "\n" if rp else "")
                   + blockin_steps.step_text(rep) + "\n" + sh[1]]


def fr_say(k: str) -> str:
    from . import face_ruler as face_ruler_mod
    return face_ruler_mod.EXPR_SAY.get(k, k)


@mcp.tool(structured_output=False)
def face_ruler(name: str, save: str | None = None):
    """THE FACE RULER: the block-in model against its reference pictures in MILLIMETRES: first the ORBIT (eye depth:
    set it before any lid work), then gnm_mm's 27 measures, picture - model, largest first, each with the reader's
    error and the `mm:` move that closes it (block_in_step). Read from skin OUTLINES, iris centres and the side views'
    limbus through the fitted cameras (yaw left free), not by eye and not from detector landmarks. NOT READ = these
    pictures do not show it. Start a block-in from this table. Returns the pictures with the reads drawn (save: the
    path) and the table. Details: guide(topic="face_ruler")."""
    from . import face_ruler_compare
    c = face_ruler_compare.compare(name)
    path = save or str(store.HOME / "human_renders" / f"face_ruler_{name}.png")
    im = face_ruler_compare.overlay(c)
    im.save(path)
    return [_png(im), c["text"] + f"\noverlay (green = the model's outline through each fitted camera, yellow = where "
                                  f"the picture's skin outline was read against it, magenta / cyan = iris centres picture / model): {path}"]


@mcp.tool(structured_output=False)
def lip_read(name: str, match: bool = False, out: str | None = None, seen: str = "", save: str | None = None):
    """The lips on the front picture vs the model: vermilion border miss (mm), seam miss, Cupid's bow (picture /
    model), the neutral's contact gaps and how it is closed. match=True: THE LIPS STEP (a block-in step): one solve
    over the identity + GNM's lower-face expression for the picture's borders and seam, the neutral closed by GNM's
    expression (no seal), the rest of the face held. out, save (focus=mouth sheet), seen. Details:
    guide(topic="lip_read")."""
    from . import blockin_lips as bl
    from . import blockin_focus, blockin_steps
    if not match:
        return bl.read_text(bl.lip_read(name))
    lines = []
    rep = bl.lips_step(name, out=out, seen=seen, log=lines.append)
    to = rep["entry"]["to"]
    path = save or str(store.HOME / "human_renders" / f"blockin_{to}_mouth.png")
    blockin_focus.focus(to, "mouth", path, before=name)
    txt = (blockin_steps.step_text(rep) + "\n" + "\n".join(lines) + "\n" + bl.text(rep["lips"]) + "\n" + bl.read_text(bl.lip_read(to))
           + f"\nfocus=mouth sheet (before | after, raking light): {path}")
    return [_png(PILImage.open(path)), txt]
