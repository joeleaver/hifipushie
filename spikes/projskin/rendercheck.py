"""rendercheck.py <render dir> [limit]: FAIL a render set before review if any tile is magenta-dominant (Blender's
missing-texture / failed-shader colour; render.missing_texture_fraction). Writes <dir>/ERROR and exits 1 so the
batch's eyecmp / skincheck / review never run on it; exits 0 (and removes a stale ERROR) when every tile is clean."""
import glob, json, os, sys
from hifipushie import render
d = sys.argv[1]; lim = float(sys.argv[2]) if len(sys.argv) > 2 else 0.2
tiles = sorted(glob.glob(os.path.join(d, "*.png")))
err = os.path.join(d, "ERROR")
if not tiles:
    open(err, "w").write("rendercheck: no tiles\n"); print("FAIL: no tiles in", d); sys.exit(1)
bad = render.magenta_tiles(tiles, lim)
if bad:
    open(err, "w").write("rendercheck: magenta (missing texture / failed shader) tiles\n" + json.dumps(bad, indent=1) + "\n")
    print(f"FAIL: {len(bad)} / {len(tiles)} tiles magenta-dominant:", json.dumps(bad)); sys.exit(1)
if os.path.exists(err) and open(err).read().startswith("rendercheck"):
    os.remove(err)
print(f"ok: {len(tiles)} tiles, none magenta")
