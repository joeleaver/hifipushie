# hifipushie

An MCP server that lets an LLM model characters, creatures, props and environments the way an artist does:
by describing them, looking at the result beside the reference, and correcting.

Instead of driving a mouse or writing raw mesh code, the model describes a creature or a prop as a
**skeleton with SDF blobs hung on it**: joints and bones (round cones) plus masses, smooth-blended into one
surface, then sculpted with strokes and painted. hifipushie meshes it and returns clay renders with world-unit
rulers, so the model can see what it made and correct it; with reference art it scores the silhouette and
reports edge errors in world units. Realistic humans, hair, clothes, skin, terrain, plants and clutter have
their own tools, and a finished model exports as a game-ready GLB.

## Tools

147 tools in 17 domains. A small core is native MCP tools; every other tool runs through
`call_tool(name, args)`. An agent does not need this table: `guide` is the playbook (read first),
`find_tool("<the job in plain words>")` names the tool for a job with an example call, and
`guide(topic="<tool>")` gives any tool's full parameters. `guide(topic="example")` returns two whole models to
start from.

| domain | what it is for | tools |
|---|---|---|
| core | Native tools: models, specs, look, check, measure, history, the guide, find / call any tool | `guide`, `find_tool`, `call_tool`, `list_models`, `get_model`, `kit_reference`, `put_model`, `edit_model`, `look`, `check`, `measure`, `history`, `revert`, `review_view` |
| plan | Plans, reference images, compare, silhouette fit, clearance, style check | `set_plan`, `set_reference`, `compare`, `fit`, `clearance`, `style_check` |
| concept | Match a concept image: fit its camera, render from it pixel-aligned, same-box feature tiles for review_view, how parts join the body (stalk or base) | `fit_concept_camera`, `look_matched`, `feature_tiles`, `join_report`, `fit_matched` |
| reshape | Reshape what is already there, as a modeller's hands do: work two masses into one flowing mass, take hold of clay in a flat view and move it, cut clay away along a line or take one shape out of another, bend a mass along a path, make a flap that folds over | `fuse`, `grab`, `trim`, `carve`, `flap`, `bend` |
| features | Sculpt from reference pictures: read a picture's views, patches and form lines, name its features as marks on it (the feature map), build the masses from their marks, measure a model feature by feature | `read_reference`, `look_beside`, `mark_features`, `build_masses`, `build_forms`, `feature_report`, `review_part`, `study_part` |
| scene | The Blender scene (sync, pull) and the heavy-job queue | `sync`, `pull`, `heavy_status`, `heavy_queue` |
| export | OBJ export, game-ready assets (GLB/FBX, PBR maps), the export rig, judging a GLB | `export`, `export_asset`, `rig`, `judge_asset` |
| human | Realistic humans: the base body, the artist block-in of a head from pictures (the default), measurements, fits, skin | `human`, `measure_human`, `fit_human`, `nudge_human`, `human_reference`, `block_in_start`, `block_in_look`, `block_in_step`, `block_in_solve`, `block_in_expression`, `set_expression`, `lid_read`, `eye_ruler`, `face_ruler`, `lip_read`, `gnm_controls` |
| skin | A human's skin: description, measured from the reference pictures, close looks beside them | `skin`, `skin_from_reference`, `brow_read`, `look_skin`, `skin_reference`, `skin_project` |
| likeness | Matching a real person's face and look from reference pictures | `likeness`, `fit_likeness`, `likeness_points`, `character_read`, `project_reference`, `texture_from_reference`, `reference_brief`, `check_references` |
| hair | Hair: strand grooms, tied styles, stylised locks, look, reference, export | `groom_hair`, `tie_hair`, `look_hair`, `hair_reference`, `hair_from_reference`, `export_hair` |
| cloth | Garments: design, the toile (with a collar the lapels and collar one turned flap), its marks and the cut flat pattern (drape first), the pattern and its gate, alterations, the chain build, references | `garment_plan`, `body_tape`, `garment_toile`, `garment_mark`, `garment_cut`, `draft_pattern`, `pattern_parts`, `pattern_check`, `chain_garment`, `garment_details`, `look_chain`, `garment_appearance`, `export_garment`, `garment_record` |
| terrain | Terrain and game levels (height fields in a level designer's words) | `set_terrain`, `check_terrain`, `look_terrain`, `export_terrain`, `terrain_history` |
| plants | Trees and plants (grown, measured, exported), stands of them, wind | `grow_plant`, `edit_plant`, `get_plant`, `look_plant`, `look_plants`, `plant_form`, `plant_reference`, `export_plant`, `wind_plant`, `sync_plant`, `plant_history`, `grow_stand`, `look_stand`, `export_stand` |
| hardsurf | Hard surface from a fused concept sculpt (oxidegen make_point_cloud): clean parts fitted to it (turned, swept, tubes, boxes, radial arrays), colour baked from the point cloud's renders, rigid joints with numeric tests | `hardsurf_start`, `hardsurf_frame`, `hardsurf_look`, `hardsurf_vote`, `hardsurf_fit`, `hardsurf_build`, `hardsurf_check`, `hardsurf_bake`, `hardsurf_rig`, `hardsurf_disagree` |
| retopo | Artist-style retopology of a fused concept sculpt (oxidegen make_point_cloud): your own cage of loops, pressed, baked, rigged and range-of-motion checked | `retopo_start`, `retopo_look`, `retopo_slices`, `retopo_measure`, `retopo_check`, `retopo_fit`, `retopo_fit_cylinder`, `retopo_primitives`, `retopo_cage`, `retopo_press`, `retopo_bake`, `retopo_fill`, `retopo_assemble`, `retopo_compare`, `retopo_armature`, `retopo_rom`, `retopo_lod`, `retopo_report` |
| clutter | Ground clutter kits (rocks, logs, leaves ...) for terrain | `make_clutter`, `look_clutter`, `clutter_kit` |

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

Approve the `hifipushie` server when asked (or check it with `/mcp`). The repo also ships a Claude Code skill
(`.claude/skills/hifipushie`) that points Claude at the playbook (`guide` tool) whenever you ask for a model. Then ask for a creature, e.g.
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

## Run as an oxidegen artist

hifipushie can be the `sculpt` artist of an [oxidegen](https://oxidegen.jkbase.app) Art Department. Usually the
department runs it for you on a rented GPU box (the hosted image below) and you need nothing installed. To run
it on your own Linux machine instead, ask oxidegen to connect this computer; it gives you one command:

```sh
curl -fsSL <department>/install/runner.sh | sh -s -- --url <department> --code <one-time code>
```

`--check` first prints whether the machine fits (disk, RAM, GPU, missing libraries with the install command)
without changing anything. The runner dials out to the department and pulls work; nothing listens on your
machine. Each department session works on one model or terrain in its own workspace (deleted when the session
closes), in a worker process the department can cancel (Blender included). Tools take no `name` and no host
paths: reference images arrive as library versions, exports go back as files. The live-Blender socket is off in
runner mode (`HIFIPUSHIE_NO_LIVE=1`). Standalone use (`hifipushie-mcp`) is unchanged.

### Start at login

The installer runs `hifipushie-artist setup`, which keeps this project's runner in `.oxidegen/runner/` (config,
the token (mode 600), logs, workspaces; added to `.git/info/exclude`) and shared bits in `~/.cache/oxidegen/`
(Blender 5.1 unless you have it, the asset packs, the Python env), then installs and starts the systemd user
service `oxidegen-runner-sculpt.service` (one per user; setting up from another project reuses it,
`--move-here` repoints it). Without systemd it starts a background process instead. Other commands:
`hifipushie-artist status | logout | install | uninstall`, or `login` (browser pairing, no code). If the
department forgets this computer, the runner stops and says to run setup again. The runner follows the version
the department pins (it updates itself between sessions and rolls back a version that doesn't work). Remove it
all with `install-runner.sh --uninstall [--purge]`. From a checkout, for development:
`OXIDEGEN_RUNNER_TOKEN=<token> uv run hifipushie-artist` (`--url`, `--name`, `--work-root`, `--assets`,
`--capabilities`).

### Hosted runner image

`Dockerfile.sculpt` is the image a department rents a GPU box for (one session per box, destroyed after):
Ubuntu 24.04, the official Blender 5.1.2 (sha256-checked), hifipushie from `uv.lock`, and the GNM (Apache-2.0) and
MakeHuman (CC0) packs at `/opt/hifipushie-assets`. Build and push with `docker/build-sculpt.sh [--push]` (it stages
the packs from `$HIFIPUSHIE_ASSETS` or `./workspace/_templates`, fetching what's missing by checksum; tag = the git
short sha). Its CMD is `hifipushie-artist` in hosted mode, configured only by env: `OXIDEGEN_URL`,
`OXIDEGEN_RUNNER_TOKEN`, `OXIDEGEN_RUNNER_NAME`, plus `NVIDIA_DRIVER_CAPABILITIES=all` so the NVIDIA runtime adds
the driver's EGL (EEVEE renders headless through it). It runs as a non-root user with sessions under `/work`, logs to
stdout, opens no ports, and exits 77 if the department refuses its token (other failures: retried with backoff).
At start it renders a 64 px cube in Workbench and EEVEE and reports the result in its registration `equipment`
(`eevee`, `workbench`, `gpu_renderer`); without a usable GPU (Mesa llvmpipe) painted looks (`look`, `style_check`)
are marked `needs.gpu` and the instructions say to use clay looks. With `OXIDEGEN_WANTED_VERSION=<git sha>` a box runs
that hifipushie commit instead of the baked one (installed at start over a copy of the image's env; on failure it runs the
baked one and reports `update_failed`).

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
