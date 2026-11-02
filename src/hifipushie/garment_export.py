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
  * skinned to the character's rig (rig.rig_bones: Mixamo names) with weights READ OFF THE BODY (rig.skin_parts: the
    base body's own weights at its surface, smoothed; clothes move with the skin under them); a detail takes the
    weights of the garment vertex nearest it (a button rides the cloth).
Numbers (the text): triangles vs budget, UV stretch (3D edge / pattern edge per triangle: the drape vs its cut), the
weight check (one arm raised 45 deg: how far each garment vertex's distance to the body changes where the body moved).
The look (shape only): the GLB rendered in EEVEE (asset.preview), rest and posed, beside the reference.

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


def piece_h(M: dict, h: float) -> dict:
    """{piece: edge}: h, finer on the stiff (made) pieces to MADE_MIN_ROWS rows across their short side."""
    uv, pc, out = np.asarray(M["uv"], float), np.asarray(M["piece"]), {}
    made = set(M.get("made") or [])
    for i, n in enumerate(M["names"]):
        e = h
        if n in made:
            s = uv[pc == i]
            short = float(np.min(s.max(0) - s.min(0))) if len(s) else h
            e = min(h, max(H_MIN, short / MADE_MIN_ROWS))
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


def game_mesh(drape: dict, M: dict, h: float, body=None, joints: dict | None = None) -> dict:
    """The game mesh at ~h: outer + inner + rims (garment_game.shell), uv = the packed pattern atlas, and the outer
    mesh's pattern uv (metres) for the stretch. joints: see regrid (None: the old hex route)."""
    from . import garment_loops as gl
    pieces, m = regrid(drape, h, body, fold_lines(M), piece_h(M, h), joints)
    m["quad_share"] = round(gl.quad_share(pieces), 3) if joints is not None else 0.0
    offs = np.cumsum([0] + [len(p["V"]) for p in pieces])[:-1]  # (merged stacks the pieces in order)
    m["quads"] = np.vstack([np.asarray(p.get("quads", np.zeros((0, 4), int))).reshape(-1, 4) + o
                            for p, o in zip(pieces, offs)])
    uvs, side = gg.atlas(pieces)
    m["uv_pattern"], m["uv"] = m["uv"], np.vstack(uvs)
    sh = gg.shell(m, m["T"])
    sh.update({"outer": m, "h": h, "side": side, "pieces": [p["name"] for p in pieces],
               "missing_boundary_edges": int(sum(p["missing_boundary_edges"] for p in pieces))})
    return sh


def fit_budget(drape: dict, M: dict, budget: int, extra: int = 0, body=None, h0: float = 0.02,
               joints: dict | None = None) -> tuple[dict, list]:
    """The finest grid whose triangles (+ extra: the details) fit the budget, within [H_MIN, H_MAX]: h scaled by
    sqrt(count / target) a few times. Returns (game mesh, tries [(h, triangles)]). Over budget at H_MAX: the H_MAX mesh
    (the caller refuses)."""
    target, h, tries, best = BUDGET_FILL * budget - extra, h0, [], None
    for _ in range(6):
        g = game_mesh(drape, M, h, body, joints)
        n = len(g["T"])
        tries.append((round(h, 4), n))
        if n + extra <= budget and (best is None or n > len(best["T"])):
            best = g
        if target <= 0:
            h = H_MAX
        nh = float(np.clip(h * np.sqrt(n / max(target, 1.0)), H_MIN, H_MAX))
        if abs(nh - h) < 0.03 * h or (h == H_MAX and n + extra > budget) or (h == H_MIN and n <= target):
            if best is None and h != H_MAX:
                h = H_MAX
                continue
            break
        h = nh
    return (best if best is not None else g), tries


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
    """T11's weights (the old route, kept for comparison): rig.skin_parts' transfer, not smoothed over the cloth.
    The export uses garment_bend.skin (projected + geodesic)."""
    from . import rig
    return rig.skin_parts(spec, rb, {"garment_export_probe": (np.asarray(V, float), np.asarray(T, np.int64))},
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


def gate_rows(g, n_details, budget, st, bend, sd) -> list[dict]:
    tot = len(g["T"]) + n_details
    rows = [{"row": "triangles", "status": "PASS" if tot <= budget else "FAIL", "value": tot, "target": budget},
            {"row": "uv stretch vs the drape (informational)", "status": "INFO", "value": [st["p5"], st["p95"]],
             "target": f"the drape's p5 {sd['p5']} p95 {sd['p95']}: no named limit"},
            {"row": "open pattern edges", "status": "PASS" if g["missing_boundary_edges"] == 0 else "FAIL",
             "value": g["missing_boundary_edges"], "target": 0}]
    L = bend["limits"]
    for pn, r in bend["poses"].items():
        rows.append({"row": f"bends cleanly: {pn}", "status": "PASS" if r["ok"] else "FAIL",
                     "value": {"strain_p99": r["strain_p99"], "new_creases": r["new_creases"], "where": r["crease_where"]},
                     "target": f"strain over the skin's p99 <= {L['strain_p99']}; no new crease past {L['crease_deg']} deg"})
    return rows


def budget_for(role: str) -> int:
    try:
        return budgets.triangles(role, PART)
    except KeyError as e:
        raise ExportRefused(f"role {role!r}: {e.args[0]}") from None


def write_json(path: Path, out: dict) -> None:
    Path(path).write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
