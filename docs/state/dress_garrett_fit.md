# STATE: dress_garrett_fit (Garrett jacket over the approved shirt gc1: closed form fit + ONE release sim + arrangement) -- 2026-10-22, round 29

DESIGN FACTS (Joe, settled): the jacket is worn OPEN, unbuttoned; it falls straight down (no waist suppression, side
line plumb). Put "the reference jacket is worn open, unbuttoned" in every review's context. Renders show the OPEN,
ARRANGED jacket only. Covered show-through is not a fault (C153); seen shirt renders as approved (C158). gc1 used AS IS.
STATE: round 29 (handover, ~95 tool calls). Pattern r29p2 (collar roll 21 mm, cutaway 10 deg) gated PASS_WAIVED on its
OWN keys (C164: rounds 25-28 ran on r19a's keys; cloth_release.write now refuses another pattern's). Collar FIXED (shirt
shows 11 / 14 / 16, tell 10-20). Lapel / V reach the concept only with lapel pins (r29b), which ripple the fronts and
break the R side. Crumple 12.4 / 11.4 -> 10.4 / 10.2 (r29a, cutaway): not solved. Nothing approved. $0 spent.
Suite (14 files, capped -rs): exit 0, 250 passed, 5 skipped (3 wf_simon + 2 freesewing), 3 xfailed.
NEXT: (1) r29a is the candidate base (render it: post29.sh r29a; not rendered yet); r29b's look is WORSE than r28h
(wavy ridged lapel edges, rope fold down each front edge in the belly crop, ragged hem corners). (2) the lapel: open the
roll line in the CLOSED fit (the closed fit's roll sits 33 / 8 / 0 off CF at 150 / 250 / 350; concept 69 / 64 / 59),
not by pinning the turned edge in the release; (3) crumple: the cutaway alone gave -2 mm; next lever the lap below the
break (overlap 20 mm -> less below the top button) or Joe's call; (4) mesher zero-area faces (chip filed), notch angle
57.9 (waived), closed-fit p99 11.0 -> 14.6 with the lower collar (read where).
## Method
Pattern: fr29.py (fr27 at the form recipe ROWS_H 0 + env COLLAR_ROLL / GORGE_DROP / BREAK_Y / CUTAWAY). r29p2 =
COLLAR_ROLL=21 CUTAWAY='{"angle_deg": 10, "start": 0.2, "end": 0.55}'. Closed fit: job29.sh <tag> (gc1, LAPEL_W
0.081, ROLL_R 6 mm, ROLL_GAP, STAND_RUN_OFF) -> asm + neck29 / lapel29 reads. Gate: gate29.py <tag> $FR29/waive29.json
<placed.pkl> (prints the placed keys: must equal the gate's). Release: BASE=$FR29/asm_r29p2.pkl ./arr.sh <tag>
arrange=1 keep=1 pull=100 side=1 hang=plumb selfclear=1 start=$BASE placed=$FR15/placed_641f7d9cce52.pkl [lapel=1].
Post: post29.sh <tag> (recull BELT 50 + render23 views) ; reads29.sh <asm>... (crumple ITER 10, collar, lapel, side, flaps).
## Table (concept | r28h | r29a | r29b)  [$FR29 = /mnt/data/hifipushie/dress_garrett/fit_round29]
collar top above HPS CB/45/side: - | 47/38/22 | 41/32/17 | 41/32/17; shirt shows (10-20): 5/7/11 | 11/14/16 | 11/14/16
lapel outer 150 L/R: 127/134 | 110/111 | 107/106 | 125/131;  at 250: ~110 at 261 | 58/63 | 53/56 | 106/98
V at 200: 237 | 168 | 155 | 232.  crumple p95 L/R (tilt): closed 3.5/3.9 | 12.4/11.4 (24/33) | 10.4/10.2 (34/40) | 11.5/10.5 (50/47)
edge off CF 450/550/650 L|R: 70,80,91|66,74,83 | 67,77,91|63,69,83 | 48,61,85|48,63,88 | 64,71,97|44,54,73
side line max L/R: <=20 | 20/21 | 20/20 | 21/40 FAIL.  flaps p50 (sunk/25): - | 3.2/4.4 (1/1) | 3.2/4.6 (2/0) | 5.9/2.2 (2/0)
hem sweep (front view): 482 | 409 | 394 | 392.  lapel through its base L/R: - | - | 0/0.085 | 0.03/0.18 FAIL.  stretch p99 11.0 | 14.6 | 14.6
## Sheets ($FR29/check): wholefront / upper_front / upper_three / side / lapeltop.L / lapeltop.R _r29bc.png (ref | clay
| diag); belly_r28hc_r29bc.png (Joe's spot, r28h | r29b). r28h's: fit_round28/check/*_r28hc.png.
## Dead ends (one line each)
- Gravity substitutes; release neck unheld; fronts' crossing fixes (cloth.md r20-r25); plumb cut at the side seams.
- Roll rows graded to 2.2 mm (C156). No-sim styling without a layer floor (C157).
- Crumple: edge pinned at ends only, soft pull 10, sides held above the waist, facing band (round 28).
- Collar roll 16 mm (CB top stays 38, side fall no longer covers the stand); roll 20 (zero-area collar faces at mesh).
- Lapel pinned out on its turned edge in the release (r29b): numbers to the concept, look worse, R side broken.
