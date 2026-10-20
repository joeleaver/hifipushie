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
CLEAR = 0.003  # m: the least the under garment (a collider) lies under this one at the start (preflight wants >= 2 mm)
CLEAR_MAX = 0.02  # m: never press the under garment further than this (more is a fit fault: report it)


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


def clear_under(X: np.ndarray, U: np.ndarray, FU: np.ndarray, body, gap: float = CLEAR,
                most: float = CLEAR_MAX) -> tuple[np.ndarray, dict]:
    """The under garment (a static collider in the release) pressed back toward the body wherever this garment's start
    lies closer than `gap` above it (or through it): each under vertex moves along its outward normal (oriented away
    from the body) by what it lacks, at most `most`. The under cloth is soft and lies under this one: this is the
    same rule the sims' cloth.pressed applies, not a move of the garment being judged. Returns (U moved, info)."""
    from .pattern_form import _Surface, _body_surface
    U = np.asarray(U, float).copy()
    X = np.asarray(X, float)
    us = _Surface(U, FU, ref=_body_surface(body))
    N = us.N
    tx = cKDTree(X)
    push = np.zeros(len(U))
    for i, js in enumerate(tx.query_ball_point(U, 0.012)):
        if not js:
            continue
        D = X[js] - U[i]
        h = D @ N[i]
        lat = np.linalg.norm(D - np.outer(h, N[i]), axis=1)
        h = h[lat < 0.008]
        if len(h):
            push[i] = max(0.0, gap - float(h.min()))
    over = push > most
    push = np.minimum(push, most)
    U -= N * push[:, None]
    return U, {"pressed": int((push > 0).sum()), "press_p50_mm": round(float(np.median(push[push > 0]) * 1000), 2)
               if (push > 0).any() else 0.0, "press_max_mm": round(float(push.max() * 1000), 2),
               "over_most": int(over.sum())}


def job(res: dict, X: np.ndarray, g: dict | None = None, under: dict | None = None, body=None,
        release=("front",), frames: int = SETTLE_FRAMES, settle_frames: int = SELF_FRAMES,
        sew_frames: int = SEW_FRAMES, clear: float = CLEAR, zozo: dict | None = None,
        name: str | None = None) -> tuple[dict, dict, dict]:
    """The release sim's (cfg, arrays, info). res: the placed pattern (cloth.build place_only: "mesh", "pieces",
    "fabric", "body", "gate_keys"); X: its fitted state on the form (pattern_form.assemble "V"); g: the garment dict
    (zozo options, strain limit); under: {"V", "F"} the under garment's form fit (or None); body: the collider body
    (default res["body"]; a padded body when the fit used a shoulder pad: the pad is sewn into this garment)."""
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
    if under is not None:
        U, uinfo = clear_under(X, under["V"], np.asarray(under["F"]), body, clear)
        info["under"] = uinfo
        coll = cloth._collider(body, {"V": U, "F": np.asarray(under["F"]), "res": True}, False)
    else:
        coll = cloth._collider(body, None, False)
    arrays = dict(X=X, uv=uv, F=np.asarray(M["F"], np.int64), sew=np.asarray(M["sew"], np.int64).reshape(-1, 2),
                  stitch=stitch, stiff=stiff, piece=np.asarray(M["piece"], np.int64), pins=np.zeros(0, np.int64),
                  bodyV=np.asarray(coll["bodyV"], float), bodyT=np.asarray(coll["bodyT"], np.int64))
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
