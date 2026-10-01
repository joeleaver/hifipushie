# hifipushie

An MCP server that lets an LLM sculpt characters and creatures.

Instead of driving a mouse or writing raw mesh code, the model describes a creature as a
**skeleton with SDF blobs hung on it**: joints and bones (round cones) plus ellipsoid masses,
smooth-blended into one surface. hifipushie meshes it and returns clay renders with world-unit
rulers, so the model can see what it made and correct it. When there is reference art, it scores
silhouette overlap and reports edge errors in world units.

## Tools

| tool | what it does |
|---|---|
| `guide` | the playbook: working in stages, stroke and parts rules, judging renders, diagnosing artifacts (read it first) |
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
| `export` | OBJ for Blender or printing, one object per part |

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
