"""Hard-surface-from-the-point-cloud tools: a fused concept sculpt (oxidegen make_point_cloud: fused mesh + its renders)
-> clean fitted parts (turned, swept, tubes, boxes, plates, radial arrays) -> built, checked, baked (colour projected
from the renders), optionally rigged with rigid joints. For props, vehicles, furniture, buildings: anything an artist
would model from primitives, not sculpt. Characters press a cage (retopo_*); hard surface FITS.
The playbook is guide(topic="hardsurf"); each tool's text guide(topic="<tool>")."""
from __future__ import annotations

import json

from .mcp_app import mcp


def _txt(d) -> str:
    return json.dumps(d, indent=1, default=str)


@mcp.tool(structured_output=False)
def hardsurf_start(name: str, mesh: str, views: str | None = None, concept: str | None = None):
    """Start a hard-surface object: copy the fused mesh (closed PLY), the point cloud's renders (views.npz: colour
    is projected from them at bake) and the concept into its folder; refuses an open or inside-out mesh."""
    from . import hardsurf_run as R
    rep = R.start(name, mesh, views, concept)
    return f"folder {R.folder(name)}\n{_txt(rep)}\nnext: hardsurf_frame"


@mcp.tool(structured_output=False)
def hardsurf_frame(name: str, up: str = "y", contact_h: float = 0.06, contacts: int | None = None,
                   exclude_centre: float | None = None, yaw: str | float = "pca", yaw0: float | None = None,
                   scale: dict | None = None, flip: bool = False):
    """Square the fused mesh up on its ground footprint: contacts = the regions contact_h over its lowest point (keep
    the N biggest with `contacts`; `exclude_centre` drops ones within that |x| after the first turn); yaw "pca" |
    "pairs" (left/right contact pairs) | degrees; `yaw0` the first turn when the footprint is near square (warned);
    scale {"extent": "y", "value": 1.3} or {"pair_gap": 0.82}; flip if the front came out at +y."""
    from . import hardsurf_run as R, artretopo_study as St
    info = R.frame(name, up=up, contact_h=contact_h, contacts=contacts, exclude_centre=exclude_centre,
                   yaw=yaw if not (isinstance(yaw, str) and yaw.lstrip("-").replace(".", "").isdigit()) else float(yaw),
                   yaw0=yaw0, scale=scale, flip=flip)
    p, txt = St.views(str(R.folder(name)), "high", ("front", "side", "top"))
    from .tools_retopo import _img
    return [_img(p), f"{_txt(info)}\n{txt}\nnext: is the front at -y and the footprint square? then read the parts "
            "(hardsurf_look, hardsurf_vote) and fit them (hardsurf_fit)"]


@mcp.tool(structured_output=False)
def hardsurf_look(name: str, mesh: str = "high", views: list[str] | None = None, centre: list[float] | None = None,
                  scale: float | None = None, step: float = 0.05, style: str = "colour"):
    """Gridded orthographic views of the framed fused mesh (mesh high) or the built parts to read positions off (same
    viewer as retopo_look: views front|back|side|side_r|top|below|3q; centre + scale frame a part)."""
    from . import hardsurf_run as R, artretopo_study as St
    from .tools_retopo import _img
    p, txt = St.views(str(R.folder(name)), mesh, tuple(views or ("front", "side", "top")), centre, scale, step, style)
    return [_img(p), txt]


@mcp.tool(structured_output=False)
def hardsurf_vote(name: str, kind: str, axis: list[float] | str, origin: list[float] | None = None,
                  t: list[float] | None = None, rmax: float = 0.2, values: list[float] | None = None,
                  window: list[float] | None = None, step: float = 0.006, angles: int = 36):
    """The evidence as text you can read: kind "turned" (cells (t along axis, r from it) solid at most of `angles`
    directions round origin/axis, t=[t0,t1]) or "width" (a profile: sections at `values` along axis "x"|"y"|"z" over
    window [a0,a1,b0,b1] of the other two axes, voted). '#' > 0.7, '+' > 0.5, '.' > 0.2. Draw profiles off it."""
    from . import hardsurf_run as R, hardsurf_fit as F
    S = R.solid(name)
    if kind == "turned":
        ts, rs, V = S.votes(origin, axis, t[0], t[1], rmax, step, angles)
        return f"rows t (along the axis), cols r\n{F.vote_text(V, ts, rs)}"
    if kind == "width":
        A, B, V = F.profile_vote(S, axis, values, window, step)
        return f"rows = the first in-plane axis, cols = the second (xyz order)\n{F.vote_text(V, A, B)}"
    raise ValueError("kind is turned or width")


@mcp.tool(structured_output=False)
def hardsurf_fit(name: str, kind: str, part: dict):
    """Fit a part to the fused mesh and add it to parts.json (a part with the same name is replaced). kind:
    "turned" {name, origin, axis, t0, t1, rmax, [step, angles, keep, tol], + part keys}: a lathe part from the
      revolution vote (warns when the vote is weak: thin shell / not round -> draw the profile, kind "part");
    "sweep" {name, profile [[a,b],...], x0, x1, [axis "x", round_r, side (2nd profile), side_from, n]}: a slab;
    "outline_tube" {name, axis, value, window, r}: a tube round a plane's biggest outline pulled in by r (a frame);
    "trace" {start, direction}: measure a tube's centreline + radius (returns it; add it as kind "part");
    "ring" {centre, normal, [rmin, rmax]}: a ring's centre + radius (wheels, rims; returns it);
    "part" {any part dict, hardsurf_parts.TYPES}: add a part you wrote (boxes, plates, radial lugs / studs ...)."""
    from . import hardsurf_run as R, hardsurf_fit as F
    S = R.solid(name) if kind != "part" else None
    p = dict(part)
    if kind == "turned":
        keys = ("name", "origin", "axis", "t0", "t1", "rmax", "step", "angles", "keep", "tol")
        d = F.turned(S, **{k: p.pop(k) for k in keys if k in p}, **p)
    elif kind == "sweep":
        d = F.sweep(p.pop("name"), p.pop("profile"), p.pop("x0"), p.pop("x1"), **p)
    elif kind == "outline_tube":
        loop = F.outline_loop(S, p.pop("axis"), p.pop("value"), p.pop("window"), p["r"])
        d = dict(type="tube", name=p.pop("name"), paths=[loop], closed=True, smooth=True, step=0.03, **p)
    elif kind == "trace":
        pts, r = F.trace_tube(S, p["start"], p["direction"])
        return _txt({"centreline": pts.round(4).tolist(), "radius": round(r, 4)})
    elif kind == "ring":
        c, r, e = F.ring_fit(S, p["centre"], p["normal"], rmin=p.get("rmin", 0.0), rmax=p.get("rmax", 0.3))
        return _txt({"centre": c.round(4).tolist(), "radius": round(r, 4), "mean_error": round(e, 4)})
    elif kind == "part":
        d = p
    else:
        raise ValueError("kind: turned | sweep | outline_tube | trace | ring | part")
    rep = R.put_parts(name, [d])
    warn = d.get("warning", "")
    return f"{_txt(rep)}\n{warn}\nnext: more parts, then hardsurf_build"


@mcp.tool(structured_output=False)
def hardsurf_build(name: str, drop: list[str] | None = None):
    """Mesh every part (one object each, artist seams) and report each part's distance from the fused mesh (median /
    95th percentile, mm): far parts are invented on purpose (fine) or misplaced (look). `drop` removes parts first."""
    from . import hardsurf_run as R
    if drop: R.drop_parts(name, drop)
    rep = R.build(name)
    return f"{_txt(rep)}\nnext: hardsurf_check (nothing floats), look beside the sculpt, then hardsurf_bake"


@mcp.tool(structured_output=False)
def hardsurf_check(name: str, glb: str = "parts.glb", touch: float = 0.004):
    """Game-ready checks as numbers: FLOATING groups (parts touching nothing within `touch`; attach them: a post, a
    batten, a longer axle) and OVERLAPPING pairs (read them: an axle in its hub is meant)."""
    from . import hardsurf_run as R
    return _txt(R.check(name, glb, touch))


@mcp.tool(structured_output=False)
def hardsurf_bake(name: str, res: int = 2048, depth_tol: float = 0.012):
    """Bake every part into one atlas: colour PROJECTED from the point cloud's renders at the fused-mesh point each texel
    covers (vertex-colour fallback, push-pull fill, metals cleaned), normals from the fused mesh per part `nmap`."""
    from . import hardsurf_run as R
    return _txt(R.bake(name, res, depth_tol))


@mcp.tool(structured_output=False)
def hardsurf_rig(name: str, joints: list[dict], lod_ratio: float = 0.35):
    """Rigid-parts rig + numeric tests. joints: [{name, kind hinge|spinner|slider, parts, pivot, axis, parent,
    range [lo, hi] (deg / m), follows {joint, ratio} (linked: doors, gears, a steering link), static}]. Reports each
    joint's turns (angle / axis / sign) and its CLEAR range (largest values before the moved parts cross the rest)."""
    from . import hardsurf_run as R
    return _txt(R.rig(name, joints, lod_ratio))


@mcp.tool(structured_output=False)
def hardsurf_disagree(name: str, where: str, sculpt_says: str, concept_says: str, call: str):
    """Log a place where the fused mesh and the concept (or the game) disagree, and the call you made. The fused mesh
    is evidence, not the spec: splats invent parts, bulge bars, fill under floors."""
    from . import hardsurf_run as R
    return _txt(R.disagree(name, where, sculpt_says, concept_says, call))
