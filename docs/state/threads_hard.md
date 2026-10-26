# STATE: threads hard (no cloth stretches in the fit past its cap) -- 2026-10-26

GOAL (Joe 2026-10-26: "why are we allowing it [to stretch]?"): threads are a hard rule in every fit; pins, the
seat, contact give way; a pattern that can't reach shows as what it can't reach (cloth inside the body, open seams,
neck points short), named by piece. Ledger C235 (supersedes the "stiff threads" half of C161-C167).
CODE (branch threads-hard, DEFAULT ON, env PF_THREADS_HARD=0 for A/B): pattern_form THREADS_HARD, piece_stretch_asked
(knit caps from the pattern's own seams), _thread_limit (Gauss-Seidel by colour + woven shear lock), _hard_pass
(threads + seams + closures at the end of every relax phase and of assemble), face_threads, info inside_by_piece /
neck_point_mm (soft pins listed); next_steps THREAD_OVER_P99_MAX 1 % past cap, misfit_lines; fit_garment reads threads.
SEAT_GRAVITY (no all-round attraction) NOT changed: on the soft fit it raised inside_body (hoodie 185 -> 222).
RUNS: $T=/mnt/data/hifipushie/threads (ab.py fit + readout, where.py per piece, phase.py per phase, dbg.py lone panel).
HOODIE (trial_hoodie_t2): body threads p99 8-10 % -> 2.7 %, seams 1 mm; misfit now READS: back 197 v 9 mm inside,
sleeves 118 / 174 v 10 mm, cuffs 16 mm (the trial's mis-shaped armhole / cap). Pre-seam-pass jacket: threads p99 3.7 %
but seams 39 mm open (fixed by _hard_pass; jacket not re-run since).
NEXT: suite ($T/suite1.log) -> fix / restate breaks; jacket + shirt re-run (hard3); then a FRESH trial agent makes a
T-shirt through the MCP (Joe 2026-10-26) on this branch; judge its full figure.
