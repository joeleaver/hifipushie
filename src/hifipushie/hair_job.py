"""The Blender job for hair: streams, the job, the card cap, baby locks, card allowance. Part of hair (hair.py has
the overview)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from . import hair
from . import store
from . import hair_head
from .hair import _unit, dirs
from .hair_groom import _line_at, _part, groom_params, hairline, inside, look_of, needs_body
from .hair_head import Scalp
from .hair_lockmesh import cap_mesh, lock_extents
from .hair_spec import hair_of, resolve

# ------------------------------------------------------------------------------------------------ Blender
def streams(sc: Scalp, g: dict, V) -> dict:
    """The underlayer's combed clumps, for the material: on short back and sides the hair runs back and down toward
    the nape, so flow lines are rays from a point under the nape; `hp_tangent` = that direction on the surface and
    `hp_across` = a sawtooth (-1..1) of the angle round the nape point, one tooth per clump (`clumps.width` m at the
    ear's distance, jittered): the lock shader then draws a dark parting at each tooth's edge and strand grooves
    across. (Geometric fill locks on the sides either broke the outline or read as scales and blotches.)"""
    cl = g.get("clumps") or {}
    width = float(cl.get("width", 0.024))
    N = sc.C + np.array([0.0, 0.06, -0.13])  # under the nape: where the back and sides converge
    axis = _unit(np.array([0.0, -0.9, 0.45]))  # from it toward the forehead
    Q = V - N
    t = _unit(Q - (Q @ axis)[:, None] * axis)
    e1 = _unit(np.cross(axis, [1.0, 0, 0]))
    e2 = np.cross(axis, e1)
    ang = np.arctan2(t @ e2, t @ e1)
    dist = np.linalg.norm(Q, axis=1)
    rng = np.random.default_rng(int(g.get("seed", 0)) + 7)
    k = np.arange(-400, 400)
    edges = np.cumsum(np.r_[0.0, (1 + 0.35 * rng.uniform(-1, 1, len(k) - 1))]) * (width / 0.13)
    edges = edges - edges[len(k) // 2]
    i = np.clip(np.searchsorted(edges, ang) - 1, 0, len(edges) - 2)
    frac = (ang - edges[i]) / (edges[i + 1] - edges[i])
    across = 2 * frac - 1
    n = _unit(V - sc.C)
    tan = -Q  # combed toward the nape point
    tan = _unit(tan - (tan * n).sum(1, keepdims=True) * n)
    del dist
    return {"across": across.astype(np.float32), "tangent": tan.astype(np.float32),
            "lock": (rng.uniform(0, 1, len(edges))[i]).astype(np.float32)}


def job(name: str, spec: dict | None = None, only=None, budget: int | None = None, cap_step: float = 1.0,
        count: int | None = None) -> dict:
    """What Blender needs to show the hair: the locks, the cap (or the mass), the material. `only`: lock names or
    fnmatch patterns ("sweep*") to show alone on the underlayer (finding which locks make a patch)."""
    from . import hair_cards_job
    spec = store.load(name) if spec is None else spec
    h = hair_of(spec)
    if not h:
        return {}
    sc = hair_head.scalp(name, spec)
    g = groom_params(spec)
    tmp = Path(tempfile.mkdtemp(prefix="hifipushie-hair-"))
    stage = h.get("stage", "locks")
    if isinstance(budget, str) and budget in hair.CARD_TIERS:
        cap_step = float(hair.CARD_TIERS[budget]["cap_step"])
    locks = [] if stage == "mass" else resolve(spec, sc)
    if isinstance(budget, str) and "cap_step" in hair.SHORT_TIERS.get(budget, {}) and g.get("loose") and locks:
        # a short cut's cap is a smooth dome under its picture: at the long tiers' step it took 4,400 of a main
        # tier's 8,000 triangles and left its cards 4 triangles each (shards poking out of a swim cap)
        ln_ = [float(np.linalg.norm(np.diff(np.asarray(k_["pts"], float), axis=0), axis=1).sum()) for k_ in locks]
        if float(np.mean(ln_)) < hair.MASS_MIN:
            cap_step = float(hair.SHORT_TIERS[budget]["cap_step"])
    if only:
        from fnmatch import fnmatch
        pats = [only] if isinstance(only, str) else list(only)
        locks = [lk for lk in locks if any(fnmatch(lk["name"], q) for q in pats)]
    far = isinstance(budget, str) and hair.CARD_TIERS.get(budget, {}).get("cap") == "mass"  # (a far tier's cap IS the
    # hair on the head: the groom's full volume, not the layer under its locks)
    V, F = cap_mesh(sc, g, float(h.get("cap", 0.002)), mass=True, sunk=stage != "mass" and not far, step=cap_step, ease=0.035 if far else 0.0,
                    extra=lock_extents(sc, locks) if (locks and h.get("filler")) else None)
    extra = {k: v for k, v in streams(sc, g, V).items() if k == "tangent"} if stage != "mass" else {}  # (the
    # sawtooth clumps on the underlayer aliased into jagged stripes: the strips carry the clumps now)
    if stage != "mass":  # the parting is a line of shadow: the underlayer there takes the gap colour
        va, ve, _ = sc.coords(V)
        pw = _part(sc, g, va, ve, 2 * float(g["parting"].get("width", 0.012)))
        extra["across"] = (0.45 + 0.55 * np.clip(pw * 1.5, 0, 1)).astype(np.float32)
    np.savez(tmp / "cap.npz", verts=V, faces=F, **extra)
    out = {"locks": locks, "cap": str(tmp / "cap.npz"),
           "cap_kind": "mass" if stage == "mass" else "under", "look": look_of(spec, h),
           "centre": sc.C.tolist()}
    if h.get("style") == "cards" and stage != "mass":
        from . import hair_loose_body
        body = hair_loose_body.collider(name, spec, sc)
        colc = body if g.get("loose") else None
        out["cards"] = hair_cards_job.cards_job(sc, g, spec, locks, tmp, V, F, budget=budget, cap_step=cap_step, col=colc,
                                 clear_col=body)
    if h.get("style") == "strands" and stage != "mass":
        from . import hair_strands_job
        col = None
        if g.get("loose") or needs_body(g):
            from . import hair_loose_body
            col = hair_loose_body.collider(name, spec, sc)
        out["strands"] = hair_strands_job.job(sc, g, spec, locks, tmp, count=count, col=col)
    return out


def card_cap(sc: Scalp, g: dict, S: dict, tiles: list, V, F, e0: float | None = None) -> dict:
    """The underlayer as a card mesh: it wears a dense strand tile whose ragged end lies along the hairline, so the
    hair's edge on the skin breaks up into strands over `strands.soft` m instead of ending on a line."""
    line = hairline(sc, g)
    az, el, _ = sc.coords(V)
    d_in = inside(sc, line, az, el)
    t = next(t for t in tiles if t["kind"] == "hairline")
    x = np.radians(az) * 0.09 / 0.03
    tan = streams(sc, g, V)["tangent"]
    tie = g.get("tie")
    if tie:  # tied hair runs to the tie: the cap's strands converge there (round the nearest tie's own direction)
        from . import hair_tied
        D = _unit(np.asarray(V, float) - sc.C)
        best = np.full(len(V), -2.0)
        for tp in hair_tied.params(tie):
            ax = dirs(*tp["at"])
            e1 = _unit(np.cross(ax, [0.0, 0.0, 1.0]))
            e2 = np.cross(ax, e1)
            c = D @ ax
            xa = np.arctan2(D @ e2, D @ e1) * 0.09 / 0.03
            toward = _unit(ax[None] - c[:, None] * D)
            x = np.where(c > best, xa, x)
            tan = np.where((c > best)[:, None], toward, tan)
            best = np.maximum(best, c)
    tri = np.abs((x % 2.0) - 1.0)
    # the tile's first 45% (single roots, then more, then the opaque base) laid over 3 x soft from the line in
    vt = 0.45 * np.clip(d_in / max(3 * float(S["soft"]), 1e-4), 0, 1)
    uv = np.stack([t["u0"] + (t["u1"] - t["u0"]) * tri, 1 - vt], 1)
    F = np.asarray(F)
    tris = np.concatenate([F[:, [0, 1, 2]], F[:, [0, 2, 3]]])
    chart = next((t_ for t_ in tiles if t_["kind"] == "cap"), None)
    if chart is not None and e0 is not None:  # the cap wears the scalp chart: its own hair, drawn where it lies
        u = (az % 360) / 360.0
        vv = np.clip((el - e0) / (90.0 - e0), 0.0, 1.0)
        V, tan = np.asarray(V, float), np.asarray(tan, float)
        wrap = np.ptp(u[tris], axis=1) > 0.5  # faces across the azimuth seam: their low-u corners get u + 1
        if wrap.any():
            lo = np.unique(tris[wrap][u[tris[wrap]] < 0.5])
            new = len(V) + np.arange(len(lo))
            remap = np.arange(len(V))
            remap[lo] = new
            tw_ = tris[wrap]
            tris[wrap] = np.where(u[tw_] < 0.5, remap[tw_], tw_)
            V, tan = np.vstack([V, V[lo]]), np.vstack([tan, tan[lo]])
            u, vv = np.r_[u, u[lo] + 1.0], np.r_[vv, vv[lo]]
            az, el = np.r_[az, az[lo]], np.r_[el, el[lo]]
        uv = np.stack([chart["u0"] + (chart["u1"] - chart["u0"]) * np.clip(u, 0.0, 1.0), vv], 1)
    n = len(V)
    return {"verts": np.asarray(V, np.float32), "tris": tris.astype(np.int32), "uv": uv.astype(np.float32),
            "normal": sc.normal(az, el).astype(np.float32), "tangent": np.asarray(tan, np.float32),
            "col": np.full((n, 3), 0.9, np.float32), "along": np.full(n, 0.5, np.float32),
            "layer": np.full(n, -1.0, np.float32), "card": np.zeros(n, np.int32)}


def baby_locks(sc: Scalp, g: dict, S: dict, seed: int = 0) -> list:
    """Baby hairs: short fine locks rooted just inside the hairline all the way round, lying on the skin at every
    angle from along the line to straight out over it (resolved locks, for hair_cards)."""
    n_cm = float(S.get("baby", 0.0))
    if n_cm <= 0:
        return []
    line = hairline(sc, g)
    rng = np.random.default_rng(seed + 31)
    a = np.arange(0.0, 360.0, 0.5)
    L = sc.point(a, _line_at(line, a), 0.0)
    seg = np.linalg.norm(np.diff(L, axis=0, append=L[:1]), axis=1)
    cum = np.r_[0.0, np.cumsum(seg)]
    out = []
    for k, d in enumerate(np.arange(0.0, cum[-1], 0.025 / n_cm)):  # (the soft line itself is painted in the cap's
        # chart: cards only add stray hairs over it; one a cm overlapped into smudges)
        az = float(np.interp(d + rng.uniform(-0.3, 0.3) * 0.01 / n_cm, cum, np.r_[a, 360.0])) % 360
        el = float(_line_at(line, az))
        r = float(sc.r(az, el))
        de, da = np.degrees(0.002 / r), np.degrees(0.002 / max(r * np.cos(np.radians(el)), 0.02))
        gn = float(inside(sc, line, az, el + de) - inside(sc, line, az, el - de))  # which way is into the hair
        ge = float(inside(sc, line, az + da, el) - inside(sc, line, az - da, el))
        # most lie back into the hair (they soften the edge), a quarter stray out over the skin
        stray = rng.uniform() < 0.25
        th = np.arctan2(ge, gn) + (np.pi + rng.uniform(-1.0, 1.0) if stray else rng.normal(0, 0.8))
        ln = rng.uniform(0.008, 0.016) if stray else rng.uniform(0.015, 0.035)
        pts = []
        for f in (-0.12, 0.3, 0.65, 1.0):
            e2 = el + np.degrees(np.cos(th) * ln * f / r) + de * 1.5
            a2 = az + np.degrees(np.sin(th) * ln * f / max(r * np.cos(np.radians(el)), 0.02))
            pts.append(sc.point(a2, e2, 0.0012 + 0.002 * max(f, 0.0)))
        out.append({"name": f"baby{k}", "pts": np.asarray(pts).tolist(), "handles": None, "radius": None, "tilt": None,
                    "inputs": {"Width": rng.uniform(0.012, 0.02), "Thickness": 0.001, "Cup": 0.0, "Taper": 0.3,
                               "Belly": 0.3, "Root": 0.8, "Twist": 0.0, "Flip": 0.0},
                    "strands": {"layers": 1, "flyaway": 0.0, "wave": 0.0}, "free": 0.0, "core": None, "kind": "baby"})
    return out


def _hcap_vm():
    from . import hair_cap as hcap_
    return hcap_.VALUE_MAP


def tier_settings(tier: str, short: bool = False, even: bool = False) -> dict:
    """A card tier's settings: CARD_TIERS, a short cut's SHORT_TIERS over them; an EVEN groom (strands.even) is cut by
    visual clumps at every tier: it has no per-lock guide strands, so clump_cards found none (c2: Garrett's main 57
    cards, npc / far 0, the lifted cap alone stood as a pompadour). hair_clumps_cut.cut scales its cards with the triangles."""
    t = {**hair.CARD_TIERS[tier], **(hair.SHORT_TIERS[tier] if short else {})}
    if even and hair.EVEN_CLUMPS:
        t["cut"] = "clumps"
    return t


def tier_drawn_max(tier: str, own: dict | None = None) -> int:
    """The most DRAWN triangles a card tier may export: hair.export.tier_drawn_max {tier: n}, else the range maximum of
    budgets.json's hair_cards for the tier's role (TIER_ROLE)."""
    from . import budgets
    if own and tier in own:
        return int(own[tier])
    return int(budgets.role(hair.TIER_ROLE[tier])["parts"]["hair_cards"]["range"][1])


def card_allowance(budget: int, cap: int, other: int, back_faces: bool | None = None,
                   drawn_max: int | None = None) -> tuple[int, int, int]:
    """The cards' own (single-sided) triangles for a tier. (c13, coordinator 2026-10-19) `budget` (the role's hair_cards
    DEFAULT at the tier's LOD, tier_triangles) counts CARD FACES, one side: cap + other + cards <= budget; and the DRAWN
    triangles (with BACK_FACES every triangle but the cap's is exported twice: cards, baby hairs, tie, core) stay within
    `drawn_max` (tier_drawn_max): cap + factor x (other + cards) <= drawn_max. drawn_max None: the c10/c11 rule (the
    budget itself counts drawn triangles). Returns (drawn factor, the fixed parts' drawn triangles, the cards' allowance)."""
    from . import hair
    bf = 2 if (hair.BACK_FACES if back_faces is None else back_faces) else 1
    fixed = int(cap) + bf * int(other)
    if drawn_max is None:
        return bf, fixed, max((int(budget) - fixed) // bf, 200)
    faces = int(budget) - int(cap) - int(other)
    drawn = (int(drawn_max) - fixed) // bf
    return bf, fixed, max(min(faces, drawn), 200)
