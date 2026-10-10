"""creasefit.py <model> [h_mm] [dark]: GNM identity (all 170) + habitual eye-region expression fitted to the CREASE
EVIDENCE on the photo (the line's height over the lash line and its darkness, lidfold.read_lid; Tess: 4.35-5.0 mm,
dark 0.31-0.33), the whole face held by every view's detector points (lipfit.point_system) and the M3 prior. Not
lidfold's displacement field (lidgnm.py fit did that: the coordinator / Joe: "a usage problem, not a capability problem").

The crease is read on GNM's RAW head (clay close-up, 0.079 mm/px, lidgnm.shot; no lidfold, no sliders) at the target
height (lidgnm.valleys: the luminance valley depth there, 6 columns). Directions: the posterior-cheapest moves (points +
prior) that deepen a GEOMETRIC groove at that height (second difference of the skin's forward position across the lid,
+-1.5 mm and +-0.8 mm, fixed vertex sets), finite differences on renders along them, Levenberg-Marquardt.
Writes $F/out/lid/creasefit_<model>.png (photo eyes | start | after) and .json."""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HREG", "eyes")
import numpy as np  # noqa: E402

import lipfit as LF  # noqa: E402  (sets headfit.N = 170)
import lidgnm as LG  # noqa: E402
import perc  # noqa: E402
from hifipushie import humanfit, humanfit_map as hm, lidfold, likeness, store  # noqa: E402

F = Path(os.environ.get("F", "/mnt/data/hifipushie/faces5"))
model = sys.argv[1]
H_MM = float(sys.argv[2]) if len(sys.argv) > 2 else 4.7
DARK = float(sys.argv[3]) if len(sys.argv) > 3 else 0.31
ROUNDS = int(os.environ.get("ROUNDS", "4"))
NC, NH = LF.NC, LF.NH
spec = store.load(model)
refs = json.loads((store.HOME / model / "human_refs.json").read_text())
views = [dict(v) for v in refs["views"]]
cams = [dict(cm) for cm in refs["cameras"]]
Pinv = LF.prior_inv()


def raw_V(z):
    c = np.zeros(len(perc.ID_NAMES))
    c[LF.HC] = z[:NC]
    return LF.TPL + np.tensordot(z[:NC], LF.IB, 1) + np.tensordot(z[NC:], LF.EB, 1)


def feats(z):
    im, P = LG.shot(raw_V(z))
    return LG.valleys(im, P, H_MM), im, P


def groove_sets(z):
    """per column (both eyes x 3 thirds) vertex triples (below, at, above the target height; +-W mm) on the raw head's
    front lid skin, for W in (1.5, 0.8)."""
    V = raw_V(z)
    W_ = perc.world(V)
    X = lambda ids: (W_[LG.VID[ids]] * LG.W[ids][..., None]).sum(1)  # noqa: E731
    nrm = LG.normals(V)
    cand = np.flatnonzero(perc.EXT & (nrm[:, 2] > 0.3))
    sets = {1.5: [], 0.8: []}
    for s_ in (0, 1):
        rim = X(list(lidfold.UPPER[s_]))
        o = np.argsort(rim[:, 0])
        xi, xo = X([lidfold.INNER[s_]])[0, 0], X([lidfold.OUTER[s_]])[0, 0]
        for f in (0.25, 0.5, 0.75):
            x = xi + f * (xo - xi)
            zl = np.interp(x, rim[o, 0], rim[o, 2])
            for wd in sets:
                tri = []
                for dh in (-wd, 0.0, wd):
                    tgt = np.array([x, zl + (H_MM + dh) * 1e-3])
                    d = np.hypot(W_[cand, 0] - tgt[0], W_[cand, 2] - tgt[1])
                    near = cand[d < 0.0012]
                    j = near[np.argmin(W_[near, 1])] if len(near) else cand[np.argmin(d)]   # front-most (world -Y)
                    tri.append(j)
                sets[wd].append(tri)
    return sets


def groove_jac(sets):
    """(2, n): d(groove)/dz, groove = mean over columns of fwd(below) + fwd(above) - 2 fwd(at) (GNM frame z forward:
    + = the middle sits back = a groove), for the two widths."""
    Bz = np.concatenate([LF.IB, LF.EB])[:, :, 2]
    out = []
    for wd in (1.5, 0.8):
        t = np.array(sets[wd])
        out.append((Bz[:, t[:, 0]] + Bz[:, t[:, 2]] - 2 * Bz[:, t[:, 1]]).mean(1))
    return np.array(out)


def main():
    from PIL import Image, ImageDraw
    z0 = np.r_[LF.humanfit.identity(spec["base"]), LF.h_of(spec)]
    # the photo's own read (front view, iris scale) for the record
    v0 = refs["views"][0]
    ph = Image.open(v0["image"]).convert("RGB")
    Pp = likeness.detect([ph])[0]
    rph = lidfold.read_lid(ph, np.asarray(Pp, float)[:, :2])
    print("photo read_lid mid columns:", [(c["tps"], c["dark"]) for eye in rph for c in eye], flush=True)
    # (a) the points (the face held as the pictures show it)
    z = z0.copy()
    rviews = None
    for it in range(2):
        st = humanfit.state(LF.spec_with(spec, z[:NC], z[NC:])["base"])
        if rviews is None:
            rviews = hm._resolve(st, views)
        for _ in range(3):
            H, b, cost, rms = LF.point_system(st, rviews, cams, z, z)
            z = np.linalg.solve(H + Pinv, b)
        print(f"(a) {it}: points rms {np.round(rms, 2).tolist()} prior {float(z @ Pinv @ z):.1f}", flush=True)
    Hp = H + Pinv
    f, im0, P0 = feats(z)
    za = z.copy()
    r0 = lidfold.read_lid(im0, P0, LG.MMPX)
    print("after (a): valleys at", H_MM, "mm", f.round(3), "| read_lid", LG.summary(r0)["tps"], LG.summary(r0)["dark"], flush=True)
    W = 1 / 0.05
    lam = 1e-3
    hist = []
    for rnd in range(ROUNDS):
        sets = groove_sets(z)
        Jg = groove_jac(sets)
        D = np.linalg.solve(Hp, Jg.T)
        D /= np.sqrt(np.einsum("ij,jk,ki->i", D.T, Hp, D))[None, :]
        step = 2.0
        Jf = np.zeros((6, D.shape[1]))
        for j in range(D.shape[1]):
            Jf[:, j] = (feats(z + step * D[:, j])[0] - f) / step
        gq = D.T @ (Hp @ z - b)
        A = W ** 2 * Jf.T @ Jf + D.T @ Hp @ D + lam * np.eye(D.shape[1])
        rhs = W ** 2 * Jf.T @ (DARK - f) - gq
        a = np.linalg.solve(A, rhs)
        zn = z + D @ a
        fn, imn, Pn = feats(zn)
        cost_old = W ** 2 * np.sum((DARK - f) ** 2) + float(z @ Hp @ z - 2 * b @ z)
        cost_new = W ** 2 * np.sum((DARK - fn) ** 2) + float(zn @ Hp @ zn - 2 * b @ zn)
        print(f"round {rnd}: dvalley/ddir {Jf.mean(0).round(4)} groove/unit {(Jg @ D).diagonal().round(5) * 1e3} mm | a "
              f"{a.round(2)} | valleys {fn.round(3)} | cost {cost_old:.1f} -> {cost_new:.1f}", flush=True)
        if cost_new < cost_old:
            z, f = zn, fn
        else:
            lam *= 10
        hist.append({"round": rnd, "valleys": f.tolist(), "a": a.tolist()})
    st = humanfit.state(LF.spec_with(spec, z[:NC], z[NC:])["base"])
    _, _, _, rms_b = LF.point_system(st, rviews, cams, z, z)
    _, imf, Pf = feats(z)
    rf = lidfold.read_lid(imf, Pf, LG.MMPX)
    rep = {"photo": [(c["tps"], c["dark"]) for eye in rph for c in eye], "after_a": LG.summary(r0), "final": LG.summary(rf),
           "points_rms_final": rms_b, "maha_c_a": float(np.sqrt(za[:NC] @ Pinv[:NC, :NC] @ za[:NC])),
           "maha_c": float(np.sqrt(z[:NC] @ Pinv[:NC, :NC] @ z[:NC])), "move_maha": float(np.sqrt((z - za) @ Hp @ (z - za))),
           "h": z[NC:].round(3).tolist(), "hist": hist}
    print(json.dumps({k: rep[k] for k in ("photo", "after_a", "final", "points_rms_final", "maha_c_a", "maha_c", "move_maha")},
                     default=float))
    np.save(F / "out" / "lid" / f"creasefit_{model}.npy", z)
    (F / "out" / "lid" / f"creasefit_{model}.json").write_text(json.dumps(rep, default=float))
    # sheet: the photo's eyes (cropped to the same span) | start (a) | after
    ex = np.asarray(Pp, float)[[33, 263], :2]
    cx, cy = ex.mean(0)
    half = 1.25 * abs(ex[1, 0] - ex[0, 0]) / 2 * 1.4
    pc = ph.crop((int(cx - half), int(cy - half / 2), int(cx + half), int(cy + half / 2))).resize((1400, 700))
    tiles = [(pc, "photo"), (LG.annotate(im0, P0, r0, f"after the points fit (GNM, raw head): tps {LG.summary(r0)['tps']:.1f} dark {LG.summary(r0)['dark']:.2f}"), ""),
             (LG.annotate(imf, Pf, rf, f"fitted to the crease evidence: tps {LG.summary(rf)['tps']:.1f} dark {LG.summary(rf)['dark']:.2f}"), "")]
    out = Image.new("RGB", (700, 350 * 3), "white")
    for i, (t, lab) in enumerate(tiles):
        out.paste(t.convert("RGB").resize((700, 350)), (0, 350 * i))
        if lab:
            ImageDraw.Draw(out).text((6, 350 * i + 4), lab, fill=(0, 0, 0))
    p = F / "out" / "lid" / f"creasefit_{model}.png"
    out.save(p)
    print("wrote", p)


if __name__ == "__main__":
    main()
