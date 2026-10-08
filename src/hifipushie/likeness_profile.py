"""The profile a turned view shows (likeness_guide.md, "A profile from a three-quarter view").

In a three-quarter picture the far side of the face against the background IS a profile, at a known angle: forehead,
brow ridge, the far orbit and cheek, lips, mentolabial fold, chin, under-chin. The nose's own edge against the far cheek
is a second, internal contour (bridge, tip, columella). Both are traced on the reference (likeness_points lines
"profile" and "nose": hand / LLM placed anchors; the outer one is snapped onto the picture's edge against the
background) and found on the model through the same camera (its render's silhouette; the nose region's own extreme),
then measured alike: both in ONE frame (the model's nasion -> chin through that camera), protrusion c toward the
facing side as a function of height v, in mm of the picture (a turned view foreshortens depth: these are not true
profile millimetres, but the photo and the model are read the same way).

Line format (shared with onemesh2): likeness_points.json views[].lines["profile"] / ["nose"] = [[u, v], ...] in
full-picture pixels, top to bottom; "profile" from the forehead down round the chin, "nose" from between the brows
down the bridge, round the tip, back to the columella's base.
"""
from __future__ import annotations

import numpy as np

EDGE_REACH = 4.0      # px either side of the hand-placed line searched for the picture's edge
STEP_MM = 0.5         # the envelope's height step
KEYS = ("forehead_slope", "brow_ridge", "cheek_line", "upper_lip", "lower_lip", "mentolabial", "chin_projection", "chin_height",
        "nose_tip", "nose_length", "bridge_bow", "bridge_angle", "nose_gap")


def _dense(Q, step=0.25):
    Q = np.asarray(Q, float)
    seg = np.linalg.norm(np.diff(Q, axis=0), axis=1)
    s = np.r_[0, np.cumsum(seg)]
    t = np.arange(0, s[-1] + 1e-9, step)
    return np.c_[np.interp(t, s, Q[:, 0]), np.interp(t, s, Q[:, 1])]


def _lum(img):
    a = np.asarray(img.convert("RGB"), float)
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def snap_edge(img, anchors, reach: float = EDGE_REACH, outward=None) -> np.ndarray:
    """The hand-placed line moved onto the picture's own edge: along each point's normal, the strongest fall of
    luminance toward `outward` (default: the darker side of the whole line: a face against a dark background) within
    `reach` px; offsets median-filtered and smoothed along the line (one bright stroke must not pull a notch)."""
    from scipy.ndimage import gaussian_filter, gaussian_filter1d, map_coordinates, median_filter
    L = gaussian_filter(_lum(img), 0.8)
    Q = _dense(anchors, 0.5)
    T = np.gradient(Q, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    N = np.c_[T[:, 1], -T[:, 0]]
    ts = np.arange(-reach - 1, reach + 1.01, 0.25)
    S = np.stack([map_coordinates(L, [Q[:, 1] + t * N[:, 1], Q[:, 0] + t * N[:, 0]], order=1, mode="nearest") for t in ts], 1)
    if outward is None:
        outward = 1.0 if S[:, ts > 1].mean() < S[:, ts < -1].mean() else -1.0
    G = -np.gradient(S, axis=1) * outward     # > 0 where the picture darkens going outward
    G = gaussian_filter1d(G, 3, axis=0)       # along the line
    inner = (ts >= -reach) & (ts <= reach)
    G[:, ~inner] = -1e9
    off = ts[np.argmax(G, axis=1)]
    off = gaussian_filter1d(median_filter(off, 9, mode="nearest"), 2.0, mode="nearest")
    R = Q + off[:, None] * N
    return R[::3]


def frame_of(lm_px: np.ndarray, line) -> tuple:
    """(origin, ex toward the facing side, ey down the face) from the model's landmarks as the camera shows them:
    origin between the inner eye corners (lm 39, 42), ey toward the middle of the mouth's corners (48, 54): points a
    nose or chin fit doesn't move (nasion -> chin moved with the fit, and the photo's numbers with it)."""
    lm_px = np.asarray(lm_px, float)
    o = 0.5 * (lm_px[39] + lm_px[42])
    ey = 0.5 * (lm_px[48] + lm_px[54]) - o
    ey /= max(np.linalg.norm(ey), 1e-9)
    ex = np.array([ey[1], -ey[0]])
    if np.mean((np.asarray(line, float) - o) @ ex) < 0:
        ex = -ex
    return o, ex, ey


def envelope(Q, fr, mmpx, step=STEP_MM, smooth=1.0):
    """(v, c) mm: per height v down the face, the furthest the line reaches toward the facing side."""
    from scipy.ndimage import gaussian_filter1d
    o, ex, ey = fr
    D = _dense(Q, 0.1) if len(Q) < 5000 else np.asarray(Q, float)
    x, v = (D - o) @ ex * mmpx, (D - o) @ ey * mmpx
    i = np.floor((v - v.min()) / step).astype(int)
    c = np.full(i.max() + 1, -np.inf)
    np.maximum.at(c, i, x)
    vg = v.min() + (np.arange(len(c)) + 0.5) * step
    ok = np.isfinite(c)
    c = np.interp(vg, vg[ok], c[ok])
    if smooth:
        c = gaussian_filter1d(c, smooth / step, mode="nearest")
    return vg, c


def model_outline(zb, k, box, fr, mmpx, vlim, step=STEP_MM):
    """The model's silhouette toward the facing side from its render's depth pass: (v, c) mm and the line in picture
    pixels. vlim = (v0, v1) mm kept (forehead .. under the chin)."""
    from scipy.ndimage import gaussian_filter1d
    o, ex, ey = fr
    yy, xx = np.nonzero(np.isfinite(zb))
    P = np.c_[xx / k + box[0], yy / k + box[1]]
    x, v = (P - o) @ ex * mmpx, (P - o) @ ey * mmpx
    keep = (v >= vlim[0]) & (v <= vlim[1])
    x, v = x[keep], v[keep]
    i = np.floor((v - vlim[0]) / step).astype(int)
    c = np.full(int((vlim[1] - vlim[0]) / step) + 1, -np.inf)
    np.maximum.at(c, i, x)
    vg = vlim[0] + (np.arange(len(c)) + 0.5) * step
    ok = np.isfinite(c)
    if ok.sum() < 10:
        return None
    vg, c = vg[ok], gaussian_filter1d(c[ok], 1.0 / step, mode="nearest")
    Q = o + np.outer(c / mmpx, ex) + np.outer(vg / mmpx, ey)
    return vg, c, Q


def nose_ids(V, L, ears=None) -> np.ndarray:
    """Template vertices of the nose: near its bridge line and tip (lm 27..30, 33), a radius growing from 8 mm at the
    nasion to 15 mm at the tip."""
    A = np.array([L[27], L[28], L[29], L[30], L[33]])
    R = np.array([0.008, 0.010, 0.012, 0.015, 0.012])
    near = np.zeros(len(V), bool)
    for a, b, ra, rb in zip(A[:-1], A[1:], R[:-1], R[1:]):
        d = b - a
        t = np.clip(((V - a) @ d) / max(d @ d, 1e-12), 0, 1)
        near |= np.linalg.norm(V - (a + t[:, None] * d), axis=1) < ra + t * (rb - ra)
    return np.nonzero(near)[0]


def vertex_envelope(Qv, ids, fr, mmpx, step=2.0):
    """The extreme toward the facing side of a set of projected vertices, per height: (v, c, vertex id) (the id of the
    vertex that makes the contour there: what a fit moves)."""
    from scipy.ndimage import gaussian_filter1d
    o, ex, ey = fr
    x, v = (Qv - o) @ ex * mmpx, (Qv - o) @ ey * mmpx
    vg = np.arange(v.min() + step / 2, v.max(), step / 2)
    c, who = [], []
    for g in vg:
        m = np.abs(v - g) <= step / 2
        if not m.any():
            c.append(np.nan)
            who.append(-1)
            continue
        j = np.nonzero(m)[0][np.argmax(x[m])]
        c.append(x[j])
        who.append(int(ids[j]))
    c, who = np.array(c), np.array(who)
    ok = np.isfinite(c)
    return vg[ok], gaussian_filter1d(c[ok], 2.0, mode="nearest"), who[ok]


def _win(v, c, a, b):
    m = (v >= a) & (v <= b)
    return (v[m], c[m]) if m.sum() >= 2 else (None, None)


def _ext(v, c, a, b, kind):
    vv, cc = _win(v, c, a, b)
    if vv is None:
        return None
    i = int(np.argmax(cc) if kind == "max" else np.argmin(cc))
    return float(vv[i]), float(cc[i])


def keypoints(v, c, lv: dict) -> dict:
    """Named points (v, c) on an outer contour. lv = landmark heights in the same frame (mm): brow, sn (subnasale), sto
    (stomion), chin; they only open windows: each point is a feature of the contour itself. The chin point is the
    contour's corner between the face's front and the under-jaw (the support point 45 deg down and forward: it exists
    on any chin, notch or no notch); the lips are named only where a notch between them breaks the contour."""
    kp = {}
    b = _ext(v, c, lv["brow"] - 12, lv["brow"] + 8, "max")
    if b:
        kp["brow"] = b
        d = _ext(v, c, b[0] + 3, b[0] + 24, "min")
        if d:
            kp["orbit"] = d
        for nm, dv in (("fh1", -15.0), ("fh2", -38.0)):
            if v.min() <= b[0] + dv:
                kp[nm] = (b[0] + dv, float(np.interp(b[0] + dv, v, c)))
    if not (v.min() < lv["sto"] < v.max()):
        return kp
    kp["mouth"] = (lv["sto"], float(np.interp(lv["sto"], v, c)))
    m = (v >= lv["sto"]) & (v <= lv["chin"] + 10)
    vv, cc = v[m], c[m]
    if len(vv) > 8:
        # the corner: the point standing furthest out of the chord from the mouth's height to the under-jaw's end
        d = cc - (cc[0] + (cc[-1] - cc[0]) * (vv - vv[0]) / max(vv[-1] - vv[0], 1e-6))
        g = int(np.argmax(d))
        kp["chin"] = (float(vv[g]), float(cc[g]))
        w = (vv >= lv["sto"]) & (vv <= lv["sto"] + 12)
        if w.sum() >= 2 and vv[g] > lv["sto"] + 14:
            j = int(np.argmax(np.where(w, cc, -np.inf)))
            kp["ll"] = (float(vv[j]), float(cc[j]))
            k2 = (vv > vv[j] + 2) & (vv < vv[g] - 2)
            if k2.sum() >= 2:
                d = cc[j] + (cc[g] - cc[j]) * (vv - vv[j]) / max(vv[g] - vv[j], 1e-6) - cc
                i2 = int(np.argmax(np.where(k2, d, -np.inf)))
                kp["sulcus"] = (float(vv[i2]), float(cc[i2]))
    # the lips: only where a notch (a local minimum with a rise of 0.3 mm+ either side) breaks the contour near the mouth
    w0, w1 = lv["sto"] - 8, lv["sto"] + 8
    m = (v >= w0 - 12) & (v <= w1 + 12)
    vv, cc = v[m], c[m]
    best = None
    for i in range(1, len(cc) - 1):
        if w0 <= vv[i] <= w1 and cc[i] <= cc[i - 1] and cc[i] <= cc[i + 1]:
            up = cc[(vv < vv[i]) & (vv > vv[i] - 12)]
            dn = cc[(vv > vv[i]) & (vv < vv[i] + 12)]
            if len(up) and len(dn) and min(up.max(), dn.max()) - cc[i] >= 0.3:
                if best is None or abs(vv[i] - lv["sto"]) < abs(vv[best] - lv["sto"]):
                    best = i
    if best is not None:
        kp["sto"] = (float(vv[best]), float(cc[best]))
        kp["ul"] = _ext(v, c, vv[best] - 12, vv[best] - 0.5, "max")
        kp["ll_notch"] = _ext(v, c, vv[best] + 0.5, vv[best] + 12, "max")
    return {k: p for k, p in kp.items() if p is not None}


def nose_keypoints(v, c, base_v=None, nasion_v=None) -> dict:
    kp = {}
    if len(v) < 6:
        return kp
    i = int(np.argmax(c))
    kp["tip"] = (float(v[i]), float(c[i]))
    bv = v[-1] if base_v is None else min(base_v, v[-1])
    if bv > v[i] + 2:
        kp["base"] = (float(bv), float(np.interp(bv, v, c)))
    if nasion_v is not None:
        kp["nasion"] = (float(nasion_v), float(np.interp(nasion_v, v, c)))
    return kp


def measures(kp: dict, nkp: dict | None = None, nose=None, outer=None) -> dict:
    """The contour items (mm, deg). kp: keypoints of the outer contour; nkp, nose = (v, c): the nose's own contour;
    outer = (v, c) of the outer contour (for the nose tip's gap to it)."""
    out = {}
    g = kp.get
    if g("fh1") and g("fh2"):   # + = the forehead slopes back going up
        out["forehead_slope"] = float(np.degrees(np.arctan2(g("fh1")[1] - g("fh2")[1], g("fh1")[0] - g("fh2")[0])))
    if g("brow") and g("orbit"):
        out["brow_ridge"] = g("brow")[1] - g("orbit")[1]
    if g("ul") and g("sto"):
        out["upper_lip"] = g("ul")[1] - g("sto")[1]
    if g("ll_notch") and g("sto"):
        out["lower_lip"] = g("ll_notch")[1] - g("sto")[1]
    # the chin and the cheek's line against the brow's peak (the contour's own bony reference): a chin read against
    # the mouth-height contour mixed a full cheek with a weak chin
    if g("chin") and g("brow"):
        out["chin_projection"] = g("chin")[1] - g("brow")[1]
    if g("mouth") and g("brow"):
        out["cheek_line"] = g("mouth")[1] - g("brow")[1]
    if g("chin") and g("mouth"):
        out["chin_height"] = g("chin")[0] - g("mouth")[0]
    if g("ll") and g("sulcus") and g("chin"):
        (v0, c0), (v1, c1), (vs, cs) = g("ll"), g("chin"), g("sulcus")
        out["mentolabial"] = max(float(c0 + (c1 - c0) * (vs - v0) / max(v1 - v0, 1e-6) - cs), 0.0)
    nkp = nkp or {}
    if nkp.get("tip") and nkp.get("base"):
        out["nose_tip"] = nkp["tip"][1] - nkp["base"][1]
    if nkp.get("tip") and nkp.get("nasion"):
        out["nose_length"] = nkp["tip"][0] - nkp["nasion"][0]
    if nkp.get("tip") and nose is not None:   # + = the bridge bows out of its chord (a hump), - = scooped
        v, c = nose
        v1 = nkp["tip"][0] - 8.0
        v0 = max(v1 - 32.0, v.min())
        m = (v >= v0) & (v <= v1)
        if m.sum() >= 4 and v1 - v0 > 18:
            ca, cb = float(np.interp(v0, v, c)), float(np.interp(v1, v, c))
            d = c[m] - (ca + (cb - ca) * (v[m] - v0) / (v1 - v0))
            out["bridge_bow"] = float(d[np.argmax(np.abs(d))])
            out["bridge_angle"] = float(np.degrees(np.arctan2(cb - ca, v1 - v0)))
    if nkp.get("tip") and outer is not None:
        vo, co = outer
        if vo.min() < nkp["tip"][0] < vo.max():
            out["nose_gap"] = float(np.interp(nkp["tip"][0], vo, co) - nkp["tip"][1])
    return out


def levels(lm_px, fr, mmpx) -> dict:
    o, ex, ey = fr
    h = lambda ids: float(np.mean((np.asarray(lm_px, float)[ids] - o) @ ey) * mmpx)  # noqa: E731
    return {"brow": h([19, 24]), "sn": h([33]), "sto": h([62, 66]), "chin": h([8]), "nasion": h([27])}


def photo_levels(P, fr, mmpx, lv: dict) -> dict:
    """The photo's own heights for the windows (the detector's points), the model's where it has none."""
    if P is None:
        return dict(lv)
    o, ex, ey = fr
    h = lambda ids: float(np.mean((np.asarray(P, float)[ids] - o) @ ey) * mmpx)  # noqa: E731
    try:
        return {"brow": h([105, 334]), "sn": h([2]), "sto": h([13, 14]), "chin": h([152]), "nasion": h([168])}
    except Exception:  # noqa: BLE001
        return dict(lv)


def read(ph_img, lines: dict, md: dict, ph_box, P_photo=None) -> dict | None:
    """Everything for one picture: the photo's contours (the outer one snapped to its edge), the model's, both sets of
    key points and measures. md = likeness.model_sides entry (cam, passes, k, mesh, mmpx, side.lm = the model's
    landmarks projected); P_photo = the detector's points on the photo (heights of its own mouth / brow / chin)."""
    from . import humanfit
    P = lines.get("profile")
    if not P or len(P) < 5:
        return None
    mesh, cam, mmpx = md["mesh"], md["cam"], md["mmpx"]
    lm = np.asarray(md["side"].lm, float)
    fr = frame_of(lm, P)
    o, ex, ey = fr
    lv = levels(lm, fr, mmpx)
    lp_ = photo_levels(P_photo, fr, mmpx, lv)
    lv0 = lv
    lv = photo_levels(getattr(md["side"], "P", None), fr, mmpx, lv)   # the model's, by the same detector on its render
    Qp = snap_edge(ph_img, P)
    vp, cp = envelope(Qp, fr, mmpx)
    mo = model_outline(md["passes"]["zb"], md["k"], ph_box, fr, mmpx, (min(vp.min(), lv["brow"] - 45), lv["chin"] + 30))
    if mo is None:
        return None
    vm, cm, Qm = mo
    out = {"frame": fr, "mmpx": mmpx, "levels": lv0, "model_levels": lv, "photo_levels": lp_,
           "photo": {"line": Qp, "v": vp, "c": cp, "kp": keypoints(vp, cp, lp_)},
           "model": {"line": Qm, "v": vm, "c": cm, "kp": keypoints(vm, cm, lv)}}
    ids = nose_ids(mesh["V"], mesh["L"])
    Qv = humanfit.project(cam, mesh["V"][ids])
    vn, cn, who = vertex_envelope(Qv, ids, fr, mmpx)
    out["model"]["nose"] = {"v": vn, "c": cn, "ids": who, "line": o + np.outer(cn / mmpx, ex) + np.outer(vn / mmpx, ey)}
    nmk = nose_keypoints(vn, cn, base_v=lv["sn"], nasion_v=max(lv["nasion"], vn.min()))
    npk, nose_p = {}, None
    N = lines.get("nose")
    if N and len(N) >= 4:
        Qn = np.asarray(_dense(N, 0.5))
        vq, cq = envelope(Qn, fr, mmpx, smooth=0.75)
        npk = nose_keypoints(vq, cq, nasion_v=max(lp_.get("nasion", 0.0), vq.min()))
        nose_p = (vq, cq)
        out["photo"]["nose"] = {"v": vq, "c": cq, "line": Qn}
    out["photo"]["kn"], out["model"]["kn"] = npk, nmk
    out["photo"]["m"] = measures(out["photo"]["kp"], npk, nose_p, (vp, cp))
    out["model"]["m"] = measures(out["model"]["kp"], nmk, (vn, cn), (vm, cm))
    return out


def shift(rd: dict, v0=None, v1=None) -> np.ndarray:
    """(dc, dv) mm that lays the photo's outer contour on the model's over the bony upper face (brow to the nose's
    base): a loose camera's offset, taken out before contour misses become fit targets."""
    lv = rd["levels"]
    v0 = lv["brow"] - 8 if v0 is None else v0
    v1 = lv["sn"] if v1 is None else v1
    vp, cp, vm, cm = rd["photo"]["v"], rd["photo"]["c"], rd["model"]["v"], rd["model"]["c"]
    best = (1e9, 0.0, 0.0)
    g = np.arange(v0, v1, 1.0)
    for dv in np.arange(-6, 6.01, 0.5):
        a = np.interp(g + dv, vp, cp, left=np.nan, right=np.nan)
        b = np.interp(g, vm, cm, left=np.nan, right=np.nan)
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() < 8:
            continue
        dc = float(np.median(b[ok] - a[ok]))
        e = float(np.mean(np.abs(b[ok] - a[ok] - dc))) + 0.02 * abs(dv)
        if e < best[0]:
            best = (e, dc, dv)
    return np.array([best[1], -best[2]])


def targets(rd: dict, mesh: dict, cam: dict, vi: int, part: str, v_range=None, gain: float = 1.0, cap_mm: float = 5.0) -> list:
    """humanfit.fit_region targets from the contour's misses: the model vertices that make its contour ("outer": the
    silhouette's vertices found near the outline; "nose": the nose envelope's own), each asked to move toward the
    facing side by the photo's contour minus the model's at its height (the camera's offset, `shift`, taken out)."""
    from . import humanfit
    o, ex, ey = rd["frame"]
    mmpx = rd["mmpx"]
    dc, dv = shift(rd)
    out = []
    if part == "nose":
        if "nose" not in rd["photo"]:
            return out
        vq, cq = rd["photo"]["nose"]["v"] + dv, rd["photo"]["nose"]["c"] + dc
        n = rd["model"]["nose"]
        vs, cs, ids = n["v"], n["c"], n["ids"]
    else:
        vq, cq = rd["photo"]["v"] + dv, rd["photo"]["c"] + dc
        V = mesh["V"]
        Qv = humanfit.project(cam, V)
        x, v = (Qv - o) @ ex * mmpx, (Qv - o) @ ey * mmpx
        vm, cm = rd["model"]["v"], rd["model"]["c"]
        vs, cs, ids = [], [], []
        lo, hi = v_range or (vm.min(), vm.max())
        front = V[:, 1] < np.median(V[:, 1][np.abs(V[:, 2] - mesh["L"][30, 2]) < 0.05])   # the face's half of the head
        for g in np.arange(lo, hi, 2.0):
            m = (np.abs(v - g) <= 1.5) & front
            if not m.any():
                continue
            j = np.nonzero(m)[0][np.argmax(x[m])]
            if abs(x[j] - np.interp(g, vm, cm)) > 2.5:    # not on the silhouette (hidden behind something nearer)
                continue
            vs.append(v[j]); cs.append(x[j]); ids.append(int(j))
        vs, cs, ids = np.array(vs), np.array(cs), np.array(ids, int)
    seen = set()
    for g, c, i in zip(vs, cs, ids):
        if i in seen or g < vq.min() or g > vq.max() or (v_range and not (v_range[0] <= g <= v_range[1])):
            continue
        seen.add(int(i))
        raw = float(np.interp(g, vq, cq) - c)
        d = float(np.clip(gain * raw, -cap_mm, cap_mm))
        u0 = humanfit.project(cam, mesh["V"][i][None])[0]
        out.append({"view": vi, "tpl": [int(i)] * 3, "bary": [1.0, 0.0, 0.0], "uv": list(map(float, u0 + ex * d / mmpx)),
                    "miss_mm": d, "raw_mm": raw, "v": float(g)})
    return out
