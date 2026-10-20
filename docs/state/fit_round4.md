# STATE: fit_round4 (Garrett jacket v2 + shirt: the collar fall's turn on the form) -- 2026-10-19. NO SIMS.

STATE: HANDOVER. Steps 1-4 done. Fold cause found + tool fixed (C46); notch step item added (C47), fails round 3 and 4.
Blind review FAIL (front, three); side / back / top have NO jacket reference, not reviewed. My read: still no notch,
the collar is a thick roll up the neck, shirt collar oversized and asymmetric, shards at the L lapel edge.
NEXT (one cause at a time, re-measure after each): (a) NO NOTCH: notch_step L open 0.3 / depth 0, R 9.8 / 7.6 (ref
open 2-10, depth 10-26): the collar end lies against the lapel point in the front view; find why (pressed seam
collar end <-> gorge, _lay_pressed / _pressed_cells) before the draft. (b) Stand off the neck 14-35 mm (worse at CB:
6 -> 14 since the fall lies on it). (c) Shirt through the jacket 365 -> 447. (d) Collar section +-90 deg 86-107: read
what is under it there before calling it a fault (the collar's front runs down the chest; the az read may be wrong).
Files: $FR4 = /mnt/data/hifipushie/dress_garrett/fit_round4/ (run.sh = this worktree). harness.py = the jacket's form
assembly alone from cached inputs.pkl (~3 min; = the gate's numbers): `harness.py <tag> [PF_CONST=json]` -> asm_<tag>.pkl
+ per-phase collar trace. probe5.py (collar section per station), notch.py (notch step), collar.py <asm> (measures +
renders), refs.py, sheet.py, review.sh. asm_seam.pkl = round 4's result. History: cloth.md "fit round 4".

## Step 1: the fold (cause)
- "-34 deg" was never the turn: it is the hinge report's REST per row (5 roll rows x 34 = 170). The NaN in
  turned_deg [171, 167, NaN] IS the collar roll: fold_turned read only the fold's own piece, and the fall's base side
  is 4 mm (FALL_FOLD at) < HINGE_BAND 6 mm -> no base triangles -> NaN. The turn was never measured.
- Measured in section (probe5), round 3: CB 161, +-30 151-163, +-60 131-149, +-90 88-112: turned at the back, open at
  the sides. Trace per phase: turn_flaps 154-169 everywhere; SEAT and LET_GO lose it at the sides.
- KAT (tests test_two_piece_collar_turns_over_its_stand: stand band + fall strip, roll 4 mm above the seam, neck
  cylinder): passes 173-177 at every station with the old code -> the hinge is fine; nothing pushes there.
- Cause: the flap's "lie on your base" (over list: one THICK outside, FLAP_PULL) used only the fold's OWN base (the
  4 mm strip). The fall had nothing to lie on; where the shoulder / under-layer pushed it, it stood off. Fix
  (general): BASE_ACROSS_SEAM: a fold whose own base is < BASE_NARROW 12 mm lies on the piece(s) sewn to it. Garrett
  seat phase 172-179 at -60..60; let_go: fall edges 3-8 mm off the stand (were 15-25). fold_turned reads across the
  seam (3D), past a roll's arc, in a 5 mm section slab (KAT 174 true -> 165 read; was NaN / 151).

## Table (round 1 | round 3 | round 4 | target)
| fall top over HPS (CB) | 71 | 51.8 (stand 43.8) | 40.1 (stand 33.3) | ~stand top |
| collar turn in section CB / 30 / 60 / 90 | - | 161 / 151-163 / 131-149 / 88-112 | 161 / 162-163 / 142-158 / 86-107 | ~170 |
| fall edge off the stand CB / 60 | - | 15 / 18-25 | 5 / 3-8 | ~2-5 |
| fold_turned lapels / collar | | 171 / 167 / NaN | 171 / 166 / 142 | 165-180 |
| notch step L open/depth, R | - | 0.3/0, 12.3/9.6 FAIL | 0.3/0, 9.8/7.6 FAIL | open 2-10, depth 10-26 |
| notch gap / angle (3D) | 57 / 74 | 26.5 / 61.4 | 41.2 / 92.6 | 20-40 / 60-90 |
| stand gap to neck CB -> front | 15-34 | 6/10/24/38 | 14/18/25/35 | 2-5 |
| collar end to gorge | 15 | 14.9 | 14.1 | ~0 |
| shirt collar shows back / side | -11/-8 | 7.7/6.2 | 19.4/15.8 | 10-15 |
| shirt faces through jacket | 268 | 365 | 447 | 0 |

## Known open
form_validated() False. Refs: front = concept (scale-matched crop), three = desk portrait (painted, not scale-matched);
side / back / top: none. BASE_ACROSS_SEAM is default ON (tests pass); revert = set False.
