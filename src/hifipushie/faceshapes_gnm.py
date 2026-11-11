"""class GnmFace: a GNM head's shapes from GNM's own expression basis. Part of face shapes (faceshapes.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import spec as specmod
from .spec import SpecError
from . import faceshapes
from .faceshapes import _ss, _unit, family
from .faceshapes import lid_seal_options
from .faceshapes_face import Face
from .faceshapes_gnm_solve import _GnmSolve
from .faceshapes_gnm_moves import _GnmMoves
from .faceshapes_gnm_mouth import _GnmMouth
from .faceshapes_gnm_lids import _GnmLids
from .faceshapes_gnm_lips import _GnmLips

class GnmFace(_GnmSolve, _GnmMoves, _GnmMouth, _GnmLids, _GnmLips, Face):
    """A GNM head (base.py): its mouth from the landmarks (base_gnm_parts.mouth_lips); its interior GNM's OWN (base_gnm_parts.mouth_mode
    "gnm", the default: mouth bag, teeth and tongue, each moved by its own share of a shape's expression coefficients)
    or the face kit's (base.head.interior: kits._interior, moved rigidly with the jaw); its shapes from GNM's
    expression basis carried onto the export."""

    def __init__(self, spec: dict):
        from . import base_gnm_parts, base_measures
        b = spec["base"]
        hd = b["head"]
        e = specmod.expand_mirror(spec)
        head = base_measures.head_of({"joints": e["joints"]}, b)
        mode = base_gnm_parts.mouth_mode(b, head)
        self.gnm_mouth = mode == "gnm"
        self.note = base_gnm_parts.mouth_note(b, head)
        if mode == "none":
            raise SpecError("face_shapes on a GNM head needs a mouth that can open: GNM's own (the default; "
                            + (self.note or "base.head.mouth is \"none\" here")
                            + ") or the face kit's (base.head.interior: true, or {\"teeth\": true, \"tongue\": true}), and, "
                            "unless the body is the one mesh on its own quads, base.head.mouth_gap >= 0.002 (the lips "
                            "parted while modelling; the export closes them)")
        one = (b.get("body") or {}).get("source") == "human"  # (one mesh: GNM's own lips, never zipped unasked)
        self.own_quads = one and ((spec.get("parts") or {}).get("body") or {}).get("topology") == "wrap"
        if (float(hd.get("mouth_gap") or 0) < 0.0015) and not (one and hd.get("mouth_gap") is None):
            raise SpecError("face_shapes on a GNM head: base.head.mouth_gap must part the lips (>= 0.002 m): closed "
                            "lips are zipped into one seam and can't open")
        opts = spec.get("face_shapes") or {}
        self.amount = {str(a): float(v) for a, v in (opts.get("amount") or {}).items()}
        self.skin_parts = {str(p) for p in (opts.get("parts") or [])}
        bad = [a for a in self.amount if a not in faceshapes.ALL]
        if bad:
            raise SpecError(f"face_shapes.amount: unknown shape(s) {bad} (have the ARKit names {', '.join(faceshapes.ALL)})")
        prims = {p.name: p for p in specmod.compile_prims(spec)}
        self.head = head
        m = base_gnm_parts.mouth_lips(head)
        lm = head["lm68"]
        self.M, self.out, self.up, self.side = m["M"], m["out"], m["up"], m["side"]
        self.width = m["width"]
        self.W2 = self.width / 2
        self.ru, self.rl = m["ru"], m["rl"]
        self.lip = max(self.ru, self.rl)
        pts = m["pts"] - self.M
        self.su, self.sz, self.sf = m["knots"], pts @ self.up, pts @ self.out
        self.corners = {"Left": lm[54], "Right": lm[48]}
        self.R = 0.5 * float(np.linalg.norm(lm[16] - lm[0]))
        if self.gnm_mouth:
            self._gnm_mouth_parts(m, b)
        else:
            self._mouth_parts(prims, "face")
        self.nose = []
        self.nose_bone = []
        self.eyes = {s: {"c": np.asarray(c, float), "r": float(head["eye_r"]), "ro": 1.3 * float(head["eye_r"]),
                         "part": b.get("eyes")} for s, c in zip(("Left", "Right"), head["eyes"])}
        eg = head.get("eye_gnm")
        if eg and b.get("cornea") is not False:  # GNM's own eyeball: its corneal sphere stands proud of the ball, and
            # a lid must clear it too (displacements): centre on the gaze line, as base_implied.inject places the bulge
            for s, sfx in (("Left", ".L"), ("Right", ".R")):
                if f"eye_front{sfx}" in e["joints"]:
                    c = self.eyes[s]["c"]
                    gz = _unit(np.asarray(e["joints"][f"eye_front{sfx}"]["pos"], float) - c)
                    self.eyes[s]["cornea"] = (c + (float(eg["apex"]) - float(eg["cornea_r"])) * gz, float(eg["cornea_r"]))
        self.brows, self.cheeks = {}, {}
        jaw = opts.get("jaw") or {}
        self.P = (np.asarray(specmod.resolve_point(e, jaw["pivot"]), float) if "pivot" in jaw
                  else 0.5 * (lm[0] + lm[16]))
        self.open = np.radians(float(jaw.get("open", faceshapes.GNM_OPEN)))
        self.depth = float(jaw.get("depth", 0.75 * self.R))
        self.lid_seal = lid_seal_options(opts.get("lid_seal"))
        self._gnm = {}

    def _gnm_mouth_parts(self, m: dict, b: dict):
        """GNM's own mouth (base_gnm_parts.gnm_mouth): the numbers the kit's slit and bag gave (the lips' depth, the bag's
        half sizes in the mouth's frame, how fine the teeth are meshed), and the pieces' own vertices."""
        from . import base_gnm_parts, base_identity
        from . import base
        mp = base_gnm_parts.gnm_mouth(self.head)
        self.slit = max(float(m["gap"]), 0.001)
        self.slit_part = b.get("part", "body")
        self.slit_u = np.array([0.0, 0.92])
        self.slit_h = np.array([0.5 * self.slit, 0.25 * 0.5 * self.slit])
        self.thick = 2.2 * self.lip
        g = base_identity._gnm_data()
        own = np.asarray(g["groups"]["mouth_sock"])[mp["sock"]["ids"]] > 0.5
        P = (mp["sock"]["verts"][own] - self.M) @ np.stack([self.side, self.out, self.up], 1)
        self.bag = 0.5 * (P.max(0) - P.min(0))
        self.parts_teeth, self.parts_tongue = set(base.TEETH_PARTS), {"tongue"}
        self.teeth_t = 3 * float(base.MOUTH_PARTS["teeth"]["voxel"])
        self.tongue = None

    def neutral(self, Xm: np.ndarray, kind: str, index=None) -> np.ndarray:
        """The lips closed: the inner lips' landmarks moved half the gap each, solved in the basis and carried."""
        if kind != "skin" and not (self.gnm_mouth and kind in ("teeth", "tongue")):
            return np.zeros_like(Xm)
        if "close" not in self._gnm:
            G = self._setup()
            X0 = G["X0"]
            mv = {}
            for u, l in ((61, 67), (62, 66), (63, 65)):
                gap = (X0[l] - X0[u]) / G["wg"]
                mv[u], mv[l] = 0.5 * gap, -0.5 * gap
            dV = self._solve(mv, "mouth", hold=0.2)
            dW, = self._carried(dV)
            # the basis gets most of the way (holding the outer lips); scaled so the inner lips' midpoints meet
            lm = self.head["lm68"]
            D, _ = self._onto(lm[[62, 66]], dW)
            want = float((lm[66] - lm[62]) @ self.up)
            got = float((D[0] - D[1]) @ self.up)
            k = float(np.clip(-want / got, 1.0, 2.0) if got * want < 0 else 1.0)
            self._gnm["close"] = dW * k
            self._gnm["close_dV"] = dV * k
        if kind != "skin":  # GNM's own teeth / tongue: their own share of the same closing expression
            return self._piece_onto(Xm, self._gnm["close_dV"], kind)
        D, a = self._onto(Xm, self._gnm["close"])
        D = D * a[:, None]
        if index is not None:  # (one mesh, own quads) GNM's own vertices take GNM's own offsets
            D = self._indexed(D, index, self._gnm["close_dV"])
            if faceshapes.LIPS_MEET:  # what the basis leaves between the lips closed on GNM's own contact ring
                M = self._lips_meet(Xm + D, index)
                self._gnm["meet"] = (Xm.shape, M)  # (a shape that parts the lips takes it back: displacements)
                D = D + self._corners_meet(Xm + D + M, index)  # (kept by every shape: the commissure stays sealed)
                B = self._rolls_behind(Xm + D + M, index)  # the rolls behind the closed seam (taken back with M)
                self._gnm["meet"] = (Xm.shape, M + B)
                D = D + M + B
            if faceshapes.SOCK_SMOOTH and self.gnm_mouth:  # the rest's sock ironed too (hidden here; every shape opens onto it)
                D = self._smooth_sock(Xm, D, index, rest=True)
        if faceshapes.NEUTRAL_PARTED and index is not None:  # the approved lips kept; the close is mouthClose's (displacements)
            self._gnm["parted"] = (Xm.shape, D)
            self._gnm["meet"] = None
            return np.zeros_like(Xm)
        return D

    def _by_index(self, dV: np.ndarray) -> np.ndarray:
        """GNM offsets (its frame, every GNM vertex) -> world offsets of every GNM vertex, as the head places them
        (the one mesh: no subdivision, the stitch's fade)."""
        c = self._setup()["c"]
        d = dV * np.asarray(c["esc"], float)[:, None]
        if c.get("fade") is not None:
            d = d * np.asarray(c["fade"], float)[:, None]
        d[:, 0] *= c["narrow"]
        return c["s"] * d @ np.asarray(c["R"], float).T

    def _indexed(self, D: np.ndarray, index, dV: np.ndarray) -> np.ndarray:
        idx = np.asarray(index, int)
        own = idx >= 0
        D = np.array(D, float)
        from . import gnmloops  # (the lids' new vertices, ids >= GNM's count: their parents' mean)
        D[own] = gnmloops.take(self._by_index(dV), idx[own])
        return D

    def displacements(self, Xm, Xn, nrm, kind, names, lower=None, index=None) -> dict:
        if kind == "eyes":
            return self.eye_part(Xm, names)
        G = self._setup()
        L = self.local(Xm)
        n = len(Xm)
        wj = self.jaw_weight(L) if kind == "skin" else (np.ones(n) if kind == "tongue" else
                                                        (np.zeros(n) if lower is None else lower.astype(float)))
        res = {}
        todo = [nm for nm in names if nm not in G.setdefault("dW", {}) and family(nm) != "look"]
        if todo:  # every shape's GNM offsets, then one subdivision for all of them
            dVs = []
            for name in todo:
                mv, region = self._gnm_moves(name)
                dV = mv if region is None else self._solve(mv, region,
                                                           prior=faceshapes.JAW_PRIOR if name in faceshapes.JAW_PRIORED else faceshapes.SOLVE_RIDGE)
                if name == "tongueOut" and self.gnm_mouth:  # GNM's own tongue components on top of the jaw's opening
                    dV = dV + self._tongue_out()[0]
                if self.gnm_mouth and faceshapes.WRAP_TEETH and name.split("Left")[0].split("Right")[0] in faceshapes.WRAP_SHAPES:
                    dV = self._wrap_teeth(dV)
                dVs.append(dV)
            G["dW"].update(zip(todo, self._carried(*dVs)))
            G.setdefault("dV", {}).update(zip(todo, dVs))
        # regions: the basis's lower-face components reach up to the lids and its eye components down the cheek;
        # each family fades out past its own region (jawOpen moved the forehead, brows tugged the cheek)
        lm = self.head["lm68"]
        h = (Xm - self.M) @ self.up
        hn = float((lm[33] - self.M) @ self.up)                   # the nose's base
        hl = float(np.mean([(lm[i] - self.M) @ self.up for i in (40, 41, 46, 47)]))  # the lower lids
        mouth_mask = 1 - _ss((h - (hn + 0.35 * (hl - hn))) / (0.55 * (hl - hn)))
        eye_mask = _ss((h - hn) / (0.5 * (hl - hn)))
        carry = {}
        if faceshapes.SMILE_FIT_FADE:
            fw = faceshapes.SMILE_FIT_FADE * (hl - hn)
            fit_mouth = 1 - _ss((h - (hl - fw)) / fw)
        for name in names:
            if family(name) == "look":  # (the eyeballs' part turns; the skin stays)
                res[name] = np.zeros_like(Xm)
                continue
            dW = G["dW"][name]
            if self.gnm_mouth and kind in ("teeth", "tongue"):
                # GNM's own teeth and tongue: the shape's expression coefficients on THEIR vertices (the lower row
                # and the tongue go with the lower-face components, the tongue with its own; the upper row stays)
                if kind == "tongue" and name in faceshapes.JAW_SHAPES:  # the tongue rides the lower row rigidly (its own share
                    # of the jaw's coefficients left it up in the opening: expr_r4's "red mass"), tongueOut adds its own
                    Rr, a, b = self._rigid_lower_row(G["dV"][name])
                    d = (Xn - a) @ Rr.T + b - Xn
                    if name == "tongueOut":
                        d = d + self._piece_onto(Xn, self._tongue_out()[0], "tongue")
                    if name == "jawOpen" and any(faceshapes.JAW_TONGUE):  # GNM's own tongue shape: tip down behind the
                        # lower teeth, the top bowed (r25)
                        d = d + self._piece_onto(Xn, self._tongue_shape(*faceshapes.JAW_TONGUE), "tongue")
                    if name == "jawOpen":  # the dorsum flattens as the floor of the mouth drops (it rose into the
                        # opening, "a red mass", expr_r4..r6): each point down by its height share over the tongue
                        hh = (Xn - Xn.min(0)) @ self.up
                        d = d - (faceshapes.TONGUE_SINK + faceshapes.TONGUE_DROP * (hh / max(float(hh.max()), 1e-9)))[:, None] * self.up[None]
                        if any(faceshapes.TONGUE_DOME):  # (r32) a sagittal dome: the front half rolls down toward the tip
                            # (quadratic in its share of the front half: its top then faces the camera and catches
                            # light, the back stays flat under the palate's shadow) and the whole tongue rises a little
                            fz = Xn @ self.out; q0, q1 = np.percentile(fz, 50), fz.max()
                            sh = np.clip((fz - q0) / max(q1 - q0, 1e-9), 0, 1)
                            top = np.clip((hh / max(float(hh.max()), 1e-9) - 0.3) / 0.4, 0, 1)
                            tl = np.clip((q1 - fz) / max(q1 - fz.min(), 1e-9), 0, 1)  # 1 at the back, 0 at the tip
                            d = d + (faceshapes.TONGUE_DOME[1] * tl - faceshapes.TONGUE_DOME[0] * sh ** 2 * top)[:, None] * self.up[None]
                    res[name] = d * self.amount.get(name, 1.0)
                    continue
                if (faceshapes.SMILE_FIT and kind == "teeth" and name.startswith("mouthSmile")) or (faceshapes.JAW_FIT and kind == "teeth" and name == "jawOpen"):  # (r36) the fitted smile's jaw share
                    # moves the lower row RIGIDLY (its own coefficients on the teeth bent the rows: f36a), the upper row stays
                    Rr, a, b = self._rigid_lower_row(G["dV"][name])
                    lw = np.zeros(len(Xn)) if lower is None else np.asarray(lower, float)
                    res[name] = ((Xn - a) @ Rr.T + b - Xn) * lw[:, None] * self.amount.get(name, 1.0)
                    continue
                res[name] = self._piece_onto(Xn, G["dV"][name], kind, lower) * self.amount.get(name, 1.0)
                continue
            if self.gnm_mouth:  # what isn't near the skin's own vertices is GNM's mouth sock: its own offsets
                rigid = self._piece_onto(Xn, G["dV"][name], "sock") if kind == "skin" else np.zeros_like(Xn)
            elif name in faceshapes.JAW_SHAPES:
                Rr, a, b = self._rigid_jaw(dW)
                rigid = (Xn - a) @ Rr.T + b - Xn  # the jaw's own move, for what isn't skin (bag, teeth, tongue)
            else:  # (the jaw line hardly moves: its fit is noise, and moved the teeth in a smile)
                rigid = np.zeros_like(Xn)
            if kind == "skin":
                D, near = self._onto(Xm, dW)
                if index is not None:  # (one mesh, own quads) GNM's vertices move as GNM moves them: no projection
                    # (the lips' inner rolls and the mouth sock are its own; nearest-six mixed the parted lips)
                    D = self._indexed(D, index, G["dV"][name])
                    near = np.where(np.asarray(index) >= 0, 1.0, near)
                    mt = self._gnm.get("meet")
                    if mt is not None and mt[0] == Xm.shape:  # the neutral's lips were closed past GNM's own (its
                        # basis leaves them parted): a shape that parts them takes that close back in proportion
                        # (left in, jawOpen tore the inner rolls into shards against the closed contact ring)
                        D = D - self._meet_share(D, mt[1], index) * mt[1]
                # (headbody, 2026-10-12) the jaw's rigid move in full is for GNM's own TEETH and TONGUE only: on the skin
                # it gave every vertex away from the face (the whole body under the neck) jawOpen's 26 mm, and
                # rigid_near then weighted all of it 1.0 to the Head bone (the chest turned with the head)
                d = D * near[:, None] + rigid * ((1 - near) * (1.0 if self.gnm_mouth and kind != "skin" else wj))[:, None]
                if index is not None and kind == "skin":  # (one mesh) the body under the stitch: GNM's shapes fade to
                    # 0 at the seam ring, so nothing below it moves
                    d[np.asarray(index) < 0] = 0.0
                fam = family(name)
                if index is not None and kind == "skin" and fam == "mouth" and faceshapes.SOCK_SMOOTH and self.gnm_mouth:
                    d = self._smooth_sock(Xn, d, index)
                if index is not None and kind == "skin" and name.startswith("mouthSmile") and faceshapes.SMILE_EDGE_LIFT[0] and not faceshapes.SMILE_FIT:
                    d = self._smile_edge(Xn, d, index, "Left" if name.endswith("Left") else "Right")
                if index is not None and kind == "skin" and fam == "mouth" and faceshapes.ROLL_TUCK:
                    ins = [] if not (faceshapes.ROLL_TUCK_COMBINED and name in faceshapes.CORRECTIVES) else [
                        j for i in faceshapes.CORRECTIVES[name][1:] for j in ((i,) if i in res else (i + "Left", i + "Right"))]
                    if ins and all(i in res for i in ins):  # (r33) a corrective's rolls tucked against the COMBINED
                        # pose (its inputs at full + itself), not its own offsets alone: jawOpen's tuck is for its lifted
                        # lip, so a corrective that lowers the vermilion left the roll hanging below it (a dark dash)
                        base = sum(res[i] for i in ins)
                        d = self._rolls_tucked(Xn, base + d, index) - base
                    else:
                        d = self._rolls_tucked(Xn, d, index)
                fit_free = bool(faceshapes.SMILE_FIT) and not faceshapes.SMILE_FIT_MASK and name.startswith(("mouthSmile", "cheekSquint"))
                if fit_free:  # (r37) the fitted smile's halves as fitted (see SMILE_FIT_MASK), (r38) faded at the family
                    if faceshapes.SMILE_FIT_FADE and fam == "mouth":  # border only (SMILE_FIT_FADE; cheekSquint is "mid": no family mask)
                        if faceshapes.SMILE_FIT_CARRY:
                            carry[name.replace("mouthSmile", "cheekSquint")] = d * (1 - fit_mouth)[:, None]
                        d *= fit_mouth[:, None]
                elif fam == "mouth":  # (the smile's cheek "terraces" in expr_r6 were Blender's split-normal seams, not
                    # this mask: blender_game imports with merge_vertices now; the lids stay cheekSquint's)
                    d *= mouth_mask[:, None]
                elif fam == "eye":
                    d *= eye_mask[:, None]
                if name not in faceshapes.JAW_SHAPES and self.eyes:  # (GNM's expression prototypes behind the smile and
                    # cheekSquint moved the back of the head and the neck 0.4 mm: test_gnm_head_shapes) faded out past
                    # MOUTH_REACH from the mouth and EYE_REACH from between the eyes
                    rr = np.linalg.norm(Xm - self.M, axis=1)
                    ec = np.mean([np.asarray(e["c"], float) for e in self.eyes.values()], 0)
                    re = np.linalg.norm(Xm - ec, axis=1)
                    keep = np.maximum(1 - _ss((rr - faceshapes.MOUTH_REACH[0]) / (faceshapes.MOUTH_REACH[1] - faceshapes.MOUTH_REACH[0])),
                                      1 - _ss((re - faceshapes.EYE_REACH[0]) / (faceshapes.EYE_REACH[1] - faceshapes.EYE_REACH[0])))
                    d *= keep[:, None]
                if kind == "skin" and name.startswith("mouthSmile") and faceshapes.SMILE_FOLD and not faceshapes.SMILE_FIT:
                    d = d + self._smile_fold(Xn, nrm, "Left" if name.endswith("Left") else "Right")
                elif kind == "skin" and name.startswith("mouthSmile") and faceshapes.SMILE_FOLD and faceshapes.SMILE_FIT and faceshapes.SMILE_FIT_FOLD:
                    d = d + faceshapes.SMILE_FIT_FOLD * self._smile_fold(Xn, nrm, "Left" if name.endswith("Left") else "Right", corner=False)
                if name.startswith("eyeBlink") and faceshapes.LID_SEAL and self.lid_seal["amount"] > 0:
                    # (by index too: GNM's own blink left Tess's lids 2.75 mm apart mid-eye and ~2 mm at the corners,
                    # measured by rays from the front on the export (assembly/eyegap.py): a pale sliver under the
                    # lashes and red slits at the corners in every skin round)
                    for sd in self.eyes:
                        if name.endswith(sd):
                            d = self._lid_seal(sd, Xn, d)
                # nothing may sink into an eyeball (a blink's lid slides over it), but no deeper than where the
                # neutral already has it: pushed out to a fixed clearance, the lower lids (a hair inside it in the
                # neutral) took the same 3-6 mm offset in EVERY shape, and A2F's sums dragged them 10-27 mm
                for ev in self.eyes.values():
                    r0 = np.linalg.norm(Xn - ev["c"], axis=1)
                    q = Xn + d - ev["c"]
                    r = np.linalg.norm(q, axis=1)
                    lim = np.minimum(ev["r"] + 0.0006, r0)
                    inside = (r < lim) & (r0 < 1.6 * ev["r"])
                    d[inside] += q[inside] * ((lim[inside] - r[inside]) / np.maximum(r[inside], 1e-9))[:, None]
                    if ev.get("cornea"):  # GNM's corneal bulge: the closing UPPER lid rides over it, as over the ball
                        cc, rc = ev["cornea"]
                        r0c = np.linalg.norm(Xn - cc, axis=1)
                        qc = Xn + d - cc
                        rr = np.linalg.norm(qc, axis=1)
                        limc = np.minimum(rc + 0.0001, r0c)
                        # (the upper lid only: it does the closing. Pushing the lower lid's few vertices that reach
                        # the cap made the skin under the eye jagged on a decimated face: unevenness 0.14 > 0.12)
                        ins = (rr < limc) & (r0c < 1.4 * rc) & ((Xn - ev["c"]) @ self.up > -0.15 * ev["r"])
                        d[ins] += qc[ins] * ((limc[ins] - rr[ins]) / np.maximum(rr[ins], 1e-9))[:, None]
                        # (pushed off the cornea a vertex may have slid a hair back into the ball: the ball's limit again)
                        q = Xn + d - ev["c"]
                        r = np.linalg.norm(q, axis=1)
                        inside = (r < lim) & (r0 < 1.6 * ev["r"])
                        d[inside] += q[inside] * ((lim[inside] - r[inside]) / np.maximum(r[inside], 1e-9))[:, None]
            else:
                d = rigid * wj[:, None]
            if name == "tongueOut" and kind == "tongue" and self.tongue is not None:
                tc, ts = self.tongue.params["c"], self.tongue.params["size"]
                along = np.clip(((Xm - tc) @ self.out + ts[1]) / (2 * ts[1]), 0, 1)
                reach = ((self.M - tc) @ self.out) - ts[1] + 0.3 * self.width
                d = d + (_ss(along) * reach)[:, None] * self.out - (along ** 2 * 0.2 * reach)[:, None] * self.up
            res[name] = d * self.amount.get(name, 1.0)
        for name, d in carry.items():  # (r39) SMILE_FIT_CARRY
            if name in res:
                res[name] = res[name] + d * self.amount.get(name, 1.0)
        pt = self._gnm.get("parted")
        if kind == "skin" and index is not None and "mouthClose" in res and pt is not None and pt[0] == Xm.shape:
            res["mouthClose"] = res["mouthClose"] + pt[1] * self.amount.get("mouthClose", 1.0)  # (r44) NEUTRAL_PARTED
        return res
