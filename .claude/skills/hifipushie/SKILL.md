---
name: hifipushie
description: Model characters, creatures, props and environments with the hifipushie MCP server (skeleton + SDF blobs, strokes, parts, clay renders; realistic humans, hair, clothes, terrain and plants have their own tools). Use whenever the user asks to make, sculpt, dress, fix or detail a creature, character, prop, garment or terrain with hifipushie, or to continue work on a hifipushie model.
---

# Modelling with hifipushie

Call the hifipushie `guide` tool first and follow it: it is the full playbook. The essentials:

- **Reaching the tools:** a small core is native (`guide`, `find_tool`, `call_tool`, `list_models`, `get_model`,
  `kit_reference`, `put_model`, `edit_model`, `look`, `check`, `measure`, `history`, `revert`, `review_view`). Every
  other tool (plan, concept, scene, export, human, skin, likeness, hair, cloth, terrain, plants, clutter) runs
  through `call_tool(name, args)`. `find_tool("<the job in your own words>")` names the tool with its parameters
  and an example call; `find_tool("")` lists every tool by domain; `guide(topic="<tool>")` has any tool's full
  text. If the hifipushie tools arrive deferred, load them with ToolSearch.
- **Which path:** a creature, a cartoon character or a prop is a spec (`put_model`; props and rooms:
  `guide(topic="props")`). Hair, clothes, skin, terrain, plants and clutter have their own tools and a guide topic
  each (`guide(topic="hair")`, `"cloth"`, `"skin"`, `"terrain"`, `"vegetation"`, `"clutter"`): read the topic
  before working there. Clothes have one path: `garment_plan` -> `body_tape` -> `draft_pattern` ->
  `chain_garment` -> `garment_details` -> `look_chain` -> `export_garment`.
- **Tool answers end with "next:"**: do what it says. Judge every result beside its reference; an independent look
  is `review_view`, one view per call.

0. **Realistic humans start from `spec["base"]`** (MakeHuman body + GNM head, shaped by parameters: guide 4d),
   never from blobs and kits. The blob/kit route below is for creatures, cartoons and props. **A person from
   pictures: the artist block-in is the default** (`guide(topic="block_in")`; its tools run through `call_tool`):
   `human_reference` for the cameras, `block_in_start`, then rounds of look -> name the biggest mass / plane
   difference -> ONE small `block_in_step` -> keep only if the whole face reads closer and no target went out; lids
   by `lid_read`.

1. **Stages, with `check` after each:** plan (`set_plan`: front/side outlines, landmarks, sections) →
   blockout (`put_model`, kits, `fit` against the plan) → secondary forms (strokes) → detail
   (strokes with repeat/scatter, in close-ups). Fix proportions in the plan, where it's cheap.
2. **Show your work:** tool images may be invisible to the user. Use `save=` on `look`/`check`/`set_plan`
   and send them the PNG at each milestone, with a short honest read of what works and what doesn't.
3. **Judge with the right view:** `look(strokes=True)` for stroke placement, `shading="raking"` for
   forms, `shading="curvature"` for blobbiness and defects; close-ups (`focus`, `zoom`) for any detail.
4. **Strokes:** broad and shallow, depth tapering to 0 at the ends of masses, creases at least 3 voxels
   wide, anchored on skeleton bones or kit features (never raw head-relative guesses).
5. **Geometry vs strokes:** separate digits, tusks and horns are geometry (bones, kits, seated joints);
   strokes only push skin in and out.
6. **Parts** for anything with its own material: eyes, teeth, clothing (solid shells cut to a region).
7. **Paint** (`spec["paint"]` layers) last, broad to fine: base, countershading (`facing`), regions (`near`),
   markings (`path`), breakup (`noise`, `cavity`), then weathering as mask stacks (`ao`, `cavity`, `cells`,
   `breakup`: edge wear, grime, dust; recipes in kit_reference) and `height` for fine relief. Judge with
   `shading="flat"`, each mask alone with `look(paint_layer=...)` (its info line says how much it covers).
8. **History:** every model gets a `story` (age, climate, use, directions, events) and each event becomes
   geometry (weather ops, lumpy, chips, things out of place) and paint (weather side, sky, wear paths).
   Perfect copies, axis-aligned furniture and flat unmarked faces read as CG: `check` flags them.
9. **When something looks wrong,** isolate it (remove suspects one at a time, curvature view) before
   changing anything; don't stack speculative fixes.
