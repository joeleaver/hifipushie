"""sheet04.py: workspace/human_renders/hb_04_pose_after_weights_fix.png: the posed neck (head turned 45, neck bent 35)
on the exported GLBs, REFERENCE | NOW (after the faceshapes fix: raking, shaded) | BEFORE (raking), and the Head /
Neck / Spine2 weight profile down the neck."""
import os, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import asset, render, resources, rig as rigmod, rig_audit, store

D = "/mnt/data/hifipushie/headbody"
REF = "/home/joe/dev/hifipushie/workspace/neck_refs"
F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)  # noqa: E731
P_ = rigmod.PREFIX
UP = [0.0, 0.0, 1.0]
POSES = [("HEAD TURNED 45", {P_ + "Neck": (UP, 15.0), P_ + "Head": (UP, 30.0)}),
         ("NECK BENT 35 (looking up)", {P_ + "Neck": ([1.0, 0, 0], -20.0), P_ + "Head": ([1.0, 0, 0], -15.0)})]
VIEWS = [("front", 0), ("side", 90), ("back", 180)]
T_ = 400


def mats(bones, turns):
    M = np.tile(np.eye(4), (len(bones), 1, 1))
    for i, b in enumerate(bones):
        L = np.eye(4)
        if b["name"] in turns:
            ax, deg = turns[b["name"]]
            ax = np.asarray(ax, float) / np.linalg.norm(ax)
            t = np.radians(deg)
            K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
            R = np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * K @ K
            h = np.asarray(b["head"], float)
            L[:3, :3], L[:3, 3] = R, h - R @ h
        M[i] = (M[b["parent"]] if b["parent"] >= 0 else np.eye(4)) @ L
    return M


def skin(m, M):
    V4 = np.c_[m["V"], np.ones(len(m["V"]))]
    P, N = np.zeros((len(V4), 3)), np.zeros((len(V4), 3))
    for c in range(m["J"].shape[1]):
        Tc = M[m["J"][:, c]]
        P += m["W"][:, c:c + 1] * np.einsum("nij,nj->ni", Tc, V4)[:, :3]
        N += m["W"][:, c:c + 1] * np.einsum("nij,nj->ni", Tc[:, :3, :3], m["N"])
    return P, N / (np.linalg.norm(N, axis=1, keepdims=True) + 1e-12)


def load(glb):
    g = rig_audit.read_glb(glb)
    ms = [m for k, m in g["meshes"].items() if k.split("_")[-1] in ("head", "body", "top")]
    return g["bones"], ms


def profile(glb):
    bones, ms = load(glb)
    names = [b["name"].split(":")[-1] for b in bones]
    V = np.concatenate([m["V"] for m in ms[:2]])
    J = np.concatenate([m["J"] for m in ms[:2]]); W = np.concatenate([m["W"] for m in ms[:2]])
    Dn = np.zeros((len(V), len(names)))
    for k in range(4):
        np.add.at(Dn, (np.arange(len(V)), J[:, k]), W[:, k])
    nk, hd = np.asarray(bones[names.index("Neck")]["head"]), np.asarray(bones[names.index("Head")]["head"])
    out = []
    for lo in np.arange(hd[2] + 0.02, nk[2] - 0.13, -0.02):
        s = (V[:, 2] < lo) & (V[:, 2] >= lo - 0.02) & (np.linalg.norm(V[:, :2] - nk[:2], axis=1) < 0.11)
        if s.sum() > 5:
            h = Dn[s][:, names.index("Head")]
            out.append((1e3 * (lo - 0.01 - nk[2]), int(s.sum()), h.mean(), h.min(), h.max(), Dn[s][:, names.index("Neck")].mean(), Dn[s][:, names.index("Spine2")].mean()))
    return out, 1e3 * (hd[2] - nk[2])


def tiles(glb, shaded):
    bones, ms = load(glb)
    names = [b["name"] for b in bones]
    c = 0.5 * (np.asarray(bones[names.index(P_ + "Neck")]["head"], float) + np.asarray(bones[names.index(P_ + "Head")]["head"], float)) - [0, 0, 0.03]
    rak = str(render.raking_matcap(store.HOME / "raking_matcap.png"))
    out = {}
    for pname, turns in POSES:
        M = mats(bones, turns)
        Vs, Ns, Fs, off = [], [], [], 0
        for m in ms:
            P, N = skin(m, M)
            Vs.append(P); Ns.append(N); Fs.append(m["F"] + off); off += len(P)
        V, N, Fc = np.concatenate(Vs), np.concatenate(Ns), np.concatenate(Fs)
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "posed.npz"
            np.savez(f, verts=V.astype(np.float32), faces=Fc, normals=N.astype(np.float32))
            frames = render.view_frames(V, [v for v, _ in VIEWS], focus=c, zoom=1.0)
            for fr in frames:
                fr["scale"] = 0.36
            out[(pname, "raking")] = [im.convert("RGB").resize((T_, T_)) for im in render.render_views(f, frames, T_, rak)]
        if shaded:
            one = {"turns": {k: [*(float(x) for x in v[0]), float(v[1])] for k, v in turns.items()}}
            cams = [{"eye": (c + 1.5 * np.array([np.sin(np.radians(az)), -np.cos(np.radians(az)), 0.03])).tolist(), "target": c.tolist(), "fov": 14.0, "name": v} for v, az in VIEWS[:2]]
            sh = asset.preview(Path(glb), [], size=T_, samples=32, poses=[one], cameras=cams)[0].convert("RGB")
            out[(pname, "shaded")] = sh
    return out


def fit(path, w, h, box=None):
    im = Image.open(path).convert("RGB")
    if box:
        W_, H_ = im.size
        im = im.crop((int(box[0] * W_), int(box[1] * H_), int(box[2] * W_), int(box[3] * H_)))
    k = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * k + 1), int(im.height * k + 1)))
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


BL = [("TESS", "tess", {"HEAD TURNED 45": ("Young_woman_s_neck.jpg", None), "NECK BENT 35 (looking up)": ("Female_neck.jpg", (0.05, 0, 0.8, 1))}),
      ("GARRETT", "garrett", {"HEAD TURNED 45": ("Adam_s_apple_35.jpg", (0, 0, 0.75, 1)), "NECK BENT 35 (looking up)": ("Gray1195.png", None)})]
RW = 520
BW = RW + 3 * T_ + 20
BH = 70 + 3 * T_ + 30
sheet = Image.new("RGB", (2 * BW + 30, 90 + len(BL) * BH), (250, 250, 250))
dr = ImageDraw.Draw(sheet)
dr.text((20, 14), "POSED NECK after the face-shape / Head-weight fix:  REFERENCE | NOW raking | NOW shaded | BEFORE the fix (raking).  No rig.py change yet.", font=F(30), fill=(0, 0, 0))
with resources.heavy("headbody pose sheet", gb=8):
    for bi_, (who, tag, refs) in enumerate(BL):
        now = tiles(f"{D}/export_{tag}/hb_{tag}.glb", True)
        bef = tiles(f"{D}/export_{tag}_before/hb_{tag}.glb", False)
        for pi, (pname, _) in enumerate(POSES):
            x0, y0 = 15 + pi * BW, 90 + bi_ * BH
            dr.text((x0, y0 + 8), f"{who}: {pname}", font=F(34), fill=(0, 0, 0))
            rf, box = refs[pname]
            sheet.paste(fit(f"{REF}/{rf}", RW, 3 * T_, box), (x0, y0 + 60))
            dr.text((x0 + 6, y0 + 64), f"REFERENCE ({rf[:26]})", font=F(18), fill=(255, 220, 0))
            for vi in range(3):
                sheet.paste(now[(pname, "raking")][vi], (x0 + RW + vi * T_, y0 + 60))
                sheet.paste(bef[(pname, "raking")][vi], (x0 + RW + vi * T_, y0 + 60 + 2 * T_))
            sh = now[(pname, "shaded")]
            sh = sh.resize((3 * T_, int(3 * T_ * sh.height / sh.width)))
            sheet.paste(sh.crop((0, 0, 3 * T_, T_)), (x0 + RW, y0 + 60 + T_))
            for ri, lab in enumerate(("NOW raking (front / side / back)", "NOW shaded (front / side)", "BEFORE the fix, raking")):
                dr.text((x0 + RW + 8, y0 + 64 + ri * T_), lab, font=F(20), fill=(255, 220, 0))
sheet.save("/home/joe/dev/hifipushie/workspace/human_renders/hb_04_pose_after_weights_fix.png")
for who, tag, _ in BL:
    for lab, d_ in (("NOW", ""), ("BEFORE", "_before")):
        pr, nl = profile(f"{D}/export_{tag}{d_}/hb_{tag}.glb")
        print(f"{who} {lab}: Head weight down the neck (mm above the Neck joint; Head joint at +{nl:.0f}): " + "; ".join(f"{z:+.0f}: {h:.2f} [{lo:.2f}-{hi:.2f}] N {n_:.2f} S2 {s2:.2f}" for z, c_, h, lo, hi, n_, s2 in pr))
print("saved")
