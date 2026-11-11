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
            # the SAME two pieces sewn on past this point (a piece cut on the fold and unfolded: a collar's fall on its
            # stand at CB is two mirrored seams meeting there): the seam goes on, this is no seam end (dress-tess s19:
            # Tess's coat collar read "turn 178.5" at cbLow, two straight 180 deg edges)
            if on[0] is not None and on[0] == on[1] and {_side(pcs, e)[0][1] for e in Bp["seams"][on[0]]} == {nma, nmb}:
                continue
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


MADE_ROLES = ("collar", "stand", "fall", "cuff", "band", "facing", "lapel", "placket", "yoke_facing", "hood")


def _made_like(nm: str, pc: dict) -> bool:
    """A piece made rather than draped (a collar, stand, cuff, band, facing, lapel; or any piece with a fold / roll
    line): its corners are design, not truing faults."""
    role = str(pc.get("role") or nm).lower()
    if any(r_ in role or r_ in nm.lower() for r_ in MADE_ROLES):
        return True
    return any(("fold" in k or "roll" in k) for k in (pc.get("lines") or {}))


def auto_true(pcs: dict, seams: list, corners=(), log=None) -> dict:
    """DRAFTS COME OUT TRUED (tee trial t4: 4-5 of 17 rounds went on hand truing, "true" ops whose `keep` bent a sleeve
    hem into a wave): every seam end the truing row would fail (junctions: turn > TRUE_DEG, not a corner by design, not
    a crossing) is trued on BOTH pieces by pattern.true_corner, each side taking half the turn so the joined edge runs
    on as one line, the seam edge held (keep = the seam side's far end on that piece). Returns the trued pieces."""
    out = dict(pcs)
    made_ = {nm for nm, pc in pcs.items() if _made_like(nm, pc)}
    for _ in range(2):  # (a corner trued on one seam can move another seam's end on the same point: once more)
        jn = junctions({"pieces": out, "seams": seams}, corners=tuple(corners or ()))
        # (a made piece's corners and the seam ends on it are design: a collar's, a cuff's, a lapel's; trued, a
        # tailored jacket's collar lay moved, test_collar made_lay)
        todo = [r for r in jn if not r["ok"] and not any(x.split(":", 1)[0] in made_ for x in r["at"].split(" | "))]
        if not todo:
            break
        for r in todo:
            A, B = r["seam"]
            sa, sb = _side(out, A), _side(out, B)
            sm_ = r["deg_a"] + r["deg_b"]
            # (smooth is a total of 180 + 360 k: a piece outlined the other way, a sleeve sewn to itself, reads its
            # wrist corners reflex, 278 + 278; aimed at 180 its hem was bent into a wave)
            fix = (180.0 + 360.0 * round((sm_ - 180.0) / 360.0) - sm_) / 2.0
            for side_, deg_ in ((sa, r["deg_a"]), (sb, r["deg_b"])):
                done = False
                for e_, nm, ix, _ in {id(x): x for x in (side_[0], side_[-1])}.values():
                    for at_i, far_i in ((int(ix[0]), int(ix[-1])), (int(ix[-1]), int(ix[0]))):
                        at_, keep = _pname(out[nm], at_i), _pname(out[nm], far_i)
                        if done or f"{nm}:{at_}" not in r["at"].split(" | ") or at_.startswith("#") or keep.startswith("#"):
                            continue
                        try:
                            out[nm] = pattern.true_corner(out[nm], at_, keep, float(deg_ + fix))
                        except Exception:  # (a corner the op can't bend is left for the gate to name)
                            continue
                        done = True
                        if log is not None:
                            log.append(f"trued {nm}:{at_} (keep {keep}): {deg_:.0f} -> {deg_ + fix:.0f} deg")
    return out


def _pname(pc, i):
    nm = [k for k, v in pc["names"].items() if int(v) == int(i) and not k.startswith("_")]
    return nm[0] if nm else f"#{i}"


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


# ---------------------------------------------------------------- flat first (2026-10-19 dress-garrett muslin 1)


# (a step the eye reads as an edge with its shadow; the same cloth running on smoothly from the collar into the lapel,
# round 3's fall roll, is no notch however the named points lie)


# ---------------------------------------------------------------- layer clearance (flat; fit round 1, 2026-10-19)


def _chord(P: np.ndarray, y: float) -> float:
    """Total length of a horizontal line at y inside the closed outline P (pattern plane)."""
    xs = []
    Q = np.r_[P, P[:1]]
    for a, b in zip(Q[:-1], Q[1:]):
        if (a[1] - y) * (b[1] - y) < 0:
            xs.append(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]))
    xs = sorted(xs)
    return float(sum(xs[i + 1] - xs[i] for i in range(0, len(xs) - 1, 2)))


def _selftest_layer_clearance():
    """Known answers: a rectangle's chord; a sleeve 10 mm wider passes only a clearance under 10 / 2 pi mm."""
    P = np.array([[0, 0], [0.3, 0], [0.3, 0.5], [0, 0.5]], float)
    assert abs(_chord(P, 0.25) - 0.3) < 1e-9
    U = np.array([[0, 0], [0.2, 0], [0.25, 0.4], [-0.05, 0.4]], float)  # widening upward: 0.3 at y 0.4
    assert abs(_chord(U, 0.2) - 0.25) < 1e-9


_selftest_layer_clearance()
