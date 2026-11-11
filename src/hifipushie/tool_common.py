"""Helpers more than one tool module uses: tool output (PNG images, saved files), references, shared texts."""
from __future__ import annotations

import io
import json
from pathlib import Path

from mcp.server.mcpserver import Image
from PIL import Image as PILImage

from . import store

def _png(im: PILImage.Image) -> Image:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return Image(data=buf.getvalue(), format="png")


def _sil_parts(spec: dict, only_parts: list[str] | None, hide_parts: list[str] | None) -> frozenset | None:
    """The parts a silhouette counts (check/compare/fit): only_parts, all but hide_parts, else the plan's
    "parts", else every part (None)."""
    if not only_parts and not hide_parts:
        only_parts = (spec.get("plan") or {}).get("parts")
        if not only_parts:
            return None
    from .spec import compile_prims
    have = {p.part for p in compile_prims(spec)}
    for pn in [*(only_parts or []), *(hide_parts or [])]:
        if pn not in have:
            raise ValueError(f"no part {pn!r} (parts: {', '.join(sorted(have))})")
    keep = set(only_parts) if only_parts else set(have)
    keep -= set(hide_parts or [])
    if not keep:
        raise ValueError("no parts left to count in the silhouette")
    return None if keep == have else frozenset(keep)


def _silhouettes(name: str, spec: dict, resolution: int, parts: frozenset | None) -> dict:
    """{view: silhouette} of the whole model (the build's), or of just those parts (evaluated here)."""
    if parts is None:
        store.build(name, resolution)
        return {v: store.silhouette(name, v) for v in ("front", "side", "top")}
    from . import sdf
    from .spec import compile_prims
    return sdf.silhouettes(sdf.evaluate([p for p in compile_prims(spec) if p.part in parts], resolution))


def _parts_note(parts: frozenset | None) -> str:
    return f"silhouettes count parts: {', '.join(sorted(parts))}\n" if parts else ""


def _out(im: PILImage.Image, save: str | None) -> Image:
    """The image for the tool result, also written to `save` (a path) when given."""
    if save:
        path = Path(save).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        im.save(path)
    return _png(im)


def _spec_arg(spec) -> dict:
    return json.loads(spec) if isinstance(spec, str) else spec


REPO = Path(__file__).resolve().parents[2]  # (bin/review, docs/notes: present in a source checkout)
