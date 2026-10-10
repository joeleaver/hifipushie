"""fidelity.py <model> [out png]: faces6, does the fast renderer read the SURFACE THAT SHIPS? The fast renderer draws the
one mesh's raw quads (humanfit.state: GNM + sliders at template resolution); the shipped build Catmull-Clarks them and
meshes an implicit surface over the points (base.py: kernel width h per vertex), which smooths. Builds the model's
face close-up (store.build box, on a scratch copy <model>_fid), then per feature crop renders, at the crop's native
picture pixels (x SS, downsampled), with the SAME fast shading (photo light + AO + soft shadow): raw | shipped |
raw with the candidate smoothing (SMOOTH: model_mesh_from_state(subdivide=...)). Prints the raw -> shipped surface
distance per region and the luminance difference per crop (mean |dL| / the crop's median), writes the sheet."""
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

from featsheet import boxes
from noserender import lit_render
from hifipushie import humanfit, likeness, store

SS = int(os.environ.get("SS", "2"))
RES = int(os.environ.get("RES", "320"))
HALF = float(os.environ.get("HALF", "0.11"))


def shipped_mesh(m, st):
    fid = m + "_fid"
    d = store.HOME / fid
    d.mkdir(exist_ok=True)
    shutil.copy(store.HOME / m / "spec.json", d / "spec.json")
    shutil.copy(store.HOME / m / "human_refs.json", d / "human_refs.json")
    c = 0.5 * (st["L"][36] + st["L"][45]) * 0 + st["L"][30]   # the nose tip: the face's centre
    c = np.asarray(c, float) + [0, 0.02, -0.01]
    meta = store.build(fid, RES, box=(c - HALF, c + HALF))
    z = np.load(meta["mesh"], allow_pickle=True)
    print("closeup keys", list(z.keys()), "voxel", meta.get("voxel"))
    V = np.asarray(z["verts"] if "verts" in z else z["V"], float)
    F = np.asarray(z["faces"] if "faces" in z else z["F"], np.int64)
    if "part" in z and "part_names" in z:   # the skin only
        names = [str(x) for x in z["part_names"]]
        pv = np.asarray(z["part"])
        if len(pv) == len(V) and "body" in names:
            keep = pv == names.index("body")
            F = F[keep[F].all(1)]
    return V, F


def crop_render(mesh, cam, box, img):
    side = int(round(max(box[2] - box[0], box[3] - box[1])))
    im = lit_render(mesh, cam, img, box=box, px=side * SS)[0]
    return im.resize((side, side), Image.LANCZOS)


def lum(im):
    a = np.asarray(im.convert("RGB"), float) / 255.0
    return a @ [0.2126, 0.7152, 0.0722]


if __name__ == "__main__":
    m = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else f"/mnt/data/hifipushie/faces6/out/fid_{m}.png"
    refs = json.loads((store.HOME / m / "human_refs.json").read_text())
    st = humanfit.state(store.load(m)["base"])
    raw = likeness.model_mesh_from_state(st)
    Vs, Fs = shipped_mesh(m, st)
    ship = {**raw, "V": Vs, "F": Fs}
    ship.pop("_ao", None)
    # geometry: raw vertices of the face -> the shipped surface (nearest shipped vertex; ~0.6 mm voxels)
    tree = cKDTree(Vs)
    face = np.linalg.norm(raw["V"] - st["L"][30], axis=1) < 0.08
    dist, _ = tree.query(raw["V"][face])
    print(f"raw -> shipped (face, {face.sum()} verts): median {np.median(dist) * 1000:.2f} mm, p90 "
          f"{np.percentile(dist, 90) * 1000:.2f}, max {dist.max() * 1000:.2f}")
    cols = {"raw quads (fast now)": raw, "shipped surface": ship}
    if os.environ.get("SMOOTH"):
        st2 = dict(st)
        cols[f"raw + {os.environ['SMOOTH']}"] = likeness.model_mesh_from_state(st, smooth=os.environ["SMOOTH"])
    bx = boxes(refs, ["nose", "lips", "eyes"])
    T = 260
    sheet = Image.new("RGB", (T * (1 + len(cols)), (T + 18) * len(bx) + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, lab in enumerate(["photo"] + list(cols)):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    for i, (vi, rg, box, img) in enumerate(bx):
        cam = refs["cameras"][vi]
        y = 18 + i * (T + 18)
        ims = {k: crop_render(mm, cam, box, img) for k, mm in cols.items()}
        Ls = {k: lum(v) for k, v in ims.items()}
        ref = Ls["shipped surface"]
        msk = ref < 0.92   # (on the model: the backdrop is 238 / 255)
        med = float(np.median(ref[msk]))
        line = []
        for k, L_ in Ls.items():
            if k != "shipped surface":
                line.append(f"{k}: |dL| {np.abs(L_ - ref)[msk].mean() / med:.3f}, p95 {np.percentile(np.abs(L_ - ref)[msk], 95) / med:.3f}")
        print(f"view {vi} {rg}: " + "; ".join(line), flush=True)
        dr.text((4, y), f"view {vi} {rg}", fill=(0, 0, 0))
        sheet.paste(img.crop(tuple(int(round(b)) for b in box)).resize((T, T), Image.LANCZOS), (0, y + 16))
        for j, k in enumerate(cols):
            sheet.paste(ims[k].resize((T, T), Image.LANCZOS), ((j + 1) * T, y + 16))
    sheet.save(out)
    print("wrote", out)
