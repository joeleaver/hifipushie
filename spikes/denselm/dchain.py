"""dchain.py <from> <prefix> <n calls> [key=value ...]: chinread's cchain.py (blockin.solve_step calls in a row, scored
against a known head) with the dense-landmark observation switched by the environment: DL_DENSE=1 (on) | 0,
DL_SIG=<x the network's sigma>, DL_FLOOR=<mm>, DL_MAX=<mm>, DL_REGIONS=chin,cheeks,.. (default: every skin landmark)."""
import os
import runpy
import sys
from pathlib import Path

from hifipushie import face_ruler as fr

fr.DENSE = os.environ.get("DL_DENSE", "1") == "1"
if os.environ.get("DL_SIG"):
    fr.DENSE_SIG_SCALE = float(os.environ["DL_SIG"])
if os.environ.get("DL_FLOOR"):
    fr.DENSE_SIG_FLOOR = float(os.environ["DL_FLOOR"])
if os.environ.get("DL_MAX"):
    fr.DENSE_MAX_MM = float(os.environ["DL_MAX"])
if os.environ.get("DL_REGIONS"):
    fr.DENSE_REGIONS = tuple(os.environ["DL_REGIONS"].split(","))
print(f"dense landmarks: {'ON' if fr.DENSE else 'off'} (sigma x{fr.DENSE_SIG_SCALE}, floor {fr.DENSE_SIG_FLOOR} mm, max {fr.DENSE_MAX_MM} mm, regions {fr.DENSE_REGIONS})")
runpy.run_path(str(Path(__file__).parent.parent / "chinread" / "cchain.py"), run_name="__main__")
