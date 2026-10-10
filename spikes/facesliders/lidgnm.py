"""lidgnm.py [density|scan|fit|sheet]: can GNM's identity space make the upper-lid crease we built lidfold for? (faces5;
Joe on f4_10: "It looks like GNM was able to do the eye crease the whole time?")

GNM's raw head (no one-mesh build, no lidfold, no sliders), clay (likeness.render, smooth normals, key upper left), a
close-up of both eyes at ~0.08 mm/px. The 478 detector points come from the calibrated table (humanfit_map,
mp478_gnm.npz: where MediaPipe puts each point on GNM's surface, front class), projected through the same camera, so
lidfold.read_lid reads every render the same way (no detector noise).

  density  rows of GNM vertices across the upper lid (lash line -> brow) at the inner / middle / outer third
  scan     read_lid at -3 / 0 / +3 sd along every one of GNM's 170 components and ICT's 100 carried modes (mean head),
           and Tess's / Garrett's identities: tps (visible line over the lash line, mm), dark (0..1)
  fit      lidfold's crease (profile across a line at crease_height over the upper rim, along the normals; Tess's and
           Garrett's fold parameters) as a GNM displacement over the orbit, MAP-fitted by the 170 comps: the share made,
           the cost (sd), and read_lid on the result
  sheet    crops (human_renders/f5_lid_*.png)
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import perc
from hifipushie import humanfit, humanfit_map, lidfold, likeness, store

F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces5"))
OUT = F / "out" / "lid"
OUT.mkdir(parents=True, exist_ok=True)
R = Path("/home/joe/dev/hifipushie/workspace/human_renders")
PX = 1400
HALF = 0.055         # m: half the frame width (both eyes, outer corners in)
TAB = humanfit_map.table()
VID, W = TAB["vid"][0], TAB["w"][0]
N = perc.N
IB = perc.IB
NAMES = perc.ID_NAMES
HC = [i for i, x in enumerate(NAMES) if x.startswith("head")]
MMPX = 2 * HALF * 1000 / PX


def cam_for(Ww):
    L = perc.WLM @ Ww
    cen = L[36:48].mean(0)
    return {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.8], "f": PX / 2 * 0.8 / HALF, "size": [PX, PX],
            "centre": list(map(float, cen)), "yaw": 0.0}


def shot(V):
    """(image (PX x PX/2 band around the eyes), 478 points in its pixels)."""
    Ww = perc.world(V)
    cam = cam_for(Ww)
    mesh = {"V": Ww, "F": perc.F_SKIN, "eyes": [(Ww, f, col) for f, col in perc.EYE_PARTS], "L": perc.WLM @ Ww}
    y0 = PX // 4
    im, _ = likeness.render(mesh, cam, (0, y0, PX, y0 + PX // 2), px=PX, brows=False)
    X = (Ww[VID] * W[..., None]).sum(1)
    P = humanfit.project(cam, X)[:, :2] - np.array([0, y0])
    return im, P


def read(V):
    im, P = shot(V)
    r = lidfold.read_lid(im, P, MMPX)
    return im, P, r


def summary(r):
    """mid columns of both eyes: tps mean, dark mean; plus all 6 columns."""
    cols = [c for eye in r for c in eye]
    mids = [eye[1] for eye in r]
    t = [c["tps"] for c in mids if np.isfinite(c["tps"])]
    return {"tps": float(np.mean(t)) if t else float("nan"), "dark": float(np.mean([c["dark"] for c in mids])),
            "cols": [(c["tps"], c["dark"]) for c in cols]}


def c_of(model):
    if model == "mean":
        return np.zeros(len(NAMES))
    return perc.head(model)


def density():
    V = perc.verts(np.zeros(len(NAMES)))
    Ww = perc.world(V)
    X = lambda ids: (Ww[VID[ids]] * W[ids][..., None]).sum(1)  # noqa: E731
    ext = perc.EXT
    for s, side in ((0, "R"), (1, "L")):
        up = X(list(lidfold.UPPER[s]))
        brow = X(list(lidfold.BROW_LOW[s]))
        for f, nm in ((0.25, "inner"), (0.5, "mid"), (0.75, "outer")):
            # interpolate lid / brow points at that fraction across (x)
            xi, xo = X([lidfold.INNER[s]])[0, 0], X([lidfold.OUTER[s]])[0, 0]
            x = xi + f * (xo - xi)
            zl = np.interp(x, *zip(*sorted(zip(up[:, 0], up[:, 2]))))
            zb = np.interp(x, *zip(*sorted(zip(brow[:, 0], brow[:, 2]))))
            # the section of the skin by the vertical plane at x: every exterior quad edge crossing it; the front
            # sheet only (per crossing, nothing else within 0.6 mm of height lies more than 1 mm in front of it)
            q = perc.Q[ext[perc.Q].all(1)]
            e = np.unique(np.sort(np.r_[q[:, [0, 1]], q[:, [1, 2]], q[:, [2, 3]], q[:, [3, 0]]], 1), axis=0)
            a, b = Ww[e[:, 0]], Ww[e[:, 1]]
            s_ = (x - a[:, 0]) / np.where(np.abs(b[:, 0] - a[:, 0]) < 1e-12, 1e-12, b[:, 0] - a[:, 0])
            ok = (s_ >= 0) & (s_ <= 1)
            Pc = a[ok] + s_[ok, None] * (b[ok] - a[ok])
            Pc = Pc[(Pc[:, 2] > zl - 0.0005) & (Pc[:, 2] < zb + 0.001)]
            Pc = Pc[Pc[:, 1] < Pc[:, 1].min() + 0.03]   # the face, not the back of the head
            front = np.array([p for p in Pc if not np.any((np.abs(Pc[:, 2] - p[2]) < 0.0006) & (Pc[:, 1] < p[1] - 0.001))])
            z = np.sort(front[:, 2]) * 1e3
            seg = np.linalg.norm(np.diff(front[np.argsort(front[:, 2])][:, 1:], axis=0), axis=1) * 1e3
            print(f"eye {side} {nm:5s}: lash -> brow {1e3 * (zb - zl):5.1f} mm, edge crossings (rows) {len(z):3d}, "
                  f"segment along the skin median {np.median(seg):.2f} max {seg.max():.2f} mm")


def scan():
    rows = []
    c0 = np.zeros(len(NAMES))
    _, _, r0 = read(perc.verts(c0))
    base = summary(r0)
    rows.append({"name": "mean", "0": base})
    print("mean", base, flush=True)
    for nm in ("tess", "garrett"):
        s = summary(read(perc.verts(c_of(nm)))[2])
        rows.append({"name": nm, "0": s})
        print(nm, s, flush=True)
    for i in HC:
        e = np.zeros(len(NAMES))
        e[i] = 3.0
        sp, sm = summary(read(perc.verts(c0 + e))[2]), summary(read(perc.verts(c0 - e))[2])
        rows.append({"name": NAMES[i], "+3": sp, "-3": sm})
        print(NAMES[i], "+3", round(sp["tps"], 2), round(sp["dark"], 3), "-3", round(sm["tps"], 2), round(sm["dark"], 3),
              flush=True)
    M = np.load(F / "out" / "ict_modes.npz")["modes"].astype(float)
    V0 = perc.verts(c0)
    for k in range(len(M)):
        sp, sm = summary(read(V0 + 3 * M[k])[2]), summary(read(V0 - 3 * M[k])[2])
        rows.append({"name": f"ict_{k:02d}", "+3": sp, "-3": sm})
        print(f"ict_{k:02d}", "+3", round(sp["tps"], 2), round(sp["dark"], 3), "-3", round(sm["tps"], 2), round(sm["dark"], 3),
              flush=True)
    (OUT / "scan.json").write_text(json.dumps(rows))


def annotate(im, P, r, label):
    """the crop with the read: lash line points (upper lid), and per column the read line (tps) as a tick."""
    from hifipushie.likeness_eyes import frame
    im = im.convert("RGB").copy()
    d = ImageDraw.Draw(im)
    for s in (0, 1):
        for i in lidfold.UPPER[s]:
            x, y = P[i]
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(40, 120, 255))
    ex, ey = frame(P)
    ex, ey = np.asarray(ex, float), np.asarray(ey, float)
    for s in (0, 1):
        pi, po = P[lidfold.INNER[s]], P[lidfold.OUTER[s]]
        span = float((po - pi) @ ex)
        for f, col in zip((0.25, 0.5, 0.75), r[s]):
            if not np.isfinite(col["tps"]):
                continue
            lid = lidfold._interp_curve(P, lidfold.UPPER[s], f * span, ex, ey, pi)
            q = pi + f * span * ex + (lid - col["tps"] / MMPX) * ey
            a, b = q - 6 * ex, q + 6 * ex
            d.line([tuple(a), tuple(b)], fill=(255, 40, 40) if col["dark"] > 0.12 else (255, 190, 0), width=2)
    d.text((8, 6), label, fill=(0, 0, 0))
    return im


def sheet_rows(rows, path, ncol=3, scale=0.5):
    """rows: list of (label, V). A grid of annotated crops."""
    ims = []
    for label, V in rows:
        im, P, r = read(V)
        s = summary(r)
        ims.append(annotate(im, P, r, f"{label}  tps {s['tps']:.1f} mm dark {s['dark']:.2f}"))
    w, h = int(ims[0].width * scale), int(ims[0].height * scale)
    nrow = (len(ims) + ncol - 1) // ncol
    out = Image.new("RGB", (w * ncol, h * nrow), (255, 255, 255))
    for k, im in enumerate(ims):
        out.paste(im.resize((w, h), Image.LANCZOS), ((k % ncol) * w, (k // ncol) * h))
    out.save(path)
    print("wrote", path)


def normals(V):
    q = perc.Q
    fn = np.cross(V[q[:, 2]] - V[q[:, 0]], V[q[:, 3]] - V[q[:, 1]])
    vn = np.zeros_like(V)
    for k in range(4):
        np.add.at(vn, q[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)


def fold_field(c, fold, sex=0.0):
    """(N, 3) GNM-frame displacement: lidfold's profile across a crease line at crease_height (mm, front plane) over
    the upper rim (the calibrated detector points' upper-lid arc), along the skin's normals, faded at the ends as
    lidfold fades them. A stand-in for mod_fold on GNM's own mesh (the vertical front-plane distance as t)."""
    cfg = {**lidfold.DEFAULTS, "crease_height": 4.0 - sex}
    cfg.update(fold)
    V = perc.verts(c)
    Ww = perc.world(V)
    nrm = normals(V)
    X = lambda ids: (Ww[VID[ids]] * W[ids][..., None]).sum(1)  # noqa: E731
    D = np.zeros_like(V)
    MM = 0.001
    for s in (0, 1):
        rim = X(list(lidfold.UPPER[s]))
        o = np.argsort(rim[:, 0])
        xs, zs = rim[o, 0], rim[o, 2]
        xi, xo = X([lidfold.INNER[s]])[0, 0], X([lidfold.OUTER[s]])[0, 0]
        lo, hi = min(xi, xo), max(xi, xo)
        x = Ww[:, 0]
        u = np.clip((x - xi) / (xo - xi), -0.2, 1.2)        # 0 inner .. 1 outer
        hfac = np.interp(u, [0, 0.25, 0.5, 0.75, 1], [cfg["inner"], cfg["inner"], 1, cfg["outer"], cfg["outer"]])
        zline = np.interp(x, xs, zs) + cfg["crease_height"] * MM * hfac
        ei = np.clip((u - cfg["start"]) / cfg["fade_inner"], 0, 1)
        eo = np.clip((1.0 + cfg["outer_reach"] * MM / abs(xo - xi) - u) / cfg["fade_outer"], 0, 1)
        e = np.minimum(ei, eo)
        taper = e * e * e * (e * (6 * e - 15) + 10)
        t = Ww[:, 2] - zline
        m = perc.EXT & (x > lo - 0.004) & (x < hi + 0.004) & (np.abs(t) < 0.009) & (nrm[:, 2] > 0.2)
        n = int(m.sum())
        pr = {"G": np.full(n, cfg["crease_depth"] * MM), "sg": cfg["crease_width"] * MM / 2.355 * (0.5 + 0.5 * taper[m]),
              "O": np.full(n, cfg["fold_overhang"] * MM), "so": np.full(n, cfg["fold_width"] * MM),
              "Pl": np.full(n, cfg["platform"] * MM),
              "ph": np.full(n, max(cfg["crease_height"] * MM - 0.8 * MM, 0.5 * MM))}
        amp = lidfold.profile(t[m], pr, np.arange(n)) * taper[m]
        D[m] += amp[:, None] * nrm[m]
    return D


def fit(prior=None):
    """lidfold's fold (Tess's, Garrett's parameters) on their own identities as a target; GNM's 170 comps fitted to it
    over both orbits (MAP, noise NOISE; prior = None: GNM's N(0, I), else a (170, 170) covariance), and with no prior
    (the span alone). Reports the share made and the cost; renders target / GNM's best for the sheet."""
    noise = float(os.environ.get("NOISE", "0.00005"))
    orb = np.zeros(N, bool)
    for k in ("left_orbital_region", "right_orbital_region", "left_brow_region", "right_brow_region"):
        orb |= perc.grp(k)
    orb &= perc.EXT
    B = IB[HC][:, orb].reshape(len(HC), -1)
    Sig = np.eye(len(HC)) if prior is None else prior
    folds = {"tess": ({"crease_height": 4.233, "crease_width": 1.0, "crease_depth": 0.6, "fold_overhang": 0.4,
                       "inner": 0.95, "outer": 1.0}, 0.0),
             "garrett": ({"crease_height": 3.0, "crease_depth": 0.6, "crease_width": 1.1, "fold_overhang": 0.8,
                          "fold_width": 3.0}, 1.0)}
    rows, res = [], {}
    for who, (fold, sex) in folds.items():
        c0 = c_of(who)
        D = fold_field(c0, fold, sex)
        y = D[orb].ravel()
        out = {"rms": float(np.sqrt(np.mean(np.sum(D[orb] ** 2, 1)[np.linalg.norm(D[orb], axis=1) > 1e-6]))) * 1e3,
               "max": float(np.abs(D).max() * 1e3)}
        # the span alone (least squares) and the MAP under the prior
        cl = np.linalg.lstsq(B.T, y, rcond=None)[0]
        cm = Sig @ np.linalg.solve(B @ B.T @ Sig + noise ** 2 * np.eye(len(HC)), B @ y)   # (B B^T + s^2 Sig^-1) c = B y
        for nm, cc in (("span", cl), ("map", cm)):
            r = y - B.T @ cc
            out[nm] = {"share": float(1 - r @ r / (y @ y)), "maha": float(np.sqrt(cc @ np.linalg.solve(Sig, cc))),
                       "max_sd": float(np.abs(cc).max())}
        res[who] = out
        print(who, json.dumps(out), flush=True)
        cfull = np.zeros(len(NAMES))
        cfull[HC] = cm
        rows += [(f"{who}: GNM identity (no fold)", perc.verts(c0)), (f"{who}: + lidfold's fold (target)", perc.verts(c0) + D),
                 (f"{who}: + GNM's best MAP of it ({out['map']['share']:.2f} made, {out['map']['maha']:.1f} sd)",
                  perc.verts(c0 + cfull))]
    return rows, res


def quick():
    rows = [(nm, perc.verts(c_of(nm))) for nm in ("mean", "tess", "garrett")]
    sheet_rows(rows, OUT / "quick.png", ncol=1, scale=0.8)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "density"
    if what == "samples":   # samples <prior npz> <n> <out png>: random identities from a prior, lid crops + reads
        z = np.load(sys.argv[2])
        S = z["cov"][:len(HC), :len(HC)]
        w, Vv = np.linalg.eigh(S)
        A = Vv * np.sqrt(np.maximum(w, 0))
        rng = np.random.default_rng(1)
        rows, reads = [], []
        for k in range(int(sys.argv[3])):
            c = np.zeros(len(NAMES))
            c[HC] = A @ rng.standard_normal(len(HC))
            V = perc.verts(c)
            rows.append((f"prior sample {k}", V))
            reads.append(summary(read(V)[2]))
        print("tps", [round(r["tps"], 2) for r in reads], "dark", [round(r["dark"], 3) for r in reads])
        sheet_rows(rows, sys.argv[4], ncol=2, scale=0.5)
    elif what == "sheet":   # sheet <out png> <item>...: item = mean | tess | garrett | head_NNN:+3 | ict_NN:-3
        M = None
        rows = []
        for it in sys.argv[3:]:
            nm, _, a = it.partition(":")
            if nm.startswith("ict_"):
                if M is None:
                    M = np.load(F / "out" / "ict_modes.npz")["modes"].astype(float)
                rows.append((f"ICT mode {nm[4:]} at {a} sd", perc.verts(np.zeros(len(NAMES))) + float(a) * M[int(nm[4:])]))
            elif nm.startswith("head_"):
                c = np.zeros(len(NAMES))
                c[NAMES.index(nm)] = float(a)
                rows.append((f"GNM {nm} at {a} sd", perc.verts(c)))
            else:
                rows.append((f"{nm} (identity only, raw GNM)", perc.verts(c_of(nm))))
        sheet_rows(rows, sys.argv[2], ncol=2, scale=0.6)
    elif what == "fit":
        pp = os.environ.get("PRIOR")
        rows, res = fit(None if not pp else np.load(pp)["cov"][:len(HC), :len(HC)])
        suf = "" if not pp else "_" + Path(pp).stem
        (OUT / f"fit{suf}.json").write_text(json.dumps(res))
        sheet_rows(rows, OUT / f"fit{suf}.png", ncol=3, scale=0.5)
    else:
        {"density": density, "scan": scan, "quick": quick}[what]()
