# STATE: Garrett hair, shells (hair-garrett agent, branch hair-heads2) -- rewritten 2026-10-19 (sh4 handover; sh5 in flight)

## Current best (coordinator decision 2026-10-19, NOT Joe-approved)
- **sh4T**, style "shells", all four tiers in budget: $HG/cards/exp/sh4T/hg_G88a_hair_{hero,main,npc,far}.glb
  (HG=/mnt/data/hifipushie/hair_garrett). hero 13,068 faces (cap + 2 shells 9,300 + 83 hairline cards 3,768; drawn 16,836),
  main 7,392 / 8,496 drawn, npc 2,832 / 3,240, far 668 (cap only).
- Exact build ($HG/shells/sh4/q2.sh -> sh3/tiers.sh -> cards/c7/hx7.py hg_G88a <out> tiers=hero,main,npc,far):
  ex={"headroom": 2.0, "style": "shells"} hq.SHELL_WIDTH=0.0005 hq.SHELL_LIT=0 hq.GREY_SPREAD=1.0 hq.LAY_COVER=1.5
  hq.BASE_EDGE=0.008 hq.GREY_REGION=1.0 hq.BASE_DEPTH=0.25 hq.EDGE_SHADE=0.5
  hj.GREY_MAP={"top": .1, "fa": [0,60,100,140,180], "band": [.6,.75,.5,.3,.2], "low": [.5,.55,.35,.12,.08], "band_h": [.15,.35,.6,.8]}
  hj.SHADE_MAP={"top": .6, "band": [1,1,1,1,1], "low": [1,1,1,1,1]}
  hj.VALUE_MAP={"top": .5, "band": [.85,.7,.6,.55,.5], "low": [.8,.7,.6,.55,.5]}
  look={"card_grey": .7, "grey": "#6c6966", "lit": "#524e4a", "gap": "#1e1b19"} hh.SHELL_EDGE_LIFT=0.0 hh.SHELL_CARD_VALUE=0.75.
  These are module constants, not spec keys: the export sets them via assembly_garrett/s15/sh4t.py (Garrett v8 in flight).
- Blind A/B: sh4T vs c11L (previously shipped cards) NEW 2 / OLD 0 / TIE 2; vs c14s (hero-only) NEW 1 / OLD 3.
  Rule: future builds must beat sh4T AND, at hero, c14s.
- Numbers (hero, segmented all-hair p50 / MID std; photo front 43.1 / 3.7, q34 42.0 / 4.1, side 37.9 / 3.6, back 34.5 / 2.8):
  sh4T 43.5 / 5.0, 41.1 / 5.1, 42.3 / 4.9, 31.9 / 4.6.
- sh5 in flight ($HG/shells/sh5/q1.sh): sh5n / sh5m (SHELL_LIFT_EASE 12 / 20 mm), sh5t (texture: EDGE_SHADE .3, LAY_DEP_T .3,
  LAY_LEN 1.1, LAY_MIN 10 mm, LAY_WOBBLE .06), sh5a (all + silver sides + SHELL_CARD_VALUE .65). Unjudged.

## Open faults (by game visibility)
1. 1-3 m: black jagged NAPE fringe (side + back; reviewer's MAJOR): the CAP's alpha-tested tips at the hanging nape edge, still
   lifted inside the 5 mm ease (cards-only render clean). Lever: SHELL_LIFT_EASE 12 / 20 mm (sh5n / sh5m). Target black px g1back 0.
2. 1 m: no silver sweep over the ear / sides (front mid band 42.7 vs photo 51.2); back too dark / brown (31.9 vs 34.5).
3. 1 m: "wool" texture, no combing direction; MID std 4.6-5.1 vs photo 2.8-4.1 (EDGE_SHADE / BASE_DEPTH / combing).
4. 1 m: light temple plates (hairline cards +5.8 L* over the cap in profile: SHELL_CARD_VALUE .75 -> ~.65).
5. Back (export, v6 cards): crown ledge 6-7 mm step at el 60-75 deg (top layer standing off): cards issue, shells should remove it.

## Decisions in force
- COORDINATOR: budget counts DRAWN triangles, back faces included.
- COORDINATOR: top length / sweep must match G88a (a tight dark short crop), not a "carpet"; Joe on v4: "a totally different hairstyle".
- Adopt by blind A/B only (bin/review-ab after 13:00 MT, else fresh blind subagent; label-check the reviewer's faults).
- hair-heads2 commits are local only (never push). Hair judged in EEVEE.

## Dead ends (don't retry)
- Black rim as shadow or atlas alpha bleed (no-shadow render unchanged; transparent texels ~110). It was the cap's lifted underside.
- SHELL_EDGE_LIFT 1 mm (rim stays): 0 it is.
- SHADE_MAP for darkening (floors at .45): use VALUE_MAP. VALUE_MAP on the whole colour (killed the silver): base / dark strands only.
- Fins (SHELL_FINS): off; pale scales. GREY_SPREAD: stretched lock noise (use GREY_REGION / GREY_MAP).
- A coarser far cap: not needed (far cap 668 faces).

## Commands
- All tiers + shots: `bash $HG/shells/sh3/tiers.sh <tag> [hx7 args]` (hx7 sets constants as hq./hj./hh. <CONST>=<json>).
- Crops / measures: sh4/crop.py <out> <tags...> (hairline 3x), sh4/ctone.py (cards vs cap L*), m_*.txt from ns.sh.
- A/B: `bash $HG/shells/sh4/ab.sh <tag>` (tiles + review-ab vs c11L / c14s). Tests: tests/test_hair_shells.

## History (grep only)
docs/notes/hair.md "Garrett short-hair shells sh3" / "sh4" / "sh5" and their HANDOVERs; header "BEST GARRETT CARDS FOR EXPORT" (c6M cards).
