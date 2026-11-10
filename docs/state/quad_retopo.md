# Quad retopo (the whole export as clean quads, loops by intent; no template): STATE 2026-11-06

CLOSED 2026-11-10, NOT LANDED (idle worktrees cleared; this page's own verdict below: stop the method as the default
export). The code (quadlayout.py, cagemesh.py, facelayout.py, the asset / limbloops hooks, tests) and its 15 ledger rows
are in tag archive/quad-retopo, cut from main 8a142ff5; ledger ids on this page are that branch's own. Merge bar: export body p99
within ~1 mm of today's, 0 folds on the triangulated export, no tears, loops by intent. Ring fitting (runs 1-7,
`topology: "quads"`) is stopped: Puddles 47 folds / p99 3.92 mm, Scraps 52 / 7.1; today's 0 / 0.4-0.5.

## Run 15 (2026-11-06): pudq re-copied from pud2 v76 (thick ears, nub tail, free arm): NO-GO, worse than run 14
- Set-asides: tail end clean (the nub is surface now) and dropped; ear roots still bad, moved to (+-90, -60, 750) r 30;
  ear bases clean. Today's reference re-exported from v76 (export_pud2_v76): 11,111 tris, p99 0.41, 8 folds (armpit).
- Real export [all / outside the ear roots]: 11,292 triangles (+1.6%); folds 65 / 55 (armpit, ear roots); TORN OR
  TANGLED at elbow.L (31) / elbow.R (22); body p99 3.55 / 3.31 mm (bar 1.41); coverage p99 6.4 mm (today's 3.18; bar
  4.18): FAIL on all four. Coverage lost: the tail nub (47 mm: too short for a branch, the grid runs over it), ears
  (10 mm, 8 round), the armpit.
- Why: the free arm, 4.5 mm off the side, counts the whole side under it as its skin, so its hole takes 20-36 round
  and the budget; the floor-sized cage drops to 51 mm cells (trunk 16 round, ears and mouth 8). The armpit gap is
  under a cell: the side grid and the arm cross there. Not patched (rule).
- Fixed: a stub ("short") isn't a missing feature (it sent the ladder to 18,376 quads for 5,732).
- By eye (game preview, run15_byeye_today_left_cage_right.png): at racing distance the two can't be told apart; close
  on the head the cage's ears are visibly faceted, with notched edges. Snout, mouth, eyes match.
- View: at today's budget the cage spends its quads on its own minimum structure; every sculpt change (a free arm, a
  short tail) moves that floor. I'd stop the method as the default export. Keep it only as an option at ~2x budget.
- Run 14 (old sculpt): 10,968 tris, coverage 2.73, body p99 1.52 vs 1.4, all else passed (C390).

## Diagnosis (why ring fitting traded folds for accuracy)
Each ring was topology AND final position at once, shot from a skeleton chain onto the full-density surface, then
smoothed. Off a one-layer surface (junctions, bends, thin sheets, creases, the ruff) vertices on the real surface folded;
moved to a simpler one (trunk-only primitives, sunk tail root, ruff smoothed in) they were off by the difference, and the
export's error IS vertices off the surface (Scraps 116 -> 52 folds for p99 4.7 -> 7.1; Puddles 91 -> 47 for 1.96 -> 3.92).
3D smoothing re-projected to the nearest point shrinks round forms and jumps layers. Coverage wasn't the problem (p99 3.3
vs a decimation's 2.9 mm).

## Method (proposed, run 8 tests it): coarse cage by intent, subdivide, project, relax on the surface
1. The layout by intent (trunk rings, branch blocks, mouth / eye rings) as a coarse cage, checked for 0 turned / folded /
   crossing cells where it's cheap. Its poles are the final poles.
2. Catmull-Clark x2. 3. Each vertex along its normal to the skin facing the same way (an ear's sides apart); accuracy
   comes from this. 4. Tangential relax, local steps refused if they turn or fold a face (run 8: on the SDF with a short
   Newton step, not fine-mesh footpoints). 5. Fallback in tight creases: a Tutte / mean-value map of the patch (no flips).
- Ruff: each surviving layer its own cage piece (a tuft a tube extruded from a cage face) or its own part; finer stacks
  merge into one sheet and the normal map carries them. Ears: a flat box cage. Jaw / blink: the rings are cage loops.
- Risks: uniform subdivision (fingers, tail curl, ear tips need cage loops); normal rays crossing in tight creases.
- Alternative weighed: field-guided quads (QuadriFlow / Instant Meshes / QuadWild): on-surface and adaptive, but the
  2026-09 spike showed its loops aren't ours, it drops constraints and stalls, and its poles go where the field turns.
  Best used to fill a patch inside the cage.

## Proof plan (unchanged)
a. Cage 0 turned / folded / crossing, else NO-GO. b. Subdivide, project, relax; folds on drawn triangles, vertex error,
coverage vs a same-count decimation, poles. c. export_asset(rig=True): GO if 0 folds, body p99 <= today's + 1 mm,
coverage p99 <= the decimation's + 1 mm, no tears; wire beside today's, shoulder / hand / tail-root close-ups.
d. Scraps (tufts as cage tubes).

Dead ends: QuadriFlow whole-body; capped sheet rays; easing along tubes; caps shot from inside; loose tufts in body;
smoothing an inside-out cage patch (run 8);
midline ring respaced from its first crossing (twisted; start nearest the last); flap caps 2 rows (no change).
`/mnt/data/hifipushie/quadretopo/{cage.py <model>, cage_why.py, mirror_dbg.py <model> [div], dev.py, trifolds.py,
glbfolds.py, glberr.py, wire.py, cov_dec.py, export_all.py, measure13.py, cov_where.py, ear_cross.py,
cage_list.py, renders13.sh, renders14.sh, qlrun.py}`.
NEXT: nothing queued. Reopen from the tag only as a ~2x-budget option. Worth lifting by itself: limbloops.tube's
MAX_TURN (a curly tail's rings cut corners on the limbs path too).
