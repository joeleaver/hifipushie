"""EVERY VERTEX PLACED (R3c2): the START stage's row that no vertex of a built piece is left where nothing put it.

R3c's suit jacket (2026-11-10) reached the chains gate with its chest canvases' 1103 points each at (0, 0, 0), 137 of its
collar ply's and 68-69 of each facing's with them, and came back as "length 9850 % off" and "held_length 77658 % off",
lines running to the floor. A length row can't say "never placed". This row does, at the start, by piece and count:
a point at the origin, or farther than OFF_BODY from the body, is one nothing placed (a ply, a floating layer, or a piece
sewn to one, left behind by the stage that should carry it: chain_holds.place_plies / place_layers).

The same jacket's collar seams were declared end to end the wrong way round (the undercollar's neck edge notch>shoulder
sewn to the front's neck edge shoulder>notch, the collar's gorge to the facing's likewise): the front's neck point and
its notch, 90 mm apart on the flat, became ONE node through the undercollar, and every chain there read 2700 % off.
`crossed:<piece>` names it at the start: two points of one piece (not sewn to itself) farther apart than CROSS on its
flat in one node.
"""
from __future__ import annotations

import numpy as np

OFF_BODY = 0.5  # m: no garment point starts this far from the body it is worn on (a sleeve's cuff hangs ~0.1 m off)
ORIGIN = 1e-9  # m: a point exactly here was never set (the build's X starts as zeros)
CROSS = 0.02  # m: two points of one piece this far apart on its flat can't be one node (a seam corner's are < a link)


def unplaced(b, X) -> dict:
    """{piece: (at the origin, farther than OFF_BODY from the body)} for every piece with any."""
    X = np.asarray(X, float)
    z = np.linalg.norm(X, axis=1) < ORIGIN
    far = (np.abs(b.body.contact.query(X)[0]) > OFF_BODY) & ~z
    out = {}
    for n in b.net.names:
        v = b.net.verts(n)
        a, f = int(z[v].sum()), int(far[v].sum())
        if a or f:
            out[n] = (a, f)
    return out


def placed_rows(b, X, row) -> tuple[list, dict]:
    """The start's `placed:<piece>` rows (row: chain_stages._row), one per piece with a point left unplaced."""
    bad = unplaced(b, X)
    H = getattr(b, "holds", None)
    rows = []
    for n, (a, f) in bad.items():
        kind = ("a ply of " + H.plies[n] if H is not None and n in H.plies else
                "a floating layer in " + H.layers[n] if H is not None and n in H.layers else "")
        rows.append(row(f"placed:{n}", a + f, 0, False,
                        f"every vertex of a built piece is placed by the start: {a} of {n}'s {len(b.net.verts(n))} points "
                        f"at the origin, {f} farther than {OFF_BODY} m from the body; limit none",
                        f"{n}{' (' + kind + ')' if kind else ''} has points nothing placed: the stage that carries it "
                        "(chain_holds.place_plies for a ply, place_layers for a floating layer, its seam to one for a piece "
                        "sewn there) left them; a build fault, not the pattern's: report it"))
    return rows, {n: list(v) for n, v in bad.items()}


def crossed(b) -> dict:
    """{piece: [(point a, point b, mm apart on the flat, the other pieces in the node)]}: nodes that hold two points of one
    piece far apart on its flat (a seam sewn end to end the wrong way round folds the piece onto itself). Pieces sewn to
    themselves (a tube's seam, a dart) are not read, nor a node where such a seam closes (a shirt's cuff, sewn round its
    one-piece sleeve, has its two ends there: 205 mm apart on its flat, one point worn)."""
    net, rs = b.net, b.net.root
    selfs = {int(net.piece[a]) for a, c in net.sew if net.piece[a] == net.piece[c]}
    cnt = np.bincount(rs, minlength=net.n)
    pts = {}
    for nm, i in (net.M.get("points") or {}).items():
        if isinstance(i, (int, np.integer)):
            pts.setdefault(int(i), nm.split(":", 1)[-1])
    out: dict = {}
    for node in np.where(cnt > 2)[0]:
        mem = np.where(rs == node)[0]
        pc = net.piece[mem]
        if any(int(q) in selfs and (pc == q).sum() > 1 for q in np.unique(pc)):
            continue  # (a tube's own seam closes what is sewn round it: a cuff's two ends meet there)
        for p in np.unique(pc):
            vs = mem[pc == p]
            if int(p) in selfs or len(vs) < 2:
                continue
            d = np.linalg.norm(net.uv[vs][:, None] - net.uv[vs][None], axis=2)
            a, c = np.unravel_index(int(np.argmax(d)), d.shape)
            if d[a, c] > CROSS:
                oth = sorted({net.names[q] for q in pc if q != p})
                out.setdefault(net.names[p], []).append((pts.get(int(vs[a]), str(int(vs[a]))), pts.get(int(vs[c]), str(int(vs[c]))),
                                                         round(float(d[a, c]) * 1e3), oth))
    return out


def crossed_rows(b, row) -> tuple[list, dict]:
    bad = crossed(b)
    rows = []
    for n, lst in bad.items():
        a, c, mm, oth = lst[0]
        rows.append(row(f"crossed:{n}", len(lst), 0, False,
                        f"a node is one point of cloth: {len(lst)} node(s) hold two of {n}'s points far apart on its flat "
                        f"(over {CROSS * 1e3:.0f} mm; first {n}:{a} and {n}:{c}, {mm} mm apart, through {', '.join(oth)}); "
                        "limit none",
                        f"a seam joining {n} to {' / '.join(oth)} is sewn end to end the wrong way round (its two edges run "
                        f"opposite ways), so {n}:{a} and {n}:{c} are sewn together: draft_pattern (step 4) with that seam's "
                        "edges running the same way, then chain_garment again"))
    return rows, {n: [list(x) for x in v] for n, v in bad.items()}
