"""mkgc.py <dst> <head model>: Garrett's ONE current dressing (the coordinator, 2026-10-09):
- head: <head model>'s base (gj8: the joint solve's identity, residuals, squint pose);
- hair: tess's gc_c1 (h7's groom with groom.fit and the concept's colour; its hair_*.npz);
- skin: g4_garrett's skin.py layers with skin2's stubble and d9's lips (melanin 4.5, blood 1.2); the lashes' paint at
  its defaults (lashes geometry: base.lashes, default on for human heads);
- eyes: lidfold with eyedetail's Garrett values (the "roll 3.0" is lidfold's fold_width); the crease sliders dropped;
- paint: g4_garrett's own layers that skin.py has no equivalent of (KEEP); the old ~30-layer likeloop stack and
  over_lip_seam / 180_mouth_inside (obsolete: a sealed mouth) dropped."""
import json
import shutil
import sys

from hifipushie import hair, store

dst, head = sys.argv[1], sys.argv[2]
H = store.HOME
ld = lambda m: (lambda s: s.get("spec", s))(json.loads((H / m / "spec.json").read_text()))  # noqa: E731
sp, g4, gc = ld(head), ld("g4_garrett"), ld("gc_c1")
# (faces2, 2026-10-10: the grey share is grey_amount + grey_locks x each lock's grey, and gc_c1's groom already
# greys its locks 0.35 top .. 0.8 temples (mean 0.49): grey_amount 0.45 on top of that made ~75% grey strands, silver.
# Measured on the concept's crop: top median luminance 0.30 (#594d44), sides 0.36. Was top 0.59 / sides 0.45 (silver).
# grey_amount 0 + this darker warm base: top 0.35, sides 0.28 (dark sides: a dark-haired man greying on top);
# grey_amount 0.12: top 0.41, sides 0.32, reads salt-and-pepper at sheet size (faces2/out a_g3 / a_g5))
GREY = {"grey_amount": 0.12, "grey_locks": 0.9, "lit": "#4a4039", "sheen": "#5e544b", "gap": "#201b18", "grey": "#9a958f",
        "eevee_sat": 0.45}
KEEP = ("g4_nostril.L", "g4_body_tone", "g4_neck_cool")   # nostril interiors, the body's tone off the face, the neck's
sp["paint"] = {k: v for k, v in (g4.get("paint") or {}).items() if k in KEEP}
skin = json.loads(json.dumps(g4["skin"]))
skin["lips"] = {**(skin.get("lips") or {}), "melanin": 4.5, "blood": 1.2}
skin.setdefault("hair", {})["stubble"] = {"amount": 1.0, "style": "short", "length": 0.002, "grey": 0.35, "cheeks": 0.75,
                                          "color": "#3a342f"}
skin["hair"].pop("lashes", None)
sp["skin"] = skin
sp["parts"] = g4["parts"]
sp["hair"] = hair.carry("gc_c1")  # (gc_c1 has its groom.fit)
# the concept's hair is short salt-and-pepper GREY: gc_c1's colour match chased the concept's colour bands and
# rendered dark brown (eevee_sat 0.6 over brown lit / sheen). Greyed: a grey strand share, near-neutral lit / sheen /
# gap, eevee's saturation at the measured 0.35 or under; the strands' wave off (a neat short cut)
look = sp["hair"].setdefault("look", {})
look.update({k: v for k, v in GREY.items()})
sp["hair"].setdefault("strands", {}).update({"wave": 0.0, "frizz": 0.015})
h = sp["base"]["head"]
h["fold"] = {"crease_height": 3.0, "crease_depth": 0.6, "crease_width": 1.1, "fold_overhang": 0.8, "fold_width": 3.0}
h["sliders"] = {k: v for k, v in (h.get("sliders") or {}).items()
                if k not in ("eye_crease_height", "eye_crease_depth", "eye_platform", "eye_hood", "eye_hood_lateral", "age_lid_fold")}
sp["base"].pop("lashes", None)
d = H / dst
d.mkdir(exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp, indent=1))
shutil.copy(H / head / "human_refs.json", d / "human_refs.json")
for f in (H / "gc_c1").glob("hair_*.npz"):
    shutil.copy(f, d / f.name)
print("wrote", d, "paint kept:", list(sp["paint"]), "sliders:", h["sliders"])
