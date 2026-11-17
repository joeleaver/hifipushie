"""Artist retopo tools: a fused concept sculpt (oxidegen make_point_cloud's mesh_ply) -> a low cage written by you as
code -> pressed, baked, rigged, range-of-motion checked game character. Every step is its own tool; the playbook is
guide(topic="retopo"), each tool's full text guide(topic="<tool>")."""
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


def _d(name):
    from .artretopo_run import folder
    return folder(name)


# ---- start, look, measure
@mcp.tool(structured_output=False)
def retopo_start(name: str, mesh: str, concept: str | None = None, align: bool = True):
    """Start an artist retopo: copy the fused mesh (PLY) and the concept into the character's folder, check it,
    turn it so its mirror plane is x = 0 (align), show a gridded front / side / top sheet beside the concept. Details:
    guide(topic="retopo_start")."""
    from . import artretopo_run as R, artretopo_study as St
    rep = R.start(name, mesh, concept, align)
    p, txt = St.views(name, "high", ("front", "side", "top"))
    out = [_img(p)]
    c = next(iter(sorted(_d(name).glob("concept.*"))), None)
    if c is not None and c.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        from PIL import Image as PI
        q = _d(name) / "study" / "concept.jpg"; PI.open(c).convert("RGB").save(q, quality=88); out.insert(0, _img(q))
    return out + [f"folder {_d(name)}\ninput check: {_txt(rep)}\n{txt}\nnext: study the sculpt (retopo_look, "
                  "retopo_slices, retopo_measure), decide the loops (guide(topic=\"retopo\")), rebuild eyes / held "
                  "props (retopo_fit, retopo_fit_cylinder, retopo_primitives) if the concept has them, then retopo_cage"]


@mcp.tool(structured_output=False)
def retopo_look(name: str, mesh: str = "high", views: list[str] | None = None, centre: list[float] | None = None,
                scale: float | None = None, step: float = 0.05, style: str = "colour", over: str | None = None,
                folds: bool = False):
    """Gridded orthographic views of a retopo mesh (high, body, cage, low, lod1, final, rigged, or a file
    name) to read positions off. views front|back|side|side_r|top|below|3q|3qr; centre + scale frame a part; style
    colour (vertex colours / textures) | flat (textures unlit) | clay | wire; over="cage" draws the cage in red;
    folds=True paints the press's folded faces red (mesh low). Details: guide(topic="retopo_look")."""
    from . import artretopo_study as St
    p, txt = St.views(name, mesh, tuple(views or ("front", "side", "top")), centre, scale, step, style, over, folds=folds)
    return [_img(p), txt]


@mcp.tool(structured_output=False)
def retopo_slices(name: str, axis: str = "z", at: list[float] | None = None, mesh: str = "high"):
    """Section a retopo mesh with planes (axis z: horizontal at each height in `at`; x or y: vertical) and list every
    region (centroid, extent, area, holes), drawn on one gridded sheet: where rings go, a limb's centre, where two
    regions merge. Details: guide(topic="retopo_slices")."""
    from . import artretopo_study as St
    p, txt = St.slices(name, axis, tuple(at or (0.0,)), mesh)
    return [_img(p), txt]


@mcp.tool(structured_output=False)
def retopo_measure(name: str, what: str, point: list[float] | None = None, direction: list[float] | None = None,
                   lo: list[float] | None = None, hi: list[float] | None = None, radius: float = 0.01,
                   mesh: str = "high") -> str:
    """Numbers off the fused mesh: what = "extreme" (the furthest vertex along direction inside the box lo..hi: a horn's
    or ear's real tip), "ray" (every surface hit from point along direction), "thickness" (through the part at the
    surface nearest point), "colour" (mean vertex colour within radius of point). Details:
    guide(topic="retopo_measure")."""
    from . import artretopo_measure as M
    from .artretopo_sculpt import Sculpt
    from .artretopo_study import _mesh_path
    s = Sculpt(_mesh_path(_d(name), mesh))
    if what == "extreme":
        return _txt(M.extreme(s, lo, hi, direction))
    if what == "ray":
        return _txt(M.ray(s, point, direction))
    if what == "thickness":
        return _txt(M.thickness(s, point))
    if what == "colour":
        return _txt(M.colour_at(s, point, radius))
    raise ValueError('what: "extreme", "ray", "thickness" or "colour"')


@mcp.tool(structured_output=False)
def retopo_check(name: str, what: str = "low") -> str:
    """Checks again, as numbers: what = "input" (watertight, outward volume, parts, mirror error), "cage" (closed quad
    manifold, genus, winding notes) or "low" (the pressed mesh: folds and where, volume, open edges). Details:
    guide(topic="retopo_check")."""
    from . import artretopo_check as C, artretopo_steps as S
    from .artretopo_mesh import Mesh, read_ply
    d = _d(name)
    if what == "input":
        return _txt(C.check_input(Mesh.load(d / "high.ply")))
    if what == "cage":
        V, F, _ = read_ply(d / "cage.ply")
        return _txt(C.check_cage(V, [list(map(int, q)) for q in F]))
    if what == "low":
        return _txt(S.check_low(name))
    raise ValueError('what: "input", "cage" or "low"')


# ---- eyes and props
@mcp.tool(structured_output=False)
def retopo_fit(name: str, near: list[float], radius: float, rgb: list[int] | None = None, tol: int = 60) -> str:
    """Fit a sphere to the fused mesh's vertices within `radius` of `near` (only those coloured within tol of rgb, if
    given): an eyeball's centre and radius (rms: how round it really is). Details: guide(topic="retopo_fit")."""
    from .artretopo_sculpt import Sculpt, fit_sphere
    s = Sculpt(_d(name) / "high.ply"); P = s.verts_near(near, radius, rgb, tol)
    c, Rr, rms = fit_sphere(P)
    return _txt({"points": len(P), "c": [round(float(x), 4) for x in c], "R": round(Rr, 4), "rms": round(rms, 5)})


@mcp.tool(structured_output=False)
def retopo_fit_cylinder(name: str, axis: str, at: list[float], pick: list[float]) -> str:
    """Fit a cylinder to an accessory from cross-sections across `axis` at the stations `at` (the region nearest `pick` in
    each, pick in the section's plane): centre, radius, per-slice radii (where they stay equal is the cylinder's
    length). An accessory rebuilt as a primitive. Details: guide(topic="retopo_fit_cylinder")."""
    from . import artretopo_measure as M
    from .artretopo_sculpt import Sculpt
    return _txt(M.fit_cylinder(Sculpt(_d(name) / "high.ply"), axis, at, pick))


@mcp.tool(structured_output=False)
def retopo_primitives(name: str, eyes: list[dict] | None = None, items: list[dict] | None = None,
                      cut: list[dict] | None = None, margin: float = 0.006, parts: list[dict] | None = None):
    """Rebuild eyeballs and held accessories as primitives and cut them out of the fused mesh (-> high_body.ply, the biggest part
    kept; props.json). eyes [{c, R}]; items [{name, type: cylinder|sphere, axis, c, R, length, bone: Head|Jaw}]; cut:
    your own cut shapes (default: each one grown by margin); parts [{name, cut: [shapes], bone, extrusion, reach,
    near}]: soft pieces kept as their own (a comb, a wattle). Details: guide(topic="retopo_primitives")."""
    from . import artretopo_run as R, artretopo_study as St
    rep = R.props(name, eyes, items, cut, margin, parts)
    p, txt = St.views(name, "body", ("front", "side"), style="clay")
    return [_img(p), _txt(rep) + "\n" + txt]


# ---- the cage and the press
@mcp.tool(structured_output=False)
def retopo_cage(name: str, code: str, part: str | None = None):
    """Run your retopo cage code (Python; in scope: c the Cage, s the body mesh, full the whole fused mesh, props, az,
    X, Y, Z, np, math, fit_sphere) and save the low cage; refuses an open or non-manifold cage; shows it in red over
    the fused mesh. Every version is kept (cage_v<N>.py). part: a separate part's own cage (low = the pressed body in
    scope). Details: guide(topic="retopo_cage")."""
    from . import artretopo_run as R, artretopo_study as St
    rep = R.cage(name, code, part)
    if rep["faults"]:
        return f"cage v{rep['version']} REFUSED (fix the code, call again):\n{_txt(rep)}"
    stem = f"part_{part}_cage.ply" if part else "cage"
    p, txt = St.views(name, "high", ("front", "side", "back", "3q"), style="clay", over=stem)
    return [_img(p), f"cage v{rep['version']}: {_txt(rep)}\n{txt}\nnext: retopo_press" + (f" part={part!r}" if part else "")]


@mcp.tool(structured_output=False)
def retopo_press(name: str, levels: int = 1, relax: int = 6, after: int = 1, part: str | None = None):
    """Subdivide the cage `levels` times, press it onto the fused mesh along normals (pinned vertices stay invented), relax
    `relax` rounds, keep that as LOD1, subdivide `after` more levels unpressed (the form); count folds. part: a
    separate part's cage (no LOD1). Details: guide(topic="retopo_press")."""
    from . import artretopo_steps as S
    rep = S.press(name, levels, relax, after, part)
    return [_img(rep["sheet"]), _txt(rep) + "\nnext: retopo_look mesh=low style=wire folds=true where "
            "the folds are; then retopo_bake"]


# ---- bake, fill, assemble, compare
@mcp.tool(structured_output=False)
def retopo_bake(name: str, res: int = 2048, extrusion: float = 0.012, reach: float = 0.03, thin_extrusion: float = 0.004,
                thin_reach: float = 0.015):
    """UVs from your seams, then bake the fused mesh's normals + colour onto the retopo mesh, LOD1 and the accessories, with the
    masks the repair needs (coverage, islands, thin parts, invented skin diffused on the surface, the mouth inside).
    Raw maps: retopo_fill repairs them. Details: guide(topic="retopo_bake")."""
    from . import artretopo_steps as S
    rep = S.bake(name, res, extrusion, reach, thin_extrusion, thin_reach)
    return [_img(_d(name) / "bake_sheet.jpg"), _txt(rep) + "\nnext: retopo_fill"]


@mcp.tool(structured_output=False)
def retopo_fill(name: str) -> str:
    """Repair every bake in place: thin parts from the short bake, rays that found nothing from their neighbours,
    invented skin from the surface-diffused colour with flat normals, the mouth inside dark; colours pushed over the
    UV gutters. Details: guide(topic="retopo_fill")."""
    from . import artretopo_steps as S
    return _txt(S.fill(name)) + "\nnext: retopo_assemble"


@mcp.tool(structured_output=False)
def retopo_assemble(name: str):
    """Put the repaired maps into the baked retopo mesh -> final.glb (body, accessories, LOD1), shown beside the fused mesh.
    Details: guide(topic="retopo_assemble")."""
    from . import artretopo_steps as S
    S.assemble(name)
    p = S.compare(name)
    return [_img(p), f"wrote {_d(name) / 'final.glb'}; sculpt left, yours right\nnext: judge it (retopo_compare for "
            "other views, retopo_look mesh=final style=flat for the maps alone); then retopo_armature"]


@mcp.tool(structured_output=False)
def retopo_compare(name: str, result: str = "final.glb", views: list[dict] | None = None, head: list[float] | None = None):
    """The fused mesh and a retopo result (final.glb, rigged.glb, lod1_rigged.glb, low.ply) rendered alike, side by side: the
    standard body / head / back, or your own views [{name, view: [dx, dy, dz], target, scale}]. Details:
    guide(topic="retopo_compare")."""
    from . import artretopo_steps as S
    return [_img(S.compare(name, result, views, head)), "sculpt left, result right"]


# ---- rig, range of motion, LOD1, report
@mcp.tool(structured_output=False)
def retopo_armature(name: str, joints: dict, helpers: list[str] | None = None) -> str:
    """Build the Mixamo armature of a retopo character from your joints (LEFT side for paired joints; jaw + jaw_tip add
    a Jaw bone), weight it (bone heat, half-angle helpers, the cage's jaw group, empty vertices from their
    neighbours), parent the accessories, weight LOD1; write rigged.glb and rigged.blend. Details: guide(topic="retopo_armature")."""
    from . import artretopo_steps as S
    return _txt(S.rig(name, joints, tuple(helpers or ("Arm", "ForeArm", "Leg")))) + "\nnext: retopo_rom"


@mcp.tool(structured_output=False)
def retopo_rom(name: str, poses: list | None = None, clavicle: float = 0.3, close: dict | None = None,
               close_ups: bool = True):
    """Range of motion of a retopo character: pose, measure (folds, edges squashed < 0.5 / stretched > 1.8) and render every pose
    (the standard 16, or names and your own {name: [[bone, [axis], deg] | [bone, "aim", [dir]], ...]}); close-ups in
    clay with bad faces red (standard and / or close={name: {view, target, scale}}). Details: guide(topic="retopo_rom")."""
    from . import artretopo_steps as S
    rom = S.rom(name, poses, clavicle, close, close_ups)
    d = _d(name); out = [_img(d / "rom_sheet.jpg")]
    for f in ("close_rom.jpg", "close_mouth.jpg", "close_custom.jpg"):
        if (d / f).exists():
            out.append(_img(d / f))
    return out + [(d / "rom_final.txt").read_text() + "\nnext: fix the worst pose where its cause is (cage loops, "
                  "joints, pins); then retopo_lod and retopo_report"]


@mcp.tool(structured_output=False)
def retopo_lod(name: str):
    """Export a retopo character's LOD1 on its own (lod1_rigged.glb: the pressed coarse mesh with its own bake, the same
    armature and accessories), and show it. Details: guide(topic="retopo_lod")."""
    from . import artretopo_steps as S
    rep = S.lod(name)
    return [_img(_d(name) / "lod1_rest.png"), _txt(rep) + f"\nwrote {_d(name) / 'lod1_rigged.glb'}"]


@mcp.tool(structured_output=False)
def retopo_report(name: str, decisions: str, out_dir: str | None = None) -> str:
    """Write the run's report: your decision log (markdown: what you saw, what you chose and why, what you changed
    after looking) plus every deliverable and number, into out_dir (default <folder>/report). Details:
    guide(topic="retopo_report")."""
    from . import artretopo_report
    return artretopo_report.write(name, decisions, out_dir)
