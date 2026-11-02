"""Measuring a body BY NAME (garment step 3): the agent names each measurement its garment's seams call for, and how
it is taken; the tape answers each in mm with how it was taken, and draws every tape line on the body.

Why: "we don't know what measurements we need until we see the clothing and discern what seams there are" (Joe,
docs/state/garment_steps.md). tailor.measure takes a fixed FreeSewing list; this module builds on its primitives
(slice_loops, section, girth, arc) and its landmarks, so a FreeSewing name and the same measurement asked by name agree.

`Tape(V, faces, J, hps=None)`: the body, measured once by tailor.measure (its landmarks and levels).
`Tape.landmarks()` -> {name: {"pos", "how", "surface"}}: tailor's landmarks (hps, shoulder point, neck points, bust),
  the torso's centre front / centre back / side at each level (cf_<level>, cb_<level>, side_<level>.L|.R), floor,
  crown, crotch, and every joint (inside the body: straight and vertical measures only). ".R" mirrors ".L".
`Tape.take(item)` -> {"name", "kind", "mm", "how"} (+ the tape line in self.lines[name]); one item is a dict:
  girth   {"at": LEVEL, "square_to": "body"} round the torso, level; or square to a limb ("arm.L", "forearm.L",
          "thigh.L", "shin.L", "neck") at {"t": fraction along it} | {"along": m from its start} | {"at": landmark};
          "fullest" / "narrowest": [LEVEL, LEVEL] (body) or [t0, t1] (limb) searches between. The tape is the convex
          hull of the section (a tape bridges hollows).
  arc     {"from", "to", "over": front|back|top|bottom|left|right}: over the surface, in the plane through both
          points that gives the shortest arc bulging to that side; "taut" (default true) bridges hollows in the plane.
  length  {"from", "to" | "down_to": LEVEL, "via": [...], "over": "surface" (needs surface landmarks) | "straight",
          "side": front|back}: "down_to" is the tailor's tape down the body from a surface point at its x (taut).
  height  {"from", "to"}: vertical, between LEVELs or landmarks ("floor" for the floor).
  freesewing  {"name"} (or the bare name as a string): tailor.measure's value in FreeSewing's definition
          ("consumer", default "freesewing:simon" = brian's base, measure_defs adapters; null: the tape's own).
  LEVEL: a level name (armpit, chest, waist, high_hip, hips, seat, crotch: tailor's definitions), a landmark (its
  height), {"z": m}, {"between": [LEVEL, LEVEL], "t": f}, {"at": LEVEL, "dz": m}.
Refusals (TapeError) name what is wrong and what to say instead. `run` is the MCP tool body (server.body_tape).
"""
from __future__ import annotations

import numpy as np

from . import tailor
from scipy.spatial import ConvexHull

Z = np.array([0.0, 0.0, 1.0])
KINDS = ("girth", "arc", "length", "height", "freesewing")
LIMBS = {"arm": ("shoulder", "elbow"), "forearm": ("elbow", "wrist"), "thigh": ("hip", "knee"), "shin": ("knee", "ankle"),
         "neck": ("neck", "head")}
SIDES = {"front": np.array([0, -1.0, 0]), "back": np.array([0, 1.0, 0]), "top": Z, "bottom": -Z,
         "left": np.array([1.0, 0, 0]), "right": np.array([-1.0, 0, 0])}
LEVELS = {  # level name: (tailor's "at" key, its definition: tailor.measure's docstring)
    "armpit": ("armpit_z", "the highest torso section the arm has left"),
    "chest": ("chest_z", "the fullest torso section 2-12 cm under the armpit"),
    "waist": ("waist_z", "70% of the way from the pelvis joint to the chest joint (skeletal, a belly doesn't move it)"),
    "high_hip": ("high_hip_z", "the iliac crest: 0.125 x stature above the crotch (ANSUR II iliocristale)"),
    "hips": ("hips_z", "the hip joints + 2 cm (the greater trochanter; FreeSewing's hips is the high_hip)"),
    "seat": ("seat_z", "the fullest torso section in the 12 cm under the hips level"),
    "crotch": ("crotch_z", "the highest level where the body's section splits into two legs"),
}
TAILOR = {  # tailor's own landmarks: (our name, tailor's "at" key, how it is found)
    "hps.L": ("hps.L", "high point of shoulder: the outermost point of the neck loop (square to the neck, 2 cm up it)"),
    "shoulder_point.L": ("shoulder.L", "shoulder point: where the top of the shoulder turns down into the arm (the "
                         "acromion's edge, scanned out from the shoulder joint)"),
    "neck_side.L": ("neck_side.L", "the neck loop's widest point"),
    "cf_neck": ("cf_neck", "the neck loop's centre front"),
    "cb_neck": ("cb_neck", "the neck loop's centre back (the nape)"),
    "bust.L": ("bust.L", "bust point: the front of the chest section 9.5 cm out from the centre"),
}
SURFACE_TOL = 0.02  # m: a section through a landmark passes this near it


class TapeError(ValueError):
    """A measurement the tape can't take as asked: says what is wrong and what to ask instead."""


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def _taut(P: np.ndarray, out: np.ndarray) -> np.ndarray:
    """A tape pulled taut over the ordered points P that bulge toward `out` (in their plane): it bridges hollows (the
    points under the line between their neighbours are dropped)."""
    if len(P) < 3:
        return P
    e = _unit(P[-1] - P[0])
    o = out - (out @ e) * e
    if np.linalg.norm(o) < 1e-9:
        return P
    o = _unit(o)
    q = np.c_[(P - P[0]) @ e, (P - P[0]) @ o]
    keep = [0]
    for i in range(1, len(q)):
        while len(keep) >= 2:
            a, b = q[keep[-2]], q[keep[-1]]
            if (b[0] - a[0]) * (q[i][1] - a[1]) - (b[1] - a[1]) * (q[i][0] - a[0]) >= 0:
                keep.pop()  # b lies under the line a -> P[i]: the tape lifts off it
            else:
                break
        keep.append(i)
    return P[keep]


class Tape:
    def __init__(self, V, faces, J: dict, hps: str | None = None):
        self.V = np.asarray(V, float)
        self.T = tailor.triangles(faces) if not isinstance(faces, np.ndarray) or faces.shape[1] != 3 else faces
        self.J = {k: np.asarray(v, float) for k, v in J.items()}
        self.R = tailor.measure(self.V, faces, self.J, hps=hps)
        self.zmin, self.zmax = float(self.V[:, 2].min()), float(self.V[:, 2].max())
        self.lines: dict = {}
        self._lm = None

    # ------------------------------------------------------------------ landmarks and levels
    def axis_at(self, z):
        P = [self.J[k] for k in ("pelvis", "chest", "neck")]
        return np.array([0.0, float(np.interp(z, [p[2] for p in P], [p[1] for p in P])), z])

    def torso(self, z):
        return tailor.section(self.V, self.T, self.axis_at(z), Z, self.axis_at(z))

    def landmarks(self) -> dict:
        if self._lm is not None:
            return self._lm
        at, lm = self.R["at"], {}
        for nm, (k, how) in TAILOR.items():
            if k in at:
                lm[nm] = {"pos": np.asarray(at[k], float), "how": how, "surface": True}
        for lv, (k, d) in LEVELS.items():
            if k not in at or lv == "crotch":
                continue
            L = self.torso(float(at[k]))
            if L is None:
                continue
            mid = L[np.abs(L[:, 0]) < 0.02]
            mid = mid if len(mid) else L
            for nm, p, w in ((f"cf_{lv}", mid[np.argmin(mid[:, 1])], "centre front"),
                             (f"cb_{lv}", mid[np.argmax(mid[:, 1])], "centre back"),
                             (f"side_{lv}.L", L[np.argmax(L[:, 0])], "outermost point (+X, the body's left)")):
                lm[nm] = {"pos": p, "how": f"{w} of the torso section at the {lv} level ({d})", "surface": True}
        for nm in [k for k in lm if k.endswith(".L")]:
            lm[nm[:-2] + ".R"] = dict(lm[nm], pos=lm[nm]["pos"] * [-1, 1, 1], how=lm[nm]["how"] + "; mirrored")
        if "crotch_z" in at:
            cy = float(np.mean(self.R["loops"]["seat"][:, 1])) if "seat" in self.R["loops"] else 0.0
            lm["crotch"] = {"pos": np.array([0.0, cy, float(at["crotch_z"])]), "surface": False,
                            "how": "the crotch level at the centre line (" + LEVELS["crotch"][1] + ")"}
        cy = float(np.mean(self.V[:, 1]))
        lm["floor"] = {"pos": np.array([0.0, cy, self.zmin]), "how": "the floor: the body's lowest point", "surface": False}
        lm["crown"] = {"pos": self.V[np.argmax(self.V[:, 2])], "how": "the top of the head", "surface": True}
        for k, p in self.J.items():
            lm["joint:" + k] = {"pos": p, "how": "a joint (inside the body)", "surface": False}
            lm.setdefault(k, lm["joint:" + k])  # (bare joint names too, where no landmark has the name)
        self._lm = lm
        return lm

    def point(self, name, need_surface=False) -> np.ndarray:
        lm = self.landmarks()
        if not isinstance(name, str) or name not in lm:
            own = [k for k in lm if not k.startswith("joint:") and k not in self.J]
            raise TapeError(f"unknown landmark {name!r}: landmarks are {', '.join(own)}; joints by name "
                            f"({', '.join(k for k in self.J if not k.startswith(('finger', 'thumb', 'lm_')))}, ...)")
        if need_surface and not lm[name]["surface"]:
            raise TapeError(f"{name!r} is {lm[name]['how']}, not on the surface: over the surface needs surface "
                            f"landmarks (e.g. shoulder_point.L, cb_waist), or say over=\"straight\"")
        return np.asarray(lm[name]["pos"], float)

    def level(self, spec) -> tuple[float, str]:
        at = self.R["at"]
        if isinstance(spec, str):
            if spec in LEVELS:
                k, d = LEVELS[spec]
                if k not in at:
                    raise TapeError(f"level {spec!r}: the tape couldn't find it on this body")
                z, how = float(at[k]), f"the {spec} level ({d})"
            else:
                try:
                    z, how = float(self.point(spec)[2]), f"{spec}'s height"
                except TapeError as e:
                    raise TapeError(f"unknown level {spec!r}: a level name ({', '.join(LEVELS)}), a landmark, "
                                    "{\"z\": m}, {\"between\": [a, b], \"t\": f} or {\"at\": a, \"dz\": m}. " + str(e)) from None
        elif isinstance(spec, dict) and "z" in spec:
            z, how = float(spec["z"]), f"z {float(spec['z']):.3f} m"
        elif isinstance(spec, dict) and "between" in spec:
            (za, ha), (zb, hb) = (self.level(s) for s in spec["between"])
            t = float(spec.get("t", 0.5))
            z, how = za + t * (zb - za), f"{t:g} of the way from {ha} to {hb}"
        elif isinstance(spec, dict) and "at" in spec:
            z0, h0 = self.level(spec["at"])
            dz = float(spec.get("dz", 0.0))
            z, how = z0 + dz, f"{h0} {'+' if dz >= 0 else '-'} {abs(dz) * 1000:.0f} mm"
        else:
            raise TapeError(f"level {spec!r}: a level name ({', '.join(LEVELS)}), a landmark, {{\"z\": m}}, "
                            "{\"between\": [a, b], \"t\": f} or {\"at\": a, \"dz\": m}")
        if not self.zmin <= z <= self.zmax:
            raise TapeError(f"level {spec!r} is at z {z:.3f} m, outside the body (floor {self.zmin:.3f} .. crown "
                            f"{self.zmax:.3f} m)")
        return z, how

    # ------------------------------------------------------------------ the kinds
    def _girth(self, it: dict) -> tuple[float, str, np.ndarray]:
        sq = it.get("square_to", "body")
        search = "fullest" if "fullest" in it else "narrowest" if "narrowest" in it else None
        if sq == "body":
            if search:
                (za, ha), (zb, hb) = (self.level(s) for s in it[search])
                cands = [(tailor.girth(L, Z), z, L) for z in np.linspace(za, zb, 25) if (L := self.torso(z)) is not None]
                if not cands:
                    raise TapeError(f"no torso section between {ha} and {hb}")
                g, z, L = (max if search == "fullest" else min)(cands, key=lambda c: c[0])
                how = f"the {search} torso section between {ha} and {hb} (at z {z:.3f} m)"
            else:
                if "at" not in it:
                    raise TapeError("girth: say where: \"at\": a LEVEL (or \"fullest\" / \"narrowest\": [LEVEL, LEVEL])")
                z, how = self.level(it["at"])
                L = self.torso(z)
                if L is None:
                    raise TapeError(f"girth at {how}: no torso section there")
                g = tailor.girth(L, Z)
            return g, f"round the torso, level, at {how}; the tape is the section's convex hull (bridges hollows)", \
                self._hull(L, Z)
        limb, _, side = str(sq).partition(".")
        if limb not in LIMBS:
            raise TapeError(f"square_to {sq!r}: \"body\" or a limb: {', '.join(k + '.L' for k in LIMBS if k != 'neck')} "
                            "(or .R), \"neck\"")
        ja, jb = (j + (f".{side}" if side and j not in ("neck", "head") else "") for j in LIMBS[limb])
        if ja not in self.J or jb not in self.J:
            raise TapeError(f"square_to {sq!r}: needs the joints {ja} and {jb} (have {', '.join(sorted(self.J))[:200]})")
        a, b = self.J[ja], self.J[jb]
        n, ln = _unit(b - a), float(np.linalg.norm(b - a))
        r = max(0.4 * ln, 0.12)

        def sec(t):
            p = a + t * (b - a)
            L = tailor.section(self.V, self.T, p, n, p)
            ok = L is not None and np.max(np.linalg.norm(L - p, axis=1)) < r
            return L if ok else None
        if search:
            t0, t1 = (float(x) for x in it[search])
            cands = [(tailor.girth(L, n), t, L) for t in np.linspace(t0, t1, 21) if (L := sec(t)) is not None]
            if not cands:
                raise TapeError(f"every section of the {sq} between t {t0} and {t1} runs into the body (arms against it?)")
            g, t, L = (max if search == "fullest" else min)(cands, key=lambda c: c[0])
            how = f"the {search} section of the {sq} between {t0:g} and {t1:g} of {ja} -> {jb} (at {t:.2f})"
        else:
            if "t" in it:
                t = float(it["t"])
            elif "along" in it:
                t = float(it["along"]) / ln
            elif "at" in it:
                t = float((self.point(it["at"]) - a) @ n) / ln
            else:
                raise TapeError(f"girth square to {sq}: say where: \"t\" (0 at {ja}, 1 at {jb}), \"along\" (m from "
                                f"{ja}), \"at\" (a landmark), or \"fullest\" / \"narrowest\": [t0, t1]")
            L = sec(t)
            if L is None:
                raise TapeError(f"girth square to {sq} at t {t:.2f}: no section there, or it runs into the body")
            g, how = tailor.girth(L, n), f"{t:.2f} of the way from {ja} to {jb}"
        return g, f"round the {sq}, square to it, at {how}; convex hull", self._hull(L, n)

    @staticmethod
    def _hull(L, n):
        u, v = tailor._frame(n)
        h = ConvexHull(np.c_[L @ u, L @ v]).vertices
        return np.r_[L[h], L[h[:1]]]

    def _arc(self, a, b, over: str, taut: bool = True) -> np.ndarray:
        """The shortest surface arc a -> b in a plane through both that bulges toward `over`."""
        if over not in SIDES:
            raise TapeError(f"over {over!r}: one of {', '.join(SIDES)}")
        d = SIDES[over]
        e = _unit(b - a)
        ref = Z if abs(e[2]) < 0.7 else np.array([1.0, 0, 0])
        n0 = _unit(ref - (ref @ e) * e)
        w = np.cross(e, n0)
        best = None
        for th in np.radians(np.arange(-82.5, 90.0, 7.5)):
            n = np.cos(th) * n0 + np.sin(th) * w
            loops = [L for L in tailor.slice_loops(self.V, self.T, a, n)
                     if np.min(np.linalg.norm(L - a, axis=1)) < SURFACE_TOL and np.min(np.linalg.norm(L - b, axis=1)) < SURFACE_TOL]
            for L in loops:
                ia, ib = (int(np.argmin(np.linalg.norm(L - p, axis=1))) for p in (a, b))
                m = len(L)
                halves = [L[[(ia + k) % m for k in range((ib - ia) % m + 1)]],
                          L[[(ib + k) % m for k in range((ia - ib) % m + 1)][::-1]]]
                # the half further toward `over` (as tailor.arc), and only if it bulges that way at all
                reach = [float(np.max((H - (a + b) / 2) @ d)) for H in halves]
                P = halves[int(np.argmax(reach))]
                if max(reach) < 0.02:
                    continue
                bu = (P - (a + b) / 2)[np.argmax((P - (a + b) / 2) @ d)]
                if taut:
                    P = _taut(P, bu)
                if best is None or tailor.length(P) < tailor.length(best):
                    best = P
        if best is None:
            raise TapeError(f"no surface arc from {np.round(a, 3).tolist()} to {np.round(b, 3).tolist()} over the {over}: "
                            "try another side (front, back, top, left, right) or over=\"straight\"")
        return best

    def _down(self, start, z1: float, sign: int) -> np.ndarray:
        """tailor's tape down the back (sign +1) or front (-1) from a surface point to height z1, taut."""
        pts = [start]
        for z in np.arange(start[2] - 0.01, z1 - 1e-6, -0.01):
            L = self.torso(z)
            if L is None:
                continue
            near = L[np.abs(L[:, 0] - start[0]) < 0.015]
            if len(near):
                pts.append(near[np.argmax(sign * near[:, 1])])
        P = np.array(pts)
        if len(P) >= 3:  # (tailor.measure's down(): the same taut rule, in the y-z profile)
            q = np.c_[-P[:, 2], sign * P[:, 1]]
            keep = [0]
            for i in range(1, len(q)):
                while len(keep) >= 2:
                    a_, b_ = q[keep[-2]], q[keep[-1]]
                    if (b_[0] - a_[0]) * (q[i][1] - a_[1]) - (b_[1] - a_[1]) * (q[i][0] - a_[0]) >= 0:
                        keep.pop()
                    else:
                        break
                keep.append(i)
            P = P[keep]
        return P

    def _length(self, it: dict) -> tuple[float, str, np.ndarray]:
        if "from" not in it:
            raise TapeError("length: say \"from\" (a landmark) and \"to\" (a landmark) or \"down_to\" (a LEVEL)")
        over = it.get("over", "surface")
        if over not in ("surface", "straight"):
            raise TapeError(f"length over {over!r}: \"surface\" or \"straight\"")
        if "down_to" in it:
            side = it.get("side", "back")
            if side not in ("front", "back"):
                raise TapeError(f"down_to side {side!r}: \"front\" or \"back\"")
            a = self.point(it["from"], need_surface=True)
            z1, how = self.level(it["down_to"])
            if z1 >= a[2]:
                raise TapeError(f"down_to {how} (z {z1:.3f}) is not below {it['from']} (z {a[2]:.3f})")
            P = self._down(a, z1, 1 if side == "back" else -1)
            return tailor.length(P), (f"a tape down the {side} from {it['from']} to {how}, at {it['from']}'s x, taut "
                                      "(bridges the hollows)"), P
        if "to" not in it:
            raise TapeError("length: say \"to\" (a landmark) or \"down_to\" (a LEVEL)")
        names = [it["from"], *it.get("via", []), it["to"]]
        pts = [self.point(nm, need_surface=over == "surface") for nm in names]
        if over == "straight":
            P = np.array(pts)
            return tailor.length(P), "straight lines " + " -> ".join(names), P
        side = it.get("side", "front")
        P = np.concatenate([self._arc(p, q, side, it.get("taut", True)) for p, q in zip(pts, pts[1:])])
        return tailor.length(P), f"over the surface ({side} side), taut, " + " -> ".join(names), P

    def take(self, it) -> dict:
        if isinstance(it, str):
            it = {"name": it, "kind": "freesewing"}
        if not isinstance(it, dict) or not it.get("name"):
            raise TapeError(f"{it!r}: each measurement is a dict with a \"name\" and a \"kind\" ({', '.join(KINDS)}), "
                            "or a FreeSewing name as a string")
        nm, kind = it["name"], it.get("kind", "freesewing")
        if kind == "girth":
            v, how, P = self._girth(it)
        elif kind == "arc":
            if "from" not in it or "to" not in it:
                raise TapeError("arc: say \"from\" and \"to\" (surface landmarks) and \"over\" (front, back, top, ...)")
            a, b = self.point(it["from"], True), self.point(it["to"], True)
            P = self._arc(a, b, it.get("over", "front"), it.get("taut", True))
            v = tailor.length(P)
            how = (f"over the surface from {it['from']} to {it['to']} round the {it.get('over', 'front')}, the shortest "
                   f"plane arc{', taut' if it.get('taut', True) else ''}")
        elif kind == "length":
            v, how, P = self._length(it)
        elif kind == "height":
            if "from" not in it or "to" not in it:
                raise TapeError("height: say \"from\" and \"to\" (LEVELs or landmarks; \"floor\" for the floor)")
            (za, ha), (zb, hb) = self.level(it["from"]), self.level(it["to"])
            v, how = abs(za - zb), f"vertical from {ha} to {hb}"
            lm = self.landmarks()  # (drawn at the "from" landmark, else beside the waist)
            x, y = (lm[it["from"]]["pos"][:2] if isinstance(it["from"], str) and it["from"] in lm and lm[it["from"]]["surface"]
                    else (float(lm["side_waist.L"]["pos"][0]) + 0.06 if "side_waist.L" in lm else 0.25, 0.0))
            P = np.array([[x, y, za], [x, y, zb]])
        elif kind == "freesewing":
            return self._freesewing(nm, it)
        else:
            raise TapeError(f"{nm}: kind {kind!r}: one of {', '.join(KINDS)}")
        self.lines[nm] = P
        return {"name": nm, "kind": kind, "mm": round(v * 1000.0, 1), "how": how}

    def _freesewing(self, nm: str, it: dict) -> dict:
        from . import measure_defs as md
        fs = it.get("measure", nm)
        mm = self.R["mm"]
        if fs not in mm:
            raise TapeError(f"{fs!r} is not a FreeSewing measurement the tape takes: {', '.join(sorted(mm))}; or define "
                            f"it by kind ({', '.join(k for k in KINDS if k != 'freesewing')})")
        consumer = it.get("consumer", "freesewing:simon")
        vals, info = md.for_consumer(consumer, {k: float(v) for k, v in mm.items()}, self.R["at"])
        v = vals.get(fs, mm[fs])
        how = f"tailor.measure's {fs} (its docstring)"
        if fs in (info.get("definitions") or {}):
            how += f", in {consumer}'s definition (measure_defs adapter {info['definitions'][fs][0]}; the tape's own: {mm[fs]})"
        loop = self.R["loops"].get({"shoulderToShoulder": "shoulders"}.get(fs, fs))
        if loop is not None and fs in ("chest", "waist", "hips", "seat", "neck", "biceps", "wrist"):
            loop = np.r_[loop, loop[:1]]
        if loop is not None:
            self.lines[nm] = np.asarray(loop, float)
        unit = "deg" if fs == "shoulderSlope" else "mm"
        return {"name": nm, "kind": "freesewing", unit: round(float(v), 2 if unit == "deg" else 1), "how": how}


# ---------------------------------------------------------------------- the look: the tape lines on the body
VIEWS = (("front", lambda P: P[:, 0], lambda P: P[:, 1]),  # (name, image x, depth: smaller is nearer the viewer)
         ("side", lambda P: P[:, 1], lambda P: -P[:, 0]),  # (from the body's left, its front to the left)
         ("back", lambda P: -P[:, 0], lambda P: -P[:, 1]))
COLOURS = [(220, 40, 40), (30, 110, 220), (20, 150, 60), (200, 110, 0), (150, 50, 190), (0, 150, 160), (200, 30, 130),
           (110, 110, 0), (90, 60, 30), (60, 60, 200)]


def _dense(P: np.ndarray, step: float = 0.005) -> np.ndarray:
    """The polyline resampled every `step` m (its visibility is judged point by point)."""
    out = [P[:1]]
    for a, b in zip(P[:-1], P[1:]):
        k = max(int(np.linalg.norm(b - a) / step), 1)
        out.append(a + np.outer(np.arange(1, k + 1) / k, b - a))
    return np.concatenate(out)


def draw(tape: Tape, rows: list, path, h: int = 760) -> str:
    """Front / side / back: the body in clay, each row's tape line in its colour (solid where seen, thin where behind
    the body), numbered at the line; the legend names each row with its value."""
    from PIL import Image, ImageDraw
    V, T = tape.V, tape.T
    zmin, zmax = tape.zmin, tape.zmax
    s = (h - 40) / (zmax - zmin)
    w = int(0.62 * h)
    tiles = []
    drawn = [r for r in rows if r["name"] in tape.lines]
    for vname, fx, fd in VIEWS:
        im = Image.new("RGB", (w, h), (250, 250, 248))
        dr = ImageDraw.Draw(im)
        X = fx(V)
        cx = 0.5 * (X.min() + X.max())
        ix = lambda P: w / 2 + (fx(P) - cx) * s  # noqa: E731
        iy = lambda P: h - 20 - (P[:, 2] - zmin) * s  # noqa: E731
        px, py, D = ix(V), iy(V), fd(V)
        tri = np.stack([px[T], py[T]], axis=-1)
        nrm = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
        view = {"front": np.array([0, -1.0, 0]), "side": np.array([1.0, 0, 0]), "back": np.array([0, 1.0, 0])}[vname]
        light = _unit(view + np.array([0.3, 0, 0.5]))
        shade = np.clip(np.abs(nrm @ light), 0, 1)
        for k in np.argsort(-D[T].mean(axis=1)):  # far to near
            g = int(120 + 110 * shade[k])
            dr.polygon([tuple(p) for p in tri[k]], fill=(g, g - 4, g - 10))
        # a coarse depth buffer from the vertices: a tape point is seen where nothing nearer covers it
        cell = 4
        zb = np.full((h // cell + 2, w // cell + 2), np.inf)
        gi, gj = np.clip((py / cell).astype(int), 0, zb.shape[0] - 1), np.clip((px / cell).astype(int), 0, zb.shape[1] - 1)
        np.minimum.at(zb, (gi, gj), D)
        for n, r in enumerate(drawn):
            P = _dense(tape.lines[r["name"]])
            col = COLOURS[n % len(COLOURS)]
            qx, qy, qd = ix(P), iy(P), fd(P)
            i_, j_ = np.clip((qy / cell).astype(int), 1, zb.shape[0] - 2), np.clip((qx / cell).astype(int), 1, zb.shape[1] - 2)
            near = np.min([zb[i_ + a, j_ + b] for a in (-1, 0, 1) for b in (-1, 0, 1)], axis=0)
            seen = qd <= near + 0.012
            for k in range(len(P) - 1):
                both = seen[k] and seen[k + 1]
                dr.line([(qx[k], qy[k]), (qx[k + 1], qy[k + 1])], fill=col if both else tuple(int(c * 0.4 + 150) for c in col),
                        width=4 if both else 1)
            vis = np.where(seen)[0]
            if len(vis):
                k = vis[np.argmax(qx[vis])] if r["kind"] in ("girth", "freesewing") and len(P) > 8 else vis[len(vis) // 2]
                dr.ellipse([qx[k] + 3, qy[k] - 8, qx[k] + 19, qy[k] + 8], fill=(255, 255, 255), outline=col, width=2)
                dr.text((qx[k] + 8, qy[k] - 6), str(n + 1), fill=col)
        dr.text((8, 6), vname, fill=(40, 40, 40))
        tiles.append(im)
    lw = 360
    leg = Image.new("RGB", (lw, h), (255, 255, 255))
    dl = ImageDraw.Draw(leg)
    dl.text((10, 8), "body_tape (mm)", fill=(0, 0, 0))
    for n, r in enumerate(drawn):
        col = COLOURS[n % len(COLOURS)]
        y = 32 + 20 * n
        dl.rectangle([10, y + 2, 26, y + 12], fill=col)
        val = f"{r['mm']:.1f}" if "mm" in r else f"{r.get('deg')} deg"
        dl.text((32, y), f"{n + 1}. {r['name']}  {val}", fill=(0, 0, 0))
    off = [r["name"] for r in rows if r["name"] not in tape.lines]
    if off:
        dl.text((10, 40 + 20 * len(drawn)), "not drawn: " + ", ".join(off)[:52], fill=(90, 90, 90))
    out = Image.new("RGB", (3 * w + lw + 12, h), (255, 255, 255))
    for i, t in enumerate(tiles):
        out.paste(t, (i * (w + 4), 0))
    out.paste(leg, (3 * w + 12, 0))
    out.save(path)
    return str(path)


# ---------------------------------------------------------------------- the tool
def landmark_text(tape: Tape) -> str:
    lm = tape.landmarks()
    rows = [f"  {k}: [{', '.join(f'{c:.3f}' for c in v['pos'])}] {v['how']}" for k, v in lm.items()
            if not k.startswith("joint:") and (k not in tape.J)]
    lv = [f"  {k}: z {tape.R['at'][a]:.3f} m: {d}" for k, (a, d) in LEVELS.items() if a in tape.R["at"]]
    js = ", ".join(k for k in tape.J if not k.startswith(("finger", "thumb", "lm_")))
    return ("landmarks (m; .R mirror .L):\n" + "\n".join(rows) + "\nlevels:\n" + "\n".join(lv) +
            f"\n  floor z {tape.zmin:.3f}, crown z {tape.zmax:.3f}\njoints (inside the body; \"joint:<name>\" too): {js}")


def run(name: str, measurements: list | None = None, garment: str = "", landmarks: bool = False) -> tuple[str | None, str]:
    """The MCP tool body: (look path or None, the answer)."""
    from . import cloth, store
    spec = store.load(name)
    if not spec.get("base"):
        raise TapeError(f"{name!r} has no base body to measure (body_tape measures a model's base human)")
    b = cloth.model_body(name, spec, {})
    tape = Tape(b["V"], b["F"], b["J"], hps=b.get("hps"))
    if landmarks or not measurements:
        txt = landmark_text(tape)
        if not measurements:
            return None, txt + "\nnext: body_tape(name, measurements=[...]) by name; kinds: guide(topic=\"body_tape\")"
    rows, errs = [], []
    for it in measurements:
        try:
            rows.append(tape.take(it))
        except TapeError as e:
            errs.append(f"  REFUSED {it.get('name', it) if isinstance(it, dict) else it}: {e}")
    if errs and not rows:
        raise TapeError("\n".join(errs))
    d = store._dir(name) / "tape"
    if garment:
        from . import garment_record as gr
        d = gr.look_dir(name, garment)
    d.mkdir(parents=True, exist_ok=True)
    look = draw(tape, rows, d / "step3_measure.png")
    out = [f"{r['name']}: {r['mm'] if 'mm' in r else r['deg']} {'mm' if 'mm' in r else 'deg'} ({r['kind']}): {r['how']}"
           for r in rows]
    txt = "\n".join(out + errs) + f"\nlook: {look}"
    if landmarks:
        txt = landmark_text(tape) + "\n" + txt
    if garment:
        from . import garment_record as gr
        try:
            gr.write(name, garment, "3", "done", output={"body": name, "measurements": rows,
                                                         "refused": [e.strip() for e in errs]}, look=[look], by="body_tape")
            txt += f"\nrecord: step 3 (measure) written: {gr.path(name, garment)}"
        except gr.OrderRefused as e:
            txt += f"\nrecord: refused: {e}"
    return look, txt + "\nnext: judge the look (each tape where the garment's seam needs it); a missing one: add it by name"
