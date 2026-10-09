"""garrett.py <stage>: Garrett on the face sliders (model fs_garrett, from ll_garrett).
  strip : ll_garrett's head without its one-off edits: the shape ops (hood, eye_bag, lip_roll, lid_fold and the ageing
          ops) out; the identity without the eye rounds' hand nudges (history 0005-0008: lid / corner / brow nudges)
          but with every identity-slider move (nose, jaw, mouth-width macros); the ageing ops converted to their
          sliders at their old amounts. Writes workspace/fs_garrett (spec + the refs).
  eyes  : fit canthal_tilt, eye_platform, eye_hood_lateral, brow_lateral to the photo (matched pair, same detector):
          canthal tilt, cover, opening, brow gap, brow tilt.
  lips  : fit lip_upper_roll, lip_lower_roll, lip_bow to upper / lower lip height and the bow.
Each stage saves the spec and prints before / after."""
import json
import shutil
import sys
from pathlib import Path

import gm
from hifipushie import faceslide

WS = Path("/home/joe/dev/hifipushie/workspace")
SRC, DST = WS / "ll_garrett", WS / "fs_garrett"
stage = sys.argv[1]


def load(p):
    s = json.loads(p.read_text())
    return s.get("spec", s)


def save(spec):
    DST.mkdir(exist_ok=True)
    for f in ("human_refs.json", "pose.json"):
        if not (DST / f).exists():
            shutil.copy(SRC / f, DST / f)
    (DST / "spec.json").write_text(json.dumps(spec, indent=1))


def show(tag, ph, md, keys):
    print(tag, "  ".join(f"{k} {md[k]:.2f} (photo {ph[k]:.2f})" for k in keys))


if stage == "strip":
    spec = load(SRC / "spec.json")
    h = spec["base"]["head"]
    i4, i8, i9 = (load(SRC / "history" / f"{n:04d}.json")["base"]["head"]["identity"] for n in (4, 8, 9))
    ids = set(i4) | set(i8) | set(i9)
    h["identity"] = {k: round(i4.get(k, 0) + i9.get(k, 0) - i8.get(k, 0), 5) for k in sorted(ids)}
    sh = h.get("shape", {})
    for k in ("hood", "eye_bag", "lip_roll", "lid_fold", "nasolabial", "prejowl", "cheek_flat", "planes", "lean",
              "hollow", "chin"):
        sh.pop(k, None)
    # the ageing ops at their old amounts (units: faceslide.UNITS / BAKED)
    h["sliders"] = {"face_planes": 0.5, "face_lean": 1.5, "chin_cleft": 1.5, "cheek_hollow": 0.62,
                    "age_nasolabial": 0.5, "age_cheek_flat": 1.0, "age_prejowl": 0.75, "age_lid_fold": 1.0}
    save(spec)
    ph, md, _ = gm.measure("fs_garrett", spec["base"])
    show("stripped:", ph, md, ("open", "cover", "canthal_tilt", "brow_gap", "brow_tilt", "upper_lip", "lower_lip",
                               "cupid_bow", "mouth_width"))
elif stage == "brow":  # the brows' height: an identity move (humanfit.solve, least change, everything else held)
    from hifipushie import humanfit
    spec = load(DST / "spec.json")
    ph0, md0, _ = gm.measure("fs_garrett", spec["base"])
    d = round(-(md0["brow_gap"] - ph0["brow_gap"]), 2)
    nb, rep = humanfit.solve(spec["base"], {"brow_height": f"{d:+.2f}"})
    print("solve brow_height", d, "->", {k: rep[k] for k in rep if k in ("refused", "unintended", "moved")})
    ph1, md1, _ = gm.measure("fs_garrett", nb)
    show("before:", ph0, md0, ("brow_gap", "brow_height", "brow_tilt", "open", "canthal_tilt"))
    show("after: ", ph1, md1, ("brow_gap", "brow_height", "brow_tilt", "open", "canthal_tilt"))
    if not rep.get("refused"):
        spec["base"] = nb
        save(spec)
elif stage in ("eyes", "lips"):
    spec = load(DST / "spec.json")
    if stage == "eyes":
        h = spec["base"]["head"]
        sl = h.setdefault("sliders", {})
        for k in ("canthal_tilt", "eye_platform", "brow_lateral"):
            sl.pop(k, None)
        # by eye (the detector has no crease or fold point; likeloop: his outer third hangs over the corner, a faint
        # crease over a lit platform): set, not fitted
        sl.update({"eye_hood_lateral": 0.5, "eye_crease_depth": 0.4})
        # the opening is the lid's POSE (GNM's expression; the sliders hold the margins): a secant on pose.lid_upper
        ph0, md0, _ = gm.measure("fs_garrett", spec["base"])
        pose = h.setdefault("pose", {})
        x0, f0 = float(pose.get("lid_upper", 0.0)), md0["open"] - ph0["open"]
        x1 = x0 + 0.001
        for _ in range(3):
            pose["lid_upper"] = round(x1, 5)
            f1 = gm.measure("fs_garrett", spec["base"])[1]["open"] - ph0["open"]
            print("lid_upper", x1, "open miss", round(f1, 3))
            if abs(f1) < 0.1 or f1 == f0:
                break
            x0, f0, x1 = x1, f1, x1 - f1 * (x1 - x0) / (f1 - f0)
        pose["lid_upper"] = round(float(x1), 5)
        save(spec)
        names = ["canthal_tilt", "brow_lateral"]
        tg = {"canthal_tilt": (ph0["canthal_tilt"], 0.75), "brow_gap": (ph0["brow_gap"], 0.6),
              "brow_tilt": (ph0["brow_tilt"], 1.5)}
    else:
        ph0, _, _ = gm.measure("fs_garrett", spec["base"])
        names = ["lip_upper_roll", "lip_lower_roll", "lip_bow"]
        tg = {"upper_lip": (ph0["upper_lip"], 0.5), "lower_lip": (min(ph0["lower_lip"], 9.5), 1.0),
              "cupid_bow": (ph0["cupid_bow"], 1.2)}
    ph0, md0, _ = gm.measure("fs_garrett", spec["base"])

    def read(b):
        return gm.measure("fs_garrett", b)[1]
    r = faceslide.fit(spec["base"], tg, names, read=read, on_base=True, log=print, iters=3, step=0.4)
    spec["base"]["head"].setdefault("sliders", {}).update(r["sliders"])
    save(spec)
    print("SLIDERS", r["sliders"])
    for k in tg:
        print(f"{k:14s} photo {ph0[k]:.2f}  before {md0[k]:.2f}  after {r['after'][k]:.2f}")
