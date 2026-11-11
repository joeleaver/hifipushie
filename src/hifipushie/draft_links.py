"""SEAM LINKS AT STEP 4 (C395): the flat gate FAILs what the chain build (step 5) refuses, so no approved pattern is
refused there.

Trial s5-1 / R3b (2026-11-10): the hussar's approved draft (step 4 PASS, approved) was refused by chain_garment at once:
"a seam's two sides differ by 4.865 mm over one link". The two-piece sleeve cap's underarm corner was cut 2.85 mm on one
side and 7.72 mm on the other. Step 4's truing row was INFO ("drafts are auto-trued in the build"), and it isn't trued: a
chain link between two sewn points is one length (chain_net: the mean of its sides), so the build refuses past
chain_core.SEAM_LINK_MM. The same Network the build makes is read here, on the build's OWN mesh of the saved draft
(chain_garment.load_garment: graded, trued as the build trues it), with the same number. The step's coarse flat mesh read
the hussar's corner as 15.1 mm where the build read 4.9: a link's error depends on the mesh, so only the build's mesh says
what the build will refuse.
"""
from __future__ import annotations

import numpy as np


def saved_rows(model: str, garment: str) -> list:
    """The `seam_links` and `seams_crossed` rows of a saved draft, read on the mesh the chain build makes of it."""
    from .chain_garment import load_garment
    try:
        M = load_garment(model, garment)[0].M
    except (ValueError, KeyError, FileNotFoundError) as e:  # (no body to mesh against: nothing the build could read)
        return [{"id": "seam_links", "status": "INFO", "value": "n/a",
                 "why": f"the build's mesh of this draft couldn't be made: {str(e)[:160]}", "source": "draft_links.py (C395)"}]
    return [row(M), crossed_row(M)]


def crossed_row(M: dict) -> dict:
    """The `seams_crossed` row (C403): the build's own START check (chain_placed.crossed) on its mesh of the draft: no
    node holds two points of one piece far apart on its flat. The suit jacket's draft passed seam_ends and was refused at
    step 5 with 13 crossed rows: two neck seams declared end to end the wrong way, and both armhole chains whose edges
    didn't follow on (the back armhole underarm -> shoulder, then the front armhole underarm -> shoulder again)."""
    from types import SimpleNamespace
    from .chain_core import pattern_from_mesh
    from .chain_net import Network
    from .chain_placed import CROSS, crossed
    pat = pattern_from_mesh(M)
    bad = crossed(SimpleNamespace(net=Network(pat.M, pat.stiff, pat.bend)))
    why = "; ".join(f"{n}:{a} and {n}:{c} ({mm} mm apart on {n}'s flat) sewn into one point through {', '.join(oth)}"
                    for n, lst in list(bad.items())[:6] for a, c, mm, oth in lst[:1])
    return {"id": "seams_crossed", "status": "FAIL" if bad else "PASS",
            "value": f"{len(bad)} pieces with points sewn together that lie apart",
            "target": f"no seam joins two points of one piece more than {CROSS * 1e3:.0f} mm apart on its flat (chain_garment "
                      "refuses it at its start)",
            "why": (why + ". A seam between those pieces runs end to end the wrong way round, or a chain side's edges don't "
                    "follow on: in a chain [e1, e2, ..] each edge starts where the one before it ended (where another seam "
                    "joins them: a back armhole ending at the shoulder is followed by the front armhole STARTING at the "
                    "shoulder). Flip that edge's direction (\"a>b\" -> \"b>a\") or reorder the chain, pattern_check again")
            if bad else "", "back_to": "4", "source": "chain_placed.crossed on the build's mesh (draft_links.py, C403)"}


def row(M: dict) -> dict:
    """The `seam_links` row: every seam's two sides within SEAM_LINK_MM over each link (the build's own check)."""
    from .chain_core import SEAM_LINK_MM, pattern_from_mesh
    from .chain_net import Network
    pat = pattern_from_mesh(M)
    net = Network(pat.M, pat.stiff, pat.bend)
    d = (net.link_cut[:, 1] - net.link_cut[:, 0]) * 1e3
    bad = np.where(d > SEAM_LINK_MM)[0]
    worst = bad[np.argsort(-d[bad])]
    names = net.names

    def where(k):
        sides = {names[int(net.piece[v])] for v in net.chain_v[net.link_of_chain == k].ravel()}
        lo, hi = net.link_cut[k] * 1e3
        return f"{' / '.join(sorted(sides))}: one side {lo:.2f} mm, the other {hi:.2f} mm"

    why = "; ".join(where(k) for k in worst[:4])
    return {"id": "seam_links", "status": "FAIL" if len(bad) else "PASS",
            "value": f"{round(float(d.max()), 2) if len(d) else 0.0} mm worst, {len(bad)} links over",
            "target": f"a seam's two sides within {SEAM_LINK_MM} mm over each link (chain_garment refuses past it)",
            "why": (why + ": true the seam ends there (the corner points of the two edges meet at the same place along "
                    "both; FreeSewing: the same curve control points on both pieces), pattern_check again") if why else "",
            "back_to": "4", "source": "chain_net.Network on the flat mesh, chain_core.SEAM_LINK_MM (draft_links.py, C395)"}
