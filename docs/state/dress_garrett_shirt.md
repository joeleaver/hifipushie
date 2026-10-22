# STATE: dress_garrett_shirt (Garrett's shirt, open collar) -- 2026-10-22, garrett collar round 2 (in progress)

ROUND 2 (branch claude/garrett-collar-lump, files $G/r2): Joe approved gc1's throat / V / points / button; the one fault
is the LUMP under the fall's outer edge (side view). MEASURED: the shoulder seam (front | yoke) within 50 mm of the neck
point bridges Garrett's neck-shoulder corner (seam 28 mm off the body; crest 61 deg, bump 14.8 mm vs wf_simon 21 / 5.3);
yoke sheared +7 / -5.5 %. In the CLOSED fit (styling moves it < 1 mm). CAUSE: the neck point (tape "widest", 2 cm up a
near-vertical neck): HP_HPS=base (hb, diagnostic) takes crest 61 -> 26, bump 14.8 -> 8.8, but redrafts the approved throat
(button 85.9 -> 55.6, V 47 -> 24). Ruled out: truing ops, shoulder slope (line), neck_split off, every styling op.
LANDED: garment_pull.neck_lump_rows (crest <= 32 deg, bump <= 8 mm), printed by fit_garment, KAT, C154. gc1 FAILS them.
NEXT: Joe's call: keep gc1 (lump stays) or reopen the neck point for shirts (base of neck; reopens the throat and the
parked HPS research). Sheets: $G/r2/lump_side_gc1_vs_hb.png, hb_styled_sheet.png, hb_styled_z_sheet.png.

ROUND 1 STATE: crumple FIXED on Garrett (collar crumple .37 -> .23, tips clean, 0 folded), button 1 held, concept's first
button (85.9 vs 83). NOT fixed: the throat stays closed (band corners 0.20 x neck vs concept 0.69) and the leaves
splay (front edge 51 deg vs 27-34, points 73-75 below HPS vs 50-61). wf_simon unchanged (every open-collar row PASS).
NEXT: open Garrett's throat without stretch (see "Next fault"); then a blind review of gc1 vs the concept / trace.

Branch claude/garrett-collar (from claude/probe-garrett). $G = /mnt/data/hifipushie/garrett_collar (scripts + sheets).
Workspace model gc_garrett = pg_garrett (probe: sh_garrett v19 minus its open-neck fold) + three garment edits, each
with a *_source key: closures front first 0.043 from cfNeck (concept 83 below HPS), collarWidth / collarBend dropped
(Simon's defaults), style {"turn": {"tol": 0.005, "steps": 16}}. Jacket NOT fitted (C85).

## What changed (code, shared; ledger C147)
- hold_mask("closure:front") holds every fastened pair + 8 mm of cloth round it (s1 pulled button 1 8.7 mm open).
- The turn's stretch read counts only edges with a free vertex (Garrett's HELD fronts, 21-24 %, pinned the read at
  15.5 %). Tried for pull / smooth too: it broke the sp10 KAT (points 138 -> 121) and changed nothing on Garrett: reverted.
- turn "tol": until it would stretch (off by default: on wf_simon it fails 4 photo rows, see below).
- "piece:@closure" point names (the top fastened pair's vertex: a front's roll line); garment "style" edits by op kind
  (garment_pull.style_ops). Docs: cloth_tools.md. Tests: test_worn_style_holds_the_fastened_buttons (control opens the
  pair > 3 mm), test_a_garment_edits_its_wear_style_by_op_kind.

## Measured (round 1)
- Crumple root = Garrett's own collar options (C129-era collarWidth 1.68 / Bend 0.015): outer edge 515 over a sewn 441
  (spring 74; wf_simon 45), the closed fall lay WAVY (radius bumps at CB and +-75 deg, edge turn 85 deg / 40 mm, left
  tip folded 2 faces, tip crumple .68) before any styling. Simon's defaults: spring 46, fall 47 / stand 30.5, tips .09.
- The leaf is SLACK, not over-pulled: collar p99 3.9-4.0 % to 60 mm of pull, rising only from 66. The pull's stop can't
  bound a slack flap (bending is free in the solve); it runs to max_move 45 on Garrett.
- The KB's fixed 65 deg band-end turn stretches the free fronts' tops: Garrett p99 23 / 13 % (wf_simon 15 / 16 %). At
  the concept's button it tears them (p99 39 %). Until it would stretch: Garrett 20 deg, wf_simon 53-61.

## Big reads (concept | probe s1 | gc1)  -- wf_simon: probe w0 | w2 (identical)
- V below HPS (big_reads): 60 | 122 | 47           -- 212.6 | 212.6 (big_reads V on wf is the gap rule's, suspect)
- Points apart: 147 +-20 | 176 | 154               -- 179 | 179
- Points below HPS 50-61: | 59 / 66 | 73 / 75      -- 68 / 67 | 68 / 67
- First done button: 83 | 203 (b1 8.7 open) | 85.9 -- 131.8 | 131.8 (gap 0)
- Strain p99 drawn: | 14.2 % | 7.8 % (collar+stand+fronts 6.2) -- 9.6 | 9.6
- Collar crumple p95 <= .30: | .37 | .23; tips .68 -> .066; folded 2 -> 0 -- .25 | .25
- Open rows FAIL on gc1: corners .20 (.4-.75), V depth below tips -.15, leaf front edge 51 (25-48), edge turn 59 (32).

## Next fault (ranked)
1. Throat closed / leaves splayed on Garrett. Leads: the band ring hold (70 deg + feather 130) and the pull's direction
   (side + 0.3 out) set where the slack leaf lands; nothing measures "stand beside the neck". Try a pull stop on the
   leaf's front-edge angle or the tips' height (50-61) instead of max_move, and a softer front roll that carries the
   band end without moving the fall (r2 dragged the fall down). Prove on gc1's closed pkl (style.py, 70 s per look).

## Commands ($G; run.sh = this worktree's code under capped)
cfit.py <model> <tag> [garment json] [option edits json] (closed fit, 5-7 min Garrett); style.py <res pkl> <tag>
<model> [ops.json] (style + big reads + rows, ~70 s); render.py <tag> styled (ZOOM=1 close-up); mkops.py (edit KB ops).
History: docs/notes/cloth.md "garrett collar round 1"; earlier rounds: cloth.md "shirt round 12" and the probe.
