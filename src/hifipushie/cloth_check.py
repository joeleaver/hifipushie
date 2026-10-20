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

import math

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
def seams(Bp: dict, garment_kind: str = "", ease_bands: dict | None = None) -> list:
    """Every seam's two side lengths and its ease against its kind's band. ease_bands (garment key "seam_ease"):
    {edge label: {"band": [lo, hi], "source": why}}: a seam whose side names that edge is eased by design (a two-piece
    sleeve's top sleeve eased onto the under sleeve at the elbow, 5-10 mm: dress-garrett 2026-10-19 order + seam
    lengths, Garrett's hindarm +9.2 mm read FAIL against the plain +-1.5%); its kind reads "declared"."""
    pcs = Bp["pieces"]
    rows = []
    for A, B in Bp["seams"]:
        sa, sb = _side(pcs, A), _side(pcs, B)
        la = sum(pattern.length(p) for *_, p in sa)
        lb = sum(pattern.length(p) for *_, p in sb)
        kind = _kind(Bp, A, B, garment_kind)
        lo, hi = KINDS[kind]
        names = [e for e in ([A] if isinstance(A, str) else A)] + [e for e in ([B] if isinstance(B, str) else B)]
        decl = next((v for k, v in (ease_bands or {}).items() if k != "source" and k in names), None)
        if decl is not None:
            kind = "declared"
            lo, hi = (decl["band"] if isinstance(decl, dict) else decl)
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


TRUE_DEG = 10.0  # max turn of a joined edge across a seam (pattern truing: necklines, armholes, hems, waists meet
# their seams at matching angles so the sewn edge is one smooth line; Armstrong, Patternmaking for Fashion Design,
# "truing": the neckline and armhole meet the shoulder seam at ~90 deg on front and back, blended across the joined seam)
TRUE_REACH = 0.010  # m: the edges' directions are read this far along each from the seam end


def _dir_at(P: np.ndarray, i: int, step: int, reach: float) -> np.ndarray:
    """Unit direction from outline vertex i to the point `reach` along the closed outline P going by `step` (+-1)."""
    n = len(P)
    acc, j, prev = 0.0, i, P[i]
    for _ in range(n - 1):
        j = (j + step) % n
        d = float(np.linalg.norm(P[j] - prev))
        if acc + d >= reach:
            q = prev + (P[j] - prev) * ((reach - acc) / max(d, 1e-12))
            break
        acc += d
        prev = P[j]
    else:
        q = P[j]
    v = q - P[i]
    return v / max(float(np.linalg.norm(v)), 1e-12)


def _interior_deg(P: np.ndarray, i: int, reach: float) -> float:
    """The piece's interior angle at outline vertex i, read `reach` along each edge (deg, 0..360)."""
    ccw = 0.5 * float(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])) > 0
    a, b = _dir_at(P, i, +1, reach), _dir_at(P, i, -1, reach)
    if not ccw:
        a, b = b, a
    return float(np.degrees(np.arctan2(a[0] * b[1] - a[1] * b[0], a @ b))) % 360.0


def _seam_of_segments(Bp: dict) -> dict:
    """{(piece, frozenset({i, j})): seam index} for every outline segment that a seam side covers."""
    pcs = Bp["pieces"]
    out = {}
    for si, (A, B) in enumerate(Bp["seams"]):
        for sd in (A, B):
            for _, nm, ix, _ in _side(pcs, sd):
                for a, b in zip(ix[:-1], ix[1:]):
                    out[(nm, frozenset((int(a), int(b))))] = si
    return out


def junctions(Bp: dict, reach: float = TRUE_REACH, corners=()) -> list:
    """PATTERN TRUING at every seam end: where two pieces are sewn, the edges that run on past the seam's end (a front
    and back neckline at the shoulder seam, armhole at the side seam, hems, waists, collar edges) must continue as one
    line. Per seam end: each piece's interior angle there (thA, thB) and the joined edge's turn |thA + thB - 180| (0 =
    smooth; a front + back neckline meeting the shoulder at 90 + 90 is smooth, 75 + 85 turns 20 deg: the corner Joe
    saw at Garrett's side neck, dress-garrett 2026-10-19). corners: seam-end labels that are corners by design (a
    notched collar's notch) and are reported but not failed. Only a side's single edge ends count (a chained side's
    inner junctions are other seams' ends).
    Read only where the two edges running on ARE one line (dress-garrett 2026-10-19 order + seam lengths: the round-4
    gate failed non-faults): both free (a hem, a collar's outer edge) or both in the same other seam (two necklines in
    the collar seam). A seam whose side is a CLOSED loop (a set-in sleeve's cap all round its armhole: 'under:underarm
    > ... > underarm') has no ends (it read 112 deg there); where the edges running on are in DIFFERENT seams (a
    shirt cap's end at the underarm: the sleeve seam and the side seam cross there) the end is a seam CROSSING,
    reported with "crossing" and never failed."""
    pcs = Bp["pieces"]
    cover = _seam_of_segments(Bp)
    out = []
    for A, B in Bp["seams"]:
        sa, sb = _side(pcs, A), _side(pcs, B)
        loop = lambda s_: s_[0][1] == s_[-1][1] and int(s_[0][2][0]) == int(s_[-1][2][-1])
        if loop(sa) or loop(sb):
            continue
        for end in (0, -1):
            ea, nma, ixa, _ = sa[end]
            eb, nmb, ixb, _ = sb[end]
            ia, ib = int(ixa[end]), int(ixb[end])
            if nma == nmb and ia == ib:
                continue
            # the segment running on past the seam's end on each piece, and the seam it is in (None: a free edge)
            on = []
            for nm, ix in ((nma, ixa), (nmb, ixb)):
                n = len(pcs[nm]["P"])
                i0 = int(ix[end])
                nxt = int(ix[1]) if len(ix) > 1 and end == 0 else int(ix[-2]) if len(ix) > 1 else (i0 + 1) % n
                cand = [(i0 - 1) % n, (i0 + 1) % n]
                j = cand[0] if cand[1] == nxt else cand[1]
                on.append(cover.get((nm, frozenset((i0, j)))))
            crossing = not (on[0] == on[1])
            tha = _interior_deg(pcs[nma]["P"], ia, reach)
            thb = _interior_deg(pcs[nmb]["P"], ib, reach)
            lab = f"{nma}:{_pname(pcs[nma], ia)} | {nmb}:{_pname(pcs[nmb], ib)}"
            turn = abs(tha + thb - 180.0)
            turn = min(turn, abs(turn - 360.0))
            corner = lab in corners or any(c in lab for c in corners)
            out.append({"at": lab, "seam": [A, B], "deg_a": round(tha, 1), "deg_b": round(thb, 1),
                        "turn_deg": round(turn, 1), "corner": corner, "crossing": crossing,
                        "ok": bool(turn <= TRUE_DEG or corner or crossing)})
    return out


def _pname(pc, i):
    nm = [k for k, v in pc["names"].items() if int(v) == int(i) and not k.startswith("_")]
    return nm[0] if nm else f"#{i}"


def _selftest_junctions():
    """Known answers: two rectangles sewn side to side continue their top edges straight (0 deg); a front whose
    neckline meets the shoulder at 70 deg joined to a back meeting it at 90 turns 20 deg there."""
    def pc(P, names):
        return {"P": np.asarray(P, float), "names": names, "marks": {}, "wrap": {}}
    sq = {"pieces": {"a": pc([[0, 0], [1, 0], [1, 1], [0, 1]], {"bl": 0, "br": 1, "tr": 2, "tl": 3}),
                     "b": pc([[1, 0], [2, 0], [2, 1], [1, 1]], {"bl": 0, "br": 1, "tr": 2, "tl": 3})},
          "seams": [["a:br>tr", "b:bl>tl"]]}
    r = junctions(sq, reach=0.1)
    assert all(abs(x["turn_deg"]) < 1e-6 for x in r), r
    # a shoulder seam along x from (0, 0) to (0.12, 0): back below (neck edge going -y at 90), front above, its neck
    # edge leaving the seam at 70 deg (interior)
    a70 = np.radians(70.0)
    fr = pc([[0.12, 0.0], [0.0, 0.0], [0.1 * np.cos(np.pi - a70) * -1 * -1, 0.0], [0.0, 0.0]], {})
    F = np.array([[0.0, 0.0], [0.12, 0.0], [0.12, 0.2], [0.0 + 0.2 * np.cos(a70), 0.2 * np.sin(a70)]])
    Bk = np.array([[0.0, 0.0], [0.0, -0.2], [0.12, -0.2], [0.12, 0.0]])
    sh = {"pieces": {"front": pc(F, {"hps": 0, "shoulder": 1}), "back": pc(Bk, {"hps": 0, "shoulder": 3})},
          "seams": [["front:hps>shoulder", "back:hps>shoulder"]]}
    r = junctions(sh, reach=0.05)
    h = next(x for x in r if "hps" in x["at"])
    assert abs(h["deg_a"] - 70.0) < 0.5 and abs(h["deg_b"] - 90.0) < 0.5 and abs(h["turn_deg"] - 20.0) < 0.5, h
    del fr


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
# be read from the pattern ASSEMBLED ON THE VIRTUAL DRESS FORM (pattern_form.on_form: placed, neck points on the body,
# seams closed, folds turned, over its under garment; graded fine mesh) plus the pattern's own rows (seam ease / notches). Each row comes back
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


# ---------------------------------------------------------------- flat first (2026-10-19 dress-garrett muslin 1)
# GATE ON WHAT'S PROVEN (codified C29): the virtual dress form is a reader like any other and has not passed its own
# validation, so nothing read on it blocks or passes a pattern yet. The gate blocks on the FLAT checks: seams (lengths,
# ease, notches), truing, the flat pattern stage (ease vs the body by girth, design evidence), the collar draft's
# stand / fall, the notch read flat. Form readings (placed items, worn items, form strain) are INFO with their reading
# and "form_status" kept. Set FORM_VALIDATED True only with the form's validation record (a KAT on a real arm segment:
# docs/state/dress_garrett.md) in the same commit.
FORM_VALIDATED = False  # (a manual override only; the gate reads form_validated(): this OR pattern_form's record)


def form_validated() -> bool:
    """The gate's form switch (virtual fit validation 2, 2026-10-19): True when FORM_VALIDATED is set, or when
    pattern_form.form_validated() is (its VALIDATED flag AND its validation record, every row passing). The gate reads
    this, never the constant alone, so a passing record + flag turns the form rows from INFO into gating rows."""
    from . import pattern_form as _pf
    return bool(FORM_VALIDATED or _pf.form_validated())
FORM_FAULTS = ("dress-garrett 2026-10-19 form sleeves: its first relax flattens a two-piece sleeve into a lens (biceps "
               "142 x 156 -> 72 x 159 mm), and it over-reads strain (jacket p99 49 % on a block whose drape reads in band)")
FLAT_MEASURES = ("collar_stand_cb_mm", "collar_fall_minus_stand_mm", "notch_flat")
SPEC_READ = ("detail_choice", "has_belt", "over", "fabric", "colour")  # placed measures that read the spec, not the form


def _arc_len_resample(L: np.ndarray, n: int) -> np.ndarray:
    L = np.asarray(L, float)
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(L, axis=0), axis=1))]
    t = np.linspace(0.0, s[-1], n)
    return np.c_[np.interp(t, s, L[:, 0]), np.interp(t, s, L[:, 1])]


def _side_arc(pcs: dict, side) -> np.ndarray:
    parts = []
    for e in ([side] if isinstance(side, str) else side):
        nm, arc = e.split(":", 1)
        parts.append(np.asarray(pcs[nm]["P"], float)[pattern.arc_indices(pcs[nm], arc)])
    return np.concatenate(parts, 0)


def _fall_fold_at(Bp: dict) -> float:
    """The two-piece collar fall's fold line, m above its seam on the stand (its fold entry's edge offset, else the
    wrap turn's "at"; 0 without either)."""
    for f in Bp.get("folds") or []:
        ln = f.get("line")
        if f.get("piece") == "collar" and isinstance(ln, dict) and "cbLow" in str(ln.get("edge", "")):
            return float(ln.get("offset", 0.0))
    c = (Bp.get("pieces") or {}).get("collar") or {}
    return float(((c.get("wrap") or {}).get("turn") or {}).get("at", 0.0))


def collar_draft_two_piece(Bp: dict) -> dict | None:
    """collar_draft for a TWO-PIECE collar (pattern_jacket.op_collar_two_piece: a "stand" cb..cbTop sewn by its neck
    edge, a fall "collar" cbLow..cbOuter sewn to the stand's top, turned about its fold line `fold_at` above that seam).
    Worn, the roll line sits at stand + fold_at over the neck seam; the fall below the roll line is fall - fold_at.
    (fit round 2: the readers knew only the one-piece collar, so the gate rows collar_stand / collar_fall read
    UNMEASURED on the v2 draft.)"""
    pcs = Bp.get("pieces") or {}
    s, c = pcs.get("stand"), pcs.get("collar")
    if s is None or c is None or not {"cb", "cbTop", "cf", "cfTop"} <= set(s["names"]) or \
            not {"cbLow", "cbOuter"} <= set(c["names"]):
        return None
    P, Q = np.asarray(s["P"], float), np.asarray(c["P"], float)
    fat = _fall_fold_at(Bp)
    st = float(np.linalg.norm(P[s["names"]["cbTop"]] - P[s["names"]["cb"]]))
    se = float(np.linalg.norm(P[s["names"]["cfTop"]] - P[s["names"]["cf"]]))
    fa = float(np.linalg.norm(Q[c["names"]["cbOuter"]] - Q[c["names"]["cbLow"]]))
    # the fall's height spent in the turn of cloth (pattern_jacket.turn_stack: the draft's own record, else the default
    # fabrics) is not seen: the worn fall is the piece less the fold's rise and the turn
    tm = (((Bp.get("draft") or {}).get("meta") or {}).get("collar_two_piece") or {}).get("turn")
    if not tm:
        from . import pattern_jacket
        tm = pattern_jacket.turn_stack()
    stand, fall = st + fat, fa - fat - float(tm["depth_mm"]) / 1000
    return {"stand_cb_mm": round(stand * 1000, 1), "stand_end_mm": round((se + fat) * 1000, 1),
            "tapers": bool(se < st), "collar_cb_mm": round((st + fa) * 1000, 1), "fall_cb_mm": round(fall * 1000, 1),
            "fall_minus_stand_mm": round((fall - stand) * 1000, 1), "two_piece": True,
            "fold_at_mm": round(fat * 1000, 1)}


def collar_draft(Bp: dict) -> dict | None:
    """A tailored (notched) collar's draft, flat: the stand (the roll line's distance from the neck edge) at CB and at
    the roll line's last point (where it meets the neck edge: ~0, the collar all fall past it), whether it tapers
    without a rise, the whole collar at CB (neck edge -> outer edge) and the fall (whole - stand). None: no such collar."""
    c = (Bp.get("pieces") or {}).get("collar")
    two = collar_draft_two_piece(Bp)
    if two:
        return two
    if c is None or "cbTop" not in c["names"] or not ((c.get("wrap") or {}).get("turn") or {}).get("line"):
        return None
    L = np.asarray(c["wrap"]["turn"]["line"], float)[:-1]  # (without the run-on into the front)
    L = L[L[:, 0] >= -1e-9]
    L = L[np.argsort(L[:, 0])]
    E = _arc_len_resample(np.asarray(c["P"], float)[pattern.arc_indices(c, "cb>shoulderNotch>cf")], 400)
    h = np.array([np.linalg.norm(E - q, axis=1).min() for q in L])
    whole = float(np.linalg.norm(c["P"][c["names"]["cbTop"]] - c["P"][c["names"]["cb"]]))
    return {"stand_cb_mm": round(h[0] * 1000, 1), "stand_end_mm": round(h[-1] * 1000, 1),
            "tapers": bool(np.all(np.diff(h) < 0.0005)), "collar_cb_mm": round(whole * 1000, 1),
            "fall_cb_mm": round((whole - h[0]) * 1000, 1), "fall_minus_stand_mm": round((whole - 2 * h[0]) * 1000, 1)}


def _rigid_onto(a: np.ndarray, b: np.ndarray):
    """The 2D rigid map taking points a onto their partners b (least squares), and its worst residual."""
    ca, cb_ = a.mean(0), b.mean(0)
    U, _, Vt = np.linalg.svd((a - ca).T @ (b - cb_))
    R = (U @ Vt).T
    if np.linalg.det(R) < 0:
        Vt[-1] *= -1
        R = (U @ Vt).T

    def T(q):
        return (np.asarray(q, float) - ca) @ R.T + cb_
    return T, float(np.linalg.norm(T(a) - b, axis=1).max())


def _notch_flat_two_piece(Bp: dict, reach: float) -> dict | None:
    """notch_flat for a two-piece collar: the fall's end carried onto the stand by their seam (fall low edge on the
    stand's top), then the stand's end into the front by its neck seam, each a rigid fit within `reach` of the end."""
    pcs = Bp["pieces"]
    s, c = pcs["stand"], pcs["collar"]
    n = 600
    out = {}
    for sfx in ("", ".m"):
        if "cf" + sfx not in s["names"] or "endOuter" + sfx not in c["names"]:
            continue
        cf = np.asarray(s["P"][s["names"]["cf" + sfx]], float)
        T1 = fr = None
        for A, B in Bp["seams"]:
            if not (isinstance(A, str) and A.startswith("stand:")) or A.split(">")[-1] != "cf" + sfx:
                continue
            fr = next((e.split(":")[0] for e in ([B] if isinstance(B, str) else B) if e.startswith("front.")), None)
            if fr is None or "lapelPoint" not in pcs[fr]["names"]:
                continue
            Ca, Fb = _arc_len_resample(_side_arc(pcs, A), n), _arc_len_resample(_side_arc(pcs, B), n)
            use = np.linalg.norm(Ca - cf, axis=1) < reach
            if use.sum() >= 5:
                T1, fit1 = _rigid_onto(Ca[use], Fb[use])
                break
        if T1 is None:
            continue
        ft = np.asarray(s["P"][s["names"]["cfTop" + sfx]], float)
        T2 = None
        for A, B in Bp["seams"]:
            if not (isinstance(A, str) and A.startswith("collar:") and isinstance(B, str) and B.startswith("stand:")):
                continue
            Ca, Sb = _arc_len_resample(_side_arc(pcs, A), n), _arc_len_resample(_side_arc(pcs, B), n)
            use = np.linalg.norm(Sb - ft, axis=1) < reach
            if use.sum() >= 5 and np.linalg.norm(Sb[use][-1] - ft) < reach and \
                    np.linalg.norm(Ca[use] - c["P"][c["names"]["endLow" + sfx]], axis=1).min() < reach:
                T2, fit2 = _rigid_onto(Ca[use], Sb[use])
                break
        if T2 is None:
            continue
        fp = pcs[fr]
        lp, cn = np.asarray(fp["P"][fp["names"]["lapelPoint"]], float), np.asarray(fp["P"][fp["names"]["cfNeck"]], float)
        eo = T1(T2(c["P"][c["names"]["endOuter" + sfx]]))
        u, v = lp - cn, eo - cn
        ang = math.degrees(math.acos(float(np.clip(u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12), -1, 1))))
        out[fr] = {"gap_mm": round(float(np.linalg.norm(lp - eo)) * 1000, 1), "angle_deg": round(ang, 1),
                   "fit_mm": round(max(fit1, fit2) * 1000, 1), "two_piece": True}
    return out or None


def notch_flat(Bp: dict, reach: float = 0.11) -> dict | None:
    """The notch as DRAFTED (dress-garrett notch2d.py, without a mesh): the collar's end carried into the front's
    pattern by its own neck seam (both sides sewn by fraction of their length; a rigid 2D fit over the seam within
    `reach` of the collar's end, as the worn collar lies with the lapel past the roll line), then per side the gap
    lapel point -> collar end (outer) and the angle between them at the front's neck end (cfNeck). The lapel and the
    collar end turn together about the roll line, so these are the worn notch's."""
    pcs = Bp.get("pieces") or {}
    c = pcs.get("collar")
    if c is None or "endOuter" not in c["names"]:
        return None
    if "stand" in pcs and "endNeck" not in c["names"]:
        return _notch_flat_two_piece(Bp, reach)
    out = {}
    for A, B in Bp["seams"]:
        if not (isinstance(A, str) and A.startswith("collar:")):
            continue
        sfx = ".m" if ".m" in A else ""
        fr = next((e.split(":")[0] for e in ([B] if isinstance(B, str) else B) if e.startswith("front.")), None)
        if fr is None or "lapelPoint" not in pcs[fr]["names"]:
            continue
        n = 600
        Ca, Fb = _arc_len_resample(_side_arc(pcs, A), n), _arc_len_resample(_side_arc(pcs, B), n)
        en = np.asarray(c["P"][c["names"]["endNeck" + sfx]], float)
        use = np.linalg.norm(Ca - en, axis=1) < reach
        if use.sum() < 5:
            continue
        a, b = Ca[use], Fb[use]
        ca, cb_ = a.mean(0), b.mean(0)
        U, _, Vt = np.linalg.svd((a - ca).T @ (b - cb_))
        R = (U @ Vt).T
        if np.linalg.det(R) < 0:
            Vt[-1] *= -1
            R = (U @ Vt).T

        def T(q, ca=ca, cb_=cb_, R=R):
            return (np.asarray(q, float) - ca) @ R.T + cb_
        fit = float(np.linalg.norm(T(a) - b, axis=1).max())
        fp = pcs[fr]
        lp, cn = np.asarray(fp["P"][fp["names"]["lapelPoint"]], float), np.asarray(fp["P"][fp["names"]["cfNeck"]], float)
        eo = T(c["P"][c["names"]["endOuter" + sfx]])
        u, v = lp - cn, eo - cn
        ang = math.degrees(math.acos(float(np.clip(u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12), -1, 1))))
        out[fr] = {"gap_mm": round(float(np.linalg.norm(lp - eo)) * 1000, 1), "angle_deg": round(ang, 1),
                   "fit_mm": round(fit * 1000, 1)}
    return out or None


# NOTCH STEP (fit round 4, 2026-10-19). Round 3's notch passed notch_gap 26.5 mm / angle 61 deg (3D distances between
# named points) while no reviewer could see a notch in any view: the points were apart, but seen from the front the
# collar's fall lay over the lapel and the outline ran on without a step. What the eye reads is the WEDGE: in the front
# view the collar end and the lapel point meet at an angle with something ELSE showing between them (the concept: a
# dark V ~18 mm deep, ~3-4 mm open at its mouth, both sides). Measured on a front-view ID raster of the top layers.
NOTCH_PX = 0.0005  # m per raster pixel
NOTCH_REACH = 0.04  # m: how far the wedge is followed from the mouth (P -> C)
NOTCH_STEP = 0.002  # m: a pixel is part of the gap only if what shows there lies this far behind the nearest top layer
# (a step the eye reads as an edge with its shadow; the same cloth running on smoothly from the collar into the lapel,
# round 3's fall roll, is no notch however the named points lie)


def notch_step(V: np.ndarray, F: np.ndarray, top_a: np.ndarray, top_b: np.ndarray, P, C, G, view=(0.0, -1.0, 0.0),
               px: float = NOTCH_PX, reach: float = NOTCH_REACH) -> dict:
    """The notch as the front view shows it. V, F: every surface that can be seen there (garment, under garments, body);
    top_a / top_b: bool per face, the two top layers that make the notch (the collar's fall, the lapel's turned flap);
    P, C: the lapel point and the collar end (3D), the notch's mouth; G: the gorge end of the collar (the wedge's apex
    side). An orthographic z-buffer of F from `view` (the camera looks along
    -view... i.e. sits at +view: front = (0, -1, 0), the creature faces -Y) labels each pixel a / b / other.
    A GAP pixel shows nothing, or a surface NOTCH_STEP or more behind the nearest top-layer pixel (an edge with depth).
    Returns {"open_mm": the length of the mouth P -> C over gap pixels, "mouth_mm": its projected length, "depth_mm":
    how far the gap pixels joined to the mouth reach in from P -> C toward the gorge G, square to it (the wedge),
    "a_b_touch": mouth samples where a and b pixels meet directly}."""
    V = np.asarray(V, float)
    F = np.asarray(F)
    d = np.asarray(view, float)
    d /= np.linalg.norm(d)
    up = np.array([0.0, 0.0, 1.0])
    ex = np.cross(up, d)
    ex /= np.linalg.norm(ex)
    ey = np.cross(d, ex)
    pr = lambda X: np.c_[np.asarray(X, float) @ ex, np.asarray(X, float) @ ey]
    dep = V @ d  # (larger = nearer the camera at +d)
    p2, c2 = pr(P[None])[0], pr(C[None])[0]
    lo = np.minimum(p2, c2) - reach
    hi = np.maximum(p2, c2) + reach
    W, H = [int(math.ceil(v)) + 1 for v in (hi - lo) / px]
    Q = (pr(V) - lo) / px
    zb = np.full((H, W), -np.inf)
    lab = np.zeros((H, W), np.int8)  # 0 nothing (background), 1 other, 2 a, 3 b
    tl = np.where(np.asarray(top_a), 2, np.where(np.asarray(top_b), 3, 1)).astype(np.int8)
    T = Q[F]
    inside = (T.max(1) >= 0).all(1) & (T[:, :, 0].min(1) < W) & (T[:, :, 1].min(1) < H)
    for f in np.where(inside)[0]:
        t = T[f]
        x0, y0 = np.floor(t.min(0)).astype(int)
        x1, y1 = np.ceil(t.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        a, b, c = t
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l1 = ((b[1] - c[1]) * (gx - c[0]) + (c[0] - b[0]) * (gy - c[1])) / den
        l2 = ((c[1] - a[1]) * (gx - c[0]) + (a[0] - c[0]) * (gy - c[1])) / den
        l3 = 1 - l1 - l2
        m = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        if not m.any():
            continue
        z = l1 * dep[F[f, 0]] + l2 * dep[F[f, 1]] + l3 * dep[F[f, 2]]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        w = m & (z > sub)
        sub[w] = z[w]
        lab[y0:y1 + 1, x0:x1 + 1][w] = tl[f]
    # a GAP pixel: nothing there, or a surface at least NOTCH_STEP behind the nearest top-layer pixel
    from scipy import ndimage
    top = lab >= 2
    if top.any():
        _, (iy, ix_) = ndimage.distance_transform_edt(~top, return_indices=True)
        behind = zb[iy, ix_] - zb
    else:
        behind = np.full(zb.shape, np.inf)
    gap = (lab == 0) | ((lab == 1) & (behind >= NOTCH_STEP))
    # along the mouth P -> C
    a2, c2_ = (p2 - lo) / px, (c2 - lo) / px
    L = float(np.linalg.norm(c2_ - a2))
    n = max(int(L * 2), 2)
    S = a2[None] + np.linspace(0, 1, n)[:, None] * (c2_ - a2)[None]
    ix = np.clip(S.astype(int), 0, [W - 1, H - 1])
    ls = lab[ix[:, 1], ix[:, 0]]
    step = L * px / max(n - 1, 1)
    other = gap[ix[:, 1], ix[:, 0]]
    out = {"open_mm": round(float(other.sum() * step) * 1000, 1), "mouth_mm": round(L * px * 1000, 1)}
    # touching: a sample whose neighbour along the mouth is the other top layer (a ran straight into b)
    tch = (ls[1:] >= 2) & (ls[:-1] >= 2) & (ls[1:] != ls[:-1])
    out["a_b_touch"] = int(tch.sum())
    # the wedge: OTHER pixels connected to the mouth's other samples, on the side of P -> C where the two layers are
    # (away from the open background), within the mouth's span and `reach` of it
    if out["open_mm"] < 1.0:  # (a closed mouth: no wedge reads, whatever lies behind)
        out["depth_mm"] = 0.0
        return out
    cc, _ = ndimage.label(gap)
    seeds = {int(cc[y, x]) for (x, y), o in zip(ix, other) if o}
    seeds.discard(0)
    if not seeds:
        out["depth_mm"] = 0.0
        return out
    if L < 1.0:  # (the corners on one pixel: no mouth)
        out["depth_mm"] = 0.0
        return out
    yy, xx = np.nonzero(np.isin(cc, list(seeds)))
    R_ = np.c_[xx + 0.5, yy + 0.5] - a2
    u = (c2_ - a2) / max(L, 1e-9)
    along = R_ @ u
    across = R_ @ np.array([-u[1], u[0]])
    ok = (along >= 0) & (along <= L) & (np.abs(across) * px <= reach)
    if not ok.any():
        out["depth_mm"] = 0.0
        return out
    # the wedge's side: the gorge's (the apex)
    g2 = (pr(np.asarray(G, float)[None])[0] - lo) / px
    side = float(np.sign((g2 - a2) @ np.array([-u[1], u[0]]))) or 1.0
    dep_ = across[ok] * side
    out["depth_mm"] = round(float(max(dep_.max(), 0.0)) * px * 1000, 1)
    return out


def _selftest_notch_step():
    """A known answer: two flat top layers in the plane y = 0 seen from the front, a (x < 0) and b (x > 0) meeting at
    a V notch 20 mm deep, 6 mm open at its mouth (y = 0 plane, z up), over a backing sheet 5 mm behind: open ~6 mm,
    depth ~20 mm. The same layers closed (b's edge on a's) read open 0, depth 0."""
    def quad(x0, x1, z0, z1, y):
        v = np.array([[x0, y, z0], [x1, y, z0], [x1, y, z1], [x0, y, z1]], float)
        return v, np.array([[0, 1, 2], [0, 2, 3]])
    out = []
    for gap in (0.006, 0.0):
        Vs, Fs, la, lb = [], [], [], []
        # the wedge: a and b are polygons fanned to a common apex 20 mm below the mouth; build them as triangles
        apex = np.array([0.0, 0.0, -0.020])
        A = np.array([[-0.05, 0, 0.0], [-gap / 2, 0, 0.0], apex, [-0.05, 0, -0.04], [0.0, 0, -0.04]])
        Vs.append(A)
        Fs.append(np.array([[0, 1, 2], [0, 2, 3], [3, 2, 4]]))
        la += [True] * 3
        lb += [False] * 3
        B_ = np.array([[gap / 2, 0, 0.0], [0.05, 0, 0.0], [0.05, 0, -0.04], apex, [0.0, 0, -0.04]])
        Vs.append(B_)
        Fs.append(np.array([[0, 1, 2], [0, 2, 3], [3, 2, 4]]) + 5)
        la += [False] * 3
        lb += [True] * 3
        bv, bf = quad(-0.06, 0.06, -0.06, 0.03, 0.005)
        Vs.append(bv)
        Fs.append(bf + 10)
        la += [False] * 2
        lb += [False] * 2
        V = np.concatenate(Vs)
        F = np.concatenate(Fs)
        r = notch_step(V, F, np.array(la), np.array(lb), np.array([-gap / 2, 0, 0.0]), np.array([gap / 2, 0, 0.0]),
                       np.array([0.0, 0, -0.03]))
        out.append(r)
    o, c = out
    assert abs(o["open_mm"] - 6.0) < 1.5 and abs(o["depth_mm"] - 20.0) < 3.0, o  # (the apex is sub-pixel: ~18)
    assert c["open_mm"] < 1.0 and c["depth_mm"] < 1.0, c
    return out


def flat_readings(Bp: dict) -> dict:
    """{FLAT_MEASURES name: reading} of a flat draft (missing: not applicable to this draft)."""
    r = {}
    cd = collar_draft(Bp)
    if cd:
        r["collar_stand_cb_mm"] = dict(cd, value=cd["stand_cb_mm"])
        r["collar_fall_minus_stand_mm"] = dict(cd, value=cd["fall_minus_stand_mm"])
    nf = notch_flat(Bp)
    if nf:
        r["notch_flat"] = nf
    return r


def flat_row(it: dict, rd) -> dict:
    """A FLAT_MEASURES item's status: flat_target (else target_mm) [lo, hi] +- flat_tolerance on reading["value"], or
    for the notch {"gap_mm": [..], "angle_deg": [..]} on every side. No reading: UNMEASURED (blocks)."""
    if not rd:
        return {"status": "UNMEASURED", "why": f"{it['flat_measure']}: not read on this draft"}
    t, tol = it.get("flat_target") or it.get("target_mm"), float(it.get("flat_tolerance", 0) or 0)

    def ok(v, rng):
        return float(rng[0]) - tol <= float(v) <= float(rng[1]) + tol
    if it["flat_measure"] == "notch_flat":
        bad = [f"{sd} {k} {v[k]}" for sd, v in rd.items() for k in ("gap_mm", "angle_deg") if not ok(v[k], t[k])]
    else:
        bad = [] if ok(rd["value"], t) else [f"{rd['value']} mm"]
    return {"status": "FAIL" if bad else "PASS", "ours": rd, "ref": t, "read_on": "flat draft",
            **({"miss": "; ".join(bad)} if bad else {})}


def classify(it: dict) -> str:
    """How the gate treats a checklist item: "pattern" (a PATTERN_MEASURES measure), "flat" (a FLAT_MEASURES reading of
    the flat draft), "worn" (read only on the garment assembled / worn: the dress form or the drape; INFO until the form
    is validated), "later" (a later stage's item, e.g. wear: INFO), "placed" (a cloth_reference measure read on the
    placed rest), "sim" (judged after the sim) or "unmeasured" (anything else: it blocks)."""
    if it.get("pattern_measure") in PATTERN_MEASURES:
        return "pattern"
    if it.get("flat_measure") in FLAT_MEASURES:
        return "flat"
    if it.get("gate") in ("worn", "later"):
        return it["gate"]
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
              garment_kind: str = "", corners=(), ease_bands: dict | None = None, form_ok: bool = True,
              flat: dict | None = None, drape: dict | None = None) -> list:
    """The gate's rows: the pattern's seam row, then one row per checklist item. ctx: a cloth_reference.Ctx holding the
    placed rest as gname's result (None: "placed" items are UNMEASURED); refs: the garment's reference targets {item id:
    reading}; extra: {PATTERN_MEASURES name: its result dict} already read on this garment. form_ok: the dress form
    passed its own validation (FORM_VALIDATED); when False every row read on the form (placed items, worn items) is INFO
    with its reading and "form_status" kept, never blocking and never a pass. flat: {FLAT_MEASURES name: reading}
    (flat_readings). drape: a garment's "drape_readings" {"source", "rows": {item id: {status, ours, ref}}}: an item
    read on the last VALIDATED drape of the same block, which blocks in place of the form's reading."""
    rows = []
    sm = seams(Bp, garment_kind, ease_bands)
    # ease the DRAFT declared on a seam (Bp seam_notes: a two-piece sleeve's cap ease, a dart released into gathers),
    # read as the flat pattern stage reads it (cloth_workflow.seam_rows): the gate and the stage must agree (muslin 1:
    # the jacket cap read "+3.0% outside 0..3%" here and "in its declared +1.8..+4.2%" there)
    for r in sm:
        n_ = (Bp.get("seam_notes") or {}).get(_json.dumps([r["a"], r["b"]]))
        if n_ and not (ease_bands and r.get("declared")):
            lo, hi = n_["ease"]
            r["band"] = (min(lo, -hi) if lo >= 0 and r["ease"] < 0 else lo, hi)
            r["kind"], r["why"] = "declared", n_.get("why")
            r["ok"] = lo - 1e-6 <= abs(r["ease"]) <= hi + 1e-6 or lo - 1e-6 <= r["ease"] <= hi + 1e-6
    bad = [r for r in sm if not r["ok"] or r["notches_off"]]
    rows.append({"id": "seams", "stage": 2, "status": "FAIL" if bad else "PASS", "measure": "cloth_check.seams",
                 "ours": f"{len(sm)} seams, {len(bad)} outside their ease band or with notches off",
                 "detail": [f"{r['a']} || {r['b']}: ease {100 * r['ease']:+.1f}% band {r['band']} notches {r['notches_off']}"
                            for r in bad][:12]})
    # pattern truing: every seam end's joined edge turns <= TRUE_DEG (garment key "truing_corners": seam ends that are
    # corners by design, e.g. a notched collar's notch, a band's extension past CF; reported, not failed)
    jn = junctions(Bp, corners=tuple(corners or ()))
    badj = [r for r in jn if not r["ok"]]
    rows.append({"id": "truing", "stage": 2, "status": "FAIL" if badj else "PASS", "measure": "cloth_check.junctions",
                 "ours": f"{len(jn)} seam ends, {len(badj)} turn > {TRUE_DEG:.0f} deg",
                 "detail": [f"{r['at']}: {r['deg_a']} + {r['deg_b']} -> turn {r['turn_deg']}" for r in badj][:16]})
    extra, refs = extra or {}, refs or {}
    for it in items:
        cl = classify(it)
        row = {"id": it["id"], "stage": it["stage"], "measure": it.get("pattern_measure") or it.get("measure")}
        if cl == "sim":
            row.update(status="SIM", why="judged after the sim (drape, folds, closures, the worn tells)")
        elif cl == "later":
            row.update(status="INFO", why=f"a later stage's item (stage {it.get('stage')}): not a pattern check")
        elif cl == "worn":
            row.update(status="INFO" if not form_ok else "UNMEASURED", form_status="UNMEASURED",
                       why=("read on the assembled / worn garment only (the dress form or the drape): INFO while the "
                            "form is not validated: " + FORM_FAULTS) if not form_ok else f"no worn measure: {it.get('measure')}")
        elif cl == "flat":
            row.update(flat_row(it, (flat or {}).get(it["flat_measure"])))
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
        elif drape and it["id"] in (drape.get("rows") or {}):  # placed, read on the last validated drape
            d_ = drape["rows"][it["id"]]
            row.update(status=d_["status"], ours=d_.get("ours"), ref=d_.get("ref"), read_on="validated drape",
                       why=drape.get("source", ""))
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
            if not form_ok and ctx is not None and it.get("measure") not in SPEC_READ:
                # read on the dress form, which is not validated: shown, not judged (design choices read the spec)
                row.update(form_status=row["status"], status="INFO",
                           why=f"read on the dress form (not validated: {FORM_FAULTS}) {row.get('why', '')}".strip())
        rows.append(row)
    return rows


def make_record(model: str, garment: str, kind, keys: dict, rows: list, waive: dict | None = None,
                warnings: list | None = None, refs: bool = False) -> dict:
    old = read_record(keys["pattern"], keys["body"]) or {}
    return {"version": GATE_VERSION, "checklist_version": checklist_version(), "model": model, "garment": garment,
            "kind": kind, "pattern": keys["pattern"], "body": keys["body"], "time": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": verdict(rows, waive), "rows": rows, "waived": dict(waive or {}), "warnings": list(warnings or []),
            "refs": bool(refs), "overrides": old.get("overrides", [])}


FORM_STRAIN_P99 = 0.06
FORM_STRAIN_SOURCE = ("a woven wool suiting worn with ease is near its rest length: its extension at 500 gf/cm (KES-FB1 "
                      "EMT) is ~3-8 % (Kawabata & Niwa, the KES tailorability charts for men's suiting); a pattern with "
                      "its ease, on the form, should not read more than the low end of that (dress-garrett 2026-10-19)")
FORM_STRAIN_SKIP = ("collar", "collar_stand", "collar_fall")  # made pieces: their roll is the collar stage's own item


def form_strain_rows(res: dict, roles: list, g: dict) -> list:
    """Gate rows: the garment's face strain on the form (diag_render.face_strain, flat pattern -> assembled) p50 / p99
    over its body pieces (made collar pieces left to the collar stage), FAIL over FORM_STRAIN_P99 (garment key
    "form_strain_p99" + "form_strain_source" to state another); and the under garment's faces through it
    (garment_game.pierce_faces), INFO."""
    from . import diag_render, garment_game
    M = res["mesh"]
    F, piece = np.asarray(M["F"]), np.asarray(M["piece"])
    s = diag_render.face_strain(np.asarray(res["A"], float), F, np.asarray(M["uv"], float))
    keep = ~np.isin(piece[F[:, 0]], [k for k, ro in enumerate(roles) if ro in FORM_STRAIN_SKIP])
    lim = float(g.get("form_strain_p99", FORM_STRAIN_P99))
    p50, p99 = float(np.percentile(s[keep], 50)), float(np.percentile(s[keep], 99))
    worst = {}
    for k, nm in enumerate(M["names"]):
        m = keep & (piece[F[:, 0]] == k)
        if m.sum() > 10:
            worst[nm] = round(float(np.percentile(s[m], 99)) * 100, 1)
    rows = [{"id": "form_strain", "stage": 3, "status": "PASS" if p99 <= lim else "FAIL",
             "measure": "diag_render.face_strain p99 (body pieces)", "ours": {"p50_pct": round(p50 * 100, 2),
             "p99_pct": round(p99 * 100, 2), "per_piece_p99": worst}, "ref": f"<= {lim * 100:.0f}%",
             "why": g.get("form_strain_source", FORM_STRAIN_SOURCE)}]
    und = res.get("form_under")
    if und is not None:
        n = garment_game.pierce_faces(np.asarray(und["A"], float), np.asarray(und["mesh"]["F"]),
                                      np.asarray(res["A"], float), F)
        rows.append({"id": "under_pierce", "stage": 3, "status": "INFO", "measure": "garment_game.pierce_faces",
                     "ours": n, "why": "under-garment faces crossing this one on the form"})
    return rows


def flat_pattern_row(model: str, garment: str, spec: dict) -> dict:
    """The flat pattern stage (cloth_workflow.stage_pattern, no image) as one blocking row: ease vs the body by girth in
    the kind's fit band (cloth.sizing, seam to seam), every piece sewn, the design's choices evidenced in the pieces,
    the draft's own "!!" warnings. Its "fail" lines are the row's detail."""
    from . import cloth_workflow
    o = cloth_workflow.stage_pattern(cloth_workflow.Ctx(model, garment, spec), image=False)
    ease = [ln for ln in o["info"] + o["fail"] if ln.startswith("ease at") or ln.startswith("dimensions")]
    return {"id": "flat_pattern", "stage": 2, "status": "FAIL" if o["fail"] else "PASS",
            "measure": "cloth_workflow.stage_pattern (flat: ease by girth, pieces sewn, design evidence)",
            "ours": {"fail": o["fail"][:16], "warn": o["warn"][:8], "ease": ease[:8]}, "read_on": "flat draft"}


def tailor_rows_for(Bp: dict, kind, g: dict) -> list:
    """The tailor's-rule rows (pattern_jacket.tailor_rows: docs/notes/tailoring_principles.md R<n>) for a jacket / coat
    drafted by us (its draft carries the tape); [] otherwise. Button size: the closure's "size" (m) or 20 mm."""
    if (kind or "") not in ("jacket", "coat", "blazer"):
        return []
    tape = ((Bp.get("draft") or {}).get("measurements")) or {}
    if not tape.get("neck"):
        return []
    from . import pattern_jacket
    size = next((float(c["size"]) for c in (Bp.get("closures") or []) if c.get("size")), 0.020)
    return pattern_jacket.tailor_rows(Bp, tape, g, button_mm=size * 1000)


def pattern_gate(model: str, garment: str, spec: dict | None = None, refs=None, waive: dict | None = None,
                 sheet: bool = False, concept: str | None = None, log=print, keep: dict | None = None) -> dict:
    """Measure the garment's pattern on its body WITHOUT a sim and write the gate record (see the section comment).
    keep: a dict that receives the build on the dress form ("res": pattern_form.on_form's result) for the caller's
    sheets (the MCP pattern_check tool).
    refs: the reference reading (cloth_reference.read's output or its saved path; targets[garment] are used); waive:
    {item id: reason} for FAIL / UNMEASURED rows accepted by name (recorded); sheet: also render the pre-sim clay sheet
    (`pattern_sheet`; run under bin/capped). Returns the record ("status", "rows", "warnings", "sheet")."""
    from . import cloth_reference as cr, garment_design, pattern_form, store
    spec = spec or store.load(model)
    g = spec["cloth"][garment]
    # placed AND assembled on the virtual dress form (pattern_form.on_form: neck points on the body's, seams closed,
    # folds turned on edge rows, over its under garment); the placed start alone put the neck point ~30 mm out
    res = pattern_form.on_form(model, garment, spec)
    keys = res["gate_keys"]
    if keep is not None:
        keep["res"] = res
    M = res["mesh"]
    light = {"V": np.asarray(res["A"], float), "F": M["F"], "piece": M["piece"], "names": list(M["names"])}
    ctx = cr.Ctx(model, spec, {garment: light}, body=res["body"])
    kind = ctx.kind(garment)
    if isinstance(refs, (str, _Path)):
        refs = _json.loads(_Path(refs).read_text())
    targets = ((refs or {}).get("targets") or {}).get(garment) or {}
    roles = [garment_design.role_of(n) for n in M["names"]]
    torso = np.isin(np.asarray(M["piece"]), [k for k, ro in enumerate(roles) if ro not in cr.NOT_TORSO])
    nk = neckline_standoff_mm(light["V"], M["F"], res["body"].V, ctx.L["neck_base"], keep=torso)
    form_ok = form_validated()
    rows = gate_rows(res["pieces_full"], cr.items_for(kind), ctx, garment, targets, {"neckline_standoff_mm": nk},
                     garment_kind=kind or "", corners=g.get("truing_corners") or (), ease_bands=g.get("seam_ease"),
                     form_ok=form_ok, flat=flat_readings(res["pieces_full"]), drape=g.get("drape_readings"))
    rows.append(flat_pattern_row(model, garment, spec))
    rows += tailor_rows_for(res["pieces_full"], kind, g)
    under_nm = g.get("over")  # (the garment worn under this one: an outer layer must clear it at every shared girth)
    if isinstance(under_nm, str) and under_nm in spec["cloth"]:
        from . import cloth_workflow
        ub = cloth_workflow.Ctx(model, under_nm, spec).Bp
        rows += layer_clearance_rows(res["pieces_full"], ub, res["body"], under_nm, g.get("layer_clearance"))
    rows.append({"id": "neckline_standoff", "stage": 3, "status": "INFO", "measure": "cloth_check.neckline_standoff_mm",
                 "ours": nk, "why": "no target yet: a checklist item adopts it with \"pattern_measure\""})
    fi = res.get("A_info") or {}
    rows.append({"id": "form_assembly", "stage": 3, "status": "INFO", "measure": "pattern_form.assemble",
                 "ours": {k: fi.get(k) for k in ("neck_point_mm", "turned_deg", "stretch_pct", "sew_gap_mm",
                                                 "inside_body", "through_under")},
                 "why": "the dress form's own report (folds turned, stretch, neck point on the body's HPS)"})
    for r_ in form_strain_rows(res, roles, g):
        if not form_ok and r_["status"] in ("PASS", "FAIL"):
            r_.update(form_status=r_["status"], status="INFO", why=f"read on the dress form (not validated: {FORM_FAULTS})")
        rows.append(r_)
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


def gate_status(model: str, garment: str, spec: dict | None = None) -> dict:
    """The gate record that a sim of this garment would be checked against, WITHOUT measuring: the pattern drafted
    and placed (cloth.build place_only, ~1 s) for its keys, then the record read. {"keys", "record" (or None),
    "passed", "why"}: why says what blocks (no record / FAIL rows). A garment drafted from no pattern passes."""
    from . import cloth, store
    spec = spec or store.load(model)
    g = spec["cloth"][garment]
    src = cloth.model_body(model, spec, g, simulate=False)
    res = cloth.build(cloth._garment_for_sim(g), src, f"{model}:{garment}", log=lambda *_: None, place_only=True)
    keys = res["gate_keys"]
    if keys.get("pattern") is None:
        return {"keys": keys, "record": None, "passed": True, "why": "no pattern: nothing to gate"}
    rec = read_record(keys["pattern"], keys["body"])
    if passed(rec):
        return {"keys": keys, "record": rec, "passed": True, "why": rec["status"]}
    why = ("no pattern-gate record for this exact pattern + body (never checked, or the pattern changed since)"
           if rec is None else f"the pattern gate is {rec.get('status')}: " + "; ".join(blocking(rec)))
    return {"keys": keys, "record": rec, "passed": False, "why": why}


def pattern_sheet(res: dict, prefix, concept: str | None = None, views=("front", "three", "side", "back"),
                  resolution: int = 700) -> _Path:
    """The pre-sim garment ASSEMBLED ON THE VIRTUAL DRESS FORM (res["A"] from pattern_form.on_form; its under garment
    drawn too), clay, front / 3/4 / side / back framed ~1 m round the garment, the concept first when given ->
    <prefix>.png. A result without "A" falls back to the placed start X0. Takes the GPU lock: run under
    /mnt/data/hifipushie/bin/capped (refused otherwise)."""
    from PIL import Image
    from . import cloth, resources
    if not _os.environ.get("HIFIPUSHIE_CAPPED"):
        raise RuntimeError("pattern_sheet renders: run it under /mnt/data/hifipushie/bin/capped (GPU lock, memory cap)")
    M, B = res["mesh"], res["body"]
    X = np.asarray(res["A"] if res.get("A") is not None else res["X0"], float)
    lo, hi = X.min(0) - 0.08, X.max(0) + 0.08
    c, half = (lo + hi) / 2, np.maximum((hi - lo) / 2, 0.5)  # (about 1 m across at least)
    objs = [{"name": "body", "V": B.V, "F": B.T, "color": "#c9b8a6"}]
    u = res.get("form_under")
    if u is not None:  # the garment under, as assembled on the form
        objs.append({"name": "under", "V": np.asarray(u["A"], float), "F": u["mesh"]["F"], "color": "#d8d4cc"})
    objs.append({"name": "garment", "V": X, "F": M["F"], "color": "#5b7fa6"})
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


# ---------------------------------------------------------------- layer clearance (flat; fit round 1, 2026-10-19)
# An OUTER garment must be bigger than the one UNDER it at every girth they share, by the room the under layer takes
# (its thickness + the gap the form keeps between layers), else the under garment comes through the outer one wherever
# it is the bigger: Garrett's shirt sleeve read 393 mm round at the biceps on the form vs the jacket's 378, and the
# diag render showed the shirt through both upper sleeves. Read FLAT (no form): chest / waist by cloth.sizing (seam to
# seam), the biceps as the line between the sleeve's biceps landmarks (BICEPS_POINTS: where the sleeve's side
# seams leave the cap), the neck as the collar stand's neck edge. Margin = 2 pi x LAYER_CLEARANCE (radial, m).
LAYER_CLEARANCE = {"chest": 0.006, "waist": 0.006, "biceps": 0.004, "neck": 0.003}  # m: one cloth (1.5) + the form's
# layer gap (pattern_form.EASE 4) at the torso; the arm and neck lie closer (pattern_form.UNDER_EASE 3, the collar)
BICEPS_POINTS = (("bicepsLeft", "bicepsRight"), ("tsF", "tsB"), ("usF", "usB"))  # (shirt one-piece; jacket top / under)
NECK_EDGES = ("cf>shoulderNotch>cb", "leftBottomCf>bottomMid")  # half the stand's neck edge (tailored stand; shirt band)


def _chord(P: np.ndarray, y: float) -> float:
    """Total length of a horizontal line at y inside the closed outline P (pattern plane)."""
    xs = []
    Q = np.r_[P, P[:1]]
    for a, b in zip(Q[:-1], Q[1:]):
        if (a[1] - y) * (b[1] - y) < 0:
            xs.append(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]))
    xs = sorted(xs)
    return float(sum(xs[i + 1] - xs[i] for i in range(0, len(xs) - 1, 2)))


def biceps_girth(Bp: dict, side: str = "L") -> float | None:
    """The sleeve's girth at its biceps line (m): the sum over the arm pieces of the straight line between each piece's
    BICEPS_POINTS pair (where its side seams leave the cap: a two-piece sleeve's front seam starts lower than its back
    one, so the line is slanted; a level chord through the top sleeve cut the cap: 212 mm for a 391 mm sleeve)."""
    tot, hit = 0.0, False
    for nm, pc in Bp["pieces"].items():
        if (pc.get("wrap") or {}).get("to") != f"arm.{side}":
            continue
        for a, b in BICEPS_POINTS:
            if a in pc["names"] and b in pc["names"]:
                P = np.asarray(pc["P"], float)
                tot += float(np.linalg.norm(P[pc["names"][a]] - P[pc["names"][b]]))
                hit = True
                break
    return tot if hit else None


def neck_girth(Bp: dict) -> float | None:
    """The collar stand's neck edge, whole (m): twice its half from the front end to CB (NECK_EDGES)."""
    from . import pattern
    pc = Bp["pieces"].get("stand")
    if pc is None:
        return None
    for arc in NECK_EDGES:
        try:
            P = np.asarray(pc["P"], float)[pattern.arc_indices(pc, arc)]
        except Exception:  # noqa: BLE001 (that edge's points aren't on this stand)
            continue
        return 2.0 * float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
    return None


def layer_girths(Bp: dict, body) -> dict:
    from . import cloth
    sz = cloth.sizing({"pieces": Bp, "body": body})["rows"]
    out = {k: float(sz[k]["garment_mm"]) / 1000 for k in ("chest", "waist") if k in sz}
    b = biceps_girth(Bp)
    if b:
        out["biceps"] = b
    n = neck_girth(Bp)
    if n:
        out["neck"] = n
    return out


def layer_clearance_rows(outer: dict, inner: dict, body, inner_name: str = "under",
                         clearance: dict | None = None) -> list:
    """One gate row per shared girth: outer >= inner + 2 pi x clearance (LAYER_CLEARANCE). outer / inner: flat pattern
    dicts (Bp) of the garment and the one worn under it."""
    cl = dict(LAYER_CLEARANCE, **(clearance or {}))
    go, gi = layer_girths(outer, body), layer_girths(inner, body)
    rows = []
    for k in ("biceps", "chest", "waist", "neck"):
        if k not in go or k not in gi:
            continue
        need = gi[k] + 2 * np.pi * cl[k]
        rows.append({"id": f"layer_clearance_{k}", "stage": 2, "status": "PASS" if go[k] >= need - 1e-4 else "FAIL",
                     "measure": "cloth_check.layer_clearance_rows (flat)", "read_on": "flat draft",
                     "ours": round(go[k] * 1000, 1), "ref": round(need * 1000, 1),
                     "why": f"over {inner_name} {gi[k] * 1000:.1f} mm + 2 pi x {cl[k] * 1000:.0f} mm clearance "
                            f"(margin {(go[k] - need) * 1000:+.1f} mm)"})
    return rows


def _selftest_layer_clearance():
    """Known answers: a rectangle's chord; a sleeve 10 mm wider passes only a clearance under 10 / 2 pi mm."""
    P = np.array([[0, 0], [0.3, 0], [0.3, 0.5], [0, 0.5]], float)
    assert abs(_chord(P, 0.25) - 0.3) < 1e-9
    U = np.array([[0, 0], [0.2, 0], [0.25, 0.4], [-0.05, 0.4]], float)  # widening upward: 0.3 at y 0.4
    assert abs(_chord(U, 0.2) - 0.25) < 1e-9


_selftest_layer_clearance()
