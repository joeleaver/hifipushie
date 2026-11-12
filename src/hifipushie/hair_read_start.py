"""The start: a first groom from a read, its text, and `apply`. Part of the hair read (hair_read.py has the overview)."""
from __future__ import annotations

import copy
import json

import numpy as np

from . import hair_read
from . import store
from .hair_read_read import read

def start(r: dict, spec: dict) -> dict:
    """The START from a read: style (strands), groom patch (loose short cut: lengths, volume by region, lay, flow,
    hairline front points, parting, grey by region), strands (crop recipe + halo / fly-aways from the read) and look
    (seen, grey, grey_amount, variation, scalp tint). rows = (key, value set, what it came from)."""
    s = r["summary"]
    rows = []

    def put(key, val, why):
        rows.append((key, val, why))
        return val
    so = {k: v / 1000.0 for k, v in s["standoff"].items() if np.isfinite(v)}
    top = so.get("top", so.get("front", 0.012))
    so_all = {reg: so.get(reg, {"crown": so.get("top", top), "nape": 0.4 * so.get("back", so.get("sides", top)),
                                "back": so.get("sides", top), "front": top, "sides": 0.8 * top, "top": top}[reg])
              for reg in hair_read.REGIONS}
    inferred = {reg: reg not in so for reg in hair_read.REGIONS}
    bottom = s.get("bottom_m")
    long_ = bottom is not None and bottom > hair_read.LONG_BELOW
    if long_ or np.mean(list(so_all.values())) * 1000 > hair_read.SHORT_MM or max(so_all.values()) * 1000 > 1.5 * hair_read.SHORT_MM:
        short = False
        if not long_:
            rows.append(("style", None, f"mean stand-off {1000 * np.mean(list(so_all.values())):.0f} mm and no hair below "
                                        "the jaw: not a short cut, not loose long hair; the reader sets hairline, parting "
                                        "and look only (groom the shape by hand: tied hair is tie_hair's)"))
    else:
        short = True
    g = {}
    if long_:
        # LOOSE LONG hair (the guide's loose-hair recipes): a one-length cut at the measured bottom (`level`), long
        # enough to reach it, `body` and `lift` from the stand-off at the sides and top, framed off the face
        lvl = -float(bottom) + 0.01  # (m from the head centre; the lowest 0.1 % of the mask is the longest strand)
        ln = float(np.clip(bottom + 0.16, 0.15, 0.8))
        put("groom.loose.level", round(lvl, 3), f"MEASURED: the hair reaches {bottom} m under the head centre (the view "
                                                "showing most of it; behind the shoulders it may reach further: INFERRED)")
        put("groom.loose.length", round(ln, 3), "the level + the crown's way down (INFERRED; the level cuts it)")
        side_so = so_all.get("sides", 0.015)
        body = round(float(np.clip(side_so - 0.006, 0.006, 0.04)), 4)
        lift = round(float(np.clip(so_all.get("top", 0.012) - 0.008, 0.002, 0.015)), 4)
        put("groom.loose.body", body, f"MEASURED side stand-off {round(1000 * side_so, 1)} mm - 6 mm (the strands' spread)")
        put("groom.loose.lift", lift, f"MEASURED top stand-off {round(1000 * so_all.get('top', 0.012), 1)} mm - 8 mm")
        wv = s.get("waviness")
        g["loose"] = {"length": round(ln, 3), "level": round(lvl, 3), "spacing": 0.02, "body": body, "lift": lift,
                      "stiff": 0.25, "messy": 0.08, "uneven": 0.35, "face": 1.0}
        put("groom.loose (rest)", "spacing 0.02, stiff 0.25, messy 0.08, uneven 0.35, face 1", "the guide's long-hair recipes")
        if s.get("halo_all") is not None:  # loose hair's own halo / fly-away words (rule 4 / 7)
            g["loose"]["halo"] = put("groom.loose.halo", round(float(np.clip(2.5 * s["halo_all"], 0.1, 1.0)), 2),
                                     f"MEASURED halo density {s['halo_all']} (hair-garrett family r4: 1.0 read ~0.3 of it "
                                     f"with the old quartered dial)")
        if s.get("wisps_per_10cm") is not None:
            g["loose"]["flyaway"] = put("groom.loose.flyaway", round(float(np.clip(0.01 * s["wisps_per_10cm"], 0.02, 0.2)), 3),
                                        f"MEASURED {s['wisps_per_10cm']} wisps / 10 cm")
        # The two principles (hair_guide.md, top): EVEN ROOTS (EVERY strand from one even sampling of the scalp; the
        # locks are dense GUIDES 4 mm apart that only steer direction, each bank of the part its own, magenta
        # only on the part line) and ARC UP, THEN FALL (out of the scalp by region, from the measured stand-off)
        g["loose"].update({"spacing": 0.004, "width": 2.4})
        arc = {reg: round(float(np.clip(0.25 * (1000 * so_all.get(reg, 0.008) / 10.0) * w, 0.0, 0.4)), 3)
               for reg, w in (("front", 0.8), ("top", 1.0), ("sides", 0.4), ("back", 0.4), ("nape", 0.0))}
        g["loose"]["out"] = put("groom.loose.out", arc, "ARC UP THEN FALL: 0.25 x stand-off / 10 mm x (front .8, top 1, "
                                                        "sides / back .4, nape 0)")
        st_long = {"count": 260000, "clump": 0.45, "loose": 0.2, "stray": 0.6, "tips": 0.5, "even": 1.0, "halo_soft": 1.0}
        put("strands.even", 1.0, "EVEN ROOTS: every strand from one even sampling of the scalp, shaped by the lock "
                                 "guides (groom.loose.spacing 4 mm: guides, not root owners); count 260k")
        if wv is not None:
            k = float(np.clip((wv - 0.08) / 0.3, 0.0, 1.0))  # 0 straight .. 1 waves
            st_long.update({"wave": round(0.002 + 0.014 * k, 4), "wavelength": round(0.16 - 0.07 * k, 3), "curl": round(0.25 * k, 2)})
            put("strands.wave / wavelength / curl", [st_long["wave"], st_long["wavelength"], st_long["curl"]],
                f"MEASURED waviness {wv} of the lengths (0.08 straight .. 0.38 waves; the guide's straight / waves recipes)")
        put("strands (rest)", "count 120000, clump 0.45, loose 0.2, stray 0.6, tips 0.5", "the guide's long-hair recipes")
    if short:
        # LIFT by region (groom.loose.lift; groom.volume does nothing to loose hair): a laid short lock's strands
        # spread ~LIFT_SPREAD m over its guide, so the guide stands at the stand-off less that
        lift = {reg: round(float(np.clip(so_all[reg] - hair_read.LIFT_SPREAD, 0.001, 0.02)), 4) for reg in ("front", "top", "sides", "back", "nape")}
        put("groom.loose.lift", lift, f"MEASURED stand-off per region - {1000 * hair_read.LIFT_SPREAD:.0f} mm (the strands' own spread"
            + (f"; INFERRED for {', '.join(k for k in hair_read.REGIONS if inferred[k])})" if any(inferred.values()) else ")"))
        # a combed short cut is longer on top and front, clipped at the sides and back, tapering to the nape (a
        # barber's taper); the stand-off sets the scale
        ln = {"front": float(np.clip(4.0 * so_all["front"], 0.03, 0.08)), "top": float(np.clip(4.0 * so_all["top"], 0.03, 0.08)),
              "sides": float(np.clip(1.5 * so_all["sides"], 0.01, 0.025)), "back": float(np.clip(1.5 * so_all["back"], 0.01, 0.025)),
              "nape": float(np.clip(0.6 * so_all["nape"], 0.005, 0.012))}
        ln = {k: round(v, 3) for k, v in ln.items()}
        put("groom.loose.length", ln, "INFERRED: a short cut lies over itself, its length is not in a picture; top / front "
                                     "4x the stand-off, sides / back 1.5x, the nape tapering (a barber's taper)")
        p = s.get("parting") or {}
        sweep = p.get("sweep")
        sx = 0.0 if sweep is None else float(np.clip(sweep, -1, 1))
        # front: up and back, over to the side the front is combed toward (image right = his left = +x, front view)
        flow = {"front": [round(0.6 * sx, 2), 0.75, 0.45], "top": [round(0.4 * sx, 2), 0.9, 0.0], "sides": [0.0, 0.7, -0.7],
                "back": [0.0, 0.15, -1.0], "nape": [0.0, 0.05, -1.0]}
        put("groom.loose.flow", flow, f"one comb direction per region: front up and back, over by the measured sweep {sweep}; "
                                      "sides back and down; back and nape down (prior: a combed short cut)")
        lay = {"front": 0.35, "top": 0.65, "sides": 0.5, "back": 0.6, "nape": 0.6}
        put("groom.loose.lay", lay, "prior (combed flat along the flow); with the locks thin enough (thickness) not to sink")
        loose = {"length": ln, "spacing": 0.005, "width": 2.4, "lift": lift, "body": 0.004, "thickness": hair_read.LOOSE_THICK,
                 "messy": {"front": 0.25, "top": 0.25, "sides": 0.1, "back": 0.06, "nape": 0.04}, "uneven": 0.5,
                 "flow": flow, "lay": lay, "stiff": {"front": 0.55, "top": 0.5, "sides": 0.6, "back": 0.65, "nape": 0.6},
                 "out": {"front": 0.15, "top": 0.05, "sides": 0.0, "back": 0.0, "nape": 0.0}}
        put("groom.loose.thickness", hair_read.LOOSE_THICK, "a laid lock thicker than twice its clearance sinks half its strands into "
                                                  "the skin; pushed out, they crumple into curls (hair-garrett r1-r2)")
        put("groom.loose (rest)", "spacing 0.005, width 2.4, body 0.004 (a dense, continuous combed surface: at 8 mm the locks parted into ridges with scalp between, hair-heads r11), messy low, uneven 0.5, stiff per region",
            "a combed short cut")
        loose["fade"] = put("groom.loose.fade", {"width": 0.02}, "a short cut fades out at the nape (prior: a barber's "
                                                                 "fade over 2 cm; the nape ended in a ledge without it)")
        g["loose"] = loose
    # hairline: the measured front points (|az| <= 75: the front and temples), heights in m
    hp = [[a, z] for a, z, e, n in s.get("hairline") or [] if a <= 75]
    if len(hp) >= 3:
        g["hairline"] = {"front_points": [[round(a, 1), round(z, 4)] for a, z in hp]}
        put("groom.hairline.front_points", f"{len(hp)} points, |az| {hp[0][0]:.0f}-{hp[-1][0]:.0f} deg",
            "MEASURED: hair / skin boundary pixels cast onto the scalp, left and right together")
    else:
        put("groom.hairline", "default", "INFERRED: too little hairline seen")
    p = s.get("parting") or {}
    if p.get("seen") and p.get("x_m") is not None:
        side = "left" if p["x_m"] > 0 else "right"
        g["parting"] = {"side": side, "offset": round(abs(float(p["x_m"])), 3)}
        put("groom.parting", g["parting"], f"MEASURED (front view: strand flip {p.get('strength')}, scalp line {p.get('scalp')})")
    elif long_ and p.get("sweep") is not None and abs(float(p["sweep"])) > 0.25:
        # long hair combed over to one side falls AWAY from a part on the other (front view: image right = the
        # person's left, +x): a side part there, its offset a guess
        side = "left" if float(p["sweep"]) < 0 else "right"
        g["parting"] = {"side": side, "offset": 0.025}
        put("groom.parting", g["parting"], f"INFERRED from the front's sweep {p['sweep']} (the hair falls away from a part on "
                                           f"the other side); no part line seen: place it by eye")
    else:
        g["parting"] = {"side": "none"}
        put("groom.parting", g["parting"], "INFERRED: no part seen in the front-ish views (combed through)")
    # grey by region: the light share above the least grey region's (that is look.grey_amount)
    ls = s.get("light_share_by_region") or {}
    c = s.get("colour") or {}
    look = {}
    if c:
        from .hair_groom import grey_age
        cr = c.get("chroma_ratio")
        young = (grey_age(spec) <= 0.2) if spec else False  # (under ~34 the light pixels are LIT hair, not grey hairs)
        lit_not_grey = cr is not None and cr >= hair_read.GREY_CHROMA
        ga_ok = not young and not lit_not_grey
        ga = 0.0
        if not ga_ok:
            g["grey"] = {"temples": 0.0, "sideburns": 0.0}
            look["grey_amount"] = put("look.grey_amount", 0.0, (
                f"MEASURED: the light pixels are LIT hair, not grey: as chromatic as the dark ones or more (ratio {cr}; "
                f"grey hair < {hair_read.GREY_CHROMA})" if lit_not_grey else "the model's age: no grey under ~34") + "; groom.grey 0")
        else:
            base = min(ls.values()) if ls else c.get("light_share", 0.0)
            ga = round(float(np.clip(base, 0.0, 0.9)), 3)
            look["grey_amount"] = put("look.grey_amount", ga, f"MEASURED: the light-strand share of the least grey region "
                                                             f"(view {s['colour_view']})")
            gr = {k: round(float(np.clip(v - base, 0, 1)) / max(1 - base, 0.1), 3) for k, v in ls.items()
                  if k in ("front", "top", "sides", "back", "nape")}  # (groom.grey's regions: no crown)
            if gr:
                g["grey"] = {**gr, "temples": round(max(gr.get("sides", 0.0), gr.get("front", 0.0)), 3), "sideburns": round(gr.get("sides", 0.0), 3)}
                put("groom.grey", g["grey"], "MEASURED: light share by region above grey_amount (temples / sideburns = the sides')")
        if not ga_ok and c.get("lit"):  # no grey: the two modes are shadow and lit hair; `seen` is the LIT hair's
            look["seen"] = put("look.seen", c["lit"], f"MEASURED: the lit hair (the lighter mode), view {s['colour_view']}")
        elif c.get("seen"):
            look["seen"] = put("look.seen", c["seen"], f"MEASURED: the lit half of the pigmented hair, view {s['colour_view']}")
        gs = c.get("grey_strand") or c.get("grey")
        if gs and ga_ok:
            look["grey"] = put("look.grey", gs, f"MEASURED: the lightest quarter of the light / grey pixels (a grey strand: "
                                                f"the pixels' median mixes it with dark hair), view {s['colour_view']}")
        va = (c.get("bands") or {}).get("variation") or {}
        if va.get("strand_sd") is not None:
            look["variation"] = put("look.variation", round(float(np.clip(0.4 * va["strand_sd"] / 4.2, 0.2, 0.8)), 2),
                                    f"strand_sd {va['strand_sd']} (Tess calibration: 4.2 at 0.4)")
        look["sun"] = put("look.sun", 0.0 if short else 0.2, "INFERRED: a short cut has no old lengths" if short else "default")
        rib = (va.get("ribbons") or {}).get("share") if va else None
        if long_ and not ga_ok and rib is not None:
            look["highlights"] = put("look.highlights", round(float(np.clip(6.0 * rib, 0.0, 0.8)), 2),
                                     f"MEASURED light ribbons {round(100 * rib)} % of the hair (Tess: 9-10 % at 0.7)")
        else:
            look["highlights"] = put("look.highlights", 0.0, "light ribbons on grey hair are the grey strands (not sun streaks)"
                                     if ga > 0.15 else "default")
        if ga > 0.15 or (c.get("dark_L") or 0) > 40:
            look["scalp_tint"] = put("look.scalp_tint", 0.15, "grey / fair hair: at 0.5 the receded temple corners of a grey crop read as dark patches (hair-heads r9)")
    st = copy.deepcopy(hair_read.CROP["strands"]) if short else (st_long if long_ else {})
    h_ = s.get("halo_all")
    if h_ is not None:
        st["halo"] = put("strands.halo", round(float(np.clip(1.2 * h_, 0.05, 0.6)), 2), f"MEASURED halo density {h_}")
    w_ = s.get("wisps_per_10cm")
    if w_ is not None:
        st["flyaway"] = put("strands.flyaway", round(float(np.clip(0.01 + 0.01 * w_, 0.0, 0.1)), 3), f"MEASURED {w_} wisps / 10 cm")
    sm = (s.get("hairline_softness_mm") or {}).get("front")
    if sm:
        st["soft"] = put("strands.soft", round(float(np.clip(sm / 1000.0, 0.002, 0.012)), 4),
                         f"MEASURED hairline softness {sm} mm (20->80 %)")
    if s.get("baby_per_cm") is not None:
        st["baby"] = put("strands.baby", round(float(np.clip(0.2 + 0.3 * s["baby_per_cm"], 0.0, 1.0)), 2),
                         f"MEASURED {s['baby_per_cm']} baby hairs / cm")
    hairp = {"style": "strands", "groom": g, "strands": st, "look": look}
    return {"hair": hairp, "rows": rows, "short": short, "text": start_text(rows)}


def start_text(rows) -> str:
    L = ["START (set from the read):"]
    for k, v, why in rows:
        L.append(f"  {k} = {json.dumps(v) if not isinstance(v, str) else v}   <- {why}")
    return "\n".join(L)


def apply(name: str, out: str | None = None, authority: int | None = None, seed: int = 0, log=print) -> dict:
    """read + start + groom: the hair patch is saved (and grown) onto `out` (a copy of `name` without hair, its
    human_refs carried) or onto `name`. Returns {"read", "start", "text"}."""
    import shutil
    from . import hair_spec
    r = read(name, authority=authority, log=log)
    spec = store.load(name)
    s = start(r, spec)
    dst = out or name
    if out:
        d = store.HOME / out
        d.mkdir(parents=True, exist_ok=True)
        sp = copy.deepcopy(spec)
        sp.pop("hair", None)
        (d / "spec.json").write_text(json.dumps(sp, indent=1))
        for f in ("human_refs.json",):
            if (store.HOME / name / f).exists():
                shutil.copy(store.HOME / name / f, d / f)
    sp = store.load(dst)
    h = sp.setdefault("hair", {})
    h["style"] = s["hair"]["style"]
    h["strands"] = hair_spec.merge_patch(h.get("strands") or {}, s["hair"]["strands"])
    h["look"] = hair_spec.merge_patch(h.get("look") or {}, s["hair"]["look"])
    hair_spec.validate(sp)
    store.save(dst, sp, "hair_from_reference: style / strands / look")
    gr = hair_spec.groom(dst, replace=True, note="hair_from_reference", patch={**s["hair"]["groom"], "seed": int(seed)})
    text = r["text"] + "\n" + s["text"] + f"\nsaved {dst} v{gr['version']}: grew " + ", ".join(f"{t} {n}" for t, n in gr["grown"].items())
    return {"read": r, "start": s, "text": text}
