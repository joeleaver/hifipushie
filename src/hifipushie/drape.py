"""DRAPE BAND: wrapped folds drafted by draping, the pattern maker's method (Joe 2026-10-21, drape band round 1).

A band that wraps a body curve and folds over itself (a shirt collar's stand + fall, a jacket collar, a cuff turned
back, a waistband, a turtleneck, a hem on a curve) is NOT drafted flat and then folded on the form: twelve shirt
rounds and twenty-six jacket rounds failed that way (spring too short then too long, rigid turns, capes, wings, torn
corners). A pattern maker drapes it: describes the WORN shape, builds it on the stand (here: in 3D on the body and the
garment's own cloth under it), and takes the flat piece off it. The flat piece stays the source of truth: it is
generated FROM the worn spec (never the reverse), stored with the worn spec's key, and the pattern gate refuses a piece
whose worn spec has changed since (row drape_band_current).

Interface (garment key "drape": a list of bands; `draft` fills each entry's "out"):
  {"name": "shirt collar",
   "along": ["front.R:cfNeck>neck", "yoke:neck.m>cbNeck>neck", "front.L:neck>cfNeck"],  # the body curve: the garment
        # edges it is sewn to, CB in the middle (the band is draped on the +X half and mirrored: cut on the fold)
   "state": "closed",            # the ONE worn state it is draped in; "target": the other state's sweep (below)
   "layers": [                   # the worn cross-section, inside out; every value {"cb": v, "end": v} or a number (m)
     {"piece": "stand", "kind": "stand", "height": 0.032, "ext": 0.009},      # up the neck from the seam; ext: past CF
     {"piece": "collar", "kind": "fall", "rise": 0.006, "land": {"cb": 0.008, "end": 0.012},
      "end_in": 0.012, "point": 0.0}],   # fall: sewn on the stand top, rises `rise`, turns over (turn of cloth, C43),
        # comes down outside the stand and LIES on the cloth under it to `land` below the neck seam (C125's landing
        # line: "on the layer below at X mm"); end_in: its sewn end short of the stand's CF; point: the tip's offset
        # along the curve from the sewn end (+ toward CF)
   "source": "why these numbers"}
  A cuff: one "fall" layer on a "stand" of height 0 (a turn-back) or a "stand" alone (a band cuff / waistband: height).

`draft(entry, base)` builds the band ON what is under it: base = {"curve": (n, 3) CB -> end, "body": Surf (the neck /
wrist / waist skin), "under": Surf (the garment's own cloth, the fall lies on it), "s_cf": the curve's arc at CF}; the
turn of cloth (C43: the fall's mid-surface one stack out over the stand's, never closer than the form's THICK);
flattens each layer with an ARAP flattener (CB held straight: it is cut on the fold), reports its distortion (edge
strain p99 / max), trues the seams (the stand's neck edge vs the neckline, the collar's sewn edge vs the stand top) and
emits pattern pieces (outline, named points as the design table's piece had them, notches, the fall's roll line as a
fold). `reach(...)`: the same flat piece put on another worn state's sweep (a shirt collar open): its strain; above
REACH_LIMIT the state is out of the piece's reach (an open spread too deep) and is flagged.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import factorized
from scipy.spatial import cKDTree

DRAPE_SOURCE = ("draping (Joe 2026-10-21): a wrapped fold is drafted from its worn shape, built on the stand and "
                "taken off flat (Aldrich, Metric Pattern Cutting for Menswear: shirt collar + stand; Armstrong, "
                "Patternmaking for Fashion Design, draping collars); turn of cloth C43; landing line C125")
SHIRT_DEFAULTS = {  # a shirt's stand + fall (Aldrich two-piece shirt collar; Simon's draft; concept_v8 checklist rows)
    "stand": {"height": 0.032, "ext": 0.009},
    "fall": {"rise": 0.006, "land": 0.008, "end_in": 0.012, "point": 0.0},
    "source": "Aldrich shirt collar: stand 3-3.5 cm at CB, fall covering the stand seam by ~1 cm; FreeSewing Simon "
              "(collar sewn ends ~1.2 cm short of the band's CF); concept_v8 checklist: stand 30-38 mm at CB, fall ~44"}
JACKET_DEFAULTS = {  # tailoring_principles R16-R18: stand ~ 2.5-3 cm, fall 1 cm deeper than the stand + turn of cloth
    "stand": {"height": 0.028, "ext": 0.0},
    "fall": {"rise": 0.0, "land": 0.012, "end_in": 0.0, "point": 0.0},
    "source": "tailoring_principles R16-R18 (stand 25-30 mm, fall = stand + ~10 mm + turn of cloth, outer edge on "
              "the landing path)"}
STAND_TOP_SHORT = 0.004  # m, whole band: its top edge shorter than its neck edge (FreeSewing Simon's band, Garrett r12)
STAND_MODE = "neck"  # round 2: the stand on the NECK (neck_stand). "skin": r1's (flares); "lean": r1 lever 2 (DEAD:
# one lean solved to the top length + a skin floor: stand p99 2.6 -> 13 %, top still 507 vs 475)
REACH_LIMIT = 0.04  # edge strain p99 the same flat piece may take to reach another worn state (a woven shirting's
# working stretch with interfacing: the fit gate's strain limit band, cloth.strain_limit_of ~3-5 %)
GRID = (36, 24)  # (along the half, across) grid nodes per layer
LAY_STEP = 0.0015  # m: the march step over the cloth under the fall
FLAT_ITERS = 80


# ---------------------------------------------------------------- surfaces
class Surf:
    """A triangle surface with exact closest points and OUTWARD face normals (oriented by `out`: a point inside, or
    a callable p -> outward direction, or another Surf whose normals are outward)."""

    def __init__(self, V, F, out=None):
        self.V = np.asarray(V, float)
        self.F = np.asarray(F, int)
        A, B, C = (self.V[self.F[:, i]] for i in range(3))
        N = np.cross(B - A, C - A)
        N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-15
        cen = (A + B + C) / 3
        if out is not None:
            if isinstance(out, Surf):
                _, n2 = out.project(cen)
                ref = n2
            elif callable(out):
                ref = out(cen)
            else:
                ref = cen - np.asarray(out, float)
            N *= np.sign(np.sum(N * ref, 1) + 1e-15)[:, None]
        self.N = N
        self.cen = cen
        self.tree = cKDTree(cen)

    def project(self, P, k: int = 10):
        """-> (closest points, outward normals of their faces)."""
        P = np.atleast_2d(np.asarray(P, float))
        k = min(k, len(self.F))
        _, idx = self.tree.query(P, k=k)
        idx = idx.reshape(len(P), -1)
        A, B, C = (self.V[self.F[idx, i]] for i in range(3))
        Q = _closest_on_tri(P[:, None, :], A, B, C)
        d = np.linalg.norm(Q - P[:, None, :], axis=2)
        j = np.argmin(d, 1)
        r = np.arange(len(P))
        return Q[r, j], self.N[idx[r, j]]

    def signed(self, P):
        Q, N = self.project(P)
        return np.sum((np.atleast_2d(P) - Q) * N, 1), Q, N


def _closest_on_tri(P, A, B, C):
    """Closest points on triangles (Ericson), broadcast over leading axes."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = np.sum(ab * ap, -1), np.sum(ac * ap, -1)
    bp = P - B
    d3, d4 = np.sum(ab * bp, -1), np.sum(ac * bp, -1)
    cp = P - C
    d5, d6 = np.sum(ab * cp, -1), np.sum(ac * cp, -1)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    den = np.where(np.abs(va + vb + vc) < 1e-30, 1e-30, va + vb + vc)
    v = vb / den
    w = vc / den
    Q = A + ab * v[..., None] + ac * w[..., None]
    # edges / vertices
    m = (d1 <= 0) & (d2 <= 0)
    Q = np.where(m[..., None], A, Q)
    m2 = (d3 >= 0) & (d4 <= d3)
    Q = np.where(m2[..., None], B, Q)
    m3 = (d6 >= 0) & (d5 <= d6)
    Q = np.where(m3[..., None], C, Q)
    e = (vc <= 0) & (d1 >= 0) & (d3 <= 0) & ~(m | m2 | m3)
    t = d1 / np.where(np.abs(d1 - d3) < 1e-30, 1e-30, d1 - d3)
    Q = np.where(e[..., None], A + ab * t[..., None], Q)
    e2 = (vb <= 0) & (d2 >= 0) & (d6 <= 0) & ~(m | m2 | m3)
    t2 = d2 / np.where(np.abs(d2 - d6) < 1e-30, 1e-30, d2 - d6)
    Q = np.where(e2[..., None], A + ac * t2[..., None], Q)
    e3 = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0) & ~(m | m2 | m3)
    t3 = (d4 - d3) / np.where(np.abs((d4 - d3) + (d5 - d6)) < 1e-30, 1e-30, (d4 - d3) + (d5 - d6))
    Q = np.where(e3[..., None], B + (C - B) * t3[..., None], Q)
    return Q


# ---------------------------------------------------------------- the worn spec
def _field(v, u):
    """A value along the half: a number, or {"cb": a, "end": b} eased (smoothstep) from CB (u = 0) to the end (1)."""
    if isinstance(v, dict):
        a, b = float(v.get("cb", v.get("end", 0.0))), float(v.get("end", v.get("cb", 0.0)))
        t = np.clip(u, 0, 1)
        t = t * t * (3 - 2 * t)
        return a + (b - a) * t
    return np.full_like(np.asarray(u, float), float(v))


def worn_key(entry: dict) -> str:
    """The worn spec's key: what the flat pieces were generated from (the gate compares it)."""
    k = {kk: entry.get(kk) for kk in ("along", "state", "layers", "turn", "base")}
    k["stand_mode"] = entry.get("stand_mode") or STAND_MODE  # (round 2: the stand's build changed: r1 pieces are stale)
    return hashlib.sha1(json.dumps(k, sort_keys=True, default=str).encode()).hexdigest()[:16]


def turn_of_cloth(fabric: str | None, thick_min: float | None = None) -> dict:
    """C43 from the fabric KB: a made band (2 cloth + interfacing = 3 layers); the fall's mid-surface lies one band
    stack out over the stand's (w), never closer than the form's layer THICK (the solver's own separation)."""
    from . import pattern_jacket as pj
    from . import pattern_form as pf
    t = pj._thick_mm(fabric or "shirting", 0.25) / 1000
    band = 3 * t
    th = pf.THICK if thick_min is None else thick_min
    return {"t_mm": round(t * 1000, 3), "band_mm": round(band * 1000, 3), "w": max(band, th), "lay": max(band, th),
            "source": "C43: turn of cloth from garment_kb fabric thickness; floor pattern_form.THICK"}


# ---------------------------------------------------------------- building the band
def _arc(C):
    return np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]


def _curve_at(C, sC, s):
    """Points on the polyline at arc s (extrapolated along the end tangents past either end)."""
    s = np.asarray(s, float)
    out = np.empty((len(s), 3))
    for d in range(3):
        out[:, d] = np.interp(s, sC, C[:, d])
    t0 = (C[1] - C[0]) / (np.linalg.norm(C[1] - C[0]) + 1e-15)
    t1 = (C[-1] - C[-2]) / (np.linalg.norm(C[-1] - C[-2]) + 1e-15)
    lo, hi = s < 0, s > sC[-1]
    out[lo] = C[0] + s[lo, None] * t0
    out[hi] = C[-1] + (s[hi, None] - sC[-1]) * t1
    return out


def _frames(C, sC, s, body: Surf, up=(0, 0, 1.0), h: float = 0.004):
    P = _curve_at(C, sC, s)
    T = _curve_at(C, sC, s + h) - _curve_at(C, sC, s - h)
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-15
    U = np.asarray(up, float)[None] - np.sum(T * np.asarray(up, float)[None], 1)[:, None] * T
    U /= np.linalg.norm(U, axis=1, keepdims=True) + 1e-15
    return P, T, U


def _stand_dirs(P, T, U, H, body: Surf, floor: float = 0.002):
    """The stand rises from the seam along the neck, at the seam's own stand-off (its ease) from the skin: its
    direction D (unit) and its outward normal O."""
    d0, _, _ = body.signed(P)
    d0 = np.maximum(d0, floor)
    D = U.copy()
    for _ in range(3):
        top = P + np.maximum(H, 0.01)[:, None] * D
        Q, N = body.project(top)
        top = Q + N * d0[:, None]
        D = top - P
        D -= np.sum(D * T, 1)[:, None] * T
        D /= np.linalg.norm(D, axis=1, keepdims=True) + 1e-15
    O = np.cross(T, D)
    _, N = body.project(P + 0.01 * D)
    O *= np.sign(np.sum(O * N, 1) + 1e-15)[:, None]
    return D, O


def neck_axis(C, cb_x: float = 0.0):
    """The neck's axis at its base: the normal of the full neckline loop's best-fit plane (the half mirrored about CB),
    pointing up; -> (axis, centroid). Garrett c0: 25.3 deg forward, the same as the throat / nape profile's lean."""
    C = np.asarray(C, float)
    full = np.r_[C, (C * [-1, 1, 1] + [2 * cb_x, 0, 0])[::-1]]
    c0 = full.mean(0)
    _, _, Vt = np.linalg.svd(full - c0)
    a = Vt[2] * (np.sign(Vt[2][2]) or 1.0)
    return a, c0


def _neck_frame(P, T, a, c0):
    """At seam points P (tangent T): the neck axis made perpendicular to the seam (A) and the outward direction off the
    axis in the stand's plane (Oh)."""
    A = a[None] - np.sum(T * a[None], 1)[:, None] * T
    A /= np.linalg.norm(A, axis=1, keepdims=True) + 1e-15
    Oh = np.cross(T, A)
    rel = P - c0[None]
    rel -= (rel @ a)[:, None] * a[None]
    Oh *= np.sign(np.sum(Oh * rel, 1) + 1e-15)[:, None]
    return A, Oh


def _ray_hits(O, D, V, F, N, facing: float = 0.0):
    """Distance along each ray (O + t D, t > 0) to the first triangle FACING it (D . N < -facing); inf when none."""
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    e1, e2 = B - A, C - A
    out = np.full(len(O), np.inf)
    for i in range(len(O)):
        d = D[i]
        front = (N @ d) < -facing
        if not front.any():
            continue
        p = np.cross(d[None], e2[front])
        det = np.sum(e1[front] * p, 1)
        ok = np.abs(det) > 1e-14
        inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
        tv = O[i][None] - A[front]
        u = np.sum(tv * p, 1) * inv
        q = np.cross(tv, e1[front])
        v = (q @ d) * inv
        t = np.sum(e2[front] * q, 1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)
        if hit.any():
            out[i] = float(t[hit].min())
    return out


NECK_FACING = 0.3  # the skin a top's ray counts must face it (D . N < -0.3): the jaw's underside, grazed by a ray in
# toward the axis, is not the neck (Garrett d1's flare); the nape's hollow (normals back and down) still is
NECK_BACK = 0.012  # m: the ray starts this far outside the top, so a top inside the skin reads negative
NECK_SMOOTH = 15  # samples (of 61 along the half): the lean's moving average (r2: 5 -> 15: stand p99 0.47 -> 0.17 %, collar 2.46 -> 2.23; an interfaced band does not follow every bump of the neck)


def neck_stand(C, sC, s_cf, ss, H, body: "Surf", gap=None, band: float = 0.0015, cb_x: float = 0.0,
               lean_lo: float = -0.35, lean_hi: float = 0.7, smooth: int | None = None) -> dict:
    """The stand's lean in toward the neck per seam sample (ss: arc from CB, H: height there): the top at H along the
    neck axis (made perpendicular to the seam), leaned in by lambda so its inner face is `gap` off the NECK, measured by a
    ray in toward the axis against neck faces only. gap None: the seam's own stand-off (a band parallel to the neck).
    -> {"axis", "c0", "lean" (rad, smoothed), "clear_mm" (achieved top clearance), "seam_off_mm", "top_body_mm"}."""
    a, c0 = neck_axis(C, cb_x)
    P = _curve_at(C, sC, ss)
    T = _curve_at(C, sC, ss + 0.004) - _curve_at(C, sC, ss - 0.004)
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-15
    A, Oh = _neck_frame(P, T, a, c0)
    hmax = float(np.max(H)) + 0.02
    ax_h = (body.cen - c0) @ a
    rel = body.cen - c0 - ax_h[:, None] * a
    pick = (ax_h > float(((P - c0) @ a).min()) - 0.02) & \
           (ax_h < float(((P - c0) @ a).max()) + hmax) & (np.linalg.norm(rel, axis=1) < 0.15)
    Fn, Nn = body.F[pick], body.N[pick]
    # the seam's own stand-off from the neck (same ray, from the seam)
    seam_off = _ray_hits(P + NECK_BACK * Oh, -Oh, body.V, Fn, Nn, NECK_FACING) - NECK_BACK
    want = np.where(np.isfinite(seam_off), seam_off, np.nan) if gap is None else \
        np.full(len(ss), 0.0) + _field(gap, ss / max(s_cf, 1e-9)) + 0.5 * band

    def clear(lam):
        # (signed: the ray starts NECK_BACK outside the top; no hit = inside the skin (-1) or no neck in reach (inf))
        D = np.cos(lam)[:, None] * A - np.sin(lam)[:, None] * Oh
        top = P + H[:, None] * D
        c = _ray_hits(top + NECK_BACK * Oh, -Oh, body.V, Fn, Nn, NECK_FACING) - NECK_BACK
        miss = ~np.isfinite(c)
        if miss.any():
            sd, _, _ = body.signed(top[miss])
            c[miss] = np.where(sd < 0, -1.0, np.inf)
        return c
    lo, hi = np.full(len(ss), lean_lo), np.full(len(ss), lean_hi)
    for _ in range(22):
        m = 0.5 * (lo + hi)
        c = clear(m)
        far = c > np.nan_to_num(want, nan=-1.0)  # (no neck in reach, or still too far: lean further in)
        lo, hi = np.where(far, m, lo), np.where(far, hi, m)
    lam = 0.5 * (lo + hi)
    nohit = ~np.isfinite(clear(lam)) | np.isnan(want)
    if nohit.all():
        lam[:] = 0.0
    elif nohit.any():
        lam[nohit] = np.interp(ss[nohit], ss[~nohit], lam[~nohit])
    smooth = NECK_SMOOTH if smooth is None else smooth
    if smooth > 1:
        k = np.ones(smooth) / smooth
        h = smooth // 2  # (CB: mirrored, the band is cut on the fold, so its lean is even about CB; CF: held)
        lam = np.convolve(np.r_[lam[1:h + 1][::-1], lam, np.full(h, lam[-1])], k, mode="valid")
    D = np.cos(lam)[:, None] * A - np.sin(lam)[:, None] * Oh
    top = P + H[:, None] * D
    sd, _, _ = body.signed(top)
    return {"axis": a, "c0": c0, "lean": lam, "clear_mm": np.round(clear(lam) * 1000, 1), "seam_off_mm":
            np.round(seam_off * 1000, 1), "top_body_mm": np.round(sd * 1000, 1), "n_faces": int(pick.sum()),
            "tilt_deg": round(float(np.degrees(np.arctan2(-a[1], a[2]))), 1)}


def _lay(start, dir0, length, under: Surf, off: float, step: float = LAY_STEP, n_out: int = 2):
    """March `length` over the under surface (at `off` out of it) from `start`, heading `dir0` and keeping the
    heading in the surface's tangent plane (a geodesic-ish lie): -> (k, 3) points (start excluded)."""
    pts = []
    p = np.asarray(start, float)
    d = np.asarray(dir0, float)
    left = float(length)
    while left > 1e-6:
        h = min(step, left)
        q = p + h * d
        Q, N = under.project(q)
        q = Q[0] + N[0] * off
        stepv = q - p
        L = np.linalg.norm(stepv)
        if L < 1e-9:
            break
        q = p + stepv * (h / L)  # (keep the arc exact)
        dn = q - p
        dn -= np.dot(dn, N[0]) * N[0]
        d = 0.5 * d + 0.5 * dn / (np.linalg.norm(dn) + 1e-15)
        d /= np.linalg.norm(d) + 1e-15
        pts.append(q)
        p = q
        left -= h
    return np.asarray(pts).reshape(-1, 3)


def _poly_at(S, a):
    """Points at arc a along polyline S (clamped)."""
    sS = _arc(S)
    a = np.clip(np.atleast_1d(np.asarray(a, float)), 0, sS[-1])
    return np.stack([np.interp(a, sS, S[:, d]) for d in range(3)], 1), sS[-1]


def _sections(entry, base, turn):
    """Per-layer section builders: layer -> f(s array, u array) -> list of (k,3) section polylines + their lengths."""
    C = np.asarray(base["curve"], float)
    sC = _arc(C)
    s_cf = float(base.get("s_cf", sC[-1]))
    body, under = base["body"], base.get("under") or base["body"]
    layers = entry["layers"]
    st = next((L for L in layers if L.get("kind") == "stand"), None)

    # THE STAND ON THE NECK (drape band round 2, C131): a stand is a near-vertical band LEANING IN toward the neck: it
    # rises from the seam along the neck's axis (the neckline plane's normal: the neck base) and its top sits `gap` off
    # the NECK (the band's inner face; ray in toward the axis, neck faces only), so its top edge comes out shorter than
    # its neck edge wherever the seam stands further off. Following the nearest skin it flared: at Garrett's front the
    # nearest skin to the top was the jaw's underside (normals pointing down), not the neck (d1: top 531 vs neck 474).
    stand_mode = str(entry.get("stand_mode") or STAND_MODE)
    ss_ = np.linspace(0, s_cf, 61)
    H_ = _field(st.get("height", 0.0), ss_ / max(s_cf, 1e-9)) if st else np.zeros(len(ss_))
    neck = None
    if st and stand_mode == "neck" and np.max(H_) > 0 and base.get("lean") is not None:
        # (another worn state of the same band, e.g. open: the closed drape's lean, not a new gap solve: an open
        # neckline's fronts swing off the neck and the band goes with them)
        a_, c0_ = neck_axis(C, float(base.get("cb_x", 0.0)))
        lq = np.asarray(base["lean"], float)
        neck = {"axis": a_, "c0": c0_, "lean": np.interp(ss_ / max(s_cf, 1e-9), np.linspace(0, 1, len(lq)), lq),
                "clear_mm": np.full(len(ss_), np.nan), "seam_off_mm": np.full(len(ss_), np.nan),
                "top_body_mm": np.full(len(ss_), np.nan), "n_faces": 0,
                "tilt_deg": round(float(np.degrees(np.arctan2(-a_[1], a_[2]))), 1)}
    elif st and stand_mode == "neck" and np.max(H_) > 0:
        neck = neck_stand(C, sC, s_cf, ss_, H_, body, gap=st.get("gap"), band=float(turn.get("band_mm", turn["w"] * 1000)) / 1000,
                          cb_x=float(base.get("cb_x", 0.0)))
    if neck is not None:
        lam_ = neck["lean"]
        a_ax = neck["axis"]
    # (the old modes: "skin" = the seam's stand-off along the nearest skin (r1, flares); "lean" = one lean solved to a
    # top length (r1 lever 2, dead: p99 13 %))
    want = (1.0 - float((st or {}).get("top_short", STAND_TOP_SHORT)) / max(2 * s_cf, 1e-9))
    lean = 0.0
    if stand_mode == "lean" and st and np.max(H_) > 0:
        P_, T_, U_ = _frames(C, sC, ss_, body)
        O_ = np.cross(T_, U_)
        _, Nb_ = body.project(P_ + 0.01 * U_)
        O_ *= np.sign(np.sum(O_ * Nb_, 1) + 1e-15)[:, None]

        def top_ratio(lean):
            D_ = np.cos(lean) * U_ - np.sin(lean) * O_
            top = P_ + H_[:, None] * D_
            return float(np.sum(np.linalg.norm(np.diff(top, axis=0), axis=1)) / max(s_cf, 1e-9))
        lo, hi = -0.6, 0.6
        for _ in range(40):
            m_ = 0.5 * (lo + hi)
            lo, hi = (m_, hi) if top_ratio(m_) > want else (lo, m_)
        lean = 0.5 * (lo + hi)

    def stand_geom(s):
        u = np.clip(s / s_cf, 0, 1)
        H = _field(st.get("height", 0.0), u) if st else np.zeros(len(s))
        P, T, U = _frames(C, sC, s, body)
        if neck is not None:
            A_, Oh = _neck_frame(P, T, a_ax, neck["c0"])
            lam = np.interp(s, ss_, lam_)  # (constant past either end: the band's extension past CF)
            D = np.cos(lam)[:, None] * A_ - np.sin(lam)[:, None] * Oh
            O = np.cross(T, D)
            O *= np.sign(np.sum(O * Oh, 1) + 1e-15)[:, None]
            return P, T, D, O, H
        if stand_mode != "lean":  # ("skin": the stand at the seam's own stand-off along the skin)
            D, O = _stand_dirs(P, T, U, H, body)
            return P, T, D, O, H
        O = np.cross(T, U)
        _, Nb = body.project(P + 0.01 * U)
        O *= np.sign(np.sum(O * Nb, 1) + 1e-15)[:, None]
        D = np.cos(lean) * U - np.sin(lean) * O
        top = P + H[:, None] * D
        sd, Q, N = body.signed(top)
        low = sd < 0.002
        if low.any():
            top[low] = Q[low] + N[low] * 0.002
            D = top - P
            D /= np.linalg.norm(D, axis=1, keepdims=True) + 1e-15
            O = np.cross(T, D)
            O *= np.sign(np.sum(O * Nb, 1) + 1e-15)[:, None]
        return P, T, D, O, H

    def stand_sec(s):
        P, T, D, O, H = stand_geom(s)
        k = 12
        return [(P[i][None] + np.linspace(0, H[i], k)[:, None] * D[i][None], None) for i in range(len(s))]

    def fall_sec(L):
        def f(s):
            P, T, D, O, H = stand_geom(s)
            u = np.clip(s / s_cf, 0, 1)
            rise = _field(L.get("rise", 0.0), u)
            land = _field(L.get("land", 0.01), u)
            w, lay = turn["w"], turn["lay"]
            out = []
            for i in range(len(s)):
                top = P[i] + H[i] * D[i]
                # where the edge lands: `land` down the cloth under it from the neck seam, one lay out of it
                ly = _lay(P[i], -D[i], land[i], under, lay)
                land_pt = ly[-1] if len(ly) else P[i] + w * O[i]
                # the fall is a ruled surface from its roll line straight to its landing line (a cone where the body
                # is round), and the collar's band above the stand is its MIRROR across the roll (a curved fold of one
                # flat piece: both sides meet the crease at the same geodesic curvature, so the band flares out as
                # the fall does). Hugging the stand down to the seam and then the shoulders, or a band standing
                # straight up into a flared fall, is no flat piece (KAT: 6-11 % strain)
                tilt = 0.0
                for _ in range(4):
                    rdir = math.sin(tilt) * O[i] + math.cos(tilt) * D[i]
                    crease = top + rise[i] * rdir  # (the roll: one crease of the mid-surface; its hairpin is the extra below)
                    gv = land_pt - crease
                    gO, gD = float(gv @ O[i]), float(gv @ D[i])
                    tilt = max(0.0, math.atan2(gO, max(-gD, 1e-9)))
                band = top[None] + np.linspace(0, 1, 6)[1:, None] * (crease - top)[None]
                # the turn of cloth (C43): round its hairpin (diameter w) the fall spends (pi / 2 - 1) w more than a
                # sharp crease; it is cut that much deeper so its edge still lands where asked
                gl = land_pt - crease
                gl /= np.linalg.norm(gl) + 1e-15
                extra = (0.5 * math.pi - 1.0) * w
                dn = crease[None] + np.linspace(0, 1, 16)[1:, None] * (land_pt + extra * gl - crease)[None]
                out.append((np.concatenate([top[None], band, dn]), float(np.linalg.norm(crease - top))))
            return out
        return f

    secs = {L["piece"]: (stand_sec if L.get("kind") == "stand" else fall_sec(L)) for L in layers}
    if neck is not None:
        secs["_neck"] = {"tilt_deg": neck["tilt_deg"], "n_faces": neck["n_faces"],
                         "lean_deg": {f"{int(100 * u)}%": round(float(np.degrees(np.interp(u * s_cf, ss_, neck["lean"]))), 1)
                                      for u in (0, 0.25, 0.5, 0.75, 1.0)},
                         "seam_off_mm": {f"{int(100 * u)}%": float(np.interp(u * s_cf, ss_, neck["seam_off_mm"]))
                                         for u in (0, 0.25, 0.5, 0.75, 1.0)},
                         "top_clear_mm": {f"{int(100 * u)}%": float(np.interp(u * s_cf, ss_, neck["clear_mm"]))
                                          for u in (0, 0.25, 0.5, 0.75, 1.0)},
                         "top_body_min_mm": float(np.min(neck["top_body_mm"])), "lean": neck["lean"].tolist()}
    return secs, sC, s_cf


def _layer_domain(L, s_cf, s_end):
    """The layer's half-domain in (s, along-section fraction): s from CB (0) to its end line, which runs from
    (s_bot, v=0) to (s_top, v=1)."""
    if L.get("kind") == "stand":
        return s_cf + float(L.get("ext", 0.0)), s_cf
    e = s_cf - float(L.get("end_in", 0.0))
    return e, e + float(L.get("point", 0.0))


def build(entry: dict, base: dict, fabric: str | None = None, grid=GRID, rows: dict | None = None) -> dict:
    """The band built in 3D on what is under it: {piece: {"X": (nv, nu, 3), "s": (nv, nu), "a": (nv, nu), "cf_u"}}."""
    turn = dict(entry.get("turn") or turn_of_cloth(fabric))
    secs, sC, s_cf = _sections(entry, base, turn)
    nu, nv = grid
    out = {}
    for L in entry["layers"]:
        s_bot, s_top = _layer_domain(L, s_cf, sC[-1])
        uu = np.linspace(0, 1, nu)
        if L.get("kind") == "stand" and s_bot > s_cf + 1e-6:  # a node at CF on the bottom edge (the notch)
            uc = s_cf / s_bot
            k = int(np.argmin(np.abs(uu - uc)))
            k = min(max(k, 1), nu - 2)
            uu = np.r_[np.linspace(0, uc, k + 1), np.linspace(uc, 1, nu - k)[1:]]
        f = secs[L["piece"]]
        # rows: a fall's are knotted at its crease (the roll): a row ON the crease, the band's rows below it
        probe = f(np.array([0.0, s_bot]))
        if rows and L["piece"] in rows:  # (another state of the same piece: the same rows)
            kc = rows[L["piece"]]
        elif probe[0][1] is not None:
            frac = float(np.mean([pk / _arc(pp)[-1] for pp, pk in probe]))
            kc = int(np.clip(round(frac * (nv - 1)), 1, nv - 3)) if frac > 0.02 else None
        else:
            kc = None
        vv = np.linspace(0, 1, nv)
        S = (uu[None, :] * (s_bot + (s_top - s_bot) * vv[:, None]))  # (nv, nu)
        X = np.zeros((nv, nu, 3))
        A = np.zeros((nv, nu))
        for j in range(nu):
            polys = f(S[:, j])
            for i in range(nv):
                pp, pk = polys[i]
                tot = _arc(pp)[-1]
                if kc is None:
                    a_ = vv[i] * tot
                elif i <= kc:
                    a_ = pk * i / kc
                else:
                    a_ = pk + (tot - pk) * (i - kc) / (nv - 1 - kc)
                Pq, _ = _poly_at(pp, a_)
                X[i, j] = Pq[0]
                A[i, j] = a_
        out[L["piece"]] = {"X": X, "s": S, "a": A, "kind": L.get("kind"), "s_cf": s_cf, "u": uu, "v": vv, "crease_row": kc}
    return {"layers": out, "turn": turn, "s_cf": s_cf, "curve_len": float(sC[-1]), "neck": secs.get("_neck")}


# ---------------------------------------------------------------- flattening
def grid_tris(nv, nu):
    I = np.arange(nv * nu).reshape(nv, nu)
    a, b, c, d = I[:-1, :-1].ravel(), I[:-1, 1:].ravel(), I[1:, 1:].ravel(), I[1:, :-1].ravel()
    return np.r_[np.c_[a, b, c], np.c_[a, c, d]]


def _edges(F):
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]
    E.sort(1)
    return np.unique(E, axis=0)


def strain(V3, U2, F):
    """Edge strain of a flat piece against a 3D state: (l3 / l2 - 1) per edge."""
    E = _edges(F)
    l3 = np.linalg.norm(V3[E[:, 0]] - V3[E[:, 1]], axis=1)
    l2 = np.linalg.norm(U2[E[:, 0]] - U2[E[:, 1]], axis=1)
    return l3 / np.maximum(l2, 1e-12) - 1


def _lscm(F, loc, n, pins: dict) -> np.ndarray:
    """Least-squares conformal map with pinned vertices {index: (u, v)}."""
    A2 = np.abs(loc[:, 1, 0] * loc[:, 2, 1] - loc[:, 1, 1] * loc[:, 2, 0])  # (2 x area)
    s = 1.0 / np.sqrt(np.maximum(A2, 1e-20))
    rows, cols, vr, vi = [], [], [], []
    for c in range(3):
        j, k = (c + 1) % 3, (c + 2) % 3
        W = (loc[:, k] - loc[:, j]) * s[:, None]  # W_c = (x_k - x_j) + i (y_k - y_j)
        rows.append(np.arange(len(F)))
        cols.append(F[:, c])
        vr.append(W[:, 0])
        vi.append(W[:, 1])
    rows, cols, vr, vi = (np.concatenate(a) for a in (rows, cols, vr, vi))
    Mr = sparse.coo_matrix((vr, (rows, cols)), shape=(len(F), n)).tocsc()
    Mi = sparse.coo_matrix((vi, (rows, cols)), shape=(len(F), n)).tocsc()
    A = sparse.bmat([[Mr, -Mi], [Mi, Mr]]).tocsc()
    pin_i = np.array(list(pins), int)
    pin_v = np.array([pins[i] for i in pin_i], float)
    free = np.setdiff1d(np.arange(n), pin_i)
    colsel_f = np.r_[free, free + n]
    colsel_p = np.r_[pin_i, pin_i + n]
    b = -A[:, colsel_p] @ np.r_[pin_v[:, 0], pin_v[:, 1]]
    Af = A[:, colsel_f]
    x = sparse.linalg.spsolve((Af.T @ Af).tocsc(), Af.T @ b)
    U = np.zeros((n, 2))
    U[free, 0], U[free, 1] = x[: len(free)], x[len(free):]
    U[pin_i] = pin_v
    return U


def flatten(V, F, U0, fix_x: np.ndarray | None = None, fix_y: int = 0, iters: int = FLAT_ITERS,
            pins: dict | None = None) -> np.ndarray:
    """ARAP flattening (Liu et al. 2008, local / global): the 3D surface V (n, 3) on triangles F into the plane,
    starting from U0 (n, 2). fix_x: vertices held on x = 0 (the CB line of a piece cut on the fold); fix_y: one vertex
    held at its y (translation)."""
    V = np.asarray(V, float)
    U = np.zeros((len(V), 2)) if U0 is None else np.asarray(U0, float).copy()
    F = np.asarray(F, int)
    n = len(V)
    # each triangle in its own 2D frame
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    x1 = np.linalg.norm(e1, axis=1)
    b1 = e1 / x1[:, None]
    nrm = np.cross(e1, e2)
    b2 = np.cross(nrm, e1)
    b2 /= np.linalg.norm(b2, axis=1, keepdims=True) + 1e-15
    loc = np.zeros((len(F), 3, 2))
    loc[:, 1, 0] = x1
    loc[:, 2, 0] = np.sum(e2 * b1, 1)
    loc[:, 2, 1] = np.sum(e2 * b2, 1)
    if pins is not None:  # LSCM start (Levy et al. 2002): conformal, linear; ARAP from a rectangle crawls on a sprung band
        U = _lscm(F, loc, n, pins)
    # cotangent weights per (triangle, opposite corner)
    W = np.zeros((len(F), 3))
    for c in range(3):
        i, j, k = c, (c + 1) % 3, (c + 2) % 3
        u_ = loc[:, j] - loc[:, i]
        v_ = loc[:, k] - loc[:, i]
        cr = np.abs(u_[:, 0] * v_[:, 1] - u_[:, 1] * v_[:, 0])
        W[:, c] = np.clip(np.sum(u_ * v_, 1) / np.maximum(cr, 1e-15), 1e-3, 1e3) * 0.5  # weight of edge (j, k)
    rows, cols, vals = [], [], []
    for c in range(3):
        j, k = F[:, (c + 1) % 3], F[:, (c + 2) % 3]
        w = W[:, c]
        rows += [j, k, j, k]
        cols += [k, j, j, k]
        vals += [-w, -w, w, w]
    L = sparse.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tocsr()
    big = 1e6 * float(np.abs(L.diagonal()).max() + 1)
    px = np.zeros(n)
    if fix_x is not None:
        px[np.asarray(fix_x, int)] = big
    py = np.zeros(n)
    py[int(fix_y)] = big
    solve_x = factorized((L + sparse.diags(px + 1e-9)).tocsc())
    solve_y = factorized((L + sparse.diags(py + 1e-9)).tocsc())
    y_fix = U[int(fix_y), 1]
    for _ in range(iters):
        # local: best rotation per triangle
        Su = np.zeros((len(F), 2, 2))
        for c in range(3):
            j, k = (c + 1) % 3, (c + 2) % 3
            dx = loc[:, j] - loc[:, k]
            du = U[F[:, j]] - U[F[:, k]]
            Su += W[:, c, None, None] * np.einsum("ti,tj->tij", du, dx)
        Uu, _, Vt = np.linalg.svd(Su)
        R = np.einsum("tij,tjk->tik", Uu, Vt)
        bad = np.linalg.det(R) < 0
        if bad.any():
            Uu[bad, :, 1] *= -1
            R[bad] = np.einsum("tij,tjk->tik", Uu[bad], Vt[bad])
        # global
        b = np.zeros((n, 2))
        for c in range(3):
            j, k = (c + 1) % 3, (c + 2) % 3
            rx = np.einsum("tij,tj->ti", R, loc[:, j] - loc[:, k]) * W[:, c, None]
            np.add.at(b, F[:, j], rx)
            np.add.at(b, F[:, k], -rx)
        bx = b[:, 0].copy()
        by = b[:, 1] + py * y_fix
        U = np.c_[solve_x(bx), solve_y(by)]
    return U


# ---------------------------------------------------------------- pieces
def _half_outline(nv, nu):
    """Grid indices round the half piece: bottom (CB -> end), end (bottom -> top), top (end -> CB)."""
    I = np.arange(nv * nu).reshape(nv, nu)
    return list(I[0, :]), list(I[:, -1]), list(I[-1, ::-1])


def to_piece(name: str, lay: dict, U: np.ndarray, like: dict | None = None) -> dict:
    """A full pattern piece (the flattened half mirrored about CB: cut on the fold) with the design table's names:
    stand: bottomMid, right/leftBottomCf, right/leftBottomEdge, right/leftTopCf, topMid; fall: bottomMid,
    right/leftBottomEdge (the sewn ends), right/leftTopEdge (the points), topMid. Notches at those points and at CB;
    `like`: the piece it replaces (its button / buttonhole marks are carried relative to CF)."""
    nv, nu = lay["X"].shape[:2]
    U = np.asarray(U, float).reshape(nv, nu, 2).reshape(-1, 2)
    bot, end, top = _half_outline(nv, nu)
    U = U - U[bot[0]] * [1, 1]  # bottomMid at the origin
    # right half (x > 0): orient the piece so the end lies at +x and the section runs +y
    if U[bot[-1], 0] < 0:
        U[:, 0] *= -1
    if U[top[-1], 1] < U[bot[0], 1]:
        U[:, 1] *= -1
    R = U
    Lf = U * [-1, 1]
    # outline: bottom R (mid -> end), end R (-> top), top R (-> mid), top L (mid -> end), end L (-> bottom), bottom L
    ring = ([R[i] for i in bot] + [R[i] for i in end[1:]] + [R[i] for i in top[1:]]
            + [Lf[i] for i in top[::-1][1:]] + [Lf[i] for i in end[::-1][1:]] + [Lf[i] for i in bot[::-1][1:-1]])
    P = np.asarray(ring)
    nb, ne, nt = len(bot), len(end), len(top)
    idx = {"bottomMid": 0}
    kind = lay["kind"]
    i_end_bot = nb - 1
    i_end_top = nb - 1 + ne - 1
    i_top_mid = i_end_top + nt - 1
    i_l_end_top = i_top_mid + nt - 1
    i_l_end_bot = i_l_end_top + ne - 1
    if kind == "stand":
        uu = lay["u"]
        s_cf = lay["s_cf"]
        kcf = int(np.argmin(np.abs(uu * lay["s"][0, -1] - s_cf)))
        idx.update(rightBottomCf=kcf, rightBottomEdge=i_end_bot, rightTopCf=i_end_top, topMid=i_top_mid,
                   leftTopCf=i_l_end_top, leftBottomEdge=i_l_end_bot, leftBottomCf=len(P) - kcf)
    else:
        idx.update(rightBottomEdge=i_end_bot, rightTopEdge=i_end_top, topMid=i_top_mid, leftTopEdge=i_l_end_top,
                   leftBottomEdge=i_l_end_bot)
    names = {k: int(v) % len(P) for k, v in idx.items()}
    marks = {f"{k}-notch": P[i].tolist() for k, i in names.items()}
    if like is not None and kind == "stand":
        lm, ln = like.get("marks") or {}, like["names"]
        lP = np.asarray(like["P"], float)
        for mk in ("button", "buttonhole"):
            if mk in lm:
                q = np.asarray(lm[mk], float)
                sd = "right" if q[0] > 0 else "left"
                if f"{sd}TopCf" in ln and f"{sd}BottomCf" in ln:
                    c_old = 0.5 * (lP[ln[f"{sd}TopCf"]] + lP[ln[f"{sd}BottomCf"]])
                    c_new = 0.5 * (P[names[f"{sd}TopCf"]] + P[names[f"{sd}BottomCf"]])
                    marks[mk] = (c_new + (q - c_old)).tolist()
    pc = {"name": name, "P": P, "names": names, "marks": marks, "lines": {}, "grain": 90.0, "draped": True}
    # the CCW sense the table's piece had (which face is the outside)
    if like is not None:
        from . import pattern
        if np.sign(pattern.area(np.asarray(like["P"], float))) != np.sign(pattern.area(P)):
            n = len(P)
            perm = [(-i) % n for i in range(n)]
            pc["P"] = P[perm]
            pc["names"] = {k: (-i) % n for k, i in names.items()}
    return pc


DEVELOP_ROUNDS = 12  # (r2: 4 -> 12) flatten <-> lift rounds: the worn spec made developable (the cloth's own shape near it)
DEVELOP_PULL = 0.005  # per relax step: the pull back to the worn spec's surface (r2: 0.05 -> 0.005 + 12 rounds: Garrett collar p99 2.23 -> ~2.0 %)
DEVELOP_STEPS = 150


def develop(lay: dict, under: "Surf | None", lay_off: float, rounds: int | None = None) -> dict:
    """The worn spec's surface made a flat piece's: a ruled fall from its roll to its landing line is developable only
    where the body is round; over a shoulder's saddle no flat piece takes that exact shape (Garrett d1: 7.7 % strain
    p99). As a pattern maker's muslin does, the cloth takes the nearest shape it CAN: alternate flattening (ARAP) and
    lifting the flat lengths back onto the spec (edge lengths of the flat, the sewn row held, a light pull to the spec,
    never inside the cloth under it). -> lay with "X" replaced, "X_spec" (the spec), "develop" (deviation report)."""
    nv, nu = lay["X"].shape[:2]
    F = grid_tris(nv, nu)
    E = _edges(F)
    X0 = lay["X"].reshape(-1, 3).copy()
    X = X0.copy()
    held = np.zeros(len(X), bool)
    held[:nu] = True  # (the sewn row)
    kc = lay.get("crease_row") or 0
    free_lay = _lying(X0, under, lay_off, (kc + 2) * nu)
    for _ in range(DEVELOP_ROUNDS if rounds is None else rounds):
        U = _flatten_grid(X, nv, nu, F)
        X = _lift(X, X0, U, E, held, under, free_lay, lay_off)
    dev = np.linalg.norm(X - X0, axis=1) * 1000
    out = dict(lay, X=X.reshape(nv, nu, 3), X_spec=X0.reshape(nv, nu, 3))
    edge = np.arange((nv - 1) * nu, nv * nu)
    land = {}
    if under is not None:
        sd, _, _ = under.signed(X[edge])
        land = {"edge_off_under_p50_mm": round(float(np.median(sd)) * 1000, 1),
                "edge_off_under_p90_mm": round(float(np.percentile(sd, 90)) * 1000, 1)}
    out["develop"] = dict({"from_spec_p50_mm": round(float(np.median(dev)), 2),
                           "from_spec_p90_mm": round(float(np.percentile(dev, 90)), 2),
                           "from_spec_max_mm": round(float(dev.max()), 2)}, **land)
    return out


def _lift(X, X0, U, E, held, under, free_lay, lay_off, steps: int | None = None, pull: float | None = None):
    """The flat piece's edge lengths put on a worn surface X0 (from X): Jacobi length projection, the held rows on
    X0, a light pull to X0, never inside the cloth under it."""
    steps = DEVELOP_STEPS if steps is None else steps  # (read at call time: a sweep can move them)
    pull = DEVELOP_PULL if pull is None else pull
    L0 = np.linalg.norm(U[E[:, 0]] - U[E[:, 1]], axis=1)
    X = X.copy()
    floor = np.minimum(under.signed(X0[free_lay])[0], lay_off) if under is not None and free_lay.any() else None  # (never nearer the cloth under it than the spec was)
    for _ in range(steps):
        d = X[E[:, 1]] - X[E[:, 0]]
        L = np.linalg.norm(d, axis=1) + 1e-15
        corr = (0.5 * (L - L0) / L)[:, None] * d
        acc = np.zeros_like(X)
        cnt = np.zeros(len(X))
        np.add.at(acc, E[:, 0], corr)
        np.add.at(acc, E[:, 1], -corr)
        np.add.at(cnt, E[:, 0], 1)
        np.add.at(cnt, E[:, 1], 1)
        X = X + 0.8 * acc / np.maximum(cnt, 1)[:, None] + pull * (X0 - X)
        X[held] = X0[held]
        if under is not None and free_lay.any():
            sd, Q, N = under.signed(X[free_lay])
            low = sd < floor
            if low.any():
                idx = np.where(free_lay)[0][low]
                X[idx] = Q[low] + N[low] * floor[low][:, None]
    return X


def _lying(X0, under, lay_off: float, first: int, slack: float = 0.001) -> np.ndarray:
    """The vertices that LIE on the cloth under them in the worn spec (past the roll, within a lay + slack of it): the
    lift keeps those on or outside it (the fall over the stand is above the neck seam: not on the under cloth)."""
    m = np.arange(len(X0)) >= first
    if under is None or not m.any():
        return np.zeros(len(X0), bool)
    sd, Q, N = under.signed(X0[m])
    over = np.linalg.norm((X0[m] - Q) - sd[:, None] * N, axis=1) < 5e-4  # (over the cloth, not past its edge)
    out = np.zeros(len(X0), bool)
    out[np.where(m)[0][(sd < lay_off + slack) & over]] = True
    return out


def _flatten_grid(V, nv, nu, F):
    cb = np.arange(nv) * nu
    top_cb = (nv - 1) * nu
    return flatten(V, F, None, fix_x=cb, fix_y=0,
                   pins={0: (0.0, 0.0), top_cb: (0.0, float(np.sum(np.linalg.norm(np.diff(V[cb], axis=0), axis=1))))})


def _flat_layer(lay):
    nv, nu = lay["X"].shape[:2]
    F = grid_tris(nv, nu)
    V = lay["X"].reshape(-1, 3)
    U0 = np.c_[lay["s"].ravel(), lay["a"].ravel()]
    cb = np.arange(nv) * nu
    top_cb = (nv - 1) * nu
    U = flatten(V, F, U0, fix_x=cb, fix_y=0, pins={0: (0.0, 0.0), top_cb: (0.0, float(np.sum(np.linalg.norm(np.diff(V[cb], axis=0), axis=1))))})
    st = strain(V, U, F)
    return U, F, st


def draft(entry: dict, base: dict, fabric: str | None = None, like: dict | None = None) -> dict:
    """Build, flatten, true and emit: -> {"pieces": {name: piece}, "folds": [...], "mesh": {name: {"uv", "X", "F"}}
    (the full mirrored drape: flat <-> worn, for the form's placement), "report"}."""
    b = build(entry, base, fabric)
    for nm_, lay_ in list(b["layers"].items()):
        b["layers"][nm_] = develop(lay_, base.get("under") if lay_["kind"] == "fall" else None, b["turn"]["lay"])
    pieces, folds, mesh, rep = {}, [], {}, {"turn": b["turn"], "layers": {}, "key": worn_key(entry),
                                            "source": entry.get("source") or DRAPE_SOURCE}
    for L in entry["layers"]:
        nm = L["piece"]
        lay = b["layers"][nm]
        U, F, st = _flat_layer(lay)
        pc = to_piece(nm, lay, U, (like or {}).get(nm))
        pieces[nm] = pc
        nv, nu = lay["X"].shape[:2]
        # the full drape (both halves) for placement: the left half mirrored in X about the CB plane
        Xr = lay["X"].reshape(-1, 3)
        Ur = U - U[0]
        if Ur[nu - 1, 0] < 0:
            Ur[:, 0] *= -1
        if Ur[-1, 1] < 0:
            Ur[:, 1] *= -1
        flip = 1.0
        if like is not None and nm in like:  # (to_piece may have reversed the outline; uv x / y kept as emitted)
            pass
        Xl = Xr * [-1, 1, 1] + [2 * float(base.get("cb_x", 0.0)), 0, 0]
        mesh[nm] = {"uv": np.r_[Ur, Ur * [-1, 1]], "X": np.r_[Xr, Xl], "F": np.r_[F, F[:, ::-1] + len(Xr)]}
        bot, end, top = _half_outline(nv, nu)
        Pg = lay["X"].reshape(-1, 3)
        rep["layers"][nm] = {
            "strain_p99_pct": round(float(np.percentile(np.abs(st), 99) * 100), 2),
            "strain_max_pct": round(float(np.abs(st).max() * 100), 2),
            "flat_bottom_mm": round(2 * float(np.sum(np.linalg.norm(np.diff(U[bot], axis=0), axis=1))) * 1000, 1),
            "flat_top_mm": round(2 * float(np.sum(np.linalg.norm(np.diff(U[top], axis=0), axis=1))) * 1000, 1),
            "worn_bottom_mm": round(2 * float(np.sum(np.linalg.norm(np.diff(Pg[bot], axis=0), axis=1))) * 1000, 1),
            "worn_top_mm": round(2 * float(np.sum(np.linalg.norm(np.diff(Pg[top], axis=0), axis=1))) * 1000, 1),
            "depth_cb_mm": round(float(lay["a"][-1, 0]) * 1000, 1), "develop": lay.get("develop")}
        if L.get("kind") == "fall":
            u_cb = 0.0
            rise = float(_field(L.get("rise", 0.0), np.array([u_cb]))[0])
            folds.append({"name": f"{nm} roll", "piece": nm, "kind": "roll", "angle": 0,
                          "line": {"edge": "leftBottomEdge>bottomMid>rightBottomEdge",
                                   "offset": round(rise + 0.25 * math.pi * b["turn"]["w"], 5)},
                          "radius": round(0.5 * b["turn"]["w"], 5), "strength": 0.6, "draped": True})
    # truing: each sewn pair's flat lengths (stand neck edge vs the worn curve, the fall's sewn edge vs the stand top)
    st_ = next((L["piece"] for L in entry["layers"] if L.get("kind") == "stand"), None)
    fa_ = next((L["piece"] for L in entry["layers"] if L.get("kind") == "fall"), None)
    tr = {}
    if st_:
        lay = b["layers"][st_]
        kcf = pieces[st_]["names"]["rightBottomCf"]
        Pp = np.asarray(pieces[st_]["P"])
        tr["neck_worn_mm"] = round(2 * b["s_cf"] * 1000, 1)
        tr["stand_neck_flat_mm"] = round(2 * float(np.sum(np.linalg.norm(np.diff(Pp[:kcf + 1], axis=0), axis=1))) * 1000, 1) \
            if kcf < len(Pp) // 2 else None
    if st_ and fa_:
        tr["stand_top_flat_mm"] = rep["layers"][st_]["flat_top_mm"]
        tr["fall_sewn_flat_mm"] = rep["layers"][fa_]["flat_bottom_mm"]
    rep["truing"] = tr
    if b.get("neck"):
        rep["stand_neck"] = {k: v for k, v in b["neck"].items() if k != "lean"}
    return {"pieces": pieces, "folds": folds, "mesh": mesh, "report": rep, "build": b}


def reach(drafted: dict, entry: dict, base_other: dict, fabric: str | None = None, limit: float = REACH_LIMIT) -> dict:
    """The same flat pieces put on another worn state's sweep (same section, the other base: a collar open): edge strain
    of the flat piece against that state's 3D; above `limit` (p99) the state is out of the piece's reach."""
    if (drafted["build"].get("neck") or {}).get("lean") is not None and base_other.get("lean") is None:
        base_other = dict(base_other, lean=drafted["build"]["neck"]["lean"])
    b2 = build(entry, base_other, fabric, rows={nm: lay.get("crease_row") for nm, lay in drafted["build"]["layers"].items()})
    out = {"limit_pct": round(limit * 100, 1), "layers": {}}
    ok = True
    for nm, lay in b2["layers"].items():
        nv, nu = lay["X"].shape[:2]
        F = grid_tris(nv, nu)
        E = _edges(F)
        U = drafted["mesh"][nm]["uv"][: nv * nu]
        X0 = lay["X"].reshape(-1, 3)
        held = np.zeros(len(X0), bool)
        held[:nu] = True
        kc = lay.get("crease_row") or 0
        free_lay = _lying(X0, base_other.get("under") if lay["kind"] == "fall" else None, b2["turn"]["lay"], (kc + 2) * nu)
        und = base_other.get("under") if lay["kind"] == "fall" else None
        X = X0.copy()
        for _ in range(DEVELOP_ROUNDS):
            X = _lift(X, X0, U, E, held, und, free_lay, b2["turn"]["lay"])
        st = strain(X, U, F)
        dev = np.linalg.norm(X - X0, axis=1) * 1000
        p99 = float(np.percentile(np.abs(st), 99))
        lay["X_spec"], lay["X"] = lay["X"], X.reshape(nv, nu, 3)
        out["layers"][nm] = {"strain_p99_pct": round(p99 * 100, 2), "strain_max_pct": round(float(np.abs(st).max()) * 100, 2),
                             "from_sweep_p90_mm": round(float(np.percentile(dev, 90)), 1),
                             "from_sweep_max_mm": round(float(dev.max()), 1), "ok": p99 <= limit}
        ok &= p99 <= limit
    out["ok"] = bool(ok)
    out["target"] = b2
    return out


# ---------------------------------------------------------------- what it is draped on
def edge_points(res: dict, X: np.ndarray, edge: str, tol: float = 6e-4) -> np.ndarray:
    """A pattern edge ("piece:a>b") as the form placed it: its mesh vertices, in order along the edge (n, 3)."""
    from . import pattern
    M = res["mesh"]
    nm, spec_ = edge.split(":", 1)
    pc = (res.get("pieces") or {}).get("pieces", {}).get(nm)
    Pe = np.asarray(pc["P"], float)[pattern.arc_indices(pc, spec_)]
    k = list(M["names"]).index(nm)
    sel = np.where(np.asarray(M["piece"]) == k)[0]
    uv = np.asarray(M["uv"], float)[sel]
    a, b = Pe[:-1], Pe[1:]
    d = b - a
    L2 = np.maximum((d * d).sum(1), 1e-18)
    t = np.clip(((uv[:, None, :] - a[None]) * d[None]).sum(2) / L2[None], 0, 1)
    q = a[None] + t[..., None] * d[None]
    dist = np.linalg.norm(q - uv[:, None, :], axis=2)
    j = np.argmin(dist, 1)
    on = dist[np.arange(len(uv)), j] < tol
    cum = np.r_[0, np.cumsum(np.sqrt(L2))]
    par = cum[j] + t[np.arange(len(uv)), j] * np.sqrt(L2[j])
    o = np.argsort(par[on])
    return np.asarray(X, float)[sel[on][o]]


def base_from_form(res: dict, X: np.ndarray, along: list, under_pieces: list, cb: str, side: float = 1.0,
                   step: float = 0.002, curve_side: float | None = None, true_sigma: float | None = None) -> dict:
    """A drape base from a dress-form result: the curve = the `along` edges (CB in the middle, at the named point
    `cb` "piece:point"), its half on the `side` (+1: +X, the creature's left) from CB to the end, resampled; the body
    (skin) and the garment's own cloth under the band (`under_pieces`), outward. `curve_side`: take the neckline half
    from that side instead (mirrored onto `side`): Garrett c0's left (over) front's neck edge is held 5.6 % over its
    flat length on the closed form (133.0 vs 125.9 mm), the right (under) one's within 1 % (124.7): the band is cut
    to the pattern's neckline, so it is draped on the half that keeps it (drape band r2, M12)."""
    from . import pattern
    C = np.concatenate([edge_points(res, X, e) for e in along])
    keep = np.r_[True, np.linalg.norm(np.diff(C, axis=0), axis=1) > 2e-4]
    C = C[keep]
    nm, pt = cb.split(":")
    M = res["mesh"]
    pc = res["pieces"]["pieces"][nm]
    q = np.asarray(pc["P"], float)[pc["names"][pt]]
    k = list(M["names"]).index(nm)
    sel = np.where(np.asarray(M["piece"]) == k)[0]
    icb = sel[np.argmin(np.linalg.norm(np.asarray(M["uv"], float)[sel] - q, axis=1))]
    pcb = np.asarray(X, float)[icb]
    i0 = int(np.argmin(np.linalg.norm(C - pcb, axis=1)))
    halves = [C[i0::-1], C[i0:]]
    cs = side if curve_side is None else curve_side
    H = max(halves, key=lambda h: cs * (h[:, 0].mean() - pcb[0]))
    H = np.r_[pcb[None], H[1:]] if np.linalg.norm(H[0] - pcb) > 1e-6 else H
    if cs * side < 0:  # (the other half's neckline, mirrored about CB: e.g. the under front's, which keeps its length)
        H = H * [-1, 1, 1] + [2 * pcb[0], 0, 0]
    s = _arc(H)
    ss = np.linspace(0, s[-1], max(int(s[-1] / step), 8) + 1)
    Hs = np.stack([np.interp(ss, s, H[:, d]) for d in range(3)], 1)
    trued = None
    true_sigma = TRUE_SIGMA if true_sigma is None else true_sigma
    if true_sigma > 0:
        Hs, trued = true_curve(Hs, float(pcb[0]), true_sigma)
        ss = _arc(Hs)
    body = res["body"]
    vn, tree = body.normals()

    def outward(P):
        _, i = tree.query(P)
        return vn[i]
    bs = Surf(body.V, body.T, out=outward)
    F = np.asarray(M["F"])
    pid = np.asarray(M["piece"])
    ks = [list(M["names"]).index(n) for n in under_pieces if n in M["names"]]
    Fu = F[np.isin(pid[F[:, 0]], ks)]
    us = Surf(np.asarray(X, float), Fu, out=outward)
    return {"curve": Hs, "s_cf": float(ss[-1]), "body": bs, "under": us, "cb_x": float(pcb[0]), "trued": trued}


TRUE_SIGMA = 0.008  # m: the neckline trued before a band is draped on it (Gaussian over arc, the whole loop)


def true_curve(H, cb_x: float, sigma: float = TRUE_SIGMA):
    """The neckline TRUED as a pattern maker trues it across its seams before the band is drafted: the form's sewn
    neck edge has corners (Garrett c0: a 50 deg V at CB, 36 deg at the yoke | front seam, 30-38 deg wiggles near CF;
    drape band r2 M12) and a band ruled on a corner is no flat piece (strain hot exactly there). The half is mirrored
    into the whole loop (square at CB and CF), smoothed (Gaussian, sigma over arc), and scaled off the loop's axis so
    its length is kept (the band is cut to the pattern's neckline). -> (trued half, {"max_dev_mm", "len_mm"})."""
    H = np.asarray(H, float)
    n = len(H)
    M = H * [-1, 1, 1] + [2 * cb_x, 0, 0]
    # the other half mirrored about CB (square there), then this half; past either CF end the curve is point-reflected
    # (its line carried on: an open neckline's fronts don't meet, so the loop is never closed across CF)
    full = np.r_[M[::-1][:-1], H]
    step = _arc(full)[-1] / (len(full) - 1)
    k = max(int(round(3 * sigma / step)), 1)
    k = min(k, n - 2)
    w = np.exp(-0.5 * (np.arange(-k, k + 1) * step / sigma) ** 2)
    w /= w.sum()
    ext = np.r_[2 * full[0] - full[k:0:-1], full, 2 * full[-1] - full[-2:-k - 2:-1]]
    sm = np.stack([np.convolve(ext[:, d], w, mode="valid") for d in range(3)], 1)
    Ht = sm[n - 1:].copy()
    Ht[:, 0] = np.where(np.arange(n) == 0, cb_x, Ht[:, 0])  # (CB on the CB plane)
    Ht[-1, 0] = cb_x if abs(H[-1, 0] - cb_x) < 1e-3 else Ht[-1, 0]
    a, c0 = neck_axis(Ht, cb_x)
    L0 = _arc(H)[-1]
    for _ in range(3):  # (length kept: scale off the axis)
        f = L0 / max(_arc(Ht)[-1], 1e-9)
        rel = Ht - c0
        ax = (rel @ a)[:, None] * a
        Ht = c0 + ax + (rel - ax) * f
    dev = np.linalg.norm(Ht - H, axis=1)
    return Ht, {"max_dev_mm": round(float(dev.max()) * 1000, 2), "p90_dev_mm": round(float(np.percentile(dev, 90)) * 1000, 2),
                "len_mm": round(float(_arc(Ht)[-1]) * 1000, 1), "sigma_mm": round(sigma * 1000, 1)}


# ---------------------------------------------------------------- the drape as the form's placement
def place_on_drape(uv: np.ndarray, dm: dict) -> np.ndarray:
    """Mesh vertices of a draped piece (pattern coords uv) -> their worn positions (barycentric in the drape's flat
    triangulation; a vertex outside it takes its nearest triangle's extension)."""
    Uf, Xf, Ff = (np.asarray(dm[k], float) for k in ("uv", "X", "F"))
    Ff = Ff.astype(int)
    A, B, C = (Uf[Ff[:, i]] for i in range(3))
    tree = cKDTree((A + B + C) / 3)
    _, idx = tree.query(uv, k=min(12, len(Ff)))
    idx = idx.reshape(len(uv), -1)
    a, b_, c = A[idx], B[idx], C[idx]
    v0, v1, v2 = b_ - a, c - a, uv[:, None, :] - a
    d00 = np.sum(v0 * v0, -1)
    d01 = np.sum(v0 * v1, -1)
    d11 = np.sum(v1 * v1, -1)
    d20 = np.sum(v2 * v0, -1)
    d21 = np.sum(v2 * v1, -1)
    den = np.where(np.abs(d00 * d11 - d01 * d01) < 1e-20, 1e-20, d00 * d11 - d01 * d01)
    w1 = (d11 * d20 - d01 * d21) / den
    w2 = (d00 * d21 - d01 * d20) / den
    w0 = 1 - w1 - w2
    out_ = -np.minimum(np.minimum(w0, w1), w2)  # how far outside (0 = inside)
    j = np.argmin(out_, 1)
    r = np.arange(len(uv))
    t = idx[r, j]
    W = np.c_[w0[r, j], w1[r, j], w2[r, j]]
    return np.einsum("ni,nij->nj", W, Xf[Ff[t]])


def mesh_file(model: str, key: str) -> str:
    from . import store
    d = store.HOME / model / "drape"
    d.mkdir(parents=True, exist_ok=True)
    return str(d / f"{key}.npz")


def save_mesh(path: str, mesh: dict) -> None:
    np.savez_compressed(path, **{f"{nm}__{k}": np.asarray(v) for nm, m in mesh.items() for k, v in m.items()})


def load_mesh(path: str) -> dict:
    z = np.load(path)
    out = {}
    for k in z.files:
        nm, kk = k.split("__", 1)
        out.setdefault(nm, {})[kk] = z[k]
    return out


def stored_pieces(entry: dict) -> dict:
    """A drape entry's emitted pieces (entry["out"]: written by `record`) as pattern pieces + their drape meshes."""
    o = entry.get("out") or {}
    mesh = load_mesh(o["file"]) if o.get("file") else {}
    pcs = {}
    for nm, d in (o.get("pieces") or {}).items():
        pc = {"name": nm, "P": np.asarray(d["P"], float), "names": {k: int(v) for k, v in d["names"].items()},
              "marks": {k: np.asarray(v, float) for k, v in (d.get("marks") or {}).items()}, "lines": {},
              "grain": float(d.get("grain", 90.0)), "draped": True}
        if nm in mesh:
            pc["drape"] = mesh[nm]
        pcs[nm] = pc
    return pcs


def record(entry: dict, drafted: dict, model: str) -> dict:
    """The entry with its generated pieces written in ("out"): outlines, names, marks, folds, the worn key, the
    report, the drape mesh file."""
    key = drafted["report"]["key"]
    path = mesh_file(model, key)
    save_mesh(path, drafted["mesh"])
    pcs = {nm: {"P": np.round(np.asarray(pc["P"]), 6).tolist(), "names": pc["names"],
                "marks": {k: np.round(np.asarray(v), 6).tolist() for k, v in pc["marks"].items()},
                "grain": pc.get("grain", 90.0)} for nm, pc in drafted["pieces"].items()}
    rep = {k: v for k, v in drafted["report"].items() if k != "turn"}
    rep["turn"] = {k: v for k, v in drafted["report"]["turn"].items()}
    return dict(entry, out={"key": key, "pieces": pcs, "folds": drafted["folds"], "file": path, "report": rep})


def gate_rows(g: dict) -> list:
    """Pattern gate rows: each drape entry's pieces must have been generated from its CURRENT worn spec
    (drape_band_current), and the flattening's distortion within the limit (drape_band_flat)."""
    rows = []
    for e in g.get("drape") or []:
        o = e.get("out") or {}
        cur = worn_key(e)
        ok = bool(o) and o.get("key") == cur
        rows.append({"id": f"drape_band_current:{e.get('name', '')}", "stage": 2, "status": "PASS" if ok else "FAIL",
                     "measure": "drape.worn_key", "ours": {"stored": o.get("key"), "worn_spec": cur},
                     "why": "the flat pieces are generated FROM the worn spec (Joe 2026-10-21); a changed worn spec "
                            "needs drape.draft again"})
        lay = (o.get("report") or {}).get("layers") or {}
        if lay:
            worst = max(v["strain_p99_pct"] for v in lay.values())
            rows.append({"id": f"drape_band_flat:{e.get('name', '')}", "stage": 2,
                         "status": "PASS" if worst <= FLAT_P99_LIMIT * 100 else "FAIL", "measure": "drape.flatten",
                         "ours": {nm: v["strain_p99_pct"] for nm, v in lay.items()},
                         "target": f"edge strain p99 <= {FLAT_P99_LIMIT * 100:.1f} %"})
    return rows


FLAT_P99_LIMIT = 0.02  # a draped band that can't be flattened within this isn't a pattern piece (needs a dart / seam)


def replace_pieces(out: dict, g: dict) -> tuple[dict, list]:
    """cloth.pieces: the design's pieces a drape entry generated replaced by them (the table's wrap / role kept);
    -> (out, the entries' folds, which replace the table's of the same piece)."""
    folds = []
    for e in g.get("drape") or []:
        if not e.get("out"):
            continue
        for nm, pc in stored_pieces(e).items():
            old = out.get(nm) or {}
            if old.get("wrap") is not None:
                pc["wrap"] = old["wrap"]
            if old.get("role"):
                pc["role"] = old["role"]
            out[nm] = pc
        folds += [dict(f) for f in e["out"].get("folds") or []]
    return out, folds


def draped_start(B: dict, M: dict) -> dict | None:
    """The placement given by the drape (cloth.place): {"pieces", "U", "X"} for the draped pieces' vertices, or None."""
    pcs = B.get("pieces") or {}
    names = list(M["names"])
    pid = np.asarray(M["piece"])
    uv = np.asarray(M["uv"], float)
    hit, X = [], None
    for k, nm in enumerate(names):
        dm = (pcs.get(nm) or {}).get("drape")
        if dm is None:
            continue
        sel = pid == k
        if X is None:
            X = np.full((len(uv), 3), np.nan)
        X[sel] = place_on_drape(uv[sel], dm)
        hit.append(nm)
    return {"pieces": hit, "X": X} if hit else None


def reproduced(M: dict, X: np.ndarray, B: dict) -> dict:
    """The self-check: the fitted draped pieces against the drape they were taken from (mm: p50 / p90 / max)."""
    out = {}
    ds = draped_start(B, M)
    if ds is None:
        return out
    pid = np.asarray(M["piece"])
    for nm in ds["pieces"]:
        sel = pid == list(M["names"]).index(nm)
        d = np.linalg.norm(np.asarray(X)[sel] - ds["X"][sel], axis=1) * 1000
        out[nm] = {"p50_mm": round(float(np.median(d)), 2), "p90_mm": round(float(np.percentile(d, 90)), 2),
                   "max_mm": round(float(d.max()), 2)}
    return out
