"""STEP 5's LINES (mark.py has the step): each seam line a named kind of body line, projected onto the toile by its own
rule (R1 / R2b / D4, C489-C491) as a scalar field g whose zero set is the line. Every kind's sign is fixed, so a mark's
`into` names [the piece where g < 0, the piece where g > 0]:
  armhole       the toile's armhole CONE (step 4's, toile_geom.Cone) near the arm's axis: [body side, arm side]
  centre_back   the plane x = 0 behind the torso's centre (a mask: the front stays open): [right (-x), left (+x)]
  panel         step 2's panel share at every girth: the seam AFTER the named panel (`after`: "front" puts it at the
                front's share of the half round from centre front), the share interpolated between the girth levels
                (held above / below), placed by arc along the toile's own section (horizontal from the torso axis);
                above the underarm (the armhole's lowest point) it runs on into `above` ("shoulder"): [ahead, behind]
  shoulder      the toile's shoulder line (step 4) carried straight down / forward: [front, back]; its inner end leans
                onto the toile's neck corner (toile.npz neck_corner: where the neck seam meets the opening)
  under_sleeve  the TAILOR'S rule on the sleeve tube: the under sleeve's two seams set in `fore_in_mm` from the arm's
                front line and `hind_in_mm` from its back line (arc on the tube): [top sleeve, under sleeve]
  level         a horizontal cut at a step-0 fit level or height (`at`), `offset_mm`: [below, above]
A mark on the left (".L" names) is mirrored to the right by evaluating it on the mirrored toile. Metres, Blender axes."""
from __future__ import annotations

import numpy as np

MIR = np.array([-1.0, 1, 1])
KINDS = ("armhole", "centre_back", "panel", "shoulder", "under_sleeve", "level")
ARM_REACH_M = 0.05   # the armhole cut reaches this far past the sleeve's own radius from its axis
NECK_LEAN_M = 0.04  # m: the shoulder line's inner end leans onto the toile's neck corner over this much of its run
SHOULDER_K = 5.0     # 1/m: the shoulder line's field in the panel's units (radians ~ m / torso radius)
Z_STEP = 0.01        # m: the panel's section spacing


class LineRefused(ValueError):
    """A line kind or its parameters the toile / earlier steps can't give (named)."""


class Cone:
    """step 4's armhole cone from toile.npz (toile_geom.Cone's sdist without the loop)."""

    def __init__(self, Z):
        self.O, self.A, self.PS, self.AL = Z["cone_O"], Z["cone_A"], Z["cone_PS"], Z["cone_AL"]
        e1 = np.cross(self.A, [0, 1.0, 0])
        self.e1 = e1 / np.linalg.norm(e1)
        self.e2 = np.cross(self.A, self.e1)

    def sdist(self, P):
        d = P - self.O
        n = np.linalg.norm(d, axis=1) + 1e-12
        ps, al = np.arctan2(d @ self.e2, d @ self.e1), np.arccos(np.clip((d @ self.A) / n, -1, 1))
        return (np.interp(ps, self.PS, self.AL, period=2 * np.pi) - al) * n


def axis_foot(P, C, R):
    """Nearest point on the polyline C (radius R along it), its radius and direction, per point."""
    best = np.full(len(P), np.inf)
    q, r, d = np.zeros((len(P), 3)), np.zeros(len(P)), np.zeros((len(P), 3))
    for j in range(len(C) - 1):
        dv = C[j + 1] - C[j]
        u = np.clip(((P - C[j]) @ dv) / (dv @ dv), 0, 1)
        x = C[j] + u[:, None] * dv
        dist = np.linalg.norm(P - x, axis=1)
        b = dist < best
        best = np.where(b, dist, best)
        q[b], r[b], d[b] = x[b], (R[j] + u * (R[j + 1] - R[j]))[b], dv / np.linalg.norm(dv)
    return q, r, d, best


class Lines:
    """The fields of one toile: Z = toile.npz, fit = step 0's fit levels, heights, panels = step 2's panels."""

    def __init__(self, Z, fit: dict, heights: dict, panels: list):
        self.Z, self.fit, self.heights, self.panels = Z, fit, heights, panels
        self.yc = float(Z["yc"])
        self.cone = Cone(Z)
        self.CAX, self.RAX = Z["sleeve_axis"], Z["sleeve_r"]
        S = Z["shoulder_line"]
        o = np.argsort(np.abs(S[:, 0]))
        self.sx, self.sy = np.abs(S[o, 0]), S[o, 1]
        if "neck_corner" in Z.files:  # (the shoulder seam meets the neck where the toile's neck seam ends: the opening
            nc = np.asarray(Z["neck_corner"], float)  # may leave it behind the body's HPS; leaning the line's inner end
            x0, y0 = abs(float(nc[0])), float(nc[1])  # onto it keeps the back's neck edge the neck seam alone)
            if x0 < self.sx[0]:
                self.sx, self.sy = np.r_[x0, self.sx], np.r_[np.interp(x0, self.sx, self.sy), self.sy]
            w = np.clip(1 - (self.sx - x0) / NECK_LEAN_M, 0, 1)
            self.sy = self.sy + (y0 - np.interp(x0, self.sx, self.sy)) * w
        self.z_under = float(Z["armhole"][:, 2].min())

    def theta(self, P):
        return np.arctan2(P[:, 0], -(P[:, 1] - self.yc))

    def field(self, line: dict, P, Vreg):
        """g at the points P (already folded to the left); Vreg: the region's vertices (folded), for the panel's arc."""
        k = line.get("kind")
        if k == "armhole":
            q, r, _, dist = axis_foot(P, self.CAX, self.RAX)
            return np.minimum(self.cone.sdist(P), r + ARM_REACH_M - dist)
        if k == "centre_back":
            return P[:, 0]
        if k == "shoulder":
            return self.shoulder(P)
        if k == "under_sleeve":
            return self.under(P, float(line.get("fore_in_mm", 30)) / 1000, float(line.get("hind_in_mm", 20)) / 1000)
        if k == "level":
            return P[:, 2] - self.level_z(line.get("at")) - float(line.get("offset_mm", 0)) / 1000
        if k == "panel":
            return self.panel(line, P, Vreg)
        raise LineRefused(f"line kind {k!r}: one of {', '.join(KINDS)}")

    def level_z(self, at):
        if at in self.fit:
            return float(self.fit[at]["level_z_m"])
        if at in self.heights:
            return float(self.heights[at]["z_mm"]) / 1000
        raise LineRefused(f"level.at {at!r}: a step-0 fit level ({', '.join(self.fit)}) or height ({', '.join(self.heights)})")

    def shoulder(self, P):
        return SHOULDER_K * (P[:, 1] - np.interp(np.abs(P[:, 0]), self.sx, self.sy))

    def under(self, P, fore_in, hind_in):
        q, r, d, _ = axis_foot(P, self.CAX, self.RAX)
        f0 = np.array([0, -1.0, 0]) - (d @ [0, -1.0, 0])[:, None] * d
        f0 /= np.linalg.norm(f0, axis=1, keepdims=True)
        u0 = np.cross(d, f0)
        u0 *= np.sign(u0 @ [-1.0, 0, -1.0])[:, None]
        w = P - q
        ph = np.arctan2(np.einsum("ij,ij->i", w, f0), np.einsum("ij,ij->i", w, u0))
        r = np.maximum(r, 1e-3)
        return np.minimum((np.pi / 2 - fore_in / r) - ph, ph + (np.pi / 2 - hind_in / r))

    def cum_share(self, after: str):
        """[(z, share of the half round from centre front to the seam after `after`)] from step 2's panels."""
        out = []
        for p in self.panels:
            sh = p.get("shares") or {}
            names = list(sh)
            if after not in names or p.get("girth") not in self.fit:
                continue
            s = sum(float(sh[n]["share"] if isinstance(sh[n], dict) else sh[n]) for n in names[:names.index(after) + 1])
            tot = sum(float(sh[n]["share"] if isinstance(sh[n], dict) else sh[n]) for n in names)
            out.append((float(self.fit[p["girth"]]["level_z_m"]), s / tot))
        if not out:
            raise LineRefused(f"panel.after {after!r}: no step-2 panel names it at a step-0 fit level "
                              f"(panels: {[list(p.get('shares') or {}) for p in self.panels]})")
        return sorted(out)

    def panel(self, line, P, Vreg):
        cs = self.cum_share(line.get("after"))
        zc, sc = np.array([c[0] for c in cs]), np.array([c[1] for c in cs])
        th_all = np.clip(self.theta(Vreg), 0, np.pi)
        r_all = np.hypot(Vreg[:, 0], Vreg[:, 1] - self.yc)
        zs = np.arange(Vreg[:, 2].min(), min(Vreg[:, 2].max(), self.z_under) + Z_STEP, Z_STEP)
        bins = np.linspace(0, np.pi, 91)
        th_seam = np.zeros(len(zs))
        for i, z in enumerate(zs):
            m = np.abs(Vreg[:, 2] - z) < Z_STEP
            if m.sum() < 20:
                th_seam[i] = np.nan
                continue
            k = np.clip(np.digitize(th_all[m], bins) - 1, 0, len(bins) - 2)
            rb = np.array([np.median(r_all[m][k == j]) if (k == j).any() else np.nan for j in range(len(bins) - 1)])
            tb = 0.5 * (bins[1:] + bins[:-1])
            ok = np.isfinite(rb)
            rb = np.interp(tb, tb[ok], rb[ok])
            xy = np.c_[rb * np.sin(tb), -rb * np.cos(tb)]
            arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
            th_seam[i] = np.interp(np.interp(z, zc, sc) * arc[-1], arc, tb)
        ok = np.isfinite(th_seam)
        g = self.theta(P) - np.interp(P[:, 2], zs[ok], th_seam[ok])
        above = line.get("above", "shoulder")
        if above == "shoulder":
            g = np.where(P[:, 2] <= self.z_under, g, self.shoulder(P))
        elif above not in (None, "none"):
            raise LineRefused(f"panel.above {above!r}: \"shoulder\" or \"none\"")
        return g
