"""Closures: how a garment's openings are fastened, as construction (design-table / garment key `closures`).

A closure is a lap held by fastenings, not a seam: the `over` piece runs `band` past the closing line and lies on the
`under` piece, held where the buttons are. One entry makes everything that used to be written by hand in three places:

  {"name": "front", "kind": "buttons" | "zip" | "hooks" | "tie",
   "over": piece, "under": piece (the same piece for a cuff or a waistband closed on itself),
   "holes": "buttonhole", "buttons": "button"     marks <holes><n> on `over` paired with <buttons><n> on `under`,
                                                  n = 1.. while both exist; or "at": [[over mark, under mark], ...]
   "edge": {"over": "a>b", "under": "a>b"}        each piece's free edge along the closure (an outline arc)
   "band": m | {"over": m, "under": m}            the placket's width from that edge: a vertex row is put on its
                                                  inner line (so the layered band has a crisp edge) and the finished
                                                  surface stands `lift` proud there (the placket's extra layers)
   "seam": [arc a, arc b], "from", "to"           a zip: the part of a seam it closes (sewn when closed)
   "size": m (button diameter, default 0.011), "lift": m (default 0.0008),
   "gap": m (a piece closed on itself worn OPEN: how far its ends stand apart, a collar's stand at the throat),
   "state": "closed" | "open" | {"open_above": mark of `over`} | {"open_top": n} (the n highest fastenings undone:
            a shirt worn without a tie has its top front button open, whatever its marks are called)}

`expand` turns the entries into stitches (one per fastening that is closed), fold-line rows for the bands and seams
for closed zips; `cloth.mesh` records each closure's vertex pairs (`M["closures"]`); after the sim `measure` says per
closure how many fastenings hold and how far apart their two sides are, `relief` raises the bands, and `buttons_mesh`
makes the buttons as small geometry on the over layer (on the under layer where the closure is open).
"""
from __future__ import annotations

import math

import numpy as np

KINDS = ("buttons", "zip", "hooks", "tie")
KEYS = {"name", "kind", "over", "under", "holes", "buttons", "at", "edge", "band", "seam", "from", "to", "size", "lift",
        "state", "gap", "finish", "topstitch", "hole", "button"}
FINISHES = ("box", "french", "facing", "plain")
# how a band is made (what the outside shows; detail maps): "box" = a box placket (the edge folded out and back so a
# band of three layers stands proud with a crisp fold at its inner edge, a row of topstitching `topstitch` in from
# each edge); "french" = a French front (the facing folded inside: a rounded fold at the edge, no band, no rows);
# "facing" = a faced edge topstitched once `topstitch` in; "plain" = nothing drawn. Default: box on the over side,
# french under.
BUTTON = {"holes": 4, "color": None, "roughness": 0.42, "thickness": 0.0021}
# a sew-through button: 4 (or 2) holes, flat with a low rim and a dished middle, `thickness` m; colour None = the
# garment's detail.button (else a pearl white); roughness 0.42 = matte pearl / corozo (a polished dome read as a rivet)
GAP_MAX = 0.006  # m: a closed fastening's two sides further apart than this isn't closed


class ClosureError(ValueError):
    pass


def _has(pc: dict, mark: str) -> bool:
    return mark in (pc.get("marks") or {}) or mark in pc["names"]


def _y(pc: dict, mark: str) -> float:
    mk = pc.get("marks") or {}
    return float(mk[mark][1]) if mark in mk else float(pc["P"][pc["names"][mark], 1])


def validate(entries, where: str = "closures") -> None:
    if not isinstance(entries, list):
        raise ClosureError(f"{where}: a list of closures ({{name, kind, over, under, ...}})")
    seen = set()
    for c in entries:
        if not isinstance(c, dict) or not c.get("name") or not c.get("over"):
            raise ClosureError(f'{where}: each closure needs "name" and "over" (the lapping piece)')
        bad = set(c) - KEYS
        if bad:
            raise ClosureError(f"{where} {c['name']!r}: unknown keys {sorted(bad)} (have {sorted(KEYS)})")
        if c.get("kind", "buttons") not in KINDS:
            raise ClosureError(f"{where} {c['name']!r}: kind is one of {', '.join(KINDS)}")
        st = c.get("state", "closed")
        if not (st in ("closed", "open") or (isinstance(st, dict) and set(st) in ({"open_above"}, {"open_top"}))):
            raise ClosureError(f'{where} {c["name"]!r}: state is "closed", "open", {{"open_above": mark}} or {{"open_top": n}}')
        fin = c.get("finish")
        if fin is not None:
            vals = list(fin.values()) if isinstance(fin, dict) else [fin]
            if (isinstance(fin, dict) and set(fin) - {"over", "under"}) or any(v not in FINISHES for v in vals):
                raise ClosureError(f'{where} {c["name"]!r}: finish is one of {", ".join(FINISHES)} or {{"over": .., "under": ..}}')
        if c.get("hole", "auto") not in ("auto", "along", "across"):
            raise ClosureError(f'{where} {c["name"]!r}: hole is "along" (along the band edge: a placket\'s vertical '
                               f'holes), "across" or "auto"')
        if c.get("button") is not None and (not isinstance(c["button"], dict) or set(c["button"]) - set(BUTTON)):
            raise ClosureError(f'{where} {c["name"]!r}: button is {{{", ".join(BUTTON)}}}')
        if c["name"] in seen:
            raise ClosureError(f"{where}: two closures named {c['name']!r}")
        seen.add(c["name"])


def expand(entries: list, pcs: dict) -> tuple[list, list, list, list]:
    """(stitches, folds, seams, closures resolved against the pieces). Closures whose pieces were dropped are left
    out; a closure whose marks don't exist raises (a chosen closure must be in the pattern)."""
    stitches, folds, seams, out = [], [], [], []
    for c in entries or []:
        over, under = c["over"], c.get("under", c["over"])
        if over not in pcs or under not in pcs:
            continue
        kind = c.get("kind", "buttons")
        state = c.get("state", "closed")
        pairs = []
        if c.get("at"):
            pairs = [(str(a), str(b)) for a, b in c["at"]]
        elif kind != "zip":
            ho, bu = c.get("holes", "buttonhole"), c.get("buttons", "button")
            n = 1
            while _has(pcs[over], f"{ho}{n}") and _has(pcs[under], f"{bu}{n}"):
                pairs.append((f"{ho}{n}", f"{bu}{n}"))
                n += 1
        for a, b in pairs:
            if not _has(pcs[over], a) or not _has(pcs[under], b):
                raise ClosureError(f"closure {c['name']!r}: no mark {over}:{a} / {under}:{b}")
        if kind != "zip" and not pairs:
            raise ClosureError(f"closure {c['name']!r}: no fastenings found (marks {c.get('holes', 'buttonhole')}<n> on "
                               f"{over} with {c.get('buttons', 'button')}<n> on {under}, or 'at': [[over mark, under mark]])")
        closed = []
        top_open = set()
        if isinstance(state, dict) and "open_top" in state:  # the n highest fastenings (by their mark on `over`)
            top_open = set(sorted(pairs, key=lambda p_: -_y(pcs[over], p_[0]))[:int(state["open_top"])])
        for a, b in pairs:
            is_closed = state == "closed" or (isinstance(state, dict) and (
                (a, b) not in top_open if "open_top" in state else
                _y(pcs[over], a) <= _y(pcs[over], state["open_above"]) + 1e-9))
            closed.append(bool(is_closed))
            if is_closed:
                stitches.append([f"{over}:{a}", f"{under}:{b}"])
        if kind == "zip" and c.get("seam") and state == "closed":
            seams.append(list(c["seam"]))
        band = c.get("band")
        edge = c.get("edge") or {}
        for side, piece in (("over", over), ("under", under)):
            w = band.get(side) if isinstance(band, dict) else band
            if w and edge.get(side) and not (side == "under" and under == over):
                folds.append({"name": f"{c['name']} band {piece}", "piece": piece, "line": {"edge": edge[side], "offset": float(w)},
                              "angle": 180, "kind": "press", "strength": 0.0, "in_wrap": True, "band": True})
        out.append({"name": c["name"], "kind": kind, "over": over, "under": under, "pairs": pairs, "closed": closed,
                    "edge": edge, "band": band, **({"seam": list(c["seam"])} if c.get("seam") else {}), "size": float(c.get("size", 0.011)), "lift": float(c.get("lift", 0.0008)),
                    "state": state, **({"gap": float(c["gap"])} if c.get("gap") is not None else {}),
                    "finish": _finish(c), "topstitch": float(c.get("topstitch", 0.003)), "hole": c.get("hole", "auto"),
                    "button": dict(BUTTON, **(c.get("button") or {}))})
    return stitches, folds, seams, out


def _finish(c: dict) -> dict:
    f = c.get("finish")
    if isinstance(f, str):
        return {"over": f, "under": f}
    return {"over": "box", "under": "french", **(f or {})}


def edge_lines(c: dict, pcs: dict) -> dict:
    """{side: the closure edge's polyline in its piece's pattern coordinates (k, 2)} for each side with an edge."""
    from . import pattern
    out = {}
    for side in ("over", "under"):
        arc = (c.get("edge") or {}).get(side)
        pc = pcs.get(c.get(side))
        if arc and pc is not None:
            try:
                out[side] = np.asarray(pc["P"][pattern.arc_indices(pc, arc)], float)
            except (KeyError, ValueError):
                pass
    return out


def resolve(closures: list, marks: dict, points: dict, seams: list | None = None, sew=None, sew_seam=None,
            pcs: dict | None = None) -> list:
    """Each closure with its fastenings' vertex pairs (`v`: [[over vertex, under vertex], ...]; a mark the mesh
    dropped is left out and counted in `lost`). A closed zip's fastenings are its seam's sewn pairs (it is sewn
    shut: without them the report read "0 of 0 closed" and never checked the fly)."""
    out = []
    for c in closures or []:
        v, ok, lost = [], [], 0
        if c.get("kind") == "zip" and c.get("seam") and c.get("state", "closed") == "closed" and seams is not None \
                and sew is not None and len(sew):
            si = [i for i, sd in enumerate(seams) if list(sd) == list(c["seam"])]
            if si:
                pr = np.asarray(sew, np.int64).reshape(-1, 2)[np.isin(np.asarray(sew_seam), si)]
                out.append(dict(c, v=pr.tolist(), closed=[True] * len(pr), lost=0))
                continue
        for (a, b), cl in zip(c["pairs"], c["closed"]):
            va = marks.get(f"{c['over']}:{a}", points.get(f"{c['over']}:{a}"))
            vb = marks.get(f"{c['under']}:{b}", points.get(f"{c['under']}:{b}"))
            if va is None or vb is None:
                lost += 1
                continue
            v.append([int(va), int(vb)])
            ok.append(cl)
        out.append(dict(c, v=v, closed=ok, lost=lost, **({"edge_xy": edge_lines(c, pcs)} if pcs else {})))
    return out


def measure(V: np.ndarray, M: dict) -> list:
    """Per closure: fastenings, how many are closed, the gap between their two sides (mm) and whether it holds."""
    rows = []
    for c in M.get("closures") or []:
        v = np.asarray(c["v"], np.int64).reshape(-1, 2)
        cl = np.asarray(c["closed"], bool)
        d = np.linalg.norm(V[v[:, 0]] - V[v[:, 1]], axis=1) * 1000 if len(v) else np.zeros(0)
        dc = d[cl] if len(d) else d
        ok = bool(len(v) and c["lost"] == 0 and (not len(dc) or dc.max() <= GAP_MAX * 1000))
        rows.append({"name": c["name"], "kind": c["kind"], "over": c["over"], "under": c["under"], "fastenings": int(len(v)),
                     "closed": int(cl.sum()), "lost": int(c["lost"]), "state": c["state"],
                     "gap_mm": [round(float(x), 1) for x in dc],
                     "gap_max_mm": round(float(dc.max()), 1) if len(dc) else None, "ok": ok})
    return rows


def text(rows: list) -> str:
    L = []
    for r in rows:
        st = "open" if r["state"] == "open" else f"{r['closed']} of {r['fastenings']} closed"
        gap = "" if r["gap_max_mm"] is None else f", sides {r['gap_max_mm']} mm apart at most (closed <= {GAP_MAX * 1000:.0f})"
        lost = f", {r['lost']} fastenings LOST in the mesh" if r["lost"] else ""
        L.append(f"  {'ok ' if r['ok'] else '!! '}closure {r['name']} ({r['kind']}, {r['over']} over {r['under']}): {st}{gap}{lost}")
    return "\n".join(L)


def _out_normals(V: np.ndarray, F: np.ndarray, body) -> np.ndarray:
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
    if body is not None and len(body.V):
        bn, tree = body.normals()
        flip = (vn * bn[tree.query(V)[1]]).sum(1) < 0
        vn[flip] *= -1
    return vn


def band_mask(M: dict, pcs: dict, c: dict, side: str) -> np.ndarray:
    """Vertices of the closure's `side` piece within its band of the free edge (pattern distance)."""
    from . import pattern
    piece = c[side]
    band = c.get("band")
    w = band.get(side) if isinstance(band, dict) else band
    arc = (c.get("edge") or {}).get(side)
    mask = np.zeros(len(M["uv"]), bool)
    if not w or not arc or piece not in M["names"]:
        return mask
    pc = pcs[piece]
    L = pc["P"][pattern.arc_indices(pc, arc)]
    sel = np.where(M["piece"] == M["names"].index(piece))[0]
    P = M["uv"][sel]
    seg = L[1:] - L[:-1]
    L2 = np.maximum((seg * seg).sum(1), 1e-18)
    f = np.clip(((P[:, None] - L[None, :-1]) * seg[None]).sum(2) / L2[None], 0, 1)
    d = np.linalg.norm(P[:, None] - (L[None, :-1] + seg[None] * f[..., None]), axis=2).min(1)
    mask[sel[d <= float(w) + 5e-4]] = True
    return mask


LAY = 0.002  # m: how far a closed lap's over layer lies off the under layer (at 1.2 mm 1 cm facets cut through each other)
SEAT_REACH = 0.03  # m past the band's inner line over which the over layer eases back to where the sim left it
SEAT_MAX = 0.008  # m: a lap further open than this isn't a lap lying a little proud (the fronts parting above the
# top button were 2-5 cm apart and at 20 mm some of that was "laid" 18 mm): left as the sim has it


def _edge_dist(M: dict, pcs: dict, piece: str, arc: str) -> tuple[np.ndarray, np.ndarray]:
    """(vertex ids of `piece`, their pattern distance from its outline arc)."""
    from . import pattern
    pc = pcs[piece]
    L = pc["P"][pattern.arc_indices(pc, arc)]
    sel = np.where(M["piece"] == M["names"].index(piece))[0]
    P = M["uv"][sel]
    seg = L[1:] - L[:-1]
    L2 = np.maximum((seg * seg).sum(1), 1e-18)
    f = np.clip(((P[:, None] - L[None, :-1]) * seg[None]).sum(2) / L2[None], 0, 1)
    return sel, np.linalg.norm(P[:, None] - (L[None, :-1] + seg[None] * f[..., None]), axis=2).min(1)


def _closest_on(P: np.ndarray, V: np.ndarray, F: np.ndarray, k: int = 12) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(closest point on the triangles F of V, that triangle's unit normal, whether the point projects inside a
    triangle: not clamped onto the mesh's edge) for each P; the k triangles with the nearest centres are tried."""
    from scipy.spatial import cKDTree
    A_, B_, C_ = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    _, idx = cKDTree((A_ + B_ + C_) / 3).query(P, k=min(k, len(F)))
    idx = idx.reshape(len(P), -1)
    best = np.full(len(P), np.inf)
    Q, N, inside = np.zeros((len(P), 3)), np.zeros((len(P), 3)), np.zeros(len(P), bool)
    for j in range(idx.shape[1]):
        A, B, C = A_[idx[:, j]], B_[idx[:, j]], C_[idx[:, j]]
        ab, ac, ap = B - A, C - A, P - A
        d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
        d00, d01, d11 = (ab * ab).sum(1), (ab * ac).sum(1), (ac * ac).sum(1)
        den = d00 * d11 - d01 * d01
        den = np.where(np.abs(den) > 1e-18, den, 1e-18)
        v0, w0 = (d11 * d1 - d01 * d2) / den, (d00 * d2 - d01 * d1) / den
        ins = (v0 >= -1e-6) & (w0 >= -1e-6) & (v0 + w0 <= 1 + 1e-6)
        v, w = np.clip(v0, 0, 1), np.clip(w0, 0, 1)
        sm = np.maximum(v + w, 1.0)
        v, w = v / sm, w / sm
        q = A + v[:, None] * ab + w[:, None] * ac
        d = np.linalg.norm(P - q, axis=1)
        m = d < best
        n = np.cross(ab, ac)
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        best[m], Q[m], N[m], inside[m] = d[m], q[m], n[m], ins[m]
    return Q, N, inside


def seat(V: np.ndarray, M: dict, pcs: dict, body, fixed: np.ndarray | None = None) -> tuple[np.ndarray, list]:
    """A closed lap lies closed: construction, not a solve. Between the first and last closed fastening of a lap of
    two pieces, the over piece's band is laid `LAY` off the under piece's surface along that surface's normal
    (a contact solver holds two layers its contact gap apart, 3-7 mm at 1-2 cm triangles: a placket stood off the
    shirt like a board), easing back to the sim's surface over `SEAT_REACH` past the band; then each closed
    fastening's two sides are brought together in the surface (half the way each, falling off over ~2.5 cm) where
    the solver's stitch left them a few mm apart. Laps open more than `SEAT_MAX`, self-closures (a cuff) and
    `fixed` vertices (made pieces) are left alone. Returns (V, rows: per closure what it moved and what it left)."""
    X = np.array(V, float)
    rows = []
    bn_ = tree = None
    if body is not None and len(body.V):
        bn_, tree = body.normals()
    fx = None if fixed is None else np.asarray(fixed, bool)
    for c in M.get("closures") or []:
        if c["over"] == c["under"] or c["kind"] not in ("buttons", "hooks", "zip") or not len(c["v"]):
            continue
        band, edge = c.get("band"), c.get("edge") or {}
        w_o = band.get("over") if isinstance(band, dict) else band
        vv = np.asarray(c["v"], np.int64).reshape(-1, 2)
        cl = np.asarray(c["closed"], bool)
        if not w_o or not edge.get("over") or not cl.any():
            continue
        ku = M["names"].index(c["under"])
        Fu = M["F"][(M["piece"][M["F"]] == ku).all(1)]
        sel, d = _edge_dist(M, pcs, c["over"], edge["over"])
        # along the lap only between the closed fastenings (+ 2 cm): above an open collar and below the last button
        # the fronts part, as worn
        yb = M["uv"][vv[cl, 0], 1]
        y = M["uv"][sel, 1]
        along = np.clip((y - (yb.min() - 0.025)) / 0.02, 0, 1) * np.clip(((yb.max() + 0.025) - y) / 0.02, 0, 1)
        t = np.clip((d - float(w_o)) / SEAT_REACH, 0, 1)
        wgt = along * (1 - t * t * (3 - 2 * t))
        act = wgt > 1e-3
        if fx is not None:
            act &= ~fx[sel]
        if not act.any() or not len(Fu):
            continue
        ids = sel[act]
        moved = np.zeros(len(ids))
        N = np.zeros((len(ids), 3))

        def lay(rounds):
            nonlocal N, moved
            for _ in range(rounds):  # (the nearest point of the under layer shifts as the over layer comes down)
                Q, N, ins = _closest_on(X[ids], X, Fu)
                if bn_ is not None:
                    flip = (N * bn_[tree.query(Q)[1]]).sum(1) < 0
                    N[flip] *= -1
                gap = ((X[ids] - Q) * N).sum(1)
                ok = ins & (np.abs(gap) < SEAT_MAX) & (np.linalg.norm(X[ids] - Q, axis=1) < SEAT_MAX)
                mv = np.where(ok, (LAY - gap) * wgt[act], 0.0)
                X[ids] += N * mv[:, None]
                moved = moved + np.abs(mv)
        lay(2)
        # the fastenings themselves: each side half the way, within its own piece (pattern distance)
        left = []
        pos = {int(v): i for i, v in enumerate(ids)}
        for (va, vb), is_cl in zip(vv, cl):
            if not is_cl:
                continue
            # the button's own two sides: the over side LAY off the under side along the body's normal there (the
            # band's lay above doesn't reach a top button whose sides the sim left 10 mm apart)
            n_ = N[pos[int(va)]] if int(va) in pos else np.zeros(3)
            if bn_ is not None:
                n_ = bn_[tree.query(X[vb])[1]]
            dv_t = X[vb] + n_ * LAY - X[va]
            g_ = float(np.linalg.norm(dv_t))
            if g_ < 3e-4:
                left.append(0.0)
                continue
            if g_ > 0.012:
                left.append(round(g_ * 1000, 1))
                continue
            for v0, sgn in ((va, 0.5), (vb, -0.5)):
                s_ = np.where(M["piece"] == M["piece"][v0])[0]
                if fx is not None:
                    s_ = s_[~fx[s_]]
                r_ = np.linalg.norm(M["uv"][s_] - M["uv"][v0], axis=1)
                X[s_] += sgn * dv_t[None] * np.exp(-0.5 * (r_ / 0.025) ** 2)[:, None]
            left.append(0.0)
        # the band laid on the under layer again: bringing a fastening's sides together moves both layers round it
        # (half each, over ~2.5 cm), and laid only before that the over band came out through the under one round
        # su_garrett's 4th and 5th buttons (96 crossings: the clean-up's revert left those two 9 mm open)
        lay(2)
        rows.append({"name": c["name"], "laid": int(act.sum()), "moved_p50_mm": round(float(np.median(moved)) * 1000, 2),
                     "moved_max_mm": round(float(moved.max()) * 1000, 2), "fastenings_left_mm": left})
    return X, rows


def relief(V: np.ndarray, M: dict, pcs: dict, body) -> np.ndarray:
    """The finished surface with every closure's bands `lift` proud (a placket is the cloth turned twice and stitched:
    three layers where the front is one). The band's inner line is a vertex row (expand's fold row), so the step is
    one triangle edge wide."""
    X = np.array(V, float)
    cs = [c for c in M.get("closures") or [] if c.get("band")]
    if not cs:
        return X
    vn = _out_normals(X, M["F"], body)
    for c in cs:
        for side in ("over", "under"):
            if side == "under" and c["under"] == c["over"]:
                continue
            m = band_mask(M, pcs, c, side)
            X[m] += vn[m] * c["lift"] * (1.0 if side == "over" else 0.5)
    return X




def hole_axis(c: dict, M: dict, va: int, vb: int) -> np.ndarray:
    """A buttonhole's long axis in pattern coordinates (unit 2-vector). Where the closure has an edge (a shirt's
    placket) the holes run ALONG it (vertical on a placket); on a piece closed on itself (a cuff, a stand, a
    waistband) from the button toward the buttonhole (holes run the way the strain pulls). "across" turns either a
    quarter turn."""
    mode = c.get("hole", "auto")
    e = (c.get("edge_xy") or {}).get("over")
    d = None
    if e is not None and len(e) > 1:
        d = np.asarray(e[-1], float) - np.asarray(e[0], float)
    elif "uv" in M and va is not None and vb is not None and M["piece"][va] == M["piece"][vb]:
        d = np.asarray(M["uv"][va], float) - np.asarray(M["uv"][vb], float)
    if d is None or np.linalg.norm(d) < 1e-4:
        d = np.array([0.0, 1.0])
    d = d / np.linalg.norm(d)
    if mode == "across":
        d = np.array([-d[1], d[0]])
    return d


def _surface_dir(V: np.ndarray, M: dict, v: int, d2: np.ndarray, reach: float = 0.025) -> np.ndarray | None:
    """The 3D direction the pattern direction d2 takes on the surface at vertex v (least-squares map uv -> 3D over
    the piece's vertices within `reach` in the pattern)."""
    if "uv" not in M or "piece" not in M:
        return None
    sel = np.where(M["piece"] == M["piece"][v])[0]
    du = M["uv"][sel] - M["uv"][v]
    near = sel[np.linalg.norm(du, axis=1) < reach]
    if len(near) < 3:
        return None
    A = np.c_[M["uv"][near] - M["uv"][v], np.ones(len(near))]
    J, *_ = np.linalg.lstsq(A, V[near] - V[v], rcond=None)
    t = J[0] * d2[0] + J[1] * d2[1]
    n = np.linalg.norm(t)
    return t / n if n > 1e-9 else None


def _button(p: np.ndarray, n: np.ndarray, ax: np.ndarray, r: float, th: float, holes: int, segs: int = 28):
    """One sew-through button: (V, F). A flat disc `th` thick: a rounded rim standing a little proud, a dished middle
    with `holes` sunk holes (4 in a square, 2 across the axis) and the thread's bars between them (along `ax`)."""
    from scipy.spatial import Delaunay
    b_ = ax - n * (ax @ n)
    b_ /= np.linalg.norm(b_)
    t_ = np.cross(b_, n)
    W = lambda x, y, h: p + t_ * x + b_ * y + n * h  # x across, y along, h up
    ang = np.linspace(0, 2 * np.pi, segs, endpoint=False)
    cs, sn = np.cos(ang), np.sin(ang)
    prof = [(1.0, 0.0), (1.0, 0.5), (0.97, 0.82), (0.9, 1.0), (0.8, 0.96), (0.7, 0.74)]  # (radius share, height share)
    Vs, F = [], []
    for rr, hh in prof:
        Vs += [W(rr * r * c, rr * r * s, hh * th) for c, s in zip(cs, sn)]
    for k in range(len(prof) - 1):
        for i in range(segs):
            a0, a1 = k * segs + i, k * segs + (i + 1) % segs
            F += [(a0, a1, a1 + segs), (a0, a1 + segs, a0 + segs)]
    h0 = prof[-1][1] * th  # the middle's level
    rin = prof[-1][0] * r
    ring0 = (len(prof) - 1) * segs
    # the middle: Delaunay over the rim's inner ring, the holes' rings and a few points between; triangles inside a
    # hole dropped
    off = 0.25 * r
    hc = [(-off, -off), (off, -off), (off, off), (-off, off)] if holes >= 4 else [(-off, 0.0), (off, 0.0)]
    hr, hs = 0.14 * r, 10
    pts = [(rin * c, rin * s) for c, s in zip(cs, sn)]
    hring = []
    for cx, cy in hc:
        hring.append(len(pts))
        pts += [(cx + hr * np.cos(a), cy + hr * np.sin(a)) for a in np.linspace(0, 2 * np.pi, hs, endpoint=False)]
    pts += [(0.0, 0.0)] + [(0.6 * r * np.cos(a), 0.6 * r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 12, endpoint=False)]
    pts = np.asarray(pts)
    base = len(Vs)
    # (the rim's inner ring is shared: its vertices are ring0 .. ring0 + segs)
    idx = np.r_[np.arange(ring0, ring0 + segs), base + np.arange(len(pts) - segs)]
    Vs += [W(x, y, h0) for x, y in pts[segs:]]
    for tri in Delaunay(pts).simplices:
        cxy = pts[tri].mean(0)
        if np.hypot(*cxy) > rin * 0.999 or any(np.hypot(cxy[0] - hx, cxy[1] - hy) < hr * 0.999 for hx, hy in hc):
            continue
        F.append(tuple(idx[tri]))
    # the holes: walls down nearly to the cloth, a floor
    walls = []
    for j, (cx, cy) in enumerate(hc):
        top = idx[hring[j]: hring[j] + hs]
        b0 = len(Vs)
        Vs += [W(cx + hr * np.cos(a), cy + hr * np.sin(a), 0.05 * h0) for a in np.linspace(0, 2 * np.pi, hs, endpoint=False)]
        for i in range(hs):
            walls += [(top[i], top[(i + 1) % hs], b0 + (i + 1) % hs, j), (top[i], b0 + (i + 1) % hs, b0 + i, j)]
        ctr = len(Vs)
        Vs.append(W(cx, cy, 0.05 * h0))
        F += [(b0 + i, b0 + (i + 1) % hs, ctr) for i in range(hs)]
    # the thread: a bar along the axis between each pair of holes, standing a little over the middle
    bw, bh = 0.03 * r, 0.12 * th
    pairs = [(0, 3), (1, 2)] if holes >= 4 else [(0, 1)]
    for a_, b2 in pairs:
        (x0, y0), (x1, y1) = hc[a_], hc[b2]
        L = np.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        px_, py_ = -uy * bw, ux * bw
        q = len(Vs)
        for (x, y) in ((x0, y0), (x1, y1)):
            Vs += [W(x + px_, y + py_, h0 * 0.5), W(x - px_, y - py_, h0 * 0.5),
                   W(x + px_, y + py_, h0 + 0.3 * bh), W(x - px_, y - py_, h0 + 0.3 * bh)]
        F += [(q + 2, q + 3, q + 7), (q + 2, q + 7, q + 6), (q + 0, q + 2, q + 6), (q + 0, q + 6, q + 4),
              (q + 1, q + 5, q + 7), (q + 1, q + 7, q + 3)]
    Vb = np.asarray(Vs)
    F = np.asarray(F, np.int64)
    # wound to face out (single-sided materials): away from a point under the button's middle; hole walls toward
    # their hole's axis
    below = p - n * 0.004
    fn = np.cross(Vb[F[:, 1]] - Vb[F[:, 0]], Vb[F[:, 2]] - Vb[F[:, 0]])
    flip = (fn * (Vb[F].mean(1) - below)).sum(1) < 0
    F[flip] = F[flip][:, [0, 2, 1]]
    if walls:
        Wf = np.asarray([w[:3] for w in walls], np.int64)
        hj = np.asarray([w[3] for w in walls])
        fn = np.cross(Vb[Wf[:, 1]] - Vb[Wf[:, 0]], Vb[Wf[:, 2]] - Vb[Wf[:, 0]])
        axis_pt = np.asarray([W(hc[j][0], hc[j][1], 0.0) for j in hj])
        to_axis = axis_pt - Vb[Wf].mean(1)
        to_axis -= np.outer(to_axis @ n, n)
        fl = (fn * to_axis).sum(1) < 0
        Wf[fl] = Wf[fl][:, [0, 2, 1]]
        F = np.r_[F, Wf]
    return Vb, F


def buttons_mesh(V: np.ndarray, M: dict, body, segs: int = 28) -> dict | None:
    """The buttons of every "buttons" closure as one small mesh ({"V", "F", "at": the vertex each sits on, "color",
    "roughness"}): flat sew-through buttons (`_button`: a low rim, a dished middle, 4 holes and the thread's bars) of
    the closure's `size`, sitting ON the cloth (their base on its surface) at the buttonhole where the fastening is
    closed (centred on the hole: it is sewn to the under layer's centre line under it), on the under layer at the
    button's own mark where it is open; turned so their holes square with the hole's axis (`hole_axis`)."""
    cs = [c for c in M.get("closures") or [] if c["kind"] == "buttons" and len(c["v"])]
    if not cs:
        return None
    V = np.asarray(V, float)
    vn = _out_normals(V, M["F"], body)
    Vs, Fs, at, mark = [], [], [], []
    n0 = 0
    color = rough = None
    for c in cs:
        bt = dict(BUTTON, **(c.get("button") or {}))
        r = 0.5 * c["size"]
        th = float(bt["thickness"]) * (c["size"] / 0.011) ** 0.5
        color = color or bt.get("color")
        rough = bt.get("roughness") if rough is None else rough
        for (va, vb), cl in zip(c["v"], c["closed"]):
            v = va if cl else vb
            n = vn[v]
            ax = _surface_dir(V, M, v, hole_axis(c, M, va, vb))
            if ax is None or abs(ax @ n) > 0.95:
                ax = np.cross(n, [1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.cross(n, [0.0, 1.0, 0.0])
            # on the surface (0.2 mm so it doesn't flicker into the cloth's facets), raised over any cloth standing
            # above its plane within its radius (a button where a roll starts was cut in half by the turning front)
            near = np.where(np.linalg.norm(V - V[v], axis=1) < 1.1 * r)[0]
            up = float(np.clip(((V[near] - V[v]) @ n).max(initial=0.0), 0.0, 0.003))
            p = V[v] + n * (0.0002 + up)
            Vb, F = _button(p, n, ax, r, th, int(bt["holes"]), segs)
            Vs.append(Vb)
            Fs.append(F + n0)
            at += [int(v)] * len(Vb)
            mark += [int(vb)] * len(Vb)
            n0 += len(Vb)
    return {"V": np.concatenate(Vs), "F": np.concatenate(Fs), "at": np.asarray(at, np.int64), "mark": np.asarray(mark, np.int64),
            "color": color, "roughness": float(rough if rough is not None else BUTTON["roughness"])}
