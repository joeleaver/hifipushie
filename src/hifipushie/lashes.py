"""Eyelashes as geometry (eyedetail, 2026-10-09; the user, at Tess's front close-up: "We also just don't seem to have
the eye detail we need"): game-ready lash ribbons, upper and lower, rooted on the built head's lid margins.

How shipped game heads do it (MetaHuman, Unreal's Digital Human, most AAA heads): the lashes are their own mesh, a
few thousand triangles of thin strips rooted along the lid margin's front edge, bound to the lid so a blink carries
them, with a dark, slightly glossy material; the painted lash line on the skin is the roots' density under them.
Here each lash is one tapered ribbon (`segments` quads, flat side facing forward, its width along the lid), opaque:
no alpha atlas to sort or cut, sharp in close-ups, and at a distance the lashes' sub-pixel coverage reads as the
dark frame round the eye (what the photograph shows). ~1.5k triangles per eye at the defaults.

Anatomy (oculoplastic / trichology references): upper lashes 90-160 in 2-3 irregular rows, 8-12 mm long (longest
in the middle and outer third, short at the inner canthus), leaving the margin forward and a little down and curling
up; lower 70-80, 6-7 mm, finer and paler, angled down and out; none over the inner ~12% (the punctum, caruncle).
Lashes group in small clumps (their tips touch), cross a little, and the outer ones sweep outward.

The margin (`lid_lines`): the eye opening as seen along the head's forward axis is where the eyeball stands in front
of the skin (the skin runs on into the socket, there is no edge loop: base.eye_opening's method), traced round each
eye from its centre; the lash line is that rim, a little out onto the lid (the upper margin faces down, so from the
front its edge IS the lash line; the lower margin faces up, so its lash line lies ~0.5 mm below the visible rim).
Purely geometric: it follows any head (sliders, pose, identity) the field is built from.

spec["base"]["lashes"] = false | true | {"upper": {...}, "lower": {...}, "color", "roughness", "seed", "segments"};
per lid: "count", "length" (mm, the longest), "curl" (deg over the length), "lift" (deg at the root, + = away from
the eye's middle line), "flare" (deg the outer ones sweep outward), "thickness" (mm at the root), "clump" (0..1),
"offset" (mm out from the visible rim). Default ON for one-mesh human heads (base.body.source "human").
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

VERSION = 1
DEFAULTS = {
    "upper": {"count": 180, "length": 9.0, "curl": 68.0, "lift": -6.0, "flare": 22.0, "thickness": 0.14,
              "clump": 0.35, "offset": 0.15, "start": 0.1, "end": 1.0},
    "lower": {"count": 42, "length": 4.2, "curl": 14.0, "lift": 40.0, "flare": 14.0, "thickness": 0.05,
              "clump": 0.55, "offset": 0.5, "start": 0.22, "end": 0.97},
    "color": "#120e0c", "lower_color": "#3a302a", "roughness": 0.5, "seed": 0, "segments": 4,
}
_CACHE: dict = {}


def wanted(spec: dict) -> dict | None:
    """The lashes' settings if the spec's base head gets them, else None."""
    b = spec.get("base") or {}
    v = b.get("lashes")
    if v is False:
        return None
    if v is None:  # default: one-mesh humans
        if (b.get("body") or {}).get("source") != "human" or not b.get("head"):
            return None
        v = {}
    if v is True:
        v = {}
    bad = set(v) - set(DEFAULTS)
    if bad:
        from .spec import SpecError
        raise SpecError(f"base.lashes: unknown keys {sorted(bad)} (have {', '.join(DEFAULTS)})")
    out = {k: (dict(DEFAULTS[k], **(v.get(k) or {})) if isinstance(DEFAULTS[k], dict) else v.get(k, DEFAULTS[k]))
           for k in DEFAULTS}
    for lid in ("upper", "lower"):
        bad = set(v.get(lid) or {}) - set(DEFAULTS[lid])
        if bad:
            from .spec import SpecError
            raise SpecError(f"base.lashes.{lid}: unknown keys {sorted(bad)} (have {', '.join(DEFAULTS[lid])})")
    return out


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-15)


def _frame(head, c):
    fwd = _unit(np.asarray(head["forward"], float))
    up = np.array([0.0, 0.0, 1.0])
    up = _unit(up - (up @ fwd) * fwd)
    side = np.cross(up, fwd)  # with fwd = -y and up = z: side = +x (the subject's left)
    return fwd, up, side


def _dense(head, c, reach=0.026, per=10, seed=0):
    """Points sampled on the head's faces near the eye (vertices alone leave gaps the opening leaks through)."""
    W = np.asarray(head["verts"], float)
    F = head["faces"]
    near = np.linalg.norm(W - c, axis=1) < reach
    T = np.array([(f[0], f[j], f[j + 1]) for f in F if any(near[v] for v in f) for j in range(1, len(f) - 1)])
    rng = np.random.default_rng(seed)
    a, b = rng.random((2, per))
    sw = a + b > 1
    a[sw], b[sw] = 1 - a[sw], 1 - b[sw]
    A, B, C = W[T[:, 0]], W[T[:, 1]], W[T[:, 2]]
    P = A[:, None] + a[None, :, None] * (B - A)[:, None] + b[None, :, None] * (C - A)[:, None]
    return np.r_[P.reshape(-1, 3), W[np.unique(T)]]  # (faces' vertices only: no stray points)


def lid_lines(head: dict, cell: float = 0.0002, n: int = 360) -> list:
    """Per eye (head["eyes"] order): {"centre", "fwd", "up", "side", "inner" (unit, toward the nose), "rim": (n, 3)
    the opening's rim on the skin per angle, "theta", "rho" (m, in the front plane), "front" (the skin's depth
    there), "corners": (inner index, outer index)}."""
    from scipy import ndimage
    out = []
    r = float(head["eye_r"])
    for c in head["eyes"]:
        c = np.asarray(c, float)
        fwd, up, side = _frame(head, c)
        P = _dense(head, c)
        d = P - c
        u, v, depth = d @ side, d @ up, d @ fwd
        m = depth > -0.006
        nn = int(0.02 / cell)
        iu, iv = np.floor(u[m] / cell).astype(int) + nn, np.floor(v[m] / cell).astype(int) + nn
        ok = (iu >= 0) & (iu < 2 * nn) & (iv >= 0) & (iv < 2 * nn)
        front = np.full((2 * nn, 2 * nn), -9.0)
        np.maximum.at(front, (iu[ok], iv[ok]), depth[m][ok])
        front = ndimage.maximum_filter(front, size=3)
        g = (np.arange(2 * nn) - nn + 0.5) * cell
        q = r * r - g[:, None] ** 2 - g[None, :] ** 2
        ball = np.where(q > 0, np.sqrt(np.maximum(q, 0)), -np.inf)
        lab, _ = ndimage.label((ball > front) & (q > 0))
        seed_lab = lab[nn, nn]
        if seed_lab == 0:  # the opening needn't cover the ball's centre (a hooded or low-set lid): the component with
            # most cells near it
            near = (np.hypot(g[:, None], g[None, :]) < 0.5 * r) & (lab > 0)
            if not near.any():
                raise ValueError("lashes: no eye opening found (closed lids?)")
            seed_lab = np.bincount(lab[near]).argmax()
        op = lab == seed_lab
        ci, cj = np.nonzero(op)  # rays from the opening's own middle (the ball's centre can lie under a lid)
        oi, oj = float(ci.mean()), float(cj.mean())
        o2 = np.array([(oi - nn + 0.5) * cell, (oj - nn + 0.5) * cell])
        th = np.linspace(0, 2 * np.pi, n, endpoint=False)
        rho = np.zeros(n)
        steps = np.arange(0, 0.02, cell * 0.25)
        for k, t in enumerate(th):
            x = oi + np.cos(t) * steps / cell
            y = oj + np.sin(t) * steps / cell
            inside = op[np.clip(x.astype(int), 0, 2 * nn - 1), np.clip(y.astype(int), 0, 2 * nn - 1)]
            j = np.argmin(inside) if not inside.all() else len(steps) - 1
            rho[k] = steps[max(j - 1, 0)] + 0.5 * cell
        # smooth along the rim (grid steps), circularly
        rho = ndimage.gaussian_filter1d(rho, 2.0, mode="wrap")
        inner = -np.sign(c[0]) * side if abs(c[0]) > 1e-6 else side
        U = np.cos(th)[:, None] * side + np.sin(th)[:, None] * up
        out.append({"centre": c, "fwd": fwd, "up": up, "side": side, "inner": inner, "theta": th, "rho": rho,
                    "dirs": U, "front": front, "cell": cell, "nn": nn, "o2": o2,
                    "corners": (int(np.argmax((U * rho[:, None]) @ inner)), int(np.argmin((U * rho[:, None]) @ inner)))})
    return out


def _arc(L, lid):
    """Indices along one lid's rim, inner corner -> outer corner, through the top (upper) or bottom (lower)."""
    n = len(L["theta"])
    i0, i1 = L["corners"]
    a = [(i0 + k) % n for k in range((i1 - i0) % n + 1)]
    b = [(i0 - k) % n for k in range((i0 - i1) % n + 1)]
    va = np.mean([L["dirs"][i] @ L["up"] for i in a])
    up_arc, lo_arc = (a, b) if va > 0 else (b, a)
    return np.array(up_arc if lid == "upper" else lo_arc)


def _on_skin(L, P2):
    """2D front-plane points (m) -> the skin's 3D point there (the front-most skin in the cell)."""
    nn, cell = L["nn"], L["cell"]
    iu = np.clip(np.floor(P2[:, 0] / cell).astype(int) + nn, 0, 2 * nn - 1)
    iv = np.clip(np.floor(P2[:, 1] / cell).astype(int) + nn, 0, 2 * nn - 1)
    dep = L["front"][iu, iv]
    return L["centre"] + P2[:, :1] * L["side"] + P2[:, 1:] * L["up"] + dep[:, None] * L["fwd"]


def build(head: dict, cfg: dict, sides=(".L", ".R")) -> dict:
    """The lash ribbons for both eyes: {"verts", "tris", "normal", "uv" (along, across), "along" (0 root .. 1 tip),
    "root" (each vertex's root point), "lid" (0 upper, 1 lower), "eye" (0, 1), "col" (per-vertex colour)}."""
    rng = np.random.default_rng(int(cfg.get("seed", 0)))
    seg = int(cfg.get("segments", 4))
    V, T, Nn, UV, AL, RT, LID, EYE, COL = [], [], [], [], [], [], [], [], []
    lines = lid_lines(head)
    r_ball = float(head["eye_r"])
    tree = head["tree"]
    HN = np.asarray(head["normals"], float)
    HV = np.asarray(head["verts"], float)
    for ei, L in enumerate(lines):
        c = L["centre"]
        for li, lid in enumerate(("upper", "lower")):
            p = cfg[lid]
            col = np.array(_hex(cfg["color"] if lid == "upper" else cfg.get("lower_color", cfg["color"])))
            idx = _arc(L, lid)
            rim2 = L["o2"] + np.c_[(L["dirs"][idx] @ L["side"]) * L["rho"][idx], (L["dirs"][idx] @ L["up"]) * L["rho"][idx]]
            seglen = np.r_[0, np.cumsum(np.linalg.norm(np.diff(rim2, axis=0), axis=1))]
            s_all = seglen / seglen[-1]
            cnt = int(p["count"])
            s = np.sort(rng.uniform(p["start"], p["end"], cnt))
            s = np.clip(s + rng.normal(0, 0.004, cnt), 0, 1)
            # roots: the rim moved out onto the lid by `offset` (2D), a little scatter across the margin (rows)
            P2 = np.c_[np.interp(s, s_all, rim2[:, 0]), np.interp(s, s_all, rim2[:, 1])]
            out2 = (P2 - L["o2"]) / np.maximum(np.linalg.norm(P2 - L["o2"], axis=1, keepdims=True), 1e-9)
            rows = rng.normal(0.0, 0.12e-3, cnt)
            P2 = P2 + out2 * (p["offset"] * 1e-3 + np.abs(rows))[:, None]
            roots = _on_skin(L, P2) - (np.abs(rows) * 0.6)[:, None] * L["fwd"]  # back rows sit a little deeper
            # along the margin: the tangent; "out" = away from the opening in the front plane
            tan2 = np.c_[np.gradient(P2[:, 0]), np.gradient(P2[:, 1])]
            tan = _unit(tan2[:, :1] * L["side"] + tan2[:, 1:] * L["up"])
            outv = _unit(out2[:, :1] * L["side"] + out2[:, 1:] * L["up"])
            # length profile: short at the inner canthus, longest over the middle-outer third, a little shorter outside
            prof = (0.5 + 0.5 * np.clip((s - p["start"]) / 0.45, 0, 1) ** 0.8) * (1 - 0.25 * np.clip((s - 0.75) / 0.25, 0, 1) ** 2)
            length = p["length"] * 1e-3 * prof * rng.uniform(0.82, 1.08, cnt)
            lift = np.radians(p["lift"] + rng.normal(0, 5, cnt))
            curl = np.radians(p["curl"] * rng.uniform(0.75, 1.2, cnt))
            # the outer lashes sweep outward (toward the outer corner), the inner ones a little toward the nose
            sweep = np.radians(p["flare"] * np.clip((s - 0.35) / 0.65, -0.4, 1) + rng.normal(0, 4, cnt))
            outer = -L["inner"]
            t = np.linspace(0, 1, seg + 1)
            ang = lift[:, None] + curl[:, None] * t[None] ** 1.4  # (cnt, seg+1)
            # direction along the lash per sample, integrated (forward, curling out from the opening)
            D = np.cos(ang)[..., None] * L["fwd"] + np.sin(ang)[..., None] * outv[:, None, :]
            sw = np.tan(sweep)[:, None, None] * t[None, :, None] * (outer - (outer @ L["fwd"]) * L["fwd"])[None, None]
            D = _unit(D + sw)
            step = (length / seg)[:, None, None]
            Pp = roots[:, None, :] + np.concatenate([np.zeros((cnt, 1, 3)), np.cumsum(D[:, :-1] * step, axis=1)], 1)
            # clumps: groups of 2-4 neighbours whose tips draw together
            k = 0
            while k < cnt:
                g = int(rng.integers(2, 5))
                j = slice(k, min(k + g, cnt))
                tip = Pp[j, -1].mean(0)
                Pp[j] += float(p["clump"]) * (t[None, :, None] ** 2) * (tip - Pp[j, -1])[:, None, :]
                k += g
            # keep clear of the eyeball (+0.3 mm) and of the skin (each point at least 0.15 mm out along the skin's
            # normal at its nearest vertex)
            for _ in range(2):
                dc = Pp - c
                rr = np.linalg.norm(dc, axis=-1, keepdims=True)
                Pp = np.where(rr < r_ball + 3e-4, c + dc / rr * (r_ball + 3e-4), Pp)
                flat = Pp[:, 1:].reshape(-1, 3)
                _, ni = tree.query(flat)
                sd = ((flat - HV[ni]) * HN[ni]).sum(1)
                push = np.clip(1.5e-4 - sd, 0, 0.003)
                flat = flat + push[:, None] * HN[ni]
                Pp[:, 1:] = flat.reshape(cnt, seg, 3)
            # the ribbon: width along the lid (tangent made square to the lash), tapering to a fine tip
            Dl = np.gradient(Pp, axis=1)
            Dl = _unit(Dl)
            Wd = _unit(tan[:, None, :] - (Dl * tan[:, None, :]).sum(-1, keepdims=True) * Dl)
            wid = p["thickness"] * 1e-3 * (1 - 0.85 * t ** 1.5)
            A = Pp - 0.5 * wid[None, :, None] * Wd
            B = Pp + 0.5 * wid[None, :, None] * Wd
            Nr = _unit(np.cross(Wd, Dl))
            Nr = np.where(((Nr * L["fwd"]).sum(-1, keepdims=True) < 0), -Nr, Nr)
            base = sum(len(x) for x in V)
            V.append(np.stack([A, B], 2).reshape(-1, 3))  # per lash: seg+1 pairs
            Nn.append(np.repeat(Nr, 2, axis=1).reshape(-1, 3))
            UV.append(np.c_[np.repeat(np.repeat(t[None], cnt, 0), 2, 1).ravel(), np.tile([0.0, 1.0], cnt * (seg + 1))])
            AL.append(np.repeat(np.repeat(t[None], cnt, 0), 2, 1).ravel())
            RT.append(np.repeat(roots, 2 * (seg + 1), 0))
            LID.append(np.full(cnt * 2 * (seg + 1), li))
            EYE.append(np.full(cnt * 2 * (seg + 1), ei))
            COL.append(np.tile(col, (cnt * 2 * (seg + 1), 1)))
            per = 2 * (seg + 1)
            q = np.arange(seg)
            a0, b0, a1, b1 = 2 * q, 2 * q + 1, 2 * q + 2, 2 * q + 3
            quad = np.stack([np.c_[a0, b0, b1], np.c_[a0, b1, a1]], 1).reshape(-1, 3)
            T.append((base + np.arange(cnt)[:, None, None] * per + quad[None]).reshape(-1, 3))
    return {"verts": np.concatenate(V), "tris": np.concatenate(T).astype(np.int32), "normal": np.concatenate(Nn),
            "uv": np.concatenate(UV), "along": np.concatenate(AL), "root": np.concatenate(RT),
            "lid": np.concatenate(LID), "eye": np.concatenate(EYE), "col": np.concatenate(COL)}


def _hex(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def for_spec(spec: dict, cfg: dict | None = None) -> dict | None:
    """The lashes of a spec's base head (world space, as the field is built), cached by the head and settings."""
    from . import base as basemod
    from .spec import expand_mirror
    cfg = cfg or wanted(spec)
    if cfg is None:
        return None
    s = expand_mirror(spec)
    head = basemod.head_of(s, s["base"])
    if head is None:
        return None
    key = hashlib.sha1(json.dumps([cfg, VERSION], sort_keys=True).encode()
                       + np.round(np.asarray(head["verts"], float), 6).tobytes()).hexdigest()[:16]
    if key not in _CACHE:
        if len(_CACHE) > 4:
            _CACHE.pop(next(iter(_CACHE)))
        out = build(head, cfg)
        out["key"] = key
        _CACHE[key] = out
    return _CACHE[key]


def scene_job(name: str, spec: dict, cache_dir) -> dict | None:
    """The scene's lash object: the mesh written into the scene cache (content-named), and its material."""
    cfg = wanted(spec)
    if cfg is None:
        return None
    m = for_spec(spec, cfg)
    if m is None:
        return None
    f = cache_dir / f"lashes_{m['key']}.npz"
    if not f.exists():
        np.savez(f, **{k: v for k, v in m.items() if k != "key"})
    return {"key": m["key"], "npz": str(f), "roughness": float(cfg["roughness"]), "tris": int(len(m["tris"]))}
