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
- r4 (C133): measured stations {"at": [[u, v], ...]} for any value; stand "lean" {"at": [[u, "neck" | deg]]};
  fall "land_dir" (ends walked over the BODY, lifted onto the cloth: _land_over_body, LAND_EASE_DEG, LAND_SMOOTH);
  stand top notches leftTopJoin / rightTopJoin, the fall sewn between them (joined_seams in cloth.pieces).
- KATs tests/test_drape.py 7 (+ test_open_fall_lands_out_on_the_fronts_and_sews_between_its_join_notches).

## Garrett shirt collar (sh_garrett v15: drape d4o OPEN; v14 d3o; v13 d3c closed)
- Worn spec = concept_v8 measured ($S/worn_d4o.json "source"): points 73-75 off CF, 50-61 below HPS, swept back;
  stand leans OUT ~35 deg at the collar end, 26 high at CF; side: fall edge 80 off CF; CB (rule) stand 32.
- concept | d3o | d4o: spread 147 | 113 | 151 (fitted); points below HPS 50-61 | 37 | 38; V 60 | 52 | 52; flat
  p99 collar <=2 | 1.93 | 1.71; seam stand|collar band -1..+1.5 | -4.7 | +1.2; cover 5-25 | 4.0 | 10.9.
- Gate FAIL on one row: collar_fall_spring (outer 310 vs need 527: the swept-back point -0.06 buys the spread with a
  tight fall). Fit p99 12.1 FAIL, collar_corners stand:34 12.9 % FAIL (as r3).
- Fit vs drape p50 7.0 / 6.5 mm: the BASE moved (fit neckline vs k12a p50 4 / max 11 mm, 4.7 mm back): drape on the
  form it is placed into, not another round's.
- Reviews FAIL: collar (stands up, points stick out sideways at jaw height, jagged leaf edge), wholefront (popped
  collar, no neck opening, baggy). PNGs $S/check/*_d4o.png. Jacket refit skipped.
- M12 ROOT: k12a is not open: fronts meet at the throat, neck edge 35-50 mm proud of the chest; landing the ends out
  on it costs 2.4-5.5 % p99. The concept's fronts roll back to a 60 mm V on the chest.

NEXT: the OPEN FORM first (coordinator call: the fronts' roll back to the concept V, lying on the chest, measured
flat), then re-drape d4o's worn spec ON that form (point back to 0, land_dir out) so the spring row passes, fit,
renders, reviews; then the jacket.
## Commands ($S = /mnt/data/hifipushie/drape_band4; run.sh = this worktree): drape_d3.py <worn.json> [save|no]
[piece.key=json ...]; sweep.py <worn> '<[overrides]>'; fit_d3.py <tag> <closed|open> (RUNNER=bin/capped);
render_d3.py - <tag> <views> (FORM=, capped); rev_d.sh <tag>; rev_w.sh <tag> [clay|diag]; drift.py <form pkl>.
