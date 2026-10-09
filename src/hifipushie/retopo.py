"""Character topology by template wrap: a production quad base mesh (Blender Studio's CC0 "Human Base Meshes"
stylized male, `templates/`) carried onto a humanoid model through matching skeletons, so a deforming character gets
real edge loops (rings at every joint, an armhole, loops round eyes and mouth) instead of decimated triangles.

Steps (`wrap`):
1. Skeleton warp: per template bone segment a rotation, a stretch along the bone and a radius ratio per angle at 5
   stations (template radius from its own vertices, model radius from rays); vertices blend their nearest segments.
   Hands and feet scale uniformly by wrist/ankle thickness (rays across a hand hit digits and gaps).
2. Face warp: a Gaussian RBF carries template landmarks (eyes, nose tip, mouth) onto the face kit's; anchors on
   the skull stay.
3. Patches the template can't bend into (`_patches`), each cut at a closed quad loop of the template and generated
   from the model instead: digits (tubes along the hand kit's chains, rings by rays onto each digit's own
   primitives: touching fingers keep their sides; template digits the model lacks are capped), ears (the model's
   ear bones as flat tubes with equal-arc rings: a blade ear keeps its rim), eyes (rings from a loop round the
   model's eye in over its lids, a ring on the lid edge, the eyeball to its pole: rays from the lids' centre). Ear
   and eye loops are first carried onto the model's ear root / eye (`_carry`): left where the skeleton put them
   they sat behind the jaw / on the cheek.
4. Stitch, then fit the template's own vertices: shot along normals onto their region's surface, relaxed along
   the surface, generated rings held fixed (so the template flows into them); the mouth bag isn't projected.
5. Untangle: faces turned against the field smoothed and re-projected.

`quality` measures a result (field distance, turned faces, closed rings at the anatomy's loop planes).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from . import sdf, surface
from .spec import compile_prims, expand_mirror, resolve_point

TEMPLATES = Path(__file__).parent / "templates"
SEGS = [("pelvis", "chest"), ("chest", "neck"), ("neck", "head"), ("chest", "shoulder.L"), ("shoulder.L", "elbow.L"),
        ("elbow.L", "wrist.L"), ("wrist.L", "hand_end.L"), ("hip.L", "knee.L"), ("knee.L", "ankle.L"),
        ("ankle.L", "toe.L")]
FINGER_SEGS = [(f"finger{k}_{j}.L", f"finger{k}_{j + 1}.L") for k in range(1, 6) for j in range(3)] + \
              [(f"thumb_{j}.L", f"thumb_{j + 1}.L") for j in range(3)]
FACE_MODEL = {"eye.L": "face_eye.L", "nose_tip": "face_nose_tip", "mouth": "face_mouth_line_0",
              "mouth_corner.L": "face_mouth_corner.L"}
BASE_FACE = {"eye.L": "eye.L", "nose_tip": "lm_nose_tip", "mouth": "lm_lip_seam",  # a base head's landmark joints
             "mouth_corner.L": "lm_mouth_corner.L"}
NB = 16  # angle bins round a bone
STATIONS = np.linspace(0.0, 1.0, 5)  # along each bone, where radii are measured
HAND_BLEND = 0.03  # m past the wrist over which the general warp hands over to the rigidly moved hand
FAR_SIGMA = 0.35  # x sigma: the blend width between bones that share no joint (see apply in _skeleton_warp)
NEAR_SOFT = 0.25  # how softly "the nearest bone" is taken when choosing those widths (relative distance)
HAND_SIGMA = 0.5  # the hand's blend between its bones (x the distance to the nearest), tighter than the body's


# ---------------------------------------------------------------------------------------------------- template

def load_template(name: str = "male_stylized") -> dict:
    """{P verts, L loops, S sizes, J joints (mirrored), face json, name}."""
    # the name comes from the spec (base.template): only the templates shipped in templates/, never a path
    have = sorted(p.stem for p in TEMPLATES.glob("*.npz"))
    if name not in have:
        raise ValueError(f"base template {name!r}: no such template (have {', '.join(have)})")
    z = np.load(TEMPLATES / f"{name}.npz")
    J = json.loads((TEMPLATES / f"{name}_joints.json").read_text())
    return {"name": name, "P": z["verts"].astype(np.float64), "L": z["loops"].astype(np.int64),
            "S": z["sizes"].astype(np.int64), "J": _mirror({k: np.array(v, float) for k, v in J.items()
                                                            if not k.startswith("_")}),
            "face": json.loads((TEMPLATES / f"{name}_face.json").read_text())}


def is_humanoid(spec: dict) -> bool:
    s = expand_mirror(spec)
    need = ("pelvis", "chest", "neck", "head", "shoulder.L", "elbow.L", "wrist.L", "hip.L", "knee.L", "ankle.L")
    return all(j in s["joints"] for j in need)


# ---------------------------------------------------------------------------------------------------- helpers

def _unit(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def _mirror(J):
    out = dict(J)
    for n, p in J.items():
        if n.endswith(".L"):
            out[n[:-2] + ".R"] = np.array([-p[0], p[1], p[2]])
    return out


def _segments(J):
    out = []
    for a, b in SEGS + FINGER_SEGS:
        for sa, sb in ((a, b), (a.replace(".L", ".R"), b.replace(".L", ".R"))) if ".L" in a + b else ((a, b),):
            if sa in J and sb in J:
                out.append((sa, sb))
    return sorted(set(out))


def _seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(a + t[:, None] * ab - P, axis=1)


def _model_name(k):
    """Template joint -> the model's: fingers to the hand kit's chains, the thumb to its thumb."""
    m = re.fullmatch(r"finger(\d)_(\d)(\.[LR])", k)
    if m:
        return f"hand_f{m[1]}_{m[2]}{m[3]}"
    m = re.fullmatch(r"thumb_(\d)(\.[LR])", k)
    if m:
        return f"hand_th_{m[1]}{m[2]}"
    return k


def _rot_between(u, v):
    c = np.cross(u, v)
    s, d = np.linalg.norm(c), u @ v
    if s < 1e-9:
        return np.eye(3)
    k = c / s
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + s * K + (1 - d) * K @ K


def _kabsch(A, B):
    """The rotation best carrying point set A onto B (both centred on their means), or None if A is degenerate."""
    A, B = A - A.mean(0), B - B.mean(0)
    U, S, Vt = np.linalg.svd(A.T @ B)
    if S[1] < 1e-6 * max(S[0], 1e-12):
        return None
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    return Vt.T @ np.diag([1.0, 1.0, d]) @ U.T


def _hand_rotations(Jt, Jm, segs):
    """Rotations for the hand's segments (the palm, wrist -> hand_end, and every digit bone), by forward kinematics:
    the hand's rotation is the best rigid fit of its palm joints (wrist, every digit's root), and each bone's is its
    parent's composed with the minimal arc from the parent-carried axis to the bone's target axis. A hand whose joints
    are a rigid motion of the template's (a base re-posed at the elbow) thus moves as ONE piece; a curled finger
    rolls with its parent. Per-bone minimal arcs (the general rule) gave neighbouring bones of one rigidly moved hand
    different rolls, and the warp's blend averaged those mismatched frames across every finger joint: bulging
    knuckles, grooves, a ring round the thumb, nail edges cut in (up to 14 mm off on a MakeHuman body)."""
    out = {}
    for side in "LR":
        roots = [f"wrist.{side}"] + [f"finger{k}_0.{side}" for k in range(1, 6)] + [f"thumb_0.{side}"]
        roots = [n for n in roots if n in Jt and n in Jm]
        if len(roots) < 3:
            continue
        Rh = _kabsch(np.array([Jt[n] for n in roots]), np.array([Jm[n] for n in roots]))
        if Rh is None:
            continue
        mine = [sg for sg in segs if sg[0] == f"wrist.{side}" and sg[1] == f"hand_end.{side}"
                or re.fullmatch(rf"(finger\d|thumb)_\d\.{side}", sg[0])]
        mine.sort(key=lambda sg: sg[0][-3])  # digits by bone index, parents first (the palm last: it parents none)
        for a, b in mine:
            parent = next((out[sg] for sg in out if sg[1] == a), Rh)
            u0, u1 = _unit(Jt[b] - Jt[a]), _unit(Jm[b] - Jm[a])
            out[(a, b)] = _rot_between(parent @ u0, u1) @ parent
    return out


FITS = {"pelvis": ("pelvis", "chest", "hip.L", "hip.R"),  # joints where several bones start: the rotation they
        "chest": ("chest", "neck", "shoulder.L", "shoulder.R")}  # share is the best rigid fit of the joints round them
FIT_OF = {"pelvis": "pelvis", "hip.L": "pelvis", "hip.R": "pelvis", "chest": "chest"}


def _palm_roots(side):
    return [f"wrist.{side}"] + [f"finger{k}_0.{side}" for k in range(1, 6)] + [f"thumb_0.{side}"]


def _body_rotations(Jt, Jm, segs):
    """Every segment's rotation by forward kinematics, and the rigid fits ({joint: R}) its bones start from.

    Where several bones start (the pelvis and hips, the chest, a palm) their shared rotation is the best rigid fit
    (Kabsch) of the joints round them; every other bone takes its parent's rotation composed with the minimal arc from
    the parent-carried axis to its own target axis. Neighbouring bones then differ only by the bend between them (a
    consistent roll down every chain), so the warp's blend across a joint mixes two views of one motion. Per-bone
    minimal arcs (the old rule) gave neighbouring bones different rolls for the same motion and the blend averaged
    the mismatched frames: twisted shoulders and elbows, and (with the radius lookup) bodies up to 13 mm asymmetric.
    A whole skeleton moved rigidly thus moves the body rigidly. The hand's own transforms (`_hand_rotations`) use the
    same palm fit; these are the general warp's, up to the wrist."""
    def fit(names):
        names = [n for n in names if n in Jt and n in Jm]
        if len(names) < 3:
            return None
        return _kabsch(np.array([Jt[n] for n in names]), np.array([Jm[n] for n in names]))
    fits = {}
    for g, names in FITS.items():
        R = fit(names)
        if R is not None:
            fits.update({j: R for j, f in FIT_OF.items() if f == g})
    for side in "LR":
        R = fit(_palm_roots(side))
        if R is not None:
            fits.update({j: R for j in _palm_roots(side)})
    ends = {sg[1]: sg for sg in segs}
    out = {}

    def rot(sg):
        if sg not in out:
            a, b = sg
            if a in fits:
                parent = fits[a]
            elif a in ends:
                parent = rot(ends[a])
            elif re.fullmatch(r"(finger\d|thumb)_0\.[LR]", a) and f"wrist.{a[-1]}" in ends:  # no palm fit
                parent = rot(ends[f"wrist.{a[-1]}"])
            else:
                parent = np.eye(3)
            u0, u1 = _unit(Jt[b] - Jt[a]), _unit(Jm[b] - Jm[a])
            out[sg] = _rot_between(parent @ u0, u1) @ parent
        return out[sg]
    for sg in segs:
        rot(sg)
    return out, fits


def _twist(R, Rend, u0, u1):
    """The signed angle about u1 that turns R into the rotation a bone ending at a rigid fit (Rend) would have: the
    bone twists by it along its length (forearm into the palm, spine into the chest), as a real forearm does."""
    Rb = _rot_between(Rend @ u0, u1) @ Rend
    x = _frame(u1)[0]
    b = Rb @ (R.T @ x)  # Rb R^T keeps u1 (both carry u0 onto it): a turn about u1
    return float(np.arctan2(np.cross(x, b) @ u1, x @ b))


def _frame(u):
    x = np.cross(u, [0, 0, 1.0]) if abs(u[2]) < 0.9 else np.cross(u, [1.0, 0, 0])
    x /= np.linalg.norm(x)
    return x, np.cross(u, x)


def _fill(r):
    ok = np.isfinite(r)
    if not ok.any():
        return np.ones(NB)
    idx = np.arange(NB)
    return np.interp(idx, idx[ok], r[ok], period=NB)


def _template_radii(P, a, b, own, t0=0.5, band=0.15):
    u = _unit(b - a)
    x, y = _frame(u)
    q = P[own] - a
    t = q @ u / np.linalg.norm(b - a)
    q = q - np.outer(q @ u, u)
    ang = np.arctan2(q @ y, q @ x)
    rad = np.linalg.norm(q, axis=1)
    bins = ((ang + np.pi) / (2 * np.pi) * NB).astype(int) % NB
    r = np.full(NB, np.nan)
    for k in range(NB):
        m = (bins == k) & (np.abs(t - t0) < band)
        if m.sum() >= 2:
            r[k] = np.percentile(rad[m], 90)
    return _fill(r)


def _target_radii(prims, a, b, t0=0.5):
    u = _unit(b - a)
    x, y = _frame(u)
    m = a + t0 * (b - a)
    ang = (np.arange(NB) + 0.5) / NB * 2 * np.pi - np.pi
    dirs = np.cos(ang)[:, None] * x + np.sin(ang)[:, None] * y
    t = np.linspace(0, 0.5, 400)
    f = sdf.field_at(prims, m + t[None, :, None] * dirs[:, None, :], margin=0.05)
    r = np.array([t[np.flatnonzero(row > 0)[0]] if (row > 0).any() and row[0] < 0 else np.nan for row in f])
    return _fill(r)


def topology(L, S):
    """faces (lists), vertex neighbours {v: set}, edge -> faces {(a, b) sorted: [face]}."""
    st = np.r_[0, np.cumsum(S)[:-1]]
    faces = [list(map(int, L[s:s + k])) for s, k in zip(st, S)]
    nb, ef = {}, {}
    for fi, f in enumerate(faces):
        for k in range(len(f)):
            a, b = f[k], f[(k + 1) % len(f)]
            nb.setdefault(a, set()).add(b)
            nb.setdefault(b, set()).add(a)
            ef.setdefault((min(a, b), max(a, b)), []).append(fi)
    return faces, nb, ef


def _walk(u, v, faces, nb, ef, limit=64):
    """Follow a quad edge loop from edge u->v (straight across every valence-4 vertex): (path, closed)."""
    path = [u, v]
    while len(path) < limit:
        if len(nb[v]) != 4:
            return path, False
        ws = set()
        for fi in ef[(min(u, v), max(u, v))]:
            f = faces[fi]
            if len(f) != 4:
                return path, False
            i = f.index(v)
            ws.add(f[(i + 1) % 4] if f[(i - 1) % 4] == u else f[(i - 1) % 4])
        rest = nb[v] - {u} - ws
        if len(rest) != 1:
            return path, False
        u, v = v, rest.pop()
        if v == path[0]:
            return path, True
        path.append(v)
    return path, False


def _tip_side(loop, nb, tip):
    """Vertices reached from tip without crossing the loop."""
    seen, stack, stop = {tip}, [tip], set(loop)
    while stack:
        v = stack.pop()
        for w in nb[v]:
            if w not in seen and w not in stop:
                seen.add(w)
                stack.append(w)
    return seen


def tris(L, S):
    st = np.r_[0, np.cumsum(S)[:-1]]
    return np.array([(L[s], L[s + j], L[s + j + 1]) for s, n in zip(st, S) for j in range(1, n - 1)])


def edges(L, S):
    st = np.r_[0, np.cumsum(S)[:-1]]
    e = {(min(L[s + j], L[s + (j + 1) % n]), max(L[s + j], L[s + (j + 1) % n])) for s, n in zip(st, S)
         for j in range(n)}
    return np.array(sorted(e))


def _vnormals(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], fn)
    return N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)


def _lap(X, E, deg):
    acc = np.zeros_like(X)
    np.add.at(acc, E[:, 0], X[E[:, 1]])
    np.add.at(acc, E[:, 1], X[E[:, 0]])
    return acc / np.maximum(deg, 1)[:, None] - X


# ---------------------------------------------------------------------------------------------------- warps

def _skeleton_warp(P, Jt, s, prims, sigma=0.8, girth=None):
    """Template vertices carried by the skeleton. Radii per angle follow the model's surface (rays onto prims), or,
    with girth ({segment start joint: scale}, for the base mesh: there is no surface yet), the template's own
    scaled (read at the template's own angle: no frame offset). Each bone's rotation by forward kinematics
    (`_body_rotations`; the hand's past the wrist by `_hand_rotations`), a bone ending at a rigid fit twisting into
    it along its length; vertices blend the bones' transforms by distance (sigma x the distance to the nearest bone),
    related bones (a shared joint or fit) over that width, others over FAR_SIGMA of it (base bodies; a wrap keeps
    the full width for all).
    Returns (warped, segments, dominant segment per vertex, apply, model joints)."""
    Jt = dict(Jt)
    Jm = {}
    for k in Jt:  # the model may use the template's names (a base mesh) or the kits' (hand_f<n>_<k>)
        for n in (k, _model_name(k)):
            if n in s["joints"]:
                Jm[k] = resolve_point(s, n)
                break
    for side in "LR":  # the palm: wrist to the middle knuckle (the template's second finger, the model's second
        # or only finger)
        mk = next((n for n in (f"finger2_0.{side}", f"hand_f2_0.{side}", f"hand_f1_0.{side}") if n in s["joints"]), None)
        if f"finger2_0.{side}" in Jt and mk:
            Jt[f"hand_end.{side}"] = Jt[f"finger2_0.{side}"]
            Jm[f"hand_end.{side}"] = resolve_point(s, mk)
        elif f"wrist.{side}" in Jt and f"elbow.{side}" in Jt and f"wrist.{side}" in Jm:
            for J in (Jt, Jm):
                w, e = J[f"wrist.{side}"], J[f"elbow.{side}"]
                J[f"hand_end.{side}"] = w + _unit(w - e) * 0.45 * np.linalg.norm(w - e)
    segs = [sg for sg in _segments(Jt) if sg[0] in Jm and sg[1] in Jm]
    near = np.stack([_seg_dist(P, Jt[a], Jt[b]) for a, b in segs], 1).argmin(1)
    hand = _hand_rotations(Jt, Jm, segs)
    body, fits = _body_rotations(Jt, Jm, segs)
    xf, xh = [], {}
    for k, (a, b) in enumerate(segs):
        a0, b0, a1, b1 = Jt[a], Jt[b], Jm[a], Jm[b]
        u0, u1 = _unit(b0 - a0), _unit(b1 - a1)
        if girth is not None:
            R0 = np.stack([_template_radii(P, a0, b0, near == k, t0) for t0 in STATIONS])
            R1 = R0 * float(girth.get(a, 1.0))
        elif b.startswith(("hand_end", "toe")):
            prox = [sg for sg in segs if sg[1] == a][0]
            pk = segs.index(prox)
            rw0 = np.median(_template_radii(P, Jt[prox[0]], Jt[prox[1]], near == pk, 0.9))
            rw1 = np.median(_target_radii(prims, Jm[prox[0]], Jm[prox[1]], 0.9))
            R0, R1 = np.full((len(STATIONS), NB), rw0), np.full((len(STATIONS), NB), rw1)
        else:
            R0 = np.stack([_template_radii(P, a0, b0, near == k, t0) for t0 in STATIONS])
            R1 = np.stack([_target_radii(prims, a1, b1, t0) for t0 in STATIONS])
        x1, y1 = _frame(u1)
        x0, y0 = _frame(u0)
        g = dict(a0=a0, u0=u0, a1=a1, u1=u1, sax=np.linalg.norm(b1 - a1) / np.linalg.norm(b0 - a0),
                 L0=np.linalg.norm(b0 - a0), R0=R0, R1=R1, x0=x0, y0=y0, tw=0.0)
        Rb = body[(a, b)]
        # a bone ending where a rigid fit starts (forearm -> palm, spine -> chest) twists along its length from its
        # own (parent-carried) roll to the fit's, so neither joint carries the whole turn
        tw = _twist(Rb, fits[b], u0, u1) if b in fits else 0.0
        for R, into, t_ in ((Rb, None, tw), (hand.get((a, b)), k, 0.0)):
            if R is None:
                continue
            xr = R @ x0
            # R1 is looked up at the point's angle in the target's frame (ang + off; + the twist along the bone),
            # as _target_radii measures it. A girth R1 is the template's own (its frame): no offset, or the radii
            # are read round the bone by the frames' twist (fingers stretched by up to ~15 mm; bodies up to 13 mm
            # asymmetric, as _frame isn't mirror-symmetric)
            off = 0.0 if girth is not None else np.arctan2(xr @ y1, xr @ x1)
            h = dict(g, R=R, off=off, tw=t_)
            if into is None:
                xf.append(h)
            else:
                xh[into] = h
    centres = (np.arange(NB) + 0.5) / NB * 2 * np.pi - np.pi
    # where the hand moves as one piece (the FK transforms in xh) instead of by the general per-bone warp: past
    # the template's wrist (ramped over HAND_BLEND along the forearm) and only where the arm's own bones carry the
    # point (the thigh beside a hanging hand keeps the warp: the body stays as it was outside the hands)
    arms = []
    for side in "LR":
        e, w = f"elbow.{side}", f"wrist.{side}"
        mine = [k for k, sg in enumerate(segs) if k in xh and sg[0].endswith(f".{side}")]
        if mine and e in Jt and w in Jt:
            chain = mine + [k for k, sg in enumerate(segs) if sg == (e, w)]
            arms.append((mine, chain, Jt[w], _unit(Jt[w] - Jt[e])))

    def smooth(x):
        x = np.clip(x, 0, 1)
        return x * x * (3 - 2 * x)

    def carry(g, X):
        q = X - g["a0"]
        t = q @ g["u0"]
        rad = q - np.outer(t, g["u0"])
        ang = np.arctan2(rad @ g["y0"], rad @ g["x0"])
        tc = np.clip(t / g["L0"], 0, 1)
        tgt = np.zeros(len(X))
        src = np.zeros(len(X))
        for i in range(len(STATIONS) - 1):
            lo, hi = STATIONS[i], STATIONS[i + 1]
            m = (tc >= lo) & (tc <= hi)
            w = (tc[m] - lo) / (hi - lo)
            ai = (ang[m] + g["off"] + g["tw"] * tc[m] + np.pi) % (2 * np.pi) - np.pi
            tgt[m] = (1 - w) * np.interp(ai, centres, g["R1"][i], period=2 * np.pi) + \
                w * np.interp(ai, centres, g["R1"][i + 1], period=2 * np.pi)
            src[m] = (1 - w) * np.interp(ang[m], centres, g["R0"][i], period=2 * np.pi) + \
                w * np.interp(ang[m], centres, g["R0"][i + 1], period=2 * np.pi)
        rs = np.clip(tgt / np.maximum(src, 1e-3), 0.3, 4.0)
        v = (np.outer(t * g["sax"], g["u0"]) + rad * rs[:, None]) @ g["R"].T
        if g["tw"]:  # the twist along the bone (0 at its start, all of it at its end), about the target axis
            u, phi = g["u1"], g["tw"] * tc
            c, s = np.cos(phi)[:, None], np.sin(phi)[:, None]
            v = v * c + np.cross(u, v) * s + np.outer(v @ u, u) * (1 - c)
        return g["a1"] + v

    # blend only across a joint's own region: bones that share a joint (or a rigid fit: pelvis and hips, the chest,
    # a palm) blend over the full width; any other pair only where their distances are nearly equal. A wide blend
    # between unrelated bones pulled the neck's base with the upper arms, a clavicle with the forearm, an inner
    # thigh with the other leg. The width is chosen by how related each bone is to the softly nearest ones, so the
    # weights stay continuous where the nearest bone changes. Base bodies only: a model's wrap (no girth) is a first
    # guess before projection and its untangling did ~7% worse (more turned faces on goblin/troll) with it
    far = FAR_SIGMA if girth is not None else 1.0
    # related: a shared joint, or one bone starts at a fit whose root joint (pelvis, chest, wrist) the other has (the
    # thighs relate to the spine, not to each other; the digits to the palm and forearm, not to each other)
    root = {**{j: g for j, g in FIT_OF.items()}, **{j: f"wrist.{j[-1]}" for s_ in "LR" for j in _palm_roots(s_)}}
    near_ = np.array([[bool(set(p) & set(q)) or root.get(p[0]) in q or root.get(q[0]) in p for q in segs]
                      for p in segs], float)

    def apply(X):
        Dx = np.stack([_seg_dist(X, Jt[a], Jt[b]) for a, b in segs], 1)
        d0 = Dx.min(1, keepdims=True)
        rel = (Dx - d0) / np.maximum(d0, 0.01)
        pk = np.exp(-(rel / NEAR_SOFT) ** 2)
        sig = sigma * (far + (1 - far) * (pk / pk.sum(1, keepdims=True)) @ near_)
        W = np.exp(-(rel / sig) ** 2)
        W /= W.sum(1, keepdims=True)
        out = np.zeros_like(X)
        for k, g in enumerate(xf):
            out += W[:, k:k + 1] * carry(g, X)
        for mine, chain, w0, ax in arms:
            h = smooth((X - w0) @ ax / HAND_BLEND) * smooth((W[:, chain].sum(1) - 0.5) / 0.4)
            sel = h > 0
            if not sel.any():
                continue
            # past the wrist: the hand's own bones only (palm and digits, their FK transforms), blended tighter than
            # the body's (HAND_SIGMA) so a re-posed finger bends at its joints. With joints that keep the template's
            # hand pose every one of these transforms is the same rigid motion: the hand moves as one. (The forearm
            # stays out: its minimal arc rolls differently, 4 mm off at the base of the thumb.)
            Xs, D = X[sel], Dx[sel][:, mine]
            dh = D.min(1, keepdims=True)
            Wh = np.exp(-((D - dh) / (HAND_SIGMA * np.maximum(dh, 0.004))) ** 2)
            Wh /= Wh.sum(1, keepdims=True)
            moved = sum(Wh[:, j:j + 1] * carry(xh[k], Xs) for j, k in enumerate(mine))
            out[sel] += h[sel, None] * (moved - out[sel])
        return out, W

    out, W = apply(P)
    return out, segs, W.argmax(1), apply, Jm


def _face_warp(out, apply, face, s, log, extra=(), names=None):
    """Gaussian RBF: template landmarks (warped by the skeleton) onto the face kit's (or `names`: a base head's
    landmark joints); skull anchors stay."""
    src, dst = [], []
    for name, pt in face["landmarks"].items():
        mn = (names or FACE_MODEL).get(name)
        if name == "eye.L" and len(extra):  # the eye loops' targets place the eyes (eyeball centres don't agree
            # with them: a goblin's bulging eye sits far forward of a human's)
            continue
        pairs = [(pt, mn)]
        if name.endswith(".L"):
            pairs.append(([-pt[0], pt[1], pt[2]], mn.replace(".L", ".R") if mn else None))
        for p_, m_ in pairs:
            if m_ is None:
                continue
            if m_ in s["joints"]:
                tgt = resolve_point(s, m_)
            elif m_ in s["blobs"]:
                bl = s["blobs"][m_]
                tgt = resolve_point(s, bl.get("at", [0, 0, 0])) + np.array(bl.get("offset", [0, 0, 0]), float)
            else:
                continue
            src.append(p_)
            dst.append(tgt)
    if not src:
        return out
    ws, _ = apply(np.array(src, float))
    disp = np.array(dst) - ws
    if len(extra):  # cut loops' targets (eyes, ears): (warped template points, model points)
        ws = np.r_[ws, np.array([p for p, _ in extra])]
        disp = np.r_[disp, np.array([q - p for p, q in extra])]
        dst = list(dst) + [q for _, q in extra]
    wa, _ = apply(np.array(list(face["anchors"].values()), float))
    C = np.r_[ws, wa]
    Dd = np.r_[disp, np.zeros_like(wa)]
    sig = max(0.6 * np.linalg.norm(ws[0] - ws[1]) if len(ws) > 1 else 0.05, 0.03)
    Phi = np.exp(-(np.linalg.norm(C[:, None] - C[None], axis=2) / sig) ** 2) + 1e-6 * np.eye(len(C))
    wts = np.linalg.solve(Phi, Dd)
    phi = np.exp(-(np.linalg.norm(out[:, None] - C[None], axis=2) / sig) ** 2)
    log.append(f"face: {len(src)} landmarks, largest move {np.linalg.norm(disp, axis=1).max() * 1000:.0f} mm")
    return out + phi @ wts


def _carry(out, loop, dst):
    """Move a loop of the warped template to dst, the surface round it following (Shepard-weighted loop moves,
    fading over about the loop's size)."""
    src = out[loop]
    disp = dst - src
    size = np.linalg.norm(src - src.mean(0), axis=1).max()
    d = np.linalg.norm(out[:, None] - src[None], axis=2)
    w = 1.0 / (d + 1e-4) ** 2
    shep = (w @ disp) / w.sum(1, keepdims=True)
    out = out + np.exp(-(d.min(1) / size) ** 2)[:, None] * shep
    out[loop] = dst
    return out


def _smooth_away(V, E, mask, rounds=40):
    """Smooth a region into a plain form, the rest fixed (toes over a club foot)."""
    deg = np.bincount(E.ravel(), minlength=len(V))
    V = V.copy()
    for _ in range(rounds):
        V[mask] += 0.6 * _lap(V, E, deg)[mask]
    return V


# ---------------------------------------------------------------------------------------------------- loops

def _base_loop(P, faces, nb, ef, base, axis, tipv, max_tip=400, near=0.03):
    """The closed loop round a digit nearest its base: across the axis, all the way round (every 45 degree
    sector), cutting off at most max_tip vertices on the tip's side."""
    best, seen = None, set()
    L = np.linalg.norm(P[tipv] - base)
    for (a, b) in ef:
        pa = P[a] - base
        sa = pa @ axis
        if not (0.08 * L < sa < 0.7 * L) or np.linalg.norm(pa - sa * axis) > near:
            continue
        e = P[b] - P[a]
        if abs(e @ axis) > 0.35 * np.linalg.norm(e) or (a, b) in seen:
            continue
        path, closed = _walk(a, b, faces, nb, ef)
        for k in range(len(path)):
            seen.add((path[k], path[(k + 1) % len(path)]))
        if not closed or not 6 <= len(path) <= 16:
            continue
        q = P[path] - base
        s = float(np.mean(q @ axis))
        r = q - q.mean(0)
        r -= np.outer(r @ axis, axis)
        x = r[0] / np.linalg.norm(r[0])
        ang = np.degrees(np.arctan2(r @ np.cross(axis, x), r @ x)) % 360
        if len(set((ang // 45).astype(int))) < 8 or len(_tip_side(path, nb, tipv)) > max_tip:
            continue
        if best is None or s < best[0]:
            best = (s, path)
    return None if best is None else best[1]


def _loops_round(P, faces, nb, ef, near, limit):
    """Closed loops through the `near` vertices: yields paths."""
    seen = set()
    for (a, b) in ef:
        if a not in near or (a, b) in seen:
            continue
        path, closed = _walk(a, b, faces, nb, ef, limit=limit)
        for k in range(len(path)):
            seen.add((path[k], path[(k + 1) % len(path)]))
            seen.add((path[(k + 1) % len(path)], path[k]))
        if closed and len(path) >= 6:
            yield path


def _ear_loop(P, faces, nb, ef, tip_pt, reach=0.07, max_cut=800):
    """The outermost closed loop round the template's ear (cutting off the most vertices, at most max_cut, all on
    the ear's side): where the ear leaves the skull. Returns (loop, tip vertex)."""
    tipv = int(np.argmin(np.linalg.norm(P - tip_pt, axis=1)))
    best = None
    for path in _loops_round(P, faces, nb, ef, set(np.flatnonzero(np.linalg.norm(P - tip_pt, axis=1) < reach)), 120):
        if not (np.sign(P[path, 0]) == np.sign(tip_pt[0])).all() or tipv in path:
            continue
        cut = len(_tip_side(path, nb, tipv))
        if cut <= max_cut and (best is None or cut > best[0]):
            best = (cut, path)
    return (None, None) if best is None else (best[1], tipv)


def _eye_loop(P, faces, nb, ef, eye, r_target, reach=0.06):
    """The closed loop round the template's eye (winding once round the y axis through it) whose mean radius is
    nearest r_target, the frontmost of equals (the socket tunnel's loops wind too). Returns (loop, inner vertex)."""
    q = P - eye
    near = set(np.flatnonzero((np.hypot(q[:, 0], q[:, 2]) < reach) & (q[:, 1] < 0.03)))
    best = None
    for path in _loops_round(P, faces, nb, ef, near, 200):
        Q = q[path]
        ang = np.arctan2(Q[:, 2], Q[:, 0])
        wn = np.sum((np.diff(np.r_[ang, ang[:1]]) + np.pi) % (2 * np.pi) - np.pi) / (2 * np.pi)
        if abs(round(wn)) != 1:
            continue
        key = (abs(np.hypot(Q[:, 0], Q[:, 2]).mean() - r_target), Q[:, 1].mean())
        if best is None or key < best[0]:
            best = (key, path)
    if best is None:
        return None, None
    inside = [v for v in near if np.hypot(q[v, 0], q[v, 2]) < 0.3 * r_target and v not in best[1]]
    return best[1], (int(inside[np.argmin([q[v, 1] for v in inside])]) if inside else None)


# ---------------------------------------------------------------------------------------------------- patches

def _shoot(prims, c, u, r_guess):
    """First exit along c + t u (c inside), t up to 4 r_guess."""
    t = np.linspace(0, 4 * r_guess, 160)
    f = sdf.field_at(prims, c[None] + t[:, None] * u[None], clip=False)
    k = np.flatnonzero(f > 0)
    if f[0] > 0 or not len(k):
        return c + r_guess * u
    k = k[0]
    t0, t1, f0, f1 = t[k - 1], t[k], f[k - 1], f[k]
    return c + (t0 + (t1 - t0) * f0 / (f0 - f1)) * u


def _exit(prims, c, dirs, reach, steps=240):
    """Where rays from c (inside) first leave the surface: (points, distances)."""
    t = np.linspace(0, reach, steps)
    f = sdf.field_at(prims, c[None, None] + t[None, :, None] * dirs[:, None], margin=0.02)
    out = f > 0
    k = np.maximum(np.where(out.any(1), out.argmax(1), steps - 1), 1)
    i = np.arange(len(dirs))
    f0, f1 = f[i, k - 1], f[i, k]
    tt = t[k - 1] + (t[k] - t[k - 1]) * np.clip(f0 / np.where(f0 - f1 == 0, -1, f0 - f1), 0, 1)
    return c + tt[:, None] * dirs, tt


def _chain_point(C, s):
    seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    s = np.clip(s, 0, cum[-1])
    i = min(np.searchsorted(cum, s, side="right") - 1, len(seg) - 1)
    d = (C[i + 1] - C[i]) / seg[i]
    return C[i] + (s - cum[i]) * d, d, cum


def _ring_arc(prims, c, d, ref, n, sign, r_guess, rays=96):
    """n points round the cross-section (plane through c, normal d) at equal arc length from direction ref: flat
    sections keep their thin edges (equal angles bunch points on the flat faces and leave the rim bare)."""
    e2 = np.cross(d, ref)
    a = sign * np.linspace(0, 2 * np.pi, rays, endpoint=False)
    P = np.array([_shoot(prims, c, np.cos(x) * ref + np.sin(x) * e2, r_guess) for x in a])
    Q = np.r_[P, P[:1]]
    cum = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    t = np.arange(n) / n * cum[-1]
    return np.stack([np.interp(t, cum, Q[:, k]) for k in range(3)], 1)


def _clear_start(C, own, full, r_guess, s_max, tol=3e-4):
    """First arc length along chain C whose cross-section on the part's own primitives lies on the whole field's
    surface (clear of the skull and its fillet)."""
    for s in np.linspace(0.0, s_max, 12):
        p, d, _ = _chain_point(C, s)
        ref, e2 = _frame(d)
        a = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        ring = np.array([_shoot(own, p, np.cos(x) * ref + np.sin(x) * e2, r_guess) for x in a])
        if np.abs(sdf.field_at(full, ring, clip=False)).max() < tol:
            return s
    return s_max


def _loop_frame(pts, d):
    q = pts - pts.mean(0)
    q -= np.outer(q @ d, d)
    ref = q[0] / np.linalg.norm(q[0])
    ang = np.arctan2(q @ np.cross(d, ref), q @ ref)
    dw = (np.diff(np.r_[ang, ang[:1]]) + np.pi) % (2 * np.pi) - np.pi
    return ref, ang, (1.0 if np.median(dw) > 0 else -1.0)


def _tube(loop_pts, C, prims, r_guess, spacing, knuckles=True, tang=None, turn=None):
    """A digit: rings (the loop's count, its angles carried along chain C) from a finger radius past the knuckle
    to the tip, spacing apart, extra rings either side of each knuckle, a 45 degree ring and a fan at the tip."""
    cum = _chain_point(C, 0)[2]
    s0 = min(1.5 * r_guess, 0.3 * cum[-1])
    p0, d0, _ = _chain_point(C, s0)
    ref, ang, _ = _loop_frame(loop_pts, d0)
    if tang is not None:  # the steps round from the template's own clean digit (a warped loop can fold: its angles ran
        # backwards and turned the tube inside out)
        ang = ang[0] + (np.asarray(tang) - tang[0])
    if turn is not None:
        dw = (np.diff(ang) + np.pi) % (2 * np.pi) - np.pi
        if np.sign(np.median(dw)) != turn:
            ang = ang[0] - (ang - ang[0])
    stations = list(np.arange(s0 + spacing, cum[-1] - 0.3 * spacing, spacing))
    if knuckles:
        stations += [x for kn in cum[1:-1] if kn > s0 + 0.5 * spacing for x in (kn - 0.3 * spacing, kn + 0.3 * spacing)]
    stations = sorted(stations)
    stations = [s for i, s in enumerate(stations) if i == 0 or s - stations[i - 1] > 0.25 * spacing] + [cum[-1]]

    def ring(p, d, ref, lift=0.0):
        e2 = np.cross(d, ref)
        dirs = np.cos(ang)[:, None] * ref + np.sin(ang)[:, None] * e2
        out = np.array([_shoot(prims, p, _unit(u + lift * d), r_guess) for u in dirs])
        if not lift:  # again from the section's own centre: a chain near the skin (a base's finger joints lie by
            # the back of the finger) shot rays out through the near side and turned the tube inside out
            c = out.mean(0)
            c = p + (c - p) - d * ((c - p) @ d)
            if float(sdf.field_at(prims, c[None], margin=0.05)[0]) < 0:
                out = np.array([_shoot(prims, c, _unit(u), r_guess) for u in dirs])
        return out
    rings = [ring(p0, d0, ref)]
    for s in stations:
        p, d, _ = _chain_point(C, s)
        ref = _unit(ref - d * (ref @ d))
        rings.append(ring(p, d, ref))
    d = _unit(C[-1] - C[-2])
    rings.append(ring(C[-1], d, ref, 1.0))
    return rings, _shoot(prims, C[-1], d, r_guess)


def _arc_tube(loop_pts, C, prims, r_guess, s0, min_step=0.4):
    """A flat appendage (a blade ear): equal-arc rings, each a ring's perimeter / count further on (square quads,
    at least min_step x the first spacing), from s0 to the tip."""
    p0, d0, cum = _chain_point(C, s0)
    ref, _, sign = _loop_frame(loop_pts, d0)
    n = len(loop_pts)
    per = lambda R: np.linalg.norm(np.diff(np.r_[R, R[:1]], axis=0), axis=1).sum()
    rings = [_ring_arc(prims, p0, d0, ref, n, sign, r_guess)]
    sp0 = per(rings[0]) / n
    s = s0
    while True:
        s += max(per(rings[-1]) / n, min_step * sp0)
        if s > cum[-1] - 0.3 * sp0:
            break
        p, d, _ = _chain_point(C, s)
        ref = _unit(ref - d * (ref @ d))
        rings.append(_ring_arc(prims, p, d, ref, n, sign, r_guess))
    return rings, _shoot(prims, C[-1], _unit(C[-1] - C[-2]), r_guess)


def _eye_margins(c, rot, prims, reach, the, phi_max=1.3, n_samp=200):
    """Per azimuth round the lids (frame rot at c, looking along local -y), the angle off the axis where the first
    exit of rays from c drops from lid to eyeball (the lid edge), median-smoothed round the eye; zeros if shut."""
    pm = np.zeros(len(the))
    ph = np.linspace(phi_max, 0.0, n_samp)
    for i, t in enumerate(the):
        loc = np.stack([np.sin(ph) * np.cos(t), -np.cos(ph), np.sin(ph) * np.sin(t)], -1)
        _, R = _exit(prims, c, loc @ rot.T, reach)
        jump = np.diff(R)
        m = int(np.argmin(jump))
        pm[i] = 0.5 * (ph[m] + ph[m + 1]) if jump[m] < -0.05 * R[m] else np.nan  # no step: the lids meet here
    ok = np.isfinite(pm)
    if ok.sum() < 3:
        return np.zeros(len(the))
    idx = np.arange(len(the))
    pm = np.interp(idx, idx[ok], pm[ok], period=len(the))
    return np.median(np.stack([np.roll(pm, k) for k in range(-2, 3)]), 0)


def _eye_rings(loop_pts, c, rot, prims, reach, voxel, n_samp=200):
    """An eye from a loop round it (on the lids, within their cone): rings over the lid down to its edge, a ring on
    the eyeball under the edge, the eyeball in to its pole. All by rays from the lids' centre c (frame rot,
    looking along local -y: the opening's walls are radial, so near the eye the surface is star-shaped from c);
    along each spoke (a loop vertex's azimuth) the first exit drops from lid to eyeball at the margin. Margins are
    median-smoothed round the eye (one spoke caught the brow's edge and spiked)."""
    n = len(loop_pts)
    q = (loop_pts - c) @ rot
    phi0 = np.arccos(np.clip(-q[:, 1] / np.linalg.norm(q, axis=1), -1, 1))
    th = np.arctan2(q[:, 2], q[:, 0])

    def world(phi, the):
        return np.stack([np.sin(phi) * np.cos(the), -np.cos(phi) * np.ones_like(the), np.sin(phi) * np.sin(the)],
                        -1) @ rot.T

    def ring(phi):
        return _exit(prims, c, world(phi, th), reach)[0]
    pm = _eye_margins(c, rot, prims, reach, th)
    shut = not pm.any()
    dphi = 0.012  # either side of the margin (margins are found to 1.3 / 200 rad)
    sp = np.linalg.norm(np.diff(np.r_[loop_pts, loop_pts[:1]], axis=0), axis=1).sum() / n
    edge = ring(pm + dphi)
    n_lid = max(1, int(round(np.linalg.norm(edge - loop_pts, axis=1).mean() / sp)))
    rings = [loop_pts.copy()] + [ring(phi0 + (pm + dphi - phi0) * k / n_lid) for k in range(1, n_lid)] + [edge]
    if not shut:
        ball = ring(np.maximum(pm - dphi, 0))
        n_ball = int(round(np.linalg.norm(ball - _exit(prims, c, world(np.zeros(1), np.zeros(1)), reach)[0],
                                          axis=1).mean() / sp))
        rings += [ring(np.maximum(pm - dphi, 0) * (1 - k / (n_ball + 1))) for k in range(n_ball + 1)]
    return rings, _exit(prims, c, world(np.zeros(1), np.zeros(1)), reach)[0][0]


def _ear_chain(s, side):
    """The model's ear: bones named ear* on one side, chained from the midline out. (points, bone names, radius)."""
    bs = {n: b for n, b in s["bones"].items() if n.startswith("ear") and n.endswith("." + side)}
    if not bs:
        return None
    pos = lambda j: np.asarray(resolve_point(s, j), float)
    first = min((b["a"] for b in bs.values()), key=lambda j: abs(pos(j)[0]))
    C, j, left = [pos(first)], first, dict(bs)
    while True:
        nxt = [(n, b) for n, b in left.items() if j in (b["a"], b["b"])]
        if not nxt:
            break
        n, b = nxt[0]
        j = b["b"] if b["a"] == j else b["a"]
        C.append(pos(j))
        del left[n]
    r = max(float(s["joints"][e].get("r", 0.01)) for b in bs.values() for e in (b["a"], b["b"]))
    return np.array(C), set(bs), r


def _plan_cuts(W, tpl, s, prims):
    """Cut loops on the template: {key: {"loop", "inner" (a vertex inside), "kind" (digit/ear/eye), and for ears and
    eyes "target": where the loop goes on the model}}, from the skeleton-warped template W."""
    P, face = tpl["P"], tpl["face"]
    faces, nb, ef = topology(tpl["L"], tpl["S"])
    names = {p.name for p in prims}
    out = {}
    for side, sg in (("L", 1.0), ("R", -1.0)):
        for tn, mn in [(f"finger{k}", f"hand_f{k}") for k in range(1, 5)] + [("thumb", "hand_th")]:
            if f"{tn}_0.{side}" not in tpl["J"]:
                continue
            ch = np.array([tpl["J"][f"{tn}_{j}.{side}"] for j in range(4)])
            ax = _unit(ch[-1] - ch[0])
            near_tip = np.flatnonzero(np.linalg.norm(P - ch[-1], axis=1) < 0.03)
            tip = int(near_tip[np.argmax((P[near_tip] - ch[0]) @ ax)])
            loop = _base_loop(P, faces, nb, ef, ch[0], ax, tip)
            if loop is not None:
                # which way round the rings must run for the tube's quads to face out: _stitch winds them against
                # the kept face along loop[0] -> loop[1] (outward needs the angle to rise when that edge isn't kept)
                drop = _tip_side(loop, nb, tip) - set(loop)
                fwd = any(f[k] == loop[0] and f[(k + 1) % len(f)] == loop[1] for f in faces
                          if not any(v in drop for v in f) for k in range(len(f)))
                out[f"{tn}.{side}"] = {"loop": loop, "inner": tip, "kind": "digit", "model": mn, "side": side,
                                       "tang": _loop_frame(P[loop], ax)[1], "turn": -1.0 if fwd else 1.0}
        if "ear_tip" in face:
            loop, tipv = _ear_loop(P, faces, nb, ef, np.array(face["ear_tip"]) * [sg, 1, 1])
            if loop is not None:
                cut = {"loop": loop, "inner": tipv, "kind": "ear"}
                chain = _ear_chain(s, side)
                if chain is not None:
                    C, bn, r = chain
                    own = [p for p in prims if p.name in bn]
                    s0 = _clear_start(C, own, prims, r, 0.5 * np.linalg.norm(C[-1] - C[0]))
                    p0, d0, _ = _chain_point(C, s0)
                    ref, _, sign = _loop_frame(W[loop], d0)
                    cut.update(chain=(C, own, r, s0), target=_ring_arc(own, p0, d0, ref, len(loop), sign, r))
                out[f"ear.{side}"] = cut
        if "eye_cut" in face and f"face_lids.{side}" in names:
            loop, inner = _eye_loop(P, faces, nb, ef, np.array(face["landmarks"]["eye.L"]) * [sg, 1, 1],
                                    face["eye_cut"])
            if loop is not None and inner is not None:
                lp = next(p for p in prims if p.name == f"face_lids.{side}")
                c, rot, ro = lp.params["c"], lp.params["rot"], lp.params["ro"]
                q = (W[loop] - c) @ rot
                th = np.arctan2(q[:, 2], q[:, 0])
                dw = (np.diff(np.r_[th, th[:1]]) + np.pi) % (2 * np.pi) - np.pi
                the = th[0] + np.sign(np.median(dw)) * np.arange(len(loop)) / len(loop) * 2 * np.pi
                # the loop follows the lid edge's shape, eye_phi (radians off the lids' axis) outside it: at a fixed
                # angle it crossed a wide almond opening at the corners
                pm = _eye_margins(c, rot, prims, 3 * ro, the)
                phi = np.minimum(pm + face.get("eye_phi", 0.4), 1.3)
                loc = np.stack([np.sin(phi) * np.cos(the), -np.cos(phi), np.sin(phi) * np.sin(the)], -1)
                out[f"eye.{side}"] = {"loop": loop, "inner": inner, "kind": "eye", "lids": (c, rot, ro),
                                      "target": _exit(prims, c, loc @ rot.T, 4 * ro)[0]}
    return out


def _patches(W, cuts, s, prims, voxel, log):
    """The model's own patch per cut (loops with a target carried there first, moving W): {key: (loop, inner,
    (rings, tip) or None for a cap)}."""
    for cut in cuts.values():
        if "target" in cut:
            W[:] = _carry(W, cut["loop"], cut["target"])
    out = {}
    for key, cut in cuts.items():
        loop, patch = cut["loop"], None
        if cut["kind"] == "digit":
            mn, side = cut["model"], cut["side"]
            if f"{mn}_0.{side}" in s["joints"]:
                C = np.array([resolve_point(s, f"{mn}_{j}.{side}") for j in range(4)])
                own = [p for p in prims if p.name.startswith(mn + "_") and p.name.endswith("." + side)]
                r = float(s["joints"][f"{mn}_1.{side}"].get("r", 0.01))
                ft = float(sdf.field_at(own or prims, C[-1:], margin=0.05)[0])
                if ft > -0.6 * r:  # a tip joint on the skin (a base's): back inside by a tip radius, or the last
                    # rings shot from the surface and the fingertips came out as bulbs
                    C[-1] = C[-1] - _unit(C[-1] - C[-2]) * (ft + 0.8 * r)
                patch = _tube(W[loop], C, own or prims, r, 2 * np.pi * r / len(loop), tang=cut.get("tang"), turn=cut.get("turn"))
                # the loop carried to just before the first ring: the skeleton warp can leave a digit's base loop
                # on its neighbour (a base's close-set fingers: the index tube twisted across from the middle one)
                d0 = _unit(C[1] - C[0])
                dst = np.asarray(patch[0][0]) - d0 * (0.8 * r)
                if cut.get("carry") and np.linalg.norm(W[loop].mean(0) - dst.mean(0)) > 0.5 * r:
                    W[:] = _carry(W, loop, dst)
        elif cut["kind"] == "ear" and "chain" in cut:
            C, own, r, s0 = cut["chain"]
            patch = _arc_tube(W[loop], C, own, r, s0)
        elif cut["kind"] == "eye":
            c, rot, ro = cut["lids"]
            patch = _eye_rings(W[loop], c, rot, prims, 3 * ro, voxel)  # noqa
        out[key] = (loop, cut["inner"], patch)
        log.append(f"{key}: loop of {len(loop)}, " + ("capped" if patch is None else f"{len(patch[0])} rings"))
    return out


def _stitch(V, faces, cuts):
    """Remove each loop's inside, add its patch's rings (the first replaces the loop) or a cap. Returns (V, faces,
    origin per vertex: 0 template, 1 generated ring (fixed), 2 generated free (cap centres), old -> new index)."""
    nb = {}
    for f in faces:
        for k in range(len(f)):
            nb.setdefault(f[k], set()).update((f[k - 1], f[(k + 1) % len(f)]))
    drop = set()
    for loop, inner, _ in cuts.values():
        drop |= _tip_side(loop, nb, inner) - set(loop)
    kept = [f for f in faces if not any(v in drop for v in f)]
    directed = {(f[k], f[(k + 1) % len(f)]) for f in kept for k in range(len(f))}
    n0 = len(V)
    V = list(np.asarray(V))
    origin = [0] * n0
    new = []
    for loop, _, patch in cuts.values():
        n = len(loop)
        # the kept faces run along the loop: patch faces run against them (a vote over the loop's edges: another
        # cut's dropped tip side can take the face on loop[0] -> loop[1], and the whole tube came out inside out)
        fwd = sum((loop[k], loop[(k + 1) % n]) in directed for k in range(n)) >= \
            sum((loop[(k + 1) % n], loop[k]) in directed for k in range(n))

        def quad(a, b, c, d):
            return [b, a, d, c] if fwd else [a, b, c, d]

        def fan(ring, t):
            for i in range(0, n - 1, 2):
                a, b, c = ring[i], ring[i + 1], ring[(i + 2) % n]
                new.append([c, b, a, t] if fwd else [a, b, c, t])
            if n % 2:
                new.append([ring[0], ring[-1], t] if fwd else [ring[-1], ring[0], t])
        if patch is None:
            V.append(np.mean([V[i] for i in loop], 0))
            origin.append(2)
            fan(loop, len(V) - 1)
            continue
        rings, tip = patch
        for i, v in enumerate(loop):
            V[v] = rings[0][i]
            origin[v] = 1
        prev = list(loop)
        for R in rings[1:]:
            ids = list(range(len(V), len(V) + n))
            V.extend(R)
            origin.extend([1] * n)
            for i in range(n):
                new.append(quad(prev[i], prev[(i + 1) % n], ids[(i + 1) % n], ids[i]))
            prev = ids
        V.append(tip)
        origin.append(1)
        fan(prev, len(V) - 1)
    faces = kept + new
    used = sorted({v for f in faces for v in f})
    remap = np.full(len(V), -1)
    remap[used] = np.arange(len(used))
    return (np.array([V[v] for v in used]), [[int(remap[v]) for v in f] for f in faces],
            np.array([origin[v] for v in used]), remap[:n0])


# ---------------------------------------------------------------------------------------------------- fitting

def _fit(V, L, S, prims, voxel, regions, dom, keep, fixed, reach=0.12, rounds=50):
    """Shoot free vertices along their normals to the nearest crossing of their region's surface, then relax
    along the surface and re-project; fixed vertices stay, kept ones (mouth bag) follow their neighbours."""
    T = tris(L, S)
    E = edges(L, S)
    N = _vnormals(V, T)
    free = ~keep & ~fixed
    t = np.linspace(-reach, reach, 121)
    f = np.full((len(V), len(t)), np.nan)
    for k, reg in enumerate(regions):
        m = (dom == k) & free
        if m.any():
            f[m] = sdf.field_at(reg or prims, V[m][:, None, :] + t[None, :, None] * N[m][:, None, :], margin=reach)
    m = free & (dom < 0)
    if m.any():
        f[m] = sdf.field_at(prims, V[m][:, None, :] + t[None, :, None] * N[m][:, None, :], margin=reach)
    ff = np.nan_to_num(f, nan=1.0)
    sgn = np.signbit(ff)
    cost = np.where(sgn[:, 1:] != sgn[:, :-1], np.abs(0.5 * (t[1:] + t[:-1]))[None, :], np.inf)
    k = cost.argmin(1)
    i = np.arange(len(V))
    ok = np.isfinite(cost[i, k]) & free
    f0, f1 = ff[i, k], ff[i, k + 1]
    tt = t[k] + (t[k + 1] - t[k]) * f0 / np.where(f0 - f1 == 0, 1, f0 - f1)
    V = V.copy()
    V[ok] += tt[ok, None] * N[ok]
    missed = free & ~ok

    def newton(X, it, m):
        X = X.copy()
        X[m] = surface.newton(prims, X[m], voxel * 0.125, voxel, iterations=it)[0]
        return X
    V = newton(V, 40, missed)
    V = newton(V, 8, free)
    deg = np.bincount(E.ravel(), minlength=len(V))
    for _ in range(rounds):
        N = _vnormals(V, T)
        lap = _lap(V, E, deg)
        dv = lap - (lap * N).sum(1, keepdims=True) * N
        X = V + 0.5 * dv
        X[keep] = V[keep] + 0.5 * lap[keep]
        X[free] = surface.newton(prims, X[free], voxel * 0.125, voxel, iterations=6)[0]
        X[fixed] = V[fixed]
        V = X
    return V, int(missed.sum())


def _neck_cut(V, L, S, c, n, side, gap):
    """A mesh cut at the closed quad loop round the neck nearest the graft plane on its own side (side -1: the
    body, below; +1: the head, above), at least `gap` from the plane, the far side dropped. A loop, not the plane:
    cut by the plane, the rims zigzagged a face deep and the bridge between them twisted."""
    faces, nb, ef = topology(L, S)
    V = np.asarray(V, float)
    u = (V - c) @ n
    rad = np.linalg.norm(np.cross(V - c, n), axis=1)
    near = set(np.flatnonzero((side * u > gap) & (side * u < gap + 0.09) & (rad < 0.12)).tolist())
    e1 = _unit(np.cross(n, [1.0, 0, 0]))
    e2 = np.cross(n, e1)
    best = None
    for path in _loops_round(V, faces, nb, ef, near, 300):
        if not all(p in near for p in path):
            continue
        q = V[path] - c
        ang = np.arctan2(q @ e2, q @ e1)
        wn = np.sum((np.diff(np.r_[ang, ang[:1]]) + np.pi) % (2 * np.pi) - np.pi) / (2 * np.pi)
        if abs(round(wn)) != 1:
            continue
        d = float(np.abs(u[path]).max())
        if best is None or d < best[0]:
            best = (d, path)
    if best is None:
        raise ValueError(f"graft: no closed neck loop on the {'head' if side > 0 else 'body'} side of the plane")
    loop = best[1]
    far = int(np.argmax(-side * u))
    drop = _tip_side(loop, nb, far) - set(loop)
    kept = [f for f in faces if not any(v in drop for v in f)]
    used = sorted({v for f in kept for v in f})
    rm = np.full(len(V), -1)
    rm[used] = np.arange(len(used))
    return V[used], np.array([rm[v] for f in kept for v in f]), np.array([len(f) for f in kept])


def _zip_mouth(V, L, S, seam, reach=0.04):
    """The open mouth of a head mesh without its mouth bag (GNM's skin) zipped shut: the boundary loop round the
    lips split at its corners, each lower-lip vertex welded to the upper one at the same place along the lip. Left
    open over closed lips, the lips' inner rims projected onto one another and flecked."""
    faces = [list(map(int, L[a:a + k])) for a, k in zip(np.r_[0, np.cumsum(S)[:-1]], S)]
    cnt: dict = {}
    for f in faces:
        for k in range(len(f)):
            e = (min(f[k], f[(k + 1) % len(f)]), max(f[k], f[(k + 1) % len(f)]))
            cnt[e] = cnt.get(e, 0) + 1
    V = np.asarray(V, float).copy()
    nbr: dict = {}
    for (a, b), c in cnt.items():
        if c == 1 and np.linalg.norm(V[a] - seam) < reach and np.linalg.norm(V[b] - seam) < reach:
            nbr.setdefault(a, []).append(b)
            nbr.setdefault(b, []).append(a)
    if not nbr or any(len(v) != 2 for v in nbr.values()):
        return V, L, S, 0
    loops, seen = [], set()
    for start in nbr:
        if start in seen:
            continue
        lp, prev = [start], None
        while True:
            nx = [w for w in nbr[lp[-1]] if w != prev]
            prev = lp[-1]
            if nx[0] == lp[0]:
                break
            lp.append(nx[0])
        seen |= set(lp)
        loops.append(lp)
    loop = max(loops, key=len)
    x = V[loop, 0]
    i0, i1, m = int(np.argmin(x)), int(np.argmax(x)), len(loop)
    a = [loop[(i0 + k) % m] for k in range((i1 - i0) % m + 1)]
    b = [loop[(i1 + k) % m] for k in range((i0 - i1) % m + 1)][::-1]
    up, lo = (a, b) if V[a, 2].mean() > V[b, 2].mean() else (b, a)
    arc = lambda P: np.r_[0, np.cumsum(np.linalg.norm(np.diff(V[P], axis=0), axis=1))] / max(
        float(np.linalg.norm(np.diff(V[P], axis=0), axis=1).sum()), 1e-9)
    su, sl = arc(up), arc(lo)
    to = np.arange(len(V))
    for v, t in zip(lo[1:-1], sl[1:-1]):
        to[v] = up[int(np.argmin(np.abs(su - t)))]
    for k, v in enumerate(up[1:-1], 1):
        V[v] = 0.5 * (V[v] + V[lo[int(np.argmin(np.abs(sl - su[k])))]])
    out = []
    for f in faces:
        g = [int(to[v]) for v in f]
        g = [v for k, v in enumerate(g) if v != g[k - 1]]
        if len(set(g)) >= 3:
            out.append(g)
    used = sorted({v for f in out for v in f})
    rm = np.full(len(V), -1)
    rm[used] = np.arange(len(used))
    return V[used], np.array([rm[v] for f in out for v in f]), np.array([len(f) for f in out]), len(up)


def graft_head(V, L, S, spec: dict, prims, log: list, unsub: int = 1, gap: float = 0.006):
    """A base with a grafted head (GNM) keeps the head's own quads: the template's face, carried onto a head of
    other proportions, folded round the mouth and jaw however the landmarks were set. The head's skin quads
    un-subdivided `unsub` times in Blender (12k -> 6k quads), both meshes cut `gap` clear of the graft plane, the
    two neck loops bridged, then the head and the bridge projected onto the field (strokes on the face count) and
    the bridge relaxed. Returns (V, L, S)."""
    import copy
    import tempfile
    from . import asset, base as basemod
    s = expand_mirror(spec)
    b = copy.deepcopy(spec["base"])
    b["head"] = {**b["head"], "subdivide": 0}
    h = basemod.head_of(s, b)
    c, n = h["plane"][0], h["plane"][1]
    HL = np.array([v for f in h["faces"] for v in f])
    HS = np.array([len(f) for f in h["faces"]])
    Vb, Lb, Sb = _neck_cut(V, L, S, c, n, -1, 0.004)  # (the template's neck rings tilt up to the nape)
    Vh, Lh, Sh = _neck_cut(h["verts"], HL, HS, c, n, +1, -0.002)  # (GNM's neck rings tilt across the plane)
    if h.get("lips_zipped"):  # the head's own mesh is closed at the lips' contact (base._zip_lips): the seam is
        # an edge loop already, on the field's lip line
        log.append(f"head: lips closed in the head mesh ({h['lips_zipped']} seam vertices)")
    elif "lm_lip_seam" in s["joints"] and float(np.linalg.norm(h["lm68"][62] - h["lm68"][66])) < 0.0015:
        Vh, Lh, Sh, nz = _zip_mouth(Vh, Lh, Sh, resolve_point(s, "lm_lip_seam"))
        log.append(f"head: the closed mouth zipped ({nz} upper-lip vertices)" if nz else "head: mouth left open")
    with tempfile.TemporaryDirectory(prefix="hifipushie-graft-") as tmp:
        tmp = Path(tmp)
        np.savez(tmp / "body.npz", verts=Vb, loops=Lb, sizes=Sb)
        np.savez(tmp / "head.npz", verts=Vh, loops=Lh, sizes=Sh)
        asset._blender({"mode": "graft_topology", "body": str(tmp / "body.npz"), "head": str(tmp / "head.npz"),
                        "plane_c": list(map(float, c)), "plane_n": list(map(float, n)), "gap": 0.08, "unsub": unsub,
                        "cuts": 2, "out": str(tmp / "out.npz")})
        z = np.load(tmp / "out.npz")
        V2, L2, S2, br = z["verts"].astype(float), z["loops"], z["sizes"], z["bridge"]
    head = ((V2 - c) @ n > 0) | br
    lo = np.min([p.lo for p in prims], 0)
    hi = np.max([p.hi for p in prims], 0)
    voxel = float((hi - lo).max()) / 200
    V2[head] = surface.newton(prims, V2[head], voxel * 0.125, voxel, iterations=12)[0]
    E = edges(L2, S2)
    deg = np.bincount(E.ravel(), minlength=len(V2))
    T = tris(L2, S2)
    rel = br.copy()  # the bridge and two rings round it (the plane-cut rims zigzag) relaxed along the surface
    for _ in range(2):
        rel[E[rel[E[:, 0]] | rel[E[:, 1]]].ravel()] = True
    if "lm_lip_seam" in s["joints"]:  # and the zipped lips' seam (their inner rims folded against each other)
        sm = np.array(resolve_point(s, "lm_lip_seam"))
        mc = np.array(resolve_point(s, "lm_mouth_corner.L"))
        q = V2 - sm
        rel |= (np.abs(q[:, 0]) < abs(mc[0] - sm[0]) + 0.004) & (np.abs(q[:, 2]) < 0.004) & (np.abs(q[:, 1]) < 0.012)
    for _ in range(60):
        N = _vnormals(V2, T)
        lap = _lap(V2, E, deg)
        dv = lap - (lap * N).sum(1, keepdims=True) * N
        V2[rel] = V2[rel] + 0.5 * dv[rel]
        V2[rel] = surface.newton(prims, V2[rel], voxel * 0.125, voxel, iterations=4)[0]
    log.append(f"head: the grafted head's own quads (un-subdivided x{unsub}), bridged at the neck: {len(V2)} verts, "
               f"{len(S2)} faces ({(S2 == 4).mean():.0%} quads)")
    return V2, L2, S2


def _untangle(V, L, S, prims, voxel, frozen, passes=12, log=None):
    """Faces turned against the field (tangles in tight creases): their vertices and two rings round them smoothed
    and re-projected, until none are left or passes run out."""
    T = tris(L, S)
    E = edges(L, S)
    deg = np.bincount(E.ravel(), minlength=len(V))
    nb = [[] for _ in range(len(V))]
    for a, b in E:
        nb[a].append(b)
        nb[b].append(a)
    bad = np.zeros(len(T), bool)
    for it in range(passes):
        bad = turned(V, T, prims) & ~frozen[T].all(1)
        if not bad.any():
            break
        m = np.zeros(len(V), bool)
        m[T[bad].ravel()] = True
        for _ in range(2):
            m[[j for i in np.flatnonzero(m) for j in nb[i]]] = True
        m &= ~frozen
        for _ in range(4):
            V[m] += 0.5 * _lap(V, E, deg)[m]
        V[m] = surface.newton(prims, V[m], voxel * 0.125, voxel, iterations=8)[0]
    if log is not None:
        log.append(f"untangle: {int(bad.sum())} faces still turned after {it + 1} passes")
    return V


def turned(V, T, prims, near=0.0015):
    """Triangles on the surface (centre within `near` of it) whose normal faces against the field's gradient."""
    c = V[T].mean(1)
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    g = sdf.gradient(prims, c, 1e-4)
    on = np.abs(sdf.field_at(prims, c, margin=0.01)) < near
    return ((fn * g).sum(1) < 0) & on


# ---------------------------------------------------------------------------------------------------- main

def base_quads(spec: dict, log: list) -> dict | None:
    """A base body's OWN quads as its topology (the same dict as `wrap`): the posed body mesh the field is made from
    (`base.surface()["quads"]`: MakeHuman's or the template's animation topology, fingers and all), its vertices
    dropped onto the field (a subdivision cage stands a little off its limit surface; pushes and strokes count),
    a grafted head bridged on as before. Carrying ANOTHER template onto a base (the stylised male's digit tubes
    onto MakeHuman's close-set fingers) tore both hands at the webs and the thumb's root, at rest: the golfer's
    "cracked" disc hand, 2251 faces still turned after the untangle. parts.body.topology = "template" for that path.
    None when the base has no quads of its own."""
    from . import base as basemod
    s = expand_mirror(spec)
    sf = basemod.surface(s, spec["base"])
    if not sf.get("quads"):
        return None
    Vq, fq = sf["quads"]
    V = np.array(Vq, float)
    L = np.array([v for f in fq for v in f])
    S = np.array([len(f) for f in fq])
    prims = [p for p in compile_prims(spec) if p.part == "body"]
    lo = np.min([p.lo for p in prims], 0)
    hi = np.max([p.hi for p in prims], 0)
    voxel = float((hi - lo).max()) / 200
    V0 = V.copy()
    one = (spec["base"].get("body") or {}).get("source") == "human"
    gnm = None
    if one:  # (onemesh.py) which GNM vertex each is (-1: MakeHuman's body or the bridge): face shapes go by index
        from . import onemesh
        tpl = basemod.source(spec["base"])
        gnm = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
        g = basemod._gnm_data()
        ext = np.asarray(g["groups"]["skin_exterior"]) > 0.5
        inner = (gnm >= 0) & ~ext[np.maximum(gnm, 0)]  # lid insides, inner lip rolls, nostrils' depths
        ears = np.asarray(g["groups"]["ears"]) > 0.5  # (thin folded shells: dropped onto the smoothed field their
        inner |= (gnm >= 0) & ears[np.maximum(gnm, 0)]  # quads folded: TORN at the head, 60 spots on Garrett's ears)
    V = surface.newton(prims, V, voxel * 0.125, voxel, iterations=12)[0]
    # (the cage stands <= ~2.5 mm off; what moves further is the neck tube's upper rings inside a grafted head, cut
    # away below, or a step that went astray)
    far = np.linalg.norm(V - V0, axis=1) > 0.004
    if one:  # GNM's own interior surfaces (they roll back under the lids, behind the lips) aren't the field's
        # surface: dropped onto it they folded (TORN OR TANGLED at both eyes). They stay as GNM placed them.
        far |= inner
    V[far] = V0[far]
    mv = np.linalg.norm(V - V0, axis=1)[~far] * 1e3
    log.append(f"wrapped: the base body's own quads, {len(V)} verts, {len(S)} faces ({(S == 4).mean():.0%} quads); "
               f"moved onto the field by mean {mv.mean():.2f} p95 {np.percentile(mv, 95):.2f} max {mv.max():.1f} mm"
               + (f", {int(far.sum())} left where they were" if far.any() else ""))
    # (a fused one-mesh source, body.source "human", has its head in these quads already: no graft)
    if (spec["base"].get("head") or {}).get("source", "gnm") == "gnm" and spec["base"].get("head") \
            and (spec["base"].get("body") or {}).get("source") != "human":
        V, L, S = graft_head(V, L, S, spec, prims, log)
    out = {"verts": V, "loops": L, "sizes": S, "origin": np.zeros(len(V), int), "log": log, "patches": {}}
    if one:
        V, L, S, gnm = _with_mouth_sock(V, L, S, gnm, spec, s, log)
        out.update(verts=V, loops=L, sizes=S, origin=np.zeros(len(V), int), gnm=gnm)
    return out


SOCK_TUCK = 0.004  # m: (one mesh) the mouth sock narrows and sinks back over this distance in from the lips' loop
SOCK_NARROW, SOCK_SINK = 0.45, 0.004  # its width taken in by this share, and m sunk back, at full tuck (0.25 / 3 mm left Garrett's
# narrower mouth with the sock's sides out through both lip corners in the exported neutral)


def _with_mouth_sock(V, L, S, gnm, spec, s, log):
    """(onemesh.py) GNM's mouth sock added to the one mesh's own quads: the skin's open mouth loop (the end of the
    inner lip rolls) closed by GNM's own oral cavity, placed as the head places its skin, so a parted or opened mouth
    shows a mouth, not the inside of the head. Not with zipped lips (a closed mouth has no loop)."""
    from . import base as basemod
    from . import onemesh
    h = onemesh.head(s, spec["base"])
    if h.get("lips_zipped"):
        return V, L, S, gnm
    g = basemod._gnm_data()
    c = h["carry"]
    sock = np.asarray(g["groups"]["mouth_sock"]) > 0.5
    where = np.full(len(sock), -1)
    where[gnm[gnm >= 0]] = np.flatnonzero(gnm >= 0)
    Q = np.asarray(g["quads"])
    skin = np.asarray(g["skin"], bool)
    q = Q[(sock[Q] | skin[Q]).all(1) & sock[Q].any(1) & ((where[Q] >= 0) | sock[Q]).all(1)]
    new = np.unique(q[where[q] < 0])
    if not len(new):
        return V, L, S, gnm
    where[new] = len(V) + np.arange(len(new))
    place = lambda X: c["eye_mid"] + c["s"] * (np.asarray(X, float) - c["mid"]) @ np.asarray(c["R"], float).T  # noqa: E731
    Xw = place(np.asarray(c["V"], float)[new])
    # what the head did to its skin after placing it (pushes, the drop onto the field), carried onto the sock from
    # the skin it hangs from: left as placed, a corner push left the sock standing out through the lips' corners
    own = np.flatnonzero(gnm >= 0)
    near = own[np.linalg.norm(np.asarray(c["V"], float)[gnm[own]][:, None] - np.asarray(c["V"], float)[new][None], axis=2)
               .argmin(0)] if len(own) * len(new) < 4e7 else None
    if near is not None:
        Xw = Xw + (V[near] - place(np.asarray(c["V"], float)[gnm[near]]))
    # and tucked in behind the lips: GNM's sock is as wide as ITS mouth, and a narrowed, pushed or fitted face
    # (Garrett's) left the sock's sides standing out through the lips' corners. Past the loop it narrows toward the
    # mouth's middle and sinks back, by how far in it is
    loop = np.unique(where[q][~sock[q]])
    if len(loop):
        from scipy.spatial import cKDTree as _T
        d = _T(V[loop]).query(Xw)[0]
        t = np.clip(d / SOCK_TUCK, 0, 1)[:, None]
        mid = V[loop].mean(0)
        fwd = np.asarray(h["forward"], float)
        Xw = mid + (Xw - mid) * np.c_[1 - SOCK_NARROW * t, np.ones_like(t), np.ones_like(t)] - fwd * (SOCK_SINK * t)
    V = np.r_[V, Xw]
    L = np.r_[L, where[q].ravel()]
    S = np.r_[S, np.full(len(q), 4)]
    gnm = np.r_[gnm, new]
    log.append(f"mouth: GNM's mouth sock added to the quads ({len(new)} vertices, {len(q)} faces)")
    return V, L, S, gnm


def wrap(spec: dict, template: str = "male_stylized", log: list | None = None) -> dict:
    """The model's body as the template's quads: {"verts", "loops", "sizes", "origin" (0 template, 1/2 generated),
    "log"}. The spec needs the humanoid joints (see is_humanoid); a face kit, hand kit and ear bones are used when
    present."""
    log = [] if log is None else log
    if spec.get("base") and ((spec.get("parts") or {}).get("body") or {}).get("topology") != "template":
        r = base_quads(spec, log)
        if r is not None:
            return r
    tpl = load_template(template)
    s = expand_mirror(spec)
    prims = [p for p in compile_prims(spec) if p.part == "body"]
    lo = np.min([p.lo for p in prims], 0)
    hi = np.max([p.hi for p in prims], 0)
    voxel = float((hi - lo).max()) / 200
    P = tpl["P"]
    W, segs, dom, apply, Jm = _skeleton_warp(P, tpl["J"], s, prims)
    cuts = _plan_cuts(W, tpl, s, prims)
    base = bool(spec.get("base"))
    if base:  # a base body has a real head with ears (they fit by projection: cut and capped for want of ear bones,
        # they were lost) and its own finger joints under the template's names: digits are tubes along those
        # (projected, the template's coarse fingers jumped between the base's close-set fingers)
        for k, c in cuts.items():
            if c["kind"] == "digit":
                c["model"], c["carry"] = k.split(".")[0], True
        cuts = {k: c for k, c in cuts.items() if c["kind"] == "eye" or "chain" in c
                or (c["kind"] == "digit" and f"{c['model']}_0.{c['side']}" in s["joints"])}
    if "face" in (spec.get("kits") or {}) or any(k.startswith("face_") for k in s["blobs"]) or base:
        extra = [(W[c["loop"][i]], c["target"][i]) for c in cuts.values() if "target" in c
                 for i in range(0, len(c["loop"]), max(1, len(c["loop"]) // 6))]
        face = tpl["face"]
        W = _face_warp(W, apply, face, s, log, extra, BASE_FACE if base else None)
    E0 = edges(tpl["L"], tpl["S"])
    if not any(n.startswith("foot_t") for n in s["joints"]):  # no toes: smooth the template's into the foot
        toe = np.zeros(len(P), bool)
        for side in "LR":
            a, t = tpl["J"][f"ankle.{side}"], tpl["J"][f"toe.{side}"]
            dirn = t - a
            dirn[2] = 0
            dirn /= np.linalg.norm(dirn)
            toe |= ((P - t) @ dirn > -0.02) & (P[:, 2] < 0.09) & (np.sign(P[:, 0]) == np.sign(t[0]))
        W = _smooth_away(W, E0, toe)
        log.append(f"toes smoothed away ({toe.sum()} vertices)")
    keep0 = np.zeros(len(P), bool)  # the mouth and nostril cavities follow their neighbours: projected they poke
    keep0[tpl["face"].get("cavities", [])] = True  # through the lips (the old rule, "inside the model near the head",
    # also caught the goblin's cheeks and jaw: they sat 15-25 mm inside the surface)
    faces, _, _ = topology(tpl["L"], tpl["S"])
    cuts = _patches(W, cuts, s, prims, voxel, log)
    V, fl, origin, remap = _stitch(W, faces, cuts)
    L = np.array([v for f in fl for v in f])
    S = np.array([len(f) for f in fl])
    # per new vertex: its template vertex's dominant segment and keep flag (generated ones: none)
    n_t = len(V)
    dom2 = np.full(n_t, -1)
    keep = np.zeros(n_t, bool)
    ok = remap >= 0
    dom2[remap[ok]] = dom[ok]
    keep[remap[ok]] = keep0[ok]
    fixed = origin == 1
    keep &= ~fixed
    # regions: a vertex first projects onto the primitives of its segment and the neighbouring ones (a hand never
    # lands on a thigh)
    cen = np.array([0.5 * (p.lo + p.hi) for p in prims])
    owner = np.stack([_seg_dist(cen, Jm[a], Jm[b]) for a, b in segs], 1).argmin(1)
    regions = [[p for p, o in zip(prims, owner) if o in [i for i, (c, d) in enumerate(segs) if {c, d} & {a, b}]]
               for a, b in segs]
    if base:  # one primitive is the whole body (owned by the torso): every segment projects onto all of it (the
        # hands had nothing to land on and collapsed into strings; the mouth landed on a small blob behind the lips)
        regions = [prims for _ in segs]
    V, missed = _fit(V, L, S, prims, voxel, regions, dom2, keep, fixed)
    V = _untangle(V, L, S, prims, voxel, fixed | keep, log=log)
    fv = np.abs(sdf.field_at(prims, V, margin=0.05))[~keep] * 1000
    log.append(f"wrapped: {len(V)} verts, {len(S)} faces ({(S == 4).mean():.0%} quads); {missed} missed the surface "
               f"along their normal; |field| mean {fv.mean():.2f} p95 {np.percentile(fv, 95):.2f} max {fv.max():.1f} mm")
    if base and (spec["base"].get("head") or {}).get("source", "gnm") == "gnm" and spec["base"].get("head"):
        V, L, S = graft_head(V, L, S, spec, prims, log)
        origin = np.zeros(len(V), int)
    return {"verts": V, "loops": L, "sizes": S, "origin": origin, "log": log,
            "patches": {k: c[2][0] for k, c in cuts.items() if c[2] is not None}}
