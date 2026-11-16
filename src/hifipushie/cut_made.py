"""garment_cut's pieces made at step 6 beyond the marked toile's: turned flaps unfolded onto their pieces (cut_flap.py),
layers traced off a host's flat (cut_layers.py), the collar drafted flat and fitted round the toile's neck
(cut_collar.py), in that order (a layer traces its host with its flap on; a collar reads the neck edges with the flap's
top). Each declaration's ".L" entry serves its ".R" mirror. Rows: flaps, layers, collar (what each made, its numbers,
what was refused by name: back to step 6)."""
from __future__ import annotations

import re

import numpy as np

LEN_PCT, LEN_MM = 1.0, 0.5  # the fitted collar's worst link (of those over 5 mm) off its flat length: both over = FAIL


def _mir(x):
    return re.sub(r"\.L(?=$|:)", ".R", x) if isinstance(x, str) else x


def _both(dd: dict) -> dict:
    out = dict(dd)
    for k, v in dd.items():
        if k.endswith(".L") and _mir(k) not in dd:
            out[_mir(k)] = {kk: ([_mir(a) if isinstance(a, str) else [_mir(b) for b in a] if isinstance(a, list) else a
                                  for a in vv] if kk == "line" else _mir(vv)) for kk, vv in v.items()}
    return out


def made(pcs: dict, edges: dict, decl: dict, s1: dict, out4: dict, toile, log=lambda *_: None):
    """(folds, rows); pcs / edges gain the made pieces (module doc)."""
    from .cut_collar import CollarRefused, build
    from .cut_flap import FlapRefused, unfold
    from .cut_layers import LayerRefused, cut_layer
    folds, rows = [], []
    flaps = _both(decl.get("flaps") or {})
    if flaps:
        Z = np.load(out4["toile"])
        reps, why = [], []
        for part, d in flaps.items():
            onto = d.get("onto")
            if f"{part}:V" not in Z.files or onto not in pcs:
                why.append(f"flaps.{part}: no toile part {part!r} or no cut piece {onto!r} (step 4's parts: "
                           f"{sorted({k.split(':')[0] for k in Z.files})})")
                continue
            try:
                g, e2, names, rep, bad = unfold(pcs[onto], edges[onto], Z[f"{part}:V"].astype(float),
                                                Z[f"{part}:F"].astype(int), d.get("edges") or {}, d.get("fold", "roll"), part)
            except FlapRefused as e:
                why.append(str(e))
                continue
            g["names"] = dict(pcs[onto].get("names") or {}, **names)
            pcs[onto], edges[onto] = g, e2
            folds.append({"name": d.get("fold", "roll"), "piece": onto, "line": sorted(names), "kind": "roll"})
            reps.append(rep)
            why += bad
            log(f"flap {part}: {rep}; {onto} edges {sorted(e2)}")
        rows.append({"id": "flaps", "status": "FAIL" if why else "PASS", "back_to": "6",
                     "value": "; ".join(f"{r['flap']} onto {r['onto']}: hinge {r['hinge_mean_mm']} mm mean "
                                        f"({r['hinge_max_mm']} max), roll {r['roll_flat_mm']['piece']} / "
                                        f"{r['roll_flat_mm']['flap']} mm, across {r['lands_across_roll']}" for r in reps),
                     "target": "each turned flap unfolded about its roll edge onto its piece, landing across the roll",
                     "why": "; ".join(why[:6])})
    layers = _both(decl.get("layers") or {})
    if layers:
        reps, why = [], []
        for lay, d in layers.items():
            h = d.get("host")
            if h not in pcs:
                why.append(f"layers.{lay}: host {h!r} is not a cut piece")
                continue
            try:
                g, e2, rep, bad = cut_layer(pcs[h], edges[h], d, lay)
            except LayerRefused as e:
                why.append(str(e))
                continue
            pcs[lay], edges[lay] = g, e2
            reps.append((lay, rep))
            why += bad
            log(f"layer {lay}: {rep}")
        rows.append({"id": "layers", "status": "FAIL" if why else "PASS", "back_to": "6",
                     "value": "; ".join(f"{n} off {r['host']}: {r['area_cm2']} cm2, line {r['line_mm']} mm, edges "
                                        f"{', '.join(r['edges'])}" for n, r in reps),
                     "target": "each layer traced off its host's flat by its declared line", "why": "; ".join(why[:6])})
    if decl.get("collar"):
        d = decl["collar"]
        try:
            c_pcs, c_edges, c_folds, rep, bad = build(pcs, edges, d, s1, layers, toile)
        except CollarRefused as e:
            rows.append({"id": "collar", "status": "FAIL", "value": "not drafted", "why": str(e), "back_to": "6",
                         "target": "the collar drafted flat and fitted round the toile's neck"})
            return folds, rows
        pcs.update(c_pcs)
        edges.update(c_edges)
        folds += c_folds
        log(f"collar: {rep}")
        L = rep["lengths"]
        lw, lmm = L["worst_pct_5mm"], L["worst_mm"]
        fails = list(bad)
        if lw > LEN_PCT and lmm > LEN_MM:
            fails.append(f"the fitted collar holds its flat lengths to {lw:.2f} % / {lmm:.1f} mm (worst link), > "
                         f"{LEN_PCT} % and {LEN_MM} mm: it can't lie round this neck as drafted")
        rows.append({"id": "collar", "status": "FAIL" if fails else "PASS", "back_to": "6",
                     "value": (f"{', '.join(c_pcs)}: neck {rep['neck_mm']['half']} mm per half (front "
                               f"{rep['neck_mm']['front']}, back {rep['neck_mm']['back']}), outer {rep['outer_half_mm']} (the landing rule's "
                               f"{rep['outer_rule_half_mm']}, spread x {rep['spread_rounds']} on the toile) "
                               f"= {rep['outer_over_neck']} x neck, flat {rep['flat_span_mm'][0]} x {rep['flat_span_mm'][1]} "
                               f"mm, neck bow {rep['neck_bow_mm']} mm; fitted: lengths worst {lw} % ({lmm} mm), outer 3D "
                               f"{rep['outer_3d_mm']} / flat {rep['outer_flat_mm']} mm, lands {rep['lands_below_neck_cb_mm']}"
                               f" mm below the neck seam at CB (d {rep['d_mm']}; its landing line on the toile behind the shoulder x"
                               f"{rep['laid_over_flat_back']} the flat outer), fall clear of the toile >= "
                               f"{rep['fall_clear_min_mm']} mm"),
                     "target": "drafted flat (outer longer than neck by the fall's landing), fitted with every flat "
                               "length held", "why": "; ".join(fails[:6])})
    return folds, rows
