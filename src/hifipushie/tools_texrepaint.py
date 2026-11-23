"""Texture repaint tools: a generated colour map (concept -> splats -> fused sculpt -> artist retopo -> bake) redone
the way a texture artist would: read as regions and materials, the concept turnaround as the authority, rebuilt at 4K
with material detail, graphics redrawn as clean decals. Playbook: guide(topic="texrepaint"); each step's text is its
function in texrepaint_run.py."""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server.mcpserver import Image

from .mcp_app import mcp


def _img(p) -> Image:
    p = Path(p)
    return Image(data=p.read_bytes(), format="jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "png")


def _txt(d) -> str:
    return json.dumps(d, indent=1, default=str)


@mcp.tool(structured_output=False)
def texrepaint_start(name: str, glb: str, turnaround: str, concept: str | None = None, image: str | None = None,
                     cover: str | None = None, invented: str | None = None, views: list[str] | None = None, k: int = 8):
    """Start a repaint: copy the model (GLB with UVs and its generated maps) and the concept art, register each
    turnaround panel (front | side | back; side = the character's left, facing left) to the model's own silhouette,
    propose the painter's palette (colours of the art where it lands on the model). image: the map to redo (default
    the one most triangles use); cover / invented: the bake's masks (texels the bake really hit / invented), so the
    texture is trusted less there. Shows the registration (model outlines in red on the sheet) and the palette."""
    from . import texrepaint_run as R
    st, pal = R.start(name, glb, turnaround, concept, image, cover, invented, tuple(views or ("front", "side", "back")), k)
    d = R.folder(name)
    return [_img(d / "sheet_register.jpg"), _img(d / "palette.png"),
            f"folder {d}\nregistration (colour_error = mean Lab distance of the model's own texture to the art; < 8 good, "
            f"side/back higher where the texture is wrong): {_txt(st['register'])}\nseen by the art: {st['seen_by_art']}\n"
            f"palette (biggest first; shading splits one paint into lit/shaded entries: merge them): {_txt(pal)}\n"
            "next: check every red outline sits on its figure; name the materials (colour = the lit colour in the "
            "concept; kind; zones for small dark features) -> texrepaint_regions"]


@mcp.tool(structured_output=False)
def texrepaint_regions(name: str, materials: list[dict], sigma: float | None = None, authority: float = 3.0,
                       min_area_cm2: float = 2.0):
    """Read the texture as REGIONS: each texel's material from the generated texture and from the art (projected),
    smoothed on the surface (sigma m, default 0.5 % of the height), the art outvoting the texture where it sees the
    texel squarely. materials: [{name, colour [r,g,b], kind (clay|gloss|horn|metal|wood|paint|flat), rough, paint
    [r,g,b], keep_texture, zones [[z0,z1]] (height fractions), ignore (another part's colour: an eyeball, a held
    prop)}]. Returns the sheet (concept | texture | texture read |
    concept read | regions per view, contradictions outlined red) and the contradictions: where the texture has one
    material and the art shows another (fixed by the art), plus what no view of the art shows (texture kept)."""
    from . import texrepaint_run as R
    rep = R.regions(name, materials, sigma, authority, min_area_cm2)
    top = rep["contradictions"][:15]
    return [_img(R.folder(name) / "sheet_regions.jpg"),
            f"summary: {_txt(rep['summary'])}\ncontradictions (largest {len(top)} of {len(rep['contradictions'])}): "
            f"{_txt(top)}\nnext: judge the regions column against the concept column per view; a wrong material "
            "-> fix its colour / zones and rerun; then texrepaint_paint"]


@mcp.tool(structured_output=False)
def texrepaint_paint(name: str, res: int = 4096, detail: float = 1.0, sharp: float = 10.0, drift: float = 0.035,
                     bump: float = 1.6, keep: list[dict] | None = None, brush: list[dict] | None = None):
    """Paint the maps at res (4K): flat-but-alive base colours measured from the art, clean region edges, each
    material's fine detail (clay fingerprints, horn bands, wood grain, metal wear) in colour, roughness and the normal
    map (the sculpted normal kept). keep: painted details to keep from the generated map, e.g. eyes, nostrils, a mouth
    line: [{"view": "front", "px": [x, y], "r": 0.03, "why": "eye"}] (px read off texrepaint_look) or {"at": [x,y,z]}.
    brush: the same points with "material": paint that material there (a lip crevice that kept the sculpt's dark
    colour, a smear the regions kept)."""
    from . import texrepaint_run as R
    out = R.paint(name, res, detail, sharp, drift, bump, keep, brush)
    return [_img(R.folder(name) / "sheet_paint.jpg"),
            f"{_txt(out)}\nnext: concept | before | after per view: the after must read as the concept; lost painted "
            "details -> keep; graphics -> texrepaint_face; then texrepaint_render"]


@mcp.tool(structured_output=False)
def texrepaint_look(name: str, view: str = "front", crop: list[int] | None = None, image: str | None = None):
    """A gridded view (front|back|side|side_r) of the model with its generated map (image="after": the repaint):
    grid every 10 px, red every 50, in the pixels keep points use. crop [x0,y0,x1,y1] zooms x3."""
    from . import texrepaint_run as R
    p, info = R.look(name, view, crop, image)
    return [_img(p), _txt(info)]


@mcp.tool(structured_output=False)
def texrepaint_face(name: str, part: str):
    """A graphic-carrying part's face (a sign, a number plate) front-on as the generated texture shows it, its outline
    corners numbered (top first, clockwise): read the same corners off the concept for texrepaint_decal."""
    from . import texrepaint_run as R
    p, info = R.decal_face(name, part)
    return [_img(p), _txt(info) + "\nnext: the concept pixel of each numbered corner, same order -> texrepaint_decal"]


@mcp.tool(structured_output=False)
def texrepaint_decal(name: str, part: str, concept: str, concept_pts: list[list[float]], k: int = 4,
                     colours: list[list[int]] | None = None, graphic: str | None = None, why: str = ""):
    """Redraw a part's graphic as a clean decal: the concept's graphic warped onto the face (3 corners: affine, 4:
    homography), posterised to k flat colours (or the given colours), shapes smoothed, specks and anti-alias halos
    removed, laid on the 4K map. graphic: an RGBA image in the face's canvas instead (e.g. from an image model)."""
    from . import texrepaint_run as R
    p, info = R.decal(name, part, concept, concept_pts, k, colours, graphic, why=why)
    return [_img(p), _txt(info) + "\nnext: before | after: every shape of the concept's graphic, none of the smear"]


@mcp.tool(structured_output=False)
def texrepaint_render(name: str, views: list[str] | None = None, hide: list[str] | None = None):
    """EEVEE renders of the repainted asset before (generated maps) and after (the repaint), same cameras: a sheet with
    before over after per view. hide: object names to leave out (stray helpers)."""
    from . import texrepaint_run as R
    p = R.render(name, tuple(views or ("front", "side", "back", "3q")), hide=tuple(hide or ()))
    return [_img(p), "before (top) / after (bottom); judge beside the turnaround (sheet_register.jpg)"]
