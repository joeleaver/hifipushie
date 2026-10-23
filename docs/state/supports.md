# STATE: supports (supports, not holds: the hold redesign in the garment fit + styling) -- 2026-10-23

GOAL (Joe: "holding things that shouldn't be held"): a garment is SUPPORTED (body contact: shoulders, neck, the layer
under; sewn seams; fastened closures), everything else is FREE and HANGS (a weak downward field, stopping where a thread
would stretch / the weave jams); any hold left is SOFT, FEATHERED, and names its support. Not a sim. No rented GPU.
AUDIT (C190): docs/notes/cloth.md "supports, not holds" (table). No real support: PLUMB_HOLD, kb hem-border hold (C186),
styling grips held forever ("placed"), the seat's all-round attraction. Real: neck / shoulder pins, sew, closures,
layer contact, floors, the worn-open break (C171), the canvassed forepart above the break (kept, rigid).
CODE (branch claude/supports; ALL OFF by default, no default changed): pattern_form.HANG_FIELD / garment key "hang";
garment_pull.STYLE_HANG / relax {"hang": true}; a hung relax floors on the body; worn_style(under=) (C191, C192).
KATs: test_pattern_form test_hang_sheet_falls_plumb / test_hang_sleeve_tube; test_garment_pull test_hang_sheet_from_its_top_edge.
RESULT (C191): the hang does NOT beat the holds yet. Best hung variant nh_h2 (no PLUMB_HOLD, hem hold off, canvas hold
kept, shirt floor, every relax hung): edge 450/550/650 30-41/38-39/50-55 (concept 71/78/94, k3 60-64/74-77/101), waist
407 (414), hem+30 460 (482), V 221, lapel 135/131, roll = k3, threads 8.76 (k3 7.42), stands 52-91 ahead (k3 26-34),
front|side fold 5-73 (k3 4-143). Fit hang G 0.1 (H): neck 53-62 % stretch, rejected. Shirt: hang fails 3-5 photo rows.
WHY (measured): local / global swings slowly + Jacobi caps leave strain under supports; made pieces are held by their
stiffness (not modelled); the lap is the seat's wrap, not missing weight.
RUNS: $SU = /mnt/data/hifipushie/supports (run.sh -> this worktree; chain1-7.sh; tab38.sh <tags>; diagH.py; shirt.py).
Sheets: check/cmp_concept_k3_nhh2.png, check/cmp_wholefront_k3_nhn_nhh.png, check/joeseam_k3_nhn_nhh_nhh2.png.
H2 (fit hang G 0.02): neck still 51 % / p99 17 % (not the load: the hang seating), H2_h2 collapsed. Suite: 302 passed, 4 xfailed, PYTEST_EXIT 0 ($SU/suite.log).
NEXT: coordinator / Joe decide whether to pursue the hang. If pursued: (1) a stiffness model for made /
canvassed pieces (their support) before hanging them; (2) replace the seat's all-round attraction (the lap's source)
by contact-only seating, measured on the edge 450-650; (3) soft feathered styling holds (FlatARAP proximal weights)
for the canvas hold. Otherwise k3 stays and dress_garrett_fit resumes r39 steps 2-4 on it.
