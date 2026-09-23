---
name: hifipushie
description: Model characters and creatures with the hifipushie MCP server (skeleton + SDF blobs, strokes, parts, clay renders). Use whenever the user asks to make, sculpt, fix or detail a creature, character or prop with hifipushie, or to continue work on a hifipushie model.
---

# Modelling with hifipushie

Call the hifipushie `guide` tool first and follow it: it is the full playbook. The essentials:

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
7. **When something looks wrong,** isolate it (remove suspects one at a time, curvature view) before
   changing anything; don't stack speculative fixes.
