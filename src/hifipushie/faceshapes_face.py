"""class Face: a kit face's regions (the mouth's parts, the parting line, the lids), its seal and its shapes. Part of face shapes (faceshapes.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import faceshapes
from . import spec as specmod
from .spec import SpecError
from .faceshapes import _bump, _rodrigues, _ss, _unit
from .faceshapes import lid_seal_options

class Face:
    """The face kit's anatomy, read from the kit-expanded spec: mouth frame and parting line, slit, bag, teeth and
    tongue parts, jaw pivot, eyes (lids), brows, cheeks."""

    def __init__(self, spec: dict):
        kits = spec.get("kits") or {}
        faces = [(n, k) for n, k in kits.items() if k.get("type") == "face"]
        if not faces:
            raise SpecError("face_shapes needs a face kit (kits: {\"face\": {\"type\": \"face\", ...}})")
        name, k = faces[0]
        fb = name[:-2] if name.endswith(".L") else name
        m = k.get("mouth")
        if not m or not m.get("interior"):
            raise SpecError(f"face_shapes needs a mouth that can open: kits.{name}.mouth.interior (true, or "
                            "{\"teeth\": true, \"tongue\": true}): a slit between the lips and a mouth bag behind them")
        opts = spec.get("face_shapes") or {}
        self.amount = {str(a): float(v) for a, v in (opts.get("amount") or {}).items()}
        self.skin_parts = {str(p) for p in (opts.get("parts") or [])}
        bad = [a for a in self.amount if a not in faceshapes.ALL]
        if bad:
            raise SpecError(f"face_shapes.amount: unknown shape(s) {bad} (have the ARKit names {', '.join(faceshapes.ALL)})")
        e = specmod.expand_mirror(spec)
        J, B = e["joints"], e["blobs"]
        prims = {p.name: p for p in specmod.compile_prims(spec)}
        self.H = np.asarray(spec["joints"][k.get("head", "head")]["pos"], float)
        self.R = float(spec["joints"][k.get("head", "head")].get("r", 0.05))
        R = self.R
        self.out = _unit(m.get("dir", [0, -1, 0]))
        up = np.array([0.0, 0.0, 1.0])
        self.up = _unit(up - self.out * (up @ self.out))
        self.side = np.cross(-self.out, self.up)  # the creature's left (+X when it faces -Y)
        self.width = float(m.get("width", 0.9 * R))
        self.W2 = self.width / 2
        self.ru, self.rl = float(m.get("upper", 0.07 * R)), float(m.get("lower", 0.08 * R))
        self.lip = max(self.ru, self.rl)
        line = [np.asarray(J[f"{fb}_mouth_line_0"]["pos"], float)] + [
            np.asarray(J[f"{fb}_mouth_line_{i}.L"]["pos"], float) for i in range(1, 6)]
        corner = np.asarray(J[f"{fb}_mouth_corner.L"]["pos"], float)
        self.M = line[0]
        pts = np.array(line + [corner]) - self.M
        self.su = np.clip(pts @ self.side / self.W2, 0, None)
        self.sz = pts @ self.up            # the parting line's height (the smile) by u
        self.sf = pts @ self.out           # and how far forward it is (the lips' front)
        self.corners = {"Left": corner, "Right": corner - 2 * self.side * ((corner - self.M) @ self.side)}
        self._mouth_parts(prims, fb)
        # the nose is bone: mouth shapes leave it where it is (a goblin's nose hangs over its upper lip)
        self.nose = [p for n, p in prims.items() if n.startswith(f"{fb}_nose") and p.op == "add"]
        # noseSneer lifts the wings (levator labii superioris alaeque nasi): it holds only the bridge and ball
        self.nose_bone = [p for n, p in prims.items() if n.startswith(f"{fb}_nose") and p.op == "add"
                          and "_wing" not in n and "nostril" not in n]
        jaw = opts.get("jaw") or {}
        self.lid_seal = lid_seal_options(opts.get("lid_seal"))  # (GNM heads; validated here too)
        self.eyes = {}
        for s, sfx in (("Left", ".L"), ("Right", ".R")):
            lp = prims.get(f"{fb}_lids{sfx}")
            if lp is None or lp.params.get("closed"):
                continue
            bl = B[f"{fb}_lids{sfx}"]
            r = float(lp.params["r"])
            hu, hl = lp.params["cu"] + lp.params["Ru"], lp.params["cl"] - lp.params["Rl"]
            self.eyes[s] = {"c": lp.params["c"], "rot": lp.params["rot"], "r": r, "ro": lp.params["ro"],
                            "hu": hu, "hl": hl, "zc": 0.35 * hu + 0.65 * hl, "w": r * float(bl.get("width", 0.85)),
                            "part": prims[f"{fb}_eye{sfx}"].part if f"{fb}_eye{sfx}" in prims else None}
        if "pivot" in jaw:
            self.P = np.asarray(specmod.resolve_point(e, jaw["pivot"]), float)
        else:  # in front of the ear: back level with the head's centre, half way up from the mouth to the eyes
            eye_z = np.mean([(v["c"] - self.M) @ self.up for v in self.eyes.values()]) if self.eyes else 0.8 * R
            back = (self.M - self.H) @ self.out + 0.1 * R
            self.P = self.M - self.out * back + self.up * 0.5 * eye_z
        self.open = np.radians(float(jaw.get("open", 18.0)))
        self.depth = float(jaw.get("depth", 0.75 * R))
        self.brows = {}
        for s, sfx in (("Left", ".L"), ("Right", ".R")):
            bp = prims.get(f"{fb}_brow{sfx}")
            if bp is not None:
                ax = bp.params["rot"][:, 0] * bp.params["size"][0]
                ends = [bp.params["c"] + ax, bp.params["c"] - ax]
                inner = min(ends, key=lambda q: abs((q - self.M) @ self.side))
                outer = max(ends, key=lambda q: abs((q - self.M) @ self.side))
                self.brows[s] = {"c": bp.params["c"], "inner": inner, "outer": outer, "half": float(bp.params["size"][0])}
            elif s in self.eyes:  # no brow blob: the skin above the eye
                ev = self.eyes[s]
                c = ev["c"] + self.up * 1.6 * ev["r"] + self.out * 0.6 * ev["r"]
                d = self.side * (1 if s == "Left" else -1) * ev["r"]
                self.brows[s] = {"c": c, "inner": c - d, "outer": c + d, "half": float(ev["r"])}
        self.cheeks = {}
        for s, sfx in (("Left", ".L"), ("Right", ".R")):
            cp = prims.get(f"{fb}_cheek{sfx}")
            sg = 1 if s == "Left" else -1
            if cp is not None:
                self.cheeks[s] = (cp.params["c"], float(np.max(cp.params["size"])))
            else:
                c = self.corners[s] + self.side * sg * 0.25 * self.width + self.up * 0.1 * self.width
                self.cheeks[s] = (c - self.out * 0.15 * self.width, 0.3 * self.width)
        self.sneer = {}
        for s, sfx in (("Left", ".L"), ("Right", ".R")):
            wp = prims.get(f"{fb}_nose_wing{sfx}")
            ball = prims.get(f"{fb}_nose_ball")
            if wp is not None or ball is not None:
                p0 = wp if wp is not None else ball
                c, r = np.asarray(p0.params["c"], float), float(np.max(p0.params["size"]))
                if wp is None:
                    c = c + self.side * (1 if s == "Left" else -1) * r
                self.sneer[s] = (c + self.side * (1 if s == "Left" else -1) * r, 1.5 * r)

    def _mouth_parts(self, prims: dict, fb: str):
        """The interior the kit made (kits._interior): slit, bag, teeth and tongue parts."""
        slit = prims[f"{fb}_mouth_slit"]
        self.slit_u = np.clip(((slit.params["P"] - self.M) @ self.side) / self.W2, 0, None)
        self.slit_h = np.asarray(slit.params["V"]["u1"], float)
        self.slit = 2 * float(self.slit_h[0])
        self.slit_part = slit.part
        bag = prims[f"{fb}_mouth_bag"]
        self.bag = np.asarray(bag.params["size"], float)
        self.thick = float(((self.M - bag.params["c"]) @ self.out) - self.bag[1])  # lip front to the bag's front
        self.parts_teeth = {p.part for n, p in prims.items() if n.startswith(f"{fb}_teeth_")}
        rows = [p for n, p in prims.items() if n.startswith(f"{fb}_teeth_")]
        self.teeth_t = min((float(np.min(p.params["V"]["n1"] - p.params["V"]["n0"])) for p in rows), default=1.0)
        self.parts_tongue = {p.part for n, p in prims.items() if n == f"{fb}_tongue"}
        self.tongue = prims.get(f"{fb}_tongue")

    def inside_mouth(self, X: np.ndarray, prims) -> np.ndarray:
        """Which points (n, 3) lie in the mouth's interior (the slit's walls, the bag): within the mouth's box and
        with the slit's own part (`prims`, its field) standing in FRONT of them, the lips. The export's mesh report
        leaves these out of its tear alarm: a bag's corners at a game budget fold, behind closed lips."""
        from . import sdf
        X = np.asarray(X, np.float64).reshape(-1, 3)
        if not len(X):
            return np.zeros(0, bool)
        q = X - self.M
        box = (np.abs(q @ self.side) < 1.3 * self.W2) & (np.abs(q @ self.up) < 2.0 * self.bag[2] + 0.01) \
            & (-(q @ self.out) < self.thick + 2 * self.bag[1] + 0.01)
        out = np.zeros(len(X), bool)
        idx = np.flatnonzero(box)
        far = self.thick + 2 * self.bag[1] + 0.004  # (from the bag's back wall the lips are this far in front)
        for t in np.linspace(0.002, far, max(6, int(np.ceil(far / 0.002)))):
            if not len(idx):
                break
            hit = sdf.field_at(prims, X[idx] + t * self.out, clip=False) < -3e-4
            out[idx[hit]] = True
            idx = idx[~hit]
        return out

    def neutral(self, Xm: np.ndarray, kind: str, index=None) -> np.ndarray:
        """The neutral's move for a part's meshed vertices: the slit closed (the lips only)."""
        return self.close(self.local(Xm)) if kind == "skin" else np.zeros_like(Xm)

    SEAL_BINS = 0.05  # seal(): how far across (of the half width) and
    SEAL_BACK = 0.001  # how far back (m) the gap at a point is measured
    SEAL_PASSES = 3  # measured and closed again on the result
    SEAL_SMOOTH = 8  # passes of smoothing the gap over the mesh
    SEAL_POCKET = 0.85  # past this (of the half width) the gap is closed at every depth (the corners' pockets)
    SEAL_OVERLAP = 0.0002  # the lips pressed this much past touching (met exactly, the low poly's edges left pinholes)

    def seal(self, Xm: np.ndarray, Xc: np.ndarray, T: np.ndarray) -> np.ndarray:
        """The neutral's last step on the skin: whatever gap `neutral` left between the lips, measured on this low
        poly (Xm meshed, Xc closed, T its triangles), closed. Across the mouth (bins of SEAL_BINS half widths, out
        past the corners), the upper lip's lowest point and the lower lip's highest in front of the bag (points over
        each lip's triangles; sides by the parting line at the meshed position, heights at the closed one) leave a
        gap r; each lip moves r/2 toward the other there, fading over a few lip radii up and down, behind the bag's
        front and past the corners (u 1, where the skin is one surface). GNM's basis close met only at the middle: the lips stayed ~1 mm apart and the corners
        open 5-7 mm (dark pockets on Garrett, s0urc3 2026-10-03). Returns the move."""
        D = np.zeros_like(Xm)
        for k in range(self.SEAL_PASSES):  # (each pass closes what the last left: edges that don't line up across)
            D += self._seal_pass(Xm, Xc + D, T)
            if k == 0:
                first = self.sealed
        self.sealed = first
        return D

    def _seal_pass(self, Xm: np.ndarray, Xc: np.ndarray, T: np.ndarray) -> np.ndarray:
        L = self.local(Xm)
        h0c = self.local(Xc)["h0"]  # heights over the parting line at the closed position
        up = L["h0"] >= 0
        front = 0.5 * self.thick  # the gap is measured (and closed in full) in front of this: what shows
        # the lips near where they meet (a goblin's nose over its upper lip and its chin, at the same depth, measured
        # a 4 cm "gap")
        cand = (L["u"] < 1.3) & (L["back"] < front) & (L["back"] > -2 * self.lip) & (np.abs(h0c) < 2 * self.lip)
        xs = L["xs"] / self.W2
        tc = T[cand[T].all(1)]
        side = up[tc]
        tc, side = tc[side.all(1) | (~side).all(1)], side[side.all(1) | (~side).all(1)]  # (one lip's own)
        # points over each triangle (barycentric grid): across, how far back, height at the closed position
        g = np.array([(i, j, 6 - i - j) for i in range(7) for j in range(7 - i)], float) / 6
        px, pb, ph = ((v[tc] @ g.T).ravel() for v in (xs, L["back"], h0c))
        pu = np.repeat(side[:, 0], len(g))
        # the gap r at each point (across, back): the upper lip's lowest point near it minus the lower's highest
        # (a corner's pocket is deeper inside than at its front: per column alone, its back wall hid the front gap)
        from scipy.spatial import cKDTree
        sx, sb = self.SEAL_BINS, self.SEAL_BACK
        tr = [cKDTree(np.c_[px[m] / sx, pb[m] / sb]) for m in (pu, ~pu)]
        hs = [ph[pu], ph[~pu]]

        def gap(qx, qb):
            q = np.c_[qx / sx, qb / sb]
            hit = [t.query_ball_point(q, 1.0) for t in tr]
            out = np.full((len(q), 2), np.nan)  # the gap, and the height half way across it
            for k, (iu, il) in enumerate(zip(*hit)):
                if iu and il:
                    a, b = hs[0][iu].min(), hs[1][il].max()
                    out[k] = a - b, 0.5 * (a + b)
            return out
        mids = np.arange(-1.2, 1.2 + 1e-9, 0.5 * sx)
        r1, z1 = gap(mids, np.zeros_like(mids)).T  # along the lips' front: the profile logged
        self.sealed = (mids, np.clip(np.nan_to_num(r1), 0.0, 2 * self.lip))
        z1 = np.interp(mids, mids[np.isfinite(z1)], z1[np.isfinite(z1)]) if np.isfinite(z1).any() else np.zeros_like(mids)
        zm = np.interp(xs, mids, z1)  # where the lips meet: each point's own, else its column's front
        rv = np.zeros(len(Xm))
        sel = np.flatnonzero(cand & (L["u"] < 1.2))
        if len(sel) == 0 or not len(pu):
            return np.zeros_like(Xm)
        rs, zs = gap(xs[sel], np.clip(L["back"][sel], -2 * self.lip, front)).T
        if np.isnan(rs).all():
            return np.zeros_like(Xm)
        ok = np.isfinite(rs)  # (no lip on one side near it: the nearest measured gap)
        if (~ok).any():
            near = cKDTree(np.c_[xs[sel][ok] / sx, L["back"][sel][ok] / sb]).query(
                np.c_[xs[sel][~ok] / sx, L["back"][sel][~ok] / sb])[1]
            rs[~ok], zs[~ok] = rs[ok][near], zs[ok][near]
        # (zm stays the column's: per point, an upper and a lower point met at different heights and crossed)
        rs = np.minimum(rs, 2 * self.lip)  # (more than that is no gap between lips)
        # inside the corners, behind the front only what the front left: closing the slit's walls by their own
        # (wider) gap pressed the lips together all through and A2F's lip combos (roll + shrug, pucker + roll) then
        # pushed the lower lip up in front of the upper 3-5 mm; the corners' pockets are closed by their own gap
        u_s = L["u"][sel]
        rs = np.where(u_s > self.SEAL_POCKET, rs, np.minimum(rs, np.interp(xs[sel], mids, self.sealed[1])))
        rv[sel] = (np.maximum(rs, 0.0) + self.SEAL_OVERLAP) * _bump(np.abs(xs[sel]), 1.0, 1.15)
        # the rest of the lips (beyond the band the gap was measured in) take the nearest column's front gap
        rest = np.flatnonzero(~np.isin(np.arange(len(Xm)), sel) & (L["u"] < 1.2))
        rv[rest] = (np.interp(xs[rest], mids, self.sealed[1]) + self.SEAL_OVERLAP) * _bump(np.abs(xs[rest]), 1.0, 1.15)
        # smoothed over the mesh (each point's own gap differs from its neighbours': a jagged lip edge), never below
        # the front gap of its column
        e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
        e = np.r_[e, e[:, ::-1]]
        floor = np.where(L["u"] < 1.2, np.interp(xs, mids, self.sealed[1]) * _bump(np.abs(xs), 1.0, 1.15), 0.0)
        for _ in range(self.SEAL_SMOOTH):
            acc = np.bincount(e[:, 0], rv[e[:, 1]], len(Xm)) + rv
            cnt = np.bincount(e[:, 0], minlength=len(Xm)) + 1
            rv = np.where(rv > 0, np.maximum(acc / cnt, floor), rv)
        lat = _bump(L["u"], 1.0, 1.2)
        deep = _bump(L["back"], front, self.thick + 0.6 * self.bag[1])
        hu = _bump(h0c, 0.5 * rv + 1.2 * self.ru, 0.5 * rv + 3.0 * self.ru)
        hl = _bump(-h0c, 0.5 * rv + 1.2 * self.rl, 0.5 * rv + 3.0 * self.rl)
        dz = 0.5 * rv * lat * deep * np.where(up, -hu, hl)
        # never past where the lips meet (+ the overlap): at a corner a lip's last vertices sit near it while the
        # pocket beside them is millimetres open, and its gap carried them across each other
        o = 0.5 * self.SEAL_OVERLAP
        dz = np.where(up, np.maximum(dz, np.minimum(zm - h0c - o, 0.0)), np.minimum(dz, np.maximum(zm - h0c + o, 0.0)))
        return dz[:, None] * self.up

    def off_margins(self, name: str, X: np.ndarray) -> np.ndarray | None:
        """Where `unevenness` judges a shape: everywhere, except a blink's own lid margins (the skin within 3 mm
        of the eyeball). There a blink is uneven on purpose: each margin vertex is brought to the lid line from
        its own height."""
        if not name.startswith("eyeBlink") or not self.eyes:
            return None
        return np.min([np.linalg.norm(X - np.asarray(ev["c"], float), axis=1) - float(ev["r"])
                       for ev in self.eyes.values()], axis=0) > 0.003

    def owns(self, part: str) -> bool:
        """Whether a part takes the skin's face shapes: the face's own skin (the part the lips are in) and any listed
        in spec.face_shapes.parts (a beard or brow shell). Clothes never do: transferred by distance, the jaw
        shapes moved Garrett's collar 31 mm and his jacket's lapel trim 21 mm."""
        return part == self.slit_part or part in self.skin_parts

    LOOK = {"Up": 20.0, "Down": 20.0, "In": 25.0, "Out": 25.0}  # deg at 1.0

    def eye_part(self, Xm: np.ndarray, names) -> dict:
        """The eyeballs' own part: eyeLook<Dir><Side> turns that side's eyeball about its centre (Up/Down about the
        left-right axis, In = toward the nose); every other shape leaves them still."""
        res = {}
        side_of = None
        if self.eyes:
            cs = {s: ev["c"] for s, ev in self.eyes.items()}
            ks = list(cs)
            dist = np.stack([np.linalg.norm(Xm - cs[k], axis=1) for k in ks])
            side_of = np.array(ks)[np.argmin(dist, 0)]
        for name in names:
            d = np.zeros_like(Xm)
            if name.startswith("eyeLook") and side_of is not None:
                s = "Left" if name.endswith("Left") else "Right"
                dr = name[len("eyeLook"):-len(s)]
                if s in self.eyes:
                    c = self.eyes[s]["c"]
                    sg = 1.0 if s == "Left" else -1.0
                    t = {"Up": self.up, "Down": -self.up, "In": -sg * self.side, "Out": sg * self.side}[dr]
                    axis = _unit(np.cross(self.out, t))
                    m = side_of == s
                    rel = Xm[m] - c
                    ang = np.full(m.sum(), np.radians(self.LOOK[dr]) * self.amount.get(name, 1.0))
                    d[m] = _rodrigues(axis, ang, rel) - rel
            res[name] = d
        return res

    def voxels(self) -> dict:
        """{part: voxel}: the export meshes the slit's part at least this fine, so the slit (2+ voxels across) and
        the lips' inner faces are real surfaces."""
        out = {} if getattr(self, "own_quads", False) else {self.slit_part: round(self.slit / 2.2, 5)}
        # (one mesh on its own quads: GNM's lips and sock are the mouth's surfaces, the field's slit isn't meshed)
        for pn in self.parts_teeth:  # a tooth row's thickness 3 voxels across (at a big body's scene voxel the
            # lower row came out in shreds)
            out[pn] = min(out.get(pn, 1.0), round(self.teeth_t / 3, 5))
        return out

    def tri_focus(self, k: float = 2.0) -> list:
        """Spheres the export's decimation magnifies k x (focuswarp.py: more triangles there): each eye's lids (a
        blink moves them an eye radius: on the plain low poly the skin round them showed facets) and the lips."""
        out = [[*map(float, ev["c"]), float(ev["ro"] + 0.3 * ev["r"]), k] for ev in self.eyes.values()]
        return out + [[*map(float, self.M - self.out * 0.5 * self.thick), float(0.45 * self.width), 1 + 0.5 * (k - 1)]]

    # ---- the parting line and the regions -------------------------------------------------------------------

    def local(self, X: np.ndarray) -> dict:
        """Mouth coordinates of points X (n, 3): u (|across| / half width), the height over the parting line h0,
        how far behind the lips' front, the jaw boundary's height h (rising toward the pivot past the corners)."""
        q = X - self.M
        xs = q @ self.side
        u = np.abs(xs) / self.W2
        uc = np.minimum(u, self.su[-1])
        zs = np.interp(uc, self.su, self.sz)
        back = np.interp(uc, self.su, self.sf) - q @ self.out
        h0 = q @ self.up - zs
        pz = (self.P - self.M) @ self.up
        pb = (self.M - self.P) @ self.out
        t = np.clip(back / pb, 0, 1) * _ss((u - 0.9) / 0.7)
        h = h0 - (pz - zs) * t
        return {"xs": xs, "u": u, "h0": h0, "back": back, "h": h, "pb": pb}

    def jaw_weight(self, L: dict) -> np.ndarray:
        """How much of the jaw's motion a point takes: below the parting line (a crisp step across the slit, wider
        past the corners and deep in the bag, so the cheeks and the bag's back wall stretch), in front of the pivot,
        above where the jaw ends under the chin."""
        band = 0.45 * self.slit + 0.5 * self.W2 * np.clip(L["u"] - 0.85, 0, None) \
            + 0.2 * np.clip(L["back"] - self.thick, 0, None)
        below = 1.0 - _ss((L["h"] + band) / (2 * band))
        front = _ss((L["pb"] - L["back"]) / (0.3 * self.R))
        neck = _bump(-L["h0"], self.depth, self.depth + 0.4 * self.R)
        return below * front * neck

    def lips(self, L: dict) -> tuple[np.ndarray, np.ndarray]:
        """The upper and lower lip (weights): either side of the parting line, a few lip radii high, out to the
        corners, from the front to the bag's front wall."""
        b0 = 0.45 * self.slit
        above = _ss((L["h0"] + b0) / (2 * b0))
        deep = _bump(L["back"], self.thick, 1.5 * self.thick)
        lat = _bump(L["u"], 0.95, 1.45)
        up = above * _bump(L["h0"], 1.4 * self.ru, 3.4 * self.ru) * deep * lat
        lo = (1 - above) * _bump(-L["h0"], 1.4 * self.rl, 3.4 * self.rl) * deep * lat
        return up, lo

    def close(self, L: dict) -> np.ndarray:
        """The neutral's move: each lip half the slit toward the parting line (the slit's own height at u)."""
        hs = np.interp(np.minimum(L["u"], self.slit_u[-1]), self.slit_u, self.slit_h)
        b0 = 0.45 * self.slit
        above = _ss((L["h0"] + b0) / (2 * b0))
        lat = _bump(L["u"], 0.75 * self.slit_u[-1], self.slit_u[-1] + 0.04)  # (to the end cap, a flap at the corner)
        deep = _bump(L["back"], self.thick, self.thick + 0.6 * self.bag[1])
        hu = _bump(L["h0"], hs + 1.2 * self.ru, hs + 3.0 * self.ru)
        hl = _bump(-L["h0"], hs + 1.2 * self.rl, hs + 3.0 * self.rl)
        dz = hs * lat * deep * (-above * hu + (1 - above) * hl)
        return dz[:, None] * self.up

    # ---- shapes ----------------------------------------------------------------------------------------------

    def _jaw_move(self, Xn: np.ndarray, wj: np.ndarray, ang: float) -> np.ndarray:
        axis = np.cross(self.up, self.out)
        rel = Xn - self.P
        return wj[:, None] * (_rodrigues(axis, np.full(len(Xn), ang), rel) - rel)

    def displacements(self, Xm: np.ndarray, Xn: np.ndarray, nrm: np.ndarray, kind: str, names,
                      lower: np.ndarray | None = None, index=None) -> dict:
        """{shape: (n, 3) move} for one part's vertices: Xm where they were meshed (weights), Xn the neutral
        (geometry), nrm its vertex normals. kind: "skin" (a part with the face), "teeth" (`lower`: the vertices of
        the lower row), "tongue"."""
        if kind == "eyes":
            return self.eye_part(Xm, names)
        L = self.local(Xm)
        n = len(Xm)
        zero = np.zeros((n, 3))
        out, up, side = self.out, self.up, self.side
        w = self.width
        if kind == "skin":
            wj = self.jaw_weight(L)
            lu, ll = self.lips(L)
        else:
            lu = ll = np.zeros(n)
            if kind == "tongue":
                wj = np.ones(n)
            else:  # teeth: the lower row rides the jaw, rigidly
                wj = np.zeros(n) if lower is None else lower.astype(float)
        # eyeball surfaces of the skin's own part (eyes not given a part of their own) never move, nor does the nose
        eyes_still = np.ones(n)
        for ev in self.eyes.values():
            eyes_still *= _ss((np.linalg.norm(Xm - ev["c"], axis=1) - 1.01 * ev["r"]) / (0.05 * ev["r"]))
        still, sneer_still = eyes_still.copy(), eyes_still.copy()
        if self.nose and kind == "skin":
            from . import sdf
            hold = lambda prims: 1 - _bump(sdf.field_at(prims, Xm), 0.001, 0.25 * self.lip + 0.004)  # noqa: E731
            still *= hold(self.nose)
            if self.nose_bone:
                sneer_still *= hold(self.nose_bone)
        jo = self._jaw_move(Xn, wj, self.open)
        # the lower lip's travel at jawOpen, per point (sampled on the parting line at the point's u): mouthClose
        # closes the gap, the lower lip doing most of it (CLOSE_LOWER)
        seam = self.M + side[None] * L["xs"][:, None] + up * np.interp(np.minimum(L["u"], self.su[-1]), self.su,
                                                                       self.sz)[:, None]
        delta = self._jaw_move(seam, np.ones(n), self.open)
        mreg = _bump(L["u"], 1.15, 2.0) * _bump(np.abs(L["h0"]), 2.5 * self.lip, 6 * self.lip) \
            * _bump(L["back"], self.thick, 2 * self.thick)
        lips = lu + ll
        ctr = _bump(L["u"], 0.0, 1.0)  # 1 at the middle of the mouth, 0 at the corners
        sgn = np.sign(L["xs"])
        res = {}

        def corner(s, a=0.15, b=0.55):
            d = np.linalg.norm(Xm - self.corners[s], axis=1)
            return _bump(d, a * w, b * w) * _bump(L["back"], self.thick, 2 * self.thick) * (kind == "skin")

        def half(s):  # the left / right half of the mouth, soft across the middle
            return _ss((L["xs"] * (1 if s == "Left" else -1)) / (0.6 * self.W2) + 0.5)

        def lip_roll(sel, lip_r, sense):
            """A lip drawn in over the teeth: back into the mouth and toward the parting line (sense +1 the lower
            lip, -1 the upper). A turn about the lip's axis tore where its weight fell off; a move can't."""
            return sel[:, None] * (-out * 0.6 * lip_r + up * sense * 0.45 * lip_r)  # (0.9 back: into the teeth)

        def press(s):
            hh = half(s)
            return hh[:, None] * (lu[:, None] * (-up * 0.3 * self.ru) + ll[:, None] * (up * 0.3 * self.rl)
                                  - lips[:, None] * out * 0.03 * w + lips[:, None] * side * sg_of(s) * 0.02 * w)

        def sg_of(s):
            return 1.0 if s == "Left" else -1.0

        # the upper lip's half of mouthClose follows the jaw weight of the point mirrored below the parting line
        # (at the corners the jaw takes less of the lower lip, and the upper lip must meet it there)
        if kind == "skin":
            Lp = self.local(Xm - 2 * L["h0"][:, None] * up)
            wjp = self.jaw_weight(Lp)
        else:
            wjp = np.zeros(n)

        for name in names:
            s = "Left" if name.endswith("Left") else "Right" if name.endswith("Right") else None
            sg = 1.0 if s == "Left" else -1.0
            if name == "jawOpen":
                d = jo
            elif name == "jawForward":
                d = wj[:, None] * out * 0.08 * w
            elif name in ("jawLeft", "jawRight"):
                d = wj[:, None] * side * sg * 0.08 * w
            elif name == "mouthClose":
                # alone (A2F drives it with the jaw shut): the closed lips firmed forward a little, never into each
                # other (a vertical press here intersected the human's lips on 70 of 765 A2F frames); the closing
                # against an open jaw is the corrective's
                d = lips[:, None] * out * faceshapes.CLOSE_SEAL * 0.03 * w
            elif name == "jawOpen_mouthClose":
                # against a full jawOpen: the lips meet, the lower lip doing most of it (meeting half way, the upper
                # lip hung like a curtain)
                d = -faceshapes.CLOSE_LOWER * jo * ll[:, None] + (1 - faceshapes.CLOSE_LOWER) * delta * (lu * wjp)[:, None]
            elif name == "jawOpen_mouthSmile":  # (the GNM path's corrective; nothing on the older template path)
                d = np.zeros((len(lips), 3))
            elif name == "mouthFunnel":
                c = (1 - 0.6 * np.minimum(L["u"], 1) ** 2)
                d = lips[:, None] * out * 0.09 * w * c[:, None] + (lu - ll)[:, None] * up * 0.06 * w * c[:, None] \
                    - (lips * sgn * np.minimum(L["u"], 1))[:, None] * side * 0.1 * self.W2
            elif name == "mouthPucker":
                c = (1 - 0.5 * np.minimum(L["u"], 1) ** 2)
                d = lips[:, None] * out * 0.12 * w * c[:, None] \
                    - (mreg * L["xs"] * 0.35 * _bump(L["u"], 1.0, 2.0))[:, None] * side \
                    + (ll - lu)[:, None] * up * 0.15 * self.slit
            elif name in ("mouthLeft", "mouthRight"):
                d = mreg[:, None] * side * sg * 0.15 * w
            elif name.startswith("mouthSmile"):
                d = corner(s)[:, None] * (up * 0.1 * w + side * sg * 0.06 * w - out * 0.05 * w)
            elif name.startswith("mouthFrown"):
                d = corner(s)[:, None] * (-up * 0.09 * w + side * sg * 0.02 * w)
            elif name.startswith("mouthDimple"):
                d = corner(s)[:, None] * (side * sg * 0.05 * w - out * 0.06 * w)
            elif name.startswith("mouthStretch"):
                d = corner(s, 0.2, 0.7)[:, None] * (side * sg * 0.09 * w - up * 0.04 * w)
            elif name == "mouthRollLower":
                d = lip_roll(ll, self.rl, 1.0)
            elif name == "mouthRollUpper":
                d = lip_roll(lu, self.ru, -1.0)
            elif name == "mouthShrugLower":
                chin = (1 - _ss((L["h"] + 0.45 * self.slit) / (0.9 * self.slit))) * _bump(-L["h0"], 0.3 * w, 0.8 * w) \
                    * _bump(L["u"], 0.9, 1.6) * _bump(L["back"], self.thick, 1.5 * self.thick) * (kind == "skin")
                d = chin[:, None] * (up * 0.05 * w + out * 0.03 * w)
            elif name == "mouthShrugUpper":
                d = lu[:, None] * (up * 0.05 * w + out * 0.03 * w)
            elif name.startswith("mouthPress"):
                d = press(s)
            elif name.startswith("mouthLowerDown"):
                d = (half(s) * ll)[:, None] * (-up * 0.1 * w + out * 0.02 * w)
            elif name.startswith("mouthUpperUp"):
                d = (half(s) * lu)[:, None] * (up * 0.1 * w + out * 0.02 * w)
            elif name.startswith("eyeBlink"):
                d = self._blink(s, Xm, Xn) if (kind == "skin" and s in self.eyes) else zero
            elif name.startswith("eyeWide"):  # the upper lid up a third of a blink's travel, the lower a little down
                d = self._blink(s, Xm, Xn, -0.35, -0.3) if (kind == "skin" and s in self.eyes) else zero
            elif name.startswith("eyeSquint") or name.startswith("cheekSquint"):
                d = zero.copy()
                if kind == "skin" and name.startswith("eyeSquint") and s in self.eyes:  # the lower lid up
                    d = self._blink(s, Xm, Xn, 0.1, 1.4)
                if kind == "skin" and s in self.cheeks:  # the cheek under the eye up (a squint takes some)
                    c, r = self.cheeks[s]
                    m = _bump(np.linalg.norm(Xm - c, axis=1), 0.5 * r, 1.5 * r) * (1 - lips)
                    d = d + (m * (0.3 if name.startswith("eyeSquint") else 1.0))[:, None] * up * 0.06 * self.R
            elif name.startswith("noseSneer"):  # the skin beside the nose's wing up and out (the nose stays)
                d = zero
                if kind == "skin" and self.sneer:
                    c, r = self.sneer[s]
                    m = _bump(np.linalg.norm(Xm - c, axis=1), 0.4 * r, 1.6 * r) * (1 - lips)
                    d = m[:, None] * (up * 0.05 * self.R + side * sg * 0.015 * self.R)
            elif name.startswith("eyeLook"):
                d = zero  # (the eyeballs' own part turns: eye_part)
            elif name.startswith("browDown") or name.startswith("browOuterUp") or name == "browInnerUp":
                d = self._brow(name, s, Xm) if kind == "skin" else zero
            elif name == "cheekPuff":
                m = np.zeros(n)
                for c, r in self.cheeks.values():
                    m = np.maximum(m, _bump(np.linalg.norm(Xm - c, axis=1), 0.6 * r, 1.7 * r))
                d = (m * (1 - lips) * (kind == "skin"))[:, None] * nrm * 0.1 * w
            elif name == "tongueOut":
                d = 0.35 * jo
                if kind == "tongue" and self.tongue is not None:
                    tc, ts = self.tongue.params["c"], self.tongue.params["size"]
                    along = np.clip(((Xm - tc) @ out + ts[1]) / (2 * ts[1]), 0, 1)
                    reach = ((self.M - tc) @ out) - ts[1] + 0.25 * w
                    d = d + (_ss(along) * reach)[:, None] * out - (along ** 2 * 0.25 * reach)[:, None] * up
            else:
                raise SpecError(f"face_shapes: unknown shape {name!r}")
            d = d * (self.amount.get(name, 1.0) * (sneer_still if name.startswith("noseSneer") else still))[:, None]
            res[name] = d
        return res

    def _blink(self, s: str, Xm: np.ndarray, Xn: np.ndarray, ku: float = 1.0, kl: float = 1.0) -> np.ndarray:
        """The upper lid turned down over the eyeball about the eye's own left-right axis (so it slides on the
        ball), the lower lid up a quarter of the way; the corners stay, the skin round the eye follows less.
        ku / kl scale the upper / lower lid's turn (eyeWide: negative, eyeSquint: the lower lid more)."""
        ev = self.eyes[s]
        c, rot, r, ro = ev["c"], ev["rot"], ev["r"], ev["ro"]
        q = (Xm - c) @ rot
        dist = np.linalg.norm(q, axis=1)
        zp = q[:, 2] * r / np.maximum(dist, 1e-9)
        xp = q[:, 0] * r / np.maximum(dist, 1e-9)
        hu, hl, zc = ev["hu"], ev["hl"], ev["zc"]
        zt = hl + 0.25 * (hu - hl)
        th_u = np.arcsin(np.clip(hu / r, -1, 1)) - np.arcsin(np.clip(zt / r, -1, 1))
        th_l = np.arcsin(np.clip(zt / r, -1, 1)) - np.arcsin(np.clip(hl / r, -1, 1))
        upper = _ss((zp - zc) / (0.3 * r) + 0.5)
        lat = _ss(1 - (xp / (1.15 * ev["w"])) ** 2)
        # the lid turns; the skin round it follows the lid's outer surface, taking the move of the point under it on
        # that surface (turning it about the eye's centre instead swung a lever as long as its distance: it tore),
        # fading over most of an eye radius (the low poly is coarse there: a tight fade made facets)
        reach = _ss((dist - 1.01 * r) / (0.05 * r)) * _bump(dist, ro, ro + 1.1 * r) \
            * _bump(q[:, 1], 0.1 * r, 0.6 * r)
        ang = (upper * th_u * ku - (1 - upper) * th_l * kl) * lat * reach
        qn = (Xn - c) @ rot
        dn = np.linalg.norm(qn, axis=1, keepdims=True)
        on = qn * np.minimum(ro / np.maximum(dn, 1e-9), 1.0)  # on the lid's outer sphere (the lid itself: as is)
        moved = _rodrigues(np.array([1.0, 0.0, 0.0]), ang, on) - on
        return moved @ rot.T

    def _brow(self, name: str, s: str | None, Xm: np.ndarray) -> np.ndarray:
        d = np.zeros_like(Xm)
        for side, b in self.brows.items():
            if s is not None and side != s:
                continue
            hb = b["half"]
            # keep the eye itself still: the brow's pull fades over the upper lid
            if name == "browInnerUp":
                m = _bump(np.linalg.norm(Xm - b["inner"], axis=1), 0.5 * hb, 1.5 * hb)
                d += m[:, None] * self.up * 0.09 * self.R
            elif name.startswith("browOuterUp"):
                m = _bump(np.linalg.norm(Xm - b["outer"], axis=1), 0.5 * hb, 1.4 * hb)
                d += m[:, None] * self.up * 0.08 * self.R
            else:  # browDown: down, toward the middle, a little forward
                m = _bump(np.linalg.norm(Xm - b["c"], axis=1), 0.8 * hb, 1.7 * hb)
                toward = -self.side * (1 if side == "Left" else -1)
                d += m[:, None] * (-self.up * 0.06 * self.R + toward * 0.03 * self.R + self.out * 0.015 * self.R)
        for ev in self.eyes.values():
            d *= _ss((np.linalg.norm(Xm - ev["c"], axis=1) - 1.01 * ev["r"]) / (0.05 * ev["r"]))[:, None]
        return d
