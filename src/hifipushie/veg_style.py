"""Vegetation styles: the same grown plant dressed another way (spec `"style": "blobby"` or {"sheet": "blobby",
...overrides}).

A style never touches the growth: the skeleton, height, crown extent and lean are the realistic tree's. It is a SHEET
of ordinary numbers (vegetation_styles/<name>.json, every key overridable in the spec) over a few general operations:

- `wood`: which limbs are drawn (the stoutest `limbs`), how far along them (`reach`), how fat (`radius` x, never
  thinner than `taper_floor` x the limb's base), bends smoothed, ends rounded, bark one flat colour.
- `crown` kind "masses": the twigs' positions are clustered (k-means), each cluster becomes an ellipsoid (its
  principal axes x `spread` + `pad` twig lengths, no semi-axis under 0.75 x `min_feature`), the ellipsoids are joined by a
  smooth union (`blend` m) and meshed (marching cubes on the field, decimated to the budget, vertices put back on the
  field). Closed, no leaves, no alpha. How many masses: the fewest in `masses` [lo, hi] whose silhouette is within
  0.01 IoU of the best (measured against the realistic tree's own silhouette from three sides, at true scale).
- normals: the field's gradient (smooth over each mass and across the blends), mixed `normals` toward the direction
  out of the crown's middle.
- colour: one tone per mass, `tones` steps across the tree by the mass's height (top lighter, a little warmer), as
  COLOR_0 (a multiplier of the material's colour, so season variants only swap the material).
- wind: a mass moves as a whole with the limb it sits on (the limb's branch weight and phase).

What artists do (sources in vegetation_guide.md): blob / low-poly trees are a few smooth-shaded lumps on a trunk;
soft "Ghibli" foliage gets its shading from normals transferred off a rounded proxy hull. Here the proxy IS the
crown (blobby), and later styles put cards on it and take its normals.
"""

from __future__ import annotations

import colorsys
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from . import sdf, veg_leaf, veg_mesh, vegetation

STYLES = Path(__file__).with_name("vegetation_styles")
AZIMUTHS = (0, 60, 120)
AUTUMN = [0.78, 0.56, 0.16]
SEASONS = ("spring", "summer", "autumn", "winter", "snow")
_FIT: dict = {}


def names() -> list[str]:
    return ["realistic"] + sorted(p.stem for p in STYLES.glob("*.json"))


def sheet(spec: dict) -> dict | None:
    """The style's numbers for this spec (the sheet under the spec's own overrides), or None for realistic."""
    st = spec.get("style")
    if not st or st == "realistic":
        return None
    name, over = (st, {}) if isinstance(st, str) else (st.get("sheet", "realistic"), {k: v for k, v in st.items() if k != "sheet"})
    if name == "realistic":
        if over:
            raise ValueError('style overrides need a sheet: {"sheet": "blobby", ...}')
        return None
    p = STYLES / f"{name}.json"
    if not p.exists():
        raise ValueError(f"no vegetation style {name!r}; styles: {names()}")
    base = json.loads(p.read_text())
    for k, v in over.items():
        if k not in base:
            raise ValueError(f"style: unknown key {k!r}; the {name} sheet has {sorted(base)}")
        if isinstance(v, dict):
            bad = set(v) - set(base[k])
            if bad:
                raise ValueError(f"style.{k}: unknown keys {sorted(bad)}; it takes {sorted(base[k])}")
    out = vegetation._merge(base, over)
    con = out.pop("conifer", None)
    if con and conifer(spec):  # the sheet's own numbers for needle trees (tiers, a bare pole), under the spec's overrides
        out = vegetation._merge(vegetation._merge(out, con), {k: v for k, v in over.items() if k != "conifer"})
        out = vegetation._merge(out, over.get("conifer") or {})
    out["name"] = name
    return out


def conifer(spec: dict) -> bool:
    return str((spec.get("leaves") or {}).get("shape", "")).startswith("needle")


def describe(name: str) -> dict:
    return json.loads((STYLES / f"{name}.json").read_text())


# ---------------------------------------------------------------- colour
def styled(rgb, sat: float = 1.0, val: float = 1.0) -> list:
    h, s, v = colorsys.rgb_to_hsv(*[float(c) for c in rgb])
    return [round(c, 4) for c in colorsys.hsv_to_rgb(h, min(s * sat, 1.0), min(v * val, 1.0))]


def lin(c) -> list:
    return [float(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c]


def evergreen(spec: dict) -> bool:
    lf = spec["leaves"]
    return bool(lf.get("evergreen", str(lf.get("shape", "")).startswith("needle")))


def season_color(spec: dict, season: str, st: dict | None = None):
    """The foliage's one colour in a season (sRGB), or None when the plant is bare then. With a style sheet the colour
    goes through its `colour` (saturation, value). spring = `leaves.spring`, else the summer colour mixed toward a
    fresh yellow-green; snow = mixed toward white; autumn = `leaves.autumn` (an evergreen keeps its colour)."""
    lf = spec["leaves"]
    eg = evergreen(spec)
    ss = (st or {}).get("seasons") or {}
    mix = lambda a, b, t: [a[i] * (1 - t) + b[i] * t for i in range(3)]
    if spec.get("plant") == "clump":  # a small plant has its own states through the year (veg_small.SEASONS)
        from . import veg_small
        stt = veg_small.season_state(spec, season)
        if stt is None:
            return None
        c = stt["color"]
        if st:
            co = st.get("colour") or {}
            c = styled(c, co.get("saturation", 1.0), co.get("value", 1.0))
        if season == "snow":
            sn = ss.get("snow") or {"mix": [0.93, 0.95, 0.98], "amount": 0.7}
            c = mix(c, sn["mix"], sn["amount"])
        return [round(float(x), 4) for x in c]
    base = list(lf.get("color", [0.16, 0.3, 0.08]))
    if season in ("winter", "snow", "bare", "dead") and (not eg or season == "dead"):  # (snow = winter + snow laid on it)
        return None
    c = base
    if season == "autumn" and not eg:
        c = list(lf.get("autumn", AUTUMN))
    elif season == "spring":
        sp = ss.get("spring") or {"mix": [0.55, 0.78, 0.25], "amount": 0.45}
        c = list(lf["spring"]) if isinstance(lf.get("spring"), (list, tuple)) else mix(base, sp["mix"], sp["amount"] * (float(sp.get("evergreen", 0.4)) if eg else 1.0))
    if st:
        co = st.get("colour") or {}
        c = styled(c, co.get("saturation", 1.0), co.get("value", 1.0))
    if season == "snow":
        sn = ss.get("snow") or {"mix": [0.93, 0.95, 0.98], "amount": 0.7}
        c = mix(c, sn["mix"], sn["amount"])
    return [round(float(x), 4) for x in c]


def material_color(rgb, st: dict) -> list:
    """The crown material's LINEAR colour factor: the season's colour x the tones' gain, scaled back as a whole when a
    channel would pass 1 (clipped per channel, autumn's orange lost its tone steps and its hue)."""
    c = np.array(lin(rgb)) * color_gain(st)
    return (c / max(1.0, float(c.max()))).tolist()


def srgb(c) -> np.ndarray:
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def season_ramp(spec: dict, season: str, st: dict | None):
    """A season that paints the masses' EDGES another colour (sheet `seasons.<season>.tips` = {"color" sRGB, "band"}:
    an evergreen's spring = the fresh shoots at the rims of its tiers, which a one-colour crown can't show): None, or
    a function u -> (n, 3) linear colour x the tones' gain, scaled back as material_color is. u = TEXCOORD_0.x of a
    styled crown (0 at a mass's foot .. 1 at its top: a cone tier's rim is u 0). The export writes it as a ramp
    texture over u in that season's material (factor x texture = this); looks colour the vertices with it."""
    if not st or (st.get("crown") or {}).get("kind", "masses") == "clouds" or spec.get("plant") == "clump":
        return None
    tp = ((st.get("seasons") or {}).get(season) or {}).get("tips")
    base = season_color(spec, season, st)
    if not tp or base is None:
        return None
    co = st.get("colour") or {}
    tip = styled(tp["color"], co.get("saturation", 1.0), co.get("value", 1.0))
    band = tp.get("band", 0.3)  # u under which the edge colour is whole, fading out by `band` (or [whole, gone])
    b0, band = (float(band[0]), float(band[1])) if isinstance(band, (list, tuple)) else (0.0, float(band))
    g = color_gain(st)
    a0, a1 = np.array(lin(base)) * g, np.array(lin(tip)) * g
    m = max(1.0, float(a0.max()), float(a1.max()))

    def ramp(u):
        x = np.clip((np.asarray(u, float) - b0) / max(band - b0, 1e-6), 0, 1)
        w = 1 - x * x * (3 - 2 * x)
        return (a0[None] * (1 - w[:, None]) + a1[None] * w[:, None]) / m
    return ramp


def ramp_texture(ramp, n: int = 64) -> tuple[np.ndarray, list]:
    """(sRGB image n x 4 x 3 in 0..1, factor rgb) whose product is ramp(u) across the image's width."""
    c = ramp((np.arange(n) + 0.5) / n)
    s = max(float(c.max()), 1e-6)
    img = np.repeat(srgb(c / s)[None], 4, axis=0)
    return img, [s, s, s]


def bark_color(spec: dict, st: dict) -> list:
    co = st.get("colour") or {}
    c = styled((spec.get("bark") or {}).get("color", [0.5, 0.45, 0.4]), co.get("bark_saturation", 1.0), co.get("bark_value", 1.0))
    if co.get("bark_mix"):  # toward one painted colour (anime: flat and cool)
        a = float(co.get("bark_mix_amount", 0.5))
        c = [round(c[i] * (1 - a) + float(co["bark_mix"][i]) * a, 4) for i in range(3)]
    return c


# ---------------------------------------------------------------- wood: the limbs that are drawn
def wood(tree: dict, st: dict, inside=None, size: float = 0.0, feed=None) -> dict:
    """A small tree of the drawn wood only: the trunk's axis, the stoutest first-order limbs and, INSIDE the crown, a
    few branches off each (`stubs`: the stoutest forks, `stub_apart` m apart; each runs into the crown and ends in a
    mass like a limb: what is left standing when the plant is bare). Fattened, bends smoothed.
    The same keys veg_mesh.tubes and veg_export.wind_nodes read; `src` = each node's node in the grown tree; `info` =
    what was left out.
    inside: points -> depth inside the crown (m, positive inside): a limb runs on inside the crown while it stays
    `keep_in` m deep (to `reach_in` of its length), so it ends in a mass, never in the air or out the far side; one
    that never gets `bury` m deep ends where it is deepest. size: the crown masses' mean radius (m): a limb's base
    is at least `limb_mass` x it (toy proportions: a limb as fat as what it carries, not as the pipe model says)."""
    w = st["wood"]
    P, par, rad, ax = tree["pos"], tree["parent"], tree["radius"], tree["axis"]
    kids: dict = {}
    for i in range(1, len(par)):
        kids.setdefault(int(par[i]), []).append(i)
    trunk = np.flatnonzero(ax == ax[1])
    trunk = trunk[trunk >= 1]
    tpos = {int(n): i for i, n in enumerate(trunk)}
    lo, hi = (w["limbs"], w["limbs"]) if isinstance(w["limbs"], int) else w["limbs"]
    allL = vegetation.limbs(tree, 400, 0.0)
    cand = sorted([L for L in allL if int(par[tree["axes"][L["axis"]]["node"]]) in tpos], key=lambda L: -L["diameter"])
    n_keep = 0
    if cand:
        n_keep = int(np.clip(sum(L["diameter"] >= 0.4 * cand[0]["diameter"] for L in cand), lo, hi))
    kept = cand[:n_keep]
    fat, floor = float(w.get("radius", 1.0)), float(w.get("taper_floor", 0.0))

    def length(nodes):
        return np.cumsum(np.linalg.norm(np.diff(np.vstack([P[par[nodes[0]]], P[nodes]]), axis=0), axis=1))

    def cut(nodes, share, least=0):
        cum = length(nodes)
        k = int(np.searchsorted(cum, share * cum[-1])) + 1
        return nodes[: max(min(k, len(nodes)), least, 2)]

    def within(full, share, entered=False, keep=None, must=False):
        """The part of a path drawn: to where it leaves the crown again after entering it."""
        if inside is None:
            return cut(full, float(w.get("reach", 1.0)))
        dep = inside(P[full])
        cum = length(full)
        ins = np.flatnonzero(dep > 0)
        if len(ins) and not entered:  # it stops for good where it first comes out of the crown again (a limb that
            out_ = np.flatnonzero(dep[ins[0]:] < 0)  # crossed a shallow lobe and went on showed as a stick in the air between two masses)
            if len(out_):
                full, dep, cum = full[: ins[0] + out_[0]], dep[: ins[0] + out_[0]], cum[: ins[0] + out_[0]]
        deep = np.flatnonzero(dep >= float(w.get("bury", 0.8)))
        if not len(deep) and not entered:
            if must and float(dep.max()) < float(w.get("keep_in", 0.5)):
                return full[:0]  # (a fork that never gets into the crown is not drawn: its end would stand in the air)
            return full[: max(int(np.argmax(dep)) + 1, 2)]
        i = 0 if entered else int(deep[0])
        end = i
        while end + 1 < len(full) and dep[end + 1] >= (float(w.get("keep_in", 0.5)) if keep is None else keep) and cum[end + 1] <= share * cum[-1]:
            end += 1
        return full[: max(end + 1, 2)]

    top_base = max([tpos[int(par[tree["axes"][L["axis"]]["node"]])] for L in kept], default=0)
    tn = cut(trunk, float(w.get("trunk_reach", 1.0)), top_base + 2)
    r_ref = float(rad[tn[min(len(tn) - 1, max(1, len(tn) // 5))]])
    r_ref = max(r_ref, float(w.get("trunk_mass", 0.0)) * size / fat)  # (a trunk as stout as the crown it carries)
    tfloor = float(w.get("trunk_floor", floor))
    foot = float(w.get("foot", 1.25))  # the root flare, at most this x the trunk (the grown flare made the trunk a cone)
    trad = lambda r_: fat * np.clip(r_, tfloor * r_ref, foot * r_ref)
    pos, parent, radius, axis, order, src = [P[0]], [0], [float(trad(rad[0]))], [0], [0], [0]
    index = {}

    def smooth(pts, r_end=0.0):
        pts = pts.copy()
        for _ in range(int(w.get("smooth", 0))):
            pts[1:-1] = 0.5 * pts[1:-1] + 0.25 * (pts[:-2] + pts[2:])
        if inside is not None and r_end and len(pts) > 2:
            # the end goes under the crown's surface by its own girth: one that lay shallower (a limb running along
            # under a mass, entering only at its tip) showed past the crown from the side. The last 40% bends with it.
            e = pts[-1].copy()
            need = r_end + float(w.get("keep_in", 0.5))
            for _ in range(6):
                dep = float(inside(e[None])[0])
                if dep >= need:
                    break
                g = grad(inside, e[None])[0]
                e = e + g / max(float(np.linalg.norm(g)), 1e-9) * min(need - dep, 1.0)
            t = np.clip((np.linspace(0, 1, len(pts)) - 0.6) / 0.4, 0, 1)
            pts = pts + (t * t * (3 - 2 * t))[:, None] * (e - pts[-1])
        return pts

    def add(nodes, root, pts, rr, ai, od):
        prev = root
        for n, p_, r_ in zip(nodes, pts, rr):
            index[int(n)] = len(pos)
            pos.append(p_)
            parent.append(prev)
            radius.append(float(r_))
            axis.append(ai)
            order.append(od)
            src.append(int(n))
            prev = len(pos) - 1

    tp = smooth(np.vstack([P[0], P[tn]]))[1:]
    tr = trad(rad[tn])
    zc = float(P[trunk[top_base], 2]) if kept else 0.35 * float(tree["height"])  # the crown's base on the trunk
    zt = max(float(tp[-1, 2]), 1e-3)
    if w.get("s_bend"):  # cartoon: one S along the bare trunk, `s_bend` x its height out and back (0 at the foot and the crown)
        ang = 2 * math.pi * float(vegetation._u(np.array([int(tree["spec"].get("seed", 1)) + 11], np.uint64), 99)[0])
        dvec = np.array([math.cos(ang), math.sin(ang), 0.0])
        zz = np.clip(tp[:, 2] / max(zc, 1e-3), 0, 1)
        tp = tp + (float(w["s_bend"]) * zc * np.sin(2 * math.pi * zz))[:, None] * dvec[None]
    tn_ = tn
    if w.get("taper") or w.get("flare"):  # cartoon: thick at the foot, thin at the top, a flared root foot
        # the flare: a concave root foot `flare_height` trunk diameters tall ((1 - s)^2.5: it rises steeply off the ground
        # and runs into the trunk; an exponential over 12% of the bole read as a mound). The trunk's first stretch is
        # resampled finely enough to carry the curve.
        fh = float(w.get("flare_height", 1.25)) * 2 * fat * r_ref  # (in trunk diameters: the bole's own girth, not the flared foot's)
        if w.get("flare") and fh > 0:
            seg = np.vstack([P[0], tp])
            zs_ = seg[:, 2]
            k_ = int(np.searchsorted(zs_, fh)) + 1
            new_p, new_n, new_r = [], [], []
            for j in range(1, len(seg)):
                a_, b_ = seg[j - 1], seg[j]
                if j <= k_:
                    m_ = int(max(1, math.ceil(np.linalg.norm(b_ - a_) / max(fh / 5, 0.05))))
                    for q in range(1, m_):
                        new_p.append(a_ + (b_ - a_) * q / m_); new_n.append(tn[j - 1]); new_r.append(float(tr[j - 1]))
                new_p.append(b_); new_n.append(tn[j - 1]); new_r.append(float(tr[j - 1]))
            tp, tn_, tr = np.array(new_p), np.array(new_n), np.array(new_r)
        z_ = np.clip(tp[:, 2], 0, None)
        if w.get("flare"):  # (the grown root swelling goes: the drawn flare replaces it)
            above = np.flatnonzero(z_ >= fh)
            if len(above):
                tr = np.where(z_ < fh, np.minimum(tr, tr[above[0]]), tr)
        tf_ = lambda zz: (1 + float(w.get("taper", 0.0)) * (1 - zz / zt)) * (1 + float(w.get("flare", 0.0)) * (1 - np.clip(zz / max(fh, 1e-3), 0, 1)) ** 2.5)
        tr = tr * tf_(z_)
    add(tn_, 0, tp, tr, 0, 0)
    if w.get("taper") or w.get("flare"):
        # the foot node goes UNDER the ground, as wide as the flare carried on down: a round cone ends in a sphere, and a
        # sphere centred on the ground reads as a bulb / mound; this way the flare meets the ground still widening
        dz = 0.3
        r1 = float(tr[0]) / float(tf_(np.array([max(float(tp[0, 2]), 1e-3)]))[0])
        slope = (float(tr[0]) - r1 * float(tf_(np.array([0.0]))[0])) / max(float(tp[0, 2]), 1e-3)
        r_g = r1 * float(tf_(np.array([0.0]))[0])
        pos[0] = P[0] - np.array([0, 0, dz])
        radius[0] = float(r_g + max(-slope, 0.0) * dz)
    drawn = [np.vstack([P[0], P[tn]])]
    n_ax, n_stub = 1, 0
    for L in kept:
        n0 = tree["axes"][L["axis"]]["node"]
        full = vegetation.stout_path(tree, n0, kids)
        root = index[int(par[n0])]
        r0 = max(fat * float(rad[n0]), float(w.get("limb_min", 0.0)) * fat * r_ref, float(w.get("limb_mass", 0.0)) * size)
        r0 = min(r0, 0.8 * radius[root])
        # (inside the crown its axis stays its own girth + keep_in under the surface: 0.5 m down, a 0.5 m limb showed through)
        nodes = within(full, float(w.get("reach_in", 0.9)), keep=float(w.get("keep_in", 0.5)) + floor * r0)
        pts = smooth(np.vstack([pos[root], P[nodes]]), floor * r0)[1:]
        rr = np.maximum(r0 * rad[nodes] / max(float(rad[n0]), 1e-9), floor * r0)
        add(nodes, root, pts, rr, n_ax, 1)
        n_ax += 1
        drawn.append(np.vstack([pos[root], pts]))
        if inside is None or not w.get("stubs"):
            continue
        # stubby branches off this limb, inside the crown: the stoutest side branches whose foot is in a mass
        on = set(int(q) for q in nodes)
        sides = []
        for q in nodes[1:]:
            for c in kids.get(int(q), ()):
                if c not in on and rad[c] >= 0.15 * rad[q]:
                    sides.append((float(rad[c]), int(c)))
        sides.sort(reverse=True)
        took = []
        for _, c in sides:
            if len(took) >= int(w["stubs"]):
                break
            if any(np.linalg.norm(P[c] - P[t_]) < float(w.get("stub_apart", 1.5)) for t_ in took):
                continue
            sroot = index[int(par[c])]
            sr0 = min(max(fat * float(rad[c]), float(w.get("stub_radius", 0.6)) * radius[sroot]), 0.8 * radius[sroot])
            sn = within(vegetation.stout_path(tree, c, kids), float(w.get("stub_reach", 0.6)), must=True,
                        keep=float(w.get("keep_in", 0.5)) + floor * sr0)  # (as a limb: on into the crown, ending in a mass)
            if len(sn) < 2 or length(sn)[-1] < float(w.get("stub_min", 1.0)):
                continue
            took.append(c)
            spts = smooth(np.vstack([pos[sroot], P[sn]]), floor * sr0)[1:]
            add(sn, sroot, spts, np.maximum(sr0 * rad[sn] / max(float(rad[c]), 1e-9), floor * sr0), n_ax, 2)
            n_ax += 1
            n_stub += 1
            drawn.append(np.vstack([pos[sroot], spts]))
    n_fed = 0
    if feed is not None and len(feed) and w.get("feed"):
        # every clump is carried: a clump with no drawn wood within `feed` x its radius gets the grown tree's own path
        # to it (from the nearest grown node in it back down to the drawn wood). Without it outer clumps floated.
        fr = float(w["feed"])
        for c, rc in feed:
            if np.linalg.norm(np.array(pos) - c, axis=1).min() <= fr * rc:
                continue
            near = np.flatnonzero(np.linalg.norm(P - c, axis=1) < 0.7 * rc)
            if not len(near):
                continue
            n = int(near[np.argmax(rad[near])])  # (its stoutest wood: the branch that carries it)
            path = []
            while n not in index and n > 0:
                path.append(n)
                n = int(par[n])
            if n not in index or not path:
                continue
            path = np.array(path[::-1])
            root = index[n]
            fr0 = min(max(fat * float(rad[path[0]]), float(w.get("feed_radius", 0.0)) * radius[root]), 0.8 * radius[root])
            fpts = smooth(np.vstack([pos[root], P[path]]))[1:]
            add(path, root, fpts, np.maximum(fr0 * rad[path] / max(float(rad[path[0]]), 1e-9), floor * fr0), n_ax, 2)
            n_ax += 1
            n_fed += 1
            drawn.append(np.vstack([pos[root], fpts]))
    src = np.array(src)
    drawn_len = float(sum(np.linalg.norm(np.diff(d_, axis=0), axis=1).sum() for d_ in drawn))
    total_len = float(np.linalg.norm(P - P[par], axis=1).sum())
    return {"pos": np.array(pos), "parent": np.array(parent), "radius": np.array(radius), "axis": np.array(axis),
            "order": np.array(order), "ends": np.zeros(len(pos), bool), "key": tree["key"][src], "height": tree["height"],
            "spec": tree["spec"], "dead": None, "src": src,
            "info": {"limbs_kept": len(kept), "limbs": len(allL), "axes": int(len(tree["axes"])), "axes_kept": n_ax, "stubs": n_stub, "fed": n_fed,
                     "wood_m": round(drawn_len, 1), "wood_m_grown": round(total_len, 1),
                     "limb_names": [L["name"] for L in kept]}}


def wood_tubes(mini: dict, st: dict, f: float = 1.0) -> dict:
    """The drawn wood as plain tubes (quick: what the fit's silhouettes use)."""
    lo, hi = st["wood"].get("sides", [6, 12])
    sides = (max(3, int(round(lo * f))), max(4, int(round(hi * f))))
    return veg_mesh.tubes(mini, sides=sides, simplify=0.25 / max(f, 0.2), tip=1.0, tile=(0.5, 1.0))


def _segments(mini: dict, orders=(0, 1, 2)) -> list:
    """Per axis of those orders: (a, b, ra, rb, node of b) for its segments, with the foot run 0.3 m into the ground."""
    out = []
    for ai in np.unique(mini["axis"]):
        if mini["order"][np.flatnonzero(mini["axis"] == ai)[-1]] not in orders:
            continue
        nodes = np.flatnonzero(mini["axis"] == ai)
        nodes = nodes[nodes >= 1]
        par = mini["parent"][nodes]
        a, b = mini["pos"][par].copy(), mini["pos"][nodes]
        ra, rb = mini["radius"][par].copy(), mini["radius"][nodes]
        if ai != mini["axis"][1]:
            ra[0] = rb[0]  # (a branch starts at its own girth, on its parent's axis: the union makes the fork)
        else:
            a[0] = a[0] - [0, 0, 0.3]
        out.append((a, b, ra, rb, nodes))
    return out


def wood_field(segs: list, p: np.ndarray, blend: float, node: bool = False):
    """The drawn wood as one field: each axis a chain of round cones (hard union along it: a smooth one bulged at every
    joint), the axes joined by a smooth union of `blend` x the branch's girth: forks are fillets, ends are round.
    node=True also returns the nearest segment's end node per point."""
    d = np.full(len(p), 1e3)
    nn = np.zeros(len(p), np.int64)
    for a, b, ra, rb, nodes in segs:
        k = blend * float(rb[0])
        lo, hi = np.minimum(a, b).min(0) - ra.max() - k - 0.3, np.maximum(a, b).max(0) + ra.max() + k + 0.3
        m = np.flatnonzero(((p >= lo) & (p <= hi)).all(1))
        if not len(m):
            continue
        da = np.full(len(m), 1e3)
        na = np.zeros(len(m), np.int64)
        for i in range(len(a)):
            ab = b[i] - a[i]
            t = np.clip((p[m] - a[i]) @ ab / max(float(ab @ ab), 1e-12), 0, 1)
            di = np.linalg.norm(p[m] - (a[i] + t[:, None] * ab), axis=1) - (ra[i] + t * (rb[i] - ra[i]))
            better = di < da
            da = np.where(better, di, da)
            na = np.where(better, nodes[i], na)
        nn[m] = np.where(da < d[m], na, nn[m])
        d[m] = sdf.smin(d[m], da, k)
    return (d, nn) if node else d


def mesh_field(fn, lo, hi, voxel: float) -> tuple:
    """Marching cubes of a field over a box: (V, F) with faces outward (the field is negative inside)."""
    from skimage import measure
    C = 4  # a coarse pass first: the field is only evaluated exactly in coarse cells the surface can reach
    nc = [int(np.ceil((hi[i] - lo[i] + 3 * voxel) / (C * voxel))) + 1 for i in range(3)]
    cax = [lo[i] - voxel + (np.arange(nc[i]) + 0.5) * C * voxel - 0.5 * voxel for i in range(3)]
    Gc = np.stack(np.meshgrid(*cax, indexing="ij"), -1).reshape(-1, 3)
    vc = np.concatenate([fn(Gc[i: i + 400000]) for i in range(0, len(Gc), 400000)]).reshape(nc)
    vol = np.repeat(np.repeat(np.repeat(vc, C, 0), C, 1), C, 2)
    ax = [lo[i] - voxel + np.arange(nc[i] * C) * voxel for i in range(3)]
    near = np.argwhere(np.abs(vol) < 1.6 * C * voxel)  # (fields here are steeper than a distance by at most ~1.3)
    Gn = np.stack([ax[i][near[:, i]] for i in range(3)], 1)
    vol[near[:, 0], near[:, 1], near[:, 2]] = np.concatenate([fn(Gn[i: i + 400000]) for i in range(0, len(Gn), 400000)]) if len(Gn) else []
    V, F, _, _ = measure.marching_cubes(vol, 0.0, spacing=(voxel,) * 3)
    V = V + [ax[0][0], ax[1][0], ax[2][0]]
    pick = np.arange(0, len(F), max(1, len(F) // 500))
    fn_ = np.cross(V[F[pick, 1]] - V[F[pick, 0]], V[F[pick, 2]] - V[F[pick, 0]])
    if (np.einsum("ij,ij->i", fn_, grad(fn, V[F[pick]].mean(1))) < 0).mean() > 0.5:
        F = F[:, ::-1]
    return V, np.ascontiguousarray(F)


def grad(fn, p, h=0.02):
    g = np.empty_like(p)
    for a in range(3):
        e = np.zeros(3)
        e[a] = h
        g[:, a] = fn(p + e) - fn(p - e)
    return g / (2 * h)


def onto(fn, V, steps: int = 2):
    """Vertices back onto a field's surface (decimation pulls a rounded surface in), and its normals there."""
    for _ in range(steps):
        g = grad(fn, V)
        V = V - g * (fn(V) / np.maximum((g * g).sum(1), 1e-9))[:, None]
    g = grad(fn, V)
    return V, g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)


def wood_dense(mini: dict, st: dict, orders=(0, 1)) -> dict | None:
    """The drawn wood of those orders meshed from its field, at full resolution. Trunk and limbs are one mesh; the forks
    (order 2: drawn only when the plant is bare) another, each fork starting inside its limb."""
    segs = _segments(mini, orders)
    if not segs:
        return None
    blend = float(st["wood"].get("blend", 0.6))
    fn = lambda q: np.maximum(wood_field(segs, q, blend), -0.3 - q[:, 2])  # (cut flat 0.3 m under the foot)
    rmin = float(min(rb.min() for _, _, _, rb, _ in segs))
    voxel = float(st["wood"].get("voxel") or np.clip(0.4 * rmin, 0.05, 0.12))
    r = float(mini["radius"].max())
    V, F = mesh_field(fn, mini["pos"].min(0) - r - 0.4, mini["pos"].max(0) + r + 0.2, voxel)
    return {"V": V, "F": F, "segs": segs, "blend": blend, "voxel": voxel, "axes": len(segs)}


def capsules(mini: dict, limit: int = 24) -> list[dict]:
    """Collision for the wood that is drawn: straight pieces along the trunk and each limb."""
    caps = []
    for ai in np.unique(mini["axis"]):
        nodes = np.flatnonzero(mini["axis"] == ai)
        nodes = nodes[nodes >= 1]
        pts = np.vstack([mini["pos"][mini["parent"][nodes[0]]], mini["pos"][nodes]])
        rr = np.r_[mini["radius"][nodes[0]], mini["radius"][nodes]]
        keep = veg_mesh._rdp(pts, np.maximum(rr, 0.02) * 0.6, rr * 0 + 1)
        for i0, i1 in zip(keep[:-1], keep[1:]):
            if rr[i1] < 0.3 * rr[i0] and np.linalg.norm(pts[i1] - pts[i0]) < rr[i0]:
                continue  # (the rounded end's rings)
            caps.append({"a": pts[i0].round(3).tolist(), "b": pts[i1].round(3).tolist(), "ra": round(float(rr[i0]), 3), "rb": round(float(rr[i1]), 3)})
    return caps[:limit]


# ---------------------------------------------------------------- crown masses
def in_leaf(tree: dict) -> dict:
    """The same tree in summer: a style is fitted to the plant in leaf whatever season it is shown in (a winter tree
    has no twigs to fit masses to, and its limbs must still be the summer tree's)."""
    if tree["spec"].get("season", "summer") == "summer":
        return tree
    return {**tree, "spec": {**tree["spec"], "season": "summer"}}


def leaf_points(tree: dict) -> tuple[np.ndarray, float]:
    """Where the foliage is: the middle of every living twig, and the twig's length (m)."""
    tree = in_leaf(tree)
    tw = veg_leaf.place_live(tree)
    tl = float({**veg_leaf.TWIG, **(tree["spec"]["leaves"].get("twig") or {})}["length"])
    if not len(tw["pos"]):
        return np.zeros((0, 3)), tl
    return tw["pos"] + tw["frame"][:, :, 1] * (0.5 * tl * tw["scale"])[:, None], tl


def _kmeans(X: np.ndarray, k: int, iters: int = 30) -> np.ndarray:
    """Labels of a k-means from a farthest-point start (no randomness: the same tree gives the same masses)."""
    C = [X[np.argmin(np.linalg.norm(X - X.mean(0), axis=1))]]
    d = np.linalg.norm(X - C[0], axis=1)
    for _ in range(1, k):
        C.append(X[int(np.argmax(d))])
        d = np.minimum(d, np.linalg.norm(X - C[-1], axis=1))
    C = np.array(C)
    lab = np.zeros(len(X), int)
    for _ in range(iters):
        D = ((X[:, None, :] - C[None]) ** 2).sum(-1)
        new = D.argmin(1)
        if (new == lab).all() and _:
            break
        lab = new
        for j in range(k):
            if (lab == j).any():
                C[j] = X[lab == j].mean(0)
    return lab


def masses(X: np.ndarray, k: int, st: dict, twig: float, seed: int = 0) -> list[dict]:
    """k ellipsoids over the foliage points: [{"c", "R" (rows = axes), "r" (semi-axes), "n" points}], lowest first."""
    cr = st["crown"]
    ztop = float(X[:, 2].max()) + 0.5 * twig
    if "tiers" in (cr.get("kind"), cr.get("masses_kind")):  # (`masses_kind`: leaf clouds on tiers)
        # stacked dumplings: one upright egg per height band (round above its widest level, flat below it: `tier_under`
        # x the band), seated low in its band, so each overhangs the narrower top of the one below with an undercut.
        # `trunk_show` m of trunk stay bare under the lowest; bands differ in height by `tier_uneven` (the seed's own
        # numbers); the top one is a cap no slimmer than `tier_cap` x its height.
        show = float(cr.get("trunk_show", 0.0))
        z0, z1 = max(float(np.percentile(X[:, 2], 1)), show), float(X[:, 2].max())
        un = float(cr.get("tier_uneven", 0.0))
        jit = (vegetation._u(np.arange(3 * k + 3).astype(np.uint64) + np.uint64(1000 * (seed + 1)), 91) - 0.5) * 2 if un else np.zeros(3 * k + 3)
        frac = (np.arange(k + 1) / k) ** float(cr.get("tier_power", 1.0))
        frac[1:-1] += 0.5 * un * jit[1:k] * np.diff(frac).min()
        edges = z0 + (z1 - z0) * frac
        out = []
        for j in range(k):
            hgt = edges[j + 1] - edges[j]
            Q = X[(X[:, 2] >= edges[j] - 1e-9) & (X[:, 2] <= edges[j] + 0.6 * hgt)]  # (its width is its lower part's: the band's top is the next one's business)
            if len(Q) < 4:
                Q = X[(X[:, 2] >= edges[j] - 1e-9) & (X[:, 2] <= edges[j + 1] + 1e-9)]
            if len(Q) < 4:
                continue
            c = np.array([Q[:, 0].mean(), Q[:, 1].mean(), edges[j] + float(cr.get("tier_seat", 0.4)) * hgt])
            wj = 1.0 + 0.35 * un * jit[k + 1 + j]
            rx, ry = [wj * float(cr.get("spread", 1.75)) * float(Q[:, i].std()) + float(cr.get("pad", 0.5)) * twig for i in (0, 1)]
            rz = max(float(cr.get("tier_height", 0.75)) * hgt, float(cr.get("roundness", 0.0)) * max(rx, ry) * 0.5)
            if j == k - 1:
                rz = max(ztop - c[2], 0.3 * hgt)
                rx, ry = [max(v, float(cr.get("tier_cap", 0.0)) * rz) for v in (rx, ry)]
            r = np.maximum(np.array([rx, ry, rz]), 0.75 * float(cr.get("min_feature", 0.6)))
            c[2] -= max(0.0, c[2] + r[2] - ztop)
            e = {"c": c, "R": np.eye(3), "r": r, "n": int(len(Q))}
            if cr.get("tier_under") is not None:
                e["down"] = float(np.clip(float(cr["tier_under"]) * hgt, 0.3 * float(cr.get("min_feature", 0.6)), max(c[2] - show, 0.05) if j == 0 else 1e9))
            if cr.get("tier_shape") == "cone":
                # a saw-tooth tier (cartoon firs): a cone standing on its band's foot, `cone_height` x the band tall (it
                # reaches into the next band: the outline steps in and out), its rim cut into `teeth` points in plan
                # (`zig` x its radius in and out): the zigzag outline
                z0 = max(edges[j] - 0.15 * hgt, show) if j else max(edges[0], show)
                Hc = float(cr.get("cone_height", 1.6)) * hgt if j < k - 1 else max(ztop - z0, hgt)
                e["cone"] = {"z0": float(z0), "h": float(min(Hc, ztop - z0)), "teeth": int(cr.get("teeth", 9)), "zig": float(cr.get("zig", 0.12)),
                             "phase": float(vegetation._u(np.array([j + 7 * (seed + 1)], np.uint64), 93)[0])}
                e["c"] = np.array([c[0], c[1], z0 + 0.3 * e["cone"]["h"]])
                e["r"] = np.array([rx, ry, 0.5 * e["cone"]["h"]])
                e.pop("down", None)
            out.append(e)
        return _scallops(out, cr, seed)
    if len(X) > 6000:  # (a cluster's shape doesn't need every twig)
        X = X[np.argsort(vegetation._u(np.arange(len(X)).astype(np.uint64), 3))[:6000]]
    es = float(cr.get("edge_share", 0.0))
    if es > 0:
        # two sizes of cloud: k big ones over the crown's inner foliage, `edge_count` x k small ones over the outer
        # `edge_share` of it (by its distance out of the crown's middle, in the crown's own proportions); all clouds
        # of one size read as one layer
        r_ = np.linalg.norm((X - X.mean(0)) / np.maximum(X.std(0), 1e-6), axis=1)
        outer = r_ >= np.quantile(r_, 1 - es)
        ke = max(int(round(float(cr.get("edge_count", 1.5)) * k)), 1)
        lab = np.empty(len(X), int)
        lab[~outer] = _kmeans(X[~outer], k)
        lab[outer] = k + _kmeans(X[outer], ke)
        k = k + ke
    else:
        lab = _kmeans(X, k)
    out = []
    for j in range(k):
        Q = X[lab == j]
        if len(Q) < max(4, (0.003 if es > 0 else 0.01) * len(X)):
            continue
        c = Q.mean(0)
        ev, U = np.linalg.eigh(np.cov((Q - c).T) + np.eye(3) * 1e-6)
        r = float(cr.get("spread", 1.75)) * np.sqrt(np.maximum(ev, 0)) + float(cr.get("pad", 0.5)) * twig
        r = np.maximum(r, 0.75 * float(cr.get("min_feature", 0.6)))
        r = np.maximum(r, float(cr.get("roundness", 0.0)) * r.max())  # (a flat cluster as a disc read as a lily pad, not a lump)
        ez = math.sqrt(float(((U.T[:, 2] * r) ** 2).sum()))  # its vertical half extent
        c[2] -= max(0.0, c[2] + ez - ztop)  # never taller than the tree: a rounded-up top mass sinks to the tree's own height
        out.append({"c": c, "R": U.T.copy(), "r": r, "n": int(len(Q))})
    out.sort(key=lambda e: float(e["c"][2]))
    out = _scallops(out, cr, seed)
    if cr.get("core") and len(out) > 1:  # the foliage is a shell: a mass in its hollow makes the crown one body with lobes
        c = X.mean(0)
        ev, U = np.linalg.eigh(np.cov((X - c).T) + np.eye(3) * 1e-6)
        r = float(cr["core"]) * np.sqrt(np.maximum(ev, 0))
        r = np.maximum(r, float(cr.get("roundness", 0.0)) * r.max())
        ez = math.sqrt(float(((U.T[:, 2] * r) ** 2).sum()))
        c[2] -= max(0.0, c[2] + ez - ztop)
        out.append({"c": c, "R": U.T.copy(), "r": r, "n": 0, "core": True})
    return out


def _scallops(out: list, cr: dict, seed: int) -> list:
    """`scallop` small round bumps standing on each mass's surface (cartoon clumps: a scalloped edge), each bump an
    ellipsoid of `scallop_size` x its mass's mean radius, `of` = its mass's index (one clump for tone, id and wind).
    Placed on the sides and top (a clump's underside stays plain), sunk `scallop_sink` of their radius."""
    n = int(cr.get("scallop", 0) or 0)
    if n <= 0:
        return out
    base = list(out)
    for j, e in enumerate(base):
        if e.get("core") or e.get("cone"):
            continue
        rm = float(e["r"].mean())
        rb = float(cr.get("scallop_size", 0.4)) * rm
        U = _fibonacci(3 * n)
        U = U[U[:, 2] > -0.25][:n] if (U[:, 2] > -0.25).sum() >= n else U[:n]
        ph = 2 * math.pi * float(vegetation._u(np.array([j + 1000 * (seed + 1)], np.uint64), 95)[0])
        Rz = np.array([[math.cos(ph), -math.sin(ph), 0], [math.sin(ph), math.cos(ph), 0], [0, 0, 1.0]])
        U = U @ Rz.T
        nn = U / e["r"]
        nn /= np.linalg.norm(nn, axis=1, keepdims=True)
        for u, nv in zip(U, nn):
            p = e["c"] + (e["r"] * u) @ e["R"] - float(cr.get("scallop_sink", 0.45)) * rb * (nv @ e["R"])
            out.append({"c": p, "R": np.eye(3), "r": np.full(3, rb), "n": 0, "of": j, "join": float(cr.get("scallop_join", 0.35))})
    return out


def _fibonacci(n: int) -> np.ndarray:
    i = np.arange(n) + 0.5
    z = 1 - 2 * i / n
    a = i * math.pi * (3 - math.sqrt(5))
    r = np.sqrt(np.maximum(1 - z * z, 0))
    return np.c_[r * np.cos(a), r * np.sin(a), z]


def _cone_d(e: dict, p: np.ndarray) -> np.ndarray:
    """A saw-tooth tier's (approximate) distance: a cone on a flat foot with a zigzag rim in plan."""
    cn = e["cone"]
    q = p - np.array([e["c"][0], e["c"][1], cn["z0"]])
    rho = np.linalg.norm(q[:, :2], axis=1)
    th = np.arctan2(q[:, 1], q[:, 0]) / (2 * math.pi) * cn["teeth"] + cn["phase"]
    tri = 4 * np.abs(th - np.floor(th) - 0.5) - 1  # (-1 .. 1, a point at every whole tooth)
    ang = np.arctan2(q[:, 1], q[:, 0])
    R0 = np.sqrt((e["r"][0] * np.cos(ang)) ** 2 + (e["r"][1] * np.sin(ang)) ** 2) * (1 + cn["zig"] * tri)
    H = max(cn["h"], 1e-3)
    Rh = R0 * (1 - np.clip(q[:, 2], 0, None) / H)
    side = (rho - Rh) / np.sqrt(1 + (R0 / H) ** 2)
    return np.maximum(side, -q[:, 2])


def blend_of(ells: list[dict], st: dict) -> float:
    """The crown union's smoothing radius (m): `blend`, or `blend_share` x the masses' mean radius when that is more
    (a fixed 1 m between 5 m masses left eight balloons)."""
    cr = st["crown"]
    size = float(np.mean([e["r"].mean() for e in ells if not e.get("core") and "of" not in e])) if ells else 0.0
    return max(float(cr.get("blend", 0.5)), float(cr.get("blend_share", 0.0)) * size)


def field(ells: list[dict], p: np.ndarray, blend: float, each: bool = False, floor: float | None = None):
    """The crown's field at points (negative inside): the ellipsoids' (approximate) distances under a smooth union.
    each=True also returns the (n, k) distances. floor: nothing under this height."""
    D = np.empty((len(p), len(ells)))
    for j, e in enumerate(ells):
        if e.get("cone"):
            D[:, j] = _cone_d(e, p)
            continue
        q = (p - e["c"]) @ e["R"].T
        r_ = e["r"]
        if e.get("down") is not None:  # an egg: its own (shorter) semi-axis below the middle
            r_ = np.tile(e["r"], (len(q), 1))
            r_[q[:, 2] < 0, 2] = e["down"]
        k0 = np.linalg.norm(q / r_, axis=1)
        k1 = np.linalg.norm(q / (r_ ** 2), axis=1)
        D[:, j] = np.where(k1 > 1e-9, k0 * (k0 - 1.0) / np.maximum(k1, 1e-9), -float(e["r"].min()))
    d = D[:, 0].copy()
    for j in range(1, len(ells)):
        d = sdf.smin(d, D[:, j], blend * float(ells[j].get("join", 1.0)))  # (a scallop bump joins its clump crisper: `join`)
    if floor is not None:
        d = np.maximum(d, floor - p[:, 2])
    return (d, D) if each else d


def _gradient_old(ells, p, blend, floor, h=0.02):
    g = np.empty_like(p)
    for a in range(3):
        e = np.zeros(3)
        e[a] = h
        g[:, a] = field(ells, p + e, blend, floor=floor) - field(ells, p - e, blend, floor=floor)
    return g / (2 * h)


def crown_mesh(ells: list[dict], st: dict, voxel: float | None = None, floor: float | None = None) -> dict:
    """The masses as one closed surface: marching cubes of the field ({"V", "F"}, outward)."""
    cr = st["crown"]
    blend = blend_of(ells, st)
    lo = np.min([e["c"] - e["r"].max() for e in ells], axis=0) - blend
    hi = np.max([e["c"] + e["r"].max() for e in ells], axis=0) + blend
    voxel = voxel or float(cr.get("voxel") or 0) or float(np.clip((hi - lo).max() / 80, 0.06, 0.3))
    V, F = mesh_field(lambda q: field(ells, q, blend, floor=floor), lo, hi, voxel)
    return {"V": V, "F": F, "voxel": voxel, "blend": blend}


def color_gain(st: dict) -> float:
    """What the crown material's colour is multiplied by (COLOR_0 holds each mass's tone divided by it)."""
    cr = st.get("crown") or {}
    if cr.get("gradient"):  # (pixar: a gradient base-to-tip, warmer at the tips)
        return float(max(cr["gradient"]) * (1 + abs(float(cr.get("warm_tip", 0.1)))) * (1 + abs(float(cr.get("hue_jitter", 0.0)))))
    return float(max(cr.get("tone", [0.85, 1.15])) * (1 + abs(float(cr.get("warm_top", 0.0)))))


def _decimate(V, F, target: int):
    if len(F) <= target:
        return V, F
    import pyfqmr
    for agg in (5, 7, 9):  # (at 5 a long smooth pole stalled at 2.4x its target)
        s = pyfqmr.Simplify()
        s.setMesh(np.ascontiguousarray(V, np.float64), np.ascontiguousarray(F, np.int32))
        s.simplify_mesh(target_count=int(target), aggressiveness=agg, preserve_border=True, verbose=False)
        V2, F2, _ = s.getMesh()
        V, F = np.asarray(V2, float), np.asarray(F2, np.int64)
        if len(F) <= 1.08 * target:
            break
    return V, F


# ---------------------------------------------------------------- silhouettes: is it still the same tree?
def _fill(mask):
    any_, left, right = vegetation._rows(mask)
    f = np.zeros_like(mask)
    for i in np.flatnonzero(any_):
        f[i, left[i]: right[i] + 1] = True
    return f


def mesh_mask(meshes: list, azimuth: float, x0: float, z1: float, px: float, shape) -> np.ndarray:
    """Triangle meshes [(V, F)] seen from the side, in a given frame (as vegetation.silhouette's)."""
    from PIL import Image, ImageDraw
    im = Image.new("L", (shape[1], shape[0]), 0)
    d = ImageDraw.Draw(im)
    c, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    for V, F in meshes:
        X = (V[:, 0] * c + V[:, 1] * s_ - x0) * px
        Y = (z1 - V[:, 2]) * px
        T = np.stack([X[F], Y[F]], -1).reshape(len(F), 6)
        for t in T.tolist():
            d.polygon(t, fill=255)
    return np.asarray(im) > 0


def reference(tree: dict, azimuths=AZIMUTHS, px: float = 10.0) -> list:
    """The realistic tree's silhouettes in leaf (mask, frame) per azimuth: what every style is held against."""
    return [vegetation.silhouette(in_leaf(tree), az, px, leaves=True, pad=3.0) for az in azimuths]


def compare(tree: dict, meshes: list, azimuths=AZIMUTHS, px: float = 10.0, refs: list | None = None) -> dict:
    """The styled meshes against the realistic tree in leaf, from the side at true scale (same frame, feet together):
    IoU of the row-filled outlines per azimuth, and both heights and crown widths (m)."""
    ious, wr, ws = [], [], []
    refs = refs or reference(tree, azimuths, px)
    for az, (A, fr) in zip(azimuths, refs):
        B = mesh_mask(meshes, az, fr["x0"], fr["z1"], px, A.shape)
        A, B = _fill(A), _fill(B)
        ious.append(float((A & B).sum() / max((A | B).sum(), 1)))
        wr.append(float(A.sum(1).max() / px))
        ws.append(float(B.sum(1).max() / px))
    top = max(float(V[:, 2].max()) for V, _ in meshes)
    return {"iou": round(float(np.mean(ious)), 3), "iou_by_azimuth": [round(v, 3) for v in ious], "azimuths": list(azimuths),
            "height_m": [round(float(tree["height"]), 2), round(top, 2)],
            "width_m": [round(float(np.mean(wr)), 2), round(float(np.mean(ws)), 2)]}


# ---------------------------------------------------------------- the fit (once per tree and sheet) and the dress (per LOD)
def fit(tree: dict, st: dict) -> dict:
    """The styled plant's parts before any budget: {"mini": the drawn wood, "wood": its dense mesh, "ells": the
    crown's masses (or []), "dense": the crown at full resolution, "match": compare()'s numbers, "tried": IoU per
    number of masses}."""
    key = hashlib.sha1(json.dumps(st, sort_keys=True).encode()).hexdigest()
    hit = _FIT.get(id(tree))
    if hit is not None and hit[0] is tree and hit[1] == key:
        return hit[2]
    mini = wood(tree, st)
    Wm = wood_tubes(mini, st)
    wm = (Wm["V"], Wm["F"])
    X, tl = leaf_points(tree)
    out = {"mini": mini, "ells": [], "dense": None, "tried": {}, "twigs": int(len(X)), "blend": 0.0}
    floor = float(tree["spec"]["leaves"].get("clear", 0.03)) + 0.02
    refs = reference(tree)
    cr = st.get("crown") or {}
    if "tiers" in (cr.get("kind"), cr.get("masses_kind")) and cr.get("trunk_show"):
        floor = max(floor, 0.6 * float(cr["trunk_show"]))  # (the union's blend may sag under the lowest tier: never to the ground)
    if len(X) >= 8 and cr.get("kind", "masses") in ("masses", "tiers", "clouds"):
        lo, hi = (cr["masses"], cr["masses"]) if isinstance(cr["masses"], int) else cr["masses"]
        cands = {}
        for k in range(int(lo), int(hi) + 1, max(int(cr.get("masses_step", 1)), 1)):
            ells = masses(X, k, st, tl, int(tree["spec"].get("seed", 1)))
            n_ = sum(not e.get("core") and "of" not in e for e in ells)
            if not ells or n_ in cands:
                continue
            cm = crown_mesh(ells, st, voxel=None if lo == hi else 0.3, floor=floor)
            cands[n_] = (ells, compare(tree, [wm, (cm["V"], cm["F"])], refs=refs)["iou"])
        best = max(v[1] for v in cands.values())
        k = min(k_ for k_, v in cands.items() if v[1] >= best - 0.01)
        out["tried"] = {k_: v[1] for k_, v in cands.items()}
        ells = out["ells"] = cands[k][0]
        out["dense"] = crown_mesh(ells, st, floor=floor)
        out["floor"] = floor
        out["blend"] = bl = out["dense"]["blend"]
        size = float(np.mean([e["r"].mean() for e in ells if not e.get("core") and "of" not in e]))
        mini = out["mini"] = wood(tree, st, lambda q: -field(ells, q, bl, floor=floor), size,
                                    feed=[(e["c"], float(e["r"].mean())) for e in ells if not e.get("core") and "of" not in e])
    in_leaf_forks = bool(st["wood"].get("forks_in_leaf"))  # (a style whose crown has gaps: the forks show in leaf too, one wood mesh)
    out["wood"] = wood_dense(mini, st, (0, 1, 2) if in_leaf_forks else (0, 1))
    out["forks"] = None if in_leaf_forks else wood_dense(mini, st, (2,))
    shown = [(out["dense"]["V"], out["dense"]["F"])] if out["dense"] else []
    if out["ells"] and cr.get("kind") == "clouds":  # what is drawn is the cards, not the proxy they stand on
        from . import veg_cloud
        C_ = veg_cloud.clouds(tree, st, out["ells"], int((1 - float(st["wood"].get("share", 0.25))) * int(st.get("budget", 12000))), floor=floor)
        shown = [(C_["V"], C_["F"])]
    out["match"] = compare(tree, [(out["wood"]["V"], out["wood"]["F"])] + shown, refs=refs)
    if len(_FIT) > 6:
        _FIT.clear()
    _FIT[id(tree)] = (tree, key, out)
    return out


def dress(tree: dict, st: dict, triangles: int | None = None, season: str = "summer") -> dict:
    """The plant in its style within a triangle count (default the sheet's `budget`): {"wood": {"V", "F", "N", "uv",
    "node"...}, "wood_wind": (trunk, branch, phase, flutter) per wood vertex, "crown": None | {"V", "F", "N", "uv",
    "col" (n, 3 multiplier), "wind", "mass"}, "mini", "info"}. A lower count takes triangles off the same two
    surfaces: the masses and the limbs themselves never change with the LOD."""
    from . import veg_export
    if tree.get("clump"):
        return dress_clump(tree, st, triangles, season)
    ft = fit(tree, st)
    full = int(st.get("budget", 5000))
    triangles = int(triangles or full)
    mini = ft["mini"]
    share = float(st["wood"].get("share", 0.25)) if ft["ells"] else 1.0
    wd_ = ft["wood"]
    wfn = lambda q: np.maximum(wood_field(wd_["segs"], q, wd_["blend"]), -0.3 - q[:, 2])
    wn = veg_export.wind_nodes(mini)

    def surface(dn, target):
        fn_ = wfn if dn is wd_ else (lambda q: wood_field(dn["segs"], q, dn["blend"]))
        V_, F_ = _decimate(dn["V"], dn["F"], max(int(target), 12 * dn["axes"], 64))  # (under ~60 a lone pole became a spike)
        V_, N_ = onto(fn_, V_)
        nd_ = wood_field(dn["segs"], V_, dn["blend"], node=True)[1]
        z_ = np.zeros(len(V_))
        return {"V": V_, "F": F_, "N": N_, "uv": np.zeros((len(V_), 2)), "node": nd_, "tan": np.tile([0, 0, 1.0], (len(V_), 1)),
                "radius": mini["radius"][nd_], "dead": z_,
                "wind": (np.clip(V_[:, 2] / max(tree["height"], 1e-6), 0, 1) ** 1.5, wn["branch"][nd_], wn["phase"][nd_], z_)}

    W = surface(wd_, share * triangles)
    Vw, Fw = W["V"], W["F"]
    out = {"wood": W, "wood_wind": W["wind"], "crown": None, "mini": mini, "forks": None, "cards": None}
    if ft.get("forks") is not None and not evergreen(tree["spec"]):
        # the limbs' forks: drawn only when the plant is bare (in leaf they cluttered the crown's underside), within
        # what the hidden crown's triangles would have cost
        out["forks"] = surface(ft["forks"], float(st["wood"].get("forks_share", 0.3)) * triangles)
    info = {"style": st["name"], **mini["info"], "masses": sum(not e.get("core") and "of" not in e for e in ft["ells"]), "core": any(e.get("core") for e in ft["ells"]),
            "blend_m": round(ft["blend"], 2), "twigs": ft["twigs"], "match": ft["match"],
            "masses_tried": ft["tried"], "wood_triangles": int(len(Fw)), "crown_triangles": 0, "budget": triangles,
            "forks_triangles": int(len(out["forks"]["F"])) if out["forks"] else 0, "kind": (st.get("crown") or {}).get("kind", "masses")}
    if ft["ells"] and season_color(tree["spec"], season, st) is not None and st["crown"].get("kind") == "clouds":
        from . import veg_cloud
        cr, ells = st["crown"], [e for e in ft["ells"] if not e.get("core") and "of" not in e]
        C_ = veg_cloud.clouds(tree, st, ells, max(triangles - len(Fw), 0), lod=triangles / max(full, 1), floor=ft["floor"])
        V = C_["V"]
        wd = st.get("wind") or {}
        anchor = np.array([int(np.argmin(np.linalg.norm(mini["pos"] - e["c"], axis=1))) for e in ells])
        b_m = np.maximum(wn["branch"][anchor], float(wd.get("mass", 0.3)))
        ph_m = np.where(mini["order"][anchor] > 0, wn["phase"][anchor], vegetation._u(np.arange(len(ells)).astype(np.uint64) + np.uint64(int(tree["spec"].get("seed", 1))), 57))
        mv = C_["mass"]
        # a long slow sweep (the clump with its limb, top more than bottom) and the cards' rims fluttering
        out["crown"] = {**C_, "tone": C_["step"],
                        "wind": (np.clip(V[:, 2] / max(tree["height"], 1e-6), 0, 1) ** 1.5,
                                 np.clip(b_m[mv] + float(wd.get("squash", 0.0)) * (C_["grad"][:, 0] - 0.5), 0, 1), ph_m[mv],
                                 float(wd.get("flutter", 0.5)) * C_["rim"] * (0.5 + 0.5 * np.array(cr.get("layers", [1.0]))[C_["layer"]]))}
        info["crown_triangles"] = int(len(C_["F"]))
        info.update(cards=C_["cards"], card_fill=round(C_["atlas"]["fill"], 3), card_m=round(C_["card_m"], 2), layers=len(cr.get("layers", [])),
                    tones=int(len(np.unique(C_["step"]))), kind="clouds")
        info["mass_list"] = [{"center": e["c"].round(2).tolist(), "radii": np.sort(e["r"])[::-1].round(2).tolist()} for e in ells]
    elif ft["ells"] and season_color(tree["spec"], season, st) is not None:
        cr, ells = st["crown"], ft["ells"]
        blend = ft["blend"]
        cfn = lambda q: field(ells, q, blend, floor=ft["floor"])
        n_big = int(round(int(cr.get("big_leaves", 0) or 0) * min(1.0, triangles / max(full, 1)) ** 0.7))  # (fewer at lower LODs)
        n_base = sum("of" not in e for e in ells)
        cards_share = float((cr.get("cards") or {}).get("share", 0.6)) if cr.get("cards") else 0.0  # (pixar: the leaf cards' share of the crown)
        V0, F = _decimate(ft["dense"]["V"], ft["dense"]["F"], max(int((triangles - len(Fw) - 112 * n_big) * (1 - cards_share)), 16 * n_base))
        V, N = onto(cfn, V0)
        # a vertex beside an undercut can land on the other sheet (a tier's underside and the dome below it are a few
        # decimetres apart): faces turned over by the move get their vertices back where the decimation left them
        fn0 = np.cross(V0[F[:, 1]] - V0[F[:, 0]], V0[F[:, 2]] - V0[F[:, 0]])
        for _ in range(3):
            fn1 = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
            bad = np.einsum("ij,ij->i", fn0, fn1) < 0.2 * np.linalg.norm(fn0, axis=1) * np.linalg.norm(fn1, axis=1)
            far = np.linalg.norm(V - V0, axis=1) > 0.5 * max(blend, 0.3)
            back = np.zeros(len(V), bool)
            back[F[bad].ravel()] = True
            back |= far
            if not back.any():
                break
            V[back] = V0[back]
        g_ = grad(cfn, V)
        N = g_ / np.maximum(np.linalg.norm(g_, axis=1, keepdims=True), 1e-9)
        d, D = field(ells, V, blend, each=True, floor=ft["floor"])
        cen = np.mean([e["c"] for e in ells], axis=0)
        o = V - cen
        o /= np.maximum(np.linalg.norm(o, axis=1, keepdims=True), 1e-9)
        wN = float(cr.get("normals", 0.0))
        N = (1 - wN) * N + wN * o
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        own = np.array([int(e.get("of", j)) for j, e in enumerate(ells)])  # (a scallop bump belongs to its clump)
        bases = np.flatnonzero(own == np.arange(len(ells)))
        rank = np.zeros(len(ells), int)
        rank[bases] = np.arange(len(bases))
        mass = own[D.argmin(1)]
        k = len(bases)
        wc = float(cr.get("normals_clump", 0.0))
        if wc:  # cartoon: flat-ish shading per clump, the normal straight out of its clump's middle
            oc = V - np.array([e["c"] for e in ells])[mass]
            oc /= np.maximum(np.linalg.norm(oc, axis=1, keepdims=True), 1e-9)
            N = (1 - wc) * N + wc * oc
            N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
        # one tone per mass, in steps by the mass's height
        cz = np.array([e["c"][2] for e in ells])[own]
        tones = int(max(1, cr.get("tones", 3)))
        t = (cz - cz.min()) / max(float(np.ptp(cz)), 1e-6)
        ti = np.minimum((t * tones).astype(int), tones - 1) if k > 1 else np.zeros(len(cz), int)
        tf = ti / max(tones - 1, 1)
        t0, t1 = cr.get("tone", [0.85, 1.15])
        warm = float(cr.get("warm_top", 0.0))
        mcol = np.stack([(t0 + (t1 - t0) * tf) * (1 + warm * (tf - 0.5) * 2), t0 + (t1 - t0) * tf, (t0 + (t1 - t0) * tf) * (1 - warm * (tf - 0.5) * 2)], 1)
        hj = float(cr.get("hue_jitter", 0.0))
        if hj:  # cartoon: the hue moves a little per clump (toward yellow or blue-green), the tone steps stay
            sd = int(tree["spec"].get("seed", 1))
            hu = (vegetation._u(own.astype(np.uint64) + np.uint64(1000 * (sd + 1)), 97) - 0.5) * 2 * hj
            mcol = mcol * np.stack([1 + hu, np.ones_like(hu), 1 - hu], 1)
        gain = float(max(t0, t1) * (1 + abs(warm)) * (1 + abs(hj)))  # COLOR_0 must stay within 0..1 (glTF): the material's colour carries the rest
        mcol = mcol / gain
        ez = np.array([math.sqrt(float(((e["R"][:, 2] * e["r"]) ** 2).sum())) for e in ells])
        ed = np.array([e["down"] if e.get("down") is not None else ez[j] for j, e in enumerate(ells)])
        ez, ed = np.maximum(ez, ez[own]), np.maximum(ed, ed[own])
        u = np.clip((V[:, 2] - (cz[mass] - ed[mass])) / (ez[mass] + ed[mass]), 0, 1)
        uv = np.stack([u, (rank[mass] + 0.5) / k], 1)
        # wind: a mass goes with the wood it sits on, as a whole; soft between masses so nothing tears
        wd = st.get("wind") or {}
        mp = mini["pos"]
        anchor = np.array([int(np.argmin(np.linalg.norm(mp - ells[own[j]]["c"], axis=1))) for j in range(len(ells))])
        b_m = np.maximum(wn["branch"][anchor], float(wd.get("mass", 0.3)))
        ph_m = np.where(mini["order"][anchor] > 0, wn["phase"][anchor], vegetation._u(own.astype(np.uint64) + np.uint64(int(tree["spec"].get("seed", 1))), 57))
        sw = np.exp(-(D - D.min(1, keepdims=True)) / max(0.5 * blend, 1e-3))
        sw /= sw.sum(1, keepdims=True)
        trunk_w = np.clip(V[:, 2] / max(tree["height"], 1e-6), 0, 1) ** 1.5
        branch_w = sw @ b_m + float(wd.get("squash", 0.0)) * (u - 0.5)
        out["crown"] = {"V": V, "F": F, "N": N, "uv": uv, "col": mcol[mass], "gain": gain, "mass": mass, "tone": ti,
                        "wind": (trunk_w, np.clip(branch_w, 0, 1), sw @ ph_m, np.full(len(V), float(wd.get("flutter", 0.0))))}
        if n_big > 0:
            bl = _big_leaves(tree, cr, out["crown"], ells, n_big)
            if bl is not None:
                C0 = out["crown"]
                n0 = len(C0["V"])
                out["crown"] = {**C0, "V": np.vstack([C0["V"], bl["V"]]), "F": np.vstack([C0["F"], bl["F"] + n0]), "N": np.vstack([C0["N"], bl["N"]]),
                                "uv": np.vstack([C0["uv"], bl["uv"]]), "col": np.vstack([C0["col"], bl["col"]]), "mass": np.r_[C0["mass"], bl["mass"]],
                                "wind": tuple(np.r_[C0["wind"][i], bl["wind"][i]] for i in range(4))}
                info["big_leaves"] = bl["n"]
                F = out["crown"]["F"]
        if cr.get("cards"):
            _shell_and_cards(tree, st, out, cfn, ft["floor"], max(triangles - len(Fw) - len(F), 0), info, triangles / max(full, 1))
        info["crown_triangles"] = int(len(F)) + (int(len(out["cards"]["F"])) if out.get("cards") else 0)
        info["tones"] = int(len(np.unique(ti)))
        info["mass_list"] = [{"center": e["c"].round(2).tolist(), "radii": np.sort(e["r"])[::-1].round(2).tolist(), "tone": int(ti[j]),
                              **({"bumps": int((own == j).sum() - 1)} if (own == j).sum() > 1 else {}),
                              **({"core": True} if e.get("core") else {})} for j, e in enumerate(ells) if "of" not in e]
    info["triangles"] = info["wood_triangles"] + info["crown_triangles"]
    out["info"] = info
    return out


def thickness(fn, V, N, reach: float = 4.0, step: float = 0.2) -> np.ndarray:
    """How far a ray from each surface point straight in (-N) runs inside the field `fn` (m, capped at `reach`): what
    light passes through a canopy shell there (thin lobes and rims glow, the core does not)."""
    t = np.full(len(V), reach)
    inside = np.ones(len(V), bool)
    for s_ in np.arange(step, reach + step / 2, step):
        live = np.flatnonzero(inside)
        if not len(live):
            break
        out_ = fn(V[live] - (s_ + 0.01) * N[live]) > 0
        t[live[out_]] = s_
        inside[live[out_]] = False
    return t


def _shell_and_cards(tree: dict, st: dict, out: dict, cfn, floor: float, budget: int, info: dict, lod: float = 1.0) -> None:
    """Pixar's crown: the closed shell (the masses) painted with a gradient base-to-tip (sheet `crown.gradient`
    [dark, light], warmer at the tips by `warm_tip`), TEXCOORD_3 = (that gradient, thickness m), and a layer of real
    leaf cards on its outside (veg_cloud.shell_cards) in out["cards"]."""
    from . import veg_cloud
    cr = st["crown"]
    C = out["crown"]
    V, N = C["V"], C["N"]
    cen = 0.5 * (V.min(0) + V.max(0))
    half = np.maximum(0.5 * (V.max(0) - V.min(0)), 1e-6)
    r_ = np.clip(np.linalg.norm((V - cen) / half, axis=1), 0, 1)
    zn = np.clip((V[:, 2] - V[:, 2].min()) / max(float(np.ptp(V[:, 2])), 1e-6), 0, 1)
    tg = np.clip(0.55 * r_ ** 1.5 + 0.45 * zn, 0, 1)  # (base / inside dark -> tips / top light)
    g0, g1 = cr.get("gradient", [0.55, 1.1])
    wt = float(cr.get("warm_tip", 0.1))
    tn = g0 + (g1 - g0) * tg
    col = np.stack([tn * (1 + wt * tg), tn, tn * (1 - wt * tg)], 1) * C["col"] / np.maximum(C["col"].mean(1, keepdims=True), 1e-6)  # (the masses keep only their hue)
    gain = color_gain(st)
    th = thickness(cfn, V, N, float(cr.get("thick_reach", 4.0)))
    out["crown"] = {**C, "col": np.clip(col / gain, 0, 1), "gain": gain, "grad": np.c_[tg, th]}
    K = veg_cloud.shell_cards(tree, st, V, C["F"], N, budget, lod=lod, floor=floor, along=tg)
    if K is not None:
        sw = st.get("wind") or {}
        # a card moves with the shell under it, its rim fluttering
        from scipy.spatial import cKDTree
        idx = cKDTree(V).query(K["V"])[1]
        K["wind"] = (C["wind"][0][idx], C["wind"][1][idx], C["wind"][2][idx], float(sw.get("flutter", 0.4)) * K["rim"])
        K["mass"] = C["mass"][idx]
        out["cards"] = K
        info.update(cards=K["cards"], card_m=round(K["card_m"], 2), card_fill=round(K["atlas"]["fill"], 3), cards_triangles=int(len(K["F"])),
                    thickness_m=[round(float(np.percentile(th, 10)), 2), round(float(np.median(th)), 2), round(float(np.percentile(th, 90)), 2)])


def _big_leaves(tree: dict, cr: dict, C: dict, ells: list, n: int) -> dict | None:
    """A few BIG single leaves standing out of the crown's silhouette (cartoon: Wind Waker / Animal Crossing trees carry
    a handful of oversized leaves on their outline): the species' leaf outline, `big_leaf` x its length, as thin closed
    plates rooted `big_leaf_sink` of their length inside the crown at its outermost points (sides and top, farthest
    apart), pointing out and up. Each takes the colour, clump id, gradient and wind of the crown where it is rooted
    (its tip flutters)."""
    lf = tree["spec"]["leaves"]
    V, N = C["V"], C["N"]
    if len(V) < 10:
        return None
    L = float(cr.get("big_leaf", 4.0)) * float(lf.get("length", 0.1))
    W = L * float(lf.get("width", 0.5))  # (`leaves.width` is a share of the length)
    cen = 0.5 * (V.min(0) + V.max(0))
    half = np.maximum(0.5 * (V.max(0) - V.min(0)), 1e-6)
    out_ = np.linalg.norm((V - cen) / half, axis=1)  # (out of the crown's middle in its own proportions: sides and top alike)
    # on a clump's EDGE: facing out of the crown (sides and top), not under it
    cand = np.flatnonzero((out_ >= np.quantile(out_, 0.75)) & (N[:, 2] > -0.1) & (np.einsum("ij,ij->i", N, (V - cen) / half) > 0.4 * out_))
    if not len(cand):
        return None
    pick = [int(cand[np.argmax(out_[cand])])]
    d = np.linalg.norm(V[cand] - V[pick[0]], axis=1)
    while len(pick) < min(n, len(cand)):
        j = int(np.argmax(d))
        pick.append(int(cand[j]))
        d = np.minimum(d, np.linalg.norm(V[cand] - V[cand[j]], axis=1))
    from . import veg_leaf
    t = np.linspace(0, 1, 15)
    shp = str(lf.get("shape", "ovate"))
    prof = veg_leaf._profile(shp if shp in ("ovate", "triangular", "lanceolate", "lobed", "round") else "ovate", t, int(lf.get("lobes", 4)))
    # a cartoon leaf: the species' outline softened toward a plain ovate one (sharp lobes read as a saw blade), rounded at
    # the tip, never thinner than a fat ellipse
    prof = (1 - float(cr.get("big_leaf_soft", 0.5))) * prof + float(cr.get("big_leaf_soft", 0.5)) * veg_leaf._profile("ovate", t, 0)
    prof = np.maximum(prof, 0.45 * np.sin(np.pi * t) ** 0.8)
    poly = np.vstack([np.c_[t * L, 0.5 * W * prof], np.c_[t[::-1][1:-1] * L, -0.5 * W * prof[::-1][1:-1]]])
    up = np.array([0, 0, 1.0])
    Vs, Fs, Ns, uvs, cols, ms, ws, n0 = [], [], [], [], [], [], [], 0
    for q, i in enumerate(pick):
        nrm = N[i] / max(float(np.linalg.norm(N[i])), 1e-9)
        # the leaf points out of the clump (a little up) and its FACE turns sideways, toward the views that see this point
        # on the outline: lying flat (face up) it was seen edge-on from eye level, a green shard
        ex = nrm + float(cr.get("big_leaf_up", 0.25)) * up
        ex /= np.linalg.norm(ex)
        ez = np.cross(up, ex)
        if np.linalg.norm(ez) < 0.3:  # (on top of the crown: stand it up, face toward a hashed side)
            a_ = 2 * math.pi * float(vegetation._u(np.array([i + 7], np.uint64), 98)[0])
            ez = np.cross(np.array([math.cos(a_), math.sin(a_), 0.0]), ex)
        ez /= np.linalg.norm(ez)
        ey = np.cross(ez, ex)
        roll = (float(vegetation._u(np.array([i + 31], np.uint64), 98)[0]) - 0.5) * float(cr.get("big_leaf_roll", 0.9))
        ey, ez = ey * math.cos(roll) + ez * math.sin(roll), ez * math.cos(roll) - ey * math.sin(roll)
        o = V[i] - float(cr.get("big_leaf_sink", 0.3)) * L * ex
        Vl, Fl, Nl = _slab(poly, o, ex, ey, ez, 0.03 * L, cup=float(cr.get("big_leaf_cup", 0.15)) / max(L, 1e-6))
        # shaded with its clump, a little of its own face; both faces lit alike (a back face turned from the sun read black)
        s_ = np.sign(Nl @ ez)[:, None]
        Nl = 0.35 * Nl * s_ * np.sign(ez @ nrm + 1e-6) + 0.65 * nrm
        Nl /= np.linalg.norm(Nl, axis=1, keepdims=True)
        along = np.clip((Vl - o) @ ex / L, 0, 1)
        Vs.append(Vl); Fs.append(Fl + n0); Ns.append(Nl)
        uvs.append(np.tile(C["uv"][i], (len(Vl), 1))); cols.append(np.tile(C["col"][i], (len(Vl), 1))); ms.append(np.full(len(Vl), C["mass"][i]))
        ws.append(np.c_[np.full(len(Vl), C["wind"][0][i]), np.full(len(Vl), C["wind"][1][i]), np.full(len(Vl), C["wind"][2][i]), 0.6 * along])
        n0 += len(Vl)
    w = np.vstack(ws)
    return {"V": np.vstack(Vs), "F": np.vstack(Fs), "N": np.vstack(Ns), "uv": np.vstack(uvs), "col": np.vstack(cols), "mass": np.concatenate(ms),
            "wind": tuple(w[:, i] for i in range(4)), "n": len(pick)}


# ---------------------------------------------------------------- small plants (veg_small clumps) in a style
def _sweep(path, half_w, half_t, face, sides: int):
    """A closed tube along a path with an elliptical section (half_w across, half_t through, per station; `face` = the
    flat side's normal per station), ending in a point: (V, F, N, t per vertex)."""
    n = len(path)
    tan = np.gradient(path, axis=0)
    tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
    z = face - tan * (face * tan).sum(1, keepdims=True)
    z /= np.maximum(np.linalg.norm(z, axis=1, keepdims=True), 1e-9)
    x = np.cross(tan, z)
    a = np.arange(sides) * 2 * math.pi / sides
    ca, sa = np.cos(a), np.sin(a)
    V = (path[:-1, None, :] + half_w[:-1, None, None] * ca[None, :, None] * x[:-1, None, :] + half_t[:-1, None, None] * sa[None, :, None] * z[:-1, None, :]).reshape(-1, 3)
    Nn = (ca[None, :, None] * x[:-1, None, :] / np.maximum(half_w[:-1, None, None], 1e-6) + sa[None, :, None] * z[:-1, None, :] / np.maximum(half_t[:-1, None, None], 1e-6)).reshape(-1, 3)
    Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-9)
    t = np.repeat(np.linspace(0, 1, n)[:-1], sides)
    V = np.vstack([V, path[-1], path[0]])
    Nn = np.vstack([Nn, tan[-1], -tan[0]])
    t = np.r_[t, 1.0, 0.0]
    tip, foot = len(V) - 2, len(V) - 1
    F = []
    for i in range(n - 2):
        for j in range(sides):
            p0, p1 = i * sides + j, i * sides + (j + 1) % sides
            F += [[p0, p1, p1 + sides], [p0, p1 + sides, p0 + sides]]
    last = (n - 2) * sides
    for j in range(sides):
        F.append([last + j, last + (j + 1) % sides, tip])
        F.append([(j + 1) % sides, j, foot])
    return V, np.array(F)[:, ::-1], Nn, t  # (the ring runs clockwise about the path: turned so faces look outward)


def _slab(poly, origin, ex, ey, ez, thick: float, cup: float = 0.0):
    """A closed thin plate: a 2D outline (k, 2; in metres, counter-clockwise) laid in the plane (ex, ey) at origin,
    `thick` through along ez, its rim lifted `cup` x its distance squared toward ez (a cupped petal). (V, F, N)."""
    poly = np.asarray(poly, float)
    if poly[:, 0] @ np.roll(poly[:, 1], -1) - poly[:, 1] @ np.roll(poly[:, 0], -1) < 0:
        poly = poly[::-1]  # (counter-clockwise, or the top faces look down: culled from above)
    k = len(poly)
    lift = cup * (poly ** 2).sum(1)
    mid = origin + poly[:, :1] * ex + poly[:, 1:] * ey + lift[:, None] * ez
    c0 = origin + poly.mean(0)[0] * ex + poly.mean(0)[1] * ey
    top, bot = mid + 0.5 * thick * ez, mid - 0.5 * thick * ez
    V = np.vstack([c0 + 0.5 * thick * ez, top, c0 - 0.5 * thick * ez, bot])
    N = np.vstack([np.tile(ez, (k + 1, 1)), np.tile(-ez, (k + 1, 1))])
    F = []
    for i in range(k):
        j = (i + 1) % k
        F.append([0, 1 + i, 1 + j])
        F.append([k + 1, k + 2 + j, k + 2 + i])
        F += [[1 + i, k + 2 + i, k + 2 + j], [1 + i, k + 2 + j, 1 + j]]
    return V, np.array(F), N


def _head(kind: str, c, up, r: float, cs: dict, seed_u, sides: int):
    """A flower / seed head of `kind`: "ball" (a sphere of radius r), "dab" (`dabs` flat ragged blobs of paint, ~r
    across, facing up and out: anime's colour dabs), "petals" (`petals` [fewest, most] fat flat petals round a centre
    disc, cupped up: a cartoon daisy). (V, F, N, part) with part 0 = petal / dab / ball, 1 = the flower's centre."""
    if kind == "ball":
        V, F, N = _ball(c, r, max(3, sides // 2 + 1), max(5, sides + 2))
        return V, F, N, np.zeros(len(V), int)
    up = np.asarray(up, float) / max(float(np.linalg.norm(up)), 1e-9)
    ex = np.cross(up, [0.31, 0.73, 0.61])
    ex /= max(float(np.linalg.norm(ex)), 1e-9)
    ey = np.cross(up, ex)
    Vs, Fs, Ns, Ps, n0 = [], [], [], [], 0
    if kind == "dab":
        # a little CLUSTER of soft paint blobs strung along the head's direction (a seed spike, a flower's puff): flat
        # discs read as coins on sticks from the side. Each blob a squashed ball of its own size and turn; the cluster
        # `dab_length` x r long, the blobs smaller toward its tip.
        nd = max(int(cs.get("dabs", 4)), 1)
        span = float(cs.get("dab_length", 2.2)) * r
        for k in range(nd):
            f_ = k / max(nd - 1, 1)
            rr = r * float(cs.get("dab_size", 0.55)) * (1.1 - 0.45 * f_) * (1 + float(cs.get("ragged", 0.35)) * (seed_u(10 + k) - 0.5))
            off = (f_ - 0.35) * span * up + (seed_u(300 + k) - 0.5) * r * 0.7 * ex + (seed_u(400 + k) - 0.5) * r * 0.7 * ey
            Vb, Fb, Nb = _ball(np.zeros(3), 1.0, 3, 6)
            a_ = 2 * math.pi * seed_u(500 + k)
            ax_ = math.cos(a_) * ex + math.sin(a_) * ey  # (squashed across a hashed side, a little longer along the head)
            sc_ = np.outer(Vb @ ax_, ax_) * (float(cs.get("dab_flat", 0.6)) - 1) + np.outer(Vb @ up, up) * 0.25
            V = c + off + rr * (Vb + sc_)
            N = Nb + np.outer(Nb @ ax_, ax_) * (1 / float(cs.get("dab_flat", 0.6)) - 1)
            N = N / np.linalg.norm(N, axis=1, keepdims=True) * 0.6 + 0.4 * np.array([0, 0, 1.0])  # (lit as a soft clump)
            N /= np.linalg.norm(N, axis=1, keepdims=True)
            Vs.append(V); Fs.append(Fb + n0); Ns.append(N); Ps.append(np.zeros(len(V), int)); n0 += len(V)
    else:  # petals round a centre
        lo, hi = cs.get("petals", [5, 8])
        n = int(lo + round((hi - lo) * seed_u(7)))
        L = r * float(cs.get("petal_length", 1.0))
        W = L * float(cs.get("petal_width", 0.42))
        t = np.linspace(0, 1, max(3, sides // 4) + 1)
        side = W * 0.5 * np.sin(np.pi * np.clip(t, 0, 1)) ** 0.6
        out_ = np.vstack([np.c_[t * L, side], np.c_[t[::-1][1:-1] * L, -side[::-1][1:-1]]])
        cen_r = r * float(cs.get("centre", 0.32))
        petal_n = up + float(cs.get("petal_sky", 0.8)) * np.array([0, 0, 1.0])
        petal_n /= np.linalg.norm(petal_n)
        for k in range(n):
            a = 2 * math.pi * (k + 0.3 * seed_u(500 + k)) / n
            dx, dy = math.cos(a), math.sin(a)
            R2 = np.array([[dx, -dy], [dy, dx]])
            poly = (out_ + [0.6 * cen_r, 0]) @ R2.T
            V, F, N = _slab(poly, c, ex, ey, up, 0.08 * L, cup=float(cs.get("cup", 0.6)) / max(L, 1e-6))
            # both faces of a petal shade as its upper face, leaned to the sky: a flower turned from the sun showed its
            # undersides dark grey (a petal is thin and lit through)
            N = np.tile(petal_n, (len(V), 1))
            Vs.append(V); Fs.append(F + n0); Ns.append(N); Ps.append(np.zeros(len(V), int)); n0 += len(V)
        V, F, N = _ball(c + 0.04 * L * up, cen_r, 3, max(6, sides))
        V = c + (V - c) * [1, 1, 1] - np.outer((V - c) @ up, up) * 0.5  # (a flattened dome)
        Vs.append(V); Fs.append(F + n0); Ns.append(N); Ps.append(np.ones(len(V), int)); n0 += len(V)
    return np.vstack(Vs), np.vstack(Fs), np.vstack(Ns), np.concatenate(Ps)


def _ball(c, r, rings: int, sides: int):
    V, N = [c + [0, 0, r]], [[0, 0, 1.0]]
    for i in range(1, rings):
        ph = math.pi * i / rings
        for j in range(sides):
            a = 2 * math.pi * j / sides
            d = np.array([math.sin(ph) * math.cos(a), math.sin(ph) * math.sin(a), math.cos(ph)])
            V.append(c + r * d)
            N.append(d)
    V.append(c - [0, 0, r])
    N.append([0, 0, -1.0])
    F = []
    for j in range(sides):
        F.append([0, 1 + j, 1 + (j + 1) % sides])
        F.append([len(V) - 1, 1 + (rings - 2) * sides + (j + 1) % sides, 1 + (rings - 2) * sides + j])
    for i in range(rings - 2):
        for j in range(sides):
            p0, p1 = 1 + i * sides + j, 1 + i * sides + (j + 1) % sides
            F += [[p0, p0 + sides, p1 + sides], [p0, p1 + sides, p1]]
    return np.array(V), np.array(F), np.array(N)


CLUMP = {"blades": [5, 9], "width": 0.2, "thick": 0.6, "curl": 0.35, "heads": 3, "ball": 0.06, "stalk": 0.012, "normals_up": 0.35,
         "tones": 3, "tone": [0.8, 1.15], "budget": 800, "roughness": 0.8}


def dress_clump(tree: dict, st: dict, triangles: int | None = None, season: str = "summer") -> dict:
    """A small plant (veg_small: cards from an atlas) in a style that has no cards: every leaf picture becomes a few FAT
    blades and every flowering picture a ball on a stalk (sheet block `clump`: `blades` [fewest, most] chosen among the
    realistic cards so the tuft keeps its height and spread (farthest tips first), each a closed paddle `width` x its
    length wide and `thick` x that through, curling over by `curl`; `heads` balls of `ball` x their stalk's length;
    `tones` steps of `tone` per blade; `normals_up` = normals leaned to the sky so the tuft shades as one clump).
    Same keys as dress(): "crown" = the blades (slot foliage), "heads" = balls + stalks (slot heads: shown only in the
    seasons their layers show in), "wood" = the plant's own stalks."""
    from . import veg_export, veg_small
    s = tree["spec"]
    cs = {**CLUMP, **(st.get("clump") or {})}
    full = int(cs["budget"])
    triangles = int(triangles or full)
    tw = tree["twigs"]
    lf = s["leaves"]
    parts = veg_leaf.part_specs(lf)
    pc = veg_leaf.part_cards(lf)
    owner = {ci: p_ for p_, cc in pc.items() for ci in cc}
    flowery = {p_ for p_, sp_ in parts.items() if (sp_.get("twig") or {}).get("flower")}
    is_head = np.array([owner[int(c)] in flowery for c in tw["card"]], bool) if len(tw["pos"]) else np.zeros(0, bool)
    up = np.array([0, 0, 1.0])
    wn = veg_export.wind_nodes(tree)
    W = veg_mesh.tubes(tree, sides=(4, 6))
    wood = {"V": W["V"], "F": W["F"], "N": veg_export._normals(W["V"], W["F"]), "uv": W["uv"], "node": W["node"], "tan": W["tan"],
            "radius": W["radius"], "dead": W["dead"],
            "wind": (wn["trunk"][W["node"]], wn["branch"][W["node"]], wn["phase"][W["node"]], np.zeros(len(W["V"])))}
    out = {"wood": wood, "wood_wind": wood["wind"], "crown": None, "heads": None, "forks": None, "mini": tree}
    info = {"style": st["name"], "clump": True, "cards": int(len(tw["pos"])), "blades": 0, "heads": 0, "wood_triangles": int(len(W["F"])),
            "crown_triangles": 0, "budget": triangles, "kind": "blades", "forks_triangles": 0}
    col = season_color(s, season, st)
    if len(tw["pos"]) and col is not None:
        tips = tw["pos"] + tw["frame"][:, :, 1] * tw["reach"][:, None]
        main = np.flatnonzero(~is_head)
        heads = np.flatnonzero(is_head)[: int(cs["heads"])]
        lo, hi = cs["blades"]
        nb = int(np.clip(round(0.6 * len(main)), lo, hi)) if len(main) else 0
        pick = []
        if nb:  # the tallest first, then whichever tip is farthest from those taken: the tuft keeps its height and spread
            pick = [int(main[np.argmax(tips[main, 2])])]
            d = np.linalg.norm(tips[main] - tips[pick[0]], axis=1)
            while len(pick) < min(nb, len(main)):
                j = int(np.argmax(d))
                pick.append(int(main[j]))
                d = np.minimum(d, np.linalg.norm(tips[main] - tips[main[j]], axis=1))
        # `fan` blades from each chosen card (a card is a picture of a clump: one blade per card left a sparse tuft),
        # turned +-`fan_angle` deg about the vertical and each a little shorter
        fan, fa = max(int(cs.get("fan", 1)), 1), math.radians(float(cs.get("fan_angle", 18.0)))
        yaw = [0.0] * len(pick)
        shrink = [1.0] * len(pick)
        base_pick = list(pick)
        for k in range(1, fan):
            sgn = 1 if k % 2 else -1
            for ci in base_pick:
                pick.append(ci)
                yaw.append(sgn * fa * ((k + 1) // 2) * (0.7 + 0.6 * float(vegetation._u(tw["key"][ci: ci + 1], 60 + k)[0])))
                shrink.append(1.0 - 0.12 * ((k + 1) // 2))
        n_obj = len(pick) + len(heads)
        hk = cs.get("heads_kind", "ball")
        if isinstance(hk, dict):  # by the realistic flower's form: {"ray": "petals", "*": "ball"} (a daisy's rays, a grass's spike)
            form = str(((parts[owner[int(tw["card"][heads[0]])]].get("twig") or {}).get("flower") or {}).get("form", "")) if len(heads) else ""
            hk = hk.get(form, hk.get("*", "ball"))
        hk = str(hk)

        def cost(a_, b_):  # triangles of every blade, stalk and head at that many sides and rings
            hs_, hr_, bs_, br_ = max(3, a_ // 2), max(b_, 2), max(5, a_ + 2), max(3, b_ // 2 + 2)
            head = {"ball": 2 * bs_ * (br_ - 1), "dab": int(cs.get("dabs", 4)) * 24,
                    "petals": int(np.mean(cs.get("petals", [5, 8]))) * 4 * (2 * (max(3, a_ // 2) + 1) - 2) + 2 * bs_ * 2}.get(hk, 2 * bs_ * (br_ - 1))
            return len(pick) * 2 * a_ * b_ + len(heads) * (2 * hs_ * hr_ + head)
        sides, rings = next(((a_, b_) for a_, b_ in ((8, 8), (7, 7), (6, 6), (5, 5), (4, 4), (4, 3), (3, 3), (3, 2))
                             if cost(a_, b_) <= triangles - len(W["F"])), (3, 2))
        tones = int(max(1, cs["tones"]))
        Vs, Fs, Ns, uvs, cols, winds, n0 = [], [], [], [], [], [], 0
        zs = tips[pick, 2] * np.array(shrink) if pick else np.zeros(0)
        for bi, ci in enumerate(pick):
            L = float(tw["reach"][ci]) * shrink[bi]
            cy, sy = math.cos(yaw[bi]), math.sin(yaw[bi])
            Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1.0]])
            d, zf = Rz @ tw["frame"][ci][:, 1], Rz @ tw["frame"][ci][:, 2]
            o = d - up * d[2]
            o = o / np.linalg.norm(o) if np.linalg.norm(o) > 1e-3 else zf
            t = np.linspace(0, 1, rings + 1)
            path = tw["pos"][ci] + L * (d[None] * t[:, None] + float(cs["curl"]) * (t ** 2)[:, None] * (o - 0.45 * up)[None])
            path[:, 2] += (tw["pos"][ci][2] + (tips[ci, 2] - tw["pos"][ci][2]) * shrink[bi] - path[-1, 2]) * t  # (the curl must not shorten the tuft)
            prof = np.where(t < 0.4, 0.62 + 0.38 * t / 0.4, np.sqrt(np.clip(1 - ((t - 0.4) / 0.6) ** 2, 0, 1)))
            hw = np.maximum(0.5 * float(cs["width"]) * L * prof, 1e-4)
            face = np.tile(np.cross(np.cross(d, o if abs(d @ o) < 0.99 else zf), d), (len(t), 1)) if abs(d[2]) < 0.999 else np.tile(zf, (len(t), 1))
            V, F, N, tt = _sweep(path, hw, hw * float(cs["thick"]), face, sides)
            N = N * (1 - float(cs["normals_up"])) + up * float(cs["normals_up"])
            N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
            tf = (int(np.clip((zs[bi] - zs.min()) / max(float(np.ptp(zs)), 1e-6) * tones, 0, tones - 1)) / max(tones - 1, 1)) if len(pick) > 1 else 1.0
            tone = cs["tone"][0] + (cs["tone"][1] - cs["tone"][0]) * tf
            Vs.append(V); Fs.append(F + n0); Ns.append(N)
            uvs.append(np.c_[tt, np.full(len(V), (bi + 0.5) / max(len(pick), 1))])
            cols.append(np.full((len(V), 3), tone))
            own = tt ** 1.5 * float(np.clip(L / 1.2, 0.08, 1.0))
            winds.append(np.c_[np.zeros(len(V)), own, np.full(len(V), float(vegetation._u(tw["key"][ci: ci + 1], 57)[0])), np.zeros(len(V))])
            n0 += len(V)
        if Vs:
            gain = float(max(cs["tone"]))
            V, F, N = np.vstack(Vs), np.vstack(Fs), np.vstack(Ns)
            wd = np.vstack(winds)
            out["crown"] = {"V": V, "F": F, "N": N, "uv": np.vstack(uvs), "col": np.vstack(cols) / gain, "gain": gain,
                            "mass": np.repeat(np.arange(len(pick)), [len(v_) for v_ in Vs]), "wind": tuple(wd[:, i] for i in range(4))}
            info.update(blades=len(pick), crown_triangles=int(len(F)), tones=tones)
        Vs, Fs, Ns, uvs, winds, n0 = [], [], [], [], [], 0
        head_part = []
        for hi_, ci in enumerate(heads):
            L = float(tw["reach"][ci])
            d = tw["frame"][ci][:, 1]
            t = np.linspace(0, 1, max(rings, 2) + 1)
            path = tw["pos"][ci] + L * d[None] * t[:, None]
            r = np.full(len(t), max(float(cs["stalk"]) * L, 0.003))
            V, F, N, tt = _sweep(path, r, r, np.tile(tw["frame"][ci][:, 2], (len(t), 1)), max(3, sides // 2))
            def su(x, ci=ci):  # the head's own random numbers (array or scalar in, the same out)
                r_ = vegetation._u(tw["key"][ci] + np.atleast_1d(np.asarray(x)).astype(np.uint64), 70)
                return r_ if np.ndim(x) else float(r_[0])
            hd = d * (1 - float(cs.get("head_up", 0.6))) + up * float(cs.get("head_up", 0.6))  # (a flower faces the sky by `head_up`, the rest along its stalk: a head along a leaning stalk faced sideways, its petals in their own shade)
            r_head = float(cs["ball"]) * L
            fl_ = ((parts[owner[int(tw["card"][ci])]].get("twig") or {}).get("flower") or {})
            if hk in ("petals", "dab") and fl_.get("radius"):  # (a flower: sized from the realistic flower, x `petal_size`)
                r_head = max(r_head, float(cs.get("petal_size", 1.0)) * float(fl_["radius"]))
            Vb, Fb, Nb, Pb = _head(hk, path[-1], hd, r_head, cs, su, max(5, sides + 2))
            head_part.append(Pb)
            ph = float(vegetation._u(tw["key"][ci: ci + 1], 57)[0])
            for V_, F_, N_, t_ in ((V, F, N, tt), (Vb, Fb, Nb, np.ones(len(Vb)))):
                Vs.append(V_); Fs.append(F_ + n0); Ns.append(N_)
                uvs.append(np.c_[t_, np.full(len(V_), (hi_ + 0.5) / len(heads))])
                winds.append(np.c_[np.zeros(len(V_)), t_ ** 1.5 * float(np.clip(L / 1.2, 0.08, 1.0)), np.full(len(V_), ph), np.zeros(len(V_))])
                n0 += len(V_)
        if Vs:
            wd = np.vstack(winds)
            hp = next(owner[int(tw["card"][c_])] for c_ in heads)
            fl = (parts[hp].get("twig") or {}).get("flower") or {}
            co = st.get("colour") or {}
            hpart = np.concatenate([np.r_[np.full(len(Vs[2 * q_]), 2), head_part[q_]] for q_ in range(len(head_part))])  # (stalk = 2, then the head: 0 petal / dab / ball, 1 its centre)
            out["heads"] = {"V": np.vstack(Vs), "F": np.vstack(Fs), "N": np.vstack(Ns), "uv": np.vstack(uvs), "part": hpart,
                            "kind": hk,
                            "wind": tuple(wd[:, i] for i in range(4)),
                            "color": styled(fl.get("color") or parts[hp].get("color") or [0.8, 0.75, 0.4], co.get("saturation", 1.0), co.get("value", 1.0)),
                            # each part's own colour (sRGB): the petals / dab / ball, the flower's centre, the stalk (the summer leaf)
                            "part_colors": [styled(fl.get("color") or parts[hp].get("color") or [0.8, 0.75, 0.4], co.get("saturation", 1.0), co.get("value", 1.0)),
                                            styled(fl.get("center") or [0.93, 0.74, 0.12], co.get("saturation", 1.0), co.get("value", 1.0)),
                                            styled((veg_small.season_state(s, "summer") or {}).get("color") or [0.3, 0.45, 0.15], co.get("saturation", 1.0), co.get("value", 1.0))],
                            "seasons": [se for se in SEASONS if any(veg_small.layer_shown({**veg_small.LAYER, **L_}, se) for L_ in s["clump"]["layers"]
                                                                    if L_.get("part", "main") in flowery) and veg_small.season_state(s, se) is not None]}
            info.update(heads=len(heads), heads_triangles=int(len(out["heads"]["F"])), heads_kind=out["heads"]["kind"])
    real = veg_small.measures(tree)
    top = max([float(out[k_]["V"][:, 2].max()) for k_ in ("crown", "heads") if out[k_] is not None], default=0.0)
    allv = np.vstack([out[k_]["V"] for k_ in ("crown", "heads") if out[k_] is not None]) if (out["crown"] or out["heads"]) else np.zeros((1, 3))
    info["match"] = {"height_m": [round(float(tree["height"]), 3), round(top, 3)],
                     "spread_m": [real.get("spread_m", 0.0), round(2 * float(np.percentile(np.linalg.norm(allv[:, :2], axis=1), 98)), 3)]}
    info["triangles"] = info["wood_triangles"] + info["crown_triangles"] + info.get("heads_triangles", 0)
    out["info"] = info
    return out


def lines(info: dict) -> list[str]:
    """What the style did to this plant, in words (the report, the export's reply, GLB extras)."""
    m = info["match"]
    if info.get("clump"):
        return [f"style {info['style']}: {info['blades']} fat blades for {info['cards']} cards, {info['heads']} flower / seed heads as {dict(ball='balls', dab='colour dabs', petals='petalled flowers').get(info.get('heads_kind', 'ball'), 'balls')} on stalks "
                f"({info['crown_triangles']} + {info.get('heads_triangles', 0)} triangles; no atlas, no alpha)",
                f"same individual: height {m['height_m'][1]} m (realistic {m['height_m'][0]}), spread {m['spread_m'][1]} m (realistic {m['spread_m'][0]})"]
    out = [f"style {info['style']}: {info['limbs_kept']} limbs kept of {info['limbs']} first-order + {info.get('stubs', 0)} of their forks " + (f"(shown only when bare: {info.get('forks_triangles', 0)} triangles) " if info.get('forks_triangles') else "(in the wood, seen through the gaps) ") +
           f"({info['axes_kept']} of {info['axes']} axes drawn, {info['wood_m']} of {info['wood_m_grown']} m of wood; no twigs)"
           + (f"; {info['masses']} crown {'tiers' if info.get('kind') == 'tiers' else 'masses'}" + (" + a core" if info.get("core") else "") + f" joined over {info.get('blend_m', 0)} m, for {info['twigs']} twigs"
              if info["masses"] and info.get("kind") != "clouds" else
              (f"; {info['masses']} leaf clouds of {info.get('cards', 0)} cards in {info.get('layers', 0)} depth layers ({info.get('card_m', 0)} m across, "
               f"alpha fill {info.get('card_fill', 0)}: overdraw ~{1 / max(info.get('card_fill', 1), 1e-3):.1f}x the visible leaf), for {info['twigs']} twigs"
               if info["masses"] else "; no crown masses"))
           + (f", {info.get('tones', 0)} tones" if info.get("tones") else "")]
    out.append(f"same individual: outline IoU {m['iou']} against the realistic tree in leaf (true scale, feet together; azimuths "
               f"{'/'.join(str(a) for a in m['azimuths'])}: {'/'.join(f'{v:.2f}' for v in m['iou_by_azimuth'])}); height "
               f"{m['height_m'][1]} m (realistic {m['height_m'][0]}), crown width {m['width_m'][1]} m (realistic {m['width_m'][0]})")
    if info.get("masses_tried"):
        out.append("masses tried (count: IoU at a coarse voxel): " + ", ".join(f"{k}: {v:.3f}" for k, v in sorted(info["masses_tried"].items())))
    return out


def warnings(info: dict) -> list[str]:
    m = info["match"]
    w = []
    if info.get("clump"):
        if abs(m["height_m"][1] - m["height_m"][0]) > 0.1 * max(m["height_m"][0], 1e-6):
            w.append(f"WARNING: the styled plant is {m['height_m'][1]} m tall, the realistic one {m['height_m'][0]} m")
        return w
    if m["iou"] < 0.8:
        w.append(f"WARNING: the {info['style']} tree's outline is only {m['iou']} IoU of the realistic one: at a distance it is not "
                 f"the same tree (style.crown.spread / pad / masses)")
    if abs(m["height_m"][1] - m["height_m"][0]) > 0.06 * m["height_m"][0]:
        w.append(f"WARNING: the styled tree is {m['height_m'][1]} m tall, the realistic one {m['height_m'][0]} m")
    return w
