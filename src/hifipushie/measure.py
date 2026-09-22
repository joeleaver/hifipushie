"""Cross-section measurements: slice the exact SDF with planes and report sizes as numbers.

Slices sample the analytic field (not the voxel grid), so numbers don't depend on build resolution.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from .sdf import field_at
from .spec import SpecError, bone_frame, compile_prims, expand_mirror, resolve_point

AXES = {"x": 0, "y": 1, "z": 2}
N = 161  # samples per side of a slice plane


def _plane(prims, centre, u, v, half):
    """Inside mask on a square plane spanned by unit vectors u, v; returns mask and 1-D coords."""
    s = np.linspace(-half, half, N)
    pts = centre + s[:, None, None] * u + s[None, :, None] * v
    return field_at(prims, pts) < 0, s


def _extent(mask, s):
    iu, iv = np.nonzero(mask)
    step = s[1] - s[0]
    return (s[iu.min()], s[iu.max()], s[iv.min()], s[iv.max()], len(iu) * step * step)


def _bone_slice(prims, centre, u, v, r0):
    """Section of the connected part that contains the bone axis, growing the plane until it fits."""
    half = 3.0 * r0
    for _ in range(6):
        mask, s = _plane(prims, centre, u, v, half)
        c = N // 2
        if not mask[c, c]:
            return None
        lab, _ = ndimage.label(mask)
        part = lab == lab[c, c]
        if not (part[0].any() or part[-1].any() or part[:, 0].any() or part[:, -1].any()):
            return _extent(part, s)
        half *= 2
    return _extent(part, s)


def _ray(prims, centre, d, reach):
    """Distance from centre along d to the first outside point (linearly refined), up to reach."""
    s = np.linspace(0, reach, 400)
    f = field_at(prims, centre + s[:, None] * d)
    out = np.nonzero(f >= 0)[0]
    if len(out) == 0:
        return reach
    i = out[0]
    if i == 0:
        return 0.0
    return float(s[i - 1] + (s[i] - s[i - 1]) * -f[i - 1] / (f[i] - f[i - 1]))


def _dirname(vec) -> str:
    """Nearest world axis as a label, e.g. '+X' or '~-Z' when not exact."""
    i = int(np.argmax(np.abs(vec)))
    label = ("+" if vec[i] > 0 else "-") + "XYZ"[i]
    return label if abs(vec[i]) > 0.99 else "~" + label


def along_bones(spec: dict, bones: list[str], samples: int) -> str:
    s = expand_mirror(spec)
    prims = compile_prims(spec)
    lines = []
    for name in bones:
        b = s["bones"].get(name)
        if b is None:
            raise SpecError(f"unknown bone {name!r}")
        a, bb = resolve_point(s, b["a"]), resolve_point(s, b["b"])
        w, axis, h = bone_frame(a, bb, b.get("up"))
        ra = float(b.get("r_a") or s["joints"][b["a"]].get("r", 0.05))
        rb = float(b.get("r_b") or s["joints"][b["b"]].get("r", 0.05))
        r0 = max(ra, rb) * max(1.0, *(b.get("flat") or [1, 1]))
        lines.append(f"bone {name}: {b['a']} -> {b['b']}, len {np.linalg.norm(bb - a):.3f}; "
                     f"width axis {_dirname(w)}, height axis {_dirname(h)}")
        lines.append("   t    centre (x, y, z)          width  height    w-     w+     h-     h+    area")
        for t in np.linspace(0, 1, samples):
            c = a + (bb - a) * t
            pos = "(" + ", ".join(f"{x:6.3f}" for x in c) + ")"
            sec = _bone_slice(prims, c, w, h, r0)
            if sec is None:
                lines.append(f"  {t:4.2f}  {pos}   axis point is outside the surface")
                continue
            wm, wp, hm, hp = (_ray(prims, c, d, 8 * r0) for d in (-w, w, -h, h))
            lines.append(f"  {t:4.2f}  {pos}   {wm + wp:6.3f}  {hm + hp:6.3f}  "
                         f"{wm:5.3f}  {wp:5.3f}  {hm:5.3f}  {hp:5.3f}  {sec[4]:7.4f}")
    lines.append("w-/w+/h-/h+ = distance from the bone axis to the surface along each section axis "
                 "(width = w- + w+); area = the whole connected section, so it jumps where the bone "
                 "merges into the body.")
    return "\n".join(lines)


def along_axis(spec: dict, axis: str, samples: int, lo: float | None, hi: float | None,
               min_area: float = 1e-4) -> str:
    prims = compile_prims(spec)
    adds = [p for p in prims if p.op == "add"]
    blo = np.min([p.lo for p in adds], axis=0)
    bhi = np.max([p.hi for p in adds], axis=0)
    k = AXES[axis]
    i, j = [d for d in range(3) if d != k]
    ui, vj = np.eye(3)[i], np.eye(3)[j]
    mid = (blo + bhi) / 2
    half = float(max(bhi[i] - blo[i], bhi[j] - blo[j])) / 2 * 1.05
    lo = blo[k] if lo is None else lo
    hi = bhi[k] if hi is None else hi
    ni, nj = "XYZ"[i], "XYZ"[j]
    lines = [f"slices across {axis.upper()} from {lo:.3f} to {hi:.3f}; each part: "
             f"{ni} range, {nj} range, area (parts smaller than {min_area} m² omitted)"]
    for t in np.linspace(lo, hi, samples):
        c = mid.copy()
        c[k] = t
        mask, s = _plane(prims, c, ui, vj, half)
        lab, n = ndimage.label(mask)
        parts = []
        for m in range(1, n + 1):
            u0, u1, v0, v1, area = _extent(lab == m, s)
            if area >= min_area:
                parts.append((u0 + c[i], u1 + c[i], v0 + c[j], v1 + c[j], area))
        parts.sort(key=lambda p: p[0])
        head = f"  {axis}={t:+.3f}"
        if not parts:
            lines.append(f"{head}  empty")
            continue
        desc = "; ".join(f"{ni}[{p[0]:+.3f},{p[1]:+.3f}] {nj}[{p[2]:+.3f},{p[3]:+.3f}] a{p[4]:.4f}"
                         for p in parts)
        lines.append(f"{head}  {len(parts)} part{'s' * (len(parts) > 1)}: {desc}")
    return "\n".join(lines)


def measure(spec: dict, along, samples: int = 11, lo: float | None = None,
            hi: float | None = None) -> str:
    if isinstance(along, str) and along.lower() in AXES:
        return along_axis(spec, along.lower(), samples, lo, hi)
    bones = [along] if isinstance(along, str) else list(along)
    return along_bones(spec, bones, samples)
