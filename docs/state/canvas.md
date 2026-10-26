# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-26 (s17)

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down; current garments are not a baseline.
Sessions: s1 78507629; s2-s14 claude/canvas2-14 ($S14 /mnt/data/hifipushie/canvas/s14; history cloth.md "canvas
stiffness session 14"). Ledger C190-C224.
DEFAULT (C205 + C206): interfaced garments fitted keyed, shirt floor from relax1, no plumb hold, styled on the shirt's
own cloth WITHOUT bending (= s8's d2), the FIT sews patch stitches. C209's RULE is on wherever the one solve runs; the
STIFF STYLING is OPT-IN (GP_STYLE_BEND=1 / =garment). C211-C217 (s10 / s11): opt-in pressed levers, findings.
S12: C218 lapel FACE read (garment_reads.lapel_face_reads); C219 roll_converge; v7 = break_y 0.44 + roll_converge 0.08.
S13 (spec v10 = DEFAULT r20 = v9 b20 + collar run_off; v8 = shirt `source_probe` -> `probe_source`, saves checked again):
| face below HPS | 150 | 200 | 250 | 300 | 350 | break | edge 450/550/650 | hem | len | thr p99 |
| concept L ; R | 62 ; 62 | 51 ; 53 | 39 ; 44 | 27 ; 37 | 14 ; 25 | 386 | 71/78/94 | 482 | 748 | |
| bc44 (v7) | 59 ; 60 | 47 ; 49 | 32 ; 35 | 18 ; 18 | 7 ; 9 | 365/375 | 57-50/70-70/95-101 | 481 | 729 | 5.75 |
| b20 (v9) | 63 ; 63 | 54 ; 54 | 42 ; 44 | 31 ; 32 | 18 ; 20 | 376/379 | 59-50/73-69/103-103 | 480 | 725 | 6.39 |
| r20 (v10) | 62 ; 62 | 54 ; 53 | 41 ; 43 | 28 ; 29 | 17 ; 18 | 374/376 | 61-49/74-67/98-97 | 486 | 728 | 5.55 |
- C220: the lower lapel was lost in the DRAFT (flat13.py: straight break -> point edge + belly 10 @ 0.4 = 18 mm 40 mm
  above the break; flat / 3D / worn agree; roll costs ~10 more). Lapel belly 0.02 @ 0.2 -> DEFAULT (LOOK
  check/cmp_b20_b18_bc44_*.png, ovl_b20.png; gate PASS_WAIVED 30c40cc66aaf2cc57ba1). b18 (18 @ 0.25) / b22 (22 @ 0.15)
  in the notes. KAT test_tailoring::test_a_low_lapel_belly_keeps_the_lower_lapel_wide.
- C221: "painted-on" lapel = the workbench clay light. lift13.py: outer edge 4-6 mm off the forepart (b20 similar);
  the same geometry in EEVEE (render13.py RTEX=1) shows the edge + stand like the concept. No geometry change.
- C222: notch tabs = the gate's waived row collar_stand_end (stand 14.2 mm at the end carries it as a tab). collar
  run_off true (R28, opt-in since round 19) -> the end lies flat, clean notch (check/notch_r20.png); collar_stand_end
  PASS; gate PASS_WAIVED 09456467b628eb573deb -> DEFAULT v10 (LOOK check/cmp_r20_b20_bc44_*.png).
S14 (no default change; v10 = r20 stays): causes per stage (repro14.py prints every fit phase + styling op per side).
| oL17 (PF_OPEN_LAP=0 + length_bonus 0.17) | 49 ; 49 | 68 ; 67 | 101 ; 98 | 747 | 478 | 42 ; 43 | 4.31 |
- C223: R/L asymmetry is the FIT's lap; OPEN_LAP False (opt-in; C232: worn_open lap false) evens it.
- C224: length is the draft: length_bonus is metres; 0.17 -> 747 (opt-in candidate oL17; LOOK level with r20, the V
  at the waist narrower: check/cmp_oL17_o0b_r20_*.png). The edge rows follow the break, which the STYLING closes
  (fit 64 -> first relax -11, smooth -4, pull -5 -> 42-53). Stiff styling (GP_STYLE_BEND) holds it but fronts 10-14 %,
  no hang (o0b): wrong model.
- Collar-end "fold": the collar fall's end (run_off) stands 6-13 mm off the lapel (cend14.py), R tilted more; lift cause open.
S15 (claude/canvas15): stiff styling threads-first: C225 caps bound stretch only; C226 thread weight per face. b2L (oL17
  fit + GP_STYLE_BEND=1): every edge row within +-8 of the concept, but the lapels ripple along the roll, threads 8.33.
S16 (claude/canvas16): C228 GP_BEND_REST_PRESS (bending rest = canvassed pieces smoothed bending-free), C229 GP_TF_BLEED;
  e7 = oL17 fit + GP_STYLE_BEND=1 + PRESS: lapels clean like r20, edges at the concept; collar 17 %, side kick, wide waist.
S17 (claude/canvas17; $S17 /mnt/data/hifipushie/canvas/s17; notes cloth.md "canvas stiffness session 17"):
- C230 GP_FINAL_SHEAR_HOLD (OPT-IN): the collar's 6 -> 42 deg was the threads-first LAST WORD shearing faces back under
  their bound (not bending / floors / fold): its lock is now max(entry shear, start shear). Collar 17 -> 7.3 %.
- C231 GP_TF_PD_PLAIN (OPT-IN): plain faces target their pattern in the PD step. Threads p99 6.81 -> 6.45.
- C232: levers are GARMENT KEYS: "style_bend": true | {"press", "final_shear_hold", "plain_pattern"}; worn_open {"lap":
  false}; env flags only override when set. No garment declares them: defaults unchanged (v10 = r20).
| run (L ; R) | edge 450 | 550 | 650 | len | hem | break | thr p99 | collar / stand | waist / hip |
| concept | 71 | 78 | 94 | 748 | 482 | 64@386 | | | 414 / - |
| r20 (DEFAULT) | 61;49 | 74;67 | 98;97 | 728 | 486 | 53;41 @380 | 5.55 | 11.0 / 8.7 | 402 / 424 |
| e7 | 72;69 | 80;76 | 99;98 | 744 | 477 | 58;55 @374 | 7.98 | 17.0 / 9.0 | 452 / 481 |
| e10 = e7 + C230 + C231 | 72;70 | 80;78 | 97;98 | 744 | 482 | 58;56 @373 | 6.45 | 7.3 / 9.5 | 453 / 479 |
  e10 = $S17/asm_e10.pkl; repro: oL17 fit + env GP_STYLE_BEND=1 GP_BEND_REST_PRESS=1 GP_FINAL_SHEAR_HOLD=1 GP_TF_PD_PLAIN=1
  (or the garment keys above + worn_open lap false + length_bonus 0.17). LOOK check/cmp_e10_e7_r20_*.png: = e7.
- NOT DEFAULT: (a) SIDE KICK + WAIST FLARE come from the oL17 FIT's let-go (relax with no attraction / weight below the
  break: lower fronts puff 25-30 mm forward at 450-500 below HPS; t0 / r20's fit does not, L17 and o0 both do). The stiff
  canvas there keeps it, the hang hangs the plain front plumb from it. Plain flaps in the fit (f1) and a hung pressing
  (e11 / e12) made it worse. (b) collar ends 13 mm off the lapel L (r20 8); (c) raster break 373 vs 386.
NEXT: (1) the oL17 fit's let-go puff: find why length_bonus 0.17 / no lap puff the free lower front (t0 doesn't; ph17.py
  per phase, xsec17.py); a fix in the fit (the free mode below the break), then restyle with e10's levers. (2) collar ends
  (cend14) and R gorge crumple. (3) raster break 373 vs 386. (4) blind review of e10 vs r20 once the limit resets
  ($S17/review_cmd.sh e10 | r20).
