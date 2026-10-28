# STATE: hang, round 2 (the fit hangs from its supports; threads hard) -- 2026-10-28

GOAL (Joe 2026-10-27: "We're still getting wings on the side ... that and the disconnected sleeves are the main
things"): a HANG step in the default fit: cloth hangs from its supports (shoulders, a waistband, the neck) under its
weight, rests on the body only where it touches it from above; nothing drawn into hollows. Threads hard (C235).
PASS (default path, no per-garment flags): C242 gates (wings <= 20, sleeve top gap <= 10, shoulder apex <= 8, hollow
<= 10 mm) on trial_hoodie_t6:hoodie, trial_tshirt_t5:tee, trial_shirt_t7:shirt, gc_garrett:jacket; threads past cap
p99 <= 1 %; inside ~0; fit tests no new failures. Then hang_reads.HANG_STEP = True + clay renders judged.
Round 1 (branch worktree-agent-ae2f8e92379fe5450, failed: tethers, no hard threads) not merged.

HARNESS (/mnt/data/hifipushie/hang2/): run.py (fit as fit_garment makes it + reads + past-cap p99 -> results.jsonl,
<tag>.pkl with phase snapshots + per-face over-cap), batch.sh, reads_pkl.py, plot / hsec / sleeve_sec / shoulder_sec /
overmap / wing_levels / neckpt / info.py. pattern_form.RESUME {phase: X} replays phases (A/B only, None in every fit).

THE STEP (all opt-in flags so far, candidate C1 = C1.txt): the seat draws cloth only onto up-facing body (HANG_SUPPORT,
existing), NO let-go (HANG_FROM_SEAT: the let-go sprang the hung sleeve back round, hoodie sleeve top 4.9 -> 13 mm),
then the weight (HANG_G 0.3, 200 rounds): supports = contact where the body faces up (HANG_UP n_z > 0.3) held where it
came to rest (HANG_ANCHOR, HANG_HOLD 1000: 10 crept, the hoodie slid 36 mm), the shoulder point not pinned 12 mm over
the shoulder (HANG_FREE_SHOULDER: the pin made the apex), the lengths 10x the weight's pull (HANG_STIFF: at 1x the
solve stretched the torso faster than 30 sweeps / round could project it back: hoodie past cap p99 3.2 % -> 0.7 %),
10 hard sweeps / round (HANG_SWEEPS), refactor only when 50+ supports change (HANG_REFAC: 1 s -> 0.4 s / round).

MEASURED (resumed A/Bs, results.jsonl): tee_k10 wings 3.5, sleeve top 5.6 / under 6, apex 4.7, hollow 8.9; past cap
0.42 %; hang 34 s. hd_k10 wings 2.5, sleeve 4.1 / 28.5, apex 9.0-9.6 FAIL, hollow 0; past cap 0.72 %; hang 172 s.
Baseline: tee sleeve 13.5 FAIL; hoodie 46 / 16 / 11 FAIL, past cap 16.2 % (knit rib bands, see READ FIXES).
READ FIXES (committed with evidence in the code): (1) sleeve stations need cloth all round the arm (a partial hem cut
read the tee axis 47-49 deg); (2) wings read from below the armhole's bottom when it is under the armpit (the hoodie's
is 117 mm under; above it the torso cut crosses the armhole edges to the sleeve, 17-21 mm "wing" by construction;
below 1.5-3.5); calibration verdicts unchanged (hoodie 46 FAIL, the rest PASS); (3) thread_cap_pct of a knit band
reported against the DRAFTED pattern (it rests at its sewn length in the fit: hem band 14 % read as past cap).
OPEN: hoodie apex 9 (free shoulder from the start: running hd_c1), shirt / jacket not run yet; rib cuffs past cap
13 % (p99 of all faces passes); time.
NEXT: hd_c1 + sh_c1 full fits (running), jacket; then defaults on, tests, BUILD_VERSION, HANG_STEP, renders.
