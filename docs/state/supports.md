# STATE: supports (supports, not holds: the hold redesign in the garment fit + styling) -- 2026-10-23

GOAL (Joe: "holding things that shouldn't be held"): a garment is SUPPORTED (body contact: shoulders, neck, the layer
under; sewn seams; fastened closures), everything else is FREE and HANGS (a weak downward field, stopping where a thread
would stretch / the weave jams); any hold left is SOFT, FEATHERED, and names its support. Not a sim. No rented GPU.
AUDIT: docs/notes/cloth.md "supports, not holds" (the table). No real support: PLUMB_HOLD, the kb jacket's hem-border
hold (C186), its rigid "above break" (partly: chest / canvas), styling grips held forever ("placed"), the seat's
all-round attraction (real only where the body holds cloth from below). Real: neck / shoulder pins, sew, closures,
layer contact, floors, the worn-open break (the canvas sets the roll's end, C171).
CODE (branch claude/supports, OFF by default): pattern_form.HANG_FIELD / garment key "hang" (settle + thread cap +
seat on up-facing body only); garment_pull.STYLE_HANG / relax {"hang": true} (FlatARAP.solve hang). KATs:
test_pattern_form test_hang_sheet_falls_plumb, test_hang_sleeve_tube; test_garment_pull test_hang_sheet_from_its_top_edge.
RUNS ($SU = /mnt/data/hifipushie/supports; run.sh -> this worktree; chain1.sh): nh = r39 fit without PLUMB_HOLD (copy);
nh_n = nh + kb style without the two holds; nh_h = + every relax hung; H = fit hang:true plumb_hold:false; H_h, H_k.
Reads per tag: r_<tag>.log (reads38 + edgeprof + prof + fwd33), seam_<tag>.log, sheets check/<tag>c_*.png.
NEXT: read chain1 results (chain1.done), table vs concept (edge 450/550/650 71/78/94, waist/hem 414/482, V 237, lapel
127/134, roll 69/64, seam fold), shirt check (test_garment_pull photo test), suite, report.
