# STATE: Tess hair cards (hair-cards agent) -- rewritten 2026-10-19 (round 45 handover; round 46 in flight)

## Current best (NOT approved: bin/approve is Joe's / the coordinator's)
- **r45a**: /mnt/data/hifipushie/haircards/exp/exar45a/hc_s2.glb (+ hc_s2_LOD1-3.glb); LOD0 707 cards, 43,548 tris, in budget.
  = the hair defaults at round 45's commit (incl. hair.BABY_NAPE (0.05, 0.02), hair_clumps.TAIL_LONG .2 / TAIL_LONG_TOP .5,
  hair_cards TAIL_AXIS_N 1.0, hair.CAP_TONE 1.4) + flags hk.FILL=1 hk.TONE_FRONT=1.0 hk.TONE_CONTRAST=3.0
  hk.TINT_TOP=(0.85,1.6) st={"hairline_row": {"pass": true}} hk.WISP_ALPHA=0.95 hk.WISP_KIDS_FACE=6 hc.HUE_CLIP=1.
  Groom th_W18 (stage hc_s2); reference groom render gSc.
- Blind A/B r45a vs r44d: NEW 2 / OLD 0 / SAME 2 (t45/ab1). LODs NOT OK.
- Round 46 candidates (built, not A/B'd): r46c = TONE_CONTRAST_DARK 2.0 (crown FINE std, p10, dark width all move toward the
  groom); r46d = WISP_KIDS_FACE 1 (temple = a few thin hairs, not a sheet); r46f = hh.FRONT_SHORT .03; r46g = BEND_ROWS 30 tail-only
  (t46/q5.sh); r46h = r45a + WISP_KIDS_FACE 1 + TONE_CONTRAST_DARK 2.0 + FRONT_SHORT .03 = the round's A/B candidate (t46/q6.sh).

## Open faults (by game visibility)
1. 1 m: crown / part blotches: card-owned smears (low strand contrast, whole-card tint) vs the groom's broad bands of dark strands.
   Lever in test: TONE_CONTRAST_DARK 2.0 (r46c).
2. 1 m: dark splintered patch where the part meets the forehead: 17-20 mm front-centre clump cards on a long card's tile
   (squashed tips) + the cap's front edge. Lever: hair.FRONT_SHORT (r46f).
3. 1 m: pale flat temple panels (face wisp cards drawing every strand x 6 kids). Lever: WISP_KIDS_FACE 1 (r46d).
4. 3 m: LOD3 tail = faceted folded panels below the tie, strays at the tie, LOD3 head darker (head/L0 cards cut, cap shows).
   r46a (BEND_ROWS 20 all classes) made it WORSE; r46g (tail only, BEND_MAX 2) pending.
5. 1 m: no blonde highlight strands, no flyaways (groom's are curly frizz: cards refuse loops), stiff flat face strands, blocky tail tip.
6. Back: tail end a touch light vs the groom's darker ends.

## Decisions in force
- COORDINATOR: keep the OUTLINE RULE: the part counts as shown only where the groom's outline dips (game reads silhouette).
- COORDINATOR (2026-10-18): budget counts DRAWN triangles, back faces included (fit_budget halves with hair.BACK_FACES).
- Joe: only what's left for Tess game-ready; the assembly agent takes the best build (docs/state/tess_export.md).
- Adopt only by blind A/B (bin/review-ab, else fresh blind subagent; trios t43/trios.py). Coordinator sets the round's ranked list.
- Judge hair in EEVEE; heavy builds via run.sh (resources slot + capped).

## Dead ends (don't retry)
- TAIL_TONE .55 (r43a): back vs 3/4 tone is view-dependent. Tip fade / taper .45 (r43b), TAIL_END_JIT .35 (r43c).
- hh.BABY_TONE as the nape-tick fix (lighter dash still a dash): dropped babies under a tie instead.
- TAIL_LONG .35 / TOP .3 (r44b: thin grey tail). FLY_FRONT .04 (r44c: harmful; stays 0).
- CAP_TONE 1.7 (overshoots). WISP_ALPHA .7 for the temple (r45c: alpha is not the lever).
- Tint low ends .85 -> .95 (r46b = r46c to the pixel). BEND_ROWS 20 on every class (r46a: far-tier budget collapse).
- "Our crown darks are round smudges" (r46 streak.py: shape is not the difference; strand contrast and width are).
- More than 25k triangles does not fix this groom's cards (structural).

## Commands (D=/mnt/data/hifipushie/haircards)
- Build + LODs + EEVEE shots: `bash t46/r46.sh <tag> [flags]` (= t40/exa40.py hc_s2 -> lodx.py -> shots.py views g1v0,g1v1,g1v2,g1backl).
- LOD3 sheet: t46/lod3.sh <tag>; t45/lodsheet.py <tag> <png> g2v1 g2back.
- Measures: t45/capshare.py (cap vs card dark share), t45/blotch.py, t46/streak.py (elongation / FINE / width), t42/pix.py (pixel probe),
  t43/tailbot.py (tail bottom). Crown boxes g1v0 440,340,640,420 / g1v1 430,340,640,440; temple 450,370,530,440 / 430,370,510,440.
- Blind A/B: t43/trios.py -> /mnt/data/hifipushie/bin/review-ab (CLI rate-limited before 13:00 MT -> fresh blind subagent).

## History (grep only)
docs/notes/hair.md "hair-cards round 43".."round 46" and their "## Handover"; header line "BEST TESS CARDS FOR EXPORT".
