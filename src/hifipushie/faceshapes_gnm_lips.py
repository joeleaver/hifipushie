"""GnmFace's lips: rings, corners, rolls, the seam, the smile's edge and fold (a mixin of GnmFace). Part of face shapes (faceshapes.py has the overview; the class is faceshapes_gnm.GnmFace)."""
from __future__ import annotations

import numpy as np

from . import faceshapes
from .faceshapes import _ss, _unit

class _GnmLips:
    """GnmFace's lips: the lip rings, the corners' meeting, the rolls behind and tucked, the seam check, the
    smile's edge and fold, the lips' meeting."""

    def _lip_rings(self) -> dict:
        """GNM's lips as rings (its index space): the skin's open mouth loop (where the sock joins), ring k out
        from it; the contact ring (base.LIP_RING out: the inner-lip landmarks sit on it) split in an upper and a
        lower half by its corners."""
        if "rings" in self._gnm:
            return self._gnm["rings"]
        import collections
        from . import base as basemod
        G = self._setup()
        g = G["g"]
        skin = np.asarray(g["skin"], bool)
        Q = np.asarray(g["quads"])
        Q = Q[skin[Q].all(1)]
        cnt = collections.Counter()
        adj = collections.defaultdict(set)
        for q in Q:
            for k in range(4):
                a, b = int(q[k]), int(q[(k + 1) % 4])
                cnt[(min(a, b), max(a, b))] += 1
                adj[a].add(b)
                adj[b].add(a)
        V = np.asarray(G["c"]["V"], float)
        X0 = G["X0"]
        seam = 0.5 * (X0[62] + X0[66])
        reach = 3.0 * float(np.linalg.norm(X0[54] - X0[48]))
        loop = {v for (a, b), c in cnt.items() if c == 1 for v in (a, b)
                if np.linalg.norm(V[a] - seam) < reach and np.linalg.norm(V[b] - seam) < reach}
        lev = {v: 0 for v in loop}
        dq = collections.deque(lev)
        while dq:
            v = dq.popleft()
            if lev[v] >= basemod.LIP_RING + faceshapes.LIP_HOLD + faceshapes.LIP_FADE:
                continue
            for w in adj[v]:
                if w not in lev:
                    lev[w] = lev[v] + 1
                    dq.append(w)
        ring = basemod.LIP_RING
        def halves(k):
            """Ring k as an (upper, lower) pair of vertex lists from corner to corner, or None."""
            rv = [v for v, lv in lev.items() if lv == k]
            rs = set(rv)
            nb = {v: [w for w in adj[v] if w in rs] for v in rv}
            if not rv or any(len(n) != 2 for n in nb.values()):
                return None
            lp, prev = [rv[0]], None
            while True:
                nx = [w for w in nb[lp[-1]] if w != prev]
                prev = lp[-1]
                if nx[0] == lp[0]:
                    break
                lp.append(nx[0])
            if len(lp) != len(rv):
                return None
            x = V[lp, 0]
            i0, i1, m = int(np.argmin(x)), int(np.argmax(x)), len(lp)
            a = [lp[(i0 + j) % m] for j in range((i1 - i0) % m + 1)]
            b = [lp[(i1 + j) % m] for j in range((i0 - i1) % m + 1)][::-1]
            return (a, b) if V[a, 1].mean() > V[b, 1].mean() else (b, a)  # (GNM's frame: Y up)
        out = {"lev": lev, "ok": False}
        h = halves(ring)
        if h:
            out.update(ok=True, up=h[0], lo=h[1])
            out["outer"] = {k: halves(k) for k in list(range(0, ring)) + list(range(ring + 1, ring + faceshapes.LIP_HOLD + 2))}
        # the mouth sock, ring by ring in from the loop (negative levels): it rides with the lips' close, fading
        # (left still, the loop's ring stretched against it in every shape that takes the close back)
        sock = np.asarray(g["groups"]["mouth_sock"]) > 0.5
        sadj = collections.defaultdict(set)
        for q in np.asarray(g["quads"]):
            if (sock[q] | skin[q]).all() and sock[q].any():
                for k in range(4):
                    a, b = int(q[k]), int(q[(k + 1) % 4])
                    sadj[a].add(b)
                    sadj[b].add(a)
        dq = collections.deque(v for v in loop)
        sl = {v: 0 for v in loop}
        while dq:
            v = dq.popleft()
            if sl[v] >= faceshapes.LIP_FADE:
                continue
            for w in sadj[v]:
                if w not in sl and sock[w] and not skin[w]:
                    sl[w] = sl[v] + 1
                    dq.append(w)
        for v, k in sl.items():
            if k > 0:
                lev[v] = -k
        if out["ok"]:  # which lip each ring vertex belongs to: GNM's own lip groups, else the nearer half of the
            # contact ring (by distance alone an inner-roll vertex at a corner went to the other lip: a 3 mm spike)
            cu, cl = V[out["up"]], V[out["lo"]]
            gu, gl = np.asarray(g["groups"]["upper_lip"], float), np.asarray(g["groups"]["lower_lip"], float)
            out["side"] = {v: (gu[v] > gl[v]) if max(gu[v], gl[v]) > 0.3 else
                           (np.linalg.norm(cu - V[v], axis=1).min() <= np.linalg.norm(cl - V[v], axis=1).min())
                           for v in lev}
            for v in out["up"]:
                out["side"][v] = True
            for v in out["lo"]:
                out["side"][v] = False
        self._gnm["rings"] = out
        return out

    def _corners_meet(self, X: np.ndarray, index) -> np.ndarray:
        """(one mesh, own quads) The rings in front of the contact ring drawn together at the mouth's corners (the
        commissure): each ring's upper and lower halves, by CORNER_CLOSE of the way at the corner, fading to nothing
        over LIP_CORNER of the mouth's width and over the rings outward. Left open, every corner was a pocket with
        the rolls showing; taken back with the lips' close in shapes, it tore jawOpen's rolls (so it stays)."""
        R = self._lip_rings()
        D = np.zeros_like(X)
        Tk = np.zeros(len(X))
        if not R["ok"]:
            return D
        from . import base as basemod
        ring = basemod.LIP_RING
        row = {int(v): i for i, v in enumerate(np.asarray(index, int)) if v >= 0}
        # first the rings themselves near the corners: a fitted identity with a narrow mouth bunches the inner rolls
        # there (each ring a zigzag: lumps and tatters at both corners of the neutral, on every export of Garrett);
        # each half ring is smoothed along itself, by how near the corner it is, its ends held
        X0, X = X, X.copy()
        rings_ = dict(R.get("outer") or {})
        rings_[ring] = (R["up"], R["lo"])
        for k, hk in rings_.items():
            if k > ring + 2 or not hk or not all(v in row for v in hk[0] + hk[1]):
                continue
            for verts in hk:
                ids = [row[v] for v in verts]
                P = X[ids].copy()
                if len(P) < 5:
                    continue
                span_ = max(float(P[:, 0].max() - P[:, 0].min()), 1e-9)
                edge_ = np.minimum(P[:, 0] - P[:, 0].min(), P[:, 0].max() - P[:, 0])
                w_ = faceshapes.ROLL_SMOOTH * (1 - _ss(np.clip(edge_ / (faceshapes.TUCK_SPAN * span_), 0, 1)))
                for _ in range(faceshapes.ROLL_PASSES):
                    P[1:-1] += w_[1:-1, None] * (0.5 * (P[:-2] + P[2:]) - P[1:-1])
                X[ids] = P
        for k, hk in (R.get("outer") or {}).items():
            if not hk or not all(v in row for v in hk[0] + hk[1]):
                continue
            u, l = hk
            Pu, Pl = X[[row[v] for v in u]], X[[row[v] for v in l]]

            def arc(P):
                d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
                return d / max(float(d[-1]), 1e-12)
            su, sl = arc(Pu), arc(Pl)
            span = max(float(Pu[:, 0].max() - Pu[:, 0].min()), 1e-9)
            wk = 1.0 if k < ring else 1 - (k - ring - 1) / (faceshapes.LIP_HOLD + 1)  # (the rolls inside the contact ring too)
            for P, s, Q, sq, verts in ((Pu, su, Pl, sl, u), (Pl, sl, Pu, su, l)):
                other = np.column_stack([np.interp(s, sq, Q[:, j]) for j in range(3)])
                edge = np.minimum(P[:, 0] - P[:, 0].min(), P[:, 0].max() - P[:, 0])
                wc = faceshapes.CORNER_CLOSE * wk * (1 - _ss(np.clip(edge / (faceshapes.LIP_CORNER * span), 0, 1)))
                for j, v in enumerate(verts):
                    D[row[v]] += wc[j] * 0.5 * (other[j] - P[j])
                if k <= ring and faceshapes.CORNER_TUCK:   # the rolls (and a share of the contact ring) sink back at the corners:
                    tk = faceshapes.CORNER_TUCK * (ring + 1 - k) / (ring + 1) * (1 - _ss(np.clip(edge / (faceshapes.TUCK_SPAN * span), 0, 1)))
                    for j, v in enumerate(verts):   # bunched there, they stood out through the lips as lumps
                        Tk[row[v]] = max(Tk[row[v]], float(tk[j]))   # (a corner vertex is in both halves: once)
        return (X - X0) + D - Tk[:, None] * self.out

    def _rolls_behind(self, X: np.ndarray, index) -> np.ndarray:
        """(one mesh, own quads) The rings inside the contact ring (the inner rolls, the loop, the sock) pushed back
        behind the closed lips' contact line by ROLL_BEHIND, along `out`. Closing on the contact ring with the rolls
        riding along folded the upper roll FORWARD past the seam where the open-mouthed low poly's rolls stood
        proud of it (Tess: 1 mm at 6-9 mm either side of the midline): a flap of wet inner lip on the closed mouth
        (expr_r8..r12, "notch", "pink sliver", "jagged seam"). Displacements; vertices already behind are kept."""
        R = self._lip_rings()
        D = np.zeros_like(X)
        if not R["ok"] or not faceshapes.ROLL_BEHIND:
            return D
        from . import base as basemod
        ring = basemod.LIP_RING
        idx = np.asarray(index, int)
        row = {int(v): i for i, v in enumerate(idx) if v >= 0}
        cont = [row[v] for v in R["up"] + R["lo"] if v in row]
        if len(cont) < 4:
            return D
        P = X[cont]
        xs = P @ self.side
        o = np.argsort(xs)
        xs, dep = xs[o], ((P - self.M) @ self.out)[o]
        inner = np.array([row[v] for v, lv in R["lev"].items() if lv < ring and v in row], int)
        if not len(inner):
            return D
        xi = X[inner] @ self.side
        lim = np.interp(np.clip(xi, xs[0], xs[-1]), xs, dep) - faceshapes.ROLL_BEHIND
        over = (X[inner] - self.M) @ self.out - lim
        D[inner] = -np.maximum(over, 0.0)[:, None] * self.out[None]
        return D

    def seam_showing(self, X: np.ndarray, T: np.ndarray, index, px: float = 0.0001, tilt: float = 0.0,
                     normals: np.ndarray | None = None) -> float | None:
        """(one mesh, own quads) The area (mm^2) of the mouth's inside seen from the front on a closed mouth: an
        orthographic z-buffer along -out over the lips (px m per pixel), counting pixels whose front-most triangle
        has a vertex inside the contact ring (inner rolls, loop, sock: lev -1). 0 = the lips close on one seam. None if the
        rings aren't found."""
        R = self._lip_rings()
        if not R["ok"]:
            return None
        from . import base as basemod
        ring = basemod.LIP_RING
        idx = np.asarray(index, int)
        lev = np.full(len(X), 99)
        for i, v in enumerate(idx):
            if v >= 0 and int(v) in R["lev"]:
                lev[i] = R["lev"][int(v)]
        cont = lev == ring
        if cont.sum() < 4:
            return None
        # the sock (GNM's mouth-lining vertices that aren't skin) is inside too: the rings' search runs over the skin
        # only, so the sock read 99 (outside) and a crumpled sock through the seal counted nothing (x32: "dark-red
        # shards along the whole lip line" at seam_showing 0.000)
        g = self._setup()["g"]
        sock = (np.asarray(g["groups"]["mouth_sock"]) > 0.5) & ~np.asarray(g["skin"], bool)
        ins = (idx >= 0) & (idx < len(sock))
        lev[ins & sock[np.clip(idx, 0, len(sock) - 1)]] = -1
        Q = X - self.M
        ca, sa = np.cos(tilt), np.sin(tilt)  # the view tilted about `side` (radians, + = from above)
        up, out = ca * self.up - sa * self.out, ca * self.out + sa * self.up
        u, h, d = Q @ self.side, Q @ up, Q @ out
        u0, u1 = float(u[cont].min()), float(u[cont].max())
        h0, h1 = float(h[cont].min()) - 0.004, float(h[cont].max()) + 0.004
        T = np.asarray(T, int)
        tu, th = u[T], h[T]
        sel = (tu.max(1) >= u0) & (tu.min(1) <= u1) & (th.max(1) >= h0) & (th.min(1) <= h1)
        nu, nh = int(np.ceil((u1 - u0) / px)) + 1, int(np.ceil((h1 - h0) / px)) + 1
        zb = np.full((nh, nu), -np.inf)
        inner = np.zeros((nh, nu), bool)
        facing = np.ones((nh, nu))  # the shading normal (as exported) along the view, where a front face is
        bad_t = (lev[T] < ring).any(1)
        for t in np.where(sel)[0]:
            a, b, c = T[t]
            ax, ay, bx, by, cx, cy = u[a], h[a], u[b], h[b], u[c], h[c]
            den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(den) < 1e-14:
                continue
            i0, i1 = max(0, int((min(ax, bx, cx) - u0) / px)), min(nu - 1, int((max(ax, bx, cx) - u0) / px) + 1)
            j0, j1 = max(0, int((min(ay, by, cy) - h0) / px)), min(nh - 1, int((max(ay, by, cy) - h0) / px) + 1)
            if i1 < i0 or j1 < j0:
                continue
            gx, gy = np.meshgrid(u0 + np.arange(i0, i1 + 1) * px, h0 + np.arange(j0, j1 + 1) * px)
            l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
            l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
            l3 = 1 - l1 - l2
            on = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
            z = l1 * d[a] + l2 * d[b] + l3 * d[c]
            sub = zb[j0:j1 + 1, i0:i1 + 1]
            win = on & (z > sub)
            sub[win] = z[win]
            inner[j0:j1 + 1, i0:i1 + 1][win] = bad_t[t]
            if normals is not None:
                nf = (l1[..., None] * normals[a] + l2[..., None] * normals[b] + l3[..., None] * normals[c]) @ out
                facing[j0:j1 + 1, i0:i1 + 1][win] = nf[win]
        self._seam_mask = (inner, zb, u0, h0, px)  # (for diagnostics)
        self._seam_facing = facing
        # a one-pixel line is the seam itself (the contact faces edge-on), not a gap: counted where 3 rows are inside
        core = inner[1:-1] & inner[:-2] & inner[2:]
        return float(core.sum()) * (px * 1000) ** 2

    def _rolls_tucked(self, Xn: np.ndarray, d: np.ndarray, index) -> np.ndarray:
        """(one mesh, own quads) A mouth shape's offsets with each lip's inner roll (rings inside the contact ring)
        kept behind its own lip's edge as seen from the front: an upper-roll vertex no lower than the upper contact
        ring at its x (less ROLL_TUCK_SLACK), a lower one no higher than the lower contact ring. Parted (smile, upper
        up, jawOpen) the upper roll hung below the vermilion as a wet pink band over the teeth, "the inner lip shows,
        not dry lip edges against the teeth" (expr_r11..r13). At rest the rolls already turn up / down behind the
        seam: no change there."""
        R = self._lip_rings()
        if not R["ok"]:
            return d
        from . import base as basemod
        ring = basemod.LIP_RING
        idx = np.asarray(index, int)
        row = {int(v): i for i, v in enumerate(idx) if v >= 0}
        P = Xn + d
        out = np.array(d, float)
        for half, sgn in ((R["up"], 1.0), (R["lo"], -1.0)):
            c = [row[v] for v in half if v in row]
            if len(c) < 4:
                continue
            xs, hs = P[c] @ self.side, (P[c] - self.M) @ self.up
            o = np.argsort(xs)
            xs, hs = xs[o], hs[o]
            rv = np.array([row[v] for v, lv in R["lev"].items() if 0 <= lv < ring and v in row
                           and bool(R["side"].get(v, True)) == (sgn > 0)], int)
            if not len(rv):
                continue
            lim = np.interp(np.clip(P[rv] @ self.side, xs[0], xs[-1]), xs, hs) - sgn * faceshapes.ROLL_TUCK_SLACK
            h = (P[rv] - self.M) @ self.up
            short = np.maximum(sgn * (lim - h), 0.0)  # how far it hangs past its lip's edge
            out[rv] += (sgn * short)[:, None] * self.up[None]
        return out

    def _smile_edge(self, Xn: np.ndarray, d: np.ndarray, index, side: str) -> np.ndarray:
        """(one mesh, own quads) SMILE_EDGE_LIFT: the upper lip's edge (its contact ring and the inner rolls, fading
        over SMILE_EDGE_LIFT[1] rings outward) lifted up the incisors, arched (full at the middle, 0 at the corners),
        this side's half faded across the midline like the prototype (SMILE_SIDE_MM)."""
        A, E, pw = faceshapes.SMILE_EDGE_LIFT
        R = self._lip_rings()
        if not R["ok"]:
            return d
        from . import base as basemod
        ring = basemod.LIP_RING
        row = {int(v): i for i, v in enumerate(np.asarray(index, int)) if v >= 0}
        P = Xn + d
        c = [row[v] for v in R["up"] if v in row]
        if len(c) < 4:
            return d
        xs = P[c] @ self.side
        mid, half = 0.5 * (xs.min() + xs.max()), 0.5 * (xs.max() - xs.min())
        out = np.array(d, float)
        sg = 1.0 if side == "Left" else -1.0
        E = int(E)
        for k in range(0, ring + E + 1):
            hv = R["up"] if k == ring else (R["outer"].get(k) or (None,))[0]
            if not hv:
                continue
            wl = 1.0 if k <= ring else 1.0 - (k - ring) / (E + 1.0)
            rv = np.array([row[v] for v in hv if v in row], int)
            if not len(rv):
                continue
            x = P[rv] @ self.side - mid
            arch = np.clip(1.0 - np.abs(x / half) ** pw, 0.0, 1.0)
            sw = 0.5 * (1 + np.tanh(sg * x / (faceshapes.SMILE_SIDE_MM * 0.001)))
            out[rv] += (A * wl * arch * sw)[:, None] * self.up[None]
        return out

    def _smile_fold(self, X: np.ndarray, nrm: np.ndarray, side: str, corner: bool = True) -> np.ndarray:
        """The nasolabial fold a smile makes (GNM's happy prototype on Tess raised no fold and no cheek: "no nasolabial
        crease, cheeks don't rise", expr_r11..r14): along the line from the nose wing's base past the mouth corner
        (landmarks 35 -> 54 on the head's left, 31 -> 48 right, carried SMILE_FOLD_PAST of the mouth's width beyond
        the corner and down), a crease SMILE_FOLD[0] deep and SMILE_FOLD[1] wide into the skin, and the cheek on
        its outer side pushed out SMILE_FOLD[2] fading over SMILE_FOLD[3]; both fade out toward the line's ends. And
        the mouth's corner lifted SMILE_LIFT[0], fading over SMILE_LIFT[1] ("corners pulled sideways, not up")."""
        lm = np.asarray(self.head["lm68"], float)
        a, c = (lm[35], lm[54]) if side == "Left" else (lm[31], lm[48])
        b = c + (c - a) * faceshapes.SMILE_FOLD_PAST
        depth, width, bulge, reach = faceshapes.SMILE_FOLD
        ab = b - a
        L = float(np.linalg.norm(ab))
        t = np.clip((X - a) @ ab / L ** 2, 0, 1)
        Q = a + t[:, None] * ab
        r = X - Q
        r = r - (r @ self.out)[:, None] * self.out  # across the line, in the face's plane
        dist = np.linalg.norm(r, axis=1)
        sgn_out = np.sign(r @ _unit(np.cross(self.out, ab) if side == "Left" else np.cross(ab, self.out)))
        ends = np.sin(np.pi * t) ** 0.7 * (np.abs((X - Q) @ self.out) < 0.02)
        if faceshapes.SMILE_FOLD_CORNER:  # held off the mouth corner (the lips' seam tears under a deep crease)
            ends = ends * _ss(np.clip(np.linalg.norm(X - c, axis=1) / faceshapes.SMILE_FOLD_CORNER, 0, 1))
        crease = -depth * np.exp(-(dist / width) ** 2)
        cheek = bulge * np.where(sgn_out > 0, np.exp(-(np.maximum(dist - width, 0) / reach) ** 2) *
                                 (1 - np.exp(-(dist / width) ** 2)), 0.0)
        lift = faceshapes.SMILE_LIFT[0] * np.exp(-(np.linalg.norm(X - c, axis=1) / faceshapes.SMILE_LIFT[1]) ** 2) * float(corner)  # the corner up
        push = np.zeros(len(X))
        if faceshapes.CHEEK_LIFT[0] or faceshapes.CHEEK_LIFT[2]:  # the cheek mass up (and out) under the eye, held at the lower lid
            lid = lm[[46, 47] if side == "Left" else [40, 41]].mean(0)
            C = lid + faceshapes.CHEEK_LIFT[3] * (c - lid)
            g = np.exp(-(np.linalg.norm(X - C, axis=1) / faceshapes.CHEEK_LIFT[1]) ** 2)
            below = (lid - X) @ self.up
            g = g * _ss(np.clip(below / max(0.5 * float((lid - C) @ self.up), 1e-4), 0, 1))
            lift = lift + faceshapes.CHEEK_LIFT[0] * g
            push = faceshapes.CHEEK_LIFT[2] * g
        return ((crease + cheek) * ends + push)[:, None] * np.asarray(nrm, float) + lift[:, None] * self.up[None]

    def _meet_share(self, D: np.ndarray, M: np.ndarray, index) -> float:
        """How much of the neutral's lip close a shape takes back: 0 if it keeps the lips together, 1 once it parts
        them by the gap that was closed (the contact ring's halves, along the close's own direction)."""
        R = self._lip_rings()
        if not R["ok"]:
            return 0.0
        row = {int(v): i for i, v in enumerate(np.asarray(index, int)) if v >= 0}
        up = [row[v] for v in R["up"] if v in row]
        lo = [row[v] for v in R["lo"] if v in row]
        closed = float(np.mean(M[up] @ self.up) - np.mean(M[lo] @ self.up))  # how far the close drew them together
        if closed > -1e-5:
            return 0.0
        opened = float(np.mean(D[up] @ self.up) - np.mean(D[lo] @ self.up))
        return float(np.clip(opened / -closed, 0.0, 1.0))

    def _lips_meet(self, X: np.ndarray, index) -> np.ndarray:
        """(one mesh, own quads) What the basis's close leaves between the lips, closed on GNM's own rings: each
        contact-ring vertex moved to halfway between its lip and the other lip at the same arc length (LIP_MEET past
        it: they touch), the rings inside the lips (the rolls, the loop) riding with their contact vertex, the rings
        outside fading over three. The decimated path's Face.seal does this on bins; here the topology is GNM's."""
        R = self._lip_rings()
        D = np.zeros_like(X)
        if not R["ok"]:
            return D
        from . import base as basemod
        idx = np.asarray(index, int)
        row = {int(v): i for i, v in enumerate(idx) if v >= 0}
        up = [v for v in R["up"] if v in row]
        lo = [v for v in R["lo"] if v in row]
        if len(up) < 3 or len(lo) < 3:
            return D

        def arc(P):
            d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(X[[row[v] for v in P]], axis=0), axis=1))]
            return d / max(float(d[-1]), 1e-12)
        su, sl = arc(up), arc(lo)
        Pu, Pl = X[[row[v] for v in up]], X[[row[v] for v in lo]]
        mv = {}
        for P, s, Q, sq, verts, sgn in ((Pu, su, Pl, sl, up, 1.0), (Pl, sl, Pu, su, lo, -1.0)):
            other = np.column_stack([np.interp(s, sq, Q[:, j]) for j in range(3)])
            mid = 0.5 * (P + other)
            gap = other - P
            n = np.linalg.norm(gap, axis=1, keepdims=True)
            push = np.where(n > 1e-9, gap / np.maximum(n, 1e-9), 0.0) * faceshapes.LIP_MEET
            for k, v in enumerate(verts):
                mv[v] = mid[k] + push[k] - P[k]
        ring = basemod.LIP_RING
        # the close as a SMOOTH function of x along each lip (per vertex pairs, it stepped between the columns of
        # the rolls: a sawtooth in every shape that takes it back), tapered to nothing at the corners
        fx = {}
        for half, verts in ((True, up), (False, lo)):
            P = X[[row[v] for v in verts]]
            o = np.argsort(P[:, 0])
            xs = P[o, 0]
            M = np.array([mv[verts[k]] for k in o])
            for _ in range(3):
                M[1:-1] = 0.25 * M[:-2] + 0.5 * M[1:-1] + 0.25 * M[2:]
            span = max(float(xs[-1] - xs[0]), 1e-9)
            fx[half] = (xs, M, span)
        for v, lv in R["lev"].items():
            if v not in row:
                continue
            fw = (1.0 if lv <= ring + faceshapes.LIP_HOLD else max(0.0, 1.0 - (lv - ring - faceshapes.LIP_HOLD) / faceshapes.LIP_FADE)) if lv >= 0 \
                else max(0.0, 1.0 + lv / (faceshapes.LIP_FADE + 1.0))  # (in the sock: fading toward the throat)
            if fw <= 0:
                continue
            xs, M, span = fx[bool(R["side"][v])]
            x = float(X[row[v], 0])
            taper = float(_ss(np.clip((min(x - xs[0], xs[-1] - x)) / (faceshapes.LIP_TAPER * span), 0, 1)))
            D[row[v]] = fw * taper * np.array([np.interp(x, xs, M[:, j]) for j in range(3)])
        return D
