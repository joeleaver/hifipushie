"""dress.py <solved head> <out> [stage ..]: the DRESSING of a GNM-native head with nothing of ours on its surface
(stages: skin brows hair; default all). A block-in fork of the solved head (the source is never written):
 skin: PLAIN: the refs model's zones / features (freckles, flush) dropped, wrinkles 0, no folds; pupil 0.33 (GNM's
       rest pupil 0.50 is a dim-room pupil), canthus 0.8, the drawn iris at GNM's limbus (no iris_size); then
       skin_from_reference groups tone / lips / eyes / brows ONLY (folds OFF, no stubble, no freckles, no zones).
 brows: brow_read(match=True) (blockin_brows.apply).
 hair: th_T66's STYLE WORDS through tie_hair (carry_from th_T66: its hairline rule, look, strand dials) + groom seed 0.
Logs to $S/out/dress_<out>_<stage>.txt. Run through heavy.sh."""
import json, sys, time
from hifipushie import blockin as bi, blockin_brows as bb, hair, server, skin_read as sr, store

S = "/mnt/data/hifipushie/nativedefault/out"
src, out = sys.argv[1:3]
stages = sys.argv[3:] or ["skin", "brows", "hair"]
assert out.startswith(("nd_", "tess_n")), out
T66 = {"tie": "low", "side": 20, "tightness": 0.85, "neatness": 0.95, "front": {"looseness": 0.6, "drape": 0.6},
       "wisps": {"amount": 1.0, "softness": 0.7}, "tail": {"length": 0.195, "wave": 0.6, "fullness": 0.43, "tousle": 0.55}}
t0 = time.time()
if "skin" in stages:
    bi.fork(src, out, replace=True)
    sp = store.load(out)
    sk = sp["skin"]
    gone = {k: sk.pop(k) for k in ("zones", "features", "folds", "fold_expressions", "makeup") if k in sk}
    sk["wrinkles"] = {"amount": 0.0}
    e = sk.setdefault("eyes", {})
    e.pop("iris_size", None)
    e.update(pupil=0.33, canthus=0.8)
    assert not sp.get("strokes") and not sp.get("paint"), (sp.get("strokes"), sp.get("paint"))
    bi._save(out, sp, f"nativedefault dress from {src}: plain skin (dropped {sorted(gone)}), pupil 0.33, canthus 0.8", bi._refs(out))
    print("dropped from the skin:", json.dumps(gone))
    res = sr.apply(out, groups=("tone", "lips", "eyes", "brows"), rounds=2, stubble=False, log=lambda s: None)
    open(f"{S}/dress_{out}_skin.txt", "w").write(res["text"])
    print(res["text"][-3000:])
    print("skin now:", json.dumps(store.load(out)["skin"]))
if "brows" in stages:
    r = bb.apply(out)
    open(f"{S}/dress_{out}_brows.txt", "w").write(r["text"])
    print(r["text"][-1500:])
if "hair" in stages:
    r = hair.tie_style(out, T66, carry_from="th_T66", look={"cycles_width": 1.8, "cycles_sat": 0.65}, note="nativedefault: th_T66's style words on the native head")
    print("tie_style:", str({k: v for k, v in r.items() if k != "made"})[:600])
    print(server.groom_hair(out, groom={"seed": 0}, replace=True)[:1500])
    sp = store.load(out)
    print("hair: fit", sp["hair"]["groom"].get("fit"), "locks", len(sp["hair"].get("locks") or []), "tied", json.dumps(sp["hair"]["groom"].get("tied")))
print(f"{time.time() - t0:.0f} s")
