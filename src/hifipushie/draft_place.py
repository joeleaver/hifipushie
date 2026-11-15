"""Step-4 row `place`: each piece's declared place {to, side} checked against WHERE its own tapes were taken (F2).

Why (blind trial s4-26): the girths row needs each piece's place (a sleeve out of the chest ring); the agent's "side"
values were "guessed (front/back/side) and accepted silently". A piece's tapes (draft_tapes: step 3's tapes it was
drafted on) say where it lies: a length or arc running down the front of the torso (the body faces -Y), the back, the
side, or along a limb (outside the torso's girths, above or below their lowest: an arm or a leg). Girths (loops) go
round the body and say nothing of a side. Each piece is read by the majority of its path tapes:
  FAIL: a torso piece declared on a side its tapes contradict (front / back), a piece declared on a limb whose tapes are
  the torso's or the reverse, a side value that isn't front / back / side; each with the declaration to write.
  said: every piece's place as used and the tapes that read it. A piece whose tapes don't decide is said, not failed.
The .L / .R of a limb comes from the piece's name (step 3 tapes the left side; the right is its mirror). Nothing here
knows a garment."""
from __future__ import annotations

import numpy as np

SIDES = ("front", "back", "side")
SIDE_M = 0.03  # m: a path this far in front of / behind the torso's centre (its girths' middle) is on that side
LIMB_WORDS = ("arm", "leg")


def _where(path: np.ndarray, y0: float, hw: float, zlow: float) -> str:
    """'front' | 'back' | 'side' | 'arm' | 'leg' for one tape path."""
    out = np.abs(path[:, 0]) > hw
    if out.mean() > 0.5:
        return "arm" if float(path[out, 2].mean()) > zlow else "leg"
    dy = float(path[:, 1].mean()) - y0
    return "front" if dy < -SIDE_M else "back" if dy > SIDE_M else "side"


def row(B: dict, decl: dict, step3: dict | None) -> dict:
    """Row `place` (module docstring)."""
    from . import draft_tapes, tape_geom
    rid = {"id": "place", "back_to": "4", "target": "each piece's place {to, side} where its own tapes were taken"}
    T = tape_geom.tapes(step3)
    loops = [np.asarray(t["loop"], float) for t in T.values() if t.get("kind") == "loop"]
    torso = [L for L in loops if abs(float(L[:, 0].mean())) < 0.03]
    if not torso:
        return dict(rid, status="INFO", value="no step-3 torso girth: places not read")
    y0 = float(np.mean([L[:, 1].mean() for L in torso]))
    hw = max(float(np.abs(L[:, 0]).max()) for L in torso)
    zlow = min(float(L[:, 2].mean()) for L in torso)
    said, fails = [], []
    for p, pc in B["pieces"].items():
        votes = {}
        for n in draft_tapes.names_of(decl, p):
            if (T.get(n) or {}).get("kind") == "path":
                votes.setdefault(_where(np.asarray(T[n]["path"], float), y0, hw, zlow), []).append(n)
        w = pc.get("wrap") or {}
        to, side = str(w.get("to", "")), w.get("side")
        if side is not None and side not in SIDES:
            fails.append(f"{p}: place.side {side!r}: one of {', '.join(SIDES)}")
        if not votes:
            said.append(f"{p}: {to or '?'}{'/' + side if side else ''} (no length tape of its own: not read)")
            continue
        best = max(votes, key=lambda k: len(votes[k]))
        ns = sorted((len(v) for v in votes.values()), reverse=True)
        if len(ns) > 1 and ns[0] == ns[1]:
            said.append(f"{p}: {to}{'/' + side if side else ''} (its tapes don't decide: "
                        + "; ".join(f"{k} {', '.join(v)}" for k, v in votes.items()) + ")")
            continue
        why = ", ".join(votes[best])
        limb = any(x in to for x in LIMB_WORDS)
        if best in LIMB_WORDS:
            sd = p[-1] if p[-2:] in (".L", ".R") else ""
            want = f"{best}.{sd}" if sd else best
            if not to.startswith(best):
                fails.append(f"{p}: placed {to or 'torso (the default)'}, its tapes ({why}) run along the {best}: "
                             f"declare place {{\"to\": \"{want}\"}}")
            said.append(f"{p}: {to} (tapes {why} on the {best})")
            continue
        if limb:
            fails.append(f"{p}: placed {to}, its tapes ({why}) lie on the torso: declare place {{\"to\": \"torso\", "
                         f"\"side\": \"{best}\"}}")
            continue
        if to.startswith("torso") and best in ("front", "back") and side != best:
            fails.append(f"{p}: place.side {side or 'missing (read as front)'}, its tapes ({why}) run down the {best}: "
                         f"declare place {{\"to\": \"torso\", \"side\": \"{best}\"}}")
            continue
        said.append(f"{p}: {to}/{side or 'front'} (tapes {why}: {best})")
    return dict(rid, status="FAIL" if fails else "PASS", value="; ".join(said), why="; ".join(fails),
                fix="declare each piece's place as the row says" if fails else "")
