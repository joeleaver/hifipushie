"""The report and the intent: realism, `report`, `intent` and what is seen from where. Part of the terrain design layer (terrain_design.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import terrain_design
from .terrain import _area
from .terrain_design import region
from .terrain_design_sight import _cells, _compass, _grades, _ij, _label, _switchbacks, lake_seen, sight

def realism(T):
    """Slope statistics against real terrain, and whether each basin's relief fits its ring at a realistic slope."""
    land = np.isnan(T.water)
    sl = T._slope()[land]
    f30, f45, f60 = (sl > 30).mean(), (sl > 45).mean(), (sl > 60).mean()
    W = T.world
    real45 = W["steep"] if W["kind"] else terrain_design.REAL["over_45"]
    what = f"a real {W['kind'].replace('_', ' ')}" if W["kind"] else "rugged real mountains"
    out = [f"realism: median slope {np.median(sl):.0f} deg; {100 * f30:.0f}% of the ground over 30 deg, "
           f"{100 * f45:.0f}% over 45, {100 * f60:.0f}% over 60 ({what}: about {100 * real45:.0f}% over 45)"]
    for name, b in T.basins.items():
        inner = T._slope()[b["inside"] & land]
        out.append(f"realism: inside basin {name}: {100 * (inner > 45).mean():.0f}% over 45 deg, "
                   f"{100 * (inner > 60).mean():.0f}% over 60")
    edge = np.zeros(T.X.shape, bool)
    edge[:, :3] = edge[:, -3:] = True
    edge[:3, :] = edge[-3:, :] = True
    ring = ndimage.binary_dilation(edge, iterations=max(3, int(0.08 * T.size / T.cell)))
    if (T._slope()[ring & land] > 45).mean() > 0.3 and isinstance(T.spec.get("border"), (int, float, dict)):
        T.warnings.append("the frame's edge is fixed low close to high ground, so the ground falls off it in cliffs "
                          "(a moat around the level); open the edge (\"border\": \"open\") or fix it higher")
    if not W["kind"] and f30 < 0.2:  # gentle country: the mountain comparison doesn't apply
        out[0] = f"realism: median slope {np.median(sl):.0f} deg; {100 * f30:.0f}% of the ground over 30 deg (gentle country)"
    elif f45 > 2 * real45 + 0.02:
        T.warnings.append(f"steeper than {what}: {100 * f45:.0f}% of the ground is over 45 deg (~{100 * real45:.0f}% in "
                          f"reality); faces steep all the way down read as draped curtains. Lower the relief, widen the "
                          f"frame, or give walls cliff bands rather than steepness everywhere")
    if W["kind"]:
        mean_face = float(np.mean(sl[sl > 5])) if (sl > 5).any() else 0.0
        lo_f, hi_f = __import__("hifipushie.terrain_world", fromlist=["K"]).KINDS[W["kind"]]["face"][1:]
        if W["kind"] and not lo_f * 0.5 <= mean_face <= hi_f * 1.25:
            T.warnings.append(f"slopes average {mean_face:.0f} deg where there's any slope; a {W['kind'].replace('_', ' ')} "
                              f"is more like {lo_f:.0f}-{hi_f:.0f}: check the relief against the frame")
    for name, b in T.basins.items():
        across = 2 * math.sqrt(b["inside"].sum() / math.pi) * T.cell  # the ring's rough diameter
        floor_share = b["floor"].sum() / max(b["inside"].sum(), 1)
        out.append(f"realism: basin {name}: from the floor's edge up to the crest at {b['avg']:.0f} deg takes a median "
                   f"{b['width']:.0f} m of mountainside; the ring is ~{across:.0f} m across, leaving "
                   f"{100 * floor_share:.0f}% of it as floor")
        if floor_share < 0.6 * T.world["floor"]:  # (alpine valleys really are ~25% floor)
            T.warnings.append(f"basin {name!r}: its walls leave only {100 * floor_share:.0f}% of the ring as floor. The "
                              f"relief ({b['relief']:.0f} m) is big for a ring ~{across:.0f} m across: lower the crest, "
                              f"widen the ring/frame, or make the walls steeper rock (\"walls\": {{\"average\": 45}}: "
                              f"granite-like; real alpine faces average 25-40 deg)")
    return out


def report(T):
    out = realism(T)
    for name, b in T.basins.items():
        on_wall = [n for n, lk in T.lakes.items() if b["wall"][_ij(T, np.array(lk["xy"]))]]
        on_wall += [n for n, st in T.sites.items() if b["wall"][_ij(T, np.array(st["xy"]))]]
        if on_wall:
            T.warnings.append(f"{', '.join(on_wall)} stand(s) on basin {name!r}'s wall, not its floor: its walls take "
                              f"{b['width']:.0f} m (a {b['avg']:.0f} deg mountainside), so the floor is smaller than the ring")
        fl = T.H[b["floor"]]
        wall = b["wall"] & np.isnan(T.water)
        built = float(np.degrees(np.arctan(np.tan(np.radians(T._slope()[wall])).mean()))) if wall.any() else 0.0
        out.append(f"basin {name}: floor {b['floor'].sum() * T.cell ** 2 / 1e6:.2f} km2 from {fl.min():.0f} to "
                   f"{np.percentile(fl, 98):.0f} m, drains to [{b['falls'][0]:.0f}, {b['falls'][1]:.0f}]; "
                   f"walls {b['width']:.0f} m wide, averaging {built:.0f} deg as built (asked {b['avg']:.0f}) with "
                   + (f"{b['bands'] or ('3' if b['character'] == 'tiered' else '1')} cliff band(s) {b['band']:.0f} m tall"
                      if not b.get("zones") else "its profile from the top:"))
        if b.get("zones"):  # each band as built: how much of the wall's height, its median slope, its cover
            sl = T._slope()
            rel = max(float(np.percentile(T.H[b["wall"]], 98) - np.percentile(T.H[b["wall"]], 2)), 1.0)
            parts = []
            for kind, sh, want in b["from_top"]:
                z = b["zones"].get(kind)
                if z is None or not (z & np.isnan(T.water)).any():
                    parts.append(f"{kind}: none left as built")
                    continue
                zz = z & np.isnan(T.water)
                # its share of the wall's height, stretch by stretch round the ring (the whole ring's range mixes the
                # low wall under a col with the high wall under a peak)
                bins = np.floor(b["arc"] / max(150 * T.k, 10 * T.cell)).astype(int)
                shares = []
                for k in np.unique(bins[zz]):
                    wk, zk = b["wall"] & (bins == k), zz & (bins == k)
                    if zk.sum() > 5 and wk.sum() > 20:
                        rk = np.percentile(T.H[wk], 98) - np.percentile(T.H[wk], 2)
                        shares.append((np.percentile(T.H[zk], 95) - np.percentile(T.H[zk], 5)) / max(rk, 1.0))
                share = float(np.median(shares)) if shares else 0.0
                parts.append(f"{kind} {100 * share:.0f}% of the height "
                             f"(asked {100 * sh:.0f}%), median {np.median(sl[zz]):.0f} deg (asked ~{want:.0f})")
            out.append("    " + "; ".join(parts) + f". Zones \"{name}.<band>\"; cover "
                       + (", ".join(getattr(T, "auto_cover", [])) or "from the spec") + " added where no layer covers a band")
    from .terrain_forms import measure_canyon, measure_mesa
    for name, c in getattr(T, "canyons", {}).items():
        m = measure_canyon(T, name)
        w = f"{m['width'][0]:.0f}-{m['width'][1]:.0f} m rim to rim" if m["width"] else "rim to rim not measurable"
        (cs, cf), (ls, lf) = m["cliff"], m["ledge"]
        strata = (f"cliff strata median {cs:.0f} deg ({100 * cf:.0f}% over 60), ledges median {ls:.0f} deg"
                  if np.isfinite(cs) and np.isfinite(ls) else "no strata could be built (too narrow or too shallow for "
                  "its bands: its walls are talus slopes)")
        out.append(f"canyon {name} (measured): {m['depth'] or 0:.0f} m deep at its deepest, {w} (asked "
                   f"{2 * c['half']:.0f}); {strata}, talus at the foot")
        if np.isfinite(cs) and cs < 50:
            T.warnings.append(f"canyon {name!r}: its cliff strata stand at only {cs:.0f} deg as built (the grid and "
                              f"erosion soften them): they read as steep slopes, not cliffs; a finer cell sharpens them")
        if np.isfinite(ls) and ls > 40:
            T.warnings.append(f"canyon {name!r}: its ledges are {ls:.0f} deg as built, too steep to read as ledges: the "
                              f"canyon is too narrow for its depth and bands; widen it or use fewer bands")
    for name, m in getattr(T, "mesas", {}).items():
        mm = measure_mesa(T, name)
        out.append(f"mesa {name} (measured): top {mm['top']:.0f} m (asked {m['top']:.0f}), flat within 2 m over "
                   f"{mm['across']:.0f} m across, cliff median {mm['cliff']:.0f} deg, {mm['rise']:.0f} m above the ground "
                   f"around it")
    for name, p in T.passes.items():
        c, ax = np.array(p["xy"]), np.array(p["axis"])
        sides = []
        worst = None
        for sgn, n, side in ((1, p["ends"][0], "left"), (-1, p["ends"][1], "right")):  # measured as built
            xy = c + sgn * ax * np.arange(0, max(n, 2 * T.cell), T.cell / 2)[:, None]  # the way itself, to its end
            g = _grades(T, xy, window=min(20.0, max(n, T.cell)))
            k = int(np.argmax(g))
            beyond = c + sgn * ax * np.arange(n, n + 60 * T.k + 40, T.cell / 2)[:, None]
            gb = _grades(T, beyond).max() if len(beyond) > 4 else 0
            sides.append(f"{side} {n:.0f} m at up to {100 * g.max():.0f}%, then the ground runs on at "
                         f"{100 * gb:.0f}%" + (" (a route continues)" if gb > p["max_grade"] else ""))
            if g.max() > p["max_grade"] * 1.1 and (worst is None or g.max() > worst[0]):
                worst = (g.max(), xy[k])
        line = (f"pass {name}: through {p['ridge']} at [{c[0]:.0f}, {c[1]:.0f}], saddle at {T.height(c):.0f} m as built"
                + (f" (planned {p['floor']:.0f})" if abs(T.height(c) - p["floor"]) > 3 else "") + ", "
                f"{p['width']:.0f} m wide; the way: " + "; ".join(sides))
        if worst:
            line += f" FAIL: {100 * worst[0]:.0f}% at [{worst[1][0]:.0f}, {worst[1][1]:.0f}]"
        out.append(line)
    for name, (zone, sc) in getattr(T, "rugged_zones", {}).items():
        if zone.sum() < 5:
            out.append(f"rugged {name}: its zone is empty")
            continue
        detail = T.H - ndimage.gaussian_filter(T.H, max(sc, 2 * T.cell) / T.cell)
        dry = np.isnan(T.water)
        gentle = T._slope() < 35
        zin = zone & dry
        rough_in = float(np.std(detail[zin])) if zin.sum() > 5 else float("nan")
        # (compared with dry ground of the same kind outside it: the whole frame's figure included every cliff)
        zout = ~zone & dry & (gentle if (zin & gentle).mean() > 0.5 * max(zin.mean(), 1e-9) else True)
        rough_out = float(np.std(detail[zout])) if zout.sum() > 5 else float("nan")
        big = float(np.percentile(np.abs(detail[zin]), 99)) if zin.sum() > 5 else float("nan")
        out.append(f"rugged {name}: {zone.sum() * T.cell ** 2 / 1e4:.1f} ha of dry ground; its detail at the {sc:.0f} m scale "
                   f"stands +-{rough_in:.1f} m (the biggest crags {big:.1f} m) against +-{rough_out:.1f} m on similar "
                   f"ground elsewhere")
    for name, s in T.sites.items():
        wet = ~np.isnan(T.water)
        dw = (np.hypot(T.X - s["xy"][0], T.Y - s["xy"][1])[wet].min() - s["radius"]) if wet.any() else None
        sea = getattr(T, "sea", None)
        if sea is not None:
            iy = int(np.clip(round((s["xy"][1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1))
            ix = int(np.clip(round((s["xy"][0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1))
            if sea["sd"][iy, ix] < 0:  # (a pad built out into the sea on a fill mound had read "edge 8 m from water")
                T.warnings.append(f"site {name!r}: its centre is {-sea['sd'][iy, ix]:.0f} m out to sea of the coastline: the "
                                  f"pad stands on {s['fill']:.0f} m of fill in the water. Move it inland, or put the "
                                  f"cove/beach where it should stand")
        above = ""
        if dw is not None and dw < max(60.0, s["radius"]):  # the water beside it as it ended up (a lake can settle lower
            # than the level the pad was set from: its spill point, or a pad's cut, drains it)
            dist = np.hypot(T.X - s["xy"][0], T.Y - s["xy"][1])
            k = int(np.argmin(np.where(wet, dist, np.inf)))
            wl = float(T.water.ravel()[k])
            above = f"; {s['level'] - wl:.1f} m above the water beside it"
            want = s.get("above_asked")
            if (want is not None and s["level"] - wl < float(want) - 0.5) or s["level"] - wl < 0:
                T.warnings.append(f"site {name!r} stands {s['level'] - wl:.1f} m above the water beside it"
                                  + (f" (asked above_water {float(want):g})" if want is not None else " (under it: it floods)")
                                  + f": the water settled at {wl:.1f} m. Give the site a level, or move it")
            if s["level"] - wl > 6 and s.get("shore"):
                T.warnings.append(f"site {name!r} was set {s.get('above', 3):.0f} m above {s['shore']!r}, but the water "
                                  f"settled at {wl:.1f} m: it stands {s['level'] - wl:.1f} m above it. Give the lake a "
                                  f"level it can hold (see its line), or the site a level")
        out.append(f"site {name}: pad {2 * s['radius']:.0f} m across at {s['level']:.0f} m, centre "
                   f"[{s['xy'][0]:.0f}, {s['xy'][1]:.0f}]; cut {s['cut']:.0f} m, fill {s['fill']:.0f} m{s.get('note', '')}"
                   + (f"; edge {dw:.0f} m from water" if dw is not None else "") + above)
    for name, R in T.routes.items():
        # the road as built: the ground under its centre line after every carve, not its own planned profile (that
        # always met the limit, so the line said OK where the warnings said nothing connects at that grade)
        # over water the way is a bridge or a ford at its planned height (the channel under it is not the road), and its
        # banks within a few metres of the water are the crossing's ramps
        wet_r = T.sample(R.xy, (~np.isnan(T.water)).astype(float)) > 0.3
        wet_r = ndimage.binary_dilation(wet_r, iterations=max(1, int(round(3.0 / max(T.cell / 2, 0.5)))))
        g = _grades(T, R.xy, h=np.where(wet_r, R.h, T.sample(R.xy)))
        if hasattr(T, "pads"):  # across a site the way is the site's own ground (a village keeping its lie): not the road's
            onp = T.sample(R.xy, T.pads) > 0.5
            g = np.where(onp[:len(g)] | onp[-len(g):], 0.0, g)
        ok = g.max() <= R.props["max_grade"] + 0.01
        turns = _switchbacks(R.xy)
        worst = int(np.argmax(g))
        verdict = "OK" if ok else f"FAIL at [{R.xy[worst, 0]:.0f}, {R.xy[worst, 1]:.0f}]"
        if not ok:  # (a FAIL had no warning at all)
            T.warnings.append(f"route {name!r} FAILS its grade as built: {100 * g.max():.0f}% at [{R.xy[worst, 0]:.0f}, "
                              f"{R.xy[worst, 1]:.0f}] (limit {100 * R.props['max_grade']:.0f}%)")
        if R.props.get("relaxed", 1) > 1:
            verdict += (f" (no way at {100 * R.props['max_grade']:.0f}% exists on the ground: it was found at "
                        f"{100 * R.props['max_grade'] * R.props['relaxed']:.0f}% and graded by cutting and filling)")
        out.append(f"route {name}: {R.props['length']:.0f} m, climbs {np.abs(np.diff(R.h)).sum():.0f} m, "
                   f"{turns} switchbacks, steepest 20 m as built {100 * g.max():.0f}% (limit "
                   f"{100 * R.props['max_grade']:.0f}%) {verdict}; cut up to {R.props['cut']:.0f} m, fill "
                   f"{R.props['fill']:.0f} m")
        for bk in getattr(T, "breaks", []):
            if bk["route"] == name:
                out.append(f"    breaks through a {bk['drop']:.0f} m step at [{bk['at'][0]:.0f}, {bk['at'][1]:.0f}]: "
                           f"{bk['legs']} switchback leg(s) cut into it (cut up to {bk['cut']:.0f} m, fill "
                           f"{bk['fill']:.0f} m); \"breaks\": false to forbid")
        for end, k in (("start", 0), ("end", -1)):
            gap = float(R.h[k] - T.sample(R.xy[k:k + 1] if k == 0 else R.xy[-1:])[0])
            if abs(gap) > 3:
                out.append(f"    its graded bed {'ends' if k else 'starts'} {abs(gap):.0f} m {'above' if gap > 0 else 'below'} "
                           f"the ground at its {end}: the last stretch there is a drop no road at its grade could make "
                           f"(a cliff band in the way: move the stop, or allow a steeper grade)")
        rw = getattr(T, "river_water", None)
        if rw is not None and rw.any():
            # each stretch of the road in river water is one crossing; it's a ford crossing if any of it is in a ford
            # (a road starting on a ford leaves it through the same water: that isn't a second crossing)
            cells = _cells(T, R.xy)
            wet = rw.ravel()[cells] | T.ford_mask.ravel()[cells]
            lab, n = ndimage.label(wet)
            fords, bridges = set(), []
            for k in range(1, n + 1):
                run = lab == k
                if T.ford_mask.ravel()[cells][run].any():
                    fords.update(nm for nm, fd in T.fords.items()
                                 if np.hypot(*(R.xy[run] - fd["xy"]).T).min() < fd["width"] * 1.5)
                else:
                    bridges.append(R.xy[run].mean(0))
            if fords:
                out.append("    crosses at a ford: " + ", ".join(sorted(fords)))
            if bridges:
                out.append(f"    crosses river water at " + ", ".join(f"[{x:.0f}, {y:.0f}]" for x, y in bridges)
                           + ": needs a bridge (or add a ford there)")
        off = np.abs(T.sample(R.xy) - R.h) > 1.0  # the ground under the road isn't the road: legs crowd each other
        if off.any():
            lab, n = ndimage.label(off)
            spots = sorted(((lab == k).sum(), k) for k in range(1, n + 1))[::-1][:3]
            out.append(f"    ground and road disagree by over 1 m along {off.sum() * R.props['length'] / len(R.xy):.0f} m "
                       f"(over 25 m of cut or fill is left for a bridge or tunnel; or legs pass close, or a later carve "
                       f"changed the ground): " + ", ".join(
                           f"[{R.xy[lab == k][:, 0].mean():.0f}, {R.xy[lab == k][:, 1].mean():.0f}]" for _, k in spots))
    for name, W in T.walls.items():
        out.append(f"wall {name} (measured): {W['length'] / 1000:.1f} km of edge, {100 * W['fraction']:.0f}% at least "
                   f"{W['spec'].get('min_slope', 50)} deg for {W['spec'].get('height', 40)} m "
                   f"(raised up to {W['raised']:.0f} m)")
        for xy, length, steep, tall in W["climbable"][:5]:
            out.append(f"    climbable: {length:.0f} m near [{xy[0]:.0f}, {xy[1]:.0f}] (steepest {steep:.0f} deg, its tallest "
                       f"steep stretch {tall:.0f} m)")
    for name, m in T.cover.items():
        line = f"cover {name}: {_area(m.sum() * T.cell ** 2)} equivalent ({100 * m.mean():.0f}% of the frame)"
        zs = [z for z in T.zones][:4]
        if zs:
            line += "; " + ", ".join(f"{z} {100 * (m * region(T, z)).sum() / max(region(T, z).sum(), 1):.0f}%" for z in zs)
        out.append(line)
    if T.cover:  # ground no layer paints: bare (grass-coloured or rock by slope) in the views, a gap in the splats
        tot = np.clip(np.sum([np.clip(m, 0, 1) for m in T.cover.values()], axis=0), 0, 1)
        dry = np.isnan(T.water)
        bare = (tot < 0.2) & dry
        if bare.mean() > 0.05:
            sl = T._slope()[bare]
            out.append(f"cover: {100 * bare.sum() / max(dry.sum(), 1):.0f}% of the dry ground has no layer (slopes there "
                       f"median {np.median(sl):.0f} deg, 10-90% {np.percentile(sl, 10):.0f}-{np.percentile(sl, 90):.0f}): "
                       f"a layer's slope range may skip it (grass/meadow stop near 30 deg, rock starts at ~32)")
    for a in (T.spec.get("probe") or []):  # the finished ground: after sites, roads and erosion
        xy, h, _ = T.address(a)
        out.append(f"probe {a}: [{xy[0]:.0f}, {xy[1]:.0f}] ground as built {h:.0f} m, slope {T._slope()[_ij(T, xy)]:.0f} deg")
    return out


def intent(T):
    out = []
    for name, it in (T.spec.get("intent") or {}).items():
        if "above_flood" in it:
            xy, h, _ = T.address(it["at"])
            if isinstance(it["at"], str) and it["at"] in T.sites:
                h = T.sites[it["at"]]["level"]
            lvls = []
            for L in (L for L in T.lines.values() if L.kind == "river"):
                dry = np.isnan(T.water.ravel()[_cells(T, L.xy)])  # a river's reach under a lake is the lake
                if dry.any():
                    q = cKDTree(L.xy[dry]).query(xy)
                    lvls.append((L.name, L.h[dry][q[1]], q[0]))
            for n, lk in T.lakes.items():
                wet = T.lake_id == lk["id"]
                if wet.any():
                    lvls.append((n, lk["level"], np.hypot(T.X[wet] - xy[0], T.Y[wet] - xy[1]).min()))
            if not lvls:
                out.append(f"intent {name}: no water to be above")
                continue
            wname, wl, _ = min(lvls, key=lambda x: x[2])
            ok = h - wl >= it["above_flood"]
            out.append(f"intent {name}: {h - wl:.0f} m above {wname} (want >= {it['above_flood']}) {'OK' if ok else 'FAIL'}")
        if "path" in it:
            pts = [T.address(a)[0] for a in it["path"]]
            xy = np.vstack([np.linspace(a, b, max(2, int(np.linalg.norm(b - a) / (T.cell / 2))))
                            for a, b in zip(pts, pts[1:])])
            g = _grades(T, xy, 50)
            d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
            w = int(np.argmax(g))
            ok = g.max() <= it["max_grade"]
            out.append(f"intent {name}: straight legs {d[-1]:.0f} m, steepest 50 m {100 * g.max():.0f}% "
                       f"(want <= {100 * it['max_grade']:.0f}%) "
                       + ("OK" if ok else f"FAIL at [{xy[w, 0]:.0f}, {xy[w, 1]:.0f}], {d[w]:.0f} m along "
                                          f"(a route would wind there: use \"routes\")"))
        if "see" in it:
            out += _see(T, name, it)
        if "hide" in it:  # the other way round: must NOT be seen from there (a hidden beach, a secret path)
            out += _see(T, name, {**it, "see": it["hide"]}, hide=True)
    return out


def _see(T, name, it, hide=False):
    """intent "see": from a place (a site: the eye at its centre and eight spots across it) to each target: whether the
    sight line clears the ground; for a summit or mesa how many metres of it show above what's in front and how far it
    stands above the skyline beside and behind it ("min_prominence"); for a lake the share of its surface seen."""
    out = []
    eye = float(it.get("eye", 1.7))
    src = it["from"]
    spots = [("centre", src)]
    if isinstance(src, str) and src in T.sites:
        st = T.sites[src]
        c = np.array(st["xy"])
        spots = [("centre", c.tolist())] + [(_compass(a), (c + 0.7 * st["radius"] * np.array([math.sin(a), math.cos(a)])).tolist())
                                            for a in np.radians(np.arange(0, 360, 45))]
        # only spots on the pad: one over a lip's drop would be an eye in the air
        spots = [sp for sp in spots if T.height(np.array(sp[1])) > st["level"] - 3] or spots[:1]
    want = it.get("min_visible", 0)
    prom = it.get("min_prominence")
    for tgt in it["see"]:
        cove = isinstance(tgt, str) and getattr(T, "sea", None) is not None and tgt in T.sea["coves"]
        lake = isinstance(tgt, str) and (tgt in T.lakes or cove)
        got = []
        for label, xy in spots:
            if lake:  # (a cove is the sea's water in its bay)
                v, tall, dip = (lake_seen(T, xy, "sea", eye, angles=True, mask=T.sea["coves"][tgt]["mask"]) if cove
                                else lake_seen(T, xy, tgt, eye, angles=True))
                got.append((label, v, v > 0, None, tall, dip))
            else:
                r = sight(T, xy, tgt, eye)
                got.append((label, r["visible"], r["visible"] > want, r, 0, 0))
        ok = [g for g in got if g[2]]
        if hide:
            line = (f"intent {name}: {_label(tgt)} hidden from {src}: " + ("seen from none of the spots OK" if not ok else
                    f"FAIL: seen from {len(ok)} of {len(got)} spots (" + ", ".join(g[0] for g in ok[:4]) + ")"))
            out.append(line)
            continue
        summit = not lake and "standout" in got[0][3]
        fmt = ((lambda v: f"{100 * v:.0f}% of its surface") if lake else
               (lambda v: f"{v:.0f} m of it showing" if v > 0 else "hidden") if summit
               else (lambda v: f"clear by {v:.0f} m" if v > 0 else f"blocked, {-v:.0f} m short"))
        best = max(got, key=lambda g: g[1])
        where = f"from {src}" + (f": seen from {len(ok)} of {len(got)} spots across it (centre {fmt(got[0][1])}, best "
                                 f"{best[0]} {fmt(best[1])})" if len(spots) > 1 else f": {fmt(got[0][1])}")
        line = f"intent {name}: {_label(tgt)} {where}; eye {eye:g} m" + ("" if ok else " FAIL")
        if lake and ok:
            b = max(got, key=lambda g: g[4])
            line += (f"; the water seen stands {got[0][4]:.1f} deg tall in the view from the centre ({b[4]:.1f} at best, "
                     f"{b[0]}), its far edge {b[5]:.1f} deg below the horizon")
            if b[4] < 1.0:
                line += " (a thin strip at eye level: lower the water relative to the eye, or bring it closer)"
        r = got[0][3]
        if not ok and r is not None and r.get("block") is not None:
            b = r["block"]
            line += f" (the ground at [{b[0]:.0f}, {b[1]:.0f}] is in the way)"
        if r is not None:
            if summit:
                so = max(g[3]["standout"] for g in got)
                line += f"; its top stands {so:.0f} m above the skyline beside/behind it" if so > 0 else \
                    f"; its top is {-so:.0f} m below the skyline beside or behind it (it doesn't stand out: higher " \
                    f"ground next to it in the view)"
                if prom is not None and so < prom:
                    line += f" FAIL (want >= {prom:g} m)"
            sk = any(g[3]["skyline"] for g in got)
            line += "; nothing directly behind it is higher (on the skyline)" if sk else "; against higher ground behind it"
            if it.get("skyline") and not sk:
                line += " FAIL (wanted on the skyline)"
        out.append(line)
    return out
