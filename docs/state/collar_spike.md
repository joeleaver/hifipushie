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
- OPEN: `run.sh flatarap.py e3 g2 '{"pts":[0.147,0.055,0.015],"swing":50,"steps":8}'` (per-face ARAP against the FLAT
  pattern, staged from the closed fit; held back / yoke / sleeves / fronts below the first fastened button; collar
  points to the concept; each band end swung about Simon's hinge ruling). p99 4.5 % vs the pattern; reads as an open
  collar (V, band ends upright with the plackets, leaves either side).

## Open faults (ranked by what shows at 1-3 m)
1. Open leaves crumple / ripple and sit low (flatarap has NO bending: interfacing behaves like tissue). The hinge-spring
   bending term (`kb`, `kb_pieces`) DIVERGES on collar / stand even with no handles (p99 70-75 % after one step; the back
   alone is fine; the rest is met exactly at the start): bug not found. Next: find it, or a dihedral term, or alternate
   with pattern_form's own made-piece bending.
2. The fronts don't roll back (taut at the V): add the soft roll (a fold row from the band end down to the first
   fastened button, or a front-edge handle), staged.
3. openm.py's V read is broken (reads 172-196); the V can't be scored until fixed.
4. Not worked (collar first): sleeve ends crushed (99 % max, ~40 vertices inside each arm); yoke at the side neck 13 %.
5. Garrett (sh_garrett) is NOT refitted on the landed changes: his spec still declares its own "open neck.R" fold and
   worn_open (both the faults found here); see docs/state/dress_garrett_shirt.md.

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
