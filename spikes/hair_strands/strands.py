"""strands.py <model> <out prefix> [amount=..] : the model's locks as guides of Blender Hair Curves + the Essentials
hair nodes, rendered as strands (EEVEE, Cycles). Free locks (a tail) and scalp locks are two Curves objects with
their own numbers."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image
from hifipushie import hair, hair_cards as hc, render, store

name, prefix = sys.argv[1], sys.argv[2]
opt = dict(a.split("=", 1) for a in sys.argv[3:])
spec = store.load(name)
sc = hair.scalp(name, spec)
S = hc.strands_of(spec)
locks = [lk for lk in hair.resolve(spec, sc) if not lk["name"].endswith("band")]
amount = int(opt.get("amount", 250))
views = opt.get("views", "front,three_quarter,side,back,close_front").split(",")
size = int(opt.get("size", 640))


def guides(sel):
    out = []
    for lk in sel:
        P, *_ = hc.spine(lk, 20)
        out.append({"pts": P.tolist(), "width": lk["inputs"]["Width"]})
    return out


free = [lk for lk in locks if lk["free"] > 0.5]
head = [lk for lk in locks if lk["free"] <= 0.5]
wave = float(S["wave"])
groups = {}
if head:
    w = float(np.median([lk["inputs"]["Width"] for lk in head]))
    groups["head"] = {"guides": guides(head), "params": {
        "amount": amount, "radius": w * float(opt.get("spread", 0.5)), "clump": float(opt.get("clump", 0.35)), "frizz": float(opt.get("frizz", 0.0002)), "noise": float(opt.get("noise", 0.0004)),
        "curl_radius": wave * float(opt.get("headcurl", 0.0)), "curl_freq": 1.0 / float(S["wavelength"]), "strand_radius": float(opt.get("r", 0.00012))}}
if free:
    w = float(np.median([lk["inputs"]["Width"] for lk in free]))
    groups["free"] = {"guides": guides(free), "params": {
        "amount": amount, "radius": w * 0.5, "clump": float(opt.get("tailclump", 0.15)), "frizz": 2 * float(opt.get("frizz", 0.0002)), "noise": 2 * float(opt.get("noise", 0.0004)), "shrinkwrap": False,
        "curl_radius": wave, "curl_freq": 1.0 / float(S["wavelength"]), "strand_radius": float(opt.get("r", 0.00012))}}
cams = hair.cameras(sc, views)
frames = [render.camera_frame(c, i) for i, c in enumerate(cams)]
rvs = hair.ref_views(name)
idv = []
for v, rc, _ in rvs[:1]:
    frames.append({"name": "matched", "eye": rc["eye"], "dir": rc["dir"], "up": rc["up"], "fov": rc["fov"],
                   "shift": rc["shift"], "center": sc.C.tolist(), "near": 0.01, "scale": None, "axes": None})
    idv = [dict(frames[-1], size=480)]
tmp = Path(tempfile.mkdtemp(prefix="hc-strands-"))
for f in idv:
    f["out"] = str(tmp / "matched.png")
for f in frames:
    f["out"] = str(tmp / f"{f['name']}.png")
engines = opt.get("engines", "eevee,cycles").split(",")
job = {"blend": str(hair.make_stage(name)), "src": str(Path(hair.__file__).parent), "groups": groups, "views": frames,
       "size": size, "engines": engines, "cycles_samples": int(opt.get("spp", 24)),
       "melanin": float(opt.get("melanin", 0.72)), "save": opt.get("save"), "id_views": idv,
       "volume": {"radius": float(opt.get("vr", 0.004)), "voxel": float(opt.get("vox", 0.002)),
                  "triangles": int(opt.get("tris", 12000))} if opt.get("volume") else None}
(tmp / "job.json").write_text(json.dumps(job))
t = time.time()
r = subprocess.run([render.BLENDER, "-b", "--factory-startup", "--python", os.path.join(os.environ["SP"], "bl_strands.py"),
                    "--", str(tmp / "job.json")], capture_output=True, text=True)
print("\n".join(line for line in r.stdout.splitlines() if line.startswith("@@")))
if r.returncode or "Error" in r.stderr:
    print(r.stderr[-1500:])
print("total", round(time.time() - t, 1), "s")
import shutil
for suf in ("id", "volid"):
    f = tmp / f"matched_{suf}.png"
    if f.exists():  # the matched view's hair mask -> the fit against the traced reference
        shutil.copy(f, os.path.join(os.environ["HR"], f"{prefix}_{suf}.png"))
        a_ = np.asarray(Image.open(f).convert("RGB"), float)
        mask = a_[..., 1] > a_[..., 0] + 60
        v, rc, tr = rvs[0]
        fm = hair.fit_metrics(name, sc, rc, spec, mask, tr=tr)
        print("fit", suf, {k: fm[k] for k in fm if k not in ("clumps", "regions", "front_edge")})
for e in engines + (["vol"] if opt.get("volume") else []):
    ims = [Image.open(f["out"].replace(".png", f"_{e}.png")).convert("RGB") for f in frames
           if os.path.exists(f["out"].replace(".png", f"_{e}.png"))]
    if ims:
        sheet = Image.new("RGB", (size * len(ims), size))
        for i, im in enumerate(ims):
            sheet.paste(im.resize((size, size)), (i * size, 0))
        sheet.save(os.path.join(os.environ["HR"], f"{prefix}_{e}.png"))
