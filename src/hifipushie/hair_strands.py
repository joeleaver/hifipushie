"""Hair as strands: the groom on Blender's own hair system (Hair Curves + the Essentials hair node groups).

`spec["hair"]["style"] = "strands"`. The spec's locks stay what a model reasons in (a spine with a width, a thickness
and a shape along it); here they become GUIDES:

  locks on the head / locks that leave it   one guide curve a lock, carrying the lock's section per point. Children
        are spread across that section (a lens: `blender_strands.lens_group`), so a lock is a flat clump of strands,
        not a rope round its guide.
  the scalp layer   short flow guides all over the scalp inside the hairline (their direction read off the locks
        above them), children by Blender's "Interpolate Hair Curves" on the scalp mesh's UV map, density from the
        hairline's fade and the parting. It is the hair's root: the soft hairline, the baby hairs, the cover under
        the locks (what the dark underlayer shell was for solid locks).

`spec["hair"]["strands"]` holds the groom numbers (hair_cards.STRANDS). They are 0..1 dials mapped here onto the
ranges that work (`physical`): the spike behind this found frizz of 0.2-0.4 mm right and 2-4 mm a cloud, and clumping
every strand of a lock to its guide a rope, so the dials can't reach those. Everything Blender needs is `job`: the
scalp mesh, the guide files and each object's modifier stack with its numbers, so the mapping is testable without
Blender and a person sees ordinary Essentials modifiers.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import hair_cards as hc

LENS = "hp_lens"
STRAND_RADIUS = 0.00008  # m at 30k strands (a real hair is 0.03-0.05 mm; fewer, wider strands cover the same)
UNDER_PER_M2 = 2.6e5  # scalp-layer strands per m2 of scalp at under = 1 and 30k strands
SEED_SPACING = 0.011  # m between the scalp layer's flow guides
# what each 0..1 dial may reach (the top of each range is where it still reads as hair)
SAFE = {
    "frizz_m": 0.0006,  # single strands off their neighbours: 0.2-0.4 mm reads as hair, 2 mm+ as a cloud
    "loose_m": 0.006,  # strands wandering TOGETHER (low frequency): loosens a lock without fuzzing it
    "clump": 0.75,  # the Essentials Clump factor at clump = 1 (to sub clumps `clump_size` apart, never to the lock)
    "flyaway": 0.12,  # share of a lock's strands that let go of it
    "flyaway_m": 0.02,  # how far a fly-away gets at its tip (x 2 on hair that leaves the head)
    "tips": 0.55,  # share of its length the shortest strand of a lock loses
    "roots": 0.12,  # share of a lock's length over which its strands' starts are staggered
    "curl_m": 0.006,  # radius of the ringlet a strand winds round its clump at curl = 1
}


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def physical(S: dict, free: bool = False) -> dict:
    """The dials as the numbers Blender's nodes take (metres, factors). `free`: hair that has left the head."""
    c = lambda k: float(np.clip(S[k], 0.0, 1.0))  # noqa: E731
    count = max(int(S["count"]), 200)
    return {
        "count": count,
        "radius": float(STRAND_RADIUS * float(S["thickness"]) * np.clip(np.sqrt(30000.0 / count), 0.6, 3.0)),
        "clump": SAFE["clump"] * c("clump"),
        "clump_size": float(np.clip(S["clump_size"], 0.002, 0.03)) * (1.5 if free else 1.0),
        "clump_shape": float(np.clip(S["clump_shape"], 0.0, 1.0)),
        "tip_spread": 0.012 * c("tip_spread") * (1.6 if free else 1.0),
        "frizz": SAFE["frizz_m"] * c("frizz") * (1.5 if free else 1.0),
        "loose": SAFE["loose_m"] * c("loose") * (2.0 if free else 1.0),
        "loose_scale": 1.0 / max(float(S["wavelength"]), 0.02) * 0.6,
        "flyaway": SAFE["flyaway"] * c("flyaway"),
        "flyaway_m": SAFE["flyaway_m"] * (2.0 if free else 1.0),
        "tips": SAFE["tips"] * c("tips"),
        "roots": SAFE["roots"] * c("roots") * (0.3 if free else 1.0),
        "curl": SAFE["curl_m"] * c("curl") * (1.0 if free else 0.3),
        "curl_freq": 1.0 / max(float(S["wavelength"]), 0.01),
    }


def lock_guides(locks: list, C, S: dict, seed: int = 0, n_head: int = 24, n_free: int = 32) -> dict:
    """{"head": G, "free": G}: G = {"counts", "pts", "side", "out", "weight", "lock", "names"} (the guide arrays of
    blender_strands.curves_object; `weight` = each lock's share of the strands, by its section)."""
    from .hair import lock_width
    out = {}
    lam = max(float(S["wavelength"]), 0.01)
    for key in ("head", "free"):
        sel = [(i, lk) for i, lk in enumerate(locks) if (float(lk.get("free", 0.0)) > 0.5) == (key == "free")]
        if not sel:
            continue
        n = n_free if key == "free" else n_head
        P_, S_, O_, W_, I_, N_ = [], [], [], [], [], []
        for i, lk in sel:
            Sl = {**S, **{k: v for k, v in (lk.get("strands") or {}).items() if k in S}}
            rng = np.random.default_rng([seed, int(hashlib.md5(lk["name"].encode()).hexdigest()[:8], 16)])
            inp = lk["inputs"]
            P, rad, tilt, u, s = hc.spine(lk, n)
            ang = np.radians(inp.get("Flip", 0.0) + inp.get("Twist", 0.0) * u) + tilt
            T, N, B, _ = hc.frames(P, C, ang, lk.get("core"))
            W, th = float(inp["Width"]), float(inp["Thickness"])
            lw = np.clip(lock_width(inp, u) * rad, 0.0, 4.0)
            belly = max(float(inp.get("Belly", 0.3)), 0.02)
            # the lock's own taper would bring every strand to one point (a wet paint brush): the section stays
            # open toward the tip and the strands end one by one instead (lens group "Tips")
            floor = (0.55 if key == "free" else 0.4) + 0.3 * float(np.clip(Sl["tip_spread"], 0, 1))
            lw = lw + np.clip(floor - lw, 0.0, None) * _ss((u - belly) / 0.3)
            fr = float(lk.get("free", 0.0))
            R = float(Sl["random"])
            A = float(Sl["wave"]) * (0.3 + 0.7 * fr) * (1 + R * rng.uniform(-0.4, 0.4))
            ph = rng.uniform(0, 2 * np.pi) * R + 2 * np.pi * s / lam
            env = _ss(s / 0.03)
            P = P + B * (A * env * np.sin(ph))[:, None] + N * (A * env * float(Sl["curl"]) * fr * np.cos(ph))[:, None]
            hw = W / 2 * lw
            ht = np.maximum(th / 2 * float(Sl["flat"]) * np.maximum(lw, 0.3) ** 0.5, 0.0008)
            P_.append(P)
            S_.append(B * hw[:, None])
            O_.append(N * ht[:, None])
            W_.append(W * max(th * float(Sl["flat"]), 0.004) * (1.0 if key == "head" else 1.6))
            I_.append(i)
            N_.append(lk["name"])
        out[key] = {"counts": np.full(len(sel), n, np.int32), "pts": np.concatenate(P_).astype(np.float32),
                    "side": np.concatenate(S_).astype(np.float32), "out": np.concatenate(O_).astype(np.float32),
                    "weight": np.asarray(W_, float), "lock": np.asarray(I_, np.int32), "names": np.asarray(N_)}
    return out


def scalp_mesh(sc, g: dict, line, S: dict, step: float = 3.0) -> dict:
    """The scalp inside the hairline (a margin outside it) as a triangle mesh with a UV map (u = azimuth / 360,
    v = elevation over its range: a chart Blender's Interpolate and Curves sculpt tools attach hair to) and
    `hp_density`: 0 just outside the hairline, 1 `soft` m inside, thinned along the parting."""
    from .hair import _part, inside
    A = np.arange(0.0, 360.0 + 1e-6, step)  # (the seam column twice: az 0 and 360)
    e0 = float(np.floor(max(line.min() - 12.0, sc.EL[0] + 2)))
    E = np.arange(e0, 88.0 + 1e-6, step)
    AA, EE = np.meshgrid(A, E, indexing="ij")
    d_in = inside(sc, line, AA % 360, EE)
    V = sc.point(AA % 360, EE, 0.0004).reshape(-1, 3)
    soft = max(float(S["soft"]), 0.001)
    dens = _ss((d_in + 0.0015) / soft)
    pw = float(g["parting"].get("width", 0.012))
    dens = dens * (1 - 0.9 * np.clip(_part(sc, g, AA % 360, EE, 0.25 * pw), 0, 1))
    na, ne = AA.shape
    idx = np.arange(na * ne).reshape(na, ne)
    live = d_in > -0.008
    uvv = np.stack([AA / 360.0, (EE - e0) / (90.0 - e0)], -1).reshape(-1, 2)
    a, b, c, d = idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]
    ok = (live[:-1, :-1] | live[1:, :-1] | live[1:, 1:] | live[:-1, 1:]).ravel()
    q = np.stack([a.ravel(), b.ravel(), c.ravel(), d.ravel()], 1)[ok]
    F = np.concatenate([q[:, [0, 1, 2]], q[:, [0, 2, 3]]])
    # the pole: a fan from the top row to one vertex
    pole = len(V)
    V = np.vstack([V, sc.point(0.0, 90.0, 0.0004)[None]])
    uvp = len(uvv)
    top = idx[:, -1]
    fan = np.stack([top[:-1], top[1:], np.full(na - 1, pole)], 1)
    F = np.concatenate([F, fan])
    dens = np.r_[dens.ravel(), 1.0]
    uv_corner = np.concatenate([uvv[F[:len(F) - len(fan)]],
                                np.stack([uvv[fan[:, 0]], uvv[fan[:, 1]],
                                          np.stack([(uvv[fan[:, 0], 0] + uvv[fan[:, 1], 0]) / 2,
                                                    np.ones(len(fan))], 1)], 1)])
    del uvp
    used = np.unique(F)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    tri = V[F]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    return {"verts": V[used].astype(np.float32), "faces": remap[F].astype(np.int32),
            "uv": uv_corner.reshape(-1, 2).astype(np.float32), "hp_density": dens[used].astype(np.float32),
            "area": float((area * dens[F].mean(1)).sum()), "e0": e0}


def scalp_uv(sc, P, e0: float):
    """The scalp chart's uv under world points."""
    az, el, _ = sc.coords(P)
    return np.stack([(az % 360) / 360.0, (el - e0) / (90.0 - e0)], -1)


def _sphere(n: int):
    k = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * k / n)
    th = np.pi * (1 + 5 ** 0.5) * k
    return np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], 1)


def under_guides(sc, g: dict, line, locks: list, S: dict, seed: int = 0, n: int = 10) -> dict | None:
    """The scalp layer's guides: from seeds all over the scalp inside the hairline, each run along the flow of the
    locks over it (the direction of the nearest lock spines, laid in the scalp's tangent plane) for `under_length`,
    rising from the skin to just under those locks. Seeds on the hairline itself are the baby hairs: short."""
    from scipy.spatial import cKDTree
    from .hair import az_el, inside
    if float(S["under"]) <= 0:
        return None
    rng = np.random.default_rng([seed, 77])
    r0 = float(np.median(sc.R))
    D = _sphere(int(4 * np.pi * r0 * r0 / SEED_SPACING ** 2))
    az, el = az_el(D)
    az, el = az + rng.uniform(-1, 1, len(az)), el + rng.uniform(-1, 1, len(az))
    d_in = inside(sc, line, az % 360, el)
    keep = (d_in > -0.001) & (el > sc.EL[0] + 3)
    az, el, d_in = az[keep] % 360, el[keep], d_in[keep]
    if not len(az):
        return None
    L = float(S["under_length"]) * (0.3 + 0.7 * _ss(d_in / 0.02)) * (1 + 0.3 * rng.uniform(-1, 1, len(az)))
    if float(S["baby"]) > 0:  # baby hairs: more seeds on the line, short and a little wild
        ab = rng.uniform(0, 360, int(60 * float(S["baby"])))
        eb = np.interp(ab, np.arange(361.0), np.r_[line, line[:1]]) + rng.uniform(0.0, 1.5, len(ab))
        ok = eb > sc.EL[0] + 3
        az, el = np.r_[az, ab[ok]], np.r_[el, eb[ok]]
        L = np.r_[L, rng.uniform(0.006, 0.016, int(ok.sum()))]
    head = [lk for lk in locks if float(lk.get("free", 0.0)) <= 0.5]
    tree = None
    if head:
        LP, LT = [], []
        for lk in head:
            P, *_ = hc.spine(lk, 16)
            LP.append(P)
            LT.append(_unit(np.gradient(P, axis=0)))
        LP, LT = np.concatenate(LP), np.concatenate(LT)
        _, _, LH = sc.coords(LP)
        tree = cKDTree(LP)
    p = sc.point(az, el, 0.0003)
    pts = [p]
    h = np.full(len(az), 0.0003)
    for k in range(1, n):
        nrm = sc.normal(az, el)
        if tree is not None:
            d, j = tree.query(p, k=min(6, len(LP)))
            w = 1.0 / (d + 0.003) ** 2
            t = (LT[j] * w[..., None]).sum(1)
            hl = (LH[j] * w).sum(1) / w.sum(1)
        else:
            t = np.tile([0.0, 0.25, -1.0], (len(p), 1))
            hl = np.full(len(p), 0.004)
        t = t - (t * nrm).sum(1, keepdims=True) * nrm
        bad = np.linalg.norm(t, axis=1) < 1e-4
        t[bad] = (np.array([0.0, 0.2, -1.0]) - nrm[bad] * nrm[bad, 2:3])
        t = _unit(t)
        s = k / (n - 1)
        q = p + t * (L / (n - 1))[:, None]
        az, el, _ = sc.coords(q)
        # up from the skin to just under the locks over it, by half its length
        h = np.clip(hl - 0.002, 0.0006, 0.03) * _ss(s / 0.5) + 0.0006
        p = sc.point(az, el, h)
        pts.append(p)
    P = np.stack(pts, 1)  # (seeds, n, 3)
    return {"counts": np.full(len(P), n, np.int32), "pts": P.reshape(-1, 3).astype(np.float32),
            "names": np.asarray([f"u{i}" for i in range(len(P))])}


def stacks(S: dict, n_head: float, n_free: float, n_under: float, area: float, seed: int = 0) -> dict:
    """Each object's modifier stack: [[node group, {input: value}], ...]. {"part": name} = the scene object of that
    part (the body: strands are kept out of it), {"attribute": name} = a named attribute as a field."""
    body = {"part": "body"}

    def lens_stack(ph, amount, free):
        st = [[LENS, {"Amount": float(amount), "Tips": ph["tips"], "Roots": ph["roots"], "Flyaway": ph["flyaway"],
                      "Flyaway Distance": ph["flyaway_m"], "Edge": 0.8, "Seed": int(seed)}]]
        if ph["clump"] > 0:
            st.append(["Clump Hair Curves", {"Factor": ph["clump"], "Shape": ph["clump_shape"],
                                             "Tip Spread": ph["tip_spread"], "Guide Distance": ph["clump_size"],
                                             "Distance Falloff": 0.0, "Distance Threshold": ph["clump_size"] * 1.5,
                                             "Seed": int(seed), "Preserve Length": True}])
        if ph["curl"] > 0:
            st.append(["Curl Hair Curves", {"Factor": 1.0, "Subdivision": 2, "Curl Start": 0.15, "Radius": ph["curl"],
                                            "Factor Start": 0.0, "Factor End": 1.0, "Frequency": ph["curl_freq"],
                                            "Random Offset": 1.0, "Seed": int(seed),
                                            "Guide Distance": ph["clump_size"]}])
        if ph["loose"] > 0:
            st.append(["Hair Curves Noise", {"Factor": 1.0, "Distance": ph["loose"], "Shape": 0.5,
                                             "Scale": ph["loose_scale"], "Scale along Curve": 0.35,
                                             "Offset per Curve": 0.15, "Seed": int(seed), "Preserve Length": True}])
        if ph["frizz"] > 0:
            st.append(["Frizz Hair Curves", {"Factor": 1.0, "Distance": ph["frizz"], "Shape": 0.5, "Seed": int(seed),
                                             "Preserve Length": True}])
        st.append(["Shrinkwrap Hair Curves", {"Surface:Object": body, "Factor": 1.0, "Above Surface": 0.0015,
                                              "Offset Distance": 0.0015, "Smoothing Steps": 2 if not free else 4,
                                              "Lock Roots": False}])
        st.append(["Set Hair Curve Profile", {"Replace Radius": True, "Radius": ph["radius"], "Shape": 0.35,
                                              "Factor Min": 0.6, "Factor Max": 0.1}])
        return st

    out = {}
    if n_head > 0:
        out["hair_guides"] = lens_stack(physical(S), n_head, False)
    if n_free > 0:
        out["hair_guides_free"] = lens_stack(physical(S, free=True), n_free, True)
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
            ["Hair Curves Noise", {"Factor": 1.0, "Distance": 0.5 * ph["loose"] + 0.0006, "Shape": 0.5,
                                   "Scale": ph["loose_scale"] * 2, "Scale along Curve": 0.35, "Offset per Curve": 0.3,
                                   "Seed": int(seed) + 1, "Preserve Length": True}],
            ["Frizz Hair Curves", {"Factor": 1.0, "Distance": ph["frizz"] + 0.0001, "Shape": 0.5,
                                   "Seed": int(seed) + 1, "Preserve Length": True}],
            ["Shrinkwrap Hair Curves", {"Surface:Object": body, "Factor": 1.0, "Above Surface": 0.0008,
                                        "Offset Distance": 0.0008, "Smoothing Steps": 1, "Lock Roots": True}],
            ["Set Hair Curve Profile", {"Replace Radius": True, "Radius": ph["radius"] * 0.9, "Shape": 0.35,
                                        "Factor Min": 0.6, "Factor Max": 0.05}],
        ]
    return out


def job(sc, g: dict, spec: dict, locks: list, tmp: Path, count: int | None = None) -> dict:
    """What blender_strands.show needs (files in tmp)."""
    import re
    from .hair import LOOK, hair_of, hairline
    h = hair_of(spec)
    S = hc.strands_of(spec)
    if count:
        S = {**S, "count": int(count)}
    look = {**LOOK, **(h.get("look") or {})}
    seed = int(g.get("seed", 0))
    bands = [k for k in locks if re.fullmatch(r"t\d*band", k["name"])]
    hair_locks = [k for k in locks if k not in bands]
    line = hairline(sc, g)
    sm = scalp_mesh(sc, g, line, S)
    area, e0 = sm.pop("area"), sm.pop("e0")
    np.savez(tmp / "strand_scalp.npz", **sm)
    G = lock_guides(hair_locks, sc.C, S, seed)
    ug = under_guides(sc, g, line, hair_locks, S, seed)
    ph = physical(S)
    n_under = 0.0
    if ug is not None:
        n_under = min(0.45 * ph["count"], float(S["under"]) * area * UNDER_PER_M2 * ph["count"] / 30000.0)
        if not G:
            n_under = max(n_under, 0.9 * ph["count"])
    n_locks = ph["count"] - n_under
    wsum = sum(float(G[k]["weight"].sum()) for k in G) or 1.0
    amount, groups = {}, []
    for key, name in (("head", "hair_guides"), ("free", "hair_guides_free")):
        if key not in G:
            continue
        gg = G[key]
        share = gg.pop("weight") / wsum * n_locks  # strands per lock
        base = np.maximum(np.round(share / 8.0), 1).astype(np.int32)  # hp_n: an eighth, the lens group's Amount = 8
        gg["n"] = base
        gg["uv"] = scalp_uv(sc, gg["pts"].reshape(len(base), -1, 3)[:, 0], e0).astype(np.float32)
        amount[name] = float(share.sum() / max(base.sum(), 1))
        np.savez(tmp / f"{name}.npz", **gg)
        groups.append({"name": name, "guides": str(tmp / f"{name}.npz"), "locks": int(len(base)),
                       "strands": int(round(share.sum()))})
    if ug is not None:
        ug["uv"] = scalp_uv(sc, ug["pts"].reshape(len(ug["counts"]), -1, 3)[:, 0], e0).astype(np.float32)
        np.savez(tmp / "hair_under.npz", **ug)
        groups.append({"name": "hair_under", "guides": str(tmp / "hair_under.npz"), "locks": int(len(ug["counts"])),
                       "strands": int(round(n_under))})
    st = stacks(S, amount.get("hair_guides", 0.0), amount.get("hair_guides_free", 0.0), n_under, area, seed)
    for grp in groups:
        grp["stack"] = st[grp["name"]]
    out = {"scalp": str(tmp / "strand_scalp.npz"), "groups": groups, "look": look, "physical": ph,
           "scalp_area": round(area, 5), "e0": e0}
    if bands:
        from . import hair_tied
        tile = [{"kind": "band", "u0": 0.0, "u1": 1.0}]
        b = hc.join(*[hair_tied.band_mesh(k, tile) for k in bands])
        np.savez(tmp / "strand_band.npz", verts=b["verts"], tris=b["tris"])
        out["band"] = str(tmp / "strand_band.npz")
    return out


def key(sd: dict) -> str:
    """A content hash of a strands job (its numbers and files): the cards / atlas caches are keyed on it."""
    hsh = hashlib.sha1(json.dumps({k: v for k, v in sd.items() if k not in ("scalp", "groups", "band")},
                                  sort_keys=True, default=float).encode())
    for grp in sd["groups"]:
        hsh.update(Path(grp["guides"]).read_bytes())
        hsh.update(json.dumps(grp["stack"], sort_keys=True, default=float).encode())
    hsh.update(Path(sd["scalp"]).read_bytes())
    return hsh.hexdigest()[:16]
