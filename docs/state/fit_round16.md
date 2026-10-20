# STATE: fit_round16 (Garrett jacket worn open = closed fit + ONE release sim) -- 2026-10-20

DIRECTION (Joe 2026-10-20): open jacket = the BUTTONED fit on the dress form, then ONE short rented sim from that fit
that undoes the button and lets the fronts / lapels swing open under gravity. No more gravity substitutes on the form.

STATE: HANDOVER. Path built (cloth_release + MCP release_garment + fit_garment's next step), KAT PASS, ONE rented run
done (job_k, $0.0355, 47 s GPU, 167 s wall). RESULT: the released fronts barely open: break still ON CF (x -8 / +11,
concept 64), fronts still overlap at 450, edge off CF at 650 22 / 37 (concept 94 / 85). Chest stays (p50 3 mm). The
same with the neck unheld (local r16n) and with a 6 s settle (local r16L, <= 2 mm from r16). Blind reviews FAIL x3.
NEXT: (1) DRAFT: the fronts hang CROSSED OVER when free = a front balance / wrap fault (tailoring agent): too much
front across CF (lap + the cutaway's cfHem) and / or front too long for the back. Not solver tuning. (2) RELEASE
METHOD: the sim opens the seams (white lines along armholes / side seams in every review: the runner steps the fit's
coincident seam ends 1 mm apart, seam gaps mean 1.7 / p95 4.2 mm after 4 sew frames): try zozo stitch_gap 0.0005 or
sew_frames 12 on a LOCAL run (free, ~2 min) before the next rented one. (3) Pocket flaps sag 16-19 mm and gape (made
pieces released). (4) Notch / gorge (coordinator, Joe): measured, not fixed (collar stage next): r15e twist on the
lapel side p50 8-10 / max 26-40 deg/cm, collar tip 12.6 (L) / 3.5 (R) mm off the lapel, end 20-25 deg out of the
lapel's plane; r16 the same (collar held). Likely cause: the made collar end and the lapel meet at the gorge with
different planes (the collar end is laid by the made-collar code, the lapel by the fold relax): the seam carries the
whole turn between them in ~1 cm. Measure unvalidated (no known answer yet).

## Table (concept | r15e form, closed | r16 form + release sim); m10 front view, L/R
| item | concept | r15e | r16 |
| break below HPS (visible lapel) | 386 | 326/322 | 325/323 |
| break point x off CF (named) | 64 | -15/+15 | -8/+11 |
| opening half 150 / 250 / 350 | 69/64/59 | 49/18/0 | 44/17/0 |
| v_width 200 | 237 | 149 | 151 |
| lapel outer 150 / 250 | 127/112 | 110/47 | 108/47 |
| front edge off CF 450 / 550 / 650 | 71/78/94 | 0/0/6 | 0/6-19/22-37 |
| waist width / hem sweep | 401 / 478 | 324 / 431 | 320 / 447 |
| torso width 350 / 425 | 396 / 400 | 374 / 325 | 371 / 321 |
| side off body 350 / 425 | ~57 / 61 | 47 / 24 | 45 / 22 |
| sideseam hem x / y | - | 209 / -68 | 228 / -73 |
| shirt-through (shirt outside jacket, verts) | 0 | 289 | 251 |
| chest stand-off p50/p90 L | - | 29.5/38 | 27.1/34.6 |
| stretch p99 (fit) / start over 5 % | - | 9.7 % / 5.2 % of tris | (local strain limit, start_over 0.06) |
| moved by the sim, front chest 100-300 p50/p90 | - | - | 2.9/6.2 (L), 3.0/4.4 (R) |
| moved, front hem 650+ p50/p90 | - | - | 19/27 (L), 39/61 (R) |
| moved, back p50 / sides p50 / flaps p50 | - | - | 6.4 / 10 / 16-19 |
Lapel face width (edgeprof) not re-read: the opening above the break didn't change (rows 150-250 within 5 mm).

## Files ($FR16 = /mnt/data/hifipushie/dress_garrett/fit_round16)
g16.py (build|gate; hold=none, zozo=json), submit.py (the rented run), zrun.py (local by hand), pre.py, prediag.py
(start pairs by piece), mk16.py (asm_<tag> from a job + region moves), still.py, cmp.py, meas16.sh (+ meas_r16.log),
notch.py, render16.py, review16.sh, katread.py. Jobs: job_k (THE rented run), job_kl (local, 6 s settle), job_n (local,
neck unheld). asm_r15e / r16 / r16L / r16n. Gate: PASS_WAIVED 51e12aabcedf45c7251a (r15e's pattern, vent waived).
check/: wholefront, upper_front, upper_three, side, back, lapel / lapeltop / break / hemcorner / notch .L/.R
(<name>_<tag>.png = ref | clay | diag; side / back clay | diag), tags r15e, r16. Reviews: review_{wholefront,
upper_front,upper_three}_r16.log.
