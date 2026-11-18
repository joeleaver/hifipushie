"""The fit (once per tree and sheet) and `dress`: shell and cards, big leaves. Part of the plant styles (veg_style.py has the overview)."""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from . import veg_style
from . import vegetation_kernels
from .veg_style import color_gain, evergreen, season_color
from .veg_style_crown import _decimate, compare, crown_mesh, field, leaf_points, masses, reference, skirt
from .veg_style_small import _slab, dress_clump
from .veg_style_wood import grad, onto, wood, wood_dense, wood_field, wood_tubes

# ---------------------------------------------------------------- the fit (once per tree and sheet) and the dress (per LOD)
def fit(tree: dict, st: dict) -> dict:
    """The styled plant's parts before any budget: {"mini": the drawn wood, "wood": its dense mesh, "ells": the
    crown's masses (or []), "dense": the crown at full resolution, "match": compare()'s numbers, "tried": IoU per
    number of masses}."""
    key = hashlib.sha1(json.dumps(st, sort_keys=True).encode()).hexdigest()
    hit = veg_style._FIT.get(id(tree))
    if hit is not None and hit[0] is tree and hit[1] == key:
        return hit[2]
    mini = wood(tree, st)
    Wm = wood_tubes(mini, st)
    wm = (Wm["V"], Wm["F"])
    X, tl = leaf_points(tree)
    out = {"mini": mini, "ells": [], "dense": None, "tried": {}, "twigs": int(len(X)), "blend": 0.0}
    X = skirt(X, float(tree["height"]), st.get("crown") or {}, int(tree["spec"].get("seed", 1)))  # (`crown.down_to`: the dome hangs down its sides)
    out["skirt_points"] = int(len(X)) - out["twigs"]
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
    if len(veg_style._FIT) > 6:
        veg_style._FIT.clear()
    veg_style._FIT[id(tree)] = (tree, key, out)
    return out


def dress(tree: dict, st: dict, triangles: int | None = None, season: str = "summer") -> dict:
    """The plant in its style within a triangle count (default the sheet's `budget`): {"wood": {"V", "F", "N", "uv",
    "node"...}, "wood_wind": (trunk, branch, phase, flutter) per wood vertex, "crown": None | {"V", "F", "N", "uv",
    "col" (n, 3 multiplier), "wind", "mass"}, "mini", "info"}. A lower count takes triangles off the same two
    surfaces: the masses and the limbs themselves never change with the LOD."""
    from . import veg_export_parts
    if tree.get("clump"):
        return dress_clump(tree, st, triangles, season)
    ft = fit(tree, st)
    full = int(st.get("budget", 5000))
    triangles = int(triangles or full)
    mini = ft["mini"]
    share = float(st["wood"].get("share", 0.25)) if ft["ells"] else 1.0
    wd_ = ft["wood"]
    wfn = lambda q: np.maximum(wood_field(wd_["segs"], q, wd_["blend"]), -0.3 - q[:, 2])
    wn = veg_export_parts.wind_nodes(mini)

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
            "masses_tried": ft["tried"], "down_to": (st.get("crown") or {}).get("down_to"), "skirt_points": ft.get("skirt_points", 0), "wood_triangles": int(len(Fw)), "crown_triangles": 0, "budget": triangles,
            "forks_triangles": int(len(out["forks"]["F"])) if out["forks"] else 0, "kind": (st.get("crown") or {}).get("kind", "masses")}
    if ft["ells"] and season_color(tree["spec"], season, st) is not None and st["crown"].get("kind") == "clouds":
        from . import veg_cloud
        cr, ells = st["crown"], [e for e in ft["ells"] if not e.get("core") and "of" not in e]
        C_ = veg_cloud.clouds(tree, st, ells, max(triangles - len(Fw), 0), lod=triangles / max(full, 1), floor=ft["floor"])
        V = C_["V"]
        wd = st.get("wind") or {}
        anchor = np.array([int(np.argmin(np.linalg.norm(mini["pos"] - e["c"], axis=1))) for e in ells])
        b_m = np.maximum(wn["branch"][anchor], float(wd.get("mass", 0.3)))
        ph_m = np.where(mini["order"][anchor] > 0, wn["phase"][anchor], vegetation_kernels._u(np.arange(len(ells)).astype(np.uint64) + np.uint64(int(tree["spec"].get("seed", 1))), 57))
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
            hu = (vegetation_kernels._u(own.astype(np.uint64) + np.uint64(1000 * (sd + 1)), 97) - 0.5) * 2 * hj
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
        ph_m = np.where(mini["order"][anchor] > 0, wn["phase"][anchor], vegetation_kernels._u(own.astype(np.uint64) + np.uint64(int(tree["spec"].get("seed", 1))), 57))
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
            _shell_and_cards(tree, st, out, cfn, ft["floor"], max(triangles - len(Fw) - len(F), 0), info, triangles / max(full, 1), ells, blend)
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


def _shell_and_cards(tree: dict, st: dict, out: dict, cfn, floor: float, budget: int, info: dict, lod: float = 1.0, ells=None, blend: float = 0.5) -> None:
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
    crease = None
    shade = None
    if ells is not None and cr.get("clump_shade") and len(ells) > 1:
        # every clump (sub-clumps included) lit on its own top and shadowed on its own underside: the clump-level
        # gradient of feature-animation canopies (a canopy-wide gradient alone read as broccoli in a blur)
        D_ = field(ells, V, blend, each=True)[1]
        j_ = D_.argmin(1)
        cz_ = np.array([e["c"][2] for e in ells])
        ez_ = np.array([math.sqrt(float(((e["R"][:, 2] * e["r"]) ** 2).sum())) for e in ells])
        u_ = np.clip((V[:, 2] - (cz_[j_] - ez_[j_])) / np.maximum(2 * ez_[j_], 1e-6), 0, 1)
        s0, s1 = cr["clump_shade"]
        shade = s0 + (s1 - s0) * (u_ * u_ * (3 - 2 * u_)) ** float(cr.get("clump_shade_power", 0.8))
        col = col * shade[:, None]
    if ells is not None and float(cr.get("crease_dark", 0.0)) > 0 and len(ells) > 1:
        # AO between clumps: where two clumps meet (the two nearest of them almost equally near) the shell darkens,
        # so each clump keeps its own volume and shadow under the leaves
        D = field(ells, V, blend, each=True)[1]
        Ds = np.sort(D, 1)
        gap = Ds[:, 1] - Ds[:, 0]
        k_ = max(float(cr.get("crease_width", 0.6)) * blend, 1e-3)
        crease = np.exp(-np.maximum(gap, 0) / k_)
        col = col * (1 - float(cr["crease_dark"]) * crease)[:, None]
        info["crease_share"] = round(float((crease > 0.5).mean()), 3)
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
        if shade is not None:  # (the cards take their clump's light: lit tops, shadowed undersides)
            K["col"] = K["col"] * shade[idx][:, None]
        if crease is not None:  # (the cards in a crease between clumps darken with it)
            K["col"] = K["col"] * (1 - 0.8 * float(cr["crease_dark"]) * crease[idx])[:, None]
        out["cards"] = K
        clump_m = 2 * float(np.mean([e["r"].mean() for e in ells if not e.get("core") and "of" not in e])) if ells else float(np.ptp(V[:, 2]))
        cs_ = cr.get("cards") or {}
        info.update(card_vs_clump=round(K["card_m"] / max(clump_m, 1e-6), 2), clump_m=round(clump_m, 2),
                    card_leaves=int(cs_.get("count", veg_cloud.CARDS["count"])))
        info.update(cards=K["cards"], card_m=round(K["card_m"], 2), leaf_cover=round(K["cover"], 2), card_fill=round(K["atlas"]["fill"], 3), cards_triangles=int(len(K["F"])),
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
            a_ = 2 * math.pi * float(vegetation_kernels._u(np.array([i + 7], np.uint64), 98)[0])
            ez = np.cross(np.array([math.cos(a_), math.sin(a_), 0.0]), ex)
        ez /= np.linalg.norm(ez)
        ey = np.cross(ez, ex)
        roll = (float(vegetation_kernels._u(np.array([i + 31], np.uint64), 98)[0]) - 0.5) * float(cr.get("big_leaf_roll", 0.9))
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
