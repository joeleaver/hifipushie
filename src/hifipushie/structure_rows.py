"""STRUCTURE ROWS: the one vocabulary of what a style-plan row may judge, and the rows the pre-sim gate reads (C286).

Why (garment_steps T6): run 2's structure rows were a shirt's, their targets INFERRED by the agent who wrote them (dress
shirt convention) or read from a README. The garment record now carries the targets: step 2 (garment_plan "style")
names the ONE worn state per closure, bends with targets and `rows` (what the reference photo judges). So the gate's rows
come from the record, and only general rules (true of every garment) are added with the rule as their source.

KINDS: a row's "what" is one of these (garment_plan refuses any other, with this list). Each kind says what it is, the
units its target may take, the base its ratios are OF (another kind, read on the build), and the build reading that
measures it (chain_structure.reads). A kind with no reading yet (`read` None) gives an UNMEASURED row that names what
is missing: it never silently passes. BASES are the kinds a ratio is taken of; a row of a base kind is a base, not judged.

TARGETS: {value, unit, tol?} -> a range value +- tol (no tol: +-10 %, a count exactly); unit "cm" -> mm; "px": a ratio of
the plan's row of this kind's base on the same view (the picture's own proportion, no scale guessed), else mm by the
view's scale (step 0), else UNMEASURED. {is: text} (a description): UNMEASURED, "give a number to judge it on the build".
Bends: a bend with a numeric target and a "what" is a row too (unless a row of the same kind is already in the plan).
"""
from __future__ import annotations

import numpy as np

STAGE = "build"
DEFAULT_TOL = 0.10  # (no tol in the plan: +-10 % of the value; stated in the row's source)

BASES = {
    "neck_width": dict(desc="the neck's width at the collar (body: twice the neck side's x)", read="neck_width_mm"),
    "shoulder_width": dict(desc="shoulder point to shoulder point (body landmarks)", read="shoulder_width_mm"),
    "closure_length": dict(desc="the closure's length down CF (the fronts' extent at CF)", read="closure_length_mm"),
}

_C = "chain_garment / chain_net: a build fault, report it"
KINDS = {
    "collar_points_apart": dict(desc="the collar points' distance (front view)", units=("mm", "ratio", "px"),
                                base="neck_width", read="collar_points_apart_mm", needs=("collar_fall",),
                                change="move the fall's point corner (alter_pattern) or the collar bend (style plan); "
                                       "else the FALL stage holds the leaves in: " + _C),
    "collar_tilt": dict(desc="the collar's top line in the side view, back high, front low", units=("deg",),
                        read="collar_top_tilt_deg", needs=("collar_stand",),
                        change="drop the CF neckline (alter_pattern move the front neck point down); else the BAND "
                               "stage holds the band level: " + _C),
    "collar_rise": dict(desc="a stand collar's rise from the neckline, deg from horizontal (90 = upright)", units=("deg",),
                        read=None, missing="no stand-rise reading yet", needs=("collar_stand",),
                        change="the stand's curve (alter_pattern on its neck edge) or the BAND stage"),
    "collar_points_drop": dict(desc="the collar points below the collar's back top (side view)", units=("mm", "ratio", "px"),
                               base="neck_width", read="collar_points_below_back_top_mm", needs=("collar_fall",),
                               change="alter_pattern move the fall's point corner down / up"),
    "collar_height": dict(desc="the collar's height at its front (a stand collar's CF height)", units=("mm", "ratio", "px"),
                          base="closure_length", read="collar_front_height_mm", needs=("collar_stand",),
                          change="the stand's height at CF (alter_pattern move the stand's front top corner)"),
    "fall_back_width": dict(desc="the collar fall's depth at CB (back / side view)", units=("mm", "ratio", "px"),
                            base="neck_width", read="collar_fall_cb_width_mm", needs=("collar_fall",),
                            change="the fall's depth at CB (alter_pattern move the fall's CB outer corner)"),
    "v_depth": dict(desc="an open front's V bottom below the higher collar point", units=("mm", "ratio", "px"),
                    base="neck_width", read="v_below_points_mm", needs=("front",),
                    change="the first fastened button (alter_pattern move the front's button marks) or the band's state"),
    "front_edge_plumb": dict(desc="a closed front's edge off vertical (worst 40 mm stretch: kinks show)", units=("deg",),
                             read="front_edge_kink_deg", needs=("front",),
                             change="the fronts' lengths either side of CF (alter_pattern match) or the button spacing; "
                                    "else the PLACKETS / soft network: " + _C),
    "hem_front_back": dict(desc="the back hem above (+) the front hem at CB / CF", units=("mm", "ratio", "px"),
                           base="closure_length", read="hem_cf_cb_mm", needs=("front", "back"),
                           change="the front and back lengths at CF / CB (alter_pattern move the hem points)"),
    "sleeve_end": dict(desc="the sleeve's end past (+) the wrist joint along the arm", units=("mm",),
                       read="sleeve_past_wrist_mm", needs=("sleeve",),
                       change="alter_pattern move the sleeve's hem points (or the cuff depth); else the RINGS stage"),
    "cuff_ease": dict(desc="the cuff's girth less the wrist's", units=("mm",), read="cuff_ease_mm", needs=("cuff",),
                      change="alter_pattern scale the cuff's length (or move its button mark)"),
    "garment_length": dict(desc="where the hem ends on the body (a landmark: waist, high hip, hip, seat...)",
                           units=("mm", "ratio", "px"), base="closure_length", read=None,
                           missing="no hem-at-landmark reading yet", change="the body length (alter_pattern)"),
    "cutaway_drop": dict(desc="a cutaway front's points below the closure's end", units=("mm", "ratio", "px"),
                         base="closure_length", read="cutaway_drop_mm",
                         change="the front's hem points (alter_pattern move the cutaway's tip) or the closure's end"),
    "trim_row_count": dict(desc="rows of a trim (frogging, buttons, braid) per side", units=("count",), read=None,
                           missing="no trims on chain builds yet (T10)", change="the detail's count (step 1)"),
    "trim_row_pitch": dict(desc="the spacing of a trim's rows", units=("mm", "ratio", "px"), base="closure_length",
                           read=None, missing="no trims on chain builds yet (T10)", change="the detail's placement"),
    "trim_lines_apart": dict(desc="the distance between two trim lines (braid)", units=("mm", "ratio", "px"),
                             base="shoulder_width", read=None, missing="no trims on chain builds yet (T10)",
                             change="the detail's placement"),
    "not_judged": dict(desc="a part the reference can't judge (no view of it): listed, never a gate row", units=()),
}
for _b, _d in BASES.items():
    KINDS[_b] = dict(desc=_d["desc"] + " (a base: ratios are taken of it; not judged)", units=("mm", "px", "cm"),
                     read=_d["read"], base_only=True)


def vocabulary() -> str:
    return "; ".join(f"{k} ({'|'.join(v['units']) or 'no target'}{', of ' + v['base'] if v.get('base') else ''}): "
                     f"{v['desc']}" for k, v in KINDS.items())


def check_row(r: dict, w: str, bad: list, ids: dict | None = None):
    """garment_plan's step-2 check of one row (or a bend with a "what"): the kind is known, its unit fits, a ratio is OF
    the kind's base (the base kind's name, or the id of a plan row of that kind)."""
    k = r.get("what")
    if k not in KINDS:
        bad.append(f"{w}.what {k!r}: not a row kind; one of: {', '.join(KINDS)} (each: guide garment_plan, or "
                   "structure_rows.vocabulary(); describe it in 'note')")
        return
    t = r.get("target") if isinstance(r.get("target"), dict) else {}
    u = t.get("unit")
    if u is not None and u not in KINDS[k]["units"]:
        bad.append(f"{w}: unit {u!r} for {k}: one of {', '.join(KINDS[k]['units']) or 'none (not judged)'}")
    if u == "ratio" and t.get("of") is not None:
        base = KINDS[k].get("base")
        of = t["of"]
        if of != base and (ids or {}).get(of) != base:
            bad.append(f"{w}.target.of {of!r}: a {k} ratio is of {base!r} (that name, or a row id of what {base!r})")


# ---------------------------------------------------------------- general rules (true of every garment)
ROUGH_SMOOTH_R_MM = 40.0  # the tightest body curve soft cloth wraps (a forearm): the smooth tube of the limit
ROUGH_LIMIT_X = 2.0       # the limit is twice that smooth tube's reading at the piece's own edge length (C286)


def rule_items(roles: set, soft: list, closures: dict) -> list:
    """Rows every garment gets from its pieces (source: the rule)."""
    I = []
    if "collar_fall" in roles:
        I.append(dict(id="collar_leaves_lie", read="collar_leaf_standoff_p90_mm", range=[None, 10.0], stage=1,
                      source="rule: a fall rests on the cloth under it (chain_garment LAYER + 2 mm = 5 mm); a coarse "
                             "panel mesh (20 mm) reads up to ~5 mm more: <= 10 mm",
                      change="the fall's outer edge is too short to lie down (alter_pattern slash_spread it) or the FALL "
                             "stage holds it up: " + _C))
        if "collar_stand" in roles:
            I.append(dict(id="collar_turned", read="fall_above_stand_mm", range=[None, 0.0], stage=1,
                          source="rule: a fall collar turns down over its stand at CB (garment_reads.collar_reads)",
                          change="the roll line / fall depth (alter_pattern on the collar's roll fold) or the FALL stage"))
    if {"front", "back"} <= roles:
        I.append(dict(id="hem_level_lr", read="hem_left_right_mm", range=[None, 10.0], stage=2,
                      source="rule: a mirrored pattern worn straight hangs level left to right; <= 10 mm (one 10 mm "
                             "panel edge)", change="front.L / front.R lengths differ (alter_pattern match) or the soft "
                                                   "network starts askew: " + _C))
    for c, st in closures.items():
        I.append(dict(id=f"closure_{c}", read=f"closure_state:{c}", equals=st["state"], stage=1,
                      source=f"style plan state.{c}: {st['state']} ({st.get('source', '')})",
                      change=f"build the closure {c} in its planned state (chain_garment wear / T7 band state)",
                      **({} if st.get("read") else {"missing": f"no build reading of the state of a closure on "
                                                               f"{'/'.join(st.get('roles') or ['these'])} pieces yet"})))
        if st["state"] == "closed" and st.get("read") == "front_state":
            I.append(dict(id=f"closure_{c}_meets", read="front_met_share", range=[0.9, None], stage=1,
                          source=f"rule: a closed closure's edges meet (garment_reads MEET_MM 2 mm) over >= 0.9 of it; "
                                 f"plan state.{c} closed", change="the fronts gape: the button marks (alter_pattern "
                                                                 "move) or the PLACKETS / soft network: " + _C))
    if soft:
        I.append(dict(id="soft_cloth_smooth", read="soft_rough_over_limit", range=[None, 1.0], stage=1,
                      source=f"rule: the build has no folds (garment_steps 7a: structure only); each soft piece's "
                             f"bump p90 (face normal vs its neighbours', as a height at the mesh's edge) <= "
                             f"{ROUGH_LIMIT_X:g}x a smooth R{ROUGH_SMOOTH_R_MM:.0f} mm tube's at the same edge (C286); "
                             f"read: worst piece's ratio to its limit",
                      change="crumpled soft cloth: the SURFACES / soft network fill (chain_garment) wrinkles it: " + _C))
    return I


# ---------------------------------------------------------------- roughness
def face_bump_mm(X, F) -> np.ndarray:
    """Per face: the angle between its normal and the mean of its edge neighbours' normals, as a height at the mesh's
    median edge (tan(angle) * edge, mm). A smooth curve's neighbours tilt symmetrically and cancel; crumples don't."""
    X, F = np.asarray(X, float), np.asarray(F, np.int64)
    if len(F) < 4:
        return np.zeros(0)
    n = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-15
    E = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1)
    fi = np.tile(np.arange(len(F)), 3)
    key = E[:, 0] * (int(F.max()) + 1) + E[:, 1]
    o = np.argsort(key, kind="stable")
    same = key[o][1:] == key[o][:-1]
    a, b = fi[o][:-1][same], fi[o][1:][same]
    acc, cnt = np.zeros_like(n), np.zeros(len(F))
    np.add.at(acc, a, n[b]); np.add.at(acc, b, n[a]); np.add.at(cnt, a, 1); np.add.at(cnt, b, 1)
    ok = cnt >= 2
    m = acc[ok] / (np.linalg.norm(acc[ok], axis=1, keepdims=True) + 1e-15)
    ang = np.arccos(np.clip((n[ok] * m).sum(1), -1, 1))
    e = float(np.median(np.linalg.norm(X[F[:, 0]] - X[F[:, 1]], axis=1)))
    return np.tan(np.minimum(ang, np.radians(80))) * e * 1000


def tube(r: float, h: float, length: float = 0.4, noise: float = 0.0, seed: int = 0):
    """A tube of radius r (m) meshed at edge ~h, optionally with radial noise (m): the roughness calibration."""
    nu, nv = max(int(2 * np.pi * r / h), 6), max(int(length / h), 3)
    t, z = np.meshgrid(np.linspace(0, 2 * np.pi, nu, endpoint=False), np.linspace(0, length, nv))
    rr = r + noise * np.random.default_rng(seed).standard_normal(t.shape)
    X = np.c_[(rr * np.cos(t)).ravel(), (rr * np.sin(t)).ravel(), z.ravel()]
    i = np.arange(nu * nv).reshape(nv, nu)
    j = np.roll(i, -1, axis=1)
    F = np.r_[np.c_[i[:-1].ravel(), j[:-1].ravel(), j[1:].ravel()], np.c_[i[:-1].ravel(), j[1:].ravel(), i[1:].ravel()]]
    return X, F


def rough_limit_mm(edge_mm: float) -> float:
    """ROUGH_LIMIT_X x the bump p90 of a smooth R40 tube meshed at this edge (measured: 1.0 mm at 10 mm edges)."""
    X, F = tube(ROUGH_SMOOTH_R_MM / 1000, max(edge_mm, 0.5) / 1000 / 1.22)  # (the tube's median edge ~1.22 h)
    return round(ROUGH_LIMIT_X * float(np.percentile(face_bump_mm(X, F), 90)), 2)


def roughness(X, M, soft: list) -> dict:
    """{piece: {bump_p90_mm, limit_mm, edge_mm}} for each soft piece of the build; worst ratio to its limit."""
    X, F, pid = np.asarray(X, float), np.asarray(M["F"]), np.asarray(M["piece"])
    out = {}
    for k, n in enumerate(M["names"]):
        if n not in soft:
            continue
        Fk = F[pid[F[:, 0]] == k]
        b = face_bump_mm(X, Fk)
        if not len(b):
            continue
        e = float(np.median(np.linalg.norm(X[Fk[:, 0]] - X[Fk[:, 1]], axis=1))) * 1000
        out[n] = dict(bump_p90_mm=round(float(np.percentile(b, 90)), 2), limit_mm=rough_limit_mm(e), edge_mm=round(e, 1))
    return out


# ---------------------------------------------------------------- rows from the record
def _role(name: str, piece: dict | None = None) -> str:
    """A piece's role: the inventory's "role" when it names one (a hussar's stand "collar"), else by its name."""
    from . import garment_design
    return garment_design.role_of(name, piece if (piece or {}).get("role") else None)


def soft_pieces(M, parts: dict | None) -> list:
    """The build's soft pieces: the inventory's stiff: false pieces (matched by name, else by role)."""
    pcs = (parts or {}).get("pieces") or {}
    by_role = {}
    for n, p in pcs.items():
        by_role.setdefault(_role(n, p), []).append(bool(p.get("stiff")))
    out = []
    for n in M["names"]:
        st = [bool(pcs[n].get("stiff"))] if n in pcs else by_role.get(_role(n))
        if st is not None and not any(st):
            out.append(n)
    return out


def closure_reads(parts: dict | None, state: dict) -> dict:
    """{closure: {state, source, read}}: which build reading tells each planned closure's state."""
    out = {}
    for c, st in (state or {}).items():
        pcs = (parts or {}).get("pieces") or {}
        roles = {_role(p, pcs.get(p)) for p in (((parts or {}).get("closures") or {}).get(c) or {}).get("pieces") or []}
        read = "front_state" if "front" in roles else "band_state" if "collar_stand" in roles else None
        out[c] = dict(st, read=read, roles=sorted(roles))
    return out


STATE_OF = {"front_state": {"closed": "closed", "open": "open", "partly": "part"},
            "band_state": {"closed": "closed", "open": "open", "partly": "open"}}


def _range(t: dict, scale: float = 1.0):
    v = float(t["value"]) * scale
    if t.get("tol") is not None:
        d, note = float(t["tol"]) * scale, f"+-{t['tol']}"
    elif t.get("unit") == "count":
        d, note = 0.0, "exactly"
    else:
        d, note = abs(v) * DEFAULT_TOL, f"+-{DEFAULT_TOL:.0%} (no tol in the plan)"
    return [round(v - d, 3), round(v + d, 3)], note


def plan_items(plan: dict | None, roles: set) -> tuple[list, list]:
    """(items, notes): the style plan's rows and numeric bends as structure items; notes list what is not judged."""
    style = (plan or {}).get("style") or {}
    views = ((plan or {}).get("read") or {}).get("views") or []
    rows = [dict(r, _from="row") for r in style.get("rows") or []]
    kinds = {r.get("what") for r in rows}
    for b in style.get("bends") or []:
        t = b.get("target") or {}
        if "value" in t and b.get("what") and b["what"] not in kinds:
            rows.append(dict(b, _from="bend"))
    bases = {}  # (base kind, view) -> px value (a base row on that view)
    for r in rows:
        k = KINDS.get(r.get("what")) or {}
        t = r.get("target") or {}
        if k.get("base_only") and t.get("unit") == "px":
            bases[(r["what"], r.get("view"))] = float(t["value"])
    I, notes = [], []
    for r in rows:
        kid, k, t = r.get("what"), KINDS.get(r.get("what")), r.get("target") or {}
        rid = r.get("id") or kid
        src = f"style plan {r['_from']} {rid}: {r.get('source', '')}"
        if k is None:
            I.append(dict(id=rid, read=f"unknown_kind:{kid}", range=[None, None], stage=1, source=src,
                          missing=f"what {kid!r} is not a row kind (garment_plan refuses it now)", change="rewrite step 2"))
            continue
        if kid == "not_judged" or k.get("base_only"):
            notes.append(f"{rid}: {'not judged' if kid == 'not_judged' else 'a base (ratios are of it)'} ({src})")
            continue
        it = dict(id=rid, stage=1, source=src, change=k.get("change", ""))
        miss = None
        if k.get("needs") and not set(k["needs"]) <= roles:
            miss = f"the build has no {' + '.join(sorted(set(k['needs']) - roles))} piece (the plan judges one)"
        elif "value" not in t:
            miss = f"the target is a description ({t.get('is')!r}): give a number (value, unit) to judge it on the build"
        elif k.get("read") is None:
            miss = k.get("missing", "no build reading for this kind yet")
        unit, read, scale = t.get("unit"), k.get("read"), 1.0
        if not miss and unit == "px":
            bpx = bases.get((k.get("base"), r.get("view"))) or bases.get((k.get("base"), None))
            sc = ((views[r["view"]] if isinstance(r.get("view"), int) and r["view"] < len(views) else {})
                  .get("scale") or {}).get("mm_per_px")
            if k.get("base") and bpx:
                unit, scale = "ratio", 1.0 / bpx
                src += f" (px as a ratio of the plan's {k['base']} row: {bpx:g} px)"
            elif sc:
                unit, scale = "mm", float(sc)
                src += f" (px to mm by the view's scale {sc} mm/px)"
            else:
                miss = f"a px target with no {k.get('base') or 'base'} row on its view and no view scale"
        if not miss:
            if unit == "cm":
                unit, scale = "mm", 10.0
            if unit == "ratio":
                read = f"{read}/{BASES[k['base']]['read']}"
            it["range"], note = _range(t, scale)
            it["read"], it["source"] = read, src + f"; {note}"
        else:
            it.update(read=f"unmeasured:{rid}", range=[None, None], missing=miss,
                      change=f"no measure: {miss}; waive it by name with a reason, or add the reading (structure_rows)")
        I.append(it)
    return I, notes
