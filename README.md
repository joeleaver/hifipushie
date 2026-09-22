# hifipushie

An MCP server that lets an LLM ("hifi") sculpt ("push") characters and creatures.

Instead of driving a mouse or writing raw mesh code, the model describes a creature as a
**skeleton with SDF blobs hung on it**: joints and bones (round cones) plus ellipsoid masses,
smooth-blended into one surface. hifipushie meshes it and returns clay renders with world-unit
rulers, so the model can see what it made and correct it. When there is reference art, it scores
silhouette overlap and reports edge errors in world units.

## Tools

| tool | what it does |
|---|---|
| `put_model` / `get_model` / `list_models` | create or replace a spec, read it back with measurements |
| `edit_model` | batch edits: set / delete / rename / move joints / scale radii |
| `look` | build + clay contact sheet (front, side, top, 3/4 …); `focus` + `zoom` for close-ups, rebuilt at full resolution |
| `kit_reference` | parameters of the `hand` and `face` kits (fingers; eyes with lids, brows, nose, lips, cheeks) |
| `strokes` (in the spec) | sculpt on the surface: clay / crease / flatten along paths addressed from the skeleton, with profiles for edge hardness and `repeat` for sets (wrinkles); they displace the skin, so they follow curvature and move with the bones |
| `measure` | cross-section sizes as numbers: axis-to-surface distances along a bone chain, or every part in slices across X/Y/Z |
| `set_reference` / `compare` | reference silhouettes → IoU, red/blue diff image, band tables of edge errors |
| `fit` | auto-adjust joints, radii and blobs so the silhouettes match the references (saved as a new version) |
| `history` / `revert` | every change is checkpointed |
| `export` | OBJ for Blender or printing |

## Setup

Needs `uv` and Blender (headless, for rendering; override the binary with `HIFIPUSHIE_BLENDER`).
The repo's `.mcp.json` registers the server for Claude Code sessions opened here.
Models live in `workspace/<name>/` (override with `HIFIPUSHIE_HOME`).

See `examples/fox.json` for a complete creature, and `examples/goblin.json` for one using the hand and face kits, and `examples/goblin_sculpt.json` for the goblin with strokes (arm muscles, forehead wrinkles).
