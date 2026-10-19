"""Seam-table check for any cloth design (read-only: nothing here changes a pattern or a sim).

`seams(Bp)` walks a drafted design's seam table (`cloth.pieces(...)` output) and, per seam, measures both sides on
the flat pattern: lengths, the ease one side carries (A / B - 1), and where the notches/junctions of one side land on
the other. The mesher (`cloth.mesh`) sews both sides by FRACTION of their length, so ease is spread evenly over the
whole seam and a notch at fraction f on one side meets fraction f on the other: a notch mismatch here is a real
misalignment in the sim (a sleeve's top notch off the shoulder seam, a side seam's waist notch off the waist).

Expected ease per seam kind (`KINDS`; tailoring practice, see cloth_audit.md):
  cap      sleeve cap into armhole: shirt 0-3% (flat-felled, little ease), coat/jacket 3-6% (eased over the cap)
  band     a band into an edge (collar to stand, stand to neckline, cuff to sleeve): -1..+1.5%
  plain    everything else (side, shoulder, underarm, centre back): +-1.5% (a back shoulder may carry +2-4%: `back_shoulder`)
A side that is a chain with gaps (pleats/darts folded away) is measured on its sewn edges only.
`report(Bp)` returns text lines; any seam outside its band or with a notch off by more than NOTCH_MM is flagged "!!".
"""
from __future__ import annotations

import numpy as np

from . import pattern, validated

KINDS = {"cap_shirt": (0.0, 0.03), "cap_coat": (0.03, 0.06), "band": (-0.01, 0.015), "plain": (-0.015, 0.015),
         "back_shoulder": (0.0, 0.04)}
NOTCH_MM = 6.0


def _panel(name, h, notch=None):
    P = np.array([[0.0, 0.0], [0.0, h], [0.3, h], [0.3, 0.0]])
    return {"name": name, "P": P, "names": {"bl": 0, "tl": 1, "tr": 2, "br": 3}, "wrap": {"to": "torso"},
            "marks": {} if notch is None else {"notch_waist": [0.0, notch]}}


def _selftest_seams():
    """Known answers on two flat panels sewn along one side (a plain seam): 500 vs 500 mm = ease 0, ok; 500 vs 480 mm
    = +4.2 %, outside +-1.5 %; a waist notch at 250 vs 270 mm along the seam = 20 mm off (> NOTCH_MM)."""
    bp = lambda hb, na=None, nb=None: {"pieces": {"front": _panel("front", 0.5, na), "back": _panel("back", hb, nb)},
                                       "seams": [("front:bl>tl", "back:bl>tl")]}
    r = seams(bp(0.5))[0]
    assert r["kind"] == "plain" and r["ok"] and r["ease"] == 0.0 and r["len_a_mm"] == 500.0, r
    r = seams(bp(0.48))[0]
    assert not r["ok"] and abs(r["ease"] - (0.5 / 0.48 - 1)) < 1e-4, r
    r = seams(bp(0.5, 0.25, 0.27))[0]
    assert r["notches_off"] and r["notches_off"][0][2] == 20.0, r
    assert not seams(bp(0.5, 0.25, 0.252))[0]["notches_off"]


def _side(pcs, side):
    chain = [side] if isinstance(side, str) else list(side)
    out = []
    for e in chain:
        nm, arc = e.split(":", 1)
        ix = pattern.arc_indices(pcs[nm], arc)
        out.append((e, nm, ix, pcs[nm]["P"][ix]))
    return out


def _marks_on(pc, P, tol=0.004):
    """(name, arc position along P) of the piece's notch marks (and named outline points inside P) lying on P."""
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    res = []
    for k, v in pc["marks"].items():
        v = np.asarray(v, float)
        if len(v) != 2 or "notch" not in k.lower():
            continue
        a, b = P[:-1], P[1:]
        ab = b - a
        t = np.clip(((v - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-18), 0, 1)
        d = np.linalg.norm(a + t[:, None] * ab - v, axis=1)
        i = int(np.argmin(d))
        if d[i] < tol:
            res.append((k, cum[i] + t[i] * seg[i]))
    return res


def _kind(Bp, A, B, garment_kind):
    pcs = Bp["pieces"]
    to = lambda s: {pcs[e.split(":")[0]]["wrap"].get("to", "torso") for e in ([s] if isinstance(s, str) else s)}
    ta, tb = to(A), to(B)
    if any(t.startswith("arm.") for t in ta) and "torso" in tb:
        return "cap_coat" if "coat" in garment_kind else "cap_shirt"
    if "neck" in ta or "neck" in tb:
        return "band"
    if any(t.startswith("arm.") for t in ta) and any(t.startswith("arm.") for t in tb) and ta != tb:
        return "plain"
    sa = [e for e in ([A] if isinstance(A, str) else A)]
    if any("cuff" in e for e in sa + ([B] if isinstance(B, str) else list(B))):
        return "band"
    if any(":shoulder" in e for e in sa) and any("back" in e.split(":")[0] for e in sa):
        return "back_shoulder"
    return "plain"


@validated.known_answer(_selftest_seams)
def seams(Bp: dict, garment_kind: str = "") -> list:
    pcs = Bp["pieces"]
    rows = []
    for A, B in Bp["seams"]:
        sa, sb = _side(pcs, A), _side(pcs, B)
        la = sum(pattern.length(p) for *_, p in sa)
        lb = sum(pattern.length(p) for *_, p in sb)
        kind = _kind(Bp, A, B, garment_kind)
        lo, hi = KINDS[kind]
        ease = la / lb - 1 if lb > 0 else 0.0
        # the longer side is the eased one; for plain seams either direction counts
        e = ease if kind.startswith("cap") or kind == "back_shoulder" else ease
        ok = lo - 1e-9 <= e <= hi + 1e-9 if kind != "plain" else abs(e) <= hi
        marks = []
        for lab, s, L in (("A", sa, la), ("B", sb, lb)):
            off, fr = 0.0, []
            for e_, nm, ix, P in s:
                fr += [(nm + ":" + k, (off + pos) / L) for k, pos in _marks_on(pcs[nm], P)]
                off += pattern.length(P)
                if off < L - 1e-9:
                    fr.append(("|" + e_, off / L))  # a junction between chained edges (a seam crossing)
            marks.append(fr)
        miss = []
        for na, fa in marks[0]:
            if not marks[1]:
                break
            nb, fb = min(marks[1], key=lambda m: abs(m[1] - fa))
            d = abs(fa - fb) * lb * 1000
            # (a mark of the other side that another of this side's marks already meets isn't this one's partner: a
            # belt's ends either side of the waist notch its own middle notch sits on)
            taken = any(abs(f2 - fb) * lb * 1000 <= NOTCH_MM for n2, f2 in marks[0] if n2 != na)
            # (two seam crossings needn't meet: a two-piece sleeve's hindarm seam lies near the back pitch, not on it)
            if abs(fa - fb) < 0.08 and d > NOTCH_MM and not taken and not (na.startswith("|") and nb.startswith("|")):
                miss.append((na, nb, round(d, 1)))
        rows.append({"a": A, "b": B, "kind": kind, "len_a_mm": round(la * 1000, 1), "len_b_mm": round(lb * 1000, 1),
                     "ease": round(ease, 4), "band": (lo, hi), "ok": bool(ok), "notches_off": miss})
    return rows


def report(Bp: dict, garment_kind: str = "") -> list:
    out = []
    for r in seams(Bp, garment_kind):
        flag = "" if r["ok"] and not r["notches_off"] else "!! "
        name = lambda s: s if isinstance(s, str) else " + ".join(s)
        line = (f"{flag}{r['kind']:<13} {r['len_a_mm']:7.1f} vs {r['len_b_mm']:7.1f} mm  ease {100 * r['ease']:+5.1f}% "
                f"(band {100 * r['band'][0]:+.1f}..{100 * r['band'][1]:+.1f})  {name(r['a'])} || {name(r['b'])}")
        if r["notches_off"]:
            line += "  notches off: " + ", ".join(f"{a}~{b} {d} mm" for a, b, d in r["notches_off"])
        out.append(line)
    return out


# ---------------------------------------------------------------- the pattern gate (2026-10-19)
# Joe: "we're spending too much time on sim before we validate our patterns." The standing rule (codified C2: a pattern
# passes its checklist before any sim) was not enforced: Garrett's jacket neckline carried widen 0.018 / back 0.035 from
# a misread note while many collar sessions tuned the drape (traps.md "A misread note became a pattern default").
#
# `pattern_gate(model, garment)` measures, WITHOUT a sim, every cloth_checklist.json item of the garment's kind that can
# be read from the pattern placed on the body (cloth.build(place_only=True): the start the sim would get, on the fine
# mesh) plus the pattern's own rows (seam ease / notches). Each row comes back
#   PASS / FAIL   measured, with its numbers (against the reference reading `refs`, or the item's target_mm rule)
#   UNMEASURED    no pattern-stage measure yet (a "missing: ..." measure, an unknown one, no reference reading): it
#                 BLOCKS (never silently passes) unless waived by name with a reason (`waive`, recorded)
#   SIM           judged after the sim by nature (drape, folds, closures done up, the worn collar / lapel tells)
#   INFO          a number with no target yet (neckline_standoff until a checklist item adopts it)
# New checklist items are picked up as they land (the checklist is read live; an item may name its pattern-stage
# measure in "pattern_measure", one of PATTERN_MEASURES). The record is <gate_dir()>/<gate_key>.json, keyed by the
# pattern's content hash + the body's hash, with the checklist's own hash as its version. Every cloth sim of a drafted
# garment (local or rented) refuses without a PASS record for exactly that pattern + body: cloth_job.require_pattern_gate.
# Override (transition only; logged in the record, the job folder and overrides.jsonl):
#   HIFIPUSHIE_SIM_WITHOUT_PATTERN_GATE="<reason>"

import hashlib as _hashlib  # noqa: E402
import json as _json  # noqa: E402
import os as _os  # noqa: E402
import time as _time  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

GATE_ENV_OVERRIDE = "HIFIPUSHIE_SIM_WITHOUT_PATTERN_GATE"
GATE_VERSION = 1

# cloth_reference measures that read the placed rest (lengths, widths, design choices from the spec)
PATTERN_READABLE = ("hem_cf_z", "hem_cb_z", "sleeve_end_t", "trouser_hem_z", "shoulder_width", "chest_width",
                    "waist_width", "hem_sweep", "seat_width", "knee_width", "leg_opening", "sleeve_opening",
                    "waistband_z", "lapel_width", "top_button_z", "detail_choice", "has_belt", "over", "fabric", "colour")
# judged after the sim by nature (gravity, folds, closures done up, the worn tells)
SIM_STAGE = ("front_hang", "drape_level", "fold_level", "silhouette_shape", "has_crease", "tucked", "front_state",
             "buttons_done", "collar_state", "button_count", "placket_finish", "tell:collar_show_mm", "tell:cuff_show_mm",
             "tell:collar_hug_mm", "tell:lapel_gap_mm")


def gate_dir() -> _Path:
    return _Path(_os.environ.get("HIFIPUSHIE_PATTERN_GATE_DIR", "/mnt/data/hifipushie/pattern_gate"))


def _r(a, q=1e-5):
    return np.round(np.asarray(a, float) / q).astype(np.int64)


def pattern_hash(Bp: dict) -> str:
    """The drafted pattern's content: every piece's outline (0.01 mm), named points, wrap, notch marks and the seam
    table. Keys starting with "_" (a Body riding along) never count."""
    h = _hashlib.sha1(b"pattern-v1")
    pcs = Bp["pieces"]
    for nm in sorted(pcs):
        pc = pcs[nm]
        h.update(f"|{nm}|".encode())
        h.update(_r(pc["P"]).tobytes())
        marks = {}
        for k, v in (pc.get("marks") or {}).items():
            a = np.asarray(v)
            if a.dtype.kind in "fi":
                marks[k] = a.astype(float).round(5).tolist()
        h.update(_json.dumps({"names": pc.get("names"), "wrap": pc.get("wrap"), "marks": marks},
                             sort_keys=True, default=str).encode())
    h.update(_json.dumps(Bp.get("seams"), default=str).encode())
    return h.hexdigest()[:20]


def body_hash(body_src: dict) -> str:
    """The body the pattern is placed on (0.01 mm), and the garment under it when layered."""
    h = _hashlib.sha1(b"body-v1")
    h.update(_r(body_src["V"]).tobytes())
    h.update(_json.dumps(body_src["F"], default=lambda o: o.tolist() if hasattr(o, "tolist") else int(o)).encode())
    u = body_src.get("under")
    if u is not None and u.get("V") is not None:
        h.update(b"|under|" + _r(u["V"]).tobytes())
    return h.hexdigest()[:20]


def gate_key(phash: str, bhash: str) -> str:
    return _hashlib.sha1(f"{phash}|{bhash}".encode()).hexdigest()[:20]


def checklist_version() -> str:
    from . import cloth_reference
    return _hashlib.sha1(cloth_reference.CHECKLIST_PATH.read_bytes()).hexdigest()[:12]


def record_path(phash: str, bhash: str) -> _Path:
    return gate_dir() / f"{gate_key(phash, bhash)}.json"


def read_record(phash: str, bhash: str) -> dict | None:
    try:
        return _json.loads(record_path(phash, bhash).read_text())
    except Exception:
        return None


def write_record(rec: dict) -> _Path:
    p = record_path(rec["pattern"], rec["body"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".tmp{_os.getpid()}")
    tmp.write_text(_json.dumps(rec, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    tmp.replace(p)
    return p


def verdict(rows: list, waive: dict | None = None) -> str:
    """PASS: no row FAIL / UNMEASURED; PASS_WAIVED: each such row waived by name with a reason; else FAIL."""
    waive = waive or {}
    block = [r for r in rows if r["status"] in ("FAIL", "UNMEASURED")]
    if not block:
        return "PASS"
    return "PASS_WAIVED" if all(waive.get(r["id"]) for r in block) else "FAIL"


def passed(rec: dict | None) -> bool:
    return bool(rec) and rec.get("status") in ("PASS", "PASS_WAIVED")


def blocking(rec: dict | None) -> list:
    """"<status> <id>" of the rows that keep a record from passing (waived rows left out)."""
    if not rec:
        return []
    w = rec.get("waived") or {}
    return [f"{r['status']} {r['id']}" for r in rec.get("rows", []) if r["status"] in ("FAIL", "UNMEASURED")
            and not w.get(r["id"])]


def _boundary_vertices(F) -> np.ndarray:
    F = np.asarray(F)
    E = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    u, c = np.unique(E, axis=0, return_counts=True)
    return np.unique(u[c == 1])


def _selftest_neckline_standoff():
    """Known answers: a body 'neck' (a dense cylinder of radius 60 mm) and a garment strip (two rings 30 mm apart, radius
    r) whose top ring is the neckline: r = 75 mm -> 15 mm off the neck; r = 100 mm (a planted wide neckline) -> 40 mm.
    The bottom ring lies below the band and never counts."""
    th = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    zs = np.linspace(1.35, 1.55, 81)
    bV = np.array([[0.06 * np.cos(t), 0.06 * np.sin(t), z] for z in zs for t in th])

    def strip(r, n=96):
        a = np.linspace(0, 2 * np.pi, n, endpoint=False)
        ring = np.c_[r * np.cos(a), r * np.sin(a)]
        V = np.r_[np.c_[ring, np.full(n, 1.45)], np.c_[ring, np.full(n, 1.42)]]
        F = [[i, (i + 1) % n, n + i] for i in range(n)] + [[(i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
        return V, np.array(F)
    neck = np.array([0.0, 0.0, 1.45])
    V, F = strip(0.075)
    m = neckline_standoff_mm(V, F, bV, neck, reach=0.12, band=0.01)
    assert m["n"] == 96 and abs(m["median_mm"] - 15.0) < 0.3, m
    V, F = strip(0.10)
    m = neckline_standoff_mm(V, F, bV, neck, reach=0.15, band=0.01)
    assert m["n"] == 96 and abs(m["median_mm"] - 40.0) < 0.3, m


@validated.known_answer(_selftest_neckline_standoff)
def neckline_standoff_mm(V, F, bodyV, neck, reach: float = 0.12, band: float = 0.025, keep=None) -> dict:
    """How far the garment's neckline (its open edge near the neck) lies off the body, read on the placed pattern:
    the boundary vertices within `reach` m of the neck point and no lower than `band` m below it, each one's distance
    to the nearest body vertex. {"median_mm", "max_mm", "n"}; keep: a vertex mask (torso pieces only)."""
    from scipy.spatial import cKDTree
    V, bodyV, neck = np.asarray(V, float), np.asarray(bodyV, float), np.asarray(neck, float)
    b = _boundary_vertices(F)
    if keep is not None:
        b = b[np.asarray(keep, bool)[b]]
    b = b[(np.linalg.norm(V[b] - neck, axis=1) < reach) & (V[b, 2] > neck[2] - band)]
    if not len(b):
        return {"median_mm": None, "max_mm": None, "n": 0}
    d, _ = cKDTree(bodyV).query(V[b])
    return {"median_mm": round(1000 * float(np.median(d)), 1), "max_mm": round(1000 * float(d.max()), 1), "n": int(len(b))}


PATTERN_MEASURES = ("neckline_standoff_mm",)

# construct option dicts whose values change a default: each needs a "source" (where the numbers came from)
SOURCE_CONSTRUCT_KEYS = ("collar_options", "lapel_options", "hug")


def option_sources(g: dict) -> list:
    """WARN lines (never a refusal): a pattern op, the block options or a construct option dict that changes a default
    without a "source" string (a measurement, a reference, a book: traps.md "A misread note became a pattern default")."""
    import inspect
    out = []
    pat = g.get("pattern") if isinstance(g.get("pattern"), dict) else {}
    try:
        from . import pattern_draft as pd
        from . import pattern_styles  # noqa: F401  (registers the style ops)
        ops_ = pd.OPS
    except Exception:
        ops_ = {}
    for k, op in enumerate(pat.get("ops") or []):
        if not isinstance(op, dict) or op.get("source"):
            continue
        defaults = {}
        fn = ops_.get(op.get("op"))
        if fn is not None:
            try:
                defaults = {n: p.default for n, p in inspect.signature(fn).parameters.items()
                            if p.default is not inspect.Parameter.empty}
            except (TypeError, ValueError):
                pass
        changed = [n for n, v in op.items() if n not in ("op", "source") and (n not in defaults or defaults[n] != v)]
        if changed:
            out.append(f"WARN pattern op {k + 1} ({op.get('op')}): {', '.join(f'{n}={op[n]!r}' for n in changed)} "
                       "without a \"source\" (say where the numbers come from)")
    bo = pat.get("block_options")
    if isinstance(bo, dict) and any(k != "source" for k in bo) and not bo.get("source"):
        out.append(f"WARN pattern block_options {sorted(k for k in bo if k != 'source')} without a \"source\"")
    c = g.get("construct")
    if isinstance(c, dict):
        for k in SOURCE_CONSTRUCT_KEYS:
            v = c.get(k)
            if isinstance(v, dict) and any(k_ != "source" for k_ in v) and not v.get("source"):
                out.append(f"WARN construct {k} {sorted(k_ for k_ in v if k_ != 'source')} without a \"source\"")
    return out


def classify(it: dict) -> str:
    """How the gate treats a checklist item: "pattern" (a PATTERN_MEASURES measure), "placed" (a cloth_reference measure
    read on the placed rest), "sim" (judged after the sim) or "unmeasured" (anything else: it blocks)."""
    if it.get("pattern_measure") in PATTERN_MEASURES:
        return "pattern"
    m = str(it.get("measure", ""))
    if m.startswith("missing"):
        return "unmeasured"
    if m in SIM_STAGE:
        return "sim"
    if m in PATTERN_READABLE:
        return "placed"
    return "unmeasured"


def _rule(it: dict, v: float):
    """(PASS | FAIL, miss mm) of a value against an item's target_mm [lo, hi] + tolerance; None for other rule shapes."""
    t = it.get("target_mm")
    if not (isinstance(t, (list, tuple)) and len(t) == 2):
        return None
    lo, hi = float(t[0]), float(t[1])
    miss = 0.0 if lo <= v <= hi else (v - hi if v > hi else v - lo)
    return ("PASS" if abs(miss) <= float(it.get("tolerance", 0) or 0) else "FAIL"), round(miss, 1)


def gate_rows(Bp: dict, items: list, ctx=None, gname: str = "", refs: dict | None = None, extra: dict | None = None,
              garment_kind: str = "") -> list:
    """The gate's rows: the pattern's seam row, then one row per checklist item. ctx: a cloth_reference.Ctx holding the
    placed rest as gname's result (None: "placed" items are UNMEASURED); refs: the garment's reference targets {item id:
    reading}; extra: {PATTERN_MEASURES name: its result dict} already read on this garment."""
    rows = []
    sm = seams(Bp, garment_kind)
    bad = [r for r in sm if not r["ok"] or r["notches_off"]]
    rows.append({"id": "seams", "stage": 2, "status": "FAIL" if bad else "PASS", "measure": "cloth_check.seams",
                 "ours": f"{len(sm)} seams, {len(bad)} outside their ease band or with notches off",
                 "detail": [f"{r['a']} || {r['b']}: ease {100 * r['ease']:+.1f}% band {r['band']} notches {r['notches_off']}"
                            for r in bad][:12]})
    extra, refs = extra or {}, refs or {}
    for it in items:
        cl = classify(it)
        row = {"id": it["id"], "stage": it["stage"], "measure": it.get("pattern_measure") or it.get("measure")}
        if cl == "sim":
            row.update(status="SIM", why="judged after the sim (drape, folds, closures, the worn tells)")
        elif cl == "unmeasured":
            row.update(status="UNMEASURED", why=f"no pattern-stage measure: {it.get('measure')}")
        elif cl == "pattern":
            v = extra.get(it["pattern_measure"])
            rr = _rule(it, float(v["median_mm"])) if v and v.get("median_mm") is not None else None
            if rr is None:
                row.update(status="UNMEASURED", why=f"{it['pattern_measure']}: not read on this garment or no "
                                                    "plain target_mm range", ours=v)
            else:
                row.update(status=rr[0], ours=v, miss=rr[1], units="mm", ref=f"rule {it['target_mm']}")
        else:  # placed
            from . import cloth_reference as cr
            ref = refs.get(it["id"])
            if ctx is None:
                row.update(status="UNMEASURED", why="no placed rest")
            elif not (ref and ref.get("visible")) and not it.get("target_mm"):
                row.update(status="UNMEASURED", why="no reference reading for this item (cloth_reference.read)")
            else:
                try:
                    ours = cr.measure(ctx, gname, it)
                    c = cr.compare(it, ref if ref and ref.get("visible") else {"visible": False, "confidence": "medium"},
                                   ours, ctx)
                    if c.get("miss") is None:
                        row.update(status="UNMEASURED", why=c.get("note", "readings not comparable"))
                    else:
                        row.update(status="FAIL" if c["severity"] > 1.0 else "PASS",
                                   **{k: c[k] for k in ("ref", "ours", "miss", "units", "detail", "severity", "sets") if k in c})
                except cr.NotMeasured as e:
                    row.update(status="UNMEASURED", why=str(e))
                except Exception as e:  # noqa: BLE001 (a measure that breaks on a placed rest is unmeasured, and says so)
                    row.update(status="UNMEASURED", why=f"{type(e).__name__}: {e}")
        rows.append(row)
    return rows


def make_record(model: str, garment: str, kind, keys: dict, rows: list, waive: dict | None = None,
                warnings: list | None = None, refs: bool = False) -> dict:
    old = read_record(keys["pattern"], keys["body"]) or {}
    return {"version": GATE_VERSION, "checklist_version": checklist_version(), "model": model, "garment": garment,
            "kind": kind, "pattern": keys["pattern"], "body": keys["body"], "time": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": verdict(rows, waive), "rows": rows, "waived": dict(waive or {}), "warnings": list(warnings or []),
            "refs": bool(refs), "overrides": old.get("overrides", [])}


def pattern_gate(model: str, garment: str, spec: dict | None = None, refs=None, waive: dict | None = None,
                 sheet: bool = False, concept: str | None = None, log=print) -> dict:
    """Measure the garment's pattern on its body WITHOUT a sim and write the gate record (see the section comment).
    refs: the reference reading (cloth_reference.read's output or its saved path; targets[garment] are used); waive:
    {item id: reason} for FAIL / UNMEASURED rows accepted by name (recorded); sheet: also render the pre-sim clay sheet
    (`pattern_sheet`; run under bin/capped). Returns the record ("status", "rows", "warnings", "sheet")."""
    from . import cloth, cloth_reference as cr, garment_design, store
    spec = spec or store.load(model)
    g = spec["cloth"][garment]
    src = cloth.model_body(model, spec, g, simulate=False)
    res = cloth.build(cloth._garment_for_sim(g), src, f"{model}:{garment}", log=lambda *_: None, place_only=True)
    keys = res["gate_keys"]
    M = res["mesh"]
    light = {"V": np.asarray(res["X0"], float), "F": M["F"], "piece": M["piece"], "names": list(M["names"])}
    ctx = cr.Ctx(model, spec, {garment: light}, body=res["body"])
    kind = ctx.kind(garment)
    if isinstance(refs, (str, _Path)):
        refs = _json.loads(_Path(refs).read_text())
    targets = ((refs or {}).get("targets") or {}).get(garment) or {}
    roles = [garment_design.role_of(n) for n in M["names"]]
    torso = np.isin(np.asarray(M["piece"]), [k for k, ro in enumerate(roles) if ro not in cr.NOT_TORSO])
    nk = neckline_standoff_mm(light["V"], M["F"], res["body"].V, ctx.L["neck_base"], keep=torso)
    rows = gate_rows(res["pieces_full"], cr.items_for(kind), ctx, garment, targets, {"neckline_standoff_mm": nk},
                     garment_kind=kind or "")
    rows.append({"id": "neckline_standoff", "stage": 3, "status": "INFO", "measure": "cloth_check.neckline_standoff_mm",
                 "ours": nk, "why": "no target yet: a checklist item adopts it with \"pattern_measure\""})
    warns = option_sources(g)
    rec = make_record(model, garment, kind, keys, rows, waive, warns, bool(targets))
    if sheet:
        rec["sheet"] = str(pattern_sheet(res, gate_dir() / "sheets" / gate_key(keys["pattern"], keys["body"]),
                                         concept or (g.get("design") or {}).get("concept") or g.get("concept")))
    p = write_record(rec)
    log(f"pattern gate {model}:{garment}: {rec['status']} ({p})")
    for w in warns:
        log(f"  {w}")
    for r in rows:
        if r["status"] in ("FAIL", "UNMEASURED"):
            log(f"  {r['status']:<10} {r['id']}: {r.get('why') or ''}{r.get('ours', '')} {r.get('miss', '')}")
    return rec


def pattern_sheet(res: dict, prefix, concept: str | None = None, views=("front", "three", "side", "back"),
                  resolution: int = 700) -> _Path:
    """The assembled pre-sim garment on the body (the placed rest a sim would start from), clay, front / 3/4 / side /
    back framed ~1 m round the garment, the concept first when given -> <prefix>.png. Takes the GPU lock: run under
    /mnt/data/hifipushie/bin/capped (refused otherwise)."""
    from PIL import Image
    from . import cloth, resources
    if not _os.environ.get("HIFIPUSHIE_CAPPED"):
        raise RuntimeError("pattern_sheet renders: run it under /mnt/data/hifipushie/bin/capped (GPU lock, memory cap)")
    M, B = res["mesh"], res["body"]
    X = np.asarray(res["X0"], float)
    lo, hi = X.min(0) - 0.08, X.max(0) + 0.08
    c, half = (lo + hi) / 2, np.maximum((hi - lo) / 2, 0.5)  # (about 1 m across at least)
    objs = [{"name": "body", "V": B.V, "F": B.T, "color": "#c9b8a6"},
            {"name": "garment", "V": X, "F": M["F"], "color": "#5b7fa6"}]
    prefix = _Path(prefix)
    with resources.heavy(f"pattern sheet {prefix.name}", gb=4, gpu=True):
        pngs = cloth.render(objs, str(prefix), views=views, resolution=resolution, box=(c - half, c + half))
    ims = ([Image.open(concept).convert("RGB")] if concept and _Path(concept).exists() else []) + \
        [Image.open(p).convert("RGB") for p in pngs]
    h = max(im.height for im in ims)
    ims = [im.resize((max(1, int(im.width * h / im.height)), h)) for im in ims]
    out = Image.new("RGB", (sum(im.width for im in ims), h), "white")
    x = 0
    for im in ims:
        out.paste(im, (x, 0))
        x += im.width
    p = prefix.with_suffix(".png")
    out.save(p)
    return p
