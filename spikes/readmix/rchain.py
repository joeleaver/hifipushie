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
if "lenspin" in kw:
    fr.LENS_PINS = kw["lenspin"] == "1"
if "nosebias" in kw:
    fr.LM_NOSE_WIDE = float(kw["nosebias"])
if "alar" in kw:
    fr.ALAR = kw["alar"] == "1"
if "alarbias" in kw:
    fr.ALAR_BIAS = float(kw["alarbias"])
if "alarfeat" in kw:
    fr.ALAR_FEATURE = kw["alarfeat"]
if "nos" in kw:
    fr.NOSTRIL = kw["nos"] == "1"
if "lens" in kw:
    fr.PHOTO_CAM_DIST_LENS = float(kw["lens"])
if "mix" in kw:
    mpread.MIX = {k: tuple(v) for k, v in json.load(open(kw["mix"])).items()}
if "neff" in kw:
    mpread.NEFF = float(kw["neff"])
if "expr" in kw:
    bi.SOLVE_EXPRESSION = {"0": False, "view": "view", "gate": "gate"}[kw["expr"]]
if kw.get("camfreeze") == "1":      # the cameras FROZEN where the chain starts them (start=true: at the truth)
    fr.PHOTO_CAM_SD7 = {k: tuple(1e-3 for _ in v) for k, v in fr.PHOTO_CAM_SD7.items()}
    fr.PHOTO_CAM_DIST_DENSE = 1e-3
    bi.CAM_FIRST = 0
if "distfreeze" in kw:               # only the DISTANCE held (%), the rest free
    fr.PHOTO_CAM_SD7 = {k: tuple(v[:6]) + (float(kw["distfreeze"]),) for k, v in fr.PHOTO_CAM_SD7.items()}
    fr.PHOTO_CAM_DIST_DENSE = float(kw["distfreeze"])
if "scout" in kw:                    # a solvecams chain's records: under this directory's out/ instead of solvecams' own
    import common as _C_
    _C_.S = kw["scout"]
print("readmix switches:", {"mp": mpread.ENABLED, "hair_edge": fr.HAIR_EDGE, "lens": fr.PHOTO_CAM_DIST_LENS, "expr": bi.SOLVE_EXPRESSION, "mix": sorted(mpread.MIX)}, flush=True)
sys.argv = sys.argv[i + 1:]
runpy.run_path(sys.argv[0], run_name="__main__")
