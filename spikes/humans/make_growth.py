"""make_growth.py: src/hifipushie/growth.json from the fetched references (workspace/skin_refs/ages, see its README).

Sources:
- WHO Child Growth Standards (0-5 y: length/height-for-age, head circumference-for-age) and the WHO 2007 growth
  reference (5-19 y height-for-age): medians (M) per sex.
- Snyder et al. 1977, "Anthropometry of Infants, Children and Youths to Age 18 for Product Safety Design" (UMTRI-77-17,
  for the US CPSC; the tables as published by NIST AnthroKids, a US government work): means per age group, both sexes
  and each.
Run: uv run --with openpyxl python spikes/humans/make_growth.py
"""
import csv
import json
from pathlib import Path

import numpy as np
import openpyxl

D = Path("/home/joe/dev/hifipushie/workspace/skin_refs/ages")
OUT = Path(__file__).resolve().parents[2] / "src" / "hifipushie" / "growth.json"


def who(name, unit):
    ws = openpyxl.load_workbook(D / name, read_only=True).worksheets[0]
    rows = [r for r in ws.iter_rows(values_only=True) if isinstance(r[0], (int, float))]
    t = np.array([r[0] for r in rows], float) / (365.25 if unit == "day" else 12.0)
    return t, np.array([r[2] for r in rows], float)


def snyder(name):
    rows = [r for r in csv.reader(open(D / "snyder1977" / f"{name}.csv")) if r and r[0].strip()]
    out = []
    for r in rows[2:]:
        try:
            a, b = (float(x) for x in r[0].split("-"))
            out.append(((a + b) / 2, float(r[2])))
        except ValueError:
            pass
    return out


def main():
    ages = [0.0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    out = {"_sources": __doc__.split("Run:")[0].strip(), "ages": ages, "stature_cm": {}, "head_circ_cm_0_5": {}}
    for sex, tag in (("m", "boys"), ("f", "girls")):
        t0, m0 = who(f"who_lhfa_{tag}_0_5.xlsx", "day")
        t1, m1 = who(f"who_hfa_{tag}_5_19.xlsx", "month")
        # (WHO measures length lying down under 2 and standing height from 2: its own tables step 0.7 cm there)
        t = np.r_[t0[t0 < 5.0], t1[t1 >= 5.0]]
        m = np.r_[m0[t0 < 5.0], m1[t1 >= 5.0]]
        out["stature_cm"][sex] = [round(float(np.interp(a, t, m)), 2) for a in ages]
        th, mh = who(f"who_hcfa_{tag}_0_5.xlsx", "day")
        out["head_circ_cm_0_5"][sex] = {"ages": [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5],
                                         "cm": [round(float(np.interp(a, th, mh)), 2) for a in [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5]]}
    # Snyder's tables: children (2-19 y) per sex and combined; infants (months) combined
    S = {}
    for name in ("stature", "sitting_height", "head_height", "head_circ", "head_breadth", "head_length", "face_height",
                 "neck_circ", "shoulder_breadth", "biacromial", "shoulder_elbow", "elbow_hand", "hand_length",
                 "chest_circ", "chest_breadth", "waist_circ", "hip_circ", "hip_breadth", "trochanteric_height",
                 "gluteal_furrow_height", "tibiale_height", "upper_thigh_circ", "calf_circ", "foot_length",
                 "suprasternale_height", "waist_height", "mouth_breadth", "nose_length", "bizygomatic", "lower_face_height"):
        S[name] = {s: snyder(f"{name}_{f}") for s, f in (("all", "all"), ("m", "m"), ("f", "f"))}
    out["snyder_children"] = {"_unit": "cm; [mid age of the group (years), mean]", **S}
    inf = {}
    for name in ("crown_sole", "crown_rump", "head_circ", "head_breadth", "head_length", "shoulder_breadth", "shoulder_elbow",
                 "elbow_hand", "hand_length", "chest_circ", "chest_breadth", "waist_circ", "rump_sole", "rump_knee",
                 "hip_circ", "hip_breadth", "mid_thigh_circ", "knee_sole", "calf_circ", "foot_length"):
        inf[name] = [(round(a / 12, 3), v) for a, v in snyder(f"infant_{name}")]
    out["snyder_infants"] = {"_unit": "cm; [mid age of the group (years), mean], sexes together", **inf}
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(OUT, OUT.stat().st_size)


if __name__ == "__main__":
    main()
