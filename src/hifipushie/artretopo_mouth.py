"""Artist retopo: the mouth, built into the cage so the jaw can open (Cage.mouth calls `build`).

The muzzle's concentric loops end in a small loop r2 (about half the root's size) whose bottom arc lies on the lip
crease. That arc (`lip`, three vertices; the corners r2[0] and r2[4] stay shared) is SPLIT: the lower lip keeps r2's
vertices, the upper lip gets copies `gap` (0.5 mm) above them, and both lines are PINNED (pressed, they land on one
point and weld shut). Put the arc ON the sculpt's lip crease first (`c.crease(x, z_lo, z_hi)` per lip vertex and
corner): the inset loop's bottom arc is only where the crease is on a flat-fronted muzzle. The upper lip and the nose pad close with a 4 x 2 grid pressed on from the front.

Behind the slit, the mouth bag (the "sock"): rings that are ELLIPSES with real height (`bag`: (shrink of the slit's
width, depth back, height) per ring; a flat copy of the closed slit folds over itself when the jaw opens), then a
2 x 2 cap. All of it pinned: it is designed, not pressed.

Groups written for the later steps:
- jaw: the lower lip, the loop below it, the lower half of every bag ring and the cap's front row (weight 1; every
  ring's two corners 0.5, so the corners stretch gradually) plus `jaw_extra` (chin vertices: weight 1). The rig's Jaw
  bone takes exactly these weights.
- mouth_inside: the last bag ring and the cap (painted dark, flat normals; weighted to the head and jaw only).
- freeze: the slit, the bag and the cap (not relaxed after pressing: they keep their designed shape).
Returns {"mouth": the slit loop (corner, lower lip, corner, upper lip), "upper": r2 with the upper lip copies,
"bag": [ring, ...], "cap": {grid}, "nose": {grid}}."""
from __future__ import annotations

import math

import numpy as np

BAG = ((0.95, 0.005, 0.0015), (0.75, 0.018, 0.016), (0.5, 0.04, 0.022))


def sock(cage, mouth, mc, shrink, depth, height):
    """one bag ring: an ellipse `shrink` x the slit's width wide and `height` tall, `depth` behind its centre;
    order follows the slit loop (corner, lower lip ..., corner, upper lip ...)"""
    n = len(mouth); half = n // 2
    xs = [np.asarray(cage.V[i])[0] for i in mouth]; w = (max(xs) - min(xs)) / 2 * shrink
    out = []
    for k in range(n):
        lower = k <= half
        x = mc[0] + w * math.cos(math.pi - (math.pi * k / half if lower else math.pi * (2 - k / half)))
        z = (mc[2] - (height / 2) * math.sin(math.pi * k / half) if lower
             else mc[2] + (height / 2) * math.sin(math.pi * (k - half) / half))
        out.append(np.array([x, mc[1] + depth, z]))
    return out


def build(cage, r1, r2, lip, gap=0.0005, bag=BAG, jaw_extra=(), nose=None):
    if len(lip) != 3 or len(r2) != 12:
        raise ValueError("mouth: the small muzzle loop r2 has 12 vertices and the lip arc is 3 of them (e.g. [1, 2, 3])")
    r2u = list(r2)
    for k in lip:
        p = np.asarray(cage.V[r2[k]]).copy(); p[2] += gap
        r2u[k] = cage.add(p); cage.pinned.update([r2u[k], r2[k]])
    m = lip[1]
    nose_fn = nose or (lambda i, j, p: cage.front(p[0], p[2]))
    ng = cage.cap_grid(r2u[m:] + r2u[:m], 4, 2, nose_fn); cage.fill(ng, 4, 2)
    lo, hi = lip[0] - 1, lip[-1] + 1                                    # the corners
    mouth = [r2[lo]] + [r2[k] for k in lip] + [r2[hi]] + [r2u[k] for k in reversed(lip)]
    mc = np.mean([cage.V[i] for i in mouth], axis=0)
    ring = mouth; rings = []
    for shrink, depth, height in bag:
        ring = cage.bridge_new(ring, sock(cage, mouth, mc, shrink, depth, height), pin=True); rings.append(ring)
    cap = cage.cap_grid(ring[2:] + ring[:2], 2, 2, lambda i, j, p: p); cage.fill(cap, 2, 2)
    cage.pinned.update(cap.values())
    jaw = {i: 1.0 for i in [r1[k] for k in lip] + [r2[k] for k in lip] + list(jaw_extra)}
    for r_ in rings:
        for k in (1, 2, 3):
            jaw[r_[k]] = 1.0
    for i in range(3):
        jaw[cap[(i, 0)]] = 1.0
    for r_ in [mouth] + rings:                    # corners stretch gradually
        for k in (0, 4):
            jaw[r_[k]] = 0.5
    cage.groups["jaw"] = jaw
    cage.groups["freeze"] = set(mouth) | {i for r_ in rings for i in r_} | set(cap.values())
    cage.groups["mouth_inside"] = (set(rings[-1]) | set(cap.values())) - set(mouth)
    return {"mouth": mouth, "upper": r2u, "bag": rings, "cap": cap, "nose": ng}
