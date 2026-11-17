"""garment_cut's flat pattern, gate, look and record (cut.py has the step and its declaration): reads step 5's marked
toile (it must be ready) and steps 0-3; writes the flat pattern in draft_pattern's block form and step 6 (FLAT)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .cut import CutRefused, flatten_piece, name_runs, other_label, runs_of


def _ends(idx, n):
    return idx[0], idx[len(idx) // 2], (idx[-1] + 1) % n


def block(pcs: dict, edges: dict, s1: dict, absent: dict, ease: dict, folds=()) -> tuple[dict, dict, list]:
    """(B: cloth.pieces' block, decl, truing rows' facts) from the flattened pieces and their named edges; folds: the
    flat pattern's folds (a flap's roll line, a collar's roll) as the flat gate reads them."""
    out, arcs, fwd3 = {}, {}, {}
    for p, f in pcs.items():
        n = len(f["loop"])
        P = f["U"][f["lp"]]
        names, arcs[p], fwd3[p] = dict(f.get("names") or {}), {}, {}
        for e, idx in edges[p].items():
            a, m, b = _ends(idx, n)
            names[f"{e}.a"], names[f"{e}.m"], names[f"{e}.b"] = a, m, b
            arcs[p][e] = f"{e}.a>{e}.m>{e}.b" if m not in (a, b) else f"{e}.a>{e}.b"
            fwd3[p][e] = (f["V"][f["lp"][a]], f["V"][f["lp"][b]])
        out[p] = {"name": p, "P": P, "names": names, "marks": {}, "lines": {}, "grain": float(f.get("grain", 90.0)), "wrap": {"to": "torso"},
                  "cut": 1, "P3": f["V"][f["lp"]]}

    seams, dseams, notes, done = [], [], {}, set()

    def add(pa, ea, pb, eb):
        (a0, a1), (b0, b1) = fwd3[pa][ea], fwd3[pb][eb]
        if np.linalg.norm(a0 - b0) + np.linalg.norm(a1 - b1) > np.linalg.norm(a0 - b1) + np.linalg.norm(a1 - b0):
            nb = out[pb]["names"]  # (b's ends renamed to run as a's: the via keeps the arc on the same outline run)
            nb[f"{eb}.a"], nb[f"{eb}.b"] = nb[f"{eb}.b"], nb[f"{eb}.a"]
            fwd3[pb][eb] = (b1, b0)
        S = [f"{pa}:{arcs[pa][ea]}", f"{pb}:{arcs[pb][eb]}"]
        seams.append(S)
        d = {"a": f"{pa}:{ea}", "b": f"{pb}:{eb}"}
        e_ = ease.get(d["a"]) or ease.get(d["b"])
        if e_:
            d["ease"] = e_
            notes[json.dumps(S)] = {"ease": [float(x) for x in e_], "why": "declared at step 6"}
        dseams.append(d)
        done.update({(pa, ea), (pb, eb)})
    for s in s1.get("seams") or []:
        pa, ea = s["a"].split(":", 1)
        pb, eb = s["b"].split(":", 1)
        if ea in arcs.get(pa, {}) and eb in arcs.get(pb, {}):
            add(pa, ea, pb, eb)
    for p in pcs:
        for e in arcs[p]:
            if (p, e) in done or not e.startswith("to_"):
                continue
            q = e[3:].split("_")[0] if e[3:] not in pcs else e[3:]
            q = next((x for x in pcs if e[3:].startswith(x)), q)
            cands = [f for f in arcs.get(q, {}) if f.startswith(f"to_{p}") and (q, f) not in done]
            if cands:
                mid = sum(fwd3[p][e]) / 2
                f = min(cands, key=lambda f: np.linalg.norm(sum(fwd3[q][f]) / 2 - mid))
                add(p, e, q, f)
    closures = []
    for nm, c in (s1.get("closures") or {}).items():
        ps, es = c.get("pieces") or [], c.get("edges") or []
        if len(ps) == 2 and all(p in pcs for p in ps) and len(es) == 2:
            eo, eu = es[0].split(":", 1)[1], es[1].split(":", 1)[1]
            if eo in arcs[ps[0]] and eu in arcs[ps[1]]:
                closures.append({"name": nm, "over": ps[0], "under": ps[1], "edge": {"over": arcs[ps[0]][eo], "under": arcs[ps[1]][eu]}})
    decl = {"pieces": {p: {"part": p} for p in pcs}, "edges": arcs, "seams": dseams, "omit": dict(absent),
            "closures": closures, "stiff": [], "folds": list(folds)}
    trued = true_seams(out, seams, notes)
    B = {"pieces": out, "seams": seams, "stitches": [], "interfaced": [], "vents": [], "folds": list(folds), "closures": closures,
         "seam_notes": notes, "edge_arcs": arcs, "decl": decl, "darts": [], "draft": {"design": "toile"}, "trued": trued,
         "landing": {p: f["landing"] for p, f in pcs.items() if f.get("landing")}}
    return B, decl


def true_seams(out: dict, seams: list, notes: dict, passes: int = 3) -> list:
    """Each plain seam trued: both sides drawn to their mean length, each run scaled about its start (the draper blends
    the seam's end); a seam with a declared ease is left as cut. [{seam, before_pct, after_pct}]."""
    from . import pattern

    def side(e):
        p, arc = e.split(":", 1)
        ix = pattern.arc_indices(out[p], arc)
        return p, ix, pattern.length(out[p]["P"][ix])
    rep = {}
    for _ in range(passes):
        for S in seams:
            if json.dumps(S) in notes:
                continue
            sd = [side(e) for e in S]
            tgt = 0.5 * (sd[0][2] + sd[1][2])
            rep.setdefault(" || ".join(S), {"seam": " || ".join(S), "before_pct": round((sd[0][2] / sd[1][2] - 1) * 100, 2)})
            for p, ix, ln in sd:
                P = out[p]["P"]
                P[ix] = P[ix[0]] + (tgt / ln) * (P[ix] - P[ix[0]])
    for S in seams:
        if " || ".join(S) in rep:
            a, b = side(S[0]), side(S[1])
            rep[" || ".join(S)]["after_pct"] = round((a[2] / b[2] - 1) * 100, 2)
    return list(rep.values())


def gate_rows(B, decl, rd, fit) -> list:
    """Today's flat gate (draft_own_gate.gate) on the flat pattern; a row family that can't read it is a FAIL naming why."""
    from . import draft_own_gate
    try:
        return draft_own_gate.gate(B, decl, rd["1"], None, rd["3"], fit, step2=rd.get("2"), look=None)
    except Exception as e:  # noqa: BLE001 (the flat gate's own crash on this form, named: R3b's fix list)
        import traceback
        tb = traceback.extract_tb(e.__traceback__)[-1]
        return [{"id": "flat_gate", "status": "FAIL", "value": f"{type(e).__name__}: {e}"[:300],
                 "target": "today's flat gate runs on the flat pattern", "why": f"at {Path(tb.filename).name}:{tb.lineno}",
                 "back_to": "6"}]


PAL_BG = (225, 230, 240)


def look(pcs, path, S_=500):
    from PIL import Image, ImageDraw
    tiles = []
    for p, f in pcs.items():
        if p.endswith(".R"):
            continue
        U, Fp, bad = f["U"], f["F"], f["bad"]
        lo, hi = np.nanmin(U, 0), np.nanmax(U, 0)
        im = Image.new("RGB", (int((hi - lo)[0] * S_) + 40, int((hi - lo)[1] * S_) + 60), (255, 255, 255))
        dr = ImageDraw.Draw(im)
        H = im.height - 20
        xy = lambda q: (20 + (q[0] - lo[0]) * S_, H - (q[1] - lo[1]) * S_)
        for t, tri in enumerate(Fp):
            c = bad[t]
            col = (255, int(255 * max(0, 1 - c / 0.06)), int(255 * max(0, 1 - c / 0.06))) if c > 0.005 else PAL_BG
            dr.polygon([xy(U[i]) for i in tri], fill=col)
        P = U[f["lp"]]
        dr.line([xy(q) for q in np.r_[P, P[:1]]], fill=(0, 0, 0), width=2)
        dr.text((6, 4), f"{p}: strain mean {f['rep']['strain_mean_pct']} % (red = 6 %)", fill=(0, 0, 0))
        tiles.append(im)
    hh = max(t.height for t in tiles)
    out = Image.new("RGB", (sum(t.width + 10 for t in tiles), hh), (255, 255, 255))
    x = 0
    for t in tiles:
        out.paste(t, (x, hh - t.height))
        x += t.width + 10
    out.save(path)
    return path


def look3d(pcs, ref, path):
    """The cut pieces where they lie (the toile's, a flap turned, the collar as draped; layers hidden under their hosts),
    4 views and the neck close, beside the reference."""
    from .mark_tool import PAL
    from .toile_geom import render, sheet
    shown = [(f["V"], f["F"], np.tile(PAL[k % len(PAL)], (len(f["F"]), 1))) for k, (p, f) in enumerate(pcs.items())
             if "host" not in f["rep"]]
    V = np.concatenate([m[0] for m in shown])
    lo, hi = V.min(0), V.max(0)
    box, sbox = ((lo[0] - 0.03, hi[0] + 0.03), (lo[2] - 0.04, hi[2] + 0.04)), ((lo[1] - 0.12, hi[1] + 0.12), (lo[2] - 0.04, hi[2] + 0.04))
    nb = ((-0.2, 0.2), (hi[2] - 0.32, hi[2] + 0.04))
    nsb = ((lo[1] - 0.05, hi[1] + 0.05), nb[1])
    tiles = [render(shown, view=v, box=box if v in ("front", "back") else sbox) for v in ("front", "left", "back")]
    tiles += [render(shown, view=v, box=nb if v in ("front", "back") else nsb, mpp=0.0008) for v in ("front", "left", "back")]
    sheet(tiles, ref, labels=["reference", "front", "left", "back", "neck front", "neck left", "neck back"]).save(path)
    return path


def run(name: str, garment: str, declarations: dict, log=lambda *_: None):
    """(look sheet or None, text)."""
    from . import garment_record as gr
    from .mark import RUN_DIRS  # noqa: F401 (the runs' directions, step 5's)
    if isinstance(declarations, str):
        declarations = json.loads(declarations)
    declarations = declarations or {}
    rec = gr.load(name, garment)
    st = gr.states(rec)
    if not st["5"]["ready"]:
        return None, f"{name}:{garment} step 6 (cut): step 5 (mark) is not ready ({st['5']['status']})\nnext: garment_mark"
    try:
        rd = gr.reads(name, garment, "6")
    except gr.OrderRefused as e:
        return None, f"{name}:{garment} step 6 (cut): {e}\nnext: finish the step named"
    s5 = rec["steps"]["5"]["output"]
    fit = (rec["steps"]["0"].get("output") or {}).get("fit") or {}
    m5 = (s5.get("declarations") or {})
    bad = [f"free: {p!r} is not a cut piece" for p in declarations.get("free") or {}
           if p not in s5["pieces"] and p[:-2] + ".L" not in s5["pieces"]]
    bad += [f"free.{p}.{e}: {c!r}: one of top, bottom, side" for p, mp in (declarations.get("free") or {}).items()
            for e, c in mp.items() for c_ in ([c] if isinstance(c, str) else c) if c_ not in ("top", "bottom", "side")]
    if bad:
        return None, f"{name}:{garment} step 6 (cut) refused: " + "; ".join(bad) + "\nnext: fix what is named, garment_cut again"
    Z = np.load(s5["mark"])
    V, F, lab, names = Z["V"], Z["F"], Z["lab"], [str(x) for x in Z["names"]]
    pcs, edges, why = {}, {}, []
    from .cut_ease import CapEase
    ce = CapEase(rec["steps"]["4"].get("output") or {})
    for p, nm in enumerate(names):
        try:
            gd = declarations.get("grain") or {}
            f = flatten_piece(V, F, lab, p, nm, ce, float(gd.get(nm, gd.get(nm[:-2] + ".L" if nm.endswith(".R") else nm, 90.0))))
            f["grain"] = f["rep"]["grain_deg"]
        except CutRefused as e:
            why.append(str(e))
            continue
        across = other_label(F, lab, p)
        fd = declarations.get("free") or {}
        rs = runs_of(f["loop"], V, across, names, p, fd.get(nm) or fd.get(nm[:-2] + ".L" if nm.endswith(".R") else nm))
        edges[nm], b = name_runs(nm, rs, V, f["loop"], rd["1"], m5.get("absent") or {}, m5.get("runs") or {},
                                 declarations.get("free") or {})
        why += b
        pcs[nm] = f
        log(f"{nm}: {f['rep']}; edges {sorted(edges[nm])}")
    from .cut_made import made
    folds, made_rows = made(pcs, edges, declarations, rd["1"], rec["steps"]["4"]["output"], log)
    from .cut_made import _mir
    from .cut_tapes import closure_marks, folds as planned, piece_tapes, places
    hems, b = planned(declarations, edges)
    folds, why = folds + hems, why + b
    absent = {p: w for p, w in (m5.get("absent") or {}).items() if p not in pcs}
    ease = dict(declarations.get("ease") or {})
    ease.update({_mir(k): v for k, v in ease.items() if _mir(k) not in ease})  # (a ".L" seam's ease serves ".R")
    B, decl = block(pcs, edges, rd["1"], absent, ease, folds)
    decl["tapes"] = piece_tapes(pcs, rd["3"], edges)  # (each piece lies where it was cut from: the tapes there are its own)
    from .draft_girths import CROSSED
    B["girth_ring"] = CROSSED  # (a girth's ring: the pieces its loop crosses, draft_girths)
    for p, w in places(pcs, rd["3"]).items():
        B["pieces"][p]["wrap"] = w
    from .cut_ease import step4_numbers
    why += closure_marks(B, pcs, step4_numbers(rec["steps"]["4"].get("output") or {}).get("opening") or {})
    rows = [{"id": "cut_flatten", "status": "FAIL" if why else "PASS", "value": f"{len(pcs)} pieces cut and flattened, edges named",
             "target": "every marked piece one disc, every edge named", "why": "; ".join(why[:8]), "back_to": "6"},
            *made_rows,
            {"id": "strain", "status": "INFO", "value": "; ".join(f"{p} {f['rep']['strain_mean_pct']} % mean, "
                                                                 f"{f['rep']['area_over_2pct']} % of area > 2 %" for p, f in pcs.items()),
             "target": "info: where the flat isn't the toile (a dart or ease wanted): cut.json per piece"}]
    tr = B["trued"]
    rows.append({"id": "trued", "status": "INFO", "value": f"{sum(abs(t['before_pct']) > 1 for t in tr)} of {len(tr)} plain "
                 f"seams off > 1 % as flattened; worst {max((abs(t['before_pct']) for t in tr), default=0):.1f} %, after "
                 f"truing {max((abs(t.get('after_pct', 0)) for t in tr), default=0):.2f} %",
                 "target": "info: each plain seam's sides drawn to one length (the flatten's own mismatch: cut.json)"})
    rows += gate_rows(B, decl, rd, fit)
    v = "FAIL" if any(r["status"] == "FAIL" for r in rows) else "PASS"
    d = gr.look_dir(name, garment) / "cut"
    d.mkdir(parents=True, exist_ok=True)
    np.savez(d / "flat.npz", **{f"{p}:{k}": f[k] for p, f in pcs.items() for k in ("U", "F", "V", "bad", "lp")})
    js = lambda o: o.tolist() if isinstance(o, np.ndarray) else float(o) if isinstance(o, np.floating) else int(o) if isinstance(o, np.integer) else str(o)
    (d / "pattern.json").write_text(json.dumps(B, default=js))
    seams = next((r["detail"] for r in rows if r["id"] == "seams" and isinstance(r.get("detail"), list)), [])
    info = {"pieces": {p: f["rep"] for p, f in pcs.items()}, "edges": {p: sorted(e) for p, e in edges.items()},
            "trued": B["trued"], "seams": [{k: r.get(k) for k in ("a", "b", "len_a_mm", "len_b_mm", "ease", "ok")} for r in seams]}
    (d / "cut.json").write_text(json.dumps(info, indent=1, default=js))
    lp = look(pcs, d / "flat_sheet.png")
    ref = ((rec["steps"]["0"].get("output") or {}).get("views") or [{}])[0].get("image")
    l3 = look3d(pcs, ref if ref and Path(ref).exists() else None, d / "cut_3d.png")
    out = {"flat": str(d / "flat.npz"), "pattern": str(d / "pattern.json"), "numbers": str(d / "cut.json"),
           "pieces": list(pcs), "seams": len(B["seams"]), "omit": decl["omit"], "declarations": declarations}
    msg = gr._try(gr.write, name, garment, "6", "done" if v == "PASS" else "failed", output=out,
                  gate={"verdict": v, "rows": json.loads(json.dumps(rows, default=js))}, look=[str(lp), str(l3)], back_to="6",
                  by="garment_cut")
    lines = [f"{name}:{garment} step 6 CUT AND FLATTEN: {v}"]
    from .draft_own_tool import row_lines
    lines += [ln for r in rows for ln in row_lines(r)]
    lines.append(f"  look: {lp} (flat pieces, strain red at 6 %; every number is in this text)")
    lines.append(f"  look: {l3} (the pieces where they lie, the collar as cut from the toile, beside the reference)")
    if msg:
        lines.append(f"  record: {msg}")
    lines.append("next: " + ("compare the flat pieces' shapes with the reference; then the details (step 7)" if v == "PASS"
                             else "each FAIL row says what: a free edge's name (free), a seam's ease (ease), or a mark "
                                  "(back to step 5); garment_cut again"))
    return lp, "\n".join(lines)
