"""Detail swatches side by side through the same detail pipeline: one preview export of rock_round's near pass (macro
maps, lines, projection), then per swatch the export's materials/ swatch images are rewritten and the views rendered
with render_tiles(textured="detail"). Swatches: "procedural" (terrain_swatch.swatch), "scan:<set>" (CC0 photoscans,
asset pack rock_scans: `uv run hifipushie-assets fetch rock_scans`), "old" (the swatch module at a git revision,
`--old-rev`, default HEAD). Also writes each swatch's swatch_stats and repetition profile to <out>/stats.json.
uv run python examples/scan_compare.py <out dir> [alps|pebble] [sources...] [--render-only] [--old-rev REV]
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import rock_round  # noqa: E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from hifipushie import terrain, terrain_mesh, terrain_swatch as ts  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def old_swatch(rev):
    """terrain_swatch.swatch as it was at git revision `rev` (loaded as a module of the package)."""
    src = subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:src/hifipushie/terrain_swatch.py"], check=True,
                         capture_output=True, text=True).stdout
    p = Path(ts.__file__).with_name("_old_swatch.py")
    p.write_text(src)
    try:
        spec = importlib.util.spec_from_file_location("hifipushie._old_swatch", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.swatch(None)
    finally:
        p.unlink()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0])
    name = args[1] if len(args) > 1 and args[1] in rock_round.SPECS else "alps"
    sources = [a for a in args[1:] if a not in rock_round.SPECS] or ["old", "procedural", "scan:rock_face_03",
                                                                    "scan:rock_06", "scan:cliff_side",
                                                                    "scan:rock_wall_02"]
    rev = sys.argv[sys.argv.index("--old-rev") + 1] if "--old-rev" in sys.argv else "HEAD"
    V = json.loads((Path(__file__).parent / "rock_views.json").read_text())
    T = terrain.load(rock_round.ROOT / rock_round.SPECS[name])
    cfg = V[name]["near"]
    o = out / f"{name}_near"
    if "--render-only" not in sys.argv:
        terrain_mesh.preview_tiles(T, o, cfg["center"], cfg.get("radius", 40.0), 8.0, {**(cfg.get("cfg") or {}),
                                                                                      "detail": True})
    M = json.loads((o / "manifest.json").read_text())
    stats = {}
    for src in sources:
        S = old_swatch(rev) if src == "old" else ts.detail_swatch(None, src)
        de = ts.write(o, None, "rock", S=S)
        stats[src] = {**ts.swatch_stats(S), "repetition_fade": de["fade"]}
        M["detail"].update({k: de[k] for k in ("size_m", "height_m", "texels_per_m", "fade", "source")})
        (o / "manifest.json").write_text(json.dumps(M, indent=1))
        views = rock_round.views_for(T, cfg["views"])
        tag = src.replace(":", "_")
        for v in views:
            v["out"] = str(o / f"{tag}_{v['name']}.png")
        terrain_mesh.render_tiles(T, o, views, size=(1200, 750), samples=32, trees=False, textured="detail")
        print(src, "done", flush=True)
    (out / "stats.json").write_text(json.dumps(stats, indent=1))
    # one sheet per view: every swatch side by side, labelled
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    for v in rock_round.views_for(T, cfg["views"]):
        ims = [Image.open(o / f"{s.replace(':', '_')}_{v['name']}.png").convert("RGB") for s in sources]
        w, h = ims[0].size
        sc = 0.5
        W, H = int(w * sc), int(h * sc)
        cols = 3
        rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (W * cols, (H + 26) * rows), (20, 20, 20))
        d = ImageDraw.Draw(sheet)
        for k, (s, im) in enumerate(zip(sources, ims)):
            x, y = (k % cols) * W, (k // cols) * (H + 26)
            sheet.paste(im.resize((W, H), Image.LANCZOS), (x, y + 26))
            d.text((x + 6, y + 4), {"old": f"ours before ({rev})", "procedural": "ours retuned"}.get(s, s),
                   fill=(255, 255, 255), font=font)
        sheet.save(out / f"{name}_{v['name']}_sheet.png")


if __name__ == "__main__":
    main()
