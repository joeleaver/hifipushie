"""GnmFace's moves: the jaw, the fitted and the hand-made smile, the lips' lifts (a mixin of GnmFace). Part of face shapes (faceshapes.py has the overview; the class is faceshapes_gnm.GnmFace)."""
from __future__ import annotations

import numpy as np

from .spec import SpecError
from . import faceshapes
from .faceshapes import _rodrigues, _ss, _unit
from .faceshapes import _mirror_ids

class _GnmMoves:
    """GnmFace's moves: each ARKit shape as GNM offsets (the jaw, the fitted smile and jaw, the smile
    prototype, the lips' lifts), and the lower teeth and tongue riding the jaw rigidly."""

    # ---- GNM's frame, the solve, the carry ---------------------------------------------------------------------

    def _jaw_moves(self, ang: float = None, shift=None) -> dict:
        """The jaw's landmarks (jaw line, lower lip; the corners half) turned about the ear line or shifted."""
        G = self._setup()
        X0 = G["X0"]
        Pg = 0.5 * (X0[0] + X0[16])
        out = {}
        for ids, k in ((faceshapes.JAW + faceshapes.LOWER_LIP, 1.0), ([2, 14, 48, 54, 60, 64], 0.5)):
            for i in ids:
                if ang is not None:
                    q = X0[i] - Pg
                    moved = _rodrigues(np.array([1.0, 0.0, 0.0]), np.array([k * ang]), q[None])[0]
                    out[i] = (moved - q) / G["wg"]
                else:
                    out[i] = k * np.asarray(shift, float)
        return out

    def _gnm_moves(self, name: str):
        """(landmark moves, region) for a shape, or (vertex offsets, None) for those the basis has no landmarks for."""
        s = "Left" if name.endswith("Left") else "Right" if name.endswith("Right") else None
        sx = 1.0 if s in (None, "Left") else -1.0
        side = (lambda ids: _mirror_ids(ids, s)) if s else (lambda ids: ids)

        def hold(mv, ids):  # these landmarks stay (moved by 0, at full weight)
            for i in ids:
                mv.setdefault(i, np.zeros(3))

        def put(mv, ids, d, k=1.0):
            for i in side(ids):
                mv[i] = np.asarray(mv.get(i, np.zeros(3)), float) + k * np.asarray([d[0] * sx, d[1], d[2]], float)
        mv = {}
        if name == "jawOpen" and faceshapes.JAW_FIT:
            return self._jaw_fit(), None
        if name == "jawOpen":  # the upper lip held (left at HOLD the solve dragged it 5 mm down with the jaw, over the
            # upper teeth: expr_r4 "upper teeth hidden"), its inner edge a little up off the incisors
            mv = self._jaw_moves(self.open)
            X0 = self._setup()["X0"]
            mid = 0.5 * (X0[48, 0] + X0[54, 0])
            mv.update(self._jaw_upper_lift())
            for i in (48, 54, 60, 64):
                mv[i] = mv[i] + np.array([np.sign(X0[i, 0] - mid) * faceshapes.JAW_CORNER_OUT, 0.0, 0.0])
            for i in (55, 56, 57, 58, 59):
                mv[i] = mv[i] + np.array([0.0, 0.0, -faceshapes.JAW_LOWER_BACK])
            # the basis can't lift the upper lip off the incisors while the jaw drops (landmarks reach -0.5 mm of
            # +6): v16's upper lip edge sat 1.3 mm BELOW the incisal edge, "no upper teeth" (expr_r6). Lifted
            # directly: the vermilion (GNM's upper_lip group) JAW_LIP_LIFT up, feathered into the skin above.
            return self._solve(mv, "mouth", prior=faceshapes.JAW_PRIOR) + self._jaw_lip_lift(), None
        if name == "jawForward":
            return self._jaw_moves(shift=[0, 0, 0.12]), "mouth"
        if name in ("jawLeft", "jawRight"):
            return self._jaw_moves(shift=[0.12 * sx, 0, 0]), "mouth"
        if name == "mouthClose":  # alone: the closed lips firmed forward a little, never into each other (the
            # closing against an open jaw is jawOpen_mouthClose's)
            put(mv, faceshapes.UPPER_LIP + faceshapes.LOWER_LIP, [0, 0, faceshapes.CLOSE_SEAL * 0.05])
            hold(mv, faceshapes.CHIN)
            return mv, "mouth"
        if name == "jawOpen_mouthClose":  # against a full jawOpen: the lower lip back up most of the way, the upper
            # down the rest. Against jawOpen as SOLVED (its prior leaves the lips short of the rigid turn): against
            # the turn itself, the lips closed past each other (A2F's warm f31: 4.2 mm)
            G = self._setup()
            dVj = self._solve(self._jaw_moves(self.open), "mouth", prior=faceshapes.JAW_PRIOR)
            Lj = np.einsum("ln,nd->ld", G["Wlm"], dVj) / G["wg"]
            # the GAP it opened (its lower lip's move less its upper lip's: the solve moves the upper lip a little too)
            pair = dict(zip([59, 58, 57, 56, 55, 67, 66, 65], faceshapes.UPPER_LIP))
            gap = {i: Lj[i] - (Lj[pair[i]] if i in pair else 0.0) for i in range(68)}
            for i in faceshapes.LOWER_LIP:
                mv[i] = -faceshapes.CLOSE_LOWER * gap[i]
            for lo_, up_ in pair.items():
                mv[up_] = (1 - faceshapes.CLOSE_LOWER) * gap[lo_]
            for i in faceshapes.JAW:
                mv[i] = np.zeros(3)
            return self._solve(mv, "mouth") - self._jaw_lip_lift(), None  # (jawOpen's direct lip lift taken back)
        if name == "jawOpen_mouthSmile":  # (r31) jawOpen's direct lip lift taken back under a smile (CORRECTIVES);
            # (r32) and its landmark lift (JAW_UPPER_LIFT) too, x SMILE_JAW_CANCEL_LM: the same solve as jawOpen's with
            # only the upper lip's lifts as targets (the solve is linear: this is exactly their share of jawOpen)
            d = -faceshapes.SMILE_JAW_CANCEL * self._jaw_lip_lift()
            if faceshapes.SMILE_JAW_CANCEL_LM:
                lift = self._jaw_upper_lift()
                mv = {i: np.zeros(3) for i in self._jaw_moves(self.open)}
                mv.update({i: -faceshapes.SMILE_JAW_CANCEL_LM * v for i, v in lift.items()})
                for i in (48, 54, 60, 64, 55, 56, 57, 58, 59):
                    mv.setdefault(i, np.zeros(3))
                d = d + self._solve(mv, "mouth", prior=faceshapes.JAW_PRIOR)
            return d, None
        if name == "mouthFunnel":
            put(mv, [48, 54], [0, 0, 0]), put(mv, [54], [-0.08, 0, 0.06]), put(mv, [48], [0.08, 0, 0.06])
            put(mv, faceshapes.UPPER_LIP[:5], [0, 0.07, 0.1]), put(mv, faceshapes.LOWER_LIP[:5], [0, -0.07, 0.1])
            put(mv, [61, 62, 63], [0, 0.07, 0.06]), put(mv, [65, 66, 67], [0, -0.07, 0.06])
            return mv, "mouth"
        if name == "mouthPucker":  # (the chin held: pucker + rollLower + shrugLower, A2F's usual mix, bulged it 10 mm)
            put(mv, [54], [-0.14, 0, 0.07]), put(mv, [48], [0.14, 0, 0.07])
            put(mv, [53, 55], [-0.07, 0, 0.1]), put(mv, [49, 59], [0.07, 0, 0.1])
            put(mv, [50, 51, 52, 56, 57, 58, 61, 62, 63, 65, 66, 67], [0, 0, 0.1])
            hold(mv, faceshapes.CHIN)
            return mv, "mouth"
        if name in ("mouthLeft", "mouthRight"):
            for i in range(48, 68):
                mv[i] = np.array([0.12 * sx, 0, 0])
            return mv, "mouth"
        if name.startswith("mouthSmile"):
            # GNM's own smile: its expression model's "happy" prototype (lower-face components) on this side, the
            # inner lips closed again (parting is mouthUpperUp / LowerDown's). The landmark solve (corners out / up)
            # read "pinched corners, cheek pouches, no nasolabial fold, eyes unchanged" (expr_r4 / r5); the prototype
            # pulls the corners up AND back into a crescent, the cheeks bunch and the folds form.
            if faceshapes.SMILE_FIT:
                return self._smile_fit(s, "lower"), None
            return self._smile_proto(s, "lower"), None
        if name.startswith("mouthFrown"):
            put(mv, [54], [0.0, -0.09, 0.0]), put(mv, [55, 64], [0, -0.04, 0])
            return mv, "mouth"
        if name.startswith("mouthDimple"):
            put(mv, [54], [0.05, 0.0, -0.06]), put(mv, [64], [0.03, 0, -0.03])
            return mv, "mouth"
        if name.startswith("mouthStretch"):
            put(mv, [54], [0.1, -0.04, -0.02]), put(mv, [55, 56, 65], [0.03, -0.04, 0])
            return mv, "mouth"
        if name == "mouthRollLower":
            # mostly back (tucked under the upper lip), little up: with less back travel, A2F's stacks (pucker +
            # rollLower + the sealed jaw + shrug) pushed the lower lip up INTO the upper one
            put(mv, [56, 57, 58], [0, 0.02, -0.1]), put(mv, [65, 66, 67], [0, 0.01, -0.09])
            hold(mv, faceshapes.CHIN)
            return mv, "mouth"
        if name == "mouthRollUpper":
            put(mv, [50, 51, 52], [0, -0.04, -0.08]), put(mv, [61, 62, 63], [0, -0.02, -0.07])
            return mv, "mouth"
        if name == "mouthShrugLower":  # the lower lip and chin pushed up (mentalis), not out
            put(mv, faceshapes.LOWER_LIP, [0, 0.03, 0.015]), put(mv, [7, 8, 9], [0, 0.02, 0])
            hold(mv, [5, 6, 10, 11])
            return mv, "mouth"
        if name == "mouthShrugUpper":
            put(mv, faceshapes.UPPER_LIP, [0, 0.05, 0.03])
            return mv, "mouth"
        if name.startswith("mouthPress"):
            put(mv, faceshapes.LEFT["upper"] + [51, 62], [0, -0.02, -0.02], 1.0), put(mv, faceshapes.LEFT["lower"] + [57, 66], [0, 0.02, -0.02])
            put(mv, [54], [0.03, 0, -0.01])
            return mv, "mouth"
        # (not forward off the teeth: forward, the parted lips showed their pink inner rolls where the reference shows
        # teeth, expr_r7; back, the teeth cut through the seam, expr_r8. The centre as far as the side: at 0.045 the
        # smile's closed inner lips held, "no teeth" in a smile with upperUp 0.5, expr_r8)
        if name.startswith("mouthLowerDown"):
            put(mv, [55, 56, 65], [0, -0.11, 0.0]), put(mv, [57, 66], [0, -0.09, 0.0])
            return mv, "mouth"
        if name.startswith("mouthUpperUp"):
            put(mv, [52, 53, 63], [0, 0.11, 0.0]), put(mv, [51, 62], [0, 0.09, 0.0])
            return mv, "mouth"
        if name.startswith("eyeBlink"):
            X0 = self._setup()["X0"]
            for up_i, lo_i in faceshapes.LEFT["lid_upper"]:
                u, lo = side([up_i])[0], side([lo_i])[0]
                gap = (X0[lo] - X0[u]) / self._setup()["wg"]
                # down (and a little forward: over the ball), meeting the lower lid a little past it (at 0.8/0.2
                # the inner corner stayed open a crack); the eyeball push keeps the lids out of the ball
                mv[u] = 0.9 * gap * np.array([0, 1.0, 0.3])
                mv[lo] = -0.25 * gap * np.array([0, 1.0, 0.3])
            return mv, "eyes"
        if name.startswith("eyeWide") or name.startswith("eyeSquint"):
            X0 = self._setup()["X0"]
            ku, kl = (-0.35, -0.15) if name.startswith("eyeWide") else (0.1, faceshapes.SQUINT_LOWER)
            for up_i, lo_i in faceshapes.LEFT["lid_upper"]:
                u, lo = side([up_i])[0], side([lo_i])[0]
                gap = (X0[lo] - X0[u]) / self._setup()["wg"]
                mv[u] = ku * gap * np.array([0, 1.0, 0.0])
                mv[lo] = -kl * gap * np.array([0, 1.0, 0.0])
            return mv, "eyes"
        if name.startswith("cheekSquint"):  # the cheek up, plus the smile prototype's own eye share on this side
            if faceshapes.SMILE_FIT:
                return self._smile_fit(s, "eyes"), None
            return self._cheek_raise(s) + self._smile_proto(s, "eyes"), None
        if name.startswith("noseSneer"):  # the nostril's wing and the skin beside it up
            put(mv, [35], [0.0, 0.07, 0.0]), put(mv, [34], [0.0, 0.04, 0.0])
            put(mv, [33], [0, 0.015, 0])
            return mv, "mouth"
        if name == "browInnerUp":
            for ss in ("Left", "Right"):
                for i in _mirror_ids([22, 23], ss):
                    mv[i] = np.array([0, 0.1, 0])
                for i in _mirror_ids([24], ss):
                    mv[i] = np.array([0, 0.04, 0])
            return mv, "eyes"
        if name.startswith("browDown"):
            put(mv, [22, 23, 24, 25, 26], [-0.02, -0.08, 0.01])
            return mv, "eyes"
        if name.startswith("browOuterUp"):
            put(mv, [25, 26], [0, 0.1, 0]), put(mv, [24], [0, 0.05, 0])
            return mv, "eyes"
        if name == "cheekPuff":
            return self._cheek_puff(), None
        if name == "tongueOut":
            jo = self._jaw_moves(0.35 * self.open)
            return jo, "mouth"
        raise SpecError(f"face_shapes: unknown shape {name!r}")

    def _smile_fit(self, s: str, part: str) -> np.ndarray:
        """GNM offsets (its frame, every vertex) of the FITTED smile (SMILE_FIT) on side s: "lower" = its lower-face
        components faded across the midline (SMILE_SIDE_MM), teeth cleared; "eyes" = its components of that side's eye."""
        G = self._setup()
        key = ("smile_fit", s, part, faceshapes.SMILE_FIT, faceshapes.SMILE_FIT_SOFT, faceshapes.SMILE_FIT_EYE_GAIN, faceshapes.SMILE_LOWLID_GAIN)
        if key in G:
            return G[key]
        EB = G["g"]["expression_basis"]
        e = np.asarray(np.load(faceshapes.SMILE_FIT), float)
        reg = G["regions"]
        if part == "eyes":
            ids = [i for i in reg["left_eye" if s == "Left" else "right_eye"] if i < len(e)]
            dE = faceshapes.SMILE_FIT_EYE_GAIN * self._soft_edge(np.tensordot(e[ids], EB[ids], 1), faceshapes.SMILE_FIT_SOFT)
            if faceshapes.SMILE_LOWLID_GAIN != 1.0:  # (r43) the lower lid's travel x gain (the fit lifts ~60% of the photo's)
                w = self._lower_lid_weight(dE)
                dE = dE * (1.0 + (faceshapes.SMILE_LOWLID_GAIN - 1.0) * w)[:, None]
            G[key] = dE
            return G[key]
        ids = [i for i in reg["lower_face"] if i < len(e)]
        dS = self._clear_teeth(self._soft_edge(np.tensordot(e[ids], EB[ids], 1), faceshapes.SMILE_FIT_SOFT))
        X0 = G["X0"]
        mid = float(np.mean(X0[[27, 28, 29, 30, 33, 51, 57, 62, 66], 0]))
        x = np.asarray(G["c"]["V"], float)[:, 0] - mid
        w = 0.5 * (1 + np.tanh(x / (faceshapes.SMILE_SIDE_MM * 0.001 / float(G["c"].get("s", 1.0)))))
        G[key] = dS * (w if s == "Left" else 1 - w)[:, None]
        return G[key]

    def _lower_lid_weight(self, dE: np.ndarray) -> np.ndarray:
        """(r43) 0..1 per GNM vertex: the lower lid of the eye that dE moves, from 1 mm above its margin (lm68's corners and
        two lower points, piecewise linear) to 3 mm below at 1, fading to 0 at 2 mm above / 7 mm below (as shares of a 30 mm
        chord), and along the chord as sin(pi t): the centre gains most, the corners not at all (less cupped)."""
        G = self._setup()
        V = np.asarray(G["c"]["V"], float)[:len(dE)]
        X = G["Wlm"][:, :len(V)] @ V if G["Wlm"].shape[1] != len(V) else G["Wlm"] @ V
        mag = np.linalg.norm(dE, axis=1)
        cen = (V * mag[:, None]).sum(0) / max(mag.sum(), 1e-12)
        eyes = ([36, 41, 40, 39], [45, 46, 47, 42])  # corner, lower, lower, corner (iBUG)
        lo = min(eyes, key=lambda q: abs(X[q, 0].mean() - cen[0]))
        P = X[lo]
        if P[0, 0] > P[-1, 0]:
            P = P[::-1]
        ch = float(np.linalg.norm(P[-1, [0, 1]] - P[0, [0, 1]]))
        t = (V[:, 0] - P[0, 0]) / max(P[-1, 0] - P[0, 0], 1e-12)
        my = np.interp(V[:, 0], P[:, 0], P[:, 1])
        below = (my - V[:, 1]) / ch * 30.0  # mm (on a 30 mm chord) under the margin; < 0 above it
        def ss(a, b, x):
            return _ss(np.clip((x - a) / (b - a), 0.0, 1.0))
        wb = ss(-2.0, -1.0, below) * (1.0 - ss(3.0, 7.0, below))
        wu = np.where((t > 0) & (t < 1), np.sin(np.pi * np.clip(t, 0, 1)), 0.0)
        near = np.abs(V[:, 2] - P[:, 2].mean()) < 0.5 * ch  # (GNM frame: z forward) the lid, not the skull behind
        return wb * wu * near * (mag > 0)

    def _jaw_fit(self) -> np.ndarray:
        """GNM offsets (its frame, every vertex) of the FITTED jaw opening (JAW_FIT): its lower-face components, teeth cleared."""
        G = self._setup()
        key = ("jaw_fit", faceshapes.JAW_FIT, faceshapes.JAW_FIT_GAIN, faceshapes.JAW_ROLL_TUCK, faceshapes.JAW_TUCK_FADE, faceshapes.JAW_WIDEN)
        if key not in G:
            e = faceshapes.JAW_FIT_GAIN * np.asarray(np.load(faceshapes.JAW_FIT), float)
            ids = [i for i in G["regions"]["lower_face"] if i < len(e)]
            d = np.tensordot(e[ids], G["g"]["expression_basis"][ids], 1)
            if faceshapes.JAW_ROLL_TUCK:
                gr = {k: np.asarray(v) > 0.5 for k, v in G["g"]["groups"].items()}
                V = np.asarray(G["c"]["V"], float)
                n = min(len(V), len(d), len(gr["skin_exterior"]))
                # the rolls: GNM's skin rings from the sock to the contact ring (skin_features_mouth.inner_lip_values = 1, the
                # same rings the export paints as wet lip), the sock itself left where the fit put it
                from . import skin_features_mouth
                iv = skin_features_mouth.inner_lip_values(self.head)
                roll = np.zeros(len(d), bool)
                if iv is not None:
                    m_ = min(len(iv), n)
                    roll[:m_] = (np.asarray(iv, float)[:m_] > 0.99) & ~gr["mouth_sock"][:m_]
                print(f"faceshapes: jawOpen tucks {int(roll.sum())} inner-roll vertices back (JAW_ROLL_TUCK {faceshapes.JAW_ROLL_TUCK})", flush=True)
                ext = np.zeros(len(d), bool)
                ext[:n] = ((gr["upper_lip"] | gr["lower_lip"]) & gr["skin_exterior"])[:n]
                f = V[ext[:len(V)]].mean(0) - V[np.flatnonzero(gr["mouth_sock"][:n])].mean(0)
                f[1] = 0.0  # (GNM frame: y up) the lips' outward direction, level
                f /= np.linalg.norm(f)
                s = np.clip(np.abs(d[roll, 1]) / (0.2 * G["wg"]), 0.0, 1.0)
                a = np.zeros(len(d))
                a[roll] = s if not faceshapes.JAW_TUCK_FADE else 1.0  # (r43) per-vertex travel left one roll vertex (GNM 10766, travel
                # under the 20%-width cap while its neighbours sat at it) 1.4 mm less tucked than the ring round it
                if faceshapes.JAW_TUCK_FADE:  # (r43) the tuck smoothed in space (Gaussian, JAW_TUCK_FADE x 0.5 mm): on the rolls alone
                    # one lower-lip vertex (GNM 10766, outside GNM's quads graph, so a quad feather can't reach it) went
                    # 1.75 mm past its neighbours (jawOpen uneven 0.53 > UNEVEN_LIMIT, test_onemesh); the rolls' mean kept
                    from scipy.spatial import cKDTree
                    sig = faceshapes.JAW_TUCK_FADE * 0.0005 / float(G["c"].get("s", 1.0))
                    P = np.zeros((len(d), 3))
                    P[:n] = V[:n]
                    near = np.flatnonzero(cKDTree(P[roll]).query(P, distance_upper_bound=4 * sig)[0] < np.inf)
                    tr = cKDTree(P[near])
                    K = []
                    for i, nb in zip(near, tr.query_ball_point(P[near], 3 * sig)):
                        nb = near[nb]
                        w_ = np.exp(-((P[nb] - P[i]) ** 2).sum(1) / (2 * sig * sig))
                        K.append((i, nb, w_ / w_.sum()))

                    def smooth(a):
                        af = np.zeros(len(d))
                        for i, nb, w_ in K:
                            af[i] = (w_ * a[nb]).sum()
                        return af
                    af = smooth(a)
                    a = af * (a[roll].mean() / max(af[roll].mean(), 1e-12))
                    amt = faceshapes.JAW_ROLL_TUCK * G["wg"]
                    for _ in range(8):  # where the teeth stop the tuck (_clear_teeth pushes those vertices back out, one
                        # by one: GNM 10766 sat 1.8 mm proud of its ring), the tuck gives way, smoothly
                        dt = d - (amt * a)[:, None] * f[None]
                        push = np.clip(((self._clear_teeth(dt) - dt) @ f), 0.0, None)
                        a = smooth(np.clip(a - push / amt, 0.0, None))
                d -= (faceshapes.JAW_ROLL_TUCK * G["wg"] * a)[:, None] * f[None]
            if faceshapes.JAW_WIDEN:  # (r43) the opening wider: the lips, their rings and the sock stretched out from the mouth's middle
                # (in the shape, so x its weight; review r42: "about 10% narrower and shorter")
                gr = {k: np.asarray(v) > 0.5 for k, v in G["g"]["groups"].items()}
                V = np.asarray(G["c"]["V"], float)
                n = min(len(V), len(d))
                lw = np.zeros(len(d))
                lw[:n] = (gr["upper_lip"] | gr["lower_lip"] | gr["mouth_sock"])[:n]
                lw = np.clip(self._feather(lw, 6) * 1.5, 0.0, 1.0)
                X0 = G["X0"]
                mid = float(np.mean(X0[[51, 57, 62, 66], 0]))
                d[:n, 0] += faceshapes.JAW_WIDEN * (V[:n, 0] - mid) * lw[:n]
            G[key] = self._clear_teeth(d)
        return G[key]

    def _smile_proto(self, s: str, part: str) -> np.ndarray:
        """GNM offsets (its frame, every vertex) of SMILE_PROTO on side s ("Left" = +x): part "lower" = the prototype's
        lower-face components, faded across the midline (SMILE_SIDE_MM), plus a solve that closes the inner lips it
        parts; "eyes" = its components of that side's eye region."""
        G = self._setup()
        key = ("smile_proto", s, part, faceshapes.SMILE_UPPER_LIFT, faceshapes.SMILE_CORNER_UP, faceshapes.SMILE_UPPER_HOLD, faceshapes.SMILE_LOWER_HOLD)
        if key in G:
            return G[key]
        from . import gnm_sampler
        g = G["g"]
        EB = g["expression_basis"]
        e = faceshapes.SMILE_PROTO[1] * np.asarray(gnm_sampler.expression()(np.zeros(64), gnm_sampler.ex_label(faceshapes.SMILE_PROTO[0]))[0], float)
        reg = G["regions"]
        if part == "eyes":
            ids = [i for i in reg["left_eye" if s == "Left" else "right_eye"] if i < len(e)]
            out = self._soft_edge(np.tensordot(e[ids], EB[ids], 1))
            G[key] = out
            return out
        ids = [i for i in reg["lower_face"] if i < len(e)]
        dS = np.tensordot(e[ids], EB[ids], 1)
        L = G["Wlm"] @ dS / G["wg"]
        mv = {}
        if faceshapes.SMILE_CORNER_UP != 1.0:  # the corners' rise scaled (Tess: corners 5-8% io above the reference smile)
            for c in (48, 54):
                mv[c] = np.array([0.0, -(1.0 - faceshapes.SMILE_CORNER_UP) * float(L[c][1]), 0.0])
        for hold, ids_ in ((faceshapes.SMILE_UPPER_HOLD, {50: 1.0, 51: 1.0, 52: 1.0, 49: 0.5, 53: 0.5}),
                           (faceshapes.SMILE_LOWER_HOLD, {56: 1.0, 57: 1.0, 58: 1.0, 55: 0.5, 59: 0.5})):
            if hold:  # (r35) the outer lip edges' vertical travel taken back (the inner edges still part over the teeth)
                for c, f in ids_.items():
                    mv[c] = np.array([0.0, -hold * f * float(L[c][1]), 0.0])
        for u, lo in ((61, 67), (62, 66), (63, 65)):  # the inner lips back together (half each)
            gap = float((L[u] - L[lo])[1])
            mv[u], mv[lo] = np.array([0.0, -0.5 * gap, 0.0]), np.array([0.0, 0.5 * gap, 0.0])
        for _ in range(3):  # (the solve reaches ~80% a round: 17 -> 3.3 mm in one; the rest let the lower tips through)
            dC = self._solve(mv, "mouth")
            L2 = G["Wlm"] @ (dS + dC) / G["wg"]
            left = 0.0
            for u, lo in ((61, 67), (62, 66), (63, 65)):
                gap = float((L2[u] - L2[lo])[1])
                left = max(left, abs(gap))
                mv[u] = mv[u] + np.array([0.0, -0.5 * gap, 0.0])
                mv[lo] = mv[lo] + np.array([0.0, 0.5 * gap, 0.0])
            if left * G["wg"] < 3e-4:
                break
        dS = dS + self._solve(mv, "mouth")
        if faceshapes.SMILE_UPPER_LIFT[0]:  # the upper lip's middle up off the incisors: the opening's top an arch (a crescent)
            lift = self._jaw_lip_lift(faceshapes.SMILE_UPPER_LIFT[0], faceshapes.SMILE_UPPER_LIFT[1], faceshapes.SMILE_UPPER_LIFT[2])
            dS = dS + lift
            if faceshapes.SMILE_UPPER_HOLD:  # (r35) the lift's own rise of the outer edge taken back too, the inner edge (61-63) kept
                Ll = G["Wlm"] @ lift / G["wg"]
                mv2 = {c: np.array([0.0, -faceshapes.SMILE_UPPER_HOLD * f * float(Ll[c][1]), 0.0])
                       for c, f in {50: 1.0, 51: 1.0, 52: 1.0, 49: 0.5, 53: 0.5}.items()}
                mv2.update({c: np.zeros(3) for c in (61, 62, 63)})
                dS = dS + self._solve(mv2, "mouth")
        dS = self._clear_teeth(self._soft_edge(dS))
        X0 = G["X0"]
        mid = float(np.mean(X0[[27, 28, 29, 30, 33, 51, 57, 62, 66], 0]))
        x = np.asarray(G["c"]["V"], float)[:, 0] - mid
        w = 0.5 * (1 + np.tanh(x / (faceshapes.SMILE_SIDE_MM * 0.001 / float(G["c"].get("s", 1.0)))))
        w = w if s == "Left" else 1 - w
        out = dS * w[:, None]
        G[key] = out
        return out

    def _jaw_upper_lift(self) -> dict:
        """jawOpen's landmark targets for the upper lip ({id: move}, mouth widths): its inner edge up off the incisors,
        tapered toward the corners (JAW_UPPER_LIFT, JAW_ARCH)"""
        X0 = self._setup()["X0"]
        mid, half = 0.5 * (X0[48, 0] + X0[54, 0]), 0.5 * abs(X0[54, 0] - X0[48, 0])

        def arch(i):
            return max(1.0 - faceshapes.JAW_ARCH * abs((X0[i, 0] - mid) / half) ** faceshapes.JAW_ARCH_POW, 0.0)
        mv = {i: np.array([0.0, faceshapes.JAW_UPPER_LIFT[1] * arch(i), 0.0]) for i in faceshapes.UPPER_LIP[:5]}
        mv.update({i: np.array([0.0, faceshapes.JAW_UPPER_LIFT[0] * arch(i), 0.0]) for i in faceshapes.UPPER_LIP[5:]})
        return mv

    def _jaw_lip_lift(self, amount: float | None = None, arch: float | None = None, power: float | None = None) -> np.ndarray:
        """jawOpen's direct lift of the upper lip (GNM offsets): the vermilion (GNM's upper_lip group) JAW_LIP_LIFT up,
        feathered into the skin above (0.4 of upper_lip_region). amount / arch / power override JAW_LIP_LIFT /
        JAW_ARCH / JAW_ARCH_POW (the smile's SMILE_UPPER_LIFT uses it with its own arch)."""
        G = self._setup()
        JAW_LIP_LIFT = faceshapes.JAW_LIP_LIFT if amount is None else amount
        JAW_ARCH = faceshapes.JAW_ARCH if arch is None else arch
        JAW_ARCH_POW = faceshapes.JAW_ARCH_POW if power is None else power
        key = ("jaw_lip_lift", JAW_LIP_LIFT, JAW_ARCH, JAW_ARCH_POW)
        if key not in G:
            gr = G["g"]["groups"]
            w = self._feather(np.clip(np.asarray(gr["upper_lip"], float) + 0.4 * np.asarray(gr["upper_lip_region"], float), 0, 1), 3)
            w = w / max(float(w.max()), 1e-9)
            if JAW_ARCH:  # tapered toward the corners (the opening's top an arch, not a flat bar)
                V0, X0 = np.asarray(G["c"]["V"], float), G["X0"]
                mid, half = 0.5 * (X0[48, 0] + X0[54, 0]), 0.5 * abs(X0[54, 0] - X0[48, 0])
                w = w * np.clip(1.0 - JAW_ARCH * np.abs((V0[:, 0] - mid) / half) ** JAW_ARCH_POW, 0.0, 1.0)
            lift = np.zeros_like(np.asarray(G["c"]["V"], float))
            lift[:, 1] = JAW_LIP_LIFT / float(G["c"].get("s", 1.0)) * w
            G[key] = lift
        return G[key]

    def _rigid_lower_row(self, dV: np.ndarray):
        """The jaw as GNM's lower tooth row moves under offsets dV: a turn about the ear line (landmarks 0 / 16, the
        line jawOpen turns about) by the angle that best fits the row, then the row's mean remaining shift (world):
        (rotation, origin, t), applied as (X - origin) @ R.T + t. (A free Procrustes on the row, a short arc that
        GNM also bends 2.6 mm, swung the tongue's root UP 4.5 mm.)"""
        from . import base_gnm_parts
        mp = base_gnm_parts.gnm_mouth(self.head)
        ids = np.asarray(mp["teeth_lower"]["ids"])
        P0 = np.asarray(mp["teeth_lower"]["verts"], float)
        D = self._by_index(dV)[ids]
        lm = np.asarray(self.head["lm68"], float)
        o = 0.5 * (lm[0] + lm[16])
        ax = _unit(lm[16] - lm[0])
        best = None
        for ang in np.radians(np.linspace(-40, 40, 321)):
            Rr = _rodrigues(ax, np.array([ang]), np.eye(3))
            Q = (P0 - o) @ Rr.T + o
            t = (P0 + D - Q).mean(0)
            err = float(((Q + t - P0 - D) ** 2).sum())
            if best is None or err < best[0]:
                best = (err, Rr, t)
        _, Rr, t = best
        return Rr, o, o + t

    def _rigid_jaw(self, dW: np.ndarray):
        """The jaw's rigid motion in a shape (Procrustes on the jaw line's landmarks, world): (rotation, origin, t)."""
        lm = self.head["lm68"]
        ids = [4, 5, 6, 7, 8, 9, 10, 11, 12]
        P0 = lm[ids]
        D, _ = self._onto(P0, dW)
        P1 = P0 + D
        a, b = P0.mean(0), P1.mean(0)
        U, _, Vt = np.linalg.svd((P0 - a).T @ (P1 - b))
        Rr = (U @ Vt).T
        if np.linalg.det(Rr) < 0:
            Vt[-1] *= -1
            Rr = (U @ Vt).T
        return Rr, a, b
