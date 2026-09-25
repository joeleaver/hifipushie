"""Whole-model deformations: bend the finished shape the way a cartoonist would (a sagging ridge, bulging walls,
a base wider than the eaves, a lean, a twist, a hand-drawn wobble).

spec["style"]["shape"]["deform"] = [op, ...], applied in order, each {"<kind>": {params}} in world metres:
  sag:    {"axis": "x" | "y", "span": [a, b], "amount": m, "from": z0, "to": z1}  drop by up to `amount` in the
          middle of the span along the axis, growing from nothing at z0 to all of it at z1 (a ridge that dips;
          the floor below z0 stays put)
  bulge:  {"half": [X, Y], "center": [x, y], "amount": m, "from": z0, "to": z1}  push outwards, `amount` at
          the walls (|x| = X or |y| = Y) half-way up, nothing at z0 and z1 (walls that belly out)
  taper:  {"center": [x, y], "amount": f, "from": z0, "to": z1}  scale across by 1 + f at z0 down to 1 at z1
          (a base wider than the top; negative: a top-heavy mushroom)
  lean:   {"dir": [dx, dy], "amount": m per m, "from": z0}  shear sideways with height above z0
  twist:  {"center": [x, y], "deg": per m, "from": z0}  turn about a vertical line with height above z0
  wobble: {"amount": m, "scale": m, "seed": n}  a smooth displacement a few `scale`s across (a hand-drawn line)

How it works (sdf.sd_csg): every primitive of the building (not prefab instances: they stay rigid and move with
the ground under them, so instances still share one mesh) is evaluated at the undeformed point, found by
inverting p = x + D(x) with fixed-point steps, and its field divided by the deformation's stretch (`lip`) so
the field never over-estimates the distance (the narrow-band mesher relies on that).
"""

from __future__ import annotations

import numpy as np

from .spec import SpecError

KINDS = ("sag", "bulge", "taper", "lean", "twist", "wobble")


def _ramp(z, a, b):
    t = np.clip((z - a) / max(b - a, 1e-9), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def displacement(ops: list, x: np.ndarray) -> np.ndarray:
    """D(x): how far each point of the undeformed shape moves (n, 3)."""
    x = np.asarray(x, np.float64)
    D = np.zeros_like(x)
    for op in ops:
        (kind, p), = op.items()
        z = x[..., 2]
        if kind == "sag":
            ax = {"x": 0, "y": 1}[p.get("axis", "x")]
            a, b = p["span"]
            u = np.clip((x[..., ax] - a) / (b - a), 0.0, 1.0)
            D[..., 2] -= float(p["amount"]) * 4 * u * (1 - u) * _ramp(z, p.get("from", 0.0), p.get("to", 1.0))
        elif kind == "bulge":
            X, Y = p["half"]
            c = np.asarray(p.get("center", [0, 0]), float)
            z0, z1 = p.get("from", 0.0), p.get("to", 1.0)
            t = np.clip((z - z0) / max(z1 - z0, 1e-9), 0.0, 1.0)
            k = float(p["amount"]) * np.sin(np.pi * t)
            D[..., 0] += k * np.clip((x[..., 0] - c[0]) / X, -1.5, 1.5)
            D[..., 1] += k * np.clip((x[..., 1] - c[1]) / Y, -1.5, 1.5)
        elif kind == "taper":
            c = np.asarray(p.get("center", [0, 0]), float)
            s = float(p["amount"]) * (1 - _ramp(z, p.get("from", 0.0), p.get("to", 1.0)))
            D[..., 0] += s * (x[..., 0] - c[0])
            D[..., 1] += s * (x[..., 1] - c[1])
        elif kind == "lean":
            d = np.asarray(p.get("dir", [1, 0]), float)
            d = d / (np.linalg.norm(d) or 1.0)
            h = float(p["amount"]) * np.maximum(z - p.get("from", 0.0), 0.0)
            D[..., 0] += d[0] * h
            D[..., 1] += d[1] * h
        elif kind == "twist":
            c = np.asarray(p.get("center", [0, 0]), float)
            th = np.radians(float(p["deg"])) * np.maximum(z - p.get("from", 0.0), 0.0)
            dx, dy = x[..., 0] - c[0], x[..., 1] - c[1]
            D[..., 0] += dx * np.cos(th) - dy * np.sin(th) - dx
            D[..., 1] += dx * np.sin(th) + dy * np.cos(th) - dy
        elif kind == "wobble":
            rng = np.random.default_rng(int(p.get("seed", 0)))
            amp, sc = float(p["amount"]), float(p.get("scale", 3.0))
            for i in range(3):  # three waves per axis, random directions and phases: smooth, cheap, seamless
                for _ in range(3):
                    k = rng.normal(size=3)
                    k *= 2 * np.pi / sc / np.linalg.norm(k)
                    D[..., i] += amp / 3 * np.sin(x @ k + rng.uniform(0, 2 * np.pi))
    return D


def undeform(ops: list, p: np.ndarray, steps: int = 4) -> np.ndarray:
    """The undeformed point x with x + D(x) = p (fixed-point iteration: fine while D bends gently)."""
    x = np.asarray(p, np.float64)
    for _ in range(steps):
        x = p - displacement(ops, x)
    return x


def validate(ops) -> list:
    if not isinstance(ops, list):
        raise SpecError("style.shape.deform is a list of {kind: {params}}")
    for i, op in enumerate(ops):
        if not isinstance(op, dict) or len(op) != 1 or next(iter(op)) not in KINDS:
            raise SpecError(f"style.shape.deform[{i}]: one of {', '.join(KINDS)}, e.g. "
                            '{"sag": {"axis": "x", "span": [-5, 5], "amount": 0.4, "from": 2.4, "to": 4.7}}')
        (kind, p), = op.items()
        need = {"sag": ("span", "amount"), "bulge": ("half", "amount"), "taper": ("amount",),
                "lean": ("amount",), "twist": ("deg",), "wobble": ("amount",)}[kind]
        miss = [k for k in need if k not in p]
        if miss:
            raise SpecError(f"style.shape.deform[{i}] {kind}: needs {', '.join(miss)}")
    return ops


def stretch(ops: list, lo: np.ndarray, hi: np.ndarray, n: int = 12) -> tuple[float, float]:
    """(lip, reach) over a box: the largest stretch of the inverse map (so the field can be divided by it and
    stay a lower bound on distance) and the largest displacement (how far primitives' boxes grow)."""
    g = [np.linspace(a, b, n) for a, b in zip(lo, hi)]
    X = np.stack(np.meshgrid(*g, indexing="ij"), -1).reshape(-1, 3)
    D = displacement(ops, X)
    h = 1e-3
    J = np.stack([(displacement(ops, X + h * e) - displacement(ops, X - h * e)) / (2 * h) for e in np.eye(3)], -1)
    # x = p - D(x): the inverse map's Jacobian is (I + dD)^-1; bound its norm by 1 / (1 - |dD|) when |dD| < 1
    norm = np.linalg.norm(J, ord=2, axis=(1, 2)).max()
    if norm >= 0.8:
        raise SpecError(f"style.shape.deform bends too sharply (stretch {norm:.2f} per metre): make it gentler")
    return float(1.0 / (1.0 - norm)), float(np.linalg.norm(D, axis=1).max())
