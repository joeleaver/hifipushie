"""The block-in's LIPS step (gnmdetail, 2026-10-10; Joe: "still don't have her ... lip line, I know GNM CAN make those
shapes"). Like the eye step (blockin_eyes.py): one MAP solve over GNM's identity (170) + its lower-face EXPRESSION
(lower_face_region 0..NL-1), on the head as it ships (onemesh.head_template), driven by what the front picture shows,
the rest of the face held. Result: base.head.identity + the lower-face comps in base.head.expression; lip_seal and
mouth_gap cleared (GNM's own expression closes the lips).

Why (gnm_atlas.md "## gnmdetail"): the lip seal (faceslide.seal_delta on the head + base._sealed_field for the field)
closes a parted neutral by moving the lips whole and fading the move out across the vermilion border: on Tess the
rendered border's turn fell from 24 deg (the one mesh) to 11 deg (the dressed stage), the upper vermilion came forward
instead of turning down, and the lips read as a flat painted pad. Closed by GNM's expression instead the border keeps
24-28 deg through Catmull-Clark and the field. But the closing alone adds a pout (faces5: CONTACT_BY=expression
overshot), so the closing is solved WITH the picture's border:
  - the vermilion border traced on the picture (lipborder.read: MediaPipe's outer lip contour refined to the a* edge,
    the corners left to the detector) vs GNM's border loops (the upper_lip / lower_lip groups' outer edges) through the
    front camera, point to polyline, sigma SIG_BORDER mm. The picture's fitted expression (human_refs "expressions",
    blockin.view_expression) is added for this term: the picture's smile is not the neutral's;
  - the neutral's lips in contact: the inner-lip landmark pairs (61-67, 62-66, 63-65) at 0 mm, sigma SIG_GAP;
  - the 68 landmarks off the mouth held at SIG_HOLD mm, the mouth corners at SIG_CORNER;
  - priors |dc|^2 + |e|^2 (both unit variance).
No faceslide sliders, no MakeHuman extensions, no seal.
"""
from __future__ import annotations

import copy

import numpy as np

NL = 40                 # lower-face expression comps solved (the mouth_gap solver's set)
SIG_BORDER = 0.35       # mm
SIG_GAP = 0.15          # mm
SIG_HOLD = 0.3          # mm
SIG_CORNER = 0.6        # mm (48 / 54)
HOLD = [i for i in range(68) if not 48 <= i < 68]
CORNERS = [48, 54]
GAPS = ((61, 67), (62, 66), (63, 65))
INNER = (0.1, 0.9)      # the share of each traced border used (its ends are the detector's corners)
SEAM_UP = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]   # MediaPipe's inner lip contours (corner to corner)
SEAM_LO = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]
SEAM_INNER = 0.1
SIG_SEAM = 0.4          # mm: the model's contact line through the camera vs the picture's seam
SIG_LEAD = 0.3          # mm: the lower lip ahead of the upper at the contact (rolled up over it)


def _names():
    from . import base as basemod
    n = [str(x) for x in basemod._gnm_data()["expression_names"]]
    return [k for k in n if k.startswith("lower_face_region")][:NL]


def border_loops():
    """Head rows (onemesh.head_template's verts: GNM's skin rows) of the upper / lower vermilion border, ordered by x:
    GNM's upper_lip / lower_lip groups' vertices next to exterior skin outside both lips."""
    from . import base as basemod
    g = basemod._gnm_data()
    grp = lambda k: np.asarray(g["groups"][k], float) > 0.5  # noqa: E731
    ext, lips = grp("skin_exterior"), grp("upper_lip") | grp("lower_lip")
    Q = np.asarray(g["quads"], int)
    E = np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]]
    T0 = np.asarray(g["template_vertex_positions"], float)
    sk = np.flatnonzero(np.asarray(g["skin"]))
    row = np.full(len(g["skin"]), -1)
    row[sk] = np.arange(len(sk))
    out = []
    for name in ("upper_lip", "lower_lip"):
        m = grp(name)
        a, b = E[:, 0], E[:, 1]
        v = np.unique(a[m[a] & ~lips[b] & ext[b]])
        out.append(row[v[np.argsort(T0[v, 0])]])
    return out


CONTACT_X = 15          # samples across the contact ring's inner CONTACT_SPAN of its width
CONTACT_SPAN = 0.85
OVERLAP = 0.2           # mm the two halves may cross before it costs (the field merges them)
ROLL_SPAN = 0.85        # (the "roll" read: the inner rolls' smallest gap, mm, - = crossing)


def ring_rows(k: int | None = None):
    """Head rows of GNM's lip ring k (rings out from the skin's open mouth loop, faceslide._lip_rings; default the
    CONTACT ring, base.LIP_RING: landmarks 61-63 / 65-67 sit on it), its upper and lower halves (GNM's upper_lip /
    lower_lip groups)."""
    from . import base as basemod, faceslide
    R = faceslide._lip_rings()
    C = R["rings"][R["contact"] if k is None else k]
    up = R["upper"][C]
    g = basemod._gnm_data()
    sk = np.flatnonzero(np.asarray(g["skin"]))
    row = np.full(len(g["skin"]), -1)
    row[sk] = np.arange(len(sk))
    return row[C[up]], row[C[~up]]


def contact_rows():
    return ring_rows(None)


def _ring_pair(ht, k=None, span=None):
    """(x samples, upper verts at them, lower verts at them) across ring k's middle `span` of its width."""
    U, L = (_rows(ht, r) for r in ring_rows(k))
    V = np.asarray(ht["verts"], float)
    U, L = U[U >= 0], L[L >= 0]
    xu, xl = V[U, 0], V[L, 0]
    ou, ol = np.argsort(xu), np.argsort(xl)
    lo, hi = max(xu.min(), xl.min()), min(xu.max(), xl.max())
    mid, half = 0.5 * (lo + hi), 0.5 * (hi - lo) * (CONTACT_SPAN if span is None else span)
    xx = np.linspace(mid - half, mid + half, CONTACT_X)
    pu = np.stack([np.interp(xx, xu[ou], V[U[ou], j]) for j in range(3)], 1)
    pl = np.stack([np.interp(xx, xl[ol], V[L[ol], j]) for j in range(3)], 1)
    return xx, pu, pl


def contact_gaps(ht, k=None, span=None) -> np.ndarray:
    """The neutral's lip gap (mm, + = open: the upper half above the lower) at CONTACT_X points across ring k's (default
    the contact ring's) middle span (CONTACT_SPAN) of its width (world z, the head's up)."""
    _, pu, pl = _ring_pair(ht, k, span)
    return (pu[:, 2] - pl[:, 2]) * 1000


def roll_rings() -> list:
    """The rings behind the contact (the inner rolls, from the open mouth loop in)."""
    from . import base as basemod
    return list(range(basemod.LIP_RING))


def contact_lead(ht) -> np.ndarray:
    """How far the LOWER half of the contact ring stands in front of the upper (mm, + = the lower lip ahead: rolled up
    over the upper lip's own roll; a closed rest mouth has the upper at or ahead)."""
    _, pu, pl = _ring_pair(ht)
    fwd = np.asarray(ht["forward"], float)
    return (pl @ fwd - pu @ fwd) * 1000


def _rows(ht, rows):
    """GNM skin rows -> this head's rows (a zipped / sealed head renumbers its skin: ht["skin_index"])."""
    si = ht.get("skin_index")
    if si is None:
        return np.asarray(rows)
    r = np.asarray(si)[np.asarray(rows)]
    return r[r >= 0]


def _similarity(A, B):
    """s, R, t with B ~ s R A + t (Umeyama)."""
    ma, mb = A.mean(0), B.mean(0)
    U, S, Vt = np.linalg.svd((B - mb).T @ (A - ma))
    d = np.sign(np.linalg.det(U @ Vt))
    D = np.diag([1, 1, d])
    R = U @ D @ Vt
    s = float(np.trace(np.diag(S) @ D) / ((A - ma) ** 2).sum())
    return s, R, mb - s * R @ ma


def head_to_world(base: dict, ht: dict):
    """The map from head_template's frame to the posed one mesh's (humanfit.state, the cameras' frame): a similarity
    fitted on the face's GNM vertices. Returns (f(X) -> world, rms mm)."""
    from . import base as basemod, humanfit, onemesh
    st = humanfit.state(base)
    tpl = st["tpl"]
    g = basemod._gnm_data()
    sk = np.flatnonzero(np.asarray(g["skin"]))
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(tpl["fid"])]
    of = np.full(len(g["skin"]), -1)
    of[gid[gid >= 0]] = np.flatnonzero(gid >= 0)
    H = np.asarray(ht["verts"], float)
    P = np.asarray(tpl["P"], float)
    si = ht.get("skin_index")
    rows = np.arange(len(sk)) if si is None else np.asarray(si)
    oi = of[sk]
    ok = (oi >= 0) & (rows >= 0)
    L = np.asarray(ht["lm68"], float)
    face = np.zeros(len(sk), bool)
    face[ok] = np.linalg.norm(H[rows[ok]] - L[27:68].mean(0), axis=1) < 0.07
    sel = ok & face
    s, R, t = _similarity(H[rows[sel]], P[oi[sel]])
    rms = float(np.sqrt(((s * H[rows[sel]] @ R.T + t - P[oi[sel]]) ** 2).sum(1).mean())) * 1000
    return (lambda X: s * np.asarray(X, float) @ R.T + t), rms


def _poly_dist(Q, poly):
    """Signed distance (px) of each point of Q to the polyline (+ = on the polyline's outward side, given by the
    caller's sign of the normal) -> (distance, nearest point)."""
    a, b = poly[:-1], poly[1:]
    ab = b - a
    out, near, inside = [], [], []
    for p in Q:
        t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab ** 2).sum(1), 1e-12), 0, 1)
        q = a + t[:, None] * ab
        d = np.linalg.norm(p - q, axis=1)
        j = int(np.argmin(d))
        out.append(d[j])
        near.append(q[j])
        # past the traced part's ends (the corners are the detector's): no evidence there
        inside.append(not ((j == 0 and t[j] <= 0.0) or (j == len(a) - 1 and t[j] >= 1.0)))
    return np.array(out), np.array(near), np.array(inside)


def photo_evidence(img, view: dict) -> dict:
    """The front picture's traced borders (px) and the scale, from MediaPipe + lipborder.read."""
    from . import blockin as bi, lipborder
    P = np.asarray(bi.detect_view(img, view), float)
    r = lipborder.read(img, P)
    n = len(r["upper"])
    u = np.linspace(0, 1, n)
    keep = (u >= INNER[0]) & (u <= INNER[1])
    # the seam where the lips meet: MediaPipe's inner upper and lower contours averaged (a closed mouth), its middle
    iu = P[SEAM_UP, :2]
    il = P[SEAM_LO, :2]
    seam = 0.5 * (iu + il)
    m = len(seam)
    seam = seam[int(round(SEAM_INNER * m)) - 1:m - int(round(SEAM_INNER * m)) + 1]
    return {"upper": r["upper"][keep], "lower": r["lower"][keep], "mmpx": float(r["mmpx"]),
            "mouth": P[[13, 14], :2].mean(0), "seam": seam, "bow": _bow_px(r["upper"], P, float(r["mmpx"]))}


def _bow_px(U, P, mmpx):
    """The traced upper border's Cupid's bow (mm): its two peaks over the centre trough, along the face's up axis."""
    from .likeness_eyes import frame
    ex, ey = (np.asarray(v, float) for v in frame(P))
    U = np.asarray(U, float)
    h = -(U - U.mean(0)) @ ey * mmpx
    n = len(U)
    c = h[int(0.46 * n):int(0.54 * n)].min()
    return float(np.mean([h[int(0.28 * n):int(0.46 * n)].max(), h[int(0.54 * n):int(0.72 * n)].max()]) - c)


def lip_read(name: str) -> dict:
    """The lips on the front picture vs the model (as the picture shows it: its fitted expression on): the vermilion
    borders' miss (rms, and mean offset + = the model's outside the picture's), the seam's miss, the Cupid's bow (mm,
    both), the neutral's contact gaps (max / median / min mm) and its inner rolls' smallest gap (- = crossing)."""
    from PIL import Image
    from . import blockin as bi, onemesh, store
    rj = bi._refs(name)
    vi = bi._front(rj)
    v = rj["views"][vi]
    ev = photo_evidence(Image.open(v["image"]).convert("RGB"), v)
    base = store.load(name)["base"]
    hn = onemesh.head_template(base)
    hv = onemesh.head_template(bi.view_base(base, rj, vi))
    to_world, _ = head_to_world(base, hn)
    q = lip_reads(hv, ev, to_world, rj["cameras"][vi])
    qn = lip_reads(hn)
    hd = base.get("head") or {}
    closing = ("seal" if float(hd.get("lip_seal") or 0) >= 0.5 and hd.get("mouth_gap") is None else
               f"mouth_gap {hd['mouth_gap']}" if hd.get("mouth_gap") is not None else
               "lip_close (GNM expression)" if hd.get("lip_close") else "expression / none")
    return {"photo_bow": ev["bow"], "bow": q["bow"], "miss_upper": q["miss_upper"], "miss_lower": q["miss_lower"],
            "off_upper": q["off_upper"], "off_lower": q["off_lower"], "miss_seam": q["miss_seam"], "gap": qn["gap"],
            "roll": qn.get("roll"), "closing": closing}


def read_text(r: dict) -> str:
    return (f"LIPS (front picture vs model): vermilion border miss upper {r['miss_upper']:.2f} mm (offset {r['off_upper']:+.2f}, "
            f"+ = model outside), lower {r['miss_lower']:.2f} mm ({r['off_lower']:+.2f}); seam miss {r['miss_seam']:.2f} mm; "
            f"Cupid's bow picture {r['photo_bow']:.2f} mm, model {r['bow']:.2f} mm; neutral contact gaps max / median / min "
            f"{np.round(r['gap'], 2).tolist()} mm, inner rolls {r['roll']:+.2f} mm; closing: {r['closing']}")


def _head(base, c, ex: dict):
    from . import blockin as bi, onemesh
    b = copy.deepcopy(base)
    bi.set_identity({"base": b}, c)
    b["head"]["expression"] = {k: round(float(v), 6) for k, v in ex.items() if abs(v) > 1e-7}
    ht = onemesh.head_template(b)
    for kk in [k for k in onemesh._CACHE if isinstance(k, tuple) and k and k[0] == "head_t"]:
        onemesh._CACHE.pop(kk, None)
    return ht


def lip_reads(ht, ev=None, to_world=None, cam=None) -> dict:
    """Readings on a head: the inner-lip gaps (mm), the border loops' rms miss against the picture's (mm) if given,
    and the bow depth (mm: the upper border's peaks over its centre trough, front plane)."""
    up, lo = (_rows(ht, r) for r in border_loops())
    V = np.asarray(ht["verts"], float)
    L = np.asarray(ht["lm68"], float)
    out = {"gap_lm": [float(np.linalg.norm(L[a] - L[b]) * 1000) for a, b in GAPS]}
    try:
        gp = contact_gaps(ht)
        out["gap"] = [float(gp.max()), float(np.median(gp)), float(gp.min())]   # contact: max / median / min (mm)
    except (ValueError, IndexError):   # (a sealed head's contact ring is merged)
        out["gap"] = [float("nan")] * 3
    U = V[up]
    x, z = U[:, 0] - 0.5 * (U[:, 0].max() + U[:, 0].min()), U[:, 2]
    k = np.argsort(x)
    f = lambda q: float(np.interp(q, x[k], z[k]))  # noqa: E731
    xx = np.linspace(0.0015, 0.010, 30)
    out["bow"] = (0.5 * (max(f(q) for q in xx) + max(f(-q) for q in xx)) - f(0.0)) * 1000
    if ev is not None:
        from . import humanfit
        for nm, rows in (("upper", up), ("lower", lo)):
            px = humanfit.project(cam, to_world(V[rows]))
            d, q, ins = _poly_dist(px, ev[nm])
            s = np.sign(((px - q) * (q - ev["mouth"])).sum(1))
            out["miss_" + nm] = float(np.sqrt(np.mean(d[ins] ** 2))) * ev["mmpx"]
            out["off_" + nm] = float(np.mean((s * d)[ins])) * ev["mmpx"]   # + = the model's border outside the picture's
        cu = _rows(ht, contact_rows()[0])
        px = humanfit.project(cam, to_world(V[cu[cu >= 0]]))
        d, q, ins = _poly_dist(px, ev["seam"])
        out["miss_seam"] = float(np.sqrt(np.mean(d[ins] ** 2))) * ev["mmpx"] if ins.any() else float("nan")
    try:
        out["roll"] = float(min(contact_gaps(ht, k, ROLL_SPAN).min() for k in roll_rings()))
    except (ValueError, IndexError):
        out["roll"] = float("nan")
    try:
        out["lead"] = float(contact_lead(ht).max())
    except (ValueError, IndexError):
        out["lead"] = float("nan")
    return out


def solve(base: dict, ev: dict, cam: dict, view_ex: dict | None = None, iters: int = 6, log=print) -> dict:
    """identity + lower-face expression for the picture's borders (ev, photo_evidence) through camera cam, the neutral
    closed, the rest held. view_ex: the picture's own fitted expression (added for the border term only)."""
    from . import blockin as bi, humanfit
    names = _names()
    b0 = copy.deepcopy(base)
    b0["head"].pop("lip_seal", None)
    b0["head"].pop("mouth_gap", None)
    b0["head"].pop("lip_close", None)
    c0 = bi.identity({"base": b0})
    ex0 = dict(b0["head"].get("expression") or {})
    other = {k: v for k, v in ex0.items() if k not in names}
    e0 = np.array([float(ex0.get(k, 0.0)) for k in names])
    view_ex = dict(view_ex or {})
    ht0 = _head(b0, c0, {**other, **dict(zip(names, e0))})
    to_world, rms = head_to_world(b0, ht0)
    log(f"lips step: head -> camera frame similarity rms {rms:.2f} mm")
    up, lo = border_loops()
    L0 = np.asarray(ht0["lm68"], float)
    sgn_poly = {}
    for nm in ("upper", "lower"):
        sgn_poly[nm] = ev[nm]

    def heads(x):
        c, e = c0 + x[:170], e0 + x[170:]
        exn = {**other, **dict(zip(names, e))}
        hn = _head(b0, c, exn)
        if view_ex:
            exv = dict(exn)
            for k, v in view_ex.items():
                exv[k] = exv.get(k, 0.0) + float(v)
            hv = _head(b0, c, exv)
        else:
            hv = hn
        return hn, hv

    def resid(x):
        hn, hv = heads(x)
        V = np.asarray(hv["verts"], float)
        r = []
        for nm, rows in (("upper", up), ("lower", lo)):
            px = humanfit.project(cam, to_world(V[rows]))
            d, q, ins = _poly_dist(px, ev[nm])
            # signed: + = the model's border outside the picture's (away from the mouth's centre); none past the
            # traced part's ends
            s = np.sign(((px - q) * (q - ev["mouth"])).sum(1))
            r += list(ins * s * d * ev["mmpx"] / SIG_BORDER)
        # the seam: the contact ring's upper half (the picture's expression on) through the camera
        cu = _rows(hv, contact_rows()[0])
        px = humanfit.project(cam, to_world(V[cu[cu >= 0]]))
        px = px[np.argsort(px[:, 0])][::2]
        d, q, ins = _poly_dist(px, ev["seam"])
        r += list(ins * np.sign(q[:, 1] - px[:, 1]) * d * ev["mmpx"] / SIG_SEAM)
        L = np.asarray(hn["lm68"], float)
        gp = contact_gaps(hn)
        r += list(np.maximum(gp, 0.0) / SIG_GAP) + list(np.minimum(gp + OVERLAP, 0.0) / SIG_GAP)
        r += list(np.maximum(contact_lead(hn), 0.0) / SIG_LEAD)
        # (the rolls behind the contact cross: GNM's closing hangs the upper roll ~6.5 mm below the lower one. Kept
        # apart by a term here (SIG_ROLL) it cost |dc| 9.7 / |e| 10.7 and OPENED the mouth (a dark slit, teeth): the
        # field leaves the rolls out instead, onemesh.CLOSED_SEAL_V. "roll" is only read)
        r += list(((L[HOLD] - L0[HOLD]) * 1000 / SIG_HOLD).ravel())
        r += list(((L[CORNERS] - L0[CORNERS]) * 1000 / SIG_CORNER).ravel())
        return np.array(r), hn, hv
    n = 170 + len(names)
    x = np.zeros(n)
    lam = 0.01
    r, hn0, hv0 = resid(x)
    q0 = {**lip_reads(hv0, ev, to_world, cam), "gap": lip_reads(hn0)["gap"]}
    log(f"  start: border miss upper {q0['miss_upper']:.2f} lower {q0['miss_lower']:.2f} mm, gaps {np.round(q0['gap'], 2).tolist()} mm, bow {q0['bow']:.2f}")
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
            rn, hn, hv = resid(xn)
            fn = float(rn @ rn + xn @ xn)
            if fn < f:
                x, r, f, lam = xn, rn, fn, lam * 0.5
                break
            lam *= 4
            if lam > 1e4:
                break
        _, hn, hv = resid(x)
        q = {**lip_reads(hv, ev, to_world, cam), "gap": lip_reads(hn)["gap"]}
        log(f"  it {it}: cost {f:.1f} |dc| {np.linalg.norm(x[:170]):.2f} |e| {np.linalg.norm(e0 + x[170:]):.2f} | border miss "
            f"{q['miss_upper']:.2f} / {q['miss_lower']:.2f} mm, gaps {np.round(q['gap'], 2).tolist()}, rolls {q['roll']:.2f}, bow {q['bow']:.2f}")
        if lam > 1e4:
            break
    e = e0 + x[170:]
    return {"c": c0 + x[:170], "expression": {**other, **{k: round(float(v), 5) for k, v in zip(names, e) if abs(v) > 1e-5}},
            "read0": q0, "read": q, "cost": f, "dc": float(np.linalg.norm(x[:170])), "e": float(np.linalg.norm(e))}


def lips_step(name: str, out: str | None = None, seen: str = "", iters: int = 6, log=print) -> dict:
    """The block-in step: solve on the front picture, then write it as a new model (blockin.step with the identity /
    expression set, lip_seal and mouth_gap cleared)."""
    from PIL import Image
    from . import blockin as bi, store
    rj = bi._refs(name)
    vi = bi._front(rj)
    v = rj["views"][vi]
    ev = photo_evidence(Image.open(v["image"]).convert("RGB"), v)
    base = store.load(name)["base"]
    s = solve(base, ev, rj["cameras"][vi], view_ex=bi.view_expression(rj, vi), iters=iters, log=log)
    a, b = s["read0"], s["read"]
    rep = bi.step(name, {}, out=out, seen=seen or "lip borders vs the picture (lips step)",
                  why=(f"lips step (identity + GNM lower-face expression closing the neutral; no seal): border miss "
                       f"{a['miss_upper']:.2f} / {a['miss_lower']:.2f} -> {b['miss_upper']:.2f} / {b['miss_lower']:.2f} mm, "
                       f"bow {a['bow']:.2f} -> {b['bow']:.2f} mm; |dc| {s['dc']:.2f}, |e| {s['e']:.2f}"),
                  _identity=s["c"], _head_set={"expression": s["expression"], "lip_seal": None, "mouth_gap": None,
                                                         "lip_close": None})
    rep["lips"] = {k: s[k] for k in ("read0", "read", "dc", "e")}
    return rep


def text(e: dict) -> str:
    a, b = e["read0"], e["read"]
    return (f"LIPS STEP (identity + GNM lower-face expression; the neutral closed by GNM, no seal; the rest held): border "
            f"miss vs the picture upper / lower {a['miss_upper']:.2f} / {a['miss_lower']:.2f} -> {b['miss_upper']:.2f} / "
            f"{b['miss_lower']:.2f} mm, inner-lip gaps {np.round(a['gap'], 1).tolist()} -> {np.round(b['gap'], 1).tolist()} mm, "
            f"bow {a['bow']:.2f} -> {b['bow']:.2f} mm | |dc| {e['dc']:.2f}, |e| {e['e']:.2f}")
