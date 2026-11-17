"""garment_cut's TAPES and FOLDS of the flat (R3d, C495): what a cut piece knows because it was cut from the toile.

TAPES: each piece names the step-3 tapes it lies on (draft_tapes' `tapes` declaration, read by the flat gate's girths and
piece_tapes rows): a tape lies on a piece when at least MIN_PTS of its points (or of its mirror across x = 0: step 3
measures one side) have that piece's surface as their nearest within NEAR (the toile stands off the body by its ease).
A length (a path) a piece runs along is named; a girth (a loop) only where the piece CROSSES its plane (cloth CROSS
on both sides of it near the tape: a back lies below the neck girth, it does not go round it). A layer (a facing, a canvas) lies on
its host: it names its host's tapes. Nothing is declared by hand: the piece was cut from where the tapes were taken.
FOLDS: garment_cut's `folds` {piece: {fold name: edge}}: a planned fold (step 2's bend, e.g. a sleeve hem turned up)
along a cut edge of that piece: a press fold of the flat on the edge's ends ({name, piece, line: [edge.a, edge.b],
kind: press}); ".L" entries serve ".R"."""
from __future__ import annotations

import numpy as np

NEAR = 0.06   # m: a tape point lies on the piece whose surface is nearest it, within this (the toile's ease + slack)
MIN_PTS = 2   # tape points on a piece before it names that tape
EDGE_NEAR = 0.04  # m: a drafted piece's edge lies along a girth whose tape is this near it on average
MARK_NEAR_M = 0.015  # m: a fastening mark is mapped into the flat by the piece's points this near its height
CROSS = 0.02  # m: a girth crosses a piece when the piece has cloth this far on both sides of its plane, near the tape


def piece_tapes(pcs: dict, step3: dict, edges: dict | None = None) -> dict:
    """{piece: [step-3 tape names] | {edge: girth}} (module doc)."""
    from scipy.spatial import cKDTree
    from . import tape_geom
    T = tape_geom.tapes(step3)
    own = [p for p, f in pcs.items() if "host" not in f.get("rep", {})]
    C = np.concatenate([np.asarray(pcs[p]["V"], float)[np.asarray(pcs[p]["F"])].mean(1) for p in own])
    who = np.concatenate([np.full(len(pcs[p]["F"]), i) for i, p in enumerate(own)])
    kd = cKDTree(C)
    out = {p: [] for p in pcs}
    for n, t in sorted(T.items()):
        P = np.asarray(t.get("loop") if t.get("kind") == "loop" else t.get("path"), float).reshape(-1, 3)
        if not len(P):
            continue
        hits = {}
        loop = t.get("kind") == "loop"
        for Q in (P, P * [-1, 1, 1]):
            d, j = kd.query(Q)
            if loop:  # (a girth goes round a piece that crosses its plane: cloth on both sides of it, near the tape)
                c = Q.mean(0)
                nrm = np.linalg.svd(Q - c)[2][-1]
                near = kd.query_ball_point(Q, NEAR)
            for k in np.where(d < NEAR)[0]:
                i = who[j[k]]
                if loop:
                    sd = (C[[x for x in near[k] if who[x] == i]] - c) @ nrm
                    if not (sd.min() < -CROSS and sd.max() > CROSS):
                        continue
                hits[own[i]] = hits.get(own[i], 0) + 1
        for p, k in hits.items():
            if k >= MIN_PTS:
                out[p].append(n)
    loops = {n: np.asarray(t["loop"], float) for n, t in T.items() if t.get("kind") == "loop"}
    for p, f in pcs.items():
        h = f.get("rep", {}).get("host")
        if h:
            out[p] = list(out.get(h, []))
        elif f.get("rep", {}).get("drafted") and edges and loops:  # (a drafted piece laid on the body: its edges' tape)
            lp, V = np.asarray(f["lp"]), np.asarray(f["V"], float)
            em = {}
            for e, idx in edges.get(p, {}).items():
                E = V[lp[list(idx)]]
                dist = {n: min(float(cKDTree(L).query(E)[0].mean()), float(cKDTree(L * [-1, 1, 1]).query(E)[0].mean()))
                        for n, L in loops.items()}
                n = min(dist, key=dist.get)
                if dist[n] < EDGE_NEAR:
                    em[e] = (n, dist[n])
            if em:
                best = min(em.values(), key=lambda x: x[1])[0]
                out[p] = {e: n for e, (n, _) in em.items() if n == best}
    return out


def folds(decl: dict, edges: dict) -> tuple[list, list]:
    """(folds, bad): the declared planned folds along cut edges (module doc)."""
    from .cut_made import _mir
    dd = dict(decl.get("folds") or {})
    for p, v in list(dd.items()):
        if p.endswith(".L") and _mir(p) not in dd:
            dd[_mir(p)] = v
    out, bad = [], []
    for p, mp in dd.items():
        for name, e in (mp or {}).items():
            if e not in edges.get(p, {}):
                bad.append(f"folds.{p}.{name}: {e!r} is not an edge of {p} (have {', '.join(sorted(edges.get(p, {})))})")
                continue
            out.append({"name": name, "piece": p, "line": [f"{e}.a", f"{e}.b"], "kind": "press", "edge": e})
    return out, bad


def places(pcs: dict, step3: dict) -> dict:
    """{piece: wrap {to, side?}}: where each piece lies on the toile, read as draft_place reads a tape (its own surface
    in front of / behind / beside the torso's girths, or along a limb); a layer lies where its host does."""
    from . import draft_place, tape_geom
    T = tape_geom.tapes(step3)
    torso = [np.asarray(t["loop"], float) for t in T.values() if t.get("kind") == "loop"
             and abs(float(np.asarray(t["loop"], float)[:, 0].mean())) < 0.03]
    if not torso:
        return {}
    y0 = float(np.mean([L[:, 1].mean() for L in torso]))
    hw = max(float(np.abs(L[:, 0]).max()) for L in torso)
    zlow = min(float(L[:, 2].mean()) for L in torso)
    out = {}
    for p, f in pcs.items():
        w = draft_place._where(np.asarray(f["V"], float), y0, hw, zlow)
        sd = p[-1] if p[-2:] in (".L", ".R") else ""
        out[p] = {"to": f"{w}.{sd}" if sd else w} if w in draft_place.LIMB_WORDS else {"to": "torso", "side": w}
    for p, f in pcs.items():
        h = f.get("rep", {}).get("host")
        if h in out:
            out[p] = dict(out[h])
    return out


def closure_marks(B: dict, pcs: dict, opening: dict, edges: dict) -> list:
    """The closures' fastening marks (C496, C503), from step 4's numbers `opening`. CLOSED toile: both fronts cross the
    centre line (x = 0), so a button on the over front and its buttonhole on the under front sit where x = 0 crosses
    each piece at the button's height (opening.buttons_z), mapped into the flat by the piece's own 3D -> flat map (least
    squares over its points within MARK_NEAR_M). OPEN toile (worn open: the fronts don't reach centre front): the marks
    are placed on the CLOSED state (step 4's closed_buttons: from_edge_mm in from the front's edge, on centre front) and
    carried to each front: on its own flat, the point at the button's height on the closure's edge, stepped
    from_edge_mm square into the piece (where it is when closed). Written as the piece's marks and the closure's
    `pairs`. [why not]."""
    why = []
    carried = opening.get("closed_buttons") if opening.get("wear") == "open" else None
    if opening.get("wear") == "open" and opening.get("buttons_z") and not carried:
        return [f"closure: the toile is worn open with buttons but step 4 gives no closed_buttons: garment_toile "
                "opening.lap_mm (the buttons are placed on the closed state)"]
    for c in B.get("closures") or []:
        pairs = []
        rows = carried or [{"z": z} for z in sorted(opening.get("buttons_z") or (), reverse=True)]
        for k, bt in enumerate(rows):
            got = []
            for side, nm in (("over", f"button{k + 1}"), ("under", f"buttonhole{k + 1}")):
                p = c[side]
                uv = (_carried(pcs[p], edges[p].get(c["edge"][side].split(".")[0]), bt) if carried
                      else _on_centre(pcs[p], bt["z"]))
                if isinstance(uv, str):
                    why.append(f"closure {c['name']!r}: {p} {uv}")
                    break
                B["pieces"][p]["marks"][nm] = [float(uv[0]), float(uv[1])]
                got.append(nm)
            if len(got) == 2:
                pairs.append(got)
        if pairs:
            c["pairs"] = pairs
            if carried:
                c["carried"] = "from the closed state: " + ", ".join(f"z {b['z']} {b['from_edge_mm']} mm in from the edge"
                                                                     for b in carried)
    return why


def _on_centre(f, bz):
    V, U = f["V"], f["U"]
    ok = ~np.isnan(U[:, 0]) & (np.abs(V[:, 2] - bz) < MARK_NEAR_M) & (np.abs(V[:, 0]) < 2 * MARK_NEAR_M)
    if ok.sum() < 6 or not V[ok, 0].min() <= 0 <= V[ok, 0].max():
        return f"doesn't cross the centre line at the button's z {bz:.3f}"
    A = np.c_[V[ok][:, [0, 2]], np.ones(int(ok.sum()))]
    return np.array([0.0, bz, 1.0]) @ np.linalg.lstsq(A, U[ok], rcond=None)[0]


def _carried(f, idx, bt):
    """The flat point from_edge_mm square in from the closure edge (positions idx of the piece's loop) at height z."""
    if not idx:
        return "has no closure edge to carry the button from"
    n = len(f["lp"])
    pos = list(idx) + [(idx[-1] + 1) % n]
    lp = np.asarray(f["lp"])
    Z, P = f["V"][lp[pos], 2], f["U"][lp[pos]]
    hit = [i for i in range(len(Z) - 1) if (Z[i] - bt["z"]) * (Z[i + 1] - bt["z"]) <= 0 and Z[i] != Z[i + 1]]
    if not hit:
        return f"its closure edge doesn't reach the button's z {bt['z']:.3f} ({Z.min():.3f}..{Z.max():.3f})"
    i = hit[0]
    w = (bt["z"] - Z[i]) / (Z[i + 1] - Z[i])
    q = P[i] + w * (P[i + 1] - P[i])
    tg = P[min(i + 2, len(P) - 1)] - P[max(i - 1, 0)]
    nv = np.array([-tg[1], tg[0]]) / np.linalg.norm(tg)
    from .draft_caught import _inside
    poly = f["U"][lp]
    d = float(bt["from_edge_mm"]) / 1000
    if not _inside((q + nv * min(d, 0.005))[None], poly)[0]:
        nv = -nv
    if not _inside((q + nv * d)[None], poly)[0]:
        return f"the button {bt['from_edge_mm']} mm in from its edge at z {bt['z']:.3f} falls outside the piece"
    return q + nv * d
