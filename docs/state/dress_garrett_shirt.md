# STATE: dress_garrett_shirt (Garrett's shirt, open collar) -- 2026-10-22, garrett collar round 3 (done, PARKED)

ROUND 3 (files $G/r3; notes cloth.md "garrett collar round 3"; ledger C160): the lump as a MEASURING fault. The tape's
hps (loop 2 cm up the neck) sits on Simon's crest but 19 mm above Garrett's. New tape mode "corner" (FS: where the neck
meets the shoulder: the crest just outside the neck; Garrett 23 down / 24 back, Simon 5 down), hps tapes rebased by
the drop so only the neck moves. Garrett hd: ridge 61 -> 13 PASS, bump 14.8 -> 10.1 FAIL (<= 8), crumple .299, throat in
gc1's frame kept; Simon better (21 -> 16 deg, 5.3 -> 4.5). LOOK: NOT better than gc1 (fall buckles at the shoulder seam,
collar 11-15 mm lower round the back, leaves shorter). Left: a front pillow = front neck depth from the neck girth vs
the body's drop (band holds the throat); -15 mm depth: bump 8.4 but throat up 11 mm.
CODE: PARKED opt-in (measure_defs.HPS_CORNER False; garment key hps "corner"); gc1 / gc_garrett unchanged.
NEXT: Joe's call: keep gc1 (lump stays), or a round on the corner (front neck redrafted from the body's drop with the
neckline length kept + the fall's shoulder buckle). Sheets: $G/r3/gc1_vs_hd_sheet.png, side_crop_gc1_hd.png.

MUSLIN TEST (C161; notes cloth.md "stiff-thread muslin test"): refitted with threads held / shear free, most of today's
red is the fit's own; REAL misfits on Garrett: the yoke corner at the neck point (threads p95 8 %, shear 47 deg) and
the hips (side seams 4-19 mm open). Straightening (r3b) can't fix the lump: it is the relaxed shape. NEXT (Joe): a
muslin gate, then the two misfits as pattern alterations; maps $G/r3/mapn_garrett_sheet.png, mapn_simon_sheet.png.
MUSLIN DEFAULT (C162 ENFORCED; branch claude/muslin-default, NOT landed: coordinator lands; C165-C169): no holds; styling
solve = the fit's woven cloth (WOVEN_STYLE on, SHEAR_FREE undriven); stops read threads + per-piece shear lock 35 (C169).
17 files exit 0: 280 passed, 4 xfailed ($M/p3/s1.log). Look $M/p3/simon_styled_sheet.png: rows pass, but the V is
shallow (fronts overlap to the throat; photo's V to the 2nd button), leaves small / flat. NEXT: land; then V depth. Jacket
on the muslin fit ($M/jacket_jon1_sheet.png): boxy, fronts lap to hem, high V, narrow lapels: NOT the concept.

ROUND 2 (branch claude/garrett-collar-lump, files $G/r2): Joe approved gc1's throat / V / points / button; the one fault
is the LUMP under the fall's outer edge (side view). MEASURED: the shoulder seam (front | yoke) within 50 mm of the neck
point bridges Garrett's neck-shoulder corner (seam 28 mm off the body; crest 61 deg, bump 14.8 mm vs wf_simon 21 / 5.3);
yoke sheared +7 / -5.5 %. In the CLOSED fit (styling moves it < 1 mm). CAUSE: the neck point (tape "widest", 2 cm up a
near-vertical neck): HP_HPS=base (hb, diagnostic) takes crest 61 -> 26, bump 14.8 -> 8.8, but redrafts the approved throat
(button 85.9 -> 55.6, V 47 -> 24). Ruled out: truing ops, shoulder slope (line; 33.9 can't be drafted), the seam's
neck end bent 13.6 deg down (sb34: lump unchanged, throat moved, C155), neck_split off, every styling op.
LANDED: garment_pull.neck_lump_rows (crest <= 32 deg, bump <= 8 mm), printed by fit_garment, KAT, C154. gc1 FAILS them.
NEXT: Joe's call: keep gc1 (lump stays) or reopen the neck point for shirts (base of neck; reopens the throat and the
parked HPS research). Sheets: $G/r2/lump_side_gc1_vs_hb.png, hb_styled_sheet.png, hb_styled_z_sheet.png.

ROUND 1 STATE: crumple FIXED on Garrett (collar crumple .37 -> .23, tips clean, 0 folded), button 1 held, concept's first
button (85.9 vs 83). NOT fixed: the throat stays closed (band corners 0.20 x neck vs concept 0.69) and the leaves
splay (front edge 51 deg vs 27-34, points 73-75 below HPS vs 50-61). wf_simon unchanged (every open-collar row PASS).

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

## Big reads (concept | probe s1 | gc1)  -- wf_simon: probe w0 | w2 (identical)
- V below HPS (big_reads): 60 | 122 | 47           -- 212.6 | 212.6 (big_reads V on wf is the gap rule's, suspect)
- Points apart: 147 +-20 | 176 | 154               -- 179 | 179
- Points below HPS 50-61: | 59 / 66 | 73 / 75      -- 68 / 67 | 68 / 67

## Commands ($G/r3; run.sh = this worktree's code under capped)
fit.sh <tag> [ENV=..] (closed fit of gc_garrett, MODEL=wf_simon, G_EDIT='{garment edits}', e.g. {"hps": "corner"});
style.py <res pkl> <tag> <model> [ops.json] (style + big reads + open rows + lump rows); render.py <tag> styled (ZOOM=1).
