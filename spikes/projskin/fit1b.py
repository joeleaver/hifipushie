"""fit1b.py: STAGE 1b, the procedural skin FITTED to the de-lit atlas.
  fit1b.py start <truth> <dst>     dst = truth (its references and cameras) with a DIFFERENT skin: same lightness class, other
                                   blood / undertone, default zones and lips, no freckles: what the fit starts from (synthetic test)
  fit1b.py fit <src> <dst> [k=v]   skin_project.apply(src -> dst, opacity 0: the measurement) then skin_from_reference(dst) from
                                   the atlas; prints both reports, the residual before / after, saves the residual maps to out/<dst>/
  fit1b.py table <truth> <fitted> <start>   the parameter-recovery table (skin_read's parameter paths)"""
import copy, json, os, sys
from hifipushie import blockin as bi, skin_project as sp, skin_read as sr, store

OUT = "/mnt/data/hifipushie/projskin/out"
cmd = sys.argv[1]
if cmd == "start":
    truth, dst = sys.argv[2:4]
    spec = copy.deepcopy(store.load(truth))
    sk = spec["skin"]
    t = sk["tone"]
    sk["tone"] = {**t, "blood": round(float(t.get("blood", 0.04)) * 1.8, 4), "undertone": round(float(t.get("undertone", 0.0)) + 0.25, 4)}
    for k in ("zones", "lips", "features", "projection"):
        sk.pop(k, None)
    rj = copy.deepcopy(bi._refs(truth))
    rj["blockin"] = {**(rj.get("blockin") or {}), "root": dst}
    bi._save(dst, spec, f"{truth} with another skin (the fit's start)", rj)
    print(dst, "tone", sk["tone"], "truth", t)
elif cmd == "fit":
    src, dst = sys.argv[2:4]
    kw = dict(a.split("=", 1) for a in sys.argv[4:])
    os.makedirs(f"{OUT}/{dst}", exist_ok=True)
    a = sp.apply(src, out=dst, opacity=0.0)
    print(a["text"])
    r0 = sp.residual(dst, save=f"{OUT}/{dst}/residual_before.png", log=lambda s: None)
    print("\nBEFORE the fit:\n" + r0["text"])
    groups = tuple(g for g in sr.DEFAULT_GROUPS if g not in ("eyes", "folds"))
    f = sr.apply(dst, groups=groups, rounds=int(kw.get("rounds", 2)), brow_shape=kw.get("brows", "1") == "1", log=lambda s: None)
    print("\n" + f["text"])
    # placed marks (moles): where the atlas has them, as skin.features.moles.at (a placed mark is not noise)
    mk = sp.marks(dst)
    print("\n" + mk["text"])
    spec = store.load(dst)
    if mk["marks"] and kw.get("marks", "1") == "1":
        ft = dict((spec["skin"].get("features") or {}))
        old = ft.get("moles")
        ft["moles"] = {"at": [m["at"] for m in mk["marks"]], "size": round(2 * float(sorted(m["radius"] for m in mk["marks"])[len(mk["marks"]) // 2]), 5)}
        spec["skin"]["features"] = ft
        store.save(dst, spec, f"placed marks from the atlas ({len(mk['marks'])}; was {old})", checked=False)
    json.dump(mk["marks"], open(f"{OUT}/{dst}/marks.json", "w"), indent=1)
    r1 = sp.residual(dst, save=f"{OUT}/{dst}/residual_after.png", log=lambda s: None)
    print("\nAFTER the fit:\n" + r1["text"])
    json.dump({"before": r0["regions"], "after": r1["regions"]}, open(f"{OUT}/{dst}/residual.json", "w"), indent=1)
elif cmd == "atlas":      # the measurement only: skin_project.apply(src -> dst), the photo colour layer off
    print(sp.apply(sys.argv[2], out=sys.argv[3], opacity=0.0)["text"])
elif cmd == "table":
    truth, fitted, start = (store.load(m)["skin"] for m in sys.argv[2:5])
    print(f"{'parameter':28s} {'truth':>9s} {'start':>9s} {'fitted':>9s}   error left (fitted - truth) / error at the start")
    for g, paths in sr.GROUPS.items():
        for p in paths:
            try:
                a, b, c = (float(sr._get(s, p)) for s in (truth, start, fitted))
            except Exception:  # noqa: BLE001
                continue
            if abs(a - b) < 1e-6 and abs(c - a) < 1e-6:
                continue
            print(f"{p:28s} {a:9.3f} {b:9.3f} {c:9.3f}   {c - a:+.3f} / {b - a:+.3f}")
