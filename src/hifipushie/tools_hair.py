"""Hair tools: grooms, ties, looks, hair from a reference picture, and the hair export."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from . import store
from .mcp_app import mcp
from .tool_common import _out, _png, _spec_arg

# ---------------------------------------------------------------- hair
HAIR_TRACE = """A trace is reference-image pixels (u right, v down) of the picture you're matching:
  {"image": path (or pass image_path), "landmarks": {lm joint: [u, v], ...} (8-10 face points: eye corners, brow
   middles, nose tip, mouth corners, chin; the model's lm_* joints), "part": [[u, v], ...] (the parting from its front
   end back), "hairline": [[u, v], ...] (temple to temple across the forehead), "hair": [[u, v], ...] (closed outline of
   the visible hair above clip_y), "clip_y": v (below it ear, sideburn and beard aren't traced), "clumps": [{"name",
   "line": [[u, v], ...] root -> tip along the strands, "width": px across the clump}], "crop"?: [x0, y0, x1, y1] (the
   square the matched views show; default: round the hair and landmarks), "views"?: {name: {the same keys for
   another view of the character: another figure in the same picture (same lens), or a turnaround's side/back with
   its own "image"; landmarks, hair, hairline, clip_y and crop needed}}}. Every view gets its own matched row and
   outline numbers in look_hair.
Clump names: one starting "part_side" is the short clump falling from the part toward the near ear; one whose root is
across the head from the part is the sweep's fall down the far side; the rest are the rows sweeping from the part,
front first."""


def _hair_counts(spec: dict) -> str:
    locks = (spec.get("hair") or {}).get("locks") or {}
    tiers: dict = {}
    for lk in locks.values():
        t = lk.get("tier", "?") + ("(hand)" if lk.get("hand") else "")
        tiers[t] = tiers.get(t, 0) + 1
    return f"{len(locks)} locks: " + ", ".join(f"{k} {v}" for k, v in sorted(tiers.items()))


def _hair_gates(look) -> str:
    """The numbers a hair look measures, each with what it should be."""
    from . import hair
    lines = []
    g = getattr(look, "gate", None) or {}
    if g:
        worst = {v: max((x for k, x in r.items() if k in ("left", "right")), default=0.0)
                 for v, r in g.items() if isinstance(r, dict)}
        notch = {v: max((x for k, x in r.items() if k.endswith("_notch")), default=0.0)
                 for v, r in g.items() if isinstance(r, dict)}
        at = {v: r.get("at") for v, r in g.items() if isinstance(r, dict)}
        lines.append(f"silhouette gate {'PASS' if g.get('pass') else 'FAIL'}: worst dent in the outline (mm, <= 1.5; brows"
                     f" + 2 cm up to near the top, 12 mm scale) " + ", ".join(f"{v} {d} at z {at[v]}" for v, d in worst.items())
                     + "; clump steps at the outline (mm, 2-5 reads as clumps) "
                     + ", ".join(f"{v} {d}" for v, d in notch.items()))
    ms = getattr(look, "mass_share", None) or {}
    if ms:
        bad = [v for v, x in ms.items() if x > 0.10]
        lines.append("bare volume share of the visible hair (< 0.10; the volume is filler, never a surface): "
                     + ", ".join(f"{v} {x}" for v, x in ms.items()) + (f"  OVER in {', '.join(bad)}" if bad else ""))
    bw = getattr(look, "bare_where", None) or {}
    bw = {v: r for v, r in bw.items() if r and ms.get(v, 0) > 0.10}
    if bw:
        lines.append("  where the bare volume shows (share of the view's hair, by head region; 'hairline' = within 15 mm "
                     "of it): " + "; ".join(f"{v}: " + ", ".join(f"{k} {x}" for k, x in list(r.items())[:4])
                                             for v, r in bw.items()))
    lm = getattr(look, "lit_mass", None) or {}
    if lm:
        lines.append("lit bare volume (reads as a helmet, < 0.03): " + ", ".join(f"{v} {x}" for v, x in lm.items()))
    fo = getattr(look, "folds", None)
    if fo:
        worst = sorted(fo.items(), key=lambda kv: -kv[1][0])
        lines.append(f"folded locks ({len(fo)}; the spine turns within the lock's own width, bend x half width >= "
                     f"1: the inner edge runs backwards and the lens crumples into flakes there; ease the path or narrow the lock): " + ", ".join(
                         f"{n} {r} at {u}" for n, (r, u) in worst[:12]) + (" ..." if len(fo) > 12 else ""))
    fi = getattr(look, "fins", None)
    if fi:
        lines.append(f"fins ({len(fi)}; a lock edge standing over the layer by more than the lock's own thickness + "
                     f"{hair.FIN_MM:g} mm, [mm over, u along it]; narrow the lock, lower its lie or lay it along the "
                     f"volume's curve): " + ", ".join(f"{n} {v[0]} at {v[1]}" for n, v in list(fi.items())[:12])
                     + (" ..." if len(fi) > 12 else ""))
    re_ = getattr(look, "root_ends", None)
    if re_:
        lines.append(f"blunt root ends ({len(re_)}; the lock's width in mm where it rises out of the layer, > "
                     f"{hair.ROOT_END_MM:g}: the cut end shows as a crescent fin at a parting or scales along a "
                     f"hairline; lower the clump's `root` (0.1) and raise `climb` (0.025 m)): " + ", ".join(
                         f"{n} {w}" for n, w in list(re_.items())[:12]) + (" ..." if len(re_) > 12 else ""))
    fits = getattr(look, "fits", None) or ({"matched": look.fit} if getattr(look, "fit", None) else {})
    for view, f in fits.items():
        if not f:
            continue
        lines.append(f"against the traced reference ({view} camera): " + ", ".join(
            f"{k} {v}" for k, v in f.items() if k not in ("clumps", "regions", "front_edge", "front_flow")))
        ff = f.get("front_flow")
        if ff:
            lines.append(f"  strand direction just inside the hairline, read off both images (deg to the hairline: 0 runs "
                         f"along it like a headband, +-90 straight out of it; per stretch from the trace's first "
                         f"hairline point to its last, [reference, ours]): " + ", ".join(
                             str(b) if b else "-" for b in ff["bins"]) + f"; mean error {ff['err_deg']} deg")
        fe = f.get("front_edge")
        if fe:
            bad = fe["rough_mm"] > 1.0 or fe["tooth_mm"] > 3.0 or fe["holes"] > 0.05
            lines.append(f"  hairline edge along the traced line ({'JAGGED' if bad else 'clean'}; the edge against the "
                         f"skin as rendered: rough_mm rms <= 1, tooth_mm worst tip/notch <= 3, holes = skin just inside "
                         f"the edge <= 0.05, turn_deg_cm = zigzag; off_mm + = ours further onto the skin than the "
                         f"trace): " + ", ".join(f"{k} {v}" for k, v in fe.items()))
        if f.get("regions"):
            lines.append("  outline per region, mm (err = ours - reference, + = ours sticks out; ref_hair / our_hair = "
                         "the outline over the bare head; ref_hair < 0: the bare head is already outside the "
                         "reference, hair can't fix it): " + "; ".join(
                             f"{r} err {v['err']:+} (worst {v['worst']:+}) ref_hair {v['ref_hair']} our_hair "
                             f"{v['our_hair']}" for r, v in f["regions"].items()))
        if f.get("clumps"):
            lines.append("  traced clump -> nearest model clump, direction error deg, mean distance px: " + "; ".join(
                f"{k} -> {v[0]} {v[1]} deg {v[2]} px" for k, v in f["clumps"].items()))
    return "\n".join(lines)


@mcp.tool(structured_output=False)
def groom_hair(name: str, groom: dict | None = None, replace: bool = False, stage: str | None = None,
               note: str = "", style: str | None = None, strands: dict | None = None, look: dict | None = None,
               fuller: dict | None = None, trim: dict | list | None = None):
    """Grow the hair from spec.hair.groom and save. groom: a patch (hairline, parting, volume, length, flow, tiers,
    drawn clumps, tie, loose ...); replace regrows all; stage "mass"|"locks"; style "strands" (realistic; the default
    on a model with `base`) | "locks" (solid, stylised); strands / look: strand dials and material; fuller {region: m}
    and trim reshape existing locks. Then look_hair. Details: guide(topic="groom_hair")."""
    from . import hair, hair_route
    from . import hair_head, hair_lockmesh, hair_spec
    hair_route.check_style_arg(style)
    if style is not None or strands or look:
        sp = store.load(name)
        h = sp.setdefault("hair", {})
        if style is not None:
            if style not in hair.STYLES:
                raise ValueError(f"style is one of {', '.join(hair.STYLES)}")
            h["style"] = style
        if strands:
            h["strands"] = hair_spec.merge_patch(h.get("strands") or {}, _spec_arg(strands))
        if look:
            h["look"] = hair_spec.merge_patch(h.get("look") or {}, _spec_arg(look))
        hair_spec.validate(sp)
        store.save(name, sp, note or "hair: style / strands / look")
    shaped = ""
    if fuller or trim:
        sp = store.load(name)
        sc = hair_head.scalp(name, sp)
        if fuller:
            fill = (sp.get("hair") or {}).get("style", "locks") != "locks"
            sp, rep = hair_lockmesh.lift(sp, sc, _spec_arg(fuller), fill=fill)
            shaped += (f"fuller: {rep['locks']} locks lifted up to {rep['max_lift_mm']} mm"
                       + (" and thickened to fill" if fill else "") + f"; volume {rep['volume']}\n")
        for t_ in ([] if not trim else trim if isinstance(trim, list) else [trim]):
            t_ = _spec_arg(t_)
            sp, rep = hair_lockmesh.trim(sp, sc, float(t_["below"]), tuple(t_.get("where", ("sides", "back", "nape"))))
            shaped += f"trim {t_}: {rep['cut']} locks cut, {rep['untouched']} untouched, too short to cut {rep['too_short']}\n"
        v = store.save(name, sp, note or "hair: fuller / trim")
        if not (groom or replace or stage):
            return shaped + f"saved {name} v{v}\n{_hair_counts(sp)}\n" + hair_route.groom_next(name, sp)
    r = hair_spec.groom(name, replace=replace, note=note, patch=_spec_arg(groom) if groom else None, stage=stage)
    spec = store.load(name)
    return (shaped + f"saved {name} v{r['version']}: grew " + (", ".join(f"{t} {n}" for t, n in r["grown"].items()) or "nothing")
            + f"; kept {len(r['kept'])} hand/edited locks" + (f" ({', '.join(r['kept'][:12])}{'...' if len(r['kept']) > 12 else ''})" if r["kept"] else "")
            + (f"; {len(r['not_regrown'])} names not regrown (deleted in Blender: hair.removed; replace=True "
               f"forgets them)" if r["not_regrown"] else "")
            + f"\n{_hair_counts(spec)}; style {(spec.get('hair') or {}).get('style', 'locks')}; "
              f"stage {(spec.get('hair') or {}).get('stage', 'locks')}\n" + hair_route.groom_next(name, spec))


@mcp.tool(structured_output=False)
def tie_hair(name: str, style: dict | None = None, carry_from: str | None = None, look: dict | None = None,
             note: str = "", reseat: bool = False):
    """A tied-back hairstyle (ponytail, bun, plait, half up) from a few words: style {tie: nape|low|mid|high|top,
    side, tightness 0..1, volume 0..1 (body: the hair stands up from the roots / the part and arcs over; 0 = a cap),
    part: centre|left|right|none, ears, tail {kind, length, fullness, wave, tousle, to}, wisps 0..1, front, hairline
    0..1, escaped, neatness 0..1, half}; a riff names only what changes. carry_from: wear another model's hair first.
    look: the colour {variation, sun (sun-lightened lengths), highlights, grey_amount: all 0..1}. Then
    look_hair(views="around"). reseat=True + carry_from: an approved groom onto a new head lock for lock. Details:
    guide(topic="tie_hair")."""
    from . import hair_seat
    if reseat:
        if not carry_from or style or look:
            raise ValueError("reseat=True wears carry_from's grown locks as they are: give carry_from and no style / look "
                             "(riff afterwards with tie_hair(name, style=...), which regrows)")
        r = hair_seat.reseat(name, carry_from, note=note)
        return (f"saved {name} v{r['version']}: {r['locks']} locks of {carry_from} re-seated (head x{r['k']:.3f})\n"
                f"{_hair_counts(store.load(name))}\nnext: call_tool(\"look_hair\", {{\"name\": \"{name}\", \"views\": [\"around\"]}}) beside {carry_from}'s "
                f"approved renders at the same views of the head")
    r = hair_seat.tie_style(name, _spec_arg(style) if style else None, carry_from=carry_from,
                       look=_spec_arg(look) if look else None, note=note)
    m = r["made"]["tie"]
    ga, tl = m["gather"], m.get("tail") or {}
    spec = store.load(name)
    return (f"saved {name} v{r['version']}: " + ", ".join(f"{k} {v}" for k, v in r["kinds"].items())
            + f"\nstyle (groom.tied): {json.dumps(r['tied'])}"
            + f"\nmade: tie at az {m['at'][0]} el {m['at'][1]} ({m['out'] * 1000:.0f} mm off the scalp); the hair stands "
              + (f"{(ga.get('volume') or {}).get('crown', 0) * 1000:.0f} mm off the crown and {(ga.get('volume') or {}).get('side', 0) * 1000:.0f} mm "
                 f"off the sides (volume: it rises within ~{2000 * (ga.get('volume') or {}).get('rise', 0):.0f} mm of the root, arc "
                 f"{(ga.get('volume') or {}).get('arc', 0):.2f})" if ga.get("volume") else f"{ga['puff'] * 1000:.0f} mm off the head")
              + f", lifts {ga['root_lift'] * 1000:.1f} mm at the roots, may hang "
              f"{ga['overhang']:.0f} deg over the hairline at the temples; parting {r['made']['parting']['side']}"
            + (f"; tail {tl['length'] * 100:.0f} cm, {tl['fullness'] * 1000:.0f} mm full, "
               + ("a bun" if tl.get("coil") else "a plait" if tl.get("plait") else "hanging") if tl else "; no tail")
            + (f"; wisps {m['wisps']['count']} a side ({', '.join(m['wisps']['where'])})"
               + (f" + {m['wisps']['loose']} thick loose locks" if m['wisps'].get('loose') else "")
               + (f" + {m['wisps']['baby']} baby hairs" if m['wisps'].get('baby') else "") if m.get("wisps") else "")
            + f"; hairline edge {ga.get('edge', 0):.2f} (0 hard .. 1 soft)"
            + f"\n{_hair_counts(spec)}\nnext: call_tool(\"look_hair\", {{\"name\": \"{name}\", \"views\": [\"around\"]}}) (every side, with the bust: tied hair is "
              "tuned through the front and is wrong from behind first); change one word of the style to riff")


@mcp.tool(structured_output=False)
def look_hair(name: str, views: list[str] | None = None, size: int = 480, clay: bool = True, layout: bool = False,
              reference: str | None = None, save: str | None = None, only: list[str] | None = None,
              tier: str | None = None, debug: str | None = None, engine: str = "eevee",
              stage: str | None = None, measure: dict | None = None):
    """Fast hair renders (EEVEE, 4-30 s) with gates: outline dents, bare volume, fit to a traced reference. views
    (+ "ref0".. = the reference pictures' fitted cameras), clay, layout (top sketch), reference, only (lock names),
    tier (game cards) + debug, engine "cycles", size, save, stage (a model with the same head whose scene is used),
    measure {"view": "ref2", "mask": png, "tie": [x, y], "colour": true} (outline / tail / colour against that
    picture). Needs `sync` once (of the model or its stage). Details: guide(topic="look_hair")."""
    from . import hair_route
    from . import hair_card_fit, hair_drawn, hair_head, hair_look, hair_spec
    from . import hair
    views = list(views) if views else ["front", "three_quarter", "side", "back", "top"]
    if "around" in views:  # every side, with the bust (hair that hangs): the angles a front-tuned groom is wrong from
        i = views.index("around")
        views[i:i + 1] = ["bust_front", "bust_three_quarter", "bust_side", "bust_back_quarter", "bust_back", "bust_side_r"]
    only_layout = views == ["layout"]
    if "layout" in views:
        layout = True
        views = [v for v in views if v != "layout"]
    measure = _spec_arg(measure) if measure else None
    if measure and measure.get("view") and measure["view"] not in views:
        views.append(measure["view"])
    bad = [v for v in views if v not in hair.VIEWS and not re.fullmatch(r"ref\d+", str(v))]
    if bad:
        raise ValueError(f"unknown views {bad} (have {', '.join(hair.VIEWS)}, layout, ref0.. = the reference "
                         f"pictures' fitted cameras)")
    spec = store.load(name)
    if not (spec.get("hair") or {}):
        raise ValueError(f"{name} has no hair: groom_hair(name, groom={{...}}) grows it")
    out = []
    text = _hair_counts(spec)
    stored = spec
    if tier is not None:
        if tier not in hair.CARD_TIERS:
            raise ValueError(f"tier is one of {', '.join(hair.CARD_TIERS)}")
        spec = {**spec, "hair": {**spec["hair"], "style": "cards"}}
    if not only_layout:
        sheet, secs, fr = hair_look.look(name, views=tuple(views), size=size, reference=reference, spec=spec, clay=clay,
                                    only=only, budget=tier, debug=debug, engine=engine, stage=stage)
        st = next((ln[10:] for ln in fr if ln.startswith("@@strands")), None)
        if st:
            text += f"\nstrands: {st}"
        out.append(_out(sheet, save))
        gates = _hair_gates(hair_look.look)
        if (spec.get("hair") or {}).get("stage") == "mass":  # the volume is the surface on purpose at this stage
            gates = "\n".join(ln for ln in gates.splitlines() if "bare volume" not in ln)
            gates += "\nstage mass: judge the silhouette (outline dents, IoU / outline px); bare-volume shares count " \
                     "once the locks are on (stage \"locks\")"
        text = f"rendered in {secs}s; {text}\n" + gates
        if measure:
            bad = set(measure) - {"view", "mask", "tie", "colour"}
            if bad or not measure.get("view"):
                raise ValueError(f"measure: {{'view': 'ref<i>', 'mask': png, 'tie': [x, y], 'colour': bool}}"
                                 + (f" (unknown {sorted(bad)})" if bad else ""))
            m = hair_card_fit.measure_ref(name, measure["view"], mask=measure.get("mask"), tie=measure.get("tie"),
                                 colour=bool(measure.get("colour", True)), stage=stage)
            o = m.get("outline")
            if o:
                text += (f"\nagainst the picture ({m['view']}, {m['mm_per_px']} mm a px): IoU {o['iou']}, area x{o['area']}"
                         + (f", outline {o['chamfer_mm']} mm apart" if "chamfer_mm" in o else ""))
                if "below" in o:
                    text += (f"\n  below the tie: {100 * o['below']:+.0f}% of hers; length {o['ours']['length_mm']} mm (hers "
                             f"{o['hers']['length_mm']}), width {o['ours']['width_mm']} mm (hers {o['hers']['width_mm']}), "
                             f"reach {o['ours']['back_mm']} mm (hers {o['hers']['back_mm']}). One draw moves these ~10%: "
                             f"judge over 3-4 groom seeds")
            c = m.get("colour") or {}
            if c.get("ours") and c.get("picture"):
                text += f"\n  colour over dense hair ({engine}), ours | picture (L*, chroma, hue):"
                for b in ("mean", "shadow", "mid", "highlight"):
                    a_, b_ = c["ours"][b], c["picture"][b]
                    text += f"\n    {b}: {a_['L']} / {a_['chroma']} / {a_['hue']}  |  {b_['L']} / {b_['chroma']} / {b_['hue']}"
                text += ("\n  (EEVEE: look.eevee_gain / eevee_sat; Cycles: look.cycles_fit, cycles_width for cover, "
                         "cycles_sat for chroma)")
    hy = hair_spec.hierarchy(spec, hair_head.scalp(name, spec))
    if hy:
        flag = ("  near-uniform: vary the widths (a few big shapes, some medium, a few small)"
                if hy["width_cv"] < 0.2 or max(hy["big"], hy["medium"], hy["small"]) > 0.8 else "")
        text += (f"\nsize hierarchy by area (artists aim near big 0.6 / medium 0.3 / small 0.1): big {hy['big']}, "
                 f"medium {hy['medium']}, small {hy['small']}; width spread (cv) {hy['width_cv']}, widest "
                 f"{hy['widest_mm']} mm" + flag)
    if layout:
        lay = hair_drawn.layout(name, spec=spec)
        lp = None
        if save:
            p = Path(save).expanduser()
            lp = str(p.with_name(p.stem + "_layout" + (p.suffix or ".png"))) if not only_layout else save
        out.append(_out(lay, lp))
    return [*out, text + "\n" + hair_route.look_next(name, stored, tier)]


@mcp.tool(structured_output=False)
def export_hair(name: str, out_dir: str, tiers: list[str] | None = None, groom: bool = True, check: bool = True,
                save: str | None = None):
    """The hair ALONE, game-ready, from a strand groom (export_asset ships the character with its hair): a GLB per tier
    into out_dir, one atlas. tiers: default main, npc, far; add "hero" for a close camera. groom=True also writes
    Alembic/USD strands; check=True judges the re-imported cards. save. Details: guide(topic="export_hair")."""
    from . import hair_route
    from . import hair_export
    from . import hair
    spec = store.load(name)
    if (spec.get("hair") or {}).get("style") != "strands":
        raise ValueError(f"{name}'s hair style is {(spec.get('hair') or {}).get('style', 'locks')!r}: export_hair cuts "
                         f"cards from a strand groom (groom_hair(name, style=\"strands\")); solid locks go out with "
                         f"export_asset")
    tiers = list(tiers) if tiers else ["main", "npc", "far"]
    bad = [t for t in tiers if t not in hair.CARD_TIERS]
    if bad:
        raise ValueError(f"unknown tiers {bad} (have {', '.join(hair.CARD_TIERS)})")
    rep = hair_export.export_hair(name, Path(out_dir).expanduser(), tiers=tuple(tiers), groom=groom, check=check, sheet=save)
    lines = [f"{t}: {r['triangles']} triangles, {r['bytes'] // 1024} KB, {r['glb']}" for t, r in rep["tiers"].items()]
    if rep.get("groom"):
        lines.append(f"groom: {rep['groom'].get('alembic')}, {rep['groom'].get('usd')}")
    if rep.get("checks_text"):
        lines.append(rep["checks_text"])
    out = []
    if save and check:
        from PIL import Image as _I
        out.append(_png(_I.open(save)))
    return [*out, "\n".join([*lines, hair_route.export_next(name, out_dir, tiers)])]


@mcp.tool(structured_output=False)
def hair_from_reference(name: str, out: str = "", read_only: bool = False, authority: int | None = None,
                        compare: dict | None = None, seed: int = 0) -> str:
    """The HAIR READER: measure the hair on the model's fitted reference pictures (stand-off by region, halo, edge
    roughness, wisps, hairline height / softness / baby hairs, parting, colour with grey by region from ONE authority
    view) and set a START groom / strands / look from it (measured vs set, INFERRED where a picture can't show it).
    read_only: the read alone. out: groom a copy. authority: the colour view (default the most frontal). compare
    {view index: render png through that fitted camera}: the same read on our renders, ours | picture.
    Details: guide(topic="hair_from_reference")."""
    from . import hair_read, hair_route
    if compare:
        c = hair_read.compare(name, {int(k): v for k, v in _spec_arg(compare).items()}, authority=authority)
        st = hair_read.colour_step(c, (store.load(name).get("hair") or {}).get("look") or {})
        return (c["text"] + ("\ncolour step (authority view): " + st["why"] if st.get("why") else "") + "\n"
                + hair_route.compare_next(name))
    if read_only:
        r = hair_read.read(name, authority=authority, log=lambda s: None)
        return r["text"] + "\n" + hair_read.start(r, store.load(name))["text"] + "\n(read only: nothing saved)\n" \
            + hair_route.reader_next(name, out, True)
    return (hair_read.apply(name, out=out or None, authority=authority, seed=seed, log=lambda s: None)["text"] + "\n"
            + hair_route.reader_next(name, out, False))


@mcp.tool(structured_output=False)
def hair_reference(name: str, trace: dict | None = None, image_path: str | None = None, apply: bool = False,
                   widen: float = 1.8, save: str | None = None):
    """An optional finer fit after hair_from_reference, by hand: store a trace of a reference picture (landmarks, part,
    hairline, hair outline, clumps in image px), fit the camera to the face; apply=True carries the trace onto the
    groom (widen scales clump widths). image_path, save. Details: guide(topic="hair_reference")."""
    from PIL import Image as PI
    from . import hair_route
    from . import hair_head, hair_reference, hair_spec, hair_trace
    d = store._dir(name)
    if not (d / "spec.json").exists():
        raise ValueError(f"no model {name!r}")
    if trace is not None:
        tr = _spec_arg(trace)
    else:
        tr = hair_reference.ref_trace(name)
        if tr is None:
            raise ValueError("no stored trace: pass trace={...}\n" + HAIR_TRACE)
    if image_path:
        tr["image"] = str(Path(image_path).expanduser())
    if not tr.get("image") or not Path(tr["image"]).exists():
        raise ValueError(f"the reference image {tr.get('image')!r} doesn't exist (give image_path)")
    for k in ("part", "hairline", "hair"):
        if k in tr and (not isinstance(tr[k], list) or any(len(p) != 2 for p in tr[k])):
            raise ValueError(f"trace {k!r} is a list of [u, v] pixels")
    for c in tr.get("clumps") or []:
        if not isinstance(c, dict) or len(c.get("line") or []) < 2:
            raise ValueError('each trace clump is {"name", "line": [[u, v], ...] root -> tip, "width": px}')
    with PI.open(tr["image"]) as im:
        tr["image_size"] = [im.width, im.height]
    spec = store.load(name)
    sc = hair_head.scalp(name, spec)
    lms = tr.get("landmarks") or {}
    unknown = [n for n in lms if n not in sc.lm]
    if unknown:
        raise ValueError(f"unknown landmarks {unknown}; the model's: {', '.join(sorted(sc.lm))}")
    if not tr.get("crop"):
        P = np.array([*lms.values(), *(tr.get("hair") or []), *(tr.get("hairline") or [])], float)
        if not len(P):
            raise ValueError("give trace crop [x0, y0, x1, y1] or some landmarks / a hair outline")
        lo, hi = P.min(0), P.max(0)
        c, half = (lo + hi) / 2, (hi - lo).max() * 0.6
        tr["crop"] = [int(c[0] - half), int(c[1] - half), int(c[0] + half), int(c[1] + half)]
    (d / "ref_trace.json").write_text(json.dumps(tr, indent=1))
    text = []
    if len(lms) >= 6:
        cam = hair_reference.fit_camera(name, lms, tr["image_size"], tr["crop"], spec)
        cam["reference"] = tr["image"]
        (d / "ref_camera.json").write_text(json.dumps(cam, indent=1))
        e = cam["error_px"]
        text.append(f"camera fitted on {len(e)} landmarks: error px mean {np.mean(list(e.values())):.1f}, max "
                    f"{max(e.values()):.1f} ({', '.join(f'{k} {v}' for k, v in e.items())}); fov {cam['fov']:.1f} deg, "
                    f"{1000 * np.linalg.norm(np.asarray(cam['eye']) - sc.C) / cam['focal_px']:.2f} mm per reference px")
    elif lms:
        raise ValueError(f"fitting the camera needs at least 6 landmarks (got {len(lms)}); the model's: "
                         f"{', '.join(sorted(sc.lm))}")
    else:
        text.append("no landmarks: the trace is stored, no camera fitted")
    cams = {}
    for v, t in (tr.get("views") or {}).items():  # more matched views: another figure or picture
        vl = t.get("landmarks") or {}
        unknown = [n for n in vl if n not in sc.lm]
        if unknown or len(vl) < 6:
            raise ValueError(f"trace view {v!r}: needs >= 6 known landmarks (unknown {unknown}, got {len(vl)})")
        if not t.get("crop"):
            raise ValueError(f"trace view {v!r}: give its crop [x0, y0, x1, y1]")
        img = t.get("image") or tr["image"]
        with PI.open(img) as im:
            size = [im.width, im.height]
        prim = hair_reference.ref_camera(name) if not t.get("image") or t["image"] == tr["image"] else None
        # another figure in the same picture: the same lens (focal); its own picture: a focal of its own
        c = hair_reference.fit_camera(name, vl, size, t["crop"], spec, view=v, save=False,
                            focal=prim["focal_px"] if prim else None)
        c["reference"] = img
        cams[v] = c
        e = c["error_px"]
        text.append(f"view {v}: camera fitted on {len(e)} landmarks: error px mean {np.mean(list(e.values())):.1f}, "
                    f"max {max(e.values()):.1f}; {1000 * np.linalg.norm(np.asarray(c['eye']) - sc.C) / c['focal_px']:.2f}"
                    f" mm per reference px")
    if cams or (d / "ref_cameras.json").exists():
        (d / "ref_cameras.json").write_text(json.dumps(cams, indent=1))
    if apply:
        if hair_reference.ref_camera(name) is None:
            raise ValueError("apply needs a fitted camera (landmarks in the trace)")
        patch = hair_trace.from_trace(name, spec, widen=widen)
        h = spec.setdefault("hair", {})
        h["groom"] = hair_spec.merge_patch(h.get("groom") or {}, patch["groom"])
        v = store.save(name, spec, "hair: groom from the traced reference")
        dr = patch["groom"]["drawn"]
        text.append(f"saved v{v}: groom parting.line ({len(patch['groom']['parting']['line'])} points, side "
                    f"{patch['groom']['parting']['side']}), hairline.front_points, {len(dr)} drawn clumps "
                    f"({', '.join(c['name'] for c in dr)}).")
    return [_out(hair_trace.trace_image(name), save), "\n".join([*text, hair_route.reference_next(name, apply)])]
