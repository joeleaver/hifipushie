"""GnmFace's lids: the blink's seal (a mixin of GnmFace). Part of face shapes (faceshapes.py has the overview; the class is faceshapes_gnm.GnmFace)."""
from __future__ import annotations

import numpy as np

from .faceshapes import _bump, _ss
from .faceshapes_consts import LID_EDGE, LID_FADE, LID_OVER_FADE, LID_PINCH, LID_SAG, _mirror_ids


class _GnmLids:
    """GnmFace's lids: the blink's seal (both margins brought onto one smooth line) and its helpers."""

    def _lid_seal(self, s: str, Xn: np.ndarray, d: np.ndarray) -> np.ndarray:
        """A blink's lids brought onto ONE smooth line, on the low poly. The basis closes the eye (no ball shows), but
        each low-poly vertex of a lid's margin lands at its own height: a wavy line with dark slots between the
        margins. Across the eye in bins: the upper lid's lowest and the lower lid's highest front vertex as posed; the
        line = a parabola through the lower lid's; each lid is moved onto it (the upper LID_OVER past it). How much
        of that a vertex takes falls off with its posed DISTANCE from its lid's margin (`_lid_share`): a field that
        is smooth over the skin and zero on the cheek and the brow. (It was the vertex's share of its margin's blink
        travel: the lower lid travels ~1 mm, so on the cheek under it that ratio was noise, 0 on one vertex and 1
        on the next: s0urc3's sawtooth in the under-eye shadow, 7-22 mm below the eye.)
        spec.face_shapes.lid_seal: false | amount 0..1 | {"amount", "over", "band", "reach": [upper, lower] m}."""
        o = self.lid_seal
        amount, over, band = o["amount"], o["over"], o["band"]
        ev = self.eyes[s]
        c, r = np.asarray(ev["c"], float), float(ev["r"])
        lm = np.asarray(self.head["lm68"], float)
        ci, co = _mirror_ids([42, 45], s)  # the eye's inner and outer corners
        pairs = [(a_, b_) for a_, b_ in zip(_mirror_ids([43, 44], s), _mirror_ids([47, 46], s))]
        side = lm[co] - lm[ci]
        width = float(np.linalg.norm(side))
        side = side / width
        up = self.up - side * (self.up @ side)
        up /= np.linalg.norm(up)
        out = np.cross(side, up)
        out = out if out @ self.out > 0 else -out
        mid = 0.5 * (lm[ci] + lm[co])
        R0 = Xn - mid
        u, h0, f0 = R0 @ side, R0 @ up, (Xn - c) @ out
        # the opening's centre line at rest: through the corners and half way between each pair of lid landmarks
        ku = [-0.5 * width] + [float((0.5 * (lm[a_] + lm[b_]) - mid) @ side) for a_, b_ in pairs] + [0.5 * width]
        kh = [0.0] + [float((0.5 * (lm[a_] + lm[b_]) - mid) @ up) for a_, b_ in pairs] + [0.0]
        order = np.argsort(ku)
        hc = np.interp(u, np.array(ku)[order], np.array(kh)[order])
        rad = np.linalg.norm(Xn - c, axis=1)
        zone = (np.abs(u) < 0.62 * width) & (rad < 1.9 * r) & (f0 > 0.3 * r)
        front = zone & (rad > r + 2e-4)  # (the skin behind the margins, on the ball, is not a margin)
        upper = h0 > hc
        dh = d @ up
        hp = h0 + dh
        nb = 14
        edges = np.linspace(-0.5 * width, 0.5 * width, nb + 1)
        bc = 0.5 * (edges[1:] + edges[:-1])
        bi = np.clip(np.searchsorted(edges, u) - 1, 0, nb - 1)
        lo_u, hi_l = (np.full(nb, np.nan) for _ in range(2))
        # which vertices ARE a margin: those within a little of their lid's edge as posed (`_lid_edge`). A coarse
        # low poly has a few dozen vertices round the eye and most bins hold no margin vertex: the "highest lower-lid
        # vertex" of such a bin was a cheek vertex 13 mm under the eye, which was then lifted to the line.
        inside = np.abs(u) < 0.5 * width
        cu, cl = front & upper & (dh < -5e-4), front & ~upper
        mu_all = cu & self._lid_edge(u, hp, cu & inside, -1.0, LID_EDGE[0])
        ml_all = cl & self._lid_edge(u, hp, cl & inside, 1.0, LID_EDGE[1])
        for k in range(nb):
            mu = np.flatnonzero(mu_all & (bi == k))
            ml = np.flatnonzero(ml_all & (bi == k))
            if len(mu):
                lo_u[k] = hp[mu].min()
            if len(ml):
                hi_l[k] = hp[ml].max()
        ok = np.isfinite(lo_u) & np.isfinite(hi_l)
        if ok.sum() < 4:
            return d

        def fill(a_):
            return np.interp(bc, bc[np.isfinite(a_)], a_[np.isfinite(a_)])
        lo_u, hi_l = fill(lo_u), fill(hi_l)
        line = np.polyval(np.polyfit(bc, hi_l, 2), bc)
        # a closed eye's lid line arcs DOWN over the globe (lowest mid-eye); through the lower lid's points alone it
        # read "almost straight, a strip pasted across the eye" (expr_r5)
        # (the UPPER lid's target only: lowering the lower lid with it moved the skin under the eye, test
        # test_blink_seal_leaves_the_cheek; the upper lid is the line one sees, passing in front of the lower)
        sag = LID_SAG * np.clip(1 - (2 * bc / width) ** 2, 0, 1)
        # the upper lid goes `over` past the line only where the lids are two sheets: toward the corners they are one
        # skin, and the overlap turned over the small triangles there that have a vertex on each lid (Garrett's 20k
        # export, right eye blinked: 3 triangles at the inner corner, a dark notch; 1 of 0.9 mm2 left)
        if LID_OVER_FADE:
            over_b = over * _ss((LID_FADE[1] * width - np.abs(bc)) / ((LID_FADE[1] - LID_FADE[0]) * width))
            over = over * _ss((LID_FADE[1] * width - np.abs(u)) / ((LID_FADE[1] - LID_FADE[0]) * width))
        else:
            over_b = np.full(nb, over)
        ends = _bump(np.abs(u), 0.5 * width, 0.62 * width) * amount  # (fades out past the corners)
        d = d.copy()
        for sel, cur, tgt, reach, sgn in ((zone & upper, lo_u, line - over_b - sag, o["reach"][0], 1.0),
                                          (zone & ~upper, hi_l, line, o["reach"][1], -1.0)):
            if not sel.any():
                continue
            shift = np.interp(u[sel], bc, np.convolve(np.pad(tgt - cur, 1, mode="edge"), [0.25, 0.5, 0.25], "valid"))
            away = sgn * (hp[sel] - np.interp(u[sel], bc, cur))  # how far from its lid's margin, as posed
            d[sel] += (np.clip(shift, -0.004, 0.004) * self._lid_share(away, reach) * ends[sel])[:, None] * up
        # then no vertex of a lid is left across the line: the band either side of it is squeezed onto its own
        # lid's side (bins put each margin NEAR the line; its vertices still sat a little over and under it,
        # which is the wavy edge)
        ln = np.interp(u, bc, line)
        lu = ln - np.interp(u, bc, sag)  # (the upper lid's own line: dipped mid-eye)
        hp = h0 + d @ up
        t = np.clip((hp - (ln - band)) / (2 * band), 0.0, 1.0)
        tu = np.clip((hp - (lu - band)) / (2 * band), 0.0, 1.0)
        for sel, new in ((zone & upper & (hp < lu + band), lu - over + tu ** LID_PINCH * (band + over)),
                         (zone & ~upper & (hp > ln - band), ln - band * (1 - t) ** LID_PINCH)):
            if sel.any():
                d[sel] += ((new[sel] - hp[sel]) * ends[sel])[:, None] * up
        return d

    @staticmethod
    def _lid_edge(u: np.ndarray, h: np.ndarray, cand: np.ndarray, sgn: float, tol: float) -> np.ndarray:
        """Which vertices lie on a lid's edge: within `tol` m of the candidates' envelope across the eye (sgn +1:
        their upper envelope, the lower lid's margin; -1: the lower one), a parabola fitted with the points on the
        far side of it counting 2%."""
        idx = np.flatnonzero(cand)
        if len(idx) < 4:
            return np.zeros(len(u), bool)
        x, y = u[idx], sgn * h[idx]
        w = np.ones(len(idx))
        for _ in range(20):
            co = np.polyfit(x, y, 2, w=np.sqrt(w))
            w = np.where(y >= np.polyval(co, x), 1.0, 0.02)
        return sgn * h >= np.polyval(co, u) - tol

    @staticmethod
    def _lid_share(away: np.ndarray, reach: float) -> np.ndarray:
        """How much of its margin's correction a lid vertex takes: all of it at the margin (and past it), none
        from `reach` m away, eased between."""
        return 1.0 - _ss(np.clip(away / max(reach, 1e-6), 0.0, 1.0))

    @staticmethod
    def _idw(d):
        w = 1 / np.maximum(d, 1e-5) ** 2
        return w / w.sum(1, keepdims=True)
