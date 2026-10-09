"""lidcmp.py <model> [posed=0] [patch.json ...]: like with like for the eyes, brows and mouth (analysis by
synthesis): the SAME detector on the front photo and on the model's own render through its fitted front camera, so
no point definition enters: per eye the lid opening, the upper lid's height over the line through the eye's corners,
the brow's height over that line, the eye's width; the mouth corners' height against the lips' middle (+ = corners
up), its width, each lip's height; all in mm at the head, photo | model (difference).
A patch.json is tried on the model's head IN MEMORY (nothing saved) and measured again:
  {"eyes": 0.9, "expression": {} | null, "macros": {"eye_height": -1, ...} (held), "shape": {key: value | null},
   "pose": {...}, "save": "<model name to save the patched model as>"}"""
import copy
import json
import sys

import numpy as np
from PIL import Image

import rs
import stage
from hifipushie import humanfit, humanmacro as hm, likeness as lk, store

PX = 768
KS = ("browDownLeft", "browDownRight", "eyeSquintLeft", "eyeSquintRight", "eyeBlinkLeft", "mouthFrownLeft", "mouthPressLeft", "mouthPressRight")


def numbers(d, mm):
    P = d["P"][:, :2]
    out = {}
    for tag, (c0, c1, up, lw, brow) in {"R": (33, 133, 159, 145, 105), "L": (263, 362, 386, 374, 334)}.items():
        ax = P[c1] - P[c0]
        n = np.array([-ax[1], ax[0]]) / np.linalg.norm(ax)
        if n[1] > 0:
            n = -n                                      # up in the picture
        h = lambda i: float((P[i] - P[c0]) @ n) * mm    # noqa: E731
        out[tag] = {"opening": h(up) - h(lw), "upper": h(up), "lower": -h(lw), "brow": h(brow), "width": float(np.linalg.norm(ax)) * mm}
    m0, m1, top, bot = P[61], P[291], P[13], P[14]
    mid = 0.5 * (top + bot)
    nose = float(np.linalg.norm(P[129] - P[358])) * mm
    out["mouth"] = {"corners_up": float(mid[1] - 0.5 * (m0[1] + m1[1])) * mm, "width": float(np.linalg.norm(m1 - m0)) * mm,
                    "upper_lip": float(np.linalg.norm(P[0] - P[13])) * mm, "lower_lip": float(np.linalg.norm(P[17] - P[14])) * mm,
                    "nose_width": nose, "nose_len": float(np.linalg.norm(P[168] - P[2])) * mm, "philtrum": float(np.linalg.norm(P[2] - P[0])) * mm}
    return out


def setup(name):
    refs = json.loads((store.HOME / name / "human_refs.json").read_text())
    v, cam = refs["views"][0], refs["cameras"][0]
    U = np.array(list(v["points"].values()), float)
    lo, hi = U.min(0), U.max(0)
    c, side = 0.5 * (lo + hi), 2.2 * max(hi - lo)
    box = (c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2)
    photo = np.asarray(Image.open(v["image"]).convert("RGB").crop(tuple(int(round(x)) for x in box)).resize((PX, PX), Image.LANCZOS))
    mm = cam["t"][2] / cam["f"] * 1000 * side / PX
    return cam, box, photo, mm


def patched(b, p):
    b = copy.deepcopy(b)
    h = b["head"]
    if "eyes" in p:
        h["eyes"] = p["eyes"]
    if "expression" in p:
        if p["expression"]:
            h["expression"] = p["expression"]
        else:
            h.pop("expression", None)
    if p.get("macros"):
        b = humanfit._with_identity(b, hm.apply(humanfit.identity(b), p["macros"], held=True))
        h = b["head"]
    for k, v in (p.get("shape") or {}).items():
        if v is None:
            h.get("shape", {}).pop(k, None)
        else:
            h.setdefault("shape", {})[k] = v
    if p.get("pose"):
        h["pose"] = {**(h.get("pose") or {}), **p["pose"]}
    for lmk, mv in (p.get("nudge") or {}).items():   # a landmark moved by the IDENTITY alone (the rest held; the
        pm0 = list((b["head"].get("shape") or {}).get("push_more") or [])   # correction bump nudge adds is dropped)
        nb, rep = humanfit.nudge(b, lmk, move=mv, force=True)
        print(f"  nudge {lmk} {mv}: by sliders {rep['by_sliders_mm']} mm, a bump would add {rep['by_correction_mm']} mm (dropped)")
        sh = nb["head"].get("shape") or {}
        if pm0:
            sh["push_more"] = pm0
        else:
            sh.pop("push_more", None)
        b = nb
    return b


def measure(b, cam, box, mm):
    mesh = lk.model_mesh(b)
    ours = np.asarray(lk.render(mesh, cam, box, px=PX)[0].convert("RGB").resize((PX, PX)))
    d = rs.detect([ours])[0]
    return numbers(d, mm), d


def show(tag, a, m, dm=None):
    print(tag)
    for k in a:
        print(f"  {k:6s} " + "  ".join(f"{q} {a[k][q]:.1f}|{m[k][q]:.1f}({m[k][q] - a[k][q]:+.1f})" for q in a[k]))
    if dm is not None:
        print("  scores model:", {k: round(dm["bs"].get(k, 0.0), 2) for k in KS})


if __name__ == "__main__":
    name = sys.argv[1]
    posed = len(sys.argv) > 2 and sys.argv[2] == "1"
    sp = store.load(name)
    b = copy.deepcopy(sp["base"])
    cam, box, photo, mm = setup(name)
    dp = rs.detect([photo])[0]
    a = numbers(dp, mm)
    print("scores photo:", {k: round(dp["bs"].get(k, 0.0), 2) for k in KS})
    if posed:
        pf = store.HOME / name / "pose.json"
        b["head"]["pose"] = json.loads(pf.read_text()) if pf.exists() else dict(stage.POSE)
    m, dm = measure(b, cam, box, mm)
    show(f"{name}{' (posed)' if posed else ''}: photo|model(diff), mm ({mm:.2f} mm a pixel)", a, m, dm)
    for pf in sys.argv[3:]:
        p = json.load(open(pf))
        b2 = patched(b, p)
        m2, dm2 = measure(b2, cam, box, mm)
        show(f"+ {pf.split('/')[-1]}: {json.dumps({k: v for k, v in p.items() if k != 'save'})[:200]}", a, m2, dm2)
        print("  plausibility", humanfit.plausibility(b2), "| integrity:", humanfit.verdict(humanfit.integrity(b2, humanfit.state(b2), humanfit.state(b)))[:160])
        if p.get("save"):
            b2["head"].pop("pose", None) if posed else None
            store.save(p["save"], {**copy.deepcopy(sp), "base": b2}, f"garrett3: {name} + {pf.split('/')[-1]} (eyes / lips / brows by the same detector on photo and render)")
            for fn in ("human_refs.json", "pose.json"):
                f = store.HOME / name / fn
                if f.exists():
                    (store.HOME / p["save"] / fn).write_text(f.read_text())
            print("saved", p["save"])
