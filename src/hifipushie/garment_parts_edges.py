"""Step 1's EDGES (garment_plan.check_parts), for any garment: every piece names its edges, a seen piece as spans of
its own outline, so a seam or a trim joins edges that exist and a later step can find where each one runs (t s1-1:
"front.L:hindarm" was accepted as free text; a shoulder seam given the full shoulder-to-shoulder width and an armhole
given the bicep girth passed).

FORM: piece.edges = {edge: [i0, i1]} for a piece with an outline: the edge runs along the outline from point i0 to
point i1 (forward, wrapping past the last point); the spans TILE the outline (each outline segment in exactly one
edge: a pattern piece's boundary is its edges). A piece with no outline (occluded / inferred, no place): edges =
[names] (or {name: null}). Seams and trims (`follows`) name "piece:edge" with a declared edge.
SEAM LENGTHS: a seam given a body length (FreeSewing names the tape takes) is compared with its edge as drawn on the
step-0 fit view, at the step-0 scale: past LENGTH_X either way it is refused unless the seam says why (a front view
foreshortens an edge running round the body: the bounds are wide; it catches the wrong measurement, not a few cm).
HIDDEN (C344): piece.hidden = [edge names] whose course this view can't show (a collar's back neckline in a front
view): drawn dashed, never length-checked; the outline still tiles (draw the hidden run where it would pass).
A TRIM that follows seen edges takes its place from them (no `where` needed: t s1-2 repeated every binding run).
"""
from __future__ import annotations

import math

LENGTH_X = (0.4, 2.5)  # (body length / the edge as drawn: outside this, the wrong measurement)


def _outline(x: dict):
    w = x.get("where") if isinstance(x.get("where"), dict) else {}
    o = w.get("outline")
    return (o, w.get("view", 0)) if isinstance(o, list) and len(o) >= 3 else (None, None)


def check(pieces: dict, bad: list) -> dict:
    """{piece: {edge: (view, [[u, v], ...]) | None}} from every piece's edges; bad gets every fault."""
    out = {}
    for n, x in pieces.items():
        if not isinstance(x, dict):
            continue
        w, e = f"pieces.{n}.edges", x.get("edges")
        o, view = _outline(x)
        if e is None:
            if x.get("build") != "omit":
                bad.append(f"{w}: name its edges ({'{edge: [i0, i1]} spans of its outline that tile it' if o else '[names]'}"
                           ", e.g. neck, shoulder, armhole, side, hem, centre front): seams and trims join named edges")
            continue
        if o is None:
            names = list(e) if isinstance(e, (list, dict)) else None
            if not names or not all(isinstance(k, str) and k for k in names):
                bad.append(f"{w}: [edge names] (no outline on the picture: names only)")
                continue
            out[n] = {k: None for k in names}
            continue
        hid = x.get("hidden") or []
        if not isinstance(hid, list) or any(h not in e for h in hid):
            bad.append(f"pieces.{n}.hidden: a list of its own edges ({', '.join(e) if isinstance(e, dict) else ''}) whose "
                       "course this view can't show")
            hid = []
        if not isinstance(e, dict) or not e:
            bad.append(f"{w}: {{edge: [i0, i1]}}: each edge a span of the outline's points (0..{len(o) - 1})")
            continue
        N, cover, spans = len(o), [[] for _ in o], {}
        for k, s in e.items():
            if not (isinstance(s, list) and len(s) == 2 and all(isinstance(i, int) and 0 <= i < N for i in s)
                    and s[0] != s[1]):
                bad.append(f"{w}.{k}: [i0, i1], two different outline point indices 0..{N - 1}")
                continue
            segs = [(s[0] + j) % N for j in range((s[1] - s[0]) % N)]
            for g in segs:
                cover[g].append(k)
            spans[k] = (view, [o[(s[0] + j) % N] for j in range(len(segs) + 1)], k in hid)
        hseg = {g for g, c in enumerate(cover) if any(k in hid for k in c)}
        xs = crossings(o, hseg)  # (t s1-2 / s1-3: a collar outline crossing itself was accepted)
        if xs:
            bad.append(f"pieces.{n}.where.outline crosses itself: segments {', '.join(f'{i}x{j}' for i, j in xs[:4])} "
                       "(segment i runs from point i to i+1): a piece's outline is one simple loop; where this view "
                       "can't show its course, mark that edge hidden")
        gaps = [g for g, c in enumerate(cover) if not c]
        twice = [g for g, c in enumerate(cover) if len(c) > 1]
        if gaps or twice:
            bad.append(f"{w}: the edges must tile the outline (each segment i -> i+1 in one edge): "
                       + (f"in none: segments {_runs(gaps)}" if gaps else "")
                       + ("; " if gaps and twice else "")
                       + (f"in two: segments {_runs(twice)} ({', '.join(sorted({k for g in twice for k in cover[g]}))})"
                          if twice else ""))
        out[n] = spans
    return out


def _runs(ix: list) -> str:
    out, i = [], 0
    while i < len(ix):
        j = i
        while j + 1 < len(ix) and ix[j + 1] == ix[j] + 1:
            j += 1
        out.append(f"{ix[i]}" if i == j else f"{ix[i]}-{ix[j]}")
        i = j + 1
    return ", ".join(out)


def refs(where: str, names: list, edges: dict, bad: list):
    """Every 'piece:edge' names an edge its piece declared."""
    for e in names:
        if not isinstance(e, str) or ":" not in e:
            continue  # (the piece check names it)
        pc, ed = e.split(":", 1)
        if pc in edges and ed not in edges[pc]:
            bad.append(f"{where}: {e!r}: {pc} has no edge {ed!r} (its edges: {', '.join(edges[pc]) or 'none'})")


def lengths(seams: list, edges: dict, fit_view, scale, mm: dict, bad: list) -> list:
    """Each body-length seam against its edge as drawn on the fit view; [(seam, body mm, drawn mm)] checked."""
    done = []
    if not scale or not mm:
        return done
    for i, s in enumerate(seams):
        ln = (s or {}).get("length") or {}
        names = ln.get("body") if isinstance(ln, dict) else None
        if not names or not all(m in mm for m in names) or str(s.get("why") or "").strip():
            continue  # (a defined measurement: step 3 takes it; a seam with why: kept)
        body = sum(float(mm[m]) for m in names)
        for end in (s.get("a"), s.get("b")):
            pc, _, ed = str(end).partition(":")
            g = (edges.get(pc) or {}).get(ed)
            if not g or g[0] != fit_view or g[2]:
                continue  # (not drawn on the fit view, or hidden there)
            drawn = sum(math.dist(p, q) for p, q in zip(g[1], g[1][1:])) * scale
            if drawn < 1:
                continue
            x = body / drawn
            done.append((i, body, drawn))
            if not LENGTH_X[0] <= x <= LENGTH_X[1]:
                bad.append(f"seams[{i}] {s.get('a')} = {s.get('b')}: {' + '.join(names)} is {body:.0f} mm on the model, "
                           f"but {end} as drawn is about {drawn:.0f} mm ({x:.1f}x; {LENGTH_X[0]}-{LENGTH_X[1]}x allowed: "
                           "a front view foreshortens): the wrong measurement (a whole girth for part of it, both shoulders "
                           "for one), or an edge joined to several pieces given the whole length in each seam (each "
                           "takes its share); define the right one, or keep it with why")
            break
    return done


def trim_where(x: dict, edges: dict):
    """A seen trim with no `where` that follows only drawn, unhidden edges: its place is those edges' runs. None, or
    why it can't be placed (t s1-3: a binding along seen and unseen edges was refused only as 'needs a where')."""
    fl = x.get("follows")
    if x.get("where") is not None or x.get("seen") != "seen" or not isinstance(fl, list) or not fl:
        return None
    runs, off = [], []
    for e in fl:
        pc, _, ed = str(e).partition(":")
        g = (edges.get(pc) or {}).get(ed)
        if not g or g[2]:
            off.append(e)
        else:
            runs.append(g)
    if off:
        return (f"follows {', '.join(off)}, with no drawn place in this view ({'hidden' if runs else 'unseen'}): a trim "
                "along seen and unseen edges is two details (the seen run, and an inferred one with from), or give it "
                "its own where")
    if len({g[0] for g in runs}) == 1:
        x["where"] = {"view": runs[0][0], "outlines": [list(map(list, g[1])) for g in runs], "from_edges": True}
    return None


def _cross(p, q, r, t) -> bool:
    """Segments p-q and r-t cross (properly)."""
    def o(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (o(p, q, r) * o(p, q, t) < 0) and (o(r, t, p) * o(r, t, q) < 0)


def crossings(outline: list, hidden_segs: set) -> list:
    """Pairs of outline segments that cross, neither on a hidden edge (a piece's outline is a simple loop)."""
    N, out = len(outline), []
    for i in range(N):
        for j in range(i + 2, N):
            if (i == 0 and j == N - 1) or i in hidden_segs or j in hidden_segs:
                continue
            if _cross(outline[i], outline[(i + 1) % N], outline[j], outline[(j + 1) % N]):
                out.append((i, j))
    return out
