"""The block-in's EYE step (blockin2, 2026-10-10; Joe: "we shouldn't really ever use our 'fix' [lidfold]. The fact that
it isn't there means we're not using GNM right"). GNM is built so the identity is the person's relaxed neutral and the
eye-region EXPRESSION is the lids' state; its lids have folds as identity + expression configurations (gnm_audit.md
finding 2, the audit's g11_crease_fit). So the eye step is one MAP solve over the identity (170) + GNM's symmetric
eye-region expression (left_k + right_k, k < NE), on the head as it ships (onemesh.head_template: the body's head, our
seated eyeball), driven by what the reference shows:
  - the lid margins against the iris (MediaPipe, iris radii: MRD1 / MRD2 style), sigma 0.05;
  - the visible fold line's height over the lash line (lidfold.read_lid's tps, mm at the iris' scale) against the
    model's visible platform (the pretarsal skin seen from the front below the fold), sigma 0.3 mm, and that a line IS
    there (the crease's local depth at least D_LINE) when the picture's line is dark;
  - the rest of the face held where the block-in put it (68 landmarks off the eyes, sigma 0.3 mm; brows 1 mm);
  - priors: |dc|^2 + |e|^2 (both unit variance).
No lidfold, no lid pose offsets: the result ships as base.head.identity + base.head.expression (eye-region pairs), the
lid pose (lid_upper / lid_lower) cleared.
"""
from __future__ import annotations

import copy

import numpy as np

NE = 20                 # symmetric eye-region expression pairs solved
SIG_LID = 0.05          # iris radii
SIG_TPS = 0.3           # mm
SIG_HOLD = 0.3          # mm (landmarks off the eyes); brows SIG_BROW
SIG_BROW = 1.0
D_LINE = 1.2            # mm: the crease's local depth when the picture shows a line (Tess: 0.7 solved to 0.74 and did not read dressed; 1.2 did)
SIG_LINE = 0.1
DARK_LINE = 0.15        # the picture's fold line darkness above which "a line is there"
HOODED_SHOW = 0.5       # mm: the visible platform when the picture shows no fold line (hooded: the fold covers it)
SIG_HOODED = 0.5
SOCKET = ("orbital_rim", "lower_orbit", "eye_depth")   # the socket's readings held (humanmacro, population sd, on the
SIG_SOCKET = 0.15       # mesh WITH the expression): unheld, lt19's fold came with orbital_rim +1.1 / lower_orbit -0.9 sd
HOLD = [i for i in range(68) if not (36 <= i < 48 or 17 <= i < 27)]
BROWS = list(range(17, 27))


def _names():
    from . import base as basemod
    n = [str(x) for x in basemod._gnm_data()["expression_names"]]
    return [f"left_eye_region_{k:03d}" for k in range(NE)], [f"right_eye_region_{k:03d}" for k in range(NE)], n


# ---- the model's readers (world frame: Z up, faces -Y) -----------------------------------------------------------

def _tris(faces):
    out = []
    for f in faces:
        for i in range(1, len(f) - 1):
            out.append((f[0], f[i], f[i + 1]))
    return np.asarray(out, int)


def _slice(V, F, x):
    s = V[:, 0] - x
    sf = s[F]
    pos = sf > 0
    cnt = pos.sum(1)
    sel = (cnt == 1) | (cnt == 2)
    Fs, ss = F[sel], sf[sel]
    segs = []
    for r in range(len(Fs)):
        pts = []
        for e0, e1 in ((0, 1), (1, 2), (2, 0)):
            a, b = ss[r, e0], ss[r, e1]
            if (a > 0) != (b > 0):
                t = a / (a - b)
                pts.append(V[Fs[r, e0]] + t * (V[Fs[r, e1]] - V[Fs[r, e0]]))
        if len(pts) == 2:
            segs.append(pts)
    return segs


def _chain(segs, tol=1e-7):
    from collections import defaultdict
    key = lambda p: tuple(np.round(p / tol).astype(np.int64))  # noqa: E731
    adj, pts = defaultdict(list), {}
    for a, b in segs:
        ka, kb = key(a), key(b)
        if ka == kb:
            continue
        adj[ka].append(kb)
        adj[kb].append(ka)
        pts[ka], pts[kb] = a, b
    seen, lines = set(), []
    for s in [k for k in adj if len(adj[k]) == 1] + list(adj):
        if s in seen:
            continue
        line, cur = [s], s
        seen.add(s)
        while True:
            nxt = [n for n in adj[cur] if n not in seen]
            if not nxt:
                break
            cur = nxt[0]
            seen.add(cur)
            line.append(cur)
        lines.append(np.array([pts[k] for k in line]))
    return lines


class Reader:
    """Lid margins vs our drawn iris, and the upper lid's sagittal profile (crease, visible platform), on head dicts
    from onemesh.head_template (the subject's LEFT eye, +x)."""

    def __init__(self, ht):
        from . import base as basemod
        g = basemod._gnm_data()
        V = np.asarray(ht["verts"], float)
        F = _tris(ht["faces"])
        # the head's rows are GNM's skin vertices in order (+ the lid loops appended): the margin = skin rows next to
        # the eye socket's lining (GNM's eye_sockets group), as the audit's Lids reader
        sk = np.flatnonzero(np.asarray(g["skin"]))
        sock = np.zeros(len(V), bool)
        sock[:len(sk)] = np.asarray(g["groups"]["eye_sockets"])[sk] > 0.5
        e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
        m = sock[e[:, 0]] != sock[e[:, 1]]
        ring = np.unique(np.where(sock[e[m, 0]], e[m, 1], e[m, 0]))
        c = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float)
        r = float(ht["eye_r"])
        self.ring = ring[np.linalg.norm(V[ring] - c, axis=1) < 2.0 * r]
        self.skin = ~sock
        F = F[np.all(self.skin[F], axis=1)]
        self.tri = F[np.all(np.linalg.norm(V[F] - c, axis=2) < 0.04, axis=1)]

    def read(self, ht):
        V = np.asarray(ht["verts"], float)
        c = np.asarray(max(ht["eyes"], key=lambda q: q[0]), float)
        r = float(ht["eye_r"])
        fwd = np.asarray(ht["forward"], float)
        up = np.array([0, 0, 1.0]) - fwd * fwd[2]
        up /= np.linalg.norm(up)
        lat = np.cross(up, fwd)
        ri = 0.51 * r * 0.985                     # the drawn iris (blockin.lid_model's)
        pole = c + r * fwd
        R = V[self.ring]
        x, z = (R - pole) @ lat, (R - pole) @ up
        near = np.abs(x) < 0.3 * ri
        out = {"r_iris_mm": ri * 1000}

        def at(sel):
            if not sel.any():
                return np.nan
            o = np.argsort(x[sel])
            return float(np.interp(0.0, x[sel][o], z[sel][o]))
        zm = 0.5 * (z.max() + z.min())   # the upper / lower lid split at the opening's middle (a lid may be past the pole)
        zu, zl = at(near & (z > zm)), at(near & (z < zm))
        out["up"], out["lo"] = zu / ri, -zl / ri
        # the upper lid's profile in the plane through the pupil (and +-4 mm): (forward, up), margin first
        res = []
        for dx in (-0.004, 0.0, 0.004):
            x0 = float(pole[0] + dx)
            best = None
            for L in _chain(_slice(V, self.tri, x0)):
                d = np.linalg.norm(L - c, axis=1)
                ok = (d > r + 0.0003) & ((L - c) @ up > -0.001) & ((L - c) @ fwd > 0) & ((L - c) @ up < 0.03)
                runs, cur = [], []
                for i, o in enumerate(ok):
                    if o:
                        cur.append(i)
                    elif cur:
                        runs.append(cur)
                        cur = []
                if cur:
                    runs.append(cur)
                for rr in runs:
                    if best is None or len(rr) > len(best[1]):
                        best = (L, rr)
            if best is None:
                continue
            L, rr = best
            P = np.c_[(L[rr] - c) @ fwd, (L[rr] - c) @ up]
            if P[0, 1] > P[-1, 1]:
                P = P[::-1]
            res.append(_profile(P))
        if res:
            mid = res[len(res) // 2]
            out.update(show=mid["show"], height=mid["height"], depth=float(np.mean([q["depth"] for q in res])),
                       local=float(np.mean([q["local"] for q in res])),
                       hsoft=float(np.nanmean([q["hsoft"] for q in res])), lsoft=float(np.mean([q["lsoft"] for q in res])),
                       drop=float(np.mean([q["drop"] for q in res])), vis=float(np.nanmean([q["vis"] for q in res])))
        else:
            out.update(show=np.nan, height=np.nan, depth=0.0, local=0.0, hsoft=np.nan, lsoft=0.0, drop=0.0, vis=np.nan)
        return out


def _profile(P, w_mm=2.5, lo=2.0, hi=12.0):
    """A lid profile (forward, up; m; margin first): the crease = the deepest narrow valley 2-12 mm over the margin
    (local depth inside the chord +-w), its height; the visible platform (front view) below the fold."""
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    s = np.arange(0, d[-1], 0.0001)
    Q = np.c_[np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])]
    k = int(round(w_mm / 0.1))
    n = len(Q)
    dep = np.full(n, np.nan)
    for i in range(k, n - k):
        a, b, p = Q[i - k], Q[i + k], Q[i]
        ab = b - a
        Ln = np.linalg.norm(ab)
        if Ln > 1e-9:
            nrm = np.array([ab[1], -ab[0]]) / Ln
            dep[i] = -((p - a) @ nrm)
    h = (Q[:, 1] - Q[0, 1]) * 1000
    # the hood: the fold hanging back DOWN over the platform (the profile drops below the height it had reached); the
    # visible platform ends at the overhang's lowest point (soft arg-max over the drop, tau 0.15 mm)
    drop = np.maximum.accumulate(h) - h
    wd = np.exp((drop - drop.max()) / 0.15)
    hood = (float(drop.max()), float((wd * h).sum() / wd.sum()))   # (its height blends in with the drop: see vis)
    ok = (h > lo) & (h < hi) & np.isfinite(dep)
    if not ok.any():
        return {"local": 0.0, "height": np.nan, "show": float(h.max()) if len(h) else np.nan, "depth": 0.0,
                "hsoft": np.nan, "lsoft": 0.0, "drop": hood[0], "vis": hood[1] if np.isfinite(hood[1]) else float(h.max())}
    # smooth reads for the solver (the arg-max and the visibility jump between valleys): the valley's height and depth as
    # a soft max over the local depth (tau 0.15 mm)
    dd, hh = dep[ok] * 1000, h[ok]
    wv = np.exp((dd - dd.max()) / 0.15)
    hsoft = float((wv * hh).sum() / wv.sum())
    lsoft = float(dd.max() + 0.15 * np.log(wv.mean()))
    i = np.flatnonzero(ok)[np.argmax(dep[ok])]
    above = Q[i:]
    below = Q[:i + 1]
    # visible from the front: a point below the crease shows unless a point of the fold above stands in front of it
    # at (about) the same height
    vis = [q for q in below[::5] if not np.any((np.abs(above[:, 1] - q[1]) < 0.0004) & (above[:, 0] > q[0] + 1e-4))]
    show = (max(q[1] for q in vis) - Q[0, 1]) * 1000 if vis else 0.0
    return {"local": float(dep[i] * 1000), "height": float(h[i]), "show": float(show), "depth": float(dep[i] * 1000),
            "hsoft": hsoft, "lsoft": lsoft, "drop": hood[0],
            # the visible platform: the crease's height without a hood, the overhang's lowest point with one (blended
            # over a 0.1 -> 0.6 mm drop: no jump for the solver)
            "vis": float(hsoft + np.clip((hood[0] - 0.1) / 0.5, 0, 1) * (hood[1] - hsoft))}


# ---- the picture's evidence ----------------------------------------------------------------------------------------

def photo_evidence(img, view: dict) -> dict:
    """{"up", "lo"} (iris radii, both eyes' mean), {"tps" (mm at the 11.7 mm iris), "dark"} (median over the middle
    columns of both eyes), from MediaPipe + lidfold.read_lid on the front picture."""
    from . import blockin as bi, lidfold
    lp = bi.lid_photo(img, view)
    if not lp:
        raise ValueError("eye step: the detector found no face (irises) on the front picture")
    P = np.asarray(bi.detect_view(img, view), float)
    cols = lidfold.read_lid(img, P)
    tps = [c["tps"] for e in cols for c in e if np.isfinite(c.get("tps", np.nan)) and c.get("dark", 0) >= DARK_LINE]
    dk = [c["dark"] for e in cols for c in e]
    hooded = len(tps) < 2   # no fold line in most columns: the fold hangs over the platform
    return {"up": float(np.mean([lp[s]["upper"] for s in lp])), "lo": float(np.mean([lp[s]["lower"] for s in lp])),
            "tps": float(np.median(tps)) if not hooded else HOODED_SHOW, "dark": float(np.median(dk)) if dk else 0.0,
            "hooded": hooded, "columns": cols}


def socket(c, expression: dict) -> dict:
    """The socket readings (SOCKET, humanmacro z-scores) of identity c with the head's expression applied: GNM's mesh
    (humanmacro.head) + the expression basis, so a lid tucked back by the eye-region expression counts."""
    from . import base as basemod, humanmacro as hm
    g = basemod._gnm_data()
    names = {str(n): i for i, n in enumerate(g["expression_names"])}
    V = hm.head(np.asarray(c, float))
    for k, v in (expression or {}).items():
        if v and k in names:
            if k not in _EB:
                B = np.asarray(g["expression_basis"][names[k]], float)
                _EB[k] = np.stack([B[..., 0], -B[..., 2], B[..., 1]], -1)   # (humanmacro's world frame)
            V = V + float(v) * _EB[k]
    z = hm.read(V=V)
    return {k: float(z[k]) for k in SOCKET}


_EB: dict = {}


# ---- the solve -----------------------------------------------------------------------------------------------------

def _head(base, c, e, Ln, Rn):
    from . import blockin as bi, onemesh
    b = copy.deepcopy(base)
    bi.set_identity({"base": b}, c)
    ex = {**{Ln[k]: round(float(e[k]), 6) for k in range(NE)}, **{Rn[k]: round(float(e[k]), 6) for k in range(NE)}}
    b["head"]["expression"] = {k: v for k, v in ex.items() if v}
    ht = onemesh.head_template(b)
    for kk in [k for k in onemesh._CACHE if isinstance(k, tuple) and k and k[0] == "head_t"]:
        onemesh._CACHE.pop(kk, None)   # (each evaluation is a new head: don't keep hundreds)
    return ht, b


def solve(base: dict, ev: dict, iters: int = 6, log=print, d_line: float | None = None,
          hold_socket: float | None = SIG_SOCKET) -> dict:
    """identity + eye expression for evidence ev (photo_evidence). base: the block-in's base (its lid pose cleared
    here). d_line: the crease's least local depth (mm) when the picture shows a line (default D_LINE); hold_socket: the
    socket readings' sigma (sd; None = not held). Returns {"c", "expression", "read0", "read", "cost", "dc", "e",
    "socket0", "socket"}."""
    d_line = D_LINE if d_line is None else float(d_line)
    from . import blockin as bi
    Ln, Rn, _ = _names()
    b0 = copy.deepcopy(base)
    pose = dict(b0["head"].get("pose") or {})
    pose.pop("lid_upper", None)
    pose.pop("lid_lower", None)
    b0["head"]["pose"] = pose
    if not pose:
        b0["head"].pop("pose", None)
    c0 = bi.identity({"base": b0})
    e0 = np.zeros(NE)
    ex0 = b0["head"].get("expression") or {}
    for k in range(NE):
        e0[k] = 0.5 * (float(ex0.get(Ln[k], 0.0)) + float(ex0.get(Rn[k], 0.0)))
    ht0, _ = _head(b0, c0, e0, Ln, Rn)
    rd = Reader(ht0)
    ex_other = {k: v for k, v in ex0.items() if k not in set(Ln) | set(Rn)}

    def sock(c, e):
        return socket(c, {**ex_other, **{Ln[k]: e[k] for k in range(NE)}, **{Rn[k]: e[k] for k in range(NE)}})
    s0 = sock(c0, e0)
    L0 = np.asarray(ht0["lm68"], float)
    tps_k = None

    def resid(x):
        ht, _ = _head(b0, c0 + x[:170], e0 + x[170:], Ln, Rn)
        q = rd.read(ht)
        r = [(q["up"] - ev["up"]) / SIG_LID if np.isfinite(q["up"]) else 50.0,
             (q["lo"] - ev["lo"]) / SIG_LID if np.isfinite(q["lo"]) else 50.0]
        if np.isfinite(ev.get("tps", np.nan)):
            want = ev["tps"] * q["r_iris_mm"] / (5.85)   # the picture's mm at an 11.7 mm iris -> ours
            if ev.get("hooded"):
                r.append((q["vis"] - want) / SIG_HOODED if np.isfinite(q["vis"]) else 20.0)
            else:
                r.append((q["hsoft"] - want) / SIG_TPS if np.isfinite(q["hsoft"]) else 20.0)
                r.append(min(q["lsoft"] - d_line, 0.0) / SIG_LINE)
        L = np.asarray(ht["lm68"], float)
        if hold_socket:
            s = sock(c0 + x[:170], e0 + x[170:])
            r += [(s[k] - s0[k]) / hold_socket for k in SOCKET]
        r += list(((L[HOLD] - L0[HOLD]) * 1000 / SIG_HOLD).ravel())
        r += list(((L[BROWS] - L0[BROWS]) * 1000 / SIG_BROW).ravel())
        return np.array(r), q
    n = 170 + NE
    x = np.zeros(n)
    lam = 0.01
    r, q0 = resid(x)
    log(f"eye step start: picture up {ev['up']:.2f} lo {ev['lo']:.2f} tps {ev.get('tps', np.nan):.2f} mm dark "
        f"{ev.get('dark', 0):.2f} | model up {q0['up']:.2f} lo {q0['lo']:.2f} show {q0['show']:.2f} mm crease local "
        f"{q0['local']:.2f} mm at {q0['height']:.1f}")
    f = float(r @ r + x @ x)
    for it in range(iters):
        J = np.zeros((len(r), n))
        h = 0.25
        for j in range(n):
            ej = np.zeros(n)
            ej[j] = h
            J[:, j] = (resid(x + ej)[0] - r) / h
        while True:
            step = np.linalg.solve(J.T @ J + (1 + lam) * np.eye(n), -(J.T @ r + x))
            xn = x + step
            rn, qn = resid(xn)
            fn = float(rn @ rn + xn @ xn)
            if fn < f:
                x, r, f, lam = xn, rn, fn, lam * 0.5
                break
            lam *= 4
            if lam > 1e4:
                break
        q = resid(x)[1]
        log(f"  it {it}: cost {f:.2f} |dc| {np.linalg.norm(x[:170]):.2f} |e| {np.linalg.norm(e0 + x[170:]):.2f} | up "
            f"{q['up']:.2f} lo {q['lo']:.2f} platform {q['vis']:.2f} (hood {q['drop']:.2f}) crease {q['lsoft']:.2f} mm at {q['hsoft']:.2f}")
        if lam > 1e4:
            break
    q = resid(x)[1]
    e = e0 + x[170:]
    s1 = sock(c0 + x[:170], e)
    log("  socket " + ", ".join(f"{k} {s0[k]:+.2f} -> {s1[k]:+.2f}" for k in SOCKET))
    return {"socket0": s0, "socket": s1, "c": c0 + x[:170], "expression": {**{Ln[k]: round(float(e[k]), 5) for k in range(NE) if abs(e[k]) > 1e-5},
                                              **{Rn[k]: round(float(e[k]), 5) for k in range(NE) if abs(e[k]) > 1e-5}},
            "read0": q0, "read": q, "cost": f, "dc": float(np.linalg.norm(x[:170])), "e": float(np.linalg.norm(e)),
            "pose": pose}


def eye_step(name: str, out: str | None = None, seen: str = "", iters: int = 6, log=print) -> dict:
    """The block-in step: solve, then write it as a new model (blockin.step with the identity / expression set)."""
    from PIL import Image
    from . import blockin as bi, store
    rj = bi._refs(name)
    vi = bi._front(rj)
    v = rj["views"][vi]
    ev = photo_evidence(Image.open(v["image"]).convert("RGB"), v)
    base = store.load(name)["base"]
    s = solve(base, ev, iters=iters, log=log)
    rep = bi.step(name, {}, out=out, seen=seen or "lids and fold vs the picture (eye step)",
                  why=(f"eye step (identity + GNM eye-region expression; no lidfold, no lid pose): picture up "
                       f"{ev['up']:.2f} lo {ev['lo']:.2f} iris radii, fold line {ev['tps']:.2f} mm (dark {ev['dark']:.2f}); "
                       f"model {s['read']['up']:.2f} / {s['read']['lo']:.2f}, platform {s['read']['show']:.2f} mm, "
                       f"crease {s['read']['local']:.2f} mm deep; |dc| {s['dc']:.2f}, |e| {s['e']:.2f}"),
                  _identity=s["c"], _head_set={"expression": s["expression"], "pose": s["pose"] or None})
    rep["eyes"] = {"evidence": {k: v for k, v in ev.items() if k != "columns"}, **{k: s[k] for k in ("read0", "read", "dc", "e")}}
    return rep


def text(e: dict) -> str:
    """The eye step's report (eye_step's rep["eyes"])."""
    ev, a, b = e["evidence"], e["read0"], e["read"]
    fold = (f"no fold line on the picture (hooded: the platform target {HOODED_SHOW} mm visible)" if ev.get("hooded")
            else f"fold line {ev['tps']:.2f} mm over the lashes (at an 11.7 mm iris), darkness {ev['dark']:.2f}")
    return (f"EYE STEP (identity + GNM eye-region expression, the rest of the face held; no lidfold, no lid pose): "
            f"picture lids {ev['up']:.2f} / {ev['lo']:.2f} iris radii, {fold}\n"
            f"  model before: lids {a['up']:.2f} / {a['lo']:.2f}, platform {a['show']:.2f} mm, crease {a['lsoft']:.2f} mm deep "
            f"at {a['hsoft']:.2f} mm\n"
            f"  model after:  lids {b['up']:.2f} / {b['lo']:.2f}, platform {b['show']:.2f} mm, crease {b['lsoft']:.2f} mm deep "
            f"at {b['hsoft']:.2f} mm | |dc| {e['dc']:.2f}, eye expression |e| {e['e']:.2f}")
