"""Sheets for the report (workspace/human_renders/mm_*).   run.sh pics.py normals | trellis"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import mm
import rs
import tmesh

R = os.environ.get("R", "/home/joe/dev/hifipushie/workspace/human_renders")
FLIP = {"david": (1, -1, -1), "marigold": (1, -1, -1), "moge2": (1, 1, 1)}
S = 300


def ncol(n):
    """Camera-frame normals (x right, y down, z forward) as the usual colours."""
    c = np.stack([n[..., 0], -n[..., 1], -n[..., 2]], -1) * 0.5 + 0.5
    return (np.clip(c, 0, 1) * 255).astype(np.uint8)


def true_normals(it):
    n = mm.vnormals(it["V"]) @ rs.humanfit._cam_rot(it["cam"]).T
    img, zb = rs.render(it["V"], it["cam"], albedo=ncol(n).astype(float), flat=True, bg=128)
    return img, np.isfinite(zb)


def tile(a, label=None):
    im = Image.fromarray(a).convert("RGB").resize((S, S), Image.LANCZOS)
    if label:
        ImageDraw.Draw(im).text((6, 4), label, fill=(255, 255, 0))
    return im


def normals():
    names = ["S1_bignose_front", "O1_mh_heavy_man_tq", "S6_plain_profile", "S3_recedingchin_front", "garrett_front", "garrett_desk"]
    models = ["david", "moge2", "marigold"]
    sheet = Image.new("RGB", (S * 6, S * len(names)), (30, 30, 30))
    for r, n in enumerate(names):
        g = n.startswith("garrett")
        im = np.asarray(Image.open((mm.MM / "img" / f"{n}.png") if g else (mm.SET / f"{n}.png")).convert("RGB"))
        sheet.paste(tile(im, n), (0, r * S))
        if not g:
            it = mm.item(n)
            tn, mask = true_normals(it)
            sheet.paste(tile(tn, "truth normals"), (S, r * S))
        for k, m in enumerate(models):
            p = mm.pred(m, n)
            nm = p["normal"] * np.asarray(FLIP[m], float)
            nm = nm / np.maximum(np.linalg.norm(nm, axis=-1, keepdims=True), 1e-9)
            c = ncol(nm)
            if not g:
                c = np.where(mask[..., None], c, 128)
            sheet.paste(tile(c, {"david": "DAViD (MIT)", "moge2": "MoGe-2 (MIT)", "marigold": "Marigold v1-1"}[m]), ((2 + k) * S, r * S))
        if not g:   # DAViD's angle to truth, 0..30 deg
            tnv = (tn.astype(float) / 255 - 0.5) * 2
            tnv = np.stack([tnv[..., 0], -tnv[..., 1], -tnv[..., 2]], -1)
            p = mm.pred("david", n)["normal"] * np.asarray(FLIP["david"], float)
            ang = np.degrees(np.arccos(np.clip((p * tnv).sum(-1) / np.maximum(np.linalg.norm(tnv, axis=-1), 1e-9), -1, 1)))
            e = np.clip(ang / 30, 0, 1)
            col = np.stack([e, 1 - np.abs(e - 0.5) * 2, 1 - e], -1) * 255
            sheet.paste(tile(np.where(mask[..., None], col, 40).astype(np.uint8), "DAViD error 0..30 deg"), (5 * S, r * S))
    sheet.save(f"{R}/mm_01_normals.png")
    print(f"{R}/mm_01_normals.png")


def ortho(V, F, N, view, box, size=S):
    """A lambert picture of a mesh seen from the front (-y) or the subject's left profile (+x looking -x)."""
    run = rs._C.get("run") or rs.likeness._raster()
    rs._C["run"] = run
    (x0, x1), (z0, z1) = box
    sc = size / max(x1 - x0, z1 - z0)
    if view == "front":
        u, d, key = V[:, 0], V[:, 1], np.array([-0.4, -0.75, 0.5])
    else:
        u, d, key = -V[:, 1], -V[:, 0], np.array([0.75, -0.4, 0.5])
    px = (u - x0) * sc
    py = (z1 - V[:, 2]) * sc
    sh = 0.25 + 0.75 * np.clip(N @ (key / np.linalg.norm(key)), 0, 1)
    C = np.tile(sh[:, None] * 215, (1, 3))
    img = np.full((size, size, 3), 30.0)
    zb = np.full((size, size), np.inf)
    run(px.copy(), py.copy(), (d - d.min() + 1.0).copy(), np.ascontiguousarray(F.astype(np.int64)), np.ascontiguousarray(C), size, size, img, zb)
    return img.astype(np.uint8)


def profile_line(V, zs, half=0.004):
    """The mid-line's most forward point per height: the profile a side view draws (m)."""
    m = np.abs(V[:, 0]) < half
    out = np.full(len(zs), np.nan)
    b = np.digitize(V[m, 2], zs)
    y = V[m, 1]
    for i in range(1, len(zs)):
        k = b == i
        if k.any():
            out[i] = y[k].min()
    return out


def trellis(names=None, out="mm_02_trellis"):
    g = rs.gnm()
    names = names or ["S1_bignose_front", "S6_plain_front", "O1_mh_heavy_man_front", "O2_mh_old_woman_tq", "O1_mh_heavy_man_profile"]
    names = [n for n in names if (tmesh.TR / f"{n}.npz").exists()]
    sheet = Image.new("RGB", (S * 6, S * len(names)), (30, 30, 30))
    for r, n in enumerate(names):
        it = mm.item(n)
        Vt = it["V"]
        me = tmesh.Mesh(n)
        tmesh.align(me, Vt)
        MV, MN = me.placed()
        L = rs.landmarks(Vt)
        zc = L[27, 2] - 0.03
        box_f = ((-0.15, 0.15), (zc - 0.15, zc + 0.15))
        yc = Vt[g["regions"]["head"], 1].mean()
        box_p = ((-(yc + 0.15), -(yc - 0.15)), (zc - 0.15, zc + 0.15))
        sheet.paste(tile(mm.image(n), n), (0, r * S))
        sheet.paste(tile(ortho(MV, me.F, MN, "front", box_f), "generated mesh, front"), (S, r * S))
        sheet.paste(tile(ortho(MV, me.F, MN, "profile", box_p), "generated mesh, profile"), (2 * S, r * S))
        T = g["T"][g["ext"][g["T"]].all(1)]
        sheet.paste(tile(ortho(Vt, T, mm.vnormals(Vt), "profile", box_p), "TRUE head, profile"), (3 * S, r * S))
        # profile lines: truth (white), mesh (orange), mean head (blue)
        f = g["regions"]["face"]
        s, Rm, t = rs.similarity(g["V0"][f], Vt[f])
        M0 = s * g["V0"] @ Rm.T + t
        zs = np.linspace(zc - 0.15, zc + 0.15, 240)
        im = Image.new("RGB", (S, S), (30, 30, 30))
        dr = ImageDraw.Draw(im)
        sc = S / 0.30
        for V, col, wd in ((M0[g["ext"]], (90, 140, 255), 1), (MV, (255, 150, 40), 2), (Vt[g["ext"]], (255, 255, 255), 1)):
            y = profile_line(V, zs)
            pts = [((-(yy) - box_p[0][0]) * sc, (zc + 0.15 - zz) * sc) for yy, zz in zip(y, zs) if np.isfinite(yy)]
            if len(pts) > 1:
                dr.line(pts, fill=col, width=wd)
        dr.text((6, 4), "profile: truth white, mesh orange, mean blue", fill=(255, 255, 0))
        sheet.paste(im, (4 * S, r * S))
        # the mesh's signed offset from truth on the true head, front view: -6..+6 mm
        z = np.load(mm.MM / "out" / f"mesh_{n}.npz")
        A = np.nan_to_num(z["A"], nan=0.0)
        e = np.clip(A / 6.0, -1, 1)
        C = np.stack([np.where(e > 0, 1, 1 + e), 1 - np.abs(e), np.where(e < 0, 1, 1 - e)], -1) * 235
        cam = rs.make_cam(Vt, yaw=35, lens=85, size=(S, S), fill=0.8)
        img, _ = rs.render(Vt, cam, albedo=C, flat=True, bg=30)
        sheet.paste(tile(img, "mesh - truth: blue -6 mm .. red +6 mm"), (5 * S, r * S))
    sheet.save(f"{R}/{out}.png")
    print(f"{R}/{out}.png")


if __name__ == "__main__":
    {"normals": normals, "trellis": trellis}[sys.argv[1]]()
