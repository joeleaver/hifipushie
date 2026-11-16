"""garment_mark: STEP 5 of drape first, MARK (docs/proposals/drape_first.md): the garment's seams drawn on the approved
toile (step 4's toile.npz) as LINES, each a named body line projected onto the toile by its own rule (mark_lines.py),
cut exactly into the toile mesh (mark_split.py). Spikes R1 / R2 / R2b (C489-C491) made general: nothing here knows a
garment; the declaration carries it (refused by name).

THE DECLARATION:
  marks   [{"name", "line": {"kind": mark_lines.KINDS, ...its parameters}, "region": the region it cuts ("toile" at the
          start, else a region an earlier mark made), "into": [piece where g < 0, piece where g > 0]}], in order. A mark
          named "*.L" (region / into "*.L") is mirrored to ".R" on the mirrored toile unless declared itself.
  absent  {step-1 piece: why}: a built step-1 piece not cut from the toile (a collar: R3c; a facing cut from the front's
          flat later); its seams are listed, not required.
  runs    {"piece:edge": "front" | "back" | "top" | "bottom"}: where two pieces share more than one run (a two-piece
          sleeve's fore and hind seams), which run is this step-1 edge (the run whose middle lies furthest that way).
GATE ROWS: marks (every mark cuts the toile: its length on the surface; a point of the line is a point of the toile by
construction), separate (every mark cuts its region into exactly TWO parts: a mark that does not separate is REFUSED,
named, R2's refusal; islands under mark_split.MIN_SHARE rejoin), pieces (the regions at the end = step 1's built pieces
less the absent ones, each ONE region), seams (every step-1 seam between two cut pieces is a shared run; a pair the marks
join that step 1 doesn't name is listed). THE LOOK: the toile coloured by piece, the marks drawn, 4 views beside the
reference. Writes <look dir>/mark/mark.npz (V, F, the piece label per face, names) + mark.json; record step 5."""
from __future__ import annotations

import json
import re

import numpy as np

from .mark_lines import MIR, LineRefused, Lines
from .mark_split import areas, edge_faces, regions, seam_runs, split

RUN_DIRS = {"front": (1, -1), "back": (1, 1), "top": (2, 1), "bottom": (2, -1)}


class MarkRefused(ValueError):
    """A declaration the toile can't be marked from, or a mark that doesn't separate (named)."""


def mirrored(marks: list) -> list:
    have = {m.get("name") for m in marks}
    out = []
    for m in marks:
        out.append(dict(m, mirror=False))
        nm = str(m.get("name", ""))
        if nm.endswith(".L") and nm[:-2] + ".R" not in have:
            sw = lambda s: re.sub(r"\.L$", ".R", s) if isinstance(s, str) else s
            reg = m.get("region")
            if isinstance(reg, str) and not reg.endswith(".L"):  # (cut from a centre region: what remains of it)
                reg = next((x for x in m.get("into") or [] if isinstance(x, str) and not x.endswith(".L")), reg)
            out.append(dict(m, name=sw(nm), region=sw(reg), into=[sw(x) for x in m.get("into") or []],
                            mirror=True))
    return out


def validate(decl: dict, s1: dict) -> list:
    if not isinstance(decl, dict):
        return ["declarations: {marks, absent, runs} (module doc)"]
    bad = []
    marks = decl.get("marks")
    if not isinstance(marks, list) or not marks:
        return ["marks: a list of {name, line: {kind, ...}, region, into: [g < 0 piece, g > 0 piece]}"]
    have = {"toile"}
    for i, m in enumerate(mirrored(marks)):
        nm = m.get("name") or f"marks[{i}]"
        if not isinstance(m.get("line"), dict) or "kind" not in m["line"]:
            bad.append(f"{nm}: line: {{kind, ...}}")
        if m.get("region") not in have:
            bad.append(f"{nm}: region {m.get('region')!r} is not made yet (have {', '.join(sorted(have))})")
        if not (isinstance(m.get("into"), list) and len(m["into"]) == 2 and m["into"][0] != m["into"][1]):
            bad.append(f"{nm}: into: two different names [g < 0, g > 0]")
            continue
        have.discard(m.get("region"))
        have |= set(m["into"])
    pcs = s1.get("pieces") or {}
    bad += [f"absent: {p!r} is not a step-1 piece" for p in decl.get("absent") or {} if p not in pcs]
    for k, v in (decl.get("runs") or {}).items():
        if v not in RUN_DIRS:
            bad.append(f"runs.{k}: {v!r}: one of {', '.join(RUN_DIRS)}")
    return bad


def run_marks(V, F, marks: list, lines: Lines, log=print):
    """(V, F, label per face, names, per-mark report): every mark cut in order; MarkRefused on one that doesn't separate."""
    names = ["toile"]
    lab = np.zeros(len(F), int)
    rep = []
    for m in marks:
        if m["region"] not in names:
            raise MarkRefused(f"{m['name']}: region {m['region']!r} is not a region now ({', '.join(names)})")
        r = names.index(m["region"])
        mask = None
        P = V * MIR if m["mirror"] else V
        Vreg = P[np.unique(F[lab == r])]
        try:
            g = lines.field(m["line"], P, Vreg)
        except LineRefused as e:
            raise MarkRefused(f"{m['name']}: {e}") from None
        if m["line"]["kind"] == "centre_back":  # the plane only behind the torso's centre: the front is the opening
            mask = (V[F, 1].mean(1) > lines.yc)
        V, F, lab, sg, msk, ncut = split(V, F, lab, r, g, mask)
        faces = np.where(lab == r)[0]
        c, ar = regions(V, F, faces, sg, msk)
        sides = [float(np.mean(sg[faces][(c == k) & msk[faces]]) if ((c == k) & msk[faces]).any() else 0.0)
                 for k in range(len(ar))]
        big = np.argsort(-ar)
        if len(ar) != 2 or np.sign(sides[0]) == np.sign(sides[1]):
            at = [np.round(V[F[faces[c == k]]].mean((0, 1)), 3).tolist() for k in big[:3]]
            raise MarkRefused(f"{m['name']} does not separate {m['region']!r}: {len(ar)} part(s), shares "
                              f"{np.round(ar[big] / ar.sum(), 3).tolist()[:4]} (centres {at}); move the line, never patch "
                              f"round it")
        neg = 0 if sides[0] < 0 else 1
        names[r] = m["into"][0]
        names.append(m["into"][1])
        lab[faces[c != neg]] = len(names) - 1
        E, ef = edge_faces(F)
        two = ef[:, 1] >= 0
        a_, b_ = lab[ef[two, 0]], lab[ef[two, 1]]
        on = E[two][((a_ == r) & (b_ == len(names) - 1)) | ((b_ == r) & (a_ == len(names) - 1))]
        rep.append({"mark": m["name"], "kind": m["line"]["kind"], "region": m["region"], "into": m["into"],
                    "length_mm": round(float(np.linalg.norm(V[on[:, 0]] - V[on[:, 1]], axis=1).sum()) * 1000, 1),
                    "inserted": ncut, "areas_cm2": [round(float(ar[neg]) * 1e4, 1), round(float(ar[1 - neg]) * 1e4, 1)]})
        log(f"mark {m['name']}: {rep[-1]}")
    return V, F, lab, names, rep


def pick_run(runs, V, how):
    ax, sgn = RUN_DIRS[how]
    return int(np.argmax([sgn * V[ch, ax].mean() for ch in runs]))


def seam_map(V, F, lab, names, s1: dict, decl: dict):
    """(rows' facts) every step-1 seam between cut pieces -> its run: {seam label: {pair, run, length_mm}}, the missing,
    the absent ones, the pairs step 1 doesn't name."""
    pairs, free = seam_runs(F, lab, names)
    absent = set(decl.get("absent") or {})
    got, miss, skipped, named_pairs = {}, [], [], set()
    by_pair = {}
    for s in s1.get("seams") or []:
        pa, pb = s["a"].split(":")[0], s["b"].split(":")[0]
        if pa in absent or pb in absent or pa == pb:
            skipped.append(f"{s['a']} | {s['b']}")
            continue
        key = (pa, pb) if (pa, pb) in pairs else (pb, pa)
        named_pairs.add(key)
        by_pair.setdefault(key, []).append(s)
    for key, ss in by_pair.items():
        runs = pairs.get(key) or []
        if not runs:
            miss += [f"{s['a']} | {s['b']}: the marks give {key[0]} and {key[1]} no shared edge" for s in ss]
            continue
        long_runs = sorted(range(len(runs)), key=lambda i: -len(runs[i]))[:max(len(ss), 1)]
        for s in ss:
            if len(ss) == 1:
                k = long_runs[0]
            else:
                how = (decl.get("runs") or {}).get(s["a"]) or (decl.get("runs") or {}).get(s["b"])
                if how is None:
                    miss.append(f"{s['a']} | {s['b']}: {key[0]} and {key[1]} share {len(ss)} step-1 seams: name which run "
                                f"(runs: {{\"{s['a']}\": front|back|top|bottom}})")
                    continue
                k = long_runs[pick_run([runs[i] for i in long_runs], V, how)]
            ch = runs[k]
            got[f"{s['a']}|{s['b']}"] = {"a": s["a"], "b": s["b"], "pair": list(key), "run": int(k),
                                         "length_mm": round(float(np.linalg.norm(np.diff(V[ch], axis=0), axis=1).sum()) * 1000, 1)}
    extra = [f"{a} + {b} ({sum(len(c) - 1 for c in r)} edges)" for (a, b), r in pairs.items() if (a, b) not in named_pairs]
    return got, miss, skipped, extra, pairs, free


def gate(rep, names, lab, V, F, s1, decl, got, miss, skipped, extra) -> list:
    from . import draft_own
    rows = [{"id": "marks", "status": "PASS" if all(r["length_mm"] > 0 for r in rep) else "FAIL",
             "value": f"{len(rep)} marks; " + ", ".join(f"{r['mark']} {r['length_mm']} mm" for r in rep),
             "target": "every mark cuts the toile (its points on the surface by construction)",
             "why": "; ".join(f"{r['mark']}: cuts nothing" for r in rep if r["length_mm"] == 0), "back_to": "5"},
            {"id": "separate", "status": "PASS", "value": f"{len(rep)} of {len(rep)} marks split their region in two",
             "target": "every mark cuts its region into exactly two parts", "back_to": "5"}]
    want = {p for p, it in (s1.get("pieces") or {}).items() if it.get("build") in draft_own.BUILT} - set(decl.get("absent") or {})
    have = set(names)
    ar = {n: round(float(areas(V, F[lab == i]).sum()) * 1e4, 1) for i, n in enumerate(names)}
    rows.append({"id": "pieces", "status": "PASS" if have == want else "FAIL",
                 "value": f"{len(have)} pieces: " + ", ".join(f"{n} {ar[n]} cm2" for n in names),
                 "target": "step 1's built pieces less the absent ones, each one region",
                 "why": "; ".join([f"not cut: {p}" for p in sorted(want - have)] + [f"not in step 1: {p}" for p in sorted(have - want)]),
                 "back_to": "5"})
    rows.append({"id": "seams", "status": "FAIL" if miss else "PASS",
                 "value": f"{len(got)} step-1 seams marked; {len(skipped)} with an absent piece",
                 "target": "every step-1 seam between two cut pieces is a mark", "why": "; ".join(miss[:8]),
                 "detail": {"marked": got, "absent": skipped, "not_in_step1": extra}, "back_to": "5"})
    if extra:
        rows.append({"id": "extra_seams", "status": "INFO", "value": "; ".join(extra[:8]),
                     "target": "info: pieces the marks join that step 1 names no seam between (sewn at step 6 as marked)"})
    return rows
