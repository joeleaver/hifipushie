# Product guides rewrite ("guides" agent, 2026-10-14)

STATE: all guides done (cloth, vegetation, hair + locks, skin, blockin, guide.md, human, likeness, gnm_driving,
tools_guide, terrain, clutter scrub); each core 87-181 lines (hair_locks 273); every core tested by a fresh agent.
NEXT: Joe / coordinator review; tooling suggestion: look_pattern line "armhole bottom N mm below the armpit".

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

## Cores after the rewrite (lines)
cloth 181, vegetation 149, hair 138, hair_locks 273, skin 125, block_in 129, playbook 134, human 141, likeness 132,
terrain 87. Total product markdown is about the same (~820 KB: details moved, not cut); what an agent reads FIRST
went from 345-1,142 lines to 87-181.

## Test agents (fresh, plan only, the guide tool only)
cloth (knit crewneck: described, measured armhole on the draft before any sim), vegetation (storybook oak: style,
structure, massing first; skeleton bare before style), hair (wavy side part: 9-item description for reference AND
render first), skin (fifties man: forms before the read, close-ups per feature), block_in (3 phone photos: stage 0
with authority per item, INFERRED list), playbook (badger-knight: stage-0 sheet, gates), likeness (jaw and nose:
character read first, every item), terrain (fjord brief). All followed the key rules; frictions fixed in the guides.

## Found, not fixed (outside the guides)
- Private subject tags in code comments (hair*.py, blockin*.py, makehuman.py, skin_swatch.py, blender_strands.py):
  removed 2026-10-14 (generic wording).
- Default paths under /mnt/data/hifipushie in env defaults (facenormals, denselm, humannormals, faceext).
