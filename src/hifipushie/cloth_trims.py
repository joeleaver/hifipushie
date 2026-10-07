"""Trims: small hard things that ride on a finished garment and are not cloth for the solver (a belt through its loops
with a buckle; belt loops). Garment / design key `trims`:

  {"kind": "belt", "on": piece (default the piece of role waistband), "width": m (0.032), "thickness": m (0.0035),
   "color": "#1b1a19", "buckle": true | false, "buckle_color": "#8a8a88", "name"}
  {"kind": "belt_loops", "on": piece, "count": 7, "width": m (0.01), "stand": m (how far a loop stands off the band:
   default a belt's thickness + 1.5 mm when the garment has a belt, else 1 mm), "color" (default the garment's)}

What a trim is here: geometry built AFTER the sim on the piece it rides (`meshes`): a strap lying on a made band
follows that band exactly, as a leather belt on an interfaced waistband does, so there is nothing for a solver to find.
It is in looks (cloth.look) and reports; it is not in the sim, the scene or the export yet. Artists do the same: belts,
buckles and loops are modelled on the simulated trousers, not simulated.

Loop positions (men's trousers, 7): centre back, two on the back between CB and the side seams, two just behind the
side seams... here: spread along the band between its two ends, the first and last `inset` (default 7 cm) from the
opening, one at the middle (the centre back of a band opening at the front).
"""
from __future__ import annotations

import numpy as np

KINDS = ("belt", "belt_loops")
KEYS = {"kind", "on", "name", "width", "thickness", "color", "buckle", "buckle_color", "count", "stand", "inset", "lift"}


class TrimError(ValueError):
    pass


def validate(trims, where: str = "trims") -> None:
    if not isinstance(trims, list):
        raise TrimError(f"{where}: a list of trims ({{kind, on, ...}}; kinds {', '.join(KINDS)})")
    for t in trims:
        if not isinstance(t, dict) or t.get("kind") not in KINDS:
            raise TrimError(f"{where}: each trim needs a kind, one of {', '.join(KINDS)}")
        bad = set(t) - KEYS
        if bad:
            raise TrimError(f"{where} {t['kind']}: unknown keys {sorted(bad)} (have {sorted(KEYS)})")


def _on(t: dict, pcs: dict) -> str | None:
    if t.get("on"):
        return t["on"] if t["on"] in pcs else None
    return next((n for n, pc in pcs.items() if (pc.get("role") or n) == "waistband"), None)


def check(trims: list, pcs: dict) -> list:
    """[(ok, text)] per trim against the pattern: the piece it rides exists and is wide enough."""
    out = []
    for t in trims or []:
        nm = _on(t, pcs)
        if nm is None:
            out.append((False, f"trim {t['kind']}: no piece {t.get('on') or 'of role waistband'} to ride on"))
            continue
        P = pcs[nm]["P"]
        h = float(np.ptp(P[:, 1]))
        if t["kind"] == "belt":
            w = float(t.get("width", 0.032))
            ok = w <= h + 0.004
            out.append((ok, f"trim belt on {nm}: {w * 1000:.0f} mm wide on a {h * 1000:.0f} mm band"
                        + ("" if ok else ": wider than its band (it would hang over the edge)")))
        else:
            n = int(t.get("count", 7))
            sp = float(np.ptp(P[:, 0])) / max(n, 1)
            out.append((n >= 5, f"trim belt_loops on {nm}: {n} loops, about {sp * 1000:.0f} mm apart"
                        + ("" if n >= 5 else " (trousers carry 5-7: fewer and the belt rides up between them)")))
    return out


class _Chart:
    """A piece's finished surface as a function of its pattern coordinates: position and outward normal."""

    def __init__(self, res: dict, nm: str):
        from scipy.interpolate import LinearNDInterpolator
        from scipy.spatial import cKDTree
        M, V = res["mesh"], np.asarray(res["V"], float)
        k = M["names"].index(nm)
        sel = np.where(np.asarray(M["piece"]) == k)[0]
        F = np.asarray(M["F"])
        Fk = F[np.isin(F[:, 0], sel)]
        N = np.zeros_like(V)
        fn = np.cross(V[Fk[:, 1]] - V[Fk[:, 0]], V[Fk[:, 2]] - V[Fk[:, 0]])
        for j in range(3):
            np.add.at(N, Fk[:, j], fn)
        N = N[sel]
        N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
        self.uv = np.asarray(M["uv"], float)[sel]
        self.V = V[sel]
        # outward: away from the body's axis through the piece's own middle (a band round the body)
        c = self.V.mean(0)
        rad = self.V - c
        rad[:, 2] = 0
        if float(np.sum(N * rad)) < 0:
            N = -N
        self.N = N
        self._p = LinearNDInterpolator(self.uv, self.V)
        self._n = LinearNDInterpolator(self.uv, self.N)
        self._tree = cKDTree(self.uv)
        self.lo, self.hi = self.uv.min(0), self.uv.max(0)

    def at(self, Q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        Q = np.atleast_2d(np.asarray(Q, float))
        P, N = self._p(Q), self._n(Q)
        bad = np.isnan(P[:, 0])
        if bad.any():  # (just outside the triangulation: the nearest vertex)
            j = self._tree.query(Q[bad])[1]
            P[bad], N[bad] = self.V[j], self.N[j]
        N = N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)
        return P, N


def _strip(C: np.ndarray, N: np.ndarray, S: np.ndarray, lift: float, th: float) -> tuple[np.ndarray, np.ndarray]:
    """A strap of rectangular section: C (k, 3) its middle line on the surface, N outward normals, S (k, 3) the half
    width vector across it; standing `lift` off the surface, `th` thick. Closed at both ends."""
    k = len(C)
    ring = [C - S + N * lift, C + S + N * lift, C + S + N * (lift + th), C - S + N * (lift + th)]
    V = np.concatenate(ring)
    F = []
    for a in range(4):
        b = (a + 1) % 4
        for i in range(k - 1):
            p, q, r, s = a * k + i, a * k + i + 1, b * k + i + 1, b * k + i
            F += [[p, q, r], [p, r, s]]
    for i, flip in ((0, False), (k - 1, True)):
        q = [a * k + i for a in range(4)]
        F += [[q[0], q[2], q[1]], [q[0], q[3], q[2]]] if not flip else [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
    return V, np.asarray(F)


def _box(c: np.ndarray, ax: np.ndarray, ay: np.ndarray, az: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A box at c with half-size vectors ax, ay, az."""
    V = np.array([c + sx * ax + sy * ay + sz * az for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    F = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                  [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    return V, F


def meshes(res: dict, g: dict) -> list:
    """The garment's trims on its finished surface: [{"name", "kind", "V", "F", "color"}]."""
    out = []
    trims = g.get("trims") or []
    if not trims:
        return out
    pcs = res["pieces"]["pieces"]
    has_belt = next((t for t in trims if t["kind"] == "belt"), None)
    charts: dict = {}
    for t in trims:
        nm = _on(t, pcs)
        if nm is None or nm not in res["mesh"]["names"]:
            continue
        ch = charts.get(nm) or charts.setdefault(nm, _Chart(res, nm))
        x0, x1 = float(ch.lo[0]), float(ch.hi[0])
        ym = 0.5 * float(ch.lo[1] + ch.hi[1])
        h = float(ch.hi[1] - ch.lo[1])
        if t["kind"] == "belt":
            w = min(float(t.get("width", 0.032)), h + 0.004)
            th, lift = float(t.get("thickness", 0.0035)), float(t.get("lift", 0.0012))
            xs = np.arange(x0 + 0.004, x1 - 0.004, 0.006)
            C, N = ch.at(np.c_[xs, np.full_like(xs, ym)])
            Tg = np.gradient(C, axis=0)
            Tg /= np.linalg.norm(Tg, axis=1, keepdims=True) + 1e-12
            S = np.cross(N, Tg)
            S /= np.linalg.norm(S, axis=1, keepdims=True) + 1e-12
            # the two ends lap: the end at high x lies a belt's thickness further out over its last 6 cm
            ramp = np.clip((xs - (x1 - 0.06)) / 0.03, 0, 1) if (pcs[nm].get("wrap") or {}).get("over") != "low" else \
                np.clip(((x0 + 0.06) - xs) / 0.03, 0, 1)
            V, F = _strip(C + N * (ramp * (th + 0.0008))[:, None], N, S * (w / 2), lift, th)
            out.append({"name": t.get("name", "belt"), "kind": "belt", "V": V, "F": F, "color": t.get("color", "#1b1a19")})
            if t.get("buckle", True):
                mk = pcs[nm].get("marks") or {}
                bx = float(np.asarray(mk["buttonhole1"])[0]) if "buttonhole1" in mk else (x0 + 0.02)
                c, n = ch.at([[bx, ym]])
                c2 = ch.at([[bx + 0.004, ym]])[0]
                tg = (c2 - c)[0]
                tg /= np.linalg.norm(tg) + 1e-12
                s = np.cross(n[0], tg)
                Vb, Fb = _box(c[0] + n[0] * (lift + 2 * th + 0.002), tg * 0.019, s * (w / 2 + 0.005), n[0] * 0.0022)
                out.append({"name": "buckle", "kind": "buckle", "V": Vb, "F": Fb, "color": t.get("buckle_color", "#8a8a88")})
        else:
            n_ = int(t.get("count", 7))
            w = float(t.get("width", 0.01))
            stand = float(t.get("stand", (float(has_belt.get("thickness", 0.0035)) + 0.003) if has_belt else 0.001))
            inset = float(t.get("inset", 0.07))
            lap = max((x1 - x0) - _closed(pcs[nm]), 0.0)
            a, b = x0 + inset + (lap if (pcs[nm].get("wrap") or {}).get("over") != "low" else 0.0), \
                x1 - inset - (lap if (pcs[nm].get("wrap") or {}).get("over") == "low" else 0.0)
            Vs, Fs, n0 = [], [], 0
            for x in np.linspace(a, b, n_):
                ys = np.array([ch.hi[1] + 0.002, ch.hi[1], ym + 0.3 * h, ym, ym - 0.3 * h, ch.lo[1], ch.lo[1] - 0.004])
                up = np.array([0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0])
                C, N = ch.at(np.c_[np.full_like(ys, x), np.clip(ys, ch.lo[1], ch.hi[1])])
                C = C + (ch.at([[x, ch.hi[1]]])[0] - ch.at([[x, ch.hi[1] - 0.004]])[0]) / 0.004 * (ys - np.clip(ys, ch.lo[1], ch.hi[1]))[:, None]
                c2 = ch.at(np.c_[np.full_like(ys, x + 0.004), np.clip(ys, ch.lo[1], ch.hi[1])])[0]
                Tg = c2 - ch.at(np.c_[np.full_like(ys, x), np.clip(ys, ch.lo[1], ch.hi[1])])[0]
                Tg /= np.linalg.norm(Tg, axis=1, keepdims=True) + 1e-12
                V, F = _strip(C + N * (up * stand)[:, None], N, Tg * (w / 2), 0.0005, 0.0016)
                Vs.append(V)
                Fs.append(F + n0)
                n0 += len(V)
            out.append({"name": t.get("name", "belt_loops"), "kind": "belt_loops", "V": np.concatenate(Vs), "F": np.concatenate(Fs),
                        "color": t.get("color") or g.get("color", "#8fb3d9")})
    return out


def _closed(pc: dict) -> float:
    mk = pc.get("marks") or {}
    if "button1" in mk and "buttonhole1" in mk:
        return float(abs(np.asarray(mk["button1"])[0] - np.asarray(mk["buttonhole1"])[0]))
    return float(np.ptp(pc["P"][:, 0]))
