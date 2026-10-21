# STATE: drape_band (wrapped folds drafted by draping) -- 2026-10-21, round 5

DECISION (Joe 2026-10-21): collars, lapel rolls, cuffs, waistbands, turtlenecks, curved hems are DRAPED: describe the
worn shape, build it in 3D on what is under it, flatten it into the pattern piece. The flat piece stays the source of
truth (generated FROM the worn spec; the gate refuses a stale one). DRAPED IN THE DESIGN'S STATE (entry "worn":
"open" | "closed", default closed; Garrett's shirt is worn OPEN); the other state's sweep is an INFO reach row.
DRAPE ON THE FORM IT IS PLACED INTO (r4). Notes: docs/notes/cloth.md "drape band round 1..5" (grep only).

## The op (src/hifipushie/drape.py, docstring = spec; ledger C130-C134)
- garment key "drape": [{name, along, worn, layers: [{piece, kind: stand|fall, ...}], source}]; gate rows
  drape_band_current + drape_band_flat (p99 <= 2 %) + drape_band_reach (INFO).
- r2 stand ON THE NECK; r3 ONE FRAME (flat_frame); r4 measured stations {"at": ...}, stand lean, fall land_dir,
  leftTopJoin / rightTopJoin seams. KATs tests/test_drape.py.
- r5 (C134): THE OPEN NECK: worn open, each front above the first fastened button turns back flat on the chest (fold
  angle 10 = turned 170; kb shirt wear.no_tie; was 95). KAT tests/test_pattern_form.py
  test_open_neck_rolls_back_to_its_v_and_lies_on_the_chest (+ control at 95).

## Garrett shirt collar (sh_garrett v16: open neck angle 10; drape still d4o, draped on k12a)
- Worn spec = concept_v8 measured (drape_band4/worn_d4o.json): points 73-75 off CF, 50-61 below HPS; stand leans OUT
  ~35 deg at the collar end; V 60 below HPS, first button 83.
- Open form k5a (step 1): turned L 162 / R 142 (k12a 55-76 / 110), turned part on its base 3.1 / 2.7 mm p50 (9-10),
  V 57.1 below HPS, button 76.8, fit p99 11.4. collar_k5a.png: the fronts turn back to a V; the d4o collar (draped on
  k12a) no longer sits on them.
- concept | d4o: spread 147 | 151; points below HPS 50-61 | 38; flat p99 <=2 | 1.71; gate FAIL collar_fall_spring.

NEXT: step 2: re-drape d4o's worn spec ON form_k5a (point back to 0, land_dir out on the rolled fronts) until
collar_fall_spring passes with flat p99 <= 2 %; then fit (step 3), renders, reviews; jacket if close.
## Commands ($S = /mnt/data/hifipushie/drape_band5; run.sh = this worktree): kat.py <angle> [kind str top_x radius];
p2.py <form pkl> (open-neck reads); pe.py <form pkl> (stand-off columns); fit5.py <tag> open (RUNNER=bin/capped);
drape_d3.py <worn.json> [save|no] [piece.key=json]; render_d3.py - <tag> <views> (FORM=, capped); rev_d.sh; rev_w.sh.
