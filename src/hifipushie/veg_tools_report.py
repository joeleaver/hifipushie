"""What the tools say: the reference, a plant's report, ground lines, a set's names and report. Part of the plant tools (veg_tools.py has the overview)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import vegetation
from . import vegetation_fit, vegetation_measures, vegetation_tree
from .veg_tools import _dir, grown, load, variants

# ---------------------------------------------------------------- what the tools say and show
def reference(name: str) -> dict | None:
    p = _dir(name) / "reference.json"
    return json.loads(p.read_text()) if p.exists() else None


def set_reference(name: str, image: str, mask: dict, bare: bool = False, credit: str = "") -> dict:
    """Keep a reference photo for the plant: copied beside it, with how its silhouette is taken (`mask` =
    vegetation_measures.reference_mask arguments: crop + foot, or a traced polygon) and whether the photo is of a bare tree."""
    import shutil
    d = _dir(name)
    d.mkdir(parents=True, exist_ok=True)
    src = Path(image)
    if not src.exists():
        raise ValueError(f"no image at {image}")
    dst = d / ("reference" + src.suffix.lower())
    if src.resolve() != dst.resolve():
        shutil.copyfile(src, dst)
    m = vegetation_measures.reference_mask(str(dst), **mask)  # (fails here if the mask's arguments are wrong)
    if m.sum() < 50:
        raise ValueError("the mask is empty: check crop/foot/tol, or trace a polygon")
    ref = {"image": str(dst), "mask": mask, "bare": bool(bare), "credit": credit}
    (d / "reference.json").write_text(json.dumps(ref, indent=1))
    return ref


def _report_clump(name: str, T: dict) -> str:
    """An assembled plant in numbers: size, cards per layer, how they stand, cover from above, triangles."""
    from . import veg_small
    from . import veg_leaf_atlas
    s, m = T["spec"], veg_small.measures(T)
    at = veg_leaf_atlas.atlas(s["leaves"], (s.get("bark") or {}).get("twig_color") or [0.45, 0.4, 0.35])
    pc = veg_leaf_atlas.part_cards(s["leaves"])
    tw = T["twigs"]
    out = [f"plant {name}: {s.get('species') or 'no preset'}, assembled from cards (plant: clump), seed {s.get('seed', 1)}",
           f"size: {m['height_m']} m tall, {m['spread_m']} m across; {m['cards']} cards on {m.get('stalks', 0)} stalks; "
           f"{sum(len(at['cards'][c]['F']) for c in tw['card'])} foliage triangles at full detail",
           f"cards stand at {m['card_elevation_p10_50_90'][1]:.0f} deg above level (p10-p90 {m['card_elevation_p10_50_90'][0]:.0f} to "
           f"{m['card_elevation_p10_50_90'][2]:.0f}: 90 = upright blades, 0 = lying flat); cover seen from above {m['cover_from_above']} of its footprint"]
    for i, L in enumerate(s["clump"]["layers"]):
        n_ = int(np.isin(tw["card"], pc.get(L.get("part") or "", [])).sum()) if L.get("part", "main") else 0
        out.append(f"  layer {i}" + (f" '{L['name']}'" if L.get("name") else "") + f": part {L.get('part', 'main')}, count {L.get('count', 12)}"
                   + (f", on stalks {L['stem']} m" if L.get("stem") else "") + (f", standing on layer {L['on']}" if L.get("on") is not None else "")
                   + (f" ({n_} cards of this part in all)" if n_ else ""))
    out.append(f"pictures (parts of the atlas): {', '.join(f'{k} x{len(v)}' for k, v in pc.items())}; atlas {at['color'].shape[0]} px, card fill {at['fill']:.2f}")
    warn = []
    if m["cards"] * at["triangles"] > 3000:
        warn.append(f"WARNING: {m['cards'] * at['triangles']} foliage triangles for one small plant; a scattered plant wants 50-600 (fewer, larger cards)")
    if at["fill"] < 0.15:
        warn.append(f"WARNING: card fill {at['fill']:.2f}: the cards are mostly empty (overdraw); `card.strips` for long thin pictures, or fuller pictures")
    if m["height_m"] > 0 and tw["pos"][:, 2].min() < -0.06:
        warn.append("WARNING: cards start more than 6 cm under the ground")
    se = s.get("season", "summer")
    stt = veg_small.season_state(s, se)
    hid = veg_small.hidden_parts(s, se)
    out.append(f"season {se}: " + ("died back to its foot (not evergreen; give clump.seasons.winter a state to keep it)" if stt is None else
                                   f"leaf colour {stt['color']}, cards laid down {stt['flatten']:.1f}, size x{stt['scale']:.2f}"
                                   + (f"; layers out of season: {', '.join(hid)}" if hid else ""))
               + " (clump.seasons; a layer's own `seasons` list)")
    from . import veg_style
    from . import veg_style_dress, veg_style_small
    sty = veg_style.sheet(s)
    if sty:  # what the style drew instead of the cards
        inf_ = veg_style_dress.dress(T, sty, season=se)["info"]
        out += veg_style_small.lines(inf_) + [f"style budget: LOD 0 {inf_['triangles']} triangles; sheet numbers: get_plant shows them under `style` (block `clump`)"]
        warn += veg_style_small.warnings(inf_)
    return "\n".join(out + warn)


def report(name: str) -> str:
    """The grown plant in numbers: size, form (measured on its own silhouettes), limbs, foliage, guides, and its
    reference match when it has one. WARNINGS last."""
    from . import veg_leaf_place
    T = grown(name)
    s = T["spec"]
    st = T["stats"]
    warn = []
    if T.get("sward"):
        from . import veg_sward
        return veg_sward.report(name, T)
    if T.get("clump"):
        return _report_clump(name, T)
    out = [f"plant {name}: {s.get('species') or 'no preset'}, age {s['age']} ({st['steps']} growth steps), "
           f"{st['nodes']} nodes, grown in {st['grow_s']} s",
           f"size: {st['height_m']} m tall, trunk DIAMETER {st['trunk_diameter_m']} m at the foot (with its flare), "
           f"branch orders to {st['max_order']}" + (f", {st['pruned_nodes']} nodes cut by prunes" if st.get("pruned_nodes") else "")]
    out_g, warn_g = ground_lines(T)
    out += out_g
    from . import veg_style
    from . import veg_style_dress, veg_style_small
    sty = veg_style.sheet(s)
    if sty:  # what the style drew of this plant, and whether it is still the same tree from afar
        inf_ = veg_style_dress.dress(T, sty)["info"]
        out += veg_style_small.lines(inf_) + [f"style budget: LOD 0 {inf_['triangles']} triangles (wood {inf_['wood_triangles']}, crown {inf_['crown_triangles']}); "
                                        f"sheet numbers: get_plant shows them under `style`"]
        warn_g = warn_g + veg_style_small.warnings(inf_)
    if st.get("dead_stubs"):
        P_, d_ = T["pos"], T["dead"]
        seg_ = np.linalg.norm(P_ - P_[T["parent"]], axis=1)
        lv_ = T["leafy"] & ~d_
        base_ = float(np.percentile(P_[lv_, 2], 5)) if lv_.any() else 0.0
        out.append(f"dead wood: {int((d_ & (T['order'] == 1)).sum() and len(np.unique(T['axis'][d_ & (T['order'] == 1)])))} limbs the shade killed within the last "
                   f"{s['habit']['dead_keep']} years are still on the trunk ({seg_[d_].sum():.0f} m of dead wood, from {P_[d_, 2].min():.1f} m up); "
                   f"live crown from {base_:.1f} m = {1 - base_ / T['height']:.0%} of the height"
                   + ("" if veg_leaf_place.dead_part(s["leaves"]) is not None else " (no `leaves.parts.dead` picture: its fine twigs are not drawn)"))
    ms = [vegetation_measures.shape_measures(vegetation_measures.silhouette(T, az, 12, leaves=True)[0]) for az in (0, 90)]
    f = lambda k: round(float(np.mean([m[k] for m in ms])), 2)
    H = T["height"]
    ends = T["pos"][T["ends"] & (T["order"] > 0)]
    if not len(ends):
        ends = T["pos"][T["ends"]]
    cen = ends[:, :2].mean(0) if len(ends) else np.zeros(2)
    rad_ = float(np.percentile(np.linalg.norm(ends[:, :2] - cen, axis=1), 90)) if len(ends) else 0.0
    zlow = float(np.percentile(ends[:, 2], 3)) if len(ends) else 0.0
    covs = []
    for az in (0, 90):  # cover of the CROWN: the side view above the crown's base, trunk rows left out
        m_, fr = vegetation_measures.silhouette(T, az, 12, leaves=True)
        top = int(max((fr["z1"] - zlow) * fr["px_per_m"], 1))
        covs.append(1 - vegetation_measures.shape_measures(m_[:top])["porosity"] if m_[:top].any() else 0.0)
    cover = float(np.mean(covs))
    tr = T["pos"][T["order"] == 0]
    tip = tr[np.argmax(tr[:, 2])]
    lean = float(np.degrees(np.arctan2(np.linalg.norm(tip[:2]), max(tip[2], 1e-6))))
    out.append(f"form (in leaf, two side views): width/height {f('width_over_height')}; widest at {f('widest_at')} of the "
               f"height; crown base (the lowest branch ends) at {zlow:.1f} m = {zlow / max(H, 1e-6):.2f} of the height")
    out.append(f"trunk: {tip[2]:.1f} m to its top, leaning {lean:.0f} deg from upright"
               + (f" toward [{tip[0] / max(np.linalg.norm(tip[:2]), 1e-6):+.1f}, {tip[1] / max(np.linalg.norm(tip[:2]), 1e-6):+.1f}]" if lean > 3 else "")
               + f" (its top stands [{tip[0]:+.1f}, {tip[1]:+.1f}] m from its foot)")
    out.append(f"crown: its middle sits [{cen[0]:+.1f}, {cen[1]:+.1f}] m from the trunk's foot ({np.linalg.norm(cen) / max(rad_, 0.5):.2f} "
               f"of its radius {rad_:.1f} m: 0 = centred, 0.5+ = plainly swept to one side); cover {cover:.2f} (1 = solid from the side)")
    ang = vegetation_measures.branch_angles(T, 1)
    if ang["n"]:
        drawn = sum(1 for ai in T["guides"].values() if T["axes"][ai]["order"] == 1)
        out.append(f"limbs: {ang['n']} first-order branches ({drawn} drawn; medians of so few jump about), leaving the trunk at {ang['insertion_p10_50_90'][1]} deg "
                   f"(p10-p90 {ang['insertion_p10_50_90'][0]}-{ang['insertion_p10_50_90'][2]}), their far halves "
                   f"{ang['elevation_p10_50_90'][1]} deg above level ({ang['elevation_p10_50_90'][0]} to {ang['elevation_p10_50_90'][2]})")
    lb = vegetation_tree.limbs(T)
    if lb:
        out.append("main limbs (name: leaves the trunk at height, base diameter, its length along its stoutest wood and where that "
                   "ends, the span of everything it carries. The compass name is by where its farthest wood lies and "
                   "is THIS tree's; the id lasts through edits. edit_plant take_limb makes one a guide you can redraw):")
        for L in lb:
            out.append(f"  {L['name']}{' (drawn)' if L['guide'] else ' (id ' + L['id'] + ')'}: at {L['height']} m, {L['diameter'] * 100:.0f} cm, "
                       f"{L['length']} m long to [{L['end'][0]:+.1f}, {L['end'][1]:+.1f}, {L['end'][2]:.1f}], "
                       f"carries {L['low']}-{L['high']} m high, {L['reach']} m out, since year {L['born_year']}")
    tw = veg_leaf_place.place_live(T)
    if len(tw["pos"]):
        out.append(f"foliage: {len(tw['pos'])} twigs ({s['leaves'].get('shape', 'ovate')} leaves, "
                   f"{s['leaves'].get('length', 0.07)} m)")
    else:
        out.append("foliage: none (winter, dead, or decayed)")
    for g, ai in T["guides"].items():
        nodes = np.flatnonzero((T["axis"] == ai) & T["pin"])
        path = np.asarray(s["guides"][g]["path"], float)
        if not len(nodes):
            out.append(f"guide {g}: not grown")
            fy = s["guides"][g].get("from_year", 0)
            warn.append(f"guide {g} has no nodes: " + (f"its from_year {fy} is at or past the tree's age {s['age']}" if fy >= s["age"]
                        else "a prune volume covers it, or the wood it started from was cut"))
            continue
        end = float(np.linalg.norm(T["pos"][nodes[-1]] - path[-1]))
        kids = int(np.isin(T["parent"], nodes).sum() - len(nodes) + 1)
        sub = np.zeros(len(T["parent"]), bool)
        sub[nodes] = True
        for i_ in range(int(nodes[0]), len(sub)):
            sub[i_] |= sub[T["parent"][i_]]
        reach = float(np.linalg.norm(T["pos"][sub][:, :2], axis=1).max())
        out.append(f"guide {g}: order {T['axes'][ai]['order']}, {len(nodes)} nodes on its path, "
                   f"{'drawn to its end' if end < 0.3 else f'{end:.1f} m short of its end'}, {kids} branches from it; "
                   f"with what grew from it, it reaches {reach:.1f} m out from the foot, {T['pos'][sub][:, 2].min():.1f}-{T['pos'][sub][:, 2].max():.1f} m high")
        if end >= 0.3:
            warn.append(f"guide {g} stops {end:.1f} m short: give it more years (until_year) or more vigour")
    for g in (s.get("guides") or {}):
        if g not in T["guides"]:
            warn.append(f"guide {g} never started (from_year past the tree's age?)")
    ref = reference(name)
    if ref:
        R = vegetation_measures.reference_mask(ref["image"], **ref["mask"])
        m = vegetation_fit.match(T, R, bare=ref["bare"], azimuths=(0, 45, 90, 135))
        o, r = m["ours"], m["ref"]
        out.append(f"reference: outline IoU {m['iou']:.2f} (best from azimuth {m['azimuth']}); width/height "
                   f"{o['width_over_height']:.2f} vs {r['width_over_height']:.2f}, bole {o['bole']:.2f} vs {r['bole']:.2f}, "
                   f"widest at {o['widest_at']:.2f} vs {r['widest_at']:.2f}")
    for dd in st.get("dead") or []:
        if dd.get("missing"):
            warn.append(f"dead: {dd['what']} is not on this tree any more (an edit regrew it without that limb): nothing died there")
        else:
            out.append(f"dead wood ({dd['what']}): {dd['nodes']} nodes died, {dd['broken_off']} of them (the thin ends) broken off; "
                       f"what stands is bare and grey, {dd['low']}-{dd['high']} m high")
            if dd["nodes"] and dd["broken_off"] >= dd["nodes"] - 1:
                warn.append(f"dead {dd['what']}: all of it broke off (min_radius is thicker than the wood there): nothing shows")
            if not dd["nodes"]:
                warn.append(f"dead {dd['what']}: no wood there (a limb shorter than its `from`, or an empty volume)")
    side = T["order"] > 0
    if side.any():  # clearance over the ground as it lies (a hillside rises under the uphill limbs)
        from . import veg_look
        Pn = T["pos"][side]
        gz = np.array([veg_look.ground_z(s, q) for q in Pn[:, :2]]) if (s.get("environment") or {}).get("ground", {}).get("slope") else np.zeros(len(Pn))
        cl = Pn[:, 2] - gz
        i_ = int(np.argmin(cl))
        out.append(f"lowest wood: {cl[i_]:.1f} m above the ground at [{Pn[i_][0]:+.1f}, {Pn[i_][1]:+.1f}]"
                   + (f" (the ground there is {gz[i_]:+.1f} m against the foot)" if abs(gz[i_]) > 0.05 else ""))
        if cl[i_] < -0.05:
            warn.append(f"{int((cl < 0).sum())} nodes are under the ground (down to {cl[i_]:.1f} m) round [{Pn[i_][0]:+.1f}, {Pn[i_][1]:+.1f}]: "
                        f"raise that limb's path, prune {{\"under\": z}}, or lower habit.sag")
    longest = max((L["length"] for L in lb), default=0.0)
    if rad_ > 0.9 * H or longest > 1.4 * H:
        warn.append(f"the crown is {2 * rad_:.0f} m across on a {H:.0f} m tree (longest limb {longest:.0f} m): limbs ran away. "
                    f"With fewer branch orders (max_order) or less shedding the same vigour goes into fewer, longer shoots: "
                    f"lower habit.vigour / shoot_max, or set tip_life for the limbs")
    for c in st.get("cuts") or []:
        if not c["nodes"]:
            warn.append(f"the cut at year {c['year']} cut nothing: the tree had no wood in that volume yet (a pollard's "
                        f"first cut must come after the trunk has grown past the cut height)")
            continue
        out.append(f"cut at year {c['year']}: {c['nodes']} nodes of wood removed, {c['stubs']} stubs left to sprout")
    lost = st.get("pruned_nodes", 0)
    if lost > 0.5 * (st["nodes"] + lost):
        warn.append(f"the prunes cut {lost} of {st['nodes'] + lost} nodes ({lost / (st['nodes'] + lost):.0%}): what is left is mostly "
                    f"stubs; shrink the prune volumes (get_plant lists them) or use a timed `cuts` entry so the tree regrows")
    elif st["nodes"] < 12 * st["steps"] and not s.get("cuts"):
        warn.append(f"only {st['nodes']} nodes after {st['steps']} steps: the tree starved (raise habit.vigour, lower habit.shed, "
                    f"or it is shaded by its environment: neighbours/stand)")
    if st["nodes"] > 90000:
        warn.append("over 90k nodes: slow to look at and heavy to export (lower habit.vigour, bud_break or max_order)")
    if s.get("height") and abs(T["height"] - s["height"]) > 0.15 * s["height"] and not s.get("cuts"):
        warn.append(f"asked height {s['height']} m, grew {T['height']:.1f} m. `height` sizes the UNEDITED tree of this "
                    f"description (it sets the segment length); guides, prunes, cuts and envelopes then change what grows. "
                    + ("With a drawn trunk the trunk's own path decides: make the path as tall as you want it, and drop `height`."
                       if any(T["axes"][a]["order"] == 0 for a in T["guides"].values()) else "Change age or habit.unit, or the edits."))
    try:
        p_age = vegetation.preset(s["species"]).get("age") if s.get("species") else None
    except ValueError:
        p_age = None
    if p_age and s["age"] > 1.4 * p_age and not s.get("height"):
        warn.append(f"age {s['age']} is well past the age the {s['species']} preset was tuned at ({p_age}): size keeps growing with "
                    f"age here ({T['height']:.0f} m); for an older-looking tree of normal size set `height`, or lower habit.vigour")
    if s["habit"]["clear"] > 0.9 * tip[2]:
        warn.append(f"habit.clear {s['habit']['clear']} m is nearly the whole trunk ({tip[2]:.1f} m): no limbs can leave it")
    dr = vegetation_fit.droop(T, max(f("bole"), 0.1))
    if dr > 0.1:
        warn.append(f"{dr:.0%} of the shoot ends hang under the crown's base away from the trunk (habit.sag, tropism)")
    d_end = vegetation_tree._norm(T["pos"] - T["pos"][T["parent"]])[T["ends"]]
    down = float((d_end[:, 2] < -0.5).mean()) if len(d_end) else 0.0
    out.append(f"shoot ends: {down:.0%} point steeply down (weeping), {float((d_end[:, 2] > 0.5).mean()) if len(d_end) else 0:.0%} steeply up")
    if down > 0.35 and min(vegetation_tree._per(s["habit"]["tropism"], np.arange(6))) > -0.3:
        warn.append(f"{down:.0%} of the shoot ends hang though the habit isn't a weeping one: lower habit.sag ({s['habit']['sag']}) "
                    f"or raise tropism on the high orders")
    if load(name.partition("#")[0]).get("set") and "#" not in name:
        out.append(set_report(name))
    return "\n".join(out + [f"WARNING: {w}" for w in warn] + warn_g)


def ground_lines(T: dict, triangles: int | None = None, force: bool = False) -> tuple[list, list]:
    """(lines, WARNING lines) on how the drawn plant stands on its ground (veg_ground.audit: wood, card corners). The
    cards need the plant's atlas: when that isn't made yet (minutes for a needle atlas) only the wood is judged, and
    the line says so; look_plant and export_plant always judge the cards."""
    from . import veg_ground
    from . import veg_leaf_atlas
    s = T["spec"]
    twc = (s.get("bark") or {}).get("twig_color") or [0.45, 0.4, 0.35]
    if force or triangles or veg_leaf_atlas.atlas_ready(s["leaves"], twc):
        lines = veg_ground.report(veg_ground.audit(T, triangles))
    else:
        d = veg_ground.drawn({**T, "spec": {**s, "season": "bare"}})
        a = veg_ground.audit(T, d=d)
        lines = [f"ground: lowest limb wood {a['lowest_wood_m']} m over it, {a['resting_m']} m of limbs rest on it "
                 f"(cards not judged yet: look_plant does)"] + [l_ for l_ in veg_ground.report(a)[1:]]
    return [l_ for l_ in lines if not l_.startswith("WARNING")], [l_ for l_ in lines if l_.startswith("WARNING")]


def set_names(name: str) -> list[str]:
    return [f"{name}#{k + 1}" for k in range(len(variants(load(name))))]


def set_report(name: str) -> str:
    """The set's plants in a line each: seed, age, height, crown width, trunk, nodes."""
    out = []
    for n_ in set_names(name):
        T = grown(n_)
        st = T["stats"]
        w = 2 * float(np.percentile(np.linalg.norm(T["pos"][:, :2], axis=1), 98))
        out.append(f"  {n_}: seed {T['spec']['seed']}, age {T['spec']['age']}, {st['height_m']} m tall, crown {w:.1f} m wide, "
                   f"trunk {st['trunk_diameter_m']} m, {st['nodes']} nodes" + (" STARVED" if st["nodes"] < 12 * st["steps"] else ""))
    hs = [grown(n_)["height"] for n_ in set_names(name)]
    return f"set of {len(hs)} from {name} (heights {min(hs):.1f}-{max(hs):.1f} m):\n" + "\n".join(out)
