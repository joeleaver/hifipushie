"""Run a hifipushie cloth job (src/hifipushie/cloth_job.py) with NVIDIA Newton's VBD cloth solver (warp; CUDA or CPU).

    python run_newton.py <job folder> [--device cuda|cpu] [--substeps N] [--iterations N] [--out file]

Standalone: needs only numpy, scipy, warp-lang, newton (requirements.txt), not hifipushie or Blender.

Mapping of the job onto VBD:
- rest shape = the flat pattern (particles built at (u, v, 0): triangle rest poses and flat bending rest angles), then
  the particles are moved to the start positions X (or S for a refine);
- membrane: VBD's StVK triangles, mu/lambda from the fabric's stretch (N/m) (`physical.mu`/`lambda` override);
  bending per hinge from the bending rigidity B (N m): ke = 3 B L / (A1 + A2) (discrete shells), interfacing
  multiplies both; areal density -> particle masses;
- seams and stitches: zero-length springs; while a stage sews with a "sew_force" (the seams are still open) their rest
  length shrinks from the start gap to 0 over the first 60% of the stage (a capped closing speed, like Blender's
  sewing_force_max), and self-contact between the two sides of a seam is filtered out (they must meet);
- fixed vertices: inactive particles (held where they are); hung garments: anchors at the hook, sewn to the pins;
- the body: a static mesh shape; rack: static capsules; self-contact: VBD's vertex-triangle + edge-edge contact with
  its conservative (penetration-free) step bound;
- each stage starts from the previous one's positions at rest velocity (as Blender's restarted cloth objects do).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print("cloth:", s, flush=True)


def _edges_of(F):
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    return np.unique(np.sort(E, 1), axis=0)


def _ring_tris(F, n, rings=2):
    """Per vertex the triangles within `rings` rings (lists)."""
    vt = [[] for _ in range(n)]
    for t, f in enumerate(F):
        for v in f:
            vt[v].append(t)
    out = []
    for v in range(n):
        tris = set(vt[v])
        for _ in range(rings - 1):
            verts = {int(u) for t in tris for u in F[t]}
            tris = {t for u in verts for t in vt[u]}
        out.append(tris)
    return out


def weld_map(n, pairs, F):
    """Union-find over sewn pairs: rep[i] = the vertex i is merged into. Pairs whose merge would collapse a triangle
    (two of its corners in one group: the end of a dart, a seam chained back onto its own piece) are left as springs.
    Returns (rep, the pairs kept as springs)."""
    par = np.arange(n)

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    left = []
    corners = [set() for _ in range(n)]  # per group root: the triangles of its members
    vt = [[] for _ in range(n)]
    for t, f in enumerate(F):
        for v in f:
            vt[v].append(t)
    for i in range(n):
        corners[i] = set(vt[i])
    for a, b in pairs:
        if a >= n or b >= n:
            left.append((a, b))
            continue
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        if corners[ra] & corners[rb]:  # a triangle would get two corners in one vertex
            left.append((a, b))
            continue
        par[rb] = ra
        corners[ra] |= corners[rb]
    rep = np.array([find(i) for i in range(n)])
    return rep, np.asarray(left, np.int64).reshape(-1, 2)


class Sim:
    def __init__(self, job, d, device, substeps, iterations):
        import warp as wp
        self.wp = wp
        self.job, self.d, self.device = job, d, device
        self.substeps, self.iterations = substeps, iterations
        self.fps = float(job.get("fps", 24))
        self.F = np.asarray(d["F"], np.int64)
        uv = np.asarray(d["uv"], float)
        self.flat = np.c_[uv, np.zeros(len(uv))] if uv.shape[1] == 2 else uv
        self.n = len(self.flat)
        sew = np.asarray(d["sew"], np.int64).reshape(-1, 2)
        st = np.asarray(d["stitch"], np.int64).reshape(-1, 2) if "stitch" in d.files else np.zeros((0, 2), np.int64)
        self.sew = np.r_[sew, st] if len(st) else sew
        self.stiff = np.asarray(d["stiff"], float) if "stiff" in d.files else np.zeros(self.n)
        self.phys = job["fabric"]["physical"]
        self.timing = {}
        # seam neighbourhoods whose self-contact is filtered (the two sides must touch)
        self._seam_filter = None
        self.weld = bool(job.get("weld", True))

    # ---------------------------------------------------------------- model

    def _filters(self, pairs, n_tot):
        """VBD external filtering maps: each sewn vertex ignores the triangles round its partner(s), and the edges
        there ignore each other."""
        rings = _ring_tris(self.F, self.n, 2)
        vmap = {}
        for a, b in pairs:
            if a >= self.n or b >= self.n:
                continue
            vmap.setdefault(int(a), set()).update(rings[b] | rings[a])
            vmap.setdefault(int(b), set()).update(rings[a] | rings[b])
        # edge ids follow the builder's edge order: map (v1, v2) -> id after finalize
        return vmap

    def build(self, X, fixed, sew_pairs, rest_len, body, rack, anchors=None, self_contact=True, rep=None):
        """rep: welded seams (weld_map): every vertex's triangles and hinges point at its group's vertex, the others
        are inactive and follow it (sew_pairs are then only the pairs left as springs)."""
        wp = self.wp
        import newton
        from newton._src.sim.graph_coloring import color_graph
        P = self.phys
        b = newton.ModelBuilder(up_axis=newton.Axis.Z, gravity=-9.81)
        r = float(self.job.get("particle_radius", max(0.005, 2 * P.get("thickness", 0.0005))))
        mu = float(P.get("mu", 0.2 * P["stretch"]))
        lam = float(P.get("lambda", 0.3 * P["stretch"]))
        kd = float(P.get("membrane_damping", 1e-2))
        b.add_cloth_mesh(pos=wp.vec3(0.0, 0.0, 0.0), rot=wp.quat_identity(), scale=1.0, vel=wp.vec3(0.0, 0.0, 0.0),
                         vertices=self.flat.tolist(), indices=self.F.ravel().tolist(), density=float(P["density"]),
                         tri_ke=mu, tri_ka=lam, tri_kd=kd, edge_ke=1e-4, edge_kd=float(P.get("bend_damping", 1e-6)),
                         particle_radius=r)
        n_anchor = 0
        if anchors is not None and len(anchors):
            for a in anchors:
                b.add_particle(wp.vec3(*map(float, a)), wp.vec3(0.0, 0.0, 0.0), 0.0, radius=r)
            n_anchor = len(anchors)
        ks = float(self.job.get("sew_ke", P.get("sew_ke", 1e4)))
        for (i, j) in sew_pairs:
            b.add_spring(int(i), int(j), ks, float(self.job.get("sew_kd", 0.0)), 0)
        cfg = b.default_shape_cfg.copy()
        cfg.mu = float(P.get("friction", 0.4))
        cfg.margin = 0.0
        full = bool(self.job.get("full_surface", False))
        if full and not str(self.device).startswith("cuda"):  # Newton builds mesh SDFs on CUDA only
            if not getattr(self, "_said_full", False):
                log("full_surface needs CUDA (the body SDF): vertex contacts only")
                self._said_full = True
            full = False
        if body is not None:
            mesh = newton.Mesh(np.asarray(body[0], np.float32), np.asarray(body[1], np.int32).ravel())
            if full:  # edges and faces against the body's SDF too (a vertex-only test lets the body through triangles)
                if getattr(self, "_body_sdf", None) is None:
                    t = time.time()
                    mesh.build_sdf(device=self.device, target_voxel_size=float(self.job.get("sdf_voxel", 0.004)))
                    log(f"body SDF built in {time.time() - t:.1f} s")
                    self._body_sdf = mesh
                mesh = self._body_sdf
            b.add_shape_mesh(body=-1, mesh=mesh, cfg=cfg)
        for (a_, b_, rad) in (rack or []):
            a_, b_ = np.asarray(a_, float), np.asarray(b_, float)
            ax = b_ - a_
            L = float(np.linalg.norm(ax))
            z = np.array([0.0, 0.0, 1.0])
            v = np.cross(z, ax / L)
            s, c = np.linalg.norm(v), float(np.dot(z, ax / L))
            q = wp.quat_identity() if s < 1e-9 else wp.quat_from_axis_angle(wp.vec3(*(v / s)), float(np.arctan2(s, c)))
            b.add_shape_capsule(body=-1, xform=wp.transform(wp.vec3(*((a_ + b_) / 2)), q), radius=float(rad),
                                half_height=L / 2, cfg=cfg)
        # colouring: the mesh's own graph + bending opposite pairs + the springs (VBD's colour() leaves springs out)
        tri = np.asarray(b.tri_indices, np.int64)
        ei = np.asarray(b.edge_indices, np.int64)
        R = None
        if rep is not None:
            R = np.arange(len(b.particle_q))
            R[:self.n] = rep
            tri = R[tri]
            ei = np.where(ei >= 0, R[np.maximum(ei, 0)], -1)
        E = [tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]
        if len(ei):
            ok = (ei[:, 0] >= 0) & (ei[:, 1] >= 0)
            E.append(ei[ok][:, [0, 1]])
        if len(sew_pairs):
            E.append(np.asarray(sew_pairs, np.int64))
        E = np.unique(np.sort(np.concatenate(E), 1), axis=0).astype(np.int32)
        b.particle_color_groups = color_graph(len(b.particle_q), wp.array(E, dtype=int, device="cpu"))
        tri_flat = np.asarray(b.tri_indices, np.int64)  # the unwelded corners (rest geometry is per piece)
        ei_flat = np.asarray(b.edge_indices, np.int64)
        if R is not None:  # welded before finalize (rest poses are already taken from the flat pieces), so the
            b.tri_indices = [tuple(map(int, t)) for t in tri]  # model's adjacency is built on the welded mesh
            b.edge_indices = [tuple(map(int, e)) for e in ei]
            m = np.asarray(b.particle_mass, float)
            dup = np.where(R != np.arange(len(R)))[0]
            np.add.at(m, R[dup], m[dup])
            m[dup] = 0.0
            b.particle_mass = m.tolist()
        model = b.finalize(device=self.device)
        # per-element stiffness: interfacing on membrane and bending, hinge stiffness from the bending rigidity
        tm = model.tri_materials.numpy()
        sf = self.stiff[tri_flat].mean(1)
        tm[:, 0] = mu * (1 + (P["interfacing_stretch"] - 1) * sf)
        tm[:, 1] = lam * (1 + (P["interfacing_stretch"] - 1) * sf)
        model.tri_materials.assign(tm)
        if len(ei):
            ei = ei_flat
            fl = self.flat
            # hinge areas: the two triangles on the edge (o1 v1 v2), (o2 v1 v2)
            def ar(o):
                return 0.5 * np.linalg.norm(np.cross(fl[ei[:, 2]] - fl[o], fl[ei[:, 3]] - fl[o]), axis=1)
            A = np.where(ei[:, 0] >= 0, ar(np.maximum(ei[:, 0], 0)), 0) + np.where(ei[:, 1] >= 0, ar(np.maximum(ei[:, 1], 0)), 0)
            L = np.linalg.norm(fl[ei[:, 2]] - fl[ei[:, 3]], axis=1)
            sb = 0.5 * (self.stiff[ei[:, 2]] + self.stiff[ei[:, 3]])
            ke = 3.0 * P["bend"] * L / np.maximum(A, 1e-12) * (1 + (P["interfacing_bend"] - 1) * sb)
            ebp = model.edge_bending_properties.numpy()
            ebp[:, 0] = ke
            model.edge_bending_properties.assign(ebp)
        if len(sew_pairs):
            model.spring_rest_length.assign(np.asarray(rest_len, np.float32))
        flags = model.particle_flags.numpy()
        fx = np.asarray(list(fixed), np.int64)
        if len(fx):
            flags[fx] &= ~int(newton.ParticleFlags.ACTIVE)
        if n_anchor:
            flags[self.n:] &= ~int(newton.ParticleFlags.ACTIVE)
        Xall = np.r_[X, anchors] if n_anchor else X.copy()
        if R is not None:  # each group starts at its members' mean; held members are held at the group
            dup = np.where(R != np.arange(len(R)))[0]
            cnt = np.zeros(len(R))
            acc = np.zeros((len(R), 3))
            np.add.at(acc, R, Xall)
            np.add.at(cnt, R, 1)
            Xall = acc[R] / cnt[R][:, None]
            held = np.zeros(len(R), bool)
            held[fx] = True
            hr = np.zeros(len(R), bool)
            np.logical_or.at(hr, R, held)
            flags[hr] &= ~int(newton.ParticleFlags.ACTIVE)
            flags[dup] &= ~int(newton.ParticleFlags.ACTIVE)
        model.particle_flags.assign(flags)
        model.particle_q.assign(np.asarray(Xall, np.float32))
        model.soft_contact_ke = float(self.job.get("contact_ke", 1e4))
        model.soft_contact_kd = float(self.job.get("contact_kd", 1e-4))
        model.soft_contact_mu = float(P.get("friction", 0.4))
        vmap = self._filters(sew_pairs, len(Xall)) if self_contact and len(sew_pairs) and R is None else None
        sc = float(self.job.get("self_margin", max(0.0025, 2 * P.get("thickness", 0.0005))))
        solver = newton.solvers.SolverVBD(
            model, iterations=self.iterations, particle_enable_self_contact=self_contact,
            particle_self_contact_margin=sc, particle_self_contact_gap=float(self.job.get("self_gap", 0.6 * sc)),
            particle_external_vertex_contact_filtering_map=vmap)
        pipe = newton.CollisionPipeline(model, soft_contact_gap=float(self.job.get("body_gap", 0.004)),
                                        enable_rigid_soft_full_surface_contact=full and body is not None)
        return model, solver, pipe

    # ---------------------------------------------------------------- stages

    def run_stage(self, name, X, frames, gravity, fixed, sew_pairs, closing, body, rack, anchors=None, self_contact=True,
                  weld=False):
        wp = self.wp
        t0 = time.time()
        rep = None
        if weld:  # sewn seams merged into one vertex: no springs or contact fighting across a closed seam
            rep, sew_pairs = weld_map(self.n, sew_pairs, self.F)
        d0 = np.linalg.norm(np.r_[X, anchors][sew_pairs[:, 0]] - np.r_[X, anchors][sew_pairs[:, 1]], axis=1) \
            if anchors is not None and len(anchors) else (
            np.linalg.norm(X[sew_pairs[:, 0]] - X[sew_pairs[:, 1]], axis=1) if len(sew_pairs) else np.zeros(0))
        rest0 = d0 if closing else np.zeros_like(d0)
        model, solver, pipe = self.build(X, fixed, sew_pairs, rest0, body, rack, anchors, self_contact, rep)
        model.set_gravity((0.0, 0.0, -9.81 * gravity))
        s0, s1 = model.state(), model.state()
        ctrl = model.control()
        contacts = pipe.contacts()
        dt = 1.0 / self.fps / self.substeps
        t_build = time.time() - t0
        damp = float(self.job.get("frame_damping", 0.85))
        close_frames = max(1, int(0.6 * frames))
        for f in range(1, frames + 1):
            if closing and len(sew_pairs):
                k = min(1.0, f / close_frames)
                model.spring_rest_length.assign((rest0 * (1 - k)).astype(np.float32))
            for _ in range(self.substeps):
                s0.clear_forces()
                pipe.collide(s0, contacts)
                solver.step(s0, s1, ctrl, contacts, dt)
                s0, s1 = s1, s0
            # quasi-static settling: bleed off velocity each frame (Blender's air damping + its damped springs)
            qd = s0.particle_qd.numpy() * damp
            s0.particle_qd.assign(qd)
            if f % 10 == 0 or f == frames:
                q = s0.particle_q.numpy()
                if not np.isfinite(q).all():
                    raise RuntimeError(f"stage {name}: NaN at frame {f}")
                print(f"cloth: progress {name} {f}/{frames} {time.time() - t0:.0f}s", flush=True)
        wp.synchronize()
        V = s0.particle_q.numpy().astype(np.float64)
        if rep is not None:
            V[:self.n] = V[rep]
            log(f"  welded {int((rep != np.arange(self.n)).sum())} seam vertices, {len(sew_pairs)} pairs left as springs")
        dtot = time.time() - t0
        self.timing[name] = {"build_s": round(t_build, 2), "total_s": round(dtot, 2), "frames": frames}
        gap = np.linalg.norm(V[self.sew[:, 0]] - V[self.sew[:, 1]], axis=1) if len(self.sew) else np.zeros(1)
        log(f"stage {name}: {frames} frames, {dtot:.1f} s (build {t_build:.1f}), seam gaps mean {gap.mean() * 1000:.1f} mm "
            f"p95 {np.percentile(gap, 95) * 1000:.1f} mm, z {V[:self.n, 2].min():.3f}..{V[:self.n, 2].max():.3f}")
        return V

    def sim(self):
        job, d = self.job, self.d
        X = np.asarray(d["X"], float)
        body = (d["bodyV"], d["bodyT"])
        asm = job.get("assemble") or {}
        snaps = {}
        anchors = None
        pins = np.asarray(job.get("pins") or [], np.int64)
        for stg in job["stages"]:
            nm = stg["name"]
            fixed = stg.get("fixed") or []
            if fixed == "assemble.fixed":
                fixed = asm.get("fixed", [])
            elif fixed == "assemble.hold":
                fixed = asm.get("hold", [])
            elif fixed == "pins":
                fixed = []  # the anchors are inactive; the pins hang from them
            fx = np.zeros(self.n, bool)
            fx[np.asarray(fixed, np.int64)] = True
            pairs = self.sew
            if stg.get("sew") == "fixed-free":
                pairs = pairs[~fx[pairs[:, 0]] & ~fx[pairs[:, 1]]]
            elif not stg.get("sew", True):
                pairs = np.zeros((0, 2), np.int64)
            if stg.get("hang"):
                hook = np.asarray(job["hook"], float)
                X = X + (hook - [0, 0, 0.01] - X[pins].mean(0))
                anchors = hook + (X[pins] - X[pins].mean(0)) * float(job.get("pin_spread", 0.3))
            if anchors is not None:
                pairs = np.r_[pairs, np.c_[pins, self.n + np.arange(len(pins))]]
            closing = stg.get("sew_force") not in (None, 0.0) and stg.get("sew") is not False
            V = self.run_stage(nm, X, int(stg["frames"]), float(stg.get("gravity", 1)), np.where(fx)[0], pairs, closing,
                               body if stg.get("body", True) else None,
                               job.get("rack") if stg.get("rack") else None, anchors,
                               bool(stg.get("self_collision", True)), weld=self.weld and not closing)
            Vn = V[:self.n].copy()
            if nm == "assemble":
                Vn[fx] = np.asarray(d["X"], float)[fx]
            snaps[nm] = Vn
            X = Vn
        return X, snaps

    def refine(self):
        """mode "refine": start at S, rest = the flat pattern, settle with gravity + self-contact (pins held)."""
        job, d = self.job, self.d
        S = np.asarray(d["S"], float)
        pins = np.asarray(job.get("pins") or [], np.int64)
        stg = job["stages"][0]
        V = self.run_stage("refine", S, int(stg["frames"]), 1.0, pins, self.sew, False,
                           (d["bodyV"], d["bodyT"]) if stg.get("body", True) else None,
                           job.get("rack") if stg.get("rack") else None, None, bool(stg.get("self_collision", True)),
                           weld=self.weld)
        return V[:self.n], {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--device", default=None)
    ap.add_argument("--substeps", type=int, default=None)
    ap.add_argument("--iterations", type=int, default=None)
    ap.add_argument("--set", action="append", default=[], help="job key=json overrides (tuning)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    jd = Path(a.job)
    job = json.loads((jd / "job.json").read_text())
    for kv in a.set:
        k, v = kv.split("=", 1)
        if k.startswith("physical."):
            job["fabric"]["physical"][k.split(".", 1)[1]] = json.loads(v)
        else:
            job[k] = json.loads(v)
    d = np.load(jd / job.get("data", "in.npz"))
    import warp as wp
    wp.config.quiet = True
    wp.init()
    dev = a.device or ("cuda" if wp.is_cuda_available() else "cpu")
    sub = a.substeps or int(job.get("substeps", 10))
    it = a.iterations or int(job.get("iterations", 10))
    log(f"newton {__import__('newton').__version__} warp {wp.__version__} on {dev}"
        f"{' ' + wp.get_device(dev).name if dev.startswith('cuda') else ''}: {len(d['uv'])} verts, {len(d['F'])} tris, "
        f"mode {job.get('mode', 'sim')}, substeps {sub}, iterations {it}")
    t = time.time()
    s = Sim(job, d, dev, sub, it)
    V, snaps = s.refine() if job.get("mode") == "refine" else s.sim()
    total = time.time() - t
    log(f"total {total:.1f} s")
    out = Path(a.out) if a.out else jd / "out.npz"
    np.savez(out, V=V, **{k: v for k, v in snaps.items()}, log=np.array(LOG),
             timing=np.array(json.dumps({"total_s": total, "stages": s.timing, "device": dev})))
    print("cloth: wrote", out, flush=True)


if __name__ == "__main__":
    main()
