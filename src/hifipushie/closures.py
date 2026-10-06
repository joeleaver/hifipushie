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
   "state": "closed" | "open" | {"open_above": mark of `over`}}

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
        "state"}
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
        if not (st in ("closed", "open") or (isinstance(st, dict) and set(st) == {"open_above"})):
            raise ClosureError(f'{where} {c["name"]!r}: state is "closed", "open" or {{"open_above": mark}}')
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
        for a, b in pairs:
            is_closed = state == "closed" or (isinstance(state, dict) and _y(pcs[over], a) <= _y(pcs[over], state["open_above"]) + 1e-9)
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
                    "edge": edge, "band": band, "size": float(c.get("size", 0.011)), "lift": float(c.get("lift", 0.0008)),
                    "state": state})
    return stitches, folds, seams, out


def resolve(closures: list, marks: dict, points: dict) -> list:
    """Each closure with its fastenings' vertex pairs (`v`: [[over vertex, under vertex], ...]; a mark the mesh
    dropped is left out and counted in `lost`)."""
    out = []
    for c in closures or []:
        v, ok, lost = [], [], 0
        for (a, b), cl in zip(c["pairs"], c["closed"]):
            va = marks.get(f"{c['over']}:{a}", points.get(f"{c['over']}:{a}"))
            vb = marks.get(f"{c['under']}:{b}", points.get(f"{c['under']}:{b}"))
            if va is None or vb is None:
                lost += 1
                continue
            v.append([int(va), int(vb)])
            ok.append(cl)
        out.append(dict(c, v=v, closed=ok, lost=lost))
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


def buttons_mesh(V: np.ndarray, M: dict, body, segs: int = 14) -> dict | None:
    """The buttons of every "buttons" closure as one small mesh ({"V", "F", "at": the vertex each sits on}): a disc
    with a raised rim, on the over layer at its buttonhole where the fastening is closed, on the under layer at the
    button's own mark where it is open."""
    cs = [c for c in M.get("closures") or [] if c["kind"] == "buttons" and len(c["v"])]
    if not cs:
        return None
    vn = _out_normals(np.asarray(V, float), M["F"], body)
    Vs, Fs, at = [], [], []
    n0 = 0
    ang = np.linspace(0, 2 * np.pi, segs, endpoint=False)
    for c in cs:
        r = 0.5 * c["size"]
        for (va, vb), cl in zip(c["v"], c["closed"]):
            v = va if cl else vb
            n = vn[v]
            t = np.cross(n, [0.0, 0.0, 1.0])
            if np.linalg.norm(t) < 1e-6:
                t = np.cross(n, [1.0, 0.0, 0.0])
            t /= np.linalg.norm(t)
            b = np.cross(n, t)
            ring = np.outer(np.cos(ang), t) + np.outer(np.sin(ang), b)
            p = V[v] + n * (c["lift"] + 0.0004)
            # rings: base, top of the rim, inner edge of the rim, the dished middle; then the centre
            rows = [(r, 0.0), (r, 0.0018), (0.72 * r, 0.0020), (0.6 * r, 0.0012)]
            P = [p + ring * rr + n * hh for rr, hh in rows] + [(p + n * 0.0012)[None]]
            Vb = np.concatenate(P)
            F = []
            for k in range(len(rows) - 1):
                for i in range(segs):
                    a0, a1 = k * segs + i, k * segs + (i + 1) % segs
                    b0, b1 = a0 + segs, a1 + segs
                    F += [(a0, a1, b1), (a0, b1, b0)]
            ctr = len(rows) * segs
            for i in range(segs):
                F.append(((len(rows) - 1) * segs + i, (len(rows) - 1) * segs + (i + 1) % segs, ctr))
            F = np.asarray(F, np.int64)
            # faces wound to face out of the button (single-sided materials: glTF, engines)
            mid_ = p + n * 0.0009
            fn_ = np.cross(Vb[F[:, 1]] - Vb[F[:, 0]], Vb[F[:, 2]] - Vb[F[:, 0]])
            inward = (fn_ * (Vb[F].mean(1) - mid_)).sum(1) < 0
            F[inward] = F[inward][:, [0, 2, 1]]
            Vs.append(Vb)
            Fs.append(F + n0)
            at += [int(v)] * len(Vb)
            n0 += len(Vb)
    return {"V": np.concatenate(Vs), "F": np.concatenate(Fs), "at": np.asarray(at, np.int64)}
