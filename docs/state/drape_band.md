# STATE: drape_band (wrapped folds drafted by draping) -- 2026-10-21, round 4

DECISION (Joe 2026-10-21): collars, lapel rolls, cuffs, waistbands, turtlenecks, curved hems are DRAPED: describe the
worn shape, build it in 3D on what is under it, flatten it into the pattern piece. The flat piece stays the source of
truth (generated FROM the worn spec; the gate refuses a stale one). DRAPED IN THE DESIGN'S STATE (entry "worn":
"open" | "closed", default closed; Garrett's shirt is worn OPEN); the other state's sweep is an INFO reach row.
Notes: docs/notes/cloth.md "drape band round 1/2/3/4" (grep only).

## The op (src/hifipushie/drape.py, docstring = spec; ledger C130-C133)
- garment key "drape": [{name, along, worn, layers: [{piece, kind: stand|fall, ...}], source}]; gate rows
  drape_band_current + drape_band_flat (p99 <= 2 %) + drape_band_reach (INFO).
- r2 stand ON THE NECK (neck_stand) on a trued neckline; r3 ONE FRAME (flat_frame, MESH_FRAME 2).
- r4 (C133): measured stations: any value {"at": [[u, v], ...]} (_field); stand "lean" {"at": [[u, "neck" | deg]]}
  (stand_lean: deg + in / - out, "neck" = the solve); fall "land_dir" (deg out of straight down: the landing walked
  over the BODY and lifted onto the cloth, _land_over_body, eased over LAND_EASE_DEG, line smoothed LAND_SMOOTH);
  stand top knotted where the fall's sewn ends join (leftTopJoin / rightTopJoin) and cloth.pieces sews the fall
  between them (drape.joined_seams). Surf.project(facing=) for walkers.
- KATs tests/test_drape.py 7 (+ test_open_fall_lands_out_on_the_fronts_and_sews_between_its_join_notches).

## Garrett shirt collar (sh_garrett v15: drape d4o OPEN; v14 d3o; v13 d3c closed)
- Worn spec = concept_v8 measured ($S/worn_d4o.json "source"): points 73-75 off CF, 50-61 below HPS, swept back
  (18 px out, 35 px below the collar-end notch); notch ~15 below HPS / 54 off CF; stand leans OUT ~35 deg at the
  collar's end (lies back), 26 high at CF; side: fall edge 80 off CF; CB (rule): stand 32, cover 5-25.
- d4o: stand 0.38 / collar 1.71 % p99 (flat PASS); drape points 135.8 apart, 43.6 below HPS; fall CB 62.3; seam
  fall 434.8 vs stand join-to-join 429.7 = +1.2 % (was -4.7 CF to CF). Reach closed INFO 10 / 14 %.
- M12 (measured, k12a): the open form's front neckline at the collar's end stands 35-50 mm PROUD of the chest and
  its edge is curled; land_dir 70-100 / deeper land gave 123-144 apart but 2.4-5.5 % p99 (stop-loss): the spread
  comes from the swept-back point (-0.06), as the concept draws it.
- r3 numbers: d3o 107 apart / 42.7 below (drape), 113 / 37 fitted; fit vs drape p50 7.5 / 4.6 mm.

NEXT: step 4 running: pattern_check + open form fit (f_d4o.log), fold rows, collar_corners, fit-vs-drape self-check;
renders (collar, points, wholefront) + blind reviews; jacket refit only if the collar review is close.
## Commands ($S = /mnt/data/hifipushie/drape_band4; run.sh = this worktree): drape_d3.py <worn.json> [save|no]
[piece.key=json ...]; sweep.py <worn> '<[overrides]>'; fit_d3.py <tag> <closed|open> (RUNNER=bin/capped);
render_d3.py - <tag> <views> (FORM=, capped); rev_d.sh <tag>; probe_a-e.py (open-form reads).
