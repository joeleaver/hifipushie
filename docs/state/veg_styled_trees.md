# Styled trees (pixar / cartoon / blobby): STATE (2026-11-17, branch claude/veg-oak-gaps-fe5013)

Three gaps Joe hit on Braynard Racing's storybook oak (pixar), fixed in the style code for every tree (C504-C506).

## Current best
- Test subject: /home/joe/dev/braynard-racing/workspace/props/braynard_oak/spec_round2.json; concept
  .../props/leafy_oak_concept.png. Suggested round 3 = round 2 + `style.crown.down_to: 0.35`, the `style.crown.cards`
  override dropped (the 2 m card workaround is no longer needed): /mnt/data/hifipushie/vegoak/spec_round3_suggested.json.
- Before / after beside the concept: /mnt/data/hifipushie/vegoak/oak_round3_compare.png.
- Numbers (oak, round-2 spec): shell bottom 0.46 H -> 0.34 H with down_to 0.35; default cards' leaf cover 1.1 -> 4.0
  (cards 171 -> 1167, LOD 0 4.7k -> 9.7k of 14k triangles); roots reach 2.1 m on the ground (the flare alone ~1.4).

## What changed
- veg_cloud.shell_cards: `cover` counts LEAF area (card area x the picture's alpha fill), so cards actually cover
  the shell (random cards at leaf cover ~1.1 left about a third of the shell bare: the bald lumps). The top clamp
  is the shell's own top + the most `out`; a card sinks no deeper than its own shell point, and for any overhang left
  it shrinks to half size at most. Returns `pos` (each card's middle).
- Report: a "leaf cards on the shell" line (count, metres across, x a clump, leaves per picture, leaf cover); a WARNING
  past CARD_WARN 1.5 x a clump explaining that `cards.count` is leaves per picture.
- veg_style_wood._roots: spec `roots` -> fat root buttresses (own axes, joined over ROOT_JOIN 3 x blend) in the styled
  wood field (every styled sheet); mesh bounds now cover them.
- veg_style_crown.skirt + sheet keys `crown.down_to` (null), `skirt_rim` 0.6, `skirt_curl` 0.25, `skirt_max` 2 on all
  four sheets: foliage points hung under the outer twigs, so the masses reach down the crown's sides.
- store.BUILD_VERSION 35. Docs: vegetation_styles.md (wood roots, crown.down_to, cards cover / clamp / size),
  vegetation_spec.md (roots on styled trunks).

## Open faults (game visibility)
1. The oak with down_to has a wide, boxy crown and a flat bottom edge; the concept is a taller dome. Try a smaller
   `skirt_curl` / `spread`, or more masses, next.
2. With the default cards the leaves are fine fuzz; the concept's big clay leaves came from round 2's `cards.leaf` 4,
   but those 2 m cards warn now. Big leaves want `big_leaves` or a larger `leaf` with a higher `length`, not giant cards.
3. Outline IoU against the realistic tree drops to 0.57 with down_to (intended; the warning says so).
4. Not blind-reviewed (no LOOK gate run); not approved.

## Decisions in force
- These are general fixes: no oak-only paths. down_to is opt-in (null by default); the cards cover change applies to
  every pixar tree (more cards, still within budget).

## Dead ends
- Clamp fix alone: no visible change on this oak (its shell top = the grown height); the bald patches came from
  under-cover, not from the clamp.
- Thin tube roots: read as spider legs. A 1 x blend join: hard crease at each root's top.

## Commands
- Tests: `uv run python -m pytest -m "" tests/test_veg_style_crown_depth.py tests/test_veg_style.py`
- Probe / renders: /mnt/data/hifipushie/vegoak/{probe2,render,render_lumps,render_final,bald}.py (run from the worktree).

NEXT: Braynard regrows the oak from spec_round3_suggested.json once this lands and the runners restart; then a blind
LOOK against the concept and work through the open faults (crown shape first).
