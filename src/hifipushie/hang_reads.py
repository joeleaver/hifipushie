"""HOW A GARMENT HANGS, measured on its fit (lesson 2 of the t3-t7 trials, docs/notes/trials.md; Joe 2026-10-27: "We're
still getting wings on the side ... that and the disconnected sleeves are the main things, those shouldn't ever have
passed early review").

Why: a garment falls from its supports (shoulders, the top of the arm, chest, seat) under its own weight and bridges the
body's hollows. The dress-form fit (pattern_form.on_form) draws every vertex onto an offset of the body instead, so the
pattern's ease has nowhere to go but the seams: it collects at the side seams as a thin double layer standing out like
a wing (hoodie t6), a sleeve stands off the arm all round as a separate tube with the gap ON TOP of the arm where the
weight should rest it (hoodie t6, tee t5), the shoulder points poke up where the cap meets the body (hoodie t6), and a
long hem is drawn in between the legs and into the seat (shirt t7). Every gate passed those fits: they measured that
the fit was clean, never how it hangs. Each read here is general (any garment on any body): it names the pieces from
their roles (garment_design.role_of) and the body from its landmarks (body.at: shoulder / elbow / wrist, armpit_z,
crotch_z), never from one garment's names.

READINGS (mm, read off the fitted vertices X and the body; `reads(res, X)` returns all four):
- `wing_reads`      per side (L = +x): in horizontal sections of the torso pieces from the armpit (or the armhole's bottom,
                    if lower) down to the hem, the
                    WING: how far the section's outermost cloth runs as a thin double layer (front and back closer than
                    WING_T) before it opens out; a smooth hang turns round the side in a few mm (a round of radius r
                    reaches WING_T across within WING_T^2 / 8r: < 1 mm). Also the side stand-off off the body vs the
                    front / back stand-off at that level (context, not gated: a boxy body hangs plumb from the chest, so
                    a large side stand-off below a narrow waist is a straight hang, tee t5 ~50 mm).
- `sleeve_reads`    per sleeve, in sections square to the arm (the body's own arm sections round the shoulder -> elbow ->
                    wrist landmarks): the gap between the sleeve and the TOP of the arm (the weight rests a hanging
                    sleeve on its support, so the top gap is the form's ease; the slack hangs underneath), the gap
                    under it, and the angle between the sleeve's axis (its sections' centres) and the arm's.
- `shoulder_reads`  per side, round the shoulder point (body.at shoulder.L, mirrored): the sharpest APEX, a cloth
                    vertex's height over the plane of the cloth SPIKE_R round it: a spike / step where the cap meets the
                    body is a point; a rounded (padded) shoulder is a dome and reads low.
- `hollow_reads`    in horizontal sections from just above the crotch to the hem: how deep the garment's cloth lies
                    INSIDE the convex hull of the body's section (between the legs, into the seat cleft): a real hem
                    bridges what it can't reach, a garment drawn into a hollow does not.

ROWS: `rows(rd)` -> fit rows (cloth_check.fit_rows), family "hang", each FAIL naming the piece and the fix. Until the fit
has a hang step (HANG_STEP, set by the hang step when it lands) the fix says so honestly: the fit draws the cloth onto
the body, so these are the FIT's faults, not the pattern's (an agent must not re-draft the pattern to chase them).
Thresholds: calibrated 2026-10-27 on the fits of trial_hoodie_t6:hoodie, trial_tshirt_t5:tee, trial_shirt_t7:shirt and
gc_garrett:jacket (/mnt/data/hifipushie/hang_gates/: dumps, section plots, calibrate.txt); evidence beside each.
"""
from __future__ import annotations

import numpy as np

# The fit has no hang step yet (another agent builds it in pattern_form): every hang FAIL is the fit's, and its fix says
# so. The hang step sets this True when it lands; the rows then name the pattern / the hang as the fix.
HANG_STEP = False

# ---------------------------------------------------------------- thresholds (evidence: calibrate.txt, 2026-10-27)
# Measured on the four fits (worst level / side; /mnt/data/hifipushie/hang_gates/calibrate.txt, sections_*.png):
#                     hoodie t6      tee t5         shirt t7 (styled)  jacket gc (styled, over the shirt)
#   wing mm           46 / 46 FAIL   5 / 8          8 / 12             15 / 13
#   sleeve top gap    16 / 16 FAIL   14 / 13 FAIL   7.5 / 6.9          6.5 / 5.8 (off the shirt's sleeve)
#   shoulder apex     11 / 10 FAIL   3.4 / 3.3      4.3 / 4.4          4.3 / 6.6
#   hollow mm         0              0              26 FAIL (front,    27 FAIL (the back drawn under the seat:
#                                                   between the legs)  CB y 108 -> 32 mm below the crotch)
WING_T = 0.020  # m: a section narrower than this front-to-back is a thin double layer (two cloth layers + a little air)
# Wing length: hoodie t6 46 mm (the wings Joe saw, sections_hoodie.png: front and back meet at an acute point 60-77 mm off
# the body); the rounded sides read 5-15 (sections_tee / shirt / jacket.png: a round side turns within ~1 mm, the rest is
# the mesh's own corner at the side seam and a jacket's side panel seam).
WING_MAX_MM = 20.0
# Sleeve: the gap between the sleeve and the top of what supports it (the arm, or the under garment's sleeve), median
# over the stations. A hanging sleeve rests there (the form's EASE 4 mm + a layer): shirt 6.9-7.5, jacket 5.8-6.5; the
# tubes stand off: hoodie 16 (upper arm 18-25), tee 13-14 with ~2 mm UNDER the arm (resting on the underside, held up).
SLEEVE_TOP_GAP_MAX_MM = 10.0
SLEEVE_AXIS_MAX_DEG = 10.0  # the sleeve's axis off the arm's (a tube held out at an angle): 2.5-4.4 deg on all four
ARM_SECTION_REACH = 0.09  # m: an arm section reaching further from its station than this has cut the torso too
# A station is a sleeve section only where the cloth goes ROUND the arm (no gap in its angle about the arm's centre over
# this). Hang round 2 (2026-10-27): a short sleeve hung from its cap has its hem lower under the arm than over it, so the
# last plane square to the arm cut only the hem's underside (16 points, an arc, its "top gap" -38 mm, its centre 40 mm
# off): read as a station, the tee's sleeve axis came out 47-49 deg from 3 stations 30 mm apart.
SLEEVE_ARC_GAP_DEG = 90.0
# Shoulder: the apex over the cloth's local plane (SPIKE_R) within SHOULDER_R of the shoulder point. Hoodie t6 10.4-10.8 mm
# (the cusps Joe saw, shoulder_hoodie.png); the padded jacket's rounded shoulder 4.3-6.6 (shoulder_jacket.png: a dome),
# tee 3.3, shirt 4.4.
SPIKE_R = 0.02
SHOULDER_R = 0.07
SHOULDER_SPIKE_MAX_MM = 8.0
# Hollow: cloth this deep inside the convex hull of the body's section. The shirt t7 hem drawn between the legs 26 mm
# (fit5_clay.png), the jacket's back hem 27 mm under the seat; every level above the crotch on all four reads <= 4 mm
# (hollow_levels.py: a hem that bridges reads <= 0).
HOLLOW_MAX_MM = 10.0
HOLLOW_ABOVE_CROTCH = 0.10  # m: from this far above the crotch (the seat cleft) down to the hem
STEP = 0.02  # m between sections


def _roles(names):
    from . import garment_design
    return [garment_design.role_of(n) for n in names]


def _faces_of(M: dict, keep) -> np.ndarray:
    F = np.asarray(M["F"])
    pid = np.asarray(M["piece"])[F[:, 0]]
    return F[np.isin(pid, list(keep))]


def _at(body) -> dict:
    return getattr(body, "at", None) or {}


def _mirror(p, sx: float) -> np.ndarray:
    return np.asarray(p, float).reshape(-1)[-3:] * [sx, 1.0, 1.0]


def _scalar(v) -> float:
    return float(np.asarray(v, float).reshape(-1)[-1])


def _loops(V, F, z):
    from . import tailor
    out = []
    for L in tailor.slice_loops(np.asarray(V, float), np.asarray(F), (0.0, 0.0, z), (0.0, 0.0, 1.0)):
        out.append(np.r_[L, L[:1]] if np.linalg.norm(L[0] - L[-1]) < 0.01 else L)
    return out


def _y_at(loops, x: float) -> np.ndarray:
    """Every y where the section's polylines cross the vertical line x."""
    ys = []
    for L in loops:
        a, b = L[:-1], L[1:]
        m = ((a[:, 0] - x) * (b[:, 0] - x) <= 0) & (np.abs(b[:, 0] - a[:, 0]) > 1e-9)
        t = (x - a[m, 0]) / (b[m, 0] - a[m, 0])
        ys += list(a[m, 1] + t * (b[m, 1] - a[m, 1]))
    return np.asarray(ys)


def _wing_len(loops, side: float) -> tuple:
    """(thin-run length m, outermost x m) on one side (+1: +x) of a section."""
    Ls = [L * [side, 1.0, 1.0] for L in loops]
    xt = float(max(L[:, 0].max() for L in Ls))
    for dx in np.arange(0.0005, 0.15, 0.001):
        ys = _y_at(Ls, xt - dx)
        if len(ys) >= 2 and ys.max() - ys.min() >= WING_T:
            return float(dx), xt
    return 0.15, xt


def _torso_section(body, z):
    from . import tailor
    BV = np.asarray(body.V, float)
    mid = BV[(np.abs(BV[:, 2] - z) < 0.01) & (np.abs(BV[:, 0]) < 0.03)]
    if not len(mid):
        return None
    return tailor.section(BV, np.asarray(body.T), (0.0, 0.0, z), (0.0, 0.0, 1.0), (0.0, float(mid[:, 1].mean()), z))


def _armhole_bottom(M: dict, X, torso) -> float:
    """The lowest point (z, m) of the seams joining a sleeve to the torso pieces; +inf without sleeves / seams.
    Above it a horizontal section of the torso pieces alone crosses the armhole's front and back edges, which run out to
    the sleeve's underarm seam: a thin double layer by construction, not a side hanging out (hang round 2: the hoodie t6's
    armhole bottom lies 117 mm under the armpit; hung, its torso read 17.5-21.5 mm there, the sleeve-torso junction, and
    1.5-3.5 mm at every level below it; Joe's wings were below it, z 1.12-1.14, 46 mm)."""
    from . import cloth_reference as cr
    sw = np.asarray(M.get("sew") if M.get("sew") is not None else [], int).reshape(-1, 2)
    if not len(sw):
        return float("inf")
    pv = np.asarray(M["piece"])
    sl = [k for k, r in enumerate(_roles(M["names"])) if r in cr.SLEEVE_ROLES]
    a, b = np.isin(pv[sw], sl), np.isin(pv[sw], list(torso))
    m = (a[:, 0] & b[:, 1]) | (a[:, 1] & b[:, 0])
    return float(np.asarray(X, float)[sw[m].ravel(), 2].min()) if m.any() else float("inf")


def wing_reads(M: dict, X, body) -> dict:
    """Per side ("L" = +x): the worst level's wing (thin double-layer run at the side, mm), its z, the side's stand-off
    off the body and the front / back stand-offs at that level (mm). {} without torso pieces or landmarks."""
    from . import cloth_reference as cr
    at = _at(body)
    if "armpit_z" not in at:
        return {}
    X = np.asarray(X, float)
    torso = [k for k, r in enumerate(_roles(M["names"])) if r not in cr.NOT_TORSO]
    Ft = _faces_of(M, torso)
    if not len(Ft):
        return {}
    zt = X[np.unique(Ft), 2]
    z0 = min(_scalar(at["armpit_z"]), _armhole_bottom(M, X, torso)) - STEP
    z1 = max(float(zt.min()) + STEP, _scalar(at.get("crotch_z", zt.min())) + STEP)
    out: dict = {}
    for z in np.arange(z0, z1, -STEP):
        B = _torso_section(body, z)
        loops = _loops(X, Ft, z)
        if B is None or not loops:
            continue
        P = np.concatenate(loops)
        c = B[:, :2].mean(0)
        for sx, k in ((1.0, "L"), (-1.0, "R")):
            w, xt = _wing_len(loops, sx)
            bx = float((B[:, 0] * sx).max())
            # front / back stand-off at this level: the cloth's extreme y beyond the body's, within the middle third
            mx = np.abs(P[:, 0] - c[0]) < 0.05
            mb = np.abs(B[:, 0] - c[0]) < 0.05
            fr = (B[mb, 1].min() - P[mx, 1].min()) * 1000 if mx.any() and mb.any() else None
            bk = (P[mx, 1].max() - B[mb, 1].max()) * 1000 if mx.any() and mb.any() else None
            r = {"wing_mm": round(w * 1000, 1), "z": round(float(z), 3), "side_off_mm": round((xt - bx) * 1000, 1),
                 "front_off_mm": None if fr is None else round(float(fr), 1),
                 "back_off_mm": None if bk is None else round(float(bk), 1)}
            if k not in out or r["wing_mm"] > out[k]["wing_mm"]:
                out[k] = r
    return out


def _seg(at: dict, sx: float):
    return [_mirror(at[k], sx) for k in ("shoulder.L", "elbow.L", "wrist.L")]


def _axis(P: np.ndarray) -> np.ndarray:
    c = P.mean(0)
    v = np.linalg.svd(P - c)[2][0]
    return v if v @ (P[-1] - P[0]) > 0 else -v


def _arc_gap_deg(P: np.ndarray, n: np.ndarray) -> float:
    """The largest gap (deg) in the angles of points P (relative to an axis point) about the axis n."""
    a = np.cross(n, [0.0, 0.0, 1.0] if abs(n[2]) < 0.9 else [1.0, 0.0, 0.0])
    a /= np.linalg.norm(a)
    b = np.cross(n, a)
    th = np.sort(np.degrees(np.arctan2(P @ b, P @ a)))
    if len(th) < 3:
        return 360.0
    return float(np.max(np.r_[np.diff(th), th[0] + 360.0 - th[-1]]))


def sleeve_reads(M: dict, X, body, under=None) -> dict:
    """Per sleeve ("L" = the +x one): in sections square to the arm, the median gap between the sleeve and the TOP of
    what supports it (the arm, or the under garment's sleeve over it: under = (V, F)) in mm, under it, the stations
    read, and the angle (deg) between the sleeve's axis and the arm's over them. {} without sleeves or arm landmarks.
    (A jacket over a shirt rests on the shirt's sleeve: read off the arm, gc_garrett's jacket stood 20 mm over the top
    of the arm with the shirt in it.)"""
    from . import cloth_reference as cr, tailor
    at = _at(body)
    if not all(k in at for k in ("shoulder.L", "elbow.L", "wrist.L")):
        return {}
    X = np.asarray(X, float)
    BV, BT = np.asarray(body.V, float), np.asarray(body.T)
    roles = _roles(M["names"])
    pv = np.asarray(M["piece"])
    sl = [k for k, r in enumerate(roles) if r in cr.SLEEVE_ROLES and (pv == k).any()]
    out = {}
    for sx, side in ((1.0, "L"), (-1.0, "R")):
        ks = [k for k in sl if float(np.mean(X[pv == k, 0])) * sx > 0]
        if not ks:
            continue
        Fs = _faces_of(M, ks)
        S_, E_, W_ = _seg(at, sx)
        tops, unders, ca, cs, n_ = [], [], [], [], 0
        for a, b in ((S_, E_), (E_, W_)):
            n = (b - a) / np.linalg.norm(b - a)
            u = np.array([0.0, 0.0, 1.0]) - n[2] * n
            u /= np.linalg.norm(u)
            for t in np.arange(0.1, 0.95, 0.1):
                o = a + t * (b - a)
                A = tailor.section(BV, BT, o, n, o)
                if A is None or np.linalg.norm(A - o, axis=1).max() > ARM_SECTION_REACH:
                    continue  # (the plane cut the torso too, near the shoulder, or missed the arm)
                Ls = [L for L in tailor.slice_loops(X, Fs, o, n) if np.min(np.linalg.norm(L - o, axis=1)) < 0.12]
                if not Ls:
                    continue
                C = np.concatenate(Ls)
                c0 = A.mean(0)
                if _arc_gap_deg(C - c0, n) > SLEEVE_ARC_GAP_DEG:
                    continue  # (the plane cut the hem obliquely: the cloth doesn't go round the arm there)
                if under is not None:  # (the support: the arm and the under garment's cloth round it)
                    Lu = [L for L in tailor.slice_loops(under[0], under[1], o, n)
                          if np.linalg.norm(L - o, axis=1).max() < ARM_SECTION_REACH + 0.03]
                    A = np.concatenate([A] + Lu)
                tops.append(((C - c0) @ u).max() - ((A - c0) @ u).max())
                unders.append(((A - c0) @ u).min() - ((C - c0) @ u).min())
                ca.append(c0)
                cs.append(C.mean(0))
                n_ += 1
        if not n_:
            continue
        ang = None
        if n_ >= 3:
            ang = float(np.degrees(np.arccos(np.clip(_axis(np.array(ca)) @ _axis(np.array(cs)), -1, 1))))
        out[side] = {"top_gap_mm": round(float(np.median(tops)) * 1000, 1),
                     "under_gap_mm": round(float(np.median(unders)) * 1000, 1),
                     "top_gap_max_mm": round(float(np.max(tops)) * 1000, 1),
                     "axis_deg": None if ang is None else round(ang, 1), "stations": n_,
                     "pieces": [M["names"][k] for k in ks]}
    return out


def shoulder_reads(M: dict, X, body) -> dict:
    """Per side: the sharpest APEX within SHOULDER_R of the shoulder point: a cloth vertex's height (mm) over the plane
    fitted to the cloth SPIKE_R round it (the ring past 0.4 SPIKE_R; outward = away from the body), where (mm off the
    shoulder point), on which piece, and its stand-off off the body. {} without the landmark. (A protrusion over the
    neighbourhood's stand-off read a padded jacket's rounded shoulder, a dome, as high as the hoodie's cusps, 12 vs
    11-13 mm: shoulder_jacket.png / shoulder_hoodie.png; the apex over the local plane tells a point from a dome.)"""
    from scipy.spatial import cKDTree
    from . import pattern_form
    at = _at(body)
    if "shoulder.L" not in at:
        return {}
    X = np.asarray(X, float)
    pv = np.asarray(M["piece"])
    tree = cKDTree(X)
    surf = pattern_form._body_surface(body)
    out = {}
    for sx, side in ((1.0, "L"), (-1.0, "R")):
        sp = _mirror(at["shoulder.L"], sx)
        idx = np.flatnonzero(np.linalg.norm(X - sp, axis=1) < SHOULDER_R)
        if not len(idx):
            continue
        sd, N, _ = surf.signed(X[idx])
        best = (-1.0, None, 0)
        for j, i in enumerate(idx):
            nb = [k for k in tree.query_ball_point(X[i], SPIKE_R) if np.linalg.norm(X[k] - X[i]) > 0.4 * SPIKE_R]
            if len(nb) < 6:
                continue
            P = X[nb]
            c = P.mean(0)
            n = np.linalg.svd(P - c)[2][2]
            h = float((X[i] - c) @ (n if n @ N[j] > 0 else -n))
            if h > best[0]:
                best = (h, i, j)
        if best[1] is None:
            continue
        h, i, j = best
        out[side] = {"spike_mm": round(h * 1000, 1), "standoff_mm": round(float(sd[j]) * 1000, 1),
                     "at_mm": [int(round(v)) for v in (X[i] - sp) * 1000], "piece": M["names"][int(pv[i])]}
    return out


def _inside_hull(P2: np.ndarray, H2: np.ndarray) -> np.ndarray:
    """Depth (m) of each point inside the convex polygon H2 (counter-clockwise hull vertices); <= 0 outside."""
    a, b = H2, np.roll(H2, -1, 0)
    e = b - a
    nrm = np.c_[e[:, 1], -e[:, 0]] / np.linalg.norm(e, axis=1)[:, None]  # outward for a ccw polygon
    d = np.einsum("pk,ek->pe", P2, nrm) - np.sum(a * nrm, 1)
    return -d.max(1)


def hollow_reads(M: dict, X, body, skip=()) -> dict:
    """The deepest cloth inside the convex hull of the body's section (mm), its z and where ("front" / "back" / "between
    the legs"), over sections from HOLLOW_ABOVE_CROTCH above the crotch to the hem; the piece. {} without crotch_z.
    skip: piece names left out (a trouser leg wraps a leg: between the legs is where it belongs)."""
    from scipy.spatial import ConvexHull
    from . import cloth_reference as cr
    at = _at(body)
    if "crotch_z" not in at:
        return {}
    X = np.asarray(X, float)
    torso = [k for k, r in enumerate(_roles(M["names"])) if r not in cr.SLEEVE_ROLES and M["names"][k] not in skip]
    Ft = _faces_of(M, torso)
    if not len(Ft):
        return {}
    cz = _scalar(at["crotch_z"])
    zmin = float(X[np.unique(Ft), 2].min())
    BV, BT = np.asarray(body.V, float), np.asarray(body.T)
    pv = np.asarray(M["piece"])
    best = {"depth_mm": 0.0}
    for z in np.arange(cz + HOLLOW_ABOVE_CROTCH, zmin, -STEP / 2):
        Bl = [L for L in _loops(BV, BT, z) if abs(L[:, 0].mean()) < 0.25]  # (the hands hang beside the thighs)
        if not Bl:
            continue
        B2 = np.concatenate(Bl)[:, :2]
        if len(B2) < 4:
            continue
        H2 = B2[ConvexHull(B2).vertices]
        from . import tailor
        segs = []
        for L in tailor.slice_loops(X, Ft, (0.0, 0.0, z), (0.0, 0.0, 1.0)):
            segs.append(L)
        if not segs:
            continue
        C = np.concatenate(segs)
        dep = _inside_hull(C[:, :2], H2)
        j = int(np.argmax(dep))
        if dep[j] * 1000 > best["depth_mm"]:
            q = C[j]
            gap = abs(q[0]) < 0.05 and z < cz
            where = "between the legs" if gap else ("back (the seat)" if q[1] > B2[:, 1].mean() else "front")
            # the piece: the nearest garment vertex
            v = int(np.argmin(np.linalg.norm(X - q, axis=1)))
            best = {"depth_mm": round(float(dep[j]) * 1000, 1), "z": round(float(z), 3),
                    "above_crotch_mm": round((float(z) - cz) * 1000), "where": where,
                    "piece": M["names"][int(pv[v])]}
    return best


def reads(res: dict, X) -> dict:
    """All four hang reads of a fit (res: on_form's result, X its vertices as judged: styled)."""
    M, body = res["mesh"], res["body"]
    pcs = (res.get("pieces") or {}).get("pieces") or {}
    fu = res.get("form_under")
    und = None if fu is None else (np.asarray(fu["A"], float), np.asarray(fu["mesh"]["F"]))
    legs = tuple(n for n, pc in pcs.items() if str(((pc or {}).get("wrap") or {}).get("to", "")).startswith("leg."))
    out = {}
    for k, f in (("wings", wing_reads), ("sleeves", lambda M_, X_, b_: sleeve_reads(M_, X_, b_, under=und)),
                 ("shoulders", shoulder_reads),
                 ("hollow", lambda M_, X_, b_: hollow_reads(M_, X_, b_, skip=legs))):
        try:
            out[k] = f(M, X, body)
        except Exception as e:  # noqa: BLE001 (a read that breaks is unmeasured, and says so)
            out[k] = {"error": f"{type(e).__name__}: {e}"}
    return out


# With the hang step (HANG_STEP) a hang FAIL is the PATTERN's: the fit hangs it from its supports, so what still stands
# off, spikes or clings is cut that way. The pattern fix per read (a pattern maker's first move for that fault):
PATTERN_FIX = {
    "wings": "the girth at that level is more than the hang can carry round: take ease out at the side seams there (or "
             "shape the side seam in), keeping the chest / hip ease the kind asks",
    "sleeves": "the sleeve is held off the arm by its cap: raise the cap (a higher cap hangs the sleeve closer to the "
               "arm) or take width out of the upper sleeve",
    "shoulders": "the cap meets the shoulder seam in a point: lower the cap's ease at the top, or shorten / drop the "
                 "shoulder seam so the cap's crown lies on the shoulder",
    "hollow": "the hem can't bridge the hollow: shorten the hem there or give the seat / front more width so it hangs "
              "clear",
}


def _cause(read: str = "") -> str:
    if HANG_STEP:
        return f" (the fit hangs the garment from its supports: this is cut into the PATTERN: {PATTERN_FIX[read]})" \
            if read in PATTERN_FIX else ""
    return (" (no hang step yet: the fit draws the cloth onto the body, so this is the FIT's fault, not the "
            "pattern's: don't re-draft the pattern to chase it; judge the pattern by its other rows)")


def rows(rd: dict) -> list:
    """The hang fit rows (family "hang", stage 1: a big read) from reads(): FAIL naming the side / piece and the fix."""
    out = []

    def row(id_, ok, ours, target, fix, measure, err=None):
        if err:
            return {"id": id_, "family": "hang", "stage": 1, "status": "UNMEASURED", "why": err, "measure": measure}
        if ok is None:
            return {"id": id_, "family": "hang", "stage": 1, "status": "PASS", "ours": ours, "target": target,
                    "measure": measure, "why": "nothing to read on this garment"}
        r = {"id": id_, "family": "hang", "stage": 1, "status": "PASS" if ok else "FAIL", "ours": ours,
             "target": target, "measure": measure}
        if not ok:
            r["fix"] = fix + _cause(id_[5:])
            r["owner"] = "pattern" if HANG_STEP else "fit"
        return r

    w = rd.get("wings") or {}
    bad = {k: v for k, v in w.items() if isinstance(v, dict) and v.get("wing_mm", 0) > WING_MAX_MM}
    out.append(row("hang_wings", None if not w else not bad, w, f"<= {WING_MAX_MM:g} mm of thin double layer at "
                   "each side (a smooth hang turns round the side)",
                   "wings at the side seams (" + ", ".join(f"{k} {v['wing_mm']:.0f} mm at z {v['z']}, standing "
                   f"{v['side_off_mm']:.0f} mm off the body" for k, v in bad.items()) + "): the ease is collecting at "
                   "the sides; it must hang from the chest and blades all round", "hang_reads.wing_reads",
                   w.get("error")))
    s = rd.get("sleeves") or {}
    bad = {k: v for k, v in s.items() if isinstance(v, dict) and k in ("L", "R") and (
        v["top_gap_mm"] > SLEEVE_TOP_GAP_MAX_MM or (v.get("axis_deg") or 0) > SLEEVE_AXIS_MAX_DEG)}
    out.append(row("hang_sleeves", None if not s else not bad, s,
                   f"the sleeve rests on the top of the arm (gap <= {SLEEVE_TOP_GAP_MAX_MM:g} mm, the slack under it) "
                   f"and follows it (axis within {SLEEVE_AXIS_MAX_DEG:g} deg)",
                   "sleeves standing off the arm (" + ", ".join(
                       f"{'/'.join(v['pieces'])}: {v['top_gap_mm']:.0f} mm over the top of the arm, "
                       f"{v['under_gap_mm']:.0f} under it" + (f", axis {v['axis_deg']:.0f} deg off the arm's"
                                                            if (v.get("axis_deg") or 0) > SLEEVE_AXIS_MAX_DEG else "")
                       for v in bad.values()) + "): a sleeve hangs on the top of the arm by its weight",
                   "hang_reads.sleeve_reads", s.get("error")))
    sh = rd.get("shoulders") or {}
    bad = {k: v for k, v in sh.items() if isinstance(v, dict) and v.get("spike_mm", 0) > SHOULDER_SPIKE_MAX_MM}
    out.append(row("hang_shoulders", None if not sh else not bad, sh,
                   f"no point more than {SHOULDER_SPIKE_MAX_MM:g} mm above the cloth's own surface round it near the "
                   "shoulder point (a smooth shoulder line into the sleeve)",
                   "a spike / step at the shoulder point (" + ", ".join(
                       f"{k}: a point {v['spike_mm']:.0f} mm high on {v['piece']}, {v['at_mm']} mm off the shoulder point"
                       for k, v in bad.items()) + "): the cap and the shoulder seam meet in a point instead of one "
                   "smooth line", "hang_reads.shoulder_reads", sh.get("error")))
    h = rd.get("hollow") or {}
    hd = h.get("depth_mm")
    out.append(row("hang_hollow", None if not h or hd is None else hd <= HOLLOW_MAX_MM, h,
                   f"the hem bridges the body's hollows: no cloth more than {HOLLOW_MAX_MM:g} mm inside the convex hull "
                   "of the body's section (between the legs, the seat)",
                   f"cloth drawn into a hollow ({h.get('piece')} {hd} mm deep {h.get('where')}, "
                   f"{h.get('above_crotch_mm')} mm from the crotch level): it must bridge across",
                   "hang_reads.hollow_reads", h.get("error")))
    return out
