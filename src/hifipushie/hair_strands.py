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
STRAND_RADIUS = 0.00004  # m: a real hair (0.03-0.05 mm), at REAL_COUNT strands; fewer strands are drawn wider so
REAL_COUNT = 100000  # the head stays covered (a path tracer draws true widths: 30k hairs at 0.08 mm were a pale haze)
UNDER_PER_M2 = 3.6e5  # scalp-layer strands per m2 of scalp at under = 1 and 30k strands
SEED_SPACING = 0.011  # m between the scalp layer's flow guides
# what each 0..1 dial may reach (the top of each range is where it still reads as hair)
import os as _os
SAFE = {
    "sub_wave": float(_os.environ.get("HS_SUB_WAVE", 0.25)),  # a sub clump's own swing, x the lock's wave
    "frizz_m": 0.0006,  # single strands off their neighbours: 0.2-0.4 mm reads as hair, 2 mm+ as a cloud
    "loose_m": 0.006,  # strands wandering TOGETHER (low frequency): loosens a lock without fuzzing it
    "clump": 0.9,  # how far a strand is drawn to its sub clump's line at clump = 1 (never to the lock's one line)
    "wander_m": 0.0025,  # a single strand's own slow wander off its clump
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
        "radius": float(STRAND_RADIUS * float(S["thickness"]) * np.clip((REAL_COUNT / count) ** 0.8, 0.8, 4.0)),
        "wave_random": c("random") * (1.0 if free else 0.6),
        "stray": c("stray"),
        "tip_radius": float(np.clip(1.0 - 0.8 * float(S["taper"]), 0.1, 1.0)),
        "clump": SAFE["clump"] * c("clump") * (float(_os.environ.get("HS_FREE_CLUMP", 0.7)) if free else 1.0),
        "wave": SAFE["sub_wave"] * float(np.clip(S["wave"], 0.0, 0.03)) * (1.0 if free else 0.3),
        "wavelength": float(np.clip(S["wavelength"], 0.01, 1.0)),
        "curl01": c("curl") * (1.0 if free else 0.3),
        "wander": SAFE["wander_m"] * c("loose") * (2.0 if free else 1.0),
        "clump_size": float(np.clip(S["clump_size"], 0.002, 0.03)),
        "clump_shape": float(np.clip(S["clump_shape"], 0.0, 1.0)),
        "tip_spread01": c("tip_spread"),
        "frizz": SAFE["frizz_m"] * c("frizz") * (1.5 if free else 1.0),
        "loose": SAFE["loose_m"] * c("loose") * (2.0 if free else 1.0),
        "loose_scale": 1.0 / max(float(S["wavelength"]), 0.02) * 0.6,
        "flyaway": SAFE["flyaway"] * c("flyaway"),
        "flyaway_m": SAFE["flyaway_m"] * (2.0 if free else 1.0),
        "tips": SAFE["tips"] * c("tips") * (1.3 if free else 1.0),
        "roots": SAFE["roots"] * c("roots") * (0.3 if free else 1.0),
        "curl": SAFE["curl_m"] * c("curl") * (1.0 if free else 0.3),
        "curl_freq": 1.0 / max(float(S["wavelength"]), 0.01),
    }


def is_gather(lk: dict) -> bool:
    """A lock that runs over the head into a tie (hair_tied's gather rows)."""
    import re
    return bool(re.fullmatch(r"t\d*g\d+_\d+", str(lk.get("name", ""))))


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
        P_, S_, O_, W_, I_, N_, K_, F_, R_, WS_, WL_, TS_ = ([] for _ in range(12))
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
            floor = (0.4 if key == "free" else 0.4) + 0.3 * float(np.clip(Sl["tip_spread"], 0, 1))
            floor *= float(np.clip((W - 0.012) / 0.02, 0.0, 1.0))  # (a thin wisp keeps its point)
            gather = is_gather(lk)
            if gather:  # hair drawn to a tie ends IN the tie: the lock narrows into it and every strand gets there
                # (kept open and trimmed like loose hair, the gather stood round the tie as a fan of plates and tufts)
                lw = lw * (1 - 0.75 * _ss((u - 0.5) / 0.5))
            else:
                lw = lw + np.clip(floor - lw, 0.0, None) * _ss((u - belly) / 0.3)
            fr = float(lk.get("free", 0.0))
            R = float(Sl["random"])
            A = 0.6 * float(Sl["wave"]) * (0.3 + 0.7 * fr) * (1 + R * rng.uniform(-0.4, 0.4))
            # a wisp swings less and slower than a lock (at a lock's wave a few hairs side by side are ramen)
            ws = float(np.clip(W / 0.03, 0.2, 1.0))
            wl = 1.0 + 1.2 * float(np.clip(1.0 - W / 0.02, 0.0, 1.0))
            A *= ws
            # neighbours wave nearly in step (a tail swings as sheets of hair; every lock on its own phase is pasta)
            ph = rng.uniform(-1, 1) * R * 1.2 + 2 * np.pi * s / (lam * wl)
            env = _ss(s / 0.03)
            P = P + B * (A * env * np.sin(ph))[:, None] + N * (A * env * float(Sl["curl"]) * fr * np.cos(ph))[:, None]
            hw = W / 2 * lw
            thin = W < 0.016
            if key == "free" and not thin:  # a tail's locks share one volume: their strands run into each other's
                hw = hw * 1.5
            ht = np.maximum(th / 2 * float(Sl["flat"]) * np.maximum(lw, 0.3) ** 0.5, 0.0008)
            if key == "free":  # hair off the head isn't pressed flat: a rounder section (a ribbon twists like bacon)
                ht = np.maximum(ht, 0.4 * hw)
            P_.append(P)
            S_.append(B * hw[:, None])
            O_.append(N * ht[:, None])
            W_.append(W * max(th * float(Sl["flat"]), 0.004 if key == "head" else 0.0015)
                      * (1.0 if key == "head" else 0.9 if thin else 2.5))
            # a fly-away gets as far as its lock is wide (a thin face strand has no 4 cm strays)
            F_.append(min(SAFE["flyaway_m"] * (2.0 if key == "free" else 1.0), 0.8 * W) * (0.3 if gather else 1.0))
            R_.append(4.0 if lk.get("at_hairline") else 1.0)
            TS_.append(0.0 if gather else 1.0)
            WS_.append(ws)
            WL_.append(wl)
            K_.append(max(1, int(round(W / float(np.clip(Sl["clump_size"], 0.002, 0.03))))))
            I_.append(i)
            N_.append(lk["name"])
        out[key] = {"counts": np.full(len(sel), n, np.int32), "pts": np.concatenate(P_).astype(np.float32),
                    "side": np.concatenate(S_).astype(np.float32), "out": np.concatenate(O_).astype(np.float32),
                    "weight": np.asarray(W_, float), "lock": np.asarray(I_, np.int32), "k": np.asarray(K_, np.int32), "fd": np.asarray(F_, np.float32), "rs": np.asarray(R_, np.float32), "ts": np.asarray(TS_, np.float32),
                    "ws": np.asarray(WS_, np.float32), "wl": np.asarray(WL_, np.float32),
                    "names": np.asarray(N_)}
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


def collide_mesh(sc, step: float = 4.0) -> dict:
    """What strands are kept out of: the head, neck and shoulders as the head centre sees them (the scalp's rays), a
    few thousand triangles. Blender's Shrinkwrap against the body's own mesh (hundreds of thousands) took minutes."""
    A = np.arange(0.0, 360.0, step)
    E = np.arange(sc.EL[0], 90.0 - 1e-6, step)
    AA, EE = np.meshgrid(A, E, indexing="ij")
    V = sc.point(AA, EE, 0.0).reshape(-1, 3)
    na, ne = AA.shape
    idx = np.arange(na * ne).reshape(na, ne)
    a, b = idx[:, :-1], np.roll(idx, -1, 0)[:, :-1]
    c, d = np.roll(idx, -1, 0)[:, 1:], idx[:, 1:]
    q = np.stack([a.ravel(), b.ravel(), c.ravel(), d.ravel()], 1)
    pole = len(V)
    V = np.vstack([V, sc.point(0.0, 90.0, 0.0)[None]])
    top = idx[:, -1]
    fan = np.stack([top, np.roll(top, -1), np.full(na, pole)], 1)
    return {"verts": V.astype(np.float32), "faces": np.concatenate([q[:, [0, 1, 2]], q[:, [0, 2, 3]], fan]).astype(np.int32)}


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
    body = {"object": "hair_collide"}

    def lens_stack(ph, amount, free):
        st = [[LENS, {"Amount": float(amount), "Tips": ph["tips"], "Roots": ph["roots"], "Flyaway": ph["flyaway"],
                      "Flyaway Distance": 1.0, "Edge": 0.8, "Clump": ph["clump"],
                      "Clump Shape": ph["clump_shape"], "Tip Spread": ph["tip_spread01"], "Wave": ph["wave"],
                      "Wavelength": ph["wavelength"], "Curl": ph["curl01"], "Loose": ph["wander"], "Wave Random": ph["wave_random"],
                      "Stray": ph["stray"], "Seed": int(seed)}]]
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
    from .hair import inside
    for k_ in hair_locks:  # locks rooted at the hairline: their strands start one by one over a longer stretch
        if not k_.get("free"):
            a0, e0_, h0 = sc.coords(np.asarray(k_["pts"][0], float)[None])
            k_["at_hairline"] = bool(h0[0] < 0.01 and inside(sc, line, a0, e0_)[0] < 0.008)
    sm = scalp_mesh(sc, g, line, S)
    area, e0 = sm.pop("area"), sm.pop("e0")
    np.savez(tmp / "strand_scalp.npz", **sm)
    np.savez(tmp / "strand_collide.npz", **collide_mesh(sc))
    G = lock_guides(hair_locks, sc.C, S, seed)
    ug = under_guides(sc, g, line, hair_locks, S, seed)
    ph = physical(S)
    n_under = 0.0
    if ug is not None:
        n_under = min(0.6 * ph["count"], float(S["under"]) * area * UNDER_PER_M2 * ph["count"] / 30000.0)
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
    out = {"scalp": str(tmp / "strand_scalp.npz"), "collide": str(tmp / "strand_collide.npz"), "groups": groups, "look": look, "physical": ph,
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


# ------------------------------------------------------------------------------------------------ evaluated strands

def evaluate(sd: dict, out: str | None = None, abc: str | None = None, usd: str | None = None) -> str:
    """Build a strands job in an empty Blender scene and dump every evaluated strand to `out` (npz: pts, counts,
    lock, sub, rand, radius, obj, names) and / or write the groom as Alembic / USD. Seconds; returns Blender's
    "@@" lines."""
    from .scene import _blender
    r = _blender({"mode": "hair_strands_eval", "strands": sd, "out": out, "abc": abc, "usd": usd}, timeout=1800)
    return "\n".join(ln for ln in r.splitlines() if ln.startswith("@@"))


def _cache() -> Path:
    from . import store
    d = store.HOME / "_cache" / "hair_strands"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _code() -> str:
    here = Path(__file__).parent
    return hashlib.sha1(b"".join((here / f).read_bytes() for f in ("hair_strands.py", "blender_strands.py"))).hexdigest()[:12]


def strands_of_model(sd: dict) -> dict:
    """The model's evaluated strands (cached on disk by the job's content + this code)."""
    f = _cache() / f"groom_{key(sd)}_{_code()}.npz"
    if not f.exists():
        evaluate(sd, out=str(f))
    return dict(np.load(f, allow_pickle=False))


TILE_LEN = 0.16  # m: a tile's strands run this far (a card stretches its picture along the lock)
TILE_KIND = {  # per atlas tile kind: strands at a 160 px tile, sub clumps, tips x, where roots start (0..1 of the length), guide length x
    # (upper layers' roots start one by one over the first quarter: a row of cards has no root edge; a baby tile is
    # a few thin hairs with empty margins: dense and parallel they filled their quad, a brown stamp on the skin)
    "dense": (260, 6, 0.5, 0.02, 1.0), "medium": (120, 4, 1.0, 0.25, 1.0), "sparse": (44, 3, 1.4, 0.3, 1.0),
    "fly": (18, 1, 1.0, 0.03, 1.0), "baby": (16, 1, 1.6, 0.45, 0.85), "hairline": (330, 6, 0.5, 0.34, 1.0),
}


def tile_job(S: dict, tmp: Path, seed: int = 11) -> dict:
    """The atlas's clump variants as a strands job: one flat straight guide lock a tile (dense .. sparse, fly-away,
    baby, hairline), its strands made by the same lens group and deformers as the head's, with the groom's numbers."""
    n = 24
    kinds = [(i, k, w) for i, (k, w) in enumerate(hc.TILES) if k in TILE_KIND]
    ph = physical(S, free=True)
    P, Sd, O, N, K, RS, TS, FD, LK = ([] for _ in range(9))
    for i, kind, w in kinds:
        cnt, clumps, ts, start, ln = TILE_KIND[kind]
        width = TILE_LEN * w / 1024.0
        y = -np.linspace(0, TILE_LEN * ln, n)
        P.append(np.stack([np.full(n, i * 0.2), y, np.zeros(n)], 1))
        Sd.append(np.tile([(0.3 if kind in ("fly", "baby") else 0.46) * width, 0.0, 0.0], (n, 1)))
        O.append(np.tile([0.0, 0.0, 0.002], (n, 1)))
        N.append(max(1, int(round(cnt * w / 160 / 8.0))))
        K.append(clumps)
        RS.append(start)
        TS.append(ts)
        FD.append(0.3 * width)
        LK.append(i)
    np.savez(tmp / "hair_tiles.npz", counts=np.full(len(kinds), n, np.int32), pts=np.concatenate(P).astype(np.float32),
             side=np.concatenate(Sd).astype(np.float32), out=np.concatenate(O).astype(np.float32),
             n=np.asarray(N, np.int32), k=np.asarray(K, np.int32), rs=np.asarray(RS, np.float32),
             ts=np.asarray(TS, np.float32), fd=np.asarray(FD, np.float32), lock=np.asarray(LK, np.int32),
             ws=np.ones(len(kinds), np.float32), wl=np.ones(len(kinds), np.float32),
             names=np.asarray([k for _, k, _ in kinds]))
    tips = 0.25 + 0.75 * float(np.clip(S["tips"], 0, 1))
    st = [[LENS, {"Amount": 8.0, "Tips": tips, "Roots": 1.0, "Flyaway": 0.0, "Flyaway Distance": 1.0, "Edge": 1.0,
                  "Clump": ph["clump"], "Clump Shape": ph["clump_shape"], "Tip Spread": ph["tip_spread01"],
                  "Wave": float(min(0.12 * ph["wave"], 0.0012)), "Wavelength": ph["wavelength"], "Curl": 0.0,
                  "Loose": ph["wander"], "Wave Random": 0.15, "Stray": ph["stray"],
                  "Seed": int(seed)}]]
    if ph["loose"] > 0:
        st.append(["Hair Curves Noise", {"Cumulative Offset": False, "Factor": 1.0, "Distance": 0.5 * ph["loose"],
                                         "Shape": 0.5, "Scale": ph["loose_scale"], "Scale along Curve": 0.35,
                                         "Offset per Curve": 0.15, "Seed": int(seed), "Preserve Length": True}])
    if ph["frizz"] > 0:
        st.append(["Frizz Hair Curves", {"Cumulative Offset": False, "Factor": 1.0, "Distance": ph["frizz"],
                                         "Shape": 0.5, "Seed": int(seed), "Preserve Length": True}])
    return {"groups": [{"name": "hair_tiles", "guides": str(tmp / "hair_tiles.npz"), "stack": st}], "look": {}}


def tile_lines(S: dict) -> dict:
    """{tile index: [(x across 0..1, v along 0..1, depth 0..1, id 0..1), ...]}: the strands of each atlas tile,
    evaluated by Blender from `tile_job` (cached by the strand numbers that shape them)."""
    import tempfile
    kk = hashlib.sha1(json.dumps([{k: S[k] for k in ("clump", "clump_shape", "tip_spread", "frizz", "loose", "tips",
                                                     "wave", "wavelength", "curl", "random", "stray")}, TILE_KIND, hc.TILES, TILE_LEN],
                                 sort_keys=True, default=float).encode()).hexdigest()[:16]
    f = _cache() / f"tiles_{kk}_{_code()}.npz"
    if not f.exists():
        with tempfile.TemporaryDirectory(prefix="hifipushie-tiles-") as tmp:
            evaluate(tile_job(S, Path(tmp)), out=str(f))
    z = np.load(f, allow_pickle=False)
    first = np.r_[0, np.cumsum(z["counts"])]
    out: dict = {}
    for j in range(len(z["counts"])):
        i = int(z["lock"][j])
        w = hc.TILES[i][1]
        width = TILE_LEN * w / 1024.0
        q = z["pts"][first[j]:first[j + 1]]
        if len(q) < 2:
            continue
        out.setdefault(i, []).append(((q[:, 0] - i * 0.2) / width + 0.5, -q[:, 1] / TILE_LEN,
                                      float(np.clip(0.5 + q[:, 2].mean() / 0.006, 0, 1)), float(z["rand"][j])))
    return out


def cap_chart(sc, g: dict, line, S: dict, D: dict | None, e0: float, size: int = 1024) -> dict:
    """The scalp's hair as a picture on the scalp chart (u = azimuth / 360, v = elevation over e0..90, row 0 = the
    top): every strand that runs close over the scalp drawn where it lies, over an opaque base that starts `soft` m
    inside the hairline. So the hairline is an alpha edge of single hairs, and no skin shows under the cards: the
    game hair's cap texture. {"alpha", "id", "depth"} (size, size)."""
    from PIL import Image, ImageDraw
    from .hair import _part, inside
    W = H = int(size)
    ss = 2
    ims = [Image.new("L", (W * ss, H * ss), 0) for _ in range(2)]
    da, di = (ImageDraw.Draw(i) for i in ims)
    if D is not None and len(D["counts"]):
        first = np.r_[0, np.cumsum(D["counts"])]
        az, el, hh = sc.coords(D["pts"])
        names = [str(n) for n in D["names"]]
        free = names.index("hair_guides_free") if "hair_guides_free" in names else -1
        for j in range(len(D["counts"])):
            if D["obj"][j] == free:
                continue
            sl = slice(first[j], first[j + 1])
            a, e, h_ = az[sl], el[sl], hh[sl]
            ok = (h_ < 0.012) & (e < 78.0)  # (round the pole the chart stretches a strand into an arc)
            if ok.sum() < 2:
                continue
            a = np.unwrap(np.radians(a)) * 180 / np.pi
            for shift in (0.0, -360.0, 360.0):  # (a strand across the seam is drawn on both edges)
                u = (a + shift) / 360.0 * W * ss
                if u.max() < 0 or u.min() > W * ss:
                    continue
                v = (1 - (e - e0) / (90.0 - e0)) * H * ss
                pts = [(float(x), float(y)) for x, y, k_ in zip(u, v, ok) if k_]
                da.line(pts, fill=255, width=2)
                di.line(pts, fill=int(1 + 254 * float(D["rand"][j])), width=2)
    a_, idm = (np.asarray(i.resize((W, H), Image.BOX), np.float32) / 255 for i in ims)
    idm = np.clip(idm / np.maximum(a_, 1e-3), 0, 1)
    AA, EE = np.meshgrid((np.arange(W) + 0.5) / W * 360.0, 90.0 - (np.arange(H) + 0.5) / H * (90.0 - e0), indexing="xy")
    d_in = inside(sc, line, AA, EE)
    soft = max(float(S["soft"]), 0.001)
    rng = np.random.default_rng(5)
    streak = np.repeat(rng.uniform(0, 1, (1, W)), H, 0).astype(np.float32)
    base = _ss((d_in - 0.25 * soft) / soft)
    pw = float(g["parting"].get("width", 0.012))
    base = base * (1 - 0.8 * np.clip(_part(sc, g, AA, EE, 0.25 * pw), 0, 1))
    a_ = np.where(d_in > -0.004, a_, 0.0)
    from scipy import ndimage
    idm = np.where(a_ > 0.05, idm, 0.5 + 0.3 * (ndimage.gaussian_filter1d(streak, 2.0, axis=1, mode="wrap") - 0.5))
    # as deep as a dense card's strands, a little deeper between the drawn strands: the cap reads as the same hair
    dep = np.clip(0.45 + 0.35 * a_, 0, 1)
    return {"alpha": np.maximum(a_, base).astype(np.float32), "id": idm.astype(np.float32),
            "depth": dep.astype(np.float32)}
