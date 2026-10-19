"""mkE.py: copies th_E* of other human models WITH their hair (spec.json + human_refs.json only; the originals are
never written), for the hairline's before / after. th_E9 = a template-base body with a default short groom."""
import json
import os
import shutil

from hifipushie import store

E = {"th_E1": "garrett_v20", "th_E2": "om_garrett", "th_E3": "hu_s_wavy", "th_E4": "hu_s_child", "th_E5": "hc_golfer",
     "th_E6": "rs_real_S3", "th_E7": "dg_hair_long", "th_E8": "lk_mem", "th_E9": "base_test", "th_E0": "hu_s_tousled"}

if __name__ == "__main__":
    for dst, src in E.items():
        # private heads never feed a spike: their tag prefixes live outside the repo (comma list)
        assert not src.startswith(tuple(p for p in os.environ.get("HIFIPUSHIE_PRIVATE_PREFIXES", "").split(",") if p))
        d = store.HOME / dst
        d.mkdir(exist_ok=True)
        sp = json.loads((store.HOME / src / "spec.json").read_text())
        if not sp.get("hair"):
            sp["hair"] = {"groom": {}}
        (d / "spec.json").write_text(json.dumps(sp, indent=1))
        if (store.HOME / src / "human_refs.json").exists():
            shutil.copy(store.HOME / src / "human_refs.json", d / "human_refs.json")
        h = sp["hair"]
        b = sp.get("base") or {}
        print(dst, "=", src, "| base", (b.get("body") or {}).get("source") or b.get("template"), "| hair keys", sorted(h),
              "| groom keys", sorted((h.get("groom") or {}))[:14], "| locks", len(h.get("locks") or {}))
