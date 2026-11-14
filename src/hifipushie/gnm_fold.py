"""The upper lid's FOLD in GNM's own parameters ("overhang" study, 2026-10-11; docs/notes/gnm_atlas.md "## overhang").

GNM's skin round each eye is closed quad rings: ring 0 = the lid margin, ring k = k edges out (rows 0.5-0.7 mm apart
at rings 3-6, where GNM's crease is). Every ring vertex is linear in the 170 identity comps (and the eye's 100
expression comps), so a wanted fold is a closed-form least squares, not a search:

  read(V)        overhang (mm of skin hanging in front of and below the skin under it, front view), the largest turn
                 of the section (deg) and the crease's height over the margin, on radial chains up the lid's middle
  hood_direction the ONE identity direction that makes an overhang at least cost. It is hooding: the brow and drape
                 coming down over a deeper-set eye (corr -0.95 with the brow's height). Not a local fold.
  design(V, ...) a designed folded lid as vertex targets: a platform on the ball up to the crease, a slit, a roll of
                 drape hanging `overhang` mm over the platform, merging into the head's own drape
  fold(c, ...)   the least-squares identity (optionally + eye expression) for that design with the rest of the head
                 held, optionally with the overhang as a hard constraint; returns the coefficients and a blunt report

What the study found (numbers in the notes): the basis SPANS a re-entrant lid (0.13 mm rms with nothing else asked,
at |dc| 460), but with the rest of the head held to 1 mm the lid's rows keep ~0.08 mm of freedom. fold() without
`overhang` gives a crisp fold at a chosen height (turn 45-65 deg raw; the population's largest at >= 4 mm is ~36) for
|dc| ~10-15; with `overhang` it buys the overhang by lowering the brow 4-5 mm (|dc| ~18-20). GNM frame, mm inside.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at gnm_fold.NAME: C422). gnm_fold_design: the designed fold: its rows, the hood's direction, `design`, `fold`
and the fold's text. gnm_fold_mesh: the fold in MESH space: rings filled, the blink's gain, the tail, smoothing along
rings and crease rows, the slit, `mesh_delta`; the wrap: the crease smoothed and its roughness measured,
`chains_wrap`, `design_wrap`.
"""
from __future__ import annotations

import numpy as np

from . import gnm_controls as gc
from . import gnm_controls_latent
from . import moved

NC = 170
NR = 12            # rings read out from the margin
MM_FREE = ("brow_hollow", "_platform_z")   # gnm_mm's measures a fold IS (the sulcus under the brow, the platform on the ball)
_C: dict = {}


def topo() -> dict:
    """{"ring": per GNM vertex ring index round the LEFT eye (0 = margin; 99 elsewhere; negative = the socket lining),
    "nb": neighbour lists over skin edges, "mir": the mirror vertex of each vertex}."""
    if "t" in _C:
        return _C["t"]
    from scipy.spatial import cKDTree
    g = gc.gnm()
    Q, gr, T = g["quads"], g["groups"], g["T"]
    n = len(T)
    skin, sock = gr["skin"], gr["eye_sockets"]
    E = np.concatenate([Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]])
    E = E[skin[E].all(1)]
    nb = [[] for _ in range(n)]
    for a, b in E:
        nb[a].append(int(b))
        nb[b].append(int(a))
    cl = g["J"][2]
    m = sock[E[:, 0]] != sock[E[:, 1]]
    r0 = np.unique(np.where(sock[E[m, 0]], E[m, 1], E[m, 0]))
    r0 = r0[np.linalg.norm(T[r0] - cl, axis=1) < 0.03]
    ring = np.full(n, 99)
    ring[r0] = 0
    for sgn, ok, lim in ((1, ~sock, NR + 6), (-1, sock, 5)):   # (+6: a fold traced far round the outer corner uses rings to 16)
        cur = list(r0)
        for k in range(1, lim + 1):
            nxt = []
            for a in cur:
                for b in nb[a]:
                    if ring[b] == 99 and ok[b]:
                        ring[b] = sgn * k
                        nxt.append(b)
            cur = nxt
    _C["t"] = {"ring": ring, "nb": nb, "mir": cKDTree(T).query(T * [-1, 1, 1])[1]}
    return _C["t"]


def chains(umax: float = 7.0, k1: int = NR) -> np.ndarray:
    """Radial chains up the LEFT upper lid: from each margin vertex within umax mm of the eye's centre (across), follow
    the next ring's neighbour nearest in x. (n, k1 + 1) vertex ids; the right eye's are topo()["mir"][chains]."""
    key = ("ch", umax, k1)
    if key in _C:
        return _C[key]
    g, t = gc.gnm(), topo()
    T = g["T"] * 1000.0
    J = g["J"][2] * 1000.0
    r0 = np.flatnonzero(t["ring"] == 0)
    r0 = r0[(T[r0, 1] > J[1] + 0.5) & (np.abs(T[r0, 0] - J[0]) < umax)]
    out = []
    for v in r0[np.argsort(T[r0, 0])]:
        ch = [int(v)]
        while t["ring"][ch[-1]] < k1:
            up = [b for b in t["nb"][ch[-1]] if t["ring"][b] == t["ring"][ch[-1]] + 1]
            if not up:
                break
            ch.append(min(up, key=lambda b: abs(T[b, 0] - T[ch[-1], 0])))
        if len(ch) == k1 + 1:
            out.append(ch)
    _C[key] = np.array(out)
    return _C[key]


def vertices(c=None, e=None) -> np.ndarray:
    """GNM's head in mm (GNM frame) for identity c (<= 253) and expression e (383)."""
    return gnm_controls_latent.vertices(c, e) * 1000.0


def read(V: np.ndarray, umax: float = 7.0) -> dict:
    """The fold on vertices V (mm), left eye, per radial chain and as means:
    hang   mm: the largest v[a] - v[b] over rings a < b <= a + 5 with ring b's skin FORWARD of ring a's: skin hanging in
           front of and below the skin under it (0 = no overhang anywhere); ka = that pair's lower ring (the crease)
    turn   deg: the largest turn between successive segments of the sagittal section at rings 2..9
    h      mm: the crease ring's height over the margin (the overhang's ring, else the turn's)."""
    ch = chains(umax)
    v, w = V[ch][..., 1], V[ch][..., 2]
    n, m = v.shape
    hang, ka = np.zeros(n), np.zeros(n, int)
    for a in range(1, m - 1):
        for b in range(a + 1, min(a + 6, m)):
            d = np.where(w[:, b] > w[:, a], v[:, a] - v[:, b], -np.inf)
            better = d > hang
            hang[better], ka[better] = d[better], a
    ang = np.unwrap(np.arctan2(np.diff(w, axis=1), np.diff(v, axis=1)), axis=1)
    tr = np.degrees(np.diff(ang, axis=1))[:, 1:9]
    kt = 2 + tr.argmax(1)
    hk = np.where(hang > 0, ka, kt)
    h = v[np.arange(n), hk] - v[:, 0]
    return {"hang": hang, "turn": tr.max(1), "h": h, "ring": hk, "hang_mean": float(hang.mean()), "hang_max": float(hang.max()),
            "turn_mean": float(tr.max(1).mean()), "h_mean": float(h.mean()), "ring_mode": int(np.bincount(hk).argmax()),
            "brow_h": float((v[:, NR] - v[:, 0]).mean())}


def read_text(q: dict) -> str:
    return (f"overhang {q['hang_mean']:.2f} mm (max {q['hang_max']:.2f}), turn {q['turn_mean']:.0f} deg, crease at ring {q['ring_mode']}, "
            f"{q['h_mean']:.1f} mm over the margin, brow ring {q['brow_h']:.1f} mm over the margin")


# ---------------------------------------------------------------- the fold in MESH space (projskin, 2026-10-13)
FOLD_KEYS = {"crease", "overhang", "thick", "standoff", "amount", "ring", "last", "L", "R", "reach", "taper", "wrap", "crease_by_angle", "tail", "depth", "smooth"}
CREASE_KNOTS = (-9.0, 0.0, 9.0)     # mm across from the eye's centre (inner, middle, outer) where "crease" / "overhang" lists sit
BLINK_FULL = 0.75                   # the fold is gone when the upper margin has come down this share of the open aperture

FADE_RINGS = (0.55, 0.25, 0.08)   # the displacement handed on to the rings past the fold's last one (no hard patch edge)
FADE_DEG = 20.0                    # deg: the displacement fades to nothing this far past the angular span the chains cover

TAIL_WIDTH = 0.9     # mm: the crease tail's groove half-width (a Gaussian's)
TAIL_DEPTH = 0.5     # mm

RING_SMOOTH = 0     # passes of smoothing the fold's displacement along each lid ring (OFF: GNM's BFS rings are not the design's rows; 6 passes flattened the hood to nothing)

CREASE_ROW_PASSES = 3   # passes of smoothing the crease rows' FINAL positions along their rings

WRAP_DEG = 25.0     # deg below the eye's horizontal the fold's chains reach round the OUTER corner (the hood wraps it). At
                    # 70 the crease turned straight down at the corner and ran back under the eye (a roll under the lower
                    # lid; the photos' creases run on 4-11 mm LATERALLY past the canthus and drop only 0-5 mm)

WRAP_MAX = 10.0     # deg: the most the wrap may reach below the horizontal, whatever the spec asks. Round the outer canthus the

CREASE_DEG = 2   # the crease's height along the lid: a polynomial of this degree in the chain angle (one maximum at most)


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("gnm_fold_design", "gnm_fold_mesh")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
