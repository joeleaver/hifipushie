"""The staged clothing workflow: how a pattern maker / Marvelous Designer artist works, as checkable stages.

  1 design        the design sheet (garment_design): kind, fabric with physical numbers, fit, every construction
                  choice (collar, cuff, placket, closure, hem, ...), defaults filled from garment_kb.json; a choice the
                  draft source can't make, or one that needs another (a barrel cuff needs a sleeve placket), fails.
  2 pattern       the draft laid flat and LOOKED at (pattern_sheet: names, roles, grain, notches, seams numbered on both
                  sides, folds, interfacing); checks: every sheet choice evidenced in the pieces and seam table, every
                  seam's ease in its band (cloth_check; the sleeve cap by kind), notches, ease vs the body per girth in
                  the fit's band, every piece sewn to something, the details' dimensions.
  3 construction  the making plan: sewing order, layers and which side laps, fold/press lines with angles, interfacing
                  and what rests "as made", fabric and interfacing stiffness, the sim's stage schedule; checks: nothing
                  that must roll is frozen as made, made pieces are the ones the knowledge base says.
  4 place         the pieces arranged round the body (or dressed for the hanger), before any sim: crossings at the
                  start, how far the start was pushed off the body, start stretch past the solver's limit, layer gaps.
  5 sim           after dress (draft first, then final): the report's verdict plus the numeric targets of
                  garment_kb.json (layer gaps, collar cover and points, hem level, waistband height, sleeves hung,
                  crest radius, strain), judged at the quality they belong to.
Each stage returns {"stage", "fail", "warn", "info", "images"}; `text` prints failures first. `gate` is what `dress`
runs before it starts a sim (stages 1-3): hard failures stop it unless forced.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import cloth, cloth_check, garment_design

STAGES = ("design", "pattern", "construction", "place", "sim")


def _out(stage: str) -> dict:
    return {"stage": stage, "fail": [], "warn": [], "info": [], "images": []}


class Ctx:
    """What every stage reads: the spec, the garment (raw and compiled), the body and its tape, the sheet."""

    def __init__(self, name: str, gname: str, spec: dict | None = None):
        from . import store
        self.name, self.gname = name, gname
        self.spec = spec or store.load(name)
        gs = self.spec.get("cloth") or {}
        if gname not in gs:
            raise cloth.ClothError(f"no garment {gname!r} (have {', '.join(gs) or 'none'})")
        self.g = gs[gname]
        self.gx = cloth._garment_for_sim(self.g)
        self.sheet = self.g.get("design")
        self.res = garment_design.resolve(self.sheet) if self.sheet else None
        K = garment_design.kb()
        if self.res:
            self.kind = self.res["kind"]
        else:
            fr = (self.gx.get("pattern") or {}).get("from")
            self.kind = (K["designs"].get(fr) or {}).get("kind")
        self.kind_kb = K["kinds"].get(self.kind, {}) if self.kind else {}
        self._body = self._Bp = None

    @property
    def body(self) -> "cloth.Body":
        if self._body is None:
            self._body = cloth.Body(cloth.model_body(self.name, self.spec, self.g))
        return self._body

    @property
    def meas(self) -> dict:
        return self.body.m["mm"] if (self.gx.get("pattern") or {}) else {}

    @property
    def Bp(self) -> dict:
        if self._Bp is None:
            self._Bp = cloth.pieces(self.gx, self.meas)
        return self._Bp

    def fabric_class(self) -> str:
        ph = self.res["fabric"]["physical"] if self.res else {}
        if ph.get("stretch") == "knit":
            return "knit"
        gsm = ph.get("gsm") or [0, 0]
        fab = cloth.fabric(self.gx)
        if (gsm and gsm[0] >= 300) or fab.get("name") in ("wool_coating", "denim") or float(fab.get("bending", 0)) >= 0.8:
            return "woven_heavy"
        return "woven_light"


# ---------------------------------------------------------------- 1 design


def stage_design(c: Ctx) -> dict:
    o = _out("design")
    if not c.sheet:
        o["warn"].append("no design sheet: the construction choices (collar, cuff, placket, hem...) aren't stated, so "
                         "nothing checks the pattern makes them. Write one: design_garment(name, garment, design={...})")
        if c.kind:
            o["info"].append(f"kind taken from the design table: {c.kind}")
        return o
    r = c.res
    o["info"] += garment_design.sheet_text(r)
    o["fail"] += r["problems"]
    return o


# ---------------------------------------------------------------- 2 pattern


def _cap_band(c: Ctx):
    cb = c.kind_kb.get("cap_ease")
    return tuple(cb) if cb else None


def seam_rows(c: Ctx) -> list:
    rows = cloth_check.seams(c.Bp, c.kind or "")
    cb = _cap_band(c)
    for r in rows:
        if r["kind"].startswith("cap") and cb:
            r["band"] = cb
            r["kind"] = f"cap_{c.kind}"
            r["ok"] = cb[0] - 1e-9 <= r["ease"] <= cb[1] + 1e-9
    return rows


def stage_pattern(c: Ctx, image: bool = True) -> dict:
    o = _out("pattern")
    Bp = c.Bp
    # every sheet choice evidenced in the pieces and seams
    if c.res:
        for ok, d, ch, txt in garment_design.evidence(c.res, Bp, c.meas):
            (o["info"] if ok else o["fail"]).append(f"{d} {ch}: {txt}")
    # seam table: ease per kind, notches
    rows = seam_rows(c)
    nm_ = lambda s: s if isinstance(s, str) else " + ".join(s)
    for i, r in enumerate(rows):
        line = (f"S{i + 1} {r['kind']} {r['len_a_mm']:.1f} vs {r['len_b_mm']:.1f} mm, ease {r['ease'] * 100:+.1f}% "
                f"(band {r['band'][0] * 100:+.1f}..{r['band'][1] * 100:+.1f}): {nm_(r['a'])} || {nm_(r['b'])}")
        if r["notches_off"]:
            line += "; notches off: " + ", ".join(f"{a}~{b} {d} mm" for a, b, d in r["notches_off"])
        (o["fail"] if (not r["ok"] or r["notches_off"]) else o["info"]).append(line)
    # every piece sewn to something
    sewn = {e.split(":")[0] for s in Bp["seams"] for side in s for e in ([side] if isinstance(side, str) else side)}
    loose = [n for n in Bp["pieces"] if n not in sewn]
    if loose and len(Bp["pieces"]) > 1:
        o["fail"].append(f"pieces sewn to nothing: {', '.join(loose)} (a seam table entry is missing)")
    # ease vs the body, per girth, in the fit's band
    D = garment_design.dims(Bp, c.meas)
    bands = (c.res or {}).get("fit_bands") or next(iter((c.kind_kb.get("fit") or {}).values()), {})
    if c.meas and any(Bp["pieces"][n]["wrap"].get("to", "torso") == "torso" for n in Bp["pieces"]):
        sz = cloth.sizing({"pieces": Bp, "body": c.body})["rows"]
        R = garment_design.roles(Bp)
        for reg, v in sz.items():
            if v["garment_mm"] <= 0:
                continue  # the garment doesn't reach that girth
            ease = v["ease"]
            how = "flat pattern"
            if reg == "waist" and "waistband" in R and "waistband_over_waist" in D:
                ease = D["waistband_over_waist"] / c.meas["waist"]
                how = "waistband closed"
            band = bands.get(reg)
            line = f"ease at {reg}: {ease * 100:+.1f}% ({how}; body {v['body_mm']:.0f} mm)"
            if band:
                line += f", {c.res['fit'] if c.res else 'kind'} band {band[0] * 100:+.0f}..{band[1] * 100:+.0f}%"
                if not band[0] - 0.005 <= ease <= band[1] + 0.005:
                    o["fail"].append(line + (": TOO SMALL" if ease < 0 and c.fabric_class() != "knit" else ": outside the fit"))
                    continue
            elif ease < -0.01 and c.fabric_class() != "knit":
                o["fail"].append(line + ": TOO SMALL (negative ease)")
                continue
            o["info"].append(line)
    if D:
        o["info"].append("dimensions: " + ", ".join(f"{k} {v:.2f}" if "ratio" in k else f"{k} {v:.1f} mm" for k, v in D.items()))
    if (Bp.get("draft") or {}).get("derived_mm"):
        o["info"].append("draft: " + json.dumps(Bp["draft"]["derived_mm"]))
    if image:
        from . import pattern_sheet
        title = f"{c.name}:{c.gname}  " + (f"{c.kind} from {(c.gx.get('pattern') or {}).get('from', 'own pieces')}"
                                           if c.kind else "")
        o["images"].append(("pattern", pattern_sheet.render(Bp, title, seam_rows=rows)))
    return o


# ---------------------------------------------------------------- 3 construction


def _sewing_order(c: Ctx) -> list:
    Bp = c.Bp
    order = c.kind_kb.get("sewing_order") or []
    pcs = Bp["pieces"]
    rank = lambda role: order.index(role) if role in order else len(order)
    steps = []
    for i, (A, B) in enumerate(Bp["seams"]):
        roles = {garment_design.role_of(n, pcs[n]) for s in (A, B)
                 for n in [e.split(":")[0] for e in ([s] if isinstance(s, str) else s)]}
        # torso first (the bodice is sewn alone first in the sim too), then by the kind's order
        tor = all(pcs[e.split(":")[0]]["wrap"].get("to", "torso") == "torso"
                  for s in (A, B) for e in ([s] if isinstance(s, str) else s))
        steps.append(((0 if tor else 1), max(rank(r) for r in roles), i, sorted(roles)))
    steps.sort()
    return steps


def stage_construction(c: Ctx) -> dict:
    o = _out("construction")
    Bp, pcs = c.Bp, c.Bp["pieces"]
    nm_ = lambda s: s if isinstance(s, str) else " + ".join(s)
    o["info"].append("sewing order (torso pieces first: the sim's assembly stage sews them alone):")
    for k, (tor, _, i, roles) in enumerate(_sewing_order(c)):
        A, B = Bp["seams"][i]
        o["info"].append(f"  {k + 1}. S{i + 1} [{' + '.join(roles)}] {nm_(A)} || {nm_(B)}")
    if Bp["stitches"]:
        groups = {}
        for a, b in Bp["stitches"]:
            groups.setdefault((a.split(":")[0], b.split(":")[0]), []).append(1)
        o["info"].append("closures (stitched last, sewn closed before the sim starts): " + ", ".join(
            f"{a}->{b} x{len(v)}" for (a, b), v in groups.items()))
    # layers: which piece lies over which
    outs = {n: float(pcs[n]["wrap"].get("out", 0)) for n in pcs}
    lay = [f"{n} {v * 1000:.0f} mm out" for n, v in outs.items() if v > 0]
    o["info"].append("layers (start offsets; the outer lies over): " + (", ".join(lay) or "none"))
    # folds
    for f in Bp.get("folds") or []:
        try:
            Q = garment_design.fold_polyline(pcs, f)
            L = float(np.sum(np.linalg.norm(np.diff(Q, axis=0), axis=1))) * 1000
            o["info"].append(f"fold {f.get('name', '')} on {f['piece']}: {f.get('kind', 'press')} to {f.get('angle')} deg "
                             f"(180 flat, 0 over onto the face, 360 under), strength {f.get('strength', 1 if f.get('kind', 'press') == 'press' else 0.5)}, "
                             f"{L:.0f} mm long")
        except Exception as e:
            o["fail"].append(f"fold {f}: its line doesn't resolve on the piece: {e}")
    for n, pc in pcs.items():
        if (pc.get("wrap") or {}).get("fold") and not any(f.get("piece") == n for f in Bp.get("folds") or []):
            o["warn"].append(f"{n} is only PLACED folded (wrap.fold {pc['wrap']['fold']}: a U that becomes its rest "
                             "shape); give it a fold line (folds) so the crease has an angle and strength")
    # interfacing and what rests as made
    fab = cloth.fabric(c.gx)
    whole = [e for e in Bp["interfaced"] if isinstance(e, str)]
    bands = [e for e in Bp["interfaced"] if not isinstance(e, str)]
    o["info"].append(f"interfacing (bending x{fab.get('stiff')} over the shell): whole {', '.join(whole) or 'none'}; bands "
                     + (", ".join(f"{e['piece']} near {e['near']} within {e.get('within', 0.02) * 1000:.0f} mm" for e in bands) or "none"))
    o["info"].append(f"rest as made in the solver today (wholly interfaced: they keep their placed shape): {', '.join(whole) or 'none'}")
    # made vs draped: what is constructed finished on the table, and what takes its shape from the body
    md = garment_design.made_or_draped(Bp, c.res, c.sheet)
    folded = {f.get("piece") for f in Bp.get("folds") or []} | {n for n in pcs if (pcs[n].get("wrap") or {}).get("fold")}
    o["info"].append("pieces, made (constructed finished and pressed, never simulated into shape) or draped (loose "
                     "cloth: body, gravity, seams):")
    for n, (how, why) in md.items():
        o["info"].append(f"  {n}: {how} ({why})" + ("; fold line" if n in folded else "")
                         + ("; interfaced" if n in whole else ""))
        if how == "made" and n not in whole:
            o["warn"].append(f"{n} is a made piece but isn't wholly interfaced: the solver will drape it")
        if how == "draped" and n in whole:
            o["fail"].append(f"{n} is draped cloth (it must hang or roll) but is wholly interfaced, so the solver "
                             "rests it as made (frozen as placed): interface a band instead")
    method = c.gx.get("method", "simulate")
    st_ = cloth._state(c.g)
    o["info"].append(f"method: {method} (simulate = sew and simulate everything; settle = made pieces constructed "
                     "finished by geometry, the draped cloth settled lightly from the fitted placement, fine folds "
                     "authored at tension points; full simulation is for states like hung and draped)")
    if method == "settle":
        if isinstance(st_, dict):
            o["warn"].append("method settle on a hung/draped state: those want the full simulation")
        o["warn"].append('method "settle" is the artists\' default path under test (clothsim): the solver side isn\'t '
                         "wired yet, so dress still runs the full simulation")
        for n, (how, _) in md.items():
            if how == "made" and n not in folded and garment_design.role_of(n, pcs[n]) in ("collar_fall", "facing"):
                o["fail"].append(f"{n} is made but has no fold line: it can't be constructed turned without one")
    K = garment_design.kb()
    lo, hi = 3, 40
    if not (lo <= float(fab.get("stiff", 0)) <= hi):
        o["warn"].append(f"interfacing multiplier {fab.get('stiff')} outside practice ({lo}-{hi}x the shell's bending)")
    if c.res:
        ph = c.res["fabric"]["physical"]
        o["info"].append(f"fabric {c.res['fabric']['name']}: " + json.dumps(ph) + f"; solver {json.dumps(fab, default=str)}")
        if c.kind in ("coat", "jacket"):
            o["warn"].append("detail maps draw 11 mm buttons with vertical holes everywhere; a coat wants 20-25 mm, "
                             "horizontal holes (not configurable yet)")
    det = dict(cloth.DETAIL, **(c.gx.get("detail") or {}))
    o["info"].append(f"detail maps: hem {det['hem'] * 1000:.0f} mm on free edges, topstitch {det['topstitch'] * 1000:.1f} mm in")
    # the sim's schedule
    from . import cloth_job
    st = cloth._state(c.g)
    cfg = {"state": st, "placement": cloth.placement_of(c.gx),
           "assemble": bool({pcs[n]["wrap"].get("to", "torso") for n in pcs} - {"torso"}) and
           any(pcs[n]["wrap"].get("to", "torso") == "torso" for n in pcs),
           "hanger": isinstance(st, dict) and "hang" in st and not (st["hang"] or {}).get("pins"), "lower": True}
    o["info"].append("sim stages: " + " -> ".join(f"{s['name']} ({s['frames']} fr{', gravity' if s.get('gravity') else ''})"
                                                    for s in cloth_job.stages(cfg)))
    return o


# ---------------------------------------------------------------- 4 place


def _layer_gaps(X: np.ndarray, M: dict, Bp: dict, pairs: list) -> dict:
    """Median distance (mm) between an outer piece and the inner one where they overlap (outer vertices within 3 cm
    of the inner piece), along the inner piece's normal there."""
    from scipy.spatial import cKDTree
    F = M["F"]
    n = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    vn = np.zeros_like(X)
    for k in range(3):
        np.add.at(vn, F[:, k], n)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
    out = {}
    for outer, inner in pairs:
        io, ii = M["names"].index(outer), M["names"].index(inner)
        so, si = np.where(M["piece"] == io)[0], np.where(M["piece"] == ii)[0]
        if not len(so) or not len(si):
            continue
        d, j = cKDTree(X[si]).query(X[so])
        near = d < 0.03
        if near.sum() < 3:
            continue
        v = X[so[near]] - X[si[j[near]]]
        gap = np.abs(np.sum(v * vn[si[j[near]]], 1))
        out[f"{outer} over {inner}"] = round(float(np.median(gap)) * 1000, 1)
    return out


def _overlap_pairs(Bp: dict) -> list:
    pcs = Bp["pieces"]
    R = garment_design.roles(Bp)
    pairs = []
    tor = [n for n in pcs if pcs[n]["wrap"].get("to", "torso") == "torso"]
    for a in tor:
        oa = float(pcs[a]["wrap"].get("out", 0))
        if oa <= 0:
            continue
        ra = garment_design.role_of(a, pcs[a])
        for b in tor:
            if b != a and float(pcs[b]["wrap"].get("out", 0)) < oa and garment_design.role_of(b, pcs[b]) == ra:
                pairs.append((a, b))
    for f in R.get("collar_fall", []):
        for s in R.get("collar_stand", []):
            pairs.append((f, s))
    return pairs


def stage_place(c: Ctx, image: bool = True) -> dict:
    o = _out("place")
    Bp = c.Bp
    if not c.body.m["at"]:
        o["info"].append("draped on a prop: no body placement to check")
        return o
    h = float(c.gx.get("coarse", 0.02))
    M = cloth.mesh(Bp, h)
    smooth = cloth.placement_of(c.gx) == "smooth"
    body_p = c.body.straight_arms()[0] if smooth else c.body
    X = cloth.place(Bp, M, body_p, smooth=smooth)
    cr = sorted(cloth._piece_crossings(X, M))
    if cr and smooth:
        o["fail"].append(f"the start has pieces through each other: {', '.join(f'{a}/{b}' for a, b in cr)} (a contact "
                         "solver can't undo a start that is already crossed: move a piece, change its layer (wrap out))")
    elif cr:
        o["warn"].append(f"the start has pieces through each other: {', '.join(f'{a}/{b}' for a, b in cr)} (placement "
                         '"fitted": Blender pushes them apart while sewing, and this is where a CORRUPT result starts; '
                         "a sleeve cap inside the armhole and a cuff's own overlap are usual at 2 cm)")
    else:
        o["info"].append("start: no piece passes through another")
    push = Bp.get("push") or {}
    for p, v in push.items():
        pc = Bp["pieces"][p]
        stands = pc["wrap"].get("to", "") == "neck" and not pc["wrap"].get("fold") and \
            not any(f.get("piece") == p for f in Bp.get("folds") or [])
        if stands and v > 8:
            o["fail"].append(f"{p} ({garment_design.role_of(p, pc)}) started {v} mm inside the neck/jaw: the band is "
                             "taller than this neck allows (lower it: the draft's stand/band width option)")
        elif v > 15:
            o["warn"].append(f"{p} was pushed {v} mm off the body at the start (that stretch goes into the rest shape)")
    if push:
        o["info"].append(f"start pushed off the body (mm): {push}")
    stiff = cloth.interfacing(Bp, M)
    if smooth:
        tri, _ = cloth.edge_strain(X, M["uv"], M["F"])  # the rest is the flat pattern (made pieces left out below)
        lim = float((c.gx.get("zozo") or {}).get("strain_limit", 0.05))
        madep = np.isin(M["piece"][M["F"][:, 0]], [M["names"].index(n) for n in cloth.made_pieces(M, stiff)])
        over = (tri > lim) & ~madep
        if over.mean() > 0.002:
            worst = {}
            for t in np.where(over)[0]:
                p = M["names"][M["piece"][M["F"][t, 0]]]
                worst[p] = max(worst.get(p, 0), float(tri[t]))
            o["fail"].append(f"start stretched past the solver's strain limit {lim * 100:.0f}% on {over.mean() * 100:.1f}% of "
                             "the triangles (a strain-limited solver can't start there): " +
                             ", ".join(f"{p} {v * 100:.0f}%" for p, v in worst.items()))
        else:
            o["info"].append(f"start stretch vs the flat pattern within the strain limit ({lim * 100:.0f}%)")
    gaps = _layer_gaps(X, M, Bp, _overlap_pairs(Bp))
    if gaps:
        o["info"].append("layer gaps at the start (mm, centre to centre; the sim should close them to ~1-4): " +
                         ", ".join(f"{k} {v}" for k, v in gaps.items()))
    o["_X"], o["_M"] = X, M
    if image:
        objs = [{"name": "body", "V": body_p.V, "F": body_p.T, "color": "#d9c3b0"},
                {"name": "g_start", "V": X, "F": M["F"], "color": c.g.get("color", "#8fb3d9"), "thickness": 0.001}]
        from . import store
        from PIL import Image
        tmp = store._dir(c.name) / "_cloth_look"
        tmp.mkdir(exist_ok=True)
        allV = X
        box = (allV.min(0) - 0.08, allV.max(0) + 0.08)
        ext = box[1] - box[0]
        aspect = float(np.clip(max(ext[0], ext[1]) / max(ext[2], 1e-3), 0.62, 1.8))
        vs = ["front", "side", {"name": "three", "dir": [-0.65, -0.72, 0.25]}]
        paths = cloth.render(objs, tmp / "place", views=vs, resolution=520, box=box, aspect=aspect)
        ims = [Image.open(p).convert("RGB") for p in paths]
        sheet = Image.new("RGB", (sum(i.width for i in ims), ims[0].height), (60, 60, 60))
        x = 0
        for im in ims:
            sheet.paste(im, (x, 0))
            x += im.width
        for p in paths:
            Path(p).unlink(missing_ok=True)
        o["images"].append(("place", sheet))
    return o


# ---------------------------------------------------------------- 5 sim targets


def _target(name: str, cls: str) -> tuple:
    t = garment_design.kb()["targets"][name]
    rng = t.get("range") or t.get(cls)
    return rng, t.get("stage", "draft")


def _crest_radius(V: np.ndarray, M: dict, pieces: list) -> np.ndarray:
    F = M["F"]
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], n)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    kap = np.linalg.norm(vn[E[:, 0]] - vn[E[:, 1]], axis=1) / (np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1) + 1e-9)
    kv = np.zeros(len(V))
    np.maximum.at(kv, E[:, 0], kap)
    np.maximum.at(kv, E[:, 1], kap)
    sel = np.isin(M["piece"], [M["names"].index(p) for p in pieces]) & ~M["border"]
    return 1.0 / np.maximum(kv[sel], 1e-6)


def sim_measures(res: dict, c: Ctx) -> dict:
    """Numbers on the simulated garment the targets read (mm)."""
    V, M, Bp = res["V"], res["mesh"], res["pieces"]
    pcs = Bp["pieces"]
    R = garment_design.roles(Bp)
    out = {}
    gaps = _layer_gaps(V, M, Bp, _overlap_pairs(Bp))
    if gaps:
        out["layer_gap_mm"] = gaps
    ix = lambda n: np.where(M["piece"] == M["names"].index(n))[0]
    # the collar: how far the fall's edge lies below the neckline seam at CB, and its points on the shirt
    if R.get("collar_fall") and R.get("collar_stand"):
        fa, st = R["collar_fall"][0], R["collar_stand"][0]
        sv = ix(st)
        sew = M["sew"]
        neckpc = [M["names"].index(n) for n in pcs if pcs[n]["wrap"].get("to") == "neck"]
        seamv = np.r_[sew[np.isin(sew[:, 0], sv) & ~np.isin(M["piece"][sew[:, 1]], neckpc), 0],
                      sew[np.isin(sew[:, 1], sv) & ~np.isin(M["piece"][sew[:, 0]], neckpc), 1]]
        fv = ix(fa)
        if len(seamv) and len(fv):
            cy = V[seamv, 1].mean()
            back_seam = seamv[(V[seamv, 1] > cy)]
            bs = back_seam[np.argsort(np.abs(V[back_seam, 0]))[:3]] if len(back_seam) else seamv[:1]
            fb = fv[(V[fv, 1] > cy) & (np.abs(V[fv, 0]) < 0.015)]
            if len(fb):
                out["collar_cover_mm"] = round(float(V[bs, 2].mean() - V[fb, 2].min()) * 1000, 1)
            # points: the fall's border vertices at its pattern ends
            fbv = fv[M["border"][fv]]
            u = M["uv"][fbv, 0]
            tips = [fbv[np.argmin(u)], fbv[np.argmax(u)]]
            from scipy.spatial import cKDTree
            tor = np.where(np.isin(M["piece"], [M["names"].index(n) for n in pcs if pcs[n]["wrap"].get("to", "torso") == "torso"]))[0]
            if len(tor):
                d, _ = cKDTree(V[tor]).query(V[tips])
                out["collar_points_off_mm"] = [round(float(x) * 1000, 1) for x in d]
    # hem level (straight-hemmed kinds): the bottom row's height spread
    if c.kind in ("skirt", "coat", "dress", "trousers", "shorts", "jacket"):
        tor = [n for n in pcs if pcs[n]["wrap"].get("to", "torso") == "torso" and garment_design.role_of(n, pcs[n]) != "waistband"]
        hv = []
        for n in tor:
            s = ix(n)
            s = s[M["border"][s]]
            y = M["uv"][s, 1]
            hv.append(s[y < y.min() + 0.01])
        if hv:
            z = V[np.concatenate(hv), 2]
            out["hem_level_mm"] = round(float(np.percentile(z, 90) - np.percentile(z, 10)) * 1000, 1)
    if R.get("waistband") and "waist_z" in res["body"].at:
        wv = ix(R["waistband"][0])
        y = M["uv"][wv, 1]
        bot = wv[y < y.min() + 0.004]
        out["waistband_at_waist_mm"] = round(float(np.median(V[bot, 2]) - res["body"].at["waist_z"]) * 1000, 1)
    if res.get("sleeves"):
        out["sleeve_angle_hung_deg"] = res["sleeves"]
    vis = [n for n in pcs if n not in {e for e in Bp["interfaced"] if isinstance(e, str)}]
    cr = _crest_radius(V, M, vis)
    if len(cr):
        out["crest_radius_p10_mm"] = round(float(np.percentile(cr, 10)) * 1000, 1)
    out["strain_p95"] = round(float(res["fit"]["strain_p95"]), 4)
    return out


def stage_sim(c: Ctx, res: dict | None = None) -> dict:
    o = _out("sim")
    res = res or cloth.cached(c.name, c.spec, c.gname)
    if res is None:
        st = cloth.status(c.name, c.gname, c.g)
        o["info"].append(f"not simulated ({st['state']}): dress(name, garment, quality='draft') once stages 1-4 pass")
        return o
    v = res["fit"]["verdict"]
    (o["fail"] if v != "fits" else o["info"]).append(f"verdict: {v}")
    q = c.gx.get("quality", "final")
    h = float(c.gx.get("resolution", 0.01)) if q == "final" else float(c.gx.get("coarse", 0.02))
    cls = c.fabric_class()
    meas = sim_measures(res, c)
    o["info"].append(f"quality {q} ({h * 1000:.0f} mm triangles); fabric class {cls}")

    def judge(name, val, label):
        rng, stg = _target(name, cls)
        if rng is None:
            return
        vals = val if isinstance(val, list) else list(val.values()) if isinstance(val, dict) else [val]
        bad = [x for x in vals if not rng[0] <= x <= rng[1]]
        txt = f"{label}: {val} (target {rng[0]}..{rng[1]}, judged at {stg})"
        if bad and (stg == "draft" or (stg == "final" and q == "final" and h <= 0.0105)):
            o["fail"].append(txt)
        elif bad:
            o["warn"].append(txt + f" - not judged at {q} {h * 1000:.0f} mm")
        else:
            o["info"].append(txt)
    if "layer_gap_mm" in meas:
        judge("layer_gap_mm", meas["layer_gap_mm"], "layer gaps (mm)")
    if "collar_cover_mm" in meas:
        judge("collar_cover_mm", meas["collar_cover_mm"], "collar fall below the neckline seam at CB (mm)")
    if "collar_points_off_mm" in meas:
        judge("collar_points_off_mm", meas["collar_points_off_mm"], "collar points off the shirt (mm)")
    if "hem_level_mm" in meas:
        judge("hem_level_mm", meas["hem_level_mm"], "hem height spread p10-p90 (mm)")
    if "waistband_at_waist_mm" in meas:
        judge("waistband_at_waist_mm", meas["waistband_at_waist_mm"], "waistband's seam vs the body's waist (mm)")
    if "sleeve_angle_hung_deg" in meas:
        judge("sleeve_angle_hung_deg", meas["sleeve_angle_hung_deg"], "sleeves from vertical on the hanger (deg)")
    judge("crest_radius_p10_mm", meas.get("crest_radius_p10_mm", 0), "tightest folds, crest radius p10 (mm)")
    judge("strain_p95", meas["strain_p95"], "strain p95")
    o["info"].append("not measured by the tools yet: crease width, fold spacing (cloth_audit.md measured them on renders)")
    o["_res"] = res
    return o


# ---------------------------------------------------------------- running stages


def run(name: str, gname: str, stages=STAGES, images: bool = True, spec: dict | None = None) -> list:
    c = Ctx(name, gname, spec)
    out = []
    for s in stages:
        try:
            if s == "design":
                out.append(stage_design(c))
            elif s == "pattern":
                out.append(stage_pattern(c, image=images))
            elif s == "construction":
                out.append(stage_construction(c))
            elif s == "place":
                out.append(stage_place(c, image=images))
            elif s == "sim":
                out.append(stage_sim(c))
            else:
                raise ValueError(f"stage {s!r} unknown (have {', '.join(STAGES)})")
        except cloth.ClothError:
            raise
        except Exception as e:  # a stage that can't run is a failure of that stage, said plainly
            o = _out(s)
            o["fail"].append(f"stage {s} could not run: {type(e).__name__}: {e}")
            out.append(o)
    return out


def text(results: list, verbose: bool = True) -> str:
    L = []
    nf = sum(len(r["fail"]) for r in results)
    L.append(("FAILED: " + ", ".join(f"{r['stage']} {len(r['fail'])}" for r in results if r["fail"]) if nf else
              "all checked stages pass") + " (stages " + " > ".join(r["stage"] for r in results) + ")")
    for r in results:
        L.append(f"== {r['stage']}: {'FAIL' if r['fail'] else 'ok'}" + (f" ({len(r['warn'])} warnings)" if r["warn"] else ""))
        L += [f"  FAIL {x}" for x in r["fail"]]
        L += [f"  WARN {x}" for x in r["warn"]]
        if verbose:
            L += [f"  {x}" if not x.startswith("  ") else f"  {x}" for x in r["info"]]
    return "\n".join(L)


def gate(name: str, gname: str, spec: dict | None = None) -> list:
    """The hard failures of stages 1-3 (what dress refuses to simulate over)."""
    res = run(name, gname, ("design", "pattern", "construction"), images=False, spec=spec)
    return [f"{r['stage']}: {x}" for r in res for x in r["fail"]]
