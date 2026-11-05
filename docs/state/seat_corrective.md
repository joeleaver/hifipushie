# Stub seat corrective (seated hips 90 on legs blended into the body): STATE 2026-11-05

Branch seat-corrective (worktree .claude/worktrees/seat-corrective), from main c1b55537. Leg-blend's "Open 1"; asked for
by Baynard Racing (Puddles, gap 22). Not pushed; coordinator lands. Exploring run (no gate).

## What the tools hold now (correctives.py `_stub_target` docstring = spec; ledger C374)
- `keys(bones, girth=)`: frames from `rig.arc_frames(bones, girth)` (the ones the weights used). New motion
  `UpLeg_flex` (axis -X, key 90 = rig_audit.seated) exists ONLY on a stub (`STUB_ONLY`): a person's hip still has none.
- Stub target: LBS, then (1) inner side (belly): the hip family's move sharpened by the limb's share `STUB_SHARP`
  (0.3, 0.9): body skin with a weight tail stays put; (2) outer side (seat): parent-side skin held at the turned
  thigh's underside, `STUB_FLOOR` 1.0 x girth (soft min), for skin under `STUB_SEAT_TAU` (0.2, 0.8) of the limb;
  (3) the move faded across the midline so the two sides add to one. `STUB_MUSH` delta mush exists, off (0).
- Export: export_asset solves each part's keys from its own `limb_girth`; the json's rig.correctives gets the
  UpLeg rows (driver as every corrective; Blender's preview drives them by itself). No BUILD_VERSION bump.
- People: keys identical with or without girth, no UpLeg key (tests/test_rig_stub.py, 5 tests, 2 new).

## Proof (workspace pudsc = copy of pud2; renders in the Baynard notes folder, seat_corrective/)
- Model (160 voxel build), seated: edges > 3x 20 -> 37, > 2x 406 -> 503, p99.9 2.18x -> 2.27x. Seat skin > 5 mm
  past the turned thigh's underside: L 30 -> 7, R 38 -> 10 (worst 20 -> 12 mm). Front: the fold line at z 0.21-0.24
  is gone (belly stays round, meets the thigh at z 0.2). Back: as LBS with the seat a little higher. Crotch: still
  notched (both legs' keys solved alone).
- Real export (pudsc.glb, 15k tris, /mnt/data/hifipushie/seatcorr/export): UpLeg targets in, ~1000 vertices each.
  Seated body edges > 3x 1 -> 4, > 2x 40 -> 64 of 14k. At this density LBS was already near clean: the corrective's
  gain shows on the model, barely on the GLB (front edge a touch lower, jaggies at the thigh top either way).

## Open, ranked by what shows in the kart
1. Judge the GLB in the kart at 1 m (Joe / Baynard): it is not yet a clear win on the export. If it reads worse,
   STUB_ONLY = () turns it off with nothing else changed.
2. Crotch notch at the midline (model and GLB): needs both legs solved together (a seated key on the pair).
3. Knee: Leg_flex solves 0 vertices on a stub's knee (reach 0.28 x a 5.5 cm shin < its girth). Not touched.
4. topodensity.hinge_mask still sizes a stub hip by length: it runs before weights exist, so limb_girth can't be
   passed; it would need a weight-free girth. Not done.
5. The jagged line round the body at z 0.22-0.25 is the weights' ARC_BODY ramp (2.5 x girth) grazing the belly:
   a weights fix (rig.py), not a corrective one.

## Dead ends (C374)
Turn by the share round the pivot (bottom swung 10 cm down); ARAP of the ramp (a flap); sharpening the back too
(the weights put the bottom on the leg: a sheet); counting the knee in the family; delta mush (ridges); a seat
plane from the thigh's own skin (a pig's thigh has no back skin: it came out on the front).

## Commands
`/mnt/data/hifipushie/seatcorr/measure.py <model> [render dir]` (CMSET="NAME=val;..." overrides), glbcheck.py.

NEXT: coordinator lands after bin/suite; Baynard exports Puddles and judges seated in the kart (Open 1) before
anyone builds on it; then the pair key for the crotch.
History: this page + commits on seat-corrective; ledger C374.
