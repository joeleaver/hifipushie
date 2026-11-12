"""Cards from locks: the spine, frames, a lock's cards, and `mesh`. Part of hair cards (hair_cards.py has the overview)."""
from __future__ import annotations

import hashlib

import numpy as np

from . import hair_cards
from .hair_cards import _ss, _unit
from .hair_cards_budget import _segments

# ------------------------------------------------------------------------------------------------ cards from locks
def spine(lk: dict, n: int = 64):
    """A resolved lock's spine as Blender draws it, evenly by arc length: points (n, 3), radius, tilt, the lock's
    own parameter u (0 root .. 1 tip) and arc length s (m). Free handles are honoured; auto ones are Catmull-Rom's."""
    P = np.asarray(lk["pts"], float)
    H = lk.get("handles") or [None] * len(P)
    rad = np.asarray(lk.get("radius") or [1.0] * len(P), float)
    tilt = np.asarray(lk.get("tilt") or [0.0] * len(P), float)
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out, par = [], []
    t = np.linspace(0, 1, 12, endpoint=False)[:, None]
    for i in range(len(P) - 1):
        p0, p3 = P[i], P[i + 1]
        p1 = np.asarray(H[i][3:], float) if H[i] else p0 + (Q[i + 2] - Q[i]) / 6
        p2 = np.asarray(H[i + 1][:3], float) if H[i + 1] else p3 - (Q[i + 3] - Q[i + 1]) / 6
        out.append((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)
        par.append(i + t[:, 0])
    C = np.vstack(out + [P[-1:]])
    par = np.concatenate(par + [[len(P) - 1.0]])
    s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]
    si = np.linspace(0, s[-1], n)
    Pn = np.stack([np.interp(si, s, C[:, k]) for k in range(3)], 1)
    pi = np.interp(si, s, par)
    k = np.arange(len(P))
    return Pn, np.interp(pi, k, rad), np.interp(pi, k, tilt), si / max(s[-1], 1e-9), si


def frames(P, C, ang, core=None):
    """Per spine point: tangent T, the lock's outward normal N (away from the head centre C, or from the nearest point
    of `core`, a polyline: a tail's own axis) turned by `ang` (radians) about T, and B = T x N (across the lock).
    Where "outward" runs along the lock (a tail leaving the head), the frame is carried on from the point before."""
    T = _unit(np.gradient(P, axis=0))
    if core is not None and len(core) >= 2:
        K = np.asarray(core, float)
        a, b = K[:-1], K[1:]
        ab = b - a
        tt = np.clip(((P[:, None] - a[None]) * ab[None]).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-12)[None], 0, 1)
        near = a[None] + tt[..., None] * ab[None]
        d = np.linalg.norm(P[:, None] - near, axis=-1)
        cen = near[np.arange(len(P)), d.argmin(1)]
    else:
        cen = np.asarray(C, float)[None]
    out = _unit(P - cen)
    perp = out - (out * T).sum(-1, keepdims=True) * T
    N = np.zeros_like(P)
    prev = None
    for i in range(len(P)):
        v = perp[i]
        if prev is not None:
            pt = prev - (prev @ T[i]) * T[i]
            v = v + 0.25 * pt / max(np.linalg.norm(pt), 1e-9)
        if np.linalg.norm(v) < 1e-6:
            v = np.cross(T[i], [1.0, 0, 0]) if abs(T[i][0]) < 0.9 else np.cross(T[i], [0, 1.0, 0])
        N[i] = v / np.linalg.norm(v)
        prev = N[i]
    c, s = np.cos(ang)[:, None], np.sin(ang)[:, None]
    N = N * c + np.cross(T, N) * s
    return T, N, np.cross(T, N), cen


def _lock_cards(lk: dict, C, S: dict, rng, n: int = 72) -> list:
    """The cards of one resolved lock: each {"P" centre line, "X" across (unit), "N" normal, "hw" half width, "u"
    the lock's parameter, "s" m along, "kind", "layer", "bend" (the volume's outward direction there)}."""
    from .hair_spec import lock_width
    inp = lk["inputs"]
    S = {**S, **(lk.get("strands") or {})}
    P, rad, tilt, u, s = spine(lk, n)
    ang = np.radians(inp.get("Flip", 0.0) + inp.get("Twist", 0.0) * u) + tilt
    T, N, B, cen = frames(P, C, ang, lk.get("core"))
    W, th = float(inp["Width"]), float(inp["Thickness"])
    lw = np.clip(lock_width(inp, u) * rad, 0.0, 4.0)
    cw = float(np.clip(W * 0.62, 0.006, S["card_width"]))
    na = 1 if W <= cw * 1.15 else int(np.ceil(W / (cw * 0.72)))
    L = max(1, int(S["layers"]))
    R = float(S["random"])
    hw0 = cw / 2 * np.maximum(lw, 0.2) ** 0.6
    span = np.maximum(W / 2 * lw - 0.55 * hw0, 0.0)
    lam = max(float(S["wavelength"]), 0.01)
    phi0 = rng.uniform(0, 2 * np.pi)
    env = _ss(s / 0.03)
    free = float(lk.get("free", 0.0))
    out = []

    def card(x, yo, kind, layer, u0=0.0, u1=1.0, hw=None, drift=None, amp=1.0):
        a = 0.35 * x + rng.normal(0, 0.12)
        if layer > 0 and drift is None:  # upper cards lift off the ones under them by their own amount: depth
            yo = yo + th * R * rng.uniform(0.0, 1.2) * np.sin(np.pi * np.clip(u, 0, 1)) ** 0.8
        X = _unit(B * np.cos(a) - N * np.sin(a))
        Nc = np.cross(X, T)
        # a lock lying on the head is held by the hair round it: it waves a little, in its own plane; free hair
        # swings fully and (curl) leaves its plane
        A = float(S["wave"]) * amp * (1 + R * rng.uniform(-0.5, 0.5)) * (0.3 + 0.7 * free)
        th_ = 2 * np.pi * s / lam + phi0 + R * rng.uniform(-1.2, 1.2)
        swing = A * env * np.sin(th_)
        lift = A * env * float(S["curl"]) * np.cos(th_) * free
        Pc = P + B * (x * span + swing)[:, None] + N * (yo + lift - inp.get("Cup", 0.0) * x * x)[:, None]
        if drift is not None:
            Pc = Pc + drift
        sel = (u >= u0 - 1e-9) & (u <= u1 + 1e-9)
        if sel.sum() < 3:
            return
        h = (hw0 if hw is None else np.full(len(u), hw))[sel]
        out.append({"P": Pc[sel], "X": X[sel], "N": Nc[sel], "hw": h, "u": u[sel], "s": s[sel], "kind": kind,
                    "prio": layer + 0.45 * min(abs(float(x)), 1.0) + (0.0 if free < 0.5 or W >= 0.016 else 0.3),
                    "cval": 1 + R * rng.uniform(-0.28, 0.28),
                    "layer": layer, "bend": _unit(P[sel] - (cen[sel] if len(cen) > 1 else cen[0])), "T": T[sel]})

    edge = bool(lk.get("at_hairline"))
    for la in range(L):
        kind = ("hairline" if edge else "dense") if la == 0 else ("medium" if la == 1 else "sparse")
        if free > 0.5:  # hair off the head has nothing to hide under it: no opaque base (a solid ribbon), and a
            kind = "sparse" if (W < 0.016 or la >= 2) else "medium"  # wisp is a few strands
            if L == 1 and W >= 0.016:  # (the far tier: one card a lock has to be the lock)
                kind = "dense"
        nl = na if la == 0 else max(1, na - (la % 2))
        for j in range(nl):
            x = ((j + 0.5 + R * rng.uniform(-0.25, 0.25)) / nl - 0.5) * 2 if nl > 1 else R * rng.uniform(-0.3, 0.3)
            yo = th * (-0.15 + 0.6 * la / max(L - 1, 1)) + th * rng.uniform(-0.05, 0.05)
            k2 = kind if (L > 1 or j % 2 == 0 or edge) else "medium"
            u1 = 1.0 - S["tips"] * R * rng.uniform(0.0, 0.22) if la > 0 else 1.0
            u0 = R * rng.uniform(0.0, 0.3) if la > 0 else 0.0  # (their roots staggered up the lock)
            if edge and la > 0:  # the line stays the thin layer's: upper cards start behind it
                u0 = max(u0, min(0.3, 0.02 / max(s[-1], 1e-6)))
            card(x, yo, k2, la, u0, u1)
    nf = rng.poisson(float(S["flyaway"]) * na * L)
    for _ in range(int(nf)):
        u0 = rng.uniform(0.0, 0.5)
        u1 = min(1.0, u0 + rng.uniform(0.3, 0.7))
        g = _ss((u - u0) / max(u1 - u0, 1e-6)) ** 1.5
        d = rng.normal(0, 1) * B + abs(rng.normal(0.6, 0.6)) * N
        drift = g[:, None] * d * rng.uniform(0.004, 0.018 + 0.03 * free)
        card(rng.uniform(-1.1, 1.1), th * rng.uniform(0.5, 1.3), "fly", L, u0, u1, hw=rng.uniform(0.005, 0.009),
             drift=drift, amp=1.4)
    return out


def _resample(c: dict, m: int) -> dict:
    """A card at m rows (evenly along it)."""
    s = c["s"]
    si = np.linspace(s[0], s[-1], m)
    o = dict(c)
    for k in ("P", "X", "N", "bend", "T"):
        o[k] = np.stack([np.interp(si, s, c[k][:, j]) for j in range(3)], 1)
    for k in ("hw", "u", "rad"):
        if k in c and np.ndim(c[k]):
            o[k] = np.interp(si, s, c[k])
    o["s"] = si
    return o


def mesh(cards: list, S: dict, look: dict, tiles: list, segment: float | None = None, seed: int = 0) -> dict:
    """Cards -> one triangle mesh: verts, tris, uv per vertex (Blender's way up: v = 1 at the root), normal (bent
    toward the volume's), tangent (along the hair), col (rgb multiplier: root to tip, a value per lock, lower layers
    darker; a = 1), plus per-vertex along / card / layer."""
    rng = np.random.default_rng(seed + 5)
    seg = float(segment or S["segment"])
    by = {}
    for i, t in enumerate(tiles):
        by.setdefault(t["kind"], []).append(i)
    V, F, UV, Nn, Tn, COL, AL, LAY, CID, BK = [], [], [], [], [], [], [], [], [], []
    off = 0
    rootd, rootl = (0.7 if S.get("short") else 0.62), (0.45 if S.get("short") else float(look.get("root", 0.12)))  # (a short cut's cards
    # root in the cap, which carries the shade: darkened roots were dark flakes on it)
    tip_amt = float(look.get("tip_amount", 0.0))
    rnd = float(S["round"])
    lam = max(float(S["wavelength"]), 0.01)
    for ci, c in enumerate(cards):
        length = float(c["s"][-1] - c["s"][0])
        per = seg if float(S["wave"]) <= 0 else min(seg, lam / 6)
        m = _segments(c, per) + 1
        hwm = float(np.max(c["hw"]))
        c = _resample(c, m)
        vv = (c["s"] - c["s"][0]) / max(length, 1e-9)
        left, right = c["P"] - c["X"] * c["hw"][:, None], c["P"] + c["X"] * c["hw"][:, None]
        V.append(np.stack([left, right], 1).reshape(-1, 3))
        if c.get("island") is not None:  # its own baked picture (hair_clumps_bake.bake): across = the clump's spread
            u0, u1, vt, vb = c["island"]
            fr = c["hw"] / max(2 * hwm, 1e-9)
            vi = vt - vv * (vt - vb)
            UV.append(np.stack([np.stack([u0 + (0.5 - fr) * (u1 - u0), vi], 1),
                                np.stack([u0 + (0.5 + fr) * (u1 - u0), vi], 1)], 1).reshape(-1, 2))
            BK.append(np.ones(2 * m, bool))
        else:
            t = tiles[by[c["kind"]][int(rng.integers(len(by[c["kind"]])))]]
            ua, ub = (t["u0"], t["u1"]) if rng.random() < 0.5 else (t["u1"], t["u0"])
            UV.append(np.stack([np.stack([np.full(m, ua), 1 - vv], 1), np.stack([np.full(m, ub), 1 - vv], 1)], 1).reshape(-1, 2))
            BK.append(np.zeros(2 * m, bool))
        nb = c["N"] * np.where((c["N"] * c["bend"]).sum(-1, keepdims=True) < 0, -1.0, 1.0)
        nb = _unit((1 - rnd) * nb + rnd * c["bend"])
        if hair_cards.EDGE_ROUND > 0 and np.ndim(c.get("rad")):
            # each edge its own normal: the volume's outward direction THERE (a card on a cylinder of radius R: n at the
            # edge = R n + / - hw X), so neighbouring cards shade as one rounded mass instead of flat planks, each with
            # its own tilt (lock-scale bands, a tail of flat sheets, dark wedges where a wide card's plane turns from the
            # light: g4_b19). Turned at most ~60 deg (R >= hw / 1.7)
            R_ = np.maximum(np.asarray(c["rad"], float), c["hw"] / 1.7)
            k_ = (hair_cards.EDGE_ROUND * c["hw"] / np.maximum(R_, 1e-6))[:, None]
            Nn.append(np.stack([_unit(nb - c["X"] * k_), _unit(nb + c["X"] * k_)], 1).reshape(-1, 3))
        else:
            Nn.append(np.repeat(nb, 2, 0))
        Tn.append(np.repeat(c["T"], 2, 0))
        ramp = rootd + (1 - rootd) * _ss(c["u"] / max(rootl, 1e-3))
        ramp = ramp * (1 + tip_amt * 0.35 * _ss((c["u"] - 0.55) / 0.45))
        lay = 1.0  # (lower layers were darkened here AND by the atlas's depth: a dark band wherever layer 0 showed)
        if S.get("colour_model", True) and not S.get("short"):
            # the look's colour model on the cards (tesshair7; hair_colour): each card is a ribbon: its lock's drift
            # and depth, lighter with the hair's age along it, a share of cards highlight ribbons. Stored / peak (a
            # vertex colour cannot brighten); the atlas is lifted by the same peak (atlas colour x col = the tone)
            from . import hair_colour as hcol
            import re as _re
            nm = str(c.get("lock", ""))
            hsh_ = int(hashlib.md5(nm.encode()).hexdigest()[:8], 16)
            age = (c["s"] - c["s"][0]) + (hcol.TAIL_AGE if _re.fullmatch(r"t\d*[ty]\d+", nm) else 0.0)
            # a highlight is a RIBBON of a few mm: on a card wider than HIGHLIGHT_W the whole card lit up, a pale
            # rectangle (Tess's tail at the 'lock' cut: a patchwork of light and dark blocks)
            hl_ = ((hsh_ // 1000 + ci * 7919) % 1000) / 999.0 + 1e-4 if 2 * float(np.median(c["hw"])) <= hair_cards.HIGHLIGHT_W else None
            tone = hcol.lock_tone(look, (hsh_ % 1000) / 999.0, float(c.get("shade", 0.0))) \
                * hcol.along_tone(look, age, hl_, float(c.get("sun", 0.0)))
            if c.get("island") is not None:  # its picture carries its strands' tone (hair_clumps_bake.strand_tones)
                tone = np.full(np.shape(age), float(c.get("tone_k", 1.0)))
            if c.get("fine"):  # rows the strands draw FINE (see-through, light against the sky: the outline): half the lift;
                # at full tone the sparse tile's hairs were a hard dark wire rim round the head (review c2)
                tone = tone * (1 + 0.3 * hcol._k(look, "fly_light", 0.3))
            if c.get("wisp") and c.get("island") is None:  # face-framing bundles read lighter (the strands' fly_light; Tess's are near blonde). Not
                # every fly card: the halo's and the hairline's lying on the head were pale strips across the sweep
                tone = tone * (1 + 0.6 * hcol._k(look, "fly_light", 0.3))
            ramp = ramp * tone / hcol.peak(look)
        COL.append(np.repeat(np.clip(ramp * lay * c.get("value", 1.0) * c.get("cval", 1.0), 0, 1)[:, None]
                             * np.ones(3)[None], 2, 0))
        AL.append(np.repeat(c["u"], 2))
        LAY.append(np.full(2 * m, c["layer"], np.float32))
        CID.append(np.full(2 * m, ci, np.int32))
        i = np.arange(m - 1) * 2 + off
        F.append(np.concatenate([np.stack([i, i + 1, i + 3], 1), np.stack([i, i + 3, i + 2], 1)]))
        off += 2 * m
    if not V:
        z = np.zeros((0, 3), np.float32)
        return {"verts": z, "tris": np.zeros((0, 3), np.int32), "uv": np.zeros((0, 2), np.float32), "normal": z,
                "tangent": z, "col": z, "along": np.zeros(0, np.float32), "layer": np.zeros(0, np.float32),
                "card": np.zeros(0, np.int32), "baked": np.zeros(0, bool)}
    Vv, Ff, Nv_ = np.concatenate(V).astype(np.float32), np.concatenate(F).astype(np.int32), np.concatenate(Nn).astype(np.float32)
    if hair_cards.TAIL_AXIS_N > 0:  # (round 42, opt-in) see TAIL_AXIS_N
        cid_ = np.concatenate(CID)
        tl_ = np.array([c.get("cls") == "tail" and not c.get("wisp") and not c.get("fly") for c in cards], bool)
        tv = tl_[cid_] if len(tl_) else np.zeros(len(Vv), bool)
        if tv.sum() > 20:
            zb = np.round(Vv[:, 2] / 0.01)
            outv = np.zeros_like(Nv_)
            for b in np.unique(zb[tv]):
                m_ = tv & (zb == b)
                d_ = Vv[m_] - Vv[m_].mean(0)
                d_[:, 2] = 0.0
                outv[m_] = d_ / np.maximum(np.linalg.norm(d_, axis=1, keepdims=True), 1e-9)
            k_ = float(hair_cards.TAIL_AXIS_N)
            Nv_[tv] = _unit((1 - k_) * Nv_[tv] + k_ * outv[tv]).astype(np.float32)
    if hair_cards.WIND_TO_NORMAL and len(Ff):  # (c4, Garrett) a triangle whose winding opposes its vertex normals shows its BACK
        # from outside: a double-sided renderer shades a back face with the flipped normal, lit from inside = black
        # (the c3 "dark card backs / shards" on the crown's outline: folds where a card turns over its root)
        fn = np.cross(Vv[Ff[:, 1]] - Vv[Ff[:, 0]], Vv[Ff[:, 2]] - Vv[Ff[:, 0]])
        bad = np.einsum("ij,ij->i", fn, Nv_[Ff].sum(1)) < 0
        Ff[bad] = Ff[bad][:, [0, 2, 1]]
    return {"verts": Vv, "tris": Ff,
            "uv": np.concatenate(UV).astype(np.float32), "normal": Nv_,
            "tangent": np.concatenate(Tn).astype(np.float32), "col": np.concatenate(COL).astype(np.float32),
            "along": np.concatenate(AL).astype(np.float32), "layer": np.concatenate(LAY),
            "card": np.concatenate(CID), "baked": np.concatenate(BK)}


def cards_of(locks: list, C, S: dict, look: dict | None = None) -> list:
    """Every resolved lock's cards (hair.resolve's list), each with its lock's name and value."""
    look = look or {}
    out = []
    vary = float(look.get("vary", 0.25))
    for lk in locks:
        seed = int(hashlib.md5(lk["name"].encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        val = 1 + vary * 0.8 * (rng.uniform() - 0.5)
        for c in _lock_cards(lk, C, S, rng):
            c["lock"], c["value"] = lk["name"], val
            out.append(c)
    return out
