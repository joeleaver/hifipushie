"""Hypothesis a: macro sliders as calibrated directions in the identity space. The calibration table, each macro's
check (does the head's measure follow the slider, how far before the mesh breaks, what else moves) and sheets.
  run.sh macros.py [sheet]"""
import sys

import numpy as np
from PIL import Image, ImageDraw

import rs
from hifipushie import humanmacro as hm


def check():
    t = hm.table()
    print(f"{'macro':16s} {'unit':5s} {'mean':>8s} {'pop sd':>8s} {'linear r2':>9s} | slider -2 / +2 -> measure (sigma) | sound to -/+ | goes with it (r)")
    for i, k in enumerate(hm.NAMES):
        got = [hm.read(hm.apply(None, {k: z}))[k] for z in (-2, 2)]
        lim = []
        for sgn in (-1, 1):
            ok = 0.0
            for z in (1, 2, 3, 4, 5, 6):
                s = hm.soundness(hm.apply(None, {k: sgn * z}))
                if s["flipped"] > 0 or s["squeeze"] < 0.25:
                    break
                ok = z
            lim.append(ok)
        cr = t["corr"][i].copy()
        cr[i] = 0
        top = np.argsort(-np.abs(cr))[:3]
        weak = "WEAK " if k in t["weak"] else ""
        print(f"{k:16s} {hm.MACROS[k][0]:5s} {t['fm'][i]:8.3f} {t['sd'][i]:8.4f} {t['r2'][i]:9.3f} | {got[0]:+5.2f} / {got[1]:+5.2f}"
              f"                 | {lim[0]:.0f} / {lim[1]:.0f}      | {weak}" + ", ".join(f"{hm.NAMES[j]} {cr[j]:+.2f}" for j in top))
    print("\nweak (the identity space barely moves them: a shape op is needed):", t["weak"])
    # how much of a head is said by the macros at all: variance of the vertices explained by the macro subspace
    An = t["A"] / t["sd"][:, None]
    Q = np.linalg.qr(An.T)[0]   # (K, M)
    g = rs.gnm()
    rng = np.random.default_rng(3)
    tot = {r: [] for r in rs.REGIONS}
    for _ in range(40):
        c = rng.normal(0, 1, hm.K)
        V = rs.head(c)
        Vm = rs.head(Q @ (Q.T @ c))
        sc, s0 = rs.score(Vm, V), rs.score(rs.head(), V)
        for r in rs.REGIONS:
            tot[r].append((sc[r], s0[r]))
    print(f"\na head rebuilt from its {len(hm.NAMES)} macros alone vs the mean head (mm, 40 random heads):")
    print("            " + rs.HEADER)
    print("macros only " + " ".join(f"{np.mean([a for a, _ in tot[r]]):5.2f}" for r in rs.REGIONS))
    print("mean head   " + " ".join(f"{np.mean([b for _, b in tot[r]]):5.2f}" for r in rs.REGIONS))


def sheet(names, out, zs=(-2.5, -1.25, 0, 1.25, 2.5), held=False):
    rows = []
    for k in names:
        tiles = []
        for z in zs:
            V = rs.head(hm.apply(None, {k: z}, held=held))
            pair = []
            for yaw in (0.0, 88.0):
                cam = rs.make_cam(rs.head(), yaw=yaw, lens=85, size=(300, 340), fill=0.7)
                img, _ = rs.render(V, cam)
                pair.append(img)
            tiles.append(np.concatenate(pair, 1))
        row = Image.fromarray(np.concatenate(tiles, 1))
        d = ImageDraw.Draw(row)
        d.text((6, 4), f"{k}{' (others held)' if held else ''}: {hm.MACROS[k][1]}   sigma: " + "  ".join(f"{z:+.2f}" for z in zs), fill=(0, 0, 0))
        rows.append(np.asarray(row))
    Image.fromarray(np.concatenate(rows, 0)).save(out)
    print("sheet", out)


if __name__ == "__main__":
    import os
    R = os.environ.get("R", str(rs.D / "out"))
    if len(sys.argv) > 1 and sys.argv[1] == "sheet":
        sheet(["jaw_square", "jaw_width", "jaw_angle", "chin_projection", "chin_width", "chin_cleft"], f"{R}/rs_macros_jaw_chin.png")
        sheet(["nose_length", "nose_projection", "nose_upturn", "nose_width", "bridge_height", "bridge_hump"], f"{R}/rs_macros_nose.png")
        sheet(["face_length", "face_width", "cheek_fullness", "cheekbone_width", "brow_ridge", "eye_depth", "eye_height", "neck_width"], f"{R}/rs_macros_face.png")
        sheet(["jaw_square", "chin_projection", "nose_upturn", "cheek_fullness"], f"{R}/rs_macros_held.png", held=True)
    else:
        check()
