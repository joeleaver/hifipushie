"""The virtual dress form: a garment ASSEMBLED FROM ITS PATTERN on the body, before any sim (dress-garrett 2026-10-19).

What a pattern maker does on a dress form, as geometry and constraints (no physics, no solver tuning):
  1. the panels are meshed so every seam, notch and FOLD LINE is a chain of mesh edges (cloth.mesh with the garment key
     "mesh_refine": local ~5 mm triangles at the lapel, gorge, notch and collar; `sizing` below);
  2. pinned by landmarks: every neck point (a piece point named "hps", "hps.m") ON the body's neck point (body.at["hps.L"],
     mirrored for the right side; lifted by the layer's ease along the body normal), every centre-back / centre-front point
     on the centre line (x = 0: points named cb*, bottomMid, topMid; fastened closures' buttons), the shoulder point near
     the body's shoulder point (soft);
  3. every sewn pair closed (M["sew"]), fastened closures closed (button on buttonhole);
  4. relaxed onto an offset of the body surface (`ease` per layer; a folded flap one more cloth thickness out; the
     garment UNDER as a second obstacle), as-rigid-as-possible against the flat pattern: edges keep their pattern
     lengths, so ease stands off the body where the pattern is bigger than the form;
  5. folded along the fold lines (garment key "folds", folds.py): each cell on a fold row has the flat pattern folded
     about the row as its rest, so the fold is a hinge exactly on the line, the flap turned to the face the fold names;
  6. a collar (a piece sewn by one edge, wrap "to" neck / seam) stood up from the neckline it is sewn to, then its fall
     turned over its stand.

`assemble(pattern, body)` returns {"V", "F", "M", "info"}; `placement_error` is the validated neck-point measure.
"""
from __future__ import annotations

import math
import os

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import splu
from scipy.spatial import cKDTree

from . import validated

THICK = 0.0015  # m: one cloth layer (a folded flap lies this much further out than its base)
EASE = 0.004  # m: the least a garment lies off what is under it (body or the garment under)
HINGE_BAND = 0.006  # m (pattern) either side of a fold row left out of fold_turned (the bend of a THICK hairpin)
SECTION_W = 0.005  # m: fold_turned reads each row vertex's section from the points within this of its plane
FLAP_PULL = 0.5  # a turned-over flap drawn onto its own base (one THICK out) per round, in both relax phases
# ROLL_GAP (fit round 15, opt-in until A/B'd): a turned flap near its fold line lies off its base by the roll's own
# diameter, not one THICK: a hinge of radius r (folds' rows are r x turn apart) turns 180 deg round a 2r gap. The gap
# fades to THICK over one half-turn of arc (pi r) past the last row. Without it, FLAP_PULL pressed the rolled hinge into a
# hairpin: the lapel's roll line rendered as a 2-3 mm crease where the concept's is 6-7 mm wide (edgeprof.py, front
# view, rows 120-220 below HPS). Tailoring: a lapel's roll line is not pressed in (it is shaped and steamed, then rolled).
ROLL_GAP = False
# A fold whose own base side is narrower than BASE_NARROW (pattern, from its first row) lies on the piece(s) sewn to
# that base as well (fit round 4: a two-piece collar's fall, 4 mm above its seam, lies on its stand). Off = the old rule.
BASE_ACROSS_SEAM = True
BASE_NARROW = 0.012
# A TURNED FLAP LIES ON WHAT IS UNDER IT (shirt round 10, C124): past its own base's edge a turned flap (a collar's
# fall past its stand's neck seam, a lapel past its forepart, a cuff) lies on the rest of the garment under it (the
# yoke, the fronts, the shoulders), one THICK out, drawn there as onto its base (FLAP_PULL). Without it the fall was
# held only where it stood within 2 cm of its stand, along the STAND's normal (horizontal): past the neck seam it hung
# as the rigid turn left it, a vertical tube, its sprung outer edge rippling (Garrett k9a: 9 mm out at the sides, gaps
# 6-15 mm; shoulder KAT: the fall a tube 12 mm inside the bodice). A flap vertex lies on the garment's other cloth (not
# any turned fold's flap) where that cloth is nearer than its own base and the vertex stands over it (sideways within
# FLAP_LAY_REACH x the mesh edge). Known answer: tests/test_pattern_form.py test_sprung_fall_lies_on_the_shoulders.
FLAP_LAY = True
FLAP_LAY_REACH = 1.0
FLAP_LAY_FAR = 0.04  # m: the farthest a flap vertex is drawn down onto the cloth under it in one round's target
# A LAID FLAP MOVES AS CLOTH, NOT VERTEX BY VERTEX (shirt round 11, C127): each flap vertex picked its own surface to
# lie on (its base or the cloth under it) and was drawn there alone, so neighbours along the outer edge got different
# targets: the edge row bent against the next one (boundary dihedral p90 10.6 deg, max 23) and the cloth under it
# showed through between the vertices (7 % of the fall's 0-5 mm edge band, Garrett k10b): the render's sawtooth.
# FLAP_LAY_SMOOTH passes of neighbour averaging (the vertex half, its flap neighbours half) on the flap's correction;
# what keeps it one THICK outside is then re-applied where the smoothed move falls short.
FLAP_LAY_SMOOTH = 0  # (opt-in: DEAD LEVER on Garrett k11b: dihedral p90 7.96 -> 8.22, through 3.7 % both)
BASE_ACROSS_PRESSED = False  # opt-in, fit round 17: a fold's base across a seam continues onto the flap that piece is pressed on (r17c: no change: dead lever)
# LOOSE cloth stands off EVENLY (dress-garrett 2026-10-19 block proportions): in the let-go phase, cloth more than 2 mm
# off its offset is pushed out along its own normal this much per round (a dress form's ease reads as an even stand-off,
# the pattern's lengths stop it). Without it the placement's cross-section stayed: the o4 jacket sleeve read 66 x 139 mm
# at the hem (girth = its pattern's 326) where the drape of the same pattern reads 104 x 104, the waist 360 vs 396.
# Known answer: tests/test_pattern_form.py test_loose_sleeve_hangs_round. OPT-IN (LOOSE_ROUND) until the gate reads it.
LOOSE_ROUND = False
LOOSE_PRESS = 0.0005
# SEAT BY GRAVITY (same session): the seating phase draws cloth onto the form only where the form's surface faces UP
# (x the up-component of its normal): a garment on a dress form rests on the shoulders and the top of an arm and hangs
# from them; drawn on all round, a loose sleeve's ease (wrist girth x 2) had nowhere to go and folded into a lens.
SEAT_GRAVITY = False
HANG = 0.0  # A/B (validation 2): weight as a constant downward pull on the proximal target, m
# PRESS UNDER (same session): on_form assembles a garment over its under garment PRESSED as the sims press it
# (cloth.pressed). OPT-IN until the gate reads it.
PRESS_UNDER = False
# SETTLE (fit round 1, 2026-10-19): the cloth's WEIGHT with REAL CONTACT, a deterministic static settle after the let-go
# (no sim: no time, no velocity, no damping to tune). Each round: the global solve with gravity as a constant per-area
# force on the right-hand side (vertex mass = its pattern area / the mean) against a SMALL proximal weight
# (SETTLE_FREE: the cloth moves as far as its own lengths, seams, pins and bending allow), then every vertex inside
# the offset body (or under-garment) PROJECTED back onto it (hard contact; the old HANG pulled through the arm because
# contact was only the soft proximal push). Vertices in contact are held where they touch at the full proximal weight
# (static friction: cloth resting on a shoulder doesn't slide off it), refactored every SETTLE_REFAC rounds.
# SETTLE_G: the weight per vertex (x mean edge^2, so the stretch it causes does not depend on the mesh size).
# Known answers: tests/test_pattern_form.py test_settle_tube_on_bar, test_settle_cape_on_bar. OPT-IN until validated.
SETTLE = False
SETTLE_ITERS = 150
SETTLE_G = 0.1  # x the mean pattern edge^2 (the stretch it causes does not depend on the mesh size); tube KAT: p99 1.2 %
SETTLE_FREE = 0.005
SETTLE_REFAC = 0  # refactor when more than this many vertices joined the contact set
SETTLE_HOLD = 10.0  # proximal weight of a vertex resting on the form (static friction), x a free one's 1.0
SETTLE_STRAIN = 0.01  # strain limit after each round (Jacobi, SETTLE_SWEEPS): weight never stretches cloth past this
SETTLE_SWEEPS = 4
SETTLE_STEP = 0.004  # m: the most a vertex moves in one round
SETTLE_BEND = 1.0  # the settle's bending x FIT_BEND (FIT_BEND keeps a tube round; cloth's own bending vs its weight is this)
# THE HANG: SUPPORTS, NOT HOLDS (supports thread, 2026-10-23; Joe: "a lot of the styling issues we're having are due to
# holding things that shouldn't be held"). A garment is SUPPORTED by body contact (shoulders, neck, the layer under it),
# sewn seams and fastened closures; everything else is free and HANGS. The fit had no gravity, so holds stood in for it
# (PLUMB_HOLD, the seat's all-round attraction onto the body, the styling's rigid holds). HANG_FIELD: after the let-go,
# the SETTLE phase (gravity as a weak per-area force in the local / global solve, hard contact with the body and the
# layer under it, cloth resting on the form held where it touches: static friction) with the muslin's stop: the weight
# never stretches a THREAD (warp / weft) past HANG_STRAIN (a per-triangle projection in the thread frame, so the bias
# still shears: SETTLE's edge cap jammed shear); and in the seat, the cloth is drawn onto the form only where the form
# holds it from below (HANG_SUPPORT: x the up-component of the body normal, SEAT_GRAVITY's rule), not wrapped round it.
# Not a sim: no time, velocity or collisions beyond the floors. Garment key "hang": true / false (None: HANG_FIELD).
# Known answers: tests/test_pattern_form.py test_hang_sheet_falls_plumb, test_hang_sleeve_tube.
HANG_FIELD = False
# CANVAS / INTERFACING STIFFNESS (canvas thread, 2026-10-23; bending.py): the fit's bending (FIT_BEND, Bergou) weighed
# every vertex alike; FIT_BEND_KEYED adds the interfaced cloth's extra stiffness (bending.weights - 1: canvas 19, fusible
# 7) as edge hinges with a flat rest, x FIT_HINGE_W x FIT_BEND (plain cloth's term unchanged). Garment key "bend_keyed": true / false (None: the flag).
# The mesh carries the weights as M["bend_w"] for the styling (garment_pull.STYLE_BEND).
FIT_BEND_KEYED = __import__("os").environ.get("PF_BEND_KEYED", "0") == "1"
FIT_HINGE_W = float(__import__("os").environ.get("PF_HINGE_W", "1.0"))  # x FIT_BEND per unit weight over plain
# STIFFNESS NEVER BUYS SHAPE WITH STRETCH (canvas s2, Joe 2026-10-23: "it shouldn't really be a choice between
# stiffness and stretch"): woven cloth barely stretches along its threads, canvassed or not; stiffness changes how it
# BENDS. In a weighted sum (ARAP + hinges) a stiff piece asked for a shape it can't reach bought it with thread strain
# (session 1: keyed fit threads p99 7.2 -> 8.4 %, the jacket styled 7.4 -> 9.6 %). The hierarchy: every round the
# interfaced triangles' warp / weft are projected back within FIT_THREAD_CAP (_thread_limit: the bias still shears),
# then contact; the hinges act only inside what the threads allow. Env PF_THREAD_FIRST=0 for the A/B.
FIT_THREAD_FIRST = __import__("os").environ.get("PF_THREAD_FIRST", "1") == "1"
FIT_THREAD_CAP = float(__import__("os").environ.get("PF_THREAD_CAP", "0.02"))  # (the muslin's ~1-2 %)
FIT_THREAD_SWEEPS = 4
HANG_G = 0.1  # the weight per vertex x mean pattern edge^2 (as SETTLE_G)
HANG_ITERS = 600  # (the towel KAT: 150 rounds left it half way, 26 mm; 600: 9-10 mm, hems +3 / +0.4)
HANG_STRAIN = 0.01  # the most the weight stretches a thread (warp / weft): the muslin's "until it would stretch"
HANG_SUPPORT = True


def hang_for(g: dict | None) -> bool:
    """Whether garment g is fitted with the hang (garment key "hang", else HANG_FIELD)."""
    own = (g or {}).get("hang")
    return HANG_FIELD if own is None else bool(own)


def _thread_limit(W: dict, X: np.ndarray, cap: float, sweeps: int = 4) -> np.ndarray:
    """Jacobi strain limit in the THREAD frame: every FIT triangle whose warp or weft is longer than 1 + cap is mapped
    back to it, or shorter than 1 - cap (its deformation gradient's thread columns scaled, about its centroid); vertices take the mean of their
    triangles' corrections. Shear is untouched (the bias shears freely, as the woven fit)."""
    Ft, q = W["F"], W["q"]
    X = X.copy()
    for _ in range(sweeps):
        Fg = _woven_grad(W, X)[0]
        ln = np.linalg.norm(Fg, axis=1)  # (t, 2)
        sc = np.clip(ln, 1.0 - cap, 1.0 + cap) / np.maximum(ln, 1e-12)  # (nor shorter: a woven buckles, it does not shrink)
        bad = (np.abs(sc - 1.0) > 1e-9).any(1)
        if not bad.any():
            break
        Fb = Fg[bad] * sc[bad][:, None, :]
        qb, fb = q[bad], Ft[bad]
        qc = qb.mean(1)
        xc = X[fb].mean(1)
        tgt = xc[:, None, :] + np.einsum("bij,bcj->bci", Fb, qb - qc[:, None, :])
        cor = np.zeros_like(X)
        cnt = np.zeros(len(X))
        for c in range(3):
            np.add.at(cor, fb[:, c], tgt[:, c] - X[fb[:, c]])
            np.add.at(cnt, fb[:, c], 1.0)
        X += cor / np.maximum(cnt, 1.0)[:, None]
    return X


# TRACE (dress-garrett 2026-10-19 form sleeves): a callable (phase, X, M) called after each assembly phase (placement,
# relax1, swing, band_init, turn_flaps, seat, let_go): bisect where a shape fault appears. None = off.
TRACE = None
# THE FIT RELAX (2026-10-19 virtual fit; Joe: "We shouldn't need a sim to drape it. We should be able to build a 'fit'").
# The old relax was as-rigid-as-possible with one rigid cell per vertex fitted to the FLAT pattern one-ring: (a) a cell
# prefers its ring flat, so every panel prefers to lie flat, and (b) the two sides of a seam are different cells, so a
# crease AT a seam costs nothing. A sleeve of two panels (upper + under) went to a lens with creases at its seams (KAT
# tests/test_pattern_form.py test_two_panel_sleeve_on_real_arm: aspect 0.98 -> 0.57 at 480 iterations, a one-piece
# tube to a teardrop 1.59, attraction off or on; Garrett's jacket sleeve 142 x 156 -> 72 x 159 mm). FIT = True replaces
# it, for every cell that isn't a fold / made piece, by what fashion and game cloth tools solve for a quick fit
# (ShapeOp / projective dynamics, Bouaziz et al. 2014; Marvelous Designer's arrangement + settle):
#   - ISOMETRY: each pattern edge keeps its length (local step: the edge's current direction at its pattern length), no
#     preferred rotation, so no preferred flatness;
#   - BENDING on the SEWN surface (seams welded): Bergou et al. 2006's quadratic bending for isometric surfaces,
#     |cot Laplacian (pattern) x|^2 / area at interior vertices. Measured across seams, a crease costs what a crease
#     anywhere costs; with the lengths kept, a closed tube's least bending is round (Euler's elastica: the circle).
#     FIT_BEND_REST "flat" (cloth's own rest) or "smooth" (its rest is the current curvature smoothed over its one-ring
#     x FIT_SMOOTH passes: only unevenness costs, not curvature);
#   - folds, turned flaps, pressed seams and made pieces (bands / collars) keep their ARAP cells and folded rests.
# Collision with the offset body / the garment under is unchanged; SEAT_GRAVITY / PRESS_UNDER stay optional.
FIT = True
FIT_BEND = 1.0  # bending weight (x h^2 of the mesh: the edge terms' scale)
FIT_BEND_REST = "flat"
FIT_SMOOTH = 2
FIT_STIFF = 12.0  # an isometry edge's weight (x an ARAP cell edge's): the lengths hold against the obstacles' pushes
# WOVEN (fit round 14, opt-in): a woven cloth barely stretches along its warp / weft but SHEARS easily (on the bias).
# FIT's isometry holds all three edges of every triangle: shear-stiff, so a front held at the chest could open its break
# only by stretching or tearing (Garrett r12d: p99 74 %). WOVEN replaces the FIT edges' targets (not the cells: folds,
# flaps, made pieces stay ARAP) by per-triangle targets from the deformation gradient in the piece's GRAIN frame
# (u = weft, v = warp; piece["grain"] deg, 90 = warp along the pattern's y): F = [f_u f_v] (3 x 2). The local step
# projects F onto two sets (projective dynamics): P_s = [f_u/|f_u|, f_v/|f_v|] (warp and weft at their length, ANY angle:
# stretch-free, sheared) at weight 1 and P_r = the nearest rotation (no shear either) at weight SHEAR_STIFF; the target
# is (P_s + SHEAR_STIFF P_r) / (1 + SHEAR_STIFF). Global step unchanged (the same sparse system: the edge rows, each
# edge's target the mean of its triangles' T e). Bending unchanged (Bergou).
# SHEAR_STIFF from KES-F (Kawabata) for suiting: shear rigidity G 0.6-0.9 gf/cm/deg (KES-FB1, suiting typical; a plain
# weave suiting sheet G 0.64-0.70), tensile EMT 6.1-6.7 % at Fm 500 gf/cm (WT 9.7-10.7, LT 0.65-0.67): secant tensile
# stiffness E = Fm / EMT ~ 7800 gf/cm per unit strain, G = 0.75 x 57.3 = 43 gf/cm per rad: G / E = 0.0055. Energy per
# area: E eps^2 / 2 (stretch) vs G gamma^2 / 2 (shear); the projections cost (1 + s) eps^2 and s gamma^2 / 2 (small
# strain), so s / (1 + s) = 2 G / E.
# THE MUSLIN FIT IS THE FIT (Joe 2026-10-22, C161 / C162: "shouldn't this always be the measuring process, always?"):
# WOVEN on, the neck pin soft (NECK_PIN_W), threads never squashed (WOVEN_SLACK off). A pattern that can't reach shows
# as thread strain / open seams in the one fit everyone looks at, not as stretch hidden by an isometric fit. Garments
# fitted and approved on the old fit are HELD on it ("isometric": WOVEN off, neck pin 200) until refitted: garment key
# fit_model, or garment_kb fit_holds by "model:garment" (fit_model_for).
WOVEN = True
KES_G = 0.75  # gf/cm/deg: shear rigidity of a suiting wool (KES-FB1 G, 0.6-0.9)
KES_EMT = 0.064  # strain at KES_FM (KES-FB1 EMT, 6.1-6.7 %)
KES_FM = 500.0  # gf/cm: KES-FB1's maximum tensile load for wovens
_r = 2.0 * KES_G * 180.0 / math.pi / (KES_FM / KES_EMT)
SHEAR_STIFF = _r / (1.0 - _r)  # ~0.011 (see WOVEN)
WOVEN_SLACK = False  # A/B only: warp / weft free in compression (a woven buckles rather than shortens; |f| < 1 kept)
# SHEAR WHERE NOTHING DRIVES IT (muslin default, C166): WOVEN's shear weight (SHEAR_STIFF ~0.011, the KES G / E ratio)
# is the cloth's shear rigidity UNDER LOAD; a woven also has shear hysteresis (KES 2HG, ~1-3 gf/cm for shirting and
# suiting, of the order of G x 2-4 deg): a force under it does not shear the cloth at all. With only 0.011 holding it, a
# FREE sheet (no body, pin or layer touching it) kept the shear the fold's transient put in (a diagonal fold 13 deg,
# a run-off fold 28 deg turned past it). Triangles with no driven vertex (touching the form: within FREE_REACH of its
# offset; a pin; the garment under or over; a flap's base) take SHEAR_FREE instead. The body ATTRACTION is not an
# obstacle (a stand-in for the drape): it drove loose ease to shear onto the body (cloth hanging under a seat cupped in): a loose sheet stays square; where the form
# acts the cloth shears as before (the misfit the muslin reveals stays: Garrett's yoke corner, notes "muslin default").
# A turned flap's cells (WOVEN_FLAPS) are woven only where driven too: free, they stay ARAP (its pattern shape).
SHEAR_FREE = 1.0
# SHEAR_YIELD (opt-in A/B, C168): the hysteresis holds a free cell's shear only while its threads are at length (KES
# 2HG / E ~ 0.02-0.04 % of thread strain): a free cell whose threads strain past this yields to the driven weight. At
# 0.001 the wf_simon collar's free right tip compresses -3.4 % (warp p5) instead of -4.4 and styles clean (0.109 vs
# closed 0.091 + 0.05), but every free cell shears more (shear p99 13.9 -> 19.0): the points open 156 apart (concept
# ~147, <= 154), the run-off fold folds past its run-off, the break step reads 2.6 mm, open-collar reads fail (5 reds,
# /mnt/data/hifipushie/muslin_default/pfy.log). None: off (needs its own round).
SHEAR_YIELD = float(os.environ["PF_SHEAR_YIELD"]) if os.environ.get("PF_SHEAR_YIELD") else None
SHEAR_LOCK_DEG = 35.0  # a woven's shear jamming angle (shirting / suiting ~30-40 deg): past it the cloth can't shear
# SHEAR_RAMP (C166): the local / global step takes a shear back by only s / (1 + s) a round (1.1 % at SHEAR_STIFF), so
# a transient's shear (a collar stood up, a placement on a cone) outlived the rounds: the shoulder-collar KAT's
# developable bodice read shear p99 31.8 deg at 120 rounds, 4.0 at 480. Driven shear builds in a few rounds (P_s
# keeps any angle), undriven shear decays at the weight: so each relax starts at SHEAR_FREE and eases (geometrically)
# to SHEAR_STIFF over its first SHEAR_RAMP of rounds; the rest are the muslin's own.
SHEAR_RAMP = float(os.environ.get("PF_SHEAR_RAMP", 0.5))
FREE_REACH = float(os.environ.get("PF_FREE_REACH", 0.003))  # m: in contact = within this of the form's offset
WOVEN_FLAPS = True  # WOVEN on a turned flap's own triangles too (a lapel is the same cloth; its fold rows stay ARAP)
# FORM VALIDATED (2026-10-19 virtual fit): True once frozen_ae's pattern assembled on the form matches the simulated
# drape of the same pattern (waist / hem / sleeve girth +-3 %, sleeve aspect +-15 %, shoulder, length, collar stand;
# tests/test_form_validation.py, record /mnt/data/hifipushie/pattern_form/validation.json). The pattern gate reads its
# form items as INFO until this is True.
VALIDATED = False  # validation 2 (2026-10-19, vs frozen_ae's RAW SIM V_sim, 16 rows): 12 pass; failing shoulder +3.2 %
# (cap stands out, no weight), front opening chest -10.5 / hips -19.5 mm, back standoff +26 mm at the small of the back.
# (The finished drape res["V"] is hand work: closure-step mirror + sculpt, face strain p99 74 % vs the sim's 9.4 %.)
# Set True only from a record whose "validated" is true.
VALIDATION_RECORD = "/mnt/data/hifipushie/pattern_form/validation.json"


def form_validated(path: str = VALIDATION_RECORD) -> bool:
    """VALIDATED, checked against the recorded validation (form vs the drape of the same pattern): True only when the
    flag is set AND the record says every row passes; a missing record reads False."""
    import json as _json
    import os as _os
    if not VALIDATED or not _os.path.exists(path):
        return False
    with open(path) as fh:
        return bool(_json.load(fh).get("validated"))


# ------------------------------------------------------------------ mesher sizing (cloth.mesh, garment key mesh_refine)

def sizing(B: dict, h: float):
    """hz(piece, Q (n, 2)) -> local triangle size (n,) from B["mesh_refine"]: a list of
    {"piece": name | [names], "h": m, "near": [point | mark | [x, y], ...] (a polyline; absent = the whole piece),
     "within": m (full refinement inside, default 0.02), "blend": m (back to h over this, default 3 h)}."""
    from .cloth import _seg_dist
    pcs = B["pieces"]
    ents = []
    for e in B.get("mesh_refine") or []:
        nms = [e["piece"]] if isinstance(e["piece"], str) else list(e["piece"])
        for nm in nms:
            if nm not in pcs:
                continue
            L = None
            if e.get("near"):
                pts = []
                for q in e["near"]:
                    if isinstance(q, str):
                        if q in pcs[nm]["names"]:
                            pts.append(pcs[nm]["P"][pcs[nm]["names"][q]])
                        elif q in (pcs[nm].get("marks") or {}):
                            pts.append(np.asarray(pcs[nm]["marks"][q], float))
                    else:
                        pts.append(np.asarray(q, float))
                if not pts:
                    continue
                L = np.asarray(pts, float)
                if len(L) == 1:
                    L = np.r_[L, L + 1e-9]
            ents.append((nm, float(e["h"]), L, float(e.get("within", 0.02)), float(e.get("blend", 3 * h))))

    def hz(nm, Q):
        Q = np.atleast_2d(np.asarray(Q, float))
        out = np.full(len(Q), float(h))
        for nm_, hf, L, w, bl in ents:
            if nm_ != nm or not len(Q):
                continue
            d = np.zeros(len(Q)) if L is None else _seg_dist(Q, L, closed=False)
            out = np.minimum(out, hf + (h - hf) * np.clip((d - w) / max(bl, 1e-9), 0, 1))
        return out
    return hz


def _hex(lo, hi, h):
    dy = h * math.sqrt(3) / 2
    rows = []
    for r, y in enumerate(np.arange(lo[1] + dy / 2, hi[1], dy)):
        xs = np.arange(lo[0] + (h / 2 if r % 2 else 0), hi[0], h)
        rows.append(np.c_[xs, np.full(len(xs), y)])
    return np.concatenate(rows) if rows else np.zeros((0, 2))


def graded_lattice(ring: np.ndarray, h: float, size, Q0: np.ndarray) -> np.ndarray:
    """Interior points: the piece's own h lattice (Q0) where the size is h, finer hex lattices (h/2, h/4 ...) where the
    size asks for them (each point kept by the level nearest its local size)."""
    lo, hi = ring.min(0), ring.max(0)
    g = _hex(lo, hi, h / 4)
    hmin = float(size(g).min()) if len(g) else h
    K = max(0, int(math.ceil(math.log2(h / max(hmin, 1e-4)) - 0.25)))

    def level(Q):
        return np.clip(np.round(np.log2(h / np.maximum(size(Q), 1e-6))), 0, K).astype(int)
    out = [Q0[level(Q0) == 0]] if len(Q0) else []
    for k in range(1, K + 1):
        Qk = _hex(lo, hi, h / 2 ** k)
        if len(Qk):
            out.append(Qk[level(Qk) == k])
    return np.concatenate(out) if out else np.zeros((0, 2))


def row_h(pcs: dict, f: dict, h: float, hz) -> float:
    """A fold's row spacing: the finest local size along its line (h without refinement)."""
    if hz is None:
        return h
    from . import pattern
    L = pattern.fold_line(pcs, f)
    return float(min(h, hz(f["piece"], L).min()))


# ------------------------------------------------------------------ geometry helpers

def _edges(F):
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    return np.unique(np.sort(E, 1), axis=0)


def _vnormals(V, F):
    n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], n)
    return N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)


def _rodrigues(p, u, th):
    """Rotate vectors p (n, 3) about unit axes u (n, 3) by angles th (n,)."""
    c, s = np.cos(th)[:, None], np.sin(th)[:, None]
    return p * c + np.cross(u, p) * s + u * np.sum(u * p, 1, keepdims=True) * (1 - c)


class _Surface:
    """An obstacle the garment lies outside of: vertices, outward vertex normals (signed distance = (x - q) . n_q)."""

    def __init__(self, V, F, ref=None):
        self.V = np.asarray(V, float)
        F = np.asarray(F)
        N = _vnormals(self.V, F)
        if ref is not None:  # orient by the body: outward = away from it
            d, i = ref.tree.query(self.V)
            s = np.sign(np.sum((self.V - ref.V[i]) * N, 1) + 1e-12)
            N = N * s[:, None]
        else:
            c = self.V.mean(0)
            if np.mean(np.sum((self.V - c) * N, 1)) < 0:
                N = -N
        self.N = N
        self.tree = cKDTree(self.V)

    def signed(self, X):
        d, i = self.tree.query(X)
        return np.sum((X - self.V[i]) * self.N[i], 1), self.N[i], d


def padded_body(body, pad: dict | None):
    """The body with a SHOULDER PAD on each shoulder (garment key "shoulder_pad": {"thickness" m, "reach" m, "toward_neck"
    fraction}; fit round 1, 2026-10-19). A tailored jacket's pad is a layer between the body and the jacket: it squares
    and lifts the shoulder line and carries the sleeve head. Modelled as the form's own surface pushed out along its
    normal by a smooth dome, `thickness` at its centre (on the shoulder line, `toward_neck` of the way from the shoulder
    point to the neck point), fading to 0 at `reach`, on the upper side only (normal z > -0.3: the pad lies on the top of
    the shoulder and down the top of the arm). Returns body unchanged without a pad or landmarks."""
    import types as _types
    at = getattr(body, "at", None) or {}
    if not pad or "shoulder.L" not in at or "hps.L" not in at:
        return body
    from .cloth_made import outward
    V = np.asarray(body.V, float)
    T = np.asarray(body.T)
    N = _vnormals(V, outward(V, T))
    t, R, f = float(pad.get("thickness", 0.010)), float(pad.get("reach", 0.075)), float(pad.get("toward_neck", 0.3))
    lift = np.zeros(len(V))
    for sx in (1.0, -1.0):
        sp, hp = np.asarray(at["shoulder.L"], float) * [sx, 1, 1], np.asarray(at["hps.L"], float) * [sx, 1, 1]
        c = sp + f * (hp - sp)
        r = np.linalg.norm(V - c, axis=1) / R
        lift = np.maximum(lift, t * np.clip(1 - r ** 2, 0, None) ** 2)
    lift *= np.clip((N[:, 2] + 0.3) / 0.6, 0.0, 1.0)
    return _types.SimpleNamespace(V=V + N * lift[:, None], T=T, at=at, pad_lift_max_mm=float(lift.max() * 1000))


def _body_surface(body):
    from .cloth_made import outward
    V = np.asarray(body.V, float)
    return _Surface(V, outward(V, np.asarray(body.T)))


# BRIDGE (fit round 23, 2026-10-20; Joe on r22: "that jacket looks really tight around his middle, that's not how jackets
# work"). A hung outer garment of stiff cloth BRIDGES the body's concavities: it hangs from the convex points (chest,
# shoulder blades, seat) and runs straight across the hollows (small of the back, waist sides) and plumb below the seat,
# within its own ease. The form drew every vertex onto an offset of the BODY, so the jacket followed the hollows: Garrett
# r22a / r22b, side seam 31-46 mm and back (45 deg) 24-31 mm INSIDE the column's straight edge at the waist while 9-30 mm
# off the body (fit_round23/columns.py). The seat attraction's target is now the body's offset with its concavities
# filled along the hanging direction, by `bridge` of the way: per azimuth column round the torso (BRIDGE_AZ bins x
# BRIDGE_DZ), the column's upper concave hull in z (a straight edge laid from convex point to convex point) and plumb
# below its lowest support (the seat), between the garment's hem and the armpit. Only the attraction: the body stays the
# hard obstacle and nothing pushes the cloth out past what its lengths allow (the ease decides how far it bridges).
# `bridge` from the fabric's bending length (Peirce cantilever, the KB's bending_length_mm): 0 at or below
# BRIDGE_SOFT_MM (the KB's "soft" drape level, cloth_reference.m_drape_level: shirting 10-14 mm follows the body), 1 at
# BRIDGE_CRISP_MM ("crisp": a coating, a canvassed front), linear between (wool suiting 14-18: 0.67). KAT:
# tests/test_pattern_form.py test_bridge_hourglass_tube.
BRIDGE = False  # OPT-IN (fit round 23: r23c vs r22a blind side A/B chose OLD: the seat swelled 413 -> 433 wide, the hem still curls)
BRIDGE_SOFT_MM = 12.0
BRIDGE_CRISP_MM = 18.0
BRIDGE_AZ = 72
BRIDGE_DZ = 0.01
BRIDGE_HANG = True  # (fit round 23 lever 2): on the torso band the pull-in onto the filled surface x (1 - bridge) (r23b vs r23a: waist width 305 -> 319, girth +99 -> +104 of the draft +110)
BRIDGE_SOURCE = ("a hung outer garment bridges the body's hollows (tailoring: a coat hangs from the shoulders, chest, "
                 "blades and seat; its stiffness, the fabric's bending length (Peirce 1930, BS 3356 cantilever), decides "
                 "how far it spans); drape levels from the KB (soft < 12 mm, crisp > 18 mm bending length)")


def bridge_fraction(g: dict | None) -> float:
    """How far a garment's cloth bridges the body's hollows on the form (0 follows, 1 the full straight edge): from its
    KB fabric's bending length (BRIDGE_SOFT_MM .. BRIDGE_CRISP_MM). 0 without fabric data."""
    if not g or not BRIDGE:
        return 0.0
    try:
        from . import cloth, cloth_reference
        fab = cloth.fabric(g)
        e = cloth_reference._fabric_entry(fab.get("kb") or fab.get("name"))
        b = float(np.mean(e["bending_length_mm"]))
    except Exception:
        return 0.0
    return float(np.clip((b - BRIDGE_SOFT_MM) / (BRIDGE_CRISP_MM - BRIDGE_SOFT_MM), 0.0, 1.0))


class _Bridged:
    """The body's torso with its hollows filled along z (BRIDGE): signed(X) -> (d, n) of the filled surface, d = +inf off
    the torso band [z_lo, z_hi]. Polar grid round the vertical axis through c."""

    def __init__(self, V, frac, z_lo, z_hi, torso_x, c=None):
        V = np.asarray(V, float)
        m = (V[:, 2] > z_lo - 0.05) & (V[:, 2] < z_hi + 0.01) & (np.abs(V[:, 0]) < torso_x)
        P = V[m]
        if c is None:
            zm = 0.5 * (z_lo + z_hi)
            s = P[np.abs(P[:, 2] - zm) < 0.02]
            c = 0.5 * (s[:, :2].min(0) + s[:, :2].max(0)) if len(s) else P[:, :2].mean(0)
        self.c = np.asarray(c, float)
        self.z_lo, self.z_hi = float(z_lo), float(z_hi)
        self.zg = np.arange(z_lo - 0.03, z_hi + 0.0001, BRIDGE_DZ)
        na, nz = BRIDGE_AZ, len(self.zg)
        d = P[:, :2] - self.c
        r = np.linalg.norm(d, axis=1)
        ia = (np.floor((np.arctan2(d[:, 1], d[:, 0]) + np.pi) / (2 * np.pi) * na).astype(int)) % na
        iz = np.clip(np.round((P[:, 2] - self.zg[0]) / BRIDGE_DZ).astype(int), -1, nz)
        ok = (iz >= 0) & (iz < nz)
        R = np.full((na, nz), -1.0)
        np.maximum.at(R, (ia[ok], iz[ok]), r[ok])
        for a in range(na):  # empty bins: interpolated along z
            k = R[a] > 0
            if k.sum() >= 2:
                R[a] = np.interp(self.zg, self.zg[k], R[a, k])
        for j in range(nz):  # columns with nothing: from the azimuth neighbours (periodic)
            k = R[:, j] > 0
            if 2 <= k.sum() < na:
                ax = np.arange(na)
                R[:, j] = np.interp(ax, ax[k], R[k, j], period=na)
        E = R.copy()
        for a in range(na):
            E[a] = self._hull(self.zg, R[a])
        self.R, self.E = R, R + float(frac) * (E - R)
        self.dEdz = np.gradient(self.E, BRIDGE_DZ, axis=1)
        self.frac = float(frac)

    @staticmethod
    def _hull(z, r):
        """upper concave hull of r(z), plumb below its lowest support (the hull vertex above the bottom end)."""
        H = []
        for p in zip(z, r):
            while len(H) >= 2 and ((H[-1][0] - H[-2][0]) * (p[1] - H[-2][1]) - (H[-1][1] - H[-2][1]) * (p[0] - H[-2][0])) >= 0:
                H.pop()
            H.append(p)
        hz, hr = np.array(H).T
        out = np.interp(z, hz, hr)
        if len(H) >= 2 and hr[1] >= hr[0]:  # plumb below the lowest support: the cloth hangs from it, not along a
            # line in to the hem (the hull's first vertex is the bottom end; the next one up is the support)
            out = np.where(z < hz[1], np.maximum(out, hr[1]), out)
        return np.maximum(out, r)

    def signed(self, X):
        X = np.asarray(X, float)
        d = X[:, :2] - self.c
        r = np.linalg.norm(d, axis=1)
        th = np.arctan2(d[:, 1], d[:, 0])
        fa = (th + np.pi) / (2 * np.pi) * BRIDGE_AZ - 0.5
        a0 = np.floor(fa).astype(int)
        wa = fa - a0
        fz = np.clip((X[:, 2] - self.zg[0]) / BRIDGE_DZ, 0, len(self.zg) - 1.0001)
        z0 = np.floor(fz).astype(int)
        wz = fz - z0
        a0m, a1m = a0 % BRIDGE_AZ, (a0 + 1) % BRIDGE_AZ

        def bil(G):
            return ((1 - wa) * ((1 - wz) * G[a0m, z0] + wz * G[a0m, z0 + 1]) +
                    wa * ((1 - wz) * G[a1m, z0] + wz * G[a1m, z0 + 1]))

        e, g = bil(self.E), bil(self.dEdz)
        er = np.c_[d / np.maximum(r, 1e-9)[:, None], np.zeros(len(X))]
        n = er - g[:, None] * np.array([0.0, 0.0, 1.0])
        ln = np.linalg.norm(n, axis=1)
        n /= ln[:, None]
        out = (r - e) / ln
        band = (X[:, 2] >= self.z_lo) & (X[:, 2] <= self.z_hi) & (r > 1e-3)
        return np.where(band, out, np.inf), n


def bridged_surface(body, frac: float, z_lo: float):
    """_Bridged for a body (cloth.Body with at["armpit_z"], at["shoulder.L"]) from z_lo (the garment's hem) to the
    armpit; None when frac is 0 or the landmarks are missing."""
    at = getattr(body, "at", None) or {}
    if frac <= 0 or "armpit_z" not in at:
        return None
    zh = float(np.asarray(at["armpit_z"]).reshape(-1)[-1])
    tx = abs(float(np.asarray(at["shoulder.L"]).reshape(-1)[0])) if "shoulder.L" in at else 0.2
    if zh <= z_lo + 0.05:
        return None
    return _Bridged(np.asarray(body.V, float), frac, z_lo, zh, tx)


# ------------------------------------------------------------------ fold rests

def _fold_cells(M: dict, face_sign: dict):
    """Per fold row vertex: the flap-side neighbours' rest edges rotated about the row (the flat pattern folded at the
    line). Returns ({(i, j): angle}, axis per row vertex, flap vertex set per fold)."""
    from . import folds as foldmod
    uv = np.asarray(M["uv"], float)
    out = []
    for fd in M.get("folds") or []:
        turn = float(fd.get("turn", 0.0))
        if abs(turn) < 1e-3 or not len(fd["rows"]) or len(fd["rows"][0]) < 2:
            continue
        g = foldmod._geom(M, fd)
        # the flap's side of the row ("sign", folds.fold_rows: +1 left of the line's direction) sets which way a
        # rotation about the row's tangent turns it: a mirrored piece (".R") has its flap on the other side, so the same
        # "over" is the opposite rotation (dress-garrett 2026-10-19: left out, the R lapel's rest turned it INTO the
        # body; it read 148 deg vs the L's 167, its roll row 11% long and its edge sawtoothed)
        out.append((fd, g, turn * face_sign.get(fd["piece"], 1.0) * float(fd.get("sign", 1.0))))
    return out


def _fold_fade(M, fd, idx):
    from . import folds as _fm
    return _fm.fade(M, fd, idx)


def _rest_edges(M, src, dst, folds_):
    """Directed rest edge vectors (3D, the pattern plane z = 0) for cell src: e = uv[dst] - uv[src], folded where the
    cell is a fold row vertex and dst lies on the flap side of that row."""
    uv = np.asarray(M["uv"], float)
    e = np.c_[uv[dst] - uv[src], np.zeros(len(src))]
    for fd, g, turn in folds_:
        for r, rg in enumerate(g["rows"]):
            row = np.asarray(rg["row"])
            if len(row) < 2:
                continue
            onrow = np.zeros(len(uv), bool)
            onrow[row] = True
            flap = np.zeros(len(uv), bool)
            flap[rg["v"]] = True
            # only a cell ON the row spans both sides (the hinge runs through it): its flap-side neighbours turn by
            # the row's share. A cell beside the row has the row's vertices on the axis: rigid, its rest stays flat
            sel = onrow[src] & flap[dst]
            for s_, sg in ((sel, 1.0),):
                if not s_.any():
                    continue
                # local row tangent at the cell (the row polyline's nearest segment)
                L = uv[row]
                P = uv[src[s_]]
                ab = L[1:] - L[:-1]
                ln2 = np.maximum((ab ** 2).sum(1), 1e-18)
                t = np.clip(((P[:, None] - L[None, :-1]) * ab[None]).sum(-1) / ln2[None], 0, 1)
                d = np.linalg.norm(P[:, None] - (L[None, :-1] + t[..., None] * ab[None]), axis=-1)
                j = np.argmin(d, 1)
                tan = ab[j] / np.sqrt(ln2[j])[:, None]
                u = np.c_[tan, np.zeros(len(tan))]
                e[s_] = _rodrigues(e[s_], u, np.full(int(s_.sum()), sg * turn) * _fold_fade(M, fd, src[s_]))
    return e


PRESSED_REACH = 0.012  # m (pattern): the seam pairs a pressed seam's local 2D map is fitted over

PRESSED_W = 1.0  # a pressed seam's cross cells vs a cell's own edges

# FIT ROUND 5 (2026-10-19, C48): a piece with NO fold of its own sewn to a flap rides with it. The two-piece collar's
# STAND is sewn to the neckline, and beyond the lapel's roll line that neckline is the lapel's gorge (turned). The rule
# read only flap <-> flap seams, so with a stand between the gorge and the fall nothing was pressed (pressed_cells 0):
# the stand's front end stood up in its wrap BEHIND the turned lapel, the collar's end lay under the front (front view:
# no collar below the shoulder line; notch step L open 0.3 / depth 0). Tailoring: the collar's roll line runs into the
# lapel's at the gorge; beyond it the collar's end (stand and fall) lies on the lapel, the gorge seam pressed open
# (Cabrera & Flaherty, Classic Tailoring Techniques; Aldrich, split undercollar). A pair is pressed when one side is a
# folded piece's flap vertex and the other a flap or an UNFOLDED piece's vertex; two unfolded pieces (stand <-> back
# neck) never are, nor a flap <-> the base side of anything.
PRESS_UNFOLDED = True


def _press_flags(M, folds_, rows_ride: bool = False):
    """({piece index: pressable per vertex}, {folded piece indices}). A folded piece: its flap vertices (rows' v; the
    hinge row itself only if rows_ride); an unfolded piece (PRESS_UNFOLDED): every vertex (it rides with the flap it
    is sewn to)."""
    uv = np.asarray(M["uv"], float)
    pid = np.asarray(M["piece"])
    flap = {}
    for fd, g, turn in folds_:
        k = list(M["names"]).index(fd["piece"])
        s_ = flap.setdefault(k, np.zeros(len(uv), bool))
        for r_ in g["rows"]:
            s_[np.asarray(r_["v"], int)] = True
        if not rows_ride:
            for r_ in g["rows"]:
                s_[np.asarray(r_["row"], int)] = False  # (a row vertex is the hinge itself: its cell already turns)
    folded = set(flap)
    if PRESS_UNFOLDED and folded:
        for k in set(np.unique(pid).tolist()) - folded:
            flap[int(k)] = pid == k
    return flap, folded


def _pressed_pair(pid, flap, folded, a, b) -> bool:
    """A sewn pair is pressed: different pieces, both pressable, at least one of them a FOLDED piece's flap vertex."""
    return bool(pid[a] != pid[b] and pid[a] in flap and pid[b] in flap and flap[pid[a]][a] and flap[pid[b]][b]
                and (pid[a] in folded or pid[b] in folded))


def _pressed_cells(M, folds_, E):
    """A seam joining two FLAPS (each sewn vertex on the turned side of a fold in its own piece: a notched collar's
    end sewn to the lapel's gorge) is pressed flat: the two pieces lie as one surface across it, each on its own side.
    Without it a seam is a free hinge and a flap sewn to a flap can lie anywhere round it (dress-garrett 2026-10-19
    "notch and open neck": the jacket collar's end stood up the front of the neck like a funnel, the notch gap 62 mm
    / angle 162 deg on the form where the flat draft carried into the front reads 29 / 62).
    Returns cross-seam cells (src, dst, rest): each sewn vertex gets its partner's one-ring as extra rest edges, the
    partner's pattern carried into its own by a local 2D map fitted over the seam's pairs within PRESSED_REACH, the
    proper or mirrored one that puts the partner's piece on the far side of the seam."""
    uv = np.asarray(M["uv"], float)
    pid = np.asarray(M["piece"])
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    if not len(sw) or not folds_:
        return np.zeros(0, int), np.zeros(0, int), np.zeros((0, 3))
    flap, folded = _press_flags(M, folds_)
    ok = np.array([_pressed_pair(pid, flap, folded, a, b) for a, b in sw], bool)
    P = sw[ok]
    if len(P) < 2:
        return np.zeros(0, int), np.zeros(0, int), np.zeros((0, 3))
    nb = [[] for _ in range(len(uv))]
    for i, j in E:
        nb[i].append(j)
        nb[j].append(i)
    out_s, out_d, out_r = [], [], []
    for a, b in P:
        near = P[(pid[P[:, 0]] == pid[a]) & (pid[P[:, 1]] == pid[b])
                 & (np.linalg.norm(uv[P[:, 0]] - uv[a], axis=1) < PRESSED_REACH)]
        if len(near) < 2:
            continue
        A_, B_ = uv[near[:, 0]], uv[near[:, 1]]
        ca, cb = A_.mean(0), B_.mean(0)
        U, _, Vt = np.linalg.svd((A_ - ca).T @ (B_ - cb))
        best = None
        for flip in (1.0, -1.0):
            Vt2 = Vt.copy()
            Vt2[-1] *= flip if np.linalg.det(U @ Vt) > 0 else -flip
            R = (U @ Vt2).T  # a-frame -> b-frame
            # the a-piece's one-ring carried over must lie on the far side of the seam from b's own
            ta = np.mean([uv[j] for j in nb[a] if pid[j] == pid[a]], axis=0) - uv[a]
            tb = np.mean([uv[j] for j in nb[b] if pid[j] == pid[b]], axis=0) - uv[b]
            tl = B_[-1] - B_[0]
            tl = tl / (np.linalg.norm(tl) + 1e-12)
            nrm = np.array([-tl[1], tl[0]])
            side = float((R @ ta) @ nrm) * float(tb @ nrm)
            res = float(np.linalg.norm(A_ @ R.T - (A_ @ R.T).mean(0) - (B_ - cb)))
            sc = (side < 0, -res)
            if best is None or sc > best[0]:
                best = (sc, R)
        R = best[1]
        for j in nb[b]:
            if pid[j] == pid[b]:
                out_s.append(a); out_d.append(j); out_r.append(R.T @ (uv[j] - uv[b]))
        for j in nb[a]:
            if pid[j] == pid[a]:
                out_s.append(b); out_d.append(j); out_r.append(R @ (uv[j] - uv[a]))
    if not out_s:
        return np.zeros(0, int), np.zeros(0, int), np.zeros((0, 3))
    r2 = np.asarray(out_r)
    return np.asarray(out_s, int), np.asarray(out_d, int), np.c_[r2, np.zeros(len(r2))]


def _lay_pressed(M, X, folds_, reach: float = 0.05):
    """The start for a pressed seam between two flaps: the SMALLER piece's flap vertices within `reach` (pattern) of
    the seam laid in the other's plane, carried across the seam (the collar's end on the turned lapel, as a tailor
    bastes it): one 2D map over all the seam's pairs (continuation side, as _pressed_cells), then the bigger piece's
    local uv -> 3D affine map (its flap vertices within `reach` of the seam). Without it the ARAP relax kept the end
    where the fall's turn had flung it (notch gap 58 of a drafted 29).
    PRESS_CARRIES_LAYERS: the layers already turned onto a carried piece go with it (see there)."""
    uv = np.asarray(M["uv"], float)
    X_in = np.asarray(X, float).copy()
    carried = set()
    pid = np.asarray(M["piece"])
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    flap, folded = _press_flags(M, folds_, rows_ride=True)
    pairs = {}
    for a, b in sw:
        if _pressed_pair(pid, flap, folded, a, b):
            # a on the piece carried: an unfolded piece (it rides with the flap), else the smaller one
            if (pid[a] in folded) != (pid[b] in folded):
                if pid[a] in folded:
                    a, b = b, a
            elif (pid == pid[a]).sum() > (pid == pid[b]).sum():
                a, b = b, a
            pairs.setdefault((int(pid[a]), int(pid[b])), []).append((a, b))
    X = X.copy()
    for (ka, kb), pr in pairs.items():
        pr = np.asarray(pr)
        if len(pr) < 3:
            continue
        A_, B_ = uv[pr[:, 0]], uv[pr[:, 1]]
        ca, cb = A_.mean(0), B_.mean(0)
        U, _, Vt = np.linalg.svd((A_ - ca).T @ (B_ - cb))
        va = np.where(pid == ka)[0]
        vb = np.where(pid == kb)[0]
        da = cKDTree(A_).query(uv[va])[0]
        db = cKDTree(B_).query(uv[vb])[0]
        mov = va[(da < reach) & flap[ka][va]]
        if ka not in folded:  # an unfolded piece rides only where its nearest seam vertex to kb is a pressed one
            s0 = sw[(pid[sw[:, 0]] == ka) & (pid[sw[:, 1]] == kb), 0]
            s1 = sw[(pid[sw[:, 1]] == ka) & (pid[sw[:, 0]] == kb), 1]
            sv = np.unique(np.r_[s0, s1])
            if len(sv) and len(mov):
                mov = mov[np.isin(sv[cKDTree(uv[sv]).query(uv[mov])[1]], pr[:, 0])]
        own = vb[(db < reach) & flap[kb][vb]]
        best = None
        for flip in (1.0, -1.0):
            Vt2 = Vt.copy()
            Vt2[-1] *= flip if np.linalg.det(U @ Vt) > 0 else -flip
            R = (U @ Vt2).T
            q = (uv[mov] - ca) @ R.T + cb
            # continuation: the carried piece lies away from the other's own vertices (not folded over them)
            sep = float(np.mean(cKDTree(uv[vb]).query(q)[0]))
            if best is None or sep > best[0]:
                best = (sep, q)
        q = best[1]
        Aff = np.linalg.lstsq(np.c_[uv[own], np.ones(len(own))], X[own], rcond=None)[0]
        X[mov] = np.c_[q, np.ones(len(q))] @ Aff
        if len(mov):
            carried.add((ka, kb))
    if PRESS_CARRIES_LAYERS and carried:
        X = _carry_layers(M, X_in, X, carried)
    return X


# PRESS CARRIES LAYERS (fit round 17, Joe's notch on r15e: the collar's end stood off the lapel like a square tab).
# _lay_pressed moved the stand's end 16-30 mm onto the turned lapel's plane, but the collar's FALL, already turned onto
# the stand by turn_flaps (fall-to-stand gap 4 mm), stayed where it was: the gap jumped to 12-20 mm and the relax only
# took it back to 7-8 (max 14-15): the fall's end a tab 30 deg out of the lapel's plane, the gorge seam twisting
# 30-50 deg / cm (gorge_lie). Two codes laid the two layers of one collar end in two planes. A tailor bastes the made
# collar's end (fall on stand) onto the lapel as one: every vertex of a piece sewn to a carried piece (and not itself
# the piece it is laid on) within LAYER_CARRY of the carried piece's start takes the move of its nearest carried-piece
# vertex (0 where that piece didn't move: the carry fades with the laid zone). And what the press laid lies ON the
# flap: the seat no longer draws it through the lapel onto the body (it had pulled the laid stand end back 25 mm).
# Off = round 16's behaviour.
PRESS_CARRIES_LAYERS = False  # opt-in: r17b pressed-phase fall-stand gap 20 -> 4 mm, final gorge_lie unchanged (tip 10 / 7.5)
LAYER_CARRY = 0.02  # m: a layer this close to the piece under it rides with it (fall on stand: 4-12 mm with ROLL_GAP)


def _carry_layers(M, X0, X1, carried):
    """X1 with the layers on each carried piece moved with it (PRESS_CARRIES_LAYERS). carried: {(piece laid, piece
    it was laid on)}; X0 the positions before the lay."""
    pid = np.asarray(M["piece"])
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    X = X1.copy()
    D = X1 - X0
    laid = {k for k, _ in carried}
    for ka in sorted(laid):  # once per laid piece (a stand laid on both lapels: its move D already holds both ends)
        on = set(pid[sw[pid[sw[:, 0]] == ka, 1]].tolist()) | set(pid[sw[pid[sw[:, 1]] == ka, 0]].tolist())
        on -= laid | {kb for k, kb in carried if k == ka}
        va = np.where(pid == ka)[0]
        tree = cKDTree(X0[va])
        for kl in on:
            vl = np.where(pid == kl)[0]
            dd, ii = tree.query(X0[vl])
            m = dd < LAYER_CARRY
            X[vl[m]] += D[va[ii[m]]]
    return X


def _fit_residual(src, rest, cur, n):
    """Sum over cells of the best rigid fit's squared residual (rest r = -e onto the current x_i - x_j)."""
    r = -rest
    Cm = np.zeros((n, 3, 3))
    np.add.at(Cm, src, r[:, :, None] * cur[:, None, :])
    U, _, Vt = np.linalg.svd(Cm)
    R = np.einsum("nji,nkj->nik", Vt, U)
    bad = np.linalg.det(R) < 0
    if bad.any():
        Vt2 = Vt[bad].copy()
        Vt2[:, 2] *= -1
        R[bad] = np.einsum("nji,nkj->nik", Vt2, U[bad])
    return float(np.sum((np.einsum("nij,nj->ni", R[src], r) - cur) ** 2))


def _fit_bending(M, F, uv, n, sw, skip, w=None):
    """The sewn surface's bending (FIT): returns (K (n, n) sparse, rhs(X) -> (n, 3) or None). Seams welded (sew pairs ->
    one vertex, averaged), cot Laplacian from the flat pattern (exact for isometric maps), lumped areas, rows kept at
    interior vertices not in `skip` (folds, made pieces). K = P^T L^T D L P (Bergou et al. 2006)."""
    from scipy.sparse import csr_matrix
    par = np.arange(n)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for a, b in sw:
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            par[max(ra, rb)] = min(ra, rb)
    root = np.array([find(i) for i in range(n)])
    _, wid = np.unique(root, return_inverse=True)
    nw = int(wid.max()) + 1
    cnt = np.bincount(wid, minlength=nw).astype(float)
    P = csr_matrix((1.0 / cnt[wid], (wid, np.arange(n))), shape=(nw, n))
    Fw = wid[F]
    U = np.c_[uv, np.zeros(len(uv))]
    I, J, Wt = [], [], []
    area = np.zeros(nw)
    for k in range(3):
        i, j, o = F[:, k], F[:, (k + 1) % 3], F[:, (k + 2) % 3]
        a_, b_ = U[i] - U[o], U[j] - U[o]
        cr_ = np.linalg.norm(np.cross(a_, b_), axis=1)
        cot = np.sum(a_ * b_, 1) / np.maximum(cr_, 1e-14)
        I += [Fw[:, k], Fw[:, (k + 1) % 3]]
        J += [Fw[:, (k + 1) % 3], Fw[:, k]]
        Wt += [0.5 * cot, 0.5 * cot]
        np.add.at(area, Fw[:, k], cr_ / 6.0)
    I, J, Wt = np.concatenate(I), np.concatenate(J), np.concatenate(Wt)
    Wm = coo_matrix((Wt, (I, J)), shape=(nw, nw)).tocsr()
    L = diags(np.asarray(Wm.sum(1)).ravel()) - Wm
    # boundary of the sewn surface: edges in one face only
    Ew = np.sort(np.r_[Fw[:, [0, 1]], Fw[:, [1, 2]], Fw[:, [2, 0]]], 1)
    ue, cnt_e = np.unique(Ew, axis=0, return_counts=True)
    keep = np.ones(nw, bool)
    keep[ue[cnt_e == 1].ravel()] = False
    sk = np.zeros(nw, bool)
    np.logical_or.at(sk, wid, skip)
    keep &= ~sk
    wv = np.ones(nw)
    if w is not None:  # (FIT_BEND_KEYED: bending.weights per vertex; a welded vertex takes its stiffest member's)
        wv = np.zeros(nw)
        np.maximum.at(wv, wid, np.asarray(w, float))
    D = diags(keep * wv / np.maximum(area, 1e-12))
    LP = (L @ P).tocsr()
    K = (LP.T @ D @ LP).tocsr()
    if FIT_BEND_REST != "smooth":
        return K, None
    A = (abs(Wm) > 0).astype(float) + diags(np.ones(nw))
    S = diags(1.0 / np.asarray(A.sum(1)).ravel()) @ A

    def rhs(X):
        d = LP @ X
        for _ in range(FIT_SMOOTH):
            d = S @ d
        return LP.T @ (D @ d)
    return K, rhs


# ------------------------------------------------------------------ the assembly


def _woven_setup(M: dict, B: dict | None, F: np.ndarray, E: np.ndarray, cellv: np.ndarray, skip=None):
    """WOVEN: the FIT triangles (no cell vertex), their grain-frame rest inverses, and each one's three undirected edges
    (index into E, sign: +1 when the triangle edge (a, b) is E's (a, b))."""
    uv = np.asarray(M["uv"], float)
    pid = np.asarray(M["piece"])
    names = list(M["names"])
    g_ = np.array([float(((B or {}).get("pieces", {}).get(nm) or {}).get("grain", 90.0)) for nm in names])
    t = np.where(~cellv[F].any(1))[0]
    Ft = F[t]
    Ft = Ft[np.isin(pid[Ft[:, 0]], np.asarray(list(range(len(names))) if skip is None else
                                              [k for k in range(len(names)) if k not in skip], int))]
    ga = np.radians(g_[pid[Ft[:, 0]]])
    warp = np.c_[np.cos(ga), np.sin(ga)]
    weft = np.c_[np.sin(ga), -np.cos(ga)]
    q = np.stack([np.stack([np.einsum("tk,tk->t", uv[Ft[:, c]], weft),
                            np.einsum("tk,tk->t", uv[Ft[:, c]], warp)], -1) for c in range(3)], 1)  # (t, 3, 2)
    Dm = np.stack([q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]], -1)  # (t, 2, 2) columns = edge vectors
    ok = np.abs(np.linalg.det(Dm)) > 1e-14
    Ft, q, Dm = Ft[ok], q[ok], Dm[ok]
    Dinv = np.linalg.inv(Dm)
    key = {(int(a), int(b)): i for i, (a, b) in enumerate(E)}
    te = np.zeros((len(Ft), 3), int)
    ts = np.zeros((len(Ft), 3))
    for c, (i, j) in enumerate(((0, 1), (1, 2), (2, 0))):
        for r_, (a, b) in enumerate(zip(Ft[:, i].tolist(), Ft[:, j].tolist())):
            te[r_, c], ts[r_, c] = (key[(a, b)], 1.0) if a < b else (key[(b, a)], -1.0)
    cnt = np.zeros(len(E))
    np.add.at(cnt, te.ravel(), 1.0)
    return {"F": Ft, "q": q, "Dinv": Dinv, "te": te, "ts": ts, "cnt": cnt}


def _woven_grad(W: dict, X: np.ndarray):
    Ft = W["F"]
    Ds = np.stack([X[Ft[:, 1]] - X[Ft[:, 0]], X[Ft[:, 2]] - X[Ft[:, 0]]], -1)  # (t, 3, 2)
    Fg = Ds @ W["Dinv"]  # columns f_u (weft), f_v (warp)
    Ps = Fg / np.maximum(np.linalg.norm(Fg, axis=1, keepdims=True), 1e-12)
    U, _, Vt = np.linalg.svd(Fg, full_matrices=False)
    return Fg, Ps, U @ Vt


def woven_targets(W: dict, X: np.ndarray, nE: int, shear: float | None = None):
    """WOVEN local step: per undirected edge of E (mean over its FIT triangles) the target of x_E0 - x_E1, and the mask
    of the edges that have one. (See WOVEN.)"""
    s = SHEAR_STIFF if shear is None else shear
    if np.ndim(s):  # (per FIT triangle: SHEAR_FREE where nothing drives the cloth)
        s = np.asarray(s, float)[:, None, None]
    Fg, Ps, Pr = _woven_grad(W, X)
    if WOVEN_SLACK:
        Ps = Ps * np.minimum(np.linalg.norm(Fg, axis=1, keepdims=True), 1.0)
    T = (Ps + s * Pr) / (1.0 + s)
    q = W["q"]
    tgt = np.zeros((nE, 3))
    for c, (i, j) in enumerate(((0, 1), (1, 2), (2, 0))):
        e = np.einsum("tij,tj->ti", T, q[:, i] - q[:, j])  # target of x_i - x_j
        np.add.at(tgt, W["te"][:, c], W["ts"][:, c, None] * e)
    has = W["cnt"] > 0
    tgt[has] /= W["cnt"][has, None]
    return tgt, has


def woven_energy(W: dict, X: np.ndarray, shear: float | None = None) -> dict:
    """The WOVEN energy of a configuration, integrated over rest area: stretch (distance^2 of F to warp / weft at their
    length) and shear (SHEAR_STIFF x distance^2 to the nearest rotation), as the local step weighs them."""
    s = SHEAR_STIFF if shear is None else shear
    Fg, Ps, Pr = _woven_grad(W, X)
    a = 0.5 / np.abs(np.linalg.det(W["Dinv"]))
    es = float(np.sum(a * ((Fg - Ps) ** 2).sum((1, 2))))
    eg = float(np.sum(a * s * ((Fg - Pr) ** 2).sum((1, 2))))
    return {"stretch": es, "shear": eg, "total": es + eg, "area": float(a.sum())}


def woven_shear_deg(W: dict, X: np.ndarray) -> np.ndarray:
    """Per FIT triangle: the warp / weft angle's departure from 90 deg (the bias shear the fit put in)."""
    Fg, _, _ = _woven_grad(W, X)
    c = np.einsum("ti,ti->t", Fg[:, :, 0], Fg[:, :, 1]) / np.maximum(
        np.linalg.norm(Fg[:, :, 0], axis=1) * np.linalg.norm(Fg[:, :, 1], axis=1), 1e-12)
    return np.degrees(np.arcsin(np.clip(np.abs(c), 0, 1)))


# THE NECK POINT SPLITS THE NECK AS THE GARMENT'S NECKLINE DOES (shirt round 4, C113). The neck pins put every piece
# point "hps" on the body's hps landmark (the widest point of the neck loop 2 cm up the neck, tailor "widest"). Where
# the garment's own neckline divides back : front differently from the body's loop at that landmark, the pin forces the
# shorter side to stretch: Garrett's shirt (Simon) has a back neck share of 0.447 (yoke cbNeck -> hps 101 mm, front
# hps -> cfNeck 125) where his neck loop splits 0.483 at hps (98 / 105): the yoke's back neck went +12 % in relax1, the
# stand's front -1.5 %, and the yoke tented over the trapezius (its HPS column +10 % front-to-back). A pattern maker pins
# the shoulder seam where the back neck reaches round the form, so NECK_SPLIT places the neck point on the body's neck
# loop at the arc share of the garment's own neckline (back / (back + front), read off the pattern from each "hps" to
# its piece's centre-line neck point cbNeck / cfNeck), moved at most NECK_SPLIT_MAX along the loop. A garment with no
# such points keeps the landmark.
NECK_SPLIT = False  # module default OFF: garment key "neck_split": true (the parked jacket regressed with it, C113)
NECK_SPLIT_MAX = 0.02  # m along the loop
NECK_PIN_W = 2.0  # the neck points' pin weight, as the shoulder point's: soft (the muslin fit; C161)
LEGACY_NECK_PIN_W = 200.0  # fit_model "isometric" (held garments): the neck point pinned hard
FIT_MODELS = ("woven", "isometric")


def fit_model_for(model: str, garment: str, g: dict | None = None) -> str | None:
    """The fit model a garment is assembled with: its garment key "fit_model", else "isometric" when garment_kb
    fit_holds names "model:garment" or "model:*" (approved on the old fit, held until refitted), else None (the
    module default: the muslin fit)."""
    fm = (g or {}).get("fit_model")
    if fm is not None:
        if fm not in FIT_MODELS:
            raise ValueError(f"fit_model {fm!r}: one of {', '.join(FIT_MODELS)}")
        return fm
    from . import cloth
    holds = cloth._kb().get("fit_holds") or {}
    return "isometric" if f"{model}:{garment}" in holds or f"{model}:*" in holds else None


def _boundary_path_len(M, a: int, b: int) -> float | None:
    """The pattern length (uv) of the shortest path from vertex a to b along the outline of a's piece (None: none)."""
    from scipy.sparse.csgraph import dijkstra
    F = np.asarray(M["F"]); uv = np.asarray(M["uv"], float); pid = np.asarray(M["piece"])
    Fp = F[pid[F[:, 0]] == pid[a]]
    E = np.sort(np.r_[Fp[:, [0, 1]], Fp[:, [1, 2]], Fp[:, [2, 0]]], 1)
    u, cnt = np.unique(E, axis=0, return_counts=True)
    be = u[cnt == 1]
    if not len(be):
        return None
    w = np.linalg.norm(uv[be[:, 0]] - uv[be[:, 1]], axis=1)
    n = len(uv)
    G = coo_matrix((np.r_[w, w], (np.r_[be[:, 0], be[:, 1]], np.r_[be[:, 1], be[:, 0]])), shape=(n, n)).tocsr()
    d = dijkstra(G, indices=int(a))[int(b)]
    return float(d) if np.isfinite(d) else None


def neckline_share(M: dict) -> float | None:
    """The garment's back neck share: (mean back length cbNeck -> hps) / (back + mean front hps -> cfNeck), read
    along each piece's outline in the pattern; None when the pattern has no hps with both neck ends."""
    P = M["points"]
    back, front = [], []
    for k, v in P.items():
        nm, pt = k.split(":", 1)
        if pt not in ("hps", "hps.m"):
            continue
        for end, acc in (("cbNeck", back), ("cfNeck", front)):
            if f"{nm}:{end}" in P:
                L = _boundary_path_len(M, int(v), int(P[f"{nm}:{end}"]))
                if L:
                    acc.append(L)
    if not back or not front:
        return None
    b, f = float(np.mean(back)), float(np.mean(front))
    return b / (b + f)


def neck_split_point(body, share: float, max_move: float | None = None):
    """The point on the body's neck loop (the plane through its cb_neck, cf_neck and hps.L landmarks) whose arc from
    the centre back is `share` of the left half loop (cb -> cf), moved at most `max_move` along the loop from hps.L;
    None without those landmarks or a loop."""
    at = getattr(body, "at", {}) or {}
    if not all(k in at for k in ("cb_neck", "cf_neck", "hps.L")) or not hasattr(body, "V"):
        return None
    from . import tailor
    cb, cf, h = (np.asarray(at[k], float).reshape(-1)[:3] for k in ("cb_neck", "cf_neck", "hps.L"))
    n = np.cross(cf - cb, h - cb)
    if np.linalg.norm(n) < 1e-9:
        return None
    n /= np.linalg.norm(n)
    T = getattr(body, "T", None)
    if T is None:
        return None
    L = tailor.section(np.asarray(body.V, float), np.asarray(T), h, n, h)
    if L is None or len(L) < 8:
        return None
    L = np.asarray(L, float)
    ib, i_f = int(np.argmin(np.linalg.norm(L - cb, axis=1))), int(np.argmin(np.linalg.norm(L - cf, axis=1)))
    # the left half: walk from cb toward cf the way that passes x > 0
    m = len(L)
    for s in (1, -1):
        idx = [ib]
        while idx[-1] != i_f and len(idx) <= m:
            idx.append((idx[-1] + s) % m)
        half = L[idx]
        if np.mean(half[:, 0]) > 0:
            break
    seg = np.linalg.norm(np.diff(half, axis=0), axis=1)
    cum = np.r_[0.0, np.cumsum(seg)]
    if cum[-1] < 1e-6:
        return None
    ih = int(np.argmin(np.linalg.norm(half - h, axis=1)))
    mv = NECK_SPLIT_MAX if max_move is None else float(max_move)
    t = float(np.clip(share * cum[-1], cum[ih] - mv, cum[ih] + mv))
    j = int(np.clip(np.searchsorted(cum, t) - 1, 0, len(half) - 2))
    f = (t - cum[j]) / max(seg[j], 1e-12)
    return half[j] + f * (half[j + 1] - half[j])


def _pins(M, X0, body, ease, bsurf, under_v=None, neck_split: bool | None = None, neck_w: float | None = None):
    """Landmark pins: ([vertex], [target xyz], [weight]) full pins and ([vertex], [weight]) centre-line (x = 0) pins.
    A layer over another (under_v: the under garment's vertices) has its neck point ON THE LAYER BELOW plus ease, not
    on the skin: the under layer's height off the skin there (its collar band at the neck point) + THICK + ease
    (coordinator 2026-10-19: the jacket's seam off skin at HPS read 4.2 of 5-14 with the pin on the skin)."""
    full, cx = [], []
    at = getattr(body, "at", {}) if body is not None else {}
    ut = cKDTree(np.asarray(under_v, float)) if under_v is not None and len(under_v) else None
    hps_at = np.asarray(at["hps.L"], float).reshape(-1)[:3] if "hps.L" in at else None
    if (NECK_SPLIT if neck_split is None else neck_split) and hps_at is not None:
        sh_ = neckline_share(M)
        q_ = neck_split_point(body, sh_) if sh_ is not None else None
        if q_ is not None:
            hps_at = q_
    for k, v in M["points"].items():
        nm, pt = k.split(":", 1)
        side = 1.0 if X0[v, 0] >= 0 else -1.0
        if pt in ("hps", "hps.m") and hps_at is not None:
            q = hps_at * [side, 1, 1]
            if bsurf is not None:
                _, n, _ = bsurf.signed(q[None])
                lift = ease
                if ut is not None:
                    # the under layer's top at the neck point: its vertices within 8 mm of the normal through q
                    ii = ut.query_ball_point(q, 0.03)
                    if ii:
                        U = ut.data[ii] - q
                        h = U @ n[0]
                        rad = np.linalg.norm(U - np.outer(h, n[0]), axis=1)
                        hh = h[(rad < 0.008) & (h > 0) & (h < 0.015)]  # (not a band standing up the neck)
                        if len(hh):
                            lift = float(hh.min()) + THICK + ease  # (the layer itself, not its band standing beside)
                q = q + lift * n[0]
            full.append((v, q, float(NECK_PIN_W if neck_w is None else neck_w)))
        elif pt in ("shoulder", "shoulder.m") and "shoulder.L" in at:
            q = np.asarray(at["shoulder.L"], float) * [side, 1, 1]
            if bsurf is not None:
                _, n, _ = bsurf.signed(q[None])
                q = q + (ease + 0.008) * n[0]  # (a shoulder line lies over the shoulder's flesh; soft)
            full.append((v, q, 2.0))
        elif pt.startswith("cb") or pt in ("bottomMid", "topMid"):
            cx.append((v, 100.0))
    return full, cx


# AN OPEN COLLAR LIES SPREAD (fit round 7, 2026-10-19): a collar worn open (its stand's closure undone) is laid spread
# by the same rule the sim's placement uses (cloth._spread_open_collar: its front swung out from the neck's sides and
# tipped onto the collarbones), after the flaps are turned (a collar's fall is made first), and its swung front ends are
# HELD there (OPEN_SPREAD_W per vertex) through the seat and the let-go: the form has no gravity, so an unfastened collar
# does not fall open (the worn-open fronts' rule). Without it the form re-stood the neck pieces as a ring from the
# neckline (_band_init) and the turn folded the fall's ends to the centre front: Garrett's shirt collar points 48 mm
# apart (concept 146), its stand 25-36 mm off the neck in front, and the jacket collar over it stood off with it (60 / 90
# deg: 18 / 28 mm; no shirt: 5 / 12). Known answer: tests/test_pattern_form.py test_open_collar_lies_spread_on_the_form.
# OPT-IN: on Garrett the shirt alone spreads (points 48 -> 101 mm apart, their height 77 -> 91 mm below HPS, concept 93),
# but the jacket fitted over the spread shirt got WORSE (stand off the neck at 60 / 90 deg 18 / 28 -> 19 / 36 mm, jacket
# vertices inside the shirt 119 -> 368, shirt torn through the jacket collar in the renders): nothing presses the
# spread shirt collar under the jacket (cloth.pressed keeps made pieces as they lie). fit_round7 STATE.
OPEN_SPREAD = False
OPEN_SPREAD_W = 5.0
OPEN_SPREAD_HOLD = 0.6  # the held ends: neck-piece vertices the spread moved at least this x the most it moved (per side)


def open_collar_spread(B, M, body, X: np.ndarray):
    """The open-collar spread on the form: (X with the neck pieces spread, [(vertex, target, weight)] pins holding the
    swung ends) or (X, []) when no neck closure is open (cloth._spread_open_collar decides that)."""
    if not OPEN_SPREAD or B is None or body is None or not len(getattr(body, "V", [])):
        return X, []
    from . import cloth
    Xs = cloth._spread_open_collar(B, M, body, np.asarray(X, float).copy(), True)
    mv = np.linalg.norm(Xs - X, axis=1)
    if mv.max() < 1e-6:
        return X, []
    pins = []
    for sg in (-1.0, 1.0):
        side = (np.sign(Xs[:, 0]) == sg) & (mv > 1e-6)
        if side.any():
            for v in np.where(side & (mv >= OPEN_SPREAD_HOLD * mv[side].max()))[0]:
                pins.append((int(v), Xs[v].copy(), OPEN_SPREAD_W))
    return Xs, pins


WORN_OPEN_W = 60.0  # a worn-open point's pull to its offset from the centre line (a centre-line pin is 100)


def worn_open_pins(M: dict, X0: np.ndarray, worn_open: dict | None) -> list:
    """A FORM RULE for fronts worn open (coordinator 2026-10-19): the form has no gravity, so an unfastened front does
    not fall open; worn open, each front is turned about its roll line / break so the named point sits `offset` m off
    the centre line (|x|), on its own side, resting on what is under it (the body, the garment under: the obstacles).
    worn_open: {point name: offset} - a bare name ("break", "cfNeck") applies to every piece point of that name
    ("front.L:break" and "front.R:break"), a full "piece:point" to that one. Returns [(vertex, x target, weight)].
    Sources travel with the offsets (the caller's): Garrett's concept break 64 mm off CF (concept px, both sides)."""
    out = []
    for nm, off in (worn_open or {}).items():
        if nm == "source":
            continue
        for k, v in M["points"].items():
            pt = k.split(":", 1)[1]
            if k == nm or pt == nm or pt == nm + ".m":
                # the piece's side (its mean x), not the point's: Garrett's jacket fronts start crossed over CF (the
                # L break at x -15 mm), and a point's own sign sent it to the wrong side
                k = int(np.asarray(M["piece"])[v])
                side = 1.0 if float(np.mean(X0[np.asarray(M["piece"]) == k, 0])) >= 0 else -1.0
                out.append((int(v), side * float(off), WORN_OPEN_W))
    return out


# ORDER (dress-garrett 2026-10-19 order + seam lengths): worn open, the fronts swing FIRST, then the collars / stands
# are stood up on the swung necklines and the flaps (lapels, collar fall) turned there, as a tailor sets a collar on
# the fronts as they will be worn. Swung after the bands, the fronts left the collar / stand where the closed fronts
# had put them; the seams then dragged them: Garrett o2, the jacket collar ends 31.5 mm off the lapel plane (n8 4.8),
# the shirt stand crumpled into pleats. False restores the old order (A/B only).
SWING_FIRST = True
SWING_UNPINNED = True  # the first relax without the worn-open pins (the swing does the turning; see assemble)


def _swing_open(M, X, ox, fast, bsurf):
    """The worn-open START: each front with a worn-open point is turned in its own plane about its pivot (the piece's
    neck point "hps", else the top of its first fold row: the roll line's top) until the point sits at its x target.
    The turn is whole above the piece's highest fastened vertex and fades to none at it (a shirt open at the neck stays
    buttoned below; an unfastened jacket front swings whole). A rigid turn: the relax then only settles it on the
    layer under (a pin alone dragged the one point: 70% stretch on the known answer)."""
    pid = np.asarray(M["piece"])
    fz = {}
    for a, b in fast:
        for v in (a, b):
            fz[int(pid[v])] = max(fz.get(int(pid[v]), -np.inf), float(X[v, 2]))
    for v, xt, _ in ox:
        k = int(pid[v])
        sel = np.where(pid == k)[0]
        nm = M["names"][k]
        piv = None
        for key in (f"{nm}:hps", f"{nm}:hps.m"):
            if key in M["points"]:
                piv = X[M["points"][key]].copy()
        if piv is None:
            fr = [np.asarray(fd["rows"][0]) for fd in M.get("folds") or [] if fd["piece"] == nm and len(fd["rows"])]
            if not fr:
                continue
            r0 = fr[0]
            piv = X[r0[np.argmax(X[r0, 2])]].copy()
        # the piece's plane at the pivot: its normal (mean of the faces near the pivot), pointing off the body
        Fk = np.asarray(M["F"])[pid[np.asarray(M["F"])[:, 0]] == k]
        c = X[Fk].mean(1)
        flp = np.zeros(len(X), bool)  # (a turned flap's faces face the other way: the base's plane only)
        for fd in M.get("folds") or []:
            if fd["piece"] == nm and len(fd["rows"]):
                from . import folds as _fm
                flp[_fm._geom(M, fd)["flap0"]] = True
                flp[np.asarray(fd["rows"][0])] = True
        near = (np.linalg.norm(c - piv, axis=1) < 0.12) & ~flp[Fk].any(1)
        Nf = np.cross(X[Fk[near, 1]] - X[Fk[near, 0]], X[Fk[near, 2]] - X[Fk[near, 0]]).sum(0)
        ax = Nf / (np.linalg.norm(Nf) + 1e-12)
        zt, zh = float(X[v, 2]), fz.get(k, -np.inf)
        w = np.ones(len(sel)) if not np.isfinite(zh) else np.clip((X[sel, 2] - zh) / max(zt - zh, 1e-3), 0, 1)
        best = None
        for th in np.radians(np.linspace(-60, 60, 481)):
            q = piv + _rodrigues((X[v] - piv)[None], ax[None], np.array([th]))[0]
            e = abs(q[0] - xt)
            if best is None or e < best[0]:
                best = (e, th)
        if ROLL_TURN:
            w = w * roll_turn_weight(M, X, k)[sel]
        X[sel] = piv + _rodrigues(X[sel] - piv, np.tile(ax, (len(sel), 1)), w * best[1])
    return X


# THE LAPEL TURNS, THE CHEST STAYS (fit round 12, coordinator-approved method change): a jacket worn open does not turn its
# whole upper front about the neck point. The chest, held by the body at the shoulder, armhole and side seams, barely
# moves; only the lapel turns, about its roll line (neck point -> break), and the front below the break hangs from it.
# Turned whole (fit round 11, r11d), every seam hold above the break fought the swing: the sleeves held -> the lapel top
# through its base (r11e 86 / 102 vertices); freed -> the shirt sleeve through the jacket (29 / 32); the front dart
# folded to a fin (33 deg median). The swing's turn per vertex is now a FIELD: 1 on the roll line and on the lapel (the
# flap past it), 0 on the piece's seams to the garment the body holds (shoulder, armhole, side:
# every seam to a piece that is sewn to something else too; a patch sewn only to this piece, a pocket flap, rides on it,
# and bands stood up on the neckline follow the lapel), linear in pattern distance between them (d_seam / (d_roll +
# d_seam)). The break, on the roll line, still meets its worn-open offset; the cloth between the roll line and the held
# seams takes up the turn the way a real front does: it eases off the chest along the roll (the soft roll), not by
# sliding round the body. ROLL_TURN False: the old rigid turn (A/B only).
# RESULT (fit round 12, stop-loss): OPT-IN. As a START the field changed little: the relax decides where the chest goes
# (Garrett r12a chest drift p90 52 / 54 mm vs r11d 62 / 56, lapel through its base 9 / 23 % vs 13 / 12 %, break step
# 0.7 / 0.5 mm vs 1.7 / 1.4, shirt sleeves through 23 / 31 vs 29 / 32). Held as well (CHEST_HOLD 1), the chest stays
# (tube KAT drift 0) but the cloth has to give the opening somewhere: an isometric front cannot move its break 50 mm off
# CF with its chest and side seams fixed (the arc from the break to the side is 52 mm shorter than the cloth: tube KAT),
# so it compressed: lapels 66 / 90 % through their base (tube), Garrett r12d stretch p99 74 %, max 353 %. A real front
# gives that width by SHEAR (woven cloth shears at a small fraction of its tensile stiffness; the fit's edge isometry is
# shear-stiff): the lever is a woven (warp / weft / shear) cell energy; test_open_front_turns_its_lapel_not_its_chest
# (xfail) is its known answer.
ROLL_TURN = False
ROLL_REACH = None  # m (pattern) the turn fades to none over, from the roll line (None: to the held seams)
CHEST_HOLD = 0.0  # with OPEN_HOLD + ROLL_TURN: the chest above the break held at the closed fit, x OPEN_HOLD_W x (1 - turn)


def roll_turn_weight(M: dict, X: np.ndarray, k: int) -> np.ndarray:
    """The worn-open turn's weight per vertex of piece k (ROLL_TURN; 1 elsewhere): 1 on the first fold row (the roll
    line) and its flap, 0 on the seams to pieces the body holds, linear in pattern distance
    between. A piece with no fold row turns whole (1). Returns an (n,) array."""
    from scipy.spatial import cKDTree
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    nm = M["names"][k]
    out = np.ones(len(X))
    fds = [fd for fd in M.get("folds") or [] if fd["piece"] == nm and len(fd["rows"])]
    if not fds:
        return out
    from . import folds as _fm
    row = np.asarray(fds[0]["rows"][0], int)
    flap = np.asarray(_fm._geom(M, fds[0])["flap0"], bool)
    sw = np.asarray(M.get("sew", []), int).reshape(-1, 2)
    partners = {}
    for a, b in sw:
        partners.setdefault(int(pid[a]), set()).add(int(pid[b]))
        partners.setdefault(int(pid[b]), set()).add(int(pid[a]))
    held = np.zeros(len(X), bool)
    for a, b in sw:
        for p, q in ((a, b), (b, a)):
            if pid[p] == k and pid[q] != k and (partners.get(int(pid[q]), set()) - {k}):
                held[p] = True
    sel = np.where(pid == k)[0]
    if not held[sel].any():
        return out
    dr, _ = cKDTree(uv[row]).query(uv[sel])
    ds, _ = cKDTree(uv[sel[held[sel]]]).query(uv[sel])
    w = ds / np.maximum(dr + ds, 1e-9)
    if ROLL_REACH is not None:
        w = np.minimum(w, np.clip(1.0 - dr / ROLL_REACH, 0.0, 1.0))
    w[flap[sel]] = 1.0
    w[np.isin(sel, row)] = 1.0
    out[sel] = w
    return out


# PATCH_ON_BASE (fit round 26, C95): a PATCH, a piece sewn (or stitched) to one other piece only and along that piece's INTERIOR
# (a pocket flap on its pocket line; not a collar on a stand's edge, not a sleeve), lies on its base one THICK out, drawn
# there each relax round like a turned flap (FLAP_PULL), not at the body's ease: Garrett's flaps kept their old offset
# off the BODY (20-24 mm) while the plumb cut + BRIDGE moved the fronts out (~26 mm) and sank 20-25 of 25 vertices behind
# the front (r24c); a flap that starts behind its front stays there through the release (CCD keeps the order).
PATCH_ON_BASE = True


def patches(M: dict) -> list:
    """[(piece k, base piece b, k's vertices)] for every patch (see PATCH_ON_BASE)."""
    pid = np.asarray(M["piece"])
    F = np.asarray(M["F"])
    sw = np.r_[np.asarray(M.get("sew", []), int).reshape(-1, 2), np.asarray(M.get("stitch", []), int).reshape(-1, 2)]
    E = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    Eu, cnt = np.unique(E, axis=0, return_counts=True)
    border = np.zeros(len(pid), bool)
    border[Eu[cnt == 1].ravel()] = True
    out = []
    for k in range(len(M["names"])):
        a = sw[(pid[sw[:, 0]] == k) & (pid[sw[:, 1]] != k)][:, 1]
        a = np.r_[a, sw[(pid[sw[:, 1]] == k) & (pid[sw[:, 0]] != k)][:, 0]]
        if not len(a):
            continue
        bs = set(pid[a].tolist())
        if len(bs) != 1:
            continue
        b = bs.pop()
        if border[a].mean() > 0.5:  # (sewn to the base's edge: a joined piece, not a patch)
            continue
        out.append((k, int(b), np.where(pid == k)[0]))
    return out


WORN_EDGE_W = 20.0  # the swung front edge's pull to its swung x (a worn-open point's is WORN_OPEN_W)
WORN_EDGE = False  # opt-in: validation 2 A/B opened the fronts (hips 72 vs the sim's 75) but slid the fronts sideways (hem sweep +23 %, waist +6 %)
EDGE_FIELD = True  # fit round 11: the worn-open edge's targets carry the named points' corrections (worn_open_edge)
BREAK_STEP_MM = 3.0  # the front edge through the break: no vertex further than this off the edge's lines either side
BREAK_TURN_DEG = 60.0  # ... and the lines meet at less than this (the lapel's turned edge opens a V, never folds back)
BREAK_STEP_SOURCE = ("a front edge is ONE line: the lapel's outer edge runs on into the front edge below the break, no "
                     "notch or step (tailoring: the roll line starts AT the break on the edge; Joe 2026-10-19 on fit "
                     "round 10: 'the notches cut in the bottom of the lapels'); 3 mm = two cloth thicknesses")


CREASE_DEG = 20.0  # below the break, a front's faces meet at under this (p90 interior; median along each seam)
CREASE_SHARP_MM = 30.0  # ... and its interior edges over 2 x CREASE_DEG add up to under this (a crease LINE, not faceting)
CREASE_SOURCE = ("an open front below the break hangs smooth (the concept: a soft open hang, a flap pocket; a front dart "
                 "is pressed, never a ridge); Joe on fit round 10: 'hopefully there's not a sharp fold here'. 20 deg "
                 "between ~25 mm faces = a bend radius of ~70 mm, the body's own at the side")
FLAP_THROUGH_MAX = 0.05  # share of a turned flap's vertices (past the hinge) through its own base
FLAP_THROUGH_SOURCE = ("a turned lapel lies one cloth thickness ON its base (pressed); Joe on fit round 10: 'the tops of "
                       "the lapels are embedded in the layer below'; round 6's clean fit had 0/67 at the gorge")


def front_creases(M: dict, X: np.ndarray) -> dict:
    """Creases on each piece with a "break" point, BELOW the break (fit round 11): the dihedral between neighbouring
    faces with the mesh welded at its sew pairs (a dart or seam ridge is no interior edge), fold rows left out.
    {piece: {"interior_p90", "interior_max", "seams": {other piece or "self": [median, max]}, "ok"}} (deg)."""
    F = np.asarray(M["F"]); n = len(X); pid = np.asarray(M["piece"]); names = list(M["names"])
    par = np.arange(n)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]; a = par[a]
        return a
    for a, b in np.asarray(M.get("sew", []), int).reshape(-1, 2):
        ra, rb = find(int(a)), find(int(b))
        if ra != rb:
            par[max(ra, rb)] = min(ra, rb)
    rep = np.array([find(i) for i in range(n)])
    N = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    fold = np.zeros(n, bool)
    for fd in M.get("folds") or []:
        for r in fd["rows"]:
            fold[np.asarray(r, int)] = True
    ed = {}
    for j, f in enumerate(rep[F]):
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            ed.setdefault((min(a, b), max(a, b)), []).append(j)
    out = {}
    for key, bvx in M["points"].items():
        if not key.endswith(":break"):
            continue
        k = names.index(key.split(":")[0])
        zb = float(X[bvx, 2]) - 0.01
        inner, seams, sharp = [], {}, 0.0
        for (a, b), js in ed.items():
            if len(js) != 2 or (fold[a] and fold[b]) or (X[a, 2] + X[b, 2]) / 2 > zb:
                continue
            f0, f1 = F[js[0]], F[js[1]]
            k0, k1 = int(pid[f0[0]]), int(pid[f1[0]])
            if k not in (k0, k1):
                continue
            ang = math.degrees(math.acos(float(np.clip(N[js[0]] @ N[js[1]], -1, 1))))
            if len(set(f0.tolist()) & set(f1.tolist())) >= 2:
                inner.append(ang)
                if ang > 2 * CREASE_DEG:
                    sharp += float(np.linalg.norm(X[a] - X[b]))
            else:
                seams.setdefault("self" if k0 == k1 else names[k1 if k0 == k else k0], []).append(ang)
        if not inner:
            continue
        sm = {s: [round(float(np.median(v)), 1), round(max(v), 1)] for s, v in seams.items()}
        p90 = float(np.percentile(inner, 90))
        out[key.split(":")[0]] = {"interior_p90": round(p90, 1), "interior_max": round(max(inner), 1), "seams": sm,
                                  "sharp_mm": round(sharp * 1000, 0),
                                  "ok": bool(p90 <= CREASE_DEG and sharp * 1000 <= CREASE_SHARP_MM
                                              and all(m <= CREASE_DEG for m, _ in sm.values()))}
    return out


FLAP_THROUGH_REACH = 0.008  # m: a flap vertex is read against its base only where it stands over it (C124)


def flap_through_base(M: dict, X: np.ndarray, body=None, hinge: float = 0.018) -> dict:
    """Each folded piece's turned flap vertices (folds.flap_faces; past `hinge` m of its fold rows in the pattern: the
    roll's own bend) THROUGH its own base surface (signed distance < 0, within 20 mm of it): {piece: {"through", "n",
    "share", "ok"}} against FLAP_THROUGH_MAX (fit round 11). The base's outside is read off the body (`body`, the form's
    body: its surface orients the base's normals; without it the sense is arbitrary)."""
    from . import folds as _fm
    F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); names = list(M["names"]); uv = np.asarray(M["uv"])
    fl = _fm.flap_faces(M, F)
    bs = _body_surface(body) if body is not None else None
    out = {}
    for nm in sorted({fd["piece"] for fd in M.get("folds") or []}):
        k = names.index(nm)
        fpc = pid[F[:, 0]] == k
        if not (fl & fpc).any() or not (~fl & fpc).any():
            continue
        bv = np.unique(F[fpc & ~fl])
        fv = np.setdiff1d(np.unique(F[fpc & fl]), bv)
        rows = [np.asarray(r, int) for fd in M["folds"] if fd["piece"] == nm for r in fd["rows"]]
        if rows and len(fv):
            dd, _ = cKDTree(uv[np.concatenate(rows)]).query(uv[fv])
            fv = fv[dd > hinge]
        if not len(fv):
            continue
        bF = F[fpc & ~fl]
        # THE BASE ACROSS A SEAM (C119, shirt round 9; C46's rule): a fold whose own base side is narrow (a two-piece
        # collar's fall, its roll 4-6 mm above the seam) lies on the piece sewn there (the stand). Read against its
        # 6 mm strip alone, the fall read 0.8 'through' on every start, the known-good closed one too: no signal
        narrow = False
        for fd in M["folds"]:
            if fd["piece"] != nm:
                continue
            g_ = _fm._geom(M, fd)
            ob_ = np.setdiff1d(np.asarray(g_["sel"]), np.where(np.asarray(g_["flap0"]))[0])
            narrow |= bool(len(ob_)) and float(np.asarray(g_["d0"])[ob_].max()) < BASE_NARROW
        sw = np.asarray(M.get("sew") if M.get("sew") is not None else np.zeros((0, 2), int)).reshape(-1, 2)
        if BASE_ACROSS_SEAM and narrow and len(sw):
            ob = np.zeros(len(X), bool)
            ob[bv] = True
            oth = sorted({int(pid[b]) for a, b in sw if ob[a] and pid[b] != k} |
                         {int(pid[a]) for a, b in sw if ob[b] and pid[a] != k})
            if oth:
                oF = F[np.isin(pid[F[:, 0]], oth)]
                bv = np.union1d(bv, np.unique(oF))
                bF = np.r_[bF, oF]
        ix = -np.ones(len(X), int); ix[bv] = np.arange(len(bv))
        d, _, dist = _Surface(X[bv], ix[bF], ref=bs).signed(X[fv])
        # (C124, shirt round 10: only where the flap stands OVER its base, sideways within FLAP_THROUGH_REACH of the
        # nearest base vertex: past the base's outline its plane says nothing. Jacket r26 collar: 21 of 25 'through'
        # were past the stand's neck edge, the fall lying on the body below it; over the stand 4, 0.1 mm deep)
        tang = np.sqrt(np.maximum(dist ** 2 - d ** 2, 0.0))
        m = (dist < 0.02) & (tang < FLAP_THROUGH_REACH)
        t = int((d[m] < 0).sum())
        out[nm] = {"through": t, "n": int(m.sum()), "share": round(t / max(int(m.sum()), 1), 3),
                   "ok": bool(t <= FLAP_THROUGH_MAX * max(int(m.sum()), 1))}
    return out


# GORGE LIE (fit round 17, Joe on r15e: the collar's end stands off the lapel like a small square tab and the gorge
# seam twists). Tailoring: the gorge seam is pressed open and the collar's end lies ON the lapel as one surface
# across it (Cabrera & Flaherty, Classic Tailoring Techniques; the C48 pressed-seam rule above). Limits from the cloth
# itself: across a pressed seam the two sides may differ by the seam allowances under them, two cloth thicknesses
# (2 x 2 mm wool coating, cloth.FABRICS) over a 10 mm allowance: atan(4 / 10) = 22 deg is the most a seam can bend
# by its allowances, so a twist of 10 deg / cm (half of it) and a plane change of 15 deg are the limits; the collar's
# end may stand off the lapel's plane by its own layers (fall over stand: 2 thicknesses) + 1 thickness: 6 mm.
GORGE_TWIST_DEG_CM = 10.0
GORGE_ACROSS_DEG = 15.0
GORGE_TIP_MM = 6.0
GORGE_SOURCE = ("the gorge seam is pressed open; the collar's end lies on the lapel as one surface across it "
                "(Cabrera & Flaherty, Classic Tailoring Techniques; C48). Limits: 2 x 2 mm cloth over a 10 mm seam "
                "allowance (cloth.FABRICS wool_coating), Joe on r15e (round 17)")


def _plane_fit(P):
    c = P.mean(0)
    return c, np.linalg.svd(P - c)[2][-1]


def seam_lie(V: np.ndarray, F: np.ndarray, pid: np.ndarray, pairs, win: float = 0.01) -> dict:
    """How two pieces lie across a sewn seam. pairs (a, b): the seam's vertex pairs IN ORDER along it, a on one side,
    b on the other. Per side, the surface normal's rotation ABOUT THE SEAM'S TANGENT (twist; the normal's turn about
    the binormal, the surface's own bend along the seam, is projected out) per cm, read between vertices >= `win` m
    apart along the seam: {"twist_a": {p50, max}, "twist_b": ..}; "across" (deg): the angle between the two sides'
    normals at each pair ({p50, max}; 0 = one surface, pressed open). Normals: each piece's own faces only."""
    V = np.asarray(V, float); F = np.asarray(F); pid = np.asarray(pid)
    pr = np.asarray(pairs, int)
    out = {"n": int(len(pr))}
    if len(pr) < 3:
        return out
    N = {}
    for side, col in (("a", 0), ("b", 1)):
        ks = np.unique(pid[pr[:, col]])
        Fs = F[np.isin(pid[F], ks).all(1)]
        N[side] = _vnormals(V, Fs)[pr[:, col]]
    P = V[pr[:, 0]]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    for side in ("a", "b"):
        n_, rates = N[side], []
        for i in range(len(pr)):
            j = int(np.searchsorted(s, s[i] + win - 1e-9))
            if j >= len(pr):
                break
            t = P[j] - P[i]
            t /= np.linalg.norm(t) + 1e-12
            u, w = n_[i] - (n_[i] @ t) * t, n_[j] - (n_[j] @ t) * t
            c = np.clip(u @ w / (np.linalg.norm(u) * np.linalg.norm(w) + 1e-12), -1, 1)
            rates.append(np.degrees(np.arccos(c)) / ((s[j] - s[i]) * 100))
        out[f"twist_{side}"] = ({"p50": round(float(np.median(rates)), 1), "max": round(float(np.max(rates)), 1)}
                                if rates else None)
    ac = np.degrees(np.arccos(np.clip(np.abs(np.sum(N["a"] * N["b"], 1)), 0, 1)))
    out["across"] = {"p50": round(float(np.median(ac)), 1), "max": round(float(np.max(ac)), 1)}
    return out


def _end_off_plane(X, lapel_v, end_v):
    """The end's vertices off the plane fitted to `lapel_v` (mm): tip (max) and p50; the end's own plane vs it (deg)."""
    c, n = _plane_fit(X[lapel_v])
    d = np.abs((X[end_v] - c) @ n) * 1000
    out = {"tip_mm": round(float(d.max()), 1), "p50_mm": round(float(np.median(d)), 1)}
    if len(end_v) >= 3:
        _, m = _plane_fit(X[end_v])
        out["plane_deg"] = round(float(np.degrees(np.arccos(min(abs(float(n @ m)), 1.0)))), 1)
    return out


def _selftest_gorge_lie():
    """Planted answers on two strips sewn along x (a: y < 0, b: y > 0, 2 mm spacing): flat (one surface) reads 0;
    b turned about the seam linearly 0 -> 20 deg over 10 mm reads twist_b 20 deg / cm and twist_a 0; a pressed seam
    bent along a 50 mm radius cylinder (both sides curve with it: no twist) reads ~0 twist / across; b hinged 30 deg
    about the seam reads across 30 and twist 0; a collar end lifted 12 mm reads tip 12 off the lapel's plane."""
    h = 0.002
    xs = np.arange(0, 0.0201, h)
    ys = np.arange(0, 0.0101, h)
    nx, ny = len(xs), len(ys)

    def strips(fb):
        Va = np.array([fb("a", x, -y) for x in xs for y in ys])
        Vb = np.array([fb("b", x, y) for x in xs for y in ys])
        Fa = []
        for i in range(nx - 1):
            for j in range(ny - 1):
                q = [i * ny + j, (i + 1) * ny + j, (i + 1) * ny + j + 1, i * ny + j + 1]
                Fa += [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
        Fa = np.array(Fa)
        V = np.r_[Va, Vb]
        F = np.r_[Fa, Fa[:, ::-1] + len(Va)]
        pid = np.r_[np.zeros(len(Va), int), np.ones(len(Vb), int)]
        return V, F, pid, [(i * ny, i * ny + len(Va)) for i in range(nx)]

    def flat(side, x, y):
        return np.array([x, y, 0.0])

    def twisted(side, x, y):
        th = 0.0 if side == "a" else np.radians(20.0) * min(x / 0.01, 1.0)
        return np.array([x, y * np.cos(th), y * np.sin(th)])

    def bent(side, x, y):
        R = 0.05
        return np.array([R * np.sin(x / R), y, R * (1 - np.cos(x / R))])

    def hinged(side, x, y):
        th = 0.0 if side == "a" else np.radians(30.0)
        return np.array([x, y * np.cos(th), y * np.sin(th)])

    r = seam_lie(*strips(flat))
    assert r["twist_a"]["max"] < 0.5 and r["twist_b"]["max"] < 0.5 and r["across"]["max"] < 0.5, r
    r = seam_lie(*strips(twisted))
    assert abs(r["twist_b"]["max"] - 20.0) < 3.0 and r["twist_a"]["max"] < 0.5, r  # (vertex normals blend the ramp ends)
    r = seam_lie(*strips(bent))
    assert r["twist_a"]["max"] < 1.0 and r["twist_b"]["max"] < 1.0 and r["across"]["max"] < 1.0, r
    r = seam_lie(*strips(hinged))
    assert abs(r["across"]["p50"] - 30.0) < 1.0 and r["twist_b"]["max"] < 0.5, r
    V, F, pid, pairs = strips(flat)
    end = np.where((pid == 1) & (V[:, 0] < 0.006))[0]
    V2 = V.copy()
    V2[end, 2] += 0.012 * (V[end, 1] / 0.01)
    assert abs(_end_off_plane(V2, np.where(pid == 0)[0], end)["tip_mm"] - 12.0) < 0.5
    assert _end_off_plane(V, np.where(pid == 0)[0], end)["tip_mm"] < 0.1


@validated.known_answer(_selftest_gorge_lie)
def gorge_lie(M: dict, X: np.ndarray, end_r: float = 0.025, lapel_r: float = 0.03, win: float = 0.01,
              hinge: float = 0.018) -> dict:
    """Each front's gorge (fit round 17): the seam pairs between the front's TURNED lapel (its fold's flap) and the
    collar / stand past `hinge` (pattern) of its fold rows (flap_through_base's hinge: the roll's own bend is left
    out), ordered from the front's cfNeck (the notch end) inward: seam_lie (twist per side, across), and the
    collar's end (collar + stand vertices within `end_r` m, 3D, of the notch-end seam vertex) off the
    lapel's plane (fitted to the lapel's flap vertices within `lapel_r` m of cfNeck, pattern): tip_mm (max), p50_mm,
    plane_deg. {front: {..., "ok"}} against GORGE_TWIST_DEG_CM / GORGE_ACROSS_DEG / GORGE_TIP_MM."""
    from . import folds as _fm
    X = np.asarray(X, float); F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); uv = np.asarray(M["uv"], float)
    names = list(M["names"]); P = M["points"]
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    kc = [names.index(n) for n in ("collar", "stand") if n in names]
    out = {}
    for fd in M.get("folds") or []:
        nm = fd["piece"]
        if not nm.startswith("front.") or f"{nm}:cfNeck" not in P or not kc or not len(fd["rows"]):
            continue
        k = names.index(nm)
        fl = np.zeros(len(uv), bool)
        g = _fm._geom(M, fd)
        fl[np.asarray(g["rows"][-1]["v"], int)] = True
        fl[np.asarray(g["rows"][-1]["row"], int)] = True
        cn = P[f"{nm}:cfNeck"]
        # the lapel's FACE only: front vertices past `hinge` (pattern) of the fold rows; across the roll's own hinge the
        # lapel turns ~160 deg in a few mm (its roll, not a twist), and the gorge seam crosses it there
        rows_ = np.concatenate([np.asarray(r_, int) for r_ in fd["rows"]])
        far = np.zeros(len(uv), bool)
        dh, _ = cKDTree(uv[rows_]).query(uv[fl])
        far[np.where(fl)[0][dh > hinge]] = True
        fl &= far
        pr = set()
        for a, b in sw:
            if pid[b] == k:
                a, b = b, a
            if pid[a] == k and pid[b] in kc and fl[a]:
                pr.add((int(a), int(b)))
        pr_, seen = [], set()
        for a, b in sorted(pr, key=lambda t: float(np.linalg.norm(uv[t[0]] - uv[cn]))):
            if a not in seen:  # one pair per front vertex
                seen.add(a); pr_.append((a, b))
        row = seam_lie(X, F, pid, pr_, win=win)
        # the collar's end: every collar / stand vertex within end_r (3D) of the notch-end seam vertex (the fall is
        # sewn to the stand, not the front: a pattern radius about the front seam would leave it out)
        endv = np.where(np.isin(pid, kc) & (np.linalg.norm(X - X[pr_[0][1]], axis=1) < end_r))[0] if pr_ else []
        lap = np.where(fl & (pid == k) & (np.linalg.norm(uv - uv[cn], axis=1) < lapel_r))[0]
        if len(endv) and len(lap) >= 3:
            row.update(_end_off_plane(X, lap, endv))
        tw = max(((row.get(f"twist_{s}") or {}).get("max", 0.0) for s in ("a", "b")), default=0.0)
        row["ok"] = bool(row.get("n", 0) >= 3 and tw <= GORGE_TWIST_DEG_CM
                         and row.get("across", {}).get("max", 0.0) <= GORGE_ACROSS_DEG
                         and row.get("tip_mm", 0.0) <= GORGE_TIP_MM)
        out[nm] = row
    return out


def edge_through_break(M: dict, X: np.ndarray, span: float = 0.04, near: float = 0.012, plane=(0, 2)) -> dict:
    """The front edge through each piece's "break" point, read in the plane `plane` of X (fitted: the front view x, z;
    the flat: pass the pattern uv with plane (0, 1)): the border walked both ways from the break, a line fitted to each
    arm between `near`/3 and `span` (m, along the edge), then step_mm = the furthest vertex within `near` of the break
    from the nearer line, turn_deg = the angle between the arms' directions continuing through the break (0 straight on,
    180 folded back). {piece: {"step_mm", "turn_deg", "ok"}} against BREAK_STEP_MM / BREAK_TURN_DEG."""
    from collections import defaultdict
    F = np.asarray(M["F"])
    E = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], axis=1)
    e, c = np.unique(E, axis=0, return_counts=True)
    adj = defaultdict(list)
    for a, b in e[c == 1]:
        adj[int(a)].append(int(b)); adj[int(b)].append(int(a))
    Y = np.asarray(X, float)[:, list(plane)]
    out = {}
    for key, b in M["points"].items():
        if not key.endswith(":break") or len(adj[b]) != 2:
            continue
        arms = []
        for s in adj[b]:
            seq, prev, cur, L = [], b, s, 0.0
            while L < span and len(seq) < 500:
                L += float(np.linalg.norm(Y[cur] - Y[seq[-1][0] if seq else b]))
                seq.append((cur, L))
                nx = [q for q in adj[cur] if q != prev]
                if not nx:
                    break
                prev, cur = cur, nx[0]
            arms.append(seq)
        lines, nearv = [], [b]
        for seq in arms:
            far = np.array([Y[v] for v, L in seq if L >= near / 3])
            nearv += [v for v, L in seq if L < near]
            if len(far) < 2:
                break
            c0 = far.mean(0)
            d = np.linalg.svd(far - c0)[2][0]
            if d @ (far[-1] - far[0]) < 0:
                d = -d
            lines.append((c0, d))
        if len(lines) < 2:
            continue
        dist = lambda p, ln: abs(float(ln[1][0] * (p - ln[0])[1] - ln[1][1] * (p - ln[0])[0]))
        step = max(min(dist(Y[v], ln) for ln in lines) for v in nearv)
        turn = math.degrees(math.acos(float(np.clip(-lines[0][1] @ lines[1][1], -1, 1))))
        out[key.split(":")[0]] = {"step_mm": round(step * 1000, 1), "turn_deg": round(turn, 1),
                                  "ok": bool(step * 1000 <= BREAK_STEP_MM and turn <= BREAK_TURN_DEG)}
    return out


EDGE_FREE = 0.08  # m (pattern): the seat's attraction fades to none toward a worn-open front edge (0: off)


def worn_open_edge(M: dict, X: np.ndarray, ox: list, band: float = 0.01, reach: float = 0.005, fast: list | None = None) -> list:
    """The worn-open front EDGE held where the swing put it (validation 2, 2026-10-19): with only the named points
    pinned, the seat's attraction wrapped the free edge between them back round the body toward CF (Garrett, hips:
    swung 72 mm off CF, seated 43, let go 55; the sim of the same pattern 75). The edge = each worn-open piece's border
    vertices that are CF-most in their 1 cm height band (within `reach`), from the lowest worn-open point to the
    highest, plus the CF-most vertices of its roll line (first fold row) above it: the lapel line. A gravity-free
    stand-in for the fronts' weight and stiffness keeping them hanging open; x only, so they still rest on what is
    under them. Returns [(vertex, x target, weight)] in the worn_open_pins form."""
    pid = np.asarray(M["piece"])
    border = np.asarray(M.get("border") if M.get("border") is not None else np.zeros(len(X), bool), bool)
    sewn = np.zeros(len(X), bool)
    sewn[np.asarray(M.get("sew", []), int).ravel()] = True
    out, have = [], {int(v) for v, _, _ in ox}
    for k in sorted({int(pid[v]) for v, _, _ in ox}):
        zs = [float(X[v, 2]) for v, _, _ in ox if pid[v] == k]
        lowest = min((v for v, _, _ in ox if pid[v] == k), key=lambda v: X[v, 2])
        x_low = [abs(xt) for v, xt, _ in ox if v == lowest][0]
        side = 1.0 if float(np.mean(X[pid == k, 0])) >= 0 else -1.0
        nm = M["names"][k]
        roll = np.zeros(len(X), bool)
        for fd in M.get("folds") or []:
            if fd["piece"] == nm and len(fd["rows"]):
                roll[np.asarray(fd["rows"][0], int)] = True
        # (below the lowest worn-open point the free edge hangs plumb, see below; not a piece its buttons hold: a shirt
        # open at the neck stays buttoned below; hung, Garrett's shirt fronts opened to the belt)
        hang = OPEN_HANG and OPEN_HOLD and k not in {int(pid[v]) for pr in (fast or []) for v in pr}
        cand = np.where((pid == k) & ((border & (X[:, 2] >= min(zs) - 1e-6) & (X[:, 2] <= max(zs) + 1e-6))
                                      | (border & ~sewn & (X[:, 2] < min(zs) - 1e-6) & hang)
                                      | (roll & (X[:, 2] > max(zs)))))[0]
        if not len(cand):
            continue
        # THE EDGE FIELD (fit round 11, Joe: "the notches cut in the bottom of the lapels"): the rigid swing turns the
        # front once per worn-open point, so it meets only the LAST one (Garrett: cfHem at 96 mm, the break left at ~50
        # vs its 64). Held at their swung x, the edge vertices then fought the break's own pin: the break vertex alone
        # was dragged 10 mm out of the edge, a spike (a 94 deg turn) where the lapel meets the front. A front edge is ONE
        # line (tailoring: the lapel's edge runs on into the front edge at the break, no step): every edge vertex takes
        # the named points' corrections (target - swung x), linear in height between them, the top one fading to none
        # at the roll line's top (the lapel pivots about the neck), the bottom one held below. EDGE_FIELD False: old.
        corr = sorted((float(X[v, 2]), side * xt_ - side * float(X[v, 0])) for v, xt_, _ in ox if pid[v] == k)
        ztop = float(X[roll, 2].max()) if roll.any() else corr[-1][0]
        zc = np.array([c[0] for c in corr] + ([ztop] if ztop > corr[-1][0] + 1e-6 else []))
        cc = np.array([c[1] for c in corr] + ([0.0] if ztop > corr[-1][0] + 1e-6 else []))
        cfun = (lambda z: float(np.interp(z, zc, cc))) if EDGE_FIELD else (lambda z: 0.0)
        sx = side * X[cand, 0]
        bz = np.floor(X[cand, 2] / band).astype(int)
        for b in np.unique(bz):
            m = bz == b
            lo = sx[m].min()
            for v in cand[m][sx[m] <= lo + reach]:
                if int(v) not in have:
                    # THE HANG (fit round 10): below the lowest worn-open point the free edge falls plumb from it (its
                    # weight, which the form lacks): x held at that point's offset, not where the rigid swing carried
                    # it (the swing kept the side seams on the front: they slid); with no point below the break the
                    # edge wrapped back to CF (open tube: 0.6 mm off CF). The edge keeps its drafted line: a vertex
                    # its pattern puts further from that point across (a cutaway) hangs that much further out.
                    du = abs(float(M["uv"][v][0]) - float(M["uv"][lowest][0]))
                    xt = (side * (x_low + du) if (hang and X[v, 2] < min(zs) - 1e-6)
                          else float(X[v, 0]) + side * cfun(float(X[v, 2])))
                    out.append((int(v), xt, WORN_EDGE_W))
    return out


OPEN_HOLD = False  # opt-in (fit round 10 A/B): a worn-open front's seams to the rest of the garment stay where the closed fit put them
HANG_FREE = True  # fit round 11: a worn-open front below its break is not drawn onto the body (assemble, EDGE_FREE block)
HOLD_SLEEVES = False  # opt-in, fit round 11 A/B (r11e: sleeves 29/32 -> 18/15 but the lapel top back through its base 40-120 mm L 86 / R 102: the rigid swing of the upper front fights any hold above the break). A worn-open front's seams to its sleeves are held at every height (the body holds the arm; freed with the shoulder, the shirt sleeve came through: 8/11 -> 22/27)
HOLD_NAMED = True  # fit round 11: the hold's height from the named worn-open points (the break), not the edge pins
OPEN_HOLD_W = 20.0  # the held seam vertex's pull to its closed-fit position (3D)
OPEN_HANG = True  # with OPEN_HOLD: the free edge below the lowest worn-open point hangs plumb from it (worn_open_edge)


# A PLUMB JACKET'S SIDE SEAMS HANG ON THE VERTICAL BELOW THE UNDERARM (fit round 35, C181; Joe 2026-10-20: the jacket
# "should basically just fall straight down"): real tailoring cuts the side seam plumb and the jacket hangs from the
# shoulders, so below its underarm point the side seam sits on the vertical through it. Without it the muslin fit of
# round 34's straight-fall pattern slid the front panel's side seam forward round the body (60 deg from CF at the hem
# vs 74-81 in round 33, y 63 -> 107 mm forward) and the extra girth became front LAP: the open fronts met at CF (C180).
# PLUMB_HOLD: each seam between the named piece kinds (front|side, side|back on a three-panel jacket; front|back where
# there is no side panel), its vertices below the seam's top held SOFTLY (weight PLUMB_W per vertex, ramped in over
# "ramp" m below the top, as the neck pin: soft) on the vertical through the top: "anchor" "hung" (default) = where the
# top hangs when the jacket is on the shoulders, before the seat draws it onto the body (read once, as the seat
# starts), "live" = the top as it lies each round; axes "y" (front / back) by default, "xy" also holds x, outward only.
# A/B on Garrett (fit_round35 a1-a4 + styled b1-b2; concept edge off CF 450/550/650 71/78/94, waist / hem 414 / 482,
# side line <= 20): hung y (a2) 59/90/124, 434 / 470, 21 (chosen: widths + side line right, the fronts open); live y
# (a3) 45/71/98 but 378 / 459 and the sides pinched in 32 under the chest (a flared skirt); xy boxed the jacket (a1
# hung: chest 477 / waist 522; a4 live: 448 / 466); as a first styling op (garment_pull.plumb, b1 / b2) the seams stop
# half way (the threads would stretch) and the fronts stay lapped (edge 450 10-50, 650 0-6).
PLUMB_HOLD = {"seams": [["front", "side"], ["side", "back"]], "w": 2.0, "ramp": 0.05, "axes": "y", "anchor": "hung"}


def plumb_hold_for(g: dict | None) -> dict | None:
    """The plumb hold garment g is fitted with: its own "plumb_hold" (a dict edits PLUMB_HOLD, false none), else
    PLUMB_HOLD for a design declared to fall straight (cloth_workflow.falls_straight_design, C179), else None."""
    from .cloth_workflow import falls_straight_design
    own = (g or {}).get("plumb_hold")
    if own is False:
        return None
    if isinstance(own, dict):
        return dict(PLUMB_HOLD, **own)
    return dict(PLUMB_HOLD) if (own or falls_straight_design(g or {})) else None


def plumb_seam_pins(M: dict, X: np.ndarray, hold: dict | None) -> list:
    """[(vertex, top vertex, weight, axes, anchor xy or None)] for PLUMB_HOLD on the fit X: per seam (each side), its
    sewn vertices on both pieces below its top (weight ramped in); the target the (x, y) of the seam's top vertex: on
    X ("hung", the anchor given) or as it lies each round ("live", None)."""
    if not hold:
        return []
    pid = np.asarray(M["piece"])
    names = list(M["names"])
    kind = [nm.split(".")[0] for nm in names]
    side = [nm.split(".", 1)[1] if "." in nm else "" for nm in names]
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    out = []
    for ka, kb in hold.get("seams") or []:
        for sd in sorted({s for s in side if s}):
            ia = [k for k, nm in enumerate(names) if kind[k] == ka and side[k] == sd]
            ib = [k for k, nm in enumerate(names) if kind[k] == kb and side[k] == sd]
            m = (np.isin(pid[sw[:, 0]], ia) & np.isin(pid[sw[:, 1]], ib)) | (np.isin(pid[sw[:, 0]], ib) & np.isin(pid[sw[:, 1]], ia))
            if not m.any():
                continue
            ss = np.asarray(M.get("sew_seam") if M.get("sew_seam") is not None else np.zeros(len(sw)), int).reshape(-1)
            for sid in np.unique(ss[m]):  # (each seam on its own vertical: a tube's two seams are two lines)
                v = np.unique(sw[m & (ss == sid)].ravel())
                tv = int(v[np.argmax(X[v, 2])])
                ramp = max(float(hold.get("ramp", 0.05)), 1e-6)
                live = hold.get("anchor", "hung") == "live"
                for k in v:
                    r = float(np.clip((X[tv, 2] - X[k, 2]) / ramp, 0.0, 1.0))
                    if r > 0:
                        out.append((int(k), tv, float(hold.get("w", 2.0)) * r, hold.get("axes", "y"),
                                    None if live else (float(X[tv, 0]), float(X[tv, 1]))))
                band = float(hold.get("band", 0.0) or 0.0)
                if band > 0 and not live:  # (fit round 39: the panels either side move WITH their seam, feathered to 0
                    # at `band`: a hold on the seam line alone pinned a crease along it, the panels folding 35-110 deg
                    # across the front|side seam where they hung forward of it: a proud cord down Garrett's sides)
                    from scipy.spatial import cKDTree as _T
                    sv = np.asarray([k for k in v if X[tv, 2] - X[k, 2] > 0], int)
                    if len(sv):
                        cand = np.where(np.isin(pid, ia + ib))[0]
                        cand = cand[~np.isin(cand, v) & (X[cand, 2] < X[tv, 2])]
                        d, j = _T(X[sv]).query(X[cand])
                        for q, dq, jq in zip(cand, d, j):
                            if dq < band:
                                k = sv[jq]
                                r = float(np.clip((X[tv, 2] - X[k, 2]) / ramp, 0.0, 1.0)) * (1.0 - dq / band)
                                if r > 0:
                                    dy = float(X[tv, 1] - X[k, 1])
                                    out.append((int(q), tv, float(hold.get("w", 2.0)) * r, "y",
                                                (float(X[q, 0]), float(X[q, 1]) + dy)))
    return out


def open_seam_holds(M: dict, Xc: np.ndarray, ox: list, placed: dict | None = None, fast: list | None = None) -> list:
    """A worn-open front HANGS from its seams (fit round 10): in a real jacket worn open the front pivots about the roll
    line / break and its edge falls by its weight, while the side seams, the back and the sleeves stay where the body
    holds them. The form has no gravity: opened by its edge alone, an isometric front can only open by sliding the whole
    panel round the body (Garrett r9h: the side seams out, hem 580 mm wide vs 478, a peplum flare). The stand-in: every
    vertex of a worn-open piece sewn to ANOTHER piece (not its own darts, not a band stood up on it: collars / stands)
    below the piece's highest worn-open point is held at its position in the CLOSED fit (Xc), together with its partner
    across the seam. The edge pins then open the front only by what the panel can give between the held seam and the
    edge: it bridges off the body (the hang) instead of sliding. A piece with a fastened closure (`fast`: a shirt open
    at the neck, buttoned below) is held by its buttons and is left alone (held too, Garrett's shirt went into the
    body: 72 vertices). Returns [(vertex, xyz target, weight)] (the `full` pin form)."""
    pid = np.asarray(M["piece"])
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    fk = {int(pid[v]) for pr in (fast or []) for v in pr}
    out, seen = [], set()
    for k in sorted({int(pid[v]) for v, _, _ in ox} - fk):
        zb = max(float(Xc[v, 2]) for v, _, _ in ox if pid[v] == k)
        for a, b in sw:
            for p, q in ((a, b), (b, a)):
                if pid[p] != k or pid[q] == k or (placed is not None and not placed.get(int(pid[q]), True)):
                    continue
                if Xc[p, 2] >= zb and not (HOLD_SLEEVES and M["names"][int(pid[q])].split(".")[0] in ("sleeve", "top", "under")):
                    continue
                for v in (int(p), int(q)):
                    if v not in seen:
                        seen.add(v)
                        out.append((v, Xc[v].copy(), OPEN_HOLD_W))
    return out


def sleeve_width(M: dict, side: str = ".L", prefixes=("sleeve", "top", "under")) -> float:
    """A sleeve's flat width at its widest band (the biceps line, m): the sum over its pieces on `side` (a two-piece
    sleeve: top + under) of each piece's widest 8 mm band in the pattern (uv)."""
    uv, pid, names = np.asarray(M["uv"]), np.asarray(M["piece"]), list(M["names"])
    tot = 0.0
    for k, nm in enumerate(names):
        if nm.split(".")[0] not in prefixes or not nm.endswith(side):
            continue
        q = uv[pid == k]
        ys = np.linspace(q[:, 1].min(), q[:, 1].max(), 60)
        tot += max((np.ptp(q[np.abs(q[:, 1] - y) < 0.004, 0]) if (np.abs(q[:, 1] - y) < 0.004).sum() > 1 else 0.0)
                   for y in ys)
    return float(tot)


def sleeve_room(under_M: dict, over_M: dict, ease: float = EASE) -> dict:
    """A SLEEVE OVER A SLEEVE (fit round 10): the over garment's sleeve must hold the under one plus one layer all round:
    width >= under width + 2 pi (ease + THICK). Garrett: the jacket's sleeve was drafted from the bare arm (396 mm,
    biceps ease 25 %) over a shirt sleeve of 391: the shirt showed through both upper arms. Returns {"under", "over",
    "need" (mm), "ok"}."""
    u, o = sleeve_width(under_M) * 1000, sleeve_width(over_M) * 1000
    need = u + 2 * math.pi * (ease + THICK) * 1000
    return {"under": round(u, 1), "over": round(o, 1), "need": round(need, 1), "ok": bool(o >= need - 1.0)}


SWING_BELOW = False  # A/B: the whole front stays swung (False: only the lapel above the break; the edge pins open the rest)


def _swing_front(M, X, ox, fast, bsurf):
    """The worn-open start, validation 2: the fronts swung (_swing_open) give the open front EDGE's targets
    (worn_open_edge); the swing itself is kept only above the highest worn-open point (the break: the lapel and the
    neckline the collar is stood on), fading over 3 cm to the relaxed front below it. A whole-front rigid turn also swung
    the side seams out at the hem (Garrett: hem sweep +25 %, waist +6.5 % vs the sim, whose fronts fall open at the
    edge only); below the break the edge pins open the front and the side stays. Returns (X, edge pins or None)."""
    Xs = _swing_open(M, X.copy(), ox, fast, bsurf)
    edge = worn_open_edge(M, Xs, ox, fast=fast) if WORN_EDGE else None
    if SWING_BELOW or edge is None:  # (without the edge pins the whole front stays swung: nothing else opens it)
        return Xs, edge
    pid = np.asarray(M["piece"])
    Xn = X.copy()
    for k in {int(pid[v]) for v, _, _ in ox}:
        zb = max(float(X[v, 2]) for v, _, _ in ox if pid[v] == k)
        sel = pid == k
        w = np.clip((X[sel, 2] - (zb - 0.03)) / 0.03, 0.0, 1.0)[:, None]
        Xn[sel] = X[sel] + w * (Xs[sel] - X[sel])
    return Xn, edge


# A LAPPED CLOSURE IS LAYERED (fit round 21, 2026-10-20). A closure's `over` piece runs past the closing line and LIES ON
# its `under` piece (closures.py): one cloth thickness outside it wherever they overlap, joined only at the fastenings.
# Which side laps is the closure's design key: men's garments lap the wearer's LEFT front (buttonholes, ".L" = +X) over
# the right (buttons), women's the reverse (Aldrich, Metric Pattern Cutting for Menswear: the buttonholes on the left
# front; the shirt placket strips in garments.py follow the same rule). Without it the form relaxed both fronts onto the
# same offset of the body and they passed THROUGH each other across the overlap (Garrett jacket r19a: 75 + 72 crossing
# vertices 315-568 mm below HPS, made in relax1 and kept by every release since; his shirt: 188 + 210, 79-699 mm). An
# intersection-free sim keeps a crossing it starts with, so no release or arrangement could part them.
LAP_LAYER = True
LAP_GAP = THICK  # m: the over piece's least gap off the under piece where they lap (one cloth layer)
LAP_REACH = 0.012  # m: an over vertex laps the under piece where it is within this of its nearest vertex ACROSS (tangentially: ~ the mesh edge; 6 mm missed the 10 mm triangles below the lapel)
LAP_DEPTH = 0.008  # m: ... and at most this far behind or in front of it (further is another layer: 30 mm caught the lapel)


def lap_layers(M: dict, X: np.ndarray, fast=(), skip=None) -> list:
    """Per lapped closure (over and under different pieces): (the over piece's vertices, its triangles, the under
    piece's vertices, its triangles). The vertices of the fastened pairs are left out: the button joins the layers."""
    F, pid, names = np.asarray(M["F"]), np.asarray(M["piece"]), list(M["names"])
    tied = {int(a) for a, _ in fast} | {int(b) for _, b in fast}
    sk = np.zeros(len(pid), bool) if skip is None else np.asarray(skip, bool)
    out = []
    for c in M.get("closures") or []:
        o, u = c.get("over"), c.get("under")
        if not o or not u or o == u or o not in names or u not in names:
            continue
        ko, ku = names.index(o), names.index(u)
        fo = np.array([v for v in np.where((pid == ko) & ~sk)[0] if int(v) not in tied], np.int64)
        fu = np.array([v for v in np.where((pid == ku) & ~sk)[0] if int(v) not in tied], np.int64)
        tv = np.array(sorted(v for v in tied if pid[v] in (ko, ku)), np.int64)
        out.append((fo, F[pid[F[:, 0]] == ko], fu, F[pid[F[:, 0]] == ku], tv))
    return out


LAP_BUTTON = 0.025  # m: a fastening joins the two layers: the parting fades to nothing over this round it


def _lap_w(X, Q, tv) -> np.ndarray:
    """The parting's weight at Q: 0 at a fastened vertex, 1 from LAP_BUTTON away (the button holds the layers
    together; parted to LAP_GAP right up to it, the cloth round the button stood in a 1.5 mm cone: shirt front p99 27 %)."""
    if not len(tv):
        return np.ones(len(Q))
    d, _ = cKDTree(X[tv]).query(Q)
    return np.clip(d / LAP_BUTTON, 0.0, 1.0)


LAP_STEP = 0.001  # m: the most a lapped pair is parted per round (each side half)
LAP_FINAL = False  # the last round all the way (r21a: single vertices jumped up to 9 mm, front.L stretch p99 23 %)


def _lap_side(X, Q, tris, ref):
    """Q's signed distance off the surface of `tris` (outward = away from the body), its normal there, and whether Q laps
    it (within LAP_REACH across, LAP_DEPTH along the normal)."""
    v_ = np.unique(tris)
    ix = -np.ones(len(X), int)
    ix[v_] = np.arange(len(v_))
    S = _Surface(X[v_], ix[tris], ref=ref)
    d, nrm, _ = S.signed(Q)
    i = S.tree.query(Q)[1]
    tang = np.linalg.norm((Q - S.V[i]) - d[:, None] * nrm, axis=1)
    return d, nrm, (tang < LAP_REACH) & (np.abs(d) < LAP_DEPTH)


def _lap_separate(X: np.ndarray, lap, ref, final: bool = False) -> np.ndarray:
    """One round of LAP_LAYER: the over vertices that lap the under piece closer than LAP_GAP (or behind it) move out
    along its outward normal, and the under vertices that lap the over piece closer than LAP_GAP inside it (or in
    front of it) move in, each half the shortfall, at most LAP_STEP per round (the last round all the way: over out,
    then under in, so the result is layered from both sides: a ripple of the under piece pokes through otherwise)."""
    fo, to, fu, tu, tv = lap
    X = X.copy()
    d, nrm, m = _lap_side(X, X[fo], tu, ref)
    m &= d < LAP_GAP
    sh = (LAP_GAP - d[m]) * _lap_w(X, X[fo[m]], tv)
    X[fo[m]] += nrm[m] * (sh if final else np.minimum(0.5 * sh, LAP_STEP))[:, None]
    d, nrm, m = _lap_side(X, X[fu], to, ref)
    m &= d > -LAP_GAP
    sh = (d[m] + LAP_GAP) * _lap_w(X, X[fu[m]], tv)
    X[fu[m]] -= nrm[m] * (sh if final else np.minimum(0.5 * sh, LAP_STEP))[:, None]
    return X


LAP_START = 0.06  # m: at the start, the over piece within this of the under piece is lifted outside it (lap_order)
LAP_LIFT = 0.003  # m: ... to this much further off the body than the under piece's nearest vertex


def lap_order(X: np.ndarray, laps: list, bsurf) -> tuple[np.ndarray, dict]:
    """The start's layer order for each lapped closure: the over piece's vertices within LAP_START of the under piece
    lifted along the body's normal to LAP_LIFT further off the body than the under piece's nearest vertex (fading to
    nothing at LAP_START). The fronts SLIDE across each other into the lap as the form relaxes them: an over front that
    arrives behind the under one is pushed through it by the layering and they weave (Garrett r21: placement over
    23 mm behind, 42-114 crossing vertices left after a per-round separation alone). Returns (X, {lifted, max_mm})."""
    X = X.copy()
    rep = {"lifted": 0, "max_mm": 0.0}
    if bsurf is None:
        return X, rep
    for fo, to, fu, tu, _tv in laps:
        dist, j = cKDTree(X[fu]).query(X[fo])
        near = dist < LAP_START
        if not near.any():
            continue
        db_o, nb_o, _ = bsurf.signed(X[fo[near]])
        db_u, _, _ = bsurf.signed(X[fu[j[near]]])
        lift = np.maximum(db_u + LAP_LIFT - db_o, 0.0) * np.clip(1.0 - dist[near] / LAP_START, 0.0, 1.0)
        X[fo[near]] += nb_o * lift[:, None]
        rep["lifted"] += int((lift > 1e-4).sum())
        rep["max_mm"] = max(rep["max_mm"], round(float(lift.max()) * 1000, 1))
    return X, rep


LAP_FINISH = 16  # rounds of lap_finish at most


def lap_finish(M: dict, X: np.ndarray, laps: list, bsurf) -> tuple[np.ndarray, dict]:
    """The lap's last step: where an edge of the over piece still passes through the under piece's triangles (the
    layering reads vertex to vertex; a ripple of either between its vertices crosses), the crossing vertices of the over
    piece move out along the body's normal and the under piece's in, LAP_STEP each a round, until nothing crosses
    (at most LAP_FINISH rounds; the under piece never inside its EASE off the body). Returns (X, {before, after, rounds})."""
    from . import cloth
    F, pid, names = np.asarray(M["F"]), np.asarray(M["piece"]), list(M["names"])
    X = X.copy()
    rep = {}
    for c in M.get("closures") or []:
        o, u = c.get("over"), c.get("under")
        if not o or not u or o == u or o not in names or u not in names:
            continue
        ko, ku = names.index(o), names.index(u)
        n0 = None
        for r in range(LAP_FINISH + 1):
            vo = np.asarray(cloth._pair_crossing_verts(X, F, pid, ko, ku), np.int64).reshape(-1)
            vu = np.asarray(cloth._pair_crossing_verts(X, F, pid, ku, ko), np.int64).reshape(-1)
            n0 = len(vo) + len(vu) if n0 is None else n0
            if (not len(vo) and not len(vu)) or r == LAP_FINISH or bsurf is None:
                break
            if len(vo):
                _, nb, _ = bsurf.signed(X[vo])
                X[vo] += nb * LAP_STEP
            if len(vu):
                d, nb, _ = bsurf.signed(X[vu])
                X[vu] -= nb * np.clip(d - EASE, 0.0, LAP_STEP)[:, None]
        rep[c.get("name", o)] = {"before": int(n0), "after": int(len(vo) + len(vu)), "rounds": r}
    return X, rep


def lap_gaps(M: dict, X: np.ndarray, body=None) -> dict:
    """Per lapped closure: crossing vertices (cloth._pair_crossing_verts both ways) and the over piece's gap off the
    under piece where it laps it (mm: p01 / p50 / min, n). The gate: crossings 0, min gap >= 0 (no_front_through_front)."""
    from . import cloth
    F, pid, names = np.asarray(M["F"]), np.asarray(M["piece"]), list(M["names"])
    ref = _body_surface(body) if body is not None else None
    out = {}
    for c in M.get("closures") or []:
        o, u = c.get("over"), c.get("under")
        if not o or not u or o == u or o not in names or u not in names:
            continue
        ko, ku = names.index(o), names.index(u)
        cr = len(np.asarray(cloth._pair_crossing_verts(X, F, pid, ko, ku)).reshape(-1)) + \
            len(np.asarray(cloth._pair_crossing_verts(X, F, pid, ku, ko)).reshape(-1))
        ut = F[pid[F[:, 0]] == ku]
        uv_ = np.unique(ut)
        ix = -np.ones(len(X), int)
        ix[uv_] = np.arange(len(uv_))
        S = _Surface(X[uv_], ix[ut], ref=ref)
        Q = X[pid == ko]
        d, nrm, _ = S.signed(Q)
        i = S.tree.query(Q)[1]
        tang = np.linalg.norm((Q - S.V[i]) - d[:, None] * nrm, axis=1)
        m = (tang < LAP_REACH) & (np.abs(d) < LAP_DEPTH)
        g = d[m] * 1000
        out[c.get("name", o)] = {"over": o, "under": u, "crossing": int(cr), "lap_n": int(m.sum()),
                                 "gap_mm": {"min": round(float(g.min()), 2) if len(g) else None,
                                            "p01": round(float(np.percentile(g, 1)), 2) if len(g) else None,
                                            "p50": round(float(np.median(g)), 2) if len(g) else None},
                                 "ok": bool(cr == 0 and (not len(g) or g.min() >= -0.1))}
    return out


def fastened(M: dict, fasten="default") -> list:
    """Vertex pairs of the closures fastened on the form: "default" = every closure whose state is closed, and an open
    front's TOP pair (a jacket on the form at its top button; the break is there); "all"; or a list of
    "closure:mark" names (the over side's mark)."""
    out = []
    for c in M.get("closures") or []:
        pairs = list(zip(c.get("pairs") or [], c.get("v") or []))
        if not pairs:
            continue
        if fasten == "all" or (fasten == "default" and c.get("state") == "closed"):
            out += [v for _, v in pairs]
        elif fasten == "worn_open":  # (worn open: an open front is not held at its top button; closed closures are)
            out += [v for _, v in pairs] if c.get("state") == "closed" else []
        elif fasten == "default" and c.get("name") == "front":
            out.append(pairs[0][1])
        elif isinstance(fasten, (list, tuple)):
            out += [v for (a, _), v in pairs if f"{c['name']}:{a}" in fasten]
    return [tuple(int(x) for x in v) for v in out]


def _band_init(M, B, X, placed):
    """Pieces sewn by one edge and wrapped to the neck / a seam (collars, stands): stood up from the edge they are sewn
    to, continuing the surface across that seam (the neckline's panels continue up the neck). In order: a stand before
    the collar sewn to it."""
    if B is None:
        return X, []
    names = list(M["names"])
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    E = _edges(np.asarray(M["F"]))
    nb = [[] for _ in range(len(uv))]
    for a, b in E:
        nb[a].append(b)
        nb[b].append(a)
    todo = [k for k, nm in enumerate(names)
            if ((B["pieces"].get(nm) or {}).get("wrap") or {}).get("to") in ("neck", "seam")]
    done = []
    for _ in range(4):
        for k in list(todo):
            mine = pid[sw[:, 0]] == k
            other = pid[sw[:, 1]] == k
            pr = np.r_[sw[mine & ~(pid[sw[:, 1]] == k)], sw[other & ~(pid[sw[:, 0]] == k)][:, ::-1]]
            if len(pr):  # sewn to pieces already in place (a stand's top seam to its collar waits for the collar)
                pr = pr[np.array([placed[pid[b]] for b in pr[:, 1]])]
            if not len(pr):
                continue
            a_, b_ = pr[:, 0], pr[:, 1]
            # continuation across the seam at each partner: away from its own piece's inner neighbours
            cont = np.zeros((len(b_), 3))
            for r, b in enumerate(b_):
                inn = [j for j in nb[b] if pid[j] == pid[b] and j not in set(b_)]
                cont[r] = X[b] - (X[inn].mean(0) if inn else X[b])
            # 3D seam tangent from the partner chain ordered along the collar's own uv edge
            sel = np.where(pid == k)[0]
            tr = cKDTree(uv[a_])
            dd, ii = tr.query(uv[sel])
            c_ = uv[a_] - uv[a_].mean(0)
            o = np.argsort(c_ @ np.linalg.svd(c_, full_matrices=False)[2][0])
            tan3 = np.gradient(X[b_][o], axis=0)
            tanuv = np.gradient(uv[a_][o], axis=0)
            inv = np.empty_like(o)
            inv[o] = np.arange(len(o))
            for vi, i, in zip(sel, ii):
                j = inv[i]
                t3 = tan3[j] / (np.linalg.norm(tan3[j]) + 1e-12)
                tu = tanuv[j] / (np.linalg.norm(tanuv[j]) + 1e-12)
                c = cont[i] - t3 * (cont[i] @ t3)
                c /= np.linalg.norm(c) + 1e-12
                du = uv[vi] - uv[a_[i]]
                along = du @ tu
                across = np.linalg.norm(du - along * tu)
                X[vi] = X[b_[i]] + along * t3 + across * c
            placed[k] = True
            todo.remove(k)
            done.append(names[k])
    return X, done


FLAP_OUT_FIRST = True  # _turn_flaps: of the senses that reach the asked turn, the one further outside (False: the old rank)
TURN_TOL = math.radians(20.0)  # how near the asked turn a sense must come to qualify


def _turn_flaps(M, X, folds_, bsurf):
    """Each fold's flap turned about its first row, vertex by vertex in the row's local frame (foot on the row, its
    pattern distance kept): the start the ARAP relax refines. The side that turns toward the outside is tried both
    ways; the one further off the body (or, without a body, the rest's own sense) is kept."""
    uv = np.asarray(M["uv"], float)
    for fd, g, turn in folds_:
        rg = g["rows"][0]
        row = np.asarray(rg["row"])
        allv = np.unique(np.concatenate([np.asarray(r_["v"]) for r_ in g["rows"]] + [np.asarray(r_["row"]) for r_ in g["rows"][1:]]))
        if not len(allv):
            continue
        L = uv[row]
        Q = X[row]
        ab = L[1:] - L[:-1]
        ln2 = np.maximum((ab ** 2).sum(1), 1e-18)
        P = uv[allv]
        t = np.clip(((P[:, None] - L[None, :-1]) * ab[None]).sum(-1) / ln2[None], 0, 1)
        dd = np.linalg.norm(P[:, None] - (L[None, :-1] + t[..., None] * ab[None]), axis=-1)
        j = np.argmin(dd, 1)
        tt = t[np.arange(len(j)), j]
        H = Q[j] + tt[:, None] * (Q[j + 1] - Q[j])
        T3 = Q[j + 1] - Q[j]
        T3 /= np.linalg.norm(T3, axis=1, keepdims=True) + 1e-12
        # in-surface direction toward the flap (from its current positions)
        D = X[allv] - H
        D -= T3 * np.sum(D * T3, 1, keepdims=True)
        dist = dd[np.arange(len(j)), j]
        Dn = D / (np.linalg.norm(D, axis=1, keepdims=True) + 1e-12)
        flat = H + dist[:, None] * Dn
        wa = _fold_fade(M, fd, allv)  # (a fold that runs off turns by its share)
        # the start may already carry the flap partly turned (cloth.place turns folds): turn it by what is left,
        # the candidate whose fold reads closest to the asked turn, then the one further outside
        tot = abs(turn) * len(g["rows"])
        phi0 = fold_turned(M, X, g)
        phi0 = 0.0 if not np.isfinite(phi0) else math.radians(phi0)
        best = None
        for s in (1.0, -1.0):
            for th in {tot, abs(tot - phi0), tot + phi0} if phi0 > 0.05 else {tot}:
                W = H + _rodrigues(flat - H, T3, np.full(len(allv), s * th) * wa)
                Xt = X.copy()
                Xt[allv] = W
                miss = abs(math.radians(np.nan_to_num(fold_turned(M, Xt, g), nan=0.0)) - tot)
                if bsurf is not None:
                    out_ = float(np.mean(bsurf.signed(W)[0]))
                else:
                    out_ = float(np.mean(W[:, 2])) * np.sign(turn)
                # (shirt spike 2026-10-21: both senses reach the asked turn about equally (the dihedral is unsigned), so
                # ranking by the miss first let a mesh change flip a collar's fall INSIDE its stand (e0: the roll +82
                # vs -82 deg). Any sense within TURN_TOL of the asked turn qualifies; of those the one further out wins.)
                if not FLAP_OUT_FIRST:
                    sc = (-round(miss, 1), out_)
                elif miss <= TURN_TOL:
                    sc = (0, out_)
                else:
                    sc = (-1, -miss)
                if best is None or sc > best[0]:
                    best = (sc, W)
        X[allv] = best[1]
    return X


# TWO LAYERS THAT TOUCH (fit round 8, 2026-10-19): real dressing presses the inner garment down where the outer one
# covers it, and the inner shows where the outer doesn't. `assemble(..., over=)` gives a garment the layer OVER it as a
# CEILING: a vertex COVERED by it (its nearest point on the over layer within COVER_LAT sideways, i.e. under its
# surface, not beside its edge) is held at least LAYER_GAP inside it (toward the body); uncovered cloth (an open
# collar's points in a jacket's V) is free. Two orders on the form (layered_fit): "outer_first" fits the over garment on
# the body plus the under layer's allowance (LAYER_ALLOW: its least stand-off + one cloth), then the under garment
# with that fit as its ceiling; "joint" alternates (over on under, under under over) LAYER_ROUNDS times.
# Known answer: tests/test_pattern_form.py test_nested_tubes_inner_pressed_under.
COVER_LAT = 0.006  # m: sideways reach of "covered" (about one mesh edge: past the over layer's edge = uncovered)
COVER_FACING = 0.5  # cos: the over layer's normal against the body's at the point (the same stack)
LAYER_GAP = THICK  # m: the under layer lies at least one cloth thickness inside the over layer where covered
LAYER_ROUNDS = 2
LAYER_STEP = 0.002  # m: the most the over layer pushes an under vertex in one round (the last round: all the way)
LAYER_W = 20.0  # a vertex touching the over layer: its proximal weight (x a free one's 1.0; a neck pin is 200 x FIT_STIFF)
# THE UNDER LAYER IS A FLOOR, NOT A SUGGESTION (C172, garrett jacket fit round 31): the over garment's push off the
# garment under it was a proximal target only (the local step's T), and the lengths won: Garrett's worn-open jacket fit
# ended with 131 vertices through the pressed shirt (fronts 0-300 mm below the top, up to 13 mm; backs / stand / collar at
# the neck), the shirt drawn OUT through the jacket at the shoulders / upper chest (442 shirt vertices > 1 mm outside), and
# styling's shirt floor then fought the solve round after round at the edge of that region (pushes summing to 175 mm a
# vertex in a 20-round relax; threads 7.5 -> 12 %): it "stopped the opening". A muslin can't pass through what is under
# it any more than it can stretch: the misfit must show as strain (the muslin read), not hide in the shirt. So, as the
# ceiling's mirror: the vertices on the under layer (covered(): stacked over it) weigh LAYER_W in the solve and are put
# back at least LAYER_GAP outside it after every round from the seat on (LAYER_STEP a round, the last all the way).
# Known answer: tests/test_pattern_form.py test_tight_outer_tube_lies_over_the_under_one. OPT-IN (False: the old soft
# push): on Garrett's worn-open jacket (f1) it cut the jacket through the shirt 131 -> 18 and the shirt poking out 442 ->
# 118, but moved the roll off the concept (150 / 250: 58 / 47 vs w1h 70 / 58, concept 69 / 64; break 337 vs 379 below
# HPS), opened a sew gap 4.6 mm and grain max 98 %; Joe: covered show-through is culled anyway (C153), so not pursued.
UNDER_FLOOR = __import__("os").environ.get("PF_UNDER_FLOOR", "0") == "1"
# THE FLOOR UNDER A STIFF LAYER WINS, FROM THE START, ON ITS OWN SIDE (canvas s5, C200): with the interfaced cloth's
# hinges in the fit (FIT_BEND_KEYED), the soft push off the shirt (the T target above) lost to the canvas's flat rest:
# Garrett's chest sank behind the shirt in the FIRST relax (46-49 % of the chest vertices, p10 -12 mm) and in the swing
# (75 %, p50 -11 mm), before the C172 floor (from the seat) acts; the keyed fits c1 / c2 / h2 / t1 end 37-56 % behind,
# the unkeyed c0 4-8 %. UNDER_FLOOR_FROM "relax1": the floor acts in every relax. UNDER_FLOOR_SIDE: a vertex behind the
# under layer at the PLACEMENT (a jacket point placed inside the shirt's open collar leaf) is never pushed through it
# from behind (C197's rule at fit time); the rest are kept outside it every round.
UNDER_FLOOR_FROM = __import__("os").environ.get("PF_UNDER_FLOOR_FROM", "seat")
UNDER_FLOOR_SIDE = __import__("os").environ.get("PF_UNDER_FLOOR_SIDE", "1") == "1"
LAYER_FROM = "seat"  # the ceiling acts from this phase on ("relax1": all relaxes; "seat": once made pieces are stood up)


def covered(osurf, X, bsurf=None):
    """(covered mask, signed distance to the over layer (> 0 = outside it), its normals) for points X. With the body
    (bsurf), only where the over layer faces the way the body does at X (> COVER_FACING): the same stack of layers, not
    a jacket sleeve's inside beside the shirt's side seam at the armpit."""
    d, nrm, dist = osurf.signed(X)
    lat = np.sqrt(np.maximum(dist ** 2 - d ** 2, 0.0))
    c = (lat < COVER_LAT) & (d < 0.03) & (d > -0.03)
    if bsurf is not None:
        _, nb, _ = bsurf.signed(X)
        c &= np.sum(nb * nrm, 1) > COVER_FACING
    return c, d, nrm


def assemble(pattern: dict, body=None, under: dict | None = None, ease: float = EASE, fasten="default",
             iters: int = 120, X0: np.ndarray | None = None, attract: float = 0.5, log=None, pressed: bool = True,
             worn_open: dict | None = None, shoulder_pad: dict | None = None, over: dict | None = None,
             bridge: float = 0.0, neck_split: bool | None = None, fit_model: str | None = None,
             plumb_hold: dict | None = None, hang: bool | None = None, bend_w: np.ndarray | None = None) -> dict:
    """The garment assembled on the form (see the module docstring). pattern: a placed garment (cloth.build
    place_only result: "mesh", "X0", "pieces") or {"mesh": M, "X0": start, "pieces": B (optional)}. body: a
    cloth.Body (V, T, at) or None (a free sheet: the fold tests). under: {"V", "F"} of the garment under (the shirt
    under the jacket) or None. worn_open: {point name: offset m} (WORN_OPEN). fit_model: "woven" | "isometric" | None
    (the module default WOVEN / NECK_PIN_W; fit_model_for). plumb_hold: PLUMB_HOLD's form (plumb_hold_for) or None.
    hang: the HANG (supports, not holds; None: HANG_FIELD). bend_w: per vertex bending weight (FIT_BEND_KEYED,
    bending.weights; None: every vertex 1). Returns {"V", "F", "M", "info"}."""
    hang_ = HANG_FIELD if hang is None else bool(hang)
    woven_ = WOVEN if fit_model is None else fit_model == "woven"
    neck_w_ = LEGACY_NECK_PIN_W if fit_model == "isometric" else NECK_PIN_W
    M = pattern["mesh"]
    B = pattern.get("pieces")
    closed_args = dict(body=body, under=under, ease=ease, fasten=fasten, iters=iters, X0=X0, attract=attract,
                       pressed=pressed, shoulder_pad=shoulder_pad, over=over, bridge=bridge,
                       fit_model=fit_model)  # (OPEN_HOLD: the same garment closed)
    X = np.asarray(X0 if X0 is not None else pattern["X0"], float).copy()
    Xplaced = X.copy()  # (the placement: a fold its wrap turned keeps the sense the wrap gave it)
    F = np.asarray(M["F"])
    uv = np.asarray(M["uv"], float)
    pid = np.asarray(M["piece"])
    n = len(X)
    names = list(M["names"])
    if shoulder_pad and body is not None:  # (the pad is on the form, under this garment: see padded_body)
        body = padded_body(body, shoulder_pad)
    bsurf = _body_surface(body) if body is not None else None
    fsurf = bridged_surface(body, float(bridge), float(X[:, 2].min()) - 0.02) if body is not None and bridge > 0 else None
    usurf = _Surface(under["V"], under["F"], ref=bsurf) if under is not None and bsurf is not None else None
    osurf = _Surface(over["V"], over["F"], ref=bsurf) if over is not None and bsurf is not None else None
    ufsurf = usurf  # (UNDER_FLOOR's surface: the under garment's own cloth, not its made pieces (C200: its collar / stand
    # are a thin leaf at the neck; floored on them, the jacket's neck cloth tore, front plain p99 9 -> 18 %, max 100 %))
    if usurf is not None and UNDER_FLOOR and under.get("floor_F") is not None:
        fF_ = np.asarray(under["floor_F"], int)
        iv_ = np.unique(fF_)
        ix_ = -np.ones(len(under["V"]), int)
        ix_[iv_] = np.arange(len(iv_))
        ufsurf = _Surface(np.asarray(under["V"], float)[iv_], ix_[fF_], ref=bsurf)
    ceil_on = [LAYER_FROM == "relax1"]
    uf_on = [UNDER_FLOOR_FROM == "relax1"]  # (UNDER_FLOOR's start; C200)
    uf_side = np.ones(len(X), bool)  # (UNDER_FLOOR_SIDE: the vertices outside the under layer at the placement)
    if UNDER_FLOOR and UNDER_FLOOR_SIDE and usurf is not None:
        cv0_, du0_, _ = covered(ufsurf, X, bsurf)
        uf_side = ~(cv0_ & (du0_ < 0.0))
        # (and only this garment's own cloth: its made pieces (collar, stand) rest on the under garment's made pieces,
        # which are no floor; floored on the shirt's yoke there the jacket's collar 15.7 -> 21.8 %, stand 10 -> 19 %)
        uf_side &= ~np.isin(pid, [names.index(p_) for p_ in (M.get("made") or []) if p_ in names])
    # which face of each piece is its outside (CCW in the pattern = +z normal): from the start's placement
    face_sign = {}
    Nf = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    for k, nm in enumerate(names):
        fk = pid[F[:, 0]] == k
        if bsurf is not None and fk.any():
            c = X[F[fk]].mean(1)
            _, nb_, _ = bsurf.signed(c)
            face_sign[nm] = 1.0 if np.sum(Nf[fk] * nb_) >= 0 else -1.0
        else:
            face_sign[nm] = 1.0
    folds_ = _fold_cells(M, face_sign)
    sw = np.asarray(M["sew"]).reshape(-1, 2)
    fast = fastened(M, "worn_open" if worn_open and fasten == "default" else fasten)
    # buttons on the centre line: a front's closure (cuffs, plackets close where they are)
    cf_fast = [tuple(int(x) for x in v) for c in M.get("closures") or [] if c.get("name") == "front"
               for v in (c.get("v") or []) if tuple(int(x) for x in v) in set(fast)]
    full, cx = _pins(M, X, body, ease, bsurf, under_v=under["V"] if under is not None else None, neck_split=neck_split,
                     neck_w=neck_w_)
    ox = worn_open_pins(M, X, worn_open)
    ox_named = list(ox)  # (the named worn-open points alone: ox gains the edge pins below)
    py = []  # PLUMB_HOLD pins (set before the seat: plumb_seam_pins)
    # 1. collars / stands stood up from their seams; 2. flaps turned
    placed = {k: True for k in range(len(names))}
    if B is not None:
        for k, nm in enumerate(names):
            if ((B["pieces"].get(nm) or {}).get("wrap") or {}).get("to") in ("neck", "seam"):
                placed[k] = False
    edge_free = np.ones(n)  # (the seat's attraction per vertex: faded near a worn-open edge, below)
    edge = None  # (worn open: the front edge's x targets, read on the swung fronts)
    # a first relax of the torso before the bands are stood on it
    E = _edges(F)
    src = np.r_[E[:, 0], E[:, 1]]
    dst = np.r_[E[:, 1], E[:, 0]]
    rest = _rest_edges(M, src, dst, folds_)
    flapv = np.zeros(n, bool)  # vertices of folded-over flaps (one layer further out)
    over = []  # folds turned over onto their base: (flap vertices, base vertices, base triangles)
    over_lay = []  # per fold over entry: it lies on the garment under it past its base (FLAP_LAY)
    over_gap = []  # per over entry: each flap vertex's target gap off its base (THICK; ROLL_GAP: + the roll near the line)
    for fd, g, turn in folds_:
        if abs(turn) * len(g["rows"]) > math.radians(120):
            fv = np.asarray(g["rows"][-1]["v"])
            flapv[fv] = True
            # (a fold that runs off: only the fully turned flap lies on its base; in the fade it is partly turned)
            fv = fv[np.asarray(g["rows"][-1].get("w", np.ones(len(fv)))) > 0.98]
            bv = np.setdiff1d(g["sel"], np.where(g["flap0"])[0])
            bt_ = np.asarray(g["base_tris"])
            if BASE_ACROSS_SEAM and len(bv) and float(np.asarray(g["d0"])[bv].max()) < BASE_NARROW:
                # THE BASE CONTINUES ACROSS A SEAM (fit round 4): a fold close to a seam (a two-piece collar's fall
                # turns 4 mm above its seam on the stand) has almost no base of its own; it lies on the piece sewn
                # there. With the 4 mm strip as its only base, the fall had nothing to lie on or be drawn onto, and
                # where the shoulder pushed it, it stood off (Garrett round 3: 88-112 deg at the neck sides).
                ob = np.zeros(n, bool)
                ob[bv] = True
                oth = sorted({int(pid[b]) for a, b in sw if ob[a] and pid[b] != pid[a]}
                             | {int(pid[a]) for a, b in sw if ob[b] and pid[a] != pid[b]})
                if oth:
                    ov = np.where(np.isin(pid, oth))[0]
                    bv = np.union1d(bv, ov)
                    bt_ = np.r_[bt_.reshape(-1, 3), F[np.isin(pid[F[:, 0]], oth)]]
                if oth and BASE_ACROSS_PRESSED:
                    # ... AND ACROSS A PRESSED SEAM (fit round 17, Joe's notch): where that piece is pressed onto
                    # another fold's turned flap (the stand's end on the lapel's gorge), the flap is base too: the
                    # fall's end runs past the stand's end onto the lapel and lies on it (with only the stand as
                    # base it stood off at the stand's edge: a tab 8-15 mm off, 30 deg out of the lapel's plane)
                    for fd2, g2, t2 in folds_:
                        if fd2 is fd or abs(t2) * len(g2["rows"]) <= math.radians(120):
                            continue
                        f2 = np.zeros(n, bool)
                        f2[np.asarray(g2["rows"][-1]["v"], int)] = True
                        if any((f2[a] and pid[b] in oth) or (f2[b] and pid[a] in oth) for a, b in sw):
                            bv = np.union1d(bv, np.where(f2)[0])
                            bt_ = np.r_[bt_.reshape(-1, 3), F[f2[F].all(1)]]
            over.append((fv, bv, bt_))
            # (FLAP_LAY: folds turned onto the OUTSIDE only; their own flap is not cloth under them)
            over_lay.append(np.asarray(g["flap0"], bool) if float(fd.get("angle", 180.0)) < 180.0 else None)
            gap = np.full(len(fv), THICK)
            if ROLL_GAP and len(g["rows"]) > 1:  # (see ROLL_GAP: the roll's own radius, from the rows' spacing)
                d0 = np.asarray(g["d0"])
                dr_ = [float(np.median(d0[np.asarray(r_["row"])])) for r_ in g["rows"]]
                rad = (dr_[-1] - dr_[0]) / max(len(dr_) - 1, 1) / max(abs(turn), 1e-6)
                s_ = np.maximum(d0[fv] - dr_[-1], 0.0)
                gap = THICK + 2 * rad * np.clip(1.0 - s_ / (math.pi * rad), 0.0, 1.0) ** 2
            over_gap.append(gap)
    if PATCH_ON_BASE:  # (C95: a patch sewn inside one piece, a pocket flap, lies on that piece, not off the body)
        for k, b, pv in patches(M):
            bt_ = F[pid[F[:, 0]] == b]
            over.append((pv, np.where(pid == b)[0], bt_))
            over_gap.append(np.full(len(pv), THICK))
            flapv[pv] = True
    lay = [None] * len(over)  # FLAP_LAY: per fold entry, the garment's cloth its flap may lie on past its own base
    if FLAP_LAY:
        lay_h = FLAP_LAY_REACH * float(np.median(np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)))
        for oi, own in enumerate(over_lay):
            if own is None:
                continue
            own = own.copy()
            own[over[oi][0]] = True
            lv = np.where(~own)[0]  # (every other cloth, other folds' flaps too: a collar's end lies ON the lapel)
            lix = -np.ones(n, int)
            lix[lv] = np.arange(len(lv))
            lt = lix[F[(lix[F] >= 0).all(1)]]
            if len(lt):
                lay[oi] = (lv, lt)
    if FLAP_LAY and FLAP_LAY_SMOOTH and any(l_ is not None for l_ in lay):  # (C127: the flaps' neighbour matrix)
        import scipy.sparse as _sp
        _e = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
        _e = np.r_[_e, _e[:, ::-1]]
        lay_adj = _sp.csr_matrix((np.ones(len(_e)), (_e[:, 0], _e[:, 1])), shape=(n, n))
        lay_adj.data[:] = 1.0
    else:
        lay_adj = None
    laps = lap_layers(M, X, fast, skip=flapv) if LAP_LAYER else []  # (a lapped closure's over piece outside its under piece; turned flaps lie on their own base)
    # off-the-body target per vertex
    off = ease + THICK * flapv
    on_flap = flapv.copy()  # (no seat attraction onto the body: turned flaps + what the press laid on them)
    # FIT: which cells stay ARAP (folds: rows + flaps; made pieces) and the sewn surface's bending
    cellv = np.zeros(n, bool)
    for fd, g, turn in folds_:
        for r_ in g["rows"]:
            cellv[np.asarray(r_["row"], int)] = True
            cellv[np.asarray(r_["v"], int)] = True
    for k in range(len(names)):
        if not placed[k]:
            cellv[pid == k] = True
    arap_e = cellv[src] if FIT else np.ones(len(src), bool)
    if FIT:
        hbar = float(np.mean(np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)))
        kb = FIT_BEND * hbar ** 2
        sw_b = sw[~(cellv[sw[:, 0]] | cellv[sw[:, 1]])] if len(sw) else sw  # (made pieces: not welded)
        Kb, bend_rhs = _fit_bending(M, F, uv, n, sw_b, cellv)
        Kb = kb * Kb
        if bend_w is not None and np.max(bend_w) > 1.0 + 1e-9:  # (FIT_BEND_KEYED: the interfaced cloth's extra
            # stiffness as edge hinges (bending.Bending: saddles cost, unlike the vertex term), flat rest, its weight
            # over plain (w - 1) x FIT_HINGE_W; fold rows / flaps / made pieces (ARAP cells) left out: they keep their rests)
            from . import bending as _bd
            Kb = (Kb + _bd.Bending(F, uv, n, np.maximum(np.asarray(bend_w, float) - 1.0, 0.0), FIT_BEND * FIT_HINGE_W,
                                   skip=cellv).K).tocsr()
    else:
        Kb, bend_rhs, kb = None, None, 0.0
    Wv = None
    if FIT and woven_:  # (WOVEN: the grain-frame triangles: off the fold rows; made pieces stay ARAP)
        wcell = np.zeros(n, bool)
        for fd, g, turn in folds_:
            for r_ in g["rows"]:
                wcell[np.asarray(r_["row"], int)] = True
                if not WOVEN_FLAPS:
                    wcell[np.asarray(r_["v"], int)] = True
        Wv = _woven_setup(M, B, F, E, wcell, skip={k for k in range(len(names)) if not placed[k]})
    nE0 = len(E)
    n_src0 = len(src)
    flapv0 = np.zeros(n_src0, bool)  # (WOVEN_FLAPS: a directed edge whose cell is a flap vertex off the rows)
    if FIT and woven_:
        rowv_ = np.zeros(n, bool)
        flv_ = np.zeros(n, bool)
        for fd, g, turn in folds_:
            for r_ in g["rows"]:
                rowv_[np.asarray(r_["row"], int)] = True
                flv_[np.asarray(r_["v"], int)] = True
        flapv0 = (flv_ & ~rowv_)[src]

    bend_f = 1.0  # (the settle's bending scale, SETTLE_BEND)
    Wk = None  # THREADS FIRST (FIT_THREAD_FIRST): the interfaced triangles' threads capped every round while keyed bending acts
    if FIT_THREAD_FIRST and Wv is not None and bend_w is not None and np.max(bend_w) > 1.0 + 1e-9:
        mk_ = (np.asarray(bend_w, float)[Wv["F"]] > 1.0 + 1e-9).all(1)
        if mk_.any():
            Wk = {"F": Wv["F"][mk_], "q": Wv["q"][mk_], "Dinv": Wv["Dinv"][mk_]}

    def system(wc, sw=sw):
        w = wE
        # each directed cell edge (i, j): w (x_i - x_j - t)^2 -> rows i and j
        Lp = coo_matrix((np.r_[w, w, -w, -w], (np.r_[src, dst, src, dst], np.r_[src, dst, dst, src])), shape=(n, n)).tocsr()
        S = coo_matrix((np.ones(2 * len(sw)), (np.r_[sw[:, 0], sw[:, 1]], np.r_[sw[:, 0], sw[:, 1]])), shape=(n, n))
        So = coo_matrix((-np.ones(2 * len(sw)), (np.r_[sw[:, 0], sw[:, 1]], np.r_[sw[:, 1], sw[:, 0]])), shape=(n, n))
        fa = np.asarray(fast, int).reshape(-1, 2)
        Fs = coo_matrix((np.ones(2 * len(fa)), (np.r_[fa[:, 0], fa[:, 1]], np.r_[fa[:, 0], fa[:, 1]])), shape=(n, n))
        Fo = coo_matrix((-np.ones(2 * len(fa)), (np.r_[fa[:, 0], fa[:, 1]], np.r_[fa[:, 1], fa[:, 0]])), shape=(n, n))
        WS = 400.0 * PK
        A0 = Lp + WS * (S + So) + WS * (Fs + Fo) + diags(wc)
        if Kb is not None:
            A0 = A0 + bend_f * Kb
        dp = np.zeros(n)
        for v, q, w_ in full:
            dp[v] += PK * w_
        dx = np.zeros(n)
        for v, w_ in cx:
            dx[v] += PK * w_
        for v, _, w_ in ox:
            dx[v] += PK * w_
        for a, b in cf_fast:
            dx[a] += PK * 100.0
            dx[b] += PK * 100.0
        dy = np.zeros(n)
        for v, _t, w_, ax_, _a in py:
            if "x" in ax_:
                dx[v] += PK * w_
            if "y" in ax_:
                dy[v] += PK * w_
        Ayz_ = splu((A0 + diags(dp)).tocsc())
        return splu((A0 + diags(dp + dx)).tocsc()), Ayz_, (splu((A0 + diags(dp + dy)).tocsc()) if dy.any() else Ayz_)

    wc = np.full(n, 1.0 if bsurf is not None else 1e-3)
    # a pressed crease holds its angle: the fold rows' cells weigh 1 + PRESS x strength (folds.PRESS, as the sims'
    # hinge bending), else the obstacles (body, the garment under, its own base) open the fold
    from .folds import PRESS
    wE = np.ones(len(src))
    for fd, g, turn in folds_:
        for r_ in g["rows"]:
            if bsurf is not None:  # (a free sheet has no obstacle to open it: plain ARAP is exact there)
                wE[np.isin(src, np.asarray(r_["row"]))] = 1.0 + PRESS * float(fd.get("strength", 1.0))
    PK = FIT_STIFF if FIT else 1.0  # (pins, seams and closures keep their weight relative to the cloth's edges)
    if FIT:
        wE = wE * FIT_STIFF

    if SETTLE or hang_:  # (vertex mass for the settle: lumped pattern area / its mean)
        e1_, e2_ = uv[F[:, 1]] - uv[F[:, 0]], uv[F[:, 2]] - uv[F[:, 0]]
        a_ = 0.5 * np.abs(e1_[:, 0] * e2_[:, 1] - e1_[:, 1] * e2_[:, 0])
        mass = np.zeros(n)
        for c_ in range(3):
            np.add.at(mass, F[:, c_], a_ / 3)
        mass /= max(float(mass.mean()), 1e-12)

    def relax(X, iters, attract=attract, sw_=None, loose=0.0, grav=0.0):
        nonlocal wc, bend_f
        bend_keep = bend_f
        if grav > 0:
            bend_f = SETTLE_BEND
        l0e = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)
        wc_keep = wc
        held = np.zeros(n, bool)
        if grav > 0:
            wc = np.full(n, SETTLE_FREE)
        Ax, Ayz, Ay = system(wc) if sw_ is None else system(wc, sw_)
        fa = np.asarray(fast, int).reshape(-1, 2)
        ccon = np.zeros(n, bool)
        ucon = np.zeros(n, bool)  # (UNDER_FLOOR: the vertices on the under layer)
        drv_ = np.zeros(n, bool)  # (SHEAR_FREE: the vertices something drives: pins, the body in reach, the layers)
        for v_, _, _ in full:
            drv_[v_] = True
        for v_, _, _ in ox:
            drv_[v_] = True
        for v_, _ in cx:
            drv_[v_] = True
        for v_, *_ in py:
            drv_[v_] = True
        drv_pin = drv_.copy()
        ramp_n = max(int(SHEAR_RAMP * iters), 1)
        for it in range(iters):
            if osurf is not None and ceil_on[0] and grav <= 0 and it % 5 == 0:  # TWO LAYERS: the vertices the over
                # layer touches weigh LAYER_W in the solve (contact the solve knows, as the settle's held set): a soft
                # push lost to the lengths (the too-big inner tube stayed round) and a per-vertex projection tore the shirt
                cv_, do_, _ = covered(osurf, X, bsurf)
                c_ = cv_ & (do_ > -LAYER_GAP - 0.001)
                if (c_ != ccon).any():
                    ccon = c_
                    wc = wc_keep + LAYER_W * (ccon | ucon)
                    Ax, Ayz, Ay = system(wc) if sw_ is None else system(wc, sw_)
            if UNDER_FLOOR and usurf is not None and uf_on[0] and grav <= 0 and it % 5 == 0:  # (C172: the vertices
                # on the under layer weigh LAYER_W in the solve, as the ceiling's: contact the solve knows)
                cv_, du_, _ = covered(ufsurf, X, bsurf)
                c_ = cv_ & (du_ < LAYER_GAP + 0.001) & uf_side
                if (c_ != ucon).any():
                    ucon = c_
                    wc = wc_keep + LAYER_W * (ccon | ucon)
                    Ax, Ayz, Ay = system(wc) if sw_ is None else system(wc, sw_)
            if grav > 0 and it and (held != (wc > SETTLE_FREE)).sum() > SETTLE_REFAC:  # (the contact set changed: the
                # held vertices' weight; the solve must know the contact, else everything else falls a step per round
                # and only the touching vertices are put back: the tube read 780 % stretch in 8 rounds)
                wc = np.where(held, SETTLE_HOLD, SETTLE_FREE)
                Ax, Ayz, Ay = system(wc) if sw_ is None else system(wc, sw_)
            # local: per-cell rotation (Kabsch of the rest one-ring onto the current)
            cur = X[src] - X[dst]  # (x_i - x_j) for cell i = src
            Cm = np.zeros((n, 3, 3))
            np.add.at(Cm, src, wE[:, None, None] * rest[:, :, None] * (-cur)[:, None, :])  # rest e_ij = uv_j - uv_i ~ -(x_i - x_j)
            U, s, Vt = np.linalg.svd(Cm)
            R = np.einsum("nji,nkj->nik", Vt, U)  # V U^T
            det = np.linalg.det(R)
            bad = det < 0
            if bad.any():
                Vt2 = Vt[bad].copy()
                Vt2[:, 2] *= -1
                R[bad] = np.einsum("nji,nkj->nik", Vt2, U[bad])
            # global: sum over cells of |x_i - x_j - R_i (-(e_ij))|^2 ; rhs
            Re = np.einsum("nij,nj->ni", R[src], -rest)  # target for x_i - x_j
            if not arap_e.all():  # FIT: an edge at its pattern length along its current direction (isometry)
                ne = ~arap_e
                ln = np.linalg.norm(cur[ne], axis=1, keepdims=True)
                Re[ne] = cur[ne] / np.maximum(ln, 1e-12) * np.linalg.norm(rest[ne], axis=1, keepdims=True)
                if Wv is not None:  # WOVEN: warp / weft held, shear soft (the triangles' targets; see WOVEN)
                    s_it = SHEAR_STIFF if it >= ramp_n else math.exp(math.log(SHEAR_FREE) + (it / ramp_n) * (
                        math.log(SHEAR_STIFF) - math.log(SHEAR_FREE)))  # (SHEAR_RAMP: a transient's shear decays first)
                    sh_t = np.where(drv_[Wv["F"]].any(1), s_it, SHEAR_FREE)  # (SHEAR_FREE: nothing drives it)
                    if SHEAR_YIELD is not None:  # (SHEAR_YIELD: the hysteresis gives where the threads would strain)
                        th_ = np.abs(np.linalg.norm(_woven_grad(Wv, X)[0], axis=1) - 1.0).max(1)
                        sh_t = np.where(th_ > SHEAR_YIELD, np.minimum(sh_t, s_it), sh_t)
                    tg_, has_ = woven_targets(Wv, X, nE0, shear=sh_t)
                    m2 = np.zeros(len(src), bool)
                    m2[:2 * nE0] = np.r_[has_, has_]
                    # (a flap's own cells woven only where something drives them: a free flap keeps its ARAP cells,
                    # as on the isometric fit; woven, a free sheet's pressed flap opened 18 -> 24 deg, C166)
                    fl_drv = np.r_[flapv0 & drv_[src[:n_src0]], np.zeros(max(len(src) - n_src0, 0), bool)]
                    m2 &= ~arap_e | (fl_drv if WOVEN_FLAPS else False)
                    Re[m2] = np.r_[tg_, -tg_][m2[:2 * nE0]]
            Re = wE[:, None] * Re
            b = np.zeros((n, 3))
            np.add.at(b, src, Re)
            np.add.at(b, dst, -Re)
            # proximal / obstacle targets
            T = X.copy()
            if bsurf is not None:
                d, nrm, _ = bsurf.signed(X)
                lo = d < off
                T[lo] += nrm[lo] * (off[lo] - d[lo])[:, None]
                if grav > 0:  # (settle: no attraction; resting cloth is held where it touches)
                    held = held | (d < off + 0.0015)
                da, na_ = d, nrm
                if fsurf is not None and attract > 0:  # BRIDGE: drawn onto the body's offset with its hollows filled
                    # (the union of the body and the filled torso: the nearer surface outside, the filled one inside it)
                    de_, ne_ = fsurf.signed(X)
                    fb_ = de_ < d
                    da, na_ = np.where(fb_, de_, d), np.where(fb_[:, None], ne_, nrm)
                hi = (np.abs(da - off) > 0.002) & (da < 0.06) & (d >= off) & ~on_flap & (grav <= 0)  # (a turned flap lies on its base, not on the body)
                aw_ = attract * (np.clip(na_[hi, 2], 0.0, 1.0) if (SEAT_GRAVITY or (hang_ and HANG_SUPPORT)) else 1.0)
                aw_ = aw_ * edge_free[hi]  # (worn open: the cloth near the open edge is not drawn onto the body)
                if fsurf is not None and BRIDGE_HANG and attract > 0:  # (BRIDGE_HANG: on the torso band, cloth standing OUT of the filled
                    # surface is drawn in only (1 - bridge) as hard: a stiff garment hangs where its lengths put it)
                    aw_ = aw_ * np.where(np.isfinite(de_[hi]) & (da[hi] > off[hi]), 1.0 - float(bridge), 1.0)
                T[hi] -= na_[hi] * (aw_ * (da[hi] - off[hi]))[:, None]
                if loose > 0:  # loose cloth pushed out along its own normal (oriented off the body): ease stands off evenly
                    fn_ = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
                    vn_ = np.zeros_like(X)
                    for c_ in range(3):
                        np.add.at(vn_, F[:, c_], fn_)
                    vn_ /= np.maximum(np.linalg.norm(vn_, axis=1, keepdims=True), 1e-12)
                    vn_ *= np.sign(np.sum(vn_ * nrm, 1) + 1e-12)[:, None]
                    T[hi] += vn_[hi] * loose
                T_att = T.copy()  # (SHEAR_FREE: the targets before the layers / flap bases act; attraction is no obstacle)
                for oi, ((fv, bv, bt), gp) in enumerate(zip(over, over_gap)):  # a flap stays one THICK outside its base
                    if not len(bt):
                        continue
                    ix = -np.ones(n, int)
                    ix[bv] = np.arange(len(bv))
                    ok_ = (ix[bt] >= 0).all(1)
                    srf = _Surface(X[bv], ix[bt[ok_]], ref=bsurf)
                    dfl, nfl, dist = srf.signed(T[fv])
                    if lay[oi] is not None:  # FLAP_LAY: past its base's edge the flap lies on the garment under it
                        dl, nl_, distl = _Surface(X[lay[oi][0]], lay[oi][1], ref=bsurf).signed(T[fv])
                        tang = np.sqrt(np.maximum(distl ** 2 - dl ** 2, 0.0))
                        use = (distl < dist - 1e-4) & (tang < lay_h) & (dl < FLAP_LAY_FAR)
                        if use.any():
                            dfl, nfl, dist = np.where(use, dl, dfl), np.where(use[:, None], nl_, nfl), np.where(use, np.minimum(distl, 0.019), dist)
                    near = (dist < 0.02) & (dfl < gp)
                    # a pressed flap LIES on its base (as the iron left it), in both phases: unheld, a fall stood
                    # off its stand (curved-collar known answer 172 of 180 deg, the free ends flared 20 mm)
                    far = (dist < 0.02) & (dfl > gp + 0.0005) & (dfl < 0.03)
                    cor = np.zeros((len(fv), 3))
                    cor[near] += nfl[near] * (gp[near] - dfl[near])[:, None]
                    cor[far] -= nfl[far] * (FLAP_PULL * (dfl[far] - gp[far]))[:, None]
                    if lay_adj is not None and lay[oi] is not None:  # (C127: the flap moves as cloth)
                        msk = np.zeros(n)
                        msk[fv] = 1.0
                        cnt = (lay_adj @ msk)[fv]
                        for _ in range(int(FLAP_LAY_SMOOTH)):
                            fl_ = np.zeros((n, 3))
                            fl_[fv] = cor
                            nb = (lay_adj @ fl_)[fv]
                            cor = np.where(cnt[:, None] > 0, 0.5 * cor + 0.5 * nb / np.maximum(cnt, 1)[:, None], cor)
                        short = (gp - dfl) - np.sum(cor * nfl, 1)  # (still one THICK out: what the smoothing undid)
                        fix = near & (short > 0)
                        cor[fix] += nfl[fix] * short[fix, None]
                    T[fv] += cor
                if usurf is not None:
                    du, nu, dist = usurf.signed(T)
                    near = (dist < 0.03) & (du < off + 0.001)
                    T[near] += nu[near] * (off[near] + 0.001 - du[near])[:, None]
                if osurf is not None and ceil_on[0]:  # the layer over this one presses it down where it covers it (TWO LAYERS)
                    cv_, do_, no_ = covered(osurf, T, bsurf)
                    cv_ &= do_ > -LAYER_GAP
                    T[cv_] -= no_[cv_] * (do_[cv_] + LAYER_GAP)[:, None]
            if bsurf is not None:  # (SHEAR_FREE: what drives the cloth this round, for the next round's local step)
                drv_ = drv_pin | (d < off + FREE_REACH) | (np.abs(T - T_att).max(1) > 1e-9)
            b += wc[:, None] * T
            if HANG > 0 and bsurf is not None:  # (A/B: the cloth's weight as a constant pull down, m per round)
                b[:, 2] -= wc * HANG
            if grav > 0:  # (settle: the weight as a force, per vertex mass, against the cloth's own stiffness)
                b[:, 2] -= PK * grav * mass
            if bend_rhs is not None:
                b += bend_f * kb * bend_rhs(X)
            bp = b.copy()
            for v, q, w_ in full:
                bp[v] += PK * w_ * q
            bx = bp[:, 0].copy()
            for v, w_ in cx:
                bx[v] += 0.0
            for v, x_, w_ in ox:
                bx[v] += PK * w_ * x_
            by = bp[:, 1].copy()
            for v, t_, w_, ax_, an_ in py:  # PLUMB_HOLD: the hung top (or as it lies); x only outward
                x_, y_ = an_ if an_ is not None else (float(X[t_, 0]), float(X[t_, 1]))
                if "x" in ax_:
                    bx[v] += PK * w_ * (math.copysign(max(abs(float(X[v, 0])), abs(x_)), x_))
                if "y" in ax_:
                    by[v] += PK * w_ * y_
            Xn = np.c_[Ax.solve(bx), Ay.solve(by), Ayz.solve(bp[:, 2])]
            if grav > 0:  # a step never moves a vertex more than SETTLE_STEP (contact can't be tunnelled; the
                # equilibrium is unchanged: there the steps are 0)
                dX = Xn - X
                ln = np.linalg.norm(dX, axis=1, keepdims=True)
                Xn = X + dX * np.minimum(1.0, SETTLE_STEP / np.maximum(ln, 1e-12))
            if grav > 0 and hang_ and Wv is not None:  # HANG: the THREADS capped (the bias still shears)
                Xn = _thread_limit(Wv, Xn, HANG_STRAIN, SETTLE_SWEEPS)
            if Wk is not None:  # THREADS FIRST: the stiff cloth bends only within the shapes its threads allow
                Xn = _thread_limit(Wk, Xn, FIT_THREAD_CAP, FIT_THREAD_SWEEPS)
            if grav > 0:  # strain limit: the weight never stretches an edge past SETTLE_STRAIN (wovens barely give)
                for _ in range(SETTLE_SWEEPS):
                    dv = Xn[E[:, 1]] - Xn[E[:, 0]]
                    ln = np.linalg.norm(dv, axis=1)
                    ex = ln - (1 + (HANG_STRAIN if hang_ else SETTLE_STRAIN)) * l0e
                    m_ = ex > 0
                    if hang_ and Wv is not None:  # (HANG: only the edges no woven triangle limits: fold rows, made pieces)
                        m_ &= Wv["cnt"] == 0
                    if not m_.any():
                        break
                    cor = np.zeros_like(Xn)
                    cnt = np.zeros(n)
                    dd = dv[m_] * (0.5 * ex[m_] / np.maximum(ln[m_], 1e-12))[:, None]
                    np.add.at(cor, E[m_, 0], dd)
                    np.add.at(cor, E[m_, 1], -dd)
                    np.add.at(cnt, E[m_, 0], 1)
                    np.add.at(cnt, E[m_, 1], 1)
                    Xn += cor / np.maximum(cnt, 1)[:, None]
            if grav > 0 and bsurf is not None:  # hard contact: nothing ends a round inside the form / the under layer
                d, nrm, _ = bsurf.signed(Xn)
                lo = d < off
                Xn[lo] += nrm[lo] * (off[lo] - d[lo])[:, None]
                held = held | lo
                if usurf is not None:
                    du, nu, dist = usurf.signed(Xn)
                    near = (dist < 0.03) & (du < off + 0.001)
                    Xn[near] += nu[near] * (off[near] + 0.001 - du[near])[:, None]
                    held |= near
            for lp_ in laps:  # LAP_LAYER: hard, every round (a soft target lost to the lengths: the fronts stayed woven)
                Xn = _lap_separate(Xn, lp_, bsurf, final=LAP_FINAL and it == iters - 1)
            if osurf is not None and ceil_on[0]:  # TWO LAYERS: hard contact under the over layer (a proximal target alone lost to the
                # lengths: the too-big inner tube stayed round, 146 vertices outside the outer), then off the form
                cv_, do_, no_ = covered(osurf, Xn, bsurf)
                cv_ &= do_ > -LAYER_GAP
                # (at most LAYER_STEP per round: projected in one jump, single vertices left their neighbours and the
                # shirt tore everywhere, 2000 edges past 30 % on Garrett)
                Xn[cv_] -= no_[cv_] * np.minimum(do_[cv_] + LAYER_GAP, LAYER_STEP if it < iters - 1 else 1.0)[:, None]
                if bsurf is not None:
                    d, nrm, _ = bsurf.signed(Xn)
                    lo = d < off
                    Xn[lo] += nrm[lo] * (off[lo] - d[lo])[:, None]
            if UNDER_FLOOR and usurf is not None and uf_on[0] and grav <= 0:  # THE UNDER LAYER IS A FLOOR (C172): hard
                # contact over the garment under it, the ceiling's mirror (see UNDER_FLOOR)
                cv_, du_, nu_ = covered(ufsurf, Xn, bsurf)
                cv_ &= (du_ < LAYER_GAP) & uf_side
                Xn[cv_] += nu_[cv_] * np.minimum(LAYER_GAP - du_[cv_], LAYER_STEP if it < iters - 1 else 1.0)[:, None]
            X = Xn
        wc, bend_f = wc_keep, bend_keep
        return X

    info = {}
    tr = TRACE or (lambda *a_: None)
    if laps:  # (LAP_LAYER: the over piece starts outside the under one; see lap_order)
        X, info["lap_order"] = lap_order(X, laps, bsurf)
    tr("placement", X, M)
    if B is not None and not all(placed.values()):
        # the bands' own vertices relax only after they are stood up: first the rest of the garment, WITHOUT the
        # bands' seams (sewn to a band still where the placement left it, a tab out of the back, the neckline was
        # dragged off the neck before the band was stood on it: the curved-collar known answer read 139 of 180 deg)
        unpl = np.array([not placed[k] for k in range(len(names))])
        keep = ~(unpl[pid[sw[:, 0]]] | unpl[pid[sw[:, 1]]]) if len(sw) else np.zeros(0, bool)
        # (worn open: the first relax runs WITHOUT the worn-open pins: with them it dragged the two named points to
        # their offsets, the swing then found nothing left to turn (0 deg) and the front edge between break and hem
        # stayed by CF: Garrett hips gap 99 vs the drape's 178 mm. The swing turns the whole front; the pins settle it.)
        ox_hold, ox = ox, ([] if SWING_FIRST and SWING_UNPINNED else ox)
        X = relax(X, max(20, iters // 3), sw_=sw[keep])
        ox = ox_hold
        tr("relax1", X, M)
        if ox and SWING_FIRST:
            X, edge = _swing_front(M, X, ox, fast, bsurf)
            tr("swing", X, M)
        X, info["stood_up"] = _band_init(M, B, X, placed)
        tr("band_init", X, M)
    elif ox and SWING_FIRST:
        X, edge = _swing_front(M, X, ox, fast, bsurf)
    X = _turn_flaps(M, X, folds_, bsurf)
    tr("turn_flaps", X, M)
    X, sp_pins = open_collar_spread(B, M, body, X)
    if sp_pins and osurf is not None:  # (TWO LAYERS: an open collar's held end under the over layer is held by it;
        # held where the spread put it, outside the jacket, the pins and the jacket tore the shirt collar)
        cv_, do_, _ = covered(osurf, np.array([q for _, q, _ in sp_pins]), bsurf)
        info["open_spread_pins_covered"] = int((cv_ & (do_ > -LAYER_GAP)).sum())
        sp_pins = [p_ for p_, c_ in zip(sp_pins, cv_ & (do_ > -LAYER_GAP)) if not c_]
    if sp_pins:
        full = full + sp_pins
        info["open_spread_pins"] = len(sp_pins)
        tr("spread", X, M)
    if ox and not SWING_FIRST:
        X = _swing_open(M, X, ox, fast, bsurf)
    if ox and WORN_EDGE:  # the swung front edge (lapel line) held open, not just its two named points
        ox = ox + (edge if edge is not None else worn_open_edge(M, X, ox, fast=fast))
        info["worn_edge_v"] = len(ox)
    if ox and WORN_EDGE and EDGE_FREE > 0:
        # an open front HANGS off the body near its edge (its own weight and stiffness: the sim's edge stands forward);
        # drawn onto the body, the edge pins could open it only by sliding the whole front sideways (Garrett: hem sweep
        # +25 %, the side seam 5 cm out). The seat's attraction fades to none at the edge over EDGE_FREE m (pattern).
        from scipy.spatial import cKDTree
        ev = np.array([v for v, _, _ in ox], int)
        for k in {int(pid[v]) for v in ev}:
            sel = np.where(pid == k)[0]
            dd, _ = cKDTree(uv[ev[pid[ev] == k]]).query(uv[sel])
            edge_free[sel] = np.clip(dd / EDGE_FREE, 0.0, 1.0)
            if HANG_FREE and OPEN_HOLD and OPEN_HANG:
                # (fit round 11, Joe: "hopefully there's not a sharp fold here"): a front worn open HANGS from the chest
                # below its break: the body holds it at the shoulders and the chest, not round the waist. Drawn onto the
                # body there while its edge is held open and its seams held closed, the 84 mm the edge moved had nowhere
                # to go but a fin at the front dart (Garrett r11c: the dart seam 73 deg median, max 107; r6 closed 8).
                # Below the break the whole worn-open piece is free of the seat's attraction (still pushed out of the body).
                zb_ = max(float(X[v, 2]) for v, _, _ in ox_named if pid[v] == k) if any(pid[v] == k for v, _, _ in ox_named) else None
                if zb_ is not None:
                    edge_free[sel[X[sel, 2] < zb_]] = 0.0
    holds = []
    if ox and OPEN_HOLD and body is not None and ({int(pid[v]) for v, _, _ in ox}
                                                   - {int(pid[v]) for pr in fast for v in pr}):
        # the worn-open front's seams held where the closed fit puts them (open_seam_holds)
        Xc = assemble(pattern, worn_open=None, **closed_args)["V"]
        # (from the NAMED points only, fit round 11: given ox with the edge pins, the roll line's top set the hold's
        # height, so the shoulder / neck seams were held CLOSED under a turned lapel: the lapel top through its base,
        # Garrett 40-120 mm below the neck point L 129 / R 125 flap vertices vs 45 / 45 unheld. Joe: "the tops of the
        # lapels are embedded in the layer below". HOLD_NAMED False: old.)
        holds = open_seam_holds(M, Xc, ox_named if HOLD_NAMED else ox, placed, fast)
        if ROLL_TURN and CHEST_HOLD:
            # THE CHEST STAYS (fit round 12): the turn field as a start alone did not keep it: the relax carried the
            # chest with the roll line (Garrett r12a: chest drift p90 52 / 54 mm vs r11d 62 / 56). Every vertex of a
            # worn-open front above its break, off its lapel, is held at its closed-fit position, weight (1 - turn) x
            # OPEN_HOLD_W: full on the held seams, none at the roll line. The roll line and the lapel turn freely.
            seen_ = {v for v, _, _ in holds}
            for k in sorted({int(pid[v]) for v, _, _ in ox_named} - {int(pid[v]) for pr in fast for v in pr}):
                wt = roll_turn_weight(M, Xc, k)
                zb_ = max(float(Xc[v, 2]) for v, _, _ in ox_named if pid[v] == k)
                for v in np.where((pid == k) & (Xc[:, 2] > zb_) & (wt < 1.0 - 1e-6))[0]:
                    if int(v) not in seen_:
                        holds.append((int(v), Xc[v].copy(), OPEN_HOLD_W * (1.0 - float(wt[v])) * CHEST_HOLD))
        full = full + holds
        info["open_hold_v"] = len(holds)
    info["turned_deg_start"] = [round(fold_turned(M, X, g), 0) for fd, g, t in folds_]
    # each fold's rest turns the way its flap now lies (a proper rotation fits only one sense)
    for q, (fd, g, turn) in enumerate(folds_):
        row = np.asarray(g["rows"][0]["row"])
        m_ = np.isin(src, row)
        best = None
        for s in (1.0, -1.0):
            r_ = _rest_edges(M, src[m_], dst[m_], [(fd, g, s * abs(turn))])
            # a fold its wrap turned ("in_wrap": a collar's roll) keeps the wrap's sense, read on the placement: read
            # after the turns it flipped with the lapels (2026-10-19: jacket collar 162 deg / 35% row stretch, 178 / 9%
            # in the wrap's sense)
            Xs_ = Xplaced if fd.get("in_wrap") else X
            res = _fit_residual(src[m_], r_, Xs_[src[m_]] - Xs_[dst[m_]], n)
            if best is None or res < best[0]:
                best = (res, s)
        folds_[q] = (fd, g, best[1] * abs(turn))
    rest = _rest_edges(M, src, dst, folds_)
    # a seam between two flaps pressed flat (the collar's end on the lapel's gorge): cross-seam cells, from here on
    ps, pd, pr = _pressed_cells(M, folds_, E) if pressed else (np.zeros(0, int),) * 2 + (np.zeros((0, 3)),)
    if len(ps):
        X_lp = X
        X = _lay_pressed(M, X, folds_)
        if PRESS_CARRIES_LAYERS:  # what the press laid on a turned flap lies on it: not drawn through it onto the body
            on_flap |= np.linalg.norm(X - X_lp, axis=1) > 1e-9
        tr("pressed", X, M)
        src, dst, rest = np.r_[src, ps], np.r_[dst, pd], np.r_[rest, pr]
        wE = np.r_[wE, np.full(len(ps), PRESSED_W)]
        arap_e = np.r_[arap_e, np.ones(len(ps), bool)]
    info["pressed_cells"] = int(len(ps))
    # onto the form (drawn toward the body's offset), then let go: the pattern's lengths decide how far it stands off
    # (a membrane can't resist a pull onto a curved form: held there it shrinks; the ease would read short)
    ceil_on[0] = True
    uf_on[0] = True
    if plumb_hold and body is not None:  # (C181: the side seams on the vertical below their tops, from the seat on)
        py = plumb_seam_pins(M, X, plumb_hold)
        info["plumb_hold_v"] = len(py)
    X = relax(X, iters // 2)
    tr("seat", X, M)
    info["turned_deg_mid"] = [round(fold_turned(M, X, g), 0) for fd, g, t in folds_]
    X = relax(X, iters, attract=0.0, loose=LOOSE_PRESS if LOOSE_ROUND else 0.0)
    tr("let_go", X, M)
    if SETTLE or hang_:  # the cloth's weight with real contact (see SETTLE; HANG_FIELD: the threads capped)
        h_ = float(np.mean(np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)))
        g_, it_ = (HANG_G, HANG_ITERS) if hang_ else (SETTLE_G, SETTLE_ITERS)
        X = relax(X, it_, attract=0.0, grav=g_ * h_ ** 2)
        tr("settle", X, M)
        info["settled"] = {"iters": it_, "g": g_, "hang": bool(hang_)}
    if laps:  # (LAP_LAYER: nothing of the over piece left through the under one)
        X, info["lap_finish"] = lap_finish(M, X, laps, bsurf)
    info["turned_deg"] = [round(fold_turned(M, X, g), 0) for fd, g, t in folds_]
    # report
    l0 = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)
    l1 = np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
    st = l1 / np.maximum(l0, 1e-9) - 1
    info.update({"stretch_pct": {"p50": round(float(np.median(np.abs(st))) * 100, 2),
                                 "p99": round(float(np.percentile(np.abs(st), 99)) * 100, 1),
                                 "max": round(float(np.abs(st).max()) * 100, 1)},
                 "sew_gap_mm": round(float(np.linalg.norm(X[sw[:, 0]] - X[sw[:, 1]], axis=1).max()) * 1000, 2) if len(sw) else 0.0,
                 "fastened": len(fast)})
    if Wv is not None:  # WOVEN: stretch along the grain (an edge across the bias changes length when the cloth shears)
        Fg_ = _woven_grad(Wv, X)[0]
        gs_ = np.abs(np.linalg.norm(Fg_, axis=1) - 1).ravel()
        sh_ = woven_shear_deg(Wv, X)
        info["grain_stretch_pct"] = {"p50": round(float(np.median(gs_)) * 100, 2),
                                     "p99": round(float(np.percentile(gs_, 99)) * 100, 1),
                                     "max": round(float(gs_.max()) * 100, 1)}
        info["shear_deg"] = {"p50": round(float(np.median(sh_)), 1), "p99": round(float(np.percentile(sh_, 99)), 1),
                             "max": round(float(sh_.max()), 1)}
    if py:  # (C181) how far the plumb-held seam vertices ended off their vertical (mm, horizontal)
        def _an(t_, an_):
            return an_ if an_ is not None else (float(X[t_, 0]), float(X[t_, 1]))
        dpl = np.array([np.hypot(X[v, 0] - (math.copysign(max(abs(float(X[v, 0])), abs(_an(t_, an_)[0])), _an(t_, an_)[0])
                                            if "x" in ax_ else X[v, 0]), (X[v, 1] - _an(t_, an_)[1]) if "y" in ax_ else 0.0)
                        for v, t_, w_, ax_, an_ in py if w_ > 0]) * 1000
        info["plumb_off_mm"] = {"p50": round(float(np.median(dpl)), 1), "max": round(float(dpl.max()), 1)}
    if holds:  # how far the held seams ended from the closed fit (mm): the hang's side effect
        dh = np.array([np.linalg.norm(X[v] - q) for v, q, _ in holds]) * 1000
        info["open_hold_drift_mm"] = {"p50": round(float(np.median(dh)), 1), "max": round(float(dh.max()), 1)}
    if ox:
        info["worn_open_mm"] = {k: round(abs(float(X[v, 0])) * 1000, 1) for k, v in M["points"].items()
                                for v_, _, _ in ox if v_ == v}
    hinge = []
    for fd, g, turn in folds_:
        row = np.asarray(g["rows"][0]["row"])
        rs = np.linalg.norm(X[row[1:]] - X[row[:-1]], axis=1) / np.maximum(np.linalg.norm(uv[row[1:]] - uv[row[:-1]], axis=1), 1e-9) - 1
        hinge.append({"piece": fd["piece"], "fold": fd["name"], "deg": round(math.degrees(turn), 0),
                      "row_stretch_pct": round(float(np.abs(rs).max()) * 100, 2), "missing_edges": fd.get("missing_edges", 0)})
    info["folds"] = hinge
    if laps:
        info["laps"] = lap_gaps(M, X, body)
    if bsurf is not None:
        d, _, _ = bsurf.signed(X)
        info["inside_body"] = int((d < 0).sum())
        info["neck_point_mm"] = {k: round(placement_error(X[v], q), 1) for k, v in M["points"].items()
                                 for v_, q, w_ in full if v_ == v and w_ >= 100}
    if usurf is not None:
        du, _, dist = usurf.signed(X)
        info["through_under"] = int(((du < 0) & (dist < 0.01)).sum())
    if osurf is not None:
        cv_, do_, _ = covered(osurf, X, bsurf)
        info["through_over"] = int((cv_ & (do_ > 0)).sum())
        info["covered"] = int(cv_.sum())
    if log:
        log(f"assemble: {info}")
    return {"V": X, "F": F, "M": M, "info": info}


# The form's mesh grading when a garment names none (dress-garrett 2026-10-19: $G/form/place2.py, the recipe the form's
# sheets were judged with): ~5 mm at a lapel / gorge / notch and on collars, ~6 mm at a shirt's neck. Names a draft does
# not have are skipped (sizing). A garment's own "mesh_refine" wins.
FORM_REFINE_LAPEL = [
    {"piece": ["front.L", "front.R"], "h": 0.005, "near": ["break", "lapelPoint", "cfNeck", "hps"], "within": 0.035,
     "blend": 0.04},
    {"piece": ["collar", "under_collar"], "h": 0.005}]
FORM_REFINE_SHIRT = [
    # (C137, shirt spike 2026-10-21: the collar roll's radius is 3 mm; at h 5 mm its half turn spanned 2 triangles and
    # turned as two 90 deg kinks with a flat 9 mm shelf on top; at 2 mm one rounded roll, sections 172 / 169 / 176 deg)
    {"piece": ["collar", "stand"], "h": 0.002},
    {"piece": ["front.L", "front.R"], "h": 0.006, "near": ["cfNeck", "neck", "hps"], "within": 0.04, "blend": 0.04},
    {"piece": "yoke", "h": 0.006, "near": ["neck", "cbNeck", "neck.m"], "within": 0.02}]
UNDER_EASE = 0.003  # m: the innermost layer on the form (the shirt on the skin; form.py's setting); a layer over it EASE


def form_refine(g: dict) -> list:
    """The mesh grading the form uses for garment g: its own "mesh_refine", else the lapel recipe for a design with a
    lapel op, else the shirt recipe."""
    if g.get("mesh_refine"):
        return g["mesh_refine"]
    ops = [o.get("op") for o in ((g.get("design") or {}).get("ops") or []) if isinstance(o, dict)]
    return FORM_REFINE_LAPEL if "lapel" in ops else FORM_REFINE_SHIRT


# AN UNDER LAYER'S FULLNESS LIES DOWN (fit round 22, 2026-10-20; Joe on Garrett r20k: "really tight around his middle,
# that's not how jackets work"). Fitted alone, a shirt keeps its whole ease as radius: Garrett's +109 mm waist stood as a
# smooth tube 17 mm off the body, and the jacket over it (+119 mm over the body, the book's 14 %) lay 1-11 mm over the
# shirt and clung. A shirt worn under a jacket is tucked in; its fullness lies soft against the body (it folds and
# blouses, it doesn't stand off). layered_fit mode "lie": the under garment fitted alone, then its loose cloth laid down
# to at most UNDER_LIE_CAP off the body along the body's normal (made pieces: collars, stands, cuffs, and the cloth rolled
# back at an open neck as they stand; the cloth next to them eased over UNDER_LIE_EASE), then the over garment fitted
# over THAT. The girth the press takes off is compression the form doesn't resolve (fine folds: a sim from this start
# buckles it, its rest is the flat pattern). Known answer: tests/test_pattern_form.py test_under_layer_lies_down.
UNDER_LIE_CAP = 0.008  # m off the body (cloth.UNDER_CAP, the sims' rule for a garment's loose cloth under another)
UNDER_LIE_EASE = 0.03  # m: the cloth beside a made piece eases from as made to laid down over this
UNDER_LIE_GATHER = 0.10  # the most of an edge's standing length the press may take up or add (see lie_under)
UNDER_LIE_ITERS = 40
UNDER_LIE_SMOOTH = 8  # passes evening the press between neighbours
UNDER_LIE_LAP = 0.03  # m: an over front within this of its under front is laid down as far as the under one


def lie_under(M: dict, X: np.ndarray, body, cap: float | None = None, pieces: dict | None = None) -> np.ndarray:
    """The under garment's vertices X with its loose cloth laid down to at most `cap` (UNDER_LIE_CAP) off the body (see
    UNDER_LIE_CAP). Made pieces (M["made"], else the wholly interfaced pieces of `pieces`) and the rows of roll / open-neck
    folds stay as they are; moves are along the body's normal, eased, never closer than 2 mm to the body."""
    from . import cloth as _cloth
    from . import folds as _folds
    cap = UNDER_LIE_CAP if cap is None else float(cap)
    X = np.asarray(X, float)
    bsurf = _body_surface(body)
    d, nrm, _ = bsurf.signed(X)
    names = list(M["names"])
    pid = np.asarray(M["piece"])
    if M.get("made") is not None:
        made_nm = list(M["made"])
    elif pieces is not None and pieces.get("interfaced"):
        made_nm = _cloth.made_pieces(M, _cloth.interfacing(pieces, M))
    else:
        made_nm = []
    made = np.isin(pid, [names.index(nm) for nm in made_nm if nm in names])
    for fd in M.get("folds") or []:
        if fd.get("kind") == "roll" or str(fd.get("name", "")).startswith("open neck"):
            try:
                made[np.asarray(_folds._geom(M, fd)["rows"][0]["v"], np.int64)] = True
                for row in fd["rows"]:
                    made[np.asarray(row, np.int64)] = True
            except Exception:
                pass
    F = np.asarray(M["F"])
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]], np.asarray(M.get("sew", []), int).reshape(-1, 2)], 1), axis=0)

    def avg(f):
        acc, wt = np.zeros(len(X)), np.zeros(len(X))
        np.add.at(acc, E[:, 0], f[E[:, 1]]); np.add.at(wt, E[:, 0], 1.0)
        np.add.at(acc, E[:, 1], f[E[:, 0]]); np.add.at(wt, E[:, 1], 1.0)
        return acc / np.maximum(wt, 1)

    keep = made.astype(float)
    hm = float(np.median(np.linalg.norm(X[F[:, 0]] - X[F[:, 1]], axis=1)))
    for _ in range(max(2, int(round(UNDER_LIE_EASE / max(hm, 1e-4))))):
        keep = np.where(made, 1.0, avg(keep))
    move = np.maximum(d - cap, 0.0) * (1.0 - keep)
    # a lapped closure's two layers move alike (each laid down on its own, both fronts ended on the same offset and
    # crossed: Garrett's shirt fronts 243 + 279 crossing vertices): the over piece near the under one moves as the under
    # piece's nearest vertex does
    pairs = []
    for c in M.get("closures") or []:
        o, u = c.get("over"), c.get("under")
        if o and u and o != u and o in names and u in names:
            fo, fu = np.where(pid == names.index(o))[0], np.where(pid == names.index(u))[0]
            dist, j = cKDTree(X[fu]).query(X[fo])
            pairs.append((fo, fu[j], np.clip(1.0 - dist / UNDER_LIE_LAP, 0.0, 1.0)))
    for _ in range(UNDER_LIE_SMOOTH):
        move = np.where(made, 0.0, 0.5 * move + 0.5 * avg(move))
        for fo, ju, w in pairs:
            move[fo] = w * move[ju] + (1.0 - w) * move[fo]
    move = np.minimum(move, np.maximum(d - 0.002, 0.0))
    # at most UNDER_LIE_GATHER of the cloth's own length taken up between neighbours (a woven gathers that much into soft
    # folds under the layer over it; laid to the cap everywhere, a shirt sleeve that blouses 2-5 cm compressed ~50 %)
    l_ = np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1)
    for _ in range(UNDER_LIE_ITERS):
        Y = X - nrm * move[:, None]
        c = 1.0 - np.linalg.norm(Y[E[:, 0]] - Y[E[:, 1]], axis=1) / np.maximum(l_, 1e-9)
        bad = np.zeros(len(X), bool)
        bad[E[np.abs(c) > UNDER_LIE_GATHER].ravel()] = True
        if not bad.any():
            break
        move[bad] *= 0.85
    return X - nrm * move[:, None]


WAIST_OVER_BODY = 0.10  # C84: a fitted jacket's waist girth at least this over the body's (the book: 14 %, Aldrich ~10-12 cm)
WAIST_OVER_UNDER = 2 * np.pi * EASE  # m: ... and at least the layer ease (EASE all round) over the garment under it


def waist_layers(body_V, under_V, over_V, z: float, concept_w: float | None = None, half: float = 0.005,
                 torso: float = 0.22) -> dict:
    """C84's gate row at the height z (the body's waist): the convex-hull girth (a tape passes over hollows) and the
    front-view width (x extent) of a 2 * half slice of the body, the under garment and the over one (|x| < torso: the arms
    out); the over garment's ease over the body (ok_body: >= WAIST_OVER_BODY) and over the under one (ok_under: >=
    WAIST_OVER_UNDER; under_V None = culled / not modelled: not judged), and its front-view width against the concept's
    (reported, not gated: a worn-open concept's width is the arranged hang's)."""
    from scipy.spatial import ConvexHull

    def g(P):
        if P is None:
            return float("nan"), float("nan")
        P = np.asarray(P, float)
        s_ = P[(np.abs(P[:, 2] - z) < half) & (np.abs(P[:, 0]) < torso)][:, :2]
        if len(s_) < 8:
            return float("nan"), float("nan")
        q = s_[ConvexHull(s_).vertices]
        return float(np.linalg.norm(q - np.roll(q, 1, 0), axis=1).sum()), float(np.ptp(s_[:, 0]))

    (gb, wb), (gu, wu), (go, wo) = g(body_V), g(under_V), g(over_V)
    r = lambda v: None if not np.isfinite(v) else round(v * 1000)  # noqa: E731
    out = {"girth_mm": {"body": r(gb), "under": r(gu), "over": r(go)},
           "width_mm": {"body": r(wb), "under": r(wu), "over": r(wo)},
           "over_body_pct": round(100 * (go / gb - 1), 1), "over_under_mm": r(go - gu)}
    out["ok_body"] = bool(go / gb - 1 >= WAIST_OVER_BODY)
    out["ok_under"] = bool(not np.isfinite(gu) or go - gu >= WAIST_OVER_UNDER)
    if concept_w is not None:
        out["width_vs_concept_mm"] = round(wo * 1000 - concept_w * 1000)
    out["ok"] = out["ok_body"] and out["ok_under"]
    return out


LAYER_ALLOW = None  # m: outer_first's allowance for the under layer (None: UNDER_EASE + THICK, its least stand-off + its cloth)


def layered_fit(ures: dict, ores: dict, mode: str = "outer_first", ug: dict | None = None, og: dict | None = None,
                log=None, iters: int = 120) -> tuple:
    """TWO LAYERS THAT TOUCH on the form (see COVER_LAT): (under result, over result) of assemble, for any under / over
    pair. ures / ores: placed garments (cloth.build place_only results, or {"mesh", "X0", "pieces"} with "body");
    ug / og: their garment dicts (worn_open, shoulder_pad). mode "lie" (UNDER_LIE_CAP) | "outer_first" | "joint" (LAYER_ROUNDS)."""
    ug, og = ug or {}, og or {}
    allow = UNDER_EASE + THICK if LAYER_ALLOW is None else float(LAYER_ALLOW)

    def ua(over=None):
        return assemble(ures, ures.get("body"), ease=UNDER_EASE, worn_open=ug.get("worn_open"), iters=iters,
                        shoulder_pad=ug.get("shoulder_pad"), over=over, log=log, fit_model=ug.get("fit_model"),
                        bridge=bridge_fraction(ug))

    def oa(under=None, ease=EASE):
        return assemble(ores, ores.get("body"), under=under, ease=ease, worn_open=og.get("worn_open"), iters=iters,
                        shoulder_pad=og.get("shoulder_pad"), log=log, fit_model=og.get("fit_model"),
                        bridge=bridge_fraction(og))

    if mode == "lie":  # (UNDER_LIE_CAP: the under layer's fullness laid down, then the over layer fitted over it)
        u = ua(None)
        u = dict(u, V=lie_under(u["M"], u["V"], ures.get("body"), pieces=ures.get("pieces")), V_standing=u["V"])
        o = oa({"V": u["V"], "F": u["F"]})
    elif mode == "outer_first":
        o = oa(None, ease=EASE + allow)
        u = ua({"V": o["V"], "F": o["F"]})
    elif mode == "joint":
        u = ua(None)
        o = None
        for _ in range(max(1, LAYER_ROUNDS)):
            o = oa({"V": u["V"], "F": u["F"]})
            u = ua({"V": o["V"], "F": o["F"]})
    else:
        raise ValueError(f"layered_fit mode {mode!r}")
    return u, o


def on_form(model: str, garment: str, spec: dict | None = None, g: dict | None = None, log=None) -> dict:
    """The garment drafted, meshed with fold lines as edges (form_refine), placed (cloth.build place_only) and
    ASSEMBLED on the form; a layered garment over its under garment (itself on the form first, garment key "over").
    g: the garment dict to use (default the spec's; patched copies for re-drafts). Returns the placed result with
    "A" (assembled vertices), "A_info", and "form_under" (the under garment's on_form result, or None). The pattern
    gate's placement (cloth_check.pattern_gate / pattern_sheet)."""
    import json as _json
    from . import cloth, store
    spec = spec or store.load(model)
    g = _json.loads(_json.dumps(g if g is not None else spec["cloth"][garment]))
    g["mesh_refine"] = form_refine(g)
    # EVERY VISIBLE PIECE IS ON THE FORM (dress-tess s19; Joe "complete pattern, every piece"): construct
    # "sim_collar": false holds the collar out of a SIM (built on the drape after it); the form is not a sim, so it
    # fits the whole draft. Held out here, Tess's coat came onto the form with no collar at all (probe 2026-10-22).
    if isinstance(g.get("construct"), dict) and g["construct"].get("sim_collar") is False:
        g["construct"] = dict(g["construct"], sim_collar=True)
    src, und = form_source(model, garment, spec, g, log=log)
    res = cloth.build(cloth._garment_for_sim(g), src, f"{model}:{garment}", log=lambda *_: None, place_only=True)
    if und is not None and PRESS_UNDER:
        # the under garment as it lies under this one (cloth.pressed, the sims' own rule: loose cloth pressed to at most
        # the garment's under_cap off the body, made pieces as they are). Unpressed, the shirt's own ease held the
        # jacket's sleeves out: o4 top sleeve p50 -3.5 % alone, +3.3 % over the shirt (dress-garrett 2026-10-19 block
        # proportions)
        und = dict(und, A=cloth.pressed({"res": und, "V": und["A"]}, res["body"],
                                        float(g.get("under_cap", cloth.UNDER_CAP)), cloth.under_fall(g)),
                   A_unpressed=und["A"])
    under = {"V": und["A"], "F": und["mesh"]["F"]} if und is not None else None
    if under is not None and und["mesh"].get("made"):  # (UNDER_FLOOR: the floor is the under garment's own cloth, C200)
        uF_, upid_ = np.asarray(und["mesh"]["F"]), np.asarray(und["mesh"]["piece"])
        mk_ = np.isin(upid_[uF_[:, 0]], [und["mesh"]["names"].index(p) for p in und["mesh"]["made"] if p in und["mesh"]["names"]])
        under["floor_F"] = uF_[~mk_]
    from . import bending as _bd
    bw = _bd.weights(res.get("pieces"), res["mesh"], g)  # (the mesh carries them for the styling: STYLE_BEND)
    res["mesh"]["bend_w"] = bw
    keyed = g.get("bend_keyed")
    bw = bw if (FIT_BEND_KEYED if keyed is None else bool(keyed)) else None
    # garment key "worn_open" {point: offset m, "source": why}: the form rule for fronts worn open (worn_open_pins)
    out = assemble(res, res["body"], under=under, ease=EASE if under is not None else UNDER_EASE, log=log,
                   worn_open=g.get("worn_open"), shoulder_pad=g.get("shoulder_pad"), bridge=bridge_fraction(g), neck_split=g.get("neck_split"),
                   fit_model=fit_model_for(model, garment, g), plumb_hold=plumb_hold_for(g),
                   hang=hang_for(g), bend_w=bw)
    res["A"], res["A_info"], res["form_under"] = out["V"], out["info"], und
    res["A_info"]["fit_model"] = fit_model_for(model, garment, g) or ("woven" if WOVEN else "isometric")
    if cloth.expanded(g).get("tucked"):
        res["A"], res["A_info"]["tucked"] = tuck(res, res["A"], cloth.expanded(g))
    return res


def form_source(model: str, garment: str, spec: dict, g: dict | None = None, log=None) -> tuple:
    """(body source, under garment's worn form fit or None): the body a garment is placed on in the form path, the one
    on_form and the pattern gate key the garment's record on (cloth_check.gate_status for a layered garment, fit round
    33: the sim path's model_body looked the under garment's sim / pin up and refused the jacket, so fit_garment never
    matched the gate's record).
    THE UNDER LAYER IS THE UNDER GARMENT'S FORM FIT, AS WORN (muslin default, C168): the over garment is placed on the
    body padded by it, drafted from the tape taken over it, laid on its body without its neck pieces: the sim path's
    steps, given the form fit instead of the under garment's sim (none needed; before, model_body looked the sim up and
    refused the jacket "under_missing" until the shirt was simulated, and a pinned sim stood in for the form's shirt)."""
    from . import cloth
    g = g if g is not None else spec["cloth"][garment]
    ug = cloth.expanded(g).get("over")
    und = on_form(model, ug, spec, log=log) if ug and ug in (spec.get("cloth") or {}) else None
    if und is not None:
        und = under_as_worn(und, spec["cloth"][ug], log=log)
    ures = None if und is None else dict(und, V=np.asarray(und["A"], float), key=f"form:{ug}:{cloth._arr_hash(np.asarray(und['A'], float))}")
    return cloth.model_body(model, spec, g, simulate=False, under=ures), und


def under_as_worn(und: dict, gu: dict, log=None) -> dict:
    """An under garment's form fit as it is worn under another: its kind's wear style (garment_pull.worn_style: a
    shirt without a tie, collar opened) on the closed fit, unless it declares its own worn_open or "style": false (as
    fit_garment styles it). "A" = the worn vertices, "A_closed" the closed fit, "A_style" the op reads (None: no
    style)."""
    from . import cloth, garment_pull as gp
    gx = cloth.expanded(gu)
    if gx.get("worn_open") or gx.get("style", True) is False or und.get("form_under") is not None:
        return dict(und, A_closed=und["A"], A_style=None)
    body = und["body"]
    Xs, info = gp.worn_style(und["mesh"], np.asarray(und["A"], float), (np.asarray(body.V, float), np.asarray(body.T, int)),
                             gx, log=log)
    return dict(und, A=Xs, A_closed=und["A"], A_style=info)


TUCK_CAP = 0.006  # m: tucked cloth below the line lies at most this off the body (a waistband over it: one cloth + ease)
TUCK_BLEND = 0.012  # m: BELOW the line the pull fades in over this (hidden); above the line nothing moves
TUCK_SLIDE_ITERS = 1500  # the hidden cloth's stretched edges given back their length (it slides into the trousers)
TUCK_SLIDE_OVER = 1.0  # (1.8 oscillated on the hollow KAT: max 15.7 %)
TUCK_SOURCE = ("a shirt tucked into trousers is held to the body by the waistband and lies flat under the trousers' "
               "seat and fronts; its fullness below the line is hidden (Garrett concept v8: the shirt runs into the "
               "trousers under the belt). Shirt round 1: no tuck key, the hem flared 15-25 mm off the hips")
# A TUCK LINE IS A LINE, AND TUCKED CLOTH SLIDES (shirt round 3, C109). Round 2's tuck faded the pull in over 30 mm ABOVE
# the line: the visible cloth stepped in by up to 34 mm over 30 mm (a sheared ring that read as a peplum), and the pull
# along the body's normals drew the hidden back into the lumbar hollow with its length held, stretching it vertically:
# 1022 of the 3010 faces over the 5 % start limit (back p99 50 %, max 224 %) were the tuck's, and the arrangement was
# refused at preflight. Real cloth tucked under a waistband is not nailed where it hung: it slides down into the trousers
# (its hem is free). So: nothing moves above the line (the visible fit is the fit; the waistband's top edge makes the
# line), the pull fades in over TUCK_BLEND below it, and the hidden vertices then give their stretched edges back their
# pattern length (Jacobi, the visible ones fixed), held between EASE / 2 and the cap off the body.


def _tuck_slide(X, F, uv, movable, surf, lo: float, cap: float, iters: int | None = None):
    """Hidden cloth given its length back: each edge with a movable end that is longer than its pattern length is
    shortened to it (the movable ends move, Jacobi-averaged), then the movable vertices are held between `lo` and `cap`
    off the body. Compression is left alone (tucked cloth gathers). Returns X."""
    F = np.asarray(F)
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    E = E[movable[E[:, 0]] | movable[E[:, 1]]]
    if not len(E):
        return X
    L0 = np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1)
    ma, mb = movable[E[:, 0]].astype(float), movable[E[:, 1]].astype(float)
    share = ma + mb
    idx = np.where(movable)[0]
    for _ in range(int(TUCK_SLIDE_ITERS if iters is None else iters)):
        D = X[E[:, 1]] - X[E[:, 0]]
        L = np.linalg.norm(D, axis=1)
        ex = np.where(L > L0, (L - L0) / np.maximum(L, 1e-12), 0.0)
        step = D * (ex / np.maximum(share, 1.0))[:, None]
        acc = np.zeros_like(X)
        cnt = np.zeros(len(X))
        np.add.at(acc, E[:, 0], step * ma[:, None])
        np.add.at(acc, E[:, 1], -step * mb[:, None])
        np.add.at(cnt, E[:, 0], ma * (ex > 0))
        np.add.at(cnt, E[:, 1], mb * (ex > 0))
        X = X + TUCK_SLIDE_OVER * acc / np.maximum(cnt, 1.0)[:, None]
        d, N, _ = surf.signed(X[idx])
        X[idx] -= N * (d - np.clip(d, lo, cap))[:, None]
    return X


def tuck(res: dict, X, g: dict, cap: float = TUCK_CAP, blend: float = TUCK_BLEND) -> tuple:
    """TUCKED (design key "tucked": true | {"line": landmark z name | z m, "drop": m, "cap": m}; any garment worn into
    another): the torso cloth below the tuck line (garment_reads.tuck_line_z: default the body's waist_z) is pulled
    along the body's normal to at most `cap` off it, faded in over `blend` BELOW the line (above it nothing moves: the
    line stays a line, C109), then the hidden cloth slides (_tuck_slide: its stretched edges back to their pattern
    length, when the mesh carries F + uv); sleeves, cuffs and collars untouched. Returns (X, info) with info["hidden"] =
    the vertices below the line (covered by the garment over it)."""
    from . import garment_reads
    X = np.asarray(X, float).copy()
    t = g.get("tucked") if isinstance(g.get("tucked"), dict) else {}
    cap = float(t.get("cap", cap))
    lz = garment_reads.tuck_line_z(res["body"], g)
    if lz is None:
        return X, {"line_z": None}
    M = res["mesh"]
    torso = ~garment_reads._mask(M, ("sleeve", "cuff", "collar_stand", "collar_fall"))
    w = np.clip((lz - X[:, 2]) / max(blend, 1e-6), 0.0, 1.0) * torso
    sel = w > 0
    surf = _body_surface(res["body"])
    d, N, _ = surf.signed(X[sel])
    pull = np.maximum(d - cap, 0.0) * w[sel]
    X[np.where(sel)[0]] -= N * pull[:, None]
    hidden = torso & (X[:, 2] < lz)
    slid = None
    if M.get("F") is not None and M.get("uv") is not None and hidden.any():
        X0 = X.copy()
        X = _tuck_slide(X, M["F"], np.asarray(M["uv"], float), hidden & (w >= 1.0), surf, EASE / 2, cap)
        slid = round(float(np.linalg.norm(X - X0, axis=1).max()) * 1000, 1)
    return X, {"line_z": round(lz, 4), "cap_mm": cap * 1000, "moved": int((pull > 1e-4).sum()),
               "max_mm": round(float(pull.max()) * 1000, 1) if len(pull) else 0.0, "slide_max_mm": slid,
               "hidden": np.where(hidden)[0].tolist(), "source": TUCK_SOURCE}


def fold_turned(M: dict, X: np.ndarray, g: dict, reach: float = 0.03) -> float:
    """How far a fold is turned on the form, deg (0 flat, 180 folded right over): the angle between the mean normals of
    the base's and the flap's triangles within `reach` (pattern) of the fold's first row."""
    uv = np.asarray(M["uv"], float)
    row = np.asarray(g["rows"][0]["row"])
    T = np.asarray(g["tris"])
    d = cKDTree(uv[row]).query(uv[T].mean(1))[0]
    fl = np.asarray(g["flap0"])[T].all(1)
    ins = np.zeros(len(uv), bool)
    for r_ in g["rows"]:
        ins[np.asarray(r_["row"])] = True
    near = (d < reach) & (d > HINGE_BAND)  # (past the hairpin at the row: a layer's thickness bends the cells beside it)
    bt, ft = T[near & ~fl & ~ins[T].all(1)], T[near & fl]
    if not len(ft):
        return float("nan")
    # THE BASE ACROSS A SEAM (fit round 4): a fold line close to a seam (a two-piece collar's fall turns 4 mm above its
    # seam on the stand) has no base cloth of its own past the hinge band: the base is the piece sewn there. Read then
    # from that piece's vertices within HINGE_BAND..reach IN 3D (another piece's pattern frame isn't this one's). Left
    # out, every two-piece collar read NaN on the form and its turn went unmeasured (Garrett round 3 [171, 167, nan]).
    xb = None
    if not len(bt):
        k = int(np.asarray(M["piece"])[row[0]])
        pid = np.asarray(M["piece"])
        own_base = np.setdiff1d(np.asarray(g["sel"]), np.where(np.asarray(g["flap0"]))[0])
        sw = np.asarray(M.get("sew") if M.get("sew") is not None else np.zeros((0, 2), int)).reshape(-1, 2)
        ob = np.zeros(len(uv), bool)
        ob[own_base] = True
        oth = {int(pid[b]) for a, b in sw if ob[a] and pid[b] != k} | {int(pid[a]) for a, b in sw if ob[b] and pid[a] != k}
        if not oth:
            return float("nan")
        xb = np.where(np.isin(pid, sorted(oth)))[0]
    # the DIHEDRAL IN SECTION at each row vertex (the base's and the flap's directions away from the row, square to
    # the row's own tangent, from their vertices within HINGE_BAND..reach of it), 180 - it, the median along the row.
    # A collar wraps the neck: normals summed over its whole row cancel round the neck and leave only the lean
    # (dress-garrett 2026-10-19: the curved-collar known answer, ~180 in its CB section, read 163 as one normal sum)
    fvs = np.unique(ft)
    bvs = np.unique(bt) if xb is None else xb
    tb = cKDTree(uv[bvs]) if xb is None else cKDTree(X[bvs])
    tf = cKDTree(uv[fvs])
    # a ROLL's rows are the hinge too: the flap side is read past its last row (+ the band), not inside the arc (fit
    # round 4: the two-piece collar known answer, 174 deg in section, read 151 with the 10 mm arc's points in the flap)
    arc = float(np.median(np.asarray(g["d0"])[np.asarray(g["rows"][-1]["row"])])) if len(g["rows"]) > 1 else 0.0
    out = []
    for j, rv in enumerate(row):
        t = X[row[min(j + 1, len(row) - 1)]] - X[row[max(j - 1, 0)]]
        t /= np.linalg.norm(t) + 1e-12
        dirs = []
        for tr, vs, Y, lo in ((tb, bvs, uv if xb is None else X, HINGE_BAND), (tf, fvs, uv, HINGE_BAND + arc)):
            ii = [i for i in tr.query_ball_point(Y[rv], reach) if np.linalg.norm(Y[vs[i]] - Y[rv]) > lo]
            if not ii:
                break
            D = X[vs[ii]] - X[rv]
            # IN SECTION: the points within SECTION_W of the row vertex's plane (fit round 4: a 30 mm ball round a
            # collar on a 64 mm neck takes points round the curve, their sagitta (~7 mm) tilts the read: the two-piece
            # known answer, 174 deg in section, read 156)
            sl_ = np.abs(D @ t) < SECTION_W
            if sl_.sum() >= 3:
                D = D[sl_]
            D -= np.outer(D @ t, t)
            m = D.mean(0)
            # the side's own direction (its points' principal axis in the section), not the chords from the row
            # vertex: a flap one THICK off its base read ~8 deg open from the chords alone
            if len(D) >= 3:
                a = np.linalg.svd(D - m, full_matrices=False)[2][0]
                m = a if a @ m >= 0 else -a
            dirs.append(m / (np.linalg.norm(m) + 1e-12))
        if len(dirs) == 2:
            out.append(180.0 - math.degrees(math.acos(float(np.clip(dirs[0] @ dirs[1], -1, 1)))))
    if not out:
        return float("nan")
    return float(np.median(out))


def _selftest_placement_error():
    q = np.array([0.061, -0.036, 1.549])
    assert placement_error(q, q) == 0.0
    assert abs(placement_error(q + [0.03, 0, 0], q) - 30.0) < 1e-9
    assert abs(placement_error(q + [0, 0.003, -0.004], q) - 5.0) < 1e-9


@validated.known_answer(_selftest_placement_error)
def placement_error(p, target) -> float:
    """mm between a garment landmark on the form (its neck point) and where the body says it goes."""
    return float(np.linalg.norm(np.asarray(p, float) - np.asarray(target, float)) * 1000.0)
