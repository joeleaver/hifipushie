"""ONE HUMAN MESH: `base: {"body": {"source": "human", ...MakeHuman's keys...}, "head": {...GNM's keys...}}`.

GNM's head topology stitched ONCE, offline, onto MakeHuman's body topology at the neck (human_mesh.npz, built by
spikes/onemesh/make_asset.py from the two packs; hand corrections in spikes/onemesh/edits.json). Nothing is grafted
when a character is built: no neck tube, no cross-fade of two point sets, no head scale, no weights copied across
a join.

How the one mesh takes its shape:
- The body is MakeHuman's (makehuman.body: age with measured growth, sex, weight, muscle, height, race, chest...).
- Every GNM skin vertex is BOUND to a point of MakeHuman's reference surface (3 body vertices + weights), so the
  body's own head (which MakeHuman shapes with the rest: a baby's, an old woman's) carries GNM's head: a similarity
  (the head's size) plus a remainder smoothed over GNM's mesh, held hard at the stitch (`bound`). Ears, lids' insides,
  nostrils and the mouth ride; eyes, teeth and tongue follow the skin beside them as rigid pieces with a scale.
- GNM's identity / expression components (and everything base_gnm_head.gnm_head does with them: fit, regions, pose,
  mouth_gap, eye size, planes, pushes, simplify) are applied on top, x the head's size, faded to nothing over the
  rings above the stitch (`hook`, called by base_gnm_head.gnm_head): the neck is always the body's.
- `template(base)` is the fused mesh as a body template (what base.source returns): MakeHuman's vertices below its
  neck loop, the bridge's, GNM's skin above its ring; `head(s, base)` is the head's dict (landmarks, eyes, carry) as
  base_measures.head_of returns it, posed with the spec's joints by the same warp as the body.
- Skin weights are the asset's (`weights`): MakeHuman's hand-made ones, by index on the body and through the
  binding on the head.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at onemesh.NAME: C422). onemesh_native: the native head on the body: pivot, bib, seat, the neck's follow, its
size and description, the style lift, the neck field and fade. onemesh_head: the head of the one mesh: the hook into
gnm_head, face weights, the head's description and template, the head carried to a pose, the seam ring.
onemesh_report: the attach report (ring loops, girths against ANSUR), and weights.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from . import moved

_CACHE: dict = {}
CLOSED_GAP = 0.0008     # m: a GNM-closed mouth (the contact ring's halves within this, corner to corner) gets the seam field
CLOSED_SEAL_V = (0.5,)  # its rows drawn toward the seam (base_surface.SEAL_V's): the first only. The seal's three rows halved the
# vermilion border's turn; the first alone keeps the border and makes the seam a V (-60 / +27 deg each side, Tess)
VERSION = 15  # bump when the one mesh's built field changes (store's build key, base_surface.surface's key; old paths keep theirs)
DIMORPHISM = 0.8  # as headfit's: under a seed's individuality MakeHuman's own difference reads as neither sex
ANCHORS = 48  # skin vertices a loose piece (eye, teeth, tongue) follows
HEAD_KEYS = ("toward", "dimorphism", "features", "follow_body", "like", "neck", "attach", "size")  # head keys handled
# here (the rest are base_gnm_head.gnm_head's)
# (headbody, 2026-10-12) base.head.attach "native": GNM's head UNTOUCHED, at GNM's own size (metres; x base.head.size),
# down to the seam ring (the asset's stitch, GNM's neck ring 13); the BODY is fitted to it (stature, neck). See `native`.
NATIVE_REACH = 0.11  # m over the body's surface from the seam ring: how far the body's neck / shoulders give to meet it
NATIVE_RELAX = 0.045  # m from the ring: the body's rows evened out along the surface after the move (the bridge)
NATIVE_RELAX_ITERS = 40
NATIVE_DROP = ("gnm_base", "gnm_base_rest", "gnm_base_blend", "gnm_base_age", "scale")  # head keys with no meaning there
_RG = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # GNM (Y up, facing +Z) -> world (Z up, facing -Y)


def applies(base: dict | None) -> bool:
    return bool(base) and ((base.get("body") or {}).get("source") == "human")


def asset() -> dict:
    if "asset" not in _CACHE:
        z = np.load(Path(__file__).with_name("human_mesh.npz"))
        from . import gnmloops  # the lids' extra edge loops, appended (gnmloops.py)
        _CACHE["asset"] = gnmloops.extend_asset({k: z[k] for k in z.files})
    return _CACHE["asset"]


def body_params(base: dict) -> dict:
    return {k: v for k, v in (base.get("body") or {}).items() if k != "source"}


def _reference() -> dict:
    """What the binding needs of MakeHuman's reference body and GNM's mesh, once per process."""
    if "ref" in _CACHE:
        return _CACHE["ref"]
    import scipy.sparse as sp
    from scipy.sparse.linalg import factorized
    from scipy.spatial import cKDTree

    from . import base_identity
    from . import makehuman
    a = asset()
    meta = json.loads(str(a["meta"]))
    g = base_identity._gnm_data()
    Pref = np.asarray(makehuman.body(json.loads(str(a["reference"])))["P"], float)
    val = a["g_valid"]
    tri, bar = a["g_tri"], a["g_bary"].astype(float)
    Tref = (bar[:, :, None] * Pref[tri]).sum(1)
    lev = a["g_lev"].astype(int)
    sk = np.flatnonzero(lev >= 0)  # GNM's skin component (with the mouth sock)
    loc = np.full(len(lev), -1)
    loc[sk] = np.arange(len(sk))
    quads = np.asarray(g["quads"])
    Q = loc[quads[(loc[quads] >= 0).all(1)]]
    e = np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]]
    m = len(sk)
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (m, m)).tocsr()
    A = ((A + A.T) > 0).astype(float)
    deg = np.asarray(A.sum(1)).ravel()
    L = sp.diags(np.where(deg > 0, 1.0, 0.0)) - sp.diags(1 / np.maximum(deg, 1)) @ A
    lips = (g["groups"]["upper_lip"] > 0.5) | (g["groups"]["lower_lip"] > 0.5)
    w = val[sk] * np.where(lips[sk], meta["LIPS"], 1.0)
    st = np.clip(1 - np.abs(lev[sk] - meta["RING"]) / meta["STIFF"], 0, 1)  # hard round the stitch: it must follow the body
    w = w * (1 + 400 * st * st)
    solve = factorized((sp.diags(w) + meta["LAM"] * (L.T @ L) + 1e-9 * sp.identity(m)).tocsc())
    X0 = a["g_neutral"].astype(float)
    head = val & (lev >= meta["RING"])  # the vertices the head's size is read from
    # loose pieces and the skin they follow
    part = a["g_part"].astype(int)
    outer = np.flatnonzero(val & (lev >= meta["RING"]))
    tree = cKDTree(X0[outer])
    pieces = []
    for ids in (2, 3, 4, 5, 6):
        pv = np.flatnonzero((part == ids) & (lev < 0))
        if len(pv):
            pieces.append((pv, outer[tree.query(X0[pv].mean(0), k=ANCHORS)[1]]))
    eye_anchor = [outer[tree.query(p, k=ANCHORS)[1]] for p in a["g_eye_j"].astype(float)]
    _CACHE["ref"] = {"Pref": Pref, "Tref": Tref, "sk": sk, "solve": solve, "w": w, "X0": X0, "head": head, "val": val,
                     "tri": tri, "bar": bar, "pieces": pieces, "eye_anchor": eye_anchor, "meta": meta,
                     "io_scale": float(a["io"][0] / a["io"][1])}
    return _CACHE["ref"]


def _similar(X0, X1):
    """(c0, c1, k): the translation and uniform scale that take points X0 to X1 (no rotation)."""
    c0, c1 = X0.mean(0), X1.mean(0)
    k = float(np.sqrt(((X1 - c1) ** 2).sum() / max(((X0 - c0) ** 2).sum(), 1e-30)))
    return c0, c1, k


def bound(params: dict, toward: float = 1.0) -> dict:
    """GNM's whole head (all its vertices, world frame of the MakeHuman body made from `params`) as that body's own
    head carries it: {"B": (17821, 3), "k": the head's size over the reference head's, "eyes": the two eye joints,
    "P": the body's vertices}. toward < 1 leaves part of GNM's own mean head in (0 = its mean proportions)."""
    key = ("bound", json.dumps(params, sort_keys=True, default=float), round(float(toward), 6))
    if key in _CACHE:
        return _CACHE[key]
    from . import makehuman
    r = _reference()
    a = asset()
    mb = makehuman.body(params)
    P = np.asarray(mb["P"], float)
    val, sk, X0 = r["val"], r["sk"], r["X0"]
    T = (r["bar"][:, :, None] * P[r["tri"]]).sum(1)
    c0, c1, k = _similar(r["Tref"][r["head"]], T[r["head"]])
    rem = np.where(val[:, None], T - (c1 + k * (r["Tref"] - c0)), 0.0)
    D = np.column_stack([r["solve"](r["w"] * rem[sk, j]) for j in range(3)])
    B = c1 + k * (X0 - c0)
    B[sk] += D
    if toward != 1.0:
        B[sk] += (1 - float(toward)) * k * (a["g_mean"].astype(float) * a["g_fade"][:, None])[sk]
    for pv, anc in r["pieces"]:  # eyes, teeth, tongue: rigid with a scale, as the skin beside them went
        a0, a1, ka = _similar(X0[anc], B[anc])
        B[pv] = a1 + ka * (X0[pv] - a0)
    eyes = []
    for p, anc in zip(a["g_eye_j"].astype(float), r["eye_anchor"]):
        a0, a1, ka = _similar(X0[anc], B[anc])
        eyes.append(a1 + ka * (p - a0))
    out = {"B": B, "k": k, "eyes": np.array(eyes), "P": P, "mh": mb}
    if len(_CACHE) > 24:
        for kk in [kk for kk in _CACHE if isinstance(kk, tuple) and kk[0] == "bound"][:4]:
            _CACHE.pop(kk)
    _CACHE[key] = out
    return out


NATIVE_VERSION = 2  # bump when a NATIVE head's build changes (2: seated by the bib, the body laid on it); other one-mesh
# models keep their build keys


def build_version(base: dict | None) -> str:
    """What store / base_surface.surface key a one-mesh build on."""
    return f"{VERSION}" + (f"n{NATIVE_VERSION}" if native(base) else "")


def native(base: dict | None) -> bool:
    """base.head.attach == "native": the head is GNM's own evaluation under ONE similarity (its size in metres x
    base.head.size, a rigid placement on the body's skull pivot), every vertex from the seam ring up; nothing of the
    body's head, no blend above the ring, no style head sliders. The body gives: its height is set so the figure
    stands at the stated stature (base.body.height) under THIS head, and its neck / shoulders are moved to meet GNM's
    ring (`_neck_field`). `attach_report(base)` has the numbers."""
    return applies(base) and (base.get("head") or {}).get("attach") == "native"


SEAT_RINGS = (0, 9)  # the bib's rings the head is seated by: the shoulder slope, clavicle line and upper back (not the
# neck's column: a head whose neck is thicker than the body's must not ride up or down for it)
SEAT_REACH = 0.04    # m: bib points further than this from the body's surface do not count

BIB_FULL, BIB_NONE = 10.0, 1.0  # the body takes GNM's bib whole from this ring up (to the seam ring), not at all from this ring down
FOLLOW_REACH = 0.17   # m over the body's surface from the seam ring (x stature / 1.7): the vertices that may move
FOLLOW_ITERS = 80

NECK_RINGS = (10, 20)  # rings above the stitch over which the hand-over runs: at the throat, at the nape
NECK_FADE = True  # the head's own shape handed over to the body's through the whole neck (stitch -> chin level)

SUPRASTERNALE, ACROMION = 1522, 8275  # MakeHuman body vertices: the pit of the throat (front midline, between the
# clavicles) and the shoulder's outer top; both under the neck loop, so in every one-mesh build
# ANSUR II (2012; fitted here to the public per-subject tables, docs/notes/headbody.md "## Round 2"): each measure as
# value at the sex's mean stature x (stature / that stature) ^ alpha, with the residual's sd (of the log): (women, men).
# A head does not grow in step with the body (alpha ~0.3), so "heads tall" rises with stature by itself.
ANSUR_STATURE = (1.627, 1.755)
ANSUR = {"top_over_pit": ((0.2985, 0.687, 0.0368), (0.3173, 0.682, 0.0370)),  # top of head - suprasternale height
         "neck_girth": ((0.3292, 0.436, 0.0549), (0.3968, 0.325, 0.0629)),    # neck circumference
         "head_height": ((0.218, 0.29, 0.048), (0.232, 0.24, 0.046))}         # menton - top of head: the VALUES are ANSUR
# 1988's FROM MEMORY (not in the public tables); alpha and sd are tragion - top of head's
NECK_CONFLICT = 0.08  # the head's neck girth against the body's own, at the narrowest: past this the report says so
SD_FLAG = 2.5


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("onemesh_native", "onemesh_head", "onemesh_report")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
