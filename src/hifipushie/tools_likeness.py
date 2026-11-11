"""Likeness tools: reading a person's references, fitting and projecting them, and the reference brief."""
from __future__ import annotations

from pathlib import Path

from PIL import Image as PILImage

from . import skin_route, store
from .mcp_app import mcp
from .tool_common import _png

@mcp.tool(structured_output=False)
def likeness(name: str, targets: bool = False, top: int = 8):
    """The likeness checklist (~50 facial features) on a one-mesh human vs its fitted reference pictures: ranked
    misses, coverage, focus panels. targets=True measures the references alone and stores the target sheet and stage
    plan. top = how many panels. Measures only. Details: guide(topic="likeness")."""
    from . import likeness_compare, likeness_panels, likeness_stages
    if targets:
        from . import head_route
        sh = likeness_compare.measure_reference(name)
        return likeness_compare.sheet_text(sh) + ("" if head_route.is_block_in(name) else
                                    "\n\nstage plan (fit_likeness, big to small):\n" + likeness_stages.stage_plan(name))
    txt, out, _ = likeness_panels.report(name, top=top)
    return [_png(PILImage.open(out)), txt + f"\nfocus sheet: {out}"]


@mcp.tool(structured_output=False)
def fit_likeness(name: str, stage: str, force: bool = False, save: bool = True):
    """ONE stage of the likeness fit (proportions, widths, eyes, brows, nose, mouth, chin_jaw, ears, profile): misses
    solved minimal-change, earlier stages pinned, integrity-guarded. Run likeness(targets=True) first; approve each
    stage's panels. force, save. Details: guide(topic="fit_likeness")."""
    from . import head_route
    from . import likeness_fit, likeness_notes, likeness_panels
    head_route.refuse_off_route(name, "fit_likeness")
    pn = str(store.HOME / "human_renders" / f"lk_{name}_stage_{stage}.png")
    if stage == "profile":   # the nose and chin on a turned view's contours alone (likeness_points 'profile' / 'nose')
        base, cmp, log = likeness_fit.fit_profile(name, force=force, save=save)
        rows = [r for r in cmp["rows"] if r.get("kind") == "contour" and r["score"] >= 0]
        likeness_panels.focus_sheet(cmp, pn, rows=rows, cols=3)
        return [_png(PILImage.open(pn)), "\n".join(log) + "\n" + likeness_notes.table_text({**cmp, "rows": rows}) + f"\npanels: {pn}"]
    rep = likeness_fit.fit_stage(name, stage, force=force, save=save, panels=pn)
    out = [rep["text"] + f"\npanels: {pn}"]
    if Path(pn).exists():
        out.insert(0, _png(PILImage.open(pn)))
    return out


@mcp.tool(structured_output=False)
def project_reference(name: str, view: int = 0, save: str = ""):
    """Project fitted reference picture `view` onto the head through its camera and show it from other angles: where it
    smears or slides, the geometry is wrong there. save writes the sheet. Details: guide(topic="project_reference")."""
    from . import likeness_read as lr
    pn = save or str(store.HOME / "human_renders" / f"lk_{name}_projected.png")
    r = lr.project_reference(name, pn, view=view)
    return [_png(PILImage.open(pn)), f"reference {view} projected on {name}; share of each view's head that carries the picture: {r['seen']}\n{pn}"]


@mcp.tool(structured_output=False)
def texture_from_reference(name: str, views: list[int] | None = None, opacity: float = 0.9, delight: bool = True,
                           match: str = "tone", remove: bool = False) -> str:
    """Lay the fitted reference pictures over the head's skin as de-lit paint decals ("ref_texture_<view>"), to JUDGE
    a head: photo pixels never ship (skin_project is the measured atlas). views,
    opacity, delight, match "tone"|"level"|"", remove=True takes them out. Redo after head shape changes. Details:
    guide(topic="texture_from_reference")."""
    from . import likeness_texture as lt
    if not remove:
        skin_route.refuse_decals(store.load(name))
    r = lt.apply(name, views=views, opacity=opacity, delight=delight, match=match or None, remove=remove)
    st = lt.stale(store.load(name))
    warn = "" if remove else "\nWARNING: photo pixels never ship: remove these decals (remove=True) before export."
    return r["text"] + warn + (f"\nSTALE (made on another head shape, make again): {st}" if st else "")


@mcp.tool(structured_output=False)
def character_read(name: str, tag: str = "", read: dict | None = None, view: str = "", render: bool = False,
                   author: str = "llm"):
    """Stage 0 of likeness: the character read. No read: the form to fill. tag="reference" + read stores the
    reference's read (author="user" for the user's words); render=True gives a sheet for blind reads; tag + read +
    view stores one; tag alone diffs reference vs model. Details: guide(topic="character_read")."""
    from . import likeness_read as lr
    if render:
        pn = str(store.HOME / "human_renders" / f"lk_{name}_read_views.png")
        r = lr.render_views(name, pn)
        return [_png(PILImage.open(pn)), f"views {r['views']}: {pn}\n\n" + lr.form()]
    if read is not None:
        lr.set_read(name, tag or "reference", read, view=view or None, author=author)
        qs = lr.questions(name) if (tag or "reference") == "reference" else []
        return f"stored read '{tag or 'reference'}'" + (f" view {view}" if view else f" by {author}") + \
            ("\nQUESTIONS for the user (their read and the reader's differ; theirs is used):\n" + "\n".join(qs) if qs else "")
    if tag and tag != "reference":
        return lr.diff(name, tag)
    return lr.form()


@mcp.tool(structured_output=False)
def likeness_points(name: str, image: str, points: dict | None = None, lines: dict | None = None, by: str = "",
                    replace: bool = False) -> str:
    """Hand-placed points and lines on a reference picture (full-image px) for what the detector misses: points
    (gonion.R, ear_lobe.R, menton, ...) and lines (jaw.R, neck.R, profile, nose). Merged unless replace; by = who
    placed them. Details: guide(topic="likeness_points")."""
    from . import likeness_shape as ls
    d = ls.set_points(name, image, points, lines, by=by, replace=replace)
    v = next(x for x in d["views"] if x["image"] == image)
    return f"stored for {Path(image).name}: points {sorted(v['points'])}, lines " + \
        ", ".join(f"{k} ({len(q)} points)" for k, q in v["lines"].items())


@mcp.tool(structured_output=False)
def reference_brief(kind: str = "head", subject: str = "") -> str:
    """The shot list and generator prompts for likeness references (kind "head" | "figure", subject). Details:
    guide(topic="reference_brief")."""
    from . import likeness_brief as lb
    return lb.reference_brief(kind, subject)["text"]


@mcp.tool(structured_output=False)
def check_references(images: list[str], name: str | None = None) -> str:
    """What a set of reference pictures can support for the likeness checklist (views, lens, expression, light,
    ears/hairline, identity consistency) and which shots to ask for. name: the model's fitted cameras. Details:
    guide(topic="check_references")."""
    from . import likeness_brief as lb
    return lb.check_references(images, name)["text"]
