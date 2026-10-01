"""Macro maps + tiling rock detail vs unique bakes, on rock_round's fixed views (examples/rock_views.json).
uv run python examples/detail_round.py <out dir> <alps|pebble> <far|near> <variant ...> [--render-only]
Variants: "u16" / "u32" (unique maps at 16 / 32 texels/m, the baked material), "m4" (unique macro maps at 4 texels/m
+ the tiling rock detail, drawn as the manifest's detail recipe: textured="detail"); any "u<d>" / "m<d>" works.
Prints the bake's cost per variant (texels, CPU s in the bake jobs, the tile stage's wall) into <out>/costs.json."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import rock_round  # noqa: E402

from hifipushie import terrain, terrain_mesh  # noqa: E402


def cost(o):
    M = json.loads((o / "manifest.json").read_text())
    st = {s["stage"].strip(): s for s in M["profile"]["stages"]}
    tex = sum(L["maps"]["texels"] for e in M["tiles"] for L in e["lods"] if L and L.get("maps"))
    busy = sum(st[k]["busy_s"] for k in ("_job_bake", "_job_finish") if k in st)
    tiles = [s for s in M["profile"]["stages"] if s["stage"].startswith("tiles (")]
    return {"texels": tex, "bake_cpu_s": round(busy, 1), "tile_stage_wall_s": round(sum(s["wall_s"] for s in tiles), 1),
            "density": M.get("texel_density_used"), "total_s": round(M["timing_s"]["total before check"], 1),
            "detail": {k: M["detail"][k] for k in ("wrap_seam", "tileable", "strike_stretch_p5_p50_p95")
                       if k in M["detail"]} if M.get("detail") else None}


def main():
    out = Path(sys.argv[1])
    name, ps = sys.argv[2], sys.argv[3]
    variants = [a for a in sys.argv[4:] if not a.startswith("--")]
    V = json.loads((Path(__file__).parent / "rock_views.json").read_text())
    T = terrain.load(rock_round.ROOT / rock_round.SPECS[name])
    cfgv = V[name][ps]
    costs = json.loads((out / "costs.json").read_text()) if (out / "costs.json").exists() else {}
    for var in variants:
        d = float(var[1:])
        o = out / f"{name}_{ps}_{var}"
        cfg = dict(cfgv.get("cfg") or {})
        if var[0] == "m":
            cfg["detail"] = True
        if d > 20:
            cfg["texture_max"] = 4096
        t0 = time.time()
        if "--render-only" not in sys.argv:
            terrain_mesh.preview_tiles(T, o, cfgv["center"], cfgv.get("radius", 40.0), d, cfg)
            costs[f"{name}_{ps}_{var}"] = {**cost(o), "preview_s": round(time.time() - t0, 1)}
            print(var, costs[f"{name}_{ps}_{var}"], flush=True)
        views = rock_round.views_for(T, cfgv["views"])
        for v in views:
            v["out"] = str(o / f"{name}_{v['name']}.png")
        terrain_mesh.render_tiles(T, o, views, size=(1200, 750), samples=32, trees=False, box=cfgv.get("box"),
                                  textured="detail" if var[0] == "m" else True)
        (out / "costs.json").write_text(json.dumps(costs, indent=1))


if __name__ == "__main__":
    main()
