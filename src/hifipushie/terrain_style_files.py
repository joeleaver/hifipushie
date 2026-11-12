"""Files: tileable images, the layers and overlay written, the code key and cache, `write`, `export_styles`. Part of the terrain styles (terrain_style.py has the overview)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from . import terrain_style
from .terrain_style import _srgb_lin, layer_colour, layer_sheet, resolve, sheet
from .terrain_style_fields import overlay, texture
from .terrain_style_zones import layer_edge, rock_scale, season_colours, snow_numbers, style_fields

# ------------------------------------------------------------------------------------------------ files
def _png(path, a, mode=None):
    from PIL import Image
    Image.fromarray(np.ascontiguousarray(a), mode).save(path)


def _q8(a):
    return np.round(np.clip(a, 0, 1) * 255).astype(np.uint8)


def _q16(a):
    return np.round(np.clip(a, 0, 1) * 65535).astype(np.uint16)


def tileable(img: np.ndarray) -> float:
    """The wrap seam's step against the steps beside it (1 = invisible), the worst channel."""
    a = np.asarray(img, float)
    a = a if a.ndim == 3 else a[..., None]
    seam = np.abs(a[0] - a[-1]).mean() + np.abs(a[:, 0] - a[:, -1]).mean()
    # (against the mean step between ALL neighbouring rows / columns: against the one row beside it, a sparse texture
    # with a pebble on the seam read 4x)
    beside = np.abs(np.diff(a, axis=0)).mean() + np.abs(np.diff(a, axis=1)).mean()
    q = 1.0 / 255  # (steps under an 8-bit level are invisible: a flat blobby swatch's 1e-4 steps read 1.7 as noise)
    return round(float((seam + q) / (beside + q)), 3)


def write_layers(out: Path, st: dict, refs: dict, layers, px: int = terrain_style.PX) -> dict:
    """materials/<style>/<layer>_albedo|_normal|_height.png for `layers`; returns the manifest entries per layer."""
    d = out / "materials" / st["name"]
    d.mkdir(parents=True, exist_ok=True)
    import shutil
    res = {}
    cache = _cache_dir()
    for nm in layers:
        if nm not in refs:
            continue
        col = layer_colour(st, nm, refs)
        Ls = layer_sheet(st, nm)
        key = hashlib.sha1(json.dumps([st["name"], nm, Ls, [round(float(x), 6) for x in col], int(px), _code()],
                                      sort_keys=True).encode()).hexdigest()[:24]
        kd = cache / key if cache else None
        has_plain = any(o.get("fade_small") for o in (Ls.get("ops") or []))
        kinds = ("albedo", "normal", "height") + (("plain_albedo", "plain_normal") if has_plain else ())
        meta = None
        if kd is not None and (kd / "meta.json").exists():  # (the PNGs as made before: identical bytes)
            meta = json.loads((kd / "meta.json").read_text())
            for k in kinds:
                shutil.copyfile(kd / f"{k}.png", out / f"materials/{st['name']}/{nm}_{k}.png")
        if meta is None:
            S = texture(st, nm, col, px)
            hr = float(max(np.abs(S["height"]).max(), 1e-5))
            # (contract 4: the albedo carries the height in its alpha, 8-bit, 0.5 = 0, +- height_m like _height.png:
            # an engine packing them at load paid seconds of startup)
            rgba = lambda alb, h: np.concatenate([_q8(alb), _q8(h / hr * 0.5 + 0.5)[..., None]], -1)
            imgs = [("albedo", rgba(S["albedo"], S["height"])), ("normal", _q8(S["normal"] * 0.5 + 0.5)),
                    ("height", _q16(S["height"] / hr * 0.5 + 0.5))]
            if has_plain:
                Sp = texture(st, nm, col, px, plain=True)
                imgs += [("plain_albedo", rgba(Sp["albedo"], Sp["height"])),
                         ("plain_normal", _q8(Sp["normal"] * 0.5 + 0.5))]
            for k, a in imgs:
                _png(out / f"materials/{st['name']}/{nm}_{k}.png", a[::-1],
                     "I;16" if a.dtype == np.uint16 else None)  # (image rows run down)
            meta = {"size_m": S["size_m"], "projection": S["projection"], "height_m": round(hr, 5),
                    "roughness": S["roughness"], "wrap_seam": max(tileable(S["albedo"]),
                                                                  tileable(Sp["albedo"]) if has_plain else 0.0)}
            if kd is not None:
                try:
                    kd.mkdir(parents=True, exist_ok=True)
                    for k in kinds:
                        shutil.copyfile(out / f"materials/{st['name']}/{nm}_{k}.png", kd / f"{k}.png")
                    (kd / "meta.json").write_text(json.dumps(meta))
                except OSError:
                    pass
        files = {k: f"materials/{st['name']}/{nm}_{k}.png" for k in ("albedo", "normal", "height")}
        res[nm] = {**files, **{k: meta[k] for k in ("size_m", "projection", "height_m")},
                   "color": [round(float(x), 4) for x in col],
                   "color_linear": [round(float(x), 4) for x in _srgb_lin(col)],
                   "roughness": meta["roughness"], "normal_strength": float(Ls.get("normal_strength", 1.0)),
                   "v_jitter_m": float(Ls.get("v_jitter_m", 0.0)) if meta["projection"] == "triplanar" else 0.0,
                   "seasons": season_colours(st, nm, col), "wrap_seam": meta["wrap_seam"],
                   "albedo_alpha": "height"}  # (contract 4: alpha = height, 8-bit, (a - 0.5) x 2 x height_m metres)
        if has_plain:  # (the layer without its fade_small ops: shown on small or thin rock, by maps.rock_scale)
            fade = {**terrain_style.SMALL_FADE, **(Ls.get("small_fade") or {})}
            res[nm]["small"] = {"albedo": f"materials/{st['name']}/{nm}_plain_albedo.png",
                                "normal": f"materials/{st['name']}/{nm}_plain_normal.png",
                                "face_m": fade["face_m"], "thick_m": fade["thick_m"]}
    return res


def _code():
    if terrain_style._CODE is None:
        src = Path(__file__).parent  # (terrain_style.py was split, C427: its code is every module of the family)
        terrain_style._CODE = hashlib.sha1(b"".join((src / f"{m}.py").read_bytes()
                                                    for m in ("terrain_style", *terrain_style.MODULES))).hexdigest()
    return terrain_style._CODE


def _cache_dir():
    """Where written layer PNGs are kept by their inputs ($HIFIPUSHIE_STYLE_CACHE; 0 = off): making a dab layer
    takes seconds, copying it none."""
    import os
    v = os.environ.get("HIFIPUSHIE_STYLE_CACHE")
    if v in ("0", "off", "false"):
        return None
    return Path(v) if v else Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "hifipushie" / "terrain_style"


def write_overlay(out: Path, st: dict) -> dict | None:
    O = overlay(st)
    if O is None:
        return None
    d = out / "materials" / st["name"]
    d.mkdir(parents=True, exist_ok=True)
    fa, fn = f"materials/{st['name']}/overlay_albedo.png", f"materials/{st['name']}/overlay_normal.png"
    _png(out / fa, _q8(0.5 * O["mult"])[::-1])
    _png(out / fn, _q8(O["normal"] * 0.5 + 0.5)[::-1])
    return {"albedo": fa, "normal": fn, "size_m": O["size_m"], "fade_m": O["fade_m"], "strength": O["strength"],
            "how": "albedo x (1 + s (2 a - 1)), s = strength x (1 - smoothstep(fade_m[0], fade_m[1], view distance)); "
                   "normal RNM-combined by s; top projection on the ground, triplanar on rock"}


def write(out: Path, T, refs: dict, spec: dict | None = None, tiles: list | None = None, px: int = terrain_style.PX,
          layers=None) -> dict:
    """Every style's files into `out` (an export directory, or any directory) and the manifest section. `refs` = the
    realistic layers' reference looks ({layer: {"color", "roughness", "scale"}}, Materials.layer_ref), `tiles` =
    [(i, j, (x0, y0, x1, y1))] to say which styles reach each tile. Cached per sheet + layer + code (texture making
    is a few seconds a layer)."""
    from PIL import Image
    out = Path(out)
    spec = spec if spec is not None else T.spec
    styles = resolve(spec)
    if not any(s["name"] == "realistic" for s in styles):
        styles_all = styles + [{"name": "realistic", "zones": [], "band": terrain_style.BAND, "sheet": sheet("realistic")}]
    else:
        styles_all = styles
    layers = [nm for nm in (layers or terrain_style.STYLE_LAYERS) if nm in refs]
    F = style_fields(T, styles)
    order = F["order"]
    sdir = out / "styles"
    sdir.mkdir(parents=True, exist_ok=True)
    maps = {"sd": {}, "weights": []}
    (x0, y0), (x1, y1) = T.spec["extent"]
    for nm in (order if styles else []):
        fn = f"styles/{nm}_sd.png"
        _png(out / fn, _q16(F["sd"][nm] / (2 * terrain_style.SD_RANGE) + 0.5)[::-1], "I;16")
        maps["sd"][nm] = fn
    if styles:
        W = [F["w"][nm] for nm in order]
        for g in range(0, len(W), 4):
            grp = W[g:g + 4] + [np.zeros_like(W[0])] * (4 - len(W[g:g + 4]))
            fn = f"styles/weights{g // 4}.png"
            Image.fromarray(np.ascontiguousarray(_q8(np.stack(grp, -1))[::-1]), "RGBA").save(out / fn)
            maps["weights"].append(fn)
    if getattr(T, "H", None) is not None:  # (how big the rock is: where `fade_small` ops give way to plain textures)
        Hf, thick = rock_scale(T)
        rg = np.stack([Hf / terrain_style.ROCK_SCALE["face_m"], thick / terrain_style.ROCK_SCALE["thick_m"], np.zeros_like(Hf)], -1)
        _png(out / "styles/rock_scale.png", _q8(rg)[::-1])
        maps["rock_scale"] = "styles/rock_scale.png"
    per_tile = []
    for (i, j, (bx0, by0, bx1, by1)) in (tiles or []):
        sel = (T.X >= bx0 - T.cell) & (T.X <= bx1 + T.cell) & (T.Y >= by0 - T.cell) & (T.Y <= by1 + T.cell)
        reach = [nm for nm in order if (F["w"][nm][sel].max() if styles else 1.0) > 0.005]
        per_tile.append({"i": i, "j": j, "styles": reach})
    entries = []
    for s in styles_all:
        st = s["sheet"]
        lay = write_layers(out, st, refs, layers, px)
        entries.append({"name": s["name"], "zones": s["zones"], "band_m": s["band"], "about": st.get("about", ""),
                        "sd": maps["sd"].get(s["name"]),
                        "weights": ([f"styles/weights{order.index(s['name']) // 4}.png", order.index(s["name"]) % 4]
                                    if styles else None),
                        "macro": float(st.get("macro", 1.0)), "macro_normal": float(st.get("macro_normal", 1.0)),
                        "detail": float(st.get("detail", 0.0)), "overlay": write_overlay(out, st),
                        "layer_edge": layer_edge(st),
                        "layers": lay, "snow": snow_numbers(st), "rock": st.get("rock") or {}})
    return {"contract": {"version": terrain_style.CONTRACT, "changes": {str(k): v for k, v in terrain_style.CONTRACT_LOG.items()}},
            "order": order, "styles": entries,
            "maps": {"sd": maps["sd"], "weights": maps["weights"], "range_m": terrain_style.SD_RANGE,
                     "rock_scale": ({"file": maps["rock_scale"], "face_m": terrain_style.ROCK_SCALE["face_m"],
                                     "thick_m": terrain_style.ROCK_SCALE["thick_m"],
                                     "how": "RGB 8-bit, linear, the same grid as the sd maps: face height = R x face_m, "
                                            "half-thickness in plan = G x thick_m (metres)"}
                                    if maps.get("rock_scale") else None),
                     "extent": [[x0, y0], [x1, y1]], "cell_m": float(T.cell),
                     "uv": "north-up images over the terrain's extent: pixel centre (c, r) at x = x0 + (c + 0.5) cell, "
                           "y = y1 - (r + 0.5) cell; sd 16-bit, value 0.5 = the edge, (v - 0.5) x 2 x range_m metres, "
                           "positive inside the style's zone; weights RGBA in `order`, groups of 4, sum 1"},
            "tiles": per_tile, "recipe": terrain_style.RECIPE,
            "note": "colours: `color` sRGB, `color_linear` / `tint_linear` linear; albedo PNGs are sRGB, normal / "
                    "height PNGs linear (never sRGB). Shape (rock, landform) per style is in the tiles' geometry; "
                    "textures and seasons here are for the engine's shader."}


def refs_of(T) -> dict:
    """The realistic layers' reference looks for terrain T without the 3D field (as Materials.layer_ref: the rock
    colour is the median of the steep cells' rock colour)."""
    from . import terrain_mesh as tm
    from . import terrain_materials
    refs = {k: dict(v) for k, v in tm.LAYERS.items()}
    rg = terrain_materials.rock_colours(T)
    steep = T._slope() > 45
    rr = np.median(rg[steep] if steep.any() else rg.reshape(-1, 3), 0)
    refs["rock"]["color"] = [round(float(x), 3) for x in rr]
    refs["wet_rock"]["color"] = [round(float(x) * 0.45, 3) for x in rr]
    return refs


def export_styles(T, out, mats=None, G=None, px: int = terrain_style.PX) -> dict:
    """The styles' files for terrain T into `out` (an export_terrain tiles directory, or a fresh one beside it): the
    textures, the zone maps, styles.json (= the manifest section) and, when out/manifest.json exists, its "styles"
    key. `mats` / `G` (terrain_materials.Materials / Grid) are made when not given (the 3D field's setup: seconds)."""
    from . import terrain_mesh as tm
    from . import terrain_materials, terrain_tile_jobs, terrain_tile_mesh
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    cfg = {**tm.DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {})}
    if mats is None:
        field = terrain_tile_jobs.build_field(T, cfg)[0]
        mats = terrain_materials.Materials(T, field)
    if G is None:
        G = terrain_tile_mesh.Grid(T, cfg)
    refs = {nm: mats.layer_ref(nm) for nm in mats.layers}
    tiles = []
    for j in range(G.nj):
        for i in range(G.ni):
            lo, hi = G.bounds(i, j)
            tiles.append((i, j, (float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1]))))
    sec = write(out, T, refs, tiles=tiles, layers=mats.layers, px=px)
    (out / "styles.json").write_text(json.dumps(sec, indent=1))
    mf = out / "manifest.json"
    if mf.exists():
        M = json.loads(mf.read_text())
        M["styles"] = sec
        mf.write_text(json.dumps(M, indent=1))
    return sec


def summary(sec: dict) -> str:
    """A few lines for a tool reply: each style, its zones, layers and how many tiles it reaches."""
    lines = [f"styles (contract {sec['contract']['version']}): {', '.join(sec['order'])}"]
    for s in sec["styles"]:
        n = sum(1 for t in sec["tiles"] if s["name"] in t["styles"])
        lines.append(f"- {s['name']}: zones {s['zones'] or ['(everywhere else)']}, band {s['band_m']:g} m, "
                     f"{n} of {len(sec['tiles'])} tiles, macro {s['macro']:g}, layers "
                     + ", ".join(f"{k} {v['size_m']:g} m" for k, v in s["layers"].items())
                     + (", overlay" if s.get("overlay") else ""))
    worst = max((v["wrap_seam"], s["name"], k) for s in sec["styles"] for k, v in s["layers"].items())
    lines.append(f"worst wrap seam: {worst[1]} {worst[2]} {worst[0]:g} (1 = invisible; over 1.5 shows)")
    return "\n".join(lines)
