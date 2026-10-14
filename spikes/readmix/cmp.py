"""cmp.py <model> [dense=1] [rounds=1]: face_ruler.compare WITHOUT applying it: the read counts, the notes (NOSE READ,
OUTLINE READS, LENS, DISAGREE ..) and what each read group asks of nose_width / mouth_width (J dc of the solved step)."""
import sys
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, gnm_mm, store

name = sys.argv[1]
kw = dict(a.split("=") for a in sys.argv[2:])
c0 = bi.identity(store.load(name))
root = (bi._refs(name).get("blockin") or {}).get("root")
off = c0 - bi.identity(store.load(root)) if root else None
c = fr.compare(name, rounds=int(kw.get("rounds", 1)), prior_off=off, lids=True, lips=True, parse="auto", adapt=True, cmax=3.0, cam_first=1, cam_reset=False,
               cam_done0=np.zeros((len(bi._refs(name)["views"]), 7)), dense=kw.get("dense") == "1")
print("reads:", {k: v for k, v in c["n"].items() if v}, "| per view:", c["n_view"])
for x in c["notes"]:
    if x[:4] in ("NOSE", "OUTL", "NO O", "LENS", "DISA", "NOIS", "AT T"):
        print(" ", x[:600])
for ob in c["obs"]:
    if ob["type"] == "nostril":
        print(f"   {ob['view']} {ob['name']}: o {ob['o']:+.2f} mm sig {ob['sig']:.2f} area {ob['area']:.0f} mm2")
names = list(gnm_mm.NAMES)
for m in ("nose_width", "mouth_width"):
    r = next(r for r in c["rows"] if r["measure"] == m)
    print(f"{m}: gap (picture - model) {r['gap']:+.2f} mm, read {r['read']:.2f}")
