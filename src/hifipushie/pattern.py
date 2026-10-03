"""Pattern pieces: 2D outlines in metres (x right, y up), named points, and the general 2D operations a pattern maker
does to them. Pieces come from a FreeSewing draft (`from_freesewing`) or are written directly in the spec
(`from_spec`: an outline of points and arcs, e.g. a tablecloth is one rectangle).

A piece: {"name", "P": (n, 2) closed outline (no repeated end), "names": {point name: outline index},
"marks": {name: (x, y)} (points inside or off the outline: buttons, pins), "lines": {name: (k, 2) polylines}
(fold, press, pleat, grain lines), "grain": angle (deg; 90 = straight grain along y)}.

Edges are addressed "piece:a>b" (the outline from point a to point b, the shorter way round) or "piece:a>via>b".
Ops (`alter`): `slash_spread` (cut along a line and open it by an amount, hinged at one end: the tailor's way to add
room for a belly, a round back, a full chest), `move` (named points), `turn` (cut along a fold line and keep one side:
a hem, a facing or a placket turned under), `scale` (lengthen/shorten along a line).
"""
from __future__ import annotations

import copy

import numpy as np

STEP = 0.003  # m: bezier flattening chord target


def _bezier(p0, c1, c2, p1, step=STEP):
    p0, c1, c2, p1 = (np.asarray(v, float) for v in (p0, c1, c2, p1))
    n = max(2, int(np.ceil((np.linalg.norm(c1 - p0) + np.linalg.norm(c2 - c1) + np.linalg.norm(p1 - c2)) / step)))
    t = np.linspace(0, 1, n + 1)[1:, None]
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * p1


def _dedupe(P, names):
    """Drop repeated consecutive points (and a closing repeat), keeping names on the survivors."""
    keep, remap = [], {}
    for i, p in enumerate(P):
        if keep and np.linalg.norm(p - P[keep[-1]]) < 1e-6:
            remap[i] = len(keep) - 1
            continue
        remap[i] = len(keep)
        keep.append(i)
    if len(keep) > 1 and np.linalg.norm(P[keep[0]] - P[keep[-1]]) < 1e-6:
        last = len(keep) - 1
        keep.pop()
        remap = {i: (0 if j == last else j) for i, j in remap.items()}
    out_names = {}
    for n, i in names.items():
        out_names.setdefault(n, remap[i])
    return np.asarray([P[i] for i in keep]), out_names


def _points_on_outline(P: np.ndarray, names: dict, pts: dict, tol: float = 2e-6) -> tuple:
    """Named points lying on the outline between its vertices (a pleat's fold marks along a waist edge) inserted as
    outline vertices, so seams can address them ("tail:cbTop>fold1Top")."""
    n = len(P)
    ins = {}  # edge index -> [(t, name, point)]
    for k, q in pts.items():
        A, B = P, np.roll(P, -1, axis=0)
        d = B - A
        L2 = np.maximum((d * d).sum(1), 1e-18)
        t = np.clip(((q - A) * d).sum(1) / L2, 0, 1)
        dist = np.linalg.norm(A + t[:, None] * d - q, axis=1)
        e = int(np.argmin(dist))
        if dist[e] < tol and 1e-4 < t[e] * np.sqrt(L2[e]) < np.sqrt(L2[e]) - 1e-4:
            ins.setdefault(e, []).append((float(t[e]), k, A[e] + t[e] * d[e]))
    if not ins:
        return P, names
    out, remap, extra = [], {}, {}
    for i in range(n):
        remap[i] = len(out)
        out.append(P[i])
        for t, k, q in sorted(ins.get(i, []), key=lambda r: r[0]):
            if np.linalg.norm(q - out[-1]) < 1e-6:
                extra[k] = len(out) - 1
                continue
            extra[k] = len(out)
            out.append(q)
    names = {k: remap[i] for k, i in names.items()}
    names.update(extra)
    return np.asarray(out), names


def _fs_xy(v):
    return np.array([v[0], -v[1]]) / 1000.0


def from_freesewing(part: dict, name: str, fold: str | None = None) -> dict:
    """A FreeSewing part's seam line as a piece. fold "x0": the part is half, cut on a fold at x = 0: mirrored whole,
    mirrored points named "<name>.m" (points on the fold keep their name). Unnamed outline points that mirror a named
    one (FreeSewing's own mirrored halves) get "<name>.m" too."""
    ops = part["paths"]["seam"]["ops"]
    pts = {k: _fs_xy(v) for k, v in part["points"].items() if v}
    P, names, cur = [], {}, None

    def name_at(q):
        hits = [k for k, v in pts.items() if np.linalg.norm(v - q) < 2e-6]
        hits.sort(key=lambda k: (k.startswith("__") or "|" in k, len(k)))
        return hits

    for o in ops:
        if o["type"] == "move":
            cur = _fs_xy(o["to"])
            P.append(cur)
            for k in name_at(cur):
                names.setdefault(k, len(P) - 1)
        elif o["type"] == "line":
            cur = _fs_xy(o["to"])
            P.append(cur)
            for k in name_at(cur):
                names.setdefault(k, len(P) - 1)
        elif o["type"] == "curve":
            seg = _bezier(cur, _fs_xy(o["cp1"]), _fs_xy(o["cp2"]), _fs_xy(o["to"]))
            P.extend(seg)
            cur = seg[-1]
            for k in name_at(cur):
                names.setdefault(k, len(P) - 1)
    P, names = _dedupe(np.asarray(P), names)
    P, names = _points_on_outline(P, names, {k: v for k, v in pts.items() if not k.startswith("__")
                                             and k not in names and k != "title"})
    piece = {"name": name, "P": P, "names": names, "marks": {}, "lines": {}, "grain": 90.0}
    for s in part.get("snippets", []):
        if s.get("at"):
            piece["marks"][s["name"]] = _fs_xy(s["at"])
    for k, path in part["paths"].items():
        if k in ("seam", "sa") or path.get("hidden") or k.startswith("sa") or k.endswith("Sa"):
            continue
        L = []
        cur = None
        for o in path["ops"]:
            if o["type"] in ("move", "line") and o["to"]:
                cur = _fs_xy(o["to"])
                L.append(cur)
            elif o["type"] == "curve":
                seg = _bezier(cur, _fs_xy(o["cp1"]), _fs_xy(o["cp2"]), _fs_xy(o["to"]))
                L.extend(seg)
                cur = seg[-1]
        if len(L) >= 2:
            piece["lines"][k] = np.asarray(L)
    # FreeSewing's own mirrored halves: name the unnamed mirror images
    taken = set(names.values())
    for k, i in list(names.items()):
        m = P[i] * [-1, 1]
        if abs(P[i][0]) < 1e-5:
            continue
        j = int(np.argmin(np.linalg.norm(P - m, axis=1)))
        if j not in taken and np.linalg.norm(P[j] - m) < 2e-5:
            names[k + ".m"] = j
    if fold:
        piece = mirror_fold(piece)
    return piece


def mirror_fold(piece: dict, eps: float = 1e-4) -> dict:
    """A half piece cut on the fold at x = 0, made whole."""
    P, names = piece["P"], piece["names"]
    on = np.abs(P[:, 0]) < eps
    n = len(P)
    # the run of off-fold points between two fold points
    starts = [i for i in range(n) if on[i] and not on[(i + 1) % n]]
    if len(starts) != 1:
        raise ValueError(f"{piece['name']}: can't find one fold run at x = 0 to mirror ({len(starts)} runs)")
    i0 = starts[0]
    run = [i0]
    i = (i0 + 1) % n
    while not on[i]:
        run.append(i)
        i = (i + 1) % n
    run.append(i)
    half = P[run]
    mir = half[::-1][1:-1] * [-1, 1]
    full = np.r_[half, mir]
    pos = {j: k for k, j in enumerate(run)}
    H = len(half)
    new_names = {}
    for k, j in names.items():
        if j in pos:
            new_names[k] = pos[j]
            if not on[j]:
                new_names[k + ".m"] = H + (H - 2 - pos[j])
    out = dict(piece, P=full, names=new_names)
    out["marks"] = dict(piece["marks"])
    for k, v in piece["marks"].items():
        if abs(v[0]) > eps:
            out["marks"][k + ".m"] = v * [-1, 1]
    out["lines"] = dict(piece["lines"])
    for k, L in piece["lines"].items():
        out["lines"][k + ".m"] = L * [-1, 1]
    return out


def mirror_x(piece: dict) -> dict:
    """The piece's mirror image (x -> -x; the other side's copy of a "cut 2" piece). Names stay on their points."""
    n = len(piece["P"])
    P = (piece["P"] * [-1, 1])[::-1]
    names = {k: n - 1 - i for k, i in piece["names"].items()}
    return dict(piece, P=P, names=names, marks={k: v * [-1, 1] for k, v in piece["marks"].items()},
                lines={k: v * [-1, 1] for k, v in piece["lines"].items()})


def from_spec(name: str, d: dict) -> dict:
    """A piece written in the spec: {"outline": [[x, y] | {"at": [x, y], "name": n} | {"arc": [cx, cy], "to": ...}...],
    "marks": {n: [x, y]}, "lines": {n: [[x, y], ...]}, "grain": deg}. Coordinates in metres. A "rect": [w, h]
    shorthand makes a rectangle with corners named sw, se, ne, nw (and mid-edge points s, e, n, w)."""
    names = {}
    if "rect" in d:
        w, h = (float(v) for v in d["rect"])
        P = np.array([[0, 0], [w / 2, 0], [w, 0], [w, h / 2], [w, h], [w / 2, h], [0, h], [0, h / 2]], float)
        P -= [w / 2, h / 2]
        for k, nm in enumerate(("sw", "s", "se", "e", "ne", "n", "nw", "w")):
            names[nm] = k
    else:
        pts = []
        for v in d["outline"]:
            if isinstance(v, dict):
                if "name" in v:
                    names[v["name"]] = len(pts)
                pts.append(np.asarray(v["at"], float))
            else:
                pts.append(np.asarray(v, float))
        P = np.asarray(pts)
    marks = {k: np.asarray(v, float) for k, v in (d.get("marks") or {}).items()}
    lines = {k: np.asarray(v, float) for k, v in (d.get("lines") or {}).items()}
    return {"name": name, "P": P, "names": names, "marks": marks, "lines": lines, "grain": float(d.get("grain", 90))}


def length(L: np.ndarray, closed: bool = False) -> float:
    if closed:
        L = np.r_[L, L[:1]]
    return float(np.sum(np.linalg.norm(np.diff(L, axis=0), axis=1)))


def area(P: np.ndarray) -> float:
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def index_of(piece: dict, point: str) -> int:
    if point not in piece["names"]:
        raise KeyError(f"piece {piece['name']!r} has no point {point!r} (has {', '.join(sorted(piece['names']))})")
    return piece["names"][point]


def arc_indices(piece: dict, spec: str) -> list[int]:
    """Outline indices of "a>b" or "a>via>b" (shorter way round unless a via point decides)."""
    parts = spec.split(">")
    ids = [index_of(piece, p) for p in parts]
    n = len(piece["P"])
    a, b = ids[0], ids[-1]
    fwd = [(a + k) % n for k in range((b - a) % n + 1)]
    bwd = [(a - k) % n for k in range((a - b) % n + 1)]
    if len(ids) > 2:
        vias = set(ids[1:-1])
        if vias <= set(fwd):
            return fwd
        if vias <= set(bwd):
            return bwd
        raise ValueError(f"{piece['name']}:{spec}: the via points aren't on one way round")
    L = lambda ix: length(piece["P"][ix])
    return fwd if L(fwd) <= L(bwd) else bwd


def _clip_halfplane(P, o, n):
    """Polygon P clipped to (p - o) . n >= 0 (Sutherland-Hodgman), with a map old index -> new index."""
    out, idx = [], {}
    m = len(P)
    d = (P - o) @ n
    for i in range(m):
        j = (i + 1) % m
        if d[i] >= 0:
            idx[i] = len(out)
            out.append(P[i])
        if (d[i] >= 0) != (d[j] >= 0):
            t = d[i] / (d[i] - d[j])
            out.append(P[i] + t * (P[j] - P[i]))
    return np.asarray(out), idx


def turn(piece: dict, line, keep_point: str | None = None, keep=None) -> dict:
    """Cut along a straight fold line (a line name or [[x, y], [x, y]]) and keep the side holding `keep_point`
    (or the point `keep`): a turned-under hem, facing or placket. The new edge's ends are named "<line>.a"/".b"."""
    L = piece["lines"][line] if isinstance(line, str) else np.asarray(line, float)
    a, b = L[0], L[-1]
    d = b - a
    n = np.array([-d[1], d[0]])
    q = piece["P"][index_of(piece, keep_point)] if keep_point else np.asarray(keep, float)
    if (q - a) @ n < 0:
        n = -n
    P2, idx = _clip_halfplane(piece["P"], a, n / np.linalg.norm(n))
    names = {k: idx[i] for k, i in piece["names"].items() if i in idx}
    on = np.where(np.abs((P2 - a) @ (n / np.linalg.norm(n))) < 1e-7)[0]
    nm = line if isinstance(line, str) else "turn"
    if len(on) >= 2:
        names[nm + ".a"], names[nm + ".b"] = int(on[0]), int(on[-1])
    marks = {k: v for k, v in piece["marks"].items() if (v - a) @ n >= -1e-7}
    out = dict(piece, P=P2, names=names, marks=marks)
    out.setdefault("folded", []).append({"line": [a.tolist(), b.tolist()]})
    return out


def slash_spread(piece: dict, line, amount: float, hinge: str = "a") -> dict:
    """Cut along a line (two points, or a line name) from the outline in, and open it by `amount` (m) at the free
    end, hinged at the other: the side of the line away from its normal rotates about the hinge. A full-abdomen or
    round-back alteration. hinge "a" | "b" names the hinge end of the line; "none" opens it parallel (a lengthen)."""
    L = piece["lines"][line] if isinstance(line, str) else np.asarray(line, float)
    a, b = np.asarray(L[0], float), np.asarray(L[-1], float)
    d = b - a
    nrm = np.array([-d[1], d[0]]) / np.linalg.norm(d)
    P = piece["P"].copy()
    side = (P - a) @ nrm > 0
    if hinge == "none":
        move = lambda X: X + nrm * amount
    else:
        h, f = (a, b) if hinge == "a" else (b, a)
        ang = amount / np.linalg.norm(f - h) * (1 if hinge == "a" else -1)
        c, s = np.cos(ang), np.sin(ang)
        R = np.array([[c, -s], [s, c]])
        move = lambda X: (X - h) @ R.T + h
    P[side] = move(P[side])
    marks = {k: (move(v[None])[0] if (v - a) @ nrm > 0 else v) for k, v in piece["marks"].items()}
    lines = {}
    for k, Ln in piece["lines"].items():
        s2 = (Ln - a) @ nrm > 0
        Ln = Ln.copy()
        Ln[s2] = move(Ln[s2])
        lines[k] = Ln
    return dict(piece, P=P, marks=marks, lines=lines)


def move_point(piece: dict, point: str, by, falloff: float = 0.05) -> dict:
    """Move a named outline point by [dx, dy], dragging its neighbours along the outline with a smooth falloff (m)."""
    P = piece["P"].copy()
    i = index_of(piece, point)
    n = len(P)
    seg = np.linalg.norm(np.diff(np.r_[P, P[:1]], axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    tot = cum[-1]
    dist = np.abs(cum[:n] - cum[i])
    dist = np.minimum(dist, tot - dist)
    w = np.clip(1 - dist / max(falloff, 1e-6), 0, 1)
    w = w * w * (3 - 2 * w)
    P += w[:, None] * np.asarray(by, float)
    return dict(piece, P=P)


def apply(pieces: dict, ops: list) -> dict:
    """Apply alteration ops in order: {"op": "slash_spread" | "turn" | "move" | "scale", "piece", ...}."""
    pieces = {k: copy.copy(v) for k, v in pieces.items()}
    for op in ops or []:
        kind = op["op"]
        names = op["piece"] if isinstance(op["piece"], list) else [op["piece"]]
        for nm in names:
            if nm not in pieces:
                raise KeyError(f"alter {kind}: no piece {nm!r} (have {', '.join(pieces)})")
            p = pieces[nm]
            if kind == "slash_spread":
                pieces[nm] = slash_spread(p, _line(p, op["line"]), float(op["amount"]), op.get("hinge", "a"))
            elif kind == "turn":
                pieces[nm] = turn(p, op["line"] if isinstance(op["line"], str) else _line(p, op["line"]),
                                  keep_point=op.get("keep"))
            elif kind == "move":
                pieces[nm] = move_point(p, op["point"], op["by"], float(op.get("falloff", 0.05)))
            elif kind == "scale":
                pieces[nm] = slash_spread(p, _line(p, op["line"]), float(op["amount"]), "none")
            else:
                raise ValueError(f"unknown alteration op {kind!r} (slash_spread, turn, move, scale)")
    return pieces


def _line(piece, spec):
    """A line as [[x, y], [x, y]]: given directly, by two point names, or a line name. A point name may carry an
    offset "name+[dx,dy]"."""
    if isinstance(spec, str):
        return piece["lines"][spec]
    out = []
    for v in spec:
        if isinstance(v, str):
            base, _, off = v.partition("+")
            q = piece["P"][index_of(piece, base)] if base in piece["names"] else piece["marks"][base]
            out.append(q + (np.asarray(eval_vec(off)) if off else 0))
        else:
            out.append(np.asarray(v, float))
    return np.asarray(out)


def eval_vec(s: str):
    import json
    return json.loads(s)
