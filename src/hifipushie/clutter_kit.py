"""Looks, the manifest and `kit`. Part of clutter (clutter.py has the overview)."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from . import clutter
from .clutter import presets, styles
from .clutter_export import export, report

# ------------------------------------------------------------------------------------------- looks, kits, manifest
def look(folders, out: str, distances=(2.5, 10.0, 40.0), lods=(0, 1, 2), scale: float = 1.0, clay: bool = False, season: str = "summer") -> str:
    """A sheet of exported clutter folders (a row each): every variant side by side on rough grass at each distance
    with the LOD drawn there; the far views are centre crops of a 1280 x 720 frame at a 50 deg lens, enlarged (real
    pixels). Blender (EEVEE), ~10 s a picture. Returns `out`."""
    import os
    import subprocess
    import tempfile
    from PIL import Image, ImageDraw
    from .render import BLENDER
    tmp = Path(tempfile.mkdtemp(prefix="cklook"))
    rows = []
    for fi, fo in enumerate([folders] if isinstance(folders, (str, Path)) else folders):
        fo = Path(fo)
        J = json.loads(next(fo.glob("*_seasons.json")).read_text())
        cl = J["clutter"]
        vs = cl["variants"]
        n = len(vs)
        width = n * 1.25 * scale
        tiles = []
        items, views, meta = [], [], []
        for di, (d0, lod) in enumerate(zip(distances, lods)):
            oy = 300.0 * di
            items += [{"glb": str(fo / v["lods"][min(lod, len(v["lods"]) - 1)]["file"]), "at": [(i - (n - 1) / 2) * 1.25 * scale, oy, 0],
                       "yaw": 25 * i, "scale": scale, "shadow": lod < len(v["lods"]) - 1 or len(v["lods"]) < 3} for i, v in enumerate(vs)]
            d = max(d0, width * 0.95 + 0.8) if di == 0 else d0
            png = tmp / f"r{fi}_{di}.png"
            views.append({"eye": [0.35 * d, oy - d, 1.6 if d > 3 else 1.1], "look": [0, oy, cl["height_m"] * scale * 0.35], "fov": 50, "out": str(png), "res": [1280, 720]})
            meta.append((d0, d, lod, png))
        job = {"items": items, "clay": clay, "views": views}
        tex = (J.get("seasons", {}).get(season) or {})
        job["albedo"] = next((v_["baseColorTexture"]["file"] for v_ in tex.values() if isinstance(v_, dict) and v_.get("baseColorTexture")), None) if season != "summer" else None
        jp = tmp / f"j{fi}.json"
        jp.write_text(json.dumps(job))
        subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(clutter.HERE / "blender_clutter.py"), "--", str(jp)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ})
        for d0, d, lod, png in meta:
            im = Image.open(png).convert("RGB")
            ppm = 640 / 0.4663 / (d * 1.06)
            cw = int(min(1280, max(120, (width + 0.6) * ppm)))
            ch = int(cw * 360 / 960)
            z = max(1, 960 // cw)
            cy = 360 + int(0.02 * 720)
            t = im.crop((640 - cw // 2, cy - ch // 2, 640 + cw // 2, cy + ch // 2)).resize((960, 360), Image.NEAREST if z > 1 else Image.LANCZOS)
            ImageDraw.Draw(t).text((6, 4), f"{fo.name}  {d0:g} m  LOD{lod}" + (f"  (x{z} pixels)" if z > 1 else ""), fill=(255, 255, 255))
            tiles.append(t)
        rows.append(tiles)
    sheet = Image.new("RGB", (960 * len(distances), 360 * len(rows)))
    for r, tiles in enumerate(rows):
        for c, t in enumerate(tiles):
            sheet.paste(t, (960 * c, 360 * r))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return str(out)


def glb_size(path) -> dict:
    """A GLB's extent from its POSITION accessors' min / max (glTF: Y up): {"width_m" (largest plan dimension), "height_m"}."""
    d = open(path, "rb").read()
    n = struct.unpack("<I", d[12:16])[0]
    G = json.loads(d[20: 20 + n])
    lo, hi = np.full(3, 1e9), np.full(3, -1e9)
    for m in G.get("meshes", []):
        for pr in m["primitives"]:
            a = G["accessors"][pr["attributes"]["POSITION"]]
            lo, hi = np.minimum(lo, a["min"]), np.maximum(hi, a["max"])
    return {"width_m": round(float(max(hi[0] - lo[0], hi[2] - lo[2])), 3), "height_m": round(float(hi[1]), 3)}


def manifest(root) -> dict:
    """Write <root>/clutter.json: terrain clutter kind -> the folder to draw it with, per style (what exists under
    root), with the instance convention. An engine reads this once, then each folder's <stem>_seasons.json."""
    root = Path(root)
    sts = styles()
    kinds = {}
    for kind, how in clutter.TERRAIN_KINDS.items():
        per = {}
        for st in sts:
            f = root / f"{clutter.SHORT.get(st, st)}_{how.get('asset') or how['plant']}"
            js = list(f.glob("*_seasons.json")) if f.is_dir() else []
            if js:
                J = json.loads(js[0].read_text())
                per[st] = {"folder": f.name, "json": js[0].name, "grade": J.get("grade"), "contract": J.get("contract", {}).get("version"),
                           "variants": len(J["clutter"]["variants"]) if J.get("clutter") else 1}
                if not J.get("clutter"):  # a plant is at its own size: the row's scale is a width in metres
                    g0 = f / (J["glb"][:-4] + "_LOD0.glb")
                    if g0.exists():
                        per[st].update(glb_size(g0))
                        per[st]["instance_scale"] = "row scale / width_m (a plant is exported at its own size, not 1 m across)"
        pre = clutter.HERE / "clutter_presets" / f"{how.get('asset')}.json"
        info = json.loads(pre.read_text()) if how.get("asset") and pre.exists() else {}
        kinds[kind] = {"what": how["what"], "z": how["z"], "kit": "clutter" if how.get("asset") else "plant (groundcover grade)",
                       "size_range_m": info.get("size_range"), "place": info.get("place"), "styles": per,
                       "missing": [st for st in sts if st not in per]}
    M = {"about": "terrain clutter kinds (clutter.csv / the tiles manifest's clutter.kinds) -> the asset folder that draws each, per style",
         "row": "x, y, z, kind, scale, yaw, squash[, place]: scale = the largest plan dimension in m (assets are 1 m at scale 1), yaw deg about up (0 = the "
                "asset's +X along world +X), squash = RELATIVE height (1 = the asset's own proportions): instance = T(x, y, z) * Rz(yaw) * S(scale, scale, scale * squash)",
         "variant": "variant = hash(row) % variants (a folder's json lists them); mirror in x for every other row if you want more",
         "lods": "each folder's json: clutter.lod_switch_m x the instance's scale",
         "kinds": kinds}
    (root / "clutter.json").write_text(json.dumps(M, indent=1))
    return M


def kit(root, kinds=None, style_names=None, progress=None, **over) -> dict:
    """Export a whole kit into root (<style>_<kind>/ folders, "realistic" -> "real") and write the manifest."""
    out = {}
    for st in style_names or styles():
        for kind in kinds or presets():
            sh = clutter.SHORT.get(st, st)
            J = export({"kind": kind, "style": st, **over}, Path(root) / f"{sh}_{kind}", stem=f"ck_{kind}_{sh}", progress=progress)
            out[f"{sh}_{kind}"] = J
            if progress:
                progress(report(J))
    manifest(root)
    return out
