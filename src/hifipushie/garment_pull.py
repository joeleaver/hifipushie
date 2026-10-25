"""PULL AND SMOOTH UNTIL IT WOULD STRETCH (C142 / C143; Joe 2026-10-21): how people put clothes on and set them, as
tools. "If I were
hand-editing, I'd try to just pull the point out and to the side, and let it go as far as it could without
stretching"; "Think of men pulling their shirts down along the G-line, popping cuffs, women pulling down skirts. It's
not a gravity simulation, it's a flatten-this-along-interesting-geometry without stretching it much thing, and it's how
humans put on clothes." "There's likely a 'smooth' operation ... those are the two main operations to styling the
clothing one is wearing." A fitted garment is posed by DRAGGING handles and smoothing, never by pinning handles at
guessed coordinates or by tuning stiffness. `style(M, X, held, ops)` runs a SEQUENCE of pull / turn / smooth ops
(earlier grips held where they ended; gripping one again picks it up).

`pull(M, X, held, handles, body=None, ...)` -> (X_new, info):
  - M: the fitted garment's mesh (pattern_form.on_form's "mesh": F, uv (each piece's flat pattern, m), piece, names,
    sew (pairs of vertices sewn together), points ({"piece:point": vertex})); X: its vertex positions (n, 3);
  - held: vertices that don't move (a mask (n,) or indices): what the other hand / the body holds still (the back,
    the sleeves, the fronts below the first fastened button, a tucked waist ...);
  - handles: [{"at": ..., "dir": ..., "side_from"?, "patch"?, "turn"?}], dragged TOGETHER (one distance for all:
    a symmetric pull keeps the mirror). "at" = what the hand grips (`grip`): a vertex or "piece:point" grabs an AREA,
    the cloth within `patch` (PATCH, 25 mm on its pattern), and the patch TURNS with the cloth (each step the point is
    dragged alone, the patch's start shape fitted rigidly (Kabsch) onto that solution and pinned, solved again: one
    vertex dragged pinched and twisted the collar's tip, 15-18 % / 60-80 deg; a rigid patch folded the cloth over at
    its edge, 18 / 28 faces); "piece:a..b" (the piece's border from a to b: a hem, a cuff's edge, a front edge) or a
    list moves as one. "dir" is a vector [x, y, z], a name, or a weighted mix {"side": 1, "out": 0.3, "up": 0.3}
    (each named unit vector x its weight, the sum normalised):
      "side": away from centre front / back (x = 0), the side taken from `side_from` (a landmark well off CF: a
              hinge, a neck point), else from the handle (a group's centroid); refused when that is within SIDE_MIN of
              x = 0 (where a band's two ends cross, the side of a point AT CF flips: the shirt spike's mirror bugs);
      "out": the body's outward normal at the nearest body vertex (needs `body` = (V, F) or an object with V and F/T);
      "up" / "down": +z / -z;
      "easy" or {"easy": base}: the cloth chooses: each step probes 9 directions round the base (default "side"),
              tilted toward the body normal / up by 0 / 35 / 70 deg, and takes the least stretch (~9x the time; on the
              shirt's points it went 81 mm with stretch falling). A tangent "along the plane" pulls the leaf taut (the
              shirt's point went 12 mm): a held leaf moves by swinging ACROSS its plane. Don't bake in out / up weights:
              up 0.3 put the shirt's points too high (Joe).
  - body: only for "out" (the solve itself ignores the body: no push-out; it dented the shirt's band).

The solve: per-face as-rigid-as-possible against the FLAT PATTERN (Liu et al. 2008 local / global: each triangle keeps
its own pattern shape; rest = its uv), sewn pairs welded into one vertex, bending free (every bending variant roughened
the shirt's collar, C142). FEW rounds per step on purpose, each from where the cloth was: the cloth moves as little as
it must (early stopping is the regulariser: the shirt pull with every solve run to convergence crumpled the collar to
p95 0.33 mm and stopped 16 mm short; 12 rounds per step keep 0.28). A step that reads over `tol` is re-solved up to
`confirm` more rounds and the CONVERGED read decides (an unconverged solve on a big move reads stretch the cloth
doesn't need: a slack strip stopped at 75 of its 100 mm without it); the few-rounds state is the one kept, and a
confirmed read doesn't lower the least (it is read another way).
First the free cloth relaxes against the pattern with the handles held where they are (`relax_iters`): its stretch is
the START. Then each step moves every handle `step` further along its direction and re-solves (`iters`). The pull
stops at the last step whose stretch is within `tol` of the LEAST stretch reached so far (the start included, read
after `iters`): a pull first takes up slack (the shirt's collar eased 4.41 -> 4.30 % over its first 36 mm), then
meets the knee where it starts to stretch (few-rounds reads 4.51 % at 45 mm, 4.84 at 48, 5.52 at 51, 6.01 at 54;
confirmed, 48 and 51 pass and 54 stops it: 51 mm, y3's place). Or at `max_move`
(reported: nothing stopped it). Last a `settle_iters` solve with the handles held where they stopped.

Stretch = THREAD strain (C169): p99 over the faces of |warp / weft length - 1| (each face's deformation gradient in the
piece's thread frame, pattern x / y on grain), on `pieces` (default: every piece with a vertex that is neither held nor
a handle: held pieces don't move and would dilute the read). Shear is read apart (the threads' angle off 90, p99) and
LOCKS at pattern_form.SHEAR_LOCK_DEG (35, a woven's jamming angle; or where the cloth started if past it): the styling
solve is the fit's woven model (WOVEN_STYLE), so a bias edge lengthens as the cloth shears and an edge read counted
that as stretch (the wobble smooth stopped, the spike's smooth ran 0 rounds). Every stop (pull, turn tol, smooth,
smooth_border) reads the same: until a thread would stretch, or the weave would jam.

info: {"moved_mm": {handle: mm}, "stretch_p99_start" / "_least" / "_end" (%: threads), "shear_p99_deg" [start, end],
"shear_lock_deg", "steps", "stopped" ("stretch" | "shear" | "max_move"), "path_mm", "gripped", "dirs" (unit vectors, the last step's), "pieces"}. `turn` turns grips about a line
(a band end swung open, a cuff popped); `smooth` flattens ripples; `smooth_border` draws a border toward one fitted
curve (one swoop, C145); `hold_region` / `feather` hold a region, its edge feathered (C144); `hold_mask` builds
`held`; reads: `crumple`, `edge_turns` (a free edge's side-view swoop),
`tip_read` (a point's tip: crumple, stretch max, twist), `folded` (folded-over faces near a point).

Known answers (tests/test_garment_pull.py): a slack strip pinned at one end, its free end pulled, stops within one
step of where its pattern length runs out (and two pulls in a sequence go as far as one); a rippled sheet smooths
without stretching; wf_simon's Simon shirt, closed fit: band ends turned 30 deg about Simon's hinges, collar points
pulled out / side / up (25 mm turning patches), collar + stand smoothed: points 142 apart, 64 / 60 below HPS, collar
crumple p95 0.28 mm, tips as clean as the closed collar's (spike y3: 147, 63 / 59, 0.28).
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import splu
from scipy.spatial import cKDTree

# THE HANG IN STYLING (supports thread, 2026-10-23; pattern_form.HANG_FIELD's twin): a "relax" op with hang (or every
# relax with STYLE_HANG) lets the free cloth settle under a weak downward field onto what supports it (the held pieces,
# the floors), each round's move clamped to HANG_STEP, the threads capped at HANG_STRAIN (the muslin's stop). Known
# answer: tests/test_garment_pull.py test_hang_sheet_from_its_top_edge.
STYLE_HANG = False
HANG_G = 0.004  # m: the free move a round the weight would make (force = HANG_G x HANG_PROX x rest area / mean)
HANG_PROX = 0.0025  # the hang's proximal weight (x a cot weight): small, so the free modes (a panel's swing) move
HANG_STEP = 0.004  # m: the most a vertex moves in one hang round
HANG_STRAIN = 0.01  # the most the weight stretches a thread
HANG_ITERS = 1500  # (the sheet KAT: 400 rounds left the hem 44 mm back; 1500: 9 mm)
HANG_SWEEPS = 4  # Jacobi sweeps of the thread cap a round

# CANVAS / INTERFACING STIFFNESS IN STYLING (canvas thread, 2026-10-23; bending.py): the styling solve was bending-free
# (C142: every bending variant then roughened the shirt's collar), so a canvassed chest, a lapel, a collar and stand kept
# their shape only while HELD. STYLE_BEND adds bending.Bending to FlatARAP's global step: per vertex weights from the
# mesh's "bend_w" (bending.weights: fabric x interfacing kind), rest = the cloth's shape when the solve was built (the
# fit: a canvas is moulded and steamed to it, a collar made to its roll; a fold present at the start stays a fold),
# overall STYLE_BEND_W x the cot weights' scale. Plain cloth (weight 1) keeps STYLE_BEND_PLAIN of it, resting FLAT
# (cloth's own rest; only interfaced cloth is made to a shape).
STYLE_BEND = __import__("os").environ.get("GP_STYLE_BEND", "0") == "1"
STYLE_BEND_W = float(__import__("os").environ.get("GP_STYLE_BEND_W", "5.0"))
# THREADS FIRST (canvas s2, Joe: "it shouldn't really be a choice between stiffness and stretch"): with STYLE_BEND on,
# every round projects each face's warp / weft back within max(its length when the STYLING started (_bend_rest), 1 + STYLE_THREAD_CAP)
# (_thread_cap), so the bending acts only within the shapes the threads allow; a pull then stops earlier, never
# stretches further. Env GP_THREAD_FIRST=0 for the A/B.
STYLE_THREAD_FIRST = __import__("os").environ.get("GP_THREAD_FIRST", "1") == "1"
STYLE_THREAD_CAP = float(__import__("os").environ.get("GP_THREAD_CAP", "0.01"))
STYLE_THREAD_FIRST_ALL = __import__("os").environ.get("GP_THREAD_FIRST_ALL", "0") == "1"  # (A/B: every styling solve, bending or not)
STYLE_THREAD_FINAL = 60  # bending-free rounds at most at the end of a solve, until every face is within its bound
STYLE_THREAD_TOL = 0.002  # (a thread this far past its bound counts as within it)
STYLE_THREAD_ROUNDS = int(__import__("os").environ.get("GP_THREAD_ROUNDS", "2"))  # bending-free rounds a round
STYLE_BEND_PLAIN = float(__import__("os").environ.get("GP_STYLE_BEND_PLAIN", "0.0"))  # (x a plain vertex's weight 1)

STEP = 0.003  # m: a handle's move per step
TOL = 0.005  # stretch p99 allowed above the least the pull has reached (0.5 %: the shirt's knee, module docstring)
MAX_MOVE = 0.08  # m: the farthest a pull goes
ITERS = 12  # local / global rounds per step, from where the cloth was (few on purpose: module docstring)
RELAX_ITERS = 20  # before a pull / turn: the free cloth relaxed against the pattern
SETTLE_ITERS = 10  # after the pull: the cloth settled with the handles held where they stopped
CONFIRM_ITERS = 120  # a step that reads over tol is re-solved up to this many more rounds before the pull stops there
TURN_ROUNDS = 2  # a turning grip: fit-and-pin rounds per step
PATCH = 0.025  # m (pattern): the cloth a point handle grabs round the point (u25)
TURN_PATCH = 0.015  # m (pattern): a turn grips the cloth this near what it names (q40: the band end as an area)
HOLD_ITERS = 20  # a "relax" op's rounds
PROBE_ITERS = 4  # dir "easy": rounds per probed direction
FEATHER_AFTER = ("pull",)  # ops after which a feathered band is drawn back
MIRROR_REACH = 0.03  # m: a handle's mirror partner is the one whose lead is this near its mirror image
CONVERGED = 1e-5  # m: the confirm stops early once no vertex moves more than this in a round
FASTENED = 0.008  # m: a closure pair this near on the fit is done up (garment_reads.BUTTON_DONE_MM)
BUTTON_HOLD = 0.008  # m (pattern): a fastened button holds its cloth this near both of its vertices (hold_mask)
WOVEN_STYLE = __import__("os").environ.get("GP_WOVEN_STYLE", "1") == "1"  # DEFAULT (C168 / C169): see FlatARAP
# WOVEN_STYLE's undriven faces (no fixed vertex: nothing holds, grips or pins them) take the fit's SHEAR_FREE (C166:
# where nothing drives the cloth it does not shear); env GP_STYLE_SHEAR_FREE=<w> | "off" for the A/B (C169)
_SF = __import__("os").environ.get("GP_STYLE_SHEAR_FREE", "fit")
SHEAR_LOCK_NOISE = 1.0  # deg: a piece already past the jamming angle is jammed once its shear p99 rises this much more
SIDE_MIN = 0.015  # m: a "side" is taken only from a point at least this far off x = 0
_HE = ((0, 1, 2), (1, 2, 0), (2, 0, 1))


FLOOR_GAP = None  # m: the least a layer lies off its floor (None: pattern_form.THICK, one cloth)
FLOOR_REACH = 1.5  # x the floor's LOCAL edge (its nearest vertex's longest edge, C173): a vertex is held off a floor only
# where it stands over it (C124's rule). Was x the floor's MEDIAN edge: a front meshed fine at its lapel rows and coarse
# under its pocket flap (median 5 mm, 10-12 mm between vertices there) left 3-19 of each flap's 20 free vertices with no
# floor from the start, and they sank 6-25 mm through the front (Garrett jacket fit round 30 / 31)


FLOOR_REACH_CAP = 3.0
# A FLOOR HAS A SIDE (canvas s3, C197): a layer floor pushes a vertex out only from the side it started on. Two ways the
# shirt's open collar (a thin two-sided leaf beside the jacket's gorge) tore the jacket's plain lapel cloth 260 % in the
# open styling's FIRST relax (front plain p99 9 -> 18 %, then 67 % by the end): (1) a vertex BEHIND the floor (d < 0)
# but not yet over it was given the gap, so when it came over it was shoved through the leaf to its far side (12 mm in a
# round); (2) next to a thin leaf the nearest floor vertex flips between its two faces, so neighbours were pushed in
# opposite directions. Now a vertex behind its floor at the start keeps its own depth (never pushed through from
# behind), and a push applies only while the floor normal under the vertex agrees with the one it is tracked on
# (cos > FLOOR_SIDE_COS; followed round by round, so a slide round the body turns with it). GP_FLOOR_SIDE=0 for the A/B.
FLOOR_SIDE = __import__("os").environ.get("GP_FLOOR_SIDE", "1") == "1"
FLOOR_SIDE_COS = 0.5
# THREADS FIRST FOR A PINNED MOVE (canvas s3, C198): a pull drags its grip and smooth_border pins its border, then the
# rest is re-solved; their stops read the p99 (+ tol), so 1 % of the faces could tear: the open jacket's last two edge
# smooths (break .. cutawayTop, to the chord) took the canvassed lapel's worst faces 35 -> 154 % at p99 + 3 points, its
# hem pull down (6 mm) the plain faces by the grip 40 -> 91 %. With it a step / round is refused once any face's warp /
# weft passes max(its op-start strain, STYLE_THREAD_CAP) + BORDER_LOCAL_TOL (a pull reads it on the converged solve).
# Per op, "thread_stop": true (the jacket's open wear); not yet for every op: the shirt's collar-point pull stretches the
# faces at its grips at its first step, its open-collar smooths stopped early (3 test_garment_pull reds).
BORDER_LOCAL_STOP = __import__("os").environ.get("GP_BORDER_LOCAL", "1") == "1"
BORDER_LOCAL_TOL = 0.02
FLOOR_CONTACT = __import__("os").environ.get("GP_FLOOR_CONTACT", "1") == "1"  # (FlatARAP.solve: floor pushes held, C197)
FLOOR_SIDE_TRACK = __import__("os").environ.get("GP_FLOOR_SIDE_TRACK", "1") == "1"  # (A/B: rule (2) alone off)


def _local_reach(V, Fs):
    """FLOOR_REACH x each vertex's longest edge (0 for a vertex in no face), at most FLOOR_REACH_CAP x the median edge
    (a sliver's long edge read 50 mm on Garrett's front)."""
    V, Fs = np.asarray(V, float), np.asarray(Fs, int).reshape(-1, 3)
    r = np.zeros(len(V))
    es = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        e = np.linalg.norm(V[Fs[:, a]] - V[Fs[:, b]], axis=1)
        np.maximum.at(r, Fs[:, a], e)
        np.maximum.at(r, Fs[:, b], e)
        es.append(e)
    cap = FLOOR_REACH_CAP * float(np.median(np.concatenate(es))) if len(Fs) else 0.0
    return FLOOR_REACH * np.minimum(r, cap)


def _signed_i(surf, P):
    """pattern_form._Surface.signed with the nearest surface vertex: (d, normal, dist, index)."""
    dist, i = surf.tree.query(P)
    return np.sum((P - surf.V[i]) * surf.N[i], 1), surf.N[i], dist, i


def layer_floor(M: dict, X: np.ndarray, body=None, under=None, gap: float | None = None, flaps: bool = True) -> list:
    """THE FIT'S LAYER ORDER AS A FLOOR FOR STYLING (C157 / C170): the styling solve is a flat-pattern ARAP with no
    contact, so a pull let the lapels go through their own fronts, the pocket flaps sink into theirs and the fronts into
    the shirt (Garrett jacket round 27). The layers, as the fit stacked them: the garment over the BODY and over the
    garment UNDER it (under = (V, F), e.g. the shirt as pressed under a jacket), every fold's turned FLAP over its own
    base (folds._geom: the lapel over its front), every STITCHED patch (M["stitch"]: a pocket flap) over the piece it
    is stitched to. Pass the list as style(..., floor=...): after every solve round, a free vertex that went nearer a
    floor than min(gap, its start distance) is put back on it along the floor's normal (oriented off the body).
    Returns [{"v", "level", "surf" | ("bv", "bF"), "reach", "ref", "name"}]: floors with no body are oriented by their
    own centroid. A vertex not over the body / under garment at the start gets the gap (it may slide over it); a flap
    or patch vertex not over its base at the start has no floor (it is sewn to that base and doesn't slide)."""
    from . import pattern_form as pf_, folds as fm_
    from .cloth_made import outward
    X = np.asarray(X, float)
    gap = (pf_.THICK if FLOOR_GAP is None else FLOOR_GAP) if gap is None else gap
    bvf = _body_vf(body)
    ref = pf_._Surface(bvf[0], outward(*bvf)) if bvf is not None else None
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    names = list(M["names"])

    def reach(V, Fs):  # (per floor vertex, C173)
        return _local_reach(V, Fs)

    def level(d, dist, tang, rch, slides=True):
        # (a vertex over its floor at the start keeps min(gap, how far off it stood): one that started through is never
        # pushed out. One not over it yet gets the gap where the cloth SLIDES over its floor (the body, the garment
        # under: the strip KAT) and no floor where it doesn't: a flap is sewn to its base and stays over the same
        # cloth; given the gap, Garrett's collar fall, hanging past the stand's edge, was pushed off it (collar + stand
        # shear p99 10 -> 20 deg in one relax, fit round 30))
        lev = np.full(len(d), gap if slides else -np.inf)
        over = (tang < rch) & (dist < 0.03)
        lev[over] = np.minimum(gap, d[over])
        if FLOOR_SIDE and slides:  # (A FLOOR HAS A SIDE, C197: behind it at the start, never pushed through it from behind)
            behind = ~over & (d < 0)
            lev[behind] = d[behind]
        return lev

    out = []
    allv = np.arange(len(X))
    stat = [("body", bvf[0], outward(*bvf))] if bvf is not None else []
    if under is not None:
        stat.append(("under", np.asarray(under[0], float), np.asarray(under[1], int)))
    for nm, V, Fs in stat:
        sf = pf_._Surface(V, Fs, ref=ref if nm != "body" else None) if nm != "body" else ref
        d, _, dist, ni = _signed_i(sf, X)
        rch = reach(sf.V, Fs)
        tang = np.sqrt(np.maximum(dist ** 2 - d ** 2, 0.0))
        out.append({"name": nm, "v": allv, "level": level(d, dist, tang, rch[ni]), "surf": sf, "reach": rch, "ref": ref,
                    "n0": sf.N[ni]})
    if flaps:
        fl = fm_.flap_faces(M, F)
        for nm in sorted({fd["piece"] for fd in M.get("folds") or []}):
            k = names.index(nm)
            fpc = pid[F[:, 0]] == k
            if not (fl & fpc).any() or not (~fl & fpc).any():
                continue
            bF = F[fpc & ~fl]
            bv = np.unique(bF)
            fv = np.setdiff1d(np.unique(F[fpc & fl]), bv)
            # THE BASE ACROSS A SEAM (C119, pattern_form.flap_through_base's rule): a fold whose own base side is narrow
            # (a two-piece collar's fall, its roll a few mm above the seam) lies on the piece sewn there (the stand).
            # Against its 6 mm strip alone the floor pushed the fall off the strip's edge: Garrett's collar + stand
            # shear p99 10 -> 24 deg in one relax (fit round 30)
            narrow = False
            for fd in M["folds"]:
                if fd["piece"] == nm and len(fd["rows"]):
                    g_ = fm_._geom(M, fd)
                    ob_ = np.setdiff1d(np.asarray(g_["sel"]), np.where(np.asarray(g_["flap0"]))[0])
                    narrow |= bool(len(ob_)) and float(np.asarray(g_["d0"])[ob_].max()) < pf_.BASE_NARROW
            sw = np.asarray(M.get("sew") if M.get("sew") is not None else np.zeros((0, 2), int), int).reshape(-1, 2)
            if pf_.BASE_ACROSS_SEAM and narrow and len(sw):
                ob = np.zeros(len(X), bool)
                ob[bv] = True
                oth = sorted({int(pid[b]) for a, b in sw if ob[a] and pid[b] != k} |
                             {int(pid[a]) for a, b in sw if ob[b] and pid[a] != k})
                if oth:
                    bF = np.r_[bF, F[np.isin(pid[F[:, 0]], oth)]]
                    bv = np.unique(bF)
            if len(fv):
                out.append(_dyn_floor(f"flap:{nm}", X, fv, bv, bF, ref, gap, None, level))
        st = np.asarray(M.get("stitch") if M.get("stitch") is not None else [], int).reshape(-1, 2)
        for pa in sorted({int(p) for p in pid[st.ravel()]}) if len(st) else []:
            other = {int(pid[b]) if pid[a] == pa else int(pid[a]) for a, b in st if pa in (pid[a], pid[b])} - {pa}
            if not other or (pid == pa).sum() >= min((pid == o).sum() for o in other):
                continue  # (the patch is the smaller piece of a stitched pair)
            bF = F[np.isin(pid[F[:, 0]], sorted(other))]
            bv = np.unique(bF)
            fv = np.setdiff1d(np.where(pid == pa)[0], np.unique(st.ravel()))
            if len(fv):
                out.append(_dyn_floor(f"patch:{names[pa]}", X, fv, bv, bF, ref, gap, None, level))
    return out


def _dyn_floor(name, X, fv, bv, bF, ref, gap, rch, level):
    from . import pattern_form as pf_
    ix = -np.ones(len(X), int)
    ix[bv] = np.arange(len(bv))
    d, _, dist, ni = _signed_i(pf_._Surface(X[bv], ix[bF], ref=ref), X[fv])  # (_ = the floor normal under each, C197)
    tang = np.sqrt(np.maximum(dist ** 2 - d ** 2, 0.0))
    rch = _local_reach(X[bv], ix[bF])  # (per base vertex, C173)
    return {"name": name, "v": fv, "level": level(d, dist, tang, rch[ni], slides=False), "surf": None, "bv": bv, "bF": ix[bF],
            "reach": rch, "ref": ref, "n0": _, "anchor": ni}


def _bind_floor(floor, inv):
    """layer_floor's floors on a welded mesh (FlatARAP.inv): vertex ids -> welded ids, the vertices with no floor
    (level -inf) dropped."""
    if not floor:
        return []
    out = []
    for fl in floor:
        keep = np.isfinite(fl["level"])
        if not keep.any():
            continue
        b = dict(fl, w=inv[np.asarray(fl["v"])[keep]], level=np.asarray(fl["level"])[keep])
        if fl.get("n0") is not None:  # (the side each vertex is tracked on, C197: _floor writes it back, so the next op starts from it)
            fl["n0"] = np.asarray(fl["n0"], float)
            b["n0"], b["_src"], b["_keep"] = np.array(fl["n0"][keep]), fl, np.where(keep)[0]
        if fl.get("anchor") is not None:
            b["anchor"] = np.asarray(fl["anchor"])[keep]
        if fl.get("surf") is None:
            b["bw"] = inv[np.asarray(fl["bv"])]
        out.append(b)
    return out


class FlatARAP:
    """Per-face ARAP against the flat pattern on the WELDED mesh (sewn pairs one vertex). W = welded positions.
    WOVEN_STYLE (DEFAULT since C169; env GP_WOVEN_STYLE=0 for the isometric A/B): the local step as the muslin fit's (pattern_form.WOVEN:
    (P_s + SHEAR_STIFF R) / (1 + SHEAR_STIFF), pattern x / y as the threads). WHY: the styling solve is isometric
    (shear-stiff) on a woven fit, so its rounds take the fit's shear back as length: wf_simon's closed muslin collar
    (right tip warp p5 -4.4 %, the fall's roll side -3 to -8 %), band ends turned, read tip crumple 0.146 vs closed
    0.086 (the iso fit 0.101; with the turn run to convergence BOTH crumple, 0.27 / 0.28: the early stop hid it). With
    it: tips 0.039 / 0.084 (= closed), points 147 apart (concept ~147); but the edge-stretch reads (pull / smooth
    stops, tip stretch) counted the shear it allows: 4 test_garment_pull reds (the wobble smooth, the spike reads'
    smooth stopping at 0 rounds, the open-by-default stretch). So every stop reads THREADS (thread_p99, C169), with
    a shear lock at pattern_form.SHEAR_LOCK_DEG: "until it would stretch" is until a thread would stretch or the
    weave would jam."""

    def __init__(self, M: dict, X: np.ndarray):
        F = np.asarray(M["F"], int)
        uv = _thread_frames(M)  # (the pattern in its thread frame: ARAP doesn't care, WOVEN_STYLE's threads do)
        n0 = len(uv)
        par = np.arange(n0)

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i
        sew = np.asarray(M.get("sew") if M.get("sew") is not None else [], int).reshape(-1, 2)
        for a, b in sew:
            ra, rb = find(a), find(b)
            if ra != rb:
                par[rb] = ra
        root = np.array([find(i) for i in range(n0)])
        _, self.inv = np.unique(root, return_inverse=True)
        self.n = int(self.inv.max()) + 1
        U = uv[F]
        WF = self.inv[F]
        good = (WF[:, 0] != WF[:, 1]) & (WF[:, 1] != WF[:, 2]) & (WF[:, 0] != WF[:, 2])
        e1, e2 = U[:, 1] - U[:, 0], U[:, 2] - U[:, 0]
        good &= np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) > 1e-10
        self.U, self.WF = U[good], WF[good]
        Wt, I, J = [], [], []
        for a, b, c in _HE:  # cot weight of half-edge (a, b) = 0.5 cot(angle at c), from the rest triangle
            p, q = self.U[:, a] - self.U[:, c], self.U[:, b] - self.U[:, c]
            cot = (p * q).sum(1) / np.maximum(np.abs(p[:, 0] * q[:, 1] - p[:, 1] * q[:, 0]), 1e-12)
            Wt.append(np.clip(0.5 * cot, 1e-4, 5.0))
            I.append(self.WF[:, a])
            J.append(self.WF[:, b])
        self.Wt = np.stack(Wt, 1)
        I, J = np.stack(I, 1).ravel(), np.stack(J, 1).ravel()
        w = self.Wt.ravel()
        Lw = coo_matrix((np.r_[w, w], (np.r_[I, J], np.r_[J, I])), shape=(self.n, self.n)).tocsr()
        self.L = (diags(np.asarray(Lw.sum(1)).ravel()) - Lw).tocsr()
        self.bend = None
        bw = M.get("bend_w")
        if STYLE_BEND and bw is not None and STYLE_BEND_W > 0:  # (CANVAS STIFFNESS: bending.Bending, rest = the start)
            from . import bending as bd_
            bw = np.asarray(bw, float)
            bw = np.where(bw > 1.0 + 1e-9, bw, bw * STYLE_BEND_PLAIN)  # (plain cloth: STYLE_BEND_PLAIN of its weight)
            wv = np.zeros(self.n)
            np.maximum.at(wv, self.inv, bw)
            self.bend = bd_.Bending(self.WF, self.U, self.n, wv, STYLE_BEND_W, rest=self.weld(np.asarray(
                M["_bend_rest"] if M.get("_bend_rest") is not None else X, float)), flat_below=STYLE_BEND_PLAIN)
            self.L0 = self.L
            self.L = (self.L + self.bend.K).tocsr()
        if (STYLE_THREAD_FIRST and self.bend is not None) or STYLE_THREAD_FIRST_ALL:  # THREADS FIRST: each face's
            # warp / weft kept within max(its styling-start length, 1 +/- cap)
            self.L0 = getattr(self, "L0", None) if self.bend is not None else self.L
            self.Dinv0 = np.linalg.inv(np.stack([self.U[:, 1] - self.U[:, 0], self.U[:, 2] - self.U[:, 0]], -1))
            W0 = self.weld(np.asarray(M["_bend_rest"] if M.get("_bend_rest") is not None else X, float))  # (the
            # styling's start, as the bending's rest: a per-op start would ratchet the bound up op by op)
            ln0 = np.linalg.norm(np.stack([W0[self.WF[:, 1]] - W0[self.WF[:, 0]], W0[self.WF[:, 2]] - W0[self.WF[:, 0]]], -1)
                                 @ self.Dinv0, axis=1)
            self.thread_hi = np.maximum(ln0, 1.0 + STYLE_THREAD_CAP)
            self.thread_lo = np.minimum(ln0, 1.0 - STYLE_THREAD_CAP)  # (nor shorter: a woven buckles, it doesn't shrink)
        self._lu, self._lu0 = {}, {}
        self.floor, self.floor_pushed = _bind_floor(M.get("_floor"), self.inv), 0  # (style(floor=...): C170)
        self.shear = self.shear_free = None
        if WOVEN_STYLE:
            from . import pattern_form as pf_
            if pf_.WOVEN:
                Dm = np.stack([self.U[:, 1] - self.U[:, 0], self.U[:, 2] - self.U[:, 0]], -1)
                self.Dinv, self.shear = np.linalg.inv(Dm), pf_.SHEAR_STIFF
                self.shear_free = None if _SF == "off" else pf_.SHEAR_FREE if _SF == "fit" else float(_SF)

    def weld(self, X: np.ndarray) -> np.ndarray:
        W = np.zeros((self.n, 3))
        np.add.at(W, self.inv, X)
        return W / np.bincount(self.inv, minlength=self.n)[:, None]

    def unweld(self, W: np.ndarray) -> np.ndarray:
        return W[self.inv]

    def welded_mask(self, mask: np.ndarray) -> np.ndarray:
        out = np.zeros(self.n, bool)
        out[self.inv[np.asarray(mask, bool)]] = True
        return out

    def _factors(self, fixed: np.ndarray, hang: bool, tf: bool):
        """The global step's factorizations for one fixed set (kept for the last few sets: a solve's floor contacts
        add to its fixed set, C197, and the next solve starts from the op's own again)."""
        key = np.packbits(fixed).tobytes() + (b"h" if hang else b"")
        fi, ci = np.where(~fixed)[0], np.where(fixed)[0]
        if key not in self._lu:
            Lf = self.L[fi]
            Aff = Lf[:, fi] + (diags(np.full(len(fi), HANG_PROX)) if hang else 0)
            if len(self._lu) >= 4:
                self._lu.pop(next(iter(self._lu)))
            self._lu[key] = (splu(Aff.tocsc()), Lf[:, ci].tocsr())
        lu, Lfc = self._lu[key]
        lu0 = L0fc = None
        if tf:  # THREADS FIRST: the bending-free (ARAP / woven only) system for the rounds that give the threads back
            k0 = key + b"t"
            if k0 not in self._lu0:
                L0f = self.L0[fi]
                if len(self._lu0) >= 4:
                    self._lu0.pop(next(iter(self._lu0)))
                self._lu0[k0] = (splu(L0f[:, fi].tocsc()), L0f[:, ci].tocsr())
            lu0, L0fc = self._lu0[k0]
        return fi, ci, lu, Lfc, lu0, L0fc

    def solve(self, Y: np.ndarray, fixed: np.ndarray, iters: int = ITERS, eps: float | None = None,
              hang: bool = False) -> np.ndarray:
        """Up to `iters` local / global rounds from Y, stopping once no vertex moves more than `eps` in one; vertices
        `fixed` (welded mask) stay where Y has them. hang: the free cloth's WEIGHT (HANG: a weak downward force per
        rest area against a small proximal weight, each round's move clamped to HANG_STEP, the threads capped at
        HANG_STRAIN; the floors as ever). FLOOR_CONTACT (C197): a vertex the floor put back is held where the floor
        put it for the rest of this solve, so the cloth round it follows it in the next global step (pushed after the
        threads' cap and fought by the next round, the lapel's floor shoved its vertices up to 9 mm a round, 190 mm in
        one relax, and tore the canvassed lapel 122 %)."""
        if hang and getattr(self, "mass", None) is None:
            a_ = 0.5 * np.abs((self.U[:, 1, 0] - self.U[:, 0, 0]) * (self.U[:, 2, 1] - self.U[:, 0, 1])
                              - (self.U[:, 1, 1] - self.U[:, 0, 1]) * (self.U[:, 2, 0] - self.U[:, 0, 0]))
            m_ = np.zeros(self.n)
            for c in range(3):
                np.add.at(m_, self.WF[:, c], a_ / 3)
            self.mass = m_ / max(float(m_.mean()), 1e-12)
            self.Dinv0 = np.linalg.inv(np.stack([self.U[:, 1] - self.U[:, 0], self.U[:, 2] - self.U[:, 0]], -1))
        U, WF, Wt = self.U, self.WF, self.Wt
        Y = Y.copy()
        tf = getattr(self, "thread_hi", None) is not None
        fixed = np.asarray(fixed, bool)
        fx = fixed.copy()  # (the op's fixed set + this solve's floor contacts)
        fi, ci, lu, Lfc, lu0, L0fc = self._factors(fx, hang, tf)

        def floor_round(Y):
            nonlocal fx, fi, ci, lu, Lfc, lu0, L0fc
            self._pushed_static = np.zeros(self.n, bool)
            Yp = self._floor(Y, fx)
            if FLOOR_CONTACT:  # (static floors only: the body, the garment under. A flap's floor is its own moving base:
                # pinned in place while the base moved, the canvassed lapel tore 256 %)
                new = self._pushed_static & ~fx
                if new.any():
                    fx = fx | new
                    fi, ci, lu, Lfc, lu0, L0fc = self._factors(fx, hang, tf)
            return Yp
        for _ in range(iters):
            fall = HANG_G * HANG_PROX * self.mass[fi] if hang else None
            rhs = self._arap_rhs(Y, fixed)
            if self.bend is not None:  # (the rest curvature along the current direction: bending.Bending.rhs)
                rhs = rhs + self.bend.rhs(Y)
            r = rhs[fi] - Lfc @ Y[ci]
            if hang:  # (HANG: the proximal weight and the weight; a round moves a vertex at most HANG_STEP)
                r = r + HANG_PROX * Y[fi]
                r[:, 2] -= fall
            Yf = np.column_stack([lu.solve(r[:, k]) for k in range(3)])
            if hang:
                dY = Yf - Y[fi]
                ln = np.linalg.norm(dY, axis=1, keepdims=True)
                Yf = Y[fi] + dY * np.minimum(1.0, HANG_STEP / np.maximum(ln, 1e-12))
            dmax = float(np.abs(Yf - Y[fi]).max()) if len(fi) else 0.0
            Y[fi] = Yf
            if hang:  # (the threads capped: the weight never stretches a thread past HANG_STRAIN)
                Y = self._thread_cap(Y, fx)
            if tf:  # THREADS FIRST: the bending acts within the threads. Rounds of the bending-free solve give back the
                # length the bending bought (a Jacobi cap alone can't: a strip stretched end to end stayed 12.4 %), then
                # the cap takes off what is still past each face's bound
                for _r in range(STYLE_THREAD_ROUNDS):
                    r0 = self._arap_rhs(Y, fixed)[fi] - L0fc @ Y[ci]
                    Y[fi] = np.column_stack([lu0.solve(r0[:, k]) for k in range(3)])
                Y = self._thread_cap(Y, fx, hi=self.thread_hi, lo=self.thread_lo)
            if self.floor:  # THE LAYER FLOOR (C170): what went under its floor this round is put back on it
                Y = floor_round(Y)
            if eps is not None and dmax < eps:
                break
        if tf:  # THREADS FIRST, the last word: bending-free rounds until no face is past its bound (the bending chose the
            # shape on the way; the threads have the last say), floors kept
            for _r in range(STYLE_THREAD_FINAL):
                Fg = np.stack([Y[WF[:, 1]] - Y[WF[:, 0]], Y[WF[:, 2]] - Y[WF[:, 0]]], -1) @ self.Dinv0
                ln_ = np.linalg.norm(Fg, axis=1)
                if max(float((ln_ - self.thread_hi).max()), float((self.thread_lo - ln_).max())) <= STYLE_THREAD_TOL:
                    break
                r0 = self._arap_rhs(Y, fixed)[fi] - L0fc @ Y[ci]
                Y[fi] = np.column_stack([lu0.solve(r0[:, k]) for k in range(3)])
                Y = self._thread_cap(Y, fx, hi=self.thread_hi, lo=self.thread_lo)
                if self.floor:
                    Y = floor_round(Y)
        return Y

    def _arap_rhs(self, Y: np.ndarray, fixed: np.ndarray) -> np.ndarray:
        """The local step (each face's closest rotation of its pattern, WOVEN: warp / weft at their length, shear at
        its weight) as the global step's right-hand side (welded, (n, 3))."""
        U, WF, Wt = self.U, self.WF, self.Wt
        S = np.zeros((len(WF), 3, 2))
        for k, (a, b, _c) in enumerate(_HE):
            S += Wt[:, k, None, None] * (Y[WF[:, a]] - Y[WF[:, b]])[:, :, None] * (U[:, a] - U[:, b])[:, None, :]
        Uu, _, Vt = np.linalg.svd(S, full_matrices=False)
        R = Uu @ Vt  # (m, 3, 2): each face's closest orthonormal map from its pattern to its current edges
        if self.shear is not None:  # WOVEN (the fit's cloth): warp / weft at their length, shear at its weight
            Fg = np.stack([Y[WF[:, 1]] - Y[WF[:, 0]], Y[WF[:, 2]] - Y[WF[:, 0]]], -1) @ self.Dinv
            Ps = Fg / np.maximum(np.linalg.norm(Fg, axis=1, keepdims=True), 1e-12)
            sh = self.shear
            if self.shear_free is not None:  # (undriven faces, no fixed vertex: the fit's SHEAR_FREE, C166)
                sh = np.where(fixed[WF].any(1), self.shear, self.shear_free)[:, None, None]
            R = (Ps + sh * R) / (1.0 + sh)
        rhs = np.zeros((self.n, 3))
        for k, (a, b, _c) in enumerate(_HE):
            v = Wt[:, k, None] * np.einsum("mij,mj->mi", R, U[:, a] - U[:, b])
            np.add.at(rhs, WF[:, a], v)
            np.add.at(rhs, WF[:, b], -v)
        return rhs

    def _thread_cap(self, Y: np.ndarray, fixed: np.ndarray, sweeps: int | None = None, hi=None, lo=None) -> np.ndarray:
        """Jacobi thread-strain limit (pattern_form._thread_limit on the welded faces): a face whose warp or weft is
        longer than 1 + HANG_STRAIN (or `hi`, per face: THREADS FIRST) mapped back to it about its centroid; fixed vertices stay."""
        U, WF = self.U, self.WF
        for _ in range(HANG_SWEEPS if sweeps is None else sweeps):
            Fg = np.stack([Y[WF[:, 1]] - Y[WF[:, 0]], Y[WF[:, 2]] - Y[WF[:, 0]]], -1) @ self.Dinv0
            ln = np.linalg.norm(Fg, axis=1)
            if hi is not None:  # (THREADS FIRST: each face's own bounds, longer or shorter)
                sc = np.clip(ln, np.asarray(lo) if lo is not None else 0.0, np.asarray(hi)) / np.maximum(ln, 1e-12)  # ((faces, 2) warp / weft)
            else:
                sc = np.clip(ln, 1.0 - HANG_STRAIN, 1.0 + HANG_STRAIN) / np.maximum(ln, 1e-12)  # (nor shorter: a woven buckles)
            bad = (np.abs(sc - 1.0) > 1e-9).any(1)
            if not bad.any():
                break
            Fb = Fg[bad] * sc[bad][:, None, :]
            ub, fb = U[bad], WF[bad]
            tgt = Y[fb].mean(1)[:, None, :] + np.einsum("bij,bcj->bci", Fb, ub - ub.mean(1)[:, None, :])
            cor = np.zeros_like(Y)
            cnt = np.zeros(len(Y))
            for c in range(3):
                np.add.at(cor, fb[:, c], tgt[:, c] - Y[fb[:, c]])
                np.add.at(cnt, fb[:, c], 1.0)
            cor[fixed] = 0.0
            Y = Y + cor / np.maximum(cnt, 1.0)[:, None]
        return Y

    def _floor(self, Y: np.ndarray, fixed: np.ndarray) -> np.ndarray:
        """Each floor (layer_floor) on the welded positions: a free vertex nearer its floor than its LEVEL (min(gap, how
        far it stood off it at the start): a layer that started through is never pushed out, only kept from going
        deeper) is moved out along the floor's normal to it; only where it stands OVER the floor (sideways within the
        floor's reach of its nearest floor vertex)."""
        from . import pattern_form as pf_
        for fl in self.floor:
            w = fl["w"]
            free = ~fixed[w]
            if not free.any():
                continue
            w, lev = w[free], fl["level"][free]
            surf = fl["surf"] if fl["surf"] is not None else \
                pf_._Surface(Y[fl["bw"]], fl["bF"], ref=fl["ref"])
            if FLOOR_SIDE and fl.get("anchor") is not None:  # (A FLOOR HAS A SIDE, C197: a flap / patch is sewn to its
                # base and stays over the SAME cloth, so it is read against the base vertex it started over, not the
                # nearest: Garrett's left lapel lay where two sheets of its base met (the front, the turn of the roll),
                # neighbours took their nearest from either and were shoved apart up to 9 mm a round: canvas 122 %)
                # (while it is still over that vertex; one that has slid off it, as a pocket flap over a sliding front,
                # is read against the nearest: anchored only, 10 of 25 flap vertices sank up to 18 mm)
                d, n, dist, ni = _signed_i(surf, Y[w])
                na = fl["anchor"][free]
                dv = Y[w] - surf.V[na]
                da = np.sum(dv * surf.N[na], 1)
                ta = np.sqrt(np.maximum((dv ** 2).sum(1) - da ** 2, 0.0))
                on = ta < np.asarray(fl["reach"])[na]
                d, n, ni = np.where(on, da, d), np.where(on[:, None], surf.N[na], n), np.where(on, na, ni)
                dist = np.where(on, np.linalg.norm(dv, axis=1), dist)
            else:
                d, n, dist, ni = _signed_i(surf, Y[w])
            tang = np.sqrt(np.maximum(dist ** 2 - d ** 2, 0.0))
            m = (d < lev) & (tang < np.asarray(fl["reach"])[ni])
            if FLOOR_SIDE and FLOOR_SIDE_TRACK and fl.get("n0") is not None:  # (A FLOOR HAS A SIDE, C197: pushed only from the side the vertex
                # is tracked on; the tracked normal follows where the floor under it turns gradually)
                n0 = fl["n0"][free]
                agree = (n * n0).sum(1) > FLOOR_SIDE_COS
                m &= agree
                ix_ = np.where(free)[0][agree]
                fl["n0"][ix_] = n[agree]
                if fl.get("_src") is not None:  # (written back to the styling's floor list: the next op starts from it)
                    fl["_src"]["n0"][fl["_keep"][ix_]] = n[agree]
            if m.any():
                Y[w[m]] += (lev[m] - d[m])[:, None] * n[m]
                self.floor_pushed += int(m.sum())
                if fl["surf"] is not None and getattr(self, "_pushed_static", None) is not None:
                    self._pushed_static[w[m]] = True
        return Y


def edge_stretch(M: dict, X: np.ndarray, pieces=None, free=None) -> np.ndarray:
    """|3D length / pattern length - 1| of every same-piece edge (on `pieces`, names or indices, when given; with
    `free`, a mask (n,), only the edges with a free vertex: held cloth can't be stretched by the move, and its own strain
    masked the read: Garrett's shirt fronts below the first button, held, carry 21-24 % p99 at the tuck and side seams,
    so the pull's read sat at 15.5 % whatever the collar did (2026-10-22, C147). NOT a stop any more (C169): an edge
    across the bias lengthens when a woven shears, so the stops read thread_p99 (threads + shear apart); the turn keeps
    the free-cloth mask (thread_faces free=), pull / smooth / relax the whole-piece read."""
    F = np.asarray(M["F"], int)
    uv = np.asarray(M["uv"], float)
    pid = np.asarray(M["piece"])
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    l0 = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)
    ok = (l0 > 1e-5) & (pid[E[:, 0]] == pid[E[:, 1]])
    if pieces is not None:
        ok &= np.isin(pid[E[:, 0]], _piece_ids(M, pieces))
    if free is not None:
        free = np.asarray(free, bool)
        ok &= free[E[:, 0]] | free[E[:, 1]]
    E, l0 = E[ok], l0[ok]
    return np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / l0 - 1)


def stretch_p99(M: dict, X: np.ndarray, pieces=None, free=None) -> float:
    s = edge_stretch(M, X, pieces, free)
    return float(np.percentile(s, 99)) if len(s) else 0.0


def _thread_frames(M: dict):
    """Per vertex-piece rest coordinates in the thread frame (weft, warp): the pattern rotated so the warp lies along
    piece grain (M["grain"]: {piece name: deg}, default 90 = warp along the pattern's y, as pattern_form._woven_setup)."""
    uv = np.asarray(M["uv"], float)
    g = M.get("grain") or {}
    if not g:
        return uv
    pid = np.asarray(M["piece"])
    ga = np.radians(np.array([float(g.get(nm, 90.0)) for nm in M["names"]]))[pid]
    warp = np.c_[np.cos(ga), np.sin(ga)]
    weft = np.c_[np.sin(ga), -np.cos(ga)]
    return np.c_[(uv * weft).sum(1), (uv * warp).sum(1)]


def thread_faces(M: dict, pieces=None, free=None):
    """The faces a thread read covers (all three vertices on one piece; on `pieces` when given; with `free`, a mask
    (n,), only faces with a free vertex) and their rest inverses in the thread frame: (F, Dinv)."""
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    q = _thread_frames(M)
    ok = (pid[F[:, 0]] == pid[F[:, 1]]) & (pid[F[:, 1]] == pid[F[:, 2]])
    if pieces is not None:
        ok &= np.isin(pid[F[:, 0]], _piece_ids(M, pieces))
    if free is not None:
        ok &= np.asarray(free, bool)[F].any(1)
    F = F[ok]
    Dm = np.stack([q[F[:, 1]] - q[F[:, 0]], q[F[:, 2]] - q[F[:, 0]]], -1)
    good = np.abs(np.linalg.det(Dm)) > 1e-14
    return F[good], np.linalg.inv(Dm[good])


def thread_strain(M: dict, X: np.ndarray, pieces=None, free=None, faces=None):
    """THREADS AND SHEAR APART (C166 / C169): per face its warp / weft strain |len - 1| (t, 2) and its shear (deg: the
    threads' angle off 90). A woven's edge across the bias lengthens when the cloth shears without any thread
    stretching; the threads are what stretch, the shear is limited by jamming (pattern_form.SHEAR_LOCK_DEG)."""
    F, Dinv = thread_faces(M, pieces, free) if faces is None else faces
    if not len(F):
        return np.zeros((0, 2)), np.zeros(0)
    Fg = np.stack([X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]]], -1) @ Dinv
    ln = np.linalg.norm(Fg, axis=1)
    c = np.abs((Fg[:, :, 0] * Fg[:, :, 1]).sum(1)) / np.maximum(ln[:, 0] * ln[:, 1], 1e-12)
    return np.abs(ln - 1), np.degrees(np.arcsin(np.clip(c, 0, 1)))


def thread_p99(M: dict, X: np.ndarray, pieces=None, free=None, faces=None):
    """(thread strain p99 (fraction, pooled), shear p99 (deg) PER PIECE (an array, in piece order)): what every styling
    stop reads (C169). Shear per piece because a pooled p99 hides a small piece jamming: wf_simon's points pulled open
    took front.L's free neck cloth to shear p99 39.7 deg (and threads 15.9 %) while the pooled read (collar + stand 12k
    faces, the fronts' free cloth 1.2k) said 20 deg."""
    F = (thread_faces(M, pieces, free) if faces is None else faces)
    t, sh = thread_strain(M, X, faces=F)
    if not len(sh):
        return 0.0, np.zeros(0)
    pid = np.asarray(M["piece"])[F[0][:, 0]]
    return float(np.percentile(t, 99)), np.array([float(np.percentile(sh[pid == p], 99)) for p in np.unique(pid)])


def _stop_key(read, lock) -> float:
    """One number to rank candidate moves by (dir "easy"): thread p99, a move past the shear lock last."""
    return read[0] + (1.0 if _jammed(read[1], lock) else 0.0)


def _shear_lock(sh0):
    """The shear each piece may reach: the jamming angle; a piece already past it (a band-end turn with no tol jams the
    fronts' free tops, 39-43 deg) may not shear further than SHEAR_LOCK_NOISE more."""
    from . import pattern_form as pf_
    sh0 = np.asarray(sh0, float)
    return np.where(sh0 < pf_.SHEAR_LOCK_DEG, pf_.SHEAR_LOCK_DEG, sh0 + SHEAR_LOCK_NOISE)


def _jammed(sh, lock) -> bool:
    return bool(np.any(np.asarray(sh) > lock))


def _shmax(sh) -> float:
    return round(float(np.max(sh)), 1) if len(sh) else 0.0


def _piece_ids(M, pieces):
    nm = list(M["names"])
    return [p if isinstance(p, (int, np.integer)) else nm.index(p) for p in pieces]


def vertex(M: dict, at) -> int:
    """A vertex index, or "piece:point" (M["points"]), or "piece:@closure" = that piece's vertex of the closure's TOP
    FASTENED pair (the first done button: a front's roll line runs from it to the neck point)."""
    if isinstance(at, (int, np.integer)):
        return int(at)
    if isinstance(at, str) and ":@" in at:
        return _top_fastened(M, *at.split(":@", 1))
    if isinstance(at, str) and ".." in at and "@" in at:  # "piece:a..b@t": the border's point at t of its length (C174)
        ch, t = at.rsplit("@", 1)
        return border_at(M, ch, float(t))
    P = M.get("points") or {}
    if at not in P:
        pre = at.split(":")[0] + ":"
        have = sorted(k for k in P if k.startswith(pre))
        raise ValueError(f"no garment point {at!r} (points on that piece: {', '.join(have) or 'none'})")
    return int(np.asarray(P[at]).reshape(-1)[0])


def _top_fastened(M: dict, piece: str, closure: str, X=None) -> int:
    """The vertex on `piece` of `closure`'s highest pair that is fastened (pairs within FASTENED on the fit; M["X"] or
    `X` gives the fit, else every pair counts and the highest by the pattern's order is the first listed)."""
    pid = np.asarray(M["piece"])
    k = _piece_ids(M, [piece])[0]
    X = M.get("_X") if X is None else X
    best = None
    for c in M.get("closures") or []:
        if c.get("name") != closure:
            continue
        for v in c.get("v") or []:
            v = [int(i) for i in np.asarray(v).ravel()]
            if X is not None and np.linalg.norm(X[v[0]] - X[v[-1]]) > FASTENED:
                continue
            mine = [i for i in v if pid[i] == k]
            if not mine:
                continue
            z = X[mine[0], 2] if X is not None else -len(best or [])
            if best is None or z > best[0]:
                best = (z, mine[0])
    if best is None:
        raise ValueError(f"no fastened pair of closure {closure!r} on {piece!r}")
    return best[1]


def vertices(M: dict, at) -> np.ndarray:
    """The vertices a handle grips: a vertex, "piece:point", "piece:a..b" (the piece's border from point a to b, the
    shorter way round: a hem, a cuff's edge, a front edge), or a list of those."""
    if isinstance(at, (list, tuple, np.ndarray)) and not isinstance(at, str):
        return np.unique(np.concatenate([vertices(M, a) for a in at]))
    if isinstance(at, str) and ".." in at and "@" in at:
        return np.array([vertex(M, at)], int)
    if isinstance(at, str) and at.count("..") > 1:
        return np.unique(border_chain(M, at))
    if isinstance(at, str) and ".." in at:
        from .cloth_release import pin_vertices
        try:
            return np.asarray(pin_vertices(M, at), int)
        except KeyError as e:
            raise ValueError(str(e).strip("'\"")) from None
    return np.array([vertex(M, at)], int)


def border_at(M: dict, at: str, t: float) -> int:
    """The vertex of border walk `at` ("piece:a..b") nearest t (0..1) of its length on the pattern: a hand gripping
    a front edge part-way down (C174: the jacket's edge below the break opened top-down, grips at 0.2 / 0.45)."""
    ch = border_chain(M, at)
    uv = np.asarray(M["uv"], float)[ch]
    s_ = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(uv, axis=0), axis=1))]
    return int(ch[int(np.argmin(np.abs(s_ - float(t) * s_[-1])))])


def border_chain(M: dict, at: str) -> np.ndarray:
    """The ORDERED vertices of a piece's border walk: "piece:a..b" (the shorter way round between two points) or
    "piece:a..b..c" (a to b, then b to c: the collar's outer edge point -> CB -> point). Walked along the boundary,
    never sorted by pattern x (that mixed in the front edges: a fake 172 deg kink, C145)."""
    from .cloth_release import pin_vertices
    pc, rest = at.split(":", 1)
    names = rest.split("..")
    if len(names) < 2:
        raise ValueError(f"a border is 'piece:a..b' or 'piece:a..b..c', not {at!r}")
    out = []
    for a, b in zip(names[:-1], names[1:]):
        try:
            seg = [int(v) for v in pin_vertices(M, f"{pc}:{a}..{b}")]
        except KeyError as e:
            raise ValueError(str(e).strip("'\"")) from None
        out += seg if not out else seg[1:]
    return np.asarray(out, int)


def _body_vf(body):
    if body is None:
        return None
    if isinstance(body, (tuple, list)):
        return np.asarray(body[0], float), np.asarray(body[1], int)
    return np.asarray(body.V, float), np.asarray(body.T if hasattr(body, "T") else body.F, int)


def body_normal_at(body, p: np.ndarray, mirrored: bool = True) -> np.ndarray:
    """The body's outward vertex normal nearest to p (area-weighted face normals). mirrored: averaged with the mirror
    image of the normal at p mirrored across x = 0, so mirrored handles get mirrored directions (the shirt's two "out"
    pulls differed, up 0.38 vs 0.32, and the right collar tip twisted 55-66 deg vs the left's 22)."""
    V, F = _body_vf(body)
    nn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], nn)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    tr = cKDTree(V)
    n = vn[tr.query(p)[1]]
    if mirrored:
        flip = np.array([-1.0, 1.0, 1.0])
        n = n + vn[tr.query(p * flip)[1]] * flip
    return n / (np.linalg.norm(n) + 1e-12)


def direction(d, p: np.ndarray, side_x: float | None = None, body=None) -> np.ndarray:
    """A handle's unit pull direction at p: a vector, a name ("side", "out", "up", "down") or a mix {name: w}."""
    if isinstance(d, str):
        d = {d: 1.0}
    if isinstance(d, dict):
        v = np.zeros(3)
        for k, w in d.items():
            if k == "side":
                sx = p[0] if side_x is None else side_x
                if abs(sx) < SIDE_MIN:
                    raise ValueError(f"'side' from a point {abs(sx) * 1000:.0f} mm off centre (x = 0): take the side "
                                     f"from a landmark well off CF (side_from: a hinge, a neck point), never a point "
                                     f"at CF, where the band's ends cross")
                v += w * np.array([np.sign(sx), 0.0, 0.0])
            elif k == "out":
                if body is None:
                    raise ValueError("'out' (the body normal) needs the body")
                v += w * body_normal_at(body, p)
            elif k in ("up", "down"):
                v += w * np.array([0.0, 0.0, 1.0 if k == "up" else -1.0])
            else:
                raise ValueError(f"no direction {k!r} (side, out, up, down, or a vector [x, y, z])")
    else:
        v = np.asarray(d, float).reshape(3)
    nv = np.linalg.norm(v)
    if nv < 1e-9:
        raise ValueError(f"direction {d!r} is zero")
    return v / nv


def _mask(held, n0):
    held = np.asarray(held)
    if held.dtype != bool:
        hm = np.zeros(n0, bool)
        hm[held.astype(int)] = True
        held = hm
    return held.copy()


def grip(M: dict, h: dict, held=None, patch_default: float | None = None) -> tuple[np.ndarray, int]:
    """(vertices, lead) a handle grips. A single point grabs the cloth within `patch` of it on its piece's pattern
    (default PATCH: a hand grabs an AREA; one vertex dragged pinched and twisted the collar's tip, C142); a border or a
    list grips those vertices (patch 0 unless given). The lead = the point itself, or the gripped vertex nearest the
    grip's middle on the pattern. A grip overlapping held cloth is REFUSED (the two fight: a corner pull sharing
    vertices with the held band end stretched 280 %, shirt spike). A point's patch TURNS
    with the cloth each step (handle "turn", default on for a point); a border / list moves as one (the hand holds its
    line: a turning border tilted the strip's end in-plane and stopped it 7 mm short)."""
    vs = vertices(M, h["at"])
    uv = np.asarray(M["uv"], float)
    pid = np.asarray(M["piece"])
    if patch_default is None:
        patch_default = PATCH if len(vs) == 1 else 0.0
    patch = float(h.get("patch", patch_default))
    if len(vs) == 1:
        lead = int(vs[0])
    else:
        c = uv[vs].mean(0)
        lead = int(vs[np.argmin(np.linalg.norm(uv[vs] - c, axis=1))])
    if patch > 0:
        near = np.zeros(len(uv), bool)
        for v in vs:
            near |= (pid == pid[v]) & (np.linalg.norm(uv - uv[v], axis=1) <= patch)
        vs = np.where(near)[0]
    if held is not None and held[vs].any():  # (a grip and a hold on the same cloth fight: 280 % in the shirt spike)
        raise ValueError(f"handle {h['at']!r} grips {int(held[vs].sum())} held vertices (patch {patch * 1000:.0f} mm): "
                         "a grip overlapping a hold tears the cloth between them; shrink its patch, grip elsewhere or "
                         "hold less")
    return np.unique(vs), lead


def _kabsch(P0: np.ndarray, Q: np.ndarray):
    """Proper rotation R and t with R P0 + t ~ Q (det +1: it can't mirror)."""
    a0, b0 = P0.mean(0), Q.mean(0)
    U, _, Vt = np.linalg.svd((P0 - a0).T @ (Q - b0))
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    return R, b0 - R @ a0


def _easy_dir(A, Y, fixed, leads, base, body, step, st, probe_iters):
    """'Let the cloth choose' (shirt spike w25): candidates = each handle's base direction tilted toward the body
    normal (+-0 / 35 / 70 deg) or up (+-35 / 70 deg), every handle the same tilt (a symmetric pull stays mirrored);
    each probed with a short solve, the least-stretch one taken for this step."""
    best = None
    for ax in ("n", "u"):
        for ang in (0, 35, -35, 70, -70):
            if (ax == "u" and ang == 0) or (ax == "n" and body is None and ang):
                continue
            cand, T, fx = [], Y.copy(), fixed.copy()
            for w, b in zip(leads, base):
                o = body_normal_at(body, Y[w]) if ax == "n" and body is not None else np.array([0.0, 0.0, 1.0])
                o = o - (o @ b) * b
                o /= np.linalg.norm(o) + 1e-12
                d = np.cos(np.radians(ang)) * b + np.sin(np.radians(ang)) * o
                cand.append(d)
                T[w] = Y[w] + step * d
                fx[w] = True
            s = st(A.solve(T, fx, probe_iters))
            if best is None or s < best[0]:
                best = (s, cand)
    return best[1]


def pull(M: dict, X: np.ndarray, held, handles: list[dict], body=None, step: float = STEP, tol: float = TOL,
         max_move: float = MAX_MOVE, iters: int = ITERS, relax_iters: int = RELAX_ITERS,
         settle_iters: int = SETTLE_ITERS, confirm: int = CONFIRM_ITERS, thread_stop: bool = False, turn_rounds: int = TURN_ROUNDS,
         probe_iters: int = PROBE_ITERS, mirror: bool = True, pieces=None, log=None):
    """Drag `handles` until the cloth would stretch (module docstring). Returns (X_new, info)."""
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    if not handles:
        raise ValueError("handles: at least one {\"at\": ..., \"dir\": ...}")
    A = FlatARAP(M, X)
    Y = A.weld(X)
    grips = [grip(M, h, held) for h in handles]
    groups = [np.unique(A.inv[vs]) for vs, _ in grips]  # welded vertices each handle grips
    leads = [int(A.inv[ld]) for _, ld in grips]
    li = [int(np.where(g == w)[0][0]) for g, w in zip(groups, leads)]
    turning = [bool(h.get("turn", len(vertices(M, h["at"])) == 1)) and len(g) > 1 for h, g in zip(handles, groups)]
    gripped = np.zeros(len(X), bool)
    for vs, _ in grips:
        gripped[vs] = True
    fixed = A.welded_mask(held)
    if pieces is None:  # the pieces the pull can change: any with a free vertex
        pieces = sorted(set(np.asarray(M["piece"])[~held & ~gripped].tolist()))
    names = [list(M["names"])[p] if isinstance(p, (int, np.integer)) else p for p in pieces]
    tf = thread_faces(M, pieces)
    st = lambda W: thread_p99(M, A.unweld(W), faces=tf)  # (threads, shear: C169)
    fx_all = fixed.copy()
    for g in groups:
        fx_all[g] = True
    Y = A.solve(Y, fx_all, relax_iters)
    s0, sh0 = st(Y)
    lock = _shear_lock(sh0)
    t_lim = np.maximum(thread_strain(M, A.unweld(Y), faces=tf)[0].max(1), STYLE_THREAD_CAP) + BORDER_LOCAL_TOL
    torn = lambda W: thread_stop and BORDER_LOCAL_STOP and bool((thread_strain(M, A.unweld(W), faces=tf)[0].max(1) > t_lim).any())
    easy, base = [], []
    for h, g, w in zip(handles, groups, leads):
        d = h.get("dir", "side")
        easy.append(d == "easy" or (isinstance(d, dict) and "easy" in d))
        if easy[-1]:
            d = "side" if d == "easy" else d["easy"]
        sx = float(X[vertex(M, h["side_from"])][0]) if h.get("side_from") is not None else \
            float(Y[g, 0].mean()) if len(g) > 1 else None
        base.append(direction(d, Y[w], sx, body))
    if mirror:  # (mirrored handles pulled the same way: the fit's own asymmetry tilted the two "out"s apart)
        flip = np.array([-1.0, 1.0, 1.0])
        L = np.array([Y[w] for w in leads])
        b0 = [d.copy() for d in base]
        for i in range(len(leads)):
            dj = np.linalg.norm(L - L[i] * flip, axis=1)
            j = int(np.argmin(dj))
            if j != i and dj[j] < MIRROR_REACH:
                v = b0[i] + b0[j] * flip
                base[i] = v / (np.linalg.norm(v) + 1e-12)
    if any(easy) and not all(easy):
        raise ValueError("'easy' is for every handle of a pull or none (they move together)")
    P0 = [Y[g].copy() for g in groups]  # each grip's shape at the start: fitted back on (turned) every step
    tgt = [Y[w].copy() for w in leads]
    dirs = list(base)
    good, steps, stopped, least, path = Y, 0, "max_move", s0, 0.0
    while path + step <= max_move + 1e-9:
        if all(easy) and easy:
            dirs = _easy_dir(A, good, fixed, leads, base, body, step, lambda W: _stop_key(st(W), lock), probe_iters)
        tg = [t + step * d for t, d in zip(tgt, dirs)]
        T, fx = good.copy(), fixed.copy()
        for g, p0, i, w, t, tu in zip(groups, P0, li, leads, tg, turning):
            if tu:
                T[w] = t
                fx[w] = True
            else:  # (a border / list grip moves as one: the hand holds its line)
                T[g] = good[g] + (t - good[w])
                fx[g] = True
        Yt = A.solve(T, fx, iters)
        # TURNING GRIP (C142): the lead dragged alone, then each grip's start shape fitted rigidly onto that solution
        # (it turns with the cloth: a rigid translated patch folded the cloth over at its edge), the lead on its
        # target, the grip pinned, solved again
        fx2 = fx.copy()
        for _ in range(turn_rounds if any(turning) else 0):
            T2 = Yt.copy()
            for g, p0, i, t, tu in zip(groups, P0, li, tg, turning):
                if not tu:
                    continue
                R, tr = _kabsch(p0, Yt[g])
                Pn = p0 @ R.T + tr
                T2[g] = Pn + (t - Pn[i])
                fx2[g] = True
            Yt = A.solve(T2, fx2, iters)
        s, sh = st(Yt)
        if log:
            log(f"pull step {steps + 1}: {path * 1000 + step * 1000:.0f} mm, threads p99 {s * 100:.2f} %, "
                f"shear p99 {_shmax(sh)} deg")
        tr_ = torn(Yt)
        confirmed = (s > least + tol or _jammed(sh, lock) or tr_) and confirm
        if confirmed:  # (an unconverged solve on a big move reads stretch the cloth doesn't need: the converged read
            # decides; the few-rounds state is kept, so the cloth still moves as little as it must)
            Yc = A.solve(Yt, fx2, confirm, eps=CONVERGED)
            s, sh = st(Yc)
            tr_ = tr_ and torn(Yc)
        if s > least + tol or _jammed(sh, lock) or tr_:
            stopped = "stretch" if s > least + tol else "shear" if _jammed(sh, lock) else "thread"
            break
        good, steps, tgt, path = Yt, steps + 1, tg, path + step
        if not confirmed:  # (the least is read the same way every step: a converged read is lower)
            least = min(least, s)
    fx_end = fixed.copy()
    for g in groups:
        fx_end[g] = True
    Y = A.solve(good, fx_end, settle_iters)
    Xn = A.unweld(Y)
    Xn[held] = X[held]  # (held vertices exactly where they were: welding averages a held vertex with its free twin)
    info = {"moved_mm": {str(h["at"]): round(float(np.linalg.norm(Y[w] - p0[i])) * 1000, 1)
                         for h, w, p0, i in zip(handles, leads, P0, li)},
            "path_mm": round(path * 1000, 1),
            "stretch_p99_start": round(s0 * 100, 2), "stretch_p99_least": round(least * 100, 2),
            "stretch_p99_end": round(thread_p99(M, Xn, faces=tf)[0] * 100, 2), "steps": steps,
            "shear_p99_deg": [_shmax(sh0), _shmax(thread_p99(M, Xn, faces=tf)[1])], "shear_lock_deg": _shmax(lock),
            "step_mm": step * 1000, "tol_pct": tol * 100, "stopped": stopped,
            "gripped": {str(h["at"]): int(len(vs)) for h, (vs, _) in zip(handles, grips)},
            "dirs": {str(h["at"]): np.round(d, 3).tolist() for h, d in zip(handles, dirs)}, "pieces": names}
    return Xn, info


def smooth(M: dict, X: np.ndarray, held, pieces, lam: float = 0.5, iters: int = 6, rounds: int = 20,
           tol: float = TOL, stretch_pieces=None, near=None, radius: float = 0.04):
    """SMOOTH (C143; Joe: "a 'smooth' operation ... in conjunction with the 'pull' operation ... those are the two
    main operations to styling the clothing one is wearing"): a hand flattening ripples. In the brushed `pieces`
    (minus `held`) alternate (a) fair: each vertex `lam` of the way toward its one-ring centroid ALONG ITS NORMAL only,
    (b) restore: the flat-pattern solve (`iters` rounds) with everything outside the brush held. Stops when the stretch
    (on `stretch_pieces`; default the pull's read, every piece with free cloth) would exceed the least so far + `tol`
    (the pull's rule) or the roughness (p95 of the fair's normal distance, the
    crumple read) stops dropping. Shirt spike sm1: collar + stand roughness p95 0.67 -> 0.32 mm, stretch +0.3 pt.
    `near` (points "piece:point" / vertices) + `radius` (m, pattern): a LOCAL brush, the pieces' cloth within radius of
    each point, its stop read there alone (shirt spike x5: the band ends' turn buckled the free collar tips, crumple
    p95 0.23 mm; a whole-collar smooth didn't see them, a 40 mm brush round each point took them to 0.06-0.08 = closed).
    Returns (X_new, info: rounds, rough p95 start / end (mm), stretch p99 start / end (%))."""
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    A = FlatARAP(M, X)
    Y = A.weld(X)
    on = np.isin(np.asarray(M["piece"]), _piece_ids(M, pieces))
    if near is not None:
        uv_ = np.asarray(M["uv"], float)
        pid_ = np.asarray(M["piece"])
        loc = np.zeros(len(X), bool)
        for q in (near if isinstance(near, (list, tuple)) else [near]):
            o = vertex(M, q)
            loc |= (pid_ == pid_[o]) & (np.linalg.norm(uv_ - uv_[o], axis=1) <= radius)
        on &= loc
    brush = A.welded_mask(on)
    keep = ~brush | A.welded_mask(held)
    WF = A.WF
    Ew = np.unique(np.sort(np.r_[WF[:, [0, 1]], WF[:, [1, 2]], WF[:, [2, 0]]], 1), axis=0)
    cnt = np.zeros(A.n)
    np.add.at(cnt, Ew[:, 0], 1)
    np.add.at(cnt, Ew[:, 1], 1)

    def normal_offset(Yc):
        fn = np.cross(Yc[WF[:, 1]] - Yc[WF[:, 0]], Yc[WF[:, 2]] - Yc[WF[:, 0]])
        vn = np.zeros_like(Yc)
        for k in range(3):
            np.add.at(vn, WF[:, k], fn)
        vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
        S = np.zeros_like(Yc)
        np.add.at(S, Ew[:, 0], Yc[Ew[:, 1]])
        np.add.at(S, Ew[:, 1], Yc[Ew[:, 0]])
        o = ((S / np.maximum(cnt, 1)[:, None] - Yc) * vn).sum(1)
        return o[:, None] * vn, np.abs(o)

    sp = stretch_pieces  # (default: the pull's read, every piece with free cloth: one rule for both operations)
    if sp is None:
        sp = sorted(set(np.asarray(M["piece"])[~held].tolist()))
    tf = thread_faces(M, sp)
    st = lambda W: thread_p99(M, A.unweld(W), faces=tf)  # (threads, shear: C169)
    free = ~keep
    s0, sh0 = st(Y)
    least, lock = s0, _shear_lock(sh0)
    r0 = rr = float(np.percentile(normal_offset(Y)[1][free], 95))
    k = 0
    for k in range(1, rounds + 1):
        mv, _ = normal_offset(Y)
        T = Y.copy()
        T[free] += lam * mv[free]
        Yt = A.solve(T, keep, iters)
        rt = float(np.percentile(normal_offset(Yt)[1][free], 95))
        s, sh = st(Yt)
        if s > least + tol or _jammed(sh, lock) or rt > rr * 0.995:
            k -= 1
            break
        Y, rr, least = Yt, rt, min(least, s)
    Xn = A.unweld(Y)
    Xn[held] = X[held]
    return Xn, {"rounds": k, "rough_p95_mm": [round(r0 * 1000, 3), round(rr * 1000, 3)],
                "stretch_p99": [round(s0 * 100, 2), round(st(Y)[0] * 100, 2)],
                "shear_p99_deg": [_shmax(sh0), _shmax(st(Y)[1])], "pieces": list(pieces),
                **({"near": list(near) if isinstance(near, (list, tuple)) else [near], "radius": radius} if near is not None else {})}


def _kink3d(P: np.ndarray, win: float, on=None) -> float:
    """The largest turn (deg) of a polyline's direction over `win` (m of arc); `on` (bool per vertex): only turns
    centred on those vertices."""
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    mx = 0.0
    for i in range(len(P)):
        if on is not None and not on[i]:
            continue
        a = np.searchsorted(s, s[i] - win / 2)
        b = np.searchsorted(s, s[i] + win / 2) - 1
        if a >= i or b <= i:
            continue
        d1, d2 = P[i] - P[a], P[b] - P[i]
        mx = max(mx, float(np.degrees(np.arccos(np.clip(d1 @ d2 / (np.linalg.norm(d1) * np.linalg.norm(d2) + 1e-12),
                                                        -1, 1)))))
    return mx


def smooth_border(M: dict, X: np.ndarray, held, border: str, spline: int = 10, lam: float = 0.4, ends: float = 0.025,
                  win: float = 0.03, rounds: int = 30, iters: int = 8, tol: float = 0.015, stretch_pieces=None,
                  thread_stop: bool = False):
    """SMOOTH A BORDER INTO ONE SWOOP (C145; Joe: "if this profile read as one continuous swoop instead of three
    different angles, it would be a lot closer to done"): a long-scale shape, so the border is drawn toward ONE fitted
    curve, not its neighbours (local averaging over 10-50 mm stalled after 2 rounds and roughened the collar). Each
    round: a least-squares cubic spline with `spline` interior knots per coordinate over arc length through the border
    walk (`border_chain`), every border vertex further than `ends` (pattern) from the walk's two ends moved `lam` of the
    way onto it and pinned, the rest re-solved (`iters`); stops when the stretch would exceed the least + `tol`, or the
    border's 3D kink over `win` stops dropping. Spike sp10 (spline 10, lam 0.4, win 30 mm, tol 1.5 %): the collar's
    side-view kinks 18 / 34 -> 12 / 12 deg. Returns (X_new, info: rounds, kink deg start / end, stretch p99 start /
    end (%)). `spline` 0 (C185): drawn toward the straight CHORD between the walk's ends in the front view (x, z; y as it
    lies), stopping on stretch / shear or on the chord, not on the kink: an open jacket's edge runs straight from the break."""
    from scipy.interpolate import LSQUnivariateSpline
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    ch = border_chain(M, border)
    uv = np.asarray(M["uv"], float)
    dist = np.minimum(np.linalg.norm(uv[ch] - uv[ch[0]], axis=1), np.linalg.norm(uv[ch] - uv[ch[-1]], axis=1))
    mov = (dist > ends) & ~held[ch]
    A = FlatARAP(M, X)
    Y = A.weld(X)
    chw = A.inv[ch]
    fixed = A.welded_mask(held)
    sp = stretch_pieces
    if sp is None:
        sp = sorted(set(np.asarray(M["piece"])[~held].tolist()))
    tf = thread_faces(M, sp)
    st = lambda W: thread_p99(M, A.unweld(W), faces=tf)  # (threads, shear: C169)
    s0, sh0 = st(Y)
    least, lock = s0, _shear_lock(sh0)
    # (fit round 33) the kink is ALSO read where the smooth can move the border: a fixed corner at an end (the jacket's
    # break, where the edge meets the held lapel: 15 deg at 3 mm of a 396 mm edge) was the max every round, so the stop
    # fired at 0-2 rounds whatever the middle did; it goes on while either read drops
    k0 = kk = _kink3d(Y[chw], win)
    m0 = mm_ = _kink3d(Y[chw], win, mov)
    if thread_stop:  # (THREADS FIRST for a pinned move, C198: each face against its own start, not the p99)
        t_lim = np.maximum(thread_strain(M, X, faces=tf)[0].max(1), STYLE_THREAD_CAP) + BORDER_LOCAL_TOL
    nk = int(min(spline, max(1, len(ch) // 3 - 1)))  # (a coarse border: fewer knots than its vertices allow fail fpchec)
    r = 0
    for r in range(1, rounds + 1):
        p = Y[chw]
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
        kn = np.linspace(s[0], s[-1], nk + 2)[1:-1]
        if spline == 0:  # (C185: the border drawn toward its CHORD in the FRONT view, x and z, its depth y left as it
            # lies: a 3D chord cut into the shirt and the floor pushed it back out round the body, L 450 stuck at 56 vs 63)
            fit = p[0] + (s / max(s[-1], 1e-9))[:, None] * (p[-1] - p[0])
            fit[:, 1] = p[:, 1]
        else:
            fit = np.column_stack([LSQUnivariateSpline(s, p[:, c], kn, k=3)(s) for c in range(3)])
        T, fx = Y.copy(), fixed.copy()
        T[chw[mov]] = p[mov] + lam * (fit[mov] - p[mov])
        fx[chw[mov]] = True
        Yt = A.solve(T, fx, iters)
        kt, mt, (sn, sh) = _kink3d(Yt[chw], win), _kink3d(Yt[chw], win, mov), st(Yt)
        # (chord mode: a straight target, so the kink read isn't the stop: the stretch / shear stop, or on the chord)
        bend = spline != 0 and (kt > kk - 0.2 and mt > mm_ - 0.2)
        torn = thread_stop and BORDER_LOCAL_STOP and bool((thread_strain(M, A.unweld(Yt), faces=tf)[0].max(1) > t_lim).any())
        if sn > least + tol or _jammed(sh, lock) or bend or torn or \
                (spline == 0 and np.abs(fit[mov] - p[mov]).max(initial=0) < 5e-4):
            r -= 1
            break
        Y, kk, mm_, least = Yt, min(kk, kt), min(mm_, mt), min(least, sn)
    Xn = A.unweld(Y)
    Xn[held] = X[held]
    return Xn, {"rounds": r, "kink_deg": [round(k0, 1), round(_kink3d(Y[chw], win), 1)],
                "kink_moving_deg": [round(m0, 1), round(_kink3d(Y[chw], win, mov), 1)],
                "stretch_p99": [round(s0 * 100, 2), round(st(Y)[0] * 100, 2)],
                "shear_p99_deg": [_shmax(sh0), _shmax(st(Y)[1])], "border": border}


def style(M: dict, X: np.ndarray, held, ops: list[dict], body=None, log=None, floor=None):
    """Styling as a SEQUENCE of hand moves (C142-C144): ops [{"pull": {"handles": [...], step / tol / max_move ...}}
    | {"turn": {"turns": [...], steps ...}} | {"smooth": {"pieces": [...], lam / rounds / tol ...} or {"border":
    "piece:a..b..c", spline / lam / ...} (smooth_border), "release"?: pieces freed from region holds} | {"relax":
    {iters}} (the free cloth against its pattern) | {"hold": {...}} (hold_region: kept where it is NOW for every later
    op; relax first: holding the unrelaxed closed collar locked in its strain, p99 7.5 vs 6.1 %; "feather_to": the
    band beyond the hold drawn back after every later pull)], each from where
    the last left the cloth; what a pull or turn gripped is HELD where it ended for every later op (Joe: move these
    apart a little, then push the points a little more); a pull that grips them again picks them up. Returns
    (X_new, [info per op])."""
    X = np.asarray(X, float)
    base = _mask(held, len(X))
    M = dict(M, _X=X.copy())  # ("piece:@closure" names read which pairs are done up on the fit styled)
    if M.get("_bend_rest") is None:  # (STYLE_BEND: every op's stiffness rests on the shape the styling started from)
        M["_bend_rest"] = X.copy()
    if floor:  # (C170: layer_floor's floors, read by every op's solve)
        M["_floor"] = floor
    placed = np.zeros(len(X), bool)  # what earlier ops gripped: held where they left it
    feathers = []  # (vertices, share, positions at the hold) of each feathered hold
    regions = np.zeros(len(X), bool)  # what hold ops hold (a smooth may "release" pieces of it)
    infos = []
    for op in ops:
        (kind, a), = op.items()
        a = dict(a)
        let_go = bool(a.pop("let_go", False)) if kind in ("pull", "turn", "slide") else False  # (C199: the hand lets go:
        # what this op gripped is NOT held for later ops; supports, not holds (C190: styling grips held for every later
        # op stand for no support). Its "with" / let_go_above rules then have nothing left to keep.)
        placed0 = placed.copy()
        if kind == "pull":
            hs = a.pop("handles")
            mine = np.zeros(len(X), bool)
            for h in hs:  # (picking a point up again releases it)
                mine[grip(M, h, base)[0]] = True
            X, inf = pull(M, X, base | (placed & ~mine), hs, body=body, log=log, **a)
            placed |= mine
        elif kind == "turn":
            ts = a.pop("turns")
            mine = np.zeros(len(X), bool)
            for t in ts:  # (the whole gripped area stays where the turn left it, not just the named vertices)
                mine[grip(M, t, None, TURN_PATCH)[0]] = True
            X, inf = turn(M, X, base | (placed & ~mine), ts, body=body, log=log, **a)
            placed |= mine
        elif kind == "smooth":
            rel = np.zeros(len(X), bool)  # ("release": pieces freed from earlier REGION holds for this op; grips stay)
            if a.get("release"):
                rel = regions & np.isin(np.asarray(M["piece"]), _piece_ids(M, a.pop("release")))
            hold_now = base | (placed & ~rel)
            if "border" in a:
                X, inf = smooth_border(M, X, hold_now, a.pop("border"), **a)
            else:
                X, inf = smooth(M, X, hold_now, a.pop("pieces"), **a)
        elif kind == "plumb":  # (C181: seams laid on the vertical; what it grips stays where it put it)
            mine = np.zeros(len(X), bool)
            for b in a["borders"]:
                mine[border_chain(M, b)] = True
            X, inf = plumb(M, X, base | (placed & ~mine), a.pop("borders"), log=log, **a)
            placed |= mine
        elif kind == "slide":  # (fit round 37: lapped cloth slid round the body; what it grips stays where it put it)
            ss = a.pop("slides")
            mine = np.zeros(len(X), bool)
            for sl in ss:
                ch = border_chain(M, sl["at"])
                uv_, pid_ = np.asarray(M["uv"], float), np.asarray(M["piece"])
                on_ = np.where((pid_ == pid_[ch[0]]) & ~base)[0]
                mine[on_[cKDTree(uv_[ch]).query(uv_[on_])[0] <= float(sl.get("patch", 0.04))]] = True
            X, inf = slide(M, X, base | (placed & ~mine), ss, body=body, log=log, **a)
            for sl in ss:  # ("let_go_above": the grip above that point is let go after the slide, C185)
                if sl.get("let_go_above"):
                    v_ = vertex(M, sl["let_go_above"])
                    mine &= ~((pid_ == pid_[v_]) & (X[:, 2] > X[v_, 2]))
            placed |= mine
            for sl in ss:  # (a slide's "with" pieces above the edge's top stay as they lie for later ops)
                wp = [q for q in sl.get("with") or [] if q in M["names"]]
                if wp:
                    top = float(X[border_chain(M, sl["at"])[0], 2])
                    placed |= np.isin(np.asarray(M["piece"]), _piece_ids(M, wp)) & (X[:, 2] >= top) & ~base
        elif kind == "relax":
            keep = a.pop("keep", None)  # (C199: hold_region kwargs held for THIS relax only: a hang of the lower fronts
            # alone keeps the rest as it lies, without holding it for later ops)
            kept = hold_region(M, X, **keep) if keep else np.zeros(len(X), bool)
            hung_ = STYLE_HANG if a.get("hang") is None else bool(a.get("hang"))
            if hung_ and not floor and body is not None:  # (HANG: what hangs rests on its supports: with no layer
                # floor the body is its floor for this op; hung through nothing, wf_simon's open collar fell through
                # the neck: threads p99 326 %, shear 82 deg)
                M_ = dict(M, _floor=layer_floor(M, X, body=body))
                X, inf = relax(M_, X, base | placed | kept, **a)
            else:
                X, inf = relax(M, X, base | placed | kept, **a)
        elif kind == "push":
            X, inf = push(M, X, base | placed, a.pop("pieces"), body, **a)
        elif kind == "hold":
            mine = hold_region(M, X, **a)
            placed |= mine
            regions |= mine
            inf = {"held": int(mine.sum())}
            if a.get("feather_to") is not None:
                # ("feather_pieces": only these are feathered back, e.g. the band but not the collar's fall: holding the
                # fall at the sides too made an S in the front view (in, out, back in to the tip); c1: one arc)
                fv, fw = feather_weights(M, X, a.get("feather_pieces") or a["pieces"], a["within_deg"], a["feather_to"],
                                         a.get("of", "back"), a.get("center") or a["pieces"][0])
                fv, fw = fv[~(base | placed)[fv]], fw[~(base | placed)[fv]]
                feathers.append((fv, fw, X.copy()))
                inf["feathered"] = int(len(fv))
        else:
            raise ValueError(f"no styling op {kind!r} (pull, turn, slide, smooth, relax, hold, push, plumb)")
        if let_go:  # (what it picked up is let go too)
            placed = placed0 & ~mine
        if kind in FEATHER_AFTER and feathers:  # (the feathered band drawn back after each move)
            for fv, fw, ref in feathers:
                keep = ~placed[fv]
                X = feather(M, X, base | placed, fv[keep], fw[keep], ref)
        if floor:  # (C170: a smooth / feather moves cloth outside the solve: the floor once more after every op;
            # without it the brushed pocket flaps sank 13 of 25 vertices into their fronts, fit round 30)
            A_ = FlatARAP(M, X)
            hm = base | placed
            Xf = A_.unweld(A_._floor(A_.weld(X), A_.welded_mask(hm)))
            Xf[hm] = X[hm]
            if isinstance(inf, dict):
                inf["floor_pushed"] = A_.floor_pushed
            X = Xf
        infos.append({kind: inf})
    return X, infos


def push(M: dict, X: np.ndarray, held, pieces, body, gap: float = 0.002, rounds: int = 4, iters: int = 8):
    """The body as a floor for `pieces` only (shirt spike w5d: the fronts, once the throat opened, sank into the chest;
    pushed off the body after the moves they lie open with soft folds; on the band a push-out dented it, so it is never
    applied to every piece): `rounds` times, every free vertex of `pieces` less than `gap` outside the body (signed along
    the nearest body vertex's normal) moved out to `gap` and pinned, the rest re-solved. Returns (X_new, info: inside
    before / after)."""
    from scipy.spatial import cKDTree
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    BV, BF = _body_vf(body)
    fn = np.cross(BV[BF[:, 1]] - BV[BF[:, 0]], BV[BF[:, 2]] - BV[BF[:, 0]])
    vn = np.zeros_like(BV)
    for k in range(3):
        np.add.at(vn, BF[:, k], fn)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    bt = cKDTree(BV)
    mine = np.isin(np.asarray(M["piece"]), _piece_ids(M, pieces)) & ~held
    A = FlatARAP(M, X)

    def under(Xc):
        _, j = bt.query(Xc)
        sd = ((Xc - BV[j]) * vn[j]).sum(1)
        return mine & (sd < gap), sd, j

    n0 = int(under(X)[0].sum())
    for _ in range(rounds):
        bad, sd, j = under(X)
        if not bad.any():
            break
        T = X.copy()
        T[bad] += (gap - sd[bad])[:, None] * vn[j[bad]]
        Y = A.solve(A.weld(T), A.welded_mask(held | bad), iters)
        X = A.unweld(Y)
    return X, {"inside": [n0, int(under(X)[0].sum())], "pieces": list(pieces)}


def relax(M: dict, X: np.ndarray, held, iters: int = HOLD_ITERS, hang: bool | None = None, hang_iters: int | None = None):
    """The free (not held) cloth relaxed against its flat pattern (`iters` rounds), nothing gripped. hang (None:
    STYLE_HANG): then the free cloth HANGS under its weight for `hang_iters` (HANG_ITERS) more rounds (FlatARAP.solve
    hang: supports, not holds). Returns (X_new, info: stretch p99 start / end (%), on the pieces with free cloth)."""
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    A = FlatARAP(M, X)
    sp = sorted(set(np.asarray(M["piece"])[~held].tolist()))
    tf = thread_faces(M, sp)
    (s0, sh0) = thread_p99(M, X, faces=tf)
    Y = A.solve(A.weld(X), A.welded_mask(held), iters)
    if STYLE_HANG if hang is None else hang:
        Y = A.solve(Y, A.welded_mask(held), int(hang_iters or HANG_ITERS), hang=True)
    Xn = A.unweld(Y)
    Xn[held] = X[held]
    s1, sh1 = thread_p99(M, Xn, faces=tf)
    return Xn, {"stretch_p99": [round(s0 * 100, 2), round(s1 * 100, 2)], "shear_p99_deg": [_shmax(sh0), _shmax(sh1)]}


def _ring_angle(M: dict, X: np.ndarray, pieces, of: str = "back", center=None) -> np.ndarray:
    """|angle| (deg) of every vertex round a vertical axis through `center`'s x-y centroid (a piece; default the first
    of `pieces`), 0 at CB ("of": "back", +y: the creature faces -y) or CF ("front")."""
    pid = np.asarray(M["piece"])
    c = X[pid == _piece_ids(M, [center or pieces[0]])[0]][:, :2].mean(0)
    ref = {"back": 1.0, "front": -1.0}[of]
    return np.abs(np.degrees(np.arctan2(X[:, 0] - c[0], ref * (X[:, 1] - c[1]))))


def feather_weights(M: dict, X: np.ndarray, pieces, from_deg: float, to_deg: float, of: str = "back",
                    center=None) -> tuple[np.ndarray, np.ndarray]:
    """(vertices, share): `pieces`' vertices between `from_deg` and `to_deg` round the ring, each with a share fading
    1 -> 0 on a cosine ramp across that band (a hand pressing firm at the back, lighter toward the front)."""
    ang = _ring_angle(M, X, pieces, of, center)
    on = np.isin(np.asarray(M["piece"]), _piece_ids(M, pieces))
    v = np.where(on & (ang >= from_deg) & (ang < to_deg))[0]
    t = 1 - (ang[v] - from_deg) / (to_deg - from_deg)
    return v, 0.5 - 0.5 * np.cos(np.pi * t)


def feather(M: dict, X: np.ndarray, held, verts: np.ndarray, share: np.ndarray, ref: np.ndarray, rounds: int = 3,
            iters: int = 8) -> np.ndarray:
    """FEATHERED HOLD (C144, the spike's f2): `rounds` times, each of `verts` drawn its `share` of the way back to `ref`
    (its held position), pinned, the rest re-solved against the pattern. A hard hold border kinked the collar's edge
    (29 deg at the border); feathered from 70 to 130 deg: 18 deg, the sides still hugging."""
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    A = FlatARAP(M, X)
    Y = A.weld(X)
    w = A.welded_mask(held)
    vw = A.inv[verts]
    for _ in range(rounds):
        T = Y.copy()
        cur = A.unweld(Y)[verts]
        tgt = cur + share[:, None] * (ref[verts] - cur)
        acc, cnt = np.zeros((A.n, 3)), np.zeros(A.n)
        np.add.at(acc, vw, tgt)
        np.add.at(cnt, vw, 1)
        m = cnt > 0
        T[m] = acc[m] / cnt[m, None]
        fx = w | m
        Y = A.solve(T, fx, iters)
    Xn = A.unweld(Y)
    Xn[held] = X[held]
    return Xn


def hold_region(M: dict, X: np.ndarray, pieces=None, within_deg: float | None = None, of: str = "back",
                center=None, at=None, feather_to: float | None = None, feather_pieces=None, above=None) -> np.ndarray:
    """A region the hand / body keeps still (C144; Joe: the collar "should mostly hug the neck on the back and sides;
    the flare is all toward the front"): the vertices of `pieces` within `within_deg` of CB ("of": "back", +y: the
    creature faces -y) or CF ("front") round a vertical axis through `center` (a piece name: its x-y centroid; default
    the first piece's), plus whatever `at` names (vertex / "piece:point" / "piece:a..b" / a list). Angles read on X
    as it is now. Shirt spike h110 / q40: band + collar within 110 deg of CB held, the side hug 70 mm vs 68 closed
    (unheld: the opened front's slack spread round the ring, the fall 8 / 14 mm further off the neck at CB / side).
    `feather_to` (deg; used by style()): the band from within_deg to feather_to is not held but FEATHERED back after
    each pull (`feather`; FEATHER_AFTER): a hard border kinked the collar's edge 29 deg (q40); held to 70, feathered to 130:
    18 deg (f2). `above` ("piece:point" or a list): that piece's vertices at or above the point's height, as they lie
    (C174: a worn-open front above its break held as the fit set it: the roll line is the fit's, C171)."""
    X = np.asarray(X, float)
    pid = np.asarray(M["piece"])
    out = np.zeros(len(X), bool)
    for pt in ([above] if isinstance(above, str) else above or []):
        v = vertex(M, pt)
        out |= (pid == pid[v]) & (X[:, 2] >= X[v, 2])
    if pieces:
        on = np.isin(pid, _piece_ids(M, pieces))
        if within_deg is None:
            out |= on
        else:
            out |= on & (_ring_angle(M, X, pieces, of, center) < within_deg)
    if at is not None:
        if isinstance(at, (list, tuple)):  # (C186: a named border of a piece the garment hasn't is skipped, as a slide's "with")
            at = [q for q in at if not isinstance(q, str) or ":" not in q or q.split(":")[0] in M["names"]]
        if not isinstance(at, (list, tuple)) or len(at):
            out[vertices(M, at)] = True
    return out


def tip_read(M: dict, X: np.ndarray, point, near: float = 0.015, mid: float = 0.04) -> dict:
    """A point's tip (shirt spike tip.py): within `near` (pattern) of the point on its piece, crumple p95 (mm) and edge
    stretch max (%), and the twist (deg) between the cloth's mean normal there and at `mid` from the point (the
    leaf's middle). A point dragged by one vertex: 15-18 % / 60-80 deg; the closed collar 2-3 % / 15-28 deg."""
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    o = vertex(M, point)
    nrm = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    vn = np.zeros_like(X)
    for j in range(3):
        np.add.at(vn, F[:, j], nrm)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    E = E[pid[E[:, 0]] == pid[E[:, 1]]]
    S, c = np.zeros_like(X), np.zeros(len(X))
    np.add.at(S, E[:, 0], X[E[:, 1]])
    np.add.at(S, E[:, 1], X[E[:, 0]])
    np.add.at(c, E[:, 0], 1)
    np.add.at(c, E[:, 1], 1)
    lap = np.abs(((S / np.maximum(c, 1)[:, None] - X) * vn).sum(1)) * 1000
    d = np.linalg.norm(uv - uv[o], axis=1)
    on = pid == pid[o]
    nr = on & (d < near) & (c >= 3)
    en = nr[E[:, 0]] & nr[E[:, 1]]
    l0 = np.maximum(np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1), 1e-9)
    stv = np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / l0 - 1) * 100
    md = on & (np.abs(d - mid) < 0.005)
    a, b = vn[nr].mean(0), vn[md].mean(0)
    tw = np.degrees(np.arccos(np.clip(abs(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12), -1, 1)))
    # THREADS AND SHEAR APART (C166 / C168): on the woven fit an edge on the bias lengthens when the cloth shears; the
    # threads (pattern x / y: the grain of a piece cut on it) are what stretch
    Fn = F[nr[F].all(1)]
    Dm = np.stack([uv[Fn[:, 1]] - uv[Fn[:, 0]], uv[Fn[:, 2]] - uv[Fn[:, 0]]], -1)
    okf = np.abs(np.linalg.det(Dm)) > 1e-14
    Fg = np.stack([X[Fn[okf, 1]] - X[Fn[okf, 0]], X[Fn[okf, 2]] - X[Fn[okf, 0]]], -1) @ np.linalg.inv(Dm[okf])
    ln = np.linalg.norm(Fg, axis=1)
    sh = np.degrees(np.arcsin(np.clip(np.abs((Fg[:, :, 0] * Fg[:, :, 1]).sum(1)) / np.maximum(ln[:, 0] * ln[:, 1], 1e-12), 0, 1)))
    return {"crumple_p95_mm": round(float(np.percentile(lap[nr], 95)), 3),
            "stretch_max_pct": round(float(stv[en].max()), 1), "twist_deg": round(float(tw), 1),
            "thread_max_pct": round(float(np.abs(ln - 1).max() * 100), 1) if len(ln) else 0.0,
            "shear_max_deg": round(float(sh.max()), 1) if len(sh) else 0.0}


def folded(M: dict, X: np.ndarray, point, radius: float = 0.025, deg: float = 120.0) -> int:
    """Folded-over faces near a point (shirt spike flips.py): faces of the point's piece within `radius` (pattern) whose
    dihedral with an edge neighbour exceeds `deg`, fold rows left out. The closed collar: 0; a rigid patch: 18 / 28."""
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    o = vertex(M, point)
    fold = np.zeros(len(X), bool)
    for fd in M.get("folds") or []:
        for r in fd["rows"]:
            fold[np.asarray(r, int)] = True
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    fn /= np.linalg.norm(fn, axis=1)[:, None] + 1e-15
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    fi = np.tile(np.arange(len(F)), 3)
    key = np.sort(E, 1)
    order = np.lexsort((key[:, 1], key[:, 0]))
    ks, fs = key[order], fi[order]
    same = (ks[1:] == ks[:-1]).all(1)
    a, b = fs[:-1][same], fs[1:][same]
    e = ks[:-1][same]
    ok = ~(fold[e[:, 0]] & fold[e[:, 1]])
    a, b = a[ok], b[ok]
    ang = np.degrees(np.arccos(np.clip((fn[a] * fn[b]).sum(1), -1, 1)))
    worst = np.zeros(len(F))
    np.maximum.at(worst, a, ang)
    np.maximum.at(worst, b, ang)
    m = (pid[F[:, 0]] == pid[o]) & (np.linalg.norm(uv[F].mean(1) - uv[o], axis=1) < radius)
    return int((m & (worst > deg)).sum())


def crumple(M: dict, X: np.ndarray, piece, ring_min: int = 5) -> np.ndarray:
    """Crumple read (mm): each vertex's distance from its one-ring centroid along its normal, on `piece`, fold rows
    and border vertices (fewer than `ring_min` neighbours) left out. Smooth cloth at 2 mm reads ~0.0x; the shirt
    spike's closed collar 0.14 p95, y3 0.28, pinned variants 0.34-0.72."""
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    k = _piece_ids(M, [piece])[0]
    fold = np.zeros(len(X), bool)
    for fd in M.get("folds") or []:
        for r in fd["rows"]:
            fold[np.asarray(r, int)] = True
    nrm = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    vn = np.zeros_like(X)
    for j in range(3):
        np.add.at(vn, F[:, j], nrm)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    E = E[pid[E[:, 0]] == pid[E[:, 1]]]
    S, c = np.zeros_like(X), np.zeros(len(X))
    np.add.at(S, E[:, 0], X[E[:, 1]])
    np.add.at(S, E[:, 1], X[E[:, 0]])
    np.add.at(c, E[:, 0], 1)
    np.add.at(c, E[:, 1], 1)
    lap = np.abs(((S / np.maximum(c, 1)[:, None] - X) * vn).sum(1)) * 1000
    return lap[(pid == k) & ~fold & (c >= ring_min)]


def _rodrigues(p: np.ndarray, axis: np.ndarray, th: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return p @ (np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * K @ K).T


def turn(M: dict, X: np.ndarray, held, turns: list[dict], body=None, steps: int = 6, iters: int = 20,
         relax_iters: int = RELAX_ITERS, pieces=None, tol: float | None = None, confirm: int = CONFIRM_ITERS,
         log=None):
    """TURN what a hand grips about a line, staged (a band end swung open about its hinge, a cuff popped up about its
    fold): each turn {"at": grip (as a pull handle's "at"; it grips the cloth within "patch" (TURN_PATCH, 15 mm on the
    pattern) of what it names: the band end's 3 corner vertices turned alone pinched a lobe at its top corner, 21 %
    vs 3 % closed, Joe's arrow), "about": [point a, point b] (vertices / "piece:point"),
    "deg": angle, "toward": direction (as a pull's "dir"; default "side") the grip's centroid should start moving
    along (picks the sense), "side_from"?}. The free cloth relaxes against the pattern first, then `steps` steps each
    turn a further deg / steps (grips rigid, held still) and re-solve (`iters`). Returns (X_new, info: start / end
    stretch p99 (%), per turn the sense and how far the grip's centroid went (mm)). Keep the turned grips HELD in a
    following pull (they stay where the hand put them).
    `tol` (C147): turn UNTIL IT WOULD STRETCH, the pull's rule: stop at the last step whose stretch (the free cloth's,
    the pull's read, converged by `confirm` rounds when over) stays within `tol` of the least reached; "deg" is then the
    most it turns. None: the full "deg" whatever it costs (before 2026-10-22: Garrett's band ends turned 65 deg took
    the free fronts' tops to p99 23 / 13 %, wf_simon's to 15 / 16 %).
    A turn's "plumb": [upper, lower] (C182, fit round 36): turn UNTIL THE LINE HANGS PLUMB, the way the cloth would hang:
    that turn stops at the angle where `lower` comes onto the vertical through `upper` in the front view (its x off
    `upper`'s, measured out from the centre line, i.e. away from x = 0 on `upper`'s side, reaches 0; interpolated
    between steps and re-solved), whatever "deg" allows; the stretch / shear stop still applies first. An open jacket's
    lower front swings until its edge below the break hangs plumb (break -> cutawayTop), not by a fixed angle tuned on
    one body (r33-r35: 48 deg, set when the side seam sat further forward, threw the hem corners out like coat tails)."""
    X = np.asarray(X, float)
    held = np.asarray(held)
    if held.dtype != bool:
        hm = np.zeros(len(X), bool)
        hm[held.astype(int)] = True
        held = hm
    A = FlatARAP(M, X)
    Y = A.weld(X)
    fixed = A.welded_mask(held)
    plan, pl = [], []
    for t in turns:
        g = np.unique(A.inv[grip(M, t, held, TURN_PATCH)[0]])
        a, b = (Y[A.inv[vertex(M, q)]] for q in t["about"])
        c = Y[g].mean(0)
        sx = float(X[vertex(M, t["side_from"])][0]) if t.get("side_from") is not None else float(a[0] + b[0]) / 2
        d = direction(t.get("toward", "side"), c, sx, body)
        sense = max((1, -1), key=lambda q: float(((a + _rodrigues((c - a)[None], b - a, q * 0.05))[0] - c) @ d))
        plan.append((g, a, b - a, sense * np.radians(t["deg"]), Y[g].copy(), sense))
        if t.get("plumb"):
            u, lo = (A.inv[vertex(M, q)] for q in t["plumb"])
            pl.append((len(plan) - 1, u, lo, 1.0 if Y[u][0] >= 0 else -1.0))
        fixed[g] = True
    if pieces is None:
        free = ~A.unweld(fixed)
        pieces = sorted(set(np.asarray(M["piece"])[free].tolist()))
    Y = A.solve(Y, fixed, relax_iters)
    tf = thread_faces(M, pieces, ~held)
    st = lambda W: thread_p99(M, A.unweld(W), faces=tf)  # (threads, shear: C169)
    s0, sh0 = st(Y)
    least, lock = s0, _shear_lock(sh0)
    done, stopped = 0, "deg"
    share = np.zeros(len(plan))  # (each turn's share of its deg reached)
    stop_at = {}  # (plumb turns: the share where the line hung plumb)
    plumb_off = lambda W, u, lo, sg: sg * float(W[lo][0] - W[u][0])
    off_prev = {i: plumb_off(Y, u, lo, sg) for i, u, lo, sg in pl}

    def place(sh):
        T = Y.copy()
        for (g, a, ax, th, p0, _s), q in zip(plan, sh):
            T[g] = a + _rodrigues(p0 - a, ax, th * q)
        return T

    for k in range(1, steps + 1):
        nxt = np.array([stop_at.get(i, k / steps) for i in range(len(plan))])
        Yk = A.solve(place(nxt), fixed, iters)
        crossed = False
        for i, u, lo, sg in pl:
            if i in stop_at:
                continue
            o = plumb_off(Yk, u, lo, sg)
            if o >= 0:
                o0 = off_prev[i]
                f = o0 / (o0 - o) if o0 < 0 else 0.0
                stop_at[i] = share[i] + (nxt[i] - share[i]) * f
                crossed = True
            off_prev[i] = o
        if crossed:
            nxt = np.array([stop_at.get(i, k / steps) for i in range(len(plan))])
            Yk = A.solve(place(nxt), fixed, iters)
        if tol is not None:
            s, sh = st(Yk)
            if log:
                log(f"turn step {k}: {abs(np.degrees(plan[0][3])) * k / steps:.0f} deg, threads p99 {s * 100:.2f} %, "
                    f"shear p99 {_shmax(sh)} deg")
            confirmed = (s > least + tol or _jammed(sh, lock)) and confirm
            if confirmed:
                s, sh = st(A.solve(Yk, fixed, confirm, eps=CONVERGED))
            if s > least + tol or _jammed(sh, lock):
                stopped = "stretch" if s > least + tol else "shear"
                break
            if not confirmed:
                least = min(least, s)
        Y, done, share = Yk, k, nxt
        if pl and len(stop_at) == len(plan):
            stopped = "plumb"
            break
    Xn = A.unweld(Y)
    Xn[held] = X[held]
    s1, sh1 = st(A.weld(Xn))
    info = {"stretch_p99_start": round(s0 * 100, 2), "stretch_p99_end": round(s1 * 100, 2),
            "shear_p99_deg": [_shmax(sh0), _shmax(sh1)],
            "deg_turned": [round(float(abs(np.degrees(th))) * float(q), 1) for (_g, _a, _x, th, _p, _s), q in zip(plan, share)],
            "stopped": stopped, "plumb": {str(turns[i]["at"]): {"hung": bool(i in stop_at and share[i] >= stop_at[i] - 1e-9),
                                                                 "off_mm": round(plumb_off(Y, u, lo, sg) * 1000, 1)}
                                          for i, u, lo, sg in pl} or None,
            "turns": {str(t["at"]): {"sense": s, "moved_mm": round(float(np.linalg.norm(Y[g].mean(0) - p0.mean(0)))
                                                                    * 1000, 1)}
                      for t, (g, _a, _x, _t, p0, s) in zip(turns, plan)}}
    return Xn, info


SLIDE_DS = 0.002  # m: a slide's march step along the under surface
SLIDE_NORMAL_K = 8  # under-surface vertices averaged for the march's normal (one vertex's normal zigzags the path)


def _march(surf, P: np.ndarray, sgn: np.ndarray, arc: np.ndarray, ds: float = SLIDE_DS) -> np.ndarray:
    """Each point of P moved ALONG the surface, horizontally round it, away from x = 0 on its side (sgn +-1), by `arc` (m),
    keeping its offset off the surface: the positions at every 1 / n of the way, (n + 1, len(P), 3)."""
    k = min(SLIDE_NORMAL_K, len(surf.V))

    def nrm(Q):
        _d, i = surf.tree.query(Q, k=k)
        n = surf.N[i.reshape(len(Q), -1)].mean(1)
        return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)

    def off(Q):
        return surf.signed(Q)[0]
    P = np.asarray(P, float)
    h0 = off(P)
    nsub = max(1, int(np.ceil(float(np.max(arc, initial=0.0)) / ds)))
    cur, out = P.copy(), [P.copy()]
    for _ in range(nsub):
        n = nrm(cur)
        t = np.cross(n, np.array([0.0, 0.0, 1.0]))
        t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
        t *= np.where(t[:, 0] * sgn >= 0, 1.0, -1.0)[:, None]
        cur = cur + t * (np.asarray(arc, float) / nsub)[:, None]
        for _r in range(2):
            cur = cur + (h0 - off(cur))[:, None] * nrm(cur)
        out.append(cur.copy())
    return np.stack(out)


def slide(M: dict, X: np.ndarray, held, slides: list[dict], body=None, steps: int = 10, iters: int = 20,
          relax_iters: int = RELAX_ITERS, pieces=None, tol: float | None = 0.01, confirm: int = CONFIRM_ITERS,
          log=None):
    """SLIDE cloth ALONG what it lies on (fit round 37): an unbuttoned front doesn't swing out like a door, its lapped
    cloth slides back round the body. Each slide {"at": a border "piece:a..b" (an edge), "patch": m on the pattern
    (default 0.04: the hand's band along the edge), "by": metres of arc, or {"plumb": [upper, lower]}: the lap set by
    the hang: every edge vertex from `upper` to `lower` slides until it lies on the vertical through `upper` in the
    front view, the edge below `lower` by `lower`'s arc (the cut-away keeps its shape), "follow": m (pattern distance
    beyond the band over which the rest of the piece follows, falling off to 0; default 0.12)}. The band moves along the
    body surface, horizontally round it, toward the side, keeping its fitted offset off the body; the free cloth starts
    where it would follow and is solved. Staged, until it would stretch (`tol`, as turn). What it grips stays held
    for later ops ("let_go_above": a point: style() lets go of the grip above it after the slide, C185: the un-lap's
    small arcs just under the break, held, kept the later swing and smooths from pulling the edge straight). Returns
    (X_new, info)."""
    from . import pattern_form as pf_
    from .cloth_made import outward
    X = np.asarray(X, float)
    held = _mask(held, len(X))
    bvf = _body_vf(body)
    if bvf is None:
        raise ValueError("slide needs the body (it slides along it)")
    surf = pf_._Surface(bvf[0], outward(*bvf))
    uv = np.asarray(M["uv"], float)
    pid = np.asarray(M["piece"])
    A = FlatARAP(M, X)
    Y = A.weld(X)
    fixed = A.welded_mask(held)
    jobs, info_s = [], {}
    for sl in slides:
        ch = border_chain(M, sl["at"])
        pc = int(pid[ch[0]])
        sgn = 1.0 if float(np.median(X[ch, 0])) >= 0 else -1.0
        by = sl.get("by", {"plumb": None})
        if isinstance(by, dict):
            pl = by.get("plumb") or [int(ch[0]), int(ch[-1])]
            up, lo = vertex(M, pl[0]), vertex(M, pl[1])
            xu = sgn * float(X[up][0])
            i_up, i_lo = int(np.where(ch == up)[0][0]), int(np.where(ch == lo)[0][0])
            reach = 0.25
            tr = _march(surf, X[ch], np.full(len(ch), sgn), np.full(len(ch), reach))
            fr = np.linspace(0.0, reach, len(tr))
            arc_ch = np.zeros(len(ch))
            for j in range(i_up, len(ch)):
                xs = sgn * tr[:, j, 0]
                hit = np.where(xs >= xu)[0]
                if j <= i_lo:
                    if not len(hit) or hit[0] == 0:
                        arc_ch[j] = 0.0 if len(hit) else reach
                    else:
                        h = hit[0]
                        f = (xu - xs[h - 1]) / max(xs[h] - xs[h - 1], 1e-9)
                        arc_ch[j] = fr[h - 1] + f * (fr[h] - fr[h - 1])
                else:
                    arc_ch[j] = arc_ch[i_lo]
            if by.get("ramp"):  # (the lap taken up linearly from `upper` to `lower`: the edge between them one straight line)
                zc = X[ch, 2]
                r = np.clip((zc[i_up] - zc) / max(zc[i_up] - zc[i_lo], 1e-6), 0.0, 1.0)
                arc_ch = np.where(np.arange(len(ch)) <= i_lo, arc_ch[i_lo] * r, arc_ch)
                arc_ch[:i_up] = 0.0
        else:
            arc_ch = np.full(len(ch), float(by))
        arc_ch = arc_ch * float(sl.get("scale", 1.0))
        patch, follow = float(sl.get("patch", 0.04)), float(sl.get("follow", 0.12))
        on = np.where((pid == pc) & ~held)[0]
        d_e, j_e = cKDTree(uv[ch]).query(uv[on])
        w = np.clip(1.0 - (d_e - patch) / max(follow, 1e-6), 0.0, 1.0)
        arc_v = arc_ch[j_e] * w
        grip_v = on[d_e <= patch]
        withp = [q for q in sl.get("with") or [] if q in M["names"]]  # (a jacket with no side panel: just the back)
        if withp:  # the pieces round the body behind it follow too, by the angle round from the edge to CB
            zt = float(X[ch[0], 2])
            wv = np.where(np.isin(pid, _piece_ids(M, withp)) & ~held)[0]
            above = wv[X[wv, 2] >= zt]
            held = held.copy()
            held[above] = True
            fixed[A.inv[above]] = True
            on = np.r_[on, wv[X[wv, 2] < zt]]
            Bv = bvf[0]

            def phi(P):
                yc = np.empty(len(P))
                for i, z in enumerate(P[:, 2]):
                    b = Bv[np.abs(Bv[:, 2] - z) < 0.02]
                    yc[i] = 0.5 * (b[:, 1].min() + b[:, 1].max()) if len(b) else 0.0
                return np.arctan2(np.abs(P[:, 0]), -(P[:, 1] - yc))
            oz = np.argsort(X[ch, 2])
            arc_z = lambda z: np.interp(z, X[ch, 2][oz], arc_ch[oz], right=0.0)
            phe = phi(X[ch])
            phe_z = lambda z: np.interp(z, X[ch, 2][oz], phe[oz])
            Pn = X[on]
            ww = np.clip((np.pi - phi(Pn)) / np.maximum(np.pi - phe_z(Pn[:, 2]), 1e-3), 0.0, 1.0)
            isg = np.isin(on, grip_v)
            arc_v = np.where(isg, np.r_[arc_v, np.zeros(len(on) - len(arc_v))], arc_z(Pn[:, 2]) * ww)
        tr = _march(surf, X[on], np.full(len(on), sgn), arc_v)
        jobs.append((on, tr, A.inv[grip_v]))
        fixed[A.inv[grip_v]] = True
        info_s[str(sl["at"])] = {"arc_mm": [round(float(arc_ch.min()) * 1000, 1), round(float(arc_ch.max()) * 1000, 1)],
                                 "gripped": int(len(grip_v))}
    if pieces is None:
        pieces = sorted(set(pid[~A.unweld(fixed)].tolist()))
    Y = A.solve(Y, fixed, relax_iters)
    tf = thread_faces(M, pieces, ~held)
    st = lambda W: thread_p99(M, A.unweld(W), faces=tf)
    s0, sh0 = st(Y)
    least, lock = s0, _shear_lock(sh0)
    done, stopped = 0, "done"

    def place(f):
        T = Y.copy()
        for on, tr, gw in jobs:
            q = f * (len(tr) - 1)
            i0 = int(np.floor(q))
            i1 = min(i0 + 1, len(tr) - 1)
            T[A.inv[on]] = tr[i0] + (q - i0) * (tr[i1] - tr[i0])
        return T

    for k in range(1, steps + 1):
        Yk = A.solve(place(k / steps), fixed, iters)
        if tol is not None:
            s, sh = st(Yk)
            if log:
                log(f"slide step {k}: threads p99 {s * 100:.2f} %, shear p99 {_shmax(sh)} deg")
            confirmed = (s > least + tol or _jammed(sh, lock)) and confirm
            if confirmed:
                s, sh = st(A.solve(Yk, fixed, confirm, eps=CONVERGED))
            if s > least + tol or _jammed(sh, lock):
                stopped = "stretch" if s > least + tol else "shear"
                break
            if not confirmed:
                least = min(least, s)
        Y, done = Yk, k
    Xn = A.unweld(Y)
    Xn[held] = X[held]
    s1, sh1 = st(A.weld(Xn))
    return Xn, {"stretch_p99_start": round(s0 * 100, 2), "stretch_p99_end": round(s1 * 100, 2),
                "shear_p99_deg": [_shmax(sh0), _shmax(sh1)], "share_done": round(done / steps, 2), "stopped": stopped,
                "slides": info_s}


def plumb(M: dict, X: np.ndarray, held, borders: list, ramp: float = 0.05, axes: str = "xy", steps: int = 10,
          iters: int = 20, relax_iters: int = RELAX_ITERS, tol: float | None = 0.01, confirm: int = CONFIRM_ITERS,
          pieces=None, log=None):
    """LAY SEAMS ON THE VERTICAL (fit round 35, C181): each border ("piece:a..b", a seam) moved, staged, onto the
    vertical through its top vertex below it (ramped in over `ramp` m): y (front / back) both ways, x only outward
    (axes "xy"; "y" leaves x). A plumb jacket's side seams hang plumb from the underarm (pattern_form.PLUMB_HOLD is
    the fit's form of the same rule). Until it would stretch (`tol`, as turn). What it grips stays held for later ops.
    Returns (X_new, info)."""
    X = np.asarray(X, float)
    held = np.asarray(held)
    if held.dtype != bool:
        hm = np.zeros(len(X), bool)
        hm[held.astype(int)] = True
        held = hm
    A = FlatARAP(M, X)
    Y = A.weld(X)
    fixed = A.welded_mask(held)
    g_all, tgt = [], []
    for b in borders:
        g = np.unique(A.inv[border_chain(M, b)])
        top = Y[g[np.argmax(Y[g, 2])]]
        r = np.clip((top[2] - Y[g, 2]) / max(ramp, 1e-6), 0.0, 1.0)
        T = Y[g].copy()
        if "x" in axes:
            T[:, 0] = np.where(np.abs(T[:, 0]) < abs(top[0]), T[:, 0] + r * (top[0] - T[:, 0]), T[:, 0])
        if "y" in axes:
            T[:, 1] = T[:, 1] + r * (top[1] - T[:, 1])
        g_all.append(g)
        tgt.append(T)
        fixed[g] = True
    if pieces is None:
        pieces = sorted(set(np.asarray(M["piece"])[~A.unweld(fixed)].tolist()))
    Y = A.solve(Y, fixed, relax_iters)
    tf = thread_faces(M, pieces, ~held)
    st = lambda W: thread_p99(M, A.unweld(W), faces=tf)
    s0, sh0 = st(Y)
    least, lock = s0, _shear_lock(sh0)
    P0 = [Y[g].copy() for g in g_all]
    done, stopped = 0, "done"
    for k in range(1, steps + 1):
        T = Y.copy()
        for g, p0, t in zip(g_all, P0, tgt):
            T[g] = p0 + (t - p0) * k / steps
        Yk = A.solve(T, fixed, iters)
        if tol is not None:
            s, sh = st(Yk)
            if log:
                log(f"plumb step {k}: threads p99 {s * 100:.2f} %, shear p99 {_shmax(sh)} deg")
            confirmed = (s > least + tol or _jammed(sh, lock)) and confirm
            if confirmed:
                s, sh = st(A.solve(Yk, fixed, confirm, eps=CONVERGED))
            if s > least + tol or _jammed(sh, lock):
                stopped = "stretch" if s > least + tol else "shear"
                break
            if not confirmed:
                least = min(least, s)
        Y, done = Yk, k
    Xn = A.unweld(Y)
    Xn[held] = X[held]
    s1, sh1 = st(A.weld(Xn))
    info = {"stretch_p99_start": round(s0 * 100, 2), "stretch_p99_end": round(s1 * 100, 2),
            "shear_p99_deg": [_shmax(sh0), _shmax(sh1)], "share_done": round(done / steps, 2), "stopped": stopped,
            "moved_mm": {b: round(float(np.abs(Y[g] - p0).max()) * 1000, 1) for b, g, p0 in zip(borders, g_all, P0)}}
    return Xn, info


def hold_mask(M: dict, X: np.ndarray, free, below=None, margin: float = 0.005,
              button_hold: float = BUTTON_HOLD) -> np.ndarray:
    """What stays still: every piece not in `free`, and on the free pieces whatever lies more than `margin` below
    `below` (z): a garment point "piece:point", or "closure:<name>" = that closure's top fastened button (the shirt's
    fronts below the first button stay closed). With a closure, every FASTENED pair of it is held too, with the cloth
    within `button_hold` (m, on its pattern) round each of its two vertices: a button sewn through an area, done up.
    Holding only what lay `margin` below the top button left the button itself free: Garrett's styled shirt (probe s1 /
    s2, 2026-10-22) pulled its first fastened button 8.7 / 19.4 mm open, so the first DONE button dropped to the
    second (203 mm below HPS vs the concept's 83)."""
    pid = np.asarray(M["piece"])
    held = ~np.isin(pid, _piece_ids(M, free))
    if below:
        if below.startswith("closure:"):
            cn = below.split(":", 1)[1]
            zs = [X[np.asarray(v, int)].mean(0)[2] for c in M.get("closures") or [] if c.get("name") == cn
                  for v in (c.get("v") or [])]
            if not zs:
                have = sorted({c.get("name") for c in M.get("closures") or []})
                raise ValueError(f"no fastened closure {cn!r} (closures: {', '.join(map(str, have)) or 'none'})")
            zb = max(zs)
            uv = np.asarray(M["uv"], float)
            for c in M.get("closures") or []:
                if c.get("name") != cn:
                    continue
                for v in c.get("v") or []:
                    v = np.asarray(v, int).ravel()
                    if np.linalg.norm(X[v[0]] - X[v[-1]]) > FASTENED:  # (an undone pair is not held)
                        continue
                    for i in v:
                        held |= (pid == pid[i]) & (np.linalg.norm(uv - uv[i], axis=1) <= button_hold)
        else:
            zb = float(X[vertex(M, below)][2])
        held |= X[:, 2] < zb - margin
    return held


def edge_turns(M: dict, X: np.ndarray, piece: str, mid: str, end: str, center=None, window: float = 0.015,
               skip_deg: float = 12.0, min_deg: float = 15.0) -> dict:
    """The side-view swoop of a piece's free outer edge (shirt spike profile.py; Joe: "one continuous swoop instead of
    three different angles"): the piece's border vertices that aren't sewn, on `end`'s side of `mid` (pattern x),
    ordered from mid; the turn (deg) of the edge's direction in the side plane (y, z) over `window` (m, 3D arc); the
    largest and where it is (deg round the ring from CB about `center`'s centroid), the point's own corner (the last
    `skip_deg`) and the `min_deg` round CB (the two halves meet there: the closed collar turns 19 / 31 deg at CB) left
    out. A hard hold border: 29 deg at 79 deg from CB (q40); feathered: 18 (f2)."""
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    k = _piece_ids(M, [piece])[0]
    Ek = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    Ek = Ek[(pid[Ek[:, 0]] == k) & (pid[Ek[:, 1]] == k)]
    u, c = np.unique(Ek, axis=0, return_counts=True)
    bv = np.unique(u[c == 1])
    sew = set(np.asarray(M.get("sew") if M.get("sew") is not None else [], int).ravel().tolist())
    outer = np.array([i for i in bv if i not in sew])
    m0, e0 = vertex(M, mid), vertex(M, end)
    o = outer[np.sign(uv[outer, 0] - uv[m0, 0]) == np.sign(uv[e0, 0] - uv[m0, 0])]
    o = o[np.argsort(np.abs(uv[o, 0] - uv[m0, 0]))]
    yz = X[o][:, [1, 2]]
    arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(X[o], axis=0), axis=1))]
    ang = np.degrees(np.arctan2(X[o, 0] - 0, X[o, 1] - 0))
    if center is not None:
        cc = X[pid == _piece_ids(M, [center])[0]][:, :2].mean(0)
        ang = np.degrees(np.arctan2(X[o, 0] - cc[0], X[o, 1] - cc[1]))
    def turn_at(i, w):
        a = np.searchsorted(arc, arc[i] - w / 2)
        b = np.searchsorted(arc, arc[i] + w / 2) - 1
        if a >= i or b <= i:
            return None
        d1, d2 = yz[i] - yz[a], yz[b] - yz[i]
        return float(np.degrees(np.arccos(np.clip(d1 @ d2 / (np.linalg.norm(d1) * np.linalg.norm(d2) + 1e-12), -1, 1))))
    # KINK = THE TURN NOT EXPLAINED BY THE EDGE'S OWN BEND (muslin default, C168): an arc turns twice as much over twice
    # the window, a crease turns as much; so the kink at a vertex is its turn over `window` less half its turn over
    # 2 x `window` (an arc: 0; a crease of c deg: c / 2). A collar edge bending down to its point turns 20-23 deg per
    # 15 mm there and is one swoop; a hard hold border creases it
    turns = []
    for i in range(len(o)):
        t, t2 = turn_at(i, window), turn_at(i, 2 * window)
        if t is None or t2 is None:
            continue
        turns.append((t, ang[i], t - t2 / 2))
    turns = np.array(turns)
    turns = turns[(np.abs(turns[:, 1]) < np.abs(ang[-1]) - skip_deg) & (np.abs(turns[:, 1]) >= min_deg)]
    j, k_ = int(np.argmax(turns[:, 0])), int(np.argmax(turns[:, 2]))
    return {"max_turn_deg": round(float(turns[j, 0]), 1), "at_deg": round(float(turns[j, 1]), 1),
            "p50_deg": round(float(np.median(turns[:, 0])), 1),
            "kink_deg": round(float(turns[k_, 2]), 1), "kink_at_deg": round(float(turns[k_, 1]), 1)}


def ops_pieces(M: dict, ops: list[dict]) -> list:
    """The pieces a styling op list moves: what its pulls / turns grip and its smooths / holds / pushes name."""
    pid = np.asarray(M["piece"])
    at = [h["at"] for o in ops for h in (o.get("pull") or {}).get("handles", [])] + \
         [t["at"] for o in ops for t in (o.get("turn") or {}).get("turns", [])]
    out = {M["names"][int(pid[v])] for a in at for v in vertices(M, a)}
    for o in ops:
        (kind, a), = o.items()
        if kind in ("smooth", "hold", "push"):
            out |= set(a.get("pieces") or [])
            if "border" in a:
                out.add(a["border"].split(":")[0])
        if kind == "plumb":
            out |= {b.split(":")[0] for b in a.get("borders") or []}
        if kind == "slide":
            out |= {sl["at"].split(":")[0] for sl in a.get("slides") or []}
            out |= {p for sl in a.get("slides") or [] for p in sl.get("with") or []}
    return sorted(p for p in out if p in M["names"])


def style_ops(g: dict) -> list:
    """The styling op list a garment is worn with: the wear's (garment_kb kinds.<kind>.wear.<tie|no_tie>.style), or the
    garment's own "style": a list replaces it, a dict {op kind: {param: value}} sets those params on every op of that
    kind (Garrett's shirt: {"turn": {"tol": 0.005, "steps": 16}}: its concept's first button 83 below HPS leaves the
    fronts too little cloth for the wear's full 65 deg band-end turn, p99 39 %; turned until it would stretch: 20 deg,
    7.8 %), false none."""
    from . import garment_design
    own = g.get("style")
    if own is False:
        return []
    ops = own if isinstance(own, list) else garment_design.wear(g, "style")
    ops = [{k: dict(v) for k, v in o.items()} for o in ops or []]
    if isinstance(own, dict):
        bad = sorted(set(own) - {"pull", "turn", "smooth", "relax", "hold", "push", "plumb"})
        if bad:
            raise ValueError(f"style edits name no op kind {bad} (pull, turn, smooth, relax, hold, push)")
        for o in ops:
            (kind, a), = o.items()
            a.update(own.get(kind) or {})
    return ops


def worn_style(M: dict, X: np.ndarray, body, g: dict, log=None, under=None):
    """HOW THE KIND IS WORN, set by hand (C146): the wear's "style" ops (garment_kb kinds.<kind>.wear.<tie|no_tie>.style,
    via garment_design.wear(g, "style")) run on the closed form fit: the pieces they move are free, the rest held, and
    on those pieces whatever lies below the top fastened front button stays closed. A shirt without a tie gets its
    collar opened as Joe's references show (the shirt spike's c1). Returns (X_new, infos) or (X, None) when the kind has
    no style for how it is worn. under: (V, F) of the garment under a worn-open one (a floor, layer_floor)."""
    ops = style_ops(g)
    if not ops:
        return np.asarray(X, float), None
    free = ops_pieces(M, ops)
    if g.get("worn_open"):  # (C174: a garment worn OPEN: fitted open, no button done; its stitched patches sewn as the
        # fit has them (welded like seams) and the fit's layer order kept as a floor (body, flaps, patches; C170 / C173))
        st_ = np.asarray(M.get("stitch") if M.get("stitch") is not None else [], int).reshape(-1, 2)
        Ms = dict(M, sew=np.r_[np.asarray(M["sew"], int).reshape(-1, 2), st_])
        pid_, nm_ = np.asarray(M["piece"]), list(M["names"])
        for pa, pb in pid_[st_] if len(st_) else []:  # (a patch stitched to a moved piece moves with it: held, the
            # pocket flaps sank 14-19 of 25 vertices into the opened fronts, r31 k1)
            if nm_[pa] in free or nm_[pb] in free:
                free = sorted(set(free) | {nm_[pa], nm_[pb]})
        # (under = (V, F): the garment under it as a floor too, the layer that supports it; supports thread: hung
        # without it, Garrett's jacket chest went down through the shirt)
        return style(Ms, X, hold_mask(Ms, X, free), ops, body=body, log=log,
                     floor=layer_floor(Ms, X, body=body, under=under))
    below = "closure:front" if any(c.get("name") == "front" for c in M.get("closures") or []) else None
    held = hold_mask(M, X, free, below)
    return style(M, X, held, ops, body=body, log=log)


# THE OPEN COLLAR'S READS (C146): what the shirt spike measured every look, beside Joe's references. Front view =
# (x, z); landmarks on the 3D fit: the collar points (tips), the collar's sewn ends (inner corners, = the band's top
# corners at CF), the collar's outer edge at +-85 deg round the neck from CB (the leaf's turn at the side of the neck),
# the V's bottom (the lowest height above which the fronts' edges are parted). Ratios over the neck width there (outer
# edge to outer edge). Targets: Joe's open-shirt photo / the concept trace, read by eye (spikes/shirt_spike/angles.py).
OPEN_COLLAR_TARGETS = {
    "corners apart / neck": (0.40, 0.75, "photo 0.50, trace 0.69"),
    "tips apart / neck": (0.70, 1.15, "photo 0.72, trace 1.01"),
    "V angle (deg)": (50.0, 100.0, "photo 69, trace 95"),
    "V depth below tips / neck": (0.0, 0.25, "photo 0.19, trace 0.04"),
    "leaf front edge (deg from down)": (25.0, 48.0, "photo 29-35, trace 27-34"),
    "edge max turn per 40 mm (deg)": (0.0, 32.0, "one arc: c1 30; x5's S 46-50"),
    "collar crumple p95 (mm)": (0.0, 0.30, "closed 0.14; c1 0.24"),
    "tip crumple p95 (mm)": (0.0, 0.22, "closed 0.03-0.07"),
    "folded faces near the points": (0, 0, "closed 0"),
    "collar + band mirror p95 (mm)": (0.0, 6.0, "mesh floor 1-2"),
}


def open_collar_reads(M: dict, X: np.ndarray) -> dict:
    """{item: value} for OPEN_COLLAR_TARGETS on a shirt with Simon's piece / point names (collar, stand, front.L / .R)."""
    from scipy.spatial import cKDTree
    X = np.asarray(X, float)
    pid = np.asarray(M["piece"])
    nm = list(M["names"])
    uv = np.asarray(M["uv"], float)
    P = M["points"]
    tipL, tipR = X[P["collar:leftTopEdge"]], X[P["collar:rightTopEdge"]]
    if tipL[0] > tipR[0]:
        tipL, tipR = tipR, tipL
    cL, cR = X[P["collar:leftBottomEdge"]], X[P["collar:rightBottomEdge"]]
    if cL[0] > cR[0]:
        cL, cR = cR, cL
    out_ch = border_chain(M, "collar:leftTopEdge..topMid..rightTopEdge")
    c = X[pid == nm.index("stand")][:, :2].mean(0)
    ang = np.degrees(np.arctan2(X[out_ch, 0] - c[0], X[out_ch, 1] - c[1]))
    oL, oR = X[out_ch[np.argmin(np.abs(ang + 85))]], X[out_ch[np.argmin(np.abs(ang - 85))]]
    if oL[0] > oR[0]:
        oL, oR = oR, oL
    neck = abs(oR[0] - oL[0])
    eL = (pid == nm.index("front.L")) & (uv[:, 0] < uv[P["front.L:placketTopFold1"], 0] + 0.003)
    eR = (pid == nm.index("front.R")) & (uv[:, 0] > uv[P["front.R:placketTopOut"], 0] - 0.003)
    top = max(X[P["front.L:cfNeck"], 2], X[P["front.R:cfNeck"], 2])
    vz, vx = top, 0.0
    for z in np.arange(top, top - 0.3, -0.003):  # (spikes/shirt_spike/openm.py: front.L's edge on the +x side once parted)
        a = X[eL & (np.abs(X[:, 2] - z) < 0.003)]
        b = X[eR & (np.abs(X[:, 2] - z) < 0.003)]
        if not len(a) or not len(b):
            continue
        if a[:, 0].min() - b[:, 0].max() > 0.002:
            vz, vx = z, 0.5 * (a[:, 0].min() + b[:, 0].max())
        else:
            break
    fz = lambda p: np.array([p[0], p[2]])
    V = np.array([vx, vz])
    l1, l2 = fz(cL) - V, fz(cR) - V
    deg = lambda u, w: float(np.degrees(np.arccos(np.clip(u @ w / (np.linalg.norm(u) * np.linalg.norm(w)), -1, 1))))
    down = np.array([0.0, -1.0])
    fe = [deg(fz(tipL) - fz(cL), down), deg(fz(tipR) - fz(cR), down)]
    # the outer edge's turn per 40 mm of arc in 3D (edgeplot.py), the middle 80 % (not the points' own corners), off CB
    p3 = X[out_ch]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p3, axis=0), axis=1))]
    turns = []
    for i in range(len(p3)):
        if s[i] < 0.1 * s[-1] or s[i] > 0.9 * s[-1] or abs(ang[i]) < 15:
            continue
        a_ = np.searchsorted(s, s[i] - 0.02)
        b_ = np.searchsorted(s, s[i] + 0.02) - 1
        if a_ < i < b_:
            turns.append(deg(p3[i] - p3[a_], p3[b_] - p3[i]))
    tips = [tip_read(M, X, q) for q in ("collar:leftTopEdge", "collar:rightTopEdge")]
    cs = np.isin(pid, [nm.index("collar"), nm.index("stand")])
    mir, _ = cKDTree(X).query(X[cs] * [-1, 1, 1])
    return {"corners apart / neck": round(float(np.linalg.norm(fz(cR) - fz(cL)) / neck), 2),
            "tips apart / neck": round(float(np.linalg.norm(fz(tipR) - fz(tipL)) / neck), 2),
            "V angle (deg)": round(deg(l1, l2), 0),
            "V depth below tips / neck": round(float((0.5 * (tipL[2] + tipR[2]) - vz) / neck), 2),
            "leaf front edge (deg from down)": round(max(fe), 0),
            "edge max turn per 40 mm (deg)": round(max(turns) if turns else 0.0, 0),
            "collar crumple p95 (mm)": round(float(np.percentile(crumple(M, X, "collar"), 95)), 3),
            "tip crumple p95 (mm)": round(max(t["crumple_p95_mm"] for t in tips), 3),
            "folded faces near the points": int(sum(folded(M, X, q) for q in ("collar:leftTopEdge", "collar:rightTopEdge"))),
            "collar + band mirror p95 (mm)": round(float(np.percentile(mir, 95) * 1000), 1)}


# THE NECK-SHOULDER LUMP (garrett collar round 2, 2026-10-22; Joe on gc1: "the only real issue is the lumpy part here",
# the side view under the fall's outer edge). What it was: the shoulder seam (front | yoke) within ~50 mm of the neck
# point standing off the body as a ridge (a fin in a horizontal section) with a pillow of front in front of it: the seam
# bridged Garrett's neck-shoulder corner (neck point 2 cm up a near-vertical neck, the shoulder 40 mm below it 25 mm
# out) and the yoke there was sheared +7 / -5.5 %. Already in the CLOSED fit; the style changed it < 1 mm. Two reads:
# the CREST (the turn between the cloth's normals either side of a neck point's shoulder seam, both oriented off the
# body, median over 5-35 mm from the neck point: a flat seam ~0, a fin 60+) and the BUMP (the body cloth's distance off
# the body minus its mean over 30 mm, the max within 60 mm of the neck point: a smooth stand-off cancels, a lump stays).
NECK_LUMP_TARGETS = {
    "neck-shoulder seam crest (deg)": (0.0, 32.0, "wf_simon closed 21, styled 7; gc1 61 / 62"),
    "body cloth bump at the neck point (mm)": (0.0, 8.0, "wf_simon 5.3 / 5.7; gc1 14.8 / 14.7"),
}


def neck_lump_reads(M: dict, X: np.ndarray, body) -> dict:
    """{item: value} for NECK_LUMP_TARGETS: every piece point "hps" / "hps.m" with a "shoulder" / "shoulder.m" on the
    same piece is a neck point with its shoulder seam (piece:hps..shoulder); crest and bump read round each, the worst
    kept. {} when the garment has no such points or no body."""
    BV, BF = _body_vf(body) if body is not None else (None, None)
    if BV is None:
        return {}
    X = np.asarray(X, float)
    F = np.asarray(M["F"], int)
    pid = np.asarray(M["piece"])
    nm = list(M["names"])
    P = M["points"]
    fn = np.cross(BV[BF[:, 1]] - BV[BF[:, 0]], BV[BF[:, 2]] - BV[BF[:, 0]])
    vn = np.zeros_like(BV)
    for k in range(3):
        np.add.at(vn, BF[:, k], fn)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    bt = cKDTree(BV)
    _, j = bt.query(X)
    sd = ((X - BV[j]) * vn[j]).sum(1)
    cn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    fc = X[F].mean(1)
    _, jf = bt.query(fc)
    cn *= np.sign((cn * (fc - BV[jf])).sum(1))[:, None]  # (oriented off the body: winding-free)
    fp = pid[F[:, 0]]
    ft = cKDTree(fc)
    made = [i for i, n_ in enumerate(nm) if n_.startswith(("collar", "stand"))]
    crest, bump = [], []
    for k, v in P.items():
        piece, pt = k.split(":", 1)
        if pt not in ("hps", "hps.m") or f"{piece}:{pt.replace('hps', 'shoulder')}" not in P:
            continue
        ch = border_chain(M, f"{piece}:{pt}..{pt.replace('hps', 'shoulder')}")
        Q = X[ch]
        L = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        turns = []
        for d_ in np.arange(0.005, 0.0351, 0.005):
            ii = np.asarray(ft.query_ball_point(Q[int(np.argmin(np.abs(L - d_)))], 0.012), int)
            ii = ii[~np.isin(fp[ii], made)]  # (the collar's fall lying over the seam is not the seam)
            ps, cnt = np.unique(fp[ii], return_counts=True)
            if len(ps) < 2:
                continue
            a, b = (cn[ii[fp[ii] == q]].sum(0) for q in ps[np.argsort(-cnt)][:2])
            turns.append(np.degrees(np.arccos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12), -1, 1))))
        if turns:
            crest.append(float(np.median(turns)))
        sewn = set(fp[np.asarray(ft.query_ball_point(X[v], 0.03), int)].tolist())
        reg = np.where(np.isin(pid, list(sewn)) & (np.linalg.norm(X - X[v], axis=1) < 0.06))[0]
        reg = reg[~np.isin(pid[reg], made)]
        if len(reg) > 10:
            nb = cKDTree(X[reg]).query_ball_point(X[reg], 0.03)
            bump.append(float(max(sd[i] - sd[reg[n]].mean() for i, n in zip(reg, nb))))
    out = {}
    if crest:
        out["neck-shoulder seam crest (deg)"] = round(max(crest), 0)
    if bump:
        out["body cloth bump at the neck point (mm)"] = round(max(bump) * 1000, 1)
    return out


def neck_lump_rows(M: dict, X: np.ndarray, body) -> list:
    """item | target | ours | PASS / FAIL rows for NECK_LUMP_TARGETS (fit_garment prints them for the closed fit and
    the worn one)."""
    r = neck_lump_reads(M, X, body)
    return [{"id": k, "ours": r[k], "target": f"{lo:g}-{hi:g} ({src})", "status": "PASS" if lo <= r[k] <= hi else "FAIL"}
            for k, (lo, hi, src) in NECK_LUMP_TARGETS.items() if k in r]


def open_collar_rows(M: dict, X: np.ndarray) -> list:
    """item | target | ours | PASS / FAIL rows for OPEN_COLLAR_TARGETS (fit_garment prints them for a shirt worn open)."""
    r = open_collar_reads(M, X)
    rows = []
    for k, (lo, hi, src) in OPEN_COLLAR_TARGETS.items():
        v = r[k]
        rows.append({"id": k, "ours": v, "target": f"{lo:g}-{hi:g} ({src})", "status": "PASS" if lo <= v <= hi else "FAIL"})
    return rows
