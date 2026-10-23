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
3. ARRANGE (fit round 20, Joe 2026-10-20: "as a man settles his coat after sitting"): a pose or openness physics alone
   won't give (a concept's wide-open front) is reached by hand, never by the pattern or the fit. `arrange_job`: the
   release's job plus SOFT pins (pull springs) on named points / border edges (`pin_vertices`), moved from where they
   start to their targets over ARRANGE_PLACE frames of the gravity settle, held to its end, then let go for
   ARRANGE_FREE frames (the free settle). `arranged` reports per pin how near its target it got (held), how far it
   sprang back once let go, and the stretch near the pins vs the rest. Springback over SPRING_MM: the pins are kept
   (keep=True) and the result is recorded "placed by hand" (the shape is baked into the asset; no pin ships).
   MCP arrange_garment.

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
# A RELEASED closure's two layers parted at the start (fit round 25): the closed fit joins them at the fastened button
# (pattern_form LAP_BUTTON fades the lap's parting to 0 there: Garrett r24c's button pair front.L | front.R 0.0 mm apart,
# 398 mm below HPS) and lays the rest of the lap LAP_GAP (1.5 mm) apart. Unbuttoned, the pair is two free sheets
# touching: ZOZO's CCD fails the first Newton step (toi 0, r21k / r25a). Parted to RELEASE_PART (> the contact gap)
# where they lap, each side half, the button's fade dropped (the button is gone).
RELEASE_PART = 0.0022  # m
EDGE_CLEAR = 0.0021  # m: garment edges this close to a collider edge stepped off at the start (preflight: 2 mm)
EDGE_CLEAR_MOST = 0.002  # m: ... by at most this
BODY_CLEAR_MOST = 0.004  # m: clear_body's most per vertex in job() (more is a fit fault: reported)


def part_released(X: np.ndarray, M: dict, release=("front",), body=None, gap: float = RELEASE_PART,
                  reach: float = 0.05, rounds: int = 8) -> tuple[np.ndarray, dict]:
    """The released closures' layers parted round their (former) fastenings: within `reach` of the closure's vertex
    pairs, an over vertex lapping the under piece IN ORDER (in front of it, closer than `gap`) moves out along the
    under piece's normal and the under vertex lapping the over piece in order moves in, each half the shortfall, at
    most pattern_form.LAP_STEP a round. Out-of-order vertices (another layer: the lapel's turn, a facing) are never
    pushed through (round 25: a whole-lap parting without the order test made 47 crossings). Returns (X, {closure:
    {"pairs_mm_before", "pairs_mm_after", "moved", "max_mm"}}) (the closure pairs' distances)."""
    from . import pattern_form as pf
    X0 = np.array(X, float)
    X = X0.copy()
    rel = set(release or ())
    F, pid, names = np.asarray(M["F"]), np.asarray(M["piece"]), list(M["names"])
    ref = pf._body_surface(body) if body is not None else None
    out = {}
    for c in M.get("closures") or []:
        o, u = c.get("over"), c.get("under")
        if c.get("name") not in rel or not c.get("v") or not o or not u or o == u or o not in names or u not in names:
            continue
        ko, ku = names.index(o), names.index(u)
        tv = np.asarray(c["v"], np.int64).reshape(-1)
        near = cKDTree(X[tv]).query(X)[0] < reach
        fo, fu = np.where((pid == ko) & near)[0], np.where((pid == ku) & near)[0]
        to, tu = F[pid[F[:, 0]] == ko], F[pid[F[:, 0]] == ku]
        before = [round(float(np.linalg.norm(X[a_] - X[b_])) * 1000, 2) for a_, b_ in c["v"]]
        for _ in range(rounds):
            d, nrm, m = pf._lap_side(X, X[fo], tu, ref)
            m &= (d > -5e-4) & (d < gap)  # (a coincident button pair reads either sign)
            X[fo[m]] += nrm[m] * np.minimum(0.5 * (gap - d[m]), pf.LAP_STEP)[:, None]
            d, nrm, m = pf._lap_side(X, X[fu], to, ref)
            m &= (d < 5e-4) & (d > -gap)
            X[fu[m]] -= nrm[m] * np.minimum(0.5 * (gap + d[m]), pf.LAP_STEP)[:, None]
        mv = np.linalg.norm(X - X0, axis=1)
        out[c["name"]] = {"pairs_mm_before": before,
                          "pairs_mm_after": [round(float(np.linalg.norm(X[a_] - X[b_])) * 1000, 2) for a_, b_ in c["v"]],
                          "moved": int((mv > 1e-5).sum()), "max_mm": round(float(mv.max()) * 1000, 2)}
    return X, out

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


def untangle_closure(X: np.ndarray, M: dict, release=("front",), body=None, gap: float = 0.002,
                     reach: float = 0.03, rounds: int = 4, most: float = 0.012) -> tuple[np.ndarray, dict]:
    """A released closure's over piece passing THROUGH its under piece in the start (fit round 20: Garrett's front.L
    through front.R round the break, 61-75 vertices, in the closed fit r15e and every release after it: an
    intersection-free solver keeps a crossing it starts with, so the fronts stay locked together and no arrangement
    can part them). The over piece's vertices near the crossing (within `reach`) that lie behind the under piece's
    surface (its outward side by the body) are moved out to `gap` in front of it, rounds until none cross. Over /
    under: the closure's pairs (over vertex, under vertex). Returns (X, {closure: {"crossing_before", "after", "moved",
    "max_mm"}})."""
    from . import cloth
    from .pattern_form import _Surface, _body_surface
    X = np.array(X, float)
    F, pid, names = np.asarray(M["F"]), np.asarray(M["piece"]), M["names"]
    rel = set(release or ())
    out = {}
    for c in M.get("closures") or []:
        if c.get("name") not in rel or not c.get("v"):
            continue
        ko, ku = int(pid[c["v"][0][0]]), int(pid[c["v"][0][1]])
        if ko == ku:
            continue
        cr0 = np.asarray(cloth._pair_crossing_verts(X, F, pid, ko, ku), np.int64).reshape(-1)
        rec = {"over": names[ko], "under": names[ku], "crossing_before": int(len(cr0)), "moved": 0, "max_mm": 0.0}
        if not len(cr0):
            out[c["name"]] = dict(rec, after=0)
            continue
        X0 = X.copy()
        bsurf = _body_surface(body) if body is not None else None
        best = (len(cr0), X0, "none")
        # two ways to part them, the one leaving fewer crossings kept: the over piece's cloth just behind the under
        # piece moved out in front of it, or the under piece's cloth just in front of the over piece moved behind it
        for kmove, kref, sg, how in ((ko, ku, 1.0, "over out"), (ku, ko, -1.0, "under in")):
            Y = X0.copy()
            Fu = F[(pid[F] == kref).all(1)]
            ui = np.unique(Fu)
            Fl = np.searchsorted(ui, Fu)
            cr_ = cr0
            for _ in range(rounds):
                if not len(cr_):
                    break
                S = _Surface(Y[ui], Fl, ref=bsurf)
                cv = np.unique(np.r_[cr_, np.asarray(cloth._pair_crossing_verts(Y, F, pid, ku, ko), np.int64).reshape(-1)])
                ov = np.where((pid == kmove) & (cKDTree(Y[cv]).query(Y)[0] < reach))[0]
                d, n, dist = S.signed(Y[ov])
                d = sg * d  # (distance on the side it should be on)
                b = (d < gap) & (d > -most) & (dist < most)  # (only cloth lying just on the wrong side: not the far side)
                Y[ov[b]] += sg * n[b] * (gap - d[b])[:, None]
                cr_ = np.asarray(cloth._pair_crossing_verts(Y, F, pid, ko, ku), np.int64).reshape(-1)
            if len(cr_) < best[0]:
                best = (len(cr_), Y, how)
        X = best[1]
        mv = np.linalg.norm(X - X0, axis=1)
        rec.update(after=int(best[0]), how=best[2], moved=int((mv > 0).sum()), max_mm=round(float(mv.max() * 1000), 1))
        out[c["name"]] = rec
    return X, out


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
        name: str | None = None, pad_base=None, hold_ring: float = 0.0, untangle: bool = False,
        part: float = RELEASE_PART, held: np.ndarray | None = None) -> tuple[dict, dict, dict]:
    """The release sim's (cfg, arrays, info). held: more vertices held as fitted (a seen part's cut edge, seen_job). res: the placed pattern (cloth.build place_only: "mesh", "pieces",
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
    if hold_ring > 0 and len(carry):
        # the held pieces' NEIGHBOURS held with them (fit round 20): a stand held as fitted while the shoulder it is
        # sewn to settles under gravity parts at the seam (Garrett r19: 7-12 mm at HPS). The band of the bodice within
        # `hold_ring` of the held pieces is held too, so the seam has both sides held and the give is inside one cloth
        ring = np.where(~np.isin(np.arange(len(X)), carry) & (cKDTree(X[carry]).query(X)[0] < hold_ring))[0]
        # (never a vertex of a triangle the fit left over the strain limit: pinned, it can't relax, and ZOZO's strain
        # limiting fails at t = 0; Garrett ring 40 mm: 188 such triangles, up to 55 %, round 20)
        Fm = np.asarray(M["F"])
        Ed = np.r_[Fm[:, [0, 1]], Fm[:, [1, 2]], Fm[:, [2, 0]]]
        se = (np.linalg.norm(X[Ed[:, 0]] - X[Ed[:, 1]], axis=1) / (np.linalg.norm(uv[Ed[:, 0]] - uv[Ed[:, 1]], axis=1)
                                                                   + 1e-12) - 1).reshape(3, -1).max(0)
        lim = cloth.strain_limit_of(g) if cloth.strain_limit_of(g) > 0.05 else 0.05
        bad = np.zeros(len(X), bool)
        bad[Fm[se > 0.8 * lim].ravel()] = True
        info_bad = int(np.isin(ring, np.where(bad)[0]).sum())
        ring = ring[~bad[ring]]
        info["held_ring"] = {"mm": round(hold_ring * 1000, 1), "vertices": int(len(ring)), "left_free_strained": info_bad,
                             "pieces": sorted({M["names"][k] for k in pid[ring]})}
    else:
        ring = np.zeros(0, np.int64)
    free = np.ones(len(X), bool)
    free[carry] = False  # (the ring is cleared off the body / shirt like free cloth first, then held where cleared)
    carry = np.union1d(carry, ring).astype(np.int64)
    # (a seen part's cut edge, `held`: pinned where it joined the hidden cloth, "cutIdx", after it is cleared like free
    # cloth. NOT carried: a carried vertex rests as placed, and a triangle with one carried corner rests half flat, half
    # placed: 1185 such starts over the limit, up to 26x, on the shirt's cut sleeves, shirt round 5)
    held = np.zeros(0, np.int64) if held is None else np.setdiff1d(np.asarray(held, np.int64), carry)
    if pad_base is not None:
        import types as _types
        lift = np.linalg.norm(np.asarray(body.V, float) - np.asarray(pad_base.V, float), axis=1)
        Vp, pinfo = clear_under(X, M["F"], body.V, np.asarray(body.T), pad_base, clear, most=lift, free=free)
        pinfo.pop("faces_keep")
        info["pad"] = dict(pinfo, lift_max_mm=round(float(lift.max() * 1000), 1))
        body = _types.SimpleNamespace(V=Vp, T=np.asarray(body.T), at=getattr(body, "at", {}))
    if untangle:  # (a front through the other front, carried from the closed fit: parted before the sim)
        X, info["untangle"] = untangle_closure(X, M, gone, body=body)
    if part and gone:  # (the released closure's layers parted: the button is gone, see RELEASE_PART)
        X, info["part"] = part_released(X, M, gone, body=body, gap=part)
    X, info["body_clear"] = clear_body(X, body, free=free, M=M, most=BODY_CLEAR_MOST)
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
    X1, _ = clear_start(X, (np.asarray(coll["bodyV"], float), np.asarray(coll["bodyT"])), free, EDGE_CLEAR,
                        rounds=2, F=np.asarray(M["F"]))
    mv = np.linalg.norm(X1 - X, axis=1)
    cap = mv > EDGE_CLEAR_MOST
    X1[cap] = X[cap] + (X1[cap] - X[cap]) * (EDGE_CLEAR_MOST / mv[cap])[:, None]
    info["edge_clear"] = {"moved": int((mv > 0).sum()), "max_mm": round(float(min(mv.max(), EDGE_CLEAR_MOST) * 1000), 2),
                          "capped": int(cap.sum())}
    X = X1
    # the reverse pairs (fit round 25): a COLLIDER vertex within EDGE_CLEAR of a free garment face (a shirt vertex at a
    # crumple poking up under the jacket: Garrett r25d's shirt vertex 0.99 mm off front.L by the underarm, ZOZO "face-
    # vertex (collision mesh, assembly)" overlap at t = 0, which no garment-vertex / edge clear sees). The under
    # garment's vertex steps back from the face (a static collider: it may go into the body), at most
    # EDGE_CLEAR_MOST + 1 mm; the body's own vertices are left (a body vertex there is a fit fault: reported)
    bV_ = np.asarray(coll["bodyV"], float).copy()
    nb = len(np.asarray(body.V))
    fi = np.where(free[np.asarray(M["F"])].any(1))[0]
    from .cloth_made import closest as _closest
    Qc = _closest(bV_, X, np.asarray(M["F"])[fi])[0]
    dv = bV_ - Qc
    dd = np.linalg.norm(dv, axis=1)
    rv = np.where(dd < EDGE_CLEAR)[0]
    us = rv[rv >= nb]
    step = np.minimum(EDGE_CLEAR - dd[us] + 1e-4, EDGE_CLEAR_MOST + 0.001)
    bV_[us] += dv[us] / (dd[us, None] + 1e-12) * step[:, None]
    coll = dict(coll, bodyV=bV_)
    info["collider_clear"] = {"under_moved": int(len(us)), "body_left": int((rv < nb).sum()),
                              "min_mm": round(float(dd.min()) * 1000, 2)}
    arrays = dict(X=X, uv=uv, F=np.asarray(M["F"], np.int64), sew=np.asarray(M["sew"], np.int64).reshape(-1, 2),
                  stitch=stitch, stiff=stiff, piece=np.asarray(M["piece"], np.int64), pins=np.zeros(0, np.int64),
                  bodyV=np.asarray(coll["bodyV"], float), bodyT=np.asarray(coll["bodyT"], np.int64))
    if len(held):
        arrays["cutIdx"] = held.astype(np.int64)
        info["held_cut"] = int(len(held))
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
    if res.get("gate_keys"):  # (C164: write() checks the gate keys it is given are this pattern's)
        cfg["_gate_keys"] = dict(res["gate_keys"])
    return cfg, arrays, info


class GateKeyMismatch(ValueError):
    pass


def write(job_dir: Path, cfg: dict, arrays: dict, names: list, gate: dict | None) -> Path:
    """The job folder (cloth_job.write) with the pattern gate's keys beside it (run_zozo refuses without a PASS).
    C164 (garrett jacket fit round 29): the keys must be the drafted pattern's own (job() records res["gate_keys"]
    in cfg["_gate_keys"], dropped before writing): rounds 25-28 wrote round 19's keys into every release job, so
    run_zozo checked an older pattern's PASS record. A job built from another pattern's keys is refused."""
    from . import cloth_job
    cfg = dict(cfg)
    own = cfg.pop("_gate_keys", None)
    if own and gate and (own.get("pattern"), own.get("body")) != (gate.get("pattern"), gate.get("body")):
        raise GateKeyMismatch(f"gate keys {gate.get('pattern')} / {gate.get('body')} are not this job's pattern "
                              f"{own.get('pattern')} / {own.get('body')}: pass res['gate_keys'] (C164)")
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


SEAM_OPEN_MM = 1.0  # a sewn pair further apart than this reads as an open seam (a white line in renders)


def seam_gaps(M: dict, X: np.ndarray) -> dict:
    """The sewn seams' gaps after a sim (mm): each sew pair's distance. FAIL when any pair is over SEAM_OPEN_MM.
    Fit round 18: the closed fit r15e reads max 0.03 (PASS); the release r16 p50 1.17 / max 11.8, 458 of 579 pairs over
    1 mm (FAIL). The median tracks ZOZO's contact gap (1 mm: p50 1.08; 0.5 mm: 0.56): the seam's two sides are held
    apart as a contact pair; stitch_gap 0.5 mm changed nothing (max 9.1)."""
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    d = np.linalg.norm(np.asarray(X)[sw[:, 0]] - np.asarray(X)[sw[:, 1]], axis=1) * 1000
    if not len(d):
        return {"pairs": 0, "status": "PASS"}
    return {"pairs": int(len(d)), "p50": round(float(np.median(d)), 2), "p99": round(float(np.percentile(d, 99)), 2),
            "max": round(float(d.max()), 2), "open": int((d > SEAM_OPEN_MM).sum()),
            "status": "PASS" if d.max() <= SEAM_OPEN_MM else "FAIL"}


WELD_MM = 3.0  # a sewn pair this close after the sim is one seam held a contact gap apart: welded to its midpoint


def weld_seams(M: dict, X: np.ndarray, reach_mm: float = WELD_MM) -> tuple[np.ndarray, dict]:
    """The release's result with its sewn pairs WELDED (fit round 19): ZOZO holds a seam's two sides a contact gap
    apart (they are a contact pair; stitch_gap does not close them), so every pair within reach_mm is moved to its
    midpoint, as the sewn seam is one line. A pair further apart is a real opening, not welded: reported with its
    pieces and position (the seam is located, never hidden). Returns (X welded, {"welded", "open": [...], gaps after})."""
    X = np.array(X, float)
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    d = np.linalg.norm(X[sw[:, 0]] - X[sw[:, 1]], axis=1) * 1000
    ok = d <= reach_mm
    # (a vertex in several pairs, a seam end: the mean of its pairs' midpoints)
    acc = np.zeros_like(X)
    cnt = np.zeros(len(X))
    mid = 0.5 * (X[sw[ok, 0]] + X[sw[ok, 1]])
    for c in (0, 1):
        np.add.at(acc, sw[ok, c], mid)
        np.add.at(cnt, sw[ok, c], 1)
    hit = cnt > 0
    X[hit] = acc[hit] / cnt[hit][:, None]
    pid, names = np.asarray(M["piece"]), M["names"]
    opn = [{"pieces": f"{names[pid[a]]}|{names[pid[b]]}", "gap_mm": round(float(g), 1),
            "at": np.round(0.5 * (X[a] + X[b]), 3).tolist()} for (a, b), g in zip(sw[~ok], d[~ok])]
    opn.sort(key=lambda r: -r["gap_mm"])
    return X, {"welded": int(ok.sum()), "open": opn, "after": seam_gaps(M, X)}


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


def from_form(model: str, garment: str, spec: dict | None = None, release=("front",), log=None,
              pins: list | None = None, arrange: dict | None = None, hold_ring: float = 0.0,
              cover: dict | None = None, res: dict | None = None) -> dict:
    """A model's garment fitted CLOSED on the form (pattern_form.on_form, worn_open off) and its release job (with
    `pins`: released and arranged in one sim, arrange_job; `arrange`: its frames / pull / keep).
    cover: the garment worn OVER this one, as it is worn ({"V", "mesh"}: an open jacket's arranged state): the job is
    built on the SEEN part only (`seen_res`: hidden cloth and cloth below a tuck line cut away, the made pieces whole,
    the cut edge held where it joined the hidden cloth), so the sim and its preflight judge only cloth that shows.
    res: on_form's result when already made. Returns {"res" (on_form's result, or its seen part), "cfg", "arrays",
    "info", "gate"} (+ "seen": seen_res's info)."""
    import json as _json
    from . import pattern_form, store
    spec = spec or store.load(model)
    g = _json.loads(_json.dumps(spec["cloth"][garment]))
    g.pop("worn_open", None)  # (the closed fit: the top button fastened, pattern_form.fastened "default")
    res = res if res is not None else pattern_form.on_form(model, garment, spec, g=g, log=log)
    seen = None
    if cover is not None:
        res, seen = seen_res(res, cover, g)
    und = res.get("form_under")
    under = {"V": und["A"], "F": und["mesh"]["F"]} if und is not None else None
    body = pattern_form.padded_body(res["body"], g.get("shoulder_pad")) if g.get("shoulder_pad") else res["body"]
    pad_base = res["body"] if g.get("shoulder_pad") else None
    if pins:  # released and arranged in one sim (arrange_job)
        cfg, arrays, info = arrange_job(res, res["A"], pins, g, under=under, body=body, release=release,
                                        name=f"{model}:{garment}", pad_base=pad_base, hold_ring=hold_ring,
                                        held=seen["cut"] if seen else None, **(arrange or {}))
    else:
        cfg, arrays, info = job(res, res["A"], g, under=under, body=body, release=release, name=f"{model}:{garment}",
                                pad_base=pad_base, hold_ring=hold_ring, held=seen["cut"] if seen else None)
    out = {"res": res, "cfg": cfg, "arrays": arrays, "info": info, "gate": res.get("gate_keys")}
    if seen:
        info["seen"] = {k: v for k, v in seen.items() if k not in ("old", "cut")}
        out["seen"] = seen
    return out


def seen_res(res: dict, cover: dict, g: dict | None = None) -> tuple[dict, dict]:
    """on_form's result cut down to the part `cover` (the over garment as worn) leaves SEEN (cloth_layers.seen_part:
    the round-24 margins at the cover's openings, open_front_margin at an open front, PIERCE_CULL, the made pieces
    whole; below the garment's tuck line dropped when it is tucked). -> (res with "mesh" / "A" (and "V") of the seen
    part, info with "old" / "cut")."""
    from . import cloth_check, cloth_layers
    g = g or {}
    body = res["body"]
    outer = {"V": np.asarray(cover["V"], float), "mesh": cover["mesh"], "body": body}
    below = None
    if g.get("tucked"):  # (C108: what lies below the tuck line is inside the garment it's tucked into)
        from . import garment_reads
        below = garment_reads.tuck_line_z(body, g)
    M2, A2, info = cloth_layers.seen_part({"V": res["A"], "mesh": res["mesh"]}, outer,
                                          edge_margin=cloth_check.open_front_margin(outer), below_z=below)
    r2 = dict(res, mesh=M2, A=A2)
    if "V" in res and len(np.asarray(res["V"])) == len(res["A"]):
        r2["V"] = np.asarray(res["V"])[info["old"]]
    info["below_z"] = below
    return r2, info


ARRANGE_PLACE = 24  # frames (1 s) the pins take to their targets, with gravity on
ARRANGE_HOLD = 24  # frames held there (the cloth and the shirt settle round the placed points; friction takes hold)
ARRANGE_FREE = 24  # frames after the pins let go: the springback
ARRANGE_PULL = 10.0  # the soft pins' pull (ZOZO pin pull: a spring to the moving target, contact acts; KAT: 1 stops 12 mm short, 10 within 7)
SPRING_MM = 10.0  # a pin that springs back further than this once let go: kept, the result "placed by hand"


def pin_vertices(M: dict, ref: str) -> np.ndarray:
    """The vertices a pin names: "piece:point" (M["points"]) -> that vertex; "piece:a..b" -> the piece's BORDER from
    point a to point b along its boundary edges, the shorter way round (a front edge from the break to the hem)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    P = M.get("points") or {}
    if ".." not in ref:
        if ref not in P:
            raise KeyError(f"no point {ref!r} (points like {', '.join(list(P)[:6])} ...)")
        return np.array([int(P[ref])], np.int64)
    pc, ab = ref.split(":", 1)
    a, b = (f"{pc}:{s}" for s in ab.split(".."))
    for q in (a, b):
        if q not in P:
            raise KeyError(f"no point {q!r}")
    F = np.asarray(M["F"])
    pid = np.asarray(M["piece"])
    k = M["names"].index(pc)
    Fk = F[(pid[F] == k).all(1)]
    E = np.sort(np.r_[Fk[:, [0, 1]], Fk[:, [1, 2]], Fk[:, [2, 0]]], axis=1)
    u, c = np.unique(E, axis=0, return_counts=True)
    B = u[c == 1]  # the piece's boundary edges
    uv = np.asarray(M["uv"], float)
    w = np.linalg.norm(uv[B[:, 0]] - uv[B[:, 1]], axis=1) + 1e-9
    n = len(uv)
    G = coo_matrix((np.r_[w, w], (np.r_[B[:, 0], B[:, 1]], np.r_[B[:, 1], B[:, 0]])), shape=(n, n)).tocsr()
    ia, ib = int(P[a]), int(P[b])
    dist, pred = dijkstra(G, indices=ia, return_predecessors=True)
    if not np.isfinite(dist[ib]):
        raise ValueError(f"{a} and {b} are not joined by {pc}'s border")
    path = [ib]
    while path[-1] != ia:
        path.append(int(pred[path[-1]]))
    return np.asarray(path[::-1], np.int64)


def arrange_targets(M: dict, X: np.ndarray, pins: list) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
    """(idx, target, group, names) from pin specs: {"name"?, "at": "piece:point" | "piece:a..b", and one of "to":
    [x, y, z] (a point; an edge: where its first vertex goes, the rest moved with it) | "by": [dx, dy, dz] (every
    vertex; with "by_end" an edge's shift blends from "by" at a to "by_end" at b) | "targets": [[x, y, z] ...] (one
    per vertex)}. A vertex named by two pins keeps the first. "patch": r (m, pattern) on a point pin spreads it over
    the piece's vertices within r of the point (the point first), moved as one ("to" / "by": the patch translated
    rigidly): a single-vertex pin tore the cloth round it (C123, Garrett a8c: 31 % at a band end, 10 % at a point)."""
    X = np.asarray(X, float)
    idx, tgt, grp, names, seen = [], [], [], [], set()
    for k, p in enumerate(pins):
        v = pin_vertices(M, p["at"])
        if p.get("patch") and len(v) == 1:
            uv = np.asarray(M["uv"], float)
            pid = np.asarray(M["piece"])
            near = np.where((pid == pid[v[0]]) & (np.linalg.norm(uv - uv[v[0]], axis=1) <= float(p["patch"])))[0]
            v = np.r_[v, near[near != v[0]]].astype(np.int64)
        if "targets" in p:
            T = np.asarray(p["targets"], float).reshape(-1, 3)
            if len(T) != len(v):
                raise ValueError(f"pin {p['at']}: {len(T)} targets for {len(v)} vertices")
        elif "to" in p:
            T = X[v] + (np.asarray(p["to"], float) - X[v[0]])
        else:
            d0 = np.asarray(p.get("by", (0, 0, 0)), float)
            d1 = np.asarray(p.get("by_end", d0), float)
            s = np.linspace(0, 1, len(v))[:, None] if len(v) > 1 else np.zeros((1, 1))
            T = X[v] + d0 + (d1 - d0) * s
        new = np.array([int(i) not in seen for i in v])
        seen.update(map(int, v))
        idx.append(v[new])
        tgt.append(T[new])
        grp.append(np.full(int(new.sum()), k))
        names.append(p.get("name") or p["at"])
    return np.concatenate(idx), np.concatenate(tgt), np.concatenate(grp), names


def arrange_job(res: dict, X: np.ndarray, pins: list, g: dict | None = None, under: dict | None = None, body=None,
                release=("front",), hold=("neck",), place_frames: int = ARRANGE_PLACE, hold_frames: int = ARRANGE_HOLD,
                free_frames: int = ARRANGE_FREE, pull: float = ARRANGE_PULL, keep: bool = False,
                zozo: dict | None = None, name: str | None = None, pad_base=None, hold_ring: float = 0.0,
                sew_frames: int = SEW_FRAMES, held: np.ndarray | None = None) -> tuple[dict, dict, dict]:
    """The release job (`job`; X the closed fit: released and arranged in one sim, or an earlier release's result)
    with soft pins placing `pins` (arrange_targets' specs) during the gravity settle: place_frames to the targets,
    held to the settle's end (+ hold_frames), let go (unless keep) for free_frames. Held neck pieces are never pinned
    (they are held already)."""
    cfg, arrays, info = job(res, X, g, under=under, body=body, release=release, hold=hold,
                            frames=place_frames + hold_frames, settle_frames=free_frames, sew_frames=sew_frames,
                            zozo=zozo, name=name, pad_base=pad_base, hold_ring=hold_ring, held=held)
    idx, tgt, grp, names = arrange_targets(res["mesh"], arrays["X"], pins)
    if "carryIdx" in arrays:
        ok = ~np.isin(idx, arrays["carryIdx"])
        idx, tgt, grp = idx[ok], tgt[ok], grp[ok]
    arrays.update(arrIdx=idx.astype(np.int64), arrTarget=tgt, arrGroup=grp.astype(np.int64))
    cfg["arrange"] = {"stage": "settle", "place_frames": int(place_frames), "pull": float(pull), "keep": bool(keep),
                      "pins": names}
    info["arrange"] = {"pins": names, "vertices": [int((grp == k).sum()) for k in range(len(names))],
                       "move_mm": [round(float(np.linalg.norm(tgt[grp == k] - arrays["X"][idx[grp == k]], axis=1).max()
                                               * 1000), 1) if (grp == k).any() else 0.0 for k in range(len(names))],
                       "keep": bool(keep), "pull": float(pull)}
    return cfg, arrays, info


def _stretch(M: dict, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(edges, per-edge strain against the flat pattern's uv)."""
    F = np.asarray(M["F"])
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1), axis=0)
    uv = np.asarray(M["uv"], float)
    L0 = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)
    return E, np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / (L0 + 1e-12) - 1)


def arranged(M: dict, arrays: dict, out: dict, keep: bool = False, X_ref: np.ndarray | None = None,
             near: float = 0.03) -> dict:
    """The arrangement's report: per pin (mm) "held_max" = target to where it stood as the pins let go (Vheld: a
    pull is a spring, contact and the cloth resist), "springback" = Vheld to the end (0 when kept), "off_max" =
    target to the end; stretch p99 / max (%) of edges within `near` of a pinned vertex vs the rest (a pin spike reads
    near >> rest), and X_ref's p99 (the start); "status": "held by friction" | "springs back" (over SPRING_MM: rerun
    with keep=True) | "placed by hand" (kept)."""
    V = np.asarray(out["V"], float)
    H = np.asarray(out.get("Vheld", V), float)
    idx, tgt, grp = np.asarray(arrays["arrIdx"]), np.asarray(arrays["arrTarget"], float), np.asarray(arrays["arrGroup"])
    pins = {}
    for k in np.unique(grp):
        s = grp == k
        held = np.linalg.norm(H[idx[s]] - tgt[s], axis=1) * 1000
        sb = np.linalg.norm(V[idx[s]] - H[idx[s]], axis=1) * 1000
        off = np.linalg.norm(V[idx[s]] - tgt[s], axis=1) * 1000
        pins[int(k)] = {"n": int(s.sum()), "held_max": round(float(held.max()), 1),
                        "springback_p50": round(float(np.median(sb)), 1), "springback_max": round(float(sb.max()), 1),
                        "off_max": round(float(off.max()), 1)}
    E, st = _stretch(M, V)
    nearv = cKDTree(V[idx]).query(V)[0] < near
    ne = nearv[E].any(1)
    rep = {"pins": pins, "stretch_p99_near": round(float(np.percentile(st[ne], 99) * 100), 2) if ne.any() else None,
           "stretch_max_near": round(float(st[ne].max() * 100), 2) if ne.any() else None,
           "stretch_p99_rest": round(float(np.percentile(st[~ne], 99) * 100), 2)}
    if X_ref is not None:
        rep["stretch_p99_start"] = round(float(np.percentile(_stretch(M, np.asarray(X_ref, float))[1], 99) * 100), 2)
    worst = max((p["springback_max"] for p in pins.values()), default=0.0)
    rep["status"] = "placed by hand" if keep else ("springs back" if worst > SPRING_MM else "held by friction")
    return rep
