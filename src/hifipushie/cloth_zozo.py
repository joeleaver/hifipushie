"""The ZOZO cloth backend's runner: a hifipushie cloth job (cloth_job.py) run with ZOZO's contact solver
(ppf-contact-solver, Apache-2.0: intersection-free IPC-style contact, strain limiting, stitches). Runs on CUDA, ROCm
(the laptop's Radeon 890M, from the release's own bundled HIP runtime) or CPU.

This file runs inside the ZOZO release's own Python (it never imports hifipushie): garment key `backend: "zozo"` runs
it through `cloth_job.run_zozo` (locally under resources.heavy, or on a GPU box through $HIFIPUSHIE_ZOZO_REMOTE, which
copies this file with the job). By hand:

    <ppf>/python/bin/python3.12 cloth_zozo.py <job folder> [--set key=json ...] [--frames N]
    (env: CARGO_TARGET_DIR=<ppf>/target/rocm|cuda|cpu, PYTHONPATH=<ppf>; spikes/gpu_cloth/zozo.sh sets them)

Options: job.json's top-level keys, then its "zozo" dict (the garment's `zozo` key: contact_gap, strain_limit, dt,
bend, young_mod, body_offset, hanger_offset, air_friction, ...), then --set.

Mapping (one session for the whole schedule, times at the job's 24 fps):
- placement "smooth" jobs (cloth.place(smooth=True), the way to run ZOZO): the garment's membrane REST is the flat
  pattern, written into the built scene (the frontend has no call for a static rest apart from the start); the made
  pieces (`job["made"]`, wholly interfaced: collar, stand, cuffs) rest as placed in stretch and bending; bending rest
  flat elsewhere (`set_bend_rest_vert`). The start is the placement on a body with straight arms (bodyV0); the arms
  bend back through bodyPoses in the "pose" stage (only the arms are a solved, prescribed object: a moving body is
  2.5x a static collider's cost). Nothing may start intersecting: no pass-through allowances, no pins on the pieces
  (ZOZO sets a pin's pass-through once at build and keeps it after the unpin: pinned sleeves passed through the
  body for the whole sim; and two prescribed things in contact, a held cuff on the wrist, can't be parted).
- other jobs: the REST is the start placement X (isometric to the pattern, like Blender's), bending rest from that
  geometry, the placement's overlaps (sleeve fins) allowed, assemble.fixed / assemble.hold pinned as in Blender;
- seams and stitches: ZOZO stitches (vertex to vertex) from t = 0; gravity 0 while sewing, then on;
- hung on a hanger (job "hanger", stage "hanger"): the hanger and rail meshes (in.npz hangerV/F, railV/F) are static
  colliders from the start, inside the body while the garment is dressed; the body stops colliding at the hang
  (collision window + a still move) and the garment settles onto the hanger by contact. No pins;
- the old pinned hang: the hanger-loop vertices (pinned from the start) move up under the hook, the rack's arms rise
  with them;
- material: young-mod = stretch / density (ZOZO's is normalised by density), `bend` (dimensionless, ZOZO's scale),
  strain limit (`strain_limit`, default 5%), friction.
- a scene check that fails names each violation's pieces (`--set debug_violations=true`: the raw record).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

import numpy as np

LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print("cloth:", s, flush=True)


MIN_FREE_GB = 20.0  # refuse to start with less free disk than this where the session writes
STOP_FREE_GB = 10.0  # stop a running session when free disk falls under this
KEEP_LAST = 8  # vert_N.bin frames kept at the end (the result and Vprev)


def _free_gb(path) -> float:
    return shutil.disk_usage(path).free / 2**30


class _Pruner(threading.Thread):
    """While a session runs: deletes its vert_N.bin frames but frame 0 (the row map), every `snap`-th and the last
    KEEP_LAST (a 1 cm coat writes ~2 MB a frame, every frame), and stops the run when free disk falls under
    STOP_FREE_GB."""

    def __init__(self, out_dir: Path, snap: int, total: int = 0):
        super().__init__(daemon=True)
        self.out_dir, self.snap, self.stop_flag, self.low = out_dir, snap, threading.Event(), None
        self.total, self.last, self.t0, self.said = total, 0, time.time(), 0.0

    def prune(self):
        frames = []
        for f in self.out_dir.glob("vert_*.bin") if self.out_dir.exists() else ():
            m = re.match(r"vert_(\d+)\.bin$", f.name)
            if m:
                frames.append((int(m.group(1)), f))
        if not frames:
            return
        last = max(k for k, _ in frames)
        self.last = last
        for k, f in frames:
            if k == 0 or k > last - KEEP_LAST or (self.snap and k % self.snap == 0):
                continue
            f.unlink(missing_ok=True)

    def run(self):
        while not self.stop_flag.wait(5.0):
            self.prune()
            if self.total and time.time() - self.said > 60 and self.last:  # progress for dress/status
                self.said = time.time()
                el = self.said - self.t0
                log(f"progress: frame {self.last}/{self.total}, {el:.0f} s, ~{el / self.last * (self.total - self.last):.0f} s left")
            free = _free_gb(self.out_dir if self.out_dir.exists() else self.out_dir.parent.parent)
            if free < STOP_FREE_GB:
                self.low = free
                log(f"disk: {free:.1f} GB free (< {STOP_FREE_GB}): stopping the session")
                from frontend import App
                App.terminate()
                return


def _shrunk(V: np.ndarray, T: np.ndarray, iters: int) -> np.ndarray:
    """A mesh pulled toward its own skeleton: umbrella smoothing (Laplacian, step 1) `iters` times, so limbs and the
    torso thin toward their axes."""
    n = len(V)
    E = np.r_[T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]
    E = np.r_[E, E[:, ::-1]]
    deg = np.bincount(E[:, 0], minlength=n).astype(float)
    S = V.copy()
    for _ in range(iters):
        acc = np.zeros_like(S)
        np.add.at(acc, E[:, 0], S[E[:, 1]])
        S = np.where(deg[:, None] > 0, acc / np.maximum(deg, 1)[:, None], S)
    return S


def _start_stretch(R: np.ndarray, X: np.ndarray, F: np.ndarray) -> np.ndarray:
    """The largest principal stretch of each triangle from rest R (3D, any orientation) to X."""
    e1, e2 = R[F[:, 1]] - R[F[:, 0]], R[F[:, 2]] - R[F[:, 0]]
    u = e1 / np.maximum(np.linalg.norm(e1, axis=1, keepdims=True), 1e-12)
    w = e2 - (e2 * u).sum(1, keepdims=True) * u
    v = w / np.maximum(np.linalg.norm(w, axis=1, keepdims=True), 1e-12)
    Dm = np.zeros((len(F), 2, 2))
    Dm[:, 0, 0] = (e1 * u).sum(1)
    Dm[:, 0, 1] = (e2 * u).sum(1)
    Dm[:, 1, 1] = (e2 * v).sum(1)
    Ds = np.stack([X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]]], -1)
    det = Dm[:, 0, 0] * Dm[:, 1, 1]
    ok = np.abs(det) > 1e-14
    inv = np.zeros_like(Dm)
    inv[ok, 0, 0] = 1 / Dm[ok, 0, 0]
    inv[ok, 0, 1] = -Dm[ok, 0, 1] / det[ok]
    inv[ok, 1, 1] = 1 / Dm[ok, 1, 1]
    return np.linalg.svd(Ds @ inv, compute_uv=False)[:, 0]


BEND_SCALE = 1.28e-5  # ZOZO's shell_bend_stiffness.kernel.cpp: hinge k = BEND_SCALE * bend * |e|^2 / area * areal density


def part_stitches(X: np.ndarray, F: np.ndarray, sew: np.ndarray, held: np.ndarray | None = None, gap: float = 0.002,
                  near: float = 5e-4) -> tuple[np.ndarray, np.ndarray, dict]:
    """Stitches whose two ends start together (closer than `near`) give ZOZO no direction: the force is NaN, and
    dropped (as the runner did) nothing sews the seam at all (a jacket's centre back seam, two panels drafted edge to
    edge, stood open). A general rule instead of per-garment starts: each such end steps `gap` / 2 back into its own
    cloth (toward the mean of its triangle neighbours), so the ends start `gap` apart and the stitch draws them
    together; two layers lying on each other (both step the same way) part along the surface normal instead. `held`
    vertices (pinned, or resting as placed) stay; a stitch between two held ends that coincide is dropped (the pins
    hold it), as is a stitch from a vertex to itself. Returns (X moved, stitches kept, counts)."""
    X = np.array(X, float)
    sew = np.asarray(sew, np.int64).reshape(-1, 2)
    info = {"coincident": 0, "moved": 0, "by_normal": 0, "dropped": 0}
    if not len(sew):
        return X, sew, info
    held = np.zeros(len(X), bool) if held is None else np.asarray(held, bool)
    keep = sew[:, 0] != sew[:, 1]
    dist = np.linalg.norm(X[sew[:, 0]] - X[sew[:, 1]], axis=1)
    close = keep & (dist < near)
    info["coincident"] = int(close.sum())
    both = close & held[sew[:, 0]] & held[sew[:, 1]]
    keep &= ~both
    info["dropped"] = int((~keep).sum())
    todo = close & ~both
    if gap <= 0:  # the old behaviour: drop them
        info["dropped"] = int((~keep | todo).sum())
        return X, sew[keep & ~todo], info
    if not todo.any():
        return X, sew[keep], info
    # each vertex's own cloth: the mean of its triangle neighbours, and its normal
    acc, cnt, nrm = np.zeros_like(X), np.zeros(len(X)), np.zeros_like(X)
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    for k in range(3):
        for j in (1, 2):
            np.add.at(acc, F[:, k], X[F[:, (k + j) % 3]])
            np.add.at(cnt, F[:, k], 1.0)
        np.add.at(nrm, F[:, k], fn)
    X0 = X.copy()
    vs = np.unique(sew[todo])
    vs = vs[~held[vs] & (cnt[vs] > 0)]
    u = acc[vs] / cnt[vs, None] - X0[vs]
    ln = np.linalg.norm(u, axis=1)
    ok = ln > 1e-9
    if ok.any():
        X[vs[ok]] += u[ok] / ln[ok, None] * min(0.5 * gap, float(np.median(ln[ok])) * 0.25)
    info["moved"] = int(ok.sum())
    # layers lying on each other stepped the same way: part them along the normal
    a, b = sew[todo, 0], sew[todo, 1]
    still = np.linalg.norm(X[a] - X[b], axis=1) < 0.25 * gap
    for i, j in zip(a[still], b[still]):
        n = nrm[i] if np.linalg.norm(nrm[i]) > 1e-12 else nrm[j]
        ln_ = np.linalg.norm(n)
        if ln_ < 1e-12 or np.linalg.norm(X[i] - X[j]) >= 0.25 * gap:
            continue
        n = n / ln_
        if not held[i]:
            X[i] += n * 0.25 * gap
        if not held[j]:
            X[j] -= n * 0.25 * gap
        info["by_normal"] += 1
    return X, sew[keep], info


def zozo_bend(P: dict) -> float:
    """ZOZO's dimensionless `bend` for a fabric's flexural rigidity B (N m, cloth_job.PHYSICAL "bend"). ZOZO's hinge
    stiffness is BEND_SCALE * bend * areal density * |e|^2 / (A1 + A2) (Discrete Shells, density-normalised), i.e. a
    flexural rigidity B = BEND_SCALE * bend * density: bend = B / (BEND_SCALE * density). Shirting 2e-6 N m at
    120 g/m2: 1.3; wool coating 2e-5 at 450 g/m2: 3.5."""
    return float(P.get("bend", 2e-6)) / (BEND_SCALE * float(P["density"]))


def membrane(P: dict, job: dict) -> tuple[float, float]:
    """ZOZO's (young-mod, poiss-rat) for a fabric. Its Baraff-Witkin membrane takes stretch along the threads with
    mu = E / (2 (1 + nu)) and shear with lambda = E nu / ((1 + nu)(1 - 2 nu)) (builder.rs convert_prop), both per unit
    density. A woven cloth shears ~10x easier than it stretches (PHYSICAL shear/stretch 0.1-0.17): nu = r / (2 (1 + r)),
    E = 2 (1 + nu) stretch / density. (The old fixed nu 0.3 made shear 1.5x STIFFER than stretch: with the strain limit
    on the principal stretch, a sleeve couldn't shear its cap to hang down.) BUT the patch test (spikes/gpu_cloth/
    zozo_patch.py, a 0.2 m square under gravity) says the opposite: "woven" (E 418, nu 0.045) stretched 0.49% and
    sheared 2.4 deg vs "fixed" (E 200, nu 0.3) 1.27% / 3.8 deg: stiffer both ways (mu = E / 2(1 + nu) is what shear
    sees too). So job "shear_model" defaults to "fixed" (young = stretch / density, nu 0.3); "woven" kept as an
    option; "poisson"/"young_mod" override."""
    dens = float(P["density"])
    if job.get("shear_model", "fixed") == "fixed" or "shear" not in P:
        nu, young = 0.3, P["stretch"] / dens
    else:
        r = float(P["shear"]) / float(P["stretch"])
        nu = r / (2 * (1 + r))
        young = 2 * (1 + nu) * float(P["stretch"]) / dens
    nu = float(job.get("poisson", nu))
    young = float(job.get("young_mod", young))
    return young, nu


def profile(data: Path, times: dict, fps: float) -> dict:
    """Where a session's time went, per stage of the schedule (ZOZO's per-step records in output/data): ms per frame,
    steps per frame, how much of dt each step advanced (the time of impact: contact or the strain limit), newton
    steps, PCG iterations, contacts, the largest stretch, and ms per step of the big phases."""
    def load(nm):
        f = data / f"{nm}.out"
        try:
            a_ = np.loadtxt(f, ndmin=2)
            return a_ if a_.shape[1] >= 2 else None
        except (OSError, ValueError):
            return None
    rec = {k: load(f"advance.{k}" if k else "advance") for k in (
        "", "toi", "SL_toi", "contact_toi", "newton_steps", "iter", "num_contact", "max_sigma", "linsolve",
        "matrix_assembly", "asm_contact", "check_intersection", "line_search")}
    if rec[""] is None:
        return {}
    out = {}
    for nm, (t0, t1) in times.items():
        def sel(k):
            a_ = rec.get(k)
            if a_ is None:
                return np.zeros(0)
            return a_[(a_[:, 0] >= t0) & (a_[:, 0] < t1), 1]
        steps = sel("")
        if not len(steps):
            continue
        frames = max(1e-9, (t1 - t0) * fps)
        toi, sl = sel("toi"), sel("SL_toi")
        out[nm] = {"frames": int(round(frames)), "ms_per_frame": float(steps.sum() / frames),
                   "steps_per_frame": float(len(steps) / frames),
                   "toi": float(toi.mean()) if len(toi) else 1.0,
                   "sl_bound": float(np.mean(sl <= toi + 1e-9)) if len(sl) and len(sl) == len(toi) and toi.mean() < 0.999 else 0.0,
                   "newton": float(sel("newton_steps").mean()) if len(sel("newton_steps")) else 0.0,
                   "pcg": float(sel("iter").mean()) if len(sel("iter")) else 0.0,
                   "contacts": float(sel("num_contact").mean()) if len(sel("num_contact")) else 0.0,
                   "max_sigma": float(sel("max_sigma").max()) if len(sel("max_sigma")) else 0.0,
                   "ms": {k: float(sel(k).mean()) if len(sel(k)) else 0.0 for k in (
                       "linsolve", "matrix_assembly", "asm_contact", "check_intersection", "line_search")}}
    return out


def _tube(a, b, r, n=16):
    """A closed cylinder (end fans) round a -> b: a rack's pole or a hanger's arm as a collider."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = (b - a) / np.linalg.norm(b - a)
    u = np.cross(d, [1, 0, 0] if abs(d[0]) < 0.9 else [0, 1, 0])
    u /= np.linalg.norm(u)
    w = np.cross(d, u)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.outer(np.cos(ang), u) + np.outer(np.sin(ang), w)
    V = np.r_[a + r * ring, b + r * ring, [a], [b]]
    F = [[i, (i + 1) % n, n + (i + 1) % n] for i in range(n)] + [[i, n + (i + 1) % n, n + i] for i in range(n)]
    F += [[2 * n, (i + 1) % n, i] for i in range(n)] + [[2 * n + 1, n + i, n + (i + 1) % n] for i in range(n)]
    return V, np.asarray(F, np.int64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--frames", type=int, default=None, help="stop early (debugging)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--snap", type=int, default=0, help="also keep every N-th frame (S<frame> in out.npz)")
    ap.add_argument("--keep-session", action="store_true", help="leave ZOZO's session folder (deleted by default)")
    a = ap.parse_args()
    jd = Path(a.job)
    job = json.loads((jd / "job.json").read_text())
    job.update(job.pop("zozo", None) or {})  # the garment's solver options
    a.snap = a.snap or int(job.get("snap", 0))  # snapshots S<frame> in out.npz (zozo option "snap": every N frames)
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
    # a stitch whose ends start together has no direction (ZOZO: NaN force), and dropped it sews nothing: its ends
    # are stepped apart into their own cloth (part_stitches); what is held as made stays where it is
    held = np.zeros(n, bool)
    if "carryIdx" in d:
        held[np.asarray(d["carryIdx"], np.int64)] = True
    if job.get("made"):
        held |= np.isin(np.asarray(d["piece"]), [job["pieces"].index(nm) for nm in job["made"]])
    X, sew, sinfo = part_stitches(X, F, sew, held, float(job.get("stitch_gap", 0.002)))
    if sinfo["coincident"]:
        log(f"zozo: {sinfo['coincident']} stitches started with their ends together: {sinfo['moved']} ends stepped "
            f"apart into their own cloth ({sinfo['by_normal']} pairs along the normal), {sinfo['dropped']} dropped")
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
    data_root = Path(App.get_data_dirpath())
    data_root.mkdir(parents=True, exist_ok=True)
    free = _free_gb(data_root)
    if free < MIN_FREE_GB:
        raise RuntimeError(f"only {free:.1f} GB free under {data_root} (need {MIN_FREE_GB}): not starting")
    app = App.create(name)
    app_root = data_root / name  # the session's files: deleted after the run (out.npz has what we keep)
    # the flat pattern as the mesh's UV: ZOZO's Baraff-Witkin membrane takes its thread directions (stretch along u
    # and v, shear between them) from the UV; without one each triangle's own first edge was its "warp", a random
    # anisotropy that only an isotropic material (shear as stiff as stretch) hides
    if job.get("uv_frame", True) and "uv" in d:
        app.asset.add.tri("garment", np.c_[X, np.asarray(d["uv"], float)].astype(np.float64), F)
    else:
        app.asset.add.tri("garment", X.astype(np.float64), F)
    Ind = np.c_[sew[:, 0], sew[:, 1], sew[:, 1], sew[:, 1]].astype(np.int64)
    W = np.tile([1.0, 1.0, 0.0, 0.0], (len(sew), 1))
    app.asset.add.stitch("seams", (Ind, W))
    has_body = any(s.get("body", True) for s in stages) and not job.get("no_body")
    if has_body:
        # placement "smooth": the garment was put on the body with straight arms (bodyV0), which bends back to its
        # pose through bodyPoses in the "pose" stage
        bV0 = np.asarray(d["bodyV0"] if "bodyV0" in d else d["bodyV"], float)
        bT = np.asarray(d["bodyT"], np.int64)
        # a body that moves is solved (pinned, prescribed): 2.5x the cost of a static collider. Only the part that
        # moves is: the arms (faces with a vertex the poses move) apart from the static rest
        parts = [("body", np.arange(len(bV0)), bT)]
        # stages that move the body: "pose" true = bodyPoses (elbows bent back), or the array's name (bodyLower: the
        # arms brought down to the sides before a garment goes on its hanger)
        posers = [(st, "bodyPoses" if st["pose"] is True else st["pose"]) for st in stages if st.get("pose")]
        posers = [(st, k) for st, k in posers if k in d]
        if posers and job.get("split_body", True):
            mv = np.zeros(len(bV0), bool)
            for _, k in posers:
                mv |= (np.abs(np.asarray(d[k], float) - bV0).max(axis=(0, 2)) > 1e-7)
            fm = mv[bT].any(1)
            parts = []
            for nm_, ff in (("body", bT[~fm]), ("arms", bT[fm])):
                used = np.unique(ff)
                remap = -np.ones(len(bV0), np.int64)
                remap[used] = np.arange(len(used))
                parts.append((nm_, used, remap[ff]))
        for nm_, used, ff in parts:
            app.asset.add.tri(nm_, bV0[used], ff)
    scene = app.scene.create()
    g = scene.add("garment")
    if not job.get("no_stitch"):
        g.stitch("seams")
    dens = float(P["density"])
    young, poisson = membrane(P, job)
    g.param.set("density", dens).set("young-mod", young)
    bend = zozo_bend(P) if job.get("bend") is None else float(job["bend"])
    log(f"zozo: bend {bend:.2f} (ZOZO's dimensionless shell bend; the fabric's rigidity {P.get('bend', 0):.2g} N m"
        f" = {P.get('bend', 0) / 9.807e-5:.3f} gf cm2/cm at {P['density'] * 1000:.0f} g/m2)")
    g.param.set("poiss-rat", poisson).set("bend", bend)
    g.param.set("strain-limit", float(job.get("strain_limit", 0.05))).set("friction", float(P.get("friction", 0.4)))
    g.param.set("contact-gap", float(job.get("contact_gap", 1e-3)))
    # rest "flat": the membrane rests on the flat pattern (set on the built scene below), the start is the placement
    # (placement "smooth" jobs); "placed": the start is the rest, as in Blender
    rest = job.get("rest", "flat" if job.get("placement") == "smooth" else "placed")
    stiff = np.asarray(d["stiff"], float)
    pid = np.asarray(d["piece"])
    if rest == "flat":
        # bending rest flat (0) on ordinary cloth. Pieces wholly interfaced (collar, stand, cuffs) rest as placed in membrane and bending: a turned collar's U
        # and a cuff's curl are the made shape, and a fold over coarse triangles isn't isometric to the flat. Every
        # hinge lies inside one piece, so choosing per piece is consistent
        uv = np.asarray(d["uv"], float)
        flat3 = np.c_[uv, np.zeros(len(uv))]
        made = np.isin(pid, [job["pieces"].index(nm) for nm in job.get("made", [])])  # cloth.made_pieces
        if "rest" in d:  # cloth.rest_shape: the made pieces as made (before the start was pushed clear of the body)
            flat3[made] = np.asarray(d["rest"], float)[made]
        else:
            flat3[made] = X[made]
        lifted = made.copy()  # pieces that may start past the strain limit (placed folded or closed round a limb)
        if "releaseIdx" in d:
            lifted[np.asarray(d["releaseIdx"], np.int64)] = True
        if "carryIdx" in d:  # held pieces (method "settle") rest as they start: nothing in them is solved
            ci = np.asarray(d["carryIdx"], np.int64)
            # (the fine settle gives their made shape as "rest": a flap released after the press rests folded as made,
            # not as it started, open)
            if "restIdx" in d and "rest" in d:  # the fine settle: the made pieces (their free flaps too) rest as made;
                # draped cloth held far from them rests flat like the cloth it is joined to
                ri = np.asarray(d["restIdx"], np.int64)
                flat3[ri] = np.asarray(d["rest"], float)[ri]
                made[ri] = True
            else:
                flat3[ci] = X[ci]
                made[ci] = True
        for nm in job.get("rest_placed", []):  # (experiments: these pieces rest as they start)
            sel_ = pid == job["pieces"].index(nm)
            flat3[sel_] = X[sel_]
        for nm in job.get("rest_flat", []):  # (experiments: these made pieces rest on the flat pattern)
            sel_ = pid == job["pieces"].index(nm)
            flat3[sel_] = np.c_[uv, np.zeros(len(uv))][sel_]
            made[sel_] = False
        ref = flat3.copy()
        if "bend_rest" in d:  # fold lines (folds.py): the flat pattern folded at its lines, where the cloth rests flat
            ref[~made] = np.asarray(d["bend_rest"], float)[~made]
        g.set_bend_rest_vert(ref)
        # a made piece pushed clear of the body starts stretched past its rest (a cuff round a wrist fatter than it
        # was made for); a strain-limited solver can't start past the limit, so those pieces get a limit above their
        # start stretch, and contract onto the body to their made size
        lim = float(job.get("strain_limit", 0.05))
        sig = _start_stretch(flat3, X, F)
        # so do the few triangles of draped cloth that start past it by construction (the rows of a roll line turned
        # round a chest that curves, a cut-on collar's stand pushed a millimetre off the neck): a local limit above
        # their start, never more than START_OVER of the cloth (more is a placement fault: cloth_workflow stage 4)
        over = (sig > 1.0 + lim) & ~lifted[F].all(1)
        if 0 < over.mean() <= float(job.get("start_over", 0.03)):
            lifted[np.unique(F[over])] = True
            log(f"zozo: {int(over.sum())} triangles of draped cloth start up to {(float(sig[over].max()) - 1) * 100:.0f}% "
                "stretched (fold rows, pushed bands): a local strain limit there")
        fm = lifted[F].all(1) | over
        need = float(sig[fm].max()) - 1.0 if fm.any() else 0.0
        # (experiment) job "zone_limit": {"pieces": [...whole], "top": {piece: m from its pattern top}, "value": 0.15}:
        # another strain limit there (the shoulder/yoke dome)
        zl = job.get("zone_limit")
        zone = np.zeros(len(pid))
        if zl:
            for nm in zl.get("pieces", []):
                zone[pid == job["pieces"].index(nm)] = 1.0
            for nm, dy in (zl.get("top") or {}).items():
                sel_ = pid == job["pieces"].index(nm)
                zone[sel_ & (uv[:, 1] > uv[sel_, 1].max() - float(dy))] = 1.0
            zone[made] = 0.0
        tgt = min(1.0, 1.3 * need + 0.02) if need > 0.8 * lim else None
        if tgt is not None or zone.any():
            zv = float(zl["value"]) if zl else lim
            T = max(tgt or 0.0, zv)
            w = (lifted.astype(float) * ((tgt - lim) / (T - lim) if tgt else 0.0)
                 + zone * (zv - lim) / max(T - lim, 1e-9))
            g.param.set("strain-limit", lim)
            g.set_param_spatial("strain-limit", np.clip(w, 0, 1), T)
            if tgt:
                log(f"zozo: made pieces start up to {need * 100:.0f}% stretched past their rest: their strain limit "
                    f"{tgt * 100:.0f}%")
            if zone.any():
                log(f"zozo: strain limit {zv * 100:.0f}% on {int(zone.sum())} zone vertices")
    else:
        g.param.set("bend-rest-from-geometry", float(job.get("bend_rest_geom", 1.0)))
    # the start's own few crossings (a coat's under sleeve against the back's armhole edge, a collar pushed off the jaw
    # into its stand: all at seams that close) are linked by the scene check and exempt; everything else collides.
    # (The pass-through that once looked like this allowance was the pins': `pin_pass`)
    if job.get("allow_existing", True):
        g.param.set("allow-existing-intersection", 1.0)  # the placement's own few overlaps (sleeve fins) aren't fatal
    if job.get("stitch_stiffness"):
        g.param.set("stitch-stiffness", float(job["stitch_stiffness"]))
    # interfacing: bending up towards its interfaced value; fold lines: the rows of a crease bend harder still (a
    # pressed fold holds its angle), `fold_press` x the cloth's at strength 1. One multiplier per vertex
    mult = np.ones(n)
    if stiff.max() > 0 and job.get("interfacing", True):
        mult += stiff * (float(job.get("interfacing_bend", P.get("interfacing_bend", 10))) - 1.0)
    if "fold" in d and job.get("folds", True):
        mult += np.asarray(d["fold"], float) * float(job.get("fold_press", 20.0))
    if mult.max() > 1.0:
        g.set_param_spatial("bend", (mult - 1.0) / (mult.max() - 1.0), bend * float(mult.max()))
    asm = job.get("assemble") or {}
    sew_end = 0.0
    for s in stages:
        if s.get("gravity", 1) == 0:
            sew_end = max(sew_end, times[s["name"]][1])
    # the bodice is sewn alone with the rest held (assemble.fixed until the assemble stage ends); pieces that close
    # round a limb (cuffs, assemble.hold) are held on until the sewing ends. One pin per vertex: the hold used to be
    # (hold - fixed), which is empty when the cuffs are among the fixed, so the cuffs flew up the arm once released
    # (resting on the flat pattern the cuffs aren't held: a held cuff pressed onto the wrist is two prescribed things
    # in contact, which the barrier can't part: "contact starts overlapping" as the sleeve pulled on it)
    hold = set(map(int, asm.get("hold") or [])) if "sew" in times and job.get("hold", rest != "flat") else set()
    fixed = set(map(int, asm.get("fixed") or [])) - hold if "assemble" in times else set()
    # neck pieces (stand, collar) aren't held: held, the rising bodice pressed them into the (also prescribed) body,
    # two pinned things no contact separates (an intersection at the unpin)
    neck = [k for k, nm in enumerate(job["pieces"]) if (job.get("wraps") or {}).get(nm) == "neck"]
    fixed = sorted(fixed - set(np.where(np.isin(pid, neck))[0].tolist())) if job.get("free_neck", True) else sorted(fixed)
    pp = bool(job.get("pin_pass", False))  # ZOZO keeps a pin's pass-through after the unpin (set once at build): False
    if fixed and job.get("assemble_pins", rest != "flat"):
        g.pin(fixed, allow_intersection=pp).unpin(times["assemble"][1])
    if hold:
        g.pin(sorted(hold), allow_intersection=pp).unpin(times["sew"][1])
    if "carryIdx" in d and len(d["carryIdx"]):
        # method "settle": the made pieces are held as constructed for the whole sim and ride the body through its
        # poses (their positions per pose come with the job: a rigid move fitted to the body under each)
        ci = np.asarray(d["carryIdx"], np.int64)
        cposes = np.asarray(d["carryPoses"], float)
        # releaseIdx (the fine settle): the made pieces' turned-over flaps are let go once they have pressed the cloth
        # down, and settle on it as stiff cloth resting folded (a fall lies on the shoulders' cloth: held, it stood
        # off it or went through it)
        rel = np.isin(ci, np.asarray(d["releaseIdx"], np.int64)) if "releaseIdx" in d else np.zeros(len(ci), bool)
        pose_st = [st for st in stages if st.get("pose") is True]
        # hugIdx: made bands constructed inside the body's contact standoff (a buttoned collar stand 1.2 mm off the
        # neck): held, they need no contact with the body, and their pins pass through it
        hug = np.isin(ci, np.asarray(d["hugIdx"], np.int64)) if "hugIdx" in d else np.zeros(len(ci), bool)
        for part, free, thru in ((~rel & ~hug, False, False), (~rel & hug, False, True), (rel, True, False)):
            if not part.any() or (free and not pose_st):  # (flaps free from the start: never pinned)
                continue
            cp = g.pin(list(map(int, ci[part])), allow_intersection=thru)
            for pose in pose_st:
                t0, t1 = times[pose["name"]]
                for k in range(len(cposes)):
                    cp.move_to(cposes[k][part], t0 + (t1 - t0) * k / len(cposes), t0 + (t1 - t0) * (k + 1) / len(cposes))
            if free and pose_st:
                cp.unpin(times[pose_st[-1]["name"]][1])
        log(f"zozo: {len(ci)} vertices of made pieces held as constructed and carried with the body"
            + (f"; {int(rel.sum())} of them (flaps) released after the press" if rel.any() else ""))
    hang = next((s for s in stages if s.get("hang") or s.get("hanger")), None)
    pins = np.asarray(job.get("pins") or [], np.int64)
    if hang is not None and len(pins):
        t0, t1 = times[hang["name"]]
        hook = np.asarray(job["hook"], float)
        target = hook - [0, 0, 0.01] + (X[pins] - X[pins].mean(0)) * float(job.get("pin_spread", 0.3))
        # pinned where they start (a small patch at the back neck, harmless while dressing), then lifted to the hook
        g.pin(list(map(int, pins))).move_to(target, t0, t0 + 0.4 * (t1 - t0))
    if hang is not None and job.get("rack") and job.get("use_rack", True):
        # the rack: capsules far from the hook (a pole) stand still from the start; the hanger's arms (near the hook)
        # start where the hanger loop starts (inside the body's shoulders, which they don't collide with) and rise
        # with the pins, colliding only from the hang on: the coat is lifted by its shoulders, as on a real hanger
        t0, t1 = times[hang["name"]]
        hook = np.asarray(job["hook"], float)
        lift = hook - [0, 0, 0.01] - X[pins].mean(0) if len(pins) else np.zeros(3)
        # (from the hanger loop itself they started touching the collar: contact can't start overlapping) a further
        # `rack_drop` down, inside the body, and rising that much more
        lift = lift + [0.0, 0.0, float(job.get("rack_drop", 0.08))]
        for k, (a_, b_, r_) in enumerate(job["rack"]):
            a_, b_ = np.asarray(a_, float), np.asarray(b_, float)
            near = min(np.linalg.norm(a_ - hook), np.linalg.norm(b_ - hook)) < 0.15
            if near:  # an arm from the hook's centre: start it 1.5 cm out (the two arms mustn't overlap)
                c_, e_ = (a_, b_) if np.linalg.norm(a_ - hook) < np.linalg.norm(b_ - hook) else (b_, a_)
                a_, b_ = c_ + (e_ - c_) * 0.015 / np.linalg.norm(e_ - c_), e_
            V_, F_ = _tube(a_ - (lift if near else 0), b_ - (lift if near else 0), float(r_))
            app.asset.add.tri(f"rack{k}", V_, F_)
            o_ = scene.add(f"rack{k}")
            o_.param.set("contact-offset", float(job.get("body_offset", 0.002))).set("friction", float(P.get("friction", 0.4)))
            rp = o_.pin()
            if near:
                rp.move_by(list(map(float, lift)), t0, t0 + 0.4 * (t1 - t0))
                o_.collision_windows([(t0, t1 + 1e3)])
    if hang is not None and hang.get("hanger") and job.get("use_hanger", True):
        # on a hanger: the hanger (arms, hook, bar) and the rail stand still from the start, inside the body while the
        # garment is dressed (the cloth never meets them until the body stops colliding), then carry it by contact
        for nm_ in ("hanger", "rail"):
            if f"{nm_}V" not in d:
                continue
            app.asset.add.tri(nm_, np.asarray(d[f"{nm_}V"], float), np.asarray(d[f"{nm_}F"], np.int64))
            o_ = scene.add(nm_)
            o_.param.set("contact-offset", float(job.get("hanger_offset", job.get("body_offset", 0.002))))
            o_.param.set("friction", float(job.get("hanger_friction", max(0.5, float(P.get("friction", 0.4))))))
            o_.pin()
    if has_body:
        for nm_, used, _ in parts:
            b = scene.add(nm_)
            b.param.set("contact-offset", float(job.get("body_offset", 0.002))).set("friction", float(P.get("friction", 0.4)))
            bp = b.pin()
            for pose, key in (posers if (nm_ == "arms" or len(parts) == 1) else []):
                t0, t1 = times[pose["name"]]
                poses = np.asarray(d[key], float)[:, used]
                for k in range(len(poses)):
                    bp.move_to(poses[k], t0 + (t1 - t0) * k / len(poses), t0 + (t1 - t0) * (k + 1) / len(poses))
            if hang is not None:  # the body stops colliding as the coat is lifted to its hook (moved away down
                # through the sleeves, it dragged them down against the hanger pins: CCD failed at the strain limit).
                # Windows act on solved objects only: a static collider kept holding the sleeves out, so the body is
                # given a still move to make it one. job "release" (experiments): "window" (default) | "keep" (the
                # body stays, gravity off over the hang) | "sink" (the body moves down `release_drop` m over
                # `release_frames`, colliding) | "shrink" (it shrinks toward a heavily smoothed copy of itself)
                th = times[hang["name"]][0]
                rel = job.get("release", "window")
                rdur = float(job.get("release_frames", 30)) / fps
                cur = (np.asarray(d[posers[-1][1]], float)[-1] if posers else bV0)[used]
                if rel == "keep":
                    pass
                elif rel in ("sink", "shrink"):
                    if rel == "sink":
                        tgt = cur + [0.0, 0.0, -float(job.get("release_drop", 0.6))]
                    else:
                        tgt = _shrunk(np.asarray(d[posers[-1][1]], float)[-1] if posers else bV0, bT,
                                      int(job.get("shrink_iters", 300)))[used]
                    n_ = 6
                    for k in range(n_):
                        bp.move_to(cur + (tgt - cur) * (k + 1) / n_, th + rdur * k / n_, th + rdur * (k + 1) / n_)
                    b.collision_windows([(0.0, th + rdur)])
                else:
                    b.collision_windows([(0.0, th)])
                    if nm_ == "body" and len(parts) > 1:
                        bp.move_by([0.0, 0.0, 0.0], th, th + 0.05)
    st_ = job.get("set")
    if st_ and st_.get("from") in times:
        # the garment takes a set (bend plasticity: each hinge's rest angle creeps toward its current angle at `rate`
        # per second) while `from` .. `to` stages run: a coat on a hanger keeps the shape the arms-down pose gave its
        # sleeves instead of springing back to the angle its flat-pattern rest prefers
        ta = times[st_["from"]][0]
        tb = times[st_.get("to", st_["from"])][1]
        if st_.get("to_frac") is not None:  # only the first part of the last stage
            t0_ = times[st_.get("to", st_["from"])][0]
            tb = t0_ + float(st_["to_frac"]) * (tb - t0_)
        r_ = float(st_.get("rate", 1.0))
        end_ = max(v[1] for v in times.values()) + 1.0
        scene.set_param_anim_times([0.0, max(ta - 1e-3, 1e-4), ta, tb, tb + 1e-3, end_])
        if r_ > 0:
            g.set_param_anim("bend-plasticity", [0.0, 0.0, r_, r_, 0.0, 0.0])
            g.param.set("bend-plasticity-threshold", float(st_.get("threshold", 0.0)))
        # membrane plasticity: a coarse membrane can't buckle its compressed cloth into fine folds the way woven
        # cloth does (the underarm compressed ~4% by the arm pressed to the side), so it pushes back like a spring
        # (a hung sleeve swung 13-18 deg out in 8 frames once the body went); creeping the rest toward the current
        # state outside a dead zone takes that compression up
        rs_ = float(st_.get("stretch_rate", 0.0))
        if rs_ > 0:
            g.set_param_anim("plasticity", [0.0, 0.0, rs_, rs_, 0.0, 0.0])
            g.param.set("plasticity-threshold", float(st_.get("stretch_threshold", 0.01)))
        log(f"zozo: plasticity (bend {r_}/s, membrane {rs_}/s) from {ta:.2f} to {tb:.2f} s (the garment takes a set)")
    try:
        scene = scene.build()
    except Exception as e:
        from scipy.spatial import cKDTree
        tg, tb = cKDTree(X), cKDTree(bV0) if has_body else None
        for v in (getattr(e, "violations", None) or [])[:20]:
            who = []
            for tri in np.asarray(v.get("tris", np.zeros((0, 3, 3))), float).reshape(-1, 3, 3):
                c = np.asarray(tri, float).mean(0)
                dg, ig = tg.query(c)
                db = tb.query(c)[0] if tb is not None else np.inf
                who.append(job["pieces"][int(pid[ig])] if dg <= db else "body")
            if job.get("debug_violations"):
                log("detail:", json.dumps(v, default=str)[:700])
            log("violation:", v.get("type"), " x ".join(who), np.asarray(v.get("tris", np.zeros((1, 3, 3))), float).reshape(-1, 3, 3)[0].mean(0).round(3))
        raise
    if rest == "flat":  # the frontend has no call for a static rest shape apart from the start: write it in
        idx = np.asarray(scene._map_by_name["garment"], np.int64)
        cv = np.asarray(scene._vert[1], float)
        rv = cv.copy() if scene._concat_rest_vert is None else np.asarray(scene._concat_rest_vert, float)
        mask = np.zeros(len(cv), np.uint8) if scene._rest_vert_mask is None else np.asarray(scene._rest_vert_mask)
        rv[idx] = flat3
        mask[idx] = 1
        scene._concat_rest_vert, scene._rest_vert_mask = rv, mask
    gidx = np.asarray(scene._map_by_name["garment"], np.int64)
    # the garment's rows in the session's vert_N.bin (ZOZO reorders): for looking into a running session
    np.save(jd / "zozo_rows.npy", gidx)
    sess = app.session.create(scene)
    prm = sess.param
    prm.set("fps", fps).set("frames", total).set("dt", float(job.get("dt", 0.01)))
    prm.set("gravity", [0.0, 0.0, 0.0] if sew_end > 0 else [0.0, 0.0, -9.8])
    if sew_end > 0:
        gdyn = prm.dyn("gravity").time(sew_end).hold().change([0.0, 0.0, -9.8])
        if job.get("release") == "keep" and hang is not None:  # (experiment) the hang without gravity, body kept
            gdyn.time(times[hang["name"]][0]).hold().change([0.0, 0.0, 0.0])
    if job.get("air_friction") is not None:
        prm.set("air-friction", float(job["air_friction"]))
    sess = sess.build()
    cw = getattr(scene, "_collision_windows_data", None) or {}
    if cw:  # the session's dyn_param.txt (gravity) is written over the scene's: the collision windows were lost and
        # the hung coat's sleeves stayed up on the body's arms. Appended back
        with open(Path(sess.info.path) / "dyn_param.txt", "a") as f:
            for key, wins in cw.items():
                f.write(f"[{key}]\n" + "".join(f"{float(a_)} {float(b_)}\n" for a_, b_ in wins))
    log(f"zozo: {n} verts, {len(F)} tris, {len(sew)} stitches, {total} frames at {fps:.0f} fps, sewing until "
        f"{sew_end:.2f} s, mode {job.get('mode', 'sim')}")
    tt = time.time()
    pruner = _Pruner(app_root / "session" / "output", a.snap, total)
    pruner.start()
    try:
        sess.start(blocking=True)
    finally:
        pruner.stop_flag.set()
    pruner.prune()
    if pruner.low is not None:
        shutil.rmtree(app_root, ignore_errors=True)
        raise RuntimeError(f"stopped: disk down to {pruner.low:.1f} GB free")
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
    F0 = np.asarray(first[0], float)
    # the garment's rows in ZOZO's concatenated output (`map_by_name`); checked on frame 0 (matching frame 0 by
    # nearest start vertex failed on a coat whose start has coincident vertices)
    rows = gidx if len(F0) > gidx.max() and np.abs(F0[gidx] - X).max() < 1e-5 else None
    if rows is None:
        from scipy.spatial import cKDTree
        dd, ii = cKDTree(F0).query(X)
        if dd.max() > 1e-5:
            raise RuntimeError(f"frame 0 doesn't hold the start ({dd.max() * 1000:.3f} mm off)")
        rows = ii
    V = np.asarray(Vall, float)[rows]
    try:
        ms = sess.get.log.numbers("time-per-frame")
        per = sum(v for _, v in ms) / max(1, len(ms))
    except Exception:
        per = float("nan")
    gap = np.linalg.norm(V[sew[:, 0]] - V[sew[:, 1]], axis=1)
    log(f"zozo: {frame} frames in {wall:.1f} s ({per:.0f} ms/frame), seam gaps mean {gap.mean() * 1000:.1f} mm p95 "
        f"{np.percentile(gap, 95) * 1000:.1f} mm, z {V[:, 2].min():.3f}..{V[:, 2].max():.3f}")
    snaps = {}
    for f in range(a.snap, frame, a.snap) if a.snap else ():
        got_f = sess.get.vertex(f)
        if got_f is not None:
            Vf = np.asarray(got_f[0], float)[rows]
            snaps[f"S{f}"] = Vf
    got_p = sess.get.vertex(max(0, frame - 6)) if frame > 6 else None  # cloth.PREV_APART: the "still moving" measure
    if got_p is not None:
        snaps["Vprev"] = np.asarray(got_p[0], float)[rows]
    out = Path(a.out) if a.out else jd / "out.npz"
    prof = profile(app_root / "session" / "output" / "data", times, fps)
    for nm_, st in prof.items():
        log(f"zozo {nm_}: {st['frames']} frames, {st['ms_per_frame']:.0f} ms/frame, {st['steps_per_frame']:.1f} steps/frame "
            f"(step advanced {st['toi'] * 100:.0f}% of dt, strain limit binding in {st['sl_bound'] * 100:.0f}% of "
            f"steps), {st['newton']:.1f} newton, {st['pcg']:.0f} pcg iters, {st['contacts']:.0f} contacts, max sigma "
            f"{st['max_sigma']:.3f}; ms/step: linsolve {st['ms']['linsolve']:.0f}, assembly "
            f"{st['ms']['matrix_assembly']:.0f}, contact {st['ms']['asm_contact']:.0f}, intersection check "
            f"{st['ms']['check_intersection']:.0f}")
    np.savez(out, V=V, **snaps, log=np.array(LOG), timing=np.array(json.dumps(
        {"total_s": wall, "ms_per_frame": per, "stages": prof})))
    print("cloth: wrote", out, flush=True)
    if not a.keep_session:
        shutil.rmtree(app_root, ignore_errors=True)


if __name__ == "__main__":
    main()
