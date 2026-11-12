"""The strands job: modifier stacks, `job`, the npz hash and the key. Part of the hair strands (hair_strands.py has the overview)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import hair_strands
from . import hair_cards as hc
from . import hair_cards_budget
from .hair_strands import _ss, physical, wisp_physical
from .hair_strands_guides import (
    _guides_subset, _longest, collide_mesh, lock_guides, scalp_mesh, scalp_uv, under_guides,
)

def stacks(S: dict, n_head: float, n_free: float, n_under: float, area: float, seed: int = 0, n_wisp: float = 0.0,
           tail: bool = True, n_even: float = 0.0, even_all: bool = False, banks: bool = False,
           even_objs: list | None = None, short_even: bool = False) -> dict:
    """Each object's modifier stack: [[node group, {input: value}], ...]. {"part": name} = the scene object of that
    part (the body: strands are kept out of it), {"attribute": name} = a named attribute as a field."""
    body = {"object": "hair_collide"}

    def lens_stack(ph, amount, free):
        st = [[hair_strands.LENS, {"Amount": float(amount), "Tips": ph["tips"], "Roots": ph["roots"], "Flyaway": ph["flyaway"],
                      "Flyaway Distance": 1.0, "Edge": 0.8, "Clump": ph["clump"],
                      "Clump Shape": ph["clump_shape"], "Tip Spread": ph["tip_spread01"], "Wave": ph["wave"],
                      "Wavelength": ph["wavelength"], "Curl": ph["curl01"], "Loose": ph["wander"], "Wave Random": ph["wave_random"],
                      "Stray": ph["stray"], "Seed": int(seed)}]]
        if ph.get("halo", 0.0) > 0:  # (only when asked for: older jobs keep their stacks, and so their cache keys)
            st[0][1].update({"Halo": ph["halo"], "Halo Distance": ph.get("halo_m", hair_strands.SAFE["halo_m"]),
                             "Halo Length": ph.get("halo_len", hair_strands.SAFE["halo_len"])})
        if ph["loose"] > 0:  # strands wandering together (Blender's noise is coherent in space: neighbours agree)
            st.append(["Hair Curves Noise", {"Cumulative Offset": False, "Factor": 1.0, "Distance": ph["loose"], "Shape": 0.5,
                                             "Scale": ph["loose_scale"], "Scale along Curve": 0.35,
                                             "Offset per Curve": 0.15, "Seed": int(seed), "Preserve Length": True}])
        if ph["frizz"] > 0:
            st.append(["Frizz Hair Curves", {"Cumulative Offset": False, "Factor": 1.0, "Distance": ph["frizz"], "Shape": 0.5, "Seed": int(seed),
                                             "Preserve Length": True}])
        st.append(["Shrinkwrap Hair Curves", {"Surface:Object": body, "Factor": 1.0, "Above Surface": 0.0015,
                                              "Offset Distance": 0.0015, "Smoothing Steps": 1,
                                              "Lock Roots": False}])
        st.append(["hp_profile", {"Radius": ph["radius"], "Tip": ph["tip_radius"], "Taper": 0.3, "Root": 0.8}])
        return st

    out = {}
    if n_head > 0:
        out["hair_guides"] = lens_stack(physical(S), n_head, False)
    if n_free > 0:
        out["hair_guides_free"] = lens_stack(physical({**S, **(S.get("free") or {})}, free=True, tail=tail), n_free, True)
    if n_wisp > 0:  # single hairs: no clumps to join, no strays of strays; each keeps most of its length
        ph = wisp_physical(S)
        st = lens_stack(ph, n_wisp, True)
        st[-1][1]["Radius"] = ph["radius"] * hair_strands.WISP_RADIUS
        st[0][1]["Fine"] = 1.0
        out[hair_strands.WISPS] = st
    if n_even > 0:  # even roots, shaped by the lock guides (the guides are these curves; the children replace them)
        ph = physical({**S, **(S.get("free") or {})}, free=True, tail=tail)
        out["hair_even"] = [
            ["Interpolate Hair Curves", {"Surface:Object": {"object": "hair_scalp"},
                                         "Surface UV Map": {"attribute": "UVMap"}, "Surface Rest Position": False,
                                         "Follow Surface Normal": False, "Part by Mesh Islands": True,
                                         "Interpolation Guides": int(S.get("even_guides") or (1 if even_all else 3)),
                                         "Distance to Guides": 0.03,
                                         "Density": float(n_even / max(area, 1e-6)),
                                         "Density Mask": {"attribute": "hp_density_even_l" if banks else "hp_density_even"},
                                         "Viewport Amount": 1.0, "Seed": int(seed) + 7}],
        ]
        if not even_all:
            # a COVER layer, not the lengths: trimmed to EVEN_LEN m (x 0.6..1): interpolated children translate their
            # guides' shapes, and full-length ones near the face hung over it as a veil; the lengths are the
            # locks' (which keep the face rule), the even layer covers the scalp under them
            out["hair_even"].append(["Trim Hair Curves", {"Scale Uniform": True, "Length Factor": hair_strands.EVEN_LEN,
                                                          "Replace Length": True, "Random Offset": 0.4,
                                                          "Seed": int(seed) + 8}])
        else:
            # interpolated children are smooth and evenly spaced: no clumps, a helmet. Blender's Clump
            # (its own guide map: one guide every clump_size m) draws neighbours together toward the tips
            # (on short hair too: the nape starbursts once blamed on it (E6) were the collider pushing short locks up the
            # scalp (E7 kept them without Clump); a crop without clumps read as a uniform bristle carpet, G6)
            if True:
                out["hair_even"].append(["Clump Hair Curves", {
                    "Factor": float(np.clip(ph["clump"], 0.0, 1.0)), "Shape": 0.5,
                    "Tip Spread": 0.002 * float(ph["tip_spread01"]), "Clump Offset": 0.0, "Distance Falloff": 0.0,
                    "Distance Threshold": 0.0, "Seed": int(seed) + 9, "Preserve Length": True,
                    "Guide Distance": float(ph["clump_size"]), "Guide Mask": 1.0, "Existing Guide Map": False}])
            # ... and the colour model's per-lock numbers (lock lightness, highlight ribbons) from the root's cell:
            # without them every child shaded alike, one solid black hood
            out["hair_even"].append(["hp_cells", {"Seed": int(seed)}])
        out["hair_even"] += [
            ["Hair Curves Noise", {"Cumulative Offset": False, "Factor": 1.0, "Distance": ph["loose"] + 0.0008, "Shape": 0.5,
                                   "Scale": ph["loose_scale"] * 2, "Scale along Curve": 0.35, "Offset per Curve": 0.3,
                                   "Seed": int(seed) + 2, "Preserve Length": True}],
            ["Frizz Hair Curves", {"Cumulative Offset": False, "Factor": 1.0, "Distance": ph["frizz"] + 0.0001, "Shape": 0.5,
                                   "Seed": int(seed) + 2, "Preserve Length": True}],
            ["Shrinkwrap Hair Curves", {"Surface:Object": body, "Factor": 1.0, "Above Surface": 0.0015,
                                        "Offset Distance": 0.0015, "Smoothing Steps": 1, "Lock Roots": True}],
            ["hp_profile", {"Radius": ph["radius"], "Tip": ph["tip_radius"], "Taper": 0.3, "Root": 0.8}],
        ]
    if n_even > 0 and banks and not even_objs:  # the right bank: the same stack on its own mask
        import copy as _copy
        st_r = _copy.deepcopy(out["hair_even"])
        st_r[0][1]["Density Mask"] = {"attribute": "hp_density_even_r"}
        st_r[0][1]["Seed"] = int(seed) + 17
        out["hair_even_r"] = st_r
    if n_even > 0 and even_objs:  # [(object, mask attribute, guides)]: the bank x zone objects (the same stack each)
        import copy as _copy
        base_ = out.pop("hair_even")
        for i_, (nm_, attr_, ng_) in enumerate(even_objs):
            st_ = _copy.deepcopy(base_)
            st_[0][1]["Density Mask"] = {"attribute": attr_}
            st_[0][1]["Interpolation Guides"] = int(ng_)
            st_[0][1]["Seed"] = int(seed) + 7 + 10 * i_
            out[nm_] = st_
    if n_under > 0:
        ph = physical(S)
        out["hair_under"] = [
            ["Interpolate Hair Curves", {"Surface:Object": {"object": "hair_scalp"},
                                         "Surface UV Map": {"attribute": "UVMap"}, "Surface Rest Position": False,
                                         "Follow Surface Normal": False, "Part by Mesh Islands": False,
                                         "Interpolation Guides": 4, "Distance to Guides": 0.03,
                                         "Density": float(n_under / max(area, 1e-6)),
                                         "Density Mask": {"attribute": "hp_density"}, "Viewport Amount": 1.0,
                                         "Seed": int(seed)}],
            ["Trim Hair Curves", {"Scale Uniform": True, "Length Factor": 1.0, "Replace Length": False,
                                  "Random Offset": 0.5, "Seed": int(seed)}],
            ["Hair Curves Noise", {"Cumulative Offset": False, "Factor": 1.0, "Distance": 0.5 * ph["loose"] + 0.0006, "Shape": 0.5,
                                   "Scale": ph["loose_scale"] * 2, "Scale along Curve": 0.35, "Offset per Curve": 0.3,
                                   "Seed": int(seed) + 1, "Preserve Length": True}],
            ["Frizz Hair Curves", {"Cumulative Offset": False, "Factor": 1.0, "Distance": ph["frizz"] + 0.0001, "Shape": 0.5,
                                   "Seed": int(seed) + 1, "Preserve Length": True}],
            ["Shrinkwrap Hair Curves", {"Surface:Object": body, "Factor": 1.0, "Above Surface": 0.0008,
                                        "Offset Distance": 0.0008, "Smoothing Steps": 1, "Lock Roots": True}],
            ["hp_profile", {"Radius": ph["radius"], "Tip": 0.15, "Taper": 0.6, "Root": 0.8}],
        ]
    return out


def job(sc, g: dict, spec: dict, locks: list, tmp: Path, count: int | None = None, col=None) -> dict:
    """What blender_strands.show needs (files in tmp)."""
    import re
    from .hair_groom import hairline, look_of
    from .hair_spec import hair_of
    h = hair_of(spec)
    S = hc.strands_of(spec)
    if count:
        S = {**S, "count": int(count)}
    look = look_of(spec, h)
    if not look.get("cycles_fit"):
        look["cycles_fit"] = list(hair_strands.CYCLES_FIT)
    seed = int(g.get("seed", 0))
    bands = [k for k in locks if re.fullmatch(r"t\d*band", k["name"])]
    hair_locks = [k for k in locks if k not in bands]
    line = hairline(sc, g)
    from .hair_groom import inside
    for k_ in hair_locks:  # locks rooted at the hairline: their strands start one by one over a longer stretch
        if not k_.get("free"):
            a0, e0_, h0 = sc.coords(np.asarray(k_["pts"][0], float)[None])
            k_["at_hairline"] = bool(h0[0] < 0.01 and inside(sc, line, a0, e0_)[0] < 0.008)
        elif k_.get("tier") == "loose":
            # LOOSE hair rooted at the hairline (hair-garrett, rule 15): the same staggered starts, and FEWER strands
            # the nearer the line (a density ramp over EDGE_RAMP m: real hairlines thin out over 3-4 mm). Without it
            # each front lock started all its strands on one row: the hairline was a row of comb teeth
            a0, e0_, h0 = sc.coords(np.asarray(k_["pts"][0], float)[None])
            d0 = float(inside(sc, line, a0, e0_)[0])
            # (loose roots start ~4 mm inside the line, the scalp layer covers the strip: the ramp runs from there)
            if h0[0] < 0.01 and d0 < hair_strands.EDGE_START + hair_strands.EDGE_RAMP:
                k_["at_hairline"] = True
                k_["edge_density"] = float(hair_strands.EDGE_MIN + (1 - hair_strands.EDGE_MIN) * _ss((d0 - hair_strands.EDGE_START) / hair_strands.EDGE_RAMP))
    sm = scalp_mesh(sc, g, line, S)
    area, e0, xp_ = sm.pop("area"), sm.pop("e0"), sm.pop("xp")
    sm_keys = list(sm)
    np.savez(tmp / "strand_scalp.npz", **sm)
    np.savez(tmp / "strand_collide.npz", **(col.mesh() if col is not None else collide_mesh(sc)))  # (loose hair: the
    # body's own surface down to the back, hair_loose.Collider)
    G = lock_guides(hair_locks, sc.C, S, seed)
    ug = under_guides(sc, g, line, hair_locks, S, seed)
    ph = physical(S)
    n_under = 0.0
    if ug is not None:
        n_under = min(0.6 * ph["count"], float(S["under"]) * area * hair_strands.UNDER_PER_M2 * ph["count"] / 30000.0)
        if not G:
            n_under = max(n_under, 0.9 * ph["count"])
    n_locks = ph["count"] - n_under
    # EVEN ROOTS (hair-heads; Joe: "hair distribution over the growing area is fairly even; parts are from styling, not
    # distribution"): a share `even` of the strands grows from ONE even sampling of the hair-bearing scalp (Blender's
    # Interpolate Hair Curves on the scalp mesh, its density the hairline ramp only, no thinning at the part) and takes
    # its SHAPE from the nearest lock guides: the locks only steer direction, so a part, a sweep or a whorl is the comb,
    # never a gap between locks. The rest stays lock strands (clumps, ribbons, the detail).
    # strands.even >= EVEN_ALL: EVERY strand from the even roots (Joe's model: density is uniform, the style is only
    # direction): the locks are GUIDES (march them dense: groom.loose.spacing ~4 mm, so a child's guides are a few mm
    # away, on its side of the part, and already obey the face rule), no lock strands; single hairs keep their own
    ev = float(np.clip(S.get("even") or 0.0, 0.0, 1.0))
    even_all = ev >= hair_strands.EVEN_ALL
    n_even, eg = 0.0, None
    if ev > 0 and any(k in G for k in ("head", "free")):
        cs = [G[k]["counts"] for k in ("head", "free") if k in G]
        ps = [G[k]["pts"] for k in ("head", "free") if k in G]
        cnt = np.concatenate(cs).astype(np.int32)
        pts = np.concatenate(ps).astype(np.float32)
        first = np.r_[0, np.cumsum(cnt)[:-1]]
        eg = {"counts": cnt, "pts": pts, "uv": scalp_uv(sc, pts[first], e0, xp_).astype(np.float32),
              "names": np.asarray([f"e{i}" for i in range(len(cnt))])}
        # each guide's grey share (hp_gr) for its children: from whichever groups there are (loose hair has only
        # "free" guides: keyed on "head", the even children of a grey crop lost their grey, Garrett E2)
        if all("gr" in G[k] for k in ("head", "free") if k in G):
            eg["gr"] = np.concatenate([G[k]["gr"] for k in ("head", "free") if k in G]).astype(np.float32)
        n_even = ev * n_locks
        n_locks = n_locks - n_even
    wsum = sum(float(G[k]["weight"].sum()) for k in G) or 1.0
    amount, groups = {}, []
    for key, name in (("head", "hair_guides"), ("free", "hair_guides_free"), ("wisp", hair_strands.WISPS)):
        if key not in G or (even_all and n_even > 0 and key != "wisp"):
            continue
        gg = G[key]
        hairs = gg.pop("hairs")
        share = gg.pop("weight") * gg.pop("density", 1.0) / wsum * n_locks  # strands per lock
        base = np.maximum(np.round(share / 8.0), 1).astype(np.int32)  # hp_n: an eighth, the lens group's Amount = 8
        if key == "wisp":  # exactly `hairs` strands a lock (Amount 1)
            share = base = hairs
        gg["n"] = base
        gg["uv"] = scalp_uv(sc, gg["pts"].reshape(len(base), -1, 3)[:, 0], e0, xp_).astype(np.float32)
        amount[name] = float(share.sum() / max(base.sum(), 1))
        np.savez(tmp / f"{name}.npz", **gg)
        groups.append({"name": name, "guides": str(tmp / f"{name}.npz"), "locks": int(len(base)),
                       "strands": int(round(share.sum()))})
    banks = eg is not None and xp_ is not None
    even_objs = []
    if eg is not None:
        sides = [("hair_even", None)]
        if banks:
            cnt_ = eg["counts"]
            first_ = np.r_[0, np.cumsum(cnt_)[:-1]]
            right = (eg["pts"][first_, 0] - sc.C[0] - xp_) > 0
            sides = [("hair_even", ~right), ("hair_even_r", right)]
        zoned = any(k.endswith("_n") for k in sm_keys)
        ng_auto = S.get("even_guides")
        for nm_, sel_ in sides:
            e_ = eg if sel_ is None else _guides_subset(eg, sel_)
            if sel_ is not None and not sel_.any():
                continue
            np.savez(tmp / f"{nm_}.npz", **e_)
            share_ = 1.0 if sel_ is None else float(sel_.mean())
            attr_ = "hp_density_even" + ("" if sel_ is None else ("_r" if nm_.endswith("_r") else "_l"))
            if zoned:  # blend (3 guides) outside the split zone, the nearest guide in it
                for nm2, a2, ng2 in ((nm_, attr_, int(ng_auto or 3)), (nm_ + "_n", attr_ + "_n", int(ng_auto or 1))):
                    groups.append({"name": nm2, "guides": str(tmp / f"{nm_}.npz"), "locks": int(len(e_["counts"])),
                                   "strands": int(round(n_even * share_ * 0.5))})
                    even_objs.append((nm2, a2, ng2))
            else:
                groups.append({"name": nm_, "guides": str(tmp / f"{nm_}.npz"), "locks": int(len(e_["counts"])),
                               "strands": int(round(n_even * share_))})
                if even_all:
                    even_objs.append((nm_, attr_ if sel_ is not None else "hp_density_even", int(ng_auto or 3)))
    if ug is not None:
        ug["uv"] = scalp_uv(sc, ug["pts"].reshape(len(ug["counts"]), -1, 3)[:, 0], e0, xp_).astype(np.float32)
        np.savez(tmp / "hair_under.npz", **ug)
        groups.append({"name": "hair_under", "guides": str(tmp / "hair_under.npz"), "locks": int(len(ug["counts"])),
                       "strands": int(round(n_under))})
    # is the free hair a TAIL (tied hair that left the head) or LOOSE hair (groom.loose, no tie)? a tail keeps its
    # quartered halo; loose hair takes groom.loose's own halo / flyaway words (rule 4's knob for a loose head)
    tail = any(float(k_.get("free", 0.0)) > 0.5 and k_.get("tier") != "loose" for k_ in hair_locks)
    lo_ = g.get("loose") or {}
    if not tail and (lo_.get("halo") is not None or lo_.get("flyaway") is not None):
        fw = {k: float(lo_[k]) for k in ("halo", "flyaway") if lo_.get(k) is not None}
        S = {**S, "free": {**(S.get("free") or {}), **fw}}
    st = stacks(S, amount.get("hair_guides", 0.0), amount.get("hair_guides_free", 0.0), n_under, area, seed,
                n_wisp=amount.get(hair_strands.WISPS, 0.0), tail=tail, n_even=n_even, even_all=even_all, banks=banks,
                even_objs=even_objs or None, short_even=_longest(g) <= 0.1)
    for grp in groups:
        grp["stack"] = st[grp["name"]]
    out = {"scalp": str(tmp / "strand_scalp.npz"), "collide": str(tmp / "strand_collide.npz"), "groups": groups, "look": look, "physical": ph,
           "scalp_area": round(area, 5), "e0": e0}
    if bands:
        from . import hair_tied
        tile = [{"kind": "band", "u0": 0.0, "u1": 1.0}]
        b = hair_cards_budget.join(*[hair_tied.band_mesh(k, tile) for k in bands])
        np.savez(tmp / "strand_band.npz", verts=b["verts"], tris=b["tris"])
        out["band"] = str(tmp / "strand_band.npz")
    return out


def _npz_hash(hsh, path) -> None:
    """An npz's arrays into a hash (its bytes carry the zip's timestamps: the same job hashed differently a second
    later, so every look and every export tier re-evaluated the groom in Blender and filled the cache)."""
    z = np.load(path, allow_pickle=False)
    for k in sorted(z.files):
        a = np.ascontiguousarray(z[k])
        hsh.update(k.encode())
        hsh.update(str(a.dtype).encode() + str(a.shape).encode())
        hsh.update(a.tobytes())


def key(sd: dict) -> str:
    """A content hash of a strands job's GEOMETRY (its numbers and files; not its colours, not where its files
    lie): the evaluated strands, the cards and the cap chart are cached on it."""
    hsh = hashlib.sha1(json.dumps({k: v for k, v in sd.items() if k not in ("scalp", "groups", "band", "collide", "look")},
                                  sort_keys=True, default=float).encode())
    for grp in sd["groups"]:
        _npz_hash(hsh, grp["guides"])
        hsh.update(json.dumps(grp["stack"], sort_keys=True, default=float).encode())
    for k in ("scalp", "collide"):
        if sd.get(k) and Path(sd[k]).exists():
            _npz_hash(hsh, sd[k])
    return hsh.hexdigest()[:16]
