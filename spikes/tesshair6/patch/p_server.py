"""p_server.py: (applied once) server.look_hair: views "ref<i>", stage=, measure=."""
from pathlib import Path

p = Path(__file__).resolve().parents[3] / "src/hifipushie/server.py"
s = p.read_text()


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:70])
    s = s.replace(a, b)


rep('''              tier: str | None = None, debug: str | None = None, engine: str = "eevee"):
    """Fast hair renders (EEVEE, 4-30 s) with gates: outline dents, bare volume, fit to a traced reference. views,
    clay, layout (top sketch), reference, only (lock names), tier (game cards) + debug, engine "cycles", size, save.
    Needs `sync` once. Details: guide(topic="look_hair")."""''',
    '''              tier: str | None = None, debug: str | None = None, engine: str = "eevee",
              stage: str | None = None, measure: dict | None = None):
    """Fast hair renders (EEVEE, 4-30 s) with gates: outline dents, bare volume, fit to a traced reference. views
    (+ "ref0".. = the reference pictures' fitted cameras), clay, layout (top sketch), reference, only (lock names),
    tier (game cards) + debug, engine "cycles", size, save, stage (a model with the same head whose scene is used),
    measure {"view": "ref2", "mask": png, "tie": [x, y], "colour": true} (outline / tail / colour against that
    picture). Needs `sync` once (of the model or its stage). Details: guide(topic="look_hair")."""''')
rep('''    bad = [v for v in views if v not in hair.VIEWS]
    if bad:
        raise ValueError(f"unknown views {bad} (have {', '.join(hair.VIEWS)}, layout)")''',
    '''    measure = _spec_arg(measure) if measure else None
    if measure and measure.get("view") and measure["view"] not in views:
        views.append(measure["view"])
    bad = [v for v in views if v not in hair.VIEWS and not re.fullmatch(r"ref\\d+", str(v))]
    if bad:
        raise ValueError(f"unknown views {bad} (have {', '.join(hair.VIEWS)}, layout, ref0.. = the reference "
                         f"pictures' fitted cameras)")''')
rep('''        sheet, secs, fr = hair.look(name, views=tuple(views), size=size, reference=reference, spec=spec, clay=clay,
                                    only=only, budget=tier, debug=debug, engine=engine)''',
    '''        sheet, secs, fr = hair.look(name, views=tuple(views), size=size, reference=reference, spec=spec, clay=clay,
                                    only=only, budget=tier, debug=debug, engine=engine, stage=stage)''')
rep('''        text = f"rendered in {secs}s; {text}\\n" + gates
''', '''        text = f"rendered in {secs}s; {text}\\n" + gates
        if measure:
            bad = set(measure) - {"view", "mask", "tie", "colour"}
            if bad or not measure.get("view"):
                raise ValueError(f"measure: {{'view': 'ref<i>', 'mask': png, 'tie': [x, y], 'colour': bool}}"
                                 + (f" (unknown {sorted(bad)})" if bad else ""))
            m = hair.measure_ref(name, measure["view"], mask=measure.get("mask"), tie=measure.get("tie"),
                                 colour=bool(measure.get("colour", True)), stage=stage)
            o = m.get("outline")
            if o:
                text += (f"\\nagainst the picture ({m['view']}, {m['mm_per_px']} mm a px): IoU {o['iou']}, area x{o['area']}"
                         + (f", outline {o['chamfer_mm']} mm apart" if "chamfer_mm" in o else ""))
                if "below" in o:
                    text += (f"\\n  below the tie: {100 * o['below']:+.0f}% of hers; length {o['ours']['length_mm']} mm (hers "
                             f"{o['hers']['length_mm']}), width {o['ours']['width_mm']} mm (hers {o['hers']['width_mm']}), "
                             f"reach {o['ours']['back_mm']} mm (hers {o['hers']['back_mm']}). One draw moves these ~10%: "
                             f"judge over 3-4 groom seeds")
            c = m.get("colour") or {}
            if c.get("ours") and c.get("picture"):
                text += f"\\n  colour over dense hair ({engine}), ours | picture (L*, chroma, hue):"
                for b in ("mean", "shadow", "mid", "highlight"):
                    a_, b_ = c["ours"][b], c["picture"][b]
                    text += f"\\n    {b}: {a_['L']} / {a_['chroma']} / {a_['hue']}  |  {b_['L']} / {b_['chroma']} / {b_['hue']}"
                text += ("\\n  (EEVEE: look.eevee_gain / eevee_sat; Cycles: look.cycles_fit, cycles_width for cover, "
                         "cycles_sat for chroma)")
''')
if "\nimport re\n" not in s:
    rep("\nimport json\n", "\nimport json\nimport re\n")
p.write_text(s)
print("ok")
