"""rchain.py [mp=0|1] [he=0|1] [lens=<%>] [mix=<json file>] [expr_gate=0|1] -- <script> <args..>: run a groundtruth /
solvecams script (gchain.py, chain.py ..) with readmix's switches set first (module defaults: the scripts call
blockin.solve_step with its defaults). The script's own records go under $HIFIPUSHIE_GROUNDTRUTH (readmix's own root)."""
import json
import runpy
import sys

from hifipushie import blockin as bi, face_ruler as fr, mpread

i = sys.argv.index("--")
kw = dict(a.split("=", 1) for a in sys.argv[1:i])
if "mp" in kw:
    mpread.ENABLED = kw["mp"] == "1"
if "he" in kw:
    fr.HAIR_EDGE = kw["he"] == "1"
if "lens" in kw:
    fr.PHOTO_CAM_DIST_LENS = float(kw["lens"])
if "mix" in kw:
    mpread.MIX = {k: tuple(v) for k, v in json.load(open(kw["mix"])).items()}
if "neff" in kw:
    mpread.NEFF = float(kw["neff"])
if "expr" in kw:
    bi.SOLVE_EXPRESSION = {"0": False, "view": "view", "gate": "gate"}[kw["expr"]]
print("readmix switches:", {"mp": mpread.ENABLED, "hair_edge": fr.HAIR_EDGE, "lens": fr.PHOTO_CAM_DIST_LENS, "expr": bi.SOLVE_EXPRESSION, "mix": sorted(mpread.MIX)}, flush=True)
sys.argv = sys.argv[i + 1:]
runpy.run_path(sys.argv[0], run_name="__main__")
