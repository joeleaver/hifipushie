"""Step 3 of a garment's record (body_tape(..., garment=...)), for any garment: COMPLETE or refused by name, and SUMS.

COMPLETE (C355): step 3 is written only when it holds every measurement step 1 names (its `measurements`: the seams'
body lengths and the bases of their ratios); a missing one is refused by name (t s3-1: written without `armscye`, which
the armhole seams were drafted from, and nothing said so). The draft (step 4) needs more than these: its own
measurements (chest, waist, back length...) are taken in the same call.
SUMS (C355): {"name", "kind": "sum", "of": [names taken in the same call]}: a measurement no single tape can take,
added from its parts as a tailor adds them (t s3-1: the armhole is a tilted loop over the shoulder point and under the
armpit; no girth square to the arm reaches it, so it is its front and back halves, each an arc over the surface).
"""
from __future__ import annotations


def sums(items: list, rows: list, errs: list):
    """Each sum from rows already taken (appended to rows), or refused into errs by name."""
    have = {r["name"]: r for r in rows}
    for it in items:
        n, of = it.get("name"), it.get("of")
        if not n or not isinstance(of, list) or len(of) < 2 or not all(isinstance(x, str) for x in of):
            errs.append(f"  REFUSED {n or it}: a sum is {{name, kind: 'sum', of: [two or more names taken in this call]}}")
            continue
        miss = [x for x in of if x not in have]
        if miss:
            errs.append(f"  REFUSED {n}: its parts {', '.join(miss)} aren't taken in this call (take each by name)")
            continue
        if any("mm" not in have[x] for x in of):
            errs.append(f"  REFUSED {n}: a sum adds lengths in mm (an angle can't be added)")
            continue
        mm = round(sum(float(have[x]["mm"]) for x in of), 1)
        rows.append({"name": n, "kind": "sum", "mm": mm, "of": list(of),
                     "how": " + ".join(f"{x} ({have[x]['mm']})" for x in of) + ": each taken above"})
        have[n] = rows[-1]


def write(name: str, garment: str, rows: list, errs: list, look: str) -> str:
    """Write step 3 when it is complete; else say what is missing (the record unchanged)."""
    from . import garment_record as gr
    try:
        rec = gr.load(name, garment)
    except Exception as e:  # noqa: BLE001  (no record: say so, nothing written)
        return f"record: refused: {e}"
    need = list((rec["steps"]["1"].get("output") or {}).get("measurements") or [])
    taken = {r["name"] for r in rows}
    miss = [m for m in need if m not in taken]
    if miss:
        return (f"record: refused: step 3 not written: step 1 names {', '.join(miss)} (its seams' lengths are drafted "
                "from them); take each by name in the same call: as defined there, a FreeSewing name, or, when no one "
                "tape can take it, a sum of parts ({name, kind: 'sum', of: [...]}, e.g. an armhole's front + back arcs)")
    try:
        gr.write(name, garment, "3", "done", output={"body": name, "measurements": rows,
                                                     "refused": [e.strip() for e in errs]}, look=[look], by="body_tape")
    except gr.OrderRefused as e:
        return f"record: refused: {e}"
    return (f"record: step 3 (measure) written: {gr.path(name, garment)} (all {len(need)} step 1 names taken)"
            + blocks(taken))


def blocks(taken: set) -> str:
    """Which of FreeSewing's designs this step 3 can draft, and what each other one still needs (C362, t s4-2: every
    jacket block needs hpsToBust, which step 3 hadn't taken; step 4 had to retake it). '' when the pack is absent."""
    from . import assets, pattern_parts as pp
    try:
        have = sorted(p.name for p in (assets.pack("freesewing") / "node_modules" / "@freesewing").iterdir()
                      if (p / "package.json").exists() and p.name not in NOT_DESIGNS)
    except Exception:  # noqa: BLE001
        return ""
    ok, short = [], []
    for n in have:
        try:
            need = pp.inspect(n, None, None, draft=False).get("config", {}).get("measurements") or []
        except Exception:  # noqa: BLE001  (not a design)
            continue
        miss = [m for m in need if m not in taken]
        (short.append(f"{n} needs {', '.join(miss)}") if miss else ok.append(n))
    return ("\nFreeSewing's blocks: this step 3 can draft " + (", ".join(ok) or "none") +
            (f"; not yet: {'; '.join(short)} (take those here, by name, before drafting from them)" if short else ""))


NOT_DESIGNS = ("core", "core-plugins", "config", "library") + tuple(f"plugin-{x}" for x in (
    "annotations", "bin-pack", "bust", "flip", "measurements", "mirror", "round", "sprinkle", "transform"))
