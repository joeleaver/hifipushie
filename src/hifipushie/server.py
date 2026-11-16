"""hifipushie MCP server: skeleton-and-blob creature modeling with clay-render feedback.

This module gathers the tools and starts the server. The app, the tool decorator and the registry are in
mcp_app.py; each domain's tools are in tools_<domain>.py; shared helpers in tool_common.py.
`from hifipushie import server; server.<tool>(...)` calls any tool as a plain function."""
from __future__ import annotations

from . import moved
from .mcp_app import CORE, INSTRUCTIONS, TOOL_GROUPS, _register_core, enable_all, mcp  # noqa: F401
from .tools_cloth import (  # noqa: F401
    body_tape, chain_garment, draft_pattern, export_garment, garment_appearance, garment_details, garment_plan,
    garment_cut, garment_mark, garment_record, garment_toile, look_chain, pattern_check, pattern_parts,
)
from .tools_clutter import (  # noqa: F401
    clutter_kit, look_clutter, make_clutter,
)
from .tools_export import (  # noqa: F401
    export, export_asset, heavy_queue, heavy_status, judge_asset, pull, rig, sync,
)
from .tools_features import (  # noqa: F401
    build_forms, build_masses, feature_report, look_beside, mark_features, read_reference,
)
from .tools_find import (  # noqa: F401
    call_tool, find_tool, guide,
)
from .tools_hair import (  # noqa: F401
    export_hair, groom_hair, hair_from_reference, hair_reference, look_hair, tie_hair,
)
from .tools_human import (  # noqa: F401
    block_in_expression, block_in_look, block_in_solve, block_in_start, block_in_step, eye_ruler, face_ruler,
    fit_human, gnm_controls, human, human_reference, lid_read, lip_read, measure_human, nudge_human, set_expression,
)
from .tools_likeness import (  # noqa: F401
    character_read, check_references, fit_likeness, likeness, likeness_points, project_reference, reference_brief,
    texture_from_reference,
)
from .tools_model import (  # noqa: F401
    check, edit_model, get_model, history, kit_reference, list_models, look, measure, put_model, revert, review_view,
)
from .tools_plan import (  # noqa: F401
    clearance, compare, feature_tiles, fit, fit_concept_camera, fit_matched, join_report, look_matched, set_plan,
    set_reference, style_check,
)
from .tools_reshape import carve, flap, fuse, grab, trim  # noqa: F401
from .tools_plants import (  # noqa: F401
    edit_plant, export_plant, export_stand, get_plant, grow_plant, grow_stand, look_plant, look_plants, look_stand,
    plant_form, plant_history, plant_reference, sync_plant, wind_plant,
)
from .tools_skin import (  # noqa: F401
    brow_read, look_skin, skin, skin_from_reference, skin_project, skin_reference,
)
from .tools_terrain import (  # noqa: F401
    check_terrain, export_terrain, look_terrain, set_terrain, terrain_history,
)

# A helper that moved out of server.py says where it is now (C427): the tools above are still server.<tool>.
__getattr__ = moved.refuse(__name__, ("mcp_app", "tool_common", "tools_find", "tools_model", "tools_plan", "tools_export",
                                      "tools_features", "tools_reshape", "tools_human", "tools_likeness", "tools_skin", "tools_hair", "tools_cloth",
                                      "tools_terrain", "tools_plants", "tools_clutter"))

_register_core()


def main():
    mcp.run()


if __name__ == "__main__":
    main()
