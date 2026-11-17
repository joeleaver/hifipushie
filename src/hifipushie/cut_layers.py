"""garment_cut's LAYERS: a piece cut from another piece's FLAT (a facing, a canvas, an interlining: step 1's pieces that
lie inside a shell piece), as a pattern maker traces it off the shell's pattern: the host's flat (with its flaps
unfolded) cut by the layer's declared INNER LINE, the side holding its declared edge kept. The layer's outline runs along
the host's outline (its edges named by the host's, renamed by the declaration) and along the line (its `inner` edge);
its 3D shape is the host's at the same flat points (it lies on its host: nothing is placed). Its seams with the host's
neighbours are the host's own runs, so they are equal by construction; step 1's `caught` row checks it reaches them.

THE DECLARATION (garment_cut's `layers`):
  layers {layer piece: {"host": cut piece, "line": [anchor, anchor, ...], "keeps": a host edge on the layer's side,
          "edges": {host edge: layer edge} (renames; a host edge not named keeps its name), "inner": the line's edge
          name (default "inner")}}; an anchor is [host edge, mm, toward]: the point mm along that host edge from its end
          nearest host edge `toward` (["hem", 90, "front"]: 90 mm along the hem from its front end); mm may be a share
          of the edge, "60%" (the front's own outline: a cutaway hem is short, R3f-6). The line runs straight between
          anchors, from the host's outline (its end anchors) to its outline, and cuts the host in exactly two (the
          outline split at the end anchors, closed by the line: the side holding `keeps` is the layer). A line that
          leaves the host between its anchors, or a layer edge that comes out as more than one run, is REFUSED by
          name, never cut (R3f-6, C503: a canvas line crossing the armhole twice came out as two `inner` and two
          `armhole` runs). ".L" layers serve ".R".
Nothing here knows a garment."""
from __future__ import annotations

import numpy as np

from .toile_geom import clip, largest


HOLE_MM = 10.0  # mm: a hole's outline under this (a sliver where a flap is zipped to its piece) is not a hole


class LayerRefused(ValueError):
    """A layer whose line doesn't cut its host, or an anchor naming what isn't there (named)."""


def _edge_pts(f, idx):
    n = len(f["lp"])
    pos = list(idx) + [(idx[-1] + 1) % n]
    return pos, f["U"][np.asarray(f["lp"])[pos]]


def anchor(f, edges, a, name):
    """The flat point an anchor names (module doc)."""
    if not (isinstance(a, list) and len(a) == 3 and a[0] in edges and a[2] in edges):
        raise LayerRefused(f"{name}: anchor {a!r}: [host edge, mm, toward host edge] with edges of {f['name']} "
                           f"({', '.join(sorted(edges))})")
    _, P = _edge_pts(f, edges[a[0]])
    _, T = _edge_pts(f, edges[a[2]])
    if min(np.linalg.norm(T - P[-1], axis=1)) < min(np.linalg.norm(T - P[0], axis=1)):
        P = P[::-1]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    if isinstance(a[1], str) and a[1].strip().endswith("%"):
        d = float(a[1].strip()[:-1]) / 100 * s[-1]
    else:
        d = float(a[1]) / 1000
    if not 0 <= d <= s[-1]:
        raise LayerRefused(f"{name}: anchor {a!r}: {f['name']}:{a[0]} is {s[-1] * 1000:.0f} mm long")
    return np.array([np.interp(d, s, P[:, 0]), np.interp(d, s, P[:, 1])])


def side_of(U, L):
    """Signed distance of points U to the polyline L run on past both ends (> 0 on its left)."""
    L = np.asarray(L, float)
    L = np.r_[L[:1] - 5 * (L[1] - L[0]) / np.linalg.norm(L[1] - L[0]), L, L[-1:] + 5 * (L[-1] - L[-2]) / np.linalg.norm(L[-1] - L[-2])]
    best = np.full(len(U), np.inf)
    sg = np.zeros(len(U))
    for A, B in zip(L[:-1], L[1:]):
        d = B - A
        t = np.clip(((U - A) @ d) / (d @ d), 0, 1)
        Q = A + t[:, None] * d
        dist = np.linalg.norm(U - Q, axis=1)
        cr = d[0] * (U[:, 1] - A[1]) - d[1] * (U[:, 0] - A[0])
        b = dist < best
        best[b] = dist[b]
        sg[b] = np.sign(cr[b])
    return best * np.where(sg == 0, 1, sg)


def _on_loop(HP, q):
    """(segment index, point) of the host's outline nearest q."""
    A, B = HP, np.roll(HP, -1, axis=0)
    dd = B - A
    t = np.clip(((q - A) * dd).sum(1) / np.maximum((dd * dd).sum(1), 1e-18), 0, 1)
    Q = A + t[:, None] * dd
    i = int(np.argmin(np.linalg.norm(Q - q, axis=1)))
    return i, Q[i]


def split_side(f, edges, L, keeps, U, name):
    """Signed distance of the flat points U to the line L (> 0 on the layer's side): the host's outline split at the
    line's end anchors into two polygons, each closed by the line; the one holding the `keeps` edge is the layer's."""
    from .draft_caught import _inside
    lp = np.asarray(f["lp"])
    HP, n = f["U"][lp], len(lp)
    mids = np.concatenate([np.linspace(a, b, 12)[1:-1] for a, b in zip(L[:-1], L[1:])])
    out = ~_inside(mids, HP)
    if out.any():
        raise LayerRefused(f"{name}: its line leaves {f['name']} between its anchors (at flat "
                           f"{np.round(mids[out][0] * 1000).tolist()} mm): anchors on the edges it should run between")
    (s0, a0), (s1, a1) = _on_loop(HP, L[0]), _on_loop(HP, L[-1])
    walk = lambda i, j: [k % n for k in range(i + 1, i + 1 + (j - i) % n)]  # (loop positions i+1 .. j)
    ia, ib = walk(s1, s0), walk(s0, s1)
    PA = np.r_[[a1], HP[ia], [a0], L[1:-1]]
    PB = np.r_[[a0], HP[ib], [a1], L[-2:0:-1]] if len(L) > 2 else np.r_[[a0], HP[ib], [a1]]
    k = list(edges[keeps])[len(edges[keeps]) // 2]
    keep, other = (PA, PB) if k in ia else (PB, PA)
    sd = side_of(U, L)
    sg = np.where(_inside(U, keep), 1.0, np.where(_inside(U, other), -1.0, np.nan))
    ref = np.sign(np.nanmedian(sd[sg > 0])) if (sg > 0).any() else 1.0
    sg = np.where(np.isnan(sg), np.sign(sd) * ref, sg)
    return np.abs(sd) * sg


def cut_layer(f: dict, edges: dict, d: dict, name: str):
    """(piece dict as cut.flatten_piece gives: U, F, V, bad, lp, loop, rep; its edges {name: [positions]}; report)."""
    from .cut import _group
    for k in ("host", "line", "keeps"):
        if k not in d:
            raise LayerRefused(f"{name}: layers.{name} needs {k!r} (module doc)")
    if d["keeps"] not in edges:
        raise LayerRefused(f"{name}: keeps {d['keeps']!r} is not an edge of {f['name']} ({', '.join(sorted(edges))})")
    L = np.array([anchor(f, edges, a, name) for a in d["line"]])
    if len(L) < 2:
        raise LayerRefused(f"{name}: line: two anchors at least")
    used = np.unique(f["F"])
    remap = -np.ones(len(f["V"]), int)
    remap[used] = np.arange(len(used))
    U, V3, F = f["U"][used], f["V"][used], remap[f["F"]]
    phi = split_side(f, edges, L, d["keeps"], U, name)
    W, Fl = largest(*clip(np.c_[U, V3], F, phi))
    if not len(Fl):
        raise LayerRefused(f"{name}: its line leaves nothing of {f['name']} on the {d['keeps']} side")
    Ul, Vl = W[:, :2], W[:, 2:]
    from .mark_split import chains, edge_faces
    E, ef = edge_faces(Fl)
    loops = [np.asarray(c[:-1] if c[0] == c[-1] else c) for c in chains(E[ef[:, 1] < 0])]
    perim = [float(np.linalg.norm(Ul[np.roll(c, -1)] - Ul[c], axis=1).sum()) for c in loops]
    loop = loops[int(np.argmax(perim))]
    holes = sorted(round(x * 1000, 1) for x in perim if x < max(perim))
    P = Ul[loop]
    if 0.5 * float(np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(P[:, 1], np.roll(P[:, 0], -1))) < 0:
        loop = loop[::-1]
    on = np.abs(side_of(Ul[loop], L)) < 1e-7
    HP = f["U"][np.asarray(f["lp"])]
    hname = {}
    for e, idx in edges.items():
        for i in idx:
            hname[i] = e
    ren, inner = d.get("edges") or {}, d.get("inner", "inner")
    keys = []
    n = len(loop)
    for k in range(n):
        if on[k] and on[(k + 1) % n]:
            keys.append(inner)
            continue
        mid = 0.5 * (Ul[loop[k]] + Ul[loop[(k + 1) % n]])
        A, B = HP, np.roll(HP, -1, axis=0)
        dd = B - A
        t = np.clip(((mid - A) * dd).sum(1) / np.maximum((dd * dd).sum(1), 1e-18), 0, 1)
        j = int(np.argmin(np.linalg.norm(mid - (A + t[:, None] * dd), axis=1)))
        e = hname.get(j, "?")
        keys.append(ren.get(e, e))
    out, bad = {}, []
    if holes and max(holes) > HOLE_MM:
        bad.append(f"{name}: holes in its flat (outline mm {holes[-3:]}): its host's flat isn't one disc there")
    groups = list(_group(keys))
    mm = lambda idx: round(float(sum(np.linalg.norm(Ul[loop[(i + 1) % n]] - Ul[loop[i]]) for i in idx)) * 1000, 1)
    for key in {k for k, _ in groups}:
        runs = [mm(idx) for k, idx in groups if k == key]
        if len(runs) > 1:
            raise LayerRefused(f"{name}: edge {key!r} comes out as {len(runs)} runs apart ({runs} mm; its line crosses "
                               f"{f['name']}'s outline more than at its two end anchors): declare a line that runs once "
                               f"across the host, from edge to edge")
    for key, idx in groups:
        out[key] = idx
    from .mark_split import areas
    ar = float(areas(Vl, Fl).sum())
    rep = {"faces": int(len(Fl)), "area_cm2": round(ar * 1e4, 1), "host": f["name"], "edges": sorted(out),
           "strain_mean_pct": 0.0, "area_over_2pct": 0.0, "holes_mm": holes,  # (traced off its host's flat)
           "line_mm": round(float(np.linalg.norm(np.diff(L, axis=0), axis=1).sum()) * 1000, 1)}
    g = {"name": name, "U": Ul, "F": Fl, "V": Vl, "bad": np.zeros(len(Fl)), "lp": loop, "loop": list(loop), "rep": rep}
    return g, out, rep, bad
