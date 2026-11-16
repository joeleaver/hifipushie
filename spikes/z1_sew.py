"""Z1 (experiment): can ZOZO SEW the jacket's flat pieces onto the body (seams closed, lengths kept, nothing through the
body) so step 5's chains can be read off its result? Mesh = D3's chain network itself (cnet: every chain point is a
vertex, the pieces Delaunay-filled between the 30 mm lines; the coarse grid), start = D2's outside start (D3's
run/X_start.npy). The seams are ZOZO stitches (cloth_zozo: vertex to vertex from t = 0), gravity 0 while sewing, then
on for a short settle; strain limit = the hang's woven limit (zozo_hang.woven_limit); the body the collider; membrane
and bending rest on the flat pattern. canvas.L / .R (unsewn plies) are left out of the sim and the reads.
Folds (opt folds): ZOZO's bending rest "bend_rest" = the flat pattern with each planned fold's rows turned by the
plan's angle (each row fitted by a straight line, the far side rotated about it: approximate for curved rows) and
"fold" pressing those rows.

  HIFIPUSHIE_HOME=<ws> capped uv run python spikes/z1_sew.py write <jd> <loaded.pkl> <run dir> [folds] [sew=N settle=N]
  uv run python spikes/z1_sew.py run <jd>            (the machine's configured route, else here under heavy + GPU)
  HIFIPUSHIE_HOME=<ws> capped uv run python spikes/z1_sew.py read <jd> <loaded.pkl> <run dir>
read writes <jd>/read.json and <jd>/X.npy (per cnet vertex; canvas at its start)."""
import json
import os
import pickle
import shlex
import sys
import time
from pathlib import Path

import numpy as np

KINDS = {0: "edge", 1: "fold row", 2: "line along", 3: "line across"}
DROP = ("canvas.L", "canvas.R")
log = lambda m: print(m, flush=True)


def load(src, run):
    d = pickle.load(open(src, "rb"))
    g = pickle.load(open(os.path.join(run, "cnet.pkl"), "rb"))
    return d, g, np.nan_to_num(np.load(os.path.join(run, "X_start.npy")))


def kept(c):
    keep = ~np.isin(c.piece, [c.names.index(p) for p in DROP])
    idx = np.where(keep)[0]
    new = -np.ones(c.n, np.int64)
    new[idx] = np.arange(len(idx))
    return keep, idx, new


def folds_and_pulls(c, d, g, X0):
    from hifipushie import chain_lay, chain_settle, panel_start
    body, plan = d["body"], d["wear"]
    OUT = chain_lay.outside(c, X0, body.contact, [p for p in c.names if p not in DROP])
    folds = chain_lay.fold_rows(c, plan, OUT)
    other = {c.names[c.piece[x]] for a, b in c.sew if c.piece[a] != c.piece[b] for x in (a, b)}
    skip = [p for p in c.names if p not in other]
    _, epulls, _ = panel_start.starts(c, g["keep"], body, skip, spin={p: 0.0 for p in c.names})
    return folds, chain_settle.girth_pulls(c, X0) + epulls


def bend_rest(c, folds, keep):
    """The flat pattern with each fold row turned by its target (straight-line fit per row, far side rotated)."""
    R = np.c_[c.uv, np.zeros(c.n)]
    press = np.zeros(c.n)
    for f in folds:
        row = np.asarray(f["row"], np.int64)
        p = c.piece[row[0]]
        v = np.where(c.piece == p)[0]
        P = c.uv[row]
        m = P.mean(0)
        u = np.linalg.svd(P - m)[2][0]
        nrm = np.array([-u[1], u[0]])
        s = (c.uv[v] - m) @ nrm
        far = v[s > 0] if (s > 0).sum() <= (s < 0).sum() else v[s < 0]  # (the smaller side turns)
        th = np.radians(f["turn_deg"]) * float(f.get("toward", 1.0) if np.isscalar(f.get("toward", 1.0)) else 1.0)
        a3 = np.r_[m, 0.0]
        k = np.r_[u, 0.0]
        Y = R[far] - a3
        Y = Y * np.cos(th) + np.cross(k, Y) * np.sin(th) + np.outer(Y @ k, k) * (1 - np.cos(th))
        R[far] = Y + a3
        press[row] = 1.0
    return R[keep], press[keep]


SLIVER_MM2 = 0.5  # flat triangles under this area (Delaunay slivers on outlines) are left out of the sim mesh
CLEAR = 0.006  # m: every start point at least this far outside the body (ZOZO's offset 2 mm + contact gap + chord sag)


def fair_start(c, X, F, uv, pid, names, body, lim):
    """D2's start made one ZOZO can begin from: a piece whose start faces stretch past the limit (D2's start keeps its
    CHAINS exact, not the faces between them) is replaced by its flat pattern placed rigidly (Kabsch) on its D2 start,
    then moved straight out from the body until clear; every point then pushed out to CLEAR along the body's normal."""
    from hifipushie import cloth_zozo as cz
    X = X.copy()
    sig = cz._start_stretch(np.c_[uv, np.zeros(len(uv))], X, F)
    flat = []
    for p, nm in enumerate(names):
        if (sig[pid[F[:, 0]] == p] > 1 + lim).any():
            v = np.where(pid == p)[0]
            A = np.c_[uv[v], np.zeros(len(v))]
            a0, b0 = A.mean(0), X[v].mean(0)
            U, _, Vt = np.linalg.svd((A - a0).T @ (X[v] - b0))
            R = U @ np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))]) @ Vt
            Y = (A - a0) @ R + b0
            sd, nrm = body.contact.query(Y)[:2]
            dirn = nrm[np.argsort(sd)[: max(3, len(v) // 10)]].mean(0)
            dirn /= max(np.linalg.norm(dirn), 1e-9)
            k = 0
            while body.contact.query(Y)[0].min() < CLEAR and k < 100:
                Y += dirn * 0.01
                k += 1
            X[v] = Y
            flat.append((nm, int((sig[pid[F[:, 0]] == p] > 1 + lim).sum()), k * 10))
    for _ in range(4):
        sd, nrm = body.contact.query(X)[:2]
        m = sd < CLEAR
        X[m] += nrm[m] * (CLEAR - sd[m])[:, None]
    return X, flat


def write(jd, src, run, opt):
    from hifipushie import cloth, cloth_job as cj, store, zozo_hang as zh
    d, g, X0 = load(src, run)
    c = g["cnet"]
    keep, idx, new = kept(c)
    F = new[c.F]
    F = F[(F >= 0).all(1)]
    uv = c.uv[idx]
    e1, e2 = uv[F[:, 1]] - uv[F[:, 0]], uv[F[:, 2]] - uv[F[:, 0]]
    area = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
    slivers = int((area < SLIVER_MM2 * 1e-6).sum())
    F = F[area >= SLIVER_MM2 * 1e-6]
    used = np.zeros(len(idx), bool)
    used[F] = True  # (a vertex in no triangle has no mass: ZOZO's frame 0 fails, NaN blocks; left out, set at read)
    sub = np.where(used)[0]
    re = -np.ones(len(idx), np.int64)
    re[sub] = np.arange(len(sub))
    F, idx, uv = re[F], idx[sub], uv[sub]
    new = -np.ones(c.n, np.int64)
    new[idx] = np.arange(len(idx))
    keep = np.zeros(c.n, bool)
    keep[idx] = True
    log(f"vertices in no triangle left out: {int((~used).sum())}")
    sew = new[c.sew]
    sew = sew[(sew >= 0).all(1) & (sew[:, 0] != sew[:, 1])]
    names = [p for p in c.names if p not in DROP]
    pid = np.array([names.index(c.names[p]) for p in c.piece[idx]], np.int64)
    bV, bT = np.asarray(d["body"].V, float), np.asarray(d["body"].T, np.int64)
    spec = store.load("garrett")
    fabric = cloth.fabric(json.loads(json.dumps(spec["cloth"]["jacket"])))
    lim = zh.woven_limit()
    X, flat = fair_start(c, X0[idx], F, uv, pid, names, d["body"], lim)
    log(f"slivers dropped {slivers}; pieces placed flat (piece, faces past the limit in D2's start, mm moved out): {flat}")
    arrays = dict(X=X, uv=uv, F=F, sew=sew, stitch=np.zeros((0, 2), np.int64),
                  stiff=np.clip(np.asarray(c.stiff, float)[idx], 0, 1), piece=pid, pins=np.zeros(0, np.int64),
                  bodyV=bV, bodyT=bT)
    if "folds" in opt:
        folds, _ = folds_and_pulls(c, d, g, X0)
        arrays["bend_rest"], arrays["fold"] = bend_rest(c, folds, keep)
    cfg = {"fabric": fabric, "name": "z1_sew", "placement": "smooth", "wraps": {}, "made": [], "strain_limit": lim}
    jc = cj.job_config(cfg, names)
    base = {"sew": True, "self_collision": True, "fixed": [], "body": True}
    jc["stages"] = [dict(base, name="sew", frames=int(opt.get("sew", 96)), gravity=0),
                    dict(base, name="settle", frames=int(opt.get("settle", 24)), gravity=1)]
    jc["snap"] = 24
    jd = Path(jd)
    jd.mkdir(parents=True, exist_ok=True)
    np.savez(jd / "in.npz", **arrays)
    np.save(jd / "idx.npy", idx)
    (jd / "job.json").write_text(json.dumps(jc, indent=1, default=cj._jsonable))
    lg = zh.legality(X, F, bV, bT)
    ss = zh.start_strain(arrays, jc)
    gap = np.linalg.norm(X[sew[:, 0]] - X[sew[:, 1]], axis=1) * 1e3
    el = np.linalg.norm(arrays["uv"][F[:, 0]] - arrays["uv"][F[:, 1]], axis=1) * 1e3
    pre = {"verts": len(X), "tris": len(F), "stitches": len(sew), "strain_limit": lim, "legal": lg["ok"],
           "legal_min_mm": lg.get("min_mm"), "start_strain_ok": ss["ok"], "start_over": ss.get("over"),
           "seam_gap_mm": [round(float(gap.mean()), 1), round(float(gap.max()), 1)],
           "edge_mm_p50_max": [round(float(np.median(el)), 1), round(float(el.max()), 1)], "folds": "folds" in opt,
           "slivers_dropped": slivers, "placed_flat": flat, "start_worst": str(ss.get("worst"))[:300],
           "illegal": lg.get("illegal"), "illegal_by_kind": lg.get("by_kind")}
    Xs = X0.copy()
    Xs[idx] = X
    np.save(jd / "X_start.npy", Xs)
    (jd / "pre.json").write_text(json.dumps(pre, indent=1, default=str))
    log(f"written {jd}: {pre}")


def run(jd):
    from hifipushie import cloth_job as cj, localconf, resources, zozo_hang as zh
    jd = Path(jd).resolve()
    t0 = time.time()
    where = "here"
    remote = zh.remote_route()  # (the machine's configured route; this spike is not the product hang, so no chain gate)
    done = False
    if remote:
        try:
            cj._stream(shlex.split(remote) + [str(jd)], log, 3600, localconf.environ(), "z1 sew (remote)")
            where, done = f"remote ({remote.split()[-1]}, LAN_HOST {localconf.get('LAN_HOST')})", True
        except RuntimeError as e:
            if "(exit 9)" not in str(e):
                raise
            log("remote route not available: running here")
    if not done:
        cmd, env = cj.zozo_command(jd)
        with resources.heavy(f"z1 sew {jd.name}", log=log, kind="cloth_zozo", gpu=True, model=jd.name):
            cj._stream(cmd, log, 3600, env, "z1 sew")
    (jd / "ran.json").write_text(json.dumps({"where": where, "wall_s": round(time.time() - t0, 1)}))
    log(f"ran {where} in {time.time() - t0:.0f} s")


def links(c, X, keep_piece):
    cur = np.linalg.norm(X[c.link_j] - X[c.link_i], axis=1)
    s = (cur / np.maximum(c.link_L, 1e-12) - 1) * 100
    kind, piece = np.zeros(len(s), int), np.zeros(len(s), int)
    kind[c.link_of_chain], piece[c.link_of_chain] = c.chain_kind, c.chain_piece
    m = keep_piece[piece]
    over = (np.abs(s) > 2) & m
    by_p, by_k = {}, {}
    for x in np.where(over)[0]:
        by_p[c.names[piece[x]]] = by_p.get(c.names[piece[x]], 0) + 1
        by_k[KINDS[kind[x]]] = by_k.get(KINDS[kind[x]], 0) + 1
    return {"links": int(m.sum()), "over_2pct": int(over.sum()), "stretched": int(((s > 2) & m).sum()),
            "short": int(((s < -2) & m).sum()), "worst_pct": round(float(np.abs(s[m]).max()), 2),
            "median_pct": round(float(np.median(np.abs(s[m]))), 3),
            "by_piece": dict(sorted(by_p.items(), key=lambda t: -t[1])),
            "by_kind": dict(sorted(by_k.items(), key=lambda t: -t[1]))}


def read(jd, src, run_):
    from hifipushie import chain_solve as cs, chain_solve_terms as terms, cloth_job as cj
    from hifipushie.chain_core import GAP
    d, g, X0 = load(src, run_)
    c, body = g["cnet"], d["body"]
    keep, _, _ = kept(c)
    jd = Path(jd)
    idx = np.load(jd / "idx.npy")
    arr, _ = cj.read_out(jd / "out.npz")
    V = np.asarray(arr["V"], float)
    X = X0.copy()
    X[idx] = V
    insim = np.zeros(c.n, bool)
    insim[idx] = True
    for v in np.where(keep & ~insim)[0]:  # (left out of the sim: carried by an affine fit of its 6 nearest in the flat)
        w = idx[c.piece[idx] == c.piece[v]]
        w = w[np.argsort(np.linalg.norm(c.uv[w] - c.uv[v], axis=1))[:6]]
        A = np.c_[c.uv[w], np.ones(len(w))]
        X[v] = np.r_[c.uv[v], 1.0] @ np.linalg.lstsq(A, X[w], rcond=None)[0]
    idx = np.where(keep)[0]
    np.save(jd / "X.npy", X)
    kp = np.array([p not in DROP for p in c.names])
    # each vertex on its own (a seam's two sides are not merged: link reads at the root vertex, seam gap apart)
    sew = c.sew[keep[c.sew].all(1)]
    gap = np.linalg.norm(X[sew[:, 0]] - X[sew[:, 1]], axis=1) * 1e3
    sd = body.contact.query(X[idx])[0]
    folds, pulls = folds_and_pulls(c, d, g, X0)
    pulls = [p for p in pulls if kp[c.piece[p["ids"][0]]]]
    t = cs._blocks(c, X, [], folds, pulls, None, body.contact)
    rep = terms.report(c, X, t, (body.contact, GAP), 2.0)
    by_in = {}
    for p in np.unique(c.piece[idx][sd < 0]):
        by_in[c.names[p]] = int(((c.piece[idx] == p) & (sd < 0)).sum())
    out = {"ran": json.loads((jd / "ran.json").read_text()) if (jd / "ran.json").exists() else None,
           "links": links(c, X, kp), "links_merged_roots": rep.get("links", {}).get("over_tol"),
           "seam_gap_mm": {"mean": round(float(gap.mean()), 2), "p95": round(float(np.percentile(gap, 95)), 2),
                           "max": round(float(gap.max()), 2), "over_5mm": int((gap > 5).sum()), "n": len(gap)},
           "inside": {"n": int((sd < 0).sum()), "deepest_mm": round(float(-sd.min()) * 1e3, 1), "by_piece": by_in},
           "folds": rep["folds"], "tapes": rep["pulls"]}
    (jd / "read.json").write_text(json.dumps(out, indent=1, default=str))
    log(json.dumps({k: out[k] for k in ("ran", "links", "seam_gap_mm", "inside")}, default=str))


if __name__ == "__main__":
    cmd = sys.argv[1]
    opt = dict(a.split("=", 1) if "=" in a else (a, "1") for a in sys.argv[3:] if not a.startswith("/"))
    if cmd == "write":
        write(sys.argv[2], sys.argv[3], sys.argv[4], dict(a.split("=", 1) if "=" in a else (a, "1") for a in sys.argv[5:]))
    elif cmd == "run":
        run(sys.argv[2])
    elif cmd == "read":
        read(sys.argv[2], sys.argv[3], sys.argv[4])
