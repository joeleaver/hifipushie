"""Step 2's panel shares, each from a named SOURCE, placed round the body for the step-2 look (F4, blind trial s4-28).

Why (Joe, 2026-11-15): s4-28, sent back to step 2 for its panels, read the front off the picture and wrote the side and
back "inferred": the block's own proportions (the side body 0.08 of the chest, a 45 mm sliver). Step 4's row panels then
compared the draft with itself and passed. A check against a number the drafting agent also writes is met by writing the
draft's number; so the agent types NO share: each is read off the reference (seam points the tool turns into a share on
the body) or filled from the one named convention below. The shares are a style decision, judged on the step-2 look
where Joe approves step 2: its seams are drawn round the body where the shares put them.

FORM (step 2 `panels`): [{girth: a body girth by name (chest, waist, hips: a level step 0 read a width at), shares:
  {piece base name (no .L/.R; a left and right pair share it): {source: "reference", view, at: [[u, v], ...], what} |
  {source: "convention"}}}], the pieces listed from the centre front round to the centre back.
  reference: `at` = where the piece's seams cross the girth's level on that view, on ONE side of the figure (a piece at
    the centre front on a front view, or at the centre back on a back view, has one seam there: one point; a piece
    between two others: two), `what` = what was read (e.g. "the front / side seam at the silhouette under the arm").
    Each point is checked against step 0's read of that view: within LEVEL_TOL_MM of the girth's level, inside the
    garment's width there. The tool walks the body's own girth from the centre line to that place: the share.
  convention: RULE_TEXT. The rule's shares of the pieces not read are scaled to what the read ones leave.
  Any other source ("inferred", "draft", "block"...) is refused by name; so is a typed share.
The filled entry carries each piece's `share`, the `round_mm` and `placed` (the seams' places round the ring, for the
look): written by the tool, never by the agent."""
from __future__ import annotations

import numpy as np

SOURCES = ("reference", "convention")
RULE_NAME = "body_panels"
RULE = {2: (0.50, 0.50), 3: (0.40, 0.22, 0.38), 4: (0.28, 0.22, 0.22, 0.28)}
RULE_TEXT = (f"{RULE_NAME}: a body cut in N pieces round a girth, centre front to centre back: 2 = 0.50 / 0.50 (the "
             "side seam at the side); 3 = 0.40 / 0.22 / 0.38 (a side body under the arm, its back seam at the blade); "
             "4 = 0.28 / 0.22 / 0.22 / 0.28 (princess seams front and back)")
LEVEL_TOL_MM = 40.0  # a reference point off the girth's level by more than this isn't read at that girth
SUM_TOL = 0.02
FORM = ("panels: [{girth (chest, waist, hips...), shares: {piece base name: {source: reference, view, at: [[u, v]...] "
        "where its seams cross that level on one side, what: what was read} | {source: convention}}}], pieces from the "
        f"centre front to the centre back; no share is typed (panel_shares.py; {RULE_TEXT})")


def base(p: str) -> str:
    return p[:-2] if p.endswith((".L", ".R")) else p


# ---------------------------------------------------------------- the body's ring at a girth
def ring(L) -> dict:
    """The girth loop (n, 3) m as the LEFT half ring from the centre front to the centre back: {xy (mm, x from the
    centre), s (arc mm from the centre front), round_mm, s_side (arc to the widest point: the side seen front-on)}."""
    P = np.asarray(L, float)[:, :2] * 1000
    P = np.vstack([P, P[:1]])
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    rnd = float(seg.sum())
    t = np.linspace(0, rnd, max(int(rnd), 64), endpoint=False)  # (1 mm steps)
    cs = np.r_[0, np.cumsum(seg)]
    Q = np.c_[np.interp(t, cs, P[:, 0]), np.interp(t, cs, P[:, 1])]
    cx, cy = (Q[:, 0].max() + Q[:, 0].min()) / 2, Q[:, 1].mean()
    Q = Q - [cx, 0]
    front = np.where(Q[:, 1] < cy)[0]
    i0 = int(front[np.argmin(np.abs(Q[front, 0]))])  # (the centre front)
    Q = np.roll(Q, -i0, axis=0)
    if Q[min(5, len(Q) - 1), 0] < 0:  # (walk toward the wearer's left, +X)
        Q = np.vstack([Q[:1], Q[:0:-1]])
    n = len(Q) // 2 + 1
    Q = Q[:n]
    s = np.arange(n) * rnd / len(t)
    return {"xy": Q, "s": s, "round_mm": rnd, "s_side": float(s[int(np.argmax(Q[:, 0]))]), "xmax": float(Q[:, 0].max())}


def s_of(R: dict, t: float, view: str) -> float:
    """Arc mm from the centre front to the place seen at t (0 = the centre line, 1 = the side) on a front / back view."""
    x, k = abs(t) * R["xmax"], int(np.argmax(R["xy"][:, 0]))
    if view == "back":
        tail = R["xy"][k:, 0]
        return float(R["s"][k + int(np.nonzero(tail >= x)[0].max())])
    return float(R["s"][int(np.nonzero(R["xy"][:k + 1, 0] >= x)[0].min())])


def t_of(R: dict, s_mm: float) -> tuple[float, str]:
    """(t across the view, the view that sees it) of the place s_mm from the centre front."""
    i = int(np.clip(np.searchsorted(R["s"], s_mm), 0, len(R["s"]) - 1))
    return float(R["xy"][i, 0] / R["xmax"]), ("front" if s_mm <= R["s_side"] else "back")


# ---------------------------------------------------------------- step 0's read of the view at a girth
def width_row(read: dict, girth: str, vi: int) -> dict | None:
    """{centre, half (px: the garment's half width at the level), v, mm_per_px} from step 0's fit widths, or None."""
    fr = read.get("fit_read") or {}
    if fr.get("view", 0) != vi:
        return None
    for w in fr.get("widths") or []:
        if not isinstance(w, dict) or w.get("at") != girth:
            continue
        g = w.get("garment") or w.get("body")
        try:
            (u0, v0), (u1, v1) = g
            b = w.get("body") or g
            bw = abs(float(b[1][0]) - float(b[0][0]))
        except (TypeError, ValueError, IndexError):
            return None
        return {"centre": (u0 + u1) / 2, "half": abs(u1 - u0) / 2, "v": (v0 + v1) / 2, "body_px": bw}
    return None


# ---------------------------------------------------------------- the check
def check(panels, pieces: dict, read: dict, loop_of, bad: list) -> list | None:
    """Step 2's panels refused by name (FORM), else filled: each piece's share, round_mm and placed. loop_of(girth) ->
    the body's girth loop (n, 3) m, or None (no body: a reference share can't be read; nothing placed)."""
    if panels is None:
        return None
    if not isinstance(panels, list):
        bad.append(FORM)
        return None
    have, views, out = {base(p) for p in pieces}, read.get("views") or [], []
    for i, e in enumerate(panels):
        w = f"panels[{i}]"
        if not isinstance(e, dict) or not isinstance(e.get("girth"), str) or not isinstance(e.get("shares"), dict) \
                or not e["shares"]:
            bad.append(f"{w}: {FORM}")
            continue
        g, sh, n0 = e["girth"], e["shares"], len(bad)
        for k, v in sh.items():
            ww = f"{w}.shares.{k}"
            if base(k) not in have:
                bad.append(f"{ww}: not a step-1 piece (have {', '.join(sorted(have))})")
            if not isinstance(v, dict):
                bad.append(f"{ww}: {{source: reference | convention}}, never a typed share (a number the draft can also "
                           "write is met by writing the draft's: t s4-28)")
            elif v.get("source") not in SOURCES:
                bad.append(f"{ww}.source {v.get('source')!r}: reference (read off the picture) or convention "
                           f"({RULE_NAME}); never draft / block / inferred: the block's proportion is what's checked")
        if len(bad) > n0:
            continue
        L = loop_of(g) if loop_of else None
        R = ring(L) if L is not None and len(L) > 8 else None
        names, got = list(sh), {}
        for j, k in enumerate(names):
            v = sh[k]
            if v["source"] != "reference":
                continue
            s = _read(v, f"{w}.shares.{k}", g, j, len(names), R, read, views, bad)
            if s is not None:
                got[k] = s
        if len(bad) > n0:
            continue
        conv = [k for k in names if sh[k]["source"] == "convention"]
        left = 1.0 - sum(got.values())
        if conv:
            rule = RULE.get(len(names))
            if rule is None:
                bad.append(f"{w}: {RULE_NAME} has no rule for {len(names)} pieces round a girth ({RULE_TEXT}): read "
                           "each off the reference")
                continue
            if left <= 0.05:
                bad.append(f"{w}: the read shares take {1 - left:.2f} of the {g}, leaving the convention pieces "
                           f"{', '.join(conv)} nothing: re-read the seam points")
                continue
            rs = sum(rule[names.index(k)] for k in conv)
            got.update({k: rule[names.index(k)] * left / rs for k in conv})
        tot = sum(got.values())
        if abs(tot - 1) > SUM_TOL:
            bad.append(f"{w}: the read shares sum to {tot:.2f} round the {g} ({', '.join(f'{k} {v:.2f}' for k, v in got.items())}): "
                       "the pieces share all of it (1): re-read the seam points, or let one piece take the convention")
            continue
        typed = [k for k in names if "share" in sh[k] and abs(float(sh[k]["share"]) - got[k]) > 0.005]
        if typed:  # (a saved entry re-checked carries the tool's own share; any other is typed)
            bad += [f"{w}.shares.{k}.share {sh[k]['share']}: not typed: the tool's is {got[k]:.3f} (read off the "
                    f"reference points, or {RULE_NAME}); leave it out" for k in typed]
            continue
        f = dict(e, shares={k: dict(sh[k], share=round(got[k], 3)) for k in names})
        if R is not None:
            f["round_mm"] = round(R["round_mm"], 1)
            f["placed"] = place(R, [(k, got[k]) for k in names])
        out.append(f)
    return out


def _read(v: dict, w: str, g: str, j: int, n: int, R, read: dict, views: list, bad: list) -> float | None:
    """A reference share: its seam points on the view, turned into arc along the body's girth (module docstring)."""
    vi, at = v.get("view", 0), v.get("at")
    if not str(v.get("what") or "").strip():
        bad.append(f"{w}.what: what was read (e.g. 'the front / side seam at the silhouette under the arm')")
    if not isinstance(vi, int) or not 0 <= vi < len(views) or views[vi].get("view") not in ("front", "back"):
        bad.append(f"{w}.view {vi!r}: a step-0 front or back view")
        return None
    side = views[vi]["view"]
    want = 2 - (j == 0 and side == "front") - (j == n - 1 and side == "back")
    if not (isinstance(at, list) and all(isinstance(q, (list, tuple)) and len(q) == 2 for q in at)) or len(at) != want:
        bad.append(f"{w}.at: {want} point(s) [[u, v]] where its seams cross the {g} level on one side of view {vi} "
                   f"({'its one seam: the other side of it is the centre line' if want == 1 else 'its two seams'}"
                   + ("; a piece whose both seams aren't seen on this view: convention, or read it on another view"
                      if want == 0 else "") + ")")
        return None
    wr = width_row(read, g, vi)
    if wr is None:
        bad.append(f"{w}: step 0 read no width at the {g} on view {vi} (fit_read.widths): the seam's place round the "
                   "body is read against it; convention, or back to step 0")
        return None
    if R is None:
        bad.append(f"{w}: no body to read the {g} round on (the model has no base): convention")
        return None
    mmpx = 2 * R["xmax"] / max(wr["body_px"], 1.0)
    ss = []
    for u, vv in at:
        if abs(vv - wr["v"]) * mmpx > LEVEL_TOL_MM:
            bad.append(f"{w}.at [{u}, {vv}]: {abs(vv - wr['v']) * mmpx:.0f} mm off the {g} level (v {wr['v']:.0f} on "
                       f"view {vi}, step 0's width row): read the seam where it crosses that level")
            continue
        t = (u - wr["centre"]) / max(wr["half"], 1.0)
        if abs(t) > 1.05:
            bad.append(f"{w}.at [{u}, {vv}]: outside the garment at the {g} (u {wr['centre'] - wr['half']:.0f} to "
                       f"{wr['centre'] + wr['half']:.0f} on view {vi}): a seam behind the side isn't seen here")
            continue
        ss.append(s_of(R, min(abs(t), 1.0), side))
    if len(ss) != len(at):
        return None
    lo = 0.0 if (j == 0 and side == "front") else min(ss)
    hi = R["round_mm"] / 2 if (j == n - 1 and side == "back") else max(ss)
    return 2 * (hi - lo) / R["round_mm"]


def place(R: dict, shares: list) -> dict:
    """The seams round the ring where the shares put them (one side; the other mirrors): {seams: [{between, s_mm, t,
    seen_from, xy}], pieces: [{piece, share, mid_t, seen_from, xy}], ring: [[x, y, s] mm, a top view of the half ring]}."""
    half, s, seams, pcs = R["round_mm"] / 2, 0.0, [], []
    for k, (p, sh) in enumerate(shares):
        mid = s + sh * half / 2
        t, vw = t_of(R, mid)
        pcs.append({"piece": p, "share": round(sh, 3), "mid_t": round(t, 3), "seen_from": vw, "xy": _xy(R, mid)})
        s += sh * half
        if k < len(shares) - 1:
            t, vw = t_of(R, s)
            seams.append({"between": [p, shares[k + 1][0]], "s_mm": round(s, 1), "t": round(t, 3), "seen_from": vw,
                          "xy": _xy(R, s)})
    step = max(1, len(R["xy"]) // 40)
    return {"seams": seams, "pieces": pcs, "ring": [[round(float(x)), round(float(y)), round(float(s_))] for (x, y), s_ in
                                                    zip(R["xy"][::step], R["s"][::step])]}


def _xy(R: dict, s_mm: float) -> list:
    i = int(np.clip(np.searchsorted(R["s"], s_mm), 0, len(R["s"]) - 1))
    return [round(float(R["xy"][i, 0])), round(float(R["xy"][i, 1]))]


def text_lines(p: dict) -> list:
    """Step 2's text answer: every share, its source and where its seams fall (numbers here, never on the look: C288)."""
    L = []
    for e in p.get("panels") or []:
        pl = e.get("placed") or {}
        L.append(f"  panels {e['girth']}" + (f" (round {e['round_mm']:.0f} mm)" if e.get("round_mm") else "") + ": "
                 + ", ".join(f"{k} {v['share']:.2f} ({v['source']}" + (f" on view {v.get('view', 0)}: {v.get('what')}"
                             if v["source"] == "reference" else f": {RULE_NAME}") + ")" for k, v in e["shares"].items()))
        if pl:
            L.append("    seams a side, mm round from the centre front: " + ", ".join(
                f"{a} / {b} at {sm['s_mm']:.0f} (seen from the {sm['seen_from']}, {abs(sm['t']):.2f} of the way to the "
                "side)" for sm in pl["seams"] for a, b in [sm["between"]]))
    return L


def loop_of_body(body):
    """loop_of for check: the model's torso girth loop at a step-0 landmark's level, or None."""
    if body is None:
        return None

    def f(g):
        try:
            b = body() if callable(body) and not hasattr(body, "at") else body  # (garment_plan.write's lazy body)
        except (OSError, KeyError, ValueError):
            return None
        if b is None or not hasattr(b, "torso_loop"):
            return None
        try:
            return b.torso_loop(b.at(g)["z_mm"])
        except (KeyError, ValueError, TypeError):
            return None
    return f
