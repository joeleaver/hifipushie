"""Pose correctives: morph targets that undo what linear blend skinning does to a bent joint, sculpted by a solver.

Why (2026-10-14, rig_r1..r4): weights alone (MakeHuman's, the half-angle helpers, `rig.BEND_ARC`'s repaint, dual
quaternions, a delta mush) never gave a knee a kneecap at 90 deg, a seated buttock its round, a raised shoulder its
deltoid: LBS turns each vertex by a blend of rigid turns, so the outer side of a bend runs along the chord and the
inner side folds through itself. Games fix it the way MetaHuman and every AAA character does: a CORRECTIVE morph
target per joint and angle, faded in by the joint's angle (a "pose driver"). An artist sculpts each one; here a
solver does: the skin of the joint's region is bent AS-RIGID-AS-POSSIBLE (Sorkine and Alexa 2007: every vertex's
one-ring keeps its rest shape up to a rotation) between the two segments held where LBS puts them, so the outer side
goes round the arc with its rest form (kneecap, olecranon, glute) and the inner side compresses; what still crosses
the bisecting plane of the bend on the inner side is laid on it (the contact crease) and the solve runs again with
those held. The move is written in the REST frame (glTF applies morph targets before skinning): delta = M^-1 (target
- LBS), M the vertex's blended skinning matrix, so at the key angle LBS(rest + delta) = target.

Each corrective: name "corr_<Side><Joint>_<motion><deg>", its joint, the motion's axis in the joint's rest frame
(world, Blender axes, = the parent's frame at rest) and the key angle. Driver (what an engine does every frame, the
json's rig.correctives): the joint's local rotation from rest as swing (about an axis perpendicular to the bone) and
twist; w = clamp(swing_deg * dot(swing_axis, key_axis) / key_deg, 0, 1) for the first key of a motion; with two keys
k1 < k2 the first rises 0 -> 1 over 0..k1 and falls 1 -> 0 over k1..k2 while the second rises (a piecewise-linear
pose driver). Each key is solved alone from the rest: at a key angle only that key is on.
Worn parts (briefs, socks) take the skin's rest-frame move at the nearest point of the skin's surface.
"""
from __future__ import annotations

import numpy as np

from . import rig as rigmod

PREFIX = rigmod.PREFIX
# motion: (joint, axis for the LEFT side or "hinge" (the rest bend's own axis, flexing), sign, key angles in degrees
# from rest). Right side: the axis mirrored as a rotation (x, -y, -z).
MOTIONS = {
    "Leg_flex": ("Leg", "hinge", 1.0, (90.0, 130.0)),
    "ForeArm_flex": ("ForeArm", "hinge", 1.0, (60.0, 100.0)),
    "Arm_raise": ("Arm", (0.0, 1.0, 0.0), -1.0, (45.0, 90.0)),
}
# (no hip corrective: the solved buttock flattened and dragged the briefs in every variant, rig_r5; the arc weights
# alone keep it round)
# ARAP relax after the arc target: off. Surface ARAP is a straw: a bent tube with both ends held kinks and flattens
# (the synthetic leg's knee front went from 5.5 to 2.9 cm off the pivot, tests/test_rig_bend.py), what read as a
# rounded knee in c1 was that collapse. The arc target keeps every vertex's distance from the pivot.
RELAX: tuple = ()
ARC_WIDEN = 1.4    # the target's zone x the weights' (the outer skin of a 120 deg knee needs r x 2.1 of arc)
ARC_LINEAR = 0.7   # the target's turn along the zone: this much linear, the rest smoothstep (a smoothstep alone turned
                   # most of the angle mid-zone: a corner at 120 deg)
ITERS = 12          # ARAP local / global rounds
FREE = 2.4          # the solved region: |s| within this x the joint's outer zone half width (rig.arc_frames)
TARGET = "arc"      # "arc": the family's share turned round the pivot by phi x angle; "arap": as-rigid-as-possible
CONTACT_ROUNDS = 2
CONTACT_SOFT = 0.004  # m: the soft contact's width (arc target)  # lay the inner side on the bisecting plane, solve again
EPS = 1e-4          # m: moves under this are left out of a target


def _children(bones):
    ch = {i: [] for i in range(len(bones))}
    for i, b in enumerate(bones):
        if b["parent"] >= 0:
            ch[b["parent"]].append(i)
    return ch


def keys(bones: list[dict], motions: dict | None = None) -> list[dict]:
    """Every corrective this rig gets: [{name, joint, side, axis (unit, world rest), deg, prev (name of the lower
    key of the same motion or None), frame (rig.arc_frames row)}]."""
    names = [b["name"] for b in bones]
    frames = {(f["joint"], f["side"]): f for f in rigmod.arc_frames(bones)}
    out = []
    for mo, (jn, ax, sign, degs) in (motions or MOTIONS).items():
        for side, sg in (("Left", 1.0), ("Right", -1.0)):
            full = PREFIX + side + jn
            if full not in names or (jn, sg) not in frames:
                continue
            f = frames[(jn, sg)]
            if ax == "hinge":
                i = names.index(full)
                ud = f["pivot"] - np.asarray(bones[bones[i]["parent"]]["head"], float)
                ch = [c for c in _children(bones)[i] if not bones[c].get("twist") and not bones[c].get("bend")]
                if not ch:
                    continue
                uc = np.asarray(bones[ch[0]]["head"], float) - f["pivot"]
                a = np.cross(ud, uc)
                if np.linalg.norm(a) < 1e-6 * np.linalg.norm(ud) * np.linalg.norm(uc):
                    continue
                a = a / np.linalg.norm(a) * sign
            else:
                a = np.asarray(ax, float) * sign
                if sg < 0:
                    a = a * np.array([1.0, -1.0, -1.0])
                a = a / np.linalg.norm(a)
            prev = None
            for d in degs:
                nm = f"corr_{side}{jn}_{mo.split('_')[1]}{int(round(d))}"
                out.append({"name": nm, "joint": full, "side": side, "axis": a, "deg": float(d), "prev": prev,
                            "frame": f, "motion": mo})
                prev = nm
    return out


def weights_at(k: dict, all_keys: list[dict], deg: float) -> dict:
    """The drivers' weights {name: w} of one motion's keys at `deg` (the swing about its axis): piecewise linear."""
    ks = sorted([x for x in all_keys if x["joint"] == k["joint"] and x["motion"] == k["motion"]], key=lambda x: x["deg"])
    out = {}
    for i, x in enumerate(ks):
        lo = ks[i - 1]["deg"] if i else 0.0
        hi = ks[i + 1]["deg"] if i + 1 < len(ks) else None
        if deg <= lo:
            w = 0.0
        elif deg <= x["deg"]:
            w = (deg - lo) / (x["deg"] - lo)
        elif hi is None:
            w = 1.0
        else:
            w = max(0.0, (hi - deg) / (hi - x["deg"]))
        out[x["name"]] = w
    return out


def _cot_laplacian(V, F):
    from scipy import sparse
    n = len(V)
    I, J, Wv = [], [], []
    for a, b, c in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
        ea = V[F[:, b]] - V[F[:, a]]
        eb = V[F[:, c]] - V[F[:, a]]
        cr = np.linalg.norm(np.cross(ea, eb), axis=1)
        cot = (ea * eb).sum(1) / np.maximum(cr, 1e-12)
        cot = np.clip(cot, 0.0, 5.0)  # clamped: obtuse slivers make negative weights and an unstable solve
        I += [F[:, b], F[:, c]]
        J += [F[:, c], F[:, b]]
        Wv += [0.5 * cot, 0.5 * cot]
    I, J, Wv = np.concatenate(I), np.concatenate(J), np.concatenate(Wv) + 1e-8
    Wm = sparse.coo_matrix((Wv, (I, J)), shape=(n, n)).tocsr()
    Wm.sum_duplicates()
    return Wm


def arap(V: np.ndarray, F: np.ndarray, P0: np.ndarray, free: np.ndarray, iters: int = ITERS) -> np.ndarray:
    """As-rigid-as-possible: the free vertices of a mesh (rest V) placed so each one-ring keeps its rest shape up to
    a rotation, the others held at P0 (P0 also the start)."""
    from scipy import sparse
    from scipy.sparse.linalg import splu
    n = len(V)
    Wm = _cot_laplacian(V, F)
    deg = np.asarray(Wm.sum(1)).ravel()
    Lm = (sparse.diags(deg) - Wm).tocsc()
    fi = np.flatnonzero(free)
    ci = np.flatnonzero(~free)
    if not len(fi):
        return P0.copy()
    Lff = Lm[fi][:, fi].tocsc()
    Lfc = Lm[fi][:, ci]
    lu = splu(Lff)
    coo = Wm.tocoo()
    r, c, w = coo.row, coo.col, coo.data
    keep = np.isin(r, fi) | np.isin(c, fi)
    r, c, w = r[keep], c[keep], w[keep]
    E = V[r] - V[c]
    P = P0.copy()
    for _ in range(iters):
        Ep = P[r] - P[c]
        S = np.zeros((n, 3, 3))
        np.add.at(S, r, w[:, None, None] * E[:, :, None] * Ep[:, None, :])
        U, _s, Vt = np.linalg.svd(S)
        R = np.einsum("nji,nkj->nik", Vt, U)  # V U^T
        bad = np.linalg.det(R) < 0
        if bad.any():
            U2 = U[bad].copy()
            U2[:, :, 2] *= -1
            R[bad] = np.einsum("nji,nkj->nik", Vt[bad], U2)
        bvec = np.zeros((n, 3))
        np.add.at(bvec, r, 0.5 * w[:, None] * np.einsum("nij,nj->ni", R[r] + R[c], E))
        rhs = bvec[fi] - Lfc @ P[ci]
        P[fi] = np.column_stack([lu.solve(rhs[:, k]) for k in range(3)])
    return P


def _skin_mats(bones, J, W, turns):
    """Per vertex the blended skinning matrix (4x4) of LBS under `turns` (rig.pose's convention)."""
    n = len(bones)
    M = np.tile(np.eye(4), (n, 1, 1))
    for i, b in enumerate(bones):
        L = np.eye(4)
        if b["name"] in turns:
            ax, deg = turns[b["name"]]
            ax = np.asarray(ax, float) / np.linalg.norm(ax)
            t = np.radians(deg)
            K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
            Rm = np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K
            h = np.asarray(b["head"], float)
            L[:3, :3], L[:3, 3] = Rm, h - Rm @ h
        M[i] = (M[b["parent"]] if b["parent"] >= 0 else np.eye(4)) @ L
    return np.einsum("nk,nkij->nij", W, M[J]), M


def _weld(V, F, tol=1e-6):
    key = np.round(V / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    return V[first], inv[F], inv


def solve(bones: list[dict], V: np.ndarray, F: np.ndarray, J: np.ndarray, W: np.ndarray,
          ks: list[dict] | None = None, log: list | None = None) -> dict:
    """{name: rest-frame delta (n, 3)} for the skin mesh (V, F rest; J, W its final weights)."""
    log = log if log is not None else []
    ks = ks if ks is not None else keys(bones)
    V = np.asarray(V, float)
    J = np.asarray(J)
    W = np.asarray(W, float)
    Vw, Fw, inv = _weld(V, np.asarray(F))
    first = np.zeros(len(Vw), int)
    first[inv] = np.arange(len(V))
    Jw, Ww = J[first], W[first]
    names = [b["name"] for b in bones]
    fam = np.arange(len(bones))
    for i, b in enumerate(bones):
        if b.get("twist"):
            fam[i] = b["parent"]
    out: dict = {}
    for k in ks:
        f = k["frame"]
        turns = rigmod.drive_twist(bones, {k["joint"]: (k["axis"], k["deg"])})
        Mv, _ = _skin_mats(bones, Jw, Ww, turns)
        P0 = np.einsum("nij,nj->ni", Mv, np.c_[Vw, np.ones(len(Vw))])[:, :3]
        d = Vw - f["pivot"]
        s = d @ f["u"]
        q = d - s[:, None] * f["u"]
        rho = np.linalg.norm(q, axis=1)
        jd, jp, jh = names.index(k["joint"]), f["of"], f["helper"]
        own = np.zeros(len(Vw))
        for c in range(Jw.shape[1]):
            fj = fam[Jw[:, c]]
            own += np.where((fj == jd) | (fj == jp) | (Jw[:, c] == jh), Ww[:, c], 0.0)
        side = np.ones(len(Vw), bool)
        if f["mid"] is not None:
            side = (Vw[:, 0] - f["mid"]) * f["side"] > -0.02
        free = (np.abs(s) < FREE * f["outer"]) & (rho < f["reach"]) & (own > 0.5) & side
        # the solved region's boundary rides LBS; a ring of the region is enough to keep the free set connected
        if TARGET == "arc":
            # the joint family's share of each vertex turned round the pivot by phi x the angle (radius kept: the
            # outer side keeps its volume and rest form, a rotation not a chord); the rest of its weights as LBS
            x_ = np.clip(s / (2 * ARC_WIDEN * (f["inner"] + (f["outer"] - f["inner"]) * (1 + ((q @ f["o"]) / np.maximum(rho, 1e-9))) / 2)) + 0.5, 0, 1)
            ph = ARC_LINEAR * x_ + (1 - ARC_LINEAR) * rigmod._sstep(x_)  # near-constant turn along the zone: an even arc
            fam_w = own.copy()
            rest_part = P0 - fam_w[:, None] * 0  # (placeholder, replaced below)
            Mo = np.zeros((len(Vw), 4, 4))
            _, Mb = _skin_mats(bones, Jw, Ww, turns)
            for c in range(Jw.shape[1]):
                fj = fam[Jw[:, c]]
                notf = ~((fj == jd) | (fj == jp) | (Jw[:, c] == jh))
                Mo += np.where(notf, Ww[:, c], 0.0)[:, None, None] * Mb[Jw[:, c]]
            other = np.einsum("nij,nj->ni", Mo, np.c_[Vw, np.ones(len(Vw))])[:, :3]
            Rv = np.stack([_rot(k["axis"], k["deg"] * x) for x in ph])
            arcp = f["pivot"] + np.einsum("nij,nj->ni", Rv, Vw - f["pivot"])
            P = P0.copy()
            P[free] = other[free] + fam_w[free, None] * arcp[free]
            del rest_part
        else:
            P = arap(Vw, Fw, P0, free)
        # contact: the inner side laid on the bisecting plane of the two segments (posed)
        Rj = _rot(k["axis"], k["deg"])
        a = f["u"] if k["joint"].endswith(("UpLeg", "Arm")) else (f["pivot"] - np.asarray(bones[jp]["head"], float))
        a = a / np.linalg.norm(a)
        cdir = Rj @ (f["u"] if k["joint"].endswith(("UpLeg", "Arm")) else _child_dir(bones, names.index(k["joint"])))
        nrm = a + cdir
        held = np.zeros(len(Vw), bool)
        if np.linalg.norm(nrm) > 1e-6:
            nrm /= np.linalg.norm(nrm)
            inner = ((Vw - f["pivot"]) @ f["o"]) < 0
            phi = rigmod._sstep(s / (2 * (f["inner"] + 1e-9)) + 0.5)
            if TARGET == "arc":
                # a soft contact: each side's inner skin is held to its own side of the bisecting plane by a soft
                # minimum (width CONTACT_SOFT): what crossed lies on the plane, what nears it flattens against it
                # (the two sides press together along a crease instead of cutting into each other in a V)
                h = (P - f["pivot"]) @ nrm
                sgn = np.where(phi < 0.5, 1.0, -1.0)  # parent side lives at h < 0, the child's at h > 0
                hh = sgn * h
                dlt = CONTACT_SOFT
                soft = -dlt * np.logaddexp(-hh / dlt, 0.0)
                band = free & inner & (hh > -4 * dlt)
                P[band] += ((soft - hh) * sgn)[band, None] * nrm
                held |= band & (hh > 0)
                if k["motion"] in RELAX:  # the region relaxed as-rigid-as-possible round what lies on the plane: the
                    P = arap(Vw, Fw, P, free & ~held)  # outer side rounds over the joint (knee, elbow)
            for _ in range(CONTACT_ROUNDS if TARGET != "arc" else 0):
                h = (P - f["pivot"]) @ nrm
                cross = free & inner & (((phi < 0.5) & (h > 0)) | ((phi >= 0.5) & (h < 0)))
                if not cross.any():
                    break
                P[cross] -= h[cross, None] * nrm
                held |= cross
                P = arap(Vw, Fw, P, free & ~held)
        T = P
        lin = Mv[:, :3, :3]
        dl = np.linalg.solve(lin, (T - P0)[:, :, None])[:, :, 0]
        dl[np.linalg.norm(dl, axis=1) < EPS] = 0.0
        out[k["name"]] = dl[inv]
        mv = np.linalg.norm(T - P0, axis=1)
        log.append(f"corrective {k['name']}: {int(free.sum())} vertices solved, {int(held.sum())} laid on the "
                   f"contact plane; move max {mv.max() * 1e3:.1f} mm, p95 {np.percentile(mv[free], 95) * 1e3 if free.any() else 0:.1f} mm")
    return out


def _rot(ax, deg):
    ax = np.asarray(ax, float) / np.linalg.norm(ax)
    t = np.radians(deg)
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    return np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K


def _child_dir(bones, i):
    ch = [c for c in _children(bones)[i] if not bones[c].get("twist") and not bones[c].get("bend")]
    d = np.asarray(bones[ch[0]]["head"], float) - np.asarray(bones[i]["head"], float)
    return d / np.linalg.norm(d)


def transfer(Vs: np.ndarray, Fs: np.ndarray, D: dict, V: np.ndarray, reach: float = 0.05) -> dict:
    """A worn part's rest-frame moves read off the skin's surface (its nearest skin vertex's, within `reach`)."""
    from scipy.spatial import cKDTree
    d, i = cKDTree(np.asarray(Vs, float)).query(np.asarray(V, float))
    fade = np.clip(1.0 - (d - 0.6 * reach) / (0.4 * reach), 0.0, 1.0)[:, None]
    return {nm: x[i] * fade for nm, x in D.items()}


def table(ks: list[dict]) -> list[dict]:
    """The json's rig.correctives rows (drivers)."""
    out = []
    for k in ks:
        lo = [x for x in ks if x["name"] == k["prev"]]
        hi = [x for x in ks if x["prev"] == k["name"]]
        out.append({"target": k["name"], "joint": k["joint"], "axis_rest": [round(float(v), 4) for v in k["axis"]],
                    "key_deg": k["deg"], "from_deg": lo[0]["deg"] if lo else 0.0,
                    "to_deg": hi[0]["deg"] if hi else None})
    return out


def vertex_normals(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    V = np.asarray(V, float)
    F = np.asarray(F)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for c in range(3):
        np.add.at(N, F[:, c], fn)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-30)
