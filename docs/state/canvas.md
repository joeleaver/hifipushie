# STATE: canvas (canvas / interfacing BENDING STIFFNESS in the fit + styling; the jacket with fewer holds) -- 2026-10-23

GOAL (Joe, after C190-C192): canvassed / interfaced pieces keep their shape by STIFFNESS so the workaround holds go.
Not a sim; no rented GPU. Joe (relay): the concept is SLIM-CUT, modern -> step 0 slimmed the pattern first.
STEP 0 DONE (C193): gc_garrett v6 (stored; gate PASS_WAIVED 2e1b8483 / e31aac35, r35 waivers). Flat before -> after:
chest 1113 -> 1104 (+14.1 %: floor = shirt 1067 + 2 pi 6; slim practice +7.5-10.5 cm needs a slimmer shirt), waist 1131
-> 1103, hem+30 1270 -> 1103 (r34 let-out removed), sleeve hem 319 -> 284, biceps ~417 -> ~405 (armhole-bound). KB jacket
fit "slim"; design fact on dress_garrett_fit.md. Stored shirt has a stale key "source_probe" (validate refuses it).
MODEL (C194, bending.py): edge HINGES (4-point stencil), weights canvas 20 / fusible 8 / plain 1 (entry "kind" or garment
key interfacing_kind; gc_garrett: front / stand / collar canvas); rest carried in the hinge frame (signed; hairpins
along the stencil). Vertex-Laplacian bending FAILED (saddles free). KATs tests/test_bending.py (4).
FIT: pattern_form.FIT_BEND_KEYED (OFF; env PF_BEND_KEYED=1 / garment key bend_keyed): + hinge term (w - 1) x FIT_HINGE_W 1
x FIT_BEND, flat rest, fold rows / flaps / made pieces skipped. on_form stores M["bend_w"].
STYLING: garment_pull.STYLE_BEND (OFF; GP_STYLE_BEND=1), W 5, plain 0 (a flat-rest plain term fought the floors: 15 %).
JACKET ($CV/tab38.sh; concept 71/78/94, waist 414, hem 482, V 237; r39 k3 60-64/74-77/101, hem 444, V 232, thr 7.42):
s1_k3 slim + PLUMB_HOLD + kb: 59-64/72-74/95-97, hem 443, V 233, thr 8.78 (the cord as before).
c0 slim, no plumb, no keyed: k3 41-48/44-46/53-55, none 25-32/71-78/30-33: the fronts lap (C189 again).
c2 slim + KEYED fit, no plumb: k3 54-61/67-76/84-88 hem 426 thr 9.71 (chest show-through); nab 53-60/68-76/84-90;
nhem 55-62/67-75/84-87 hem 473; NONE (no workaround hold) 52-58/67-72/82-86, waist 429, hem 472, V 240, lapel 136/140,
ahead 20-35, thr 9.62, front|side fold 3-21 deg below 500 (s1_k3 5-36, 43-61 above; cord gone in Joe's framing).
c1 keyed + plumb: 67-71/67-69/81-127, V 210, lapel 114/137: worse. Styling bend on the jacket (c2b_*): thr 15 %, worse.
SHIRT (shdiag.py on shirt_s0): full ops + STYLE_BEND: 2 rows fail; SIMPLER ops v3 (relax, hold, turn band ends, push x2:
no point pulls, no smooths) ALL rows pass at W 1-5, threads 12.5 (no bend: v3 fails 3; full ops 6.47).
SHEETS ($CV/check): cmp_wholefront|upper_front|side_s1k3_c2k3_c2none.png, joeseam_s1k3_c2k3_c2none_c0none.png.
VERDICT so far: the canvas FIT stiffness is what keeps the fronts open without PLUMB_HOLD (c0 vs c2); with it the
jacket styles with NO workaround hold, hem / V / seam better than k3, edge 450 / 550 5-8 mm short of k3, threads +2.2.
Not default yet. Suite (17 garment files + test_bending): 306 passed, 4 xfailed, PYTEST_EXIT 0 ($CV/suite.log).
NEXT (session 2): (1) FIT_HINGE_W 2 / 3 sweeps on c2_none (fitc.py tag '{"plumb_hold": false}' with PF_HINGE_W; then
sty2.sh <fit> <tag> ops_none.json): aim edge 450 >= 60, threads <= 8.5; (2) the c2 thread rise: where (diagH.py);
(3) pocket flaps ragged + L hem corner flip on c2_none; (4) if a variant matches k3 on edge and threads: defaults =
FIT_BEND_KEYED on + gc_garrett plumb_hold off + kb jacket.wear.open without the two holds, KAT (strip / jacket), ledger;
(5) shirt: decide v3 + STYLE_BEND (rows pass, threads 12.5) vs today's ops (6.47) with the coordinator.
