"""basestack.py <out png> [camera model]: faces6 diagnostic (coordinator): is our BASE STACK part of the miss? GNM's sampler
female class mean + 3 random female samples (femsamp.npz), each rendered two ways in the same hair-cap clay through
the same cameras (front / 3/4 / profile of <camera model>):
  (a) GNM's OWN head mesh: template + identity (humanmacro.space, world frame), its own eyeballs, nothing else;
      similarity-aligned (scale, rotation, shift: Procrustes on the 68 landmarks) onto (b)'s head so the camera sees
      both the same size and pose: shape differences only;
  (b) our one-mesh pipeline: the body's MakeHuman head (Tess's body: age 22, sex 0, weight 0.15) + onemesh.hook's
      GNM difference + the dimorphism field x 1.3 (f3_t1's head keys, local layers stripped).
Prints per identity the landmark rms between (a) and (b) after the alignment (mm) and a few widths."""
import copy
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import wholeclay as WC
from hifipushie import humanfit, humanmacro as hmac, likeness, store

T = int(os.environ.get("T", "300"))
F = os.environ.get("F", "/mnt/data/hifipushie/faces6")


def procrustes(A, B):
    """s, R, t with s R A + t ~ B (rows)."""
    ma, mb = A.mean(0), B.mean(0)
    A0, B0 = A - ma, B - mb
    U, S, Vt = np.linalg.svd(A0.T @ B0)
    d = np.sign(np.linalg.det(U @ Vt))
    D = np.diag([1, 1, d])
    R = (U @ D @ Vt).T
    s = float((S * np.diag(D)).sum() / (A0 ** 2).sum())
    return s, R, mb - s * R @ ma


def raw_mesh(c, L_target):
    sp = hmac.space()
    V = sp["V0"] + np.tensordot(np.asarray(c, np.float32)[:sp["IB"].shape[0]], sp["IB"], 1)
    L = sp["W"] @ V
    s, R, t = procrustes(L[:68], L_target[:68])
    V = s * V @ R.T + t
    L = s * L @ R.T + t
    gr = sp["gr"]
    C = np.tile(likeness.SKIN, (len(V), 1)).astype(float)
    for k, col in (("scleras", (235, 230, 225)), ("irises", (80, 62, 48)), ("pupils", (25, 18, 15))):
        if k in gr:
            C[gr[k]] = col
    hm_ = gr.get("hockey_mask")
    ear = gr.get("ears")
    if hm_ is not None:
        zcut = 0.5 * (L[1, 2] + L[15, 2])
        w = (~hm_) & (~ear if ear is not None else True) & (V[:, 2] > zcut)
        for k in ("left_eye", "right_eye", "scleras", "irises", "pupils"):
            if k in gr:
                w &= ~gr[k]
        C[w] = WC.HAIR_RGB
    rms = float(np.sqrt(np.mean(np.sum((L[:68] - L_target[:68]) ** 2, 1)))) * 1000
    return {"V": V, "F": sp["T"], "eyes": [], "L": L, "C": C}, rms, s


def pipe_mesh(base, c):
    b = copy.deepcopy(base)
    b["head"]["identity"] = {f"head_{i:03d}": round(float(v), 5) for i, v in enumerate(c)}
    st = humanfit.state(b)
    mesh = likeness.model_mesh_from_state(st)
    mesh["C"] = WC.haircap(mesh, st)
    return mesh, st


if __name__ == "__main__":
    out = sys.argv[1]
    cm = sys.argv[2] if len(sys.argv) > 2 else "f3_t1"
    refs = json.loads((store.HOME / cm / "human_refs.json").read_text())
    base = copy.deepcopy(store.load(cm)["base"])
    for k in ("sliders", "warp", "fold", "pose"):
        base["head"].pop(k, None)
    fs = np.load(f"{F}/femsamp.npz")
    ids = [("female mean", fs["mean"])] + [(f"female sample {i + 1}", s) for i, s in enumerate(fs["samples"])]
    WC.BROW_MM = 2.0
    cols = []
    for lab, c in ids:
        pm, st = pipe_mesh(base, c)
        rm, rms, s = raw_mesh(c, st["L"])
        print(f"{lab}: |c| {np.linalg.norm(c):.2f}; (a) raw GNM vs (b) pipeline, landmark rms after similarity {rms:.2f} mm "
              f"(scale {s:.3f})", flush=True)
        cols += [(f"{lab}: (a) GNM alone", rm), (f"{lab}: (b) our pipeline", pm)]
    ref_st = humanfit.state(base)
    sheet = Image.new("RGB", (T * len(cols), (T + 18) * 3 + 18), "white")
    dr = ImageDraw.Draw(sheet)
    for j, (lab, _) in enumerate(cols):
        dr.text((j * T + 4, 2), lab, fill=(0, 0, 0))
    for i, vi in enumerate((0, 1, 2)):
        cam = refs["cameras"][vi]
        P = humanfit.project(cam, ref_st["L"])
        cc = 0.5 * (P.min(0) + P.max(0))
        side = 1.45 * float(np.max(P.max(0) - P.min(0)))
        box = (cc[0] - side / 2, cc[1] - side * 0.56, cc[0] + side / 2, cc[1] + side * 0.44)
        for j, (lab, mesh) in enumerate(cols):
            im, k = likeness.render(mesh, cam, box, px=2 * T, brows=False, ao=True, shadow=8.0)[:2]
            im = WC.draw_brows(im, mesh, cam, box, k)
            sheet.paste(im.resize((T, T), Image.LANCZOS), (j * T, 18 + i * (T + 18)))
    sheet.save(out)
    print("wrote", out)
