"""ROLLED PANELS (N2d of docs/proposals/step5_rewrite.md, "The build" 1): every piece of the pattern is its flat outline
mapped by a DEVELOPABLE map with a handful of numbers, so lengths are given and only bends are chosen, literally.

Joe (2026-11-12) chose "Rolled panels, bends" after three runs failed at one point: turning flats into an assembled 3D
shape with positions as the unknowns (N2c: links 300-2,900 % off their cut before any bend). Here no point is ever a
free variable:
- A PANEL is a piece's flat (or a part of it between fold rows) mapped by: a ROLL round a cylinder or a CONE (the
  generatrix's direction in the flat, phi, the curvature across it, kappa: 0 = flat, and the taper g = sin of the cone's
  half-angle: 0 = a cylinder; N2e: a sleeve cap's or darted panel's ease needs a cone) then a rigid motion (a rotation
  vector and a translation): 9 numbers. Cylinder or cone is the fit's choice per panel, never by name. The map is ISOMETRIC by construction: every link of every chain is at its cut whatever the numbers
  (`roll`: (s, t) -> (s, sin(k t) / k, (1 - cos(k t)) / k), the flat's +z onto the surface's normal).
- A FOLD ROW splits its piece into panels (each point's side of each row; row points belong to both) joined by a
  HINGE along the row with one angle: the turned panel's direction across the row against the plan's turn (the turn
  split over the draft's rows, the way chain_lay.fold_way says (N2i: THE one rule, from the draft's turn and the piece's
  outside: `out`, chain_lay.outside at the start) in the flat's +z terms (x the flat's winding), +1 = +z).
  The turned side of a row is its smaller side. N2f: the hinge RULES its turned panel (`resolve`): that panel's rigid
  motion is its base's at the row's middle turned by the plan's angle, exactly; only its roll is its own. A fold lying on
  another piece (plan lies_on) is not ruled: its turn stays a residual.
- A piece sewn to nothing (a ply that follows its host) is not a panel: it is bound on its host afterwards.
Panels(cnet, plan, skip, out) -> .panels [{piece, ids, c (flat centre)}], .owner (point -> its first panel), .hinges, .rule.
place(th, k, uv) / positions(th): the map; fit_start(Xs): each panel's numbers fitted to a start (Kabsch then the roll).
Nothing here knows a garment, a piece's role or a wear state.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .chain_core import ChainRefused
from .chain_lay_net import _side

NP = 9  # numbers per panel: rotation vector (3), translation (3), roll axis angle in the flat, curvature, taper
G0 = 1e-3  # a start's taper: a cylinder to the eye, but the fit's differences see the cone (at 0 they don't)
G_MAX = 0.95  # |taper| (the cone's sin half-angle over its curvature ratio) is clipped here


def _cyl(s, t, kappa):
    a = kappa * t
    if abs(kappa) < 1e-6:
        return s, t - kappa * kappa * t ** 3 / 6, kappa * t * t / 2
    return s, np.sin(a) / kappa, (1 - np.cos(a)) / kappa


def _cone(s, t, kappa, g):
    """(s, t) rolled round a CONE whose generatrix through the centre runs along s and whose curvature across it at the
    centre is kappa; g = sin(half-angle) sets the apex at s = -1 / (g kappa) (g -> 0: the cylinder). Isometric: a flat
    point at polar (rho, alpha) about the apex goes to slant rho, angle alpha / g round the axis."""
    sk, sg = (1.0 if kappa >= 0 else -1.0), (1.0 if g >= 0 else -1.0)
    k, gg = abs(kappa), min(abs(g), G_MAX)
    s = s * sg
    rc = 1.0 / (gg * k)
    rho = np.hypot(s + rc, t)
    th = np.arctan2(t, s + rc) / gg
    cb = np.sqrt(1 - gg * gg)
    x = rho * (cb * cb + gg * gg * np.cos(th)) - rc
    y = rho * gg * np.sin(th)
    z = rho * gg * cb * (1 - np.cos(th))
    return x * sg, y, z * sk


def roll(uv, phi, kappa, g=0.0):
    """The flat uv (n, 2, about the panel's centre) rolled round a cylinder (g = 0) or a cone (g = sin of its half
    angle): (n, 3) local, isometric (module doc)."""
    c, s_ = np.cos(phi), np.sin(phi)
    s = uv[:, 0] * c + uv[:, 1] * s_
    t = -uv[:, 0] * s_ + uv[:, 1] * c
    if abs(g) < 1e-7 or abs(kappa) < 1e-6:
        x, y, z = _cyl(s, t, kappa)
    else:
        x, y, z = _cone(s, t, kappa, g)
    # (back into the flat's own axes so phi = 0, kappa = 0 is the identity on the plane)
    return np.c_[x * c - y * s_, x * s_ + y * c, z]


def roll_normal(uv, phi, kappa, g=0.0, eps=1e-4):
    """The unit normal of the rolled flat at uv (the flat's +z where kappa = 0), by the map's own differences."""
    du = roll(uv + [eps, 0], phi, kappa, g) - roll(uv - [eps, 0], phi, kappa, g)
    dv = roll(uv + [0, eps], phi, kappa, g) - roll(uv - [0, eps], phi, kappa, g)
    n = np.cross(du, dv)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)


class Panels:
    """The panels of a chains-only network (module doc)."""

    def __init__(self, cnet, plan=None, skip=(), out=None):
        from .chain_lay import _draft_fold, _uv_wind, fold_way
        self.cnet = cnet
        plan = plan or {}
        rows_of: dict = {}
        for bid, f in sorted((plan.get("folds") or {}).items()):
            fd = _draft_fold(cnet, f, bid)
            rows = [np.asarray(r, np.int64) for r in fd.get("rows") or []]
            if f["on"] not in (out or {}):
                raise ChainRefused(f"fold {bid}: no outside read for {f['on']}: place it first (chain_lay.outside)")
            way = fold_way(fd, out[f["on"]]) * _uv_wind(cnet, f["on"])  # (F's normal side -> the flat's +z side)
            for r in rows:
                rows_of.setdefault(cnet.pid(f["on"]), []).append((r, float(f["turn_deg"]) / len(rows), way, bid,
                                                                  bool(f.get("lies_on")) and f["lies_on"] != f["on"]))
        self.panels, self.hinges = [], []
        self.owner = -np.ones(cnet.n, np.int64)
        for p, nm in enumerate(cnet.names):
            if nm in skip:
                continue
            ids = np.where(cnet.piece == p)[0]
            rows = rows_of.get(p, [])
            if not rows:
                self._add(nm, ids)
                continue
            S = np.stack([_side(cnet.uv, r, cnet.uv[ids]) for r, *_ in rows], 1)
            # (the turned side of a fold's first row is its smaller side; every row of that fold turns the same way:
            # its base side is the one holding the base's farthest point from the first row)
            for bid in dict.fromkeys(rr[3] for rr in rows):
                ks = [k for k, rr in enumerate(rows) if rr[3] == bid]
                k0 = ks[0]
                sm = [np.ptp(cnet.uv[ids[S[:, k0] == s_]], 0).prod() if (S[:, k0] == s_).any() else 0 for s_ in (1, -1)]
                base = -1.0 if sm[0] <= sm[1] else 1.0
                cand = np.where(S[:, k0] == base)[0]
                dist = np.min(np.linalg.norm(cnet.uv[ids[cand]][:, None] - cnet.uv[rows[k0][0]][None], axis=2), axis=1)
                far = cand[np.argmax(dist)]
                for k in ks:
                    if S[far, k] > 0:
                        S[:, k] *= -1  # (-1: the base side, +1: the turned side)
            # (a panel per side pattern; a row point counts on both sides of its row, so the strip between two rows
            # with no cloth point between them is a panel of its own rows' points)
            cands = set()
            for s_ in np.unique(S, axis=0):
                z = np.where(s_ == 0)[0]
                for bits in range(2 ** len(z)):
                    g = s_.copy()
                    g[z] = [1 if (bits >> q) & 1 else -1 for q in range(len(z))]
                    cands.add(tuple(g))
            sig, pan = [], {}
            for g in sorted(cands):
                m = ((S == np.array(g)) | (S == 0)).all(1)
                if m.sum() >= 4 and (np.ptp(cnet.uv[ids[m]], 0) > 1e-3).all():
                    sig.append(np.array(g))
                    pan[g] = self._add(nm, ids[m])
            # (a hinge between two panels of the piece sharing a line of points: the rows between them turn together,
            # e.g. a hem's two rows with no cloth point between them)
            for g in sig:
                for g1 in sig:
                    D = np.where(g != g1)[0]
                    if not len(D) or (g1[D] != 1).any() or (g[D] != -1).any():
                        continue
                    a, b = pan[tuple(g)], pan[tuple(g1)]
                    sh = np.intersect1d(self.panels[a]["ids"], self.panels[b]["ids"])
                    if len(sh) < 2:
                        continue
                    k = int(D[0])
                    r = rows[k][0]
                    turn = float(sum(rows[q][1] for q in D))
                    way, bid = rows[k][2], rows[k][3]
                    on = r[np.isin(r, sh)] if np.isin(r, sh).sum() >= 2 else sh
                    d = cnet.uv[on[-1]] - cnet.uv[on[0]]
                    m2 = np.array([-d[1], d[0]]) / max(np.linalg.norm(d), 1e-12)
                    tp = self.panels[b]["ids"]
                    if (cnet.uv[tp].mean(0) - cnet.uv[on].mean(0)) @ m2 < 0:
                        m2 = -m2
                    self.hinges.append({"base": a, "turned": b, "row": on, "turn_deg": turn, "way": way,
                                        "mid": cnet.uv[on].mean(0), "across": m2, "name": f"{bid}#{k}",
                                        "free": rows[k][4]})
        self.n = len(self.panels)
        self.shared = [(h["base"], h["turned"], h["row"]) for h in self.hinges]
        # (N2f: a hinge RULES its turned panel: that panel's rigid motion is its base's at the row's middle turned by the
        # plan's angle (exact by construction, no turn residual); its own numbers keep only its roll. A fold that lies
        # on ANOTHER piece is not ruled (it must follow what it rests on: its turn stays a residual). Bases first; a
        # panel ruled once.)
        self.rule, seen = [], set()
        left = list(range(len(self.hinges)))
        while left:
            ok = [i for i in left if self.hinges[i]["base"] not in {self.hinges[j]["turned"] for j in left if j != i}]
            if not ok:
                break
            for i in ok:
                h = self.hinges[i]
                if h["turned"] not in seen and h["base"] != h["turned"] and not h["free"]:
                    seen.add(h["turned"])
                    self.rule.append(i)
                left.remove(i)
        self.ruled = {self.hinges[i]["turned"]: i for i in self.rule}
        self.up = {b: self.hinges[i]["base"] for b, i in self.ruled.items()}

    def ancestors(self, k):
        """Panel k and every panel its map depends on (its ruling bases)."""
        out = [k]
        while out[-1] in self.up:
            out.append(self.up[out[-1]])
        return out

    def _frame(self, th, k, mid, m, local=False):
        """(point, row tangent, across) of panel k's map at flat mid, across m (unit)."""
        t = np.array([-m[1], m[0]])
        f = (lambda q: roll(q - self.panels[k]["c"], th[6], th[7], self._taper(th, k))) if local else \
            (lambda q: self.place(th, k, q))
        e = 1e-4
        P = f(np.array([mid, mid + e * t, mid - e * t, mid + e * m, mid - e * m]))
        return P[0], (P[1] - P[2]) / (2 * e), (P[3] - P[4]) / (2 * e)

    def resolve(self, TH):
        """TH with every ruled panel's rigid motion set from its base and the hinge's angle (module doc)."""
        TH = np.array(TH, float)
        for i in self.rule:
            h = self.hinges[i]
            a, b, mid, m = h["base"], h["turned"], h["mid"], h["across"]
            pa, ta, wa = self._frame(TH[a], a, mid, m)
            na = self.normal(TH[a], a, mid[None])[0] * h["way"]
            ang = np.radians(h["turn_deg"])
            wt = np.cos(ang) * wa + np.sin(ang) * na
            pb, tb, wb = self._frame(TH[b], b, mid, m, local=True)
            def orth(t, w):
                t = t / np.linalg.norm(t)
                w = w - (w @ t) * t
                w /= np.linalg.norm(w)
                return np.c_[t, w, np.cross(t, w)]
            R = orth(ta, wt) @ orth(tb, wb).T
            TH[b, 3:6] = pa - R @ pb
            TH[b, :3] = Rotation.from_matrix(R).as_rotvec()
        return TH

    def free_cols(self):
        """Per panel, the columns of its numbers the solver moves (a ruled panel: only its roll)."""
        return [[6, 7, 8] if k in self.ruled else list(range(NP)) for k in range(self.n)]

    def _add(self, nm, ids):
        k = len(self.panels)
        self.panels.append({"piece": nm, "ids": ids, "c": self.cnet.uv[ids].mean(0)})
        free = self.owner[ids] < 0
        self.owner[ids[free]] = k
        return k

    # ---- the map
    def _taper(self, th, k):
        """The cone's taper, clipped so its apex stays off the panel (a flat holding its apex makes no cone): no panel
        point lies past the apex along the generatrix."""
        P = self.panels[k]
        g, kap = float(th[8]), abs(float(th[7]))
        if kap < 1e-9 or g == 0.0:
            return g
        d = self.cnet.uv[P["ids"]] - P["c"]
        s = d[:, 0] * np.cos(th[6]) + d[:, 1] * np.sin(th[6])
        far = max(float((-s * np.sign(g)).max()), 1e-3)
        lim = min(G_MAX, 1.0 / (1.1 * kap * far))
        return float(np.clip(g, -lim, lim))

    def place(self, th, k, uv):
        """Panel k's numbers th (NP,) applied to flat points uv (n, 2)."""
        L = roll(uv - self.panels[k]["c"], th[6], th[7], self._taper(th, k))
        return Rotation.from_rotvec(th[:3]).apply(L) + th[3:6]

    def normal(self, th, k, uv):
        return Rotation.from_rotvec(th[:3]).apply(roll_normal(uv - self.panels[k]["c"], th[6], th[7], self._taper(th, k)))

    def positions(self, TH, which=None):
        """(n, 3): every point at its owner panel's map (which: a per-point panel instead of the owner)."""
        which = self.owner if which is None else which
        X = np.full((self.cnet.n, 3), np.nan)
        for k in range(self.n):
            m = which == k
            if m.any():
                X[m] = self.place(TH[k], k, self.cnet.uv[m])
        return X

    def hinge_read(self, TH, h):
        """(turned panel's direction across the row, target direction, measured turn deg) at the row's middle (the
        maps' own central differences: a 1 mm step on a narrow strip rolled tight read a ruled turn 13 deg off)."""
        a, b, mid, m = h["base"], h["turned"], h["mid"], h["across"]
        wa = self._frame(TH[a], a, mid, m)[2]
        wb = self._frame(TH[b], b, mid, m)[2]
        mid = mid[None]
        n = self.normal(TH[a], a, mid)[0] * h["way"]
        th = np.radians(h["turn_deg"])
        tgt = np.cos(th) * wa + np.sin(th) * n
        got = np.degrees(np.arctan2(wb @ n, wb @ wa))
        return wb, tgt, float(got)

    def fit_start(self, Xs):
        """Each panel's numbers fitted to start positions Xs (n, 3) of the network's points: (P, NP)."""
        TH = np.zeros((self.n, NP))
        for k, P in enumerate(self.panels):
            ids = P["ids"]
            A = np.c_[self.cnet.uv[ids] - P["c"], np.zeros(len(ids))]
            B = Xs[ids]
            ma, mb = A.mean(0), B.mean(0)
            U, _, Vt = np.linalg.svd((A - ma).T @ (B - mb))
            D = np.diag([1.0, 1.0, np.sign(np.linalg.det(Vt.T @ U.T)) or 1.0])
            R = Vt.T @ D @ U.T
            th0 = np.r_[Rotation.from_matrix(R).as_rotvec(), mb - R @ ma, 0.0, 0.0, G0]
            best = None
            for phi in (0.0, np.pi / 2):  # (the roll axis along either flat axis; the fit takes the better)
                for kap in (-12.0, -4.0, 4.0, 12.0):
                    x0 = th0.copy()
                    x0[6], x0[7] = phi, kap
                    r = least_squares(lambda t: (self.place(t, k, self.cnet.uv[ids]) - B).ravel(), x0, max_nfev=200)
                    if best is None or r.cost < best.cost:
                        best = r
            TH[k] = best.x
        return self.resolve(TH)
