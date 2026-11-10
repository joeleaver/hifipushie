"""CHAIN JOBS: the chain build's job and its status (chain_garment.py's docstring is the spec, stages 7a and 8): the hang's
held mask, write_job and finish_hang (a mixin of GarmentBuild), job_dir, job_key, status.json (write_status, status,
live_status) and the record. Moved out of chain_garment.py (R3a, behaviour-preserving). The worker itself stays in
chain_garment.py (it runs as `python -m hifipushie.chain_garment`, and tests patch the names it reads there)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import numpy as np

from . import chain_net as cn
from .chain_net import project
from .chain_core import (ChainRefused)


class HangJob:
    """GarmentBuild's hang: what is held, the ZOZO job, the hung result (mixed into chain_garment.GarmentBuild)."""

    # ---- 7. the hang
    def hold_mask(self):
        net = self.net
        h = self._stiff_mask().copy()
        if getattr(self, "extra_held", None) is not None:
            h |= self.extra_held
        return np.isin(net.root, net.root[h])

    def write_job(self, jd: Path, fabric: dict, frames: int = 144, name: str = "chain_garment"):
        """The ZOZO job: the soft cloth under gravity, stiff parts held, the whole body the collider. A start ZOZO would
        refuse is refused here by name: it is the chain build's fault, never fixed by cutting, pushing or holding."""
        from . import cloth_job as cj, cloth_zozo as cz, zozo_hang as zh
        net = self.net
        X = np.asarray(self.X, float)
        uv, F = net.uv, net.F
        bV, bT = self.body.V, self.body.T
        hold = self.hold_mask()
        whole = self._stiff_mask()
        lg = zh.legality(X, F, bV, bT)
        if not lg["ok"]:
            w = lg["worst"][0] if lg["worst"] else None
            nm = net.names[net.piece[w[1][0]]] if w else "?"
            who = {}
            pr = zh.contact_pairs(X, F, bV, bT, zh.BODY_OFFSET + 1e-9)
            for c in pr["cloth"]:
                k_ = net.names[net.piece[c[c >= 0][0]]]
                who[k_] = who.get(k_, 0) + 1
            raise ChainRefused(f"illegal start: {lg['illegal']} cloth / body pairs inside ZOZO's contact offset ({lg['by_kind']}), nearest "
                               f"{lg['min_mm']} mm, worst on {nm}; by piece {who}. next: this is a chain-build fault; report it, nothing is pushed or cut")
        lim = zh.woven_limit()
        flat = np.c_[uv, np.zeros(len(uv))]
        R = flat.copy()
        R[whole] = X[whole]
        ci = np.where(hold)[0].astype(np.int64)
        ls = getattr(self, "layer_stiff", None)  # (R3c2: a floating layer's stiffness on its host, chain_holds)
        ls = 0.0 if ls is None else ls
        arrays = dict(X=X, uv=uv, F=F, sew=net.sew, stitch=np.asarray(net.M.get("stitch", np.zeros((0, 2))), np.int64).reshape(-1, 2),
                      stiff=np.clip(np.maximum(np.maximum(self.pat.stiff, whole.astype(float)), ls), 0, 1), piece=net.piece.astype(np.int64),
                      pins=np.zeros(0, np.int64), bodyV=bV, bodyT=bT, carryIdx=ci, carryPoses=X[ci][None], rest=R,
                      restIdx=np.where(whole)[0].astype(np.int64))
        made = [p for p in net.names if whole[net.verts(p)].all()]
        cfg = {"fabric": fabric, "name": name, "placement": "smooth", "wraps": {}, "made": made, "strain_limit": lim}
        jc = cj.job_config(cfg, net.names)
        jc["stages"] = [{"name": "settle", "frames": int(frames), "gravity": 1, "sew": True, "self_collision": True, "fixed": [], "body": True}]
        jc["snap"] = 24
        jd = Path(jd)
        jd.mkdir(parents=True, exist_ok=True)
        np.savez(jd / "in.npz", **arrays)
        (jd / "job.json").write_text(json.dumps(jc, indent=1, default=cj._jsonable))
        ss = zh.start_strain(arrays, jc)
        if not ss["ok"]:
            raise ChainRefused(f"start past the strain limit: {ss['over']} of {ss['faces']} faces, by piece {ss.get('by_piece')}; worst "
                               f"{ss.get('worst')}. next: a chain-build fault; report it, the limit is not a setting")
        self.reads["hang_start"] = {"legal_min_mm": lg["min_mm"], "strain_ok": True, "held": int(hold.sum()), "frames": int(frames)}
        return jd

    def finish_hang(self, V):
        """ZOZO's result back into the build: seams welded (a held side wins), lengths the last word, the body a floor."""
        net = self.net
        rs = net.root
        Vb = np.asarray(V, float)
        hold = self.hold_mask()
        cnt = np.bincount(rs, minlength=net.n).astype(float)
        S = np.zeros((net.n, 3))
        np.add.at(S, rs, Vb)
        M = S / np.maximum(cnt, 1)[:, None]
        M = np.where(hold[:, None], self.X, M)
        moved = np.linalg.norm(M[rs] - self.X, axis=1)
        I2, J2, L2, E2, _, fl2, th = self.final_links
        fl2 = fl2[:1]  # (the body: ZOZO has kept the cloth under the held fall; a squeezed point there must not stall the lengths)
        held = np.zeros(net.n, bool)
        held[rs[hold]] = True
        self.reads["hang_moved_mm"] = {"p50": round(float(np.median(moved[~hold]) * 1e3), 1), "p95": round(float(np.percentile(moved[~hold], 95) * 1e3), 1),
                                       "max": round(float(moved[~hold].max() * 1e3), 1), "drop_mm": round(float((self.X[~hold, 2] - M[rs][~hold, 2]).mean() * 1e3), 1)}
        self.reads["after_hang_before_lengths"] = {"threads": th.report(M[rs]), "chains_free_worst_pct": self.chain_read(M[rs])["free_worst_pct"]}
        n_chain = len(self.net.link_i) + len(self.net.lines()[0]) + len(self._closure_ties())
        Z = M.copy()
        # lengths the last word, the threads with them: a chain-only pass tears the cloth between the chains
        rd = {}
        for rnd in range(4):
            Z, rd = project(Z, I2, J2, L2, E2, held, fl2, threads=th, iters=30, step=0.004)
            self.log(f"after hang {rnd}: {rd}")
        # the chains last, with their moves carried into the cloth between them (a chain pass alone tears it, C263). Lines may
        # shorten here: a strip curved both ways by the hang can't keep every line across it exact and its chains too
        Ec = E2[:n_chain] & (np.arange(n_chain) < len(self.net.link_i))
        chain_nodes = np.unique(np.r_[self.net.link_i, self.net.link_j])
        rd2 = {}
        for rnd in range(3):
            Z0 = Z.copy()
            Z, rd2 = project(Z, I2[:n_chain], J2[:n_chain], L2[:n_chain], Ec, held, fl2, iters=40, step=0.003)
            kn = held.copy()
            kn[chain_nodes] = True
            for p in self.roles.panels + self.roles.tubes:
                v = net.verts(p)
                Fp = net.F[np.all(net.piece[net.F] == net.pid(p), axis=1)]
                k_ = np.zeros(net.n, bool)
                k_[v] = kn[rs[v]]
                Zr, Z0r = Z[rs], Z0[rs]
                filled = cn.fill(Z0r, Zr, k_, net.uv, Fp, v)
                free_ = v[~k_[v]]
                Z[rs[free_]] = filled[free_]
            self.log(f"chains after hang {rnd}: {rd2}")
        self.reads["hang_last_lengths"] = {"all": rd, "chains": rd2}
        self.X = Z[rs]
        self.reads["threads"] = th.report(self.X)
        self.reads["chains"] = self.chain_read(self.X)
        self.reads["seam_gap_mm"] = round(net.seam_gap(self.X), 3)
        return self.X


def job_dir(model: str, garment: str, wear: str) -> Path:
    from . import store
    d = store.HOME / model / "chain" / f"{garment}_{wear}"
    d.mkdir(parents=True, exist_ok=True)
    return d


RUNNING = ("queued", "building", "resuming", "built", "hanging", "hung")  # stages a live worker is in; the rest are its ends
BUILD_GB = 8.0  # the build's real peak (rss read per job: status "peak_gb"); the hang declares its own kind


def job_key(spec: dict, garment: str, wear: dict, blockin: dict | None = None) -> str:
    """What a job answers for: the body, this garment, the wear (from the style plan, T7), the plan's block-in (step 2's
    SDF garment as worn: the build STARTS from it, F10) and the build's code (store.BUILD_VERSION: a job built by older
    stages is built again; C280). Another garment on the model doesn't change it."""
    from . import store
    rest = {k: v for k, v in spec.items() if k != "cloth"}
    wear = {k: v for k, v in wear.items() if k not in ("waive", "resume")}  # (a waiver re-reads the saved build, T2)
    parts = [rest, spec["cloth"][garment], wear, store.BUILD_VERSION] + ([blockin] if blockin is not None else [])
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def write_status(d: Path, **kw):
    p = Path(d) / "status.json"
    st = json.loads(p.read_text()) if p.exists() else {}
    st.update(kw)
    t = Path(d) / f"status.{os.getpid()}.tmp"
    t.write_text(json.dumps(st, default=str))
    t.replace(p)


_status = write_status


def status(d: Path) -> dict:
    p = Path(d) / "status.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _alive(pid) -> bool:
    try:
        text = Path(f"/proc/{int(pid)}/status").read_text()
    except (OSError, TypeError, ValueError):
        return False
    return not re.search(r"^State:\s+Z", text, re.M)  # (a dead child the server hasn't reaped is not a worker)


def live_status(d: Path) -> dict:
    """status(), with a worker that died mid-job (OOM kill, reboot) read as failed: its stage would say running for ever."""
    st = status(d)
    if st.get("stage") in RUNNING and "pid" in st and not _alive(st["pid"]) and status(d).get("stage") in RUNNING:
        tail = (Path(d) / "worker.log").read_text(errors="replace")[-300:] if (Path(d) / "worker.log").exists() else ""
        write_status(d, stage="failed", error=f"the worker died at stage {st['stage']} ({tail.strip() or 'no output'})")
        st = status(d)
    return st


def elapsed(st: dict) -> int:
    return int(time.time() - float(st.get("t0") or time.time()))


def gr_from_chain(model: str, garment: str, wear: str, d: Path, st: dict) -> str:
    try:
        from . import garment_record as gr
        return gr.from_chain(model, garment, wear, d, st)
    except Exception as e:  # (the record never breaks a build)
        return f"record: not written: {type(e).__name__}: {e}"


def _peak_gb() -> float:
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
