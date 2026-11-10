"""FOLD BENDS (R2 of docs/proposals/step5_one_build.md, C392): step 2's bends are numbers the build can act on.

Joe approved (2026-11-10): one build from ties, folds and what holds what. Step 2 wrote bends as prose ("lapel turned back
along the roll line from the gorge to the break ..."); no build could read them, so each stage had its own idea of a
collar's roll and a lapel had none. A rolled collar, a lapel rolled to its break, a turned-back cuff and a rolled sleeve
are one thing: a crease along a line on a piece, the part beyond it turned over by an angle, lying on something.

STEP 2 "style" bends, each ONE of:
  FOLD   {id, on: piece, fold: <name>, turn_deg: 0..180, lies_on: piece | "body" | "free", trace?: <trace id>, source}
         on: the inventory piece the crease is on (each side of a pair its own bend). fold: the crease's name; the
         draft (step 4) declares a fold of that name on that piece, and its line (break point to neck...) is the
         pattern's. turn_deg: how far the part beyond the crease turns over (0 = flat on, 180 = folded right back on
         itself). lies_on: what the turned part rests on (its own piece: a lapel on its forepart; another piece: a
         collar's fall over its stand; the body; free). trace: the reference's line of that crease (a step-2 trace).
  TARGET {id, on, what: <structure_rows kind>, target: {value, unit, of?}, source}   a number a stage aims at (the collar
         points' spread): judged by its row as before (C286).
A bend in words only ({target: {is}}) is refused: say it as a fold, as a target, or as a row the photo judges; a hang
is step 8's, a pose is `pose`.

STEP 4 (draft_own.gate, row `planned_folds`): every fold step 2 plans is declared on its piece, and every ROLL fold the
draft declares has its turn planned (a roll is a worn bend; a press fold is the cut's own, flat or pressed).
The build reads them as wear["folds"] (chain_plan.planned_wear) for R3's one crease turn.
"""
from __future__ import annotations

LIES = ("body", "free")
FORM = ("bends [{id, on: piece, fold: <the crease's name, declared on that piece at step 4>, turn_deg: 0..180 (0 = flat "
        "on, 180 = folded right back), lies_on: piece | body | free, trace?: <step-2 trace id>, source} | {id, on, what: "
        "<row kind>, target: {value, unit, of?}, source}]")


def base(piece: str) -> str:
    return piece[:-2] if piece.endswith((".L", ".R")) else piece


def is_fold(b: dict) -> bool:
    return isinstance(b, dict) and "fold" in b


def check(b: dict, w: str, pieces: dict, traces: list, bad: list) -> bool:
    """One step-2 bend's fold / prose refusals into bad. True when it is a fold bend (checked here, not as a target)."""
    if not is_fold(b):
        t = b.get("target")
        if isinstance(t, dict) and "is" in t and "value" not in t:
            bad.append(f"{w}: a bend in words only can't be built (C392): say it as a fold {{fold, turn_deg, lies_on}}, "
                       "a target {what, target: {value, unit}}, or a row the photo judges (rows); a hang is step 8's, a "
                       "pose is `pose`. " + FORM)
        return False
    on = str(b.get("on", ""))
    if on not in pieces:
        bad.append(f"{w}.on {on!r}: a fold is on an inventory piece (have {', '.join(sorted(pieces))})")
    if not str(b.get("fold") or "").strip():
        bad.append(f"{w}.fold: the crease's name (the draft declares a fold of this name on {on})")
    t = b.get("turn_deg")
    if not isinstance(t, (int, float)) or isinstance(t, bool) or not 0 <= t <= 180:
        bad.append(f"{w}.turn_deg {t!r}: how far the part beyond the crease turns over, 0..180 (180 = right back on itself)")
    lo = b.get("lies_on")
    if lo not in LIES and lo not in pieces:
        bad.append(f"{w}.lies_on {lo!r}: what the turned part rests on: an inventory piece, body or free")
    tr = b.get("trace")
    if tr is not None and tr not in {x.get("id") for x in traces if isinstance(x, dict)}:
        bad.append(f"{w}.trace {tr!r}: not a step-2 trace id")
    if "target" in b:
        bad.append(f"{w}: a fold's numbers are turn_deg and lies_on, no target (judge its line with a trace)")
    return True


def planned(style: dict | None) -> list:
    """The step-2 fold bends."""
    return [b for b in (style or {}).get("bends") or [] if is_fold(b)]


def wear(style: dict | None) -> dict:
    """{bend id: {on, fold, turn_deg, lies_on}}: what the build turns (R3)."""
    return {b["id"]: {k: b.get(k) for k in ("on", "fold", "turn_deg", "lies_on")} for b in planned(style)}


def draft_row(decl: dict, step2: dict | None) -> dict | None:
    """The flat gate's `planned_folds` row: every planned fold declared on its piece; every declared roll planned."""
    if step2 is None:
        return None
    folds = [f for f in decl.get("folds") or [] if isinstance(f, dict)]
    have = {(base(str(f.get("piece", ""))), f.get("name")) for f in folds}
    plan = planned(step2)
    why = []
    for b in plan:
        if (base(str(b.get("on", ""))), b.get("fold")) not in have:
            why.append(f"step 2 turns fold {b.get('fold')!r} on {b.get('on')} ({b.get('id')}); the draft declares none: "
                       "declare it (folds: {name, piece, line: [point, point], kind}) or change step 2")
    pl = {(base(str(b.get("on", ""))), b.get("fold")) for b in plan}
    for f in folds:
        if f.get("kind") == "roll" and (base(str(f.get("piece", ""))), f.get("name")) not in pl:
            why.append(f"roll fold {f.get('name')!r} on {f.get('piece')}: no step-2 bend turns it; back to step 2 "
                       "(garment_plan): plan its turn_deg and lies_on")
    return {"id": "planned_folds", "status": "FAIL" if why else "PASS",
            "value": f"{len(plan)} planned, {len(folds)} declared", "why": "; ".join(why),
            "source": "step 2's fold bends vs the draft's folds (fold_bends.py, C392)"}
