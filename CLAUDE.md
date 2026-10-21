# hifipushie

MCP server for LLM-driven character / creature / prop modelling. Design principle: give the model representations it
reasons well in (skeletons, named parts, numbers) and feedback it can act on (multi-view renders, rulers, numeric
silhouette errors), not mouse control. North star: tools that let an LLM work like a real artist.

## Start here
- Working on a thread? Read ONLY its STATE page: `docs/state/<thread>.md` (rules in docs/state/README.md). History lives in
  `docs/notes/<thread>.md`: append-only, read by grep, never end to end.
- Any stage: read `docs/notes/gates.md` first.
- New character: follow `docs/notes/character_recipe.md` (stage order, defaults, gates) and check `docs/notes/traps.md`
  before trusting a measure. Lesson ledger: `docs/notes/codified.md` (add a row for every new lesson).

## Hard rules
- Gates every stage: DESCRIBE the reference as measurable items -> MEASURE each round -> LOOK (independent blind reviewer on
  reference | result crops, no captions) -> APPROVE (Joe or coordinator only: workspace/approved.json via
  /mnt/data/hifipushie/bin/approve). Stages consume only approved pieces. Clean != right; "runs end to end" is plumbing.
- Git: stage by path, NEVER `git add -A` (public repo: github.com/joeleaver/hifipushie). Agents never push; the coordinator
  lands work on main. `workspace/` is git-ignored; shareable models go in `examples/`.
- Family / private heads: nothing of them in the repo, ever. Critique the model, never the person.
- Memory: heavy jobs take `resources.heavy` (declare the real GB) and run under /mnt/data/hifipushie/bin/capped (renders also
  take the GPU lock); light sweeps use bin/slot. Kill only PIDs you started.
- Durable / big files on /mnt/data/hifipushie, never /tmp. Third-party assets via `assets.py` ($HIFIPUSHIE_ASSETS).
- Document as you go: rewrite your STATE page + append notes + commit after every step (STATE / NEXT line). Hand over and
  restart fresh past ~250k tokens.
- Judge renders yourself before forwarding (agents over-rate); reference beside every result; send renders to Joe as files.
- Bump `store.BUILD_VERSION` whenever meshing output changes. Incremental builds must equal cold builds.
- Keep this file < 8 KB: no thread history here.

## Conventions
Metres, Blender axes: Z up, creature faces -Y, its left is +X; ".L" mirrors to ".R". Side view faces left.
Test subjects: examples/troll.json (reference), workspace/goblin, fox.

## Layout (src/hifipushie/; each module's docstring is the spec)
- `spec.py` spec format, mirroring, compile to primitives (read its docstring first). `sdf.py` SDFs, narrow-band grid,
  marching cubes, `project`; clipping relies on `Prim.reach` / `inert` (break it -> flat seams in fillets).
- `kits.py` hand / face / foot kits; `anatomy.py` lore by joint type (docs/notes/anatomy.md); `strokes.py` surface sculpting
  (summed dabs); `assemble.py` prefabs / instances / arrays (docs/notes/assemble.md); `stylesheet.py` + `deform.py` style.
- Parts / shells / `hides.py`; `surface.py` (`Points`); `paint.py` + `paintnodes.py` + `materials.py` (docs/notes/paint.md);
  `images.py` (docs/notes/images.md); `realism.py` story / weather; `plan.py` 2D blockout.
- `judge.py` + bin/judge: THE way to judge a GLB (standard shots, feature crops, self-checked measures, blind A/B with
  controls; docs/notes/judge.md).
- `measure.py`, `compare.py`, `fit.py` (LM silhouette fit); `render.py` + `blender_render.py` (docs/notes/render.md).
- `tailor.py` the tape; `measure_defs.py` each draft's measurement definitions + adapters (docs/notes/measurements.md: the table).
- `store.py` spec + history + build cache; `scene.py` + `blender_scene.py` live Blender scene (docs/notes/blender_scene.md).
- Humans: `base.py` (docs/notes/base.md), `blockin.py` default for heads from pictures, GNM-native heads, `gnm_controls.py`
  (docs/notes/gnm_atlas.md), `faceshapes.py` (docs/notes/faceshapes.md), headbody (docs/notes/headbody.md).
- Skin: `skin_read.py`, `skin_folds.py`, `skin_project.py` (docs/notes/skin.md). Hair: `hair.py`, `hair_flow.py`,
  `hair_cards.py`, `hair_cap.py` (docs/notes/hair.md). Cloth: `cloth.py`, `pattern.py`, `tailor.py`, `freesewing.py`
  (docs/notes/cloth.md).
- Export: `asset.py` + `blender_asset.py` (docs/notes/asset.md, game_ready.md), `rig.py` (docs/notes/rig.md),
  `retopo.py` (docs/notes/retopo.md), `budgets.py` + budgets.json (docs/notes/budgets.md).
- `resources.py` (docs/notes/resources.md); `server.py` MCP tools (mcp 2.x MCPServer; every tool wrapped by
  `_tool_with_errors`). Audits: bin/audit, bin/audit-summary (docs/notes/audit.md).
- Performance invariants (field_at chunking, PartGrid reuse, caches keyed by content): docs/notes/performance.md.

## Testing without restarting the MCP
`uv run python -c "from hifipushie import server; ..."`; `look` returns `[Image, str]` (`Image.data` = PNG bytes).
The running MCP server has the code from when it started. Tooling repros: `uv run python tests/test_tooling.py`.
OpenBLAS is capped at 4 threads in `__init__.py`.

## Threads (state page -> history)
- Tess export: docs/state/tess_export.md -> game_ready.md "## r<N>"
- Garrett export: docs/state/garrett_export.md -> game_ready.md "## Garrett, session <N>"
- Tess hair cards: docs/state/tess_hair.md -> hair.md "hair-cards round <N>"
- Garrett hair (shells): docs/state/garrett_hair.md -> hair.md "Garrett short-hair shells sh<N>"
- Skin: docs/state/skin.md -> skin.md "## r<N>"
- Dress Garrett (jacket + shirt fit): docs/state/dress_garrett_fit.md -> cloth.md "fit round <N>"
- Dress Garrett shirt (alone, then under the jacket): docs/state/dress_garrett_shirt.md -> cloth.md "shirt round <N>"
- Dress Tess: docs/state/dress_tess.md -> cloth.md "dress-tess session <N>"
- Tailoring (jacket rules): docs/state/tailoring.md -> cloth.md "tailoring <date>"
- MCP rules (tools carry the gates): docs/state/mcp_rules.md -> mcp_audit.md "## History"
- Pattern gate (sims refused without a PASS record): docs/state/pattern_gate.md -> pattern_gate.md
- No state page yet (history only): topology, blender_scene, terrain, streambeds, vegetation, clutter, onemesh, likeness,
  refstudy, garrett_head, measuremodels, rig, base, retopo, images, faceshapes, headbody, resources, budgets, audit.
