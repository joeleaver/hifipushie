"""lipbias.py <truth model> ..: what each read that sets the LIPS' HEIGHT says AT THE TRUTH (the scan-fitted identity through
the rig's true cameras, front view): per read type and segment, the picture's point minus the model's, VERTICAL (mm in
the picture, + = the picture's point lies LOWER). 0 = the read leaves the true head alone. For the upper border a negative
value asks for a TALLER upper lip; for the lower border a positive value a taller lower lip.
  lip       the traced vermilion borders (blockin_lips.photo_evidence: the COLOUR edge) against GNM's border vertex rows
  mp        MediaPipe's vermilion border / lip seam / corners through the correspondence
  landmark  the differential detector anchors (lm 48-67: picture minus our render)
Segments by the model point's place across the mouth (u: 0 = the middle, 1 = a corner): centre |u| < 0.2, bow 0.2-0.55,
near corners > 0.55. -> out/lipbias.json + a table."""
import json, os, sys
import numpy as np
from hifipushie import blockin as bi, face_ruler as fr, store

RM = os.environ["HIFIPUSHIE_READMIX"]
UP_LM, LO_LM, SEAM_LM = (49, 50, 51, 52, 53), (55, 56, 57, 58, 59), (60, 61, 62, 63, 64, 65, 66, 67)
UP_MP = (185, 40, 39, 37, 0, 267, 269, 270, 409)
LO_MP = (146, 91, 181, 84, 17, 314, 405, 321, 375)
rows = []
for name in sys.argv[1:]:
    head, views, notes = fr.reference_views(name, lips=True, lids=False, mp=True, hair_edge=False, alar=False)
    v = next(v for v in views if v["kind"] == "front")
    v["extra_obs"] = v["extra"](head, v)
    L = np.asarray(head["L"], float)
    _, q = fr._cam_points(v["cam"], L[[48, 54]])
    c0, half = q.mean(0), 0.5 * np.linalg.norm(q[1] - q[0])
    ex = (q[1] - q[0]) / np.linalg.norm(q[1] - q[0])
    for ob in v["extra_obs"]:
        t = ob["type"]
        if t == "lip":
            seg = "upper" if "upper" in ob["name"] else "lower"
            dy = float(ob["o"] * ob["n"][1])
        elif t == "mp" and ob["name"].endswith(".y"):
            m = ob["mp"]
            seg = "upper" if m in UP_MP else "lower" if m in LO_MP else "seam" if ob["feature"] == "lip seam" else None
            dy = float(ob["o"])
        elif t == "landmark" and ob["name"].endswith(".y") and ob["name"][:4] == "lm" + ob["name"][2:4] and ob["name"][2:4].isdigit():
            i = int(ob["name"][2:4])
            seg = "upper" if i in UP_LM else "lower" if i in LO_LM else "seam" if i in SEAM_LM else None
            dy = float(ob["o"])
        else:
            continue
        if seg is None:
            continue
        us = float((np.asarray(ob["p"]) - c0) @ ex) / half
        u = abs(us)
        key = ob["name"][:-2] if t != "lip" else f"{seg}:{int(np.clip(round((us + 1) * 5), 0, 10))}"
        dx = float(ob["o"] * ob["n"][0]) if t == "lip" else None
        part = "centre" if u < 0.2 else "bow" if u < 0.55 else "corners"
        rows.append({"model": name, "type": t, "seg": seg, "part": part, "dy": dy, "key": key, "u": us})
    print(name, "front reads:", {t: sum(r["type"] == t and r["model"] == name for r in rows) for t in ("lip", "mp", "landmark")}, flush=True)
json.dump(rows, open(f"{RM}/out/lipbias_{'_'.join(sys.argv[1:])[:50]}.json", "w"))
print("\n| read | border | part | mean dy mm (sd over subjects) | per subject |")
print("|---|---|---|---|---|")
for t in ("lip", "mp", "landmark"):
    for seg in ("upper", "seam", "lower"):
        for part in ("centre", "bow", "corners"):
            per = [np.mean([r["dy"] for r in rows if r["model"] == m and r["type"] == t and r["seg"] == seg and r["part"] == part] or [np.nan]) for m in sys.argv[1:]]
            per = np.array(per)
            if np.isfinite(per).sum():
                print(f"| {t} | {seg} | {part} | {np.nanmean(per):+.2f} ({np.nanstd(per):.2f}) | " + " ".join(f"{x:+.1f}" for x in per) + " |")

# per-key calibration (mean over subjects of each subject's mean): lip = border:u-bin (0..10 across the mouth), mp = "mp<id>",
# landmark = "lm<NN>"; only the VERTICAL offset (mm in the picture, + = down)
cal = {}
for t in ("lip", "mp", "landmark"):
    keys = sorted({r["key"] for r in rows if r["type"] == t})
    for k in keys:
        per = [np.mean([r["dy"] for r in rows if r["type"] == t and r["key"] == k and r["model"] == m]) for m in sys.argv[1:]
               if any(r["type"] == t and r["key"] == k and r["model"] == m for r in rows)]
        if len(per) >= 4:
            cal.setdefault(t, {})[k] = [round(float(np.mean(per)), 3), round(float(np.std(per)), 3), len(per)]
json.dump({"provenance": {"what": "vertical offset (mm, + = down) of each lip read at the TRUE head on HSRD photographs: picture minus model; "
           "subtract it from a photo's read", "subjects": sys.argv[1:], "script": "spikes/readmix/lipbias.py", "date": "2026-10-14"}, "cal": cal},
          open(f"{RM}/out/lip_photo_bias.json", "w"), indent=0)
print("calibration keys:", {t: len(v) for t, v in cal.items()})
