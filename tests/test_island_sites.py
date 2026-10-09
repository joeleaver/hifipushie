"""Pushieworld's island (their spec, read from their repo or a copy in the workspace; skipped when neither exists): its
site pads stand where 3f2d1f1 put them, and every pad honours its above_water (pushieworld notes 67 / 116: vale_village
was set from no water at all, 56 m from the vale river, and stood 4 m UNDER the river's level with above_water 3, with
no warning). uv run python tests/test_island_sites.py"""
import json
import os
import time
from pathlib import Path

import numpy as np

from hifipushie import terrain

SPECS = [Path("/home/joe/dev/pushieworld/pushie/terrain/island.json"),
         Path(os.environ.get("HIFIPUSHIE_HOME", "workspace")) / "terrain" / "pw_island2" / "spec.json"]
# 3f2d1f1's pads; vale_village is the fix (33.85 there: under the river)
LEVELS = {"crown_camp": 69.9, "downs_green": 51.67, "pencil_landing": 3.0, "vale_village": 41.52, "kaze_lookout": 82.48}


def main():
    spec = next((p for p in SPECS if p.exists()), None)
    if spec is None:
        print("skipped: no island spec here")
        return
    t = time.time()
    T = terrain.Terrain(json.loads(spec.read_text()))
    raw = json.loads(spec.read_text())["sites"]
    for name, want in LEVELS.items():
        got = T.sites[name]["level"]
        assert abs(got - want) < 0.3, (name, got, want)
    wet = ~np.isnan(T.water)
    for name, s in T.sites.items():
        d = np.hypot(T.X - s["xy"][0], T.Y - s["xy"][1])
        if not wet.any() or d[wet].min() - s["radius"] > max(60.0, s["radius"]):
            continue
        wl = float(T.water[wet][np.argmin(d[wet])])
        asked = raw[name].get("above_water")
        if asked is not None:
            assert s["level"] - wl >= asked - 0.5, (name, s["level"], wl, asked)
        assert s["level"] > wl, (name, s["level"], wl)
    assert not any("vale_village" in w and "above the water" in w for w in T.warnings), T.warnings
    print(f"ok island sites ({time.time() - t:.0f} s): " + ", ".join(f"{n} {T.sites[n]['level']:.1f}" for n in LEVELS))


if __name__ == "__main__":
    main()
