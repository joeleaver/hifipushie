# STATE: skin (projskin2 agent) -- rewritten 2026-10-19 after r24

## Current best skin for export (by blind A/B; NOT Joe-approved unless approved.json says so)
- Tess: **tp_k19_a16** (on the approved head tp_k19; r24 A/B 2-1 over a6: lids win, mouth lost). = a6 + pale lid + thin crease
  line (skin.folds.lid_fold .6 = 0.51 mm, passes the fold gate; lid_shade pale neutral), lips.border 3.0, brows colour #22160e at
  shadow .3 (brow L 48.3, photo 50.2).
- Garrett: **gp_h6c_a11** (on approved gp_h6c; r24 A/B 2-1 over a6; a10 1-0) = a10 + lips darker / less salmon, stubble cheeks .85,
  crepe 1.2. Iris KEEP #585c54 (r23: cast-corrected photo favours it over approved #61584f; rendered iris ~12 L too light, owed).
- Candidates rendered, not A/B'd: tp_k19_a17 (= a16, blemish density off the alae: no change), **a19** (a17 + lips strength 1,
  melanin 16, border 1.8: lip L 54.3 -> 48.3, photo 40.8), a18 (a17 + skin.shading.rough_breakup .3).
- Private heads: paused.

## Open faults (by game visibility)
1. 1 m: brows too dark / heavy, near-black at the head (both heads, every reviewer). Garrett: should be sparse grey.
2. 1 m: lips. Tess lip L 54 vs photo 41 (a19 = -6 L; a* 13.6 now under photo 16: blood 2 -> 2.6 next); a16's 3 mm border blurred
   the lip (target border ~1.8). Garrett: salmon-orange / too saturated vs muted mauve.
3. 1 m: Tess left ala red-brown blob = NOSE FORM (soft concavity, no crisp alar groove), not skin maps (stack symmetric, blemishes
   ruled out). Route to head / block-in. Owed: probe an a16 export bake's albedo at the ala L vs R.
4. 1 m: skin "peach vs pinkish neutral" (Tess); uniform cheek speckle (stack fine_strength .5 calms it: r22 a9).
5. 1 m: Garrett cheek_r vertical scratch streaks (crepe 1.2 -> back to .8); stamped under-eye ripples; beard missing along the
   jaw / sideburn; blue fleck at the inner corner; furrows too faint.
6. Export-side (not ours): stubble / speckle point-sampled by the bake (assembly BAKE_PREFILTER, not yet acting).

## Decisions in force
- Gates (docs/notes/gates.md): describe -> measure -> independent blind look -> approve (Joe / coordinator only).
- CURRENT BEST changes only by blind A/B (bin/review-ab; CLI rate-limited before 13:00 MT -> fresh blind subagent on its trios,
  unblind with key.json).
- Judge at the 1 mm face the export now meshes (coordinator), not 7 mm stage tiles alone.
- lid_fold is a field modifier: coordinator OK'd .6 (fold gate: relief <= 1 mm ships).
- Family heads never in the repo; critique the model, never the person.

## Dead ends / rules (don't retry)
- Darkening lips by lowering lips.strength with melanin up in one step (cancels): melanin at strength >= 1, one lever per step.
- Brows "soft" to lighten (washes them, +12 L); thickness / opacity / soft move L together: one at a time against brow L.
- lid_fold 1.0 (lumpy roll on the lashes). Crease band = crease_strength (r22), not lid_shade.
- Ala patch as blemishes (a17 = a16) or as de-light asymmetry (stack even). skin_layers.even_out: works, isn't the fix.
- a14 (calmer cheek + lid line + border 3 lips together): lost 0-4.
- Garrett iris back to #61584f: the photo favours #585c54.

## Commands (C=/mnt/data/hifipushie/projskin/cut; run from the worktree)
- Variants: cut/r24/mk24.py (pattern: mk22*.py). Renders: MODELS="<m> ..." bash cut/r23/chain23.sh (sh20 frames; chains wait on DONE).
- Measures + tiles: python cut/r22/m22.py <dir> <cols...> (brow L, lip L / a* / edge, cheek mottle, beard rows, glabella).
- Ala: cut/r24/ala24.py, asym24.py. Trios: python3 cut/r21/trios.py <out> <tiles22 dir> <old> <new> -> review-ab / blind subagent.
- NEXT A/B ready: python3 cut/r21/trios.py out/private/r24/ab_t_a19 out/private/r23/tess/tiles22 tp_k19_a16 tp_k19_a19.

## History (grep only)
docs/notes/skin.md "## r22", "## r23", "## r24" and their Handovers; "CURRENT BEST SKIN FOR EXPORT" lines; "## projskin", "## skinread".
