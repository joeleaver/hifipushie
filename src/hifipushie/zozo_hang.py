"""The HANG stage of a garment fit as a short ZOZO settle under gravity, run on this machine (PROVISIONAL, Joe
2026-10-28: "We can provisionally use ZOZO, keep using it on the laptop for now, while we're figuring this out").

Design: our pattern + fit place the garment (pattern-aware, threads hard, per-piece misfit reads); ZOZO
(cloth_zozo.py, the release's own runner) settles it under gravity for SETTLE_S seconds, held ONLY by real supports
(the body's contact and friction; no pins, holds or carried pieces); our gates read the result. One code path, the
same settings for every garment; every number comes from the fabric table (cloth_job.PHYSICAL), the fit's own thread
model (pattern_form.FIT_THREAD_CAP, SHEAR_LOCK_DEG) or the runner's documented defaults. Selected by
pattern_form.HANG_SOLVER / garment key "hang_solver" = "zozo" (the old quasi-static hang stays "ours" for A/B).

The four handoff rules (the reference run, docs/state/zozo_ref.md, needed four workarounds; each is a rule here):
1. START STRAIN: ZOZO's strain limit is ISOTROPIC (the largest principal stretch, strain_toi.kernel.cpp
   shell_max_strain), while its Baraff-Witkin membrane already takes stretch along the threads (uv) apart from shear.
   A woven's threads cap ~2 % but its bias shears freely to the weave's jamming angle, and a sheared square's largest
   principal stretch is (1 + cap) sqrt(1 + sin(shear)): the most a woven can take is woven_limit() = (1 + cap)
   sqrt(1 + sin(lock)) - 1 (2 %, 35 deg: 27.9 %). That is the strain limit for wovens (a knit keeps its fabric's own
   limit, cloth.strain_limit_of). The limit then forbids only what the weave can't do; the threads are held by the
   membrane's stretch stiffness (fabric table) and READ after the settle (threads past cap p99, as fit_garment reads
   it). No local loosening (the reference's releaseIdx "lift").
2. CLEARANCE, DERIVED (round 2): an edge of length L lying on a surface of convex radius R dips by its chord sag
   (sagitta ~ L^2 / 8R), so a vertex at the solver's standoff is not enough: each vertex's contact plane lies at
   CLEARANCE (the runner's body_offset + contact_gap) + the sag of its longest incident SETTLED edge over the
   collider's tightest convex radius at its foot (Clearance; pattern_form on_form -> assemble(skin=...) and
   hard_threads via res["hard_skin_v"]). A coarse settle counts the coarse mesh's edges (settle_edge_len), so the
   coarse start needs no push-out either. What the linearised planes leave inside is REPORTED, never pushed.
3. MADE PIECES (collar, stand, cuffs, bands; cloth.made_pieces): rest as MADE = their intended worn shape from the
   draft (round 4, C252: made_rest, the placement's made shape: laid on the wrap, folded at the declared lines, the
   drape band's worn mesh), sent as in.npz "rest"; not as the fit left them (round 3: the fit's crumples became rest).
   The fabric table's interfacing bending (PHYSICAL interfacing_bend) on interfaced vertices.
   The start passes ZOZO's two frame-0 tests in the pre-flight: contact (legality, C249) and start strain
   (start_strain, C252: no face at or past its own limit, as the runner sets it).
4. FOLDS: every declared fold line (folds.py: hems, plackets, folded bands, a collar's fall line, cuff turn-backs)
   carries its bending REST ANGLE (folds.bend_reference: the flat pattern folded at its lines) and the pressed rows'
   stiffer bending (the runner's fold_press); made pieces rest folded as made.
Seams: ZOZO keeps a seam's two edges a contact gap apart (the ~1.3 mm light lines): the sewn vertices are WELDED after
the settle (cloth.cleanup's weld only: each sewn group at its mean, no smoothing, no push), as every ZOZO result is.
Coarse vs fine: settle(coarse=m) settles a coarse mesh of the same pattern (cloth.build place_only at m) started from
the fit carried over by pattern position, and carries the result back onto the fit's mesh the same way.
The fit's pattern gate decides (fit_garment refuses an unpassed pattern unless force=True, "only to look"); settle()
refuses unless told the gate passed or look=True."""
from __future__ import annotations

import json
import math
import os
import shlex
import time
from pathlib import Path

import numpy as np

BODY_OFFSET = 0.002  # m: cloth_zozo's default body contact offset (job "body_offset")
CONTACT_GAP = 0.001  # m: cloth_zozo's default contact gap (job "contact_gap")


def woven_limit(cap: float | None = None, lock_deg: float | None = None) -> float:
    """The largest principal stretch a woven can take, as a strain: threads at their cap, bias sheared to the jam."""
    from . import pattern_form as pf
    cap = pf.FIT_THREAD_CAP if cap is None else cap
    lock = pf.SHEAR_LOCK_DEG if lock_deg is None else lock_deg
    return (1.0 + cap) * math.sqrt(1.0 + math.sin(math.radians(lock))) - 1.0


# THE SOLVER'S OWN LEGALITY TEST (zozo hang round 3, C249; coordinator: "stop approximating"). ZOZO assembles three
# cloth / collision-mesh pair kinds (crates/ppf-cts-solver/src/kernels/contact/collision_narrow.kernel.cpp): a cloth
# VERTEX against a collider TRIANGLE (point-triangle), a collider VERTEX against a cloth TRIANGLE (triangle-point), a cloth
# EDGE against a collider EDGE (edge-edge). Each pair's separation is the exact closest-point vector; its offset is the
# two elements' contact-offsets summed (cloth tri default 0, datamodel/params.rs; the body BODY_OFFSET, cloth_zozo
# "body_offset"); embed_collision refuses the run ("contact starts overlapping") when !(d^2 > offset^2), i.e. d <= offset.
# The barrier acts within offset + ghat (ghat = the mean of the two contact-gaps: CONTACT_GAP both sides). LEGAL = every
# pair d > BODY_OFFSET (the pre-flight's refusal). The fit's last contact pass holds every pair at REACH = offset + ghat
# (= CLEARANCE): ZOZO's own advice, "give the initial geometry a small clearance so nothing starts in contact".
REACH = BODY_OFFSET + CONTACT_GAP


def _pt_tri(P, A, B, C):
    """Closest points on triangles ABC to points P, row by row (Ericson, Real-Time Collision Detection 5.1.5): (Q, w)
    with Q = w0 A + w1 B + w2 C."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = P - B
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = P - C
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    n = len(P)
    w = np.zeros((n, 3))
    done = np.zeros(n, bool)

    def put(m, w0, w1, w2):
        m = m & ~done
        w[m, 0], w[m, 1], w[m, 2] = w0[m] if np.ndim(w0) else w0, w1[m] if np.ndim(w1) else w1, w2[m] if np.ndim(w2) else w2
        done[m] = True
    z, o = 0.0, 1.0
    put((d1 <= 0) & (d2 <= 0), o, z, z)
    put((d3 >= 0) & (d4 <= d3), z, o, z)
    put((d6 >= 0) & (d5 <= d6), z, z, o)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = d1 / (d1 - d3)
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), 1 - t, t, z)
        t = d2 / (d2 - d6)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), 1 - t, z, t)
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        put((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), z, 1 - t, t)
        den = va + vb + vc
        v_, w_ = vb / den, vc / den
        put(np.ones(n, bool), 1 - v_ - w_, v_, w_)
    Q = w[:, :1] * A + w[:, 1:2] * B + w[:, 2:] * C
    return Q, w


def _tri_radius(V, T):
    c = V[T].mean(1)
    return c, np.linalg.norm(V[T] - c[:, None], axis=2).max(1)


def _pairs_within(Pa, ra, Pb, rb, d):
    """Candidate pairs (i, j): ball i (centre Pa, radius ra) within d of ball j."""
    from scipy.spatial import cKDTree
    if not len(Pa) or not len(Pb):
        return np.zeros((0, 2), np.int64)
    L = cKDTree(Pb).query_ball_point(Pa, ra + float(rb.max()) + d)
    I = np.array([(i, k) for i, ks in enumerate(L) for k in ks], np.int64).reshape(-1, 2)
    if len(I):
        I = I[np.linalg.norm(Pa[I[:, 0]] - Pb[I[:, 1]], axis=1) < ra[I[:, 0]] + rb[I[:, 1]] + d]
    return I


def _edges(T):
    T = np.asarray(T, np.int64)
    return np.unique(np.sort(np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]], 1), axis=0)


def contact_pairs(X, F, bV, bT, dmin: float, chunk: int = 200000) -> dict:
    """Every cloth / collider pair ZOZO assembles (point-triangle, triangle-point, edge-edge) whose exact distance is
    under dmin. Returns {"kind": [n] str ("vf" | "fv" | "ee"), "cloth": [n, 3] cloth vertex ids (-1 unused), "w": [n, 3]
    their weights, "body": [n] the collider element (triangle | vertex | edge row), "sep": [n, 3] the separation (cloth
    minus collider), "d": [n] metres}."""
    X, bV = np.asarray(X, float), np.asarray(bV, float)
    F, bT = np.asarray(F, np.int64), np.asarray(bT, np.int64)
    out = {k: [] for k in ("kind", "cloth", "w", "body", "sep", "d")}

    def add(kind, cv, w, be, sep, d):
        m = d < dmin
        if m.any():
            out["kind"].append(np.full(int(m.sum()), kind))
            out["cloth"].append(cv[m]), out["w"].append(w[m]), out["body"].append(be[m])
            out["sep"].append(sep[m]), out["d"].append(d[m])
    # (a box round the cloth: collider elements outside it can't be within dmin)
    lo, hi = X.min(0) - dmin, X.max(0) + dmin
    bc, br = _tri_radius(bV, bT)
    keep = np.where(((bc + br[:, None] > lo) & (bc - br[:, None] < hi)).all(1))[0]
    # cloth vertex vs collider triangle
    I = _pairs_within(X, np.zeros(len(X)), bc[keep], br[keep], dmin)
    for s in range(0, len(I), chunk):
        J = I[s:s + chunk]
        t = bT[keep[J[:, 1]]]
        Q, _ = _pt_tri(X[J[:, 0]], bV[t[:, 0]], bV[t[:, 1]], bV[t[:, 2]])
        sep = X[J[:, 0]] - Q
        cv = np.c_[J[:, 0], -np.ones((len(J), 2), np.int64)]
        add("vf", cv, np.c_[np.ones(len(J)), np.zeros((len(J), 2))], keep[J[:, 1]], sep, np.linalg.norm(sep, axis=1))
    # collider vertex vs cloth triangle
    cc, cr = _tri_radius(X, F)
    vb = np.where(((bV > lo) & (bV < hi)).all(1))[0]
    I = _pairs_within(bV[vb], np.zeros(len(vb)), cc, cr, dmin)
    for s in range(0, len(I), chunk):
        J = I[s:s + chunk]
        t = F[J[:, 1]]
        Q, w = _pt_tri(bV[vb[J[:, 0]]], X[t[:, 0]], X[t[:, 1]], X[t[:, 2]])
        sep = Q - bV[vb[J[:, 0]]]
        add("fv", t, w, vb[J[:, 0]], sep, np.linalg.norm(sep, axis=1))
    # cloth edge vs collider edge
    from .cloth import _seg_seg
    E, bE = _edges(F), _edges(bT)
    me, he = X[E].mean(1), 0.5 * np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
    mb, hb = bV[bE].mean(1), 0.5 * np.linalg.norm(bV[bE[:, 0]] - bV[bE[:, 1]], axis=1)
    kb = np.where(((mb + hb[:, None] > lo) & (mb - hb[:, None] < hi)).all(1))[0]
    I = _pairs_within(me, he, mb[kb], hb[kb], dmin)
    for s in range(0, len(I), chunk):
        J = I[s:s + chunk]
        e, b = E[J[:, 0]], bE[kb[J[:, 1]]]
        p0, p1, q0, q1 = X[e[:, 0]], X[e[:, 1]], bV[b[:, 0]], bV[b[:, 1]]
        sa, tb, d = _seg_seg(p0, p1, q0, q1)
        sep = (p0 + sa[:, None] * (p1 - p0)) - (q0 + tb[:, None] * (q1 - q0))
        add("ee", np.c_[e, -np.ones(len(e), np.int64)], np.c_[1 - sa, sa, np.zeros(len(e))], kb[J[:, 1]], sep, d)
    if not out["d"]:
        return {"kind": np.zeros(0, str), "cloth": np.zeros((0, 3), np.int64), "w": np.zeros((0, 3)),
                "body": np.zeros(0, np.int64), "sep": np.zeros((0, 3)), "d": np.zeros(0)}
    return {k: np.concatenate(v) for k, v in out.items()}


def legality(X, F, bV, bT, offset: float = BODY_OFFSET) -> dict:
    """ZOZO's frame-0 test on this start: the pairs with d <= offset (illegal: the solver refuses the run) and the
    nearest pair. {"ok", "illegal", "min_mm", "by_kind", "worst": [(kind, cloth ids, body element, d mm, at xyz)]}."""
    P = contact_pairs(X, F, bV, bT, offset + 1e-9)
    bad = P["d"] <= offset
    Q = contact_pairs(X, F, bV, bT, REACH + 0.002)
    mn = float(Q["d"].min()) * 1000 if len(Q["d"]) else float("inf")
    o = np.argsort(P["d"])[:5]
    X = np.asarray(X, float)
    worst = [(str(P["kind"][i]), [int(c) for c in P["cloth"][i] if c >= 0], int(P["body"][i]),
              round(float(P["d"][i]) * 1000, 3), [round(float(x), 4) for x in X[P["cloth"][i][0]]]) for i in o]
    return {"ok": not bool(bad.any()), "illegal": int(bad.sum()), "min_mm": round(mn, 3),
            "in_reach": int((Q["d"] < REACH).sum()),
            "by_kind": {k: int(((P["kind"] == k) & bad).sum()) for k in ("vf", "fv", "ee")}, "worst": worst}


def start_strain(arrays: dict, jc: dict, top: int = 6) -> dict:
    """ZOZO's second frame-0 test (round 4, C252), mirrored: strainlimiting/strain_toi.kernel.cpp shell_strain_toi
    returns toi 0 for a face whose largest principal strain (shell_max_strain, vs its rest) is at or past its limit at
    the start and still past it after the full step ("ccd failed, strain limiting toi 0": the hoodie, round 3). The
    rest and the per-face limit are exactly what the runner hands the solver (cloth_zozo.flat_rest + face_limits: the
    made pieces' and declared bands' raised limits, the runner's lifted few). A face that starts past its own limit
    passes only if the first step happens to bring it back (the tee, round 3): the pre-flight refuses it.
    {"ok", "over", "faces", "by_piece": {piece: [n, worst strain %, its limit %]}, "worst": [(face, piece, %, lim %)]}"""
    from . import cloth_zozo as cz
    job = dict(jc)
    job.update(job.pop("zozo", None) or {})
    X, F = np.asarray(arrays["X"], float), np.asarray(arrays["F"], np.int64)
    if job.get("rest", "flat" if job.get("placement") == "smooth" else "placed") != "flat":
        return {"ok": True, "over": 0, "faces": len(F), "by_piece": {}, "worst": [], "note": "rest placed: start = rest"}
    fr = cz.flat_rest(job, arrays, X, F)
    fl = cz.face_limits(fr["lv"], fr["lim"], F)
    e = (fr["sig"] - 1.0).astype(np.float32)
    bad = e >= fl.astype(np.float32)
    fp = np.asarray(arrays["piece"])[F[:, 0]]
    by = {}
    for k, nm in enumerate(job["pieces"]):
        m = bad & (fp == k)
        if m.any():
            by[nm] = [int(m.sum()), round(float(e[m].max()) * 100, 1), round(float(fl[m].min()) * 100, 1)]
    w = np.where(bad)[0]
    w = w[np.argsort(-(e[w] - fl[w]))][:top]
    return {"ok": not bad.any(), "over": int(bad.sum()), "faces": len(F), "by_piece": by,
            "worst": [(int(f), job["pieces"][int(fp[f])], round(float(e[f]) * 100, 1), round(float(fl[f]) * 100, 1))
                      for f in w]}


CHAIN_GATE = "chain_gate.json"  # the chain job's own gate beside its job (structure PASS + step 7a), see run()
REMOTE_KEY = "HIFIPUSHIE_HANG_REMOTE"  # the machine's configured route (localconf), never an agent's choice


def write_chain_gate(jd: Path, structure: str, presim: str) -> dict:
    """The chain job's gate record beside its ZOZO job: its structure verdict (PASS / PASS_WAIVED) and why step 7a let it
    hang (chain_presim.presim_ready). Written by the chain_garment worker only after both passed; not in in.npz /
    job.json, so a result's cache key is the same wherever it ran."""
    rec = {"structure": structure, "presim": presim}
    Path(jd).mkdir(parents=True, exist_ok=True)
    (Path(jd) / CHAIN_GATE).write_text(json.dumps(rec))
    return rec


def chain_gate(jd: Path) -> tuple:
    """(gated, why): a remote route's gate for a chain job = its own structure PASS + step 7a (pre-sim approval), in
    place of cloth_job's pattern-gate record (the old cloth path's gate). No record: not gated for a remote route."""
    try:
        rec = json.loads((Path(jd) / CHAIN_GATE).read_text())
    except (OSError, ValueError):
        return False, "no chain gate record (structure PASS + step 7a) beside the job"
    if str(rec.get("structure", "")).split("_")[0] != "PASS":
        return False, f"structure {rec.get('structure')!r}, not PASS"
    if not rec.get("presim"):
        return False, "step 7a not passed"
    return True, f"structure {rec['structure']}, {rec['presim']}"


def remote_route() -> str | None:
    """The configured remote route's command (a path relative to this checkout is resolved in it), else None."""
    from . import localconf
    cmd = localconf.get(REMOTE_KEY)
    if not cmd:
        return None
    parts = shlex.split(cmd)
    if not Path(parts[0]).is_absolute():
        root = Path(__file__).resolve().parents[2]
        if (root / parts[0]).exists():
            parts[0] = str(root / parts[0])
    return shlex.join(parts)


def run(jd: Path, log=print, timeout: float = 3600) -> tuple:
    """The written job: through the machine's configured remote route ($HIFIPUSHIE_HANG_REMOTE, environment or
    localconf; a command run with the job folder as its last argument that leaves out.npz there) when one is set and the
    job carries its chain gate (chain_gate); else on this machine under the heavy slot + GPU (resources.heavy gpu=True)
    and ZOZO's memory cap ($HIFIPUSHIE_ZOZO_MEM). A remote run holds no local slot (the laptop's GPU stays free for
    renders). A route that answers exit 9 (not available) falls back here, said in one line. out.npz lands in the same
    job folder either way: results are found whichever machine ran them. Returns (out.npz arrays, log lines)."""
    from . import cloth_job as cj, localconf, resources
    lines = []
    def say(m):
        lines.append(m)
        log(m)
    remote = remote_route()
    if remote:
        gated, why = chain_gate(jd)
        if not gated:
            say(f"zozo hang: ran locally ({why})")
        else:
            if cj._paid(remote) and not cj.may_submit():
                raise cj.SimNotSubmitted(f"zozo hang {jd}: the configured route is paid; no opt-in at the call site "
                                         "(cloth_job.submitting() or HP_SUBMIT_SIMS=1). The job folder is written.")
            try:
                cj._stream(shlex.split(remote) + [str(jd)], lambda m: None, timeout, localconf.environ(),
                           "zozo hang (remote)")
                say(f"zozo hang: ran remotely (gate: {why})")
                arr, ol = cj.read_out(jd / "out.npz")
                return arr, list(ol) + lines
            except RuntimeError as e:
                if "(exit 9)" not in str(e):
                    raise
                say("zozo hang: the remote route is not available: ran locally")
    cmd, env = cj.zozo_command(jd)
    with resources.heavy(f"zozo hang {jd.name}", log=log, kind="cloth_zozo", gpu=True, model=jd.name):
        cj.clear_strays(log)
        cj._stream(cmd, lambda m: None, timeout, env, "zozo hang settle")
    if not remote:
        say("zozo hang: ran locally")
    arr, ol = cj.read_out(jd / "out.npz")
    return arr, list(ol) + lines

