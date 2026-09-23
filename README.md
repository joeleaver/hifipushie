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
| `look` | build + clay contact sheet (front, side, top, 3/4 …); `focus` + `zoom` for close-ups, rebuilt at full resolution; `shading` raking / curvature to judge form; `strokes=True` draws stroke paths |
| `kit_reference` | parameters of the `hand` and `face` kits (fingers; eyes with lids, brows, nose, lips, cheeks) |
| `strokes` (in the spec) | sculpt on the surface: clay / crease / flatten along paths addressed from the skeleton, with profiles for edge hardness and `repeat` for sets (wrinkles); they displace the skin, so they follow curvature and move with the bones |
| `measure` | cross-section sizes as numbers: axis-to-surface distances along a bone chain, or every part in slices across X/Y/Z |
| `set_plan` / `check` | draw a 2D blockout plan first (front/side outlines from ellipses, capsules and polygons; landmark heights; planned sections), then check the model against it at every stage: silhouette diff in exact world units, landmark joints, section widths/depths |
| `set_reference` / `compare` | reference silhouettes → IoU, red/blue diff image, band tables of edge errors |
| `fit` | auto-adjust joints, radii and blobs so the silhouettes match the references or the plan (saved as a new version) |
| `history` / `revert` | every change is checkpointed |
| `export` | OBJ for Blender or printing |

## Install

You need:
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (it fetches Python 3.12+ and the dependencies itself)
- [Blender](https://www.blender.org/download/) 4.1 or newer, used headless for the clay renders (tested on 5.1).
  hifipushie runs `blender` from your `PATH`; if it isn't there (the macOS app usually isn't), set
  `HIFIPUSHIE_BLENDER` to the executable, e.g. `/Applications/Blender.app/Contents/MacOS/Blender`.

```bash
git clone https://github.com/joeleaver/hifipushie.git
cd hifipushie
uv sync
```

Check that rendering works (builds the example goblin and writes a contact sheet):

```bash
uv run hifipushie-import examples/goblin.json
uv run python -c "from hifipushie import server; open('goblin.png', 'wb').write(server.look('goblin')[0].data)"
```

### Claude Code

The repo's `.mcp.json` registers the server for sessions started in this directory:

```bash
claude
```

Approve the `hifipushie` server when asked (or check it with `/mcp`). Then ask for a creature, e.g.
"make a small dragon with hifipushie", or "load examples/goblin_sculpt.json and show me the face".

### Other MCP clients (Claude Desktop, etc.)

Point the client at the checkout with an absolute path, and give models a fixed home:

```json
{
  "mcpServers": {
    "hifipushie": {
      "command": "uv",
      "args": ["--directory", "/path/to/hifipushie", "run", "hifipushie-mcp"],
      "env": {"HIFIPUSHIE_HOME": "/path/to/hifipushie/workspace"}
    }
  }
}
```

## Models and examples

Models live in `workspace/<name>/` under the directory the server runs in (override with `HIFIPUSHIE_HOME`):
`spec.json` plus every earlier version in `history/`. `workspace/` is git-ignored.

- `examples/fox.json`: a complete quadruped
- `examples/goblin.json`: a biped using the hand and face kits
- `examples/goblin_sculpt.json`: the goblin with strokes (arm muscles, forehead wrinkles)
- `examples/troll.json`: a troll made with the plan workflow, all four stages (plan, fitted blockout, strokes for secondary forms, scattered warts and wrinkles)

Load one with `uv run hifipushie-import examples/fox.json` (the model is named after the file, or pass a
name as a second argument), or just ask Claude to load it.

## License

MIT
