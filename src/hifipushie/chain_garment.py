"""CHAIN GARMENT: a garment built from its pattern and a body, as chains of the pattern's own lengths (chain_net.py). The
one way a garment is started (Joe 2026-11-01: "that should be the only path available to the agent for starting
clothing"). Input: a pattern (the flat mesh dict) and a body (V, T, at). A fit's positions are never read: Pattern
carries only PATTERN_KEYS, so a fit has no way in.

ROLES come from the pattern's construction, never from names (read_roles, chain_holds.read): a stiff piece with a "roll"
fold is a FALL; the wholly interfaced piece it is sewn to is its BAND; a stiff part sewn along the body cloth's neckline
with nothing on it is a STAND (chain_roles.neck_part); other wholly interfaced pieces closed on themselves are RINGS
(cuffs, waistbands); a soft piece sewn to itself is a TUBE (sleeves); other soft pieces are PANELS wrapped round the
torso. A closure between two pieces is the FRONT. A role the core can't build is refused by name; no fallback path.

THE ORDER (R3c, C399; each from a visible fault, C259-C262): ONE sequence for every garment, read from what holds what
(chain_holds.read): stiff parts first, in Holds' order, each resting on what is under it; soft parts hang from them,
never the reverse. run() branches on no worn state and no role (tests/test_chain_one_build.py reads its source).
THE STATE (T7 C287, R1 C391, R3c C399; chain_plan.py, closure_ties.py): the worn state is only which closure pairs are
tied (step 2's ties): any set, none included. A tied pair is held a layer apart (a zip's teeth edge to edge); an edge
neither sewn nor tied is FREE: its own lengths and the body as a floor, nothing else (an open front's edges lie where
their cloth reaches). wear["state"] is a derived label (the job's directory, the texts); the build never reads it. The
plan's bend targets (collar spread) are the stages' targets. Draped pieces (step 1's hang "draped") are still their own
input, chain_drape: R3e folds them into this sequence.
1. A STIFF PART ON THE NECKLINE (rest_part): the ring of its own neckline length resting on the high points
   (chain_rest.rest_ring, C280): chains + exact lines, stiff all along, keeps its own shape (can't sink in, a light rest
   pull, never follows the surface). With a part sewn on top (a fall) its top is that seam (band_closed); nothing on top,
   it stands with its own top edge (stand_ring). Its own closure TIED: closed on its own button. UNTIED (band_untied): the
   pressed curve kept round the back, relaxed straight past the side necks, started swung open; the sewn fronts held to
   the topmost TIED front pair (started on the torso: nothing soft is built yet), and with none tied held by nothing.
   A stand's neck ends meet where the front's top pair is tied. Worn straight = mirror symmetric.
2. A PART RESTING ON A PART (a fall on its band): roll line, outer edge, ends: exact chains; lines across may shorten
   where the leaf curves, full width where it lies flat at the back; the point's triangle is rigid. Outside faces out.
   Its band untied: its points spread as the plan's bend says.
3. A STIFF PART RESTING ON THE BODY ELSEWHERE (RINGS): a stiff circle of its own closed length, where the tube's own length
   reaches, clear of the body (a centre ring round the torso: chain_loops.body_ring).
4. SOFT NETWORK: panels wrapped on a garment-sized ring per height (the torso's convex section, offset until its perimeter
   is the pattern's width there), each at its own width; tubes on the limb's axis at the pattern's width. Sewn points one
   node, stiff nodes held, tied pairs tied, chains + lines projected with the body as a floor: the start is legal by
   construction, nothing is pushed afterwards. Plies follow their hosts (chain_holds.place_plies).
5. PLACKETS (fold_plackets): only through a TIED pair an untied band was held to: a stiff strip folds out of plane along
   a solved crease through it (in-plane rotation stretches) so its top reaches the band's ends apart; over side over
   under side. No tied pair held apart (band done up, or nothing tied): no fold. Then a fall rests on the soft cloth
   under it, and the soft cloth is solved again under the fall.
5a. THE CREASE TURN (chain_crease.py, R3d C401): every fold step 2 plans (wear["folds"]: on, fold, turn_deg, lies_on) that
   no other stage turns, after the soft cloth is laid: the piece split along the draft's own fold row; the side with less
   sewn length turns about the row by turn_deg (a roll round its radius, a press sharp), lies on its lies_on (its own other
   side or another piece a LAYER out, the body at GAP, or free), then the net's projection; plies and the sewn cloth
   beside it follow. Gated per fold (stage "crease"). A stiff part's roll (a fall) stays stage 2's (R3e folds it in).
6. SURFACES fill between fixed chains (fold turn: a half circle of the pattern's radius round the band top; the band stays
   under the fall; corner patch at the leaf's neck end).
7. STRUCTURE (chain_structure.py, C279): the BUILD is measured beside the reference before any hang: the collar's
   clearance under the jaw, its top line's tilt, the points' spread and drop, the leaves lying; the front meeting and
   straight, the V (open); the hem level; sleeve length and cuff ease. Each row: target, source, and on FAIL what to
   change. The job ends "structure_failed" with its rows unless every row passes or is waived by name with a reason. The
   hang adds folds by design: a hung result never judges a structure fault, nor hides one.
7a. PRE-SIM APPROVAL (chain_presim.py): after a pass the job stops at "awaiting_approval" until the garment record's step
   7a is approved (or HIFIPUSHIE_PRESIM_APPROVAL=optional); the same call then resumes from built.pkl, never rebuilds.
8. HANG (hang()): the soft cloth under gravity in ZOZO, stiff parts held; lengths have the last word afterwards. Its gate:
   no face past the thread cap (chain_presim.threads_gate).
   The collider is the whole body: nothing is cut from it. An illegal start is a build fault and is refused by name.
   Worn over another garment (step 1's "over", chain_layers.py + chain_press.py, T12): the body + that garment's
   thickness + its stiff parts and details; the garment under is then fitted inside this one (visible parts by default).

Every stage ends in chain_net.project; Build.reads holds the numbers; a length that can't hold raises ChainRefused naming
the piece and the line and what to do next."""
from __future__ import annotations

import json
import os
import time

import numpy as np

from . import chain_net as cn
from .chain_net import BendSolve, Contact, Network, Threads, project, unit  # noqa: F401  (re-exported)
# (R3a: the build split by responsibility; chain_garment stays THE import point, so every name is re-exported here)
from .chain_core import (CAP, FALL_GAP, GAP, LAYER, MAX_FREE_PCT, OPEN_SPREAD, SEAM_LINK_MM, PATTERN_KEYS, REST,  # noqa: F401
                         RING_GAP, RING_H, SHEAR_LIMIT, UNDER, Body, ChainRefused, Pattern, Roles, _keep_roots,
                         _neighbours, cn_vnormals, hand_of, joined_faces, pattern_from_mesh, read_roles, zozo_legal)
from .chain_band import BandStages
from .chain_fall import FallStages
from .chain_soft import LimbAxis, SoftStages, TorsoRings, blockin_of, uses_blockin_start  # noqa: F401
from .chain_stiff import StiffStages
from .chain_jobs import (BUILD_GB, RUNNING, HangJob, _alive, _peak_gb, _status, elapsed,  # noqa: F401
                         gr_from_chain, job_dir, job_key, live_status, status, write_status)
from .chain_render import render_views  # noqa: F401


class Build(BandStages, FallStages):
    """One garment build. X: per vertex; sewn groups share a position. reads: what each stage measured."""

    def __init__(self, pattern: Pattern, body: Body, wear: dict | None = None, log=print):
        self.pat, self.body, self.log = pattern, body, log
        from .chain_plan import apply_tie, ties_of_wear
        from .chain_roles import neck_part
        self.wear = ties_of_wear({"state": "closed", "spread": OPEN_SPREAD, **(wear or {})})  # (no record: wear as ties)
        self.net = Network(pattern.M, pattern.stiff, pattern.bend)
        self.roles = read_roles(self.net)
        self.holds = self.roles.holds  # (R3b chain_holds: plies follow their host, floating layers stiffen theirs)
        self.X = np.zeros((self.net.n, 3))
        self.held = np.zeros(self.net.n, bool)
        self.axes: dict = {}
        self.reads: dict = {"seam_truing": self.net.seam_mismatch()}
        self.neck = neck_part(self)  # (R3c: the stiff part on the neckline, by construction: chain_roles.neck_part)
        # (R1 C391, R3c C399: step 2's ties, exactly the fastenings the plan does up; any set, none included)
        self.roles.front = apply_tie(self.roles.front, self.wear.get("front_tie"), self.net.uv)
        self.roles.band_closure = apply_tie(self.roles.band_closure, self.wear.get("band_tie"), self.net.uv)
        # its own closure done up: as its tie says; no tie in the wear (no record, wear "closed") is done up, as it always
        # was (the pattern's own drawn state of the band closure was never the wear)
        bc, bt = self.roles.band_closure, self.wear.get("band_tie")
        self.band_tied = bool(bc) and (bt is None or bt.get("legacy") == "closed" or all(bc.get("closed") or [True]))
        self.band_hold = None  # (the topmost tied front pair an untied band is held to: chain_band.band_untied)
        m = float(self.net.link_cut[:, 1].sum()) and self.net.seam_mismatch()["max_pct"]
        if self.reads["seam_truing"]["max_mm"] > SEAM_LINK_MM:
            raise ChainRefused(f"a seam's two sides differ by {self.reads['seam_truing']['max_mm']} mm over one link: "
                               "next: true the pattern (pattern_check, alter_pattern); a chain can't be two lengths")
        self._mirror()

    # ---- helpers
    def _mirror(self):
        net = self.net
        pairs, solo = [], []
        for n in net.names:
            if n.endswith(".L"):
                r = n[:-2] + ".R"
                if r in net.names:
                    u = net.uv[net.verts(n), 0]
                    ur = net.uv[net.verts(r), 0]
                    same = abs(u.mean() - ur.mean()) < 0.5 * max(abs(u.mean()), abs(ur.mean()), 1e-3) or \
                        (abs(u.mean()) < 0.02 and abs(ur.mean()) < 0.02)
                    pairs.append((n, r, 1.0 if same else -1.0))
            elif not n.endswith(".R"):
                solo.append(n)
        self.mir = cn.mirror_map(net, pairs, solo)

    def _set(self, v, P):
        """Set positions of vertices v (sewn partners follow through the root)."""
        r = self.net.root[np.asarray(v, np.int64)]
        self.X[r] = P
        self.X[np.isin(self.net.root, r)] = self.X[self.net.root[np.isin(self.net.root, r)]]

    def _sync(self):
        self.X = self.X[self.net.root]

    def sewn_with(self, a: str, b: str) -> dict:
        """vertex of a -> vertex of b, for a seam between pieces a and b."""
        pa, pb = self.net.pid(a), self.net.pid(b)
        out = {}
        for x, y in self.net.sew:
            if self.net.piece[x] == pa and self.net.piece[y] == pb:
                out[int(x)] = int(y)
            elif self.net.piece[y] == pa and self.net.piece[x] == pb:
                out[int(y)] = int(x)
        return out

    def order_x(self, v):
        v = np.asarray(sorted(set(int(q) for q in v)), np.int64)
        return v[np.argsort(self.net.uv[v, 0])]


class GarmentBuild(SoftStages, StiffStages, HangJob, Build):
    """All stages. run() -> self.X (the chain build, before the hang)."""

    # ---- the whole build (the stages: chain_band, chain_fall, chain_soft, chain_stiff; the hang: chain_jobs)
    def run(self):
        """THE ONE BUILD (R3c, C399; THE ORDER): stiff parts in chain_holds' order, each placed by what it rests on and
        tied as its own tie says; then the soft cloth, tied exactly where step 2 ties it (any set of pairs, none
        included), every edge neither sewn nor tied free; plies follow their hosts. No branch on a worn state or a role.
        Draped pieces (step 1's hang "draped") are still their own input, chain_drape (R3e folds them in)."""
        t0 = time.time()
        if getattr(self, "drape", None):  # (T13 C297: an INPUT, not a mode: step 1's draped pieces, R3e folds them in)
            from .chain_drape import build_drape
            build_drape(self, t0)
        else:
            self.stiff_rest()  # 1-3: bands, stands, falls, rings, each resting on what is under it, tied as its tie says
            self.reads["stiff_s"] = round(time.time() - t0, 1)
            self._hold_tied()  # the tied pair an untied band was held to stays there (none: nothing more is held)
            self.soft_net()  # 4: the soft cloth, tied exactly where step 2 ties it; free edges free
            self._fold_then_rest()  # 5: plackets fold through tied pairs only; a fall rests on the cloth under it
            self.crease_turn()  # 5a: every planned fold no other stage turns, to its turn_deg, on its lies_on
        self.reads["chains"] = self.chain_read(self.X)
        self.reads["seam_gap_mm"] = round(self.net.seam_gap(self.X), 3)
        self.reads["build_s"] = round(time.time() - t0, 1)
        return self.X

    def crease_turn(self):
        from .chain_crease import turn_all
        return turn_all(self)

    def _hold_tied(self):
        """The topmost tied front pair stays where the untied band was held to it: left free, the soft cloth carried it
        10 mm down and 14 mm out, the fronts' neck-to-button reach ran 12.6 mm past its cut and the plackets tore (T7).
        No such pair (the band done up, or nothing tied): nothing extra is held."""
        if self.band_hold is not None:
            self.extra_held = np.zeros(self.net.n, bool)
            self.extra_held[list(self.band_hold)] = True

    def _fold_then_rest(self):
        far_z = self.fold_plackets()
        self._rest_fall(far_z)
        self.stay_v = None
        self.thread_read_all()

    # ---- plies follow their host after every stage that places one (R3b, chain_holds.place_plies)
    def stiff_last(self):
        super().stiff_last()
        self._plies()

    def rings(self, only=None):
        super().rings(only)
        self._plies()

    def soft_net(self, start=None, far_z=None):
        out = super().soft_net(start, far_z)
        self._plies()
        return out

    def _plies(self):
        if self.holds is not None and (self.holds.plies or self.holds.layers):
            from .chain_holds import place_plies
            place_plies(self)
            if self.holds.layers:  # (not built: they stiffen their host, R3c gives them their effect)
                self.reads["layers"] = {k: {"stiffens": v, "built": False} for k, v in self.holds.layers.items()}

    def chain_read(self, X) -> dict:
        """Chains at X. A soft link with both ends sewn to a stiff part is gathered into it (a sleeve into its cuff):
        it may only be shorter; those are read apart."""
        net = self.net
        held = np.zeros(net.n, bool)
        held[net.root[self._stiff_mask()]] = True
        both = held[net.link_i] & held[net.link_j]
        rep = net.chain_report(X)
        l = np.linalg.norm(X[net.link_j] - X[net.link_i], axis=1)
        e = np.abs(l / np.maximum(net.link_L, 1e-9) - 1) * 100
        free = ~both
        rep["free_worst_pct"] = round(float(e[free].max()), 3) if free.any() else 0.0
        rep["free_p99_pct"] = round(float(np.percentile(e[free], 99)), 3) if free.any() else 0.0
        k = int(np.argmax(np.where(free, e, -1)))
        c = int(np.where(net.link_of_chain == k)[0][0])
        rep["free_worst_line"] = (f"{net.names[net.chain_piece[c]]} {'fold line' if net.chain_kind[c] else 'edge'} at flat "
                                  f"({net.uv[net.chain_v[c, 0], 0]:.3f}, {net.uv[net.chain_v[c, 0], 1]:.3f})"
                                  + self._near_point(int(net.link_i[k]), net.names[net.chain_piece[c]]))
        over = (l - net.link_L) / np.maximum(net.link_L, 1e-9) * 100
        rep["gathered_links"] = int(both.sum())
        rep["held_longest_over_pct"] = round(float(over[both].max()), 2) if both.any() else 0.0
        from .chain_loops import held_read
        rep.update(held_read(self, X, both, e, over))  # (F1: held links are lengths too)
        return rep

    def _near_point(self, v: int, piece: str) -> str:
        """(C278) the worst link named by the pattern point nearest it on its piece: flat coordinates alone don't say
        where to alter_pattern."""
        net = self.net
        pts = [(n.split(":", 1)[1], i) for n, i in (net.M.get("points") or {}).items()
               if isinstance(i, (int, np.integer)) and n.startswith(piece + ":")]
        if not pts:
            return ""
        d = [float(np.linalg.norm(net.uv[i] - net.uv[v])) for _, i in pts]
        j = int(np.argmin(d))
        return f", {d[j] * 1000:.0f} mm from {piece}:{pts[j][0]}"

    def gate_lengths(self):
        """Lengths have the last word: a free chain link past MAX_FREE_PCT is refused by piece and line."""
        c = self.chain_read(self.X)
        self.reads["chains"] = c
        if c["free_worst_pct"] > MAX_FREE_PCT:
            raise ChainRefused(f"a length can't hold: {c['free_worst_line']} is {c['free_worst_pct']} % off its cut (limit "
                               f"{MAX_FREE_PCT} %). next: the pattern can't make this line on this body: look_pattern, then "
                               "alter_pattern at that line, pattern_check, chain_garment again")
        if c.get("held_worst_pct", 0.0) > MAX_FREE_PCT:  # (F1: a link held at both ends is still a length)
            raise ChainRefused(f"a held length can't hold: {c['held_worst_line']} is {c['held_worst_pct']} % off its cut "
                               f"(limit {MAX_FREE_PCT} %). next: look_chain at that line; the stiff piece's cut can't take "
                               "this shape on this body: draft_pattern at that edge, chain_garment again")


# ---- the job: what the MCP tools run (a worker process, so a hang never blocks the server)
def load_garment(model: str, garment: str, spec: dict | None = None) -> tuple:
    """(Pattern, Body, fabric) of a saved garment: the draft meshed flat with fold lines as edges (cloth.build place_only);
    positions in the result are dropped by Pattern, never read."""
    from . import bending, cloth, pattern_form as pf, store
    spec = spec or store.load(model)
    g = json.loads(json.dumps(spec["cloth"][garment]))
    g["mesh_refine"] = pf.form_refine(g)
    src, _ = pf.form_source(model, garment, spec, g)
    res = cloth.build(cloth._garment_for_sim(g), src, f"{model}:{garment}", log=lambda *_: None, place_only=True)
    M, B = res["mesh"], res["pieces"]
    st = cloth.interfacing(B, M)
    # a stiff ring keeps a smooth section: its chords must not sag into the limb (L^2 / 8R over a 25 mm wrist)
    rings = [n for i, n in enumerate(M["names"]) if st[np.asarray(M["piece"]) == i].mean() > 0.95 and n not in ("collar", "stand")]
    rings = [n for n in rings if not any(f.get("piece") == n and f.get("kind") == "roll" for f in M.get("folds") or [])]
    if rings:
        g["mesh_refine"] = list(g["mesh_refine"]) + [{"piece": rings, "h": RING_H}]
        res = cloth.build(cloth._garment_for_sim(g), src, f"{model}:{garment}", log=lambda *_: None, place_only=True)
        M, B = res["mesh"], res["pieces"]
    radius = {f["name"]: float(f["radius"]) for f in (B.get("folds") or []) if isinstance(f, dict) and f.get("radius") and f.get("name")}
    try:  # (F4: each piece's measurements and where step 3 took them: the build's starts, piece_start.py)
        from . import garment_record as gr, piece_start
        st_ = gr.load(model, garment)["steps"]
        piece_start.attach(M, st_.get("3", {}).get("output") or {}, st_.get("4", {}).get("output") or {})
    except (FileNotFoundError, KeyError):
        M["starts"] = {}
    pat = pattern_from_mesh(M, cloth.interfacing(B, M), bending.weights(B, M, g), radius)
    body = Body(np.asarray(res["body"].V, float), np.asarray(res["body"].T, np.int64),
                {k: np.asarray(v, float) if np.ndim(v) else float(v) for k, v in res["body"].at.items()})
    return pat, body, res.get("fabric") or cloth.fabric(g)


def worker(model: str, garment: str, wear: dict):
    """Build, structure, pre-sim approval (step 7a, chain_presim.py), then hang. Every stage writes its numbers to
    status.json; a refusal is a result, not a crash. wear["resume"]: the build is loaded from built.pkl, never rebuilt."""
    from . import chain_drape as cd, chain_presim as cp, chain_structure as cs, resources, zozo_hang as zh
    d = job_dir(model, garment, wear["state"])
    resume = wear.get("resume") or ""  # ("approved" / "waiver": from built.pkl, see chain_presim)
    _status(d, stage="resuming" if resume else "building", pid=os.getpid())
    note = lambda m: _status(d, note=str(m)[:200])
    waive = dict(wear.get("waive") or {})
    wear = {k: v for k, v in wear.items() if k not in ("waive", "resume")}
    import pickle
    try:
        if resume:  # (approved, or a waiver: the saved build, as it was)
            b, r = cp.load_build(d)
            pat, body, fabric = b.pat, b.body, r.get("fabric") or {}
        else:
            # kind named: a job of no kind is counted as holding the GPU (resources._holds_gpu), and a CPU-only build
            # held every render behind it for its whole run; the hang claims the GPU itself (zozo_hang, gpu=True)
            with resources.heavy(f"chain build {model}:{garment} {wear['state']}", gb=BUILD_GB, kind="chain_build",
                                 log=note):
                pat, body, fabric = load_garment(model, garment)
                def _build(lb):  # (T13: the plan's draped pieces, set before the run whatever builds it)
                    gb = GarmentBuild(pat, lb, wear, log=lambda *_: None)
                    gb.drape = cd.info(model, garment, gb.net) if hasattr(gb, "net") else None
                    gb.blockin = ((cs.load_plan(model, garment) or {}).get("style") or {}).get("blockin")  # (F9)
                    return gb
                from . import chain_press as cpr
                if wear.get("under") and cpr.mode(model, garment)[0] == "visible":  # (hidden decided first: C296)
                    from . import chain_hidden as ch
                    b, body = ch.build_over(model, garment, body, wear["under"], _build, log=note)
                else:
                    if wear.get("under"):  # (worn over another garment, layers "full": everything of it pushes, T12)
                        from . import chain_layers as cl
                        body = cl.layered_body(model, garment, body, wear["under"], log=note)
                    b = _build(body)
                    b.run()
            bid = cp.save_build(d, b, pat, body, fabric)
            _status(d, stage="built", reads=b.reads, note="", build_s=elapsed(status(d)), peak_gb=round(_peak_gb(), 1),
                    build_id=bid, build_threads=b.reads.get("threads"))
        sc = status(d).get("structure") if resume == "approved" else None  # (approved as read: not read again)
        if not sc:
            sc = cs.check(b.X, pat.M, body.V, body.T, body.at, dict(wear, drape_reads=cd.build_reads(b)),
                          cs.load_plan(model, garment), waive)  # (C279, C286; T13: draped rows wait for the hang)
            sc["reads"].pop("front_gap_profile", None)
        _status(d, structure=sc)
        from . import chain_layers as cl  # (inside the garment under it, then the lengths: T9)
        cl.gate(b, body, put=lambda **kw: _status(d, **kw), refused=ChainRefused, d=d)  # (a refusal is answered first; structure rows stay beside it)
        if not cs.passed(sc):
            _status(d, stage="structure_failed")
            return
        gr_msg = gr_from_chain(model, garment, wear["state"], d, dict(status(d), stage="presim"))
        go, why, msg = cp.gate_presim(model, garment, wear["state"], d, status(d))
        if not go:  # (step 7a: nothing is hung that wasn't approved built)
            sheet = None
            try:
                from . import garment_record as gr
                sheet = str(gr.sheet(model, garment))
            except Exception:  # (the sheet is a look; its failure never loses the build)
                pass
            _status(d, stage=cp.AWAIT, presim=why, sheet=sheet, record="; ".join(m for m in (gr_msg, msg) if m))
            return
        jd = b.write_job(d / "zozo", fabric, name=f"chain:{model}:{garment}")
        zh.write_chain_gate(jd, sc["verdict"], why)  # (the remote route's gate: this job's structure PASS + step 7a)
        _status(d, stage="hanging", reads=b.reads, presim=why)
        out, hl = zh.run(jd, log=note, timeout=3000)
        _status(d, hang_ran=next((m.split(": ", 1)[1] for m in (hl or []) if str(m).startswith("zozo hang: ")), None))
        X = b.finish_hang(out["V"] if hasattr(out, "keys") else out[0])
        pickle.dump({"X": X, "M": pat.M, "bV": body.V, "bT": body.T, "reads": b.reads}, open(d / "final.pkl", "wb"))
        _status(d, stage="hung", reads=b.reads, note="")  # (a refusal below still leaves the hung result to look at)
        b.gate_lengths()
        if getattr(b, "drape", None):  # (T13: step 8's gate gains the draped rows, read on the hung cloth)
            hs = cd.hang_check(X, pat.M, body, cs.load_plan(model, garment), b.drape, waive)
            _status(d, hang_structure=hs)
            if not cs.passed(hs):
                _status(d, stage="hang_rows_failed", reads=b.reads)
                return
        _status(d, stage="done", reads=b.reads)
    except (ChainRefused, cd.DrapeRefused) as e:
        _status(d, stage="refused", refused=str(e))
    except Exception as e:  # (a crash is reported as one, with what it was doing)
        if type(e).__name__ == "StageFailed":  # (F5: a stage's gate ended the build where it failed, cheapest first)
            from . import chain_stages as cst
            cst.on_fail(d, e, lambda **kw: _status(d, **kw), log=note)
            return
        if type(e).__name__ in ("ChainRefused", "DrapeRefused"):  # (F1: the worker runs as __main__, so a refusal
            _status(d, stage="refused", refused=str(e))       # raised in chain_roles / chain_loops is another class)
            return
        import traceback
        _status(d, stage="failed", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-1500:])
    finally:  # (steps 5, 6 and 8 of the garment record; a refusal of the record's order is noted, the job stands)
        if status(d).get("stage") != cp.AWAIT:
            msg = gr_from_chain(model, garment, wear["state"], d, status(d))
            if msg:
                _status(d, record=msg)


if __name__ == "__main__":
    import sys
    worker(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
