# STATE: drape_band (wrapped folds drafted by draping) -- 2026-10-21, after round 5

DECISION (Joe 2026-10-21): collars, lapel rolls, cuffs, waistbands, turtlenecks, curved hems are DRAPED: describe the
worn shape, build it in 3D on what is under it, flatten it into the pattern piece. The flat piece stays the source of
truth (generated FROM the worn spec; the gate refuses a stale one). DRAPE ON THE FORM IT IS PLACED INTO (r4).
COORDINATOR (end of r5, C135): a collar is draped CLOSED, as it is cut; the open state is the INFO reach row, never
the draft source. Notes: docs/notes/cloth.md "drape band round 1..5" (grep only).

## The op (src/hifipushie/drape.py, docstring = spec; ledger C130-C135)
- garment key "drape": [{name, along, worn, layers: [{piece, kind: stand|fall, ...}], source}]; gate rows
  drape_band_current + drape_band_flat (p99 <= 2 %) + drape_band_reach (INFO).
- r2 stand ON THE NECK; r3 ONE FRAME (flat_frame); r4 measured stations {"at": ...}, stand lean, fall land_dir,
  leftTopJoin / rightTopJoin seams. KATs tests/test_drape.py.
- r5 (C134): THE OPEN NECK: worn open, each front above the first fastened button turns back flat on the chest (fold
  angle 10 = turned 170; kb shirt wear.no_tie; was 95). KAT tests/test_pattern_form.py
  test_open_neck_rolls_back_to_its_v_and_lies_on_the_chest (+ control at 95).
- r5 (C135): the OPEN drape is a NEGATIVE spring (worn outer ~400-420 vs sewn 445; spring need 530; closed reach 62 %).

## Garrett shirt (sh_garrett v17: open neck angle 10 (v16) + drape d5o OPEN on k5a, gate FAIL)
- Open form k5a / d5o fit: open neck turned L 162-172 / R 142-167 (k12a 55-110), on its base 2-3 mm (9-10), V 57
  below HPS (60), first button 74-77 (83). The fronts now turn back to a V (collar_k5a.png).
- d5o (point 0): flat collar p99 2.88 FAIL, spring short 129 FAIL; fit: spread 100 FAIL, points 37.5 below HPS,
  collar_state part, p99 14.0, corners FAIL, fit vs drape 15 mm p50 (97 max). Reviews: collar FAIL, wholefront FAIL.
- concept | d4o | d5o: spread 147 | 151 | 100; points below HPS 50-61 | 38 | 37.5; V 60 | 52 | 57; collar flat p99
  <=2 | 1.71 | 2.88. Jacket refit not run since r26 (collar not close).
- Renders $S/check/*_d5o.png, collar_k5a.png; reviews $S/rev_collar_d5o.log, rev_whole_clay_d5o.log.

NEXT (coordinator): drape the collar CLOSED (how it's cut: round 2's closed drape looked right); the open look comes
from the rolled-back fronts (C134) plus an arrangement if needed (C81); the open sweep stays a reach check (info), not
the draft source. Then fit on the open form k5a-style (angle 10 rolls), renders, reviews, then the jacket.
## Commands ($S = /mnt/data/hifipushie/drape_band5; run.sh = this worktree): kat.py <angle> [kind str top_x radius];
p2.py <form pkl> (open-neck reads); pe.py <form pkl> (stand-off columns); sweep5.py <worn> '<overrides>' (k5a, with
the spring read); fit5.py <tag> open (RUNNER=bin/capped); drape_d3.py <worn.json> [save|no] [piece.key=json]
(open base = form_k5a); render_d3.py - <tag> <views> (FORM=, capped); rev_d.sh <tag>; rev_w.sh <tag> [clay|diag].
