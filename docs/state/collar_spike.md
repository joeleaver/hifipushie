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
- Pull tool (fervent-bouman 0016774f) reproduces q40 / f2 / sp10 (via_tool.py; tsp10 kinks 10 / 20 vs 12 / 12). Joe: f2, pt2 best.
- sp10 (Joe: "none of these are yet producing one smooth swoop"): f2 + `"edge_smooth":{"spline":10,"lam":0.4,"win":0.03,
  "rounds":30,"tol":0.015}`: the collar's outer edge (boundary walk point -> CB -> point) drawn toward ONE smooth curve
  (LSQ spline, 10 knots) until it would stretch; side-view kinks 12 / 12 deg (f2 18 / 34). Neighbour averaging stalled.
- f2: `{"swing":40,"steps":6,"nopush":1,"hug":70,"feather":[70,130],"swing_patch":0.015,"pulls":[P0],"smooth":
  {"pieces":["collar","stand"]}}`, P0 = points side 1 / out 0.3 / up 0, patch 0.025, turn (C142-C144).
- Crease on the roll: two bends 4 mm apart (seam + roll line); roll at the seam (r0a / r0b) not adopted.

## Open faults (ranked by what shows at 1-3 m)
0. CURRENT BEST c1 (Joe: "do your best to get a clean single curve"): x5's recipe with "pulls":[P0 + "max":0.045] and
   `"feather_pieces":["stand"]` (the side hold keeps the BAND only: holding the fall too made an S in the front view: in at
   z 1525, out at 1505, back in to the tip; edgeplot.py). Front view: one arc CB -> tips. Side fall 91 mm from the neck
   centre (x5 72, closed 68): hugs less. p99 6.4 %, collar crumple p95 0.24, tips clean, tips 0.96 neck apart, V 62.
   x5 = x1 + "smooth2" (local smooth within 40 mm of each point: un-buckles the tips); x1 = e5 (first button 132 below
   HPS) + swing 65, push_pieces fronts, hug 70 / feather 70-130, swing_patch, pulls P0 max 0.025, edge_smooth spline 10,
   smooth collar + stand + fronts: angles all within / near the photo + trace (front edges 33-34, tips 1.01, corners 0.54).
2. No blind review vs the photo / trace yet; cloth inside the body not counted (push-out off).
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
