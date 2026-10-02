"""Run a hifipushie cloth job (src/hifipushie/cloth_job.py) with ZOZO's contact solver (ppf-contact-solver, Apache-2.0:
intersection-free IPC-style contact, strain limiting, stitches). Runs on CUDA, ROCm (this laptop's Radeon 890M, from the
release's own bundled HIP runtime) or CPU.

    <ppf>/python/bin/python3.12 run_zozo.py <job folder> [--set key=json ...] [--frames N]
    (env: CARGO_TARGET_DIR=<ppf>/target/rocm|cuda|cpu, PYTHONPATH=<ppf>; spikes/gpu_cloth/zozo.sh sets them)

Mapping (one session for the whole schedule, times at the job's 24 fps):
- the garment is one shell whose REST is the start placement X (isometric to the pattern, like Blender's), bending
  rest from that geometry (`bend-rest-from-geometry`: a turned collar keeps its fold);
- seams and stitches: ZOZO stitches (vertex to vertex) from t = 0;
- gravity 0 while sewing (the "assemble" + "sew" stages), then on;
- assemble.fixed vertices pinned until the bodice is sewn, assemble.hold (cuffs) until the sewing ends;
- the body a static collider (contact offset `body_offset`); hung garments: the body moves away down after the worn
  settle while the hanger-loop vertices (pinned from the start) move up under the hook. No rack (yet);
- material: young-mod = stretch / density (ZOZO's is normalised by density), `bend` (dimensionless, ZOZO's scale),
  strain limit (`strain_limit`, default 5%), friction.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print("cloth:", s, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--frames", type=int, default=None, help="stop early (debugging)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    jd = Path(a.job)
    job = json.loads((jd / "job.json").read_text())
    for kv in a.set:
        k, v = kv.split("=", 1)
        job[k] = json.loads(v)
    d = np.load(jd / "in.npz")
    from frontend import App
    P = job["fabric"]["physical"]
    fps = float(job.get("fps", 24))
    X = np.asarray(d["S"] if job.get("mode") == "refine" else d["X"], float)
    F = np.asarray(d["F"], np.int64)
    n = len(X)
    sew = np.r_[d["sew"], d["stitch"]] if len(d["stitch"]) else np.asarray(d["sew"])
    # a stitch whose ends already coincide has no direction (ZOZO: NaN force): those vertices are sewn already
    sew = sew[np.linalg.norm(X[sew[:, 0]] - X[sew[:, 1]], axis=1) > 1e-6]
    stages = job["stages"]
    t = 0.0
    times = {}
    for s in stages:
        times[s["name"]] = (t, t + s["frames"] / fps)
        t += s["frames"] / fps
    total = int(round(t * fps))
    if a.frames:
        total = min(total, a.frames)
    name = f"hp_{jd.parent.name}_{jd.name}"[:60]
    app = App.create(name)
    app.asset.add.tri("garment", X.astype(np.float64), F)
    Ind = np.c_[sew[:, 0], sew[:, 1], sew[:, 1], sew[:, 1]].astype(np.int64)
    W = np.tile([1.0, 1.0, 0.0, 0.0], (len(sew), 1))
    app.asset.add.stitch("seams", (Ind, W))
    has_body = any(s.get("body", True) for s in stages) and not job.get("no_body")
    if has_body:
        app.asset.add.tri("body", np.asarray(d["bodyV"], float), np.asarray(d["bodyT"], np.int64))
    scene = app.scene.create()
    g = scene.add("garment")
    if not job.get("no_stitch"):
        g.stitch("seams")
    dens = float(P["density"])
    g.param.set("density", dens).set("young-mod", float(job.get("young_mod", P["stretch"] / dens)))
    g.param.set("poiss-rat", float(job.get("poisson", 0.3))).set("bend", float(job.get("bend", 1.0)))
    g.param.set("strain-limit", float(job.get("strain_limit", 0.05))).set("friction", float(P.get("friction", 0.4)))
    g.param.set("contact-gap", float(job.get("contact_gap", 1e-3)))
    g.param.set("bend-rest-from-geometry", float(job.get("bend_rest_geom", 1.0)))
    g.param.set("allow-existing-intersection", 1.0)  # the placement's own few overlaps (sleeve fins) aren't fatal
    if job.get("stitch_stiffness"):
        g.param.set("stitch-stiffness", float(job["stitch_stiffness"]))
    stiff = np.asarray(d["stiff"], float)
    if stiff.max() > 0 and job.get("interfacing", True):  # interfacing: bending and stretch up towards their interfaced values
        g.set_param_spatial("bend", stiff, float(job.get("bend", 1.0)) * float(P.get("interfacing_bend", 10)))
    asm = job.get("assemble") or {}
    sew_end = 0.0
    for s in stages:
        if s.get("gravity", 1) == 0:
            sew_end = max(sew_end, times[s["name"]][1])
    if asm.get("fixed") and "assemble" in times:
        g.pin(list(map(int, asm["fixed"])), allow_intersection=bool(job.get("pin_pass", True))).unpin(times["assemble"][1])
    if asm.get("hold") and "sew" in times:
        held = sorted(set(map(int, asm["hold"])) - set(map(int, asm.get("fixed", []))))
        if held:
            g.pin(held, allow_intersection=bool(job.get("pin_pass", True))).unpin(times["sew"][1])
    hang = next((s for s in stages if s.get("hang")), None)
    pins = np.asarray(job.get("pins") or [], np.int64)
    if hang is not None and len(pins):
        t0, t1 = times[hang["name"]]
        hook = np.asarray(job["hook"], float)
        target = hook - [0, 0, 0.01] + (X[pins] - X[pins].mean(0)) * float(job.get("pin_spread", 0.3))
        # pinned where they start (a small patch at the back neck, harmless while dressing), then lifted to the hook
        g.pin(list(map(int, pins))).move_to(target, t0, t0 + 0.4 * (t1 - t0))
    if has_body:
        b = scene.add("body")
        b.param.set("contact-offset", float(job.get("body_offset", 0.002))).set("friction", float(P.get("friction", 0.4)))
        bp = b.pin()
        if hang is not None:  # the body leaves downward while the coat is lifted to its hook
            t0, t1 = times[hang["name"]]
            bp.move_by([0.0, 0.0, -3.0], t0, t0 + 0.4 * (t1 - t0))
    scene = scene.build()
    sess = app.session.create(scene)
    prm = sess.param
    prm.set("fps", fps).set("frames", total).set("dt", float(job.get("dt", 0.01)))
    prm.set("gravity", [0.0, 0.0, 0.0] if sew_end > 0 else [0.0, 0.0, -9.8])
    if sew_end > 0:
        prm.dyn("gravity").time(sew_end).hold().change([0.0, 0.0, -9.8])
    if job.get("air_friction") is not None:
        prm.set("air-friction", float(job["air_friction"]))
    sess = sess.build()
    log(f"zozo: {n} verts, {len(F)} tris, {len(sew)} stitches, {total} frames at {fps:.0f} fps, sewing until "
        f"{sew_end:.2f} s, mode {job.get('mode', 'sim')}")
    tt = time.time()
    sess.start(blocking=True)
    wall = time.time() - tt
    got = sess.get.vertex()
    if got is None:
        raise RuntimeError("no vertices written:\n" + "\n".join(sess.get.log.stdout(n_lines=30)))
    Vall, frame = got
    # ZOZO writes the vertices reordered (its own layout): frame 0 is the start, so each output row is the start
    # vertex it sits on
    first = sess.get.vertex(0)
    if first is None:
        raise RuntimeError("no frame 0 to map ZOZO's vertex order back")
    from scipy.spatial import cKDTree
    dd, ii = cKDTree(X).query(np.asarray(first[0], float)[:n])
    if dd.max() > 1e-5 or len(np.unique(ii)) != n:
        raise RuntimeError(f"frame 0 isn't a permutation of the start ({dd.max() * 1000:.3f} mm off)")
    V = np.empty((n, 3))
    V[ii] = np.asarray(Vall[:n], float)
    try:
        ms = sess.get.log.numbers("time-per-frame")
        per = sum(v for _, v in ms) / max(1, len(ms))
    except Exception:
        per = float("nan")
    gap = np.linalg.norm(V[sew[:, 0]] - V[sew[:, 1]], axis=1)
    log(f"zozo: {frame} frames in {wall:.1f} s ({per:.0f} ms/frame), seam gaps mean {gap.mean() * 1000:.1f} mm p95 "
        f"{np.percentile(gap, 95) * 1000:.1f} mm, z {V[:, 2].min():.3f}..{V[:, 2].max():.3f}")
    out = Path(a.out) if a.out else jd / "out.npz"
    np.savez(out, V=V, log=np.array(LOG), timing=np.array(json.dumps({"total_s": wall, "ms_per_frame": per})))
    print("cloth: wrote", out, flush=True)


if __name__ == "__main__":
    main()
