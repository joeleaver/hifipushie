"""Measuring: the same 2D quantity on the photo and on the model through one camera (Side, value). Part of likeness (likeness.py has the overview)."""
from __future__ import annotations

import numpy as np

from .likeness import OVAL, _MP_TO_LM, checklist

# ---- measuring: the same 2D quantity on the photo and on the model, through one camera ------------------------------
class Unmeasurable(Exception):
    pass


def view_kind(yaw: float) -> str:
    a = abs(float(yaw or 0.0))
    return "front" if a < 20 else ("three_quarter" if a < 70 else "profile")


class Side:
    """One picture's face: MediaPipe's 478 (P) and/or the 68 + 2 eye centres (lm), pixels of the reference picture."""

    def __init__(self, P=None, lm=None, source=""):
        self.P = None if P is None else np.asarray(P, float)
        self.lm = None if lm is None else np.asarray(lm, float)
        self.source = source or ("detector" if P is not None else "landmarks")

    def pt(self, idx) -> np.ndarray:
        idx = [idx] if isinstance(idx, (int, np.integer)) else list(idx)
        out = []
        for i in idx:
            if self.P is not None:
                out.append(self.P[i])
            elif self.lm is not None and i in _MP_TO_LM and np.isfinite(self.lm[_MP_TO_LM[i]]).all():
                out.append(self.lm[_MP_TO_LM[i]])
            else:
                raise Unmeasurable(f"point {i} needs the detector (not in the 68)")
        return np.mean(out, 0)

    def frame(self):
        a = self.pt(168)
        try:
            b = self.pt(152)
        except Unmeasurable:      # (stored reference points often leave the jaw contour out: its definition differs)
            b = self.pt([13, 14])
        ey = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        return np.array([ey[1], -ey[0]]), ey


def points_of(m: dict) -> list:
    """Every point a measure (or a judge item's region) reads."""
    out = []
    if m.get("kind") == "shape":
        return sorted({int(r[k]) for r in (m["region"], m["ref"]) for k in ("at", "from", "to") if k in r})
    if m.get("kind") == "jaw":
        return []
    for k, v in m.items():
        if k in ("a", "b", "vertex", "level", "from", "to", "pts", "line", "region"):
            out += list(np.ravel(v))
        elif k == "pairs":
            out += list(np.ravel([i for p in v for x in p for i in np.ravel(x)]))
        elif k in ("num", "den"):
            out += points_of(v)
        elif k in ("outer", "inner"):
            out += list(np.ravel(v))
        elif k == "kind" and v == "width":
            out += OVAL
    return sorted({int(i) for i in out})


def _width_ends(side: Side, level) -> tuple:
    """The face oval's two crossings of the face-horizontal line through the level's points (picture pixels)."""
    if side.P is None:
        raise Unmeasurable("face widths need the detector's face oval")
    ex, ey = side.frame()
    c = side.pt(level)
    o = side.P[OVAL]
    s = (o - c) @ ey
    xs = []
    for p in range(len(o)):
        q = (p + 1) % len(o)
        if s[p] * s[q] <= 0 and s[p] != s[q]:
            t = s[p] / (s[p] - s[q])
            xs.append(((o[p] + t * (o[q] - o[p])) - c) @ ex)
    if len(xs) < 2:
        raise Unmeasurable("the level misses the face oval")
    return c + min(xs) * ex, c + max(xs) * ex


def _width(side: Side, level) -> float:
    a, b = _width_ends(side, level)
    return float(np.linalg.norm(b - a))


def _width_lines(m: dict) -> list:
    if m.get("kind") == "width":
        return [m["level"]]
    return [x for k in ("num", "den") if k in m for x in _width_lines(m[k])]


def _item(iid: str) -> dict:
    return next(it for it in checklist() if it["id"] == iid)


def _facing(side: Side, ex) -> float:
    """+1 when the face points along +ex in the picture (its nose tip ahead of its wings), else -1."""
    return 1.0 if (side.pt(1) - side.pt([129, 358])) @ ex >= 0 else -1.0


def value(side: Side, m: dict, mmpx: float):
    """One measure on one side: mm (distances), degrees (tilts, angles) or a ratio."""
    k = m["kind"]
    if k == "judge":
        raise Unmeasurable("judge by eye (focus panel)")
    if k == "dist":
        ex, ey = side.frame()
        ax = {"x": ex, "y": ey}.get(m.get("axis"))
        vals = []
        for a, b in (m.get("pairs") or [[m["a"], m["b"]]]):
            d = side.pt(b) - side.pt(a)
            v = float(np.linalg.norm(d)) if ax is None else float(d @ ax)
            vals.append(abs(v) if m.get("abs") else v)
        if m.get("forward"):  # signed toward where the face points (+ = b ahead of a): turned views only
            vals = [v * _facing(side, ex) for v in vals]
        return float(np.mean(vals)) * mmpx
    if k == "eline":  # signed distance of points from the line a -> b, + = ahead of it (toward where the face points)
        a, b, q = side.pt(m["a"]), side.pt(m["b"]), side.pt(m["pts"])
        ex, ey = side.frame()
        t = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        n = np.array([-t[1], t[0]])
        if (n @ ex) * _facing(side, ex) < 0:
            n = -n
        return float((q - a) @ n) * mmpx
    if k == "width":
        return _width(side, m["level"]) * mmpx
    if k == "ratio":
        d = value(side, m["den"], mmpx)
        return value(side, m["num"], mmpx) / d if abs(d) > 1e-9 else float("nan")
    if k == "tilt":
        ex, ey = side.frame()
        vals = []
        for a, b in m["pairs"]:
            d = side.pt(b) - side.pt(a)
            vals.append(np.degrees(np.arctan2(-(d @ ey), abs(d @ ex))))
        return float(np.mean(vals))
    if k == "level":
        ex, ey = side.frame()
        a, b = side.pt(m["from"]), side.pt(m["to"])
        return float(((side.pt(m["pts"]) - a) @ ey) / max((b - a) @ ey, 1e-9))
    if k == "arch":
        ex, ey = side.frame()
        vals = []
        for line in m["pairs"]:
            Q = np.array([side.pt(i) for i in line])
            n = Q[-1] - Q[0]
            n = np.array([-n[1], n[0]]) / max(np.linalg.norm(n), 1e-9)
            if n @ ey > 0:
                n = -n                     # up the face
            vals.append(float(((Q - Q[0]) @ n).max()))
        return float(np.mean(vals)) * mmpx
    if k == "angle":
        a, v, b = side.pt(m["a"]), side.pt(m["vertex"]), side.pt(m["b"])
        u, w = a - v, b - v
        return float(np.degrees(np.arccos(np.clip(u @ w / max(np.linalg.norm(u) * np.linalg.norm(w), 1e-12), -1, 1))))
    if k in ("cushion", "lip_area"):
        # the lower vermilion between its outer (skin) border and its inner (contact) line, corner to corner:
        # "cushion" = its visible width (where it is thicker than `frac` of its middle) over the mouth's width (a
        # short central cushion vs a lip out to the corners); "lip_area" = its area over the mouth's width squared
        # (fullness: a pouting lower lip shows more red)
        ex, ey = side.frame()
        O = np.array([side.pt(i) for i in m["outer"]])
        I_ = np.array([side.pt(i) for i in m["inner"]])
        wm = float((O[-1] - O[0]) @ ex)
        if abs(wm) < 1e-9:
            return float("nan")
        if k == "lip_area":
            P = np.r_[O, I_[::-1]]
            area = 0.5 * abs(float(np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(P[:, 1], np.roll(P[:, 0], -1))))
            return area / wm ** 2
        t = np.abs((O - I_) @ ey)
        u = ((0.5 * (O + I_)) - O[0]) @ ex / wm
        mid = len(t) // 2
        lim = float(m.get("frac", 0.5)) * t[mid]
        ends = []
        for rng in (range(mid, 0, -1), range(mid, len(t) - 1)):
            e = None
            for i in rng:
                j = i - 1 if rng.step < 0 else i + 1
                if t[j] < lim <= t[i]:
                    e = u[i] + (u[j] - u[i]) * (t[i] - lim) / max(t[i] - t[j], 1e-12)
                    break
            ends.append(u[0] if (e is None and rng.step < 0) else (u[-1] if e is None else e))
        return float(abs(ends[1] - ends[0]))
    if k == "bow":
        ex, ey = side.frame()
        Q = np.array([side.pt(i) for i in m["line"]])
        n = Q[-1] - Q[0]
        n = np.array([-n[1], n[0]]) / max(np.linalg.norm(n), 1e-9)
        out = side.pt(m["line"][-1]) - side.pt([129, 358])
        if n @ out < 0:
            n = -n                         # + = toward where the nose points: a hump
        dev = (Q - Q[0]) @ n
        return float(dev[np.argmax(np.abs(dev))]) * mmpx
    raise ValueError(f"likeness: unknown measure kind {k!r}")


def _confidence(item: dict, vk: str, mmpx: float, src: str) -> str:
    if item["measure"]["kind"] == "judge":
        return "judge"
    pref = item["views"][0] if item["views"] else vk
    if item.get("tol") and item["unit"] == "mm" and item["tol"] < 1.2 * mmpx:
        return "low"            # the tolerance is about a pixel of the reference
    if item.get("reliability") or vk != pref or src != "detector":
        return "medium"
    return "high"
