"""Step 10, EXPORT: a chain garment as a game asset (docs/state/garment_steps.md, tooling run T11).

The game artist's way (docs/state/garment_game.md, proved on the old drapes): the hung (or built) garment is the HIGH
poly; the game mesh is a clean RE-GRID OF THE FLAT PATTERN mapped onto that surface (garment_game.boundaries +
remesh_panel: seams resampled once and shared by both sides, barycentric through the garment's own triangles), so
  * the UVs are the pattern: every piece's flat layout packed into one square (garment_game.atlas), texel density known;
  * the density is chosen to fit the role's clothing budget (budgets.json "clothing", LOD0), counted as rendered
    triangles: outer + explicit inner faces + rims on free edges (garment_game.shell) + the details;
  * stiff pieces (the pattern's made pieces: collar, stand, cuffs) are re-gridded finer, to MADE_MIN_ROWS rows across;
  * fold lines (M["folds"]: a collar's roll, a pressed band) are kept as vertex rows (a chord would cut a fold);
  * the details (garment_details, step 7: details.pkl) are their own meshes and materials, as made;
  * skinned to the character's rig (rig_report.rig_bones: Mixamo names) with weights READ OFF THE BODY (rig_skin.skin_parts: the
    base body's own weights at its surface, smoothed; clothes move with the skin under them); a detail takes the
    weights of the garment vertex nearest it (a button rides the cloth).
Numbers (the text): triangles vs budget, UV stretch (3D edge / pattern edge per triangle: the drape vs its cut), the
weight check (one arm raised 45 deg: how far each garment vertex's distance to the body changes where the body moved).
The look (shape only): the GLB rendered in EEVEE (asset_export.preview), rest and posed, beside the reference.

The LODs (C439): <garment>_LOD1.. are the SAME re-grid at a coarser grid (lod_plan: the role's clothing budget at each
LOD, budgets.lod_ratios, what the character's export gives a part below the neck; stiff pieces' rows and the coarsest
grid go with sqrt(share)), never a decimation of LOD0: the character's generic decimator kinked the shirt at LOD2 and
tore its fronts at LOD3. Seams stay shared, the UVs stay the pattern, the weights are read off the body again on each
LOD's own mesh. Details (lod_details): a piece under DETAIL_MIN_PX on screen at the LOD's switch size is left out, the
others are decimated to the LOD's share and moved with the cloth under them.

Refused by name: step 9 not approved (internally an approved 7a is enough for the build: the record's step 10 then
says why it can't be written), no build, over budget at the coarsest grid (H_MAX: say what to change).
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from . import budgets, garment_game as gg

H_MAX = 0.04  # m: the coarsest grid kept (garment_game: a 9 cm grid lost the sleeves' shape and sank the chords 2 cm)
H_MIN = 0.006  # m: no finer than this (the drape's own resolution is ~5 mm)
MADE_MIN_ROWS = gg.MADE_MIN_ROWS  # a stiff piece keeps this many rows across its short side
BUDGET_FILL = 0.92  # aim for this share of the budget (the count isn't exactly predictable from h)
ROLE = "main_npc"
PART = "clothing"
H_MAX_LOD = 0.14  # m: the coarsest grid a LOD takes (a sleeve keeps about three edges round; past it pattern edges open)
SCREEN_PX = 1920  # px: the larger dimension of the target's screen (budgets.json "target": 1080p)
DETAIL_MIN_PX = 2.0  # a detail piece (a button) smaller than this at a LOD's switch size is left out of that LOD
DETAIL_MIN_TRIS = 12  # a kept detail piece is never decimated below this (a closed solid, not a sliver)
# UV stretch row: INFORMATIONAL (T11b). T11 set its limits after seeing the numbers and widened them once to pass; no
# named tolerance exists (budgets.json gives texel densities per role, not a stretch tolerance), so it gates nothing.


class ExportRefused(ValueError):
    pass


# ---------------------------------------------------------------- the source

def drape_of(r: dict) -> dict:
    """A chain result (built.pkl / final.pkl: X on the flat mesh M) as garment_game's drape: every piece a panel."""
    M = r["M"]
    return {"name": "garment", "V": np.asarray(r["X"], float), "F": np.asarray(M["F"], np.int64),
            "uv": np.asarray(M["uv"], float), "piece": np.asarray(M["piece"], np.int64), "names": list(M["names"]),
            "sew": np.asarray(M["sew"], np.int64).reshape(-1, 2), "sew_seam": np.asarray(M["sew_seam"], np.int64),
            "made": [], "drop": set()}


def fold_lines(M: dict) -> dict:
    """{piece: [2D polyline]} from the pattern's folds (rows of flat-mesh vertices)."""
    uv, out = np.asarray(M["uv"], float), {}
    for f in M.get("folds") or []:
        for row in f.get("rows") or []:
            row = np.asarray(row, int)
            if len(row) > 1:
                out.setdefault(f["piece"], []).append(uv[row])
    return out


def piece_h(M: dict, h: float, rows: int | None = None) -> dict:
    """{piece: edge}: h, finer on the stiff (made) pieces to `rows` (MADE_MIN_ROWS; a LOD: fewer) across their short side."""
    uv, pc, out = np.asarray(M["uv"], float), np.asarray(M["piece"]), {}
    made = set(M.get("made") or [])
    rows = MADE_MIN_ROWS if rows is None else rows
    for i, n in enumerate(M["names"]):
        e = h
        if n in made:
            s = uv[pc == i]
            short = float(np.min(s.max(0) - s.min(0))) if len(s) else h
            e = min(h, max(H_MIN, short / rows))
        out[n] = e
    return out


# ---------------------------------------------------------------- the re-grid

def regrid(drape: dict, h: float, body: np.ndarray | None = None, lines: dict | None = None, hp: dict | None = None,
           joints: dict | None = None):
    """Every piece re-gridded in 2D at ~h (hp: per piece), mapped onto the drape, seams shared, wound away from body.
    joints None: the old route (garment_game.remesh_panel: hex grid + Delaunay); a dict ({piece: joint polylines},
    garment_loops.joint_lines): clean loops (garment_loops.remesh_loops, T11b). Returns (pieces, merged mesh)."""
    from . import garment_loops as gl
    hp = hp or {n: h for n in drape["names"]}
    bd = gg.boundaries(drape, hp)
    if joints is None:
        pieces = [gg.remesh_panel(drape, n, bd[n], hp[n], (lines or {}).get(n, ())) for n in bd]
    else:
        pieces = [gl.remesh_loops(drape, n, bd[n], hp[n], (lines or {}).get(n, ()), joints.get(n, ())) for n in bd]
    for p in pieces:
        close_corners(p)
    gg._weld_corners(pieces)
    if body is not None:
        tree = cKDTree(body)
        for p in pieces:
            V, T = p["V"], p["T"]
            fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
            _, i = tree.query(V)
            if np.sum((fn * (V - body[i])[T].mean(1)).sum(1) > 0) < 0.5 * len(T):
                p["T"] = T[:, ::-1].copy()
    return pieces, gg.merged(pieces)


def close_corners(p: dict) -> int:
    """A border vertex the triangulation left in NO triangle gets its corner back; returns how many. The re-grid drops
    every triangle on a chord that runs within 0.05 h of the outline: at a LOD's grid that is a real corner (the
    shirt's right front at 125 mm: a 1 cm hem run past the side seam), cut off with the triangle behind it, a hole
    11 cm long at the seam, where the other piece still has the vertex. The corner triangle (prev, v, next) is put
    back, and the one behind its chord (prev, next, c: both open edges of the hole) when the chord is not a mesh
    edge. Only a convex corner is closed; anything else stays counted in missing_boundary_edges."""
    T, uv = np.asarray(p["T"], np.int64), np.asarray(p["uv"], float)
    nb = int((np.asarray(p["gid"]) >= 0).sum())
    if not len(T) or nb < 3:
        return 0
    used = np.zeros(len(uv), bool)
    used[T] = True

    def edges(t):
        e, c = np.unique(np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), 1), axis=0, return_counts=True)
        return dict(zip(map(tuple, e.tolist()), c.tolist()))
    E = edges(T)
    key = lambda a, b: (min(a, b), max(a, b))  # noqa: E731
    near = {}
    for a, b in E:
        near.setdefault(a, set()).add(b)
        near.setdefault(b, set()).add(a)
    ccw = np.median([gg._area2(uv[t]) for t in T[:200]]) > 0
    add, n = [], 0
    for v in np.flatnonzero(~used[:nb]):
        a, b = int((v - 1) % nb), int((v + 1) % nb)
        if not (used[a] and used[b]) or gg._area2(uv[[a, v, b]]) <= 0:
            continue
        new = [[a, int(v), b]]
        if key(a, b) not in E:  # the triangle behind the chord went too: (a, b, c), c across two open edges
            cs = [c for c in near.get(a, set()) & near.get(b, set())
                  if E[key(a, c)] == 1 and E[key(b, c)] == 1 and gg._area2(uv[[a, b, c]]) > 0]
            if not cs:
                continue
            new.append([a, b, min(cs, key=lambda c: np.linalg.norm(uv[c] - uv[a]) + np.linalg.norm(uv[c] - uv[b]))])
        elif E[key(a, b)] != 1:
            continue
        add += new if ccw else [t[::-1] for t in new]
        n += 1
    if add:
        add = np.array(add, np.int64)
        p["T"] = T = np.vstack([T, add])
        if "tris" in p:
            p["tris"] = np.vstack([np.asarray(p["tris"], np.int64).reshape(-1, 3), add])
        E = edges(T)
        p["missing_boundary_edges"] = int(sum(key(j, (j + 1) % nb) not in E for j in range(nb)))
    return n


def game_mesh(drape: dict, M: dict, h: float, body=None, joints: dict | None = None, rows: int | None = None) -> dict:
    """The game mesh at ~h: outer + inner + rims (garment_game.shell), uv = the packed pattern atlas, and the outer
    mesh's pattern uv (metres) for the stretch. joints: see regrid (None: the old hex route). rows: piece_h's."""
    from . import garment_loops as gl
    pieces, m = regrid(drape, h, body, fold_lines(M), piece_h(M, h, rows), joints)
    m["quad_share"] = round(gl.quad_share(pieces), 3) if joints is not None else 0.0
    offs = np.cumsum([0] + [len(p["V"]) for p in pieces])[:-1]  # (merged stacks the pieces in order)
    m["quads"] = np.vstack([np.asarray(p.get("quads", np.zeros((0, 4), int))).reshape(-1, 4) + o
                            for p, o in zip(pieces, offs)])
    # (T14) the atlas is laid from the PATTERN pieces' boxes (garment_appearance.layout), so the appearance step's
    # textures, baked on the pattern before the game mesh exists, land on these UVs exactly
    from . import garment_appearance as ga
    lay = ga.layout(drape)
    uvs, side = [ga.atlas_uv(lay, p["name"], p["uv"]) for p in pieces], lay["side"]
    m["uv_pattern"], m["uv"] = m["uv"], np.vstack(uvs)
    sh = gg.shell(m, m["T"])
    sh.update({"outer": m, "h": h, "side": side, "pieces": [p["name"] for p in pieces],
               "missing_boundary_edges": int(sum(p["missing_boundary_edges"] for p in pieces))})
    return sh


def fit_budget(drape: dict, M: dict, budget: int, extra: int = 0, body=None, h0: float = 0.02,
               joints: dict | None = None, rows: int | None = None, h_max: float = H_MAX) -> tuple[dict, list]:
    """The finest grid whose triangles (+ extra: the details) fit the budget, within [H_MIN, h_max]: h scaled by
    sqrt(count / target) a few times. Returns (game mesh, tries [(h, triangles)]). Over budget at h_max: the h_max mesh
    (LOD0's caller refuses; a LOD says it is over its share). Among the tries that fit, one with every pattern edge
    closed wins over a finer one with open edges (a missing border edge is a hole at a seam)."""
    target, h, tries, best = BUDGET_FILL * budget - extra, min(h0, h_max), [], None
    rank = lambda m: (-m["missing_boundary_edges"], len(m["T"]))  # noqa: E731
    for _ in range(6):
        g = game_mesh(drape, M, h, body, joints, rows)
        n = len(g["T"])
        tries.append((round(h, 4), n))
        if n + extra <= budget and (best is None or rank(g) > rank(best)):
            best = g
        if target <= 0:
            h = h_max
        nh = float(np.clip(h * np.sqrt(n / max(target, 1.0)), H_MIN, h_max))
        if abs(nh - h) < 0.03 * h or (h == h_max and n + extra > budget) or (h == H_MIN and n <= target):
            if best is None and h != h_max:
                h = h_max
                continue
            break
        h = nh
    return (best if best is not None else g), tries


# ---------------------------------------------------------------- the LODs

def lod_plan(role: str) -> list[dict]:
    """[{"lod", "share", "budget", "rows", "h_max", "screen"}] for LOD1..: the role's clothing budget at each LOD
    (budgets.lod_ratios(PART): the share asset_export gives a part below the neck), the stiff pieces' rows and the
    coarsest grid scaled by sqrt(share) (triangles go with 1 / h^2), and the LOD's switch size (budgets.json
    lod_screen_size: the character's bounding sphere / the screen's larger dimension, below which the LOD is used)."""
    rs = budgets.lod_ratios(PART)
    ss = budgets.load()["characters"]["lod_screen_size"]["default"]
    out = []
    for k in range(1, len(rs)):
        q = float(np.sqrt(rs[k]))
        out.append({"lod": k, "share": float(rs[k]), "budget": budgets.triangles(role, PART, lod=k),
                    "rows": max(1, int(MADE_MIN_ROWS * q + 1e-9)), "h_max": round(min(H_MAX / q, H_MAX_LOD), 4),
                    "screen": float(ss[min(k, len(ss) - 1)])})
    return out


def on_surface(P: np.ndarray, V: np.ndarray, T: np.ndarray, k: int = 12) -> tuple[np.ndarray, np.ndarray]:
    """(corner vertex ids [n, 3], barycentrics [n, 3]) of the closest point of the triangle mesh (V, T) to each of P
    (the k triangles with the nearest centroids tried)."""
    from .rig_template import _closest_on_triangles
    P, T = np.atleast_2d(np.asarray(P, float)), np.asarray(T, np.int64)
    R = np.asarray(V, float)[T]
    k = min(k, len(R))
    cand = np.asarray(cKDTree(R.mean(1)).query(P, k=k)[1]).reshape(len(P), k)
    tri, bary, d = np.zeros(len(P), np.int64), np.zeros((len(P), 3)), np.full(len(P), np.inf)
    for j in range(k):
        t = cand[:, j]
        b, dj = _closest_on_triangles(P, R[t, 0], R[t, 1], R[t, 2])
        w = dj < d
        tri[w], bary[w], d[w] = t[w], b[w], dj[w]
    return T[tri], bary


def closest(P: np.ndarray, V: np.ndarray, T: np.ndarray) -> np.ndarray:
    """The closest point of the triangle mesh (V, T) to each of P."""
    c, b = on_surface(P, V, T)
    return (b[:, :, None] * np.asarray(V, float)[c]).sum(1)


def lod_details(details: dict, share: float, px_per_m: float) -> tuple[dict, dict]:
    """The details at a LOD -> ({name: {V, F, colour, "piece" (per vertex)}}, {name: {"pieces", "kept", "size_mm",
    "px", "triangles"}}). Each connected piece of a detail (one button) is LEFT OUT when its largest extent is under
    DETAIL_MIN_PX on screen at the LOD's switch size (px_per_m: pixels per metre there); a kept piece is decimated to
    the LOD's share of its triangles (never below DETAIL_MIN_TRIS). seat_details then moves them onto the LOD's cloth."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from .lods_pieces import _decimate
    out, info = {}, {}
    for name, x in details.items():
        V, F = np.asarray(x["V"], float), np.asarray(x["F"], np.int64)
        e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]]])
        lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(V),) * 2), directed=False)[1]
        Vs, Fs, Ps, sizes = [], [], [], []
        for c in np.unique(lab[F[:, 0]]):
            f = F[lab[F[:, 0]] == c]
            ids = np.unique(f)
            v, f = V[ids], np.searchsorted(ids, f)
            sizes.append(float((v.max(0) - v.min(0)).max()))
            if sizes[-1] * px_per_m < DETAIL_MIN_PX:
                continue
            tgt = max(DETAIL_MIN_TRIS, int(round(share * len(f))))
            if tgt < len(f):
                v2, f2 = _decimate(v, f, tgt, border=False)
                if len(f2) >= 4:
                    v, f = v2, f2
            Fs.append(f + sum(len(a) for a in Vs))
            Ps.append(np.full(len(v), len(Ps)))
            Vs.append(v)
        size = float(np.median(sizes)) if sizes else 0.0
        info[name] = {"pieces": len(sizes), "kept": len(Vs), "size_mm": round(size * 1000, 1),
                      "px": round(size * px_per_m, 1), "triangles": int(sum(len(f) for f in Fs))}
        if Vs:
            out[name] = {"V": np.vstack(Vs), "F": np.vstack(Fs), "colour": x.get("colour"), "piece": np.concatenate(Ps)}
    return out, info


def seat_details(details: dict, V0, T0, Vk, Tk) -> None:
    """Each kept detail piece moved rigidly with the cloth under it: from its foot on LOD0's outer surface (V0, T0) to
    that foot's nearest point on the LOD's (Vk, Tk). A coarser grid's chords sink: a button left where LOD0 had it
    floats over the LOD's cloth, or is buried in it."""
    for x in details.values():
        for c in np.unique(x["piece"]):
            m = x["piece"] == c
            foot = closest(x["V"][m].mean(0), V0, T0)
            x["V"][m] += closest(foot, Vk, Tk) - foot


def details_text(info: dict) -> str:
    """One LOD's details in words: what was kept (simplified) and what was left out, with the size that decided it."""
    if not info:
        return "no details"
    bits = []
    for n, v in info.items():
        what = (f"{v['kept']} of {v['pieces']} kept, {v['triangles']} triangles" if v["kept"] else "left out")
        bits.append(f"{n} {what} ({v['size_mm']:.0f} mm = {v['px']:.1f} px)")
    return "; ".join(bits)


# ---------------------------------------------------------------- numbers

def uv_stretch(m: dict) -> dict:
    """Per outer triangle: sqrt(3D area / pattern area) (1 = the cloth as cut). p5 / p50 / p95 / max."""
    return stretch(m["V"], m["uv_pattern"], m["T"])


def stretch(V, U, T) -> dict:
    """sqrt(3D area / pattern area) per triangle: p5 / p50 / p95 / max (the drape's own: drape_of's V, uv, F)."""
    V, U, T = np.asarray(V, float), np.asarray(U, float), np.asarray(T, np.int64)
    a3 = 0.5 * np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1)
    d1, d2 = U[T[:, 1]] - U[T[:, 0]], U[T[:, 2]] - U[T[:, 0]]
    a2 = 0.5 * np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0])
    ok = a2 > 1e-12
    s = np.sqrt(a3[ok] / a2[ok])
    q = np.percentile(s, [5, 50, 95]) if len(s) else [0, 0, 0]
    return {"p5": round(float(q[0]), 3), "p50": round(float(q[1]), 3), "p95": round(float(q[2]), 3),
            "max": round(float(s.max()) if len(s) else 0.0, 3), "faces": int(ok.sum())}


def bone_index(rb: list[dict], short: str) -> int:
    names = [b["name"] for b in rb]
    for i, n in enumerate(names):
        if n == short or n.split(":")[-1] == short:
            return i
    raise ExportRefused(f"no rig bone {short!r} for the weight check (rig: {', '.join(names[:12])} ...)")


def skin(spec: dict, rb: list[dict], V: np.ndarray, T: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """T11's weights (the old route, kept for comparison): rig_skin.skin_parts' transfer, not smoothed over the cloth.
    The export uses garment_bend.skin (projected + geodesic)."""
    from . import rig_skin
    return rig_skin.skin_parts(spec, rb, {"garment_export_probe": (np.asarray(V, float), np.asarray(T, np.int64))},
                          smooth=3)["garment_export_probe"]


def details_of(d: Path, hung: bool) -> dict:
    """T10's details (details.pkl): {name: {V, F, colour}} on the hung garment when there is one, else the build."""
    p = Path(d) / "details.pkl"
    if not p.exists():
        return {}
    x = pickle.load(open(p, "rb"))
    src = x.get("hung") if hung and x.get("hung") else x.get("built")
    return {n: {"V": np.asarray(m["V"], float), "F": np.asarray(m["F"], np.int64), "colour": m.get("colour")}
            for n, m in (src or {}).items()}


def hex_rgb(c) -> list:
    if isinstance(c, str) and c.startswith("#") and len(c) == 7:
        return [int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    if isinstance(c, (list, tuple)) and len(c) == 3:
        return [float(x) / (255 if max(c) > 1 else 1) for x in c]
    return [0.8, 0.8, 0.8]


def text(model, garment, src, g, n_details, budget, role, tries, st, bend, glb, sd, winfo) -> list[str]:
    from . import garment_bend as gb
    tot = len(g["T"]) + n_details
    o = g["outer"]
    return [f"{model}:{garment} export (step 10) from the {src}: {glb}",
            f"  triangles {tot} / budget {budget} ({role} {PART} LOD0): garment {len(g['T'])} (outer {g['outer_faces']}, "
            f"inner {g['inner_faces']}, rims {g['rim_faces']}) + details {n_details}; grid {g['h'] * 1000:.0f} mm "
            f"(tries {', '.join(f'{h * 1000:.0f} mm: {n}' for h, n in tries)}); stiff pieces to {MADE_MIN_ROWS} rows; "
            f"loops: quad share {o.get('quad_share', 0):.2f}",
            f"  UVs = the pattern ({len(g['pieces'])} pieces packed, square {g['side']:.2f} m); stretch 3D / pattern "
            f"p5 {st['p5']} p50 {st['p50']} p95 {st['p95']} max {st['max']} (the drape's own: p5 {sd['p5']} p95 {sd['p95']}; "
            f"informational: no named limit); open pattern edges {g['missing_boundary_edges']}",
            f"  weights: the body's at each vertex's projected skin point, smoothed over the garment within "
            f"{winfo.get('geo_radius_m', 0) * 100:.1f} cm (stand-off p95 {winfo['standoff_p95_m'] * 100:.1f} cm)"] + gb.rows_text(bend)


def gate_rows(g, n_details, budget, st, bend, sd, lods=()) -> list[dict]:
    """Step 10's gate rows, each named by "id" (the key garment_record keeps: the record and the character's export
    name a failed row by it). lods: the LOD entries (run's): a LOD with an open pattern edge fails; over its share is
    information (the share is the character's LOD target, not a named limit)."""
    tot = len(g["T"]) + n_details
    rows = [{"id": "triangles", "status": "PASS" if tot <= budget else "FAIL", "value": tot, "target": budget},
            {"id": "uv stretch vs the drape (informational)", "status": "INFO", "value": [st["p5"], st["p95"]],
             "target": f"the drape's p5 {sd['p5']} p95 {sd['p95']}: no named limit"},
            {"id": "open pattern edges", "status": "PASS" if g["missing_boundary_edges"] == 0 else "FAIL",
             "value": g["missing_boundary_edges"], "target": 0}]
    L = bend["limits"]
    for pn, r in bend["poses"].items():
        rows.append({"id": f"bends cleanly: {pn}", "status": "PASS" if r["ok"] else "FAIL",
                     "value": {"strain_p99": r["strain_p99"], "new_creases": r["new_creases"], "where": r["crease_where"]},
                     "target": f"strain over the skin's p99 <= {L['strain_p99']}; no new crease past {L['crease_deg']} deg"})
    for x in lods:
        k = x["lod"]
        rows.append({"id": f"LOD{k} open pattern edges", "status": "PASS" if x["open_edges"] == 0 else "FAIL",
                     "value": x["open_edges"], "target": 0})
        rows.append({"id": f"LOD{k} triangles vs its share (informational)", "status": "INFO", "value": x["triangles"],
                     "target": f"{x['budget']} ({x['share']:g} of the {PART} budget)"})
    return rows


def budget_for(role: str) -> int:
    try:
        return budgets.triangles(role, PART)
    except KeyError as e:
        raise ExportRefused(f"role {role!r}: {e.args[0]}") from None


def write_json(path: Path, out: dict) -> None:
    Path(path).write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
