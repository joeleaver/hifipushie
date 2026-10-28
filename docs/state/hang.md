# STATE: hang, round 2 (the fit hangs from its supports; threads hard) -- 2026-10-27

GOAL (Joe 2026-10-27: "We're still getting wings on the side ... that and the disconnected sleeves are the main
things"): a HANG step in the default fit: cloth hangs from its supports (shoulders, a waistband, the neck) under its
weight, rests on the body only where it touches it from above; nothing drawn into hollows. Threads hard (C235).
PASS (default path, no per-garment flags): C242 gates (wings <= 20, sleeve top gap <= 10, shoulder apex <= 8, hollow
<= 10 mm) on trial_hoodie_t6:hoodie, trial_tshirt_t5:tee, trial_shirt_t7:shirt, gc_garrett:jacket; threads past cap
p99 <= 1 %; inside ~0; fit tests no new failures. Then hang_reads.HANG_STEP = True + clay renders judged.
Round 1 (branch worktree-agent-ae2f8e92379fe5450, failed: tethers, no hard threads) not merged.

HARNESS (/mnt/data/hifipushie/hang2/): run.py (fit as fit_garment makes it + reads + past-cap p99 -> results.jsonl,
<tag>.pkl with phase snapshots), batch.sh, reads_pkl.py (reads on X / Xs / snaps), plot.py, sleeve_dbg.py, info.py.
pattern_form.RESUME {phase: X}: replays relax1 / seat / let_go snapshots (A/B only, None in every fit).

BASELINE (current fit, no hang): hoodie 46 / 16 / 11 / 0 (calibrate.txt), tee wings 4.5-8.5, sleeve top 13.5 FAIL,
shirt hollow 26 FAIL, jacket hollow 25-27 FAIL. Tee fit 218 s (placement 100, let_go 63 s for 120 rounds).

FINDINGS so far:
1. Old HANG_FIELD path (n_z-weighted seat + 600-round settle, threads hard) on the tee: wings 2.5-3.5, sleeve top 7 /
   under 6, past cap 0.76 % (= base), but +435 s (settle 0.72 s / round).
2. Sleeve read counted a partial hem cut (16-point arc) as a station: tee axis 47-49 deg. Fixed in hang_reads
   (SLEEVE_ARC_GAP_DEG: the cloth must go round the arm); calibration fits unchanged (jacket under gap 5.7 -> 7.3).
3. Hoodie, hang seat + 200 settle rounds: at the SEAT wings 16 / sleeve top 4.9 (both pass), the LET-GO undoes it
   (24 / 13), the settle more (28 / 17): with no attraction the tube's bending (FIT_BEND, a round-tube regulariser
   far stiffer than jersey) springs the sleeve round off the arm; G 0.1 can't hold it down. G 0.4 on the tee slid the
   garment 47 mm down the neck (soft neck pins, creeping friction) and broke the threads (past cap 6.7 %).
4. Hoodie past-cap p99 15 % in the hang run: baseline number pending (knit bands read vs drafted pattern?).
NEXT: A/B on the tee / hoodie (resumed): settle bending 0.2, hang straight from the seat, static-friction anchors.
