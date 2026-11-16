"""The sleeve cap's EASE through the flattening (step 6 of drape first; C496). Step 4 builds the crown as a dome standing
proud of the armhole and records the ease (step 4's numbers (toile.json) sleeve.cap: ease_pct, band_mm; toile.npz: the armhole cone). The
seam itself is one line in the toile (the sleeve and the body share it), so the flat cap would be as long as the armhole:
a tailor's cap is LONGER, its fullness shrunk into the seam. So the cloth in the cap's band is the eased cloth: its rest
length along the seam is (1 + e) x the toile's, e = the ease at the seam, fading to nothing CAP_BAND inside it (square
of the share), full over the crown and W_FLOOR of that at the underarm (toile.CAP_UNDER_COS, the angle round the cone from the shoulder point), shared so its mean round the armhole is
the ease. The piece is flattened against
that rest shape (flatten.flatten(rest=...)), the band's scale CALIBRATED (CAL_PASSES) until each sleeve piece's flat seam edge
is longer than the toile's by its share of the ease. A piece lying mostly outside the cone (the body's pieces: they
meet it along the seam) is flattened as it lies. Metres."""
from __future__ import annotations

import numpy as np

from .toile import CAP_UNDER_COS
from .toile_geom import smooth01

CAL_PASSES = 5
W_FLOOR = 0.25  # the ease's weight at the underarm (the crown's 1): the under sleeve's seam is held to its toile length +
SEAM_TOL_M = 0.002  # a loop vertex this near the cone is on the armhole seam


class CapEase:
    """From step 4's output (numbers.sleeve.cap) and its toile.npz (the cone)."""

    def __init__(self, s4: dict):
        import json
        from pathlib import Path
        nb = s4.get("numbers")
        nb = json.loads(Path(nb).read_text()) if isinstance(nb, str) and Path(nb).exists() else (nb or {})
        cap = ((nb if isinstance(nb, dict) else {}).get("sleeve") or {}).get("cap")
        self.ok = bool(cap) and bool(s4.get("toile"))
        if not self.ok:
            return
        from .mark_lines import Cone
        self.cone = Cone(np.load(s4["toile"]))
        self.pct, self.band = float(cap["ease_pct"]), float(cap["band_mm"]) / 1000
        loop = np.load(s4["toile"])["armhole"]
        d0 = loop[0] - self.cone.O  # (the armhole starts at the shoulder point: the crown's top)
        self.ps0 = float(np.arctan2(d0 @ self.cone.e2, d0 @ self.cone.e1))
        self.wmean = float(self.fields(loop)[1].mean())  # (the ease shared round the armhole by w: its mean is pct)

    def fields(self, V):
        """(sigma: into the sleeve from the cone (m), w: the crown's weight 0..1) per vertex (folded to the left)."""
        Q = V * np.where(V[:, :1] < 0, np.array([-1.0, 1, 1]), 1)
        s = self.cone.sdist(Q)
        d = Q - self.cone.O
        ps = np.arctan2(d @ self.cone.e2, d @ self.cone.e1)
        return s, W_FLOOR + (1 - W_FLOOR) * smooth01((np.cos(ps - self.ps0) - CAP_UNDER_COS) / (1 - CAP_UNDER_COS))

    def rest(self, V, F, k):
        """Per face (axis, stretch): the band's seam-parallel direction (3D unit) and its rest stretch."""
        s, w = self.fields(V)
        e = k * self.pct / 100 * w / self.wmean * np.clip(1 - s / self.band, 0, 1) ** 2 * (s > -SEAM_TOL_M)
        g = np.stack([(self.cone.sdist(_fold(V + h)) - self.cone.sdist(_fold(V - h))) / 2e-3
                      for h in np.eye(3) * 1e-3], 1)
        n = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        t = np.cross(n, g[F].mean(1))
        return t / (np.linalg.norm(t, axis=1, keepdims=True) + 1e-12), e[F].mean(1)


def _fold(P):
    return P * np.where(P[:, :1] < 0, np.array([-1.0, 1, 1]), 1)


def seam_stretch(U, V, loop, on):
    """The flat seam over the crown against the toile's: (flat / toile - 1, toile length m) along loop edges on it."""
    a, b = np.asarray(loop), np.roll(loop, -1)
    m = on[a] & on[b]
    if not m.any():
        return 0.0, 0.0
    l3 = np.linalg.norm(V[a[m]] - V[b[m]], axis=1).sum()
    return float(np.linalg.norm(U[a[m]] - U[b[m]], axis=1).sum() / max(l3, 1e-9) - 1), float(l3)


def flatten_eased(V, F, loop, ce: CapEase):
    """flatten.flatten with the cap's ease (module doc): (U, S, F kept, report or None)."""
    from .flatten import flatten
    if ce is None or not ce.ok:
        return (*flatten(V, F), None)
    s, w = ce.fields(V)
    if not np.median(s) > 0:  # (a body piece lies outside the cone: it meets it along its seam)
        return (*flatten(V, F), None)
    on = np.abs(s) < SEAM_TOL_M
    wl = w[np.asarray(loop)][on[np.asarray(loop)]]
    want = ce.pct / 100 * (float(wl.mean()) / ce.wmean if len(wl) else 0.0)
    k, got, hist, kg = 1.0, 0.0, [], []
    for _ in range(CAL_PASSES):
        U, S, Fk = flatten(V, F, rest=lambda Vc, Fc, k=k: ce.rest(Vc, Fc, k))
        got, l3 = seam_stretch(U, V, loop, on)
        hist.append(round(got * 100, 2))
        kg.append((k, got))
        if want <= 0 or abs(got - want) < 0.002:
            break
        (k0, g0), (k1, g1) = kg[-2] if len(kg) > 1 else (0.0, got - k * 0.5 * want), kg[-1]
        k = float(np.clip(k1 + (want - g1) * (k1 - k0) / (g1 - g0 if abs(g1 - g0) > 1e-4 else 1e-4), 0.0, 4 * k1 + 1))
    return U, S, Fk, {"ease_pct": round(want * 100, 2), "flat_over_toile_pct": round(got * 100, 2),
                      "crown_seam_mm": round(l3 * 1000, 1), "scale": round(k, 3), "passes_pct": hist}
