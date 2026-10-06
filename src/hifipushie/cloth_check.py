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

from . import pattern

KINDS = {"cap_shirt": (0.0, 0.03), "cap_coat": (0.03, 0.06), "band": (-0.01, 0.015), "plain": (-0.015, 0.015),
         "back_shoulder": (0.0, 0.04)}
NOTCH_MM = 6.0


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
