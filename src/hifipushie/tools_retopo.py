"""Artist retopo tools: a fused concept sculpt (oxidegen make_point_cloud's mesh_ply) -> a low cage written by you as
code -> pressed, baked, rigged, range-of-motion checked game character. The playbook: guide(topic="retopo")."""
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
def retopo_start(name: str, mesh: str, concept: str | None = None):
    """Start an artist retopo: copy the fused sculpt (a PLY: z up, facing -y, mirror x = 0) and the concept image into
    the character's folder, check the input, and show a gridded study sheet (front, side, top). Details:
    guide(topic="retopo_start")."""
    from . import artretopo_run as R, artretopo_study as St
    rep = R.start(name, mesh, concept)
    p, txt = St.views(name, "high", ("front", "side", "top"))
    out = [_img(p)]
    c = next(iter(sorted(R.folder(name).glob("concept.*"))), None)
    if c is not None and c.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        from PIL import Image as PI
        q = R.folder(name) / "study" / "concept.jpg"; PI.open(c).convert("RGB").save(q, quality=88); out.insert(0, _img(q))
    return out + [f"folder {R.folder(name)}\ninput check: {_txt(rep)}\n{txt}\nnext: study the sculpt (retopo_look, "
                  "retopo_slices), decide the loops (guide(topic=\"retopo\")), rebuild eyes / held props as primitives "
                  "(retopo_fit, retopo_props) if the concept has them, then retopo_cage"]


@mcp.tool(structured_output=False)
def retopo_look(name: str, mesh: str = "high", views: list[str] | None = None, centre: list[float] | None = None,
                scale: float | None = None, step: float = 0.05, style: str = "colour", over: str | None = None):
    """Gridded orthographic views of a mesh in the retopo folder (high, body, cage, low, lod1, final) to read
    positions off: views front|back|side|side_r|top|below|3q|3qr; centre + scale frame a part (a head, a hand);
    style colour|clay|wire; over="cage" draws the cage in red over it. Details: guide(topic="retopo_look")."""
    from . import artretopo_study as St
    p, txt = St.views(name, mesh, tuple(views or ("front", "side", "top")), centre, scale, step, style, over)
    return [_img(p), txt]


@mcp.tool(structured_output=False)
def retopo_slices(name: str, axis: str = "z", at: list[float] | None = None, mesh: str = "high"):
    """Cut the sculpt with planes (axis z: horizontal at each height in `at`; x or y: vertical) and list every region
    with its centroid, extent and area, drawn on one gridded sheet: where rings go, a limb's centre, where an arm
    fuses to the body. Details: guide(topic="retopo_slices")."""
    from . import artretopo_study as St
    p, txt = St.slices(name, axis, tuple(at or (0.0,)), mesh)
    return [_img(p), txt]


@mcp.tool(structured_output=False)
def retopo_fit(name: str, near: list[float], radius: float, rgb: list[int] | None = None, tol: int = 60) -> str:
    """Fit a sphere to the sculpt's vertices within `radius` of `near` (only those coloured within tol of rgb, if
    given): an eyeball's centre and radius (rms says how round it really is). Details: guide(topic="retopo_fit")."""
    from . import artretopo_run as R
    from .artretopo_sculpt import Sculpt, fit_sphere
    s = Sculpt(R.folder(name) / "high.ply"); P = s.verts_near(near, radius, rgb, tol)
    c, Rr, rms = fit_sphere(P)
    return _txt({"points": len(P), "c": [round(float(x), 4) for x in c], "R": round(Rr, 4), "rms": round(rms, 5)})


@mcp.tool(structured_output=False)
def retopo_props(name: str, eyes: list[dict] | None = None, items: list[dict] | None = None, cut: list[dict] | None = None,
                 margin: float = 0.006):
    """Rebuild eyes and held props as primitives and cut them out of the sculpt (-> high_body.ply, props.json).
    eyes [{c, R}]; items [{name, type: cylinder|sphere, axis, c, R, length, bone: Head|Jaw}]; cut: your own cut shapes
    (default: each one grown by margin). Details: guide(topic="retopo_props")."""
    from . import artretopo_run as R, artretopo_study as St
    rep = R.props(name, eyes, items, cut, margin)
    p, txt = St.views(name, "body", ("front", "side"), style="clay")
    return [_img(p), _txt(rep) + "\n" + txt]


@mcp.tool(structured_output=False)
def retopo_cage(name: str, code: str):
    """Run your cage code (Python; in scope: c the Cage, s the body sculpt, full the whole sculpt, props, az, X, Y, Z,
    np, math, fit_sphere) and save the low cage; refuses an open or non-manifold cage; shows it in red over the
    sculpt. Every version is kept (cage_v<N>.py). Details: guide(topic="retopo_cage")."""
    from . import artretopo_run as R, artretopo_study as St
    rep = R.cage(name, code)
    if rep["faults"]:
        return f"cage v{rep['version']} REFUSED (fix the code, call again):\n{_txt(rep)}"
    p, txt = St.views(name, "high", ("front", "side", "back", "3q"), style="clay", over="cage")
    return [_img(p), f"cage v{rep['version']}: {_txt(rep)}\n{txt}\nnext: retopo_press"]


@mcp.tool(structured_output=False)
def retopo_press(name: str, levels: int = 1, relax: int = 6, after: int = 1):
    """Subdivide the cage `levels` times, press it onto the sculpt along normals (pinned vertices stay invented), relax
    `relax` rounds, save LOD1, subdivide `after` more levels unpressed (the form); count folds. Details:
    guide(topic="retopo_press")."""
    from . import artretopo_run as R, artretopo_steps as S
    rep = S.press(name, levels, relax, after)
    return [_img(R.folder(name) / "wire_sheet.jpg"), _txt(rep) + "\nnext: look close (retopo_look mesh=low "
            "style=wire) where folds are; then retopo_bake"]


@mcp.tool(structured_output=False)
def retopo_bake(name: str, res: int = 2048, extrusion: float = 0.012, reach: float = 0.03, head: list[float] | None = None):
    """UVs from your seams, bake normals + colour from the sculpt (props from the whole sculpt), repair the bake
    (misses, thin parts, invented skin, the mouth inside), write final.glb; show the sculpt beside it. Details:
    guide(topic="retopo_bake")."""
    from . import artretopo_run as R, artretopo_steps as S
    rep = S.bake(name, res, extrusion, reach, head)
    return [_img(R.folder(name) / "final_cmp.jpg"), _txt(rep) + "\nnext: judge final_cmp (sculpt left, yours right); "
            "then retopo_rig"]


@mcp.tool(structured_output=False)
def retopo_rig(name: str, joints: dict, helpers: list[str] | None = None, clavicle: float = 0.3):
    """Rig final.glb (Mixamo names; joints for the LEFT side; jaw + jaw_tip add a Jaw bone), weight it, run the range of
    motion (16 poses: folds, squashed / stretched edges), weight LOD1, write rigged.glb. Details:
    guide(topic="retopo_rig")."""
    from . import artretopo_run as R, artretopo_steps as S
    rom = S.rig(name, joints, tuple(helpers or ("Arm", "ForeArm", "Leg")), clavicle)
    d = R.folder(name)
    out = [_img(d / "rom_sheet.jpg"), _img(d / "close_rom.jpg")]
    if (d / "close_mouth.jpg").exists():
        out.append(_img(d / "close_mouth.jpg"))
    return out + [(d / "rom_final.txt").read_text() + _txt(rom["rig"]) + "\nnext: fix the worst pose where its "
                  "cause is (cage loops, joints, pins); then retopo_report"]


@mcp.tool(structured_output=False)
def retopo_report(name: str, decisions: str, out_dir: str | None = None) -> str:
    """Write the run's report: your decision log (markdown: what you saw, what you chose and why, what you changed
    after looking) plus every deliverable and number, into out_dir (default <folder>/report). Details:
    guide(topic="retopo_report")."""
    from . import artretopo_report
    return artretopo_report.write(name, decisions, out_dir)
