"""CHAIN CORE: the chain build's core types and helpers, moved out of chain_garment.py (R3a, behaviour-preserving; the spec
is chain_garment.py's docstring). The build's constants (GAP, LAYER, MAX_FREE_PCT ...), ChainRefused, Pattern (pattern data
only, never positions), Body, Roles and read_roles, hand_of, and the small mesh helpers (joined_faces, zozo_legal,
cn_vnormals). Import them from chain_garment: it stays the one import point."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from . import chain_net as cn
from .chain_net import Contact, Network, unit

PATTERN_KEYS = ("uv", "piece", "names", "F", "folds", "made", "grain", "sew", "sew_seam", "stitch", "marks", "closures",
                "points", "border", "stitch_lines", "roles", "place",
                "starts")  # (starts: step 3+4 measurement data, never positions: piece_start.py)
GAP = 0.0045  # m: soft cloth and stiff parts stay this far off the body (ZOZO's reach + a mesh edge's sag over an arm)
RING_GAP = 0.004  # m: a stiff ring off a limb (ZOZO's reach): it hangs loose, so its gap is the solver's, no more
RING_H = 0.008  # m: mesh size on a stiff ring
UNDER = 0.002  # m: soft cloth under the fall
LAYER = 0.003  # m: one layer of cloth over another (the fall over the shirt, the over placket over the under)
FALL_GAP = GAP + LAYER + 0.002  # the fall rests on the soft cloth under it
REST = 0.1  # weight of the light rest pull (contact itself is 5)
CAP = 0.02  # thread cap of soft cloth (pattern_form.FIT_THREAD_CAP)
SHEAR_LIMIT = 0.27  # the weave's own limit on a mesh edge (zozo_hang.woven_limit, 2 % threads, jam 35 deg)
OPEN_SPREAD = 1.7  # default open wear: the collar points this many neck widths apart
MAX_FREE_PCT = 2.0  # % a free chain link may read off its cut at a stage's end before the build is refused


class ChainRefused(ValueError):
    """A build that can't hold. The message names the piece, the line, the number and the next step."""


@dataclass
class Pattern:
    """Pattern data only (never positions)."""
    M: dict
    stiff: np.ndarray
    bend: np.ndarray
    fold_radius: dict = field(default_factory=dict)  # fold name / piece -> roll radius (m)


def pattern_from_mesh(M: dict, stiff=None, bend=None, fold_radius: dict | None = None) -> Pattern:
    m = {k: M[k] for k in PATTERN_KEYS if k in M}
    n = len(m["uv"])
    return Pattern(m, np.zeros(n) if stiff is None else np.asarray(stiff, float),
                   np.ones(n) if bend is None else np.asarray(bend, float), dict(fold_radius or {}))


@dataclass
class Body:
    V: np.ndarray
    T: np.ndarray
    at: dict

    def __post_init__(self):
        self.V, self.T = np.asarray(self.V, float), np.asarray(self.T, np.int64)
        self.contact = Contact(self.V, self.T)

    def p(self, k):
        return np.asarray(self.at[k], float)


@dataclass
class Roles:
    band: str | None
    fall: str | None
    rings: list
    tubes: list
    panels: list
    front: dict | None
    band_closure: dict | None
    fold: dict | None
    stand: bool = False  # the band is a STAND: nothing turned over it (chain_roles)
    tube_groups: dict = field(default_factory=dict)  # piece -> the pieces of its several-piece tube (chain_roles)
    holds: object = None  # chain_holds.Holds: plies and floating layers, the order, the folds (R3b)

    @property
    def carried(self) -> list:
        """Pieces with no role: plies (they follow their host) and floating layers (they stiffen theirs)."""
        h = self.holds
        return list(h.plies) + list(h.layers) if h is not None else []


def read_roles(net: Network) -> Roles:
    """The pattern's roles: chain_roles.read_roles (its doc: fall, band, stand, rings, tubes of one or more pieces,
    panels, the front lapped or edge to edge)."""
    from .chain_roles import read_roles as rr
    return rr(net)


def hand_of(name: str) -> float:
    """Which side a piece is worn on, by the repo's own naming rule: ".L" = +X, ".R" = -X, else on the centre."""
    return 1.0 if name.endswith(".L") else (-1.0 if name.endswith(".R") else 0.0)


def joined_faces(X, M, bV, bT) -> np.ndarray:
    """The garment's faces with sewn vertices shared and every piece facing outward (the spike's joined.py: pronounced
    seams were mostly per-piece shading). Used by every render of a chain build."""
    X = np.asarray(X, float)
    F = np.asarray(M["F"], np.int64).copy()
    pc = np.asarray(M["piece"])
    s = np.asarray(M["sew"], np.int64).reshape(-1, 2)
    s = s[np.linalg.norm(X[s[:, 0]] - X[s[:, 1]], axis=1) < 0.002]
    root = cn.union_roots(len(X), s)
    N = cn_vnormals(np.asarray(bV, float), np.asarray(bT, np.int64))
    kd = cKDTree(bV)
    for p in np.unique(pc):
        fi = np.where(pc[F[:, 0]] == p)[0]
        c = X[F[fi]].mean(1)
        n = np.cross(X[F[fi, 1]] - X[F[fi, 0]], X[F[fi, 2]] - X[F[fi, 0]])
        if (n * N[kd.query(c)[1]]).sum() < 0:
            F[fi] = F[fi][:, [0, 2, 1]]
    return root[F]


def zozo_legal() -> float:
    """The nearest a cloth point may start to the collider (ZOZO's contact offset + a hair)."""
    return 0.00203


def _keep_roots(net, X):
    return np.asarray(X, float)[net.root]


def cn_vnormals(X, F):
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    N = np.zeros_like(X)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    return unit(N + 1e-30)


def _neighbours(F) -> dict:
    nb: dict = {}
    for a, b in cn.edges_of(F):
        nb.setdefault(int(a), []).append(int(b))
        nb.setdefault(int(b), []).append(int(a))
    return nb
