"""Walking through: `check` on the built tiles. Part of the caves (terrain_caves.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from .terrain_caves import Cave

# ---------------------------------------------------------------- walking through
def check(caves: list[Cave], field, height=1.8, radius=0.25, step=0.6, sea=None, paths=None) -> list[str]:
    """Walk a person through every passage (every 0.5 m along its line): the floor under them, headroom, the clear
    width at knee, waist and head height, and the body as a capsule (radius clear of rock from above a step to the top
    of the head, the rule measure.clearance uses in buildings). Steps up to `step` (a scramble in a cave). Water: the
    depth over the floor where it's under the sea (wading to 1 m, then swimming).
    `paths` (a list): each passage's walk appended as {cave, from, to, step_m, points: [[x, y, floor z | null], ...],
    width_m, headroom_m} (the tile manifest's `cave_paths`)."""
    lines = []
    for cv in caves:
        for i, e in enumerate(cv.edges):
            xy, fl0 = e["_xy"], e["_floor"]
            seg = np.linalg.norm(np.diff(xy, axis=0), axis=1)
            sc = np.r_[0, np.cumsum(seg)]
            s = np.arange(0, sc[-1] + 1e-9, 0.5)
            P = np.c_[np.interp(s, sc, xy[:, 0]), np.interp(s, sc, xy[:, 1])]
            f0 = np.interp(s, sc, fl0)
            tang = np.gradient(P, axis=0)
            tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)
            side = np.c_[-tang[:, 1], tang[:, 0]]
            # floor and roof along vertical lines through the passage's middle
            zs = np.arange(-3.0, e["_h"] + 6.0, 0.05)
            col = np.empty((len(P), len(zs), 3))
            col[..., :2] = P[:, None, :]
            col[..., 2] = f0[:, None] + zs[None, :]
            F = field.value(col.reshape(-1, 3)).reshape(len(P), len(zs))
            mid = int(np.searchsorted(zs, 0.5 * e["_h"]))
            floor = np.full(len(P), np.nan)
            head = np.full(len(P), np.nan)
            for j in range(len(P)):
                air = F[j] > 0
                if not air[mid]:
                    continue
                below = np.flatnonzero(~air[:mid])
                above = np.flatnonzero(~air[mid:])
                floor[j] = f0[j] + zs[below[-1] + 1] if len(below) else np.nan
                head[j] = (f0[j] + zs[mid + above[0]] if len(above) else np.inf) - floor[j]
            if sea is not None:  # standing in water: the floor is under the sea
                wet = np.nan_to_num(sea - floor, nan=0.0).clip(0)
            else:
                wet = np.zeros(len(P))
            ok = ~np.isnan(floor)
            base = np.where(ok, floor, f0)
            widths = []
            rs = np.arange(0, 6.0, 0.05)
            for hz in (0.5, 1.0, 1.6):
                both = np.zeros(len(P))
                for sg in (1, -1):
                    pts = P[:, None, :] + sg * side[:, None, :] * rs[None, :, None]
                    q = np.c_[pts.reshape(-1, 2), np.repeat(base + hz, len(rs))]
                    solid = field.value(q).reshape(len(P), len(rs)) < 0
                    both += np.where(solid.any(1), rs[solid.argmax(1)], rs[-1])
                widths.append(both)
            width = np.min(widths, 0)
            # the body as a capsule, at the line or stepped up to 0.8 m aside (a person picks their way through): the
            # best of those offsets that has a floor near this one
            # (tested by sign on a ring `radius` round each point of the body's axis, not by the field's value: with
            # rock relief and blended passages the field is no distance, and read 0.2 in a 1.3 m gap)
            hz = np.linspace(min(step, 0.3) + radius, height - radius, 6)
            ring = np.array([[math.cos(a), math.sin(a)] for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)])
            fits = np.zeros(len(P), bool)
            for off in (0.0, 0.4, -0.4, 0.8, -0.8):
                Q = P + off * side
                pts = (Q[:, None, None, :] + radius * ring[None, None, :, :]) * np.ones((1, len(hz), 1, 1))
                zz = np.broadcast_to((base[:, None] + hz[None, :])[:, :, None], pts.shape[:3])
                q = np.c_[pts.reshape(-1, 2), zz.reshape(-1)]
                ok_ = (field.value(q) > 0).reshape(len(P), -1).all(1)
                under = field.value(np.c_[Q, base - 0.15]) < 0  # standing on rock there, not over a hole
                fits |= ok_ & (under | (off == 0.0))
            clear = np.where(fits, radius, 0.0)
            steps = np.abs(np.diff(base[ok])) if ok.sum() > 1 else np.zeros(1)
            blocked = int((~ok).sum())
            low = int((ok & (head < height)).sum())
            tight = int((ok & ((clear < radius) | (width < 2 * radius))).sum())
            swim = int((wet > 1.0).sum())
            passes = not blocked and not low and not tight and (steps.max() if len(steps) else 0) <= step
            bad_at = np.flatnonzero(~ok | (clear < radius) | (width < 2 * radius) | (head < height))
            if len(steps) and steps.max() > step:
                bad_at = np.r_[bad_at, np.flatnonzero(ok)[int(np.argmax(steps))]]
            stp = ""
            if len(steps) and steps.max() > step:  # (where the largest is: the advice depends on it)
                ks = np.flatnonzero(ok)[int(np.argmax(steps))]
                stp = f" ({steps.max():.2f} m at [{P[ks, 0]:.0f}, {P[ks, 1]:.0f}, {base[ks]:.1f}], {s[ks]:.0f} m along)"
            why = [w for w, bad in (("blocked", blocked), ("low headroom", low), ("too tight", tight),
                                    (f"a step over {step} m{stp}", len(steps) and steps.max() > step)) if bad]
            if paths is not None:  # (the walk as an engine can use it: navigation, lighting, its own walk test)
                r2 = lambda a: [None if not np.isfinite(x) else round(float(x), 2) for x in a]
                paths.append({"cave": cv.name, "from": e["from"], "to": e["to"], "step_m": 0.5,
                              "points": [[round(float(P[q, 0]), 2), round(float(P[q, 1]), 2),
                                          round(float(base[q]), 2) if ok[q] else None] for q in range(len(P))],
                              "width_m": r2(np.where(ok, width, np.nan)),
                              "headroom_m": r2(np.where(ok, np.minimum(head, 99.0), np.nan))})
            lines.append(
                f"{cv.name} {e['from']} -> {e['to']}: {s[-1]:.0f} m, floor {np.nanmin(base):+.1f}..{np.nanmax(base):+.1f}"
                f" m, headroom min {np.nanmin(head[ok]) if ok.any() else float('nan'):.1f} m, width min "
                f"{width[ok].min() if ok.any() else 0:.1f} m, largest step {steps.max() if len(steps) else 0:.2f} m"
                + (f", water up to {wet.max():.1f} m deep" + (f" (swim {swim * 0.5:.0f} m)" if swim else " (wading)")
                   if wet.max() > 0.05 else "")
                + (": a person PASSES" if passes else f": does NOT pass ({', '.join(why)}; first at "
                   f"[{P[bad_at[0], 0]:.0f}, {P[bad_at[0], 1]:.0f}, {base[bad_at[0]]:.1f}], {s[bad_at[0]]:.0f} m along)"))
    return lines
