# Legs blended into the body, seated (stub limbs): STATE 2026-11-05

Branch leg-blend (worktree .claude/worktrees/leg-blend), from main d89f5709. Asked for by Baynard Racing (Puddles the
pig, gap 22 in baynard-racing/workspace/puddles/hifipushie_gaps.md). Not pushed; coordinator lands. Exploring run (no gate).

## What the tools hold now (rig.py, `_arc_bend` comments = spec; ledger C373)
- `limb_girth(rb, V, J, W)`: per bend driver, the lower quartile of the distance from the segment's axis of the skin
  on its middle half whose top weight is in the chain below it.
- A limb ROOT (`ARC_ROOTS` UpLeg, Arm) with girth > `ARC_GIRTH` 0.25 x its length is a STUB. Its arc zone's unit is
  girth / `ARC_STUB_UNIT` 0.1 (not the length), the zone has no radial cut-off, the side mask runs 2 cm past the
  midline, and skin farther than `ARC_BODY` (1.1, 2.5) x girth from its axis gives its whole chain's weight (thigh,
  knee, foot, their helpers) to the parent. A stub's knee stays an ordinary hinge.
- People untouched: a person's limb is never a stub; `_arc_bend` is bit-identical (tests/test_rig_stub.py, 3 tests).
- Export: weights only, through the same `rig_weights` -> `_spread_twist` -> `_arc_bend` path that export_asset(rig=True)
  uses; the bend helpers and their rig notes (engine wiring) were already there. No engine change, no BUILD_VERSION
  bump (no meshing change). NOT checked: an actual export of the blended model (do it before Baynard relies on it).

## Proof (hifipushie workspace; renders in the Baynard notes folder, leg_blend/)
- pudlb_one = pud2 with thigh/shin back in the body (no part), body rig_drop without UpLeg/Leg/Foot/ToeBase.
  pudlb_sep = pud2 as is. pud2 untouched.
- Seated (hips, knees 90), edges stretched > 3x: before 2442 (> 2x 5568, p99.9 6.7x; belly torn across at z 0.25-0.30, thigh
  weight 13 cm up the belly); after 60 (> 2x 816, p99.9 2.2x). Leg's own skin keeps 0.99 leg weight. Layers seated: none crossing
  (pudlb_sep: legs/body BAD at 17 / 15 vertices). Standing: no step (one skin), pudlb_sep shows the step.
- Swept ARC_BODY: starting < 1.1 x girth looked cleaner (2 edges > 3x) only because the thigh's own skin went to the
  hips (half turned): a dead end, don't go back.

## Open, ranked by what shows in the kart
1. Seated, still visible at 1 m: a fold line where the belly meets the thigh's top (front z 0.21-0.24), the seat
   behind the thigh dragged down ~5 cm toward the shin (it lies 1.1-2.5 x girth from the thigh's axis: the ramp),
   a crumpled crotch between the legs. Not "no tear" yet. Next candidate: a seated pose corrective on this skin
   (correctives.py, solved for UpLeg 90 on the stub; its `arc_frames` call takes no girth yet, nor does
   topodensity.py's: pass `limb_girth` there first), judged on the seat and crotch only.
2. Weights audit still BAD on Puddles for joints unrelated to this (neck, spine, head flips; same as before).
3. Arms are stubs too by the rule (Puddles' are their own part, not tried blended).

NEXT: coordinator lands leg-blend after bin/suite; then a corrective run for open 1 (the seat and crotch), then
Baynard re-exports Puddles with legs in the body and judges seated in the kart.
History: this page + commits on leg-blend; ledger row C373. (No line in CLAUDE.md Threads: it would pass 8 KB.)
