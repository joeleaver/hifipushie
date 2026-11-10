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


def saved_row(model: str, garment: str) -> dict:
    """The `seam_links` row of a saved draft, read on the mesh the chain build makes of it."""
    from .chain_garment import load_garment
    try:
        M = load_garment(model, garment)[0].M
    except (ValueError, KeyError, FileNotFoundError) as e:  # (no body to mesh against: nothing the build could read)
        return {"id": "seam_links", "status": "INFO", "value": "n/a",
                "why": f"the build's mesh of this draft couldn't be made: {str(e)[:160]}", "source": "draft_links.py (C395)"}
    return row(M)


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
