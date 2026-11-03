"""The model's body for step 0's fit (garment_fit.py): girth, width across the view and height at each landmark, the
distance along a limb, and a section anywhere: TapeBody (the model's own, through body_tape) and DictBody (tests)."""
from __future__ import annotations

import numpy as np

from .garment_fit import LANDMARKS, SIDE_VIEWS, FitRefused

ALIAS = {"shoulder": "shoulder_point.L", "eyes": "eye.L"}  # (a height-only landmark: the tape's point of that name)


class DictBody:
    """A body given as numbers {landmark: {girth_mm, width_mm, z_mm}} (tests; a body with no mesh)."""

    def __init__(self, d: dict):
        self.d = d
        self.mesh = None

    def at(self, lm, view="front"):
        if lm not in self.d:
            raise FitRefused(f"the body has no {lm!r}")
        return self.d[lm]

    # (tests: limbs read straight down, distance along = drop in height from the limb's top landmark)
    def along(self, part, lm, view="front"):
        return 2000.0 - self.at(lm, view)["z_mm"]

    def limb_length(self, part):
        return 2000.0

    def point_along(self, part, s_mm):
        return {"z_mm": 2000.0 - s_mm, "bone": None, "t": None}

    def section_on(self, bone, where, view="front"):
        return self.at_z(None, where if bone == "body" else where, view)

    def at_z(self, near, z_mm: float, view="front"):
        """The section at a height: interpolated between the two numbered landmarks either side (tests)."""
        pts = sorted((e["z_mm"], e) for e in self.d.values() if e.get("girth_mm"))
        lo = max((p for p in pts if p[0] <= z_mm), default=pts[0], key=lambda p: p[0])
        hi = min((p for p in pts if p[0] >= z_mm), default=pts[-1], key=lambda p: p[0])
        f = 0.0 if hi[0] == lo[0] else (z_mm - lo[0]) / (hi[0] - lo[0])
        return {k: lo[1][k] + f * (hi[1][k] - lo[1][k]) for k in ("girth_mm", "width_mm")} | {"z_mm": z_mm}


class TapeBody:
    """The model's own body through body_tape: girth, width across the view and height (mm above the floor)."""

    def __init__(self, tape):
        self.tape, self._c, self._p3 = tape, {}, {}
        self.mesh = (tape.V, tape.T)

    def at(self, lm, view="front"):
        key = (lm, view)
        if key not in self._c:
            item, _ = LANDMARKS[lm]
            t = self.tape
            if item is None:
                z = {"floor": t.zmin, "crown": t.zmax}.get(lm)
                z = t.level(ALIAS.get(lm, lm))[0] if z is None else z
                self._c[key] = {"girth_mm": 0.0, "width_mm": 0.0, "z_mm": (z - t.zmin) * 1000, "centre": None, "dir": None}
            else:
                self._c[key] = self._section(item, lm, view)
                self._p3[key] = self._c[key].pop("p3")
        return self._c[key]

    def _chain(self, part):
        from .garment_fit_heights import CHAINS
        segs, s0 = [], 0.0
        for bone, ja, jb in CHAINS[part]:
            a, b = (np.asarray(self.tape.J[f"{j}.L"], float) for j in (ja, jb))
            ln = float(np.linalg.norm(b - a))
            segs.append((bone, a, b, ln, s0))
            s0 += ln
        return segs

    def limb_length(self, part):
        return sum(sg[3] for sg in self._chain(part)) * 1000

    def along(self, part, lm, view="front"):
        """mm along the limb (hip -> knee -> ankle, shoulder -> elbow -> wrist) to the landmark's own place."""
        t = self.tape
        item, _ = LANDMARKS[lm]
        if item is None:
            q = np.asarray(t.point(ALIAS[lm]), float) if lm in ALIAS else \
                np.r_[t.J["hip.L"][:2], t.zmin + self.at(lm, view)["z_mm"] / 1000]
        else:
            self.at(lm, view)
            q = np.asarray(self._p3[(lm, view)], float)
        best = None
        for bone, a, b, ln, s0 in self._chain(part):
            u = float(np.clip((q - a) @ (b - a) / (ln * ln), 0.0, 1.0))
            d = float(np.linalg.norm(a + u * (b - a) - q))
            if best is None or d < best[0]:
                best = (d, (s0 + u * ln) * 1000)
        return best[1]

    def point_along(self, part, s_mm):
        """The limb's axis point s_mm along it: its height (mm above the floor), the bone and the fraction along it."""
        s = s_mm / 1000
        segs = self._chain(part)
        for bone, a, b, ln, s0 in segs:
            if s <= s0 + ln or (bone, a, b, ln, s0) == segs[-1]:
                u = float(np.clip((s - s0) / ln, 0.0, 1.0))
                return {"z_mm": round(float((a + u * (b - a))[2] - self.tape.zmin) * 1000, 1), "bone": bone,
                        "t": round(u, 3), "s_mm": round(s_mm, 1)}

    def section_on(self, bone, where, view="front"):
        """A section across a bone at a fraction along it, or (bone "body") the torso level at a height in mm."""
        key = (bone, round(float(where), 3), view)
        if key not in self._c:
            it = {"square_to": "body", "at": {"z": self.tape.zmin + where / 1000}} if bone == "body" else \
                {"square_to": f"{bone}.L", "t": float(np.clip(where, 0.02, 0.97))}
            self._c[key] = self._section(it, f"{bone}@{where:.3f}", view)
        return self._c[key]

    def _section(self, item, name, view):
        from . import body_tape as bt
        t = self.tape
        m = t.take(dict(item, name=f"fit:{name}", kind="girth"))
        L = np.asarray(t.lines[f"fit:{name}"], float)
        sq = item["square_to"]
        if sq == "body":
            n = np.array([0.0, 0.0, 1.0])
        else:
            limb, _, side = sq.partition(".")
            ja, jb = (j + (f".{side}" if side and j not in ("neck", "head") else "") for j in bt.LIMBS[limb])
            n = t.J[jb] - t.J[ja]
        ax = (0, 2) if view not in SIDE_VIEWS else (1, 2)  # (the view's plane: across, up)
        n2 = np.array([n[ax[0]], n[ax[1]]])
        n2 = n2 / (np.linalg.norm(n2) or 1.0)
        d = np.array([n2[1], -n2[0]])  # (across the limb in the view)
        P = L[:, ax]
        return {"p3": L.mean(0).tolist(), "girth_mm": m["mm"], "width_mm": float(np.ptp(P @ d)) * 1000,
                "z_mm": (float(L[:, 2].mean()) - t.zmin) * 1000, "centre": P.mean(0).tolist(), "dir": d.tolist()}


_BODIES: dict = {}


def body_for(model: str):
    """The model's base body as a TapeBody (garment_plan step 0 applies the fit's ratios to it). The body mesh is kept
    on disk by its base's content (building it is ~20 s; a step-0 call must answer in seconds), the tape in process."""
    import hashlib
    import json
    from . import body_tape as bt, cloth, store
    spec = store.load(model)
    if not spec.get("base"):
        return None
    key = hashlib.sha1(json.dumps(spec["base"], sort_keys=True, default=str).encode()).hexdigest()[:16]
    if (model, key) in _BODIES:
        return _BODIES[(model, key)]
    f = store._dir(model) / "tape" / f"fit_body_{key}.npz"
    try:
        z = np.load(f, allow_pickle=False)
        V, T, J = z["V"], z["T"], {k[2:]: z[k] for k in z.files if k.startswith("J:")}
        hps = str(z["hps"]) or None
    except (OSError, KeyError, ValueError):
        b = cloth.model_body(model, spec, {})
        tape = bt.Tape(b["V"], b["F"], b["J"], hps=b.get("hps"))
        V, T, J, hps = tape.V, np.asarray(tape.T), tape.J, b.get("hps")
        f.parent.mkdir(parents=True, exist_ok=True)
        np.savez(f, V=V, T=T, hps=np.array(hps or ""), **{"J:" + k: v for k, v in J.items()})
    _BODIES[(model, key)] = body = TapeBody(bt.Tape(V, T, J, hps=hps))
    return body


