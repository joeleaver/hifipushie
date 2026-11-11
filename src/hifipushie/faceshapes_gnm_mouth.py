"""GnmFace's mouth interior and cheeks (a mixin of GnmFace). Part of face shapes (faceshapes.py has the overview; the class is faceshapes_gnm.GnmFace)."""
from __future__ import annotations

import numpy as np

from . import faceshapes
from .faceshapes import _bump, _ss, vertex_normals

class _GnmMouth:
    """GnmFace's mouth interior and cheeks: clearing and wrapping the teeth, the sock, soft edges, the cheek's
    raise and puff, and carrying offsets onto the export's vertices."""

    def _clear_teeth(self, dV: np.ndarray) -> np.ndarray:
        """GNM offsets with the lips kept in front of the teeth: a prototype made on an average face pulled Tess's
        lips back THROUGH her upper incisors (the smile x2: 33 front points of the upper row ahead of the lips, 3.5 mm;
        "teeth fragments along the lip line", expr_r6). Each skin vertex of the lips and the skin round them that sits
        behind a tooth's front at its height (GNM frame: z forward), within 1.5 mm across, is pushed forward to
        LIP_CLEAR in front of it; the push is spread over the skin's quads so it reads as the lip riding the teeth."""
        from scipy.spatial import cKDTree
        from . import base_gnm_parts
        G = self._setup()
        g = G["g"]
        V = np.asarray(G["c"]["V"], float) + dV
        mp = base_gnm_parts.gnm_mouth(self.head)
        T = np.concatenate([V[np.asarray(mp[k]["ids"])] for k in ("teeth_upper", "teeth_lower")])
        gr = g["groups"]
        lips = np.clip(sum(np.asarray(gr[k], float) for k in ("upper_lip", "lower_lip", "upper_lip_region",
                                                              "lower_lip_region")), 0, 1) > 0.5
        lips &= np.asarray(g["skin"], bool)
        ids = np.flatnonzero(lips)
        tree = cKDTree(T[:, :2])
        r = 0.0015 / float(G["c"].get("s", 1.0))
        push = np.zeros(len(V))
        for k, near in zip(ids, tree.query_ball_point(V[ids, :2], r)):
            if near:
                front = T[near, 2].max()
                if V[k, 2] < front + faceshapes.LIP_CLEAR and V[k, 2] > front - 0.012:  # (behind it, not the far side of the head)
                    push[k] = front + faceshapes.LIP_CLEAR - V[k, 2]
        if not push.any():
            return dV
        Q = g["quads"]
        cnt = np.zeros(len(V))
        for k in range(4):
            np.add.at(cnt, Q[:, k], 1)
        sp = push.copy()
        for _ in range(4):  # spread: each vertex takes the larger of its own push and its quads' mean
            acc = np.zeros(len(V))
            m = sp[Q].mean(1)
            for k in range(4):
                np.add.at(acc, Q[:, k], m)
            sp = np.maximum(push, np.where(cnt > 0, acc / np.maximum(cnt, 1), 0))
        out = np.array(dV, float)
        out[:, 2] += sp * np.asarray(g["skin"], bool)
        return out

    def _mouth_graph(self):
        """GNM's skin + mouth sock as a vertex graph (index pairs both ways), cached."""
        G = self._setup()
        if "mouth_graph" not in G:
            g = G["g"]
            Q = np.asarray(g["quads"])
            keep = np.asarray(g["skin"], bool) | (np.asarray(g["groups"]["mouth_sock"]) > 0.5)
            Q = Q[keep[Q].all(1)]
            e = np.concatenate([Q[:, [k, (k + 1) % 4]] for k in range(4)])
            e = np.unique(np.sort(e, 1), axis=0)
            G["mouth_graph"] = np.concatenate([e, e[:, ::-1]])
        return G["mouth_graph"]

    def _relax(self, F: np.ndarray, fixed: np.ndarray, free: np.ndarray, rounds: int) -> np.ndarray:
        """Jacobi rounds of the graph Laplacian on F (n, k): `free` vertices take their neighbours' mean, the rest
        stay (fixed values, or outside the region: their own)."""
        E = self._mouth_graph()
        n = len(F)
        deg = np.bincount(E[:, 0], minlength=n).astype(float)
        mv = free & ~fixed & (deg > 0)
        F = F.copy()
        for _ in range(rounds):
            acc = np.zeros_like(F)
            np.add.at(acc, E[:, 0], F[E[:, 1]])
            F[mv] = acc[mv] / deg[mv, None]
        return F

    def _wrap_teeth(self, dV: np.ndarray, measure: bool = False):
        """GNM offsets with the lips WRAPPING the teeth: real lips lie on the dental arch and slide over it as the
        mouth opens or smiles; ours stood off it and opened as a hole cut in the face (expr_r7..r12: "teeth small,
        floating", "the lips don't roll over the teeth"). Each vertex of the inner lip (the rolls and the contact
        ring) and the first sock rings, with a tooth or gum at its height within WRAP_ANGLE of its direction from the
        arch's centre, goes onto the arch's outer surface + WRAP_OFFSET: pulled in from up to WRAP_REACH outside, or
        out from up to WRAP_INSIDE inside (_clear_teeth's case). The moves spread smoothly (graph-harmonic) over the
        lips and sock round them, fading to nothing WRAP_SPREAD from the mouth's middle."""
        from scipy.spatial import cKDTree
        from . import base as basemod
        from . import base_gnm_parts
        G = self._setup()
        g = G["g"]
        s_ = float(G["c"].get("s", 1.0))
        V0 = np.asarray(G["c"]["V"], float)
        V = V0 + (0.0 if self._gnm.get("parted") is not None else self._gnm.get("close_dV", 0.0)) + dV  # (r44: the rest parted)
        R = self._lip_rings()
        if not R["ok"]:
            return dV
        ring = basemod.LIP_RING
        mp = base_gnm_parts.gnm_mouth(self.head)
        tid = np.concatenate([np.asarray(mp[k]["ids"]) for k in ("teeth_upper", "teeth_lower")])
        Tt = V[tid]
        up_ids = np.asarray(mp["teeth_upper"]["ids"])
        front = float(V[up_ids, 2].max())
        C = np.array([float(np.median(V[up_ids, 0])), 0.0, front - faceshapes.WRAP_CENTRE / s_])

        def polar(P):
            q = P - C
            return np.arctan2(q[:, 0], q[:, 2]), np.hypot(q[:, 0], q[:, 2])
        ta, tr = polar(Tt)
        wv = np.array([v for v, lv in R["lev"].items() if faceshapes.WRAP_RINGS[0] <= lv <= ring + faceshapes.WRAP_RINGS[1]], int)
        if not len(wv):
            return dV
        va, vr = polar(V[wv])
        tree = cKDTree(np.column_stack([ta * faceshapes.WRAP_CENTRE / s_, Tt[:, 1]]))
        near = tree.query_ball_point(np.column_stack([va * faceshapes.WRAP_CENTRE / s_, V[wv, 1]]), faceshapes.WRAP_ANGLE / s_)
        gaps = np.full(len(wv), np.nan)
        for j, nb in enumerate(near):
            if nb:
                gaps[j] = vr[j] - (float(tr[nb].max()) + faceshapes.WRAP_OFFSET / s_)
        if measure:
            return wv, gaps
        # relative to the rest (the closed mouth as GNM rests it): a vertex keeps the stand-off it has at rest, never
        # more (shapes add: wrapping each to the arch outright would pull the resting lips in once per shape)
        w0, g0 = self._wrap_teeth(np.zeros_like(dV), measure=True) if "wrap_rest" not in G else G["wrap_rest"]
        G["wrap_rest"] = (w0, g0)
        rest = dict(zip(w0.tolist(), g0.tolist()))
        mv = np.zeros((len(V), 3))
        fixed = np.zeros(len(V), bool)
        for j, k in enumerate(wv):
            gap = gaps[j]
            if not np.isfinite(gap) or not (-faceshapes.WRAP_INSIDE / s_ < gap < faceshapes.WRAP_REACH / s_):
                continue
            r0 = rest.get(int(k), np.nan)
            keep = faceshapes.WRAP_KEEP * max(0.0, r0) if np.isfinite(r0) else 0.0
            new = gap if 0.0 <= gap <= keep else (keep if gap > keep else 0.0)
            if new == gap:
                continue
            mv[k, 0] = (new - gap) * np.sin(va[j])
            mv[k, 2] = (new - gap) * np.cos(va[j])
            fixed[k] = True
        if not fixed.any():
            return dV
        skin_or_sock = np.asarray(g["skin"], bool) | (np.asarray(g["groups"]["mouth_sock"]) > 0.5)
        M0 = 0.5 * (G["X0"][62] + G["X0"][66])
        region = skin_or_sock & (np.linalg.norm(V0 - M0, axis=1) < faceshapes.WRAP_SPREAD / s_)
        teeth = np.zeros(len(V), bool)
        teeth[tid] = True
        region &= ~teeth
        return dV + self._relax(mv, fixed, region, faceshapes.WRAP_ROUNDS)

    def _smooth_sock(self, Xn: np.ndarray, d: np.ndarray, index, rest: bool = False) -> np.ndarray:
        """(one mesh, own quads) A shape's offsets with the mouth sock's POSED shape smoothed (Taubin, no shrinking)
        over GNM's quads, the skin held: the export's sock is tucked in behind the lips (retopo._with_mouth_sock
        narrows it 45% within 4 mm of the lips' loop), and opened by a shape that fold folds into crumpled walls
        beside the teeth (clay: faceted folds lit pink with dark voids between, "torn lining", expr_r7..r13). The
        rest pose's own shape is the smoothing's zero: only what the shape adds to the sock's unevenness goes; the
        rest itself is ironed by the neutral (rest=True: the folds were the tuck's, opened by every mouth shape)."""
        G = self._setup()
        g = G["g"]
        idx = np.asarray(index, int)
        sock = (np.asarray(g["groups"]["mouth_sock"]) > 0.5) & ~np.asarray(g["skin"], bool)
        ok = (idx >= 0) & (idx < len(sock))  # (gnmloops' own vertices are numbered past GNM's)
        rows = np.flatnonzero(ok)
        on = np.zeros(len(sock), bool)
        on[idx[rows]] = True
        mv = sock & on
        if not mv.any() or not (rest or np.abs(d[ok][sock[idx[ok]]]).max() > 1e-7):
            return d

        def taubin(P):
            for _ in range(faceshapes.SOCK_SMOOTH):
                P = P + 0.5 * (self._relax(P, ~mv, mv & on, 1) - P)
                P = P - 0.53 * (self._relax(P, ~mv, mv & on, 1) - P)
            return P
        A = np.zeros((len(sock), 3))
        B = np.zeros((len(sock), 3))
        A[idx[rows]] = Xn[rows]
        B[idx[rows]] = Xn[rows] + d[rows]
        dA, dB = (taubin(A) - A if faceshapes.SOCK_SMOOTH_REL and not rest else 0.0), taubin(B) - B  # (the rest's own subtracted)
        out = np.array(d, float)
        sel = rows[sock[idx[rows]]]
        out[sel] += (dB - dA)[idx[sel]]
        return out

    def _soft_edge(self, dV: np.ndarray, rounds: int | None = None) -> np.ndarray:
        """GNM offsets with the regional basis's hard edge melted: GNM's lower-face components stop dead ~60 mm out
        on the cheek (x2 the smile prototype left 3 mm against 0 there: a terraced crease at the cheekbone,
        expr_r6 / r7). Where the move is small next to its largest (under SOFT_EDGE of it) the offsets are
        averaged over the skin's quads `rounds` times, blended in by that ratio."""
        G = self._setup()
        Q = G["g"]["quads"]
        rounds = faceshapes.SOFT_ROUNDS if rounds is None else rounds
        S = np.array(dV, float)
        cnt = np.zeros(len(S))
        for k in range(4):
            np.add.at(cnt, Q[:, k], 1)
        for _ in range(rounds):
            acc = np.zeros_like(S)
            m = S[Q].mean(1)
            for k in range(4):
                np.add.at(acc, Q[:, k], m)
            S = np.where(cnt[:, None] > 0, acc / np.maximum(cnt, 1)[:, None], S)
        mag = np.linalg.norm(dV, axis=1)
        b = 1 - _ss(mag / (faceshapes.SOFT_EDGE * max(float(mag.max()), 1e-9)))
        return dV * (1 - b[:, None]) + S * b[:, None]

    def _cheek_raise(self, s: str) -> np.ndarray:
        """cheekSquint: the cheek under the eye up (GNM's zygomatic and infraorbital regions, feathered)."""
        G = self._setup()
        g, V = G["g"], G["c"]["V"]
        k = "left" if s == "Left" else "right"
        w = np.clip(g["groups"][f"{k}_zygomatic_region"] + 0.7 * g["groups"][f"{k}_infraorbital_region"], 0, 1)
        w = self._feather(w)
        out = np.zeros_like(V)
        out[:, 1] = faceshapes.CHEEK_RAISE[0] * G["wg"] * w  # GNM frame: y up, z forward
        out[:, 2] = faceshapes.CHEEK_RAISE[1] * G["wg"] * w
        return out

    def _feather(self, w: np.ndarray, rounds: int = 8) -> np.ndarray:
        Q = self._setup()["g"]["quads"]
        for _ in range(rounds):
            acc, cnt = np.zeros(len(w)), np.zeros(len(w))
            for k in range(4):
                np.add.at(acc, Q[:, k], w[Q].mean(1))
                np.add.at(cnt, Q[:, k], 1)
            w = acc / np.maximum(cnt, 1)
        return w

    def _cheek_puff(self) -> np.ndarray:
        """The cheeks blown out along their normals (no landmark there for the basis to aim at)."""
        G = self._setup()
        g, V = G["g"], G["c"]["V"]
        Q = g["quads"]
        N = vertex_normals(V, np.r_[Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]])
        w = np.clip(g["groups"]["left_cheek_region"] + g["groups"]["right_cheek_region"]
                    + 0.5 * (g["groups"]["left_parotid_region"] + g["groups"]["right_parotid_region"]), 0, 1)
        w = w * (1 - np.clip(g["groups"]["upper_lip_region"] + g["groups"]["lower_lip_region"], 0, 1))
        # feathered across the quads (the regions have hard edges)
        for _ in range(8):
            acc = np.zeros(len(V))
            cnt = np.zeros(len(V))
            for k in range(4):
                np.add.at(acc, Q[:, k], w[Q].mean(1))
                np.add.at(cnt, Q[:, k], 1)
            w = acc / np.maximum(cnt, 1)
        return N * (0.09 * G["wg"]) * w[:, None]

    def _carried(self, *dVs: np.ndarray) -> list:
        """GNM offsets (its frame, every GNM vertex) -> offsets of the head mesh's vertices (head["verts"]): the eye
        scaling's local magnification, the head's narrowing, the placement (scale, turn), then Catmull-Clark as the
        skin was (linear in the positions: all the offsets go through one subdivision side by side)."""
        from . import base_imls
        c = self._setup()["c"]
        cols = []
        for dV in dVs:
            d = dV * c["esc"][:, None]
            if c.get("fade") is not None:  # (onemesh.py) one human mesh: nothing moves at the neck's stitch
                d = d * np.asarray(c["fade"], float)[:, None]
            d[:, 0] *= c["narrow"]
            dW = c["s"] * d[c["skin"]] @ c["R"].T
            if c["skin_index"] is not None:  # (zipped lips: never with face shapes, they need the lips apart)
                dW = dW[c["skin_index"] >= 0]
            cols.append(dW)
        D, faces = np.concatenate(cols, 1), c["faces"]
        for _ in range(c["subdivide"]):
            D, faces = base_imls._catmull_clark(D, faces)
        return [D[:, 3 * k:3 * k + 3] for k in range(len(dVs))]

    def _carried_scalar(self, f: np.ndarray) -> np.ndarray:
        """A per-GNM-vertex value (a vertex group) on the head mesh's vertices, subdivided like the positions."""
        from . import base_imls
        c = self._setup()["c"]
        v = np.asarray(f, float)[c["skin"]]
        if c["skin_index"] is not None:
            v = v[c["skin_index"] >= 0]
        D, faces = np.repeat(v[:, None], 3, 1), c["faces"]
        for _ in range(c["subdivide"]):
            D, faces = base_imls._catmull_clark(D, faces)
        return D[:, 0]

    def _onto(self, X: np.ndarray, dW: np.ndarray):
        """Head-mesh offsets onto points X: inverse-distance over the 6 nearest head-mesh vertices, and how near the
        head mesh each point is (1 within 2 mm, 0 from 6 mm: the bag, teeth and tongue go by the jaw instead). Between the lips a point takes only its own lip's vertices: the parted lips are ~3 mm
        apart, so the nearest six mixed both lips and the jaw's opening tore the slit's walls into shards."""
        G = self._setup()
        if "sides" not in G:  # which lip each head vertex is: GNM's lip groups (the inner rolls curl past the
            # parting line's height, so height alone put lower-lip vertices in the upper lip), else its height
            from scipy.spatial import cKDTree
            W = np.asarray(self.head["verts"], float)
            gr = G["g"]["groups"]
            up_w, lo_w = self._carried_scalar(gr["upper_lip"]), self._carried_scalar(gr["lower_lip"])
            above = np.where(np.maximum(up_w, lo_w) > 0.3, up_w > lo_w, self.local(W)["h0"] >= 0)
            G["sides"] = [(np.flatnonzero(m), cKDTree(W[m])) for m in (above, ~above)]
        d, i = G["tree"].query(X, k=6)
        L = self.local(X)
        lips = _bump(L["u"], 0.95, 1.3) * _bump(L["back"], self.thick + 0.004, self.thick + 0.012) \
            * _bump(np.abs(L["h0"]), 3 * self.lip, 6 * self.lip)
        out = (dW[i] * self._idw(d)[..., None]).sum(1)
        sel = lips > 0
        if sel.any():
            sided = np.zeros((sel.sum(), 3))
            up = L["h0"][sel] >= 0
            for (idx, tree), m in zip(G["sides"], (up, ~up)):
                if m.any():
                    ds, js = tree.query(X[sel][m], k=6)
                    sided[m] = (dW[idx[js]] * self._idw(ds)[..., None]).sum(1)
            out[sel] = out[sel] * (1 - lips[sel, None]) + sided * lips[sel, None]
        return out, _bump(d[:, 0], 0.002, 0.006)
