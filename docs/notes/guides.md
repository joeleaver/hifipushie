# Product guides rewrite ("guides" agent, 2026-10-14)

STATE: cloth, vegetation, hair (+locks), skin, blockin, guide.md done and tested; EEVEE judging rule applied; guide(topic="tool:<name>").
NEXT: human / likeness / gnm_driving, tools_guide, terrain (clutter_guide: studio lines).

Why: the product guides (src/hifipushie/*_guide.md, served by the `guide` tool) had grown into lab notebooks (~800 KB;
cloth 918 lines, vegetation 1,142). Key rules were buried: game-ready Tess's sweater was a sweatshirt block with
torso-deep armholes and no knit (the agent started from the nearest template); the village oak was a realistic
broom-branched tree for a stylised storybook concept (the guide never made the agent describe the concept first).

The shape of every rewritten guide:
- a core topic of ~150-250 lines: the stages, a DESCRIBE-THE-REFERENCE-FIRST checklist (measurable items, before any
  template or default), the craft rules once each, the self-review loop (render beside the reference at the same
  framing, region by region, MAJOR / MINOR, construction and form before material before colour, fix the worst MAJOR,
  repeat; a clean result that isn't the reference is wrong), common mistakes, known gaps;
- details in sub-topics (new files registered in server.GUIDE_TOPICS); tool sections stay where `_tool_section`
  finds them (any file in GUIDE_TOPICS);
- history (dates, run numbers, our model names, how we learned it) appended to docs/notes/<thread>.md; studio-only
  content (oxidegen, NICO-TOP, rented GPUs, costs, bin/*, our agents, scratch paths) out of the product.
- proof: a fresh agent given only the guide tool plans a small real task; a rule it skips wasn't prominent enough.

## cloth
- cloth_guide.md 918 -> 167 lines. New topics: cloth_design (sheet keys, tailoring numbers, knits, jeans, shirts'
  wear, layers), cloth_construction (stage 2-4 detail: folds, interfacing, closures, built on the form, open-jacket
  tells, the start), cloth_sim (methods, quality, solvers and where they run, report, targets, judging, clean-up,
  made pieces after the drape, detail maps, closures and bands, states, hand pass, export), cloth_faults (the fault
  table, grouped: wrong garment / pattern and construction / start / simulation / looks), cloth_blocks (block + ops).
- cloth_background lost "Where each lesson lives", "Still open" and "Closed faults" (history) -> notes/cloth.md.
- cloth_reference_guide: "from Garrett's suit, 2026-10" and Garrett's concept counts made generic.
- cloth_tools `dress`: backends now list file / remote; "this machine's GPU" -> local GPU or your own command.
- Found: no tool prints the draft's armhole depth against the body's armpit; the guide tells the agent to read it
  off the pattern sheet / draft meta. A `look_pattern` line "armhole bottom N mm below the armpit" would make the
  knit-sweater fault impossible to miss (tooling suggestion, not built).
- Found: the old guide's "Sims cost money ... $0.66" and the oxidegen / NICO-TOP section were studio-only.

## guide(topic="tool:<name>") (the one code change)
Topics skin / human / likeness shadowed the tools of the same name: guide("skin") could never return the `skin`
tool's section. `guide("tool:<name>")` always returns a tool's section; test_toolsets asserts every registered tool is
reachable that way (and by its bare name where no topic shadows it).

## EEVEE, not Cycles (coordinator, from Joe 2026-10-14: "Blender with eevee built like a game would work is enough")
Guides judge in EEVEE and judge exports as the GLB re-imported into Blender EEVEE set up like a game; no Cycles
judging, no engine (Godot) checks. Engine-importer facts and reference shaders stay as consumer information.

### Cycles judging renders still in code (parked; not changed by the guides work)
- export_asset(preview=) / asset.preview renders the exported GLB with Cycles (blender_asset.py ~974): handed to the
  assembly agent (it is building the game-like EEVEE check).
- look_terrain perspective views (blender_terrain.py ~1050) and terrain tile views (blender_tiles.py ~1110).
- look_clutter (blender_clutter.py ~99, module-level render setup).
- a vegetation look path (blender_vegetation.py ~1156, near aim_sun).
- look_hair / look_skin engine="cycles" (optional, not the default; the guides call it reference only).
Bakes (bake_maps, bake_inputs, export_bake) use Cycles as a baker, not a judging render.
