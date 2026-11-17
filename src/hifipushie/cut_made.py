"""garment_cut's pieces made at step 6 beyond the marked toile's: turned flaps unfolded onto their pieces (cut_flap.py),
layers traced off a host's flat (cut_layers.py), the collar cut from the toile and its fall unfolded about the roll
(cut_collar.py), in that order (a layer traces its host with its flap on; a collar names its neck runs by the edges it
lies on, the flap's top among them). Each declaration's ".L" entry serves its ".R" mirror. Rows: flaps, layers, collar (what each made, its numbers,
what was refused by name: back to step 6)."""
from __future__ import annotations

import re

import numpy as np

SEAM_MM = 3.0  # the collar's flat neck edge on a garment edge vs that edge's flat length (truing takes the rest)


def _mir(x):
    return re.sub(r"\.L(?=$|:)", ".R", x) if isinstance(x, str) else x


def _both(dd: dict) -> dict:
    out = dict(dd)
    for k, v in dd.items():
        if k.endswith(".L") and _mir(k) not in dd:
            out[_mir(k)] = {kk: ([_mir(a) if isinstance(a, str) else [_mir(b) for b in a] if isinstance(a, list) else a
                                  for a in vv] if kk == "line" else _mir(vv)) for kk, vv in v.items()}
    return out


def made(pcs: dict, edges: dict, decl: dict, s1: dict, out4: dict, log=lambda *_: None):
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
    if decl.get("collar"):
        from .cut_collar import split_gorge
        for m in split_gorge(pcs, edges, decl["collar"], out4):
            log(m)
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
            c_pcs, c_edges, c_folds, rep, bad = build(pcs, edges, d, s1, layers, out4)
        except CollarRefused as e:
            rows.append({"id": "collar", "status": "FAIL", "value": "not cut", "why": str(e), "back_to": "6",
                         "target": "the toile's collar cut and its fall unfolded about the roll line"})
            return folds, rows
        pcs.update(c_pcs)
        edges.update(c_edges)
        folds += c_folds
        log(f"collar: {rep}")
        fails = list(bad)
        sm = rep["seams"]
        off = {g: v["collar_mm"] - v["garment_mm"] for g, v in sm.items()}
        fails += [f"collar: its neck edge on {g} is {v['collar_mm']} mm flat, {g} {v['garment_mm']} mm: off {off[g]:+.1f} mm "
                  f"(> {SEAM_MM:g}; on the toile {v['collar_3d_mm']} / {v['garment_3d_mm']} mm: never stretched in the flat "
                  "(C504): back to step 4 where they disagree in 3D, else it is the flatten's strain)"
                  for g, v in sm.items() if abs(off[g]) > SEAM_MM]
        if rep["outer_over_neck"] <= 1.0:
            fails.append(f"collar: the flat outer edge is no longer than its neck edge (x{rep['outer_over_neck']}): a band, "
                         "not a turned collar (back to step 4: the fall must lie out over the shoulders)")
        t4 = rep["toile"]
        rows.append({"id": "collar", "status": "FAIL" if fails else "PASS", "back_to": "6",
                     "value": (f"{', '.join(c_pcs)}: cut from the toile's collar (stand {t4['stand_mm']} / fall "
                               f"{t4['fall_mm']} mm, lands {t4['lands_below_seam_cb_mm']} mm below the neck seam at CB), the "
                               f"fall unfolded about the roll: flat {rep['flat_span_mm'][0]} x {rep['flat_span_mm'][1]} mm, "
                               f"neck {rep['neck_flat_mm']} / roll {rep['roll_flat_mm']} / outer {rep['outer_flat_mm']} mm "
                               f"(outer = {rep['outer_over_neck']} x neck; outer on the toile {rep['outer_3d_mm']}), neck bow "
                               f"{rep['neck_bow_mm']} mm, strain {rep['strain_mean_pct']} % mean; seams: "
                               + "; ".join(f"{g} {v['collar_mm']} / {v['garment_mm']} mm (3D {v['collar_3d_mm']} / "
                                           f"{v['garment_3d_mm']})" for g, v in sm.items())),
                     "target": f"cut from the toile, unfolded (outer longer than neck), each neck seam within {SEAM_MM:g} mm "
                               "of its garment edge", "why": "; ".join(fails[:6])})
    return folds, rows
