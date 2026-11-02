"""LAYERING (T9, C292): a garment built over another garment. Not a step of its own: step 5 (chains in 3D) run on the
garment underneath instead of the body alone.

DECLARED in the plan: the over garment's step 1 (parts) names what it is worn over, `"over": ["shirt"]` (garment names
on the same model). garment_plan validates it (check_over): each name is a garment of the model with a record, not the
garment itself, and not worn over this one (no loop).

THE ORDER (under_for, at chain_garment's call, a refusal at once; T12): the over garment's build needs each under
garment's step 4 (pattern), step 1 (parts: which are stiff) and a BUILD of it (built.pkl: not approved; its details.pkl when
placed). The under garment's final fit comes AFTER the over garment's build (chain_press.fit_unders, in the gate) and both
are approved together at the over garment's step 7a. Development setting HIFIPUSHIE_LAYER_UNDER=built: an under garment
whose record lacks steps 1 / 4 is accepted, flagged in the answer (a proof on an unfinished record; never for an agent).
The under garment's build id is part of the over garment's job key: a rebuilt shirt rebuilds the jacket.

THE COLLIDER (LayeredBody, a chain_garment.Body; T12, C294): the over garment keeps ITS pattern's shape: the body offset
by the under garment's THICKNESS where its soft cloth covers the body (never its shape: T9 inflated the body over the
shirt's loose build and the jacket ballooned), plus its STIFF parts (the pieces its build holds: band, fall, cuffs) and its
SOLID details (details.pkl: buttons), which really push an outer garment out. One closed surface, read as a body by every
stage, the torso rings, ZOZO and the structure gate.

THE UNDER GARMENT INSIDE (chain_press.py): fitted inside the over build after it, lengths exact, between the body and the
over garment's inner side; visible-only by default (hidden cloth dropped, its edge held), the whole of it pressed for the
plan's step 2 layers {"mode": "full", why}.

THE GATE (gate): before the length gate, anything of the over garment inside an under one (its midsurface crossed, or
inside a solid detail) is refused by name: the piece, how many points, how deep, at which body level, and what to change
(ease at that level in the draft; the girth to add). reads(): the closest distance over-to-each-under cloth and
over-to-its-details, written to the job's status ("layers").
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from . import chain_net as cn
from .chain_garment import GAP, Body, ChainRefused, zozo_legal
from .chain_net import Contact, unit

SETTING = "HIFIPUSHIE_LAYER_UNDER"  # "approved" (default) | "built" (development: any saved build, flagged UNAPPROVED)
THICK_DEFAULT = 0.0005  # m: an under cloth with no thickness in its reading
INSIDE_TOL = 0.0  # m: a point of the over garment past the under's midsurface is inside it
DETAIL_REACH = 0.01  # m: a solid detail decides only this near it (a far point's side off one facet is a guess)
REACH = 0.05  # m: a layer is queried only for points this near its box
BEHIND = 0.002  # m: "inside" an open cloth is only the room between it and the body (+ this): deeper is the body's side

class LayerRefused(ValueError):
    """The layering can't be built: the message names the under garment, what is missing and the next call."""


# ---------------------------------------------------------------- the plan
def worn_over(model: str, garment: str) -> list:
    """The garments this one is worn over: its step 1's "over" (step 2's when step 1 has none)."""
    from . import garment_record as gr
    rec = gr.load(model, garment)
    for sid in ("1", "2"):
        o = (rec["steps"][sid].get("output") or {}).get("over")
        if o:
            return list(o)
    return []


def check_over(model: str, garment: str, over) -> list:
    """Validate a plan's "over": a list of garment names of this model, each with a record, not itself, no loop.
    Returns the list; raises LayerRefused naming each fault."""
    from . import garment_record as gr, store
    if over in (None, []):
        return []
    if not isinstance(over, list) or not all(isinstance(x, str) and x.strip() for x in over):
        raise LayerRefused('over: a list of garment names this one is worn over, e.g. ["shirt"]')
    cloth = (store.load(model).get("cloth") or {}) if store._dir(model).exists() else {}
    bad = []
    for u in over:
        if u == garment:
            bad.append(f"over: {u!r} is this garment")
        elif u not in cloth:
            bad.append(f"over: {u!r} is not a garment of {model} (garments: {', '.join(sorted(cloth)) or 'none'}): "
                       "design it first (the garment underneath is built first)")
        elif not gr.path(model, u).exists():
            bad.append(f"over: {u!r} has no garment record: garment_plan step='read' for it first")
        elif garment in worn_over(model, u):
            bad.append(f"over: {u!r} is itself worn over {garment!r} (a loop)")
    if bad:
        raise LayerRefused("; ".join(bad))
    return list(over)


# ---------------------------------------------------------------- the order
def _under_job(model: str, under: str) -> Path:
    from . import chain_garment as cg, chain_plan, chain_structure as cs
    wear = chain_plan.planned_wear(cs.load_plan(model, under), None, None)["state"]
    return cg.job_dir(model, under, wear)


def under_for(model: str, garment: str) -> dict:
    """{under: {"job", "surface": hung|built, "build_id", "approved", "details"}} for each garment this one is worn over
    ({} when none). Raises LayerRefused when an under garment's build isn't there or isn't approved (see THE ORDER)."""
    from . import chain_garment as cg, garment_record as gr
    over = worn_over(model, garment)
    if not over:
        return {}
    check_over(model, garment, over)
    dev = os.environ.get(SETTING, "approved") == "built"
    out = {}
    for u in over:
        d = _under_job(model, u)
        st = cg.status(d)
        built = (d / "built.pkl").exists()
        rs = gr.states(gr.load(model, u))
        miss = [f"its step {k} ({w}) is {rs[k]['status']}" for k, w in (("1", "parts: which are stiff"), ("4", "pattern"))
                if rs[k]["status"] not in ("done", "approved")]
        ok = not miss
        if not built or (miss and not dev):
            why = "no build" if not built else "; ".join(miss)
            raise LayerRefused(
                f"{garment} is worn over {u}: {u}'s pattern (step 4), its parts (step 1) and a build of it come first (its "
                f"build need not be approved: it is fitted inside {garment} after {garment}'s build, and both are approved "
                f"together at {garment}'s step 7a); {why} (job {d}, stage {st.get('stage', 'none')}).\nnext: "
                f"call_tool(\"chain_garment\", {{\"name\": \"{model}\", \"garment\": \"{u}\"}}); then this call again")
        out[u] = {"job": str(d), "surface": "built", "build_id": str(st.get("build_id") or ""),
                  "approved": bool(ok), "details": (d / "details.pkl").exists()}
    return out


# ---------------------------------------------------------------- the collider
def thickness(model: str, garment: str) -> float:
    """m: the thickest cloth of a garment's reading (step 0)."""
    from . import garment_record as gr
    cl = (gr.load(model, garment)["steps"]["0"].get("output") or {}).get("cloth") or {}
    t = [float(c["thickness_mm"]) * 1e-3 for c in cl.values() if isinstance(c, dict) and c.get("thickness_mm")]
    return max(t) if t else THICK_DEFAULT


def outward(X, F, body_contact) -> np.ndarray:
    """F with every face turned to face away from the body (its outward side is the side cloth over it must be on)."""
    F = np.asarray(F, np.int64).copy()
    tri = np.asarray(X, float)[F]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n = body_contact.query(tri.mean(1))[1]
    flip = (fn * n).sum(1) < 0
    F[flip] = F[flip][:, [0, 2, 1]]
    return F


def closed_outward(V, F) -> np.ndarray:
    """F of closed solids (several per mesh) turned outward: each connected solid's signed volume positive."""
    V, F = np.asarray(V, float), np.asarray(F, np.int64).copy()
    root = cn.union_roots(len(V), cn.edges_of(F))[F[:, 0]]
    vol = np.einsum("ij,ij->i", V[F[:, 0]], np.cross(V[F[:, 1]], V[F[:, 2]]))
    for r in np.unique(root):
        m = root == r
        if vol[m].sum() < 0:
            F[m] = F[m][:, [0, 2, 1]]
    return F


def _bary(Q, A, B, C):
    v0, v1, v2 = B - A, C - A, Q - A
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    den = np.where(np.abs(d00 * d11 - d01 * d01) > 1e-30, d00 * d11 - d01 * d01, 1e-30)
    v = (d11 * d20 - d01 * d21) / den
    w = (d00 * d21 - d01 * d20) / den
    return np.c_[1 - v - w, v, w]


class Layer:
    """One under surface: open cloth (covers a point unless its closest place is on the open edge) or closed solids."""

    def __init__(self, name: str, kind: str, V, F, gap: float, body_contact=None, role: str = "stand"):
        """role (the collider, LayeredBody): "cover" pushes by gap where it covers the body (soft cloth: its thickness),
        "stand" by how far it stands off + gap (stiff parts, solid details)."""
        self.name, self.kind, self.gap, self.bc, self.role = name, kind, float(gap), body_contact, role
        self.c = Contact(V, F)
        self.lo, self.hi = self.c.V.min(0) - REACH, self.c.V.max(0) + REACH
        if kind == "cloth":
            F = self.c.T
            be = {tuple(e) for e in cn.boundary_edges(F).tolist()}
            opp = [(1, 2), (2, 0), (0, 1)]  # the edge opposite each corner
            self.open = np.array([[tuple(sorted((int(f[a]), int(f[b])))) in be for a, b in opp] for f in F], bool)

    def query(self, P):
        """(signed distance, normal, covered) of P against this surface; points far from its box: not covered."""
        P = np.asarray(P, float)
        d, n, cov = np.full(len(P), np.inf), np.zeros((len(P), 3)), np.zeros(len(P), bool)
        m = ((P >= self.lo) & (P <= self.hi)).all(1)
        if m.any():
            d[m], n[m], cov[m] = self._query(P[m])
        return d, n, cov

    def _query(self, P):
        c = self.c
        _, J = c.kd.query(P, k=c.k)
        J = np.asarray(J).reshape(len(P), c.k)
        Pr = np.repeat(P, c.k, axis=0)
        t = c.T[J.ravel()]
        Q = cn._closest_on_tris(Pr, c.V[t[:, 0]], c.V[t[:, 1]], c.V[t[:, 2]])
        d = np.linalg.norm(Pr - Q, axis=1).reshape(len(P), c.k)
        r = np.arange(len(P))
        b = np.argmin(d, axis=1)
        j = J[r, b]
        Qb = Q.reshape(len(P), c.k, 3)[r, b]
        fn = c.fn[j]
        dv = P - Qb
        dist = d[r, b]
        s = np.where((dv * fn).sum(1) >= 0, 1.0, -1.0)
        n = np.where((dist > 1e-7)[:, None], unit(dv) * s[:, None], fn)
        if self.kind != "cloth":
            return s * dist, n, dist < DETAIL_REACH
        tri = c.V[c.T[j]]
        lam = _bary(Qb, tri[:, 0], tri[:, 1], tri[:, 2])
        cov = ~((lam < 1e-4) & self.open[j]).any(1)
        if self.bc is not None:  # (behind the cloth deeper than the cloth stands off the body: not between them)
            h = self.bc.query(Qb)[0]
            cov &= ~((s < 0) & (dist > np.maximum(h, 0.0) + BEHIND))
        return s * dist, n, cov


class LayeredBody(Body):
    """The body offset by what it wears, for the OVER garment's build (T12, C294): each body vertex pushed out along its
    normal by the room the under garment needs there:
      - where an under garment's SOFT cloth covers the body (its build mapped to the nearest body vertex, filled over the
        1-ring): its THICKNESS, not its shape (room(): both half thicknesses + ZOZO's reach + the under cloth once, or
        FOLDS times for layers "full"); a loose under build never inflates the over garment;
      - under its STIFF parts (interfaced: a band, a collar fall, a cuff; pieces held in its build): how far they stand off
        the body + both half thicknesses + the reach (a stiff part really pushes an outer garment out);
      - under its SOLID details (details.pkl: buttons): how far they stand off + the over's half thickness + the reach.
    One closed, well-oriented surface: every stage, the torso rings, ZOZO and the structure gate read it as a body (the
    stages keep GAP off it). at, body_V / body_T / body_contact (the body itself) are kept for the reads. fits: {under:
    Layer} the under garment's fit INSIDE the over garment (chain_press.fit_unders), what the gate reads.
    (T9 inflated the body over the under garment's whole surface: Joe: "the shirt is inflating the jacket".)"""

    def __init__(self, body: Body, layers: list, info: dict):
        self.body_V, self.body_T, self.at = body.V, body.T, body.at
        self.body_contact = body.contact
        self.layers, self.info, self.fits = layers, info, {}
        V, T = body.V, body.T
        self.kd = cKDTree(V)
        nb = _rings(T, len(V))
        push = np.zeros(len(V))
        for L in layers:  # (per layer: how far it stands off each body vertex, filled over the 1-ring, smoothed once)
            P = L.c.V[np.unique(L.c.T)]  # (only the layer's own faces' points: a stiff layer shares its garment's array)
            d = body.contact.query(P)[0]
            k = self.kd.query(P)[1]
            ok = d > 0
            f = np.zeros(len(V))
            np.maximum.at(f, k[ok], d[ok])
            for _ in range(2):  # (fill: a body vertex between two mapped ones)
                f = np.maximum(f, np.array([f[n].max() if len(n) else 0.0 for n in nb]))
            if L.role == "cover":  # (the soft cloth: its thickness where it covers, never its shape)
                p = np.where(f > 0, L.gap, 0.0)
            else:
                f = 0.5 * f + 0.5 * np.array([f[n].mean() if len(n) else 0.0 for n in nb])
                p = np.where(f > 0, f + L.gap - GAP, 0.0)
            push = np.maximum(push, p)
        self.push = push
        self.V = V + _vnormals(V, T) * self.push[:, None]
        self.T = T
        self.contact = Contact(self.V, self.T)


def _vnormals(X, F):
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    N = np.zeros_like(X)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    return unit(N + 1e-30)


def _rings(T, n) -> list:
    e = cn.edges_of(T)
    nb = [[] for _ in range(n)]
    for a, b in e.tolist():
        nb[a].append(b)
        nb[b].append(a)
    return [np.array(x, np.int64) for x in nb]


def welded(F, root) -> np.ndarray:
    """F on the sewn roots (a seam is not an open edge), degenerate faces dropped."""
    F = np.asarray(root)[np.asarray(F, np.int64)] if root is not None else np.asarray(F, np.int64)
    return F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]


def under_parts(r: dict):
    """(X, soft faces, stiff faces, the build or None) of an under garment's built.pkl: stiff = the pieces its build holds
    (band, fall, rings: cn roles from the pattern's declarations); without a saved build everything reads soft."""
    X = np.asarray(r["X"], float)
    b = r.get("build")
    root = getattr(getattr(b, "net", None), "root", None)
    F = welded(r["M"]["F"], root)
    if b is None:
        return X, F, F[:0], None
    st = np.isin(b.net.root, b.net.root[b._stiff_mask()])
    sf = st[F].all(1)
    return X, F[~sf], F[sf], b


def layered_body(model: str, garment: str, body: Body, under: dict, log=print) -> LayeredBody:
    """The collider of a garment worn over `under` (under_for's answer): the body + each under garment's thickness where
    it covers, its stiff parts and its solid details (LayeredBody)."""
    import pickle
    from . import chain_press as cpr, garment_details as gd
    layers, info = [], {}
    t_o = thickness(model, garment)
    mode = cpr.mode(model, garment)[0]
    for u, x in under.items():
        d = Path(x["job"])
        r = pickle.load(open(d / "built.pkl", "rb"))
        t_u = thickness(model, u)
        push, gap_out = cpr.room(t_u, t_o, mode)
        X, Fs, Fst, _ = under_parts(r)
        if len(Fs):
            layers.append(Layer(u, "cloth", X, outward(X, Fs, body.contact), push, body.contact, role="cover"))
        if len(Fst):
            layers.append(Layer(f"{u}:stiff", "cloth", X, outward(X, Fst, body.contact), gap_out, body.contact))
        dets = []
        if x.get("details") and (d / "details.pkl").exists():
            dp = gd.load_result(d / "details.pkl")
            meshes = dp.get("built") or {}
            Vs, Fs_, off = [], [], 0
            for n_, m in meshes.items():
                if m and len(m.get("F", [])):
                    Vs.append(np.asarray(m["V"], float))
                    Fs_.append(np.asarray(m["F"], np.int64) + off)
                    off += len(m["V"])
                    dets.append(n_)
            if Vs:
                V, F = np.concatenate(Vs), np.concatenate(Fs_)
                layers.append(Layer(f"{u}:details", "solid", V, closed_outward(V, F), t_o / 2 + zozo_legal()))
        info[u] = dict(x, mode=mode, push_mm=round(push * 1e3, 2), gap_mm=round(gap_out * 1e3, 2),
                       thick_mm=[round(t_u * 1e3, 2), round(t_o * 1e3, 2)], details_in=dets)
    LB = LayeredBody(body, layers, info)
    LB.model, LB.garment = model, garment
    return LB


# ---------------------------------------------------------------- reads and the gate
def _level(at: dict, z: float) -> str:
    lv = {k[:-2]: float(v) for k, v in at.items() if k.endswith("_z") and np.ndim(v) == 0}
    if "hps.L" in at:
        lv["neck"] = float(np.asarray(at["hps.L"])[2])
    return min(lv, key=lambda k: abs(lv[k] - z)) if lv else f"z {z:.2f} m"


def reads(X, M, body) -> dict:
    """Per under layer: the closest the over garment comes (mm, covered points only), how many of its points are inside
    and the deepest, by piece."""
    if not isinstance(body, LayeredBody):
        return {}
    X = np.asarray(X, float)
    piece = np.asarray(M["piece"])
    out = {"under": body.info}
    d0 = body.body_contact.query(X)[0]
    k = body.kd.query(X)[1]
    raw, near = {}, {}
    fits = getattr(body, "fits", {}) or {}
    for L in body.layers:
        if L.role == "cover" and L.name in fits:  # (the under garment as fitted inside this one: chain_press)
            L = fits[L.name]
        elif L.role == "cover":  # (not fitted: its thickness over the body is the under cloth, covered where it is)
            raw[L.name] = (d0 - L.gap, body.push[k] > 0)
            continue
        raw[L.name] = L.query(X)[::2]
        if L.kind == "cloth":
            near[L.name] = float(cKDTree(L.c.V).query(X)[0].min())
    for name, (d, cov) in raw.items():
        dc = np.where(cov, d, np.inf)
        inside = np.where(dc < -INSIDE_TOL)[0]
        row = {"closest_mm": round(float(dc.min()) * 1e3, 2) if np.isfinite(dc).any() else None, "inside": int(len(inside))}
        if name in near:  # (to the under garment's own vertices, unsigned: its rough build, not the model of it)
            row["nearest_vertex_mm"] = round(near[name] * 1e3, 2)
        if len(inside):
            by = {}
            for i in inside:
                p = M["names"][int(piece[i])]
                if p not in by or dc[i] < dc[by[p]]:
                    by[p] = int(i)
            row["pieces"] = {p: {"n": int((piece[inside] == piece[i]).sum()), "deepest_mm": round(float(-dc[i]) * 1e3, 2),
                                 "level": _level(body.at, float(X[i, 2])), "z": round(float(X[i, 2]), 3)}
                             for p, i in by.items()}
        out[name] = row
    return out


def inside_refusal(rd: dict) -> str:
    """The refusal text of an over garment inside an under one ("" when nothing is)."""
    msgs = []
    for name, row in rd.items():
        if name == "under" or not row.get("inside"):
            continue
        for p, x in row["pieces"].items():
            girth = 2 * math.pi * (x["deepest_mm"] + (rd["under"].get(name.split(":")[0], {}).get("gap_mm") or 0))
            what = ("its solid details (buttons...) push through it: more ease over them, or flatter details" if
                    name.endswith(":details") else f"the pattern is too small for what it is worn over: add ~{girth:.0f} mm "
                    f"of girth (ease) at the {x['level']} in the draft (step 4), pattern_check, rebuild")
            msgs.append(f"{p} is inside {name} at {x['n']} points (deepest {x['deepest_mm']} mm, at the {x['level']}, "
                        f"z {x['z']} m): {what}")
    return "; ".join(msgs)


def gate(b, body, put=None, refused=ChainRefused, d=None):
    """The worker's gate after the build: each under garment fitted inside it first (chain_press: its lengths kept, else
    refused by name), then anything of it inside an under garment's fit (refused by name), then the length gate. A
    length refusal on a layered build says what it is worn over (a pattern too small reads as stretch)."""
    fit_why = ""
    if isinstance(body, LayeredBody) and hasattr(b, "net"):
        from . import chain_press as cpr
        fr, fit_why = cpr.fit_unders(getattr(body, "model", ""), getattr(body, "garment", ""), b, body, d=d)
        b.reads["under_fit"] = fr
        if put:
            put(under_fit=fr)
    rd = reads(b.X, b.pat.M, body)
    if fit_why:
        raise refused(f"worn over {', '.join(body.info)}: {fit_why}")
    if rd:
        b.reads["layers"] = rd
        if put:
            put(layers=rd)
        why = inside_refusal(rd)
        if why:
            raise refused(f"worn over {', '.join(body.info)}: {why}")
    try:
        b.gate_lengths()
    except refused as e:  # (refused: the worker's own class; run as __main__ it is not this module's import)
        if rd:
            raise refused(f"{e} (built over {', '.join(body.info)}: a stretch where it rests on the garment under it "
                               "is a pattern too small for it: ease there in the draft)") from None
        raise


def answer_line(st: dict) -> str:
    """One line of the job's answer on its layering ("" when worn over nothing)."""
    rd = st.get("layers") or (st.get("wear") or {}).get("under") and {"under": st["wear"]["under"]}
    if not rd:
        return ""
    u = rd.get("under") or {}
    parts = [f"{n} ({x.get('mode', 'visible')}{'' if x.get('approved') else ', its record UNFINISHED (' + SETTING + '=built, dev only)'}"
             f"{', thickness push ' + str(x['push_mm']) + ' mm' if 'push_mm' in x else ''})" for n, x in u.items()]
    near = [f"{n} {r['closest_mm']} mm" + (f" ({r['inside']} inside)" if r.get("inside") else "")
            for n, r in rd.items() if n != "under" and isinstance(r, dict)]
    fit = st.get("under_fit") or {}
    fits = [f"{n} fitted inside ({r.get('mode')}: {r.get('kept_faces')}/{r.get('faces')} faces kept, lengths "
            f"{r.get('kept_free_worst_pct')} % worst)" + ("; " + "; ".join(r["advice"]) if r.get("advice") else "")
            for n, r in fit.items() if isinstance(r, dict) and "mode" in r]
    return ("  layered: built over " + ", ".join(parts) + (f"; closest: {', '.join(near)}" if near else "") +
            ("; " + "; ".join(fits) if fits else "") + "; approved together at this garment's 7a")


def with_answer(text: str, st: dict) -> str:
    line = answer_line(st)
    if not line:
        return text
    i = text.rfind("\nnext:")
    return text + "\n" + line if i < 0 else text[:i] + "\n" + line + text[i:]


def plan_line(over: list) -> str:
    return f"  worn over: {', '.join(over)} (built on their approved builds: chain_layers)" if over else ""

