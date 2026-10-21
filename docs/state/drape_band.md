# STATE: drape_band (wrapped folds drafted by draping) -- 2026-10-21, round 3

DECISION (Joe 2026-10-21): collars, lapel rolls, cuffs, waistbands, turtlenecks, curved hems are DRAPED: describe the
worn shape, build it in 3D on what is under it, flatten it into the pattern piece. The flat piece stays the source of
truth (generated FROM the worn spec; the gate refuses a stale one). DRAPED IN THE DESIGN'S STATE (coordinator r3:
entry "worn": "open" | "closed", default closed; Garrett's shirt is worn OPEN); the other state's sweep is an INFO
reach row, never a gate. Notes: docs/notes/cloth.md "drape band round 1/2/3" (grep only).

## The op (src/hifipushie/drape.py, docstring = spec; ledger C130, C131, C132)
- garment key "drape": [{name, along, worn, layers: [{piece, kind: stand|fall, height / ext / gap | rise / land /
  end_in / point}], source}]; draft / record / gate rows drape_band_current + drape_band_flat (p99 <= 2 %) +
  drape_band_reach (INFO); reach. drape_state(entry) reads "worn" (or the older "state").
- r2 STAND ON THE NECK (neck_stand) on a TRUED NECKLINE (true_curve); curve_side; develop pull 0.005 / rounds 12.
- r3 ONE FRAME (C132): drape.flat_frame normalises the flattened half for BOTH the emitted piece (to_piece) and the
  drape mesh (placement: place_on_drape). MESH_FRAME 2 in worn_key: frame-1 drapes (v11, v12) are stale.
- KATs tests/test_drape.py 6 (+ test_pieces_place_on_their_own_drape: neckline dropping 40 mm to CF).

## The placement bug (r1 + r2 "front 0.29 m triangle"): FIXED, round 3 step 1
- Cause: the stand's mesh uv was the drape's flat uv with v negated (draft normalised by the top CF corner, to_piece
  by the top CB point). cloth.place laid the stand ~60 mm up the neck, flat (front.R|stand seam pairs 54 mm apart
  at the start); _pin_seams dragged the fronts' CF neck corners into the jaw; _clear_of_body's uncapped gap growth
  (+22 mm a round for a face held by fold rows) flung them 0.2 m. Uncrush was never the lever.
- Open side-issue (not fixed, not needed now): _clear_of_body's per-round gap growth has no cap when grow=None.
- Garrett closed d3c (v13 = d2c numbers, frame 2): form fit PLACES and completes (264 s); X0 vs drape 0.0 mm;
  fitted vs drape p50 6.0 / 4.2 mm (stand / collar); fit p99 12.3 FAIL; points 20.9 apart, 51.0 below HPS.
- Gate FAIL rows on v13 (r2 had them too): seams (collar sewn edge 426.3 vs stand top 448.3 flat: -4.9 %, band
  -1.0..+1.5), checklist:collar_cover 1.7 mm (5-25).

## Garrett shirt collar (spec sh_garrett v14: drape d3o OPEN, point -0.04; v13 d3c closed; v12 d2c)
- r3 open lean (C132 row): worn open, past OPEN_OFF 10 mm seam stand-off the stand carries on its under cloth.
- d3o: stand p99 0.40, collar 1.93 (flat PASS); points 107 apart / 42.7 below HPS in the drape, 113.3 / 37.4 fitted
  (concept ~147 / 50-61); V 52.1 (60); fall 51.9 CB (~44). Reach closed INFO: 2.29 / 9.16 %. Point lever
  non-monotonic (-0.03..-0.07: 102-143 apart, 30-64 below, 1.9-3.6 %): stop-loss.
- Gate FAIL: seams -4.7 % (collar sewn edge vs stand top TO CF: the 2 x 12 mm end_in; seam definition item),
  collar_cover 4.0 (5-25). Open fit places, p99 12.4 FAIL, collar_corners stand:34 14 % FAIL.
- Reviews FAIL: collar (stands to the jaw and flares, stubby tabs high at the shoulder, V closed), wholefront.
  PNGs $S/check/{collar,point_L,point_R,wholefront}_d3o.png. Jacket refit skipped (collar not close).

NEXT: the fall must LIE on the open fronts: land far down and out at the ends (the concept's points on the chest),
not hug its own stand; describe that as the worn rows (land at the end ~40-50 mm below the seam ON the rolled front,
point 0) and rerun; fix the stand|collar seam definition to the collar's sewn ends; then fit, renders, reviews, jacket.
## Commands ($S = /mnt/data/hifipushie/drape_band3; run.sh = this worktree): drape_d3.py <worn.json> [save|no]
[piece.key=json ...]; fit_d3.py <tag> <closed|open> (capped); render_d3.py - <tag> <views> (FORM=, capped);
rev_d.sh <tag>; probe1-6.py (placement probes).
