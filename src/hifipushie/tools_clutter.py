"""Ground clutter tools: kits of rocks, logs and litter for terrain."""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server.mcpserver import Image

from . import store
from .mcp_app import mcp

@mcp.tool(structured_output=False)
def make_clutter(kind: str = "", style: str = "realistic", out_dir: str | None = None, seed: int = 1, variants: int | None = None,
                 form: dict | None = None, paint: dict | None = None, color: list | None = None, moss: float | None = None,
                 lods: list | None = None, look: bool = False):
    """Make a terrain clutter asset (boulder, river_rock, cobbles, slab, driftwood, bush, litter; "" lists them) in a
    style (realistic|blobby|anime|cartoon|pixar): GLB variants with LODs, one atlas, a seasons json. form / paint /
    color / moss overrides, seed, variants, lods, out_dir, look=True for a sheet. Details:
    guide(topic="make_clutter")."""
    from . import clutter as ck
    from . import clutter_export, clutter_kit as clutter_kit_mod
    if not kind:
        return json.dumps({"kinds": {k: json.loads((ck.HERE / "clutter_presets" / f"{k}.json").read_text()).get("about", "") for k in ck.presets()},
                           "styles": {s_: ck.style_sheet(s_).get("about", "") for s_ in ck.styles()}}, indent=1)
    spec = {"kind": kind, "style": style, "seed": seed}
    for k_, v_ in (("variants", variants), ("form", form), ("paint", paint), ("color", color), ("moss", moss), ("lods", lods)):
        if v_ is not None:
            spec[k_] = v_
    st = ck.style_sheet(style)["name"]
    sh = ck.SHORT.get(st, st)
    out = Path(out_dir) if out_dir else store.HOME / "clutter" / f"{sh}_{kind}"
    J = clutter_export.export(spec, out, stem=f"ck_{kind}_{sh}")
    text = f"wrote {out}\n" + clutter_export.report(J)
    if not look:
        return text
    png = out / "look.png"
    clutter_kit_mod.look(out, str(png))
    return [Image(data=png.read_bytes(), format="png"), text]


@mcp.tool(structured_output=False)
def look_clutter(folders: list[str], season: str = "summer", clay: bool = False, scale: float = 1.0, save: str | None = None):
    """A sheet of exported clutter folders at 2.5 / 10 / 40 m with LODs. season, clay, scale, save. Details:
    guide(topic="look_clutter")."""
    from . import clutter_kit as clutter_kit_mod
    png = Path(save) if save else Path(folders[0]) / f"look_{season}.png"
    clutter_kit_mod.look(folders, str(png), scale=scale, clay=clay, season=season)
    return [Image(data=png.read_bytes(), format="png"), f"saved {png}"]


@mcp.tool(structured_output=False)
def clutter_kit(out_dir: str, kinds: list[str] | None = None, styles: list[str] | None = None) -> str:
    """Export every clutter kind in every style into out_dir plus clutter.json (kind -> folder per style). kinds,
    styles. Details: guide(topic="clutter_kit")."""
    from . import clutter_kit as clutter_kit_mod
    lines = []
    K = clutter_kit_mod.kit(out_dir, kinds, styles, progress=lines.append)
    M = json.loads((Path(out_dir) / "clutter.json").read_text())
    miss = {k: v["missing"] for k, v in M["kinds"].items() if v["missing"]}
    return f"{len(K)} folders in {out_dir}; manifest clutter.json" + (f"; missing: {miss}" if miss else "") + "\n" + "\n".join(lines)
