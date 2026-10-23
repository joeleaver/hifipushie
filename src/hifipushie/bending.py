"""CLOTH BENDING STIFFNESS, KEYED BY FABRIC + INTERFACING (canvas thread, 2026-10-23; Joe: "a collar is not floppy
cloth"; the hold audit, C190 / C191: the canvassed chest and lapels, the shirt's collar, stand, cuffs and placket keep
their shape through STIFFNESS the fit and the styling did not model, so holds stood in for it).

Real practice: a tailored jacket's forepart is CANVASSED (hair canvas + a felt / domette chest piece, pad-stitched and
steamed to the chest's shape), its lapels and undercollar canvassed and pad-stitched into their roll; a dress shirt's
collar, stand, cuffs and front placket are FUSED (a woven fusible interlining). Both raise the cloth's bending rigidity
several- to tens-fold (KES-FB2 bending rigidity B: a suiting wool 0.08-0.15 gf cm2/cm, a fused shirting collar 0.3-1,
a canvassed jacket front 1-3: fusing raises B 3-10 x, a canvas chest 10-30 x the shell alone; Kawabata & Niwa 1989,
Fan, Yu & Hunter 2004 "Clothing appearance and fit" ch. 3: values inferred from the published ranges, not measured on
our cloths). Plain cloth is not zero-stiffness either: it keeps a weak term.

The model (both relax solvers, quasi-static: not a sim, no time, no velocity):
  E_bend = sum_i w_i / A_i | (L x)_i - t_i |^2
L the cot Laplacian of the FLAT PATTERN on the sewn (welded) surface (exact for isometric maps: Bergou et al. 2006's
quadratic bending), A_i the lumped pattern area, w_i the vertex's bending weight (`weights`), t_i the REST curvature
vector: "flat" (t = 0: Bergou) or "start" (projective dynamics' bending constraint, Bouaziz et al. 2014: the rest
shape's mean-curvature magnitude |(L x_rest)_i| along the current curvature direction; rotation invariant). The matrix
is constant (prefactored with the rest of the global step); only t moves with x (the local step).

Weights: INTERFACING x (BEND_FABRIC, off: the plain level stays each solver's calibrated term) FABRIC (the garment
fabric's bending length, Peirce: B ~ w c^3, relative to wool suiting's). INTERFACING
(per vertex, cloth.interfacing's 0..1 share, feathered; the entry's "kind": "canvas" (a jacket forepart / lapel /
undercollar) or "fusible" (default: collars, stands, cuffs, plackets, facings)). Folds: the fit keeps fold rows / turned
flaps / made pieces as ARAP cells (their folded rests) outside this term; the styling's rest "start" carries a fold as
part of the rest shape, so the term never flattens a declared fold.

Known answers: tests/test_bending.py (a canvassed strip clamped at one end holds near straight where plain cloth bends;
a rolled collar strip keeps its roll radius; a folded strip stays folded).
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix, diags

# BEND_KIND: an interfacing's bending weight x the plain cloth's (the garment fabric's own). Ratios from the KES-B
# ranges in the module docstring (inferred): a fused interlining 3-10 x (8), a canvassed front 10-30 x (20).
BEND_KIND = {"plain": 1.0, "fusible": 8.0, "canvas": 20.0}
BEND_DEFAULT_KIND = "fusible"
# FABRIC: bending rigidity ~ c^3 (Peirce: B = w g c^3; per mass it is c^3): relative to wool suiting (c 16 mm, the
# middle of the KB's 14-18): shirting (c 10-14, 12) 0.42, a wool coating / denim (22-30) 3-6. 1.0 without KB data.
BEND_REF_MM = 16.0
# BEND_FABRIC: the fabric factor in `weights`. OFF by default: the plain cloth's level stays each solver's calibrated
# plain term (pattern_form.FIT_BEND; the styling's STYLE_BEND_PLAIN), so turning the keyed bending on changes only the
# interfaced cloth (a shirting shirt's whole fit would otherwise drop to 0.42 of its validated bending).
BEND_FABRIC = False


def fabric_factor(g: dict | None) -> float:
    """The garment fabric's bending relative to wool suiting (Peirce c^3 from the KB's bending_length_mm); 1.0 when
    the fabric has no KB entry."""
    if not g:
        return 1.0
    try:
        from . import cloth, cloth_reference
        fab = cloth.fabric(g)
        e = cloth_reference._fabric_entry(fab.get("kb") or fab.get("name"))
        bl = (e or {}).get("bending_length_mm")
        if not bl:
            return 1.0
        c = 0.5 * (float(bl[0]) + float(bl[1]))
        return float((c / BEND_REF_MM) ** 3)
    except Exception:  # noqa: BLE001 (no fabric data: the plain weight)
        return 1.0


def interfacing_kinds(Bp: dict, M: dict, kinds: dict | None = None) -> np.ndarray:
    """Per vertex: the interfacing weight factor (BEND_KIND of its entry's "kind", else `kinds` by the piece's name or
    its base name before the "." (the garment key "interfacing_kind": {"front": "canvas", "stand": "canvas"}), else
    BEND_DEFAULT_KIND; feathered by cloth.interfacing's share; the strongest entry wins); 1.0 (plain) elsewhere."""
    from . import cloth
    n = len(M["uv"])
    out = np.ones(n)
    ents = list((Bp or {}).get("interfaced") or [])
    if not ents:
        return out
    for e in ents:
        try:
            s = cloth.interfacing(dict(Bp, interfaced=[e]), M)
        except (KeyError, ValueError, IndexError):  # (an entry naming a piece this mesh doesn't have)
            continue
        nm = e if isinstance(e, str) else e.get("piece", "")
        kind = ((e.get("kind") if isinstance(e, dict) else None) or (kinds or {}).get(nm)
                or (kinds or {}).get(nm.split(".")[0]) or BEND_DEFAULT_KIND)
        k = BEND_KIND.get(kind, BEND_KIND[BEND_DEFAULT_KIND])
        out = np.maximum(out, 1.0 + s * (k - 1.0))
    return out


def weights(Bp: dict | None, M: dict, g: dict | None = None) -> np.ndarray:
    """Per vertex bending weight (x the garment's plain cloth): interfacing_kinds, x fabric_factor(g) with BEND_FABRIC."""
    return (fabric_factor(g) if BEND_FABRIC else 1.0) * interfacing_kinds(Bp or {}, M, (g or {}).get("interfacing_kind"))


def cot_laplacian(F: np.ndarray, U: np.ndarray, n: int):
    """(L (n, n) csr, lumped area (n,)) of the flat pattern U (per face corners (m, 3, 2) or per vertex (n, 2) with
    F (m, 3) into n vertices): L = D - W, W_ij = (cot a + cot b) / 2."""
    F = np.asarray(F, int)
    Uc = U if U.ndim == 3 else U[F]
    Uc = np.concatenate([Uc, np.zeros(Uc.shape[:2] + (1,))], 2)
    I, J, Wt = [], [], []
    area = np.zeros(n)
    for k in range(3):
        i, j = F[:, k], F[:, (k + 1) % 3]
        a_ = Uc[:, k] - Uc[:, (k + 2) % 3]
        b_ = Uc[:, (k + 1) % 3] - Uc[:, (k + 2) % 3]
        cr = np.linalg.norm(np.cross(a_, b_), axis=1)
        cot = np.sum(a_ * b_, 1) / np.maximum(cr, 1e-14)
        I += [i, j]
        J += [j, i]
        Wt += [0.5 * cot, 0.5 * cot]
        np.add.at(area, F[:, k], cr / 6.0)
    W = coo_matrix((np.concatenate(Wt), (np.concatenate(I), np.concatenate(J))), shape=(n, n)).tocsr()
    return (diags(np.asarray(W.sum(1)).ravel()) - W).tocsr(), area


def boundary(F: np.ndarray, n: int) -> np.ndarray:
    """(n,) True on the surface's boundary (edges in one face only)."""
    E = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    ue, c = np.unique(E, axis=0, return_counts=True)
    b = np.zeros(n, bool)
    b[ue[c == 1].ravel()] = True
    return b


def hinges(F: np.ndarray, U: np.ndarray):
    """Interior edges of the (welded) mesh as hinges: (H (h, 4) vertex ids [e0, e1, opposite in face A, opposite in
    face B], alpha (h, 4) the hinge's curvature stencil, el (h,) the edge's rest length, ar (h,) the two faces' rest
    area). The stencil is the one combination of the four FLAT rest points (face B unfolded onto face A's plane across
    the edge: the faces may come from different pieces, each in its own pattern frame) with sum 0 and sum alpha p = 0:
    it vanishes for every planar placement and reads |e| x the fold angle for a small fold (Bergou et al. 2006's edge
    vector, up to scale)."""
    F = np.asarray(F, int)
    Uc = U if U.ndim == 3 else U[F]
    m = len(F)
    rec = {}
    pairs = []
    for f in range(m):
        for k in range(3):
            a, b = int(F[f, k]), int(F[f, (k + 1) % 3])
            key = (a, b) if a < b else (b, a)
            if key in rec:
                pairs.append((rec.pop(key), (f, k)))
            else:
                rec[key] = (f, k)
    if not pairs:
        z = np.zeros((0, 4))
        return z.astype(int), z, np.zeros(0), np.zeros(0)
    H = np.zeros((len(pairs), 4), int)
    P = np.zeros((len(pairs), 4, 2))
    ar = np.zeros(len(pairs))
    for i, ((fa, ka), (fb, kb)) in enumerate(pairs):
        a, b, c = F[fa, ka], F[fa, (ka + 1) % 3], F[fa, (ka + 2) % 3]
        pa, pb, pc = Uc[fa, ka], Uc[fa, (ka + 1) % 3], Uc[fa, (ka + 2) % 3]
        # face B: the same edge (in either order) and its own opposite vertex, by its own rest lengths
        jb = [F[fb, (kb + q) % 3] for q in range(3)]
        qb = [Uc[fb, (kb + q) % 3] for q in range(3)]
        d = jb[2]
        ua = qb[jb.index(a)] if a in jb else qb[0]
        ub = qb[jb.index(b)] if b in jb else qb[1]
        r0, r1 = np.linalg.norm(qb[2] - ua), np.linalg.norm(qb[2] - ub)
        e = pb - pa
        L = max(float(np.linalg.norm(e)), 1e-12)
        ex = e / L
        ey = np.array([-ex[1], ex[0]])
        x = (r0 ** 2 - r1 ** 2 + L ** 2) / (2 * L)
        y = np.sqrt(max(r0 ** 2 - x ** 2, 0.0))
        side = np.sign(np.dot(pc - pa, ey)) or 1.0
        pd = pa + x * ex - side * y * ey  # (unfolded: the other side of the edge from face A's opposite vertex)
        H[i] = (a, b, c, d)
        P[i] = (pa, pb, pc, pd)
        e1a, e2a = pb - pa, pc - pa
        e2b = pd - pa
        ar[i] = 0.5 * abs(e1a[0] * e2a[1] - e1a[1] * e2a[0]) + 0.5 * abs(e1a[0] * e2b[1] - e1a[1] * e2b[0])
    # the null vector of [[1 1 1 1], [x], [y]] per hinge (3 x 4: one dimensional)
    A3 = np.concatenate([np.ones((len(P), 1, 4)), np.transpose(P, (0, 2, 1))], 1)
    _, _, Vt = np.linalg.svd(A3)
    al = Vt[:, -1, :]
    # scale: a small fold by theta of face B about the edge moves d by dist(d, edge) theta -> |sum alpha x| = |e| theta
    el = np.linalg.norm(P[:, 1] - P[:, 0], axis=1)
    exx = (P[:, 1] - P[:, 0]) / np.maximum(el, 1e-12)[:, None]
    rel = P[:, 3] - P[:, 0]
    dist = np.abs(rel[:, 0] * exx[:, 1] - rel[:, 1] * exx[:, 0])
    al = al * (el / np.maximum(np.abs(al[:, 3]) * dist, 1e-12))[:, None]
    return H, al, el, ar


class Bending:
    """The bending term on a (welded) mesh: per interior edge (a hinge, `hinges`) w_e 3 / (A0 + A1) |sum alpha x -
    t_e|^2 x scale x mean edge^2 (the edge terms' scale, as pattern_form.FIT_BEND). Edge-based, not the vertex
    Laplacian: |L x|^2 at vertices only sees MEAN curvature, so a strip bent along its length and curled across it (a
    saddle) cost nothing and a canvassed strip fell as fast as a plain one (proof1, 2026-10-23). w: per vertex weight
    (an edge takes the mean of its two vertices'; 0 = no term, `skip` too); rest: "flat" (t = 0) or an (n, 3) rest
    shape (|alpha . x_rest| along the current direction: projective dynamics' bending, rotation invariant)."""

    def __init__(self, F: np.ndarray, U: np.ndarray, n: int, w: np.ndarray, scale: float, rest="flat",
                 skip: np.ndarray | None = None, flat_below: float | None = None):
        """flat_below: hinges whose weight is at or under this rest FLAT whatever `rest` says (plain cloth's rest is
        flat; only interfaced / canvassed cloth is made to a shape: moulded, steamed, rolled)."""
        H, al, el, ar = hinges(F, U)
        Uc = U if U.ndim == 3 else U[np.asarray(F, int)]
        h2 = float(np.mean(np.sum((Uc[:, 1] - Uc[:, 0]) ** 2, 1)))
        w = np.asarray(w, float)
        we = 0.5 * (w[H[:, 0]] + w[H[:, 1]]) if len(H) else np.zeros(0)
        if skip is not None and len(H):
            sk = np.asarray(skip, bool)
            we = we * ~(sk[H[:, 0]] & sk[H[:, 1]])
        self.H, self.al = H, al
        self.d = we * float(scale) * h2 * 3.0 / np.maximum(ar, 1e-12)
        h = len(H)
        self.S = coo_matrix((al.ravel(), (np.repeat(np.arange(h), 4), H.ravel())), shape=(h, n)).tocsr()
        self.K = (self.S.T @ diags(self.d) @ self.S).tocsr()
        self.mag = None
        if not (isinstance(rest, str) and rest == "flat"):
            R0 = np.asarray(rest, float)
            # THE REST IN THE HINGE'S OWN FRAME (edge e, normal n, m = n x e): the stencil of a placement that is not
            # isometric to the flat pattern (the fit's threads strain a few %) has in-plane parts too; a target along
            # the normal only put forces on the start (the shirt's first relax went from threads 7.0 to 14.0 %). SIGNED
            # (an unsigned magnitude let a roll flip over its stand for free: edge 24 -> -22 mm). A hinge folded past
            # 90 deg (a collar's fall over its stand, a lapel's turn): its summed normal is noise, so its out-of-edge
            # part goes along the stencil's own current direction (the fold's bisector, well defined at a hairpin).
            d0 = self.S @ R0
            e0, n0 = self._frame(R0)
            self.ce = np.einsum("hd,hd->h", d0, e0)
            self.cn = np.einsum("hd,hd->h", d0, n0)
            self.cm = np.einsum("hd,hd->h", d0, np.cross(n0, e0))
            self.big = self._fold_angle(R0) > np.radians(90) if len(H) else np.zeros(0, bool)
            self.cp = np.linalg.norm(d0 - self.ce[:, None] * e0, axis=1)
            self.mag = np.linalg.norm(d0, axis=1)
            if flat_below is not None and len(H):
                flat = we <= flat_below + 1e-9
                self.mag[flat] = 0.0
                for c_ in (self.ce, self.cn, self.cm, self.cp):
                    c_[flat] = 0.0

    def _frame(self, X: np.ndarray):
        a, b = X[self.H[:, 0]], X[self.H[:, 1]]
        e = (b - a) / np.maximum(np.linalg.norm(b - a, axis=1, keepdims=True), 1e-15)
        return e, self._normal(X)

    def _normal(self, X: np.ndarray) -> np.ndarray:
        """Per hinge: the unit normal of its two faces (a, b, c) and (b, a, d), summed."""
        a, b, c, d = (X[self.H[:, k]] for k in range(4))
        n = np.cross(b - a, c - a) + np.cross(a - b, d - b)
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)

    def _fold_angle(self, X: np.ndarray) -> np.ndarray:
        """Per hinge: the dihedral fold angle (rad, 0 = flat) from the two faces' normals."""
        a, b, c, d = (X[self.H[:, k]] for k in range(4))
        na, nb = np.cross(b - a, c - a), np.cross(a - b, d - b)
        cs = np.einsum("hd,hd->h", na, nb) / np.maximum(np.linalg.norm(na, axis=1) * np.linalg.norm(nb, axis=1), 1e-30)
        return np.arccos(np.clip(cs, -1.0, 1.0))

    def target(self, X: np.ndarray) -> np.ndarray | None:
        """t (h, 3): the rest stencil vector carried into the hinge's current frame (see __init__); None for a flat
        rest."""
        if self.mag is None:
            return None
        e, n = self._frame(X)
        t = self.ce[:, None] * e + self.cn[:, None] * n + self.cm[:, None] * np.cross(n, e)
        if self.big.any():
            d = (self.S @ X)[self.big]
            eb = e[self.big]
            u = d - np.einsum("hd,hd->h", d, eb)[:, None] * eb
            t[self.big] = self.ce[self.big, None] * eb + self.cp[self.big, None] * u / np.maximum(
                np.linalg.norm(u, axis=1, keepdims=True), 1e-12)
        return t

    def rhs(self, X: np.ndarray) -> np.ndarray:
        """S^T diag(d) t(X): the global step's right-hand side (zero for a flat rest)."""
        t = self.target(X)
        if t is None:
            return np.zeros_like(X)
        return self.S.T @ (self.d[:, None] * t)

    def energy(self, X: np.ndarray) -> float:
        d = self.S @ X
        t = self.target(X)
        if t is not None:
            d = d - t
        return float(np.sum(self.d[:, None] * d * d))

    def fold_deg(self, X: np.ndarray) -> np.ndarray:
        """Per hinge: the fold angle read from the stencil (deg; |alpha . x| / |e| for small folds)."""
        el = np.linalg.norm(X[self.H[:, 1]] - X[self.H[:, 0]], axis=1)
        return np.degrees(np.linalg.norm(self.S @ X, axis=1) / np.maximum(el, 1e-12))
