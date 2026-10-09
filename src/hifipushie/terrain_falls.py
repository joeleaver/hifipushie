"""Waterfalls on rivers: `rivers.<r>.falls: [{"at": 0..1, "drop": m, "width"?: m}]`.

A fall is a step in the river's own profile, made by a band of hard rock across the valley (the cap rock that stood
while the softer rock below was cut back): a lip at the upstream level, a near-vertical face, an amphitheatre cut back
round a plunge pool at the foot, and the river running on from the pool's level. What the ground needs:
- `profile`: each drop comes out of the reach below its lip (lower and gentler to the next fall or the mouth, which
  keep their heights); the river above keeps its given heights. With too little fall left below (a fall at the mouth,
  `at` 1, off a sea cliff) the reach above is raised instead: the river runs to the cliff's top and falls into the sea.
- `stamp` (in terrain_forms.water, on the finished ground, every build): the lip raised to the upstream level, the
  ground below lowered to the pool's level inside the amphitheatre (its sides rise 1:1 from the pool's edge to the
  ground), the plunge pool carved, the face and lip marked hard rock. The heightfield holds the face as steep as its
  cells allow (one cell across); the tiles' cliff overlay meshes it as rock.
- `T.falls` (meta "falls"): per fall the lip line (two xyz points across the water at the lip's water level), drop,
  width of the sheet, the pool (centre xyz at the pool's water level, radius, depth) and `into` ("river" | "sea" |
  "lake"): what the game needs to draw the falling sheet and the spray.
The water's level (river_water_lines) steps at the lip; easing and the bank rule act on each reach on its own."""

from __future__ import annotations

import math

import numpy as np

from .terrain import smoothstep

META_NOTE = ("per waterfall: lip = two [x, y, z] points across the falling water at the lip's water level (the "
             "sheet's top edge), drop m (lip to the pool's water), width m, flow = the river's direction [x, y], pool = "
             "the plunge pool (xyz = its centre at its water level, radius m, depth m; null in the sea), into = river | "
             "lake | sea. Draw the sheet from the lip down to pool z, spray and foam at the pool. The rivers' water "
             "points step down at the lip.")
FACE_MIN_DEG = 60.0  # the report warns when the built face is gentler than this (cells too coarse for the drop)


def parse(name, r, length):
    """The river's falls, checked: list of {"at", "drop", "width"}, sorted downstream."""
    out = []
    for k, f in enumerate(r.get("falls") or []):
        if not isinstance(f, dict) or "at" not in f or "drop" not in f:
            raise ValueError(f"river {name!r}: falls[{k}] needs \"at\" (0..1 along the river) and \"drop\" (m)")
        at, drop = float(f["at"]), float(f["drop"])
        if not 0.02 <= at <= 1.0:
            raise ValueError(f"river {name!r}: falls[{k}] at {at:g}: 0.02..1 along the river (1 = its mouth)")
        if not 0.5 <= drop <= 200:
            raise ValueError(f"river {name!r}: falls[{k}] drop {drop:g} m: 0.5..200 m")
        w = f.get("width")
        if w is not None and float(w) <= 0:
            raise ValueError(f"river {name!r}: falls[{k}] width {w!r}: metres of falling water, > 0")
        out.append({"at": at, "drop": drop, "width": None if w is None else float(w)})
    out.sort(key=lambda f: f["at"])
    for a, b in zip(out[:-1], out[1:]):
        if (b["at"] - a["at"]) * length < 3 * max(a["drop"], b["drop"]):
            raise ValueError(f"river {name!r}: falls at {a['at']:g} and {b['at']:g} are {(b['at'] - a['at']) * length:.0f} m "
                             f"apart: give a cascade as one fall, or space them at least 3 drops apart")
    return out


def profile(name, h, s, falls):
    """The river's heights with its falls: (h, falls with "i", the first sample below each lip, and "mode").
    Each fall's drop comes out of its own reach below (the river from the lip to the next fall or the mouth runs
    lower and gentler, ending where it did: the river above the fall keeps the heights it was given, which on ground
    the design already made are that ground's: raising them stood the lip in the air, its banks lower than its water,
    and the bank rule flattened the fall away). Where too little fall is left below (a fall at the mouth, off a sea
    cliff) the reach above is raised instead, evenly from the fall before it (or the source) to the lip."""
    if not falls:
        return h, []
    F = float(h[0] - h[-1])
    tot = sum(f["drop"] for f in falls)
    if tot > 0.9 * F:
        raise ValueError(f"river {name!r}: its falls drop {tot:g} m of the {F:.0f} m it falls from source to mouth: "
                         f"keep them under 90% of it (raise the source or lower the mouth)")
    h2 = np.asarray(h, float).copy()
    n = len(h2)
    u = np.asarray(s, float) / max(float(s[-1]), 1e-9)
    idx = [int(np.clip(np.searchsorted(u, f["at"]), 1, n - 1)) for f in falls]
    out = []
    for k, (f, i) in enumerate(zip(falls, idx)):
        D = f["drop"]
        b = idx[k + 1] - 1 if k + 1 < len(idx) else n - 1  # the reach below: samples i..b (b keeps its height)
        top, bot = float(h2[i]), float(h2[b])
        if b > i and top - bot > D / 0.9:  # lowered and compressed below the lip
            h2[i:b] = bot + (h2[i:b] - bot) * (1 - D / (top - bot))
            mode = "below"
        else:  # raised above it, evenly from the reach's start
            a = idx[k - 1] if k > 0 else 0
            w = (u[a:i] - u[a]) / max(u[i - 1] - u[a], 1e-9)
            h2[a:i] = h2[a:i] + D * w
            mode = "above"
        out.append({**f, "i": i, "mode": mode})
    h2 = np.minimum.accumulate(np.where(np.isfinite(h2), h2, 0.0))  # (never uphill)
    return h2, out


def no_steps(h, falls):
    """The profile with the falls' steps taken out (for the grade: a fall isn't a torrent)."""
    h = np.asarray(h, float).copy()
    for f in falls:
        h[f["i"]:] += f["drop"]
    return h


def step_levels(hl, s, falls, slope=0.01):
    """The water's level with every fall's step: below each lip at least `drop` under the level above it, the river
    cut down below the fall (a gorge) until it meets its own level again, never under the mouth's level. Where the
    banks above a lip are lower than the bed (heights drawn over lower ground) the bank rule had flattened the step;
    this keeps the fall at the level the ground holds."""
    hl = np.asarray(hl, float).copy()
    for f in falls:
        i = f["i"]
        line = float(hl[i - 1]) - f["drop"] - slope * (s[i:] - s[i])
        hl[i:] = np.minimum(hl[i:], np.maximum(line, float(hl[-1])))
    return np.minimum.accumulate(hl)


def segments(n, falls):
    """Sample ranges of the reaches between falls."""
    cuts = [0] + [f["i"] for f in falls] + [n]
    return [(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b > a]


def guard(s, falls, cell):
    """Samples whose bank-height rule is lifted: just above each lip (the ground beside them is the pool's) and
    through the amphitheatre below it (its own stamp lowered those banks on the build's first pass)."""
    m = np.zeros(len(s), bool)
    for f in falls:
        R = max(3 * cell, 1.2 * f["drop"])
        i = f["i"]
        m |= (s >= s[i - 1] - R) & (s <= s[i] + 1.5 * R + 6.0)
    return m


def stamp(T, L, falls, hl, half_w, d, i, floor_half):
    """Shape the ground round each fall (see the module's text). hl: the river's water level per sample (eased, with
    its steps), half_w: water half-width per sample, (d, i): every cell's distance to the line and nearest sample.
    Returns the records for T.falls."""
    recs = []
    xy = L.xy
    for k, f in enumerate(falls):
        il = f["i"]  # first sample below the lip
        up, dn = float(hl[il - 1]), float(hl[il])
        drop = up - dn
        t_ = xy[min(il + 1, len(xy) - 1)] - xy[max(il - 2, 0)]
        t_ = t_ / max(np.linalg.norm(t_), 1e-9)
        nrm = np.array([-t_[1], t_[0]])
        lip_xy = 0.5 * (xy[il - 1] + xy[il])
        wl = f["width"] if f["width"] else 2.0 * float(max(half_w[il - 1], half_w[min(il + 1, len(half_w) - 1)]))
        wl = max(wl, 1.5 * T.cell)
        Rp = max(0.5 * wl + 0.15 * drop, 0.6 * drop, 2.5 * T.cell)  # the plunge pool's radius
        Rp = min(Rp, 0.5 * wl + 0.6 * drop + 4.0)
        pool_c = lip_xy + t_ * 0.85 * Rp
        depth = float(np.clip(0.25 * drop + 0.8, 1.2, 6.0))
        Wz = min(0.5 * wl + max(4.0, 0.8 * drop), max(floor_half, 0.5 * wl + 2 * T.cell))  # the rock band's half-length
        # cells round the fall: along (from the lip, + downstream) and across (from the line)
        box = np.hypot(T.X - lip_xy[0], T.Y - lip_xy[1]) < Wz + 2 * Rp + max(drop, 6.0) + 4 * T.cell
        if not box.any():
            continue
        rel = np.stack([T.X[box] - lip_xy[0], T.Y[box] - lip_xy[1]], 1)
        along = rel @ t_
        across = np.abs(rel @ nrm)
        rp = np.hypot(T.X[box] - pool_c[0], T.Y[box] - pool_c[1])
        H = T.H[box].copy()
        sea = ~np.isnan(T.water[box]) & ~T.river_water[box]  # (the sea or a lake already standing there)
        # below the lip: the amphitheatre, the pool's edge and sides rising 1:1 to the ground
        cap = dn + 0.3 + np.maximum(rp - Rp, 0.0)
        H = np.where(along > 0, np.minimum(H, cap), H)
        # the lip: the band of cap rock across the valley at the upstream level (the bank's 1:3 above the water)
        w_across = smoothstep(Wz + 3 * T.cell, Wz, across)
        R_up = max(3 * T.cell, 1.2 * drop)
        w_up = smoothstep(-R_up - 3 * T.cell, -R_up, along) * (along <= 0)
        lip_top = up + 0.3 + 0.33 * np.maximum(across - 0.5 * wl, 0.0)
        H = np.where(along <= 0, np.maximum(H, H + (lip_top - H) * np.clip(w_across * w_up, 0, 1) * (lip_top > H)), H)
        # the water: a shallow sheet over the lip, the pool below
        on_lip = (along <= 0) & (along > -R_up) & (across < 0.5 * wl)
        H = np.where(on_lip, np.minimum(H, up - 0.25), H)
        in_pool = (rp < Rp) & (along > -0.5 * T.cell)
        bed = dn - depth * (1 - (rp / Rp) ** 2)
        H = np.where(in_pool, np.minimum(H, bed), H)
        T.H[box] = H
        wet_new = in_pool & ~sea
        Wt = T.water[box]
        Wt = np.where(wet_new, dn, Wt)
        T.water[box] = Wt
        rw = T.river_water[box]
        T.river_water[box] = rw | wet_new
        face = (np.abs(along) < 2.0 * T.cell + 0.15 * drop) & (across < Wz + T.cell)
        T.hard[box] = T.hard[box] | face
        T.hardness[box] = np.where(face, 0.03, T.hardness[box])
        pm = rp < Rp
        into = "river"
        if pm.any() and sea[pm].mean() > 0.5:  # (falling into standing water: the sea, or a lake)
            sid = (T.lakes.get("sea") or {}).get("id")
            into = "sea" if sid is not None and np.mean(T.lake_id[box][pm & sea] == sid) > 0.5 else "lake"
            dn = float(np.nanmedian(T.water[box][pm & sea]))
            drop = up - dn
        a, b = lip_xy - nrm * 0.5 * wl, lip_xy + nrm * 0.5 * wl
        recs.append({"river": L.name, "at": f["at"], "drop": round(drop, 2), "asked": f["drop"], "width": round(wl, 2),
                     "lip": [[round(float(a[0]), 2), round(float(a[1]), 2), round(up, 2)],
                             [round(float(b[0]), 2), round(float(b[1]), 2), round(up, 2)]],
                     "flow": [round(float(t_[0]), 4), round(float(t_[1]), 4)],
                     "pool": {"xyz": [round(float(pool_c[0]), 2), round(float(pool_c[1]), 2), round(dn, 2)],
                              "radius": round(Rp, 2), "depth": round(depth, 2) if into != "sea" else None},
                     "into": into})
    return recs


def measure(T):
    """Each fall as built: the face's steepest slope across the lip on the channel's line (deg) and the drop from the
    lip's ground to the pool's water."""
    out = []
    for f in getattr(T, "falls", None) or []:
        a, b = np.array(f["lip"][0][:2]), np.array(f["lip"][1][:2])
        c = 0.5 * (a + b)
        t_ = np.array(f["flow"])
        nrm = np.array([-t_[1], t_[0]])
        best = 0.0
        for off in np.linspace(-0.3, 0.3, 5) * f["width"]:
            u = np.arange(-4 * T.cell, 4 * T.cell + 1e-9, T.cell / 4)
            p = c + off * nrm + u[:, None] * t_
            z = T.sample(p)
            run = np.abs(z[4:] - z[:-4]) / T.cell  # (the steepest run over one cell: the heightfield's resolution)
            best = max(best, float(np.degrees(np.arctan(run.max()))))
        out.append({**f, "face_deg": round(best, 1)})
    return out


def report(T):
    lines = []
    for f in measure(T):
        note = ""
        if f["drop"] < 0.8 * f["asked"]:
            note = (f" (the ground holds only {f['drop']:.1f} m here: the land at the lip stands no higher over the water "
                    f"below, or the water below can't go lower (the sea, the mouth's level); put the fall where the "
                    f"ground drops that far, or lower the river's heights below it)")
        elif f["face_deg"] < FACE_MIN_DEG:
            note = (f" (gentler than {FACE_MIN_DEG:.0f} deg: the {T.cell:g} m cells are too coarse for a {f['drop']:g} m "
                    f"drop; a smaller \"cell\" or \"detail\" makes it stand)")
        lines.append(f"fall on {f['river']} at {f['at']:g}: {f['drop']:.1f} m (asked {f['asked']:g}) into the "
                     f"{f['into']}, {f['width']:.1f} m wide, face {f['face_deg']:.0f} deg, pool r {f['pool']['radius']:.1f} m"
                     + (f" {f['pool']['depth']:.1f} m deep" if f['pool']['depth'] else "") + note)
    return lines
