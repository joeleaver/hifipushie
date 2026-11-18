"""garment_cut: STEP 6 of drape first, CUT AND FLATTEN (docs/proposals/drape_first.md): the marked toile (step 5's
mark.npz: one mesh, a piece label per face) cut on the marks (the pieces share the marks' exact vertices), each piece
flattened with least distortion (flatten.py) and read for strain (where a dart or ease is wanted), each seam's two sides
compared (truing), and the FLAT PATTERN written in draft_pattern's block form (cloth.pieces: pieces {P outline, names,
marks, grain, wrap, cut}, seams as "piece:a>via>b" arcs, closures, omit) so today's flat gate (draft_own_gate.gate:
seams, cut, sewn, closures, girths, panels, caught, shape rows...) runs on it. Every piece keeps its 3D outline (P3)
and its 3D mesh from the toile: nothing is placed later. Nothing here knows a garment (spike R2b made general).

EDGES: a piece's outline is cut into runs: a run along a mark is named by step 1's seam between the two pieces (two
runs between one pair: step 5's `runs` picks); a run step 1 doesn't name is "to_<other piece>"; a FREE run (the toile's
own edge: hem, neckline, opening, sleeve end) is named by THE DECLARATION:
  free   {piece: {step-1 edge: "top" | "bottom" | "side" | [classes]}}: a free edge segment is "side" when it runs
         more up than across, else "top" / "bottom" by its height against the piece's middle; neighbouring segments of
         one edge's classes are one run; runs under FREE_MERGE_MM join their neighbours (under
         FREE_CORNER_MM between a seam and a free edge, or inside one free edge: that edge). ".L" pieces' maps serve their
         ".R" mirror. A free run no edge takes, or an edge in two runs, is refused by name (row cut_flatten).
  ease   {"piece:edge": [lo, hi]}: a seam with a declared ease (a sleeve cap) is left as cut (never trued) and held to
         its band; else trued, +-1 % (draft_own.PLAIN_TOL). ".L" entries serve ".R". The cap's ease itself comes from step 4
         (cut_ease.py: the eased band flattened at its rest length, the cap longer than the toile's seam by the ease).
  folds  {piece: {fold name: edge}}: a planned fold (step 2's sleeve hem) along a cut edge: a press fold (cut_tapes.py).
  grain  {piece: deg}: the warp's angle in the flat (90: up the body, the straight grain: the default for every
         marked piece, a tailor's rule for bodies and sleeves); ".L" serves ".R". Every piece is flattened BY ITS
         THREADS (flatten_threads.py, R3g C512: warp / weft kept, shear free to the weave's jam) and its strain read
         along them (strain_mean_pct; iso_strain_mean_pct the isotropic reading). The collar's grain: its own `grain`.
TAPES and PLACE: each piece names the step-3 tapes it lies on and its place (torso front / back / side, a limb), read
off the toile where it was cut (cut_tapes.py): never declared.
MADE PIECES (cut_made.py; each module's docstring is its spec), after the marked pieces are flattened, in this order:
  flaps  {toile part: {"onto", "fold", "edges"}}: a turned flap (a lapel) unfolded across its roll edge onto its piece
         (cut_flap.py); the roll becomes a fold of the flat.
  layers {piece: {"host", "line": [[edge, mm, toward], ...], "keeps", "edges", "inner"}}: a facing / canvas traced off
         its host's flat (cut_layers.py); its seams are the host's runs.
  collar {"pieces", "neck", "outer", "end", "fold", "fold_on"}: the collar draped on the toile at step 4 (its part)
         cut and flattened, the fall unfolded about the roll line (cut_collar.py).
  shaped {"piece:run": pct}: the tailor's steam shaping of a collar's runs (+ stretch, - shrink), the flat cut to the
         shaped target, beyond cut_shape.SHAPE_MAX_PCT refused (cut_shape.py).
Writes <look dir>/cut/flat.npz (per piece U, F, V, strain), pattern.json (the block), cut.json, cut_3d.png (the pieces
where they lie, beside the reference); record step 6."""
from __future__ import annotations

import numpy as np

from .mark_split import areas, edge_faces, chains

FREE_MERGE_MM = 15.0
FREE_CORNER_MM = 40.0  # a free run shorter than this leaving a seam corner joins the free edge it leads into, one
                       # between two runs of one free edge joins it (the opening's drop at the side of the neck: neck)
FREE_CLASSES = ("top", "bottom", "side")


class CutRefused(ValueError):
    """A piece the toile's marks leave unflattenable, or a declaration naming what isn't there (named)."""


def outline(F, lab, p):
    """The piece's boundary as one closed loop of global vertex ids (CutRefused if it has holes)."""
    sub = F[lab == p]
    E, ef = edge_faces(sub)
    loops = chains(E[ef[:, 1] < 0])
    loops = [c[:-1] if c[0] == c[-1] else c for c in loops]
    if len(loops) != 1:
        raise CutRefused(f"piece {p}: its outline is {len(loops)} loops (a hole, or a slit the marks left): one piece is "
                         f"one disc")
    return loops[0]


def other_label(F, lab, p):
    """{sorted edge: label of the face across} for the piece's boundary edges (-1: the toile's own edge)."""
    E, ef = edge_faces(F)
    la = lab[ef[:, 0]]
    lb = np.where(ef[:, 1] >= 0, lab[np.maximum(ef[:, 1], 0)], -1)
    out = {}
    for (a, b), x, y in zip(E, la, lb):
        if x == p and y != p:
            out[(int(a), int(b))] = int(y)
        elif y == p and x != p:
            out[(int(a), int(b))] = int(x)
    return out


def runs_of(loop, V, across, names, p, fmap=None):
    """[(key, [loop positions])]: contiguous runs of the loop by what lies across (a piece name, or "free:" + the
    declared free edge its class belongs to (fmap {edge: class or [classes]}), else "free:" + the class)."""
    cls_name = {}
    for e, c in (fmap or {}).items():
        for c_ in ([c] if isinstance(c, str) else c):
            cls_name[c_] = e
    n = len(loop)
    zmid = 0.5 * (V[loop, 2].min() + V[loop, 2].max())
    keys = []
    for i in range(n):
        a, b = loop[i], loop[(i + 1) % n]
        q = across.get((min(a, b), max(a, b)), -1)
        if q >= 0:
            keys.append(names[q])
        else:
            d = V[b] - V[a]
            c = ("side" if abs(d[2]) > 0.7 * np.linalg.norm(d) else
                 ("bottom" if 0.5 * (V[a, 2] + V[b, 2]) < zmid else "top"))
            keys.append("free:" + cls_name.get(c, c))
    seg = np.linalg.norm(V[np.roll(loop, -1)] - V[loop], axis=1) * 1000
    for _ in range(len(keys)):  # short free runs join a free neighbour, the shortest first, one at a time
        rs = _group(keys)
        if len(rs) < 2:
            break
        best = None
        for k, (key, idx) in enumerate(rs):
            fr = [x for x in (rs[(k - 1) % len(rs)][0], rs[(k + 1) % len(rs)][0]) if x.startswith("free:") and x != key]
            lim = FREE_CORNER_MM if fr and fr[0] == fr[-1] else FREE_MERGE_MM
            ln = seg[idx].sum()
            if key.startswith("free:") and fr and ln < lim and (best is None or ln < best[0]):
                best = (ln, idx, fr[0])
        if best is None:
            break
        for i in best[1]:
            keys[i] = best[2]
    return _group(keys)


def _group(keys):
    """Cyclic runs of equal keys: [(key, [edge positions])] (edge i runs loop[i] -> loop[i + 1])."""
    n = len(keys)
    start = next((i for i in range(n) if keys[i] != keys[i - 1]), 0)
    out = []
    for k in range(n):
        i = (start + k) % n
        if out and out[-1][0] == keys[i]:
            out[-1][1].append(i)
        else:
            out.append((keys[i], [i]))
    return out


def name_runs(p, rs, V, loop, s1, absent, runs_decl, free_decl):
    """{edge name: [edge positions]} for piece p: seams by step 1, extra ones to_<q>, free ones by the declaration."""
    from .mark import RUN_DIRS
    base = p[:-2] + ".L" if p.endswith(".R") else p
    fmap = free_decl.get(p) or free_decl.get(base) or {}
    out, bad = {}, []
    by_q = {}
    for key, idx in rs:
        by_q.setdefault(key, []).append(idx)
    for key, lst in by_q.items():
        if key.startswith("free:"):
            e = key[5:]
            if e not in fmap:
                bad.append(f"{p}: a free {e} run no declared edge takes: free.{base}: {{edge: \"{e}\" or [classes]}}")
            lst = sorted(lst, key=len, reverse=True)
            if e in fmap and len(lst) > 1:
                bad.append(f"{p}: free edge {e!r} is {len(lst)} runs apart (another edge between them)")
            for j, idx in enumerate(lst):
                out[(e if e in fmap else f"free_{e}") + (f"_{j + 1}" if j else "")] = idx
            continue
        ss = [s for s in s1.get("seams") or [] if {s["a"].split(":")[0], s["b"].split(":")[0]} == {p, key}]
        mine = [s["a"] if s["a"].split(":")[0] == p else s["b"] for s in ss]
        if not ss:
            for j, idx in enumerate(sorted(lst, key=len, reverse=True)):
                out[f"to_{key}" + (f"_{j + 1}" if j else "")] = idx
            continue
        lst = sorted(lst, key=len, reverse=True)
        if len(ss) == 1:
            out[mine[0].split(":", 1)[1]] = lst[0]
            for j, idx in enumerate(lst[1:]):
                out[f"to_{key}_{j + 2}"] = idx
            continue
        left = lst[:len(ss)]
        for s, e in zip(ss, mine):
            how = runs_decl.get(s["a"]) or runs_decl.get(s["b"])
            if how is None or not left:
                bad.append(f"{e}: which of the {len(lst)} runs to {key} (step 5's runs)")
                continue
            ax, sg = RUN_DIRS[how]
            k = int(np.argmax([sg * V[[loop[i] for i in idx], ax].mean() for idx in left]))
            out[e.split(":", 1)[1]] = left.pop(k)
    return out, bad


def flatten_piece(V, F, lab, p, nm, ease=None, grain=90.0):
    """The piece flattened by its threads (warp at grain deg; flatten_threads.py), its strain read along them."""
    from .flatten_threads import numbers, threads
    loop = outline(F, lab, p)
    fid = np.where(lab == p)[0]
    used = np.unique(F[fid])
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    Vp, Fp = V[used], remap[F[fid]]
    from .cut_ease import flatten_eased
    U, S, Fk, cap = flatten_eased(Vp, Fp, remap[loop], ease, grain)
    ar = areas(Vp, Fk)
    bad, th = numbers(Vp, Fk, U, S, grain, ar)
    lp = remap[loop]
    P = U[lp]
    if 0.5 * float(np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(P[:, 1], np.roll(P[:, 0], -1))) < 0:
        loop, lp = loop[::-1], lp[::-1]
    worst = np.argsort(-bad)[: max(1, len(bad) // 50)]
    w, f_, _ = threads(Vp, Fk[worst], U, 90.0 if grain is None else grain)
    rep = {"faces": int(len(Fk)), "area_cm2": round(float(ar.sum()) * 1e4, 1), **th,
           "area_over_5pct": round(float(ar[bad > 0.05].sum() / ar.sum() * 100), 1),
           "worst_2pct_at": np.round(Vp[Fk[worst]].mean((0, 1)), 3).tolist(),
           "worst_kind": "threads short on the toile (cloth over: a dart wanted)" if (w + f_).mean() < 0
           else "threads long on the toile (stretched: ease wanted)"}
    if cap:
        rep["cap_ease"] = cap
    return {"name": nm, "loop": list(loop), "U": U, "F": Fk, "V": Vp, "bad": bad, "lp": lp, "rep": rep}
