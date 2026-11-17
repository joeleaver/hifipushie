"""Small plants (veg_small clumps) in a style: sweeps, slabs, heads, `dress_clump`, lines, warnings. Part of the plant styles (veg_style.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from . import veg_style
from . import veg_mesh
from . import veg_leaf_atlas
from . import vegetation_kernels
from .veg_style import season_color, styled

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
            off = (f_ - 0.8) * span * up + (seed_u(300 + k) - 0.5) * r * 0.7 * ex + (seed_u(400 + k) - 0.5) * r * 0.7 * ey
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


def dress_clump(tree: dict, st: dict, triangles: int | None = None, season: str = "summer") -> dict:
    """A small plant (veg_small: cards from an atlas) in a style that has no cards: every leaf picture becomes a few FAT
    blades and every flowering picture a ball on a stalk (sheet block `clump`: `blades` [fewest, most] chosen among the
    realistic cards so the tuft keeps its height and spread (farthest tips first), each a closed paddle `width` x its
    length wide and `thick` x that through, curling over by `curl`; `heads` balls of `ball` x their stalk's length;
    `tones` steps of `tone` per blade; `normals_up` = normals leaned to the sky so the tuft shades as one clump).
    Same keys as dress(): "crown" = the blades (slot foliage), "heads" = balls + stalks (slot heads: shown only in the
    seasons their layers show in), "wood" = the plant's own stalks."""
    from . import veg_export, veg_small
    from . import veg_export_parts
    s = tree["spec"]
    cs = {**veg_style.CLUMP, **(st.get("clump") or {})}
    full = int(cs["budget"])
    triangles = int(triangles or full)
    tw = tree["twigs"]
    lf = s["leaves"]
    parts = veg_leaf_atlas.part_specs(lf)
    pc = veg_leaf_atlas.part_cards(lf)
    owner = {ci: p_ for p_, cc in pc.items() for ci in cc}
    flowery = {p_ for p_, sp_ in parts.items() if (sp_.get("twig") or {}).get("flower")}
    is_head = np.array([owner[int(c)] in flowery for c in tw["card"]], bool) if len(tw["pos"]) else np.zeros(0, bool)
    up = np.array([0, 0, 1.0])
    wn = veg_export_parts.wind_nodes(tree)
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
                yaw.append(sgn * fa * ((k + 1) // 2) * (0.7 + 0.6 * float(vegetation_kernels._u(tw["key"][ci: ci + 1], 60 + k)[0])))
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
            winds.append(np.c_[np.zeros(len(V)), own, np.full(len(V), float(vegetation_kernels._u(tw["key"][ci: ci + 1], 57)[0])), np.zeros(len(V))])
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
                r_ = vegetation_kernels._u(tw["key"][ci] + np.atleast_1d(np.asarray(x)).astype(np.uint64), 70)
                return r_ if np.ndim(x) else float(r_[0])
            hd = d * (1 - float(cs.get("head_up", 0.6))) + up * float(cs.get("head_up", 0.6))  # (a flower faces the sky by `head_up`, the rest along its stalk: a head along a leaning stalk faced sideways, its petals in their own shade)
            r_head = float(cs["ball"]) * L
            fl_ = ((parts[owner[int(tw["card"][ci])]].get("twig") or {}).get("flower") or {})
            if hk in ("petals", "dab") and fl_.get("radius"):  # (a flower: sized from the realistic flower, x `petal_size`)
                r_head = max(r_head, float(cs.get("petal_size", 1.0)) * float(fl_["radius"]))
            Vb, Fb, Nb, Pb = _head(hk, path[-1], hd, r_head, cs, su, max(5, sides + 2))
            head_part.append(Pb)
            ph = float(vegetation_kernels._u(tw["key"][ci: ci + 1], 57)[0])
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
                            "seasons": [se for se in veg_style.SEASONS if any(veg_small.layer_shown({**veg_small.LAYER, **L_}, se) for L_ in s["clump"]["layers"]
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
    if info.get("kind") != "clouds" and info.get("cards_triangles"):
        out.append(f"leaf cards on the shell: {info['cards']} cards, each {info['card_m']} m across ({info.get('card_vs_clump', 0)}x a crown clump of "
                   f"{info.get('clump_m', 0)} m), {info.get('card_leaves', 0)} leaves painted per card picture, leaf cover {info.get('leaf_cover', 0)}")
    out.append(f"same individual: outline IoU {m['iou']} against the realistic tree in leaf (true scale, feet together; azimuths "
               f"{'/'.join(str(a) for a in m['azimuths'])}: {'/'.join(f'{v:.2f}' for v in m['iou_by_azimuth'])}); height "
               f"{m['height_m'][1]} m (realistic {m['height_m'][0]}), crown width {m['width_m'][1]} m (realistic {m['width_m'][0]})")
    if info.get("masses_tried"):
        out.append("masses tried (count: IoU at a coarse voxel): " + ", ".join(f"{k}: {v:.3f}" for k, v in sorted(info["masses_tried"].items())))
    return out


CARD_WARN = 1.5  # a leaf card wider than this x a crown clump is warned about (pixar's own cards are ~1x one)


def warnings(info: dict) -> list[str]:
    m = info["match"]
    w = []
    if info.get("clump"):
        if abs(m["height_m"][1] - m["height_m"][0]) > 0.1 * max(m["height_m"][0], 1e-6):
            w.append(f"WARNING: the styled plant is {m['height_m'][1]} m tall, the realistic one {m['height_m'][0]} m")
        return w
    if info.get("card_vs_clump", 0) > CARD_WARN:  # (pixar's leaf cards: `cards.count` reads like a number of cards; it is leaves per card PICTURE)
        w.append(f"WARNING: each leaf card is {info['card_m']} m across, {info['card_vs_clump']}x a crown clump ({info['clump_m']} m): cards that big "
                 f"stand off the shell as flat sheets. A card is 2 x `cards.leaf` x the leaf's length / `cards.length` across; `cards.count` "
                 f"({info.get('card_leaves')}) is the leaves drawn in ONE card's picture, not the number of cards (that is the budget's)")
    if m["iou"] < 0.8:
        w.append(f"WARNING: the {info['style']} tree's outline is only {m['iou']} IoU of the realistic one: at a distance it is not "
                 f"the same tree (style.crown.spread / pad / masses)"
                 + (f"; crown.down_to {info['down_to']} hangs the crown below the realistic tree's on purpose, which costs IoU" if info.get("down_to") is not None else ""))
    if abs(m["height_m"][1] - m["height_m"][0]) > 0.06 * m["height_m"][0]:
        w.append(f"WARNING: the styled tree is {m['height_m'][1]} m tall, the realistic one {m['height_m'][0]} m")
    return w
