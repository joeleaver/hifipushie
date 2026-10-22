# STATE: collar_spike -> shirt spike (Simon's shirt + its collar on the average male, closed + worn open, NO sim) -- 2026-10-21

GOAL (Joe): a fast loop (seconds per look) putting the PATTERN's own pieces on a body, closed and worn open, matching the
concept's open collar (trace /mnt/data/hifipushie/collar_spike/joe_trace.png; workspace/garrett_v20/concept_v8_front_apose.png:
V ~60 below HPS, leaves standing either side of the neck, points ~147 apart and 50-61 below HPS, first fastened button
83 below HPS) and Joe's open-shirt photos (placket edge runs straight up into the band end; the front rolls back SOFTLY,
the band turning with it; band ends lean apart; leaves stand off the neck). Joe: "We're almost there."

## Settled by Joe (don't re-litigate)
- The pattern has the right shape (FreeSewing Simon); don't re-draft / invent the collar (drape op parked for this).
- Collar + band are interfaced, stiff, not floppy cloth; the points are held off the chest, not lying on it.
- Simulation is not the path for this (Blender cloth crumpled every time); no closed-source tools; don't overengineer.
- Work like a modeller but fast and repeatable: staged moves that can't stretch, measured every look.

## Current best (wf_simon = MakeHuman 35 y / 1.78 m / weight + muscle 0.5; outputs /mnt/data/hifipushie/shirt_spike)
- CLOSED: repo defaults (landed, BUILD_VERSION 17) + the concept's button spacing = v1 (= e3): clean closed collar, band
  ends sewn flush with the placket tops, one rounded roll (176 deg), collar + band mirror p95 1.4-1.9 mm, strain p99 9 %.
  `spikes/shirt_spike/run.sh base_fit.py v1 '{"closures":[{"name":"front","spacing":{"first":0.034,"from":"cfNeck"}}]}'`
- CURRENT BEST f2: `{"swing":40,"steps":6,"nopush":1,"hug":70,"feather":[70,130],"swing_patch":0.015,"pulls":[P0],
  "smooth":{"pieces":["collar","stand"]}}`, P0 = points side 1 / out 0.3 / up 0, patch 0.025, turn. Band end swings as
  an AREA (3 pinned corners pinched a lobe: TopCf 21 -> 3 %). Hug FEATHERED (Joe: "one continuous swoop instead of three
  different angles"): held to 70 deg from CB, drawn back by a fading share to 130 (a hard hug edge kinked the profile:
  q40 29 deg; profile.py 18 deg now), side 73 mm from the neck centre (closed 68). Points 137 / 76, p99 6.3 %.
- Crease on the roll (Joe): the fold turns in TWO bends 4 mm apart (seam + roll line). Roll at the seam (offset 1 mm,
  radius 4 / 6 mm: r0a / r0b) softens the ridge; r0b stands the collar up + breaks the points; not adopted.
- SMOOTH (C143, sm1): `"smooth":{"pieces":["collar","stand"]}` after the pulls halves the crumple for +0.3 pt.
- OPEN (u25 = t15's pulls with "patch":0.025,"turn":1: each step drags the point alone, then fits the
  patch's unstretched start shape rigidly (Kabsch) onto that and solves again: tips clean (crumple p95 0.06-0.10 mm =
  closed; flips.py: 1 folded face per side at the patch edge, was 18 / 28 with a rigid patch), points 156 / 64-65.)
- Reads: tip.py / flips.py / rough.py / profile.py / csec.py / layers.py (history: cloth.md, ledger C142-C144).

## Open faults (ranked by what shows at 1-3 m)
1. u25: points 64-65 below HPS (concept 50-61); 1 folded face per side at the patch edge; a stretched patch at the V's corner (the fronts' cfNeck, welded to the band corners, have 34 mm of cloth
   above the first fastened button). Try the same pull on the band ends instead of a fixed swing; refine the fronts
   near the V (6-20 mm there).
2. y3 not yet judged blind against the photo / trace (bin/review), nor checked for cloth inside the body (push-out off:
   count it; a soft floor if it matters).
3. Make "pull until it would stretch" a general tool (pattern_form / MCP) for any garment handle (C142).
4. Not worked: sleeve ends crushed (99 % max, ~40 vertices inside each arm); yoke at the side neck 13 %.
5. Garrett (sh_garrett) not refitted on the landed defaults (own "open neck.R" fold + worn_open); see
   docs/state/dress_garrett_shirt.md.

## Decisions / rules in force (ledger docs/notes/codified.md)
- C137 a roll needs h <= pi r / 4 on its rows (collar + stand 2 mm on the form). C138 mirrored declarations must mirror.
- C139 the band is sewn edge to edge; its end continues the front's edge; no fold may turn the neckline a band is sewn to
  (the KB no_tie open-neck rolls are removed). C140 a fold's sense = the further-outside of the senses near the asked turn.
- Mirror rule (every bug of the day): take a SIDE from a landmark well off CF (hinge, neck point), never from a point at
  CF, where the band's ends cross; check every new rotation's sign on one vertex before a run.
- Every look: sym.py (mirror per piece), faults.py, csec.py / cbprof.py for the collar; reference beside the result.
## Dead ends (one line each)
- wrap.py home-made settle (crumples); Blender cloth b1-b10 (crumples once the seam springs pull).
- Rigid turns of the band fronts (geo.py: 46-80 % stretch); vertex ARAP with a closed-fit rest (can't open the ring).
- pattern_form worn_open for the open state: the band tops stay knotted at CF; collar_spread / OPEN_SPREAD dead levers.

## Commands
spikes/shirt_spike/README.md (every script); spikes/collar_spike/README.md (primitive-neck scripts). run.sh runs the
modest-napier worktree's code under bin/capped: edit its cd for another checkout. Renders take the GPU lock (capped).

## History
docs/notes/cloth.md "shirt spike 2026-10-21" (grep). Commits on branch claude/blissful-yonath-566ebc (modest-napier worktree).
