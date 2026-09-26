"""Template wrap: a production base mesh carried onto a hifipushie model through matching skeletons, then projected
onto the exact surface and relaxed. usage: wrap.py model template.npz template_joints.json out_dir"""
import json
import sys
from pathlib import Path

import numpy as np

from hifipushie import sdf, store, surface
from hifipushie.spec import compile_prims, expand_mirror, resolve_point

FINGER_SEGS = [(f"finger{k}_{j}.L", f"finger{k}_{j + 1}.L") for k in range(1, 6) for j in range(3)] + \
              [(f"thumb_{j}.L", f"thumb_{j + 1}.L") for j in range(3)]
SEGS = [("pelvis", "chest"), ("chest", "neck"), ("neck", "head"), ("chest", "shoulder.L"), ("shoulder.L", "elbow.L"),
        ("elbow.L", "wrist.L"), ("wrist.L", "hand_end.L"), ("hip.L", "knee.L"),
        ("knee.L", "ankle.L"), ("ankle.L", "toe.L")]


def unit(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def mirror(J):
    out = dict(J)
    for n, p in J.items():
        if n.endswith(".L"):
            out[n[:-2] + ".R"] = np.array([-p[0], p[1], p[2]])
    return out


def segments(J):
    out = []
    for a, b in SEGS + FINGER_SEGS:
        for sa, sb in ((a, b), (a.replace(".L", ".R"), b.replace(".L", ".R"))) if ".L" in a + b else ((a, b),):
            if sa in J and sb in J:
                out.append((sa, sb))
    return sorted(set(out))


def seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(a + t[:, None] * ab - P, axis=1), t


def model_name(k):
    """Template joint name -> the model's: fingers to the hand kit's chains, the thumb to its thumb."""
    import re
    m = re.fullmatch(r"finger(\d)_(\d)(\.[LR])", k)
    if m:
        return f"hand_f{m[1]}_{m[2]}{m[3]}"
    m = re.fullmatch(r"thumb_(\d)(\.[LR])", k)
    if m:
        return f"hand_th_{m[1]}{m[2]}"
    return k


def rot_between(u, v):
    c = np.cross(u, v)
    s, d = np.linalg.norm(c), u @ v
    if s < 1e-9:
        return np.eye(3)
    k = c / s
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + s * K + (1 - d) * K @ K


def frame(u):
    x = np.cross(u, [0, 0, 1.0]) if abs(u[2]) < 0.9 else np.cross(u, [1.0, 0, 0])
    x /= np.linalg.norm(x)
    return x, np.cross(u, x)


NB = 16  # angle bins around a bone


SEGS_USED: list = []
STATIONS = np.linspace(0.0, 1.0, 5)  # along each bone, where radii are measured


def template_radii(P, a, b, own, t0=0.5, band=0.15):
    """Template's radius per angle bin around segment a-b at t0 along it, from its own vertices near there."""
    u = unit(b - a)
    x, y = frame(u)
    q = P[own] - a
    t = q @ u / np.linalg.norm(b - a)
    q = q - np.outer(q @ u, u)
    ang = np.arctan2(q @ y, q @ x)
    rad = np.linalg.norm(q, axis=1)
    bins = ((ang + np.pi) / (2 * np.pi) * NB).astype(int) % NB
    r = np.full(NB, np.nan)
    for k in range(NB):
        m = (bins == k) & (np.abs(t - t0) < band)
        if m.sum() >= 2:
            r[k] = np.percentile(rad[m], 90)
    return fill(r)


def fill(r):
    ok = np.isfinite(r)
    if not ok.any():
        return np.ones(NB)
    idx = np.arange(NB)
    return np.interp(idx, idx[ok], r[ok], period=NB)


def target_radii(prims, a, b, t0=0.5):
    """Target's radius per angle bin: rays from the point t0 along the segment in its cross-section plane."""
    u = unit(b - a)
    x, y = frame(u)
    m = a + t0 * (b - a)
    ang = (np.arange(NB) + 0.5) / NB * 2 * np.pi - np.pi
    dirs = np.cos(ang)[:, None] * x + np.sin(ang)[:, None] * y
    t = np.linspace(0, 0.5, 400)
    f = sdf.field_at(prims, m + t[None, :, None] * dirs[:, None, :], margin=0.05)
    r = np.array([t[np.flatnonzero(row > 0)[0]] if (row > 0).any() and row[0] < 0 else np.nan for row in f])
    return fill(r)


def wrap(model, tpl_npz, tpl_joints, out_dir, relax_rounds=15, sigma=0.8, face=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)
    spec = store.load(model)
    s = expand_mirror(spec)
    prims = [p for p in compile_prims(spec) if p.part == "body"]
    z = np.load(tpl_npz)
    P, L, S = z["verts"].astype(float), z["loops"], z["sizes"]
    Jt = mirror({k: np.array(v, float) for k, v in json.load(open(tpl_joints)).items() if not k.startswith("_")})
    Jm = {k: resolve_point(s, model_name(k)) for k in Jt if model_name(k) in s["joints"]}
    # the palm: wrist to the middle knuckle (the template's second finger, the model's second or only finger)
    for side in "LR":
        mk = next((f"hand_f{k}_0.{side}" for k in (2, 1) if f"hand_f{k}_0.{side}" in s["joints"]), None)
        if f"finger2_0.{side}" in Jt and mk:
            Jt[f"hand_end.{side}"] = Jt[f"finger2_0.{side}"]
            Jm[f"hand_end.{side}"] = resolve_point(s, mk)
        elif f"wrist.{side}" in Jt and f"elbow.{side}" in Jt:
            for J in (Jt, Jm):
                w, e = J[f"wrist.{side}"], J[f"elbow.{side}"]
                J[f"hand_end.{side}"] = w + unit(w - e) * 0.45 * np.linalg.norm(w - e)
    segs = [sg for sg in segments(Jt) if sg[0] in Jm and sg[1] in Jm]
    SEGS_USED[:] = segs
    # weights: each template vertex to its nearest segments (by distance relative to the template's local radius)
    D = np.stack([seg_dist(P, Jt[a], Jt[b])[0] for a, b in segs], 1)
    near = D.argmin(1)
    # per segment: rotation, stretch along the bone, radius scale per angle at stations along it
    xf = []
    for k, (a, b) in enumerate(segs):
        a0, b0, a1, b1 = Jt[a], Jt[b], Jm[a], Jm[b]
        u0, u1 = unit(b0 - a0), unit(b1 - a1)
        R = rot_between(u0, u1)
        sax = np.linalg.norm(b1 - a1) / np.linalg.norm(b0 - a0)
        L0 = np.linalg.norm(b0 - a0)
        if b.startswith(("hand_end", "toe")):  # a hand or a foot: rays across it hit digits and gaps; scale it
            # uniformly by how much thicker the wrist or ankle is (digits need their own correspondences)
            prox = [sg for sg in segs if sg[1] == a][0]
            pk = segs.index(prox)
            rw0 = np.median(template_radii(P, Jt[prox[0]], Jt[prox[1]], near == pk, 0.9))
            rw1 = np.median(target_radii(prims, Jm[prox[0]], Jm[prox[1]], 0.9))
            R0 = np.full((len(STATIONS), NB), rw0)
            R1 = np.full((len(STATIONS), NB), rw1)
        else:
            R0 = np.stack([template_radii(P, a0, b0, near == k, t0) for t0 in STATIONS])  # (stations, bins)
            R1 = np.stack([target_radii(prims, a1, b1, t0) for t0 in STATIONS])
        x1, y1 = frame(u1)
        x0, y0 = frame(u0)
        xr = R @ x0  # the template's frame carried over; its angle offset from the target's own frame
        xf.append(dict(a0=a0, u0=u0, a1=a1, R=R, sax=sax, L0=L0, R0=R0, R1=R1, x0=x0, y0=y0,
                       off=np.arctan2(xr @ y1, xr @ x1)))
    centres = (np.arange(NB) + 0.5) / NB * 2 * np.pi - np.pi

    def apply(X):
        Dx = np.stack([seg_dist(X, Jt[a], Jt[b])[0] for a, b in segs], 1)
        d0 = Dx.min(1, keepdims=True)
        W = np.exp(-((Dx - d0) / (sigma * np.maximum(d0, 0.01))) ** 2)
        W /= W.sum(1, keepdims=True)
        out = np.zeros_like(X)
        for k, g in enumerate(xf):
            q = X - g["a0"]
            t = q @ g["u0"]
            rad = q - np.outer(t, g["u0"])
            ang = np.arctan2(rad @ g["y0"], rad @ g["x0"])
            tc = np.clip(t / g["L0"], 0, 1)
            tgt = np.zeros(len(X)); src = np.zeros(len(X))
            for i in range(len(STATIONS) - 1):  # linear between stations
                lo, hi = STATIONS[i], STATIONS[i + 1]
                m = (tc >= lo) & (tc <= hi)
                w = (tc[m] - lo) / (hi - lo)
                ai = (ang[m] + g["off"] + np.pi) % (2 * np.pi) - np.pi
                tgt[m] = (1 - w) * np.interp(ai, centres, g["R1"][i], period=2 * np.pi) + w * np.interp(ai, centres, g["R1"][i + 1], period=2 * np.pi)
                src[m] = (1 - w) * np.interp(ang[m], centres, g["R0"][i], period=2 * np.pi) + w * np.interp(ang[m], centres, g["R0"][i + 1], period=2 * np.pi)
            rs = np.clip(tgt / np.maximum(src, 1e-3), 0.3, 4.0)
            out += W[:, k:k + 1] * (g["a1"] + (np.outer(t * g["sax"], g["u0"]) + rad * rs[:, None]) @ g["R"].T)
        return out, W

    out, W = apply(P)
    TPL_VERTS[:] = [P]
    s_prims[:] = [prims]
    if face is not None:  # the face: a radial-basis displacement carrying template landmarks onto the model's
        out = face_warp(out, P, apply, face, s)
    np.savez(out_dir / "warped.npz", verts=out, loops=L, sizes=S)
    # regions: each target primitive belongs to the target segment nearest its centre; a vertex projects onto its
    # dominant segment's primitives and its neighbours' (sharing a joint), so a hand never lands on a thigh
    cen = np.array([0.5 * (p.lo + p.hi) for p in prims])
    Dp = np.stack([seg_dist(cen, Jm[a], Jm[b])[0] for a, b in segs], 1)
    owner = Dp.argmin(1)
    regions = []
    for k, (a, b) in enumerate(segs):
        nbk = [i for i, (c, d) in enumerate(segs) if {c, d} & {a, b}]
        regions.append([p for p, o in zip(prims, owner) if o in nbk])
    dom = W.argmax(1)
    return out, L, S, prims, regions, dom


FACE_MODEL = {"eye.L": "face_eye.L", "nose_tip": "face_nose_tip", "mouth": "face_mouth_line_0",
              "mouth_corner.L": "face_mouth_corner.L", "ear_tip.L": "ear1.L"}


TPL_VERTS: list = []
s_prims: list = []


def _front(prims, p):
    """The model's front surface at p's x, z (a ray along +y from in front)."""
    t = np.linspace(-0.4, 0.2, 1200)
    pts = np.tile(p, (len(t), 1)); pts[:, 1] = p[1] + t
    f = sdf.field_at(prims, pts, margin=0.02)
    k = np.flatnonzero(f < 0)
    return pts[k[0]] if len(k) else None


def face_warp(out, P, apply, face_json, s):
    """Gaussian RBF on the warped template: each template landmark (warped by the skeleton) goes to the model's
    (face kit and ear joints); anchors on the crown, the back of the skull and the neck stay put."""
    f = json.load(open(face_json))
    src, dst = [], []
    for name, pt in f["landmarks"].items():
        mn = FACE_MODEL.get(name)
        pairs = [(pt, mn)]
        if name.endswith(".L"):
            pairs.append(([-pt[0], pt[1], pt[2]], mn.replace(".L", ".R") if mn else None))
        for p_, m_ in pairs:
            if m_ is None:
                continue
            if m_ in s["joints"]:
                tgt = resolve_point(s, m_)
            elif m_ in s["blobs"]:
                bl = s["blobs"][m_]
                tgt = resolve_point(s, bl.get("at", [0, 0, 0])) + np.array(bl.get("offset", [0, 0, 0]), float)
            else:
                continue
            src.append(p_)
            dst.append(tgt)
    ring = f.get("eye_ring")
    if ring and "face_lids.L" in s["blobs"]:  # scale the eye region: a ring round the template's eye goes to one
        # scaled by the ratio of lid openings, so the opening shrinks with its loops instead of being crushed
        Pt = TPL_VERTS[0]
        for side, sg in (("L", 1.0), ("R", -1.0)):
            c0 = np.array(f["landmarks"]["eye.L"], float) * [sg, 1, 1]
            lid = s["blobs"][f"face_lids.{side}"]
            c1 = resolve_point(s, lid["at"])
            k = float(lid.get("width", 0.85)) * float(lid["r"]) / ring["open_halfwidth"]
            for a in np.linspace(0, 2 * np.pi, ring["n"], endpoint=False):
                d = ring["radius"] * np.array([np.cos(a), 0.0, np.sin(a)])
                p0 = c0 + d
                near = Pt[np.hypot(Pt[:, 0] - p0[0], Pt[:, 2] - p0[2]) < 0.004]
                if not len(near):
                    continue
                p0[1] = near[:, 1].min()  # on the template's front surface
                p1 = c1 + k * d
                hit = _front(s_prims[0], p1)
                if hit is None:
                    continue
                src.append(p0)
                dst.append(hit)
    src = np.array(src, float)
    ws, _ = apply(src)
    disp = np.array(dst) - ws
    anc = np.array(list(f["anchors"].values()), float)
    wa, _ = apply(anc)
    C = np.r_[ws, wa]
    Dd = np.r_[disp, np.zeros_like(wa)]
    sig = 0.6 * np.linalg.norm(ws[0] - ws[1]) if len(ws) > 1 else 0.05
    sig = max(sig, 0.03)
    Phi = np.exp(-(np.linalg.norm(C[:, None] - C[None], axis=2) / sig) ** 2) + 1e-6 * np.eye(len(C))
    wts = np.linalg.solve(Phi, Dd)
    phi = np.exp(-(np.linalg.norm(out[:, None] - C[None], axis=2) / sig) ** 2)
    print(f"face: {len(src)} landmarks, largest move {np.linalg.norm(disp, axis=1).max() * 1000:.0f} mm, sigma {sig * 1000:.0f} mm")
    return out + phi @ wts


def tris(L, S):
    st = np.r_[0, np.cumsum(S)[:-1]]
    return np.array([(L[s], L[s + j], L[s + j + 1]) for s, n in zip(st, S) for j in range(1, n - 1)])


def edges(L, S):
    st = np.r_[0, np.cumsum(S)[:-1]]
    e = {(min(L[s + j], L[s + (j + 1) % n]), max(L[s + j], L[s + (j + 1) % n])) for s, n in zip(st, S) for j in range(n)}
    return np.array(sorted(e))


def vnormals(V, T):
    fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, T[:, k], fn)
    return N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)


def fit(V, L, S, prims, voxel, regions=None, dom=None, reach=0.12, rounds=int(__import__("os").environ.get("RELAX", 50)), keep=None, V_warped=None):
    """Shoot every vertex along its normal to the nearest zero crossing of its region's surface, then relax along
    the surface and re-project."""
    T = tris(L, S)
    E = edges(L, S)
    N = vnormals(V, T)
    t = np.linspace(-reach, reach, 121)
    if regions is None:
        f = sdf.field_at(prims, V[:, None, :] + t[None, :, None] * N[:, None, :], margin=reach)
    else:
        f = np.empty((len(V), len(t)))
        for k, reg in enumerate(regions):
            m = dom == k
            if m.any():
                f[m] = sdf.field_at(reg or prims, V[m][:, None, :] + t[None, :, None] * N[m][:, None, :], margin=reach)
    sgn = np.signbit(f)
    cross = sgn[:, 1:] != sgn[:, :-1]
    cost = np.where(cross, np.abs(0.5 * (t[1:] + t[:-1]))[None, :], np.inf)
    k = cost.argmin(1)
    ok = np.isfinite(cost[np.arange(len(V)), k])
    f0, f1 = f[np.arange(len(V)), k], f[np.arange(len(V)), k + 1]
    tt = t[k] + (t[k + 1] - t[k]) * f0 / np.where(f0 - f1 == 0, 1, f0 - f1)
    V = V.copy()
    V[ok] += tt[ok, None] * N[ok]

    def newton(X, it):
        if regions is None:
            return surface.newton(prims, X, voxel * 0.125, voxel, iterations=it)[0]
        X = X.copy()
        for k, reg in enumerate(regions):
            m = dom == k
            if m.any():
                X[m] = surface.newton(reg or prims, X[m], voxel * 0.125, voxel, iterations=it)[0]
        return X
    # vertices that found no surface along their normal: many Newton steps onto their own region
    keep = np.zeros(len(V), bool) if keep is None else keep  # interiors (a mouth bag, eye sockets): not projected
    V0 = V.copy()
    V[~ok & ~keep] = newton(V, 40)[~ok & ~keep]
    V = np.where(keep[:, None], V0, newton(V, 8))
    deg = np.bincount(E.ravel(), minlength=len(V))

    def lap(X):
        acc = np.zeros_like(X)
        np.add.at(acc, E[:, 0], X[E[:, 1]])
        np.add.at(acc, E[:, 1], X[E[:, 0]])
        return acc / np.maximum(deg, 1)[:, None] - X
    # relax toward the template's own spacing (its dense rings round the eyes and mouth, its packing in creases):
    # each vertex keeps its offset from its neighbours' average as warped, and loses only what projecting added
    L_w = lap(V_warped) if V_warped is not None else 0.0
    for _ in range(rounds):
        acc = np.zeros_like(V)
        np.add.at(acc, E[:, 0], V[E[:, 1]])
        np.add.at(acc, E[:, 1], V[E[:, 0]])
        N = vnormals(V, T)
        dv = lap(V) - L_w
        dv -= (dv * N).sum(1, keepdims=True) * N
        # interiors (mouth bag, sockets) aren't projected but move with their neighbours: held still, the lids
        # round them stretched into big faces
        # the whole body now: every vertex is near its own region, and a region's surface can be buried in another
        # (a finger's cone inside the palm), which left vertices inside and slivers hanging off them
        V = np.where(keep[:, None], V + 0.5 * lap(V),
                     surface.newton(prims, V + 0.5 * dv, voxel * 0.125, voxel, iterations=6)[0])
    return V, int((~ok).sum())


def smooth_away(V, L, S, mask, rounds=40):
    """Smooth a region of the warped template into a plain form (its other vertices fixed): a feature the model
    doesn't have (toes over a club foot) would otherwise be crushed onto its surface."""
    E = edges(L, S)
    deg = np.bincount(E.ravel(), minlength=len(V))
    V = V.copy()
    for _ in range(rounds):
        acc = np.zeros_like(V)
        np.add.at(acc, E[:, 0], V[E[:, 1]])
        np.add.at(acc, E[:, 1], V[E[:, 0]])
        V[mask] += 0.6 * (acc[mask] / np.maximum(deg[mask], 1)[:, None] - V[mask])
    return V


def untangle(V, L, S, prims, voxel, regions, dom, keep, passes=12):
    """Faces turned against the surface (tangles at eye and mouth corners, folds in a tight crease): smooth their
    vertices and a ring around them, re-project onto their regions, until none are left (or passes run out)."""
    T = tris(L, S)
    E = edges(L, S)
    deg = np.bincount(E.ravel(), minlength=len(V))
    nb = [[] for _ in range(len(V))]
    for a, b in E:
        nb[a].append(b)
        nb[b].append(a)
    for it in range(passes):
        fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        fn /= np.linalg.norm(fn, axis=1, keepdims=True) + 1e-12
        g = sdf.gradient(prims, V[T].mean(1), 1e-4)
        g /= np.linalg.norm(g, axis=1, keepdims=True) + 1e-12
        bad = (fn * g).sum(1) < 0.2
        bad &= ~keep[T].any(1)
        if not bad.any():
            break
        m = np.zeros(len(V), bool)
        m[T[bad].ravel()] = True
        for _ in range(2):  # and two rings around them
            m[[j for i in np.flatnonzero(m) for j in nb[i]]] = True
        m &= ~keep
        for _ in range(4):
            acc = np.zeros_like(V)
            np.add.at(acc, E[:, 0], V[E[:, 1]])
            np.add.at(acc, E[:, 1], V[E[:, 0]])
            V[m] += 0.5 * (acc[m] / np.maximum(deg[m], 1)[:, None] - V[m])
        V[m] = surface.newton(prims, V[m], voxel * 0.125, voxel, iterations=8)[0]
        print(f"  untangle pass {it}: {bad.sum()} faces turned, {m.sum()} verts smoothed")
    return V


if __name__ == "__main__":
    model, tpl, joints, out = sys.argv[1:5]
    Wd, L, S, prims, regions, dom = wrap(model, tpl, joints, out, face=sys.argv[5] if len(sys.argv) > 5 else None)
    meta = store.build(model, 160)
    sx = expand_mirror(store.load(model))
    if not any(n.startswith("foot_t") for n in sx["joints"]):  # no toes on the model: smooth the template's away
        Pt = np.load(tpl)["verts"]
        Jt = mirror({k: np.array(v, float) for k, v in json.load(open(joints)).items() if not k.startswith("_")})
        toe = np.zeros(len(Pt), bool)
        for side in "LR":
            a, t = Jt[f"ankle.{side}"], Jt[f"toe.{side}"]
            dirn = t - a
            dirn[2] = 0
            dirn /= np.linalg.norm(dirn)
            toe |= ((Pt - t) @ dirn > -0.02) & (Pt[:, 2] < 0.09) & (np.sign(Pt[:, 0]) == np.sign(t[0]))
        Wd = smooth_away(Wd, L, S, toe)
        print(f"toes smoothed away: {toe.sum()} verts")
    fv = json.load(open(joints)).get("_finger_verts", {})
    Pt = np.load(tpl)["verts"]
    from scipy.spatial import cKDTree
    kd = cKDTree(Pt)
    gone = np.zeros(len(Pt), bool)
    for name, idx in fv.items():
        k = int(name[6:])
        if f"hand_f{k}_0.L" not in sx["joints"]:  # the model has fewer fingers: this one folds into the palm
            idx = np.array(idx)
            gone[idx] = True
            gone[kd.query(Pt[idx] * [-1, 1, 1])[1]] = True
    if gone.any():
        Wd = smooth_away(Wd, L, S, gone, rounds=80)
        print(f"fingers smoothed away: {gone.sum()} verts")
    head = [k for k, sg in enumerate(SEGS_USED) if sg[1] in ("head", "neck")]
    inside = sdf.field_at(prims, Wd, margin=0.05) < -0.01
    keep = inside & np.isin(dom, head)
    if len(sys.argv) > 5:  # the template's eye openings (lid margins and the tunnel behind): follow, don't project
        fj = json.load(open(sys.argv[5]))
        if "eye_open" in fj:
            Pt = np.load(tpl)["verts"]
            e = np.array(fj["landmarks"]["eye.L"], float)
            for c in (e, e * [-1, 1, 1]):
                q = Pt - c
                keep |= (np.hypot(q[:, 0], q[:, 2]) < fj["eye_open"]) & (q[:, 1] < 0.01)
    print(f"kept inside (mouth, sockets): {keep.sum()}")
    V, missed = fit(Wd, L, S, prims, meta["voxel"], regions, dom, keep=keep,
                    V_warped=Wd if __import__("os").environ.get("SHAPE_RELAX", "0") == "1" else None)
    V = untangle(V, L, S, prims, meta["voxel"], regions, dom, keep)
    np.savez(Path(out) / "wrapped.npz", verts=V, loops=L, sizes=S)
    f = np.abs(sdf.field_at(prims, V, margin=0.05)) * 1000
    print(f"wrapped {len(V)} verts; {missed} missed the surface; |field| mean {f.mean():.2f} p95 {np.percentile(f, 95):.2f} max {f.max():.1f} mm")
