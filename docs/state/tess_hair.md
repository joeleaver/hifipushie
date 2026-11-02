# STATE: Hair (route done 2026-11-01; Tess cards section below is STALE, as of 2026-10-19)

## Hair route (2026-11-01, branch hair-route): a blind agent is walked down one path
- Code: src/hifipushie/hair_route.py (server.py only calls it). Default path: top of hair_guide.md.
- Done: blockers 5, 7, 10, the routes, blocker 4's small part. first groom on a `base` = strands; `hair.export` keys closed;
  groom_hair(style="cards") refused; every hair tool ends `next:`; find_tool("hair") leads with the path; hair_short.md =
  shells (sources moved to hair_background); `hair.head` hash with a warning in groom, look, export_hair, export_asset.
- Grown solid grooms on a `base` with no style (153 in workspace/) stay locks and warn. No stored hash = no head warning.
- Not done: blockers 1 and 2 (constants not promoted: a default shell or card export is unjudged), 3 (no trial), rest of 4
  (no approval gate, tie_hair carry_from without reseat still regrows), 6, 8, 9.
- Unverified: no render or real MCP session this run; `next:` on look_hair, export_hair, hair_reference tested on the route
  functions, not through a render. Real specs: hg_G88a reads short, th_W18 not, hash stable on both (copies).

## STALE below: 2026-10-19. r47 landed by hand in 89638730; its flags are still opt-in. Check before trusting.

## BEST CARDS FOR EXPORT (NOT approved: bin/approve is Joe's / the coordinator's)
- **r47b**: /mnt/data/hifipushie/haircards/exp/exar47b/hc_s2.glb (+ hc_s2_LOD1.glb, _LOD2, _LOD3). Branch tess-hair-r47.
- Settings = r45a's + two opt-in levers (they're off by default; the export MUST pass them):
  `hk.FILL=1 hk.TONE_FRONT=1.0 hk.TONE_CONTRAST=3.0 'hk.TINT_TOP=(0.85,1.6)' 'st={"hairline_row": {"pass": true}}' hk.WISP_ALPHA=0.95 hk.WISP_KIDS_FACE=6 hc.HUE_CLIP=1`
  `hc.BEND_ROWS=30 'hh.CAP_TONE_TIERS={"far": 1.9}'` (t47/r47.sh). Groom th_W18 (stage hc_s2); reference groom render gSc.
- Hair tris / verts per LOD (drawn, back faces incl.): LOD0 43556 / 23249 (card faces 19800 of 25000, drawn <= 50000),
  LOD1 20116 / 11159 (drawn max 25000), LOD2 14284 / 8568 (16500), LOD3 4092 / 2671 (5000). All in budget.
- A/Bs: r47b vs r45a on LOD3 crops (photo ponytail_right.jpg | X | Y), fresh blind subagent (review-ab rate-limited):
  NEW 4 / OLD 0 (t47/ab1). Earlier: r45a vs r44d NEW 2 / SAME 2; r46h vs r45a OLD 4.

## Round 47 (LOD3)
- Zero-match cause: LOD1-3 tiers (main / npc / far) aren't the clumps cut; their cards come from hc.clump_cards, which set no
  "cls". Every class filter (BEND_CLS, TAIL_AXIS_N, FIT_FLOOR) silently matched 0 cards there. Fix: hair.stamp_cls stamps
  hair_clumps.classify's class from the lock. Side effect: TAIL_AXIS_N (default 1) now reaches LOD1-3 tail cards too.
- Tail: BEND_ROWS 30 tail-only now matches 181 / 74 / 74 / 39 cards (LOD0-3). LOD3's big folded dark panel is gone.
- Head: the far tier keeps no head cards (group "free"): the cap IS the head. CAP_TONE_TIERS far 1.9 (vs 1.4).
  LOD3 / LOD0 mean head luminance (hair ID mask, top 40 %, same camera) g2v1 / g2back / g4v1:
  r45a 70.5/77.0, 76.3/94.0, 71.8/79.2 (-8, -19, -9 %) -> r47b 80.3/77.0, 91.8/94.0, 81.9/79.3 (+4, -2, +3 %).
- Lever rule: hc.lever_matched prints matched / population and raises LeverMatchedNothing for an ON lever matching 0
  (BEND_ROWS, FRONT_SHORT); tests/test_hair_levers.py.
- Sheet: t47/sheet_b.png (rows tail g2v1, tail g2back, head g2v1, head g2back: photo | LOD0 | LOD3 r45a | LOD3 r47b, 3 m).

## Open faults (by game visibility)
1. 1 m: crown / part blotches; 2. dark splintered patch at the part (FRONT_SHORT matches 0: another builder makes those cards);
3. pale flat temple panels (WISP_KIDS_FACE 1 untested alone); 4. 3 m LOD3: a few strays still stand off the tie; the
   whole LOD3 tail is darker than LOD0's (all-hair mean -7 to -8 %; the far tier's tail cards are tile cards, not baked);
   reviewer: both LODs are flat brown, none of the photo's waves / highlight streaks; 5. 1 m: blunt tail end.

## Decisions in force
- COORDINATOR: keep the OUTLINE RULE; budget counts DRAWN triangles incl. back faces.
- Adopt only by blind A/B (bin/review-ab, else fresh blind subagent; trios t43/trios.py). Judge hair in EEVEE.
- Joe: the assembly agent takes the best build (docs/state/tess_export.md).

## Dead ends (don't retry)
TAIL_TONE .55; tip fade / taper .45; TAIL_END_JIT .35; BABY_TONE for nape ticks; TAIL_LONG .35 / TOP .3; FLY_FRONT .04;
CAP_TONE 1.7 (globally); WISP_ALPHA .7; tint low ends .95; BEND_ROWS on every class; TONE_CONTRAST_DARK 2.0; > 25k tris.

## Commands (D=/mnt/data/hifipushie/haircards)
Build + LOD0/LOD3 shots `bash t47/r47.sh <tag> [flags]` (run47.sh = run.sh on this worktree); shots only t47/shots47.sh;
head luminance t47/headlum.py <tag>; tris t47/lodcount.py exp/exa<tag>; tiles t47/tiles.py <out> r45a <tag>.
History: docs/notes/hair.md "hair-cards round 47 (LOD3 fix)".

STATE: round 47 done, r47b best. NEXT: coordinator / Joe approve r47b; export with the two extra flags.

NEXT: blockers 1 + 2 with renders and a transfer test (promote the winning card and shell values to defaults), then a blind hair trial.
