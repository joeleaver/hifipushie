"""garrett4.py: round 3 on Garrett (the coordinator's list, 2026-10-09): EYES (eye scale 1.0, the lid-opening
expression regions out, brow_height / eye_depth measured on the photo into the MAP, upper-lid hood fitted: half as
identity, half left to the squint pose), NECK from the body (om_garrett's girth, 31.9 cm, not the MAP's prior), the
same structure as rs2_m3, then AGE as an alternative (headfit's age direction in the identity + thinner lips + a
shallow wide mid-cheek thinning).
  run.sh garrett4.py        -> models rs2_n0 (MAP), rs2_n3 (structure, eyes, neck), rs2_n4 (+ age), six-view sheets"""
import copy
import json
import os

import numpy as np

import garrett
import garrett3
import measured as ms
import structure
from hifipushie import headfit, humanfit, humanfit_map, humanmacro as hm, likeness_read as lr, store

D2 = os.environ.get("D2")
NECK_CM = 31.9
EXTRA = ("brow_height", "eye_depth")


def measure():
    M, rms, cols = garrett3.low_model()
    F, f, d = garrett3.photo_features(cols)
    z = ms.predict(M, F)[0]
    out = {}
    for k in garrett3.WIDTH_MACROS + EXTRA:
        i = hm.NAMES.index(k)
        out[k] = (round(float(z[i]), 2), round(float(rms[i] * 1.5), 2))
    print("measured on the photo (points + low outline; sigma = 1.5 x cv rms):", out)
    return out


def save(tag, sp, b, vs, cams, note):
    store.save(tag, {**copy.deepcopy(sp), "base": b}, "refstudy2 round 3: " + note)
    (store.HOME / tag / "human_refs.json").write_text(json.dumps({"views": vs, "cameras": cams}, indent=1))
    structure.info(tag, b)
    print(lr.render_views(tag, f"{D2}/out/six_{tag}.png", base=b))


def neck_to(b, cm):
    """humanfit's neck girth is read on the BODY's own neck (body + bridge vertices): it is the body's whatever the
    head's identity does (31.9 cm on every Garrett copy). What the MAP can change is the head's part of the neck,
    under the jaw (macro neck_width): unmeasured in the photo (collar), so it goes to the population's mean."""
    c0 = humanfit.identity(b)
    z = hm.read(c0)["neck_width"]
    nb = humanfit._with_identity(b, hm.apply(c0, {"neck_width": -z}, held=True))
    print(f"neck girth (body) {humanfit.state(nb)['measures']['neck_circ']:.1f} cm (om_garrett {cm}); head's neck_width macro {z:+.2f} -> "
          f"{hm.read(humanfit.identity(nb))['neck_width']:+.2f} sigma")
    return nb


def main(scale=1.25):
    meas = measure()
    read = {**meas, **garrett3.SHAPE_READ, "eye_depth": meas["eye_depth"]}   # the shape words win where both speak (jaw_square)
    sp = garrett.hist("lk_garrett", 1)
    vs = garrett.refs()
    b0 = copy.deepcopy(sp["base"])
    # the lid-opening regions every Garrett copy carried, at HALF: with them out and the squint posed, fit_hood said
    # "the picture's upper lids are HIGHER than the hood-free face's" (-7.5 mm asked): GNM's own lids rest low
    b0["head"]["expression"] = {k: 0.5 * float(v) for k, v in (b0["head"].get("expression") or {}).items()}
    b0["head"]["eyes"] = 1.0
    b0["head"]["pose"] = {k: v for k, v in garrett3.POSE.items() if k != "lid_upper"}
    b, rep = humanfit_map.fit(b0, vs, read=read, read_sd=0.5)
    if rep.get("refused"):
        print("REFUSED:", rep["refused"][:200])
        b, rep = humanfit_map.fit(b0, vs, read=read, read_sd=0.5, force=True)
    print("fit with the pose:", [(v["rms_mm"], v["lens_mm"]) for v in rep["views"]], rep["plausibility"])
    print("read asked -> got:", {k: (v["asked"], v["got"]) for k, v in rep["read"].items()})
    b["head"]["identity"] = {k: float(v) * scale for k, v in b["head"]["identity"].items()}
    cams = rep["cameras"]
    # the hood, fitted on the upper lids of the pictures WITH the pose on; half of it kept as identity
    bh, rh = humanfit.fit_hood(b, vs, cams)
    asked = float(rh.get("asked_mm", rh.get("amount", 0.0)) or 0.0)
    print("fit_hood:", {k: v for k, v in rh.items() if k in ("amount_before", "asked_mm", "amount", "note", "rms_px_before", "refused")})
    b["head"].pop("pose", None)
    save("rs2_n0", sp, b, vs, cams, "MAP: eyes 1.0, no lid-opening regions, measured widths + brow height, shape words, expression as pose")
    b = neck_to(b, NECK_CM)
    c = hm.apply(humanfit.identity(b), {"chin_projection": 1.2, "jaw_angle": 2.0}, held=True)
    b = humanfit._with_identity(b, c)
    b["head"]["shape"] = {"planes": 2.3, "lean": {"under_jaw": 0.006, "jowl": 0.0025},
                          "chin": {"cleft": 0.004, "cleft_width": 0.005, "cleft_lobes": 0.003, "cleft_length": 0.018},
                          "nose_tip": {"up": 5, "round": 0.5}, "hood": round(max(min(asked, 5.0), 0.0) * 0.5 / 1000, 5)}
    save("rs2_n3", sp, b, vs, cams, "n0 + neck from the body + rs2_m3's structure + half the fitted hood")
    # AGE: headfit's age direction (MakeHuman's 80-year move fitted in GNM's components, orthogonal to sex), thinner
    # lips, a shallow wide thinning of the mid cheek
    ax = headfit._body_axes()[:, 1]
    c0 = humanfit.identity(b)
    z0 = hm.read(c0)
    for sg in (1.0, -1.0):
        z1 = hm.read(c0 + sg * ax[:len(c0)])
        if z1["lip_fullness"] < z0["lip_fullness"]:
            break
    print("age axis x1: macros that move most:", sorted(((round(z1[k] - z0[k], 2), k) for k in z0), key=lambda t: -abs(t[0]))[:8])
    ba = humanfit._with_identity(b, hm.apply(c0 + 0.8 * sg * ax[:len(c0)], {"lip_fullness": -0.5}, held=True))
    ba["head"]["shape"]["hollow"] = {"amount": 0.002, "radius": 0.03}
    it = humanfit.integrity(ba, humanfit.state(ba), humanfit.state(b))
    print("age step:", humanfit.verdict(it)[:200])
    save("rs2_n4", sp, ba, vs, cams, "n3 + age: headfit age axis x0.8, lip_fullness -0.5, mid-cheek thinning 2 mm / 30 mm")


if __name__ == "__main__":
    main()
