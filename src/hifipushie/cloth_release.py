"""Worn open = the CLOSED fit on the dress form, then ONE short sim that lets the closure go (Joe 2026-10-20).

Why: five rounds of gravity-free holds on the form (OPEN_HOLD, WORN_EDGE, SWING_UNPINNED, ROLL_TURN, CHEST_HOLD) could
not make an unbuttoned front swing open and hang: that is gravity with contact, which the form doesn't have
(docs/state/pattern_form.md "missing physics"). A tailor's fitting is done buttoned; the jacket is then worn open. So:

1. fit CLOSED on the form (pattern_form.assemble, the top button fastened, worn_open None): the balance, the chest, the
   shoulders and the lapel's roll come from the pattern there, and that fit passes the pattern gate first;
2. RELEASE: the fitted state is the sim's START (positions), the flat pattern its REST (membrane: rest "flat"; bending
   flat except at the fold lines, which rest folded: folds.bend_reference; the made pieces, wholly interfaced, rest as
   fitted), the seams and the non-closure stitches sewn, the closure(s) named in `release` NOT sewn, the under garment
   (its form fit, pressed back under this one where it comes within `clear` of it) and the body one static collider,
   gravity on, a short settle. Nothing else: no pins, no holds, no solver tuning.

Schedule (24 fps): SEW_FRAMES with gravity 0 (the fit's seams start closed: the runner steps their ends apart, a few
frames draw them shut), then SETTLE_FRAMES of gravity (2 s: a jacket front is a ~0.35-0.45 m pendulum, period
2 pi sqrt(L/g) = 1.2-1.3 s, so it swings out and damps within about one and a half periods), then SELF_FRAMES (1 s: the
"still moving" read, Vprev = 6 frames before the end).

The job is an ordinary cloth_job folder (cloth_job.write + the pattern gate's keys): cloth_job.run_zozo runs it, locally
or rented, and refuses it without a PASS record for the pattern + body (pattern_gate), like every sim.
Entry points: `job` (arrays from a placed pattern + its fitted state), `from_form` (a model's garment: on_form closed ->
job), `write`, `run`, `moved` (how far the sim moved each piece / band from the fit). MCP: release_garment.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

SEW_FRAMES = 4
SETTLE_FRAMES = 48
SELF_FRAMES = 24
CLEAR = 0.0035  # m: the least the under garment (a collider) lies under this one at the start (preflight wants >= 2 mm)


def closure_stitches(M: dict, release=("front",)) -> tuple[np.ndarray, list]:
    """The closures that stay fastened as stitches (over vertex, under vertex): every closure whose state is closed
    and whose name is not in `release`. A released closure (an open front fitted at its top button) sews nothing.
    Returns (pairs [k, 2], the released closures' names)."""
    keep, gone = [], []
    rel = set(release or ())
    for c in M.get("closures") or []:
        if c.get("name") in rel:
            gone.append(c["name"])
            continue
        if c.get("state") == "closed":
            keep += [tuple(int(x) for x in v) for v in c.get("v") or []]
    return np.asarray(keep, np.int64).reshape(-1, 2), gone


def clear_under(X: np.ndarray, F: np.ndarray, U: np.ndarray, FU: np.ndarray, body, gap: float = CLEAR,
                most=None, edge_gap: float = 0.0023, rounds: int = 10,
                free: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """The under garment (a static collider in the release) pressed back toward the body wherever this garment's start
    (X, F) lies closer than `gap` above it, or through it: each under vertex moves along its outward normal (oriented
    away from the body) by what it lacks to the garment's SURFACE (closest point on its triangles), at most `most`;
    then edge pairs closer than `edge_gap` (what the solver's edge-edge contact and cloth_job.preflight see between
    vertices) push their under vertices further. The under cloth is soft and lies under this one (cloth.pressed's
    rule), and the garment being judged is not moved. `most`: the furthest a vertex may go (m, scalar or per vertex);
    None = down to the body under it (the fit left the shirt's upper sleeves 20+ mm outside the jacket's: validation
    2's magenta, a fit fault reported by the press numbers). Returns (U moved, info)."""
    from .cloth_over import closest, edge_pairs
    from .pattern_form import _Surface, _body_surface
    U = np.asarray(U, float).copy()
    U0 = U.copy()
    X = np.asarray(X, float)
    F = np.asarray(F)
    FU = np.asarray(FU)
    bs = _body_surface(body)
    N = _Surface(U, FU, ref=bs).N
    if most is None:  # pressed at most down onto the body (a cloth can't go into it; pressed there it IS the body)
        most = np.maximum(bs.signed(U)[0] + 0.001, 0.0)
    free = np.ones(len(X), bool) if free is None else np.asarray(free, bool)
    Q = closest(U, X, F[free[F].any(1)])[0]  # (held pieces pass through the collider: nothing to press under them)
    D = Q - U
    near = np.linalg.norm(D, axis=1) < 0.015
    h = np.sum(D * N, 1)
    most = np.broadcast_to(np.asarray(most, float), (len(U),))
    push = np.where(near, np.maximum(0.0, gap - h), 0.0)
    U -= N * np.minimum(push, most)[:, None]
    for _ in range(rounds):
        _, bE, dd, _ = edge_pairs(X, F, (U, FU), free, edge_gap)
        if not len(bE):
            break
        extra = np.zeros(len(U))
        for (i, j), di in zip(bE, dd):
            for v in (i, j):
                extra[v] = max(extra[v], edge_gap - di + 3e-4)
        U -= N * extra[:, None]
    mv = np.linalg.norm(U - U0, axis=1)
    over = mv > most + 1e-9
    if over.any():  # (never further than `most` in all: more is a fit fault, reported)
        U[over] = U0[over] + (U[over] - U0[over]) * (most[over] / mv[over])[:, None]
    mv = np.linalg.norm(U - U0, axis=1)
    # what no press parts (the under garment's own fins and seams standing through this one, at its armholes and
    # neck: their normals point every way): those faces leave the collider, the body under them stays
    _, bE, _, _ = edge_pairs(X, F, (U, FU), free, edge_gap)
    bad = np.zeros(len(U), bool)
    bad[np.asarray(bE, np.int64).reshape(-1)] = True
    keep = ~bad[FU].any(1)
    return U, {"faces_keep": keep, "dropped_faces": int((~keep).sum()), "pressed": int((mv > 0).sum()), "press_p50_mm": round(float(np.median(mv[mv > 0]) * 1000), 2)
               if (mv > 0).any() else 0.0, "press_p99_mm": round(float(np.percentile(mv, 99) * 1000), 2),
               "press_max_mm": round(float(mv.max() * 1000), 2), "at_most": int(over.sum())}


def clear_body(X: np.ndarray, body, gap: float = 0.0036, free: np.ndarray | None = None, M: dict | None = None,
               most: float = 0.004, rounds: int = 3) -> tuple[np.ndarray, dict]:
    """The garment's free vertices that the fit left closer than `gap` to the BODY (pattern_form's contact is a
    proximal push: a few end on or just inside it; the solver can't start there) moved out along the body's outward
    normal at their closest point, at most `most` in all (more is a fit fault: reported, left). Vertices only: an edge
    pass (cloth_over.clear_start's) walked the upper back 14 mm off a body it was 0.7 mm inside (fit round 16 job b)."""
    from .pattern_form import _body_surface
    X0 = np.asarray(X, float)
    X1 = X0.copy()
    fr = np.ones(len(X0), bool) if free is None else np.asarray(free, bool)
    bs = _body_surface(body)
    for _ in range(rounds):
        d, n, _ = bs.signed(X1)
        b = fr & (d < gap)
        if not b.any():
            break
        X1[b] += n[b] * (gap - d[b] + 1e-4)[:, None]
    mv = np.linalg.norm(X1 - X0, axis=1)
    big = mv > most
    X1[big] = X0[big] + (X1[big] - X0[big]) * (most / mv[big])[:, None]
    mv = np.linalg.norm(X1 - X0, axis=1)
    out = {"moved": int((mv > 0).sum()), "max_mm": round(float(mv.max() * 1000), 2), "at_most": int(big.sum())}
    if M is not None and out["moved"]:
        pid = np.asarray(M["piece"])
        out["by_piece_max_mm"] = {nm: round(float(mv[pid == k].max() * 1000), 1) for k, nm in enumerate(M["names"])
                                  if (mv[pid == k] > 1e-6).any()}
    return X1, out


def neck_pieces(Bp: dict, M: dict, made: list) -> list:
    """The made pieces round the neck (stand, collar): wrapped to the neck, or sewn on a seam (wrap "seam") without
    lying on another piece (a pocket flap lies on its front and swings with it)."""
    out = []
    for nm in made:
        w = ((Bp.get("pieces") or {}).get(nm) or {}).get("wrap") or {}
        if w.get("to") == "neck" or (w.get("to") == "seam" and not w.get("lies_on")):
            out.append(nm)
    return out


def job(res: dict, X: np.ndarray, g: dict | None = None, under: dict | None = None, body=None,
        release=("front",), hold=("neck",), frames: int = SETTLE_FRAMES, settle_frames: int = SELF_FRAMES,
        sew_frames: int = SEW_FRAMES, clear: float = CLEAR, zozo: dict | None = None,
        name: str | None = None, pad_base=None) -> tuple[dict, dict, dict]:
    """The release sim's (cfg, arrays, info). res: the placed pattern (cloth.build place_only: "mesh", "pieces",
    "fabric", "body", "gate_keys"); X: its fitted state on the form (pattern_form.assemble "V"); g: the garment dict
    (zozo options, strain limit); under: {"V", "F"} the under garment's form fit (or None); body: the collider body
    (default res["body"]; a padded body when the fit used a shoulder pad: the pad is sewn into this garment);
    pad_base: the body without the pad (then the pad, soft wadding, is pressed under the garment like the under
    garment, never below the body: the fit's contact is a proximal push and left the back up to 14 mm into it)."""
    from . import cloth, folds as foldmod
    M = res["mesh"]
    Bp = res["pieces"]
    g = g or {}
    body = body if body is not None else res["body"]
    X = np.asarray(X, float)
    uv = np.asarray(M["uv"], float)
    stiff = cloth.interfacing(Bp, M)
    made = cloth.made_pieces(M, stiff)
    cst, gone = closure_stitches(M, release)
    stitch = np.r_[np.asarray(M["stitch"], np.int64).reshape(-1, 2), cst]
    info = {"released": gone, "closure_stitches": int(len(cst)), "made": made}
    # pieces held as fitted for the whole sim (cloth.build method "settle"'s carried made pieces): those that wrap
    # `hold` (the neck: stand, collar). The neck doesn't move when a front is unbuttoned, and the shirt collar under a
    # jacket's collar is a fold over a fold no normal press can part (1144 edge pairs within 2 mm, fit round 16 job a)
    pid = np.asarray(M["piece"])
    held_pcs = neck_pieces(Bp, M, made) if hold == ("neck",) else [nm for nm in (hold or ()) if nm in M["names"]]
    carry = np.where(np.isin(pid, [M["names"].index(nm) for nm in held_pcs]))[0]
    info["held"] = held_pcs
    free = np.ones(len(X), bool)
    free[carry] = False
    if pad_base is not None:
        import types as _types
        lift = np.linalg.norm(np.asarray(body.V, float) - np.asarray(pad_base.V, float), axis=1)
        Vp, pinfo = clear_under(X, M["F"], body.V, np.asarray(body.T), pad_base, clear, most=lift, free=free)
        pinfo.pop("faces_keep")
        info["pad"] = dict(pinfo, lift_max_mm=round(float(lift.max() * 1000), 1))
        body = _types.SimpleNamespace(V=Vp, T=np.asarray(body.T), at=getattr(body, "at", {}))
    X, info["body_clear"] = clear_body(X, body, free=free, M=M)
    if under is not None:
        U, uinfo = clear_under(X, M["F"], under["V"], np.asarray(under["F"]), body, clear, free=free)
        keep = uinfo.pop("faces_keep")
        info["under"] = uinfo
        coll = cloth._collider(body, {"V": U, "F": np.asarray(under["F"])[keep], "res": True}, False)
    else:
        coll = cloth._collider(body, None, False)
    # the few edge pairs left (a collider edge between two of the garment's vertices): both free ends stepped off along
    # the pair's separation (cloth_over.clear_start's edge pass), at most 2 mm (it walked 14 mm where crossings were
    # left; with them gone it moves only the ends of the remaining pairs)
    from .cloth_over import clear_start
    X1, _ = clear_start(X, (np.asarray(coll["bodyV"], float), np.asarray(coll["bodyT"])), free, 0.0021,
                        rounds=2, F=np.asarray(M["F"]))
    mv = np.linalg.norm(X1 - X, axis=1)
    cap = mv > 0.002
    X1[cap] = X[cap] + (X1[cap] - X[cap]) * (0.002 / mv[cap])[:, None]
    info["edge_clear"] = {"moved": int((mv > 0).sum()), "max_mm": round(float(min(mv.max(), 0.002) * 1000), 2),
                          "capped": int(cap.sum())}
    X = X1
    arrays = dict(X=X, uv=uv, F=np.asarray(M["F"], np.int64), sew=np.asarray(M["sew"], np.int64).reshape(-1, 2),
                  stitch=stitch, stiff=stiff, piece=np.asarray(M["piece"], np.int64), pins=np.zeros(0, np.int64),
                  bodyV=np.asarray(coll["bodyV"], float), bodyT=np.asarray(coll["bodyT"], np.int64))
    if len(carry):  # (held: pinned where fitted, passing through the collider as cloth.build's hugIdx bands do)
        arrays.update(carryIdx=carry.astype(np.int64), carryPoses=X[carry][None], hugIdx=carry.astype(np.int64))
    if M.get("folds"):
        arrays["fold"] = foldmod.weights(M)
        arrays["bend_rest"] = foldmod.bend_reference(M, np.c_[uv, np.zeros(len(uv))], Bp.get("faces"))
    z = {"rest": "flat"}
    z.update(g.get("zozo") or {})
    z.update(zozo or {})
    cfg = {"name": name or (res.get("gate_keys") or {}).get("name") or "release", "fabric": res["fabric"],
           "frames": int(frames), "settle_frames": int(settle_frames), "sew_frames": int(sew_frames),
           "self_collision": True, "made": made, "zozo": z, "backend": "zozo", "release": list(gone),
           **({"strain_limit": cloth.strain_limit_of(g)} if cloth.strain_limit_of(g) > 0.05 else {})}
    dec = cloth.declared_pieces(Bp, M["names"]) if Bp.get("seam_notes") else {}
    if dec:
        cfg["declared"] = dec
    info["seconds_gravity"] = (frames + settle_frames) / 24.0
    return cfg, arrays, info


def write(job_dir: Path, cfg: dict, arrays: dict, names: list, gate: dict | None) -> Path:
    """The job folder (cloth_job.write) with the pattern gate's keys beside it (run_zozo refuses without a PASS)."""
    from . import cloth_job
    jd = cloth_job.write(Path(job_dir), cfg, arrays, names)
    cloth_job.write_gate_keys(jd, gate)
    return jd


def preflight(job_dir: Path) -> dict:
    from . import cloth_job
    import json
    jd = Path(job_dir)
    arr = dict(np.load(jd / "in.npz", allow_pickle=False))
    return cloth_job.preflight(arr, json.loads((jd / "job.json").read_text()))


def run(job_dir: Path, progress=print, log=print) -> tuple:
    """cloth_job.run_zozo on the folder (rented only inside cloth_job.submitting() / HP_SUBMIT_SIMS=1)."""
    from . import cloth_job
    return cloth_job.run_zozo(Path(job_dir), progress, log)


def moved(M: dict, X0: np.ndarray, X1: np.ndarray) -> dict:
    """How far the release moved each piece from the fit: {piece: {"p50", "p90", "max"} mm}."""
    d = np.linalg.norm(np.asarray(X1, float) - np.asarray(X0, float), axis=1) * 1000
    pid = np.asarray(M["piece"])
    out = {}
    for k, nm in enumerate(M["names"]):
        s = d[pid == k]
        if len(s):
            out[nm] = {"p50": round(float(np.median(s)), 1), "p90": round(float(np.percentile(s, 90)), 1),
                       "max": round(float(s.max()), 1)}
    return out


def from_form(model: str, garment: str, spec: dict | None = None, release=("front",), log=None) -> dict:
    """A model's garment fitted CLOSED on the form (pattern_form.on_form, worn_open off) and its release job.
    Returns {"res" (on_form's result), "cfg", "arrays", "info", "gate"}."""
    import json as _json
    from . import pattern_form, store
    spec = spec or store.load(model)
    g = _json.loads(_json.dumps(spec["cloth"][garment]))
    g.pop("worn_open", None)  # (the closed fit: the top button fastened, pattern_form.fastened "default")
    res = pattern_form.on_form(model, garment, spec, g=g, log=log)
    und = res.get("form_under")
    under = {"V": und["A"], "F": und["mesh"]["F"]} if und is not None else None
    body = pattern_form.padded_body(res["body"], g.get("shoulder_pad")) if g.get("shoulder_pad") else res["body"]
    cfg, arrays, info = job(res, res["A"], g, under=under, body=body, release=release, name=f"{model}:{garment}")
    return {"res": res, "cfg": cfg, "arrays": arrays, "info": info, "gate": res.get("gate_keys")}
