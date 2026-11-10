"""CLOSURE TIES (R1 of docs/proposals/step5_one_build.md, C391): a closure's worn state is WHICH of its fastenings are
done up, never a named state.

Joe (2026-11-10): "I'm very concerned about 'open' and 'closed' states being their own thing in the code ... why should it
matter?" It shouldn't: a closure is a row of pairs (button 1 to hole 1, ...; a zip's teeth along its edges), and wearing
it ties some of them. Open is no tie, closed is every tie, partly is some: one list, no modes.

STEP 2 "style" writes `ties` for EVERY inventory closure:
  ties {closure: {fastened: [numbers from the top, 1 = the top fastening], of: how many it has (counted on the
        reference or the inventory), detail?, source}}    buttons, hooks, clasps, a band's own button
        {closure: {span: [from, to], detail?, source}}     a closure with no separate fastenings (a zip, lacing): the
                                                           share of its length done up, 0 = its top, 1 = its bottom
`fastened: []` is a closure left wholly undone; a top button done and the lower left undone is `fastened: [1], of: 2`.

The build (chain_plan.planned_wear -> chain_garment.Build) ties exactly the pairs these name: `tied()` maps a tie onto a
closure's pairs, ordered top first, by number or by each pair's share along the closure. `summary()` is what the
STRUCTURE reads compare a build with (none tied -> open, every one -> closed, else partly): derived, never written.

Old records wrote `state {closure: {state: open|closed|partly, fastened_from?}}`; `of_style` still reads them (approved
records keep their digests), and a new step 2 with `state` is refused, pointing here.
"""
from __future__ import annotations

FORM = ("ties {closure: {fastened: [numbers from the top, 1 = the top], of: how many it has, source} | {span: [from, to] "
        "share of its length done up (a zip, lacing; 0 = top), source}} for EVERY closure: fastened [] = none done up")


def check(p: dict, closures: dict, bad: list, src) -> None:
    """Step 2's ties, refused by name into `bad` (src: garment_plan._src)."""
    if p.get("state") is not None:
        bad.append("state: a closure's worn state is which fastenings are done up, not a named state (C391): write " + FORM)
        return
    ties = p.get("ties") if isinstance(p.get("ties"), dict) else {}
    for c in ties:
        if c not in closures:
            bad.append(f"ties.{c}: no closure {c!r} in the inventory (have {', '.join(closures) or 'none'})")
    for c in closures:
        x = ties.get(c)
        w = f"ties.{c}"
        if not isinstance(x, dict) or ("fastened" in x) == ("span" in x):
            bad.append(f"{w}: which of its fastenings are done up: " + FORM)
            continue
        src(x, w, bad)
        if "span" in x:
            s = x["span"]
            if not (isinstance(s, list) and len(s) == 2 and all(isinstance(v, (int, float)) for v in s)
                    and 0 <= s[0] <= s[1] <= 1):
                bad.append(f"{w}.span {s!r}: [from, to], shares of the closure's length from its top, 0 <= from <= to <= 1")
            continue
        f, n = x.get("fastened"), x.get("of")
        if not isinstance(n, int) or n < 1:
            bad.append(f"{w}.of {n!r}: how many fastenings the closure has (a whole number, counted on the reference)")
        elif not (isinstance(f, list) and all(isinstance(k, int) and 1 <= k <= n for k in f) and len(set(f)) == len(f)):
            bad.append(f"{w}.fastened {f!r}: the numbers of the fastenings done up, each 1..{n} (1 = the top), [] for none")


def of_style(style: dict | None) -> dict:
    """{closure: tie} from a step-2 output: its `ties`, or an old record's `state` read as ties."""
    style = style or {}
    if isinstance(style.get("ties"), dict):
        return {c: dict(x) for c, x in style["ties"].items() if isinstance(x, dict)}
    out = {}
    for c, x in (style.get("state") or {}).items():
        if not isinstance(x, dict):
            continue
        s, keep = x.get("state"), {k: x[k] for k in ("detail", "source") if k in x}
        if s == "open":
            out[c] = dict(keep, fastened=[], legacy="open")
        elif s == "partly":
            k = x.get("fastened_from")
            out[c] = dict(keep, fastened_from=k, legacy="partly")
        else:
            out[c] = dict(keep, all=True, legacy=s or "closed")  # (the pattern's own pairs as they were: kept as built)
    return out


def tied(tie: dict | None, shares: list) -> list:
    """Which pairs of a closure are tied: shares = each pair's place along the closure, top first (0 top .. 1 bottom)."""
    n = len(shares)
    if tie is None or tie.get("all"):
        return [True] * n
    if "span" in tie:
        a, b = tie["span"]
        return [a - 1e-9 <= s <= b + 1e-9 for s in shares]
    if "fastened_from" in tie:  # (an old record's partly: from that button down)
        k = tie.get("fastened_from")
        return [isinstance(k, int) and i + 1 >= k for i in range(n)]
    f = set(tie.get("fastened") or [])
    return [i + 1 in f for i in range(n)]


def summary(tie: dict | None) -> str:
    """open / closed / partly: what the build's closure reads are compared with (derived from the tie, never written)."""
    if tie is None or tie.get("all"):
        return "closed"
    if tie.get("legacy") in ("open", "partly"):
        return tie["legacy"]
    if "span" in tie:
        a, b = tie["span"]
        return "open" if b - a <= 1e-9 else ("closed" if a <= 1e-9 and b >= 1 - 1e-9 else "partly")
    f, n = tie.get("fastened") or [], tie.get("of") or 0
    return "open" if not f else ("closed" if len(f) >= n else "partly")


def said(tie: dict | None) -> str:
    """The tie in words, for answers: 'fastened 1 of 2', 'none of 2 done up', 'span 0-1', or an old record's state."""
    t = tie or {}
    if t.get("legacy"):
        return t["legacy"] + (f" from button {t['fastened_from']}" if t.get("fastened_from") else "")
    if "span" in t:
        return f"done up over {t['span'][0]:g}-{t['span'][1]:g} of its length"
    f, n = t.get("fastened") or [], t.get("of")
    return (f"fastened {', '.join(map(str, f))} of {n}" if f else f"none of {n} done up") + f" ({summary(t)})"


def states(style: dict | None) -> dict:
    """{closure: {state: summary, source, detail, tie}}: the shape the structure reads take (structure_rows.closure_reads)."""
    return {c: {"state": summary(t), "source": t.get("source", ""), "detail": t.get("detail", ""), "tie": t}
            for c, t in of_style(style).items()}


def shares_of(n: int) -> list:
    """Evenly spaced places for n pairs with no positions known (a closure's own pairs, top first)."""
    return [0.0] if n == 1 else [i / (n - 1) for i in range(n)]
