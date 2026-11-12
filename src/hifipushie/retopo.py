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

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at retopo.NAME: C422). retopo_warp: warps: the template carried onto a spec's skeleton, the face warp, carry
and smoothing away. retopo_patches: loops and patches: base, ear and eye loops, tubes and arc tubes, the cut plan,
patches, the stitch. retopo_fit: fitting: the fit onto the surface, the neck cut, the mouth zip, graft_head,
untangling. retopo_wrap: `wrap` and what it starts from: base_quads, the lid and face keep regions, the mouth sock.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from . import sdf
from .spec import expand_mirror
from . import moved

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


LID_KEEP = True  # (r41) GNM's eye region (expression_basis_*_eye skin) is NOT dropped onto the field: the smoothed field rounds
# the lids, and dropped, their skin moved up to 1 mm (upper lid up +0.44 and back +0.27 mm on average), so the exported
# neutral eye opening was 10.0 mm against the approved GNM head's 8.6 (ga_tess v55, game_ready.md r41)
LID_KEEP_RINGS = 3  # the keep fades out over this many rings of quads past the group (no step where the drop resumes)


FACE_KEEP = True  # (r42) generalises LID_KEEP to the whole face: the drop moved the LIPS' skin by 1.2 mm on average (max 6.6 mm),
# the lower vermilion 3.5 mm shorter at the centre, the upper 1.5 mm ("neutral lips thin" in the r41 review), the nose tip 0.34 mm
# back (r42/fid_before.txt in the assembly scratch). GNM's expression-basis regions (eyes, mouth / nose / ears) keep the cage
FACE_KEEP_GROUPS = ("expression_basis_left_eye", "expression_basis_right_eye", "expression_basis_mouth_nose_ears")

SOCK_TUCK = 0.004  # m: (one mesh) the mouth sock narrows and sinks back over this distance in from the lips' loop
SOCK_NARROW, SOCK_SINK = 0.45, 0.004  # its width taken in by this share, and m sunk back, at full tuck (0.25 / 3 mm left Garrett's
# narrower mouth with the sock's sides out through both lip corners in the exported neutral)
SOCK_CARRY = True  # the head's own moves of its skin carried onto the sock (nearest skin vertex)
SOCK_FALLOFF = 0  # (r20: 0 again: with 6 (v32-v36) the head's texels astray 3.75% -> 4.89% and the closed upper lip baked torn streaks (seam/r20_alb_31_32_36.png); r17: rest ring-1 roughness 3.4 -> 2.0 mm unironed, rings 2+ as GNM) rings: > 0 replaces the carry and the tuck: the lips' loop's own offset from GNM's rest (what the head
# did to its skin) extended harmonically into the sock, fading to 0 over this many rings of the sock's quads
SOCK_FALLOFF_EASE = True  # (with SOCK_FALLOFF) the harmonic offset also eased by a smoothstep of the ring
SOCK_FALLOFF_NARROW = 0.0  # (with SOCK_FALLOFF) share of the tuck's narrowing kept, faded the same way


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("retopo_warp", "retopo_patches", "retopo_fit", "retopo_wrap")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
